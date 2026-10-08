"""REST surface for the ADR-019 generic suggestion inbox (WP4).

These tests drive the real HTTP + service + DB stack over the three endpoints
added in WP4, and pin the contract the MCP parent can rely on:

* **list** — ``GET /api/v1/suggestions/?workspace_id=`` answers the
  ``StandardPagination`` envelope with the workspace's ``open`` suggestions and
  their server-set provenance;
* **tenant fence** — a workspace of a foreign tenant yields an empty page, never
  a cross-tenant row (the service's tenant-scoped read cannot see it);
* **RBAC gate** — the global ``RbacPermission`` maps POST to ``WRITE``, so a
  ``viewer`` is refused (403) on accept while still allowed to read;
* **agent self-accept** — ``AgentSelfConfirmError`` is mapped to
  ``403 PERMISSION_DENIED`` (review finding ADR-019 ``003-01``), and the
  proposal survives the refused attempt;
* **reject** — a human reject stamps ``rejected`` and removes only the *proposal
  link*, never the linked artifacts (Zusage 7(e)).

A suggestion can only be produced over MCP / in an agent context (the
human-bearer REST producer is deliberately out of MVP scope), so the fixtures
create one through the same ``SuggestionService`` the producer uses and then
exercise the REST decisions against it.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from application.suggestion_service import SuggestionService
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import (
    ROLE_ADMIN,
    ROLE_VIEWER,
    ApiKey,
    UserRole,
)
from auth_tenancy.services.authentication import (
    generate_api_key_plaintext,
    hash_api_key,
)
from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Suggestion, Tenant, TraceLink, User, Workspace
from persistence.tenancy import TenantContext

_SECRET = "test-secret-not-a-real-key-wp4"
_PASSWORD = "wp4pass123456"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)

_AGENT_LABEL = "Suggestion Bot"


def _seed_workspace(
    *, tenant: Tenant, username: str, role: str
) -> tuple[Workspace, User]:
    """Create a workspace + one role-holding user inside *tenant*."""
    user = User.objects.create(
        username=f"{username}-{tenant.slug}",
        email=f"{username}-{tenant.slug}@t.test",
        tenant=tenant,
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=f"{username} WS", preset={"name": "standard"}
        )
        provision_workspace_link_types(
            workspace_id=workspace.id, tenant_id=tenant.id
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=role
        )
    finally:
        clear_request_tenant()
    return workspace, user


def _trace_link_payload(source: Artifact, target: Artifact) -> dict:
    return {
        "rule_id": "TRACE-P1",
        "source_artifact_id": str(source.id),
        "ranked_candidates": [
            {
                "artifact_id": str(target.id),
                "artifact_type": "Requirement",
                "score": 3,
            },
        ],
        "rationale": "keyword overlap",
    }


@pytest.fixture
def sug_env(db):
    """Tenant + workspace + admin/viewer users + an agent key, and one suggestion.

    The suggestion is produced with the ``trace_link`` adapter exactly as the
    WP5 producer does, so the accept/reject paths run against a real M2 proposal
    link.
    """
    tenant = Tenant.objects.create(name="WP4 T", slug="wp4-t", is_active=True)
    workspace, admin = _seed_workspace(
        tenant=tenant, username="wp4admin", role=ROLE_ADMIN
    )

    set_request_tenant(tenant.id)
    try:
        viewer = User.objects.create(
            username="wp4viewer", email="wp4viewer@t.test", tenant=tenant
        )
        viewer.set_password(_PASSWORD)
        viewer.save(update_fields=["password"])
        UserRole.objects.create(
            tenant=tenant, user=viewer, workspace=workspace, role=ROLE_VIEWER
        )
        source = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        target = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        plaintext = generate_api_key_plaintext()
        key = ApiKey.objects.create(
            tenant=tenant,
            user=admin,
            name="wp4-bot",
            key_hash=hash_api_key(plaintext),
            principal_type="agent",
            agent_label=_AGENT_LABEL,
            workspace_ids=[str(workspace.id)],
            expires_at=timezone.now() + timedelta(days=1),
        )
    finally:
        clear_request_tenant()

    agent_ctx = AuthContext(
        user_id=admin.id,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=key.id,
        actor_type="agent",
        agent_label=_AGENT_LABEL,
    )
    TenantContext.set_tenant(tenant.id)
    try:
        suggestion = SuggestionService().propose(
            "trace_link",
            agent_ctx,
            workspace_id=workspace.id,
            payload=_trace_link_payload(source, target),
            producer="traceability.suggest_links",
        )
    finally:
        TenantContext.clear_tenant()

    yield {
        "tenant": tenant,
        "workspace": workspace,
        "admin": admin,
        "viewer": viewer,
        "source": source,
        "target": target,
        "key": key,
        "agent_key": plaintext,
        "suggestion": suggestion,
    }


def _login_client(username: str) -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": _PASSWORD},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def _human_admin_client(env: dict) -> APIClient:
    return _login_client(env["admin"].username)


def _viewer_client(env: dict) -> APIClient:
    return _login_client(env["viewer"].username)


def _agent_client(env: dict) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {env['agent_key']}")
    return client


# ---------------------------------------------------------------------------
# List contract
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_list_returns_open_suggestions_with_provenance(sug_env):
    client = _human_admin_client(sug_env)

    resp = client.get(
        "/api/v1/suggestions/",
        {"workspace_id": str(sug_env["workspace"].id)},
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert {"count", "results"} <= set(body)
    assert body["count"] == 1

    row = body["results"][0]
    assert row["id"] == sug_env["suggestion"]["id"]
    assert row["kind"] == "trace_link"
    assert row["status"] == "open"
    assert row["producer"] == "traceability.suggest_links"
    # Provenance is server-set from the producing ApiKey, never from a body.
    assert row["proposed_by"] == str(sug_env["key"].id)
    assert row["proposed_at"] is not None
    assert row["decided_by"] is None
    assert row["decided_at"] is None
    assert row["workspace_id"] == str(sug_env["workspace"].id)


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_list_requires_workspace_id(sug_env):
    client = _human_admin_client(sug_env)

    resp = client.get("/api/v1/suggestions/")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Tenant fence
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_list_does_not_leak_a_foreign_tenants_workspace(sug_env):
    foreign = Tenant.objects.create(name="WP4 Foreign", slug="wp4-foreign")
    _, foreign_admin = _seed_workspace(
        tenant=foreign, username="wp4foreign", role=ROLE_ADMIN
    )

    foreign_client = _login_client(foreign_admin.username)
    resp = foreign_client.get(
        "/api/v1/suggestions/",
        {"workspace_id": str(sug_env["workspace"].id)},
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["results"] == []

    # Sanity: the owner still sees it, so the empty page is a fence, not a bug.
    owner = _human_admin_client(sug_env)
    assert owner.get(
        "/api/v1/suggestions/",
        {"workspace_id": str(sug_env["workspace"].id)},
    ).json()["count"] == 1


# ---------------------------------------------------------------------------
# RBAC gate
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_viewer_may_read_but_not_accept(sug_env):
    viewer = _viewer_client(sug_env)

    listed = viewer.get(
        "/api/v1/suggestions/",
        {"workspace_id": str(sug_env["workspace"].id)},
    )
    assert listed.status_code == 200, listed.content
    assert listed.json()["count"] == 1

    refused = viewer.post(
        f"/api/v1/suggestions/{sug_env['suggestion']['id']}/accept/"
    )
    assert refused.status_code == 403, refused.content
    assert refused.json()["error"]["code"] == "PERMISSION_DENIED"

    # The refused attempt is a no-op: the receipt stays open.
    suggestion = Suggestion.unscoped.get(id=sug_env["suggestion"]["id"])
    assert suggestion.status == "open"


# ---------------------------------------------------------------------------
# Agent self-accept -> 403 (ADR-019 7(c), finding 003-01)
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_agent_self_accept_is_403_not_500(sug_env):
    agent = _agent_client(sug_env)

    resp = agent.post(
        f"/api/v1/suggestions/{sug_env['suggestion']['id']}/accept/",
        {"workspace_id": str(sug_env["workspace"].id)},
        format="json",
    )
    assert resp.status_code == 403, resp.content
    body = resp.json()["error"]
    assert body["code"] == "PERMISSION_DENIED"
    assert "may not" in body["message"]
    assert "internal error" not in body["message"].lower()

    # Neither the receipt nor the proposal link moved.
    suggestion = Suggestion.unscoped.get(id=sug_env["suggestion"]["id"])
    assert suggestion.status == "open"
    link = TraceLink.unscoped.get(id=sug_env["suggestion"]["target_item_id"])
    assert link.is_proposal is True


# ---------------------------------------------------------------------------
# Accept contract (human)
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_human_accept_delegates_and_stamps_accepted(sug_env):
    human = _human_admin_client(sug_env)

    resp = human.post(
        f"/api/v1/suggestions/{sug_env['suggestion']['id']}/accept/"
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["decided_by"] == str(sug_env["admin"].id)
    assert body["decided_at"] is not None

    # The delegated M2 confirm really ran.
    link = TraceLink.unscoped.get(id=sug_env["suggestion"]["target_item_id"])
    assert link.is_proposal is False


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_accept_unknown_suggestion_is_404(sug_env):
    import uuid

    human = _human_admin_client(sug_env)
    resp = human.post(f"/api/v1/suggestions/{uuid.uuid4()}/accept/")
    assert resp.status_code == 404, resp.content
    assert resp.json()["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Reject contract (ADR-019 7(e))
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_human_reject_stamps_rejected_and_destroys_no_artifact(sug_env):
    human = _human_admin_client(sug_env)

    resp = human.post(
        f"/api/v1/suggestions/{sug_env['suggestion']['id']}/reject/",
        {"reason": "not a real derivation"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["decided_by"] == str(sug_env["admin"].id)
    assert body["decided_at"] is not None

    # Both linked artifacts survive; only the proposal link is discarded.
    assert Artifact.unscoped.filter(
        id__in=[sug_env["source"].id, sug_env["target"].id]
    ).count() == 2
    assert not TraceLink.unscoped.filter(
        id=sug_env["suggestion"]["target_item_id"]
    ).exists()


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_agent_self_reject_is_403(sug_env):
    agent = _agent_client(sug_env)

    resp = agent.post(
        f"/api/v1/suggestions/{sug_env['suggestion']['id']}/reject/",
        {"reason": "agent cannot decide its own proposal"},
        format="json",
    )
    assert resp.status_code == 403, resp.content
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"

    suggestion = Suggestion.unscoped.get(id=sug_env["suggestion"]["id"])
    assert suggestion.status == "open"
