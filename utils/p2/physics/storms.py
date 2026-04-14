"""
Storm / cyclone detection and superposed-epoch compositing.

Thresholds used by :func:`detect_storms`:

* **Wave storm** — 6-hour rolling mean ``Hs_6h ≥ 4.0 m`` *or* instantaneous
  ``Hs ≥ 5.0 m``.
* **Wind storm** — 6-hour rolling mean ``U10_6h ≥ 17.2 m/s`` (Beaufort 8,
  gale) *or* instantaneous ``U10 ≥ 20.8 m/s`` (Beaufort 9).
* **Cyclone** — Sanders & Gyakum (1980) normalized deepening rate exceeds
  the latitude-dependent "bomb" threshold,

      dP_24h ≤ -24 · sin(lat) / sin(60°)   hPa in 24 h.

The ``storm`` column is the union of the three; ``storm_type`` labels it
with the category; ``storm_event_id`` assigns a monotonically increasing
identifier to each contiguous block of stormy rows (gaps ≤ 1 h merged).
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd

WAVE_6H_MEAN_THRESHOLD = 4.0          # m
WAVE_INSTANT_THRESHOLD = 5.0          # m
WIND_6H_MEAN_THRESHOLD = 17.2         # m/s (gale)
WIND_INSTANT_THRESHOLD = 20.8         # m/s (severe gale)
SIN60 = math.sin(math.radians(60.0))

_HS_ALIASES = ("Hs", "Hs_m", "wave_height")
_U10_ALIASES = ("U10", "wind_speed_10m", "Wind_Speed")
_PRES_ALIASES = ("Pres", "surface_pressure", "SLP", "pressure")
_LAT_ALIASES = ("Lat", "Latitude", "lat")
_TS_ALIASES = ("Timestamp", "Receive Time", "time", "Time")


def _first(df: pd.DataFrame, aliases: Iterable[str]) -> str | None:
    for a in aliases:
        if a in df.columns:
            return a
    return None


def _rolling_hours(df: pd.DataFrame, col: str, ts_col: str, hours: int) -> pd.Series:
    """Hour-based rolling mean over an irregular time index."""
    ts = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
    s = pd.to_numeric(df[col], errors="coerce")
    tmp = pd.Series(s.values, index=ts).sort_index()
    roll = tmp.rolling(f"{hours}h", min_periods=1).mean()
    return pd.Series(roll.reindex(ts).values, index=df.index)


def _pressure_24h_drop(df: pd.DataFrame, pres_col: str, ts_col: str) -> pd.Series:
    """Return the change in pressure (hPa) over a 24-hour rolling window."""
    ts = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
    p = pd.to_numeric(df[pres_col], errors="coerce")
    tmp = pd.Series(p.values, index=ts).sort_index()
    p_now = tmp
    p_past = tmp.rolling("24h", min_periods=1).apply(lambda a: a.iloc[0], raw=False)
    dp = p_now - p_past
    return pd.Series(dp.reindex(ts).values, index=df.index)


def _assign_event_ids(mask: pd.Series, ts: pd.Series, gap_hours: float = 1.0) -> pd.Series:
    """Contiguous run-length encoding with a small gap tolerance."""
    ids = pd.Series(0, index=mask.index, dtype=int)
    current = 0
    last_ts = None
    in_event = False
    for i in mask.index:
        m = bool(mask.at[i])
        t = ts.at[i]
        if m:
            if not in_event or (
                last_ts is not None and (t - last_ts).total_seconds() > gap_hours * 3600
            ):
                current += 1
            in_event = True
            ids.at[i] = current
            last_ts = t
        else:
            in_event = False
    return ids


def detect_storms(df: pd.DataFrame) -> pd.DataFrame:
    """Tag each row with wave/wind/cyclone storm flags and assign event IDs.

    Added columns:
        ``wave_storm``      bool
        ``wind_storm``      bool
        ``cyclone``         bool
        ``storm``           bool (union)
        ``storm_event_id``  int (0 for non-storm rows)
        ``storm_type``      str: "", "wave", "wind", "cyclone", or combos
    """
    out = df.copy()
    ts_col = _first(out, _TS_ALIASES)
    if ts_col is None:
        raise ValueError("detect_storms: timestamp column not found")
    ts = pd.to_datetime(out[ts_col], utc=True, errors="coerce")

    # Wave
    hs_col = _first(out, _HS_ALIASES)
    if hs_col is not None:
        hs = pd.to_numeric(out[hs_col], errors="coerce")
        hs_6h = _rolling_hours(out, hs_col, ts_col, 6)
        out["wave_storm"] = (hs_6h >= WAVE_6H_MEAN_THRESHOLD) | (hs >= WAVE_INSTANT_THRESHOLD)
    else:
        out["wave_storm"] = False

    # Wind
    u10_col = _first(out, _U10_ALIASES)
    if u10_col is not None:
        u = pd.to_numeric(out[u10_col], errors="coerce")
        u_6h = _rolling_hours(out, u10_col, ts_col, 6)
        out["wind_storm"] = (u_6h >= WIND_6H_MEAN_THRESHOLD) | (u >= WIND_INSTANT_THRESHOLD)
    else:
        out["wind_storm"] = False

    # Cyclone (Sanders & Gyakum 1980)
    pres_col = _first(out, _PRES_ALIASES)
    lat_col = _first(out, _LAT_ALIASES)
    if pres_col is not None and lat_col is not None:
        dp = _pressure_24h_drop(out, pres_col, ts_col)
        lat = pd.to_numeric(out[lat_col], errors="coerce")
        sin_lat = np.sin(np.deg2rad(np.clip(lat.abs(), 1.0, 90.0)))
        threshold = -24.0 * sin_lat / SIN60
        out["cyclone"] = dp <= threshold
    else:
        out["cyclone"] = False

    out["storm"] = out["wave_storm"] | out["wind_storm"] | out["cyclone"]

    # storm_type (composite label)
    def _label(row):
        parts = []
        if row["wave_storm"]:
            parts.append("wave")
        if row["wind_storm"]:
            parts.append("wind")
        if row["cyclone"]:
            parts.append("cyclone")
        return "+".join(parts)

    out["storm_type"] = out.apply(_label, axis=1)

    out["storm_event_id"] = _assign_event_ids(out["storm"].fillna(False).astype(bool), ts)
    return out


def superposed_epoch(
    df: pd.DataFrame,
    event_times: Iterable,
    window_hours: int = 48,
    cols: list[str] | None = None,
) -> pd.DataFrame:
    """Build a superposed-epoch composite centred on each event time.

    Returns a long-format DataFrame with columns
    ``[event_idx, lag_hours, <var>, ...]`` where ``lag_hours`` spans
    ``[-window_hours, +window_hours]`` in 1-hour steps.

    Parameters
    ----------
    df : DataFrame
        Must contain a timestamp column (any alias in ``_TS_ALIASES``).
    event_times : iterable of timestamp-likes
        Reference times around which to compose.
    window_hours : int
        Half-width of the compositing window.
    cols : list of str, optional
        Columns to include. Defaults to every non-timestamp numeric column.
    """
    ts_col = _first(df, _TS_ALIASES)
    if ts_col is None:
        raise ValueError("superposed_epoch: timestamp column not found")
    ts = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
    df2 = df.copy()
    df2["_ts"] = ts

    if cols is None:
        cols = [
            c for c in df2.columns
            if c not in (ts_col, "_ts") and pd.api.types.is_numeric_dtype(df2[c])
        ]

    frames = []
    for k, ev in enumerate(event_times):
        ev_ts = pd.Timestamp(ev)
        if ev_ts.tz is None:
            ev_ts = ev_ts.tz_localize("UTC")
        else:
            ev_ts = ev_ts.tz_convert("UTC")
        lo = ev_ts - pd.Timedelta(hours=window_hours)
        hi = ev_ts + pd.Timedelta(hours=window_hours)
        window = df2[(df2["_ts"] >= lo) & (df2["_ts"] <= hi)].copy()
        if window.empty:
            continue
        window["event_idx"] = k
        window["lag_hours"] = (window["_ts"] - ev_ts).dt.total_seconds() / 3600.0
        frames.append(window[["event_idx", "lag_hours", *cols]])

    if not frames:
        return pd.DataFrame(columns=["event_idx", "lag_hours", *cols])
    return pd.concat(frames, ignore_index=True)


__all__ = [
    "WAVE_6H_MEAN_THRESHOLD",
    "WAVE_INSTANT_THRESHOLD",
    "WIND_6H_MEAN_THRESHOLD",
    "WIND_INSTANT_THRESHOLD",
    "detect_storms",
    "superposed_epoch",
]
