"""Join Phase 1 TX packets to satellite geometry.

This is the adapter that lets Phase 3 pages reuse Phase 1's
Google-Sheets data path without touching Phase 1 files. Responsibilities:

1. Discover the Phase 1 timestamp / lat / lon / TX-time columns in a
   DataFrame that may come from any of the six packet decoders.
2. For every row with a valid fix, propagate the Iridium and GPS
   constellations to the TX epoch and compute the Phase 3 enrichment
   columns (``IRI_*`` and ``GPS_*``).
3. Return an *enriched copy* of the DataFrame. The caller decides
   whether to show it, plot it or offer it as a CSV download — this
   module never writes to the original sheet.

Detection is tolerant: fewer than 4 visible sats → enrichment still
happens but the "best satellite" entries become ``NaN`` / empty
strings; a row with no (lat, lon, timestamp) is passed through
untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from utils.p3 import gps_geometry as _gps
from utils.p3 import iridium_link as _link
from utils.p3.sgp4_engine import Sat, look_angles


# ── Column name aliases ────────────────────────────────────────────
_TIME_ALIASES: tuple[str, ...] = (
    "Timestamp", "timestamp", "Time", "time",
    "Date Time", "DateTime", "UTC", "Date (UTC)",
)
_LAT_ALIASES: tuple[str, ...] = (
    "Lat", "Latitude", "GPS Lat", "GPS_Latitude", "Approx Latitude",
    "Latitude (°)", "Latitude (deg)",
)
_LON_ALIASES: tuple[str, ...] = (
    "Lon", "Lng", "Longitude", "GPS Lon", "GPS_Longitude", "Approx Longitude",
    "Longitude (°)", "Longitude (deg)",
)
_RB1_ALIASES: tuple[str, ...] = (
    "RockBLOCK Time", "RB Time", "rb1", "RB1",
    "Prev 1st RB Time", "1st RB Time",
)
_RB2_ALIASES: tuple[str, ...] = (
    "Prev 2nd RB Time", "2nd RB Time", "rb2", "RB2",
)
_GPST_ALIASES: tuple[str, ...] = (
    "GPS Time", "Prev GPS Time", "TTFF", "GPS Acquisition Time",
)

# Iridium acquisition minimum the constellation is specified down to.
IRI_MIN_EL_DEG = 8.2

# The columns Phase 3 adds to any enriched frame.
P3_COLUMNS: tuple[str, ...] = (
    "IRI_N_VISIBLE", "IRI_BEST_EL_deg", "IRI_BEST_AZ_deg",
    "IRI_BEST_SAT", "IRI_LINK_MARGIN_dB", "IRI_P_SUCCESS",
    "GPS_N_VISIBLE", "GPS_N_HIGH_EL", "GPS_MAX_EL_deg", "GPS_PDOP",
    "TLE_EPOCH_AGE_HRS",
)


# ── Column discovery ──────────────────────────────────────────────
def _first_match(df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


@dataclass(frozen=True)
class ColumnMap:
    """Resolved Phase 1 column names used by the join layer."""
    time: str | None
    lat: str | None
    lon: str | None
    rb1: str | None
    rb2: str | None
    gpst: str | None

    def ready(self) -> bool:
        return self.time is not None and self.lat is not None and self.lon is not None


def resolve_columns(df: pd.DataFrame) -> ColumnMap:
    """Best-effort alias matching for Phase 1 packet frames."""
    time_col = _first_match(df, _TIME_ALIASES)
    if time_col is None:
        for c in df.columns:
            if any(k in str(c).lower() for k in ("time", "timestamp", "date")):
                time_col = c
                break
    return ColumnMap(
        time=time_col,
        lat=_first_match(df, _LAT_ALIASES),
        lon=_first_match(df, _LON_ALIASES),
        rb1=_first_match(df, _RB1_ALIASES),
        rb2=_first_match(df, _RB2_ALIASES),
        gpst=_first_match(df, _GPST_ALIASES),
    )


# ── Core join ─────────────────────────────────────────────────────
def _empty_row() -> dict:
    return {col: np.nan if "SAT" not in col else "" for col in P3_COLUMNS}


def _iridium_summary(sats: Sequence[Sat], dt, lat: float, lon: float) -> dict:
    """Compute the Iridium summary columns for one TX epoch."""
    best_el = -90.0
    best_az = np.nan
    best_name = ""
    n_vis = 0
    for s in sats:
        la = look_angles(s, dt, lat, lon)
        if la is None:
            continue
        if la.el_deg > IRI_MIN_EL_DEG:
            n_vis += 1
            if la.el_deg > best_el:
                best_el = la.el_deg
                best_az = la.az_deg
                best_name = s.name
    if n_vis == 0:
        return dict(IRI_N_VISIBLE=0,
                    IRI_BEST_EL_deg=np.nan,
                    IRI_BEST_AZ_deg=np.nan,
                    IRI_BEST_SAT="",
                    IRI_LINK_MARGIN_dB=np.nan,
                    IRI_P_SUCCESS=0.0)
    margin = _link.link_margin_db(best_el)
    return dict(
        IRI_N_VISIBLE=n_vis,
        IRI_BEST_EL_deg=round(best_el, 2),
        IRI_BEST_AZ_deg=round(best_az, 1),
        IRI_BEST_SAT=best_name,
        IRI_LINK_MARGIN_dB=round(margin, 2),
        IRI_P_SUCCESS=round(_link.p_success(margin, best_el), 3),
    )


def enrich_phase1_frame(
    df: pd.DataFrame,
    iridium_sats: Sequence[Sat],
    gps_sats: Sequence[Sat],
    *,
    tle_epoch_utc: "pd.Timestamp | None" = None,
    cols: ColumnMap | None = None,
) -> pd.DataFrame:
    """Return a copy of ``df`` with the Phase 3 ``IRI_*`` / ``GPS_*`` columns.

    Parameters
    ----------
    df
        A Phase 1 DataFrame (any of the decoder versions is fine).
    iridium_sats, gps_sats
        Parsed :class:`Sat` lists from :mod:`utils.p3.tle_io`.
    tle_epoch_utc
        Optional representative TLE epoch for the ``TLE_EPOCH_AGE_HRS``
        audit column. If ``None``, the median Iridium epoch is used.
    cols
        Override for column-name resolution — handy in tests.
    """
    if df is None or df.empty:
        return df.copy() if df is not None else pd.DataFrame()
    cm = cols or resolve_columns(df)
    out = df.copy()
    for col in P3_COLUMNS:
        out[col] = "" if "SAT" in col else np.nan

    if not cm.ready():
        return out

    tle_epoch_age_fill = _tle_age_hours(iridium_sats, tle_epoch_utc)

    ts = pd.to_datetime(out[cm.time], errors="coerce", utc=True)
    lats = pd.to_numeric(out[cm.lat], errors="coerce")
    lons = pd.to_numeric(out[cm.lon], errors="coerce")

    for idx in out.index:
        t = ts.loc[idx]
        la = lats.loc[idx]
        lo = lons.loc[idx]
        if pd.isna(t) or pd.isna(la) or pd.isna(lo):
            continue
        if la == 0.0 and lo == 0.0:
            # Phase 1 convention for "no fix" — skip satellite math so
            # the caller can tell geometry from a failed GPS attempt.
            continue
        dt = t.to_pydatetime()
        iri = _iridium_summary(iridium_sats, dt, float(la), float(lo))
        gps_vis = _gps.gps_visibility(gps_sats, dt, float(la), float(lo))
        gps_sum = _gps.summarise(gps_vis)
        for k, v in {**iri, **gps_sum}.items():
            out.at[idx, k] = v
        out.at[idx, "TLE_EPOCH_AGE_HRS"] = tle_epoch_age_fill

    return out


# ── Helpers ───────────────────────────────────────────────────────
def _tle_age_hours(sats: Sequence[Sat],
                   tle_epoch_utc: "pd.Timestamp | None") -> float:
    """Return a representative TLE age in hours for the audit column."""
    from utils.p3.sgp4_engine import tle_epoch as _epoch
    if tle_epoch_utc is not None:
        ts = pd.Timestamp(tle_epoch_utc)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        now = pd.Timestamp.utcnow().tz_localize("UTC") if pd.Timestamp.utcnow().tzinfo is None else pd.Timestamp.utcnow()
        return round((now - ts).total_seconds() / 3600.0, 2)
    if not sats:
        return np.nan
    epochs = [_epoch(s) for s in sats]
    epochs = [e for e in epochs if e is not None]
    if not epochs:
        return np.nan
    epochs.sort()
    med = epochs[len(epochs) // 2]
    from datetime import datetime, timezone
    return round((datetime.now(timezone.utc) - med).total_seconds() / 3600.0, 2)
