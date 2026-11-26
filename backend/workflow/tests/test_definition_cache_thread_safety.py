"""P2.7 (m-11) — the workflow-definition cache must survive concurrent access.

``_DefinitionCache`` used to be a bare dict whose ``put`` interleaved
``len()``, ``next(iter(...))`` and ``del`` with no lock at all. Under
concurrent writers two threads could both pass the size check, both pick the
same oldest key and the loser's ``del`` raised ``KeyError`` — or a thread
iterated the dict while another resized it and ``RuntimeError: dictionary
changed size during iteration`` escaped. In production that surfaced as a 500
on an unrelated transition, under load only.

These tests are deliberately *behavioural* (no exception, bounded size,
invalidate/put ordering consistency) and assert **no** wall-clock numbers — a
timing assertion on a shared CI box is a flake generator, and the contract here
is memory safety, not throughput.
"""
from __future__ import annotations

import threading
import uuid

from workflow.definition_store import WorkflowDefinitionDTO
from workflow.transition_validator import _DefinitionCache

_THREADS = 8
_OPS_PER_THREAD = 500


def _dto(workspace_id: str, item_type: str, marker: int) -> WorkflowDefinitionDTO:
    return WorkflowDefinitionDTO(
        states=(f"s{marker}",),
        transitions=(),
        workspace_id=uuid.UUID(workspace_id),
        item_type=item_type,
        preset="standard",
    )


def test_concurrent_put_get_invalidate_never_raises_and_stays_bounded() -> None:
    """8 threads x 500 mixed ops: no exception, size never above the cap."""
    cache = _DefinitionCache()
    # A workspace uuid per thread keeps the keys mostly distinct, which is what
    # forces the eviction branch to run constantly once the cap is reached.
    workspaces = [str(uuid.uuid4()) for _ in range(_THREADS)]
    errors: list[BaseException] = []
    over_capacity: list[int] = []
    barrier = threading.Barrier(_THREADS)

    def worker(index: int) -> None:
        workspace = workspaces[index]
        try:
            barrier.wait(timeout=10)
            for op in range(_OPS_PER_THREAD):
                key_workspace = workspaces[(index + op) % _THREADS]
                item_type = f"Type{op % 7}"
                if op % 5 == 4:
                    cache.invalidate(key_workspace, item_type)
                else:
                    cache.put(
                        key_workspace,
                        item_type,
                        _dto(key_workspace, item_type, op),
                    )
                cache.get(workspace, item_type)
                size = len(cache._cache)  # noqa: SLF001 — invariant under test
                if size > cache._MAX_ENTRIES:
                    over_capacity.append(size)
        except BaseException as exc:  # noqa: BLE001 — collected for the assert
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(i,), name=f"cache-{i}")
        for i in range(_THREADS)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, f"concurrent cache access raised: {errors!r}"
    assert not over_capacity, (
        f"cache grew past _MAX_ENTRIES={cache._MAX_ENTRIES}: "
        f"{sorted(set(over_capacity))}"
    )
    assert all(not thread.is_alive() for thread in threads), "a worker deadlocked"


def test_eviction_at_capacity_keeps_the_floor() -> None:
    """Filling past the cap evicts instead of growing — sequentially.

    The sequential twin of the test above: it pins the invariant that the
    concurrent run asserts, so a failure names the eviction logic rather than
    "something raced".
    """
    cache = _DefinitionCache()
    workspace = str(uuid.uuid4())
    for index in range(cache._MAX_ENTRIES + 10):
        cache.put(workspace, f"Type{index}", _dto(workspace, f"Type{index}", index))

    assert len(cache._cache) == cache._MAX_ENTRIES  # noqa: SLF001
    # The ten oldest keys are gone, the newest is present.
    assert cache.get(workspace, "Type0") is None
    assert cache.get(workspace, f"Type{cache._MAX_ENTRIES + 9}") is not None


def test_invalidate_between_get_and_put_stays_consistent() -> None:
    """get -> invalidate -> put leaves exactly the fresh value, never a ghost."""
    cache = _DefinitionCache()
    workspace = str(uuid.uuid4())
    stale = _dto(workspace, "Issue", 1)
    fresh = _dto(workspace, "Issue", 2)

    cache.put(workspace, "Issue", stale)
    assert cache.get(workspace, "Issue") is stale

    cache.invalidate(workspace, "Issue")
    assert cache.get(workspace, "Issue") is None

    cache.put(workspace, "Issue", fresh)
    assert cache.get(workspace, "Issue") is fresh


def test_a_fresh_put_after_invalidation_is_returned_to_every_reader() -> None:
    """After invalidation the next put is visible to all threads (no shadow)."""
    cache = _DefinitionCache()
    workspace = str(uuid.uuid4())
    cache.put(workspace, "Risk", _dto(workspace, "Risk", 0))
    cache.invalidate(workspace, "Risk")

    fresh = _dto(workspace, "Risk", 99)
    seen: list[WorkflowDefinitionDTO | None] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(_THREADS)

    def reader() -> None:
        try:
            barrier.wait(timeout=10)
            seen.append(cache.get(workspace, "Risk"))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=reader) for _ in range(_THREADS - 1)]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=10)  # the writer is this thread
    cache.put(workspace, "Risk", fresh)
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, errors
    # Readers that ran before the put may legitimately have seen None; nobody
    # may have seen the invalidated entry, and the cache now holds the fresh one.
    assert all(entry is None or entry is fresh for entry in seen), seen
    assert cache.get(workspace, "Risk") is fresh


def test_clear_is_a_consistent_reset() -> None:
    """``clear`` empties the whole cache (used by the invalidation seam)."""
    cache = _DefinitionCache()
    workspace = str(uuid.uuid4())
    for index in range(5):
        cache.put(workspace, f"Type{index}", _dto(workspace, f"Type{index}", index))
    assert len(cache._cache) == 5  # noqa: SLF001

    cache.clear()

    assert cache.get(workspace, "Type0") is None
    assert len(cache._cache) == 0  # noqa: SLF001
