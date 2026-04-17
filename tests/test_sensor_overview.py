"""Unit tests for utils.p2.viz.sensor_overview."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tests.test_p2_skeleton import _install_stub_modules

_install_stub_modules()

plotly = pytest.importorskip("plotly.graph_objects")

from utils.p2.viz import sensor_overview  # noqa: E402


def _make_frame(n: int = 24) -> pd.DataFrame:
    times = pd.date_range("2026-04-01", periods=n, freq="h", tz=None)
    rng = np.random.default_rng(0)
    return pd.DataFrame({
        "Timestamp": times,
        "Device Tab": ["Buoy-A"] * n,
        "Battery Voltage": rng.uniform(3.2, 3.4, n),
        "SST": rng.uniform(8.0, 12.0, n),
        "Pressure": rng.uniform(12.0, 16.0, n),
        "Internal Temp": rng.uniform(5.0, 15.0, n),
        "Humidity": rng.uniform(40, 80, n),
        "WAVE_H_cm":        rng.integers(50, 300, n).astype("int64"),
        "WAVE_T_ds":        rng.integers(40, 120, n).astype("int64"),
        "WAVE_DIR_deg":     rng.integers(0, 360, n).astype("int64"),
        "SWELL_H_cm":       rng.integers(50, 200, n).astype("int64"),
        "SWELL_T_ds":       rng.integers(50, 140, n).astype("int64"),
        "WIND_SPD_cms":     rng.integers(100, 1500, n).astype("int64"),
        "WIND_DIR_deg":     rng.integers(0, 360, n).astype("int64"),
        "ERA5_PRES_dPa":    rng.integers(9800, 10300, n).astype("int64"),
        "ERA5_AIRT_cC":     rng.integers(-500, 1500, n).astype("int64"),
        "SAT_SST_OISST_cC": rng.integers(800, 1300, n).astype("int64"),
        "SAT_SST_MUR_cC":   rng.integers(800, 1300, n).astype("int64"),
        "SAT_SST_OSTIA_cC": rng.integers(800, 1300, n).astype("int64"),
        "SAT_SST_ERA5_cC":  rng.integers(800, 1300, n).astype("int64"),
        "OSCAR_U_mms":      rng.integers(-500, 500, n).astype("int64"),
        "OSCAR_V_mms":      rng.integers(-500, 500, n).astype("int64"),
        "SEAICE_CONC_pct":  rng.integers(0, 100, n).astype("int64"),
        "ENRICH_FLAG":      rng.integers(0, 128, n).astype("int64"),
    })


def test_phase1_sensor_figures_built_for_all_keywords() -> None:
    df = _make_frame()
    figs = sensor_overview.build_phase1_sensor_figures(
        df, "Timestamp", "Device Tab", hide_ec_salinity=True,
    )
    titles = [t for t, _ in figs]
    # Core Phase 1 sensors present in the frame should all render.
    for expected in ("Battery", "SST (buoy)", "Pressure", "Internal Temp", "Humidity"):
        assert expected in titles
    # EC / Salinity must be hidden when hide_ec_salinity=True.
    assert "EC Conductivity" not in titles
    assert "Salinity" not in titles


def test_phase1_sensor_figures_skip_empty_columns() -> None:
    df = _make_frame()
    df["Battery Voltage"] = np.nan
    figs = sensor_overview.build_phase1_sensor_figures(
        df, "Timestamp", "Device Tab",
    )
    titles = [t for t, _ in figs]
    assert "Battery" not in titles


def test_enriched_groups_all_render_when_data_present() -> None:
    df = _make_frame()
    results = sensor_overview.build_enriched_group_figures(
        df, "Timestamp", "Device Tab",
    )
    # Every group should produce a figure (non-None) for the synthetic data.
    titles = [t for t, _fig, _reason in results]
    figs = [fig for _t, fig, _r in results]
    assert len(titles) == len(sensor_overview.ENRICHED_GROUPS)
    assert all(f is not None for f in figs), \
        f"Some groups skipped: {[(t,r) for t,f,r in results if f is None]}"


def test_enriched_group_skipped_with_reason_when_all_nan() -> None:
    df = _make_frame()
    for c in ("SAT_SST_OISST_cC", "SAT_SST_MUR_cC", "SAT_SST_OSTIA_cC",
              "SAT_SST_ERA5_cC", "SST"):
        df[c] = pd.NA
    results = sensor_overview.build_enriched_group_figures(
        df, "Timestamp", "Device Tab",
    )
    sst_entry = [r for r in results if "Sea surface temperature" in r[0]]
    assert sst_entry, "SST group missing from output"
    title, fig, reason = sst_entry[0]
    assert fig is None
    assert reason is not None and "NaN" in reason or "columns" in reason or "plottable" in reason


def test_sst_group_includes_buoy_overlay_trace() -> None:
    df = _make_frame()
    results = sensor_overview.build_enriched_group_figures(
        df, "Timestamp", "Device Tab",
    )
    sst_entry = [r for r in results if "Sea surface temperature" in r[0]]
    title, fig, reason = sst_entry[0]
    assert fig is not None
    trace_names = [t.name for t in fig.data]
    # Four products + buoy overlay.
    assert any("Buoy" in n for n in trace_names)
    assert any("OISST" in n for n in trace_names)
    assert any("MUR" in n for n in trace_names)


def test_empty_time_col_returns_empty_lists() -> None:
    df = _make_frame().drop(columns=["Timestamp"])
    assert sensor_overview.build_phase1_sensor_figures(df, "Timestamp", "Device Tab") == []
    assert sensor_overview.build_enriched_group_figures(df, "Timestamp", "Device Tab") == []


# ---------- Dual-y axis compliance ----------------------------------

def _fig_for_group_key(results, key_substring: str):
    for title, fig, _reason in results:
        if key_substring.lower() in title.lower():
            return fig
    raise AssertionError(f"no group matching {key_substring!r} in results")


def test_wind_group_uses_dual_y_axis_separating_speed_and_direction() -> None:
    """The original bug: Wind plot flattened the speed series because
    direction (0-360) dominated a single axis. Verify the rebuilt
    figure explicitly puts speed on y1 and direction on y2."""
    df = _make_frame()
    results = sensor_overview.build_enriched_group_figures(
        df, "Timestamp", "Device Tab",
    )
    fig = _fig_for_group_key(results, "Wind (10 m")
    assert fig is not None

    layout = fig.layout
    # yaxis2 must exist with overlaying="y" and side="right".
    assert layout.yaxis2 is not None
    assert layout.yaxis2.overlaying == "y"
    assert layout.yaxis2.side == "right"

    # Trace axis assignments: speed on y1, direction on y2.
    speed_traces = [t for t in fig.data if "speed" in str(t.name).lower()]
    dir_traces = [t for t in fig.data if "direction" in str(t.name).lower()]
    assert speed_traces and dir_traces
    assert all((t.yaxis or "y") == "y" for t in speed_traces)
    assert all(t.yaxis == "y2" for t in dir_traces)


def test_atmos_group_dual_y_with_pressure_and_air_temp() -> None:
    df = _make_frame()
    results = sensor_overview.build_enriched_group_figures(
        df, "Timestamp", "Device Tab",
    )
    fig = _fig_for_group_key(results, "Atmosphere")
    assert fig is not None
    assert fig.layout.yaxis2 is not None
    pres_traces = [t for t in fig.data if "pressure" in str(t.name).lower()]
    air_traces = [t for t in fig.data if "air temp" in str(t.name).lower()]
    assert pres_traces and air_traces
    assert all((t.yaxis or "y") == "y" for t in pres_traces)
    assert all(t.yaxis == "y2" for t in air_traces)


def test_wave_period_group_puts_direction_on_secondary_axis() -> None:
    df = _make_frame()
    results = sensor_overview.build_enriched_group_figures(
        df, "Timestamp", "Device Tab",
    )
    fig = _fig_for_group_key(results, "Wave period")
    assert fig is not None
    assert fig.layout.yaxis2 is not None
    # Tp / Tswell (seconds) on y1, Wave dir (degrees) on y2.
    dir_traces = [t for t in fig.data if "wave dir" in str(t.name).lower()]
    tp_traces = [t for t in fig.data if "tp" in str(t.name).lower() and "tswell" not in str(t.name).lower()]
    assert dir_traces and tp_traces
    assert all(t.yaxis == "y2" for t in dir_traces)
    assert all((t.yaxis or "y") == "y" for t in tp_traces)


def test_sst_products_group_collapses_to_single_axis() -> None:
    """SST products share a unit (°C) so the builder now auto-collapses
    to a single y-axis instead of splitting across y1 / y2 — the
    values are directly comparable and a second axis would just be
    visual noise. Overrides the previous dual-y requirement at user
    request (see Phase 2 figure-layout improvements)."""
    df = _make_frame()
    results = sensor_overview.build_enriched_group_figures(
        df, "Timestamp", "Device Tab",
    )
    fig = _fig_for_group_key(results, "Sea surface temperature")
    assert fig is not None
    # All SST-product traces should be on the primary axis; no yaxis2
    # overlay should be configured.
    for t in fig.data:
        assert (t.yaxis or "y") == "y"
    try:
        overlaying = fig.layout.yaxis2.overlaying
    except (AttributeError, KeyError):
        overlaying = None
    assert overlaying is None


def test_list_dual_axis_groups_excludes_same_unit_groups() -> None:
    """`list_dual_axis_groups` should return only groups where the
    series have mixed units, so the Page 9 per-group y2 selector does
    not offer pointless controls for all-°C / all-m/s groups."""
    duals = sensor_overview.list_dual_axis_groups()
    titles = [g["title"] for g in duals]
    # SST products (all °C) and Ocean currents (all m/s) have shared
    # units — must be excluded.
    assert not any("surface temperature" in t.lower() for t in titles)
    assert not any("ocean surface currents" in t.lower() for t in titles)
    # Wind (m/s + deg) and Atmosphere (Pa + °C) have mixed units —
    # must be included.
    assert any("wind" in t.lower() for t in titles)
    assert any("atmosphere" in t.lower() for t in titles)


def test_y2_override_routes_columns_to_requested_axis() -> None:
    """Passing an override dict should force named columns onto y2 and
    leave everything else on y1, regardless of the group's default."""
    df = _make_frame()
    # Wind group defaults: WIND_SPD_cms -> y, WIND_DIR_deg -> y2.
    # Flip the override so SPD lands on y2 and DIR stays on y1.
    results = sensor_overview.build_enriched_group_figures(
        df, "Timestamp", "Device Tab",
        y2_overrides={"wind": ["WIND_SPD_cms"]},
    )
    fig = _fig_for_group_key(results, "Wind")
    assert fig is not None
    axis_by_name = {t.name: (t.yaxis or "y") for t in fig.data}
    # Traces are named "<label>" or "<label> — <device>"; check prefix.
    for name, axis in axis_by_name.items():
        if name.startswith("Wind speed"):
            assert axis == "y2"
        if name.startswith("Wind direction"):
            assert axis == "y"


def test_single_series_group_has_no_secondary_axis() -> None:
    df = _make_frame()
    results = sensor_overview.build_enriched_group_figures(
        df, "Timestamp", "Device Tab",
    )
    fig = _fig_for_group_key(results, "Sea-ice concentration")
    assert fig is not None
    # Single series → yaxis2 not configured (plotly omits the attr
    # entirely when it hasn't been set). Use a tolerant check.
    try:
        overlaying = fig.layout.yaxis2.overlaying
    except (AttributeError, KeyError):
        overlaying = None
    assert overlaying is None
    # And all traces land on the primary axis.
    for t in fig.data:
        assert (t.yaxis or "y") == "y"


# ---------- Per-group dual-axis toggle ------------------------------

def test_dual_axis_disabled_collapses_wind_to_single_axis() -> None:
    """Passing ``dual_axis_enabled={'wind': False}`` must collapse the
    Wind group's two series back onto y1 — the same code path as
    same-unit groups — even though the group's defaults split them."""
    df = _make_frame()
    results = sensor_overview.build_enriched_group_figures(
        df, "Timestamp", "Device Tab",
        dual_axis_enabled={"wind": False},
    )
    fig = _fig_for_group_key(results, "Wind")
    assert fig is not None
    # Every trace should be on y1.
    for t in fig.data:
        assert (t.yaxis or "y") == "y"


def test_dual_axis_enabled_keeps_default_split() -> None:
    df = _make_frame()
    results = sensor_overview.build_enriched_group_figures(
        df, "Timestamp", "Device Tab",
        dual_axis_enabled={"wind": True},
    )
    fig = _fig_for_group_key(results, "Wind")
    assert fig is not None
    dir_traces = [t for t in fig.data if "direction" in str(t.name).lower()]
    assert dir_traces and all(t.yaxis == "y2" for t in dir_traces)


# ---------- Buoy / air overlay toggles ------------------------------

def test_overlay_buoy_default_renders_buoy_trace_on_sst_group() -> None:
    df = _make_frame()
    results = sensor_overview.build_enriched_group_figures(
        df, "Timestamp", "Device Tab",
    )
    fig = _fig_for_group_key(results, "Sea surface temperature")
    assert fig is not None
    assert any("Buoy" in str(t.name) for t in fig.data)


def test_overlay_buoy_disabled_drops_buoy_trace() -> None:
    df = _make_frame()
    results = sensor_overview.build_enriched_group_figures(
        df, "Timestamp", "Device Tab",
        overlay_buoy_sst=False,
    )
    fig = _fig_for_group_key(results, "Sea surface temperature")
    assert fig is not None
    assert not any("Buoy" in str(t.name) for t in fig.data)


def test_overlay_air_temp_adds_era5_trace_to_sst_group() -> None:
    df = _make_frame()
    results = sensor_overview.build_enriched_group_figures(
        df, "Timestamp", "Device Tab",
        overlay_air_temp=True,
    )
    fig = _fig_for_group_key(results, "Sea surface temperature")
    assert fig is not None
    assert any("Land / air temp" in str(t.name) for t in fig.data)


def test_overlay_internal_temp_adds_hull_trace_to_sst_group() -> None:
    df = _make_frame()
    results = sensor_overview.build_enriched_group_figures(
        df, "Timestamp", "Device Tab",
        overlay_internal_temp=True,
    )
    fig = _fig_for_group_key(results, "Sea surface temperature")
    assert fig is not None
    assert any("internal" in str(t.name).lower() for t in fig.data)


def test_overlay_internal_temp_default_off() -> None:
    df = _make_frame()
    results = sensor_overview.build_enriched_group_figures(
        df, "Timestamp", "Device Tab",
    )
    fig = _fig_for_group_key(results, "Sea surface temperature")
    assert fig is not None
    assert not any("internal" in str(t.name).lower() for t in fig.data)


# ---------- Enrichment coverage summary -----------------------------

def test_summarize_enrichment_coverage_reports_ranges_and_cells() -> None:
    df = _make_frame()
    df["Lat"] = 46.28
    df["Lon"] = -119.30
    cov = sensor_overview.summarize_enrichment_coverage(df, "Timestamp")
    assert cov["n_rows"] == len(df)
    assert cov["lat_min"] == pytest.approx(46.28)
    assert cov["lon_min"] == pytest.approx(-119.30)
    # Snapped to the 0.1° enrichment grid — single cell for constant lat/lon.
    assert cov["lat_cells"] == [46.3]
    assert cov["lon_cells"] == [-119.3]
    assert cov["n_hours_used"] > 0
    assert cov["t_min"] is not None and cov["t_max"] is not None


def test_summarize_enrichment_coverage_detects_inland_hint() -> None:
    df = _make_frame()
    # Inland signature: satellite products all NaN, Open-Meteo populated.
    for c in ("SAT_SST_OISST_cC", "SAT_SST_MUR_cC", "SAT_SST_OSTIA_cC"):
        df[c] = pd.NA
    df["SAT_SST_OPENMETEO_cC"] = 1100
    cov = sensor_overview.summarize_enrichment_coverage(df, "Timestamp")
    assert cov["inland_hint"] is True


def test_summarize_enrichment_coverage_empty_frame() -> None:
    cov = sensor_overview.summarize_enrichment_coverage(pd.DataFrame(), "Timestamp")
    assert cov["n_rows"] == 0
    assert cov["t_min"] is None and cov["lat_min"] is None
