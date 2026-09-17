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
        payload = {
            "title": "New Title",
            "description": "New description",
            "category": "functional",
        }

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.first.return_value = artifact_mock
                with patch(
                    "application.artifact_diff_service.ArtifactVersionService"
                ) as version_svc_cls:
                    version_svc_cls.return_value.get_payload.return_value = payload
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
    """Issue #767 (QA Audit Follow-up #737); revalidated for Task 29 (M5).

    A workflow transition writes ``status`` via
    ``StateLifecycleManager._sync_status_mirror``, a bare ``.update()`` on the
    live row that never touches ``ArtifactVersion``. Since Task 29, ``diff()``
    reads exclusively from the immutable, already-recorded
    ``ArtifactVersion`` snapshot (never the live row), so a workflow
    transition happening between two calls to ``diff()`` for the same
    revision pair cannot change the result at all — a stronger guarantee than
    the pre-M5 "status is excluded from the diffable field list" fix.
    """

    def test_diff_unchanged_when_status_mutates_without_version_bump(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        artifact_mock = _make_artifact_mock("Requirement")
        payload = {
            "title": "Stable Title",
            "description": "Stable description",
            "category": "functional",
        }

        def _run_diff() -> dict:
            with patch.object(svc, "_set_tenant_context"):
                with patch("application.artifact_diff_service.Artifact") as ArtMock:
                    ArtMock.objects.filter.return_value.first.return_value = artifact_mock
                    with patch(
                        "application.artifact_diff_service.ArtifactVersionService"
                    ) as version_svc_cls:
                        version_svc_cls.return_value.get_payload.return_value = payload
                        return svc.diff(
                            artifact_id=ARTIFACT_ID,
                            from_version=0,
                            to_version=2,
                            ctx=ctx,
                        )

        result_before = _run_diff()

        # A workflow transition mutates the live row's `status` via a bare
        # `.update()` that never calls ArtifactVersionService.record() — the
        # recorded revision-2 payload is unaffected, so a second diff() call
        # for the same version pair must be byte-for-byte identical.
        result_after = _run_diff()

        assert result_after == result_before

        # "status" is not part of _ENTITY_FIELDS["Requirement"] and the mock
        # payload never carried it either — it must not appear either side.
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

    def test_diff_unsupported_artifact_type_at_version_zero_returns_empty_fields(self):
        """Task 29 (M5): diff() no longer gates on a fixed type-support list.

        Before Task 29, an artifact type absent from ``_ENTITY_FIELDS`` raised
        NotFoundError up front. Since ``diff()`` reads exclusively from
        ``ArtifactVersionService`` now, an unregistered type simply has no
        diffable fields (``_ENTITY_FIELDS.get(type, [])`` defaults to
        ``[]``) — comparing baseline (0) against itself (0) succeeds with an
        empty field list rather than being rejected outright.
        """
        svc = ArtifactDiffService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        artifact_mock = _make_artifact_mock("UnsupportedType")

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.first.return_value = artifact_mock

                result = svc.diff(
                    artifact_id=ARTIFACT_ID,
                    from_version=0,
                    to_version=0,
                    ctx=ctx,
                )

        assert result["entity_type"] == "UnsupportedType"
        assert result["fields"] == []

    def test_diff_unsupported_artifact_type_at_missing_revision_raises_not_found(self):
        """A non-zero version with no recorded snapshot still 404s."""
        svc = ArtifactDiffService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        artifact_mock = _make_artifact_mock("UnsupportedType")

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.first.return_value = artifact_mock
                with patch(
                    "application.artifact_diff_service.ArtifactVersionService"
                ) as version_svc_cls:
                    version_svc_cls.return_value.get_payload.return_value = None

                    with pytest.raises(NotFoundError, match="not available"):
                        svc.diff(
                            artifact_id=ARTIFACT_ID,
                            from_version=0,
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

        with patch.object(svc, "_set_tenant_context") as mock_set_tenant:
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.first.return_value = artifact_mock
                svc.diff(
                    artifact_id=ARTIFACT_ID,
                    from_version=0,
                    to_version=0,
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
        payload = {
            "title": "Component A",
            "description": "Updated description",
            "element_type": "component",
        }

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.first.return_value = artifact_mock
                with patch(
                    "application.artifact_diff_service.ArtifactVersionService"
                ) as version_svc_cls:
                    version_svc_cls.return_value.get_payload.return_value = payload
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

        Task 29 (M5): ``get_payload`` returning ``None`` for the from-side
        (e.g. a revision recorded before a field joined ``_ENTITY_FIELDS``,
        or genuinely missing) is documented via ``note`` rather than treated
        as a 404 — only the to-side is hard-required.
        """
        svc = ArtifactDiffService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        artifact_mock = _make_artifact_mock("Requirement")
        payload = {"title": "t", "description": "d", "category": "functional"}

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.first.return_value = artifact_mock
                with patch(
                    "application.artifact_diff_service.ArtifactVersionService"
                ) as version_svc_cls:
                    version_svc_cls.return_value.get_payload.side_effect = (
                        lambda _artifact_id, revision, _ctx: (
                            None if revision == 1 else payload
                        )
                    )
                    result = svc.diff(
                        artifact_id=ARTIFACT_ID,
                        from_version=1,
                        to_version=3,
                        ctx=ctx,
                    )

        # from_version=1 has no stored snapshot → limitation documented
        assert "note" in result
        assert "no stored content" in result["note"]


# ---------------------------------------------------------------------------
# list_versions
# ---------------------------------------------------------------------------


class TestListVersions:
    """REQ-L2-AS-032: Version listing for artifacts."""

    def test_list_versions_returns_baseline_and_recorded_revisions(self):
        """list_versions returns version 0 (baseline) + every stored revision."""
        svc = ArtifactDiffService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        recorded = [
            {"version": 1, "label": "v1", "modified_at": None, "content_available": True},
            {"version": 2, "label": "v2", "modified_at": None, "content_available": True},
        ]

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.exists.return_value = True
                with patch(
                    "application.artifact_diff_service.ArtifactVersionService"
                ) as version_svc_cls:
                    version_svc_cls.return_value.list_revisions.return_value = recorded
                    versions = svc.list_versions(artifact_id=ARTIFACT_ID, ctx=ctx)

        assert len(versions) == 3
        assert versions[0]["version"] == 0
        assert versions[0]["label"] == "Creation baseline"
        assert [v["version"] for v in versions[1:]] == [1, 2]
        assert all(v["content_available"] for v in versions[1:])

    def test_list_versions_unknown_artifact_raises_not_found(self):
        svc = ArtifactDiffService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        with patch.object(svc, "_set_tenant_context"):
            with patch("application.artifact_diff_service.Artifact") as ArtMock:
                ArtMock.objects.filter.return_value.exists.return_value = False
                with pytest.raises(NotFoundError):
                    svc.list_versions(artifact_id=ARTIFACT_ID, ctx=ctx)
