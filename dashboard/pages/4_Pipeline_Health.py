"""Pipeline health: runs, durations, alerts, load throughput."""
from __future__ import annotations

import plotly.express as px
import streamlit as st

from db import run

st.set_page_config(page_title="Pipeline Health · HaulPulse", page_icon="🩺", layout="wide")
st.title("🩺 Pipeline health")

runs = run("""
    SELECT run_id, logical_date, started_at, finished_at, duration_seconds, status,
           failed_tasks, rows_in, rows_rejected, rejection_rate, fact_rows
    FROM ops.pipeline_runs
    ORDER BY logical_date DESC, run_pk DESC
    LIMIT 100
""")

if runs.empty:
    st.info("No pipeline runs recorded yet. Trigger the Airflow DAG once.")
else:
    ok = int((runs["status"] == "SUCCESS").sum())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Runs recorded", f"{len(runs)}")
    c2.metric("Success rate", f"{ok / len(runs) * 100:.0f}%")
    c3.metric("Avg duration", f"{runs['duration_seconds'].mean():.0f} s")
    c4.metric("Latest status", runs["status"].iloc[0])

    st.plotly_chart(
        px.bar(runs.sort_values("logical_date"), x="logical_date", y="duration_seconds", color="status",
               color_discrete_map={"SUCCESS": "#2ca02c", "FAILED": "#d62728"},
               title="DAG run duration (seconds)", labels={"logical_date": "", "duration_seconds": "Seconds"}),
        use_container_width=True,
    )
    st.dataframe(runs, hide_index=True, use_container_width=True)

st.subheader("Failure alerts")
alerts = run("""
    SELECT created_at, dag_id, task_id, try_number, message
    FROM ops.pipeline_alerts
    ORDER BY alert_id DESC
    LIMIT 20
""")
if alerts.empty:
    st.success("No alerts recorded.")
else:
    st.dataframe(alerts, hide_index=True, use_container_width=True)

st.subheader("Load throughput (bronze)")
load = run("""
    SELECT target_table, COUNT(*) AS loads, SUM(rows_loaded) AS rows,
           ROUND(SUM(duration_ms) / 1000.0, 1) AS seconds,
           ROUND(SUM(rows_loaded) / NULLIF(SUM(duration_ms) / 1000.0, 0)) AS rows_per_sec
    FROM ops.file_load_log
    WHERE status = 'SUCCESS'
    GROUP BY target_table
""")
st.dataframe(load, hide_index=True, use_container_width=True)

failed = run("SELECT COUNT(*) AS n FROM ops.file_load_log WHERE status = 'FAILED'")
st.caption(f"Failed load attempts on record: {int(failed['n'].iloc[0])} "
           "(logs are history, so old failures stay visible).")