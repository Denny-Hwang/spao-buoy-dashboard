"""
Page 1: Dashboard — Device overview with trajectory map and status cards.
"""

import streamlit as st
import pandas as pd
from datetime import date

st.set_page_config(page_title="Dashboard", page_icon="📡", layout="wide")
st.title("📡 Dashboard")

_errors = []

try:
    from utils.sheets_client import (
        list_device_tabs, get_device_data, reorder_columns,
        get_device_ids, get_device_column,
    )
except Exception as e:
    _errors.append(f"sheets_client: {type(e).__name__}: {e}")

try:
    from utils.map_utils import build_drift_map, BASEMAPS
except Exception as e:
    _errors.append(f"map_utils: {type(e).__name__}: {e}")

try:
    from streamlit_folium import st_folium
except Exception as e:
    _errors.append(f"streamlit_folium: {type(e).__name__}: {e}")

SHEETS_AVAILABLE = len(_errors) == 0


def render_dashboard():
    if not SHEETS_AVAILABLE:
        st.error("Failed to load required modules:")
        for err in _errors:
            st.error(err)
        return

    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()

    with st.spinner("Loading device data..."):
        tabs = list_device_tabs()

    if not tabs:
        st.info("No device tabs found in the Google Sheet.")
        return

    # Load all tabs
    frames = []
    for tab in tabs:
        df = get_device_data(tab)
        if not df.empty:
            df = df.copy()
            df["Device Tab"] = tab
            frames.append(df)

    if not frames:
        st.info("No data available.")
        return

    all_data = pd.concat(frames, ignore_index=True)

    # Determine device column and unique device IDs
    dev_col = get_device_column(all_data) or "Device Tab"
    device_ids = get_device_ids(all_data)

    if not device_ids:
        device_ids = tabs
        dev_col = "Device Tab"

    # Device filter
    selected_devices = st.multiselect("Select Devices", device_ids, default=device_ids)
    if not selected_devices:
        st.info("Select at least one device.")
        return

    # Filter data by selected devices
    all_data = all_data[all_data[dev_col].isin(selected_devices)]
    if all_data.empty:
        st.info("No data for selected devices.")
        return

    # Parse time column and add date filter
    time_cols = [c for c in all_data.columns if "time" in c.lower() or "timestamp" in c.lower() or "date" in c.lower()]
    if time_cols:
        try:
            all_data["_parsed_time"] = pd.to_datetime(all_data[time_cols[0]], errors="coerce")
            latest = all_data["_parsed_time"].max()
            if pd.notna(latest):
                delta = pd.Timestamp.now() - latest
                hours = delta.total_seconds() / 3600
                if hours < 1:
                    st.success(f"Last data received: {int(delta.total_seconds() / 60)} minutes ago")
                else:
                    st.success(f"Last data received: {hours:.1f} hours ago")

            # Date range filter — defaults to today
            valid_times = all_data["_parsed_time"].dropna()
            if not valid_times.empty:
                today = date.today()
                col_d1, col_d2, col_d3 = st.columns([2, 2, 1])
                with col_d1:
                    start_date = st.date_input("Start date", value=today, key="dash_start")
                with col_d2:
                    end_date = st.date_input("End date", value=today, key="dash_end")
                with col_d3:
                    st.write("")
                    st.write("")
                    if st.button("Today", key="dash_today"):
                        st.session_state["dash_start"] = today
                        st.session_state["dash_end"] = today
                        st.rerun()
                mask = (all_data["_parsed_time"].dt.date >= start_date) & (all_data["_parsed_time"].dt.date <= end_date)
                all_data = all_data[mask]
        except Exception:
            pass

    if all_data.empty:
        st.info("No data for the selected date range.")
        return

    st.subheader(f"Active Devices: {len(selected_devices)}")

    # Device summary cards
    cols = st.columns(min(len(selected_devices), 4))
    for i, device_id in enumerate(selected_devices):
        col = cols[i % len(cols)]
        device_df = all_data[all_data[dev_col] == device_id]

        with col:
            st.markdown(f"### {device_id}")
            if device_df.empty:
                st.write("No data")
                continue

            st.metric("Messages", len(device_df))

            batt_cols = [c for c in device_df.columns if "battery" in c.lower()]
            if batt_cols:
                last_batt = pd.to_numeric(device_df[batt_cols[0]], errors="coerce").dropna()
                if not last_batt.empty:
                    st.metric("Battery", f"{last_batt.iloc[-1]:.3f} V")

            lat_cols = [c for c in device_df.columns if "latitude" in c.lower()]
            lon_cols = [c for c in device_df.columns if "longitude" in c.lower()]
            if lat_cols and lon_cols:
                last_lat = pd.to_numeric(device_df[lat_cols[0]], errors="coerce").dropna()
                last_lon = pd.to_numeric(device_df[lon_cols[0]], errors="coerce").dropna()
                if not last_lat.empty and not last_lon.empty:
                    st.write(f"GPS: {last_lat.iloc[-1]:.4f}, {last_lon.iloc[-1]:.4f}")

            st.divider()

    # Trajectory map
    st.subheader("Device Trajectories")
    lat_cols = [c for c in all_data.columns if "latitude" in c.lower()]
    lon_cols = [c for c in all_data.columns if "longitude" in c.lower()]
    if lat_cols and lon_cols:
        drift_map = build_drift_map(
            all_data,
            basemap="Satellite",
            lat_col=lat_cols[0],
            lon_col=lon_cols[0],
            device_col=dev_col,
            highlight_latest=True,
        )
        st_folium(drift_map, width=None, height=700, returned_objects=[])
    else:
        st.info("No GPS data available for mapping.")


render_dashboard()

st.divider()
st.caption("SPAO Buoy Dashboard — Pacific Northwest National Laboratory")
