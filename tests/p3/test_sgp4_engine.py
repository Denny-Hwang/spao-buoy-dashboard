"""Sanity tests for the Phase 3 SGP4 wrapper.

Uses a pair of Iridium TLEs from the HTML prototype so we have a
known-good fixture that does not depend on a live CelesTrak fetch.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from utils.p3 import sgp4_engine as sgp


IRIDIUM_TLE = [
    {"name": "IRIDIUM 106",
     "line1": "1 41917U 17003A   26090.16404766  .00000226  00000+0  73702-4 0  9996",
     "line2": "2 41917  86.3940 121.1858 0002524 100.6731 259.4749 14.34217814482022"},
    {"name": "IRIDIUM 103",
     "line1": "1 41918U 17003B   26090.15136786  .00000169  00000+0  53335-4 0  9996",
     "line2": "2 41918  86.3937 121.0910 0001952  95.0196 265.1223 14.34218625482047"},
]


def test_parse_tle_returns_sat_records():
    sats = sgp.parse_tle(IRIDIUM_TLE)
    assert len(sats) == 2
    assert sats[0].name == "IRIDIUM 106"
    assert sats[0].sr is not None


def test_propagate_returns_reasonable_altitude():
    sats = sgp.parse_tle(IRIDIUM_TLE)
    dt = datetime(2026, 3, 31, 4, 0, tzinfo=timezone.utc)
    pv = sgp.propagate(sats[0], dt)
    assert pv is not None
    r, v = pv
    # Iridium NEXT orbits at ~781 km altitude; position magnitude ~= Re + 781.
    mag = math.sqrt(float(r[0])**2 + float(r[1])**2 + float(r[2])**2)
    assert 6800.0 < mag < 7400.0


def test_look_angles_roundtrip():
    sats = sgp.parse_tle(IRIDIUM_TLE)
    # Observer at Richland, WA — bound on realistic elevations.
    dt = datetime(2026, 3, 31, 4, 0, tzinfo=timezone.utc)
    la = sgp.look_angles(sats[0], dt, 46.28, -119.28)
    assert la is not None
    assert -90.0 <= la.el_deg <= 90.0
    assert 0.0 <= la.az_deg < 360.0
    assert la.range_km > 500.0  # can't be closer than horizon-hugging


def test_sky_positions_visibility_flag():
    sats = sgp.parse_tle(IRIDIUM_TLE)
    dt = datetime(2026, 3, 31, 4, 0, tzinfo=timezone.utc)
    df = sgp.sky_positions(sats, dt, 46.28, -119.28, min_el_deg=8.2)
    # We always get 2 rows (both propagations succeed); visibility is a flag.
    assert len(df) == 2
    assert df["visible"].dtype == bool


def test_visibility_radius_km_reasonable():
    # At 0° elevation with Iridium altitude, horizon radius should be
    # in the ballpark of the great-circle distance ≈ 2500–3000 km.
    r = sgp.visibility_radius_km(0.0, 781.0)
    assert 2000.0 < r < 3500.0
