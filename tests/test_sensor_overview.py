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
