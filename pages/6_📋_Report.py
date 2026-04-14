"""
Page 6: Report Generator — One-page device summary with PDF export.
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, time, datetime

st.set_page_config(page_title="Report", page_icon="📋", layout="wide")

from utils.theme import (  # noqa: E402
    render_header, render_footer, render_empty_state, render_error,
    render_sidebar, inject_custom_css, render_kpi_card,
    PNNL_BLUE, SENSOR_COLORS, DEVICE_PALETTE,
)

inject_custom_css()
render_sidebar()
render_header()

_errors = []
try:
    from utils.sheets_client import (
        list_device_tabs, get_device_data,
        get_device_nicknames, format_device_label,
    )
except Exception as e:
    _errors.append(f"sheets_client: {type(e).__name__}: {e}")

try:
    from utils.map_utils import build_drift_map, BASEMAPS
except Exception as e:
    _errors.append(f"map_utils: {type(e).__name__}: {e}")

try:
    from utils.plot_utils import (
        apply_plot_style, LINE_WIDTH, MARKER_SIZE,
    )
except Exception as e:
    _errors.append(f"plot_utils: {type(e).__name__}: {e}")

try:
    from streamlit_folium import st_folium
except Exception as e:
    _errors.append(f"streamlit_folium: {type(e).__name__}: {e}")

try:
    import plotly.graph_objects as go
except Exception as e:
    _errors.append(f"plotly: {type(e).__name__}: {e}")

try:
    from utils.report_pdf import (
        build_sensor_chart, build_scatter_chart,
        build_trajectory_image, build_trajectory_chart_fallback,
        compute_statistics, compute_kpis,
        generate_report_pdf, REPORT_SENSORS,
        _find_col, _find_time_col,
    )
except Exception as e:
    _errors.append(f"report_pdf: {type(e).__name__}: {e}")

MODULES_OK = len(_errors) == 0


def _find_time_column(df: pd.DataFrame) -> str | None:
    """Find and parse the best time column (local copy for page use)."""
    candidates = [c for c in df.columns
                  if "time" in c.lower() or "timestamp" in c.lower() or "date" in c.lower()]
    if not candidates:
        return None
    time_col = candidates[0]
    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    return time_col


def _find_sensor_col(df: pd.DataFrame, keywords: list[str]) -> str | None:
    """Find a column matching keywords, excluding prev-session and meta cols."""
    skip = {"Device", "Device Tab", "IMEI", "Timestamp", "Transmit Time",
            "MOMSN", "Packet Ver", "Bytes", "CRC Valid", "Raw Hex",
            "Notes", "Decode Error", "Warning"}
    for c in df.columns:
        cl = c.lower()
        if cl.startswith("prev"):
            continue
        if any(kw in cl for kw in keywords):
            if c not in skip:
                return c
    return None


def render_report():
    if not MODULES_OK:
        render_error(
            "Cannot load required modules",
            "Some dependencies failed to load. Check your installation.",
        )
        for err in _errors:
            st.error(err)
        return

    st.markdown(
        f'<h1 style="color:{PNNL_BLUE}; margin-top:0;">Report Generator</h1>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p style="color:#5A5A5A; margin-top:-8px;">'
        'Select a device and time period to generate a comprehensive report with PDF export.'
        '</p>',
        unsafe_allow_html=True,
    )

    tabs = list_device_tabs()
    if not tabs:
        render_empty_state("No device tabs found", "Waiting for first transmission from RockBLOCK webhook.")
        return

    nicknames = get_device_nicknames()

    # ── Sidebar-style controls ──
    col_dev, col_s, col_st, col_e, col_et = st.columns([2, 1, 1, 1, 1])

    with col_dev:
        labels = {tab: format_device_label(tab, nicknames) for tab in tabs}
        selected_tab = st.selectbox(
            "Device",
            tabs,
            format_func=lambda t: labels.get(t, t),
            key="report_device",
        )

    # Load data for selected device
    raw_df = get_device_data(selected_tab)
    if raw_df.empty:
        render_empty_state("No data available", f"Device tab '{selected_tab}' contains no decoded data.")
        return

    df = raw_df.copy()
    time_col = _find_time_column(df)

    # Date range
    if time_col:
        valid_times = df[time_col].dropna()
        if not valid_times.empty:
            data_min = valid_times.min()
            data_max = valid_times.max()
        else:
            data_min = datetime.now()
            data_max = datetime.now()

        # Reset dates when device changes
        if st.session_state.get("_rpt_sel_key") != selected_tab:
            st.session_state["_rpt_sel_key"] = selected_tab
            st.session_state["rpt_start"] = data_min.date()
            st.session_state["rpt_start_t"] = time(0, 0)
            st.session_state["rpt_end"] = data_max.date()
            st.session_state["rpt_end_t"] = time(23, 59)
            # Clear stale PDF
            st.session_state.pop("report_pdf", None)
            st.session_state.pop("report_filename", None)

        with col_s:
            start_d = st.date_input("Start", value=data_min.date(), key="rpt_start")
        with col_st:
            start_t = st.time_input("Start time", value=time(0, 0), key="rpt_start_t")
        with col_e:
            end_d = st.date_input("End", value=data_max.date(), key="rpt_end")
        with col_et:
            end_t = st.time_input("End time", value=time(23, 59), key="rpt_end_t")

        start_dt = datetime.combine(start_d, start_t)
        end_dt = datetime.combine(end_d, end_t)
        mask = ((df[time_col] >= pd.Timestamp(start_dt)) &
                (df[time_col] <= pd.Timestamp(end_dt))) | df[time_col].isna()
        df = df[mask].copy()
    else:
        start_d = date.today()
        end_d = date.today()

    if df.empty:
        render_empty_state("No data in selected range", "Adjust the date range to see data.")
        return

    device_label = labels.get(selected_tab, selected_tab)
    period_str = f"{start_d} ~ {end_d}"

    st.markdown(
        f'<div style="background:#F4F6F8; padding:8px 16px; border-radius:6px; '
        f'margin-bottom:16px; border-left:4px solid {PNNL_BLUE};">'
        f'<strong style="color:{PNNL_BLUE};">{device_label}</strong>'
        f'<span style="color:#5A5A5A; margin-left:16px;">{period_str}'
        f' &middot; {len(df)} packets</span></div>',
        unsafe_allow_html=True,
    )

    # ── 1. Summary KPI Cards ──
    kpis = compute_kpis(df, time_col)

    kpi_cols = st.columns(5)
    with kpi_cols[0]:
        render_kpi_card("Total Packets", str(kpis.get("total_packets", 0)),
                        f"CRC Valid: {kpis.get('crc_rate', 0):.1f}%" if kpis.get("crc_rate") is not None else None)
    with kpi_cols[1]:
        if kpis.get("battery_latest") is not None:
            delta = kpis.get("battery_change", 0)
            sign = "+" if delta >= 0 else ""
            render_kpi_card("Battery", f"{kpis['battery_latest']:.3f}V", f"{sign}{delta:.3f}V change")
        else:
            render_kpi_card("Battery", "N/A")
    with kpi_cols[2]:
        if kpis.get("sst_avg") is not None:
            render_kpi_card("Avg SST", f"{kpis['sst_avg']:.2f}\u00b0C",
                            f"{kpis['sst_min']:.1f} ~ {kpis['sst_max']:.1f}\u00b0C")
        else:
            render_kpi_card("Avg SST", "N/A")
    with kpi_cols[3]:
        if kpis.get("crc_rate") is not None:
            render_kpi_card("CRC Quality", f"{kpis['crc_rate']:.1f}%",
                            f"{kpis.get('crc_invalid', 0)} invalid")
        else:
            render_kpi_card("CRC Quality", "N/A")
    with kpi_cols[4]:
        if kpis.get("coverage_days") is not None:
            render_kpi_card("Coverage", f"{kpis['coverage_days']}d",
                            f"{kpis['packets_per_day']:.1f} packets/day")
        else:
            render_kpi_card("Coverage", "N/A")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── 2. Statistics Table ──
    stats_df = compute_statistics(df)
    if not stats_df.empty:
        st.markdown(
            f'<h3 style="color:{PNNL_BLUE}; margin-bottom:4px;">Statistics</h3>',
            unsafe_allow_html=True,
        )
        st.dataframe(
            stats_df.set_index("Metric"),
            width='stretch',
            height=min(len(stats_df) * 38 + 40, 500),
        )
    st.markdown("<br>", unsafe_allow_html=True)

    # ── 3. Drift Trajectory Map ──
    lat_cols = [c for c in df.columns if "latitude" in c.lower()]
    lon_cols = [c for c in df.columns if "longitude" in c.lower()]

    if lat_cols and lon_cols:
        st.markdown(
            f'<h3 style="color:{PNNL_BLUE}; margin-bottom:4px;">Drift Trajectory</h3>',
            unsafe_allow_html=True,
        )

        m = build_drift_map(
            df,
            basemap="Satellite",
            lat_col=lat_cols[0],
            lon_col=lon_cols[0],
            device_col="Device Tab" if "Device Tab" in df.columns else "Device",
            highlight_latest=True,
        )
        st_folium(m, width=None, height=550, returned_objects=[])

        # Show start/end position details
        valid_gps = df[
            df[lat_cols[0]].notna() & df[lon_cols[0]].notna()
            & ((pd.to_numeric(df[lat_cols[0]], errors="coerce") != 0)
               | (pd.to_numeric(df[lon_cols[0]], errors="coerce") != 0))
        ]
        if not valid_gps.empty:
            first = valid_gps.iloc[0]
            last = valid_gps.iloc[-1]
            pos_c1, pos_c2 = st.columns(2)
            with pos_c1:
                st.markdown(
                    f'<div style="border-left:4px solid {DEVICE_PALETTE[4]}; padding:8px 12px;">'
                    f'<strong style="color:{PNNL_BLUE};">Start Position</strong><br>'
                    f'<span style="font-size:13px; color:#5A5A5A;">'
                    f'Lat: {first[lat_cols[0]]}, Lon: {first[lon_cols[0]]}'
                    f'</span></div>',
                    unsafe_allow_html=True,
                )
            with pos_c2:
                st.markdown(
                    f'<div style="border-left:4px solid {DEVICE_PALETTE[5]}; padding:8px 12px;">'
                    f'<strong style="color:{PNNL_BLUE};">Latest Position</strong><br>'
                    f'<span style="font-size:13px; color:#5A5A5A;">'
                    f'Lat: {last[lat_cols[0]]}, Lon: {last[lon_cols[0]]}'
                    f'</span></div>',
                    unsafe_allow_html=True,
                )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── 4. Sensor Time-Series Plots (2-column grid) ──
    if time_col:
        st.markdown(
            f'<h3 style="color:{PNNL_BLUE}; margin-bottom:4px;">Sensor Plots</h3>',
            unsafe_allow_html=True,
        )

        show_ec_salinity_report = st.toggle(
            "Show EC Conductivity & Salinity (sensor not mounted)",
            value=False,
            key="show_ec_salinity_report",
            help="Toggle on to display EC Conductivity and Salinity plots. "
                 "These sensors are currently not mounted, so values may be missing.",
        )

        battery_nominal_report = st.number_input(
            "Battery nominal voltage (V)",
            min_value=0.0,
            max_value=10.0,
            value=3.2,
            step=0.1,
            format="%.2f",
            key="battery_nominal_v_report",
            help="Reference line drawn on the Battery plot. The y-axis lower "
                 "bound defaults to this value, but auto-zooms out if the "
                 "data goes below it (e.g. FY25 battery chemistry).",
        )

        plot_df = df.dropna(subset=[time_col]).copy()
        chart_figs = []  # Collect for PDF

        # Filter REPORT_SENSORS based on EC/Salinity toggle
        active_sensors = REPORT_SENSORS
        if not show_ec_salinity_report:
            active_sensors = [
                s for s in REPORT_SENSORS
                if s[0] not in ("EC Conductivity", "Salinity")
            ]

        # Build all available sensor charts
        sensor_items = []
        for title, unit, keywords in active_sensors:
            col = _find_sensor_col(plot_df, keywords)
            if col is None:
                continue
            test = pd.to_numeric(plot_df[col], errors="coerce").dropna()
            if test.empty:
                continue
            fig = build_sensor_chart(
                plot_df, time_col, col, title, unit, height=380,
                battery_nominal=battery_nominal_report,
            )
            if fig is not None:
                sensor_items.append((title, fig))
                chart_figs.append((title, fig))

        # Render 2-column grid
        for i in range(0, len(sensor_items), 2):
            cols = st.columns(2)
            with cols[0]:
                st.plotly_chart(sensor_items[i][1], width='stretch')
            if i + 1 < len(sensor_items):
                with cols[1]:
                    st.plotly_chart(sensor_items[i + 1][1], width='stretch')

        # ── 5. Pressure vs SST Scatter ──
        pres_col = _find_sensor_col(plot_df, ["pressure"])
        sst_col = _find_sensor_col(plot_df, ["sst", "ocean temp"])
        scatter_fig = None

        if pres_col and sst_col:
            st.markdown(
                f'<h3 style="color:{PNNL_BLUE}; margin-bottom:4px;">Pressure vs SST</h3>',
                unsafe_allow_html=True,
            )
            scatter_fig = build_scatter_chart(
                plot_df, sst_col, pres_col,
                "Pressure vs SST", "\u00b0C", "psi",
            )
            if scatter_fig is not None:
                st.plotly_chart(scatter_fig, width='stretch')
    else:
        chart_figs = []
        scatter_fig = None

    st.markdown("<br>", unsafe_allow_html=True)

    # ── PDF Download ──
    st.markdown(
        f'<h3 style="color:{PNNL_BLUE}; margin-bottom:4px;">Export</h3>',
        unsafe_allow_html=True,
    )

    if st.button("Generate PDF Report", type="primary"):
        with st.spinner("Generating PDF... (exporting charts)"):
            try:
                # Try real map tiles first, fall back to XY scatter
                trajectory_png = None
                trajectory_fig = None
                if lat_cols and lon_cols:
                    trajectory_png = build_trajectory_image(
                        df, lat_cols[0], lon_cols[0],
                        title=f"Drift Trajectory \u2014 {device_label}",
                    )
                    if trajectory_png is None:
                        trajectory_fig = build_trajectory_chart_fallback(
                            df, lat_cols[0], lon_cols[0],
                            title=f"Drift Trajectory \u2014 {device_label}",
                        )

                pdf_bytes = generate_report_pdf(
                    df=df,
                    device_name=device_label,
                    period_start=str(start_d),
                    period_end=str(end_d),
                    chart_figures=chart_figs,
                    trajectory_png=trajectory_png,
                    trajectory_fig=trajectory_fig,
                    scatter_fig=scatter_fig,
                )
                st.session_state["report_pdf"] = pdf_bytes
                st.session_state["report_filename"] = (
                    f"SPAO_Report_{selected_tab}_{start_d}_{end_d}.pdf"
                )
                st.success("PDF generated successfully!")
            except Exception as e:
                render_error("PDF Generation Failed", str(e))

    if st.session_state.get("report_pdf"):
        st.download_button(
            label="Download PDF",
            data=st.session_state["report_pdf"],
            file_name=st.session_state.get("report_filename", "report.pdf"),
            mime="application/pdf",
        )


render_report()
render_footer()
