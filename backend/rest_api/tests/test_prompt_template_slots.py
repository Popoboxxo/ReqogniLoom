"""
Issue #119 — prompt-template *slot* REST endpoints.

The pre-existing flat facade at ``/api/v1/prompt-templates/`` exposes only 4 of
the slots the AI-derivation flows actually use, tenant-global scope only, and
merges the scopes into a single string per slot. These tests cover the slot
API that closes that gap:

- GET    /api/v1/prompt-templates/slots/[?workspace_id=]
- PUT    /api/v1/prompt-templates/slots/<name>/[?workspace_id=]
- DELETE /api/v1/prompt-templates/slots/<name>/[?workspace_id=]

Reuses the JWT + APIClient pattern from test_prompt_template.py.
"""
from __future__ import annotations

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from application.ai_derivation_service import PROMPT_TEMPLATE_DEFAULTS
from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import PromptTemplate, Tenant, User, Workspace

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET="test-secret-not-a-real-key",
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)

_SLOTS_URL = "/api/v1/prompt-templates/slots/"

# One of the 4 slots the flat facade never exposed (issue #119's core symptom).
_MCP_ONLY_SLOT = "testcase_derive"


@pytest.fixture
def pts_ctx(db):
    """Yield ``(tenant, workspace)`` with an admin and an editor user."""
    tenant = Tenant.objects.create(name="PTS T", slug="pts-t", is_active=True)
    admin = User.objects.create(
        username="ptsadmin", email="ptsadmin@t.test", tenant=tenant
    )
    admin.set_password("ptspass123")
    admin.save(update_fields=["password"])
    editor = User.objects.create(
        username="ptseditor", email="ptseditor@t.test", tenant=tenant
    )
    editor.set_password("ptspass123")
    editor.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="PTS WS", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        UserRole.objects.create(
            tenant=tenant, user=editor, workspace=workspace, role=ROLE_EDITOR
        )
        yield tenant, workspace
    finally:
        clear_request_tenant()


def _client(username: str = "ptsadmin") -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": "ptspass123"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def _slot(body: dict, name: str) -> dict:
    """Return the slot dict named ``name`` from a list response body."""
    matches = [s for s in body["slots"] if s["name"] == name]
    assert matches, f"slot {name!r} missing from {[s['name'] for s in body['slots']]}"
    return matches[0]


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_list_exposes_every_factory_slot(pts_ctx):
    """Every derive-flow slot is listed, not just the flat facade's 4."""
    resp = _client().get(_SLOTS_URL)
    assert resp.status_code == 200, resp.content
    body = resp.json()
    names = {s["name"] for s in body["slots"]}
    assert set(PROMPT_TEMPLATE_DEFAULTS) <= names
    # The four slots the flat facade never exposed (issue #119).
    assert {
        "testcase_derive",
        "architecture_to_risk",
        "workspace_to_glossary",
        "decision_to_adr",
    } <= names
    assert body["count"] == len(body["slots"])


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_untouched_slot_reports_factory_scope(pts_ctx):
    """A slot with no row anywhere resolves to the factory default."""
    resp = _client().get(_SLOTS_URL)
    slot = _slot(resp.json(), _MCP_ONLY_SLOT)
    assert slot["effective_scope"] == "factory"
    assert slot["effective_content"] == PROMPT_TEMPLATE_DEFAULTS[_MCP_ONLY_SLOT]
    assert slot["global_content"] is None
    assert slot["workspace_content"] is None
    assert slot["has_workspace_override"] is False


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_list_includes_mcp_created_custom_names(pts_ctx):
    """A template created under a custom name via MCP is still listed."""
    tenant, _ = pts_ctx
    set_request_tenant(tenant.id)
    PromptTemplate.objects.create(
        tenant=tenant, name="custom_flow", content="hi", version=1, is_active=True
    )

    slot = _slot(_client().get(_SLOTS_URL).json(), "custom_flow")
    assert slot["factory_default"] is None
    assert slot["effective_content"] == "hi"
    assert slot["effective_scope"] == "global"


# ---------------------------------------------------------------------------
# Write — tenant-global scope
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_put_global_slot_previously_unreachable_via_rest(pts_ctx):
    """PUT customises one of the 4 slots the flat facade never exposed."""
    client = _client()
    resp = client.put(
        f"{_SLOTS_URL}{_MCP_ONLY_SLOT}/", {"content": "custom tc"}, format="json"
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["global_content"] == "custom tc"
    assert resp.json()["effective_scope"] == "global"

    slot = _slot(client.get(_SLOTS_URL).json(), _MCP_ONLY_SLOT)
    assert slot["effective_content"] == "custom tc"
    assert slot["global_version"] == 1


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_repeated_put_bumps_the_version(pts_ctx):
    """Each PUT publishes a new version rather than mutating the row."""
    client = _client()
    client.put(f"{_SLOTS_URL}{_MCP_ONLY_SLOT}/", {"content": "v1"}, format="json")
    resp = client.put(
        f"{_SLOTS_URL}{_MCP_ONLY_SLOT}/", {"content": "v2"}, format="json"
    )
    assert resp.json()["global_version"] == 2
    assert resp.json()["global_content"] == "v2"


# ---------------------------------------------------------------------------
# Write — workspace override scope
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_workspace_override_shadows_the_global_default(pts_ctx):
    """A workspace override wins over the tenant-global row."""
    _, workspace = pts_ctx
    client = _client()
    client.put(f"{_SLOTS_URL}need_to_sysreq/", {"content": "global"}, format="json")
    resp = client.put(
        f"{_SLOTS_URL}need_to_sysreq/?workspace_id={workspace.id}",
        {"content": "ws only"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["has_workspace_override"] is True
    assert body["workspace_content"] == "ws only"
    assert body["global_content"] == "global"
    assert body["effective_scope"] == "workspace"
    assert body["effective_content"] == "ws only"

    # The tenant-global view is unaffected by the workspace override.
    assert (
        _slot(client.get(_SLOTS_URL).json(), "need_to_sysreq")["effective_content"]
        == "global"
    )


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_delete_workspace_override_falls_back_to_global(pts_ctx):
    """DELETE drops only the workspace override; the global row survives."""
    _, workspace = pts_ctx
    client = _client()
    client.put(f"{_SLOTS_URL}need_to_sysreq/", {"content": "global"}, format="json")
    client.put(
        f"{_SLOTS_URL}need_to_sysreq/?workspace_id={workspace.id}",
        {"content": "ws only"},
        format="json",
    )

    resp = client.delete(
        f"{_SLOTS_URL}need_to_sysreq/?workspace_id={workspace.id}"
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["has_workspace_override"] is False
    assert body["effective_scope"] == "global"
    assert body["effective_content"] == "global"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_delete_global_slot_falls_back_to_factory(pts_ctx):
    """Clearing the tenant-global scope restores the factory text."""
    client = _client()
    client.put(f"{_SLOTS_URL}need_to_sysreq/", {"content": "global"}, format="json")

    body = client.delete(f"{_SLOTS_URL}need_to_sysreq/").json()
    assert body["global_content"] is None
    assert body["effective_scope"] == "factory"
    assert body["effective_content"] == PROMPT_TEMPLATE_DEFAULTS["need_to_sysreq"]


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_delete_without_override_is_a_noop(pts_ctx):
    """DELETE on an untouched scope succeeds instead of 404-ing."""
    resp = _client().delete(f"{_SLOTS_URL}need_to_sysreq/")
    assert resp.status_code == 200
    assert resp.json()["effective_scope"] == "factory"


# ---------------------------------------------------------------------------
# Validation + permissions
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_malformed_workspace_id_is_rejected(pts_ctx):
    """A non-UUID workspace_id is a 400, not a 500."""
    resp = _client().get(f"{_SLOTS_URL}?workspace_id=not-a-uuid")
    assert resp.status_code == 400


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_put_requires_content(pts_ctx):
    """A PUT without a content field is a validation error."""
    resp = _client().put(f"{_SLOTS_URL}need_to_sysreq/", {}, format="json")
    assert resp.status_code == 400


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_non_admin_is_forbidden(pts_ctx):
    """Editors may neither read nor write prompt slots."""
    client = _client("ptseditor")
    assert client.get(_SLOTS_URL).status_code == 403
    assert (
        client.put(
            f"{_SLOTS_URL}need_to_sysreq/", {"content": "x"}, format="json"
        ).status_code
        == 403
    )
    assert client.delete(f"{_SLOTS_URL}need_to_sysreq/").status_code == 403
