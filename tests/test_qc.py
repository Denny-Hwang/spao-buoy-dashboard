"""Tests for utils.p2.qc."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from utils.p2 import qc


def _frame(**kwargs) -> pd.DataFrame:
    return pd.DataFrame(kwargs)


def test_sst_vs_oisst_flag():
    df = _frame(
        SST_buoy=[10.0, 10.0, 10.0],
        SAT_SST_OISST_cC=[1000, 800, 700],  # 10.0, 8.0, 7.0
    )
    flags = qc.check_sst_vs_oisst(df)
    # |10-10|=0 OK, |10-8|=2 OK, |10-7|=3 boundary (>3 is False)
    assert list(flags) == [False, False, False]
    df.loc[3] = {"SST_buoy": 10.0, "SAT_SST_OISST_cC": 300}  # 3°C, diff=7
    flags = qc.check_sst_vs_oisst(df)
    assert flags.iloc[3]


def test_wave_height_flag():
    df = _frame(Hs=[2.0, 16.0, 8.0])
    flags = qc.check_wave_height(df)
    assert list(flags) == [False, True, False]


def test_wave_height_flag_from_enriched_column():
    df = _frame(WAVE_H_cm=[200, 1600, 800])  # 2 m, 16 m, 8 m
    flags = qc.check_wave_height(df)
    assert list(flags) == [False, True, False]


def test_wind_flag_from_cms_column():
    df = _frame(WIND_SPD_cms=[500, 5100, 3000])  # 5, 51, 30 m/s
    flags = qc.check_wind_speed(df)
    assert list(flags) == [False, True, False]


def test_gps_speed_flag_fast_move():
    # Two rows 1° latitude apart (~111 km) over 1 hour → ~111 km/h.
    df = _frame(
        Timestamp=pd.to_datetime(["2025-01-01T00:00:00Z", "2025-01-01T01:00:00Z"]),
        Lat=[58.0, 59.0],
        Lon=[-170.0, -170.0],
    )
    flags = qc.check_gps_speed(df)
    assert flags.iloc[1]


def test_gps_speed_flag_normal_drift():
    df = _frame(
        Timestamp=pd.to_datetime([
            "2025-01-01T00:00:00Z",
            "2025-01-01T01:00:00Z",
            "2025-01-01T02:00:00Z",
        ]),
        Lat=[58.0, 58.001, 58.002],
        Lon=[-170.0, -170.0, -170.0],
    )
    flags = qc.check_gps_speed(df)
    assert not flags.any()


def test_qc_summary_structure():
    df = _frame(
        Timestamp=pd.to_datetime(["2025-01-01T00:00:00Z", "2025-01-01T01:00:00Z"]),
        Lat=[58.0, 58.001],
        Lon=[-170.0, -170.0],
        SST_buoy=[10.0, 10.0],
        SAT_SST_OISST_cC=[1000, 1000],
        Hs=[2.0, 2.0],
        WIND_SPD_cms=[500, 500],
    )
    summary = qc.qc_summary(df)
    assert set(summary["check"]) == set(qc.QC_CHECKS)
    assert (summary["n_flagged"] == 0).all()
    assert (summary["n_rows"] == 2).all()


def test_qc_flags_matrix_boolean_columns():
    df = _frame(
        Timestamp=pd.to_datetime(["2025-01-01T00:00:00Z", "2025-01-01T01:00:00Z"]),
        Lat=[58.0, 59.0],
        Lon=[-170.0, -170.0],
        Hs=[2.0, 20.0],
    )
    flags = qc.qc_flags_matrix(df)
    assert set(flags.columns) == set(qc.QC_CHECKS)
    assert flags["wave_h_gt15"].iloc[1]
    assert flags["gps_speed_gt10kmh"].iloc[1]
