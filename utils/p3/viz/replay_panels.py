"""Field-Replay detail panels: event KV, timeline, and verdict builder.

Centralising the HTML-demo-inspired panels here keeps page 14 tidy.
Each function is pure rendering — it takes already-resolved data and
returns a Plotly figure or a block of markdown.
"""

from __future__ import annotations

from typing import Iterable

import pandas as pd
import plotly.graph_objects as go

from utils.p3 import tz as _tz


# ── Event-detail key/value block (markdown) ───────────────────────
def event_kv_markdown(row: pd.Series, *, tz_name: str | None = None) -> str:
    """Render a 2-column markdown block of the key Phase-3 event metrics."""
    def _val(k, default="—"):
        v = row.get(k)
        if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
            return default
        return v

    ts = row.get("Timestamp")
    ts_md = _tz.format_dual(ts, tz_name=tz_name)

    lat = _val("Latitude") if "Latitude" in row else _val("Lat")
    lon = _val("Longitude") if "Longitude" in row else _val("Lon")
    fix_md = f"{lat}, {lon}" if lat != "—" and lon != "—" else "—"

    rb1 = _val("RockBLOCK Time", _val("Prev 1st RB Time"))
    rb2 = _val("Prev 2nd RB Time", 0.0)
    gps_t = _val("GPS Time")
    bat = _val("Battery")

    iri_n = _val("IRI_N_VISIBLE")
    iri_el = _val("IRI_BEST_EL_deg")
    iri_sat = _val("IRI_BEST_SAT")
    iri_margin = _val("IRI_LINK_MARGIN_dB")
    iri_p = _val("IRI_P_SUCCESS")

    gps_nv = _val("GPS_N_VISIBLE")
    gps_nh = _val("GPS_N_HIGH_EL")
    gps_max = _val("GPS_MAX_EL_deg")
    gps_pd = _val("GPS_PDOP")

    tle_age = _val("TLE_EPOCH_AGE_HRS")

    rows = [
        ("Timestamp", ts_md),
        ("Fix", fix_md),
        ("rb1 / rb2 / TTFF", f"{rb1}s / {rb2}s / {gps_t}s"),
        ("Battery", f"{bat} V"),
        ("Iridium visible", f"{iri_n} (best {iri_el}° on {iri_sat})"),
        ("Iridium margin / P(success)", f"{iri_margin} dB / {iri_p}"),
        ("GPS visible / >30°", f"{gps_nv} / {gps_nh}"),
        ("GPS max el / PDOP", f"{gps_max}° / {gps_pd}"),
        ("TLE epoch age (hrs)", f"{tle_age}"),
    ]
    lines = ["| | |", "|---|---|"]
    for k, v in rows:
        lines.append(f"| **{k}** | {v} |")
    return "\n".join(lines)


# ── Timeline: GPS → sensors → cap → RB TX ─────────────────────────
def timeline_figure(row: pd.Series, *, height: int = 140) -> go.Figure:
    """Build the horizontal timeline bar the HTML demo shows."""
    gps_t = _safe_float(row.get("GPS Time"), default=0.0)
    rb1 = _safe_float(row.get("RockBLOCK Time"),
                      default=_safe_float(row.get("Prev 1st RB Time"), 0.0))
    rb2 = _safe_float(row.get("Prev 2nd RB Time"), 0.0)
    sensor_gap = 5.0
    cap_charge = 30.0
    t_cap_start = gps_t + sensor_gap
    t_cap_end = t_cap_start + cap_charge
    t_rb_end = t_cap_end + rb1
    total = t_rb_end + rb2

    def _seg(x0, x1, color, label):
        return go.Bar(
            x=[x1 - x0], y=["timeline"], base=[x0],
            orientation="h",
            marker=dict(color=color, line=dict(color="#ffffff", width=1)),
            text=[label], textposition="inside", insidetextanchor="middle",
            textfont=dict(color="#ffffff", size=10),
            hovertext=[f"{label} ({x1 - x0:.1f}s)"],
            hoverinfo="text",
            showlegend=False,
        )

    gps_color = "#C62828" if str(row.get("GPS Valid", "")).upper() == "NO" else "#2E7D32"
    rb_color = "#C62828" if rb1 >= 70 else "#F57C00" if rb1 >= 30 else "#0078D4"

    fig = go.Figure()
    fig.add_trace(_seg(0, gps_t, gps_color, f"GPS {gps_t:.0f}s"))
    fig.add_trace(_seg(gps_t, t_cap_start, "#5A5A5A", ""))
    fig.add_trace(_seg(t_cap_start, t_cap_end, "#5E35B1", "cap"))
    fig.add_trace(_seg(t_cap_end, t_rb_end, rb_color, f"RB1 {rb1:.0f}s"))
    if rb2 > 0:
        fig.add_trace(_seg(t_rb_end, total, "#BC8CFF", f"RB2 {rb2:.0f}s"))

    fig.update_layout(
        barmode="stack",
        height=height,
        margin=dict(l=10, r=10, t=20, b=20),
        xaxis=dict(title="seconds since wake", showgrid=True,
                   gridcolor="#e8e8e8", range=[0, max(total * 1.02, 1)]),
        yaxis=dict(showticklabels=False, showgrid=False),
        plot_bgcolor="#ffffff",
    )
    return fig


# ── Retrospective verdict (rule-based) ────────────────────────────
def retrospective_verdict(row: pd.Series) -> str:
    gps_valid = str(row.get("GPS Valid", "YES")).upper() != "NO"
    gps_t = _safe_float(row.get("GPS Time"), 0.0)
    rb1 = _safe_float(row.get("RockBLOCK Time"),
                      _safe_float(row.get("Prev 1st RB Time"), 0.0))
    rb2 = _safe_float(row.get("Prev 2nd RB Time"), 0.0)
    n_iri = _safe_int(row.get("IRI_N_VISIBLE"), 0)
    best_el = _safe_float(row.get("IRI_BEST_EL_deg"), 0.0)
    pdop = _safe_float(row.get("GPS_PDOP"), 99.0)
    n_gps = _safe_int(row.get("GPS_N_VISIBLE"), 0)
    n_gps_hi = _safe_int(row.get("GPS_N_HIGH_EL"), 0)

    parts: list[str] = []

    if not gps_valid:
        parts.append(
            f"**GPS FAILED.** TTFF hit the ~30 s timeout with {n_gps} sats visible "
            f"(PDOP {pdop}). Geometry was adequate → failure was cold-start "
            f"ephemeris download, not constellation geometry. A 45 s timeout "
            f"likely would have succeeded."
        )
    elif gps_t > 28:
        parts.append(
            f"**GPS narrowly succeeded** at {gps_t} s (close to 30 s timeout). "
            f"Geometry fine (N={n_gps}, high-el={n_gps_hi}, PDOP={pdop}). "
            f"Consider raising GNSS_TIMEOUT to 45 s for margin."
        )
    elif gps_t < 5:
        parts.append(
            f"**GPS warm-start!** TTFF {gps_t} s — ephemeris likely persisted."
        )
    else:
        parts.append(
            f"**GPS nominal** (TTFF {gps_t} s, N={n_gps}, PDOP={pdop})."
        )

    if rb1 >= 70:
        parts.append(
            f"**Iridium: retry loop** — rb1 hit the 60 s SBDIX timeout, "
            f"recovered after retry (rb1+rb2 = {rb1 + rb2:.1f} s). "
            f"Peak elevation {best_el:.1f}°, {n_iri} sats visible → geometry "
            f"does **not** explain this failure. Likely modem state or "
            f"ground-segment factor."
        )
    elif rb1 >= 30:
        parts.append(
            f"**Iridium: first SBDIX slow** (rb1 {rb1} s). Next attempt "
            f"succeeded. Peak elevation {best_el:.1f}°, {n_iri} sats visible "
            f"— not geometry-limited."
        )
    elif rb1 < 15 and rb1 > 0:
        parts.append(
            f"**Iridium: clean link** — rb1 {rb1} s. "
            f"{n_iri} sats visible (peak {best_el:.1f}°)."
        )
    else:
        parts.append(
            f"**Iridium: normal** — rb1 {rb1} s. "
            f"{n_iri} sats visible (peak {best_el:.1f}°)."
        )

    return "\n\n".join(parts)


# ── Correlation scatter (RB1 vs N_visible / best_el) ──────────────
def correlation_scatter(df: pd.DataFrame, xcol: str, ycol: str,
                        *, title: str | None = None,
                        height: int = 280) -> go.Figure:
    """Plotly scatter used on the bottom of Field Replay.

    Rows with NaN / blank in either axis are dropped. Hover shows the
    device + TX timestamp.
    """
    if df is None or df.empty or xcol not in df.columns or ycol not in df.columns:
        fig = go.Figure()
        fig.update_layout(title=title or f"{xcol} vs {ycol}", height=height)
        return fig
    data = df[[xcol, ycol, "Timestamp"]].copy()
    data[xcol] = pd.to_numeric(data[xcol], errors="coerce")
    data[ycol] = pd.to_numeric(data[ycol], errors="coerce")
    data = data.dropna(subset=[xcol, ycol])

    fig = go.Figure(data=[go.Scatter(
        x=data[xcol], y=data[ycol],
        mode="markers",
        marker=dict(size=7, color="#0078D4",
                    line=dict(color="#003E6B", width=0.6)),
        hovertext=[f"{t} (row idx {i})" for t, i in zip(data["Timestamp"], data.index)],
        hoverinfo="x+y+text",
    )])
    fig.update_layout(
        title=title or f"{xcol} vs {ycol}",
        height=height,
        margin=dict(l=40, r=10, t=40, b=40),
        xaxis=dict(title=xcol, gridcolor="#e8e8e8"),
        yaxis=dict(title=ycol, gridcolor="#e8e8e8"),
        plot_bgcolor="#ffffff",
    )
    return fig


# ── Counterfactual: GNSS_TIMEOUT sweep ────────────────────────────
def gnss_timeout_sweep(df: pd.DataFrame, cutoff_s: float,
                       *, gps_fallback_ttff: float = 38.0) -> dict:
    """Replay the FY25 counterfactual from the HTML demo, on any frame.

    Rules: a row whose GPS TTFF > ``cutoff_s`` is counted as a new
    failure. Failed rows in the source data are assumed to succeed at
    ``gps_fallback_ttff`` seconds if ``cutoff_s >= 35`` (i.e. the
    historical cold-start would have finished in ~38 s).
    """
    if df is None or df.empty:
        return dict(cutoff_s=cutoff_s, n=0, would_fail=0,
                    fail_rate=0.0, mean_ttff=0.0,
                    mean_energy_j=0.0)
    n = len(df)
    would_fail = 0
    total_ttff = 0.0
    gps_t = pd.to_numeric(df.get("GPS Time", pd.Series(dtype=float)),
                          errors="coerce")
    fail_col = df.get("GPS Valid", pd.Series(dtype=str)).astype(str).str.upper()
    for idx in df.index:
        is_fail_now = str(fail_col.loc[idx]) == "NO"
        gt = gps_t.loc[idx] if idx in gps_t.index else float("nan")
        if is_fail_now:
            if cutoff_s >= 35:
                eff = gps_fallback_ttff
            else:
                would_fail += 1
                eff = cutoff_s
        else:
            if pd.isna(gt):
                eff = cutoff_s
            elif gt > cutoff_s:
                would_fail += 1
                eff = cutoff_s
            else:
                eff = float(gt)
        total_ttff += eff
    mean_ttff = total_ttff / max(1, n)
    return dict(
        cutoff_s=cutoff_s,
        n=n,
        would_fail=would_fail,
        fail_rate=round(would_fail / max(1, n) * 100.0, 2),
        mean_ttff=round(mean_ttff, 1),
        mean_energy_j=round(mean_ttff * 0.13, 2),
    )


# ── Helpers ───────────────────────────────────────────────────────
def _safe_float(v, default: float = 0.0) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if pd.isna(f):
        return default
    return f


def _safe_int(v, default: int = 0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default
