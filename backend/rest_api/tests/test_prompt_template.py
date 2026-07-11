"""
REQ-L2-PT-001 — PromptTemplate model + REST endpoint tests.

Covers:
- GET/PATCH /api/v1/prompt-templates/ (admin-only).
- GET lazily creates the singleton row seeded with factory defaults.
- ``defaults_dict`` always exposes the DEFAULT_* constants.
- PATCH updates individual slots; other slots stay intact.
- POST /api/v1/prompt-templates/reset/ restores a single slot or all slots.
- Non-admin roles are rejected with 403.
- Singleton semantics (one row per tenant).

Reuses the JWT + APIClient pattern from test_llm_settings.py.
"""
from __future__ import annotations

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    PROMPT_TEMPLATE_DEFAULTS,
    PromptTemplate,
    Tenant,
    User,
    Workspace,
)

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET="test-secret-not-a-real-key",
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def pt_tenant(db):
    """A tenant with an admin and an editor user for prompt-template tests."""
    tenant = Tenant.objects.create(name="PT T", slug="pt-t", is_active=True)
    admin = User.objects.create(
        username="ptadmin", email="ptadmin@t.test", tenant=tenant
    )
    admin.set_password("ptpass123")
    admin.save(update_fields=["password"])
    editor = User.objects.create(
        username="pteditor", email="pteditor@t.test", tenant=tenant
    )
    editor.set_password("ptpass123")
    editor.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="PT WS", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        UserRole.objects.create(
            tenant=tenant, user=editor, workspace=workspace, role=ROLE_EDITOR
        )
        yield tenant
    finally:
        clear_request_tenant()


def _login(client: APIClient, username: str) -> str:
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": "ptpass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    return resp.json()["token"]


def _auth(client: APIClient, token: str) -> None:
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")


# ---------------------------------------------------------------------------
# REST endpoint
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_get_creates_default_row_with_factory_prompts(pt_tenant):
    """GET lazily creates the singleton row seeded with factory defaults."""
    client = APIClient()
    _auth(client, _login(client, "ptadmin"))

    resp = client.get("/api/v1/prompt-templates/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["need_to_sysreq"] == PROMPT_TEMPLATE_DEFAULTS["need_to_sysreq"]
    assert (
        body["sysreq_to_arch_assign"]
        == PROMPT_TEMPLATE_DEFAULTS["sysreq_to_arch_assign"]
    )
    assert (
        body["sysreq_decompose_next_level"]
        == PROMPT_TEMPLATE_DEFAULTS["sysreq_decompose_next_level"]
    )
    # defaults_dict always mirrors the DEFAULT_* constants.
    assert body["defaults_dict"] == dict(PROMPT_TEMPLATE_DEFAULTS)


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_patch_updates_single_slot_leaving_others_intact(pt_tenant):
    """PATCH one slot; the other slots keep their default content."""
    client = APIClient()
    _auth(client, _login(client, "ptadmin"))

    resp = client.patch(
        "/api/v1/prompt-templates/",
        {"need_to_sysreq": "custom prompt {n}"},
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["need_to_sysreq"] == "custom prompt {n}"
    assert (
        body["sysreq_to_arch_assign"]
        == PROMPT_TEMPLATE_DEFAULTS["sysreq_to_arch_assign"]
    )

    set_request_tenant(pt_tenant.id)
    row = PromptTemplate.objects.get(tenant_id=pt_tenant.id)
    assert row.need_to_sysreq == "custom prompt {n}"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reset_single_slot_restores_default(pt_tenant):
    """POST reset with a slot restores only that slot to its default."""
    client = APIClient()
    _auth(client, _login(client, "ptadmin"))

    client.patch(
        "/api/v1/prompt-templates/",
        {
            "need_to_sysreq": "customised",
            "sysreq_to_arch_assign": "also customised",
        },
        format="json",
    )

    resp = client.post(
        "/api/v1/prompt-templates/reset/",
        {"slot": "need_to_sysreq"},
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["need_to_sysreq"] == PROMPT_TEMPLATE_DEFAULTS["need_to_sysreq"]
    # The other customised slot is untouched by a single-slot reset.
    assert body["sysreq_to_arch_assign"] == "also customised"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reset_all_restores_every_slot(pt_tenant):
    """POST reset without a slot restores all slots to their defaults."""
    client = APIClient()
    _auth(client, _login(client, "ptadmin"))

    client.patch(
        "/api/v1/prompt-templates/",
        {
            "need_to_sysreq": "a",
            "sysreq_to_arch_assign": "b",
            "sysreq_decompose_next_level": "c",
        },
        format="json",
    )

    resp = client.post("/api/v1/prompt-templates/reset/", {}, format="json")
    assert resp.status_code == 200
    body = resp.json()
    for slot, default in PROMPT_TEMPLATE_DEFAULTS.items():
        assert body[slot] == default


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_reset_unknown_slot_is_rejected(pt_tenant):
    """POST reset with an unknown slot returns 400."""
    client = APIClient()
    _auth(client, _login(client, "ptadmin"))

    resp = client.post(
        "/api/v1/prompt-templates/reset/",
        {"slot": "does_not_exist"},
        format="json",
    )
    assert resp.status_code == 400


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_non_admin_is_forbidden(pt_tenant):
    """A non-admin (editor) cannot read, write, or reset prompt templates."""
    client = APIClient()
    _auth(client, _login(client, "pteditor"))

    assert client.get("/api/v1/prompt-templates/").status_code == 403
    assert (
        client.patch(
            "/api/v1/prompt-templates/",
            {"need_to_sysreq": "x"},
            format="json",
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/prompt-templates/reset/", {}, format="json"
        ).status_code
        == 403
    )


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_singleton_one_row_per_tenant(pt_tenant):
    """Repeated access never creates more than one row per tenant."""
    client = APIClient()
    _auth(client, _login(client, "ptadmin"))

    client.get("/api/v1/prompt-templates/")
    client.patch(
        "/api/v1/prompt-templates/", {"need_to_sysreq": "x"}, format="json"
    )
    client.post("/api/v1/prompt-templates/reset/", {}, format="json")

    set_request_tenant(pt_tenant.id)
    assert PromptTemplate.objects.filter(tenant_id=pt_tenant.id).count() == 1
