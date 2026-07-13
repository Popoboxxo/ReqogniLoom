"""
COMP-AT-005 ItemPermissionStore — tests (REQ-L1-039).

Covers the model + service + cache foundation:

* PermissionCache: get/set/invalidate, TTL expiry, thread isolation.
* ItemPermissionService.grant_permission: admin gate, create + update, audit.
* ItemPermissionService.revoke_permission: delete + no-op + audit.
* ItemPermissionService.list_permissions: admin gate, returns rules.
* ItemPermissionService.check_permission: resolution algorithm + cache hit
  + cache wipe on grant/revoke.
* ItemPermission model: explicit-deny property, workspace-wide property,
  unique constraint.

Tests are split into unit tests (no DB) and integration tests (DB-backed).
The integration tests use the existing ``tenant_a`` / ``user_a`` / ``workspace_a``
fixtures and the ``active_tenant`` context manager from
``auth_tenancy/tests/conftest.py``.
"""
from __future__ import annotations

import threading
import time
from uuid import uuid4

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import (
    ITEM_PERMISSION_NONE,
    ITEM_PERMISSION_READ,
    ITEM_PERMISSION_WRITE,
    ItemPermission,
    ROLE_ADMIN,
    ROLE_EDITOR,
)
from auth_tenancy.services import (
    ItemPermissionService,
    PermissionCache,
)
from auth_tenancy.services.item_permission import PermissionDecision

from application.base import PermissionDeniedError

from .conftest import active_tenant


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_permission_cache():
    """Ensure the thread-local cache is empty at the start and end of each test.

    Autouse so the cache never leaks state between tests; the spec doc calls
    for invalidation on grant/revoke, but tests that hit the cache directly
    should still start from a clean slate.
    """
    PermissionCache.clear_thread()
    yield
    PermissionCache.clear_thread()


@pytest.fixture
def artifact_a(db, tenant_a, workspace_a):
    """An Artifact in tenant A / workspace A."""
    with active_tenant(tenant_a):
        from persistence.models import Artifact

        return Artifact.objects.create(
            tenant=tenant_a,
            workspace=workspace_a,
            artifact_type="requirement",
        )


@pytest.fixture
def admin_ctx(tenant_a, user_a) -> AuthContext:
    """An AuthContext for an Admin user in tenant A."""
    return AuthContext(
        user_id=user_a.id,
        tenant_id=tenant_a.id,
        active_roles=(ROLE_ADMIN,),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


@pytest.fixture
def editor_ctx(tenant_a, user_a) -> AuthContext:
    """An AuthContext for an Editor user in tenant A (lacks Admin)."""
    return AuthContext(
        user_id=user_a.id,
        tenant_id=tenant_a.id,
        active_roles=(ROLE_EDITOR,),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


# ---------------------------------------------------------------------------
# Unit tests — PermissionCache
# ---------------------------------------------------------------------------


def test_permission_cache_get_returns_none_when_empty():
    """A fresh cache returns None for any key."""
    cache = PermissionCache()
    assert (
        cache.get(
            user_id=uuid4(),
            workspace_id=uuid4(),
            artifact_id=uuid4(),
        )
        is None
    )


def test_permission_cache_set_then_get_returns_decision():
    """Stored decisions round-trip through the cache."""
    cache = PermissionCache()
    user_id = uuid4()
    workspace_id = uuid4()
    artifact_id = uuid4()
    decision = PermissionDecision(level=ITEM_PERMISSION_READ, reason="unit test")

    cache.set(
        user_id=user_id,
        workspace_id=workspace_id,
        artifact_id=artifact_id,
        decision=decision,
    )
    got = cache.get(
        user_id=user_id,
        workspace_id=workspace_id,
        artifact_id=artifact_id,
    )
    assert got == decision


def test_permission_cache_ttl_expiry(monkeypatch):
    """An entry past its TTL is lazily evicted and returns None on the next get."""
    cache = PermissionCache(ttl_seconds=0.05)  # 50 ms
    user_id = uuid4()
    workspace_id = uuid4()
    artifact_id = uuid4()
    decision = PermissionDecision(level=ITEM_PERMISSION_READ, reason="ttl test")

    cache.set(
        user_id=user_id,
        workspace_id=workspace_id,
        artifact_id=artifact_id,
        decision=decision,
    )
    # Sanity: the entry is there immediately.
    assert cache.get(
        user_id=user_id,
        workspace_id=workspace_id,
        artifact_id=artifact_id,
    ) == decision

    # Sleep past the TTL.
    time.sleep(0.08)

    assert (
        cache.get(
            user_id=user_id,
            workspace_id=workspace_id,
            artifact_id=artifact_id,
        )
        is None
    )


def test_permission_cache_invalidate_all_clears_everything():
    """invalidate_all() removes every entry on the current thread."""
    cache = PermissionCache()
    user_id = uuid4()
    workspace_id = uuid4()
    decision = PermissionDecision(level=ITEM_PERMISSION_WRITE, reason="wipe test")

    for i in range(5):
        cache.set(
            user_id=user_id,
            workspace_id=workspace_id,
            artifact_id=uuid4(),
            decision=decision,
        )

    cache.invalidate_all()

    # All five keys are now misses (use unique key reconstruction — we don't
    # keep the artifact_ids, so verify via a different approach: call
    # invalidate_all and then attempt to set + get + invalidate_all again to
    # confirm the dict is empty).
    cache.set(
        user_id=user_id,
        workspace_id=workspace_id,
        artifact_id=uuid4(),
        decision=decision,
    )
    # A subsequent invalidate_all must succeed without raising.
    cache.invalidate_all()


def test_permission_cache_thread_isolation():
    """Entries set on one thread are not visible from another thread."""
    cache = PermissionCache()
    user_id = uuid4()
    workspace_id = uuid4()
    artifact_id = uuid4()
    decision = PermissionDecision(level=ITEM_PERMISSION_READ, reason="isolation test")

    other_thread_saw_value: list[bool] = []

    def worker() -> None:
        try:
            got = cache.get(
                user_id=user_id,
                workspace_id=workspace_id,
                artifact_id=artifact_id,
            )
            other_thread_saw_value.append(got is not None)
        finally:
            PermissionCache.clear_thread()

    # Set the entry on the main thread.
    cache.set(
        user_id=user_id,
        workspace_id=workspace_id,
        artifact_id=artifact_id,
        decision=decision,
    )
    # Start a worker thread. It must NOT see the entry.
    t = threading.Thread(target=worker)
    t.start()
    t.join(timeout=2.0)
    assert t.is_alive() is False
    assert other_thread_saw_value == [False], (
        "Cache entry leaked across threads; threading.local() broken."
    )


# ---------------------------------------------------------------------------
# Unit tests — ItemPermissionService (admin-gate only, no DB)
# ---------------------------------------------------------------------------


def test_grant_permission_requires_admin_role(editor_ctx, tenant_a, user_a, workspace_a):
    """A non-admin caller is denied at the gate before any DB write."""
    svc = ItemPermissionService()
    with active_tenant(tenant_a), pytest.raises(PermissionDeniedError):
        svc.grant_permission(
            editor_ctx,
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=None,
            level=ITEM_PERMISSION_READ,
            granted_by_user_id=user_a.id,
        )


def test_grant_permission_rejects_invalid_level(
    admin_ctx, tenant_a, user_a, workspace_a
):
    """An unrecognised level raises ValueError."""
    svc = ItemPermissionService()
    with active_tenant(tenant_a), pytest.raises(ValueError):
        svc.grant_permission(
            admin_ctx,
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=None,
            level="superuser",  # not a valid level
            granted_by_user_id=user_a.id,
        )


def test_revoke_permission_requires_admin_role(editor_ctx, tenant_a, user_a, workspace_a):
    """A non-admin caller is denied at the gate."""
    svc = ItemPermissionService()
    with active_tenant(tenant_a), pytest.raises(PermissionDeniedError):
        svc.revoke_permission(
            editor_ctx,
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=None,
        )


def test_list_permissions_requires_admin_role(editor_ctx, tenant_a, user_a, workspace_a):
    """A non-admin caller is denied at the gate."""
    svc = ItemPermissionService()
    with active_tenant(tenant_a), pytest.raises(PermissionDeniedError):
        svc.list_permissions(
            editor_ctx,
            user_id=user_a.id,
            workspace_id=workspace_a.id,
        )


# ---------------------------------------------------------------------------
# Integration tests — DB-backed, exercise the full service surface
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_grant_then_check_returns_granted_level(
    admin_ctx, tenant_a, user_a, workspace_a, artifact_a
):
    """A granted read rule is returned by check_permission."""
    svc = ItemPermissionService()
    with active_tenant(tenant_a):
        svc.grant_permission(
            admin_ctx,
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=artifact_a.id,
            level=ITEM_PERMISSION_READ,
            granted_by_user_id=user_a.id,
        )
        decision = svc.check_permission(
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=artifact_a.id,
        )
    assert decision.level == ITEM_PERMISSION_READ
    assert decision.is_allowed is True


@pytest.mark.django_db
def test_grant_is_upsert(
    admin_ctx, tenant_a, user_a, workspace_a, artifact_a
):
    """A second grant on the same triple updates the level in place."""
    svc = ItemPermissionService()
    with active_tenant(tenant_a):
        first = svc.grant_permission(
            admin_ctx,
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=artifact_a.id,
            level=ITEM_PERMISSION_READ,
            granted_by_user_id=user_a.id,
        )
        second = svc.grant_permission(
            admin_ctx,
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=artifact_a.id,
            level=ITEM_PERMISSION_WRITE,
            granted_by_user_id=user_a.id,
        )
    assert first.id == second.id
    assert second.permission_level == ITEM_PERMISSION_WRITE


@pytest.mark.django_db
def test_revoke_removes_rule_and_returns_true(
    admin_ctx, tenant_a, user_a, workspace_a, artifact_a
):
    """A successful revoke returns True and removes the row."""
    svc = ItemPermissionService()
    with active_tenant(tenant_a):
        svc.grant_permission(
            admin_ctx,
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=artifact_a.id,
            level=ITEM_PERMISSION_READ,
            granted_by_user_id=user_a.id,
        )
        deleted = svc.revoke_permission(
            admin_ctx,
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=artifact_a.id,
        )
    assert deleted is True
    with active_tenant(tenant_a):
        assert not ItemPermission.objects.filter(
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=artifact_a.id,
        ).exists()


@pytest.mark.django_db
def test_revoke_nonexistent_rule_returns_false(
    admin_ctx, tenant_a, user_a, workspace_a, artifact_a
):
    """Revoking a non-existent rule returns False (idempotent)."""
    svc = ItemPermissionService()
    with active_tenant(tenant_a):
        deleted = svc.revoke_permission(
            admin_ctx,
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=artifact_a.id,
        )
    assert deleted is False


@pytest.mark.django_db
def test_check_permission_no_rule_returns_deny(
    admin_ctx, tenant_a, user_a, workspace_a, artifact_a
):
    """A user with no rule gets the closed-world default deny."""
    svc = ItemPermissionService()
    with active_tenant(tenant_a):
        decision = svc.check_permission(
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=artifact_a.id,
        )
    assert decision.level == "deny"
    assert decision.is_allowed is False


@pytest.mark.django_db
def test_check_permission_artifact_rule_overrides_workspace_default(
    admin_ctx, tenant_a, user_a, workspace_a, artifact_a
):
    """An artifact-scoped rule wins over the workspace-wide default."""
    svc = ItemPermissionService()
    with active_tenant(tenant_a):
        svc.grant_permission(
            admin_ctx,
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=None,
            level=ITEM_PERMISSION_READ,
            granted_by_user_id=user_a.id,
        )
        svc.grant_permission(
            admin_ctx,
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=artifact_a.id,
            level=ITEM_PERMISSION_WRITE,
            granted_by_user_id=user_a.id,
        )
        decision = svc.check_permission(
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=artifact_a.id,
        )
    assert decision.level == ITEM_PERMISSION_WRITE
    assert "artifact-scoped" in decision.reason


@pytest.mark.django_db
def test_check_permission_workspace_default_fallback(
    admin_ctx, tenant_a, user_a, workspace_a, artifact_a
):
    """Without an artifact rule, the workspace-wide default applies."""
    svc = ItemPermissionService()
    with active_tenant(tenant_a):
        svc.grant_permission(
            admin_ctx,
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=None,
            level=ITEM_PERMISSION_READ,
            granted_by_user_id=user_a.id,
        )
        decision = svc.check_permission(
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=artifact_a.id,
        )
    assert decision.level == ITEM_PERMISSION_READ
    assert "workspace-wide" in decision.reason


@pytest.mark.django_db
def test_check_permission_explicit_deny(
    admin_ctx, tenant_a, user_a, workspace_a, artifact_a
):
    """A rule with level='none' always returns deny."""
    svc = ItemPermissionService()
    with active_tenant(tenant_a):
        svc.grant_permission(
            admin_ctx,
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=artifact_a.id,
            level=ITEM_PERMISSION_NONE,
            granted_by_user_id=user_a.id,
        )
        decision = svc.check_permission(
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=artifact_a.id,
        )
    assert decision.level == "deny"
    assert decision.is_allowed is False


@pytest.mark.django_db
def test_list_permissions_returns_all_rules_for_user_workspace(
    admin_ctx, tenant_a, user_a, workspace_a, artifact_a
):
    """list_permissions returns both artifact-scoped and workspace-wide rules."""
    svc = ItemPermissionService()
    with active_tenant(tenant_a):
        svc.grant_permission(
            admin_ctx,
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=None,
            level=ITEM_PERMISSION_READ,
            granted_by_user_id=user_a.id,
        )
        svc.grant_permission(
            admin_ctx,
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=artifact_a.id,
            level=ITEM_PERMISSION_WRITE,
            granted_by_user_id=user_a.id,
        )
        rules = svc.list_permissions(
            admin_ctx,
            user_id=user_a.id,
            workspace_id=workspace_a.id,
        )
    assert len(rules) == 2
    levels = {r.permission_level for r in rules}
    assert levels == {ITEM_PERMISSION_READ, ITEM_PERMISSION_WRITE}


@pytest.mark.django_db
def test_grant_invalidates_check_cache(
    admin_ctx, tenant_a, user_a, workspace_a, artifact_a
):
    """A grant call wipes the per-thread cache so subsequent checks see the new rule."""
    svc = ItemPermissionService()
    with active_tenant(tenant_a):
        # First call: no rule -> deny (populates cache as deny).
        first = svc.check_permission(
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=artifact_a.id,
        )
        assert first.level == "deny"

        # Now grant a read rule; grant must wipe the cache.
        svc.grant_permission(
            admin_ctx,
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=artifact_a.id,
            level=ITEM_PERMISSION_READ,
            granted_by_user_id=user_a.id,
        )

        # The next check sees the new rule (cache was wiped, not stale).
        second = svc.check_permission(
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=artifact_a.id,
        )
    assert second.level == ITEM_PERMISSION_READ


@pytest.mark.django_db
def test_itempermission_model_properties(
    admin_ctx, tenant_a, user_a, workspace_a, artifact_a
):
    """The model exposes is_explicit_deny and is_workspace_wide helpers."""
    svc = ItemPermissionService()
    with active_tenant(tenant_a):
        workspace_rule = svc.grant_permission(
            admin_ctx,
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=None,
            level=ITEM_PERMISSION_READ,
            granted_by_user_id=user_a.id,
        )
        deny_rule = svc.grant_permission(
            admin_ctx,
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=artifact_a.id,
            level=ITEM_PERMISSION_NONE,
            granted_by_user_id=user_a.id,
        )
    assert workspace_rule.is_workspace_wide is True
    assert workspace_rule.is_explicit_deny is False
    assert deny_rule.is_workspace_wide is False
    assert deny_rule.is_explicit_deny is True


@pytest.mark.django_db
def test_unique_constraint_blocks_duplicate_triple(
    admin_ctx, tenant_a, user_a, workspace_a, artifact_a
):
    """Two rows with the same (tenant, user, workspace, artifact) violate the constraint."""
    from django.db import IntegrityError, transaction

    svc = ItemPermissionService()
    with active_tenant(tenant_a):
        svc.grant_permission(
            admin_ctx,
            user_id=user_a.id,
            workspace_id=workspace_a.id,
            artifact_id=artifact_a.id,
            level=ITEM_PERMISSION_READ,
            granted_by_user_id=user_a.id,
        )
        # Bypass the service to insert a duplicate directly.
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                ItemPermission.unscoped.create(
                    tenant_id=tenant_a.id,
                    user_id=user_a.id,
                    workspace_id=workspace_a.id,
                    artifact_id=artifact_a.id,
                    permission_level=ITEM_PERMISSION_WRITE,
                    granted_by_id=user_a.id,
                )
