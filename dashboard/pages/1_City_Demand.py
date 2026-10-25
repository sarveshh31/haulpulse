"""City demand: when and where trips happen."""
from __future__ import annotations

import plotly.express as px
import streamlit as st

from db import fmt_inr, pct, run

st.set_page_config(page_title="City Demand · HaulPulse", page_icon="🗺️", layout="wide")
st.title("🗺️ City demand")

hourly = run("""
    SELECT city, hour_of_day, total_trips, days_observed, avg_trips_per_day,
           cancellation_rate, no_driver_rate, avg_fare, demand_rank, is_peak_hour
    FROM analytics.mart_city_demand_hourly
    ORDER BY city, hour_of_day
""")
if hourly.empty:
    st.warning("No data in analytics.mart_city_demand_hourly yet.")
    st.stop()

# ---- heatmap ----
pivot = hourly.pivot(index="city", columns="hour_of_day", values="avg_trips_per_day").fillna(0)
fig = px.imshow(pivot, aspect="auto", color_continuous_scale="YlOrRd",
                labels={"x": "Hour of day", "y": "City", "color": "Avg trips/day"},
                title="Average trips per day, by city and hour")
fig.update_xaxes(dtick=1)
st.plotly_chart(fig, use_container_width=True)

# ---- peak hours ----
st.subheader("Peak hours (top 3 per city)")
peaks = hourly[hourly["is_peak_hour"]].sort_values(["city", "demand_rank"])
peak_table = (
    peaks.groupby("city")["hour_of_day"]
    .apply(lambda s: ", ".join(f"{int(h):02d}:00" for h in s))
    .reset_index(name="Top 3 peak hours")
)
st.dataframe(peak_table, hide_index=True, use_container_width=True)

# ---- city deep dive ----
st.subheader("City deep dive")
cities = sorted(hourly["city"].unique())
city = st.selectbox("City", cities, index=0)
sub = hourly[hourly["city"] == city].copy()
sub["Hour type"] = sub["is_peak_hour"].map({True: "Peak", False: "Normal"})

l, r = st.columns(2)
l.plotly_chart(
    px.bar(sub, x="hour_of_day", y="avg_trips_per_day", color="Hour type",
           color_discrete_map={"Peak": "#d62728", "Normal": "#9ecae1"},
           title=f"{city}: trips per day by hour",
           labels={"hour_of_day": "Hour of day", "avg_trips_per_day": "Avg trips/day"}),
    use_container_width=True,
)
fig2 = px.line(sub, x="hour_of_day", y=["cancellation_rate", "no_driver_rate"],
               title=f"{city}: failure rates by hour",
               labels={"hour_of_day": "Hour of day", "value": "Rate", "variable": "Metric"})
fig2.update_yaxes(tickformat=".0%")
r.plotly_chart(fig2, use_container_width=True)

# ---- why trips fail + payment mix ----
st.subheader("Failures and payments")
choice = st.selectbox("Filter by city", ["All"] + cities, key="fail_city")

reasons = run("""
    SELECT f.cancellation_reason AS reason, COUNT(*) AS trips
    FROM analytics.fact_trips f
    JOIN analytics.dim_city c ON f.city_key = c.city_key
    WHERE f.cancellation_reason IS NOT NULL AND (:city = 'All' OR c.city = :city)
    GROUP BY 1 ORDER BY 2 DESC
""", {"city": choice})

payments = run("""
    SELECT f.payment_mode, COUNT(*) AS trips,
           COALESCE(SUM(f.fare_amount) FILTER (WHERE f.is_completed), 0) AS revenue
    FROM analytics.fact_trips f
    JOIN analytics.dim_city c ON f.city_key = c.city_key
    WHERE (:city = 'All' OR c.city = :city)
    GROUP BY 1 ORDER BY 2 DESC
""", {"city": choice})

p, q = st.columns(2)
p.plotly_chart(
    px.bar(reasons.sort_values("trips"), x="trips", y="reason", orientation="h",
           title="Why trips fail", labels={"trips": "Trips", "reason": ""}),
    use_container_width=True,
)
q.plotly_chart(
    px.pie(payments, names="payment_mode", values="trips", hole=0.5, title="Payment mode mix"),
    use_container_width=True,
)
q.caption(f"Revenue in this selection: {fmt_inr(payments['revenue'].sum())} "
          f"· UPI share: {pct(payments.loc[payments['payment_mode'] == 'UPI', 'trips'].sum() / max(payments['trips'].sum(), 1))}")