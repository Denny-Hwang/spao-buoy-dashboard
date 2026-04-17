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
    "OISST":     ("SAT_SST_OISST",    "SAT_SST_OISST_cC"),
    "ERA5":      ("SAT_SST_ERA5",     "SAT_SST_ERA5_cC"),
    "MUR":       ("SAT_SST_MUR",      "SAT_SST_MUR_cC"),
    "OSTIA":     ("SAT_SST_OSTIA",    "SAT_SST_OSTIA_cC"),
    "OpenMeteo": ("SAT_SST_OPENMETEO", "SAT_SST_OPENMETEO_cC"),
}

BUOY_SST_ALIASES = ("SST_buoy", "sst_buoy", "SST", "Water Temp", "Water_Temp", "WaterTemp")
BUOY_INTERNAL_TEMP_ALIASES = (
    "Internal Temp", "Internal_Temp", "InternalTemp",
    "Int Temp", "Int_Temp", "internal_temp",
)
# Land / coastal context references. ``ERA5_AIRT_cC`` is 2m air
# temperature from the Open-Meteo Archive (ERA5) fetcher; it is
# populated EVERYWHERE including inland deployments (Richland, WA) so
# we use it as the "what the weather station would report" reference
# when satellite SST products are masked. Stored in hundredths of °C.
LAND_AIR_TEMP_ALIASES = ("ERA5_AIRT_cC", "ERA5_AIRT")


# One-line descriptions used by the Streamlit page to explain each plot
# directly under its title.
DESCRIPTIONS: dict[str, str] = {
    "timeseries": (
        "Buoy SST (dots) overlaid on each satellite / reanalysis SST product "
        "(solid lines). Looks for cold / warm biases and missing coverage."
    ),
    "residual_hist": (
        "Distribution of buoy − reference SST differences with a Gaussian fit — "
        "a symmetric zero-centred histogram means no systematic bias."
    ),
    "taylor": (
        "Taylor diagram — each product's radial position is its std-dev ratio "
        "and its angle is the correlation with the buoy, so the product "
        "closest to the reference point agrees best with the buoy."
    ),
    "target": (
        "Target diagram — normalized bias (y) vs unbiased RMSE (x). Products "
        "inside the unit circle agree with the buoy to within one std-dev."
    ),
    "metrics_table": (
        "Scalar validation metrics per product: number of paired samples, "
        "bias, RMSE, unbiased RMSE, Δstd, correlation."
    ),
    "pairwise_bias": (
        "Mean (buoy − product) bias per SST product — a quick side-by-side "
        "ranking of how each reference compares to the buoy sensor."
    ),
    "drift_ts": (
        "Residual (buoy − reference) over time with Theil-Sen trend line — "
        "used to catch slow sensor drift (|slope| > 0.01 °C/week triggers an "
        "alarm)."
    ),
    "drift_box": (
        "Weekly residual boxplots — visual check for stable median and "
        "tightening IQR over the deployment."
    ),
    "cusum": (
        "Cumulative sum (CUSUM) of residuals — vertical lines flag the "
        "samples at which CUSUM exceeds the alarm threshold, i.e. a change "
        "point in the bias."
    ),
    "diurnal": (
        "Hour-of-day mean buoy SST vs the reference's daily mean — highlights "
        "diurnal warming cycles that bulk satellite SST cannot resolve."
    ),
    "amplitude_vs_wind": (
        "Daily diurnal-amplitude (max − min) vs daily-mean wind speed, "
        "overlaid with Kawai & Wada (2007) empirical envelope A = 2.5·U⁻¹."
    ),
    "internal_vs_air_diag": (
        "Diagnostic: hull internal temperature vs ERA5 2 m air "
        "temperature on the same time axis, with their difference "
        "Δ = internal − air on the right axis. They should be positively "
        "correlated; a near-zero / negative correlation flags a unit, "
        "scale, or timezone problem in one of the streams."
    ),
}


# Descriptions of each reference product — surfaced in an expander on
# page 8 so scientists know exactly what they're comparing against.
PRODUCT_INFO: dict[str, dict[str, str]] = {
    "Buoy": {
        "source":  "Buoy external SST sensor (thermistor at hull)",
        "access":  "Decoded from RockBLOCK satellite telemetry, 1 sample ~ 30 min",
        "resolution": "Point measurement (the buoy itself)",
        "bias":    "Skin-effect warm bias possible in low-wind sun; no bulk SST correction applied",
    },
    "OISST": {
        "source":  "NOAA Optimum Interpolation SST v2.1 (AVHRR + in-situ blended)",
        "access":  "ERDDAP griddap `ncdcOisst21Agg_LonPM180`, daily",
        "resolution": "0.25° (~25 km) daily mean, global",
        "bias":    "Bulk SST; under-estimates skin during diurnal peak. Masked on land.",
    },
    "MUR": {
        "source":  "JPL MUR (Multi-scale Ultra-high Resolution) L4 GHRSST",
        "access":  "ERDDAP griddap `jplMURSST41`, daily",
        "resolution": "0.01° (~1 km) daily foundation SST, global",
        "bias":    "Foundation SST (diurnal cycle removed by construction). Masked on land.",
    },
    "OSTIA": {
        "source":  "UKMO OSTIA Global Ocean SST Analysis (Copernicus CMEMS)",
        "access":  "Copernicus Marine SDK `copernicusmarine` subset, daily",
        "resolution": "0.05° (~5 km) daily foundation SST, global",
        "bias":    "Foundation SST; 24-h lag. Masked on land.",
    },
    "ERA5": {
        "source":  "ECMWF ERA5 reanalysis surface SST (via Open-Meteo Marine)",
        "access":  "Open-Meteo Marine API `sea_surface_temperature`, hourly",
        "resolution": "~0.25° reanalysis, hourly, global over ocean",
        "bias":    "Model-assimilated; reacts to wind but not instantaneous microscale events.",
    },
    "OpenMeteo": {
        "source":  "Open-Meteo unified surface temperature (Marine + ERA5-Land)",
        "access":  "Marine `sea_surface_temperature` with ERA5-Land `soil_temperature_0cm` fallback",
        "resolution": "~0.1° hourly — works over ocean AND land (coastal/inland deployments)",
        "bias":    "Over land this is soil skin temperature, NOT water SST — use with care near shore.",
    },
}


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


def extract_buoy_internal_temp(df: pd.DataFrame) -> pd.Series | None:
    """Return the buoy internal temperature series (°C) when present."""
    col = _column_or_none(df, BUOY_INTERNAL_TEMP_ALIASES)
    if col is None:
        return None
    return pd.to_numeric(df[col], errors="coerce")


def extract_land_air_temp(df: pd.DataFrame) -> pd.Series | None:
    """Return ERA5 2m air temperature (°C) when present.

    Useful as a reference overlay on inland / coastal buoys where the
    satellite SST products are land-masked — air temp at the buoy's
    location is often the best "weather-station-grade" reference.
    The underlying column is stored in hundredths of °C, so we divide
    by 100 when the suffix matches.
    """
    col = _column_or_none(df, LAND_AIR_TEMP_ALIASES)
    if col is None:
        return None
    s = pd.to_numeric(df[col], errors="coerce")
    if col.endswith("_cC"):
        s = s / 100.0
    return s


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


_PRODUCT_COLORS: dict[str, str] = {
    "OISST":     "#0078D4",   # PNNL accent blue
    "MUR":       "#C62828",   # Red
    "OSTIA":     "#2E7D32",   # Green
    "ERA5":      "#F0AB00",   # Battelle orange
    "OpenMeteo": "#5E35B1",   # Purple (coastal / inland fallback)
}


# Buoy is the point-truth in every panel — give it a dedicated palette
# that does not collide with any satellite product so the eye finds it
# first. PNNL deep blue (single device) and a contrasting set when
# multiple devices co-exist on one chart.
_BUOY_PRIMARY_COLOR = "#003E6B"
_BUOY_DEVICE_COLORS: tuple[str, ...] = (
    "#003E6B",  # PNNL deep blue
    "#1B5E20",  # Forest green
    "#4527A0",  # Indigo
    "#BF360C",  # Burnt orange
    "#37474F",  # Dark slate
)


def _resolve_ts_col(df: pd.DataFrame, ts_col: str | None) -> str | None:
    """Return the best timestamp column name present in ``df``."""
    if ts_col and ts_col in df.columns:
        return ts_col
    for candidate in ("Timestamp", "Transmit Time", "Date", "Time", "time", "timestamp"):
        if candidate in df.columns:
            return candidate
    # Fuzzy fallback: first column whose name contains a time keyword.
    for c in df.columns:
        cl = c.lower()
        if "time" in cl or "date" in cl or "timestamp" in cl:
            return c
    return None


def _resolve_dev_col(df: pd.DataFrame) -> str | None:
    for c in ("Device", "Device Tab", "device", "device_tab"):
        if c in df.columns:
            return c
    return None


def build_sst_timeseries(
    df: pd.DataFrame,
    ts_col: str | None = None,
    *,
    include_internal_temp: bool = False,
    include_land_air_temp: bool = False,
) -> Any:
    """Buoy SST (per device) vs satellite/reanalysis products over time.

    ``ts_col`` is auto-detected from a small set of common aliases when
    None, so pages that don't ship a literal ``Timestamp`` column still
    render correctly. When the frame has multiple devices the buoy
    points are colored per device so overlapping deployments stay
    distinguishable. The buoy track is rendered as connected
    larger-than-default markers in PNNL blue with a white outline so it
    pops above the satellite/reanalysis reference lines and the optional
    internal/air overlays.
    """
    _require_plotly()
    fig = go.Figure()

    # Lazy import so this module stays usable under the Streamlit stub.
    try:
        from utils.plot_utils import apply_plot_style
    except Exception:  # pragma: no cover
        apply_plot_style = None  # type: ignore[assignment]

    resolved_ts = _resolve_ts_col(df, ts_col)
    if resolved_ts is None:
        fig.update_layout(
            title="Sea surface temperature — no time column found",
            xaxis_title="Time", yaxis_title="SST (°C)",
        )
        return fig

    ts = pd.to_datetime(df[resolved_ts], utc=True, errors="coerce")
    buoy = extract_buoy_sst(df)
    dev_col = _resolve_dev_col(df)

    # Buoy points — one series per device when device info is present.
    # The buoy is the truth source for B1/B2/B3 stats so we render it
    # as the visually dominant trace: larger markers, a thin connecting
    # line, an outline for contrast against satellite curves and the
    # PNNL blue palette so it stays distinct from any reference colour.
    if buoy is not None:
        if dev_col is not None:
            devices = list(pd.Series(df[dev_col]).dropna().unique())
            for di, device in enumerate(devices):
                mask = df[dev_col] == device
                yb = buoy.loc[mask]
                xb = ts.loc[mask]
                if not yb.notna().any():
                    continue
                color = _BUOY_DEVICE_COLORS[di % len(_BUOY_DEVICE_COLORS)]
                fig.add_trace(go.Scatter(
                    x=xb, y=yb,
                    mode="lines+markers",
                    name=f"Buoy — {device}",
                    line=dict(width=1.5, color=color),
                    marker=dict(
                        size=8,
                        color=color,
                        symbol="circle",
                        line=dict(width=1.0, color="white"),
                    ),
                ))
        else:
            fig.add_trace(go.Scatter(
                x=ts, y=buoy, mode="lines+markers", name="Buoy (point truth)",
                line=dict(width=1.5, color=_BUOY_PRIMARY_COLOR),
                marker=dict(
                    size=8,
                    color=_BUOY_PRIMARY_COLOR,
                    line=dict(width=1.0, color="white"),
                ),
            ))

    # Satellite / reanalysis products as solid lines in product-specific colors.
    for name, series in extract_products(df).items():
        if not series.notna().any():
            continue
        color = _PRODUCT_COLORS.get(name, "#5A5A5A")
        fig.add_trace(go.Scatter(
            x=ts, y=series, mode="lines",
            name=name,
            line=dict(width=2, color=color),
        ))

    # Optional overlay: buoy internal temperature (inside the hull, NOT
    # water SST). Useful to investigate thermal coupling / drift.
    if include_internal_temp:
        itemp = extract_buoy_internal_temp(df)
        if itemp is not None and itemp.notna().any():
            fig.add_trace(go.Scatter(
                x=ts, y=itemp, mode="lines",
                name="Buoy internal temp (hull, NOT water)",
                line=dict(width=1.2, color="#9CA3AF", dash="dot"),
                opacity=0.7,
            ))

    # Optional overlay: ERA5 2m air temperature at the buoy location.
    # Essential reference for inland / coastal deployments where all
    # satellite SST products are masked — the user still sees *some*
    # land-weather curve to interpret the buoy SST against.
    if include_land_air_temp:
        airt = extract_land_air_temp(df)
        if airt is not None and airt.notna().any():
            fig.add_trace(go.Scatter(
                x=ts, y=airt, mode="lines",
                name="Land / air temp (ERA5 2 m)",
                line=dict(width=1.4, color="#8E24AA", dash="dashdot"),
                opacity=0.75,
            ))

    if apply_plot_style is not None:
        apply_plot_style(
            fig,
            title="Sea surface temperature — buoy vs satellite products",
            x_title="Time",
            y_title="SST (°C)",
        )
    else:  # pragma: no cover
        fig.update_layout(
            title="Sea surface temperature — buoy vs satellite products",
            xaxis_title="Time", yaxis_title="SST (°C)",
        )
    return fig


def build_internal_vs_air_diagnostic(
    df: pd.DataFrame,
    ts_col: str | None = None,
) -> dict:
    """Diagnostic comparison of buoy hull temperature vs ERA5 2 m air temp.

    Returns ``{"fig": Figure, "stats": {...}}`` where the figure shows
    both raw °C curves on a shared y-axis plus a Δ(internal − air)
    secondary axis so the reader can confirm whether the two streams
    actually move together (positive correlation) or are drifting in
    opposite directions (negative correlation).

    The accompanying stats dict reports sample count, mean/std of each
    series, mean delta, the Pearson correlation, and whether the time
    bases line up — useful for flagging timezone or sample-alignment
    bugs that pure visual inspection might miss.
    """
    _require_plotly()
    out: dict = {"stats": {
        "n": 0, "mean_internal": float("nan"), "mean_air": float("nan"),
        "mean_delta": float("nan"), "correlation": float("nan"),
        "ts_overlap_hours": float("nan"),
    }}
    resolved_ts = _resolve_ts_col(df, ts_col)
    itemp = extract_buoy_internal_temp(df)
    airt = extract_land_air_temp(df)
    if resolved_ts is None or itemp is None or airt is None:
        out["fig"] = go.Figure().update_layout(
            title="Internal vs air temp diagnostic — required columns missing",
        )
        return out

    ts = pd.to_datetime(df[resolved_ts], utc=True, errors="coerce")
    frame = pd.DataFrame({"ts": ts, "internal": itemp, "air": airt}).dropna()
    if frame.empty:
        out["fig"] = go.Figure().update_layout(
            title="Internal vs air temp diagnostic — no overlapping samples",
        )
        return out
    frame = frame.sort_values("ts")
    frame["delta"] = frame["internal"] - frame["air"]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=frame["ts"], y=frame["internal"], mode="lines+markers",
        name="Internal (hull)", line=dict(color="#5A5A5A", width=1.6),
        marker=dict(size=4),
    ))
    fig.add_trace(go.Scatter(
        x=frame["ts"], y=frame["air"], mode="lines+markers",
        name="Air (ERA5 2 m)", line=dict(color="#8E24AA", width=1.6, dash="dashdot"),
        marker=dict(size=4),
    ))
    fig.add_trace(go.Scatter(
        x=frame["ts"], y=frame["delta"], mode="lines",
        name="Δ = internal − air",
        line=dict(color="#C62828", width=1.4, dash="dot"),
        yaxis="y2", opacity=0.85,
    ))
    fig.add_hline(
        y=0, line_color="#C62828", line_dash="dot",
        line_width=0.8, opacity=0.5,
        annotation_text="Δ = 0", annotation_position="top right",
        annotation_font=dict(color="#C62828"),
    )
    fig.update_layout(
        title=dict(
            text="Hull vs ERA5 air temperature — sanity check",
            font=dict(size=18),
        ),
        xaxis=dict(title="Time (UTC)"),
        yaxis=dict(title="Temperature (°C)"),
        yaxis2=dict(
            title=dict(text="Δ internal − air (°C)", font=dict(color="#C62828")),
            overlaying="y", side="right", showgrid=False,
            tickfont=dict(color="#C62828"),
        ),
        height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1.0),
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=60, r=60, t=70, b=50),
    )

    corr = float(frame["internal"].corr(frame["air"])) if len(frame) > 1 else float("nan")
    overlap_hours = (
        (frame["ts"].max() - frame["ts"].min()).total_seconds() / 3600.0
        if len(frame) > 1 else 0.0
    )
    out["fig"] = fig
    out["stats"] = {
        "n": int(len(frame)),
        "mean_internal": float(frame["internal"].mean()),
        "mean_air": float(frame["air"].mean()),
        "mean_delta": float(frame["delta"].mean()),
        "correlation": corr,
        "ts_overlap_hours": float(overlap_hours),
    }
    return out


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


def build_pairwise_bias_bar(df: pd.DataFrame) -> Any:
    """Bar chart of mean (buoy - product) per SST product — a one-look
    ranking of which reference disagrees least with the buoy.
    """
    _require_plotly()
    buoy = extract_buoy_sst(df)
    prods = extract_products(df)
    if buoy is None or not prods:
        return go.Figure().update_layout(title="Pairwise bias — data missing")
    names: list[str] = []
    biases: list[float] = []
    ns: list[int] = []
    for name, series in prods.items():
        if not series.notna().any():
            continue
        diff = (buoy - series).dropna()
        if diff.empty:
            continue
        names.append(name)
        biases.append(float(diff.mean()))
        ns.append(int(len(diff)))
    if not names:
        return go.Figure().update_layout(title="Pairwise bias — no overlap")
    colors = [_PRODUCT_COLORS.get(n, "#5A5A5A") for n in names]
    fig = go.Figure(go.Bar(
        x=names, y=biases, marker=dict(color=colors),
        text=[f"{b:+.2f} °C<br>N={n}" for b, n in zip(biases, ns)],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Bias = %{y:+.3f} °C<extra></extra>",
    ))
    fig.add_hline(y=0, line_color="black", line_width=1)
    fig.update_layout(
        title=dict(text="Mean bias: buoy − product", font=dict(size=18)),
        yaxis_title="Bias (°C)",
        height=420,
        margin=dict(l=60, r=30, t=60, b=50),
        plot_bgcolor="white", paper_bgcolor="white",
    )
    return fig


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
def build_diurnal_composite(
    df: pd.DataFrame,
    ts_col: str = "Timestamp",
    ref: str = "OISST",
    *,
    include_internal_temp: bool = False,
    include_land_air_temp: bool = False,
) -> Any:
    _require_plotly()
    buoy = extract_buoy_sst(df)
    prods = extract_products(df)
    if buoy is None:
        return go.Figure().update_layout(title="Diurnal composite — no buoy SST")
    ts = pd.to_datetime(df.get(ts_col, pd.Series(index=df.index)), utc=True, errors="coerce")
    frame = pd.DataFrame({"ts": ts, "buoy": buoy}).dropna()
    if ref in prods:
        frame["ref"] = prods[ref].reindex(frame.index)
    if include_internal_temp:
        itemp = extract_buoy_internal_temp(df)
        if itemp is not None:
            frame["itemp"] = itemp.reindex(frame.index)
    if include_land_air_temp:
        airt = extract_land_air_temp(df)
        if airt is not None:
            frame["airt"] = airt.reindex(frame.index)
    if frame.empty:
        return go.Figure().update_layout(title="Diurnal composite — no data")
    frame["hour"] = frame["ts"].dt.hour
    buoy_mean = frame.groupby("hour")["buoy"].mean()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=buoy_mean.index, y=buoy_mean.values, mode="lines+markers",
        name="buoy SST (hour-of-day mean)",
        line=dict(color="#003E6B", width=2),
        marker=dict(size=8),
    ))
    if "itemp" in frame.columns:
        itemp_mean = frame.groupby("hour")["itemp"].mean()
        if itemp_mean.notna().any():
            fig.add_trace(go.Scatter(
                x=itemp_mean.index, y=itemp_mean.values,
                mode="lines+markers",
                name="buoy internal temp (hour-of-day mean)",
                line=dict(color="#888888", width=2, dash="dot"),
                marker=dict(size=6),
            ))
    if "airt" in frame.columns:
        airt_mean = frame.groupby("hour")["airt"].mean()
        if airt_mean.notna().any():
            fig.add_trace(go.Scatter(
                x=airt_mean.index, y=airt_mean.values,
                mode="lines+markers",
                name="land / air temp (ERA5 2 m, hour-of-day mean)",
                line=dict(color="#8E24AA", width=2, dash="dashdot"),
                marker=dict(size=6),
            ))
    if "ref" in frame.columns:
        ref_mean = frame["ref"].mean()
        if np.isfinite(ref_mean):
            fig.add_hline(y=ref_mean, line_dash="dash", line_color="grey",
                          annotation_text=f"{ref} daily mean")
    fig.update_layout(
        title=dict(text="Diurnal warming composite", font=dict(size=18)),
        xaxis_title="Hour of day (UTC)",
        yaxis_title="Temperature (°C)",
        height=460,
        plot_bgcolor="white", paper_bgcolor="white",
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
    "BUOY_INTERNAL_TEMP_ALIASES",
    "LAND_AIR_TEMP_ALIASES",
    "DESCRIPTIONS",
    "PRODUCT_INFO",
    "extract_products",
    "extract_buoy_sst",
    "extract_buoy_internal_temp",
    "extract_land_air_temp",
    "build_metrics_table",
    "build_sst_timeseries",
    "build_residual_histogram",
    "build_taylor",
    "build_target",
    "build_pairwise_bias_bar",
    "build_drift_timeseries",
    "build_drift_boxplot",
    "build_cusum_chart",
    "build_diurnal_composite",
    "build_amplitude_vs_wind",
    "build_internal_vs_air_diagnostic",
]
