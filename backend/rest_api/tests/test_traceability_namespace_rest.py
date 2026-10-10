"""REST-level coverage for the /traceability/ namespace complement (views.py).

leaf_id : COMP-RA-TR (TraceabilityViewSet)
req_id  : REQ-L2-TE-019

``test_trace_graph_endpoints_rest.py`` pins the ``/traceability/`` happy paths
and the resolve batch contract; this module closes the remaining guard branches
of the same dedicated namespace (mirrored from ``/tracelinks/`` but with its
own handler copies):

  - ``impact``: invalid ``direction``, non-integer ``max_depth``, the
    ``MAX_DEPTH_CAP`` refusal and the ``link_types`` filter;
  - ``path``: the happy-path shortest route, the no-path 404, the non-integer
    and above-cap ``max_depth`` refusals;
  - ``cycles``: the empty count for an acyclic graph and a detected back-edge;
  - ``resolve``: the empty-list guard (``?artifact_ids=,``).
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, UserRole
from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Tenant, TraceLink, User, Workspace
from traceability.types import LinkType

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"
_LINK = LinkType.ALLOCATED_TO.value


def _scenario() -> tuple[Tenant, User, Workspace]:
    """Create a tenant, one admin user and one Extended-preset workspace."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"T-{suffix}", slug=f"tn-{suffix}", is_active=True)
    user = User.objects.create(
        username=f"tn-{suffix}", email=f"tn-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="TN WS", preset={"name": "extended"}
        )
        provision_workspace_link_types(workspace_id=workspace.id, tenant_id=tenant.id)
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
    set_request_tenant(tenant.id)
    try:
        return Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
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
def chain() -> tuple[Tenant, User, Workspace, list[Artifact]]:
    """A workspace holding the chain ``a -> b -> c`` of three artifacts."""
    tenant, user, workspace = _scenario()
    artifacts = [_artifact(tenant, workspace) for _ in range(3)]
    _link(tenant, artifacts[0], artifacts[1])
    _link(tenant, artifacts[1], artifacts[2])
    return tenant, user, workspace, artifacts


# ---------------------------------------------------------------------------
# impact guards
# ---------------------------------------------------------------------------


def test_impact_rejects_unknown_direction(chain) -> None:
    _, user, _, artifacts = chain
    resp = _client(user).get(
        f"/api/v1/traceability/impact/?artifact_id={artifacts[0].id}&direction=sideways"
    )
    assert resp.status_code == 400, resp.content
    assert "direction must be" in resp.json()["error"]["message"]


def test_impact_rejects_non_integer_max_depth(chain) -> None:
    _, user, _, artifacts = chain
    resp = _client(user).get(
        f"/api/v1/traceability/impact/?artifact_id={artifacts[0].id}&max_depth=deep"
    )
    assert resp.status_code == 400, resp.content
    assert (
        resp.json()["error"]["message"] == "max_depth and limit must be integers"
    )


def test_impact_rejects_max_depth_above_cap(chain) -> None:
    _, user, _, artifacts = chain
    resp = _client(user).get(
        f"/api/v1/traceability/impact/?artifact_id={artifacts[0].id}&max_depth=21"
    )
    assert resp.status_code == 400, resp.content
    assert "max_depth must be <=" in resp.json()["error"]["message"]


def test_impact_filters_by_link_type(chain) -> None:
    """A ``link_types`` filter that matches nothing returns an empty result."""
    _, user, _, artifacts = chain
    resp = _client(user).get(
        f"/api/v1/traceability/impact/?artifact_id={artifacts[0].id}"
        "&link_types=references"
    )

    assert resp.status_code == 200, resp.content
    assert resp.json() == []


def test_impact_honours_direction_both(chain) -> None:
    _, user, _, artifacts = chain
    resp = _client(user).get(
        f"/api/v1/traceability/impact/?artifact_id={artifacts[1].id}&direction=both"
    )

    assert resp.status_code == 200, resp.content
    reachable = {n["artifact_id"] for n in resp.json()}
    assert reachable == {str(artifacts[0].id), str(artifacts[2].id)}


# ---------------------------------------------------------------------------
# path guards + happy path
# ---------------------------------------------------------------------------


def test_path_returns_the_shortest_path(chain) -> None:
    _, user, _, artifacts = chain
    resp = _client(user).get(
        f"/api/v1/traceability/path/?source_id={artifacts[0].id}"
        f"&target_id={artifacts[2].id}"
    )

    assert resp.status_code == 200, resp.content
    paths = resp.json()
    assert len(paths) == 1
    assert paths[0]["nodes"] == [
        str(artifacts[0].id),
        str(artifacts[1].id),
        str(artifacts[2].id),
    ]


def test_path_without_connection_returns_404(chain) -> None:
    tenant, user, workspace, _ = chain
    isolated = _artifact(tenant, workspace)

    resp = _client(user).get(
        f"/api/v1/traceability/path/?source_id={isolated.id}"
        f"&target_id={uuid.uuid4()}"
    )

    assert resp.status_code == 404, resp.content
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_path_rejects_non_integer_max_depth(chain) -> None:
    _, user, _, artifacts = chain
    resp = _client(user).get(
        f"/api/v1/traceability/path/?source_id={artifacts[0].id}"
        f"&target_id={artifacts[2].id}&max_depth=lots"
    )
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "max_depth must be an integer"


def test_path_rejects_max_depth_above_cap(chain) -> None:
    _, user, _, artifacts = chain
    resp = _client(user).get(
        f"/api/v1/traceability/path/?source_id={artifacts[0].id}"
        f"&target_id={artifacts[2].id}&max_depth=99"
    )
    assert resp.status_code == 400, resp.content
    assert "max_depth must be <=" in resp.json()["error"]["message"]


# ---------------------------------------------------------------------------
# cycles
# ---------------------------------------------------------------------------


def test_cycles_counts_empty_for_an_acyclic_graph(chain) -> None:
    _, user, workspace, _ = chain
    resp = _client(user).get(f"/api/v1/traceability/cycles/?workspace_id={workspace.id}")

    assert resp.status_code == 200, resp.content
    assert resp.json() == {"cycles": [], "count": 0}


def test_cycles_detects_a_back_reference(chain) -> None:
    tenant, user, workspace, artifacts = chain
    _link(tenant, artifacts[2], artifacts[0])

    resp = _client(user).get(f"/api/v1/traceability/cycles/?workspace_id={workspace.id}")

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["count"] >= 1, f"expected at least one cycle, got {body}"
    assert body["count"] == len(body["cycles"])


# ---------------------------------------------------------------------------
# resolve — the empty-list guard
# ---------------------------------------------------------------------------


def test_resolve_with_only_separators_is_the_missing_parameter(chain) -> None:
    """``?artifact_ids=,`` splits into zero ids — the same contract as absent."""
    _, user, _, _ = chain
    resp = _client(user).get("/api/v1/traceability/resolve/?artifact_ids=,")

    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "artifact_ids is required"
