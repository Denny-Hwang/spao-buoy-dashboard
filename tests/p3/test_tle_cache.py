"""Phase 3 TLE I/O — empty-skip caching + force-refresh helper.

These tests cover the cache-layer refactor that prevents
``UnserializableReturnValueError``: the cache now stores plain
record dicts (picklable) and the SGP4 ``Sat`` objects are
reconstructed on each read.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

sys.path.insert(0, str(REPO_ROOT / "tests"))
_skel = importlib.import_module("test_p2_skeleton")
_skel._install_stub_modules()  # type: ignore[attr-defined]

from utils.p3 import tle_io  # noqa: E402


_ONE_TLE_RECORD = {
    "name": "IRIDIUM 106",
    "line1": "1 41917U 17003A   26090.16404766  .00000226  00000+0  73702-4 0  9996",
    "line2": "2 41917  86.3940 121.1858 0002524 100.6731 259.4749 14.34217814482022",
}


def test_cached_function_returns_picklable_dicts(monkeypatch):
    """The cached function must return plain dicts, not ``Sat`` objects.

    Streamlit 1.40+ rejects any cache value it can't round-trip through
    pickle/Arrow; the SGP4 ``Satrec`` inside ``Sat`` breaks that. By
    caching the raw records we keep the 1 h TTL benefit without the
    serialisation hazard.
    """
    import pickle

    monkeypatch.setattr(tle_io, "_read_tab", lambda *_a, **_k: None)
    monkeypatch.setattr(
        tle_io,
        "_df_to_records",
        lambda _df: [_ONE_TLE_RECORD],
    )
    tle_io.force_refresh_tle()

    records = tle_io._load_iridium_records_cached()
    assert records == [_ONE_TLE_RECORD]
    # Contract: pickleable. This is what Streamlit's cache wants.
    pickled = pickle.dumps(records)
    restored = pickle.loads(pickled)
    assert restored == [_ONE_TLE_RECORD]


def test_load_iridium_tle_returns_parsed_sats(monkeypatch):
    """The public helper reconstructs ``Sat`` objects on every call."""
    monkeypatch.setattr(tle_io, "_read_tab", lambda *_a, **_k: None)
    monkeypatch.setattr(
        tle_io,
        "_df_to_records",
        lambda _df: [_ONE_TLE_RECORD],
    )
    tle_io.force_refresh_tle()

    sats = tle_io.load_iridium_tle()
    assert len(sats) == 1
    assert sats[0].name == "IRIDIUM 106"
    # The Satrec is NOT part of the cache payload — only re-created here.
    assert sats[0].sr is not None


def test_load_iridium_tle_skips_caching_empty(monkeypatch):
    """Empty Sheet reads must NOT lock the page into 1 h of empty results."""
    calls = {"n": 0}

    def fake_records(_df):
        calls["n"] += 1
        return [] if calls["n"] == 1 else [_ONE_TLE_RECORD]

    monkeypatch.setattr(tle_io, "_read_tab", lambda *_a, **_k: None)
    monkeypatch.setattr(tle_io, "_df_to_records", fake_records)
    tle_io.force_refresh_tle()

    first = tle_io.load_iridium_tle()
    second = tle_io.load_iridium_tle()
    assert first == []
    assert len(second) == 1
    assert calls["n"] == 2


def test_force_refresh_tle_clears_both(monkeypatch):
    cleared = []

    def make_clearable(label):
        def f(_sheet_id=None):
            return []
        f.clear = lambda: cleared.append(label)  # type: ignore[attr-defined]
        return f

    monkeypatch.setattr(tle_io, "_load_iridium_records_cached",
                        make_clearable("iri"))
    monkeypatch.setattr(tle_io, "_load_gps_records_cached",
                        make_clearable("gps"))
    tle_io.force_refresh_tle()
    assert "iri" in cleared
    assert "gps" in cleared


def test_force_refresh_tle_safe_when_clear_missing(monkeypatch):
    def f(_sheet_id=None):
        return []
    monkeypatch.setattr(tle_io, "_load_iridium_records_cached", f)
    monkeypatch.setattr(tle_io, "_load_gps_records_cached", f)
    tle_io.force_refresh_tle()  # no AttributeError
