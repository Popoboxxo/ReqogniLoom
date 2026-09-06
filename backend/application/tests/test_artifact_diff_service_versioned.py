"""
Tests for ArtifactDiffService's generic list_versions/diff against types that
record a real snapshot per content revision (REQ-142).

req_id: REQ-142 — real per-revision diff/versions for Diagram and
        GlossaryTerm, both backed by the generic ArtifactVersion store via
        ArtifactVersionService.

Datenmodell-Konsolidierung Task 29 (Milestone M5): the dedicated
``list_versions_for_diagram``/``diff_for_diagram``/
``list_versions_for_glossary_term``/``diff_for_glossary_term`` methods this
file used to test were deleted — ``list_versions``/``diff`` are now the only
two entry points for every artifact type, Diagram and GlossaryTerm included.
This file proves they produce the same shape of output these per-type
variants used to (chronological order, field-level diff, 404 handling).

Covers:
  - list_versions: chronological order for a Diagram-typed artifact,
    404 for unknown artifact
  - diff: field-level diff (payload changed -> modified w/ lines,
    payload_format unchanged), from_version=0 -> all fields "added",
    404 for unknown version
  - list_versions / diff: same guarantees for a GlossaryTerm-typed artifact

These tests mock ``Artifact``/``ArtifactVersionService`` directly (no live
database) — consistent with rest_api/tests/test_diagram_canvas_views.py and
rest_api/tests/test_versioning.py, which avoid a django_db dependency.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.artifact_diff_service import ArtifactDiffService
from application.base import NotFoundError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.tenant_id = uuid.uuid4()
    ctx.user_id = uuid.uuid4()
    return ctx


ARTIFACT_ID = uuid.uuid4()


def _make_artifact(artifact_type: str) -> MagicMock:
    artifact = MagicMock()
    artifact.id = ARTIFACT_ID
    artifact.artifact_type = artifact_type
    return artifact


def _diagram_payload(
    payload: str = "graph TD;\nA-->B",
    payload_format: str = "mermaid",
    canvas_json=None,
) -> dict:
    """One stored ArtifactVersion payload for a Diagram revision."""
    return {
        "payload_format": payload_format,
        "payload": payload,
        "canvas_json": canvas_json,
    }


def _glossary_payload(definition: str = "Old def") -> dict:
    """One stored ArtifactVersion payload for a GlossaryTerm revision."""
    return {
        "term": "Requirement",
        "definition": definition,
        "synonyms": [],
        "abbreviation": "REQ",
    }


# ---------------------------------------------------------------------------
# list_versions — Diagram-typed artifact
# ---------------------------------------------------------------------------


class TestListVersionsForDiagramType:
    """REQ-142/Task 29: listing delegates to ArtifactVersionService.list_revisions."""

    def test_returns_versions_chronologically(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        expected = [
            {"version": 1, "label": "v1", "modified_at": None, "content_available": True},
            {"version": 2, "label": "v2", "modified_at": None, "content_available": True},
        ]

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.exists.return_value = True
                with patch(
                    "application.artifact_diff_service.ArtifactVersionService"
                ) as version_svc_cls:
                    version_svc_cls.return_value.list_revisions.return_value = expected
                    result = svc.list_versions(ARTIFACT_ID, ctx)

        assert [r["version"] for r in result] == [0, 1, 2]
        assert result[0]["label"] == "Creation baseline"
        version_svc_cls.return_value.list_revisions.assert_called_once_with(
            ARTIFACT_ID, ctx
        )

    def test_unknown_artifact_raises_not_found(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.exists.return_value = False
                with pytest.raises(NotFoundError):
                    svc.list_versions(ARTIFACT_ID, ctx)


# ---------------------------------------------------------------------------
# diff — Diagram-typed artifact
# ---------------------------------------------------------------------------


class TestDiffForDiagramType:
    """REQ-142: field-level diff between two recorded Diagram revisions."""

    def test_diff_detects_payload_change(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        payloads = {
            1: _diagram_payload(payload="graph TD;\nA-->B"),
            2: _diagram_payload(payload="graph TD;\nA-->C"),
        }

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.first.return_value = (
                    _make_artifact("Diagram")
                )
                with patch(
                    "application.artifact_diff_service.ArtifactVersionService"
                ) as version_svc_cls:
                    version_svc_cls.return_value.get_payload.side_effect = (
                        lambda _artifact_id, revision, _ctx: payloads.get(revision)
                    )
                    result = svc.diff(
                        ARTIFACT_ID, from_version=1, to_version=2, ctx=ctx
                    )

        assert result["entity_type"] == "Diagram"
        field_statuses = {f["name"]: f["status"] for f in result["fields"]}
        assert field_statuses["payload"] == "modified"
        assert field_statuses["payload_format"] == "unchanged"

        payload_field = next(f for f in result["fields"] if f["name"] == "payload")
        assert "lines" in payload_field  # payload is a _TEXT_FIELDS entry

    def test_from_version_zero_all_fields_added(self):
        """from_version=0 (empty baseline) -> every field is 'added'."""
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.first.return_value = (
                    _make_artifact("Diagram")
                )
                with patch(
                    "application.artifact_diff_service.ArtifactVersionService"
                ) as version_svc_cls:
                    version_svc_cls.return_value.get_payload.return_value = (
                        _diagram_payload()
                    )
                    result = svc.diff(
                        ARTIFACT_ID, from_version=0, to_version=1, ctx=ctx
                    )

        field_statuses = {f["name"]: f["status"] for f in result["fields"]}
        assert field_statuses["payload"] == "added"
        assert field_statuses["payload_format"] == "added"

    def test_unknown_to_version_raises_not_found(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.first.return_value = (
                    _make_artifact("Diagram")
                )
                with patch(
                    "application.artifact_diff_service.ArtifactVersionService"
                ) as version_svc_cls:
                    version_svc_cls.return_value.get_payload.return_value = None
                    with pytest.raises(NotFoundError, match="99"):
                        svc.diff(
                            ARTIFACT_ID, from_version=0, to_version=99, ctx=ctx
                        )

    def test_unknown_artifact_raises_not_found(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.first.return_value = None
                with pytest.raises(NotFoundError):
                    svc.diff(ARTIFACT_ID, from_version=0, to_version=1, ctx=ctx)


# ---------------------------------------------------------------------------
# list_versions / diff — GlossaryTerm-typed artifact
# ---------------------------------------------------------------------------


class TestListVersionsForGlossaryTermType:
    """REQ-142/Task 29: listing delegates to ArtifactVersionService.list_revisions."""

    def test_returns_versions_chronologically(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        expected = [
            {"version": 1, "label": "v1", "modified_at": None, "content_available": True},
            {"version": 2, "label": "v2", "modified_at": None, "content_available": True},
        ]

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.exists.return_value = True
                with patch(
                    "application.artifact_diff_service.ArtifactVersionService"
                ) as version_svc_cls:
                    version_svc_cls.return_value.list_revisions.return_value = expected
                    result = svc.list_versions(ARTIFACT_ID, ctx)

        assert [r["version"] for r in result] == [0, 1, 2]
        version_svc_cls.return_value.list_revisions.assert_called_once_with(
            ARTIFACT_ID, ctx
        )


class TestDiffForGlossaryTermType:
    """REQ-142/Task 29: field-level diff via ArtifactVersionService.get_payload."""

    def test_diff_detects_definition_change(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        payload_v1 = _glossary_payload("Old def")
        payload_v2 = _glossary_payload("New def")

        def _get_payload_side_effect(artifact_id, revision, ctx):
            return payload_v1 if revision == 1 else payload_v2

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.first.return_value = (
                    _make_artifact("GlossaryTerm")
                )
                with patch(
                    "application.artifact_diff_service.ArtifactVersionService"
                ) as version_svc_cls:
                    version_svc_cls.return_value.get_payload.side_effect = (
                        _get_payload_side_effect
                    )
                    result = svc.diff(
                        ARTIFACT_ID, from_version=1, to_version=2, ctx=ctx
                    )

        assert result["entity_type"] == "GlossaryTerm"
        field_statuses = {f["name"]: f["status"] for f in result["fields"]}
        assert field_statuses["definition"] == "modified"
        assert field_statuses["abbreviation"] == "unchanged"
        assert field_statuses["term"] == "unchanged"

    def test_unknown_to_version_raises_not_found(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.first.return_value = (
                    _make_artifact("GlossaryTerm")
                )
                with patch(
                    "application.artifact_diff_service.ArtifactVersionService"
                ) as version_svc_cls:
                    version_svc_cls.return_value.get_payload.return_value = None
                    with pytest.raises(NotFoundError, match="99"):
                        svc.diff(
                            ARTIFACT_ID, from_version=0, to_version=99, ctx=ctx
                        )
