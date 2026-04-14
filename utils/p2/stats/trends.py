"""
Non-parametric trend detection and change-point helpers.

* :func:`mann_kendall` — Mann-Kendall monotonic trend test with tie and
  continuity correction, returning the ``S`` statistic, variance,
  normalized ``Z``, and two-sided p-value.
* :func:`theil_sen` — Theil-Sen slope + intercept estimator (median of
  pairwise slopes, robust to outliers).
* :func:`cusum` — Page's CUSUM change-point detection with a tabular
  output of upper and lower cumulative sums.
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np

try:
    from scipy import stats as _scipy_stats
except Exception:  # pragma: no cover
    _scipy_stats = None


def _to_array(x: Iterable) -> np.ndarray:
    arr = np.asarray(list(x), dtype=float)
    return arr[np.isfinite(arr)]


def mann_kendall(x: Iterable[float]) -> dict:
    """Two-sided Mann-Kendall test for monotonic trend.

    Returns a dict with keys ``s``, ``var_s``, ``z``, ``p_value``,
    ``trend`` (one of ``"increasing"``, ``"decreasing"``, ``"no trend"``),
    and ``n``.

    Ties in ``x`` are handled via the standard variance correction.
    Requires at least 3 finite samples; otherwise returns NaNs.
    """
    arr = _to_array(x)
    n = len(arr)
    out: dict = {"n": n, "s": float("nan"), "var_s": float("nan"),
                 "z": float("nan"), "p_value": float("nan"), "trend": "no trend"}
    if n < 3:
        return out

    # S statistic.
    s = 0
    for i in range(n - 1):
        s += int(np.sign(arr[i + 1:] - arr[i]).sum())

    # Variance with tie correction.
    _unique, counts = np.unique(arr, return_counts=True)
    ties = counts[counts > 1]
    var_s = n * (n - 1) * (2 * n + 5) / 18.0
    var_s -= sum(t * (t - 1) * (2 * t + 5) for t in ties) / 18.0

    # Continuity-corrected normal approximation.
    if s > 0:
        z = (s - 1) / math.sqrt(var_s) if var_s > 0 else 0.0
    elif s < 0:
        z = (s + 1) / math.sqrt(var_s) if var_s > 0 else 0.0
    else:
        z = 0.0

    if _scipy_stats is not None:
        p = 2.0 * (1.0 - _scipy_stats.norm.cdf(abs(z)))
    else:  # pragma: no cover — scipy is a hard dep for stats module
        p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(z) / math.sqrt(2.0))))

    if p < 0.05 and s > 0:
        trend = "increasing"
    elif p < 0.05 and s < 0:
        trend = "decreasing"
    else:
        trend = "no trend"

    out.update({
        "s": float(s),
        "var_s": float(var_s),
        "z": float(z),
        "p_value": float(p),
        "trend": trend,
    })
    return out


def theil_sen(y: Iterable[float], x: Iterable[float] | None = None) -> dict:
    """Theil-Sen robust slope + intercept.

    Returns ``{"slope": float, "intercept": float, "n": int}``. With
    fewer than 2 samples the slope/intercept are NaN.
    """
    y_arr = np.asarray(list(y), dtype=float)
    if x is None:
        x_arr = np.arange(len(y_arr), dtype=float)
    else:
        x_arr = np.asarray(list(x), dtype=float)
    mask = np.isfinite(x_arr) & np.isfinite(y_arr)
    x_arr = x_arr[mask]
    y_arr = y_arr[mask]
    n = len(y_arr)
    if n < 2:
        return {"slope": float("nan"), "intercept": float("nan"), "n": n}
    slopes = []
    for i in range(n - 1):
        dx = x_arr[i + 1:] - x_arr[i]
        dy = y_arr[i + 1:] - y_arr[i]
        valid = dx != 0
        slopes.extend((dy[valid] / dx[valid]).tolist())
    slope = float(np.median(slopes)) if slopes else float("nan")
    intercept = float(np.median(y_arr - slope * x_arr))
    return {"slope": slope, "intercept": intercept, "n": n}


def cusum(
    x: Iterable[float],
    target: float | None = None,
    k: float = 0.5,
    h: float = 5.0,
) -> dict:
    """Page's tabular CUSUM for change detection.

    ``target`` defaults to the sample mean. ``k`` is the reference value
    in units of the sample standard deviation (default 0.5 σ), and ``h``
    is the decision threshold (default 5 σ).

    Returns dict with keys
        ``sh``         upper CUSUM array
        ``sl``         lower CUSUM array
        ``alarms``     sorted indices where |S| crossed ``h``
        ``target``     used target value
    """
    arr = np.asarray(list(x), dtype=float)
    if target is None:
        target = float(np.nanmean(arr))
    sigma = float(np.nanstd(arr, ddof=1)) if len(arr) > 1 else 0.0
    if sigma == 0 or not math.isfinite(sigma):
        sigma = 1.0
    sh = np.zeros_like(arr)
    sl = np.zeros_like(arr)
    alarms: list[int] = []
    for i, v in enumerate(arr):
        prev_h = sh[i - 1] if i > 0 else 0.0
        prev_l = sl[i - 1] if i > 0 else 0.0
        sh[i] = max(0.0, prev_h + (v - target - k * sigma))
        sl[i] = min(0.0, prev_l + (v - target + k * sigma))
        if sh[i] > h * sigma or sl[i] < -h * sigma:
            alarms.append(i)
    return {"sh": sh, "sl": sl, "alarms": alarms, "target": target}


__all__ = ["mann_kendall", "theil_sen", "cusum"]
