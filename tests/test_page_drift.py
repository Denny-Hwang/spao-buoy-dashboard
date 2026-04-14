"""Smoke tests for page 9 Drift Dynamics and drift_panels."""

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
        # Streamlit pages call st.stop() when data is missing; under the
        # stub this raises a sentinel exception which we treat as a
        # successful early return.
        if type(exc).__name__ != "_StreamlitStop":
            raise
    return mod


def _synthetic(n: int = 200, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2025-08-01", periods=n, freq="1h", tz="UTC")
    lat0 = 58.0 + 0.001 * np.cumsum(rng.normal(size=n))
    lon0 = -170.0 + 0.002 * np.cumsum(rng.normal(size=n))
    wind_u = 5 + rng.normal(scale=2, size=n)
    wind_v = 2 + rng.normal(scale=2, size=n)
    wind_spd = np.sqrt(wind_u ** 2 + wind_v ** 2)
    wind_dir = (np.degrees(np.arctan2(wind_v, wind_u)) + 360) % 360
    hs = np.full(n, 1.5)
    hs[60:70] = 5.5  # storm
    return pd.DataFrame({
        "Timestamp": ts,
        "Lat": lat0,
        "Lon": lon0,
        "U10": wind_u,
        "V10": wind_v,
        "WIND_SPD_cms": (wind_spd * 100).astype(int),
        "WIND_DIR_deg": wind_dir.astype(int),
        "Hs": hs,
        "WAVE_H_cm": (hs * 100).astype(int),
        "Pres": np.full(n, 1012.0),
        "OSCAR_U_mms": rng.normal(scale=50, size=n).astype(int),
        "OSCAR_V_mms": rng.normal(scale=50, size=n).astype(int),
    })


@pytest.fixture(autouse=True)
def _stubs():
    _install_stub_modules()
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    yield


def test_c1_trajectory_and_distance():
    from utils.p2.viz import drift_panels

    df = _synthetic()
    assert drift_panels.build_trajectory_speed_colored(df) is not None
    assert drift_panels.build_stick_plot_drift(df) is not None
    assert drift_panels.build_cumulative_distance(df) is not None
    assert drift_panels.build_daily_displacement(df) is not None


def test_c2_alpha_and_roses():
    from utils.p2.viz import drift_panels

    df = _synthetic()
    assert drift_panels.build_alpha_timeseries(df) is not None
    assert drift_panels.build_theta_histogram(df) is not None
    wind_rose, drift_rose = drift_panels.build_wind_and_drift_rose(df)
    assert wind_rose is not None and drift_rose is not None
    assert drift_panels.build_residual_vs_oscar(df) is not None


def test_c3_storm_table_and_epoch():
    from utils.p2.viz import drift_panels

    df = _synthetic()
    tbl = drift_panels.build_storm_event_table(df)
    assert not tbl.empty  # the injected storm window should be detected
    assert {"id", "type", "start", "end", "duration_h", "peak_Hs", "peak_U10"}.issubset(tbl.columns)
    fig = drift_panels.build_epoch_multipanel(df)
    assert fig is not None
    fig_box = drift_panels.build_pre_during_post_box(df, var="Hs")
    assert fig_box is not None


def test_page9_importable_under_stub():
    page = PAGES_DIR / "9_🧭_Drift_Dynamics.py"
    assert page.exists()
    _load_module(page, "_page_9_drift")
