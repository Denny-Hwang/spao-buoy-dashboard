"""
Page 2: Live Telemetry — Real-time data table with battery/CRC badges and inline notes editing.
"""

import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import date, time, datetime

st.set_page_config(page_title="Live Telemetry", page_icon="🔬", layout="wide")

from utils.theme import (  # noqa: E402
    render_header, render_footer, render_empty_state, render_error,
    battery_badge, crc_badge, battery_color,
    render_sidebar, inject_custom_css, PNNL_BLUE,
)

inject_custom_css()
render_sidebar()
render_header()

_errors = []
try:
    from utils.sheets_client import (
        list_device_tabs, get_device_data, update_note, reorder_columns,
        get_device_ids, get_device_column,
    )
except Exception as e:
    _errors.append(f"sheets_client: {type(e).__name__}: {e}")

SHEETS_AVAILABLE = len(_errors) == 0


def render_live_telemetry():
    if not SHEETS_AVAILABLE:
        render_error(
            "Cannot connect to data source",
            "Failed to load the Google Sheets client. Check your Streamlit Secrets configuration.",
        )
        for err in _errors:
            st.error(err)
        return

    st.markdown(
        f'<h1 style="color:{PNNL_BLUE}; margin-top:0;">Live Telemetry</h1>',
        unsafe_allow_html=True,
    )

    if st.button("Refresh Data"):
        st.cache_data.clear()
        st.rerun()

    tabs = list_device_tabs()
    if not tabs:
        render_empty_state("No device tabs found", "Waiting for first transmission from RockBLOCK webhook.")
        return

    # Load all tab data to discover Device IDs
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
    dev_col = get_device_column(all_data) or "Device Tab"
    device_ids = get_device_ids(all_data)
    if not device_ids:
        device_ids = tabs
        dev_col = "Device Tab"

    # Sidebar filters
    st.markdown(f'<h4 style="color:{PNNL_BLUE};">Filters</h4>', unsafe_allow_html=True)
    filter_col1, filter_col2, filter_col3 = st.columns([2, 1, 1])
    with filter_col1:
        selected = st.selectbox("Select Device", device_ids)
    with filter_col2:
        crc_cols = [c for c in all_data.columns if "crc" in c.lower()]
        crc_filter = st.selectbox("CRC Filter", ["All", "Valid only", "Invalid only"])
    with filter_col3:
        auto_refresh = st.checkbox("Auto-refresh (5 min)")

    # Filter by selected device
    df = all_data[all_data[dev_col] == selected].copy()
    selected_tab = df["Device Tab"].iloc[0] if "Device Tab" in df.columns and not df.empty else selected

    # Detect device change and reset date filters
    if st.session_state.get("live_selected_device") != selected:
        st.session_state.live_selected_device = selected
        for k in ("live_start", "live_end", "live_start_time", "live_end_time"):
            st.session_state.pop(k, None)
        st.rerun()

    if auto_refresh:
        import time
        if "last_refresh" not in st.session_state:
            st.session_state.last_refresh = time.time()
        if time.time() - st.session_state.last_refresh > 300:
            st.session_state.last_refresh = time.time()
            get_device_data.clear()
            st.rerun()

    if df.empty:
        render_empty_state(f"No data for {selected}", "This device has not transmitted any data yet.")
        return

    st.write(f"**{len(df)} records** for device `{selected}`")

    # Date range filter
    time_cols = [c for c in df.columns if "time" in c.lower() or "timestamp" in c.lower() or "date" in c.lower()]
    time_col = None
    if time_cols:
        time_col = time_cols[0]
        try:
            df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
            valid_times = df[time_col].dropna()
            if not valid_times.empty:
                data_min = valid_times.min()
                data_max = valid_times.max()
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    start_date = st.date_input("Start date", value=data_min.date(), key="live_start")
                with col2:
                    start_time = st.time_input("Start time", value=time(0, 0), key="live_start_time")
                with col3:
                    end_date = st.date_input("End date", value=data_max.date(), key="live_end")
                with col4:
                    end_time = st.time_input("End time", value=time(23, 59), key="live_end_time")
                start_dt = datetime.combine(start_date, start_time)
                end_dt = datetime.combine(end_date, end_time)
                mask = (df[time_col] >= pd.Timestamp(start_dt)) & (df[time_col] <= pd.Timestamp(end_dt))
                df = df[mask]
        except Exception:
            pass

    # CRC filter
    if crc_cols and crc_filter != "All":
        crc_col_name = crc_cols[0]
        if crc_filter == "Valid only":
            df = df[df[crc_col_name] == True]  # noqa: E712
        elif crc_filter == "Invalid only":
            df = df[df[crc_col_name] == False]  # noqa: E712

    # Sort newest first
    if time_col:
        df = df.sort_values(time_col, ascending=False)

    # Save original sheet row index then reset
    df["_sheet_row"] = df.index
    df = df.reset_index(drop=True)

    # Reorder columns (hex last)
    df = reorder_columns(df)

    # Drop columns that are entirely empty/NaN
    non_empty = [c for c in df.columns if c in ("_sheet_row", "Notes") or df[c].notna().any()]
    df = df[non_empty]

    # Ensure Notes column exists
    if "Notes" not in df.columns:
        df["Notes"] = ""

    # === Battery & CRC visual badges ===
    batt_cols = [c for c in df.columns if "battery" in c.lower()]
    crc_valid_cols = [c for c in df.columns if "crc" in c.lower()]

    if batt_cols or crc_valid_cols:
        st.markdown(f'<h4 style="color:{PNNL_BLUE};">Status Indicators</h4>', unsafe_allow_html=True)
        badge_items = []
        if batt_cols:
            last_batt = pd.to_numeric(df[batt_cols[0]], errors="coerce").dropna()
            if not last_batt.empty:
                batt_val = last_batt.iloc[0]
                badge_items.append(f"Battery: {battery_badge(batt_val)}")
        if crc_valid_cols:
            last_crc = df[crc_valid_cols[0]].iloc[0] if not df.empty else None
            if last_crc is not None:
                badge_items.append(f"CRC: {crc_badge(bool(last_crc))}")
        if badge_items:
            st.markdown(" &nbsp;&nbsp; ".join(badge_items), unsafe_allow_html=True)

    # Columns to display
    display_cols = [c for c in df.columns if c not in ("_sheet_row", "Device Tab")]

    # Inline editable data table
    st.markdown(f'<h4 style="color:{PNNL_BLUE};">Data</h4>', unsafe_allow_html=True)
    edited_df = st.data_editor(
        df[display_cols],
        use_container_width=True,
        height=500,
        disabled=[c for c in display_cols if c != "Notes"],
        hide_index=True,
        key=f"editor_{selected}",
    )

    # Detect and save note changes
    if edited_df is not None and "Notes" in edited_df.columns:
        original_notes = df["Notes"].fillna("").astype(str)
        edited_notes = edited_df["Notes"].fillna("").astype(str)
        changed_mask = original_notes.values != edited_notes.values
        if changed_mask.any():
            if st.button("Save Notes", type="primary"):
                saved = 0
                for i in range(len(df)):
                    if changed_mask[i]:
                        sheet_row = int(df.iloc[i]["_sheet_row"])
                        new_note = str(edited_notes.iloc[i])
                        if update_note(selected_tab, sheet_row, new_note):
                            saved += 1
                if saved:
                    st.success(f"Saved {saved} note(s)!")
                    st.rerun()

    # CSV download
    csv_buf = BytesIO()
    df.to_csv(csv_buf, index=False)
    st.download_button(
        "Download CSV",
        data=csv_buf.getvalue(),
        file_name=f"{selected}_data.csv",
        mime="text/csv",
    )


render_live_telemetry()
render_footer()
