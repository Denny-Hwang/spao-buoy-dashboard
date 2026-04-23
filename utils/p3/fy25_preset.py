"""Load the FY25 Bering-sea deployment preset.

The raw data lives in ``data/presets/fy25_deployment.json`` so it is
version-controlled alongside the Phase 3 code. This module exposes
two helpers:

* :func:`load_fy25_preset` — returns the raw dict (map config, cutoffs…).
* :func:`load_fy25_frame` — returns a Phase-1-shaped DataFrame so the
  Field-Replay page can reuse exactly the same join path it uses on
  live Google-Sheets data.

The preset ships with a frozen TLE epoch baked into a metadata field;
the Field-Replay page displays that alongside the live Iridium TLE
health so the user can tell at a glance they are looking at historical
geometry (SGP4 accuracy degrades rapidly with epoch age).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_PRESET_PATH = Path(__file__).resolve().parents[2] / "data" / "presets" / "fy25_deployment.json"


def preset_path() -> Path:
    """Absolute path to the FY25 preset JSON. Kept public for tests."""
    return _PRESET_PATH


def load_fy25_preset() -> dict:
    """Return the preset dict (raises ``FileNotFoundError`` if missing)."""
    with _PRESET_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_fy25_frame() -> pd.DataFrame:
    """Return TX events as a Phase-1-shaped DataFrame.

    Columns are aligned with the aliases in :mod:`utils.p3.tx_join`
    so ``enrich_phase1_frame`` can ingest the result unchanged.
    """
    preset = load_fy25_preset()
    df = pd.DataFrame(preset["tx_events"])
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce", utc=True)
    df["Device Tab"] = df["device"]
    df = df.rename(columns={"tx": "TX Index"})
    # Preserve the boat/ocean annotation from the preset for the UI.
    cutoffs: dict[str, int] = preset.get("boat_cutoff", {}) or {}
    df["Deployment Phase"] = df.apply(
        lambda r: "Boat" if (
            r["device"] in cutoffs and r["TX Index"] < cutoffs[r["device"]]
        ) else "Ocean",
        axis=1,
    )
    return df


def approx_tle_epoch() -> datetime:
    """Return a representative TLE epoch (2025-09-10 UTC).

    The FY25 preset was recorded against a CelesTrak snapshot that
    had a median Iridium epoch age of ~12 h — we approximate it as
    2025-09-10 12:00 UTC so the "TLE age" column in the exported CSV
    is at least self-consistent. The live Iridium TLE stored in the
    Google Sheet would of course be wildly out of date for 2025-09-10
    playback, so the Field Replay page hides the "live TLE health"
    warning when FY25 is selected.
    """
    return datetime(2025, 9, 10, 12, 0, tzinfo=timezone.utc)
