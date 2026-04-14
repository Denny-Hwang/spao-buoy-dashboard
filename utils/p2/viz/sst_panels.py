"""
Panel builders for page 8 — SST Validation.

Sections:
    B1  Intercomparison of buoy vs satellite/reanalysis products
    B2  Drift detection on the (buoy - OISST) residual
    B3  Diurnal warming composite and amplitude-vs-wind scatter
"""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd

try:
    import plotly.graph_objects as go  # type: ignore
    from plotly.subplots import make_subplots  # type: ignore
except Exception:  # pragma: no cover
    go = None  # type: ignore[assignment]
    make_subplots = None  # type: ignore[assignment]

from ..stats.quality import metrics_table
from ..stats.taylor import taylor_diagram
from ..stats.trends import cusum, theil_sen
from ..viz.diagrams import target_diagram


# Candidate column names for each reference product.
PRODUCT_ALIASES: dict[str, tuple[str, ...]] = {
    "OISST":  ("SAT_SST_OISST", "SAT_SST_OISST_cC"),
    "ERA5":   ("SAT_SST_ERA5",  "SAT_SST_ERA5_cC"),
    "MUR":    ("SAT_SST_MUR",   "SAT_SST_MUR_cC"),
    "OSTIA":  ("SAT_SST_OSTIA", "SAT_SST_OSTIA_cC"),
}

BUOY_SST_ALIASES = ("SST_buoy", "sst_buoy", "SST", "Water Temp", "Water_Temp", "WaterTemp")


def _require_plotly() -> None:
    if go is None:  # pragma: no cover
        raise RuntimeError("plotly is required for utils.p2.viz.sst_panels")


def _column_or_none(df: pd.DataFrame, aliases: Iterable[str]) -> str | None:
    for a in aliases:
        if a in df.columns:
            return a
    return None


def _decode_hundredths(series: pd.Series, col: str) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    if col.endswith("_cC"):
        return s / 100.0
    return s


def extract_products(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Return ``{product_name: Series}`` for every present reference."""
    out: dict[str, pd.Series] = {}
    for name, aliases in PRODUCT_ALIASES.items():
        col = _column_or_none(df, aliases)
        if col is not None:
            out[name] = _decode_hundredths(df[col], col)
    return out


def extract_buoy_sst(df: pd.DataFrame) -> pd.Series | None:
    col = _column_or_none(df, BUOY_SST_ALIASES)
    if col is None:
        return None
    return pd.to_numeric(df[col], errors="coerce")


# ──────────────────────────────────────────────────────────────────────
# B1 — Intercomparison
# ──────────────────────────────────────────────────────────────────────
def build_metrics_table(df: pd.DataFrame) -> pd.DataFrame:
    buoy = extract_buoy_sst(df)
    if buoy is None:
        return pd.DataFrame(columns=["n", "bias", "rmse", "uRMSE", "std_diff", "correlation"])
    products = extract_products(df)
    if not products:
        return pd.DataFrame()
    return metrics_table(buoy, products)


def build_sst_timeseries(df: pd.DataFrame, ts_col: str = "Timestamp") -> Any:
    _require_plotly()
    fig = go.Figure()
    ts = pd.to_datetime(df.get(ts_col, pd.Series(index=df.index)), utc=True, errors="coerce")
    buoy = extract_buoy_sst(df)
    if buoy is not None:
        fig.add_trace(go.Scatter(
            x=ts, y=buoy, mode="markers", name="Buoy",
            marker=dict(size=4, color="black"),
        ))
    for name, series in extract_products(df).items():
        fig.add_trace(go.Scatter(x=ts, y=series, mode="lines", name=name))
    fig.update_layout(
        title="Sea surface temperature — buoy vs satellite products",
        xaxis_title="Time", yaxis_title="SST (°C)",
    )
    return fig


def build_residual_histogram(df: pd.DataFrame, ref: str = "OISST") -> Any:
    _require_plotly()
    buoy = extract_buoy_sst(df)
    prods = extract_products(df)
    if buoy is None or ref not in prods:
        return go.Figure().update_layout(title=f"Residual vs {ref} — data missing")
    resid = (buoy - prods[ref]).dropna()
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=resid, nbinsx=30, name=f"buoy - {ref}"))
    if len(resid) > 2:
        mu = float(resid.mean())
        sd = float(resid.std(ddof=1))
        if sd > 0:
            xs = np.linspace(resid.min(), resid.max(), 100)
            bin_width = (resid.max() - resid.min()) / 30 if len(resid) > 0 else 1.0
            norm = (
                len(resid) * bin_width
                * np.exp(-0.5 * ((xs - mu) / sd) ** 2)
                / (sd * np.sqrt(2 * np.pi))
            )
            fig.add_trace(go.Scatter(
                x=xs, y=norm, mode="lines",
                name=f"N({mu:.2f}, {sd:.2f})",
                line=dict(color="red", dash="dash"),
            ))
    fig.update_layout(
        title=f"Residual histogram: buoy - {ref}",
        xaxis_title="°C", yaxis_title="count",
    )
    return fig


def build_taylor(df: pd.DataFrame) -> Any:
    buoy = extract_buoy_sst(df)
    prods = extract_products(df)
    if buoy is None or not prods:
        if go is None:  # pragma: no cover
            raise RuntimeError("plotly required")
        return go.Figure().update_layout(title="Taylor diagram — data missing")
    return taylor_diagram(buoy, prods, title="SST Taylor diagram")


def build_target(df: pd.DataFrame) -> Any:
    buoy = extract_buoy_sst(df)
    prods = extract_products(df)
    if buoy is None or not prods:
        if go is None:  # pragma: no cover
            raise RuntimeError("plotly required")
        return go.Figure().update_layout(title="Target diagram — data missing")
    return target_diagram(buoy, prods, title="SST target diagram")


# ──────────────────────────────────────────────────────────────────────
# B2 — Drift detection
# ──────────────────────────────────────────────────────────────────────
def build_drift_timeseries(df: pd.DataFrame, ts_col: str = "Timestamp", ref: str = "OISST") -> dict:
    _require_plotly()
    buoy = extract_buoy_sst(df)
    prods = extract_products(df)
    if buoy is None or ref not in prods:
        return {
            "fig": go.Figure().update_layout(title="Drift detection — data missing"),
            "slope_per_week": float("nan"),
            "alarm": False,
        }
    ts = pd.to_datetime(df.get(ts_col, pd.Series(index=df.index)), utc=True, errors="coerce")
    delta = (buoy - prods[ref]).astype(float)
    frame = pd.DataFrame({"ts": ts, "d": delta}).dropna().sort_values("ts")
    if frame.empty:
        return {
            "fig": go.Figure().update_layout(title="Drift detection — no overlap"),
            "slope_per_week": float("nan"),
            "alarm": False,
        }

    t_days = (frame["ts"] - frame["ts"].min()).dt.total_seconds() / 86400.0
    ts_fit = theil_sen(frame["d"].values, t_days.values)
    slope_per_week = 7.0 * ts_fit["slope"] if np.isfinite(ts_fit["slope"]) else float("nan")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=frame["ts"], y=frame["d"], mode="markers",
        name=f"Δ = buoy - {ref}", marker=dict(size=4, opacity=0.6),
    ))
    if np.isfinite(ts_fit["slope"]):
        xs = np.array([frame["ts"].min(), frame["ts"].max()])
        td = np.array([0.0, t_days.max()])
        fig.add_trace(go.Scatter(
            x=xs,
            y=ts_fit["intercept"] + ts_fit["slope"] * td,
            mode="lines", line=dict(color="red", dash="dash"),
            name=f"Theil-Sen {slope_per_week:+.3g} °C/week",
        ))
    fig.update_layout(
        title=f"Drift detection — buoy minus {ref}",
        xaxis_title="Time", yaxis_title="Δ SST (°C)",
    )
    alarm = bool(np.isfinite(slope_per_week) and abs(slope_per_week) > 0.01)
    return {"fig": fig, "slope_per_week": slope_per_week, "alarm": alarm}


def build_drift_boxplot(df: pd.DataFrame, ts_col: str = "Timestamp", ref: str = "OISST") -> Any:
    _require_plotly()
    buoy = extract_buoy_sst(df)
    prods = extract_products(df)
    if buoy is None or ref not in prods:
        return go.Figure().update_layout(title="Weekly residual — data missing")
    ts = pd.to_datetime(df.get(ts_col, pd.Series(index=df.index)), utc=True, errors="coerce")
    delta = buoy - prods[ref]
    frame = pd.DataFrame({"ts": ts, "d": delta}).dropna()
    if frame.empty:
        return go.Figure().update_layout(title="Weekly residual — no data")
    frame["week"] = frame["ts"].dt.tz_convert("UTC").dt.tz_localize(None).dt.to_period("W").astype(str)
    fig = go.Figure()
    for wk, sub in frame.groupby("week"):
        fig.add_trace(go.Box(y=sub["d"], name=wk, boxpoints=False))
    fig.update_layout(
        title=f"Weekly residual buoy - {ref}",
        xaxis_title="ISO week", yaxis_title="Δ SST (°C)",
        showlegend=False,
    )
    return fig


def build_cusum_chart(df: pd.DataFrame, ref: str = "OISST") -> Any:
    _require_plotly()
    buoy = extract_buoy_sst(df)
    prods = extract_products(df)
    if buoy is None or ref not in prods:
        return go.Figure().update_layout(title="CUSUM — data missing")
    delta = (buoy - prods[ref]).dropna().values
    if len(delta) < 3:
        return go.Figure().update_layout(title="CUSUM — insufficient data")
    out = cusum(delta)
    fig = go.Figure()
    fig.add_trace(go.Scatter(y=out["sh"], mode="lines", name="SH (upper)"))
    fig.add_trace(go.Scatter(y=out["sl"], mode="lines", name="SL (lower)"))
    for a in out["alarms"]:
        fig.add_vline(x=a, line_color="red", line_dash="dot")
    fig.update_layout(
        title=f"CUSUM of (buoy - {ref})",
        xaxis_title="sample index", yaxis_title="cumulative sum",
    )
    return fig


# ──────────────────────────────────────────────────────────────────────
# B3 — Diurnal warming
# ──────────────────────────────────────────────────────────────────────
def build_diurnal_composite(df: pd.DataFrame, ts_col: str = "Timestamp", ref: str = "OISST") -> Any:
    _require_plotly()
    buoy = extract_buoy_sst(df)
    prods = extract_products(df)
    if buoy is None:
        return go.Figure().update_layout(title="Diurnal composite — no buoy SST")
    ts = pd.to_datetime(df.get(ts_col, pd.Series(index=df.index)), utc=True, errors="coerce")
    frame = pd.DataFrame({"ts": ts, "buoy": buoy}).dropna()
    if ref in prods:
        frame["ref"] = prods[ref].reindex(frame.index)
    if frame.empty:
        return go.Figure().update_layout(title="Diurnal composite — no data")
    frame["hour"] = frame["ts"].dt.hour
    buoy_mean = frame.groupby("hour")["buoy"].mean()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=buoy_mean.index, y=buoy_mean.values, mode="lines+markers",
        name="buoy (hour-of-day mean)",
    ))
    if "ref" in frame.columns:
        ref_mean = frame["ref"].mean()
        if np.isfinite(ref_mean):
            fig.add_hline(y=ref_mean, line_dash="dash", line_color="grey",
                          annotation_text=f"{ref} daily mean")
    fig.update_layout(
        title="Diurnal warming composite",
        xaxis_title="Hour of day (UTC)",
        yaxis_title="SST (°C)",
    )
    return fig


def build_amplitude_vs_wind(df: pd.DataFrame, ts_col: str = "Timestamp") -> Any:
    """Daily amplitude (max-min) vs daily-mean wind speed.

    Overlay shows the Kawai & Wada (2007) empirical envelope
    ``A = a · U^{-b}`` with a=2.5, b=1.0 for U in m/s (qualitative).
    """
    _require_plotly()
    buoy = extract_buoy_sst(df)
    if buoy is None or "WIND_SPD_cms" not in df.columns:
        wind_col = None
        for cand in ("WIND_SPD_cms", "WIND_SPD", "WIND_SPD_mps", "U10"):
            if cand in df.columns:
                wind_col = cand
                break
        if buoy is None or wind_col is None:
            return go.Figure().update_layout(title="Amplitude vs wind — data missing")
    else:
        wind_col = "WIND_SPD_cms"
    wind = pd.to_numeric(df[wind_col], errors="coerce")
    if wind_col == "WIND_SPD_cms":
        wind = wind / 100.0
    ts = pd.to_datetime(df.get(ts_col, pd.Series(index=df.index)), utc=True, errors="coerce")

    frame = pd.DataFrame({"ts": ts, "buoy": buoy, "wind": wind}).dropna()
    if frame.empty:
        return go.Figure().update_layout(title="Amplitude vs wind — no data")
    frame["day"] = frame["ts"].dt.date
    daily = frame.groupby("day").agg(amp=("buoy", lambda s: s.max() - s.min()),
                                     wind=("wind", "mean")).dropna()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=daily["wind"], y=daily["amp"], mode="markers",
        marker=dict(size=8, opacity=0.7, color="crimson"),
        name="observed",
    ))
    if len(daily) > 0:
        xs = np.linspace(max(0.5, daily["wind"].min()), max(1.0, daily["wind"].max()), 50)
        kw = 2.5 / np.maximum(xs, 0.5)
        fig.add_trace(go.Scatter(
            x=xs, y=kw, mode="lines",
            line=dict(color="grey", dash="dash"),
            name="Kawai & Wada 2007 (empirical)",
        ))
    fig.update_layout(
        title="Daily diurnal amplitude vs daily-mean wind speed",
        xaxis_title="Wind speed (m/s)",
        yaxis_title="ΔSST amplitude (°C)",
    )
    return fig


__all__ = [
    "PRODUCT_ALIASES",
    "BUOY_SST_ALIASES",
    "extract_products",
    "extract_buoy_sst",
    "build_metrics_table",
    "build_sst_timeseries",
    "build_residual_histogram",
    "build_taylor",
    "build_target",
    "build_drift_timeseries",
    "build_drift_boxplot",
    "build_cusum_chart",
    "build_diurnal_composite",
    "build_amplitude_vs_wind",
]
