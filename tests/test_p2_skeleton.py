"""
Smoke tests for the Phase 2 skeleton (PR P2-0).

These tests do NOT talk to Google Sheets or any external API. They
simply verify that modules import cleanly, the flag bitfield is sane,
and the sheets_client filter helper respects the session-state toggle.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PAGES_DIR = REPO_ROOT / "pages"


def _load_module_from_path(path: Path, mod_name: str) -> types.ModuleType:
    """Load a file-based module by absolute path without touching sys.path order."""
    spec = importlib.util.spec_from_file_location(mod_name, path)
    assert spec is not None and spec.loader is not None, f"cannot spec {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        # Pages may call st.stop() when data is missing; under the stub
        # that raises a sentinel exception which we treat as a valid
        # early return.
        if type(exc).__name__ != "_StreamlitStop":
            raise
    return module


class _MagicObj:
    """Permissive stub: any attribute access or call returns another _MagicObj.

    Supports context-manager, iteration, subscript, truthiness, and decorator
    use patterns so that Streamlit pages can import under test without a real
    Streamlit runtime.
    """

    def __init__(self, *_a, **_k):
        pass

    def __call__(self, *args, **_kwargs):
        # Decorator style: @st.cache_data(ttl=...) returns a decorator.
        if args and callable(args[0]) and len(args) == 1:
            return args[0]
        return _MagicObj()

    def __getattr__(self, _name):
        return _MagicObj()

    def __iter__(self):
        # st.tabs([...]) / st.columns(...) unpacking → yield infinite magics.
        return iter([_MagicObj() for _ in range(8)])

    def __getitem__(self, _key):
        return _MagicObj()

    def __setitem__(self, _key, _value):
        pass

    def __contains__(self, _key):
        return False

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def __bool__(self):
        return False

    def __len__(self):
        return 0


class _StreamlitStub(types.ModuleType):
    """Module subclass that returns _MagicObj for any attribute."""

    _p2_stub = True

    def __init__(self):
        super().__init__("streamlit")
        self.session_state: dict = {}
        self.secrets: dict = {}
        self.sidebar = _MagicObj()

        def _cache(*a, **_k):
            if a and callable(a[0]) and not _k:
                return a[0]

            def _wrap(fn):
                return fn

            return _wrap

        self.cache_data = _cache
        self.cache_resource = _cache

        # st.tabs / st.columns return a list whose length matches their arg,
        # so that ``a, b = st.tabs([...])`` unpacks correctly.
        def _tabs(labels, *_a, **_k):
            try:
                n = len(labels)
            except TypeError:
                n = int(labels) if isinstance(labels, int) else 2
            return [_MagicObj() for _ in range(max(1, n))]

        def _columns(spec, *_a, **_k):
            if isinstance(spec, int):
                n = spec
            else:
                try:
                    n = len(spec)
                except TypeError:
                    n = 2
            return [_MagicObj() for _ in range(max(1, n))]

        self.tabs = _tabs
        self.columns = _columns

        # st.stop() must actually halt page execution; we use a sentinel
        # exception that the test harness catches to mark "reached stop".
        class _StreamlitStop(Exception):
            pass
        self._StreamlitStop = _StreamlitStop  # type: ignore[attr-defined]

        def _stop():
            raise _StreamlitStop()
        self.stop = _stop

        # Input widgets return sensible default values so page code
        # that later does int()/float()/bool() on them still works.
        def _radio(label, options=None, *, index=0, **_k):
            opts = list(options or [])
            if not opts:
                return None
            idx = 0
            try:
                idx = int(index)
            except Exception:
                idx = 0
            return opts[min(max(idx, 0), len(opts) - 1)]

        def _selectbox(label, options=None, *, index=0, **_k):
            return _radio(label, options, index=index)

        def _multiselect(label, options=None, *, default=None, **_k):
            if default is not None:
                return list(default)
            return list(options or [])

        def _checkbox(*_a, value=False, **_k):
            return bool(value)

        def _slider(*_a, value=0, **_k):
            return value

        def _number_input(*_a, value=0, **_k):
            return value

        def _text_input(*_a, value="", **_k):
            return value

        def _date_input(*_a, value=None, **_k):
            return value

        def _button(*_a, **_k):
            return False

        self.radio = _radio
        self.selectbox = _selectbox
        self.multiselect = _multiselect
        self.checkbox = _checkbox
        self.slider = _slider
        self.number_input = _number_input
        self.text_input = _text_input
        self.date_input = _date_input
        self.button = _button

    def __getattr__(self, name):
        # Only called when attribute is NOT already set on the instance.
        obj = _MagicObj()
        setattr(self, name, obj)
        return obj


def _install_stub_modules() -> None:
    """Install stubs for streamlit and non-pure-python deps used by Phase 1."""
    if not isinstance(sys.modules.get("streamlit"), _StreamlitStub):
        sys.modules["streamlit"] = _StreamlitStub()

    # Only stub modules that are NOT actually installed. Stubbing a real
    # dependency (plotly, scipy, …) would break the panel builders that
    # rely on its real API.
    stub_names = [
        "gspread",
        "gspread.exceptions",
        "google",
        "google.oauth2",
        "google.oauth2.service_account",
        "folium",
        "streamlit_folium",
        "fpdf",
        "staticmap",
    ]
    import importlib.util
    for name in stub_names:
        if name in sys.modules:
            continue
        if importlib.util.find_spec(name) is not None:
            continue  # real module available, do not stub
        mod = types.ModuleType(name)
        mod.__getattr__ = lambda _n: _MagicObj()  # type: ignore[attr-defined]
        sys.modules[name] = mod

    # gspread.exceptions needs a WorksheetNotFound class for `except` clauses.
    gspread_exc = sys.modules["gspread.exceptions"]
    if not hasattr(gspread_exc, "WorksheetNotFound"):
        class WorksheetNotFound(Exception):
            pass

        gspread_exc.WorksheetNotFound = WorksheetNotFound  # type: ignore[attr-defined]
    gspread_mod = sys.modules["gspread"]
    if not hasattr(gspread_mod, "exceptions"):
        gspread_mod.exceptions = gspread_exc  # type: ignore[attr-defined]
    if not hasattr(gspread_mod, "Client"):
        class _Client:
            pass

        gspread_mod.Client = _Client  # type: ignore[attr-defined]
    if not hasattr(gspread_mod, "Spreadsheet"):
        class _Spreadsheet:
            pass

        gspread_mod.Spreadsheet = _Spreadsheet  # type: ignore[attr-defined]
    if not hasattr(gspread_mod, "authorize"):
        gspread_mod.authorize = lambda _c: _MagicObj()  # type: ignore[attr-defined]

    # google.oauth2.service_account.Credentials.from_service_account_info(...)
    sa_mod = sys.modules["google.oauth2.service_account"]
    if not hasattr(sa_mod, "Credentials"):
        class Credentials:
            @staticmethod
            def from_service_account_info(_info, scopes=None):  # noqa: ARG004
                return _MagicObj()

        sa_mod.Credentials = Credentials  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def _ensure_repo_on_syspath():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    _install_stub_modules()
    yield


def _find_phase1_page(n: int) -> Path:
    matches = sorted(PAGES_DIR.glob(f"{n}_*.py"))
    assert matches, f"no Phase 1 page found for number {n}"
    return matches[0]


def _find_phase2_page(n: int) -> Path:
    matches = sorted(PAGES_DIR.glob(f"{n}_*.py"))
    assert matches, f"no Phase 2 page found for number {n}"
    return matches[0]


# ──────────────────────────────────────────────────────────────────────
# Phase 1 smoke: pages 1..5 must still import under the stubbed runtime.
# ──────────────────────────────────────────────────────────────────────
def test_phase1_pages_importable():
    for n in (1, 2, 3, 4, 5):
        page = _find_phase1_page(n)
        _load_module_from_path(page, f"_phase1_page_{n}")


# ──────────────────────────────────────────────────────────────────────
# Schema / flag bits
# ──────────────────────────────────────────────────────────────────────
def test_p2_schema_flag_bits():
    from utils.p2.schema import (
        ENRICH_COLUMN_ORDER,
        FULL_ENRICHED_FLAG,
        EnrichFlag,
        decode_value,
        encode_value,
    )

    assert int(EnrichFlag.WAVE | EnrichFlag.WIND) == 3
    assert EnrichFlag.ERA5_SST in FULL_ENRICHED_FLAG
    assert "ENRICH_FLAG" in ENRICH_COLUMN_ORDER

    # Encode/decode round-trip with scale factor 100 (cm/°C).
    raw = encode_value("SAT_SST_OISST_cC", 12.34)
    assert isinstance(raw, int)
    assert abs(decode_value("SAT_SST_OISST_cC", raw) - 12.34) < 1e-6

    # NaN / empty round-trip.
    assert encode_value("SAT_SST_OISST_cC", float("nan")) == ""
    import math
    assert math.isnan(decode_value("SAT_SST_OISST_cC", ""))


# ──────────────────────────────────────────────────────────────────────
# Phase 2 placeholder pages must import (pages 7..10 after shift).
# ──────────────────────────────────────────────────────────────────────
def test_p2_placeholder_pages_importable():
    for n in (7, 8, 9, 10):
        page = _find_phase2_page(n)
        _load_module_from_path(page, f"_phase2_page_{n}")


# ──────────────────────────────────────────────────────────────────────
# sheets_client.apply_p2_column_filter
# ──────────────────────────────────────────────────────────────────────
def test_sheets_client_filter_drops_when_toggle_off():
    import streamlit as st  # stubbed

    from utils.p2.schema import ENRICH_COLUMN_ORDER
    from utils.sheets_client import apply_p2_column_filter

    df = pd.DataFrame(
        {
            "Timestamp": [pd.Timestamp("2026-01-01", tz="UTC")],
            "Device": ["BUOY-1"],
            ENRICH_COLUMN_ORDER[0]: [123],
            "ENRICH_FLAG": [7],
        }
    )

    # Toggle OFF → enriched columns dropped.
    st.session_state["p2_show_enriched"] = False
    out_off = apply_p2_column_filter(df.copy())
    for c in ENRICH_COLUMN_ORDER:
        assert c not in out_off.columns
    assert "Timestamp" in out_off.columns
    assert "Device" in out_off.columns

    # Toggle ON → enriched columns preserved.
    st.session_state["p2_show_enriched"] = True
    out_on = apply_p2_column_filter(df.copy())
    assert ENRICH_COLUMN_ORDER[0] in out_on.columns
    assert "ENRICH_FLAG" in out_on.columns
