"""
Page 5: Analytics — Drift maps, sensor plots, and custom charts with PNNL branding.
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, time, datetime

st.set_page_config(page_title="Analytics", page_icon="🔬", layout="wide")

from utils.theme import (  # noqa: E402
    render_header, render_footer, render_empty_state, render_error,
    render_sidebar, inject_custom_css,
    PNNL_BLUE, SENSOR_COLORS, DEVICE_PALETTE,
)

inject_custom_css()
render_sidebar()
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


def _find_col_by_keywords(df: pd.DataFrame, keywords: list[str]) -> str | None:
    """Find the first column matching any of the given keywords (case-insensitive)."""
    for c in df.columns:
        cl = c.lower()
        if cl.startswith("prev"):
            continue
        if any(kw in cl for kw in keywords):
            return c
    return None


def _render_multi_y_plot(
    df: pd.DataFrame,
    x_var: str,
    y_vars: list[str],
    plot_type: str,
    color_col: str | None,
    dev_col: str,
    dual_y: bool,
) -> None:
    """Render a Line / Scatter / Trendline plot with one or more Y-axis variables.

    When ``dual_y`` is True and exactly (or more than) two Y variables are given,
    subsequent variables after the first are drawn on a secondary right axis.
    """
    plot_df = df.dropna(subset=[x_var] + list(y_vars)).copy()
    if plot_df.empty:
        st.warning("No data available for the selected variables.")
        return

    mode = "lines+markers" if plot_type == "Line" else "markers"
    use_dual = dual_y and len(y_vars) >= 2

    fig = go.Figure()

    # Determine per-series coloring
    def _series_color(idx: int, y_name: str) -> str:
        sensor = _get_sensor_color(y_name, fallback_idx=idx)
        return sensor or DEVICE_PALETTE[idx % len(DEVICE_PALETTE)]

    def _add_series(xvals, yvals, name, color, yaxis):
        fig.add_trace(go.Scatter(
            x=xvals, y=yvals,
            mode=mode,
            name=name,
            line=dict(width=LINE_WIDTH, color=color),
            marker=dict(size=MARKER_SIZE, color=color),
            yaxis=yaxis,
        ))

    if color_col and color_col in plot_df.columns and color_col != dev_col:
        # Color-by numeric not supported with multi-y in a clean way; fall back to device.
        color_col = dev_col if dev_col in plot_df.columns else None

    groups = None
    if color_col and color_col in plot_df.columns:
        groups = list(plot_df.groupby(color_col))

    for yi, y_var in enumerate(y_vars):
        yaxis = "y2" if (use_dual and yi >= 1) else "y"
        if groups:
            for gi, (gname, gdf) in enumerate(groups):
                label = f"{y_var} \u2013 {gname}" if len(y_vars) > 1 else f"{gname}"
                color = DEVICE_PALETTE[(gi + yi * 3) % len(DEVICE_PALETTE)]
                _add_series(gdf[x_var], gdf[y_var], label, color, yaxis)
        else:
            color = _series_color(yi, y_var)
            _add_series(plot_df[x_var], plot_df[y_var], y_var, color, yaxis)

    # Optional trendline (simple linear on combined data for each y var)
    if plot_type == "X-Y with Trendline":
        x_num = pd.to_numeric(plot_df[x_var], errors="coerce")
        for yi, y_var in enumerate(y_vars):
            y_num = pd.to_numeric(plot_df[y_var], errors="coerce")
            mask = x_num.notna() & y_num.notna()
            if mask.sum() > 1:
                coeffs = np.polyfit(x_num[mask], y_num[mask], 1)
                x_range = np.linspace(x_num[mask].min(), x_num[mask].max(), 100)
                yaxis = "y2" if (use_dual and yi >= 1) else "y"
                fig.add_trace(go.Scatter(
                    x=x_range, y=np.polyval(coeffs, x_range),
                    mode="lines",
                    name=f"{y_var} trend (y={coeffs[0]:.4f}x+{coeffs[1]:.4f})",
                    line=dict(width=2, dash="dash", color="#94a3b8"),
                    yaxis=yaxis,
                ))

    title = " & ".join(y_vars) + f" vs {x_var}"
    y_title_primary = y_vars[0]
    apply_plot_style(fig, title=title, x_title=x_var, y_title=y_title_primary)

    if use_dual:
        secondary_names = ", ".join(y_vars[1:])
        fig.update_layout(
            yaxis2=dict(
                title=secondary_names,
                overlaying="y",
                side="right",
                showgrid=False,
            ),
        )

    st.plotly_chart(fig, width="stretch")


def _render_binned_battery_temp(
    df: pd.DataFrame,
    time_col: str | None,
    dev_col: str,
) -> None:
    """Render the Battery vs Internal Temperature Binned View chart."""
    batt_col = _find_col_by_keywords(df, ["battery"])
    temp_col = _find_col_by_keywords(df, ["internal temp", "int temp"])

    if batt_col is None or temp_col is None:
        st.warning(
            "Could not find Battery and/or Internal Temperature columns in the data."
        )
        return

    work = df.copy()
    work[batt_col] = pd.to_numeric(work[batt_col], errors="coerce")
    work[temp_col] = pd.to_numeric(work[temp_col], errors="coerce")
    if time_col and time_col in work.columns:
        work[time_col] = pd.to_datetime(work[time_col], errors="coerce")

    # ── Controls: date range + r toggle ──
    ctrl_cols = st.columns([1, 1, 1, 1, 1])
    if time_col and work[time_col].notna().any():
        data_min = work[time_col].min()
        data_max = work[time_col].max()
        with ctrl_cols[0]:
            bstart = st.date_input(
                "Start", value=data_min.date(), key="binned_start"
            )
        with ctrl_cols[1]:
            bstart_t = st.time_input(
                "Start time", value=time(0, 0), key="binned_start_t"
            )
        with ctrl_cols[2]:
            bend = st.date_input(
                "End", value=data_max.date(), key="binned_end"
            )
        with ctrl_cols[3]:
            bend_t = st.time_input(
                "End time", value=time(23, 59), key="binned_end_t"
            )
        start_dt = datetime.combine(bstart, bstart_t)
        end_dt = datetime.combine(bend, bend_t)
        mask = (work[time_col] >= pd.Timestamp(start_dt)) & (
            work[time_col] <= pd.Timestamp(end_dt)
        )
        work = work[mask]
    else:
        st.info("No time column available — using all data.")

    with ctrl_cols[4]:
        show_r = st.toggle("Show Pearson r", value=True, key="binned_show_r")

    work = work.dropna(subset=[batt_col, temp_col])
    if work.empty:
        st.warning("No Battery / Internal Temperature data in the selected range.")
        return

    # ── 2°C bins ──
    x_min = float(np.floor(work[temp_col].min() / 2.0) * 2.0)
    x_max = float(np.ceil(work[temp_col].max() / 2.0) * 2.0)
    if x_max <= x_min:
        x_max = x_min + 2.0
    bins = np.arange(x_min, x_max + 2.0, 2.0)

    work = work.copy()
    work["_bin_idx"] = pd.cut(
        work[temp_col], bins=bins, include_lowest=True, labels=False
    )
    grouped = (
        work.dropna(subset=["_bin_idx"])
        .groupby("_bin_idx")
        .agg(
            y_mean=(batt_col, "mean"),
            y_std=(batt_col, "std"),
            n=(batt_col, "count"),
        )
        .reset_index()
    )
    # Bin centers
    grouped["x_center"] = grouped["_bin_idx"].apply(
        lambda idx: (bins[int(idx)] + bins[int(idx) + 1]) / 2.0
    )

    # Drop bins with n <= 10
    valid = grouped[grouped["n"] > 10].copy()
    if valid.empty:
        st.warning(
            "No temperature bins have more than 10 samples. "
            "Try widening the date range."
        )
        return

    # Replace NaN std (single-sample bins shouldn't happen here since n>10, but be safe)
    valid["y_std"] = valid["y_std"].fillna(0.0)

    # ── Weighted linear fit on bin means ──
    xs = valid["x_center"].values.astype(float)
    ys = valid["y_mean"].values.astype(float)
    ws = valid["n"].values.astype(float)
    slope, intercept = np.polyfit(xs, ys, 1, w=ws)

    # ── Pearson r on raw data ──
    r_val = float(work[temp_col].corr(work[batt_col]))

    # ── Build plot ──
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=xs,
        y=ys,
        error_y=dict(
            type="data",
            array=valid["y_std"].values,
            visible=True,
            thickness=1.5,
            width=6,
            color="#003E6B",
        ),
        mode="markers+text",
        marker=dict(size=11, color="#003E6B",
                    line=dict(width=1, color="#003E6B")),
        text=[f"n={int(n)}" for n in valid["n"]],
        textposition="top center",
        textfont=dict(size=11, color="#334155"),
        name="Bin mean \u00b1 1\u03c3",
    ))

    x_fit = np.linspace(xs.min(), xs.max(), 100)
    y_fit = slope * x_fit + intercept
    fig.add_trace(go.Scatter(
        x=x_fit,
        y=y_fit,
        mode="lines",
        line=dict(width=2, dash="dash", color="#C62828"),
        name=f"Linear fit: {slope * 1000:.2f} mV/\u00b0C",
    ))

    apply_plot_style(
        fig,
        title="Battery vs Internal Temperature \u2014 Binned View",
        x_title="Internal Temperature (\u00b0C)",
        y_title="Battery Voltage (V)",
    )
    fig.update_yaxes(tickformat=".3f")
    fig.update_layout(legend=dict(
        orientation="v", yanchor="bottom", y=0.02, xanchor="right", x=0.98,
        bgcolor="rgba(255,255,255,0.8)",
    ))

    if show_r:
        sign = "+" if r_val >= 0 else "-"
        fig.add_annotation(
            xref="paper", yref="paper",
            x=0.02, y=0.98,
            xanchor="left", yanchor="top",
            text=f"<b>r = {sign}{abs(r_val):.3f}</b>",
            showarrow=False,
            font=dict(size=15, color="#C62828"),
            bordercolor="#C62828",
            borderwidth=2,
            borderpad=6,
            bgcolor="white",
        )

    st.plotly_chart(fig, width="stretch")


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
            data_min = valid.min()
            data_max = valid.max()

            # Reset dates when device selection changes
            _sel_key = str(sorted(selected_devices))
            if st.session_state.get("_viz_sel_key") != _sel_key:
                st.session_state["_viz_sel_key"] = _sel_key
                st.session_state["viz_start"] = data_min.date()
                st.session_state["viz_start_time"] = time(0, 0)
                st.session_state["viz_end"] = data_max.date()
                st.session_state["viz_end_time"] = time(23, 59)

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                start = st.date_input("Start", value=data_min.date(), key="viz_start")
            with c2:
                start_t = st.time_input("Start time", value=time(0, 0), key="viz_start_time")
            with c3:
                end = st.date_input("End", value=data_max.date(), key="viz_end")
            with c4:
                end_t = st.time_input("End time", value=time(23, 59), key="viz_end_time")
            start_dt = datetime.combine(start, start_t)
            end_dt = datetime.combine(end, end_t)
            mask = (all_df[time_col] >= pd.Timestamp(start_dt)) & (all_df[time_col] <= pd.Timestamp(end_dt)) | all_df[time_col].isna()
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

            show_ec_salinity = st.toggle(
                "Show EC Conductivity & Salinity (sensor not mounted)",
                value=False,
                key="show_ec_salinity_analytics",
                help="Toggle on to display EC Conductivity and Salinity plots. "
                     "These sensors are currently not mounted, so values may be missing.",
            )

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

            if not show_ec_salinity:
                sensor_configs = [
                    cfg for cfg in sensor_configs
                    if cfg[0] not in ("EC Conductivity", "Salinity")
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

                    # Battery-specific styling: show nominal 3.2 V reference
                    # and force y-axis minimum to 3.2 V by default (avoid over-zoom).
                    if title == "Battery":
                        y_max = float(plot_df[y_col].max())
                        fig.update_yaxes(range=[3.2, max(y_max + 0.02, 3.4)])
                        fig.add_hline(
                            y=3.2,
                            line_dash="dash",
                            line_color="#C62828",
                            line_width=1.5,
                            annotation_text="Nominal 3.2 V",
                            annotation_position="bottom right",
                            annotation_font_size=11,
                            annotation_font_color="#C62828",
                        )

                    st.plotly_chart(fig, width="stretch")

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
                st.plotly_chart(fig, width="stretch")

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
                    st.plotly_chart(fig, width="stretch")

    # --- Custom Plot ---
    with tab_custom:
        # Metadata fields that are not meaningful to chart.
        _custom_skip = {
            "Device", "Device Tab", "IMEI", "Transmit Time",
            "MOMSN", "Packet Ver", "Bytes", "CRC Valid", "Raw Hex",
            "Notes", "Decode Error", "Warning",
        }

        numeric_cols = [
            c for c in all_df.select_dtypes(include="number").columns.tolist()
            if c not in _custom_skip
        ]
        all_cols = [c for c in all_df.columns.tolist() if c not in _custom_skip]

        BINNED_PLOT = "Battery vs Internal Temperature \u2014 Binned View"
        plot_types = [
            "Line", "Scatter", "X-Y with Trendline", "3D Scatter", BINNED_PLOT,
        ]

        if not numeric_cols:
            st.warning("No numeric columns available for plotting.")
        else:
            plot_type = st.selectbox("Plot Type", plot_types, key="custom_plot_type")

            if plot_type == BINNED_PLOT:
                _render_binned_battery_temp(all_df, time_col, dev_col)
            else:
                c1, c2, c3 = st.columns(3)
                with c1:
                    x_var = st.selectbox("X-axis", all_cols, key="custom_x")
                with c2:
                    default_y = numeric_cols[:1] if numeric_cols else []
                    y_vars = st.multiselect(
                        "Y-axis (select one or more)",
                        numeric_cols,
                        default=default_y,
                        key="custom_y_multi",
                    )
                with c3:
                    z_var = st.selectbox(
                        "Z-axis (3D only)", ["None"] + numeric_cols, key="custom_z"
                    )

                c4, c5, c6 = st.columns(3)
                with c4:
                    dual_y = st.toggle(
                        "Dual Y-axis",
                        value=False,
                        key="custom_dual_y",
                        help="When enabled and you select 2+ Y variables, the "
                             "second variable is drawn on a secondary right-hand axis.",
                    )
                with c5:
                    color_options = ["None", dev_col] + [c for c in numeric_cols if c != dev_col]
                    color_var = st.selectbox("Color By", color_options, key="custom_color")
                with c6:
                    st.write("")  # spacer

                color_col = color_var if color_var != "None" else None

                if st.button("Generate Plot", type="primary"):
                    if not y_vars:
                        st.warning("Select at least one Y-axis variable.")
                    elif plot_type == "3D Scatter":
                        if z_var == "None":
                            st.warning("Select a Z-axis variable for 3D scatter.")
                        else:
                            y_var = y_vars[0]
                            plot_df = all_df.dropna(subset=[x_var, y_var, z_var])
                            fig = make_3d_scatter(
                                plot_df, x_var, y_var, z_var, color_col=color_col
                            )
                            st.plotly_chart(fig, width="stretch")
                    else:
                        _render_multi_y_plot(
                            all_df, x_var, y_vars, plot_type,
                            color_col=color_col, dev_col=dev_col,
                            dual_y=dual_y,
                        )


render_analytics()
render_footer()
