"""Tests for the Phase 3 visibility gate in utils.theme.

The gate is a dev-toggle so the entire Phase 3 surface can be hidden
from users while we validate. These tests exercise the pure-Python
helpers (``phase3_pages_visible``, ``P3_PAGE_SLUGS``) and verify that
the hidden pages still *import* cleanly (they just bail out with a
banner + ``st.stop()``).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Reuse the Phase 2 stub harness so ``streamlit`` / ``gspread`` import cleanly.
sys.path.insert(0, str(REPO_ROOT / "tests"))
_skel = importlib.import_module("test_p2_skeleton")
_install = _skel._install_stub_modules  # type: ignore[attr-defined]
_install()

# Must import *after* the stub is installed.
from utils import theme  # noqa: E402


def test_default_visibility_is_false():
    # Fresh session_state has no key → helper returns False.
    theme.st.session_state.clear()
    assert theme.phase3_pages_visible() is False


def test_toggle_flip_is_respected():
    theme.st.session_state[theme.P3_VISIBILITY_KEY] = True
    assert theme.phase3_pages_visible() is True
    theme.st.session_state[theme.P3_VISIBILITY_KEY] = False
    assert theme.phase3_pages_visible() is False


def test_page_slugs_cover_all_phase3_pages():
    # Each Phase 3 page filename must contain exactly one slug so the
    # CSS hider matches it via the sidebar nav href.
    pages = sorted((REPO_ROOT / "pages").glob("1[2-5]_*.py"))
    assert len(pages) == 4, "expected exactly four Phase 3 pages"
    for page in pages:
        matches = [s for s in theme.P3_PAGE_SLUGS if s in page.name]
        assert len(matches) == 1, (
            f"page {page.name} must match exactly one P3_PAGE_SLUGS entry, "
            f"got {matches}"
        )


def test_require_phase3_visible_stops_when_hidden():
    theme.st.session_state[theme.P3_VISIBILITY_KEY] = False
    with pytest.raises(Exception) as exc:
        theme.require_phase3_visible()
    # Phase 2 stub raises ``_StreamlitStop`` — that's the contract.
    assert "Stop" in type(exc.value).__name__


def test_require_phase3_visible_noop_when_visible():
    theme.st.session_state[theme.P3_VISIBILITY_KEY] = True
    # Must not raise.
    theme.require_phase3_visible()


def test_render_toggle_initialises_session_state_only_once():
    """The widget must NOT clobber an existing user choice on rerun.

    Operators were hitting the bug where toggling the checkbox on, then
    navigating to another Phase 3 page, reset it to off — that happened
    because ``st.checkbox(value=False, key=...)`` was being called every
    rerun. The fix is to seed session_state explicitly *only* if the
    key is missing, and never pass ``value=`` to the widget.
    """
    # User has previously turned the toggle on.
    theme.st.session_state[theme.P3_VISIBILITY_KEY] = True
    theme.render_phase3_visibility_toggle()
    # After the rerun, the user's choice must still be True.
    assert theme.st.session_state[theme.P3_VISIBILITY_KEY] is True


def test_render_toggle_seeds_default_when_absent():
    theme.st.session_state.pop(theme.P3_VISIBILITY_KEY, None)
    theme.render_phase3_visibility_toggle()
    assert theme.st.session_state[theme.P3_VISIBILITY_KEY] is False
