"""Unit tests for ``utils.p2.sources.copernicus`` with a patched SDK."""

from __future__ import annotations

import os
import sys
import types
from datetime import date
from unittest.mock import MagicMock

import numpy as np
import pytest

from utils.p2.sources import copernicus  # noqa: E402


@pytest.fixture
def fake_sdk(monkeypatch):
    """Install a stub ``copernicusmarine`` module with a patchable open_dataset."""
    fake = types.ModuleType("copernicusmarine")
    fake.open_dataset = MagicMock()
    monkeypatch.setitem(sys.modules, "copernicusmarine", fake)
    return fake


@pytest.fixture(autouse=True)
def _with_creds(monkeypatch):
    monkeypatch.setenv("COPERNICUS_USERNAME", "demo-user")
    monkeypatch.setenv("COPERNICUS_PASSWORD", "demo-pass")
    monkeypatch.delenv("COPERNICUSMARINE_SERVICE_USERNAME", raising=False)
    monkeypatch.delenv("COPERNICUSMARINE_SERVICE_PASSWORD", raising=False)
    yield


def _make_dataset(sst_kelvin: float):
    """Build a mock xarray-like dataset returning ``sst_kelvin`` for any .sel."""
    ds = MagicMock()
    data_var = MagicMock()
    sel_result = MagicMock()
    sel_result.values = np.array(sst_kelvin, dtype=float)
    data_var.sel.return_value = sel_result
    ds.__getitem__.return_value = data_var
    ds.close = MagicMock()
    return ds


def test_ensure_credentials_maps_env(monkeypatch):
    monkeypatch.delenv("COPERNICUSMARINE_SERVICE_USERNAME", raising=False)
    monkeypatch.delenv("COPERNICUSMARINE_SERVICE_PASSWORD", raising=False)
    monkeypatch.setenv("COPERNICUS_USERNAME", "u")
    monkeypatch.setenv("COPERNICUS_PASSWORD", "p")
    copernicus._ensure_credentials()
    assert os.environ["COPERNICUSMARINE_SERVICE_USERNAME"] == "u"
    assert os.environ["COPERNICUSMARINE_SERVICE_PASSWORD"] == "p"


def test_ensure_credentials_raises_without_env(monkeypatch):
    monkeypatch.delenv("COPERNICUS_USERNAME", raising=False)
    monkeypatch.delenv("COPERNICUS_PASSWORD", raising=False)
    monkeypatch.delenv("COPERNICUSMARINE_SERVICE_USERNAME", raising=False)
    monkeypatch.delenv("COPERNICUSMARINE_SERVICE_PASSWORD", raising=False)
    with pytest.raises(RuntimeError) as excinfo:
        copernicus._ensure_credentials()
    msg = str(excinfo.value)
    # Helpful message that names the env var but never contains secret values.
    assert "COPERNICUS_USERNAME" in msg
    assert "demo-user" not in msg
    assert "demo-pass" not in msg


def test_fetch_ostia_point_happy(fake_sdk):
    fake_sdk.open_dataset.return_value = _make_dataset(284.32)  # K → 11.17 °C
    val = copernicus.fetch_ostia_point(58.35, -169.98, date(2025, 9, 9))
    assert val == pytest.approx(284.32 - 273.15, abs=1e-3)
    # open_dataset called with correct dataset id and a small bbox around point.
    args, kwargs = fake_sdk.open_dataset.call_args
    assert kwargs["dataset_id"] == copernicus.OSTIA_DATASET_ID
    assert kwargs["variables"] == [copernicus.OSTIA_VAR]
    assert kwargs["minimum_latitude"] < 58.35 < kwargs["maximum_latitude"]
    assert kwargs["minimum_longitude"] < -169.98 < kwargs["maximum_longitude"]


def test_fetch_ostia_point_kelvin_out_of_range(fake_sdk):
    fake_sdk.open_dataset.return_value = _make_dataset(100.0)  # impossible
    val = copernicus.fetch_ostia_point(58.35, -169.98, date(2025, 9, 9))
    assert val is None


def test_fetch_ostia_point_sdk_failure(fake_sdk):
    fake_sdk.open_dataset.side_effect = RuntimeError("auth failed")
    val = copernicus.fetch_ostia_point(58.35, -169.98, date(2025, 9, 9))
    assert val is None


def test_fetch_ostia_batch_groups_by_day(fake_sdk):
    fake_sdk.open_dataset.return_value = _make_dataset(283.65)  # ≈ 10.5 °C
    points = [
        (58.35, -169.98, date(2025, 9, 9)),
        (58.40, -169.95, date(2025, 9, 9)),
        (58.35, -169.98, date(2025, 9, 10)),
    ]
    out = copernicus.fetch_ostia_batch(points)
    # 3 points × 1 value each; 2 distinct days ⇒ 2 open_dataset calls.
    assert fake_sdk.open_dataset.call_count == 2
    for v in out.values():
        assert v == pytest.approx(10.5, abs=1e-2)


def test_fetch_ostia_batch_without_creds(monkeypatch, fake_sdk):
    monkeypatch.delenv("COPERNICUS_USERNAME", raising=False)
    monkeypatch.delenv("COPERNICUS_PASSWORD", raising=False)
    monkeypatch.delenv("COPERNICUSMARINE_SERVICE_USERNAME", raising=False)
    monkeypatch.delenv("COPERNICUSMARINE_SERVICE_PASSWORD", raising=False)
    points = [(58.35, -169.98, date(2025, 9, 9))]
    out = copernicus.fetch_ostia_batch(points)
    assert list(out.values()) == [None]
    fake_sdk.open_dataset.assert_not_called()


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("COPERNICUS_USERNAME"),
    reason="COPERNICUS_USERNAME not set",
)
def test_fetch_ostia_point_live():
    val = copernicus.fetch_ostia_point(58.35, -169.98, date(2025, 9, 9))
    assert val is None or (-3.0 < val < 30.0)
