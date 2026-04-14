"""
Page 7 — TENG Performance (Phase 2 placeholder).

Will analyze triboelectric nanogenerator output versus wave state and
correlate harvested energy with battery behavior.
"""

import importlib

import streamlit as st

st.set_page_config(page_title="TENG Performance", page_icon="🔋", layout="wide")

st.title("🔋 TENG Performance")
st.info("Phase 2 — Coming soon in PR P2-1")

st.markdown(
    """
    **Planned sections**
    - Wave-height vs. TENG power scatter with fitted response curve
    - Rolling energy budget (harvested vs. consumed)
    - Battery state-of-charge correlation with sea state
    - Event-based bursts: storm windows and harvesting spikes
    - Per-device comparison and deployment-wide aggregates
    """
)

# Sidebar toggle — import defensively so a missing Phase 2 module
# cannot crash the Streamlit app.
try:
    _flag = importlib.import_module("utils.p2.__phase2_flag")
    _flag.render_toggle_in_sidebar()
except Exception as exc:  # noqa: BLE001
    st.sidebar.caption(f"Phase 2 toggle unavailable: {exc}")
