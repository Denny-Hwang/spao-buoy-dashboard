"""Tests for Derived_Daily aggregation (utils.p2.derived + the CLI)."""

from __future__ import annotations

import importlib
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils.p2.derived import (  # noqa: E402
    DERIVED_DAILY_COLUMNS,
    compute_daily_table,
)


def _synthetic_hourly(days: int = 3, seed: int = 0) -> pd.DataFrame:
    """Return 24×``days`` hourly rows covering three UTC days."""
    rng = np.random.default_rng(seed)
    total = 24 * days
    start = pd.Timestamp("2025-09-09", tz="UTC")
    ts = pd.date_range(start, periods=total, freq="1h")
    hs = 1.5 + 0.2 * np.sin(np.arange(total) / 12 * np.pi) + rng.normal(scale=0.05, size=total)
    tp = 6.0 + rng.normal(scale=0.2, size=total)
    teng = 4.0 * hs ** 2 * tp / 50.0 + rng.normal(scale=0.1, size=total)
    buoy = 10.0 + 0.5 * np.sin(np.arange(total) / 24 * 2 * np.pi) + rng.normal(scale=0.05, size=total)
    oisst = buoy - 0.10  # constant negative bias
    lat = 58.0 + 0.001 * np.cumsum(rng.normal(size=total))
    lon = -170.0 + 0.002 * np.cumsum(rng.normal(size=total))
    u10 = 5.0 + rng.normal(scale=1.0, size=total)
    v10 = 2.0 + rng.normal(scale=1.0, size=total)
    return pd.DataFrame({
        "Timestamp": ts,
        "Lat": lat,
        "Lon": lon,
        "U10": u10,
        "V10": v10,
        "TENG_P_mW": teng,
        "Hs": hs,
        "Tp": tp,
        "WAVE_H_cm": (hs * 100).round().astype(int),
        "WAVE_T_ds": (tp * 10).round().astype(int),
        "SST_buoy": buoy,
        "SAT_SST_OISST_cC": (oisst * 100).round().astype(int),
    })


# ──────────────────────────────────────────────────────────────────────
# Aggregation correctness
# ──────────────────────────────────────────────────────────────────────
def test_compute_daily_table_three_days():
    df = _synthetic_hourly(days=3)
    daily = compute_daily_table(df)
    assert len(daily) == 3
    assert list(daily.columns) == DERIVED_DAILY_COLUMNS
    assert (daily["n_records"] == 24).all()
    # SST_buoy is ~10 °C, OISST = buoy − 0.10. Bias = mean(buoy − OISST) = +0.10.
    assert daily["sst_bias_OISST"].mean() == pytest.approx(0.10, abs=0.01)
    # Products not in df remain NaN.
    assert daily["sst_bias_MUR"].isna().all()
    assert daily["sst_bias_ERA5"].isna().all()
    assert daily["sst_bias_OSTIA"].isna().all()
    # Drift distance is positive (synthetic random walk).
    assert (daily["drift_distance_km"] >= 0).all()


def test_compute_daily_table_sets_teng_slope_after_3_days():
    df = _synthetic_hourly(days=5)
    daily = compute_daily_table(df)
    assert len(daily) == 5
    # First two rows have window < 3 points → NaN. Remaining rows are finite.
    assert daily["teng_eta_l1_slope"].iloc[0] != daily["teng_eta_l1_slope"].iloc[0]  # NaN
    assert np.isfinite(daily["teng_eta_l1_slope"].iloc[-1])


def test_compute_daily_table_empty_input():
    out = compute_daily_table(pd.DataFrame())
    assert out.empty
    assert list(out.columns) == DERIVED_DAILY_COLUMNS


def test_compute_daily_table_missing_day_gap():
    df1 = _synthetic_hourly(days=2)
    df2 = _synthetic_hourly(days=1, seed=1)
    # Shift df2 forward by 4 days to create a 2-day gap.
    df2["Timestamp"] = df2["Timestamp"] + pd.Timedelta(days=4)
    combined = pd.concat([df1, df2], ignore_index=True)
    daily = compute_daily_table(combined)
    # We expect a row per UTC date present → 3 distinct dates (no row for the gap).
    assert len(daily) == 3
    assert daily["date"].tolist() == ["2025-09-09", "2025-09-10", "2025-09-13"]


def test_compute_daily_storm_flag_true_when_injected():
    df = _synthetic_hourly(days=1)
    df.loc[6:12, "Hs"] = 5.5  # instant-trigger storm
    df.loc[6:12, "WAVE_H_cm"] = 550
    daily = compute_daily_table(df)
    assert bool(daily["storm_flag"].iloc[0]) is True
    assert "wave" in daily["storm_type_dominant"].iloc[0]


def test_windage_columns_present_even_without_drift():
    # Without u_drift the windage fit should be NaN, not crash.
    df = _synthetic_hourly(days=1)
    daily = compute_daily_table(df)
    assert daily["windage_alpha"].isna().all()
    assert daily["ekman_theta_deg"].isna().all()


# ──────────────────────────────────────────────────────────────────────
# Idempotency of write_derived_daily (via stubbed gspread worksheet)
# ──────────────────────────────────────────────────────────────────────
class _FakeWorksheet:
    def __init__(self, existing_rows: list[dict] | None = None):
        self._records = list(existing_rows or [])
        self.updated_range: tuple[str, list] | None = None
        self.cleared = False

    def get_all_records(self):
        return list(self._records)

    def clear(self):
        self.cleared = True
        self._records = []

    def update(self, range_name=None, values=None):
        self.updated_range = (range_name, values)
        if values and len(values) > 1:
            header = values[0]
            new = [dict(zip(header, row)) for row in values[1:]]
            self._records = new


class _FakeSpreadsheet:
    def __init__(self, ws: _FakeWorksheet):
        self._ws = ws
        self.added = None

    def worksheet(self, title):
        return self._ws

    def add_worksheet(self, title, rows, cols):
        self.added = (title, rows, cols)
        return self._ws


def test_write_derived_daily_upserts_existing_rows(monkeypatch):
    from utils.p2 import derived_io

    ws = _FakeWorksheet(existing_rows=[
        {col: "" for col in DERIVED_DAILY_COLUMNS} | {
            "date": "2025-09-08", "n_records": 24, "teng_eta_l1_mean": 1.23,
        },
        {col: "" for col in DERIVED_DAILY_COLUMNS} | {
            "date": "2025-09-09", "n_records": 10, "teng_eta_l1_mean": 9.99,
        },
    ])
    sh = _FakeSpreadsheet(ws)
    monkeypatch.setattr(derived_io, "open_spreadsheet", lambda _id: sh)

    new = pd.DataFrame([
        {col: "" for col in DERIVED_DAILY_COLUMNS} | {
            "date": "2025-09-09", "n_records": 24, "teng_eta_l1_mean": 2.0,
        },
        {col: "" for col in DERIVED_DAILY_COLUMNS} | {
            "date": "2025-09-10", "n_records": 24, "teng_eta_l1_mean": 2.5,
        },
    ])
    written = derived_io.write_derived_daily("sheet-id", new)
    # Expect 3 final rows: 09-08 kept, 09-09 overwritten, 09-10 added.
    assert written == 3
    dates = [r["date"] for r in ws._records]
    assert dates == ["2025-09-08", "2025-09-09", "2025-09-10"]
    # The 09-09 teng value was overwritten with the new value.
    updated_row = next(r for r in ws._records if r["date"] == "2025-09-09")
    assert float(updated_row["teng_eta_l1_mean"]) == pytest.approx(2.0)


def test_write_derived_daily_creates_tab_when_missing(monkeypatch):
    from utils.p2 import derived_io

    class _MissingWorksheet(_FakeWorksheet):
        pass

    class _LazySpreadsheet:
        def __init__(self):
            self._ws = _MissingWorksheet()
            self.added = None

        def worksheet(self, title):
            if self.added is None:
                raise RuntimeError("missing")
            return self._ws

        def add_worksheet(self, title, rows, cols):
            self.added = (title, rows, cols)
            return self._ws

    sh = _LazySpreadsheet()
    monkeypatch.setattr(derived_io, "open_spreadsheet", lambda _id: sh)

    df = pd.DataFrame([
        {col: "" for col in DERIVED_DAILY_COLUMNS} | {
            "date": "2025-09-10", "n_records": 24,
        }
    ])
    written = derived_io.write_derived_daily("sheet-id", df)
    assert written == 1
    assert sh.added is not None


# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────
def test_cli_default_window_last_7_days():
    cli = importlib.import_module("scripts.compute_daily_derived")
    start, end = cli.default_window()
    assert (end - start).days == 7


def test_cli_filter_window_keeps_in_range_only():
    cli = importlib.import_module("scripts.compute_daily_derived")
    df = _synthetic_hourly(days=5)
    out = cli.filter_window(df, date(2025, 9, 10), date(2025, 9, 11))
    # 2 days × 24 hours = 48 rows in window.
    assert len(out) == 48
