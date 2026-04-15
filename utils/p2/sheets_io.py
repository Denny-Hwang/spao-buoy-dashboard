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
import re
import string
import time
from typing import Any, Callable, Iterable, TypeVar

import pandas as pd

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# gspread update() API cap: ~100 rows per batch works under the
# default 60 req/min quota. Reduce to 50 if we hit HTTP 429 in practice.
DEFAULT_BATCH_SIZE = 100

DEFAULT_EXCLUDED_TABS = {"_errors", "_devices", "Derived_Daily"}
_DEFAULT_SHEET_RE = re.compile(r"^Sheet\d+$")
_T = TypeVar("_T")

# Substrings matched against ``str(exception)`` that indicate a transient
# Google Sheets API error worth retrying. Two families:
#   * 429 / quota / rate-limit  — caller-side throttling
#   * 500 / 502 / 503 / 504     — server-side transient errors (Google
#                                 Sheets API occasionally returns these
#                                 for 30s – a few minutes at a time).
RETRYABLE_MARKERS = (
    # Rate limits
    "429",
    "Quota exceeded",
    "RESOURCE_EXHAUSTED",
    "rateLimitExceeded",
    # Transient HTTP 5xx from Google Sheets API
    "[500]",
    "[502]",
    "[503]",
    "[504]",
    "Service is currently unavailable",
    "Internal error encountered",
    "Backend Error",
    "backendError",
    "internalError",
)

# Longer tail so transient 5xx outages (usually < 2 min) self-heal
# within a single job rather than killing the whole workflow. Total
# worst-case wall time: 2+5+15+30+60 = 112 s across 5 retries.
DEFAULT_RETRY_DELAYS_S = (2.0, 5.0, 15.0, 30.0, 60.0)


def _is_retryable_error(exc: Exception) -> bool:
    """Return True if *exc* is a transient Google Sheets API error."""
    msg = str(exc)
    return any(marker in msg for marker in RETRYABLE_MARKERS)


# Backwards-compatible alias — the old name survives so existing tests
# and any out-of-tree callers keep working.
_is_retryable_quota_error = _is_retryable_error


def _with_quota_retries(fn: Callable[[], _T], *, op: str) -> _T:
    """Retry Google Sheets calls on transient (quota or 5xx) errors."""
    delays = DEFAULT_RETRY_DELAYS_S
    for i in range(len(delays) + 1):
        try:
            return fn()
        except Exception as exc:
            if not _is_retryable_error(exc) or i == len(delays):
                raise
            delay = delays[i]
            log.warning(
                "sheets_io: %s hit transient error (%s); retrying in %.1fs",
                op, type(exc).__name__, delay,
            )
            time.sleep(delay)
    raise RuntimeError(f"unreachable retry loop for op={op}")


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
    sh = _with_quota_retries(lambda: client.open_by_key(sheet_id), op="open_by_key(read)")
    ws = _with_quota_retries(lambda: sh.worksheet(worksheet), op=f"worksheet({worksheet})")
    records = _with_quota_retries(ws.get_all_records, op=f"get_all_records({worksheet})")
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    df["_row"] = range(2, len(df) + 2)
    return df


def worksheet_exists(client, sheet_id: str, worksheet: str) -> bool:
    """Return True if *worksheet* exists in the spreadsheet."""
    sh = _with_quota_retries(lambda: client.open_by_key(sheet_id), op="open_by_key(exists)")
    try:
        _with_quota_retries(lambda: sh.worksheet(worksheet), op=f"worksheet_exists({worksheet})")
        return True
    except Exception:
        return False


def list_data_worksheets(
    client,
    sheet_id: str,
    exclude: set[str] | None = None,
) -> list[str]:
    """List worksheet tabs that look like device data sources.

    Excludes Google's default ``SheetN`` tabs and internal/non-source
    tabs such as ``_errors``, ``_devices``, and ``Derived_Daily``.
    """
    sh = _with_quota_retries(lambda: client.open_by_key(sheet_id), op="open_by_key(list_tabs)")
    excluded = DEFAULT_EXCLUDED_TABS if exclude is None else exclude
    return [
        ws.title
        for ws in _with_quota_retries(sh.worksheets, op="worksheets()")
        if ws.title not in excluded and not _DEFAULT_SHEET_RE.match(ws.title)
    ]


def resolve_source_worksheets(client, sheet_id: str, worksheet: str) -> list[str]:
    """Resolve the set of source worksheet tabs for Phase 2 jobs.

    - If ``worksheet`` exists, return it as a singleton list.
    - If ``worksheet`` is ``Sheet1`` and missing, fall back to all
      detected data worksheets (one tab per device).
    """
    if worksheet_exists(client, sheet_id, worksheet):
        return [worksheet]
    if worksheet == "Sheet1":
        return list_data_worksheets(client, sheet_id)
    return []


def _ensure_header_columns(ws, columns: list[str]) -> dict[str, int]:
    """Make sure every column in *columns* exists in the worksheet header.

    Returns a mapping ``{column_name: 1-indexed_col_number}``.
    Missing columns are appended to the right of the existing header.
    """
    header = _with_quota_retries(lambda: ws.row_values(1), op=f"row_values({ws.title})")
    col_to_idx: dict[str, int] = {name: i + 1 for i, name in enumerate(header) if name}
    missing = [c for c in columns if c not in col_to_idx]
    if missing:
        new_header = header + missing
        # Write the full header row to avoid gaps.
        cells_end = _col_letter(len(new_header))
        _with_quota_retries(
            lambda: ws.update(range_name=f"A1:{cells_end}1", values=[new_header]),
            op=f"update_header({ws.title})",
        )
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

    sh = _with_quota_retries(lambda: client.open_by_key(sheet_id), op="open_by_key(write)")
    ws = _with_quota_retries(lambda: sh.worksheet(worksheet), op=f"worksheet({worksheet})")

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
                _with_quota_retries(
                    lambda: ws.update(range_name=rng, values=[[_format_cell(v)] for v in batch_vals]),
                    op=f"update_range({worksheet}:{rng})",
                )
                written += len(batch_vals)
            else:
                for r, v in zip(batch_rows, batch_vals):
                    _with_quota_retries(
                        lambda r=r, v=v: ws.update(
                            range_name=f"{col_letter}{r}", values=[[_format_cell(v)]]
                        ),
                        op=f"update_cell({worksheet}:{col_letter}{r})",
                    )
                    written += 1
            if sleep_between_batches:
                time.sleep(sleep_between_batches)

    log.info("sheets_io: wrote %d cells across %d columns", written, len(cols))
    return written


__all__ = [
    "SCOPES",
    "DEFAULT_BATCH_SIZE",
    "load_credentials_from_env",
    "list_data_worksheets",
    "read_sheet_as_df",
    "resolve_source_worksheets",
    "worksheet_exists",
    "write_enrichment_columns",
]
