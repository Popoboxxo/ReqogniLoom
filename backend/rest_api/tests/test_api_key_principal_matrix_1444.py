"""E1.4 — API-key principal matrix across REST and MCP (Plan E, issue #1444).

One literal expectation table, one real request per cell:

* keys: Bearer user, unfenced user key (``write``), fenced agent key
  (``read_only`` / ``author`` / ``admin``);
* calls: workspace list, read inside the fence, read outside, write inside,
  write outside — each through REST **and** MCP.

MCP calls are real ``POST /mcp/`` JSON-RPC 2.0 requests with ``X-API-Key`` and
the production dispatcher (no dispatcher mock). For every API-key row the two
doors must agree on the allow/deny class, and a denial must use the same error
category at both: HTTP 403 ``PERMISSION_DENIED`` ↔ JSON-RPC ``-32001``.

Known documented exception — MCP is API-key-only
------------------------------------------------
The Bearer user is listed in the matrix for completeness, but MCP rejects JWT
credentials by design (REQ-L2-MC-006 / REQ-052; the explicit
``bearer_not_supported`` branch in ``mcp_server/tool_registry.py`` — see
``_validate_api_key``). The literal table therefore expects ``AUTH_FAILED`` on
every MCP cell of the Bearer row, and the cross-door parity assertion is
deliberately restricted to the API-key rows. This is a spec/main divergence
recorded in the PR body, not a silent exemption.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import timedelta
from typing import Any

import pytest
from django.test import Client as DjangoClient
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from auth_tenancy.jwt_tokens import encode_hs256
from auth_tenancy.models import ROLE_EDITOR, UserRole
from auth_tenancy.services.authentication import AuthenticationService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Artifact,
    Requirement,
    Tenant,
    User,
    Workspace,
)
from presets.models import WorkspacePresetConfig

_SECRET = "e1-4-matrix-test-secret-not-a-real-key"
_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)

#: Expected class per (key label, call). ``allow`` / ``deny``. The MCP cells of
#: the Bearer row are the documented ``AUTH_FAILED`` exception described above.
MATRIX: dict[tuple[str, str], dict[str, str]] = {
    ("bearer", "list"): {"rest": "allow", "mcp": "deny"},
    ("bearer", "read_inside"): {"rest": "allow", "mcp": "deny"},
    ("bearer", "read_outside"): {"rest": "deny", "mcp": "deny"},
    ("bearer", "write_inside"): {"rest": "allow", "mcp": "deny"},
    ("bearer", "write_outside"): {"rest": "deny", "mcp": "deny"},
    ("user_write", "list"): {"rest": "allow", "mcp": "allow"},
    ("user_write", "read_inside"): {"rest": "allow", "mcp": "allow"},
    ("user_write", "read_outside"): {"rest": "deny", "mcp": "deny"},
    ("user_write", "write_inside"): {"rest": "allow", "mcp": "allow"},
    ("user_write", "write_outside"): {"rest": "deny", "mcp": "deny"},
    ("fenced_read_only", "list"): {"rest": "allow", "mcp": "allow"},
    ("fenced_read_only", "read_inside"): {"rest": "allow", "mcp": "allow"},
    ("fenced_read_only", "read_outside"): {"rest": "deny", "mcp": "deny"},
    ("fenced_read_only", "write_inside"): {"rest": "deny", "mcp": "deny"},
    ("fenced_read_only", "write_outside"): {"rest": "deny", "mcp": "deny"},
    ("fenced_author", "list"): {"rest": "allow", "mcp": "allow"},
    ("fenced_author", "read_inside"): {"rest": "allow", "mcp": "allow"},
    ("fenced_author", "read_outside"): {"rest": "deny", "mcp": "deny"},
    ("fenced_author", "write_inside"): {"rest": "allow", "mcp": "allow"},
    ("fenced_author", "write_outside"): {"rest": "deny", "mcp": "deny"},
    ("fenced_admin", "list"): {"rest": "allow", "mcp": "allow"},
    ("fenced_admin", "read_inside"): {"rest": "allow", "mcp": "allow"},
    ("fenced_admin", "read_outside"): {"rest": "deny", "mcp": "deny"},
    ("fenced_admin", "write_inside"): {"rest": "allow", "mcp": "allow"},
    ("fenced_admin", "write_outside"): {"rest": "deny", "mcp": "deny"},
}

_CALLS = ("list", "read_inside", "read_outside", "write_inside", "write_outside")
_API_KEY_LABELS = ("user_write", "fenced_read_only", "fenced_author", "fenced_admin")


@pytest.fixture(autouse=True)
def _reset_mcp_view_singletons(monkeypatch: pytest.MonkeyPatch) -> None:
    """The /mcp/ view keeps its registry/handler singletons module-global."""
    monkeypatch.setattr("mcp_server.views._tool_registry", None)
    monkeypatch.setattr("mcp_server.views._protocol_handler", None)


def _seed() -> dict[str, Any]:
    slug = f"e14-{uuid.uuid4().hex[:8]}"
    tenant = Tenant.objects.create(name=f"T-{slug}", slug=slug, is_active=True)
    user = User.objects.create(
        username=f"user-{slug}", email=f"{slug}@t.test", tenant=tenant
    )
    user.set_password("hunter2pass")
    user.save(update_fields=["password"])

    set_request_tenant(tenant.id)
    try:
        ws_a = Workspace.objects.create(
            tenant=tenant, name=f"WS-A-{slug}", preset={"name": "extended"}
        )
        ws_b = Workspace.objects.create(
            tenant=tenant, name=f"WS-B-{slug}", preset={"name": "extended"}
        )
        UserRole.objects.create(
            tenant=tenant, user=user, workspace=ws_a, role=ROLE_EDITOR
        )
        req_a = _requirement(tenant, ws_a, "req-a")
        req_b = _requirement(tenant, ws_b, "req-b")
    finally:
        clear_request_tenant()

    for workspace in (ws_a, ws_b):
        WorkspacePresetConfig.unscoped.create(
            tenant=tenant,
            workspace=workspace,
            active_tier="extended",
            terminology_profile="dev_mode",
            downgrade_policy="allow",
        )

    return {
        "tenant": tenant,
        "user": user,
        "ws_a": ws_a,
        "ws_b": ws_b,
        "req_a": req_a,
        "req_b": req_b,
    }


def _requirement(tenant: Tenant, workspace: Workspace, title: str) -> Requirement:
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="Requirement"
    )
    return Requirement.objects.create(
        tenant=tenant,
        workspace=workspace,
        artifact=artifact,
        title=title,
        description="e1.4 matrix fixture",
    )


def _mint_key(
    tenant: Tenant,
    user: User,
    *,
    scope: str,
    principal_type: str = "agent",
    workspace_ids: list[Workspace] | None = None,
) -> str:
    return (
        AuthenticationService()
        .create_api_key(
            user_id=user.id,
            tenant_id=tenant.id,
            name=f"e14-{scope}-{uuid.uuid4().hex[:6]}",
            principal_type=principal_type,
            scope=scope,
            workspace_ids=[str(ws.id) for ws in (workspace_ids or [])],
            expires_at=timezone.now() + timedelta(days=1),
        )
        .plaintext
    )


def _bearer_token(user: User, tenant: Tenant) -> str:
    now = int(time.time())
    return encode_hs256(
        {
            "user_id": str(user.id),
            "tenant_id": str(tenant.id),
            "roles": [ROLE_EDITOR],
            "iss": "reqflow",
            "aud": "reqflow-api",
            "iat": now,
            "exp": now + 3600,
        },
        secret=_SECRET,
    )


def _rest_cell(
    env: dict[str, Any], credentials: dict[str, str], call: str
) -> tuple[str, str | None]:
    client = APIClient()
    client.credentials(**credentials)
    ws_a, ws_b = env["ws_a"], env["ws_b"]
    req_a, req_b = env["req_a"], env["req_b"]

    if call == "list":
        response = client.get("/api/v1/workspaces/")
    elif call == "read_inside":
        response = client.get(f"/api/v1/requirements/?workspace_id={ws_a.id}")
    elif call == "read_outside":
        response = client.get(f"/api/v1/requirements/?workspace_id={ws_b.id}")
    elif call == "write_inside":
        response = client.patch(
            f"/api/v1/requirements/{req_a.id}/",
            {"title": f"matrix-inside-{uuid.uuid4().hex[:4]}", "change_reason": "matrix"},
            format="json",
        )
    elif call == "write_outside":
        response = client.patch(
            f"/api/v1/requirements/{req_b.id}/",
            {"title": f"matrix-outside-{uuid.uuid4().hex[:4]}", "change_reason": "matrix"},
            format="json",
        )
    else:  # pragma: no cover - guarded by the literal table
        raise AssertionError(f"unknown call {call}")

    if response.status_code < 400:
        return "allow", None
    body = response.json()
    return "deny", body.get("error", {}).get("code")


def _mcp_cell(
    env: dict[str, Any], header: dict[str, str], call: str
) -> tuple[str, str | None]:
    ws_a, ws_b = env["ws_a"], env["ws_b"]
    req_a, req_b = env["req_a"], env["req_b"]

    if call == "list":
        tool, arguments = "workspace.list", {}
    elif call == "read_inside":
        tool, arguments = "requirement.query", {"workspace_id": str(ws_a.id)}
    elif call == "read_outside":
        tool, arguments = "requirement.query", {"workspace_id": str(ws_b.id)}
    elif call == "write_inside":
        tool, arguments = (
            "requirement.update",
            {
                "id": str(req_a.id),
                "title": f"mcp-inside-{uuid.uuid4().hex[:4]}",
                "change_reason": "matrix",
            },
        )
    elif call == "write_outside":
        tool, arguments = (
            "requirement.update",
            {
                "id": str(req_b.id),
                "title": f"mcp-outside-{uuid.uuid4().hex[:4]}",
                "change_reason": "matrix",
            },
        )
    else:  # pragma: no cover - guarded by the literal table
        raise AssertionError(f"unknown call {call}")

    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }
    response = DjangoClient().post(
        "/mcp/",
        data=json.dumps(body),
        content_type="application/json",
        **header,
    )
    payload = response.json()
    if "error" in payload:
        return "deny", str(payload["error"]["code"])
    result = payload.get("result") or {}
    if result.get("isError"):
        return "deny", "isError"
    return "allow", None


@pytest.mark.django_db
@override_settings(**_JWT_OVERRIDES)
def test_api_key_principal_matrix() -> None:
    env = _seed()
    token = _bearer_token(env["user"], env["tenant"])

    credentials: dict[str, dict[str, str]] = {
        "bearer": {"HTTP_AUTHORIZATION": f"Bearer {token}"},
        "user_write": {
            "HTTP_X_API_KEY": _mint_key(
                env["tenant"], env["user"], scope="write", principal_type="user"
            )
        },
        "fenced_read_only": {
            "HTTP_X_API_KEY": _mint_key(
                env["tenant"], env["user"], scope="read_only", workspace_ids=[env["ws_a"]]
            )
        },
        "fenced_author": {
            "HTTP_X_API_KEY": _mint_key(
                env["tenant"], env["user"], scope="author", workspace_ids=[env["ws_a"]]
            )
        },
        "fenced_admin": {
            "HTTP_X_API_KEY": _mint_key(
                env["tenant"], env["user"], scope="admin", workspace_ids=[env["ws_a"]]
            )
        },
    }

    observed: dict[tuple[str, str], dict[str, tuple[str, str | None]]] = {}

    for key_label, creds in credentials.items():
        for call in _CALLS:
            rest_class, rest_code = _rest_cell(env, creds, call)
            mcp_class, mcp_code = _mcp_cell(env, creds, call)
            observed[(key_label, call)] = {
                "rest": (rest_class, rest_code),
                "mcp": (mcp_class, mcp_code),
            }

            expected = MATRIX[(key_label, call)]
            assert rest_class == expected["rest"], (
                f"REST {key_label}/{call}: expected {expected['rest']}, "
                f"got {rest_class} ({rest_code})"
            )
            assert mcp_class == expected["mcp"], (
                f"MCP {key_label}/{call}: expected {expected['mcp']}, "
                f"got {mcp_class} ({mcp_code})"
            )

    # Cross-door parity: same class at both doors for every API-key row, and a
    # denial uses the same error category (403 PERMISSION_DENIED ↔ -32001).
    for key_label in _API_KEY_LABELS:
        for call in _CALLS:
            rest_class, rest_code = observed[(key_label, call)]["rest"]
            mcp_class, mcp_code = observed[(key_label, call)]["mcp"]
            assert rest_class == mcp_class, (
                f"{key_label}/{call}: REST says {rest_class}, MCP says {mcp_class}"
            )
            if rest_class == "deny":
                assert rest_code == "PERMISSION_DENIED", (
                    f"REST {key_label}/{call} denial code: {rest_code}"
                )
                assert mcp_code == "-32001", (
                    f"MCP {key_label}/{call} denial code: {mcp_code}"
                )
