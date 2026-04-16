"""
Page 10 — Data Enrichment admin / QC.

Shows enrichment coverage, source health, a (gated) manual backfill
trigger, and QC flags for the current data.
"""

from __future__ import annotations

import importlib
import json
import os
from datetime import date, timedelta

import numpy as np
import pandas as pd
import streamlit as st

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None  # type: ignore[assignment]

st.set_page_config(page_title="Data Enrichment", page_icon="📡", layout="wide")

from utils.theme import (  # noqa: E402
    render_header, render_footer, render_sidebar, inject_custom_css,
    PNNL_BLUE,
)

inject_custom_css()
render_sidebar()
render_header()

st.markdown(
    f'<h1 style="color:{PNNL_BLUE}; margin-top:0;">📡 Data Enrichment</h1>',
    unsafe_allow_html=True,
)

try:
    _flag = importlib.import_module("utils.p2.__phase2_flag")
    _flag.render_toggle_in_sidebar()
except Exception as exc:  # noqa: BLE001
    st.sidebar.caption(f"Phase 2 toggle unavailable: {exc}")


try:
    from utils.p2.schema import ENRICH_COLUMN_ORDER, EnrichFlag
    from utils.p2 import qc as qc_mod
except Exception as exc:  # noqa: BLE001
    st.error(f"Failed to load Phase 2 modules: {exc}")
    st.stop()


@st.cache_data(ttl=120)
def _load_data() -> pd.DataFrame:
    from utils.sheets_client import get_all_data
    try:
        return get_all_data()
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Could not load data: {exc}")
        return pd.DataFrame()


raw_df = _load_data()
if raw_df.empty:
    st.warning("No data available yet — enrichment panels have nothing to show.")
    st.stop()

# ── Shared device + date-range toolbar ────────────────────────────────
try:
    toolbar = importlib.import_module("utils.p2.ui_toolbar")
    df, selected_devices, time_col, dev_col = toolbar.render_device_time_filter(
        raw_df, key_prefix="p10",
    )
except Exception as exc:  # noqa: BLE001
    st.error(f"Toolbar unavailable: {exc}")
    st.stop()

if df.empty:
    st.info("Select at least one device with data in the chosen date range.")
    st.stop()

# ──────────────────────────────────────────────────────────────────────
# Main-area tabs
# ──────────────────────────────────────────────────────────────────────
tab_coverage, tab_health, tab_backfill, tab_qc = st.tabs([
    "Coverage",
    "Source Health",
    "Backfill",
    "QC Flags",
])


# ──────────────────────────────────────────────────────────────────────
# 1. Coverage heatmap
# ──────────────────────────────────────────────────────────────────────

try:
    import plotly.graph_objects as go
except Exception:  # pragma: no cover
    go = None  # type: ignore[assignment]


def _flag_matrix(df: pd.DataFrame) -> pd.DataFrame:
    if "ENRICH_FLAG" not in df.columns:
        return pd.DataFrame()
    ts = pd.to_datetime(df.get("Timestamp"), utc=True, errors="coerce")
    flag_int = pd.to_numeric(df["ENRICH_FLAG"], errors="coerce").fillna(0).astype(int)
    rows = []
    for ts_i, fv in zip(ts, flag_int):
        if pd.isna(ts_i):
            continue
        day = ts_i.date()
        for src in EnrichFlag:
            rows.append({"day": day, "source": src.name,
                         "hit": 1 if (fv & int(src)) else 0})
    if not rows:
        return pd.DataFrame()
    long = pd.DataFrame(rows)
    return long.pivot_table(index="source", columns="day", values="hit",
                            aggfunc="max", fill_value=0)


with tab_coverage:
    st.subheader("Coverage heatmap")
    matrix = _flag_matrix(df)
    if matrix.empty or go is None:
        st.info("No ENRICH_FLAG column available for the current selection.")
    else:
        fig = go.Figure(go.Heatmap(
            z=matrix.values,
            x=[str(c) for c in matrix.columns],
            y=list(matrix.index),
            colorscale=[[0, "#eeeeee"], [1, "#2ca02c"]],
            showscale=False,
            zmin=0, zmax=1,
        ))
        fig.update_layout(
            title="Per-source coverage by day",
            xaxis_title="Date", yaxis_title="Source",
        )
        st.plotly_chart(fig, use_container_width=True)


# ──────────────────────────────────────────────────────────────────────
# 2. Source health
# ──────────────────────────────────────────────────────────────────────
SOURCE_COLUMNS = {
    "WAVE (Open-Meteo)":        ["WAVE_H_cm", "WAVE_T_ds"],
    "WIND (Open-Meteo)":        ["WIND_SPD_cms", "WIND_DIR_deg"],
    "ERA5 atmospheric":         ["ERA5_PRES_dPa", "ERA5_AIRT_cC"],
    "Open-Meteo SST (coastal)": ["SAT_SST_OPENMETEO_cC"],
    "NOAA OISST":               ["SAT_SST_OISST_cC"],
    "MUR SST":                  ["SAT_SST_MUR_cC"],
    "OSTIA (Copernicus)":       ["SAT_SST_OSTIA_cC"],
    "OSCAR currents":           ["OSCAR_U_mms", "OSCAR_V_mms"],
    "OSI SAF sea ice":          ["SEAICE_CONC_pct"],
}

with tab_health:
    st.subheader("Source health")
    health_ts_col = time_col or "Timestamp"
    health_rows = []
    for name, cols in SOURCE_COLUMNS.items():
        present = [c for c in cols if c in df.columns]
        if not present:
            health_rows.append({"source": name, "last_ok": None,
                                "column(s)": ", ".join(cols), "status": "missing"})
            continue
        last_ok = None
        for c in present:
            mask = pd.to_numeric(df[c], errors="coerce").notna() & (df[c].astype(str) != "")
            if mask.any() and health_ts_col in df.columns:
                ts = pd.to_datetime(df.loc[mask, health_ts_col], utc=True, errors="coerce")
                ts = ts.dropna()
                if not ts.empty:
                    most_recent = ts.max()
                    if last_ok is None or most_recent > last_ok:
                        last_ok = most_recent
        health_rows.append({
            "source": name,
            "last_ok": last_ok,
            "column(s)": ", ".join(present),
            "status": "ok" if last_ok else "no data",
        })

    health_df = pd.DataFrame(health_rows)
    st.dataframe(health_df, use_container_width=True)


# ──────────────────────────────────────────────────────────────────────
# 3. Manual backfill trigger
# ──────────────────────────────────────────────────────────────────────
GH_REPO = "Denny-Hwang/spao-buoy-dashboard"
WORKFLOW_FILE = "enrichment_daily.yml"


def _get_dispatch_token() -> str | None:
    # 1) Streamlit secrets (preferred in Streamlit Cloud)
    try:
        tok = st.secrets.get("GH_DISPATCH_TOKEN")  # type: ignore[attr-defined]
        if tok:
            return str(tok).strip()
    except Exception:
        pass
    # 2) Environment variable fallback (local/dev/self-hosted)
    tok_env = os.environ.get("GH_DISPATCH_TOKEN", "").strip()
    return tok_env or None


with tab_backfill:
    st.subheader("Manual backfill trigger")

    today = date.today()
    col1, col2, col3 = st.columns([2, 2, 3])
    with col1:
        start = st.date_input(
            "Start date",
            value=today - timedelta(days=7),
            key="p10_backfill_start",
        )
    with col2:
        end = st.date_input("End date", value=today, key="p10_backfill_end")
    with col3:
        source_choices = list(SOURCE_COLUMNS.keys())
        selected_sources = st.multiselect(
            "Sources",
            options=source_choices,
            default=source_choices,
            key="p10_backfill_sources",
        )

    gh_token = _get_dispatch_token()

    if not gh_token:
        st.info(
            "Manual trigger disabled — add a Streamlit secret "
            "`GH_DISPATCH_TOKEN` (fine-grained PAT with Actions: Write, "
            f"scoped to `{GH_REPO}`) to enable the button below. "
            "You can also set environment variable `GH_DISPATCH_TOKEN`. See "
            "[README → GH_DISPATCH_TOKEN](../README.md#gh_dispatch_token) "
            "for setup steps."
        )
        st.button("Trigger backfill", disabled=True, key="p10_backfill_disabled")
    else:
        trigger = st.button("Trigger backfill", type="primary", key="p10_backfill_go")
        if trigger:
            if requests is None:
                st.error("requests library not installed in this runtime.")
            else:
                url = (
                    f"https://api.github.com/repos/{GH_REPO}"
                    f"/actions/workflows/{WORKFLOW_FILE}/dispatches"
                )
                payload = {
                    "ref": "main",
                    "inputs": {
                        "start_date": str(start),
                        "end_date": str(end),
                        "dry_run": "false",
                    },
                }
                try:
                    resp = requests.post(
                        url,
                        headers={
                            "Authorization": f"Bearer {gh_token}",
                            "Accept": "application/vnd.github+json",
                        },
                        data=json.dumps(payload),
                        timeout=15,
                    )
                    if resp.status_code in (200, 204):
                        st.success("✅ Workflow dispatched.")
                    else:
                        st.error(
                            f"GitHub API returned {resp.status_code}: {resp.text[:200]}"
                        )
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Dispatch failed: {exc}")

    if selected_sources and (start > end):
        st.warning("Start date must be on or before end date.")


# ──────────────────────────────────────────────────────────────────────
# 4. QC flags panel
# ──────────────────────────────────────────────────────────────────────
with tab_qc:
    st.subheader("QC flags")

    summary = qc_mod.qc_summary(df)
    st.dataframe(
        summary.style.format({"pct": "{:.2f}%"}),
        use_container_width=True,
    )

    with st.expander("Thresholds"):
        st.markdown(
            f"""
            | Check | Threshold |
            |---|---|
            | `sst_vs_oisst_gt3` | `|SST_buoy − OISST|` > **{qc_mod.SST_DELTA_LIMIT_C} °C** |
            | `wave_h_gt15`      | Hs > **{qc_mod.WAVE_H_LIMIT_M} m** |
            | `wind_gt50`        | U10 > **{qc_mod.WIND_LIMIT_MPS} m/s** |
            | `gps_speed_gt10kmh` | GPS-derived speed > **{qc_mod.GPS_SPEED_LIMIT_KMH} km/h** |
            """
        )

    if summary["n_flagged"].sum() > 0:
        st.caption("Individual flagged rows (first 50):")
        flags = qc_mod.qc_flags_matrix(df)
        offenders = flags[flags.any(axis=1)].head(50)
        if not offenders.empty:
            st.dataframe(offenders, use_container_width=True)

render_footer()
