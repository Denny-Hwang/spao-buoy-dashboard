"""
Wave-power helpers based on linear deep-water wave theory.

Reference
---------
Falnes, J. (2002). *Ocean Waves and Oscillating Systems*, Eq. 6.19.

The energy flux per unit crest length of a random sea in deep water is

    P = ρ g² / (64 π) · Hs² · Te      [W/m]

where ρ is sea-water density, g is gravity, Hs is the significant wave
height, and Te is the energy period. For a JONSWAP spectrum ``Te ≈ 0.9 Tp``.

Miche (1944) gives a deep-water wave-steepness breaking limit

    s = 2 π Hs / (g Tp²)     ; s_max ≈ 0.142
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np

# Physical constants (SI). Sea-water density at 15 °C, 35 psu.
RHO_SEAWATER = 1025.0    # kg/m³
G = 9.81                 # m/s²

# Pre-computed Falnes coefficient: ρ g² / (64 π) ≈ 490.6 W/(m·m²·s).
_FALNES_COEFF = RHO_SEAWATER * G * G / (64.0 * math.pi)

# JONSWAP energy-period to peak-period ratio (DNV-RP-C205 default).
TE_OVER_TP = 0.9

# Miche 1944 breaking limit.
STEEPNESS_BREAKING = 0.142


def theoretical_wave_flux_w_per_m(
    Hs_m: float | Iterable[float],
    Tp_s: float | Iterable[float],
    te_over_tp: float = TE_OVER_TP,
    rho: float = RHO_SEAWATER,
    g: float = G,
) -> float | np.ndarray:
    """Return deep-water wave-energy flux in W per metre of crest length.

    Uses Falnes (2002) Eq. 6.19 with energy period ``Te = te_over_tp · Tp``.

    Parameters
    ----------
    Hs_m : float or array-like
        Significant wave height [m].
    Tp_s : float or array-like
        Spectral peak period [s].
    te_over_tp : float, optional
        Ratio of energy period to peak period (default 0.9, JONSWAP).
    rho : float, optional
        Sea-water density [kg/m³] (default 1025).
    g : float, optional
        Gravitational acceleration [m/s²] (default 9.81).

    Returns
    -------
    float or ndarray
        Wave-energy flux in W/m. Invalid inputs yield ``NaN``.

    Notes
    -----
    For Hs = 3.1 m, Tp = 7.0 s (Te ≈ 6.3 s) the standard formula gives
    ≈ 29.7 kW/m. Published anchor values vary between sources (27–47
    kW/m) depending on the chosen Te convention and constant.

    Example
    -------
    >>> theoretical_wave_flux_w_per_m(3.1, 7.0)  # Bering Sea deployment
    29693.4...
    # ≈ 29 700 W/m (Bering Sea conditions, Lu et al. 2026 deployment).
    """
    Hs = np.asarray(Hs_m, dtype=float)
    Tp = np.asarray(Tp_s, dtype=float)
    Te = te_over_tp * Tp
    coeff = rho * g * g / (64.0 * math.pi)
    with np.errstate(invalid="ignore"):
        P = coeff * Hs * Hs * Te
    P = np.where((Hs >= 0) & (Tp > 0), P, np.nan)
    if P.ndim == 0:
        return float(P)
    return P


def wave_steepness(
    Hs_m: float | Iterable[float],
    Tp_s: float | Iterable[float],
    g: float = G,
) -> float | np.ndarray:
    """Return deep-water wave steepness ``s = 2π Hs / (g Tp²)``.

    A value above ``STEEPNESS_BREAKING`` (≈ 0.142, Miche 1944) indicates
    the sea state has exceeded the deep-water breaking limit — unusual
    for Hs/Tp measured in open ocean.
    """
    Hs = np.asarray(Hs_m, dtype=float)
    Tp = np.asarray(Tp_s, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        s = 2.0 * math.pi * Hs / (g * Tp * Tp)
    s = np.where((Hs >= 0) & (Tp > 0), s, np.nan)
    if s.ndim == 0:
        return float(s)
    return s


__all__ = [
    "RHO_SEAWATER",
    "G",
    "TE_OVER_TP",
    "STEEPNESS_BREAKING",
    "theoretical_wave_flux_w_per_m",
    "wave_steepness",
]
