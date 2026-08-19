"""
Tests for COMP-AS-005 TraceLinkService.

leaf_id : COMP-AS-005
req_id  : REQ-L2-AS-010 (TraceLink Orchestration)

Note (#625): ``create_trace_link`` resolves its endpoints through
``_resolve_artifact`` (returns the id *and* the already-loaded Artifact row)
rather than ``_resolve_artifact_id``, so the endpoint checks can reuse the row
instead of re-SELECTing it. Stubs below therefore patch ``_resolve_artifact``
and return ``(id, None)``; read paths still patch ``_resolve_artifact_id``.

Coverage:
  - create_trace_link: all 8 valid types accepted, invalid type raises ValidationError,
    SourceNotFoundError → NotFoundError, TargetNotFoundError → NotFoundError,
    cross-workspace message → ValidationError, audit entry produced
  - cascade_delete_trace_links: delegates to traceability.services, returns count
  - query_trace_links: delegates with direction and optional link_type filter
  - VALID_LINK_TYPES constant contains the 8 expected types
  - Tenant isolation: _set_tenant_context called
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.base import NotFoundError, ValidationError
from application.trace_link_service import (
    TraceLinkService,
    VALID_LINK_TYPES,
    MANUAL_LINK_TYPES,
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


SOURCE_ID = uuid.uuid4()
TARGET_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# VALID_LINK_TYPES
# ---------------------------------------------------------------------------


class TestValidLinkTypes:
    """REQ-L2-AS-010: 8 standard link types."""

    EXPECTED_TYPES = {
        "parent-child",
        "derives-from",
        "satisfies",
        "verifies",
        "implements",
        "refines",
        "documents",
        "realizes",
        "traces",
        "copy-of",
        "allocated-to",  # REQ-L1-042
        "uses-term",
        "decides",  # REQ-L2-TE-020 (ADR -> ArchitectureElement)
        "decomposes",  # UMSETZUNGSPLAN_SYSENG_2.0.md §1.4 — hardcoded decompose() output
        "diagram-ref",  # Codeberg #353 Task 3 — reconciler-owned only, see traceability/types.py
    }

    def test_all_ten_types_present(self):
        """VALID_LINK_TYPES contains all harmonized link types (incl. REQ-L1-042)."""
        assert self.EXPECTED_TYPES == VALID_LINK_TYPES

    def test_types_is_frozenset(self):
        """VALID_LINK_TYPES is a frozenset (immutable)."""
        assert isinstance(VALID_LINK_TYPES, frozenset)


# ---------------------------------------------------------------------------
# create_trace_link
# ---------------------------------------------------------------------------


class TestCreateTraceLink:
    """REQ-L2-AS-010."""

    def test_invalid_link_type_raises_validation_error(self):
        """ValidationError for unrecognised link_type."""
        svc = TraceLinkService()
        ctx = _make_ctx()

        with patch("application.trace_link_service.ServiceBase._set_tenant_context"):
            with pytest.raises(ValidationError, match="Invalid link type"):
                svc.create_trace_link(
                    source_id=SOURCE_ID,
                    target_id=TARGET_ID,
                    link_type="made-up-type",
                    ctx=ctx,
                )

    def test_diagram_ref_link_type_raises_validation_error(self):
        """I1 (Codeberg #353 final review): 'diagram-ref' IS a member of
        VALID_LINK_TYPES (the reconciler needs it there) but must never be
        creatable through manual TraceLink CRUD — a hand-authored one would
        be silently deleted on the diagram's next node_graph save. This is a
        distinct rejection reason from an unrecognised link_type, so it is
        checked before source/target resolution, same as the invalid-type
        check above."""
        svc = TraceLinkService()
        ctx = _make_ctx()

        with patch("application.trace_link_service.ServiceBase._set_tenant_context"):
            with pytest.raises(ValidationError, match="system-managed"):
                svc.create_trace_link(
                    source_id=SOURCE_ID,
                    target_id=TARGET_ID,
                    link_type="diagram-ref",
                    ctx=ctx,
                )

    @pytest.mark.parametrize("link_type", sorted(MANUAL_LINK_TYPES))
    def test_all_valid_link_types_accepted(self, link_type):
        """All manually-createable link types pass validation and delegate to
        TE. Excludes 'diagram-ref' (I1) — covered separately above by
        test_diagram_ref_link_type_raises_validation_error."""
        svc = TraceLinkService()
        ctx = _make_ctx()
        mock_result = MagicMock()
        mock_result.id = uuid.uuid4()

        with (
            patch("application.trace_link_service.ServiceBase._set_tenant_context"),
            patch.object(svc, "_resolve_artifact", side_effect=lambda x: (x, None)),
            patch(
                "application.trace_link_service.TraceLinkService._audit"
            ),
            # REQ-L1-044: allocated-to runs the I4 invariant hook (ORM-backed);
            # neutralized here, covered by TestAllocationInvariantHook below.
            patch.object(svc, "_check_allocation_invariant"),
            patch(
                "traceability.services.create_trace_link",
                return_value=mock_result,
            ) as mock_te_create,
        ):
            result = svc.create_trace_link(
                source_id=SOURCE_ID,
                target_id=TARGET_ID,
                link_type=link_type,
                ctx=ctx,
            )

        mock_te_create.assert_called_once_with(
            source_id=SOURCE_ID,
            target_id=TARGET_ID,
            link_type=link_type,
            created_by_id=ctx.user_id,
        )
        assert result is mock_result

    def test_source_not_found_remapped_to_not_found_error(self):
        """SourceNotFoundError from TraceabilityEngine → NotFoundError."""
        from traceability.services import SourceNotFoundError

        svc = TraceLinkService()
        ctx = _make_ctx()

        with (
            patch("application.trace_link_service.ServiceBase._set_tenant_context"),
            patch.object(svc, "_resolve_artifact", side_effect=lambda x: (x, None)),
            patch(
                "traceability.services.create_trace_link",
                side_effect=SourceNotFoundError("not found"),
            ),
        ):
            with pytest.raises(NotFoundError, match="Source entity"):
                svc.create_trace_link(
                    source_id=SOURCE_ID,
                    target_id=TARGET_ID,
                    link_type="verifies",
                    ctx=ctx,
                )

    def test_target_not_found_remapped_to_not_found_error(self):
        """TargetNotFoundError from TraceabilityEngine → NotFoundError."""
        svc = TraceLinkService()
        ctx = _make_ctx()

        with (
            patch("application.trace_link_service.ServiceBase._set_tenant_context"),
            patch.object(svc, "_resolve_artifact", side_effect=lambda x: (x, None)),
        ):
            from traceability.services import TargetNotFoundError

            with patch(
                "traceability.services.create_trace_link",
                side_effect=TargetNotFoundError("not found"),
            ):
                with pytest.raises(NotFoundError, match="Target entity"):
                    svc.create_trace_link(
                        source_id=SOURCE_ID,
                        target_id=TARGET_ID,
                        link_type="verifies",
                        ctx=ctx,
                    )

    def test_cross_workspace_error_remapped_to_validation_error(self):
        """Exception with 'cross' in message → ValidationError."""
        svc = TraceLinkService()
        ctx = _make_ctx()

        with (
            patch("application.trace_link_service.ServiceBase._set_tenant_context"),
            patch.object(svc, "_resolve_artifact", side_effect=lambda x: (x, None)),
            patch(
                "traceability.services.create_trace_link",
                side_effect=Exception("cross-workspace link not permitted"),
            ),
        ):
            with pytest.raises(ValidationError, match="Cross-workspace"):
                svc.create_trace_link(
                    source_id=SOURCE_ID,
                    target_id=TARGET_ID,
                    link_type="verifies",
                    ctx=ctx,
                )

    def test_audit_called_on_create(self):
        """_audit is called with operation='create', entity_type='TraceLink'."""
        svc = TraceLinkService()
        ctx = _make_ctx()
        mock_result = MagicMock()
        mock_result.id = uuid.uuid4()

        with (
            patch("application.trace_link_service.ServiceBase._set_tenant_context"),
            patch.object(svc, "_resolve_artifact", side_effect=lambda x: (x, None)),
            patch(
                "traceability.services.create_trace_link", return_value=mock_result
            ),
            patch.object(svc, "_audit") as mock_audit,
        ):
            svc.create_trace_link(
                source_id=SOURCE_ID,
                target_id=TARGET_ID,
                link_type="implements",
                ctx=ctx,
            )

        mock_audit.assert_called_once()
        kw = mock_audit.call_args.kwargs
        assert kw["operation"] == "create"
        assert kw["entity_type"] == "TraceLink"

    def test_tenant_context_set_on_create(self):
        """_set_tenant_context is called before validation."""
        svc = TraceLinkService()
        ctx = _make_ctx(tenant_id=uuid.uuid4())

        with (
            patch(
                "application.trace_link_service.ServiceBase._set_tenant_context"
            ) as mock_stc,
            patch.object(svc, "_resolve_artifact", side_effect=lambda x: (x, None)),
        ):
            with pytest.raises(ValidationError):
                svc.create_trace_link(
                    source_id=SOURCE_ID,
                    target_id=TARGET_ID,
                    link_type="bad",
                    ctx=ctx,
                )

        mock_stc.assert_called_once_with(ctx)


# ---------------------------------------------------------------------------
# cascade_delete_trace_links
# ---------------------------------------------------------------------------


class TestCascadeDeleteTraceLinks:
    """ADR-L3-AS005-02: runs in caller TX; IF-AS-INT-001/004/005."""

    def test_returns_zero_when_no_links(self):
        """cascade_delete_trace_links returns 0 when no links found."""
        svc = TraceLinkService()
        ctx = _make_ctx()

        with (
            patch("application.trace_link_service.ServiceBase._set_tenant_context"),
            patch(
                "traceability.services.query",
                return_value=[],
            ),
            patch("traceability.types.Direction", create=True),
        ):
            count = svc.cascade_delete_trace_links(SOURCE_ID, ctx)

        assert count == 0

    def test_deletes_all_upstream_and_downstream_links(self):
        """cascade_delete_trace_links calls batch_delete with collected link IDs."""
        svc = TraceLinkService()
        ctx = _make_ctx()

        link_id_1 = uuid.uuid4()
        link_id_2 = uuid.uuid4()

        upstream_item = MagicMock()
        upstream_item.link_id = link_id_1

        downstream_item = MagicMock()
        downstream_item.link_id = link_id_2

        def mock_query(artifact_id, direction, transitive):
            if direction == "upstream":
                return [upstream_item]
            return [downstream_item]

        with (
            patch("application.trace_link_service.ServiceBase._set_tenant_context"),
            patch("traceability.services.query", side_effect=mock_query),
            patch(
                "traceability.services.batch_delete_trace_links", return_value=2
            ) as mock_batch,
            patch("traceability.types.Direction", create=True),
        ):
            count = svc.cascade_delete_trace_links(SOURCE_ID, ctx)

        mock_batch.assert_called_once()
        call_args = mock_batch.call_args[0][0]
        assert link_id_1 in call_args
        assert link_id_2 in call_args
        assert count == 2


class TestDeleteTraceLink:
    """Codeberg #336: DELETE /api/v1/trace-links/{id}/ must actually delete
    the TraceLink identified by its own id (not treat it as an entity id)."""

    def test_deletes_link_via_manager(self):
        """delete_trace_link delegates to TraceLinkManager.delete(link_id)."""
        svc = TraceLinkService()
        ctx = _make_ctx()
        link_id = uuid.uuid4()

        mock_manager = MagicMock()
        with (
            patch("application.trace_link_service.ServiceBase._set_tenant_context"),
            patch(
                "traceability.trace_link_manager.TraceLinkManager",
                return_value=mock_manager,
            ),
        ):
            svc.delete_trace_link(link_id, ctx)

        mock_manager.delete.assert_called_once_with(link_id)

    def test_missing_link_raises_not_found_error(self):
        """TraceLink.DoesNotExist from the manager is remapped to NotFoundError."""
        from persistence.models import TraceLink

        svc = TraceLinkService()
        ctx = _make_ctx()
        link_id = uuid.uuid4()

        mock_manager = MagicMock()
        mock_manager.delete.side_effect = TraceLink.DoesNotExist()
        with (
            patch("application.trace_link_service.ServiceBase._set_tenant_context"),
            patch(
                "traceability.trace_link_manager.TraceLinkManager",
                return_value=mock_manager,
            ),
        ):
            with pytest.raises(NotFoundError):
                svc.delete_trace_link(link_id, ctx)

    def test_tenant_context_set_before_delete(self):
        """_set_tenant_context runs before the manager delete call."""
        svc = TraceLinkService()
        ctx = _make_ctx()
        link_id = uuid.uuid4()

        mock_manager = MagicMock()
        with (
            patch(
                "application.trace_link_service.ServiceBase._set_tenant_context"
            ) as mock_set_ctx,
            patch(
                "traceability.trace_link_manager.TraceLinkManager",
                return_value=mock_manager,
            ),
        ):
            svc.delete_trace_link(link_id, ctx)

        mock_set_ctx.assert_called_once_with(ctx)


# ---------------------------------------------------------------------------
# query_trace_links
# ---------------------------------------------------------------------------


class TestQueryTraceLinks:
    """REQ-L2-AS-010."""

    def test_query_delegates_to_traceability_engine(self):
        """query_trace_links resolves entity_id and calls traceability.services.query."""
        svc = TraceLinkService()
        ctx = _make_ctx()
        mock_results = [MagicMock(), MagicMock()]
        resolved_id = uuid.uuid4()

        with (
            patch("application.trace_link_service.ServiceBase._set_tenant_context"),
            patch.object(
                svc, "_resolve_artifact_id", return_value=resolved_id
            ) as mock_resolve,
            patch(
                "traceability.services.query", return_value=mock_results
            ) as mock_query,
        ):
            result = svc.query_trace_links(
                entity_id=SOURCE_ID, direction="downstream", ctx=ctx
            )

        mock_resolve.assert_called_once_with(SOURCE_ID)
        mock_query.assert_called_once_with(
            artifact_id=resolved_id, direction="downstream"
        )
        assert result == mock_results

    def test_query_filters_by_link_type(self):
        """query_trace_links filters results by link_type when provided."""
        svc = TraceLinkService()
        ctx = _make_ctx()
        resolved_id = uuid.uuid4()

        item_verifies = MagicMock()
        item_verifies.link_type = "verifies"
        item_implements = MagicMock()
        item_implements.link_type = "implements"

        with (
            patch("application.trace_link_service.ServiceBase._set_tenant_context"),
            patch.object(
                svc, "_resolve_artifact_id", return_value=resolved_id
            ) as mock_resolve,
            patch(
                "traceability.services.query",
                return_value=[item_verifies, item_implements],
            ) as mock_query,
        ):
            result = svc.query_trace_links(
                entity_id=SOURCE_ID,
                direction="downstream",
                link_type="verifies",
                ctx=ctx,
            )

        mock_resolve.assert_called_once_with(SOURCE_ID)
        mock_query.assert_called_once_with(
            artifact_id=resolved_id, direction="downstream"
        )
        assert result == [item_verifies]

    def test_query_without_ctx_skips_tenant_context(self):
        """query_trace_links can be called with ctx=None (no tenant propagation)."""
        svc = TraceLinkService()
        mock_results: list = []
        resolved_id = uuid.uuid4()

        with (
            patch.object(
                svc, "_resolve_artifact_id", return_value=resolved_id
            ) as mock_resolve,
            patch(
                "traceability.services.query", return_value=mock_results
            ) as mock_query,
        ):
            result = svc.query_trace_links(
                entity_id=SOURCE_ID, direction="upstream", ctx=None
            )

        mock_resolve.assert_called_once_with(SOURCE_ID)
        mock_query.assert_called_once_with(
            artifact_id=resolved_id, direction="upstream"
        )
        assert result == []


# ---------------------------------------------------------------------------
# _resolve_artifact_id (B-TR-002)
# ---------------------------------------------------------------------------


class TestResolveArtifactId:
    """B-TR-002: Requirement/ArchitectureElement IDs resolve to Artifact IDs."""

    def test_artifact_id_returned_unchanged(self):
        """An existing Artifact ID is returned as-is."""
        svc = TraceLinkService()
        artifact_id = uuid.uuid4()
        mock_artifact = MagicMock()

        with patch(
            "persistence.models.Artifact.objects.filter",
            return_value=MagicMock(first=MagicMock(return_value=mock_artifact)),
        ) as artifact_filter:
            result = svc._resolve_artifact_id(artifact_id)

        artifact_filter.assert_called_once_with(id=artifact_id)
        assert result == artifact_id

    def test_requirement_id_resolves_to_artifact_id(self):
        """A Requirement ID resolves to its backing Artifact ID."""
        svc = TraceLinkService()
        requirement_id = uuid.uuid4()
        artifact_id = uuid.uuid4()
        mock_req = MagicMock()
        mock_req.artifact_id = artifact_id

        with (
            patch(
                "persistence.models.Artifact.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
            patch(
                "persistence.models.Requirement.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=mock_req)),
            ) as req_filter,
        ):
            result = svc._resolve_artifact_id(requirement_id)

        req_filter.assert_called_once_with(id=requirement_id)
        assert result == artifact_id

    def test_architecture_element_id_resolves_to_artifact_id(self):
        """An ArchitectureElement ID resolves to its backing Artifact ID."""
        svc = TraceLinkService()
        arch_id = uuid.uuid4()
        artifact_id = uuid.uuid4()
        mock_arch = MagicMock()
        mock_arch.artifact_id = artifact_id

        with (
            patch(
                "persistence.models.Artifact.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
            patch(
                "persistence.models.Requirement.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
            patch(
                "persistence.models.ArchitectureElement.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=mock_arch)),
            ) as arch_filter,
        ):
            result = svc._resolve_artifact_id(arch_id)

        arch_filter.assert_called_once_with(id=arch_id)
        assert result == artifact_id

    def test_adr_id_resolves_to_artifact_id(self):
        """REQ-L2-TE-020: An ADR ID resolves to its backing Artifact ID."""
        svc = TraceLinkService()
        adr_id = uuid.uuid4()
        artifact_id = uuid.uuid4()
        mock_adr = MagicMock()
        mock_adr.artifact_id = artifact_id

        with (
            patch(
                "persistence.models.Artifact.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
            patch(
                "persistence.models.Requirement.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
            patch(
                "persistence.models.ArchitectureElement.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
            patch(
                "application.models.Adr.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=mock_adr)),
            ) as adr_filter,
        ):
            result = svc._resolve_artifact_id(adr_id)

        adr_filter.assert_called_once_with(id=adr_id)
        assert result == artifact_id

    def test_goal_id_resolves_to_artifact_id(self):
        """fix #237: A Goal ID resolves to its backing Artifact ID.

        Previously Goal was missing from ``_resolve_artifact_id``'s
        resolution chain, so any Goal<->Requirement TraceLink raised
        NotFoundError("Entity ... not found") even though every Goal has
        its own dedicated Artifact row (GoalService.create_version).
        """
        svc = TraceLinkService()
        goal_id = uuid.uuid4()
        artifact_id = uuid.uuid4()
        mock_goal = MagicMock()
        mock_goal.artifact_id = artifact_id

        with (
            patch(
                "persistence.models.Artifact.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
            patch(
                "persistence.models.Requirement.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
            patch(
                "persistence.models.ArchitectureElement.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
            patch(
                "application.models.Adr.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
            patch(
                "application.models.Goal.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=mock_goal)),
            ) as goal_filter,
        ):
            result = svc._resolve_artifact_id(goal_id)

        goal_filter.assert_called_once_with(id=goal_id)
        assert result == artifact_id

    def test_main_goal_id_resolves_to_artifact_id(self):
        """fix #237: A MainGoal ID resolves to its backing Artifact ID."""
        svc = TraceLinkService()
        main_goal_id = uuid.uuid4()
        artifact_id = uuid.uuid4()
        mock_main_goal = MagicMock()
        mock_main_goal.artifact_id = artifact_id

        with (
            patch(
                "persistence.models.Artifact.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
            patch(
                "persistence.models.Requirement.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
            patch(
                "persistence.models.ArchitectureElement.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
            patch(
                "application.models.Adr.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
            patch(
                "application.models.Goal.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
            patch(
                "application.models.MainGoal.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=mock_main_goal)),
            ) as main_goal_filter,
        ):
            result = svc._resolve_artifact_id(main_goal_id)

        main_goal_filter.assert_called_once_with(id=main_goal_id)
        assert result == artifact_id

    def test_unknown_id_raises_not_found_error(self):
        """An ID matching none of the tables raises NotFoundError."""
        svc = TraceLinkService()
        unknown_id = uuid.uuid4()

        with (
            patch(
                "persistence.models.Artifact.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
            patch(
                "persistence.models.Requirement.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
            patch(
                "persistence.models.ArchitectureElement.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
            patch(
                "application.models.Adr.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
            patch(
                "application.models.Goal.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
            patch(
                "application.models.MainGoal.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
            # fix #264: TestCase/StakeholderNeed joined the resolution chain.
            patch(
                "persistence.models.TestCase.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
            patch(
                "persistence.models.StakeholderNeed.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
            # fix #407: Risk/Issue joined the resolution chain.
            patch(
                "application.models.Risk.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
            patch(
                "application.models.Issue.objects.filter",
                return_value=MagicMock(first=MagicMock(return_value=None)),
            ),
        ):
            with pytest.raises(NotFoundError, match="Entity"):
                svc._resolve_artifact_id(unknown_id)

    def test_create_trace_link_resolves_source_and_target(self):
        """create_trace_link passes resolved Artifact IDs to the engine."""
        svc = TraceLinkService()
        ctx = _make_ctx()
        source_artifact_id = uuid.uuid4()
        target_artifact_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.id = uuid.uuid4()

        # #625: create_trace_link resolves through _resolve_artifact, which
        # returns (artifact_id, artifact_row_or_None).
        def _resolve_side_effect(entity_id):
            if entity_id == SOURCE_ID:
                return source_artifact_id, None
            if entity_id == TARGET_ID:
                return target_artifact_id, None
            return entity_id, None

        with (
            patch("application.trace_link_service.ServiceBase._set_tenant_context"),
            patch.object(
                svc, "_resolve_artifact", side_effect=_resolve_side_effect
            ) as mock_resolve,
            patch(
                "application.trace_link_service.TraceLinkService._audit"
            ),
            patch(
                "traceability.services.create_trace_link",
                return_value=mock_result,
            ) as mock_te_create,
        ):
            svc.create_trace_link(
                source_id=SOURCE_ID,
                target_id=TARGET_ID,
                link_type="verifies",
                ctx=ctx,
            )

        assert mock_resolve.call_count == 2
        mock_te_create.assert_called_once_with(
            source_id=source_artifact_id,
            target_id=target_artifact_id,
            link_type="verifies",
            created_by_id=ctx.user_id,
        )


# ---------------------------------------------------------------------------
# Allocation invariant I4 hook (REQ-L1-044)
# ---------------------------------------------------------------------------


class TestAllocationInvariantHook:
    """REQ-L1-044: create_trace_link routes allocated-to through I4."""

    def _create(self, svc, ctx, link_type):
        mock_result = MagicMock()
        mock_result.id = uuid.uuid4()
        with (
            patch("application.trace_link_service.ServiceBase._set_tenant_context"),
            patch.object(svc, "_resolve_artifact", side_effect=lambda x: (x, None)),
            patch("application.trace_link_service.TraceLinkService._audit"),
            patch.object(svc, "_check_allocation_invariant") as mock_check,
            patch(
                "traceability.services.create_trace_link",
                return_value=mock_result,
            ),
        ):
            svc.create_trace_link(
                source_id=SOURCE_ID,
                target_id=TARGET_ID,
                link_type=link_type,
                ctx=ctx,
            )
        return mock_check

    def test_allocated_to_link_runs_invariant_check(self):
        svc = TraceLinkService()
        mock_check = self._create(svc, _make_ctx(), "allocated-to")
        mock_check.assert_called_once_with(SOURCE_ID, TARGET_ID)

    def test_other_link_types_skip_invariant_check(self):
        svc = TraceLinkService()
        mock_check = self._create(svc, _make_ctx(), "verifies")
        mock_check.assert_not_called()

    def test_check_delegates_to_validator_for_element_pairs(self):
        """Both endpoints are ArchitectureElements → validate_allocation runs."""
        svc = TraceLinkService()
        source_el = MagicMock()
        target_el = MagicMock()
        qs = MagicMock()
        qs.select_related.return_value.filter.return_value.first.return_value = (
            source_el
        )
        qs.filter.return_value.first.return_value = target_el

        with (
            patch(
                "persistence.models.ArchitectureElement.objects",
                qs,
            ),
            patch(
                "application.validators.ArchitectureElementInvariantValidator"
                ".for_workspace"
            ) as mock_for_ws,
        ):
            svc._check_allocation_invariant(SOURCE_ID, TARGET_ID)

        mock_for_ws.assert_called_once_with(source_el.artifact.workspace_id)
        mock_for_ws.return_value.validate_allocation.assert_called_once_with(
            source_element=source_el, target_element=target_el
        )

    def test_check_skips_when_endpoint_is_not_an_element(self):
        """Requirement → ArchitectureElement allocations are unaffected."""
        svc = TraceLinkService()
        qs = MagicMock()
        qs.select_related.return_value.filter.return_value.first.return_value = None
        qs.filter.return_value.first.return_value = MagicMock()

        with (
            patch("persistence.models.ArchitectureElement.objects", qs),
            patch(
                "application.validators.ArchitectureElementInvariantValidator"
                ".for_workspace"
            ) as mock_for_ws,
        ):
            svc._check_allocation_invariant(SOURCE_ID, TARGET_ID)

        mock_for_ws.assert_not_called()


# ---------------------------------------------------------------------------
# propagate_suspect_status (SN-30)
# ---------------------------------------------------------------------------


class TestPropagateSuspectStatus:
    """SN-30: suspect status propagates to DEPENDENTS via INCOMING edges.

    Dependents are the SOURCES of links whose TARGET is the changed artifact
    (TC --verifies--> Req, ChildReq --derives-from--> ParentReq), i.e. the
    ``upstream`` transitive closure.
    """

    def test_traverses_incoming_edges_and_marks_dependents(self):
        """query() is called upstream+transitive; dependents flagged suspect."""
        svc = TraceLinkService()
        ctx = _make_ctx()
        resolved = uuid.uuid4()
        dep_1 = uuid.uuid4()
        dep_2 = uuid.uuid4()

        result_1 = MagicMock(entity_id=dep_1, depth=1)
        result_2 = MagicMock(entity_id=dep_2, depth=2)

        req_qs = MagicMock()
        arch_qs = MagicMock()
        tc_qs = MagicMock()

        with (
            patch("application.trace_link_service.ServiceBase._set_tenant_context"),
            patch.object(svc, "_resolve_artifact_id", return_value=resolved),
            patch(
                "traceability.services.query",
                return_value=[result_1, result_2],
            ) as mock_query,
            patch("persistence.models.Requirement") as mock_req,
            patch("persistence.models.ArchitectureElement") as mock_arch,
            patch("persistence.models.TestCase") as mock_tc,
        ):
            mock_req.objects.filter.return_value = req_qs
            mock_arch.objects.filter.return_value = arch_qs
            mock_tc.objects.filter.return_value = tc_qs

            svc.propagate_suspect_status(SOURCE_ID, ctx)

        # INCOMING edges = upstream direction, full transitive closure.
        mock_query.assert_called_once_with(
            artifact_id=resolved, direction="upstream", transitive=True
        )
        flagged = mock_req.objects.filter.call_args.kwargs["artifact_id__in"]
        assert dep_1 in flagged
        assert dep_2 in flagged
        assert resolved not in flagged  # source itself is never flagged
        req_qs.update.assert_called_once_with(suspect=True)
        arch_qs.update.assert_called_once_with(suspect=True)
        tc_qs.update.assert_called_once_with(suspect=True)

    def test_respects_configured_max_depth(self, settings):
        """SUSPECT_PROPAGATION_MAX_DEPTH bounds the traversal when set."""
        svc = TraceLinkService()
        ctx = _make_ctx()
        settings.SUSPECT_PROPAGATION_MAX_DEPTH = 1

        near = uuid.uuid4()
        far = uuid.uuid4()
        near_result = MagicMock(entity_id=near, depth=1)
        far_result = MagicMock(entity_id=far, depth=2)

        req_qs = MagicMock()

        with (
            patch("application.trace_link_service.ServiceBase._set_tenant_context"),
            patch.object(svc, "_resolve_artifact_id", return_value=uuid.uuid4()),
            patch(
                "traceability.services.query",
                return_value=[near_result, far_result],
            ),
            patch("persistence.models.Requirement") as mock_req,
            patch("persistence.models.ArchitectureElement"),
            patch("persistence.models.TestCase"),
        ):
            mock_req.objects.filter.return_value = req_qs
            svc.propagate_suspect_status(SOURCE_ID, ctx)

        flagged = mock_req.objects.filter.call_args.kwargs["artifact_id__in"]
        assert near in flagged
        assert far not in flagged  # beyond configured depth

    def test_missing_source_returns_without_query(self):
        """A source that resolves to nothing is a no-op (no traversal)."""
        svc = TraceLinkService()
        ctx = _make_ctx()

        with (
            patch("application.trace_link_service.ServiceBase._set_tenant_context"),
            patch.object(
                svc, "_resolve_artifact_id", side_effect=NotFoundError("x")
            ),
            patch("traceability.services.query") as mock_query,
        ):
            svc.propagate_suspect_status(SOURCE_ID, ctx)

        mock_query.assert_not_called()

    def test_reraises_and_logs_on_error(self):
        """Traversal errors are logged with a stack trace and re-raised."""
        svc = TraceLinkService()
        ctx = _make_ctx()

        with (
            patch("application.trace_link_service.ServiceBase._set_tenant_context"),
            patch.object(svc, "_resolve_artifact_id", return_value=uuid.uuid4()),
            patch(
                "traceability.services.query",
                side_effect=RuntimeError("boom"),
            ),
            patch("application.trace_link_service.logger") as mock_logger,
        ):
            with pytest.raises(RuntimeError, match="boom"):
                svc.propagate_suspect_status(SOURCE_ID, ctx)

        mock_logger.exception.assert_called_once()
