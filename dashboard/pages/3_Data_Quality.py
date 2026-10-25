"""Data quality scorecard: what was rejected, why, and what was auto-corrected."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from db import pct, run

st.set_page_config(page_title="Data Quality · HaulPulse", page_icon="✅", layout="wide")
st.title("✅ Data quality scorecard")
st.caption("Rows that fail validation are quarantined with a reason. They are never silently dropped.")

RULES = {
    "DUPLICATE_IN_FILE": "Exact duplicate trip_id within one file (first copy kept)",
    "MISSING_TRIP_ID": "trip_id is empty",
    "MISSING_CUSTOMER_ID": "customer_id is empty",
    "MISSING_CITY": "city is empty",
    "UNKNOWN_CITY": "city spelling not in the reference mapping",
    "INVALID_VEHICLE_TYPE": "vehicle type is not one of the known types",
    "INVALID_STATUS": "status is not a valid trip status",
    "MISSING_DRIVER": "no driver on a trip that should have one",
    "UNPARSEABLE_TIMESTAMP": "a required timestamp is missing or unreadable",
    "INVALID_NUMERIC_FIELD": "a number is missing or not numeric",
    "MISSING_FARE": "completed trip without a fare",
    "NEGATIVE_FARE": "fare is below zero",
    "BAD_DISTANCE": "distance is zero, negative or implausibly large",
    "GPS_OUT_OF_INDIA": "coordinates fall outside India",
    "MISSING_DELIVERY_TIMES": "completed trip without pickup or delivery time",
    "DELIVERED_BEFORE_PICKUP": "delivery time is earlier than pickup time",
}

files = run("""
    SELECT DISTINCT ON (source_file) source_file, rows_in, rows_clean, rows_duplicate,
           rows_rejected, city_fixed, status_fixed, run_at
    FROM ops.validation_log
    WHERE status = 'SUCCESS' AND LEFT(source_file, 6) = 'trips_'
    ORDER BY source_file, log_id DESC
""")
if files.empty:
    st.warning("No validation runs recorded yet. Run the pipeline first.")
    st.stop()

files["file_date"] = pd.to_datetime(files["source_file"].str.extract(r"trips_(\d{4}-\d{2}-\d{2})")[0])
files = files.sort_values("file_date")
files["rejection_rate"] = files["rows_rejected"] / files["rows_in"]

threshold = st.sidebar.slider("Alert threshold (rejection %)", 1.0, 20.0, 8.0, 0.5)

total_in, total_rej = int(files["rows_in"].sum()), int(files["rows_rejected"].sum())
fixed = int(files["city_fixed"].sum() + files["status_fixed"].sum())
over = int((files["rejection_rate"] * 100 > threshold).sum())

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Rows validated", f"{total_in:,}")
c2.metric("Quarantined", f"{total_rej:,}", pct(total_rej / total_in) + " of rows")
c3.metric("Auto-corrected values", f"{fixed:,}")
c4.metric("Latest day rejection", pct(files["rejection_rate"].iloc[-1]))
c5.metric(f"Days above {threshold:.1f}%", f"{over}", delta="alert" if over else "all clear",
          delta_color="inverse" if over else "normal")

# ---- rejection rate over time ----
fig = px.line(files, x="file_date", y="rejection_rate", title="Daily rejection rate",
              labels={"file_date": "", "rejection_rate": "Rejected rows / rows in"})
fig.add_hline(y=threshold / 100, line_dash="dash", line_color="red",
              annotation_text=f"alert threshold {threshold:.1f}%")
fig.update_yaxes(tickformat=".0%")
st.plotly_chart(fig, use_container_width=True)

# ---- reasons ----
reasons = run("""
    SELECT q.source_file, r AS reason, COUNT(*) AS n
    FROM quarantine.trips_rejected q, unnest(q.reject_reasons) AS r
    GROUP BY q.source_file, r
""")
reasons["file_date"] = pd.to_datetime(reasons["source_file"].str.extract(r"trips_(\d{4}-\d{2}-\d{2})")[0])
totals = reasons.groupby("reason")["n"].sum().sort_values()

left, right = st.columns(2)
left.plotly_chart(
    px.bar(totals.reset_index(), x="n", y="reason", orientation="h",
           title="Rejections by reason (all time)", labels={"n": "Rows", "reason": ""}),
    use_container_width=True,
)
right.plotly_chart(
    px.bar(reasons.sort_values("file_date"), x="file_date", y="n", color="reason",
           title="Rejections by reason over time", labels={"file_date": "", "n": "Rows"}),
    use_container_width=True,
)

# ---- auto-corrections ----
st.subheader("Auto-corrected, not rejected")
corr = files[["file_date", "city_fixed", "status_fixed"]].rename(
    columns={"city_fixed": "City spellings normalised", "status_fixed": "Status casing normalised"})
st.plotly_chart(
    px.bar(corr.melt(id_vars="file_date", var_name="Fix", value_name="Values"),
           x="file_date", y="Values", color="Fix", labels={"file_date": ""}),
    use_container_width=True,
)

# ---- rule coverage ----
st.subheader("Rule coverage")
coverage = pd.DataFrame({
    "Rule": list(RULES),
    "What it checks": list(RULES.values()),
    "Rows caught": [int(totals.get(code, 0)) for code in RULES],
})
st.dataframe(coverage.sort_values("Rows caught", ascending=False), hide_index=True,
             use_container_width=True)
st.caption("Rules with 0 rows are still active. They simply never fired on this data.")

# ---- quarantine explorer ----
st.subheader("Quarantine explorer")
reason = st.selectbox("Inspect a rejection reason", list(totals.sort_values(ascending=False).index))
sample = run("""
    SELECT source_file, row_num, reject_reasons, raw_payload
    FROM quarantine.trips_rejected
    WHERE :reason = ANY(reject_reasons)
    ORDER BY reject_id DESC
    LIMIT 25
""", {"reason": reason})
if sample.empty:
    st.info("No rows for this reason.")
else:
    payload = pd.json_normalize(sample["raw_payload"].tolist())
    head = sample[["source_file", "row_num"]].reset_index(drop=True)
    head["reasons"] = sample["reject_reasons"].map(lambda r: ", ".join(r)).reset_index(drop=True)
    st.dataframe(pd.concat([head, payload], axis=1), hide_index=True, use_container_width=True)
    st.caption("Original raw values exactly as received, so you can see what the source actually sent.")