"""
Ekman / wind-driven drift decomposition.

References
----------
- Niiler, P. P., & Paduan, J. D. (1995). Wind-driven motions in the
  Northeast Pacific as measured by Lagrangian drifters. *J. Phys.
  Oceanogr.*, 25, 2819–2830.
- Poulain, P.-M., Gerin, R., Mauri, E., & Pennel, R. (2009). Wind
  effects on drogued and undrogued drifters in the eastern
  Mediterranean. *J. Atmos. Oceanic Technol.*, 26, 1144–1156.

The wind-driven component of surface drift is approximated as a complex
gain ``α e^{iθ}`` applied to the wind vector:

    V_drift = α · e^{iθ} · V_wind + V_residual

where α is the windage factor (typically 0.01–0.04 for undrogued
surface floats) and θ is the Ekman-like turning angle (positive = to
the right of the wind in the Northern Hemisphere). Least-squares
solution via the closed-form complex ratio is:

    g  = Σ (Z_drift · Ẑ_wind*) / Σ |Z_wind|²
    α  = |g|
    θ  = arg(g)
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd

_LAT_ALIASES = (
    "Lat", "Latitude", "lat", "Lat (°)", "Latitude (°)", "Latitude (deg)",
    "GPS Lat", "GPS_Lat", "GPS Latitude", "GPS_Latitude",
)
_LON_ALIASES = (
    "Lon", "Lng", "Longitude", "lon", "Lon (°)", "Longitude (°)", "Longitude (deg)",
    "GPS Lon", "GPS_Lon", "GPS Longitude", "GPS_Longitude",
)
_TS_ALIASES = (
    "Timestamp", "Receive Time", "Date Time (UTC)", "Date Time", "time", "Time",
)
_WIND_U_ALIASES = ("U10", "u_wind", "Wind_U", "WIND_U_mps")
_WIND_V_ALIASES = ("V10", "v_wind", "Wind_V", "WIND_V_mps")

# Substring fallbacks for sheets whose headers don't match any alias.
_LAT_SUBSTRINGS = ("latitude", "lat")
_LON_SUBSTRINGS = ("longitude", "lng", "lon")
_LON_EXCLUDE_SUBSTRINGS = ("longevity", "long-term", "longterm")

EARTH_RADIUS_M = 6_371_000.0


def _first(df: pd.DataFrame, aliases: Iterable[str]) -> str | None:
    for a in aliases:
        if a in df.columns:
            return a
    return None


def _first_substring(
    df: pd.DataFrame,
    needles: Iterable[str],
    *,
    exclude: Iterable[str] = (),
) -> str | None:
    ex = tuple(exclude)
    for c in df.columns:
        cl = str(c).lower()
        if any(x in cl for x in ex):
            continue
        if any(n in cl for n in needles):
            return c
    return None


def _resolve_lat_col(df: pd.DataFrame) -> str | None:
    return _first(df, _LAT_ALIASES) or _first_substring(df, _LAT_SUBSTRINGS)


def _resolve_lon_col(df: pd.DataFrame) -> str | None:
    return _first(df, _LON_ALIASES) or _first_substring(
        df, _LON_SUBSTRINGS, exclude=_LON_EXCLUDE_SUBSTRINGS,
    )


def _latlon_to_xy(lat: np.ndarray, lon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Crude equirectangular projection around the dataset mean latitude."""
    lat_rad = np.deg2rad(lat)
    lon_rad = np.deg2rad(lon)
    lat0 = np.nanmean(lat_rad)
    x = EARTH_RADIUS_M * (lon_rad - np.nanmean(lon_rad)) * math.cos(lat0)
    y = EARTH_RADIUS_M * (lat_rad - lat0)
    return x, y


def compute_drift_velocity(df: pd.DataFrame) -> pd.DataFrame:
    """Finite-difference the buoy's GPS track to ``(u_drift, v_drift)`` m/s.

    Adds (or overwrites) ``u_drift`` and ``v_drift`` columns and returns
    the augmented DataFrame. Requires Lat, Lon and a timestamp column
    under any of the recognized aliases. Rows with missing coordinates
    or non-positive dt produce NaN velocities.
    """
    out = df.copy()
    lat_col = _resolve_lat_col(out)
    lon_col = _resolve_lon_col(out)
    ts_col = _first(out, _TS_ALIASES)
    if lat_col is None or lon_col is None or ts_col is None:
        raise ValueError(
            f"compute_drift_velocity: missing columns "
            f"(lat={lat_col}, lon={lon_col}, ts={ts_col})"
        )

    lat = pd.to_numeric(out[lat_col], errors="coerce").to_numpy(dtype=float)
    lon = pd.to_numeric(out[lon_col], errors="coerce").to_numpy(dtype=float)
    ts = pd.to_datetime(out[ts_col], utc=True, errors="coerce")
    x, y = _latlon_to_xy(lat, lon)

    dx = np.diff(x)
    dy = np.diff(y)
    dt = ts.diff().dt.total_seconds().to_numpy()[1:]
    u = np.concatenate(([np.nan], np.where(dt > 0, dx / dt, np.nan)))
    v = np.concatenate(([np.nan], np.where(dt > 0, dy / dt, np.nan)))
    out["u_drift"] = u
    out["v_drift"] = v
    return out


def fit_windage(drift_uv: np.ndarray, wind_uv: np.ndarray) -> dict:
    """Least-squares fit of ``V_drift = α e^{iθ} V_wind + residual``.

    Parameters
    ----------
    drift_uv, wind_uv : ndarray of shape (N, 2)
        Columns are ``[u, v]`` in the same units (m/s).

    Returns
    -------
    dict with keys
        ``alpha``          — unitless windage magnitude
        ``theta_deg``      — turning angle in degrees (CCW positive)
        ``r_squared``      — fraction of drift variance explained
        ``residual_u``     — ndarray of u residuals (drift minus fit)
        ``residual_v``     — ndarray of v residuals
        ``n_samples``      — number of valid samples used
    """
    drift = np.asarray(drift_uv, dtype=float)
    wind = np.asarray(wind_uv, dtype=float)
    if drift.shape != wind.shape or drift.ndim != 2 or drift.shape[1] != 2:
        raise ValueError("drift_uv and wind_uv must have matching shape (N, 2)")

    z_drift = drift[:, 0] + 1j * drift[:, 1]
    z_wind = wind[:, 0] + 1j * wind[:, 1]
    mask = np.isfinite(z_drift) & np.isfinite(z_wind)
    z_drift = z_drift[mask]
    z_wind = z_wind[mask]
    n = int(mask.sum())

    if n < 2 or np.sum(np.abs(z_wind) ** 2) == 0:
        return {
            "alpha": float("nan"),
            "theta_deg": float("nan"),
            "r_squared": float("nan"),
            "residual_u": np.full(n, np.nan),
            "residual_v": np.full(n, np.nan),
            "n_samples": n,
        }

    # Closed-form complex least-squares: g = <Zd, Zw> / <Zw, Zw>
    g = np.sum(z_drift * np.conj(z_wind)) / np.sum(np.abs(z_wind) ** 2)
    alpha = float(abs(g))
    theta_deg = float(math.degrees(math.atan2(g.imag, g.real)))

    fit = g * z_wind
    resid = z_drift - fit
    ss_tot = float(np.sum(np.abs(z_drift - np.mean(z_drift)) ** 2))
    ss_res = float(np.sum(np.abs(resid) ** 2))
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else float("nan")

    return {
        "alpha": alpha,
        "theta_deg": theta_deg,
        "r_squared": r_squared,
        "residual_u": resid.real,
        "residual_v": resid.imag,
        "n_samples": n,
    }


def decompose_drift(df: pd.DataFrame) -> pd.DataFrame:
    """Split drift into wind-driven and residual components.

    Requires ``u_drift``/``v_drift`` (see :func:`compute_drift_velocity`)
    and ``U10``/``V10`` wind columns (or any alias in
    ``_WIND_U_ALIASES``/``_WIND_V_ALIASES``).

    Adds ``u_wind_driven``, ``v_wind_driven``, ``u_residual``,
    ``v_residual`` columns and returns the augmented DataFrame. The
    fit parameters are attached under ``df.attrs['windage_fit']``.
    """
    out = df.copy()
    if "u_drift" not in out or "v_drift" not in out:
        raise ValueError("decompose_drift requires u_drift/v_drift columns")
    u_col = _first(out, _WIND_U_ALIASES)
    v_col = _first(out, _WIND_V_ALIASES)
    if u_col is None or v_col is None:
        raise ValueError("decompose_drift requires wind U/V columns")

    drift_uv = np.column_stack([
        pd.to_numeric(out["u_drift"], errors="coerce").to_numpy(dtype=float),
        pd.to_numeric(out["v_drift"], errors="coerce").to_numpy(dtype=float),
    ])
    wind_uv = np.column_stack([
        pd.to_numeric(out[u_col], errors="coerce").to_numpy(dtype=float),
        pd.to_numeric(out[v_col], errors="coerce").to_numpy(dtype=float),
    ])
    fit = fit_windage(drift_uv, wind_uv)
    alpha = fit["alpha"]
    theta = math.radians(fit["theta_deg"])
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    # Rotated wind vector scaled by alpha is the wind-driven component.
    u_wind_driven = alpha * (wind_uv[:, 0] * cos_t - wind_uv[:, 1] * sin_t)
    v_wind_driven = alpha * (wind_uv[:, 0] * sin_t + wind_uv[:, 1] * cos_t)
    out["u_wind_driven"] = u_wind_driven
    out["v_wind_driven"] = v_wind_driven
    out["u_residual"] = drift_uv[:, 0] - u_wind_driven
    out["v_residual"] = drift_uv[:, 1] - v_wind_driven
    out.attrs["windage_fit"] = {
        "alpha": fit["alpha"],
        "theta_deg": fit["theta_deg"],
        "r_squared": fit["r_squared"],
        "n_samples": fit["n_samples"],
    }
    return out


__all__ = [
    "compute_drift_velocity",
    "fit_windage",
    "decompose_drift",
]
