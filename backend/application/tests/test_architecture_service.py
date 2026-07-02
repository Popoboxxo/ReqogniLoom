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
    """REQ-L2-AS-004."""

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

    def test_delete_cascades_trace_links(self):
        """cascade_delete_trace_links called before element.delete()."""
        svc = ArchitectureService()
        ctx = _make_ctx()
        mock_el = _make_arch_el()

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
        ):
            svc.delete_architecture_element(arch_el_id=ARCH_EL_ID, ctx=ctx)

        mock_cascade.assert_called_once()
        mock_el.delete.assert_called_once()


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

    def test_list_returns_all_elements(self):
        """list_architecture_elements returns a list for the workspace."""
        svc = ArchitectureService()
        ctx = _make_ctx()
        mock_elements = [_make_arch_el(), _make_arch_el()]

        with (
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ArchitectureElement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(return_value=mock_elements)
                ),
            ),
        ):
            result = svc.list_architecture_elements(WS_ID, ctx)

        assert result == mock_elements


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

    def test_create_with_invalid_element_type_raises_validation_error(self):
        """Invalid element_type like 'banane' raises ValidationError."""
        svc = ArchitectureService()
        ctx = _make_ctx()

        with (
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ServiceBase._assert_write_permission"
            ),
        ):
            with pytest.raises(ValidationError, match="Invalid element_type"):
                svc.create_architecture_element(
                    workspace_id=WS_ID,
                    title="Invalid",
                    ctx=ctx,
                    element_type="banane",
                )

    def test_create_with_empty_string_raises_validation_error(self):
        """Empty string element_type raises ValidationError."""
        svc = ArchitectureService()
        ctx = _make_ctx()

        with (
            patch("application.architecture_service.ServiceBase._set_tenant_context"),
            patch(
                "application.architecture_service.ServiceBase._assert_write_permission"
            ),
        ):
            with pytest.raises(ValidationError, match="Invalid element_type"):
                svc.create_architecture_element(
                    workspace_id=WS_ID,
                    title="Empty",
                    ctx=ctx,
                    element_type="",
                )

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

    def test_update_with_invalid_element_type_raises_validation_error(self):
        """update_architecture_element rejects invalid element_type."""
        svc = ArchitectureService()
        ctx = _make_ctx()
        mock_el = _make_arch_el(version=1)

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
            with pytest.raises(ValidationError, match="Invalid element_type"):
                svc.update_architecture_element(
                    arch_el_id=ARCH_EL_ID,
                    ctx=ctx,
                    expected_version=1,
                    element_type="banane",
                )

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


