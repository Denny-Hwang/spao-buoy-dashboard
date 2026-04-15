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
ENRICHED_GROUPS: list[dict] = [
    {
        "key": "wave",
        "title": "Waves (Open-Meteo Marine)",
        "series": [
            ("WAVE_H_cm",  "Hs",     "m",   100.0),
            ("SWELL_H_cm", "Hswell", "m",   100.0),
        ],
        "y_label": "Wave height (m)",
    },
    {
        "key": "wave_period",
        "title": "Wave period & direction",
        "series": [
            ("WAVE_T_ds",   "Tp",          "s",   10.0),
            ("SWELL_T_ds",  "Tswell",      "s",   10.0),
            ("WAVE_DIR_deg","Wave dir",    "deg",  1.0),
        ],
        "y_label": "Period (s) / direction (deg)",
    },
    {
        "key": "wind",
        "title": "Wind (10 m, Open-Meteo Historical)",
        "series": [
            ("WIND_SPD_cms", "Wind speed",     "m/s", 100.0),
            ("WIND_DIR_deg", "Wind direction", "deg",   1.0),
        ],
        "y_label": "Speed (m/s) / direction (deg)",
    },
    {
        "key": "atmos",
        "title": "Atmosphere (ERA5)",
        "series": [
            ("ERA5_PRES_dPa", "Pressure",    "Pa",  0.1),
            ("ERA5_AIRT_cC",  "Air temp",    "°C",  100.0),
        ],
        "y_label": "Pa / °C",
    },
    {
        "key": "sst_products",
        "title": "Sea surface temperature — buoy vs satellite products",
        "series": [
            ("SAT_SST_OISST_cC", "OISST",  "°C", 100.0),
            ("SAT_SST_MUR_cC",   "MUR",    "°C", 100.0),
            ("SAT_SST_OSTIA_cC", "OSTIA",  "°C", 100.0),
            ("SAT_SST_ERA5_cC",  "ERA5",   "°C", 100.0),
        ],
        "y_label": "SST (°C)",
        "overlay_buoy_sst": True,
    },
    {
        "key": "ocean_currents",
        "title": "Ocean surface currents (OSCAR)",
        "series": [
            ("OSCAR_U_mms", "U (east)",  "m/s", 1000.0),
            ("OSCAR_V_mms", "V (north)", "m/s", 1000.0),
        ],
        "y_label": "Current (m/s)",
    },
    {
        "key": "seaice",
        "title": "Sea-ice concentration (OSI SAF)",
        "series": [
            ("SEAICE_CONC_pct", "Sea ice", "%", 1.0),
        ],
        "y_label": "Concentration (%)",
    },
    {
        "key": "enrich_flag",
        "title": "Enrichment coverage (ENRICH_FLAG)",
        "series": [
            ("ENRICH_FLAG", "ENRICH_FLAG", "bitfield", 1.0),
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
def build_enriched_group_figures(
    df: pd.DataFrame,
    time_col: str,
    dev_col: str,
) -> list[tuple[str, object, str | None]]:
    """Return ``[(title, figure_or_None, skip_reason), …]``.

    When a group is skipped the figure is ``None`` and ``skip_reason``
    describes why, so the caller can render a caption instead of a
    blank chart.
    """
    out: list[tuple[str, object, str | None]] = []
    if df is None or df.empty or time_col not in df.columns:
        return out

    base = df.dropna(subset=[time_col]).copy()
    if base.empty:
        return out

    for group in ENRICHED_GROUPS:
        title = group["title"]
        cols = [c for c, _n, _u, _s in group["series"]]
        reason = _empty_reason(base, cols)

        # SST product group: also check for a buoy-SST column to overlay.
        if group.get("overlay_buoy_sst"):
            buoy_col = _find_col_by_keywords(
                base, ("sst_buoy", "water temp", "ocean temp", "sst"),
            )
            if reason is not None and buoy_col is None:
                out.append((title, None, reason))
                continue
            reason = None  # we have at least buoy or at least one product

        if reason is not None:
            out.append((title, None, reason))
            continue

        fig = _new_fig()
        plotted_any = False

        # Per-series: one trace per (device × variable). When multiple
        # devices are selected we color by device and dash by variable.
        devices = base[dev_col].unique() if dev_col in base.columns else [None]

        for si, (col, label, unit, scale) in enumerate(group["series"]):
            if col not in base.columns:
                continue
            y = _decode(base[col], scale)
            if not y.notna().any():
                continue
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
                ))
                plotted_any = True

        # SST products: overlay buoy SST as black dots on the same axis.
        if group.get("overlay_buoy_sst"):
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
                    name = f"Buoy — {device}" if device is not None and len(devices) > 1 else "Buoy"
                    fig.add_trace(go.Scatter(
                        x=base.loc[mask, time_col],
                        y=y,
                        mode="markers",
                        name=name,
                        marker=dict(
                            size=5,
                            color="black",
                            symbol="circle",
                        ),
                    ))
                    plotted_any = True

        if not plotted_any:
            out.append((title, None, "no plottable points in range"))
            continue

        apply_plot_style(
            fig,
            title=title,
            x_title=time_col,
            y_title=group["y_label"],
        )
        out.append((title, fig, None))

    return out
