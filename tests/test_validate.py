"""Unit tests for the validation rules (pipeline/validate.py)."""
import pandas as pd
import pytest

from pipeline.validate import DUPLICATE_REASON, REASON_ORDER, validate_trips
from tests.helpers import frame, make_row


def single_reasons(**overrides) -> list:
    result = validate_trips(frame(make_row(**overrides)))
    assert len(result.rejected) == 1, "expected exactly one rejected row"
    return result.rejected[0]["reasons"]


# ---------- happy path and auto-corrections ----------

def test_clean_row_passes():
    result = validate_trips(frame(make_row()))
    assert result.stats["rows_clean"] == 1
    assert result.rejected == []
    row = result.clean.iloc[0]
    assert row["city"] == "Bengaluru"
    assert float(row["fare_amount"]) == 120.5


def test_clean_output_is_typed():
    clean = validate_trips(frame(make_row())).clean
    assert pd.api.types.is_datetime64_any_dtype(clean["requested_at"])
    assert pd.api.types.is_float_dtype(clean["fare_amount"])
    assert str(clean["eta_minutes"].dtype) == "Int64"


@pytest.mark.parametrize("raw_city", ["Bangalore", "BLR ", "bengaluru", "BENGALURU", "Bengalore"])
def test_city_variants_are_fixed_not_rejected(raw_city):
    result = validate_trips(frame(make_row(city=raw_city)))
    assert result.stats["rows_rejected"] == 0
    assert result.clean.iloc[0]["city"] == "Bengaluru"
    assert result.stats["city_fixed"] == 1


def test_canonical_city_is_not_counted_as_fixed():
    assert validate_trips(frame(make_row())).stats["city_fixed"] == 0


@pytest.mark.parametrize("raw_status", ["completed", "COMPLETED ", " Completed"])
def test_status_case_is_fixed_not_rejected(raw_status):
    result = validate_trips(frame(make_row(status=raw_status)))
    assert result.stats["rows_rejected"] == 0
    assert result.clean.iloc[0]["status"] == "COMPLETED"
    assert result.stats["status_fixed"] == 1


def test_lowercase_vehicle_type_is_accepted():
    result = validate_trips(frame(make_row(vehicle_type="two_wheeler")))
    assert result.stats["rows_rejected"] == 0
    assert result.clean.iloc[0]["vehicle_type"] == "TWO_WHEELER"


# ---------- rejection rules ----------

@pytest.mark.parametrize("bad_status", ["DONE", "???", "delivered", "COMPLETE_OK"])
def test_invalid_status_rejected(bad_status):
    assert single_reasons(status=bad_status) == ["INVALID_STATUS"]


def test_negative_fare_rejected():
    assert single_reasons(fare_amount="-50") == ["NEGATIVE_FARE"]


def test_missing_fare_on_completed_trip_rejected():
    assert single_reasons(fare_amount=None) == ["MISSING_FARE"]


def test_missing_fare_on_cancelled_trip_becomes_zero():
    row = make_row(status="CANCELLED_BY_CUSTOMER", fare_amount=None, pickup_at=None,
                   delivered_at=None, cancellation_reason="Booked by mistake")
    result = validate_trips(frame(row))
    assert result.stats["rows_rejected"] == 0
    assert float(result.clean.iloc[0]["fare_amount"]) == 0.0


def test_no_driver_found_trip_may_have_no_driver():
    row = make_row(status="NO_DRIVER_FOUND", driver_id=None, pickup_at=None, delivered_at=None,
                   fare_amount="0.0", cancellation_reason="No driver available nearby")
    result = validate_trips(frame(row))
    assert result.rejected == []
    assert pd.isna(result.clean.iloc[0]["driver_id"])


def test_completed_trip_without_driver_rejected():
    assert single_reasons(driver_id=None) == ["MISSING_DRIVER"]


def test_delivered_before_pickup_rejected():
    reasons = single_reasons(pickup_at="2026-10-25 10:40:00", delivered_at="2026-10-25 10:10:00")
    assert reasons == ["DELIVERED_BEFORE_PICKUP"]


def test_completed_trip_missing_delivery_time_rejected():
    assert single_reasons(delivered_at=None) == ["MISSING_DELIVERY_TIMES"]


@pytest.mark.parametrize("value", ["0", "-5", "9999"])
def test_bad_distance_rejected(value):
    assert single_reasons(distance_km=value) == ["BAD_DISTANCE"]


def test_non_numeric_distance_rejected():
    assert single_reasons(distance_km="abc") == ["INVALID_NUMERIC_FIELD"]


def test_gps_outside_india_rejected():
    assert single_reasons(pickup_lat="0.0", pickup_lng="0.0") == ["GPS_OUT_OF_INDIA"]


@pytest.mark.parametrize("value", ["not_a_date", "31/02/2026 25:99", "yesterday"])
def test_unparseable_requested_at_rejected(value):
    assert single_reasons(requested_at=value) == ["UNPARSEABLE_TIMESTAMP"]


@pytest.mark.parametrize("city, expected", [
    ("Atlantis", "UNKNOWN_CITY"),
    (None, "MISSING_CITY"),
    ("   ", "MISSING_CITY"),
])
def test_unknown_and_missing_city_rejected(city, expected):
    assert single_reasons(city=city) == [expected]


def test_missing_trip_id_rejected():
    assert single_reasons(trip_id="   ") == ["MISSING_TRIP_ID"]


def test_invalid_vehicle_type_rejected():
    assert single_reasons(vehicle_type="HELICOPTER") == ["INVALID_VEHICLE_TYPE"]


# ---------- duplicates ----------

def test_duplicate_in_same_file_keeps_first_and_rejects_rest():
    result = validate_trips(frame(make_row(), make_row()))
    assert result.stats["rows_clean"] == 1
    assert result.stats["rows_duplicate"] == 1
    assert result.rejected[0]["reasons"] == [DUPLICATE_REASON]
    assert result.rejected[0]["row_num"] == 2


def test_same_trip_id_in_different_files_is_not_a_duplicate():
    first = make_row(source_file="trips_2026-10-25.csv")
    later = make_row(source_file="trips_2026-10-26.csv", updated_at="2026-10-26 02:00:00",
                     fare_amount="130.00")
    result = validate_trips(frame(first, later))
    assert result.stats["rows_duplicate"] == 0
    assert result.stats["rows_clean"] == 2


def test_duplicate_of_a_bad_row_reports_only_the_duplicate():
    bad = make_row(fare_amount="-1")
    result = validate_trips(frame(bad, dict(bad)))
    reason_lists = [r["reasons"] for r in result.rejected]
    assert ["NEGATIVE_FARE"] in reason_lists
    assert [DUPLICATE_REASON] in reason_lists


# ---------- reporting and bookkeeping ----------

def test_row_with_several_problems_records_all_reasons_in_rule_order():
    assert single_reasons(fare_amount="-10", distance_km="0") == ["NEGATIVE_FARE", "BAD_DISTANCE"]


def test_rejected_row_keeps_original_raw_values():
    result = validate_trips(frame(make_row(city=" BLR ", fare_amount="-12.5")))
    payload = result.rejected[0]["payload"]
    assert payload["city"] == " BLR "
    assert payload["fare_amount"] == "-12.5"
    assert payload["cancellation_reason"] is None


def test_row_accounting_always_balances():
    rows = [
        make_row(trip_id="T1"),
        make_row(trip_id="T2", fare_amount="-1"),
        make_row(trip_id="T3", city="Atlantis"),
        make_row(trip_id="T1"),  # duplicate of the first row
        make_row(trip_id="T5", status="DONE"),
    ]
    result = validate_trips(frame(*rows))
    s = result.stats
    assert s["rows_in"] == 5
    assert s["rows_clean"] + s["rows_rejected"] == s["rows_in"]
    assert len(result.clean) == s["rows_clean"]
    assert len(result.rejected) == s["rows_rejected"]
    assert s["rows_clean"] == 1


def test_reason_counts_cover_every_rule():
    result = validate_trips(frame(make_row()))
    assert set(result.stats["reason_counts"]) == set(REASON_ORDER) | {DUPLICATE_REASON}