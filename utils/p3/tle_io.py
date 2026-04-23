"""Read (and optionally fetch) TLE data for Phase 3.

The Streamlit process only ever *reads* TLE data from the Google
Sheet tabs ``_iridium_tle`` / ``_gps_tle``. Writes are the job of
``scripts/enrichment_iridium_tle.py`` running under a GitHub Actions
cron every six hours.

Public API:

* :func:`load_iridium_tle` / :func:`load_gps_tle` — return parsed
  :class:`~utils.p3.sgp4_engine.Sat` lists, 1 h Streamlit cache.
* :func:`tle_health` — audit snapshot (n_sats, oldest epoch, source).
* :func:`fetch_celestrak_tle` — pure-requests fetcher used by the cron
  script, safe to call from the ad-hoc workflow dispatcher too.
* :func:`parse_tle_text` — plain-text (3-line) → record dicts,
  exposed for the cron so unit tests don't need a mock Sheet.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import pandas as pd

try:
    import streamlit as _st  # type: ignore
except Exception:  # noqa: BLE001
    _st = None  # type: ignore[assignment]

from utils.p3.sgp4_engine import Sat, parse_tle, tle_epoch

log = logging.getLogger(__name__)


# ── Constants ──────────────────────────────────────────────────────
TAB_IRIDIUM = "_iridium_tle"
TAB_GPS = "_gps_tle"

CELESTRAK_IRIDIUM_NEXT = (
    "https://celestrak.org/NORAD/elements/gp.php"
    "?GROUP=iridium-NEXT&FORMAT=tle"
)
CELESTRAK_IRIDIUM_LEGACY = (
    "https://celestrak.org/NORAD/elements/gp.php"
    "?GROUP=iridium&FORMAT=tle"
)
CELESTRAK_GPS_OPS = (
    "https://celestrak.org/NORAD/elements/gp.php"
    "?GROUP=gps-ops&FORMAT=tle"
)

SHEET_COLUMNS = (
    "satname", "norad_id", "line1", "line2",
    "epoch_utc", "fetched_at_utc", "source_url",
)


# ── Data classes ───────────────────────────────────────────────────
@dataclass(frozen=True)
class TleHealth:
    """Audit summary for a TLE dataset."""
    tab: str
    n_sats: int
    newest_epoch: datetime | None
    oldest_epoch: datetime | None
    fetched_at: datetime | None
    median_age_hours: float | None

    @property
    def ok(self) -> bool:
        """Heuristic: at least 10 sats and median epoch age ≤ 7 d."""
        if self.n_sats < 10:
            return False
        if self.median_age_hours is None:
            return False
        return self.median_age_hours <= 7 * 24


# ── Plain-text parsing ─────────────────────────────────────────────
def parse_tle_text(text: str) -> list[dict]:
    """Parse a CelesTrak 3-line TLE text dump into record dicts.

    Each dict has ``name`` / ``line1`` / ``line2``. Duplicate NORAD
    IDs are folded by keeping the newest epoch.
    """
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    records: list[dict] = []
    i = 0
    while i < len(lines):
        if i + 2 < len(lines) and lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
            name = lines[i].lstrip("0").strip() or f"SAT-{lines[i + 1][2:7].strip()}"
            records.append(dict(name=name, line1=lines[i + 1], line2=lines[i + 2]))
            i += 3
        elif lines[i].startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
            records.append(
                dict(name=f"SAT-{lines[i][2:7].strip()}", line1=lines[i], line2=lines[i + 1])
            )
            i += 2
        else:
            i += 1

    # Deduplicate by NORAD ID (columns 3-7 of line 1) keeping newest epoch.
    by_id: dict[str, dict] = {}
    for r in records:
        try:
            nid = r["line1"][2:7].strip()
            ep = float(r["line1"][20:32])
        except Exception:  # noqa: BLE001
            nid = r["name"]
            ep = 0.0
        cur = by_id.get(nid)
        if cur is None:
            by_id[nid] = {**r, "_ep": ep}
            continue
        if ep > cur["_ep"]:
            by_id[nid] = {**r, "_ep": ep}
    for v in by_id.values():
        v.pop("_ep", None)
    return list(by_id.values())


# ── CelesTrak fetch (cron-side only; no Streamlit dependency) ──────
def fetch_celestrak_tle(url: str, *, timeout_s: float = 30.0) -> str:
    """Fetch a CelesTrak TLE URL and return the raw text.

    Uses ``requests`` (already in the cron requirements). Raises on
    HTTP errors. Intended for :mod:`scripts.enrichment_iridium_tle`.
    """
    import requests  # local import so Streamlit runtime isn't forced to have it
    resp = requests.get(url, timeout=timeout_s, headers={"User-Agent": "SPAO-P3/1.0"})
    resp.raise_for_status()
    return resp.text


# ── Sheet read (Streamlit side) ────────────────────────────────────
def _read_tab(tab: str, sheet_id: str | None = None) -> pd.DataFrame:
    """Read a TLE tab from the configured Google Sheet.

    Returns an empty DataFrame if the tab is missing — callers treat
    that as "no TLE available" rather than raising, so the Tracker /
    Field-Replay pages can render a friendly "run the TLE cron first"
    message instead of a stack trace.
    """
    from utils.sheets_client import _open_sheet, SHEET_ID  # local to avoid cycles

    target_id = sheet_id or SHEET_ID
    try:
        sheet = _open_sheet(target_id)
        ws = sheet.worksheet(tab)
        values = ws.get_all_values()
    except Exception as exc:  # noqa: BLE001
        log.warning("P3: cannot read %s tab (%s)", tab, exc)
        return pd.DataFrame(columns=list(SHEET_COLUMNS))
    if not values or len(values) < 2:
        return pd.DataFrame(columns=list(SHEET_COLUMNS))
    header = [h.strip() for h in values[0]]
    rows = values[1:]
    df = pd.DataFrame(rows, columns=header)
    # Coerce dtypes
    for col in ("epoch_utc", "fetched_at_utc"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
    return df


def _df_to_sats(df: pd.DataFrame) -> list[Sat]:
    """Turn a tab DataFrame into :class:`Sat` objects."""
    if df is None or df.empty:
        return []
    records = df[["satname", "line1", "line2"]].rename(
        columns={"satname": "name"}
    ).to_dict("records")
    return parse_tle(records)


def _cached(fn):
    """Wrap ``fn`` in :func:`st.cache_data(ttl=3600)` when available."""
    if _st is None:
        return fn
    try:
        return _st.cache_data(ttl=3600, show_spinner=False)(fn)
    except Exception:  # noqa: BLE001
        return fn


@_cached
def _load_iridium_tle_cached(sheet_id: str | None = None) -> list[Sat]:
    return _df_to_sats(_read_tab(TAB_IRIDIUM, sheet_id))


@_cached
def _load_gps_tle_cached(sheet_id: str | None = None) -> list[Sat]:
    return _df_to_sats(_read_tab(TAB_GPS, sheet_id))


def _drop_cache(fn) -> None:
    """Best-effort ``st.cache_data.clear()`` for one function."""
    clearer = getattr(fn, "clear", None)
    if callable(clearer):
        try:
            clearer()
        except Exception:  # noqa: BLE001
            pass


def load_iridium_tle(sheet_id: str | None = None) -> list[Sat]:
    """Return parsed Iridium satellites from the ``_iridium_tle`` tab.

    Empty results are deliberately *not* cached: when the cron has not
    yet populated the sheet (or the read transiently fails) we don't
    want to lock the page into "no data" for the full 1 h TTL. The
    next call after the cron writes will see fresh data.
    """
    sats = _load_iridium_tle_cached(sheet_id)
    if not sats:
        _drop_cache(_load_iridium_tle_cached)
    return sats


def load_gps_tle(sheet_id: str | None = None) -> list[Sat]:
    """Return parsed GPS satellites — same empty-skip semantics as Iridium."""
    sats = _load_gps_tle_cached(sheet_id)
    if not sats:
        _drop_cache(_load_gps_tle_cached)
    return sats


def force_refresh_tle() -> None:
    """Clear both TLE caches so the next call re-reads the Sheet.

    Used by the ``Refresh TLE`` button on the Tracker page so operators
    can pull data immediately after triggering the cron.
    """
    _drop_cache(_load_iridium_tle_cached)
    _drop_cache(_load_gps_tle_cached)


def _health_from_sats(tab: str, sats: list[Sat],
                      fetched_at: datetime | None = None) -> TleHealth:
    if not sats:
        return TleHealth(tab=tab, n_sats=0, newest_epoch=None,
                         oldest_epoch=None, fetched_at=fetched_at,
                         median_age_hours=None)
    epochs = [tle_epoch(s) for s in sats]
    epochs_valid = [e for e in epochs if e is not None]
    if not epochs_valid:
        return TleHealth(tab=tab, n_sats=len(sats), newest_epoch=None,
                         oldest_epoch=None, fetched_at=fetched_at,
                         median_age_hours=None)
    now = datetime.now(timezone.utc)
    ages_hr = [(now - e).total_seconds() / 3600.0 for e in epochs_valid]
    ages_hr.sort()
    med = ages_hr[len(ages_hr) // 2]
    return TleHealth(
        tab=tab,
        n_sats=len(sats),
        newest_epoch=max(epochs_valid),
        oldest_epoch=min(epochs_valid),
        fetched_at=fetched_at,
        median_age_hours=med,
    )


def tle_health(tab: str, sheet_id: str | None = None) -> TleHealth:
    """Return audit information for ``tab`` (``_iridium_tle`` / ``_gps_tle``)."""
    df = _read_tab(tab, sheet_id)
    sats = _df_to_sats(df)
    fetched_at = None
    if not df.empty and "fetched_at_utc" in df.columns:
        try:
            fetched_at = df["fetched_at_utc"].dropna().max()
            if isinstance(fetched_at, pd.Timestamp):
                fetched_at = fetched_at.to_pydatetime()
        except Exception:  # noqa: BLE001
            fetched_at = None
    return _health_from_sats(tab, sats, fetched_at)


# ── Sheet write helper (used by cron) ──────────────────────────────
def build_sheet_rows(records: Iterable[dict],
                     source_url: str,
                     fetched_at: datetime | None = None) -> list[list[str]]:
    """Turn parsed TLE records into 2-D list rows for gspread ``update()``.

    Header row is always first. Uses the canonical column order in
    :data:`SHEET_COLUMNS`.
    """
    fetched_at = fetched_at or datetime.now(timezone.utc)
    rows: list[list[str]] = [list(SHEET_COLUMNS)]
    for r in records:
        line1 = str(r.get("line1", ""))
        line2 = str(r.get("line2", ""))
        norad = line1[2:7].strip() if len(line1) >= 7 else ""
        # Epoch string derived from line1 (YYDDD.DDDDDDDD)
        epoch_iso = ""
        try:
            y = int(line1[18:20])
            d = float(line1[20:32])
            year = 2000 + y if y < 57 else 1900 + y
            ep = datetime(year, 1, 1, tzinfo=timezone.utc) + pd.Timedelta(days=d - 1)
            epoch_iso = ep.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:  # noqa: BLE001
            pass
        rows.append([
            str(r.get("name", "")),
            norad,
            line1,
            line2,
            epoch_iso,
            fetched_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            source_url,
        ])
    return rows


def env_sheet_id() -> str | None:
    """Return the Google Sheet ID the cron should target.

    Reads ``GOOGLE_SHEETS_ID`` env var (set by the GitHub Actions
    workflow); falls back to the SHEET_ID baked into ``sheets_client``
    so local ad-hoc runs work unchanged.
    """
    from utils.sheets_client import SHEET_ID  # local to avoid import cycles
    return os.environ.get("GOOGLE_SHEETS_ID") or SHEET_ID
