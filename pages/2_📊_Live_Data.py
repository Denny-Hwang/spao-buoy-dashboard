"""
Page 2: Live Data — Real-time data table with inline notes editing.
"""

import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Live Data", page_icon="📊", layout="wide")
st.title("📊 Live Data")

try:
    from utils.sheets_client import list_device_tabs, get_device_data, update_note, reorder_columns
    SHEETS_AVAILABLE = True
except Exception as _import_err:
    SHEETS_AVAILABLE = False
    _IMPORT_ERROR = _import_err


def render_live_data():
    if not SHEETS_AVAILABLE:
        st.warning("Google Sheets connection not configured. Add `gcp_service_account` to Streamlit secrets.")
        st.error(f"Import error: {_IMPORT_ERROR}")
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

    # Ensure columns are reordered (hex last)
    df = reorder_columns(df)

    # Ensure Notes column exists for inline editing
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
                    if update_note(selected, idx, new_note):
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
