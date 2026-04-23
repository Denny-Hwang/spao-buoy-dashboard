"""Plotly polar sky plot for Iridium and GPS satellites.

Used on the Tracker, Field-Replay, and TX-Simulator pages. Renders:

* concentric dashed rings at 30°, 60° elevation;
* a coloured dashed circle marking the elevation mask;
* one marker per satellite — visible ones coloured by constellation,
  below-horizon ones faded;
* N/S/E/W labels and a central red dot for the observer.

Returns a :class:`plotly.graph_objects.Figure` so the caller decides
whether to render it via ``st.plotly_chart`` or compose it into a
multi-frame animation.
"""

from __future__ import annotations

from typing import Sequence

import math
import pandas as pd
import plotly.graph_objects as go

from utils.p3.sgp4_engine import Sat, sky_positions


_DEG = math.pi / 180.0

_IRI_COLORS = [
    "#58a6ff", "#3fb950", "#d29922", "#f85149", "#bc8cff",
    "#39d2c0", "#ff7b72", "#79c0ff",
]
_GPS_COLORS = ["#2E7D32", "#0078D4", "#C62828", "#F57C00", "#5E35B1"]


def _color_for(idx: int, constellation: str) -> str:
    pool = _GPS_COLORS if constellation == "GPS" else _IRI_COLORS
    return pool[idx % len(pool)]


def _label_for(name: str, constellation: str) -> str:
    if constellation == "GPS":
        import re
        m = re.search(r"PRN\s*(\d+)", name)
        if m:
            return f"PRN{m.group(1)}"
        parts = name.strip().split()
        return parts[-1] if parts else name
    return name.replace("IRIDIUM ", "").replace("Iridium ", "")


def sky_figure(
    sats: Sequence[Sat],
    dt,
    lat_deg: float,
    lon_deg: float,
    *,
    min_el_deg: float = 8.2,
    constellation: str = "Iridium",
    title: str | None = None,
    height: int = 440,
    show_labels: bool = True,
) -> go.Figure:
    """Return a Plotly polar sky plot for the given snapshot."""
    df = sky_positions(sats, dt, lat_deg, lon_deg, min_el_deg=-90.0)
    if df.empty:
        df = pd.DataFrame(columns=["name", "el_deg", "az_deg", "visible"])

    fig = go.Figure()

    # Above-horizon sats
    vis = df[df["el_deg"] > min_el_deg]
    below = df[df["el_deg"] <= min_el_deg]

    if not vis.empty:
        fig.add_trace(go.Scatterpolar(
            theta=vis["az_deg"],
            r=90.0 - vis["el_deg"],
            mode="markers+text" if show_labels else "markers",
            marker=dict(
                size=[6 + v / 25.0 for v in vis["el_deg"]],
                color=[_color_for(i, constellation) for i in range(len(vis))],
                line=dict(color="#0d1117", width=1),
            ),
            text=[_label_for(n, constellation) for n in vis["name"]] if show_labels else None,
            textposition="top center",
            textfont=dict(size=10, color="#1A1A1A"),
            hovertext=[
                f"{n}<br>el={e:.1f}°<br>az={a:.0f}°"
                for n, e, a in zip(vis["name"], vis["el_deg"], vis["az_deg"])
            ],
            hoverinfo="text",
            name=f"{constellation} visible",
            showlegend=False,
        ))

    if not below.empty:
        fig.add_trace(go.Scatterpolar(
            theta=below["az_deg"],
            r=[min(90.0 - e, 89.0) for e in below["el_deg"]],
            mode="markers",
            marker=dict(size=3, color="rgba(50,55,65,0.35)"),
            hovertext=[
                f"{n}<br>el={e:.1f}° (below mask)<br>az={a:.0f}°"
                for n, e, a in zip(below["name"], below["el_deg"], below["az_deg"])
            ],
            hoverinfo="text",
            name=f"{constellation} below mask",
            showlegend=False,
        ))

    # Mask ring (drawn as a dense scatter in dashed style via a line trace).
    import numpy as np
    mask_theta = np.linspace(0, 360, 180)
    fig.add_trace(go.Scatterpolar(
        theta=mask_theta,
        r=[90.0 - min_el_deg] * len(mask_theta),
        mode="lines",
        line=dict(color="#d29922", width=1, dash="dash"),
        name=f"{min_el_deg:.1f}° mask",
        hoverinfo="skip",
        showlegend=False,
    ))

    fig.update_layout(
        title=title or f"{constellation} sky @ observer",
        height=height,
        margin=dict(l=30, r=30, t=50, b=30),
        polar=dict(
            bgcolor="#f4f6f8",
            radialaxis=dict(
                range=[0, 90],
                tickvals=[0, 30, 60, 90],
                ticktext=["90°", "60°", "30°", "0°"],
                tickfont=dict(size=9, color="#5A5A5A"),
                gridcolor="#dedede",
            ),
            angularaxis=dict(
                direction="clockwise",
                rotation=90,
                tickmode="array",
                tickvals=[0, 90, 180, 270],
                ticktext=["N", "E", "S", "W"],
                tickfont=dict(size=11, color="#1A1A1A"),
                gridcolor="#dedede",
            ),
        ),
        showlegend=False,
    )
    return fig


def sky_figure_combined(
    iridium_sats: Sequence[Sat],
    gps_sats: Sequence[Sat],
    dt,
    lat_deg: float,
    lon_deg: float,
    *,
    iri_min_el: float = 8.2,
    gps_min_el: float = 5.0,
    height: int = 440,
) -> go.Figure:
    """Return an overlay plot with Iridium (blue-ish) + GPS (green-ish)."""
    fig = sky_figure(
        iridium_sats, dt, lat_deg, lon_deg,
        min_el_deg=iri_min_el, constellation="Iridium",
        title="Combined sky view", height=height,
    )
    gps_df = sky_positions(gps_sats, dt, lat_deg, lon_deg, min_el_deg=-90.0)
    vis = gps_df[gps_df["el_deg"] > gps_min_el]
    if not vis.empty:
        fig.add_trace(go.Scatterpolar(
            theta=vis["az_deg"],
            r=90.0 - vis["el_deg"],
            mode="markers",
            marker=dict(
                size=[5 + v / 30.0 for v in vis["el_deg"]],
                color="#2E7D32",
                symbol="diamond",
                line=dict(color="#ffffff", width=0.8),
            ),
            hovertext=[
                f"{n}<br>el={e:.1f}°<br>az={a:.0f}°"
                for n, e, a in zip(vis["name"], vis["el_deg"], vis["az_deg"])
            ],
            hoverinfo="text",
            name="GPS visible",
            showlegend=False,
        ))
    return fig
