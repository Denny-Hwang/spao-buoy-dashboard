"""
Plotly style constants and helper functions for consistent chart styling.
"""

import plotly.graph_objects as go

TITLE_SIZE = 22
AXIS_TITLE_SIZE = 17
TICK_SIZE = 14
LEGEND_SIZE = 14
LINE_WIDTH = 3
MARKER_SIZE = 9
PLOT_HEIGHT = 480

COLORS = [
    "#3b82f6", "#ef4444", "#10b981", "#f59e0b", "#8b5cf6",
    "#ec4899", "#06b6d4", "#84cc16", "#f97316", "#6366f1",
]


def apply_plot_style(
    fig: go.Figure,
    title: str = "",
    x_title: str = "",
    y_title: str = "",
    height: int = PLOT_HEIGHT,
) -> go.Figure:
    """Apply standard SPAO plot styling to a Plotly figure."""
    fig.update_layout(
        title=dict(text=title, font=dict(size=TITLE_SIZE)),
        xaxis_title=dict(text=x_title, font=dict(size=AXIS_TITLE_SIZE)),
        yaxis_title=dict(text=y_title, font=dict(size=AXIS_TITLE_SIZE)),
        height=height,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(size=TICK_SIZE),
        legend=dict(font=dict(size=LEGEND_SIZE)),
        margin=dict(l=60, r=30, t=60, b=50),
        xaxis=dict(
            showgrid=True,
            gridcolor="#e5e7eb",
            tickfont=dict(size=TICK_SIZE),
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="#e5e7eb",
            tickfont=dict(size=TICK_SIZE),
        ),
    )
    return fig


def make_time_series(
    df,
    x_col: str,
    y_col: str,
    title: str = "",
    y_unit: str = "",
    color_col: str | None = None,
) -> go.Figure:
    """Create a styled time-series line plot."""
    fig = go.Figure()

    if color_col and color_col in df.columns:
        groups = df.groupby(color_col)
        for i, (name, group) in enumerate(groups):
            color = COLORS[i % len(COLORS)]
            fig.add_trace(go.Scatter(
                x=group[x_col], y=group[y_col],
                mode="lines+markers",
                name=str(name),
                line=dict(width=LINE_WIDTH, color=color),
                marker=dict(size=MARKER_SIZE),
            ))
    else:
        fig.add_trace(go.Scatter(
            x=df[x_col], y=df[y_col],
            mode="lines+markers",
            line=dict(width=LINE_WIDTH, color=COLORS[0]),
            marker=dict(size=MARKER_SIZE),
        ))

    y_label = f"{y_col} ({y_unit})" if y_unit else y_col
    apply_plot_style(fig, title=title or y_col, x_title=x_col, y_title=y_label)
    return fig


def make_scatter(
    df, x_col: str, y_col: str, title: str = "",
    x_unit: str = "", y_unit: str = "",
    color_col: str | None = None, trendline: bool = False,
) -> go.Figure:
    """Create a styled scatter plot with optional trendline."""
    import numpy as np

    fig = go.Figure()

    if color_col and color_col in df.columns:
        groups = df.groupby(color_col)
        for i, (name, group) in enumerate(groups):
            color = COLORS[i % len(COLORS)]
            fig.add_trace(go.Scatter(
                x=group[x_col], y=group[y_col],
                mode="markers",
                name=str(name),
                marker=dict(size=MARKER_SIZE, color=color),
            ))
    else:
        fig.add_trace(go.Scatter(
            x=df[x_col], y=df[y_col],
            mode="markers",
            marker=dict(size=MARKER_SIZE, color=COLORS[0]),
        ))

    if trendline and len(df) > 1:
        x_num = pd.to_numeric(df[x_col], errors="coerce")
        y_num = pd.to_numeric(df[y_col], errors="coerce")
        mask = x_num.notna() & y_num.notna()
        if mask.sum() > 1:
            coeffs = np.polyfit(x_num[mask], y_num[mask], 1)
            x_range = np.linspace(x_num[mask].min(), x_num[mask].max(), 100)
            fig.add_trace(go.Scatter(
                x=x_range, y=np.polyval(coeffs, x_range),
                mode="lines",
                name=f"Trend (y={coeffs[0]:.4f}x+{coeffs[1]:.4f})",
                line=dict(width=2, dash="dash", color="#94a3b8"),
            ))

    x_label = f"{x_col} ({x_unit})" if x_unit else x_col
    y_label = f"{y_col} ({y_unit})" if y_unit else y_col
    apply_plot_style(fig, title=title or f"{y_col} vs {x_col}", x_title=x_label, y_title=y_label)
    return fig


def make_3d_scatter(
    df, x_col: str, y_col: str, z_col: str,
    title: str = "", color_col: str | None = None,
) -> go.Figure:
    """Create a 3D scatter plot."""
    fig = go.Figure()

    if color_col and color_col in df.columns:
        groups = df.groupby(color_col)
        for i, (name, group) in enumerate(groups):
            color = COLORS[i % len(COLORS)]
            fig.add_trace(go.Scatter3d(
                x=group[x_col], y=group[y_col], z=group[z_col],
                mode="markers",
                name=str(name),
                marker=dict(size=4, color=color),
            ))
    else:
        fig.add_trace(go.Scatter3d(
            x=df[x_col], y=df[y_col], z=df[z_col],
            mode="markers",
            marker=dict(size=4, color=COLORS[0]),
        ))

    fig.update_layout(
        title=dict(text=title or f"{z_col} vs {x_col} vs {y_col}", font=dict(size=TITLE_SIZE)),
        scene=dict(
            xaxis_title=x_col,
            yaxis_title=y_col,
            zaxis_title=z_col,
        ),
        height=600,
    )
    return fig


# Import pandas for trendline
import pandas as pd
