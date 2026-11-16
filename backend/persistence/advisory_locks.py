"""Layer-0 advisory-lock helpers for tenant-scoped critical sections.

PostgreSQL transaction-scoped advisory locks (``pg_advisory_xact_lock``) are the
Layer-0 primitive for serialising an operation that cannot be expressed as a
single row/constraint check — e.g. "read the whole tenant graph, decide whether
an edge would close a cycle, then write the edge". The lock is released by
PostgreSQL when the enclosing transaction commits or rolls back; it must
therefore be acquired **inside** an open ``transaction.atomic()`` block. Outside
a transaction the SQL is legal but the lock is dropped at the end of the
statement, which would silently reintroduce the race (the same trap documented
for ``SELECT ... FOR UPDATE`` in ``workflow.lifecycle_manager``).

Vendor guard: on non-PostgreSQL vendors there is no advisory-lock primitive, so
the helper is a no-op. Callers keep their pre-existing best-effort behaviour;
no behaviour is silently changed on those vendors.

Lock ordering (trace-graph advisory lock vs. workflow row lock)
---------------------------------------------------------------
The workflow state machine takes a fine-grained row lock via
``StateLifecycleManager.lock_item_state`` (``SELECT ... FOR UPDATE`` on
``WorkflowItemState``). When a single operation needs both locks, the order is
always:

1. tenant-scoped advisory lock (coarse, acquired first);
2. workflow ``WorkflowItemState`` row lock (fine, acquired second).

Never acquire a workflow row lock and then wait for the tenant advisory lock:
that is the inverse order and can deadlock against a graph write that already
holds the advisory lock and is waiting for the same row. Trace-link writes only
need step 1; the ordering contract exists for callers that compose the two.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from django.db import connection

#: Byte-identical to the statement ``application.import_idempotency`` uses in
#: its **own** copy (line ~108) — that call site has NOT been migrated to this
#: helper yet. Keeping the SQL byte-identical means extracting it later will not
#: change which key an existing caller hashes. This module is the Layer-0 home
#: for new callers (ADR-01: no Layer-1 module imports from ``application``).
ADVISORY_XACT_LOCK_SQL = "SELECT pg_advisory_xact_lock(hashtext(%s))"

#: Namespace for the trace-link graph mutation lock. Because the advisory key is
#: a 32-bit hash, a namespace keeps graph writes from contending with unrelated
#: tenant-scoped critical sections (and makes the lock's purpose explicit in
#: diagnostics).
TRACE_GRAPH_NAMESPACE = "trace-graph"


def _lock_key(tenant_id: uuid.UUID | str, namespace: str | None) -> str:
    """Return the string hashed into PostgreSQL's advisory-lock key space.

    Args:
        tenant_id: Active tenant primary key (UUID or its string form).
        namespace: Optional logical lock family. When omitted the bare tenant
            id is used, preserving the key used by the pre-extraction call site.

    Returns:
        The string passed as the ``hashtext`` argument.
    """
    tenant_key = str(tenant_id)
    return f"{namespace}:{tenant_key}" if namespace else tenant_key


def acquire_tenant_advisory_lock(
    tenant_id: uuid.UUID | str, *, namespace: str | None = None
) -> None:
    """Acquire a transaction-scoped advisory lock keyed to *tenant_id*.

    Must be called inside an open ``transaction.atomic()`` block on PostgreSQL;
    the lock is held until that transaction ends. On non-PostgreSQL vendors the
    call is a no-op (see the module docstring).

    Args:
        tenant_id: Active tenant primary key. A hash collision between two
            tenants only over-serialises them; it can never leak a lock.
        namespace: Optional logical lock family. Omit it to preserve the key of
            the legacy ``application.import_idempotency`` call site.
    """
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute(ADVISORY_XACT_LOCK_SQL, [_lock_key(tenant_id, namespace)])


@contextmanager
def tenant_graph_lock(tenant_id: uuid.UUID | str) -> Iterator[None]:
    """Serialise a tenant's trace-graph mutations (L1-002).

    **Precondition:** an open ``transaction.atomic()`` block must already be
    active on the calling thread (either an explicit ``with transaction.atomic()``
    around this context manager, or a ``@transaction.atomic`` decorator on the
    caller). ``pg_advisory_xact_lock`` is transaction-scoped: without that
    enclosing transaction PostgreSQL drops the lock at the end of the lock
    statement itself, silently reintroducing the read-decide-write race. This
    context manager does **not** open a transaction on the caller's behalf::

        with transaction.atomic():
            with tenant_graph_lock(tenant_id):
                ...  # read graph, check cycles, write edge

    Usage inside a method already decorated with ``@transaction.atomic`` is
    equivalent; the lock then lives until that method's transaction commits.

    Args:
        tenant_id: Active tenant primary key.
    """
    acquire_tenant_advisory_lock(tenant_id, namespace=TRACE_GRAPH_NAMESPACE)
    yield


__all__ = [
    "ADVISORY_XACT_LOCK_SQL",
    "TRACE_GRAPH_NAMESPACE",
    "acquire_tenant_advisory_lock",
    "tenant_graph_lock",
]
