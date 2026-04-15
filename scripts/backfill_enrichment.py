#!/usr/bin/env python3
"""
Backfill / cron entry point for Phase 2 enrichment.

PR P2-1a wires in the free-tier sources (Open-Meteo Marine + Historical,
NOAA ERDDAP OISST/MUR/OSCAR). Copernicus OSTIA and OSI SAF sea ice are
added in P2-1b and P2-1c.

Workflow:
    1. Authenticate to Google Sheets from GCP_SERVICE_ACCOUNT_JSON.
    2. Read the target sheet as a DataFrame, locate Timestamp / lat / lon
       columns by common aliases.
    3. For each requested source, find rows whose ENRICH_FLAG bit is
       unset, group them by (snapped_lat, snapped_lon, date-bucket) to
       minimize API calls, fetch, and populate the enriched columns
       with scaled int values from ``utils.p2.schema``.
    4. OR the corresponding EnrichFlag bit into ENRICH_FLAG.
    5. Unless --dry-run, write the affected columns back to Sheets.
    6. Print a per-source summary to stdout (consumed by the GitHub
       Actions step summary).
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import sys
from datetime import date, datetime, timezone
from typing import Any, Callable

import pandas as pd

# Make repo-root imports work when invoked as a script.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from utils.p2.schema import ENRICHED_COLUMNS, EnrichFlag, encode_value  # noqa: E402
from utils.p2.sources.grid import snap, time_bucket  # noqa: E402

log = logging.getLogger("backfill")


ALL_SOURCES = [
    "open_meteo_marine",
    "open_meteo_historical",
    "noaa_oisst",
    "mur_sst",
    "ostia",
    "oscar",
    "osi_saf_seaice",
]

# Mapping source -> (flag bit, [columns filled], bucket, fetch-group fn).
SOURCE_FLAG_BITS: dict[str, EnrichFlag] = {
    "open_meteo_marine": EnrichFlag.WAVE,
    "open_meteo_historical": EnrichFlag.WIND | EnrichFlag.ERA5_ATMOS,
    "noaa_oisst": EnrichFlag.OISST,
    "mur_sst": EnrichFlag.MUR,
    "ostia": EnrichFlag.OSTIA,
    "oscar": EnrichFlag.OSCAR,
    "osi_saf_seaice": EnrichFlag.SEAICE,
}

SOURCE_COLUMNS: dict[str, list[str]] = {
    "open_meteo_marine": [
        "WAVE_H_cm", "WAVE_T_ds", "WAVE_DIR_deg",
        "SWELL_H_cm", "SWELL_T_ds",
    ],
    "open_meteo_historical": [
        "WIND_SPD_cms", "WIND_DIR_deg", "ERA5_PRES_dPa", "ERA5_AIRT_cC",
    ],
    "noaa_oisst": ["SAT_SST_OISST_cC"],
    "mur_sst": ["SAT_SST_MUR_cC"],
    "ostia": ["SAT_SST_OSTIA_cC"],
    "oscar": ["OSCAR_U_mms", "OSCAR_V_mms"],
    "osi_saf_seaice": ["SEAICE_CONC_pct"],
}

# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────
def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid date '{s}' (expected YYYY-MM-DD)"
        ) from exc


def _parse_sources(s: str | None) -> list[str]:
    if not s:
        return list(ALL_SOURCES)
    return [tok.strip() for tok in s.split(",") if tok.strip()]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Backfill Phase 2 enrichment columns into Google Sheets."
    )
    p.add_argument("--start-date", type=_parse_date, default=None,
                   help="Inclusive start date (YYYY-MM-DD). Default: all missing rows.")
    p.add_argument("--end-date", type=_parse_date, default=None,
                   help="Inclusive end date (YYYY-MM-DD). Default: now (UTC).")
    p.add_argument("--dry-run", action="store_true",
                   help="Do not write to Sheets; print intended actions only.")
    p.add_argument("--sources", type=str, default=None,
                   help="Comma-separated subset of sources. Default: all.")
    p.add_argument("--worksheet", type=str, default="Sheet1",
                   help="Target worksheet tab (default: Sheet1).")
    p.add_argument("--verbose", action="store_true",
                   help="Enable DEBUG-level logging.")
    return p.parse_args(argv)


# ──────────────────────────────────────────────────────────────────────
# DataFrame helpers
# ──────────────────────────────────────────────────────────────────────
_TIMESTAMP_ALIASES = ("Timestamp", "Receive Time", "Date Time (UTC)", "Date Time", "Time")
_LAT_ALIASES = ("Lat", "Latitude", "lat", "GPS Lat", "GPS_Lat")
_LON_ALIASES = ("Lon", "Lng", "Longitude", "lon", "GPS Lon", "GPS_Lon")


def _first_alias(df: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    for a in aliases:
        if a in df.columns:
            return a
    return None


def locate_geotemporal_columns(df: pd.DataFrame) -> tuple[str, str, str]:
    ts = _first_alias(df, _TIMESTAMP_ALIASES)
    lat = _first_alias(df, _LAT_ALIASES)
    lon = _first_alias(df, _LON_ALIASES)
    if ts is None or lat is None or lon is None:
        raise RuntimeError(
            f"Sheet missing geo/time columns: timestamp={ts}, lat={lat}, lon={lon}"
        )
    return ts, lat, lon


def _coerce_float(val: Any) -> float:
    try:
        f = float(val)
        if math.isnan(f):
            return float("nan")
        return f
    except (TypeError, ValueError):
        return float("nan")


def _coerce_ts(val: Any) -> pd.Timestamp:
    try:
        return pd.Timestamp(val, tz="UTC") if not pd.isna(val) else pd.NaT
    except Exception:
        return pd.NaT


def ensure_enrichment_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in ENRICHED_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    if "ENRICH_FLAG" not in df.columns:
        df["ENRICH_FLAG"] = 0
    return df


def rows_needing_source(df: pd.DataFrame, bit: EnrichFlag) -> pd.Index:
    def _missing(flag_val: Any) -> bool:
        try:
            return (int(flag_val or 0) & int(bit)) == 0
        except (TypeError, ValueError):
            return True
    mask = df["ENRICH_FLAG"].map(_missing)
    return df.index[mask]


def filter_by_window(
    df: pd.DataFrame,
    ts_col: str,
    start: date | None,
    end: date | None,
) -> pd.Index:
    if start is None and end is None:
        return df.index
    ts = pd.to_datetime(df[ts_col], errors="coerce", utc=True)
    mask = pd.Series(True, index=df.index)
    if start is not None:
        start_ts = pd.Timestamp(start, tz="UTC")
        mask &= ts >= start_ts
    if end is not None:
        end_ts = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
        mask &= ts < end_ts
    return df.index[mask]


# ──────────────────────────────────────────────────────────────────────
# Per-source enrichment
# ──────────────────────────────────────────────────────────────────────
def _group_rows(
    df: pd.DataFrame,
    rows: pd.Index,
    ts_col: str,
    lat_col: str,
    lon_col: str,
    bucket: str,
) -> dict[tuple[float, float, pd.Timestamp], list[int]]:
    groups: dict[tuple[float, float, pd.Timestamp], list[int]] = {}
    for idx in rows:
        lat = _coerce_float(df.at[idx, lat_col])
        lon = _coerce_float(df.at[idx, lon_col])
        ts = _coerce_ts(df.at[idx, ts_col])
        if math.isnan(lat) or math.isnan(lon) or pd.isna(ts):
            continue
        key = (snap(lat), snap(lon), time_bucket(ts, bucket))  # type: ignore[arg-type]
        groups.setdefault(key, []).append(idx)
    return groups


def _set_cells(df: pd.DataFrame, idxs: list[int], values: dict[str, Any]) -> None:
    for col, val in values.items():
        encoded = encode_value(col, val) if col in ENRICHED_COLUMNS else val
        for idx in idxs:
            df.at[idx, col] = encoded


def _or_flag(df: pd.DataFrame, idxs: list[int], bits: EnrichFlag) -> None:
    for idx in idxs:
        try:
            cur = int(df.at[idx, "ENRICH_FLAG"] or 0)
        except (TypeError, ValueError):
            cur = 0
        df.at[idx, "ENRICH_FLAG"] = cur | int(bits)


def enrich_open_meteo_marine(
    df: pd.DataFrame, rows: pd.Index, ts_col: str, lat_col: str, lon_col: str
) -> int:
    from utils.p2.sources.open_meteo import fetch_marine_point
    groups = _group_rows(df, rows, ts_col, lat_col, lon_col, bucket="H")
    filled = 0
    # Gather rows into (lat,lon,day) chunks so we can fetch a whole day at once.
    by_day: dict[tuple[float, float, pd.Timestamp], list[int]] = {}
    for (lat, lon, hour), idxs in groups.items():
        day_key = (lat, lon, hour.floor("D"))
        by_day.setdefault(day_key, []).extend(idxs)

    for (lat, lon, day), idxs in by_day.items():
        frame = fetch_marine_point(lat, lon, day, day)
        if frame is None or frame.empty:
            continue
        for idx in idxs:
            ts = _coerce_ts(df.at[idx, ts_col])
            if pd.isna(ts):
                continue
            hour = time_bucket(ts, "H")
            if hour not in frame.index:
                continue
            row = frame.loc[hour]
            _set_cells(df, [idx], {
                "WAVE_H_cm": row.get("wave_height"),
                "WAVE_T_ds": row.get("wave_period"),
                "WAVE_DIR_deg": row.get("wave_direction"),
                "SWELL_H_cm": row.get("swell_wave_height"),
                "SWELL_T_ds": row.get("swell_wave_period"),
            })
            _or_flag(df, [idx], EnrichFlag.WAVE)
            filled += 1
    return filled


def enrich_open_meteo_historical(
    df: pd.DataFrame, rows: pd.Index, ts_col: str, lat_col: str, lon_col: str
) -> int:
    from utils.p2.sources.open_meteo import fetch_historical_point
    groups = _group_rows(df, rows, ts_col, lat_col, lon_col, bucket="H")
    filled = 0
    by_day: dict[tuple[float, float, pd.Timestamp], list[int]] = {}
    for (lat, lon, hour), idxs in groups.items():
        day_key = (lat, lon, hour.floor("D"))
        by_day.setdefault(day_key, []).extend(idxs)

    for (lat, lon, day), idxs in by_day.items():
        frame = fetch_historical_point(lat, lon, day, day)
        if frame is None or frame.empty:
            continue
        for idx in idxs:
            ts = _coerce_ts(df.at[idx, ts_col])
            if pd.isna(ts):
                continue
            hour = time_bucket(ts, "H")
            if hour not in frame.index:
                continue
            row = frame.loc[hour]
            _set_cells(df, [idx], {
                "WIND_SPD_cms": row.get("wind_speed_10m"),
                "WIND_DIR_deg": row.get("wind_direction_10m"),
                "ERA5_PRES_dPa": row.get("surface_pressure"),
                "ERA5_AIRT_cC": row.get("temperature_2m"),
            })
            _or_flag(df, [idx], EnrichFlag.WIND | EnrichFlag.ERA5_ATMOS)
            filled += 1
    return filled


def enrich_erddap_point(
    df: pd.DataFrame,
    rows: pd.Index,
    ts_col: str,
    lat_col: str,
    lon_col: str,
    fetch: Callable,
    column: str,
    flag_bit: EnrichFlag,
) -> int:
    groups = _group_rows(df, rows, ts_col, lat_col, lon_col, bucket="D")
    filled = 0
    for (lat, lon, day), idxs in groups.items():
        val = fetch(lat=lat, lon=lon, d=day.date())
        if val is None:
            continue
        _set_cells(df, idxs, {column: val})
        _or_flag(df, idxs, flag_bit)
        filled += len(idxs)
    return filled


def enrich_oscar(
    df: pd.DataFrame, rows: pd.Index, ts_col: str, lat_col: str, lon_col: str
) -> int:
    from utils.p2.sources.erddap import fetch_oscar_point
    groups = _group_rows(df, rows, ts_col, lat_col, lon_col, bucket="D")
    filled = 0
    for (lat, lon, day), idxs in groups.items():
        result = fetch_oscar_point(lat, lon, day.date())
        if result is None:
            continue
        u, v = result
        _set_cells(df, idxs, {"OSCAR_U_mms": u, "OSCAR_V_mms": v})
        _or_flag(df, idxs, EnrichFlag.OSCAR)
        filled += len(idxs)
    return filled


def enrich_osi_saf_seaice(
    df: pd.DataFrame, rows: pd.Index, ts_col: str, lat_col: str, lon_col: str
) -> int:
    from utils.p2.sources.osisaf import fetch_sea_ice_concentration
    groups = _group_rows(df, rows, ts_col, lat_col, lon_col, bucket="D")
    filled = 0
    for (lat, lon, day), idxs in groups.items():
        val = fetch_sea_ice_concentration(lat, lon, day.date())
        if val is None:
            # Treat tropics as "0% with flag set" so we don't retry forever.
            if abs(float(lat)) < 40.0:
                _set_cells(df, idxs, {"SEAICE_CONC_pct": 0.0})
                _or_flag(df, idxs, EnrichFlag.SEAICE)
                filled += len(idxs)
            continue
        _set_cells(df, idxs, {"SEAICE_CONC_pct": val})
        _or_flag(df, idxs, EnrichFlag.SEAICE)
        filled += len(idxs)
    return filled


def enrich_ostia(
    df: pd.DataFrame, rows: pd.Index, ts_col: str, lat_col: str, lon_col: str
) -> int:
    from utils.p2.sources.copernicus import fetch_ostia_batch
    groups = _group_rows(df, rows, ts_col, lat_col, lon_col, bucket="D")
    if not groups:
        return 0
    points = [(lat, lon, day.date()) for (lat, lon, day) in groups.keys()]
    results = fetch_ostia_batch(points)
    filled = 0
    for (lat, lon, day), idxs in groups.items():
        key = (round(lat, 1), round(lon, 1), day.date().isoformat())
        val = results.get(key)
        if val is None:
            continue
        _set_cells(df, idxs, {"SAT_SST_OSTIA_cC": val})
        _or_flag(df, idxs, EnrichFlag.OSTIA)
        filled += len(idxs)
    return filled


SOURCE_DISPATCH: dict[str, Callable] = {}


def _register_default_dispatch() -> None:
    from utils.p2.sources.erddap import fetch_mur_sst_point, fetch_oisst_point

    SOURCE_DISPATCH["open_meteo_marine"] = enrich_open_meteo_marine
    SOURCE_DISPATCH["open_meteo_historical"] = enrich_open_meteo_historical
    SOURCE_DISPATCH["noaa_oisst"] = (
        lambda df, rows, ts, la, lo: enrich_erddap_point(
            df, rows, ts, la, lo, fetch_oisst_point, "SAT_SST_OISST_cC", EnrichFlag.OISST
        )
    )
    SOURCE_DISPATCH["mur_sst"] = (
        lambda df, rows, ts, la, lo: enrich_erddap_point(
            df, rows, ts, la, lo, fetch_mur_sst_point, "SAT_SST_MUR_cC", EnrichFlag.MUR
        )
    )
    SOURCE_DISPATCH["oscar"] = enrich_oscar
    SOURCE_DISPATCH["ostia"] = enrich_ostia
    SOURCE_DISPATCH["osi_saf_seaice"] = enrich_osi_saf_seaice


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────
def print_summary(header: str, stats: dict[str, int]) -> None:
    print(f"\n=== {header} ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _register_default_dispatch()

    sources = _parse_sources(args.sources)
    unknown = [s for s in sources if s not in ALL_SOURCES]
    if unknown:
        print(f"[error] unknown sources: {unknown}", file=sys.stderr)
        return 2
    requested = [s for s in sources if s in SOURCE_DISPATCH]
    skipped = [s for s in sources if s not in SOURCE_DISPATCH]
    if skipped:
        log.info("sources not implemented yet in P2-1a: %s", skipped)

    sheet_id = os.environ.get("GOOGLE_SHEETS_ID", "")
    now_utc = datetime.now(timezone.utc).isoformat()

    print(f"[backfill] run at {now_utc}")
    print(f"[backfill] sources active: {requested}")
    print(f"[backfill] sources skipped (later PR): {skipped}")
    print(f"[backfill] dry_run={args.dry_run}")
    print(f"[backfill] window: {args.start_date or 'ALL'} → {args.end_date or 'now'}")
    print(f"[backfill] worksheet: {args.worksheet}")

    if not sheet_id:
        print("[backfill] GOOGLE_SHEETS_ID not set — skipping Sheets I/O (local smoke mode).")
        if args.dry_run:
            return 0
        print("[error] cannot write without GOOGLE_SHEETS_ID", file=sys.stderr)
        return 3

    try:
        from utils.p2.sheets_io import (
            load_credentials_from_env,
            read_sheet_as_df,
            resolve_source_worksheets,
            write_enrichment_columns,
        )
    except Exception as exc:
        print(f"[error] failed to import sheets_io: {exc}", file=sys.stderr)
        return 4

    try:
        client = load_credentials_from_env()
    except RuntimeError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 5

    source_tabs = resolve_source_worksheets(client, sheet_id, args.worksheet)
    if not source_tabs:
        print(
            f"[error] source worksheet '{args.worksheet}' not found and no device tabs detected.",
            file=sys.stderr,
        )
        return 6
    if args.worksheet == "Sheet1" and source_tabs != ["Sheet1"]:
        print(f"[backfill] Sheet1 missing; auto-detected device tabs: {source_tabs}")

    grand_totals: dict[str, int] = {src: 0 for src in requested}
    tabs_processed = 0
    tabs_with_rows = 0

    for tab in source_tabs:
        print(f"\n[backfill] processing worksheet: {tab}")
        df = read_sheet_as_df(client, sheet_id, worksheet=tab)
        tabs_processed += 1
        if df.empty:
            print(f"[backfill] worksheet '{tab}' is empty — skipping.")
            continue
        tabs_with_rows += 1

        df = ensure_enrichment_columns(df)
        try:
            ts_col, lat_col, lon_col = locate_geotemporal_columns(df)
        except RuntimeError as exc:
            print(f"[error] worksheet '{tab}': {exc}", file=sys.stderr)
            continue
        window = filter_by_window(df, ts_col, args.start_date, args.end_date)

        total_stats: dict[str, int] = {}
        affected_columns: set[str] = set()
        for src in requested:
            bit = SOURCE_FLAG_BITS[src]
            cand = rows_needing_source(df.loc[window], bit)
            stats = {"candidates": len(cand)}
            if args.dry_run:
                groups = _group_rows(df, cand, ts_col, lat_col, lon_col,
                                     bucket="H" if src.startswith("open_meteo") else "D")
                stats["groups"] = len(groups)
                print(f"[dry-run] {tab}/{src}: would fetch {len(groups)} groups for {len(cand)} rows")
            else:
                filled = SOURCE_DISPATCH[src](df, cand, ts_col, lat_col, lon_col)
                stats["filled"] = filled
                affected_columns.update(SOURCE_COLUMNS.get(src, []))
                if filled:
                    affected_columns.add("ENRICH_FLAG")
            value = stats.get("filled", stats.get("groups", 0))
            total_stats[src] = value
            grand_totals[src] += value

        print_summary(f"enrichment stats ({tab})", total_stats)

        if args.dry_run:
            continue

        if affected_columns:
            cols = sorted(affected_columns)
            print(f"[backfill] writing columns back to '{tab}': {cols}")
            write_enrichment_columns(
                client, sheet_id, df, cols, worksheet=tab
            )
        else:
            print(f"[backfill] worksheet '{tab}': nothing to write.")

    print(f"\n[backfill] worksheets processed: {tabs_processed}, non-empty: {tabs_with_rows}")
    print_summary("enrichment stats (all worksheets)", grand_totals)

    if tabs_with_rows == 0:
        print("[backfill] all source worksheets are empty — nothing to do.")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
