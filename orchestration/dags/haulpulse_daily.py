"""HaulPulse daily pipeline.

generate source data -> bronze load -> silver validation -> dbt seed/run/test

Every task is idempotent, so retries and re-runs are safe.
"""
from __future__ import annotations

import logging
import os
from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator

log = logging.getLogger(__name__)

PROJECT_DIR = "/opt/airflow/project"
PY = "/home/airflow/pipeline-venv/bin/python"
DBT = "/home/airflow/pipeline-venv/bin/dbt"


def _sh(cmd: str) -> str:
    return f"cd {PROJECT_DIR} && {cmd}"


def _dbt(cmd: str) -> str:
    return f"cd {PROJECT_DIR}/dbt_project && {DBT} {cmd}"


def alert_on_failure(context) -> None:
    """Runs after a task has failed all of its retries."""
    ti = context["task_instance"]
    message = (
        f"ALERT: {ti.dag_id}.{ti.task_id} failed "
        f"(try {ti.try_number}, run_id={context['run_id']}): {context.get('exception')}"
    )
    log.error(message)
    try:
        import psycopg2

        conn = psycopg2.connect(
            host=os.environ["POSTGRES_HOST"],
            port=os.environ["POSTGRES_PORT"],
            dbname=os.environ["POSTGRES_DB"],
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
        )
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


default_args = {
    "owner": "sarvesh",
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
    "execution_timeout": timedelta(minutes=20),
    "on_failure_callback": alert_on_failure,
}

with DAG(
    dag_id="haulpulse_daily",
    description="Logistics ETL: source -> bronze -> silver -> dbt star schema + tests",
    start_date=pendulum.datetime(2026, 10, 19, tz="UTC"),
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
    dbt_run = BashOperator(task_id="dbt_run", bash_command=_dbt("run"))
    dbt_test = BashOperator(task_id="dbt_test", bash_command=_dbt("test"))

    apply_ddl >> generate_source_data >> [load_reference_data, load_bronze] >> validate_silver
    validate_silver >> dbt_seed >> dbt_run >> dbt_test