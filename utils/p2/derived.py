"""
Derived-daily aggregation logic.

Given a flat enriched buoy DataFrame (one row per raw transmission),
:func:`compute_daily_table` returns a single row per UTC date with
a stable set of summary columns consumed by the long-term trend
panels and the Derived_Daily Google Sheets worksheet.

All computation is vectorised where practical. Per-day operations
that need to call physics helpers (Ekman fit, storms) are looped
over groups but each group is small (≤ 24 records in normal
operation) so the overhead is negligible.
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd

from .physics.ekman import fit_windage
from .physics.storms import detect_storms
from .physics.teng_norm import eta_level1
from .stats.trends import theil_sen


# ──────────────────────────────────────────────────────────────────────
# Column registry
# ──────────────────────────────────────────────────────────────────────
DERIVED_DAILY_COLUMNS: list[str] = [
    "date",
    "n_records",
    "n_tx_attempted",
    "n_tx_success",
    "teng_eta_l1_mean",
    "teng_eta_l1_slope",
    "sst_bias_OISST",
    "sst_bias_ERA5",
    "sst_bias_MUR",
    "sst_bias_OSTIA",
    "sst_diurnal_amplitude",
    "drift_distance_km",
    "drift_speed_mean",
    "windage_alpha",
    "ekman_theta_deg",
    "storm_flag",
    "storm_type_dominant",
]

DERIVED_DAILY_WORKSHEET = "Derived_Daily"


_TS_ALIASES = ("Timestamp", "Receive Time", "time", "Time")
_LAT_ALIASES = (
    "Lat", "Latitude", "lat", "Lat (°)", "Latitude (°)", "Latitude (deg)",
    "GPS Lat", "GPS_Lat", "GPS Latitude", "GPS_Latitude",
)
_LON_ALIASES = (
    "Lon", "Lng", "Longitude", "lon", "Lon (°)", "Longitude (°)", "Longitude (deg)",
    "GPS Lon", "GPS_Lon", "GPS Longitude", "GPS_Longitude",
)
_TX_ATTEMPTED_ALIASES = ("tx_attempted", "Transmit Attempts", "MO_Attempts")
_TX_SUCCESS_ALIASES = ("tx_success", "Transmit Success", "CRC Valid")
_BUOY_SST_ALIASES = ("SST_buoy", "sst_buoy", "SST", "SST (°C)", "Water Temp", "Water_Temp")

_SAT_COLUMNS = {
    "OISST":  ("SAT_SST_OISST", "SAT_SST_OISST_cC"),
    "ERA5":   ("SAT_SST_ERA5",  "SAT_SST_ERA5_cC"),
    "MUR":    ("SAT_SST_MUR",   "SAT_SST_MUR_cC"),
    "OSTIA":  ("SAT_SST_OSTIA", "SAT_SST_OSTIA_cC"),
}

EARTH_RADIUS_M = 6_371_000.0


def _first_alias(df: pd.DataFrame, aliases: Iterable[str]) -> str | None:
    for a in aliases:
        if a in df.columns:
            return a
    return None


def _to_celsius(s: pd.Series, col: str) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    if col.endswith("_cC"):
        return s / 100.0
    return s


def _to_mps_from_cms(s: pd.Series, col: str) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    if col.endswith("_cms") or col == "WIND_SPD_cms":
        return s / 100.0
    return s


def _buoy_sst(df: pd.DataFrame) -> pd.Series:
    col = _first_alias(df, _BUOY_SST_ALIASES)
    if col is None:
        return pd.Series(np.nan, index=df.index)
    return pd.to_numeric(df[col], errors="coerce")


def _sat_series(df: pd.DataFrame, name: str) -> pd.Series | None:
    aliases = _SAT_COLUMNS.get(name, ())
    col = _first_alias(df, aliases)
    if col is None:
        return None
    return _to_celsius(df[col], col)


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    rlat1 = math.radians(lat1)
    rlat2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2)
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(max(0.0, min(1.0, a)))) / 1000.0


# ──────────────────────────────────────────────────────────────────────
# Per-day aggregation
# ──────────────────────────────────────────────────────────────────────
def _daily_distance_km_and_speed(sub: pd.DataFrame) -> tuple[float, float]:
    lat_col = _first_alias(sub, _LAT_ALIASES)
    lon_col = _first_alias(sub, _LON_ALIASES)
    ts_col = _first_alias(sub, _TS_ALIASES)
    if lat_col is None or lon_col is None or ts_col is None or len(sub) < 2:
        return (0.0, 0.0)
    ordered = sub.sort_values(ts_col)
    lat = pd.to_numeric(ordered[lat_col], errors="coerce").to_numpy(dtype=float)
    lon = pd.to_numeric(ordered[lon_col], errors="coerce").to_numpy(dtype=float)
    ts = pd.to_datetime(ordered[ts_col], utc=True, errors="coerce")
    dist_km = 0.0
    speeds: list[float] = []
    for i in range(1, len(ordered)):
        if not (np.isfinite(lat[i - 1]) and np.isfinite(lat[i])
                and np.isfinite(lon[i - 1]) and np.isfinite(lon[i])):
            continue
        d = _haversine_km(lat[i - 1], lon[i - 1], lat[i], lon[i])
        dt = (ts.iloc[i] - ts.iloc[i - 1]).total_seconds()
        dist_km += d
        if dt and dt > 0:
            speeds.append(d * 1000.0 / dt)  # m/s
    mean_speed = float(np.mean(speeds)) if speeds else 0.0
    return (dist_km, mean_speed)


def _daily_windage_fit(sub: pd.DataFrame) -> tuple[float, float]:
    if "u_drift" not in sub.columns or "U10" not in sub.columns:
        return (float("nan"), float("nan"))
    drift = np.column_stack([
        pd.to_numeric(sub["u_drift"], errors="coerce").to_numpy(dtype=float),
        pd.to_numeric(sub.get("v_drift", pd.Series(np.nan)), errors="coerce").to_numpy(dtype=float),
    ])
    wind = np.column_stack([
        pd.to_numeric(sub["U10"], errors="coerce").to_numpy(dtype=float),
        pd.to_numeric(sub.get("V10", pd.Series(np.nan)), errors="coerce").to_numpy(dtype=float),
    ])
    fit = fit_windage(drift, wind)
    return (fit["alpha"], fit["theta_deg"])


def _daily_storm_summary(sub: pd.DataFrame) -> tuple[bool, str]:
    try:
        tagged = detect_storms(sub)
    except Exception:
        return (False, "")
    if "storm" not in tagged.columns or not tagged["storm"].any():
        return (False, "")
    types = tagged.loc[tagged["storm"], "storm_type"].dropna()
    dominant = types.mode().iloc[0] if not types.empty else ""
    return (True, dominant)


def _diurnal_amplitude(series: pd.Series) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.size < 2:
        return float("nan")
    return float(s.max() - s.min())


def _teng_slope_over_days(per_day: pd.DataFrame, col: str) -> list[float]:
    """Rolling 7-day Theil-Sen slope of ``col`` in per-day units."""
    out: list[float] = []
    values = per_day[col].to_numpy(dtype=float)
    for i in range(len(values)):
        lo = max(0, i - 6)
        window = values[lo:i + 1]
        finite = window[np.isfinite(window)]
        if len(finite) < 3:
            out.append(float("nan"))
            continue
        x = np.arange(len(window), dtype=float)[np.isfinite(window)]
        fit = theil_sen(finite.tolist(), x.tolist())
        out.append(fit["slope"] if np.isfinite(fit["slope"]) else float("nan"))
    return out


def compute_daily_table(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate a flat enriched DataFrame into one row per UTC date.

    Parameters
    ----------
    df : DataFrame
        Must contain a timestamp column recognized by ``_TS_ALIASES``.
        All other columns are optional; missing inputs produce NaN /
        False entries in the corresponding output column.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=DERIVED_DAILY_COLUMNS)

    ts_col = _first_alias(df, _TS_ALIASES)
    if ts_col is None:
        return pd.DataFrame(columns=DERIVED_DAILY_COLUMNS)

    frame = df.copy()
    frame["_ts"] = pd.to_datetime(frame[ts_col], utc=True, errors="coerce")
    frame = frame.dropna(subset=["_ts"])
    if frame.empty:
        return pd.DataFrame(columns=DERIVED_DAILY_COLUMNS)
    frame["_date"] = frame["_ts"].dt.date

    # Pre-compute vectorised series.
    eta1 = eta_level1(frame)
    buoy = _buoy_sst(frame)
    sat = {name: _sat_series(frame, name) for name in _SAT_COLUMNS}

    tx_att_col = _first_alias(frame, _TX_ATTEMPTED_ALIASES)
    tx_suc_col = _first_alias(frame, _TX_SUCCESS_ALIASES)

    rows: list[dict] = []
    for day, sub in frame.groupby("_date", sort=True):
        n_records = int(len(sub))
        idx = sub.index

        n_tx_att = (
            int(pd.to_numeric(sub[tx_att_col], errors="coerce").fillna(0).sum())
            if tx_att_col else n_records
        )
        if tx_suc_col == "CRC Valid":
            n_tx_suc = int(sub[tx_suc_col].astype(str).str.lower().isin(("true", "1")).sum())
        elif tx_suc_col:
            n_tx_suc = int(pd.to_numeric(sub[tx_suc_col], errors="coerce").fillna(0).sum())
        else:
            n_tx_suc = n_records

        eta_mean = float(np.nanmean(eta1.loc[idx])) if len(idx) else float("nan")

        sst_bias = {}
        for name, series in sat.items():
            if series is None:
                sst_bias[name] = float("nan")
                continue
            diff = (buoy.loc[idx] - series.loc[idx]).dropna()
            sst_bias[name] = float(diff.mean()) if not diff.empty else float("nan")

        diurnal = _diurnal_amplitude(buoy.loc[idx])
        dist_km, mean_spd = _daily_distance_km_and_speed(sub)
        alpha, theta = _daily_windage_fit(sub)
        storm_flag, storm_type = _daily_storm_summary(sub)

        rows.append({
            "date": pd.Timestamp(day).strftime("%Y-%m-%d"),
            "n_records": n_records,
            "n_tx_attempted": n_tx_att,
            "n_tx_success": n_tx_suc,
            "teng_eta_l1_mean": eta_mean,
            "teng_eta_l1_slope": float("nan"),  # filled below
            "sst_bias_OISST": sst_bias["OISST"],
            "sst_bias_ERA5": sst_bias["ERA5"],
            "sst_bias_MUR": sst_bias["MUR"],
            "sst_bias_OSTIA": sst_bias["OSTIA"],
            "sst_diurnal_amplitude": diurnal,
            "drift_distance_km": dist_km,
            "drift_speed_mean": mean_spd,
            "windage_alpha": alpha,
            "ekman_theta_deg": theta,
            "storm_flag": bool(storm_flag),
            "storm_type_dominant": storm_type,
        })

    per_day = pd.DataFrame(rows, columns=DERIVED_DAILY_COLUMNS)
    if not per_day.empty:
        per_day["teng_eta_l1_slope"] = _teng_slope_over_days(per_day, "teng_eta_l1_mean")
    return per_day


__all__ = [
    "DERIVED_DAILY_COLUMNS",
    "DERIVED_DAILY_WORKSHEET",
    "compute_daily_table",
]
