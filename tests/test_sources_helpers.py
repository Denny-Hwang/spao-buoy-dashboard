"""Coverage-oriented smoke tests for source helper modules."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from utils.p2.sources import cache as cache_mod
from utils.p2.sources import grid as grid_mod


# ── grid.py ────────────────────────────────────────────────────────────
def test_grid_snap_and_time_bucket():
    assert grid_mod.snap(58.37, 0.1) == pytest.approx(58.4, abs=1e-9)
    assert grid_mod.snap(58.31, 0.1) == pytest.approx(58.3, abs=1e-9)

    naive = datetime(2025, 9, 9, 14, 37)
    hour = grid_mod.time_bucket(naive, "H")
    assert hour.hour == 14 and hour.minute == 0
    day = grid_mod.time_bucket(naive, "D")
    assert day.hour == 0

    with pytest.raises(ValueError):
        grid_mod.time_bucket(naive, "X")


def test_grid_key_stable_for_same_inputs():
    k1 = grid_mod.grid_key(58.37, -169.98, "2025-09-09T14:37Z", "oisst", "D")
    k2 = grid_mod.grid_key(58.38, -169.99, "2025-09-09T18:22Z", "oisst", "D")
    assert k1 == k2  # same day, same 0.1° cell


def test_grid_as_utc_and_utcnow():
    ts = grid_mod.as_utc("2025-01-01T12:00")
    assert ts.tz is not None
    ts2 = grid_mod.as_utc(pd.Timestamp("2025-01-01T12:00", tz="UTC"))
    assert ts2.tz is not None
    now = grid_mod.utcnow()
    assert now.tz is not None


# ── cache.py ───────────────────────────────────────────────────────────
@pytest.fixture
def tmp_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SPAO_CACHE_DIR", str(tmp_path))
    # Reset the module's interpretation of the path.
    yield Path(tmp_path)


def test_cache_put_get_roundtrip(tmp_cache_dir):
    key = ("oisst", 58.4, -170.0, "2025-09-09T00:00Z")
    df = pd.DataFrame({"sst": [9.8, 10.1]})
    cache_mod.put(key, df)
    loaded = cache_mod.get(key)
    assert loaded is not None
    assert list(loaded.columns) == ["sst"]
    assert loaded.shape == (2, 1)


def test_cache_get_missing_returns_none(tmp_cache_dir):
    assert cache_mod.get(("oisst", 0.0, 0.0, "never")) is None


def test_cache_put_empty_is_noop(tmp_cache_dir):
    cache_mod.put(("oisst", 1.0, 2.0, "x"), pd.DataFrame())
    assert cache_mod.list_keys() == []


def test_cache_clear_removes_files(tmp_cache_dir):
    cache_mod.put(("a", 1.0, 2.0, "x"), pd.DataFrame({"v": [1]}))
    cache_mod.put(("b", 1.0, 2.0, "y"), pd.DataFrame({"v": [2]}))
    assert len(cache_mod.list_keys()) >= 2
    removed = cache_mod.clear()
    assert removed >= 2
    assert cache_mod.list_keys() == []


def test_cache_memoize_decorator(tmp_cache_dir):
    calls = {"n": 0}

    @cache_mod.memoize("demo")
    def fetch(lat, lon, ts):
        calls["n"] += 1
        return pd.DataFrame({"v": [lat + lon]})

    df1 = fetch(lat=58.4, lon=-170.0, ts="2025-09-09")
    df2 = fetch(lat=58.4, lon=-170.0, ts="2025-09-09")
    assert df1.equals(df2)
    assert calls["n"] == 1  # second call hit the cache

    # Non-DataFrame passthrough (lat missing).
    @cache_mod.memoize("demo2")
    def other(**kwargs):
        return "raw"

    assert other(lat=1.0) == "raw"  # no ts → passthrough, not cached
