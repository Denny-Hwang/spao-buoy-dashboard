"""
Panel builders for page 9 — Drift Dynamics.

Sections:
    C1  Trajectory — speed-coloured polyline, stick plot, cumulative
        distance, daily displacement bar
    C2  Ekman decomposition — α(t), θ histogram, wind rose × drift rose,
        residual current vs OSCAR
    C3  Storm response — event table, superposed epoch ±48 h,
        pre/during/post boxplots
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

try:
    import plotly.graph_objects as go  # type: ignore
    from plotly.subplots import make_subplots  # type: ignore
except Exception:  # pragma: no cover
    go = None  # type: ignore[assignment]
    make_subplots = None  # type: ignore[assignment]

from ..physics.ekman import (
    compute_drift_velocity,
    decompose_drift,
    fit_windage,
    _resolve_lat_col,
    _resolve_lon_col,
)
from ..physics.storms import detect_storms, superposed_epoch

NIILER_PADUAN_ALPHA = 0.007   # drogued surface drifters
POULAIN_ALPHA_LOW = 0.03      # undrogued lower
POULAIN_ALPHA_HIGH = 0.05     # undrogued upper


DESCRIPTIONS: dict[str, str] = {
    "trajectory": (
        "Drift trajectory coloured by instantaneous speed. Start / end are "
        "marked with a green circle and red star; hover shows UTC time, "
        "speed and wind. Use this to connect spatial patterns to the "
        "time-series on the rest of the page."
    ),
    "stick_plot": (
        "Meridional (north-south) drift velocity over time — vertical bars "
        "help spot sign flips and event-driven reversals."
    ),
    "cumulative_distance": (
        "Total distance travelled along the trajectory — a steeper slope "
        "means a faster drift leg."
    ),
    "daily_displacement": (
        "Per-day net displacement magnitude — short bars on quiet days, "
        "tall bars under storms."
    ),
    "alpha": (
        "Rolling windage coefficient α = |U_drift| / |U_wind|. Reference "
        "lines compare the buoy to drogued (Niiler-Paduan 0.007) and "
        "undrogued (Poulain 0.03–0.05) surface drifters."
    ),
    "theta": (
        "Deflection angle (θ, CCW positive) between wind vector and drift "
        "vector. Classical Ekman theory predicts ~45° to the right in the "
        "northern hemisphere."
    ),
    "roses": (
        "Wind and drift roses share the same polar binning so the user can "
        "see at a glance how wind forcing aligns (or not) with buoy drift."
    ),
    "residual_vs_oscar": (
        "After subtracting the wind-driven Ekman component, the remaining "
        "residual drift should correlate with OSCAR surface currents if "
        "the decomposition is right."
    ),
    "storm_table": (
        "Storms auto-detected from Hs / U10 thresholds; peaks and duration "
        "are the entry points into the superposed-epoch view below."
    ),
    "epoch_multipanel": (
        "Storm-centred superposed-epoch composite ±48 h. A sharp peak at "
        "lag = 0 means every storm acts the same way on this variable."
    ),
    "pre_during_post": (
        "Distribution of the chosen variable before, during, and after each "
        "storm — highlights sustained or delayed response."
    ),
}


def _require_plotly() -> None:
    if go is None:  # pragma: no cover
        raise RuntimeError("plotly is required for utils.p2.viz.drift_panels")


# ──────────────────────────────────────────────────────────────────────
# C1 — Trajectory
# ──────────────────────────────────────────────────────────────────────
def build_trajectory_speed_colored(
    df: pd.DataFrame,
    *,
    height: int = 640,
    pad_deg: float = 0.15,
) -> Any:
    """Lat/Lon polyline coloured by instantaneous drift speed (m/s).

    Phase-2 oriented trajectory view: larger than the default geo chart,
    auto-zoom to tightly fit the observed track (with a small padding
    band so start / end markers stay fully visible), start-of-track and
    latest-position markers for quick temporal anchoring, and hover
    tooltips that join lat/lon/UTC/speed/wind in one line so operators
    don't have to cross-reference the time-series.
    """
    _require_plotly()
    drift = compute_drift_velocity(df)
    if "u_drift" not in drift.columns:
        return go.Figure().update_layout(title="Trajectory — no drift data")
    lat_col = _resolve_lat_col(drift) or "Lat"
    lon_col = _resolve_lon_col(drift) or "Lon"
    lat = pd.to_numeric(drift.get(lat_col), errors="coerce")
    lon = pd.to_numeric(drift.get(lon_col), errors="coerce")
    speed = np.sqrt(drift["u_drift"] ** 2 + drift["v_drift"] ** 2)
    mask = np.isfinite(lat) & np.isfinite(lon) & np.isfinite(speed)
    lat_v = lat[mask].to_numpy()
    lon_v = lon[mask].to_numpy()
    spd_v = speed[mask].to_numpy()

    ts = pd.to_datetime(drift.get("Timestamp"), utc=True, errors="coerce")
    ts_v = ts[mask]
    wind = None
    if "U10" in drift.columns and "V10" in drift.columns:
        u10 = pd.to_numeric(drift.get("U10"), errors="coerce")
        v10 = pd.to_numeric(drift.get("V10"), errors="coerce")
        wind = np.sqrt(u10 ** 2 + v10 ** 2)[mask].to_numpy()

    fig = go.Figure()

    if lat_v.size == 0:
        fig.update_layout(
            title=dict(text="Trajectory — no drift data", font=dict(size=18)),
            height=height,
        )
        return fig

    hover = []
    for i in range(len(lat_v)):
        t = ts_v.iloc[i].strftime("%Y-%m-%d %H:%M UTC") if pd.notna(ts_v.iloc[i]) else "—"
        w = f"{wind[i]:.1f} m/s" if wind is not None and np.isfinite(wind[i]) else "n/a"
        hover.append(
            f"{t}<br>lat {lat_v[i]:.4f}°, lon {lon_v[i]:.4f}°"
            f"<br>speed {spd_v[i]:.3f} m/s<br>wind {w}"
        )

    fig.add_trace(go.Scattergeo(
        lon=lon_v, lat=lat_v, mode="lines+markers",
        marker=dict(
            size=6, color=spd_v, colorscale="Viridis",
            cmin=float(np.nanmin(spd_v)) if spd_v.size else 0.0,
            cmax=float(np.nanpercentile(spd_v, 95)) if spd_v.size else 1.0,
            colorbar=dict(
                title=dict(text="Speed (m/s)", font=dict(size=13)),
                thickness=16, len=0.75, x=1.02,
                tickfont=dict(size=12),
            ),
        ),
        line=dict(width=2, color="rgba(0,0,0,0.35)"),
        name="trajectory",
        text=hover,
        hoverinfo="text",
    ))

    # Start marker (green circle) and latest marker (red star).
    fig.add_trace(go.Scattergeo(
        lon=[lon_v[0]], lat=[lat_v[0]], mode="markers+text",
        marker=dict(size=14, color="#2E7D32", symbol="circle",
                    line=dict(width=2, color="white")),
        text=["Start"], textposition="top center",
        textfont=dict(color="#2E7D32", size=12),
        name="Start", hoverinfo="text",
    ))
    fig.add_trace(go.Scattergeo(
        lon=[lon_v[-1]], lat=[lat_v[-1]], mode="markers+text",
        marker=dict(size=16, color="#C62828", symbol="star",
                    line=dict(width=2, color="white")),
        text=["Latest"], textposition="top center",
        textfont=dict(color="#C62828", size=12),
        name="Latest", hoverinfo="text",
    ))

    lat_min, lat_max = float(np.nanmin(lat_v)), float(np.nanmax(lat_v))
    lon_min, lon_max = float(np.nanmin(lon_v)), float(np.nanmax(lon_v))
    # If the track straddles the antimeridian (lon jumps −179 ↔ +179)
    # the naive min/max spans ~360° instead of a few degrees. Detect by
    # looking for an unphysically wide lon span + lat span and fall
    # back to a global-ish view rather than the broken zoom.
    crosses_antimeridian = (lon_max - lon_min) > 180.0
    if crosses_antimeridian:
        lon_min, lon_max = -180.0, 180.0
    # Ensure a minimum window so a stationary track still has visible extent.
    span_lat = max(lat_max - lat_min, 0.05)
    span_lon = max(lon_max - lon_min, 0.05)
    lat_pad = max(pad_deg, 0.2 * span_lat)
    lon_pad = max(pad_deg, 0.2 * span_lon) if not crosses_antimeridian else 0.0

    fig.update_layout(
        title=dict(text="Trajectory — coloured by drift speed", font=dict(size=20)),
        height=height,
        margin=dict(l=10, r=10, t=60, b=10),
        legend=dict(font=dict(size=12), x=0.01, y=0.99,
                    bgcolor="rgba(255,255,255,0.8)"),
        geo=dict(
            projection_type="mercator",
            showland=True, landcolor="#eaeaea",
            showocean=True, oceancolor="#cfe3ef",
            showcoastlines=True, coastlinecolor="#5A5A5A",
            showcountries=True, countrycolor="#aaaaaa",
            showrivers=True, rivercolor="#a8cfe0",
            showlakes=True, lakecolor="#cfe3ef",
            lataxis=dict(range=[lat_min - lat_pad, lat_max + lat_pad],
                         showgrid=True, gridcolor="rgba(0,0,0,0.1)"),
            lonaxis=dict(range=[lon_min - lon_pad, lon_max + lon_pad],
                         showgrid=True, gridcolor="rgba(0,0,0,0.1)"),
        ),
    )
    return fig


def build_stick_plot_drift(df: pd.DataFrame) -> Any:
    _require_plotly()
    drift = compute_drift_velocity(df)
    if "u_drift" not in drift.columns:
        return go.Figure().update_layout(title="Stick plot — no drift")
    ts = pd.to_datetime(drift.get("Timestamp"), utc=True, errors="coerce")
    u = drift["u_drift"]
    v = drift["v_drift"]
    shapes = []
    for ti, ui, vi in zip(ts, u, v):
        if pd.isna(ti) or not (np.isfinite(ui) and np.isfinite(vi)):
            continue
        shapes.append({
            "type": "line",
            "x0": ti, "x1": ti,
            "y0": 0.0, "y1": float(vi),
            "line": {"color": "steelblue", "width": 2},
        })
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ts, y=u, mode="lines", name="u_drift",
                             line=dict(color="darkorange", width=1)))
    fig.update_layout(
        title=dict(text="Drift velocity stick plot", font=dict(size=18)),
        xaxis=dict(title=dict(text="Time", font=dict(size=14)),
                   tickfont=dict(size=12), showgrid=True, gridcolor="#e5e7eb"),
        yaxis=dict(title=dict(text="Meridional velocity (m/s)", font=dict(size=14)),
                   tickfont=dict(size=12), showgrid=True, gridcolor="#e5e7eb"),
        height=420,
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=60, r=30, t=55, b=50),
        shapes=shapes,
    )
    return fig


def build_cumulative_distance(df: pd.DataFrame) -> Any:
    _require_plotly()
    drift = compute_drift_velocity(df)
    ts = pd.to_datetime(drift.get("Timestamp"), utc=True, errors="coerce")
    speed = np.sqrt(drift.get("u_drift", pd.Series(np.nan)) ** 2 +
                    drift.get("v_drift", pd.Series(np.nan)) ** 2)
    dt = ts.diff().dt.total_seconds()
    step = np.where(np.isfinite(speed) & np.isfinite(dt), speed * dt, 0.0)
    cum_km = np.cumsum(step) / 1000.0
    fig = go.Figure(go.Scatter(
        x=ts, y=cum_km, mode="lines", name="cumulative",
        line=dict(width=2.5, color="#003E6B"),
    ))
    fig.update_layout(
        title=dict(text="Cumulative distance", font=dict(size=17)),
        xaxis=dict(title=dict(text="Time", font=dict(size=14)),
                   tickfont=dict(size=12), showgrid=True, gridcolor="#e5e7eb"),
        yaxis=dict(title=dict(text="Distance (km)", font=dict(size=14)),
                   tickfont=dict(size=12), showgrid=True, gridcolor="#e5e7eb"),
        height=380,
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=55, r=25, t=55, b=45),
    )
    return fig


def build_daily_displacement(df: pd.DataFrame) -> Any:
    _require_plotly()
    drift = compute_drift_velocity(df)
    ts = pd.to_datetime(drift.get("Timestamp"), utc=True, errors="coerce")
    u = drift.get("u_drift")
    v = drift.get("v_drift")
    dt = ts.diff().dt.total_seconds()
    dx = np.where(np.isfinite(u) & np.isfinite(dt), u * dt, np.nan)
    dy = np.where(np.isfinite(v) & np.isfinite(dt), v * dt, np.nan)
    frame = pd.DataFrame({"ts": ts, "dx": dx, "dy": dy}).dropna()
    if frame.empty:
        return go.Figure().update_layout(title="Daily displacement — no data")
    frame["day"] = frame["ts"].dt.tz_convert("UTC").dt.date
    daily = frame.groupby("day").apply(
        lambda g: np.sqrt(g["dx"].sum() ** 2 + g["dy"].sum() ** 2) / 1000.0,
        include_groups=False,
    )
    fig = go.Figure(go.Bar(
        x=list(daily.index), y=daily.values, name="displacement",
        marker=dict(color="#F0AB00"),
    ))
    fig.update_layout(
        title=dict(text="Daily displacement", font=dict(size=17)),
        xaxis=dict(title=dict(text="Date", font=dict(size=14)),
                   tickfont=dict(size=12)),
        yaxis=dict(title=dict(text="Distance (km)", font=dict(size=14)),
                   tickfont=dict(size=12), showgrid=True, gridcolor="#e5e7eb"),
        height=380,
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=55, r=25, t=55, b=45),
    )
    return fig


# ──────────────────────────────────────────────────────────────────────
# C2 — Ekman decomposition
# ──────────────────────────────────────────────────────────────────────
def _rolling_windage(df: pd.DataFrame, window: int = 24) -> dict:
    out = compute_drift_velocity(df)
    if "u_drift" not in out.columns or "U10" not in out.columns:
        return {"ts": [], "alpha": [], "theta": []}
    ts = pd.to_datetime(out.get("Timestamp"), utc=True, errors="coerce").values
    u_d = pd.to_numeric(out["u_drift"], errors="coerce").to_numpy()
    v_d = pd.to_numeric(out.get("v_drift"), errors="coerce").to_numpy()
    u_w = pd.to_numeric(out["U10"], errors="coerce").to_numpy()
    v_w = pd.to_numeric(out.get("V10"), errors="coerce").to_numpy()
    alpha_arr: list[float] = []
    theta_arr: list[float] = []
    ts_arr: list[Any] = []
    for i in range(len(u_d)):
        lo = max(0, i - window // 2)
        hi = min(len(u_d), i + window // 2 + 1)
        drift = np.column_stack([u_d[lo:hi], v_d[lo:hi]])
        wind = np.column_stack([u_w[lo:hi], v_w[lo:hi]])
        fit = fit_windage(drift, wind)
        alpha_arr.append(fit["alpha"])
        theta_arr.append(fit["theta_deg"])
        ts_arr.append(ts[i])
    return {"ts": ts_arr, "alpha": alpha_arr, "theta": theta_arr}


def build_alpha_timeseries(df: pd.DataFrame) -> Any:
    _require_plotly()
    rolling = _rolling_windage(df)
    fig = go.Figure()
    if rolling["ts"]:
        fig.add_trace(go.Scatter(
            x=rolling["ts"], y=rolling["alpha"],
            mode="lines+markers", name="α(t)",
            marker=dict(size=4),
        ))
    fig.add_hline(y=NIILER_PADUAN_ALPHA, line_color="green", line_dash="dash",
                  annotation_text=f"Niiler-Paduan {NIILER_PADUAN_ALPHA} (drogued)")
    fig.add_hrect(y0=POULAIN_ALPHA_LOW, y1=POULAIN_ALPHA_HIGH,
                  fillcolor="orange", opacity=0.1,
                  annotation_text="Poulain 0.03–0.05 (undrogued)")
    fig.update_layout(
        title=dict(text="Rolling windage coefficient α(t)", font=dict(size=18)),
        xaxis=dict(title=dict(text="Time", font=dict(size=14)),
                   tickfont=dict(size=12), showgrid=True, gridcolor="#e5e7eb"),
        yaxis=dict(title=dict(text="α (unitless)", font=dict(size=14)),
                   tickfont=dict(size=12), showgrid=True, gridcolor="#e5e7eb"),
        height=420,
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=55, r=30, t=55, b=50),
    )
    return fig


def build_theta_histogram(df: pd.DataFrame) -> Any:
    _require_plotly()
    rolling = _rolling_windage(df)
    theta = [t for t in rolling["theta"] if np.isfinite(t)]
    fig = go.Figure()
    if theta:
        fig.add_trace(go.Histogram(x=theta, nbinsx=24, name="θ"))
    fig.add_vline(x=45, line_dash="dash", line_color="red",
                  annotation_text="Ekman 45° (NH)")
    fig.update_layout(
        title=dict(text="Deflection angle histogram", font=dict(size=18)),
        xaxis=dict(title=dict(text="θ (degrees, CCW positive)", font=dict(size=14)),
                   tickfont=dict(size=12)),
        yaxis=dict(title=dict(text="count", font=dict(size=14)),
                   tickfont=dict(size=12), showgrid=True, gridcolor="#e5e7eb"),
        height=380,
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=55, r=30, t=55, b=50),
    )
    return fig


def _rose_figure(directions, speeds, title: str) -> Any:
    _require_plotly()
    d = np.asarray(list(directions), dtype=float) % 360
    s = np.asarray(list(speeds), dtype=float)
    mask = np.isfinite(d) & np.isfinite(s)
    d, s = d[mask], s[mask]
    bins = 16
    edges = np.linspace(0, 360, bins + 1)
    hist, _ = np.histogram(d, bins=edges)
    thetas = 0.5 * (edges[:-1] + edges[1:])
    fig = go.Figure(go.Barpolar(r=hist, theta=thetas, width=[360.0 / bins] * bins,
                                marker=dict(color=hist, colorscale="Viridis")))
    fig.update_layout(
        title=dict(text=title, font=dict(size=17)),
        polar=dict(
            angularaxis=dict(direction="clockwise", rotation=90,
                             tickfont=dict(size=11)),
            radialaxis=dict(tickfont=dict(size=11)),
        ),
        height=420, margin=dict(l=30, r=30, t=60, b=30),
    )
    return fig


def build_wind_and_drift_rose(df: pd.DataFrame) -> tuple[Any, Any]:
    """Return (wind_rose_fig, drift_rose_fig)."""
    drift = compute_drift_velocity(df)
    wind_dir = pd.to_numeric(df.get("WIND_DIR_deg", pd.Series(dtype=float)), errors="coerce")
    wind_spd = pd.to_numeric(df.get("WIND_SPD_cms", pd.Series(dtype=float)), errors="coerce") / 100.0
    u = drift.get("u_drift", pd.Series(np.nan, index=drift.index))
    v = drift.get("v_drift", pd.Series(np.nan, index=drift.index))
    drift_dir = np.degrees(np.arctan2(v, u)) % 360
    drift_spd = np.sqrt(u ** 2 + v ** 2)
    return _rose_figure(wind_dir, wind_spd, "Wind rose"), \
           _rose_figure(drift_dir, drift_spd, "Drift rose")


def build_residual_vs_oscar(df: pd.DataFrame) -> Any:
    _require_plotly()
    drift = compute_drift_velocity(df)
    if "u_drift" not in drift.columns:
        return go.Figure().update_layout(title="Residual vs OSCAR — no drift")
    wind_u = pd.to_numeric(df.get("WIND_SPD_cms", pd.Series(np.nan))) / 100.0
    if "U10" in df.columns:
        drift["U10"] = pd.to_numeric(df["U10"], errors="coerce")
    else:
        drift["U10"] = wind_u
    if "V10" in df.columns:
        drift["V10"] = pd.to_numeric(df["V10"], errors="coerce")
    else:
        drift["V10"] = 0.0
    try:
        decomp = decompose_drift(drift)
    except Exception:
        return go.Figure().update_layout(title="Residual vs OSCAR — decompose failed")
    ou = pd.to_numeric(df.get("OSCAR_U_mms", pd.Series(np.nan)), errors="coerce") / 1000.0
    ov = pd.to_numeric(df.get("OSCAR_V_mms", pd.Series(np.nan)), errors="coerce") / 1000.0
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=decomp["u_residual"].values, y=ou.values,
        mode="markers", name="u (residual vs OSCAR)",
        marker=dict(size=6, opacity=0.6, color="steelblue"),
    ))
    fig.add_trace(go.Scatter(
        x=decomp["v_residual"].values, y=ov.values,
        mode="markers", name="v (residual vs OSCAR)",
        marker=dict(size=6, opacity=0.6, color="crimson"),
    ))
    fig.update_layout(
        title=dict(text="Residual drift vs OSCAR surface currents", font=dict(size=18)),
        xaxis=dict(title=dict(text="Residual component (m/s)", font=dict(size=14)),
                   tickfont=dict(size=12), showgrid=True, gridcolor="#e5e7eb"),
        yaxis=dict(title=dict(text="OSCAR component (m/s)", font=dict(size=14)),
                   tickfont=dict(size=12), showgrid=True, gridcolor="#e5e7eb"),
        height=440,
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=55, r=30, t=55, b=50),
    )
    return fig


# ──────────────────────────────────────────────────────────────────────
# C3 — Storm response
# ──────────────────────────────────────────────────────────────────────
def build_storm_event_table(df: pd.DataFrame) -> pd.DataFrame:
    """Return a compact storm summary keyed by storm_event_id."""
    tagged = detect_storms(df)
    if "storm_event_id" not in tagged.columns:
        return pd.DataFrame(columns=["id", "type", "start", "end", "duration_h", "peak_Hs", "peak_U10"])
    hs_col = "Hs" if "Hs" in tagged.columns else "WAVE_H_cm"
    u_col = "U10" if "U10" in tagged.columns else "WIND_SPD_cms"
    rows = []
    for ev, sub in tagged[tagged["storm"]].groupby("storm_event_id"):
        if ev == 0:
            continue
        ts = pd.to_datetime(sub.get("Timestamp"), utc=True, errors="coerce")
        hs_series = pd.to_numeric(sub.get(hs_col, pd.Series(np.nan)), errors="coerce")
        u_series = pd.to_numeric(sub.get(u_col, pd.Series(np.nan)), errors="coerce")
        if hs_col == "WAVE_H_cm":
            hs_series = hs_series / 100.0
        if u_col == "WIND_SPD_cms":
            u_series = u_series / 100.0
        rows.append({
            "id": int(ev),
            "type": sub["storm_type"].mode().iloc[0] if not sub["storm_type"].mode().empty else "",
            "start": ts.min(),
            "end": ts.max(),
            "duration_h": float((ts.max() - ts.min()).total_seconds() / 3600.0),
            "peak_Hs": float(hs_series.max()) if not hs_series.empty else float("nan"),
            "peak_U10": float(u_series.max()) if not u_series.empty else float("nan"),
        })
    return pd.DataFrame(rows)


def build_epoch_multipanel(df: pd.DataFrame, variables: list[str] | None = None) -> Any:
    _require_plotly()
    tagged = detect_storms(df)
    if tagged["storm"].sum() == 0:
        return go.Figure().update_layout(title="No storm events detected")
    ts = pd.to_datetime(tagged.get("Timestamp"), utc=True, errors="coerce")
    events = ts[tagged["storm"]].drop_duplicates().tolist()
    if variables is None:
        wanted = [
            ("Hs", "WAVE_H_cm"),
            ("U10", "WIND_SPD_cms"),
            ("Pres", "ERA5_PRES_dPa"),
            ("SST_buoy", None),
        ]
        variables = [c for primary, fallback in wanted
                     for c in (primary, fallback) if c in tagged.columns][:4]
    if not variables:
        return go.Figure().update_layout(title="Epoch plot — no variables")
    comp = superposed_epoch(tagged, events[:10], window_hours=48, cols=variables)
    if comp.empty:
        return go.Figure().update_layout(title="Epoch plot — empty composite")

    fig = make_subplots(rows=len(variables), cols=1, shared_xaxes=True,
                        subplot_titles=variables)
    for row, var in enumerate(variables, start=1):
        grouped = comp.groupby("lag_hours")[var]
        mean = grouped.mean()
        fig.add_trace(go.Scatter(x=mean.index, y=mean.values, mode="lines",
                                 line=dict(color="blue", width=2), name=var),
                      row=row, col=1)
        fig.add_vline(x=0, line_color="red", line_dash="dash", row=row, col=1)
    fig.update_layout(
        title=dict(text="Storm superposed epoch ±48 h", font=dict(size=18)),
        height=max(280, 240 * len(variables)),
        showlegend=False,
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=60, r=30, t=60, b=50),
        font=dict(size=12),
    )
    fig.update_xaxes(
        title_text="Lag (hours)", row=len(variables), col=1,
        title_font=dict(size=14), tickfont=dict(size=12),
        showgrid=True, gridcolor="#e5e7eb",
    )
    fig.update_yaxes(tickfont=dict(size=12), showgrid=True, gridcolor="#e5e7eb")
    return fig


def build_pre_during_post_box(df: pd.DataFrame, var: str = "Hs") -> Any:
    _require_plotly()
    tagged = detect_storms(df)
    if var not in tagged.columns:
        if var == "Hs" and "WAVE_H_cm" in tagged.columns:
            tagged["Hs"] = pd.to_numeric(tagged["WAVE_H_cm"], errors="coerce") / 100.0
        else:
            return go.Figure().update_layout(title=f"Pre/during/post — {var} missing")
    tagged["phase"] = "pre"
    tagged.loc[tagged["storm"], "phase"] = "during"
    if "storm_event_id" in tagged.columns:
        ev_ids = tagged.loc[tagged["storm"], "storm_event_id"].unique()
        for ev in ev_ids:
            end_idx = tagged.index[(tagged["storm_event_id"] == ev) & tagged["storm"]].max()
            post_idx = tagged.index[tagged.index > end_idx][:6]  # next 6 samples
            tagged.loc[post_idx, "phase"] = "post"
    fig = go.Figure()
    for phase in ("pre", "during", "post"):
        sub = tagged[tagged["phase"] == phase]
        if sub.empty:
            continue
        fig.add_trace(go.Box(y=pd.to_numeric(sub[var], errors="coerce"), name=phase))
    fig.update_layout(
        title=dict(text=f"Pre / during / post storm {var}", font=dict(size=17)),
        yaxis=dict(title=dict(text=var, font=dict(size=14)),
                   tickfont=dict(size=12), showgrid=True, gridcolor="#e5e7eb"),
        xaxis=dict(tickfont=dict(size=12)),
        height=400,
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=55, r=25, t=55, b=45),
    )
    return fig


__all__ = [
    "NIILER_PADUAN_ALPHA",
    "POULAIN_ALPHA_LOW",
    "POULAIN_ALPHA_HIGH",
    "DESCRIPTIONS",
    "build_trajectory_speed_colored",
    "build_stick_plot_drift",
    "build_cumulative_distance",
    "build_daily_displacement",
    "build_alpha_timeseries",
    "build_theta_histogram",
    "build_wind_and_drift_rose",
    "build_residual_vs_oscar",
    "build_storm_event_table",
    "build_epoch_multipanel",
    "build_pre_during_post_box",
]
