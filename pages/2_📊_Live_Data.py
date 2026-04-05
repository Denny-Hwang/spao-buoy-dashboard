"""
Page 2: Live Data — Real-time data table with notes editing.
"""

import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Live Data", page_icon="📊", layout="wide")
st.title("📊 Live Data")

try:
    from utils.sheets_client import list_device_tabs, get_device_data, update_note
    SHEETS_AVAILABLE = True
except Exception:
    SHEETS_AVAILABLE = False


def render_live_data():
    if not SHEETS_AVAILABLE:
        st.warning("Google Sheets connection not configured. Add `gcp_service_account` to Streamlit secrets.")
        return

    # Refresh button
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()

    tabs = list_device_tabs()
    if not tabs:
        st.info("No device tabs found.")
        return

    # Device selector
    selected = st.selectbox("Select Device", tabs)

    # Auto-refresh
    auto_refresh = st.checkbox("Auto-refresh (every 5 min)")
    if auto_refresh:
        st.empty()
        import time
        if "last_refresh" not in st.session_state:
            st.session_state.last_refresh = time.time()
        if time.time() - st.session_state.last_refresh > 300:
            st.session_state.last_refresh = time.time()
            get_device_data.clear()
            st.rerun()

    # Load data
    df = get_device_data(selected)
    if df.empty:
        st.info(f"No data for {selected}.")
        return

    st.write(f"**{len(df)} records** for device `{selected}`")

    # Date range filter
    time_cols = [c for c in df.columns if "time" in c.lower() or "timestamp" in c.lower() or "date" in c.lower()]
    if time_cols:
        time_col = time_cols[0]
        try:
            df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
            valid_times = df[time_col].dropna()
            if not valid_times.empty:
                col1, col2 = st.columns(2)
                with col1:
                    start_date = st.date_input("Start date", value=valid_times.min().date())
                with col2:
                    end_date = st.date_input("End date", value=valid_times.max().date())
                mask = (df[time_col].dt.date >= start_date) & (df[time_col].dt.date <= end_date)
                df = df[mask]
        except Exception:
            pass

    # Sort newest first
    if time_cols:
        df = df.sort_index(ascending=False)

    # Display data table
    st.dataframe(df, use_container_width=True, height=400)

    # CSV download
    csv_buf = BytesIO()
    df.to_csv(csv_buf, index=False)
    st.download_button(
        "Download CSV",
        data=csv_buf.getvalue(),
        file_name=f"{selected}_data.csv",
        mime="text/csv",
    )

    # Notes editor
    st.subheader("Edit Notes")
    if "Notes" not in df.columns:
        df["Notes"] = ""

    row_options = list(range(len(df)))
    if not row_options:
        return

    selected_row = st.selectbox(
        "Select row to edit",
        row_options,
        format_func=lambda i: f"Row {i + 1}" + (f" — {df.iloc[i].get(time_cols[0], '')}" if time_cols else ""),
    )

    current_note = str(df.iloc[selected_row].get("Notes", ""))
    new_note = st.text_area("Note", value=current_note, key=f"note_{selected_row}")

    if st.button("Save Note"):
        original_idx = df.index[selected_row]
        success = update_note(selected, original_idx, new_note)
        if success:
            st.success("Note saved!")
            st.rerun()


render_live_data()

st.divider()
st.caption("SPAO Buoy Dashboard — Pacific Northwest National Laboratory · DOE Water Power Technologies Office")
