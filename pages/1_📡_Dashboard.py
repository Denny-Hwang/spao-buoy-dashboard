"""
Page 1: Dashboard — Device overview with trajectory map and status cards.
"""

import streamlit as st
import pandas as pd

st.set_page_config(page_title="Dashboard", page_icon="📡", layout="wide")
st.title("📡 Dashboard")

try:
    from utils.sheets_client import list_device_tabs, get_device_data, get_all_data, reorder_columns
    from utils.map_utils import build_drift_map, BASEMAPS
    from streamlit_folium import st_folium

    SHEETS_AVAILABLE = True
except Exception:
    SHEETS_AVAILABLE = False


def render_dashboard():
    if not SHEETS_AVAILABLE:
        st.warning("Google Sheets connection not configured. Add `gcp_service_account` to Streamlit secrets.")
        return

    # Refresh button
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()

    with st.spinner("Loading device data..."):
        tabs = list_device_tabs()

    if not tabs:
        st.info("No device tabs found in the Google Sheet.")
        return

    # Device selector
    selected_devices = st.multiselect("Select Devices", tabs, default=tabs)
    if not selected_devices:
        st.info("Select at least one device.")
        return

    # Load data for selected devices
    frames = []
    for tab in selected_devices:
        df = get_device_data(tab)
        if not df.empty:
            df = df.copy()
            df["Device Tab"] = tab
            frames.append(df)

    if not frames:
        st.info("No data available for selected devices.")
        return

    all_data = pd.concat(frames, ignore_index=True)

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

    st.subheader(f"Active Devices: {len(selected_devices)}")

    # Device summary cards
    cols = st.columns(min(len(selected_devices), 4))
    for i, tab_name in enumerate(selected_devices):
        col = cols[i % len(cols)]
        device_df = all_data[all_data["Device Tab"] == tab_name] if "Device Tab" in all_data.columns else pd.DataFrame()

        with col:
            st.markdown(f"### {tab_name}")
            if device_df.empty:
                st.write("No data")
                continue

            st.metric("Messages", len(device_df))

            # Battery
            batt_cols = [c for c in device_df.columns if "battery" in c.lower()]
            if batt_cols:
                last_batt = pd.to_numeric(device_df[batt_cols[0]], errors="coerce").dropna()
                if not last_batt.empty:
                    st.metric("Battery", f"{last_batt.iloc[-1]:.3f} V")

            # GPS
            lat_cols = [c for c in device_df.columns if "latitude" in c.lower()]
            lon_cols = [c for c in device_df.columns if "longitude" in c.lower()]
            if lat_cols and lon_cols:
                last_lat = pd.to_numeric(device_df[lat_cols[0]], errors="coerce").dropna()
                last_lon = pd.to_numeric(device_df[lon_cols[0]], errors="coerce").dropna()
                if not last_lat.empty and not last_lon.empty:
                    st.write(f"GPS: {last_lat.iloc[-1]:.4f}, {last_lon.iloc[-1]:.4f}")

            st.divider()

    # Trajectory map — satellite basemap, shows full track with latest point highlighted
    st.subheader("Device Trajectories")
    lat_cols = [c for c in all_data.columns if "latitude" in c.lower()]
    lon_cols = [c for c in all_data.columns if "longitude" in c.lower()]
    if lat_cols and lon_cols:
        drift_map = build_drift_map(
            all_data,
            basemap="Satellite",
            lat_col=lat_cols[0],
            lon_col=lon_cols[0],
            device_col="Device Tab",
            highlight_latest=True,
        )
        st_folium(drift_map, width=None, height=500, returned_objects=[])
    else:
        st.info("No GPS data available for mapping.")


render_dashboard()

st.divider()
st.caption("SPAO Buoy Dashboard — Pacific Northwest National Laboratory")
