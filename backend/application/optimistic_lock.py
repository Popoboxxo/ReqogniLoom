"""Reusable optimistic-locking primitives for versioned domain entities.

Every entity inheriting :class:`persistence.models.AuditableModel` (plus the
``application.models`` entities that carry their own ``version`` column) is
guarded by a pure optimistic-concurrency counter. Until SYSTEMAUDIT_2026-08-29
(REST finding 1) the ``expected_version`` / 409 contract was implemented in
exactly one place — ``ArchitectureService.update_architecture_element`` — so a
client that had read version ``N``, gone stale, and PATCHed a Requirement, ADR,
Risk, Issue, TestCase, StakeholderNeed, ChangeRequest or GlossaryTerm silently
overwrote whatever version ``N+k`` another session had written. The REST layer
even *accepted* ``expected_version`` on all of them
(``_ALWAYS_ALLOWED_PATCH_FIELDS``) and then dropped it on the floor, which is
worse than not supporting it at all: the client believes it is protected.

This module extracts that reference implementation into the two primitives the
services need, so a versioned ``update_*`` gains the guarantee in three lines::

    qs = Adr.objects.filter(id=adr_id, tenant_id=ctx.tenant_id)
    adr = lock_for_version_check(qs, expected_version).first()
    if adr is None:
        raise NotFoundError(f"ADR {adr_id} not found")
    assert_expected_version(adr, expected_version, entity_type="Adr")

Why two primitives instead of one "load and check" helper: the NotFoundError
message is part of each service's published contract (and asserted in its
tests), and the querysets differ (``select_related``, tenant filters). Keeping
the load in the service preserves both while still sharing the two parts that
actually carry the locking semantics.

Layering note (ADR-01): these are Layer-2 helpers. The REST and MCP boundaries
never perform the version compare themselves — they only forward the
client-supplied ``expected_version`` into the service, so both surfaces (and any
future one) inherit the same behaviour and the check always runs inside the
service's transaction.
"""
from __future__ import annotations

from typing import Any, TypeVar

from application.base import OptimisticLockError

__all__ = ["assert_expected_version", "lock_for_version_check"]

_QS = TypeVar("_QS")


def lock_for_version_check(queryset: _QS, expected_version: int | None) -> _QS:
    """Return *queryset*, row-locked when an optimistic-lock check will follow.

    ``SELECT ... FOR UPDATE`` is applied **only** when the caller supplied an
    ``expected_version``. That conditionality is the whole point:

    * With a lock, the version compare that follows is authoritative for the
      rest of the enclosing ``@atomic_transaction``. Without it, the compare
      would be a plain read-then-write with a window in between — a concurrent
      writer could commit its own bump after our SELECT and before our UPDATE,
      and the guarded request would still overwrite it. That is exactly the
      lost update the caller asked us to prevent, so answering "no conflict"
      there would be a false guarantee.
    * Requests that do *not* ask for the guarantee keep the unlocked read, so
      the lock is never taken on the (dominant) unguarded path and the change
      cannot introduce contention for callers that did not opt in.

    A service that already persists through a checked compare-and-swap
    (``UPDATE ... WHERE version = <current>`` whose row count is asserted, as
    ``ArchitectureService.update_architecture_element`` does) does **not** need
    this — it detects the conflict at write time. The services that persist a
    full row via ``save()`` overwrite a concurrent bump before any such check
    could run, which is why they take the lock instead.

    Requires an open transaction, which every versioned ``update_*`` already
    has via ``@atomic_transaction`` / ``@transaction.atomic``.

    ``of=("self",)`` restricts the lock to the entity's own row. Several call
    sites load through ``select_related("artifact")``; a bare
    ``select_for_update()`` would try to lock the joined rows too, which both
    widens the lock beyond what the version check needs and raises
    ``FieldError`` on the nullable side of an outer join.

    Args:
        queryset: The queryset that will load the single row to be updated.
        expected_version: The caller's last-seen version, or ``None``.

    Returns:
        The same queryset, with ``select_for_update(of=("self",))`` applied when
        *expected_version* is not ``None``.
    """
    if expected_version is None:
        return queryset
    return queryset.select_for_update(of=("self",))


def assert_expected_version(
    instance: Any, expected_version: int | None, *, entity_type: str
) -> None:
    """Raise :class:`OptimisticLockError` if *instance* is not at the expected version.

    A ``None`` *expected_version* means "caller does not track versions" and
    skips the check — the backwards-compatible path that the reference
    implementation (``ArchitectureService.update_architecture_element``) has
    always had, and the reason adding this guard to an existing service is not
    a breaking change for existing clients.

    ``OptimisticLockError`` is mapped to ``409 CONFLICT`` by
    ``rest_api.views._service_error_response``. On the MCP side it surfaces as a
    ``VALIDATION_ERROR`` tool error prefixed ``"Version conflict: "`` (see
    ``mcp_server.tools.generic._handle_update`` and
    ``mcp_server.tools.architecture``) — JSON-RPC tool errors have no
    ``CONFLICT`` code. Either way no call site needs its own translation.

    Args:
        instance: The freshly loaded ORM row (ideally obtained through
            :func:`lock_for_version_check`).
        expected_version: The caller's last-seen version, or ``None`` to skip.
        entity_type: Entity name used in the error message, e.g. ``"Adr"``.

    Raises:
        OptimisticLockError: The stored version differs from *expected_version*.
    """
    if expected_version is None:
        return
    current = getattr(instance, "version", None)
    if current == expected_version:
        return
    raise OptimisticLockError(
        f"Stale version for {entity_type} {getattr(instance, 'pk', '?')}: "
        f"expected {expected_version}, current is {current}"
    )
