"""Tests for utils.sheets_client.normalize_ts_to_utc — the fix that
corrects the ~12 h phase offset between buoy hull temperature and
ERA5 2 m air temperature.

Root cause: the Apps Script writes an ISO UTC string but Google
Sheets reformats Date values using the spreadsheet's Display Time
Zone, so gspread reads back naive local-time strings. The fix
applies a sheet-wide ``SHEETS_DISPLAY_TZ`` (Streamlit secret / env
var) and returns naive UTC values that Phase 1 consumers can keep
using unchanged.

Note: an earlier iteration attempted per-row GPS-based TZ lookup
but had to be reverted — an outlier GPS fix would then localize
that one row with a different offset than its neighbours, visibly
re-ordering the Data Explorer. A sheet is always stored in a single
zone, so the TZ applied on read must be column-uniform."""

from __future__ import annotations

import importlib.util

import pandas as pd
import pytest

from tests.test_p2_skeleton import _install_stub_modules
_install_stub_modules()

from utils.sheets_client import normalize_ts_to_utc, tz_for_gps  # noqa: E402


_HAS_TZFINDER = importlib.util.find_spec("timezonefinder") is not None


def test_normalize_naive_values_default_utc_no_shift(monkeypatch):
    """With SHEETS_DISPLAY_TZ unset, naive values stay as UTC —
    preserves the legacy behavior for sheets already in UTC."""
    monkeypatch.delenv("SHEETS_DISPLAY_TZ", raising=False)
    s = normalize_ts_to_utc(pd.Series(["2026-04-12 04:00:00"]))
    assert s.dt.tz is None
    assert s.iloc[0] == pd.Timestamp("2026-04-12 04:00:00")


def test_normalize_naive_values_with_sheet_tz_env(monkeypatch):
    """KST 13:00 → UTC 04:00 when SHEETS_DISPLAY_TZ=Asia/Seoul."""
    monkeypatch.setenv("SHEETS_DISPLAY_TZ", "Asia/Seoul")
    s = normalize_ts_to_utc(pd.Series(["2026-04-12 13:00:00"]))
    assert s.dt.tz is None
    assert s.iloc[0] == pd.Timestamp("2026-04-12 04:00:00")


def test_normalize_tz_aware_input_returns_naive_utc(monkeypatch):
    """Explicit-offset strings are honored; env var isn't re-applied."""
    monkeypatch.setenv("SHEETS_DISPLAY_TZ", "Asia/Seoul")
    s = normalize_ts_to_utc(pd.Series(["2026-04-12T04:00:00.000Z"]))
    assert s.dt.tz is None
    assert s.iloc[0] == pd.Timestamp("2026-04-12 04:00:00")


def test_normalize_mixed_values_preserves_nat_on_garbage(monkeypatch):
    monkeypatch.delenv("SHEETS_DISPLAY_TZ", raising=False)
    s = normalize_ts_to_utc(pd.Series(["2026-04-12 04:00:00", "not-a-date"]))
    assert pd.isna(s.iloc[1])
    assert s.iloc[0] == pd.Timestamp("2026-04-12 04:00:00")


def test_normalize_explicit_src_tz_param_overrides_env(monkeypatch):
    monkeypatch.setenv("SHEETS_DISPLAY_TZ", "UTC")
    s = normalize_ts_to_utc(
        pd.Series(["2026-04-12 13:00:00"]),
        src_tz="Asia/Seoul",
    )
    assert s.iloc[0] == pd.Timestamp("2026-04-12 04:00:00")


def test_normalize_lat_lon_kwargs_are_ignored_for_ordering(monkeypatch):
    """Regression guard: passing lat/lon must NOT cause per-row TZ
    lookup. An outlier GPS row must not be shifted relative to its
    sheet-ordered neighbours — otherwise the Data Explorer shows rows
    out of chronological order."""
    monkeypatch.delenv("SHEETS_DISPLAY_TZ", raising=False)
    # Three rows in increasing time, with the MIDDLE row at a wildly
    # different GPS. Under the reverted per-row GPS path this row
    # would have been localized differently from its neighbours,
    # pushing it out of chronological order.
    df = pd.DataFrame({
        "Timestamp": [
            "2026-04-11 00:00:00",
            "2026-04-11 00:30:00",
            "2026-04-11 01:00:00",
        ],
        "Lat": [58.3, 37.5, 58.3],
        "Lon": [-170.0, 127.0, -170.0],
    })
    s = normalize_ts_to_utc(df["Timestamp"], lat=df["Lat"], lon=df["Lon"])
    assert list(s) == [
        pd.Timestamp("2026-04-11 00:00:00"),
        pd.Timestamp("2026-04-11 00:30:00"),
        pd.Timestamp("2026-04-11 01:00:00"),
    ]
    # Monotone non-decreasing → chronological order preserved.
    assert list(s.diff().dropna()) == [
        pd.Timedelta(minutes=30), pd.Timedelta(minutes=30),
    ]


# ---------- tz_for_gps helper (still exported for other callers) ----

@pytest.mark.skipif(not _HAS_TZFINDER, reason="timezonefinder not installed")
def test_tz_for_gps_lookup_known_locations():
    """Sanity check a handful of known points resolve to the expected
    IANA zones. Mid-ocean points correctly fall back to the nautical
    ``Etc/GMT±N`` family; continental / coastal points resolve to the
    civil zone."""
    assert tz_for_gps(37.5, 127.0) == "Asia/Seoul"
    assert tz_for_gps(46.3, -119.3) == "America/Los_Angeles"
    assert tz_for_gps(61.2, -149.9) == "America/Anchorage"


def test_tz_for_gps_invalid_returns_none():
    assert tz_for_gps(float("nan"), 0.0) is None
    assert tz_for_gps(0.0, 0.0) is None
    assert tz_for_gps("not-a-number", 0.0) is None
