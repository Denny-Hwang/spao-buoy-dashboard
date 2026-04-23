"""Phase 3 feature toggle + TZ selector helpers.

Each Phase 3 page calls ``render_sidebar_controls()`` at the top so
the user always sees the same compact control strip:

    [x] Show Phase 3 RF analysis
    Display TZ: [ US/Pacific ▾ ]

The TZ selection is stored under ``st.session_state["p3_display_tz"]``
and consumed by :mod:`utils.p3.tz` throughout the page.
"""

from __future__ import annotations

import streamlit as st

from utils.p3 import tz as _tz


def phase3_enabled() -> bool:
    """Return True if the user has opted in to show Phase 3 analysis widgets."""
    return bool(st.session_state.get("p3_show_iridium", False))


def render_toggle_in_sidebar() -> None:
    """Render the Phase 3 enable toggle in the Streamlit sidebar."""
    st.sidebar.checkbox(
        "Show Phase 3 RF analysis",
        key="p3_show_iridium",
        value=False,
    )


def render_sidebar_controls() -> None:
    """Full Phase 3 sidebar: enable toggle + display-TZ selector.

    Pages 12–15 all call this at the top so the TZ choice follows the
    user across pages.
    """
    render_toggle_in_sidebar()
    _tz.render_tz_selector_in_sidebar()
