"""
Tests for COMP-AS-015 IssueService.

leaf_id : COMP-AS-015
req_id  : REQ-L1-029, REQ-L3-ISSUE-001..011

Static tests (no DB): CRUD, severity validation, assignee tracking,
multi-filter listing, workflow init, TraceLink, audit, event emission,
tenant isolation.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.issue_service import IssueService, IssueDTO, IssueValidator, ISSUE_LINK_TYPES
from application.models import Issue

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


WS_ID = uuid.uuid4()
ISSUE_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# DB-backed fixtures (Task 1 / Phase 1 prerequisite cleanup: outdate() e2e)
# ---------------------------------------------------------------------------


@pytest.fixture
def issue_tenant():
    from persistence.models import Tenant

    return Tenant.objects.create(name="issue-outdate-tenant", slug="issue-outdate-tenant")


@pytest.fixture
def issue_user(issue_tenant):
    from persistence.models import User

    return User.objects.create(
        username="issue-outdate-user",
        email="issue-outdate@example.com",
        tenant=issue_tenant,
    )


@pytest.fixture
def issue_workspace(issue_tenant):
    from persistence.models import Workspace
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(issue_tenant.id)
    try:
        return Workspace.objects.create(tenant=issue_tenant, name="issue-outdate-workspace")
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def auth_ctx(issue_user):
    from auth_tenancy.context import AuthContext

    return AuthContext(
        user_id=issue_user.id,
        tenant_id=issue_user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="issue-outdate-tenant",
    )


@pytest.fixture
def issue(auth_ctx, issue_workspace):
    """Persisted Issue with a default workflow, for outdate()-based delete tests."""
    from persistence.tenancy import TenantContext
    from workflow.services import create_default_workflow

    TenantContext.set_tenant(issue_workspace.tenant_id)
    try:
        create_default_workflow(
            workspace_id=issue_workspace.id,
            preset="issue_default",
            item_type="Issue",
            tenant_id=issue_workspace.tenant_id,
        )
    finally:
        TenantContext.clear_tenant()

    svc = IssueService()
    return svc.create_issue(
        workspace_id=issue_workspace.id,
        title="Outdate Target Issue",
        severity="medium",
        ctx=auth_ctx,
    )


def _make_issue(**kwargs):
    issue = MagicMock(spec=Issue)
    issue.id = kwargs.get("id", ISSUE_ID)
    issue.workspace_id = kwargs.get("workspace_id", WS_ID)
    issue.tenant_id = kwargs.get("tenant_id", TENANT_ID)
    issue.title = kwargs.get("title", "Login button broken")
    issue.description = kwargs.get("description", "Button does not respond")
    issue.severity = kwargs.get("severity", "high")
    issue.category = kwargs.get("category", "defect")
    issue.assignee_id = kwargs.get("assignee_id", None)
    issue.assignee_changed_date = kwargs.get("assignee_changed_date", None)
    issue.due_date = kwargs.get("due_date", None)
    issue.tags = kwargs.get("tags", [])
    issue.status = kwargs.get("status", "Open")
    issue.version = kwargs.get("version", 1)
    return issue


# ---------------------------------------------------------------------------
# IssueValidator
# ---------------------------------------------------------------------------


class TestIssueValidator:
    def test_valid_create_passes(self):
        IssueValidator.validate_create(title="Login broken", severity="high")

    def test_empty_title_raises(self):
        with pytest.raises(ValidationError, match="required"):
            IssueValidator.validate_create(title="", severity="high")

    def test_invalid_severity_raises(self):
        with pytest.raises(ValidationError, match="severity"):
            IssueValidator.validate_create(title="Issue", severity="blocker")

    def test_invalid_category_raises(self):
        with pytest.raises(ValidationError, match="category"):
            IssueValidator.validate_create(
                title="Issue", severity="high", category="unknown"
            )

    def test_validate_create_has_no_status_parameter(self):
        """Datenmodell-Konsolidierung Phase 1: status is not a create input
        anymore; a caller sending it gets a TypeError, not a ValidationError."""
        with pytest.raises(TypeError):
            IssueValidator.validate_create(
                title="Issue", severity="high", status="Cancelled"
            )

    def test_all_severities_valid(self):
        for s in Issue.Severity.values:
            IssueValidator.validate_create(title="Issue", severity=s)

    def test_all_categories_valid(self):
        for c in Issue.Category.values:
            IssueValidator.validate_create(title="Issue", severity="medium", category=c)


# ---------------------------------------------------------------------------
# IssueDTO
# ---------------------------------------------------------------------------


class TestIssueDTO:
    def test_from_orm_maps_fields(self):
        """Datenmodell-Konsolidierung: `status` is now supplied by the caller
        (resolved from the workflow engine), not read off the ORM row."""
        issue = _make_issue(tags=["ui", "frontend"])
        dto = IssueDTO.from_orm(issue, status=issue.status)
        assert dto.id == issue.id
        assert dto.severity == issue.severity
        assert dto.status == issue.status
        assert dto.tags == ["ui", "frontend"]


# ---------------------------------------------------------------------------
# create_issue
# ---------------------------------------------------------------------------


class TestCreateIssue:
    def test_creates_issue_with_workflow_init(self):
        """create_issue persists, inits workflow, writes audit, emits event."""
        svc = IssueService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        created_issue = _make_issue()

        with (
            patch("application.issue_service.Issue.objects") as mock_mgr,
            patch("application.issue_service.IssueService._set_tenant_context"),
            patch("application.issue_service.IssueService._assert_write_permission"),
            patch("application.issue_service.IssueService._audit") as mock_audit,
            patch("application.issue_service.IssueService._emit_event") as mock_emit,
            patch("application.issue_service.IssueService._make_event", return_value=MagicMock()),
            patch("persistence.models.Tenant.objects") as mock_tenant,
            patch("persistence.models.Workspace.objects") as mock_ws,
            patch("persistence.models.Artifact.objects") as mock_artifact,
            patch("workflow.services.initialize_workflow_states") as mock_wf,
        ):
            mock_tenant.filter.return_value.first.return_value = MagicMock()
            mock_ws.filter.return_value.first.return_value = MagicMock()
            mock_artifact.create.return_value = MagicMock()
            mock_mgr.create.return_value = created_issue
            result = svc.create_issue(
                workspace_id=WS_ID,
                title="Login button broken",
                severity="high",
                ctx=ctx,
            )

        mock_mgr.create.assert_called_once()
        mock_wf.assert_called_once()
        mock_audit.assert_called_once()
        assert mock_audit.call_args.kwargs["operation"] == "create"
        mock_emit.assert_called_once()
        assert result is created_issue

    def test_viewer_cannot_create(self):
        svc = IssueService()
        ctx = _make_ctx(roles=("viewer",))
        with pytest.raises(PermissionDeniedError):
            svc.create_issue(
                workspace_id=WS_ID,
                title="Issue",
                severity="low",
                ctx=ctx,
            )

    def test_invalid_severity_raises_before_db_write(self):
        svc = IssueService()
        ctx = _make_ctx()

        with (
            patch("application.issue_service.IssueService._set_tenant_context"),
            patch("application.issue_service.IssueService._assert_write_permission"),
        ):
            with pytest.raises(ValidationError, match="severity"):
                svc.create_issue(
                    workspace_id=WS_ID,
                    title="Issue",
                    severity="blocker",
                    ctx=ctx,
                )

    def test_workflow_failure_is_swallowed(self):
        """Workflow init failure does not abort issue creation."""
        svc = IssueService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        created_issue = _make_issue()

        with (
            patch("application.issue_service.Issue.objects") as mock_mgr,
            patch("application.issue_service.IssueService._set_tenant_context"),
            patch("application.issue_service.IssueService._assert_write_permission"),
            patch("application.issue_service.IssueService._audit"),
            patch("application.issue_service.IssueService._emit_event"),
            patch("application.issue_service.IssueService._make_event", return_value=MagicMock()),
            patch("persistence.models.Tenant.objects") as mock_tenant,
            patch("persistence.models.Workspace.objects") as mock_ws,
            patch("persistence.models.Artifact.objects") as mock_artifact,
            patch(
                "workflow.services.initialize_workflow_states",
                side_effect=RuntimeError("no workflow"),
            ),
        ):
            mock_tenant.filter.return_value.first.return_value = MagicMock()
            mock_ws.filter.return_value.first.return_value = MagicMock()
            mock_artifact.create.return_value = MagicMock()
            mock_mgr.create.return_value = created_issue
            result = svc.create_issue(
                workspace_id=WS_ID,
                title="Issue",
                severity="medium",
                ctx=ctx,
            )

        assert result is created_issue


# ---------------------------------------------------------------------------
# update_issue
# ---------------------------------------------------------------------------


class TestUpdateIssue:
    def test_updates_fields_and_increments_version(self):
        """update_issue patches fields and increments version atomically (REQ-L3-PL001-002)."""
        svc = IssueService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        existing = _make_issue(version=1)
        existing.save = MagicMock()
        # Simulate the DB-level F("version") + 1 that refresh_from_db would return.
        existing.refresh_from_db = MagicMock(
            side_effect=lambda fields=None: setattr(existing, "version", existing.version + 1)
        )

        with (
            patch("application.issue_service.Issue.objects") as mock_mgr,
            patch("application.issue_service.IssueService._set_tenant_context"),
            patch("application.issue_service.IssueService._assert_write_permission"),
            patch("application.issue_service.IssueService._audit"),
            patch("application.issue_service.IssueService._emit_event"),
            patch("application.issue_service.IssueService._make_event", return_value=MagicMock()),
        ):
            mock_mgr.filter.return_value.first.return_value = existing
            result = svc.update_issue(
                issue_id=ISSUE_ID,
                ctx=ctx,
                title="Fixed login button",
                severity="medium",
                tags=["ui"],
            )

        assert result.title == "Fixed login button"
        assert result.severity == "medium"
        assert result.tags == ["ui"]
        assert result.version == 2
        existing.save.assert_called_once()
        # Verify the atomic update was issued and version was refreshed.
        mock_mgr.filter.return_value.update.assert_called_once()
        existing.refresh_from_db.assert_called_once_with(fields=["version"])

    def test_not_found_raises(self):
        svc = IssueService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        with (
            patch("application.issue_service.Issue.objects") as mock_mgr,
            patch("application.issue_service.IssueService._set_tenant_context"),
            patch("application.issue_service.IssueService._assert_write_permission"),
        ):
            mock_mgr.filter.return_value.first.return_value = None
            with pytest.raises(NotFoundError):
                svc.update_issue(issue_id=ISSUE_ID, ctx=ctx)

    def test_audit_entry_written(self):
        svc = IssueService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        existing = _make_issue(version=1)
        existing.save = MagicMock()

        with (
            patch("application.issue_service.Issue.objects") as mock_mgr,
            patch("application.issue_service.IssueService._set_tenant_context"),
            patch("application.issue_service.IssueService._assert_write_permission"),
            patch("application.issue_service.IssueService._audit") as mock_audit,
            patch("application.issue_service.IssueService._emit_event"),
            patch("application.issue_service.IssueService._make_event", return_value=MagicMock()),
        ):
            mock_mgr.filter.return_value.first.return_value = existing
            svc.update_issue(issue_id=ISSUE_ID, ctx=ctx, title="Updated", change_reason="fix")

        mock_audit.assert_called_once()
        assert mock_audit.call_args.kwargs["operation"] == "update"
        assert mock_audit.call_args.kwargs["change_reason"] == "fix"


# ---------------------------------------------------------------------------
# delete_issue
# ---------------------------------------------------------------------------


class TestDeleteIssue:
    def test_does_not_cascade_tracelinks_and_calls_outdate_not_hard_delete(self):
        """GH-484: delete_issue() no longer cascades TraceLinks — it only
        routes the soft-delete through workflow.services.outdate() instead
        of a hard Issue.delete(), so TraceLinks survive and reactivate()
        (GH-443) restores them intact."""
        mock_tls = MagicMock()
        svc = IssueService(trace_link_service=mock_tls)
        ctx = _make_ctx(tenant_id=TENANT_ID)
        existing = _make_issue()

        with (
            patch("application.issue_service.Issue.objects") as mock_mgr,
            patch("application.issue_service.IssueService._set_tenant_context"),
            patch("application.issue_service.IssueService._assert_write_permission"),
            patch("application.issue_service.IssueService._audit"),
            patch("application.issue_service.IssueService._emit_event"),
            patch("application.issue_service.IssueService._make_event", return_value=MagicMock()),
            patch("workflow.services.outdate") as mock_outdate,
        ):
            mock_mgr.filter.return_value.first.return_value = existing
            svc.delete_issue(issue_id=ISSUE_ID, ctx=ctx)

        mock_tls.cascade_delete_trace_links.assert_not_called()
        mock_outdate.assert_called_once_with(
            item_id=existing.id,
            item_type="Issue",
            workspace_id=existing.workspace_id,
            ctx=ctx,
            reason="deleted via issue.delete",
        )
        existing.delete.assert_not_called()

    def test_not_found_raises(self):
        svc = IssueService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        with (
            patch("application.issue_service.Issue.objects") as mock_mgr,
            patch("application.issue_service.IssueService._set_tenant_context"),
            patch("application.issue_service.IssueService._assert_write_permission"),
        ):
            mock_mgr.filter.return_value.first.return_value = None
            with pytest.raises(NotFoundError):
                svc.delete_issue(issue_id=ISSUE_ID, ctx=ctx)


# ---------------------------------------------------------------------------
# list_issues (REQ-006/Phase 0: outdated-filtering)
# ---------------------------------------------------------------------------


class TestListIssuesExcludesOutdated:
    """REQ-006/Phase 0: list_issues() excludes Issues soft-deleted via
    workflow.services.outdate() by default."""

    def test_list_issues_excludes_outdated_by_default(self):
        """Datenmodell-Konsolidierung: the exclusion now filters on
        ``id__in=state_reader.item_ids_in_state(...)``, not a status kwarg."""
        svc = IssueService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        with (
            patch("application.issue_service.Issue.objects") as mock_mgr,
            patch("application.issue_service.IssueService._set_tenant_context"),
            patch(
                "application.issue_service.state_reader.item_ids_in_state",
                return_value="OUTDATED_IDS",
            ) as mock_seam,
        ):
            qs_mock = MagicMock()
            qs_mock.exclude.return_value = qs_mock
            qs_mock.order_by.return_value = []
            mock_mgr.filter.return_value = qs_mock

            svc.list_issues(workspace_id=WS_ID, ctx=ctx)

        mock_seam.assert_called_once_with("Issue", "outdated", tenant_id=ctx.tenant_id)
        qs_mock.exclude.assert_called_once_with(id__in="OUTDATED_IDS")

    def test_list_issues_include_deleted_skips_exclude(self):
        svc = IssueService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        with (
            patch("application.issue_service.Issue.objects") as mock_mgr,
            patch("application.issue_service.IssueService._set_tenant_context"),
        ):
            qs_mock = MagicMock()
            qs_mock.order_by.return_value = []
            mock_mgr.filter.return_value = qs_mock

            svc.list_issues(workspace_id=WS_ID, ctx=ctx, include_deleted=True)

        qs_mock.exclude.assert_not_called()

    def test_delete_then_list_excludes_end_to_end(self, issue, auth_ctx):
        """DB-backed: delete_issue() (outdate()) removes the issue from the
        default list_issues() result; include_deleted=True still returns it."""
        svc = IssueService()

        svc.delete_issue(issue_id=issue.id, ctx=auth_ctx)

        results = list(svc.list_issues(workspace_id=issue.workspace_id, ctx=auth_ctx))
        assert issue.id not in [i.id for i in results]

        results_incl = list(
            svc.list_issues(
                workspace_id=issue.workspace_id, ctx=auth_ctx, include_deleted=True
            )
        )
        assert issue.id in [i.id for i in results_incl]


# ---------------------------------------------------------------------------
# list_issues_by_severity
# ---------------------------------------------------------------------------


class TestListIssuesBySeverity:
    def test_filters_by_severity(self):
        svc = IssueService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        critical_issues = [_make_issue(severity="critical")]

        with (
            patch("application.issue_service.Issue.objects") as mock_mgr,
            patch("application.issue_service.IssueService._set_tenant_context"),
        ):
            mock_mgr.filter.return_value.order_by.return_value = critical_issues
            result = svc.list_issues_by_severity(WS_ID, "critical", ctx)

        mock_mgr.filter.assert_called_once_with(
            workspace_id=WS_ID,
            tenant_id=ctx.tenant_id,
            severity="critical",
        )
        assert result == critical_issues

    def test_invalid_severity_raises(self):
        svc = IssueService()
        ctx = _make_ctx()

        with patch("application.issue_service.IssueService._set_tenant_context"):
            with pytest.raises(ValidationError, match="Invalid severity"):
                svc.list_issues_by_severity(WS_ID, "blocker", ctx)


# ---------------------------------------------------------------------------
# list_issues_multi_filter (ADR-L3-ISSUE-03)
# ---------------------------------------------------------------------------


class TestListIssuesMultiFilter:
    def test_no_filters_returns_all(self):
        """Without filters, all tenant issues in workspace are returned."""
        svc = IssueService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        all_issues = [_make_issue(), _make_issue()]

        with (
            patch("application.issue_service.Issue.objects") as mock_mgr,
            patch("application.issue_service.IssueService._set_tenant_context"),
        ):
            qs_mock = MagicMock()
            qs_mock.filter.return_value = qs_mock
            qs_mock.order_by.return_value = all_issues
            mock_mgr.filter.return_value = qs_mock

            result = svc.list_issues_multi_filter(WS_ID, ctx)

        assert result == all_issues

    def test_status_filter_applied(self):
        """Datenmodell-Konsolidierung Phase 1: the status filter now resolves
        through ``workflow.state_reader.item_ids_in_state`` (unioned per
        requested status) instead of a raw ``status__in`` column filter."""
        svc = IssueService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        with (
            patch("application.issue_service.Issue.objects") as mock_mgr,
            patch("application.issue_service.IssueService._set_tenant_context"),
            patch(
                "application.issue_service.state_reader.item_ids_in_state",
                side_effect=lambda item_type, status, tenant_id: {"id-" + status},
            ) as mock_seam,
        ):
            qs_mock = MagicMock()
            qs_mock.filter.return_value = qs_mock
            qs_mock.order_by.return_value = []
            mock_mgr.filter.return_value = qs_mock

            svc.list_issues_multi_filter(WS_ID, ctx, statuses=["Open", "In Progress"])

        assert mock_seam.call_count == 2
        mock_seam.assert_any_call("Issue", "Open", tenant_id=ctx.tenant_id)
        mock_seam.assert_any_call("Issue", "In Progress", tenant_id=ctx.tenant_id)
        qs_mock.filter.assert_called_with(id__in={"id-Open", "id-In Progress"})

    def test_status_filter_reads_the_engine_not_the_stale_column(self, issue_tenant):
        """DB-backed: an Issue whose WorkflowItemState is "Closed" but whose
        (now write-once, frozen-at-creation) ``status`` column still says
        "Open" must be found under the "Closed" filter, not the column's
        stale value — the whole point of Finding B."""
        from persistence.tenancy import TenantContext
        from workflow.lifecycle_manager import StateLifecycleManager
        from workflow.services import create_default_workflow
        from workflow.transition_validator import ValidationResult

        svc = IssueService()
        workspace_id = uuid.uuid4()
        issue = Issue.objects.create(
            workspace_id=workspace_id,
            tenant_id=issue_tenant.id,
            title="Stale-column issue",
            status="Open",
        )

        TenantContext.set_tenant(issue_tenant.id)
        try:
            create_default_workflow(
                workspace_id=workspace_id,
                preset="issue_default",
                item_type="Issue",
                tenant_id=issue_tenant.id,
            )
            manager = StateLifecycleManager()
            manager.initialize_workflow_states([issue.id], "Issue", workspace_id)
            manager.perform_transition(
                item_id=issue.id,
                item_type="Issue",
                workspace_id=workspace_id,
                target_state="Closed",
                transitioned_by="test",
                validation_result=ValidationResult(valid=True),
            )
        finally:
            TenantContext.clear_tenant()

        assert Issue.objects.get(id=issue.id).status == "Open"  # column frozen

        ctx = _make_ctx(tenant_id=issue_tenant.id)
        found = svc.list_issues_multi_filter(workspace_id, ctx, statuses=["Closed"])

        assert [i.id for i in found] == [issue.id]

    def test_severity_filter_applied(self):
        """Severity filter is applied when severities list is provided."""
        svc = IssueService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        with (
            patch("application.issue_service.Issue.objects") as mock_mgr,
            patch("application.issue_service.IssueService._set_tenant_context"),
        ):
            qs_mock = MagicMock()
            qs_mock.filter.return_value = qs_mock
            qs_mock.order_by.return_value = []
            mock_mgr.filter.return_value = qs_mock

            svc.list_issues_multi_filter(
                WS_ID, ctx, statuses=["Open"], severities=["critical", "high"]
            )

        # Both filters called
        calls = qs_mock.filter.call_args_list
        assert any("severity__in" in str(c) for c in calls)


# ---------------------------------------------------------------------------
# assign_issue (REQ-L3-ISSUE-008, ADR-L3-ISSUE-02)
# ---------------------------------------------------------------------------


class TestAssignIssue:
    def test_assign_updates_assignee_and_date(self):
        """assign_issue sets assignee_id, date, and increments version atomically (REQ-L3-PL001-002)."""
        svc = IssueService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        existing = _make_issue(assignee_id=None)
        existing.save = MagicMock()
        # Simulate the DB-level F("version") + 1 that refresh_from_db would return.
        existing.refresh_from_db = MagicMock(
            side_effect=lambda fields=None: setattr(existing, "version", existing.version + 1)
        )
        new_assignee = uuid.uuid4()

        with (
            patch("application.issue_service.Issue.objects") as mock_mgr,
            patch("application.issue_service.IssueService._set_tenant_context"),
            patch("application.issue_service.IssueService._assert_write_permission"),
            patch("application.issue_service.IssueService._audit") as mock_audit,
            patch("django.utils.timezone.now", return_value="2026-06-24T10:00:00Z"),
        ):
            mock_mgr.filter.return_value.first.return_value = existing
            result = svc.assign_issue(
                issue_id=ISSUE_ID, assignee_id=new_assignee, ctx=ctx
            )

        assert result.assignee_id == new_assignee
        assert result.version == 2
        existing.save.assert_called_once()
        mock_audit.assert_called_once()
        assert mock_audit.call_args.kwargs["operation"] == "assign"

    def test_unassign_sets_assignee_to_none(self):
        """assign_issue with None unassigns the issue (REQ-L3-ISSUE-008)."""
        svc = IssueService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        existing = _make_issue(assignee_id=uuid.uuid4())
        existing.save = MagicMock()

        with (
            patch("application.issue_service.Issue.objects") as mock_mgr,
            patch("application.issue_service.IssueService._set_tenant_context"),
            patch("application.issue_service.IssueService._assert_write_permission"),
            patch("application.issue_service.IssueService._audit"),
            patch("django.utils.timezone.now", return_value="2026-06-24T10:00:00Z"),
        ):
            mock_mgr.filter.return_value.first.return_value = existing
            result = svc.assign_issue(issue_id=ISSUE_ID, assignee_id=None, ctx=ctx)

        assert result.assignee_id is None


# ---------------------------------------------------------------------------
# transition_status (I8: in-memory status staleness fix)
# ---------------------------------------------------------------------------


class TestTransitionStatus:
    def test_returned_instance_reports_the_new_state_not_the_frozen_column(
        self, issue, auth_ctx
    ):
        """Datenmodell-Konsolidierung Phase 1: the engine no longer writes a
        ``status`` mirror, so ``issue.refresh_from_db()`` alone would leave
        the returned instance's ``.status`` at its stale, pre-transition
        column value. Must be corrected in memory before returning."""
        svc = IssueService()

        updated = svc.transition_status(
            issue_id=issue.id,
            target_status="In Progress",
            ctx=auth_ctx,
            change_reason="starting work",
        )

        assert updated.status == "In Progress"
        assert Issue.objects.get(id=issue.id).status == "Open"  # column frozen


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


class TestIssuetenantIsolation:
    def test_list_issues_by_assignee_filters_by_tenant(self):
        """list_issues_by_assignee includes tenant_id in query (REQ-L3-ISSUE-009)."""
        svc = IssueService()
        ctx_a = _make_ctx(tenant_id=uuid.uuid4())
        ctx_b = _make_ctx(tenant_id=uuid.uuid4())
        assignee = uuid.uuid4()

        with (
            patch("application.issue_service.Issue.objects") as mock_mgr,
            patch("application.issue_service.IssueService._set_tenant_context"),
        ):
            mock_mgr.filter.return_value.order_by.return_value = []
            svc.list_issues_by_assignee(WS_ID, assignee, ctx_a)
            svc.list_issues_by_assignee(WS_ID, assignee, ctx_b)

        calls = mock_mgr.filter.call_args_list
        assert calls[0].kwargs["tenant_id"] == ctx_a.tenant_id
        assert calls[1].kwargs["tenant_id"] == ctx_b.tenant_id


# ---------------------------------------------------------------------------
# create_tracelink
# ---------------------------------------------------------------------------


class TestIssueCreateTracelink:
    def test_valid_link_type_delegates(self):
        mock_tls = MagicMock()
        mock_tls.create_trace_link.return_value = MagicMock()
        svc = IssueService(trace_link_service=mock_tls)
        ctx = _make_ctx(tenant_id=TENANT_ID)
        target_id = uuid.uuid4()

        with (
            patch("application.issue_service.Issue.objects") as mock_mgr,
            patch("application.issue_service.IssueService._set_tenant_context"),
        ):
            mock_mgr.filter.return_value.first.return_value = _make_issue()
            svc.create_tracelink(
                issue_id=ISSUE_ID,
                target_id=target_id,
                link_type="blocks",
                ctx=ctx,
            )

        mock_tls.create_trace_link.assert_called_once_with(
            source_id=ISSUE_ID,
            target_id=target_id,
            link_type="blocks",
            ctx=ctx,
        )

    def test_invalid_link_type_raises(self):
        svc = IssueService()
        ctx = _make_ctx()

        with patch("application.issue_service.IssueService._set_tenant_context"):
            with pytest.raises(ValidationError, match="Invalid Issue link type"):
                svc.create_tracelink(
                    issue_id=ISSUE_ID,
                    target_id=uuid.uuid4(),
                    link_type="threatens",  # Risk-type, invalid here
                    ctx=ctx,
                )

    def test_all_valid_link_types_accepted(self):
        for lt in ISSUE_LINK_TYPES:
            mock_tls = MagicMock()
            mock_tls.create_trace_link.return_value = MagicMock()
            svc = IssueService(trace_link_service=mock_tls)
            ctx = _make_ctx(tenant_id=TENANT_ID)

            with (
                patch("application.issue_service.Issue.objects") as mock_mgr,
                patch("application.issue_service.IssueService._set_tenant_context"),
            ):
                mock_mgr.filter.return_value.first.return_value = _make_issue()
                svc.create_tracelink(
                    issue_id=ISSUE_ID,
                    target_id=uuid.uuid4(),
                    link_type=lt,
                    ctx=ctx,
                )
