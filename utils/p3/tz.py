"""Display-time-zone helpers for Phase 3 pages.

Phase 3 rule: *all* computation is done in UTC. Any user-facing
timestamp, axis tick, or CSV column that shows local wall-clock is
produced through this module so that the IANA zone can be changed in
one place.

The default display zone is **US/Pacific (PT)** — not UTC — because the
operators who run the dashboard are based at PNNL (Richland, WA). A
user may override via the sidebar selector to anything in
:data:`TZ_PRESETS` or by typing a custom IANA name.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import pandas as pd

try:  # Streamlit is optional at import time so unit tests work headless.
    import streamlit as _st  # type: ignore
except Exception:  # noqa: BLE001
    _st = None  # type: ignore[assignment]


# ── Session key ─────────────────────────────────────────────────────
SESSION_KEY = "p3_display_tz"
DEFAULT_TZ = "America/Los_Angeles"  # PT — primary US West-coast ops default

# Ordered so the sidebar selector feels sensible to a US West-coast op.
# All names are canonical IANA so pandas/zoneinfo resolves them without
# the deprecated ``US/*`` aliases (which need the ``pytz`` legacy map).
TZ_PRESETS: tuple[str, ...] = (
    "UTC",
    "America/Los_Angeles",   # Pacific
    "America/Anchorage",     # Alaska
    "America/New_York",      # Eastern
    "Asia/Seoul",
    "Europe/London",
)


# ── Session resolvers ───────────────────────────────────────────────
def get_display_tz() -> str:
    """Return the currently-selected IANA display time zone name.

    Order:
    1. ``st.session_state["p3_display_tz"]``
    2. :data:`DEFAULT_TZ` (``US/Pacific``)
    """
    if _st is None:
        return DEFAULT_TZ
    try:
        val = _st.session_state.get(SESSION_KEY, None)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        val = None
    return str(val) if val else DEFAULT_TZ


def render_tz_selector_in_sidebar() -> str:
    """Render the display-TZ selector in the sidebar and return the choice.

    Safe to call from any Phase 3 page. Uses a selectbox backed by the
    :data:`TZ_PRESETS` tuple; if a user previously typed a custom zone
    that is not in the preset list, we show it as the first option so
    nothing is silently overwritten.

    Marker
    ------
    The ``<div id="p3-tz-selector-anchor">`` right before the
    selectbox lets the sidebar-relocation JS in
    :mod:`utils.theme` move the selector DOM node into the same host
    that holds the Phase 3 developer toggle, so both controls end up
    as one visual block right above the Phase 3 nav group.
    """
    if _st is None:
        return DEFAULT_TZ

    current = get_display_tz()
    options = list(TZ_PRESETS)
    if current not in options:
        options = [current, *options]

    idx = options.index(current)
    _st.sidebar.markdown(
        '<div id="p3-tz-selector-anchor"></div>',
        unsafe_allow_html=True,
    )
    choice = _st.sidebar.selectbox(
        "Display TZ (UTC is always shown)",
        options,
        index=idx,
        key="_p3_display_tz_widget",
        help="Phase 3 displays every timestamp in UTC. "
             "This selector sets the secondary local zone shown alongside it.",
    )
    # Persist under the stable key so pages read a single source of truth.
    _st.session_state[SESSION_KEY] = choice
    return choice


# ── Conversion / formatting primitives ──────────────────────────────
def to_utc(dt: datetime | pd.Timestamp | None) -> pd.Timestamp | None:
    """Coerce ``dt`` to a tz-aware UTC :class:`pd.Timestamp`.

    Naive values are assumed to already be UTC (Phase 2 enforces this
    in sheets_client). ``None`` / NaT is returned unchanged.
    """
    if dt is None:
        return None
    ts = pd.Timestamp(dt)
    if pd.isna(ts):
        return None
    if ts.tzinfo is None:
        return ts.tz_localize(timezone.utc)
    return ts.tz_convert(timezone.utc)


def to_local(dt: datetime | pd.Timestamp | None,
             tz_name: str | None = None) -> pd.Timestamp | None:
    """Return ``dt`` in the requested display zone (default: session)."""
    ts = to_utc(dt)
    if ts is None:
        return None
    zone = tz_name or get_display_tz()
    try:
        return ts.tz_convert(zone)
    except Exception:  # noqa: BLE001 — unknown zone, fall back to UTC
        return ts


def format_dual(dt: datetime | pd.Timestamp | None,
                tz_name: str | None = None,
                fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Return ``"<UTC> UTC  (<local> <TZ>)"`` — the canonical Phase 3 label.

    Short-circuits to ``"—"`` on NaT / None so it is safe to drop
    into Streamlit markdown cells directly.
    """
    ts_utc = to_utc(dt)
    if ts_utc is None:
        return "—"
    zone = tz_name or get_display_tz()
    if zone == "UTC":
        return f"{ts_utc.strftime(fmt)} UTC"
    try:
        local = ts_utc.tz_convert(zone)
        return f"{ts_utc.strftime(fmt)} UTC  ({local.strftime(fmt)} {zone})"
    except Exception:  # noqa: BLE001
        return f"{ts_utc.strftime(fmt)} UTC"


def add_local_columns(
    df: pd.DataFrame,
    time_cols: Iterable[str],
    tz_name: str | None = None,
    suffix_local: str = "_local",
    suffix_tz: str = "_tz",
) -> pd.DataFrame:
    """Return a copy of ``df`` with local-time sibling columns added.

    For every ``col`` in ``time_cols`` that exists in ``df`` we add:

    * ``<col><suffix_local>`` — tz-aware local-time :class:`pd.Timestamp`
    * ``<col><suffix_tz>``    — the IANA zone name (string constant)

    This is what the Field-Replay CSV export uses so downstream
    consumers see UTC and local alongside each other.
    """
    if df is None or df.empty:
        return df
    zone = tz_name or get_display_tz()
    out = df.copy()
    for c in time_cols:
        if c not in out.columns:
            continue
        series = pd.to_datetime(out[c], errors="coerce", utc=True)
        try:
            local = series.dt.tz_convert(zone)
        except Exception:  # noqa: BLE001
            local = series
            zone_for_col = "UTC"
        else:
            zone_for_col = zone
        out[f"{c}{suffix_local}"] = local
        out[f"{c}{suffix_tz}"] = zone_for_col
    return out
