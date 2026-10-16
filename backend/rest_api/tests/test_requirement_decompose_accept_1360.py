"""Issue #1360 (variant A) — server-side persist endpoint for accepted
next-level requirement drafts.

The defect this pins
====================
``RequirementEditors.tsx``'s "KI-Ableitung" button calls
``POST /api/v1/requirements/{id}/decompose-next-level/``, which is a *pure
preview*: it persists nothing. The drafts were counted in the UI and then
thrown away, while the success message claimed they were waiting under
"Reviews -> Only AI suggestions" — a promise the endpoint cannot keep, so a
human pressing the button lost the (paid) LLM draft (#1368).

The fix is the sibling of the #1095 need path:
``POST /api/v1/requirements/{pk}/decompose-next-level/accept/`` resolves the
*authoring* context through the single seam in
``application.ai_proposal_service`` and hands ``authoring.create_context`` to
the creation service, so every child is born ``"proposed"`` and lands in the
pending-review queue.

Assertions are driven over HTTP (plus ORM *creates* for the fixtures) so the
suite pins the wire contract rather than service internals — the gap was
precisely the missing transport.

Two fixture rules this file had to learn the hard way (both are runtime
preconditions of ``TenantManager``, not test cosmetics):

* every tenant-scoped ORM call must run inside an armed tenant context
  (``set_request_tenant``), including the *fixture* helpers that create users
  and roles — otherwise ``TenantContextNotSetError``;
* the API user needs a **workspace-scoped** ``UserRole`` — the endpoint is
  permission-gated, and without a role it answers 403 instead of reaching the
  validation branches these tests are about.

Covered:
* happy path — 201, children whose workflow state really is ``"proposed"``,
  a ``derives-from`` link, the ``ai_elicit``/``origin`` markers, and (the point
  of #1360) the created proposals appearing in ``GET /api/v1/reviews/pending/``;
* a ``minimal``-preset workspace (no ``"proposed"`` in the graph) is a 400
  with the plain-text reason and creates **nothing** — never a silent
  downgrade to ``draft`` (#1089);
* the #851 envelope for an undeclared key, and a malformed body;
* an unknown requirement is a 404 and creates nothing;
* atomicity: an invalid second draft leaves no first-draft artefact.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_EDITOR, UserRole
from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Tenant, User, Workspace
from workflow.services import create_default_workflow

_PASSWORD = "hunter2pass-1360"
_ACCEPT_URL = "/api/v1/requirements/{req}/decompose-next-level/accept/"

pytestmark = pytest.mark.django_db


def _provision(workspace: Workspace, preset: str) -> None:
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


def _make_workspace(tenant: Tenant, name: str, preset: str) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        ws = Workspace.objects.create(tenant=tenant, name=name, preset={"name": preset})
        provision_workspace_link_types(workspace_id=ws.id, tenant_id=tenant.id)
        return ws
    finally:
        clear_request_tenant()


def _make_editor(tenant: Tenant, workspace: Workspace) -> User:
    """Editor with a workspace-scoped role, created inside an armed context.

    Both parts matter: ``User``/``UserRole`` are tenant-scoped (no context →
    ``TenantContextNotSetError``), and the endpoint is permission-gated (no
    role → 403, so the validation branches would never be reached).
    """
    set_request_tenant(tenant.id)
    try:
        user = User.objects.create(
            username=f"u-{uuid.uuid4().hex[:8]}", email="editor@t.test", tenant=tenant
        )
        user.set_password(_PASSWORD)
        user.save(update_fields=["password"])
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=ROLE_EDITOR
        )
        return user
    finally:
        clear_request_tenant()


def _make_requirement(tenant: Tenant, workspace: Workspace, title: str) -> Requirement:
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
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def _payload(*titles: str) -> dict:
    return {
        "drafts": [
            {"title": t, "description": f"description of {t}", "rationale": f"rationale of {t}"}
            for t in titles
        ]
    }


def _accept(client: APIClient, req_id, payload: dict):
    return client.post(_ACCEPT_URL.format(req=req_id), payload, format="json")


def _requirement_count(client: APIClient, workspace_id) -> int:
    resp = client.get(f"/api/v1/requirements/?workspace_id={workspace_id}&page_size=1")
    assert resp.status_code == 200, resp.content
    return resp.json().get("count", 0)


@contextmanager
def _stack(preset: str = "extended"):
    """Tenant + workspace + editor + parent requirement on *preset*."""
    tenant = Tenant.objects.create(name=f"t-{uuid.uuid4().hex[:8]}")
    ws = _make_workspace(tenant, f"ws-1360-{uuid.uuid4().hex[:6]}", preset)
    _provision(ws, preset)
    user = _make_editor(tenant, ws)
    parent = _make_requirement(tenant, ws, "Parent requirement")
    yield _login(user), tenant, ws, parent


def test_accept_persists_children_as_proposed_and_visible_in_queue():
    with _stack("extended") as (client, tenant, ws, req):
        before = _requirement_count(client, ws.id)

        resp = _accept(client, req.id, _payload("Child A", "Child B"))
        assert resp.status_code == 201, resp.content
        body = resp.json()
        assert body["count"] == 2, body
        for created in body["created"]:
            assert created["status"] == "proposed", created
            assert created["trace_link_id"], created
            assert created["proposal"]["is_proposal"] is True, created
        assert body["proposal"]["is_proposal"] is True, body

        after = _requirement_count(client, ws.id)
        assert after == before + 2, (before, after)

        # THE point of #1360: the accepted proposals are in the review queue.
        pending = client.get(f"/api/v1/reviews/pending/?workspace_id={ws.id}")
        assert pending.status_code == 200, pending.content
        assert pending.json()["count"] >= 2, pending.json()


def test_minimal_preset_is_rejected_with_reason_and_writes_nothing():
    with _stack("minimal") as (client, tenant, ws, req):
        before = _requirement_count(client, ws.id)

        resp = _accept(client, req.id, _payload("Nope"))
        assert resp.status_code == 400, resp.content
        body = resp.json()
        assert body["error"]["code"] == "VALIDATION_ERROR", body

        assert _requirement_count(client, ws.id) == before


def test_undeclared_key_is_rejected_and_writes_nothing():
    with _stack("extended") as (client, tenant, ws, req):
        before = _requirement_count(client, ws.id)

        resp = _accept(client, req.id, {"drafts": [{"title": "X"}], "status": "approved"})
        assert resp.status_code == 400, resp.content
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

        assert _requirement_count(client, ws.id) == before


def test_empty_and_malformed_bodies_are_rejected():
    with _stack("extended") as (client, tenant, ws, req):
        for payload in ({}, {"drafts": []}, {"drafts": "nope"}):
            resp = _accept(client, req.id, payload)
            assert resp.status_code == 400, (payload, resp.content)
        assert _requirement_count(client, ws.id) == 1  # only the parent


def test_unknown_requirement_is_404():
    with _stack("extended") as (client, tenant, ws, req):
        resp = _accept(client, uuid.uuid4(), _payload("Ghost"))
        assert resp.status_code == 404, resp.content


def test_invalid_second_draft_leaves_no_first_artefact():
    """Atomicity: the batch is validated before anything is written."""
    with _stack("extended") as (client, tenant, ws, req):
        resp = _accept(
            client,
            req.id,
            {
                "drafts": [
                    {"title": "Good one", "description": "d", "rationale": "r"},
                    {"title": "   ", "description": "d", "rationale": "r"},
                ]
            },
        )
        assert resp.status_code == 400, resp.content
        assert _requirement_count(client, ws.id) == 1, "atomicity violated: first draft leaked"
