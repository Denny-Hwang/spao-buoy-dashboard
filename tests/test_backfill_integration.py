"""
Integration tests for the backfill dispatcher.

The ``integration`` marker hits live external APIs (Open-Meteo, ERDDAP)
and is skipped in normal CI. Run locally with:

    pytest tests/test_backfill_integration.py -v -m integration
"""

from __future__ import annotations

import os

import pytest

from utils.p2.sources import erddap, open_meteo

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.environ.get("SPAO_RUN_INTEGRATION") != "1",
    reason="set SPAO_RUN_INTEGRATION=1 to hit live APIs",
)
def test_open_meteo_marine_live():
    df = open_meteo.fetch_marine_point(58.35, -169.98, "2025-09-09", "2025-09-09")
    assert not df.empty
    assert "wave_height" in df.columns


@pytest.mark.skipif(
    os.environ.get("SPAO_RUN_INTEGRATION") != "1",
    reason="set SPAO_RUN_INTEGRATION=1 to hit live APIs",
)
def test_erddap_oisst_live():
    val = erddap.fetch_oisst_point(58.35, -169.98, "2025-09-09")
    assert val is None or (-3.0 < val < 30.0)
