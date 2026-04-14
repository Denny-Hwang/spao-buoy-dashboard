"""Tests for utils.p2.stats.trends."""

from __future__ import annotations

import numpy as np
import pytest

from utils.p2.stats.trends import cusum, mann_kendall, theil_sen


def test_mann_kendall_linear_increasing_p_lt_0p01():
    rng = np.random.default_rng(0)
    x = np.arange(100, dtype=float) + rng.normal(scale=0.5, size=100)
    out = mann_kendall(x)
    assert out["n"] == 100
    assert out["trend"] == "increasing"
    assert out["p_value"] < 0.01
    assert out["s"] > 0


def test_mann_kendall_linear_decreasing():
    rng = np.random.default_rng(1)
    x = -np.arange(100, dtype=float) + rng.normal(scale=0.5, size=100)
    out = mann_kendall(x)
    assert out["trend"] == "decreasing"
    assert out["p_value"] < 0.01


def test_mann_kendall_no_trend_on_random_series():
    rng = np.random.default_rng(2)
    x = rng.normal(size=200)
    out = mann_kendall(x)
    assert out["trend"] == "no trend"
    assert out["p_value"] > 0.05


def test_mann_kendall_short_series_returns_nan():
    out = mann_kendall([1.0, 2.0])
    assert out["trend"] == "no trend"
    assert np.isnan(out["s"])


def test_theil_sen_matches_ols_on_linear_data():
    rng = np.random.default_rng(3)
    x = np.arange(50, dtype=float)
    y = 2.5 * x + 7 + rng.normal(scale=0.1, size=50)
    fit = theil_sen(y, x)
    assert fit["n"] == 50
    assert fit["slope"] == pytest.approx(2.5, abs=0.05)
    assert fit["intercept"] == pytest.approx(7, abs=0.5)


def test_theil_sen_without_x_uses_index():
    y = [0.0, 1.0, 2.0, 3.0]
    fit = theil_sen(y)
    assert fit["slope"] == pytest.approx(1.0)


def test_cusum_detects_step_change():
    rng = np.random.default_rng(4)
    baseline = rng.normal(loc=0.0, scale=1.0, size=100)
    shift = rng.normal(loc=3.0, scale=1.0, size=100)
    x = np.concatenate([baseline, shift])
    out = cusum(x, target=0.0, k=0.5, h=5.0)
    assert out["alarms"]
    assert out["alarms"][0] >= 100  # first alarm triggers after the shift
    assert "sh" in out and "sl" in out
    assert out["sh"].shape == (200,)


def test_cusum_defaults_target_to_mean():
    x = np.array([1.0, 1.0, 1.0, 1.0])
    out = cusum(x)
    assert out["target"] == pytest.approx(1.0)
    assert out["alarms"] == []
