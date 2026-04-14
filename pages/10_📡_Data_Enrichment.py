"""
Page 10 — Data Enrichment (Phase 2 placeholder).

Will show the status of cron-based enrichment runs: coverage per source,
failure rates, last successful update, and a preview of enriched columns.
"""

import importlib

import streamlit as st

st.set_page_config(page_title="Data Enrichment", page_icon="📡", layout="wide")

st.title("📡 Data Enrichment")
st.info("Phase 2 — Coming soon in PR P2-4")

st.markdown(
    """
    **Planned sections**
    - Per-source coverage and last successful run
    - ENRICH_FLAG bit-occupancy heatmap across devices and time
    - Failure log and retry status
    - Preview of enriched columns for a selected device window
    - Manual backfill trigger (admin only, optional)
    """
)

try:
    _flag = importlib.import_module("utils.p2.__phase2_flag")
    _flag.render_toggle_in_sidebar()
except Exception as exc:  # noqa: BLE001
    st.sidebar.caption(f"Phase 2 toggle unavailable: {exc}")
