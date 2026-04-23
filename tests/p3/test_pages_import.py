"""Smoke-test that all Phase 3 pages import cleanly under the stubs.

Also re-checks that the Phase 1 pages 1..5 still import — guarding
against accidental regressions in `utils/sheets_client.py`
(Phase 3 added two entries to ``EXCLUDED_TABS``).
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
PAGES_DIR = REPO_ROOT / "pages"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Reuse the Phase 2 smoke-test stub harness so pages can import the
# real ``streamlit`` replacement used across the rest of the test
# suite. Importing the module side-effects the stub install.
sys.path.insert(0, str(REPO_ROOT / "tests"))
skel = importlib.import_module("test_p2_skeleton")
_install = skel._install_stub_modules  # type: ignore[attr-defined]
_StopExc = skel._StreamlitStub().__getattr__("stop")  # instantiate to set _StreamlitStop


def _load(path: Path, name: str) -> None:
    _install()
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        if type(exc).__name__ != "_StreamlitStop":
            raise


def _find_page(n: int) -> Path:
    matches = sorted(PAGES_DIR.glob(f"{n}_*.py"))
    assert matches, f"no page found for number {n}"
    return matches[0]


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5])
def test_phase1_pages_still_import(n):
    _load(_find_page(n), f"_phase1_page_{n}")


@pytest.mark.parametrize("n", [12, 13, 14, 15])
def test_phase3_pages_import(n):
    _load(_find_page(n), f"_phase3_page_{n}")
