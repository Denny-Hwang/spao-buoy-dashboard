"""
Quality-control flag detection for enriched buoy data.

Each check returns a boolean Series aligned to the input DataFrame
(True → flagged). ``qc_table`` aggregates everything into a single
long-format DataFrame ready for display.

Current checks:
    * ``sst_vs_oisst_gt3``  — |SST_buoy − OISST| > 3 °C
    * ``wave_h_gt15``       — Hs > 15 m
    * ``wind_gt50``         — U10 > 50 m/s
    * ``gps_speed_gt10kmh`` — GPS-derived speed > 10 km/h (≈2.8 m/s)
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd


BUOY_SST_ALIASES = ("SST_buoy", "sst_buoy", "SST", "Water Temp", "Water_Temp")
OISST_ALIASES = ("SAT_SST_OISST", "SAT_SST_OISST_cC")
HS_ALIASES = ("Hs", "Hs_m", "WAVE_H_cm")
WIND_ALIASES = ("U10", "WIND_SPD_cms", "WIND_SPD_mps", "Wind_Speed")
LAT_ALIASES = ("Lat", "Latitude", "lat", "GPS Lat")
LON_ALIASES = ("Lon", "Lng", "Longitude", "lon", "GPS Lon")
TS_ALIASES = ("Timestamp", "Receive Time", "time", "Time")

EARTH_RADIUS_M = 6_371_000.0

SST_DELTA_LIMIT_C = 3.0
WAVE_H_LIMIT_M = 15.0
WIND_LIMIT_MPS = 50.0
GPS_SPEED_LIMIT_KMH = 10.0


def _first(df: pd.DataFrame, aliases: Iterable[str]) -> str | None:
    for a in aliases:
        if a in df.columns:
            return a
    return None


def _to_celsius(series: pd.Series, col: str) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    if col.endswith("_cC"):
        return s / 100.0
    return s


def _to_metres(series: pd.Series, col: str) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    if col == "WAVE_H_cm":
        return s / 100.0
    return s


def _to_mps(series: pd.Series, col: str) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    if col == "WIND_SPD_cms":
        return s / 100.0
    return s


# ──────────────────────────────────────────────────────────────────────
# Individual checks
# ──────────────────────────────────────────────────────────────────────
def check_sst_vs_oisst(df: pd.DataFrame) -> pd.Series:
    buoy_col = _first(df, BUOY_SST_ALIASES)
    oisst_col = _first(df, OISST_ALIASES)
    if buoy_col is None or oisst_col is None:
        return pd.Series(False, index=df.index)
    buoy = pd.to_numeric(df[buoy_col], errors="coerce")
    oisst = _to_celsius(df[oisst_col], oisst_col)
    return (buoy - oisst).abs() > SST_DELTA_LIMIT_C


def check_wave_height(df: pd.DataFrame) -> pd.Series:
    col = _first(df, HS_ALIASES)
    if col is None:
        return pd.Series(False, index=df.index)
    return _to_metres(df[col], col) > WAVE_H_LIMIT_M


def check_wind_speed(df: pd.DataFrame) -> pd.Series:
    col = _first(df, WIND_ALIASES)
    if col is None:
        return pd.Series(False, index=df.index)
    return _to_mps(df[col], col) > WIND_LIMIT_MPS


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    rlat1 = math.radians(lat1)
    rlat2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2)
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(max(0.0, min(1.0, a)))) / 1000.0


def check_gps_speed(df: pd.DataFrame) -> pd.Series:
    lat_col = _first(df, LAT_ALIASES)
    lon_col = _first(df, LON_ALIASES)
    ts_col = _first(df, TS_ALIASES)
    if lat_col is None or lon_col is None or ts_col is None:
        return pd.Series(False, index=df.index)
    lat = pd.to_numeric(df[lat_col], errors="coerce").to_numpy(dtype=float)
    lon = pd.to_numeric(df[lon_col], errors="coerce").to_numpy(dtype=float)
    ts = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
    flags = np.zeros(len(df), dtype=bool)
    for i in range(1, len(df)):
        if not (np.isfinite(lat[i - 1]) and np.isfinite(lat[i])
                and np.isfinite(lon[i - 1]) and np.isfinite(lon[i])):
            continue
        dt = (ts.iloc[i] - ts.iloc[i - 1]).total_seconds()
        if not dt or dt <= 0:
            continue
        dist_km = _haversine_km(lat[i - 1], lon[i - 1], lat[i], lon[i])
        kmh = dist_km / (dt / 3600.0)
        if kmh > GPS_SPEED_LIMIT_KMH:
            flags[i] = True
    return pd.Series(flags, index=df.index)


# ──────────────────────────────────────────────────────────────────────
# Aggregate
# ──────────────────────────────────────────────────────────────────────
QC_CHECKS = {
    "sst_vs_oisst_gt3": check_sst_vs_oisst,
    "wave_h_gt15": check_wave_height,
    "wind_gt50": check_wind_speed,
    "gps_speed_gt10kmh": check_gps_speed,
}


def qc_flags_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Return a boolean DataFrame (one column per QC check)."""
    return pd.DataFrame({name: fn(df) for name, fn in QC_CHECKS.items()}, index=df.index)


def qc_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Return a per-check count summary."""
    flags = qc_flags_matrix(df)
    rows = []
    n = len(df)
    for col in flags.columns:
        hits = int(flags[col].sum())
        rows.append({
            "check": col,
            "n_rows": n,
            "n_flagged": hits,
            "pct": (100.0 * hits / n) if n else 0.0,
        })
    return pd.DataFrame(rows)


__all__ = [
    "SST_DELTA_LIMIT_C",
    "WAVE_H_LIMIT_M",
    "WIND_LIMIT_MPS",
    "GPS_SPEED_LIMIT_KMH",
    "QC_CHECKS",
    "check_sst_vs_oisst",
    "check_wave_height",
    "check_wind_speed",
    "check_gps_speed",
    "qc_flags_matrix",
    "qc_summary",
]
