"""F4.2 — REST surface for baseline tags (real DB).

Plan F (2026-10-21), F4.2. Pins ``PUT /api/v1/baselines/{id}/tags/``, the
``?tag=`` list filter and the optional ``tags`` field on create.

Requirements:
- REQ-L2-BL-001, REQ-L2-RA-001, REQ-L2-PL-010, QR-S09 a.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, ROLE_VIEWER, UserRole
from auth_tenancy.services.authentication import AuthenticationService
from baseline.models import BaselineSnapshot, BaselineTag
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"


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


def _workspace(tenant: Tenant, name: str, tier: str = "extended") -> Workspace:
    set_request_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name=f"{name}-{uuid.uuid4().hex[:8]}", preset={"name": tier}
        )
    finally:
        clear_request_tenant()


def _baseline(
    tenant: Tenant, workspace: Workspace, name: str, labels: list[str] | None = None
) -> BaselineSnapshot:
    set_request_tenant(tenant.id)
    try:
        baseline = BaselineSnapshot.unscoped.create(
            tenant=tenant,
            workspace_id=workspace.id,
            scope="project",
            name=name,
        )
        for label in labels or []:
            BaselineTag.unscoped.create(
                tenant=tenant,
                baseline=baseline,
                workspace_id=workspace.id,
                label=label,
            )
        return baseline
    finally:
        clear_request_tenant()


def _create_baseline(client: APIClient, workspace: Workspace, name: str, **extra):
    payload = {
        "workspace_id": str(workspace.id),
        "scope": "project",
        "name": name,
        "override_reason": "accepted deviation for tag fixture",
    }
    payload.update(extra)
    return client.post("/api/v1/baselines/", payload, format="json")


def _set_tags(client: APIClient, baseline_id, tags: list[str], **extra):
    payload = {"tags": tags}
    payload.update(extra)
    return client.put(
        f"/api/v1/baselines/{baseline_id}/tags/", payload, format="json"
    )


class TestBaselineTagsPut:
    def test_put_replaces_and_sorts_case_insensitively(
        self, authed_client: APIClient, tenant: Tenant, workspace: Workspace
    ) -> None:
        created = _create_baseline(
            authed_client, workspace, f"tags-{uuid.uuid4().hex[:8]}"
        )
        assert created.status_code == 201, created.content
        baseline_id = created.json()["id"]

        response = _set_tags(authed_client, baseline_id, ["Release", "RC1"])

        assert response.status_code == 200, response.content
        assert response.json() == {"id": baseline_id, "tags": ["RC1", "Release"]}

        detail = authed_client.get(f"/api/v1/baselines/{baseline_id}/")
        assert detail.status_code == 200, detail.content
        assert detail.json()["tags"] == ["RC1", "Release"]

    def test_put_ignores_a_body_workspace_id(
        self, authed_client: APIClient, tenant: Tenant, workspace: Workspace
    ) -> None:
        """The stored workspace_id always comes from the baseline.

        A ``workspace_id`` in the body is not a write input (QR-S09 a). The
        caller must still hold write authority in whatever workspace it names
        (the ADR-011 seam reads it), so this grants the admin a role in the
        second workspace too — the point is that the *persisted* tag row still
        belongs to the baseline's workspace.
        """
        other = _workspace(tenant, "other")
        admin = User.objects.get(username="bundleadmin")
        _grant(tenant, admin, other, ROLE_ADMIN)
        baseline = _baseline(tenant, workspace, f"ws-derived-{uuid.uuid4().hex[:8]}")

        response = _set_tags(
            authed_client, baseline.id, ["Release"], workspace_id=str(other.id)
        )

        assert response.status_code == 200, response.content
        tag = BaselineTag.unscoped.get(baseline_id=baseline.id)
        assert tag.workspace_id == workspace.id
        assert tag.workspace_id != other.id

    def test_put_tags_rejects_unknown_field(
        self, authed_client: APIClient, tenant: Tenant, workspace: Workspace
    ) -> None:
        """An undeclared body key is a 400, not a silent drop (#851)."""
        baseline = _baseline(tenant, workspace, f"unknown-{uuid.uuid4().hex[:8]}")

        response = _set_tags(authed_client, baseline.id, ["Release"], tagz=["typo"])

        assert response.status_code == 400, response.content
        body = response.json()["error"]
        assert body["code"] == "VALIDATION_ERROR"
        assert {"field": "tagz", "errors": ["Unknown field."]} in body["details"]

    @pytest.mark.parametrize(
        "tags",
        [
            ["bad\nlabel"],
            ["x" * 65],
            ["tag-{}".format(i) for i in range(21)],
        ],
    )
    def test_put_rejects_invalid_tags_with_details(
        self, authed_client: APIClient, tenant: Tenant, workspace: Workspace, tags
    ) -> None:
        baseline = _baseline(tenant, workspace, f"invalid-{uuid.uuid4().hex[:8]}")

        response = _set_tags(authed_client, baseline.id, tags)

        assert response.status_code == 400, response.content
        body = response.json()["error"]
        assert body["code"] == "VALIDATION_ERROR"
        assert body["details"], body

    def test_put_unknown_baseline_is_404(self, authed_client: APIClient) -> None:
        response = _set_tags(authed_client, uuid.uuid4(), ["Release"])

        assert response.status_code == 404, response.content
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_viewer_cannot_tag(
        self, tenant: Tenant, workspace: Workspace
    ) -> None:
        viewer = _user(tenant, f"viewer-{uuid.uuid4().hex[:8]}")
        _grant(tenant, viewer, workspace, ROLE_VIEWER)
        baseline = _baseline(tenant, workspace, f"viewer-{uuid.uuid4().hex[:8]}")

        response = _set_tags(_login(viewer), baseline.id, ["Release"])

        assert response.status_code == 403, response.content
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"

    def test_minimal_preset_answers_404(
        self, authed_client: APIClient, tenant: Tenant
    ) -> None:
        minimal = _workspace(tenant, "minimal", tier="minimal")
        admin = User.objects.get(username="bundleadmin")
        _grant(tenant, admin, minimal, ROLE_ADMIN)
        baseline = _baseline(tenant, minimal, f"min-{uuid.uuid4().hex[:8]}")

        response = _set_tags(authed_client, baseline.id, ["Release"])

        assert response.status_code == 404, response.content

    def test_fenced_key_cannot_tag_foreign_workspace_baseline(
        self, tenant: Tenant, workspace: Workspace
    ) -> None:
        foreign = _workspace(tenant, "fenced-foreign")
        user = _user(tenant, f"fenced-{uuid.uuid4().hex[:8]}")
        _grant(tenant, user, foreign, ROLE_ADMIN)
        baseline = _baseline(
            tenant, foreign, f"fenced-{uuid.uuid4().hex[:8]}", ["Release"]
        )
        key = AuthenticationService().create_api_key(
            user_id=user.id,
            tenant_id=tenant.id,
            name="f4-2-fenced",
            principal_type="agent",
            scope="author",
            workspace_ids=[str(workspace.id)],
            expires_at=timezone.now() + timedelta(days=1),
        )
        client = APIClient()
        client.credentials(HTTP_X_API_KEY=key.plaintext)

        response = _set_tags(client, baseline.id, ["RC1"])

        assert response.status_code == 403, response.content
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"
        assert (
            BaselineTag.unscoped.filter(baseline_id=baseline.id, label="RC1").count()
            == 0
        )


class TestBaselineTagsListAndCreate:
    def test_tag_filter_is_case_insensitive_and_workspace_scoped(
        self, authed_client: APIClient, tenant: Tenant, workspace: Workspace
    ) -> None:
        tagged = _baseline(
            tenant, workspace, f"tagged-{uuid.uuid4().hex[:8]}", ["Release"]
        )
        _baseline(tenant, workspace, f"untagged-{uuid.uuid4().hex[:8]}")
        foreign_ws = _workspace(tenant, "foreign-list")
        _baseline(
            tenant, foreign_ws, f"foreign-tag-{uuid.uuid4().hex[:8]}", ["Release"]
        )

        response = authed_client.get(
            "/api/v1/baselines/",
            {"workspace_id": str(workspace.id), "tag": "release"},
        )

        assert response.status_code == 200, response.content
        ids = {row["id"] for row in response.json()["results"]}
        assert str(tagged.id) in ids
        assert len(ids) == 1

    def test_create_accepts_tags(
        self, authed_client: APIClient, tenant: Tenant, workspace: Workspace
    ) -> None:
        response = _create_baseline(
            authed_client,
            workspace,
            f"created-tags-{uuid.uuid4().hex[:8]}",
            tags=["Release", "rc1", "RC1"],
        )

        assert response.status_code == 201, response.content
        assert response.json()["tags"] == ["rc1", "Release"]

        listed = authed_client.get(
            "/api/v1/baselines/",
            {"workspace_id": str(workspace.id), "tag": "RC1"},
        )
        assert listed.status_code == 200, listed.content
        assert len(listed.json()["results"]) == 1

    def test_create_with_invalid_tag_is_400_with_details(
        self, authed_client: APIClient, tenant: Tenant, workspace: Workspace
    ) -> None:
        response = _create_baseline(
            authed_client,
            workspace,
            f"bad-tags-{uuid.uuid4().hex[:8]}",
            tags=["bad\nlabel"],
        )

        assert response.status_code == 400, response.content
        body = response.json()["error"]
        assert body["code"] == "VALIDATION_ERROR"
        assert body["details"], body


class TestBaselineTagFilterValidation:
    """F4.2 review B2 — the ``?tag=`` filter is validated, not passed through.

    Before the fix a NUL byte reached psycopg2 (``A string literal cannot
    contain NUL (0x00) characters``) and the request answered **500**; an
    unbounded value went straight into ``iexact``. Both are request defects and
    must answer ``400 VALIDATION_ERROR``.
    """

    def test_tag_filter_with_nul_byte_is_400_not_500(
        self, authed_client: APIClient, tenant: Tenant, workspace: Workspace
    ) -> None:
        _baseline(tenant, workspace, f"nul-{uuid.uuid4().hex[:8]}", ["Release"])

        response = authed_client.get(
            "/api/v1/baselines/",
            {"workspace_id": str(workspace.id), "tag": "\x00"},
        )

        assert response.status_code == 400, response.content
        body = response.json()["error"]
        assert body["code"] == "VALIDATION_ERROR"
        assert body["details"], body

    def test_tag_filter_longer_than_64_is_400(
        self, authed_client: APIClient, tenant: Tenant, workspace: Workspace
    ) -> None:
        _baseline(tenant, workspace, f"long-{uuid.uuid4().hex[:8]}", ["Release"])

        response = authed_client.get(
            "/api/v1/baselines/",
            {"workspace_id": str(workspace.id), "tag": "x" * 65},
        )

        assert response.status_code == 400, response.content
        body = response.json()["error"]
        assert body["code"] == "VALIDATION_ERROR"
        assert body["details"], body

    def test_blank_tag_filter_means_no_filter(
        self, authed_client: APIClient, tenant: Tenant, workspace: Workspace
    ) -> None:
        """A blank filter is "no filter", not an error (unchanged semantics)."""
        _baseline(tenant, workspace, f"blank-{uuid.uuid4().hex[:8]}", ["Release"])

        response = authed_client.get(
            "/api/v1/baselines/",
            {"workspace_id": str(workspace.id), "tag": "   "},
        )

        assert response.status_code == 200, response.content
        assert len(response.json()["results"]) == 1
