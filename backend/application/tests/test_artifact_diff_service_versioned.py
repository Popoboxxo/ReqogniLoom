"""
Tests for ArtifactDiffService diagram/glossary version+diff helpers (REQ-142).

req_id: REQ-142 — real per-revision diff/versions endpoints for Diagram and
        GlossaryTerm, both backed by the generic ArtifactVersion store via
        ArtifactVersionService (GlossaryTerm since Task 28b, Diagram since
        Task 28c-2 retired DiagramVersion) rather than the single-row
        "current state only" fallback used for
        Requirement/ArchitectureElement/etc.

Covers:
  - list_versions_for_diagram: chronological order, 404 for unknown diagram
  - diff_for_diagram: field-level diff (payload changed -> modified w/ lines,
    payload_format unchanged), from_version=0 -> all fields "added",
    404 for unknown version / unknown diagram
  - list_versions_for_glossary_term: chronological order, 404 for unknown term
  - diff_for_glossary_term: field-level diff (definition changed),
    404 for unknown version / unknown term

These tests mock the ORM managers directly (no live database) — consistent
with rest_api/tests/test_diagram_canvas_views.py and
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


DIAGRAM_ID = uuid.uuid4()
TERM_ID = uuid.uuid4()


def _make_diagram(artifact_id=None) -> MagicMock:
    """A Diagram row stub carrying the backing Artifact id the helpers read."""
    diagram = MagicMock()
    diagram.artifact_id = artifact_id if artifact_id is not None else uuid.uuid4()
    return diagram


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


# ---------------------------------------------------------------------------
# list_versions_for_diagram
# ---------------------------------------------------------------------------


class TestListVersionsForDiagram:
    """REQ-142/Task 28c-2: listing delegates to ArtifactVersionService.list_revisions."""

    def test_returns_versions_chronologically(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        diagram = _make_diagram()
        expected = [
            {"version": 1, "label": "v1", "modified_at": None, "content_available": True},
            {"version": 2, "label": "v2", "modified_at": None, "content_available": True},
        ]

        with patch.object(svc, "_set_tenant_context"):
            with patch("diagram.models.Diagram.objects") as diagram_objects:
                diagram_objects.filter.return_value.first.return_value = diagram
                with patch(
                    "application.artifact_diff_service.ArtifactVersionService"
                ) as version_svc_cls:
                    version_svc_cls.return_value.list_revisions.return_value = expected
                    result = svc.list_versions_for_diagram(DIAGRAM_ID, ctx)

        assert [r["version"] for r in result] == [1, 2]
        assert result[0]["label"] == "v1"
        version_svc_cls.return_value.list_revisions.assert_called_once_with(
            diagram.artifact_id, ctx
        )

    def test_workspaceless_diagram_has_no_recorded_history(self):
        """Task 28c-2: no backing Artifact -> nothing to hang revisions off.

        Artifact.workspace is not nullable, so a workspace-less legacy Diagram
        can never have had an ArtifactVersion row (diagram.manager has skipped
        those since Task 27). An empty list is the honest answer.
        """
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        diagram = MagicMock()
        diagram.artifact_id = None

        with patch.object(svc, "_set_tenant_context"):
            with patch("diagram.models.Diagram.objects") as diagram_objects:
                diagram_objects.filter.return_value.first.return_value = diagram
                assert svc.list_versions_for_diagram(DIAGRAM_ID, ctx) == []

    def test_unknown_diagram_raises_not_found(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        with patch.object(svc, "_set_tenant_context"):
            with patch("diagram.models.Diagram.objects") as diagram_objects:
                diagram_objects.filter.return_value.first.return_value = None
                with pytest.raises(NotFoundError):
                    svc.list_versions_for_diagram(DIAGRAM_ID, ctx)


# ---------------------------------------------------------------------------
# diff_for_diagram
# ---------------------------------------------------------------------------


class TestDiffForDiagram:
    """REQ-142: field-level diff between two recorded Diagram revisions."""

    def test_diff_detects_payload_change(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        payloads = {
            1: _diagram_payload(payload="graph TD;\nA-->B"),
            2: _diagram_payload(payload="graph TD;\nA-->C"),
        }

        with patch.object(svc, "_set_tenant_context"):
            with patch("diagram.models.Diagram.objects") as diagram_objects:
                diagram_objects.filter.return_value.first.return_value = _make_diagram()
                with patch(
                    "application.artifact_diff_service.ArtifactVersionService"
                ) as version_svc_cls:
                    version_svc_cls.return_value.get_payload.side_effect = (
                        lambda _artifact_id, revision, _ctx: payloads.get(revision)
                    )
                    result = svc.diff_for_diagram(
                        DIAGRAM_ID, from_version=1, to_version=2, ctx=ctx
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
            with patch("diagram.models.Diagram.objects") as diagram_objects:
                diagram_objects.filter.return_value.first.return_value = _make_diagram()
                with patch(
                    "application.artifact_diff_service.ArtifactVersionService"
                ) as version_svc_cls:
                    version_svc_cls.return_value.get_payload.return_value = (
                        _diagram_payload()
                    )
                    result = svc.diff_for_diagram(
                        DIAGRAM_ID, from_version=0, to_version=1, ctx=ctx
                    )

        field_statuses = {f["name"]: f["status"] for f in result["fields"]}
        assert field_statuses["payload"] == "added"
        assert field_statuses["payload_format"] == "added"

    def test_unknown_to_version_raises_not_found(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        with patch.object(svc, "_set_tenant_context"):
            with patch("diagram.models.Diagram.objects") as diagram_objects:
                diagram_objects.filter.return_value.first.return_value = _make_diagram()
                with patch(
                    "application.artifact_diff_service.ArtifactVersionService"
                ) as version_svc_cls:
                    version_svc_cls.return_value.get_payload.return_value = None
                    with pytest.raises(NotFoundError, match="99"):
                        svc.diff_for_diagram(
                            DIAGRAM_ID, from_version=0, to_version=99, ctx=ctx
                        )

    def test_unknown_diagram_raises_not_found(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        with patch.object(svc, "_set_tenant_context"):
            with patch("diagram.models.Diagram.objects") as diagram_objects:
                diagram_objects.filter.return_value.first.return_value = None
                with pytest.raises(NotFoundError):
                    svc.diff_for_diagram(
                        DIAGRAM_ID, from_version=0, to_version=1, ctx=ctx
                    )


# ---------------------------------------------------------------------------
# list_versions_for_glossary_term
# ---------------------------------------------------------------------------


class TestListVersionsForGlossaryTerm:
    """REQ-142/Task 28b: listing delegates to ArtifactVersionService.list_revisions."""

    def test_returns_versions_chronologically(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        term_mock = MagicMock()
        term_mock.artifact_id = uuid.uuid4()
        expected = [
            {"version": 1, "label": "v1", "modified_at": None, "content_available": True},
            {"version": 2, "label": "v2", "modified_at": None, "content_available": True},
        ]

        with patch.object(svc, "_set_tenant_context"):
            with patch(
                "application.artifact_diff_service.GlossaryTerm.objects"
            ) as term_objects:
                term_objects.filter.return_value.first.return_value = term_mock
                with patch(
                    "application.artifact_diff_service.ArtifactVersionService"
                ) as version_svc_cls:
                    version_svc_cls.return_value.list_revisions.return_value = expected
                    result = svc.list_versions_for_glossary_term(TERM_ID, ctx)

        assert [r["version"] for r in result] == [1, 2]
        version_svc_cls.return_value.list_revisions.assert_called_once_with(
            term_mock.artifact_id, ctx
        )

    def test_unknown_term_raises_not_found(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        with patch.object(svc, "_set_tenant_context"):
            with patch(
                "application.artifact_diff_service.GlossaryTerm.objects"
            ) as term_objects:
                term_objects.filter.return_value.first.return_value = None
                with pytest.raises(NotFoundError):
                    svc.list_versions_for_glossary_term(TERM_ID, ctx)


# ---------------------------------------------------------------------------
# diff_for_glossary_term
# ---------------------------------------------------------------------------


class TestDiffForGlossaryTerm:
    """REQ-142/Task 28b: field-level diff via ArtifactVersionService.get_payload."""

    def test_diff_detects_definition_change(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        term_mock = MagicMock()
        term_mock.id = TERM_ID
        term_mock.term = "Requirement"
        term_mock.artifact_id = uuid.uuid4()

        payload_v1 = {
            "term": "Requirement",
            "definition": "Old def",
            "synonyms": [],
            "abbreviation": "REQ",
        }
        payload_v2 = {
            "term": "Requirement",
            "definition": "New def",
            "synonyms": [],
            "abbreviation": "REQ",
        }

        def _get_payload_side_effect(artifact_id, revision, ctx):
            return payload_v1 if revision == 1 else payload_v2

        with patch.object(svc, "_set_tenant_context"):
            with patch(
                "application.artifact_diff_service.GlossaryTerm.objects"
            ) as term_objects:
                term_objects.filter.return_value.first.return_value = term_mock
                with patch(
                    "application.artifact_diff_service.ArtifactVersionService"
                ) as version_svc_cls:
                    version_svc_cls.return_value.get_payload.side_effect = (
                        _get_payload_side_effect
                    )
                    result = svc.diff_for_glossary_term(
                        TERM_ID, from_version=1, to_version=2, ctx=ctx
                    )

        assert result["entity_type"] == "GlossaryTerm"
        field_statuses = {f["name"]: f["status"] for f in result["fields"]}
        assert field_statuses["definition"] == "modified"
        assert field_statuses["abbreviation"] == "unchanged"
        assert field_statuses["term"] == "unchanged"

    def test_unknown_to_version_raises_not_found(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        term_mock = MagicMock()
        term_mock.id = TERM_ID
        term_mock.term = "Requirement"
        term_mock.artifact_id = uuid.uuid4()

        with patch.object(svc, "_set_tenant_context"):
            with patch(
                "application.artifact_diff_service.GlossaryTerm.objects"
            ) as term_objects:
                term_objects.filter.return_value.first.return_value = term_mock
                with patch(
                    "application.artifact_diff_service.ArtifactVersionService"
                ) as version_svc_cls:
                    version_svc_cls.return_value.get_payload.return_value = None
                    with pytest.raises(NotFoundError, match="99"):
                        svc.diff_for_glossary_term(
                            TERM_ID, from_version=0, to_version=99, ctx=ctx
                        )

    def test_unknown_term_raises_not_found(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        with patch.object(svc, "_set_tenant_context"):
            with patch(
                "application.artifact_diff_service.GlossaryTerm.objects"
            ) as term_objects:
                term_objects.filter.return_value.first.return_value = None
                with pytest.raises(NotFoundError):
                    svc.diff_for_glossary_term(
                        TERM_ID, from_version=0, to_version=1, ctx=ctx
                    )
