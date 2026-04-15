from __future__ import annotations

import pytest

from utils.p2 import sheets_io


def test_with_quota_retries_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}
    sleeps: list[float] = []

    monkeypatch.setattr(sheets_io.time, "sleep", lambda s: sleeps.append(s))

    def _fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("APIError: [429]: Quota exceeded")
        return "ok"

    out = sheets_io._with_quota_retries(_fn, op="unit-test")
    assert out == "ok"
    assert calls["n"] == 3
    assert sleeps == [2.0, 5.0]


def test_with_quota_retries_does_not_retry_non_quota_error(monkeypatch):
    monkeypatch.setattr(sheets_io.time, "sleep", lambda _s: pytest.fail("should not sleep"))

    def _fn():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        sheets_io._with_quota_retries(_fn, op="unit-test")

