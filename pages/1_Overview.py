"""
Page 1: Overview — Device overview with KPI cards, mini map, and activity feed.
"""

import streamlit as st
import pandas as pd
from datetime import date

st.set_page_config(page_title="Overview", page_icon="🔬", layout="wide")

from utils.theme import (  # noqa: E402
    render_header, render_footer, render_kpi_card,
    render_empty_state, render_error, battery_color,
    PNNL_BLUE, SUCCESS, WARNING,
)

render_header()

_errors = []

try:
    from utils.sheets_client import (
        list_device_tabs, get_device_data, reorder_columns,
        get_device_ids, get_device_column,
    )
except Exception as e:
    _errors.append(f"sheets_client: {type(e).__name__}: {e}")

try:
    from utils.map_utils import build_mini_map, build_drift_map, BASEMAPS
except Exception as e:
    _errors.append(f"map_utils: {type(e).__name__}: {e}")

try:
    from streamlit_folium import st_folium
except Exception as e:
    _errors.append(f"streamlit_folium: {type(e).__name__}: {e}")

SHEETS_AVAILABLE = len(_errors) == 0


def render_overview():
    if not SHEETS_AVAILABLE:
        render_error(
            "Cannot load required modules",
            "Some dependencies failed to load. Check your installation.",
        )
        for err in _errors:
            st.error(err)
        return

    st.markdown(
        f'<h1 style="color:{PNNL_BLUE}; margin-top:0;">Overview</h1>',
        unsafe_allow_html=True,
    )

    if st.button("Refresh Data"):
        st.cache_data.clear()
        st.rerun()

    with st.spinner("Loading device data..."):
        tabs = list_device_tabs()

    if not tabs:
        render_empty_state(
            "No buoy data yet",
            "Waiting for first transmission from RockBLOCK webhook.",
        )
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
        render_empty_state("No data available", "Device tabs exist but contain no decoded data.")
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
        render_empty_state("No data for selected devices", "Try selecting different devices.")
        return

    # Parse time column
    time_cols = [c for c in all_data.columns if "time" in c.lower() or "timestamp" in c.lower() or "date" in c.lower()]
    last_contact_str = "N/A"
    last_contact_device = ""
    if time_cols:
        try:
            all_data["_parsed_time"] = pd.to_datetime(all_data[time_cols[0]], errors="coerce")
            latest = all_data["_parsed_time"].max()
            if pd.notna(latest):
                delta = pd.Timestamp.now() - latest
                hours = delta.total_seconds() / 3600
                minutes = int(delta.total_seconds() / 60)
                if minutes < 1:
                    last_contact_str = "Just now"
                elif minutes < 60:
                    last_contact_str = f"{minutes}m ago"
                else:
                    last_contact_str = f"{hours:.1f}h ago"
                # Find which device had the latest contact
                latest_row = all_data.loc[all_data["_parsed_time"].idxmax()]
                last_contact_device = str(latest_row.get(dev_col, ""))

            # Date range filter
            valid_times = all_data["_parsed_time"].dropna()
            if not valid_times.empty:
                data_min = valid_times.min().date()
                data_max = valid_times.max().date()
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    start_date = st.date_input("Start date", value=data_min, key="dash_start")
                with col_d2:
                    end_date = st.date_input("End date", value=data_max, key="dash_end")
                mask = (all_data["_parsed_time"].dt.date >= start_date) & (all_data["_parsed_time"].dt.date <= end_date)
                all_data = all_data[mask]
        except Exception:
            pass

    if all_data.empty:
        render_empty_state("No data in selected range", "Adjust the date range to see data.")
        return

    # === KPI Cards ===
    total_packets = len(all_data)
    crc_col = [c for c in all_data.columns if "crc" in c.lower()]
    data_quality = "N/A"
    if crc_col:
        valid_count = all_data[crc_col[0]].sum()
        quality_pct = (valid_count / total_packets * 100) if total_packets > 0 else 0
        data_quality = f"{quality_pct:.1f}%"

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        render_kpi_card("Active Buoys", str(len(selected_devices)))
    with kpi2:
        render_kpi_card("Last Contact", last_contact_str, last_contact_device)
    with kpi3:
        render_kpi_card("Total Packets", f"{total_packets:,}")
    with kpi4:
        render_kpi_card("Data Quality", data_quality, "CRC pass rate")

    st.markdown("<br>", unsafe_allow_html=True)

    # === Mini Map + Activity Feed ===
    map_col, feed_col = st.columns([3, 2])

    with map_col:
        st.markdown(
            f'<h3 style="color:{PNNL_BLUE};">Buoy Locations</h3>',
            unsafe_allow_html=True,
        )
        lat_cols = [c for c in all_data.columns if "latitude" in c.lower()]
        lon_cols = [c for c in all_data.columns if "longitude" in c.lower()]
        if lat_cols and lon_cols:
            mini = build_mini_map(all_data, lat_col=lat_cols[0], lon_col=lon_cols[0], device_col=dev_col)
            st_folium(mini, width=None, height=380, returned_objects=[])
        else:
            st.info("No GPS data available for mapping.")

    with feed_col:
        st.markdown(
            f'<h3 style="color:{PNNL_BLUE};">Recent Activity</h3>',
            unsafe_allow_html=True,
        )
        if "_parsed_time" in all_data.columns:
            recent = all_data.dropna(subset=["_parsed_time"]).sort_values("_parsed_time", ascending=False).head(10)
            for _, row in recent.iterrows():
                ts = row["_parsed_time"]
                delta = pd.Timestamp.now() - ts
                mins = int(delta.total_seconds() / 60)
                if mins < 1:
                    ago = "just now"
                elif mins < 60:
                    ago = f"{mins} min ago"
                else:
                    ago = f"{mins // 60} hr ago"

                device_name = str(row.get(dev_col, "Unknown"))
                version = str(row.get("Packet Ver", ""))
                byte_len = str(row.get("Bytes", ""))
                crc_ok = row.get("CRC Valid", None)
                crc_str = "CRC &#10003;" if crc_ok else "CRC &#10007;" if crc_ok is not None else ""

                # Check battery warning
                batt_cols = [c for c in all_data.columns if "battery" in c.lower()]
                batt_warning = ""
                if batt_cols:
                    batt_val = pd.to_numeric(row.get(batt_cols[0], None), errors="coerce")
                    if pd.notna(batt_val) and batt_val < 3.1:
                        batt_warning = f' &middot; <span style="color:#F57C00;">{batt_val:.2f}V low</span>'

                dot_color = SUCCESS if crc_ok else WARNING
                st.markdown(
                    f'<div style="padding:8px 0; border-bottom:1px solid #EFEFEF;">'
                    f'<span style="color:{dot_color};">&#9679;</span> '
                    f'<strong>{device_name}</strong> transmitted &nbsp;'
                    f'<span style="color:#999; font-size:12px;">{ago}</span>'
                    f'<br><span style="font-size:12px; color:#5A5A5A;">'
                    f'{version} &middot; {byte_len}B &middot; {crc_str}{batt_warning}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("No timestamped data for activity feed.")

    # === Trajectory Map ===
    st.markdown(f'<h3 style="color:{PNNL_BLUE};">Device Trajectories</h3>', unsafe_allow_html=True)
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


render_overview()
render_footer()
