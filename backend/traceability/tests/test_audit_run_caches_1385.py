"""#1385 — the two run-scoped caches behind the SE-Auditor's query reduction.

``AuditService.run_audit`` used to issue one full-tenant ``pl_tracelink`` scan
per ``AuditContext.iter_trace_links()`` call site and one remediation candidate
lookup per finding. Both are now memoised, and both memos have a hard lifetime:
one audit context / one audit run. These tests pin exactly that lifetime —
a cache with a wider scope would serve stale workspace state and silently
change audit results.

Covered here:

* :meth:`AuditContext.iter_trace_links` reads the tenant's links once and
  replays them, while still honouring ``include_proposal_links`` (the cache
  must not collapse the two different filters into one entry);
* :meth:`AuditContext.memoize` is per context, not per process;
* :func:`traceability.audit.remediation.remediation_run_cache` serves the
  candidate lookup from one query inside the block, re-queries outside it, and
  never answers for another workspace.
"""
from __future__ import annotations

import pytest
from django.utils import timezone

from persistence.models import ArchitectureElement, TraceLink
from persistence.tests.factories import make_workspace
from traceability.audit.remediation import (
    _architecture_artifact_ids,
    remediation_run_cache,
)
from traceability.audit.types import AuditContext
from traceability.tests.conftest import active_tenant, make_artifact

pytestmark = pytest.mark.django_db


def _context(tenant, workspace, *, include_proposal_links: bool = True) -> AuditContext:
    return AuditContext(
        tier="extended",
        workspace_id=str(workspace.id),
        tenant_id=str(tenant.id),
        include_proposal_links=include_proposal_links,
    )


def _link(tenant, source, target, *, proposed: bool) -> TraceLink:
    return TraceLink.objects.create(
        tenant=tenant,
        source=source,
        target=target,
        link_type="derives-from",
        proposed_at=timezone.now() if proposed else None,
    )


# ---------------------------------------------------------------------------
# Trace-link snapshot
# ---------------------------------------------------------------------------


def test_iter_trace_links_queries_once_per_context(
    django_assert_max_num_queries, tenant_a, workspace_a
):
    """Eleven call sites in one run must not mean eleven table scans."""
    with active_tenant(tenant_a):
        a1 = make_artifact(tenant_a, workspace_a, artifact_type="Requirement")
        a2 = make_artifact(tenant_a, workspace_a, artifact_type="Requirement")
        _link(tenant_a, a1, a2, proposed=False)

        context = _context(tenant_a, workspace_a)
        with django_assert_max_num_queries(1):
            first = list(context.iter_trace_links())
            second = list(context.iter_trace_links())

    assert len(first) == 1
    assert second == first


def test_iter_trace_links_snapshot_honours_the_proposal_flag(tenant_a, workspace_a):
    """A cached snapshot must not leak proposals into a confirmed-state run."""
    with active_tenant(tenant_a):
        a1 = make_artifact(tenant_a, workspace_a, artifact_type="Requirement")
        a2 = make_artifact(tenant_a, workspace_a, artifact_type="Requirement")
        a3 = make_artifact(tenant_a, workspace_a, artifact_type="Requirement")
        _link(tenant_a, a1, a2, proposed=False)
        _link(tenant_a, a2, a3, proposed=True)

        with_proposals = list(_context(tenant_a, workspace_a).iter_trace_links())
        confirmed_only = list(
            _context(tenant_a, workspace_a, include_proposal_links=False).iter_trace_links()
        )

    assert len(with_proposals) == 2
    assert len(confirmed_only) == 1


def test_memoize_is_scoped_to_one_context(tenant_a, workspace_a):
    """Two contexts of one run must not share the memo (scope differs)."""
    calls: list[int] = []

    def factory() -> list[int]:
        calls.append(1)
        return [len(calls)]

    with active_tenant(tenant_a):
        first = _context(tenant_a, workspace_a)
        assert first.memoize("probe", factory) == [1]
        assert first.memoize("probe", factory) == [1]
        second = _context(tenant_a, workspace_a)
        # A fresh context re-invokes the factory (one memo per context, not
        # one per process).
        assert second.memoize("probe", factory) == [2]


# ---------------------------------------------------------------------------
# Remediation candidate memo
# ---------------------------------------------------------------------------


def test_candidate_lookup_is_memoised_inside_one_run(
    django_assert_max_num_queries, tenant_a, workspace_a
):
    """One audit run pays for the candidate search once, not once per finding."""
    with active_tenant(tenant_a):
        artifact = make_artifact(tenant_a, workspace_a, artifact_type="ArchitectureElement")
        ArchitectureElement.objects.create(
            tenant=tenant_a, artifact=artifact, title="Only Element"
        )

        with django_assert_max_num_queries(1):
            with remediation_run_cache(tenant_a.id, workspace_a.id):
                first = _architecture_artifact_ids(tenant_a.id, workspace_a.id)
                second = _architecture_artifact_ids(tenant_a.id, workspace_a.id)

        # Outside the run the next caller queries again — no process-wide value.
        with django_assert_max_num_queries(1):
            third = _architecture_artifact_ids(tenant_a.id, workspace_a.id)

    assert first == second == third == frozenset({str(artifact.id)})


def test_candidate_cache_is_per_workspace_and_restores_the_outer_run(
    django_assert_max_num_queries, tenant_a, workspace_a
):
    """A memo for one workspace must never be served to a second one.

    ``AuditService`` opens the cache around one workspace's run, but a caller
    may nest runs (e.g. a service that audits two workspaces back to back). The
    second workspace must get its own candidates, and leaving the nested run
    must restore the outer one rather than dropping it.
    """
    with active_tenant(tenant_a):
        workspace_2 = make_workspace(tenant_a, name="WS-1385-second")
        element_a = make_artifact(tenant_a, workspace_a, artifact_type="ArchitectureElement")
        ArchitectureElement.objects.create(
            tenant=tenant_a, artifact=element_a, title="Element A"
        )
        element_b = make_artifact(tenant_a, workspace_2, artifact_type="ArchitectureElement")
        ArchitectureElement.objects.create(
            tenant=tenant_a, artifact=element_b, title="Element B"
        )

        with remediation_run_cache(tenant_a.id, workspace_a.id):
            assert _architecture_artifact_ids(tenant_a.id, workspace_a.id) == frozenset(
                {str(element_a.id)}
            )
            # A nested run for another workspace must not reuse A's answer.
            with django_assert_max_num_queries(1):
                with remediation_run_cache(tenant_a.id, workspace_2.id):
                    assert _architecture_artifact_ids(
                        tenant_a.id, workspace_2.id
                    ) == frozenset({str(element_b.id)})
            # ... and the outer run's memo is still in place afterwards.
            with django_assert_max_num_queries(0):
                assert _architecture_artifact_ids(
                    tenant_a.id, workspace_a.id
                ) == frozenset({str(element_a.id)})
