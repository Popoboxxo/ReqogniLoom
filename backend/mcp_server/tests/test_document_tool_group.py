"""Plan F F2-T6 (ADR-026) — the ``document.*`` MCP tool group.

Drives the real ``ToolRegistry.dispatch_request`` stack (API-key auth -> RBAC ->
workspace gate -> tool group -> ``DocumentService``) against a real database,
so the transport is exercised end to end and nothing is mocked:

* create/read/query round-trip incl. ``custom_fields`` on the backing Artifact;
* update (+ optimistic-lock conflict), freeze refusal (F-3) and the
  gate refusal (G-4) surface the REST error codes ``FIELD_FROZEN`` /
  ``DOCUMENT_GATE_FAILED``;
* transition applies the F-1 freeze and F-5 re-open version bump;
* versions/diff read the shared ``ArtifactVersion`` store;
* soft delete hides from ``query`` until reactivated (G1.5);
* viewer may read but not write (RBAC parity);
* the dispatcher resolves the workspace fence from the document id.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from application.document_service import DocumentService
from mcp_server.tool_registry import ToolRegistry
from mcp_server.workspace_scope import resolve_target_workspace_id
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Document
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db

RELEASE_STATE = "Freigegeben"
REVIEW_STATE = "In Prüfung"


@pytest.fixture(autouse=True)
def _roles(e2e_userrole_admin, e2e_userrole_member, e2e_userrole_viewer):
    """Materialise the role rows the API keys resolve against."""
    return None


@pytest.fixture(autouse=True)
def _document_workflow(e2e_tenant, e2e_workspace):
    """Provision the ``document_default`` workflow the transitions need."""
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


def _dispatch(tool_name: str, params: dict[str, Any], api_key: str):
    """Run one dispatch through a fully real (unmocked) ToolRegistry."""
    return ToolRegistry().dispatch_request(
        tool_name=tool_name, params=params, api_key=api_key
    )


def _create(api_key: str, workspace_id: str, **overrides: Any):
    params: dict[str, Any] = {
        "workspace_id": workspace_id,
        "title": "System Spec",
        "kind": "Spec",
        "description": "How the system behaves",
        "body": "# System Spec\n\nContent.",
    }
    params.update(overrides)
    return _dispatch("document.create", params, api_key)


def _transition(api_key: str, document_id: str, target: str, **extra: Any):
    params = {"id": document_id, "target_state": target}
    params.update(extra)
    return _dispatch("document.transition", params, api_key)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_create_read_and_query_round_trip(
    e2e_workspace, e2e_api_key_member
) -> None:
    workspace_id = str(e2e_workspace.id)
    created = _create(
        e2e_api_key_member,
        workspace_id,
        custom_fields={"traceability_ref": "REQ-L1-001"},
    )
    assert created.success is True, created.message
    document = created.data["document"]
    assert document["uid"].startswith("DOC-")
    assert document["workspace_id"] == workspace_id
    assert document["status"] == "Entwurf"
    assert document["version"] == 1
    assert document["artifact_id"]
    assert document["custom_fields"] == {"traceability_ref": "REQ-L1-001"}

    read = _dispatch(
        "document.read", {"id": document["id"]}, e2e_api_key_member
    )
    assert read.success is True, read.message
    assert read.data["document"]["body"] == "# System Spec\n\nContent."

    listed = _dispatch(
        "document.query", {"workspace_id": workspace_id}, e2e_api_key_member
    )
    assert listed.success is True, listed.message
    assert document["id"] in {row["id"] for row in listed.data["documents"]}
    assert listed.data["count"] == len(listed.data["documents"])


def test_create_workflow_init_failure_is_an_internal_error_and_rolls_back(
    e2e_workspace, e2e_api_key_member
) -> None:
    """P2.13: the create is rolled back and the tool answers a static error.

    The handler maps ``WorkflowInitializationFailedError`` to ``INTERNAL_ERROR``
    with the fixed transport-neutral sentence (never the cause) and writes no
    document — the service's transaction already rolled everything back.
    """
    workspace_id = str(e2e_workspace.id)

    with patch(
        "workflow.services.initialize_workflow_states",
        side_effect=RuntimeError("boom"),
    ):
        result = _create(e2e_api_key_member, workspace_id)

    assert result.success is False
    assert result.error_code == "INTERNAL_ERROR"
    assert result.message == (
        "The artifact was not created because its workflow state could not be "
        "initialised."
    )
    assert "boom" not in (result.message or "")
    assert Document.unscoped.filter(workspace_id=e2e_workspace.id).count() == 0


def test_query_filters_by_uid(e2e_workspace, e2e_api_key_member) -> None:
    workspace_id = str(e2e_workspace.id)
    first = _create(e2e_api_key_member, workspace_id)
    _create(e2e_api_key_member, workspace_id, title="Other")
    uid = first.data["document"]["uid"]

    listed = _dispatch(
        "document.query",
        {"workspace_id": workspace_id, "uid": uid},
        e2e_api_key_member,
    )
    assert listed.success is True, listed.message
    assert [row["uid"] for row in listed.data["documents"]] == [uid]
    assert listed.data["count"] == 1


def test_query_passes_the_uid_filter_to_the_service(
    e2e_workspace, e2e_api_key_member, monkeypatch
) -> None:
    """Seam assertion for plan P1.11 (M-15).

    The uid filter must reach ``DocumentService.list_documents`` as a keyword
    argument. A client-side list comprehension after an unfiltered fetch would
    leave ``uid`` out of the call and fail here — that is exactly the
    regression this test pins.
    """
    workspace_id = str(e2e_workspace.id)
    first = _create(e2e_api_key_member, workspace_id)
    _create(e2e_api_key_member, workspace_id, title="Other")
    uid = first.data["document"]["uid"]

    calls: list[dict[str, Any]] = []
    real_list_documents = DocumentService.list_documents

    def _spy(self, *args: Any, **kwargs: Any):
        calls.append(dict(kwargs))
        return real_list_documents(self, *args, **kwargs)

    monkeypatch.setattr(DocumentService, "list_documents", _spy)

    listed = _dispatch(
        "document.query",
        {"workspace_id": workspace_id, "uid": uid},
        e2e_api_key_member,
    )
    assert listed.success is True, listed.message
    assert len(calls) == 1
    assert calls[0]["uid"] == uid
    assert calls[0]["workspace_id"] == e2e_workspace.id
    assert calls[0]["include_deleted"] is False
    assert [row["uid"] for row in listed.data["documents"]] == [uid]


def test_query_with_an_unknown_uid_returns_an_empty_page(
    e2e_workspace, e2e_api_key_member
) -> None:
    workspace_id = str(e2e_workspace.id)
    _create(e2e_api_key_member, workspace_id)

    listed = _dispatch(
        "document.query",
        {"workspace_id": workspace_id, "uid": "DOC-999"},
        e2e_api_key_member,
    )
    assert listed.success is True, listed.message
    assert listed.data["count"] == 0
    assert listed.data["documents"] == []


def test_query_treats_a_blank_uid_as_no_filter(
    e2e_workspace, e2e_api_key_member
) -> None:
    """The empty-value normalisation is unchanged: ``""`` means "no filter"."""
    workspace_id = str(e2e_workspace.id)
    _create(e2e_api_key_member, workspace_id)
    _create(e2e_api_key_member, workspace_id, title="Other")

    listed = _dispatch(
        "document.query",
        {"workspace_id": workspace_id, "uid": "   "},
        e2e_api_key_member,
    )
    assert listed.success is True, listed.message
    assert listed.data["count"] == len(listed.data["documents"]) == 2


def test_query_combines_the_uid_filter_with_include_outdated(
    e2e_workspace, e2e_api_key_member
) -> None:
    workspace_id = str(e2e_workspace.id)
    created = _create(e2e_api_key_member, workspace_id)
    document_id = created.data["document"]["id"]
    uid = created.data["document"]["uid"]
    _dispatch(
        "document.outdate",
        {"id": document_id, "reason": "no longer needed"},
        e2e_api_key_member,
    )

    hidden = _dispatch(
        "document.query",
        {"workspace_id": workspace_id, "uid": uid},
        e2e_api_key_member,
    )
    assert hidden.success is True, hidden.message
    assert hidden.data["count"] == 0

    visible = _dispatch(
        "document.query",
        {"workspace_id": workspace_id, "uid": uid, "include_outdated": True},
        e2e_api_key_member,
    )
    assert visible.success is True, visible.message
    assert [row["uid"] for row in visible.data["documents"]] == [uid]
    assert visible.data["count"] == 1


def test_update_changes_content_and_reports_version_conflict(
    e2e_workspace, e2e_api_key_member
) -> None:
    workspace_id = str(e2e_workspace.id)
    created = _create(e2e_api_key_member, workspace_id)
    document_id = created.data["document"]["id"]

    updated = _dispatch(
        "document.update",
        {
            "id": document_id,
            "title": "Renamed",
            "expected_version": 1,
            "change_reason": "rename",
        },
        e2e_api_key_member,
    )
    assert updated.success is True, updated.message
    assert updated.data["document"]["title"] == "Renamed"
    assert updated.data["document"]["version"] == 2

    stale = _dispatch(
        "document.update",
        {"id": document_id, "title": "Too late", "expected_version": 1},
        e2e_api_key_member,
    )
    assert stale.success is False
    assert stale.error_code == "CONFLICT"


def test_update_rejects_status_and_unknown_id(
    e2e_workspace, e2e_api_key_member
) -> None:
    workspace_id = str(e2e_workspace.id)
    created = _create(e2e_api_key_member, workspace_id)
    document_id = created.data["document"]["id"]

    status_write = _dispatch(
        "document.update",
        {"id": document_id, "status": RELEASE_STATE},
        e2e_api_key_member,
    )
    assert status_write.success is False
    assert status_write.error_code == "VALIDATION_ERROR"

    missing = _dispatch(
        "document.read",
        {"id": "00000000-0000-0000-0000-000000000000"},
        e2e_api_key_member,
    )
    assert missing.success is False
    assert missing.error_code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Workflow: freeze (F-3), gates (G-4), re-open (F-5)
# ---------------------------------------------------------------------------


def test_transition_release_freezes_content_fields(
    e2e_workspace, e2e_api_key_admin
) -> None:
    workspace_id = str(e2e_workspace.id)
    created = _create(e2e_api_key_admin, workspace_id)
    document_id = created.data["document"]["id"]

    review = _transition(
        e2e_api_key_admin, document_id, REVIEW_STATE, change_reason="ready"
    )
    assert review.success is True, review.message
    assert review.data["new_state"] == REVIEW_STATE

    released = _transition(
        e2e_api_key_admin, document_id, RELEASE_STATE, change_reason="approved"
    )
    assert released.success is True, released.message
    assert released.data["document"]["status"] == RELEASE_STATE
    # Issue #2024: the transition response must report the bumped version.
    assert released.data["document"]["version"] == 2
    assert released.data["version"] == 2
    assert released.data["document"]["frozen_fields"] == [
        "title",
        "description",
        "body",
        "kind",
    ]
    assert released.data["document"]["frozen_at"] is not None

    frozen = _dispatch(
        "document.update",
        {"id": document_id, "title": "Edited while frozen"},
        e2e_api_key_admin,
    )
    assert frozen.success is False
    assert frozen.error_code == "FIELD_FROZEN"

    # F-2: doc_date and custom_fields stay writable while frozen.
    allowed = _dispatch(
        "document.update",
        {
            "id": document_id,
            "doc_date": "2026-11-02",
            "custom_fields": {"note": "still writable"},
        },
        e2e_api_key_admin,
    )
    assert allowed.success is True, allowed.message
    assert allowed.data["document"]["doc_date"] == "2026-11-02"


def test_release_gate_failure_uses_the_rest_error_code(
    e2e_workspace, e2e_api_key_admin
) -> None:
    # The extended preset requires a `body` for every kind (G-4).
    created = _create(e2e_api_key_admin, str(e2e_workspace.id), body="")
    document_id = created.data["document"]["id"]
    assert _transition(
        e2e_api_key_admin, document_id, REVIEW_STATE, change_reason="ready"
    ).success

    refused = _transition(
        e2e_api_key_admin, document_id, RELEASE_STATE, change_reason="approved"
    )
    assert refused.success is False
    assert refused.error_code == "DOCUMENT_GATE_FAILED"


def test_reopen_lifts_the_freeze_and_bumps_the_version(
    e2e_workspace, e2e_api_key_admin
) -> None:
    created = _create(e2e_api_key_admin, str(e2e_workspace.id))
    document_id = created.data["document"]["id"]
    assert _transition(
        e2e_api_key_admin, document_id, REVIEW_STATE, change_reason="ready"
    ).success
    released = _transition(
        e2e_api_key_admin, document_id, RELEASE_STATE, change_reason="approved"
    )
    assert released.success is True, released.message
    # Issue #2024: creation=1, release=2, re-open=3.
    assert released.data["document"]["version"] == 2

    reopened = _transition(
        e2e_api_key_admin, document_id, REVIEW_STATE, change_reason="rework"
    )
    assert reopened.success is True, reopened.message
    assert reopened.data["document"]["frozen_at"] is None
    assert reopened.data["document"]["version"] == 3


# ---------------------------------------------------------------------------
# Versions / diff
# ---------------------------------------------------------------------------


def test_versions_and_diff_read_the_revision_store(
    e2e_workspace, e2e_api_key_member
) -> None:
    created = _create(e2e_api_key_member, str(e2e_workspace.id))
    document_id = created.data["document"]["id"]
    assert _dispatch(
        "document.update",
        {"id": document_id, "title": "Renamed"},
        e2e_api_key_member,
    ).success

    versions = _dispatch(
        "document.versions", {"id": document_id}, e2e_api_key_member
    )
    assert versions.success is True, versions.message
    assert versions.data["count"] == len(versions.data["versions"])
    assert versions.data["count"] >= 2

    diff = _dispatch(
        "document.diff",
        {"id": document_id, "from_version": 1, "to_version": 2},
        e2e_api_key_member,
    )
    assert diff.success is True, diff.message
    assert "Renamed" in str(diff.data["diff"])


def test_diff_reports_custom_fields_and_omits_unchanged_entries(
    e2e_workspace, e2e_api_key_member
) -> None:
    """Issue #2026: ``document.diff`` must be a delta that includes the
    backing Artifact's custom_fields, not a full field dump of "unchanged"
    entries with custom_fields missing."""
    created = _create(
        e2e_api_key_member,
        str(e2e_workspace.id),
        custom_fields={"reviewer": "team-a"},
    )
    assert created.success is True, created.message
    document_id = created.data["document"]["id"]

    updated = _dispatch(
        "document.update",
        {"id": document_id, "custom_fields": {"reviewer": "team-b"}},
        e2e_api_key_member,
    )
    assert updated.success is True, updated.message

    diff = _dispatch(
        "document.diff",
        {"id": document_id, "from_version": 1, "to_version": 2},
        e2e_api_key_member,
    )
    assert diff.success is True, diff.message
    fields = diff.data["diff"]["fields"]
    assert all(field["status"] != "unchanged" for field in fields)
    custom_fields = next(field for field in fields if field["name"] == "custom_fields")
    assert custom_fields["status"] == "modified"
    assert custom_fields["from"] == {"reviewer": "team-a"}
    assert custom_fields["to"] == {"reviewer": "team-b"}


# ---------------------------------------------------------------------------
# Soft delete (G1.5)
# ---------------------------------------------------------------------------


def test_outdate_hides_the_document_and_reactivate_restores_it(
    e2e_workspace, e2e_api_key_member
) -> None:
    workspace_id = str(e2e_workspace.id)
    created = _create(e2e_api_key_member, workspace_id)
    document_id = created.data["document"]["id"]

    deleted = _dispatch(
        "document.outdate",
        {"id": document_id, "reason": "no longer needed"},
        e2e_api_key_member,
    )
    assert deleted.success is True, deleted.message
    assert deleted.data["status"] == "outdated"

    hidden = _dispatch(
        "document.query", {"workspace_id": workspace_id}, e2e_api_key_member
    )
    assert document_id not in {row["id"] for row in hidden.data["documents"]}

    visible = _dispatch(
        "document.query",
        {"workspace_id": workspace_id, "include_outdated": True},
        e2e_api_key_member,
    )
    assert document_id in {row["id"] for row in visible.data["documents"]}

    restored = _dispatch(
        "document.reactivate", {"id": document_id}, e2e_api_key_member
    )
    assert restored.success is True, restored.message
    assert restored.data["new_state"] != "outdated"


# ---------------------------------------------------------------------------
# RBAC + workspace fence
# ---------------------------------------------------------------------------


def test_viewer_can_read_but_not_write(
    e2e_workspace, e2e_api_key_member, e2e_api_key_viewer
) -> None:
    created = _create(e2e_api_key_member, str(e2e_workspace.id))
    document_id = created.data["document"]["id"]

    read = _dispatch("document.read", {"id": document_id}, e2e_api_key_viewer)
    assert read.success is True, read.message

    denied = _dispatch(
        "document.update",
        {"id": document_id, "title": "viewer write"},
        e2e_api_key_viewer,
    )
    assert denied.success is False
    assert denied.error_code == "PERMISSION_DENIED"


def test_read_and_write_tools_resolve_the_owning_workspace(
    e2e_workspace, e2e_api_key_member
) -> None:
    created = _create(e2e_api_key_member, str(e2e_workspace.id))
    document_id = created.data["document"]["id"]

    # The lookup is tenant-scoped; the dispatcher arms the context before it.
    set_request_tenant(e2e_workspace.tenant_id)
    try:
        for tool in ("document.read", "document.versions", "document.diff"):
            assert resolve_target_workspace_id(tool, {"id": document_id}) == str(
                e2e_workspace.id
            )
        for tool in ("document.update", "document.transition", "document.outdate"):
            assert resolve_target_workspace_id(tool, {"id": document_id}) == str(
                e2e_workspace.id
            )
    finally:
        clear_request_tenant()
