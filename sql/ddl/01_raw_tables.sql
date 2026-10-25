-- Bronze layer: data exactly as received. Everything is TEXT on purpose.

CREATE TABLE IF NOT EXISTS raw.drivers (
    raw_id          BIGSERIAL PRIMARY KEY,
    source_file     TEXT        NOT NULL,
    row_num         INTEGER     NOT NULL,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    driver_id       TEXT,
    driver_name     TEXT,
    city            TEXT,
    vehicle_type    TEXT,
    vehicle_number  TEXT,
    rating          TEXT,
    joined_date     TEXT
);

CREATE INDEX IF NOT EXISTS idx_raw_drivers_source_file ON raw.drivers (source_file);

CREATE TABLE IF NOT EXISTS raw.trips (
    raw_id               BIGSERIAL PRIMARY KEY,
    source_file          TEXT        NOT NULL,
    row_num              INTEGER     NOT NULL,
    ingested_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    trip_id              TEXT,
    customer_id          TEXT,
    driver_id            TEXT,
    city                 TEXT,
    vehicle_type         TEXT,
    pickup_lat           TEXT,
    pickup_lng           TEXT,
    drop_lat             TEXT,
    drop_lng             TEXT,
    distance_km          TEXT,
    eta_minutes          TEXT,
    requested_at         TEXT,
    pickup_at            TEXT,
    delivered_at         TEXT,
    status               TEXT,
    fare_amount          TEXT,
    payment_mode         TEXT,
    cancellation_reason  TEXT,
    updated_at           TEXT
);

CREATE INDEX IF NOT EXISTS idx_raw_trips_source_file ON raw.trips (source_file);
CREATE INDEX IF NOT EXISTS idx_raw_trips_trip_id     ON raw.trips (trip_id);