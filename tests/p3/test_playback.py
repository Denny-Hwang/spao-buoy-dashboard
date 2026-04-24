"""Shared Phase 3 playback controller tests.

Verifies that:
* ``SPEED_OPTIONS`` covers the HTML prototype's multipliers,
* ``advance_circular`` wraps at the modulus.

The renderer itself is exercised by the page-import smoke tests and
manual QA; it depends on ``st.columns`` returning widget-capable
objects which the Phase 2 stub harness cannot fake.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

sys.path.insert(0, str(REPO_ROOT / "tests"))
_skel = importlib.import_module("test_p2_skeleton")
_skel._install_stub_modules()  # type: ignore[attr-defined]

from utils.p3.viz import playback  # noqa: E402


def test_speed_options_match_prototype():
    # The HTML prototype shipped 1× / 10× / 60× / 300×. The Tracker
    # page still expects those.
    labels = [lab for lab, _ in playback.SPEED_OPTIONS]
    assert labels == ["1×", "10×", "60×", "300×"]
    # All speeds must be positive ints so the advance math is exact.
    assert all(isinstance(v, int) and v > 0 for _, v in playback.SPEED_OPTIONS)


def test_advance_circular_wraps_at_modulus():
    import streamlit as st  # stubbed
    st.session_state.clear()
    # Start at 0, step 3, modulus 5 → 3, 1 (wraps), 4, 2, 0.
    expected = [3, 1, 4, 2, 0]
    got = [playback.advance_circular("k", 3, 5) for _ in range(5)]
    assert got == expected


def test_advance_circular_handles_zero_modulus():
    import streamlit as st  # stubbed
    st.session_state.clear()
    # max(1, 0) == 1 → value stays 0.
    result = playback.advance_circular("k2", 5, 0)
    assert result == 0


def test_default_tick_ms_is_reasonable():
    # The default tick must stay inside Streamlit Cloud's budget for
    # autorefresh (several reruns per second are fine; faster than
    # 200 ms starts lagging).
    assert 250 <= playback.DEFAULT_TICK_MS <= 2000
