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


@pytest.mark.parametrize(
    "marker",
    [
        "APIError: [500]: Internal error encountered",
        "APIError: [502]: Bad Gateway",
        "APIError: [503]: The service is currently unavailable.",
        "APIError: [504]: Deadline exceeded",
        "Backend Error",
    ],
)
def test_with_quota_retries_retries_on_transient_5xx(monkeypatch, marker):
    """Daily Enrichment / Derived Daily used to crash on a single 503
    response from Google Sheets API. The retry helper must now treat
    5xx as transient and retry with backoff."""
    calls = {"n": 0}
    sleeps: list[float] = []
    monkeypatch.setattr(sheets_io.time, "sleep", lambda s: sleeps.append(s))

    def _fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError(marker)
        return "ok"

    out = sheets_io._with_quota_retries(_fn, op="unit-test-5xx")
    assert out == "ok"
    assert calls["n"] == 3
    # First two delays come from DEFAULT_RETRY_DELAYS_S.
    assert sleeps[:2] == [
        sheets_io.DEFAULT_RETRY_DELAYS_S[0],
        sheets_io.DEFAULT_RETRY_DELAYS_S[1],
    ]


def test_is_retryable_error_covers_both_families():
    assert sheets_io._is_retryable_error(RuntimeError("APIError: [429]: Quota exceeded"))
    assert sheets_io._is_retryable_error(RuntimeError("APIError: [503]: The service is currently unavailable."))
    assert sheets_io._is_retryable_error(RuntimeError("Backend Error"))
    assert not sheets_io._is_retryable_error(RuntimeError("PermissionError: forbidden"))
    # Backwards-compat alias still works.
    assert sheets_io._is_retryable_quota_error is sheets_io._is_retryable_error

