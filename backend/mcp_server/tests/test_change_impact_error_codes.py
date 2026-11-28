"""Design §4.5 / plan S5.3: the change-impact gate codes on the MCP transport.

Two seams are pinned here:

* ``ERROR_CODES`` / ``ERROR_CODE_MAP`` — every code is registered in *both*
  catalogs and owns a unique JSON-RPC number (the reserved block
  ``-32021…-32030``).
* ``map_tool_exception`` — the ``ChangeImpactGateError`` check must run
  **before** ``isinstance(exc, ValidationError)``; otherwise the refusal
  collapses to ``VALIDATION_ERROR`` and loses both its code and its details.
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
from mcp_server.protocol_handler import (
    ERROR_CODE_MAP,
    ERROR_CODES,
    ErrorFormatter,
)
from mcp_server.tools.base import map_tool_exception
from persistence.errors import ValidationError

#: (exception type, wire code, expected JSON-RPC number, example details)
CASES = [
    (ChangeImpactMissingError, "CHANGE_IMPACT_MISSING", -32021, {"reason": "never"}),
    (ChangeImpactStaleError, "CHANGE_IMPACT_STALE", -32022, {"reason": "graph_changed"}),
    (
        ChangeImpactOpenFindingsError,
        "CHANGE_IMPACT_OPEN_FINDINGS",
        -32023,
        {"finding_ids": ["f-1"], "count": 1},
    ),
    (
        ChangeImpactIncompleteError,
        "CHANGE_IMPACT_INCOMPLETE",
        -32024,
        {"reason": "truncated"},
    ),
    (
        ChangeImpactRunningError,
        "CHANGE_IMPACT_RUNNING",
        -32025,
        {"run_id": "run-1", "status": "running"},
    ),
    (
        ChangeImpactTimeoutError,
        "CHANGE_IMPACT_TIMEOUT",
        -32026,
        {"run_id": "run-2", "status": "failed"},
    ),
    (
        ChangeImpactPolicyForbiddenError,
        "CHANGE_IMPACT_POLICY_FORBIDDEN",
        -32027,
        {"key": "max_depth"},
    ),
    (
        ChangeImpactPolicyUnavailableError,
        "CHANGE_IMPACT_POLICY_UNAVAILABLE",
        -32028,
        {"reason": "policy_unavailable"},
    ),
    (ChangeSetFrozenError, "CHANGE_SET_FROZEN", -32029, {"state": "submitted"}),
    (
        ChangeImpactRateLimitedError,
        "CHANGE_IMPACT_RATE_LIMITED",
        -32030,
        {"key": "analyze_impact"},
    ),
]


@pytest.mark.parametrize(("exc_type", "code", "rpc_number", "details"), CASES)
def test_registered_in_both_mcp_catalogs(
    exc_type: type, code: str, rpc_number: int, details: dict
) -> None:
    assert ERROR_CODES[code].strip()
    assert ERROR_CODE_MAP[code] == rpc_number


@pytest.mark.parametrize(("exc_type", "code", "rpc_number", "details"), CASES)
def test_map_tool_exception_returns_the_dedicated_code_and_details(
    exc_type: type, code: str, rpc_number: int, details: dict
) -> None:
    mapped = map_tool_exception(exc_type(details=details))

    assert mapped is not None
    # The subtype must win over the generic ValidationError branch.
    assert mapped[0] == code
    assert mapped[0] != "VALIDATION_ERROR"
    assert mapped[1]
    assert len(mapped) == 3
    assert mapped[2] == details


@pytest.mark.parametrize(("exc_type", "code", "rpc_number", "details"), CASES)
def test_error_formatter_payload_carries_code_message_and_details(
    exc_type: type, code: str, rpc_number: int, details: dict
) -> None:
    mapped = map_tool_exception(exc_type(details=details))
    assert mapped is not None
    mapped_code, message, mapped_details = mapped

    body = ErrorFormatter.format_error(mapped_code, message, mapped_details)

    assert body["code"] == rpc_number
    assert body["message"]
    assert body["details"] == details


def test_plain_validation_error_keeps_the_legacy_two_tuple() -> None:
    """Precedence guard: the new branch must not reshape every ValidationError."""
    mapped = map_tool_exception(ValidationError("bad input"))

    assert mapped == ("VALIDATION_ERROR", "bad input")


def test_no_duplicate_jsonrpc_numbers() -> None:
    """The whole catalog — not just the new block — must stay collision-free."""
    numbers = list(ERROR_CODE_MAP.values())
    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    assert duplicates == [], f"duplicate JSON-RPC numbers: {duplicates}"


def test_gate_codes_are_unique_within_the_catalog() -> None:
    codes = [case[1] for case in CASES]
    assert len(codes) == len(set(codes)) == 10
