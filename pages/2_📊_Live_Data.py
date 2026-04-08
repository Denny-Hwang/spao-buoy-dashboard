"""
Page 2: Live Data — Real-time data table with inline notes editing.
"""

import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import date

st.set_page_config(page_title="Live Data", page_icon="📊", layout="wide")
st.title("📊 Live Data")

_errors = []
try:
    from utils.sheets_client import (
        list_device_tabs, get_device_data, update_note, reorder_columns,
        get_device_ids, get_device_column,
    )
except Exception as e:
    _errors.append(f"sheets_client: {type(e).__name__}: {e}")

SHEETS_AVAILABLE = len(_errors) == 0


def render_live_data():
    if not SHEETS_AVAILABLE:
        st.error("Failed to load required modules:")
        for err in _errors:
            st.error(err)
        return

    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()

    tabs = list_device_tabs()
    if not tabs:
        st.info("No device tabs found.")
        return

    # Load all tab data to discover Device IDs
    frames = []
    tab_map = {}  # device_id -> tab_name (for note saving)
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
    dev_col = get_device_column(all_data) or "Device Tab"
    device_ids = get_device_ids(all_data)
    if not device_ids:
        device_ids = tabs
        dev_col = "Device Tab"

    # Device selector
    selected = st.selectbox("Select Device", device_ids)

    # Filter by selected device
    df = all_data[all_data[dev_col] == selected].copy()
    # Track which tab this device belongs to (for note saving)
    selected_tab = df["Device Tab"].iloc[0] if "Device Tab" in df.columns and not df.empty else selected

    # Auto-refresh
    auto_refresh = st.checkbox("Auto-refresh (every 5 min)")
    if auto_refresh:
        import time
        if "last_refresh" not in st.session_state:
            st.session_state.last_refresh = time.time()
        if time.time() - st.session_state.last_refresh > 300:
            st.session_state.last_refresh = time.time()
            get_device_data.clear()
            st.rerun()

    if df.empty:
        st.info(f"No data for {selected}.")
        return

    st.write(f"**{len(df)} records** for device `{selected}`")

    # Date range filter — defaults to today
    time_cols = [c for c in df.columns if "time" in c.lower() or "timestamp" in c.lower() or "date" in c.lower()]
    if time_cols:
        time_col = time_cols[0]
        try:
            df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
            valid_times = df[time_col].dropna()
            if not valid_times.empty:
                today = date.today()
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    start_date = st.date_input("Start date", value=today, key="live_start")
                with col2:
                    end_date = st.date_input("End date", value=today, key="live_end")
                with col3:
                    st.write("")
                    st.write("")
                    if st.button("Today", key="live_today"):
                        st.session_state["live_start"] = today
                        st.session_state["live_end"] = today
                        st.rerun()
                mask = (df[time_col].dt.date >= start_date) & (df[time_col].dt.date <= end_date)
                df = df[mask]
        except Exception:
            pass

    # Sort newest first
    if time_cols:
        df = df.sort_index(ascending=False)

    # Reorder columns (hex last)
    df = reorder_columns(df)

    # Ensure Notes column exists
    if "Notes" not in df.columns:
        df["Notes"] = ""

    # Inline editable data table
    st.subheader("Data")
    edited_df = st.data_editor(
        df,
        use_container_width=True,
        height=500,
        disabled=[c for c in df.columns if c != "Notes"],
        hide_index=True,
        key=f"editor_{selected}",
    )

    # Detect and save note changes
    if edited_df is not None and "Notes" in edited_df.columns:
        original_notes = df["Notes"].fillna("").astype(str)
        edited_notes = edited_df["Notes"].fillna("").astype(str)
        changed_mask = original_notes.values != edited_notes.values
        if changed_mask.any():
            if st.button("💾 Save Notes", type="primary"):
                saved = 0
                for idx in df.index[changed_mask]:
                    pos = df.index.get_loc(idx)
                    new_note = str(edited_notes.iloc[pos])
                    if update_note(selected_tab, idx, new_note):
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


render_live_data()

st.divider()
st.caption("SPAO Buoy Dashboard — Pacific Northwest National Laboratory")
