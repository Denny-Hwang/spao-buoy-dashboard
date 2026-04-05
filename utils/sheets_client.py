"""
Google Sheets client for reading/writing SPAO buoy data via gspread.
"""

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

SHEET_ID = "1qJWka_8kDlLBRFXtUtYWLl3S026KxP3tRCmlC_N6dkU"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
EXCLUDED_TABS = {"_errors", "Sheet1"}


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


@st.cache_data(ttl=300)
def list_device_tabs(sheet_id: str = SHEET_ID) -> list[str]:
    """Return all worksheet tab names except excluded ones."""
    try:
        spreadsheet = _open_sheet(sheet_id)
        return [ws.title for ws in spreadsheet.worksheets() if ws.title not in EXCLUDED_TABS]
    except Exception as e:
        st.error(f"Failed to list device tabs: {e}")
        return []


@st.cache_data(ttl=300)
def get_device_data(imei: str, sheet_id: str = SHEET_ID) -> pd.DataFrame:
    """Return all rows for a device tab as a DataFrame."""
    try:
        spreadsheet = _open_sheet(sheet_id)
        worksheet = spreadsheet.worksheet(imei)
        records = worksheet.get_all_records()
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        # Convert numeric columns where possible
        for col in df.columns:
            if col != "Notes":
                df[col] = pd.to_numeric(df[col], errors="ignore")
        return df
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"Worksheet '{imei}' not found.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Failed to load data for {imei}: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def get_all_data(sheet_id: str = SHEET_ID) -> pd.DataFrame:
    """Merge all device tabs into a single DataFrame with an 'IMEI' column."""
    tabs = list_device_tabs(sheet_id)
    frames = []
    for tab in tabs:
        df = get_device_data(tab, sheet_id)
        if not df.empty:
            df = df.copy()
            df["IMEI"] = tab
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def update_note(imei: str, row_index: int, note_text: str, sheet_id: str = SHEET_ID) -> bool:
    """
    Write a note to the Notes column for a specific row.

    Args:
        imei: Device tab name.
        row_index: 0-based index into data rows (row 0 = spreadsheet row 2).
        note_text: Text to write.

    Returns:
        True on success.
    """
    try:
        spreadsheet = _open_sheet(sheet_id)
        worksheet = spreadsheet.worksheet(imei)
        headers = worksheet.row_values(1)
        if "Notes" not in headers:
            # Add Notes column
            notes_col = len(headers) + 1
            worksheet.update_cell(1, notes_col, "Notes")
        else:
            notes_col = headers.index("Notes") + 1  # 1-based
        # row_index 0 = data row 2 in spreadsheet
        sheet_row = row_index + 2
        worksheet.update_cell(sheet_row, notes_col, note_text)
        # Clear cache so fresh data is loaded
        get_device_data.clear()
        get_all_data.clear()
        list_device_tabs.clear()
        return True
    except Exception as e:
        st.error(f"Failed to update note: {e}")
        return False
