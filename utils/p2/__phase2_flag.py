"""Phase 2 feature toggle helpers."""

import streamlit as st


def phase2_enrichment_visible() -> bool:
    """Return True if the user has opted in to see Phase 2 enriched columns."""
    return bool(st.session_state.get("p2_show_enriched", False))


def render_toggle_in_sidebar() -> None:
    """Render the Phase 2 enrichment toggle in the Streamlit sidebar."""
    st.sidebar.checkbox(
        "Show Phase 2 enriched columns",
        key="p2_show_enriched",
        value=False,
    )
