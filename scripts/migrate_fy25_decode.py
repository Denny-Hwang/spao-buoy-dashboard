#!/usr/bin/env python3
"""One-shot FY25 raw → decoded sheet migration.

FY25 is historical data that will not receive any more updates. Storing
it as RockBLOCK raw CSV means every Streamlit page re-decodes on the fly
and every Phase 2 cron job has to apply special-case parsing for the
compound ``Approx Lat/Lng`` column, FY25-only timestamp field, etc.

This script rewrites each FY25 worksheet in place to the same
"webhook_decoded" schema used by FY26 tabs. After migration:

  * Phase 1 pages continue to work (``read_and_decode_sheet`` still
    re-decodes from ``Raw Hex`` regardless).
  * Phase 2 cron reads clean ``GPS Latitude`` / ``GPS Longitude`` columns
    without needing ``_split_compound_latlon``.
  * Operators can inspect decoded values directly in the sheet.

Safety:

  * A backup worksheet ``{tab}__pre_decode_backup`` is created before any
    rewrite. If the backup write fails, the original is not touched.
  * Idempotent — tabs whose first header is already ``Receive Time`` are
    skipped.
  * A decode-failure threshold (5%) aborts the rewrite before any write
    so a misidentified tab cannot be destroyed.
  * ``--dry-run`` (default in the companion GitHub Actions workflow)
    prints a sample without touching the sheet.

Usage::

    python scripts/migrate_fy25_decode.py --all-fy25 --dry-run
    python scripts/migrate_fy25_decode.py --tab FY25_Bearing_sea_RB_220835
    python scripts/migrate_fy25_decode.py --all-fy25   # real rewrite
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any

# Make repo-root imports work when invoked as a script.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from utils.decoders import auto_detect_and_decode  # noqa: E402
from utils.p2.schema import ENRICH_COLUMN_ORDER  # noqa: E402
from utils.p2.sheets_io import (  # noqa: E402
    _with_quota_retries,
    load_credentials_from_env,
)

log = logging.getLogger("migrate_fy25")

# Prefix used to detect FY25 tabs. Kept as a tuple so we can extend later
# if the deployment naming convention changes.
FY25_TAB_PREFIXES = ("FY25_",)

# Backup tab suffix. A counter is appended if it already exists so
# re-running after a partial failure does not clobber an earlier backup.
BACKUP_SUFFIX = "__pre_decode_backup"

# Abort the rewrite if more than this fraction of rows fail to decode —
# a good canary against rewriting a tab that is not actually FY25 raw.
DECODE_FAILURE_THRESHOLD = 0.05

# Final column layout written to the migrated FY25 tab. The order puts
# metadata first, decoded sensors next, operator Notes, then the Phase 2
# enrichment columns (blank — filled in by the next cron run), and
# finally Raw Hex as the last column (matches the rest of the workbook).
METADATA_COLUMNS = [
    "Receive Time",
    "Transmit Time",
    "IMEI",
    "MOMSN",
    "Packet Ver",
    "Bytes",
    "CRC Valid",
]

DECODED_SENSOR_COLUMNS = [
    "TENG Current Avg",
    "Prev 2nd RB Time",
    "Prev GPS Time",
    "Prev SuperCap Init",
    "Prev SuperCap 1st F",
    "Prev SuperCap after TX",
    "Battery",
    "GPS Latitude",
    "GPS Longitude",
    "GPS Acq Time",
    "Pressure",
    "Internal Temp",
    "Humidity",
    "SST",
    "SuperCap Voltage",
]


def build_new_header() -> list[str]:
    """Return the final column order written to migrated FY25 tabs."""
    return (
        METADATA_COLUMNS
        + DECODED_SENSOR_COLUMNS
        + ["Notes"]
        + list(ENRICH_COLUMN_ORDER)
        + ["Raw Hex"]
    )


# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="One-shot FY25 raw-to-decoded sheet migration.",
    )
    group = p.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "--tab",
        default="",
        help="Single worksheet to migrate (e.g. FY25_Bearing_sea_RB_220835).",
    )
    group.add_argument(
        "--all-fy25",
        action="store_true",
        help="Migrate every tab whose name starts with 'FY25_'.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write to Sheets; print sample rows and stats only.",
    )
    p.add_argument(
        "--sheet-id",
        default=os.environ.get("GOOGLE_SHEETS_ID", ""),
        help="Override the spreadsheet ID (default: $GOOGLE_SHEETS_ID).",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    return p.parse_args(argv)


# ──────────────────────────────────────────────────────────────────────
# Detection / validation
# ──────────────────────────────────────────────────────────────────────
def is_already_migrated(header: list[str]) -> bool:
    """True if the worksheet header already uses the decoded schema."""
    return bool(header) and header[0].strip() == "Receive Time"


def is_fy25_raw(header: list[str]) -> bool:
    """True if the header looks like an FY25 RockBLOCK CSV export."""
    if not header:
        return False
    first = header[0].strip()
    header_set = {h.strip() for h in header if h}
    if first not in ("Date Time (UTC)", "Date Time"):
        return False
    return "Payload" in header_set


def _pick_timestamp(record: dict[str, Any]) -> str:
    return str(record.get("Date Time (UTC)", record.get("Date Time", ""))).strip()


def _pick_payload(record: dict[str, Any]) -> str:
    raw = str(record.get("Payload", "")).strip()
    return raw.replace(" ", "").replace("0x", "").replace("0X", "")


def _pick_device(record: dict[str, Any]) -> str:
    return str(record.get("Device", "")).strip()


def _field_lookup(fields: list[dict[str, Any]]) -> dict[str, Any]:
    """Map decoder ``field.name`` → decoded ``value`` for quick access."""
    out: dict[str, Any] = {}
    for f in fields:
        out[f["name"]] = f.get("value")
    return out


def build_decoded_row(record: dict[str, Any]) -> dict[str, Any] | None:
    """Turn one raw FY25 CSV record into a dict keyed by the new header.

    Returns ``None`` if the Payload cell is empty or fails to decode.
    The returned dict always contains every column in :func:`build_new_header`
    (Phase 2 enrichment columns and MOMSN are blank strings).
    """
    hex_str = _pick_payload(record)
    if not hex_str:
        return None

    result = auto_detect_and_decode(hex_str)
    if not result or result.get("error") or not result.get("fields"):
        return None

    timestamp = _pick_timestamp(record)
    device = _pick_device(record)
    field_values = _field_lookup(result["fields"])

    row: dict[str, Any] = {col: "" for col in build_new_header()}
    # Metadata
    row["Receive Time"] = timestamp
    # Per the user's choice: FY25 lacks a separate transmit time, so
    # mirror Receive Time into Transmit Time.
    row["Transmit Time"] = timestamp
    row["IMEI"] = device
    row["MOMSN"] = ""
    row["Packet Ver"] = result.get("version", "FY25")
    row["Bytes"] = result.get("byte_len", len(hex_str) // 2)
    row["CRC Valid"] = bool(result.get("crc_ok", False))

    # Decoded sensors — use the decoder field names verbatim.
    for col in DECODED_SENSOR_COLUMNS:
        if col in field_values and field_values[col] is not None:
            row[col] = field_values[col]

    # Preserve an existing Notes cell, if any.
    note = record.get("Notes", "")
    if note is not None and str(note).strip():
        row["Notes"] = str(note)

    row["Raw Hex"] = hex_str
    return row


# ──────────────────────────────────────────────────────────────────────
# Worksheet helpers
# ──────────────────────────────────────────────────────────────────────
def discover_fy25_tabs(sh) -> list[str]:
    worksheets = _with_quota_retries(sh.worksheets, op="worksheets()")
    titles = [ws.title for ws in worksheets]
    return [t for t in titles if any(t.startswith(p) for p in FY25_TAB_PREFIXES)]


def _unique_backup_title(sh, base_title: str) -> str:
    existing = {
        ws.title
        for ws in _with_quota_retries(sh.worksheets, op="worksheets(backup)")
    }
    candidate = f"{base_title}{BACKUP_SUFFIX}"
    if candidate not in existing:
        return candidate
    i = 2
    while f"{candidate}_{i}" in existing:
        i += 1
    return f"{candidate}_{i}"


def create_backup(sh, ws, header: list[str], rows: list[list[Any]]) -> str:
    """Create a new worksheet that duplicates the original raw content.

    Returns the backup worksheet title. Raises if any step fails — the
    caller must abort the rewrite without touching the original tab.
    """
    title = _unique_backup_title(sh, ws.title)
    n_rows = len(rows) + 1  # +1 header
    n_cols = max(len(header), 1)
    backup_ws = _with_quota_retries(
        lambda: sh.add_worksheet(title=title, rows=n_rows, cols=n_cols),
        op=f"add_worksheet({title})",
    )
    payload = [header] + rows
    _with_quota_retries(
        lambda: backup_ws.update(range_name="A1", values=payload),
        op=f"backup_update({title})",
    )
    log.info("Backup worksheet created: %s (%d rows)", title, len(rows))
    return title


def rewrite_worksheet(ws, new_header: list[str], new_rows: list[list[Any]]) -> None:
    """Replace the worksheet contents with the new header + rows."""
    _with_quota_retries(ws.clear, op=f"clear({ws.title})")
    payload = [new_header] + new_rows
    _with_quota_retries(
        lambda: ws.update(range_name="A1", values=payload),
        op=f"rewrite_update({ws.title})",
    )
    log.info("Rewrote %s with %d rows", ws.title, len(new_rows))


# ──────────────────────────────────────────────────────────────────────
# Per-tab driver
# ──────────────────────────────────────────────────────────────────────
class TabResult:
    __slots__ = ("tab", "status", "total", "decoded", "failed", "backup", "message")

    def __init__(self, tab: str) -> None:
        self.tab = tab
        self.status = "pending"
        self.total = 0
        self.decoded = 0
        self.failed = 0
        self.backup: str | None = None
        self.message = ""

    def as_line(self) -> str:
        parts = [f"{self.tab}: {self.status}"]
        if self.total:
            parts.append(f"{self.decoded}/{self.total} decoded")
        if self.failed:
            parts.append(f"{self.failed} failed")
        if self.backup:
            parts.append(f"backup={self.backup}")
        if self.message:
            parts.append(self.message)
        return " | ".join(parts)


def _row_values_in_header_order(row: dict[str, Any], header: list[str]) -> list[Any]:
    out: list[Any] = []
    for col in header:
        val = row.get(col, "")
        if val is None:
            out.append("")
        else:
            out.append(val)
    return out


def _format_preview(rows: list[dict[str, Any]], limit: int = 3) -> str:
    if not rows:
        return "(no rows)"
    lines: list[str] = []
    preview_cols = [
        "Receive Time",
        "IMEI",
        "Packet Ver",
        "Battery",
        "GPS Latitude",
        "GPS Longitude",
        "SST",
        "CRC Valid",
    ]
    for r in rows[:limit]:
        snippet = ", ".join(f"{c}={r.get(c, '')}" for c in preview_cols)
        lines.append("    " + snippet)
    return "\n".join(lines)


def migrate_tab(sh, tab: str, *, dry_run: bool) -> TabResult:
    result = TabResult(tab)
    try:
        ws = _with_quota_retries(lambda: sh.worksheet(tab), op=f"worksheet({tab})")
    except Exception as exc:
        result.status = "error"
        result.message = f"worksheet lookup failed: {exc}"
        return result

    header = _with_quota_retries(lambda: ws.row_values(1), op=f"row_values({tab})")

    if is_already_migrated(header):
        result.status = "skipped"
        result.message = "already migrated (Receive Time present)"
        return result

    if not is_fy25_raw(header):
        result.status = "skipped"
        result.message = f"not FY25 raw schema (header starts with {header[:3]!r})"
        return result

    records = _with_quota_retries(ws.get_all_records, op=f"get_all_records({tab})")
    result.total = len(records)
    if not records:
        result.status = "empty"
        return result

    decoded_rows: list[dict[str, Any]] = []
    for rec in records:
        row = build_decoded_row(rec)
        if row is None:
            result.failed += 1
            continue
        decoded_rows.append(row)
    result.decoded = len(decoded_rows)

    if result.total and result.failed / result.total > DECODE_FAILURE_THRESHOLD:
        result.status = "aborted"
        pct = 100 * result.failed / result.total
        result.message = (
            f"decode failure rate {pct:.1f}% exceeds "
            f"{DECODE_FAILURE_THRESHOLD * 100:.0f}% threshold"
        )
        return result

    if not decoded_rows:
        result.status = "aborted"
        result.message = "no rows decoded"
        return result

    new_header = build_new_header()
    preview_block = _format_preview(decoded_rows)
    log.info("[%s] sample decoded rows:\n%s", tab, preview_block)

    if dry_run:
        result.status = "dry-run"
        return result

    # ── Real rewrite ──
    # 1. Snapshot current raw contents (header + all cell values).
    original_rows = _with_quota_retries(
        ws.get_all_values, op=f"get_all_values({tab})"
    )
    # ``get_all_values`` returns header too; split it off so our backup
    # tab mirrors the layout exactly.
    if not original_rows:
        result.status = "empty"
        return result
    raw_header = original_rows[0]
    raw_data = original_rows[1:]

    backup_title = create_backup(sh, ws, raw_header, raw_data)
    result.backup = backup_title

    new_rows = [_row_values_in_header_order(r, new_header) for r in decoded_rows]
    rewrite_worksheet(ws, new_header, new_rows)
    result.status = "rewritten"
    return result


# ──────────────────────────────────────────────────────────────────────
# Entrypoint
# ──────────────────────────────────────────────────────────────────────
def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not args.sheet_id:
        log.error("Spreadsheet ID missing; pass --sheet-id or set GOOGLE_SHEETS_ID.")
        return 2

    if not args.tab and not args.all_fy25:
        log.error("Specify exactly one of --tab or --all-fy25.")
        return 2

    client = load_credentials_from_env()
    sh = _with_quota_retries(
        lambda: client.open_by_key(args.sheet_id), op="open_by_key(migrate)"
    )

    if args.all_fy25:
        tabs = discover_fy25_tabs(sh)
        if not tabs:
            log.warning("No FY25_* tabs found in spreadsheet.")
            return 0
    else:
        tabs = [args.tab]

    log.info("Target tabs: %s (dry_run=%s)", tabs, args.dry_run)

    results: list[TabResult] = []
    for tab in tabs:
        log.info("── Migrating %s ──", tab)
        results.append(migrate_tab(sh, tab, dry_run=args.dry_run))

    print("\n=== FY25 Migration Summary ===")
    for r in results:
        print("  " + r.as_line())

    # Surface an error exit code if anything aborted.
    bad = [r for r in results if r.status in ("error", "aborted")]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(run())
