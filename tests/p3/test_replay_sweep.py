"""``replay_panels.gnss_timeout_sweep`` robustness checks.

The previous implementation blew up with ``KeyError`` on Python 3.14
pandas when the frame lacked a ``GPS Valid`` or ``GPS Time`` column,
because the fallback ``df.get("GPS Valid", pd.Series())`` returned an
empty series whose index no longer aligned with ``df.index``. The
rewrite uses ``reindex`` + positional iteration, so missing columns
degrade gracefully and no ``.loc`` KeyError can occur.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

sys.path.insert(0, str(REPO_ROOT / "tests"))
_skel = importlib.import_module("test_p2_skeleton")
_skel._install_stub_modules()  # type: ignore[attr-defined]

from utils.p3.viz import replay_panels  # noqa: E402


def test_sweep_empty_frame_returns_zero_metrics():
    out = replay_panels.gnss_timeout_sweep(pd.DataFrame(), 30.0)
    assert out["n"] == 0
    assert out["fail_rate"] == 0.0


def test_sweep_missing_gps_valid_column_does_not_raise():
    df = pd.DataFrame({"GPS Time": [10, 20, 40]})
    out = replay_panels.gnss_timeout_sweep(df, 30.0)
    assert out["n"] == 3
    # Only the 40-second event exceeds the 30s cutoff.
    assert out["would_fail"] == 1


def test_sweep_missing_gps_time_column_does_not_raise():
    df = pd.DataFrame({"GPS Valid": ["YES", "NO", "YES"]})
    out = replay_panels.gnss_timeout_sweep(df, 30.0)
    assert out["n"] == 3
    # The NO row is a new failure at the 30 s cutoff (<35 s).
    assert out["would_fail"] == 1


def test_sweep_reset_index_frame():
    """The filtered frame on the Field Replay page has a 0-based index."""
    df = pd.DataFrame({
        "GPS Valid": ["YES", "YES", "NO"],
        "GPS Time":  [10.0, 32.0, 40.0],
    })
    # Simulate a filtered frame: reset_index, non-contiguous possible.
    df = df.iloc[[2, 0, 1]].reset_index(drop=True)
    out = replay_panels.gnss_timeout_sweep(df, 30.0)
    # @30s: idx0 is NO (fail), idx1 YES 10s (pass), idx2 YES 32s (fail)
    assert out["would_fail"] == 2


def test_sweep_failures_succeed_at_high_cutoff():
    """At cutoff>=35 s the historical GPS failures are assumed rescued."""
    df = pd.DataFrame({
        "GPS Valid": ["NO", "YES"],
        "GPS Time":  [30.0, 12.0],
    })
    out = replay_panels.gnss_timeout_sweep(df, 45.0)
    assert out["would_fail"] == 0
