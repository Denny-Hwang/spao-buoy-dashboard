"""
Google Sheets client for reading/writing SPAO buoy data via gspread.
Supports both webhook-decoded data and raw RockBLOCK CSV exports.
"""

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
EXCLUDED_TABS = {"_errors", "Sheet1"}

# Columns containing long hex strings — always placed at the end of tables
_HEX_COLUMNS = {"Raw Hex", "Previous Session", "Payload", "data", "hex", "Hex"}


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
    """Detect if sheet contains raw RockBLOCK data or decoded webhook data."""
    if not headers:
        return "unknown"
    first = headers[0].strip()
    if first in ("Date Time (UTC)", "Date Time"):
        return "rockblock_raw"
    elif first in ("Receive Time",):
        return "webhook_decoded"
    else:
        lower_headers = [h.lower().strip() for h in headers]
        if "payload" in lower_headers or "hex" in lower_headers or "data" in lower_headers:
            return "rockblock_raw"
        return "unknown"


def _find_hex_column(headers: list[str]) -> str | None:
    """Find the column containing hex payload data."""
    for candidate in ["Payload", "payload", "data", "Data", "hex", "Hex", "Raw Hex"]:
        if candidate in headers:
            return candidate
    return None


def decode_rockblock_data(records: list[dict]) -> pd.DataFrame:
    """Decode raw RockBLOCK export data into a standardized DataFrame."""
    decoded_rows = []
    headers = list(records[0].keys()) if records else []
    hex_col = _find_hex_column(headers)

    for row in records:
        hex_payload = str(row.get(hex_col or "Payload", "")).strip()
        if not hex_payload:
            continue

        result = auto_detect_and_decode(hex_payload)

        # Determine timestamp — try multiple column names
        timestamp = row.get("Date Time (UTC)", row.get("Date Time", ""))

        # Determine device identifier
        device = str(row.get("Device", ""))

        # Build decoded row with sensor data first, hex last
        decoded_row = {
            "Timestamp": timestamp,
            "Device": device,
            "Packet Ver": result.get("version", "Unknown") if result else "Unknown",
            "Bytes": row.get("Length (Bytes)", len(hex_payload) // 2),
            "CRC Valid": result.get("crc_ok", False) if result else False,
        }

        # Add decoded sensor fields with units in column names
        if result and result.get("fields"):
            for field in result["fields"]:
                unit = field.get("unit", "")
                name = field["name"]
                if unit and unit != "hex":
                    col_name = f"{name} ({unit})"
                else:
                    col_name = name
                decoded_row[col_name] = field["value"]

        if "error" in result and result["error"]:
            decoded_row["Decode Error"] = result["error"]

        # Raw hex at the end
        decoded_row["Raw Hex"] = hex_payload

        decoded_rows.append(decoded_row)

    if not decoded_rows:
        return pd.DataFrame()

    df = pd.DataFrame(decoded_rows)

    # Parse timestamp column
    if "Timestamp" in df.columns:
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce", format="mixed")

    return reorder_columns(df)


def read_and_decode_sheet(worksheet) -> pd.DataFrame:
    """Read sheet data, auto-detecting format and decoding if needed."""
    records = worksheet.get_all_records()
    if not records:
        return pd.DataFrame()

    headers = list(records[0].keys())
    fmt = detect_sheet_format(headers)

    if fmt == "rockblock_raw":
        return decode_rockblock_data(records)
    elif fmt == "webhook_decoded":
        df = pd.DataFrame(records)
        for col in df.columns:
            if col != "Notes":
                df[col] = pd.to_numeric(df[col], errors="ignore")
        return reorder_columns(df)
    else:
        hex_col = _find_hex_column(headers)
        if hex_col:
            return decode_rockblock_data(records)
        df = pd.DataFrame(records)
        for col in df.columns:
            if col != "Notes":
                df[col] = pd.to_numeric(df[col], errors="ignore")
        return reorder_columns(df)


@st.cache_data(ttl=60)
def list_device_tabs(sheet_id: str = SHEET_ID) -> list[str]:
    """Return all worksheet tab names except excluded ones."""
    try:
        spreadsheet = _open_sheet(sheet_id)
        return [ws.title for ws in spreadsheet.worksheets() if ws.title not in EXCLUDED_TABS]
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


def update_note(tab_name: str, row_index: int, note_text: str, sheet_id: str = SHEET_ID) -> bool:
    """Write a note to the Notes column for a specific row."""
    try:
        spreadsheet = _open_sheet(sheet_id)
        worksheet = spreadsheet.worksheet(tab_name)
        headers = worksheet.row_values(1)
        if "Notes" not in headers:
            notes_col = len(headers) + 1
            worksheet.update_cell(1, notes_col, "Notes")
        else:
            notes_col = headers.index("Notes") + 1
        sheet_row = row_index + 2
        worksheet.update_cell(sheet_row, notes_col, note_text)
        get_device_data.clear()
        get_all_data.clear()
        list_device_tabs.clear()
        return True
    except Exception as e:
        st.error(f"Failed to update note: {e}")
        return False
