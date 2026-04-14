"""
Spatial/temporal grouping helpers for enrichment fetchers.

The enrichment sources (Open-Meteo, ERDDAP, Copernicus, OSI SAF) all serve
data on coarse grids (0.1° typical) at hourly or daily cadence. Grouping
buoy rows by the same grid cell + time bucket lets us fetch once and
populate many rows, which is essential for rate-limited APIs.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

import pandas as pd


def snap(val: float, step: float = 0.1) -> float:
    """Round a coordinate to the nearest grid step (default 0.1°)."""
    return round(val / step) * step


def time_bucket(ts: pd.Timestamp | datetime, bucket: Literal["H", "D"] = "H") -> pd.Timestamp:
    """Truncate a timestamp to the top of its hour (H) or day (D) in UTC."""
    ts = pd.Timestamp(ts)
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    if bucket == "H":
        return ts.floor("h")
    if bucket == "D":
        return ts.floor("D")
    raise ValueError(f"Unknown bucket: {bucket!r}")


def grid_key(
    lat: float,
    lon: float,
    ts: pd.Timestamp | datetime | date,
    source: str,
    bucket: Literal["H", "D"] = "H",
    step: float = 0.1,
) -> tuple[str, float, float, str]:
    """Return a stable hash key for a (source, cell, time-bucket) tuple."""
    lat_s = snap(lat, step)
    lon_s = snap(lon, step)
    if isinstance(ts, date) and not isinstance(ts, datetime):
        ts_pd = pd.Timestamp(ts, tz="UTC")
    else:
        ts_pd = pd.Timestamp(ts)
    ts_b = time_bucket(ts_pd, bucket)
    return (source, lat_s, lon_s, ts_b.isoformat())


def as_utc(ts) -> pd.Timestamp:
    """Coerce any scalar timestamp-like into tz-aware UTC."""
    ts_pd = pd.Timestamp(ts)
    if ts_pd.tz is None:
        return ts_pd.tz_localize("UTC")
    return ts_pd.tz_convert("UTC")


def utcnow() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc))
