"""Phase 3 TZ formatter sanity checks (no Streamlit needed)."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from utils.p3 import tz as p3_tz


def test_to_utc_handles_naive_and_aware():
    naive = datetime(2026, 4, 1, 12, 0)
    aware = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
    assert p3_tz.to_utc(naive).tzinfo is not None
    assert p3_tz.to_utc(aware).tzinfo is not None
    assert p3_tz.to_utc(None) is None


def test_format_dual_contains_both_zones():
    dt = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
    s = p3_tz.format_dual(dt, tz_name="America/Los_Angeles")
    assert "UTC" in s
    # Pacific is UTC-7 during PDT → April → 05:00 PT.
    assert "America/Los_Angeles" in s
    assert "05:00" in s


def test_format_dual_utc_only():
    dt = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
    s = p3_tz.format_dual(dt, tz_name="UTC")
    assert s.endswith("UTC")
    assert "(" not in s  # no secondary bracketed zone


def test_add_local_columns():
    df = pd.DataFrame({
        "Timestamp": pd.to_datetime(
            ["2026-04-01T12:00:00Z", "2026-04-01T13:00:00Z"], utc=True
        ),
    })
    out = p3_tz.add_local_columns(df, ["Timestamp"], tz_name="America/Los_Angeles")
    assert "Timestamp_local" in out.columns
    assert "Timestamp_tz" in out.columns
    # Local column should be tz-aware now.
    assert str(out["Timestamp_local"].dt.tz) == "America/Los_Angeles"


def test_default_display_tz_is_pacific():
    # With no streamlit session state, default is Pacific (PT) per spec.
    assert p3_tz.get_display_tz() == "America/Los_Angeles"
