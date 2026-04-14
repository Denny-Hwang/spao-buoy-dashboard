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


def test_page8_importable_under_stub():
    page = PAGES_DIR / "8_🌊_SST_Validation.py"
    assert page.exists()
    _load_module(page, "_page_8_sst")
