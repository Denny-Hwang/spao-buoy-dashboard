"""
Page 12 — Phase 3 Overview.

A documentation-only page (mirrors the Phase 2 overview pattern). It
spells out exactly where every piece of Phase 3 data originates, how
often it is refreshed, and how we validate that the satellite-geometry
numbers on the Tracker / Field-Replay / Simulator pages are trustworthy.

No Google-Sheets data is loaded here — the page renders identically
whether or not the Phase 3 TLE cron has populated anything yet.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timezone

import streamlit as st

st.set_page_config(page_title="Phase 3 Overview", page_icon="🛰️", layout="wide")

from utils.theme import (  # noqa: E402
    render_header, render_footer, render_sidebar, inject_custom_css,
    require_phase3_visible, PNNL_BLUE,
)

inject_custom_css()
render_sidebar()
render_header()
require_phase3_visible()

# Phase 3 sidebar (enable toggle + TZ selector).
try:
    _flag = importlib.import_module("utils.p3.__phase3_flag")
    _flag.render_sidebar_controls()
except Exception as exc:  # noqa: BLE001
    st.sidebar.caption(f"Phase 3 controls unavailable: {exc}")


st.markdown(
    f'<h1 style="color:{PNNL_BLUE}; margin-top:0;">🛰️ Phase 3 Overview</h1>',
    unsafe_allow_html=True,
)
st.markdown(
    "Phase 3 adds the **RF / link-analysis layer** that explains *why* a "
    "given TX took 10 s or 100 s. It joins every Phase 1 packet to the "
    "Iridium and GPS constellation geometry at the moment of transmission "
    "and surfaces the answer on three analysis pages."
)

st.divider()

# ──────────────────────────────────────────────────────────────────────
# 1. Questions Phase 3 answers
# ──────────────────────────────────────────────────────────────────────
st.markdown(
    f'<h2 style="color:{PNNL_BLUE};">1 · What does Phase 3 add?</h2>',
    unsafe_allow_html=True,
)
st.markdown(
    """
| Page | Question it answers |
|---|---|
| **📡 Iridium Tracker** (13) | How does the Iridium constellation look *right now* over any observer? |
| **🔬 Field Replay** (14) | For each real TX in our data, how many Iridium/GPS satellites were visible, what was the link margin, and did geometry explain the rb1/rb2 result? |
| **⚡ TX Simulator** (15) | If we deploy at (lat, lon) at time t with this wave tilt, what is the expected Pass/Fail rate over the next few hours? |

Phase 1 (operational telemetry) and Phase 2 (oceanographic enrichment)
are **untouched**. Phase 3 reads Phase 1 data through the existing
``utils.sheets_client`` APIs and never writes back to device tabs.
"""
)

st.divider()

# ──────────────────────────────────────────────────────────────────────
# 2. Data sources & APIs
# ──────────────────────────────────────────────────────────────────────
st.markdown(
    f'<h2 style="color:{PNNL_BLUE};">2 · Data sources &amp; APIs</h2>',
    unsafe_allow_html=True,
)

st.markdown(
    """
All satellite ephemeris is downloaded from **CelesTrak** by a GitHub
Actions cron (`enrichment_iridium_tle.yml`, every 6 h) and written
into two new tabs on the Phase 1 spreadsheet:

| Tab | Data | CelesTrak URL | Cadence | Validation |
|---|---|---|---|---|
| `_iridium_tle` | ~75 Iridium sats (NEXT + legacy) | `celestrak.org/NORAD/elements/gp.php?GROUP=iridium-NEXT&FORMAT=tle` + `?GROUP=iridium` | 6 h | ≥ 60 sats expected; median epoch age < 7 d |
| `_gps_tle` | ~31 GPS operational sats | `celestrak.org/NORAD/elements/gp.php?GROUP=gps-ops&FORMAT=tle` | 6 h | ≥ 29 sats expected; median epoch age < 7 d |

The Streamlit app **never** calls CelesTrak at request time — it only
reads from those two sheet tabs via `utils.p3.tle_io.load_iridium_tle()`
/ `load_gps_tle()`. This preserves the "no runtime external API"
constraint that Phase 2 established.
"""
)

with st.expander("🔍 Live TLE tab health", expanded=False):
    try:
        tle_io = importlib.import_module("utils.p3.tle_io")
        iri = tle_io.tle_health(tle_io.TAB_IRIDIUM)
        gps = tle_io.tle_health(tle_io.TAB_GPS)

        def _line(h):
            age = f"{h.median_age_hours:.1f} h" if h.median_age_hours is not None else "—"
            fetched = (h.fetched_at.strftime("%Y-%m-%d %H:%M:%SZ")
                       if h.fetched_at else "never")
            ok = "✅" if h.ok else "⚠️"
            return f"{ok} `{h.tab}` — {h.n_sats} sats, median age {age}, last fetch {fetched}"

        st.markdown(f"- {_line(iri)}\n- {_line(gps)}")
        if not iri.ok or not gps.ok:
            st.warning(
                "TLE dataset looks stale or thin. Trigger the "
                "`enrichment_iridium_tle` GitHub Action manually if this "
                "persists."
            )
    except Exception as exc:  # noqa: BLE001
        st.info(f"TLE health check unavailable (sheet not yet populated?): {exc}")

st.divider()

# ──────────────────────────────────────────────────────────────────────
# 3. SGP4 propagation
# ──────────────────────────────────────────────────────────────────────
st.markdown(
    f'<h2 style="color:{PNNL_BLUE};">3 · SGP4 propagation &amp; geometry</h2>',
    unsafe_allow_html=True,
)
st.markdown(
    """
We use **brandon-rhodes/python-sgp4** (PyPI: `sgp4>=2.22`), a
pure-Python port of *Vallado et al., 2006, AIAA 2006-6753* — the
standard reference. No ephemeris download is needed.

Pipeline for every (TX time, observer lat/lon):

1. Parse each TLE into an `sgp4.api.Satrec` record.
2. Propagate to the TX epoch → TEME ECI position.
3. Rotate ECI → ECEF using GMST (IAU-82), then ECEF → local ENU.
4. Derive elevation / azimuth / slant-range from ENU.

Precision notes:
- SGP4 is a general-perturbation model; accuracy degrades ~1 km/day
  with TLE age, so we keep the TLE refresh at 6 h.
- Low-drag LEO (Iridium, 781 km) and MEO (GPS, 20 200 km) are both in
  the model's sweet spot.
- We ignore inter-satellite-link hand-offs, receiver-side multipath,
  and ionospheric scintillation; they matter for absolute link
  closure but not for the *ranking* comparisons Phase 3 uses.
"""
)

st.divider()

# ──────────────────────────────────────────────────────────────────────
# 4. Iridium link budget
# ──────────────────────────────────────────────────────────────────────
st.markdown(
    f'<h2 style="color:{PNNL_BLUE};">4 · Iridium link budget</h2>',
    unsafe_allow_html=True,
)
st.markdown(
    """
At L-band (Iridium downlink ≈ 1.6255 GHz, wavelength ≈ 18.45 cm):

```
FSPL(d)   = 20·log10(4π·d / λ)
L_atm(e)  = 0.3 / sin(e)            dB   (capped at 4 dB below 5°)
G_ant(θ)  = 3·cos^1.3(θ)            dBi  (patch antenna, nulls at ±90°)
Margin    = P_tx − L_cable + G_ant − FSPL − L_atm − (−G/T) + 228.6 − C/N₀_req
          = 32 − 2 + G_ant − FSPL − L_atm + (−16) + 228.6 − 42    [dB]
```

Combined single-attempt success probability:

```
P_success(margin, el) = sigmoid(margin − 5) × P_acq(el)
                       clamped to [0.05, 0.97]
```

`P_acq` is a piecewise function of elevation (steep drop below 15°)
and the full formulae live in `utils.p3.iridium_link` — the single
source of truth for Tracker, Field Replay, and Simulator.
"""
)

st.divider()

# ──────────────────────────────────────────────────────────────────────
# 5. Constellation constants
# ──────────────────────────────────────────────────────────────────────
st.markdown(
    f'<h2 style="color:{PNNL_BLUE};">5 · Constellation constants</h2>',
    unsafe_allow_html=True,
)
st.markdown(
    """
| Constellation | N (active) | Altitude | Incl. | Period | Min-elev mask |
|---|---|---|---|---|---|
| **Iridium NEXT** | ~66 | 781 km | 86.4° | 100.4 min | **8.2°** (SBDIX) |
| **GPS Block III/IIF** | ~31 | 20 200 km | 55° | ~12 h | 5° (u-blox ZOE-M8Q default) |

Minimum-elevation masks are applied *after* propagation so the sky
plots can still show below-mask sats faded.
"""
)

st.divider()

# ──────────────────────────────────────────────────────────────────────
# 6. Validation
# ──────────────────────────────────────────────────────────────────────
st.markdown(
    f'<h2 style="color:{PNNL_BLUE};">6 · Validation &amp; known results</h2>',
    unsafe_allow_html=True,
)
st.markdown(
    """
Validated against the FY25 Bering Sea deployment (443 TX events,
2025-09-10):

- **Iridium n_visible vs rb1** — *no* correlation detected. Above the
  8.2° mask, geometry is not the limiting factor for SBDIX duration.
  This is by design (Iridium is over-provisioned for low-latitude
  handoff), and Phase 3 exposes the evidence on the Field-Replay
  correlation scatter so this conclusion can be re-checked on every
  new deployment.
- **GPS n_visible vs TTFF** — a weak negative correlation appears;
  cold-start ephemeris download dominates, but very poor geometry
  (PDOP > 4) can push TTFF to the 30 s timeout.

Because the HTML prototype shipped the Bering-sea events inline,
we've committed the same data as `data/presets/fy25_deployment.json`
(*bundled with the repo, always available*). Select it from the
Field-Replay page's dataset picker to reproduce the validation.
"""
)

st.divider()

# ──────────────────────────────────────────────────────────────────────
# 7. Operational notes
# ──────────────────────────────────────────────────────────────────────
st.markdown(
    f'<h2 style="color:{PNNL_BLUE};">7 · Operational notes</h2>',
    unsafe_allow_html=True,
)

st.markdown(
    """
- **Time zone** — every Phase 3 page stores times internally as
  UTC. The sidebar selector chooses a secondary display zone
  (default **America/Los_Angeles** / PT). CSV downloads always include
  both `Timestamp` (UTC) and `Timestamp_local` / `Timestamp_tz` columns.
- **Caching** — TLE reads are cached for 1 h inside the Streamlit
  process. Clear via ``Refresh Data`` (where shown) or redeploy.
- **Visibility gate** — Phase 3 is still in validation, so the four
  pages (12–15) are **hidden from the sidebar by default**. Open the
  *Developer options* expander at the bottom of the sidebar and tick
  **Show Phase 3 pages (experimental)** to reveal them. The toggle
  persists across page navigation within the same session.
"""
)

st.caption(
    f"Page loaded at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}. "
    "Nothing on this page talks to external APIs."
)

render_footer()
