"""Tests for COMP-AS-022 EffectivePermissionService (issue #722).

Covers the Layer-2 relocation of the ``permissions.check`` RBAC/item-layer
combination (ADR-01) and the structured ``has_explicit_rule`` discriminator
that replaced the fragile ``reason == NO_RULE_REASON`` string compare.

The RBAC side uses the real, pure, DB-free :class:`AuthorizationService`;
the item-level side is a stub, because the question here is the *merge*, not
the rule lookup (which ``auth_tenancy/tests/test_item_permission.py`` owns).
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from auth_tenancy.services.authorization import AuthorizationService
from auth_tenancy.services.item_permission import (
    NO_RULE_REASON,
    ItemPermissionService,
    PermissionDecision,
)

from application.base import ValidationError
from application.effective_permission_service import (
    EffectivePermission,
    EffectivePermissionService,
    level_satisfies_level,
    more_restrictive_level,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000010")
ARTIFACT_ID = UUID("00000000-0000-0000-0000-000000000030")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _item_service(decision: PermissionDecision) -> MagicMock:
    """Stub ItemPermissionService whose check returns *decision*."""
    svc = MagicMock(spec=ItemPermissionService)
    svc.check_permission.return_value = decision
    return svc


def _service(decision: PermissionDecision) -> EffectivePermissionService:
    return EffectivePermissionService(
        item_permission_service=_item_service(decision),
        authz_service=AuthorizationService(),
    )


def _explicit(level: str, reason: str = "artifact-scoped rule") -> PermissionDecision:
    """A decision backed by a real ItemPermission row."""
    return PermissionDecision(level=level, reason=reason, has_explicit_rule=True)


def _silent(level: str = "deny", reason: str = NO_RULE_REASON) -> PermissionDecision:
    """The item layer's closed-world default: no rule row was evaluated."""
    return PermissionDecision(level=level, reason=reason, has_explicit_rule=False)


def _resolve(svc: EffectivePermissionService, *, roles, level, artifact_id=ARTIFACT_ID):
    return svc.resolve_effective_permission(
        active_roles=roles,
        user_id=USER_ID,
        workspace_id=WORKSPACE_ID,
        artifact_id=artifact_id,
        level=level,
    )


# ---------------------------------------------------------------------------
# Level ordering helpers
# ---------------------------------------------------------------------------


class TestLevelOrdering:
    def test_rank_order_is_deny_read_write(self):
        assert more_restrictive_level("write", "read") == "read"
        assert more_restrictive_level("read", "write") == "read"
        assert more_restrictive_level("deny", "write") == "deny"
        assert more_restrictive_level("write", "deny") == "deny"
        assert more_restrictive_level("read", "read") == "read"

    def test_satisfies_is_monotonic(self):
        assert level_satisfies_level("write", "read") is True
        assert level_satisfies_level("write", "write") is True
        assert level_satisfies_level("read", "read") is True
        assert level_satisfies_level("read", "write") is False
        assert level_satisfies_level("deny", "read") is False
        assert level_satisfies_level("deny", "write") is False


# ---------------------------------------------------------------------------
# RBAC layer alone (no explicit item rule)
# ---------------------------------------------------------------------------


class TestRbacLayerAlone:
    @pytest.mark.parametrize(
        ("roles", "queried", "expected_level", "expected_allowed"),
        [
            (("viewer",), "read", "read", True),
            (("viewer",), "write", "read", False),
            # RBAC reports the caller's STRONGEST granted level, not the
            # queried one: an Editor asking about 'read' is reported at 'write'.
            (("editor",), "read", "write", True),
            (("editor",), "write", "write", True),
            (("admin",), "write", "write", True),
            (("approver",), "read", "write", True),
            ((), "read", "deny", False),
            (("unknown_role",), "read", "deny", False),
            ((), "write", "deny", False),
        ],
    )
    def test_silent_item_layer_defers_to_rbac(
        self, roles, queried, expected_level, expected_allowed
    ):
        """Fix #716 preserved: no explicit rule -> RBAC governs alone."""
        result = _resolve(_service(_silent()), roles=roles, level=queried)

        assert result.level == expected_level
        assert result.is_allowed is expected_allowed
        assert result.queried_level == queried

    def test_silent_item_layer_reason_is_the_rbac_reason(self):
        result = _resolve(_service(_silent()), roles=("viewer",), level="read")

        assert "viewer" in result.reason
        assert result.reason != NO_RULE_REASON

    def test_workspace_wide_check_does_not_require_an_artifact(self):
        result = _resolve(
            _service(_silent()), roles=("viewer",), level="read", artifact_id=None
        )

        assert result.level == "read"
        assert result.is_allowed is True


# ---------------------------------------------------------------------------
# Item layer restricts, never broadens
# ---------------------------------------------------------------------------


class TestItemLayerCombination:
    def test_explicit_deny_overrides_editor(self):
        result = _resolve(
            _service(_explicit("deny", "artifact-scoped rule grants 'none'")),
            roles=("editor",),
            level="read",
        )

        assert result.level == "deny"
        assert result.is_allowed is False
        assert result.reason == "artifact-scoped rule grants 'none'"

    def test_explicit_read_restricts_editor_write(self):
        result = _resolve(
            _service(_explicit("read", "workspace-wide rule grants 'read'")),
            roles=("editor",),
            level="write",
        )

        assert result.level == "read"
        assert result.is_allowed is False
        assert result.reason == "workspace-wide rule grants 'read'"

    def test_explicit_read_still_restricts_admin(self):
        result = _resolve(_service(_explicit("read")), roles=("admin",), level="read")

        assert result.level == "read"
        assert result.is_allowed is True

    def test_explicit_write_cannot_escalate_viewer(self):
        result = _resolve(_service(_explicit("write")), roles=("viewer",), level="write")

        assert result.level == "read"
        assert result.is_allowed is False

    def test_explicit_write_cannot_escalate_roleless_caller(self):
        result = _resolve(_service(_explicit("write")), roles=(), level="read")

        assert result.level == "deny"
        assert result.is_allowed is False

    def test_explicit_write_is_a_no_op_for_editor(self):
        result = _resolve(_service(_explicit("write")), roles=("editor",), level="read")

        assert result.level == "write"
        assert result.is_allowed is True
        # Equal levels -> the item layer's reason wins (ties resolve to the
        # more specific layer).
        assert result.reason == "artifact-scoped rule"


# ---------------------------------------------------------------------------
# The structured discriminator (#722, Finding 1)
# ---------------------------------------------------------------------------


class TestHasExplicitRuleDiscriminator:
    def test_default_looking_reason_still_restricts_when_flag_is_set(self):
        """THE regression test for the string sentinel.

        A rule-backed decision whose ``reason`` happens to be worded exactly
        like the closed-world default must still restrict. The old
        ``reason == NO_RULE_REASON`` compare silently dropped it.
        """
        decision = _explicit("deny", NO_RULE_REASON)

        result = _resolve(_service(decision), roles=("editor",), level="read")

        assert result.level == "deny"
        assert result.is_allowed is False
        assert result.reason == NO_RULE_REASON

    def test_non_default_reason_is_ignored_when_flag_is_unset(self):
        """Inverse direction: a silent item layer stays silent whatever its
        human-readable reason text says."""
        decision = _silent("deny", "artifact-scoped rule grants 'none' (explicit deny)")

        result = _resolve(_service(decision), roles=("editor",), level="write")

        assert result.level == "write"
        assert result.is_allowed is True
        assert result.reason != "artifact-scoped rule grants 'none' (explicit deny)"

    def test_flag_alone_decides_independent_of_level(self):
        """Same level and same reason text, opposite flags -> opposite answer."""
        reason = "workspace-wide rule grants 'read'"
        silent = _resolve(
            _service(_silent("read", reason)), roles=("editor",), level="write"
        )
        explicit = _resolve(
            _service(_explicit("read", reason)), roles=("editor",), level="write"
        )

        assert silent.level == "write"
        assert silent.is_allowed is True
        assert explicit.level == "read"
        assert explicit.is_allowed is False


# ---------------------------------------------------------------------------
# Validation + result shape
# ---------------------------------------------------------------------------


class TestValidation:
    @pytest.mark.parametrize("bad", ["", "  ", "admin", "none", None, 42])
    def test_invalid_level_raises_validation_error(self, bad):
        svc = _service(_silent())

        with pytest.raises(ValidationError):
            _resolve(svc, roles=("admin",), level=bad)

    def test_invalid_level_does_not_touch_the_item_layer(self):
        item_svc = _item_service(_silent())
        svc = EffectivePermissionService(
            item_permission_service=item_svc, authz_service=AuthorizationService()
        )

        with pytest.raises(ValidationError):
            _resolve(svc, roles=("admin",), level="superuser")

        item_svc.check_permission.assert_not_called()

    @pytest.mark.parametrize("raw", ["READ", " Read ", "write"])
    def test_level_is_normalised(self, raw):
        result = _resolve(_service(_silent()), roles=("editor",), level=raw)

        assert result.queried_level == raw.strip().lower()

    def test_returns_frozen_dataclass(self):
        result = _resolve(_service(_silent()), roles=("viewer",), level="read")

        assert isinstance(result, EffectivePermission)
        with pytest.raises(FrozenInstanceError):
            result.level = "write"  # type: ignore[misc]
