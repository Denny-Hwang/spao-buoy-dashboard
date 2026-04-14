"""
Page 8 — SST Validation.

Three sections, selectable via the sidebar radio:
    B1 Intercomparison, B2 Drift Detection, B3 Diurnal Warming.
"""

from __future__ import annotations

import importlib

import pandas as pd
import streamlit as st

st.set_page_config(page_title="SST Validation", page_icon="🌊", layout="wide")
st.title("🌊 SST Validation")

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
    panels = importlib.import_module("utils.p2.viz.sst_panels")
except Exception as exc:  # noqa: BLE001
    st.error(f"Failed to load SST panels: {exc}")
    st.stop()

# ──────────────────────────────────────────────────────────────────────
# Data availability check
# ──────────────────────────────────────────────────────────────────────
buoy = panels.extract_buoy_sst(df) if not df.empty else None
products = panels.extract_products(df) if not df.empty else {}

if df.empty or buoy is None or not products:
    st.warning(
        "SST validation needs both a buoy-measured SST column and at "
        "least one enriched satellite column (SAT_SST_OISST_cC, "
        "SAT_SST_MUR_cC, SAT_SST_OSTIA_cC, or SAT_SST_ERA5_cC). "
        "Trigger the `enrichment_daily` GitHub Action and reload."
    )
    st.stop()

# ──────────────────────────────────────────────────────────────────────
# Section selector
# ──────────────────────────────────────────────────────────────────────
section = st.sidebar.radio(
    "Section",
    options=("B1 Intercomparison", "B2 Drift Detection", "B3 Diurnal Warming"),
    index=0,
)

# ──────────────────────────────────────────────────────────────────────
# B1
# ──────────────────────────────────────────────────────────────────────
if section.startswith("B1"):
    st.subheader("B1 — Intercomparison")
    metrics = panels.build_metrics_table(df)
    st.dataframe(metrics.style.format({
        "bias": "{:+.3f}", "rmse": "{:.3f}", "uRMSE": "{:.3f}",
        "std_diff": "{:+.3f}", "correlation": "{:.3f}",
    }), use_container_width=True)

    col_left, col_right = st.columns(2)
    with col_left:
        st.plotly_chart(panels.build_taylor(df), use_container_width=True)
    with col_right:
        st.plotly_chart(panels.build_target(df), use_container_width=True)

    st.plotly_chart(panels.build_sst_timeseries(df), use_container_width=True)
    st.plotly_chart(panels.build_residual_histogram(df), use_container_width=True)

# ──────────────────────────────────────────────────────────────────────
# B2
# ──────────────────────────────────────────────────────────────────────
elif section.startswith("B2"):
    st.subheader("B2 — Drift Detection")
    drift = panels.build_drift_timeseries(df)
    st.plotly_chart(drift["fig"], use_container_width=True)

    col1, col2 = st.columns(2)
    col1.metric("Drift slope", f"{drift['slope_per_week']:+.4f} °C/week")
    if drift["alarm"]:
        col2.error("🔴 Drift alarm — |slope| > 0.01 °C/week")
    else:
        col2.success("🟢 No drift alarm")

    st.plotly_chart(panels.build_drift_boxplot(df), use_container_width=True)
    st.plotly_chart(panels.build_cusum_chart(df), use_container_width=True)

# ──────────────────────────────────────────────────────────────────────
# B3
# ──────────────────────────────────────────────────────────────────────
else:
    st.subheader("B3 — Diurnal Warming")
    clear_sky = st.checkbox(
        "Clear-sky filter (requires ERA5 cloud_cover column)",
        value=False,
        help="If ERA5 cloud_cover is not in the enriched schema, the toggle has no effect.",
    )
    df_view = df
    if clear_sky and "ERA5_CLOUD_COVER" in df.columns:
        df_view = df[df["ERA5_CLOUD_COVER"] < 30]

    st.plotly_chart(panels.build_diurnal_composite(df_view), use_container_width=True)
    st.plotly_chart(panels.build_amplitude_vs_wind(df_view), use_container_width=True)
    st.caption("Kawai & Wada (2007) overlay is a qualitative envelope.")
