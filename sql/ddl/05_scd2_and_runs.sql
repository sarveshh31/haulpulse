-- Source schema evolution: drivers now carry updated_at
ALTER TABLE raw.drivers            ADD COLUMN IF NOT EXISTS updated_at TEXT;
ALTER TABLE staging.drivers_clean  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;

-- One row per Airflow DAG run
CREATE TABLE IF NOT EXISTS ops.pipeline_runs (
    run_pk            BIGSERIAL PRIMARY KEY,
    dag_id            TEXT        NOT NULL,
    run_id            TEXT        NOT NULL,
    logical_date      DATE        NOT NULL,
    started_at        TIMESTAMPTZ,
    finished_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    duration_seconds  NUMERIC(10,1),
    status            TEXT        NOT NULL,   -- SUCCESS or FAILED
    failed_tasks      TEXT,
    rows_in           INTEGER,
    rows_clean        INTEGER,
    rows_duplicate    INTEGER,
    rows_rejected     INTEGER,
    rejection_rate    NUMERIC(6,4),
    fact_rows         BIGINT,
    UNIQUE (dag_id, run_id)
);