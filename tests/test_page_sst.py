"""Smoke tests for the SST Validation page and sst_panels."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PAGES_DIR = REPO_ROOT / "pages"

from tests.test_p2_skeleton import _install_stub_modules  # noqa: E402


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        if type(exc).__name__ != "_StreamlitStop":
            raise
    return mod


def _synthetic(n: int = 200, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2025-06-01", periods=n, freq="3h", tz="UTC")
    base = 10.0 + 2.0 * np.sin(np.arange(n) / 24 * 2 * np.pi) + rng.normal(scale=0.3, size=n)
    return pd.DataFrame({
        "Timestamp": ts,
        "SST_buoy": base,
        "SAT_SST_OISST_cC": ((base - 0.10) * 100).round().astype(int),
        "SAT_SST_MUR_cC": ((base + 0.05) * 100).round().astype(int),
        "SAT_SST_OSTIA_cC": ((base * 1.02 - 0.02) * 100).round().astype(int),
        "SAT_SST_ERA5_cC": ((base + 0.20) * 100).round().astype(int),
        "WIND_SPD_cms": (5.0 * 100 + rng.normal(scale=100, size=n)).astype(int),
        "Lat": 58.35, "Lon": -169.98,
    })


@pytest.fixture(autouse=True)
def _stubs():
    _install_stub_modules()
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    yield


def test_extract_helpers_find_aliases():
    from utils.p2.viz import sst_panels

    df = _synthetic()
    buoy = sst_panels.extract_buoy_sst(df)
    assert buoy is not None
    assert len(buoy) == 200
    products = sst_panels.extract_products(df)
    assert set(products.keys()) == {"OISST", "ERA5", "MUR", "OSTIA"}
    # OISST decode: int °C×100 → float °C.
    assert products["OISST"].iloc[0] == pytest.approx(
        df["SAT_SST_OISST_cC"].iloc[0] / 100.0
    )


def test_metrics_table_has_expected_rows():
    from utils.p2.viz import sst_panels
    df = _synthetic()
    tbl = sst_panels.build_metrics_table(df)
    assert set(tbl.index) == {"OISST", "ERA5", "MUR", "OSTIA"}
    # metrics_table computes mean(pred - obs). obs=buoy, pred=OISST=buoy-0.10
    # ⇒ bias ≈ -0.10.
    assert tbl.loc["OISST", "bias"] == pytest.approx(-0.10, abs=0.05)


def test_b1_figures():
    from utils.p2.viz import sst_panels
    df = _synthetic()
    assert sst_panels.build_sst_timeseries(df) is not None
    assert sst_panels.build_residual_histogram(df) is not None
    assert sst_panels.build_taylor(df) is not None
    assert sst_panels.build_target(df) is not None


def test_sst_timeseries_autodetects_alternate_time_column():
    """build_sst_timeseries should not require a literal ``Timestamp`` column."""
    from utils.p2.viz import sst_panels
    df = _synthetic().rename(columns={"Timestamp": "Transmit Time"})
    fig = sst_panels.build_sst_timeseries(df)
    assert fig is not None
    # Should have at least one trace for buoy + 4 products.
    assert len(fig.data) >= 5


def test_sst_timeseries_colors_per_device_when_dev_col_present():
    """Multiple devices → one buoy trace per device in distinct colors."""
    from utils.p2.viz import sst_panels
    df1 = _synthetic(n=100, seed=1)
    df1["Device Tab"] = "Buoy-A"
    df2 = _synthetic(n=100, seed=2)
    df2["Device Tab"] = "Buoy-B"
    combined = pd.concat([df1, df2], ignore_index=True)

    fig = sst_panels.build_sst_timeseries(combined)
    buoy_traces = [t for t in fig.data if str(t.name).startswith("Buoy")]
    assert len(buoy_traces) == 2
    names = {t.name for t in buoy_traces}
    assert names == {"Buoy — Buoy-A", "Buoy — Buoy-B"}


def test_sst_timeseries_missing_time_col_returns_empty_fig():
    from utils.p2.viz import sst_panels
    df = _synthetic().drop(columns=["Timestamp"])
    fig = sst_panels.build_sst_timeseries(df)
    # Fig still exists but has no traces when no time column can be resolved.
    assert fig is not None
    assert len(fig.data) == 0


def test_b2_drift_detection_and_alarm():
    from utils.p2.viz import sst_panels

    # Inject a +0.02 °C/week drift → should trip the 0.01 °C/week alarm.
    df = _synthetic()
    t_days = (pd.to_datetime(df["Timestamp"]) - pd.to_datetime(df["Timestamp"]).iloc[0])
    t_days_f = t_days.dt.total_seconds().to_numpy() / 86400.0
    df["SST_buoy"] = df["SST_buoy"] + 0.02 / 7.0 * t_days_f
    out = sst_panels.build_drift_timeseries(df)
    assert out["alarm"]
    assert np.isfinite(out["slope_per_week"])
    assert out["slope_per_week"] > 0.01


def test_b2_other_figures():
    from utils.p2.viz import sst_panels
    df = _synthetic()
    assert sst_panels.build_drift_boxplot(df) is not None
    assert sst_panels.build_cusum_chart(df) is not None


def test_b3_diurnal_panels():
    from utils.p2.viz import sst_panels
    df = _synthetic()
    assert sst_panels.build_diurnal_composite(df) is not None
    assert sst_panels.build_amplitude_vs_wind(df) is not None


def test_internal_vs_air_diagnostic_detects_phase_shift():
    """Two identical diurnal cycles offset by 12 h must come back with
    ``phase_shift_hours`` close to ±12 so the page can flag a timezone
    bug. Negative correlation is a consequence of the 12-h shift."""
    from utils.p2.viz import sst_panels

    n = 72
    ts = pd.date_range("2025-06-01", periods=n, freq="h", tz="UTC")
    hours = np.arange(n) % 24
    # internal: peak at hour 14 UTC; air: peak at hour 02 UTC → 12h shift.
    internal = 15.0 + 10.0 * np.cos((hours - 14) / 24.0 * 2 * np.pi)
    air = 15.0 + 10.0 * np.cos((hours - 2) / 24.0 * 2 * np.pi)
    df = pd.DataFrame({
        "Timestamp": ts,
        "Internal Temp": internal,
        "ERA5_AIRT_cC": (air * 100).round().astype(int),
    })
    out = sst_panels.build_internal_vs_air_diagnostic(df)
    stats = out["stats"]
    assert stats["n"] == n
    assert stats["correlation"] < -0.9, stats
    assert abs(abs(stats["phase_shift_hours"]) - 12.0) <= 1.0, stats
    assert 0 <= stats["peak_hour_air"] <= 23
    assert 0 <= stats["peak_hour_internal"] <= 23


def test_internal_vs_air_diagnostic_in_phase_series():
    """When the two streams peak within a thermal-lag-reasonable window
    the phase shift stays small and correlation is strongly positive."""
    from utils.p2.viz import sst_panels

    n = 72
    ts = pd.date_range("2025-06-01", periods=n, freq="h", tz="UTC")
    hours = np.arange(n) % 24
    air = 15.0 + 8.0 * np.cos((hours - 15) / 24.0 * 2 * np.pi)
    # Hull lags air by 2 h (typical thermal inertia).
    internal = 18.0 + 12.0 * np.cos((hours - 17) / 24.0 * 2 * np.pi)
    df = pd.DataFrame({
        "Timestamp": ts,
        "Internal Temp": internal,
        "ERA5_AIRT_cC": (air * 100).round().astype(int),
    })
    out = sst_panels.build_internal_vs_air_diagnostic(df)
    stats = out["stats"]
    assert stats["correlation"] > 0.8
    assert abs(stats["phase_shift_hours"]) <= 3.0, stats


def test_page_sst_importable_under_stub():
    page = PAGES_DIR / "9_🌊_SST_Validation.py"
    assert page.exists()
    _load_module(page, "_page_8_sst")
