"""
Read / write helpers for the ``Derived_Daily`` Google Sheets worksheet.

Keeping the Sheets plumbing out of ``utils.p2.derived`` lets the
aggregation module stay gspread-free and fully unit-testable.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import pandas as pd

from .derived import DERIVED_DAILY_COLUMNS, DERIVED_DAILY_WORKSHEET

log = logging.getLogger(__name__)


def open_spreadsheet(sheet_id: str) -> Any:
    """Open the target spreadsheet via gspread using env-based credentials."""
    from .sheets_io import load_credentials_from_env
    client = load_credentials_from_env()
    return client.open_by_key(sheet_id)


def _ensure_worksheet(spreadsheet, title: str, n_cols: int):
    """Return (worksheet, created?) tuple, creating the tab if absent."""
    try:
        return spreadsheet.worksheet(title), False
    except Exception:
        try:
            ws = spreadsheet.add_worksheet(title=title, rows=1000, cols=max(26, n_cols + 2))
            return ws, True
        except Exception as exc:
            raise RuntimeError(
                f"Derived_Daily worksheet '{title}' missing and creation failed: {exc}"
            ) from exc


def _frame_to_rows(df: pd.DataFrame) -> list[list[Any]]:
    """Serialize a DataFrame to row-major lists, NaN→''."""
    def _cell(val):
        if val is None:
            return ""
        if isinstance(val, float):
            import math
            if math.isnan(val):
                return ""
            return val
        if isinstance(val, bool):
            return bool(val)
        return val

    return [[_cell(v) for v in row] for row in df.itertuples(index=False, name=None)]


def read_derived_daily(sheet_id: str, worksheet: str = DERIVED_DAILY_WORKSHEET) -> pd.DataFrame:
    """Return the Derived_Daily worksheet as a DataFrame (empty on failure)."""
    try:
        sh = open_spreadsheet(sheet_id)
    except Exception as exc:
        log.info("read_derived_daily: cannot open spreadsheet: %s", exc)
        return pd.DataFrame(columns=DERIVED_DAILY_COLUMNS)
    try:
        ws = sh.worksheet(worksheet)
    except Exception:
        log.info("read_derived_daily: worksheet %s absent", worksheet)
        return pd.DataFrame(columns=DERIVED_DAILY_COLUMNS)
    try:
        records = ws.get_all_records()
    except Exception as exc:
        log.info("read_derived_daily: get_all_records failed: %s", exc)
        return pd.DataFrame(columns=DERIVED_DAILY_COLUMNS)
    if not records:
        return pd.DataFrame(columns=DERIVED_DAILY_COLUMNS)
    df = pd.DataFrame(records)
    # Ensure stable column order.
    for col in DERIVED_DAILY_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    return df[DERIVED_DAILY_COLUMNS]


def write_derived_daily(
    sheet_id: str,
    df: pd.DataFrame,
    worksheet: str = DERIVED_DAILY_WORKSHEET,
) -> int:
    """Idempotently upsert ``df`` into the Derived_Daily worksheet.

    Merges on the ``date`` column — existing rows for the same date
    are overwritten, new dates are appended. Returns the number of
    rows written to Sheets.
    """
    if df is None or df.empty:
        return 0

    sh = open_spreadsheet(sheet_id)
    ws, created = _ensure_worksheet(sh, worksheet, n_cols=len(DERIVED_DAILY_COLUMNS))

    # Read the existing table (if any) to merge.
    try:
        existing = pd.DataFrame(ws.get_all_records())
    except Exception:
        existing = pd.DataFrame()

    if not existing.empty and "date" in existing.columns:
        existing = existing[~existing["date"].isin(df["date"])]
        merged = pd.concat([existing, df], ignore_index=True)
    else:
        merged = df.copy()

    # Sort by date ascending for stability.
    merged = merged.sort_values("date").reset_index(drop=True)
    # Guarantee the canonical column order.
    for col in DERIVED_DAILY_COLUMNS:
        if col not in merged.columns:
            merged[col] = pd.NA
    merged = merged[DERIVED_DAILY_COLUMNS]

    header = list(merged.columns)
    values = [header] + _frame_to_rows(merged)
    try:
        ws.clear()
    except Exception:
        pass
    try:
        ws.update(range_name="A1", values=values)
    except Exception as exc:
        raise RuntimeError(f"Derived_Daily update failed: {exc}") from exc
    return len(merged)


__all__ = [
    "open_spreadsheet",
    "read_derived_daily",
    "write_derived_daily",
]
