"""Tests for utils.sheets_client.normalize_ts_to_utc — the fix that
corrects the ~12 h phase offset between buoy hull temperature and
ERA5 2 m air temperature.

Root cause: the Apps Script writes an ISO UTC string, but Google
Sheets reformats Date values using the spreadsheet's Display Time
Zone so gspread reads back naive local-time strings. The fix
auto-detects each row's IANA zone from its own (lat, lon) GPS fix,
and returns naive UTC values that Phase 1 consumers can keep using
unchanged."""

from __future__ import annotations

import importlib.util

import pandas as pd
import pytest

from tests.test_p2_skeleton import _install_stub_modules
_install_stub_modules()

from utils.sheets_client import normalize_ts_to_utc, tz_for_gps  # noqa: E402


_HAS_TZFINDER = importlib.util.find_spec("timezonefinder") is not None


def test_normalize_naive_values_default_utc_no_shift(monkeypatch):
    """When neither override nor GPS is given, naive values stay as
    UTC — mirrors legacy behavior so existing deployments don't
    silently shift on upgrade."""
    monkeypatch.delenv("SHEETS_DISPLAY_TZ", raising=False)
    s = normalize_ts_to_utc(pd.Series(["2026-04-12 04:00:00"]))
    assert s.dt.tz is None
    assert s.iloc[0] == pd.Timestamp("2026-04-12 04:00:00")


def test_normalize_uses_env_override_when_set(monkeypatch):
    """Operator-set override wins over GPS auto-detection.

    Covers the case where the spreadsheet's Display Time Zone is
    fixed to the operator's zone even though the buoy GPS is
    elsewhere — in that scenario GPS lookup would be wrong."""
    monkeypatch.setenv("SHEETS_DISPLAY_TZ", "Asia/Seoul")
    s = normalize_ts_to_utc(pd.Series(["2026-04-12 13:00:00"]))
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


# ---------- GPS-based per-row TZ -------------------------------------

@pytest.mark.skipif(not _HAS_TZFINDER, reason="timezonefinder not installed")
def test_tz_for_gps_lookup_known_locations():
    """Sanity check a handful of known points resolve to the expected
    IANA zones. Mid-ocean points correctly fall back to the nautical
    ``Etc/GMT±N`` family; continental / coastal points resolve to the
    civil zone."""
    assert tz_for_gps(37.5, 127.0) == "Asia/Seoul"
    assert tz_for_gps(46.3, -119.3) == "America/Los_Angeles"
    # Anchorage city → civil Alaska zone (vs mid-Bering-Sea which
    # would land on Etc/GMT+11).
    assert tz_for_gps(61.2, -149.9) == "America/Anchorage"


def test_tz_for_gps_invalid_returns_none():
    assert tz_for_gps(float("nan"), 0.0) is None
    assert tz_for_gps(0.0, 0.0) is None  # missing-GPS sentinel
    assert tz_for_gps("not-a-number", 0.0) is None


@pytest.mark.skipif(not _HAS_TZFINDER, reason="timezonefinder not installed")
def test_normalize_gps_based_per_row_tz(monkeypatch):
    """When no env override is set, rows are localized using each row's
    own (lat, lon): a buoy in Korea localizes with Asia/Seoul and a
    row in Washington localizes with America/Los_Angeles, in the same
    call."""
    monkeypatch.delenv("SHEETS_DISPLAY_TZ", raising=False)
    # Row 0: Seoul, naive "13:00" = 13:00 KST = 04:00 UTC.
    # Row 1: Richland WA (PDT in April = UTC-7), "06:00" = 13:00 UTC.
    df = pd.DataFrame({
        "Timestamp": ["2026-04-12 13:00:00", "2026-04-12 06:00:00"],
        "Latitude": [37.5, 46.3],
        "Longitude": [127.0, -119.3],
    })
    s = normalize_ts_to_utc(
        df["Timestamp"], lat=df["Latitude"], lon=df["Longitude"],
    )
    assert s.iloc[0] == pd.Timestamp("2026-04-12 04:00:00")
    assert s.iloc[1] == pd.Timestamp("2026-04-12 13:00:00")


@pytest.mark.skipif(not _HAS_TZFINDER, reason="timezonefinder not installed")
def test_normalize_env_override_beats_gps(monkeypatch):
    """If the operator sets SHEETS_DISPLAY_TZ explicitly, the fixed
    zone must win even when GPS data is available."""
    monkeypatch.setenv("SHEETS_DISPLAY_TZ", "UTC")
    df = pd.DataFrame({
        "Timestamp": ["2026-04-12 13:00:00"],
        "Latitude": [37.5],
        "Longitude": [127.0],
    })
    s = normalize_ts_to_utc(
        df["Timestamp"], lat=df["Latitude"], lon=df["Longitude"],
    )
    # Env says UTC → treated as 13:00 UTC, not 04:00 UTC.
    assert s.iloc[0] == pd.Timestamp("2026-04-12 13:00:00")
