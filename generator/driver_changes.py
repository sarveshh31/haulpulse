"""Simulate driver master-data changes (city transfer / vehicle upgrade) for SCD Type 2.

Usage: python -m generator.driver_changes --date 2026-10-23 --rate 0.03
Rewrites data/raw/drivers.csv: changed drivers get new attributes and updated_at = <date> 00:00:00.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from generator import config as cfg

RAW_DIR = Path("data/raw")
LETTERS = list("ABCDEFGHJKLMNPRSTUVWXYZ")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply driver master-data changes")
    parser.add_argument("--date", required=True, help="effective date, YYYY-MM-DD")
    parser.add_argument("--rate", type=float, default=0.03, help="fraction of drivers that change")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    effective = datetime.strptime(args.date, "%Y-%m-%d")
    stamp = effective.strftime("%Y-%m-%d 00:00:00")

    path = RAW_DIR / "drivers.csv"
    if not path.exists():
        raise SystemExit("data/raw/drivers.csv not found.")
    df = pd.read_csv(path, dtype=str)
    if "updated_at" not in df.columns:
        raise SystemExit("drivers.csv has no updated_at column. Regenerate with --regen-drivers.")
    if (df["updated_at"] >= stamp).any():
        raise SystemExit(f"Changes on or after {args.date} were already applied. Pick a later date.")

    rng = np.random.default_rng([args.seed, effective.toordinal(), 7])
    n = int(round(len(df) * args.rate))
    idx = rng.choice(len(df), size=n, replace=False)
    cities, vtypes = list(cfg.CITIES), list(cfg.VEHICLES)

    changes = []
    for i in idx:
        row = df.loc[i]
        kind = str(rng.choice(["city_transfer", "vehicle_upgrade", "both"], p=[0.5, 0.3, 0.2]))
        new_city, new_vt = row["city"], row["vehicle_type"]
        if kind in ("city_transfer", "both"):
            new_city = str(rng.choice([c for c in cities if c != row["city"]]))
        if kind in ("vehicle_upgrade", "both"):
            new_vt = str(rng.choice([v for v in vtypes if v != row["vehicle_type"]]))
        series = "".join(str(x) for x in rng.choice(LETTERS, size=2))
        new_number = f"{cfg.CITIES[new_city]['plate']}{series}{int(rng.integers(1000, 10000))}"

        changes.append({
            "driver_id": row["driver_id"], "kind": kind,
            "old": {"city": row["city"], "vehicle_type": row["vehicle_type"]},
            "new": {"city": new_city, "vehicle_type": new_vt},
        })
        df.loc[i, ["city", "vehicle_type", "vehicle_number", "updated_at"]] = [new_city, new_vt, new_number, stamp]

    df.to_csv(path, index=False)
    kinds = {k: sum(1 for c in changes if c["kind"] == k) for k in ("city_transfer", "vehicle_upgrade", "both")}
    manifest = {"effective_date": args.date, "drivers_changed": len(changes), "by_kind": kinds, "changes": changes}
    (RAW_DIR / f"driver_changes_{args.date}.json").write_text(json.dumps(manifest, indent=2))
    print(f"Applied {len(changes)} driver changes effective {args.date}: {kinds}")


if __name__ == "__main__":
    main()