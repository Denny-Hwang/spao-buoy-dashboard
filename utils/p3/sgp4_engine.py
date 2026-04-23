"""SGP4 propagation + look-angle geometry for Phase 3.

This is the thin, well-tested layer every Phase 3 page leans on:

* :func:`parse_tle` — parse a list of ``{"name", "line1", "line2"}``
  dicts into verified :class:`sgp4.api.Satrec` records.
* :func:`propagate` — one ECI state for one epoch.
* :func:`look_angles` — observer-relative (elevation, azimuth, range).
* :func:`sky_positions` — vectorised helper used by the sky plots.

Design notes
~~~~~~~~~~~~
We deliberately depend on the pure-Python **`sgp4`** package (Brandon
Rhodes' port of Vallado's reference implementation). We explicitly
avoid Skyfield / pyephem so the Streamlit container stays lean and
there is no ephemeris download.

Inputs are UTC :class:`datetime.datetime` or :class:`pandas.Timestamp`.
Outputs are plain Python floats in SI-ish units (km, km/s, degrees).
This matches the conventions of the HTML demo that shipped with the
Phase 3 design doc, so correlation maths stays intuitive.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

# Earth / time constants
RE_KM = 6378.137                  # WGS-84 equatorial radius
FLATTENING = 1.0 / 298.257223563
E2 = FLATTENING * (2.0 - FLATTENING)
OMEGA_EARTH = 7.2921150e-5        # rad/s

_DEG = math.pi / 180.0
_RAD = 180.0 / math.pi

# ──────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Sat:
    """Parsed TLE + the SGP4 record. ``sr`` is ``None`` for failed parses."""
    name: str
    line1: str
    line2: str
    sr: object | None  # sgp4.api.Satrec; ``object`` keeps the type hint dep-free


@dataclass(frozen=True)
class LookAngle:
    """Observer-relative geometry at a single epoch."""
    el_deg: float
    az_deg: float
    range_km: float


# ──────────────────────────────────────────────────────────────────────
# TLE parsing
# ──────────────────────────────────────────────────────────────────────
def parse_tle(records: Iterable[dict]) -> list[Sat]:
    """Parse TLE dicts into :class:`Sat` objects.

    Each record must have ``name`` / ``line1`` / ``line2`` (any other
    keys are ignored). Records that fail to parse are skipped silently;
    use :func:`parse_tle_verbose` during development to see errors.
    """
    try:
        from sgp4.api import Satrec
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Phase 3 requires the 'sgp4' package. Add `sgp4>=2.22` to "
            "requirements.txt."
        ) from exc

    out: list[Sat] = []
    for rec in records:
        name = str(rec.get("name", "")).strip() or "UNKNOWN"
        l1 = str(rec.get("line1", ""))
        l2 = str(rec.get("line2", ""))
        try:
            sr = Satrec.twoline2rv(l1, l2)
            if getattr(sr, "error", 0) != 0:
                continue
        except Exception:  # noqa: BLE001
            continue
        out.append(Sat(name=name, line1=l1, line2=l2, sr=sr))
    return out


# ──────────────────────────────────────────────────────────────────────
# Time helpers
# ──────────────────────────────────────────────────────────────────────
def _as_utc_datetime(dt) -> datetime:
    """Coerce ``dt`` to a tz-aware UTC ``datetime``."""
    if isinstance(dt, pd.Timestamp):
        if dt.tzinfo is None:
            dt = dt.tz_localize("UTC")
        else:
            dt = dt.tz_convert("UTC")
        return dt.to_pydatetime()
    if isinstance(dt, datetime):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    raise TypeError(f"Unsupported datetime type: {type(dt)!r}")


def _jday(dt: datetime) -> tuple[float, float]:
    """Return the two-part Julian date the SGP4 ``sgp4()`` wants."""
    from sgp4.api import jday
    return jday(dt.year, dt.month, dt.day,
                dt.hour, dt.minute, dt.second + dt.microsecond * 1e-6)


def tle_epoch(sat: Sat) -> datetime | None:
    """Return the TLE epoch (UTC) or ``None`` if it can't be parsed."""
    sr = sat.sr
    if sr is None:
        return None
    try:
        y = int(getattr(sr, "epochyr"))
        d = float(getattr(sr, "epochdays"))
    except Exception:  # noqa: BLE001
        # Fallback: parse columns 19..32 of line 1 (YYDDD.DDDDDDDD).
        try:
            y = int(sat.line1[18:20])
            d = float(sat.line1[20:32])
        except Exception:  # noqa: BLE001
            return None
    year = 2000 + y if y < 57 else 1900 + y
    jd_start = datetime(year, 1, 1, tzinfo=timezone.utc)
    return jd_start + pd.Timedelta(days=d - 1)


# ──────────────────────────────────────────────────────────────────────
# Propagation
# ──────────────────────────────────────────────────────────────────────
def propagate(sat: Sat, dt) -> tuple[np.ndarray, np.ndarray] | None:
    """Return ECI (TEME) position/velocity in km, km/s for ``sat`` at ``dt``.

    Returns ``None`` if the SGP4 integration errored.
    """
    sr = sat.sr
    if sr is None:
        return None
    jd, fr = _jday(_as_utc_datetime(dt))
    e, r, v = sr.sgp4(jd, fr)
    if e != 0:
        return None
    return np.array(r, dtype=float), np.array(v, dtype=float)


# ──────────────────────────────────────────────────────────────────────
# Coordinate frames
# ──────────────────────────────────────────────────────────────────────
def _gmst_rad(dt: datetime) -> float:
    """Greenwich Mean Sidereal Time in radians (IAU-82 approximation)."""
    # Julian centuries since J2000.0
    jd, fr = _jday(dt)
    T = ((jd - 2451545.0) + fr) / 36525.0
    # seconds of GMST
    gmst = (67310.54841
            + (876600.0 * 3600.0 + 8640184.812866) * T
            + 0.093104 * T * T
            - 6.2e-6 * T * T * T)
    # normalise to [0, 2π)
    gmst_rad = (gmst % 86400.0) / 240.0 * _DEG
    if gmst_rad < 0:
        gmst_rad += 2 * math.pi
    return gmst_rad


def eci_to_ecef(r_eci: np.ndarray, dt) -> np.ndarray:
    """Rotate an ECI vector into ECEF using GMST."""
    theta = _gmst_rad(_as_utc_datetime(dt))
    c, s = math.cos(theta), math.sin(theta)
    rot = np.array([[ c,  s, 0.0],
                    [-s,  c, 0.0],
                    [0.0, 0.0, 1.0]])
    return rot @ r_eci


def ecef_to_geodetic(r: np.ndarray) -> tuple[float, float, float]:
    """WGS-84 ECEF → (lat°, lon°, alt km)."""
    x, y, z = float(r[0]), float(r[1]), float(r[2])
    lon = math.atan2(y, x)
    p = math.sqrt(x * x + y * y)
    # Bowring's iterative solution, 2 iterations is plenty for satellite alts.
    lat = math.atan2(z, p * (1.0 - E2))
    for _ in range(5):
        sinlat = math.sin(lat)
        N = RE_KM / math.sqrt(1.0 - E2 * sinlat * sinlat)
        lat = math.atan2(z + E2 * N * sinlat, p)
    sinlat = math.sin(lat)
    N = RE_KM / math.sqrt(1.0 - E2 * sinlat * sinlat)
    alt = p / math.cos(lat) - N
    return lat * _RAD, lon * _RAD, alt


def geodetic_to_ecef(lat_deg: float, lon_deg: float, alt_km: float = 0.0) -> np.ndarray:
    """WGS-84 geodetic → ECEF vector (km)."""
    lat = lat_deg * _DEG
    lon = lon_deg * _DEG
    sinlat = math.sin(lat)
    N = RE_KM / math.sqrt(1.0 - E2 * sinlat * sinlat)
    x = (N + alt_km) * math.cos(lat) * math.cos(lon)
    y = (N + alt_km) * math.cos(lat) * math.sin(lon)
    z = (N * (1.0 - E2) + alt_km) * sinlat
    return np.array([x, y, z], dtype=float)


def ecef_to_enu(r_ecef_sat: np.ndarray,
                lat_deg: float, lon_deg: float, alt_km: float = 0.0) -> np.ndarray:
    """Transform an ECEF position into ENU relative to the given observer."""
    obs = geodetic_to_ecef(lat_deg, lon_deg, alt_km)
    d = r_ecef_sat - obs
    lat = lat_deg * _DEG
    lon = lon_deg * _DEG
    sl, cl = math.sin(lat), math.cos(lat)
    so, co = math.sin(lon), math.cos(lon)
    # ENU rotation (row-major: east, north, up)
    R = np.array([[-so,      co,      0.0],
                  [-sl * co, -sl * so,  cl],
                  [ cl * co,  cl * so,  sl]])
    return R @ d


# ──────────────────────────────────────────────────────────────────────
# Top-level geometry queries
# ──────────────────────────────────────────────────────────────────────
def look_angles(sat: Sat, dt, lat_deg: float, lon_deg: float,
                alt_km: float = 0.0) -> LookAngle | None:
    """Return elevation / azimuth / slant range for ``sat`` at ``dt``.

    ``None`` if SGP4 failed on this epoch.
    """
    pv = propagate(sat, dt)
    if pv is None:
        return None
    r_eci = pv[0]
    r_ecef = eci_to_ecef(r_eci, dt)
    enu = ecef_to_enu(r_ecef, lat_deg, lon_deg, alt_km)
    e, n, u = float(enu[0]), float(enu[1]), float(enu[2])
    rng = math.sqrt(e * e + n * n + u * u)
    el = math.asin(u / rng) * _RAD
    az = math.atan2(e, n) * _RAD
    if az < 0:
        az += 360.0
    return LookAngle(el_deg=el, az_deg=az, range_km=rng)


def sat_subpoint(sat: Sat, dt) -> tuple[float, float, float] | None:
    """Geodetic sub-satellite point ``(lat°, lon°, alt_km)`` or ``None``."""
    pv = propagate(sat, dt)
    if pv is None:
        return None
    r_ecef = eci_to_ecef(pv[0], dt)
    return ecef_to_geodetic(r_ecef)


def sky_positions(sats: Sequence[Sat], dt, lat_deg: float, lon_deg: float,
                  min_el_deg: float = 0.0,
                  alt_km: float = 0.0) -> pd.DataFrame:
    """Return a DataFrame of (name, el_deg, az_deg, range_km, visible).

    ``visible`` = True iff ``el_deg > min_el_deg``. All satellites that
    were below the horizon are included with ``visible=False`` and
    negative elevation, which is what the sky-plot renderer needs to
    draw the faded below-horizon dots.
    """
    rows: list[dict] = []
    for s in sats:
        la = look_angles(s, dt, lat_deg, lon_deg, alt_km)
        if la is None:
            continue
        rows.append(
            dict(
                name=s.name,
                el_deg=la.el_deg,
                az_deg=la.az_deg,
                range_km=la.range_km,
                visible=la.el_deg > min_el_deg,
            )
        )
    return pd.DataFrame(rows)


def visibility_radius_km(min_el_deg: float, h_sat_km: float) -> float:
    """Great-circle radius of the visibility footprint.

    Handy for drawing the dashed horizon circle on the Leaflet map.
    """
    if min_el_deg >= 90:
        return 0.0
    eps = math.radians(min_el_deg)
    return RE_KM * (math.acos(RE_KM * math.cos(eps) / (RE_KM + h_sat_km)) - eps)
