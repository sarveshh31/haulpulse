"""Tests for the data generator and the generator/validator contract."""
from datetime import date, timedelta

import numpy as np
import pandas.testing as pdt

from generator import config as cfg
from generator.generate import (
    TRIP_COLUMNS,
    build_clean_trips,
    build_late_updates,
    generate_drivers,
    inject_dirty,
)
from pipeline.validate import validate_trips
from tests.helpers import to_bronze

DAY = date(2026, 10, 25)

# validator reason code -> generator defect name
EXPECTED = {
    "DUPLICATE_IN_FILE": "duplicate",
    "NEGATIVE_FARE": "negative_fare",
    "DELIVERED_BEFORE_PICKUP": "delivered_before_pickup",
    "MISSING_DRIVER": "missing_driver",
    "MISSING_FARE": "missing_fare",
    "INVALID_STATUS": "bad_status",
    "BAD_DISTANCE": "bad_distance",
    "GPS_OUT_OF_INDIA": "gps_out_of_india",
    "UNPARSEABLE_TIMESTAMP": "unparseable_timestamp",
    "MISSING_CITY": "missing_city",
}


def drivers():
    return generate_drivers(60, seed=42)


def test_generation_is_deterministic():
    d = drivers()
    a = build_clean_trips(DAY, 300, d, seed=42)
    b = build_clean_trips(DAY, 300, d, seed=42)
    pdt.assert_frame_equal(a, b)


def test_different_seed_changes_output():
    d = drivers()
    a = build_clean_trips(DAY, 300, d, seed=1)
    b = build_clean_trips(DAY, 300, d, seed=2)
    assert not a["fare_amount"].equals(b["fare_amount"])


def test_trip_columns_and_ids():
    df = build_clean_trips(DAY, 300, drivers(), seed=42)
    assert list(df.columns) == TRIP_COLUMNS
    assert df["trip_id"].is_unique
    assert df["trip_id"].str.startswith("TRP-20261025-").all()


def test_clean_generator_output_passes_the_validator():
    """Contract test: whatever the generator calls clean must satisfy every pipeline rule."""
    df = build_clean_trips(DAY, 500, drivers(), seed=42)
    result = validate_trips(to_bronze(df))
    assert result.rejected == []
    assert result.stats["rows_clean"] == 500


def test_inject_dirty_adds_exactly_the_requested_duplicates():
    clean = build_clean_trips(DAY, 1000, drivers(), seed=42)
    dirty, counts = inject_dirty(clean, 0.07, np.random.default_rng(7))
    assert len(dirty) == 1000 + counts["duplicate"]
    assert set(counts) == set(cfg.DIRTY_WEIGHTS)
    assert 65 <= sum(counts.values()) <= 75  # about 7% of 1000


def test_validator_catches_every_injected_defect():
    """Unit-test version of pipeline.reconcile: detected counts must equal injected counts."""
    clean = build_clean_trips(DAY, 2000, drivers(), seed=42)
    dirty, counts = inject_dirty(clean, 0.07, np.random.default_rng(7))
    result = validate_trips(to_bronze(dirty))
    reason_counts = result.stats["reason_counts"]

    for reason, defect in EXPECTED.items():
        assert reason_counts[reason] == counts[defect], f"{reason} vs {defect}"
    assert result.stats["city_fixed"] == counts["city_variant"]
    assert result.stats["status_fixed"] == counts["status_case"]
    assert result.stats["rows_rejected"] == sum(counts[d] for d in EXPECTED.values())


def test_late_updates_reference_previous_day_with_higher_fare():
    d = drivers()
    late = build_late_updates(DAY, 500, d, seed=42, late_rate=0.02, rng=np.random.default_rng(3))
    prev = build_clean_trips(DAY - timedelta(days=1), 500, d, seed=42)

    assert len(late) == 10
    assert late["trip_id"].str.startswith("TRP-20261024-").all()

    merged = late.merge(prev, on="trip_id", suffixes=("_late", "_orig"))
    assert len(merged) == len(late)
    assert (merged["fare_amount_late"] > merged["fare_amount_orig"]).all()
    assert merged["updated_at_late"].str.startswith("2026-10-25").all()
    assert (merged["updated_at_late"] > merged["updated_at_orig"]).all()