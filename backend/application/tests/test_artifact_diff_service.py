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


def _make_goal_mock(**kwargs):
    goal = MagicMock()
    goal.id = kwargs.get("id", uuid.uuid4())
    goal.title = kwargs.get("title", "Reduce onboarding time")
    goal.description = kwargs.get("description", "Initial description")
    goal.status = kwargs.get("status", "Entwurf")
    goal.version = kwargs.get("version", 1)
    goal.modified_at = kwargs.get("modified_at", None)
    return goal


def _make_main_goal_mock(**kwargs):
    mg = MagicMock()
    mg.id = kwargs.get("id", uuid.uuid4())
    mg.content = kwargs.get("content", "Deliver a self-service onboarding flow.")
    mg.source = kwargs.get("source", "ai")
    mg.status = kwargs.get("status", "Entwurf")
    mg.version = kwargs.get("version", 1)
    mg.modified_at = kwargs.get("modified_at", None)
    return mg


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
        # Issue #767: "status" is intentionally not a version-bound diff
        # field anymore — workflow transitions write it without bumping
        # `version`, which made diffs on a fixed version pair unstable.
        assert "status" not in field_statuses

        # "added" fields should have "to" but no "from"
        title_field = next(f for f in result["fields"] if f["name"] == "title")
        assert title_field["to"] == "New Title"
        assert "from" not in title_field


# ---------------------------------------------------------------------------
# diff: stable across a status-only workflow transition (issue #767)
# ---------------------------------------------------------------------------


class TestDiffStableAcrossWorkflowTransition:
    """Issue #767 (QA Audit Follow-up #737).

    A workflow transition writes ``status`` via
    ``StateLifecycleManager._sync_status_mirror``, a bare ``.update()`` that
    deliberately does not bump ``AuditableModel.version`` (it is not a
    content edit). Before the fix, ``status`` was still a version-bound diff
    field, so diffing the *same* version pair before and after a transition
    returned different content for a version number that had not moved.

    This test does not call the workflow engine — it simulates exactly what
    ``_sync_status_mirror`` does to the persistence row (mutate ``status``
    in place, leave ``version`` untouched) and asserts the diff for a fixed
    version pair is byte-for-byte stable across that mutation.
    """

    def test_diff_unchanged_when_status_mutates_without_version_bump(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        artifact_mock = _make_artifact_mock("Requirement")
        req_mock = _make_requirement_mock(
            title="Stable Title",
            description="Stable description",
            category="functional",
            status="draft",
            version=2,
        )

        req_model = MagicMock()
        req_model.objects.select_related.return_value.filter.return_value.first.return_value = (
            req_mock
        )

        def _run_diff() -> dict:
            with patch.object(svc, "_set_tenant_context"):
                with patch("application.artifact_diff_service.Artifact") as ArtMock:
                    ArtMock.objects.filter.return_value.first.return_value = artifact_mock
                    with patch.dict(
                        "application.artifact_diff_service._ENTITY_MODELS",
                        {"Requirement": req_model},
                    ):
                        return svc.diff(
                            artifact_id=ARTIFACT_ID,
                            from_version=0,
                            to_version=2,
                            ctx=ctx,
                        )

        result_before = _run_diff()

        # Simulate a workflow transition: only `status` changes, `version`
        # (the optimistic-lock counter the diff resolves on) does not move —
        # exactly what StateLifecycleManager._sync_status_mirror does via its
        # `.update(status=...)`.
        req_mock.status = "in_review"
        assert req_mock.version == 2  # sanity: transition never touches this

        result_after = _run_diff()

        assert result_after == result_before

        # "status" must not be a diffable field for this type anymore, on
        # either side of the mutation.
        field_names_before = {f["name"] for f in result_before["fields"]}
        field_names_after = {f["name"] for f in result_after["fields"]}
        assert "status" not in field_names_before
        assert "status" not in field_names_after


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
                        # Must match the mock's lock version — only the current
                        # version resolves to a snapshot (issue #213).
                        to_version=2,
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
# diff: Goal / MainGoal (issue #219 — _ENTITY_FIELDS/_ENTITY_MODELS gap)
# ---------------------------------------------------------------------------


class TestDiffForGoalAndMainGoal:
    """Issue #219: Goal/MainGoal were missing from the diff dispatch tables.

    Baselines already capture full Goal/MainGoal state (issue #398), but
    ``ArtifactDiffService`` had no ``_ENTITY_FIELDS``/``_ENTITY_MODELS`` entry
    for either type, so the entity-diff code path (``diff_for_entity`` /
    ``list_versions_for_entity``) would fail with ``NotFoundError`` the moment
    it was reached — e.g. from a future frontend wiring of #219.
    """

    def test_goal_is_registered_for_entity_diffing(self):
        from application.artifact_diff_service import _ENTITY_FIELDS, _ENTITY_MODELS
        from application.models import Goal

        assert "Goal" in _ENTITY_FIELDS
        assert _ENTITY_MODELS["Goal"] is Goal

    def test_main_goal_is_registered_for_entity_diffing(self):
        from application.artifact_diff_service import _ENTITY_FIELDS, _ENTITY_MODELS
        from application.models import MainGoal

        assert "MainGoal" in _ENTITY_FIELDS
        assert _ENTITY_MODELS["MainGoal"] is MainGoal

    def test_diff_for_goal_detects_title_change(self):
        """Field-level diff on a Goal entity via diff_for_entity."""
        svc = ArtifactDiffService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        goal_mock = _make_goal_mock(version=1)

        goal_model = MagicMock()
        goal_model.objects.filter.return_value.first.return_value = goal_mock

        with patch.object(svc, "_set_tenant_context"):
            with patch.dict(
                "application.artifact_diff_service._ENTITY_MODELS",
                {"Goal": goal_model},
            ):
                result = svc.diff_for_entity(
                    entity_type="Goal",
                    entity_id=goal_mock.id,
                    from_version=0,
                    to_version=1,
                    ctx=ctx,
                )

        title_field = next(f for f in result["fields"] if f["name"] == "title")
        assert title_field["status"] == "added"
        assert title_field["to"] == "Reduce onboarding time"

    def test_diff_for_main_goal_detects_content_change(self):
        """Field-level diff on a MainGoal entity via diff_for_entity."""
        svc = ArtifactDiffService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        mg_mock = _make_main_goal_mock(version=1)

        mg_model = MagicMock()
        mg_model.objects.filter.return_value.first.return_value = mg_mock

        with patch.object(svc, "_set_tenant_context"):
            with patch.dict(
                "application.artifact_diff_service._ENTITY_MODELS",
                {"MainGoal": mg_model},
            ):
                result = svc.diff_for_entity(
                    entity_type="MainGoal",
                    entity_id=mg_mock.id,
                    from_version=0,
                    to_version=1,
                    ctx=ctx,
                )

        content_field = next(f for f in result["fields"] if f["name"] == "content")
        assert content_field["status"] == "added"
        assert content_field["to"] == "Deliver a self-service onboarding flow."


# ---------------------------------------------------------------------------
# diff: note field when historical version unavailable
# ---------------------------------------------------------------------------


class TestDiffNoteField:
    """REQ-L2-AS-032: Response includes note when historical version unavailable."""

    def test_diff_note_when_from_version_unavailable(self):
        """from_version > 0 with no stored snapshot → response carries a note.

        Issue #213: historical lock-counter values no longer fall back to the
        current row, so the caller is told the snapshot is unavailable instead
        of being handed a diff of the current state against itself.
        """
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

        # from_version=1 has no stored snapshot → limitation documented
        assert "note" in result
        assert "not available" in result["note"]


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
