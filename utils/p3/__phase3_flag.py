"""Phase 3 per-page sidebar controls (TZ selector).

The visibility toggle for Phase 3 pages is owned by
``utils.theme.render_phase3_visibility_toggle`` and persisted under
``st.session_state[theme.P3_VISIBILITY_KEY]`` (the canonical key
``"p3_pages_visible"``). The global ``render_sidebar`` in
:mod:`utils.theme` renders that widget on every page, so this module
only adds the per-page TZ selector.

A prior revision rendered a second checkbox bound to the stale key
``"p3_show_iridium"``. The global visibility gate ignored that key,
so users could tick the legacy box and nothing happened. The
duplicate widget has been removed to eliminate the dead control and
keep a single source of truth.
"""

from __future__ import annotations

import streamlit as st

from utils.p3 import tz as _tz
from utils.theme import P3_VISIBILITY_KEY


def phase3_enabled() -> bool:
    """Return True if the user has opted in to show Phase 3 analysis widgets.

    Reads the canonical ``P3_VISIBILITY_KEY`` so callers agree with the
    sidebar toggle rendered by :func:`utils.theme.render_phase3_visibility_toggle`.
    """
    return bool(st.session_state.get(P3_VISIBILITY_KEY, False))


def render_sidebar_controls() -> None:
    """Render the Phase 3 per-page sidebar controls.

    Currently only the display-TZ selector; the visibility toggle is
    owned by :func:`utils.theme.render_sidebar`.
    """
    _tz.render_tz_selector_in_sidebar()
