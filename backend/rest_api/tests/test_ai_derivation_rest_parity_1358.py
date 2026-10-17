"""Issue #1358 (W12a) — REST parity for the AI-derivation preview/write seam.

The defect this file pins
=========================
The MCP tools under ``ai_derivation.*`` have always known two modes
(``preview`` | ``write``), but a ``preview`` response did not *say* so: the
drafts looked like persisted data (the QA repro found ``GET /api/v1/glossary/``
= 0 after ``derive_glossary_from_workspace`` returned a full draft list), and
REST had no way at all to reach the write seam for glossary/ADR/risk — the
three flows the issue targets.

W12a fixes both halves:

* every preview response carries ``"ephemeral": true`` (#1358), added at the
  single Layer-2 seam (``AiDerivationService``) so MCP and REST cannot drift;
* three additive REST actions expose the same draft flows over the existing
  write seam: ``POST /api/v1/glossary/derive/``,
  ``POST /api/v1/adrs/derive-from-decision/`` and
  ``POST /api/v1/architecture/{pk}/derive-risks/`` — ``mode="write"`` is the
  canonical persistence path and persists through the very same
  ``AiDerivationService.persist_*`` methods the MCP tools call (born
  ``proposed`` where the workspace's workflow supports it, #1089).

These tests drive the real HTTP + service + DB stack, so they assert what the
wire actually answers. Providers are the credential-free ``mock`` default (no
network access): the mock glossary draft is exactly
``f"Term for {workspace_id}"``.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from application.ai_proposal_service import AI_DERIVATION_LABEL
from auth_tenancy.models import ROLE_EDITOR, ROLE_VIEWER, UserRole
from link_types.workspace_store import provision_workspace_link_types
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Adr,
    ArchitectureElement,
    Artifact,
    GlossaryTerm,
    Requirement,
    Risk,
    Tenant,
    TraceLink,
    User,
    Workspace,
)
from workflow.services import create_default_workflow

_JWT_OVERRIDES = {
    "AUTH_JWT_SECRET": "test-secret-not-a-real-key-1358",
    "AUTH_JWT_ISSUER": "reqflow",
    "AUTH_JWT_AUDIENCE": "reqflow-api",
    "AUTH_JWT_TTL_SECONDS": 3600,
}

_PASSWORD = "hunter2pass-1358"

_GLOSSARY_DERIVE_URL = "/api/v1/glossary/derive/"
_ADR_DERIVE_URL = "/api/v1/adrs/derive-from-decision/"
_RISK_DERIVE_URL = "/api/v1/architecture/{element}/derive-risks/"

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# fixtures / helpers — same shape as the sibling #1095 suite, so a reviewer
# can diff them against each other
# ---------------------------------------------------------------------------


def _provision(workspace: Workspace, item_type: str, preset: str = "extended") -> None:
    """Give the workspace a real workflow for *item_type*."""
    set_request_tenant(workspace.tenant_id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset=preset,
            item_type=item_type,
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


def _make_requirement(tenant: Tenant, workspace: Workspace, title: str) -> Requirement:
    """A source requirement so the workspace is not empty for glossary derivation."""
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


def _make_architecture_element(
    tenant: Tenant, workspace: Workspace, title: str
) -> ArchitectureElement:
    """Create an element row + backing artifact and return the *element* row."""
    set_request_tenant(tenant.id)
    try:
        artifact = Artifact.objects.create(
            workspace=workspace, artifact_type="ArchitectureElement", tenant_id=tenant.id
        )
        return ArchitectureElement.objects.create(
            artifact=artifact, tenant_id=tenant.id, title=title
        )
    finally:
        clear_request_tenant()


@contextmanager
def _tenant_scope(tenant_id):
    """Arm the tenant thread-local for direct ORM reads (REQ-L2-PL-002).

    ``TenantManager`` raises without one, and a count that answered 0 for the
    wrong reason would prove nothing about what the write actually persisted.
    """
    set_request_tenant(tenant_id)
    try:
        yield
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


def _list_count(client: APIClient, url: str) -> int:
    resp = client.get(url)
    assert resp.status_code == 200, resp.content
    return resp.json()["count"]


def _assert_envelope(response, code: str) -> dict:
    """The canonical error envelope (REQ-L2-RA-009) carries ``error.code``."""
    body = response.json()
    assert "error" in body, body
    assert body["error"]["code"] == code, body
    return body


@pytest.fixture
def tenant():
    return Tenant.objects.create(
        name="REST parity tenant", slug=f"par-{uuid.uuid4().hex[:8]}", is_active=True
    )


@pytest.fixture
def env(tenant):
    """Tenant + editor/viewer + a workspace whose three flows can propose."""
    workspace = _make_workspace(tenant, "REST parity WS")
    for item_type in ("GlossaryTerm", "Adr", "Risk"):
        _provision(workspace, item_type)
    editor = _make_user(tenant, "par-editor")
    viewer = _make_user(tenant, "par-viewer")
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
    requirement = _make_requirement(tenant, workspace, "Operators need throughput")
    element = _make_architecture_element(tenant, workspace, "Payment Gateway")
    return {
        "tenant": tenant,
        "workspace": workspace,
        "editor": editor,
        "viewer": viewer,
        "requirement": requirement,
        "element": element,
    }


# ---------------------------------------------------------------------------
# glossary: POST /api/v1/glossary/derive/
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
def test_glossary_preview_is_ephemeral_and_persists_nothing(env):
    response = _login(env["editor"]).post(
        _GLOSSARY_DERIVE_URL, {"workspace_id": str(env["workspace"].id)}, format="json"
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["ephemeral"] is True, "#1358: a preview must say it is ephemeral"
    assert body["workspace_id"] == str(env["workspace"].id)
    assert body["drafts"], "the mock provider drafts a non-empty preview"
    assert "written" not in body
    assert (
        _list_count(
            _login(env["editor"]),
            f"/api/v1/glossary/?workspace_id={env['workspace'].id}",
        )
        == 0
    ), "the preview persists nothing"


@override_settings(**_JWT_OVERRIDES)
def test_glossary_write_persists_proposed_terms(env):
    response = _login(env["editor"]).post(
        _GLOSSARY_DERIVE_URL,
        {"workspace_id": str(env["workspace"].id), "mode": "write"},
        format="json",
    )

    assert response.status_code == 201, response.content
    body = response.json()
    assert "ephemeral" not in body, "a write receipt is not a preview"
    written = body["written"]
    assert len(written) == 1  # the mock drafts exactly one term for a workspace
    entry = written[0]
    assert entry["status"] == "proposed", (
        "an AI-authored term accepted through the write seam must be born a "
        "reviewable proposal (#1089)"
    )
    assert entry["proposal"]["is_proposal"] is True
    assert entry["proposal"]["proposed_by"] == AI_DERIVATION_LABEL
    with _tenant_scope(env["tenant"].id):
        assert GlossaryTerm.objects.filter(id=entry["id"]).exists()

    # The natural REST read path sees the same row.
    listing = _login(env["editor"]).get(
        f"/api/v1/glossary/?workspace_id={env['workspace'].id}"
    )
    assert listing.status_code == 200
    assert listing.json()["count"] == 1


@override_settings(**_JWT_OVERRIDES)
def test_glossary_write_on_a_minimal_workspace_reports_no_proposal(tenant):
    """A graph without "proposed" is not a silent downgrade — it is reported."""
    workspace = _make_workspace(tenant, "Minimal glossary WS", preset="minimal")
    _provision(workspace, "GlossaryTerm", preset="minimal")
    editor = _make_user(tenant, "min-editor")
    set_request_tenant(tenant.id)
    try:
        UserRole.objects.create(
            tenant=tenant, user=editor, workspace=workspace, role=ROLE_EDITOR
        )
    finally:
        clear_request_tenant()

    response = _login(editor).post(
        _GLOSSARY_DERIVE_URL,
        {"workspace_id": str(workspace.id), "mode": "write"},
        format="json",
    )

    assert response.status_code == 201, response.content
    entry = response.json()["written"][0]
    assert entry["proposal"]["supported"] is False
    assert entry["proposal"]["is_proposal"] is False
    assert entry["proposal"]["reason"], "the gap must be explainable, not silent"
    assert entry["status"] != "proposed"


# ---------------------------------------------------------------------------
# ADR: POST /api/v1/adrs/derive-from-decision/
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
def test_adr_preview_is_ephemeral_and_persists_nothing(env):
    response = _login(env["editor"]).post(
        _ADR_DERIVE_URL,
        {
            "workspace_id": str(env["workspace"].id),
            "decision_description": "We will use Postgres instead of MySQL.",
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["ephemeral"] is True
    assert set(body["draft"]) == {"title", "description", "context", "consequences"}
    assert (
        _list_count(
            _login(env["editor"]), f"/api/v1/adrs/?workspace_id={env['workspace'].id}"
        )
        == 0
    )


@override_settings(**_JWT_OVERRIDES)
def test_adr_write_persists_a_proposed_adr(env):
    response = _login(env["editor"]).post(
        _ADR_DERIVE_URL,
        {
            "workspace_id": str(env["workspace"].id),
            "decision_description": "We will use Postgres instead of MySQL.",
            "mode": "write",
        },
        format="json",
    )

    assert response.status_code == 201, response.content
    body = response.json()
    written = body["written"]
    assert isinstance(written, dict)
    assert written["status"] == "proposed"
    assert written["proposal"]["is_proposal"] is True
    assert written["proposal"]["proposed_by"] == AI_DERIVATION_LABEL
    assert "trace_link_id" not in written, "raw free text has no source entity to link"
    with _tenant_scope(env["tenant"].id):
        assert Adr.objects.filter(id=written["id"]).exists()


# ---------------------------------------------------------------------------
# risk: POST /api/v1/architecture/{pk}/derive-risks/
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
def test_risk_preview_is_ephemeral_and_persists_nothing(env):
    response = _login(env["editor"]).post(
        _RISK_DERIVE_URL.format(element=env["element"].id), {}, format="json"
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["ephemeral"] is True
    assert body["architecture_element_id"] == str(env["element"].id)
    assert body["drafts"]
    assert (
        _list_count(
            _login(env["editor"]), f"/api/v1/risks/?workspace_id={env['workspace'].id}"
        )
        == 0
    )


@override_settings(**_JWT_OVERRIDES)
def test_risk_write_persists_proposed_risks_with_mitigates_links(env):
    response = _login(env["editor"]).post(
        _RISK_DERIVE_URL.format(element=env["element"].id),
        {"mode": "write"},
        format="json",
    )

    assert response.status_code == 201, response.content
    body = response.json()
    written = body["written"]
    assert written
    with _tenant_scope(env["tenant"].id):
        for entry in written:
            assert entry["status"] == "proposed"
            assert entry["proposal"]["is_proposal"] is True
            risk = Risk.objects.get(id=entry["id"])
            link = TraceLink.objects.get(id=entry["trace_link_id"])
            assert link.link_type == "mitigates"
            # 'mitigates' runs Risk -> ArchitectureElement; the new Risk is the source.
            assert link.source_id == risk.artifact_id
            assert link.target_id == env["element"].artifact_id


# ---------------------------------------------------------------------------
# RBAC + transport guards
# ---------------------------------------------------------------------------

_VIEWER_CASES = (
    (
        _GLOSSARY_DERIVE_URL,
        lambda env: {"workspace_id": str(env["workspace"].id), "mode": "write"},
    ),
    (
        _ADR_DERIVE_URL,
        lambda env: {
            "workspace_id": str(env["workspace"].id),
            "decision_description": "Viewer decision.",
            "mode": "write",
        },
    ),
    (
        _RISK_DERIVE_URL,
        lambda env: {"mode": "write"},
    ),
)


@pytest.mark.parametrize("url_template,payload_fn", _VIEWER_CASES)
@override_settings(**_JWT_OVERRIDES)
def test_a_viewer_cannot_reach_the_derivation_endpoints(env, url_template, payload_fn):
    """POST is WRITE-gated by the global RbacPermission — also for mode=preview.

    Same fence the MCP name-based write gate applies (#1358 documents it):
    before W12a a Viewer could not call the MCP tools at all, and these REST
    parity endpoints extend the identical Editor+ contract.
    """
    client = _login(env["viewer"])
    response = client.post(
        url_template.format(element=env["element"].id),
        payload_fn(env),
        format="json",
    )

    assert response.status_code == 403, response.content
    _assert_envelope(response, "PERMISSION_DENIED")


@override_settings(**_JWT_OVERRIDES)
def test_unauthenticated_is_401(env):
    response = APIClient().post(
        _GLOSSARY_DERIVE_URL, {"workspace_id": str(env["workspace"].id)}, format="json"
    )

    assert response.status_code == 401, response.content


_UNKNOWN_FIELD_CASES = (
    (_GLOSSARY_DERIVE_URL, lambda env: {"workspace_id": str(env["workspace"].id), "bogus": 1}, "bogus"),
    (
        _ADR_DERIVE_URL,
        lambda env: {
            "workspace_id": str(env["workspace"].id),
            "decision_description": "Some decision.",
            "bogus": 1,
        },
        "bogus",
    ),
    (_RISK_DERIVE_URL, lambda env: {"bogus": 1}, "bogus"),
)


@pytest.mark.parametrize("url_template,payload_fn,field", _UNKNOWN_FIELD_CASES)
@override_settings(**_JWT_OVERRIDES)
def test_unknown_body_keys_are_rejected(env, url_template, payload_fn, field):
    """#851: a caller that misspells a key must not get a silent no-op."""
    response = _login(env["editor"]).post(
        url_template.format(element=env["element"].id),
        payload_fn(env),
        format="json",
    )

    assert response.status_code == 400, response.content
    body = _assert_envelope(response, "VALIDATION_ERROR")
    details = {d["field"]: d["errors"] for d in body["error"]["details"]}
    assert details[field] == ["Unknown field."]


_MODE_POLICY_CASES = (
    (_GLOSSARY_DERIVE_URL, lambda env: {"workspace_id": str(env["workspace"].id)}, "mode"),
    (_GLOSSARY_DERIVE_URL, lambda env: {"workspace_id": str(env["workspace"].id)}, "policy"),
    (
        _RISK_DERIVE_URL,
        lambda env: {},
        "mode",
    ),
    (
        _ADR_DERIVE_URL,
        lambda env: {
            "workspace_id": str(env["workspace"].id),
            "decision_description": "Some decision.",
        },
        "policy",
    ),
)


@pytest.mark.parametrize("url_template,payload_fn,key", _MODE_POLICY_CASES)
@override_settings(**_JWT_OVERRIDES)
def test_invalid_mode_or_policy_is_400(env, url_template, payload_fn, key):
    payload = payload_fn(env)
    payload[key] = "bogus"

    response = _login(env["editor"]).post(
        url_template.format(element=env["element"].id), payload, format="json"
    )

    assert response.status_code == 400, response.content
    body = _assert_envelope(response, "VALIDATION_ERROR")
    assert f"'{key}' must be one of" in body["error"]["message"]


@override_settings(**_JWT_OVERRIDES)
def test_missing_workspace_is_400_and_unknown_workspace_is_404(env):
    client = _login(env["editor"])

    missing = client.post(_GLOSSARY_DERIVE_URL, {}, format="json")
    assert missing.status_code == 400, missing.content
    _assert_envelope(missing, "VALIDATION_ERROR")

    unknown = client.post(
        _GLOSSARY_DERIVE_URL, {"workspace_id": str(uuid.uuid4())}, format="json"
    )
    assert unknown.status_code == 404, unknown.content
    _assert_envelope(unknown, "NOT_FOUND")


@override_settings(**_JWT_OVERRIDES)
def test_malformed_workspace_is_400(env):
    response = _login(env["editor"]).post(
        _GLOSSARY_DERIVE_URL, {"workspace_id": "not-a-uuid"}, format="json"
    )

    assert response.status_code == 400, response.content
    _assert_envelope(response, "VALIDATION_ERROR")


@override_settings(**_JWT_OVERRIDES)
def test_empty_decision_description_is_400(env):
    response = _login(env["editor"]).post(
        _ADR_DERIVE_URL,
        {"workspace_id": str(env["workspace"].id), "decision_description": "   "},
        format="json",
    )

    assert response.status_code == 400, response.content
    _assert_envelope(response, "VALIDATION_ERROR")


@override_settings(**_JWT_OVERRIDES)
def test_unknown_architecture_element_is_404(env):
    response = _login(env["editor"]).post(
        _RISK_DERIVE_URL.format(element=uuid.uuid4()), {}, format="json"
    )

    assert response.status_code == 404, response.content
    _assert_envelope(response, "NOT_FOUND")
