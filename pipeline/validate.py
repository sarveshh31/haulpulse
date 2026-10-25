"""Pure validation + cleaning logic for trip records (no database access).

Input : DataFrame of bronze rows (all text) with columns
        raw_id, source_file, row_num + RAW_TRIP_COLUMNS
Output: ValidationResult(clean DataFrame, rejected list, stats dict)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from pipeline import reference as ref

TS_FMT = "%Y-%m-%d %H:%M:%S"

RAW_TRIP_COLUMNS = [
    "trip_id", "customer_id", "driver_id", "city", "vehicle_type",
    "pickup_lat", "pickup_lng", "drop_lat", "drop_lng",
    "distance_km", "eta_minutes",
    "requested_at", "pickup_at", "delivered_at",
    "status", "fare_amount", "payment_mode", "cancellation_reason", "updated_at",
]

# The first failing rule in this order becomes the primary reason.
REASON_ORDER = [
    "MISSING_TRIP_ID",
    "MISSING_CUSTOMER_ID",
    "MISSING_CITY",
    "UNKNOWN_CITY",
    "INVALID_VEHICLE_TYPE",
    "INVALID_STATUS",
    "MISSING_DRIVER",
    "UNPARSEABLE_TIMESTAMP",
    "INVALID_NUMERIC_FIELD",
    "MISSING_FARE",
    "NEGATIVE_FARE",
    "BAD_DISTANCE",
    "GPS_OUT_OF_INDIA",
    "MISSING_DELIVERY_TIMES",
    "DELIVERED_BEFORE_PICKUP",
]
DUPLICATE_REASON = "DUPLICATE_IN_FILE"


def _norm(v):
    """Strip whitespace; blank or null becomes None."""
    if v is None:
        return None
    if isinstance(v, float) and v != v:
        return None
    v = str(v).strip()
    return v or None


def _upper(v):
    return v.upper() if isinstance(v, str) else None


def clean_text(s: pd.Series) -> pd.Series:
    return s.map(_norm)


def _none(v):
    if v is None or (isinstance(v, float) and v != v):
        return None
    return v


@dataclass
class ValidationResult:
    clean: pd.DataFrame
    rejected: list
    stats: dict


def validate_trips(raw: pd.DataFrame) -> ValidationResult:
    orig = raw.sort_values(["source_file", "row_num"]).reset_index(drop=True)
    df = orig.copy()
    for c in RAW_TRIP_COLUMNS:
        df[c] = clean_text(df[c])
    n = len(df)

    # ---- 1. exact duplicates inside the same file: keep the first, reject the rest ----
    dup = (df["trip_id"].notna() & df.duplicated(subset=["source_file", "trip_id"], keep="first")).to_numpy()
    active = ~dup

    # ---- 2. normalise fixable fields ----
    city_norm = df["city"].map(lambda v: ref.CITY_LOOKUP.get(v.lower()) if isinstance(v, str) else None)
    missing_city = df["city"].isna().to_numpy()
    unknown_city = (~missing_city) & city_norm.isna().to_numpy()
    city_fixed = city_norm.notna().to_numpy() & (city_norm.to_numpy(object) != orig["city"].to_numpy(object))

    status_norm = df["status"].map(_upper)
    valid_status = status_norm.isin(ref.VALID_STATUSES).to_numpy()
    status_fixed = valid_status & (status_norm.to_numpy(object) != orig["status"].to_numpy(object))
    completed = (status_norm == "COMPLETED").to_numpy()
    no_driver_status = (status_norm == "NO_DRIVER_FOUND").to_numpy()

    vt_norm = df["vehicle_type"].map(_upper)
    invalid_vehicle = ~vt_norm.isin(ref.VALID_VEHICLE_TYPES).to_numpy()
    pay_norm = df["payment_mode"].map(_upper)

    # ---- 3. parse types ----
    def ts(col):
        return pd.to_datetime(df[col], format=TS_FMT, errors="coerce")

    req, pick, deliv, upd = ts("requested_at"), ts("pickup_at"), ts("delivered_at"), ts("updated_at")

    def num(col):
        return pd.to_numeric(df[col], errors="coerce")

    fare, dist = num("fare_amount"), num("distance_km")
    plat, plng, dlat, dlng = num("pickup_lat"), num("pickup_lng"), num("drop_lat"), num("drop_lng")
    eta = num("eta_minutes")

    # ---- 4. rules ----
    unparseable = (
        req.isna().to_numpy()
        | upd.isna().to_numpy()
        | (df["pickup_at"].notna() & pick.isna()).to_numpy()
        | (df["delivered_at"].notna() & deliv.isna()).to_numpy()
    )

    numeric_cols = {
        "fare_amount": fare, "distance_km": dist, "eta_minutes": eta,
        "pickup_lat": plat, "pickup_lng": plng, "drop_lat": dlat, "drop_lng": dlng,
    }
    invalid_numeric = np.zeros(n, dtype=bool)
    for col, parsed in numeric_cols.items():
        invalid_numeric |= (df[col].notna() & parsed.isna()).to_numpy()
    for parsed in (dist, plat, plng, dlat, dlng):
        invalid_numeric |= parsed.isna().to_numpy()

    missing_driver = df["driver_id"].isna().to_numpy() & valid_status & ~no_driver_status
    missing_fare = completed & df["fare_amount"].isna().to_numpy()
    negative_fare = (fare < 0).to_numpy()
    bad_distance = ((dist <= 0) | (dist > ref.MAX_DISTANCE_KM)).to_numpy()

    coords_present = (plat.notna() & plng.notna() & dlat.notna() & dlng.notna()).to_numpy()
    in_india = (
        plat.between(*ref.INDIA_LAT) & dlat.between(*ref.INDIA_LAT)
        & plng.between(*ref.INDIA_LNG) & dlng.between(*ref.INDIA_LNG)
    ).to_numpy()
    gps_bad = coords_present & ~in_india

    missing_times = completed & (df["pickup_at"].isna() | df["delivered_at"].isna()).to_numpy()
    delivered_before_pickup = (
        completed & pick.notna().to_numpy() & deliv.notna().to_numpy() & (deliv < pick).to_numpy()
    )

    masks = {
        "MISSING_TRIP_ID": df["trip_id"].isna().to_numpy(),
        "MISSING_CUSTOMER_ID": df["customer_id"].isna().to_numpy(),
        "MISSING_CITY": missing_city,
        "UNKNOWN_CITY": unknown_city,
        "INVALID_VEHICLE_TYPE": invalid_vehicle,
        "INVALID_STATUS": ~valid_status,
        "MISSING_DRIVER": missing_driver,
        "UNPARSEABLE_TIMESTAMP": unparseable,
        "INVALID_NUMERIC_FIELD": invalid_numeric,
        "MISSING_FARE": missing_fare,
        "NEGATIVE_FARE": negative_fare,
        "BAD_DISTANCE": bad_distance,
        "GPS_OUT_OF_INDIA": gps_bad,
        "MISSING_DELIVERY_TIMES": missing_times,
        "DELIVERED_BEFORE_PICKUP": delivered_before_pickup,
    }

    matrix = np.column_stack([masks[r] & active for r in REASON_ORDER]) if n else np.zeros((0, len(REASON_ORDER)), bool)
    fail = matrix.any(axis=1)
    reject_mask = dup | fail
    good = ~reject_mask

    # ---- 5. rejected rows, with every reason and the original raw values ----
    src = orig["source_file"].to_numpy(object)
    rown = orig["row_num"].to_numpy()
    tid = df["trip_id"].to_numpy(object)
    raw_vals = orig[RAW_TRIP_COLUMNS].to_numpy(object)

    rejected = []
    for i in np.flatnonzero(reject_mask):
        if dup[i]:
            reasons = [DUPLICATE_REASON]
        else:
            reasons = [REASON_ORDER[j] for j in np.flatnonzero(matrix[i])]
        rejected.append({
            "source_file": src[i],
            "row_num": int(rown[i]),
            "trip_id": tid[i],
            "reasons": reasons,
            "payload": {c: _none(v) for c, v in zip(RAW_TRIP_COLUMNS, raw_vals[i])},
        })

    # ---- 6. clean, typed rows ----
    fare_filled = fare.where(~(fare.isna().to_numpy() & ~completed), 0.0)  # cancelled trips: no charge
    clean = pd.DataFrame({
        "trip_id": df["trip_id"],
        "customer_id": df["customer_id"],
        "driver_id": df["driver_id"],
        "city": city_norm,
        "vehicle_type": vt_norm,
        "pickup_lat": plat,
        "pickup_lng": plng,
        "drop_lat": dlat,
        "drop_lng": dlng,
        "distance_km": dist,
        "eta_minutes": eta.round().astype("Int64"),
        "requested_at": req,
        "pickup_at": pick,
        "delivered_at": deliv,
        "status": status_norm,
        "fare_amount": fare_filled,
        "payment_mode": pay_norm,
        "cancellation_reason": df["cancellation_reason"],
        "updated_at": upd,
        "source_file": orig["source_file"],
        "source_row_num": orig["row_num"],
    })[good].reset_index(drop=True)

    # ---- 7. stats + invariant ----
    reason_counts = {DUPLICATE_REASON: int(dup.sum())}
    for r in REASON_ORDER:
        reason_counts[r] = int((masks[r] & active).sum())

    stats = {
        "rows_in": n,
        "rows_clean": int(good.sum()),
        "rows_duplicate": int(dup.sum()),
        "rows_rejected": int(reject_mask.sum()),
        "city_fixed": int((city_fixed & active).sum()),
        "status_fixed": int((status_fixed & active).sum()),
        "reason_counts": reason_counts,
    }
    if stats["rows_clean"] + stats["rows_rejected"] != n or len(clean) != stats["rows_clean"]:
        raise AssertionError(f"Row accounting broken: {stats}")

    return ValidationResult(clean=clean, rejected=rejected, stats=stats)