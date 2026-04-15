#!/usr/bin/env python3
"""
Compute Phase 2 Derived_Daily aggregation and upsert to Google Sheets.

Usage (cron):
    python scripts/compute_daily_derived.py \
        --start-date 2025-09-09 --end-date 2025-09-15

Defaults to the last 7 days (UTC). The script is idempotent — rerunning
it for overlapping dates overwrites the previously-written rows.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

import pandas as pd

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from utils.p2.derived import (  # noqa: E402
    DERIVED_DAILY_COLUMNS,
    DERIVED_DAILY_WORKSHEET,
    compute_daily_table,
)

log = logging.getLogger("compute_daily_derived")


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid date '{s}' (expected YYYY-MM-DD)"
        ) from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Compute Derived_Daily aggregation and upsert to Sheets."
    )
    p.add_argument("--start-date", type=_parse_date, default=None,
                   help="Inclusive start date (YYYY-MM-DD). Default: 7 days ago.")
    p.add_argument("--end-date", type=_parse_date, default=None,
                   help="Inclusive end date (YYYY-MM-DD). Default: today.")
    p.add_argument("--dry-run", action="store_true",
                   help="Compute and print the table without writing to Sheets.")
    p.add_argument("--worksheet-source", default="Sheet1",
                   help="Source worksheet tab name (default: Sheet1).")
    p.add_argument("--worksheet-dest", default=DERIVED_DAILY_WORKSHEET,
                   help=f"Destination worksheet (default: {DERIVED_DAILY_WORKSHEET}).")
    p.add_argument("--verbose", action="store_true", help="DEBUG-level logging.")
    return p.parse_args(argv)


def default_window() -> tuple[date, date]:
    today = datetime.now(timezone.utc).date()
    return today - timedelta(days=7), today


def filter_window(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    if "Timestamp" in df.columns:
        ts_col = "Timestamp"
    elif "Receive Time" in df.columns:
        ts_col = "Receive Time"
    else:
        return df
    ts = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
    mask = (ts >= pd.Timestamp(start, tz="UTC")) & (
        ts < pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
    )
    return df.loc[mask].copy()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    start, end = args.start_date, args.end_date
    if start is None and end is None:
        start, end = default_window()
    elif start is None:
        start = end - timedelta(days=7)
    elif end is None:
        end = start + timedelta(days=7)

    if start > end:
        print(f"[error] start-date {start} > end-date {end}", file=sys.stderr)
        return 2

    sheet_id = os.environ.get("GOOGLE_SHEETS_ID", "")
    print(f"[derived] window: {start} → {end}")
    print(f"[derived] dry_run={args.dry_run}")
    print(f"[derived] source tab: {args.worksheet_source}")
    print(f"[derived] dest tab:   {args.worksheet_dest}")
    print(f"[derived] GOOGLE_SHEETS_ID present: {bool(sheet_id)}")

    if not sheet_id:
        print("[derived] GOOGLE_SHEETS_ID not set — cannot read input sheet.")
        return 0 if args.dry_run else 3

    try:
        from utils.p2.sheets_io import (
            load_credentials_from_env,
            read_sheet_as_df,
            resolve_source_worksheets,
        )
    except Exception as exc:
        print(f"[error] failed to import sheets_io: {exc}", file=sys.stderr)
        return 4

    try:
        client = load_credentials_from_env()
    except RuntimeError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 5

    source_tabs = resolve_source_worksheets(client, sheet_id, args.worksheet_source)
    if not source_tabs:
        print(
            f"[error] source worksheet '{args.worksheet_source}' not found and no device tabs detected.",
            file=sys.stderr,
        )
        return 6
    if args.worksheet_source == "Sheet1" and source_tabs != ["Sheet1"]:
        print(f"[derived] Sheet1 missing; auto-detected device tabs: {source_tabs}")

    frames: list[pd.DataFrame] = []
    for tab in source_tabs:
        tab_df = read_sheet_as_df(client, sheet_id, worksheet=tab)
        if tab_df.empty:
            print(f"[derived] source worksheet '{tab}' is empty — skipping.")
            continue
        tab_df = tab_df.copy()
        tab_df["Device Tab"] = tab
        frames.append(tab_df)

    if not frames:
        print("[derived] all source worksheets are empty — nothing to compute.")
        return 0
    df = pd.concat(frames, ignore_index=True)
    print(f"[derived] loaded {len(df)} rows from {len(frames)} source worksheets")

    window_df = filter_window(df, start, end)
    daily = compute_daily_table(window_df)
    print(f"[derived] computed {len(daily)} daily rows")
    if args.verbose or args.dry_run:
        print(daily.to_string(index=False))

    if args.dry_run:
        print("[dry-run] not writing to Sheets.")
        return 0

    try:
        from utils.p2.derived_io import write_derived_daily
    except Exception as exc:
        print(f"[error] failed to import derived_io: {exc}", file=sys.stderr)
        return 6

    written = write_derived_daily(
        sheet_id=sheet_id, df=daily, worksheet=args.worksheet_dest,
    )
    print(f"[derived] wrote {written} rows to {args.worksheet_dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
