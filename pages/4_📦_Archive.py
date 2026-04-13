"""
Page 4: Archive — Past deployment data viewer with summary statistics.
"""

import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import date, time, datetime

st.set_page_config(page_title="Archive", page_icon="🔬", layout="wide")

from utils.theme import (  # noqa: E402
    render_header, render_footer, render_kpi_card,
    render_empty_state, render_error,
    render_sidebar, inject_custom_css, PNNL_BLUE,
)

inject_custom_css()
render_sidebar()
render_header()

_errors = []
try:
    from utils.sheets_client import (
        list_device_tabs, get_device_data, reorder_columns,
        get_device_ids, get_device_column,
    )
except Exception as e:
    _errors.append(f"sheets_client: {type(e).__name__}: {e}")

SHEETS_AVAILABLE = len(_errors) == 0


def render_archive():
    if not SHEETS_AVAILABLE:
        render_error(
            "Cannot connect to data source",
            "Failed to load the Google Sheets client. Check your Streamlit Secrets configuration.",
        )
        for err in _errors:
            st.error(err)
        return

    st.markdown(
        f'<h1 style="color:{PNNL_BLUE}; margin-top:0;">Archive</h1>',
        unsafe_allow_html=True,
    )

    if st.button("Refresh Data"):
        st.cache_data.clear()
        st.rerun()

    tabs = list_device_tabs()
    if not tabs:
        render_empty_state("No device tabs found", "Waiting for first transmission from RockBLOCK webhook.")
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

    # Determine device column and IDs
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

    df = all_data[all_data[dev_col].isin(selected_devices)].copy()
    if df.empty:
        render_empty_state("No data for selected devices", "Try selecting different devices.")
        return

    # Date range filter
    time_cols = [c for c in df.columns if "time" in c.lower() or "timestamp" in c.lower() or "date" in c.lower()]
    if time_cols:
        time_col = time_cols[0]
        try:
            df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
            valid_times = df[time_col].dropna()
            if not valid_times.empty:
                data_min = valid_times.min()
                data_max = valid_times.max()

                # Reset dates when device selection changes
                _sel_key = str(sorted(selected_devices))
                if st.session_state.get("_hist_sel_key") != _sel_key:
                    st.session_state["_hist_sel_key"] = _sel_key
                    st.session_state["hist_start"] = data_min.date()
                    st.session_state["hist_start_time"] = time(0, 0)
                    st.session_state["hist_end"] = data_max.date()
                    st.session_state["hist_end_time"] = time(23, 59)

                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    start = st.date_input("Start", key="hist_start")
                with c2:
                    start_t = st.time_input("Start time", key="hist_start_time")
                with c3:
                    end = st.date_input("End", key="hist_end")
                with c4:
                    end_t = st.time_input("End time", key="hist_end_time")
                start_dt = datetime.combine(start, start_t)
                end_dt = datetime.combine(end, end_t)
                mask = (df[time_col] >= pd.Timestamp(start_dt)) & (df[time_col] <= pd.Timestamp(end_dt))
                df = df[mask]
        except Exception:
            pass

    # Reorder columns, drop all-empty columns
    df = reorder_columns(df)
    non_empty = [c for c in df.columns if df[c].notna().any()]
    df = df[non_empty]

    # Summary stats with KPI cards
    st.markdown(f'<h3 style="color:{PNNL_BLUE};">Summary</h3>', unsafe_allow_html=True)
    stat1, stat2, stat3, stat4 = st.columns(4)
    with stat1:
        render_kpi_card("Total Records", f"{len(df):,}")

    if time_cols:
        try:
            date_range = f"{df[time_cols[0]].min().strftime('%Y-%m-%d')} to {df[time_cols[0]].max().strftime('%Y-%m-%d')}"
            with stat2:
                render_kpi_card("Date Range", date_range)
        except Exception:
            pass

    batt_cols = [c for c in df.columns if "battery" in c.lower()]
    if batt_cols:
        batt = pd.to_numeric(df[batt_cols[0]], errors="coerce")
        with stat3:
            render_kpi_card("Battery Min/Max", f"{batt.min():.3f} / {batt.max():.3f} V")
        with stat4:
            render_kpi_card("Battery Avg", f"{batt.mean():.3f} V")

    # Data table
    st.markdown(f'<h3 style="color:{PNNL_BLUE};">Data</h3>', unsafe_allow_html=True)
    st.dataframe(df, width="stretch", height=500, hide_index=True)

    # CSV export
    csv_buf = BytesIO()
    df.to_csv(csv_buf, index=False)
    st.download_button(
        "Export CSV",
        data=csv_buf.getvalue(),
        file_name="historical_data.csv",
        mime="text/csv",
    )


render_archive()
render_footer()
