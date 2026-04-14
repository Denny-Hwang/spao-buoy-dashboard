"""
Plotly Taylor diagram.

Reference
---------
Taylor, K. E. (2001). Summarizing multiple aspects of model performance
in a single diagram. *Journal of Geophysical Research*, 106(D7),
7183–7192. https://doi.org/10.1029/2000JD900719

A Taylor diagram encodes three statistics per reference dataset in a
single polar plot:

    radius   σ_ref                         (standard deviation)
    angle    arccos(correlation)           (azimuth)
    distance √(σ_obs² + σ_ref² − 2 σ_obs σ_ref r)  ≡ centred RMSE
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np

try:
    import plotly.graph_objects as go  # type: ignore
except Exception:  # pragma: no cover
    go = None  # type: ignore[assignment]

from .quality import _align, correlation


def _obs_std(obs: Iterable[float]) -> float:
    arr = np.asarray(list(obs), dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size < 2:
        return float("nan")
    return float(np.std(arr, ddof=1))


def taylor_stats(obs: Iterable[float], pred: Iterable[float]) -> dict:
    """Compute (σ_ref, r, crmse) for a single reference."""
    o, p = _align(obs, pred)
    if o.size < 2:
        return {"sigma": float("nan"), "r": float("nan"), "crmse": float("nan")}
    sigma_ref = float(np.std(p, ddof=1))
    r = correlation(o, p)
    sigma_obs = float(np.std(o, ddof=1))
    crmse = math.sqrt(max(sigma_obs ** 2 + sigma_ref ** 2 - 2.0 * sigma_obs * sigma_ref * r, 0.0))
    return {"sigma": sigma_ref, "r": r, "crmse": crmse}


def taylor_diagram(
    obs: Iterable[float],
    refs: dict[str, Iterable[float]],
    title: str = "Taylor diagram",
):
    """Return a ``plotly.graph_objects.Figure`` Taylor diagram.

    Each entry in ``refs`` becomes one marker at
    ``(σ_pred, arccos(r))``. A grey reference arc at ``σ_obs`` is
    drawn for visual comparison. Raises ``RuntimeError`` if plotly is
    unavailable.
    """
    if go is None:
        raise RuntimeError("plotly is required for taylor_diagram")

    sigma_obs = _obs_std(obs)
    fig = go.Figure()

    # Observation reference point on the x-axis.
    if math.isfinite(sigma_obs):
        theta_ref = np.linspace(0, 90, 91)
        fig.add_trace(
            go.Scatterpolar(
                r=[sigma_obs] * len(theta_ref),
                theta=theta_ref,
                mode="lines",
                line=dict(color="lightgrey", dash="dot"),
                name="Observed σ",
                showlegend=False,
            )
        )
        fig.add_trace(
            go.Scatterpolar(
                r=[sigma_obs], theta=[0], mode="markers",
                marker=dict(color="black", size=10, symbol="x"),
                name="Observation",
            )
        )

    for name, pred in refs.items():
        stats = taylor_stats(obs, pred)
        if not math.isfinite(stats["sigma"]) or not math.isfinite(stats["r"]):
            continue
        r = max(-1.0, min(1.0, stats["r"]))
        theta_deg = math.degrees(math.acos(r))
        fig.add_trace(
            go.Scatterpolar(
                r=[stats["sigma"]],
                theta=[theta_deg],
                mode="markers+text",
                text=[name],
                textposition="top center",
                marker=dict(size=10),
                name=name,
            )
        )

    fig.update_layout(
        title=title,
        polar=dict(
            angularaxis=dict(
                direction="clockwise",
                rotation=90,
                tickmode="array",
                tickvals=[0, 30, 60, 90],
                ticktext=["1.0", "0.87", "0.50", "0.0"],
            ),
            radialaxis=dict(title="Standard deviation"),
            sector=[0, 90],
        ),
        showlegend=True,
    )
    return fig


__all__ = ["taylor_stats", "taylor_diagram"]
