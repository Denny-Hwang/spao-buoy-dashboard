"""
Page 7 — Phase 2 Overview / Reference.

Lands right below the Phase 1 block in the sidebar (pages 1–6 stay
unchanged) and above the Phase 2 analysis pages (8 TENG, 9 SST,
10 Drift, 11 Data Enrichment). Gives scientists and operators a single
place to understand:

  - What each Phase 2 analysis is trying to answer
  - Where the enriched columns come from (API, variable, cadence)
  - How the cron enrichment works
  - What every visualization on the downstream pages actually shows

This is a pure-documentation page — it does not load buoy data, does
not call external APIs, and renders identically whether or not Phase 2
cron jobs have populated anything yet.
"""

from __future__ import annotations

import importlib

import streamlit as st

st.set_page_config(page_title="Phase 2 Overview", page_icon="📖", layout="wide")

from utils.theme import (  # noqa: E402
    render_header, render_footer, render_sidebar, inject_custom_css,
    PNNL_BLUE,
)

inject_custom_css()
render_sidebar()
render_header()

st.markdown(
    f'<h1 style="color:{PNNL_BLUE}; margin-top:0;">📖 Phase 2 Overview</h1>',
    unsafe_allow_html=True,
)

try:
    _flag = importlib.import_module("utils.p2.__phase2_flag")
    _flag.render_toggle_in_sidebar()
except Exception as exc:  # noqa: BLE001
    st.sidebar.caption(f"Phase 2 toggle unavailable: {exc}")


# ──────────────────────────────────────────────────────────────────────
# 1. Goals
# ──────────────────────────────────────────────────────────────────────
st.markdown(
    f'<h2 style="color:{PNNL_BLUE};">1 · What does Phase 2 add?</h2>',
    unsafe_allow_html=True,
)
st.markdown(
    """
Phase 1 (pages 1–6) is the **operational** dashboard — live telemetry,
packet decoding, data table, quick analytics. It answers *"is the buoy
working?"* Phase 2 (pages 8–11) is the **scientific** layer. It joins
each buoy sample to **external oceanographic and atmospheric reference
data** so we can answer questions the raw telemetry cannot:

| Page | Question it answers |
|---|---|
| **🔋 TENG Performance** (8) | How much energy does the TENG extract from a given sea state? Is the generator degrading over time? |
| **🌊 SST Validation** (9)  | Does the buoy water-temperature sensor agree with satellite / reanalysis SST products? Is it drifting? |
| **🧭 Drift Dynamics** (10) | How is the buoy's motion explained by wind forcing, surface currents, and storm events? |
| **📡 Data Enrichment** (11)| Coverage, health and QC for everything above. Also the manual-backfill trigger. |

Phase 2 **never calls external APIs at Streamlit request time** — a
nightly (+ hourly) GitHub Action does the enrichment and writes results
back into the same Google Sheet, so page load stays instant.
"""
)

st.divider()

# ──────────────────────────────────────────────────────────────────────
# 2. Data sources
# ──────────────────────────────────────────────────────────────────────
st.markdown(
    f'<h2 style="color:{PNNL_BLUE};">2 · Where the enriched columns come from</h2>',
    unsafe_allow_html=True,
)
st.markdown(
    "Each column in the Google Sheet starting with `WAVE_`, `WIND_`, "
    "`ERA5_`, `SAT_SST_`, `OSCAR_`, `SEAICE_`, `ENRICH_FLAG` is written "
    "by one of the sources below. All source calls handle failures "
    "gracefully (return NaN, leave the `ENRICH_FLAG` bit unset) so a "
    "down API never blocks the rest of the pipeline."
)

st.markdown(
    """
| Source | API | Variables | Cadence | Resolution | Notes |
|---|---|---|---|---|---|
| **Open-Meteo Marine** | `https://marine-api.open-meteo.com/v1/marine` | wave_height, wave_period, wave_direction, wind/swell waves, **sea_surface_temperature** | Hourly cron (:15) | ~0.1° global ocean | Free, no auth. Powers `WAVE_*`, `SWELL_*`, `SAT_SST_ERA5_cC`. |
| **Open-Meteo Archive (ERA5)** | `https://archive-api.open-meteo.com/v1/archive` | temperature_2m, humidity, surface_pressure, wind 10 m | Hourly cron (:15) | ~0.25° global | Powers `WIND_*`, `ERA5_*`. |
| **Open-Meteo SST (unified)** | Marine + Archive combined | sea_surface_temperature with `soil_temperature_0cm` fallback | Hourly cron | ~0.1° / ~9 km | **Works over land** — this is what Richland-type coastal/inland deployments use. Powers `SAT_SST_OPENMETEO_cC`. |
| **NOAA OISST** | ERDDAP `ncdcOisst21Agg_LonPM180` | SST | Daily cron (07:30 UTC) | 0.25° global bulk | AVHRR + in-situ blended. Powers `SAT_SST_OISST_cC`. |
| **JPL MUR** | ERDDAP `jplMURSST41` | SST | Daily cron | 0.01° foundation SST | Highest res; ocean-only. Powers `SAT_SST_MUR_cC`. |
| **Copernicus OSTIA** | `copernicusmarine` SDK | SST | Daily cron | 0.05° foundation SST | Requires `COPERNICUS_USERNAME/PASSWORD`. Powers `SAT_SST_OSTIA_cC`. |
| **OSCAR surface currents** | ERDDAP (JPL PO.DAAC) | U, V surface currents | Daily cron | 0.33° 5-day composites | Powers `OSCAR_U_mms`, `OSCAR_V_mms`. |
| **OSI SAF sea ice** | THREDDS / NetCDF | sea_ice_concentration | Daily cron | 10 km polar | Powers `SEAICE_CONC_pct`; forced to 0 in the tropics. |
"""
)

with st.expander("🧭 How data reaches each column (end-to-end)"):
    st.markdown(
        """
1. **Buoy transmits** a RockBLOCK packet → Apps Script webhook →
   Google Sheets (unchanged Phase 1 flow).
2. **Hourly cron** (`enrichment_hourly.yml`, :15 every hour) calls
   Open-Meteo Marine + Archive + the unified Open-Meteo SST fetcher
   for rows whose corresponding `ENRICH_FLAG` bit is still unset.
   Values are written back as scaled integers (e.g. `WAVE_H_cm` = Hs
   in metres × 100).
3. **Daily cron** (`enrichment_daily.yml`, 07:30 UTC) runs the slower
   satellite / reanalysis fetches (OISST, MUR, OSTIA, OSCAR, sea ice).
4. **Streamlit** reads the Google Sheet via `utils.sheets_client.get_all_data()`
   — it never calls any external API itself, which keeps page loads
   fast and the Streamlit secrets minimal (`gcp_service_account` only).
5. **Derived_Daily worksheet** is (re)built by
   `scripts/compute_daily_derived.py` for long-term trend panels.

Unit-scale and `ENRICH_FLAG` bit definitions live in
`utils/p2/schema.py`; source dispatch lives in
`scripts/backfill_enrichment.py`.
"""
    )

st.divider()

# ──────────────────────────────────────────────────────────────────────
# 3. Page-by-page analysis guide
# ──────────────────────────────────────────────────────────────────────
st.markdown(
    f'<h2 style="color:{PNNL_BLUE};">3 · What each visualization means</h2>',
    unsafe_allow_html=True,
)

with st.expander("🔋 Page 8 — TENG Performance", expanded=True):
    st.markdown(
        """
**Goal.** Quantify how well the Triboelectric Nanogenerator (TENG)
converts wave energy into electrical power.

- **Hs × Tp heatmap** — mean TENG power binned by significant wave
  height and peak period; reference stars mark Jung 2024 and Lu 2026
  literature points. If your buoy's brightest bin is near a literature
  star, the capture efficiency is comparable.
- **Log-log P vs Hs²·Tp** — linear-wave-theory proxy for wave energy
  flux. A fit slope of ~1 says the TENG tracks the flux linearly.
- **vs theoretical flux (Falnes 2002)** — direct comparison against
  the analytic wave energy flux `ρ·g²·Hs²·Te/(64π)`. The fit slope is
  the effective capture width.
- **η (normalization) trend** — P normalized by Hs² or Hs²·Tp, over
  time. A Theil-Sen slope near zero + a "no trend" Mann-Kendall means
  the generator is not degrading independently of wave climate.
- **Matched-pair first-vs-last week violin** — paired comparison that
  would catch regime shifts a slope fit could miss.

**Note.** When the buoy is FY25 hardware (no dedicated TENG voltage
sensor), the pipeline derives P[mW] ≈ Battery[V] × TENG_Current[mA] as
a first-order proxy.
"""
    )

with st.expander("🌊 Page 9 — SST Validation"):
    st.markdown(
        """
**Goal.** Show whether the buoy water-temperature sensor agrees with
satellite / reanalysis SST, and flag slow sensor drift.

- **B1 Intercomparison** — Metrics table (N, bias, RMSE, unbiased
  RMSE, Δstd, correlation per product), plus mean-bias bar chart,
  Taylor diagram, Target diagram, buoy-vs-products time series, and
  residual histogram.
- **B2 Drift Detection** — Residual time series with Theil-Sen
  slope. |slope| > 0.01 °C/week triggers a drift alarm; weekly boxplot
  and CUSUM change-point chart back it up.
- **B3 Diurnal Warming** — Hour-of-day composite of buoy SST minus a
  daily-mean reference, and daily amplitude vs wind (Kawai & Wada
  2007 envelope overlay).

**Internal temperature toggle.** The hull thermistor (`Internal Temp`)
is NOT a water-SST measurement but is useful for diagnosing thermal
lag. Enable the checkbox on B1 and B3 to overlay it alongside the
water SST.

**Coastal / inland.** Satellite products are land-masked; the
**Open-Meteo SST** reference fills gaps over coast and continent
(soil-temperature fallback) so Richland-style deployments still have
a non-NaN curve to compare against. Read the *"What does each SST
product mean?"* expander on page 9 before interpreting biases.
"""
    )

with st.expander("🧭 Page 10 — Drift Dynamics"):
    st.markdown(
        """
**Goal.** Explain the buoy's motion from wind forcing, surface
currents, and storms.

- **C1 Trajectory** — Speed-coloured auto-zoom map with Start /
  Latest markers + time-series panels (stick plot, cumulative
  distance, daily displacement).
- **C2 Ekman decomposition** — Rolling windage α(t) with reference
  lines for drogued (Niiler-Paduan 0.007) and undrogued (Poulain
  0.03–0.05) drifters; deflection-angle histogram vs the classical
  45° Ekman prediction; wind-rose × drift-rose pair; residual drift
  vs OSCAR currents.
- **C3 Storm Response** — Auto-detected storm events, ±48 h
  superposed-epoch composite over Hs / U10 / pressure / SST, and
  pre/during/post storm box plots.
"""
    )

with st.expander("📡 Page 11 — Data Enrichment"):
    st.markdown(
        """
**Goal.** Operator / admin view for the enrichment pipeline.

- **Coverage** heatmap (source × day) — green cells = that source
  succeeded for at least one row that day.
- **Source health** — last-ok timestamp per source; `missing` means
  no column, `no data` means column exists but all-NaN.
- **Backfill** — manual `workflow_dispatch` button (requires
  `GH_DISPATCH_TOKEN`) that re-runs the daily enrichment for a chosen
  date range.
- **QC flags** — summary + per-flag offender rows based on
  QARTOD-like thresholds in `utils.p2.qc`.
"""
    )

st.divider()

# ──────────────────────────────────────────────────────────────────────
# 4. References & links
# ──────────────────────────────────────────────────────────────────────
st.markdown(
    f'<h2 style="color:{PNNL_BLUE};">4 · Further reading</h2>',
    unsafe_allow_html=True,
)
st.markdown(
    """
- **Falnes, J.** *Ocean Waves and Oscillating Systems* (2002), Eq. 6.19 — wave energy flux.
- **Jung, H. et al.** *Nano Energy* (2024) — triboelectric buoy benchmark point.
- **Lu, Y. et al.** (2026) — triboelectric buoy benchmark point.
- **Niiler, P. P. & Paduan, J. D.** (1995) — windage for drogued drifters.
- **Poulain, P.-M. et al.** (2009) — windage for undrogued drifters.
- **Kawai, Y. & Wada, A.** *J. Oceanogr.* (2007) — diurnal SST amplitude envelope.
- **NOAA OISST v2.1** — https://www.ncei.noaa.gov/products/optimum-interpolation-sst
- **JPL MUR** — https://podaac.jpl.nasa.gov/MEaSUREs-MUR
- **Copernicus OSTIA** — https://marine.copernicus.eu
- **Open-Meteo** — https://open-meteo.com

See also `CLAUDE.md` in the repo root for project-wide Phase 2 context.
"""
)

render_footer()
