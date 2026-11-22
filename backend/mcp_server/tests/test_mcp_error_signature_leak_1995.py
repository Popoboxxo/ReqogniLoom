"""#1995 — MCP error messages must not leak Python service signatures.

The generic CRUD tool group used to embed ``str(exc)`` from a service
``TypeError`` in its client-facing VALIDATION_ERROR, exposing lines such as
``AdrService.create_adr() missing 1 required positional argument:
'description'``. The field name must still be actionable, but it has to come
from the published ``inputSchema`` — never from the Python call text.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.generic import GenericCrudToolGroup

pytestmark = pytest.mark.django_db

CTX = AuthContext(
    user_id=UUID("00000000-0000-0000-0000-000000000001"),
    tenant_id=UUID("00000000-0000-0000-0000-000000000002"),
    active_roles=("admin",),
    auth_method=AuthMethod.API_KEY,
    api_key_id=UUID("00000000-0000-0000-0000-000000000003"),
)
ENTITY_ID = UUID("00000000-0000-0000-0000-000000000020")

# Tokens that could only come from a Python exception string, never from a
# schema-derived validation message.
_SIGNATURE_LEAKS = (
    "Service",
    "create_adr",
    "create_risk",
    "update_adr",
    "positional argument",
    "() missing",
    "unexpected keyword argument",
)


def _ctx_for(name: str):
    """Create a Tenant + User + Workspace + AuthContext for *name*."""
    from persistence.models import Tenant, User, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name=name, slug=name)
    user = User.objects.create(
        username=f"{name}-user", email=f"{name}@example.com", tenant=tenant
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name=f"{name}-ws")
    finally:
        TenantContext.clear_tenant()
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )
    return workspace, ctx


def _assert_no_signature(message: str) -> None:
    for token in _SIGNATURE_LEAKS:
        assert token not in message, f"leaked Python signature token {token!r}: {message}"


def test_create_missing_required_field_names_field_without_python_signature():
    """adr.create without ``description``: actionable field name, no signature."""
    from application.adr_service import AdrService

    workspace, ctx = _ctx_for("adr-mcp-1995")
    group = GenericCrudToolGroup("adr", AdrService)

    # Isolate the TypeError branch: the attribute-definition gate may reject
    # the missing field earlier with its own (already safe) message.
    with patch("mcp_server.tools.generic.validate_artifact_write", return_value=None):
        result = group._handle_create(
            params={"workspace_id": str(workspace.id), "title": "Issue1995 ADR"},
            auth_context=ctx,
            api_key="reqlo_x",
        )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "description" in result.message
    assert result.message.startswith("Missing required field(s) for adr.create:")
    _assert_no_signature(result.message)


def test_create_lists_every_missing_required_field_without_python_signature():
    """risk.create missing both enums names both, in schema order."""
    from application.risk_service import RiskService

    workspace, ctx = _ctx_for("risk-mcp-1995")
    group = GenericCrudToolGroup("risk", RiskService)

    with patch("mcp_server.tools.generic.validate_artifact_write", return_value=None):
        result = group._handle_create(
            params={"workspace_id": str(workspace.id), "title": "Issue1995 Risk"},
            auth_context=ctx,
            api_key="reqlo_x",
        )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "probability" in result.message and "impact" in result.message
    assert result.message.startswith("Missing required field(s) for risk.create:")
    _assert_no_signature(result.message)


def test_update_type_error_names_invalid_field_from_schema_without_signature():
    """An invalid field is named from the schema's allowed property names.

    ``reject_unknown_params`` is patched to a no-op so the simulated service
    TypeError actually reaches the handler branch — the point is to verify
    that branch derives the field name from the schema, not from ``exc``.
    """
    from application.adr_service import AdrService

    workspace, ctx = _ctx_for("adr-mcp-1995-update")
    group = GenericCrudToolGroup("adr", AdrService)
    group._read_method = lambda **kwargs: SimpleNamespace(
        id=ENTITY_ID, workspace_id=workspace.id
    )

    def _boom(**kwargs):
        raise TypeError(
            "AdrService.update_adr() got an unexpected keyword argument 'bogus_field'"
        )

    with patch("mcp_server.tools.generic.reject_unknown_params"), patch(
        "mcp_server.tools.generic.validate_artifact_write", return_value=None
    ), patch.object(group, "_update_method", side_effect=_boom):
        result = group._handle_update(
            params={"id": str(ENTITY_ID), "bogus_field": "x"},
            auth_context=ctx,
            api_key="reqlo_x",
        )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "bogus_field" in result.message
    assert result.message.startswith("Invalid field(s) for adr.update:")
    _assert_no_signature(result.message)
