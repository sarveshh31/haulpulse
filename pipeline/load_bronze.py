"""Bronze load: copy raw CSV files into raw.* tables exactly as received.

Usage (from project root):
    python -m pipeline.load_bronze                  # drivers + every trips file
    python -m pipeline.load_bronze --date 2026-10-25  # one day only
"""
from __future__ import annotations

import argparse
import csv
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from pipeline.db import get_engine

RAW_DIR = Path("data/raw")

TABLES = {
    "trips": {
        "target": "raw.trips",
        "columns": [
            "trip_id", "customer_id", "driver_id", "city", "vehicle_type",
            "pickup_lat", "pickup_lng", "drop_lat", "drop_lng",
            "distance_km", "eta_minutes",
            "requested_at", "pickup_at", "delivered_at",
            "status", "fare_amount", "payment_mode", "cancellation_reason", "updated_at",
        ],
    },
    "drivers": {
        "target": "raw.drivers",
        "columns": [
            "driver_id", "driver_name", "city", "vehicle_type",
            "vehicle_number", "rating", "joined_date",
        ],
    },
}


def count_data_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as f:
        return sum(1 for _ in csv.reader(f)) - 1  # minus header


def check_header(path: Path, expected: list[str]) -> None:
    with path.open("r", encoding="utf-8", newline="") as f:
        header = next(csv.reader(f), [])
    if header != expected:
        raise ValueError(
            f"Header mismatch in {path.name}.\n  expected: {expected}\n  found:    {header}"
        )


def log_load(engine, source_file, target, rows_in_file, rows_loaded,
             status, error, started, t0) -> int:
    duration_ms = int((time.perf_counter() - t0) * 1000)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO ops.file_load_log
                    (source_file, target_table, rows_in_file, rows_loaded,
                     status, error_message, started_at, finished_at, duration_ms)
                VALUES (:f, :t, :rin, :rl, :s, :e, :st, now(), :d)
                """
            ),
            {
                "f": source_file, "t": target, "rin": rows_in_file, "rl": rows_loaded,
                "s": status, "e": (error or "")[:500] or None, "st": started, "d": duration_ms,
            },
        )
    return duration_ms


def load_file(engine, path: Path, kind: str) -> tuple[int, int]:
    """Load one CSV into its raw table. Returns (rows_loaded, duration_ms)."""
    spec = TABLES[kind]
    target, cols = spec["target"], spec["columns"]
    col_list = ", ".join(cols)

    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    rows_in_file = None
    rows_loaded = None

    raw = engine.raw_connection()
    try:
        check_header(path, cols)
        rows_in_file = count_data_rows(path)

        with raw.cursor() as cur:
            # Temp staging table keeps file order via row_num, dropped at commit
            cols_ddl = ", ".join(f"{c} TEXT" for c in cols)
            cur.execute(f"CREATE TEMP TABLE _stg_load (row_num BIGSERIAL, {cols_ddl}) ON COMMIT DROP")

            with path.open("r", encoding="utf-8", newline="") as f:
                cur.copy_expert(
                    f"COPY _stg_load ({col_list}) FROM STDIN WITH (FORMAT csv, HEADER true)", f
                )

            # Idempotency: replace this file's rows in one transaction
            cur.execute(f"DELETE FROM {target} WHERE source_file = %s", (path.name,))
            cur.execute(
                f"INSERT INTO {target} (source_file, row_num, {col_list}) "
                f"SELECT %s, row_num, {col_list} FROM _stg_load ORDER BY row_num",
                (path.name,),
            )
            rows_loaded = cur.rowcount

            if rows_loaded != rows_in_file:
                raise RuntimeError(
                    f"Reconciliation failed for {path.name}: file has {rows_in_file} rows, "
                    f"loaded {rows_loaded}"
                )
        raw.commit()
    except Exception as exc:
        raw.rollback()
        log_load(engine, path.name, target, rows_in_file, None, "FAILED", str(exc), started, t0)
        raise
    finally:
        raw.close()

    duration_ms = log_load(engine, path.name, target, rows_in_file, rows_loaded,
                           "SUCCESS", None, started, t0)
    return rows_loaded, duration_ms


def main() -> None:
    parser = argparse.ArgumentParser(description="HaulPulse bronze loader")
    parser.add_argument("--date", help="load only trips_<date>.csv, format YYYY-MM-DD")
    args = parser.parse_args()

    if args.date:
        jobs = [("trips", RAW_DIR / f"trips_{args.date}.csv")]
    else:
        jobs = []
        drivers = RAW_DIR / "drivers.csv"
        if drivers.exists():
            jobs.append(("drivers", drivers))
        jobs += [("trips", p) for p in sorted(RAW_DIR.glob("trips_*.csv"))]

    if not jobs:
        raise SystemExit("No files to load. Run: python -m generator.generate first.")

    engine = get_engine()
    failures = []
    total_rows = 0
    for kind, path in jobs:
        try:
            rows, ms = load_file(engine, path, kind)
            total_rows += rows
            rate = int(rows / (ms / 1000)) if ms else rows
            print(f"OK     {path.name:<24} {rows:>7} rows  {ms:>6} ms  (~{rate} rows/sec)")
        except Exception as exc:
            failures.append(path.name)
            print(f"FAILED {path.name:<24} {str(exc).splitlines()[0]}")

    print(f"\nLoaded {total_rows} rows from {len(jobs) - len(failures)}/{len(jobs)} files.")
    if failures:
        raise SystemExit(f"Failed files: {failures}")


if __name__ == "__main__":
    main()