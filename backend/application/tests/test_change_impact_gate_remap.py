"""Design §4.5 / plan S5.3: the change-impact gate at the workflow remap seam.

``workflow.precondition_rules`` will emit the ``EC_CHANGE_IMPACT_*`` /
``EC_CHANGE_SET_FROZEN`` markers from the shared ``ChangeRequest`` precondition
(S5.2). This module pins the *transport half* of that contract: the markers are
registered now, and ``_remap_workflow_exc`` turns each of them into its
dedicated ``application.base`` subtype instead of degrading to the generic
``VALIDATION_ERROR``/400 fallback.

It also pins the documented deviation for ``artifact.bulk_transition``: the
four-code envelope is preserved and the gate code rides in
``details.change_impact_code``.
"""
from __future__ import annotations

import uuid

import pytest

from application.base import (
    ChangeImpactIncompleteError,
    ChangeImpactMissingError,
    ChangeImpactOpenFindingsError,
    ChangeImpactPolicyForbiddenError,
    ChangeImpactPolicyUnavailableError,
    ChangeImpactRateLimitedError,
    ChangeImpactRunningError,
    ChangeImpactStaleError,
    ChangeImpactTimeoutError,
    ChangeSetFrozenError,
)
from application.bulk_update_service import _transition_error
from application.workflow_facade import _remap_workflow_exc
from workflow import precondition_rules
from workflow.services import WorkflowTransitionError

#: (marker attribute name, expected exception type, expected HTTP status)
CASES = [
    ("EC_CHANGE_IMPACT_MISSING", ChangeImpactMissingError, 409),
    ("EC_CHANGE_IMPACT_STALE", ChangeImpactStaleError, 409),
    ("EC_CHANGE_IMPACT_OPEN_FINDINGS", ChangeImpactOpenFindingsError, 409),
    ("EC_CHANGE_IMPACT_INCOMPLETE", ChangeImpactIncompleteError, 409),
    ("EC_CHANGE_IMPACT_RUNNING", ChangeImpactRunningError, 409),
    ("EC_CHANGE_IMPACT_TIMEOUT", ChangeImpactTimeoutError, 409),
    ("EC_CHANGE_IMPACT_POLICY_FORBIDDEN", ChangeImpactPolicyForbiddenError, 400),
    ("EC_CHANGE_IMPACT_POLICY_UNAVAILABLE", ChangeImpactPolicyUnavailableError, 409),
    ("EC_CHANGE_SET_FROZEN", ChangeSetFrozenError, 409),
    ("EC_CHANGE_IMPACT_RATE_LIMITED", ChangeImpactRateLimitedError, 429),
]


@pytest.mark.parametrize(("marker_name", "expected_type", "http_status"), CASES)
def test_remap_turns_each_marker_into_its_dedicated_subtype(
    marker_name: str, expected_type: type, http_status: int
) -> None:
    marker = getattr(precondition_rules, marker_name)
    # The marker value IS the wire code (same identity as
    # EC_DOCUMENT_GATE_FAILED), which is what makes the mapping auditable.
    assert marker == expected_type.error_code

    exc = WorkflowTransitionError(
        marker, "The change impact gate refused this transition.", details={"reason": "never"}
    )

    with pytest.raises(expected_type) as info:
        _remap_workflow_exc(exc)

    assert info.value.error_code == marker
    assert info.value.http_status == http_status
    assert info.value.details == {"reason": "never"}
    assert info.value.__cause__ is exc


def test_unregistered_marker_still_degrades_to_validation_error() -> None:
    """Precedence guard: the mapping must not swallow unknown validator codes."""
    from application.base import ValidationError

    exc = WorkflowTransitionError("EC_SOMETHING_ELSE", "nope")
    with pytest.raises(ValidationError) as info:
        _remap_workflow_exc(exc)
    assert type(info.value) is ValidationError


@pytest.mark.parametrize(("marker_name", "expected_type", "http_status"), CASES)
def test_bulk_transition_keeps_its_envelope_and_publishes_the_gate_code(
    marker_name: str, expected_type: type, http_status: int
) -> None:
    """The bulk path's four-code contract is documented behaviour, not drift."""
    exc = expected_type(details={"reason": "never"})

    payload = _transition_error(0, uuid.uuid4(), exc)

    assert payload is not None
    # Four-code envelope preserved: the gate code is NOT the entry code.
    assert payload["code"] == "VALIDATION_ERROR"
    assert payload["details"]["change_impact_code"] == expected_type.error_code
    assert payload["details"]["reason"] == "never"
