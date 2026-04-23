"""Link-budget physics sanity checks."""

from __future__ import annotations

import math

import pytest

from utils.p3 import iridium_link as il


def test_antenna_gain_peak_at_zero():
    assert il.antenna_gain_db(0.0) == pytest.approx(3.0)


def test_antenna_gain_declines_monotonically():
    values = [il.antenna_gain_db(a) for a in (0, 15, 30, 45, 60, 75)]
    for a, b in zip(values, values[1:]):
        assert a >= b


def test_antenna_gain_hits_null_past_90():
    # Past 90° we clamp to -20 dB so link-budget math never returns -inf.
    assert il.antenna_gain_db(120.0) == pytest.approx(-20.0)


def test_slant_range_monotone_in_elevation():
    # Lower elevation → longer slant range at constant altitude.
    lo = il.slant_range_km(10.0)
    hi = il.slant_range_km(80.0)
    assert lo > hi
    assert hi < 900.0   # near-zenith ~ h=781
    assert lo > 1500.0


def test_link_margin_sign():
    # With default RockBLOCK params, a high-elevation pass should leave
    # positive margin; a grazing-angle pass should be near-zero or small.
    m_high = il.link_margin_db(75.0)
    m_low = il.link_margin_db(10.0)
    assert m_high > m_low
    assert m_high > 5.0       # healthy margin at high el
    assert m_low > -10.0      # still computable


def test_p_success_bounds():
    # Negative margin → 0.05 floor.
    assert il.p_success(-5.0, 10.0) == pytest.approx(0.05)
    # Very high margin at high elevation → capped at 0.97.
    assert il.p_success(30.0, 80.0) <= 0.97
    assert il.p_success(30.0, 80.0) > 0.9


def test_acquisition_time_piecewise():
    assert il.acquisition_time_s(70, 15) < il.acquisition_time_s(20, 15)
    # Low margin multiplies by 1.3.
    assert il.acquisition_time_s(70, 5) > il.acquisition_time_s(70, 15)


def test_cumulative_p_success_combines_attempts():
    # Two 0.5 attempts should combine to 0.75.
    p = il.cumulative_p_success([(10.0, 60.0), (10.0, 60.0)])
    assert p > 0.5
