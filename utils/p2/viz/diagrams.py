"""
Plotly visualization primitives (no Streamlit calls allowed).

All functions here return ``plotly.graph_objects.Figure`` objects so
they can be used by both Streamlit pages and standalone reports.
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd

try:
    import plotly.graph_objects as go  # type: ignore
except Exception:  # pragma: no cover
    go = None  # type: ignore[assignment]


def _require_plotly() -> None:
    if go is None:  # pragma: no cover
        raise RuntimeError("plotly is required for utils.p2.viz.diagrams")


def stick_plot(
    t: Iterable,
    u: Iterable[float],
    v: Iterable[float],
    title: str = "Stick plot",
    scale: float = 1.0,
):
    """Vector stick plot — one arrow per sample.

    Arrows point ``(u, v)`` with their tails anchored on the time axis.
    """
    _require_plotly()
    t_arr = pd.to_datetime(list(t), utc=True, errors="coerce")
    u_arr = np.asarray(list(u), dtype=float)
    v_arr = np.asarray(list(v), dtype=float)

    shapes = []
    for ti, ui, vi in zip(t_arr, u_arr, v_arr):
        if pd.isna(ti) or not (np.isfinite(ui) and np.isfinite(vi)):
            continue
        shapes.append({
            "type": "line",
            "x0": ti, "x1": ti,
            "y0": 0.0, "y1": vi * scale,
            "line": {"color": "steelblue", "width": 2},
        })

    fig = go.Figure()
    fig.update_layout(
        title=title,
        shapes=shapes,
        xaxis=dict(title="Time"),
        yaxis=dict(title="Meridional velocity (m/s)"),
        showlegend=False,
    )
    # Plot a trace of u as a reference trail.
    fig.add_trace(go.Scatter(
        x=t_arr, y=u_arr, mode="lines",
        name="u component", line=dict(color="darkorange", width=1),
    ))
    return fig


def wind_rose(
    direction_deg: Iterable[float],
    speed: Iterable[float],
    bins_dir: int = 16,
    bins_speed: Iterable[float] | None = None,
    title: str = "Wind rose",
):
    """Polar histogram of wind by direction and speed bin."""
    _require_plotly()
    d = np.asarray(list(direction_deg), dtype=float) % 360
    s = np.asarray(list(speed), dtype=float)
    mask = np.isfinite(d) & np.isfinite(s)
    d, s = d[mask], s[mask]

    dir_edges = np.linspace(0, 360, bins_dir + 1)
    if bins_speed is None:
        max_s = float(np.nanmax(s)) if s.size else 1.0
        bins_speed = np.linspace(0, max(max_s, 1.0), 6)
    speed_edges = np.asarray(list(bins_speed), dtype=float)

    fig = go.Figure()
    for lo, hi in zip(speed_edges[:-1], speed_edges[1:]):
        mask_s = (s >= lo) & (s < hi)
        hist, _ = np.histogram(d[mask_s], bins=dir_edges)
        thetas = 0.5 * (dir_edges[:-1] + dir_edges[1:])
        fig.add_trace(go.Barpolar(
            r=hist,
            theta=thetas,
            width=[360.0 / bins_dir] * bins_dir,
            name=f"{lo:.1f}–{hi:.1f} m/s",
        ))
    fig.update_layout(
        title=title,
        polar=dict(angularaxis=dict(direction="clockwise", rotation=90)),
        barmode="stack",
    )
    return fig


def target_diagram(
    obs: Iterable[float],
    refs: dict[str, Iterable[float]],
    title: str = "Target diagram",
):
    """Plot (signed uRMSE, bias) for a dictionary of references.

    Both axes are normalized by σ_obs so the unit circle corresponds
    to RMSE = σ_obs. Points inside the unit circle outperform
    climatology.
    """
    _require_plotly()
    from ..stats.quality import bias as _bias
    from ..stats.quality import correlation as _corr
    from ..stats.quality import uRMSE as _uRMSE

    sigma_obs = float(np.nanstd(np.asarray(list(obs), dtype=float), ddof=1))
    if sigma_obs == 0 or not np.isfinite(sigma_obs):
        sigma_obs = 1.0

    fig = go.Figure()
    # Unit circle and axes.
    theta = np.linspace(0, 2 * math.pi, 181)
    fig.add_trace(go.Scatter(
        x=np.cos(theta), y=np.sin(theta),
        mode="lines", line=dict(color="lightgrey", dash="dot"),
        name="σ_obs", showlegend=False,
    ))
    fig.add_hline(y=0, line_color="lightgrey")
    fig.add_vline(x=0, line_color="lightgrey")

    for name, pred in refs.items():
        b = _bias(obs, pred)
        u = _uRMSE(obs, pred)
        r = _corr(obs, pred)
        # Sign uRMSE by sign of (σ_pred - σ_obs) for conventional
        # target-diagram quadrants.
        pred_arr = np.asarray(list(pred), dtype=float)
        sigma_pred = float(np.nanstd(pred_arr, ddof=1))
        sign = 1.0 if sigma_pred >= sigma_obs else -1.0
        fig.add_trace(go.Scatter(
            x=[sign * u / sigma_obs],
            y=[b / sigma_obs],
            mode="markers+text",
            text=[name],
            textposition="top center",
            marker=dict(size=10),
            name=f"{name} (r={r:.2f})",
        ))

    fig.update_layout(
        title=title,
        xaxis=dict(title="signed uRMSE / σ_obs", zeroline=True),
        yaxis=dict(title="bias / σ_obs", zeroline=True, scaleanchor="x"),
    )
    return fig


__all__ = ["stick_plot", "wind_rose", "target_diagram"]
