"""Unit tests for ``utils.p2.sources.erddap``."""

from __future__ import annotations

import pytest

requests_mock = pytest.importorskip("requests_mock")

from utils.p2.sources import erddap  # noqa: E402


OISST_PAYLOAD = {
    "table": {
        "columnNames": ["time", "zlev", "latitude", "longitude", "sst"],
        "columnTypes": ["String", "double", "double", "double", "double"],
        "rows": [["2025-09-09T00:00:00Z", 0.0, 58.375, -169.875, 9.81]],
    }
}

MUR_PAYLOAD_C = {
    "table": {
        "columnNames": ["time", "latitude", "longitude", "analysed_sst"],
        "rows": [["2025-09-09T09:00:00Z", 58.375, -169.975, 10.42]],
    }
}

MUR_PAYLOAD_K = {
    "table": {
        "columnNames": ["time", "latitude", "longitude", "analysed_sst"],
        "rows": [["2025-09-09T09:00:00Z", 58.375, -169.975, 283.57]],
    }
}

OSCAR_PAYLOAD = {
    "table": {
        "columnNames": ["time", "depth", "latitude", "longitude", "u", "v"],
        "rows": [["2025-09-09T00:00:00Z", 0.0, 58.375, -169.875, 0.123, -0.045]],
    }
}


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(erddap.time, "sleep", lambda *_a, **_k: None)
    yield


def test_fetch_oisst_point_happy():
    with requests_mock.Mocker() as m:
        m.get(requests_mock.ANY, json=OISST_PAYLOAD)
        val = erddap.fetch_oisst_point(58.35, -169.98, "2025-09-09")
    assert val == pytest.approx(9.81)


def test_fetch_oisst_point_404_returns_none():
    with requests_mock.Mocker() as m:
        m.get(requests_mock.ANY, status_code=404, text="no data")
        val = erddap.fetch_oisst_point(58.35, -169.98, "2025-09-09")
    assert val is None


def test_fetch_oisst_point_empty_rows():
    with requests_mock.Mocker() as m:
        m.get(requests_mock.ANY, json={"table": {"columnNames": ["sst"], "rows": []}})
        val = erddap.fetch_oisst_point(58.35, -169.98, "2025-09-09")
    assert val is None


def test_fetch_mur_point_celsius():
    with requests_mock.Mocker() as m:
        m.get(requests_mock.ANY, json=MUR_PAYLOAD_C)
        val = erddap.fetch_mur_sst_point(58.35, -169.98, "2025-09-09")
    assert val == pytest.approx(10.42)


def test_fetch_mur_point_kelvin_auto_convert():
    with requests_mock.Mocker() as m:
        m.get(requests_mock.ANY, json=MUR_PAYLOAD_K)
        val = erddap.fetch_mur_sst_point(58.35, -169.98, "2025-09-09")
    assert val is not None
    # 283.57 K → 10.42 °C
    assert val == pytest.approx(283.57 - 273.15, abs=1e-3)


def test_fetch_oscar_point_happy():
    with requests_mock.Mocker() as m:
        m.get(requests_mock.ANY, json=OSCAR_PAYLOAD)
        result = erddap.fetch_oscar_point(58.35, -169.98, "2025-09-09")
    assert result is not None
    u, v = result
    assert u == pytest.approx(0.123)
    assert v == pytest.approx(-0.045)


def test_fetch_oscar_point_404_returns_none():
    with requests_mock.Mocker() as m:
        m.get(requests_mock.ANY, status_code=404)
        result = erddap.fetch_oscar_point(58.35, -169.98, "2025-09-09")
    assert result is None


def test_fetch_oscar_point_retries_then_fails():
    with requests_mock.Mocker() as m:
        m.get(requests_mock.ANY, status_code=500)
        result = erddap.fetch_oscar_point(58.35, -169.98, "2025-09-09")
    assert result is None
