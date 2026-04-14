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

from ..physics.ekman import compute_drift_velocity, decompose_drift, fit_windage
from ..physics.storms import detect_storms, superposed_epoch

NIILER_PADUAN_ALPHA = 0.007   # drogued surface drifters
POULAIN_ALPHA_LOW = 0.03      # undrogued lower
POULAIN_ALPHA_HIGH = 0.05     # undrogued upper


def _require_plotly() -> None:
    if go is None:  # pragma: no cover
        raise RuntimeError("plotly is required for utils.p2.viz.drift_panels")


# ──────────────────────────────────────────────────────────────────────
# C1 — Trajectory
# ──────────────────────────────────────────────────────────────────────
def build_trajectory_speed_colored(df: pd.DataFrame) -> Any:
    """Lat/Lon polyline coloured by instantaneous drift speed (m/s)."""
    _require_plotly()
    drift = compute_drift_velocity(df)
    if "u_drift" not in drift.columns:
        return go.Figure().update_layout(title="Trajectory — no drift data")
    lat = pd.to_numeric(drift.get("Lat"), errors="coerce")
    lon = pd.to_numeric(drift.get("Lon"), errors="coerce")
    speed = np.sqrt(drift["u_drift"] ** 2 + drift["v_drift"] ** 2)
    mask = np.isfinite(lat) & np.isfinite(lon) & np.isfinite(speed)
    fig = go.Figure()
    fig.add_trace(go.Scattergeo(
        lon=lon[mask], lat=lat[mask], mode="lines+markers",
        marker=dict(size=6, color=speed[mask], colorscale="Viridis",
                    colorbar=dict(title="Speed (m/s)")),
        line=dict(width=2, color="rgba(0,0,0,0.4)"),
        name="trajectory",
    ))
    fig.update_layout(
        title="Trajectory (speed-coloured)",
        geo=dict(projection_type="natural earth", showland=True, showocean=True,
                 landcolor="lightgrey", oceancolor="lightblue"),
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
        title="Drift velocity stick plot",
        xaxis_title="Time",
        yaxis_title="Meridional velocity (m/s)",
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
    fig = go.Figure(go.Scatter(x=ts, y=cum_km, mode="lines", name="cumulative"))
    fig.update_layout(title="Cumulative distance",
                      xaxis_title="Time", yaxis_title="Distance (km)")
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
    fig = go.Figure(go.Bar(x=list(daily.index), y=daily.values, name="displacement"))
    fig.update_layout(title="Daily displacement",
                      xaxis_title="Date", yaxis_title="Distance (km)")
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
        title="Rolling windage coefficient α(t)",
        xaxis_title="Time", yaxis_title="α (unitless)",
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
        title="Deflection angle histogram",
        xaxis_title="θ (degrees, CCW positive)",
        yaxis_title="count",
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
    fig.update_layout(title=title,
                      polar=dict(angularaxis=dict(direction="clockwise", rotation=90)))
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
        title="Residual drift vs OSCAR surface currents",
        xaxis_title="Residual component (m/s)",
        yaxis_title="OSCAR component (m/s)",
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
    fig.update_layout(title="Storm superposed epoch ±48 h",
                      height=220 * len(variables),
                      showlegend=False)
    fig.update_xaxes(title_text="Lag (hours)", row=len(variables), col=1)
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
    fig.update_layout(title=f"Pre / during / post storm {var}",
                      yaxis_title=var)
    return fig


__all__ = [
    "NIILER_PADUAN_ALPHA",
    "POULAIN_ALPHA_LOW",
    "POULAIN_ALPHA_HIGH",
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
