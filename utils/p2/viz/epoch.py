"""
Superposed-epoch multi-panel plots.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

try:
    import plotly.graph_objects as go  # type: ignore
    from plotly.subplots import make_subplots  # type: ignore
except Exception:  # pragma: no cover
    go = None  # type: ignore[assignment]
    make_subplots = None  # type: ignore[assignment]


def plot_superposed(
    events_df: pd.DataFrame,
    window_df: pd.DataFrame | None = None,
    variables: Iterable[str] | None = None,
    title: str = "Superposed epoch composite",
):
    """Return a multi-panel Plotly figure of a superposed-epoch composite.

    Parameters
    ----------
    events_df : DataFrame
        Long-format output of ``utils.p2.physics.storms.superposed_epoch``
        with columns ``event_idx``, ``lag_hours``, and one column per
        variable to plot.
    window_df : DataFrame, optional
        Unused — accepted for API symmetry with plot callers that also
        want to pass the raw window. Reserved for future use.
    variables : iterable of str, optional
        Subset of variable columns to draw. Defaults to every numeric
        column that is not ``event_idx`` or ``lag_hours``.
    """
    if go is None or make_subplots is None:  # pragma: no cover
        raise RuntimeError("plotly is required for utils.p2.viz.epoch")
    del window_df  # reserved

    if variables is None:
        variables = [
            c for c in events_df.columns
            if c not in ("event_idx", "lag_hours")
            and pd.api.types.is_numeric_dtype(events_df[c])
        ]
    variables = list(variables)
    if not variables:
        return go.Figure()

    fig = make_subplots(
        rows=len(variables), cols=1, shared_xaxes=True,
        subplot_titles=variables,
    )

    for row, var in enumerate(variables, start=1):
        grouped = events_df.groupby("lag_hours")[var]
        mean = grouped.mean()
        std = grouped.std()
        lag = mean.index.values

        # Individual event traces (thin, semi-transparent).
        for eid, sub in events_df.groupby("event_idx"):
            fig.add_trace(
                go.Scatter(
                    x=sub["lag_hours"], y=sub[var],
                    mode="lines",
                    line=dict(color="rgba(120,120,120,0.25)", width=1),
                    showlegend=False,
                    name=f"event {eid}",
                ),
                row=row, col=1,
            )

        # Mean ± 1σ ribbon.
        fig.add_trace(
            go.Scatter(
                x=np.concatenate([lag, lag[::-1]]),
                y=np.concatenate([mean + std, (mean - std)[::-1]]),
                fill="toself",
                fillcolor="rgba(0,0,255,0.15)",
                line=dict(color="rgba(0,0,0,0)"),
                showlegend=False,
                name=f"{var} ±σ",
            ),
            row=row, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=lag, y=mean, mode="lines",
                line=dict(color="blue", width=2),
                name=f"{var} mean" if row == 1 else None,
                showlegend=(row == 1),
            ),
            row=row, col=1,
        )
        fig.add_vline(x=0, line_dash="dash", line_color="red", row=row, col=1)

    fig.update_layout(title=title, height=280 * len(variables))
    fig.update_xaxes(title_text="Lag (hours)", row=len(variables), col=1)
    return fig


__all__ = ["plot_superposed"]
