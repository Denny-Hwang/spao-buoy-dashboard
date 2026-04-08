"""
Page 5: Analytics — Drift maps, sensor plots, and custom charts with PNNL branding.
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import date

st.set_page_config(page_title="Analytics", page_icon="🔬", layout="wide")

from utils.theme import (  # noqa: E402
    render_header, render_footer, render_empty_state, render_error,
    PNNL_BLUE, SENSOR_COLORS, DEVICE_PALETTE,
)

render_header()

_errors = []
try:
    from utils.sheets_client import (
        list_device_tabs, get_device_data,
        get_device_ids, get_device_column,
    )
except Exception as e:
    _errors.append(f"sheets_client: {type(e).__name__}: {e}")

try:
    from utils.map_utils import build_drift_map, BASEMAPS
except Exception as e:
    _errors.append(f"map_utils: {type(e).__name__}: {e}")

try:
    from utils.plot_utils import (
        make_time_series, make_scatter, make_3d_scatter, apply_plot_style,
        LINE_WIDTH, MARKER_SIZE, PLOT_HEIGHT,
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

SHEETS_AVAILABLE = len(_errors) == 0


def _find_time_col(df: pd.DataFrame) -> str | None:
    """Find and parse the best time column."""
    candidates = [c for c in df.columns if "time" in c.lower() or "timestamp" in c.lower() or "date" in c.lower()]
    if not candidates:
        return None
    time_col = candidates[0]
    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    return time_col


def _get_sensor_color(sensor_name: str, fallback_idx: int = 0) -> str:
    """Get color from SENSOR_COLORS map, with fallback to DEVICE_PALETTE."""
    for key, color in SENSOR_COLORS.items():
        if key.lower() in sensor_name.lower():
            return color
    return DEVICE_PALETTE[fallback_idx % len(DEVICE_PALETTE)]


def render_analytics():
    if not SHEETS_AVAILABLE:
        render_error(
            "Cannot load required modules",
            "Some dependencies failed to load. Check your installation.",
        )
        for err in _errors:
            st.error(err)
        return

    st.markdown(
        f'<h1 style="color:{PNNL_BLUE}; margin-top:0;">Analytics</h1>',
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

    all_df = pd.concat(frames, ignore_index=True)

    # Determine device column and IDs
    dev_col = get_device_column(all_df) or "Device Tab"
    device_ids = get_device_ids(all_df)
    if not device_ids:
        device_ids = tabs
        dev_col = "Device Tab"

    selected_devices = st.multiselect("Select Devices", device_ids, default=device_ids)

    if not selected_devices:
        st.info("Select at least one device.")
        return

    all_df = all_df[all_df[dev_col].isin(selected_devices)].copy()
    if all_df.empty:
        render_empty_state("No data for selected devices", "Try selecting different devices.")
        return

    # Parse time column
    time_col = _find_time_col(all_df)

    # Date range filter
    if time_col:
        valid = all_df[time_col].dropna()
        if not valid.empty:
            data_min = valid.min().date()
            data_max = valid.max().date()
            c1, c2 = st.columns(2)
            with c1:
                start = st.date_input("Start", value=data_min, key="viz_start")
            with c2:
                end = st.date_input("End", value=data_max, key="viz_end")
            mask = all_df[time_col].dt.date.between(start, end) | all_df[time_col].isna()
            all_df = all_df[mask]

    if all_df.empty:
        render_empty_state("No data in selected range", "Adjust the date range to see data.")
        return

    # Tabs
    tab_map, tab_sensor, tab_custom = st.tabs(["Drift Map", "Sensor Plots", "Custom Plot"])

    # --- Drift Map with split layout ---
    with tab_map:
        map_col, detail_col = st.columns([3, 2])

        with map_col:
            basemap = st.selectbox("Basemap", list(BASEMAPS.keys()), index=0)

            lat_cols = [c for c in all_df.columns if "latitude" in c.lower()]
            lon_cols = [c for c in all_df.columns if "longitude" in c.lower()]

            if lat_cols and lon_cols:
                m = build_drift_map(
                    all_df,
                    basemap=basemap,
                    lat_col=lat_cols[0],
                    lon_col=lon_cols[0],
                    device_col=dev_col,
                    highlight_latest=True,
                )
                st_folium(m, width=None, height=600, returned_objects=[])
            else:
                st.warning("No GPS columns found in the data.")

        with detail_col:
            st.markdown(f'<h4 style="color:{PNNL_BLUE};">Latest Position Details</h4>', unsafe_allow_html=True)

            if lat_cols and lon_cols:
                for i, device in enumerate(selected_devices):
                    device_df = all_df[all_df[dev_col] == device]
                    if device_df.empty:
                        continue

                    lat_c = lat_cols[0]
                    lon_c = lon_cols[0]
                    valid_gps = device_df[
                        device_df[lat_c].notna() & device_df[lon_c].notna()
                        & ((device_df[lat_c] != 0) | (device_df[lon_c] != 0))
                    ]
                    if valid_gps.empty:
                        continue

                    last = valid_gps.iloc[-1]
                    dev_color = DEVICE_PALETTE[i % len(DEVICE_PALETTE)]

                    st.markdown(
                        f'<div style="border-left:4px solid {dev_color}; padding:8px 12px; margin-bottom:12px;">'
                        f'<strong style="color:{PNNL_BLUE};">{device}</strong><br>'
                        f'<span style="font-size:13px; color:#5A5A5A;">'
                        f'Lat: {last[lat_c]:.4f}, Lon: {last[lon_c]:.4f}',
                        unsafe_allow_html=True,
                    )

                    # Show key sensor values
                    detail_parts = []
                    batt_cols = [c for c in device_df.columns if "battery" in c.lower()]
                    if batt_cols:
                        bv = pd.to_numeric(last.get(batt_cols[0], None), errors="coerce")
                        if pd.notna(bv):
                            detail_parts.append(f"Battery: {bv:.3f}V")
                    sst_cols = [c for c in device_df.columns if "sst" in c.lower()]
                    if sst_cols:
                        sv = pd.to_numeric(last.get(sst_cols[0], None), errors="coerce")
                        if pd.notna(sv):
                            detail_parts.append(f"SST: {sv:.2f}&deg;C")
                    pres_cols = [c for c in device_df.columns if "pressure" in c.lower()]
                    if pres_cols:
                        pv = pd.to_numeric(last.get(pres_cols[0], None), errors="coerce")
                        if pd.notna(pv):
                            detail_parts.append(f"Pressure: {pv:.1f} psi")

                    if detail_parts:
                        st.markdown(
                            '<span style="font-size:13px; color:#5A5A5A;">'
                            + " &middot; ".join(detail_parts) + '</span>',
                            unsafe_allow_html=True,
                        )
                    st.markdown('</div>', unsafe_allow_html=True)

    # --- Sensor Plots ---
    with tab_sensor:
        if not time_col:
            st.warning("No time column found for time-series plots.")
        else:
            plot_base = all_df.dropna(subset=[time_col])

            _skip = {"Device", "Device Tab", "IMEI"}

            sensor_configs = [
                ("Battery", "V", ["battery"]),
                ("SST", "\u00b0C", ["sst", "ocean temp"]),
                ("Pressure", "psi", ["pressure"]),
                ("Internal Temp", "\u00b0C", ["internal temp", "int temp"]),
                ("Humidity", "%RH", ["humidity"]),
                ("TENG Current Avg", "mA", ["teng current", "teng avg"]),
                ("EC Conductivity", "mS/cm", ["ec conductivity"]),
                ("Salinity", "PSS-78", ["salinity"]),
                ("Prev Oper Time", "s", ["prev oper time"]),
                ("SuperCap Voltage", "V", ["supercap"]),
            ]

            for title, unit, keywords in sensor_configs:
                matching = [c for c in plot_base.columns
                            if any(kw in c.lower() for kw in keywords)
                            and c not in _skip
                            and not c.lower().startswith("prev")]
                if matching:
                    y_col = matching[0]
                    plot_df = plot_base.copy()
                    plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
                    plot_df = plot_df.dropna(subset=[y_col])
                    if plot_df.empty:
                        continue

                    # Use SENSOR_COLORS for consistent coloring
                    fig = go.Figure()
                    devices = plot_df[dev_col].unique()
                    for di, device in enumerate(devices):
                        ddf = plot_df[plot_df[dev_col] == device]
                        color = DEVICE_PALETTE[di % len(DEVICE_PALETTE)]
                        fig.add_trace(go.Scatter(
                            x=ddf[time_col], y=ddf[y_col],
                            mode="lines+markers",
                            name=str(device),
                            line=dict(width=LINE_WIDTH, color=color),
                            marker=dict(size=MARKER_SIZE),
                        ))

                    sensor_color = _get_sensor_color(title)
                    y_label = f"{y_col} ({unit})" if unit else y_col
                    apply_plot_style(fig, title=title, x_title=time_col, y_title=y_label)
                    st.plotly_chart(fig, use_container_width=True)

            pres_cols = [c for c in plot_base.columns if "pressure" in c.lower()]
            sst_cols = [c for c in plot_base.columns if "sst" in c.lower() or "ocean temp" in c.lower()]
            if pres_cols and sst_cols:
                st.markdown(f'<h4 style="color:{PNNL_BLUE};">Pressure vs SST</h4>', unsafe_allow_html=True)
                fig = make_scatter(
                    plot_base,
                    x_col=sst_cols[0],
                    y_col=pres_cols[0],
                    title="Pressure vs SST",
                    x_unit="\u00b0C",
                    y_unit="psi",
                    color_col=dev_col,
                    trendline=True,
                )
                st.plotly_chart(fig, use_container_width=True)

            hum_cols = [c for c in plot_base.columns if "humidity" in c.lower()]
            temp_cols = [c for c in plot_base.columns if "internal temp" in c.lower()]
            if hum_cols and temp_cols:
                st.markdown(f'<h4 style="color:{PNNL_BLUE};">Humidity & Dewpoint</h4>', unsafe_allow_html=True)
                plot_df = plot_base.copy()
                plot_df[hum_cols[0]] = pd.to_numeric(plot_df[hum_cols[0]], errors="coerce")
                plot_df[temp_cols[0]] = pd.to_numeric(plot_df[temp_cols[0]], errors="coerce")
                plot_df = plot_df.dropna(subset=[hum_cols[0], temp_cols[0]])

                if not plot_df.empty:
                    a, b = 17.27, 237.7
                    T = plot_df[temp_cols[0]]
                    RH = plot_df[hum_cols[0]].clip(lower=0.1)
                    alpha = (a * T) / (b + T) + np.log(RH / 100)
                    plot_df["Dewpoint"] = (b * alpha) / (a - alpha)

                    fig = go.Figure()
                    devices = plot_df[dev_col].unique()
                    for i, device in enumerate(devices):
                        ddf = plot_df[plot_df[dev_col] == device]
                        hum_color = DEVICE_PALETTE[i % len(DEVICE_PALETTE)]
                        dew_color = DEVICE_PALETTE[(i + 1) % len(DEVICE_PALETTE)]
                        fig.add_trace(go.Scatter(
                            x=ddf[time_col], y=ddf[hum_cols[0]],
                            mode="lines+markers", name=f"Humidity \u2013 {device}",
                            line=dict(width=LINE_WIDTH, color=hum_color),
                            marker=dict(size=MARKER_SIZE),
                            yaxis="y",
                        ))
                        fig.add_trace(go.Scatter(
                            x=ddf[time_col], y=ddf["Dewpoint"],
                            mode="lines+markers", name=f"Dewpoint \u2013 {device}",
                            line=dict(width=LINE_WIDTH, color=dew_color, dash="dot"),
                            marker=dict(size=MARKER_SIZE),
                            yaxis="y2",
                        ))
                    apply_plot_style(fig, title="Humidity & Dewpoint", x_title=time_col, y_title="Humidity (%RH)")
                    fig.update_layout(
                        yaxis2=dict(
                            title="Dewpoint (\u00b0C)",
                            overlaying="y",
                            side="right",
                            showgrid=False,
                        ),
                    )
                    st.plotly_chart(fig, use_container_width=True)

    # --- Custom Plot ---
    with tab_custom:
        numeric_cols = all_df.select_dtypes(include="number").columns.tolist()
        all_cols = all_df.columns.tolist()

        if not numeric_cols:
            st.warning("No numeric columns available for plotting.")
        else:
            c1, c2, c3 = st.columns(3)
            with c1:
                x_var = st.selectbox("X-axis", all_cols, key="custom_x")
            with c2:
                y_var = st.selectbox("Y-axis", numeric_cols, key="custom_y",
                                     index=min(1, len(numeric_cols) - 1))
            with c3:
                z_var = st.selectbox("Z-axis (3D only)", ["None"] + numeric_cols, key="custom_z")

            c4, c5 = st.columns(2)
            with c4:
                plot_type = st.selectbox("Plot Type", ["Line", "Scatter", "X-Y with Trendline", "3D Scatter"])
            with c5:
                color_options = ["None", dev_col] + [c for c in numeric_cols if c != dev_col]
                color_var = st.selectbox("Color By", color_options, key="custom_color")

            color_col = color_var if color_var != "None" else None

            if st.button("Generate Plot", type="primary"):
                plot_df = all_df.dropna(subset=[x_var, y_var])

                if plot_type == "Line":
                    fig = make_time_series(plot_df, x_var, y_var, color_col=color_col)
                    st.plotly_chart(fig, use_container_width=True)
                elif plot_type == "Scatter":
                    fig = make_scatter(plot_df, x_var, y_var, color_col=color_col)
                    st.plotly_chart(fig, use_container_width=True)
                elif plot_type == "X-Y with Trendline":
                    fig = make_scatter(plot_df, x_var, y_var, color_col=color_col, trendline=True)
                    st.plotly_chart(fig, use_container_width=True)
                elif plot_type == "3D Scatter":
                    if z_var == "None":
                        st.warning("Select a Z-axis variable for 3D scatter.")
                    else:
                        plot_df = plot_df.dropna(subset=[z_var])
                        fig = make_3d_scatter(plot_df, x_var, y_var, z_var, color_col=color_col)
                        st.plotly_chart(fig, use_container_width=True)


render_analytics()
render_footer()
