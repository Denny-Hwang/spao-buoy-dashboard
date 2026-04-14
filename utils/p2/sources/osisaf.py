"""
OSI SAF sea ice concentration fetcher.

Product: OSI-401-d (global multi-sensor passive microwave), delivered on a
polar stereographic grid with per-hemisphere files at
https://thredds.met.no/thredds/dodsC/osisaf/met.no/ice/conc/{YYYY}/{MM:02d}/
and filenames ``ice_conc_{hem}_polstere-100_multi_{YYYYMMDD}1200.nc``.

We query a single (lat, lon, date) point:
    1. Reproject lat/lon → NH polar stereographic metres with pyproj.
    2. Open the NetCDF via OPeNDAP (xarray + netCDF4 engine).
    3. Nearest-neighbor select on the ``xc``/``yc`` axes.
    4. Return ``ice_conc`` as percent (0–100). None on any failure.

For |lat| < 40° we short-circuit to None since no sea ice is present at
those latitudes — this avoids hitting OPeNDAP for every tropical row.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

OSISAF_BASE = "https://thredds.met.no/thredds/dodsC/osisaf/met.no/ice/conc"

NH_CRS = "+proj=stere +lat_0=90 +lat_ts=70 +lon_0=-45 +k=1 +x_0=0 +y_0=0 +a=6378273 +b=6356889.449 +units=m +no_defs"
SH_CRS = "+proj=stere +lat_0=-90 +lat_ts=-70 +lon_0=0 +k=1 +x_0=0 +y_0=0 +a=6378273 +b=6356889.449 +units=m +no_defs"

TROPIC_LAT_CUTOFF = 40.0


def _as_date(d: date | datetime | str | pd.Timestamp) -> date:
    if isinstance(d, date) and not isinstance(d, datetime):
        return d
    return pd.Timestamp(d).date()


def _dataset_url(hem: str, d: date) -> str:
    return (
        f"{OSISAF_BASE}/{d.year}/{d.month:02d}/"
        f"ice_conc_{hem}_polstere-100_multi_{d.strftime('%Y%m%d')}1200.nc"
    )


def _reproject(lat: float, lon: float, hem: str) -> tuple[float, float] | None:
    try:
        import pyproj
    except Exception as exc:  # pragma: no cover
        log.warning("pyproj not installed: %s", exc)
        return None
    crs = NH_CRS if hem == "nh" else SH_CRS
    transformer = pyproj.Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    try:
        x, y = transformer.transform(lon, lat)
    except Exception as exc:
        log.warning("osi-saf reproject failed for (%s,%s): %s", lat, lon, exc)
        return None
    return float(x), float(y)


def fetch_sea_ice_concentration(
    lat: float, lon: float, d: date | datetime | str | pd.Timestamp
) -> float | None:
    """Return sea ice concentration in percent at a point, or None."""
    if abs(float(lat)) < TROPIC_LAT_CUTOFF:
        # No sea ice in the tropics / mid-latitudes.
        return None
    try:
        import xarray as xr  # noqa: F401 — dep probe
    except Exception as exc:  # pragma: no cover
        log.warning("xarray not installed: %s", exc)
        return None

    day = _as_date(d)
    hem = "nh" if float(lat) > 0 else "sh"
    xy = _reproject(lat, lon, hem)
    if xy is None:
        return None
    x, y = xy

    url = _dataset_url(hem, day)
    try:
        import xarray as xr
        ds = xr.open_dataset(url, engine="netcdf4")
    except Exception as exc:
        log.info("osi-saf open_dataset failed for %s: %s", url, exc)
        return None

    try:
        arr = ds["ice_conc"].sel(xc=x, yc=y, method="nearest")
        # ice_conc has shape (time=1, yc, xc) — isel the lone time axis.
        if "time" in arr.dims:
            arr = arr.isel(time=0)
        val = float(arr.values)
        if val < 0 or val > 100:
            return None
        return val
    except Exception as exc:
        log.warning("osi-saf select failed: %s", exc)
        return None
    finally:
        try:
            ds.close()
        except Exception:
            pass


def fetch_ice_edge_distance_km(
    lat: float, lon: float, d: date | datetime | str | pd.Timestamp
) -> float | None:
    """Approximate distance (km) from (lat, lon) to the 15% ice-edge contour.

    Returns 0.0 if the point is inside the ice pack. None if the dataset
    cannot be opened or the point is outside the polar grid.

    Uses a bounding-box subset ±500 km around the query point to keep
    the OPeNDAP transfer small, then a nearest-grid-cell Euclidean
    distance in metres.
    """
    if abs(float(lat)) < TROPIC_LAT_CUTOFF:
        return None
    try:
        import numpy as np
        import xarray as xr
    except Exception as exc:  # pragma: no cover
        log.warning("numpy/xarray not installed: %s", exc)
        return None

    day = _as_date(d)
    hem = "nh" if float(lat) > 0 else "sh"
    xy = _reproject(lat, lon, hem)
    if xy is None:
        return None
    x, y = xy

    url = _dataset_url(hem, day)
    try:
        ds = xr.open_dataset(url, engine="netcdf4")
    except Exception as exc:
        log.info("osi-saf open_dataset failed for %s: %s", url, exc)
        return None

    try:
        half_box = 500_000  # metres
        sub = ds["ice_conc"].sel(
            xc=slice(x - half_box, x + half_box),
            yc=slice(y - half_box, y + half_box),
        )
        if "time" in sub.dims:
            sub = sub.isel(time=0)
        vals = sub.values
        if vals.size == 0:
            return None
        xs = sub["xc"].values
        ys = sub["yc"].values
        xg, yg = np.meshgrid(xs, ys)
        here = np.argmin((xg - x) ** 2 + (yg - y) ** 2)
        here_flat = vals.ravel()[here]
        if here_flat >= 15.0:
            return 0.0
        ice_mask = vals >= 15.0
        if not ice_mask.any():
            return float("nan")
        dx = xg[ice_mask] - x
        dy = yg[ice_mask] - y
        d_m = np.sqrt(dx * dx + dy * dy).min()
        return float(d_m) / 1000.0
    except Exception as exc:
        log.warning("osi-saf edge-distance failed: %s", exc)
        return None
    finally:
        try:
            ds.close()
        except Exception:
            pass


__all__ = [
    "OSISAF_BASE",
    "TROPIC_LAT_CUTOFF",
    "fetch_sea_ice_concentration",
    "fetch_ice_edge_distance_km",
]
