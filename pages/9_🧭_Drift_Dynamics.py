"""
Page 9 — Drift Dynamics.

Three sections, selected via main-area tabs:
    C1 Trajectory, C2 Ekman decomposition, C3 Storm Response.

Device and date-range selection lives in the shared Phase 2 toolbar
(``utils.p2.ui_toolbar.render_device_time_filter``), mirroring the
Phase 1 Analytics page so all analyses operate on an explicitly scoped
frame rather than a silent all-devices concat.
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


raw_df = _load_data()

try:
    panels = importlib.import_module("utils.p2.viz.drift_panels")
except Exception as exc:  # noqa: BLE001
    st.error(f"Failed to load drift panels: {exc}")
    st.stop()

# ── Shared device + date-range toolbar ────────────────────────────────
try:
    toolbar = importlib.import_module("utils.p2.ui_toolbar")
    df, selected_devices, time_col, dev_col = toolbar.render_device_time_filter(
        raw_df, key_prefix="p9",
    )
except Exception as exc:  # noqa: BLE001
    st.error(f"Toolbar unavailable: {exc}")
    st.stop()

# The toolbar already canonicalizes lat/lon to "Lat"/"Lon" when a
# recognizable variant (including FY25 "Approx Latitude" style headers)
# is present. Fall back to the resolver explicitly in case the toolbar
# couldn't rename for any reason.
try:
    from utils.p2.ui_toolbar import resolve_lat_lon_columns
    _lat, _lon = resolve_lat_lon_columns(df)
except Exception:
    _lat = "Lat" if "Lat" in df.columns else None
    _lon = "Lon" if "Lon" in df.columns else None

if df.empty or _lat is None or _lon is None:
    st.warning(
        "Drift Dynamics needs at least a latitude and longitude column. "
        f"Detected: lat={_lat!r}, lon={_lon!r}. "
        "If your sheet uses nonstandard headers, add them to the "
        "`_LAT_ALIASES` / `_LON_ALIASES` lists in utils/p2/ui_toolbar.py."
    )
    st.stop()

# ── Main-area tabs ────────────────────────────────────────────────────
tab_c1, tab_c2, tab_c3 = st.tabs([
    "C1 — Trajectory",
    "C2 — Ekman decomposition",
    "C3 — Storm Response",
])

# C1 — Trajectory ──────────────────────────────────────────────────────
with tab_c1:
    st.subheader("C1 — Trajectory")
    st.plotly_chart(panels.build_trajectory_speed_colored(df), use_container_width=True)
    st.plotly_chart(panels.build_stick_plot_drift(df), use_container_width=True)
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(panels.build_cumulative_distance(df), use_container_width=True)
    with col2:
        st.plotly_chart(panels.build_daily_displacement(df), use_container_width=True)

# C2 — Ekman decomposition ────────────────────────────────────────────
with tab_c2:
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

# C3 — Storm Response ─────────────────────────────────────────────────
with tab_c3:
    st.subheader("C3 — Storm Response")
    table = panels.build_storm_event_table(df)
    if table.empty:
        st.info("No storm events detected under the current thresholds.")
    else:
        st.dataframe(table, use_container_width=True)
    st.plotly_chart(panels.build_epoch_multipanel(df), use_container_width=True)
    st.plotly_chart(panels.build_pre_during_post_box(df, var="Hs"), use_container_width=True)

render_footer()
