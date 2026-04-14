"""
Copernicus Marine fetchers (OSTIA SST).

This module uses the ``copernicusmarine`` SDK, which requires
authentication. Credentials must be available via GitHub Actions
secrets and are *never* imported from the Streamlit app.

We accept credentials under two env var schemes:
    - COPERNICUS_USERNAME / COPERNICUS_PASSWORD  (our convention)
    - COPERNICUSMARINE_SERVICE_USERNAME / COPERNICUSMARINE_SERVICE_PASSWORD
      (what the SDK reads natively)

`_ensure_credentials` copies the first form into the second so the SDK
can authenticate without any runtime prompting.

Dataset:
    METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2 (UK Met Office OSTIA, 0.05°, daily).
Variable: ``analysed_sst`` (Kelvin). We convert to °C.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

OSTIA_DATASET_ID = "METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2"
OSTIA_VAR = "analysed_sst"

_BBOX_HALF_DEG = 0.1  # ±0.1° box around the point for nearest-neighbor select.
_KELVIN_OFFSET = 273.15


def _ensure_credentials() -> None:
    """Populate ``COPERNICUSMARINE_SERVICE_USERNAME/PASSWORD`` from our env.

    The SDK reads those env vars at login time. Raises ``RuntimeError``
    with a helpful message — never containing the secret values — if
    neither scheme is present.
    """
    have_sdk = bool(os.environ.get("COPERNICUSMARINE_SERVICE_USERNAME")) and bool(
        os.environ.get("COPERNICUSMARINE_SERVICE_PASSWORD")
    )
    have_ours = bool(os.environ.get("COPERNICUS_USERNAME")) and bool(
        os.environ.get("COPERNICUS_PASSWORD")
    )
    if have_sdk:
        return
    if have_ours:
        os.environ["COPERNICUSMARINE_SERVICE_USERNAME"] = os.environ["COPERNICUS_USERNAME"]
        os.environ["COPERNICUSMARINE_SERVICE_PASSWORD"] = os.environ["COPERNICUS_PASSWORD"]
        return
    raise RuntimeError(
        "Copernicus credentials missing. Set COPERNICUS_USERNAME and "
        "COPERNICUS_PASSWORD (or COPERNICUSMARINE_SERVICE_USERNAME / "
        "COPERNICUSMARINE_SERVICE_PASSWORD) in the environment."
    )


def _kelvin_to_celsius(val: Any) -> float | None:
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if pd.isna(f):
        return None
    if f > 200.0:
        f -= _KELVIN_OFFSET
    if f < -3.0 or f > 40.0:
        return None
    return f


def _as_date(d: date | datetime | str | pd.Timestamp) -> date:
    if isinstance(d, date) and not isinstance(d, datetime):
        return d
    return pd.Timestamp(d).date()


def fetch_ostia_point(
    lat: float, lon: float, d: date | datetime | str | pd.Timestamp
) -> float | None:
    """Return OSTIA analysed SST (°C) at the nearest grid cell, or None."""
    try:
        _ensure_credentials()
    except RuntimeError as exc:
        log.warning("copernicus: %s", exc)
        return None

    try:
        import copernicusmarine  # type: ignore
    except Exception as exc:  # pragma: no cover
        log.warning("copernicusmarine SDK not available: %s", exc)
        return None

    day = _as_date(d)
    start = datetime(day.year, day.month, day.day)
    end = start + timedelta(days=1)

    try:
        ds = copernicusmarine.open_dataset(
            dataset_id=OSTIA_DATASET_ID,
            variables=[OSTIA_VAR],
            minimum_longitude=lon - _BBOX_HALF_DEG,
            maximum_longitude=lon + _BBOX_HALF_DEG,
            minimum_latitude=lat - _BBOX_HALF_DEG,
            maximum_latitude=lat + _BBOX_HALF_DEG,
            start_datetime=start.isoformat(),
            end_datetime=end.isoformat(),
        )
    except Exception as exc:
        log.warning("copernicus open_dataset failed for %s %s: %s", lat, lon, exc)
        return None

    try:
        arr = ds[OSTIA_VAR].sel(latitude=lat, longitude=lon, method="nearest")
        val = arr.values
        # Scalar or 1-element array.
        if hasattr(val, "size") and val.size > 1:
            val = val.flat[0]
        return _kelvin_to_celsius(val)
    except Exception as exc:
        log.warning("copernicus select failed: %s", exc)
        return None
    finally:
        try:
            ds.close()
        except Exception:
            pass


def fetch_ostia_batch(
    points: list[tuple[float, float, date | datetime | str | pd.Timestamp]],
) -> dict[tuple[float, float, str], float | None]:
    """Fetch several points, grouping by day so one dataset open covers many.

    ``points`` is an iterable of ``(lat, lon, date)``. Returns a dict
    keyed by ``(round(lat,1), round(lon,1), iso_date)`` → °C or None.
    """
    try:
        _ensure_credentials()
    except RuntimeError as exc:
        log.warning("copernicus: %s", exc)
        return {k: None for k in _batch_keys(points)}

    try:
        import copernicusmarine  # type: ignore
    except Exception:  # pragma: no cover
        return {k: None for k in _batch_keys(points)}

    by_day: dict[date, list[tuple[float, float]]] = {}
    for lat, lon, d in points:
        by_day.setdefault(_as_date(d), []).append((float(lat), float(lon)))

    out: dict[tuple[float, float, str], float | None] = {}
    for day, pts in by_day.items():
        lats = [p[0] for p in pts]
        lons = [p[1] for p in pts]
        min_lat, max_lat = min(lats) - _BBOX_HALF_DEG, max(lats) + _BBOX_HALF_DEG
        min_lon, max_lon = min(lons) - _BBOX_HALF_DEG, max(lons) + _BBOX_HALF_DEG
        start = datetime(day.year, day.month, day.day)
        end = start + timedelta(days=1)
        try:
            ds = copernicusmarine.open_dataset(
                dataset_id=OSTIA_DATASET_ID,
                variables=[OSTIA_VAR],
                minimum_longitude=min_lon,
                maximum_longitude=max_lon,
                minimum_latitude=min_lat,
                maximum_latitude=max_lat,
                start_datetime=start.isoformat(),
                end_datetime=end.isoformat(),
            )
        except Exception as exc:
            log.warning("copernicus open_dataset failed for %s: %s", day, exc)
            for la, lo in pts:
                out[(round(la, 1), round(lo, 1), day.isoformat())] = None
            continue
        for la, lo in pts:
            try:
                arr = ds[OSTIA_VAR].sel(latitude=la, longitude=lo, method="nearest")
                val = arr.values
                if hasattr(val, "size") and val.size > 1:
                    val = val.flat[0]
                out[(round(la, 1), round(lo, 1), day.isoformat())] = _kelvin_to_celsius(val)
            except Exception as exc:
                log.warning("copernicus select failed for %s %s: %s", la, lo, exc)
                out[(round(la, 1), round(lo, 1), day.isoformat())] = None
        try:
            ds.close()
        except Exception:
            pass
    return out


def _batch_keys(
    points: list[tuple[float, float, date | datetime | str | pd.Timestamp]],
) -> list[tuple[float, float, str]]:
    return [
        (round(float(lat), 1), round(float(lon), 1), _as_date(d).isoformat())
        for lat, lon, d in points
    ]


__all__ = [
    "OSTIA_DATASET_ID",
    "OSTIA_VAR",
    "fetch_ostia_point",
    "fetch_ostia_batch",
]
