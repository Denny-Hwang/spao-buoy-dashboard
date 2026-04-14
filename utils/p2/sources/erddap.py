"""
NOAA ERDDAP fetchers (OISST, MUR SST, OSCAR currents).

ERDDAP exposes gridded datasets as JSON over HTTP. We query one point at
a time via the ``[(time)][(depth?)][(lat)][(lon)]`` index syntax. The
response shape is:

    {"table": {"columnNames": [...], "columnTypes": [...],
               "rows": [[t, lat, lon, value, ...]]}}

404 means "no data at that point/time" (common near coast/ice). We
return None on 404 so the caller marks the bit unset.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any

import pandas as pd

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

ERDDAP_BASE = "https://coastwatch.pfeg.noaa.gov/erddap/griddap"

OISST_DATASET = "ncdcOisst21Agg_LonPM180"
MUR_DATASET = "jplMURSST41"
OSCAR_DATASET = "jplOscar_LonPM180"

DEFAULT_TIMEOUT = 30
RETRIES = 2
BACKOFF_BASE = 2.0


def _fmt_iso_date(d: date | datetime | pd.Timestamp) -> str:
    return pd.Timestamp(d).strftime("%Y-%m-%d")


def _erddap_get(url: str) -> dict | None:
    if requests is None:  # pragma: no cover
        log.warning("requests not installed; cannot call %s", url)
        return None
    for attempt in range(RETRIES + 1):
        try:
            resp = requests.get(url, timeout=DEFAULT_TIMEOUT)
        except Exception as exc:  # pragma: no cover
            log.warning("erddap GET failed: %s", exc)
            time.sleep(BACKOFF_BASE ** attempt)
            continue
        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError:
                return None
        if resp.status_code == 404:
            return None
        if resp.status_code in (429,) or 500 <= resp.status_code < 600:
            time.sleep(BACKOFF_BASE ** (attempt + 1))
            continue
        log.warning("erddap %s returned %s", url, resp.status_code)
        return None
    return None


def _first_row(payload: dict | None) -> list | None:
    if not payload:
        return None
    try:
        rows = payload["table"]["rows"]
    except (KeyError, TypeError):
        return None
    if not rows:
        return None
    return rows[0]


def _col_index(payload: dict, col_name: str) -> int | None:
    try:
        names = payload["table"]["columnNames"]
    except (KeyError, TypeError):
        return None
    for i, name in enumerate(names):
        if name == col_name:
            return i
    return None


def fetch_oisst_point(lat: float, lon: float, d: date | datetime | str) -> float | None:
    """Return the NOAA OISST daily SST (°C) at a point, or None on miss."""
    date_str = _fmt_iso_date(d) + "T00:00:00Z"
    url = (
        f"{ERDDAP_BASE}/{OISST_DATASET}.json"
        f"?sst[({date_str})][(0.0)][({lat})][({lon})]"
    )
    payload = _erddap_get(url)
    row = _first_row(payload)
    if row is None:
        return None
    idx = _col_index(payload, "sst")
    if idx is None or row[idx] is None:
        return None
    try:
        return float(row[idx])
    except (TypeError, ValueError):
        return None


def fetch_mur_sst_point(lat: float, lon: float, d: date | datetime | str) -> float | None:
    """Return the MUR v4.1 analysed_sst (°C) at a point, or None on miss."""
    date_str = _fmt_iso_date(d) + "T09:00:00Z"
    url = (
        f"{ERDDAP_BASE}/{MUR_DATASET}.json"
        f"?analysed_sst[({date_str})][({lat})][({lon})]"
    )
    payload = _erddap_get(url)
    row = _first_row(payload)
    if row is None:
        return None
    idx = _col_index(payload, "analysed_sst")
    if idx is None or row[idx] is None:
        return None
    try:
        val = float(row[idx])
    except (TypeError, ValueError):
        return None
    # MUR reports in Kelvin if the dataset attributes say so; analysed_sst
    # on jplMURSST41 is Celsius on ERDDAP but clip to a sane range.
    if val > 200:  # almost certainly Kelvin
        val = val - 273.15
    if val < -3.0 or val > 40.0:
        return None
    return val


def fetch_oscar_point(
    lat: float, lon: float, d: date | datetime | str
) -> tuple[float, float] | None:
    """Return the (u, v) OSCAR surface current at a point in m/s, or None."""
    date_str = _fmt_iso_date(d) + "T00:00:00Z"
    url = (
        f"{ERDDAP_BASE}/{OSCAR_DATASET}.json"
        f"?u[({date_str})][(0.0)][({lat})][({lon})]"
        f",v[({date_str})][(0.0)][({lat})][({lon})]"
    )
    payload = _erddap_get(url)
    if not payload:
        return None
    try:
        rows = payload["table"]["rows"]
    except (KeyError, TypeError):
        return None
    if not rows:
        return None
    row = rows[0]
    u_idx = _col_index(payload, "u")
    v_idx = _col_index(payload, "v")
    if u_idx is None or v_idx is None:
        return None
    try:
        u = float(row[u_idx])
        v = float(row[v_idx])
    except (TypeError, ValueError):
        return None
    return (u, v)


__all__ = [
    "ERDDAP_BASE",
    "OISST_DATASET",
    "MUR_DATASET",
    "OSCAR_DATASET",
    "fetch_oisst_point",
    "fetch_mur_sst_point",
    "fetch_oscar_point",
]
