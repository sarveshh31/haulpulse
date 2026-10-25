"""HaulPulse daily pipeline.

generate source data -> bronze load -> silver validation -> dbt (seed, snapshot, run, test) -> audit

Every task is idempotent, so retries and re-runs are safe.
"""
from __future__ import annotations

import logging
import os
from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.exceptions import AirflowException
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.utils.trigger_rule import TriggerRule

log = logging.getLogger(__name__)

PROJECT_DIR = "/opt/airflow/project"
PY = "/home/airflow/pipeline-venv/bin/python"
DBT = "/home/airflow/pipeline-venv/bin/dbt"


def _sh(cmd: str) -> str:
    return f"cd {PROJECT_DIR} && {cmd}"


def _dbt(cmd: str) -> str:
    return f"cd {PROJECT_DIR}/dbt_project && {DBT} {cmd}"


def _connect():
    import psycopg2

    return psycopg2.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )


def alert_on_failure(context) -> None:
    """Runs after a task has failed all of its retries."""
    ti = context["task_instance"]
    message = (
        f"ALERT: {ti.dag_id}.{ti.task_id} failed "
        f"(try {ti.try_number}, run_id={context['run_id']}): {context.get('exception')}"
    )
    log.error(message)
    try:
        conn = _connect()
        with conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ops.pipeline_alerts "
                "(dag_id, task_id, run_id, try_number, logical_date, message) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (ti.dag_id, ti.task_id, context["run_id"], ti.try_number,
                 context.get("logical_date"), message[:1000]),
            )
        conn.close()
    except Exception:
        log.exception("Could not record alert in ops.pipeline_alerts")


def record_pipeline_run(**context) -> None:
    """Write one audit row per DAG run. Runs even if upstream tasks failed."""
    dag_run = context["dag_run"]
    this_task = context["task_instance"].task_id
    others = [ti for ti in dag_run.get_task_instances() if ti.task_id != this_task]
    failed = sorted(ti.task_id for ti in others if ti.state in ("failed", "upstream_failed"))
    status = "FAILED" if failed else "SUCCESS"

    started = dag_run.start_date
    finished = pendulum.now("UTC")
    duration = round((finished - started).total_seconds(), 1) if started else None
    source_file = f"trips_{context['ds']}.csv"

    conn = _connect()
    with conn, conn.cursor() as cur:
        cur.execute(
            "SELECT rows_in, rows_clean, rows_duplicate, rows_rejected FROM ops.validation_log "
            "WHERE source_file = %s AND status = 'SUCCESS' ORDER BY log_id DESC LIMIT 1",
            (source_file,),
        )
        rows_in, rows_clean, rows_dup, rows_rej = cur.fetchone() or (None, None, None, None)
        rate = round(rows_rej / rows_in, 4) if rows_in else None

        cur.execute("SELECT to_regclass('analytics.fact_trips')")
        fact_rows = None
        if cur.fetchone()[0] is not None:
            cur.execute("SELECT COUNT(*) FROM analytics.fact_trips")
            fact_rows = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO ops.pipeline_runs
                (dag_id, run_id, logical_date, started_at, finished_at, duration_seconds, status,
                 failed_tasks, rows_in, rows_clean, rows_duplicate, rows_rejected, rejection_rate, fact_rows)
            VALUES (%s, %s, %s, %s, now(), %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (dag_id, run_id) DO UPDATE SET
                finished_at = now(), duration_seconds = EXCLUDED.duration_seconds,
                status = EXCLUDED.status, failed_tasks = EXCLUDED.failed_tasks,
                rows_in = EXCLUDED.rows_in, rows_clean = EXCLUDED.rows_clean,
                rows_duplicate = EXCLUDED.rows_duplicate, rows_rejected = EXCLUDED.rows_rejected,
                rejection_rate = EXCLUDED.rejection_rate, fact_rows = EXCLUDED.fact_rows
            """,
            (dag_run.dag_id, dag_run.run_id, context["ds"], started, duration, status,
             ",".join(failed) or None, rows_in, rows_clean, rows_dup, rows_rej, rate, fact_rows),
        )
    conn.close()
    log.info("Recorded pipeline run: status=%s failed=%s", status, failed)

    # Without this, the green audit task would make a failed run look successful
    if failed:
        raise AirflowException(f"Pipeline run failed. Failed tasks: {failed}")


default_args = {
    "owner": "sarvesh",
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
    "execution_timeout": timedelta(minutes=20),
    "on_failure_callback": alert_on_failure,
}

with DAG(
    dag_id="haulpulse_daily",
    description="Logistics ETL: source -> bronze -> silver -> dbt star schema + tests -> audit",
    start_date=pendulum.datetime(2026, 3, 1, tz="UTC"),
    schedule="@daily",
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["haulpulse", "etl", "dbt"],
) as dag:

    apply_ddl = BashOperator(
        task_id="apply_ddl",
        bash_command=_sh(f"{PY} -m pipeline.bootstrap"),
    )

    generate_source_data = BashOperator(
        task_id="generate_source_data",
        bash_command=_sh(f"{PY} -m generator.generate --date " + "{{ ds }}" + " --rows 5000"),
    )

    load_reference_data = BashOperator(
        task_id="load_reference_data",
        bash_command=_sh(f"{PY} -m pipeline.load_reference"),
    )

    load_bronze = BashOperator(
        task_id="load_bronze",
        bash_command=_sh(f"{PY} -m pipeline.load_bronze --date " + "{{ ds }}"),
    )

    validate_silver = BashOperator(
        task_id="validate_silver",
        bash_command=_sh(f"{PY} -m pipeline.run_silver --date " + "{{ ds }}"),
    )

    dbt_seed = BashOperator(task_id="dbt_seed", bash_command=_dbt("seed"))
    dbt_snapshot = BashOperator(task_id="dbt_snapshot", bash_command=_dbt("snapshot"))
    dbt_run = BashOperator(task_id="dbt_run", bash_command=_dbt("run"))
    dbt_test = BashOperator(task_id="dbt_test", bash_command=_dbt("test"))

    record_run = PythonOperator(
        task_id="record_pipeline_run",
        python_callable=record_pipeline_run,
        trigger_rule=TriggerRule.ALL_DONE,
        retries=0,
        on_failure_callback=None,
    )

    apply_ddl >> generate_source_data >> [load_reference_data, load_bronze] >> validate_silver
    validate_silver >> dbt_seed >> dbt_snapshot >> dbt_run >> dbt_test >> record_run