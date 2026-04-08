"""
SPAO Buoy Dashboard — PNNL Brand Theme
Color tokens based on Pacific Northwest National Laboratory brand standards.
"""

import streamlit as st
import base64

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


# SPAO Project Logo (JPEG, base64-encoded)
SPAO_LOGO_BASE64 = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAGwAbgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD3+iiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKx7/wAV+HdLyL/XdNtmHVZbpFb8ic0AbFFcJd/GTwDZ5D+IIpGHaGGSTP4quP1rHn/aB8EQk7G1Gf8A6522P/QiKAPU6K8dk/aO8JMcSaZrSfSKI/8AtSr9v+0B4HmI8yTUIP8ArpbZ/wDQSaAPZ6K4e0+MPhG9wI/EUCEdia2Rv03A13Fhrulangas9VsLhB1aG4Rx+YNAG1RRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAVFPNFDAQW8yQQRDc8srhVUepJ4FePeJvj/oWnyG08PW02s3ZO1XAMcWfYkbm/AcetS6b4B+MXxH/AHuranJoGly/wZNtkf7qjMjf8COK6aOGqVXaCuYVK0Kb952Oa8TfH/QtPkNp4etZtZuydquAY4s+xI3N+A59a5ey+E3xU+I9w+o+K9QfSbRjlbdMZx7RjCJ9Tlvwr2/wAJ/CXwl4PVHtNOW5vV/wCXy7xJJ+B+6P8AgIA967qplXhD4FcqNCc/iehy/gv4V+FvBCRy2Fj9ovlHN7cYeU/QdF/4CAa7iiiuBycnds7UklZBRRRSGFFFFABRRRQBxXxZZl+GN+wJGLqA8H/bFedfEj4j6h4J+H2iWOiOI9V1ezgLXGAfITyly2D3Yjj0BJ9K9c8eWV1qHgfVbOytpbi4lhwkcSFmJ3DoB14rzjw/8FNag8P2txrXiSaa8ubVY5bS2BMNu20ZXPRznrzj618lnOKp0XCE2lzXt306n0eV4edVTnBN8tr/APBI/CHwJtL3w9Z33i3V726uruBJjZ27mKKHcAdu4YZ+OuSBn0rbj+AXgSKQOdOupQO0t3Ic/luA/SvTFUIoVQAoGAB2paivjKtR3lJmtPC04K0YoqaZpdjpFhFY6daw2trENscUKBVUfQVboornNwooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAK5nxN8QPDHhJWGratCk4HFtGfMlP/AAFcn6nArrq+fPid8H9Y1vxFP4k0W/SS4mVFa1u5CqEKoXCOAcHAHDAj2oA6C7+Md5rcrWvg7w3dahO52o8ybFJ9cD5m/ACqP8AZ3xv8W/8fOrL/Z9u/wDCgFtgf7qjczfjmul+FGi+I/DPgGHTtf1dru7WRzHBFuMNqhP3EJMZJJJ65AwBya7ygDyCD4CaTqMy3XizWdV168U7lM8xWJD7IOv4mvQ9G8LaD4dh8rSNIsrFcYJhgVWb6tjLH6mteigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooA//Z"  # noqa: E501

LOGO_HTML_TEMPLATE = '<img src="{src}" alt="SPAO Logo" style="height:{height}px; vertical-align:middle;">'


def render_logo(height: int = 48) -> str:
    """Return HTML img tag for the SPAO logo at the given height in pixels."""
    return LOGO_HTML_TEMPLATE.format(src=SPAO_LOGO_BASE64, height=height)


def get_logo_bytes() -> bytes:
    """Decode the base64 logo and return raw JPEG bytes."""
    raw_b64 = SPAO_LOGO_BASE64.split(",", 1)[1]
    return base64.b64decode(raw_b64)


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
    </style>
    """, unsafe_allow_html=True)


def render_sidebar():
    """Render sidebar header with logo and PNNL / SPAO BUOY branding."""
    st.sidebar.markdown(
        f'<div style="text-align:center; padding:8px 0;">'
        f'<img src="{SPAO_LOGO_BASE64}" alt="SPAO Logo" '
        f'style="height:80px; margin-bottom:4px;">'
        f'<p style="font-size:13px; color:#5A5A5A; margin:0; font-weight:600; '
        f'letter-spacing:3px;">PNNL</p>'
        f'<h2 style="color:#003E6B; margin:4px 0 0 0; font-size:22px; font-weight:700; '
        f'letter-spacing:1px;">SPAO BUOY</h2>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.sidebar.divider()
    st.sidebar.markdown(
        '<p style="color:#5A5A5A; font-size:12px; text-align:center; margin:0;">'
        'Pacific Northwest National Laboratory<br>'
        'DOE Water Power Technologies Office</p>',
        unsafe_allow_html=True,
    )


# === UI Components ===

def render_header():
    """Render the global SPAO Buoy header with PNNL branding."""
    col1, col2 = st.columns([1, 5])

    with col1:
        st.markdown(
            f'<img src="{SPAO_LOGO_BASE64}" alt="SPAO Logo" '
            f'style="height:72px; vertical-align:middle;">',
            unsafe_allow_html=True,
        )

    with col2:
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
