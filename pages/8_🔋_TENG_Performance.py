"""
Page 8 — TENG Performance.

Wave-to-power transfer function and normalized-power trend panels.
All analysis functions live in ``utils.p2.viz.teng_panels`` so this
page stays a thin orchestration layer.
"""

from __future__ import annotations

import importlib

import pandas as pd
import streamlit as st

st.set_page_config(page_title="TENG Performance", page_icon="🔋", layout="wide")

from utils.theme import (  # noqa: E402
    render_header, render_footer, render_sidebar, inject_custom_css,
    PNNL_BLUE,
)

inject_custom_css()
render_sidebar()
render_header()

st.markdown(
    f'<h1 style="color:{PNNL_BLUE}; margin-top:0;">🔋 TENG Performance</h1>',
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────────────────────────────
# Phase 2 sidebar toggle (defensively imported so a broken helper
# cannot crash the Streamlit app).
# ──────────────────────────────────────────────────────────────────────
try:
    _flag = importlib.import_module("utils.p2.__phase2_flag")
    _flag.render_toggle_in_sidebar()
except Exception as exc:  # noqa: BLE001
    st.sidebar.caption(f"Phase 2 toggle unavailable: {exc}")


# ──────────────────────────────────────────────────────────────────────
# Data loading
# ──────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=120)
def _load_data() -> pd.DataFrame:
    from utils.sheets_client import get_all_data
    try:
        return get_all_data()
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Could not load data: {exc}")
        return pd.DataFrame()


df = _load_data()

# ── Shared device + date-range toolbar ────────────────────────────────
try:
    toolbar = importlib.import_module("utils.p2.ui_toolbar")
    df, selected_devices, time_col, dev_col = toolbar.render_device_time_filter(
        df, key_prefix="p8",
    )
except Exception as exc:  # noqa: BLE001
    st.error(f"Toolbar unavailable: {exc}")
    st.stop()

REQUIRED = ("WAVE_H_cm", "WAVE_T_ds")
missing = [c for c in REQUIRED if c not in df.columns]
if df.empty or missing:
    st.warning(
        "Phase 2 enrichment not yet available for this selection. "
        f"Missing columns: {missing or '(empty selection)'}. "
        "Trigger the `enrichment_hourly` GitHub Action to populate "
        "wave columns, then reload."
    )
    st.stop()


# ──────────────────────────────────────────────────────────────────────
# KPI header
# ──────────────────────────────────────────────────────────────────────
try:
    panels = importlib.import_module("utils.p2.viz.teng_panels")
    # Streamlit Cloud occasionally serves a stale cached module that
    # predates the DESCRIPTIONS dict. Force a reload so new keys
    # introduced in follow-up deploys are always available.
    panels = importlib.reload(panels)
    kpis = panels.compute_kpis(df)
except Exception as exc:  # noqa: BLE001
    st.error(f"Failed to build TENG panels: {exc}")
    st.stop()

# Defensive: the old module version shipped without DESCRIPTIONS. Fall
# back to an empty dict so a missing description never crashes the page.
_DESC: dict = getattr(panels, "DESCRIPTIONS", {}) or {}

col1, col2, col3 = st.columns(3)
col1.metric("Harvested today", f"{kpis['today_joules']:.1f} J")
col2.metric("Session avg P_TENG", f"{kpis['avg_power_mw']:.2f} mW")
col3.metric("P_TENG / P_wave", f"{kpis['ratio_pct']:.2f} %")

st.divider()

# ──────────────────────────────────────────────────────────────────────
# Main-area tabs: A1 Transfer │ A4 Normalized trend │ Long-term
# ──────────────────────────────────────────────────────────────────────
tab_a1, tab_a4, tab_long = st.tabs([
    "A1 — Transfer function",
    "A4 — Normalized power trend",
    "Long-term (Derived_Daily)",
])

with tab_a1:
    st.subheader("A1 — Wave-to-Power Transfer Function")
    sub_hm, sub_loglog, sub_flux = st.tabs([
        "Hs × Tp heatmap",
        "Log-log P vs Hs²·Tp",
        "vs theoretical flux",
    ])
    with sub_hm:
        st.markdown(f"*{_DESC.get('hs_tp_heatmap', '')}*")
        st.plotly_chart(panels.build_hs_tp_heatmap(df), use_container_width=True)
        st.caption(
            f"Reference markers: Jung 2024 ({panels.JUNG_2024['P_mW']} mW, "
            f"blue star) and Lu 2026 ({panels.LU_2026['P_mW']} mW, red star)."
        )
    with sub_loglog:
        st.markdown(f"*{_DESC.get('loglog_hs2tp', '')}*")
        st.plotly_chart(panels.build_loglog_hs2tp(df), use_container_width=True)
        st.caption("Slope of ~1 indicates P_TENG scales linearly with Hs²·Tp.")
    with sub_flux:
        st.markdown(f"*{_DESC.get('flux_scatter', '')}*")
        st.plotly_chart(panels.build_flux_scatter(df), use_container_width=True)
        st.caption("Theoretical flux from Falnes (2002) Eq. 6.19 with Te = 0.9·Tp.")

with tab_a4:
    st.subheader("A4 — Normalized Power Trend")
    st.markdown(f"*{_DESC.get('eta_trend', '')}*")
    level = st.radio(
        "Normalization level",
        options=[0, 1, 2],
        format_func=lambda L: {0: "0 — raw mW", 1: "1 — / Hs²", 2: "2 — / (Hs²·Tp)"}[L],
        horizontal=True,
        index=2,
        key="p7_norm_level",
    )

    trend = panels.build_eta_trend(df, level=int(level))
    st.plotly_chart(trend["fig"], use_container_width=True)

    badge_col, mk_col = st.columns(2)
    if trend["mk_p"] == trend["mk_p"]:  # not NaN
        badge_col.metric(
            "Theil-Sen slope (per day)",
            f"{trend['slope']:.3g}",
        )
        mk_col.metric(
            "Mann-Kendall",
            trend["mk_trend"],
            help=f"p = {trend['mk_p']:.3g} (N = {trend['n']})",
        )

    st.markdown(f"*{_DESC.get('week_violin', '')}*")
    st.plotly_chart(
        panels.build_week_violin(df, level=int(level)),
        use_container_width=True,
    )

    st.info(
        "⚠️ η₁ and η₂ are **proxies only**. A trend in η does not uniquely "
        "identify generator degradation — wave climatology can shift "
        "independently. Always pair these metrics with direct health "
        "indicators (RMS voltage, peak output)."
    )

# ──────────────────────────────────────────────────────────────────────
# Long-term trend (Derived_Daily)
# ──────────────────────────────────────────────────────────────────────


@st.cache_data(ttl=300)
def _load_derived_daily() -> pd.DataFrame:
    """Read the Derived_Daily worksheet; empty DataFrame on any failure."""
    try:
        import os
        from utils.p2.derived_io import read_derived_daily
        sheet_id = (
            st.secrets.get("GOOGLE_SHEETS_ID", None)
            if hasattr(st, "secrets") else None
        ) or os.environ.get("GOOGLE_SHEETS_ID", "")
        if not sheet_id:
            try:
                from utils.sheets_client import SHEET_ID as _FALLBACK_ID
                sheet_id = _FALLBACK_ID
            except Exception:
                sheet_id = ""
        if not sheet_id:
            return pd.DataFrame()
        return read_derived_daily(sheet_id)
    except Exception as exc:  # noqa: BLE001
        st.caption(f"Derived_Daily unavailable: {exc}")
        return pd.DataFrame()


with tab_long:
    st.subheader("Long-term trend (Derived_Daily)")
    daily_df = _load_derived_daily()
    if daily_df.empty:
        st.info(
            "Derived_Daily worksheet not yet populated. "
            "Run the `derived_daily` GitHub Action (or `python scripts/compute_daily_derived.py`) "
            "to generate the long-term trend table."
        )
    else:
        try:
            trend_panels = importlib.import_module("utils.p2.viz.trend_panels")
            st.plotly_chart(
                trend_panels.build_teng_long_trend(daily_df),
                use_container_width=True,
            )
        except Exception as exc:  # noqa: BLE001
            st.caption(f"Long-term trend rendering failed: {exc}")

render_footer()
