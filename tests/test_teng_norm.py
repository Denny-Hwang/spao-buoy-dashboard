"""Tests for utils.p2.physics.teng_norm."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from utils.p2.physics.teng_norm import (
    eta_level0,
    eta_level1,
    eta_level2,
    teng_power_mw,
)


def _frame(**kwargs) -> pd.DataFrame:
    return pd.DataFrame(kwargs)


def test_teng_power_from_direct_column():
    df = _frame(TENG_P_mW=[1.0, 2.0, 3.0])
    p = teng_power_mw(df)
    assert list(p) == [1.0, 2.0, 3.0]
    assert p.name == "TENG_P_mW"


def test_teng_power_from_voltage_current():
    df = _frame(TENG_V=[1.0, 2.0], TENG_I=[0.001, 0.002])  # 1 mW, 4 mW
    p = teng_power_mw(df)
    assert p.iloc[0] == pytest.approx(1.0)
    assert p.iloc[1] == pytest.approx(4.0)


def test_teng_power_all_nan_when_missing():
    df = _frame(Something=[1, 2, 3])
    p = teng_power_mw(df)
    assert len(p) == 3
    assert p.isna().all()


def test_eta_levels_monotonic_in_wave_state():
    # Constant TENG output; increasing Hs → eta1 and eta2 should shrink.
    df = _frame(
        TENG_P_mW=[100.0, 100.0, 100.0],
        Hs=[1.0, 2.0, 4.0],
        Tp=[6.0, 6.0, 6.0],
    )
    e0 = eta_level0(df)
    e1 = eta_level1(df)
    e2 = eta_level2(df)
    assert (e0 == 100.0).all()
    assert e1.iloc[0] > e1.iloc[1] > e1.iloc[2]
    assert e2.iloc[0] > e2.iloc[1] > e2.iloc[2]
    # eta2 = eta1 / Tp when Tp constant.
    assert e2.iloc[0] == pytest.approx(e1.iloc[0] / 6.0, rel=1e-9)


def test_eta_level1_guards_against_divide_by_zero():
    df = _frame(TENG_P_mW=[5.0, 5.0], Hs=[0.0, 1.0], Tp=[6.0, 6.0])
    e1 = eta_level1(df)
    assert np.isnan(e1.iloc[0])
    assert np.isfinite(e1.iloc[1])


def test_enriched_cm_ds_decoding():
    # WAVE_H_cm and WAVE_T_ds are stored in cm and deci-seconds.
    df = _frame(TENG_P_mW=[10.0], WAVE_H_cm=[200], WAVE_T_ds=[70])
    e2 = eta_level2(df)
    # Hs=2.0 m, Tp=7.0 s  → denom = 2² × 7 = 28, eta2 = 10/28 ≈ 0.357
    assert e2.iloc[0] == pytest.approx(10.0 / 28.0, rel=1e-9)
