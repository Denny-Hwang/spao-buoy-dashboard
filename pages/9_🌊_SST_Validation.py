"""
Page 9 — SST Validation.

The page now mirrors the Phase 1 Analytics layout:

    [ Shared toolbar: device + date range ]
    ── Tabs ──────────────────────────────────────────
        📋 Data Explorer       (Archive-style table; enriched columns
                                gated on the sidebar p2_show_enriched
                                toggle)
        📈 Sensor Overview     (Phase 1 sensor plots + 7 Phase 2
                                enriched-column groups)
        B1 Intercomparison
        B2 Drift Detection
        B3 Diurnal Warming
        Long-term Bias         (Derived_Daily worksheet)

Operators can now visually inspect the enriched raw values and sensor
time-series before running the intercomparison / drift / diurnal
analyses, which previously only surfaced summary statistics.
"""

from __future__ import annotations

import importlib
import os
from io import BytesIO

import pandas as pd
import streamlit as st

st.set_page_config(page_title="SST Validation", page_icon="🌊", layout="wide")

from utils.theme import (  # noqa: E402
    render_header, render_footer, render_sidebar, inject_custom_css,
    render_kpi_card, PNNL_BLUE,
)

inject_custom_css()
render_sidebar()
render_header()

st.markdown(
    f'<h1 style="color:{PNNL_BLUE}; margin-top:0;">🌊 SST Validation</h1>',
    unsafe_allow_html=True,
)

try:
    _flag = importlib.import_module("utils.p2.__phase2_flag")
    _flag.render_toggle_in_sidebar()
except Exception as exc:  # noqa: BLE001
    st.sidebar.caption(f"Phase 2 toggle unavailable: {exc}")


@st.cache_data(ttl=120)
def _load_data() -> pd.DataFrame:
    from utils.sheets_client import get_all_data
    try:
        return get_all_data()
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Could not load data: {exc}")
        return pd.DataFrame()


raw_df = _load_data()

try:
    panels = importlib.import_module("utils.p2.viz.sst_panels")
    # Force reload so new attributes added in later deploys (DESCRIPTIONS,
    # PRODUCT_INFO, build_pairwise_bias_bar, …) are always picked up even
    # if Streamlit Cloud has cached an older module object.
    panels = importlib.reload(panels)
except Exception as exc:  # noqa: BLE001
    panels = None
    st.error(f"Failed to load SST panels: {exc}")

try:
    sensor_overview = importlib.import_module("utils.p2.viz.sensor_overview")
    sensor_overview = importlib.reload(sensor_overview)
except Exception as exc:  # noqa: BLE001
    sensor_overview = None
    st.caption(f"Sensor overview unavailable: {exc}")

# Defensive: older cached module versions did not expose DESCRIPTIONS /
# PRODUCT_INFO / build_pairwise_bias_bar. Resolve them via getattr with
# graceful fallbacks so a stale module never crashes the page.
_DESC: dict = getattr(panels, "DESCRIPTIONS", {}) or {}
_PRODUCT_INFO: dict = getattr(panels, "PRODUCT_INFO", {}) or {}


def _build_pairwise_bias_bar_safe(frame):
    fn = getattr(panels, "build_pairwise_bias_bar", None)
    if fn is None:
        return None
    try:
        return fn(frame)
    except Exception:  # noqa: BLE001
        return None

# ── Shared device + date-range toolbar ────────────────────────────────
try:
    toolbar = importlib.import_module("utils.p2.ui_toolbar")
    df, selected_devices, time_col, dev_col = toolbar.render_device_time_filter(
        raw_df, key_prefix="p8",
    )
except Exception as exc:  # noqa: BLE001
    st.error(f"Toolbar unavailable: {exc}")
    st.stop()

# ──────────────────────────────────────────────────────────────────────
# Data availability probe — controls which tabs can do meaningful work.
# ──────────────────────────────────────────────────────────────────────
buoy = panels.extract_buoy_sst(df) if (panels and not df.empty) else None
products = panels.extract_products(df) if (panels and not df.empty) else {}
per_row_ready = panels is not None and buoy is not None and bool(products)

# ──────────────────────────────────────────────────────────────────────
# Main-area tabs
# ──────────────────────────────────────────────────────────────────────
tab_explorer, tab_overview, tab_b1, tab_b2, tab_b3, tab_long = st.tabs([
    "📋 Data Explorer",
    "📈 Sensor Overview",
    "B1 — Intercomparison",
    "B2 — Drift Detection",
    "B3 — Diurnal Warming",
    "Long-term Bias",
])

# ── Data Explorer ─────────────────────────────────────────────────────
with tab_explorer:
    st.subheader("📋 Data Explorer")
    if df.empty:
        st.info("No data in the selected range.")
    else:
        # Gate enriched columns on the sidebar Phase 2 toggle.
        show_enriched = bool(st.session_state.get("p2_show_enriched", False))
        try:
            from utils.p2.schema import ENRICH_COLUMN_ORDER
        except Exception:
            ENRICH_COLUMN_ORDER = []  # type: ignore[assignment]

        try:
            from utils.sheets_client import reorder_columns
            display_df = reorder_columns(df)
        except Exception:
            display_df = df.copy()

        if not show_enriched:
            drop_cols = [c for c in ENRICH_COLUMN_ORDER if c in display_df.columns]
            display_df = display_df.drop(columns=drop_cols)
            st.caption(
                "Phase 2 enriched columns hidden. Toggle **Show Phase 2 "
                "enriched columns** in the sidebar to include SAT_SST_*, "
                "WAVE_*, WIND_*, ERA5_*, OSCAR_*, SEAICE_*, and "
                "ENRICH_FLAG in the table."
            )
        else:
            present_enriched = [c for c in ENRICH_COLUMN_ORDER if c in display_df.columns]
            st.caption(
                f"Phase 2 enriched columns shown: {len(present_enriched)} of "
                f"{len(ENRICH_COLUMN_ORDER)} ({', '.join(present_enriched) or 'none populated'})."
            )

        # Summary KPIs
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            render_kpi_card("Records", f"{len(display_df):,}")
        if time_col and time_col in display_df.columns:
            ts = pd.to_datetime(display_df[time_col], errors="coerce").dropna()
            if not ts.empty:
                with k2:
                    render_kpi_card(
                        "Date Range",
                        f"{ts.min().strftime('%Y-%m-%d')} → {ts.max().strftime('%Y-%m-%d')}",
                    )
        if buoy is not None:
            b = buoy.dropna()
            if not b.empty:
                with k3:
                    render_kpi_card(
                        "Buoy SST",
                        f"{b.min():.2f} / {b.max():.2f} °C",
                    )
        if products:
            total_rows = max(len(df), 1)
            cov = sum(v.notna().any() for v in products.values())
            with k4:
                render_kpi_card(
                    "SAT products",
                    f"{cov} of {len(products)} populated",
                )

        st.dataframe(display_df, width="stretch", height=440, hide_index=True)

        csv_buf = BytesIO()
        display_df.to_csv(csv_buf, index=False)
        st.download_button(
            "Export CSV",
            data=csv_buf.getvalue(),
            file_name="sst_validation_data.csv",
            mime="text/csv",
            key="p8_export_csv",
        )

# ── Sensor Overview ───────────────────────────────────────────────────
with tab_overview:
    st.subheader("📈 Sensor Overview")
    if sensor_overview is None:
        st.warning("Sensor overview module failed to load.")
    elif df.empty or not time_col:
        st.info("Select a non-empty device / date range to see plots.")
    else:
        hide_ec = st.checkbox(
            "Hide EC Conductivity & Salinity (sensor not mounted)",
            value=True,
            key="p8_hide_ec_salinity",
            help="Phase 1 convention — toggle off to force-render the unused "
                 "EC / Salinity channels.",
        )

        st.markdown(
            f"<h4 style='color:{PNNL_BLUE}; margin-top:8px;'>Phase 1 buoy telemetry</h4>",
            unsafe_allow_html=True,
        )
        phase1_figs = sensor_overview.build_phase1_sensor_figures(
            df, time_col, dev_col, hide_ec_salinity=hide_ec,
        )
        if not phase1_figs:
            st.caption("No Phase 1 sensor columns found for the current selection.")
        for _title, fig in phase1_figs:
            st.plotly_chart(fig, use_container_width=True)

        st.markdown(
            f"<h4 style='color:{PNNL_BLUE}; margin-top:8px;'>Phase 2 enriched groups</h4>",
            unsafe_allow_html=True,
        )

        # Per-group controls — surfaced as three compact columns so the
        # user can flip dual-axis on/off, pick which series lands on y2
        # and (for the SST product group only) toggle the buoy / air
        # overlays without opening a nested expander.
        _dual_groups = getattr(sensor_overview, "list_dual_axis_groups", lambda: [])()
        _y2_overrides: dict[str, list[str]] = {}
        _dual_enabled: dict[str, bool] = {}
        if _dual_groups:
            with st.expander("⚙️  Dual y-axis configuration", expanded=False):
                st.caption(
                    "Per-group dual-axis toggle. Disable to collapse both "
                    "series onto a single y-axis; enable to pick which "
                    "variable(s) plot on the RIGHT-hand axis."
                )
                for _g in _dual_groups:
                    _key = _g.get("key")
                    _opts = [s[0] for s in _g["series"]]
                    _label_by_col = {s[0]: f"{s[1]} — {s[0]}" for s in _g["series"]}
                    _default_y2 = [s[0] for s in _g["series"]
                                   if (len(s) >= 5 and s[4] == "y2")]
                    c_tog, c_sel = st.columns([1, 3])
                    with c_tog:
                        _on = st.toggle(
                            "Dual Y",
                            value=True,
                            key=f"p8_dual_axis_{_key}",
                            help=f"Toggle the right-hand axis for '{_g['title']}'.",
                        )
                    with c_sel:
                        _sel = st.multiselect(
                            _g["title"],
                            options=_opts,
                            default=_default_y2,
                            format_func=lambda c, m=_label_by_col: m.get(c, c),
                            key=f"p8_y2_override_{_key}",
                            disabled=not _on,
                            help="Columns to plot on the RIGHT-hand y-axis when dual mode is on.",
                        )
                    _dual_enabled[_key] = bool(_on)
                    _y2_overrides[_key] = _sel

        c_buoy, c_air, _spacer = st.columns([1, 1, 2])
        with c_buoy:
            _overlay_buoy = st.toggle(
                "Overlay buoy SST",
                value=True,
                key="p8_overlay_buoy",
                help=(
                    "Render the buoy external SST sensor as a highlighted "
                    "trace on the SST-products chart so you can anchor the "
                    "satellite / reanalysis products against the point truth."
                ),
            )
        with c_air:
            _overlay_air = st.toggle(
                "Overlay land / air temp",
                value=False,
                key="p8_overlay_air",
                help=(
                    "Overlay ERA5 2 m air temperature on the SST-products "
                    "chart. Useful for inland / coastal deployments where "
                    "the satellite SST products are land-masked."
                ),
            )

        enriched_results = sensor_overview.build_enriched_group_figures(
            df, time_col, dev_col,
            y2_overrides=_y2_overrides,
            dual_axis_enabled=_dual_enabled,
            overlay_buoy_sst=_overlay_buoy,
            overlay_air_temp=_overlay_air,
        )
        if not enriched_results:
            st.caption("No enriched columns available — run the enrichment workflows.")
        for title, fig, reason in enriched_results:
            if fig is None:
                st.caption(f"*{title}* — skipped ({reason}).")
            else:
                st.plotly_chart(fig, use_container_width=True)

# ── B1 / B2 / B3 analyses ─────────────────────────────────────────────
_b_warning = (
    "SST validation needs both a buoy-measured SST column and at "
    "least one enriched satellite column (SAT_SST_OISST_cC, "
    "SAT_SST_MUR_cC, SAT_SST_OSTIA_cC, or SAT_SST_ERA5_cC). "
    "Trigger the `enrichment_daily` GitHub Action and reload."
)

with tab_b1:
    st.subheader("B1 — Intercomparison")
    st.markdown(
        "Compare the buoy's **external SST** thermistor against every enriched "
        "reference product (satellite and reanalysis) to catch biases, drift, "
        "and coverage gaps. The buoy is treated as the point-truth; each "
        "product is the candidate reference."
    )

    with st.expander("ℹ️  What does each SST product mean? (source · resolution · known bias)"):
        if not _PRODUCT_INFO:
            st.caption(
                "Product info not available in the currently loaded module "
                "build. See the 📖 Phase 2 Overview page for the full product "
                "reference."
            )
        else:
            for name, info in _PRODUCT_INFO.items():
                st.markdown(
                    f"**{name}** — *{info.get('source', '')}*  \n"
                    f"&nbsp;&nbsp;&nbsp;• Access: {info.get('access', '—')}  \n"
                    f"&nbsp;&nbsp;&nbsp;• Resolution: {info.get('resolution', '—')}  \n"
                    f"&nbsp;&nbsp;&nbsp;• Known bias: {info.get('bias', '—')}"
                )

    tog_col1, tog_col2 = st.columns(2)
    with tog_col1:
        show_internal = st.checkbox(
            "Overlay buoy internal temperature (hull thermistor)",
            value=False,
            key="p8_show_internal_temp",
            help=(
                "Internal temperature is NOT a water-SST measurement — it "
                "lives inside the sealed hull. Toggle on to visualize thermal "
                "lag between the water and the electronics bay."
            ),
        )
    with tog_col2:
        show_land_air = st.checkbox(
            "Overlay land / air temperature (ERA5 2 m)",
            value=False,
            key="p8_show_land_air_temp",
            help=(
                "ERA5 2-m air temperature at the buoy location — populated "
                "EVERYWHERE including inland deployments. Use this when the "
                "buoy is on land / in rivers (Richland test) and the "
                "satellite SST products are all masked, so you still have a "
                "'land-weather' reference to compare the buoy against."
            ),
        )

    if not per_row_ready:
        st.warning(_b_warning)
    else:
        st.markdown(f"*{_DESC.get('metrics_table', '')}*")
        metrics = panels.build_metrics_table(df)
        st.dataframe(metrics.style.format({
            "bias": "{:+.3f}", "rmse": "{:.3f}", "uRMSE": "{:.3f}",
            "std_diff": "{:+.3f}", "correlation": "{:.3f}",
        }), use_container_width=True)

        _bias_fig = _build_pairwise_bias_bar_safe(df)
        if _bias_fig is not None:
            st.markdown(f"*{_DESC.get('pairwise_bias', '')}*")
            st.plotly_chart(_bias_fig, use_container_width=True)

        col_left, col_right = st.columns(2)
        with col_left:
            st.markdown(f"*{_DESC.get('taylor', '')}*")
            st.plotly_chart(panels.build_taylor(df), use_container_width=True)
        with col_right:
            st.markdown(f"*{_DESC.get('target', '')}*")
            st.plotly_chart(panels.build_target(df), use_container_width=True)

        st.markdown(f"*{_DESC.get('timeseries', '')}*")
        st.plotly_chart(
            panels.build_sst_timeseries(
                df,
                include_internal_temp=show_internal,
                include_land_air_temp=show_land_air,
            ),
            use_container_width=True,
        )

        # Hull vs ERA5-air diagnostic — only render when both overlays
        # are toggled on, so the user actively asked to compare them.
        # Surfaces correlation + sample count so timezone / unit bugs
        # are flagged numerically instead of having to be eyeballed.
        if show_internal and show_land_air:
            _diag_fn = getattr(panels, "build_internal_vs_air_diagnostic", None)
            if _diag_fn is not None:
                _diag = _diag_fn(df)
                _stats = _diag.get("stats", {}) or {}
                st.markdown(f"*{_DESC.get('internal_vs_air_diag', '')}*")
                st.plotly_chart(_diag["fig"], use_container_width=True)
                _n = int(_stats.get("n", 0) or 0)
                _corr = _stats.get("correlation", float("nan"))
                _delta = _stats.get("mean_delta", float("nan"))
                _hours = _stats.get("ts_overlap_hours", float("nan"))
                if _n > 0 and pd.notna(_corr):
                    if _corr < 0:
                        st.error(
                            f"⚠️  Hull and air temperatures are NEGATIVELY "
                            f"correlated (r = {_corr:+.3f}, N = {_n}, "
                            f"Δ_mean = {_delta:+.2f} °C, span = {_hours:.0f} h). "
                            "Inspect timestamp alignment, units, and the "
                            "decoder for the Internal Temp field."
                        )
                    elif _corr < 0.2:
                        st.warning(
                            f"Weak hull–air correlation (r = {_corr:+.3f}, "
                            f"N = {_n}). Trends may be obscured by hull "
                            "greenhouse warming or sample sparsity."
                        )
                    else:
                        st.success(
                            f"Hull and air temperatures are positively "
                            f"correlated (r = {_corr:+.3f}, N = {_n}, "
                            f"Δ_mean = {_delta:+.2f} °C). Streams are "
                            "aligned in time and units."
                        )
                else:
                    st.info(
                        "Diagnostic produced no overlapping samples — at "
                        "least one of the two streams is empty for the "
                        "current selection."
                    )

        st.markdown(f"*{_DESC.get('residual_hist', '')}*")
        st.plotly_chart(panels.build_residual_histogram(df), use_container_width=True)

with tab_b2:
    st.subheader("B2 — Drift Detection")
    st.markdown(
        "Track the **buoy − reference** residual over time; a non-zero slope "
        "here means the buoy thermistor is slowly drifting relative to a "
        "(trusted) reference. OISST is the default reference because it "
        "fuses in-situ + AVHRR data and has the longest continuous record."
    )
    if not per_row_ready:
        st.warning(_b_warning)
    else:
        st.markdown(f"*{_DESC.get('drift_ts', '')}*")
        drift = panels.build_drift_timeseries(df)
        st.plotly_chart(drift["fig"], use_container_width=True)

        col1, col2 = st.columns(2)
        col1.metric("Drift slope", f"{drift['slope_per_week']:+.4f} °C/week")
        if drift["alarm"]:
            col2.error("🔴 Drift alarm — |slope| > 0.01 °C/week")
        else:
            col2.success("🟢 No drift alarm")

        st.markdown(f"*{_DESC.get('drift_box', '')}*")
        st.plotly_chart(panels.build_drift_boxplot(df), use_container_width=True)
        st.markdown(f"*{_DESC.get('cusum', '')}*")
        st.plotly_chart(panels.build_cusum_chart(df), use_container_width=True)

with tab_b3:
    st.subheader("B3 — Diurnal Warming")
    st.markdown(
        "Bulk satellite products resolve daily or foundation-SST; the buoy "
        "samples often enough to see the diurnal cycle. Large daily amplitudes "
        "at low wind indicate strong skin warming the references can't see."
    )
    if not per_row_ready:
        st.warning(_b_warning)
    else:
        clear_sky = st.checkbox(
            "Clear-sky filter (requires ERA5 cloud_cover column)",
            value=False,
            key="p8_clear_sky",
            help="If ERA5 cloud_cover is not in the enriched schema, the toggle has no effect.",
        )
        b3_col1, b3_col2 = st.columns(2)
        with b3_col1:
            b3_internal = st.checkbox(
                "Overlay buoy internal temperature (hull thermistor)",
                value=False,
                key="p8_b3_internal_temp",
                help="Compare water-SST diurnal cycle vs the electronics-bay thermal response.",
            )
        with b3_col2:
            b3_land_air = st.checkbox(
                "Overlay land / air temperature (ERA5 2 m)",
                value=False,
                key="p8_b3_land_air_temp",
                help="ERA5 2 m air temperature context, populated everywhere including inland buoys.",
            )
        df_view = df
        if clear_sky and "ERA5_CLOUD_COVER" in df.columns:
            df_view = df[df["ERA5_CLOUD_COVER"] < 30]

        st.markdown(f"*{_DESC.get('diurnal', '')}*")
        st.plotly_chart(
            panels.build_diurnal_composite(
                df_view,
                include_internal_temp=b3_internal,
                include_land_air_temp=b3_land_air,
            ),
            use_container_width=True,
        )
        st.markdown(f"*{_DESC.get('amplitude_vs_wind', '')}*")
        st.plotly_chart(panels.build_amplitude_vs_wind(df_view), use_container_width=True)
        st.caption("Kawai & Wada (2007) overlay is a qualitative envelope.")

# ──────────────────────────────────────────────────────────────────────
# Long-term bias trend (Derived_Daily) — always runs.
# ──────────────────────────────────────────────────────────────────────


@st.cache_data(ttl=300)
def _load_derived_daily() -> pd.DataFrame:
    try:
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
    st.subheader("30-day bias trend (Derived_Daily)")
    daily_df = _load_derived_daily()
    if daily_df.empty:
        st.info(
            "Derived_Daily worksheet not yet populated. "
            "Run the `derived_daily` GitHub Action (or "
            "`python scripts/compute_daily_derived.py`) to generate the "
            "daily-aggregation table, then reload this page."
        )
    else:
        try:
            trend_panels = importlib.import_module("utils.p2.viz.trend_panels")
            st.plotly_chart(
                trend_panels.build_sst_bias_trend(daily_df, window_days=30),
                use_container_width=True,
            )
            latest = daily_df.tail(7)
            if not latest.empty:
                st.caption("Last 7 rows from Derived_Daily")
                st.dataframe(latest, use_container_width=True)
        except Exception as exc:  # noqa: BLE001
            st.caption(f"Bias trend rendering failed: {exc}")

render_footer()
