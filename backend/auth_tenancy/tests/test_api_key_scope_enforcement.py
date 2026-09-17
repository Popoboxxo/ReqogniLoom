"""API-key scope and workspace restriction (audit finding E2.1)."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from auth_tenancy.context import (
    AuthMethod,
    IdentityClaims,
    TenantContext as TenantContextValue,
)
from auth_tenancy.services.tenant_context import TenantContextService

TENANT_ID = UUID("22222222-2222-2222-2222-222222222222")
ALLOWED_WS = UUID("11111111-1111-1111-1111-111111111111")


def _claims(workspace_ids: tuple[str, ...]) -> IdentityClaims:
    return IdentityClaims(
        user_id=uuid4(),
        tenant_id=TENANT_ID,
        roles=(),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid4(),
        actor_type="agent",
        agent_label="Bot",
        scope="write",
        api_key_workspace_ids=workspace_ids,
    )


def _tenant() -> TenantContextValue:
    return TenantContextValue(tenant_id=TENANT_ID, tenant_name="t")


def test_empty_workspace_ids_keeps_all_roles():
    ctx = TenantContextService().build_auth_context(
        _claims(()), _tenant(), ("editor", "admin"), workspace_id=ALLOWED_WS
    )
    assert ctx.active_roles == ("editor", "admin")


def test_listed_workspace_keeps_roles():
    ctx = TenantContextService().build_auth_context(
        _claims((str(ALLOWED_WS),)),
        _tenant(),
        ("editor",),
        workspace_id=ALLOWED_WS,
    )
    assert ctx.active_roles == ("editor",)


def test_unlisted_workspace_loses_all_roles():
    ctx = TenantContextService().build_auth_context(
        _claims((str(ALLOWED_WS),)), _tenant(), ("admin",), workspace_id=uuid4()
    )
    assert ctx.active_roles == ()


def test_restricted_key_without_workspace_context_loses_all_roles():
    # A restricted key must not fall back to the tenant-wide role union, which
    # is exactly the path that would hand it every workspace it was fenced out of.
    ctx = TenantContextService().build_auth_context(
        _claims((str(ALLOWED_WS),)), _tenant(), ("admin",), workspace_id=None
    )
    assert ctx.active_roles == ()
