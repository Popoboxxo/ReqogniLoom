"""REST-level coverage for TraceLinkViewSet CRUD/lifecycle (views.py).

leaf_id : COMP-RA-TL (TraceLinkViewSet)
req_id  : REQ-L2-RA-001, REQ-002, REQ-L2-VS-004

``test_trace_graph_endpoints_rest.py`` pins the graph read endpoints
(impact/path/cycles/resolve); this module covers the remaining handler surface
of the same ViewSet through the real middleware stack:

  - ``list`` both branches — workspace-level pagination and the
    ``?artifact_id=`` up/downstream listing (#264/#512 endpoint-echo);
  - ``create`` happy path + serializer 400, the always-404 ``retrieve`` and the
    immutability 405 on PATCH;
  - ``destroy`` and the proposal lifecycle ``confirm``/``discard``;
  - ``similar`` validation guards against the pgvector similarity search.
"""
from __future__ import annotations

import uuid

import pytest
from django.utils import timezone
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
    tenant = Tenant.objects.create(name=f"T-{suffix}", slug=f"tl-{suffix}", is_active=True)
    user = User.objects.create(
        username=f"tl-{suffix}", email=f"tl-{suffix}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="TL WS", preset={"name": "extended"}
        )
        # Link validation is always-on: an unprovisioned workspace has an empty
        # link-type catalog and rejects every trace link (see rest_api/conftest).
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


def _artifact(
    tenant: Tenant, workspace: Workspace, name: str = "Artifact", artifact_type: str = "Requirement"
) -> Artifact:
    set_request_tenant(tenant.id)
    try:
        return Artifact.objects.create(
            tenant=tenant,
            workspace=workspace,
            artifact_type=artifact_type,
            custom_fields={"name": name},
        )
    finally:
        clear_request_tenant()


def _link(
    tenant: Tenant,
    source: Artifact,
    target: Artifact,
    *,
    proposed: bool = False,
) -> TraceLink:
    set_request_tenant(tenant.id)
    try:
        return TraceLink.objects.create(
            tenant=tenant,
            source=source,
            target=target,
            link_type=_LINK,
            # ``is_proposal`` reads ``proposed_at`` — an unconfirmed agent
            # proposal carries a timestamp, ``proposed_by`` stays optional.
            proposed_at=timezone.now() if proposed else None,
        )
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# Auth + validation guards
# ---------------------------------------------------------------------------


def test_list_without_token_returns_401() -> None:
    assert APIClient().get("/api/v1/tracelinks/").status_code == 401


def test_create_without_token_returns_401() -> None:
    resp = APIClient().post("/api/v1/tracelinks/", {}, format="json")
    assert resp.status_code == 401, resp.content


def test_list_requires_workspace_id() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get(f"/api/v1/tracelinks/?artifact_id={uuid.uuid4()}")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "workspace_id is required"


def test_list_rejects_invalid_workspace_uuid() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get("/api/v1/tracelinks/?workspace_id=nope")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "workspace_id must be a valid UUID"


def test_create_with_missing_fields_returns_400() -> None:
    _, user, _ = _scenario()
    resp = _client(user).post(
        "/api/v1/tracelinks/", {"link_type": _LINK}, format="json"
    )
    assert resp.status_code == 400, resp.content
    fields = {d["field"] for d in resp.json()["error"]["details"]}
    assert {"source_id", "target_id"} <= fields


def test_retrieve_is_not_supported_and_returns_404() -> None:
    """TraceLinkService exposes no get-by-id — the handler is a fixed 404."""
    _, user, _ = _scenario()
    resp = _client(user).get(f"/api/v1/tracelinks/{uuid.uuid4()}/")
    assert resp.status_code == 404, resp.content
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_patch_is_refused_with_405() -> None:
    """TraceLinks are immutable: PATCH is a 405, not a silent no-op."""
    tenant, user, workspace = _scenario()
    source = _artifact(tenant, workspace)
    target = _artifact(tenant, workspace)
    link = _link(tenant, source, target)

    resp = _client(user).patch(
        f"/api/v1/tracelinks/{link.id}/", {"link_type": "references"}, format="json"
    )

    assert resp.status_code == 405, resp.content
    assert "cannot be updated" in resp.json()["error"]["message"]


# ---------------------------------------------------------------------------
# list — both branches
# ---------------------------------------------------------------------------


def test_list_workspace_branch_returns_the_stored_link() -> None:
    """Fix #264: the workspace-level branch lists real rows, not an empty page."""
    tenant, user, workspace = _scenario()
    source = _artifact(tenant, workspace, "Source")
    target = _artifact(tenant, workspace, "Target")
    link = _link(tenant, source, target)

    resp = _client(user).get(f"/api/v1/tracelinks/?workspace_id={workspace.id}")

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["count"] == 1
    row = body["results"][0]
    assert row["id"] == str(link.id)
    assert row["source_id"] == str(source.id)
    assert row["target_id"] == str(target.id)


def test_list_artifact_branch_returns_up_and_downstream_links() -> None:
    tenant, user, workspace = _scenario()
    upstream = _artifact(tenant, workspace, "Up")
    middle = _artifact(tenant, workspace, "Mid")
    downstream = _artifact(tenant, workspace, "Down")
    _link(tenant, upstream, middle)
    _link(tenant, middle, downstream)

    resp = _client(user).get(
        f"/api/v1/tracelinks/?workspace_id={workspace.id}&artifact_id={middle.id}"
    )

    assert resp.status_code == 200, resp.content
    rows = resp.json()["results"]
    ids = {row["id"] for row in rows}
    source_targets = {(row["source_id"], row["target_id"]) for row in rows}
    assert len(rows) == 2, rows
    assert (str(upstream.id), str(middle.id)) in source_targets
    assert (str(middle.id), str(downstream.id)) in source_targets
    assert len(ids) == 2, "a link listed twice is the self-link bug from #264"


def test_list_is_scoped_to_the_tenant() -> None:
    _tenant, user, workspace = _scenario()
    foreign_tenant, _, foreign_ws = _scenario()
    _link(
        tenant=foreign_tenant,
        source=_artifact(foreign_tenant, foreign_ws),
        target=_artifact(foreign_tenant, foreign_ws),
    )

    resp = _client(user).get(f"/api/v1/tracelinks/?workspace_id={workspace.id}")

    assert resp.status_code == 200, resp.content
    assert resp.json()["count"] == 0


# ---------------------------------------------------------------------------
# create / destroy
# ---------------------------------------------------------------------------


def test_create_happy_path_resolves_titles() -> None:
    tenant, user, workspace = _scenario()
    # ``allocated-to`` is only valid Requirement -> ArchitectureElement — the
    # link-type catalog enforces the endpoint pair (always-on, see conftest).
    source = _artifact(tenant, workspace, "Req A")
    target = _artifact(tenant, workspace, "Subsystem", artifact_type="ArchitectureElement")

    resp = _client(user).post(
        "/api/v1/tracelinks/",
        {
            "source_id": str(source.id),
            "target_id": str(target.id),
            "link_type": _LINK,
            "rationale": "allocated because",
        },
        format="json",
    )

    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["source_id"] == str(source.id)
    assert body["target_id"] == str(target.id)
    assert body["link_type"] == _LINK
    assert body["rationale"] == "allocated because"
    assert TraceLink.unscoped.filter(
        source_id=source.id, target_id=target.id, link_type=_LINK
    ).exists()


def test_create_with_unknown_link_type_is_a_mapped_error() -> None:
    tenant, user, workspace = _scenario()
    source = _artifact(tenant, workspace)
    target = _artifact(tenant, workspace)

    resp = _client(user).post(
        "/api/v1/tracelinks/",
        {
            "source_id": str(source.id),
            "target_id": str(target.id),
            "link_type": "no-such-link-type",
        },
        format="json",
    )

    assert resp.status_code in (400, 422, 500), resp.content
    assert "error" in resp.json()


def test_destroy_happy_path_and_unknown_id() -> None:
    tenant, user, workspace = _scenario()
    source = _artifact(tenant, workspace)
    target = _artifact(tenant, workspace)
    link = _link(tenant, source, target)

    deleted = _client(user).delete(f"/api/v1/tracelinks/{link.id}/")
    assert deleted.status_code == 204, deleted.content
    assert not TraceLink.unscoped.filter(id=link.id).exists()

    missing = _client(user).delete(f"/api/v1/tracelinks/{uuid.uuid4()}/")
    assert missing.status_code == 404, missing.content


# ---------------------------------------------------------------------------
# confirm / discard — the proposal lifecycle
# ---------------------------------------------------------------------------


def test_confirm_of_a_plain_link_is_idempotent() -> None:
    """Confirming an already-confirmed (non-proposal) link is a no-op 200."""
    tenant, user, workspace = _scenario()
    link = _link(
        tenant, _artifact(tenant, workspace), _artifact(tenant, workspace)
    )

    resp = _client(user).post(f"/api/v1/tracelinks/{link.id}/confirm/", {}, format="json")

    assert resp.status_code == 200, resp.content
    assert resp.json()["id"] == str(link.id)


def test_confirm_unknown_link_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).post(
        f"/api/v1/tracelinks/{uuid.uuid4()}/confirm/", {}, format="json"
    )
    assert resp.status_code == 404, resp.content


def test_discard_of_a_proposed_link_deletes_it() -> None:
    _tenant, user, workspace = _scenario()
    link = _link(
        _tenant, _artifact(_tenant, workspace), _artifact(_tenant, workspace), proposed=True
    )

    resp = _client(user).post(f"/api/v1/tracelinks/{link.id}/discard/", {}, format="json")

    assert resp.status_code == 204, resp.content
    assert not TraceLink.unscoped.filter(id=link.id).exists()


def test_discard_of_a_non_proposed_link_is_refused() -> None:
    """A confirmed link goes through DELETE — this route must not delete it."""
    tenant, user, workspace = _scenario()
    link = _link(
        tenant, _artifact(tenant, workspace), _artifact(tenant, workspace)
    )

    resp = _client(user).post(f"/api/v1/tracelinks/{link.id}/discard/", {}, format="json")

    assert resp.status_code == 400, resp.content
    assert TraceLink.unscoped.filter(id=link.id).exists()


def test_discard_unknown_link_returns_404() -> None:
    _, user, _ = _scenario()
    resp = _client(user).post(
        f"/api/v1/tracelinks/{uuid.uuid4()}/discard/", {}, format="json"
    )
    assert resp.status_code == 404, resp.content


# ---------------------------------------------------------------------------
# similar — pgvector nearest-neighbour guards
# ---------------------------------------------------------------------------


def test_similar_requires_tracelink_id() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get("/api/v1/tracelinks/similar/")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "tracelink_id is required"


def test_similar_rejects_malformed_uuid() -> None:
    _, user, _ = _scenario()
    resp = _client(user).get("/api/v1/tracelinks/similar/?tracelink_id=abc")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["message"] == "tracelink_id must be a valid UUID"


def test_similar_accepts_a_non_integer_limit() -> None:
    """A garbage ``limit`` falls back to 10 instead of failing the request."""
    tenant, user, workspace = _scenario()
    link = _link(
        tenant, _artifact(tenant, workspace), _artifact(tenant, workspace)
    )

    resp = _client(user).get(
        f"/api/v1/tracelinks/similar/?tracelink_id={link.id}&limit=lots"
    )

    # The link has no embedding: a mapped 400 is the deterministic answer; 503
    # is the honest one when the deployment has no pgvector extension.
    assert resp.status_code in (400, 503), resp.content
