"""Shared database access and formatting helpers for the dashboard."""
from __future__ import annotations

import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()


@st.cache_resource
def get_engine():
    url = (
        f"postgresql+psycopg2://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
        f"@{os.getenv('POSTGRES_HOST', 'localhost')}:{os.getenv('POSTGRES_PORT', '5433')}"
        f"/{os.getenv('POSTGRES_DB')}"
    )
    return create_engine(url, pool_pre_ping=True)


@st.cache_data(ttl=300, show_spinner=False)
def query(sql: str, params: dict | None = None) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {}, coerce_float=True)


def run(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Run a cached query; show a friendly error and stop the page if the database is unreachable."""
    try:
        return query(sql, params)
    except Exception as exc:
        st.error(f"Database query failed: {exc}\n\nIs Docker running? Try: `docker compose up -d`")
        st.stop()


def fmt_inr(value: float) -> str:
    value = float(value or 0)
    if value >= 1e7:
        return f"₹{value / 1e7:.2f} Cr"
    if value >= 1e5:
        return f"₹{value / 1e5:.2f} L"
    return f"₹{value:,.0f}"


def pct(value: float, digits: int = 1) -> str:
    return f"{float(value or 0) * 100:.{digits}f}%"