"""L1-002 — concurrent trace-link writes must not both commit a cycle.

Both ``TraceLinkManager.create()`` (DFS) and ``batch_create()`` (Tarjan) decide
whether an edge closes a cycle from a graph snapshot. Under READ COMMITTED two
transactions used to be able to read the same acyclic snapshot — one about to
write A→B, the other B→A — pass both checks and commit a cycle. The fix takes
the tenant-scoped advisory lock in ``persistence.advisory_locks`` *before the
first read*, so the second writer observes the first writer's committed edge
and raises :class:`CycleDetectedError`.

The two worker threads each open their own connection. ``transaction=True`` is
mandatory: with the plain ``db`` fixture the whole test runs in one outer
transaction on the main connection, so the workers would neither see the
fixture rows nor contend on the advisory lock and the race would pass
vacuously. A ``threading.Barrier(2)`` sits *after the snapshot read* of the
leader (via a hook on ``_build_adjacency_from_edges``) and before the follower
starts its transaction. Pre-fix the follower then reads the same empty graph;
post-fix it blocks on the advisory lock until the leader commits and rejects
the edge.

This test is PostgreSQL-only: the advisory-lock helper is a no-op on other
vendors, so on SQLite both writers would commit and the race would pass
*vacuously* (false assurance). It is explicitly skipped there rather than
silently asserting nothing.
"""
from __future__ import annotations

import threading
import uuid
from unittest.mock import patch

import pytest
from django.db import close_old_connections, connection, transaction

import traceability.trace_link_manager as tlm
from persistence.models import Artifact, Tenant, TraceLink, Workspace
from persistence.tenancy import TenantContext
from traceability.exceptions import CycleDetectedError
from traceability.trace_link_manager import TraceLinkManager

_LINK_TYPE = "references"  # deliberate: not a hierarchy type (no second DFS)

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(
    not _IS_POSTGRES, reason="advisory locks are PostgreSQL-only (no-op elsewhere)"
)


@_pg_only
@pytest.mark.django_db(transaction=True)
def test_concurrent_reciprocal_links_produce_one_commit_and_no_cycle() -> None:
    """Two racing reciprocal links: one winner, one CycleDetectedError."""
    tenant_id = uuid.uuid4()
    TenantContext.set_tenant(tenant_id)
    try:
        tenant = Tenant.objects.create(
            id=tenant_id, name="L1-002 Tenant", slug="l1-002-tenant"
        )
        workspace = Workspace.objects.create(tenant=tenant, name="L1-002 WS")
        artifact_a = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="requirement"
        )
        artifact_b = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="requirement"
        )
    finally:
        TenantContext.clear_tenant()

    manager = TraceLinkManager()
    barrier = threading.Barrier(2, timeout=15)
    thread_local = threading.local()
    original_build = tlm._build_adjacency_from_edges

    def _snapshot_barrier(edges):
        adj = original_build(edges)  # materialises the snapshot read
        if getattr(thread_local, "race_leader", False):
            barrier.wait(timeout=15)  # AFTER the snapshot, BEFORE the decision
        return adj

    outcomes: dict[str, str] = {}
    outcomes_lock = threading.Lock()

    def _leader() -> None:
        close_old_connections()
        thread_local.race_leader = True
        try:
            TenantContext.set_tenant(tenant_id)
            with patch.object(
                tlm, "_build_adjacency_from_edges", _snapshot_barrier
            ):
                manager.create(artifact_a.id, artifact_b.id, _LINK_TYPE)
            result = "ok"
        except Exception as exc:  # noqa: BLE001 — diagnostic for the assertion
            result = f"error:{exc!r}"
        finally:
            with outcomes_lock:
                outcomes["leader"] = result
            TenantContext.clear_tenant()
            close_old_connections()

    def _follower() -> None:
        close_old_connections()
        try:
            TenantContext.set_tenant(tenant_id)
            barrier.wait(timeout=15)  # leader has taken its snapshot
            manager.create(artifact_b.id, artifact_a.id, _LINK_TYPE)
            result = "ok"
        except CycleDetectedError:
            result = "cycle"
        except Exception as exc:  # noqa: BLE001 — diagnostic for the assertion
            result = f"error:{exc!r}"
        finally:
            with outcomes_lock:
                outcomes["follower"] = result
            TenantContext.clear_tenant()
            close_old_connections()

    threads = [
        threading.Thread(target=_leader, name="l1-002-leader"),
        threading.Thread(target=_follower, name="l1-002-follower"),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not any(t.is_alive() for t in threads), (
        "worker thread did not finish in time"
    )
    assert set(outcomes) == {"leader", "follower"}, outcomes
    # The leader holds the lock first; the follower must reject the reciprocal
    # edge rather than committing it.
    assert outcomes == {"leader": "ok", "follower": "cycle"}, outcomes

    TenantContext.set_tenant(tenant_id)
    try:
        assert TraceLink.objects.count() == 1, (
            "exactly one edge may be committed — a second one closes the cycle"
        )
        assert manager.validate_graph_integrity() == {
            "valid": True,
            "cycle_path": None,
        }
    finally:
        TenantContext.clear_tenant()
