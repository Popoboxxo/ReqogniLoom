"""Regression tests for GitHub issue #264 — TraceLinkService entity resolution
and error mapping.

leaf_id : COMP-AS-005
req_id  : REQ-L2-AS-010

Three findings are covered here at the unit level (no DB — the resolution
chain and the exception mapping are pure branching logic):

  Befund A  TestCase and StakeholderNeed were missing from
            ``_resolve_artifact_id``, so ``traceability.create_link`` answered
            404 for ``verifies`` (Requirement -> TestCase) and ``derives-from``
            (Requirement -> StakeholderNeed) — the very pairs the SE endpoint
            matrix declares legal.
  Befund C  ``CycleDetectedError`` and friends derive from ``Exception``, not
            from this layer's ``ValidationError``, and travelled unmapped out
            of the MCP tool as an opaque HTTP 500.

Befund B (persistence round-trip) needs a real database and lives in
``mcp_server/tests/test_traceability_link_issue264.py``.
"""
from __future__ import annotations

import uuid
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from application.base import NotFoundError, ValidationError
from application.trace_link_service import TraceLinkService

SOURCE_ID = uuid.uuid4()
TARGET_ID = uuid.uuid4()


def _make_ctx(*, roles=("editor",), tenant_id=None, user_id=None):
    """Mirror the AuthContext stub used by test_trace_link_service.py."""
    ctx = MagicMock()
    ctx.active_roles = roles
    ctx.tenant_id = tenant_id or uuid.uuid4()
    ctx.user_id = user_id or uuid.uuid4()
    ctx.has_role = lambda role: role in roles
    return ctx


def _miss(stack: ExitStack, *model_paths: str) -> None:
    """Patch every *model_paths* ``objects.filter`` to yield no match."""
    for path in model_paths:
        stack.enter_context(
            patch(path, return_value=MagicMock(first=MagicMock(return_value=None)))
        )


def _hit(stack: ExitStack, path: str, obj):
    """Patch *path* ``objects.filter`` to yield *obj*; return the mock."""
    return stack.enter_context(
        patch(path, return_value=MagicMock(first=MagicMock(return_value=obj)))
    )


#: Everything probed before TestCase / StakeholderNeed in the chain.
_EARLIER_MODELS = (
    "persistence.models.Artifact.objects.filter",
    "persistence.models.Requirement.objects.filter",
    "persistence.models.ArchitectureElement.objects.filter",
    "application.models.Adr.objects.filter",
    "application.models.Goal.objects.filter",
    "application.models.MainGoal.objects.filter",
)

_TEST_CASE_PATH = "persistence.models.TestCase.objects.filter"
_NEED_PATH = "persistence.models.StakeholderNeed.objects.filter"


# ---------------------------------------------------------------------------
# Befund A — TestCase / StakeholderNeed resolution
# ---------------------------------------------------------------------------


class TestResolveTestCaseAndNeed:
    """#264 Befund A: both entity types must resolve to their Artifact."""

    def test_test_case_id_resolves_to_artifact_id(self):
        """A TestCase ID resolves to its backing Artifact ID.

        Before the fix this raised NotFoundError("Entity ... not found"),
        which the MCP tool reported as a 404 even though
        ``GET /testcases/{id}`` returned 200 for the same id.
        """
        svc = TraceLinkService()
        test_case_id = uuid.uuid4()
        artifact_id = uuid.uuid4()
        mock_tc = MagicMock()
        mock_tc.artifact_id = artifact_id

        with ExitStack() as stack:
            _miss(stack, *_EARLIER_MODELS)
            tc_filter = _hit(stack, _TEST_CASE_PATH, mock_tc)
            result = svc._resolve_artifact_id(test_case_id)

        tc_filter.assert_called_once_with(id=test_case_id)
        assert result == artifact_id

    def test_stakeholder_need_id_resolves_to_artifact_id(self):
        """A StakeholderNeed ID resolves to its backing Artifact ID."""
        svc = TraceLinkService()
        need_id = uuid.uuid4()
        artifact_id = uuid.uuid4()
        mock_need = MagicMock()
        mock_need.artifact_id = artifact_id

        with ExitStack() as stack:
            _miss(stack, *_EARLIER_MODELS, _TEST_CASE_PATH)
            need_filter = _hit(stack, _NEED_PATH, mock_need)
            result = svc._resolve_artifact_id(need_id)

        need_filter.assert_called_once_with(id=need_id)
        assert result == artifact_id

    def test_resolve_entity_to_artifact_id_is_public_and_sets_tenant(self):
        """The Layer-3 wrapper sets the tenant context before resolving."""
        svc = TraceLinkService()
        ctx = _make_ctx()
        artifact_id = uuid.uuid4()

        with (
            patch(
                "application.trace_link_service.ServiceBase._set_tenant_context"
            ) as mock_stc,
            patch.object(
                svc, "_resolve_artifact_id", return_value=artifact_id
            ) as mock_resolve,
        ):
            result = svc.resolve_entity_to_artifact_id(SOURCE_ID, ctx=ctx)

        mock_stc.assert_called_once_with(ctx)
        mock_resolve.assert_called_once_with(SOURCE_ID)
        assert result == artifact_id


# ---------------------------------------------------------------------------
# Befund C — no traceability exception may escape as a 500
# ---------------------------------------------------------------------------


class TestTraceLinkErrorMapping:
    """#264 Befund C: TraceLinkError subclasses map to ValidationError.

    The MCP tool only catches NotFoundError / ValidationError /
    PermissionDeniedError, so anything else becomes ``-32603 An internal
    error occurred`` — an HTTP 500 for what is a rejected input.
    """

    def _create_with(self, side_effect, link_type="traces"):
        """Run create_trace_link with the engine raising *side_effect*."""
        svc = TraceLinkService()
        ctx = _make_ctx()

        with ExitStack() as stack:
            stack.enter_context(
                patch("application.trace_link_service.ServiceBase._set_tenant_context")
            )
            stack.enter_context(
                patch.object(svc, "_resolve_artifact_id", side_effect=lambda x: x)
            )
            stack.enter_context(patch.object(svc, "_check_se_semantics"))
            stack.enter_context(
                patch(
                    "traceability.services.create_trace_link",
                    side_effect=side_effect,
                )
            )
            return svc.create_trace_link(
                source_id=SOURCE_ID,
                target_id=TARGET_ID,
                link_type=link_type,
                ctx=ctx,
            )

    def test_cycle_detected_maps_to_validation_error(self):
        """A cycle is a rejected input, not a server fault.

        Reproduces the #264 Befund C sequence: once ``traces``
        Goal -> Requirement exists, ``traces`` Requirement -> Goal closes the
        cycle. That used to surface as HTTP 500.
        """
        from traceability.exceptions import CycleDetectedError

        with pytest.raises(ValidationError, match="Cycle detected"):
            self._create_with(CycleDetectedError("traces"))

    def test_cross_tenant_error_maps_to_validation_error(self):
        from traceability.exceptions import CrossTenantLinkError

        with pytest.raises(ValidationError, match="Cross-workspace"):
            self._create_with(CrossTenantLinkError())

    def test_invalid_link_type_from_engine_maps_to_validation_error(self):
        from traceability.exceptions import InvalidLinkTypeError

        with pytest.raises(ValidationError, match="Invalid link type"):
            self._create_with(InvalidLinkTypeError("nonsense"))

    def test_duplicate_edge_maps_to_validation_error(self):
        """uq_tracelink_edge violation is a 400, not a 500."""
        from django.db import IntegrityError

        with pytest.raises(ValidationError, match="already exists"):
            self._create_with(IntegrityError("duplicate key uq_tracelink_edge"))

    def test_source_not_found_still_maps_to_not_found(self):
        """SourceNotFoundError keeps its NotFoundError mapping.

        SourceNotFoundError is itself a TraceLinkError, so the new catch-all
        must not swallow it ahead of the more specific handler.
        """
        from traceability.exceptions import SourceNotFoundError

        with pytest.raises(NotFoundError, match="Source entity"):
            self._create_with(SourceNotFoundError(SOURCE_ID))

    def test_target_not_found_still_maps_to_not_found(self):
        """TargetNotFoundError keeps its NotFoundError mapping."""
        from traceability.exceptions import TargetNotFoundError

        with pytest.raises(NotFoundError, match="Target entity"):
            self._create_with(TargetNotFoundError(TARGET_ID))

    def test_unexpected_exception_is_not_swallowed(self):
        """A genuine bug must still propagate — it is not a 400."""
        with pytest.raises(RuntimeError, match="disk on fire"):
            self._create_with(RuntimeError("disk on fire"))


# ---------------------------------------------------------------------------
# list_links_for_entity / list_links_for_workspace
# ---------------------------------------------------------------------------


class TestListLinks:
    """#264 Befund B: read paths that return the persisted rows themselves."""

    def test_upstream_filters_on_target_id(self):
        svc = TraceLinkService()
        ctx = _make_ctx()
        resolved = uuid.uuid4()

        with (
            patch("application.trace_link_service.ServiceBase._set_tenant_context"),
            patch.object(svc, "_resolve_artifact_id", return_value=resolved),
            patch(
                "traceability.services.list_trace_links", return_value=[]
            ) as mock_list,
        ):
            svc.list_links_for_entity(
                entity_id=SOURCE_ID, direction="upstream", ctx=ctx
            )

        mock_list.assert_called_once_with(
            filters={"target_id": resolved}, link_type=None
        )

    def test_downstream_filters_on_source_id(self):
        svc = TraceLinkService()
        ctx = _make_ctx()
        resolved = uuid.uuid4()

        with (
            patch("application.trace_link_service.ServiceBase._set_tenant_context"),
            patch.object(svc, "_resolve_artifact_id", return_value=resolved),
            patch(
                "traceability.services.list_trace_links", return_value=[]
            ) as mock_list,
        ):
            svc.list_links_for_entity(
                entity_id=SOURCE_ID, direction="downstream", ctx=ctx
            )

        mock_list.assert_called_once_with(
            filters={"source_id": resolved}, link_type=None
        )

    def test_invalid_direction_raises_validation_error(self):
        svc = TraceLinkService()
        ctx = _make_ctx()

        with pytest.raises(ValidationError, match="Invalid direction"):
            svc.list_links_for_entity(
                entity_id=SOURCE_ID, direction="sideways", ctx=ctx
            )

    def test_unresolvable_entity_raises_not_found(self):
        """A bad id must not masquerade as "this artifact has no links"."""
        svc = TraceLinkService()
        ctx = _make_ctx()

        with (
            patch("application.trace_link_service.ServiceBase._set_tenant_context"),
            patch.object(
                svc,
                "_resolve_artifact_id",
                side_effect=NotFoundError("Entity x not found"),
            ),
        ):
            with pytest.raises(NotFoundError):
                svc.list_links_for_entity(
                    entity_id=SOURCE_ID, direction="upstream", ctx=ctx
                )

    def test_workspace_listing_delegates_with_workspace_id(self):
        svc = TraceLinkService()
        ctx = _make_ctx()
        workspace_id = uuid.uuid4()

        with (
            patch("application.trace_link_service.ServiceBase._set_tenant_context"),
            patch(
                "traceability.services.list_trace_links", return_value=[]
            ) as mock_list,
        ):
            svc.list_links_for_workspace(workspace_id=workspace_id, ctx=ctx)

        mock_list.assert_called_once_with(workspace_id=workspace_id, link_type=None)
