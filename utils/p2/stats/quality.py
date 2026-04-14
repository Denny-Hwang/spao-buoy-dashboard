"""
Validation / quality metrics for observation–reference comparisons.

* :func:`bias`         — mean(pred - obs)
* :func:`rmse`         — root-mean-square error
* :func:`uRMSE`        — unbiased (centred) RMSE, sqrt(rmse² - bias²)
* :func:`std_diff`     — std(pred) - std(obs)
* :func:`correlation`  — Pearson correlation coefficient
* :func:`metrics_table` — computes all metrics for a dict of references
  against a common observation vector and returns a tidy DataFrame.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


def _align(obs, pred) -> tuple[np.ndarray, np.ndarray]:
    o = np.asarray(list(obs), dtype=float)
    p = np.asarray(list(pred), dtype=float)
    if o.shape != p.shape:
        raise ValueError(f"obs and pred must match shape; got {o.shape} vs {p.shape}")
    mask = np.isfinite(o) & np.isfinite(p)
    return o[mask], p[mask]


def bias(obs, pred) -> float:
    o, p = _align(obs, pred)
    if o.size == 0:
        return float("nan")
    return float(np.mean(p - o))


def rmse(obs, pred) -> float:
    o, p = _align(obs, pred)
    if o.size == 0:
        return float("nan")
    return float(np.sqrt(np.mean((p - o) ** 2)))


def uRMSE(obs, pred) -> float:
    """Unbiased (centred) RMSE: ``sqrt(rmse² - bias²)``."""
    r = rmse(obs, pred)
    b = bias(obs, pred)
    if not np.isfinite(r) or not np.isfinite(b):
        return float("nan")
    val = r * r - b * b
    if val < 0 and val > -1e-12:
        val = 0.0
    return float(np.sqrt(max(val, 0.0)))


def std_diff(obs, pred) -> float:
    """``std(pred) - std(obs)`` (positive = reference is more variable)."""
    o, p = _align(obs, pred)
    if o.size < 2:
        return float("nan")
    return float(np.std(p, ddof=1) - np.std(o, ddof=1))


def correlation(obs, pred) -> float:
    o, p = _align(obs, pred)
    if o.size < 2:
        return float("nan")
    if np.std(o) == 0 or np.std(p) == 0:
        return float("nan")
    return float(np.corrcoef(o, p)[0, 1])


def metrics_table(obs: Iterable[float], refs: dict[str, Iterable[float]]) -> pd.DataFrame:
    """Return a DataFrame with rows indexed by reference name.

    Columns: ``n, bias, rmse, uRMSE, std_diff, correlation``.
    """
    rows = []
    for name, pred in refs.items():
        o, p = _align(obs, pred)
        rows.append({
            "reference": name,
            "n": int(o.size),
            "bias": bias(o, p),
            "rmse": rmse(o, p),
            "uRMSE": uRMSE(o, p),
            "std_diff": std_diff(o, p),
            "correlation": correlation(o, p),
        })
    return pd.DataFrame(rows).set_index("reference")


__all__ = ["bias", "rmse", "uRMSE", "std_diff", "correlation", "metrics_table"]
