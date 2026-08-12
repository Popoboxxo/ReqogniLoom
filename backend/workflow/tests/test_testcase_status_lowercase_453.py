"""GH-453 — TestCase lifecycle states are lowercase, everywhere.

TestCase used to be the only persistence-app entity spelling its workflow
states in Title Case ("Draft"/"Ready"/"Approved"/"Deprecated"), so a
case-sensitive cross-entity query ("give me every draft item") silently skipped
every test case.

Covered here:
  * the ``TestCase.Status`` enum      — lowercase values, Title-Case labels;
  * the ``testcase_default`` preset   — states/transitions/state_meta in sync
                                        with the enum, and unchanged for the
                                        entities that legitimately keep Title
                                        Case (Adr/Risk/Issue);
  * the data migration                — forwards AND backwards, across all four
                                        storage locations and without touching
                                        other item types;
  * a live transition                 — the mirror written by
                                        ``_sync_status_mirror`` is lowercase.

The REST round-trip lives in ``rest_api/tests/test_testcase_status_lowercase_453.py``.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from importlib import import_module
from uuid import uuid4

import pytest
from django.db import connection
from django.db.migrations.loader import MigrationLoader

from auth_tenancy.context import AuthContext
from persistence.models import Artifact, Tenant, TestCase, User, Workspace
from persistence.tenancy import TenantContext
from workflow.definition_store import PRESET_SCHEMAS
from workflow.models import (
    GlobalWorkflowDefinition,
    WorkflowEngineDefinition,
    WorkflowHistoryEntry,
    WorkflowItemState,
)

pytestmark = pytest.mark.django_db

_mig = import_module("workflow.migrations.0014_testcase_status_lowercase")
migration_forwards = _mig.forwards
migration_backwards = _mig.backwards

OLD_STATES = ["Draft", "Ready", "Approved", "Deprecated"]
NEW_STATES = ["draft", "ready", "approved", "deprecated"]


@contextmanager
def _tenant_scope(tenant_id):
    """Tenant-scoped models need an active TenantContext (ADR-03)."""
    TenantContext.set_tenant(tenant_id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="gh453-tenant", slug="gh453-tenant")


@pytest.fixture
def second_tenant():
    """A second tenant proves the migration is not silently tenant-scoped."""
    return Tenant.objects.create(name="gh453-tenant-2", slug="gh453-tenant-2")


@pytest.fixture
def historical_apps():
    """The app registry a RunPython actually receives.

    Rendering the migration project state (rather than passing
    ``django.apps.apps``) is what makes this test meaningful: historical models
    carry a plain, unscoped manager because ``persistence.tenancy.TenantManager``
    does not set ``use_in_migrations``. Handing the migration the *real*
    registry would run every query through the tenant-scoped manager and would
    therefore pass even if the migration only ever reached a single tenant.
    """
    return MigrationLoader(connection).project_state().apps


# ---------------------------------------------------------------------------
# Enum + preset schema
# ---------------------------------------------------------------------------


def test_testcase_status_enum_values_are_lowercase() -> None:
    assert [choice.value for choice in TestCase.Status] == NEW_STATES


def test_testcase_status_enum_labels_stay_human_readable() -> None:
    """The rename is a *value* change; the display label must not regress."""
    assert [choice.label for choice in TestCase.Status] == [
        "Draft",
        "Ready",
        "Approved",
        "Deprecated",
    ]


def test_testcase_status_default_is_lowercase_draft() -> None:
    field = TestCase._meta.get_field("status")
    assert field.default == TestCase.Status.DRAFT
    assert str(field.default) == "draft"


def test_testcase_default_preset_states_match_the_enum() -> None:
    """The mirror is written verbatim, so preset and enum must agree byte for
    byte — the invariant TestCase.Status's docstring declares."""
    schema = PRESET_SCHEMAS["testcase_default"]
    assert schema["states"] == [choice.value for choice in TestCase.Status]


def test_testcase_default_preset_transitions_reference_declared_states() -> None:
    schema = PRESET_SCHEMAS["testcase_default"]
    declared = set(schema["states"])
    for transition in schema["transitions"]:
        assert transition["from_state"] in declared, transition
        assert transition["to_state"] in declared, transition


def test_testcase_default_state_meta_key_was_renamed_too() -> None:
    """A stale ``"Deprecated"`` key would silently disable the
    is_outdated_equivalent flag (get_state_meta looks up by state name)."""
    schema = PRESET_SCHEMAS["testcase_default"]
    assert schema["state_meta"] == {"deprecated": {"is_outdated_equivalent": True}}


@pytest.mark.parametrize(
    "preset,expected_first_state",
    [("adr_default", "Draft"), ("risk_default", "Identified"), ("issue_default", "Open")],
)
def test_other_presets_keep_their_own_vocabulary(
    preset: str, expected_first_state: str
) -> None:
    """Guard against the obvious over-reach: Adr/Risk/Issue share literals with
    the old TestCase spelling and must NOT have been lowercased."""
    assert PRESET_SCHEMAS[preset]["states"][0] == expected_first_state


# ---------------------------------------------------------------------------
# Data migration
# ---------------------------------------------------------------------------


def _legacy_testcase_workflow_json() -> dict:
    return {
        "states": list(OLD_STATES),
        "transitions": [
            {
                "from_state": "Draft",
                "to_state": "Ready",
                "allowed_roles": ["editor", "admin"],
                "requires_change_reason": False,
                "signature_gate": False,
            },
            {
                "from_state": "Approved",
                "to_state": "Deprecated",
                "allowed_roles": ["approver", "admin"],
                "requires_change_reason": False,
                "signature_gate": False,
            },
        ],
        "state_meta": {"Deprecated": {"is_outdated_equivalent": True}},
    }


def _adr_workflow_json() -> dict:
    return {
        "states": ["Draft", "In Review", "Approved", "Rejected", "Superseded"],
        "transitions": [
            {
                "from_state": "Draft",
                "to_state": "In Review",
                "allowed_roles": ["editor", "admin"],
                "requires_change_reason": False,
                "signature_gate": False,
            }
        ],
        "state_meta": {"Approved": {"auto_approve_target": True}},
    }


def _seed_legacy_rows(tenant, label: str = "gh453") -> dict:
    """Create pre-GH-453 rows in every storage location the migration touches,
    plus an Adr control row that must survive untouched."""
    workspace_id = uuid4()
    with _tenant_scope(tenant.id):
        workspace = Workspace.objects.create(tenant=tenant, name=f"{label}-ws")
        global_def = GlobalWorkflowDefinition.objects.create(
            tenant=tenant,
            item_type="TestCase",
            preset="testcase_default",
            workflow_json=_legacy_testcase_workflow_json(),
        )
        engine_def = WorkflowEngineDefinition.objects.create(
            tenant=tenant,
            workspace_id=workspace_id,
            item_type="TestCase",
            preset="testcase_default",
            workflow_json=_legacy_testcase_workflow_json(),
            source_global=global_def,
        )
        # A workspace that diverged from the global default: still must be
        # renamed, otherwise its item states point at names it no longer holds.
        customized_def = WorkflowEngineDefinition.objects.create(
            tenant=tenant,
            workspace_id=uuid4(),
            item_type="TestCase",
            preset="testcase_default",
            workflow_json=_legacy_testcase_workflow_json(),
            is_customized=True,
        )
        adr_global = GlobalWorkflowDefinition.objects.create(
            tenant=tenant,
            item_type="Adr",
            preset="adr_default",
            workflow_json=_adr_workflow_json(),
        )
        adr_def = WorkflowEngineDefinition.objects.create(
            tenant=tenant,
            workspace_id=workspace_id,
            item_type="Adr",
            preset="adr_default",
            workflow_json=_adr_workflow_json(),
        )

        item_state = WorkflowItemState.objects.create(
            tenant=tenant,
            item_id=uuid4(),
            item_type="TestCase",
            workspace_id=workspace_id,
            definition=engine_def,
            current_state="Approved",
        )
        history = WorkflowHistoryEntry.objects.create(
            tenant=tenant,
            item_state=item_state,
            workspace_id=workspace_id,
            from_state="Ready",
            to_state="Approved",
            transitioned_by="tester",
            transitioned_at=datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc),
        )
        adr_state = WorkflowItemState.objects.create(
            tenant=tenant,
            item_id=uuid4(),
            item_type="Adr",
            workspace_id=workspace_id,
            definition=adr_def,
            current_state="Approved",
        )

        artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="TestCase"
        )
        test_case = TestCase.objects.create(
            tenant=tenant, artifact=artifact, title="legacy TC"
        )
        # Bypass the model default so the row carries the pre-migration value.
        TestCase.objects.filter(pk=test_case.pk).update(status="Approved")

        # An already-soft-deleted TestCase: "outdated" is written outside the
        # preset's state list and is already lowercase — it must pass through
        # both directions untouched.
        outdated_artifact = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="TestCase"
        )
        outdated_tc = TestCase.objects.create(
            tenant=tenant, artifact=outdated_artifact, title="outdated TC"
        )
        TestCase.objects.filter(pk=outdated_tc.pk).update(status="outdated")

    return {
        "global_def": global_def,
        "engine_def": engine_def,
        "customized_def": customized_def,
        "adr_global": adr_global,
        "adr_def": adr_def,
        "item_state": item_state,
        "history": history,
        "adr_state": adr_state,
        "test_case": test_case,
        "outdated_tc": outdated_tc,
    }


def test_migration_forwards_lowercases_every_storage_location(tenant, historical_apps) -> None:
    rows = _seed_legacy_rows(tenant)

    migration_forwards(historical_apps, None)

    with _tenant_scope(tenant.id):
        for key in ("global_def", "engine_def", "customized_def"):
            rows[key].refresh_from_db()
            payload = rows[key].workflow_json
            assert payload["states"] == NEW_STATES, key
            assert payload["transitions"][0]["from_state"] == "draft", key
            assert payload["transitions"][0]["to_state"] == "ready", key
            assert payload["transitions"][1]["from_state"] == "approved", key
            assert payload["transitions"][1]["to_state"] == "deprecated", key
            assert payload["state_meta"] == {
                "deprecated": {"is_outdated_equivalent": True}
            }, key

        rows["item_state"].refresh_from_db()
        assert rows["item_state"].current_state == "approved"

        rows["history"].refresh_from_db()
        assert rows["history"].from_state == "ready"
        assert rows["history"].to_state == "approved"

        rows["test_case"].refresh_from_db()
        assert rows["test_case"].status == "approved"


def test_migration_forwards_leaves_other_item_types_alone(tenant, historical_apps) -> None:
    """The whole point of filtering on item_type: Adr shares the literals."""
    rows = _seed_legacy_rows(tenant)

    migration_forwards(historical_apps, None)

    with _tenant_scope(tenant.id):
        for key in ("adr_global", "adr_def"):
            rows[key].refresh_from_db()
            assert rows[key].workflow_json["states"] == [
                "Draft",
                "In Review",
                "Approved",
                "Rejected",
                "Superseded",
            ], key
            assert rows[key].workflow_json["state_meta"] == {
                "Approved": {"auto_approve_target": True}
            }, key

        rows["adr_state"].refresh_from_db()
        assert rows["adr_state"].current_state == "Approved"


def test_migration_forwards_leaves_outdated_soft_delete_state_alone(tenant, historical_apps) -> None:
    rows = _seed_legacy_rows(tenant)

    migration_forwards(historical_apps, None)

    with _tenant_scope(tenant.id):
        rows["outdated_tc"].refresh_from_db()
        assert rows["outdated_tc"].status == "outdated"


def test_migration_forwards_reaches_every_tenant(
    tenant, second_tenant, historical_apps
) -> None:
    """Multi-tenancy: the backfill must not stop at whichever tenant happened
    to be in the thread-local TenantContext when it ran."""
    rows_a = _seed_legacy_rows(tenant)
    rows_b = _seed_legacy_rows(second_tenant, label="gh453b")

    # Deliberately run with tenant A active: a tenant-scoped query would then
    # leave tenant B's rows behind.
    with _tenant_scope(tenant.id):
        migration_forwards(historical_apps, None)

    for owner, rows in ((tenant, rows_a), (second_tenant, rows_b)):
        with _tenant_scope(owner.id):
            rows["engine_def"].refresh_from_db()
            rows["item_state"].refresh_from_db()
            rows["test_case"].refresh_from_db()
            assert rows["engine_def"].workflow_json["states"] == NEW_STATES
            assert rows["item_state"].current_state == "approved"
            assert rows["test_case"].status == "approved"


def test_migration_is_idempotent(tenant, historical_apps) -> None:
    rows = _seed_legacy_rows(tenant)

    migration_forwards(historical_apps, None)
    migration_forwards(historical_apps, None)

    with _tenant_scope(tenant.id):
        rows["engine_def"].refresh_from_db()
        rows["item_state"].refresh_from_db()
        assert rows["engine_def"].workflow_json["states"] == NEW_STATES
        assert rows["item_state"].current_state == "approved"


def test_migration_backwards_restores_the_previous_spelling(tenant, historical_apps) -> None:
    rows = _seed_legacy_rows(tenant)

    migration_forwards(historical_apps, None)
    migration_backwards(historical_apps, None)

    with _tenant_scope(tenant.id):
        for key in ("global_def", "engine_def", "customized_def"):
            rows[key].refresh_from_db()
            payload = rows[key].workflow_json
            assert payload["states"] == OLD_STATES, key
            assert payload["state_meta"] == {
                "Deprecated": {"is_outdated_equivalent": True}
            }, key

        rows["item_state"].refresh_from_db()
        assert rows["item_state"].current_state == "Approved"

        rows["history"].refresh_from_db()
        assert rows["history"].from_state == "Ready"
        assert rows["history"].to_state == "Approved"

        rows["test_case"].refresh_from_db()
        assert rows["test_case"].status == "Approved"

        rows["outdated_tc"].refresh_from_db()
        assert rows["outdated_tc"].status == "outdated"

        # The reverse must not spill over into other item types either.
        rows["adr_state"].refresh_from_db()
        assert rows["adr_state"].current_state == "Approved"


# ---------------------------------------------------------------------------
# Live transition — the status mirror
# ---------------------------------------------------------------------------


def test_live_transition_writes_a_lowercase_status_mirror(tenant) -> None:
    """End-to-end proof that definition, item state and mirror agree after the
    rename: a real transition through the real preset."""
    from application.test_service import TestService
    from workflow.services import create_default_workflow, transition

    user = User.objects.create(
        username="gh453-user", email="gh453@example.com", tenant=tenant
    )
    with _tenant_scope(tenant.id):
        workspace = Workspace.objects.create(tenant=tenant, name="gh453-live-ws")
        create_default_workflow(
            workspace_id=workspace.id,
            preset="testcase_default",
            item_type="TestCase",
            tenant_id=tenant.id,
        )

    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor", "approver", "admin"),
        auth_method="test",
        api_key_id=None,
        tenant_name="gh453-tenant",
    )

    service = TestService()
    test_case = service.create_test_case(
        workspace_id=workspace.id, title="live TC", ctx=ctx
    )

    with _tenant_scope(tenant.id):
        state = WorkflowItemState.objects.get(
            item_id=test_case.id, item_type="TestCase"
        )
        assert state.current_state == "draft"

    # workflow.services.transition reads WorkflowItemState through the
    # tenant-scoped manager and does not derive the context from ``ctx``.
    with _tenant_scope(tenant.id):
        transition(
            item_id=test_case.id,
            target_state="ready",
            change_reason="",
            ctx=ctx,
            item_type="TestCase",
            workspace_id=workspace.id,
        )
        transition(
            item_id=test_case.id,
            target_state="approved",
            change_reason="reviewed",
            ctx=ctx,
            item_type="TestCase",
            workspace_id=workspace.id,
        )

    with _tenant_scope(tenant.id):
        state.refresh_from_db()
        assert state.current_state == "approved"
        test_case.refresh_from_db()
        assert test_case.status == "approved"
        assert test_case.status == TestCase.Status.APPROVED
