"""
SPAO Buoy Dashboard — PNNL Brand Theme
Color tokens based on Pacific Northwest National Laboratory brand standards.
"""

import streamlit as st

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
    /* Sidebar navigation items — bigger, bolder */
    section[data-testid="stSidebar"] [data-testid="stSidebarNavItems"] a span,
    section[data-testid="stSidebar"] nav a span {
        font-size: 1.15rem !important;
        font-weight: 500 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarNavItems"] a,
    section[data-testid="stSidebar"] nav a {
        padding: 0.5rem 1rem !important;
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
    """Render sidebar header with PNNL / SPAO BUOY branding at top, org info at bottom."""
    st.sidebar.markdown(
        '<div style="text-align:center; padding:8px 0;">'
        '<p style="font-size:13px; color:#5A5A5A; margin:0; font-weight:600; '
        'letter-spacing:3px;">PNNL</p>'
        '<h2 style="color:#003E6B; margin:4px 0 0 0; font-size:22px; font-weight:700; '
        'letter-spacing:1px;">SPAO BUOY</h2>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.sidebar.markdown(
        '<div style="position:fixed; bottom:0; left:0; width:var(--sidebar-width, 21rem); '
        'padding:12px 0; border-top:1px solid #DEDEDE; background:#FFFFFF;">'
        '<p style="color:#5A5A5A; font-size:12px; text-align:center; margin:0;">'
        'Pacific Northwest National Laboratory<br>'
        'DOE Water Power Technologies Office</p>'
        '</div>',
        unsafe_allow_html=True,
    )


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
