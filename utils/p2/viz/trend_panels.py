"""
Long-term trend panels backed by the ``Derived_Daily`` worksheet.

Panels:
    * :func:`build_teng_long_trend`  —  η₁ mean with Theil-Sen overlay
    * :func:`build_sst_bias_trend`   —  30-day bias time series per product
"""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd

try:
    import plotly.graph_objects as go  # type: ignore
except Exception:  # pragma: no cover
    go = None  # type: ignore[assignment]

from ..stats.trends import theil_sen


SST_BIAS_COLUMNS = (
    "sst_bias_OISST",
    "sst_bias_ERA5",
    "sst_bias_MUR",
    "sst_bias_OSTIA",
)


def _require_plotly() -> None:
    if go is None:  # pragma: no cover
        raise RuntimeError("plotly is required for utils.p2.viz.trend_panels")


def _date_series(df: pd.DataFrame) -> pd.Series:
    if "date" not in df.columns:
        return pd.Series(pd.NaT, index=df.index)
    return pd.to_datetime(df["date"], errors="coerce")


def build_teng_long_trend(
    daily: pd.DataFrame,
    col: str = "teng_eta_l1_mean",
) -> Any:
    """Return a time-series figure of the long-term TENG η₁ mean.

    The figure overlays the Theil-Sen fit computed on the full series
    plus the pre-computed 7-day rolling slope (if present).
    """
    _require_plotly()
    if daily is None or daily.empty or col not in daily.columns:
        return go.Figure().update_layout(title="TENG long-term trend — no data")

    dates = _date_series(daily)
    values = pd.to_numeric(daily[col], errors="coerce")
    frame = pd.DataFrame({"date": dates, "val": values}).dropna()
    if frame.empty:
        return go.Figure().update_layout(title="TENG long-term trend — no data")
    frame = frame.sort_values("date").reset_index(drop=True)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=frame["date"], y=frame["val"], mode="lines+markers",
        name="η₁ daily mean", marker=dict(size=6),
    ))

    # Theil-Sen on the whole series.
    if len(frame) >= 3:
        x_days = (frame["date"] - frame["date"].min()).dt.total_seconds() / 86400.0
        fit = theil_sen(frame["val"].to_numpy(), x_days.to_numpy())
        if np.isfinite(fit["slope"]):
            xs = np.array([frame["date"].min(), frame["date"].max()])
            xd = np.array([0.0, x_days.max()])
            ys = fit["intercept"] + fit["slope"] * xd
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="lines",
                line=dict(color="black", dash="dash"),
                name=f"Theil-Sen {fit['slope']:+.3g}/day",
            ))

    # Rolling slope if available.
    if "teng_eta_l1_slope" in daily.columns:
        slope = pd.to_numeric(daily["teng_eta_l1_slope"], errors="coerce")
        slope_frame = pd.DataFrame({"date": dates, "slope": slope}).dropna()
        if not slope_frame.empty:
            fig.add_trace(go.Scatter(
                x=slope_frame["date"], y=slope_frame["slope"],
                mode="lines", name="7-day rolling slope",
                line=dict(color="orange", width=1, dash="dot"),
                yaxis="y2",
            ))
            fig.update_layout(
                yaxis2=dict(
                    overlaying="y", side="right",
                    title="Rolling slope (units/day)",
                    showgrid=False,
                )
            )

    fig.update_layout(
        title="TENG η₁ long-term trend (Derived_Daily)",
        xaxis_title="Date",
        yaxis_title="η₁ = P_TENG / Hs²",
    )
    return fig


def build_sst_bias_trend(
    daily: pd.DataFrame,
    products: Iterable[str] | None = None,
    window_days: int = 30,
) -> Any:
    """Return a multi-line time series of ``sst_bias_*`` columns.

    Filters to the most recent ``window_days`` of data and draws one
    line per SST product plus a grey zero reference.
    """
    _require_plotly()
    if daily is None or daily.empty:
        return go.Figure().update_layout(title="SST bias trend — no data")

    selected = list(products) if products is not None else list(SST_BIAS_COLUMNS)
    selected = [c for c in selected if c in daily.columns]
    if not selected:
        return go.Figure().update_layout(title="SST bias trend — no columns")

    dates = _date_series(daily)
    frame = pd.DataFrame({"date": dates})
    for col in selected:
        frame[col] = pd.to_numeric(daily[col], errors="coerce")
    frame = frame.dropna(subset=["date"]).sort_values("date")
    if frame.empty:
        return go.Figure().update_layout(title="SST bias trend — no data")

    cutoff = frame["date"].max() - pd.Timedelta(days=window_days)
    recent = frame[frame["date"] >= cutoff]
    if recent.empty:
        recent = frame

    fig = go.Figure()
    for col in selected:
        label = col.replace("sst_bias_", "")
        fig.add_trace(go.Scatter(
            x=recent["date"], y=recent[col], mode="lines+markers",
            name=label,
        ))
    fig.add_hline(y=0, line_color="grey", line_dash="dot")
    fig.update_layout(
        title=f"SST bias (buoy − product) — last {window_days} days",
        xaxis_title="Date", yaxis_title="Bias (°C)",
    )
    return fig


__all__ = ["SST_BIAS_COLUMNS", "build_teng_long_trend", "build_sst_bias_trend"]
