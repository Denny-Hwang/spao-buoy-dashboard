"""
Page 15 — TX Simulator.

What-if planning tool. Given an observer + start time + duration the
simulator propagates the Iridium constellation every ``step_s``
seconds, scores each TX attempt, and then offers the operator an
animated play-back of the sky and the KPI strip.

Design choice per Phase 3 plan
------------------------------
* **Primary animation** — Plotly frames (serverless, single component,
  Play/Pause + slider comes for free).
* **Fallback / map sync** — a Streamlit slider drives an auxiliary
  Folium map + KPI numbers below the Plotly figure, so the user can
  step through the same timeline on a geographic view.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

st.set_page_config(page_title="TX Simulator", page_icon="⚡", layout="wide")

from utils.theme import (  # noqa: E402
    render_header, render_footer, render_sidebar, inject_custom_css,
    require_phase3_visible, PNNL_BLUE,
)

inject_custom_css()
render_sidebar()
render_header()
require_phase3_visible()

st.markdown(
    f'<h1 style="color:{PNNL_BLUE}; margin-top:0;">⚡ TX Simulator</h1>',
    unsafe_allow_html=True,
)

# Sidebar toggle + TZ.
try:
    _flag = importlib.import_module("utils.p3.__phase3_flag")
    _flag.render_sidebar_controls()
except Exception as exc:  # noqa: BLE001
    st.sidebar.caption(f"Phase 3 controls unavailable: {exc}")

# Phase 3 modules.
try:
    tle_io = importlib.import_module("utils.p3.tle_io")
    sgp4_engine = importlib.import_module("utils.p3.sgp4_engine")
    iridium_link = importlib.import_module("utils.p3.iridium_link")
    sim_playback = importlib.import_module("utils.p3.viz.sim_playback")
    sky_plot = importlib.import_module("utils.p3.viz.sky_plot")
    p3_tz = importlib.import_module("utils.p3.tz")
except Exception as exc:  # noqa: BLE001
    st.error(f"Phase 3 modules unavailable: {exc}")
    st.stop()

sats = tle_io.load_iridium_tle()
if not sats:
    st.warning("No Iridium TLE data found yet — run the enrichment cron first.")
    st.stop()


# ── Simulator controls -----------------------------------------------
st.subheader("Simulation parameters")
left, mid, right = st.columns(3)

PRESETS = {
    "Richland, WA":  (46.28, -119.28),
    "Sequim, WA":    (48.08, -123.05),
    "Bering Sea":    (58.35, -169.98),
    "FY25 deploy":   (58.23, -169.91),
    "Arctic (75°N)": (75.00, -170.00),
}
preset = left.selectbox("Observer preset", list(PRESETS.keys()), index=0,
                        key="p15_preset")
lat0, lon0 = PRESETS[preset]
obs_lat = left.number_input("Lat (°)", value=float(lat0),
                            step=0.01, format="%.4f", key="p15_lat")
obs_lon = left.number_input("Lon (°)", value=float(lon0),
                            step=0.01, format="%.4f", key="p15_lon")

start_str = mid.text_input(
    "Start UTC", value=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
    key="p15_start",
)
duration_h = mid.slider("Duration (hours)", 1, 24, 6, key="p15_dur")
step_s = mid.select_slider("Step (seconds per frame)",
                           options=[30, 60, 120, 300], value=60,
                           key="p15_step")

min_el = right.slider("Min elevation (°)", 0, 30, 8, key="p15_min_el")
tx_timeout = right.slider("TX timeout (s)", 30, 300, 120, 10,
                          key="p15_to",
                          help="Max allowed wait per TX attempt (operator setting).")
n_attempts = right.slider("Max attempts per TX", 1, 5, 3, key="p15_attempts")

# Parse start time.
try:
    start_utc = pd.to_datetime(start_str, utc=True, errors="raise").to_pydatetime()
except Exception:  # noqa: BLE001
    st.error("Could not parse the start UTC. Using current instant.")
    start_utc = datetime.now(timezone.utc)

st.caption(f"Simulated window: {p3_tz.format_dual(start_utc)} "
           f"→ {p3_tz.format_dual(start_utc + timedelta(hours=duration_h))}")


# ── Run -------------------------------------------------------------
run = st.button("▶ Run Simulation", type="primary", key="p15_go")


@st.cache_data(ttl=600, show_spinner=False)
def _run_sim(lat, lon, start_iso, duration_h, step_s, min_el, n_tle):
    """Cache the frame calculation by input signature.

    ``n_tle`` is part of the key so when the TLE tab is refreshed the
    cache entry invalidates automatically.
    """
    start = pd.to_datetime(start_iso, utc=True).to_pydatetime()
    frames = sim_playback.compute_frames(
        sats,
        start_utc=start,
        duration_h=duration_h,
        lat_deg=lat,
        lon_deg=lon,
        min_el_deg=min_el,
        step_s=step_s,
    )
    return frames


if run or "p15_frames" in st.session_state:
    if run:
        with st.spinner("Propagating constellation over the window…"):
            frames_df = _run_sim(
                float(obs_lat), float(obs_lon),
                start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                int(duration_h), int(step_s), int(min_el),
                n_tle=len(sats),
            )
        st.session_state["p15_frames"] = frames_df
    frames_df = st.session_state["p15_frames"]

    kpi = sim_playback.kpi_series(frames_df)

    # ── Top-level KPIs -------------------------------------------------
    vis_mean = kpi["n_visible"].dropna().mean() if not kpi.empty else None
    best_el_mean = kpi["best_el"].dropna().mean() if not kpi.empty else None
    best_margin_mean = kpi["best_margin"].dropna().mean() if not kpi.empty else None

    # Simulate TX attempts at each frame start using the HTML prototype's rule.
    tx_records: list[dict] = []
    tx_spacing_s = 600  # same 10-minute default as the prototype
    t_next = 0
    for i, r in kpi.iterrows():
        t_sim = (pd.Timestamp(r["t_utc"]) - pd.Timestamp(start_utc)).total_seconds()
        if t_sim < t_next:
            continue
        best_el = r["best_el"] if pd.notna(r["best_el"]) else -1.0
        if best_el <= min_el:
            tx_records.append(dict(
                t_utc=r["t_utc"], ok=False, p=0.0,
                cause="no visible satellite",
                best_el=None, margin=None,
            ))
            t_next = t_sim + tx_spacing_s
            continue
        margin = iridium_link.link_margin_db(best_el)
        # Cumulative probability over attempts, capped by tx_timeout.
        p_cum = 0.0
        total_acq = 0.0
        cause = ""
        for _a in range(n_attempts):
            acq = iridium_link.acquisition_time_s(best_el, margin)
            if total_acq + acq > tx_timeout:
                cause = f"timeout @ {total_acq + acq:.0f}s"
                break
            total_acq += acq
            p_cum = 1.0 - (1.0 - p_cum) * (1.0 - iridium_link.p_success(margin, best_el))
            if p_cum >= 0.97:
                break
        ok = p_cum >= 0.5
        if not ok and not cause:
            cause = f"low P={p_cum:.2f}"
        tx_records.append(dict(
            t_utc=r["t_utc"], ok=ok, p=round(p_cum, 3),
            cause=cause or f"P={p_cum:.2f}",
            best_el=round(float(best_el), 1), margin=round(margin, 1),
        ))
        t_next = t_sim + tx_spacing_s

    tx_df = pd.DataFrame(tx_records)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Avg visible", f"{vis_mean:.1f}" if vis_mean is not None else "—")
    k2.metric("Avg best el",
              f"{best_el_mean:.1f}°" if best_el_mean is not None else "—")
    k3.metric("Avg link margin",
              f"{best_margin_mean:.1f} dB" if best_margin_mean is not None else "—")
    if not tx_df.empty:
        passed = int(tx_df["ok"].sum())
        k4.metric("TX pass / total", f"{passed} / {len(tx_df)}")
    else:
        k4.metric("TX pass / total", "—")

    # ── Animated sky: mode switch (Polar default | Map overlay) -----
    st.subheader("Animated sky")
    mode = st.radio(
        "Visualisation",
        ("Polar sky plot", "Map overlay"),
        index=0, horizontal=True, key="p15_anim_mode",
        help="Polar sky plot — clean top-down view with Plotly's "
             "built-in Play / Pause. Map overlay — world map with "
             "satellite sub-points + dashed link lines scrubbed by a "
             "slider, matching the Tracker page.",
    )

    frame_count = kpi["t_idx"].max() + 1 if not kpi.empty else 1

    if mode == "Polar sky plot":
        # Original Plotly frames-based animation with its own Play bar.
        st.plotly_chart(
            sim_playback.build_playback_figure(
                frames_df, min_el_deg=float(min_el),
                title="Iridium sky — simulated playback",
            ),
            use_container_width=True,
        )
        # Show the slider-driven map BELOW as a supplementary snapshot
        # so both views are still available to the operator.
        st.markdown("##### Synchronised map snapshot")
        if frame_count > 1:
            f_idx = st.slider("Scrub frame", 0, int(frame_count - 1), 0,
                              key="p15_scrub")
        else:
            f_idx = 0
    else:
        # Map-overlay mode: the map IS the animation, advanced by an
        # autoplay loop tied to the shared Phase 3 playback controller.
        playback = importlib.import_module("utils.p3.viz.playback")
        pb = playback.render_play_controls(
            "p15_map",
            label="Map playback",
            help_text="Cycles through simulation frames and re-draws "
                      "the overlay map on each tick.",
            allowed_speeds=(("1×", 1), ("5×", 5), ("10×", 10), ("30×", 30)),
            tick_ms=400,
        )
        if "p15_map_scrub" not in st.session_state:
            st.session_state["p15_map_scrub"] = 0
        if pb.playing:
            nxt = (int(st.session_state["p15_map_scrub"]) + pb.speed_units) % max(1, frame_count)
            st.session_state["p15_map_scrub"] = nxt
        if frame_count > 1:
            f_idx = st.slider("Scrub frame", 0, int(frame_count - 1),
                              int(st.session_state.get("p15_map_scrub", 0)),
                              key="p15_map_scrub")
        else:
            f_idx = 0

    snap = kpi[kpi["t_idx"] == f_idx]
    t_snap = snap["t_utc"].iloc[0] if not snap.empty else start_utc
    n_vis = int(snap["n_visible"].iloc[0]) if not snap.empty else 0
    best_el_snap = snap["best_el"].iloc[0] if not snap.empty else None
    best_margin_snap = snap["best_margin"].iloc[0] if not snap.empty else None

    c1, c2, c3 = st.columns(3)
    c1.metric("Time", p3_tz.format_dual(t_snap))
    c2.metric("Visible", n_vis)
    c3.metric("Best el / margin",
              f"{best_el_snap:.1f}° / {best_margin_snap:.1f} dB"
              if best_el_snap is not None and pd.notna(best_el_snap) else "—")

    # Folium snapshot at the scrubbed instant — HTML-prototype-style
    # overlay: observer + visible sat sub-points + connection lines +
    # horizon ring, on a satellite tile by default.
    try:
        from streamlit_folium import st_folium
        from utils.p3.viz import map_overlay as overlay  # lazy import
        if isinstance(t_snap, pd.Timestamp):
            dt_snap = t_snap.to_pydatetime()
        else:
            dt_snap = pd.Timestamp(t_snap, tz="UTC").to_pydatetime()
        tile_choice = st.radio(
            "Map tile", overlay.TILE_LABELS,
            index=0, horizontal=True, key="p15_tile",
        )
        m = overlay.build_overlay_map(
            observer_lat=float(obs_lat),
            observer_lon=float(obs_lon),
            dt=dt_snap,
            iridium_sats=sats,
            min_el_deg=float(min_el),
            tile=tile_choice,
            zoom_start=3,
        )
        st_folium(m, height=420, use_container_width=True,
                  returned_objects=[])
    except Exception as exc:  # noqa: BLE001
        st.caption(f"Map unavailable: {exc}")

    # ── TX event log -------------------------------------------------
    st.subheader("TX event log")
    if tx_df.empty:
        st.info("No TX attempts in window.")
    else:
        tx_display = tx_df.copy()
        tx_display["t_utc"] = tx_display["t_utc"].apply(
            lambda t: p3_tz.format_dual(t)
        )
        st.dataframe(tx_display, hide_index=True, use_container_width=True,
                     height=240)

else:
    st.info(
        "Configure parameters above and click **Run Simulation**. "
        "The simulation is cached for 10 min so repeated runs with "
        "identical inputs are instant."
    )

render_footer()
