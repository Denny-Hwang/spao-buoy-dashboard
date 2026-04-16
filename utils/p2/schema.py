"""
Phase 2 enrichment schema.

Defines the enriched column set written by cron jobs into Google Sheets,
their dtypes/scale factors, an `EnrichFlag` bitfield recording which
sources succeeded per-row, and encode/decode helpers for Sheet I/O.

All integer-scaled columns are stored in Sheets as ints (or empty string
for NaN) so that rows remain compact and human-inspectable.
"""

from __future__ import annotations

import math
from enum import IntFlag
from typing import Any

import numpy as np

# ──────────────────────────────────────────────────────────────────────
# Column registry
#
# Mapping: column_name -> (numpy_dtype, scale_factor, unit, source_tag)
#
# Encoded value (int stored in Sheet) = round(physical_value * scale_factor)
# Decoded physical value               = raw / scale_factor
# ──────────────────────────────────────────────────────────────────────
ENRICHED_COLUMNS: dict[str, tuple[str, float, str, str]] = {
    # Waves (Open-Meteo Marine)
    "WAVE_H_cm":        ("int16", 100.0,  "m",       "open_meteo_marine"),
    "WAVE_T_ds":        ("int16", 10.0,   "s",       "open_meteo_marine"),
    "WAVE_DIR_deg":     ("int16", 1.0,    "deg",     "open_meteo_marine"),
    "SWELL_H_cm":       ("int16", 100.0,  "m",       "open_meteo_marine"),
    "SWELL_T_ds":       ("int16", 10.0,   "s",       "open_meteo_marine"),
    # Wind / atmosphere (Open-Meteo Historical / ERA5)
    "WIND_SPD_cms":     ("int16", 100.0,  "m/s",     "open_meteo_historical"),
    "WIND_DIR_deg":     ("int16", 1.0,    "deg",     "open_meteo_historical"),
    "ERA5_PRES_dPa":    ("int16", 0.1,    "Pa",      "open_meteo_historical"),
    "ERA5_AIRT_cC":     ("int16", 100.0,  "degC",    "open_meteo_historical"),
    # Satellite / reanalysis SST
    "SAT_SST_OISST_cC": ("int16", 100.0,  "degC",    "noaa_oisst"),
    "SAT_SST_ERA5_cC":  ("int16", 100.0,  "degC",    "era5_sst"),
    "SAT_SST_MUR_cC":   ("int16", 100.0,  "degC",    "mur_sst"),
    "SAT_SST_OSTIA_cC": ("int16", 100.0,  "degC",    "ostia"),
    # Open-Meteo general weather-API reference: covers coastal / inland
    # points where satellite SST products are masked (e.g. Richland, WA
    # river deployment). Over ocean uses Marine `sea_surface_temperature`;
    # over land falls back to ERA5-Land `soil_temperature_0cm`.
    "SAT_SST_OPENMETEO_cC": ("int16", 100.0, "degC",  "open_meteo_sst"),
    # Surface currents (OSCAR)
    "OSCAR_U_mms":      ("int16", 1000.0, "m/s",     "oscar"),
    "OSCAR_V_mms":      ("int16", 1000.0, "m/s",     "oscar"),
    # Sea ice
    "SEAICE_CONC_pct":  ("int16", 1.0,    "percent", "osi_saf_seaice"),
    # Enrichment success bitfield
    "ENRICH_FLAG":      ("uint16", 1.0,   "bitfield", "internal"),
}


class EnrichFlag(IntFlag):
    """Bitfield recording which enrichment sources succeeded for a row."""

    WAVE = 1
    WIND = 2
    ERA5_ATMOS = 4
    OISST = 8
    MUR = 16
    OSTIA = 32
    OSCAR = 64
    SEAICE = 128
    ERA5_SST = 256
    OPEN_METEO_SST = 512


FULL_ENRICHED_FLAG: EnrichFlag = (
    EnrichFlag.WAVE
    | EnrichFlag.WIND
    | EnrichFlag.ERA5_ATMOS
    | EnrichFlag.OISST
    | EnrichFlag.MUR
    | EnrichFlag.OSTIA
    | EnrichFlag.OSCAR
    | EnrichFlag.SEAICE
    | EnrichFlag.ERA5_SST
    | EnrichFlag.OPEN_METEO_SST
)


ENRICH_COLUMN_ORDER: list[str] = [
    "WAVE_H_cm",
    "WAVE_T_ds",
    "WAVE_DIR_deg",
    "SWELL_H_cm",
    "SWELL_T_ds",
    "WIND_SPD_cms",
    "WIND_DIR_deg",
    "ERA5_PRES_dPa",
    "ERA5_AIRT_cC",
    "SAT_SST_OISST_cC",
    "SAT_SST_ERA5_cC",
    "SAT_SST_MUR_cC",
    "SAT_SST_OSTIA_cC",
    "SAT_SST_OPENMETEO_cC",
    "OSCAR_U_mms",
    "OSCAR_V_mms",
    "SEAICE_CONC_pct",
    "ENRICH_FLAG",
]


def _is_nan(val: Any) -> bool:
    if val is None:
        return True
    try:
        return bool(math.isnan(float(val)))
    except (TypeError, ValueError):
        return False


def encode_value(col: str, val: Any) -> int | str:
    """Encode a physical value for storage in Google Sheets.

    Returns ``""`` (empty string) for NaN / missing so the Sheet cell
    is blank rather than the literal string "nan".
    """
    if col not in ENRICHED_COLUMNS:
        raise KeyError(f"Unknown enriched column: {col}")
    if _is_nan(val):
        return ""
    _dtype, scale, _unit, _source = ENRICHED_COLUMNS[col]
    try:
        return int(round(float(val) * scale))
    except (TypeError, ValueError):
        return ""


def decode_value(col: str, raw: Any) -> float:
    """Decode a Sheets-stored value back to its physical value.

    Returns ``NaN`` for empty strings, None, or unparseable inputs.
    """
    if col not in ENRICHED_COLUMNS:
        raise KeyError(f"Unknown enriched column: {col}")
    if raw is None or raw == "":
        return float("nan")
    _dtype, scale, _unit, _source = ENRICHED_COLUMNS[col]
    try:
        return float(raw) / scale
    except (TypeError, ValueError):
        return float("nan")


__all__ = [
    "ENRICHED_COLUMNS",
    "EnrichFlag",
    "FULL_ENRICHED_FLAG",
    "ENRICH_COLUMN_ORDER",
    "encode_value",
    "decode_value",
]


# Sanity: ensure numpy is importable at module load (surfaces missing dep
# early during validation rather than inside a fetcher).
assert np.uint16(FULL_ENRICHED_FLAG) == int(FULL_ENRICHED_FLAG)
