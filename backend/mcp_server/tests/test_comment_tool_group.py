"""comment.* MCP tool group (Menschen-im-System spec §4).

Plan-deviation note — the plan's Task 17 test block is written against a tool
group API that does not exist in this tree, so the six cases below keep their
names, mocks and assertions but use the real one:

* ``group.dispatch(name, args, ctx)`` -> ``BaseToolGroup.execute_tool(
  tool_name, params, auth_context, api_key)`` (``mcp_server/tools/base.py``).
* ``result.payload`` -> ``ToolResult.data`` and ``ToolResult(payload=...)`` ->
  ``ToolResult.ok(dict)`` (``mcp_server/protocol_handler.py``). ``data`` is what
  the transport hands to ``json.dumps``, so the json-safety assertion still
  guards exactly the regression it was written for (issue #441).
"""
import json
import uuid
from datetime import datetime
from datetime import timezone as dt_timezone
from unittest.mock import MagicMock, patch

import pytest

from mcp_server.tools.comment import CommentToolGroup
from persistence.errors import NotFoundError, PermissionDeniedError


def _comment_stub():
    stub = MagicMock()
    stub.id = uuid.uuid4()
    stub.pk = stub.id
    stub.artifact_id = uuid.uuid4()
    stub.author_id = uuid.uuid4()
    stub.text = "needs a rationale"
    stub.resolved = False
    stub.resolved_by_id = None
    stub.resolved_at = None
    stub.created_at = datetime(2026, 9, 4, 10, 0, tzinfo=dt_timezone.utc)
    return stub


@pytest.fixture
def ctx():
    return MagicMock()


@pytest.mark.django_db
def test_create_returns_a_json_serialisable_payload(ctx):
    group = CommentToolGroup()
    with patch("mcp_server.tools.comment.CommentService") as svc:
        svc.return_value.create_comment.return_value = _comment_stub()
        result = group.execute_tool(
            "comment.create",
            {"artifact_id": str(uuid.uuid4()), "text": "needs a rationale"},
            ctx,
            None,
        )

    # The transport uses stdlib json.dumps — a UUID or datetime in here is a 500.
    json.dumps(result.data)
    assert result.data["text"] == "needs a rationale"
    assert isinstance(result.data["id"], str)
    assert isinstance(result.data["created_at"], str)


@pytest.mark.django_db
def test_create_without_text_names_the_missing_field(ctx):
    """#982: a missing body field must name it, not answer "internal error".

    ``comment.create`` declares ``text`` as required, so omitting it (or the
    natural-guess ``body``) is a caller error. Sibling tools already answer
    ``Required parameter 'x' is missing``; this pins the same shape here.
    """
    group = CommentToolGroup()
    with patch("mcp_server.tools.comment.CommentService"):
        result = group.execute_tool(
            "comment.create",
            {"artifact_id": str(uuid.uuid4()), "body": "hello"},
            ctx,
            None,
        )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "text" in result.message
    assert "internal error" not in result.message.lower()


@pytest.mark.django_db
def test_payload_never_uses_the_reserved_content_key(ctx):
    group = CommentToolGroup()
    with patch("mcp_server.tools.comment.CommentService") as svc:
        svc.return_value.list_for_artifact.return_value = [_comment_stub()]
        result = group.execute_tool(
            "comment.list", {"artifact_id": str(uuid.uuid4())}, ctx, None
        )

    assert "content" not in result.data


@pytest.mark.django_db
def test_list_returns_a_comments_array(ctx):
    group = CommentToolGroup()
    with patch("mcp_server.tools.comment.CommentService") as svc:
        svc.return_value.list_for_artifact.return_value = [_comment_stub()]
        result = group.execute_tool(
            "comment.list", {"artifact_id": str(uuid.uuid4())}, ctx, None
        )

    json.dumps(result.data)
    assert len(result.data["comments"]) == 1


@pytest.mark.django_db
def test_resolve_returns_the_full_object(ctx):
    group = CommentToolGroup()
    stub = _comment_stub()
    stub.resolved = True
    with patch("mcp_server.tools.comment.CommentService") as svc:
        svc.return_value.resolve_comment.return_value = stub
        result = group.execute_tool("comment.resolve", {"id": str(stub.id)}, ctx, None)

    assert result.data["resolved"] is True
    assert result.data["text"] == "needs a rationale"


@pytest.mark.parametrize(
    ("tool_name", "params", "method_name"),
    [
        (
            "comment.create",
            {
                "artifact_id": str(uuid.uuid4()),
                "text": "hello",
                "workspace_id": str(uuid.uuid4()),
            },
            "create_comment",
        ),
        (
            "comment.list",
            {
                "artifact_id": str(uuid.uuid4()),
                "workspace_id": str(uuid.uuid4()),
            },
            "list_for_artifact",
        ),
        (
            "comment.resolve",
            {"id": str(uuid.uuid4()), "workspace_id": str(uuid.uuid4())},
            "resolve_comment",
        ),
    ],
)
def test_comment_tools_reject_workspace_id_before_service(
    ctx, tool_name, params, method_name
):
    group = CommentToolGroup()
    with patch("mcp_server.tools.comment.CommentService") as svc:
        result = group.execute_tool(tool_name, params, ctx, None)

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    getattr(svc.return_value, method_name).assert_not_called()


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (NotFoundError("missing"), "NOT_FOUND"),
        (PermissionDeniedError("denied"), "PERMISSION_DENIED"),
    ],
)
def test_resolve_maps_domain_errors_without_changing_other_tools(ctx, error, code):
    group = CommentToolGroup()
    with patch("mcp_server.tools.comment.CommentService") as svc:
        svc.return_value.resolve_comment.side_effect = error
        result = group.execute_tool(
            "comment.resolve", {"id": str(uuid.uuid4())}, ctx, None
        )

    assert result.success is False
    assert result.error_code == code


@pytest.mark.parametrize(
    ("tool_name", "params", "method_name", "error", "code"),
    [
        (
            "comment.create",
            {"artifact_id": str(uuid.uuid4()), "text": "hello"},
            "create_comment",
            PermissionDeniedError("denied"),
            "PERMISSION_DENIED",
        ),
        (
            "comment.list",
            {"artifact_id": str(uuid.uuid4())},
            "list_for_artifact",
            NotFoundError("missing"),
            "NOT_FOUND",
        ),
    ],
)
def test_comment_create_and_list_map_domain_errors(
    ctx, tool_name, params, method_name, error, code
):
    group = CommentToolGroup()
    with patch("mcp_server.tools.comment.CommentService") as svc:
        getattr(svc.return_value, method_name).side_effect = error
        result = group.execute_tool(tool_name, params, ctx, None)

    assert result.success is False
    assert result.error_code == code


def test_exactly_three_tools_are_declared():
    schemas = {schema["name"] for schema in CommentToolGroup._TOOL_SCHEMAS}
    assert schemas == {"comment.create", "comment.list", "comment.resolve"}


def test_delete_is_deliberately_not_exposed():
    """Spec §4: deletion is author-or-admin, a human decision — not an agent tool."""
    assert "comment.delete" not in CommentToolGroup._TOOL_MAP
