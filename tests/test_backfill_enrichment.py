from __future__ import annotations

import pandas as pd

from scripts.backfill_enrichment import _group_rows, locate_geotemporal_columns


def test_locate_geotemporal_columns_accepts_degree_variants():
    df = pd.DataFrame(
        {
            "Date Time (UTC)": ["2026-04-15 00:00:00"],
            "Latitude (deg)": [46.36],
            "Longitude (deg)": [-119.27],
        }
    )
    ts, lat, lon = locate_geotemporal_columns(df)
    assert ts == "Date Time (UTC)"
    assert lat == "Latitude (deg)"
    assert lon == "Longitude (deg)"


def test_group_rows_skips_zero_zero_gps_fix():
    df = pd.DataFrame(
        {
            "Receive Time": ["2026-04-15 00:00:00", "2026-04-15 01:00:00"],
            "Lat (°)": [0.0, 46.36],
            "Lon (°)": [0.0, -119.27],
        }
    )
    groups = _group_rows(
        df=df,
        rows=df.index,
        ts_col="Receive Time",
        lat_col="Lat (°)",
        lon_col="Lon (°)",
        bucket="H",
    )
    # First row should be skipped because (0, 0) is an invalid GPS fix.
    assert sum(len(v) for v in groups.values()) == 1
