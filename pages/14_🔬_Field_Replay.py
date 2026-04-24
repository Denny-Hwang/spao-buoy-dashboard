"""
Page 14 — Field Replay.

Main Phase 3 analysis page. Runs the satellite-geometry join on a
user-selected slice of data and lets the operator inspect any TX
event in detail:

* **Dataset picker** — Phase 1 live (through the shared Phase 2
  toolbar) or FY25_Deployment preset.
* **Event picker** — a dropdown of ``<timestamp> · <device> · rb1=X`` so
  the operator can jump by case, not by a blind index.
* **Overlay map** — the buoy location, horizon ring, and every visible
  Iridium sat rendered as sub-points with dashed link lines, like the
  HTML prototype. Default tile is satellite.
* **Sky plots** (Iridium + GPS) at the TX epoch.
* **Timeline bar** (GPS → sensors → cap → RB TX).
* **Retrospective verdict** (rule-based text).
* **Counterfactual** GNSS timeout sweep.
* **Correlation** scatters.
* **CSV / Excel downloads** with the full Phase 3 enrichment.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Field Replay", page_icon="🔬", layout="wide")

from utils.theme import (  # noqa: E402
    render_header, render_footer, render_sidebar, inject_custom_css,
    require_phase3_visible, PNNL_BLUE,
)

inject_custom_css()
render_sidebar()
render_header()
require_phase3_visible()

st.markdown(
    f'<h1 style="color:{PNNL_BLUE}; margin-top:0;">🔬 Field Replay</h1>',
    unsafe_allow_html=True,
)

try:
    _flag = importlib.import_module("utils.p3.__phase3_flag")
    _flag.render_sidebar_controls()
except Exception as exc:  # noqa: BLE001
    st.sidebar.caption(f"Phase 3 controls unavailable: {exc}")

# ── Phase 3 modules -------------------------------------------------
try:
    tle_io = importlib.import_module("utils.p3.tle_io")
    tx_join = importlib.import_module("utils.p3.tx_join")
    replay_export = importlib.import_module("utils.p3.replay_export")
    replay_panels = importlib.import_module("utils.p3.viz.replay_panels")
    sky_plot = importlib.import_module("utils.p3.viz.sky_plot")
    overlay = importlib.import_module("utils.p3.viz.map_overlay")
    fy25 = importlib.import_module("utils.p3.fy25_preset")
    p3_tz = importlib.import_module("utils.p3.tz")
except Exception as exc:  # noqa: BLE001
    st.error(f"Phase 3 modules unavailable: {exc}")
    st.stop()


# ── Dataset picker --------------------------------------------------
st.subheader("Dataset")
ds_col, _ = st.columns([1.5, 3])
dataset = ds_col.radio(
    "Select a dataset to replay:",
    ["Phase 1 live data", "FY25_Deployment (preset)"],
    horizontal=True,
    key="p14_dataset",
)
is_fy25 = dataset.startswith("FY25")


# ── Load chosen dataset --------------------------------------------
if is_fy25:
    try:
        df_raw = fy25.load_fy25_frame()
        tle_epoch_for_fy25 = fy25.approx_tle_epoch()
        st.caption(
            f"Using the FY25 Bering-sea preset — {len(df_raw)} events, "
            f"TLE epoch ≈ {tle_epoch_for_fy25.strftime('%Y-%m-%d %H:%M Z')}."
        )
        selected_devices = list(df_raw["Device Tab"].unique())
        time_col, dev_col = "Timestamp", "Device Tab"
        df = df_raw
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not load FY25 preset: {exc}")
        st.stop()
else:
    @st.cache_data(ttl=120)
    def _load_live() -> pd.DataFrame:
        from utils.sheets_client import get_all_data
        try:
            return get_all_data()
        except Exception as exc:  # noqa: BLE001
            st.warning(f"Could not load data: {exc}")
            return pd.DataFrame()
    live = _load_live()
    try:
        toolbar = importlib.import_module("utils.p2.ui_toolbar")
        df, selected_devices, time_col, dev_col = toolbar.render_device_time_filter(
            live, key_prefix="p14",
        )
    except Exception as exc:  # noqa: BLE001
        st.error(f"Toolbar unavailable: {exc}")
        st.stop()
    tle_epoch_for_fy25 = None

if df is None or df.empty:
    st.info("No rows to replay — adjust the filter or pick a device with data.")
    st.stop()


# ── TLE load + refresh ---------------------------------------------
tle_refresh_col, _ = st.columns([1, 5])
if tle_refresh_col.button("🔄 Refresh TLE", key="p14_refresh_tle",
                          help="Re-read `_iridium_tle` / `_gps_tle` tabs."):
    tle_io.force_refresh_tle()
    st.rerun()

iridium_sats = tle_io.load_iridium_tle()
gps_sats = tle_io.load_gps_tle()
if not iridium_sats or not gps_sats:
    st.warning(
        "TLE data is missing in `_iridium_tle` / `_gps_tle`. Trigger "
        "the **Phase 3 TLE Enrichment** GitHub Action and click "
        "**🔄 Refresh TLE**."
    )

if is_fy25:
    st.info(
        "⚠️ FY25 playback uses *current* TLE to propagate back to "
        "2025-09-10. SGP4 accuracy degrades ~1 km/day, so absolute "
        "sat-pass timing is approximate; visibility *counts* and "
        "**rb1 vs geometry** correlations remain representative."
    )


# ── Enrich the frame -----------------------------------------------
with st.spinner("Propagating Iridium + GPS geometry at every TX…"):
    enriched = tx_join.enrich_phase1_frame(
        df, iridium_sats=iridium_sats, gps_sats=gps_sats,
        tle_epoch_utc=tle_epoch_for_fy25,
    )


def _safe_nanmean(series):
    s = pd.to_numeric(series, errors="coerce")
    if s.dropna().empty:
        return "—"
    return f"{s.mean():.1f}"


rb1_mean = _safe_nanmean(enriched.get("RockBLOCK Time")) \
    if "RockBLOCK Time" in enriched.columns \
    else _safe_nanmean(enriched.get("Prev 1st RB Time"))
k1, k2, k3, k4 = st.columns(4)
k1.metric("TX events", len(enriched))
k2.metric("Mean rb1 (s)", rb1_mean)
k3.metric("Mean Iri N_visible", _safe_nanmean(enriched.get("IRI_N_VISIBLE")))
k4.metric("Mean GPS N_visible", _safe_nanmean(enriched.get("GPS_N_VISIBLE")))


# ── Filter ---------------------------------------------------------
st.subheader("Events")
flt1, flt2 = st.columns([1.5, 3])
filter_mode = flt1.selectbox(
    "Filter", ["All events", "GPS failures (Lat=Lon=0 or GPS Valid=NO)",
               "Slow rb1 (≥30 s)", "Retry required (rb2 > 0)",
               "Fast & clean (rb1 < 15 s)"],
    key="p14_filter",
)


def _failed(row) -> bool:
    gv = str(row.get("GPS Valid", "YES")).upper()
    if gv == "NO":
        return True
    lat = pd.to_numeric(row.get("Latitude", row.get("Lat")), errors="coerce")
    lon = pd.to_numeric(row.get("Longitude", row.get("Lon")), errors="coerce")
    if pd.isna(lat) or pd.isna(lon):
        return True
    return float(lat) == 0.0 and float(lon) == 0.0


def _rb1_of(row) -> float:
    v = row.get("RockBLOCK Time", row.get("Prev 1st RB Time", 0.0))
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _rb2_of(row) -> float:
    v = row.get("Prev 2nd RB Time", 0.0)
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


mask = pd.Series(True, index=enriched.index)
if filter_mode.startswith("GPS failures"):
    mask = enriched.apply(_failed, axis=1)
elif filter_mode.startswith("Slow"):
    mask = enriched.apply(lambda r: _rb1_of(r) >= 30.0, axis=1)
elif filter_mode.startswith("Retry"):
    mask = enriched.apply(lambda r: _rb2_of(r) > 0.0, axis=1)
elif filter_mode.startswith("Fast"):
    mask = enriched.apply(lambda r: 0 < _rb1_of(r) < 15.0, axis=1)

filtered = enriched[mask].reset_index(drop=True)
flt2.caption(f"{len(filtered)} / {len(enriched)} events match `{filter_mode}`.")


# ── Events table ---------------------------------------------------
visible_cols = [c for c in [
    "Timestamp", dev_col if dev_col in filtered.columns else "Device Tab",
    "TX Index", "RockBLOCK Time", "Prev 2nd RB Time", "GPS Time",
    "IRI_N_VISIBLE", "IRI_BEST_EL_deg", "IRI_LINK_MARGIN_dB",
    "GPS_N_VISIBLE", "GPS_PDOP",
] if c in filtered.columns]

st.dataframe(
    filtered[visible_cols],
    height=240,
    hide_index=True,
    use_container_width=True,
)


# ── Event picker: DROPDOWN, not slider -----------------------------
if filtered.empty:
    st.info("No events match the current filter.")
else:
    st.subheader("Event detail")

    def _label(i: int) -> str:
        """Build a human label: 'YYYY-MM-DD HH:MM · DEV · rb1=10.5s · IRI=3'."""
        row = filtered.iloc[i]
        ts = pd.to_datetime(row.get("Timestamp"), utc=True, errors="coerce")
        ts_str = ts.strftime("%Y-%m-%d %H:%M") if pd.notna(ts) else "??"
        dev = row.get("Device Tab", row.get("device", "?"))
        rb1 = _rb1_of(row)
        rb2 = _rb2_of(row)
        nv = row.get("IRI_N_VISIBLE", "")
        try:
            nv_str = f"{int(nv)}" if pd.notna(nv) else "?"
        except (TypeError, ValueError):
            nv_str = "?"
        gv = str(row.get("GPS Valid", "YES")).upper()
        fail_tag = " · GPS FAIL" if gv == "NO" else ""
        retry_tag = f" · rb2={rb2:.1f}s" if rb2 > 0 else ""
        return f"{ts_str}  ·  {dev}  ·  rb1={rb1:.1f}s{retry_tag}  ·  IRI={nv_str}{fail_tag}"

    picker_options = list(range(len(filtered)))
    picker_labels = {i: _label(i) for i in picker_options}
    sel_idx = st.selectbox(
        "Select event (case-labelled)",
        picker_options,
        format_func=lambda i: picker_labels[i],
        key="p14_event_select",
    )
    row = filtered.iloc[sel_idx]

    kv_col, map_col = st.columns([1.2, 1])
    with kv_col:
        st.markdown(replay_panels.event_kv_markdown(row, tz_name=p3_tz.get_display_tz()))
    with map_col:
        lat = pd.to_numeric(row.get("Latitude", row.get("Lat")), errors="coerce")
        lon = pd.to_numeric(row.get("Longitude", row.get("Lon")), errors="coerce")
        if pd.notna(lat) and pd.notna(lon) and (float(lat) != 0.0 or float(lon) != 0.0):
            # HTML-demo-style overlay map: observer + visible Iridium
            # sub-points + dashed connection lines + horizon ring.
            try:
                from streamlit_folium import st_folium
                ts = pd.to_datetime(row.get("Timestamp"), utc=True)
                dt = ts.to_pydatetime() if not pd.isna(ts) else None
                tile = st.radio(
                    "Map tile", overlay.TILE_LABELS,
                    index=0, horizontal=True, key="p14_tile",
                )
                m = overlay.build_overlay_map(
                    observer_lat=float(lat),
                    observer_lon=float(lon),
                    dt=dt or datetime.now(timezone.utc),
                    iridium_sats=iridium_sats,
                    min_el_deg=8.2,
                    tile=tile,
                    zoom_start=5,
                    observer_label=f"{row.get('Device Tab', '')} TX",
                )
                st_folium(m, height=340, use_container_width=True,
                          returned_objects=[])
            except Exception as exc:  # noqa: BLE001
                st.caption(f"Map unavailable: {exc}")
        else:
            st.caption("No valid GPS fix — map hidden.")

    st.plotly_chart(replay_panels.timeline_figure(row),
                    use_container_width=True)
    st.markdown(replay_panels.retrospective_verdict(row))

    try:
        ts = pd.to_datetime(row.get("Timestamp"), utc=True)
        dt = ts.to_pydatetime() if not pd.isna(ts) else None
        fix_lat = float(lat) if pd.notna(lat) else 46.28
        fix_lon = float(lon) if pd.notna(lon) else -119.28
        if dt is not None:
            sky_col1, sky_col2 = st.columns(2)
            with sky_col1:
                st.plotly_chart(
                    sky_plot.sky_figure(
                        iridium_sats, dt, fix_lat, fix_lon,
                        min_el_deg=8.2, constellation="Iridium",
                        title="Iridium sky @ TX",
                    ),
                    use_container_width=True,
                )
            with sky_col2:
                st.plotly_chart(
                    sky_plot.sky_figure(
                        gps_sats, dt, fix_lat, fix_lon,
                        min_el_deg=5.0, constellation="GPS",
                        title="GPS sky @ fix",
                    ),
                    use_container_width=True,
                )
    except Exception as exc:  # noqa: BLE001
        st.caption(f"Sky plots unavailable: {exc}")


# ── Counterfactual -------------------------------------------------
st.subheader("Counterfactual: GNSS timeout sweep")
cf_col, res_col = st.columns([1.4, 2])
with cf_col:
    cutoff = st.slider(
        "Candidate GNSS timeout (s)", 15, 60, 30, 1, key="p14_cf",
        help="Replays every event assuming this timeout. Historical "
             "failures assumed to succeed at ~38 s if cutoff ≥ 35 s."
    )
with res_col:
    sweep = replay_panels.gnss_timeout_sweep(enriched, float(cutoff))
    st.markdown(
        f"- Effective fail rate: **{sweep['fail_rate']} %** "
        f"({sweep['would_fail']}/{sweep['n']})\n"
        f"- Mean effective TTFF: **{sweep['mean_ttff']} s**\n"
        f"- Mean energy / cycle (~0.13 J/s): **{sweep['mean_energy_j']} J**"
    )


# ── Correlation ----------------------------------------------------
st.subheader("Correlation")
sc1, sc2 = st.columns(2)
with sc1:
    if "IRI_N_VISIBLE" in enriched.columns and "RockBLOCK Time" in enriched.columns:
        st.plotly_chart(
            replay_panels.correlation_scatter(
                enriched, "IRI_N_VISIBLE", "RockBLOCK Time",
                title="rb1 vs Iridium visible sats",
            ),
            use_container_width=True,
        )
with sc2:
    if "GPS_N_VISIBLE" in enriched.columns and "GPS Time" in enriched.columns:
        st.plotly_chart(
            replay_panels.correlation_scatter(
                enriched, "GPS_N_VISIBLE", "GPS Time",
                title="TTFF vs GPS visible sats",
            ),
            use_container_width=True,
        )


# ── Downloads ------------------------------------------------------
st.subheader("Download")
stem_device = "-".join(selected_devices) if len(selected_devices) <= 2 else "multidev"
stem = ("fy25" if is_fy25 else stem_device).replace(" ", "")

csv_bytes = replay_export.build_events_csv(
    enriched, tz_name=p3_tz.get_display_tz()
)
fname_csv = replay_export.default_filename(stem, ext="csv")
st.download_button(
    "⬇ CSV — events + Phase 3 columns",
    data=csv_bytes,
    file_name=fname_csv,
    mime="text/csv",
    key="p14_dl_csv",
)

if st.toggle("Also build Excel with per-sat visibility sheets",
             value=False, key="p14_excel_toggle"):
    with st.spinner("Building multi-sheet workbook…"):
        xlsx_bytes = replay_export.build_events_excel(
            enriched, iridium_sats, gps_sats,
            tz_name=p3_tz.get_display_tz(),
        )
    fname_xlsx = replay_export.default_filename(stem, ext="xlsx")
    st.download_button(
        "⬇ Excel (events + sat_visibility_iri + sat_visibility_gps)",
        data=xlsx_bytes,
        file_name=fname_xlsx,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="p14_dl_xlsx",
    )

st.caption(
    f"Built at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')} · "
    f"display TZ = **{p3_tz.get_display_tz()}** · "
    f"{len(iridium_sats)} Iridium sats, {len(gps_sats)} GPS sats in TLE."
)

render_footer()
