"""
Tests for COMP-AS-003 ArchitectureService.

leaf_id : COMP-AS-003
req_id  : REQ-L2-AS-004 (ArchitectureElement CRUD with Versioning)

Coverage:
  - create_architecture_element: success (version=1), viewer denied,
    tenant/workspace not found, audit and event emission
  - update_architecture_element: success (version incremented),
    optimistic lock error on stale version, not found
  - delete_architecture_element: success, cascade trace link call, not found
  - get_architecture_element / list_architecture_elements: delegation
  - Tenant isolation: _set_tenant_context called on each operation
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.architecture_service import ArchitectureService
from application.base import (
    NotFoundError,
    OptimisticLockError,
    PermissionDeniedError,
    ValidationError,
)

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
ARCH_EL_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()


def _make_arch_el(**kwargs):
    """Return a MagicMock shaped like an ArchitectureElement ORM instance."""
    el = MagicMock()
    el.id = kwargs.get("id", ARCH_EL_ID)
    el.title = kwargs.get("title", "Component A")
    el.description = kwargs.get("description", "")
    el.element_type = kwargs.get("element_type", "component")
    el.version = kwargs.get("version", 1)
    artifact = MagicMock()
    artifact.id = uuid.uuid4()
    artifact.workspace_id = kwargs.get("workspace_id", WS_ID)
    el.artifact = artifact
    el.artifact_id = artifact.id
    return el


# ---------------------------------------------------------------------------
# create_architecture_element
# ---------------------------------------------------------------------------


class TestCreateArchitectureElement:
    """REQ-L2-AS-004."""

    def test_viewer_cannot_create(self):
        """PermissionDeniedError for viewer-only context."""
        svc = ArchitectureService()
        ctx = _make_ctx(roles=("viewer",))

        with patch("application.architecture_service.ServiceBase._set_tenant_context"):
            with pytest.raises(PermissionDeniedError):
                svc.create_architecture_element(
                    workspace_id=WS_ID, title="C", ctx=ctx
                )

    def test_tenant_not_found_raises(self):
        """NotFoundError when tenant does not exist."""
        svc = ArchitectureService()
        ctx = _make_ctx()

        with (
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.architecture_service.Tenant",
                **{"objects.filter.return_value.first.return_value": None},
            ),
        ):
            with pytest.raises(NotFoundError, match="Tenant"):
                svc.create_architecture_element(
                    workspace_id=WS_ID, title="C", ctx=ctx
                )

    def test_workspace_not_found_raises(self):
        """NotFoundError when workspace does not exist."""
        svc = ArchitectureService()
        ctx = _make_ctx()

        with (
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.architecture_service.Tenant",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.architecture_service.Workspace",
                **{"objects.filter.return_value.first.return_value": None},
            ),
        ):
            with pytest.raises(NotFoundError, match="Workspace"):
                svc.create_architecture_element(
                    workspace_id=WS_ID, title="C", ctx=ctx
                )

    def test_create_returns_element_with_version_1(self):
        """ArchitectureElement is created with version=1."""
        svc = ArchitectureService()
        ctx = _make_ctx()
        mock_el = _make_arch_el(version=1)
        mock_artifact = MagicMock()

        with (
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.architecture_service.Tenant",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.architecture_service.Workspace",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.architecture_service.Artifact.objects.create",
                return_value=mock_artifact,
            ),
            patch(
                "application.architecture_service.ArchitectureElement.objects.create",
                return_value=mock_el,
            ),
            # SysEng 2.0 I5: create now validates the single-root invariant for
            # roots too; stub the root scan so this stays a pure unit test.
            patch.object(
                ArchitectureElementInvariantValidator,
                "_get_existing_root",
                return_value=None,
            ),
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event"),
        ):
            result = svc.create_architecture_element(
                workspace_id=WS_ID, title="C", ctx=ctx
            )

        assert result is mock_el
        assert result.version == 1

    def test_audit_called_on_create(self):
        """_audit is called with operation='create' on success."""
        svc = ArchitectureService()
        ctx = _make_ctx()
        mock_el = _make_arch_el()
        mock_artifact = MagicMock()

        with (
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.architecture_service.Tenant",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.architecture_service.Workspace",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.architecture_service.Artifact.objects.create",
                return_value=mock_artifact,
            ),
            patch(
                "application.architecture_service.ArchitectureElement.objects.create",
                return_value=mock_el,
            ),
            patch.object(
                ArchitectureElementInvariantValidator,
                "_get_existing_root",
                return_value=None,
            ),
            patch.object(svc, "_audit") as mock_audit,
            patch.object(svc, "_emit_event"),
        ):
            svc.create_architecture_element(workspace_id=WS_ID, title="C", ctx=ctx)

        mock_audit.assert_called_once()
        kw = mock_audit.call_args.kwargs
        assert kw["operation"] == "create"
        assert kw["entity_type"] == "ArchitectureElement"


# ---------------------------------------------------------------------------
# update_architecture_element
# ---------------------------------------------------------------------------


class TestUpdateArchitectureElement:
    """REQ-L2-AS-004 — optimistic locking."""

    def test_not_found_raises(self):
        """NotFoundError when element does not exist."""
        svc = ArchitectureService()
        ctx = _make_ctx()

        with (
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.architecture_service.ArchitectureElement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(first=MagicMock(return_value=None))
                    )
                ),
            ),
        ):
            with pytest.raises(NotFoundError, match="ArchitectureElement"):
                svc.update_architecture_element(
                    arch_el_id=ARCH_EL_ID, ctx=ctx, expected_version=1
                )

    def test_stale_version_raises_optimistic_lock_error(self):
        """OptimisticLockError when expected_version does not match current."""
        svc = ArchitectureService()
        ctx = _make_ctx()
        mock_el = _make_arch_el(version=3)  # current = 3

        with (
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.architecture_service.ArchitectureElement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(first=MagicMock(return_value=mock_el))
                    )
                ),
            ),
        ):
            with pytest.raises(OptimisticLockError, match="Stale version"):
                svc.update_architecture_element(
                    arch_el_id=ARCH_EL_ID,
                    ctx=ctx,
                    expected_version=1,  # stale
                )

    def test_update_success_increments_version(self):
        """update_architecture_element calls filter().update() for version bump."""
        svc = ArchitectureService()
        ctx = _make_ctx()
        mock_el = _make_arch_el(version=1)

        mock_filter_qs = MagicMock()
        mock_filter_qs.update = MagicMock()

        with (
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.architecture_service.ArchitectureElement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_el)
                        )
                    )
                ),
            ),
            patch(
                "application.architecture_service.ArchitectureElement.objects.filter",
                return_value=mock_filter_qs,
            ),
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event"),
        ):
            result = svc.update_architecture_element(
                arch_el_id=ARCH_EL_ID,
                ctx=ctx,
                expected_version=1,
                title="Updated Title",
            )

        mock_filter_qs.update.assert_called_once()
        assert mock_el.title == "Updated Title"

    def test_update_without_expected_version_skips_lock_check(self):
        """Omitting expected_version skips optimistic lock but still bumps version."""
        svc = ArchitectureService()
        ctx = _make_ctx()
        mock_el = _make_arch_el(version=3)

        mock_filter_qs = MagicMock()
        mock_filter_qs.update = MagicMock()

        with (
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.architecture_service.ArchitectureElement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_el)
                        )
                    )
                ),
            ),
            patch(
                "application.architecture_service.ArchitectureElement.objects.filter",
                return_value=mock_filter_qs,
            ),
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event"),
        ):
            result = svc.update_architecture_element(
                arch_el_id=ARCH_EL_ID,
                ctx=ctx,
                title="Updated without lock",
            )

        # Lock check skipped; update still happens guarded by current version
        mock_filter_qs.update.assert_called_once()
        assert mock_el.title == "Updated without lock"

    def test_viewer_cannot_update(self):
        """PermissionDeniedError for viewer-only context."""
        svc = ArchitectureService()
        ctx = _make_ctx(roles=("viewer",))

        with patch("application.architecture_service.ServiceBase._set_tenant_context"):
            with pytest.raises(PermissionDeniedError):
                svc.update_architecture_element(
                    arch_el_id=ARCH_EL_ID, ctx=ctx, expected_version=1
                )


# ---------------------------------------------------------------------------
# delete_architecture_element
# ---------------------------------------------------------------------------


class TestDeleteArchitectureElement:
    """REQ-L2-AS-004, REQ-006: soft-delete replaces hard-delete for end-users."""

    def test_delete_not_found_raises(self):
        """NotFoundError when element to delete does not exist."""
        svc = ArchitectureService()
        ctx = _make_ctx()

        with (
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.architecture_service.ArchitectureElement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(first=MagicMock(return_value=None))
                    )
                ),
            ),
        ):
            with pytest.raises(NotFoundError, match="ArchitectureElement"):
                svc.delete_architecture_element(arch_el_id=ARCH_EL_ID, ctx=ctx)

    def test_delete_calls_outdate(self):
        """REQ-006/Phase 0: delete_architecture_element routes the soft-delete
        through workflow.services.outdate(), does NOT hard-delete."""
        svc = ArchitectureService()
        ctx = _make_ctx()
        mock_el = _make_arch_el()
        mock_el.save = MagicMock()

        with (
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.architecture_service.ArchitectureElement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_el)
                        )
                    )
                ),
            ),
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event"),
            patch("workflow.services.outdate") as mock_outdate,
        ):
            svc.delete_architecture_element(arch_el_id=ARCH_EL_ID, ctx=ctx)

        mock_outdate.assert_called_once_with(
            item_id=mock_el.id,
            item_type="ArchitectureElement",
            workspace_id=mock_el.artifact.workspace_id,
            ctx=ctx,
            reason="deleted via architecture.delete",
        )
        mock_el.delete.assert_not_called()
        mock_el.save.assert_not_called()

    def test_soft_delete_does_not_cascade_tracelinks(self):
        """REQ-006: soft-delete must NOT cascade-delete TraceLinks (preserve audit trail)."""
        svc = ArchitectureService()
        ctx = _make_ctx()
        mock_el = _make_arch_el()
        mock_el.save = MagicMock()

        with (
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.architecture_service.ArchitectureElement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_el)
                        )
                    )
                ),
            ),
            patch.object(
                svc._trace_link_service, "cascade_delete_trace_links"
            ) as mock_cascade,
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event"),
            patch("workflow.services.outdate"),
        ):
            svc.delete_architecture_element(arch_el_id=ARCH_EL_ID, ctx=ctx)

        mock_cascade.assert_not_called()


# ---------------------------------------------------------------------------
# get / list
# ---------------------------------------------------------------------------


class TestGetArchitectureElement:
    def test_get_returns_element(self):
        """get_architecture_element returns the ORM instance."""
        svc = ArchitectureService()
        ctx = _make_ctx()
        mock_el = _make_arch_el()

        with (
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ArchitectureElement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_el)
                        )
                    )
                ),
            ),
            patch("workflow.services.outdated_item_ids", return_value=[]),
        ):
            result = svc.get_architecture_element(ARCH_EL_ID, ctx)

        assert result is mock_el

    def test_get_not_found_raises(self):
        """NotFoundError when element is absent."""
        svc = ArchitectureService()
        ctx = _make_ctx()

        with (
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ArchitectureElement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(first=MagicMock(return_value=None))
                    )
                ),
            ),
        ):
            with pytest.raises(NotFoundError):
                svc.get_architecture_element(ARCH_EL_ID, ctx)

    def test_get_raises_not_found_when_outdated(self):
        """REQ-006: get_architecture_element treats soft-deleted (outdated) elements as not found."""
        svc = ArchitectureService()
        ctx = _make_ctx()
        mock_el = _make_arch_el()

        with (
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ArchitectureElement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_el)
                        )
                    )
                ),
            ),
            patch("workflow.services.outdated_item_ids", return_value=[mock_el.id]),
        ):
            with pytest.raises(NotFoundError):
                svc.get_architecture_element(ARCH_EL_ID, ctx)

    def test_list_returns_all_elements(self):
        """list_architecture_elements returns active elements, excludes deleted (REQ-006)."""
        svc = ArchitectureService()
        ctx = _make_ctx()
        mock_elements = [_make_arch_el(), _make_arch_el()]

        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.exclude.return_value = mock_elements

        with (
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ArchitectureElement.objects.select_related",
                return_value=mock_qs,
            ),
            patch(
                "workflow.models.WorkflowItemState.objects.filter",
                return_value=MagicMock(values_list=MagicMock(return_value=[])),
            ),
        ):
            result = svc.list_architecture_elements(WS_ID, ctx)

        # Phase 0: ArchitectureElement is not wired into _STATUS_MIRROR_MODELS,
        # so the default filter excludes ids whose WorkflowItemState is
        # "outdated" (id__in=<outdated ids>), instead of a lifecycle_status field.
        mock_qs.exclude.assert_called_once()
        assert "id__in" in mock_qs.exclude.call_args.kwargs
        assert result == mock_elements

    def test_list_include_deleted_skips_exclude(self):
        """REQ-006: include_deleted=True disables the deleted exclusion filter."""
        svc = ArchitectureService()
        ctx = _make_ctx()
        mock_elements = [_make_arch_el()]

        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_elements

        with (
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ArchitectureElement.objects.select_related",
                return_value=mock_qs,
            ),
        ):
            result = svc.list_architecture_elements(WS_ID, ctx, include_deleted=True)

        # .exclude() must NOT be called when include_deleted=True
        mock_qs.exclude.assert_not_called()


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    """REQ-L2-AS-022."""

    def test_set_tenant_context_called_on_get(self):
        """_set_tenant_context is called before the ORM query."""
        svc = ArchitectureService()
        ctx = _make_ctx(tenant_id=uuid.uuid4())
        mock_el = _make_arch_el()

        with (
            patch(
                "application.architecture_service.ServiceBase._set_tenant_context"
            ) as mock_stc,
            patch(
                "application.architecture_service.ArchitectureElement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_el)
                        )
                    )
                ),
            ),
            patch("workflow.services.outdated_item_ids", return_value=[]),
        ):
            svc.get_architecture_element(ARCH_EL_ID, ctx)

        mock_stc.assert_called_once_with(ctx)


# ---------------------------------------------------------------------------
# element_type validation (Bug 4 — "banane" fix)
# ---------------------------------------------------------------------------


class TestElementTypeValidation:
    """REQ-L2-AS-004 — element_type must be one of the 5 enum values."""

    # -- helpers to set up the standard mock chain for create --

    @staticmethod
    def _patch_create_chain(svc):
        """Return a context-manager stack that mocks all create dependencies."""
        from unittest.mock import patch, MagicMock

        return list((
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.architecture_service.Tenant",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.architecture_service.Workspace",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.architecture_service.Artifact.objects.create",
                return_value=MagicMock(),
            ),
            patch(
                "application.architecture_service.ArchitectureElement.objects.create",
                side_effect=lambda **kw: _make_arch_el(
                    element_type=kw.get("element_type", "component")
                ),
            ),
            # SysEng 2.0 I5: create validates the single-root invariant even for
            # roots — stub the root scan so element_type tests stay pure units.
            patch.object(
                ArchitectureElementInvariantValidator,
                "_get_existing_root",
                return_value=None,
            ),
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event"),
        ))

    def test_create_with_all_valid_element_types(self):
        """Each of the 5 ElementType values is accepted and stored lowercase."""
        from persistence.models import ElementType

        for etype in ElementType.values:
            svc = ArchitectureService()
            ctx = _make_ctx()
            patches = self._patch_create_chain(svc)

            # Enter all patches
            cms = [p.start() for p in patches]
            try:
                result = svc.create_architecture_element(
                    workspace_id=WS_ID,
                    title=f"Test {etype}",
                    ctx=ctx,
                    element_type=etype,
                )
                assert result.element_type == etype
            finally:
                for p in patches:
                    p.stop()

    def test_create_normalizes_pascal_case_to_lowercase(self):
        """Legacy PascalCase values like 'Component' are normalized to 'component'."""
        svc = ArchitectureService()
        ctx = _make_ctx()
        patches = self._patch_create_chain(svc)

        # Override the create side_effect to capture the actual kwargs
        from unittest.mock import MagicMock

        captured = {}

        def capture_create(**kw):
            captured.update(kw)
            return _make_arch_el(element_type=kw.get("element_type", "component"))

        patches[5] = patch(
            "application.architecture_service.ArchitectureElement.objects.create",
            side_effect=capture_create,
        )

        cms = [p.start() for p in patches]
        try:
            svc.create_architecture_element(
                workspace_id=WS_ID,
                title="PascalCase Test",
                ctx=ctx,
                element_type="Component",  # PascalCase → should be normalized
            )
            assert captured["element_type"] == "component"
        finally:
            for p in patches:
                p.stop()

    def test_create_with_custom_element_type_is_accepted(self):
        """REQ-006 (D5): free-vocabulary element_type like 'banane' is accepted, not rejected."""
        svc = ArchitectureService()
        ctx = _make_ctx()
        patches = self._patch_create_chain(svc)

        captured = {}

        def capture_create(**kw):
            captured.update(kw)
            return _make_arch_el(element_type=kw.get("element_type", "component"))

        patches[5] = patch(
            "application.architecture_service.ArchitectureElement.objects.create",
            side_effect=capture_create,
        )

        cms = [p.start() for p in patches]
        try:
            svc.create_architecture_element(
                workspace_id=WS_ID,
                title="Custom Type",
                ctx=ctx,
                element_type="banane",
            )
            assert captured["element_type"] == "banane"
        finally:
            for p in patches:
                p.stop()

    def test_create_with_empty_string_defaults_to_component(self):
        """REQ-006 (D5): empty string element_type falls back to the default COMPONENT type."""
        from persistence.models import ElementType

        svc = ArchitectureService()
        ctx = _make_ctx()
        patches = self._patch_create_chain(svc)

        captured = {}

        def capture_create(**kw):
            captured.update(kw)
            return _make_arch_el(element_type=kw.get("element_type", "component"))

        patches[5] = patch(
            "application.architecture_service.ArchitectureElement.objects.create",
            side_effect=capture_create,
        )

        cms = [p.start() for p in patches]
        try:
            svc.create_architecture_element(
                workspace_id=WS_ID,
                title="Empty",
                ctx=ctx,
                element_type="",
            )
            assert captured["element_type"] == ElementType.COMPONENT
        finally:
            for p in patches:
                p.stop()

    def test_update_with_valid_element_type(self):
        """update_architecture_element accepts valid element_type values."""
        svc = ArchitectureService()
        ctx = _make_ctx()
        mock_el = _make_arch_el(version=1, element_type="component")

        mock_filter_qs = MagicMock()
        mock_filter_qs.update = MagicMock()

        with (
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.architecture_service.ArchitectureElement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(first=MagicMock(return_value=mock_el))
                    )
                ),
            ),
            patch(
                "application.architecture_service.ArchitectureElement.objects.filter",
                return_value=mock_filter_qs,
            ),
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event"),
        ):
            result = svc.update_architecture_element(
                arch_el_id=ARCH_EL_ID,
                ctx=ctx,
                expected_version=1,
                element_type="subsystem",
            )

        assert mock_el.element_type == "subsystem"

    def test_update_with_custom_element_type_is_accepted(self):
        """REQ-006 (D5): update accepts free-vocabulary element_type like 'banane'."""
        svc = ArchitectureService()
        ctx = _make_ctx()
        mock_el = _make_arch_el(version=1)

        mock_filter_qs = MagicMock()
        mock_filter_qs.update = MagicMock()

        with (
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.architecture_service.ArchitectureElement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(first=MagicMock(return_value=mock_el))
                    )
                ),
            ),
            patch(
                "application.architecture_service.ArchitectureElement.objects.filter",
                return_value=mock_filter_qs,
            ),
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event"),
        ):
            svc.update_architecture_element(
                arch_el_id=ARCH_EL_ID,
                ctx=ctx,
                expected_version=1,
                element_type="banane",
            )

        assert mock_el.element_type == "banane"

    def test_update_normalizes_pascal_case_element_type(self):
        """update_architecture_element normalizes PascalCase to lowercase."""
        svc = ArchitectureService()
        ctx = _make_ctx()
        mock_el = _make_arch_el(version=1, element_type="component")

        mock_filter_qs = MagicMock()
        mock_filter_qs.update = MagicMock()

        with (
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.architecture_service.ArchitectureElement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(first=MagicMock(return_value=mock_el))
                    )
                ),
            ),
            patch(
                "application.architecture_service.ArchitectureElement.objects.filter",
                return_value=mock_filter_qs,
            ),
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event"),
        ):
            svc.update_architecture_element(
                arch_el_id=ARCH_EL_ID,
                ctx=ctx,
                expected_version=1,
                element_type="Layer",  # PascalCase → normalized
            )

        assert mock_el.element_type == "layer"

    def test_default_element_type_is_component(self):
        """create_architecture_element defaults to 'component' when not specified."""
        svc = ArchitectureService()
        ctx = _make_ctx()
        patches = self._patch_create_chain(svc)

        from unittest.mock import MagicMock

        captured = {}

        def capture_create(**kw):
            captured.update(kw)
            return _make_arch_el(element_type=kw.get("element_type", "component"))

        patches[5] = patch(
            "application.architecture_service.ArchitectureElement.objects.create",
            side_effect=capture_create,
        )

        cms = [p.start() for p in patches]
        try:
            svc.create_architecture_element(
                workspace_id=WS_ID,
                title="Default Type",
                ctx=ctx,
                # element_type not specified → should default to "component"
            )
            assert captured["element_type"] == "component"
        finally:
            for p in patches:
                p.stop()


# ---------------------------------------------------------------------------
# Invariant validator I1-I4 with rigor gating (REQ-L1-044)
# ---------------------------------------------------------------------------

import contextlib  # noqa: E402  — section-local imports for REQ-L1-044 tests

from application.validators import (  # noqa: E402
    ALL_INVARIANTS,
    ArchitectureElementInvariantValidator,
    RIGOR_INVARIANT_PRESETS,
)


class TestRigorInvariantGating:
    """REQ-L1-044: invariant sets are gated by rigor preset tier."""

    def test_default_rigor_preset_mapping(self):
        """Minimal={I3,I5}, Standard={I1,I2,I3,I5}, Extended=all incl. I4/I5."""
        assert RIGOR_INVARIANT_PRESETS["minimal"] == frozenset({"I3", "I5"})
        assert RIGOR_INVARIANT_PRESETS["standard"] == frozenset(
            {"I1", "I2", "I3", "I5"}
        )
        assert RIGOR_INVARIANT_PRESETS["extended"] == ALL_INVARIANTS

    def test_for_tier_builds_gated_validator(self):
        v = ArchitectureElementInvariantValidator.for_tier("minimal")
        assert v.is_enabled("I3")
        assert not v.is_enabled("I1")
        assert not v.is_enabled("I2")
        assert not v.is_enabled("I4")

    def test_for_tier_unknown_falls_back_to_standard(self):
        v = ArchitectureElementInvariantValidator.for_tier("my-custom-tier")
        assert v.is_enabled("I1") and v.is_enabled("I2") and v.is_enabled("I3")
        assert not v.is_enabled("I4")

    def test_for_workspace_resolves_tier_via_feature_gate(self):
        preset = MagicMock()
        preset.tier = "extended"
        gate = MagicMock()
        gate.get_preset.return_value = preset
        with patch("presets.gate.get_gate_service", return_value=gate):
            v = ArchitectureElementInvariantValidator.for_workspace(WS_ID)
        gate.get_preset.assert_called_once_with(str(WS_ID))
        assert v.is_enabled("I4")

    def test_for_workspace_falls_back_to_minimal_on_resolution_error(self):
        with patch(
            "presets.gate.get_gate_service", side_effect=RuntimeError("db down")
        ):
            v = ArchitectureElementInvariantValidator.for_workspace(WS_ID)
        assert v.is_enabled("I3")
        assert not v.is_enabled("I1")


class TestInvariantI1CycleDetection:
    """REQ-L1-044 I1: no circular parent references (standard/extended)."""

    def test_self_parent_raises(self):
        v = ArchitectureElementInvariantValidator.for_tier("standard")
        el_id = uuid.uuid4()
        with pytest.raises(ValidationError, match=r"\[I1\]"):
            v.check_i1(element_id=el_id, parent_id=el_id)

    def test_indirect_cycle_raises(self):
        """A -> C, where C.parent=B and B.parent=A closes a cycle."""
        a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        chain = {
            c: MagicMock(parent_id=b),
            b: MagicMock(parent_id=a),
        }
        v = ArchitectureElementInvariantValidator.for_tier("standard")
        with patch.object(
            ArchitectureElementInvariantValidator,
            "_get_element",
            side_effect=lambda eid: chain.get(eid),
        ):
            with pytest.raises(ValidationError, match=r"\[I1\]"):
                v.check_i1(element_id=a, parent_id=c)

    def test_acyclic_chain_passes(self):
        a, b, root = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        chain = {
            b: MagicMock(parent_id=root),
            root: MagicMock(parent_id=None),
        }
        v = ArchitectureElementInvariantValidator.for_tier("standard")
        with patch.object(
            ArchitectureElementInvariantValidator,
            "_get_element",
            side_effect=lambda eid: chain.get(eid),
        ):
            v.check_i1(element_id=a, parent_id=b)  # must not raise

    def test_i1_skipped_on_minimal(self):
        v = ArchitectureElementInvariantValidator.for_tier("minimal")
        el_id = uuid.uuid4()
        v.check_i1(element_id=el_id, parent_id=el_id)  # must not raise


class TestInvariantI2LevelOrdering:
    """REQ-L1-044 I2: parent.level < child.level (standard/extended)."""

    @staticmethod
    def _element(level, el_id=None):
        el = MagicMock()
        el.id = el_id or uuid.uuid4()
        el.get_level = MagicMock(return_value=level)
        return el

    def test_child_level_2_with_parent_level_5_raises(self):
        v = ArchitectureElementInvariantValidator.for_tier("standard")
        with pytest.raises(ValidationError, match=r"\[I2\]"):
            v.check_i2(self._element(2), self._element(5))

    def test_equal_levels_raise(self):
        v = ArchitectureElementInvariantValidator.for_tier("extended")
        with pytest.raises(ValidationError, match=r"\[I2\]"):
            v.check_i2(self._element(1), self._element(1))

    def test_valid_ordering_passes(self):
        v = ArchitectureElementInvariantValidator.for_tier("standard")
        v.check_i2(self._element(2), self._element(1))  # must not raise

    def test_i2_skipped_on_minimal(self):
        v = ArchitectureElementInvariantValidator.for_tier("minimal")
        v.check_i2(self._element(2), self._element(5))  # must not raise

    def test_i2_skipped_on_create_path_without_element(self):
        v = ArchitectureElementInvariantValidator.for_tier("standard")
        v.check_i2(None, self._element(5))  # must not raise


class TestInvariantI3DanglingReferences:
    """REQ-L1-044 I3: parent must exist in the same workspace (all tiers)."""

    @pytest.mark.parametrize("tier", ["minimal", "standard", "extended"])
    def test_dangling_parent_raises_on_all_tiers(self, tier):
        v = ArchitectureElementInvariantValidator.for_tier(tier)
        with patch.object(
            ArchitectureElementInvariantValidator, "_get_element", return_value=None
        ):
            with pytest.raises(ValidationError, match=r"\[I3\]"):
                v.check_i3(uuid.uuid4())

    def test_cross_workspace_parent_raises(self):
        parent = MagicMock()
        parent.artifact.workspace_id = uuid.uuid4()
        v = ArchitectureElementInvariantValidator.for_tier("minimal")
        with patch.object(
            ArchitectureElementInvariantValidator, "_get_element", return_value=parent
        ):
            with pytest.raises(ValidationError, match=r"\[I3\].*Cross-workspace"):
                v.check_i3(uuid.uuid4(), workspace_id=uuid.uuid4())

    def test_valid_parent_is_returned_for_reuse(self):
        ws_id = uuid.uuid4()
        parent = MagicMock()
        parent.artifact.workspace_id = ws_id
        v = ArchitectureElementInvariantValidator.for_tier("extended")
        with patch.object(
            ArchitectureElementInvariantValidator, "_get_element", return_value=parent
        ):
            assert v.check_i3(uuid.uuid4(), workspace_id=ws_id) is parent

    def test_none_parent_is_always_valid_root(self):
        v = ArchitectureElementInvariantValidator.for_tier("extended")
        assert v.check_i3(None) is None


class TestInvariantI4AllocationStructure:
    """REQ-L1-044 I4: allocated-to must not target an ancestor (extended)."""

    @staticmethod
    def _element(el_id=None, parent_id=None):
        el = MagicMock()
        el.id = el_id or uuid.uuid4()
        el.parent_id = parent_id
        return el

    def test_allocation_to_direct_parent_raises_on_extended(self):
        target = self._element()
        source = self._element(parent_id=target.id)
        v = ArchitectureElementInvariantValidator.for_tier("extended")
        with pytest.raises(ValidationError, match=r"\[I4\]"):
            v.check_i4(source, target)

    def test_allocation_to_transitive_ancestor_raises(self):
        target = self._element()
        mid_id = uuid.uuid4()
        source = self._element(parent_id=mid_id)
        chain = {mid_id: self._element(el_id=mid_id, parent_id=target.id)}
        v = ArchitectureElementInvariantValidator.for_tier("extended")
        with patch.object(
            ArchitectureElementInvariantValidator,
            "_get_element",
            side_effect=lambda eid: chain.get(eid),
        ):
            with pytest.raises(ValidationError, match=r"\[I4\]"):
                v.check_i4(source, target)

    def test_allocation_to_unrelated_element_passes(self):
        v = ArchitectureElementInvariantValidator.for_tier("extended")
        v.check_i4(self._element(parent_id=None), self._element())  # no raise

    @pytest.mark.parametrize("tier", ["minimal", "standard"])
    def test_i4_skipped_below_extended(self, tier):
        target = self._element()
        source = self._element(parent_id=target.id)
        v = ArchitectureElementInvariantValidator.for_tier(tier)
        v.check_i4(source, target)  # must not raise


class TestInvariantServiceIntegration:
    """REQ-L1-044: ArchitectureService enforces invariants on CRUD."""

    @staticmethod
    def _create_patches():
        return [
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.architecture_service.Tenant",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.architecture_service.Workspace",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.architecture_service.Artifact.objects.create",
                return_value=MagicMock(),
            ),
            patch(
                "application.architecture_service.ArchitectureElement.objects.create",
                return_value=_make_arch_el(version=1),
            ),
            # Index 6 — issue #366: create_architecture_element resolves the
            # parent element's backing Artifact id before writing the Artifact
            # row. Appended (not inserted) so the [:5] / [5] slices above keep
            # their meaning.
            patch(
                "application.architecture_service.ArchitectureElement.objects.filter",
                return_value=MagicMock(
                    **{"values_list.return_value.first.return_value": None}
                ),
            ),
        ]

    def test_create_with_parent_runs_validator(self):
        svc = ArchitectureService()
        ctx = _make_ctx()
        parent_id = uuid.uuid4()

        with contextlib.ExitStack() as stack:
            for p in self._create_patches():
                stack.enter_context(p)
            mock_cls = stack.enter_context(
                patch(
                    "application.architecture_service."
                    "ArchitectureElementInvariantValidator"
                )
            )
            stack.enter_context(patch.object(svc, "_audit"))
            stack.enter_context(patch.object(svc, "_emit_event"))
            svc.create_architecture_element(
                workspace_id=WS_ID, title="C", ctx=ctx, parent_id=parent_id
            )

        mock_cls.for_workspace.assert_called_once_with(WS_ID)
        mock_cls.for_workspace.return_value.validate_parent_assignment.assert_called_once_with(
            parent_id=parent_id, workspace_id=WS_ID
        )

    def test_create_root_runs_validator_for_single_root_invariant(self):
        """SysEng 2.0 I5: creating a root (no parent) still runs the validator
        so a second root in the workspace is rejected."""
        svc = ArchitectureService()
        ctx = _make_ctx()

        with contextlib.ExitStack() as stack:
            for p in self._create_patches():
                stack.enter_context(p)
            mock_cls = stack.enter_context(
                patch(
                    "application.architecture_service."
                    "ArchitectureElementInvariantValidator"
                )
            )
            stack.enter_context(patch.object(svc, "_audit"))
            stack.enter_context(patch.object(svc, "_emit_event"))
            svc.create_architecture_element(workspace_id=WS_ID, title="C", ctx=ctx)

        mock_cls.for_workspace.assert_called_once_with(WS_ID)
        mock_cls.for_workspace.return_value.validate_parent_assignment.assert_called_once_with(
            parent_id=None, workspace_id=WS_ID
        )

    def test_create_with_invalid_parent_raises_validation_error(self):
        """I3 violation aborts creation before the element row is written."""
        svc = ArchitectureService()
        ctx = _make_ctx()

        with contextlib.ExitStack() as stack:
            patches = self._create_patches()
            for p in patches[:5]:
                stack.enter_context(p)
            mock_el_create = stack.enter_context(patches[5])
            mock_cls = stack.enter_context(
                patch(
                    "application.architecture_service."
                    "ArchitectureElementInvariantValidator"
                )
            )
            mock_cls.for_workspace.return_value.validate_parent_assignment.side_effect = ValidationError(
                "[I3] Dangling parent reference"
            )
            with pytest.raises(ValidationError, match=r"\[I3\]"):
                svc.create_architecture_element(
                    workspace_id=WS_ID, title="C", ctx=ctx, parent_id=uuid.uuid4()
                )
            mock_el_create.assert_not_called()

    @staticmethod
    def _update_patches(mock_el, mock_filter_qs):
        return [
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.architecture_service.ArchitectureElement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(first=MagicMock(return_value=mock_el))
                    )
                ),
            ),
            patch(
                "application.architecture_service.ArchitectureElement.objects.filter",
                return_value=mock_filter_qs,
            ),
        ]

    def test_update_with_parent_id_validates_and_persists(self):
        svc = ArchitectureService()
        ctx = _make_ctx()
        mock_el = _make_arch_el(version=1)
        mock_filter_qs = MagicMock()
        new_parent = uuid.uuid4()

        with contextlib.ExitStack() as stack:
            for p in self._update_patches(mock_el, mock_filter_qs):
                stack.enter_context(p)
            mock_cls = stack.enter_context(
                patch(
                    "application.architecture_service."
                    "ArchitectureElementInvariantValidator"
                )
            )
            stack.enter_context(patch.object(svc, "_audit"))
            stack.enter_context(patch.object(svc, "_emit_event"))
            svc.update_architecture_element(
                arch_el_id=ARCH_EL_ID,
                ctx=ctx,
                expected_version=1,
                parent_id=new_parent,
            )

        mock_cls.for_workspace.assert_called_once_with(mock_el.artifact.workspace_id)
        mock_cls.for_workspace.return_value.validate_parent_assignment.assert_called_once()
        assert mock_filter_qs.update.call_args.kwargs["parent_id"] == new_parent

    def test_update_detach_parent_runs_single_root_validation(self):
        """SysEng 2.0 I5: detaching to root (parent_id=None) runs the validator
        so a second root cannot be created, then persists parent_id=None."""
        svc = ArchitectureService()
        ctx = _make_ctx()
        mock_el = _make_arch_el(version=1)
        mock_filter_qs = MagicMock()

        with contextlib.ExitStack() as stack:
            for p in self._update_patches(mock_el, mock_filter_qs):
                stack.enter_context(p)
            mock_cls = stack.enter_context(
                patch(
                    "application.architecture_service."
                    "ArchitectureElementInvariantValidator"
                )
            )
            stack.enter_context(patch.object(svc, "_audit"))
            stack.enter_context(patch.object(svc, "_emit_event"))
            svc.update_architecture_element(
                arch_el_id=ARCH_EL_ID, ctx=ctx, expected_version=1, parent_id=None
            )

        mock_cls.for_workspace.assert_called_once_with(mock_el.artifact.workspace_id)
        mock_cls.for_workspace.return_value.validate_parent_assignment.assert_called_once_with(
            parent_id=None,
            element=mock_el,
            element_id=ARCH_EL_ID,
            workspace_id=mock_el.artifact.workspace_id,
        )
        assert mock_filter_qs.update.call_args.kwargs["parent_id"] is None

    def test_update_without_parent_id_leaves_parent_untouched(self):
        """Omitted parent_id (sentinel) must not appear in the UPDATE, and
        changed fields (title) must be persisted in the UPDATE statement."""
        svc = ArchitectureService()
        ctx = _make_ctx()
        mock_el = _make_arch_el(version=1)
        mock_filter_qs = MagicMock()

        with contextlib.ExitStack() as stack:
            for p in self._update_patches(mock_el, mock_filter_qs):
                stack.enter_context(p)
            mock_cls = stack.enter_context(
                patch(
                    "application.architecture_service."
                    "ArchitectureElementInvariantValidator"
                )
            )
            stack.enter_context(patch.object(svc, "_audit"))
            stack.enter_context(patch.object(svc, "_emit_event"))
            svc.update_architecture_element(
                arch_el_id=ARCH_EL_ID, ctx=ctx, expected_version=1, title="New"
            )

        mock_cls.for_workspace.assert_not_called()
        update_kwargs = mock_filter_qs.update.call_args.kwargs
        assert "parent_id" not in update_kwargs
        assert update_kwargs["title"] == "New"


# ---------------------------------------------------------------------------
# SysEng 2.0 §1.2 — derived architecture role (root/inner/leaf → role)
# ---------------------------------------------------------------------------

from application.architecture_service import ArchitectureService as _ArchSvc  # noqa: E402
from persistence.models import (  # noqa: E402
    ArchitectureRole,
    derive_architecture_role,
)


class TestDeriveArchitectureRole:
    """SysEng 2.0 §1.2: the pure role-derivation mapping (SSOT)."""

    def test_root_is_system_even_without_children(self):
        assert (
            derive_architecture_role(has_parent=False, has_children=False)
            == ArchitectureRole.SYSTEM
        )

    def test_root_with_children_is_still_system(self):
        assert (
            derive_architecture_role(has_parent=False, has_children=True)
            == ArchitectureRole.SYSTEM
        )

    def test_inner_node_is_subsystem(self):
        assert (
            derive_architecture_role(has_parent=True, has_children=True)
            == ArchitectureRole.SUBSYSTEM
        )

    def test_leaf_is_component(self):
        assert (
            derive_architecture_role(has_parent=True, has_children=False)
            == ArchitectureRole.COMPONENT
        )


class TestAnnotateRoles:
    """SysEng 2.0 §1.2: ArchitectureService._annotate_roles single-pass."""

    @staticmethod
    def _node(el_id, parent_id):
        el = MagicMock()
        el.id = el_id
        el.parent_id = parent_id
        return el

    def test_annotates_system_subsystem_component(self):
        root_id, mid_id, leaf_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        elements = [
            self._node(root_id, None),      # root → system
            self._node(mid_id, root_id),    # has a child (leaf) → subsystem
            self._node(leaf_id, mid_id),    # leaf → component
        ]

        _ArchSvc._annotate_roles(elements)

        assert elements[0]._role_annotated == ArchitectureRole.SYSTEM
        assert elements[1]._role_annotated == ArchitectureRole.SUBSYSTEM
        assert elements[2]._role_annotated == ArchitectureRole.COMPONENT

    def test_single_root_node_is_system(self):
        only = self._node(uuid.uuid4(), None)
        _ArchSvc._annotate_roles([only])
        assert only._role_annotated == ArchitectureRole.SYSTEM


# ---------------------------------------------------------------------------
# SysEng 2.0 §1.2 — I5 single-root invariant (validator unit tests)
# ---------------------------------------------------------------------------


class TestInvariantI5SingleRoot:
    """SysEng 2.0 §1.2 (I5): at most one root (System) per workspace."""

    def test_second_root_raises_on_all_tiers(self):
        existing = MagicMock()
        existing.id = uuid.uuid4()
        for tier in ("minimal", "standard", "extended"):
            v = ArchitectureElementInvariantValidator.for_tier(tier)
            with patch.object(
                ArchitectureElementInvariantValidator,
                "_get_existing_root",
                return_value=existing,
            ):
                with pytest.raises(ValidationError, match=r"\[I5\]"):
                    v.check_i5(
                        new_parent_id=None,
                        workspace_id=WS_ID,
                        element_id=uuid.uuid4(),
                    )

    def test_first_root_passes(self):
        v = ArchitectureElementInvariantValidator.for_tier("standard")
        with patch.object(
            ArchitectureElementInvariantValidator,
            "_get_existing_root",
            return_value=None,
        ):
            v.check_i5(
                new_parent_id=None, workspace_id=WS_ID, element_id=uuid.uuid4()
            )  # must not raise

    def test_assigning_a_parent_never_trips_i5(self):
        """A non-None new_parent_id can never create a second root."""
        v = ArchitectureElementInvariantValidator.for_tier("standard")
        with patch.object(
            ArchitectureElementInvariantValidator, "_get_existing_root"
        ) as scan:
            v.check_i5(
                new_parent_id=uuid.uuid4(),
                workspace_id=WS_ID,
                element_id=uuid.uuid4(),
            )
        scan.assert_not_called()

    def test_existing_root_re_saved_as_root_is_allowed(self):
        """The element under validation is excluded from the root scan."""
        el_id = uuid.uuid4()
        v = ArchitectureElementInvariantValidator.for_tier("standard")
        captured = {}

        def _scan(workspace_id, exclude_id=None):
            captured["exclude_id"] = exclude_id
            return None  # excluding self, no *other* root exists

        with patch.object(
            ArchitectureElementInvariantValidator,
            "_get_existing_root",
            side_effect=_scan,
        ):
            v.check_i5(
                new_parent_id=None, workspace_id=WS_ID, element_id=el_id
            )
        assert captured["exclude_id"] == el_id


# ---------------------------------------------------------------------------
# Regression: list_architecture_elements must exclude outdated elements
# (Phase 0 fix — WorkflowItemState is the only source of truth, since
# ArchitectureElement is not wired into workflow._STATUS_MIRROR_MODELS).
# ---------------------------------------------------------------------------


@pytest.fixture
def arch_outdate_tenant():
    from persistence.models import Tenant

    return Tenant.objects.create(name="arch-outdate-tenant", slug="arch-outdate-tenant")


@pytest.fixture
def arch_outdate_user(arch_outdate_tenant):
    from persistence.models import User

    return User.objects.create(
        username="arch-outdate-user",
        email="arch-outdate@example.com",
        tenant=arch_outdate_tenant,
    )


@pytest.fixture
def arch_outdate_workspace(arch_outdate_tenant):
    from persistence.models import Workspace
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(arch_outdate_tenant.id)
    try:
        return Workspace.objects.create(
            tenant=arch_outdate_tenant, name="arch-outdate-workspace"
        )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def arch_outdate_ctx(arch_outdate_user):
    from auth_tenancy.context import AuthContext

    return AuthContext(
        user_id=arch_outdate_user.id,
        tenant_id=arch_outdate_user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="arch-outdate-tenant",
    )


class TestListArchitectureElementsExcludesOutdated:
    """Phase 0 regression: deleted (outdated) ArchitectureElements must not
    reappear in list_architecture_elements()."""

    def test_deleted_element_excluded_from_default_list(
        self, arch_outdate_ctx, arch_outdate_workspace
    ):
        from persistence.tenancy import TenantContext
        from workflow.models import WorkflowItemState
        from workflow.services import create_default_workflow

        TenantContext.set_tenant(arch_outdate_workspace.tenant_id)
        try:
            create_default_workflow(
                workspace_id=arch_outdate_workspace.id,
                preset="architecture_default",
                item_type="ArchitectureElement",
                tenant_id=arch_outdate_workspace.tenant_id,
            )
        finally:
            TenantContext.clear_tenant()

        svc = ArchitectureService()
        kept = svc.create_architecture_element(
            workspace_id=arch_outdate_workspace.id,
            title="Kept Component",
            ctx=arch_outdate_ctx,
        )
        # I5 invariant: only one root per workspace — attach the second
        # element under the first instead of making it a second root.
        deleted = svc.create_architecture_element(
            workspace_id=arch_outdate_workspace.id,
            title="Deleted Component",
            ctx=arch_outdate_ctx,
            parent_id=kept.id,
        )

        svc.delete_architecture_element(arch_el_id=deleted.id, ctx=arch_outdate_ctx)

        item_state = WorkflowItemState.objects.get(
            item_id=deleted.id, item_type="ArchitectureElement"
        )
        assert item_state.current_state == "outdated"

        elements = svc.list_architecture_elements(
            workspace_id=arch_outdate_workspace.id, ctx=arch_outdate_ctx
        )
        ids = {el.id for el in elements}
        assert kept.id in ids
        assert deleted.id not in ids

        elements_incl = svc.list_architecture_elements(
            workspace_id=arch_outdate_workspace.id,
            ctx=arch_outdate_ctx,
            include_deleted=True,
        )
        ids_incl = {el.id for el in elements_incl}
        assert deleted.id in ids_incl


class TestListArchitectureElementsSearchFilter:
    """Issue #267 (same root cause as RequirementService.list_requirements):
    GET /api/v1/architecture-elements/?search=<term> must filter on
    title/description/uid instead of being silently ignored."""

    def test_search_filters_by_title_case_insensitive(
        self, arch_outdate_ctx, arch_outdate_workspace
    ):
        svc = ArchitectureService()
        matching = svc.create_architecture_element(
            workspace_id=arch_outdate_workspace.id,
            title="Payment Gateway Component",
            ctx=arch_outdate_ctx,
        )
        other = svc.create_architecture_element(
            workspace_id=arch_outdate_workspace.id,
            title="Unrelated Component",
            ctx=arch_outdate_ctx,
            parent_id=matching.id,
        )

        elements = svc.list_architecture_elements(
            workspace_id=arch_outdate_workspace.id,
            ctx=arch_outdate_ctx,
            search="payment gateway",
        )
        ids = {el.id for el in elements}

        assert ids == {matching.id}
        assert other.id not in ids


class TestArtifactParentMirrorsElementHierarchy:
    """Issue #366: the backing Artifact tree must mirror the element tree.

    ``ArchitectureElement.parent`` and ``Artifact.parent`` are two
    representations of the same hierarchy. ``create_architecture_element``
    used to populate only the former, so ``artifact.get_tree`` (a recursive
    CTE over ``pl_artifact.parent_id``) reported every architecture element
    as a childless root.
    """

    def test_create_child_sets_backing_artifact_parent(
        self, arch_outdate_ctx, arch_outdate_workspace
    ):
        svc = ArchitectureService()
        root = svc.create_architecture_element(
            workspace_id=arch_outdate_workspace.id,
            title="Root System",
            ctx=arch_outdate_ctx,
        )
        child = svc.create_architecture_element(
            workspace_id=arch_outdate_workspace.id,
            title="Child Component",
            ctx=arch_outdate_ctx,
            parent_id=root.id,
        )

        child.artifact.refresh_from_db()
        root.artifact.refresh_from_db()
        # The Artifact parent is the *parent element's Artifact*, never the
        # ArchitectureElement primary key (a distinct id space).
        assert child.artifact.parent_id == root.artifact_id
        assert root.artifact.parent_id is None

    def test_create_root_leaves_backing_artifact_parent_null(
        self, arch_outdate_ctx, arch_outdate_workspace
    ):
        svc = ArchitectureService()
        root = svc.create_architecture_element(
            workspace_id=arch_outdate_workspace.id,
            title="Root System",
            ctx=arch_outdate_ctx,
        )
        root.artifact.refresh_from_db()
        assert root.artifact.parent_id is None

    def test_reparenting_updates_backing_artifact_parent(
        self, arch_outdate_ctx, arch_outdate_workspace
    ):
        svc = ArchitectureService()
        root = svc.create_architecture_element(
            workspace_id=arch_outdate_workspace.id,
            title="Root System",
            ctx=arch_outdate_ctx,
        )
        first = svc.create_architecture_element(
            workspace_id=arch_outdate_workspace.id,
            title="First Branch",
            ctx=arch_outdate_ctx,
            parent_id=root.id,
        )
        moving = svc.create_architecture_element(
            workspace_id=arch_outdate_workspace.id,
            title="Moving Component",
            ctx=arch_outdate_ctx,
            parent_id=root.id,
        )

        svc.update_architecture_element(
            arch_el_id=moving.id, ctx=arch_outdate_ctx, parent_id=first.id
        )

        moving.artifact.refresh_from_db()
        assert moving.artifact.parent_id == first.artifact_id

    def test_get_tree_returns_architecture_children(
        self, arch_outdate_ctx, arch_outdate_workspace
    ):
        from application.artifact_service import ArtifactService

        svc = ArchitectureService()
        root = svc.create_architecture_element(
            workspace_id=arch_outdate_workspace.id,
            title="Root System",
            ctx=arch_outdate_ctx,
        )
        child = svc.create_architecture_element(
            workspace_id=arch_outdate_workspace.id,
            title="Child Component",
            ctx=arch_outdate_ctx,
            parent_id=root.id,
        )
        grandchild = svc.create_architecture_element(
            workspace_id=arch_outdate_workspace.id,
            title="Grandchild Component",
            ctx=arch_outdate_ctx,
            parent_id=child.id,
        )

        tree = ArtifactService().get_tree(
            root_id=root.id,
            workspace_id=arch_outdate_workspace.id,
            ctx=arch_outdate_ctx,
        )

        assert tree.id == root.artifact_id
        assert [c.id for c in tree.children] == [child.artifact_id]
        assert [g.id for g in tree.children[0].children] == [grandchild.artifact_id]


