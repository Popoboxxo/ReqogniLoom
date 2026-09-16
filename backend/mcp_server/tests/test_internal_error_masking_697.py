"""#697 (CWE-209): every MCP tool-group catch-all masks the exception.

``BaseToolGroup.execute_tool`` has masked unmapped failures since fix #108, but
each group also wraps its own handler bodies in ``except Exception`` and those
inner handlers used to hand ``str(exc)`` straight to the caller — bypassing the
base-class net entirely. The sweep replaced them with a static message plus a
server-side log; these tests pin the wiring for one representative per shape:

* ``generic``  — the seven-handler CRUD group (delete / reactivate),
* ``review``   — a group with a typed branch *above* the broad one,
* ``link_type``— a module-level ``_guard`` that already logged before #697.

The fault is injected at the service seam, so no database is involved: the
handler's only job before the ``except`` is to call it.
"""
from __future__ import annotations

from unittest.mock import patch
from uuid import UUID

import pytest
from auth_tenancy.context import AuthContext, AuthMethod
from django.db.utils import ProgrammingError

from mcp_server.tools.generic import GenericCrudToolGroup
from mcp_server.tools.link_type import LinkTypeToolGroup
from mcp_server.tools.review import ReviewToolGroup

CTX = AuthContext(
    user_id=UUID("00000000-0000-0000-0000-000000000001"),
    tenant_id=UUID("00000000-0000-0000-0000-000000000002"),
    active_roles=("admin",),
    auth_method=AuthMethod.API_KEY,
    api_key_id=UUID("00000000-0000-0000-0000-000000000003"),
)
WORKSPACE_ID = str(UUID("00000000-0000-0000-0000-000000000010"))
ITEM_ID = str(UUID("00000000-0000-0000-0000-000000000020"))

#: A message with the shape of a real leak: driver internals, SQL, credentials.
SENSITIVE = (
    'ProgrammingError: relation "persistence_requirement" does not exist '
    'LINE 1: SELECT "persistence_requirement"."tenant_id" ... '
    '(host=db.internal user=reqogniloom_app)'
)

_GENERIC_MESSAGE = "An internal error occurred."


def _adr_group() -> GenericCrudToolGroup:
    from application.adr_service import AdrService

    return GenericCrudToolGroup("adr", AdrService)


class TestGenericCrudGroupMasksUnmappedFailures:
    def test_delete_masks_and_logs(self, caplog):
        group = _adr_group()

        with patch.object(
            group, "_delete_method", side_effect=ProgrammingError(SENSITIVE)
        ), caplog.at_level("ERROR"):
            result = group.execute_tool(
                "adr.delete", {"id": ITEM_ID}, CTX, "reqlo_test"
            )

        assert result.success is False
        assert result.error_code == "INTERNAL_ERROR"
        assert result.message == _GENERIC_MESSAGE
        assert SENSITIVE not in str(result.__dict__)
        assert SENSITIVE in caplog.text

    def test_reactivate_masks_and_logs(self, caplog):
        group = _adr_group()

        # ``_resolve_workspace_id`` reads the entity first; stubbed out so the
        # fault lands on the handler's own ``reactivate`` call without a DB.
        with patch.object(
            group, "_resolve_workspace_id", return_value=UUID(WORKSPACE_ID)
        ), patch(
            "workflow.services.reactivate", side_effect=ProgrammingError(SENSITIVE)
        ), caplog.at_level("ERROR"):
            result = group.execute_tool(
                "adr.reactivate", {"id": ITEM_ID}, CTX, "reqlo_test"
            )

        assert result.success is False
        assert result.error_code == "INTERNAL_ERROR"
        assert result.message == _GENERIC_MESSAGE
        assert SENSITIVE not in str(result.__dict__)
        assert SENSITIVE in caplog.text


class TestReviewGroupMasksUnmappedFailures:
    def test_reject_masks_and_logs(self, caplog):
        """The typed ``WorkflowItemNotFoundError`` branch above the broad one
        must keep forwarding its own message — only the unmapped tail is masked."""
        group = ReviewToolGroup()

        with patch(
            "workflow.services.outdate", side_effect=ProgrammingError(SENSITIVE)
        ), caplog.at_level("ERROR"):
            result = group.execute_tool(
                "review.reject",
                {
                    "item_id": ITEM_ID,
                    "item_type": "Requirement",
                    "workspace_id": WORKSPACE_ID,
                },
                CTX,
                "reqlo_test",
            )

        assert result.success is False
        assert result.error_code == "INTERNAL_ERROR"
        assert result.message == _GENERIC_MESSAGE
        assert SENSITIVE not in str(result.__dict__)
        assert SENSITIVE in caplog.text


class TestLinkTypeGuardMasksUnmappedFailures:
    def test_guard_masks_and_logs(self, caplog):
        def _boom(*args, **kwargs):
            raise ProgrammingError(SENSITIVE)

        with caplog.at_level("ERROR"):
            result = LinkTypeToolGroup._guard(_boom)

        assert result.success is False
        assert result.error_code == "INTERNAL_ERROR"
        assert result.message == _GENERIC_MESSAGE
        assert SENSITIVE not in str(result.__dict__)
        assert SENSITIVE in caplog.text

    @pytest.mark.parametrize(
        "domain_error,expected_code",
        [
            ("PermissionDeniedError", "PERMISSION_DENIED"),
            ("NotFoundError", "NOT_FOUND"),
            ("ValidationError", "VALIDATION_ERROR"),
        ],
    )
    def test_guard_still_forwards_domain_messages(self, domain_error, expected_code):
        """Control: the domain-authored branches above the catch-all are intact."""
        from application import base

        exc_type = getattr(base, domain_error)

        def _boom(*args, **kwargs):
            raise exc_type("domain-authored message")

        result = LinkTypeToolGroup._guard(_boom)

        assert result.error_code == expected_code
        assert result.message == "domain-authored message"
