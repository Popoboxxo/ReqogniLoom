"""Issue #1095 (+ the #1089 field-filling remainder) - the server-side persist
endpoint for accepted AI-derived requirement drafts.

The defect this file pins
=========================
``DeriveRequirementsPanel.tsx:140`` persisted the accepted drafts with
``requirementsApi.create`` from a **user** principal and then built the
``derives-from`` TraceLink by hand. ``workflow.services.initial_state_for``
seeds ``"proposed"`` only when ``ctx.actor_type == "agent"``, which the auth
layer decides - a human pressing "KI-Ableitung" holds a Bearer token, so
``actor_type == "user"`` and every AI-derived Requirement was born ``draft``:
the rows existed, the panel reported success, and nobody was ever shown them
for approval (#1089).

The fix is a server-side persist endpoint,
``POST /api/v1/needs/{pk}/derive-requirements/accept/``, which resolves the
*authoring* context through the single seam in
``application.ai_proposal_service`` and hands ``authoring.create_context`` to
the creation service. These tests drive the real HTTP + service + DB stack
(the gap was precisely the missing transport), so they assert what the wire
actually answers, not what a service call would.

Covered:

* the happy path - 201, an artefact whose workflow state really is
  ``"proposed"``, the ``proposal`` block naming ``ai-derivation``, the
  ``derives-from`` TraceLink back to the need, and the
  ``ai_elicit``/``origin`` custom-field markers a human reads off the row
  (the #1089 remainder);
* the created proposal is visible in the pending-review queue;
* a ``minimal``-preset workspace (a graph with no ``"proposed"`` state) is a
  400 with the plain-text reason and creates **nothing** - never a silent
  downgrade to ``draft``;
* the #851 envelope for a client-set ``status``/``from_ai`` and for an
  undeclared key inside a draft entry, in both cases creating nothing;
* a malformed body, an unknown need, an unauthenticated call and a need in
  another tenant's scope;
* atomicity: a failure on the second draft leaves no first-draft artefact.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from application.ai_proposal_service import AI_DERIVATION_LABEL
from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER, UserRole
from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Artifact,
    Requirement,
    StakeholderNeed,
    Tenant,
    TraceLink,
    User,
    Workspace,
)
from workflow.services import create_default_workflow

_JWT_OVERRIDES = {
    "AUTH_JWT_SECRET": "test-secret-not-a-real-key-1095",
    "AUTH_JWT_ISSUER": "reqflow",
    "AUTH_JWT_AUDIENCE": "reqflow-api",
    "AUTH_JWT_TTL_SECONDS": 3600,
}

_PASSWORD = "hunter2pass-1095"

_ACCEPT_URL = "/api/v1/needs/{need}/derive-requirements/accept/"

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# fixtures / helpers - the same shape as the sibling #1089 suites, so a
# reviewer can diff them against each other
# ---------------------------------------------------------------------------


def _provision(workspace: Workspace, preset: str = "extended") -> None:
    """Give the workspace a real Requirement workflow for *preset*."""
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


def _make_workspace(tenant: Tenant, name: str, preset: str = "standard") -> Workspace:
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


def _make_need(tenant: Tenant, workspace: Workspace, title: str) -> StakeholderNeed:
    """Create a StakeholderNeed straight through the ORM.

    Mirrors the sibling suite's helper: the derivation links the derived
    Requirement back to the need's *Artifact* (``TraceLinkService`` cannot
    resolve a bare StakeholderNeed id), and the service's create path publishes
    domain events this test does not need.
    """
    set_request_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            workspace=workspace, artifact_type="StakeholderNeed", tenant_id=tenant.id
        )
        return StakeholderNeed.objects.create(
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


def _accept(client: APIClient, need_id, payload: dict):
    """POST the accepted-draft payload for *need_id*."""
    return client.post(_ACCEPT_URL.format(need=need_id), payload, format="json")


def _payload(*titles: str) -> dict:
    """Build the request body for the given draft titles."""
    return {
        "drafts": [
            {
                "title": title,
                "description": f"description of {title}",
                "rationale": f"rationale of {title}",
            }
            for title in titles
        ]
    }


def _assert_envelope(response, code: str) -> dict:
    """The canonical error envelope (REQ-L2-RA-009) carries ``error.code``."""
    body = response.json()
    assert "error" in body, body
    assert body["error"]["code"] == code, body
    return body


def _details(response) -> dict:
    """Return ``{field: errors}`` from a VALIDATION_ERROR envelope."""
    return {d["field"]: d["errors"] for d in response.json()["error"]["details"]}


@contextmanager
def _tenant_scope(tenant_id):
    """Arm the tenant thread-local for direct ORM reads (REQ-L2-PL-002).

    ``TenantManager`` raises without one, and a count that answered 0 for the
    wrong reason would prove nothing about the rollbacks these tests assert.
    """
    set_request_tenant(tenant_id)
    try:
        yield
    finally:
        clear_request_tenant()


def _requirement_count(tenant_id) -> int:
    with _tenant_scope(tenant_id):
        return Requirement.objects.count()


@pytest.fixture
def tenant():
    return Tenant.objects.create(
        name="Accept Tenant", slug=f"acc-{uuid.uuid4().hex[:8]}", is_active=True
    )


@pytest.fixture
def workspace(tenant):
    return _make_workspace(tenant, "Accept WS")


@pytest.fixture
def env(tenant, workspace):
    """Tenant + admin/editor/viewer identities + a proposal-capable workspace."""
    _provision(workspace, preset="extended")
    admin = _make_user(tenant, "acc-admin")
    editor = _make_user(tenant, "acc-editor")
    viewer = _make_user(tenant, "acc-viewer")
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        UserRole.objects.create(
            tenant=tenant, user=editor, workspace=workspace, role=ROLE_EDITOR
        )
        UserRole.objects.create(
            tenant=tenant, user=viewer, workspace=workspace, role=ROLE_VIEWER
        )
    finally:
        clear_request_tenant()
    need = _make_need(tenant, workspace, "Operators need a throughput dashboard")
    return {
        "tenant": tenant,
        "workspace": workspace,
        "admin": admin,
        "editor": editor,
        "viewer": viewer,
        "need": need,
    }


# ---------------------------------------------------------------------------
# happy path - the artefact is a reviewable AI proposal
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
def test_accepted_drafts_become_proposed_ai_artefacts(env):
    title = "The system shall show throughput"
    response = _accept(_login(env["editor"]), env["need"].id, _payload(title))

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["count"] == 1
    created = body["created"][0]
    requirement_id = created["id"]

    # The state the workflow engine actually stored - not the intended one.
    assert created["status"] == "proposed"
    with _tenant_scope(env["tenant"].id):
        from workflow import state_reader

        stored_state = state_reader.current_state(
            "Requirement", uuid.UUID(requirement_id)
        )
        created_requirement = Requirement.objects.get(id=requirement_id)
        custom_fields = created_requirement.artifact.custom_fields
        link = TraceLink.objects.get(
            source_id=created_requirement.artifact_id,
            target_id=env["need"].artifact_id,
            link_type="derives-from",
        )
    assert stored_state == "proposed", (
        "an AI draft accepted by a human must land in 'proposed', not 'draft' "
        "- otherwise nobody is ever shown the proposal (#1089)"
    )

    # The proposal block is always present, so a client cannot mistake a plain
    # draft for a reviewable proposal.
    assert body["proposal"]["is_proposal"] is True
    assert body["proposal"]["supported"] is True
    assert body["proposal"]["reason"] == ""
    # The origin marker a reviewer needs: WHO proposed it.
    assert body["proposal"]["proposed_by"] == AI_DERIVATION_LABEL
    assert created["proposal"]["proposed_by"] == AI_DERIVATION_LABEL

    # The #1089 field-filling remainder: the artefact itself says AI wrote it.
    assert custom_fields["ai_elicit"] is True
    assert custom_fields["origin"] == "ai_generated"

    # The accepted content survived the persist.
    assert created_requirement.title == title
    assert created_requirement.description == f"description of {title}"
    assert created_requirement.rationale == f"rationale of {title}"

    # The derives-from TraceLink back to the need is built server-side; the
    # client no longer has to create it (and can no longer orphan an artefact
    # by failing half-way through its own loop).
    assert created["trace_link_id"] == str(link.id)


@override_settings(**_JWT_OVERRIDES)
def test_multiple_drafts_are_all_created_and_linked(env):
    response = _accept(
        _login(env["editor"]),
        env["need"].id,
        _payload("First derived requirement", "Second derived requirement"),
    )

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["count"] == len(body["created"]) == 2
    assert {entry["status"] for entry in body["created"]} == {"proposed"}
    with _tenant_scope(env["tenant"].id):
        for entry in body["created"]:
            requirement = Requirement.objects.get(id=entry["id"])
            assert TraceLink.objects.filter(
                source_id=requirement.artifact_id,
                target_id=env["need"].artifact_id,
                link_type="derives-from",
            ).exists()


@override_settings(**_JWT_OVERRIDES)
def test_created_proposal_appears_in_the_pending_review_queue(env):
    """The actual point of the fix: the artefact is now shown to a reviewer."""
    response = _accept(_login(env["editor"]), env["need"].id, _payload("Reviewable draft"))
    assert response.status_code == 201, response.content
    created_id = response.json()["created"][0]["id"]

    admin_client = _login(env["admin"])
    queue = admin_client.get(
        f"/api/v1/reviews/pending/?workspace_id={env['workspace'].id}&state=proposed"
    )

    assert queue.status_code == 200, queue.content
    rows = {row["item_id"]: row for row in queue.json()["results"]}
    assert created_id in rows, queue.content
    row = rows[created_id]
    assert row["item_type"] == "Requirement"
    assert row["current_state"] == "proposed"
    assert row["is_proposal"] is True
    # The provenance the queue advertises is the derivation's, not a human's.
    assert row["proposed_by"] == AI_DERIVATION_LABEL
    assert row["proposed_at"]


@override_settings(**_JWT_OVERRIDES)
def test_a_viewer_may_not_persist_accepted_drafts(env):
    """Role check: ``RequirementService.create_requirement`` gates on WRITE."""
    response = _accept(_login(env["viewer"]), env["need"].id, _payload("Viewer draft"))

    assert response.status_code == 403, response.content
    _assert_envelope(response, "PERMISSION_DENIED")
    assert _requirement_count(env["tenant"].id) == 0


# ---------------------------------------------------------------------------
# a graph that cannot express a proposal is a hard 400, never a silent draft
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
def test_minimal_preset_workspace_is_400_and_creates_nothing(tenant):
    """``minimal`` is in ``SCHEMAS_WITHOUT_PROPOSED``: its graph has no
    ``"proposed"`` state, so the endpoint must refuse rather than quietly create
    an unreviewable draft (#1089's contract for this route)."""
    workspace = _make_workspace(tenant, "Minimal WS", preset="minimal")
    _provision(workspace, preset="minimal")
    editor = _make_user(tenant, "min-editor")
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=editor, workspace=workspace, role=ROLE_EDITOR
        )
    finally:
        clear_request_tenant()
    need = _make_need(tenant, workspace, "A need in a minimal workspace")

    response = _accept(_login(editor), need.id, _payload("Minimal-workspace draft"))

    assert response.status_code == 400, response.content
    body = _assert_envelope(response, "VALIDATION_ERROR")
    # Human-readable and un-mangled - never a bare "downgraded to draft".
    assert "proposed" in body["error"]["message"]
    assert "NOT a reviewable proposal" in body["error"]["message"]
    assert _requirement_count(tenant.id) == 0, (
        "the refusal must be atomic: nothing at all may be persisted"
    )


# ---------------------------------------------------------------------------
# negative transport cases
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
def test_unknown_need_is_404(env):
    response = _accept(
        _login(env["editor"]), uuid.uuid4(), _payload("Draft for a missing need")
    )

    assert response.status_code == 404, response.content
    _assert_envelope(response, "NOT_FOUND")
    assert _requirement_count(env["tenant"].id) == 0


@override_settings(**_JWT_OVERRIDES)
def test_a_need_in_another_tenant_is_404(env):
    """Tenant scoping: a foreign need is indistinguishable from a missing one."""
    other_tenant = Tenant.objects.create(
        name="Other Tenant", slug=f"other-{uuid.uuid4().hex[:8]}", is_active=True
    )
    other_workspace = _make_workspace(other_tenant, "Other WS")
    _provision(other_workspace, preset="extended")
    foreign_need = _make_need(
        other_tenant, other_workspace, "A need that belongs to someone else"
    )

    response = _accept(_login(env["editor"]), foreign_need.id, _payload("Foreign draft"))

    assert response.status_code == 404, response.content
    _assert_envelope(response, "NOT_FOUND")
    assert _requirement_count(env["tenant"].id) == 0


@pytest.mark.parametrize("forbidden_flag", ["status", "from_ai"])
@override_settings(**_JWT_OVERRIDES)
def test_client_supplied_state_flags_are_rejected(env, forbidden_flag):
    """#269/#851: the server derives the state and the AI marker.

    A client-settable ``status`` would force a workflow state the workspace's
    graph may not even have; a settable ``from_ai`` would let hand-written
    content wear an AI stamp. Both are rejected - a silently dropped key would
    be the #1089 hole with the sign reversed (an unlabelled artefact that looks
    labelled).
    """
    payload = _payload("Draft with a client flag")
    payload[forbidden_flag] = "proposed" if forbidden_flag == "status" else True

    response = _accept(_login(env["editor"]), env["need"].id, payload)

    assert response.status_code == 400, response.content
    _assert_envelope(response, "VALIDATION_ERROR")
    assert _details(response)[forbidden_flag] == ["Unknown field."]
    assert _requirement_count(env["tenant"].id) == 0


@override_settings(**_JWT_OVERRIDES)
def test_unknown_key_inside_a_draft_entry_is_rejected(env):
    payload = _payload("Draft with a smuggled key")
    payload["drafts"][0]["not_a_real_draft_key"] = "dropped"

    response = _accept(_login(env["editor"]), env["need"].id, payload)

    assert response.status_code == 400, response.content
    _assert_envelope(response, "VALIDATION_ERROR")
    assert _details(response)["not_a_real_draft_key"] == ["Unknown field."]
    assert _requirement_count(env["tenant"].id) == 0


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"drafts": []},
        {"drafts": "not-a-list"},
        {"drafts": [{"description": "no title at all"}]},
        {"drafts": [{"title": "   "}]},
        {"drafts": ["not-an-object"]},
    ],
)
@override_settings(**_JWT_OVERRIDES)
def test_malformed_bodies_are_400(env, payload):
    response = _accept(_login(env["editor"]), env["need"].id, payload)

    assert response.status_code == 400, response.content
    _assert_envelope(response, "VALIDATION_ERROR")
    assert _requirement_count(env["tenant"].id) == 0


@override_settings(**_JWT_OVERRIDES)
def test_unauthenticated_is_401(env):
    response = _accept(APIClient(), env["need"].id, _payload("Anonymous draft"))

    assert response.status_code == 401, response.content
    assert _requirement_count(env["tenant"].id) == 0


# ---------------------------------------------------------------------------
# atomicity
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
def test_a_failure_on_the_second_draft_leaves_no_artefact_behind(env, monkeypatch):
    """One ``transaction.atomic()`` around the whole batch (REQ-L3-PL003-002).

    The MCP write loop deliberately keeps its per-draft savepoints isolated so
    already-written drafts survive; the REST accept path is the opposite
    contract - it is ONE accepted batch, so "2 of 3 artefacts persisted" would
    be the #1095 partial-failure symptom in miniature.
    """
    from application.requirement_service import RequirementService

    real_create = RequirementService.create_requirement
    calls: list = []

    def _fail_on_second(self, workspace_id, title, ctx, **kwargs):
        calls.append(title)
        if len(calls) == 2:
            raise RuntimeError("simulated mid-batch failure")
        return real_create(self, workspace_id, title, ctx, **kwargs)

    monkeypatch.setattr(RequirementService, "create_requirement", _fail_on_second)

    response = _accept(
        _login(env["editor"]),
        env["need"].id,
        _payload("First draft", "Second draft"),
    )

    assert calls == ["First draft", "Second draft"], calls
    assert response.status_code == 500, response.content
    assert _requirement_count(env["tenant"].id) == 0, (
        "the first artefact must be rolled back with the failed batch"
    )
    with _tenant_scope(env["tenant"].id):
        assert TraceLink.objects.count() == 0
