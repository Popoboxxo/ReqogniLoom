"""#1998/#2032 — permissions.check must reflect the API-key scope gate.

The resolver already merges RBAC with item-level rules; a role-admin AUTHOR key
was still reported as able to do everything because the credential's scope was
never passed in. These tests pin that the shared #865 scope gate now narrows the
reported answer without changing the gate itself.
"""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID

from application.effective_permission_service import (
    EffectivePermissionService,
)
from auth_tenancy.services.authorization import AuthorizationService
from auth_tenancy.services.item_permission import (
    NO_RULE_REASON,
    ItemPermissionService,
    PermissionDecision,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000010")
ARTIFACT_ID = UUID("00000000-0000-0000-0000-000000000030")


def _service() -> EffectivePermissionService:
    item = MagicMock(spec=ItemPermissionService)
    item.check_permission.return_value = PermissionDecision(
        level="deny", reason=NO_RULE_REASON, has_explicit_rule=False
    )
    item.check_permissions_batch.return_value = {
        ARTIFACT_ID: PermissionDecision(
            level="deny", reason=NO_RULE_REASON, has_explicit_rule=False
        )
    }
    return EffectivePermissionService(
        item_permission_service=item,
        authz_service=AuthorizationService(),
    )


def _write(**extra: object):
    return _service().resolve_effective_permission(
        active_roles=("admin",),
        user_id=USER_ID,
        workspace_id=WORKSPACE_ID,
        artifact_id=ARTIFACT_ID,
        level="write",
        **extra,
    )


def test_author_scope_reports_content_write_but_no_governance():
    result = _write(scope="author")
    assert result.level == "write"
    assert result.is_allowed is True
    assert result.governance_allowed is False
    assert "author" in result.reason
    assert "governance" in result.reason.lower()


def test_admin_scope_allows_governance():
    result = _write(scope="admin")
    assert result.is_allowed is True
    assert result.governance_allowed is True
    assert "governance" not in result.reason.lower()


def test_legacy_write_scope_keeps_admin_tier():
    result = _write(scope="write")
    assert result.is_allowed is True
    assert result.governance_allowed is True


def test_read_only_scope_clamps_write_to_read():
    result = _write(scope="read_only")
    assert result.level == "read"
    assert result.is_allowed is False
    assert "read-only" in result.reason


def test_unknown_scope_fails_closed_for_both_levels():
    write = _write(scope="nonsense")
    assert write.level == "deny"
    assert write.is_allowed is False
    read = _service().resolve_effective_permission(
        active_roles=("admin",),
        user_id=USER_ID,
        workspace_id=WORKSPACE_ID,
        level="read",
        scope="nonsense",
    )
    assert read.level == "deny"
    assert read.is_allowed is False


def test_no_scope_preserves_pre_2032_answer():
    result = _write()
    assert result.level == "write"
    assert result.is_allowed is True
    assert result.governance_allowed is True


def test_batch_path_applies_the_same_scope_gate():
    result = _service().resolve_effective_permissions_batch(
        active_roles=("admin",),
        user_id=USER_ID,
        workspace_id=WORKSPACE_ID,
        artifact_ids=[ARTIFACT_ID],
        level="write",
        scope="author",
    )[ARTIFACT_ID]
    single = _write(scope="author")
    assert result == single
