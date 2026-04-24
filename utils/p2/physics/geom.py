"""Geodesy helpers shared across Phase 2 physics modules.

Previously each of ``derived.py`` and ``qc.py`` carried its own copy of
the Haversine formula plus ``EARTH_RADIUS_M``. That's a small function
but three copies is three places a subtle radius or radians-conversion
fix has to be applied. This module is the single source of truth.
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np

# Spherical-Earth radius (metres). Matches the value previously used by
# ``derived.py`` and ``qc.py`` so existing test numerics don't shift.
EARTH_RADIUS_M: float = 6_371_000.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two (lat, lon) points, in kilometres.

    Scalar-only. For bulk pairs use :func:`haversine_km_array`.
    """
    rlat1 = math.radians(lat1)
    rlat2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2.0) ** 2
         + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2.0) ** 2)
    # ``max/min`` clamp defends against 1.0 + tiny_fp overflow inside asin.
    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(max(0.0, min(1.0, a)))) / 1000.0


def haversine_km_array(
    lat1: Iterable[float],
    lon1: Iterable[float],
    lat2: Iterable[float],
    lon2: Iterable[float],
) -> np.ndarray:
    """Vectorised Haversine distance (km) for parallel coordinate arrays.

    Any non-finite entry yields ``NaN`` at that position rather than
    propagating through the whole result — matches the per-point
    ``np.isfinite(...)`` guard the call sites used previously.
    """
    lat1 = np.asarray(lat1, dtype=float)
    lon1 = np.asarray(lon1, dtype=float)
    lat2 = np.asarray(lat2, dtype=float)
    lon2 = np.asarray(lon2, dtype=float)

    rlat1 = np.radians(lat1)
    rlat2 = np.radians(lat2)
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = (np.sin(dlat / 2.0) ** 2
         + np.cos(rlat1) * np.cos(rlat2) * np.sin(dlon / 2.0) ** 2)
    a = np.clip(a, 0.0, 1.0)
    km = 2.0 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a)) / 1000.0

    bad = ~(np.isfinite(lat1) & np.isfinite(lon1)
            & np.isfinite(lat2) & np.isfinite(lon2))
    km[bad] = np.nan
    return km


__all__ = ["EARTH_RADIUS_M", "haversine_km", "haversine_km_array"]
