"""Shared playback controls for Phase 3 pages.

Every "Play / Pause + speed multiplier" control strip on the Tracker,
Field Replay and TX Simulator pages flows through this module so the
UX is uniform and the session-state keys don't collide.

Playback engine
---------------
We rely on the community ``streamlit-autorefresh`` component to rerun
the Streamlit script at a fixed cadence while playback is active.
Each page decides what to advance on rerun (a scrub slider, an event
index, a frame counter).

Speed multipliers mirror the HTML prototype (1× / 10× / 60× / 300×).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import streamlit as st

# 1× = 1 real-time second per rerun tick. Higher multipliers compress
# time so operators can watch a 6 h simulation in under a minute.
SPEED_OPTIONS: tuple[tuple[str, int], ...] = (
    ("1×", 1),
    ("10×", 10),
    ("60×", 60),
    ("300×", 300),
)

# Autorefresh tick interval in milliseconds — every tick the caller
# advances its slider by ``speed`` units, so 500 ms × 60× = 30 seconds
# of simulated time per tick. This feels right on a deployed Streamlit
# Cloud app without flooding the server with reruns.
DEFAULT_TICK_MS = 500


@dataclass
class PlaybackState:
    """Snapshot of a playback controller returned to the caller."""
    playing: bool
    speed_units: int   # units of caller-defined step per tick
    tick_ms: int


def _get_autorefresh():
    """Import streamlit-autorefresh lazily; tolerate missing dep."""
    try:
        from streamlit_autorefresh import st_autorefresh
    except Exception:  # noqa: BLE001
        return None
    return st_autorefresh


def render_play_controls(
    key_prefix: str,
    *,
    label: str = "Playback",
    help_text: str | None = None,
    tick_ms: int = DEFAULT_TICK_MS,
    allowed_speeds: Iterable[tuple[str, int]] | None = None,
) -> PlaybackState:
    """Render a Play/Pause + speed radio + optional status caption.

    Caller uses the returned :class:`PlaybackState` to decide, on each
    rerun, whether and how far to advance its position. Typical usage
    in a Streamlit page:

        state = playback.render_play_controls("p13")
        if state.playing:
            current = st.session_state.get("p13_scrub", 0)
            st.session_state["p13_scrub"] = (current + state.speed_units) % MAX

    All session-state keys are namespaced under ``{key_prefix}_pb_*``
    so multiple controllers can live on the same page.
    """
    opts = tuple(allowed_speeds) if allowed_speeds else SPEED_OPTIONS
    playing_key = f"{key_prefix}_pb_playing"
    speed_key = f"{key_prefix}_pb_speed"
    tick_key = f"{key_prefix}_pb_tick"

    if playing_key not in st.session_state:
        st.session_state[playing_key] = False
    if speed_key not in st.session_state:
        st.session_state[speed_key] = opts[0][0]

    cols = st.columns([1, 1, 3, 2])

    def _toggle_play():
        st.session_state[playing_key] = not st.session_state.get(playing_key, False)

    cols[0].markdown(f"**{label}**")
    cols[1].button(
        "⏸ Pause" if st.session_state[playing_key] else "▶ Play",
        key=f"{key_prefix}_pb_button",
        on_click=_toggle_play,
        help=help_text or "Start / stop automatic playback.",
    )

    speed_labels = [label_ for label_, _ in opts]
    speed_choice = cols[2].radio(
        "Speed",
        speed_labels,
        index=speed_labels.index(
            st.session_state.get(speed_key, opts[0][0])
            if st.session_state.get(speed_key, opts[0][0]) in speed_labels
            else opts[0][0]
        ),
        horizontal=True,
        key=speed_key,
        label_visibility="collapsed",
    )
    speed_units = {lab: val for lab, val in opts}[speed_choice]

    status = (
        f"⏵ playing at {speed_choice} "
        f"({tick_ms} ms × {speed_units} units/tick)"
        if st.session_state[playing_key]
        else "⏸ paused — click Play to start"
    )
    cols[3].caption(status)

    # Kick the autorefresh component only while playing, so we don't
    # burn server reruns on idle pages.
    if st.session_state[playing_key]:
        refresher = _get_autorefresh()
        if refresher is not None:
            refresher(
                interval=tick_ms,
                key=f"{key_prefix}_pb_refresher",
                limit=None,
            )
        else:
            st.warning(
                "Playback requires the `streamlit-autorefresh` package. "
                "Install it (`pip install streamlit-autorefresh`) then "
                "reload the app. Playback is disabled until then."
            )
            st.session_state[playing_key] = False

    return PlaybackState(
        playing=bool(st.session_state[playing_key]),
        speed_units=speed_units,
        tick_ms=tick_ms,
    )


def advance_circular(key: str, step: int, modulus: int) -> int:
    """Helper: advance ``st.session_state[key]`` by ``step`` modulo ``modulus``.

    Returns the new value so callers can render immediately with it.
    """
    cur = int(st.session_state.get(key, 0))
    nxt = (cur + step) % max(1, modulus)
    st.session_state[key] = nxt
    return nxt
