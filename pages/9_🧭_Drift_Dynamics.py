"""
Page 9 — Drift Dynamics.

Three sections, selectable via the sidebar:
    C1 Trajectory, C2 Ekman decomposition, C3 Storm Response.
"""

from __future__ import annotations

import importlib

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Drift Dynamics", page_icon="🧭", layout="wide")

from utils.theme import (  # noqa: E402
    render_header, render_footer, render_sidebar, inject_custom_css,
    PNNL_BLUE,
)

inject_custom_css()
render_sidebar()
render_header()

st.markdown(
    f'<h1 style="color:{PNNL_BLUE}; margin-top:0;">🧭 Drift Dynamics</h1>',
    unsafe_allow_html=True,
)

try:
    _flag = importlib.import_module("utils.p2.__phase2_flag")
    _flag.render_toggle_in_sidebar()
except Exception as exc:  # noqa: BLE001
    st.sidebar.caption(f"Phase 2 toggle unavailable: {exc}")


@st.cache_data(ttl=120)
def _load_data() -> pd.DataFrame:
    from utils.sheets_client import get_all_data
    try:
        return get_all_data()
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Could not load data: {exc}")
        return pd.DataFrame()


df = _load_data()

try:
    panels = importlib.import_module("utils.p2.viz.drift_panels")
except Exception as exc:  # noqa: BLE001
    st.error(f"Failed to load drift panels: {exc}")
    st.stop()

REQUIRED = ("Lat", "Lon", "Timestamp")
missing = [c for c in REQUIRED if c not in df.columns]
if df.empty or missing:
    st.warning(
        "Drift Dynamics needs at least Lat, Lon, and Timestamp columns. "
        f"Missing: {missing or '(empty data)'}."
    )
    st.stop()

section = st.sidebar.radio(
    "Section",
    options=("C1 Trajectory", "C2 Ekman decomposition", "C3 Storm Response"),
    index=0,
)

# ──────────────────────────────────────────────────────────────────────
# C1 — Trajectory
# ──────────────────────────────────────────────────────────────────────
if section.startswith("C1"):
    st.subheader("C1 — Trajectory")
    st.plotly_chart(panels.build_trajectory_speed_colored(df), use_container_width=True)
    st.plotly_chart(panels.build_stick_plot_drift(df), use_container_width=True)
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(panels.build_cumulative_distance(df), use_container_width=True)
    with col2:
        st.plotly_chart(panels.build_daily_displacement(df), use_container_width=True)

# ──────────────────────────────────────────────────────────────────────
# C2 — Ekman decomposition
# ──────────────────────────────────────────────────────────────────────
elif section.startswith("C2"):
    st.subheader("C2 — Ekman decomposition")
    st.plotly_chart(panels.build_alpha_timeseries(df), use_container_width=True)
    st.caption(
        f"Reference lines: Niiler-Paduan α = {panels.NIILER_PADUAN_ALPHA} "
        f"(drogued); Poulain α ∈ [{panels.POULAIN_ALPHA_LOW}, "
        f"{panels.POULAIN_ALPHA_HIGH}] (undrogued band)."
    )
    st.plotly_chart(panels.build_theta_histogram(df), use_container_width=True)

    col1, col2 = st.columns(2)
    wind_rose, drift_rose = panels.build_wind_and_drift_rose(df)
    with col1:
        st.plotly_chart(wind_rose, use_container_width=True)
    with col2:
        st.plotly_chart(drift_rose, use_container_width=True)

    st.plotly_chart(panels.build_residual_vs_oscar(df), use_container_width=True)

# ──────────────────────────────────────────────────────────────────────
# C3 — Storm Response
# ──────────────────────────────────────────────────────────────────────
else:
    st.subheader("C3 — Storm Response")
    table = panels.build_storm_event_table(df)
    if table.empty:
        st.info("No storm events detected under the current thresholds.")
    else:
        st.dataframe(table, use_container_width=True)
    st.plotly_chart(panels.build_epoch_multipanel(df), use_container_width=True)
    st.plotly_chart(panels.build_pre_during_post_box(df, var="Hs"), use_container_width=True)

render_footer()
