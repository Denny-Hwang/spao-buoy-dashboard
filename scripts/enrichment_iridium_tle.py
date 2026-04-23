#!/usr/bin/env python3
"""Fetch Iridium + GPS TLEs from CelesTrak and write them to Google Sheets.

Runs from GitHub Actions every 6 hours (see
``.github/workflows/enrichment_iridium_tle.yml``). The workflow passes
``GCP_SERVICE_ACCOUNT_JSON`` / ``GOOGLE_SHEETS_ID`` as env vars; this
script authenticates to gspread, replaces the ``_iridium_tle`` and
``_gps_tle`` tabs, and prints a one-line summary that GitHub Actions
renders in the job summary.

Design notes
~~~~~~~~~~~~
* We always write **full** tabs (header + rows) rather than
  incremental updates, because TLE tabs are small (<200 rows) and
  gspread's batch ``update`` is dramatically simpler and safer than
  row-level diffs.
* We request both ``iridium-NEXT`` and ``iridium`` groups and merge by
  NORAD ID (newest epoch wins) so legacy (pre-NEXT) satellites that
  are still on-orbit don't disappear.
* Dry-run mode (``--dry-run``) performs the fetch + parse and prints
  what would be written, but does NOT touch Sheets. Useful for
  ad-hoc workflow_dispatch debugging.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils.p3.tle_io import (  # noqa: E402
    CELESTRAK_GPS_OPS,
    CELESTRAK_IRIDIUM_LEGACY,
    CELESTRAK_IRIDIUM_NEXT,
    SHEET_COLUMNS,
    TAB_GPS,
    TAB_IRIDIUM,
    build_sheet_rows,
    fetch_celestrak_tle,
    parse_tle_text,
)

log = logging.getLogger("p3.tle.cron")


# ── Fetchers ──────────────────────────────────────────────────────
def fetch_iridium() -> tuple[list[dict], str]:
    """Fetch iridium-NEXT + legacy iridium, merge by NORAD ID."""
    text_next = fetch_celestrak_tle(CELESTRAK_IRIDIUM_NEXT)
    try:
        text_legacy = fetch_celestrak_tle(CELESTRAK_IRIDIUM_LEGACY)
    except Exception as exc:  # noqa: BLE001 — legacy URL sometimes 404s
        log.warning("iridium legacy fetch failed (%s); continuing with NEXT only", exc)
        text_legacy = ""
    combined = text_next + "\n" + text_legacy
    return parse_tle_text(combined), CELESTRAK_IRIDIUM_NEXT


def fetch_gps() -> tuple[list[dict], str]:
    """Fetch gps-ops."""
    text = fetch_celestrak_tle(CELESTRAK_GPS_OPS)
    return parse_tle_text(text), CELESTRAK_GPS_OPS


# ── Sheets write ──────────────────────────────────────────────────
def _gspread_client():
    """Authenticate using ``GCP_SERVICE_ACCOUNT_JSON`` env var."""
    import gspread
    from google.oauth2.service_account import Credentials

    raw = os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise SystemExit("GCP_SERVICE_ACCOUNT_JSON env var is required")
    info = json.loads(raw)
    creds = Credentials.from_service_account_info(
        info,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    return gspread.authorize(creds)


def _replace_tab(sheet, tab: str, rows: list[list[str]]) -> None:
    """Replace the contents of ``tab`` with ``rows`` (header first).

    Creates the tab if it doesn't exist. Always clears first so we
    don't leave stale rows when the constellation shrinks.
    """
    try:
        ws = sheet.worksheet(tab)
    except Exception:  # noqa: BLE001 — WorksheetNotFound
        ws = sheet.add_worksheet(title=tab, rows="200", cols=str(len(SHEET_COLUMNS)))
    ws.clear()
    if rows:
        ws.update(rows, value_input_option="RAW")


# ── Entry point ───────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch & parse only; do not write to Sheets.")
    parser.add_argument("--sheet-id", default=os.environ.get("GOOGLE_SHEETS_ID"),
                        help="Target spreadsheet ID (default: env GOOGLE_SHEETS_ID).")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    now = datetime.now(timezone.utc)

    iri_records, iri_url = fetch_iridium()
    gps_records, gps_url = fetch_gps()

    log.info("Fetched Iridium: %d sats, GPS: %d sats",
             len(iri_records), len(gps_records))

    iri_rows = build_sheet_rows(iri_records, iri_url, fetched_at=now)
    gps_rows = build_sheet_rows(gps_records, gps_url, fetched_at=now)

    if args.dry_run:
        log.info("DRY-RUN — skipping Sheets write. "
                 "First Iridium row: %s", iri_rows[1] if len(iri_rows) > 1 else "(none)")
        return 0

    if not args.sheet_id:
        raise SystemExit("GOOGLE_SHEETS_ID env or --sheet-id is required for non-dry-run")

    client = _gspread_client()
    sheet = client.open_by_key(args.sheet_id)
    _replace_tab(sheet, TAB_IRIDIUM, iri_rows)
    _replace_tab(sheet, TAB_GPS, gps_rows)

    # GitHub Actions step summary line.
    print(f"::notice::Phase 3 TLE written — "
          f"Iridium={len(iri_records)} sats, GPS={len(gps_records)} sats")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
