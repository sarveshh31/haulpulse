"""Shared helpers for building bronze-style rows in tests."""
from __future__ import annotations

import pandas as pd

from pipeline.validate import RAW_TRIP_COLUMNS

BASE_ROW = {
    "trip_id": "TRP-20261025-000001",
    "customer_id": "CUST-000001",
    "driver_id": "DRV-00001",
    "city": "Bengaluru",
    "vehicle_type": "TWO_WHEELER",
    "pickup_lat": "12.97",
    "pickup_lng": "77.59",
    "drop_lat": "12.99",
    "drop_lng": "77.61",
    "distance_km": "5.2",
    "eta_minutes": "40",
    "requested_at": "2026-10-25 10:00:00",
    "pickup_at": "2026-10-25 10:10:00",
    "delivered_at": "2026-10-25 10:40:00",
    "status": "COMPLETED",
    "fare_amount": "120.50",
    "payment_mode": "UPI",
    "cancellation_reason": None,
    "updated_at": "2026-10-25 10:40:00",
}


def make_row(**overrides) -> dict:
    """One valid bronze trip row (all text), with optional overrides."""
    row = {"source_file": "trips_2026-10-25.csv", **BASE_ROW}
    row.update(overrides)
    return row


def frame(*rows: dict) -> pd.DataFrame:
    """Bronze-style DataFrame from row dicts, with sequential raw_id / row_num."""
    df = pd.DataFrame(list(rows))
    df["row_num"] = range(1, len(df) + 1)
    df["raw_id"] = range(1, len(df) + 1)
    return df


def to_bronze(df: pd.DataFrame, source_file: str = "trips_2026-10-25.csv") -> pd.DataFrame:
    """Convert generator output into what the bronze table holds: text or NULL."""
    bronze = df.reset_index(drop=True).copy()
    for col in RAW_TRIP_COLUMNS:
        bronze[col] = bronze[col].map(lambda v: None if pd.isna(v) else str(v))
    bronze["source_file"] = source_file
    bronze["row_num"] = range(1, len(bronze) + 1)
    bronze["raw_id"] = range(1, len(bronze) + 1)
    return bronze