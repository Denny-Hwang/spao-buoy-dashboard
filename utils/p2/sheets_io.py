"""
Google Sheets I/O for the cron-side enrichment pipeline.

This module is **cron-only**. It is never imported by the Streamlit app.
It reads the service-account JSON from the ``GCP_SERVICE_ACCOUNT_JSON``
environment variable (as delivered by GitHub Actions secrets) rather
than from Streamlit secrets.
"""

from __future__ import annotations

import json
import logging
import os
import string
import time
from typing import Any, Iterable

import pandas as pd

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# gspread update() API cap: ~100 rows per batch works under the
# default 60 req/min quota. Reduce to 50 if we hit HTTP 429 in practice.
DEFAULT_BATCH_SIZE = 100


def load_credentials_from_env() -> Any:
    """Build a gspread client from ``GCP_SERVICE_ACCOUNT_JSON``.

    The env var is a JSON string (as GitHub Actions stores secrets).
    Raises ``RuntimeError`` with a clear message if the var is missing
    or malformed — we never log the secret contents.
    """
    import gspread  # local import so Streamlit side never pulls this in
    from google.oauth2.service_account import Credentials

    raw = os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError(
            "GCP_SERVICE_ACCOUNT_JSON env var is not set; cannot authenticate to Google Sheets."
        )
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "GCP_SERVICE_ACCOUNT_JSON is set but is not valid JSON."
        ) from exc
    try:
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    except Exception as exc:
        raise RuntimeError(
            "Failed to build Google credentials from GCP_SERVICE_ACCOUNT_JSON."
        ) from exc
    return gspread.authorize(creds)


def _col_letter(n: int) -> str:
    """Convert a 1-indexed column number to an A1 letter (1→A, 27→AA)."""
    if n < 1:
        raise ValueError(f"column number must be >= 1, got {n}")
    letters = []
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters.append(string.ascii_uppercase[rem])
    return "".join(reversed(letters))


def read_sheet_as_df(client, sheet_id: str, worksheet: str = "Sheet1") -> pd.DataFrame:
    """Return the worksheet contents as a DataFrame with a ``_row`` column.

    ``_row`` is the absolute 1-indexed spreadsheet row number (header = 1,
    first data row = 2) so that later writes can target the correct
    cells regardless of filtering/sorting.
    """
    sh = client.open_by_key(sheet_id)
    ws = sh.worksheet(worksheet)
    records = ws.get_all_records()
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    df["_row"] = range(2, len(df) + 2)
    return df


def _ensure_header_columns(ws, columns: list[str]) -> dict[str, int]:
    """Make sure every column in *columns* exists in the worksheet header.

    Returns a mapping ``{column_name: 1-indexed_col_number}``.
    Missing columns are appended to the right of the existing header.
    """
    header = ws.row_values(1)
    col_to_idx: dict[str, int] = {name: i + 1 for i, name in enumerate(header) if name}
    missing = [c for c in columns if c not in col_to_idx]
    if missing:
        new_header = header + missing
        # Write the full header row to avoid gaps.
        cells_end = _col_letter(len(new_header))
        ws.update(range_name=f"A1:{cells_end}1", values=[new_header])
        col_to_idx = {name: i + 1 for i, name in enumerate(new_header) if name}
    return col_to_idx


def _format_cell(val: Any) -> Any:
    """gspread.update() wants JSON-serializable scalars only."""
    if val is None:
        return ""
    if isinstance(val, float):
        import math
        if math.isnan(val):
            return ""
    return val


def write_enrichment_columns(
    client,
    sheet_id: str,
    df: pd.DataFrame,
    columns: Iterable[str],
    worksheet: str = "Sheet1",
    batch_size: int = DEFAULT_BATCH_SIZE,
    sleep_between_batches: float = 0.4,
) -> int:
    """Write the given *columns* for every row of *df* back into Sheets.

    ``df`` must include the ``_row`` absolute spreadsheet row number
    (as produced by :func:`read_sheet_as_df`).

    Writes are batched per column with one ``values_update`` call per
    batch; this is the rate-friendly pattern for gspread. Returns the
    total number of cells written.
    """
    cols = [c for c in columns if c in df.columns]
    if not cols:
        return 0
    if "_row" not in df.columns:
        raise ValueError("df must contain a '_row' column from read_sheet_as_df()")

    sh = client.open_by_key(sheet_id)
    ws = sh.worksheet(worksheet)

    col_map = _ensure_header_columns(ws, cols)
    written = 0

    # Sort by _row so contiguous batches can use a single A1 range.
    df_sorted = df.sort_values("_row")
    rows_all = df_sorted["_row"].tolist()

    for col in cols:
        col_idx = col_map[col]
        col_letter = _col_letter(col_idx)
        values = df_sorted[col].tolist()
        # Batch into chunks of batch_size.
        for start in range(0, len(rows_all), batch_size):
            end = min(start + batch_size, len(rows_all))
            batch_rows = rows_all[start:end]
            batch_vals = values[start:end]

            # If rows are not strictly contiguous, fall back to one
            # per-row write per cell; otherwise use a single range.
            if batch_rows == list(range(batch_rows[0], batch_rows[-1] + 1)):
                rng = f"{col_letter}{batch_rows[0]}:{col_letter}{batch_rows[-1]}"
                ws.update(range_name=rng, values=[[_format_cell(v)] for v in batch_vals])
                written += len(batch_vals)
            else:
                for r, v in zip(batch_rows, batch_vals):
                    ws.update(range_name=f"{col_letter}{r}", values=[[_format_cell(v)]])
                    written += 1
            if sleep_between_batches:
                time.sleep(sleep_between_batches)

    log.info("sheets_io: wrote %d cells across %d columns", written, len(cols))
    return written


__all__ = [
    "SCOPES",
    "DEFAULT_BATCH_SIZE",
    "load_credentials_from_env",
    "read_sheet_as_df",
    "write_enrichment_columns",
]
