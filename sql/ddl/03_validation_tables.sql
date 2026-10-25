-- Silver layer: validated, typed, de-duplicated data

CREATE TABLE IF NOT EXISTS staging.drivers_clean (
    driver_id       TEXT PRIMARY KEY,
    driver_name     TEXT        NOT NULL,
    city            TEXT        NOT NULL,
    vehicle_type    TEXT        NOT NULL,
    vehicle_number  TEXT,
    rating          NUMERIC(3,2),
    joined_date     DATE,
    loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.trips_clean (
    trip_id              TEXT PRIMARY KEY,
    customer_id          TEXT          NOT NULL,
    driver_id            TEXT,
    city                 TEXT          NOT NULL,
    vehicle_type         TEXT          NOT NULL,
    pickup_lat           NUMERIC(9,6)  NOT NULL,
    pickup_lng           NUMERIC(9,6)  NOT NULL,
    drop_lat             NUMERIC(9,6)  NOT NULL,
    drop_lng             NUMERIC(9,6)  NOT NULL,
    distance_km          NUMERIC(8,2)  NOT NULL,
    eta_minutes          INTEGER,
    requested_at         TIMESTAMP     NOT NULL,
    pickup_at            TIMESTAMP,
    delivered_at         TIMESTAMP,
    status               TEXT          NOT NULL,
    fare_amount          NUMERIC(10,2) NOT NULL,
    payment_mode         TEXT,
    cancellation_reason  TEXT,
    updated_at           TIMESTAMP     NOT NULL,
    source_file          TEXT          NOT NULL,
    source_row_num       INTEGER       NOT NULL,
    loaded_at            TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_trips_clean_requested_at ON staging.trips_clean (requested_at);
CREATE INDEX IF NOT EXISTS idx_trips_clean_city         ON staging.trips_clean (city);
CREATE INDEX IF NOT EXISTS idx_trips_clean_driver       ON staging.trips_clean (driver_id);

-- Quarantine: every rejected row, why it failed, and the original raw values
CREATE TABLE IF NOT EXISTS quarantine.trips_rejected (
    reject_id       BIGSERIAL PRIMARY KEY,
    source_file     TEXT        NOT NULL,
    row_num         INTEGER     NOT NULL,
    trip_id         TEXT,
    primary_reason  TEXT        NOT NULL,
    reject_reasons  TEXT[]      NOT NULL,
    raw_payload     JSONB       NOT NULL,
    rejected_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rejected_source_file ON quarantine.trips_rejected (source_file);
CREATE INDEX IF NOT EXISTS idx_rejected_reason      ON quarantine.trips_rejected (primary_reason);

-- One row per validation run per file (feeds the Data Quality scorecard later)
CREATE TABLE IF NOT EXISTS ops.validation_log (
    log_id          BIGSERIAL PRIMARY KEY,
    source_file     TEXT        NOT NULL,
    rows_in         INTEGER,
    rows_clean      INTEGER,
    rows_duplicate  INTEGER,
    rows_rejected   INTEGER,     -- includes duplicates
    city_fixed      INTEGER,
    status_fixed    INTEGER,
    status          TEXT        NOT NULL,   -- SUCCESS or FAILED
    error_message   TEXT,
    run_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    duration_ms     INTEGER
);