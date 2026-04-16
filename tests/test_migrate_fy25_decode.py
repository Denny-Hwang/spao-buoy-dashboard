"""Tests for scripts/migrate_fy25_decode.py.

These exercise the FY25 raw → decoded rewrite without touching any real
Google Sheets: a tiny in-memory fake spreadsheet backs all gspread calls
used by the migration script (``worksheets``, ``worksheet``,
``row_values``, ``get_all_records``, ``get_all_values``, ``add_worksheet``,
``update``, ``clear``).
"""

from __future__ import annotations

import pytest

from scripts import migrate_fy25_decode as mig
from utils.decoders import SAMPLE_DATA, auto_detect_and_decode
from utils.p2.schema import ENRICH_COLUMN_ORDER

# ── A known-good FY25 hex packet (from decoders.SAMPLE_DATA) ──────────
FY25_HEX = SAMPLE_DATA["FY25"]
_SAMPLE_DECODED = auto_detect_and_decode(FY25_HEX)
assert _SAMPLE_DECODED.get("version") == "FY25"
assert _SAMPLE_DECODED.get("byte_len") == 38


# ──────────────────────────────────────────────────────────────────────
# In-memory fake gspread objects
# ──────────────────────────────────────────────────────────────────────
class FakeWorksheet:
    def __init__(self, title: str, values: list[list[str]]):
        self.title = title
        # values[0] = header, values[1:] = rows.
        self._values = [list(row) for row in values]
        self._cleared = False

    def row_values(self, row: int) -> list[str]:
        if 1 <= row <= len(self._values):
            return list(self._values[row - 1])
        return []

    def get_all_records(self) -> list[dict[str, str]]:
        if len(self._values) < 2:
            return []
        header = self._values[0]
        return [
            {header[i]: (row[i] if i < len(row) else "") for i in range(len(header))}
            for row in self._values[1:]
        ]

    def get_all_values(self) -> list[list[str]]:
        return [list(r) for r in self._values]

    def clear(self) -> None:
        self._values = []
        self._cleared = True

    def update(self, range_name: str, values: list[list]) -> None:
        # We only ever write starting at A1 in this script.
        assert range_name.startswith("A1"), f"unexpected range: {range_name}"
        self._values = [list(row) for row in values]


class FakeSpreadsheet:
    def __init__(self, worksheets: list[FakeWorksheet]):
        self._worksheets = list(worksheets)

    def worksheets(self) -> list[FakeWorksheet]:
        return list(self._worksheets)

    def worksheet(self, title: str) -> FakeWorksheet:
        for ws in self._worksheets:
            if ws.title == title:
                return ws
        raise KeyError(title)

    def add_worksheet(self, title: str, rows: int, cols: int) -> FakeWorksheet:
        # Start empty; update() will fill it.
        ws = FakeWorksheet(title, [[""] * max(cols, 1)])
        ws._values = []  # real gspread semantics: caller supplies everything
        self._worksheets.append(ws)
        return ws


# ──────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ──────────────────────────────────────────────────────────────────────
def _make_raw_fy25_tab(
    title: str = "FY25_Bearing_sea_RB_220835",
    n_rows: int = 4,
) -> FakeWorksheet:
    header = ["Date Time (UTC)", "Device", "Approx Lat/Lng", "Payload"]
    data = []
    for i in range(n_rows):
        data.append(
            [
                f"2025-09-10 0{i}:00:00",
                "RockBLOCK 220835",
                "58.4494,-174.29623",
                FY25_HEX,
            ]
        )
    return FakeWorksheet(title, [header] + data)


# ──────────────────────────────────────────────────────────────────────
# Pure-function tests
# ──────────────────────────────────────────────────────────────────────
def test_build_new_header_layout():
    header = mig.build_new_header()
    assert header[0] == "Receive Time"
    assert header[-1] == "Raw Hex"
    # Every enrichment column is present, sandwiched between Notes and Raw Hex.
    notes_idx = header.index("Notes")
    raw_idx = header.index("Raw Hex")
    enrich_slice = header[notes_idx + 1 : raw_idx]
    assert enrich_slice == list(ENRICH_COLUMN_ORDER)
    # No duplicates.
    assert len(header) == len(set(header))


def test_is_fy25_raw_and_is_already_migrated():
    assert mig.is_fy25_raw(["Date Time (UTC)", "Device", "Approx Lat/Lng", "Payload"])
    assert mig.is_fy25_raw(["Date Time", "Payload"])
    assert not mig.is_fy25_raw(["Receive Time", "IMEI", "Raw Hex"])
    assert not mig.is_fy25_raw(["Date Time (UTC)", "Device"])  # no Payload

    assert mig.is_already_migrated(["Receive Time", "IMEI"])
    assert not mig.is_already_migrated(["Date Time (UTC)", "Payload"])
    assert not mig.is_already_migrated([])


def test_build_decoded_row_maps_metadata_and_sensors():
    record = {
        "Date Time (UTC)": "2025-09-10 02:23:00",
        "Device": "RockBLOCK 220835",
        "Approx Lat/Lng": "58.4494,-174.29623",
        "Payload": FY25_HEX,
    }
    row = mig.build_decoded_row(record)
    assert row is not None

    # Metadata
    assert row["Receive Time"] == "2025-09-10 02:23:00"
    # Transmit Time mirrors Receive Time (user choice (a)).
    assert row["Transmit Time"] == "2025-09-10 02:23:00"
    assert row["IMEI"] == "RockBLOCK 220835"
    assert row["MOMSN"] == ""
    assert row["Packet Ver"] == "FY25"
    assert row["Bytes"] == 38
    assert row["CRC Valid"] in (True, False)  # sample packet CRC flag

    # Raw Hex preserved (normalized: stripped / lowercase).
    assert row["Raw Hex"] == FY25_HEX.replace(" ", "").replace("0x", "").lower()

    # Sensor columns populated numerically.
    assert isinstance(row["Battery"], (int, float))
    assert isinstance(row["SST"], (int, float))
    # Enrichment columns initialised blank — the next cron run fills them.
    for c in ENRICH_COLUMN_ORDER:
        assert row[c] == ""


def test_build_decoded_row_returns_none_on_empty_payload():
    assert mig.build_decoded_row({"Date Time (UTC)": "t", "Payload": ""}) is None


def test_build_decoded_row_returns_none_on_garbage_payload():
    assert mig.build_decoded_row({"Date Time (UTC)": "t", "Payload": "zzzz"}) is None


# ──────────────────────────────────────────────────────────────────────
# Integration tests against the in-memory fake spreadsheet
# ──────────────────────────────────────────────────────────────────────
def test_migrate_tab_dry_run_leaves_sheet_untouched():
    ws = _make_raw_fy25_tab(n_rows=3)
    original_snapshot = [list(r) for r in ws.get_all_values()]
    sh = FakeSpreadsheet([ws])

    result = mig.migrate_tab(sh, ws.title, dry_run=True)

    assert result.status == "dry-run"
    assert result.total == 3
    assert result.decoded == 3
    assert result.failed == 0
    # Sheet unchanged.
    assert ws.get_all_values() == original_snapshot
    # No backup tab was created.
    assert [w.title for w in sh.worksheets()] == [ws.title]


def test_migrate_tab_real_rewrite_creates_backup_and_updates_schema():
    ws = _make_raw_fy25_tab(n_rows=3)
    original_snapshot = [list(r) for r in ws.get_all_values()]
    sh = FakeSpreadsheet([ws])

    result = mig.migrate_tab(sh, ws.title, dry_run=False)

    assert result.status == "rewritten"
    assert result.decoded == 3
    assert result.failed == 0
    assert result.backup == f"{ws.title}{mig.BACKUP_SUFFIX}"

    # Backup tab matches the original raw content.
    backup_ws = sh.worksheet(result.backup)
    assert backup_ws.get_all_values() == original_snapshot

    # Original tab now uses the decoded schema.
    new_values = ws.get_all_values()
    assert new_values[0] == mig.build_new_header()
    assert len(new_values) == 1 + 3  # header + 3 decoded rows

    # Spot-check a field from the decoded row.
    header = new_values[0]
    first_row = dict(zip(header, new_values[1]))
    assert first_row["Receive Time"] == "2025-09-10 00:00:00"
    assert first_row["IMEI"] == "RockBLOCK 220835"
    assert first_row["Packet Ver"] == "FY25"


def test_migrate_tab_idempotent_when_already_migrated():
    # Build a tab that already uses the decoded schema.
    header = mig.build_new_header()
    ws = FakeWorksheet("FY25_already_done", [header])
    sh = FakeSpreadsheet([ws])

    result = mig.migrate_tab(sh, ws.title, dry_run=False)

    assert result.status == "skipped"
    assert "already migrated" in result.message
    # No backup written.
    assert [w.title for w in sh.worksheets()] == [ws.title]


def test_migrate_tab_aborts_on_high_decode_failure():
    header = ["Date Time (UTC)", "Device", "Approx Lat/Lng", "Payload"]
    # Garbage payloads → decode failure rate 100%.
    rows = [["2025-09-10 0{}:00".format(i), "RB", "0,0", "nothex"] for i in range(5)]
    ws = FakeWorksheet("FY25_garbage", [header] + rows)
    sh = FakeSpreadsheet([ws])

    result = mig.migrate_tab(sh, ws.title, dry_run=False)

    assert result.status == "aborted"
    assert result.failed == 5
    # Tab was NOT touched.
    assert ws.get_all_values()[0] == header
    # No backup.
    assert [w.title for w in sh.worksheets()] == [ws.title]


def test_migrate_tab_skips_non_fy25_schema():
    ws = FakeWorksheet(
        "FY25_weirdly_named",
        [["Something", "Else"], ["a", "b"]],
    )
    sh = FakeSpreadsheet([ws])

    result = mig.migrate_tab(sh, ws.title, dry_run=False)

    assert result.status == "skipped"
    assert "not FY25 raw" in result.message


def test_discover_fy25_tabs_filters_by_prefix():
    sh = FakeSpreadsheet(
        [
            FakeWorksheet("FY25_one", [["Date Time (UTC)", "Payload"]]),
            FakeWorksheet("FY26_webhook", [["Receive Time"]]),
            FakeWorksheet("_errors", [["x"]]),
            FakeWorksheet("FY25_two", [["Date Time (UTC)", "Payload"]]),
        ]
    )
    assert mig.discover_fy25_tabs(sh) == ["FY25_one", "FY25_two"]


def test_unique_backup_title_increments_on_collision():
    base = "FY25_x"
    sh = FakeSpreadsheet(
        [
            FakeWorksheet(base, [["Date Time (UTC)", "Payload"]]),
            FakeWorksheet(f"{base}{mig.BACKUP_SUFFIX}", [["_"]]),
        ]
    )
    title1 = mig._unique_backup_title(sh, base)
    assert title1 == f"{base}{mig.BACKUP_SUFFIX}_2"

    sh = FakeSpreadsheet(
        [
            FakeWorksheet(base, [["Date Time (UTC)", "Payload"]]),
            FakeWorksheet(f"{base}{mig.BACKUP_SUFFIX}", [["_"]]),
            FakeWorksheet(f"{base}{mig.BACKUP_SUFFIX}_2", [["_"]]),
        ]
    )
    assert mig._unique_backup_title(sh, base) == f"{base}{mig.BACKUP_SUFFIX}_3"


def test_run_returns_error_code_when_any_tab_aborts(monkeypatch):
    # Wire the fake spreadsheet behind the credentials + open_by_key path.
    ws_good = _make_raw_fy25_tab(title="FY25_good", n_rows=2)
    ws_bad = FakeWorksheet(
        "FY25_bad",
        [["Date Time (UTC)", "Device", "Approx Lat/Lng", "Payload"]]
        + [["t", "RB", "0,0", "nothex"] for _ in range(5)],
    )
    sh = FakeSpreadsheet([ws_good, ws_bad])

    class FakeClient:
        def open_by_key(self, _sheet_id):
            return sh

    monkeypatch.setattr(mig, "load_credentials_from_env", lambda: FakeClient())

    rc = mig.run(["--all-fy25", "--dry-run", "--sheet-id", "dummy"])
    # Bad tab aborted → non-zero exit.
    assert rc == 1
