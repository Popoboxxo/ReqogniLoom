"""Regression tests for GitHub issue #407 — Risk/Issue entity resolution in
TraceLinkService.

leaf_id : COMP-AS-005
req_id  : REQ-L2-AS-010

Root cause: ``TraceLinkService._resolve_artifact_id`` supported Artifact,
Requirement, ArchitectureElement, Adr, Goal, MainGoal, TestCase and
StakeholderNeed (fix #264), but not Risk or Issue — even though both are
plain ``OneToOneField(Artifact)`` entities with the exact same shape as the
other eight (see ``application.models.Risk``/``Issue``). Any attempt to
create a TraceLink using a Risk or Issue business-entity id (e.g. for
trade-study Risk<->Requirement links) raised ``NotFoundError`` even though
the target's own artifact could otherwise be linked to just fine once
resolved.

Mirrors the unit-test style of ``test_trace_link_service_issue264.py`` (no
DB — the resolution chain is pure branching logic).
"""
from __future__ import annotations

import uuid
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from application.base import NotFoundError
from application.trace_link_service import TraceLinkService

#: Everything probed before Risk / Issue in the chain (see
#: ``TraceLinkService._resolve_artifact_id``).
_EARLIER_MODELS = (
    "persistence.models.Artifact.objects.filter",
    "persistence.models.Requirement.objects.filter",
    "persistence.models.ArchitectureElement.objects.filter",
    "application.models.Adr.objects.filter",
    "application.models.Goal.objects.filter",
    "application.models.MainGoal.objects.filter",
    "persistence.models.TestCase.objects.filter",
    "persistence.models.StakeholderNeed.objects.filter",
)

_RISK_PATH = "application.models.Risk.objects.filter"
_ISSUE_PATH = "application.models.Issue.objects.filter"


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


class TestResolveRiskAndIssue:
    """#407: both entity types must resolve to their Artifact."""

    def test_risk_id_resolves_to_artifact_id(self):
        """A Risk ID resolves to its backing Artifact ID.

        Before the fix this raised NotFoundError("Entity ... not found"),
        blocking any Risk<->Requirement trace link (trade-study support).
        """
        svc = TraceLinkService()
        risk_id = uuid.uuid4()
        artifact_id = uuid.uuid4()
        mock_risk = MagicMock()
        mock_risk.artifact_id = artifact_id

        with ExitStack() as stack:
            _miss(stack, *_EARLIER_MODELS)
            risk_filter = _hit(stack, _RISK_PATH, mock_risk)
            result = svc._resolve_artifact_id(risk_id)

        risk_filter.assert_called_once_with(id=risk_id)
        assert result == artifact_id

    def test_issue_id_resolves_to_artifact_id(self):
        """An Issue ID resolves to its backing Artifact ID."""
        svc = TraceLinkService()
        issue_id = uuid.uuid4()
        artifact_id = uuid.uuid4()
        mock_issue = MagicMock()
        mock_issue.artifact_id = artifact_id

        with ExitStack() as stack:
            _miss(stack, *_EARLIER_MODELS, _RISK_PATH)
            issue_filter = _hit(stack, _ISSUE_PATH, mock_issue)
            result = svc._resolve_artifact_id(issue_id)

        issue_filter.assert_called_once_with(id=issue_id)
        assert result == artifact_id

    def test_risk_with_null_artifact_id_falls_through_to_not_found(self):
        """A Risk row matching by id but with no backing artifact is treated
        as unresolved, same as the Adr null-artifact guard above it in the
        chain — a Risk without an artifact cannot be a TraceLink endpoint.
        """
        svc = TraceLinkService()
        risk_id = uuid.uuid4()
        mock_risk = MagicMock()
        mock_risk.artifact_id = None

        with ExitStack() as stack:
            _miss(stack, *_EARLIER_MODELS)
            _hit(stack, _RISK_PATH, mock_risk)
            _miss(stack, _ISSUE_PATH)

            with pytest.raises(NotFoundError, match="Entity"):
                svc._resolve_artifact_id(risk_id)
