"""
Tests for COMP-AS-005 TraceLinkService.

leaf_id : COMP-AS-005
req_id  : REQ-L2-AS-010 (TraceLink Orchestration)

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
from application.trace_link_service import TraceLinkService, VALID_LINK_TYPES


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
        "traces",
        "copy-of",
    }

    def test_all_eight_types_present(self):
        """VALID_LINK_TYPES contains all 8 expected link types."""
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

    @pytest.mark.parametrize("link_type", list(VALID_LINK_TYPES))
    def test_all_valid_link_types_accepted(self, link_type):
        """All 8 standard link types pass validation and delegate to TE."""
        svc = TraceLinkService()
        ctx = _make_ctx()
        mock_result = MagicMock()
        mock_result.id = uuid.uuid4()

        with (
            patch("application.trace_link_service.ServiceBase._set_tenant_context"),
            patch(
                "application.trace_link_service.TraceLinkService._audit"
            ),
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


# ---------------------------------------------------------------------------
# query_trace_links
# ---------------------------------------------------------------------------


class TestQueryTraceLinks:
    """REQ-L2-AS-010."""

    def test_query_delegates_to_traceability_engine(self):
        """query_trace_links calls traceability.services.query."""
        svc = TraceLinkService()
        ctx = _make_ctx()
        mock_results = [MagicMock(), MagicMock()]

        with (
            patch("application.trace_link_service.ServiceBase._set_tenant_context"),
            patch(
                "traceability.services.query", return_value=mock_results
            ) as mock_query,
        ):
            result = svc.query_trace_links(
                entity_id=SOURCE_ID, direction="downstream", ctx=ctx
            )

        mock_query.assert_called_once_with(
            artifact_id=SOURCE_ID, direction="downstream"
        )
        assert result == mock_results

    def test_query_filters_by_link_type(self):
        """query_trace_links filters results by link_type when provided."""
        svc = TraceLinkService()
        ctx = _make_ctx()

        item_verifies = MagicMock()
        item_verifies.link_type = "verifies"
        item_implements = MagicMock()
        item_implements.link_type = "implements"

        with (
            patch("application.trace_link_service.ServiceBase._set_tenant_context"),
            patch(
                "traceability.services.query",
                return_value=[item_verifies, item_implements],
            ),
        ):
            result = svc.query_trace_links(
                entity_id=SOURCE_ID,
                direction="downstream",
                link_type="verifies",
                ctx=ctx,
            )

        assert result == [item_verifies]

    def test_query_without_ctx_skips_tenant_context(self):
        """query_trace_links can be called with ctx=None (no tenant propagation)."""
        svc = TraceLinkService()
        mock_results: list = []

        with patch(
            "traceability.services.query", return_value=mock_results
        ):
            result = svc.query_trace_links(
                entity_id=SOURCE_ID, direction="upstream", ctx=None
            )

        assert result == []
