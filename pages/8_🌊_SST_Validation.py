"""
Page 8 — SST Validation (Phase 2 placeholder).

Will compare buoy-measured sea surface temperature against multiple
satellite/reanalysis products (OISST, MUR, OSTIA, ERA5).
"""

import importlib

import streamlit as st

st.set_page_config(page_title="SST Validation", page_icon="🌊", layout="wide")

st.title("🌊 SST Validation")
st.info("Phase 2 — Coming soon in PR P2-2")

st.markdown(
    """
    **Planned sections**
    - Multi-source SST time series (buoy vs. OISST / MUR / OSTIA / ERA5)
    - Bias, RMSE and correlation metrics per product
    - Taylor diagram of agreement across products
    - Spatial context map of closest grid cell
    - Filtering by sea ice concentration and data quality flags
    """
)

try:
    _flag = importlib.import_module("utils.p2.__phase2_flag")
    _flag.render_toggle_in_sidebar()
except Exception as exc:  # noqa: BLE001
    st.sidebar.caption(f"Phase 2 toggle unavailable: {exc}")
