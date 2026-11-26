"""Plan P1.12 (M-16) — masked MCP failures are logged, never leaked.

Before this package the tool groups answered a static
``INTERNAL_ERROR`` / ``"An internal error occurred."`` for every unmapped
exception while the ``# noqa: BLE001 — masked, logged server-side`` comment
claimed a log record existed (CWE-209 masking without the diagnosis half).
These tests pin both halves of the contract:

* **Client side:** the answer stays the exact masked message and the caller's
  parameters — including anything secret-looking — never appear in it.
* **Server side:** an unexpected exception produces an ERROR record with
  ``exc_info`` set whose message names the tool, and expected branches
  (``ValidationError`` / ``NotFoundError`` / ``PermissionDeniedError``) stay
  traceback-free.

``logger.exception`` attaches the traceback — including ``str(exc)`` — so the
record is not limited to the tool name and the exception class. What *is*
guaranteed is narrower: no request params, bodies or tokens are interpolated
into the log call, so a secret in ``params`` never reaches the log through the
message itself.

leaf_id : COMP-MC-003 / COMP-MC-0xx (translucent dispatch)
req_id  : REQ-L2-MC-001
"""
from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from application.base import NotFoundError, ValidationError
from application.document_service import DocumentService
from application.work_item_service import WorkItemService
from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.document import DocumentToolGroup
from mcp_server.tools.requirements import RequirementsToolGroup
from mcp_server.tools.work_items import WorkItemToolGroup

pytestmark = pytest.mark.django_db

#: The one client-facing message a masked failure may produce.
MASKED = "An internal error occurred."

#: A parameter value that must never be logged or echoed back.
SECRET = "TOKEN-SHOULD-NOT-BE-LOGGED"

DOCUMENT_LOGGER = "mcp_server.tools.document"
WORK_ITEM_LOGGER = "mcp_server.tools.work_items"
REQUIREMENT_LOGGER = "mcp_server.tools.requirements"

_API_KEY = "reqlo_testkey_error_logging"


@pytest.fixture
def ctx() -> AuthContext:
    """An editor context — the groups themselves do not gate here."""
    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )


def _exec(group, tool_name: str, params: dict, ctx: AuthContext):
    """Run *tool_name* through the public tool-group dispatch interface."""
    return group.execute_tool(
        tool_name=tool_name, params=params, auth_context=ctx, api_key=_API_KEY
    )


def _error_records(caplog, logger_name: str) -> list[logging.LogRecord]:
    """ERROR+ records emitted by *logger_name*, in emission order."""
    return [
        record
        for record in caplog.records
        if record.name == logger_name and record.levelno >= logging.ERROR
    ]


def _envelope(result) -> str:
    """The client-visible part of *result*, serialised for substring checks."""
    return json.dumps(
        {
            "error_code": result.error_code,
            "message": result.message,
            "details": result.details,
        }
    )


# ---------------------------------------------------------------------------
# document.* — the branch P1.12 added logging to
# ---------------------------------------------------------------------------


def test_document_unexpected_failure_is_masked_and_logged(caplog, ctx) -> None:
    """The masked answer stays static; the traceback lands in the server log."""
    caplog.set_level(logging.ERROR)

    with patch.object(
        DocumentService, "list_documents", side_effect=RuntimeError("boom")
    ):
        result = _exec(
            DocumentToolGroup(),
            "document.query",
            {"workspace_id": str(uuid4()), "uid": "DOC-001"},
            ctx,
        )

    assert result.success is False
    assert result.error_code == "INTERNAL_ERROR"
    assert result.message == MASKED
    assert "boom" not in _envelope(result)

    records = _error_records(caplog, DOCUMENT_LOGGER)
    assert len(records) == 1
    record = records[0]
    assert record.exc_info is not None
    assert record.exc_info[0] is RuntimeError
    message = record.getMessage()
    assert "document.query" in message
    assert "RuntimeError" in message


def test_secret_parameters_never_reach_the_log_or_the_client(caplog, ctx) -> None:
    """Only the tool name and the exception class are recorded, not ``params``."""
    caplog.set_level(logging.ERROR)

    with patch.object(
        DocumentService, "list_documents", side_effect=RuntimeError("boom")
    ):
        result = _exec(
            DocumentToolGroup(),
            "document.query",
            {
                "workspace_id": str(uuid4()),
                "uid": "DOC-001",
                "secret": SECRET,
                "body": SECRET,
            },
            ctx,
        )

    assert SECRET not in caplog.text
    assert SECRET not in _envelope(result)
    assert result.error_code == "INTERNAL_ERROR"


def test_expected_validation_error_emits_no_traceback(caplog, ctx) -> None:
    """A ``ValidationError`` is an expected answer, not a diagnosable crash."""
    caplog.set_level(logging.DEBUG)

    with patch.object(
        DocumentService,
        "list_documents",
        side_effect=ValidationError("workspace not found"),
    ):
        result = _exec(
            DocumentToolGroup(),
            "document.query",
            {"workspace_id": str(uuid4())},
            ctx,
        )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert result.message == "workspace not found"
    assert [record for record in caplog.records if record.exc_info] == []


# ---------------------------------------------------------------------------
# work_item.* — the same contract, different group
# ---------------------------------------------------------------------------


def test_work_item_unexpected_failure_is_masked_and_logged(caplog, ctx) -> None:
    caplog.set_level(logging.ERROR)

    with patch.object(
        WorkItemService, "list_work_items", side_effect=RuntimeError("boom")
    ):
        result = _exec(
            WorkItemToolGroup(),
            "work_item.query",
            {
                "workspace_id": str(uuid4()),
                "document_id": str(uuid4()),
                "secret": SECRET,
            },
            ctx,
        )

    assert result.success is False
    assert result.error_code == "INTERNAL_ERROR"
    assert result.message == MASKED
    assert "boom" not in _envelope(result)
    assert SECRET not in _envelope(result)
    assert SECRET not in caplog.text

    records = _error_records(caplog, WORK_ITEM_LOGGER)
    assert len(records) == 1
    record = records[0]
    assert record.exc_info is not None
    assert "work_item.query" in record.getMessage()
    assert "RuntimeError" in record.getMessage()


def test_work_item_expected_not_found_emits_no_traceback(caplog, ctx) -> None:
    caplog.set_level(logging.DEBUG)

    with patch.object(
        WorkItemService, "list_work_items", side_effect=NotFoundError("no document")
    ):
        result = _exec(
            WorkItemToolGroup(),
            "work_item.query",
            {"workspace_id": str(uuid4())},
            ctx,
        )

    assert result.error_code == "NOT_FOUND"
    assert result.message == "no document"
    assert [record for record in caplog.records if record.exc_info] == []


# ---------------------------------------------------------------------------
# requirement.* — one branch that already logged, one that had no local catch-all
# ---------------------------------------------------------------------------


def test_requirement_masked_branch_logs_with_exc_info(caplog, ctx) -> None:
    """``requirement.outdate`` masks the service failure *and* logs it (#697)."""
    caplog.set_level(logging.ERROR)
    service = MagicMock()
    service.delete_requirement.side_effect = RuntimeError("boom")

    result = _exec(
        RequirementsToolGroup(service=service),
        "requirement.outdate",
        {"id": str(uuid4()), "secret": SECRET},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "INTERNAL_ERROR"
    assert result.message == MASKED
    assert "boom" not in _envelope(result)
    assert SECRET not in _envelope(result)
    assert SECRET not in caplog.text

    records = _error_records(caplog, REQUIREMENT_LOGGER)
    assert len(records) == 1
    assert records[0].exc_info is not None
    assert "requirement.outdate" in records[0].getMessage()


def test_requirement_branch_without_a_local_catch_all_is_still_logged(
    caplog, ctx
) -> None:
    """``requirement.query`` has no local catch-all — the dispatch net logs it.

    This is the diagnostic half of the masking contract for the handlers that
    P1.12 did not have to touch: the base group's safety net records the
    traceback and names the tool, so the client-side masking is not silent.
    """
    caplog.set_level(logging.ERROR)
    service = MagicMock()
    service.list_requirements.side_effect = RuntimeError("boom")

    result = _exec(
        RequirementsToolGroup(service=service),
        "requirement.query",
        {"workspace_id": str(uuid4()), "secret": SECRET},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "INTERNAL_ERROR"
    assert result.message == MASKED
    assert "boom" not in _envelope(result)
    assert SECRET not in _envelope(result)
    assert SECRET not in caplog.text

    logged = [
        record
        for record in caplog.records
        if record.levelno >= logging.ERROR
        and "requirement.query" in record.getMessage()
    ]
    assert len(logged) == 1
    assert logged[0].exc_info is not None
    assert logged[0].exc_info[0] is RuntimeError
