"""Driver performance and SCD Type 2 history."""
from __future__ import annotations

import plotly.express as px
import streamlit as st

from db import run

st.set_page_config(page_title="Drivers · HaulPulse", page_icon="🧑‍✈️", layout="wide")
st.title("🧑‍✈️ Drivers")

drivers = run("""
    SELECT driver_id, driver_name, city, vehicle_type, rating, trips_assigned, completed_trips,
           completion_rate, on_time_rate, total_earnings, active_days,
           trips_per_active_day, utilization_rate, city_rank
    FROM analytics.mart_driver_performance
""")
if drivers.empty:
    st.warning("No data in analytics.mart_driver_performance yet.")
    st.stop()

with st.sidebar:
    st.header("Filters")
    city = st.selectbox("City", ["All"] + sorted(drivers["city"].unique()))
    min_trips = st.slider("Min completed trips", 0, int(drivers["completed_trips"].max()), 10)
    sort_by = st.selectbox("Sort by", ["completed_trips", "total_earnings", "on_time_rate", "utilization_rate"])

f = drivers[drivers["completed_trips"] >= min_trips]
if city != "All":
    f = f[f["city"] == city]
if f.empty:
    st.warning("No drivers match these filters.")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Drivers", f"{len(f):,}")
c2.metric("Avg on-time rate", f"{f['on_time_rate'].mean() * 100:.1f}%")
c3.metric("Avg utilization", f"{f['utilization_rate'].mean() * 100:.1f}%")
c4.metric("Avg rating", f"{f['rating'].mean():.2f}")

# ---- leaderboard ----
st.subheader("Leaderboard (top 25)")
top = f.sort_values(sort_by, ascending=False).head(25).copy()
top["On-time %"] = top["on_time_rate"] * 100
top["Utilization %"] = top["utilization_rate"] * 100
top["Completion %"] = top["completion_rate"] * 100
st.dataframe(
    top[["driver_id", "driver_name", "city", "vehicle_type", "rating", "completed_trips",
         "Completion %", "On-time %", "Utilization %", "total_earnings", "city_rank"]],
    hide_index=True, use_container_width=True,
    column_config={
        "rating": st.column_config.NumberColumn("Rating", format="%.2f"),
        "Completion %": st.column_config.NumberColumn(format="%.1f"),
        "On-time %": st.column_config.NumberColumn(format="%.1f"),
        "Utilization %": st.column_config.NumberColumn(format="%.1f"),
        "total_earnings": st.column_config.NumberColumn("Earnings (₹)", format="%.0f"),
        "city_rank": st.column_config.NumberColumn("City rank", format="%d"),
    },
)

# ---- scatter ----
fig = px.scatter(f, x="utilization_rate", y="on_time_rate", size="completed_trips", color="city",
                 hover_name="driver_name", title="Utilization vs on-time rate (bubble = completed trips)",
                 labels={"utilization_rate": "Utilization", "on_time_rate": "On-time rate"})
fig.update_xaxes(tickformat=".0%")
fig.update_yaxes(tickformat=".0%")
st.plotly_chart(fig, use_container_width=True)

# ---- SCD Type 2 history ----
st.subheader("Driver history (SCD Type 2)")
st.caption("When a driver moves city or changes vehicle, a new version is stored. "
           "Each trip is linked to the version that was valid at the time it was requested.")

changed = run("SELECT driver_id FROM analytics.dim_driver GROUP BY driver_id HAVING COUNT(*) > 1 ORDER BY driver_id")
moved = run("SELECT COUNT(DISTINCT driver_id) AS n FROM analytics.dim_driver WHERE NOT is_current")
st.write(f"**{int(moved['n'].iloc[0]):,}** drivers have more than one version.")

default_id = changed["driver_id"].iloc[0] if not changed.empty else "DRV-00001"
driver_id = st.text_input("Driver ID", value=default_id).strip().upper()

history = run("""
    SELECT to_char(d.valid_from, 'YYYY-MM-DD') AS valid_from,
           CASE WHEN d.is_current THEN 'current' ELSE to_char(d.valid_to, 'YYYY-MM-DD') END AS valid_to,
           d.city, d.vehicle_type, d.vehicle_number, COUNT(f.trip_id) AS trips
    FROM analytics.dim_driver d
    LEFT JOIN analytics.fact_trips f ON f.driver_key = d.driver_key
    WHERE d.driver_id = :id
    GROUP BY d.valid_from, d.valid_to, d.city, d.vehicle_type, d.vehicle_number, d.is_current
    ORDER BY d.valid_from
""", {"id": driver_id})

if history.empty:
    st.info("No driver found with that ID.")
else:
    st.dataframe(history, hide_index=True, use_container_width=True)