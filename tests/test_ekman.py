"""Tests for utils.p2.physics.ekman."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from utils.p2.physics.ekman import (
    compute_drift_velocity,
    decompose_drift,
    fit_windage,
)


def _wind_series(n: int, speed: float = 10.0, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    theta = rng.uniform(0, 2 * math.pi, size=n)
    u = speed * np.cos(theta)
    v = speed * np.sin(theta)
    return np.column_stack([u, v])


def test_fit_windage_recovers_synthetic_alpha_and_theta():
    n = 500
    wind = _wind_series(n, speed=10.0, seed=42)
    alpha_true = 0.03
    theta_true_deg = 20.0
    theta = math.radians(theta_true_deg)
    rot = np.array([
        [math.cos(theta), -math.sin(theta)],
        [math.sin(theta), math.cos(theta)],
    ])
    drift = alpha_true * (wind @ rot.T)
    rng = np.random.default_rng(7)
    drift += rng.normal(scale=0.01, size=drift.shape)

    fit = fit_windage(drift, wind)
    assert fit["n_samples"] == n
    assert fit["alpha"] == pytest.approx(alpha_true, rel=0.10)
    assert fit["theta_deg"] == pytest.approx(theta_true_deg, abs=3.0)
    assert fit["r_squared"] > 0.9
    assert fit["residual_u"].shape == (n,)
    assert fit["residual_v"].shape == (n,)


def test_fit_windage_degenerate_wind_returns_nan():
    drift = np.zeros((5, 2))
    wind = np.zeros((5, 2))
    fit = fit_windage(drift, wind)
    assert math.isnan(fit["alpha"])
    assert math.isnan(fit["theta_deg"])


def test_fit_windage_shape_validation():
    with pytest.raises(ValueError):
        fit_windage(np.zeros((3, 2)), np.zeros((4, 2)))


def test_compute_drift_velocity_from_gps():
    # Two-row track moving 1° of latitude over 1 hour (~111 km / 3600 s = 30.9 m/s).
    df = pd.DataFrame({
        "Timestamp": pd.to_datetime(
            ["2025-01-01T00:00:00Z", "2025-01-01T01:00:00Z"]
        ),
        "Lat": [58.0, 59.0],
        "Lon": [-170.0, -170.0],
    })
    out = compute_drift_velocity(df)
    assert "u_drift" in out and "v_drift" in out
    assert np.isnan(out["u_drift"].iloc[0])
    # ~111 km north in 3600 s ⇒ v ≈ 30.9 m/s, u ≈ 0.
    assert out["v_drift"].iloc[1] == pytest.approx(30.9, rel=0.02)
    assert abs(out["u_drift"].iloc[1]) < 1.0


def test_compute_drift_velocity_treats_zero_zero_as_no_fix():
    """A row with Lat=0, Lon=0 is a detection-failure sentinel — using
    it as a real position would create artificial drift velocities of
    several thousand m/s. Make sure the velocity around it is NaN
    rather than physically implausible."""
    df = pd.DataFrame({
        "Timestamp": pd.to_datetime([
            "2025-01-01T00:00:00Z",
            "2025-01-01T01:00:00Z",
            "2025-01-01T02:00:00Z",
            "2025-01-01T03:00:00Z",
        ]),
        "Lat": [58.0, 0.0, 58.001, 58.002],
        "Lon": [-170.0, 0.0, -170.001, -170.002],
    })
    out = compute_drift_velocity(df)
    # The transition INTO the bad fix and OUT of it must not produce
    # finite velocities — those would be ~10 km/s artifacts.
    assert np.isnan(out["u_drift"].iloc[1])
    assert np.isnan(out["v_drift"].iloc[1])
    assert np.isnan(out["u_drift"].iloc[2])
    assert np.isnan(out["v_drift"].iloc[2])
    # The good-to-good step at the end must still yield a real velocity.
    assert np.isfinite(out["u_drift"].iloc[3]) or np.isfinite(out["v_drift"].iloc[3])


def test_decompose_drift_pipeline():
    n = 50
    wind = _wind_series(n, speed=8.0, seed=3)
    alpha_true = 0.02
    drift = alpha_true * wind + np.random.default_rng(5).normal(scale=0.005, size=wind.shape)
    df = pd.DataFrame({
        "u_drift": drift[:, 0],
        "v_drift": drift[:, 1],
        "U10": wind[:, 0],
        "V10": wind[:, 1],
    })
    out = decompose_drift(df)
    assert "u_wind_driven" in out and "u_residual" in out
    assert out.attrs["windage_fit"]["alpha"] == pytest.approx(alpha_true, rel=0.15)
    assert out.attrs["windage_fit"]["r_squared"] > 0.9


def test_compute_drift_velocity_missing_columns():
    with pytest.raises(ValueError):
        compute_drift_velocity(pd.DataFrame({"foo": [1, 2]}))
