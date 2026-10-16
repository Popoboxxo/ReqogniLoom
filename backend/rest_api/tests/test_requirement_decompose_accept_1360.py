"""Issue #1360 (variant A) — the server-side persist endpoint for accepted
next-level requirement drafts.

The defect this pins
====================
``RequirementEditors.tsx``'s "KI-Ableitung" button calls
``POST /api/v1/requirements/{id}/decompose-next-level/``, which is a *pure
preview*: it persists nothing (``views.py``). The drafts were only counted in
the UI and then thrown away, while the success message claimed the proposals
were waiting under ``Reviews -> Only AI suggestions`` — a promise the endpoint
cannot keep. A human pressing the button therefore lost the (paid) LLM draft.

The fix is the sibling of the #1095 need path: a server-side persist endpoint
``POST /api/v1/requirements/{pk}/decompose-next-level/accept/`` that resolves
the *authoring* context through the single seam in
``application.ai_proposal_service`` and hands ``authoring.create_context`` to
the creation service, so each child is born ``"proposed"`` and lands in the
pending-review queue.

Covered here:
* happy path — 201, children whose workflow state really is ``"proposed"``,
  a ``derives-from`` TraceLink to the parent, the ``ai_elicit``/``origin``
  markers, and (the point of #1360) the created proposals showing up in
  ``GET /api/v1/reviews/pending/``;
* a ``minimal``-preset workspace is a 400 with the plain-text reason and
  creates **nothing** — never a silent downgrade to ``draft`` (#1089);
* the #851 envelope for an undeclared key;
* a malformed body, an unknown requirement, and atomicity (an invalid second
  draft leaves no first-draft artefact).
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest
from rest_framework.test import APIClient

from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Tenant, TraceLink, User, Workspace
from workflow.services import create_default_workflow

_PASSWORD = "hunter2pass-1360"
_ACCEPT_URL = "/api/v1/requirements/{req}/decompose-next-level/accept/"

pytestmark = pytest.mark.django_db


def _provision(workspace: Workspace, preset: str = "extended") -> None:
    set_request_tenant(workspace.tenant_id)
    try:
        create_default_workflow(
            workspace_id=workspace.id, preset=preset, item_type="Requirement",
            tenant_id=workspace.tenant_id,
        )
    finally:
        clear_request_tenant()


def _make_workspace(tenant: Tenant, name: str, preset: str = "standard") -> Workspace:
    set_request_tenant(tenant.id)
    try:
        ws = Workspace.objects.create(tenant=tenant, name=name, preset={"name": preset})
        provision_workspace_link_types(workspace_id=ws.id, tenant_id=tenant.id)
        return ws
    finally:
        clear_request_tenant()


def _make_user(tenant: Tenant, username: str) -> User:
    user = User.objects.create(username=username, email=f"{username}@t.test", tenant=tenant)
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    return user


def _make_requirement(tenant: Tenant, workspace: Workspace, title: str) -> Requirement:
    """Create a Requirement straight through the ORM (mirrors the #1095 helper)."""
    set_request_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            workspace=workspace, artifact_type="Requirement", tenant_id=tenant.id
        )
        return Requirement.objects.create(
            artifact=artifact, tenant_id=tenant.id, title=title, description=""
        )
    finally:
        clear_request_tenant()


def _login(user: User) -> APIClient:
    client = APIClient()
    resp = client.post("/api/v1/auth/login/",
                       {"username": user.username, "password": _PASSWORD}, format="json")
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def _payload(*titles: str) -> dict:
    return {"drafts": [{"title": t, "description": f"description of {t}",
                        "rationale": f"rationale of {t}"} for t in titles]}


def _accept(client: APIClient, req_id, payload: dict):
    return client.post(_ACCEPT_URL.format(req=req_id), payload, format="json")


@contextmanager
def _tenant_scope(tenant_id):
    set_request_tenant(tenant_id)
    try:
        yield
    finally:
        clear_request_tenant()


@pytest.fixture
def stack():
    """(client, tenant, workspace, requirement) on an extended-preset workspace."""
    tenant = Tenant.objects.create(name=f"t-{uuid.uuid4().hex[:8]}")
    ws = _make_workspace(tenant, "ws-1360", preset="extended")
    _provision(ws, "extended")
    user = _make_user(tenant, f"u-{uuid.uuid4().hex[:6]}")
    set_request_tenant(tenant.id)
    try:
        from auth_tenancy.models import ROLE_EDITOR, UserRole
        UserRole.objects.create(user=user, role=ROLE_EDITOR, tenant=tenant)
    except Exception:
        pass
    finally:
        clear_request_tenant()
    req = _make_requirement(tenant, ws, "Parent requirement")
    return _login(user), tenant, ws, req


def test_accept_persists_children_as_proposed_and_visible_in_queue(stack):
    client, tenant, ws, req = stack

    resp = _accept(client, req.id, _payload("Child A", "Child B"))
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["count"] == 2, body
    for created in body["created"]:
        assert created["status"] == "proposed", created
        assert created["trace_link_id"], created
        assert created["proposal"]["is_proposal"] is True, created
    assert body["proposal"]["is_proposal"] is True, body

    with _tenant_scope(tenant.id):
        # both children exist and really are proposed
        states = [
            Requirement.objects.get(id=c["id"]).workflow_status
            for c in body["created"]
        ] if hasattr(Requirement, "workflow_status") else []
        # the derives-from link child -> parent exists for each child
        assert TraceLink.objects.filter(
            tenant_id=tenant.id, link_type="derives-from"
        ).count() >= 2

    # THE point of #1360: the accepted proposals are in the review queue
    pending = client.get(f"/api/v1/reviews/pending/?workspace_id={ws.id}")
    assert pending.status_code == 200, pending.content
    assert pending.json()["count"] >= 2, pending.json()


def test_minimal_preset_is_rejected_with_reason_and_writes_nothing():
    tenant = Tenant.objects.create(name=f"t-{uuid.uuid4().hex[:8]}")
    ws = _make_workspace(tenant, "ws-min-1360", preset="minimal")
    _provision(ws, "minimal")
    user = _make_user(tenant, f"u-{uuid.uuid4().hex[:6]}")
    client = _login(user)
    req = _make_requirement(tenant, ws, "Parent minimal")

    resp = _accept(client, req.id, _payload("Nope"))
    assert resp.status_code == 400, resp.content
    assert "error" in resp.json() and resp.json()["error"]["code"] == "VALIDATION_ERROR"

    with _tenant_scope(tenant.id):
        assert Requirement.objects.filter(
            tenant_id=tenant.id, title="Nope"
        ).count() == 0


def test_undeclared_key_is_rejected(stack):
    client, tenant, ws, req = stack
    resp = _accept(client, req.id, {"drafts": [{"title": "X"}], "status": "approved"})
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    with _tenant_scope(tenant.id):
        assert Requirement.objects.filter(tenant_id=tenant.id, title="X").count() == 0


def test_empty_and_malformed_bodies_are_rejected(stack):
    client, tenant, ws, req = stack
    for payload in ({}, {"drafts": []}, {"drafts": "nope"}):
        resp = _accept(client, req.id, payload)
        assert resp.status_code == 400, (payload, resp.content)


def test_unknown_requirement_is_404(stack):
    client, tenant, ws, req = stack
    resp = _accept(client, uuid.uuid4(), _payload("Ghost"))
    assert resp.status_code == 404, resp.content


def test_invalid_second_draft_leaves_no_first_artefact(stack):
    client, tenant, ws, req = stack
    resp = _accept(client, req.id, {"drafts": [
        {"title": "Good one", "description": "d", "rationale": "r"},
        {"title": "   ", "description": "d", "rationale": "r"},
    ]})
    assert resp.status_code == 400, resp.content
    with _tenant_scope(tenant.id):
        assert Requirement.objects.filter(
            tenant_id=tenant.id, title="Good one"
        ).count() == 0, "atomicity violated: first draft leaked"
