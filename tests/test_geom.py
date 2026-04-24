"""Tests for the Phase 2 shared geodesy helpers.

The point of factoring ``haversine_km`` out of ``derived.py`` and
``qc.py`` was to stop those two staying in sync by convention. These
tests lock the spec down: the scalar and vector forms must agree, the
numerics must match the previous implementation at a representative
scale, and non-finite inputs must yield NaN (vector) or be rejected
upstream (scalar).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from utils.p2.physics.geom import (
    EARTH_RADIUS_M,
    haversine_km,
    haversine_km_array,
)


def test_earth_radius_matches_legacy_constant():
    # Previously duplicated in derived.py / qc.py; regressions here
    # would shift all drift-distance numerics by ~0.3 %.
    assert EARTH_RADIUS_M == 6_371_000.0


def test_haversine_km_zero_when_same_point():
    assert haversine_km(0.0, 0.0, 0.0, 0.0) == 0.0
    assert haversine_km(71.3, -156.7, 71.3, -156.7) == 0.0


def test_haversine_km_antipode_equals_half_circumference():
    # Great-circle distance between antipodes is π·R.
    expected_km = math.pi * EARTH_RADIUS_M / 1000.0
    got = haversine_km(0.0, 0.0, 0.0, 180.0)
    assert got == pytest.approx(expected_km, rel=1e-6)


def test_haversine_km_one_degree_of_latitude_is_111_km():
    # 1° latitude ≈ 111.19 km on our spherical Earth.
    got = haversine_km(0.0, 0.0, 1.0, 0.0)
    assert got == pytest.approx(111.19, abs=0.05)


def test_haversine_km_array_matches_scalar_elementwise():
    # A mix of tropical, mid-latitude, and polar pairs.
    lat1 = np.array([0.0, 45.0, 71.3, -33.0])
    lon1 = np.array([0.0, -120.0, -156.7, 151.0])
    lat2 = np.array([0.0, 45.5, 71.4, -34.0])
    lon2 = np.array([1.0, -119.5, -156.5, 152.0])

    vec = haversine_km_array(lat1, lon1, lat2, lon2)
    scalar = np.array([
        haversine_km(a, b, c, d)
        for a, b, c, d in zip(lat1, lon1, lat2, lon2)
    ])
    np.testing.assert_allclose(vec, scalar, rtol=1e-12, atol=1e-9)


def test_haversine_km_array_nans_propagate_per_row_only():
    # A NaN in one row must not poison its neighbours.
    lat1 = np.array([0.0, np.nan, 10.0])
    lon1 = np.array([0.0, 0.0, 0.0])
    lat2 = np.array([0.0, 0.0, 10.0])
    lon2 = np.array([1.0, 1.0, 2.0])

    vec = haversine_km_array(lat1, lon1, lat2, lon2)
    assert np.isfinite(vec[0])
    assert np.isnan(vec[1])
    assert np.isfinite(vec[2])


def test_haversine_km_clamps_floating_point_overshoot():
    # Forcing identical coordinates through the formula must not trip
    # asin()'s domain assertion due to 1.0 + tiny_fp overflow — this
    # is the reason the implementation clamps ``a`` to [0, 1].
    extreme = 89.999999
    assert haversine_km(extreme, 0.0, extreme, 0.0) == 0.0
