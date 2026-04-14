"""
PDF report generator for SPAO Buoy device data.

Uses fpdf2 for layout and kaleido (via Plotly) for chart image export.
Map trajectory uses staticmap (OSM tiles) with Plotly XY fallback.
"""

import io
import os
import tempfile
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from fpdf import FPDF

from utils.theme import (
    PNNL_BLUE, PNNL_NAVY, PNNL_ACCENT_BLUE, BATTELLE_ORANGE,
    SENSOR_COLORS, DEVICE_PALETTE, battery_color,
    SUCCESS, WARNING, DANGER,
)
from utils.plot_utils import apply_plot_style, LINE_WIDTH, MARKER_SIZE

# ── Constants ────────────────────────────────────────────────────────

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "SPAO_BUOY_logo.jpg")

# Sensor definitions: (display_name, unit, column_keywords)
REPORT_SENSORS = [
    ("Battery", "V", ["battery"]),
    ("SST", "\u00b0C", ["sst", "ocean temp"]),
    ("Pressure", "psi", ["pressure"]),
    ("Internal Temp", "\u00b0C", ["internal temp", "int temp"]),
    ("Humidity", "%RH", ["humidity"]),
    ("TENG Current Avg", "mA", ["teng current", "teng avg"]),
    ("EC Conductivity", "mS/cm", ["ec conductivity"]),
    ("Salinity", "PSS-78", ["salinity"]),
]

# Statistics table rows: (display_name, column_keywords)
STATS_ROWS = [
    ("TENG Current Avg (mA)", ["teng current", "teng avg"]),
    ("Battery (V)", ["battery"]),
    ("GPS Acq Time (s)", ["gps acq"]),
    ("Prev 1st RB Time (s)", ["prev 1st rb"]),
    ("Prev 2nd RB Time (s)", ["prev 2nd rb"]),
    ("Prev GPS Time (s)", ["prev gps"]),
    ("Prev Oper Time (s)", ["prev oper"]),
    ("SST (\u00b0C)", ["sst", "ocean temp"]),
    ("Pressure (psi)", ["pressure"]),
    ("Internal Temp (\u00b0C)", ["internal temp", "int temp"]),
    ("Humidity (%RH)", ["humidity"]),
    ("EC Conductivity (mS/cm)", ["ec conductivity"]),
    ("Salinity (PSS-78)", ["salinity"]),
]

_SKIP_COLS = {"Device", "Device Tab", "IMEI", "Timestamp", "Transmit Time",
              "MOMSN", "Packet Ver", "Bytes", "CRC Valid", "Raw Hex",
              "Notes", "Decode Error", "Warning"}


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert hex color string to (r, g, b) tuple."""
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _find_col(df: pd.DataFrame, keywords: list[str]) -> str | None:
    """Find a column matching any keyword (case-insensitive), excluding prev-session cols."""
    for c in df.columns:
        cl = c.lower()
        if cl.startswith("prev"):
            continue
        if any(kw in cl for kw in keywords):
            if c not in _SKIP_COLS:
                return c
    return None


def _find_col_any(df: pd.DataFrame, keywords: list[str]) -> str | None:
    """Find a column matching keywords, including prev-session cols."""
    for c in df.columns:
        cl = c.lower()
        if any(kw in cl for kw in keywords):
            if c not in _SKIP_COLS:
                return c
    return None


def _find_time_col(df: pd.DataFrame) -> str | None:
    """Find and parse the best time column."""
    candidates = [c for c in df.columns
                  if "time" in c.lower() or "timestamp" in c.lower() or "date" in c.lower()]
    if not candidates:
        return None
    time_col = candidates[0]
    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    return time_col


# ── Chart builders (for both screen and PDF) ─────────────────────────

def build_sensor_chart(df: pd.DataFrame, time_col: str, y_col: str,
                       title: str, unit: str, height: int = 400,
                       battery_nominal: float | None = None) -> go.Figure:
    """Build a single-device time-series chart for a sensor.

    When ``title`` is "Battery" and ``battery_nominal`` is provided, the
    y-axis is anchored to that nominal voltage (with auto-zoom out when the
    data dips below it) and a dashed reference line is drawn at the nominal,
    matching the Analytics page behavior. Other sensors keep the existing
    mean reference line.
    """
    fig = go.Figure()
    plot_df = df.copy()
    plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
    plot_df = plot_df.dropna(subset=[y_col, time_col])

    if plot_df.empty:
        return None

    fig.add_trace(go.Scatter(
        x=plot_df[time_col], y=plot_df[y_col],
        mode="lines+markers",
        line=dict(width=LINE_WIDTH, color=DEVICE_PALETTE[0]),
        marker=dict(size=MARKER_SIZE - 2),
        showlegend=False,
    ))

    is_battery = title == "Battery" and battery_nominal is not None

    if not is_battery:
        # Add mean reference line (kept for non-battery plots)
        mean_val = plot_df[y_col].mean()
        fig.add_hline(
            y=mean_val,
            line_dash="dash",
            line_color="#94a3b8",
            line_width=1.5,
            annotation_text=f"avg: {mean_val:.2f}",
            annotation_position="top left",
            annotation_font_size=11,
            annotation_font_color="#64748b",
        )

    y_label = f"{title} ({unit})" if unit else title
    apply_plot_style(fig, title=title, x_title="", y_title=y_label, height=height)

    if is_battery:
        y_max = float(plot_df[y_col].max())
        y_min_data = float(plot_df[y_col].min())
        bottom_margin = 0.02
        y_lower = min(battery_nominal, y_min_data) - bottom_margin
        y_upper = max(y_max + 0.02, battery_nominal + 0.2)
        fig.update_yaxes(range=[y_lower, y_upper])
        fig.add_hline(
            y=battery_nominal,
            line_dash="dash",
            line_color="#C62828",
            line_width=1.5,
            annotation_text=f"Nominal {battery_nominal:.2f} V",
            annotation_position="bottom right",
            annotation_font_size=11,
            annotation_font_color="#C62828",
        )

    return fig


def build_trajectory_image(df: pd.DataFrame, lat_col: str, lon_col: str,
                           title: str = "Drift Trajectory",
                           width: int = 1000, height: int = 600) -> bytes | None:
    """Build a trajectory map image with real map tiles (OSM via staticmap).

    Returns PNG bytes on success, or None if tile download fails.
    Falls back gracefully so callers can use ``build_trajectory_chart_fallback``.
    """
    plot_df = df.copy()
    plot_df[lat_col] = pd.to_numeric(plot_df[lat_col], errors="coerce")
    plot_df[lon_col] = pd.to_numeric(plot_df[lon_col], errors="coerce")

    zero_mask = (plot_df[lat_col] == 0) & (plot_df[lon_col] == 0)
    plot_df.loc[zero_mask, [lat_col, lon_col]] = np.nan
    plot_df = plot_df.dropna(subset=[lat_col, lon_col])

    if plot_df.empty:
        return None

    try:
        from staticmap import StaticMap, Line, CircleMarker

        m = StaticMap(width, height,
                      url_template="https://server.arcgisonline.com/ArcGIS/rest/services/"
                                   "World_Imagery/MapServer/tile/{z}/{y}/{x}",
                      tile_size=256)

        # Trajectory line  (staticmap uses (lon, lat) order)
        coords = list(zip(plot_df[lon_col], plot_df[lat_col]))
        if len(coords) > 1:
            m.add_line(Line(coords, color=DEVICE_PALETTE[0], width=3))

        # Point markers along the track
        for lon, lat in coords:
            m.add_marker(CircleMarker((lon, lat), color=DEVICE_PALETTE[0], width=4))

        # Start marker (green)
        m.add_marker(CircleMarker(coords[0], color=SUCCESS, width=14))
        # Latest marker (red)
        m.add_marker(CircleMarker(coords[-1], color=DANGER, width=14))

        pil_img = m.render()

        # Add title text overlay using PIL
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(pil_img)

        # Title banner at top
        banner_h = 36
        draw.rectangle([(0, 0), (width, banner_h)], fill=(0, 38, 58, 200))  # PNNL_NAVY semi-transparent
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
            font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
        except (OSError, IOError):
            font = ImageFont.load_default()
            font_sm = font
        draw.text((10, 8), title, fill="white", font=font)

        # Legend at bottom-right
        lx = width - 160
        ly = height - 50
        draw.rectangle([(lx - 5, ly - 5), (width - 5, height - 5)], fill=(255, 255, 255, 200))
        r_s, g_s, b_s = _hex_to_rgb(SUCCESS)
        r_d, g_d, b_d = _hex_to_rgb(DANGER)
        draw.ellipse([(lx, ly + 2), (lx + 12, ly + 14)], fill=(r_s, g_s, b_s))
        draw.text((lx + 18, ly), "Start", fill="black", font=font_sm)
        draw.ellipse([(lx, ly + 22), (lx + 12, ly + 34)], fill=(r_d, g_d, b_d))
        draw.text((lx + 18, ly + 20), "Latest", fill="black", font=font_sm)

        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        return buf.getvalue()

    except Exception:
        return None


def build_trajectory_chart_fallback(df: pd.DataFrame, lat_col: str, lon_col: str,
                                    title: str = "Drift Trajectory") -> go.Figure | None:
    """Fallback: Plotly XY scatter plot (no map tiles) when staticmap is unavailable."""
    plot_df = df.copy()
    plot_df[lat_col] = pd.to_numeric(plot_df[lat_col], errors="coerce")
    plot_df[lon_col] = pd.to_numeric(plot_df[lon_col], errors="coerce")

    zero_mask = (plot_df[lat_col] == 0) & (plot_df[lon_col] == 0)
    plot_df.loc[zero_mask, [lat_col, lon_col]] = np.nan
    plot_df = plot_df.dropna(subset=[lat_col, lon_col])

    if plot_df.empty:
        return None

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=plot_df[lon_col], y=plot_df[lat_col],
        mode="lines+markers",
        line=dict(width=3, color=DEVICE_PALETTE[0]),
        marker=dict(size=5, color=DEVICE_PALETTE[0], opacity=0.6),
        showlegend=False, name="Track",
    ))
    fig.add_trace(go.Scatter(
        x=[plot_df[lon_col].iloc[0]], y=[plot_df[lat_col].iloc[0]],
        mode="markers+text",
        marker=dict(size=16, color=SUCCESS, symbol="star",
                    line=dict(width=1, color="white")),
        text=["Start"], textposition="top center",
        textfont=dict(size=12, color=SUCCESS),
        name="Start", showlegend=True,
    ))
    fig.add_trace(go.Scatter(
        x=[plot_df[lon_col].iloc[-1]], y=[plot_df[lat_col].iloc[-1]],
        mode="markers+text",
        marker=dict(size=16, color=DANGER, symbol="star",
                    line=dict(width=1, color="white")),
        text=["Latest"], textposition="top center",
        textfont=dict(size=12, color=DANGER),
        name="Latest", showlegend=True,
    ))

    apply_plot_style(fig, title=title,
                     x_title="Longitude (\u00b0)", y_title="Latitude (\u00b0)",
                     height=500)
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    return fig


def build_scatter_chart(df: pd.DataFrame, x_col: str, y_col: str,
                        title: str, x_unit: str, y_unit: str) -> go.Figure:
    """Build a scatter plot with trendline."""
    plot_df = df.copy()
    plot_df[x_col] = pd.to_numeric(plot_df[x_col], errors="coerce")
    plot_df[y_col] = pd.to_numeric(plot_df[y_col], errors="coerce")
    plot_df = plot_df.dropna(subset=[x_col, y_col])

    if len(plot_df) < 2:
        return None

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=plot_df[x_col], y=plot_df[y_col],
        mode="markers",
        marker=dict(size=MARKER_SIZE, color=DEVICE_PALETTE[0]),
        showlegend=False,
    ))

    # Trendline
    coeffs = np.polyfit(plot_df[x_col], plot_df[y_col], 1)
    x_range = np.linspace(plot_df[x_col].min(), plot_df[x_col].max(), 100)
    fig.add_trace(go.Scatter(
        x=x_range, y=np.polyval(coeffs, x_range),
        mode="lines",
        name=f"y={coeffs[0]:.4f}x+{coeffs[1]:.4f}",
        line=dict(width=2, dash="dash", color="#94a3b8"),
    ))

    x_label = f"{x_col} ({x_unit})" if x_unit else x_col
    y_label = f"{y_col} ({y_unit})" if y_unit else y_col
    apply_plot_style(fig, title=title, x_title=x_label, y_title=y_label, height=400)
    return fig


# ── Statistics computation ───────────────────────────────────────────

def compute_statistics(df: pd.DataFrame) -> pd.DataFrame:
    """Compute summary statistics for all relevant sensor columns."""
    rows = []
    for label, keywords in STATS_ROWS:
        col = _find_col_any(df, keywords)
        if col is None:
            continue
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if series.empty:
            continue
        rows.append({
            "Metric": label,
            "Min": f"{series.min():.3f}",
            "Mean": f"{series.mean():.3f}",
            "Max": f"{series.max():.3f}",
            "Std": f"{series.std():.3f}",
            "Latest": f"{series.iloc[-1]:.3f}",
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ── KPI computation ──────────────────────────────────────────────────

def compute_kpis(df: pd.DataFrame, time_col: str | None) -> dict:
    """Compute key performance indicators for the report header."""
    kpis = {}

    # Total packets
    kpis["total_packets"] = len(df)

    # CRC quality
    if "CRC Valid" in df.columns:
        crc_series = df["CRC Valid"].astype(str).str.lower()
        valid_count = crc_series.isin(["true", "1"]).sum()
        kpis["crc_rate"] = valid_count / len(df) * 100 if len(df) > 0 else 0
        kpis["crc_invalid"] = len(df) - valid_count
    else:
        kpis["crc_rate"] = None
        kpis["crc_invalid"] = None

    # Battery
    batt_col = _find_col(df, ["battery"])
    if batt_col:
        batt = pd.to_numeric(df[batt_col], errors="coerce").dropna()
        if not batt.empty:
            kpis["battery_latest"] = batt.iloc[-1]
            kpis["battery_change"] = batt.iloc[-1] - batt.iloc[0]

    # SST
    sst_col = _find_col(df, ["sst", "ocean temp"])
    if sst_col:
        sst = pd.to_numeric(df[sst_col], errors="coerce").dropna()
        if not sst.empty:
            kpis["sst_avg"] = sst.mean()
            kpis["sst_min"] = sst.min()
            kpis["sst_max"] = sst.max()

    # Coverage period
    if time_col and time_col in df.columns:
        valid_times = df[time_col].dropna()
        if not valid_times.empty:
            span = valid_times.max() - valid_times.min()
            kpis["coverage_days"] = max(span.days, 1)
            kpis["packets_per_day"] = len(df) / max(span.days, 1)

    return kpis


# ── Plotly figure → PNG bytes ────────────────────────────────────────

def fig_to_png(fig: go.Figure, width: int = 900, height: int = 400) -> bytes:
    """Export a Plotly figure to PNG bytes using kaleido."""
    return pio.to_image(fig, format="png", width=width, height=height, scale=2)


# ── PDF builder ──────────────────────────────────────────────────────

class SpaoReportPDF(FPDF):
    """Custom FPDF subclass with SPAO Buoy branding."""

    def __init__(self, device_name: str, period_start: str, period_end: str):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.device_name = device_name
        self.period_start = period_start
        self.period_end = period_end
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        # Logo
        if os.path.isfile(_LOGO_PATH):
            self.image(_LOGO_PATH, x=10, y=8, h=12)

        # Title
        self.set_font("Helvetica", "B", 14)
        r, g, b = _hex_to_rgb(PNNL_NAVY)
        self.set_text_color(r, g, b)
        self.cell(0, 6, "SPAO Buoy Report", new_x="LMARGIN", new_y="NEXT", align="C")

        self.set_font("Helvetica", "", 9)
        self.set_text_color(100, 100, 100)
        self.cell(0, 5, f"Device: {self.device_name}", new_x="LMARGIN", new_y="NEXT", align="C")
        self.cell(0, 4, f"Period: {self.period_start} ~ {self.period_end}", new_x="LMARGIN", new_y="NEXT", align="C")

        # Divider
        r, g, b = _hex_to_rgb(PNNL_BLUE)
        self.set_draw_color(r, g, b)
        self.set_line_width(0.5)
        self.line(10, self.get_y() + 2, 200, self.get_y() + 2)
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        generated = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.cell(0, 10, f"Generated: {generated}  |  SPAO Buoy Monitoring System  |  PNNL", align="C")

    def section_title(self, title: str):
        """Render a blue section title with underline."""
        self.ln(3)
        r, g, b = _hex_to_rgb(PNNL_BLUE)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(r, g, b)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(r, g, b)
        self.set_line_width(0.3)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)

    def add_kpi_row(self, kpis: dict):
        """Add a row of key metrics."""
        items = []
        items.append(("Total Packets", str(kpis.get("total_packets", "N/A"))))
        if kpis.get("battery_latest") is not None:
            delta = kpis.get("battery_change", 0)
            sign = "+" if delta >= 0 else ""
            items.append(("Battery", f"{kpis['battery_latest']:.3f}V ({sign}{delta:.3f})"))
        if kpis.get("sst_avg") is not None:
            items.append(("Avg SST", f"{kpis['sst_avg']:.2f}\u00b0C"))
        if kpis.get("crc_rate") is not None:
            items.append(("CRC Quality", f"{kpis['crc_rate']:.1f}%"))
        if kpis.get("coverage_days") is not None:
            items.append(("Coverage", f"{kpis['coverage_days']}d ({kpis['packets_per_day']:.1f}/d)"))

        col_w = 190 / len(items) if items else 190
        self.set_font("Helvetica", "", 8)
        self.set_text_color(100, 100, 100)

        # Labels row
        x_start = 10
        y = self.get_y()
        for label, _ in items:
            self.set_xy(x_start, y)
            self.cell(col_w, 4, label, align="C")
            x_start += col_w

        self.ln(4)

        # Values row
        x_start = 10
        y = self.get_y()
        r, g, b = _hex_to_rgb(PNNL_BLUE)
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(r, g, b)
        for _, value in items:
            self.set_xy(x_start, y)
            self.cell(col_w, 7, value, align="C")
            x_start += col_w

        self.ln(10)

    def add_stats_table(self, stats_df: pd.DataFrame):
        """Add a statistics table to the PDF."""
        if stats_df.empty:
            return

        self.set_font("Helvetica", "B", 8)
        r, g, b = _hex_to_rgb(PNNL_BLUE)

        # Column widths
        col_widths = [58, 24, 24, 24, 24, 24]
        headers = ["Metric", "Min", "Mean", "Max", "Std", "Latest"]

        # Header row
        self.set_fill_color(r, g, b)
        self.set_text_color(255, 255, 255)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 6, h, border=1, fill=True,
                      align="C" if i > 0 else "L")
        self.ln()

        # Data rows
        self.set_font("Helvetica", "", 8)
        self.set_text_color(30, 30, 30)
        for idx, row in stats_df.iterrows():
            if idx % 2 == 0:
                self.set_fill_color(244, 246, 248)
            else:
                self.set_fill_color(255, 255, 255)
            for i, h in enumerate(headers):
                val = str(row.get(h, ""))
                self.cell(col_widths[i], 5, val, border=1, fill=True,
                          align="R" if i > 0 else "L")
            self.ln()

        self.ln(4)

    def add_chart_image(self, img_bytes: bytes, title: str = "", width: int = 180):
        """Add a chart image (PNG bytes) to the PDF."""
        # Check if we need a new page (leave space for image + margin)
        if self.get_y() > 200:
            self.add_page()

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(img_bytes)
            tmp_path = tmp.name

        try:
            self.image(tmp_path, x=15, w=width)
            self.ln(4)
        finally:
            os.unlink(tmp_path)

    def add_chart_pair(self, img1: bytes, img2: bytes, w: int = 90):
        """Add two charts side by side."""
        if self.get_y() > 200:
            self.add_page()

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as t1, \
             tempfile.NamedTemporaryFile(suffix=".png", delete=False) as t2:
            t1.write(img1)
            t2.write(img2)
            p1, p2 = t1.name, t2.name

        try:
            y = self.get_y()
            self.image(p1, x=10, y=y, w=w)
            self.image(p2, x=10 + w + 5, y=y, w=w)
            # Estimate image height (aspect ratio ~2:1 for charts)
            est_h = w * 0.5
            self.set_y(y + est_h + 4)
        finally:
            os.unlink(p1)
            os.unlink(p2)


def generate_report_pdf(
    df: pd.DataFrame,
    device_name: str,
    period_start: str,
    period_end: str,
    chart_figures: list[tuple[str, go.Figure]],
    trajectory_png: bytes | None = None,
    trajectory_fig: go.Figure | None = None,
    scatter_fig: go.Figure | None = None,
) -> bytes:
    """Generate a complete PDF report and return as bytes.

    Parameters
    ----------
    df : Filtered device data
    device_name : Display name for the device
    period_start / period_end : Date range strings
    chart_figures : List of (title, plotly_figure) tuples for sensor charts
    trajectory_png : Pre-rendered map image bytes (from staticmap)
    trajectory_fig : Fallback Plotly XY figure if trajectory_png is None
    scatter_fig : Plotly scatter figure for correlation plot
    """
    time_col = _find_time_col(df.copy())
    kpis = compute_kpis(df, time_col)
    stats = compute_statistics(df)

    pdf = SpaoReportPDF(device_name, period_start, period_end)
    pdf.add_page()

    # ── Summary KPIs ──
    pdf.section_title("Summary")
    pdf.add_kpi_row(kpis)

    # ── Statistics Table ──
    if not stats.empty:
        pdf.section_title("Statistics")
        pdf.add_stats_table(stats)

    # ── Trajectory Map ──
    if trajectory_png is not None:
        pdf.section_title("Drift Trajectory")
        pdf.add_chart_image(trajectory_png, width=185)
    elif trajectory_fig is not None:
        pdf.section_title("Drift Trajectory")
        img = fig_to_png(trajectory_fig, width=1000, height=500)
        pdf.add_chart_image(img, width=185)

    # ── Sensor Plots (2 per row) ──
    if chart_figures:
        pdf.add_page()
        pdf.section_title("Sensor Time Series")

        pairs = []
        for i in range(0, len(chart_figures), 2):
            if i + 1 < len(chart_figures):
                pairs.append((chart_figures[i], chart_figures[i + 1]))
            else:
                pairs.append((chart_figures[i], None))

        for pair in pairs:
            (t1, f1) = pair[0]
            img1 = fig_to_png(f1, width=800, height=400)
            if pair[1] is not None:
                (t2, f2) = pair[1]
                img2 = fig_to_png(f2, width=800, height=400)
                pdf.add_chart_pair(img1, img2)
            else:
                pdf.add_chart_image(img1, width=90)

    # ── Correlation Scatter ──
    if scatter_fig is not None:
        if pdf.get_y() > 180:
            pdf.add_page()
        pdf.section_title("Pressure vs SST")
        img = fig_to_png(scatter_fig, width=900, height=400)
        pdf.add_chart_image(img, width=140)

    return bytes(pdf.output())
