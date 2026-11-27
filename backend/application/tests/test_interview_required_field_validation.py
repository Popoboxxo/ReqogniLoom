"""Plan P0.4/P0.5 — machine-readable required-field and adapter errors.

Before this change a proposal missing ``Risk.probability`` failed deep inside
``create_risk(**fields)`` as a KeyError wrapped in a prose "invalid fields"
message, and an unexpected kwarg surfaced as the same generic string. These
tests pin the shared vocabulary the readout and write gate now use:
``MISSING_REQUIRED_FIELD`` (naming the field), ``UNKNOWN_FIELD`` (naming the
kwarg) and ``INVALID_PROPOSAL_SHAPE`` (the catch-all).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from application.interview_artifact_adapters import ARTIFACT_CREATION_ADAPTERS
from application.interview_multi_formalize_service import (
    InterviewMultiFormalizationMixin,
    collect_missing_required_fields,
    validate_confirmed_proposal_fields,
)
from application.interview_proposal_errors import ProposalValidationError
from attribute_definitions.global_definition_store import AttributeDefinitionNotFound

pytestmark = pytest.mark.django_db

_RESOLVE = "application.attribute_definition_service.AttributeDefinitionService.resolve"


@pytest.fixture(autouse=True)
def _no_definition():
    """Signature-only contract: no attribute definition in this workspace."""
    with patch(_RESOLVE, side_effect=AttributeDefinitionNotFound()):
        yield


class TestCollectMissingRequiredFields:
    def test_reports_risk_probability_and_impact(self):
        proposal = [{"type": "Risk", "fields": {"title": "R"}}]

        missing = collect_missing_required_fields(object(), "ws-1", proposal)

        assert missing == [
            {
                "item_index": 0,
                "artifact_type": "Risk",
                "fields": ["probability", "impact"],
            }
        ]

    def test_complete_item_is_not_reported(self):
        proposal = [
            {"type": "Risk", "fields": {"title": "R", "probability": "high", "impact": "low"}}
        ]
        assert collect_missing_required_fields(object(), "ws-1", proposal) == []

    def test_unknown_artifact_type_is_skipped(self):
        proposal = [{"type": "NoSuchType", "fields": {}}]
        assert collect_missing_required_fields(object(), "ws-1", proposal) == []


class TestValidateReportsMissingRequiredFields:
    def test_missing_risk_field_raises_machine_readable_error(self):
        proposal = [{"type": "Risk", "fields": {"title": "R"}}]

        with pytest.raises(ProposalValidationError) as excinfo:
            validate_confirmed_proposal_fields(object(), "ws-1", proposal)

        error = excinfo.value
        assert error.code == "MISSING_REQUIRED_FIELD"
        assert error.item_index == 0
        assert error.field == "probability"
        assert error.details["fields"] == ["probability", "impact"]
        assert error.details["artifact_type"] == "Risk"
        assert "probability" in str(error)

    def test_unknown_field_is_reported_before_missing_required(self):
        # A typo is a shape error: reporting it as "missing required" would
        # hide the actual mistake.
        proposal = [{"type": "Risk", "fields": {"titel": "R"}}]

        with pytest.raises(ProposalValidationError) as excinfo:
            validate_confirmed_proposal_fields(object(), "ws-1", proposal)

        assert excinfo.value.code == "UNKNOWN_FIELD"
        assert excinfo.value.field == "titel"


def _raise_key_error(fields, ctx, workspace_id):
    raise KeyError("probability")


def _raise_unexpected_kwarg(fields, ctx, workspace_id):
    raise TypeError("create_x() got an unexpected keyword argument 'bogus'")


def _raise_other_type_error(fields, ctx, workspace_id):
    raise TypeError("create_x() failed for another reason")


class TestCreateProposalItemsErrorMapping:
    """P0.5: defensive mapping when an adapter still raises mid-write."""

    @pytest.fixture
    def session(self):
        return SimpleNamespace(workspace_id="ws-1")

    def _call(self, session, adapter):
        proposal = [{"type": "StakeholderNeed", "fields": {"title": "N"}, "links": []}]
        with patch.dict(ARTIFACT_CREATION_ADAPTERS, {"StakeholderNeed": adapter}):
            return InterviewMultiFormalizationMixin._create_proposal_items(
                object(), session, proposal
            )

    def test_key_error_becomes_missing_required_field(self, session):
        with pytest.raises(ProposalValidationError) as excinfo:
            self._call(session, _raise_key_error)

        error = excinfo.value
        assert error.code == "MISSING_REQUIRED_FIELD"
        assert error.item_index == 0
        assert error.field == "probability"
        assert error.details["fields"] == ["probability"]
        assert error.details["artifact_type"] == "StakeholderNeed"

    def test_unexpected_kwarg_becomes_unknown_field(self, session):
        with pytest.raises(ProposalValidationError) as excinfo:
            self._call(session, _raise_unexpected_kwarg)

        error = excinfo.value
        assert error.code == "UNKNOWN_FIELD"
        assert error.field == "bogus"
        assert error.details["fields"] == ["bogus"]

    def test_other_type_error_becomes_invalid_proposal_shape(self, session):
        with pytest.raises(ProposalValidationError) as excinfo:
            self._call(session, _raise_other_type_error)

        error = excinfo.value
        assert error.code == "INVALID_PROPOSAL_SHAPE"
        assert error.item_index == 0
        assert "another reason" in error.details["error"]
