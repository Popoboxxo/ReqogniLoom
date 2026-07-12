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

    def test_invalid_status_raises(self):
        with pytest.raises(ValidationError, match="invalid"):
            AdrValidator.validate_create(
                title="Valid Title", description="ok", status="BadStatus"
            )

    def test_valid_statuses_all_pass(self):
        for status in Adr.Status.values:
            AdrValidator.validate_create(
                title="Valid Title", description="ok", status=status
            )


# ---------------------------------------------------------------------------
# AdrDTO
# ---------------------------------------------------------------------------


class TestAdrDTO:
    def test_from_orm_maps_fields(self):
        adr = _make_adr()
        dto = AdrDTO.from_orm(adr)
        assert dto.id == adr.id
        assert dto.workspace_id == adr.workspace_id
        assert dto.title == adr.title
        assert dto.status == adr.status
        assert dto.version == adr.version


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


# ---------------------------------------------------------------------------
# delete_adr
# ---------------------------------------------------------------------------


class TestDeleteAdr:
    def test_deletes_and_cascades_tracelinks(self):
        """delete_adr calls cascade_delete_trace_links and then deletes the ADR."""
        mock_tls = MagicMock()
        svc = AdrService(trace_link_service=mock_tls)
        ctx = _make_ctx(tenant_id=TENANT_ID)
        existing_adr = _make_adr()

        with (
            patch("application.adr_service.Adr.objects") as mock_mgr,
            patch("application.adr_service.AdrService._set_tenant_context"),
            patch("application.adr_service.AdrService._assert_write_permission"),
            patch("application.adr_service.AdrService._audit"),
            patch("application.adr_service.AdrService._emit_event"),
            patch("application.adr_service.AdrService._make_event", return_value=MagicMock()),
        ):
            mock_mgr.filter.return_value.first.return_value = existing_adr
            svc.delete_adr(adr_id=ADR_ID, ctx=ctx)

        mock_tls.cascade_delete_trace_links.assert_called_once_with(ADR_ID, ctx)
        existing_adr.delete.assert_called_once()

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
        """list_adrs filters by workspace_id AND tenant_id (REQ-L3-ADR-006)."""
        svc = AdrService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        adr1 = _make_adr()

        with (
            patch("application.adr_service.Adr.objects") as mock_mgr,
            patch("application.adr_service.AdrService._set_tenant_context"),
        ):
            mock_mgr.filter.return_value.order_by.return_value = [adr1]
            result = svc.list_adrs(WS_ID, ctx)

        # Verify tenant filter was applied
        mock_mgr.filter.assert_called_once_with(
            workspace_id=WS_ID, tenant_id=ctx.tenant_id
        )
        assert result == [adr1]

    def test_tenant_isolation_different_tenants(self):
        """Two tenants get separate filter calls (REQ-L3-ADR-006)."""
        svc = AdrService()
        ctx_a = _make_ctx(tenant_id=uuid.uuid4())
        ctx_b = _make_ctx(tenant_id=uuid.uuid4())

        with (
            patch("application.adr_service.Adr.objects") as mock_mgr,
            patch("application.adr_service.AdrService._set_tenant_context"),
        ):
            mock_mgr.filter.return_value.order_by.return_value = []
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

    def test_delete_adr_removes_backing_artifact(self, te020_ctx, te020_workspace):
        from persistence.models import Artifact

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

        assert not Adr.objects.filter(id=adr.id).exists()
        assert not Artifact.objects.filter(id=artifact_id).exists()
