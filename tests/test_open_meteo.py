"""Unit tests for ``utils.p2.sources.open_meteo`` using requests_mock."""

from __future__ import annotations

import pandas as pd
import pytest

requests_mock = pytest.importorskip("requests_mock")

from utils.p2.sources import open_meteo as om  # noqa: E402


MARINE_SAMPLE = {
    "latitude": 58.35,
    "longitude": -169.98,
    "generationtime_ms": 1.2,
    "utc_offset_seconds": 0,
    "timezone": "UTC",
    "hourly_units": {
        "wave_height": "m", "wave_period": "s", "wave_direction": "°",
        "wind_wave_height": "m", "wind_wave_period": "s",
        "swell_wave_height": "m", "swell_wave_period": "s",
        "sea_surface_temperature": "°C",
    },
    "hourly": {
        "time": [
            "2025-09-09T00:00", "2025-09-09T01:00", "2025-09-09T02:00",
        ],
        "wave_height": [1.2, 1.3, 1.4],
        "wave_period": [7.5, 7.6, 7.7],
        "wave_direction": [220.0, 222.0, 224.0],
        "wind_wave_height": [0.6, 0.6, 0.7],
        "wind_wave_period": [4.5, 4.4, 4.3],
        "swell_wave_height": [1.0, 1.0, 1.1],
        "swell_wave_period": [11.0, 11.0, 11.1],
        "sea_surface_temperature": [10.1, 10.2, 10.3],
    },
}


HISTORICAL_SAMPLE = {
    "latitude": 58.35,
    "longitude": -169.98,
    "timezone": "UTC",
    "hourly": {
        "time": [
            "2025-09-09T00:00", "2025-09-09T01:00",
        ],
        "temperature_2m": [8.5, 8.4],
        "relative_humidity_2m": [85, 87],
        "surface_pressure": [1013.2, 1013.1],
        "wind_speed_10m": [6.1, 6.3],
        "wind_direction_10m": [210, 212],
    },
}


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(om.time, "sleep", lambda *_a, **_k: None)
    yield


def test_fetch_marine_point_happy_path():
    with requests_mock.Mocker() as m:
        m.get(om.MARINE_URL, json=MARINE_SAMPLE)
        df = om.fetch_marine_point(58.35, -169.98, "2025-09-09", "2025-09-09")
    assert not df.empty
    assert df.index.tz is not None
    assert "wave_height" in df.columns
    assert df["wave_height"].iloc[0] == pytest.approx(1.2)
    assert df["swell_wave_height"].iloc[-1] == pytest.approx(1.1)
    # Index is monotonic UTC.
    assert df.index.is_monotonic_increasing


def test_fetch_historical_point_happy_path():
    with requests_mock.Mocker() as m:
        m.get(om.ARCHIVE_URL, json=HISTORICAL_SAMPLE)
        df = om.fetch_historical_point(58.35, -169.98, "2025-09-09", "2025-09-09")
    assert not df.empty
    assert df["temperature_2m"].iloc[0] == pytest.approx(8.5)
    assert df["wind_direction_10m"].iloc[1] == 212


def test_fetch_marine_retries_on_429():
    responses = [
        {"status_code": 429, "json": {}},
        {"status_code": 429, "json": {}},
        {"status_code": 200, "json": MARINE_SAMPLE},
    ]
    with requests_mock.Mocker() as m:
        m.get(om.MARINE_URL, response_list=responses)
        df = om.fetch_marine_point(1, 2, "2025-09-09", "2025-09-09")
    assert not df.empty
    assert len(df) == 3


def test_fetch_marine_persistent_429_returns_empty():
    with requests_mock.Mocker() as m:
        m.get(om.MARINE_URL, status_code=429, json={})
        df = om.fetch_marine_point(1, 2, "2025-09-09", "2025-09-09")
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_fetch_marine_5xx_returns_empty():
    with requests_mock.Mocker() as m:
        m.get(om.MARINE_URL, status_code=503, text="upstream error")
        df = om.fetch_marine_point(1, 2, "2025-09-09", "2025-09-09")
    assert df.empty


def test_fetch_marine_empty_payload_returns_empty():
    with requests_mock.Mocker() as m:
        m.get(om.MARINE_URL, json={"latitude": 1, "longitude": 2})
        df = om.fetch_marine_point(1, 2, "2025-09-09", "2025-09-09")
    assert df.empty


def test_fetch_marine_bad_json_returns_empty():
    with requests_mock.Mocker() as m:
        m.get(om.MARINE_URL, text="not json at all")
        df = om.fetch_marine_point(1, 2, "2025-09-09", "2025-09-09")
    assert df.empty


# ─── Open-Meteo unified SST fetcher (marine → land fallback) ──────────
_MARINE_SST_ONLY = {
    "hourly": {
        "time": ["2025-09-09T00:00", "2025-09-09T01:00"],
        "sea_surface_temperature": [10.1, 10.2],
    },
}

_LAND_SOIL_ONLY = {
    "hourly": {
        "time": ["2025-09-09T00:00", "2025-09-09T01:00"],
        "soil_temperature_0cm": [18.5, 18.9],
    },
}

_MARINE_ALL_NAN = {
    "hourly": {
        "time": ["2025-09-09T00:00", "2025-09-09T01:00"],
        "sea_surface_temperature": [None, None],
    },
}


def test_openmeteo_sst_prefers_marine_when_present():
    with requests_mock.Mocker() as m:
        m.get(om.MARINE_URL, json=_MARINE_SST_ONLY)
        m.get(om.ARCHIVE_URL, json=_LAND_SOIL_ONLY)
        df = om.fetch_openmeteo_sst_point(0.0, 0.0, "2025-09-09", "2025-09-09")
    assert list(df.columns) == ["sst_c"]
    # Marine takes priority wherever it is non-NaN.
    assert df["sst_c"].iloc[0] == pytest.approx(10.1)
    assert df["sst_c"].iloc[1] == pytest.approx(10.2)


def test_openmeteo_sst_falls_back_to_land_soil_temperature():
    with requests_mock.Mocker() as m:
        m.get(om.MARINE_URL, json=_MARINE_ALL_NAN)
        m.get(om.ARCHIVE_URL, json=_LAND_SOIL_ONLY)
        df = om.fetch_openmeteo_sst_point(46.3, -119.3, "2025-09-09", "2025-09-09")
    assert not df.empty
    assert df["sst_c"].iloc[0] == pytest.approx(18.5)
    assert df["sst_c"].iloc[1] == pytest.approx(18.9)


def test_openmeteo_sst_both_empty_returns_empty_frame():
    with requests_mock.Mocker() as m:
        m.get(om.MARINE_URL, status_code=503, text="down")
        m.get(om.ARCHIVE_URL, status_code=503, text="down")
        df = om.fetch_openmeteo_sst_point(0.0, 0.0, "2025-09-09", "2025-09-09")
    assert df.empty
