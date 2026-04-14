"""Tests for utils.p2.physics.wave_power."""

from __future__ import annotations

import math

import numpy as np
import pytest

from utils.p2.physics.wave_power import (
    STEEPNESS_BREAKING,
    theoretical_wave_flux_w_per_m,
    wave_steepness,
)


def test_canonical_falnes_value():
    """Hs=3.1, Tp=7.0 under Falnes Eq. 6.19 must land in the 25–55 kW/m band.

    The canonical Falnes/DNV formula with Te = 0.9 Tp yields ≈ 29.7 kW/m;
    published references vary up to ~47 kW/m depending on Te convention.
    """
    P = theoretical_wave_flux_w_per_m(3.1, 7.0)
    assert 25_000 < P < 55_000
    # Specifically match the ρ g² / (64 π) · Hs² · 0.9 Tp value.
    expected = 1025 * 9.81 ** 2 / (64 * math.pi) * 3.1 ** 2 * 0.9 * 7.0
    assert P == pytest.approx(expected, rel=1e-6)


def test_flux_scales_with_hs_squared_and_te_linear():
    p1 = theoretical_wave_flux_w_per_m(1.0, 10.0)
    p2 = theoretical_wave_flux_w_per_m(2.0, 10.0)
    p3 = theoretical_wave_flux_w_per_m(1.0, 20.0)
    assert p2 == pytest.approx(p1 * 4.0, rel=1e-9)
    assert p3 == pytest.approx(p1 * 2.0, rel=1e-9)


def test_flux_array_input():
    P = theoretical_wave_flux_w_per_m(np.array([0.0, 1.0, 3.1]), np.array([5.0, 5.0, 7.0]))
    assert P.shape == (3,)
    assert P[0] == pytest.approx(0.0)
    assert P[2] > P[1]


def test_flux_invalid_inputs_yield_nan():
    P = theoretical_wave_flux_w_per_m(-1.0, 7.0)
    assert np.isnan(P)
    P = theoretical_wave_flux_w_per_m(3.1, 0.0)
    assert np.isnan(P)


def test_steepness_breaking_limit():
    # Choose Hs/Tp such that s is far below the Miche limit.
    s = wave_steepness(1.0, 10.0)
    assert 0 < s < STEEPNESS_BREAKING
    # Steep sea: large Hs, short Tp pushes toward the breaking limit.
    s_steep = wave_steepness(5.0, 5.0)
    assert s_steep > s


def test_steepness_vectorized():
    s = wave_steepness(np.array([1.0, 2.0, 3.0]), np.array([10.0, 10.0, 10.0]))
    assert s.shape == (3,)
    # Steepness is linear in Hs at fixed Tp.
    assert s[1] == pytest.approx(2 * s[0], rel=1e-12)
    assert s[2] == pytest.approx(3 * s[0], rel=1e-12)


def test_steepness_invalid():
    assert np.isnan(wave_steepness(1.0, 0.0))
    assert np.isnan(wave_steepness(-1.0, 10.0))
