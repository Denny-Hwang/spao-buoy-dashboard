"""
Google Sheets client for reading/writing SPAO buoy data via gspread.
Supports both webhook-decoded data and raw RockBLOCK CSV exports.
"""

import re

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

from utils.decoders import auto_detect_and_decode

SHEET_ID = "1qJWka_8kDlLBRFXtUtYWLl3S026KxP3tRCmlC_N6dkU"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
# Exclude default Google Sheets tabs ("Sheet1", "Sheet2", …) and the error log
_DEFAULT_SHEET_RE = re.compile(r"^Sheet\d*$")
EXCLUDED_TABS = {"_errors", "_devices"}

# Columns containing long hex strings — always placed at the end of tables
_HEX_COLUMNS = {"Raw Hex", "Payload", "data", "hex", "Hex"}


@st.cache_resource
def get_client() -> gspread.Client:
    """Return a cached gspread client using Streamlit secrets."""
    creds_info = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(dict(creds_info), scopes=SCOPES)
    return gspread.authorize(creds)


def _open_sheet(sheet_id: str = SHEET_ID) -> gspread.Spreadsheet:
    """Open a Google Spreadsheet by ID."""
    client = get_client()
    return client.open_by_key(sheet_id)


def reorder_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Move hex/long data columns to the end for better readability."""
    if df.empty:
        return df
    hex_cols = [c for c in df.columns if c in _HEX_COLUMNS]
    other_cols = [c for c in df.columns if c not in _HEX_COLUMNS]
    return df[other_cols + hex_cols]


def detect_sheet_format(headers: list[str]) -> str:
    """Detect sheet data format based on header columns.

    Returns one of:
        ``rockblock_csv``   — Format A: RockBLOCK site CSV download
        ``webhook_decoded`` — Format B-1: Apps Script decoded webhook data
        ``webhook_errors``  — Format B-2: RB download / webhook error rows
        ``unknown``         — Unrecognised layout
    """
    if not headers:
        return "unknown"

    header_set = {h.strip() for h in headers}
    first = headers[0].strip()

    # Format A: RockBLOCK CSV export (first col = Date Time …)
    if first in ("Date Time (UTC)", "Date Time"):
        return "rockblock_csv"

    # Format B-1: Webhook decoded by Apps Script (first col = Receive Time)
    if first == "Receive Time":
        return "webhook_decoded"

    # Format B-2: New RB download / webhook error tab
    #   Columns: Time | IMEI | MOMSN | Transmit Time | Raw Hex | Error
    if "Raw Hex" in header_set and ("Error" in header_set or first == "Time"):
        return "webhook_errors"

    # Fallback: look for any known hex-payload column
    lower_headers = [h.lower().strip() for h in headers]
    if "payload" in lower_headers or "hex" in lower_headers or "data" in lower_headers:
        return "rockblock_csv"

    return "unknown"


def _find_hex_column(headers: list[str]) -> str | None:
    """Find the column containing hex payload data."""
    for candidate in ["Payload", "payload", "data", "Data", "hex", "Hex", "Raw Hex"]:
        if candidate in headers:
            return candidate
    return None


def normalize_sheet_data(records: list[dict], format_type: str) -> pd.DataFrame:
    """Convert any sheet format into a unified DataFrame.

    Always re-decodes from raw hex via ``auto_detect_and_decode`` so that
    decoder updates apply to all data automatically.
    """
    rows: list[dict] = []
    headers = list(records[0].keys()) if records else []

    for idx, record in enumerate(records):
        # ── Extract hex payload & metadata per format ──
        if format_type == "rockblock_csv":
            hex_col = _find_hex_column(headers)
            hex_str = str(record.get(hex_col or "Payload", "")).strip()
            timestamp = record.get("Date Time (UTC)", record.get("Date Time", ""))
            device = str(record.get("Device", ""))
            momsn = ""
            transmit_time = ""
        elif format_type == "webhook_decoded":
            hex_str = str(record.get("Raw Hex", "")).strip()
            timestamp = record.get("Receive Time", "")
            device = str(record.get("IMEI", ""))
            momsn = str(record.get("MOMSN", ""))
            transmit_time = str(record.get("Transmit Time", ""))
        elif format_type == "webhook_errors":
            hex_str = str(record.get("Raw Hex", "")).strip()
            timestamp = record.get("Time", "")
            device = str(record.get("IMEI", ""))
            momsn = str(record.get("MOMSN", ""))
            transmit_time = str(record.get("Transmit Time", ""))
        else:
            continue

        if not hex_str:
            continue

        # ── Decode ──
        result = auto_detect_and_decode(hex_str)

        row: dict = {
            # Absolute 1-indexed worksheet row (header is row 1, first data row is 2).
            # Preserved through filtering/sorting so writes target the correct cell.
            "_sheet_row": idx + 2,
            "Timestamp": timestamp,
            "Device": device,
            "MOMSN": momsn,
            "Packet Ver": result.get("version", "Unknown") if result else "Unknown",
            "Bytes": result.get("byte_len", len(hex_str) // 2) if result else len(hex_str) // 2,
            "CRC Valid": result.get("crc_ok", False) if result else False,
        }

        if transmit_time:
            row["Transmit Time"] = transmit_time

        # Decoded sensor fields
        if result and result.get("fields"):
            for field in result["fields"]:
                row[field["name"]] = field["value"]

        if result and result.get("error"):
            row["Decode Error"] = result["error"]

        if result and result.get("warning"):
            row["Warning"] = result["warning"]

        # Preserve Notes column if present
        if "Notes" in record and record["Notes"]:
            row["Notes"] = record["Notes"]

        # Raw hex last
        row["Raw Hex"] = hex_str

        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    if "Timestamp" in df.columns:
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce", format="mixed")

    return reorder_columns(df)


def read_and_decode_sheet(worksheet) -> pd.DataFrame:
    """Read sheet data, auto-detecting format and decoding if needed.

    All recognised formats are re-decoded from raw hex so that decoder
    improvements apply retroactively to historical data.
    """
    records = worksheet.get_all_records()
    if not records:
        return pd.DataFrame()

    headers = list(records[0].keys())
    fmt = detect_sheet_format(headers)

    if fmt in ("rockblock_csv", "webhook_decoded", "webhook_errors"):
        return normalize_sheet_data(records, fmt)

    # Unknown format — try to find a hex column and decode as rockblock_csv
    hex_col = _find_hex_column(headers)
    if hex_col:
        return normalize_sheet_data(records, "rockblock_csv")

    # Completely unknown — return as-is
    df = pd.DataFrame(records)
    # Absolute 1-indexed worksheet row (header row 1 → first data row 2).
    df["_sheet_row"] = range(2, len(df) + 2)
    for col in df.columns:
        if col == "Notes" or col == "_sheet_row":
            continue
        df[col] = pd.to_numeric(df[col], errors="ignore")
    return reorder_columns(df)


@st.cache_data(ttl=60)
def list_device_tabs(sheet_id: str = SHEET_ID) -> list[str]:
    """Return all worksheet tab names except excluded ones.

    Filters out default Google Sheets names (Sheet1, Sheet2, …) and
    any tabs in EXCLUDED_TABS.
    """
    try:
        spreadsheet = _open_sheet(sheet_id)
        return [
            ws.title
            for ws in spreadsheet.worksheets()
            if ws.title not in EXCLUDED_TABS and not _DEFAULT_SHEET_RE.match(ws.title)
        ]
    except Exception as e:
        st.error(f"Failed to list device tabs: {e}")
        return []


@st.cache_data(ttl=120)
def get_device_data(tab_name: str, sheet_id: str = SHEET_ID) -> pd.DataFrame:
    """Return all rows for a device tab as a DataFrame, auto-detecting format."""
    try:
        spreadsheet = _open_sheet(sheet_id)
        worksheet = spreadsheet.worksheet(tab_name)
        return read_and_decode_sheet(worksheet)
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"Worksheet '{tab_name}' not found.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Failed to load data for {tab_name}: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=120)
def get_all_data(sheet_id: str = SHEET_ID) -> pd.DataFrame:
    """Merge all device tabs into a single DataFrame with a 'Device Tab' column."""
    tabs = list_device_tabs(sheet_id)
    frames = []
    for tab in tabs:
        df = get_device_data(tab, sheet_id)
        if not df.empty:
            df = df.copy()
            df["Device Tab"] = tab
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def get_device_ids(df: pd.DataFrame) -> list[str]:
    """Extract unique device identifiers from a DataFrame.

    Checks the 'Device' column first (RockBLOCK format), then 'IMEI',
    then 'Device Tab'.  Returns a sorted list of unique IDs.
    """
    for col in ("Device", "IMEI", "Device Tab"):
        if col in df.columns:
            ids = df[col].dropna().astype(str).unique().tolist()
            ids = [d for d in ids if d and d != ""]
            if ids:
                return sorted(ids)
    return []


def get_device_column(df: pd.DataFrame) -> str | None:
    """Return the name of the best device-identifier column in *df*."""
    for col in ("Device", "IMEI", "Device Tab"):
        if col in df.columns:
            vals = df[col].dropna().astype(str)
            if not vals.empty and vals.str.strip().ne("").any():
                return col
    return None


@st.cache_data(ttl=300)
def get_device_nicknames(sheet_id: str = SHEET_ID) -> dict[str, str]:
    """Load IMEI/Serial → Nickname mapping from the optional ``_devices`` tab.

    Expected columns: ``Device ID``, ``Nickname`` (others are ignored).
    Returns ``{device_id: nickname}`` or empty dict if the tab doesn't exist.
    """
    try:
        spreadsheet = _open_sheet(sheet_id)
        ws = spreadsheet.worksheet("_devices")
        records = ws.get_all_records()
        mapping: dict[str, str] = {}
        for row in records:
            did = str(row.get("Device ID", "")).strip()
            nick = str(row.get("Nickname", "")).strip()
            if did and nick:
                mapping[did] = nick
        return mapping
    except gspread.exceptions.WorksheetNotFound:
        return {}
    except Exception:
        return {}


def format_device_label(device_id: str, nicknames: dict[str, str]) -> str:
    """Return ``nickname (id)`` if a mapping exists, else just the id."""
    nick = nicknames.get(device_id, "")
    return f"{nick} ({device_id})" if nick else device_id


def update_note(tab_name: str, sheet_row: int, note_text: str, sheet_id: str = SHEET_ID) -> bool:
    """Write a note to the Notes column for a specific row.

    ``sheet_row`` is the absolute 1-indexed worksheet row (header is row 1,
    first data row is 2) as captured in the ``_sheet_row`` column.
    """
    try:
        spreadsheet = _open_sheet(sheet_id)
        worksheet = spreadsheet.worksheet(tab_name)
        headers = worksheet.row_values(1)
        if "Notes" not in headers:
            notes_col = len(headers) + 1
            worksheet.update_cell(1, notes_col, "Notes")
        else:
            notes_col = headers.index("Notes") + 1
        worksheet.update_cell(sheet_row, notes_col, note_text)
        get_device_data.clear()
        get_all_data.clear()
        list_device_tabs.clear()
        return True
    except Exception as e:
        st.error(f"Failed to update note: {e}")
        return False
