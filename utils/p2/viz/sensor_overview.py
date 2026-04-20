"""Phase 2 "Sensor Overview" panel builder.

Renders Phase 1-style sensor plots (Battery, SST_buoy, Pressure, …)
together with the 7 Phase 2 enriched groups (Wave, Wind, Atmosphere,
SST products, Ocean currents, Sea ice, ENRICH_FLAG coverage) so that a
buoy operator can see everything on one page.

All figures are device-colored via ``utils.plot_utils.COLORS`` to match
the Phase 1 Analytics page. Groups whose source columns are entirely
absent or all-NaN for the current selection are skipped with a short
caption rather than rendering empty axes.

This module is consumed by page 8 (SST Validation → Sensor Overview tab)
but is written as a pure function so new pages can reuse it unchanged.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

try:
    import plotly.graph_objects as go  # type: ignore
except Exception:  # pragma: no cover
    go = None  # type: ignore[assignment]

from utils.plot_utils import (
    LINE_WIDTH,
    MARKER_SIZE,
    COLORS,
    apply_plot_style,
)


# ──────────────────────────────────────────────────────────────────────
# Phase 1 sensor definitions — mirrors pages/5_📈_Analytics.py so users
# see the same "base telemetry" plots on the SST page.
# ──────────────────────────────────────────────────────────────────────
PHASE1_SENSORS: list[tuple[str, str, tuple[str, ...]]] = [
    ("Battery",          "V",      ("battery",)),
    ("SST (buoy)",       "°C",     ("sst", "ocean temp", "water temp")),
    ("Pressure",         "psi",    ("pressure",)),
    ("Internal Temp",    "°C",     ("internal temp", "int temp")),
    ("Humidity",         "%RH",    ("humidity",)),
    ("TENG Current Avg", "mA",     ("teng current", "teng avg")),
    ("EC Conductivity",  "mS/cm",  ("ec conductivity",)),
    ("Salinity",         "PSS-78", ("salinity",)),
    ("SuperCap Voltage", "V",      ("supercap",)),
]

# Sensors to hide when ``hide_ec_salinity=True``.
_HIDEABLE = {"EC Conductivity", "Salinity"}


# ──────────────────────────────────────────────────────────────────────
# Phase 2 enrichment groups — one entry per plot. Each lists:
#   (title, y_label, columns, scale_factors)
# where ``scale_factors`` matches the encoded → physical conversion
# used by utils/p2/schema.ENRICHED_COLUMNS so the legend is in SI.
# ──────────────────────────────────────────────────────────────────────
# Each series entry is ``(col, label, unit, scale, axis)`` where axis
# is "y" for the primary axis and "y2" for the secondary.
#
# Dual-y rule: whenever a group renders 2+ series we show the primary
# quantity on y1 and any additional (different-unit or comparison)
# quantities on y2 so neither gets flattened by the other's scale.
# Groups with only a single series use the primary axis.
ENRICHED_GROUPS: list[dict] = [
    {
        "key": "wave",
        "title": "Waves (Open-Meteo Marine)",
        "series": [
            ("WAVE_H_cm",  "Hs",     "m",   100.0, "y"),
            ("SWELL_H_cm", "Hswell", "m",   100.0, "y2"),
        ],
        "y_label": "Hs — wave height (m)",
        "y2_label": "Hswell — swell height (m)",
    },
    {
        "key": "wave_period",
        "title": "Wave period & direction",
        "series": [
            ("WAVE_T_ds",   "Tp",          "s",   10.0, "y"),
            ("SWELL_T_ds",  "Tswell",      "s",   10.0, "y"),
            ("WAVE_DIR_deg","Wave dir",    "deg",  1.0, "y2"),
        ],
        "y_label": "Period (s)",
        "y2_label": "Direction (deg)",
    },
    {
        "key": "wind",
        "title": "Wind (10 m, Open-Meteo Historical)",
        "series": [
            ("WIND_SPD_cms", "Wind speed",     "m/s", 100.0, "y"),
            ("WIND_DIR_deg", "Wind direction", "deg",   1.0, "y2"),
        ],
        "y_label": "Wind speed (m/s)",
        "y2_label": "Wind direction (deg)",
    },
    {
        "key": "atmos",
        "title": "Atmosphere (ERA5)",
        "series": [
            ("ERA5_PRES_dPa", "Pressure",    "Pa",  0.1,   "y"),
            ("ERA5_AIRT_cC",  "Air temp",    "°C",  100.0, "y2"),
        ],
        "y_label": "Surface pressure (Pa)",
        "y2_label": "Air temperature (°C)",
    },
    {
        "key": "sst_products",
        "title": "Sea surface temperature — buoy vs satellite products",
        "series": [
            # First product on y1; remaining products on y2 so the user
            # gets an explicit dual-axis comparison per the style rule.
            # Secondary axis is range-linked to primary in the builder
            # below so the °C values stay directly comparable.
            ("SAT_SST_OISST_cC",    "OISST",     "°C", 100.0, "y"),
            ("SAT_SST_MUR_cC",      "MUR",       "°C", 100.0, "y2"),
            ("SAT_SST_OSTIA_cC",    "OSTIA",     "°C", 100.0, "y2"),
            ("SAT_SST_ERA5_cC",     "ERA5",      "°C", 100.0, "y2"),
            ("SAT_SST_OPENMETEO_cC","OpenMeteo", "°C", 100.0, "y2"),
        ],
        "y_label": "OISST (°C)",
        "y2_label": "Other SST products (°C)",
        "overlay_buoy_sst": True,
        "link_y2_to_y": True,
    },
    {
        "key": "ocean_currents",
        "title": "Ocean surface currents (OSCAR)",
        "series": [
            ("OSCAR_U_mms", "U (east)",  "m/s", 1000.0, "y"),
            ("OSCAR_V_mms", "V (north)", "m/s", 1000.0, "y2"),
        ],
        "y_label": "U current (m/s, east)",
        "y2_label": "V current (m/s, north)",
        "link_y2_to_y": True,
    },
    {
        "key": "seaice",
        "title": "Sea-ice concentration (OSI SAF)",
        "series": [
            ("SEAICE_CONC_pct", "Sea ice", "%", 1.0, "y"),
        ],
        "y_label": "Concentration (%)",
    },
    {
        "key": "enrich_flag",
        "title": "Enrichment coverage (ENRICH_FLAG)",
        "series": [
            ("ENRICH_FLAG", "ENRICH_FLAG", "bitfield", 1.0, "y"),
        ],
        "y_label": "Bitfield value",
    },
]


def _find_col_by_keywords(
    df: pd.DataFrame,
    keywords: Iterable[str],
    *,
    skip_prev: bool = True,
) -> str | None:
    for c in df.columns:
        cl = c.lower()
        if skip_prev and cl.startswith("prev"):
            continue
        if any(kw in cl for kw in keywords):
            return c
    return None


def _decode(series: pd.Series, scale: float) -> pd.Series:
    """Convert encoded int series to physical units."""
    s = pd.to_numeric(series, errors="coerce")
    if scale and scale != 1.0:
        return s / scale
    return s


def _empty_reason(df: pd.DataFrame, cols: Iterable[str]) -> str | None:
    """Return a reason string if none of ``cols`` have plottable data."""
    present = [c for c in cols if c in df.columns]
    if not present:
        return "columns not present"
    has_data = any(pd.to_numeric(df[c], errors="coerce").notna().any() for c in present)
    if not has_data:
        return "all values are NaN for the current selection"
    return None


def _new_fig():
    if go is None:  # pragma: no cover
        raise RuntimeError("plotly is required for sensor_overview")
    return go.Figure()


# ──────────────────────────────────────────────────────────────────────
# Phase 1 sensor plots
# ──────────────────────────────────────────────────────────────────────
def build_phase1_sensor_figures(
    df: pd.DataFrame,
    time_col: str,
    dev_col: str,
    *,
    hide_ec_salinity: bool = True,
) -> list[tuple[str, object]]:
    """Return ``[(title, plotly.Figure), …]`` for Phase 1 sensors present.

    Mirrors the sensor-plot loop in pages/5_📈_Analytics.py so users see
    the same default visualizations on the Phase 2 SST page.
    """
    figs: list[tuple[str, object]] = []
    if df is None or df.empty or time_col not in df.columns:
        return figs

    base = df.dropna(subset=[time_col])
    if base.empty:
        return figs

    for title, unit, keywords in PHASE1_SENSORS:
        if hide_ec_salinity and title in _HIDEABLE:
            continue
        y_col = _find_col_by_keywords(base, keywords)
        if y_col is None:
            continue
        plot_df = base.copy()
        plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
        plot_df = plot_df.dropna(subset=[y_col])
        if plot_df.empty:
            continue

        fig = _new_fig()
        devices = plot_df[dev_col].unique() if dev_col in plot_df.columns else [None]
        for di, device in enumerate(devices):
            ddf = (
                plot_df if device is None
                else plot_df[plot_df[dev_col] == device]
            )
            color = COLORS[di % len(COLORS)]
            fig.add_trace(go.Scatter(
                x=ddf[time_col], y=ddf[y_col],
                mode="lines+markers",
                name=str(device) if device is not None else y_col,
                line=dict(width=LINE_WIDTH, color=color),
                marker=dict(size=MARKER_SIZE),
            ))
        y_label = f"{y_col} ({unit})" if unit else y_col
        apply_plot_style(fig, title=title, x_title=time_col, y_title=y_label)
        figs.append((title, fig))
    return figs


# ──────────────────────────────────────────────────────────────────────
# Phase 2 enriched group plots
# ──────────────────────────────────────────────────────────────────────
def summarize_enrichment_coverage(
    df: pd.DataFrame,
    time_col: str,
) -> dict:
    """Return a compact snapshot of the GPS + time range that was used
    to populate the Phase 2 enriched columns.

    The cron pipeline snaps each buoy row's (lat, lon) to a 0.1° grid
    cell, hour-buckets the timestamp to UTC, then fetches the Open-Meteo
    / satellite reference at that cell-hour. To let a user visually
    confirm the reference is being fetched at the same place & time as
    the buoy, this helper reports:

        - ``n_rows``:        how many rows are in the current selection
        - ``lat_min/max``:   actual lat range (°) of the selected rows
        - ``lon_min/max``:   actual lon range (°)
        - ``lat_cells``:     set of 0.1°-snapped latitude cells used
        - ``lon_cells``:     set of 0.1°-snapped longitude cells used
        - ``t_min/max``:     UTC time range
        - ``n_hours_used``:  distinct hour-buckets in the selection
        - ``inland_hint``:   True when all satellite-SST columns are NaN
                             AND ``SAT_SST_OPENMETEO_cC`` *is* populated,
                             which is the signature of an inland / coastal
                             GPS fix (OISST/MUR/OSTIA are land-masked).

    All fields default to ``None`` when the frame is empty so callers
    can render a polite "no data" caption instead of a traceback.
    """
    out: dict = {
        "n_rows": 0,
        "lat_min": None, "lat_max": None,
        "lon_min": None, "lon_max": None,
        "lat_cells": [],
        "lon_cells": [],
        "t_min": None, "t_max": None,
        "n_hours_used": 0,
        "inland_hint": False,
    }
    if df is None or df.empty:
        return out
    out["n_rows"] = int(len(df))

    lat_col = None
    for cand in ("Lat", "Latitude", "lat"):
        if cand in df.columns:
            lat_col = cand
            break
    if lat_col is None:
        for c in df.columns:
            if "lat" in str(c).lower():
                lat_col = c
                break
    lon_col = None
    for cand in ("Lon", "Longitude", "lon", "Lng"):
        if cand in df.columns:
            lon_col = cand
            break
    if lon_col is None:
        for c in df.columns:
            cl = str(c).lower()
            if ("lon" in cl or "lng" in cl) and not any(
                x in cl for x in ("longevity", "long-term", "longterm")
            ):
                lon_col = c
                break

    if lat_col is not None:
        lat = pd.to_numeric(df[lat_col], errors="coerce").dropna()
        # Treat the (0, 0) sentinel ("no GPS fix") as missing.
        if lon_col is not None:
            lon_tmp = pd.to_numeric(df[lon_col], errors="coerce").reindex(lat.index)
            lat = lat[~((lat.abs() < 1e-9) & (lon_tmp.abs() < 1e-9))]
        if not lat.empty:
            out["lat_min"] = float(lat.min())
            out["lat_max"] = float(lat.max())
            # 0.1° snap mirrors utils/p2/sources/grid.py :: snap()
            out["lat_cells"] = sorted({round(round(v * 10) / 10, 1) for v in lat})

    if lon_col is not None:
        lon = pd.to_numeric(df[lon_col], errors="coerce").dropna()
        if lat_col is not None:
            lat_tmp = pd.to_numeric(df[lat_col], errors="coerce").reindex(lon.index)
            lon = lon[~((lon.abs() < 1e-9) & (lat_tmp.abs() < 1e-9))]
        if not lon.empty:
            out["lon_min"] = float(lon.min())
            out["lon_max"] = float(lon.max())
            out["lon_cells"] = sorted({round(round(v * 10) / 10, 1) for v in lon})

    if time_col and time_col in df.columns:
        ts = pd.to_datetime(df[time_col], errors="coerce", utc=True).dropna()
        if not ts.empty:
            out["t_min"] = ts.min()
            out["t_max"] = ts.max()
            out["n_hours_used"] = int(ts.dt.floor("h").nunique())

    sat_cols = ("SAT_SST_OISST_cC", "SAT_SST_MUR_cC", "SAT_SST_OSTIA_cC")
    openmeteo_col = "SAT_SST_OPENMETEO_cC"
    sat_all_nan = all(
        c not in df.columns or not pd.to_numeric(df[c], errors="coerce").notna().any()
        for c in sat_cols
    )
    om_has_data = (
        openmeteo_col in df.columns
        and pd.to_numeric(df[openmeteo_col], errors="coerce").notna().any()
    )
    out["inland_hint"] = bool(sat_all_nan and om_has_data)

    return out


def list_dual_axis_groups() -> list[dict]:
    """Return the subset of ``ENRICHED_GROUPS`` that a user could
    reasonably re-assign between y1 and y2.

    Groups whose series all share the same unit are excluded — they
    now render on a single axis automatically and a per-group axis
    selector would confuse more than help.
    """
    out: list[dict] = []
    for g in ENRICHED_GROUPS:
        series = g.get("series", [])
        if len(series) < 2:
            continue
        units = {s[2] for s in series if len(s) >= 5}
        if len(units) <= 1:
            continue
        out.append(g)
    return out


def build_enriched_group_figures(
    df: pd.DataFrame,
    time_col: str,
    dev_col: str,
    *,
    y2_overrides: dict[str, list[str]] | None = None,
    dual_axis_enabled: dict[str, bool] | None = None,
    overlay_buoy_sst: bool = True,
    overlay_air_temp: bool = False,
    overlay_internal_temp: bool = False,
) -> list[tuple[str, object, str | None]]:
    """Return ``[(title, figure_or_None, skip_reason), …]``.

    When a group is skipped the figure is ``None`` and ``skip_reason``
    describes why, so the caller can render a caption instead of a
    blank chart.

    ``y2_overrides`` lets the caller replace a group's default axis
    assignment — the key is the group ``key`` (e.g. ``"wind"``), the
    value is the list of **column names** the user wants on the
    secondary (right-hand) axis. Any column not in the list stays on
    y1. If the group's series all share one unit this parameter is
    ignored and everything renders on a single axis.

    ``dual_axis_enabled`` lets the caller flip individual mixed-unit
    groups back to a single axis on demand — when ``False`` for a given
    group key, every series in that group renders on y1 regardless of
    the group's default axis tuple. Defaults to ``True`` for groups
    that aren't explicitly mentioned, preserving the original layout.

    ``overlay_buoy_sst`` and ``overlay_air_temp`` toggle the SST
    products group's overlays. Buoy SST is on by default (it's the
    point-truth users want anchored on the chart); air temp is off
    because it lives on a different physical axis and is mainly useful
    for inland deployments.
    """
    y2_overrides = y2_overrides or {}
    dual_axis_enabled = dual_axis_enabled or {}
    out: list[tuple[str, object, str | None]] = []
    if df is None or df.empty or time_col not in df.columns:
        return out

    base = df.dropna(subset=[time_col]).copy()
    if base.empty:
        return out

    for group in ENRICHED_GROUPS:
        title = group["title"]
        cols = [s[0] for s in group["series"]]
        reason = _empty_reason(base, cols)

        # SST product group: also check for a buoy-SST column to overlay.
        # The overlay can be turned off by the caller; when it's on AND
        # the products themselves have no data we still render the chart
        # so the user can see the buoy-only series.
        is_sst_group = bool(group.get("overlay_buoy_sst"))
        wants_buoy_overlay = is_sst_group and overlay_buoy_sst
        wants_air_overlay = is_sst_group and overlay_air_temp
        wants_internal_overlay = is_sst_group and overlay_internal_temp
        if wants_buoy_overlay or wants_air_overlay or wants_internal_overlay:
            buoy_col = _find_col_by_keywords(
                base, ("sst_buoy", "water temp", "ocean temp", "sst"),
            )
            air_col = _find_col_by_keywords(
                base, ("era5_airt",),
            )
            internal_col = _find_col_by_keywords(
                base, ("internal temp", "int temp"),
            )
            has_overlay_data = (
                (wants_buoy_overlay and buoy_col is not None)
                or (wants_air_overlay and air_col is not None)
                or (wants_internal_overlay and internal_col is not None)
            )
            if reason is not None and not has_overlay_data:
                out.append((title, None, reason))
                continue
            if has_overlay_data:
                reason = None  # at least one of: buoy / air / internal / a product

        if reason is not None:
            out.append((title, None, reason))
            continue

        fig = _new_fig()
        plotted_any = False
        uses_secondary = False

        # Per-series: one trace per (device × variable). When multiple
        # devices are selected we color by device and dash by variable.
        devices = base[dev_col].unique() if dev_col in base.columns else [None]

        # Decide axis assignments up front:
        # 1. If every series in the group shares the same unit, collapse
        #    to a single y-axis (so e.g. all SST products, all in °C,
        #    share one vertical scale instead of reading off two).
        # 2. Otherwise, if the caller passed an override for this group,
        #    use it (list of columns → y2). Any column not in the list
        #    lands on y1.
        # 3. Fall back to the group's default axis tuple.
        series_entries = group["series"]
        group_units = {s[2] for s in series_entries if len(s) >= 5}
        same_unit_group = len(group_units) <= 1
        override_cols = y2_overrides.get(group.get("key"))
        # Per-group dual-axis toggle. Default ON for mixed-unit groups
        # (preserves the original Wind / Atmosphere / Wave-period
        # layouts). When the user flips the toggle off we collapse
        # everything to y1 — same code path as same-unit groups.
        group_key = group.get("key")
        dual_on = dual_axis_enabled.get(group_key, True)
        force_single_axis = same_unit_group or not dual_on
        axis_for: dict[str, str] = {}
        for entry in series_entries:
            if len(entry) == 5:
                col_, _lbl, _unit, _scale, default_axis = entry
            else:
                col_, _lbl, _unit, _scale = entry  # type: ignore[misc]
                default_axis = "y"
            if force_single_axis:
                axis_for[col_] = "y"
            elif override_cols is not None:
                axis_for[col_] = "y2" if col_ in override_cols else "y"
            else:
                axis_for[col_] = default_axis

        for si, entry in enumerate(series_entries):
            # Support 4-tuple (legacy, no axis) and 5-tuple (col, label,
            # unit, scale, axis) entries.
            if len(entry) == 5:
                col, label, unit, scale, _default_axis = entry
            else:
                col, label, unit, scale = entry  # type: ignore[misc]
            axis = axis_for.get(col, "y")
            if col not in base.columns:
                continue
            y = _decode(base[col], scale)
            if not y.notna().any():
                continue
            if axis == "y2":
                uses_secondary = True
            for di, device in enumerate(devices):
                if device is None:
                    mask = pd.Series(True, index=base.index)
                    name = label
                else:
                    mask = base[dev_col] == device
                    name = f"{label} — {device}" if len(devices) > 1 else label
                sub_x = base.loc[mask, time_col]
                sub_y = y.loc[mask]
                sub_y = sub_y.dropna()
                if sub_y.empty:
                    continue
                color = COLORS[(di + si * 3) % len(COLORS)]
                dash = "solid" if si == 0 else ("dot" if si == 1 else "dash")
                fig.add_trace(go.Scatter(
                    x=sub_x.loc[sub_y.index],
                    y=sub_y,
                    mode="lines+markers",
                    name=name,
                    line=dict(width=LINE_WIDTH, color=color, dash=dash),
                    marker=dict(size=MARKER_SIZE, color=color),
                    yaxis=axis,
                ))
                plotted_any = True

        # Buoy is the point-truth on the SST-products chart, so we
        # render it with a distinctive marker symbol (diamond), larger
        # size, a bolder line, a white outline, AND a soft translucent
        # halo underneath so it stays visually dominant over the 4–5
        # reference products. Color cycles per device so multi-buoy
        # panels remain distinguishable.
        _BUOY_PALETTE = ("#E53935", "#1B5E20", "#4527A0", "#BF360C", "#37474F")
        if is_sst_group and overlay_buoy_sst:
            buoy_col = _find_col_by_keywords(
                base, ("sst_buoy", "water temp", "ocean temp", "sst"),
            )
            if buoy_col is not None:
                for di, device in enumerate(devices):
                    mask = (
                        pd.Series(True, index=base.index) if device is None
                        else base[dev_col] == device
                    )
                    y = pd.to_numeric(base.loc[mask, buoy_col], errors="coerce")
                    if not y.notna().any():
                        continue
                    name = (
                        f"Buoy ({device})" if device is not None
                        else "Buoy"
                    )
                    color = _BUOY_PALETTE[di % len(_BUOY_PALETTE)]
                    # Halo: wide, translucent line behind the main trace
                    # so the buoy series reads as a glowing highlight
                    # even when overlapping satellite products.
                    fig.add_trace(go.Scatter(
                        x=base.loc[mask, time_col],
                        y=y,
                        mode="lines",
                        name=f"{name} halo",
                        line=dict(width=10, color=color),
                        opacity=0.18,
                        hoverinfo="skip",
                        showlegend=False,
                        yaxis="y",
                    ))
                    fig.add_trace(go.Scatter(
                        x=base.loc[mask, time_col],
                        y=y,
                        mode="lines+markers",
                        name=name,
                        line=dict(width=3.5, color=color),
                        marker=dict(
                            size=12,
                            color=color,
                            symbol="diamond",
                            line=dict(width=2.0, color="white"),
                        ),
                        yaxis="y",
                    ))
                    plotted_any = True

        # SST products: optional ERA5 2 m air-temperature overlay,
        # rendered as a low-emphasis dash-dot purple line so it provides
        # context for inland deployments without competing with the
        # satellite SST products or the buoy itself.
        if is_sst_group and overlay_air_temp:
            air_col = _find_col_by_keywords(base, ("era5_airt",))
            if air_col is not None:
                air = pd.to_numeric(base[air_col], errors="coerce") / 100.0
                if air.notna().any():
                    fig.add_trace(go.Scatter(
                        x=base[time_col],
                        y=air,
                        mode="lines",
                        name="Land / air temp (ERA5 2 m)",
                        line=dict(width=1.4, color="#8E24AA", dash="dashdot"),
                        opacity=0.75,
                        yaxis="y",
                    ))
                    plotted_any = True

        # SST products: optional buoy internal (hull) temperature overlay.
        # Not a water-SST measurement — the sensor lives inside the sealed
        # hull so its diurnal amplitude is typically 2-3x the ambient 2 m
        # air temp amplitude due to greenhouse heating. Useful for
        # diagnosing thermal coupling between the electronics bay and the
        # ambient environment.
        if is_sst_group and overlay_internal_temp:
            int_col = _find_col_by_keywords(base, ("internal temp", "int temp"))
            if int_col is not None:
                itemp = pd.to_numeric(base[int_col], errors="coerce")
                if itemp.notna().any():
                    fig.add_trace(go.Scatter(
                        x=base[time_col],
                        y=itemp,
                        mode="lines",
                        name="Buoy internal temp (hull, NOT water)",
                        line=dict(width=1.2, color="#9CA3AF", dash="dot"),
                        opacity=0.7,
                        yaxis="y",
                    ))
                    plotted_any = True

        if not plotted_any:
            out.append((title, None, "no plottable points in range"))
            continue

        # When the group was auto-collapsed to a single axis (same-unit
        # series OR user-disabled dual-axis toggle) the default y_label
        # (e.g. "OISST (°C)") is misleading — use a generic
        # "<quantity> (<unit>)" label, or fall back to the group label
        # when the units are mixed but the user collapsed everything.
        _unit_str = next(iter(group_units)) if same_unit_group and group_units else None
        y_title_final = group["y_label"]
        if same_unit_group and _unit_str:
            _quantity = {
                "°C": "Temperature",
                "m/s": "Speed",
                "deg": "Direction",
                "m": "Height",
                "s": "Period",
                "Pa": "Pressure",
                "%": "Percent",
            }.get(_unit_str, group["y_label"])
            y_title_final = f"{_quantity} ({_unit_str})"
        elif force_single_axis and not same_unit_group:
            y_title_final = "Mixed units — see legend (single-axis mode)"

        apply_plot_style(
            fig,
            title=title,
            x_title=time_col,
            y_title=y_title_final,
        )

        # Secondary axis configuration — only when at least one series
        # was actually assigned to y2.
        if uses_secondary:
            y2_cfg: dict = dict(
                title=dict(text=group.get("y2_label", ""), font=dict(size=17)),
                overlaying="y",
                side="right",
                showgrid=False,
                tickfont=dict(size=14),
            )
            # When both axes represent the same physical unit (e.g. all
            # °C for SST products or m/s for OSCAR currents) lock the
            # ranges together so traces remain directly comparable.
            if group.get("link_y2_to_y"):
                y2_cfg["matches"] = "y"
            fig.update_layout(yaxis2=y2_cfg)
            # Give the legend a little breathing room so the second
            # y-axis labels aren't clipped.
            fig.update_layout(
                margin=dict(l=60, r=70, t=60, b=50),
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1.0,
                ),
            )

        out.append((title, fig, None))

    return out
