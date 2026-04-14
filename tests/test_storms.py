"""Tests for utils.p2.physics.storms."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from utils.p2.physics.storms import detect_storms, superposed_epoch


def _frame(n=24) -> pd.DataFrame:
    ts = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame({
        "Timestamp": ts,
        "Hs": np.full(n, 1.5),
        "U10": np.full(n, 6.0),
        "Pres": np.full(n, 1012.0),
        "Lat": np.full(n, 58.0),
    })


def test_wave_storm_detection_via_rolling_mean():
    df = _frame(n=12)
    df.loc[6:11, "Hs"] = 4.5  # 6 hours of high seas → rolling mean crosses 4.0
    out = detect_storms(df)
    assert out.loc[11, "wave_storm"]
    assert not out.loc[0, "wave_storm"]
    assert out.loc[11, "storm_type"].startswith("wave")
    assert out["storm_event_id"].max() >= 1


def test_wave_storm_instant_trigger():
    df = _frame(n=5)
    df.loc[2, "Hs"] = 5.5
    out = detect_storms(df)
    assert out.loc[2, "wave_storm"]


def test_wind_storm_detection():
    df = _frame(n=8)
    df.loc[3:7, "U10"] = 21.0
    out = detect_storms(df)
    assert out.loc[7, "wind_storm"]
    assert out.loc[0, "storm"] is False or not out.loc[0, "storm"]


def test_cyclone_detection_sanders_gyakum():
    # At 58°N, threshold ≈ -24*sin(58°)/sin(60°) ≈ -23.5 hPa per 24 h.
    ts = pd.date_range("2025-01-01", periods=25, freq="h", tz="UTC")
    pres = np.linspace(1010, 985, 25)  # 25 hPa drop over 24 h
    df = pd.DataFrame({
        "Timestamp": ts, "Hs": 1.0, "U10": 5.0, "Pres": pres, "Lat": 58.0,
    })
    out = detect_storms(df)
    assert out.loc[24, "cyclone"]
    assert "cyclone" in out.loc[24, "storm_type"]


def test_event_id_assignment():
    df = _frame(n=20)
    df.loc[5:6, "Hs"] = 5.5
    df.loc[12:13, "Hs"] = 5.5
    out = detect_storms(df)
    ids = out.loc[out["storm"], "storm_event_id"].unique()
    assert len(ids) >= 2


def test_superposed_epoch_centres_on_event():
    ts = pd.date_range("2025-01-01", periods=100, freq="h", tz="UTC")
    df = pd.DataFrame({
        "Timestamp": ts,
        "var": np.sin(np.arange(100) / 10.0),
    })
    events = [ts[20], ts[60]]
    out = superposed_epoch(df, events, window_hours=10, cols=["var"])
    assert set(out.columns) == {"event_idx", "lag_hours", "var"}
    assert out["event_idx"].nunique() == 2
    assert out["lag_hours"].min() >= -10
    assert out["lag_hours"].max() <= 10


def test_superposed_epoch_no_events_returns_empty():
    df = pd.DataFrame({
        "Timestamp": pd.date_range("2025-01-01", periods=5, freq="h", tz="UTC"),
        "var": [1.0, 2.0, 3.0, 4.0, 5.0],
    })
    out = superposed_epoch(df, [pd.Timestamp("2030-01-01", tz="UTC")], window_hours=5, cols=["var"])
    assert out.empty
