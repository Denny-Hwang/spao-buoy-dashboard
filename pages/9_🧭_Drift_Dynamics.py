"""
Page 9 — Drift Dynamics (Phase 2 placeholder).

Will decompose buoy drift into wind-driven and current-driven components
using OSCAR surface currents and Open-Meteo wind.
"""

import importlib

import streamlit as st

st.set_page_config(page_title="Drift Dynamics", page_icon="🧭", layout="wide")

st.title("🧭 Drift Dynamics")
st.info("Phase 2 — Coming soon in PR P2-3")

st.markdown(
    """
    **Planned sections**
    - Observed vs. OSCAR-predicted drift trajectories
    - Wind-current decomposition and residual analysis
    - Leeway coefficient estimation
    - Mann-Kendall trend tests on drift speed
    - Sea-ice gated periods of constrained drift
    """
)

try:
    _flag = importlib.import_module("utils.p2.__phase2_flag")
    _flag.render_toggle_in_sidebar()
except Exception as exc:  # noqa: BLE001
    st.sidebar.caption(f"Phase 2 toggle unavailable: {exc}")
