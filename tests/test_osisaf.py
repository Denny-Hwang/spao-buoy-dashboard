"""Unit tests for ``utils.p2.sources.osisaf``."""

from __future__ import annotations

import sys
import types
from datetime import date
from unittest.mock import MagicMock

import numpy as np
import pytest

from utils.p2.sources import osisaf


class _FakeDataArray:
    def __init__(self, value):
        self._value = np.asarray(value, dtype=float)
        self.dims = ("yc", "xc")

    def sel(self, *args, **kwargs):
        return self

    def isel(self, *args, **kwargs):
        return self

    @property
    def values(self):
        return self._value


class _FakeDataset:
    def __init__(self, value):
        self._arr = _FakeDataArray(value)

    def __getitem__(self, name):
        assert name == "ice_conc"
        return self._arr

    def close(self):
        pass


# ──────────────────────────────────────────────────────────────────────
# Synthetic physics — the tropical short-circuit requires no mocks.
# ──────────────────────────────────────────────────────────────────────
def test_tropics_return_none_without_network():
    # 10°N equatorial — function must return None without touching xarray.
    assert osisaf.fetch_sea_ice_concentration(10.0, -50.0, date(2025, 7, 1)) is None
    assert osisaf.fetch_ice_edge_distance_km(0.0, 0.0, date(2025, 7, 1)) is None


def test_bering_sea_september_returns_zero(monkeypatch):
    """58.35°N, -169.98°W in September must come back as ~0% ice."""
    fake_xr = types.ModuleType("xarray")
    fake_xr.open_dataset = MagicMock(return_value=_FakeDataset(0.0))
    monkeypatch.setitem(sys.modules, "xarray", fake_xr)

    val = osisaf.fetch_sea_ice_concentration(58.35, -169.98, date(2025, 9, 9))
    assert val is not None
    assert val == pytest.approx(0.0, abs=1e-6)
    # URL used should be the NH file for 2025-09-09.
    args, kwargs = fake_xr.open_dataset.call_args
    url = args[0]
    assert "2025/09/" in url
    assert "nh" in url
    assert "20250909" in url


def test_arctic_january_returns_full_ice(monkeypatch):
    """80°N, 0°E in mid-January must return ~100% ice concentration."""
    fake_xr = types.ModuleType("xarray")
    fake_xr.open_dataset = MagicMock(return_value=_FakeDataset(100.0))
    monkeypatch.setitem(sys.modules, "xarray", fake_xr)

    val = osisaf.fetch_sea_ice_concentration(80.0, 0.0, date(2025, 1, 15))
    assert val is not None
    assert val == pytest.approx(100.0, abs=1e-6)


def test_open_dataset_failure_returns_none(monkeypatch):
    fake_xr = types.ModuleType("xarray")
    fake_xr.open_dataset = MagicMock(side_effect=OSError("opendap down"))
    monkeypatch.setitem(sys.modules, "xarray", fake_xr)

    val = osisaf.fetch_sea_ice_concentration(80.0, 0.0, date(2025, 1, 15))
    assert val is None


def test_out_of_range_value_is_rejected(monkeypatch):
    fake_xr = types.ModuleType("xarray")
    fake_xr.open_dataset = MagicMock(return_value=_FakeDataset(150.0))
    monkeypatch.setitem(sys.modules, "xarray", fake_xr)

    val = osisaf.fetch_sea_ice_concentration(80.0, 0.0, date(2025, 1, 15))
    assert val is None


def test_reproject_nh_grid():
    """Reprojection sanity: North Pole → ~(0, 0) in NH polar stereographic."""
    xy = osisaf._reproject(90.0, 0.0, "nh")
    assert xy is not None
    x, y = xy
    assert abs(x) < 1.0  # metres
    assert abs(y) < 1.0


def test_reproject_bering_is_finite():
    xy = osisaf._reproject(58.35, -169.98, "nh")
    assert xy is not None
    x, y = xy
    assert np.isfinite(x) and np.isfinite(y)
    # Bering Sea is far from the pole; expect |x|,|y| on the order of 1e6 m.
    assert 1e5 < abs(x) + abs(y) < 1e7
