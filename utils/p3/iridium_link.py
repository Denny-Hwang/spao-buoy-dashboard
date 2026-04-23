"""Iridium SBD link-budget physics for Phase 3.

Values and formulas mirror the HTML demo shipped with the design doc
so the Streamlit port and the prototype yield the same numbers. The
model is intentionally simple — a deterministic link-margin computation
plus a logistic P(success) — because FY25 field data shows that the
Iridium Short-Burst-Data modem's failures are *not* dominated by
geometry above the 8.2° mask; detailed handoff modelling adds noise
without adding insight.
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np

# ── Physical constants ─────────────────────────────────────────────
C_MPS = 2.998e8
F_IRIDIUM_HZ = 1.6255e9
LAMBDA_M = C_MPS / F_IRIDIUM_HZ

RE_KM = 6378.137
H_IRIDIUM_KM = 781.0

_DEG = math.pi / 180.0

# ── Link-budget parameters (RockBLOCK 9603 + Iridium GS) ───────────
# TX side (buoy)
P_TX_DBM = 32.0
L_CABLE_DB = 2.0

# Antenna gain (patch-like, ≈3 dBi peak; drop-off scales with off-axis)
ANT_MAIN_LOBE_DB = 3.0
ANT_FALLOFF_EXP = 1.3

# RX side (Iridium ground segment + satellite)
G_OVER_T_DB_K = -16.0
BOLTZMANN_DBHZ = 228.6
REQ_CNO_DBHZ = 42.0

MIN_EL_DEG = 8.2                 # Iridium acquisition minimum


# ── Primitive helpers ──────────────────────────────────────────────
def antenna_gain_db(off_axis_deg: float) -> float:
    """Simple patch-antenna gain model.

    Falls off as ``3·cos^1.3(θ)`` until θ=90°, then clamps to a deep
    null at -20 dB to avoid -inf when the sat is directly under the
    buoy's hull.
    """
    a = abs(off_axis_deg)
    if a >= 90.0:
        return -20.0
    return ANT_MAIN_LOBE_DB * (math.cos(a * _DEG) ** ANT_FALLOFF_EXP)


def off_axis_angle_deg(tilt_deg: float, tilt_azimuth_deg: float,
                       sat_el_deg: float, sat_az_deg: float) -> float:
    """Angle between the antenna boresight and the satellite LOS.

    ``tilt_deg``=0 means the antenna points at zenith; in that case
    the off-axis angle equals (90° − elevation).
    """
    if tilt_deg == 0.0:
        return 90.0 - sat_el_deg
    tr = tilt_deg * _DEG
    ta = tilt_azimuth_deg * _DEG
    bx = math.sin(tr) * math.cos(ta)
    by = math.sin(tr) * math.sin(ta)
    bz = math.cos(tr)
    er = (90.0 - sat_el_deg) * _DEG
    ea = sat_az_deg * _DEG
    dot = (bx * math.sin(er) * math.cos(ea)
           + by * math.sin(er) * math.sin(ea)
           + bz * math.cos(er))
    dot = max(-1.0, min(1.0, dot))
    return math.acos(dot) / _DEG


def slant_range_km(el_deg: float, h_sat_km: float = H_IRIDIUM_KM) -> float:
    """Slant range from ground to satellite at elevation ``el_deg``."""
    if el_deg <= -90.0 or el_deg >= 90.0:
        return float("inf")
    sin_e = math.sin(el_deg * _DEG)
    cos_e = math.cos(el_deg * _DEG)
    # Standard law of cosines in Earth-satellite triangle.
    r1 = RE_KM + h_sat_km
    r0 = RE_KM
    # d = −r0·sin(e) + sqrt(r1² − (r0·cos(e))²)
    inner = r1 * r1 - (r0 * cos_e) ** 2
    if inner < 0:
        return float("inf")
    return -r0 * sin_e + math.sqrt(inner)


def fspl_db(d_km: float) -> float:
    """Free-space path loss for a given slant range (km)."""
    d_m = max(1.0, d_km * 1000.0)
    return 20.0 * math.log10(4.0 * math.pi * d_m / LAMBDA_M)


def atmospheric_loss_db(el_deg: float) -> float:
    """Simple cosecant-scaled atmospheric loss.

    Below 5° we cap it at 4 dB — the real loss blows up but we don't
    ever transmit down there anyway.
    """
    if el_deg <= 5.0:
        return 4.0
    return 0.3 / math.sin(el_deg * _DEG)


# ── Top-level link margin / success probability ────────────────────
def link_margin_db(el_deg: float,
                   ant_gain_db: float | None = None,
                   h_sat_km: float = H_IRIDIUM_KM) -> float:
    """Deterministic link margin (dB).

    When ``ant_gain_db`` is omitted, the boresight-at-zenith assumption
    is used (gain derived from 90 − elevation). This matches the
    shortcut the HTML demo's Tracker / Field-Replay use.
    """
    if ant_gain_db is None:
        ant_gain_db = antenna_gain_db(90.0 - el_deg)
    sr = slant_range_km(el_deg, h_sat_km)
    return (P_TX_DBM
            - L_CABLE_DB
            + ant_gain_db
            - fspl_db(sr)
            - atmospheric_loss_db(el_deg)
            + G_OVER_T_DB_K
            + BOLTZMANN_DBHZ
            - REQ_CNO_DBHZ)


def p_success(margin_db: float, el_deg: float) -> float:
    """Combined acquisition × link probability of a single attempt.

    * ``P_link``  is a shallow logistic centred at margin=5 dB.
    * ``P_acq``   is elevation-dependent (acquisition gets harder at
      grazing incidence because of multipath + handoff).
    """
    if margin_db < 0:
        return 0.05
    p_link = 1.0 / (1.0 + math.exp(-0.5 * (margin_db - 5.0)))
    if el_deg >= 50.0:
        p_acq = 0.95
    elif el_deg >= 30.0:
        p_acq = 0.88 + 0.07 * (el_deg - 30.0) / 20.0
    elif el_deg >= 15.0:
        p_acq = 0.65 + 0.23 * (el_deg - 15.0) / 15.0
    else:
        p_acq = 0.30 + 0.35 * max(0.0, el_deg - 5.0) / 10.0
    return min(0.97, p_link * max(0.0, p_acq))


def acquisition_time_s(el_deg: float, margin_db: float) -> float:
    """Expected single-pass acquisition time in seconds.

    Matches the prototype's piecewise model — tuned so that the default
    FY25 baseline at 60°/15 dB lands near the 11 s figure operators see
    in the field.
    """
    if el_deg >= 60.0:
        base = 11.5
    elif el_deg >= 30.0:
        base = 21.0
    elif el_deg >= 15.0:
        base = 45.0
    else:
        base = 90.0
    if margin_db < 10.0:
        base *= 1.3
    return base


def cumulative_p_success(attempts: Iterable[tuple[float, float]]) -> float:
    """Combine independent attempt probabilities into one success P.

    Each element of ``attempts`` is ``(margin_db, el_deg)``.
    """
    q = 1.0
    for m, el in attempts:
        q *= 1.0 - p_success(m, el)
    return 1.0 - q


# ── Vectorised helpers (pandas convenience) ────────────────────────
def vector_link_margin(el_deg: np.ndarray) -> np.ndarray:
    """Apply :func:`link_margin_db` element-wise to an elevation array."""
    return np.array([link_margin_db(float(e)) for e in np.asarray(el_deg)])
