"""
Page 7 — TENG Performance.

Wave-to-power transfer function and normalized-power trend panels.
All analysis functions live in ``utils.p2.viz.teng_panels`` so this
page stays a thin orchestration layer.
"""

from __future__ import annotations

import importlib

import pandas as pd
import streamlit as st

st.set_page_config(page_title="TENG Performance", page_icon="🔋", layout="wide")

st.title("🔋 TENG Performance")

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

REQUIRED = ("WAVE_H_cm", "WAVE_T_ds")
missing = [c for c in REQUIRED if c not in df.columns]
if df.empty or missing:
    st.warning(
        "Phase 2 enrichment not yet available for this page. "
        f"Missing columns: {missing or '(no data at all)'}. "
        "Trigger the `enrichment_hourly` GitHub Action to populate "
        "wave columns, then reload."
    )
    st.stop()


# ──────────────────────────────────────────────────────────────────────
# KPI header
# ──────────────────────────────────────────────────────────────────────
try:
    panels = importlib.import_module("utils.p2.viz.teng_panels")
    kpis = panels.compute_kpis(df)
except Exception as exc:  # noqa: BLE001
    st.error(f"Failed to build TENG panels: {exc}")
    st.stop()

col1, col2, col3 = st.columns(3)
col1.metric("Harvested today", f"{kpis['today_joules']:.1f} J")
col2.metric("Session avg P_TENG", f"{kpis['avg_power_mw']:.2f} mW")
col3.metric("P_TENG / P_wave", f"{kpis['ratio_pct']:.2f} %")

st.divider()

# ──────────────────────────────────────────────────────────────────────
# A1 — Wave-to-power transfer function
# ──────────────────────────────────────────────────────────────────────
st.subheader("A1 — Wave-to-Power Transfer Function")
tab_hm, tab_loglog, tab_flux = st.tabs([
    "Hs × Tp heatmap",
    "Log-log P vs Hs²·Tp",
    "vs theoretical flux",
])

with tab_hm:
    st.plotly_chart(panels.build_hs_tp_heatmap(df), use_container_width=True)
    st.caption(
        f"Reference markers: Jung 2024 ({panels.JUNG_2024['P_mW']} mW, "
        f"blue star) and Lu 2026 ({panels.LU_2026['P_mW']} mW, red star)."
    )

with tab_loglog:
    st.plotly_chart(panels.build_loglog_hs2tp(df), use_container_width=True)
    st.caption("Slope of ~1 indicates P_TENG scales linearly with Hs²·Tp.")

with tab_flux:
    st.plotly_chart(panels.build_flux_scatter(df), use_container_width=True)
    st.caption("Theoretical flux from Falnes (2002) Eq. 6.19 with Te = 0.9·Tp.")

st.divider()

# ──────────────────────────────────────────────────────────────────────
# A4 — Normalized power trend
# ──────────────────────────────────────────────────────────────────────
st.subheader("A4 — Normalized Power Trend")
level = st.radio(
    "Normalization level",
    options=[0, 1, 2],
    format_func=lambda L: {0: "0 — raw mW", 1: "1 — / Hs²", 2: "2 — / (Hs²·Tp)"}[L],
    horizontal=True,
    index=2,
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
