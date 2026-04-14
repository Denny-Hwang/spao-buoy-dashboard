#!/usr/bin/env python3
"""
Backfill / cron entry point for Phase 2 enrichment.

Skeleton only — no real fetching yet. Parses CLI args, reads expected
environment variables, and prints what it *would* do, then exits 0.

Full implementation lands in PRs P2-1 through P2-4.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timezone


ALL_SOURCES = [
    "open_meteo_marine",
    "open_meteo_historical",
    "noaa_oisst",
    "mur_sst",
    "ostia",
    "oscar",
    "osi_saf_seaice",
]


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date '{s}' (expected YYYY-MM-DD)") from exc


def _parse_sources(s: str | None) -> list[str]:
    if not s:
        return list(ALL_SOURCES)
    return [tok.strip() for tok in s.split(",") if tok.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill Phase 2 enrichment columns into Google Sheets (skeleton).",
    )
    parser.add_argument("--start-date", type=_parse_date, default=None,
                        help="Inclusive start date (YYYY-MM-DD). Default: all missing rows.")
    parser.add_argument("--end-date", type=_parse_date, default=None,
                        help="Inclusive end date (YYYY-MM-DD). Default: now (UTC).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Do not write to Sheets; print intended actions only.")
    parser.add_argument("--sources", type=str, default=None,
                        help="Comma-separated subset of sources. Default: all.")
    args = parser.parse_args(argv)

    sources = _parse_sources(args.sources)
    unknown = [s for s in sources if s not in ALL_SOURCES]
    if unknown:
        print(f"[skeleton] unknown sources: {unknown}", file=sys.stderr)
        return 2

    # Surface configuration for visibility in CI logs; missing secrets
    # are non-fatal in the skeleton so smoke runs succeed in PRs.
    have_gcp = bool(os.environ.get("GCP_SERVICE_ACCOUNT_JSON"))
    sheet_id = os.environ.get("GOOGLE_SHEETS_ID", "")
    have_copernicus = bool(os.environ.get("COPERNICUS_USERNAME")) and bool(
        os.environ.get("COPERNICUS_PASSWORD")
    )

    now_utc = datetime.now(timezone.utc).isoformat()
    window = f"{args.start_date or 'ALL'} → {args.end_date or 'now'}"

    print(f"[skeleton] run at {now_utc}")
    print(f"[skeleton] window: {window}")
    print(f"[skeleton] sources: {sources}")
    print(f"[skeleton] dry_run={args.dry_run}")
    print(f"[skeleton] GCP_SERVICE_ACCOUNT_JSON present: {have_gcp}")
    print(f"[skeleton] GOOGLE_SHEETS_ID present: {bool(sheet_id)}")
    print(f"[skeleton] COPERNICUS creds present: {have_copernicus}")
    # Row count is unknown in the skeleton; print placeholder N.
    print(f"[skeleton] would enrich N rows for sources={sources}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
