"""Issue #1089 — REST surface for the pending-review queue.

``GET /api/v1/reviews/pending/`` and
``GET /api/v1/workspaces/<id>/reviews/pending/`` both 404'd while the MCP tool
``review.list_pending`` existed and worked. These tests drive the real HTTP +
service + DB stack, because the gap was precisely the missing transport.

Covered:

* the happy path on both routes (identical shape, identical rows);
* a real AI proposal — the item a derivation created in ``"proposed"`` — is in
  the queue and carries its ``proposed_by``/``proposed_at`` provenance;
* ``?state=proposed`` narrows the queue, ``?item_type=`` filters by type;
* pagination envelope and a clamped ``page_size``;
* the negative cases the DoD names: a **foreign workspace** (another tenant),
  a workspace the caller holds **no role** in, a **cross-tenant** workspace id
  on the flat route, a missing role, a missing/malformed ``workspace_id``, and
  the canonical error envelope on every one of them.
"""
from __future__ import annotations

import uuid

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from application.ai_proposal_service import AI_DERIVATION_LABEL
from application.requirement_service import RequirementService
from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER, UserRole
from auth_tenancy.context import AuthContext
from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from workflow.services import create_default_workflow

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET="test-secret-not-a-real-key-1089",
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)

_PASSWORD = "hunter2pass-1089"

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


def _make_workspace(tenant: Tenant, name: str, preset: str = "standard") -> Workspace:
    set_request_tenant(tenant.id)
    try:
        ws = Workspace.objects.create(
            tenant=tenant, name=name, preset={"name": preset}
        )
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


@pytest.fixture
def env():
    """Tenant + admin/editor/viewer identities + a provisioned workspace."""
    tenant = Tenant.objects.create(
        name="RQ Tenant", slug=f"rq-{uuid.uuid4().hex[:8]}", is_active=True
    )
    workspace = _make_workspace(tenant, "RQ WS")
    _provision(workspace, preset="extended")

    admin = _make_user(tenant, "rq-admin")
    editor = _make_user(tenant, "rq-editor")
    viewer = _make_user(tenant, "rq-viewer")
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
    return {
        "tenant": tenant,
        "workspace": workspace,
        "admin": admin,
        "editor": editor,
        "viewer": viewer,
    }


def _ctx(user: User, roles: tuple[str, ...]) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant_id,
        active_roles=roles,
        auth_method="test",
        tenant_name="rq",
    )


def _create_proposal(env, title: str = "AI-proposed requirement") -> str:
    """Persist a Requirement in the ``"proposed"`` state the way #1089 makes an
    AI derivation persist one, and return its id."""
    svc_ctx = _ctx(env["editor"], ("editor",))
    workspace = env["workspace"]
    set_request_tenant(env["tenant"].id)
    try:
        from application.ai_proposal_service import resolve_proposal_authoring

        authoring = resolve_proposal_authoring(
            svc_ctx, item_type="Requirement", workspace_id=workspace.id
        )
        req = RequirementService().create_requirement(
            workspace_id=workspace.id,
            title=title,
            ctx=authoring.create_context,
        )
    finally:
        clear_request_tenant()
    return str(req.id)


def _assert_envelope(body: dict, code: str) -> None:
    """The canonical error envelope (REQ-L2-RA-009) carries ``error.code``."""
    assert "error" in body, body
    assert body["error"]["code"] == code, body


# ---------------------------------------------------------------------------
# happy path — both routes, one shape
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
def test_flat_route_lists_the_pending_proposal(env):
    created = _create_proposal(env)
    admin_client = _login(env["admin"])

    resp = admin_client.get(
        f"/api/v1/reviews/pending/?workspace_id={env['workspace'].id}"
    )

    assert resp.status_code == 200, resp.content
    body = resp.json()
    # StandardPagination envelope.
    for key in ("count", "next", "previous", "page_size", "max_page_size", "results"):
        assert key in body, body
    rows = {row["item_id"]: row for row in body["results"]}
    assert created in rows, body
    row = rows[created]
    assert row["item_type"] == "Requirement"
    assert row["current_state"] == "proposed"
    assert row["is_proposal"] is True
    # The origin marker a human needs: who proposed it, and that it is AI.
    assert row["proposed_by"] == AI_DERIVATION_LABEL
    assert row["proposed_at"]


@override_settings(**_JWT_OVERRIDES)
def test_workspace_scoped_route_answers_identically(env):
    """Both routes exist because both 404'd (#1089); they must not diverge."""
    admin_client = _login(env["admin"])
    _create_proposal(env)
    ws = env["workspace"].id

    flat = admin_client.get(f"/api/v1/reviews/pending/?workspace_id={ws}")
    nested = admin_client.get(f"/api/v1/workspaces/{ws}/reviews/pending/")

    assert flat.status_code == 200, flat.content
    assert nested.status_code == 200, nested.content
    assert flat.json() == nested.json()


@override_settings(**_JWT_OVERRIDES)
def test_collection_root_answers_like_the_flat_pending_route(env):
    """#1177: ``GET /api/v1/reviews/`` is the collection root for the same queue.

    The root and ``/reviews/pending/`` are one handler, one service, one
    envelope — the root is not a second, weaker list and not a 404 (the
    measured #1177 symptom).
    """
    admin_client = _login(env["admin"])
    _create_proposal(env)
    ws = env["workspace"].id

    root = admin_client.get(f"/api/v1/reviews/?workspace_id={ws}")
    pending = admin_client.get(f"/api/v1/reviews/pending/?workspace_id={ws}")

    assert root.status_code == 200, root.content
    assert pending.status_code == 200, pending.content
    assert root.json() == pending.json()


@override_settings(**_JWT_OVERRIDES)
def test_state_narrowing_selects_only_proposals(env):
    admin_client = _login(env["admin"])
    proposal_id = _create_proposal(env, "The AI proposal")
    set_request_tenant(env["tenant"].id)
    try:
        plain = RequirementService().create_requirement(
            workspace_id=env["workspace"].id,
            title="Hand written",
            ctx=_ctx(env["editor"], ("editor",)),
        )
        plain_id = str(plain.id)
    finally:
        clear_request_tenant()

    resp = admin_client.get(
        f"/api/v1/workspaces/{env['workspace'].id}/reviews/pending/?state=proposed"
    )

    assert resp.status_code == 200, resp.content
    ids = {row["item_id"] for row in resp.json()["results"]}
    assert proposal_id in ids
    assert plain_id not in ids, "the state filter must actually narrow"


@override_settings(**_JWT_OVERRIDES)
def test_item_type_filter(env):
    _create_proposal(env)
    admin_client = _login(env["admin"])

    resp = admin_client.get(
        f"/api/v1/workspaces/{env['workspace'].id}/reviews/pending/"
        "?item_type=Adr"
    )

    assert resp.status_code == 200, resp.content
    assert resp.json()["count"] == 0, resp.content


@override_settings(**_JWT_OVERRIDES)
def test_pagination_envelope_and_clamped_page_size(env):
    admin_client = _login(env["admin"])
    for i in range(3):
        _create_proposal(env, f"Proposal {i}")

    resp = admin_client.get(
        f"/api/v1/workspaces/{env['workspace'].id}/reviews/pending/"
        "?page_size=2&page=1"
    )

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["count"] == 3
    assert len(body["results"]) == 2
    assert body["page_size"] == 2
    assert body["next"] is not None
    assert body["previous"] is None

    over = admin_client.get(
        f"/api/v1/workspaces/{env['workspace'].id}/reviews/pending/?page_size=5000"
    )
    assert over.status_code == 200, over.content
    assert over.json()["page_size"] == over.json()["max_page_size"] == 100


@override_settings(**_JWT_OVERRIDES)
def test_second_page_differs_from_the_first(env):
    admin_client = _login(env["admin"])
    for i in range(3):
        _create_proposal(env, f"Proposal {i}")
    url = f"/api/v1/workspaces/{env['workspace'].id}/reviews/pending/?page_size=2"

    first = admin_client.get(f"{url}&page=1").json()
    second = admin_client.get(f"{url}&page=2").json()

    assert {r["item_id"] for r in first["results"]} != {
        r["item_id"] for r in second["results"]
    }
    assert second["previous"] is not None
    assert second["next"] is None


# ---------------------------------------------------------------------------
# negative cases
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
def test_missing_workspace_id_is_400(env):
    admin_client = _login(env["admin"])
    resp = admin_client.get("/api/v1/reviews/pending/")

    assert resp.status_code == 400, resp.content
    _assert_envelope(resp.json(), "VALIDATION_ERROR")
    assert "workspace_id" in resp.json()["error"]["message"]


@override_settings(**_JWT_OVERRIDES)
def test_malformed_workspace_id_is_400(env):
    admin_client = _login(env["admin"])
    resp = admin_client.get("/api/v1/reviews/pending/?workspace_id=kaputt")

    assert resp.status_code == 400, resp.content
    _assert_envelope(resp.json(), "VALIDATION_ERROR")
    # The malformed value is never echoed back (#271).
    assert "kaputt" not in resp.json()["error"]["message"]


@override_settings(**_JWT_OVERRIDES)
def test_cross_tenant_workspace_is_404(env):
    """A workspace in another tenant is indistinguishable from a non-existent
    one — 404, never an empty 200 that confirms it exists."""
    admin_client = _login(env["admin"])
    other_tenant = Tenant.objects.create(
        name="Other", slug=f"other-{uuid.uuid4().hex[:8]}", is_active=True
    )
    other_ws = _make_workspace(other_tenant, "Other WS")

    flat = admin_client.get(f"/api/v1/reviews/pending/?workspace_id={other_ws.id}")
    nested = admin_client.get(f"/api/v1/workspaces/{other_ws.id}/reviews/pending/")

    assert flat.status_code == 404, flat.content
    _assert_envelope(flat.json(), "NOT_FOUND")
    assert nested.status_code == 404, nested.content
    _assert_envelope(nested.json(), "NOT_FOUND")


@override_settings(**_JWT_OVERRIDES)
def test_unknown_workspace_is_404(env):
    admin_client = _login(env["admin"])
    resp = admin_client.get(
        f"/api/v1/workspaces/{uuid.uuid4()}/reviews/pending/"
    )

    assert resp.status_code == 404, resp.content
    _assert_envelope(resp.json(), "NOT_FOUND")


@override_settings(**_JWT_OVERRIDES)
def test_caller_without_a_role_in_the_workspace_is_403(env):
    """A same-tenant user who is not a member of this workspace must not be
    able to enumerate its review queue. The workspace arrives as a path
    parameter, and ``auth_tenancy.workspace_scope`` narrows the caller's
    roles to it, so a non-member resolves to no roles at all — a 403 from the
    RBAC layer, and the service's own membership gate is the backstop behind
    it."""
    tenant = env["tenant"]
    stranger = _make_user(tenant, "rq-stranger")
    other_ws = _make_workspace(tenant, "Stranger's own WS")
    _provision(other_ws, preset="extended")
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=stranger, workspace=other_ws, role=ROLE_ADMIN
        )
    finally:
        clear_request_tenant()

    resp = _login(stranger).get(f"/api/v1/workspaces/{env['workspace'].id}/reviews/pending/")

    assert resp.status_code == 403, resp.content
    _assert_envelope(resp.json(), "PERMISSION_DENIED")
    # Either the RBAC layer ("no active role permits 'read'") or the service's
    # own membership gate ("you hold no role in workspace ...") may be the one
    # that refuses; both must answer 403 PERMISSION_DENIED, never an empty 200.
    assert "role" in resp.json()["error"]["message"]


@override_settings(**_JWT_OVERRIDES)
def test_viewer_is_403(env):
    """``PROPOSED_ROLES`` is (editor, approver, admin): a viewer cannot confirm
    or discard any queue entry, so the list is noise for them."""
    _create_proposal(env)

    resp = _login(env["viewer"]).get(
        f"/api/v1/workspaces/{env['workspace'].id}/reviews/pending/"
    )

    assert resp.status_code == 403, resp.content
    _assert_envelope(resp.json(), "PERMISSION_DENIED")
    assert "requires one of the roles" in resp.json()["error"]["message"]


@override_settings(**_JWT_OVERRIDES)
def test_editor_is_allowed(env):
    resp = _login(env["editor"]).get(
        f"/api/v1/workspaces/{env['workspace'].id}/reviews/pending/"
    )
    assert resp.status_code == 200, resp.content


@override_settings(**_JWT_OVERRIDES)
def test_unauthenticated_is_401(env):
    resp = APIClient().get(
        f"/api/v1/workspaces/{env['workspace'].id}/reviews/pending/"
    )
    assert resp.status_code == 401, resp.content


@override_settings(**_JWT_OVERRIDES)
def test_flat_route_rejects_a_foreign_workspace_too(env):
    admin_client = _login(env["admin"])
    other_tenant = Tenant.objects.create(
        name="Other2", slug=f"other2-{uuid.uuid4().hex[:8]}", is_active=True
    )
    other_ws = _make_workspace(other_tenant, "Other WS 2")

    resp = admin_client.get(f"/api/v1/reviews/pending/?workspace_id={other_ws.id}")

    assert resp.status_code == 404, resp.content
    _assert_envelope(resp.json(), "NOT_FOUND")


# ---------------------------------------------------------------------------
# the queue is reachable and actionable through the existing transitions route
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
def test_a_listed_proposal_can_be_confirmed_through_transitions(env):
    """DoD #2: the UI can act on a queue entry without a bespoke review-action
    route. The existing ``POST /requirements/{id}/transitions/`` is the action
    surface (see review_views' docstring); the confirm target is the graph's
    initial state, which the proposal graph makes 'draft'."""
    admin_client = _login(env["admin"])
    created = _create_proposal(env)

    queue = admin_client.get(
        f"/api/v1/workspaces/{env['workspace'].id}/reviews/pending/?state=proposed"
    )
    assert created in {r["item_id"] for r in queue.json()["results"]}

    detail = admin_client.get(f"/api/v1/requirements/{created}/transitions/")
    assert detail.status_code == 200, detail.content
    allowed = detail.json()["allowed_transitions"]
    confirm = next(
        t for t in allowed if not t["requires_change_reason"]
    )
    # The provenance the queue advertises is the same one this route reports.
    assert detail.json()["proposed_by"] == AI_DERIVATION_LABEL

    resp = admin_client.post(
        f"/api/v1/requirements/{created}/transitions/",
        {"target_state": confirm["target_state"]},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["new_state"] == confirm["target_state"]

    after = admin_client.get(
        f"/api/v1/workspaces/{env['workspace'].id}/reviews/pending/?state=proposed"
    )
    assert created not in {r["item_id"] for r in after.json()["results"]}