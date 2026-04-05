"""
Page 5: Visualization — Drift maps and sensor plots with per-device filtering.
"""

import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Visualization", page_icon="🗺️", layout="wide")
st.title("🗺️ Visualization")

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
        make_time_series, make_scatter, make_3d_scatter, apply_plot_style, COLORS,
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


def render_visualization():
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

    all_df = pd.concat(frames, ignore_index=True)

    # Determine device column and IDs
    dev_col = get_device_column(all_df) or "Device Tab"
    device_ids = get_device_ids(all_df)
    if not device_ids:
        device_ids = tabs
        dev_col = "Device Tab"

    # Sidebar: device selection by actual Device ID
    st.sidebar.subheader("Data Source")
    selected_devices = st.sidebar.multiselect("Devices", device_ids, default=device_ids)

    if not selected_devices:
        st.info("Select at least one device.")
        return

    # Filter by selected devices
    all_df = all_df[all_df[dev_col].isin(selected_devices)].copy()
    if all_df.empty:
        st.info("No data for selected devices.")
        return

    # Parse time column
    time_col = _find_time_col(all_df)

    # Sidebar: date range filter
    if time_col:
        valid = all_df[time_col].dropna()
        if not valid.empty:
            c1, c2 = st.sidebar.columns(2)
            with c1:
                start = st.date_input("Start", value=valid.min().date(), key="viz_start")
            with c2:
                end = st.date_input("End", value=valid.max().date(), key="viz_end")
            mask = all_df[time_col].dt.date.between(start, end) | all_df[time_col].isna()
            all_df = all_df[mask]

    if all_df.empty:
        st.info("No data in selected date range.")
        return

    # Tabs
    tab_map, tab_sensor, tab_custom = st.tabs(["Drift Map", "Sensor Plots", "Custom Plot"])

    # --- Drift Map ---
    with tab_map:
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

    # --- Sensor Plots ---
    with tab_sensor:
        if not time_col:
            st.warning("No time column found for time-series plots.")
        else:
            plot_base = all_df.dropna(subset=[time_col])

            sensor_configs = [
                ("Battery", "V", ["battery"]),
                ("SST", "°C", ["sst", "ocean temp"]),
                ("Pressure", "psi", ["pressure"]),
                ("Internal Temp", "°C", ["internal temp", "int temp"]),
                ("Humidity", "%RH", ["humidity"]),
                ("TENG Current Avg", "mA", ["teng current", "teng avg"]),
            ]

            for title, unit, keywords in sensor_configs:
                matching = [c for c in plot_base.columns
                            if any(kw in c.lower() for kw in keywords)
                            and c not in ("Device", "Device Tab", "IMEI")]
                if matching:
                    y_col = matching[0]
                    plot_df = plot_base.copy()
                    plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
                    plot_df = plot_df.dropna(subset=[y_col])
                    if plot_df.empty:
                        continue
                    fig = make_time_series(
                        plot_df,
                        x_col=time_col,
                        y_col=y_col,
                        title=title,
                        y_unit=unit,
                        color_col=dev_col,
                    )
                    st.plotly_chart(fig, use_container_width=True)

            pres_cols = [c for c in plot_base.columns if "pressure" in c.lower()]
            sst_cols = [c for c in plot_base.columns if "sst" in c.lower() or "ocean temp" in c.lower()]
            if pres_cols and sst_cols:
                st.subheader("Pressure vs SST")
                fig = make_scatter(
                    plot_base,
                    x_col=sst_cols[0],
                    y_col=pres_cols[0],
                    title="Pressure vs SST",
                    x_unit="°C",
                    y_unit="psi",
                    color_col=dev_col,
                    trendline=True,
                )
                st.plotly_chart(fig, use_container_width=True)

            hum_cols = [c for c in plot_base.columns if "humidity" in c.lower()]
            temp_cols = [c for c in plot_base.columns if "internal temp" in c.lower()]
            if hum_cols and temp_cols:
                st.subheader("Humidity & Dewpoint")
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
                    fig.add_trace(go.Scatter(
                        x=plot_df[time_col], y=plot_df[hum_cols[0]],
                        mode="lines+markers", name="Humidity (%RH)",
                        line=dict(width=LINE_WIDTH, color=COLORS[0]),
                        marker=dict(size=MARKER_SIZE),
                        yaxis="y",
                    ))
                    fig.add_trace(go.Scatter(
                        x=plot_df[time_col], y=plot_df["Dewpoint"],
                        mode="lines+markers", name="Dewpoint (°C)",
                        line=dict(width=LINE_WIDTH, color=COLORS[1]),
                        marker=dict(size=MARKER_SIZE),
                        yaxis="y2",
                    ))
                    apply_plot_style(fig, title="Humidity & Dewpoint", x_title=time_col, y_title="Humidity (%RH)")
                    fig.update_layout(
                        yaxis2=dict(
                            title="Dewpoint (°C)",
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


render_visualization()

st.divider()
st.caption("SPAO Buoy Dashboard — Pacific Northwest National Laboratory")
