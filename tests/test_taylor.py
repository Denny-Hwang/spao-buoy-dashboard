"""Tests for utils.p2.stats.taylor and utils.p2.viz.*"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from utils.p2.physics.storms import superposed_epoch
from utils.p2.stats.taylor import taylor_diagram, taylor_stats
from utils.p2.viz.diagrams import stick_plot, target_diagram, wind_rose
from utils.p2.viz.epoch import plot_superposed


def test_taylor_stats_perfect_match():
    rng = np.random.default_rng(0)
    obs = rng.normal(size=200)
    stats = taylor_stats(obs, obs)
    assert stats["r"] == pytest.approx(1.0)
    assert stats["crmse"] == pytest.approx(0.0, abs=1e-12)
    assert stats["sigma"] == pytest.approx(float(np.std(obs, ddof=1)))


def test_taylor_stats_noisy_reference():
    rng = np.random.default_rng(2)
    obs = rng.normal(size=200)
    pred = obs + rng.normal(scale=0.3, size=200)
    stats = taylor_stats(obs, pred)
    assert 0 < stats["r"] < 1
    assert stats["crmse"] > 0


def test_taylor_diagram_returns_figure():
    rng = np.random.default_rng(1)
    obs = rng.normal(size=50)
    refs = {"a": obs + 0.1, "b": rng.normal(size=50)}
    fig = taylor_diagram(obs, refs)
    assert fig is not None
    # Must contain at least one trace per reference plus the reference arc.
    assert len(fig.data) >= 2


def test_target_diagram_figure():
    rng = np.random.default_rng(3)
    obs = rng.normal(size=100)
    refs = {"a": obs + 0.05, "b": obs * 1.2}
    fig = target_diagram(obs, refs)
    assert fig is not None
    assert len(fig.data) >= 2


def test_stick_plot_figure():
    t = pd.date_range("2025-01-01", periods=5, freq="h", tz="UTC")
    fig = stick_plot(t, u=[0.1, 0.2, 0.3, 0.4, 0.5], v=[0.0, 0.1, 0.0, -0.1, 0.0])
    assert fig is not None
    assert len(fig.layout.shapes) == 5


def test_wind_rose_figure():
    rng = np.random.default_rng(4)
    d = rng.uniform(0, 360, size=200)
    s = rng.uniform(0, 15, size=200)
    fig = wind_rose(d, s)
    assert fig is not None
    assert len(fig.data) >= 1


def test_plot_superposed_figure():
    ts = pd.date_range("2025-01-01", periods=100, freq="h", tz="UTC")
    df = pd.DataFrame({
        "Timestamp": ts,
        "Hs": np.sin(np.arange(100) / 5.0) + 1.0,
        "U10": np.cos(np.arange(100) / 5.0) + 5.0,
    })
    events = [ts[30], ts[70]]
    epoch_df = superposed_epoch(df, events, window_hours=12, cols=["Hs", "U10"])
    fig = plot_superposed(epoch_df, variables=["Hs", "U10"])
    assert fig is not None
    # At least two subplot panels populated.
    assert len(fig.data) >= 2
