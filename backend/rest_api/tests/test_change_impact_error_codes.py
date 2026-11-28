"""Design §4.5 / plan S5.3: the change-impact gate codes on the REST transport.

Every structured gate refusal is a ``ChangeImpactGateError`` subclass. The REST
error helper (``_service_error_response``) looks exception types up by *exact*
identity, so each one must be registered in ``_EXC_TO_HTTP``/``_EXC_TO_CODE``
and carry a DE+EN message — otherwise it degrades to a generic 500.

The expected statuses are the spec's error table: 409 for every gate refusal,
400 for ``POLICY_FORBIDDEN`` and 429 for ``RATE_LIMITED``.
"""
from __future__ import annotations

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
from rest_api.serializers_common import _ERROR_MESSAGES
from rest_api.views_common import (
    _EXC_TO_CODE,
    _EXC_TO_HTTP,
    _service_error_response,
)

#: (exception type, wire code, expected HTTP status, example details)
CASES = [
    (
        ChangeImpactMissingError,
        "CHANGE_IMPACT_MISSING",
        409,
        {"reason": "never"},
    ),
    (
        ChangeImpactStaleError,
        "CHANGE_IMPACT_STALE",
        409,
        {"reason": "graph_changed"},
    ),
    (
        ChangeImpactOpenFindingsError,
        "CHANGE_IMPACT_OPEN_FINDINGS",
        409,
        {"finding_ids": ["f-1", "f-2"], "count": 2},
    ),
    (
        ChangeImpactIncompleteError,
        "CHANGE_IMPACT_INCOMPLETE",
        409,
        {"reason": "truncated"},
    ),
    (
        ChangeImpactRunningError,
        "CHANGE_IMPACT_RUNNING",
        409,
        {"run_id": "run-1", "status": "running"},
    ),
    (
        ChangeImpactTimeoutError,
        "CHANGE_IMPACT_TIMEOUT",
        409,
        {"run_id": "run-2", "status": "failed"},
    ),
    (
        ChangeImpactPolicyForbiddenError,
        "CHANGE_IMPACT_POLICY_FORBIDDEN",
        400,
        {"key": "max_depth"},
    ),
    (
        ChangeImpactPolicyUnavailableError,
        "CHANGE_IMPACT_POLICY_UNAVAILABLE",
        409,
        {"reason": "policy_unavailable"},
    ),
    (
        ChangeSetFrozenError,
        "CHANGE_SET_FROZEN",
        409,
        {"state": "submitted"},
    ),
    (
        ChangeImpactRateLimitedError,
        "CHANGE_IMPACT_RATE_LIMITED",
        429,
        {"key": "analyze_impact"},
    ),
]

GATE_TYPES = frozenset(case[0] for case in CASES)


@pytest.mark.parametrize(("exc_type", "code", "http_status", "details"), CASES)
@pytest.mark.parametrize("lang", ["en", "de"])
def test_service_error_response_answers_the_dedicated_code(
    exc_type: type, code: str, http_status: int, details: dict, lang: str
) -> None:
    # Passed as keyword so the base constructor's ``details`` default is not
    # shadowed by a positional-message mix-up.
    exc = exc_type(details=details)

    response = _service_error_response(exc, lang)

    assert response.status_code == http_status
    body = response.data["error"]
    assert body["code"] == code
    # The structured payload survives the envelope unchanged.
    assert body["details"] == details
    # The service's human-readable sentence is forwarded (no internals).
    assert body["message"]
    assert body["message"] != code


@pytest.mark.parametrize(("exc_type", "code", "http_status", "details"), CASES)
def test_registered_in_both_rest_maps(
    exc_type: type, code: str, http_status: int, details: dict
) -> None:
    assert _EXC_TO_HTTP[exc_type] == http_status
    assert _EXC_TO_CODE[exc_type] == code
    # The exception's own attributes agree with the maps, so a caller that
    # catches it directly can read the same contract.
    exc = exc_type()
    assert exc.error_code == code
    assert exc.http_status == http_status
    assert exc.details == {}


@pytest.mark.parametrize(("exc_type", "code", "http_status", "details"), CASES)
def test_bilingual_message_names_the_stable_code(
    exc_type: type, code: str, http_status: int, details: dict
) -> None:
    entry = _ERROR_MESSAGES[code]
    assert entry["en"].strip()
    assert entry["de"].strip()
    # The localised fallback must name the wire code so a client that only sees
    # the sentence can still map it back to the contract.
    assert code in entry["en"]
    assert code in entry["de"]


def test_gate_codes_are_unique_and_not_reused() -> None:
    """No duplicate REST codes: the ten gate types own ten distinct codes."""
    codes = [_EXC_TO_CODE[exc_type] for exc_type in GATE_TYPES]
    assert len(codes) == len(set(codes)) == len(CASES)
    gate_codes = set(codes)
    for other_type, other_code in _EXC_TO_CODE.items():
        if other_type in GATE_TYPES:
            continue
        assert other_code not in gate_codes, (
            f"{other_type.__name__} reuses the gate code {other_code}"
        )


def test_details_default_to_an_empty_dict() -> None:
    assert ChangeImpactMissingError().details == {}
    assert ChangeImpactMissingError(details=None).details == {}
