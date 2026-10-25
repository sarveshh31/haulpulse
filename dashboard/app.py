"""HaulPulse dashboard: executive overview."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from db import fmt_inr, pct, run

st.set_page_config(page_title="HaulPulse", page_icon="🚚", layout="wide")

NUM_COLS = ["total_trips", "completed_trips", "cancelled_trips", "no_driver_trips",
            "on_time_trips", "gross_revenue"]


def rates(df: pd.DataFrame) -> dict:
    """Aggregate ratios from COUNTS, never by averaging percentages."""
    t = df[NUM_COLS].sum()
    total, comp = float(t["total_trips"]), float(t["completed_trips"])
    return {
        "trips": int(total),
        "completed": int(comp),
        "revenue": float(t["gross_revenue"]),
        "on_time": float(t["on_time_trips"]) / comp if comp else 0.0,
        "cancel": float(t["cancelled_trips"]) / total if total else 0.0,
        "no_driver": float(t["no_driver_trips"]) / total if total else 0.0,
    }


st.title("🚚 HaulPulse: Logistics Analytics")
st.caption("Synthetic last-mile delivery data · dbt marts in PostgreSQL · refreshed by an Airflow DAG")

daily = run("""
    SELECT trip_date, city, total_trips, completed_trips, cancelled_trips,
           no_driver_trips, on_time_trips, gross_revenue
    FROM analytics.mart_daily_kpis
    ORDER BY trip_date
""")
if daily.empty:
    st.warning("No data in analytics.mart_daily_kpis yet. Run the pipeline first.")
    st.stop()

daily["trip_date"] = pd.to_datetime(daily["trip_date"])
min_d, max_d = daily["trip_date"].min().date(), daily["trip_date"].max().date()

with st.sidebar:
    st.header("Filters")
    picked = st.date_input("Date range", value=(min_d, max_d), min_value=min_d, max_value=max_d)
    all_cities = sorted(daily["city"].unique())
    chosen = st.multiselect("Cities", all_cities, default=all_cities)
    granularity = st.radio("Trend granularity", ["Daily", "Weekly"], horizontal=True)

if not isinstance(picked, (tuple, list)) or len(picked) != 2:
    st.info("Pick an end date to continue.")
    st.stop()
if not chosen:
    st.info("Select at least one city.")
    st.stop()

start, end = pd.Timestamp(picked[0]), pd.Timestamp(picked[1])
base = daily[daily["city"].isin(chosen)]
f = base[(base["trip_date"] >= start) & (base["trip_date"] <= end)]
if f.empty:
    st.warning("No rows for this selection.")
    st.stop()

# ---- KPI cards with 7-day deltas ----
k = rates(f)
cur = rates(base[(base["trip_date"] > end - pd.Timedelta(days=7)) & (base["trip_date"] <= end)])
prev = rates(base[(base["trip_date"] > end - pd.Timedelta(days=14)) & (base["trip_date"] <= end - pd.Timedelta(days=7))])


def delta(key: str):
    if prev["trips"] == 0:
        return None
    return f"{(cur[key] - prev[key]) * 100:+.1f} pp vs prev 7d"


c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Trips", f"{k['trips']:,}")
c2.metric("Completed", pct(k["completed"] / k["trips"]) if k["trips"] else "-")
c3.metric("Revenue", fmt_inr(k["revenue"]))
c4.metric("On-time rate", pct(k["on_time"]), delta=delta("on_time"))
c5.metric("Cancellation rate", pct(k["cancel"]), delta=delta("cancel"), delta_color="inverse")
c6.metric("No-driver rate", pct(k["no_driver"]), delta=delta("no_driver"), delta_color="inverse")

# ---- trends ----
trend = f.groupby("trip_date")[NUM_COLS].sum()
if granularity == "Weekly":
    trend = trend.resample("W").sum()
trend = trend.reset_index()
comp = trend["completed_trips"].where(trend["completed_trips"] > 0)
tot = trend["total_trips"].where(trend["total_trips"] > 0)
trend["On-time rate"] = trend["on_time_trips"] / comp
trend["Cancellation rate"] = trend["cancelled_trips"] / tot
trend["No-driver rate"] = trend["no_driver_trips"] / tot

left, right = st.columns(2)
left.plotly_chart(
    px.line(trend, x="trip_date", y="total_trips", title=f"{granularity} trips",
            labels={"trip_date": "", "total_trips": "Trips"}),
    use_container_width=True,
)
right.plotly_chart(
    px.area(trend, x="trip_date", y="gross_revenue", title=f"{granularity} revenue (₹)",
            labels={"trip_date": "", "gross_revenue": "Revenue"}),
    use_container_width=True,
)

rate_long = trend.melt(id_vars="trip_date",
                       value_vars=["On-time rate", "Cancellation rate", "No-driver rate"],
                       var_name="Metric", value_name="Rate")
fig = px.line(rate_long, x="trip_date", y="Rate", color="Metric", title="Service quality over time",
              labels={"trip_date": ""})
fig.update_yaxes(tickformat=".0%")
st.plotly_chart(fig, use_container_width=True)

# ---- city comparison ----
by_city = f.groupby("city")[NUM_COLS].sum().reset_index()
by_city["on_time_rate"] = by_city["on_time_trips"] / by_city["completed_trips"].where(by_city["completed_trips"] > 0)

a, b = st.columns(2)
a.plotly_chart(
    px.bar(by_city.sort_values("gross_revenue"), x="gross_revenue", y="city", orientation="h",
           title="Revenue by city (₹)", labels={"gross_revenue": "Revenue", "city": ""}),
    use_container_width=True,
)
fig_ot = px.bar(by_city.sort_values("on_time_rate"), x="on_time_rate", y="city", orientation="h",
                title="On-time rate by city", labels={"on_time_rate": "On-time rate", "city": ""})
fig_ot.update_xaxes(tickformat=".0%", range=[max(0, by_city["on_time_rate"].min() - 0.05), 1])
b.plotly_chart(fig_ot, use_container_width=True)

# ---- sidebar footer: last pipeline run ----
last = run("SELECT status, finished_at, logical_date FROM ops.pipeline_runs ORDER BY run_pk DESC LIMIT 1")
if not last.empty:
    try:
        when = pd.Timestamp(last["finished_at"].iloc[0]).tz_convert("Asia/Kolkata").strftime("%d %b %H:%M IST")
    except Exception:
        when = str(last["finished_at"].iloc[0])
    st.sidebar.divider()
    st.sidebar.caption(f"Last pipeline run: **{last['status'].iloc[0]}** · {when}")