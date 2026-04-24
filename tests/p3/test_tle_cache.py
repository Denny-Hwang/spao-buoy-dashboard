"""Phase 3 TLE I/O tests — cache payload is a picklable string.

Streamlit 1.40+ on Python 3.14 is strict about what it will cache.
Earlier attempts that returned ``list[Sat]`` and then ``list[dict]``
both hit ``UnserializableReturnValueError``. This module now caches
the full 3-line TLE text (plain ``str``), which is trivially
picklable on every version of Python + Streamlit we care about.
"""

from __future__ import annotations

import importlib
import pickle
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

sys.path.insert(0, str(REPO_ROOT / "tests"))
_skel = importlib.import_module("test_p2_skeleton")
_skel._install_stub_modules()  # type: ignore[attr-defined]

import pandas as pd  # noqa: E402

from utils.p3 import tle_io  # noqa: E402


_TLE_DF = pd.DataFrame([
    {"satname": "IRIDIUM 106",
     "line1": "1 41917U 17003A   26090.16404766  .00000226  00000+0  73702-4 0  9996",
     "line2": "2 41917  86.3940 121.1858 0002524 100.6731 259.4749 14.34217814482022"},
])


def test_cache_payload_is_picklable(monkeypatch):
    """Streamlit's strict serializer must accept the cache payload."""
    monkeypatch.setattr(tle_io, "_read_tab", lambda *_a, **_k: _TLE_DF)
    tle_io.force_refresh_tle()

    text = tle_io._load_iridium_text_cached()
    assert isinstance(text, str)
    assert "IRIDIUM 106" in text

    restored = pickle.loads(pickle.dumps(text))
    assert restored == text


def test_load_iridium_tle_returns_parsed_sats(monkeypatch):
    monkeypatch.setattr(tle_io, "_read_tab", lambda *_a, **_k: _TLE_DF)
    tle_io.force_refresh_tle()

    sats = tle_io.load_iridium_tle()
    assert len(sats) == 1
    assert sats[0].name == "IRIDIUM 106"
    assert sats[0].sr is not None


def test_load_iridium_tle_skips_caching_empty(monkeypatch):
    calls = {"n": 0}

    def fake_read_tab(*_a, **_k):
        calls["n"] += 1
        return pd.DataFrame() if calls["n"] == 1 else _TLE_DF

    monkeypatch.setattr(tle_io, "_read_tab", fake_read_tab)
    tle_io.force_refresh_tle()

    first = tle_io.load_iridium_tle()
    second = tle_io.load_iridium_tle()
    assert first == []
    assert len(second) == 1
    assert calls["n"] == 2, "empty TLE reads must NOT be cached"


def test_force_refresh_tle_clears_both(monkeypatch):
    cleared = []

    def make_clearable(label):
        def f(_sheet_id=None):
            return ""
        f.clear = lambda: cleared.append(label)  # type: ignore[attr-defined]
        return f

    monkeypatch.setattr(tle_io, "_load_iridium_text_cached",
                        make_clearable("iri"))
    monkeypatch.setattr(tle_io, "_load_gps_text_cached",
                        make_clearable("gps"))
    tle_io.force_refresh_tle()
    assert "iri" in cleared
    assert "gps" in cleared


def test_force_refresh_tle_safe_when_clear_missing(monkeypatch):
    def f(_sheet_id=None):
        return ""
    monkeypatch.setattr(tle_io, "_load_iridium_text_cached", f)
    monkeypatch.setattr(tle_io, "_load_gps_text_cached", f)
    tle_io.force_refresh_tle()  # no AttributeError
