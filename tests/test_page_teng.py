"""Smoke tests for the TENG performance page and its panel builders."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PAGES_DIR = REPO_ROOT / "pages"


# Reuse the rich stub from test_p2_skeleton so streamlit / gspread /
# plotly fallbacks are already wired up when we import a page module.
from tests.test_p2_skeleton import _install_stub_modules  # noqa: E402


def _load_module_from_path(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _synthetic(n: int = 200, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2025-08-01", periods=n, freq="3h", tz="UTC")
    hs = 1.5 + rng.normal(scale=0.6, size=n).clip(0.1, None)
    tp = 6.0 + rng.normal(scale=1.5, size=n).clip(2.0, None)
    p_mw = 4.0 * hs ** 2 * tp / 50.0 + rng.normal(scale=0.5, size=n)
    return pd.DataFrame({
        "Timestamp": ts,
        "WAVE_H_cm": (hs * 100).round().astype(int),
        "WAVE_T_ds": (tp * 10).round().astype(int),
        "TENG_P_mW": p_mw.clip(0.0, None),
        "Lat": 58.35, "Lon": -169.98,
    })


@pytest.fixture(autouse=True)
def _stubs():
    _install_stub_modules()
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    yield


def test_teng_panels_compute_kpis_on_synthetic():
    from utils.p2.viz.teng_panels import compute_kpis

    df = _synthetic()
    k = compute_kpis(df)
    assert set(k.keys()) == {"today_joules", "avg_power_mw", "ratio_pct"}
    assert k["avg_power_mw"] > 0
    assert np.isfinite(k["ratio_pct"])


def test_teng_panels_build_figures():
    from utils.p2.viz import teng_panels

    df = _synthetic()
    fig_hm = teng_panels.build_hs_tp_heatmap(df)
    assert fig_hm is not None and len(fig_hm.data) >= 1  # heatmap + markers
    fig_ll = teng_panels.build_loglog_hs2tp(df)
    assert fig_ll is not None and len(fig_ll.data) >= 1
    fig_flux = teng_panels.build_flux_scatter(df)
    assert fig_flux is not None
    for level in (0, 1, 2):
        out = teng_panels.build_eta_trend(df, level=level)
        assert out["fig"] is not None
        assert out["n"] >= 3
    fig_v = teng_panels.build_week_violin(df, level=1)
    assert fig_v is not None


def test_page7_importable_under_stub():
    page = PAGES_DIR / "7_🔋_TENG_Performance.py"
    assert page.exists()
    # The page calls sheets_client.get_all_data() — under the stub this
    # will raise and the page's try/except path handles it, then
    # triggers st.stop() which is a no-op.
    _load_module_from_path(page, "_page_7_teng")
