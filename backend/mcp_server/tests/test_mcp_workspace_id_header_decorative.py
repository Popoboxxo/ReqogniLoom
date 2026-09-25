"""``X-Workspace-ID`` is decorative at the MCP surface too — CR-22.

Audit track CR-22 (``docs/se/reports/deep_audit/system-audit-2026-09/
09-evidence-register.md``). The REST side of this claim is covered by
``rest_api/tests/test_workspace_id_header_decorative.py``; this module covers the
MCP transport, which had no coverage for the header at all.

The header is dropped one layer before any identity decision is taken. The HTTP
view forwards exactly three headers into the protocol layer
(``mcp_server/views.py:176-190``, ``_extract_django_headers``):
``HTTP_X_API_KEY``, ``X-API-Key`` and ``HTTP_AUTHORIZATION``. Everything else in
``request.META`` is discarded before :class:`~mcp_server.protocol_handler.
ProtocolHandler` sees the frame, and the handler's own
``TransportAdapter.extract_api_key`` (``protocol_handler.py:295-322``) reads only
``Authorization``, ``X-API-Key`` and — on stdio only — ``params.api_key``. There
is no channel by which a workspace could arrive from a header.

The assertion is the contract version of that: the same JSON-RPC call, by the
same key, resolves an identical identity with and without the header. The tool
used is ``workspace.get_context``, which echoes the caller's resolved
``tenant_id``/``user_id``/``active_roles`` directly
(``mcp_server/tools/cross_cutting.py:1046-1050``), so the comparison is on the
identity itself rather than on a proxy for it.

Header variants cover CR-22's "beliebige X-Workspace-ID-Werte": a workspace in a
foreign tenant, a workspace in the caller's own tenant where the caller holds no
role, a non-UUID string, and an empty value.
"""
from __future__ import annotations

from typing import Any, Dict

import pytest
from django.test import Client, RequestFactory

from mcp_server.tests.helpers import (
    extract_error_code,
    extract_result,
    post_mcp,
)
from mcp_server.views import _extract_django_headers
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, Workspace

#: The identity block ``workspace.get_context`` echoes for its caller.
_IDENTITY_KEYS = ("tenant_id", "user_id", "active_roles")

#: Header value kinds, per CR-22's "beliebige X-Workspace-ID-Werte".
_HEADER_KINDS = ("cross_tenant", "same_tenant_no_role", "non_uuid", "empty")

#: A synthetic, present credential. This test asserts which header *names* the
#: view forwards, never their values.
_PLACEHOLDER_CREDENTIAL = "reqlo_test_placeholder_token"


@pytest.fixture
def other_tenant_workspace() -> Workspace:
    """A workspace in a *different* tenant than the e2e tenant."""
    slug = f"mcp-hdr-other-{Tenant.objects.count()}"
    tenant = Tenant.objects.create(name=f"T-{slug}", slug=slug, is_active=True)
    set_request_tenant(tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tenant, name=f"WS-X-{slug}", preset={"name": "extended"}
        )
    finally:
        clear_request_tenant()


@pytest.fixture
def unroled_workspace(e2e_tenant: Tenant) -> Workspace:
    """A second workspace of the e2e tenant that no e2e user holds a role in."""
    set_request_tenant(e2e_tenant.id)
    try:
        return Workspace.objects.create(
            tenant=e2e_tenant, name="WS-UNROLED", preset={"name": "extended"}
        )
    finally:
        clear_request_tenant()


def _header_value(kind: str, other: Workspace, unroled: Workspace) -> str:
    """Return the concrete header value for a ``_HEADER_KINDS`` entry."""
    if kind == "cross_tenant":
        return str(other.id)
    if kind == "same_tenant_no_role":
        return str(unroled.id)
    if kind == "non_uuid":
        return "not-a-uuid-at-all"
    return ""


def _context(response) -> Dict[str, Any]:
    """Return the ``workspace_context`` payload of a ``workspace.get_context`` reply."""
    return extract_result(response)["workspace_context"]


# ---------------------------------------------------------------------------
# The transport drops the header
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("header_value", ["", "not-a-uuid", "0" * 8, "a b c"])
def test_mcp_transport_does_not_forward_the_workspace_header(
    header_value: str,
) -> None:
    """``_extract_django_headers`` must carry no workspace channel at all.

    This is the boundary assertion: whatever the protocol layer does, it can
    never see the header, because the view's extraction step returns a fixed
    three-key mapping. A future change that adds a workspace header here becomes
    a deliberate, test-visible act rather than an accident.
    """
    request = RequestFactory().post(
        "/mcp/",
        data=b"{}",
        content_type="application/json",
        HTTP_X_WORKSPACE_ID=header_value,
        HTTP_X_API_KEY=_PLACEHOLDER_CREDENTIAL,
        HTTP_AUTHORIZATION=f"Bearer {_PLACEHOLDER_CREDENTIAL}",
    )

    headers = _extract_django_headers(request)

    assert "HTTP_X_WORKSPACE_ID" not in headers
    assert "X-Workspace-ID" not in headers
    assert set(headers) == {"HTTP_X_API_KEY", "X-API-Key", "HTTP_AUTHORIZATION"}


# ---------------------------------------------------------------------------
# The resolved identity is identical with and without the header
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("header_kind", _HEADER_KINDS)
def test_get_context_identity_is_identical_with_and_without_the_header(
    admin_client: Client,
    e2e_userrole_admin,
    e2e_tenant: Tenant,
    e2e_workspace: Workspace,
    other_tenant_workspace: Workspace,
    unroled_workspace: Workspace,
    header_kind: str,
) -> None:
    """Core CR-22 contract at the MCP surface: same call, same identity.

    ``workspace.get_context`` is called with **no** ``workspace_id`` parameter,
    so the header is the only thing that could possibly supply a workspace. The
    resolved identity in the result must be identical either way, and must be
    the caller's real one.
    """
    header_value = _header_value(
        header_kind, other_tenant_workspace, unroled_workspace
    )

    plain = post_mcp(admin_client, "workspace.get_context", {})
    decorated = post_mcp(
        admin_client,
        "workspace.get_context",
        {},
        extra_headers={"HTTP_X_WORKSPACE_ID": header_value},
    )

    assert plain.status_code == decorated.status_code == 200, decorated.content

    plain_context = _context(plain)
    decorated_context = _context(decorated)

    for key in _IDENTITY_KEYS:
        assert decorated_context[key] == plain_context[key], (
            f"X-Workspace-ID changed the resolved {key!r}"
        )
    assert decorated_context == plain_context

    # Equality alone would be satisfied by two empty identities, so pin that the
    # identity is genuinely the caller's and genuinely non-trivial.
    assert decorated_context["tenant_id"] == str(e2e_tenant.id)
    assert decorated_context["active_roles"] == ["admin"]
    assert decorated_context["workspace_id"] is None


@pytest.mark.django_db
@pytest.mark.parametrize("header_kind", _HEADER_KINDS)
def test_header_cannot_override_the_explicit_workspace_parameter(
    admin_client: Client,
    e2e_userrole_admin,
    e2e_workspace: Workspace,
    other_tenant_workspace: Workspace,
    unroled_workspace: Workspace,
    header_kind: str,
) -> None:
    """An explicit ``workspace_id`` param must win; the header cannot redirect it.

    The parameter names a workspace the caller is admin in; the header names one
    they are not. If the header were live it would either hijack the target or
    fail the call. Instead the result must describe the parameter's workspace,
    unchanged.
    """
    header_value = _header_value(
        header_kind, other_tenant_workspace, unroled_workspace
    )
    params = {"workspace_id": str(e2e_workspace.id)}

    plain = post_mcp(admin_client, "workspace.get_context", params)
    decorated = post_mcp(
        admin_client,
        "workspace.get_context",
        params,
        extra_headers={"HTTP_X_WORKSPACE_ID": header_value},
    )

    assert plain.status_code == decorated.status_code == 200, decorated.content

    plain_context = _context(plain)
    decorated_context = _context(decorated)

    assert decorated_context == plain_context
    assert decorated_context["workspace_id"] == str(e2e_workspace.id)


# ---------------------------------------------------------------------------
# The write path's authorisation verdict is unchanged
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_write_denial_is_identical_with_and_without_the_header(
    viewer_client: Client,
    e2e_userrole_viewer,
    e2e_workspace: Workspace,
    other_tenant_workspace: Workspace,
) -> None:
    """A Viewer is denied the same write with and without the header.

    The write is ``link_type.create``: a workspaceless WRITE tool, so its gate is
    evaluated against the caller's tenant-wide role aggregate. The header names a
    workspace the viewer holds no role in; it must neither grant the write nor
    change the error. Doubled assertion (transport status + JSON-RPC error code)
    follows the convention of the neighbouring MCP tests.
    """
    params: Dict[str, Any] = {"key": "w1neg-header-key", "definition": {"k": "v"}}

    plain = post_mcp(viewer_client, "link_type.create", params)
    decorated = post_mcp(
        viewer_client,
        "link_type.create",
        params,
        extra_headers={"HTTP_X_WORKSPACE_ID": str(other_tenant_workspace.id)},
    )

    assert plain.status_code == decorated.status_code, decorated.content
    assert extract_error_code(plain) == extract_error_code(decorated)
    assert extract_error_code(decorated) == "PERMISSION_DENIED"


# ---------------------------------------------------------------------------
# The header is not an authentication channel
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_unauthenticated_call_fails_the_same_way_with_the_header(
    other_tenant_workspace: Workspace,
) -> None:
    """Without a key, the header must not rescue the call in any way.

    A header that could influence authentication or identity would turn this
    from an inert decoration into a credential, which is the exact class CR-22
    rules out.
    """
    client = Client()

    plain = post_mcp(client, "workspace.get_context", {})
    decorated = post_mcp(
        client,
        "workspace.get_context",
        {},
        extra_headers={"HTTP_X_WORKSPACE_ID": str(other_tenant_workspace.id)},
    )

    assert plain.status_code == decorated.status_code
    assert extract_error_code(plain) == extract_error_code(decorated) == "AUTH_FAILED"
