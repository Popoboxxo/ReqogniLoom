"""
Tests for ArtifactDiffService diagram/glossary version+diff helpers (REQ-142).

req_id: REQ-142 — real per-version diff/versions endpoints for Diagram and
        GlossaryTerm, backed by the actual immutable version tables
        (DiagramVersion, GlossaryTermVersion) rather than the single-row
        "current state only" fallback used for Requirement/ArchitectureElement/etc.

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
from datetime import datetime, timezone
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


def _make_diagram_version(
    version_number: int,
    payload: str = "graph TD;\nA-->B",
    payload_format: str = "mermaid",
    canvas_json=None,
) -> MagicMock:
    v = MagicMock()
    v.version_number = version_number
    v.payload = payload
    v.payload_format = payload_format
    v.canvas_json = canvas_json
    v.created_at = datetime(2026, 1, version_number, tzinfo=timezone.utc)
    return v


def _make_term_version(
    term_version: int,
    definition: str = "A stated need.",
    synonyms=None,
    abbreviation: str = "REQ",
) -> MagicMock:
    v = MagicMock()
    v.term_version = term_version
    v.definition = definition
    v.synonyms = synonyms or []
    v.abbreviation = abbreviation
    v.created_at = datetime(2026, 1, term_version, tzinfo=timezone.utc)
    return v


# ---------------------------------------------------------------------------
# list_versions_for_diagram
# ---------------------------------------------------------------------------


class TestListVersionsForDiagram:
    """REQ-142: DiagramVersion listing must be chronological (version_number asc)."""

    def test_returns_versions_chronologically(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        v1 = _make_diagram_version(1, payload="A")
        v2 = _make_diagram_version(2, payload="B")

        with patch.object(svc, "_set_tenant_context"):
            with patch("diagram.models.Diagram.objects") as diagram_objects:
                diagram_objects.filter.return_value.exists.return_value = True
                with patch("diagram.models.DiagramVersion.objects") as version_objects:
                    version_objects.filter.return_value.order_by.return_value = [v1, v2]
                    result = svc.list_versions_for_diagram(DIAGRAM_ID, ctx)

        assert [r["version"] for r in result] == [1, 2]
        assert result[0]["label"] == "v1"
        version_objects.filter.return_value.order_by.assert_called_once_with(
            "version_number"
        )

    def test_unknown_diagram_raises_not_found(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        with patch.object(svc, "_set_tenant_context"):
            with patch("diagram.models.Diagram.objects") as diagram_objects:
                diagram_objects.filter.return_value.exists.return_value = False
                with pytest.raises(NotFoundError):
                    svc.list_versions_for_diagram(DIAGRAM_ID, ctx)


# ---------------------------------------------------------------------------
# diff_for_diagram
# ---------------------------------------------------------------------------


class TestDiffForDiagram:
    """REQ-142: field-level diff between two real DiagramVersion snapshots."""

    def test_diff_detects_payload_change(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        v1 = _make_diagram_version(1, payload="graph TD;\nA-->B")
        v2 = _make_diagram_version(2, payload="graph TD;\nA-->C")

        def _filter_side_effect(**kwargs):
            m = MagicMock()
            m.first.return_value = v1 if kwargs.get("version_number") == 1 else v2
            return m

        with patch.object(svc, "_set_tenant_context"):
            with patch("diagram.models.Diagram.objects") as diagram_objects:
                diagram_objects.filter.return_value.exists.return_value = True
                with patch("diagram.models.DiagramVersion.objects") as version_objects:
                    version_objects.filter.side_effect = _filter_side_effect
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

        v1 = _make_diagram_version(1)

        with patch.object(svc, "_set_tenant_context"):
            with patch("diagram.models.Diagram.objects") as diagram_objects:
                diagram_objects.filter.return_value.exists.return_value = True
                with patch("diagram.models.DiagramVersion.objects") as version_objects:
                    version_objects.filter.return_value.first.return_value = v1
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
                diagram_objects.filter.return_value.exists.return_value = True
                with patch("diagram.models.DiagramVersion.objects") as version_objects:
                    version_objects.filter.return_value.first.return_value = None
                    with pytest.raises(NotFoundError, match="99"):
                        svc.diff_for_diagram(
                            DIAGRAM_ID, from_version=0, to_version=99, ctx=ctx
                        )

    def test_unknown_diagram_raises_not_found(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        with patch.object(svc, "_set_tenant_context"):
            with patch("diagram.models.Diagram.objects") as diagram_objects:
                diagram_objects.filter.return_value.exists.return_value = False
                with pytest.raises(NotFoundError):
                    svc.diff_for_diagram(
                        DIAGRAM_ID, from_version=0, to_version=1, ctx=ctx
                    )


# ---------------------------------------------------------------------------
# list_versions_for_glossary_term
# ---------------------------------------------------------------------------


class TestListVersionsForGlossaryTerm:
    """REQ-142: GlossaryTermVersion listing must be chronological (term_version asc)."""

    def test_returns_versions_chronologically(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        t1 = _make_term_version(1, definition="Old def")
        t2 = _make_term_version(2, definition="New def")

        with patch.object(svc, "_set_tenant_context"):
            with patch(
                "application.artifact_diff_service.GlossaryTerm.objects"
            ) as term_objects:
                term_objects.filter.return_value.exists.return_value = True
                with patch(
                    "persistence.models.GlossaryTermVersion.objects"
                ) as version_objects:
                    version_objects.filter.return_value.order_by.return_value = [
                        t1,
                        t2,
                    ]
                    result = svc.list_versions_for_glossary_term(TERM_ID, ctx)

        assert [r["version"] for r in result] == [1, 2]
        version_objects.filter.return_value.order_by.assert_called_once_with(
            "term_version"
        )

    def test_unknown_term_raises_not_found(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        with patch.object(svc, "_set_tenant_context"):
            with patch(
                "application.artifact_diff_service.GlossaryTerm.objects"
            ) as term_objects:
                term_objects.filter.return_value.exists.return_value = False
                with pytest.raises(NotFoundError):
                    svc.list_versions_for_glossary_term(TERM_ID, ctx)


# ---------------------------------------------------------------------------
# diff_for_glossary_term
# ---------------------------------------------------------------------------


class TestDiffForGlossaryTerm:
    """REQ-142: field-level diff between two real GlossaryTermVersion snapshots."""

    def test_diff_detects_definition_change(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        term_mock = MagicMock()
        term_mock.id = TERM_ID
        term_mock.term = "Requirement"

        t1 = _make_term_version(1, definition="Old def", abbreviation="REQ")
        t2 = _make_term_version(2, definition="New def", abbreviation="REQ")

        def _filter_side_effect(**kwargs):
            m = MagicMock()
            m.first.return_value = t1 if kwargs.get("term_version") == 1 else t2
            return m

        with patch.object(svc, "_set_tenant_context"):
            with patch(
                "application.artifact_diff_service.GlossaryTerm.objects"
            ) as term_objects:
                term_objects.filter.return_value.first.return_value = term_mock
                with patch(
                    "persistence.models.GlossaryTermVersion.objects"
                ) as version_objects:
                    version_objects.filter.side_effect = _filter_side_effect
                    result = svc.diff_for_glossary_term(
                        TERM_ID, from_version=1, to_version=2, ctx=ctx
                    )

        assert result["entity_type"] == "GlossaryTerm"
        field_statuses = {f["name"]: f["status"] for f in result["fields"]}
        assert field_statuses["definition"] == "modified"
        assert field_statuses["abbreviation"] == "unchanged"
        # "term" is immutable — taken from the parent GlossaryTerm for both sides.
        assert field_statuses["term"] == "unchanged"

    def test_unknown_to_version_raises_not_found(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx()

        term_mock = MagicMock()
        term_mock.id = TERM_ID
        term_mock.term = "Requirement"

        with patch.object(svc, "_set_tenant_context"):
            with patch(
                "application.artifact_diff_service.GlossaryTerm.objects"
            ) as term_objects:
                term_objects.filter.return_value.first.return_value = term_mock
                with patch(
                    "persistence.models.GlossaryTermVersion.objects"
                ) as version_objects:
                    version_objects.filter.return_value.first.return_value = None
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
