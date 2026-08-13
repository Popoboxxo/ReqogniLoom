"""
Tests for COMP-AS-004 TestService.

leaf_id : COMP-AS-004
req_id  : REQ-L2-AS-005 (TestCase CRUD), REQ-L2-AS-025 (Coverage)

Coverage:
  - create_test_case: success, viewer denied, invalid test_type, tenant/workspace
                      not found, audit and event emission
  - update_test_case: success, not found
  - update_test_status: valid status accepted, invalid status raises ValidationError
  - delete_test_case: success, trace links preserved (GH-484), not found
  - get_test_case / list_test_cases: delegation
  - VALID_TEST_TYPES / VALID_EXECUTION_STATUSES constants
  - Tenant isolation: _set_tenant_context called
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.test_service import (
    TestService,
    VALID_EXECUTION_STATUSES,
    VALID_TEST_TYPES,
)


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
TC_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()


def _make_test_case(**kwargs):
    """Return a MagicMock shaped like a TestCase ORM instance."""
    tc = MagicMock()
    tc.id = kwargs.get("id", TC_ID)
    tc.title = kwargs.get("title", "Test Login Flow")
    tc.description = kwargs.get("description", "")
    tc.steps = kwargs.get("steps", [])
    artifact = MagicMock()
    artifact.id = uuid.uuid4()
    artifact.workspace_id = kwargs.get("workspace_id", WS_ID)
    tc.artifact = artifact
    tc.artifact_id = artifact.id
    return tc


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    """REQ-L2-AS-005: valid type/status sets."""

    def test_valid_test_types_contains_expected(self):
        """VALID_TEST_TYPES contains Unit, Integration, System, Acceptance."""
        assert {"Unit", "Integration", "System", "Acceptance"}.issubset(VALID_TEST_TYPES)

    def test_valid_execution_statuses_contains_expected(self):
        """VALID_EXECUTION_STATUSES contains Passed, Failed, Not Run."""
        assert {"Passed", "Failed", "Not Run"}.issubset(VALID_EXECUTION_STATUSES)


# ---------------------------------------------------------------------------
# create_test_case
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCreateTestCase:
    """REQ-L2-AS-005."""

    def test_viewer_cannot_create(self):
        """PermissionDeniedError for viewer context."""
        svc = TestService()
        ctx = _make_ctx(roles=("viewer",))

        with patch("application.test_service.ServiceBase._set_tenant_context"):
            with pytest.raises(PermissionDeniedError):
                svc.create_test_case(workspace_id=WS_ID, title="T", ctx=ctx)

    def test_invalid_test_type_raises_validation_error(self):
        """ValidationError when test_type is not in VALID_TEST_TYPES."""
        svc = TestService()
        ctx = _make_ctx()

        with (
            patch("application.test_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_service.ServiceBase._assert_write_permission"
            ),
        ):
            with pytest.raises(ValidationError, match="Invalid test_type"):
                svc.create_test_case(
                    workspace_id=WS_ID, title="T", ctx=ctx, test_type="BogusType"
                )

    def test_tenant_not_found_raises(self):
        """NotFoundError when tenant does not exist."""
        svc = TestService()
        ctx = _make_ctx()

        with (
            patch("application.test_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.test_service.Tenant",
                **{"objects.filter.return_value.first.return_value": None},
            ),
        ):
            with pytest.raises(NotFoundError, match="Tenant"):
                svc.create_test_case(workspace_id=WS_ID, title="T", ctx=ctx)

    def test_workspace_not_found_raises(self):
        """NotFoundError when workspace does not exist."""
        svc = TestService()
        ctx = _make_ctx()

        with (
            patch("application.test_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.test_service.Tenant",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.test_service.Workspace",
                **{"objects.filter.return_value.first.return_value": None},
            ),
        ):
            with pytest.raises(NotFoundError, match="Workspace"):
                svc.create_test_case(workspace_id=WS_ID, title="T", ctx=ctx)

    def test_create_success_returns_test_case(self):
        """create_test_case returns the ORM TestCase instance."""
        svc = TestService()
        ctx = _make_ctx()
        mock_tc = _make_test_case()
        mock_artifact = MagicMock()

        with (
            patch("application.test_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.test_service.Tenant",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.test_service.Workspace",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.test_service.Artifact.objects.create",
                return_value=mock_artifact,
            ),
            patch(
                "application.test_service.TestCase.objects.create",
                return_value=mock_tc,
            ),
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event"),
        ):
            result = svc.create_test_case(
                workspace_id=WS_ID, title="T", ctx=ctx, test_type="Integration"
            )

        assert result is mock_tc

    def test_audit_called_on_create(self):
        """_audit invoked with operation='create', entity_type='TestCase'."""
        svc = TestService()
        ctx = _make_ctx()
        mock_tc = _make_test_case()
        mock_artifact = MagicMock()

        with (
            patch("application.test_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.test_service.Tenant",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.test_service.Workspace",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.test_service.Artifact.objects.create",
                return_value=mock_artifact,
            ),
            patch(
                "application.test_service.TestCase.objects.create",
                return_value=mock_tc,
            ),
            patch.object(svc, "_audit") as mock_audit,
            patch.object(svc, "_emit_event"),
        ):
            svc.create_test_case(workspace_id=WS_ID, title="T", ctx=ctx)

        mock_audit.assert_called_once()
        kw = mock_audit.call_args.kwargs
        assert kw["operation"] == "create"
        assert kw["entity_type"] == "TestCase"


# ---------------------------------------------------------------------------
# update_test_case
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestUpdateTestCase:
    """REQ-L2-AS-005."""

    def test_not_found_raises(self):
        """NotFoundError when test case does not exist."""
        svc = TestService()
        ctx = _make_ctx()

        with (
            patch("application.test_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.test_service.TestCase.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(first=MagicMock(return_value=None))
                    )
                ),
            ),
        ):
            with pytest.raises(NotFoundError, match="TestCase"):
                svc.update_test_case(test_case_id=TC_ID, ctx=ctx)

    def test_update_title_success(self):
        """update_test_case changes title and saves."""
        svc = TestService()
        ctx = _make_ctx()
        mock_tc = _make_test_case()

        with (
            patch("application.test_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.test_service.TestCase.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_tc)
                        )
                    )
                ),
            ),
            # #269 finding 5 / REQ-L3-PL001-002 added an atomic version bump
            # via TestCase.objects.filter(...).update(...) — a second, real
            # query path that select_related() above does not cover. Mirrors
            # the equivalent patch in test_requirement_service.py.
            patch("application.test_service.TestCase.objects.filter"),
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event"),
        ):
            result = svc.update_test_case(
                test_case_id=TC_ID, ctx=ctx, title="New Title"
            )

        assert mock_tc.title == "New Title"
        mock_tc.save.assert_called_once()
        assert result is mock_tc


# ---------------------------------------------------------------------------
# update_test_status
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestUpdateTestStatus:
    """REQ-L2-AS-005: execution_status validation."""

    def test_invalid_status_raises_validation_error(self):
        """ValidationError when execution_status is not in VALID_EXECUTION_STATUSES."""
        svc = TestService()
        ctx = _make_ctx()

        with (
            patch("application.test_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_service.ServiceBase._assert_write_permission"
            ),
        ):
            with pytest.raises(ValidationError, match="Invalid execution_status"):
                svc.update_test_status(
                    test_case_id=TC_ID, execution_status="Pending", ctx=ctx
                )

    def test_valid_status_passed_accepted(self):
        """update_test_status accepts 'Passed' and saves with tag in description."""
        svc = TestService()
        ctx = _make_ctx()
        mock_tc = _make_test_case(description="original desc")

        with (
            patch("application.test_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.test_service.TestCase.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_tc)
                        )
                    )
                ),
            ),
            patch.object(svc, "_audit"),
        ):
            result = svc.update_test_status(
                test_case_id=TC_ID, execution_status="Passed", ctx=ctx
            )

        assert "[execution_status:Passed]" in mock_tc.description
        mock_tc.save.assert_called_once()

    def test_valid_status_failed_accepted(self):
        """update_test_status accepts 'Failed'."""
        svc = TestService()
        ctx = _make_ctx()
        mock_tc = _make_test_case()

        with (
            patch("application.test_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.test_service.TestCase.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_tc)
                        )
                    )
                ),
            ),
            patch.object(svc, "_audit"),
        ):
            svc.update_test_status(
                test_case_id=TC_ID, execution_status="Failed", ctx=ctx
            )

        assert "[execution_status:Failed]" in mock_tc.description

    def test_not_found_raises(self):
        """NotFoundError when test case is absent during status update."""
        svc = TestService()
        ctx = _make_ctx()

        with (
            patch("application.test_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.test_service.TestCase.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(first=MagicMock(return_value=None))
                    )
                ),
            ),
        ):
            with pytest.raises(NotFoundError, match="TestCase"):
                svc.update_test_status(
                    test_case_id=TC_ID, execution_status="Passed", ctx=ctx
                )


# ---------------------------------------------------------------------------
# delete_test_case
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDeleteTestCase:
    """REQ-L2-AS-005."""

    def test_delete_not_found_raises(self):
        """NotFoundError when test case to delete does not exist."""
        svc = TestService()
        ctx = _make_ctx()

        with (
            patch("application.test_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.test_service.TestCase.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(first=MagicMock(return_value=None))
                    )
                ),
            ),
        ):
            with pytest.raises(NotFoundError, match="TestCase"):
                svc.delete_test_case(test_case_id=TC_ID, ctx=ctx)

    def test_delete_does_not_cascade_trace_links_and_calls_outdate_not_hard_delete(
        self,
    ):
        """GH-484: cascade_delete_trace_links is NOT called anymore — the
        soft-delete only routes through workflow.services.outdate() instead
        of test_case.delete() (REQ-006/Phase 0), and TraceLinks survive so
        reactivate() (GH-443) restores them."""
        svc = TestService()
        ctx = _make_ctx()
        mock_tc = _make_test_case()

        with (
            patch("application.test_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.test_service.TestCase.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_tc)
                        )
                    )
                ),
            ),
            patch.object(
                svc._trace_link_service, "cascade_delete_trace_links"
            ) as mock_cascade,
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event"),
            patch("workflow.services.outdate") as mock_outdate,
        ):
            svc.delete_test_case(test_case_id=TC_ID, ctx=ctx)

        mock_cascade.assert_not_called()
        mock_outdate.assert_called_once_with(
            item_id=mock_tc.id,
            item_type="TestCase",
            workspace_id=mock_tc.artifact.workspace_id,
            ctx=ctx,
            reason="deleted via test.delete",
        )
        mock_tc.delete.assert_not_called()


# ---------------------------------------------------------------------------
# get_test_case / list_test_cases
# ---------------------------------------------------------------------------


class TestGetTestCase:
    def test_get_returns_test_case(self):
        """get_test_case returns the ORM instance."""
        svc = TestService()
        ctx = _make_ctx()
        mock_tc = _make_test_case()

        with (
            patch("application.test_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_service.TestCase.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_tc)
                        )
                    )
                ),
            ),
        ):
            result = svc.get_test_case(TC_ID, ctx)

        assert result is mock_tc

    def test_get_not_found_raises(self):
        """NotFoundError when test case is absent."""
        svc = TestService()
        ctx = _make_ctx()

        with (
            patch("application.test_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_service.TestCase.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(first=MagicMock(return_value=None))
                    )
                ),
            ),
        ):
            with pytest.raises(NotFoundError):
                svc.get_test_case(TC_ID, ctx)

    def test_list_returns_all(self):
        """list_test_cases returns all test cases for the workspace."""
        svc = TestService()
        ctx = _make_ctx()
        mock_list = [_make_test_case(), _make_test_case()]

        with (
            patch("application.test_service.ServiceBase._set_tenant_context"),
            patch(
                "application.test_service.TestCase.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            exclude=MagicMock(return_value=mock_list)
                        )
                    )
                ),
            ),
        ):
            result = svc.list_test_cases(WS_ID, ctx)

        assert result == mock_list


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    """REQ-L2-AS-022."""

    def test_set_tenant_context_called_on_get(self):
        """_set_tenant_context is called before every ORM access."""
        svc = TestService()
        ctx = _make_ctx(tenant_id=uuid.uuid4())
        mock_tc = _make_test_case()

        with (
            patch(
                "application.test_service.ServiceBase._set_tenant_context"
            ) as mock_stc,
            patch(
                "application.test_service.TestCase.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_tc)
                        )
                    )
                ),
            ),
        ):
            svc.get_test_case(TC_ID, ctx)

        mock_stc.assert_called_once_with(ctx)


# ---------------------------------------------------------------------------
# Regression (Issue #267, same root cause as RequirementService.list_requirements):
# GET /api/v1/test-cases/?search=<term> must filter on title/description/uid
# instead of being silently ignored.
# ---------------------------------------------------------------------------


@pytest.fixture
def tc_search_tenant():
    from persistence.models import Tenant

    return Tenant.objects.create(name="tc-search-tenant", slug="tc-search-tenant")


@pytest.fixture
def tc_search_user(tc_search_tenant):
    from persistence.models import User

    return User.objects.create(
        username="tc-search-user",
        email="tc-search@example.com",
        tenant=tc_search_tenant,
    )


@pytest.fixture
def tc_search_workspace(tc_search_tenant):
    from persistence.models import Workspace
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(tc_search_tenant.id)
    try:
        return Workspace.objects.create(
            tenant=tc_search_tenant, name="tc-search-workspace"
        )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def tc_search_ctx(tc_search_user):
    from auth_tenancy.context import AuthContext

    return AuthContext(
        user_id=tc_search_user.id,
        tenant_id=tc_search_user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="tc-search-tenant",
    )


@pytest.mark.django_db
class TestListTestCasesSearchFilter:
    def test_search_filters_by_title_case_insensitive(
        self, tc_search_ctx, tc_search_workspace
    ):
        svc = TestService()
        matching = svc.create_test_case(
            workspace_id=tc_search_workspace.id,
            title="Payment Gateway Test",
            ctx=tc_search_ctx,
        )
        other = svc.create_test_case(
            workspace_id=tc_search_workspace.id,
            title="Unrelated Test",
            ctx=tc_search_ctx,
        )

        results = svc.list_test_cases(
            tc_search_workspace.id, tc_search_ctx, search="payment gateway"
        )
        ids = {tc.id for tc in results}

        assert ids == {matching.id}
        assert other.id not in ids
