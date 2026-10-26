"""G2.2 (#1400): the requirement list query uses ``idx_req_ws_created``.

Measured, not assumed: the test seeds 20,000 requirements across five
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

_PER_WORKSPACE = 4_000


def _seed(tenant, workspace) -> list[Workspace]:
    """Five workspaces with 4,000 requirements each; returns them."""
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
        for ws in workspaces:
            artifacts = [
                Artifact(
                    tenant=tenant,
                    workspace=ws,
                    artifact_type="Requirement",
                )
                for _ in range(_PER_WORKSPACE)
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
        node.get("Index Name") == "idx_req_ws_created" for node in nodes
    ), (
        "the requirement list must be served by idx_req_ws_created; "
        f"plan={json.dumps(plan)[:2_000]}"
    )
    assert not any(
        node.get("Node Type") == "Seq Scan"
        and node.get("Relation Name") == "pl_requirement"
        for node in nodes
    ), "a sequential scan of pl_requirement means the index was bypassed"


def test_null_workspace_rows_absent(tenant, workspace):
    _seed(tenant, workspace)

    set_request_tenant(tenant.id)
    try:
        assert Requirement.objects.filter(workspace__isnull=True).count() == 0
    finally:
        clear_request_tenant()
