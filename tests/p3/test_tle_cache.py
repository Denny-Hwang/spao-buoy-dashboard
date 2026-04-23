"""Phase 3 TLE I/O — empty-skip caching + force-refresh helper."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Reuse the Phase 2 stub harness so streamlit / gspread import cleanly.
sys.path.insert(0, str(REPO_ROOT / "tests"))
_skel = importlib.import_module("test_p2_skeleton")
_skel._install_stub_modules()  # type: ignore[attr-defined]

from utils.p3 import tle_io  # noqa: E402
from utils.p3.sgp4_engine import parse_tle  # noqa: E402


_ONE_TLE = [{
    "name": "IRIDIUM 106",
    "line1": "1 41917U 17003A   26090.16404766  .00000226  00000+0  73702-4 0  9996",
    "line2": "2 41917  86.3940 121.1858 0002524 100.6731 259.4749 14.34217814482022",
}]


def test_load_iridium_tle_skips_caching_empty(monkeypatch):
    """An empty Sheet read must NOT lock the page into 1 h of empty results."""
    calls = {"n": 0}

    def fake_df_to_sats(_df):
        calls["n"] += 1
        # First call: empty; second call: populated.
        if calls["n"] == 1:
            return []
        return parse_tle(_ONE_TLE)

    # Patch BOTH the wrapped reader and the deeper helper so the cache
    # decorator sees the new return value on retry.
    monkeypatch.setattr(tle_io, "_df_to_sats", fake_df_to_sats)
    monkeypatch.setattr(tle_io, "_read_tab", lambda *_a, **_k: None)
    tle_io.force_refresh_tle()

    first = tle_io.load_iridium_tle()
    second = tle_io.load_iridium_tle()
    assert first == []
    assert len(second) == 1, "after sheet populated, retry must succeed"
    assert calls["n"] == 2, "empty result must not be cached"


def test_force_refresh_tle_clears_both(monkeypatch):
    cleared = []

    def make_clearable(label):
        def f(_sheet_id=None):
            return []
        f.clear = lambda: cleared.append(label)  # type: ignore[attr-defined]
        return f

    monkeypatch.setattr(tle_io, "_load_iridium_tle_cached",
                        make_clearable("iri"))
    monkeypatch.setattr(tle_io, "_load_gps_tle_cached",
                        make_clearable("gps"))
    tle_io.force_refresh_tle()
    assert "iri" in cleared
    assert "gps" in cleared


def test_force_refresh_tle_safe_when_clear_missing(monkeypatch):
    # Calling clear on a function without one must not raise.
    def f(_sheet_id=None):
        return []
    monkeypatch.setattr(tle_io, "_load_iridium_tle_cached", f)
    monkeypatch.setattr(tle_io, "_load_gps_tle_cached", f)
    tle_io.force_refresh_tle()  # no AttributeError
