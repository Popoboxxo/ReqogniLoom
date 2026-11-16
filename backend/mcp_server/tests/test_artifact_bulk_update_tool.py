"""R3.2 — MCP tool ``artifact.bulk_update`` (group ``artifact``, 298th of 299).

Slice R3.2 of ``docs/superpowers/plans/2026-11-15-document-view-on-document.md``.
The batch semantics live in ``application.bulk_update_service`` (covered by
``application/tests/test_bulk_update_service.py``); this file pins the MCP
surface:

* the **manifest** (``docs/agent-templates/tool-manifest.json``) contains the
  tool and the catalogue size moved 296 -> 297 (297 -> 298 with
  ``artifact.bulk_transition``, 298 -> 299 with the Phase D ``tool`` group) (the
  drift gate compares the live
  registry against that file, so the number is not maintained by hand);
* the registry *advertises* the schema (required ``workspace_id`` + ``entries``)
  and classifies the tool as a write (RBAC-gated) — the fail-closed default;
* **error codes are the REST ones**: a refused batch is ``CONFLICT`` with the
  per-entry ``errors[]`` payload in ``details``, a request defect is
  ``VALIDATION_ERROR``, a missing write role is ``PERMISSION_DENIED``;
* an end-to-end dispatch (API key -> RBAC -> workspace gate -> tool -> service)
  writes through to the database and reports the new versions.

Everything here runs against the real ``ToolRegistry``/DB; nothing is mocked.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mcp_server.management.commands.export_tool_manifest import _MANIFEST_SUFFIX
from mcp_server.tool_registry import ToolRegistry
from persistence.middleware import clear_request_tenant, set_request_tenant
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db

EXPECTED_TOOL_COUNT = 299
BULK_TOOL = "artifact.bulk_update"


def _find_manifest_path() -> Path:
    """Locate the committed manifest in both the host and the container layout.

    Same walk-up as ``test_tool_manifest_drift._find_manifest_path``: on the host
    the repo root is three levels above ``tests/``, in Docker ``backend/`` *is*
    ``/app`` and ``docs/`` is mounted at ``/app/docs``.
    """
    for ancestor in Path(__file__).resolve().parents:
        candidate = ancestor / _MANIFEST_SUFFIX
        if candidate.is_file():
            return candidate
    raise AssertionError(f"could not find {_MANIFEST_SUFFIX} above {__file__}")


MANIFEST_PATH = _find_manifest_path()


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _document_workflow(e2e_tenant, e2e_workspace):
    """Provision the ``document_default`` workflow the create path needs."""
    set_request_tenant(e2e_tenant.id)
    try:
        create_default_workflow(
            workspace_id=e2e_workspace.id,
            preset="document_default",
            item_type="Document",
            tenant_id=e2e_tenant.id,
        )
    finally:
        clear_request_tenant()


@pytest.fixture(autouse=True)
def _roles(e2e_userrole_member, e2e_userrole_viewer):
    """Materialise the role rows the API keys resolve against."""


def _dispatch(tool_name: str, params: dict[str, Any], api_key: str):
    return ToolRegistry().dispatch_request(
        tool_name=tool_name, params=params, api_key=api_key
    )


def _create_document(api_key: str, workspace_id: str, title: str) -> dict[str, Any]:
    created = _dispatch(
        "document.create",
        {
            "workspace_id": workspace_id,
            "title": title,
            "kind": "Spec",
            "description": "Bulk update target",
            "body": "# Spec\n\nContent.",
        },
        api_key,
    )
    assert created.success is True, created.message
    return created.data["document"]


def _bulk(api_key: str, workspace_id: str, entries: list[dict[str, Any]]):
    return _dispatch(
        BULK_TOOL,
        {"workspace_id": workspace_id, "entries": entries},
        api_key,
    )


def _entry(document: dict[str, Any], **fields: Any) -> dict[str, Any]:
    return {
        "artifact_id": document["artifact_id"],
        "expected_version": document["version"],
        "fields": fields,
    }


# ---------------------------------------------------------------------------
# Manifest / registry (no DB needed, but the module is DB-marked)
# ---------------------------------------------------------------------------


def test_manifest_contains_bulk_update(manifest: dict[str, Any]) -> None:
    tools = {tool["name"]: tool for tool in manifest["tools"]}

    assert BULK_TOOL in tools
    tool = tools[BULK_TOOL]
    assert tool["prefix"] == "artifact"
    assert tool["is_write"] is True
    assert tool["inputSchema"]["required"] == ["workspace_id", "entries"]
    entries_schema = tool["inputSchema"]["properties"]["entries"]
    assert entries_schema["minItems"] == 1
    assert entries_schema["maxItems"] == 100
    assert entries_schema["items"]["required"] == [
        "artifact_id",
        "expected_version",
        "fields",
    ]


def test_tool_count_is_298(manifest: dict[str, Any]) -> None:
    assert manifest["tool_count"] == EXPECTED_TOOL_COUNT
    assert len(manifest["tools"]) == EXPECTED_TOOL_COUNT
    # 48 prefixes since MCP-Modernisierung Phase D added the ``tool`` group
    # (``tool.list_groups``); bulk_update itself joins the existing ``artifact``
    # group.
    assert len({tool["prefix"] for tool in manifest["tools"]}) == 48


def test_registry_advertises_the_tool_as_a_write() -> None:
    registry = ToolRegistry()
    registry._ensure_groups()

    schema = next(
        (
            entry
            for entry in registry.all_tool_schemas()
            if entry.get("name") == BULK_TOOL
        ),
        None,
    )
    assert schema is not None, f"{BULK_TOOL} missing from the live registry"
    assert schema["inputSchema"]["properties"]["entries"]["type"] == "array"
    # Fail-closed classification: a write tool is RBAC-gated unless listed as
    # read-only, and this one deliberately is not.
    assert registry._is_write_tool(BULK_TOOL) is True


# ---------------------------------------------------------------------------
# End-to-end dispatch
# ---------------------------------------------------------------------------


def test_bulk_update_dispatch_writes_every_entry(
    e2e_workspace, e2e_api_key_member
) -> None:
    workspace_id = str(e2e_workspace.id)
    first = _create_document(e2e_api_key_member, workspace_id, "Spec A")
    second = _create_document(e2e_api_key_member, workspace_id, "Spec B")

    result = _bulk(
        e2e_api_key_member,
        workspace_id,
        [
            _entry(first, title="Spec A (revised)"),
            _entry(second, body="# Spec B\n\nNew body."),
        ],
    )

    assert result.success is True, result.message
    assert result.data["errors"] == []
    assert [row["version"] for row in result.data["updated"]] == [2, 2]
    assert [row["artifact_id"] for row in result.data["updated"]] == [
        first["artifact_id"],
        second["artifact_id"],
    ]

    read = _dispatch("document.read", {"id": first["id"]}, e2e_api_key_member)
    assert read.data["document"]["title"] == "Spec A (revised)"
    assert read.data["document"]["version"] == 2


def test_refused_batch_is_conflict_and_writes_nothing(
    e2e_workspace, e2e_api_key_member
) -> None:
    workspace_id = str(e2e_workspace.id)
    valid = _create_document(e2e_api_key_member, workspace_id, "Stays")
    stale = _create_document(e2e_api_key_member, workspace_id, "Stale")

    result = _bulk(
        e2e_api_key_member,
        workspace_id,
        [
            _entry(valid, title="Must be rolled back"),
            {
                "artifact_id": stale["artifact_id"],
                "expected_version": 99,
                "fields": {"title": "stale write"},
            },
        ],
    )

    assert result.success is False
    assert result.error_code == "CONFLICT"
    # Same per-entry payload REST publishes with its 409 — the agent can tell
    # which row it has to re-read.
    assert result.details["updated"] == []
    assert [error["index"] for error in result.details["errors"]] == [1]
    assert result.details["errors"][0]["code"] == "CONFLICT"

    read = _dispatch("document.read", {"id": valid["id"]}, e2e_api_key_member)
    assert read.data["document"]["title"] == "Stays"
    assert read.data["document"]["version"] == 1


def test_more_than_100_entries_is_a_validation_error(
    e2e_workspace, e2e_api_key_member
) -> None:
    workspace_id = str(e2e_workspace.id)
    document = _create_document(e2e_api_key_member, workspace_id, "Spec")
    entries = [_entry(document, title=f"T{index}") for index in range(101)]

    result = _bulk(e2e_api_key_member, workspace_id, entries)

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_empty_entries_is_a_validation_error(
    e2e_workspace, e2e_api_key_member
) -> None:
    result = _bulk(e2e_api_key_member, str(e2e_workspace.id), [])

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_caller_without_write_role_is_denied(
    e2e_workspace, e2e_api_key_member, e2e_api_key_viewer
) -> None:
    workspace_id = str(e2e_workspace.id)
    document = _create_document(e2e_api_key_member, workspace_id, "Spec")

    result = _bulk(
        e2e_api_key_viewer,
        workspace_id,
        [_entry(document, title="nope")],
    )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


def test_entry_version_must_be_a_real_integer(
    e2e_workspace, e2e_api_key_member
) -> None:
    """``expected_version`` is not coerced — a string would weaken the compare."""
    workspace_id = str(e2e_workspace.id)
    document = _create_document(e2e_api_key_member, workspace_id, "Spec")

    result = _bulk(
        e2e_api_key_member,
        workspace_id,
        [
            {
                "artifact_id": document["artifact_id"],
                "expected_version": str(document["version"]),
                "fields": {"title": "nope"},
            }
        ],
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
