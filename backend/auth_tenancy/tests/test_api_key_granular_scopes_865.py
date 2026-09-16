"""Granular API-key scopes: READ_ONLY / AUTHOR / ADMIN (#865).

The shared capability gate (``scope_denial_reason``) is the single decision
point for the REST and MCP adapters, so its tier model is pinned here:

* tier 0 READ_ONLY reads, tier 1 AUTHOR writes content, tier 2 ADMIN governs,
* the legacy values keep their EXACT previous meaning — ``read`` is READ_ONLY,
  ``write`` is the widest (ADMIN) tier, so no existing key changes behaviour,
* unknown scope names fail closed (deny everything) instead of failing open,
* credentials without a scope at all (JWT bearer sessions) stay ungated.
"""
from __future__ import annotations

import pytest

from auth_tenancy.models import (
    API_KEY_SCOPE_ADMIN,
    API_KEY_SCOPE_AUTHOR,
    API_KEY_SCOPE_CHOICES,
    API_KEY_SCOPE_READ,
    API_KEY_SCOPE_READ_ONLY,
    API_KEY_SCOPE_WRITE,
    normalize_api_key_scope,
)
from auth_tenancy.services.authorization import (
    GOVERNANCE_OPERATIONS,
    Operation,
    required_scope_tier,
    scope_allows,
    scope_denial_reason,
    scope_tier,
)

_ALL_OPERATIONS = tuple(Operation)


# ---------------------------------------------------------------------------
# Tier model
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("scope", "tier"),
    [
        (API_KEY_SCOPE_READ_ONLY, 0),
        (API_KEY_SCOPE_READ, 0),
        (API_KEY_SCOPE_AUTHOR, 1),
        (API_KEY_SCOPE_ADMIN, 2),
        (API_KEY_SCOPE_WRITE, 2),
    ],
)
def test_scope_tier_mapping(scope: str, tier: int) -> None:
    assert scope_tier(scope) == tier


def test_scope_tier_normalises_case_and_whitespace() -> None:
    assert scope_tier("  READ_ONLY ") == 0
    assert scope_tier("Author") == 1
    assert scope_tier("ADMIN") == 2


@pytest.mark.parametrize("empty", [None, "", "   "])
def test_missing_scope_is_ungated(empty: object) -> None:
    """A credential without a scope (JWT bearer) is exempt from the key gate."""
    assert scope_tier(empty) is None
    assert scope_denial_reason(empty, Operation.WORKSPACE_CONFIG) is None


def test_non_string_scope_is_treated_as_no_scope() -> None:
    """Duck-typed/mock contexts carry no scope; no credential path yields one.

    ``ApiKey.scope`` is a ``CharField`` and ``AuthContext.scope`` defaults to
    ``"write"``, so a non-string can only come from a test double — treating it
    as "unknown" would deny those contexts everywhere without protecting
    anything. Unknown *names* still fail closed (see the test below).
    """
    marker = object()
    assert scope_tier(marker) is None
    assert scope_denial_reason(marker, Operation.WORKSPACE_CONFIG) is None


def test_unknown_scope_fails_closed_for_every_operation() -> None:
    assert scope_tier("godmode") == -1
    for operation in _ALL_OPERATIONS:
        assert scope_denial_reason("godmode", operation) is not None, operation


def test_required_scope_tier_is_fail_closed_for_unlisted_operations() -> None:
    assert required_scope_tier("not-an-operation") == 2  # type: ignore[arg-type]


def test_governance_operations_are_the_admin_tier() -> None:
    assert required_scope_tier(Operation.WRITE) == 1
    for operation in GOVERNANCE_OPERATIONS:
        assert required_scope_tier(operation) == 2, operation


# ---------------------------------------------------------------------------
# READ_ONLY
# ---------------------------------------------------------------------------


def test_read_only_allows_reads() -> None:
    assert scope_allows(API_KEY_SCOPE_READ_ONLY, Operation.READ)
    assert scope_allows(API_KEY_SCOPE_READ, Operation.READ)


@pytest.mark.parametrize(
    "operation",
    [
        Operation.WRITE,
        Operation.WORKFLOW_TRANSITION,
        Operation.WORKSPACE_CONFIG,
        Operation.ASSIGN_ROLE,
        Operation.WORKFLOW_APPROVAL,
    ],
)
def test_read_only_denies_every_write(operation: Operation) -> None:
    assert scope_denial_reason(API_KEY_SCOPE_READ_ONLY, operation) is not None
    assert scope_denial_reason(API_KEY_SCOPE_READ, operation) is not None


def test_read_only_denial_message_stays_compatible() -> None:
    """#917's contract: the message names the read-only key and the operation."""
    message = scope_denial_reason(API_KEY_SCOPE_READ, Operation.WRITE)
    assert message is not None
    assert "read-only" in message.lower()
    assert "operation 'write'" in message


# ---------------------------------------------------------------------------
# AUTHOR — the new tier: content writes yes, governance no
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "operation", [Operation.READ, Operation.WRITE, Operation.WORKFLOW_TRANSITION]
)
def test_author_allows_content_operations(operation: Operation) -> None:
    assert scope_allows(API_KEY_SCOPE_AUTHOR, operation)


@pytest.mark.parametrize("operation", sorted(GOVERNANCE_OPERATIONS))
def test_author_denies_governance_operations(operation: Operation) -> None:
    message = scope_denial_reason(API_KEY_SCOPE_AUTHOR, operation)
    assert message is not None
    assert "governance" in message
    assert "admin" in message


# ---------------------------------------------------------------------------
# ADMIN and the legacy aliases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scope", [API_KEY_SCOPE_ADMIN, API_KEY_SCOPE_WRITE])
def test_admin_scope_allows_every_operation(scope: str) -> None:
    for operation in _ALL_OPERATIONS:
        assert scope_allows(scope, operation), operation


def test_legacy_write_matches_historical_behaviour() -> None:
    """A pre-#865 ``write`` key reached every operation its roles allowed.

    Mapping it to the widest tier is what keeps that promise; mapping it to
    AUTHOR would silently strip governance access from existing keys.
    """
    for operation in _ALL_OPERATIONS:
        assert scope_denial_reason(API_KEY_SCOPE_WRITE, operation) is None


def test_legacy_read_matches_historical_behaviour() -> None:
    assert scope_denial_reason(API_KEY_SCOPE_READ, Operation.READ) is None
    assert scope_denial_reason(API_KEY_SCOPE_READ, Operation.WRITE) is not None


# ---------------------------------------------------------------------------
# Schema: choices + API-boundary normalisation
# ---------------------------------------------------------------------------


def test_scope_choices_keep_the_legacy_values_and_add_the_canonical_tiers() -> None:
    names = {name for name, _label in API_KEY_SCOPE_CHOICES}
    assert names == {
        API_KEY_SCOPE_READ,
        API_KEY_SCOPE_WRITE,
        API_KEY_SCOPE_READ_ONLY,
        API_KEY_SCOPE_AUTHOR,
        API_KEY_SCOPE_ADMIN,
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("read_only", API_KEY_SCOPE_READ_ONLY),
        ("AUTHOR", API_KEY_SCOPE_AUTHOR),
        (" admin ", API_KEY_SCOPE_ADMIN),
        ("read", API_KEY_SCOPE_READ),
        ("write", API_KEY_SCOPE_WRITE),
        ("godmode", None),
        ("", None),
        (None, None),
        (42, None),
    ],
)
def test_normalize_api_key_scope(value: object, expected: str | None) -> None:
    assert normalize_api_key_scope(value) == expected
