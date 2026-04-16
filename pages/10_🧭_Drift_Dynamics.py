"""
Page 10 — Drift Dynamics.

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
    # Force reload so new DESCRIPTIONS keys added in later deploys are
    # always picked up, even when Streamlit Cloud has cached an older
    # version of the module object in sys.modules.
    panels = importlib.reload(panels)
except Exception as exc:  # noqa: BLE001
    st.error(f"Failed to load drift panels: {exc}")
    st.stop()

# Defensive: older cached module versions did not expose DESCRIPTIONS,
# so resolve via getattr with an empty-dict fallback.
_DESC: dict = getattr(panels, "DESCRIPTIONS", {}) or {}

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
    st.markdown(
        "Where did the buoy go, how fast, and where is it now? The trajectory "
        "view auto-zooms to the track and links directly to the time-series "
        "panels below — spatial and temporal views should be read together."
    )
    st.markdown(f"*{_DESC.get('trajectory', '')}*")
    st.plotly_chart(panels.build_trajectory_speed_colored(df), use_container_width=True)
    st.markdown(f"*{_DESC.get('stick_plot', '')}*")
    st.plotly_chart(panels.build_stick_plot_drift(df), use_container_width=True)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"*{_DESC.get('cumulative_distance', '')}*")
        st.plotly_chart(panels.build_cumulative_distance(df), use_container_width=True)
    with col2:
        st.markdown(f"*{_DESC.get('daily_displacement', '')}*")
        st.plotly_chart(panels.build_daily_displacement(df), use_container_width=True)

# C2 — Ekman decomposition ────────────────────────────────────────────
with tab_c2:
    st.subheader("C2 — Ekman decomposition")
    st.markdown(
        "Decompose the drift velocity into a wind-driven component (Ekman) "
        "and a residual. The residual should match surface currents from "
        "OSCAR if the decomposition is clean."
    )
    st.markdown(f"*{_DESC.get('alpha', '')}*")
    st.plotly_chart(panels.build_alpha_timeseries(df), use_container_width=True)
    st.caption(
        f"Reference lines: Niiler-Paduan α = {panels.NIILER_PADUAN_ALPHA} "
        f"(drogued); Poulain α ∈ [{panels.POULAIN_ALPHA_LOW}, "
        f"{panels.POULAIN_ALPHA_HIGH}] (undrogued band)."
    )
    st.markdown(f"*{_DESC.get('theta', '')}*")
    st.plotly_chart(panels.build_theta_histogram(df), use_container_width=True)

    st.markdown(f"*{_DESC.get('roses', '')}*")
    col1, col2 = st.columns(2)
    wind_rose, drift_rose = panels.build_wind_and_drift_rose(df)
    with col1:
        st.plotly_chart(wind_rose, use_container_width=True)
    with col2:
        st.plotly_chart(drift_rose, use_container_width=True)

    st.markdown(f"*{_DESC.get('residual_vs_oscar', '')}*")
    st.plotly_chart(panels.build_residual_vs_oscar(df), use_container_width=True)

# C3 — Storm Response ─────────────────────────────────────────────────
with tab_c3:
    st.subheader("C3 — Storm Response")
    st.markdown(
        "Storm events are auto-detected from wave height (Hs) and wind "
        "(U10) thresholds. Each event is used to compute a superposed-epoch "
        "composite so response patterns emerge even from a modest catalog."
    )
    st.markdown(f"*{_DESC.get('storm_table', '')}*")
    table = panels.build_storm_event_table(df)
    if table.empty:
        st.info("No storm events detected under the current thresholds.")
    else:
        st.dataframe(table, use_container_width=True)
    st.markdown(f"*{_DESC.get('epoch_multipanel', '')}*")
    st.plotly_chart(panels.build_epoch_multipanel(df), use_container_width=True)
    st.markdown(f"*{_DESC.get('pre_during_post', '')}*")
    st.plotly_chart(panels.build_pre_during_post_box(df, var="Hs"), use_container_width=True)

render_footer()
