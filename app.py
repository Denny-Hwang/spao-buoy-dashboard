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
    "Pacific Northwest National Laboratory</small>",
    unsafe_allow_html=True,
)

# --- Intro Page ---
st.title("🌊 SPAO Buoy Dashboard")
st.markdown("Real-time monitoring system for **Self-Powered Arctic Ocean** buoy deployments.")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.markdown(
        """
        ### 📡 Dashboard
        Device status at a glance — battery levels, GPS positions,
        and satellite trajectory map with the latest location highlighted.

        ### 📊 Live Data
        Browse real-time telemetry data in a sortable table.
        Filter by device and date range, add notes directly in the table,
        and export to CSV.

        ### 🔧 Decoder
        Paste a hex string to decode any buoy packet instantly.
        Upload a CSV of RockBLOCK exports to batch-decode all payloads at once.
        """
    )

with col2:
    st.markdown(
        """
        ### 📁 Historical Data
        View and compare past deployment data across multiple devices.
        Summary statistics for battery, date range, and record count.

        ### 🗺️ Visualization
        Interactive drift trajectory maps (satellite imagery) and
        time-series sensor plots — battery, SST, pressure, humidity,
        TENG current, and more. Filter and color-code by device.
        """
    )

st.divider()

st.markdown(
    """
    ### Quick Start
    1. Select a page from the **sidebar** (or tap ☰ on mobile)
    2. Data loads automatically from Google Sheets
    3. Use **Select Devices** to filter by buoy
    4. Click **🔄 Refresh Data** on any page to pull the latest data
    """
)

# System diagnostics (collapsed by default)
with st.expander("System Diagnostics", expanded=False):
    st.write("**Secrets keys available:**", list(st.secrets.keys()))
    if "gcp_service_account" in st.secrets:
        sa = st.secrets["gcp_service_account"]
        st.write("**gcp_service_account fields:**", list(sa.keys()))
        st.success("gcp_service_account secret found")
    else:
        st.error("gcp_service_account secret NOT found")

    packages = {}
    for pkg in ["gspread", "google.oauth2.service_account", "streamlit_folium", "folium", "plotly"]:
        try:
            __import__(pkg)
            packages[pkg] = "OK"
        except ImportError as e:
            packages[pkg] = f"MISSING: {e}"
    st.write("**Package status:**")
    for pkg, status in packages.items():
        if "MISSING" in status:
            st.error(f"{pkg}: {status}")
        else:
            st.write(f"- {pkg}: {status}")

    try:
        from utils.sheets_client import get_client
        client = get_client()
        st.success("Google Sheets connection OK")
    except Exception as e:
        st.error(f"Google Sheets connection FAILED: {type(e).__name__}: {e}")
