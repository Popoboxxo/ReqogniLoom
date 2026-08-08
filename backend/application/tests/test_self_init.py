"""
Tests for REQ-188 — Self-initialisation of a fresh deployment.

Covers the acceptance criterion verbatim: a fresh (empty) database, after the
self-init path runs, has BOTH an admin account AND default workflow
definitions for the base workspace — with no separate, manually-triggered
bootstrap step.

Two things are exercised, deliberately kept apart:

* ``run_self_init()`` (``application.self_init``) — the actual provisioning
  logic, executed end-to-end against an otherwise-empty database (no admin, no
  workspace pre-created), with NOTHING mocked out. This is the real proof of
  the REQ-188 acceptance criterion: leere DB -> Admin + Workflow-Definitionen,
  ganz ohne manuellen Zwischenschritt.
* the ``post_migrate`` receiver wiring (``application.apps``) — proves the
  trigger mechanism itself (guards + dispatch) is wired to call
  ``run_self_init()`` when a real ``migrate`` run applies, and is correctly
  suppressed for the pytest process (the guard the rest of this test suite
  relies on for isolation).

Both are needed to prove the acceptance criterion end-to-end: the receiver
test alone would only prove wiring (with the actual provisioning mocked away),
and the ``run_self_init()`` test alone would not prove it is the function a
real ``migrate`` actually calls.
"""
from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from application.self_init import run_self_init
from application.workspace_provisioning import WORKFLOW_ENTITY_TYPES
from auth_tenancy.provisioning import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_USERNAME
from persistence.models import User, Workspace
from persistence.tenancy import TenantContext
from workflow.models import GlobalWorkflowDefinition, WorkflowEngineDefinition

pytestmark = pytest.mark.django_db

# Requirement (tier-dependent) + the fixed-preset per-entity types.
_EXPECTED_WORKFLOW_ITEM_TYPES = {"Requirement"} | {
    item_type for item_type, _preset in WORKFLOW_ENTITY_TYPES
}

# REQ-178 bugfix: the "Global Workflow Defaults" tab lets an admin browse ANY
# entity type under ANY of the three rigor presets — independent of the fixed
# preset key (e.g. "need_default") that entity type's workspace-level workflow
# actually uses. All three must be pre-seeded, not just the base workspace's
# own tier ("extended").
_GLOBAL_TAB_PRESETS = ("minimal", "standard", "extended")


def _workflow_item_types_for(workspace_id) -> set[str]:
    TenantContext.set_tenant(_tenant_id_of(workspace_id))
    try:
        return set(
            WorkflowEngineDefinition.objects.filter(
                workspace_id=workspace_id
            ).values_list("item_type", flat=True)
        )
    finally:
        TenantContext.clear_tenant()


def _tenant_id_of(workspace_id):
    # unscoped: resolving the tenant itself must not depend on tenant scope
    # already being active.
    return Workspace.unscoped.get(id=workspace_id).tenant_id


# ---------------------------------------------------------------------------
# REQ-188 core acceptance criterion: run_self_init() on an empty database.
# ---------------------------------------------------------------------------


def test_run_self_init_on_empty_database_provisions_admin_and_workflows(monkeypatch):
    """[REQ-188] should provision admin user and all default workflow definitions from an empty database"""
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", "s3lf-init-pw-2026")
    assert User.objects.filter(username=DEFAULT_ADMIN_USERNAME).exists() is False

    run_self_init()

    admin = User.objects.get(username=DEFAULT_ADMIN_USERNAME)
    assert admin.email == DEFAULT_ADMIN_EMAIL
    assert admin.is_staff is True
    assert admin.is_superuser is True
    assert admin.check_password("s3lf-init-pw-2026") is True

    workspace = Workspace.unscoped.get(name="Demo Workspace")
    item_types = _workflow_item_types_for(workspace.id)
    assert item_types == _EXPECTED_WORKFLOW_ITEM_TYPES
    assert len(item_types) == 13


def test_run_self_init_is_idempotent_on_repeated_runs(monkeypatch):
    """[REQ-188] should not duplicate admin or workflow rows on a second self-init run"""
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", "s3lf-init-pw-2026")

    run_self_init()
    run_self_init()

    assert User.objects.filter(username=DEFAULT_ADMIN_USERNAME).count() == 1
    workspace = Workspace.unscoped.get(name="Demo Workspace")

    TenantContext.set_tenant(workspace.tenant_id)
    try:
        for item_type in _EXPECTED_WORKFLOW_ITEM_TYPES:
            assert (
                WorkflowEngineDefinition.objects.filter(
                    workspace_id=workspace.id, item_type=item_type
                ).count()
                == 1
            ), f"duplicate workflow definition for {item_type}"
    finally:
        TenantContext.clear_tenant()


def test_run_self_init_seeds_all_three_presets_as_global_workflow_defaults(
    monkeypatch,
):
    """[REQ-178] should pre-seed minimal/standard/extended GlobalWorkflowDefinition
    rows for every entity type, not just the base workspace's own "extended" tier.

    Regression test: the base workspace self-init creates is always tier
    "extended", so only "extended" global rows used to exist. The "Global
    Workflow Defaults" tab defaults to "standard", which made it look
    completely empty even though inheritance itself worked correctly.
    """
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", "s3lf-init-pw-2026")

    run_self_init()

    workspace = Workspace.unscoped.get(name="Demo Workspace")
    tenant_id = workspace.tenant_id

    seeded = set(
        GlobalWorkflowDefinition.unscoped.filter(tenant_id=tenant_id).values_list(
            "item_type", "preset"
        )
    )
    expected = {
        (item_type, preset)
        for item_type in _EXPECTED_WORKFLOW_ITEM_TYPES
        for preset in _GLOBAL_TAB_PRESETS
    }
    missing = expected - seeded
    assert not missing, f"missing GlobalWorkflowDefinition rows: {sorted(missing)}"

    # Every seeded row must actually carry a non-empty state machine, not just
    # an empty placeholder graph — otherwise the tab would still look empty.
    for item_type, preset in expected:
        row = GlobalWorkflowDefinition.unscoped.get(
            tenant_id=tenant_id, item_type=item_type, preset=preset
        )
        assert row.workflow_json.get("states"), f"{item_type}/{preset} has no states"


def test_run_self_init_global_preset_seeding_is_idempotent(monkeypatch):
    """[REQ-178] should not duplicate or overwrite GlobalWorkflowDefinition rows
    on a second self-init run."""
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", "s3lf-init-pw-2026")

    run_self_init()
    workspace = Workspace.unscoped.get(name="Demo Workspace")
    tenant_id = workspace.tenant_id

    # Simulate a manual customisation an admin might have made in between runs.
    customized = GlobalWorkflowDefinition.unscoped.get(
        tenant_id=tenant_id, item_type="Requirement", preset="standard"
    )
    customized.workflow_json = {"states": ["draft", "custom_state"], "transitions": []}
    customized.save(update_fields=["workflow_json"])

    run_self_init()

    for item_type in _EXPECTED_WORKFLOW_ITEM_TYPES:
        for preset in _GLOBAL_TAB_PRESETS:
            count = GlobalWorkflowDefinition.unscoped.filter(
                tenant_id=tenant_id, item_type=item_type, preset=preset
            ).count()
            assert count == 1, f"duplicate global row for {item_type}/{preset}"

    customized.refresh_from_db()
    assert customized.workflow_json["states"] == ["draft", "custom_state"], (
        "second self-init run must not overwrite an already-seeded/customised "
        "global row (get_or_create semantics)"
    )


def test_run_self_init_preserves_password_changed_after_creation(monkeypatch):
    """[REQ-188] should not overwrite an admin password that was rotated after the first self-init run"""
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", "initial-pw-2026")
    run_self_init()

    admin = User.objects.get(username=DEFAULT_ADMIN_USERNAME)
    admin.set_password("rotated-via-ui-2026")
    admin.save(update_fields=["password", "modified_at"])

    # Env var still holds the old value; a second self-init run must not
    # rewrite the password (create-only guarantee, mirrors bootstrap_admin).
    run_self_init()

    admin.refresh_from_db()
    assert admin.check_password("rotated-via-ui-2026") is True
    assert admin.check_password("initial-pw-2026") is False


def test_run_self_init_skips_admin_creation_without_password_but_does_not_raise(
    monkeypatch,
):
    """[REQ-188] should skip admin creation without raising when no admin exists and no password is configured"""
    monkeypatch.delenv("SYSTEM_ADMIN_PASSWORD", raising=False)

    run_self_init()  # must not raise — this runs inside post_migrate in production

    assert User.objects.filter(username=DEFAULT_ADMIN_USERNAME).exists() is False
    assert Workspace.unscoped.filter(name="Demo Workspace").exists() is False


# ---------------------------------------------------------------------------
# post_migrate receiver wiring (application.apps): proves the trigger itself,
# not just the underlying provisioning function, is connected correctly.
# ---------------------------------------------------------------------------


def test_post_migrate_receiver_invokes_self_init_outside_test_context(monkeypatch):
    """[REQ-188] should invoke run_self_init from the post_migrate receiver once SELF_INIT_ON_MIGRATE is enabled and no test runner is active"""
    from application import apps as apps_module
    from django.conf import settings as django_settings

    monkeypatch.setattr(django_settings, "SELF_INIT_ON_MIGRATE", True)
    monkeypatch.setattr(sys, "argv", ["manage.py", "migrate"])
    # Simulate a genuine (non-pytest) process for the receiver's defensive
    # check without disturbing the real, currently-running pytest session:
    # sys.modules is swapped for a copy with the "pytest" key removed, then
    # restored automatically by monkeypatch after the test.
    modules_without_pytest = {
        name: module for name, module in sys.modules.items() if name != "pytest"
    }
    monkeypatch.setattr(sys, "modules", modules_without_pytest)

    with patch("application.self_init.run_self_init") as mock_run_self_init:
        apps_module._run_self_init_on_migrate(sender=apps_module.ApplicationConfig)

    mock_run_self_init.assert_called_once_with()


def test_post_migrate_receiver_noop_when_self_init_on_migrate_disabled(monkeypatch):
    """[REQ-188] should not invoke run_self_init when SELF_INIT_ON_MIGRATE is disabled (test-suite isolation guard)"""
    from application import apps as apps_module
    from django.conf import settings as django_settings

    monkeypatch.setattr(django_settings, "SELF_INIT_ON_MIGRATE", False)

    with patch("application.self_init.run_self_init") as mock_run_self_init:
        apps_module._run_self_init_on_migrate(sender=apps_module.ApplicationConfig)

    mock_run_self_init.assert_not_called()


def test_post_migrate_receiver_noop_while_pytest_is_active(monkeypatch):
    """[REQ-188] should not invoke run_self_init while a pytest process is active, even if SELF_INIT_ON_MIGRATE is enabled"""
    from application import apps as apps_module
    from django.conf import settings as django_settings

    # Mirrors production settings (SELF_INIT_ON_MIGRATE defaults to True); the
    # defensive "pytest active" guard alone must still suppress self-init.
    monkeypatch.setattr(django_settings, "SELF_INIT_ON_MIGRATE", True)
    assert "pytest" in sys.modules  # sanity: this IS a pytest process

    with patch("application.self_init.run_self_init") as mock_run_self_init:
        apps_module._run_self_init_on_migrate(sender=apps_module.ApplicationConfig)

    mock_run_self_init.assert_not_called()


def test_application_config_registers_post_migrate_receiver():
    """[REQ-188] should register the self-init receiver on the post_migrate signal with the documented dispatch_uid"""
    from django.db.models.signals import post_migrate

    # ``Signal.receivers`` is a Django internal with no public introspection
    # equivalent, and its entry shape is NOT stable across Django versions:
    # Django 4.2 stored ``(lookup_key, receiver)`` while Django 5.0+ appends a
    # third ``is_async`` element (``(lookup_key, receiver, is_async)``) as part
    # of the async-signal support added in 5.0. Unpacking a fixed arity here
    # therefore broke on the 4.2 -> 5.2 upgrade with "too many values to
    # unpack (expected 2)".
    #
    # Only element 0 (the ``lookup_key``, itself a ``(dispatch_uid, sender_id)``
    # tuple) carries the contract under test, so index it positionally and stay
    # agnostic about how many elements follow — the same version-robust access
    # pattern already used in test_cache_invalidation.py.
    dispatch_uids = {
        entry[0][0] for entry in post_migrate.receivers if isinstance(entry[0], tuple)
    }
    assert "application.self_init.run_self_init" in dispatch_uids
