"""Central MCP tool error mapping (#1663, #1661, N2-N4).

A domain validation, not-found, permission, optimistic-lock, integrity or
workflow-state failure must reach the client as its own error code instead of
the masked ``INTERNAL_ERROR``. These tests pin both the mapping table and the
fact that the generic group no longer swallows those exceptions itself.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

import pytest
from django.db import IntegrityError

from application.base import OptimisticLockError
from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.base import map_tool_exception
from mcp_server.tools.generic import GenericCrudToolGroup
from persistence.errors import NotFoundError, PermissionDeniedError, ValidationError
from workflow.lifecycle_manager import WorkflowConflictError, WorkflowStateError
from workflow.services import WorkflowItemNotFoundError

CTX = AuthContext(
    user_id=UUID("00000000-0000-0000-0000-000000000001"),
    tenant_id=UUID("00000000-0000-0000-0000-000000000002"),
    active_roles=("admin",),
    auth_method=AuthMethod.API_KEY,
    api_key_id=UUID("00000000-0000-0000-0000-000000000003"),
)
WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000010")
ENTITY_ID = UUID("00000000-0000-0000-0000-000000000020")


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (ValidationError("bad input"), "VALIDATION_ERROR"),
        (NotFoundError("gone"), "NOT_FOUND"),
        (PermissionDeniedError("nope"), "PERMISSION_DENIED"),
        (OptimisticLockError("stale"), "CONFLICT"),
        (IntegrityError("uq_tracelink_edge"), "CONFLICT"),
        (WorkflowConflictError("stale"), "CONFLICT"),
        (WorkflowItemNotFoundError("gone"), "NOT_FOUND"),
        (WorkflowStateError("wrong state"), "INVALID_STATE"),
    ],
)
def test_known_domain_exceptions_are_mapped(exc, code):
    mapped = map_tool_exception(exc)
    assert mapped is not None
    assert mapped[0] == code


def test_unknown_exception_stays_masked():
    assert map_tool_exception(KeyError("boom")) is None


def test_invalid_state_code_is_registered_on_both_dispatch_paths():
    """#573 used INVALID_STATE long before it was registered (#1082 class)."""
    from mcp_server.protocol_handler import ERROR_CODE_MAP, ERROR_CODES

    assert "INVALID_STATE" in ERROR_CODES
    assert "INVALID_STATE" in ERROR_CODE_MAP


class _UpdateRaisesService:
    """Minimal generic-group service whose update raises a domain error."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def create(self, ctx, workspace_id, term, definition=None):
        return SimpleNamespace(id=ENTITY_ID, workspace_id=WORKSPACE_ID)

    def update(self, ctx, term_id, definition=None):
        raise self._exc

    def delete(self, ctx, term_id):
        return None

    def get(self, ctx, term_id):
        return SimpleNamespace(id=term_id, workspace_id=WORKSPACE_ID)

    def list_by_workspace(self, workspace_id, ctx, include_deleted=False):
        return []


def _run_update(exc: Exception):
    group = GenericCrudToolGroup("glossary", lambda: _UpdateRaisesService(exc))
    with patch("mcp_server.tools.generic.validate_artifact_write", return_value=None):
        return group.execute_tool(
            "glossary.update",
            {"id": str(ENTITY_ID), "definition": "x"},
            CTX,
            "reqlo_test_key",
        )


def test_generic_update_maps_validation_error():
    result = _run_update(ValidationError("duplicate term"))
    assert result.error_code == "VALIDATION_ERROR"
    assert result.message == "duplicate term"


def test_generic_update_maps_integrity_error_to_conflict():
    result = _run_update(IntegrityError("uq_glossary_workspace_term"))
    assert result.error_code == "CONFLICT"
    # The driver message must not leak constraint/table names.
    assert "uq_glossary" not in result.message
