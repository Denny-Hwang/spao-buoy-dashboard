"""
Page 13 — Iridium Tracker.

Real-time visualisation of the Iridium constellation over any observer.

Operator-facing controls:

* Observer preset / custom lat-lon.
* **UTC timestamp** text input with a Now / ±scrub slider — modelled
  after the HTML prototype's time controls.
* **Minimum-elevation** slider (0–30°, default 8°).
* **Map tile** selector (Satellite / Terrain / Dark). **Default is
  satellite** per operator preference.

The map is an overlay in the spirit of the HTML prototype: observer
in red, visible Iridium sub-points in blue, dashed connection lines
from observer to each visible sat, and a dashed great-circle horizon
at the elevation mask.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timezone

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

st.set_page_config(page_title="Iridium Tracker", page_icon="📡", layout="wide")

from utils.theme import (  # noqa: E402
    render_header, render_footer, render_sidebar, inject_custom_css,
    require_phase3_visible, PNNL_BLUE,
)

inject_custom_css()
render_sidebar()
render_header()
require_phase3_visible()

st.markdown(
    f'<h1 style="color:{PNNL_BLUE}; margin-top:0;">📡 Iridium Tracker</h1>',
    unsafe_allow_html=True,
)

# Sidebar controls (Phase 3 toggle + TZ selector).
try:
    _flag = importlib.import_module("utils.p3.__phase3_flag")
    _flag.render_sidebar_controls()
except Exception as exc:  # noqa: BLE001
    st.sidebar.caption(f"Phase 3 controls unavailable: {exc}")

# ── Phase 3 modules -------------------------------------------------
try:
    tle_io = importlib.import_module("utils.p3.tle_io")
    sky_plot = importlib.import_module("utils.p3.viz.sky_plot")
    sgp4_engine = importlib.import_module("utils.p3.sgp4_engine")
    iridium_link = importlib.import_module("utils.p3.iridium_link")
    p3_tz = importlib.import_module("utils.p3.tz")
    overlay = importlib.import_module("utils.p3.viz.map_overlay")
except Exception as exc:  # noqa: BLE001
    st.error(f"Phase 3 modules unavailable: {exc}")
    st.stop()


# ── TLE load + refresh -----------------------------------------------
refresh_col, info_col = st.columns([1, 5])
if refresh_col.button("🔄 Refresh TLE", key="p13_refresh_tle",
                      help="Clear the in-process TLE cache and re-read "
                           "the `_iridium_tle` Sheet tab."):
    tle_io.force_refresh_tle()
    st.rerun()

sats = tle_io.load_iridium_tle()
if not sats:
    info_col.warning(
        "No Iridium TLE data found in the `_iridium_tle` Sheet tab. "
        "Trigger the **Phase 3 TLE Enrichment** GitHub Action and then "
        "click **🔄 Refresh TLE**."
    )
    st.stop()
info_col.caption(f"Loaded {len(sats)} Iridium satellites from `_iridium_tle`.")


# ── Observer panel ---------------------------------------------------
st.subheader("Observer")
PRESETS = {
    "Richland, WA":    (46.28, -119.28),
    "Sequim, WA":      (48.08, -123.05),
    "Bering Sea":      (58.35, -169.98),
    "FY25 deploy":     (58.23, -169.91),
    "Arctic (75°N)":   (75.00, -170.00),
    "Custom":          None,
}
c1, c2, c3, c4 = st.columns([1.2, 1, 1, 1])
preset_name = c1.selectbox("Preset", list(PRESETS.keys()), index=0, key="p13_preset")
default_latlon = PRESETS[preset_name] or (46.28, -119.28)
obs_lat = c2.number_input("Lat (°)", value=float(default_latlon[0]),
                          step=0.01, format="%.4f", key="p13_lat")
obs_lon = c3.number_input("Lon (°)", value=float(default_latlon[1]),
                          step=0.01, format="%.4f", key="p13_lon")
min_el = c4.slider("Min elevation (°)", 0, 30, 8, key="p13_min_el")


# ── Time controls ---------------------------------------------------
# Using an on_click callback for the "Now" button avoids
# StreamlitAPIException: writing to ``st.session_state[key]`` AFTER the
# widget with that key has been instantiated is not allowed. Callbacks
# run *before* widget re-instantiation on the next rerun.
st.subheader("Time")

if "p13_time" not in st.session_state:
    st.session_state["p13_time"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

def _set_now():
    st.session_state["p13_time"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    # reset scrub to 0 so "Now" means the wall-clock instant.
    st.session_state["p13_scrub"] = 0

t1, t2, t3 = st.columns([2, 1, 1])
t1.text_input("UTC timestamp", key="p13_time",
              help="UTC in YYYY-MM-DD HH:MM. Click Now to jump to the current instant.")
t2.button("Now (UTC)", key="p13_now", on_click=_set_now)
# Widened scrub range so autoplay at 60× / 300× has somewhere to travel
# without immediately wrapping: ±180 min covers ~1.8 Iridium orbits.
t3.slider("Scrub (± minutes)", -180, 180, 0, key="p13_scrub")

# ── Playback controls (Play / Pause + speed) ------------------------
# Reuse the shared Phase 3 playback controller so the UX is identical
# across Tracker / Field Replay / TX Simulator.
playback = importlib.import_module("utils.p3.viz.playback")
pb = playback.render_play_controls(
    "p13",
    label="Scrub playback",
    help_text="Auto-advances the scrub slider. Speed multiplies minutes "
              "of simulated time per ~0.5 s tick — 60× ≈ 30 s of real "
              "orbit motion per tick.",
)
if pb.playing:
    # speed_units is "minutes per tick" on the Tracker because the
    # scrubbing unit is minutes.
    _cur = int(st.session_state.get("p13_scrub", 0))
    _nxt = _cur + pb.speed_units
    if _nxt > 180:
        _nxt = -180  # wrap around so playback doesn't dead-end
    st.session_state["p13_scrub"] = _nxt

scrub_minutes = int(st.session_state.get("p13_scrub", 0))

try:
    base_dt = pd.to_datetime(st.session_state["p13_time"],
                             utc=True, errors="raise")
except Exception:  # noqa: BLE001
    st.error("Could not parse the UTC timestamp. Falling back to current UTC.")
    base_dt = pd.Timestamp.now(tz="UTC")
dt = (base_dt + pd.Timedelta(minutes=scrub_minutes)).to_pydatetime()

st.caption(p3_tz.format_dual(dt))


# ── Compute visibility -----------------------------------------------
sky_df = sgp4_engine.sky_positions(sats, dt, obs_lat, obs_lon, min_el_deg=-90.0)
if sky_df.empty:
    st.error("SGP4 failed on every Iridium satellite — TLE data may be corrupt.")
    st.stop()

visible = sky_df[sky_df["el_deg"] > min_el].sort_values("el_deg", ascending=False)
best = visible.iloc[0] if not visible.empty else None

def _margin(el):
    return round(iridium_link.link_margin_db(float(el)), 1)

visible = visible.assign(margin_dB=visible["el_deg"].apply(_margin))


# ── KPI strip --------------------------------------------------------
k1, k2, k3, k4 = st.columns(4)
k1.metric("Visible sats", len(visible))
k2.metric("Best elevation", f"{best['el_deg']:.1f}°" if best is not None else "—")
k3.metric("Best margin", f"{_margin(best['el_deg'])} dB" if best is not None else "—")
k4.metric("Total in TLE", len(sats))


# ── Overlay map + sky plot ------------------------------------------
sl, sr = st.columns([1.3, 1])
with sl:
    tile_choice = st.radio(
        "Map tile", overlay.TILE_LABELS,
        index=0, horizontal=True, key="p13_tile",
        help="Choose the basemap. Satellite is the default so ocean "
             "deployments read like a real-world view.",
    )
    m = overlay.build_overlay_map(
        observer_lat=obs_lat,
        observer_lon=obs_lon,
        dt=dt,
        iridium_sats=sats,
        min_el_deg=float(min_el),
        tile=tile_choice,
    )
    st_folium(m, height=520, use_container_width=True,
              returned_objects=[])

with sr:
    st.plotly_chart(
        sky_plot.sky_figure(
            sats, dt, obs_lat, obs_lon,
            min_el_deg=float(min_el),
            constellation="Iridium",
            title=None,
            height=520,
        ),
        use_container_width=True,
    )

# ── Visible-sat table -----------------------------------------------
st.markdown("**Visible satellites**")
st.dataframe(
    visible[["name", "el_deg", "az_deg", "range_km", "margin_dB"]]
    .rename(columns={"el_deg": "el°", "az_deg": "az°",
                     "range_km": "range (km)"})
    .round({"el°": 1, "az°": 0, "range (km)": 0, "margin_dB": 1}),
    hide_index=True,
    height=260,
    use_container_width=True,
)


with st.expander("How to read this page", expanded=False):
    st.markdown(
        """
- **Elevation** is the angle above the horizon (0° = on the horizon,
  90° = overhead). Iridium SBDIX links require **≥ 8.2°**.
- **Link margin** is the deterministic link-budget margin in dB.
- The map shows the **observer in red**, **visible Iridium sub-points
  in blue** (ground track under the satellite), **connection lines**
  from observer to each visible sat, and the **dashed circle** is the
  great-circle horizon at the current elevation mask.
- **Scrub (± minutes)** lets you step forward/back without re-typing
  the timestamp — handy for walking through a 100-minute orbit sweep.
"""
    )

render_footer()
