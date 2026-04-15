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
    canonicalize_lat_lon,
    find_time_col,
    resolve_lat_lon_columns,
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


# ---------- resolve_lat_lon_columns / canonicalize_lat_lon ---------

def test_resolve_lat_lon_exact_alias() -> None:
    df = pd.DataFrame({"Lat": [1.0], "Lon": [2.0]})
    assert resolve_lat_lon_columns(df) == ("Lat", "Lon")


def test_resolve_lat_lon_gps_variant() -> None:
    df = pd.DataFrame({"GPS Latitude": [1.0], "GPS Longitude": [2.0]})
    assert resolve_lat_lon_columns(df) == ("GPS Latitude", "GPS Longitude")


def test_resolve_lat_lon_fy25_approx_style() -> None:
    """FY25 tabs use headers that aren't in the exact alias list.
    The substring fallback must still resolve them."""
    df = pd.DataFrame({
        "Approx Latitude": [58.3],
        "Approx Longitude": [-169.9],
        "Battery Voltage": [3.25],
    })
    lat, lon = resolve_lat_lon_columns(df)
    assert lat == "Approx Latitude"
    assert lon == "Approx Longitude"


def test_resolve_lat_lon_excludes_long_term_tokens() -> None:
    """Ensure substring match doesn't mistake e.g. 'long-term flag' for longitude."""
    df = pd.DataFrame({
        "long-term stability": [1],
        "Latitude": [58.3],
        "Longitude": [-169.9],
    })
    lat, lon = resolve_lat_lon_columns(df)
    assert lat == "Latitude"
    assert lon == "Longitude"


def test_resolve_lat_lon_missing_returns_none() -> None:
    df = pd.DataFrame({"foo": [1], "bar": [2]})
    assert resolve_lat_lon_columns(df) == (None, None)


def test_canonicalize_lat_lon_renames_to_canonical() -> None:
    df = pd.DataFrame({
        "Approx Latitude": [58.3, 58.4],
        "Approx Longitude": [-169.9, -170.0],
        "Battery": [3.25, 3.24],
    })
    out = canonicalize_lat_lon(df)
    assert "Lat" in out.columns
    assert "Lon" in out.columns
    assert out["Lat"].tolist() == [58.3, 58.4]
    assert out["Lon"].tolist() == [-169.9, -170.0]
    # Original frame untouched.
    assert "Lat" not in df.columns


def test_canonicalize_lat_lon_idempotent_when_canonical_already_present() -> None:
    df = pd.DataFrame({"Lat": [1.0], "Lon": [2.0], "extra": [0]})
    out = canonicalize_lat_lon(df)
    assert out is df  # no rename → same object


def test_canonicalize_lat_lon_noop_when_lat_lon_absent() -> None:
    df = pd.DataFrame({"foo": [1], "bar": [2]})
    out = canonicalize_lat_lon(df)
    # No lat/lon to rename → passthrough.
    assert out is df


# ---------- FY25 compound "Approx Lat/Lng" column ------------------

def test_canonicalize_splits_compound_latlng_column() -> None:
    """FY25 tabs store GPS as a single ``Approx Lat/Lng`` column
    containing ``"58.4494,-174.29623"``. canonicalize_lat_lon must
    parse it into numeric Lat / Lon columns."""
    df = pd.DataFrame({
        "Date Time (UTC)": ["2025-09-10 02:23", "2025-09-10 03:10"],
        "Approx Lat/Lng": ["58.4494,-174.29623", "58.2881,-169.98806"],
        "Payload": ["042304ed", "01dd0434"],
    })
    out = canonicalize_lat_lon(df)
    assert "Lat" in out.columns
    assert "Lon" in out.columns
    assert out["Lat"].tolist() == pytest.approx([58.4494, 58.2881], rel=1e-6)
    assert out["Lon"].tolist() == pytest.approx([-174.29623, -169.98806], rel=1e-6)
    # Original frame untouched.
    assert "Lat" not in df.columns


def test_canonicalize_handles_empty_compound_values() -> None:
    """Blank / NaN entries in a compound Lat/Lng column become NaN
    (not exceptions) on both sides of the split."""
    df = pd.DataFrame({
        "Approx Lat/Lng": ["58.5,-174.0", "", None, "not-a-pair", "59.0,-170.0"],
    })
    out = canonicalize_lat_lon(df)
    # First and last rows parse, middle three are NaN.
    lats = out["Lat"].tolist()
    lons = out["Lon"].tolist()
    assert lats[0] == pytest.approx(58.5)
    assert lats[-1] == pytest.approx(59.0)
    assert pd.isna(lats[1]) and pd.isna(lats[2]) and pd.isna(lats[3])
    assert pd.isna(lons[1]) and pd.isna(lons[2]) and pd.isna(lons[3])


def test_canonicalize_does_not_split_when_separate_columns_exist() -> None:
    """When regular Lat / Lon already exist, the compound code path
    should not fire even if a stray compound-looking column is present."""
    df = pd.DataFrame({
        "Lat": [58.5],
        "Lon": [-174.0],
        "Approx Lat/Lng": ["58.5,-174.0"],  # shouldn't interfere
    })
    out = canonicalize_lat_lon(df)
    # Already canonical — passthrough.
    assert out is df
