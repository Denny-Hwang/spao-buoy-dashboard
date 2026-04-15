"""Unit tests for utils.p2.ui_toolbar — pure-data helpers only.

These tests intentionally avoid calling ``render_device_time_filter``
directly (which needs Streamlit's widget runtime). They cover the
pure-Python helpers ``find_time_col`` and ``apply_device_time_filter``
so the Phase 2 page filter behavior is regression-tested without the
streamlit stub dance.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

# Ensure stubs are in place before importing the module (it imports
# streamlit transitively via utils.sheets_client fallbacks).
from tests.test_p2_skeleton import _install_stub_modules

_install_stub_modules()

from utils.p2.ui_toolbar import (  # noqa: E402
    apply_device_time_filter,
    find_time_col,
)


def _make_df() -> pd.DataFrame:
    return pd.DataFrame({
        "Device Tab": ["A", "A", "B", "B", "C"],
        "Timestamp": pd.to_datetime([
            "2026-01-01 00:00",
            "2026-01-02 12:00",
            "2026-01-03 06:00",
            "2026-01-05 18:00",
            "2026-01-10 09:00",
        ]),
        "WAVE_H_cm": [10.0, 20.0, 30.0, 40.0, 50.0],
    })


def test_find_time_col_detects_timestamp_and_coerces() -> None:
    df = _make_df().copy()
    # Drop typed timestamps to simulate Sheets returning strings.
    df["Timestamp"] = df["Timestamp"].astype(str)
    col = find_time_col(df)
    assert col == "Timestamp"
    assert pd.api.types.is_datetime64_any_dtype(df["Timestamp"])


def test_find_time_col_returns_none_for_empty_df() -> None:
    assert find_time_col(pd.DataFrame()) is None


def test_find_time_col_returns_none_when_no_time_column() -> None:
    df = pd.DataFrame({"foo": [1, 2], "bar": [3, 4]})
    assert find_time_col(df) is None


def test_apply_filter_by_device_and_time_window() -> None:
    df = _make_df()
    out = apply_device_time_filter(
        df,
        selected_devices=["A", "B"],
        dev_col="Device Tab",
        time_col="Timestamp",
        start_dt=datetime(2026, 1, 2),
        end_dt=datetime(2026, 1, 6),
    )
    assert set(out["Device Tab"]) == {"A", "B"}
    assert len(out) == 3  # A@01-02, B@01-03, B@01-05
    assert out["WAVE_H_cm"].tolist() == [20.0, 30.0, 40.0]


def test_apply_filter_preserves_nan_timestamps() -> None:
    df = _make_df()
    df.loc[0, "Timestamp"] = pd.NaT  # device A row with unknown time
    out = apply_device_time_filter(
        df,
        selected_devices=["A"],
        dev_col="Device Tab",
        time_col="Timestamp",
        start_dt=datetime(2026, 1, 2),
        end_dt=datetime(2026, 1, 6),
    )
    # Both A rows survive: one by time window, one because NaT is kept.
    assert len(out) == 2


def test_apply_filter_without_time_col_is_device_only() -> None:
    df = _make_df()
    out = apply_device_time_filter(
        df,
        selected_devices=["C"],
        dev_col="Device Tab",
        time_col=None,
        start_dt=None,
        end_dt=None,
    )
    assert len(out) == 1
    assert out["Device Tab"].iloc[0] == "C"


def test_apply_filter_returns_copy_not_view() -> None:
    df = _make_df()
    out = apply_device_time_filter(
        df,
        selected_devices=["A"],
        dev_col="Device Tab",
        time_col="Timestamp",
        start_dt=datetime(2026, 1, 1),
        end_dt=datetime(2026, 1, 31),
    )
    out.loc[out.index[0], "WAVE_H_cm"] = 999.0
    assert df["WAVE_H_cm"].tolist() == [10.0, 20.0, 30.0, 40.0, 50.0]


def test_apply_filter_empty_df_passthrough() -> None:
    empty = pd.DataFrame()
    assert apply_device_time_filter(empty, [], "Device Tab", None, None, None) is empty
