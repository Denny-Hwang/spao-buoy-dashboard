"""Tests for utils.sheets_client.normalize_ts_to_utc — the fix that
corrects the ~12 h phase offset between buoy hull temperature and
ERA5 2 m air temperature when the spreadsheet's Display Time Zone
isn't UTC (Google Sheets reformats Date values using the sheet's
local zone, so gspread reads back naive local strings)."""

from __future__ import annotations

import pandas as pd
import pytest

from tests.test_p2_skeleton import _install_stub_modules
_install_stub_modules()

from utils.sheets_client import normalize_ts_to_utc  # noqa: E402


def test_normalize_naive_values_default_utc_no_shift(monkeypatch):
    """When SHEETS_DISPLAY_TZ is unset, naive values are treated as
    UTC — mirrors legacy behavior so existing deployments don't
    silently shift on upgrade."""
    monkeypatch.delenv("SHEETS_DISPLAY_TZ", raising=False)
    s = normalize_ts_to_utc(pd.Series(["2026-04-12 04:00:00"]))
    # Naive result, values unchanged.
    assert s.dt.tz is None
    assert s.iloc[0] == pd.Timestamp("2026-04-12 04:00:00")


def test_normalize_naive_values_seoul_tz_converts_to_utc(monkeypatch):
    """KST 13:00 → UTC 04:00. This is the core fix."""
    monkeypatch.setenv("SHEETS_DISPLAY_TZ", "Asia/Seoul")
    s = normalize_ts_to_utc(pd.Series(["2026-04-12 13:00:00"]))
    assert s.dt.tz is None  # tz-naive (but values are now UTC)
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
