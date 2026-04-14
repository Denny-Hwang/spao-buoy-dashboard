"""Smoke tests for page 10 Data Enrichment."""

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


@pytest.fixture(autouse=True)
def _stubs():
    _install_stub_modules()
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    yield


def test_page10_importable_under_stub():
    page = PAGES_DIR / "10_📡_Data_Enrichment.py"
    assert page.exists()
    _load_module(page, "_page_10_enrichment")


def test_qc_imports_from_page_context():
    from utils.p2 import qc
    from utils.p2.schema import EnrichFlag  # page depends on this

    assert hasattr(qc, "qc_summary")
    assert int(EnrichFlag.WAVE) == 1
