"""R2A-001 — every REST error envelope carries the correlation id.

ADR-014 §1 / REQ-071: ``body.error.request_id`` mirrors the ``X-Request-ID``
response header so a client can correlate a failed call with the server log
without depending on the header alone. Before this fix only a handful of views
added it (via ``views._with_request_id``): the canonical builder
``rest_api.serializers.build_error_response`` and the global DRF handler
``reqogniloom_exception_handler`` omitted it, so most error bodies had no
correlation id at all.

This module pins the corrected contract:

* the builder always emits ``request_id`` (``None`` outside a request context,
  which the published schema already allows);
* a real HTTP error response carries a ``request_id`` identical to its
  ``X-Request-ID`` header and a non-numeric string ``code``;
* API-001: an authenticated request that drives an item into ``proposed`` can
  GET ``/transitions/`` without the tenant-context 500 -- auth arms the
  thread-local tenant and the row-level-security GUC before the view runs, so
  the scoped manager used by ``resolve_workflow_version`` is safe.
"""
from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from rest_api.serializers import build_error_response

# ---------------------------------------------------------------------------
# Direct unit test of the canonical error builder.
# ---------------------------------------------------------------------------


def test_build_error_response_includes_request_id() -> None:
    """The builder always emits ``request_id``; outside a request it is None."""
    body = build_error_response("VALIDATION_ERROR", "en")
    assert "request_id" in body["error"]
    # No request context in a plain unit test -> the correlation id is not
    # fabricated. The OpenAPI ErrorBody schema already allows null here.
    assert body["error"]["request_id"] is None


# ---------------------------------------------------------------------------
# REV-02 — the plain-Django /api/ DB-unavailable 503 mirrors the header too.
# ---------------------------------------------------------------------------


def test_db_unavailable_middleware_mirrors_request_id() -> None:
    """``DatabaseUnavailableMiddleware.process_exception`` injects the id.

    The DRF exception handler injects ``request_id`` (see the HTTP contract
    below), but the narrow middleware that guards plain-Django ``/api/`` views
    used to return a three-field body. Drive ``process_exception`` through a
    real ``RequestIdMiddleware`` so the ContextVar is armed and there is an
    ``X-Request-ID`` header to compare against.
    """
    from django.db.utils import OperationalError
    from django.http import HttpResponse
    from django.test import RequestFactory

    from reqogniloom.middleware import (
        DatabaseUnavailableMiddleware,
        RequestIdMiddleware,
    )

    saturation = OperationalError(
        "FATAL:  remaining connection slots are reserved for roles with the "
        "SUPERUSER attribute"
    )
    captured: dict[str, Any] = {}

    def _inner(request: Any) -> HttpResponse:
        middleware = DatabaseUnavailableMiddleware(lambda r: None)
        captured["error_response"] = middleware.process_exception(request, saturation)
        return HttpResponse("ok")

    request = RequestFactory().get("/api/v1/some/plain/django/view/")
    outer = RequestIdMiddleware(_inner)(request)

    error_response = captured["error_response"]
    assert error_response is not None
    assert error_response.status_code == 503
    body = json.loads(error_response.content)
    assert set(body["error"]) == {"code", "message", "details", "request_id"}
    assert body["error"]["request_id"] == outer["X-Request-ID"]
    assert body["error"]["request_id"]  # non-empty correlation id


# ---------------------------------------------------------------------------
# HTTP contract: envelope id == header id, machine code is a non-numeric string.
# ---------------------------------------------------------------------------

# Protected routes that fail before any domain work. Whether the stack answers
# 401 or 403 depends on the active authenticator, but either way DRF raises an
# exception that reqogniloom_exception_handler normalises into the envelope.
_ERROR_ROUTES = [
    ("get", "/api/v1/requirements/"),
    ("get", "/api/v1/workspaces/"),
    ("get", "/api/v1/test-cases/"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("method,path", _ERROR_ROUTES)
def test_error_envelope_request_id_matches_header(method: str, path: str) -> None:
    """Every error envelope mirrors X-Request-ID and uses a stable string code."""
    response = getattr(APIClient(), method)(path)
    assert 400 <= response.status_code < 500, response.content

    body = response.json()
    assert "error" in body, body
    error = body["error"]
    assert "request_id" in error, error
    assert error["request_id"] == response.headers["X-Request-ID"]

    code = error["code"]
    assert isinstance(code, str) and code and not code.isdigit(), code


# ---------------------------------------------------------------------------
# API-001 (positive): authenticated GET /transitions/ after an agent proposal.
# ---------------------------------------------------------------------------

# Mirrors the proven GH-913 fixture: an agent API key POSTs a Requirement, the
# workflow engine seeds it into ``proposed`` and a workflow state row exists.
_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET="r2a001-secret-not-a-real-key",
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)


@pytest.fixture
def s11a_env() -> Any:
    """Tenant + admin + Extended workspace + agent API key."""
    from auth_tenancy.models import ROLE_ADMIN, ApiKey, UserRole
    from auth_tenancy.services.authentication import (
        generate_api_key_plaintext,
        hash_api_key,
    )
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.models import Tenant, User, Workspace
    from workflow.services import create_default_workflow

    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(
        name=f"R2A001 T {suffix}", slug=f"r2a001-t-{suffix}", is_active=True
    )
    admin = User.objects.create(
        username=f"r2a001-{suffix}", email=f"r2a001-{suffix}@t.test", tenant=tenant
    )
    admin.set_password("r2a001-pass-2026")
    admin.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="R2A001 WS", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        create_default_workflow(
            workspace_id=workspace.id,
            preset="extended",
            item_type="Requirement",
            tenant_id=tenant.id,
        )
        plaintext = generate_api_key_plaintext()
        ApiKey.objects.create(
            tenant=tenant,
            user=admin,
            name="r2a001-agent",
            key_hash=hash_api_key(plaintext),
            principal_type="agent",
            agent_label="R2A001 QA Bot",
            workspace_ids=[str(workspace.id)],
            expires_at=timezone.now() + timedelta(days=1),
        )
    finally:
        clear_request_tenant()

    return {"tenant": tenant, "workspace": workspace, "admin": admin, "key": plaintext}


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_authenticated_get_transitions_after_propose_is_200(s11a_env: Any) -> None:
    """API-001: auth arms the tenant context, so GET /transitions/ never 500s."""
    agent = APIClient()
    agent.credentials(HTTP_AUTHORIZATION=f"Bearer {s11a_env['key']}")

    # An agent-created Requirement is seeded into the "proposed" state.
    created = agent.post(
        "/api/v1/requirements/",
        {"workspace_id": str(s11a_env["workspace"].id), "title": "R2A001 proposed"},
        format="json",
    )
    assert created.status_code == 201, created.content
    item_id = created.json()["id"]

    # GET the transitions view (calls resolve_workflow_version through the
    # scoped manager) with auth. Before API-001's analysis this was feared to
    # raise TenantContextNotSetError; auth arms thread-local + GUC first.
    resp = agent.get(f"/api/v1/requirements/{item_id}/transitions/")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["current_state"] == "proposed", body
    assert "version" in body, body
