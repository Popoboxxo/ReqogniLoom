"""#1290 — update/delete on an unknown id must answer NOT_FOUND, per entity.

``GenericCrudToolGroup`` serves five entities (adr, risk, issue, glossary,
change_request) and used to let a ``NotFoundError`` fall through its bare
``except Exception`` in ``_handle_update`` / ``_handle_delete``, answering the
masked ``INTERNAL_ERROR`` ("An internal error occurred.") instead of the entity's
own "<Type> <id> not found". Every other entity group (goal/icd/diagram/needs/
requirement/architecture) already reported NOT_FOUND.

The tests run the wrapped service for real (no mocks), so they pin the exact
message the service authored — not merely the error code. Label differences
(``ADR`` vs ``GlossaryTerm``) are asserted verbatim so a future message change
is caught.

ENV LIMITATION: the messages are checked for the id and the entity label; the
suite does not re-verify the underlying soft-delete side effects (covered by the
service's own tests).
"""
from __future__ import annotations

import importlib
from uuid import uuid4

import pytest

from mcp_server.tools.generic import GenericCrudToolGroup
from persistence.tests.factories import active_tenant, editor_ctx, make_workspace

#: ``(tool prefix, service dotted path, workflow item_type, message label)``.
_ENTITIES = [
    ("adr", "application.adr_service.AdrService", None, "ADR"),
    ("risk", "application.risk_service.RiskService", None, "Risk"),
    ("issue", "application.issue_service.IssueService", None, "Issue"),
    ("glossary", "application.glossary_service.GlossaryService", "GlossaryTerm", "GlossaryTerm"),
    (
        "change_request",
        "application.change_request_service.ChangeRequestService",
        "ChangeRequest",
        "ChangeRequest",
    ),
]


def _group(prefix: str, service_path: str, item_type: str | None) -> GenericCrudToolGroup:
    module_path, class_name = service_path.rsplit(".", 1)
    service_cls = getattr(importlib.import_module(module_path), class_name)
    if item_type is None:
        return GenericCrudToolGroup(prefix, service_cls)
    return GenericCrudToolGroup(prefix, service_cls, item_type=item_type)


@pytest.mark.django_db
@pytest.mark.parametrize("prefix,service_path,item_type,label", _ENTITIES)
class TestUnknownIdIsNotFoundPerEntity:
    """Every GenericCrudToolGroup entity reports its own NOT_FOUND message."""

    def test_update_unknown_id_reports_entity_message(
        self, prefix, service_path, item_type, label
    ) -> None:
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            missing = uuid4()
            group = _group(prefix, service_path, item_type)
            result = group._handle_update(
                params={"id": str(missing)}, auth_context=ctx, api_key=None
            )

        assert result.success is False
        assert result.error_code == "NOT_FOUND"
        # The message is the entity's own "<Type> <id> not found" — not the
        # masked catch-all.
        assert result.message.startswith(f"{label} {missing} not found")
        assert "internal error" not in result.message.lower()

    def test_delete_unknown_id_reports_entity_message(
        self, prefix, service_path, item_type, label
    ) -> None:
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            missing = uuid4()
            group = _group(prefix, service_path, item_type)
            result = group._handle_delete(
                params={"id": str(missing)}, auth_context=ctx, api_key=None
            )

        assert result.success is False
        assert result.error_code == "NOT_FOUND"
        assert result.message.startswith(f"{label} {missing} not found")
        assert "internal error" not in result.message.lower()

    def test_update_unknown_id_via_execute_tool(self, prefix, service_path, item_type, label) -> None:
        """The same contract through the public dispatcher (JSON-RPC path)."""
        with active_tenant() as tenant:
            ws = make_workspace(tenant)
            ctx = editor_ctx(tenant, ws)
            missing = uuid4()
            group = _group(prefix, service_path, item_type)
            result = group.execute_tool(
                f"{prefix}.update", {"id": str(missing)}, ctx, "reqlo_test"
            )

        assert result.success is False
        assert result.error_code == "NOT_FOUND"
        assert result.message.startswith(f"{label} {missing} not found")
