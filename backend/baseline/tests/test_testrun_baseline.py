"""
ARCH-L1-006 BaselineService — TestRun/TestRunResult baseline coverage.

req_id: REQ-156

Verifies that TestRun and TestRunResult entities are included in Baseline
snapshots for project- and global-scoped builds, and that their full state
is captured in BaselineDeltaIndexEntry.state (REQ-L2-BL-012).

Design note (REQ-156):
  TestRun/TestRunResult are NOT backed by the pl_artifact table — they are
  standalone operational records linked directly to a Workspace. They are
  therefore NOT included in document-scoped baselines (which walk the artifact
  hierarchy), but ARE included in project- and global-scoped baselines.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from baseline.delta_index_builder import ScopeResolver
from baseline.state_capture import capture_states
from baseline.store import BaselineStore
from baseline.types import BaselineMetadata, DeltaIndexTuple


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT_ID = uuid.uuid4()
WORKSPACE_ID = uuid.uuid4()


def _make_metadata(name: str = "TR-Baseline", scope: str = "project") -> BaselineMetadata:
    return BaselineMetadata(
        workspace_id=WORKSPACE_ID,
        scope=scope,
        name=name,
        description="TestRun baseline test",
        created_by="test-agent",
        created_at=datetime.now(tz=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Unit tests — ScopeResolver (no real DB, uses mock cursor)
# ---------------------------------------------------------------------------


class TestScopeResolverIncludesTestRuns:
    """REQ-156: ScopeResolver._resolve_project / _resolve_global emit test_run
    and test_run_result tuples alongside artifact/glossary entries."""

    def _make_resolver_with_cursor(
        self,
        artifact_rows=None,
        glossary_rows=None,
        test_run_rows=None,
        test_result_rows=None,
    ):
        """Build a ScopeResolver whose DB cursor returns controlled data."""
        resolver = ScopeResolver()
        return resolver, {
            "artifact": artifact_rows or [],
            "glossary": glossary_rows or [],
            "test_run": test_run_rows or [],
            "test_result": test_result_rows or [],
        }

    def test_resolve_project_includes_test_run_tuples(self):
        """project scope must include test_run entity_type tuples."""
        run_id = str(uuid.uuid4())
        result_id = str(uuid.uuid4())

        resolver = ScopeResolver()

        call_counter = [0]

        def fake_execute(sql, params):
            call_counter[0] += 1

        # Build fake cursor that returns data per SQL pattern
        query_results = {
            "pl_artifact": [(str(uuid.uuid4()), 1)],
            "pl_glossary_term": [],
            "pl_test_run": [(run_id, 3)],
            "pl_test_run_result": [(result_id, 1)],
        }

        class FakeCursor:
            def __init__(self):
                self._rows = []

            def execute(self, sql, params):
                sql_stripped = " ".join(sql.split())
                if "pl_artifact" in sql_stripped and "pl_test_run" not in sql_stripped:
                    self._rows = query_results["pl_artifact"]
                elif "pl_glossary_term" in sql_stripped:
                    self._rows = query_results["pl_glossary_term"]
                elif "pl_test_run_result" in sql_stripped:
                    self._rows = query_results["pl_test_run_result"]
                elif "pl_test_run" in sql_stripped:
                    self._rows = query_results["pl_test_run"]
                else:
                    self._rows = []

            def fetchall(self):
                return self._rows

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        fake_cursor = FakeCursor()

        class FakeConnection:
            def cursor(self):
                return FakeCursor()

        with patch("django.db.connection", FakeConnection()):
            result = resolver._resolve_project(WORKSPACE_ID, TENANT_ID)

        entity_types = {t.entity_type for t in result}
        assert "test_run" in entity_types, (
            "project scope must include test_run entity_type"
        )
        assert "test_run_result" in entity_types, (
            "project scope must include test_run_result entity_type"
        )

        run_tuple = next(t for t in result if t.entity_type == "test_run")
        assert run_tuple.item_id == run_id
        assert run_tuple.version == 3

        result_tuple = next(t for t in result if t.entity_type == "test_run_result")
        assert result_tuple.item_id == result_id
        assert result_tuple.version == 1

    def test_resolve_project_no_test_runs_produces_no_test_run_tuples(self):
        """When no TestRuns exist in workspace, no test_run tuples are emitted."""

        class FakeCursor:
            def __init__(self):
                self._rows = []

            def execute(self, sql, params):
                self._rows = []

            def fetchall(self):
                return []

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        class FakeConnection:
            def cursor(self):
                return FakeCursor()

        resolver = ScopeResolver()
        with patch("django.db.connection", FakeConnection()):
            result = resolver._resolve_project(WORKSPACE_ID, TENANT_ID)

        test_run_tuples = [t for t in result if t.entity_type in ("test_run", "test_run_result")]
        assert test_run_tuples == [], (
            "no TestRuns in workspace → no test_run/test_run_result tuples"
        )

    def test_resolve_global_includes_test_run_tuples(self):
        """global scope must include test_run tuples across all workspaces."""
        run_id = str(uuid.uuid4())

        query_results: dict[str, list] = {
            "pl_artifact": [],
            "pl_glossary_term": [],
            "pl_test_run": [(run_id, 2)],
            "pl_test_run_result": [],
        }

        class FakeCursor:
            def __init__(self):
                self._rows: list = []

            def execute(self, sql, params):
                sql_stripped = " ".join(sql.split())
                if "pl_artifact" in sql_stripped and "pl_test_run" not in sql_stripped:
                    self._rows = query_results["pl_artifact"]
                elif "pl_glossary_term" in sql_stripped:
                    self._rows = query_results["pl_glossary_term"]
                elif "pl_test_run_result" in sql_stripped:
                    self._rows = query_results["pl_test_run_result"]
                elif "pl_test_run" in sql_stripped:
                    self._rows = query_results["pl_test_run"]
                else:
                    self._rows = []

            def fetchall(self):
                return self._rows

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        class FakeConnection:
            def cursor(self):
                return FakeCursor()

        resolver = ScopeResolver()
        with patch("django.db.connection", FakeConnection()):
            result = resolver._resolve_global(TENANT_ID)

        entity_types = {t.entity_type for t in result}
        assert "test_run" in entity_types
        run_tuple = next(t for t in result if t.entity_type == "test_run")
        assert run_tuple.item_id == run_id
        assert run_tuple.version == 2


# ---------------------------------------------------------------------------
# Unit tests — state_capture (no real DB, uses mock ORM)
# ---------------------------------------------------------------------------


class TestStateCaptureTestRuns:
    """REQ-156: capture_states must produce correct state dicts for
    test_run and test_run_result entity_types."""

    def test_capture_states_test_run_populates_state(self):
        """test_run entity_type → state contains name, status, workspace_id."""
        run_id = str(uuid.uuid4())
        workspace_id = str(uuid.uuid4())

        mock_run = MagicMock()
        mock_run.id = run_id
        mock_run.uid = "TR-001"
        mock_run.name = "Sprint 42 regression"
        mock_run.status = "passed"
        mock_run.started_at = datetime(2026, 7, 17, 10, 0, tzinfo=timezone.utc)
        mock_run.finished_at = datetime(2026, 7, 17, 11, 0, tzinfo=timezone.utc)
        mock_run.ci_job_id = "ci-12345"
        mock_run.workspace_id = uuid.UUID(workspace_id)
        mock_run.version = 5

        tuples = [DeltaIndexTuple(item_id=run_id, version=5, entity_type="test_run")]

        with patch("persistence.models.TestRun") as MockTestRun:
            MockTestRun.unscoped.filter.return_value = [mock_run]
            states = capture_states(tuples, TENANT_ID)

        assert run_id in states
        state = states[run_id]
        assert state["entity_type"] == "test_run"
        assert state["name"] == "Sprint 42 regression"
        assert state["status"] == "passed"
        assert state["uid"] == "TR-001"
        assert state["ci_job_id"] == "ci-12345"
        assert state["workspace_id"] == workspace_id
        assert state["version"] == 5
        assert state["started_at"] is not None
        assert state["finished_at"] is not None

    def test_capture_states_test_run_result_populates_state(self):
        """test_run_result entity_type → state contains status, test_case_title."""
        result_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        tc_id = str(uuid.uuid4())

        mock_result = MagicMock()
        mock_result.id = result_id
        mock_result.test_run_id = uuid.UUID(run_id)
        mock_result.test_case_id = uuid.UUID(tc_id)
        mock_result.test_case_title = "Login with valid credentials"
        mock_result.status = "passed"
        mock_result.executed_at = datetime(2026, 7, 17, 10, 30, tzinfo=timezone.utc)
        mock_result.duration_ms = 142
        mock_result.message = ""
        mock_result.version = 1

        tuples = [
            DeltaIndexTuple(item_id=result_id, version=1, entity_type="test_run_result")
        ]

        with patch("persistence.models.TestRunResult") as MockTRR:
            MockTRR.unscoped.filter.return_value = [mock_result]
            states = capture_states(tuples, TENANT_ID)

        assert result_id in states
        state = states[result_id]
        assert state["entity_type"] == "test_run_result"
        assert state["test_run_id"] == run_id
        assert state["test_case_id"] == tc_id
        assert state["test_case_title"] == "Login with valid credentials"
        assert state["status"] == "passed"
        assert state["duration_ms"] == 142
        assert state["version"] == 1

    def test_capture_states_test_run_result_null_test_case(self):
        """test_run_result with no test_case_id → test_case_id is None in state."""
        result_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())

        mock_result = MagicMock()
        mock_result.id = result_id
        mock_result.test_run_id = uuid.UUID(run_id)
        mock_result.test_case_id = None
        mock_result.test_case_title = "Manual check"
        mock_result.status = "failed"
        mock_result.executed_at = None
        mock_result.duration_ms = None
        mock_result.message = "Manual step failed"
        mock_result.version = 2

        tuples = [
            DeltaIndexTuple(item_id=result_id, version=2, entity_type="test_run_result")
        ]

        with patch("persistence.models.TestRunResult") as MockTRR:
            MockTRR.unscoped.filter.return_value = [mock_result]
            states = capture_states(tuples, TENANT_ID)

        assert result_id in states
        assert states[result_id]["test_case_id"] is None
        assert states[result_id]["executed_at"] is None

    def test_capture_states_empty_test_run_list(self):
        """Empty test_run list → empty dict returned without DB call."""
        tuples: list[DeltaIndexTuple] = []
        # No mock needed — capture_states short-circuits on empty input
        states = capture_states(tuples, TENANT_ID)
        assert states == {}

    def test_capture_states_mixed_entity_types(self):
        """Mixed tuples (item + test_run) are all captured in one pass."""
        run_id = str(uuid.uuid4())
        art_id = str(uuid.uuid4())

        mock_run = MagicMock()
        mock_run.id = run_id
        mock_run.uid = None
        mock_run.name = "Smoke test"
        mock_run.status = "partial"
        mock_run.started_at = None
        mock_run.finished_at = None
        mock_run.ci_job_id = ""
        mock_run.workspace_id = uuid.uuid4()
        mock_run.version = 1

        tuples = [
            DeltaIndexTuple(item_id=run_id, version=1, entity_type="test_run"),
            DeltaIndexTuple(item_id=art_id, version=2, entity_type="item"),
        ]

        with patch("persistence.models.TestRun") as MockTR, \
             patch("persistence.models.Artifact") as MockArt, \
             patch("persistence.models.Requirement") as MockReq, \
             patch("persistence.models.ArchitectureElement") as MockAE, \
             patch("persistence.models.StakeholderNeed") as MockSN, \
             patch("persistence.models.TestCase") as MockTC, \
             patch("application.models.Adr") as MockAdr, \
             patch("application.models.Risk") as MockRisk, \
             patch("application.models.Issue") as MockIssue, \
             patch("application.models.Goal") as MockGoal, \
             patch("application.models.MainGoal") as MockMainGoal:
            MockTR.unscoped.filter.return_value = [mock_run]
            # item queries return nothing — bare artifact path
            mock_art = MagicMock()
            mock_art.id = art_id
            mock_art.artifact_type = "generic"
            # Issue #398: the Artifact header now also carries custom_fields
            # and parent_id, which are captured for every artifact-backed item.
            MockArt.unscoped.filter.return_value.values_list.return_value = [
                (art_id, "generic", {"rationale": "kept"}, None)
            ]
            MockReq.unscoped.filter.return_value = []
            MockAE.unscoped.filter.return_value = []
            MockSN.unscoped.filter.return_value = []
            MockTC.unscoped.filter.return_value = []
            for mock_model in (MockAdr, MockRisk, MockIssue, MockGoal, MockMainGoal):
                mock_model.objects.filter.return_value = []

            states = capture_states(tuples, TENANT_ID)

        # test_run state present
        assert run_id in states
        assert states[run_id]["entity_type"] == "test_run"
        assert states[run_id]["name"] == "Smoke test"

        # bare artifact still gets the shared Artifact envelope (#398)
        assert states[art_id]["artifact_type"] == "generic"
        assert states[art_id]["custom_fields"] == {"rationale": "kept"}
        assert states[art_id]["artifact_parent_id"] is None


# ---------------------------------------------------------------------------
# Integration tests — round-trip with real DB
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTestRunBaselineIntegration:
    """REQ-156 integration: build a project-scoped Baseline that includes
    TestRun/TestRunResult rows and verify they are stored in delta entries."""

    def _make_tenant(self):
        from persistence.models import Tenant

        return Tenant.objects.create(
            name="TR-BL-Tenant",
            slug=f"tr-bl-{uuid.uuid4().hex[:8]}",
        )

    def test_project_scope_baseline_includes_test_run_entries(self):
        """REQ-156: A project-scoped Baseline must contain delta entries for
        TestRun entities in the workspace (entity_type='test_run')."""
        from persistence.tenancy import TenantContext
        from persistence.models import Workspace, TestRun
        from presets.models import WorkspacePresetConfig
        from baseline.store import BaselineStore
        from baseline.delta_index_builder import DeltaIndexBuilder

        tenant = self._make_tenant()
        TenantContext.set_tenant(tenant.id)
        try:
            workspace = Workspace.unscoped.create(
                tenant=tenant,
                name="TR-BL-Workspace",
                preset={"name": "extended"},
            )
            WorkspacePresetConfig.unscoped.create(
                workspace=workspace,
                tenant=tenant,
                active_tier="extended",
                terminology_profile="se_mode",
                downgrade_policy="warn",
            )
            # Create a TestRun in this workspace
            test_run = TestRun.unscoped.create(
                tenant=tenant,
                workspace=workspace,
                name="Sprint 1 regression",
                status="passed",
            )

            builder = DeltaIndexBuilder()
            bl_id = builder.build(
                scope="project",
                workspace_id=workspace.id,
                name="TR-BL-001",
                tenant_id=tenant.id,
            )

            store = BaselineStore()
            detail = store.get(bl_id, tenant.id)

            entity_types = {e.entity_type for e in detail.entries}
            assert "test_run" in entity_types, (
                f"Expected test_run in baseline entries; got {entity_types}"
            )

            run_entry = next(
                e for e in detail.entries
                if e.entity_type == "test_run" and e.item_id == str(test_run.id)
            )
            assert run_entry.version == test_run.version
        finally:
            TenantContext.clear_tenant()

    def test_project_scope_baseline_includes_test_run_result_entries(self):
        """REQ-156: TestRunResult entries within the workspace's TestRuns must
        also appear in the baseline delta index (entity_type='test_run_result')."""
        from persistence.tenancy import TenantContext
        from persistence.models import Workspace, TestRun, TestRunResult
        from presets.models import WorkspacePresetConfig
        from baseline.store import BaselineStore
        from baseline.delta_index_builder import DeltaIndexBuilder

        tenant = self._make_tenant()
        TenantContext.set_tenant(tenant.id)
        try:
            workspace = Workspace.unscoped.create(
                tenant=tenant,
                name="TR-BL-WS-Results",
                preset={"name": "extended"},
            )
            WorkspacePresetConfig.unscoped.create(
                workspace=workspace,
                tenant=tenant,
                active_tier="extended",
                terminology_profile="se_mode",
                downgrade_policy="warn",
            )
            test_run = TestRun.unscoped.create(
                tenant=tenant,
                workspace=workspace,
                name="E2E run",
                status="failed",
            )
            test_result = TestRunResult.unscoped.create(
                tenant=tenant,
                test_run=test_run,
                test_case_title="Login flow",
                status="failed",
                message="Timeout",
            )

            builder = DeltaIndexBuilder()
            bl_id = builder.build(
                scope="project",
                workspace_id=workspace.id,
                name="TR-BL-002",
                tenant_id=tenant.id,
            )

            store = BaselineStore()
            detail = store.get(bl_id, tenant.id)

            entity_types = {e.entity_type for e in detail.entries}
            assert "test_run_result" in entity_types, (
                f"Expected test_run_result in baseline entries; got {entity_types}"
            )

            result_entry = next(
                e for e in detail.entries
                if e.entity_type == "test_run_result"
                and e.item_id == str(test_result.id)
            )
            assert result_entry.version == test_result.version
        finally:
            TenantContext.clear_tenant()

    def test_baseline_state_captures_test_run_fields(self):
        """REQ-156 + REQ-L2-BL-012: The persisted state of a TestRun entry
        must contain name, status, ci_job_id and workspace_id."""
        from persistence.tenancy import TenantContext
        from persistence.models import Workspace, TestRun
        from presets.models import WorkspacePresetConfig
        from baseline.models import BaselineDeltaIndexEntry
        from baseline.delta_index_builder import DeltaIndexBuilder

        tenant = self._make_tenant()
        TenantContext.set_tenant(tenant.id)
        try:
            workspace = Workspace.unscoped.create(
                tenant=tenant,
                name="TR-State-WS",
                preset={"name": "extended"},
            )
            WorkspacePresetConfig.unscoped.create(
                workspace=workspace,
                tenant=tenant,
                active_tier="extended",
                terminology_profile="se_mode",
                downgrade_policy="warn",
            )
            test_run = TestRun.unscoped.create(
                tenant=tenant,
                workspace=workspace,
                name="Nightly build",
                status="passed",
                ci_job_id="nightly-42",
            )

            builder = DeltaIndexBuilder()
            bl_id = builder.build(
                scope="project",
                workspace_id=workspace.id,
                name="TR-BL-State",
                tenant_id=tenant.id,
            )

            entry = BaselineDeltaIndexEntry.objects.filter(
                baseline_id=bl_id,
                item_id=str(test_run.id),
                entity_type="test_run",
            ).first()

            assert entry is not None, "No BaselineDeltaIndexEntry for TestRun"
            assert entry.state is not None, (
                "State must be populated for TestRun (REQ-L2-BL-012)"
            )
            assert entry.state["name"] == "Nightly build"
            assert entry.state["status"] == "passed"
            assert entry.state["ci_job_id"] == "nightly-42"
            assert "workspace_id" in entry.state
        finally:
            TenantContext.clear_tenant()

    def test_no_test_runs_baseline_has_no_test_run_entries(self):
        """REQ-156: When no TestRuns exist for a workspace, the baseline must
        not contain any test_run entries (no contamination from other workspaces)."""
        from persistence.tenancy import TenantContext
        from persistence.models import Workspace, TestRun
        from presets.models import WorkspacePresetConfig
        from baseline.store import BaselineStore
        from baseline.delta_index_builder import DeltaIndexBuilder

        tenant = self._make_tenant()
        TenantContext.set_tenant(tenant.id)
        try:
            workspace_a = Workspace.unscoped.create(
                tenant=tenant,
                name="TR-Empty-WS",
                preset={"name": "extended"},
            )
            WorkspacePresetConfig.unscoped.create(
                workspace=workspace_a,
                tenant=tenant,
                active_tier="extended",
                terminology_profile="se_mode",
                downgrade_policy="warn",
            )
            workspace_b = Workspace.unscoped.create(
                tenant=tenant,
                name="TR-Other-WS",
                preset={},
            )
            # Create a run in workspace_b — must NOT appear in workspace_a baseline
            TestRun.unscoped.create(
                tenant=tenant,
                workspace=workspace_b,
                name="Other workspace run",
                status="in_progress",
            )

            builder = DeltaIndexBuilder()
            bl_id = builder.build(
                scope="project",
                workspace_id=workspace_a.id,
                name="TR-BL-Empty",
                tenant_id=tenant.id,
            )

            store = BaselineStore()
            detail = store.get(bl_id, tenant.id)

            test_run_entries = [
                e for e in detail.entries if e.entity_type == "test_run"
            ]
            assert test_run_entries == [], (
                "Baseline for workspace_a must not include TestRuns from workspace_b"
            )
        finally:
            TenantContext.clear_tenant()
