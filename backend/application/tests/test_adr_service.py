"""
Tests for COMP-AS-013 AdrService.

leaf_id : COMP-AS-013
req_id  : REQ-L1-029, REQ-L3-ADR-001..009

Static tests (no DB): CRUD delegation, workflow init, TraceLink creation,
audit entry, event emission, tenant isolation, validation errors.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch, call

import pytest

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.adr_service import AdrService, AdrDTO, AdrValidator
from application.models import Adr

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
ADR_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()


def _make_adr(**kwargs):
    """Return a MagicMock that looks like an Adr ORM instance."""
    adr = MagicMock(spec=Adr)
    adr.id = kwargs.get("id", ADR_ID)
    adr.workspace_id = kwargs.get("workspace_id", WS_ID)
    adr.tenant_id = kwargs.get("tenant_id", TENANT_ID)
    adr.title = kwargs.get("title", "Use REST over SOAP")
    adr.description = kwargs.get("description", "REST is simpler")
    adr.context = kwargs.get("context", "")
    adr.decision = kwargs.get("decision", "")
    adr.consequences = kwargs.get("consequences", "")
    adr.status = kwargs.get("status", "Draft")
    adr.version = kwargs.get("version", 1)
    return adr


# ---------------------------------------------------------------------------
# AdrValidator
# ---------------------------------------------------------------------------


class TestAdrValidator:
    def test_valid_create_passes(self):
        AdrValidator.validate_create(
            title="Use Event Sourcing", description="Details here"
        )

    def test_title_too_short_raises(self):
        with pytest.raises(ValidationError, match="at least 3"):
            AdrValidator.validate_create(title="AB", description="ok")

    def test_title_too_long_raises(self):
        with pytest.raises(ValidationError, match="200 characters"):
            AdrValidator.validate_create(title="x" * 201, description="ok")

    def test_description_too_long_raises(self):
        with pytest.raises(ValidationError, match="10,000"):
            AdrValidator.validate_create(title="Valid Title", description="x" * 10001)

    def test_validate_create_has_no_status_parameter(self):
        """Datenmodell-Konsolidierung Phase 1: status is not a create input
        anymore; a caller sending it gets a TypeError, not a ValidationError."""
        with pytest.raises(TypeError):
            AdrValidator.validate_create(
                title="Valid Title", description="ok", status="BadStatus"
            )


# ---------------------------------------------------------------------------
# AdrDTO
# ---------------------------------------------------------------------------


class TestAdrDTO:
    def test_from_orm_maps_fields(self):
        """Datenmodell-Konsolidierung: `status` is now supplied by the caller
        (resolved from the workflow engine), not read off the ORM row."""
        adr = _make_adr(decision="Use REST")
        dto = AdrDTO.from_orm(adr, status=adr.status)
        assert dto.id == adr.id
        assert dto.workspace_id == adr.workspace_id
        assert dto.title == adr.title
        assert dto.status == adr.status
        assert dto.version == adr.version
        # #373: `decision` is a genuine ADR field, distinct from `description`.
        assert dto.decision == "Use REST"


# ---------------------------------------------------------------------------
# create_adr
# ---------------------------------------------------------------------------


class TestCreateAdr:
    def test_creates_adr_and_emits_event(self):
        """create_adr persists, calls workflow init, audit, and event emission."""
        svc = AdrService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        created_adr = _make_adr()

        with (
            patch("application.adr_service.Adr.objects") as mock_mgr,
            patch("persistence.models.Tenant.objects") as mock_tenant,
            patch("persistence.models.Workspace.objects") as mock_ws,
            patch("persistence.models.Artifact.objects") as mock_artifact,
            patch("application.adr_service.AdrService._set_tenant_context"),
            patch("application.adr_service.AdrService._assert_write_permission"),
            patch("application.adr_service.AdrService._audit") as mock_audit,
            patch("application.adr_service.AdrService._emit_event") as mock_emit,
            patch("application.adr_service.AdrService._make_event", return_value=MagicMock()),
            patch("workflow.services.initialize_workflow_states") as mock_wf,
        ):
            mock_tenant.filter.return_value.first.return_value = MagicMock()
            mock_ws.filter.return_value.first.return_value = MagicMock()
            mock_artifact.create.return_value = MagicMock()
            mock_mgr.create.return_value = created_adr

            result = svc.create_adr(
                workspace_id=WS_ID,
                title="Use CQRS Pattern",
                description="Command Query Responsibility Segregation",
                ctx=ctx,
            )

        # REQ-L2-TE-020: backing Artifact is created before the ADR row.
        mock_artifact.create.assert_called_once()

        mock_mgr.create.assert_called_once()
        mock_wf.assert_called_once()
        mock_audit.assert_called_once_with(
            ctx=ctx, operation="create", entity_type="Adr", entity_id=created_adr.id
        )
        mock_emit.assert_called_once()
        assert result is created_adr

    def test_viewer_role_raises_permission_denied(self):
        """Viewer cannot create an ADR."""
        svc = AdrService()
        ctx = _make_ctx(roles=("viewer",))

        with pytest.raises(PermissionDeniedError):
            svc.create_adr(
                workspace_id=WS_ID,
                title="Valid Title",
                description="ok",
                ctx=ctx,
            )

    def test_invalid_title_raises_validation_error(self):
        """Short title is rejected before DB write."""
        svc = AdrService()
        ctx = _make_ctx()

        with (
            patch("application.adr_service.AdrService._set_tenant_context"),
            patch("application.adr_service.AdrService._assert_write_permission"),
        ):
            with pytest.raises(ValidationError, match="at least 3"):
                svc.create_adr(
                    workspace_id=WS_ID,
                    title="AB",
                    description="ok",
                    ctx=ctx,
                )

    def test_workflow_init_failure_is_swallowed(self):
        """Workflow init failure does not abort ADR creation."""
        svc = AdrService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        created_adr = _make_adr()

        with (
            patch("application.adr_service.Adr.objects") as mock_mgr,
            patch("persistence.models.Tenant.objects") as mock_tenant,
            patch("persistence.models.Workspace.objects") as mock_ws,
            patch("persistence.models.Artifact.objects") as mock_artifact,
            patch("application.adr_service.AdrService._set_tenant_context"),
            patch("application.adr_service.AdrService._assert_write_permission"),
            patch("application.adr_service.AdrService._audit"),
            patch("application.adr_service.AdrService._emit_event"),
            patch("application.adr_service.AdrService._make_event", return_value=MagicMock()),
            patch(
                "workflow.services.initialize_workflow_states",
                side_effect=RuntimeError("no definition"),
            ),
        ):
            mock_tenant.filter.return_value.first.return_value = MagicMock()
            mock_ws.filter.return_value.first.return_value = MagicMock()
            mock_artifact.create.return_value = MagicMock()
            mock_mgr.create.return_value = created_adr
            result = svc.create_adr(
                workspace_id=WS_ID,
                title="Valid Title",
                description="Description here",
                ctx=ctx,
            )

        assert result is created_adr

    def test_decision_field_persisted_on_create(self):
        """#373: `decision` is accepted as its own parameter and forwarded
        to Adr.objects.create — not conflated with `description`."""
        svc = AdrService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        created_adr = _make_adr()

        with (
            patch("application.adr_service.Adr.objects") as mock_mgr,
            patch("persistence.models.Tenant.objects") as mock_tenant,
            patch("persistence.models.Workspace.objects") as mock_ws,
            patch("persistence.models.Artifact.objects") as mock_artifact,
            patch("application.adr_service.AdrService._set_tenant_context"),
            patch("application.adr_service.AdrService._assert_write_permission"),
            patch("application.adr_service.AdrService._audit"),
            patch("application.adr_service.AdrService._emit_event"),
            patch("application.adr_service.AdrService._make_event", return_value=MagicMock()),
            patch("workflow.services.initialize_workflow_states"),
        ):
            mock_tenant.filter.return_value.first.return_value = MagicMock()
            mock_ws.filter.return_value.first.return_value = MagicMock()
            mock_artifact.create.return_value = MagicMock()
            mock_mgr.create.return_value = created_adr

            svc.create_adr(
                workspace_id=WS_ID,
                title="Use CQRS Pattern",
                description="Command Query Responsibility Segregation",
                ctx=ctx,
                context="High write throughput required",
                decision="Adopt CQRS with event sourcing",
                consequences="Higher operational complexity",
            )

        mock_mgr.create.assert_called_once()
        call_kwargs = mock_mgr.create.call_args.kwargs
        assert call_kwargs["decision"] == "Adopt CQRS with event sourcing"
        assert call_kwargs["description"] == "Command Query Responsibility Segregation"


# ---------------------------------------------------------------------------
# update_adr
# ---------------------------------------------------------------------------


class TestUpdateAdr:
    def test_updates_fields_and_increments_version(self):
        """update_adr patches changed fields and increments version atomically (REQ-L3-PL001-002)."""
        svc = AdrService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        existing_adr = _make_adr(version=1)
        existing_adr.save = MagicMock()
        # Simulate the DB-level F("version") + 1 that refresh_from_db would return.
        existing_adr.refresh_from_db = MagicMock(
            side_effect=lambda fields=None: setattr(existing_adr, "version", existing_adr.version + 1)
        )

        with (
            patch("application.adr_service.Adr.objects") as mock_mgr,
            patch("application.adr_service.AdrService._set_tenant_context"),
            patch("application.adr_service.AdrService._assert_write_permission"),
            patch("application.adr_service.AdrService._audit"),
            patch("application.adr_service.AdrService._emit_event"),
            patch("application.adr_service.AdrService._make_event", return_value=MagicMock()),
        ):
            mock_mgr.filter.return_value.first.return_value = existing_adr

            result = svc.update_adr(
                adr_id=ADR_ID,
                ctx=ctx,
                title="Updated Title",
            )

        assert result.title == "Updated Title"
        assert result.version == 2
        existing_adr.save.assert_called_once()
        # Verify the atomic update was issued and version was refreshed.
        mock_mgr.filter.return_value.update.assert_called_once()
        existing_adr.refresh_from_db.assert_called_once_with(fields=["version"])

    def test_not_found_raises(self):
        """update_adr raises NotFoundError when ADR does not exist."""
        svc = AdrService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        with (
            patch("application.adr_service.Adr.objects") as mock_mgr,
            patch("application.adr_service.AdrService._set_tenant_context"),
            patch("application.adr_service.AdrService._assert_write_permission"),
        ):
            mock_mgr.filter.return_value.first.return_value = None

            with pytest.raises(NotFoundError):
                svc.update_adr(adr_id=ADR_ID, ctx=ctx, title="New Title")

    def test_audit_entry_written_on_update(self):
        """update_adr writes an audit entry."""
        svc = AdrService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        existing_adr = _make_adr(version=2)
        existing_adr.save = MagicMock()

        with (
            patch("application.adr_service.Adr.objects") as mock_mgr,
            patch("application.adr_service.AdrService._set_tenant_context"),
            patch("application.adr_service.AdrService._assert_write_permission"),
            patch("application.adr_service.AdrService._audit") as mock_audit,
            patch("application.adr_service.AdrService._emit_event"),
            patch("application.adr_service.AdrService._make_event", return_value=MagicMock()),
        ):
            mock_mgr.filter.return_value.first.return_value = existing_adr
            svc.update_adr(adr_id=ADR_ID, ctx=ctx, description="New desc", change_reason="fix")

        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args.kwargs
        assert call_kwargs["operation"] == "update"
        assert call_kwargs["change_reason"] == "fix"

    def test_decision_field_updated(self):
        """#373: update_adr writes `decision` onto the ADR when supplied."""
        svc = AdrService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        existing_adr = _make_adr(version=1, decision="Old decision")
        existing_adr.save = MagicMock()
        existing_adr.refresh_from_db = MagicMock(
            side_effect=lambda fields=None: setattr(existing_adr, "version", existing_adr.version + 1)
        )

        with (
            patch("application.adr_service.Adr.objects") as mock_mgr,
            patch("application.adr_service.AdrService._set_tenant_context"),
            patch("application.adr_service.AdrService._assert_write_permission"),
            patch("application.adr_service.AdrService._audit"),
            patch("application.adr_service.AdrService._emit_event"),
            patch("application.adr_service.AdrService._make_event", return_value=MagicMock()),
        ):
            mock_mgr.filter.return_value.first.return_value = existing_adr

            result = svc.update_adr(
                adr_id=ADR_ID,
                ctx=ctx,
                decision="New decision",
            )

        assert result.decision == "New decision"


# ---------------------------------------------------------------------------
# transition_status — REQ-L3-ADR-005 supersedes TraceLink
# ---------------------------------------------------------------------------


class TestTransitionStatus:
    def test_supersede_with_successor_creates_decides_tracelink(self):
        """Transitioning to Superseded with superseded_by_id creates a
        'decides' TraceLink from the successor ADR to the superseded ADR."""
        from traceability.types import LinkType

        mock_tls = MagicMock()
        svc = AdrService(trace_link_service=mock_tls)
        ctx = _make_ctx(tenant_id=TENANT_ID)
        existing_adr = _make_adr(status="Approved")
        existing_adr.save = MagicMock()
        successor_id = uuid.uuid4()

        with (
            patch("application.adr_service.Adr.objects") as mock_mgr,
            patch("application.adr_service.AdrService._set_tenant_context"),
            patch("application.adr_service.AdrService._assert_write_permission"),
            patch("application.adr_service.AdrService._audit"),
            patch("application.workflow_facade.WorkflowFacade"),
            # _set_tenant_context is mocked above (no TenantContext ever set
            # on this thread), so the post-transition status resolution
            # (state_reader.current_state) must be mocked too.
            patch("application.adr_service.state_reader.current_state", return_value=None),
        ):
            mock_mgr.filter.return_value.first.return_value = existing_adr
            result = svc.transition_status(
                adr_id=ADR_ID,
                target_status=Adr.Status.SUPERSEDED,
                ctx=ctx,
                superseded_by_id=successor_id,
            )

        mock_tls.create_trace_link.assert_called_once_with(
            source_id=successor_id,
            target_id=ADR_ID,
            link_type=LinkType.DECIDES.value,
            ctx=ctx,
        )

    def test_supersede_without_successor_does_not_create_tracelink(self):
        """Transitioning to Superseded without superseded_by_id skips TraceLink creation."""
        mock_tls = MagicMock()
        svc = AdrService(trace_link_service=mock_tls)
        ctx = _make_ctx(tenant_id=TENANT_ID)
        existing_adr = _make_adr(status="Approved")
        existing_adr.save = MagicMock()

        with (
            patch("application.adr_service.Adr.objects") as mock_mgr,
            patch("application.adr_service.AdrService._set_tenant_context"),
            patch("application.adr_service.AdrService._assert_write_permission"),
            patch("application.adr_service.AdrService._audit"),
            patch("application.workflow_facade.WorkflowFacade"),
            # _set_tenant_context is mocked above (no TenantContext ever set
            # on this thread), so the post-transition status resolution
            # (state_reader.current_state) must be mocked too.
            patch("application.adr_service.state_reader.current_state", return_value=None),
        ):
            mock_mgr.filter.return_value.first.return_value = existing_adr
            svc.transition_status(
                adr_id=ADR_ID, target_status=Adr.Status.SUPERSEDED, ctx=ctx
            )

        mock_tls.create_trace_link.assert_not_called()

    def test_non_supersede_transition_does_not_create_tracelink(self):
        """superseded_by_id is ignored when target_status is not Superseded."""
        mock_tls = MagicMock()
        svc = AdrService(trace_link_service=mock_tls)
        ctx = _make_ctx(tenant_id=TENANT_ID)
        existing_adr = _make_adr(status="Draft")
        existing_adr.save = MagicMock()

        with (
            patch("application.adr_service.Adr.objects") as mock_mgr,
            patch("application.adr_service.AdrService._set_tenant_context"),
            patch("application.adr_service.AdrService._assert_write_permission"),
            patch("application.adr_service.AdrService._audit"),
            patch("application.workflow_facade.WorkflowFacade"),
            # _set_tenant_context is mocked above (no TenantContext ever set
            # on this thread), so the post-transition status resolution
            # (state_reader.current_state) must be mocked too.
            patch("application.adr_service.state_reader.current_state", return_value=None),
        ):
            mock_mgr.filter.return_value.first.return_value = existing_adr
            svc.transition_status(
                adr_id=ADR_ID,
                target_status=Adr.Status.IN_REVIEW,
                ctx=ctx,
                superseded_by_id=uuid.uuid4(),
            )

        mock_tls.create_trace_link.assert_not_called()

    def test_invalid_target_status_raises(self):
        svc = AdrService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        existing_adr = _make_adr()

        with (
            patch("application.adr_service.Adr.objects") as mock_mgr,
            patch("application.adr_service.AdrService._set_tenant_context"),
            patch("application.adr_service.AdrService._assert_write_permission"),
        ):
            mock_mgr.filter.return_value.first.return_value = existing_adr
            with pytest.raises(ValidationError, match="Invalid ADR status"):
                svc.transition_status(
                    adr_id=ADR_ID, target_status="NotAStatus", ctx=ctx
                )

    def test_not_found_raises(self):
        svc = AdrService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        with (
            patch("application.adr_service.Adr.objects") as mock_mgr,
            patch("application.adr_service.AdrService._set_tenant_context"),
            patch("application.adr_service.AdrService._assert_write_permission"),
        ):
            mock_mgr.filter.return_value.first.return_value = None
            with pytest.raises(NotFoundError):
                svc.transition_status(
                    adr_id=ADR_ID, target_status=Adr.Status.APPROVED, ctx=ctx
                )

    @pytest.mark.django_db
    def test_returned_instance_reports_the_new_state_not_the_frozen_column(
        self, te020_ctx, te020_workspace, te020_tenant
    ):
        """Datenmodell-Konsolidierung Phase 1: the engine no longer writes a
        ``status`` mirror, so ``adr.refresh_from_db()`` alone would leave the
        returned instance's ``.status`` at its stale, pre-transition column
        value. Must be corrected in memory before returning (same fix as
        IssueService.transition_status)."""
        from persistence.tenancy import TenantContext
        from workflow.services import create_default_workflow

        TenantContext.set_tenant(te020_tenant.id)
        try:
            create_default_workflow(
                workspace_id=te020_workspace.id,
                preset="adr_default",
                item_type="Adr",
                tenant_id=te020_tenant.id,
            )
        finally:
            TenantContext.clear_tenant()
        adr = AdrService().create_adr(
            workspace_id=te020_workspace.id,
            title="Adopt event sourcing",
            description="d",
            ctx=te020_ctx,
        )

        updated = AdrService().transition_status(
            adr_id=adr.id,
            target_status="In Review",
            ctx=te020_ctx,
        )

        assert updated.status == "In Review"
        assert Adr.objects.get(id=adr.id).status == "Draft"  # column frozen


# ---------------------------------------------------------------------------
# delete_adr
# ---------------------------------------------------------------------------


class TestDeleteAdr:
    """REQ-006: delete_adr() must soft-delete (status='Deleted'), not hard-delete."""

    def test_delete_adr_calls_outdate(self):
        """delete_adr routes the soft-delete through workflow.services.outdate()
        instead of writing status='Deleted' directly (REQ-006, Phase 0)."""
        svc = AdrService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        existing_adr = _make_adr()
        existing_adr.save = MagicMock()

        with (
            patch("application.adr_service.Adr.objects") as mock_mgr,
            patch("application.adr_service.AdrService._set_tenant_context"),
            patch("application.adr_service.AdrService._assert_write_permission"),
            patch("application.adr_service.AdrService._audit"),
            patch("application.adr_service.AdrService._emit_event"),
            patch("application.adr_service.AdrService._make_event", return_value=MagicMock()),
            patch("workflow.services.outdate") as mock_outdate,
        ):
            mock_mgr.filter.return_value.first.return_value = existing_adr
            svc.delete_adr(adr_id=ADR_ID, ctx=ctx)

        mock_outdate.assert_called_once_with(
            item_id=existing_adr.id,
            item_type="Adr",
            workspace_id=existing_adr.workspace_id,
            ctx=ctx,
            reason="deleted via adr.delete",
        )
        # Hard-delete must NOT be called, and status must NOT be written directly
        existing_adr.delete.assert_not_called()
        existing_adr.save.assert_not_called()

    def test_soft_delete_does_not_cascade_tracelinks(self):
        """delete_adr must NOT cascade-delete TraceLinks on soft-delete (REQ-006)."""
        mock_tls = MagicMock()
        svc = AdrService(trace_link_service=mock_tls)
        ctx = _make_ctx(tenant_id=TENANT_ID)
        existing_adr = _make_adr()
        existing_adr.save = MagicMock()

        with (
            patch("application.adr_service.Adr.objects") as mock_mgr,
            patch("application.adr_service.AdrService._set_tenant_context"),
            patch("application.adr_service.AdrService._assert_write_permission"),
            patch("application.adr_service.AdrService._audit"),
            patch("application.adr_service.AdrService._emit_event"),
            patch("application.adr_service.AdrService._make_event", return_value=MagicMock()),
            patch("workflow.services.outdate"),
        ):
            mock_mgr.filter.return_value.first.return_value = existing_adr
            svc.delete_adr(adr_id=ADR_ID, ctx=ctx)

        mock_tls.cascade_delete_trace_links.assert_not_called()

    def test_soft_delete_emits_deleted_event(self):
        """delete_adr still emits ARCHITECTURE_ELEMENT_DELETED event on soft-delete."""
        svc = AdrService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        existing_adr = _make_adr()
        existing_adr.save = MagicMock()

        with (
            patch("application.adr_service.Adr.objects") as mock_mgr,
            patch("application.adr_service.AdrService._set_tenant_context"),
            patch("application.adr_service.AdrService._assert_write_permission"),
            patch("application.adr_service.AdrService._audit"),
            patch("application.adr_service.AdrService._emit_event") as mock_emit,
            patch("application.adr_service.AdrService._make_event", return_value=MagicMock()),
            patch("workflow.services.outdate"),
        ):
            mock_mgr.filter.return_value.first.return_value = existing_adr
            svc.delete_adr(adr_id=ADR_ID, ctx=ctx)

        mock_emit.assert_called_once()

    def test_not_found_raises(self):
        """delete_adr raises NotFoundError for missing ADR."""
        svc = AdrService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        with (
            patch("application.adr_service.Adr.objects") as mock_mgr,
            patch("application.adr_service.AdrService._set_tenant_context"),
            patch("application.adr_service.AdrService._assert_write_permission"),
        ):
            mock_mgr.filter.return_value.first.return_value = None

            with pytest.raises(NotFoundError):
                svc.delete_adr(adr_id=ADR_ID, ctx=ctx)


# ---------------------------------------------------------------------------
# get_adr / list_adrs — tenant isolation
# ---------------------------------------------------------------------------


class TestGetAndListAdrs:
    def test_get_adr_not_found_raises(self):
        svc = AdrService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        with (
            patch("application.adr_service.Adr.objects") as mock_mgr,
            patch("application.adr_service.AdrService._set_tenant_context"),
        ):
            mock_mgr.filter.return_value.first.return_value = None
            with pytest.raises(NotFoundError):
                svc.get_adr(ADR_ID, ctx)

    def test_list_adrs_filters_by_tenant(self):
        """list_adrs filters by workspace_id AND tenant_id, excludes deleted (REQ-L3-ADR-006, REQ-006)."""
        svc = AdrService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        adr1 = _make_adr()

        with (
            patch("application.adr_service.Adr.objects") as mock_mgr,
            patch("application.adr_service.AdrService._set_tenant_context"),
        ):
            # Chain: filter() → exclude() → order_by() → list()
            mock_qs = MagicMock()
            mock_qs.exclude.return_value = mock_qs
            mock_qs.order_by.return_value = [adr1]
            mock_mgr.filter.return_value = mock_qs
            result = svc.list_adrs(WS_ID, ctx)

        # Verify tenant filter was applied
        mock_mgr.filter.assert_called_once_with(
            workspace_id=WS_ID, tenant_id=ctx.tenant_id
        )
        # REQ-006: deleted ADRs must be excluded by default
        mock_qs.exclude.assert_called_once()
        assert result == [adr1]

    def test_list_adrs_include_deleted(self):
        """list_adrs with include_deleted=True does not call .exclude() (REQ-006)."""
        svc = AdrService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        with (
            patch("application.adr_service.Adr.objects") as mock_mgr,
            patch("application.adr_service.AdrService._set_tenant_context"),
        ):
            # Chain: filter() → order_by() → list() (no exclude)
            mock_qs = MagicMock()
            mock_qs.order_by.return_value = [MagicMock()]
            mock_mgr.filter.return_value = mock_qs
            svc.list_adrs(WS_ID, ctx, include_deleted=True)

        # REQ-006: .exclude() must NOT be called when include_deleted=True
        mock_qs.exclude.assert_not_called()

    def test_tenant_isolation_different_tenants(self):
        """Two tenants get separate filter calls (REQ-L3-ADR-006)."""
        svc = AdrService()
        ctx_a = _make_ctx(tenant_id=uuid.uuid4())
        ctx_b = _make_ctx(tenant_id=uuid.uuid4())

        with (
            patch("application.adr_service.Adr.objects") as mock_mgr,
            patch("application.adr_service.AdrService._set_tenant_context"),
        ):
            # REQ-006: chain is filter() → exclude() → order_by() → list()
            mock_qs = MagicMock()
            mock_qs.exclude.return_value = mock_qs
            mock_qs.order_by.return_value = []
            mock_mgr.filter.return_value = mock_qs
            svc.list_adrs(WS_ID, ctx_a)
            svc.list_adrs(WS_ID, ctx_b)

        calls = mock_mgr.filter.call_args_list
        assert calls[0].kwargs["tenant_id"] == ctx_a.tenant_id
        assert calls[1].kwargs["tenant_id"] == ctx_b.tenant_id


# ---------------------------------------------------------------------------
# REQ-L2-TE-020: Artifact backing + ADR <-> ArchitectureElement TraceLinks
# DB-integration tests (real Postgres via docker-compose test DB).
# ---------------------------------------------------------------------------


@pytest.fixture
def te020_tenant():
    from persistence.models import Tenant

    return Tenant.objects.create(name="te020-tenant", slug="te020-tenant")


@pytest.fixture
def te020_user(te020_tenant):
    from persistence.models import User

    return User.objects.create(
        username="te020-user", email="te020@example.com", tenant=te020_tenant
    )


@pytest.fixture
def te020_workspace(te020_tenant):
    from persistence.models import Workspace
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(te020_tenant.id)
    try:
        return Workspace.objects.create(tenant=te020_tenant, name="te020-workspace")
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def te020_ctx(te020_user):
    from auth_tenancy.context import AuthContext

    return AuthContext(
        user_id=te020_user.id,
        tenant_id=te020_user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="te020-tenant",
    )


@pytest.mark.django_db
class TestAdrArtifactBackingAndTraceLinks:
    """REQ-L2-TE-020: ADR gets a backing Artifact and can be linked to an
    ArchitectureElement via a 'decides' TraceLink."""

    def test_create_adr_creates_backing_artifact(self, te020_ctx, te020_workspace):
        from persistence.models import Artifact

        svc = AdrService()
        adr = svc.create_adr(
            workspace_id=te020_workspace.id,
            title="Adopt hexagonal architecture",
            description="Ports and adapters everywhere.",
            ctx=te020_ctx,
        )

        assert adr.artifact_id is not None
        artifact = Artifact.objects.filter(id=adr.artifact_id).first()
        assert artifact is not None
        assert artifact.artifact_type == "Adr"
        assert str(artifact.workspace_id) == str(te020_workspace.id)

    def test_decides_tracelink_adr_to_architecture_element(
        self, te020_ctx, te020_workspace
    ):
        from application.architecture_service import ArchitectureService
        from application.trace_link_service import TraceLinkService
        from persistence.models import TraceLink
        from traceability.types import LinkType

        adr = AdrService().create_adr(
            workspace_id=te020_workspace.id,
            title="Use event sourcing",
            description="Append-only event log.",
            ctx=te020_ctx,
        )
        arch_el = ArchitectureService().create_architecture_element(
            workspace_id=te020_workspace.id,
            title="EventStore Component",
            ctx=te020_ctx,
        )

        link_svc = TraceLinkService()
        link = link_svc.create_trace_link(
            source_id=adr.id,
            target_id=arch_el.id,
            link_type=LinkType.DECIDES.value,
            ctx=te020_ctx,
        )

        # The link stores Artifact endpoints, resolved from the entity IDs.
        assert link.link_type == LinkType.DECIDES.value
        assert str(link.source_id) == str(adr.artifact_id)
        assert str(link.target_id) == str(arch_el.artifact_id)
        assert TraceLink.objects.filter(id=link.id).exists()

    def test_query_trace_links_from_both_endpoints(self, te020_ctx, te020_workspace):
        from application.architecture_service import ArchitectureService
        from application.trace_link_service import TraceLinkService
        from traceability.types import LinkType

        adr = AdrService().create_adr(
            workspace_id=te020_workspace.id,
            title="Choose Postgres",
            description="Relational store.",
            ctx=te020_ctx,
        )
        arch_el = ArchitectureService().create_architecture_element(
            workspace_id=te020_workspace.id,
            title="Persistence Layer",
            ctx=te020_ctx,
        )

        link_svc = TraceLinkService()
        link_svc.create_trace_link(
            source_id=adr.id,
            target_id=arch_el.id,
            link_type=LinkType.DECIDES.value,
            ctx=te020_ctx,
        )

        # Downstream from the ADR: the ArchitectureElement is reachable.
        from_adr = link_svc.query_trace_links(
            entity_id=adr.id, direction="downstream", ctx=te020_ctx
        )
        assert any(
            str(r.entity_id) == str(arch_el.artifact_id) for r in from_adr
        )

        # Upstream from the ArchitectureElement: the ADR is reachable.
        from_arch = link_svc.query_trace_links(
            entity_id=arch_el.id, direction="upstream", ctx=te020_ctx
        )
        assert any(
            str(r.entity_id) == str(adr.artifact_id) for r in from_arch
        )

    def test_delete_adr_soft_deletes_and_preserves_artifact(self, te020_ctx, te020_workspace):
        """REQ-006/Phase 0: delete_adr() soft-deletes via workflow.services.outdate(),
        preserves ADR + Artifact in DB, and moves the WorkflowItemState to "outdated"."""
        from persistence.models import Artifact
        from persistence.tenancy import TenantContext
        from workflow.models import WorkflowItemState
        from workflow.services import create_default_workflow

        # A default workflow definition must exist for "Adr" so that
        # create_adr()'s initialize_workflow_states() actually creates a
        # WorkflowItemState — otherwise outdate() has nothing to transition.
        TenantContext.set_tenant(te020_workspace.tenant_id)
        try:
            create_default_workflow(
                workspace_id=te020_workspace.id,
                preset="adr_default",
                item_type="Adr",
                tenant_id=te020_workspace.tenant_id,
            )
        finally:
            TenantContext.clear_tenant()

        svc = AdrService()
        adr = svc.create_adr(
            workspace_id=te020_workspace.id,
            title="Deprecate SOAP",
            description="Move to REST.",
            ctx=te020_ctx,
        )
        artifact_id = adr.artifact_id
        assert Artifact.objects.filter(id=artifact_id).exists()

        svc.delete_adr(adr.id, te020_ctx)

        # REQ-006: ADR row must still exist (soft-delete, not hard-delete)
        adr_in_db = Adr.objects.filter(id=adr.id).first()
        assert adr_in_db is not None, "ADR must remain in DB after soft-delete"

        # Phase 0: the workflow engine's state is now the source of truth.
        item_state = WorkflowItemState.objects.get(item_id=adr.id, item_type="Adr")
        assert item_state.current_state == "outdated"

        # REQ-006: backing Artifact must also remain in DB
        assert Artifact.objects.filter(id=artifact_id).exists(), "Artifact must remain in DB after soft-delete"

    def test_list_adrs_excludes_outdated_by_default(self, te020_ctx, te020_workspace):
        """Phase 0 regression: list_adrs() must exclude ADRs soft-deleted via
        workflow.services.outdate(), which mirrors "outdated" into Adr.status
        (not Adr.Status.DELETED)."""
        from persistence.tenancy import TenantContext
        from workflow.services import create_default_workflow

        TenantContext.set_tenant(te020_workspace.tenant_id)
        try:
            create_default_workflow(
                workspace_id=te020_workspace.id,
                preset="adr_default",
                item_type="Adr",
                tenant_id=te020_workspace.tenant_id,
            )
        finally:
            TenantContext.clear_tenant()

        svc = AdrService()
        kept = svc.create_adr(
            workspace_id=te020_workspace.id,
            title="Kept ADR",
            description="Stays visible.",
            ctx=te020_ctx,
        )
        deleted = svc.create_adr(
            workspace_id=te020_workspace.id,
            title="Deleted ADR",
            description="Gets soft-deleted.",
            ctx=te020_ctx,
        )

        svc.delete_adr(deleted.id, te020_ctx)

        results = svc.list_adrs(te020_workspace.id, te020_ctx)
        ids = {a.id for a in results}
        assert kept.id in ids
        assert deleted.id not in ids

        results_incl = svc.list_adrs(te020_workspace.id, te020_ctx, include_deleted=True)
        ids_incl = {a.id for a in results_incl}
        assert deleted.id in ids_incl
