"""
Tests for COMP-MC-002 ToolRegistry TenantContext activation.

leaf_id : COMP-MC-002
req_id  : REQ-L2-MC-006 (API-key auth), REQ-L2-MC-007 (RBAC),
          REQ-L2-PL-001 (tenant isolation)

Covers:
- Valid API key activates ``persistence.tenancy.TenantContext`` with
  ``auth_ctx.tenant_id`` for the duration of ``dispatch_request`` and
  clears it in the ``finally`` block.
- Invalid API key does NOT activate ``TenantContext`` (auth failure
  short-circuits before the try-block, so no cleanup is required).

Why this matters:
  ``AuthorizationService.active_roles_for`` queries
  ``UserRole.objects`` (tenant-scoped default manager). Without an
  active ``TenantContext`` that lookup raises
  ``TenantContextNotSetError`` (REQ-L3-PL002-002) and every write
  tool is blocked behind ``PERMISSION_DENIED`` / empty roles.
  The fix activates the context inside ``dispatch_request`` so all
  downstream tenant-scoped queries succeed.

Implementation notes:
- ``TenantContext`` is a thread-local singleton; we read its state via
  the private ``_thread_local.tenant_id`` attribute.
- The auth services are mocked (``MagicMock``) — we do not need a
  database or a real API-key row for these tests.
- An autouse fixture clears ``TenantContext`` before and after each
  test so no sibling test can observe stale thread-local state.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from auth_tenancy.context import AuthMethod, IdentityClaims
from auth_tenancy.errors import AuthenticationFailed
from mcp_server.protocol_handler import ToolResult
from mcp_server.tool_registry import ToolRegistry
from persistence.tenancy import TenantContext, TenantContextNotSetError


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
TENANT_ID = UUID("00000000-0000-0000-0000-000000000002")
API_KEY_ID = UUID("00000000-0000-0000-0000-000000000003")
VALID_API_KEY = "rf_tenant_context_test_key"
INVALID_API_KEY = "rf_invalid_key_xxx"


def _claims() -> IdentityClaims:
    """Build a fresh IdentityClaims with the module-level test ids."""
    return IdentityClaims(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        roles=(),
        auth_method=AuthMethod.API_KEY,
        api_key_id=API_KEY_ID,
    )


# ---------------------------------------------------------------------------
# Autouse: prevent TenantContext leakage between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_tenant_context() -> Any:
    """Clear TenantContext before and after each test.

    The thread-local storage persists across tests in the same process;
    this fixture keeps the test environment hermetic.
    """
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_registry(
    *,
    auth_succeeds: bool = True,
    roles: tuple[str, ...] = ("editor",),
    record_tenant_during_execute: list | None = None,
) -> ToolRegistry:
    """Build a ToolRegistry with mocked auth services and a stubbed group.

    Args:
        auth_succeeds: If True, the mocked auth service returns valid
            claims. If False, it raises ``AuthenticationFailed``.
        roles: Active roles returned by the mocked authz service.
        record_tenant_during_execute: Optional list; if provided, the
            stubbed tool group appends the active tenant id (or None)
            observed at execute-time to this list. Use to assert the
            TenantContext state during dispatch.

    Returns:
        Configured :class:`ToolRegistry` with a single ``requirement``
        prefix group.
    """
    auth_svc = MagicMock()
    if auth_succeeds:
        auth_svc.validate_api_key.return_value = _claims()
    else:
        auth_svc.validate_api_key.side_effect = AuthenticationFailed(
            "invalid_api_key"
        )

    authz_svc = MagicMock()
    authz_svc.active_roles_for.return_value = roles
    authz_svc.decide_access.return_value = MagicMock(allow=True)

    registry = ToolRegistry(auth_service=auth_svc, authz_service=authz_svc)

    stub_group = MagicMock()

    def _execute(*args, **kwargs):
        if record_tenant_during_execute is not None:
            record_tenant_during_execute.append(
                getattr(TenantContext._thread_local, "tenant_id", None)
            )
        return ToolResult.ok({"ok": True})

    stub_group.execute_tool.side_effect = _execute
    registry.register_groups({"requirement": stub_group})
    return registry


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTenantContextActivation:
    """Verify TenantContext lifecycle inside ``dispatch_request``."""

    def test_valid_api_key_activates_tenant_context_during_dispatch(self):
        """A valid API key must set ``TenantContext`` to the auth tenant
        for the duration of the dispatch and clear it on return.

        Asserts the three most important contracts:
          1. The context is unset before dispatch.
          2. The context is set to ``auth_ctx.tenant_id`` while the
             tool group is executing.
          3. The context is cleared after dispatch returns.
        """
        observed: list = []
        registry = _build_registry(
            auth_succeeds=True, record_tenant_during_execute=observed
        )

        # 1. No context before the call.
        assert getattr(TenantContext._thread_local, "tenant_id", None) is None

        result = registry.dispatch_request(
            tool_name="requirement.get",
            params={"id": "00000000-0000-0000-0000-000000000099"},
            api_key=VALID_API_KEY,
        )

        # Dispatch succeeded and the tool group was reached.
        assert result.success is True
        assert len(observed) == 1, (
            "Tool group was not invoked — cannot verify in-dispatch context."
        )

        # 2. During dispatch, the active tenant id equals the auth-asserted
        # tenant id.
        assert observed[0] == TENANT_ID, (
            f"Expected tenant id {TENANT_ID} during dispatch, "
            f"got {observed[0]!r}"
        )

        # 3. After dispatch, the context is cleared (finally block ran).
        assert getattr(TenantContext._thread_local, "tenant_id", None) is None

    def test_invalid_api_key_does_not_activate_tenant_context(self):
        """Auth failure short-circuits BEFORE the try-block, so no
        TenantContext is set and no cleanup is required.

        The TenantContext must remain unset both before and after the
        call, and the tool group must NOT be reached.
        """
        observed: list = []
        registry = _build_registry(
            auth_succeeds=False, record_tenant_during_execute=observed
        )

        # No context before the call.
        assert getattr(TenantContext._thread_local, "tenant_id", None) is None

        result = registry.dispatch_request(
            tool_name="requirement.get",
            params={},
            api_key=INVALID_API_KEY,
        )

        # Auth failed with the expected error code.
        assert result.success is False
        assert result.error_code == "AUTH_FAILED"

        # The tool group was NOT invoked (auth-fail short-circuited).
        assert observed == [], (
            "Tool group was invoked despite auth failure — auth path is broken."
        )

        # No context was ever set — the auth-fail return happens before
        # the try block, so the thread-local must still be None.
        assert getattr(TenantContext._thread_local, "tenant_id", None) is None

    def test_tenant_context_cleared_on_permission_denied(self):
        """PERMISSION_DENIED early-return must still clear the context.

        The ``finally`` block runs on every return path inside the try,
        including the RBAC failure short-circuit.
        """
        observed: list = []
        registry = _build_registry(
            auth_succeeds=True, roles=("viewer",),
            record_tenant_during_execute=observed,
        )
        # Re-bind the authz decide_access to deny writes for viewer.
        registry._authz_service.decide_access.return_value = MagicMock(allow=False)

        result = registry.dispatch_request(
            tool_name="requirement.create",
            params={"workspace_id": str(UUID(int=16))},
            api_key=VALID_API_KEY,
        )

        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        # The tool group was NOT reached (RBAC blocked before step 6).
        assert observed == []
        # finally ran: no leaked context.
        assert getattr(TenantContext._thread_local, "tenant_id", None) is None

    def test_tenant_context_cleared_on_internal_error(self):
        """A tool-group exception must not leak the TenantContext.

        The outer try/finally guarantees cleanup even when
        ``execute_tool`` raises.
        """
        registry = _build_registry(auth_succeeds=True)
        # Override the stub group to raise. We do NOT need to record the
        # in-dispatch tenant id here — the post-condition (cleared
        # context) is the contract that matters.
        registry._groups["requirement"].execute_tool.side_effect = RuntimeError(
            "boom"
        )

        result = registry.dispatch_request(
            tool_name="requirement.get",
            params={"id": "00000000-0000-0000-0000-000000000099"},
            api_key=VALID_API_KEY,
        )

        assert result.success is False
        assert result.error_code == "INTERNAL_ERROR"
        # And the context was cleared despite the exception.
        assert getattr(TenantContext._thread_local, "tenant_id", None) is None

    def test_tenant_context_cleared_on_unknown_tool(self):
        """UNKNOWN_TOOL early-return must still clear the context."""
        registry = _build_registry(auth_succeeds=True)

        result = registry.dispatch_request(
            tool_name="does.not.exist",
            params={},
            api_key=VALID_API_KEY,
        )

        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"
        assert getattr(TenantContext._thread_local, "tenant_id", None) is None

    def test_stale_tenant_context_is_replaced_then_cleared(self):
        """If some other code set the context before dispatch, the
        registry must overwrite it with the auth-asserted tenant and
        clear it on return (NOT leave the stale value behind).
        """
        observed: list = []
        stale_tenant = UUID("00000000-0000-0000-0000-0000000000ff")
        TenantContext.set_tenant(stale_tenant)
        assert getattr(TenantContext._thread_local, "tenant_id", None) == stale_tenant

        registry = _build_registry(
            auth_succeeds=True, record_tenant_during_execute=observed
        )

        registry.dispatch_request(
            tool_name="requirement.get",
            params={"id": "00000000-0000-0000-0000-000000000099"},
            api_key=VALID_API_KEY,
        )

        # During dispatch, the context was the auth-asserted tenant,
        # NOT the stale value.
        assert observed == [TENANT_ID]
        # After dispatch, the context is cleared (not left as stale).
        assert getattr(TenantContext._thread_local, "tenant_id", None) is None


class TestTenantContextWithoutAuth:
    """Direct TenantContext behaviour checks (regression anchor)."""

    def test_get_tenant_raises_when_unset(self):
        """``TenantContext.get_tenant`` must raise when no context is set.

        This is the failure mode the fix prevents: a tenant-scoped query
        (``UserRole.objects.all()``) inside ``active_roles_for`` would
        raise this exception without the fix.
        """
        TenantContext.clear_tenant()
        with pytest.raises(TenantContextNotSetError):
            TenantContext.get_tenant()
