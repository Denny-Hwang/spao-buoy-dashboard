from __future__ import annotations

import math
import os

import pandas as pd
import pytest

from scripts.backfill_enrichment import (
    _COMPOUND_LAT,
    _COMPOUND_LON,
    _coerce_ts,
    _group_rows,
    _split_compound_latlon,
    filter_by_window,
    locate_geotemporal_columns,
)


def test_locate_geotemporal_columns_accepts_degree_variants():
    df = pd.DataFrame(
        {
            "Date Time (UTC)": ["2026-04-15 00:00:00"],
            "Latitude (deg)": [46.36],
            "Longitude (deg)": [-119.27],
        }
    )
    ts, lat, lon = locate_geotemporal_columns(df)
    assert ts == "Date Time (UTC)"
    assert lat == "Latitude (deg)"
    assert lon == "Longitude (deg)"


def test_group_rows_skips_zero_zero_gps_fix():
    df = pd.DataFrame(
        {
            "Receive Time": ["2026-04-15 00:00:00", "2026-04-15 01:00:00"],
            "Lat (°)": [0.0, 46.36],
            "Lon (°)": [0.0, -119.27],
        }
    )
    groups = _group_rows(
        df=df,
        rows=df.index,
        ts_col="Receive Time",
        lat_col="Lat (°)",
        lon_col="Lon (°)",
        bucket="H",
    )
    # First row should be skipped because (0, 0) is an invalid GPS fix.
    assert sum(len(v) for v in groups.values()) == 1


def test_locate_geotemporal_columns_splits_fy25_compound_approx_latlng():
    """FY25 tabs use a single 'Approx Lat/Lng' column. locate_geotemporal
    must auto-split it into synthetic Lat/Lon columns so the enrichment
    rows actually make it through _group_rows."""
    df = pd.DataFrame(
        {
            "Date Time (UTC)": [
                "2025-09-10 02:23:00",
                "2025-09-10 03:10:00",
                "2025-09-10 04:10:00",
            ],
            "Device": ["RockBLOCK 220835"] * 3,
            "Approx Lat/Lng": [
                "58.4494,-174.29623333333333",
                "58.2881,-169.98806666666667",
                "58.34238333333333,-170.04346666666666",
            ],
            "Payload": ["042304ed", "01dd0434", "01c40472"],
        }
    )
    ts, lat, lon = locate_geotemporal_columns(df)
    assert ts == "Date Time (UTC)"
    assert lat == _COMPOUND_LAT
    assert lon == _COMPOUND_LON
    # Synthetic columns exist and were parsed correctly.
    assert _COMPOUND_LAT in df.columns
    assert _COMPOUND_LON in df.columns
    assert df[_COMPOUND_LAT].iloc[0] == 58.4494
    assert df[_COMPOUND_LON].iloc[0] == -174.29623333333333

    # And _group_rows must now yield one bucket per row (previously zero).
    groups = _group_rows(
        df=df,
        rows=df.index,
        ts_col=ts,
        lat_col=lat,
        lon_col=lon,
        bucket="H",
    )
    assert sum(len(v) for v in groups.values()) == 3


def test_split_compound_latlon_handles_empty_and_bad_rows():
    df = pd.DataFrame(
        {
            "Approx Lat/Lng": [
                "58.5,-174.0",
                "",
                None,
                "not-a-pair",
                "59.0,-170.0,extra",
                "59.5,-171.0",
            ],
        }
    )
    result = _split_compound_latlon(df)
    assert result == (_COMPOUND_LAT, _COMPOUND_LON)
    lats = df[_COMPOUND_LAT].tolist()
    lons = df[_COMPOUND_LON].tolist()
    assert lats[0] == 58.5
    assert lats[-1] == 59.5
    for bad in (1, 2, 3, 4):
        assert math.isnan(lats[bad])
        assert math.isnan(lons[bad])


def test_split_compound_latlon_returns_none_for_plain_columns():
    """A regular numeric Latitude column must not be treated as compound."""
    df = pd.DataFrame(
        {
            "Latitude": [58.5, 58.6],
            "Longitude": [-174.0, -174.1],
        }
    )
    assert _split_compound_latlon(df) is None
    assert _COMPOUND_LAT not in df.columns


def test_enrich_open_meteo_marine_writes_sst_fallback(monkeypatch):
    """Open-Meteo Marine fetches sea_surface_temperature in the same
    hourly call as the wave variables; backfill must persist it into
    SAT_SST_ERA5_cC so Page 8 still has a reference SST even when
    NOAA OISST / MUR / OSTIA haven't run yet."""
    from scripts import backfill_enrichment as bf

    # Pin Timestamp interpretation to UTC so this test's fake hourly
    # frame (keyed to 12:00 UTC) aligns with the row's bucketed hour
    # regardless of what zone GPS-based auto-detection would pick for
    # the Bering-Sea point.
    monkeypatch.setenv("SHEETS_DISPLAY_TZ", "UTC")

    # Build a tiny df with 1 row of geo+time; enrichment columns
    # initialized via ensure_enrichment_columns.
    df = pd.DataFrame(
        {
            "Timestamp": ["2026-04-15 12:00:00"],
            "Lat": [58.35],
            "Lon": [-169.98],
        }
    )
    df = bf.ensure_enrichment_columns(df)

    # Stub fetch_marine_point with a deterministic payload.
    def _fake_marine(lat, lon, start_dt, end_dt):
        idx = pd.to_datetime(
            ["2026-04-15 12:00:00"], utc=True,
        )
        return pd.DataFrame(
            {
                "wave_height": [1.25],
                "wave_period": [7.8],
                "wave_direction": [220.0],
                "wind_wave_height": [0.6],
                "wind_wave_period": [4.5],
                "swell_wave_height": [1.05],
                "swell_wave_period": [11.0],
                "sea_surface_temperature": [9.87],
            },
            index=idx,
        )

    import utils.p2.sources.open_meteo as om
    monkeypatch.setattr(om, "fetch_marine_point", _fake_marine)

    filled = bf.enrich_open_meteo_marine(
        df, df.index, "Timestamp", "Lat", "Lon",
    )
    assert filled == 1

    # SAT_SST_ERA5_cC is an int16 scaled by 100 → 9.87 °C -> 987.
    from utils.p2.schema import ENRICHED_COLUMNS
    scale = ENRICHED_COLUMNS["SAT_SST_ERA5_cC"][1]
    assert scale == 100.0
    raw = df.at[0, "SAT_SST_ERA5_cC"]
    assert int(raw) == int(round(9.87 * scale))
    # Wave columns still populated.
    assert int(df.at[0, "WAVE_H_cm"]) == int(round(1.25 * 100.0))


# ---------- Timezone normalization ---------------------------------

def test_coerce_ts_naive_value_with_default_tz_treated_as_utc(monkeypatch):
    """Legacy behavior: when SHEETS_DISPLAY_TZ is unset / UTC, naive
    timestamp strings are interpreted as UTC (no shift)."""
    monkeypatch.delenv("SHEETS_DISPLAY_TZ", raising=False)
    ts = _coerce_ts("2026-04-12 04:00:00")
    assert ts == pd.Timestamp("2026-04-12 04:00:00", tz="UTC")


def test_coerce_ts_naive_value_with_seoul_tz_converted_to_utc(monkeypatch):
    """When the sheet is in KST, a naive '13:00' value represents 04:00
    UTC on the same date. This is exactly the fix for the ~12 h phase
    offset between hull temp and ERA5 air temp."""
    monkeypatch.setenv("SHEETS_DISPLAY_TZ", "Asia/Seoul")
    ts = _coerce_ts("2026-04-12 13:00:00")
    assert ts == pd.Timestamp("2026-04-12 04:00:00", tz="UTC")


def test_coerce_ts_tz_aware_input_ignores_env_tz(monkeypatch):
    """ISO strings with explicit offsets are respected; the env var
    is not re-applied on top of them."""
    monkeypatch.setenv("SHEETS_DISPLAY_TZ", "Asia/Seoul")
    ts = _coerce_ts("2026-04-12T04:00:00.000Z")
    assert ts == pd.Timestamp("2026-04-12 04:00:00", tz="UTC")


def test_coerce_ts_explicit_src_tz_overrides_env(monkeypatch):
    monkeypatch.setenv("SHEETS_DISPLAY_TZ", "UTC")
    ts = _coerce_ts("2026-04-12 13:00:00", src_tz="Asia/Seoul")
    assert ts == pd.Timestamp("2026-04-12 04:00:00", tz="UTC")


def test_filter_by_window_respects_sheet_tz(monkeypatch):
    """A naive '2026-04-12 13:00' row with SHEETS_DISPLAY_TZ=Asia/Seoul
    represents 04:00 UTC on the same date, so it lands in that UTC
    day's window. Without the fix the same value would have been
    treated as 13:00 UTC and still been inside the day — but the test
    pins the semantics against which later behavior is compared."""
    monkeypatch.setenv("SHEETS_DISPLAY_TZ", "Asia/Seoul")
    from datetime import date
    df = pd.DataFrame({"Timestamp": ["2026-04-12 13:00:00"]})
    idx = filter_by_window(df, "Timestamp", date(2026, 4, 12), date(2026, 4, 12))
    assert list(idx) == [0]


# ---------- Chronological-order preservation under outlier GPS -----

def test_group_rows_preserves_chronology_under_outlier_gps(monkeypatch):
    """Regression guard: a single outlier GPS row must not get its
    hour-bucket shifted relative to its neighbours. _group_rows is
    column-uniform on TZ (via _coerce_ts reading SHEETS_DISPLAY_TZ),
    so rows 112/113/114 stay in time order even if row 113's GPS
    lands in a different IANA zone."""
    monkeypatch.setenv("SHEETS_DISPLAY_TZ", "UTC")
    df = pd.DataFrame({
        "Timestamp": [
            "2026-04-11 00:00:00",
            "2026-04-11 00:30:00",
            "2026-04-11 01:00:00",
        ],
        # Middle row has a totally different GPS; under the reverted
        # per-row path this would have shifted row 1's bucket.
        "Lat": [58.3, 37.5, 58.3],
        "Lon": [-170.0, 127.0, -170.0],
    })
    groups = _group_rows(df, df.index, "Timestamp", "Lat", "Lon", bucket="H")
    # Buckets are keyed by (snapped_lat, snapped_lon, hour). The point
    # of the test is that the HOUR component for each row matches the
    # row's UTC hour independent of its GPS cell — i.e. row 1's hour
    # is still 00 UTC (matching its sheet timestamp), not shifted by
    # the Seoul zone offset.
    hour_by_row: dict[int, int] = {}
    for (_lat, _lon, hour), idxs in groups.items():
        for i in idxs:
            hour_by_row[i] = int(hour.hour)
    assert hour_by_row == {0: 0, 1: 0, 2: 1}
