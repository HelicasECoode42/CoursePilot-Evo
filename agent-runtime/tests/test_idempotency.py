from __future__ import annotations

import pytest

from agent_runtime.api.idempotency import (
    IdempotencyConflict,
    IdempotencyStore,
    RequestInProgress,
)


def test_begin_marks_in_progress_and_second_same_key_conflicts() -> None:
    store = IdempotencyStore()
    assert store.begin("s", "planning", "k", "digest-a") is None
    with pytest.raises(RequestInProgress):
        store.begin("s", "planning", "k", "digest-a")


def test_different_body_same_key_is_idempotency_conflict() -> None:
    store = IdempotencyStore()
    store.begin("s", "planning", "k", "digest-a")
    with pytest.raises(IdempotencyConflict):
        store.begin("s", "planning", "k", "digest-b")


def test_complete_then_reuse_same_payload() -> None:
    store = IdempotencyStore()
    store.begin("s", "planning", "k", "digest-a")
    store.complete("s", "planning", "k", "digest-a", {"ok": True})
    assert store.begin("s", "planning", "k", "digest-a") == {"ok": True}


def test_abort_allows_retry() -> None:
    store = IdempotencyStore()
    store.begin("s", "planning", "k", "digest-a")
    store.abort("s", "planning", "k")
    assert store.begin("s", "planning", "k", "digest-a") is None


def test_run_aborts_on_failure_then_retries() -> None:
    store = IdempotencyStore()
    calls = {"n": 0}

    def boom() -> dict:
        calls["n"] += 1
        raise RuntimeError("tool down")

    with pytest.raises(RuntimeError):
        store.run("s", "planning", "k", "digest-a", boom)
    assert store.run("s", "planning", "k", "digest-a", lambda: {"n": calls["n"]}) == {"n": 1}
