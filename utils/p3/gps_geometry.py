"""GPS constellation geometry — PDOP estimation for Phase 3.

Phase 1 packets carry the *reported* gps-fix time but no geometry
info; to explain "why was TTFF slow?" we need to reconstruct how the
GPS constellation looked at that moment. This module gives us a cheap
PDOP estimate from SGP4-propagated GPS ephemeris.

PDOP formula (Kaplan, "Understanding GPS", 2nd ed., §7.1):

    H = [[−cos(e)·sin(a), −cos(e)·cos(a), −sin(e), 1], …]
    G = (HᵀH)⁻¹
    PDOP = sqrt(G[0,0] + G[1,1] + G[2,2])

``H`` uses the observer-relative ENU line-of-sight unit vectors to each
visible satellite. With four or fewer sats above the mask we return a
sentinel 99 so the downstream correlation tables don't accidentally
compute a rank-deficient inverse.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np
import pandas as pd

from utils.p3.sgp4_engine import Sat, look_angles

_DEG = math.pi / 180.0

# GPS acquisition mask the u-blox ZOE-M8Q uses by default.
GPS_MIN_EL_DEG = 5.0


def gps_visibility(sats: Sequence[Sat], dt,
                   lat_deg: float, lon_deg: float,
                   alt_km: float = 0.0,
                   min_el_deg: float = GPS_MIN_EL_DEG) -> pd.DataFrame:
    """Return GPS sky state: columns ``name, el_deg, az_deg, visible``."""
    rows = []
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


def pdop(vis: pd.DataFrame) -> float:
    """Compute PDOP from a visibility DataFrame.

    Uses the rows where ``visible`` is True. Returns 99.0 if the
    design matrix is rank-deficient (fewer than 4 visible sats or
    degenerate geometry).
    """
    if vis is None or vis.empty:
        return 99.0
    v = vis[vis["visible"] == True]  # noqa: E712
    if len(v) < 4:
        return 99.0
    el = v["el_deg"].to_numpy(dtype=float)
    az = v["az_deg"].to_numpy(dtype=float)
    ce = np.cos(el * _DEG)
    se = np.sin(el * _DEG)
    ca = np.cos(az * _DEG)
    sa = np.sin(az * _DEG)
    H = np.column_stack([-ce * sa, -ce * ca, -se, np.ones_like(el)])
    try:
        HtH = H.T @ H
        G = np.linalg.inv(HtH)
    except np.linalg.LinAlgError:
        return 99.0
    val = float(G[0, 0] + G[1, 1] + G[2, 2])
    if val < 0:
        return 99.0
    return math.sqrt(val)


def summarise(vis: pd.DataFrame) -> dict:
    """Condense a visibility DataFrame into the columns the CSV export uses."""
    if vis is None or vis.empty:
        return dict(GPS_N_VISIBLE=0, GPS_MAX_EL_deg=0.0,
                    GPS_N_HIGH_EL=0, GPS_PDOP=99.0)
    v = vis[vis["visible"] == True]  # noqa: E712
    if v.empty:
        return dict(GPS_N_VISIBLE=0, GPS_MAX_EL_deg=0.0,
                    GPS_N_HIGH_EL=0, GPS_PDOP=99.0)
    return dict(
        GPS_N_VISIBLE=int(len(v)),
        GPS_MAX_EL_deg=float(v["el_deg"].max()),
        GPS_N_HIGH_EL=int((v["el_deg"] > 30.0).sum()),
        GPS_PDOP=round(pdop(vis), 2),
    )
