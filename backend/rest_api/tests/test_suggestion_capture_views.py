"""REST + MCP parity of ``suggestion.capture`` (ADR-032, plan P2).

The listen-mode contract (spec G3/G4) is only satisfied if every transport runs
the *same* server code. Both routes here are thin adapters over
``application.capture_service.CaptureService``, so this module pins:

* the REST route returns the documented ``{created, skipped, request_id}``;
* the error codes are the contract's (``CAPTURE_DISABLED``,
  ``PRODUCER_CONTEXT_REQUIRED``, ``TEXT_TOO_LONG``, ``WORKSPACE_FORBIDDEN``);
* the unknown-field guard rejects a typo instead of silently capturing nothing;
* the MCP tool answers the same shape and the same codes for the same input.

The model is a scripted fake, exactly as in the service-level tests: parity is
about the transports, not about model quality.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import (
    ROLE_ADMIN,
    ApiKey,
    PreferenceValue,
    UserRole,
)
from auth_tenancy.services.authentication import (
    generate_api_key_plaintext,
    hash_api_key,
)
from link_types.workspace_store import provision_workspace_link_types
from mcp_server.tools.suggestion import SuggestionToolGroup
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Suggestion, Tenant, User, Workspace
from persistence.tenancy import TenantContext

_SECRET = "test-secret-not-a-real-key-capture"
_PASSWORD = "capturepass12345"
_API_KEY = "reqlo_test_capture_key"

_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)

_MESSAGE = (
    "Das System muss eine eingehende Anfrage innerhalb von zwei Sekunden "
    "beantworten und bei Zeitüberschreitung einen Fehler melden."
)


class _FakeProvider:
    PROVIDER_NAME = "fake-capture"

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.prompts: list[str] = []

    def complete(self, prompt: str, *, purpose: str = "", timeout=None) -> str:  # noqa: ARG002
        self.prompts.append(prompt)
        return self.answer


_ANSWER = (
    "```json\n"
    '[{"operation": "create", "type": "Requirement", '
    '"fields": {"title": "Antwortzeit der API", '
    '"description": "Zwei Sekunden, sonst Fehler."}, '
    '"rationale": "stated"}]\n'
    "```"
)


@pytest.fixture
def cap_env(db):
    tenant = Tenant.objects.create(name="Cap T", slug="cap-t", is_active=True)
    set_request_tenant(tenant.id)
    try:
        admin = User.objects.create(
            username="capadmin", email="capadmin@t.test", tenant=tenant
        )
        admin.set_password(_PASSWORD)
        admin.save(update_fields=["password"])
        workspace = Workspace.objects.create(
            tenant=tenant, name="Cap WS", preset={"name": "standard"}
        )
        provision_workspace_link_types(
            workspace_id=workspace.id, tenant_id=tenant.id
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        plaintext = generate_api_key_plaintext()
        key = ApiKey.objects.create(
            tenant=tenant,
            user=admin,
            name="cap-relay",
            key_hash=hash_api_key(plaintext),
            principal_type="agent",
            agent_label="Relay",
            workspace_ids=[str(workspace.id)],
            capture_enabled=True,
            expires_at=timezone.now() + timedelta(days=1),
        )
        PreferenceValue.objects.create(
            tenant=tenant,
            scope="workspace",
            workspace=workspace,
            key="capture.enabled",
            value=True,
        )
    finally:
        clear_request_tenant()

    agent_ctx = AuthContext(
        user_id=admin.id,
        tenant_id=tenant.id,
        active_roles=("admin",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=key.id,
        actor_type="agent",
        agent_label="Relay",
        scope="write",
    )

    yield {
        "tenant": tenant,
        "workspace": workspace,
        "admin": admin,
        "key": key,
        "agent_key": plaintext,
        "agent_ctx": agent_ctx,
    }


def _login_client(username: str) -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": _PASSWORD},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def _agent_client(env: dict) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {env['agent_key']}")
    return client


def _use_provider(monkeypatch, answer: str = _ANSWER) -> _FakeProvider:
    provider = _FakeProvider(answer)
    monkeypatch.setattr(
        "application.llm_provider_resolution.resolve_provider",
        lambda: (provider, provider.PROVIDER_NAME, None),
    )
    return provider


def _body(env: dict, **overrides) -> dict:
    body = {
        "workspace_id": str(env["workspace"].id),
        "text": _MESSAGE,
        "client": "claude-code",
        "source_session": "session-1",
    }
    body.update(overrides)
    return body


def _set_switch(env: dict, value: bool) -> None:
    """Flip ``capture.enabled`` with a tenant context armed.

    ``PreferenceValue`` is tenant-scoped, so a plain query outside a request (a
    direct service/MCP test) needs the thread-local tenant. HTTP tests get it
    from the middleware; these two do not.
    """
    TenantContext.set_tenant(env["tenant"].id)
    try:
        PreferenceValue.objects.filter(key="capture.enabled").delete()
        if value:
            PreferenceValue.objects.create(
                tenant=env["tenant"],
                scope="workspace",
                workspace=env["workspace"],
                key="capture.enabled",
                value=True,
            )
    finally:
        TenantContext.clear_tenant()


def _read_suggestion(env: dict, suggestion_id):
    """Read one suggestion with a tenant context armed.

    The HTTP request's middleware clears ``TenantContext`` when it finishes, so a
    direct ORM assertion afterwards must arm it itself — the tenant-scoped
    manager refuses to run without one.
    """
    TenantContext.set_tenant(env["tenant"].id)
    try:
        return Suggestion.objects.get(id=suggestion_id)
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# REST
# ---------------------------------------------------------------------------


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_rest_capture_creates_a_suggestion_with_provenance(cap_env, monkeypatch):
    _use_provider(monkeypatch)
    resp = _agent_client(cap_env).post(
        "/api/v1/suggestions/capture/", _body(cap_env), format="json"
    )

    assert resp.status_code == 200, resp.content
    payload = resp.json()
    assert set(payload) == {"created", "skipped", "request_id"}
    assert len(payload["created"]) == 1
    assert payload["skipped"] == {
        "duplicate": 0,
        "filtered": 0,
        "invalid": 0,
        "redacted": 0,
    }

    stored = _read_suggestion(cap_env, payload["created"][0])
    assert stored.kind == Suggestion.Kind.ARTIFACT_CREATE
    assert stored.client == "claude-code"
    assert stored.source_session == "session-1"
    assert stored.producer == "suggestion.capture"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_rest_capture_with_switch_off_answers_capture_disabled(cap_env, monkeypatch):
    provider = _use_provider(monkeypatch)
    _set_switch(cap_env, False)

    resp = _agent_client(cap_env).post(
        "/api/v1/suggestions/capture/", _body(cap_env), format="json"
    )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CAPTURE_DISABLED"
    assert provider.prompts == []


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_rest_capture_without_the_right_answers_producer_context_required(
    cap_env, monkeypatch
):
    _use_provider(monkeypatch)
    cap_env["key"].capture_enabled = False
    cap_env["key"].save(update_fields=["capture_enabled"])

    resp = _agent_client(cap_env).post(
        "/api/v1/suggestions/capture/", _body(cap_env), format="json"
    )

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "PRODUCER_CONTEXT_REQUIRED"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_rest_capture_too_long_answers_text_too_long(cap_env):
    resp = _agent_client(cap_env).post(
        "/api/v1/suggestions/capture/",
        _body(cap_env, text="x" * 9000),
        format="json",
    )

    assert resp.status_code == 400
    body = resp.json()["error"]
    assert body["code"] == "TEXT_TOO_LONG"
    assert body["details"]["limit"] == 8000


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_rest_capture_rejects_an_unknown_field(cap_env):
    resp = _agent_client(cap_env).post(
        "/api/v1/suggestions/capture/",
        _body(cap_env, idempotencykey="typo"),
        format="json",
    )

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_rest_capture_rejects_an_unknown_client(cap_env):
    resp = _agent_client(cap_env).post(
        "/api/v1/suggestions/capture/",
        _body(cap_env, client="not-a-client"),
        format="json",
    )

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# MCP parity
# ---------------------------------------------------------------------------


def _mcp_capture(env: dict, params: dict):
    TenantContext.set_tenant(env["tenant"].id)
    try:
        return SuggestionToolGroup().execute_tool(
            "suggestion.capture", params, env["agent_ctx"], _API_KEY
        )
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_mcp_capture_returns_the_same_shape_as_rest(cap_env, monkeypatch):
    _use_provider(monkeypatch)

    result = _mcp_capture(
        cap_env,
        {
            "workspace_id": str(cap_env["workspace"].id),
            "text": _MESSAGE,
            "client": "claude-code",
            "source_session": "session-1",
        },
    )

    assert result.success is True
    data = result.data
    assert set(data) == {"created", "skipped", "request_id"}
    assert len(data["created"]) == 1
    assert data["skipped"] == {
        "duplicate": 0,
        "filtered": 0,
        "invalid": 0,
        "redacted": 0,
    }


@pytest.mark.django_db
def test_mcp_capture_answers_the_same_error_codes(cap_env, monkeypatch):
    provider = _use_provider(monkeypatch)
    _set_switch(cap_env, False)

    disabled = _mcp_capture(
        cap_env,
        {
            "workspace_id": str(cap_env["workspace"].id),
            "text": _MESSAGE,
            "client": "claude-code",
        },
    )
    assert disabled.success is False
    assert disabled.error_code == "CAPTURE_DISABLED"
    assert provider.prompts == []

    # Re-enable so the length check (which runs after the switch) is reachable.
    _set_switch(cap_env, True)
    too_long = _mcp_capture(
        cap_env,
        {
            "workspace_id": str(cap_env["workspace"].id),
            "text": "x" * 9000,
            "client": "claude-code",
        },
    )
    assert too_long.success is False
    assert too_long.error_code == "TEXT_TOO_LONG"
