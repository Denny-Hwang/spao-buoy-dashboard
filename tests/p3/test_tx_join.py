"""End-to-end join tests — TLE + Phase 1 rows → enriched frame."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from utils.p3 import tx_join
from utils.p3.sgp4_engine import parse_tle


IRIDIUM_TLE = [
    {"name": "IRIDIUM 106",
     "line1": "1 41917U 17003A   26090.16404766  .00000226  00000+0  73702-4 0  9996",
     "line2": "2 41917  86.3940 121.1858 0002524 100.6731 259.4749 14.34217814482022"},
    {"name": "IRIDIUM 103",
     "line1": "1 41918U 17003B   26090.15136786  .00000169  00000+0  53335-4 0  9996",
     "line2": "2 41918  86.3937 121.0910 0001952  95.0196 265.1223 14.34218625482047"},
]
GPS_TLE = [
    {"name": "GPS BIIR-2  (PRN 13)",
     "line1": "1 24876U 97035A   26111.86203664  .00000039  00000+0  00000+0 0  9997",
     "line2": "2 24876  55.9649 100.7759 0099717  56.1853 304.7536  2.00563807210829"},
    {"name": "GPS BIIR-5  (PRN 22)",
     "line1": "1 26407U 00040A   26111.46312530  .00000006  00000+0  00000+0 0  9992",
     "line2": "2 26407  54.8626 217.4146 0121925 302.4867  64.6587  2.00569369188819"},
]


def _sample_phase1_frame() -> pd.DataFrame:
    return pd.DataFrame([
        {"Timestamp": "2026-03-31T04:00:00Z",
         "Latitude": 46.28, "Longitude": -119.28,
         "RockBLOCK Time": 10.5, "Prev 2nd RB Time": 0.0,
         "GPS Time": 23.7, "Battery": 3.3},
        {"Timestamp": "2026-03-31T04:15:00Z",
         "Latitude": 0.0, "Longitude": 0.0,   # no-fix sentinel
         "RockBLOCK Time": 12.0, "Prev 2nd RB Time": 0.0,
         "GPS Time": 32.1, "Battery": 3.3},
    ])


def test_resolve_columns_detects_phase1():
    df = _sample_phase1_frame()
    cm = tx_join.resolve_columns(df)
    assert cm.time == "Timestamp"
    assert cm.lat == "Latitude"
    assert cm.lon == "Longitude"
    assert cm.rb1 == "RockBLOCK Time"
    assert cm.ready()


def test_enrich_adds_all_p3_columns():
    df = _sample_phase1_frame()
    iri = parse_tle(IRIDIUM_TLE)
    gps = parse_tle(GPS_TLE)
    enriched = tx_join.enrich_phase1_frame(df, iri, gps)
    for col in tx_join.P3_COLUMNS:
        assert col in enriched.columns
    # Row 0 has a valid fix → some numeric Iri visibility (0 or more).
    assert not pd.isna(enriched.loc[0, "IRI_N_VISIBLE"])
    # Row 1 is the no-fix sentinel → Iri columns remain NaN.
    assert pd.isna(enriched.loc[1, "IRI_N_VISIBLE"])


def test_enrich_is_non_destructive():
    df = _sample_phase1_frame()
    original_cols = set(df.columns)
    iri = parse_tle(IRIDIUM_TLE)
    gps = parse_tle(GPS_TLE)
    enriched = tx_join.enrich_phase1_frame(df, iri, gps)
    # Input frame must not change
    assert set(df.columns) == original_cols
    # Output is a superset, not a replacement
    assert original_cols.issubset(set(enriched.columns))


def test_enrich_empty_frame_is_safe():
    empty = pd.DataFrame(columns=["Timestamp", "Latitude", "Longitude"])
    out = tx_join.enrich_phase1_frame(empty, [], [])
    # Empty in, empty out with no crash.
    assert out is not None
    assert len(out) == 0
