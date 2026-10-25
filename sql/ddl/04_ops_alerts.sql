CREATE TABLE IF NOT EXISTS ops.pipeline_alerts (
    alert_id      BIGSERIAL PRIMARY KEY,
    dag_id        TEXT        NOT NULL,
    task_id       TEXT        NOT NULL,
    run_id        TEXT,
    try_number    INTEGER,
    logical_date  TIMESTAMPTZ,
    message       TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);