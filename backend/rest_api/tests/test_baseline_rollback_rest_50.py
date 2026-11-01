"""Plan F F4.4 (PR-F11b) — REST surface for the additive baseline rollback.

The service half landed in PR-F11a (``application.baseline_rollback_service``,
ADR-025 R1-R9). This module pins the *transport* half exactly as plan §F4.4
specifies it:

``GET    /api/v1/baselines/{id}/rollback-preview/``  -> 200 (viewer allowed)
``POST   /api/v1/baselines/{id}/rollback-request/``  -> 201 (editor)
``POST   /api/v1/baselines/{id}/rollback/``          -> 200 (editor, humans only)

The setup uses the real services throughout (tenant, workspace, baseline build,
change-request CCB transitions, requirement updates) so the tests exercise the
production paths rather than a mocked plan.

Requirements:
- ADR-025, REQ-L2-BL-001, REQ-L3-RA004-001 (preset gate), SEC-RB-01/05/08.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from application import baseline_rollback_service as rollback_module
from application.baseline_rollback_service import BaselineRollbackService
from application.change_request_service import ChangeRequestService
from application.requirement_service import RequirementService
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER, UserRole
from auth_tenancy.services.authentication import AuthenticationService
from baseline.services import build as baseline_build
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _user(tenant: Tenant, username: str) -> User:
    user = User.objects.create(
        username=username, email=f"{username}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    return user


def _grant(tenant: Tenant, user: User, workspace: Workspace, role: str) -> None:
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=workspace, role=role
        )
    finally:
        clear_request_tenant()


def _login(user: User) -> APIClient:
    client = APIClient()
    response = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert response.status_code == 200, response.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.json()['token']}")
    return client


def _workspace(tenant: Tenant, name: str, tier: str = "standard") -> Workspace:
    set_request_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant,
            name=f"{name}-{uuid.uuid4().hex[:8]}",
            preset={"name": tier},
        )
    finally:
        clear_request_tenant()


def _provision_workflows(tenant: Tenant, workspace: Workspace) -> None:
    """The two definitions this suite needs (cheap and targeted)."""
    from workflow.services import create_default_workflow

    set_request_tenant(tenant.id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset="ccb_approval",
            item_type="ChangeRequest",
            tenant_id=tenant.id,
        )
        create_default_workflow(
            workspace_id=workspace.id,
            preset="standard",
            item_type="Requirement",
            tenant_id=tenant.id,
        )
    finally:
        clear_request_tenant()


def _ctx(user: User, workspace: Workspace) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant_id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace.id,
    )


def _make_requirement(
    tenant: Tenant, workspace: Workspace, title: str = "Original"
) -> Requirement:
    set_request_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        return Requirement.objects.create(
            tenant=tenant,
            artifact=artifact,
            workspace=workspace,
            uid=f"REQ-{uuid.uuid4().hex[:8]}",
            title=title,
            description="d",
            rationale="because",
            category="functional",
        )
    finally:
        clear_request_tenant()


def _baseline(tenant: Tenant, workspace: Workspace, name: str = "B1"):
    set_request_tenant(tenant.id)
    try:
        return baseline_build(
            scope="project",
            workspace_id=workspace.id,
            name=name,
            tenant_id=tenant.id,
            created_by="f4-4-rest-test",
        )
    finally:
        clear_request_tenant()


def _bare_baseline(tenant: Tenant, workspace: Workspace):
    """Insert a baseline row without building a delta (preset-gate fixture)."""
    from baseline.models import BaselineSnapshot

    set_request_tenant(tenant.id)
    try:
        snapshot = BaselineSnapshot.unscoped.create(
            tenant=tenant,
            workspace_id=workspace.id,
            scope="project",
            name=f"min-{uuid.uuid4().hex[:8]}",
        )
        return snapshot.id
    finally:
        clear_request_tenant()


def _rename(requirement: Requirement, ctx: AuthContext, title: str) -> None:
    RequirementService().update_requirement(
        requirement.id, ctx, title=title, change_reason="edit after baseline"
    )


def _approve_cr(ctx: AuthContext, cr_id) -> None:
    service = ChangeRequestService()
    service.transition_status(cr_id, "submitted", ctx, change_reason="please review")
    service.transition_status(cr_id, "under_review", ctx, change_reason="picked up")
    service.transition_status(cr_id, "approved", ctx, change_reason="approved")


def _draft_cr(baseline_id, ctx: AuthContext):
    return BaselineRollbackService().request(
        baseline_id, ctx, change_reason="restore the baseline"
    )


@pytest.fixture
def env(tenant: Tenant, authed_client: APIClient):
    """``standard`` workspace + admin/editor/viewer users, workflows provisioned."""
    workspace = _workspace(tenant, "rollback-rest")
    _provision_workflows(tenant, workspace)
    admin = User.objects.get(username="bundleadmin")
    _grant(tenant, admin, workspace, ROLE_ADMIN)
    editor = _user(tenant, f"editor-{uuid.uuid4().hex[:8]}")
    _grant(tenant, editor, workspace, ROLE_EDITOR)
    viewer = _user(tenant, f"viewer-{uuid.uuid4().hex[:8]}")
    _grant(tenant, viewer, workspace, ROLE_VIEWER)
    return {
        "workspace": workspace,
        "admin": admin,
        "editor": editor,
        "viewer": viewer,
        "ctx": _ctx(admin, workspace),
    }


def _preview(client: APIClient, baseline_id):
    return client.get(f"/api/v1/baselines/{baseline_id}/rollback-preview/")


def _rollback_request(client: APIClient, baseline_id, **payload):
    return client.post(
        f"/api/v1/baselines/{baseline_id}/rollback-request/", payload, format="json"
    )


def _rollback(client: APIClient, baseline_id, change_request_id):
    return client.post(
        f"/api/v1/baselines/{baseline_id}/rollback/",
        {"change_request_id": str(change_request_id)},
        format="json",
    )


def _changed_baseline(env, tenant: Tenant):
    """Baseline whose single requirement was renamed afterwards."""
    requirement = _make_requirement(tenant, env["workspace"])
    baseline_id = _baseline(tenant, env["workspace"])
    _rename(requirement, env["ctx"], "Changed")
    return requirement, baseline_id


# ---------------------------------------------------------------------------
# GET rollback-preview
# ---------------------------------------------------------------------------


class TestRollbackPreview:
    def test_preview_returns_plan_for_viewer(
        self, env, tenant: Tenant, authed_client: APIClient
    ) -> None:
        """A viewer may preview: it is a read (R8 allows agents and viewers)."""
        requirement, baseline_id = _changed_baseline(env, tenant)

        response = _preview(_login(env["viewer"]), baseline_id)

        assert response.status_code == 200, response.content
        body = response.json()
        assert body["baseline_id"] == str(baseline_id)
        assert body["summary"]["restore"] == 1
        assert body["summary"]["unchanged"] == 0
        item = next(
            row
            for row in body["items"]
            if row["item_id"] == str(requirement.artifact_id)
        )
        assert item["action"] == "restore"
        assert item["artifact_type"] == "Requirement"
        assert item["field_changes"]["title"] == {
            "current": "Changed",
            "baseline": "Original",
        }
        assert item["unrestorable_fields"] == []
        assert isinstance(item["current_version"], int)
        assert body["links_to_recreate"] == []
        assert body["skipped_links"] == []

    def test_unknown_baseline_is_404(self, env, authed_client: APIClient) -> None:
        response = _preview(authed_client, uuid.uuid4())

        assert response.status_code == 404, response.content
        assert response.json()["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# POST rollback-request
# ---------------------------------------------------------------------------


class TestRollbackRequest:
    def test_request_creates_draft_change_request(
        self, env, tenant: Tenant, authed_client: APIClient
    ) -> None:
        _, baseline_id = _changed_baseline(env, tenant)

        response = _rollback_request(
            authed_client,
            baseline_id,
            change_reason="restore the baseline",
            title="Rollback please",
        )

        assert response.status_code == 201, response.content
        body = response.json()
        assert body["status"] == "draft"
        assert body["affected_items"] == 1
        assert uuid.UUID(body["change_request_id"])

    def test_request_without_change_reason_is_400(
        self, env, tenant: Tenant, authed_client: APIClient
    ) -> None:
        _, baseline_id = _changed_baseline(env, tenant)

        response = _rollback_request(authed_client, baseline_id, title="no reason")

        assert response.status_code == 400, response.content
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_request_rejects_an_unknown_body_field(
        self, env, tenant: Tenant, authed_client: APIClient
    ) -> None:
        """#851: an undeclared key is a 400, not a silently dropped input."""
        _, baseline_id = _changed_baseline(env, tenant)

        response = _rollback_request(
            authed_client,
            baseline_id,
            change_reason="restore",
            change_reasons="typo",
        )

        assert response.status_code == 400, response.content
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_request_on_unchanged_baseline_is_rollback_empty(
        self, env, tenant: Tenant, authed_client: APIClient
    ) -> None:
        _make_requirement(tenant, env["workspace"])
        baseline_id = _baseline(tenant, env["workspace"])

        response = _rollback_request(
            authed_client, baseline_id, change_reason="nothing to do"
        )

        assert response.status_code == 400, response.content
        assert response.json()["error"]["code"] == "ROLLBACK_EMPTY"

    def test_request_over_the_mass_limit_is_rollback_too_large(
        self,
        env,
        tenant: Tenant,
        authed_client: APIClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """R9 — the limit is enforced by the service, surfaced as 400 + code."""
        monkeypatch.setattr(rollback_module, "MAX_ROLLBACK_ITEMS", 0)
        _, baseline_id = _changed_baseline(env, tenant)

        response = _rollback_request(
            authed_client, baseline_id, change_reason="too big"
        )

        assert response.status_code == 400, response.content
        assert response.json()["error"]["code"] == "ROLLBACK_TOO_LARGE"

    def test_request_as_viewer_is_403(
        self, env, tenant: Tenant
    ) -> None:
        _, baseline_id = _changed_baseline(env, tenant)

        response = _rollback_request(
            _login(env["viewer"]), baseline_id, change_reason="restore"
        )

        assert response.status_code == 403, response.content
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# POST rollback (apply)
# ---------------------------------------------------------------------------


class TestRollbackApply:
    def test_apply_restores_the_baseline_state(
        self, env, tenant: Tenant, authed_client: APIClient
    ) -> None:
        requirement, baseline_id = _changed_baseline(env, tenant)
        cr = _approve_and_get(env["ctx"], baseline_id)

        response = _rollback(authed_client, baseline_id, cr.id)

        assert response.status_code == 200, response.content
        body = response.json()
        assert body["restored"] == 1
        assert body["reactivated"] == 0
        assert body["links_recreated"] == 0
        assert body["change_request_status"] == "implemented"
        assert body["skipped"] == []
        requirement.refresh_from_db()
        assert requirement.title == "Original"

    def test_apply_with_draft_change_request_is_409(
        self, env, tenant: Tenant, authed_client: APIClient
    ) -> None:
        _, baseline_id = _changed_baseline(env, tenant)
        cr = _draft_cr(baseline_id, env["ctx"])

        response = _rollback(authed_client, baseline_id, cr.id)

        assert response.status_code == 409, response.content
        assert response.json()["error"]["code"] == "ROLLBACK_NOT_APPROVED"

    def test_apply_twice_is_409_already_applied(
        self, env, tenant: Tenant, authed_client: APIClient
    ) -> None:
        _, baseline_id = _changed_baseline(env, tenant)
        cr = _approve_and_get(env["ctx"], baseline_id)
        first = _rollback(authed_client, baseline_id, cr.id)
        assert first.status_code == 200, first.content

        second = _rollback(authed_client, baseline_id, cr.id)

        assert second.status_code == 409, second.content
        assert second.json()["error"]["code"] == "ROLLBACK_ALREADY_APPLIED"

    def test_apply_after_a_further_change_is_409_plan_stale(
        self, env, tenant: Tenant, authed_client: APIClient
    ) -> None:
        """R3 — per-item version drift is reported item by item in ``details``."""
        requirement, baseline_id = _changed_baseline(env, tenant)
        cr = _approve_and_get(env["ctx"], baseline_id)
        _rename(requirement, env["ctx"], "Changed again")

        response = _rollback(authed_client, baseline_id, cr.id)

        assert response.status_code == 409, response.content
        error = response.json()["error"]
        assert error["code"] == "ROLLBACK_PLAN_STALE"
        assert isinstance(error["details"], list) and error["details"], error
        stale = error["details"][0]
        assert stale["item_id"] == str(requirement.artifact_id)
        assert "version_before" in stale and "current_version" in stale

    def test_apply_as_viewer_is_403(
        self, env, tenant: Tenant
    ) -> None:
        """R7 — WRITE per item is checked before the first write."""
        _, baseline_id = _changed_baseline(env, tenant)
        cr = _approve_and_get(env["ctx"], baseline_id)

        response = _rollback(_login(env["viewer"]), baseline_id, cr.id)

        assert response.status_code == 403, response.content
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"

    def test_apply_for_another_baseline_is_400(
        self, env, tenant: Tenant, authed_client: APIClient
    ) -> None:
        """R2 — the CR must be bound to *this* baseline."""
        requirement = _make_requirement(tenant, env["workspace"])
        baseline_id = _baseline(tenant, env["workspace"], name="B1")
        _rename(requirement, env["ctx"], "Changed")
        other_baseline = _baseline(tenant, env["workspace"], name="B2")
        _rename(requirement, env["ctx"], "Changed again")
        cr = _draft_cr(other_baseline, env["ctx"])
        _approve_cr(env["ctx"], cr.id)

        response = _rollback(authed_client, baseline_id, cr.id)

        assert response.status_code == 400, response.content
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_apply_with_unknown_change_request_is_404(
        self, env, tenant: Tenant, authed_client: APIClient
    ) -> None:
        _, baseline_id = _changed_baseline(env, tenant)

        response = _rollback(authed_client, baseline_id, uuid.uuid4())

        assert response.status_code == 404, response.content
        assert response.json()["error"]["code"] == "NOT_FOUND"


class TestRollbackIfMatchSyntaxGate:
    """E2.4: the POST routes parse ``If-Match`` (syntax only) but never compare it.

    The domain conflict protection is R2/R3/R5, not an entity tag on the
    baseline — a well-formed tag is therefore ignored rather than answered with
    412, while a malformed header is still a 400 request defect.
    """

    def test_malformed_if_match_is_400_on_request(
        self, env, tenant: Tenant, authed_client: APIClient
    ) -> None:
        _, baseline_id = _changed_baseline(env, tenant)

        response = authed_client.post(
            f"/api/v1/baselines/{baseline_id}/rollback-request/",
            {"change_reason": "restore"},
            format="json",
            HTTP_IF_MATCH="not-a-valid-tag",
        )

        assert response.status_code == 400, response.content
        assert response.json()["error"]["code"] == "INVALID_IF_MATCH"

    def test_malformed_if_match_is_400_on_apply(
        self, env, tenant: Tenant, authed_client: APIClient
    ) -> None:
        _, baseline_id = _changed_baseline(env, tenant)

        response = authed_client.post(
            f"/api/v1/baselines/{baseline_id}/rollback/",
            {"change_request_id": str(uuid.uuid4())},
            format="json",
            HTTP_IF_MATCH="not-a-valid-tag",
        )

        assert response.status_code == 400, response.content
        assert response.json()["error"]["code"] == "INVALID_IF_MATCH"

    def test_well_formed_if_match_is_ignored(
        self, env, tenant: Tenant, authed_client: APIClient
    ) -> None:
        requirement, baseline_id = _changed_baseline(env, tenant)
        cr = _approve_and_get(env["ctx"], baseline_id)

        response = authed_client.post(
            f"/api/v1/baselines/{baseline_id}/rollback/",
            {"change_request_id": str(cr.id)},
            format="json",
            HTTP_IF_MATCH='"99"',
        )

        assert response.status_code == 200, response.content
        requirement.refresh_from_db()
        assert requirement.title == "Original"


# ---------------------------------------------------------------------------
# Preset gate (REQ-L3-RA004-001)
# ---------------------------------------------------------------------------


class TestRollbackPresetGate:
    def test_minimal_preset_answers_404_on_all_three_routes(
        self, tenant: Tenant, authed_client: APIClient
    ) -> None:
        minimal = _workspace(tenant, "minimal-rollback", tier="minimal")
        admin = User.objects.get(username="bundleadmin")
        _grant(tenant, admin, minimal, ROLE_ADMIN)
        # The builder itself refuses a project baseline on the minimal tier
        # (``ScopeNotAllowedError``), so the row is inserted directly: what this
        # test pins is that the *routes* answer 404 before any of that matters.
        baseline_id = _bare_baseline(tenant, minimal)

        preview = _preview(authed_client, baseline_id)
        request_response = _rollback_request(
            authed_client, baseline_id, change_reason="restore"
        )
        apply_response = _rollback(authed_client, baseline_id, uuid.uuid4())

        assert preview.status_code == 404, preview.content
        assert request_response.status_code == 404, request_response.content
        assert apply_response.status_code == 404, apply_response.content


# ---------------------------------------------------------------------------
# Fences + error plumbing
# ---------------------------------------------------------------------------


def test_fenced_key_cannot_rollback_foreign_workspace_baseline(
    tenant: Tenant, workspace: Workspace
) -> None:
    """SEC-RB-01 — the API key's workspace fence is a hard stop on every route."""
    foreign = _workspace(tenant, "fenced-rollback")
    _provision_workflows(tenant, foreign)
    user = _user(tenant, f"fenced-rollback-{uuid.uuid4().hex[:8]}")
    _grant(tenant, user, foreign, ROLE_ADMIN)
    requirement = _make_requirement(tenant, foreign)
    baseline_id = _baseline(tenant, foreign)
    _rename(requirement, _ctx(user, foreign), "Changed")

    key = AuthenticationService().create_api_key(
        user_id=user.id,
        tenant_id=tenant.id,
        name="f4-4-fenced",
        principal_type="agent",
        scope="author",
        workspace_ids=[str(workspace.id)],
        expires_at=timezone.now() + timedelta(days=1),
    )
    client = APIClient()
    client.credentials(HTTP_X_API_KEY=key.plaintext)

    preview = _preview(client, baseline_id)
    request_response = _rollback_request(
        client, baseline_id, change_reason="restore"
    )
    apply_response = _rollback(client, baseline_id, uuid.uuid4())

    for response in (preview, request_response, apply_response):
        assert response.status_code == 403, response.content
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"


def test_rollback_error_details_are_forwarded(
    env, tenant: Tenant, authed_client: APIClient
) -> None:
    """SEC-RB-05 — ``RollbackError.details`` reaches the client, not ``[]``.

    Before the pass-through every rollback failure answered the generic
    details-less envelope, so a client had to re-derive *which* items
    invalidated the plan (R3) or which CR state it hit (R5).
    """
    _, baseline_id = _changed_baseline(env, tenant)
    cr = _draft_cr(baseline_id, env["ctx"])

    response = _rollback(authed_client, baseline_id, cr.id)

    assert response.status_code == 409, response.content
    details = response.json()["error"]["details"]
    assert details == {"change_request_id": str(cr.id), "status": "draft"}


def _approve_and_get(ctx: AuthContext, baseline_id):
    cr = _draft_cr(baseline_id, ctx)
    _approve_cr(ctx, cr.id)
    return cr
