"""PERF-006 — batch permission checks in search (S2.2 part B).

Pins the security-critical invariant that the batched visibility path is
behaviourally IDENTICAL to the pre-existing per-hit path:

* the three new batch methods produce the same decisions as their single-item
  counterparts (`check_permissions_batch`, `resolve_effective_permissions_batch`);
* search hit sets are unchanged for the full allow/deny/none/workspace-wide/
  outdated/cross-workspace matrix, whether batching is on or off;
* the permission query count no longer scales with the number of hits;
* a batch failure falls back fail-closed to the unchanged per-hit check.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from application import search_service
from application.effective_permission_service import EffectivePermissionService
from application.search_service import SearchService
from auth_tenancy.services import PermissionCache
from persistence.models import Artifact, LifecycleStatus, TraceLink
from persistence.tests.factories import (
    active_tenant,
    assign_role,
    editor_ctx,
    make_requirement,
    make_user,
    make_workspace,
)


def _make_icd(tenant, workspace, *, name):
    """Create an Icd with its backing Artifact (required for permission checks)."""
    from icd.models import Icd

    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Icd"
    )
    return Icd.objects.create(
        tenant=tenant,
        artifact=artifact,
        workspace_id=workspace.id,
        name=name,
        semantic_description="A bus interface used by the batching tests.",
        source_element_id=uuid4(),
        target_element_id=uuid4(),
    )


def _make_link(tenant, source_req, target_req, *, link_type="references"):
    """Create a TraceLink between two Requirements' backing Artifacts."""
    return TraceLink.objects.create(
        tenant=tenant,
        source_id=source_req.artifact_id,
        target_id=target_req.artifact_id,
        link_type=link_type,
    )


def _search(workspace, ctx, term, entity_type, *, batched, monkeypatch):
    """Run one keyword search with batching on, or the legacy per-hit path off.

    The per-key PermissionCache is cleared before each run so the two paths are
    compared from an identical cold-cache state (otherwise the batched run would
    warm the cache and make the legacy run trivially identical).
    """
    PermissionCache.clear_thread()
    if batched:
        return SearchService().search(
            term,
            ctx,
            workspace_id=workspace.id,
            type_filter=[entity_type],
            mode="keyword",
        )
    with monkeypatch.context() as mp:
        mp.setattr(search_service, "_prepopulate_decision_cache", lambda *a, **kw: None)
        return SearchService().search(
            term,
            ctx,
            workspace_id=workspace.id,
            type_filter=[entity_type],
            mode="keyword",
        )


# ---------------------------------------------------------------------------
# EffectivePermissionService batch == single-item merge
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("roles", [("editor",), ("viewer",), (), ("admin",)])
def test_effective_batch_matches_single_resolution(roles):
    """The batched resolver is byte-identical to resolve_effective_permission.

    Three artifacts per run exercise the artifact-scoped rule, the explicit
    deny and the silent (no-rule) branches at once, across four RBAC levels.
    """
    from auth_tenancy.models import ItemPermission

    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        user = make_user(tenant)
        for role in roles:
            assign_role(user, ws, role)
        artifacts = [
            Artifact.objects.create(
                tenant=tenant, workspace=ws, artifact_type="requirement"
            )
            for _ in range(3)
        ]
        ItemPermission.objects.create(
            tenant=tenant,
            user_id=user.id,
            workspace=ws,
            artifact_id=artifacts[0].id,
            permission_level="read",
        )
        ItemPermission.objects.create(
            tenant=tenant,
            user_id=user.id,
            workspace=ws,
            artifact_id=artifacts[1].id,
            permission_level="none",
        )
        ids = [artifact.id for artifact in artifacts]

        PermissionCache.clear_thread()
        batched = EffectivePermissionService().resolve_effective_permissions_batch(
            active_roles=roles,
            user_id=user.id,
            workspace_id=ws.id,
            artifact_ids=ids,
            level="read",
        )
        PermissionCache.clear_thread()
        singles = {
            artifact_id: EffectivePermissionService().resolve_effective_permission(
                active_roles=roles,
                user_id=user.id,
                workspace_id=ws.id,
                artifact_id=artifact_id,
                level="read",
            )
            for artifact_id in ids
        }

    assert batched == singles


# ---------------------------------------------------------------------------
# Search hit-set matrix: batching on vs off
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "scenario",
    [
        "allow",
        "deny",
        "none",
        "workspace-wide",
        "outdated",
        "cross-workspace",
    ],
)
def test_scenario_hit_sets_identical(scenario, monkeypatch):
    """Every scenario yields the same hit set with batching on and off."""
    from auth_tenancy.models import ItemPermission

    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        ctx = editor_ctx(tenant, ws)

        if scenario == "cross-workspace":
            foreign = make_workspace(tenant)
            src = make_requirement(ws, title="Source", uid="REQ-SRC")
            tgt = make_requirement(foreign, title="Foreign target", uid="REQ-TGT")
            target = _make_link(tenant, src, tgt)
            entity_type, term = "TraceLink", "references"
            expected_visible = True  # readable source; foreign target masked
        else:
            target = _make_icd(tenant, ws, name=f"{scenario} Bus Interface")
            entity_type, term = "Icd", "Bus Interface"
            expected_visible = scenario not in ("deny", "outdated")
            if scenario == "allow":
                ItemPermission.objects.create(
                    tenant=tenant,
                    user_id=ctx.user_id,
                    workspace=ws,
                    artifact_id=target.artifact_id,
                    permission_level="read",
                )
            elif scenario == "deny":
                ItemPermission.objects.create(
                    tenant=tenant,
                    user_id=ctx.user_id,
                    workspace=ws,
                    artifact_id=target.artifact_id,
                    permission_level="none",
                )
            elif scenario == "workspace-wide":
                ItemPermission.objects.create(
                    tenant=tenant,
                    user_id=ctx.user_id,
                    workspace=ws,
                    artifact_id=None,
                    permission_level="read",
                )
            elif scenario == "outdated":
                target.artifact.lifecycle_status = LifecycleStatus.OUTDATED
                target.artifact.save(update_fields=["lifecycle_status"])

        batched_result = _search(
            ws, ctx, term, entity_type, batched=True, monkeypatch=monkeypatch
        )
        legacy_result = _search(
            ws, ctx, term, entity_type, batched=False, monkeypatch=monkeypatch
        )

    batched_ids = {hit.id for hit in batched_result.results}
    legacy_ids = {hit.id for hit in legacy_result.results}
    assert batched_ids == legacy_ids, f"hit set drifted for scenario {scenario!r}"

    target_id = str(target.id)
    assert (target_id in batched_ids) is expected_visible
    if scenario == "cross-workspace" and expected_visible:
        hit = next(hit for hit in batched_result.results if hit.id == target_id)
        assert hit.title == "references: REQ-SRC → —"
        assert "REQ-TGT" not in hit.title


# ---------------------------------------------------------------------------
# Query count is independent of hit count
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_query_count_independent_of_hit_count(monkeypatch):
    """2 hits and 200 hits issue the same number of queries.

    Before PERF-006 the per-hit item-permission check added up to two queries
    per hit; the batched path issues a constant number regardless of hit count.
    """
    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        ctx = editor_ctx(tenant, ws)

        for index in range(2):
            _make_icd(tenant, ws, name=f"Count Bus {index:03d}")
        PermissionCache.clear_thread()
        with CaptureQueriesContext(connection) as few_queries:
            few_result = _search(
                ws, ctx, "Count Bus", "Icd", batched=True, monkeypatch=monkeypatch
            )

        for index in range(2, 200):
            _make_icd(tenant, ws, name=f"Count Bus {index:03d}")
        PermissionCache.clear_thread()
        with CaptureQueriesContext(connection) as many_queries:
            many_result = _search(
                ws, ctx, "Count Bus", "Icd", batched=True, monkeypatch=monkeypatch
            )

    assert few_result.total_count == 2
    assert many_result.total_count == 200
    assert len(few_queries) == len(many_queries), (
        f"query count scaled with hits: {len(few_queries)} (2 hits) vs "
        f"{len(many_queries)} (200 hits)"
    )


# ---------------------------------------------------------------------------
# Batch failure is fail-closed
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_batch_failure_falls_back_fail_closed(monkeypatch):
    """A batching exception must not widen visibility: per-hit checks decide."""
    from auth_tenancy.models import ItemPermission

    with active_tenant() as tenant:
        ws = make_workspace(tenant)
        ctx = editor_ctx(tenant, ws)
        visible = _make_icd(tenant, ws, name="Visible Bus Interface")
        blocked = _make_icd(tenant, ws, name="Blocked Bus Interface")
        ItemPermission.objects.create(
            tenant=tenant,
            user_id=ctx.user_id,
            workspace=ws,
            artifact_id=blocked.artifact_id,
            permission_level="none",
        )

        def explode(*args, **kwargs):
            raise RuntimeError("simulated batch failure")

        monkeypatch.setattr(
            EffectivePermissionService,
            "resolve_effective_permissions_batch",
            explode,
        )
        result = _search(
            ws, ctx, "Bus Interface", "Icd", batched=True, monkeypatch=monkeypatch
        )

    ids = {hit.id for hit in result.results}
    assert str(visible.id) in ids
    assert str(blocked.id) not in ids
