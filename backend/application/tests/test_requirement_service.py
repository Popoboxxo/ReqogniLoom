"""
Tests for COMP-AS-002 RequirementService.

leaf_id : COMP-AS-002
req_id  : REQ-L2-AS-003 (Requirement CRUD), REQ-L2-AS-013 (LLM Orchestration),
          REQ-L2-AS-024 (Decomposition), REQ-L2-AS-019 (Audit per write)

Coverage:
  - create_requirement: success, viewer denied, tenant not found, workspace not found,
                        audit entry produced
  - update_requirement: success, change_reason policy enforcement, not found
  - delete_requirement: success, cascade trace links called, not found
  - get_requirement / list_requirements: basic delegation
  - decompose: manual children persisted; LLM path raises LlmNotConfiguredError
  - Tenant isolation: _set_tenant_context called on every write
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch, call

import pytest

from application.base import (
    LlmNotConfiguredError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from application.requirement_service import (
    DecompositionResultDTO,
    RequirementDTO,
    RequirementService,
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
REQ_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()


def _make_requirement(**kwargs):
    """Return a MagicMock shaped like a Requirement ORM instance."""
    req = MagicMock()
    req.id = kwargs.get("id", REQ_ID)
    req.title = kwargs.get("title", "Sample Requirement")
    req.description = kwargs.get("description", "")
    req.category = kwargs.get("category", "Functional")
    req.status = kwargs.get("status", "draft")
    req.version = kwargs.get("version", 1)
    artifact = MagicMock()
    artifact.id = uuid.uuid4()
    artifact.workspace_id = kwargs.get("workspace_id", WS_ID)
    req.artifact = artifact
    req.artifact_id = artifact.id
    return req


# ---------------------------------------------------------------------------
# create_requirement
# ---------------------------------------------------------------------------


class TestCreateRequirement:
    """REQ-L2-AS-003, REQ-L2-AS-019."""

    def test_viewer_cannot_create(self):
        """PermissionDeniedError for viewer context."""
        svc = RequirementService()
        ctx = _make_ctx(roles=("viewer",))

        with patch("application.requirement_service.ServiceBase._set_tenant_context"):
            with pytest.raises(PermissionDeniedError):
                svc.create_requirement(workspace_id=WS_ID, title="T", ctx=ctx)

    def test_tenant_not_found_raises(self):
        """NotFoundError when tenant does not exist."""
        svc = RequirementService()
        ctx = _make_ctx()

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.requirement_service.Tenant",
                **{"objects.filter.return_value.first.return_value": None},
            ),
        ):
            with pytest.raises(NotFoundError, match="Tenant"):
                svc.create_requirement(workspace_id=WS_ID, title="T", ctx=ctx)

    def test_workspace_not_found_raises(self):
        """NotFoundError when workspace does not exist."""
        svc = RequirementService()
        ctx = _make_ctx()

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.requirement_service.Tenant",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.requirement_service.Workspace",
                **{"objects.filter.return_value.first.return_value": None},
            ),
        ):
            with pytest.raises(NotFoundError, match="Workspace"):
                svc.create_requirement(workspace_id=WS_ID, title="T", ctx=ctx)

    def test_create_success_returns_requirement(self):
        """create_requirement returns the ORM Requirement instance."""
        svc = RequirementService()
        ctx = _make_ctx()
        mock_req = _make_requirement()
        mock_artifact = MagicMock()

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.requirement_service.Tenant",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.requirement_service.Workspace",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.requirement_service.Artifact.objects.create",
                return_value=mock_artifact,
            ),
            patch(
                "application.requirement_service.Requirement.objects.create",
                return_value=mock_req,
            ),
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event"),
        ):
            result = svc.create_requirement(workspace_id=WS_ID, title="T", ctx=ctx)

        assert result is mock_req

    def test_audit_entry_on_create(self):
        """_audit is called with operation='create' on successful create."""
        svc = RequirementService()
        ctx = _make_ctx()
        mock_req = _make_requirement()
        mock_artifact = MagicMock()

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.requirement_service.Tenant",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.requirement_service.Workspace",
                **{"objects.filter.return_value.first.return_value": MagicMock()},
            ),
            patch(
                "application.requirement_service.Artifact.objects.create",
                return_value=mock_artifact,
            ),
            patch(
                "application.requirement_service.Requirement.objects.create",
                return_value=mock_req,
            ),
            patch.object(svc, "_audit") as mock_audit,
            patch.object(svc, "_emit_event"),
        ):
            svc.create_requirement(workspace_id=WS_ID, title="T", ctx=ctx)

        mock_audit.assert_called_once()
        kw = mock_audit.call_args.kwargs
        assert kw["operation"] == "create"
        assert kw["entity_type"] == "Requirement"

    def test_tenant_context_set_on_create(self):
        """_set_tenant_context is called with the AuthContext on create."""
        svc = RequirementService()
        ctx = _make_ctx()

        with (
            patch(
                "application.requirement_service.ServiceBase._set_tenant_context"
            ) as mock_stc,
            patch(
                "application.requirement_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.requirement_service.Tenant",
                **{"objects.filter.return_value.first.return_value": None},
            ),
        ):
            with pytest.raises(NotFoundError):
                svc.create_requirement(workspace_id=WS_ID, title="T", ctx=ctx)

        mock_stc.assert_called_once_with(ctx)


# ---------------------------------------------------------------------------
# update_requirement
# ---------------------------------------------------------------------------


class TestUpdateRequirement:
    """REQ-L2-AS-003, REQ-L2-AS-019 (audit), ADR-L3-AS002-02 (policy gate)."""

    def test_update_not_found_raises(self):
        """NotFoundError when requirement does not exist."""
        svc = RequirementService()
        ctx = _make_ctx()

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.requirement_service.Requirement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(first=MagicMock(return_value=None))
                    )
                ),
            ),
        ):
            with pytest.raises(NotFoundError, match="Requirement"):
                svc.update_requirement(requirement_id=REQ_ID, ctx=ctx)

    def test_change_reason_required_raises_validation_error(self):
        """ValidationError when preset requires change_reason and it is missing."""
        svc = RequirementService()
        ctx = _make_ctx()
        mock_req = _make_requirement()

        mock_policy = MagicMock()
        mock_policy.is_change_reason_required.return_value = True
        svc._preset_policy = mock_policy

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.requirement_service.Requirement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_req)
                        )
                    )
                ),
            ),
        ):
            with pytest.raises(ValidationError, match="change_reason"):
                svc.update_requirement(
                    requirement_id=REQ_ID, ctx=ctx, change_reason=None
                )

    def test_change_reason_not_required_allows_update(self):
        """Update succeeds when preset does not require change_reason."""
        svc = RequirementService()
        ctx = _make_ctx()
        mock_req = _make_requirement()

        mock_policy = MagicMock()
        mock_policy.is_change_reason_required.return_value = False
        svc._preset_policy = mock_policy

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.requirement_service.Requirement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_req)
                        )
                    )
                ),
            ),
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event"),
        ):
            result = svc.update_requirement(
                requirement_id=REQ_ID, ctx=ctx, title="New Title"
            )

        assert mock_req.title == "New Title"
        assert result is mock_req

    def test_audit_entry_on_update(self):
        """_audit is invoked with operation='update' on each write."""
        svc = RequirementService()
        ctx = _make_ctx()
        mock_req = _make_requirement()

        mock_policy = MagicMock()
        mock_policy.is_change_reason_required.return_value = False
        svc._preset_policy = mock_policy

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.requirement_service.Requirement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_req)
                        )
                    )
                ),
            ),
            patch.object(svc, "_audit") as mock_audit,
            patch.object(svc, "_emit_event"),
        ):
            svc.update_requirement(requirement_id=REQ_ID, ctx=ctx, title="X")

        mock_audit.assert_called_once()
        kw = mock_audit.call_args.kwargs
        assert kw["operation"] == "update"
        assert kw["entity_type"] == "Requirement"


    def test_update_status_round_trip(self):
        """Update requirement status and verify it persists (REQ-L3-RF003-002)."""
        svc = RequirementService()
        ctx = _make_ctx()
        mock_req = _make_requirement(status="draft")

        mock_policy = MagicMock()
        mock_policy.is_change_reason_required.return_value = False
        svc._preset_policy = mock_policy

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.requirement_service.Requirement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_req)
                        )
                    )
                ),
            ),
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event"),
        ):
            result = svc.update_requirement(
                requirement_id=REQ_ID, ctx=ctx, status="approved"
            )

        assert mock_req.status == "approved"
        assert result is mock_req

    def test_update_status_none_leaves_status_unchanged(self):
        """When status is None, the existing status must not be modified."""
        svc = RequirementService()
        ctx = _make_ctx()
        mock_req = _make_requirement(status="review")

        mock_policy = MagicMock()
        mock_policy.is_change_reason_required.return_value = False
        svc._preset_policy = mock_policy

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.requirement_service.Requirement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_req)
                        )
                    )
                ),
            ),
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event"),
        ):
            svc.update_requirement(
                requirement_id=REQ_ID, ctx=ctx, title="New Title"
            )

        assert mock_req.status == "review"

    def test_update_increments_version_atomically(self):
        """update_requirement atomically increments version via F() expression (REQ-L3-PL001-002).

        Prior to this fix the method called requirement.save() without any version
        increment, so version remained at 1 forever, breaking the baseline diff engine.
        """
        svc = RequirementService()
        ctx = _make_ctx()
        mock_req = _make_requirement(version=1)

        mock_policy = MagicMock()
        mock_policy.is_change_reason_required.return_value = False
        svc._preset_policy = mock_policy

        # Simulate the DB-level F("version") + 1 that refresh_from_db would return.
        mock_req.refresh_from_db = MagicMock(
            side_effect=lambda fields=None: setattr(mock_req, "version", mock_req.version + 1)
        )

        mock_filter_qs = MagicMock()

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch("application.requirement_service.ServiceBase._assert_write_permission"),
            patch(
                "application.requirement_service.Requirement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_req)
                        )
                    )
                ),
            ),
            patch(
                "application.requirement_service.Requirement.objects.filter",
                return_value=mock_filter_qs,
            ),
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event"),
        ):
            result = svc.update_requirement(
                requirement_id=REQ_ID, ctx=ctx, title="Updated"
            )

        # Atomic update must have been issued.
        mock_filter_qs.update.assert_called_once()
        # refresh_from_db must have been called to sync the new version.
        mock_req.refresh_from_db.assert_called_once_with(fields=["version"])
        # Version must reflect the incremented value.
        assert result.version == 2


# ---------------------------------------------------------------------------
# delete_requirement
# ---------------------------------------------------------------------------


class TestDeleteRequirement:
    """REQ-L2-AS-003."""

    def test_delete_not_found_raises(self):
        """NotFoundError when requirement does not exist."""
        svc = RequirementService()
        ctx = _make_ctx()

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.requirement_service.Requirement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(first=MagicMock(return_value=None))
                    )
                ),
            ),
        ):
            with pytest.raises(NotFoundError, match="Requirement"):
                svc.delete_requirement(requirement_id=REQ_ID, ctx=ctx)

    def test_delete_cascades_trace_links_and_deletes(self):
        """cascade_delete_trace_links called then requirement.delete() called."""
        svc = RequirementService()
        ctx = _make_ctx()
        mock_req = _make_requirement()

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.requirement_service.Requirement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_req)
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
            svc.delete_requirement(requirement_id=REQ_ID, ctx=ctx)

        mock_cascade.assert_called_once()
        mock_req.delete.assert_called_once()

    def test_audit_entry_on_delete(self):
        """_audit is invoked with operation='delete'."""
        svc = RequirementService()
        ctx = _make_ctx()
        mock_req = _make_requirement()

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.requirement_service.Requirement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_req)
                        )
                    )
                ),
            ),
            patch.object(svc._trace_link_service, "cascade_delete_trace_links"),
            patch.object(svc, "_audit") as mock_audit,
            patch.object(svc, "_emit_event"),
        ):
            svc.delete_requirement(requirement_id=REQ_ID, ctx=ctx)

        mock_audit.assert_called_once()
        kw = mock_audit.call_args.kwargs
        assert kw["operation"] == "delete"


# ---------------------------------------------------------------------------
# get_requirement / list_requirements
# ---------------------------------------------------------------------------


class TestGetRequirement:
    def test_get_returns_requirement(self):
        """get_requirement returns the ORM instance."""
        svc = RequirementService()
        ctx = _make_ctx()
        mock_req = _make_requirement()

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.Requirement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_req)
                        )
                    )
                ),
            ),
        ):
            result = svc.get_requirement(REQ_ID, ctx)

        assert result is mock_req

    def test_get_not_found_raises(self):
        """NotFoundError when requirement absent."""
        svc = RequirementService()
        ctx = _make_ctx()

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.Requirement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(first=MagicMock(return_value=None))
                    )
                ),
            ),
        ):
            with pytest.raises(NotFoundError):
                svc.get_requirement(REQ_ID, ctx)

    def test_list_requirements_returns_list(self):
        """list_requirements returns a list of ORM instances."""
        svc = RequirementService()
        ctx = _make_ctx()
        mock_reqs = [_make_requirement(), _make_requirement()]

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.Requirement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(return_value=mock_reqs)
                ),
            ),
        ):
            result = svc.list_requirements(WS_ID, ctx)

        assert result == mock_reqs


# ---------------------------------------------------------------------------
# decompose — manual children path
# ---------------------------------------------------------------------------


class TestDecompose:
    """REQ-L2-AS-024, ADR-L3-AS002-01."""

    def test_decompose_manual_children_creates_child_requirements(self):
        """decompose with explicit children creates child Requirements."""
        svc = RequirementService()
        ctx = _make_ctx()
        mock_parent = _make_requirement()
        mock_child_req = _make_requirement(title="Child")
        mock_child_artifact = MagicMock()
        mock_child_req.artifact = mock_child_artifact
        mock_child_req.artifact_id = uuid.uuid4()

        # Patch the internal create_requirement call
        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.requirement_service.Requirement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_parent)
                        )
                    )
                ),
            ),
            patch.object(svc, "create_requirement", return_value=mock_child_req),
            patch.object(
                svc._trace_link_service, "create_trace_link", side_effect=Exception("no-op")
            ),
        ):
            result = svc.decompose(
                requirement_id=REQ_ID,
                ctx=ctx,
                children=[{"title": "Child", "description": "desc"}],
            )

        assert isinstance(result, DecompositionResultDTO)
        assert len(result.children) == 1
        assert result.children[0].title == "Child"

    def test_decompose_llm_not_configured_raises(self):
        """_decompose_via_llm raises LlmNotConfiguredError when LLM absent."""
        svc = RequirementService()
        ctx = _make_ctx()
        mock_parent = _make_requirement()

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.requirement_service.Requirement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_parent)
                        )
                    )
                ),
            ),
            patch(
                "application.requirement_service.RequirementService._decompose_via_llm",
                side_effect=LlmNotConfiguredError("not configured"),
            ),
        ):
            with pytest.raises(LlmNotConfiguredError):
                svc.decompose(requirement_id=REQ_ID, ctx=ctx, children=None)

    def test_decompose_parent_not_found_raises(self):
        """NotFoundError when parent requirement is missing."""
        svc = RequirementService()
        ctx = _make_ctx()

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.requirement_service.Requirement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(first=MagicMock(return_value=None))
                    )
                ),
            ),
        ):
            with pytest.raises(NotFoundError):
                svc.decompose(
                    requirement_id=REQ_ID, ctx=ctx, children=[{"title": "X"}]
                )

    def test_decompose_with_target_architecture_elements(self):
        """decompose with target_architecture_elements allocates children (REQ-L1-043)."""
        svc = RequirementService()
        ctx = _make_ctx()
        mock_parent = _make_requirement()
        mock_child_req = _make_requirement(title="Child")
        mock_child_artifact = MagicMock()
        mock_child_req.artifact = mock_child_artifact
        mock_child_req.artifact_id = uuid.uuid4()

        arch_el_id = uuid.uuid4()

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.requirement_service.Requirement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_parent)
                        )
                    )
                ),
            ),
            patch.object(svc, "create_requirement", return_value=mock_child_req),
            patch(
                "application.requirement_service.ArchitectureElement.objects.filter",
                return_value=MagicMock(
                    first=MagicMock(
                        return_value=MagicMock(
                            artifact=MagicMock(workspace_id=WS_ID)
                        )
                    )
                ),
            ),
            patch.object(
                svc._trace_link_service, "create_trace_link", side_effect=Exception("no-op")
            ),
            patch.object(
                svc._trace_link_service, "allocate", return_value=MagicMock(id=uuid.uuid4())
            ) as mock_allocate,
        ):
            result = svc.decompose(
                requirement_id=REQ_ID,
                ctx=ctx,
                children=[{"title": "Child", "description": "desc"}],
                target_architecture_elements=[arch_el_id],
            )

        assert isinstance(result, DecompositionResultDTO)
        assert len(result.children) == 1
        assert result.children[0].title == "Child"
        # Verify allocation was called
        mock_allocate.assert_called_once()
        call_kwargs = mock_allocate.call_args.kwargs
        assert call_kwargs["requirement_id"] == mock_child_req.id
        assert call_kwargs["architecture_element_id"] == arch_el_id

    def test_decompose_target_elements_count_mismatch_raises(self):
        """ValidationError when target_architecture_elements count != children count (REQ-L1-043)."""
        svc = RequirementService()
        ctx = _make_ctx()
        mock_parent = _make_requirement()

        arch_el_id = uuid.uuid4()

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.requirement_service.Requirement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_parent)
                        )
                    )
                ),
            ),
        ):
            with pytest.raises(ValidationError, match="must match number of children"):
                svc.decompose(
                    requirement_id=REQ_ID,
                    ctx=ctx,
                    children=[{"title": "Child1"}, {"title": "Child2"}],
                    target_architecture_elements=[arch_el_id],  # Only 1, but 2 children
                )

    def test_decompose_target_element_not_found_raises(self):
        """NotFoundError when target ArchitectureElement does not exist (REQ-L1-043)."""
        svc = RequirementService()
        ctx = _make_ctx()
        mock_parent = _make_requirement()

        arch_el_id = uuid.uuid4()

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.requirement_service.Requirement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_parent)
                        )
                    )
                ),
            ),
            patch(
                "application.requirement_service.ArchitectureElement.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
        ):
            with pytest.raises(NotFoundError, match="ArchitectureElement"):
                svc.decompose(
                    requirement_id=REQ_ID,
                    ctx=ctx,
                    children=[{"title": "Child"}],
                    target_architecture_elements=[arch_el_id],
                )

    def test_decompose_empty_target_elements_raises(self):
        """ValidationError when target_architecture_elements is empty list (REQ-L1-043)."""
        svc = RequirementService()
        ctx = _make_ctx()
        mock_parent = _make_requirement()

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.requirement_service.Requirement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            first=MagicMock(return_value=mock_parent)
                        )
                    )
                ),
            ),
        ):
            with pytest.raises(ValidationError, match="cannot be empty"):
                svc.decompose(
                    requirement_id=REQ_ID,
                    ctx=ctx,
                    children=[{"title": "Child"}],
                    target_architecture_elements=[],  # Empty
                )


# ---------------------------------------------------------------------------
# RequirementDTO
# ---------------------------------------------------------------------------


class TestRequirementDTO:
    def test_from_orm_maps_fields(self):
        """RequirementDTO.from_orm maps all Requirement fields correctly."""
        mock_req = _make_requirement()
        mock_req.artifact.workspace_id = WS_ID

        dto = RequirementDTO.from_orm(mock_req)

        assert dto.id == mock_req.id
        assert dto.workspace_id == WS_ID
        assert dto.title == mock_req.title
        assert dto.description == mock_req.description
        assert dto.category == mock_req.category
        assert dto.status == mock_req.status
        assert dto.version == mock_req.version
