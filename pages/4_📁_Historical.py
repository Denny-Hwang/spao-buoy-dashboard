"""
Page 4: Historical Data — Past deployment data viewer.
"""

import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="Historical Data", page_icon="📁", layout="wide")
st.title("📁 Historical Data")

try:
    from utils.sheets_client import list_device_tabs, get_device_data, get_all_data, reorder_columns
    SHEETS_AVAILABLE = True
except Exception:
    SHEETS_AVAILABLE = False


def render_historical():
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

    # Device selector — multi-select for filtering
    selected_devices = st.multiselect("Select Devices", tabs, default=tabs)
    if not selected_devices:
        st.info("Select at least one device.")
        return

    # Load and merge data
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

    df = pd.concat(frames, ignore_index=True)

    # Date range filter
    time_cols = [c for c in df.columns if "time" in c.lower() or "timestamp" in c.lower() or "date" in c.lower()]
    if time_cols:
        time_col = time_cols[0]
        try:
            df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
            valid_times = df[time_col].dropna()
            if not valid_times.empty:
                c1, c2 = st.columns(2)
                with c1:
                    start = st.date_input("Start", value=valid_times.min().date(), key="hist_start")
                with c2:
                    end = st.date_input("End", value=valid_times.max().date(), key="hist_end")
                mask = (df[time_col].dt.date >= start) & (df[time_col].dt.date <= end)
                df = df[mask]
        except Exception:
            pass

    # Reorder columns (hex last)
    df = reorder_columns(df)

    # Summary stats
    st.subheader("Summary")
    stat_cols = st.columns(4)
    stat_cols[0].metric("Total Records", len(df))

    if time_cols:
        try:
            date_range = f"{df[time_cols[0]].min().strftime('%Y-%m-%d')} to {df[time_cols[0]].max().strftime('%Y-%m-%d')}"
            stat_cols[1].metric("Date Range", date_range)
        except Exception:
            pass

    batt_cols = [c for c in df.columns if "battery" in c.lower()]
    if batt_cols:
        batt = pd.to_numeric(df[batt_cols[0]], errors="coerce")
        stat_cols[2].metric("Battery Min/Max", f"{batt.min():.3f} / {batt.max():.3f} V")
        stat_cols[3].metric("Battery Avg", f"{batt.mean():.3f} V")

    # Data table
    st.subheader("Data")
    st.dataframe(df, use_container_width=True, height=500, hide_index=True)

    # CSV export
    csv_buf = BytesIO()
    df.to_csv(csv_buf, index=False)
    st.download_button(
        "Export CSV",
        data=csv_buf.getvalue(),
        file_name="historical_data.csv",
        mime="text/csv",
    )


render_historical()

st.divider()
st.caption("SPAO Buoy Dashboard — Pacific Northwest National Laboratory")
