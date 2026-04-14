"""
Panel builders for page 7 — TENG Performance.

Each ``build_*`` function takes a pandas DataFrame (already
enriched with WAVE_H_cm / WAVE_T_ds and any TENG power column)
and returns a ``plotly.graph_objects.Figure`` so pages/7_*.py
can render them without any Streamlit-specific logic here.

Literature reference markers
----------------------------
- Jung et al. (2024): Hs ≈ 0.3 m, Tp ≈ 2.19 s, P_TENG ≈ 6.3 mW
- Lu et al. (2026):   Hs ≈ 3.1 m, Tp ≈ 7.0 s,  P_TENG ≈ 12.2 mW
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

try:
    import plotly.graph_objects as go  # type: ignore
except Exception:  # pragma: no cover
    go = None  # type: ignore[assignment]

from ..physics.teng_norm import (
    eta_level0,
    eta_level1,
    eta_level2,
    teng_power_mw,
)
from ..physics.wave_power import theoretical_wave_flux_w_per_m
from ..stats.trends import mann_kendall, theil_sen

JUNG_2024 = {"label": "Jung 2024", "Hs": 0.3, "Tp": 2.19, "P_mW": 6.3, "color": "royalblue"}
LU_2026 = {"label": "Lu 2026", "Hs": 3.1, "Tp": 7.0, "P_mW": 12.2, "color": "crimson"}


def _require_plotly() -> None:
    if go is None:  # pragma: no cover
        raise RuntimeError("plotly is required for utils.p2.viz.teng_panels")


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────
def _hs(df: pd.DataFrame) -> pd.Series:
    if "Hs" in df.columns:
        return pd.to_numeric(df["Hs"], errors="coerce")
    if "WAVE_H_cm" in df.columns:
        return pd.to_numeric(df["WAVE_H_cm"], errors="coerce") / 100.0
    return pd.Series(np.nan, index=df.index)


def _tp(df: pd.DataFrame) -> pd.Series:
    if "Tp" in df.columns:
        return pd.to_numeric(df["Tp"], errors="coerce")
    if "WAVE_T_ds" in df.columns:
        return pd.to_numeric(df["WAVE_T_ds"], errors="coerce") / 10.0
    return pd.Series(np.nan, index=df.index)


# ──────────────────────────────────────────────────────────────────────
# A1 — Wave-to-power transfer function
# ──────────────────────────────────────────────────────────────────────
def build_hs_tp_heatmap(df: pd.DataFrame) -> Any:
    """Hs × Tp heatmap of mean TENG power with literature markers."""
    _require_plotly()
    hs = _hs(df)
    tp = _tp(df)
    p = teng_power_mw(df)
    mask = np.isfinite(hs) & np.isfinite(tp) & np.isfinite(p)
    hs = hs[mask].to_numpy()
    tp = tp[mask].to_numpy()
    p = p[mask].to_numpy()

    hs_bins = np.linspace(0, max(5.0, float(np.nanmax(hs)) if hs.size else 1.0), 11)
    tp_bins = np.linspace(0, max(15.0, float(np.nanmax(tp)) if tp.size else 1.0), 11)

    if hs.size == 0:
        grid = np.zeros((len(tp_bins) - 1, len(hs_bins) - 1))
    else:
        sum_p, _, _ = np.histogram2d(tp, hs, bins=(tp_bins, hs_bins), weights=p)
        cnt, _, _ = np.histogram2d(tp, hs, bins=(tp_bins, hs_bins))
        with np.errstate(invalid="ignore"):
            grid = np.where(cnt > 0, sum_p / np.maximum(cnt, 1), np.nan)

    fig = go.Figure(
        go.Heatmap(
            z=grid,
            x=0.5 * (hs_bins[:-1] + hs_bins[1:]),
            y=0.5 * (tp_bins[:-1] + tp_bins[1:]),
            colorscale="Viridis",
            colorbar=dict(title="P_TENG (mW)"),
        )
    )
    for ref in (JUNG_2024, LU_2026):
        fig.add_trace(
            go.Scatter(
                x=[ref["Hs"]], y=[ref["Tp"]],
                mode="markers+text",
                marker=dict(symbol="star", size=16, color=ref["color"],
                            line=dict(width=1, color="white")),
                text=[f"{ref['label']} ({ref['P_mW']:.1f} mW)"],
                textposition="top center",
                name=ref["label"],
            )
        )
    fig.update_layout(
        title="TENG power vs sea state (Hs × Tp)",
        xaxis_title="Hs (m)", yaxis_title="Tp (s)",
    )
    return fig


def build_loglog_hs2tp(df: pd.DataFrame) -> Any:
    """Log-log P_TENG vs Hs²·Tp, coloured by Tp quartile, with fit lines."""
    _require_plotly()
    hs = _hs(df)
    tp = _tp(df)
    p = teng_power_mw(df)
    mask = np.isfinite(hs) & np.isfinite(tp) & np.isfinite(p) & (hs > 0) & (tp > 0) & (p > 0)
    hs = hs[mask]
    tp = tp[mask]
    p = p[mask]
    x = (hs * hs) * tp

    fig = go.Figure()
    if len(x) >= 4:
        quartiles = pd.qcut(tp, q=4, duplicates="drop")
        for lbl, sub in pd.DataFrame({"x": x.values, "y": p.values, "q": quartiles.values}).groupby("q"):
            fig.add_trace(
                go.Scatter(
                    x=sub["x"], y=sub["y"], mode="markers",
                    name=f"Tp {lbl}", marker=dict(size=6, opacity=0.7),
                )
            )
        # Power-law fit in log-log.
        lx = np.log10(x.values)
        ly = np.log10(p.values)
        if np.isfinite(lx).all() and np.isfinite(ly).all() and len(lx) > 2:
            a, b = np.polyfit(lx, ly, 1)
            xs = np.logspace(lx.min(), lx.max(), 50)
            ys = 10 ** (a * np.log10(xs) + b)
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="lines",
                name=f"Fit slope={a:.2f}",
                line=dict(color="black", dash="dash", width=2),
            ))
    fig.update_layout(
        title="P_TENG vs Hs² · Tp (log-log)",
        xaxis=dict(title="Hs² · Tp (m²·s)", type="log"),
        yaxis=dict(title="P_TENG (mW)", type="log"),
    )
    return fig


def build_flux_scatter(df: pd.DataFrame) -> Any:
    """P_TENG vs theoretical wave energy flux (W/m)."""
    _require_plotly()
    hs = _hs(df).to_numpy()
    tp = _tp(df).to_numpy()
    p = teng_power_mw(df).to_numpy()
    flux = theoretical_wave_flux_w_per_m(hs, tp)
    mask = np.isfinite(flux) & np.isfinite(p)
    flux = flux[mask]
    p = p[mask]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=flux, y=p, mode="markers",
        marker=dict(size=6, opacity=0.7, color="teal"),
        name="Samples",
    ))
    if len(flux) > 2 and np.any(flux > 0):
        coef = np.polyfit(flux, p, 1)
        xs = np.array([np.nanmin(flux), np.nanmax(flux)])
        fig.add_trace(go.Scatter(
            x=xs, y=np.polyval(coef, xs),
            mode="lines", line=dict(color="black", dash="dash"),
            name=f"Fit  slope={coef[0]:.2e}",
        ))
    fig.update_layout(
        title="P_TENG vs theoretical wave flux",
        xaxis_title="Wave energy flux (W/m)",
        yaxis_title="P_TENG (mW)",
    )
    return fig


# ──────────────────────────────────────────────────────────────────────
# A4 — Normalized power trend
# ──────────────────────────────────────────────────────────────────────
_LEVEL_FN = {0: eta_level0, 1: eta_level1, 2: eta_level2}
_LEVEL_LABEL = {0: "η₀ = P_TENG (mW)", 1: "η₁ = P / Hs²", 2: "η₂ = P / (Hs² · Tp)"}


def build_eta_trend(df: pd.DataFrame, level: int = 2, ts_col: str = "Timestamp") -> dict:
    """Return a time series figure plus trend stats for the chosen eta level.

    The dict has ``fig``, ``slope``, ``intercept``, ``mk_p``, ``mk_trend``,
    ``level``, ``n`` keys. ``fig`` is a Plotly Figure; the others are
    numeric metadata for the calling page to display in badges.
    """
    _require_plotly()
    level = int(level)
    if level not in _LEVEL_FN:
        raise ValueError(f"unknown level {level}")
    eta = _LEVEL_FN[level](df)
    ts = pd.to_datetime(df.get(ts_col, pd.Series(index=df.index)), utc=True, errors="coerce")
    s = pd.Series(eta.values, index=ts).dropna().sort_index()

    if len(s) < 3:
        fig = go.Figure().update_layout(title=f"{_LEVEL_LABEL[level]} — insufficient data")
        return {"fig": fig, "slope": float("nan"), "intercept": float("nan"),
                "mk_p": float("nan"), "mk_trend": "no trend", "level": level, "n": int(len(s))}

    # Rolling median + 95 % CI (empirical percentiles).
    roll = s.rolling("7D", min_periods=3)
    median = roll.median()
    low = roll.quantile(0.025)
    high = roll.quantile(0.975)

    # Theil-Sen on numeric time (days since start).
    t_days = (s.index - s.index.min()).total_seconds() / 86400.0
    ts_fit = theil_sen(s.values, t_days)
    # Mann-Kendall on raw series.
    mk = mann_kendall(s.values)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=s.index, y=s.values, mode="markers",
        name="samples", marker=dict(size=4, opacity=0.6, color="steelblue"),
    ))
    fig.add_trace(go.Scatter(
        x=median.index, y=median.values, mode="lines",
        name="7-day median", line=dict(color="orange", width=2),
    ))
    # 95 % CI ribbon from low/high.
    high_f = high.ffill().values
    low_f = low.ffill().values
    fig.add_trace(go.Scatter(
        x=np.concatenate([median.index, median.index[::-1]]),
        y=np.concatenate([high_f, low_f[::-1]]),
        fill="toself", fillcolor="rgba(255,165,0,0.15)",
        line=dict(width=0), hoverinfo="skip", name="95 % band",
        showlegend=False,
    ))
    if np.isfinite(ts_fit["slope"]):
        xfit = np.array([s.index.min(), s.index.max()])
        tfit = np.array([0.0, t_days.max()])
        yfit = ts_fit["intercept"] + ts_fit["slope"] * tfit
        fig.add_trace(go.Scatter(
            x=xfit, y=yfit, mode="lines", line=dict(color="black", dash="dash"),
            name=f"Theil-Sen slope={ts_fit['slope']:.3g}/day",
        ))
    fig.update_layout(
        title=_LEVEL_LABEL[level],
        xaxis_title="Time", yaxis_title=_LEVEL_LABEL[level],
    )
    return {
        "fig": fig,
        "slope": ts_fit["slope"],
        "intercept": ts_fit["intercept"],
        "mk_p": mk["p_value"],
        "mk_trend": mk["trend"],
        "level": level,
        "n": len(s),
    }


def build_week_violin(df: pd.DataFrame, level: int = 1, ts_col: str = "Timestamp") -> Any:
    """Matched-pair violin: first week vs last week within the same Hs bin."""
    _require_plotly()
    eta = _LEVEL_FN[level](df)
    hs = _hs(df)
    ts = pd.to_datetime(df.get(ts_col, pd.Series(index=df.index)), utc=True, errors="coerce")
    frame = pd.DataFrame({"eta": eta.values, "hs": hs.values, "ts": ts.values}).dropna()
    if frame.empty or frame["ts"].isna().all():
        return go.Figure().update_layout(title="Violin — no data")
    frame = frame.sort_values("ts")
    t0 = frame["ts"].min()
    tN = frame["ts"].max()
    week1 = frame[frame["ts"] < t0 + pd.Timedelta(days=7)].copy()
    weekN = frame[frame["ts"] > tN - pd.Timedelta(days=7)].copy()
    week1["group"] = "week 1"
    weekN["group"] = "week N"
    merged = pd.concat([week1, weekN], ignore_index=True)

    fig = go.Figure()
    for grp, color in (("week 1", "steelblue"), ("week N", "crimson")):
        sub = merged[merged["group"] == grp]
        if sub.empty:
            continue
        fig.add_trace(go.Violin(
            y=sub["eta"], x=[grp] * len(sub),
            name=grp, box_visible=True, meanline_visible=True,
            line_color=color,
        ))
    fig.update_layout(
        title=f"Matched-pair η_{level} — first vs last week",
        yaxis_title=_LEVEL_LABEL[level],
    )
    return fig


def compute_kpis(df: pd.DataFrame) -> dict:
    """Return a small dict of scalar KPIs used by the page header."""
    p = teng_power_mw(df)
    hs = _hs(df)
    tp = _tp(df)

    # Today's harvested energy in joules: integrate P_TENG (mW) assuming
    # roughly 1-hour spacing — good enough for a header KPI.
    today_mask = pd.to_datetime(
        df.get("Timestamp", pd.Series(index=df.index)), utc=True, errors="coerce"
    ).dt.date == pd.Timestamp.now(tz="UTC").date()
    today_p = p.where(today_mask, np.nan)
    today_joules = float(np.nansum(today_p * 3.6))  # mW · 3600 s / 1000 = J
    avg_p = float(np.nanmean(p)) if np.isfinite(np.nanmean(p)) else 0.0
    flux = theoretical_wave_flux_w_per_m(hs.to_numpy(), tp.to_numpy())
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = (p * 1e-3).to_numpy() / np.where(flux > 0, flux, np.nan)
    mean_ratio = float(np.nanmean(ratio)) if np.isfinite(np.nanmean(ratio)) else 0.0
    return {
        "today_joules": today_joules,
        "avg_power_mw": avg_p,
        "ratio_pct": 100.0 * mean_ratio,
    }


__all__ = [
    "JUNG_2024",
    "LU_2026",
    "build_hs_tp_heatmap",
    "build_loglog_hs2tp",
    "build_flux_scatter",
    "build_eta_trend",
    "build_week_violin",
    "compute_kpis",
]
