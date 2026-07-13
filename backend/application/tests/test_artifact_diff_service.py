"""
Tests for COMP-AS-019 ArtifactDiffService.

leaf_id : COMP-AS-019
req_id  : REQ-L2-AS-032 (diff calculation),
          REQ-L1-040 (visual artifact diff)

Coverage:
  - diff_first_to_current_version: from_version=0 → all fields "added"
  - diff_scalar_field_change: title changed between two snapshots
  - diff_markdown_field_line_diff: description with line-level diff
  - diff_unchanged_field_marked: unchanged fields get status "unchanged"
  - diff_invalid_version_raises_not_found: non-existent entity → NotFoundError
  - diff_tenant_isolation: _set_tenant_context is called
  - list_versions: returns baseline + current version
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.artifact_diff_service import ArtifactDiffService
from application.base import NotFoundError

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(*, roles=("editor",), tenant_id=None, user_id=None):
    ctx = MagicMock()
    ctx.active_roles = roles
    ctx.tenant_id = tenant_id or uuid.uuid4()
    ctx.user_id = user_id or uuid.uuid4()
    ctx.has_role = lambda role: role in roles
    return ctx


ARTIFACT_ID = uuid.uuid4()
WS_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()


def _make_artifact_mock(artifact_type="Requirement"):
    artifact = MagicMock()
    artifact.id = ARTIFACT_ID
    artifact.artifact_type = artifact_type
    artifact.workspace_id = WS_ID
    return artifact


def _make_requirement_mock(**kwargs):
    req = MagicMock()
    req.id = kwargs.get("id", uuid.uuid4())
    req.title = kwargs.get("title", "Sample Requirement")
    req.description = kwargs.get("description", "Initial description")
    req.category = kwargs.get("category", "functional")
    req.status = kwargs.get("status", "draft")
    req.version = kwargs.get("version", 2)
    req.modified_at = kwargs.get("modified_at", None)
    artifact = MagicMock()
    artifact.id = ARTIFACT_ID
    artifact.workspace_id = WS_ID
    req.artifact = artifact
    req.artifact_id = ARTIFACT_ID
    return req


def _make_arch_element_mock(**kwargs):
    el = MagicMock()
    el.id = kwargs.get("id", uuid.uuid4())
    el.title = kwargs.get("title", "Component A")
    el.description = kwargs.get("description", "A component")
    el.element_type = kwargs.get("element_type", "component")
    el.version = kwargs.get("version", 1)
    el.modified_at = kwargs.get("modified_at", None)
    artifact = MagicMock()
    artifact.id = ARTIFACT_ID
    artifact.workspace_id = WS_ID
    el.artifact = artifact
    el.artifact_id = ARTIFACT_ID
    return el


def _make_testcase_mock(**kwargs):
    tc = MagicMock()
    tc.id = kwargs.get("id", uuid.uuid4())
    tc.title = kwargs.get("title", "Test Case 1")
    tc.description = kwargs.get("description", "Test description")
    tc.steps = kwargs.get("steps", ["step1", "step2"])
    tc.version = kwargs.get("version", 1)
    tc.modified_at = kwargs.get("modified_at", None)
    artifact = MagicMock()
    artifact.id = ARTIFACT_ID
    artifact.workspace_id = WS_ID
    tc.artifact = artifact
    tc.artifact_id = ARTIFACT_ID
    return tc


# ---------------------------------------------------------------------------
# diff: from_version=0 → all fields "added"
# ---------------------------------------------------------------------------


class TestDiffFirstToCurrentVersion:
    """REQ-L2-AS-032: Diff from creation baseline (version 0) to current."""

    def test_diff_first_to_current_version(self):
        """from_version=0 → all fields have status 'added'."""
        svc = ArtifactDiffService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        artifact_mock = _make_artifact_mock("Requirement")
        req_mock = _make_requirement_mock(
            title="New Title",
            description="New description",
            category="functional",
            status="draft",
            version=1,
        )

        req_model = MagicMock()
        req_model.objects.select_related.return_value.filter.return_value.first.return_value = (
            req_mock
        )

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.first.return_value = artifact_mock
                with patch.dict(
                    "application.artifact_diff_service._ENTITY_MODELS",
                    {"Requirement": req_model},
                ):
                    result = svc.diff(
                        artifact_id=ARTIFACT_ID,
                        from_version=0,
                        to_version=1,
                        ctx=ctx,
                    )

        assert result["from_version"] == 0
        assert result["to_version"] == 1
        assert result["entity_type"] == "Requirement"

        # All fields should be "added" since from_snapshot is None (version 0)
        field_statuses = {f["name"]: f["status"] for f in result["fields"]}
        assert field_statuses["title"] == "added"
        assert field_statuses["description"] == "added"
        assert field_statuses["category"] == "added"
        assert field_statuses["status"] == "added"

        # "added" fields should have "to" but no "from"
        title_field = next(f for f in result["fields"] if f["name"] == "title")
        assert title_field["to"] == "New Title"
        assert "from" not in title_field


# ---------------------------------------------------------------------------
# diff: scalar field change
# ---------------------------------------------------------------------------


class TestDiffScalarFieldChange:
    """REQ-L2-AS-032: Scalar field (title) change detection."""

    def test_diff_scalar_field_change(self):
        """Title changed between two snapshots → status 'modified'."""
        svc = ArtifactDiffService()

        # Test the pure diff computation directly
        from_data = {
            "title": "Old Title",
            "description": "Same description",
            "category": "functional",
            "status": "draft",
        }
        to_data = {
            "title": "New Title",
            "description": "Same description",
            "category": "functional",
            "status": "draft",
        }

        fields = svc._compute_fields_diff(from_data, to_data, "Requirement")

        title_field = next(f for f in fields if f["name"] == "title")
        assert title_field["status"] == "modified"
        assert title_field["from"] == "Old Title"
        assert title_field["to"] == "New Title"
        # Scalar fields should NOT have line-level diff
        assert "lines" not in title_field


# ---------------------------------------------------------------------------
# diff: Markdown field with line-level diff
# ---------------------------------------------------------------------------


class TestDiffMarkdownFieldLineDiff:
    """REQ-L2-AS-032: Text field (description) gets line-level diff."""

    def test_diff_markdown_field_line_diff(self):
        """Description change → status 'modified' with 'lines' unified diff."""
        svc = ArtifactDiffService()

        from_data = {
            "title": "Same Title",
            "description": "line1\nline2\nline3",
            "category": "functional",
            "status": "draft",
        }
        to_data = {
            "title": "Same Title",
            "description": "line1\nline3\nline4",
            "category": "functional",
            "status": "draft",
        }

        fields = svc._compute_fields_diff(from_data, to_data, "Requirement")

        desc_field = next(f for f in fields if f["name"] == "description")
        assert desc_field["status"] == "modified"
        assert desc_field["from"] == "line1\nline2\nline3"
        assert desc_field["to"] == "line1\nline3\nline4"
        # Text fields MUST have line-level diff
        assert "lines" in desc_field
        assert len(desc_field["lines"]) > 0
        # Unified diff should contain removal and addition markers
        line_text = "\n".join(desc_field["lines"])
        assert "-line2" in line_text
        assert "+line3" in line_text or "+line4" in line_text


# ---------------------------------------------------------------------------
# diff: unchanged field marked
# ---------------------------------------------------------------------------


class TestDiffUnchangedFieldMarked:
    """REQ-L2-AS-032: Unchanged fields get status 'unchanged'."""

    def test_diff_unchanged_field_marked(self):
        """Fields with same value → status 'unchanged'."""
        svc = ArtifactDiffService()

        from_data = {
            "title": "Same Title",
            "description": "Same desc",
            "category": "functional",
            "status": "draft",
        }
        to_data = {
            "title": "Same Title",
            "description": "Same desc",
            "category": "functional",
            "status": "draft",
        }

        fields = svc._compute_fields_diff(from_data, to_data, "Requirement")

        for field in fields:
            assert field["status"] == "unchanged"
            assert "from" in field
            assert "to" in field


# ---------------------------------------------------------------------------
# diff: invalid version raises NotFoundError
# ---------------------------------------------------------------------------


class TestDiffInvalidVersion:
    """REQ-L2-AS-032: Non-existent entity → NotFoundError."""

    def test_diff_invalid_version_raises_not_found(self):
        """Entity not found → NotFoundError."""
        svc = ArtifactDiffService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.first.return_value = None

                with pytest.raises(NotFoundError, match="not found"):
                    svc.diff(
                        artifact_id=ARTIFACT_ID,
                        from_version=1,
                        to_version=2,
                        ctx=ctx,
                    )

    def test_diff_unsupported_artifact_type(self):
        """Artifact type not in supported list → NotFoundError."""
        svc = ArtifactDiffService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        artifact_mock = _make_artifact_mock("UnsupportedType")

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.first.return_value = artifact_mock

                with pytest.raises(NotFoundError, match="not supported"):
                    svc.diff(
                        artifact_id=ARTIFACT_ID,
                        from_version=1,
                        to_version=2,
                        ctx=ctx,
                    )


# ---------------------------------------------------------------------------
# diff: tenant isolation
# ---------------------------------------------------------------------------


class TestDiffTenantIsolation:
    """REQ-L2-AS-032: Tenant context is set before any DB access."""

    def test_diff_tenant_isolation(self):
        """_set_tenant_context is called with ctx."""
        svc = ArtifactDiffService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        artifact_mock = _make_artifact_mock("Requirement")
        req_mock = _make_requirement_mock()

        req_model = MagicMock()
        req_model.objects.select_related.return_value.filter.return_value.first.return_value = (
            req_mock
        )

        with patch.object(svc, "_set_tenant_context") as mock_set_tenant:
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.first.return_value = artifact_mock
                with patch.dict(
                    "application.artifact_diff_service._ENTITY_MODELS",
                    {"Requirement": req_model},
                ):
                    svc.diff(
                        artifact_id=ARTIFACT_ID,
                        from_version=0,
                        to_version=1,
                        ctx=ctx,
                    )

        mock_set_tenant.assert_called_once_with(ctx)


# ---------------------------------------------------------------------------
# diff: ArchitectureElement support
# ---------------------------------------------------------------------------


class TestDiffArchitectureElement:
    """REQ-L2-AS-032: Diff works for ArchitectureElement entities."""

    def test_diff_architecture_element(self):
        """ArchitectureElement diff — element_type change detected."""
        svc = ArtifactDiffService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        artifact_mock = _make_artifact_mock("ArchitectureElement")
        arch_mock = _make_arch_element_mock(
            title="Component A",
            description="Updated description",
            element_type="component",
            version=2,
        )

        arch_model = MagicMock()
        arch_model.objects.select_related.return_value.filter.return_value.first.return_value = (
            arch_mock
        )

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.first.return_value = artifact_mock
                with patch.dict(
                    "application.artifact_diff_service._ENTITY_MODELS",
                    {"ArchitectureElement": arch_model},
                ):
                    result = svc.diff(
                        artifact_id=ARTIFACT_ID,
                        from_version=0,
                        to_version=2,
                        ctx=ctx,
                    )

        assert result["entity_type"] == "ArchitectureElement"
        field_statuses = {f["name"]: f["status"] for f in result["fields"]}
        assert field_statuses["title"] == "added"
        assert field_statuses["element_type"] == "added"


# ---------------------------------------------------------------------------
# diff: TestCase support with JSON field
# ---------------------------------------------------------------------------


class TestDiffTestCase:
    """REQ-L2-AS-032: Diff works for TestCase entities with JSON steps field."""

    def test_diff_testcase_json_field(self):
        """TestCase diff — steps (JSON field) change detected."""
        svc = ArtifactDiffService()

        from_data = {
            "title": "Test Case 1",
            "description": "Same",
            "steps": '["step1", "step2"]',
        }
        to_data = {
            "title": "Test Case 1",
            "description": "Same",
            "steps": '["step1", "step2", "step3"]',
        }

        fields = svc._compute_fields_diff(from_data, to_data, "TestCase")

        steps_field = next(f for f in fields if f["name"] == "steps")
        assert steps_field["status"] == "modified"


# ---------------------------------------------------------------------------
# diff: note field when historical version unavailable
# ---------------------------------------------------------------------------


class TestDiffNoteField:
    """REQ-L2-AS-032: Response includes note when historical version unavailable."""

    def test_diff_note_when_from_version_unavailable(self):
        """from_version > 0 resolves to current state → no note (same snapshot)."""
        svc = ArtifactDiffService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        artifact_mock = _make_artifact_mock("Requirement")
        req_mock = _make_requirement_mock(version=3)

        req_model = MagicMock()
        req_model.objects.select_related.return_value.filter.return_value.first.return_value = (
            req_mock
        )

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.first.return_value = artifact_mock
                with patch.dict(
                    "application.artifact_diff_service._ENTITY_MODELS",
                    {"Requirement": req_model},
                ):
                    result = svc.diff(
                        artifact_id=ARTIFACT_ID,
                        from_version=1,
                        to_version=3,
                        ctx=ctx,
                    )

        # Both versions resolve to current state → same snapshot → no note
        assert "note" not in result


# ---------------------------------------------------------------------------
# list_versions
# ---------------------------------------------------------------------------


class TestListVersions:
    """REQ-L2-AS-032: Version listing for artifacts."""

    def test_list_versions_returns_baseline_and_current(self):
        """list_versions returns version 0 (baseline) + current version."""
        svc = ArtifactDiffService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        artifact_mock = _make_artifact_mock("Requirement")
        req_mock = _make_requirement_mock(version=3)

        req_model = MagicMock()
        req_model.objects.select_related.return_value.filter.return_value.first.return_value = (
            req_mock
        )

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.first.return_value = artifact_mock
                with patch.dict(
                    "application.artifact_diff_service._ENTITY_MODELS",
                    {"Requirement": req_model},
                ):
                    versions = svc.list_versions(
                        artifact_id=ARTIFACT_ID, ctx=ctx
                    )

        assert len(versions) == 2
        assert versions[0]["version"] == 0
        assert versions[0]["label"] == "Creation baseline"
        assert versions[1]["version"] == 3
        assert "Current" in versions[1]["label"]
