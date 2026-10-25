"""Generate Porter-style delivery trip data, with deliberately dirty records.

Usage (from the project root):
    python -m generator.generate --date 2026-10-25 --rows 5000
    python -m generator.generate --start-date 2026-10-19 --days 7 --rows 5000
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

from generator import config as cfg

RAW_DIR = Path("data/raw")
TS_FMT = "%Y-%m-%d %H:%M:%S"

TRIP_COLUMNS = [
    "trip_id", "customer_id", "driver_id", "city", "vehicle_type",
    "pickup_lat", "pickup_lng", "drop_lat", "drop_lng",
    "distance_km", "eta_minutes",
    "requested_at", "pickup_at", "delivered_at",
    "status", "fare_amount", "payment_mode", "cancellation_reason", "updated_at",
]


# --------------------------------------------------------------------------
# Drivers (master data, generated once and reused)
# --------------------------------------------------------------------------
def generate_drivers(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    Faker.seed(seed)
    fake = Faker("en_IN")

    cities = list(cfg.CITIES)
    city_p = [cfg.CITIES[c]["weight"] for c in cities]
    vtypes = list(cfg.VEHICLES)
    v_p = [cfg.VEHICLES[v]["weight"] for v in vtypes]

    city_choice = rng.choice(cities, size=n, p=city_p)
    vehicle_choice = rng.choice(vtypes, size=n, p=v_p)
    letters = list("ABCDEFGHJKLMNPRSTUVWXYZ")

    rows = []
    for i in range(n):
        city = str(city_choice[i])
        series = "".join(str(x) for x in rng.choice(letters, size=2))
        number = int(rng.integers(1000, 10000))
        joined = date(2022, 1, 1) + timedelta(days=int(rng.integers(0, 1400)))
        rows.append({
            "driver_id": f"DRV-{i + 1:05d}",
            "driver_name": fake.name(),
            "city": city,
            "vehicle_type": str(vehicle_choice[i]),
            "vehicle_number": f"{cfg.CITIES[city]['plate']}{series}{number}",
            "rating": round(float(rng.uniform(3.2, 5.0)), 2),
            "joined_date": joined.isoformat(),
        })
    return pd.DataFrame(rows)


def load_or_create_drivers(n_drivers: int, seed: int, regen: bool) -> pd.DataFrame:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / "drivers.csv"
    if path.exists() and not regen:
        return pd.read_csv(path)
    drivers = generate_drivers(n_drivers, seed)
    drivers.to_csv(path, index=False)
    print(f"Wrote {len(drivers)} drivers -> {path}")
    return drivers


# --------------------------------------------------------------------------
# Clean trips for one day (fully deterministic for a given date + seed)
# --------------------------------------------------------------------------
def _fmt(ts: pd.Series) -> pd.Series:
    out = ts.dt.strftime(TS_FMT).astype(object)
    return out.where(ts.notna(), None)


def build_clean_trips(trip_date: date, n: int, drivers: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng([seed, trip_date.toordinal()])

    d = drivers.iloc[rng.integers(0, len(drivers), n)].reset_index(drop=True)
    vtype = d["vehicle_type"]
    city = d["city"]

    # --- request time, with realistic peaks ---
    hour_p = np.array(cfg.HOUR_WEIGHTS, dtype=float)
    hour_p /= hour_p.sum()
    hours = rng.choice(24, size=n, p=hour_p)
    secs = hours * 3600 + rng.integers(0, 3600, n)
    requested = pd.Series(pd.Timestamp(trip_date) + pd.to_timedelta(secs, unit="s"))

    # --- distance and coordinates ---
    lo = vtype.map({k: v["dist_km"][0] for k, v in cfg.VEHICLES.items()}).to_numpy(float)
    hi = vtype.map({k: v["dist_km"][1] for k, v in cfg.VEHICLES.items()}).to_numpy(float)
    distance = np.maximum(np.round(lo + (hi - lo) * rng.beta(2, 4, n), 2), 0.5)

    c_lat = city.map({k: v["lat"] for k, v in cfg.CITIES.items()}).to_numpy(float)
    c_lng = city.map({k: v["lng"] for k, v in cfg.CITIES.items()}).to_numpy(float)
    pickup_lat = c_lat + rng.normal(0, 0.05, n)
    pickup_lng = c_lng + rng.normal(0, 0.05, n)
    theta = rng.uniform(0, 2 * np.pi, n)
    straight_km = distance / 1.3  # road distance is longer than a straight line
    drop_lat = pickup_lat + straight_km * np.sin(theta) / 111.0
    drop_lng = pickup_lng + straight_km * np.cos(theta) / (111.0 * np.cos(np.radians(pickup_lat)))

    # --- status ---
    statuses = list(cfg.STATUS_WEIGHTS)
    status = rng.choice(statuses, size=n, p=list(cfg.STATUS_WEIGHTS.values()))
    completed = status == "COMPLETED"

    # --- timeline ---
    speed = vtype.map({k: v["speed_kmph"] for k, v in cfg.VEHICLES.items()}).to_numpy(float)
    wait_min = rng.integers(3, 26, n)
    drive_min = distance / speed * 60 * rng.uniform(0.8, 1.6, n) + rng.integers(5, 21, n)
    pickup_full = requested + pd.to_timedelta(wait_min, unit="m").to_numpy()
    delivered_full = pickup_full + pd.to_timedelta(drive_min, unit="m").to_numpy()
    eta_minutes = np.ceil(distance / speed * 60 * 1.25 + 15).astype(int)

    pickup_at = pickup_full.where(completed)
    delivered_at = delivered_full.where(completed)
    updated = (requested + pd.to_timedelta(wait_min, unit="m").to_numpy()).where(~completed, delivered_full)

    # --- fare ---
    base = vtype.map({k: v["base"] for k, v in cfg.VEHICLES.items()}).to_numpy(float)
    per_km = vtype.map({k: v["per_km"] for k, v in cfg.VEHICLES.items()}).to_numpy(float)
    surge = np.where(np.isin(hours, list(cfg.PEAK_HOURS)), cfg.PEAK_SURGE, 1.0)
    fare = np.round((base + per_km * distance) * surge * rng.uniform(0.95, 1.05, n), 2)
    fare = np.where(completed, fare, 0.0)

    # --- drivers, customers, reasons, payment ---
    driver_id = d["driver_id"].to_numpy(object).copy()
    driver_id[status == "NO_DRIVER_FOUND"] = None

    reasons = np.array([None] * n, dtype=object)
    for st, options in cfg.CANCEL_REASONS.items():
        mask = status == st
        if mask.any():
            reasons[mask] = rng.choice(options, size=int(mask.sum()))

    payment = rng.choice(list(cfg.PAYMENT_MODES), size=n, p=list(cfg.PAYMENT_MODES.values()))

    return pd.DataFrame({
        "trip_id": [f"TRP-{trip_date:%Y%m%d}-{i:06d}" for i in range(1, n + 1)],
        "customer_id": [f"CUST-{x:06d}" for x in rng.integers(1, 50001, n)],
        "driver_id": driver_id,
        "city": city.to_numpy(object),
        "vehicle_type": vtype.to_numpy(object),
        "pickup_lat": np.round(pickup_lat, 6),
        "pickup_lng": np.round(pickup_lng, 6),
        "drop_lat": np.round(drop_lat, 6),
        "drop_lng": np.round(drop_lng, 6),
        "distance_km": distance,
        "eta_minutes": eta_minutes,
        "requested_at": _fmt(requested),
        "pickup_at": _fmt(pickup_at),
        "delivered_at": _fmt(delivered_at),
        "status": status.astype(object),
        "fare_amount": fare,
        "payment_mode": payment.astype(object),
        "cancellation_reason": reasons,
        "updated_at": _fmt(updated),
    })[TRIP_COLUMNS]


# --------------------------------------------------------------------------
# Dirty data injection
# --------------------------------------------------------------------------
def inject_dirty(df: pd.DataFrame, dirty_rate: float, rng: np.random.Generator):
    df = df.copy()
    n = len(df)
    n_dirty = int(round(n * dirty_rate))
    used = np.zeros(n, dtype=bool)
    counts: dict[str, int] = {}

    completed = (df["status"] == "COMPLETED").to_numpy()
    has_driver = (df["status"] != "NO_DRIVER_FOUND").to_numpy()

    def pick(defect: str, pool: np.ndarray | None = None) -> np.ndarray:
        k = int(round(cfg.DIRTY_WEIGHTS[defect] * n_dirty))
        mask = ~used if pool is None else (~used & pool)
        candidates = np.flatnonzero(mask)
        k = min(k, len(candidates))
        chosen = rng.choice(candidates, size=k, replace=False)
        used[chosen] = True
        counts[defect] = int(k)
        return chosen

    # Fixable problems (Phase 4 will clean these, not reject them)
    idx = pick("city_variant")
    df.loc[idx, "city"] = [str(rng.choice(cfg.CITY_ALIASES[c])) for c in df.loc[idx, "city"]]

    idx = pick("status_case")
    df.loc[idx, "status"] = [s.lower() if rng.random() < 0.5 else s + " " for s in df.loc[idx, "status"]]

    # Problems that should be rejected (quarantined) in Phase 4
    idx = pick("negative_fare", completed)
    df.loc[idx, "fare_amount"] = -df.loc[idx, "fare_amount"].abs()

    idx = pick("delivered_before_pickup", completed)
    p = df.loc[idx, "pickup_at"].to_numpy().copy()
    dl = df.loc[idx, "delivered_at"].to_numpy().copy()
    df.loc[idx, "pickup_at"] = dl
    df.loc[idx, "delivered_at"] = p

    idx = pick("missing_driver", has_driver)
    df.loc[idx, "driver_id"] = None

    idx = pick("missing_fare", completed)
    df.loc[idx, "fare_amount"] = np.nan

    idx = pick("bad_status")
    df.loc[idx, "status"] = [str(rng.choice(["DONE", "delivered", "???", "COMPLETE_OK"])) for _ in idx]

    idx = pick("bad_distance", completed)
    df.loc[idx, "distance_km"] = [float(rng.choice([0.0, -5.0, 9999.0])) for _ in idx]

    idx = pick("gps_out_of_india")
    df.loc[idx, "pickup_lat"] = 0.0
    df.loc[idx, "pickup_lng"] = 0.0

    idx = pick("unparseable_timestamp")
    df.loc[idx, "requested_at"] = [str(rng.choice(["not_a_date", "31/02/2026 25:99", "yesterday"])) for _ in idx]

    idx = pick("missing_city")
    df.loc[idx, "city"] = None

    # Exact duplicates (added last, copied from any row)
    k = int(round(cfg.DIRTY_WEIGHTS["duplicate"] * n_dirty))
    k = min(k, n)
    dup_idx = rng.choice(n, size=k, replace=False)
    df = pd.concat([df, df.iloc[dup_idx]], ignore_index=True)
    counts["duplicate"] = int(k)

    return df, counts


# --------------------------------------------------------------------------
# Late-arriving updates: yesterday's trips re-sent today with a corrected fare
# --------------------------------------------------------------------------
def build_late_updates(trip_date: date, n_rows: int, drivers: pd.DataFrame,
                       seed: int, late_rate: float, rng: np.random.Generator) -> pd.DataFrame:
    m = int(round(n_rows * late_rate))
    if m == 0:
        return pd.DataFrame(columns=TRIP_COLUMNS)

    prev_day = trip_date - timedelta(days=1)
    prev = build_clean_trips(prev_day, n_rows, drivers, seed)
    prev = prev[prev["status"] == "COMPLETED"]
    sample = prev.sample(n=min(m, len(prev)), random_state=int(rng.integers(0, 2**31 - 1))).copy()

    sample["fare_amount"] = (sample["fare_amount"] * rng.uniform(1.03, 1.15, len(sample))).round(2)
    midnight = datetime.combine(trip_date, time(0, 0))
    sample["updated_at"] = [
        (midnight + timedelta(seconds=int(s))).strftime(TS_FMT)
        for s in rng.integers(1200, 14400, len(sample))
    ]
    return sample


# --------------------------------------------------------------------------
# One day end to end
# --------------------------------------------------------------------------
def generate_day(trip_date: date, n_rows: int, dirty_rate: float, late_rate: float,
                 seed: int, drivers: pd.DataFrame) -> dict:
    rng = np.random.default_rng([seed, trip_date.toordinal(), 1])

    clean = build_clean_trips(trip_date, n_rows, drivers, seed)
    dirty, counts = inject_dirty(clean, dirty_rate, rng)
    late = build_late_updates(trip_date, n_rows, drivers, seed, late_rate, rng)

    out = pd.concat([dirty, late], ignore_index=True)
    out = out.sample(frac=1, random_state=int(rng.integers(0, 2**31 - 1))).reset_index(drop=True)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RAW_DIR / f"trips_{trip_date:%Y-%m-%d}.csv"
    out.to_csv(csv_path, index=False)

    manifest = {
        "trip_date": trip_date.isoformat(),
        "file": csv_path.name,
        "base_rows": n_rows,
        "late_update_rows": int(len(late)),
        "total_rows_in_file": int(len(out)),
        "dirty_rate_requested": dirty_rate,
        "injected_defects": counts,
        "injected_defect_total": int(sum(counts.values())),
        "seed": seed,
    }
    (RAW_DIR / f"manifest_{trip_date:%Y-%m-%d}.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> None:
    parser = argparse.ArgumentParser(description="HaulPulse trip data generator")
    parser.add_argument("--date", type=_parse_date, help="single day, YYYY-MM-DD")
    parser.add_argument("--start-date", type=_parse_date, help="first day of a range")
    parser.add_argument("--days", type=int, default=1, help="number of days from start-date")
    parser.add_argument("--rows", type=int, default=5000, help="base trips per day")
    parser.add_argument("--drivers", type=int, default=2000, help="size of driver master")
    parser.add_argument("--dirty-rate", type=float, default=0.07, help="fraction of rows made dirty")
    parser.add_argument("--late-rate", type=float, default=0.01, help="fraction of late-arriving updates")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--regen-drivers", action="store_true", help="rebuild drivers.csv")
    args = parser.parse_args()

    start = args.start_date or args.date or date.today()
    drivers = load_or_create_drivers(args.drivers, args.seed, args.regen_drivers)

    for offset in range(args.days):
        day = start + timedelta(days=offset)
        m = generate_day(day, args.rows, args.dirty_rate, args.late_rate, args.seed, drivers)
        print(f"{m['trip_date']}: {m['total_rows_in_file']} rows "
              f"({m['injected_defect_total']} injected defects, {m['late_update_rows']} late updates) "
              f"-> data/raw/{m['file']}")


if __name__ == "__main__":
    main()