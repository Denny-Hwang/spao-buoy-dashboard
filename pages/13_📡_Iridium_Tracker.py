"""
Page 13 — Iridium Tracker.

Real-time visualisation of the Iridium constellation over a chosen
observer. Controls:

* Observer preset picker (Richland / Sequim / Bering / Arctic / custom).
* Manual lat/lon input + "Use current PT" for quick check-ins.
* Time scrub / "Now" button so the operator can jump to an arbitrary
  UTC instant and see which Iridium sats are above the 8.2° mask.
* Minimum-elevation slider (0–30°).

Everything here is read-only — the page consumes the `_iridium_tle`
Google Sheet tab that the Phase 3 cron populates.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone

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

# Sidebar controls
try:
    _flag = importlib.import_module("utils.p3.__phase3_flag")
    _flag.render_sidebar_controls()
except Exception as exc:  # noqa: BLE001
    st.sidebar.caption(f"Phase 3 controls unavailable: {exc}")


# ── Load TLE -----------------------------------------------------------
try:
    tle_io = importlib.import_module("utils.p3.tle_io")
    sky_plot = importlib.import_module("utils.p3.viz.sky_plot")
    sgp4_engine = importlib.import_module("utils.p3.sgp4_engine")
    iridium_link = importlib.import_module("utils.p3.iridium_link")
    p3_tz = importlib.import_module("utils.p3.tz")
except Exception as exc:  # noqa: BLE001
    st.error(f"Phase 3 modules unavailable: {exc}")
    st.stop()


sats = tle_io.load_iridium_tle()
if not sats:
    st.warning(
        "No Iridium TLE data found. Trigger the `enrichment_iridium_tle` "
        "GitHub Action to populate the `_iridium_tle` tab, then reload."
    )
    st.stop()


# ── Observer panel -----------------------------------------------------
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


# ── Time controls ------------------------------------------------------
st.subheader("Time")
t1, t2, t3 = st.columns([2, 1, 1])
raw_input = t1.text_input(
    "UTC timestamp",
    value=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
    key="p13_time",
    help="UTC in YYYY-MM-DD HH:MM. Click Now to jump to the current instant.",
)
if t2.button("Now", key="p13_now"):
    raw_input = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    st.session_state["p13_time"] = raw_input

# Scrub slider: ±30 min from the typed value.
scrub_minutes = t3.slider("Scrub (±minutes)", -30, 30, 0, key="p13_scrub")

try:
    base_dt = pd.to_datetime(raw_input, utc=True, errors="raise")
except Exception:  # noqa: BLE001
    st.error("Could not parse the UTC timestamp. Using current UTC instead.")
    base_dt = pd.Timestamp.now(tz="UTC")
dt = (base_dt + pd.Timedelta(minutes=scrub_minutes)).to_pydatetime()

st.caption(p3_tz.format_dual(dt))


# ── Compute visibility ------------------------------------------------
sky_df = sgp4_engine.sky_positions(sats, dt, obs_lat, obs_lon, min_el_deg=-90.0)
if sky_df.empty:
    st.error("SGP4 failed on every Iridium satellite — TLE data may be corrupt.")
    st.stop()

visible = sky_df[sky_df["el_deg"] > min_el].sort_values("el_deg", ascending=False)
best = visible.iloc[0] if not visible.empty else None

# Attach margin column for the table
def _margin(el):
    return round(iridium_link.link_margin_db(float(el)), 1)

visible = visible.assign(margin_dB=visible["el_deg"].apply(_margin))

# ── KPI strip ---------------------------------------------------------
k1, k2, k3, k4 = st.columns(4)
k1.metric("Visible sats", len(visible))
k2.metric("Best elevation", f"{best['el_deg']:.1f}°" if best is not None else "—")
k3.metric("Best margin", f"{_margin(best['el_deg'])} dB" if best is not None else "—")
k4.metric("Total in TLE", len(sats))


# ── Sky plot + table --------------------------------------------------
sl, sr = st.columns([1.2, 1])
with sl:
    fig = sky_plot.sky_figure(
        sats, dt, obs_lat, obs_lon,
        min_el_deg=float(min_el),
        constellation="Iridium",
        title=f"Iridium sky @ {p3_tz.format_dual(dt)}",
        height=520,
    )
    st.plotly_chart(fig, use_container_width=True)

with sr:
    st.markdown("**Visible satellites**")
    st.dataframe(
        visible[["name", "el_deg", "az_deg", "range_km", "margin_dB"]]
        .rename(columns={"el_deg": "el°", "az_deg": "az°",
                         "range_km": "range (km)"})
        .round({"el°": 1, "az°": 0, "range (km)": 0, "margin_dB": 1}),
        hide_index=True,
        height=420,
        use_container_width=True,
    )


# ── Map (observer + ground tracks) ------------------------------------
st.subheader("Map")
m = folium.Map(location=[obs_lat, obs_lon], zoom_start=4,
               tiles="CartoDB dark_matter", attr="CartoDB")
folium.CircleMarker(
    location=[obs_lat, obs_lon], radius=7, color="#C62828",
    fill=True, fill_color="#C62828", popup="Observer",
).add_to(m)

# Draw the horizon circle at min_el (approx great-circle radius).
horizon_km = sgp4_engine.visibility_radius_km(float(min_el),
                                              iridium_link.H_IRIDIUM_KM)
folium.Circle(
    location=[obs_lat, obs_lon],
    radius=horizon_km * 1000.0,
    color="#0078D4", fill=False, dash_array="8 6",
    popup=f"{min_el}° visibility horizon (~{horizon_km:.0f} km)",
).add_to(m)

# Visible-sat sub-points
for _, row in visible.iterrows():
    sub = sgp4_engine.sat_subpoint(next(s for s in sats if s.name == row["name"]), dt)
    if sub is None:
        continue
    lat_s, lon_s, alt_s = sub
    folium.CircleMarker(
        location=[lat_s, lon_s], radius=5,
        color="#0078D4", fill=True, fill_color="#0078D4",
        popup=f"{row['name']} · el {row['el_deg']:.1f}° · alt {alt_s:.0f} km",
    ).add_to(m)
    folium.PolyLine(
        [[obs_lat, obs_lon], [lat_s, lon_s]],
        color="#58a6ff", weight=1.2, opacity=0.5, dash_array="4 4",
    ).add_to(m)

st_folium(m, height=440, use_container_width=True,
          returned_objects=[])  # disable click round-trip to stay cheap


with st.expander("How to read this page", expanded=False):
    st.markdown(
        """
- **Elevation** is the angle above the horizon (0° = on the horizon,
  90° = overhead). Iridium SBDIX links require **≥ 8.2°**.
- **Link margin** is the deterministic link-budget margin in dB (see
  Phase 3 Overview §4). It is a *lower bound* on real-world margin
  because we don't model antenna tilt, body blockage, or scintillation.
- **Scrub (± minutes)** lets you step backwards or forwards without
  re-typing the timestamp — handy for checking a coming 100 min orbit
  sweep.
"""
    )

render_footer()
