"""
Open-Meteo fetchers.

Two endpoints:
- Marine API        (waves, swell, sea-surface temperature — hourly)
- Archive / ERA5    (2 m temperature, humidity, pressure, 10 m wind — hourly)

Both are free, no-auth, rate-limited to roughly 10,000 calls/day. We add a
short sleep and retry on 429 with exponential backoff. On persistent
failure we return an empty DataFrame rather than raising, so a cron run
can mark the row's ENRICH_FLAG bit unset and move on.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any

import pandas as pd

try:  # requests is an optional dep in lightweight envs (tests stub it).
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

MARINE_VARS = [
    "wave_height",
    "wave_period",
    "wave_direction",
    "wind_wave_height",
    "wind_wave_period",
    "swell_wave_height",
    "swell_wave_period",
    "sea_surface_temperature",
]

HISTORICAL_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "surface_pressure",
    "wind_speed_10m",
    "wind_direction_10m",
]

DEFAULT_TIMEOUT = 30
RATE_LIMIT_SLEEP = 0.15
MAX_RETRIES = 3
BACKOFF_BASE = 2.0


def _fmt_date(d: date | datetime | pd.Timestamp) -> str:
    return pd.Timestamp(d).strftime("%Y-%m-%d")


def _http_get(url: str, params: dict[str, Any]) -> dict | None:
    """GET *url* with retries on 429/5xx. Returns parsed JSON or None."""
    if requests is None:  # pragma: no cover
        log.warning("requests not installed; cannot call %s", url)
        return None

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        except Exception as exc:  # pragma: no cover - network failure
            log.warning("open-meteo GET failed (%s): %s", url, exc)
            time.sleep(BACKOFF_BASE ** attempt)
            continue

        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError:
                log.warning("open-meteo returned non-JSON at %s", url)
                return None
        if resp.status_code == 429:
            wait = BACKOFF_BASE ** (attempt + 1)
            log.info("open-meteo 429, backing off %.1fs", wait)
            time.sleep(wait)
            continue
        if 500 <= resp.status_code < 600:
            time.sleep(BACKOFF_BASE ** attempt)
            continue
        # 4xx (client error): do not retry.
        log.warning("open-meteo %s returned %s: %s", url, resp.status_code, resp.text[:200])
        return None
    return None


def _hourly_frame(payload: dict, expected_vars: list[str]) -> pd.DataFrame:
    """Convert Open-Meteo `hourly` payload into a tz-aware UTC DataFrame."""
    if not payload or "hourly" not in payload:
        return pd.DataFrame()
    hourly = payload["hourly"]
    times = hourly.get("time")
    if not times:
        return pd.DataFrame()

    df = pd.DataFrame({"time": pd.to_datetime(times, utc=True)})
    for var in expected_vars:
        df[var] = hourly.get(var, [None] * len(times))
    return df.set_index("time").sort_index()


def fetch_marine_point(
    lat: float,
    lon: float,
    start_dt: date | datetime | pd.Timestamp,
    end_dt: date | datetime | pd.Timestamp,
) -> pd.DataFrame:
    """Fetch hourly Open-Meteo Marine variables for a single point.

    Returns a tz-aware UTC-indexed DataFrame with the MARINE_VARS columns.
    On error returns an empty DataFrame (never raises).
    """
    params = {
        "latitude": round(float(lat), 4),
        "longitude": round(float(lon), 4),
        "start_date": _fmt_date(start_dt),
        "end_date": _fmt_date(end_dt),
        "hourly": ",".join(MARINE_VARS),
        "timezone": "UTC",
    }
    time.sleep(RATE_LIMIT_SLEEP)
    payload = _http_get(MARINE_URL, params)
    return _hourly_frame(payload or {}, MARINE_VARS)


def fetch_historical_point(
    lat: float,
    lon: float,
    start_dt: date | datetime | pd.Timestamp,
    end_dt: date | datetime | pd.Timestamp,
) -> pd.DataFrame:
    """Fetch hourly Open-Meteo Archive / ERA5 variables for a single point."""
    params = {
        "latitude": round(float(lat), 4),
        "longitude": round(float(lon), 4),
        "start_date": _fmt_date(start_dt),
        "end_date": _fmt_date(end_dt),
        "hourly": ",".join(HISTORICAL_VARS),
        "timezone": "UTC",
    }
    time.sleep(RATE_LIMIT_SLEEP)
    payload = _http_get(ARCHIVE_URL, params)
    return _hourly_frame(payload or {}, HISTORICAL_VARS)


__all__ = [
    "MARINE_URL",
    "ARCHIVE_URL",
    "MARINE_VARS",
    "HISTORICAL_VARS",
    "fetch_marine_point",
    "fetch_historical_point",
]
