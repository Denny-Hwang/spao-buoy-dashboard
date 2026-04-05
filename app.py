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

# Debug: show secrets key availability (values are NOT shown)
with st.expander("System Diagnostics", expanded=False):
    st.write("**Secrets keys available:**", list(st.secrets.keys()))
    if "gcp_service_account" in st.secrets:
        sa = st.secrets["gcp_service_account"]
        st.write("**gcp_service_account fields:**", list(sa.keys()))
        st.success("gcp_service_account secret found")
    else:
        st.error("gcp_service_account secret NOT found")

    # Check package availability
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

    # Try sheets client import
    try:
        from utils.sheets_client import get_client
        st.success("sheets_client import OK")
    except Exception as e:
        st.error(f"sheets_client import FAILED: {type(e).__name__}: {e}")

    # Try creating gspread client
    try:
        from utils.sheets_client import get_client
        client = get_client()
        st.success(f"gspread client created OK: {type(client)}")
    except Exception as e:
        st.error(f"gspread client FAILED: {type(e).__name__}: {e}")
