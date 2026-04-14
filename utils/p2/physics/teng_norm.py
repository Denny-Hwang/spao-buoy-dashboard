"""
TENG power proxies and sea-state normalization.

.. warning::

   The efficiency levels defined here are **proxies only**. They do not
   isolate generator degradation from sea-state variability: a decline
   in ``eta_level2`` can mean the TENG is degrading *or* that wave
   climatology has shifted. Always pair these metrics with direct
   health indicators (RMS voltage, peak output) before drawing
   conclusions.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

# Columns we are willing to interpret as TENG power in milliwatts,
# in priority order.
_TENG_POWER_ALIASES = (
    "TENG_P_mW", "TENG Power (mW)", "TENG_Power_mW", "TENG P mW",
    "TENG_Power", "TENG_P", "teng_power_mw",
)
_TENG_VOLT_ALIASES = ("TENG_V", "TENG V", "TENG_Voltage", "TENG_V_V", "TENG_Vrms")
_TENG_CURR_ALIASES = ("TENG_I", "TENG I", "TENG_Current", "TENG_I_A", "TENG_Irms")

_HS_ALIASES = ("Hs", "Hs_m", "WAVE_H_m", "wave_height", "WAVE_H_cm")
_TP_ALIASES = ("Tp", "Tp_s", "WAVE_T_s", "wave_period", "WAVE_T_ds")


def _first_present(df: pd.DataFrame, aliases: Iterable[str]) -> str | None:
    for a in aliases:
        if a in df.columns:
            return a
    return None


def _series(df: pd.DataFrame, aliases: Iterable[str]) -> pd.Series | None:
    col = _first_present(df, aliases)
    if col is None:
        return None
    return pd.to_numeric(df[col], errors="coerce")


def teng_power_mw(df: pd.DataFrame) -> pd.Series:
    """Return instantaneous TENG power in milliwatts as a Series.

    Resolution order:
        1. Any column in ``_TENG_POWER_ALIASES`` — used as-is.
        2. Derived ``V * I * 1000`` if voltage and current columns exist
           (W → mW conversion).
        3. All-NaN series the length of ``df``.
    """
    p = _series(df, _TENG_POWER_ALIASES)
    if p is not None:
        return p.astype(float).rename("TENG_P_mW")
    v = _series(df, _TENG_VOLT_ALIASES)
    i = _series(df, _TENG_CURR_ALIASES)
    if v is not None and i is not None:
        return (v * i * 1000.0).rename("TENG_P_mW")
    return pd.Series(np.nan, index=df.index, name="TENG_P_mW")


def _hs_series(df: pd.DataFrame) -> pd.Series:
    col = _first_present(df, _HS_ALIASES)
    if col is None:
        return pd.Series(np.nan, index=df.index, name="Hs_m")
    s = pd.to_numeric(df[col], errors="coerce")
    # WAVE_H_cm is stored in centimetres in the enriched schema.
    if col == "WAVE_H_cm":
        s = s / 100.0
    return s.rename("Hs_m")


def _tp_series(df: pd.DataFrame) -> pd.Series:
    col = _first_present(df, _TP_ALIASES)
    if col is None:
        return pd.Series(np.nan, index=df.index, name="Tp_s")
    s = pd.to_numeric(df[col], errors="coerce")
    if col == "WAVE_T_ds":
        s = s / 10.0
    return s.rename("Tp_s")


def eta_level0(df: pd.DataFrame) -> pd.Series:
    """Raw TENG power (mW) — no sea-state normalization applied.

    Useful as a baseline against which levels 1 and 2 are compared.
    """
    return teng_power_mw(df).rename("eta_level0")


def eta_level1(df: pd.DataFrame, eps: float = 1e-6) -> pd.Series:
    """Level-1 normalization: ``P_TENG / Hs²``.

    This partially removes the dependence of output on wave amplitude.
    """
    p = teng_power_mw(df)
    hs = _hs_series(df)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = p / np.maximum(hs * hs, eps)
    out = out.where(hs > 0, np.nan)
    return out.rename("eta_level1")


def eta_level2(df: pd.DataFrame, eps: float = 1e-6) -> pd.Series:
    """Level-2 normalization: ``P_TENG / (Hs² · Tp)``.

    Normalizes by the wave-flux proxy ``Hs² · Tp`` so the metric is
    roughly proportional to generator efficiency under linear wave theory.
    Still a **proxy** — see module-level warning.
    """
    p = teng_power_mw(df)
    hs = _hs_series(df)
    tp = _tp_series(df)
    with np.errstate(invalid="ignore", divide="ignore"):
        denom = np.maximum(hs * hs * tp, eps)
        out = p / denom
    out = out.where((hs > 0) & (tp > 0), np.nan)
    return out.rename("eta_level2")


__all__ = [
    "teng_power_mw",
    "eta_level0",
    "eta_level1",
    "eta_level2",
]
