"""Tests for utils.p2.stats.quality."""

from __future__ import annotations

import math

import numpy as np
import pytest

from utils.p2.stats.quality import (
    bias,
    correlation,
    metrics_table,
    rmse,
    std_diff,
    uRMSE,
)


def test_bias_rmse_urmse_on_simple_series():
    obs = [0.0, 1.0, 2.0, 3.0]
    pred = [0.5, 1.5, 2.5, 3.5]
    assert bias(obs, pred) == pytest.approx(0.5)
    assert rmse(obs, pred) == pytest.approx(0.5)
    # Constant offset → uRMSE = sqrt(rmse² - bias²) = 0
    assert uRMSE(obs, pred) == pytest.approx(0.0, abs=1e-12)


def test_urmse_on_noisy_series():
    rng = np.random.default_rng(0)
    obs = rng.normal(size=200)
    pred = obs + 0.2 + rng.normal(scale=0.1, size=200)
    b = bias(obs, pred)
    r = rmse(obs, pred)
    u = uRMSE(obs, pred)
    assert b == pytest.approx(0.2, abs=0.05)
    assert r > 0
    assert u == pytest.approx(math.sqrt(r * r - b * b), rel=1e-12)


def test_std_diff_positive_when_pred_more_variable():
    obs = np.ones(10) * 1.0
    pred = np.linspace(-5, 5, 10)
    assert std_diff(obs, pred) > 0


def test_correlation_perfect_and_anti():
    x = np.arange(50, dtype=float)
    assert correlation(x, 2 * x + 1) == pytest.approx(1.0)
    assert correlation(x, -x) == pytest.approx(-1.0)


def test_correlation_nan_when_constant():
    x = np.arange(5)
    y = np.ones(5)
    assert np.isnan(correlation(x, y))


def test_aligning_handles_nans():
    obs = [1.0, 2.0, float("nan"), 4.0]
    pred = [1.1, 2.1, 3.1, float("nan")]
    assert bias(obs, pred) == pytest.approx(0.1)
    assert rmse(obs, pred) == pytest.approx(0.1, abs=1e-12)


def test_metrics_table_structure():
    rng = np.random.default_rng(1)
    obs = rng.normal(size=100)
    refs = {
        "model_a": obs + 0.1,
        "model_b": obs * 1.1 + 0.05,
        "model_c": rng.normal(size=100),
    }
    tbl = metrics_table(obs, refs)
    assert list(tbl.columns) == ["n", "bias", "rmse", "uRMSE", "std_diff", "correlation"]
    assert list(tbl.index) == ["model_a", "model_b", "model_c"]
    assert tbl.loc["model_a", "bias"] == pytest.approx(0.1, abs=1e-12)
    assert tbl.loc["model_c", "correlation"] < tbl.loc["model_a", "correlation"]


def test_shape_mismatch_raises():
    with pytest.raises(ValueError):
        bias([1, 2], [1, 2, 3])
