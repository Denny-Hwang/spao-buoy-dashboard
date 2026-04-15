"""Shared Phase 2 page toolbar.

All Phase 2 analysis pages use the same control strip:

    [ Refresh Data ]  [ Select Devices ▾ ]  [ Start / Start time / End / End time ]

``render_device_time_filter`` returns the filtered DataFrame plus the
device/time column names the page should reuse so that panels receive an
already-scoped frame. Session-state keys are namespaced via ``key_prefix``
so multiple Phase 2 pages can live side-by-side without clashing.

This module is deliberately import-light: it only touches pandas,
streamlit, and ``utils.sheets_client`` helpers at call time so tests can
exercise the pure-data path without a full Streamlit runtime.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Iterable

import pandas as pd
import streamlit as st


TIME_KEYWORDS: tuple[str, ...] = ("time", "timestamp", "date")

# ---------- Geo column aliases ---------------------------------------
# Exact-name candidates, ordered by preference. If none match, the
# substring fallback below is used — this mirrors the loose matching
# Phase 1 Analytics uses so FY25 tabs with headers like
# "Approx Latitude" / "GPS Longitude" still resolve correctly.
_LAT_ALIASES: tuple[str, ...] = (
    "Lat", "Latitude", "lat", "Lat (°)", "Latitude (°)", "Latitude (deg)",
    "GPS Lat", "GPS_Lat", "GPS Latitude", "GPS_Latitude",
)
_LON_ALIASES: tuple[str, ...] = (
    "Lon", "Lng", "Longitude", "lon", "Lon (°)", "Longitude (°)", "Longitude (deg)",
    "GPS Lon", "GPS_Lon", "GPS Longitude", "GPS_Longitude",
)
_LAT_SUBSTRINGS: tuple[str, ...] = ("latitude", "lat")
_LON_SUBSTRINGS: tuple[str, ...] = ("longitude", "lng", "lon")
_LON_EXCLUDE_SUBSTRINGS: tuple[str, ...] = ("longevity", "long-term", "longterm")


def _first_alias(df: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    for a in aliases:
        if a in df.columns:
            return a
    return None


def _first_substring(
    df: pd.DataFrame,
    needles: tuple[str, ...],
    *,
    exclude: tuple[str, ...] = (),
) -> str | None:
    for c in df.columns:
        cl = str(c).lower()
        if any(x in cl for x in exclude):
            continue
        if any(n in cl for n in needles):
            return c
    return None


def _split_compound_latlon_series(
    s: pd.Series,
) -> tuple[pd.Series, pd.Series] | None:
    """Parse a compound ``"lat,lon"`` string column into numeric pair.

    Used for FY25 Bearing-sea worksheets where GPS lives in a single
    ``Approx Lat/Lng`` column. Returns ``None`` if the values don't
    look like comma-separated float pairs. Tolerates partial garbage
    — at least one parseable pair in the first ~10 non-empty samples
    is enough to trigger the split.
    """
    def _looks_like_pair(v: str) -> bool:
        parts = [p.strip() for p in v.split(",")]
        if len(parts) != 2:
            return False
        try:
            float(parts[0])
            float(parts[1])
            return True
        except ValueError:
            return False

    sample = (
        s.dropna().astype(str).str.strip().replace("", pd.NA).dropna().head(10).tolist()
    )
    if not sample or not any(_looks_like_pair(v) for v in sample):
        return None
    lats: list[float] = []
    lons: list[float] = []
    for v in s:
        try:
            if v is None:
                raise ValueError
            txt = str(v).strip()
            if not txt:
                raise ValueError
            parts = [p.strip() for p in txt.split(",")]
            if len(parts) != 2:
                raise ValueError
            lats.append(float(parts[0]))
            lons.append(float(parts[1]))
        except (TypeError, ValueError):
            lats.append(float("nan"))
            lons.append(float("nan"))
    return pd.Series(lats, index=s.index), pd.Series(lons, index=s.index)


def resolve_lat_lon_columns(df: pd.DataFrame) -> tuple[str | None, str | None]:
    """Detect the best latitude / longitude column names in ``df``.

    Tries exact aliases first, then a substring fallback. Returns
    ``(None, None)`` if either is missing. Note: when a single
    compound column (e.g. ``"Approx Lat/Lng"``) exists, both returned
    names will be the same — callers should use
    :func:`canonicalize_lat_lon` to split it into two numeric columns.
    """
    lat = _first_alias(df, _LAT_ALIASES) or _first_substring(df, _LAT_SUBSTRINGS)
    lon = _first_alias(df, _LON_ALIASES) or _first_substring(
        df, _LON_SUBSTRINGS, exclude=_LON_EXCLUDE_SUBSTRINGS,
    )
    return lat, lon


def canonicalize_lat_lon(df: pd.DataFrame) -> pd.DataFrame:
    """Return a ``df`` copy where Lat/Lon are renamed to the canonical
    names ``Lat`` / ``Lon`` so downstream Phase 2 panels (drift /
    sensor_overview / sst_panels) can look them up without needing
    their own alias tables.

    Also handles the FY25 compound-column edge case: when a single
    ``"Approx Lat/Lng"``-style column resolves to *both* lat and lon,
    its string values are parsed into two numeric columns.

    Idempotent — if the canonical names already exist and no compound
    split is needed, ``df`` is returned untouched.
    """
    if df is None or df.empty:
        return df
    lat, lon = resolve_lat_lon_columns(df)

    # Compound-column case: lat/lon resolvers both landed on the same
    # header with comma-separated values. Parse it into two columns.
    if lat is not None and lat == lon:
        parsed = _split_compound_latlon_series(df[lat])
        if parsed is not None:
            out = df.copy()
            out["Lat"] = parsed[0]
            out["Lon"] = parsed[1]
            return out
        # Could not parse — fall through and return df unchanged so
        # the caller can surface a friendly error.
        return df

    rename: dict[str, str] = {}
    if lat and lat != "Lat" and "Lat" not in df.columns:
        rename[lat] = "Lat"
    if lon and lon != "Lon" and "Lon" not in df.columns:
        rename[lon] = "Lon"
    if not rename:
        return df
    return df.rename(columns=rename)


def find_time_col(df: pd.DataFrame) -> str | None:
    """Return the first column that looks like a timestamp, or None.

    The matched column is coerced in-place with ``pd.to_datetime`` so the
    caller can immediately filter on it.
    """
    if df is None or df.empty:
        return None
    for c in df.columns:
        cl = c.lower()
        if any(kw in cl for kw in TIME_KEYWORDS):
            df[c] = pd.to_datetime(df[c], errors="coerce", utc=False)
            return c
    return None


def apply_device_time_filter(
    df: pd.DataFrame,
    selected_devices: Iterable[str],
    dev_col: str,
    time_col: str | None,
    start_dt: datetime | None,
    end_dt: datetime | None,
) -> pd.DataFrame:
    """Pure filter helper — no Streamlit calls, safe for unit tests."""
    if df is None or df.empty:
        return df
    out = df
    if dev_col in out.columns:
        out = out[out[dev_col].isin(list(selected_devices))]
    if time_col and time_col in out.columns and start_dt is not None and end_dt is not None:
        ts = pd.to_datetime(out[time_col], errors="coerce")
        mask = (ts >= pd.Timestamp(start_dt)) & (ts <= pd.Timestamp(end_dt)) | ts.isna()
        out = out[mask]
    return out.copy()


def render_device_time_filter(
    df: pd.DataFrame,
    key_prefix: str,
    *,
    show_refresh: bool = True,
) -> tuple[pd.DataFrame, list[str], str | None, str]:
    """Render the shared Phase 2 toolbar and return the filtered DataFrame.

    Parameters
    ----------
    df:
        The full DataFrame from ``get_all_data()`` (or equivalent).
    key_prefix:
        Unique per-page prefix for ``st.session_state`` keys. Use e.g.
        ``"p7"``, ``"p8"``, ``"p9"``, ``"p10"``.
    show_refresh:
        If True, renders a "Refresh Data" button that clears Streamlit's
        data cache and reruns.

    Returns
    -------
    (filtered_df, selected_devices, time_col, dev_col)
    """
    from utils.sheets_client import get_device_column, get_device_ids

    if show_refresh:
        if st.button("Refresh Data", key=f"{key_prefix}_refresh"):
            st.cache_data.clear()
            st.rerun()

    if df is None or df.empty:
        st.info("No data available yet.")
        return pd.DataFrame(), [], None, "Device Tab"

    dev_col = get_device_column(df) or "Device Tab"
    device_ids = get_device_ids(df)
    if not device_ids and "Device Tab" in df.columns:
        device_ids = sorted(df["Device Tab"].dropna().unique().tolist())
        dev_col = "Device Tab"
    if not device_ids:
        st.info("No devices found in the data.")
        return pd.DataFrame(), [], None, dev_col

    selected_devices = st.multiselect(
        "Select Devices",
        device_ids,
        default=device_ids,
        key=f"{key_prefix}_devices",
    )
    if not selected_devices:
        st.info("Select at least one device.")
        return pd.DataFrame(), [], None, dev_col

    scoped = df[df[dev_col].isin(selected_devices)].copy()
    if scoped.empty:
        st.info("No data for the selected devices.")
        return scoped, selected_devices, None, dev_col

    time_col = find_time_col(scoped)
    start_dt: datetime | None = None
    end_dt: datetime | None = None

    if time_col:
        valid_ts = scoped[time_col].dropna()
        if not valid_ts.empty:
            data_min = valid_ts.min()
            data_max = valid_ts.max()

            # Reset date inputs when device selection changes, so the
            # picker always reflects the new data window.
            sel_key = f"{key_prefix}_sel_key"
            cur_sel = str(sorted(selected_devices))
            if st.session_state.get(sel_key) != cur_sel:
                st.session_state[sel_key] = cur_sel
                st.session_state[f"{key_prefix}_start"] = data_min.date()
                st.session_state[f"{key_prefix}_start_t"] = time(0, 0)
                st.session_state[f"{key_prefix}_end"] = data_max.date()
                st.session_state[f"{key_prefix}_end_t"] = time(23, 59)

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                start = st.date_input("Start", key=f"{key_prefix}_start")
            with c2:
                start_t = st.time_input("Start time", key=f"{key_prefix}_start_t")
            with c3:
                end = st.date_input("End", key=f"{key_prefix}_end")
            with c4:
                end_t = st.time_input("End time", key=f"{key_prefix}_end_t")
            start_dt = datetime.combine(start, start_t)
            end_dt = datetime.combine(end, end_t)

    filtered = apply_device_time_filter(
        scoped, selected_devices, dev_col, time_col, start_dt, end_dt,
    )
    # Canonicalize lat/lon so downstream panels (drift, sst, sensor
    # overview) can assume the column names "Lat" / "Lon" regardless
    # of the sheet's original header style.
    filtered = canonicalize_lat_lon(filtered)

    if filtered.empty:
        st.warning("No data in the selected range. Adjust the filter.")

    return filtered, selected_devices, time_col, dev_col
