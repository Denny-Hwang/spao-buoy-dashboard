"""
SPAO Buoy Dashboard — Main entry point.
Multi-page Streamlit app for Arctic Ocean buoy monitoring.
"""

import streamlit as st

st.set_page_config(
    page_title="SPAO Buoy Monitoring System",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

from utils.theme import (  # noqa: E402
    render_header, render_footer, render_sidebar, inject_custom_css,
    PNNL_BLUE, SPAO_LOGO_BASE64,
)

# --- Global CSS + Sidebar ---
inject_custom_css()
render_sidebar()

# --- Header ---
render_header()

# --- Intro Page ---
if SPAO_LOGO_BASE64:
    st.markdown(
        f'<div style="text-align:center; padding:16px 0;">'
        f'<img src="{SPAO_LOGO_BASE64}" alt="SPAO Logo" style="height:180px;">'
        f'</div>',
        unsafe_allow_html=True,
    )

st.markdown(
    f'<h1 style="color:{PNNL_BLUE};">Welcome</h1>',
    unsafe_allow_html=True,
)
st.markdown("Real-time monitoring system for **Self-Powered Arctic Ocean** buoy deployments.")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.markdown(
        f"""
        ### Overview
        Device status at a glance — battery levels, GPS positions,
        and satellite trajectory map with the latest location highlighted.

        ### Live Telemetry
        Browse real-time telemetry data in a sortable table.
        Filter by device and date range, add notes directly in the table,
        and export to CSV.

        ### Packet Decoder
        Paste a hex string to decode any buoy packet instantly.
        Upload a CSV of RockBLOCK exports to batch-decode all payloads at once.
        """
    )

with col2:
    st.markdown(
        f"""
        ### Archive
        View and compare past deployment data across multiple devices.
        Summary statistics for battery, date range, and record count.

        ### Analytics
        Interactive drift trajectory maps (satellite imagery) and
        time-series sensor plots — battery, SST, pressure, humidity,
        TENG current, and more. Filter and color-code by device.
        """
    )

st.divider()

st.markdown(
    """
    ### Quick Start
    1. Select a page from the **sidebar** (or tap the menu icon on mobile)
    2. Data loads automatically from Google Sheets
    3. Use **Select Devices** to filter by buoy
    4. Click **Refresh Data** on any page to pull the latest data
    """
)

# --- Footer ---
render_footer()
