"""INT-05 (AUD-2026-09-073 / AUD-2026-09-074) — REST pagination + status codes.

Two audit findings, one hardening unit:

* **AUD-2026-09-074** — four list endpoints answered with a bare JSON array and
  ignored ``page``/``page_size`` entirely:
  ``GET /api/v1/api-keys/``, ``GET /api/v1/users/``,
  ``GET /api/v1/link-type-defaults/`` and
  ``GET /api/v1/workspaces/<uuid>/link-type-definitions/``.
  They now use the project-wide ``StandardPagination`` envelope
  (``{count, next, previous, page_size, max_page_size, results}``).

* **AUD-2026-09-073** — ``GET /api/v1/tracelinks/`` and ``GET /api/v1/glossary/``
  resolved pagination *inside* a broad ``try/except Exception``, so DRF's
  ``NotFound`` for an invalid ``page`` was rewritten to a **500**. The
  pagination call was hoisted outside the guard; invalid ``page`` now yields
  **404** (consistent with ``/workspaces/``), a genuinely missing resource
  still yields **404**, and only real service failures stay 500.

The tests are intentionally black-box (real HTTP through a logged-in client) so
they exercise the exact transport the audit measured live.
"""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, TenantRole, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, GlossaryTerm, Requirement, Tenant, User, Workspace

pytestmark = pytest.mark.django_db

_PASSWORD = "hunter2pass"

#: The full StandardPagination envelope key set.
_ENVELOPE_KEYS = {"count", "next", "previous", "page_size", "max_page_size", "results"}


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(
        name="INT05 Tenant", slug=f"int05-{uuid.uuid4().hex[:8]}", is_active=True
    )


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    set_request_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name="INT05 WS", preset={"name": "extended"}
        )
    finally:
        clear_request_tenant()


def _login_client(user: User) -> APIClient:
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": user.username, "password": _PASSWORD},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")
    return client


def _make_user(tenant: Tenant, *, suffix: str = "") -> User:
    tag = suffix or uuid.uuid4().hex[:6]
    user = User.objects.create(
        username=f"int05-{tag}", email=f"int05-{tag}@t.test", tenant=tenant
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    return user


@pytest.fixture
def admin_client(tenant: Tenant, workspace: Workspace) -> APIClient:
    """Tenant-admin + workspace-admin client (sees ``/users/`` and link types)."""
    set_request_tenant(tenant.id)
    try:
        user = _make_user(tenant, suffix="admin")
        TenantRole.objects.create(tenant=tenant, user=user, role=TenantRole.ROLE_ADMIN)
        UserRole.objects.create(tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN)
    finally:
        clear_request_tenant()
    return _login_client(user)


@pytest.fixture
def self_client(tenant: Tenant, workspace: Workspace) -> APIClient:
    """Ordinary authenticated user with a workspace role (API keys self-scope)."""
    set_request_tenant(tenant.id)
    try:
        user = _make_user(tenant, suffix="self")
        UserRole.objects.create(tenant=tenant, user=user, workspace=workspace, role=ROLE_ADMIN)
    finally:
        clear_request_tenant()
    return _login_client(user)


# ---------------------------------------------------------------------------
# AUD-2026-09-074 — the four un-paginated lists
# ---------------------------------------------------------------------------


class TestListEndpointsPaginationShape:
    """Each of the four lists answers with the StandardPagination envelope."""

    def test_api_keys_list_is_paginated(self, self_client):
        resp = self_client.get("/api/v1/api-keys/")
        assert resp.status_code == 200, resp.content
        body = resp.json()
        assert isinstance(body, dict), body
        assert set(body) >= _ENVELOPE_KEYS, body
        assert isinstance(body["results"], list)

    def test_users_list_is_paginated(self, admin_client):
        resp = admin_client.get("/api/v1/users/")
        assert resp.status_code == 200, resp.content
        body = resp.json()
        assert isinstance(body, dict), body
        assert set(body) >= _ENVELOPE_KEYS, body
        assert isinstance(body["results"], list)

    def test_link_type_defaults_is_paginated(self, admin_client):
        resp = admin_client.get("/api/v1/link-type-defaults/")
        assert resp.status_code == 200, resp.content
        body = resp.json()
        assert isinstance(body, dict), body
        assert set(body) >= _ENVELOPE_KEYS, body
        assert isinstance(body["results"], list)

    def test_workspace_link_type_definitions_is_paginated(
        self, admin_client, workspace
    ):
        resp = admin_client.get(
            f"/api/v1/workspaces/{workspace.id}/link-type-definitions/"
        )
        assert resp.status_code == 200, resp.content
        body = resp.json()
        assert isinstance(body, dict), body
        assert set(body) >= _ENVELOPE_KEYS, body
        assert isinstance(body["results"], list)


class TestListEndpointsPageSizeAndErrors:
    """``page``/``page_size`` are honoured, invalid ``page`` is a clean 404."""

    def test_page_size_caps_results_and_echoes_applied_size(self, admin_client):
        resp = admin_client.get("/api/v1/link-type-defaults/?page_size=2")
        assert resp.status_code == 200, resp.content
        body = resp.json()
        assert body["page_size"] == 2
        assert len(body["results"]) <= 2

    @pytest.mark.parametrize("bad_page", ["0", "abc", "99999999", "-1"])
    def test_invalid_page_on_users_is_404(self, admin_client, bad_page):
        resp = admin_client.get(f"/api/v1/users/?page={bad_page}")
        assert resp.status_code == 404, (bad_page, resp.content)

    @pytest.mark.parametrize("bad_page", ["0", "abc", "99999999"])
    def test_invalid_page_on_api_keys_is_404(self, self_client, bad_page):
        resp = self_client.get(f"/api/v1/api-keys/?page={bad_page}")
        assert resp.status_code == 404, (bad_page, resp.content)

    @pytest.mark.parametrize("bad_page", ["0", "abc", "99999999"])
    def test_invalid_page_on_link_type_defaults_is_404(self, admin_client, bad_page):
        resp = admin_client.get(f"/api/v1/link-type-defaults/?page={bad_page}")
        assert resp.status_code == 404, (bad_page, resp.content)

    @pytest.mark.parametrize("bad_page", ["0", "abc", "99999999"])
    def test_invalid_page_on_workspace_link_types_is_404(
        self, admin_client, workspace, bad_page
    ):
        resp = admin_client.get(
            f"/api/v1/workspaces/{workspace.id}/link-type-definitions/?page={bad_page}"
        )
        assert resp.status_code == 404, (bad_page, resp.content)


# ---------------------------------------------------------------------------
# AUD-2026-09-073 — trace-links / glossary: 500 vs 404
# ---------------------------------------------------------------------------


def _make_requirement(tenant: Tenant, workspace: Workspace, title: str) -> Requirement:
    art = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    return Requirement.objects.create(
        tenant=tenant, artifact=art, workspace=workspace, title=title
    )


class TestInvalidPageIs404NotFoundNot500:
    """Invalid ``page`` must never be rewritten into a 500 by a broad handler."""

    @pytest.mark.parametrize("bad_page", ["0", "abc", "99999999", "-1"])
    def test_tracelinks_invalid_page_is_404(
        self, admin_client, tenant, workspace, bad_page
    ):
        set_request_tenant(tenant.id)
        try:
            _make_requirement(tenant, workspace, "INT05 src")
            _make_requirement(tenant, workspace, "INT05 tgt")
        finally:
            clear_request_tenant()

        resp = admin_client.get(
            f"/api/v1/tracelinks/?workspace_id={workspace.id}&page={bad_page}"
        )
        assert resp.status_code == 404, (bad_page, resp.content)

    @pytest.mark.parametrize("bad_page", ["0", "abc", "99999999"])
    def test_glossary_invalid_page_is_404(
        self, admin_client, tenant, workspace, bad_page
    ):
        set_request_tenant(tenant.id)
        try:
            GlossaryTerm.objects.create(
                tenant=tenant, workspace=workspace, term="INT05", definition="d"
            )
        finally:
            clear_request_tenant()

        resp = admin_client.get(
            f"/api/v1/glossary/?workspace_id={workspace.id}&page={bad_page}"
        )
        assert resp.status_code == 404, (bad_page, resp.content)

    def test_tracelinks_malformed_workspace_is_4xx_not_500(self, admin_client):
        """A malformed ``workspace_id`` is a client error, never a 500.

        A *well-formed but absent* workspace id still yields an empty page (200)
        — that is the endpoint's existing filter semantics and out of scope for
        INT-05; the audit contract is that malformed/absent-``page`` input no
        longer 500s. This pins the format-validation path to a 4xx.
        """
        resp = admin_client.get("/api/v1/tracelinks/?workspace_id=not-a-uuid")
        assert resp.status_code in (400, 404), resp.content

    def test_glossary_malformed_workspace_is_4xx_not_500(self, admin_client):
        resp = admin_client.get("/api/v1/glossary/?workspace_id=not-a-uuid")
        assert resp.status_code in (400, 404), resp.content


class TestValidPaginationStillWorks:
    """The happy path is unchanged: a valid request returns an envelope."""

    def test_tracelinks_default_page_is_envelope(self, admin_client, workspace):
        resp = admin_client.get(f"/api/v1/tracelinks/?workspace_id={workspace.id}")
        assert resp.status_code == 200, resp.content
        body = resp.json()
        assert set(body) >= _ENVELOPE_KEYS, body

    def test_glossary_default_page_is_envelope(self, admin_client, workspace):
        resp = admin_client.get(f"/api/v1/glossary/?workspace_id={workspace.id}")
        assert resp.status_code == 200, resp.content
        body = resp.json()
        assert set(body) >= _ENVELOPE_KEYS, body

    def test_glossary_include_deleted_still_paginates(self, admin_client, workspace):
        resp = admin_client.get(
            f"/api/v1/glossary/?workspace_id={workspace.id}&include_deleted=true"
        )
        assert resp.status_code == 200, resp.content
        assert set(resp.json()) >= _ENVELOPE_KEYS
