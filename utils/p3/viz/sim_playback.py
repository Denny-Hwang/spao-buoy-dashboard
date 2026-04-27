"""Animated playback for the TX Simulator / Tracker pages.

Plotly's built-in ``frames`` / ``updatemenus`` give us Play/Pause +
speed-multiplier buttons for free — no Streamlit autorefresh, no
server reruns, no flicker. Speed is implemented the HTML-prototype
way: the frame count stays the same, but the *playback rate* (ms per
frame) changes. 1× scans the orbit at roughly realistic speed; 30×
covers a full orbit in about 3 seconds, still showing every frame.

The module also ships a Plotly ``Scattergeo``-based map overlay
animation that the Simulator Map-overlay mode now uses instead of a
Folium + autorefresh combination. Same frames, same Play button —
just rendered against a world map.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from utils.p3 import iridium_link as _link
from utils.p3.sgp4_engine import Sat, look_angles, sat_subpoint


_DEG = math.pi / 180.0


# Speed presets: (label, ms_per_frame). Lower ms = faster playback.
# 1× ≈ 500 ms per frame feels like a smooth orbit walk. 30× uses the
# browser's minimum usable duration (~17 ms = 60 fps).
DEFAULT_SPEEDS: tuple[tuple[str, int], ...] = (
    ("▶ 1×", 500),
    ("▶ 5×", 100),
    ("▶ 10×", 50),
    ("▶ 30×", 17),
)


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
    speeds: tuple[tuple[str, int], ...] = DEFAULT_SPEEDS,
) -> go.Figure:
    """Build a Plotly polar figure with Play / Pause + speed controls.

    All animation is **client-side**. Each speed button re-plays the
    same frame set at a different ``frame.duration``, so 30× is a
    genuinely faster playback — not a frame skip.
    """
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
        # Bottom margin accommodates two rows below the chart: the
        # speed-button row (pad.t=10, ~32 px tall) and the scrub
        # slider (pad.t=70, ~22 px tall).
        margin=dict(l=30, r=30, t=60, b=110),
        polar=dict(
            bgcolor="#f4f6f8",
            radialaxis=dict(range=[0, 90], tickvals=[0, 30, 60, 90],
                            ticktext=["90°", "60°", "30°", "0°"]),
            angularaxis=dict(direction="clockwise", rotation=90,
                             tickvals=[0, 90, 180, 270],
                             ticktext=["N", "E", "S", "W"]),
        ),
        updatemenus=[
            # Play buttons sit ~10 px below the chart on a dedicated
            # row; the frame-scrub slider lives on its own row 60 px
            # further down. Putting them on the same vertical band (as
            # the previous version did) made the buttons hide the
            # left third of the slider.
            dict(
                type="buttons",
                showactive=False,
                y=0, x=0,
                xanchor="left", yanchor="top",
                pad=dict(t=10, r=10),
                direction="right",
                buttons=[
                    *[
                        dict(
                            label=lab,
                            method="animate",
                            args=[None,
                                  dict(mode="immediate",
                                       frame=dict(duration=ms, redraw=True),
                                       fromcurrent=True,
                                       transition=dict(duration=0))],
                        )
                        for (lab, ms) in speeds
                    ],
                    dict(
                        label="⏸ Pause",
                        method="animate",
                        args=[[None],
                              dict(mode="immediate",
                                   frame=dict(duration=0, redraw=False),
                                   transition=dict(duration=0))],
                    ),
                ],
            ),
        ],
        sliders=[dict(
            active=0,
            y=0, x=0.1,
            xanchor="left", yanchor="top",
            len=0.85,
            pad=dict(t=70, b=10),
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


# ── World-map animation (Scattergeo + frames) ─────────────────────
# The polar sky plot is perfect for sat-geometry analysis, but the
# HTML prototype also had an earth-map overlay with ground-tracks +
# connection lines. We reproduce that here using Plotly's Scattergeo
# trace — like the polar version the animation runs entirely in the
# browser (frames + updatemenus), so there is zero server rerun and
# no flicker. Speed is controlled via frame.duration so 30× is a
# genuinely faster replay, not a frame skip.
_MAP_STYLES: dict[str, dict] = {
    "Satellite": dict(
        projection_type="natural earth",
        showland=True, landcolor="rgb(225,215,190)",
        showocean=True, oceancolor="rgb(135,170,200)",
        showcountries=True, countrycolor="rgb(90,90,90)",
        showlakes=True, lakecolor="rgb(135,170,200)",
        showcoastlines=True, coastlinecolor="rgb(60,80,100)",
        bgcolor="rgba(0,0,0,0)",
    ),
    "Terrain": dict(
        projection_type="natural earth",
        showland=True, landcolor="rgb(230,230,220)",
        showocean=True, oceancolor="rgb(180,200,230)",
        showcountries=True, countrycolor="rgb(120,120,120)",
        showcoastlines=True, coastlinecolor="rgb(60,80,100)",
        bgcolor="rgba(0,0,0,0)",
    ),
    "Dark": dict(
        projection_type="natural earth",
        showland=True, landcolor="rgb(45,55,70)",
        showocean=True, oceancolor="rgb(15,25,35)",
        showcountries=True, countrycolor="rgb(80,90,100)",
        showcoastlines=True, coastlinecolor="rgb(120,130,150)",
        bgcolor="rgba(0,0,0,0)",
    ),
}
MAP_STYLE_LABELS: tuple[str, ...] = tuple(_MAP_STYLES.keys())


def _map_frame_traces(sats: Sequence[Sat],
                      dt: datetime,
                      obs_lat: float, obs_lon: float,
                      min_el_deg: float) -> list[go.Scattergeo]:
    """Traces for ONE frame: observer + visible sat sub-points + link lines."""
    vis_lats: list[float] = []
    vis_lons: list[float] = []
    vis_names: list[str] = []
    vis_el: list[float] = []
    link_lats: list[float] = []
    link_lons: list[float] = []

    for s in sats:
        la = look_angles(s, dt, obs_lat, obs_lon)
        if la is None or la.el_deg <= min_el_deg:
            continue
        sub = sat_subpoint(s, dt)
        if sub is None:
            continue
        lat_s, lon_s, _alt = sub
        vis_lats.append(lat_s)
        vis_lons.append(lon_s)
        vis_names.append(s.name)
        vis_el.append(la.el_deg)
        # Null-separated segments let a single trace draw many lines.
        link_lats.extend([obs_lat, lat_s, None])
        link_lons.extend([obs_lon, lon_s, None])

    return [
        # Dashed connection lines observer → sat (drawn first so dots sit on top)
        go.Scattergeo(
            lat=link_lats, lon=link_lons,
            mode="lines",
            line=dict(color="rgba(88,166,255,0.55)", width=1.2),
            hoverinfo="skip",
            showlegend=False,
        ),
        # Observer (red circle)
        go.Scattergeo(
            lat=[obs_lat], lon=[obs_lon],
            mode="markers",
            marker=dict(size=11, color="#C62828",
                        line=dict(color="#ffffff", width=1.5)),
            name="Observer",
            hovertext=[f"Observer ({obs_lat:.3f}, {obs_lon:.3f})"],
            hoverinfo="text",
            showlegend=False,
        ),
        # Visible sats (blue circles)
        go.Scattergeo(
            lat=vis_lats, lon=vis_lons,
            mode="markers",
            marker=dict(
                size=[6 + e / 20.0 for e in vis_el] or [6],
                color="#1f6feb",
                line=dict(color="#0b3d66", width=0.8),
            ),
            hovertext=[f"{n}<br>el {e:.1f}°" for n, e in zip(vis_names, vis_el)],
            hoverinfo="text",
            name="Iridium",
            showlegend=False,
        ),
    ]


def build_map_playback_figure(
    sats: Sequence[Sat],
    *,
    start_utc: datetime,
    duration_h: float,
    lat_deg: float,
    lon_deg: float,
    min_el_deg: float = 8.2,
    step_s: float = 60.0,
    style: str = "Satellite",
    height: int = 540,
    speeds: tuple[tuple[str, int], ...] = DEFAULT_SPEEDS,
    title: str = "Iridium sat ground tracks — simulated playback",
) -> go.Figure:
    """Build a world-map animation: observer + sat sub-points + link lines.

    Uses Plotly's native Scattergeo + frames — animation is entirely
    client-side and speed buttons change ``frame.duration`` for
    smooth, flicker-free playback.
    """
    n_steps = max(1, int(duration_h * 3600.0 / step_s))
    geo = _MAP_STYLES.get(style, _MAP_STYLES["Satellite"])

    # Pre-compute every frame's traces. This is bounded by n_steps
    # (≤ ~720 for a 6 h / 30 s simulation) and a handful of sats — a
    # few tens of ms even on Streamlit Cloud.
    frames: list[go.Frame] = []
    first_traces: list[go.Scattergeo] = []
    for i in range(n_steps + 1):
        t = start_utc + timedelta(seconds=i * step_s)
        traces = _map_frame_traces(sats, t, lat_deg, lon_deg, min_el_deg)
        tstr = t.strftime("%Y-%m-%d %H:%M:%SZ")
        frames.append(go.Frame(
            data=traces,
            name=str(i),
            layout=go.Layout(title=f"{title} · t = {tstr}"),
        ))
        if i == 0:
            first_traces = traces

    fig = go.Figure(data=first_traces)
    fig.frames = frames

    slider_steps = [
        dict(
            method="animate",
            label=str(f.name),
            args=[[f.name],
                  dict(mode="immediate",
                       frame=dict(duration=0, redraw=True),
                       transition=dict(duration=0))],
        )
        for f in frames
    ]

    # Auto-centre the map on the observer with a zoom level that
    # covers ~5000 km (Iridium horizon footprint + a margin).
    fig.update_layout(
        title=title,
        height=height,
        # Bottom margin matches the polar figure — speed-button row +
        # scrub slider need ~100 px of vertical space below the map.
        margin=dict(l=10, r=10, t=50, b=110),
        geo=dict(
            **geo,
            center=dict(lat=lat_deg, lon=lon_deg),
            projection_scale=2.6,   # tighter view than default
        ),
        updatemenus=[dict(
            # Buttons row first (pad.t=10), slider row 60 px below
            # (pad.t=70). Same staggered layout as the polar figure —
            # the prior single-row layout overlapped the slider.
            type="buttons",
            showactive=False,
            y=0, x=0,
            xanchor="left", yanchor="top",
            pad=dict(t=10, r=10),
            direction="right",
            buttons=[
                *[
                    dict(
                        label=lab,
                        method="animate",
                        args=[None,
                              dict(mode="immediate",
                                   frame=dict(duration=ms, redraw=True),
                                   fromcurrent=True,
                                   transition=dict(duration=0))],
                    )
                    for (lab, ms) in speeds
                ],
                dict(
                    label="⏸ Pause",
                    method="animate",
                    args=[[None],
                          dict(mode="immediate",
                               frame=dict(duration=0, redraw=False),
                               transition=dict(duration=0))],
                ),
            ],
        )],
        sliders=[dict(
            active=0,
            y=0, x=0.1,
            xanchor="left", yanchor="top",
            len=0.85,
            pad=dict(t=70, b=10),
            currentvalue=dict(prefix="frame #",
                              font=dict(size=11, color="#1A1A1A")),
            steps=slider_steps,
        )],
    )
    return fig
