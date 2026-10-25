-- One row per file load attempt (success or failure)
CREATE TABLE IF NOT EXISTS ops.file_load_log (
    load_id        BIGSERIAL PRIMARY KEY,
    source_file    TEXT        NOT NULL,
    target_table   TEXT        NOT NULL,
    rows_in_file   INTEGER,
    rows_loaded    INTEGER,
    status         TEXT        NOT NULL,   -- SUCCESS or FAILED
    error_message  TEXT,
    started_at     TIMESTAMPTZ NOT NULL,
    finished_at    TIMESTAMPTZ,
    duration_ms    INTEGER
);