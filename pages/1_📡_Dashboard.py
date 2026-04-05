"""
Page 1: Dashboard — Device overview and quick status.
"""

import streamlit as st
import pandas as pd

st.set_page_config(page_title="Dashboard", page_icon="📡", layout="wide")
st.title("📡 Dashboard")

try:
    from utils.sheets_client import list_device_tabs, get_device_data, get_all_data
    from utils.map_utils import build_mini_map
    from streamlit_folium import st_folium

    SHEETS_AVAILABLE = True
except Exception:
    SHEETS_AVAILABLE = False


def render_dashboard():
    if not SHEETS_AVAILABLE:
        st.warning("Google Sheets connection not configured. Add `gcp_service_account` to Streamlit secrets.")
        return

    with st.spinner("Loading device data..."):
        tabs = list_device_tabs()

    if not tabs:
        st.info("No device tabs found in the Google Sheet.")
        return

    st.subheader(f"Active Devices: {len(tabs)}")

    # Load all device data for overview
    all_data = get_all_data()

    if all_data.empty:
        st.info("No data available yet.")
        return

    # System status
    time_cols = [c for c in all_data.columns if "time" in c.lower() or "timestamp" in c.lower() or "date" in c.lower()]
    if time_cols:
        try:
            all_data["_parsed_time"] = pd.to_datetime(all_data[time_cols[0]], errors="coerce")
            latest = all_data["_parsed_time"].max()
            if pd.notna(latest):
                delta = pd.Timestamp.now() - latest
                hours = delta.total_seconds() / 3600
                if hours < 1:
                    status_text = f"Last data received: {int(delta.total_seconds() / 60)} minutes ago"
                else:
                    status_text = f"Last data received: {hours:.1f} hours ago"
                st.success(status_text)
        except Exception:
            pass

    # Device summary cards
    cols = st.columns(min(len(tabs), 4))
    for i, imei in enumerate(tabs):
        col = cols[i % len(cols)]
        device_df = all_data[all_data["IMEI"] == imei] if "IMEI" in all_data.columns else pd.DataFrame()

        with col:
            st.markdown(f"### {imei}")
            if device_df.empty:
                st.write("No data")
                continue

            msg_count = len(device_df)
            st.metric("Messages", msg_count)

            # Battery
            batt_cols = [c for c in device_df.columns if "battery" in c.lower()]
            if batt_cols:
                last_batt = device_df[batt_cols[0]].iloc[-1]
                st.metric("Battery", f"{last_batt} V")

            # GPS
            lat_cols = [c for c in device_df.columns if "latitude" in c.lower()]
            lon_cols = [c for c in device_df.columns if "longitude" in c.lower()]
            if lat_cols and lon_cols:
                last_lat = device_df[lat_cols[0]].iloc[-1]
                last_lon = device_df[lon_cols[0]].iloc[-1]
                st.write(f"GPS: {last_lat:.4f}, {last_lon:.4f}")

            st.divider()

    # Mini map
    st.subheader("Device Locations")
    lat_cols = [c for c in all_data.columns if "latitude" in c.lower()]
    lon_cols = [c for c in all_data.columns if "longitude" in c.lower()]
    if lat_cols and lon_cols:
        mini_map = build_mini_map(all_data, lat_col=lat_cols[0], lon_col=lon_cols[0])
        st_folium(mini_map, width=None, height=350, returned_objects=[])
    else:
        st.info("No GPS data available for mapping.")


render_dashboard()

st.divider()
st.caption("SPAO Buoy Dashboard — Pacific Northwest National Laboratory · DOE Water Power Technologies Office")
