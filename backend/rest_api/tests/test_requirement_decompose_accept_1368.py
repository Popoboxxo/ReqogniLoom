"""Issue #1368 (W12b) — the human Draft/Accept step for `decompose-next-level`.

The defect this file pins
=========================
``POST /api/v1/requirements/{pk}/decompose-next-level/`` is a pure preview
(``ephemeral: true``, #1358): it persists nothing. The UI counted the drafts,
said "Vorschlag/Vorschläge warten unter Reviews → Nur KI-Vorschläge auf deine
Prüfung" and threw the (paid) LLM output away — the review queue stayed at 0.

The missing half was the server-side accept step (#1368): the drafts the human
reviewed must be persistable *as reviewed*, over the same ``proposed`` seam
``#1095`` built for the StakeholderNeed flow — never by the client POSTing
``/requirements/`` per draft, which (from a user principal) is born as a plain
``draft`` and stays invisible (#1089).

Covered here, over the real HTTP + service + DB stack (mock provider, no
network):

* the preview is ephemeral and persists nothing;
* the accept persists every accepted draft as a child
  ``status == "proposed"`` with a ``derives-from`` TraceLink child -> parent
  (issue #341's SE direction);
* a workspace whose workflow graph has no ``proposed`` state answers a 400
  carrying the authoring reason — never a silent downgrade (#1089);
* the transport guards: unknown keys (top-level and per-draft), an empty
  ``drafts`` list, a viewer, and an unknown requirement.
"""
from __future__ import annotations

import uuid

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.context import AuthContext
from auth_tenancy.models import ROLE_EDITOR, ROLE_VIEWER, UserRole
from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Requirement,
    Tenant,
    TraceLink,
    User,
    Workspace,
)
from workflow.services import create_default_workflow

_JWT_OVERRIDES = {
    "AUTH_JWT_SECRET": "test-secret-not-a-real-key-1368",
    "AUTH_JWT_ISSUER": "reqflow",
    "AUTH_JWT_AUDIENCE": "reqflow-api",
    "AUTH_JWT_TTL_SECONDS": 3600,
}

_PASSWORD = "hunter2pass-1368"

pytestmark = pytest.mark.django_db


def _provision(workspace: Workspace, preset: str = "extended") -> None:
    set_request_tenant(workspace.tenant_id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset=preset,
            item_type="Requirement",
            tenant_id=workspace.tenant_id,
        )
    finally:
        clear_request_tenant()


def _make_workspace(tenant: Tenant, name: str, preset: str = "extended") -> Workspace:
    set_request_tenant(tenant.id)
    try:
        ws = Workspace.objects.create(tenant=tenant, name=name, preset={"name": preset})
        provision_workspace_link_types(workspace_id=ws.id, tenant_id=tenant.id)
        return ws
    finally:
        clear_request_tenant()


def _make_user(tenant: Tenant, username: str) -> User:
    user = User.objects.create(
        username=username, email=f"{username}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    return user


def _login(user: User) -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def _ctx(user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant_id,
        active_roles=("editor",),
        auth_method="test",
        tenant_name="decompose-1368",
    )


def _make_allocated_requirement(tenant: Tenant, workspace: Workspace, user: User) -> Requirement:
    """A parent Requirement with the mandatory allocated-to link the flow needs."""
    from application.architecture_service import ArchitectureService
    from application.requirement_service import RequirementService
    from application.trace_link_service import TraceLinkService

    ctx = _ctx(user)
    set_request_tenant(tenant.id)
    try:
        req = RequirementService().create_requirement(
            workspace_id=workspace.id,
            title="Parent requirement",
            description="The subsystem shall be decomposable.",
            ctx=ctx,
        )
        arch = ArchitectureService().create_architecture_element(
            workspace_id=workspace.id, title="Subsystem A", ctx=ctx
        )
        TraceLinkService().allocate(
            requirement_id=req.id, architecture_element_id=arch.id, ctx=ctx
        )
        return req
    finally:
        clear_request_tenant()


@pytest.fixture
def env():
    tenant = Tenant.objects.create(
        name="Decompose tenant", slug=f"dec-{uuid.uuid4().hex[:8]}", is_active=True
    )
    workspace = _make_workspace(tenant, "Decompose WS")
    _provision(workspace, preset="extended")

    editor = _make_user(tenant, "dec-editor")
    viewer = _make_user(tenant, "dec-viewer")
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=editor, workspace=workspace, role=ROLE_EDITOR
        )
        UserRole.objects.create(
            tenant=tenant, user=viewer, workspace=workspace, role=ROLE_VIEWER
        )
    finally:
        clear_request_tenant()

    parent = _make_allocated_requirement(tenant, workspace, editor)
    return {
        "tenant": tenant,
        "workspace": workspace,
        "editor": editor,
        "viewer": viewer,
        "parent": parent,
    }


def _preview_url(env) -> str:
    return f"/api/v1/requirements/{env['parent'].id}/decompose-next-level/"


def _accept_url(env) -> str:
    return f"/api/v1/requirements/{env['parent'].id}/decompose-next-level/accept/"


def _assert_envelope(response, code: str) -> dict:
    body = response.json()
    assert "error" in body, body
    assert body["error"]["code"] == code, body
    return body


# ---------------------------------------------------------------------------
# preview + accept happy paths
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
def test_preview_is_ephemeral_and_persists_nothing(env):
    client = _login(env["editor"])

    response = client.post(_preview_url(env), {}, format="json")

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["ephemeral"] is True
    assert body["parent_requirement_id"] == str(env["parent"].id)
    # No count assertion: the suite may run against the mock provider (2
    # deterministic drafts) or a configured real one — the contract under test
    # is the ephemeral marker and the lack of persistence, not the content.
    assert isinstance(body["drafts"], list)
    assert client.get(
        f"/api/v1/requirements/?workspace_id={env['workspace'].id}"
    ).json()["count"] == 1, "the preview persists nothing (only the parent exists)"


@override_settings(**_JWT_OVERRIDES)
def test_accept_persists_proposed_children_with_derives_from_links(env):
    client = _login(env["editor"])

    response = client.post(
        _accept_url(env),
        {
            "drafts": [
                {
                    "title": "Child one",
                    "description": "Refines the parent.",
                    "rationale": "Mock rationale.",
                },
                {"title": "Child two", "description": "", "rationale": ""},
            ]
        },
        format="json",
    )

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["count"] == 2
    assert len(body["created"]) == 2
    assert body["proposal"]["is_proposal"] is True

    set_request_tenant(env["tenant"].id)
    try:
        for entry in body["created"]:
            # #1089: an accepted AI draft is a reviewable proposal, not a
            # silently-written draft.
            assert entry["status"] == "proposed", entry
            assert entry["proposal"]["is_proposal"] is True, entry

            child = Requirement.objects.get(id=entry["id"])
            link = TraceLink.objects.get(id=entry["trace_link_id"])
            assert link.link_type == "derives-from"
            # #341: 'derives-from' points child -> parent.
            assert link.source_id == child.artifact_id
            assert link.target_id == env["parent"].artifact_id
    finally:
        clear_request_tenant()

    # The children are readable through the natural REST list path and carry
    # the proposal state there too.
    listing = client.get(
        f"/api/v1/requirements/?workspace_id={env['workspace'].id}&status=proposed"
    )
    assert listing.status_code == 200, listing.content
    assert listing.json()["count"] == 2


@override_settings(**_JWT_OVERRIDES)
def test_accept_without_proposal_support_is_400_not_a_silent_draft():
    """A graph without "proposed" must refuse, with the authoring reason."""
    tenant = Tenant.objects.create(
        name="Minimal tenant", slug=f"min-{uuid.uuid4().hex[:8]}", is_active=True
    )
    workspace = _make_workspace(tenant, "Minimal WS", preset="minimal")
    _provision(workspace, preset="minimal")
    editor = _make_user(tenant, "min-dec-editor")
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=editor, workspace=workspace, role=ROLE_EDITOR
        )
    finally:
        clear_request_tenant()
    parent = _make_allocated_requirement(tenant, workspace, editor)

    response = _login(editor).post(
        f"/api/v1/requirements/{parent.id}/decompose-next-level/accept/",
        {"drafts": [{"title": "Child", "description": "", "rationale": ""}]},
        format="json",
    )

    assert response.status_code == 400, response.content
    body = _assert_envelope(response, "VALIDATION_ERROR")
    assert body["error"]["message"], "the graph gap must be explainable"
    set_request_tenant(tenant.id)
    try:
        assert Requirement.objects.filter(
            artifact__workspace_id=workspace.id
        ).count() == 1, "nothing may be persisted on the refused accept"
    finally:
        clear_request_tenant()


# ---------------------------------------------------------------------------
# transport guards
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
def test_unknown_top_level_key_is_rejected(env):
    response = _login(env["editor"]).post(
        _accept_url(env),
        {
            "drafts": [{"title": "Child", "description": "", "rationale": ""}],
            "status": "approved",
        },
        format="json",
    )

    assert response.status_code == 400, response.content
    _assert_envelope(response, "VALIDATION_ERROR")


@override_settings(**_JWT_OVERRIDES)
def test_unknown_draft_key_is_rejected(env):
    response = _login(env["editor"]).post(
        _accept_url(env),
        {"drafts": [{"title": "Child", "suggested_arch_element_id": str(uuid.uuid4())}]},
        format="json",
    )

    assert response.status_code == 400, response.content
    _assert_envelope(response, "VALIDATION_ERROR")


@override_settings(**_JWT_OVERRIDES)
def test_empty_drafts_list_is_400(env):
    response = _login(env["editor"]).post(_accept_url(env), {"drafts": []}, format="json")

    assert response.status_code == 400, response.content
    _assert_envelope(response, "VALIDATION_ERROR")


@override_settings(**_JWT_OVERRIDES)
def test_viewer_cannot_accept(env):
    response = _login(env["viewer"]).post(
        _accept_url(env),
        {"drafts": [{"title": "Child", "description": "", "rationale": ""}]},
        format="json",
    )

    assert response.status_code == 403, response.content


@override_settings(**_JWT_OVERRIDES)
def test_unknown_requirement_is_404(env):
    response = _login(env["editor"]).post(
        f"/api/v1/requirements/{uuid.uuid4()}/decompose-next-level/accept/",
        {"drafts": [{"title": "Child", "description": "", "rationale": ""}]},
        format="json",
    )

    assert response.status_code == 404, response.content
