"""
On-disk parquet cache for enrichment source fetches.

Keyed by (source, snapped_lat, snapped_lon, time-bucket). The cache is
only useful across cron invocations on a persistent runner; on GitHub
Actions each run gets a fresh filesystem, so in practice the cache is
per-run and mostly serves to de-duplicate calls inside a single run.

Cache location:
    $SPAO_CACHE_DIR (if set) or ~/.cache/spao_enrichment
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd


def _cache_root() -> Path:
    root = Path(os.environ.get("SPAO_CACHE_DIR", Path.home() / ".cache" / "spao_enrichment"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _key_to_filename(key: tuple) -> Path:
    digest = hashlib.sha1(
        json.dumps(list(key), default=str).encode("utf-8")
    ).hexdigest()[:16]
    source = str(key[0]) if key else "unknown"
    return _cache_root() / f"{source}_{digest}.parquet"


def get(key: tuple) -> pd.DataFrame | None:
    """Return the cached DataFrame for *key* or ``None`` if absent."""
    path = _key_to_filename(key)
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def put(key: tuple, df: pd.DataFrame) -> None:
    """Write *df* under *key*. Silently no-ops on serialization failure."""
    if df is None or getattr(df, "empty", True):
        return
    path = _key_to_filename(key)
    try:
        df.to_parquet(path)
    except Exception:
        # pyarrow may not be installed in lightweight envs; cache is optional.
        try:
            path.with_suffix(".pkl").write_bytes(df.to_pickle(None) or b"")
        except Exception:
            pass


def list_keys() -> list[str]:
    """Return a list of file stems currently in the cache (for debugging)."""
    root = _cache_root()
    return sorted(p.stem for p in root.glob("*.parquet"))


def clear() -> int:
    """Remove every file in the cache directory. Returns count removed."""
    root = _cache_root()
    n = 0
    for p in root.glob("*"):
        try:
            p.unlink()
            n += 1
        except OSError:
            pass
    return n


def memoize(source: str):
    """Decorator: cache the return value of a single-point fetcher.

    The wrapped function must accept keyword args ``lat``, ``lon`` and a
    timestamp-like arg named ``ts`` / ``date`` / ``dt``. Unknown kwargs
    make the call uncacheable (passthrough).
    """
    def _decorator(fn):
        def _wrapped(*args: Any, **kwargs: Any):
            ts = kwargs.get("ts") or kwargs.get("date") or kwargs.get("dt")
            lat = kwargs.get("lat")
            lon = kwargs.get("lon")
            if ts is None or lat is None or lon is None:
                return fn(*args, **kwargs)
            key = (source, round(float(lat), 1), round(float(lon), 1), str(ts))
            cached = get(key)
            if cached is not None and not cached.empty:
                return cached
            result = fn(*args, **kwargs)
            if isinstance(result, pd.DataFrame):
                put(key, result)
            return result
        return _wrapped
    return _decorator
