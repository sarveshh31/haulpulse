"""Silver step: validate bronze rows, upsert clean rows, quarantine bad rows.

Usage (from project root):
    python -m pipeline.run_silver                    # drivers + every trips file in raw.trips
    python -m pipeline.run_silver --date 2026-10-25  # one day only
"""
from __future__ import annotations

import argparse
import math
import time

import numpy as np
import pandas as pd
from psycopg2.extras import Json, execute_values
from sqlalchemy import text

from pipeline import reference as ref
from pipeline.db import get_engine
from pipeline.validate import RAW_TRIP_COLUMNS, clean_text, validate_trips

CLEAN_COLS = [
    "trip_id", "customer_id", "driver_id", "city", "vehicle_type",
    "pickup_lat", "pickup_lng", "drop_lat", "drop_lng",
    "distance_km", "eta_minutes",
    "requested_at", "pickup_at", "delivered_at",
    "status", "fare_amount", "payment_mode", "cancellation_reason", "updated_at",
    "source_file", "source_row_num",
]

# A late-arriving update only wins if its updated_at is newer than what we already hold
UPSERT_TRIPS_SQL = (
    f"INSERT INTO staging.trips_clean ({', '.join(CLEAN_COLS)}) VALUES %s "
    "ON CONFLICT (trip_id) DO UPDATE SET "
    + ", ".join(f"{c} = EXCLUDED.{c}" for c in CLEAN_COLS if c != "trip_id")
    + ", loaded_at = now() "
    "WHERE EXCLUDED.updated_at > staging.trips_clean.updated_at"
)

QUARANTINE_SQL = (
    "INSERT INTO quarantine.trips_rejected "
    "(source_file, row_num, trip_id, primary_reason, reject_reasons, raw_payload) VALUES %s"
)
QUARANTINE_TEMPLATE = "(%s, %s, %s, %s, %s::text[], %s::jsonb)"


def _py(v):
    """Convert pandas/numpy values to plain Python (NaN/NaT/NA -> None)."""
    if v is None or v is pd.NA or v is pd.NaT:
        return None
    if isinstance(v, float):
        return None if math.isnan(v) else float(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    return v


def log_validation(engine, source_file, stats, status, error, t0) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO ops.validation_log
                    (source_file, rows_in, rows_clean, rows_duplicate, rows_rejected,
                     city_fixed, status_fixed, status, error_message, duration_ms)
                VALUES (:f, :ri, :rc, :rd, :rr, :cf, :sf, :s, :e, :d)
                """
            ),
            {
                "f": source_file,
                "ri": stats.get("rows_in"), "rc": stats.get("rows_clean"),
                "rd": stats.get("rows_duplicate"), "rr": stats.get("rows_rejected"),
                "cf": stats.get("city_fixed"), "sf": stats.get("status_fixed"),
                "s": status, "e": (error or "")[:500] or None,
                "d": int((time.perf_counter() - t0) * 1000),
            },
        )


def read_bronze_trips(engine, source_file: str) -> pd.DataFrame:
    cols = ", ".join(["raw_id", "source_file", "row_num"] + RAW_TRIP_COLUMNS)
    with engine.connect() as conn:
        return pd.read_sql(
            text(f"SELECT {cols} FROM raw.trips WHERE source_file = :f ORDER BY row_num"),
            conn, params={"f": source_file},
        )


def process_trips_file(engine, source_file: str) -> dict:
    t0 = time.perf_counter()
    stats: dict = {}
    conn = engine.raw_connection()
    try:
        raw_df = read_bronze_trips(engine, source_file)
        if raw_df.empty:
            raise ValueError(f"No bronze rows found for {source_file}. Run load_bronze first.")

        result = validate_trips(raw_df)
        stats = result.stats

        q_rows = [
            (r["source_file"], r["row_num"], r["trip_id"], r["reasons"][0], r["reasons"], Json(r["payload"]))
            for r in result.rejected
        ]
        c_rows = [
            tuple(_py(v) for v in row)
            for row in result.clean[CLEAN_COLS].astype(object).itertuples(index=False, name=None)
        ]

        with conn.cursor() as cur:
            cur.execute("DELETE FROM quarantine.trips_rejected WHERE source_file = %s", (source_file,))
            if q_rows:
                execute_values(cur, QUARANTINE_SQL, q_rows, template=QUARANTINE_TEMPLATE, page_size=2000)
            if c_rows:
                execute_values(cur, UPSERT_TRIPS_SQL, c_rows, page_size=2000)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        log_validation(engine, source_file, stats, "FAILED", str(exc), t0)
        raise
    finally:
        conn.close()

    log_validation(engine, source_file, stats, "SUCCESS", None, t0)
    stats["duration_ms"] = int((time.perf_counter() - t0) * 1000)
    return stats


def process_drivers(engine, source_file: str = "drivers.csv") -> int:
    t0 = time.perf_counter()
    with engine.connect() as conn:
        df = pd.read_sql(
            text(
                "SELECT driver_id, driver_name, city, vehicle_type, vehicle_number, rating, "
                "joined_date, updated_at FROM raw.drivers WHERE source_file = :f ORDER BY row_num"
            ),
            conn, params={"f": source_file},
        )
    if df.empty:
        print("SKIP   drivers: no bronze rows found")
        return 0

    df = df.apply(clean_text)
    city = df["city"].map(lambda v: ref.CITY_LOOKUP.get(v.lower()) if isinstance(v, str) else None)
    vtype = df["vehicle_type"].map(lambda v: v.upper() if isinstance(v, str) else None)
    rating = pd.to_numeric(df["rating"], errors="coerce")
    joined = pd.to_datetime(df["joined_date"], format="%Y-%m-%d", errors="coerce")
    updated = pd.to_datetime(df["updated_at"], format="%Y-%m-%d %H:%M:%S", errors="coerce")

    problems = {
        "missing driver_id": int(df["driver_id"].isna().sum()),
        "duplicate driver_id": int(df["driver_id"].dropna().duplicated().sum()),
        "missing name": int(df["driver_name"].isna().sum()),
        "unknown city": int(city.isna().sum()),
        "invalid vehicle_type": int((~vtype.isin(ref.VALID_VEHICLE_TYPES)).sum()),
        "bad rating": int((rating.isna() | (rating < 0) | (rating > 5)).sum()),
        "bad joined_date": int(joined.isna().sum()),
        "bad updated_at": int(updated.isna().sum()),
    }
    problems = {k: v for k, v in problems.items() if v}
    if problems:
        log_validation(engine, source_file, {"rows_in": len(df)}, "FAILED", str(problems), t0)
        raise ValueError(f"Driver validation failed: {problems}")

    out = pd.DataFrame({
        "driver_id": df["driver_id"], "driver_name": df["driver_name"], "city": city,
        "vehicle_type": vtype, "vehicle_number": df["vehicle_number"],
        "rating": rating, "joined_date": joined.dt.date, "updated_at": updated,
    })
    cols = list(out.columns)
    rows = [tuple(_py(v) for v in r) for r in out.astype(object).itertuples(index=False, name=None)]
    sql = (
        f"INSERT INTO staging.drivers_clean ({', '.join(cols)}) VALUES %s "
        "ON CONFLICT (driver_id) DO UPDATE SET "
        + ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "driver_id")
        + ", loaded_at = now()"
    )
    conn = engine.raw_connection()
    try:
        with conn.cursor() as cur:
            execute_values(cur, sql, rows, page_size=2000)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    log_validation(
        engine, source_file,
        {"rows_in": len(df), "rows_clean": len(df), "rows_duplicate": 0,
         "rows_rejected": 0, "city_fixed": 0, "status_fixed": 0},
        "SUCCESS", None, t0,
    )
    return len(df)


def main() -> None:
    parser = argparse.ArgumentParser(description="HaulPulse silver step")
    parser.add_argument("--date", help="process only trips_<date>.csv, format YYYY-MM-DD")
    args = parser.parse_args()

    engine = get_engine()

    if args.date:
        files = [f"trips_{args.date}.csv"]
    else:
        n = process_drivers(engine)
        if n:
            print(f"OK     drivers.csv              {n:>6} drivers validated and upserted")
        with engine.connect() as conn:
            files = [r[0] for r in conn.execute(text("SELECT DISTINCT source_file FROM raw.trips ORDER BY 1"))]

    if not files:
        raise SystemExit("No bronze trips found. Run: python -m pipeline.load_bronze first.")

    failures = []
    for f in files:
        try:
            s = process_trips_file(engine, f)
            other = s["rows_rejected"] - s["rows_duplicate"]
            print(
                f"OK     {f:<24} in {s['rows_in']:>5} | clean {s['rows_clean']:>5} | "
                f"dup {s['rows_duplicate']:>3} | rejected {other:>3} | "
                f"city fixed {s['city_fixed']:>3} | status fixed {s['status_fixed']:>3} | {s['duration_ms']} ms"
            )
        except Exception as exc:
            failures.append(f)
            print(f"FAILED {f:<24} {str(exc).splitlines()[0]}")

    if failures:
        raise SystemExit(f"Failed files: {failures}")


if __name__ == "__main__":
    main()