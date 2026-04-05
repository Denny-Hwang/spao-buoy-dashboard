"""
SPAO Buoy Dashboard — Main entry point.
Multi-page Streamlit app for Arctic Ocean buoy monitoring.
"""

import streamlit as st

st.set_page_config(
    page_title="SPAO Buoy Dashboard",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.title("SPAO Buoy Dashboard")
st.sidebar.markdown("Self-Powered Arctic Ocean buoy monitoring system")
st.sidebar.divider()
st.sidebar.markdown(
    "<small>SPAO Buoy Dashboard<br>"
    "Pacific Northwest National Laboratory<br>"
    "DOE Water Power Technologies Office</small>",
    unsafe_allow_html=True,
)

st.title("SPAO Buoy Dashboard")
st.markdown(
    """
    Welcome to the **SPAO (Self-Powered Arctic Ocean) Buoy Dashboard**.

    Use the sidebar to navigate between pages:

    - **Dashboard** — Device overview and quick status
    - **Live Data** — Real-time data table with notes editing
    - **Decoder** — Standalone packet decoder tool
    - **Historical** — Past deployment data viewer
    - **Visualization** — Maps and sensor plots
    """
)

st.info("Select a page from the sidebar to get started.")
