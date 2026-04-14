"""
Page 8 — SST Validation.

This PR (P2-8) adds the "30-day bias trend" section reading from the
Derived_Daily worksheet. The full B1/B2/B3 intercomparison panels land
in a follow-up PR (P2-5).
"""

from __future__ import annotations

import importlib
import os

import pandas as pd
import streamlit as st

st.set_page_config(page_title="SST Validation", page_icon="🌊", layout="wide")
st.title("🌊 SST Validation")

try:
    _flag = importlib.import_module("utils.p2.__phase2_flag")
    _flag.render_toggle_in_sidebar()
except Exception as exc:  # noqa: BLE001
    st.sidebar.caption(f"Phase 2 toggle unavailable: {exc}")


st.info(
    "Phase 2 SST validation — the intercomparison (B1), drift detection (B2), "
    "and diurnal warming (B3) sections land in a follow-up PR. This page "
    "currently renders the 30-day bias trend from the Derived_Daily "
    "worksheet so long-term trends are visible as soon as the aggregation "
    "cron has populated the sheet."
)

st.markdown(
    """
    **Planned sections**
    - B1 Intercomparison — metrics table, Taylor and target diagrams, time series
    - B2 Drift Detection — Theil-Sen fit on (buoy − OISST), CUSUM chart
    - B3 Diurnal Warming — hour-of-day composite, amplitude vs wind speed
    """
)

st.divider()

# ──────────────────────────────────────────────────────────────────────
# 30-day bias trend (Derived_Daily)
# ──────────────────────────────────────────────────────────────────────
st.subheader("30-day bias trend (Derived_Daily)")


@st.cache_data(ttl=300)
def _load_derived_daily() -> pd.DataFrame:
    try:
        from utils.p2.derived_io import read_derived_daily
        sheet_id = (
            st.secrets.get("GOOGLE_SHEETS_ID", None)
            if hasattr(st, "secrets") else None
        ) or os.environ.get("GOOGLE_SHEETS_ID", "")
        if not sheet_id:
            try:
                from utils.sheets_client import SHEET_ID as _FALLBACK_ID
                sheet_id = _FALLBACK_ID
            except Exception:
                sheet_id = ""
        if not sheet_id:
            return pd.DataFrame()
        return read_derived_daily(sheet_id)
    except Exception as exc:  # noqa: BLE001
        st.caption(f"Derived_Daily unavailable: {exc}")
        return pd.DataFrame()


daily_df = _load_derived_daily()
if daily_df.empty:
    st.info(
        "Derived_Daily worksheet not yet populated. "
        "Run the `derived_daily` GitHub Action (or "
        "`python scripts/compute_daily_derived.py`) to generate the "
        "daily-aggregation table, then reload this page."
    )
else:
    try:
        trend_panels = importlib.import_module("utils.p2.viz.trend_panels")
        st.plotly_chart(
            trend_panels.build_sst_bias_trend(daily_df, window_days=30),
            use_container_width=True,
        )
        latest = daily_df.tail(7)
        if not latest.empty:
            st.caption("Last 7 rows from Derived_Daily")
            st.dataframe(latest, use_container_width=True)
    except Exception as exc:  # noqa: BLE001
        st.caption(f"Bias trend rendering failed: {exc}")
