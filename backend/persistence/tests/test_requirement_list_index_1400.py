"""G2.2 (#1400) / P1: the requirement list query is index-served.

The list filters ``pl_requirement`` by workspace and orders by
``pl_artifact.sort_key COLLATE "C" NULLS LAST, created_at, id``. Since P1 that
mixed order cannot be served by ``idx_req_ws_created`` (workspace, created_at,
id) — the old index is still useful for workspace filtering, but the first sort
key now lives on the joined ``pl_artifact`` row. The plan therefore walks
``idx_artifact_sort_id`` (sort_key, id) in sort_key order, nested-loops into
``pl_requirement`` by its unique ``artifact_id`` and stops at LIMIT. Only the
ties inside one sort key need an ``Incremental Sort``; neither table is scanned
sequentially.

The corpus models a *large* workspace: 20,000 requirements in the queried
workspace plus four sibling workspaces with a handful of rows. That matters —
the planner only prefers the ordered index walk when the workspace's rows
dominate the artifact table, so the LIMIT can stop after ~100 nested-loop
lookups. With five equally sized workspaces PostgreSQL measured the opposite:
the soft-delete ``NOT IN`` sub-plan's startup cost is charged to every inner
index access, which made the ordered path's LIMIT cost ~8x the hash-join +
sort of one workspace's 4,000 rows. Both plans are correct; this test pins the
case the index exists for, and the second assertion pins the original #1400
ratchet (neither table is ever scanned sequentially).

Measured, not assumed: the test seeds 20,040 requirements across five
workspaces, refreshes the planner statistics, and explains the exact SQL
``RequirementService.list_requirements(...)[:100]`` produces.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from django.db import connection

from application.requirement_service import RequirementService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Workspace

pytestmark = pytest.mark.django_db

#: The queried workspace holds the large list the ordering index protects.
_TARGET_ROWS = 20_000
#: Sibling workspaces prove the filter is workspace-scoped, not a full table.
_SIBLING_ROWS = 10


def _seed(tenant, workspace) -> list[Workspace]:
    """One large workspace plus four siblings; returns all of them."""
    set_request_tenant(tenant.id)
    try:
        workspaces = [workspace]
        for index in range(1, 5):
            workspaces.append(
                Workspace.objects.create(
                    tenant=tenant,
                    name=f"G2.2 workspace {index}",
                    preset={"name": "standard"},
                )
            )
        for ws_index, ws in enumerate(workspaces):
            count = _TARGET_ROWS if ws_index == 0 else _SIBLING_ROWS
            # P1: the 0132 backfill gives every Requirement a fractional
            # ``sort_key``; distinct keys make the ordered walk stop at LIMIT
            # instead of sorting one giant NULL tie group.
            artifacts = [
                Artifact(
                    tenant=tenant,
                    workspace=ws,
                    artifact_type="Requirement",
                    sort_key=f"{index:018d}{ws_index:02d}",
                )
                for index in range(count)
            ]
            Artifact.objects.bulk_create(artifacts, batch_size=2_000)
            requirements = [
                Requirement(
                    tenant=tenant,
                    artifact=artifact,
                    workspace=ws,
                    title=f"G2.2 {ws.name} {index:04d}",
                )
                for index, artifact in enumerate(artifacts)
            ]
            Requirement.objects.bulk_create(requirements, batch_size=2_000)
        return workspaces
    finally:
        clear_request_tenant()


def _plan_for_list(workspace_id, tenant_id) -> dict:
    ctx = SimpleNamespace(tenant_id=tenant_id)
    queryset = RequirementService().list_requirements(
        workspace_id=workspace_id, ctx=ctx
    )[:100]
    sql, params = queryset.query.sql_with_params()
    with connection.cursor() as cursor:
        cursor.execute("EXPLAIN (FORMAT JSON) " + sql, params)
        plan = cursor.fetchone()[0]
    return plan[0]["Plan"] if isinstance(plan, list) else plan["Plan"]


def _walk(node):
    yield node
    for child in node.get("Plans", []):
        yield from _walk(child)


def test_list_query_uses_index(tenant, workspace):
    workspaces = _seed(tenant, workspace)

    with connection.cursor() as cursor:
        cursor.execute("ANALYZE pl_requirement")
        cursor.execute("ANALYZE pl_artifact")

    plan = _plan_for_list(workspaces[0].id, tenant.id)
    nodes = list(_walk(plan))

    assert any(
        node.get("Index Name") == "idx_artifact_sort_id" for node in nodes
    ), (
        "the requirement list must be served by idx_artifact_sort_id "
        "(ordering by pl_artifact.sort_key); "
        f"plan={json.dumps(plan)[:2_000]}"
    )
    seq_scans = [
        node.get("Relation Name")
        for node in nodes
        if node.get("Node Type") == "Seq Scan"
        and node.get("Relation Name") in {"pl_requirement", "pl_artifact"}
    ]
    assert seq_scans == [], (
        "a sequential scan of pl_requirement/pl_artifact means the ordering "
        f"index was bypassed: {seq_scans}; plan={json.dumps(plan)[:2_000]}"
    )


def test_null_workspace_rows_absent(tenant, workspace):
    _seed(tenant, workspace)

    set_request_tenant(tenant.id)
    try:
        assert Requirement.objects.filter(workspace__isnull=True).count() == 0
    finally:
        clear_request_tenant()
