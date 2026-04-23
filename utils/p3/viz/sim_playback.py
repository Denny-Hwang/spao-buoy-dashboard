"""Animated playback for the TX Simulator page.

Plotly's built-in ``frames`` / ``updatemenus`` give us a Play/Pause
button for free — no extra dependency. The animation shows two panels
driven by the same timeline:

1. A polar sky plot of the Iridium constellation at frame time ``t``.
2. A rolling KPI bar (visible sats / best elevation / link margin).

For the map view (which Plotly polar can't fully replace), the caller
is expected to also render a separate slider-driven Folium map; this
module only handles the Plotly side of the animation.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from utils.p3 import iridium_link as _link
from utils.p3.sgp4_engine import Sat, look_angles


_DEG = math.pi / 180.0


def compute_frames(
    sats: Sequence[Sat],
    *,
    start_utc: datetime,
    duration_h: float,
    lat_deg: float,
    lon_deg: float,
    min_el_deg: float = 8.2,
    step_s: float = 60.0,
) -> pd.DataFrame:
    """Return a long-format frame table with one row per (t, sat, visible).

    Columns: ``t_utc, t_idx, sat, el_deg, az_deg, visible``. Also
    includes ``best_el``, ``best_margin``, ``n_visible`` summary columns
    on the row with the minimum ``sat_idx`` for that frame (used by
    the KPI bar).

    The caller decides the ``step_s`` vs ``duration_h`` trade-off;
    60 s × 6 h = 360 frames which still animates smoothly.
    """
    n_steps = max(1, int(duration_h * 3600.0 / step_s))
    rows: list[dict] = []
    for i in range(n_steps + 1):
        t = start_utc + timedelta(seconds=i * step_s)
        frame_best_el = -90.0
        frame_best_margin = float("-inf")
        frame_n_vis = 0
        for s in sats:
            la = look_angles(s, t, lat_deg, lon_deg)
            if la is None:
                continue
            is_vis = la.el_deg > min_el_deg
            if is_vis:
                frame_n_vis += 1
                if la.el_deg > frame_best_el:
                    frame_best_el = la.el_deg
                    frame_best_margin = _link.link_margin_db(la.el_deg)
            rows.append(dict(
                t_utc=t,
                t_idx=i,
                sat=s.name,
                el_deg=la.el_deg,
                az_deg=la.az_deg,
                visible=is_vis,
            ))
        # Attach summary fields to the first row of this frame.
        for r in rows[-len(sats):] if len(sats) else []:
            r["n_visible"] = frame_n_vis
            r["best_el"] = frame_best_el if frame_best_el > -90.0 else None
            r["best_margin"] = frame_best_margin if frame_best_margin > float("-inf") else None
    return pd.DataFrame(rows)


def _frame_to_scatter(df_frame: pd.DataFrame, *, min_el_deg: float) -> go.Scatterpolar:
    vis = df_frame[df_frame["el_deg"] > min_el_deg]
    return go.Scatterpolar(
        theta=vis["az_deg"],
        r=90.0 - vis["el_deg"],
        mode="markers",
        marker=dict(
            size=[6 + v / 25.0 for v in vis["el_deg"]],
            color="#0078D4",
            line=dict(color="#0d1117", width=0.6),
        ),
        hovertext=[f"{n}<br>el={e:.1f}°" for n, e in zip(vis["sat"], vis["el_deg"])],
        hoverinfo="text",
        name="visible",
        showlegend=False,
    )


def build_playback_figure(
    frames_df: pd.DataFrame,
    *,
    min_el_deg: float = 8.2,
    title: str = "Iridium sky — simulated playback",
    height: int = 520,
) -> go.Figure:
    """Build a Plotly polar figure with Play / Pause controls."""
    if frames_df is None or frames_df.empty:
        fig = go.Figure()
        fig.update_layout(title="No frames — run simulation first", height=height)
        return fig

    # First frame as the "steady state" scatter
    first_idx = frames_df["t_idx"].min()
    first = frames_df[frames_df["t_idx"] == first_idx]

    fig = go.Figure(data=[_frame_to_scatter(first, min_el_deg=min_el_deg)])

    # Build plotly frames
    plotly_frames = []
    for idx, grp in frames_df.groupby("t_idx"):
        tstr = pd.Timestamp(grp["t_utc"].iloc[0]).strftime("%Y-%m-%d %H:%M:%SZ")
        plotly_frames.append(
            go.Frame(
                data=[_frame_to_scatter(grp, min_el_deg=min_el_deg)],
                name=str(idx),
                layout=go.Layout(title=f"{title} · t = {tstr}"),
            )
        )
    fig.frames = plotly_frames

    # Slider / Play button
    slider_steps = [
        dict(
            method="animate",
            label=str(f.name),
            args=[[f.name],
                  dict(mode="immediate",
                       frame=dict(duration=0, redraw=True),
                       transition=dict(duration=0))],
        )
        for f in plotly_frames
    ]
    fig.update_layout(
        title=title,
        height=height,
        margin=dict(l=30, r=30, t=60, b=60),
        polar=dict(
            bgcolor="#f4f6f8",
            radialaxis=dict(range=[0, 90], tickvals=[0, 30, 60, 90],
                            ticktext=["90°", "60°", "30°", "0°"]),
            angularaxis=dict(direction="clockwise", rotation=90,
                             tickvals=[0, 90, 180, 270],
                             ticktext=["N", "E", "S", "W"]),
        ),
        updatemenus=[dict(
            type="buttons",
            showactive=False,
            y=0, x=0,
            xanchor="left", yanchor="top",
            pad=dict(t=50, r=10),
            buttons=[
                dict(label="▶ Play",
                     method="animate",
                     args=[None, dict(mode="immediate",
                                      frame=dict(duration=250, redraw=True),
                                      fromcurrent=True,
                                      transition=dict(duration=0))]),
                dict(label="⏸ Pause",
                     method="animate",
                     args=[[None], dict(mode="immediate",
                                        frame=dict(duration=0, redraw=False),
                                        transition=dict(duration=0))]),
            ],
        )],
        sliders=[dict(
            active=0,
            y=0, x=0.1,
            xanchor="left", yanchor="top",
            len=0.85,
            pad=dict(t=50, b=10),
            currentvalue=dict(prefix="frame #",
                              font=dict(size=11, color="#1A1A1A")),
            steps=slider_steps,
        )],
    )
    return fig


def kpi_series(frames_df: pd.DataFrame) -> pd.DataFrame:
    """Return one row per frame with the KPI summary (for a line chart)."""
    if frames_df is None or frames_df.empty:
        return pd.DataFrame(columns=["t_utc", "n_visible", "best_el", "best_margin"])
    summary = (frames_df.sort_values(["t_idx"])
               .groupby("t_idx", as_index=False)
               .agg(t_utc=("t_utc", "first"),
                    n_visible=("n_visible", "first"),
                    best_el=("best_el", "first"),
                    best_margin=("best_margin", "first")))
    return summary
