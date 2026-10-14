"""Issue #1292 — canonical MCP path, deprecated alias and the auth matrix.

Two routes serve the MCP transport:

* ``/mcp/`` — **canonical** (ARCH-L1-003); every shipped client config points
  at it.
* ``/api/v1/mcp/`` — historical mounting under the REST prefix, **deprecated**.
  It keeps working but every response advertises the deprecation so the two
  can never silently drift apart again.

This module pins the three facts the issue is about:

1. both mounts answer the same requests (a regression that dropped one mount,
   or routed it to a different view, would go green everywhere else);
2. the three documented auth forms behave exactly as the auth table says —
   ``X-API-Key`` accepted, ``Authorization: Bearer reqlo_…`` accepted,
   ``Authorization: Bearer <JWT>`` rejected with ``bearer_not_supported``;
3. the deprecated alias carries the ``Deprecation``/``Sunset``/``Link`` headers
   while the canonical path does not.
"""
from __future__ import annotations

import json
import time

import pytest
from django.conf import settings
from django.test import Client

from auth_tenancy.jwt_tokens import encode_hs256

CANONICAL_PATH = "/mcp/"
LEGACY_PATH = "/api/v1/mcp/"
MONTS = (CANONICAL_PATH, LEGACY_PATH)

_TOOLS_LIST_BODY = json.dumps(
    {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
).encode()


def _post(path: str, *, api_key: str | None = None, bearer: str | None = None):
    """POST a tools/list to *path* with exactly one credential form."""
    client = Client()
    headers: dict[str, str] = {"content_type": "application/json"}
    if api_key is not None:
        headers["HTTP_X_API_KEY"] = api_key
    if bearer is not None:
        headers["HTTP_AUTHORIZATION"] = f"Bearer {bearer}"
    return client.post(path, data=_TOOLS_LIST_BODY, **headers)


def _jwt() -> str:
    """A structurally valid JWT signed with the deployment's JWT secret.

    The MCP transport rejects *every* JWT — the format check (``reqlo_``
    prefix) fires before any signature check — so a valid signature here keeps
    the test honest: it proves the rejection is about the credential *type*,
    not about a malformed token.
    """
    return encode_hs256(
        {
            "sub": "test-user",
            "iss": getattr(settings, "AUTH_JWT_ISSUER", "reqogniloom"),
            "aud": getattr(settings, "AUTH_JWT_AUDIENCE", "reqogniloom-api"),
            "exp": int(time.time()) + 3600,
        },
        getattr(settings, "AUTH_JWT_SECRET", "test-secret"),
    )


@pytest.mark.django_db
@pytest.mark.parametrize("path", MONTS)
def test_api_key_auth_is_accepted_on_both_mounts(path, e2e_api_key_admin):
    """``X-API-Key: reqlo_…`` is the preferred form and works on both mounts."""
    response = _post(path, api_key=e2e_api_key_admin)

    assert response.status_code == 200, response.content
    tools = response.json()["result"]["tools"]
    assert tools, "tools/list returned an empty catalogue"


@pytest.mark.django_db
@pytest.mark.parametrize("path", MONTS)
def test_bearer_api_key_is_accepted_on_both_mounts(path, e2e_api_key_admin):
    """``Authorization: Bearer reqlo_…`` is the second accepted form."""
    response = _post(path, bearer=e2e_api_key_admin)

    assert response.status_code == 200, response.content
    assert response.json()["result"]["tools"]


@pytest.mark.django_db
@pytest.mark.parametrize("path", MONTS)
def test_bearer_jwt_is_rejected_with_bearer_not_supported(path):
    """A JWT in ``Authorization: Bearer`` is rejected — intentionally (#1292).

    MCP accepts API keys only (REQ-L2-MC-006 / REQ-052). The error message must
    name the cause (``bearer_not_supported``) so a client author who copied a
    REST ``Authorization`` header knows it is the credential *type*, not a bad
    token.
    """
    response = _post(path, bearer=_jwt())

    assert response.status_code == 401, response.content
    message = response.json()["error"]["message"]
    assert "bearer_not_supported" in message, message


@pytest.mark.django_db
def test_both_mounts_serve_an_identical_tool_list(e2e_api_key_admin):
    """The alias must not drift: both mounts answer the same catalogue."""
    canonical = _post(CANONICAL_PATH, api_key=e2e_api_key_admin)
    legacy = _post(LEGACY_PATH, api_key=e2e_api_key_admin)

    assert canonical.status_code == legacy.status_code == 200
    canonical_tools = canonical.json()["result"]["tools"]
    legacy_tools = legacy.json()["result"]["tools"]
    assert [t["name"] for t in canonical_tools] == [t["name"] for t in legacy_tools]


@pytest.mark.django_db
def test_legacy_alias_advertises_its_deprecation(e2e_api_key_admin):
    """``/api/v1/mcp/`` carries Deprecation/Sunset/Link; ``/mcp/`` does not."""
    legacy = _post(LEGACY_PATH, api_key=e2e_api_key_admin)

    assert legacy["Deprecation"] == "true"
    assert legacy["Sunset"], "the sunset date must be advertised"
    assert legacy["Link"] == '</mcp/>; rel="alternate"'

    canonical = _post(CANONICAL_PATH, api_key=e2e_api_key_admin)
    assert "Deprecation" not in canonical
    assert "Sunset" not in canonical


@pytest.mark.django_db
def test_legacy_discovery_get_is_also_marked():
    """The unauthenticated GET discovery endpoint is marked on the alias too."""
    client = Client()

    legacy = client.get(LEGACY_PATH)
    assert legacy.status_code == 200
    assert legacy["Deprecation"] == "true"

    canonical = client.get(CANONICAL_PATH)
    assert canonical.status_code == 200
    assert "Deprecation" not in canonical
