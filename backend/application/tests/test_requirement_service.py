"""
Tests for COMP-AS-002 RequirementService.

leaf_id : COMP-AS-002
req_id  : REQ-L2-AS-003 (Requirement CRUD), REQ-L2-AS-013 (LLM Orchestration),
          REQ-L2-AS-024 (Decomposition), REQ-L2-AS-019 (Audit per write)

Coverage:
  - create_requirement: success, viewer denied, tenant not found, workspace not found,
                        audit entry produced
  - update_requirement: success, change_reason policy enforcement, not found
  - delete_requirement: soft-delete (lifecycle_status='deleted', REQ-006), not found
  - get_requirement / list_requirements: basic delegation
  - decompose: manual children persisted; LLM path raises LlmNotConfiguredError;
               always creates LinkType.DECOMPOSES TraceLinks, regardless of
               Workspace.decomposition_link_type (UMSETZUNGSPLAN_SYSENG_2.0.md §1.4)
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
from traceability.types import LinkType

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
            patch("application.requirement_service.Requirement.objects.filter"),
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
            patch("application.requirement_service.Requirement.objects.filter"),
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
            patch("application.requirement_service.Requirement.objects.filter"),
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
            patch("application.requirement_service.Requirement.objects.filter"),
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
            # REQ-L2-VS-004 added a best-effort embedding refresh that also runs
            # Requirement.objects.filter(...).update(...). Because this test uses
            # a single shared mock for objects.filter, that second update would
            # be counted here and break assert_called_once(). Neutralize the
            # embedding path so the assertion isolates the version increment.
            patch.object(svc, "_generate_and_store_embedding"),
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
        """delete_requirement soft-deletes via workflow.services.outdate() (REQ-006, Phase 0).

        Physical deletion is not performed: the requirement row and its
        TraceLinks remain for audit purposes; the soft-delete marker is now
        the workflow engine's "outdated" state instead of a direct field write.
        """
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
            patch.object(svc, "_audit"),
            patch.object(svc, "_emit_event"),
            patch("workflow.services.outdate") as mock_outdate,
        ):
            svc.delete_requirement(requirement_id=REQ_ID, ctx=ctx)

        mock_outdate.assert_called_once_with(
            item_id=mock_req.id,
            item_type="Requirement",
            workspace_id=mock_req.artifact.workspace_id,
            ctx=ctx,
            reason="deleted via requirement.delete",
        )

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
            patch("workflow.services.outdate"),
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

    def test_get_returns_outdated_requirement(self):
        """GH-443: get_requirement resolves soft-deleted requirements instead of 404ing.

        Inverted from the previous expectation: hiding the row made DELETE
        indistinguishable from a hard delete over the API, and disagreed with
        every sibling service (get_test_case/get_adr/get_issue/get_risk).
        """
        svc = RequirementService()
        ctx = _make_ctx()
        mock_req = _make_requirement(status="outdated")

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
        assert result.status == "outdated"

    def test_list_requirements_returns_list(self):
        """list_requirements returns a list of ORM instances, excluding soft-deleted (REQ-006)."""
        svc = RequirementService()
        ctx = _make_ctx()
        mock_reqs = [_make_requirement(), _make_requirement()]
        mock_filtered_qs = MagicMock()
        mock_filtered_qs.exclude.return_value = mock_reqs

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.Requirement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(return_value=mock_filtered_qs)
                ),
            ),
        ):
            result = svc.list_requirements(WS_ID, ctx)

        # Phase 0: outdate() mirrors the "outdated" state into `status`, not
        # `lifecycle_status` — the filter must match what it actually writes.
        mock_filtered_qs.exclude.assert_called_once_with(status="outdated")
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
                svc._trace_link_service,
                "create_trace_link",
                return_value=MagicMock(id=uuid.uuid4()),
            ) as mock_create_trace_link,
        ):
            result = svc.decompose(
                requirement_id=REQ_ID,
                ctx=ctx,
                children=[{"title": "Child", "description": "desc"}],
            )

        assert isinstance(result, DecompositionResultDTO)
        assert len(result.children) == 1
        assert result.children[0].title == "Child"
        # UMSETZUNGSPLAN_SYSENG_2.0.md §1.4: decompose() always creates
        # LinkType.DECOMPOSES links — Workspace is no longer consulted.
        # Issue #395: plus the reciprocal 'derives-from' back-link.
        link_types = [
            call.kwargs["link_type"] for call in mock_create_trace_link.call_args_list
        ]
        assert link_types == [
            LinkType.DECOMPOSES.value,
            LinkType.DERIVES_FROM.value,
        ]

    def test_decompose_propagates_a_failed_derives_from_back_link(self):
        """A failing back-link must abort, not commit half of the pair.

        Issue #395 (review finding F2): the 'decomposes' link is best-effort,
        but its reciprocal 'derives-from' is a correctness precondition — a
        swallowed failure would silently produce exactly the graph TRACE-P5
        reports as a BLOCKER. The exception has to escape so the surrounding
        TransactionContextManager rolls the decomposition back.
        """
        svc = RequirementService()
        ctx = _make_ctx()
        mock_parent = _make_requirement()
        mock_child_req = _make_requirement(title="Child")
        mock_child_req.artifact = MagicMock()
        mock_child_req.artifact_id = uuid.uuid4()

        def _fail_on_derives_from(**kwargs):
            if kwargs["link_type"] == LinkType.DERIVES_FROM.value:
                raise RuntimeError("traceability engine unavailable")
            return MagicMock(id=uuid.uuid4())

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
                svc._trace_link_service,
                "create_trace_link",
                side_effect=_fail_on_derives_from,
            ),
            pytest.raises(RuntimeError, match="traceability engine unavailable"),
        ):
            svc.decompose(
                requirement_id=REQ_ID,
                ctx=ctx,
                children=[{"title": "Child", "description": "desc"}],
            )

    def test_decompose_survives_a_failed_decomposes_link(self):
        """The 'decomposes' half stays best-effort and only warns.

        Since #395 the auditor reads the hierarchy off the 'derives-from'
        edge as well, so a missing 'decomposes' link degrades the graph
        without breaking its classification.
        """
        svc = RequirementService()
        ctx = _make_ctx()
        mock_parent = _make_requirement()
        mock_child_req = _make_requirement(title="Child")
        mock_child_req.artifact = MagicMock()
        mock_child_req.artifact_id = uuid.uuid4()

        def _fail_on_decomposes(**kwargs):
            if kwargs["link_type"] == LinkType.DECOMPOSES.value:
                raise RuntimeError("boom")
            return MagicMock(id=uuid.uuid4())

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
                svc._trace_link_service,
                "create_trace_link",
                side_effect=_fail_on_decomposes,
            ) as mock_create_trace_link,
        ):
            result = svc.decompose(
                requirement_id=REQ_ID,
                ctx=ctx,
                children=[{"title": "Child", "description": "desc"}],
            )

        assert len(result.children) == 1
        # Both were attempted; only the back-link produced an id.
        link_types = [
            call.kwargs["link_type"] for call in mock_create_trace_link.call_args_list
        ]
        assert link_types == [
            LinkType.DECOMPOSES.value,
            LinkType.DERIVES_FROM.value,
        ]
        assert len(result.trace_link_ids) == 1

    def test_decompose_ignores_workspace_decomposition_link_type(self):
        """decompose creates LinkType.DECOMPOSES even if the workspace is configured
        with a different decomposition_link_type (hardcoded, no longer read)."""
        svc = RequirementService()
        ctx = _make_ctx()
        mock_parent = _make_requirement()
        mock_child_req = _make_requirement(title="Child")
        mock_child_req.artifact = MagicMock()
        mock_child_req.artifact_id = uuid.uuid4()

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
            # A workspace configured with a different link type must NOT
            # influence the (now hardcoded) generation path.
            patch(
                "application.requirement_service.Workspace.objects.filter",
                return_value=MagicMock(
                    first=MagicMock(
                        return_value=MagicMock(decomposition_link_type="satisfies")
                    )
                ),
            ),
            patch.object(
                svc._trace_link_service,
                "create_trace_link",
                return_value=MagicMock(id=uuid.uuid4()),
            ) as mock_create_trace_link,
        ):
            svc.decompose(
                requirement_id=REQ_ID,
                ctx=ctx,
                children=[{"title": "Child", "description": "desc"}],
            )

        assert (
            mock_create_trace_link.call_args_list[0].kwargs["link_type"]
            == LinkType.DECOMPOSES.value
        )

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
            patch("application.requirement_service.Workspace.objects.filter"),
            patch(
                "persistence.models.ArchitectureElement.objects.filter",
                return_value=MagicMock(
                    first=MagicMock(
                        return_value=MagicMock(
                            artifact=MagicMock(workspace_id=WS_ID)
                        )
                    )
                ),
            ),
            # Stubbed out because this test is about the allocation
            # (REQ-L1-043), not about the hierarchy links. It used to raise
            # Exception("no-op") as a shortcut, which only worked while
            # decompose() swallowed every TraceLink error; the reciprocal
            # 'derives-from' now propagates by design (issue #395 review F2),
            # so the stub has to be an actual no-op.
            patch.object(
                svc._trace_link_service,
                "create_trace_link",
                return_value=MagicMock(id=uuid.uuid4()),
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
            patch("application.requirement_service.Workspace.objects.filter"),
            patch(
                "persistence.models.ArchitectureElement.objects.filter",
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
# derive_requirement — description inheritance (Issue #459, finding 2)
# ---------------------------------------------------------------------------


class TestDeriveRequirementDescriptionInheritance:
    """Issue #459 finding 2: derive_requirement must not create the child with
    an empty description — it should inherit the parent's description unless
    the caller explicitly supplies one (MCP ``requirement.derive`` / REST
    ``/requirements/{id}/derive/`` both delegate here)."""

    def test_derive_requirement_inherits_parent_description_when_omitted(self):
        """No description passed → child inherits the parent's description."""
        svc = RequirementService()
        ctx = _make_ctx()
        mock_parent = _make_requirement(description="Parent description text")
        mock_child_req = _make_requirement(title="Child")
        mock_child_req.artifact = MagicMock()
        mock_child_req.artifact_id = uuid.uuid4()
        arch_el_id = uuid.uuid4()

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.requirement_service.Requirement.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=mock_parent)),
            ) as mock_plain_filter,
            patch(
                "application.requirement_service.Requirement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(first=MagicMock(return_value=mock_parent))
                    )
                ),
            ),
            patch.object(svc, "create_requirement", return_value=mock_child_req) as mock_create,
            patch("application.requirement_service.Workspace.objects.filter"),
            patch(
                "persistence.models.ArchitectureElement.objects.filter",
                return_value=MagicMock(
                    first=MagicMock(
                        return_value=MagicMock(artifact=MagicMock(workspace_id=WS_ID))
                    )
                ),
            ),
            patch.object(
                svc._trace_link_service, "create_trace_link", return_value=MagicMock(id=uuid.uuid4())
            ),
            patch.object(
                svc._trace_link_service, "allocate", return_value=MagicMock(id=uuid.uuid4())
            ),
        ):
            svc.derive_requirement(
                parent_requirement_id=REQ_ID,
                architecture_element_id=arch_el_id,
                title="Child",
                ctx=ctx,
            )

        mock_plain_filter.assert_called_once_with(id=REQ_ID)
        assert mock_create.call_args.kwargs["description"] == "Parent description text"

    def test_derive_requirement_keeps_explicit_description(self):
        """An explicitly passed description must not be overridden by the parent's."""
        svc = RequirementService()
        ctx = _make_ctx()
        mock_parent = _make_requirement(description="Parent description text")
        mock_child_req = _make_requirement(title="Child")
        mock_child_req.artifact = MagicMock()
        mock_child_req.artifact_id = uuid.uuid4()
        arch_el_id = uuid.uuid4()

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.ServiceBase._assert_write_permission"
            ),
            patch(
                "application.requirement_service.Requirement.objects.filter"
            ) as mock_plain_filter,
            patch(
                "application.requirement_service.Requirement.objects.select_related",
                return_value=MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(first=MagicMock(return_value=mock_parent))
                    )
                ),
            ),
            patch.object(svc, "create_requirement", return_value=mock_child_req) as mock_create,
            patch("application.requirement_service.Workspace.objects.filter"),
            patch(
                "persistence.models.ArchitectureElement.objects.filter",
                return_value=MagicMock(
                    first=MagicMock(
                        return_value=MagicMock(artifact=MagicMock(workspace_id=WS_ID))
                    )
                ),
            ),
            patch.object(
                svc._trace_link_service, "create_trace_link", return_value=MagicMock(id=uuid.uuid4())
            ),
            patch.object(
                svc._trace_link_service, "allocate", return_value=MagicMock(id=uuid.uuid4())
            ),
        ):
            svc.derive_requirement(
                parent_requirement_id=REQ_ID,
                architecture_element_id=arch_el_id,
                title="Child",
                ctx=ctx,
                description="Explicit child description",
            )

        # Explicit description present → the parent-description fallback lookup
        # must be skipped entirely.
        mock_plain_filter.assert_not_called()
        assert mock_create.call_args.kwargs["description"] == "Explicit child description"


# ---------------------------------------------------------------------------
# RequirementDTO
# ---------------------------------------------------------------------------


class TestValidateRequirement:
    """Issue #576: validate_artifact() returns a raw LlmResult dataclass on
    success (see its docstring), not a dict -- the service must serialise it
    into a structured JSON-able dict instead of falling back to str(result)
    (a stringified Python repr, unusable for API/MCP consumers)."""

    def test_validate_requirement_serialises_llm_result_to_dict(self):
        from llm_adapter.interface import LlmResult

        svc = RequirementService()
        ctx = _make_ctx()
        req_id = uuid.uuid4()
        llm_result = LlmResult(
            score=0.2,
            suggestions=["Add acceptance criteria"],
            provider="opencode_go",
            model="gpt-4",
            token_usage=42,
        )

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.Requirement.objects.filter"
            ) as mock_filter,
            patch(
                "llm_adapter.services.validate_artifact",
                return_value=llm_result,
            ),
        ):
            mock_filter.return_value.only.return_value.first.return_value = None
            result = svc.validate_requirement(req_id, ctx)

        assert result == {
            "score": 0.2,
            "suggestions": ["Add acceptance criteria"],
            "provider": "opencode_go",
            "model": "gpt-4",
            "token_usage": 42,
        }


class TestCheckConsistency:
    """REQ-089: check_consistency wiring + REQ-046 content forwarding."""

    def test_check_consistency_forwards_artifact_content(self):
        """Service collects each requirement's title/content and forwards them.

        Proves the capability is reachable (REQ-089) and that the provider
        receives real artifact text, not opaque IDs (REQ-046).
        """
        svc = RequirementService()
        ctx = _make_ctx()
        ws_id = uuid.uuid4()
        r1 = MagicMock(id=uuid.uuid4(), title="R1", description="body-1")
        r2 = MagicMock(id=uuid.uuid4(), title="R2", description="")

        rows = MagicMock()
        rows.exclude.return_value.only.return_value = [r1, r2]

        with (
            patch("application.requirement_service.ServiceBase._set_tenant_context"),
            patch(
                "application.requirement_service.Requirement.objects.filter",
                return_value=rows,
            ),
            patch(
                "llm_adapter.services.check_consistency",
                return_value={"task_id": "t-1"},
            ) as mock_cc,
        ):
            result = svc.check_consistency(ws_id, ctx)

        assert result == {"task_id": "t-1"}
        forwarded = mock_cc.call_args.kwargs["artifacts"]
        assert {"id": str(r1.id), "title": "R1", "content": "body-1"} in forwarded
        assert {"id": str(r2.id), "title": "R2", "content": ""} in forwarded


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


# ---------------------------------------------------------------------------
# Regression: list_requirements() must exclude requirements soft-deleted via
# workflow.services.outdate() (Phase 0 fix — outdate() mirrors "outdated"
# into `status`, not `lifecycle_status`).
# ---------------------------------------------------------------------------


@pytest.fixture
def req_outdate_tenant():
    from persistence.models import Tenant

    return Tenant.objects.create(name="req-outdate-tenant", slug="req-outdate-tenant")


@pytest.fixture
def req_outdate_user(req_outdate_tenant):
    from persistence.models import User

    return User.objects.create(
        username="req-outdate-user",
        email="req-outdate@example.com",
        tenant=req_outdate_tenant,
    )


@pytest.fixture
def req_outdate_workspace(req_outdate_tenant):
    from persistence.models import Workspace
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(req_outdate_tenant.id)
    try:
        return Workspace.objects.create(
            tenant=req_outdate_tenant, name="req-outdate-workspace"
        )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def req_outdate_ctx(req_outdate_user):
    from auth_tenancy.context import AuthContext

    return AuthContext(
        user_id=req_outdate_user.id,
        tenant_id=req_outdate_user.tenant.id,
        active_roles=("editor",),
        auth_method="test",
        api_key_id=None,
        tenant_name="req-outdate-tenant",
    )


class TestListRequirementsExcludesOutdated:
    """Phase 0 regression: deleted (outdated) Requirements must not reappear
    in list_requirements()."""

    def test_deleted_requirement_excluded_from_default_list(
        self, req_outdate_ctx, req_outdate_workspace
    ):
        from persistence.tenancy import TenantContext
        from workflow.models import WorkflowItemState
        from workflow.services import create_default_workflow

        TenantContext.set_tenant(req_outdate_workspace.tenant_id)
        try:
            create_default_workflow(
                workspace_id=req_outdate_workspace.id,
                preset="standard",
                item_type="Requirement",
                tenant_id=req_outdate_workspace.tenant_id,
            )
        finally:
            TenantContext.clear_tenant()

        svc = RequirementService()
        kept = svc.create_requirement(
            workspace_id=req_outdate_workspace.id,
            title="Kept Requirement",
            ctx=req_outdate_ctx,
        )
        deleted = svc.create_requirement(
            workspace_id=req_outdate_workspace.id,
            title="Deleted Requirement",
            ctx=req_outdate_ctx,
        )

        svc.delete_requirement(deleted.id, req_outdate_ctx)

        item_state = WorkflowItemState.objects.get(
            item_id=deleted.id, item_type="Requirement"
        )
        assert item_state.current_state == "outdated"

        results = svc.list_requirements(req_outdate_workspace.id, req_outdate_ctx)
        ids = {r.id for r in results}
        assert kept.id in ids
        assert deleted.id not in ids

        results_incl = svc.list_requirements(
            req_outdate_workspace.id, req_outdate_ctx, include_deleted=True
        )
        ids_incl = {r.id for r in results_incl}
        assert deleted.id in ids_incl


# ---------------------------------------------------------------------------
# Regression (Issue #267): GET /api/v1/requirements/?search=<term> silently
# ignored the ``search`` query parameter and returned every item in the
# workspace unfiltered — the RequirementViewSet.list() never read
# request.query_params["search"], and list_requirements() had no ``search``
# parameter at all. Fixed by threading ``search`` through to a
# title/description/uid icontains filter on the queryset.
# ---------------------------------------------------------------------------


class TestListRequirementsSearchFilter:
    """GET /api/v1/requirements/?workspace_id=...&search=<term> (Issue #267)."""

    def test_search_filters_by_title_case_insensitive(
        self, req_outdate_ctx, req_outdate_workspace
    ):
        svc = RequirementService()
        matching = svc.create_requirement(
            workspace_id=req_outdate_workspace.id,
            title="Payment Gateway Integration",
            ctx=req_outdate_ctx,
        )
        other = svc.create_requirement(
            workspace_id=req_outdate_workspace.id,
            title="Unrelated Requirement",
            ctx=req_outdate_ctx,
        )

        results = svc.list_requirements(
            req_outdate_workspace.id, req_outdate_ctx, search="payment gateway"
        )
        ids = {r.id for r in results}

        assert ids == {matching.id}
        assert other.id not in ids

    def test_search_filters_by_description(
        self, req_outdate_ctx, req_outdate_workspace
    ):
        svc = RequirementService()
        matching = svc.create_requirement(
            workspace_id=req_outdate_workspace.id,
            title="Req A",
            description="Handles OAuth token refresh.",
            ctx=req_outdate_ctx,
        )
        other = svc.create_requirement(
            workspace_id=req_outdate_workspace.id,
            title="Req B",
            description="Nothing related.",
            ctx=req_outdate_ctx,
        )

        results = svc.list_requirements(
            req_outdate_workspace.id, req_outdate_ctx, search="oauth"
        )
        ids = {r.id for r in results}

        assert ids == {matching.id}
        assert other.id not in ids

    def test_search_filters_by_uid(self, req_outdate_ctx, req_outdate_workspace):
        svc = RequirementService()
        matching = svc.create_requirement(
            workspace_id=req_outdate_workspace.id,
            title="Req A",
            ctx=req_outdate_ctx,
            uid="REQ-L1-SPECIAL-001",
        )
        other = svc.create_requirement(
            workspace_id=req_outdate_workspace.id,
            title="Req B",
            ctx=req_outdate_ctx,
            uid="REQ-L1-OTHER-002",
        )

        results = svc.list_requirements(
            req_outdate_workspace.id, req_outdate_ctx, search="special"
        )
        ids = {r.id for r in results}

        assert ids == {matching.id}
        assert other.id not in ids

    def test_search_term_that_looks_like_sqli_is_treated_as_literal_text(
        self, req_outdate_ctx, req_outdate_workspace
    ):
        """A SQLi-shaped search term must be treated as plain text (no items
        match) rather than being evaluated as SQL or ignored entirely."""
        svc = RequirementService()
        svc.create_requirement(
            workspace_id=req_outdate_workspace.id,
            title="Regular Requirement",
            ctx=req_outdate_ctx,
        )

        results = svc.list_requirements(
            req_outdate_workspace.id, req_outdate_ctx, search="' OR 1=1--"
        )

        assert list(results) == []

    def test_no_search_param_returns_all(
        self, req_outdate_ctx, req_outdate_workspace
    ):
        svc = RequirementService()
        a = svc.create_requirement(
            workspace_id=req_outdate_workspace.id, title="Req A", ctx=req_outdate_ctx
        )
        b = svc.create_requirement(
            workspace_id=req_outdate_workspace.id, title="Req B", ctx=req_outdate_ctx
        )

        results = svc.list_requirements(req_outdate_workspace.id, req_outdate_ctx)
        ids = {r.id for r in results}

        assert {a.id, b.id} <= ids
