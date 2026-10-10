"""REST-level coverage for the trace-graph read endpoints (views.py).

leaf_id : COMP-RA-TL (TraceLinkViewSet), COMP-RA-TR (TraceabilityViewSet)
req_id  : REQ-L2-TE-019

Two ViewSets expose the same recursive-CTE read model:

  * ``TraceLinkViewSet.impact/path/cycles`` under ``/api/v1/tracelinks/``
    (kept for backward compatibility), plus ``confirm``/``discard`` for
    agent-proposed links and the pgvector-backed ``similar``.
  * ``TraceabilityViewSet`` as the dedicated ``/api/v1/traceability/``
    namespace, with the extra ``resolve`` batch endpoint.

Both were almost entirely untested at HTTP level — the validation guards
(direction, max_depth cap, batch limit) and the tenant-scoping of the graph
queries are only reachable through the full middleware stack.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Tenant, TraceLink, User, Workspace
from traceability.types import LinkType

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"
_LINK = LinkType.ALLOCATED_TO.value


def _scenario() -> tuple[Tenant, User, Workspace]:
    """Create a tenant, one admin user and one Extended-preset workspace."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"T-{suffix}", slug=f"tg-{suffix}", is_active=True)
    user = User.objects.create(
        username=f"tg-{suffix}", email=f"tg-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="TG WS", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()
    return tenant, user, workspace


def _client(user: User) -> APIClient:
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client


def _artifact(tenant: Tenant, workspace: Workspace) -> Artifact:
    """Create a bare Artifact row (the trace graph is keyed by Artifact id)."""
    set_request_tenant(tenant.id)
    try:
        return Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
    finally:
        clear_request_tenant()


def _requirement_artifact(tenant: Tenant, workspace: Workspace) -> Artifact:
    """Create an Artifact backed by a Requirement row (for ``resolve``)."""
    set_request_tenant(tenant.id)
    try:
        art = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        Requirement.objects.create(tenant=tenant, artifact=art, title="TG requirement")
        return art
    finally:
        clear_request_tenant()


def _link(tenant: Tenant, source: Artifact, target: Artifact) -> TraceLink:
    set_request_tenant(tenant.id)
    try:
        return TraceLink.objects.create(
            tenant=tenant, source=source, target=target, link_type=_LINK
        )
    finally:
        clear_request_tenant()


@pytest.fixture
def graph() -> tuple[Tenant, User, Workspace, list[Artifact]]:
    """A workspace holding a chain ``a -> b -> c`` of three artifacts."""
    tenant, user, workspace = _scenario()
    artifacts = [_artifact(tenant, workspace) for _ in range(3)]
    _link(tenant, artifacts[0], artifacts[1])
    _link(tenant, artifacts[1], artifacts[2])
    return tenant, user, workspace, artifacts


# ---------------------------------------------------------------------------
# /tracelinks/impact/
# ---------------------------------------------------------------------------


def test_impact_requires_artifact_id(graph) -> None:
    _, user, _, _ = graph
    resp = _client(user).get("/api/v1/tracelinks/impact/")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "artifact_id is required"


def test_impact_rejects_unknown_direction(graph) -> None:
    _, user, _, artifacts = graph
    resp = _client(user).get(
        f"/api/v1/tracelinks/impact/?artifact_id={artifacts[0].id}&direction=sideways"
    )
    assert resp.status_code == 400, resp.content
    assert "direction must be" in resp.json()["error"]["message"]


def test_impact_rejects_non_integer_max_depth(graph) -> None:
    _, user, _, artifacts = graph
    resp = _client(user).get(
        f"/api/v1/tracelinks/impact/?artifact_id={artifacts[0].id}&max_depth=deep"
    )
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "max_depth and limit must be integers"


def test_impact_rejects_max_depth_above_cap(graph) -> None:
    _, user, _, artifacts = graph
    resp = _client(user).get(
        f"/api/v1/tracelinks/impact/?artifact_id={artifacts[0].id}&max_depth=21"
    )
    assert resp.status_code == 400, resp.content
    assert "max_depth must be <=" in resp.json()["error"]["message"]


def test_impact_returns_the_reachable_chain(graph) -> None:
    _, user, _, artifacts = graph
    resp = _client(user).get(f"/api/v1/tracelinks/impact/?artifact_id={artifacts[0].id}")

    assert resp.status_code == 200, resp.content
    nodes = resp.json()
    assert isinstance(nodes, list)
    assert len(nodes) == 2, f"expected b and c, got {nodes}"
    reachable = {n["artifact_id"] for n in nodes}
    assert reachable == {str(artifacts[1].id), str(artifacts[2].id)}


def test_impact_accepts_incoming_direction_and_link_type_filter(graph) -> None:
    _, user, _, artifacts = graph
    resp = _client(user).get(
        f"/api/v1/tracelinks/impact/?artifact_id={artifacts[1].id}"
        f"&direction=incoming&link_types={_LINK}"
    )

    assert resp.status_code == 200, resp.content
    assert [n["artifact_id"] for n in resp.json()] == [str(artifacts[0].id)]


def test_impact_unknown_artifact_maps_to_404(graph) -> None:
    _, user, _, _ = graph
    resp = _client(user).get(f"/api/v1/tracelinks/impact/?artifact_id={uuid.uuid4()}")
    assert resp.status_code == 404, resp.content
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_impact_of_foreign_tenant_artifact_is_not_readable(graph) -> None:
    """Cross-tenant isolation: another tenant's artifact must not resolve."""
    _, user, _, _ = graph
    other_tenant, _, other_ws = _scenario()
    foreign = _artifact(other_tenant, other_ws)

    resp = _client(user).get(f"/api/v1/tracelinks/impact/?artifact_id={foreign.id}")

    assert resp.status_code == 404, resp.content
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_impact_without_token_returns_401() -> None:
    assert APIClient().get("/api/v1/tracelinks/impact/").status_code == 401


# ---------------------------------------------------------------------------
# /tracelinks/path/
# ---------------------------------------------------------------------------


def test_path_requires_both_ids(graph) -> None:
    _, user, _, artifacts = graph
    resp = _client(user).get(f"/api/v1/tracelinks/path/?source_id={artifacts[0].id}")
    assert resp.status_code == 400, resp.content
    assert "source_id and target_id are required" in resp.json()["error"]["message"]


def test_path_rejects_non_integer_max_depth(graph) -> None:
    _, user, _, artifacts = graph
    resp = _client(user).get(
        f"/api/v1/tracelinks/path/?source_id={artifacts[0].id}"
        f"&target_id={artifacts[2].id}&max_depth=lots"
    )
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "max_depth must be an integer"


def test_path_rejects_max_depth_above_cap(graph) -> None:
    _, user, _, artifacts = graph
    resp = _client(user).get(
        f"/api/v1/tracelinks/path/?source_id={artifacts[0].id}"
        f"&target_id={artifacts[2].id}&max_depth=99"
    )
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_path_returns_the_shortest_path(graph) -> None:
    _, user, _, artifacts = graph
    resp = _client(user).get(
        f"/api/v1/tracelinks/path/?source_id={artifacts[0].id}&target_id={artifacts[2].id}"
    )

    assert resp.status_code == 200, resp.content
    paths = resp.json()
    assert len(paths) == 1
    assert paths[0]["nodes"] == [
        str(artifacts[0].id),
        str(artifacts[1].id),
        str(artifacts[2].id),
    ]
    assert paths[0]["length"] == 2, "length counts the hops between three nodes"


def test_path_without_connection_returns_404(graph) -> None:
    """An unreachable target is a routing miss, exactly like an unknown one.

    ``find_path`` resolves both endpoints first, so an isolated artifact of the
    same tenant produces the same 404 contract a caller relies on: never a
    fabricated "no path" for an id it cannot see.
    """
    tenant, user, _, artifacts = graph
    isolated = _artifact(tenant, graph[2])

    resp = _client(user).get(
        f"/api/v1/tracelinks/path/?source_id={isolated.id}&target_id={artifacts[0].id}"
    )

    assert resp.status_code == 404, resp.content
    assert resp.json()["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# /tracelinks/cycles/
# ---------------------------------------------------------------------------


def test_cycles_requires_workspace_id(graph) -> None:
    _, user, _, _ = graph
    resp = _client(user).get("/api/v1/tracelinks/cycles/")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_cycles_rejects_malformed_workspace_id(graph) -> None:
    _, user, _, _ = graph
    resp = _client(user).get("/api/v1/tracelinks/cycles/?workspace_id=not-a-uuid")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_cycles_returns_empty_count_for_an_acyclic_graph(graph) -> None:
    _, user, _, _ = graph
    workspace = graph[2]
    resp = _client(user).get(f"/api/v1/tracelinks/cycles/?workspace_id={workspace.id}")

    assert resp.status_code == 200, resp.content
    assert resp.json() == {"cycles": [], "count": 0}


def test_cycles_detects_a_back_reference(graph) -> None:
    tenant, user, workspace, artifacts = graph
    _link(tenant, artifacts[2], artifacts[0])

    resp = _client(user).get(f"/api/v1/tracelinks/cycles/?workspace_id={workspace.id}")

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["count"] >= 1, f"expected at least one cycle, got {body}"
    assert body["count"] == len(body["cycles"])


def test_cycles_without_token_returns_401() -> None:
    assert APIClient().get("/api/v1/tracelinks/cycles/").status_code == 401


# ---------------------------------------------------------------------------
# /traceability/ — the dedicated namespace
# ---------------------------------------------------------------------------


def test_traceability_impact_mirrors_the_tracelink_action(graph) -> None:
    _, user, _, artifacts = graph
    resp = _client(user).get(f"/api/v1/traceability/impact/?artifact_id={artifacts[0].id}")

    assert resp.status_code == 200, resp.content
    assert {n["artifact_id"] for n in resp.json()} == {
        str(artifacts[1].id),
        str(artifacts[2].id),
    }


def test_traceability_impact_requires_artifact_id(graph) -> None:
    _, user, _, _ = graph
    resp = _client(user).get("/api/v1/traceability/impact/")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "artifact_id is required"


def test_traceability_path_requires_both_ids(graph) -> None:
    _, user, _, _ = graph
    resp = _client(user).get("/api/v1/traceability/path/?source_id=" + str(uuid.uuid4()))
    assert resp.status_code == 400, resp.content


def test_traceability_cycles_requires_workspace_id(graph) -> None:
    _, user, _, _ = graph
    resp = _client(user).get("/api/v1/traceability/cycles/")
    assert resp.status_code == 400, resp.content


def test_resolve_requires_artifact_ids(graph) -> None:
    _, user, _, _ = graph
    resp = _client(user).get("/api/v1/traceability/resolve/")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "artifact_ids is required"


def test_resolve_rejects_malformed_uuid(graph) -> None:
    _, user, _, _ = graph
    resp = _client(user).get("/api/v1/traceability/resolve/?artifact_ids=nope")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "artifact_ids must be valid UUIDs"


def test_resolve_rejects_batch_above_limit(graph) -> None:
    _, user, _, _ = graph
    many = ",".join(str(uuid.uuid4()) for _ in range(201))
    resp = _client(user).get(f"/api/v1/traceability/resolve/?artifact_ids={many}")
    assert resp.status_code == 400, resp.content
    assert "at most" in resp.json()["error"]["message"]


def test_resolve_maps_artifact_to_domain_entity(graph) -> None:
    tenant, user, workspace, _ = graph
    art = _requirement_artifact(tenant, workspace)

    resp = _client(user).get(f"/api/v1/traceability/resolve/?artifact_ids={art.id}")

    assert resp.status_code == 200, resp.content
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["artifact_id"] == str(art.id)
    assert rows[0]["resolved"] is True
    assert rows[0]["entity_type"] == "Requirement"


def test_resolve_unknown_id_is_not_an_error(graph) -> None:
    """The documented contract: unknown ids come back ``resolved: false``."""
    _, user, _, _ = graph
    unknown = uuid.uuid4()

    resp = _client(user).get(f"/api/v1/traceability/resolve/?artifact_ids={unknown}")

    assert resp.status_code == 200, resp.content
    assert len(resp.json()) == 1
    assert resp.json()[0]["resolved"] is False


def test_resolve_of_foreign_tenant_artifact_is_not_resolved(graph) -> None:
    """Cross-tenant isolation inside the batch resolve endpoint."""
    _, user, _, _ = graph
    other_tenant, _, other_ws = _scenario()
    foreign = _requirement_artifact(other_tenant, other_ws)

    resp = _client(user).get(f"/api/v1/traceability/resolve/?artifact_ids={foreign.id}")

    assert resp.status_code == 200, resp.content
    assert len(resp.json()) == 1
    assert resp.json()[0]["resolved"] is False
