"""
SPAO Buoy Dashboard — PNNL Brand Theme
Color tokens based on Pacific Northwest National Laboratory brand standards.
"""

import streamlit as st
import base64
import os


def _load_logo_base64():
    """Load the SPAO BUOY logo from assets and return as a data URI."""
    logo_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'SPAO_BUOY_logo.jpg')
    try:
        with open(logo_path, 'rb') as f:
            return f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode()}"
    except FileNotFoundError:
        return None


SPAO_LOGO_BASE64 = _load_logo_base64()

# === Primary Palette ===
PNNL_NAVY = "#00263A"           # Deep navy (primary brand)
PNNL_BLUE = "#003E6B"           # PNNL blue (headers, primary actions)
PNNL_ACCENT_BLUE = "#0078D4"    # Bright accent blue (links, highlights)
BATTELLE_ORANGE = "#F0AB00"     # Battelle orange (secondary accent, warnings)

# === Neutrals ===
WHITE = "#FFFFFF"
OFF_WHITE = "#F8F8F8"           # Background
LIGHT_GRAY = "#F4F6F8"         # Secondary background
BORDER_GRAY = "#DEDEDE"
TEXT_DARK = "#1A1A1A"
TEXT_MUTED = "#5A5A5A"

# === Semantic Colors ===
SUCCESS = "#2E7D32"             # Green (CRC valid, healthy)
WARNING = "#F57C00"             # Orange (low battery, attention)
DANGER = "#C62828"              # Red (errors, critical)
INFO = "#0078D4"                # Blue (informational)

# === Data Visualization (Consistent across all charts) ===
SENSOR_COLORS = {
    "Battery":       "#003E6B",  # PNNL blue
    "SST":           "#00838F",  # Teal (ocean)
    "Pressure":      "#5E35B1",  # Purple
    "Internal Temp": "#E65100",  # Orange
    "Humidity":      "#1565C0",  # Light blue
    "TENG Current":  "#2E7D32",  # Green (energy)
    "SuperCap":      "#6A1B9A",  # Deep purple
    "EC":            "#00695C",  # Dark teal
    "SSS":           "#0277BD",  # Salinity blue
}

# Device colors (assigned in order, cycle through)
DEVICE_PALETTE = [
    "#003E6B",  # PNNL blue
    "#F0AB00",  # Battelle orange
    "#00838F",  # Teal
    "#5E35B1",  # Purple
    "#2E7D32",  # Green
    "#C62828",  # Red
    "#6A1B9A",  # Deep purple
    "#E65100",  # Dark orange
]


def get_device_color(device_id: str, index: int = None) -> str:
    """Get a consistent color for a device. Uses hash for stability."""
    if index is not None:
        return DEVICE_PALETTE[index % len(DEVICE_PALETTE)]
    return DEVICE_PALETTE[hash(device_id) % len(DEVICE_PALETTE)]


# === Battery Status Colors ===
def battery_color(voltage: float) -> str:
    """Return color based on LiFePO4 battery voltage."""
    if voltage >= 3.3:
        return SUCCESS
    elif voltage >= 3.1:
        return WARNING
    else:
        return DANGER


def inject_custom_css():
    """Inject custom CSS for improved font sizes across sidebar and tabs."""
    st.markdown("""
    <style>
    /* Global app font smoothing and sizing */
    html, body, [data-testid="stAppViewContainer"] {
        font-size: 16px;
    }
    .stApp, [data-testid="stAppViewContainer"] p,
    [data-testid="stAppViewContainer"] li,
    [data-testid="stAppViewContainer"] label {
        font-size: 1rem !important;
        line-height: 1.55 !important;
    }
    [data-testid="stAppViewContainer"] h1 { font-size: 2rem !important; }
    [data-testid="stAppViewContainer"] h2 { font-size: 1.55rem !important; }
    [data-testid="stAppViewContainer"] h3 { font-size: 1.25rem !important; }
    [data-testid="stAppViewContainer"] h4 { font-size: 1.1rem !important; }

    /* Sidebar navigation items — bigger, bolder */
    section[data-testid="stSidebar"] [data-testid="stSidebarNavItems"] a span,
    section[data-testid="stSidebar"] nav a span {
        font-size: 1.15rem !important;
        font-weight: 500 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarNavItems"] a,
    section[data-testid="stSidebar"] nav a {
        padding: 0.4rem 1rem !important;
    }

    /* Sidebar widget labels (radios, checkboxes, selects) — restore size */
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] .stRadio label,
    section[data-testid="stSidebar"] .stCheckbox label,
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        font-size: 0.95rem !important;
    }
    section[data-testid="stSidebar"] .stRadio [role="radiogroup"] label {
        font-size: 0.95rem !important;
        font-weight: 500 !important;
    }

    /* ── Phase 1 / Phase 2 / Phase 3 section separators in the sidebar nav ──
       Selector strategy: we use ``[href$="…"]`` (ends-with) because the
       previous ``[href*="Phase3"]`` exclusion inside ``:not(:has())`` did
       not reliably cascade across all browsers' ``:has()`` implementations
       — Phase 3 pages were still inheriting the Phase 1 banner. End-match
       is unambiguous: Streamlit strips the leading index+emoji when
       routing, so the href ends in the bare page stem (``/Overview``,
       ``/Phase2_Overview``, ``/Phase3_Overview``). */

    /* PHASE 1 banner: anchored on the Phase 1 Overview (stem ends in
       "/Overview" with NO preceding "Phase" prefix). */
    section[data-testid="stSidebar"] [data-testid="stSidebarNavItems"] li:has(a[href$="/Overview"]) {
        position: relative;
        margin-top: 6px;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarNavItems"] li:has(a[href$="/Overview"])::before {
        content: "PHASE 1 — OPERATIONAL";
        display: block;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.5px;
        color: #5A5A5A;
        padding: 6px 1rem 4px 1rem;
    }

    /* PHASE 2 banner anchored on Phase2_Overview. Same styling (divider
       line + caption) as before. */
    section[data-testid="stSidebar"] [data-testid="stSidebarNavItems"] li:has(a[href$="/Phase2_Overview"]) {
        position: relative;
        margin-top: 14px;
        padding-top: 12px;
        border-top: 2px solid #003E6B;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarNavItems"] li:has(a[href$="/Phase2_Overview"])::before {
        content: "PHASE 2 — SCIENTIFIC";
        display: block;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.5px;
        color: #5A5A5A;
        padding: 2px 1rem 4px 1rem;
    }
    /* Divider line at the bottom of the Phase 2 group — anchored on the
       last Phase 2 page (Data_Enrichment). Mirrors the top border that
       opens the Phase 2 group so the whole section reads as a bracket. */
    section[data-testid="stSidebar"] [data-testid="stSidebarNavItems"] li:has(a[href$="/Data_Enrichment"]) {
        padding-bottom: 10px;
        border-bottom: 2px solid #003E6B;
        margin-bottom: 6px;
    }

    /* PHASE 3 banner anchored on Phase3_Overview. */
    section[data-testid="stSidebar"] [data-testid="stSidebarNavItems"] li:has(a[href$="/Phase3_Overview"]) {
        position: relative;
        margin-top: 14px;
        padding-top: 12px;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarNavItems"] li:has(a[href$="/Phase3_Overview"])::before {
        content: "PHASE 3 — SATELLITE SIMULATION";
        display: block;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.5px;
        color: #5A5A5A;
        padding: 2px 1rem 4px 1rem;
    }

    /* Reduce gap between branding and nav items */
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
        padding-bottom: 0 !important;
        margin-bottom: 0 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > div {
        margin-bottom: 0 !important;
        padding-bottom: 0 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarNavItems"] {
        padding-top: 0 !important;
        margin-top: 0 !important;
    }

    /* Ensure sidebar content doesn't get cut off — reserve space for footer. */
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
        padding-bottom: 60px !important;
    }

    /* Contain sidebar so position:fixed children (footer + dev toggle)
       anchor to the sidebar rather than the viewport. */
    section[data-testid="stSidebar"] {
        contain: layout !important;
    }
    .sidebar-footer {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        padding: 8px 12px;
        border-top: 1px solid #DEDEDE;
        background: #FFFFFF;
        box-sizing: border-box;
        z-index: 999;
    }

    /* ── Phase 3 dev toggle — host inside the Phase 3 section ──
       The ``<div id="p3-dev-toggle-anchor">`` marker is hidden; a small
       script in :func:`render_phase3_visibility_toggle` moves the toggle
       DOM node to sit right ABOVE the Phase 3 banner in the sidebar
       nav, so it visually belongs to the Phase 3 group. */
    section[data-testid="stSidebar"] [data-testid="element-container"]:has(#p3-dev-toggle-anchor) {
        display: none !important;
    }
    /* Visual framing for the toggle AFTER the JS has moved it into the nav. */
    #p3-dev-toggle-host {
        padding: 6px 10px 8px 10px;
        margin-top: 10px;
        background: #f8f8f8;
        border-top: 1px dashed #DEDEDE;
        border-bottom: 1px dashed #DEDEDE;
    }
    #p3-dev-toggle-host .p3-dev-toggle-label {
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.5px;
        color: #5A5A5A;
        display: block;
        margin-bottom: 4px;
    }
    .sidebar-footer p {
        color: #5A5A5A;
        font-size: 11px;
        text-align: center;
        margin: 0;
        word-wrap: break-word;
        overflow-wrap: break-word;
    }

    /* Tab buttons (Single Decode / Batch Decode etc.) */
    button[data-baseweb="tab"] {
        font-size: 1.2rem !important;
        font-weight: 600 !important;
        padding: 14px 28px !important;
    }

    /* Selectbox labels and values */
    div[data-baseweb="select"] > div {
        font-size: 1.05rem !important;
    }
    .stSelectbox label {
        font-size: 1.05rem !important;
    }

    /* Move sidebar branding above navigation */
    section[data-testid="stSidebar"] div:has(> [data-testid="stSidebarUserContent"]) {
        display: flex !important;
        flex-direction: column !important;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
        order: -1 !important;
    }
    </style>
    """, unsafe_allow_html=True)


def render_sidebar():
    """Render sidebar header with PNNL / SPAO BUOY branding at top, org info at bottom.

    Layout, top → bottom:
      1. PNNL / SPAO BUOY brand block (st.sidebar.markdown)
      2. Streamlit auto page-nav (rendered by Streamlit AFTER all
         st.sidebar.* calls)
      3. Phase 3 dev-toggle expander (CSS-pinned just above the footer)
      4. Footer (PNNL · DOE) — CSS position:fixed, bottom:0
    """
    logo_html = ""
    if SPAO_LOGO_BASE64:
        logo_html = (
            f'<img src="{SPAO_LOGO_BASE64}" alt="SPAO Logo" '
            f'style="height:70px; margin-bottom:0;">'
        )
    st.sidebar.markdown(
        '<div style="text-align:center; padding:4px 0 0 0; margin-bottom:0;">'
        '<p style="font-size:12px; color:#5A5A5A; margin:0; font-weight:600; '
        'letter-spacing:3px;">PNNL</p>'
        '<h2 style="color:#003E6B; margin:2px 0 0 0; font-size:20px; font-weight:700; '
        'letter-spacing:1px;">SPAO BUOY</h2>'
        f'{logo_html}'
        '</div>',
        unsafe_allow_html=True,
    )

    # Phase 3 pages are gated behind a developer toggle (default: hidden)
    # while the RF-analysis pages are still in validation. The expander is
    # CSS-pinned to the bottom of the sidebar (above the footer) via the
    # ``#p3-dev-toggle-anchor`` marker so it stays out of the way.
    render_phase3_visibility_toggle()

    st.sidebar.markdown(
        '<div class="sidebar-footer">'
        '<p>Pacific Northwest National Laboratory<br>'
        'DOE Water Power Technologies Office</p>'
        '</div>',
        unsafe_allow_html=True,
    )


# ── Phase 3 visibility gate (dev toggle) ─────────────────────────────
P3_VISIBILITY_KEY = "p3_pages_visible"

# Substrings of Phase 3 page slugs — used by both the CSS hider and the
# in-page ``phase3_pages_visible`` check so we only have one list to keep
# in sync when page names change.
P3_PAGE_SLUGS: tuple[str, ...] = (
    "Phase3_Overview",
    "Iridium_Tracker",
    "Field_Replay",
    "TX_Simulator",
)


def phase3_pages_visible() -> bool:
    """Return True when Phase 3 pages should be shown in the sidebar/rendered.

    Default is **False** — Phase 3 is still in validation. The toggle
    is persisted under ``st.session_state[P3_VISIBILITY_KEY]``.
    """
    return bool(st.session_state.get(P3_VISIBILITY_KEY, False))


def _inject_phase3_hide_css() -> None:
    """Hide the Phase 3 page links in the sidebar nav via CSS.

    Uses ``:has()`` + attribute-substring selectors on the anchor's
    ``href``. Streamlit strips the leading number + emoji when
    building the URL (e.g. ``/Phase3_Overview``) so we can match by
    slug substring without worrying about emoji encoding.
    """
    selectors_a = ", ".join(
        f'section[data-testid="stSidebar"] [data-testid="stSidebarNav"] '
        f'a[href*="{slug}"]'
        for slug in P3_PAGE_SLUGS
    )
    selectors_li = ", ".join(
        f'section[data-testid="stSidebar"] [data-testid="stSidebarNav"] '
        f'li:has(a[href*="{slug}"])'
        for slug in P3_PAGE_SLUGS
    )
    st.markdown(
        f"<style>{selectors_li} {{ display: none !important; }} "
        f"{selectors_a} {{ display: none !important; }}</style>",
        unsafe_allow_html=True,
    )


_P3_WIDGET_KEY = "_p3_pages_visible_widget"


def _on_p3_toggle_change() -> None:
    """Copy the widget's current value into the persistent session key."""
    st.session_state[P3_VISIBILITY_KEY] = bool(
        st.session_state.get(_P3_WIDGET_KEY, False)
    )


def render_phase3_visibility_toggle() -> None:
    """Render the Phase 3 visibility toggle.

    Persistence — the shadow-key pattern
    ------------------------------------
    Previous attempts that bound the widget directly to
    ``p3_pages_visible`` reset on every page navigation, because when
    the widget is unmounted (e.g. its expander has just been torn down
    by Streamlit's reconciler on the new page) Streamlit removes the
    bound key from ``st.session_state``. To survive teardown we use
    **two** keys:

    * ``_p3_pages_visible_widget`` is the ephemeral widget key;
      Streamlit is free to GC it whenever.
    * ``p3_pages_visible`` is our durable state; it lives for the
      whole session and never binds to a widget.

    The ``on_change`` callback syncs widget→durable; we also seed the
    widget from durable on every rerun so the checkbox reflects the
    persisted choice when the page re-mounts.

    Placement — host inside the Phase 3 nav section
    -----------------------------------------------
    The anchor div lets a tiny JS snippet (``_inject_phase3_toggle_host_js``)
    move the checkbox DOM node to sit right above the Phase 3 banner
    in the sidebar nav. This is a visual-only relocation — the
    widget's React binding and session-state wiring stay intact.
    """
    # 1. Seed durable state once.
    if P3_VISIBILITY_KEY not in st.session_state:
        st.session_state[P3_VISIBILITY_KEY] = False

    # 2. Make sure the widget mounts in sync with the durable state on
    #    every rerun — this is what repairs the value after Streamlit
    #    tears the widget down on a page change.
    st.session_state[_P3_WIDGET_KEY] = bool(st.session_state[P3_VISIBILITY_KEY])

    # 3. Anchor marker so our JS can find this specific checkbox.
    st.sidebar.markdown(
        '<div id="p3-dev-toggle-anchor"></div>',
        unsafe_allow_html=True,
    )
    # 4. The widget itself — no expander (expanders can be torn down
    #    when collapsed and their inner widgets lose state). A plain
    #    checkbox with a section-style caption is enough.
    st.sidebar.markdown(
        '<span class="p3-dev-toggle-label">DEVELOPER OPTIONS</span>',
        unsafe_allow_html=True,
    )
    st.sidebar.checkbox(
        "Show Phase 3 pages (experimental)",
        key=_P3_WIDGET_KEY,
        on_change=_on_p3_toggle_change,
        help="Phase 3 (pages 12–15, satellite-geometry / RF analysis) "
             "is still being validated. Toggle here to reveal them; "
             "your choice persists while you navigate between pages.",
    )

    # 5. JS that moves the anchor + checkbox + label DOM block to sit
    #    just above the Phase 3 banner in the sidebar nav. Safe to run
    #    even when the Phase 3 links are hidden (script no-ops in
    #    that case).
    _inject_phase3_toggle_host_js()

    if not phase3_pages_visible():
        _inject_phase3_hide_css()


def _inject_phase3_toggle_host_js() -> None:
    """Inject a MutationObserver that moves the dev-toggle into the Phase 3 area.

    Streamlit renders ``st.sidebar.*`` widgets into ``stSidebarUserContent``
    (above the nav). Streamlit does not let us inject DOM inside the
    auto-generated nav list, so we relocate via JS after render. The
    observer idempotently keeps the toggle in place on every rerun.
    """
    st.markdown(
        """
        <script>
        (function () {
          const MARKER_ID = 'p3-dev-toggle-anchor';
          const HOST_ID = 'p3-dev-toggle-host';

          function elementContainerFor(node) {
            return node ? node.closest('[data-testid="element-container"]') : null;
          }

          function locateTogglePieces(root) {
            const anchor = root.getElementById(MARKER_ID);
            if (!anchor) return null;
            const anchorCont = elementContainerFor(anchor);
            if (!anchorCont) return null;
            // The label <span> and the checkbox each get their own
            // element-container emitted immediately after the anchor.
            const labelCont = anchorCont.nextElementSibling;
            const widgetCont = labelCont ? labelCont.nextElementSibling : null;
            if (!labelCont || !widgetCont) return null;
            return {anchorCont, labelCont, widgetCont};
          }

          function locatePhase3Li(root) {
            // Match the Phase 3 Overview <li> robustly: href ends with
            // "/Phase3_Overview" OR contains "Phase3_Overview".
            const nav = root.querySelector('[data-testid="stSidebarNavItems"]');
            if (!nav) return null;
            const links = nav.querySelectorAll('a[href*="Phase3_Overview"]');
            for (const a of links) {
              const li = a.closest('li');
              if (li) return li;
            }
            return null;
          }

          function ensureHost(root, pieces) {
            let host = root.getElementById(HOST_ID);
            if (!host) {
              host = root.createElement('div');
              host.id = HOST_ID;
              // Order: label → widget
              host.appendChild(pieces.labelCont);
              host.appendChild(pieces.widgetCont);
            } else {
              // Idempotency — if Streamlit re-emitted either piece we
              // re-adopt them into the host.
              if (pieces.labelCont.parentElement !== host) {
                host.insertBefore(pieces.labelCont, host.firstChild);
              }
              if (pieces.widgetCont.parentElement !== host) {
                host.appendChild(pieces.widgetCont);
              }
            }
            return host;
          }

          function rearrange() {
            const root = document;
            const pieces = locateTogglePieces(root);
            const phase3Li = locatePhase3Li(root);
            if (!pieces || !phase3Li) return;
            const host = ensureHost(root, pieces);
            if (host.parentElement !== phase3Li.parentElement
                || host.nextSibling !== phase3Li) {
              phase3Li.parentElement.insertBefore(host, phase3Li);
            }
          }

          // Attempt now + on every DOM change (Streamlit reruns the
          // sidebar on every interaction).
          rearrange();
          if (window.__p3ToggleObserver) {
            window.__p3ToggleObserver.disconnect();
          }
          const obs = new MutationObserver(rearrange);
          window.__p3ToggleObserver = obs;
          obs.observe(document.body, {childList: true, subtree: true});
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )


def require_phase3_visible() -> None:
    """Call at the top of every Phase 3 page — bail out if the toggle is off.

    Shows a friendly banner so the user knows how to re-enable Phase 3
    instead of seeing a crash or a blank page.
    """
    if phase3_pages_visible():
        return
    st.info(
        "🚧 **Phase 3 is hidden.** These pages are still in validation. "
        "To enable, open the **Developer options** expander at the bottom "
        "of the sidebar and tick *Show Phase 3 pages (experimental)*."
    )
    st.stop()


# === UI Components ===

def render_header():
    """Render the global SPAO Buoy header with PNNL branding."""
    st.markdown(
        '<div style="padding-top:8px;">'
        '<h2 style="margin:0; color:#003E6B; font-weight:600;">'
        'SPAO Buoy Monitoring System</h2>'
        '<p style="margin:0; color:#5A5A5A; font-size:14px;">'
        'Self-Powered Arctic Ocean &middot; Pacific Northwest National Laboratory</p>'
        '</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<hr style="margin:8px 0 24px 0; border:none; '
        'border-top:2px solid #003E6B;">',
        unsafe_allow_html=True
    )


def render_footer():
    """Render the global footer for all pages."""
    st.markdown(
        '<div style="margin-top:48px; padding-top:24px; '
        'border-top:1px solid #DEDEDE; text-align:center; '
        'color:#5A5A5A; font-size:12px;">'
        '<div style="font-weight:600; color:#003E6B;">SPAO Buoy Monitoring System</div>'
        '<div>Pacific Northwest National Laboratory &middot; DOE Water Power Technologies Office</div>'
        '<div style="margin-top:8px;">'
        '<a href="https://github.com/Denny-Hwang/spao-buoy-dashboard" '
        'style="color:#0078D4; text-decoration:none;">Source Code</a> &middot; '
        '<a href="https://github.com/Denny-Hwang/spao-buoy-dashboard#readme" '
        'style="color:#0078D4; text-decoration:none;">Documentation</a> &middot; '
        '<a href="https://github.com/Denny-Hwang/spao-buoy-dashboard/issues" '
        'style="color:#0078D4; text-decoration:none;">Report Issue</a>'
        '</div>'
        '<div style="margin-top:8px; color:#999;">'
        'Version 1.2 &middot; GPL-3.0 License'
        '</div>'
        '</div>',
        unsafe_allow_html=True
    )


def render_kpi_card(label: str, value: str, delta: str = None):
    """Render a single KPI card with PNNL styling."""
    delta_html = ""
    if delta:
        delta_html = f'<div style="font-size:12px; color:#5A5A5A;">{delta}</div>'
    st.markdown(
        f'<div style="background:#FFFFFF; border:1px solid #DEDEDE; '
        f'border-left:4px solid #003E6B; border-radius:4px; padding:16px; '
        f'box-shadow:0 1px 3px rgba(0,0,0,0.05);">'
        f'<div style="font-size:12px; color:#5A5A5A; font-weight:500; '
        f'text-transform:uppercase; letter-spacing:0.5px;">{label}</div>'
        f'<div style="font-size:28px; color:#003E6B; font-weight:700; '
        f'margin-top:4px;">{value}</div>'
        f'{delta_html}'
        f'</div>',
        unsafe_allow_html=True
    )


def render_empty_state(title: str, description: str):
    """Render a friendly empty state message."""
    st.markdown(
        f'<div style="text-align:center; padding:60px 20px; '
        f'background:#F4F6F8; border-radius:8px; border:1px dashed #DEDEDE;">'
        f'<div style="font-size:48px; margin-bottom:16px;">&#128225;</div>'
        f'<h3 style="color:#003E6B; margin:0;">{title}</h3>'
        f'<p style="color:#5A5A5A; margin-top:8px;">{description}</p>'
        f'</div>',
        unsafe_allow_html=True
    )


def render_error(title: str, detail: str):
    """Render a user-friendly error message."""
    st.markdown(
        f'<div style="background:#FEF2F2; border-left:4px solid #C62828; '
        f'padding:16px; border-radius:4px; margin:16px 0;">'
        f'<div style="color:#C62828; font-weight:600; font-size:14px;">{title}</div>'
        f'<div style="color:#5A5A5A; font-size:13px; margin-top:4px;">{detail}</div>'
        f'</div>',
        unsafe_allow_html=True
    )


def battery_badge(voltage: float) -> str:
    """Return HTML badge for battery voltage with color coding."""
    color = battery_color(voltage)
    return (
        f'<span style="background:{color}; color:white; padding:2px 8px; '
        f'border-radius:12px; font-size:12px; font-weight:600;">'
        f'{voltage:.3f}V</span>'
    )


def crc_badge(valid: bool) -> str:
    """Return HTML badge for CRC status."""
    if valid:
        return '<span style="color:#2E7D32; font-weight:bold;">&#10003; Valid</span>'
    return '<span style="color:#C62828; font-weight:bold;">&#10007; Invalid</span>'
