"""GH-1881 — data-migration test for
``workflow.migrations.0027_issue_state_vocabulary_lowercase``.

The migration is a pure data rewrite (no schema change), so the real
``forwards``/``backwards`` callables are exercised directly against live rows,
the same way ``test_seed_issue_resolved_auto_approve_target_migration.py``
does. The migration itself reaches rows through ``Model.unscoped`` so a
missing ``TenantContext`` cannot narrow the backfill — that is asserted below
by running it with **no** tenant context while two tenants hold legacy rows.

Coverage:
  * all four storage locations (global definition, engine definition, item
    state, history) are rewritten;
  * a customized definition is rewritten too (otherwise its item states point
    at names it no longer contains);
  * other item types sharing the same literal strings (``risk_default`` has
    "Closed", ``adr_default`` has "Approved") are untouched;
  * unknown, admin-authored Issue states pass through verbatim;
  * the JSON payload keeps its key order and unrelated keys;
  * the migration is idempotent and reversible.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from importlib import import_module
from uuid import uuid4

import pytest
from django.apps import apps as django_apps

from persistence.models import Tenant, Workspace
from persistence.tenancy import TenantContext
from workflow.models import (
    GlobalWorkflowDefinition,
    WorkflowEngineDefinition,
    WorkflowHistoryEntry,
    WorkflowItemState,
)

pytestmark = pytest.mark.django_db

_mig = import_module(
    "workflow.migrations.0027_issue_state_vocabulary_lowercase"
)
migration_forwards = _mig.forwards
migration_backwards = _mig.backwards

OLD_STATES = [
    "Open",
    "proposed",
    "In Progress",
    "Resolved",
    "Closed",
    "Wontfix",
    "rejected",
]
NEW_STATES = [
    "open",
    "proposed",
    "in_progress",
    "resolved",
    "closed",
    "wontfix",
    "rejected",
]


@contextmanager
def _tenant_scope(tenant_id):
    """Tenant-scoped models need an active TenantContext for their default
    manager (ADR-03). The migration under test does not — it uses ``unscoped``;
    this helper exists so the *fixtures* can create rows normally."""
    TenantContext.set_tenant(tenant_id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def tenant():
    return Tenant.objects.create(name="gh1881m-tenant", slug="gh1881m-tenant")


@pytest.fixture
def second_tenant():
    """A second tenant proves the backfill is not silently tenant-scoped."""
    return Tenant.objects.create(name="gh1881m-tenant-2", slug="gh1881m-tenant-2")


def _legacy_issue_workflow_json() -> dict:
    """An Issue definition as materialized before GH-1881.

    Includes the engine-injected lowercase proposal states, the two
    state_meta flags and one admin-authored custom state ("Escalated") that is
    not part of the rename map.
    """
    return {
        "states": list(OLD_STATES),
        "transitions": [
            {
                "from_state": "Open",
                "to_state": "In Progress",
                "allowed_roles": ["editor", "admin"],
                "requires_change_reason": False,
                "signature_gate": False,
            },
            {
                "from_state": "Open",
                "to_state": "Escalated",
                "allowed_roles": ["admin"],
                "requires_change_reason": True,
                "signature_gate": False,
            },
            {
                "from_state": "Resolved",
                "to_state": "Closed",
                "allowed_roles": ["approver", "admin"],
                "requires_change_reason": False,
                "signature_gate": False,
            },
        ],
        "state_meta": {
            "Wontfix": {"is_outdated_equivalent": True},
            "Resolved": {"auto_approve_target": True},
            "Escalated": {"is_outdated_equivalent": False},
        },
        # Unrelated payload key: must survive byte-for-byte.
        "notes": ["keep-me"],
    }


def _risk_workflow_json() -> dict:
    """Risk legitimately keeps Title Case — and shares the literal "Closed"."""
    return {
        "states": ["Identified", "Monitored", "Mitigated", "Accepted", "Closed"],
        "transitions": [
            {
                "from_state": "Identified",
                "to_state": "Closed",
                "allowed_roles": ["admin"],
                "requires_change_reason": True,
                "signature_gate": False,
            }
        ],
        "state_meta": {"Closed": {"is_outdated_equivalent": True}},
    }


def _adr_workflow_json() -> dict:
    return {
        "states": ["Draft", "In Review", "Approved", "Rejected", "Superseded"],
        "transitions": [],
        "state_meta": {"Approved": {"auto_approve_target": True}},
    }


def _seed_legacy_rows(tenant, label="gh1881m") -> dict:
    """Create pre-GH-1881 rows in every storage location plus Risk/Adr controls."""
    with _tenant_scope(tenant.id):
        workspace = Workspace.objects.create(tenant=tenant, name=f"{label}-ws")
        global_def = GlobalWorkflowDefinition.objects.create(
            tenant=tenant,
            item_type="Issue",
            preset="issue_default",
            workflow_json=_legacy_issue_workflow_json(),
        )
        engine_def = WorkflowEngineDefinition.objects.create(
            tenant=tenant,
            workspace=workspace,
            item_type="Issue",
            preset="issue_default",
            workflow_json=_legacy_issue_workflow_json(),
            source_global=global_def,
        )
        # A workspace that diverged from the global default: still must be
        # renamed, otherwise its item states point at names it no longer holds.
        customized_def = WorkflowEngineDefinition.objects.create(
            tenant=tenant,
            workspace=Workspace.objects.create(tenant=tenant, name=f"{label}-ws-c"),
            item_type="Issue",
            preset="issue_default",
            workflow_json=_legacy_issue_workflow_json(),
            is_customized=True,
        )

        issue_state = WorkflowItemState.objects.create(
            tenant=tenant,
            item_id=uuid4(),
            item_type="Issue",
            workspace=workspace,
            definition=engine_def,
            current_state="In Progress",
        )
        history = WorkflowHistoryEntry.objects.create(
            tenant=tenant,
            item_state=issue_state,
            workspace_id=workspace.id,
            from_state="Open",
            to_state="In Progress",
            transitioned_by="reporter",
            transitioned_at=datetime(2026, 11, 16, 9, 0, tzinfo=UTC),
        )
        # Second history row: an injected lowercase state must stay lowercase.
        history_proposed = WorkflowHistoryEntry.objects.create(
            tenant=tenant,
            item_state=issue_state,
            workspace_id=workspace.id,
            from_state="proposed",
            to_state="Open",
            transitioned_by="reporter",
            transitioned_at=datetime(2026, 11, 16, 9, 5, tzinfo=UTC),
        )

        risk_global = GlobalWorkflowDefinition.objects.create(
            tenant=tenant,
            item_type="Risk",
            preset="risk_default",
            workflow_json=_risk_workflow_json(),
        )
        risk_def = WorkflowEngineDefinition.objects.create(
            tenant=tenant,
            workspace=workspace,
            item_type="Risk",
            preset="risk_default",
            workflow_json=_risk_workflow_json(),
            source_global=risk_global,
        )
        risk_state = WorkflowItemState.objects.create(
            tenant=tenant,
            item_id=uuid4(),
            item_type="Risk",
            workspace=workspace,
            definition=risk_def,
            current_state="Closed",
        )
        risk_history = WorkflowHistoryEntry.objects.create(
            tenant=tenant,
            item_state=risk_state,
            workspace_id=workspace.id,
            from_state="Identified",
            to_state="Closed",
            transitioned_by="owner",
            transitioned_at=datetime(2026, 11, 16, 9, 10, tzinfo=UTC),
        )

        adr_global = GlobalWorkflowDefinition.objects.create(
            tenant=tenant,
            item_type="Adr",
            preset="adr_default",
            workflow_json=_adr_workflow_json(),
        )
        adr_def = WorkflowEngineDefinition.objects.create(
            tenant=tenant,
            workspace=workspace,
            item_type="Adr",
            preset="adr_default",
            workflow_json=_adr_workflow_json(),
            source_global=adr_global,
        )
        adr_state = WorkflowItemState.objects.create(
            tenant=tenant,
            item_id=uuid4(),
            item_type="Adr",
            workspace=workspace,
            definition=adr_def,
            current_state="Approved",
        )

    return {
        "global_def": global_def,
        "engine_def": engine_def,
        "customized_def": customized_def,
        "issue_state": issue_state,
        "history": history,
        "history_proposed": history_proposed,
        "risk_global": risk_global,
        "risk_def": risk_def,
        "risk_state": risk_state,
        "risk_history": risk_history,
        "adr_global": adr_global,
        "adr_def": adr_def,
        "adr_state": adr_state,
    }


def _refresh_all(rows) -> None:
    """``refresh_from_db`` goes through the unscoped base manager, so no
    TenantContext is needed here either."""
    for row in rows.values():
        row.refresh_from_db()


# ---------------------------------------------------------------------------
# Forwards
# ---------------------------------------------------------------------------


def test_forwards_rewrites_every_issue_storage_location(tenant) -> None:
    rows = _seed_legacy_rows(tenant)

    migration_forwards(django_apps, None)
    _refresh_all(rows)

    for key in ("global_def", "engine_def", "customized_def"):
        payload = rows[key].workflow_json
        assert payload["states"] == NEW_STATES, key
        assert payload["transitions"][0]["from_state"] == "open", key
        assert payload["transitions"][0]["to_state"] == "in_progress", key
        assert payload["transitions"][2]["from_state"] == "resolved", key
        assert payload["transitions"][2]["to_state"] == "closed", key
        # Admin-authored state is not in the map -> verbatim.
        assert payload["transitions"][1]["to_state"] == "Escalated", key
        # state_meta keys renamed, values and key order preserved.
        assert list(payload["state_meta"]) == ["wontfix", "resolved", "Escalated"], key
        assert payload["state_meta"]["wontfix"] == {"is_outdated_equivalent": True}
        assert payload["state_meta"]["resolved"] == {"auto_approve_target": True}
        # Unrelated keys/structure untouched.
        assert payload["notes"] == ["keep-me"], key
        assert payload["transitions"][0]["allowed_roles"] == ["editor", "admin"], key

    assert rows["issue_state"].current_state == "in_progress"

    assert rows["history"].from_state == "open"
    assert rows["history"].to_state == "in_progress"
    # Already-lowercase history stays untouched.
    assert rows["history_proposed"].from_state == "proposed"
    assert rows["history_proposed"].to_state == "open"


def test_forwards_leaves_other_item_types_alone(tenant) -> None:
    """The whole point of filtering on item_type: Risk shares "Closed",
    Adr shares "Approved"."""
    rows = _seed_legacy_rows(tenant)

    migration_forwards(django_apps, None)
    _refresh_all(rows)

    for key in ("risk_global", "risk_def"):
        assert rows[key].workflow_json["states"] == [
            "Identified",
            "Monitored",
            "Mitigated",
            "Accepted",
            "Closed",
        ], key
        assert rows[key].workflow_json["state_meta"] == {
            "Closed": {"is_outdated_equivalent": True}
        }, key

    assert rows["risk_state"].current_state == "Closed"
    assert rows["risk_history"].to_state == "Closed"

    for key in ("adr_global", "adr_def"):
        assert rows[key].workflow_json["states"] == [
            "Draft",
            "In Review",
            "Approved",
            "Rejected",
            "Superseded",
        ], key

    assert rows["adr_state"].current_state == "Approved"


def test_forwards_is_idempotent(tenant) -> None:
    rows = _seed_legacy_rows(tenant)

    migration_forwards(django_apps, None)
    _refresh_all(rows)
    first_payload = rows["engine_def"].workflow_json

    migration_forwards(django_apps, None)
    _refresh_all(rows)

    assert rows["engine_def"].workflow_json == first_payload
    assert rows["engine_def"].workflow_json["states"] == NEW_STATES
    assert rows["issue_state"].current_state == "in_progress"
    assert rows["history"].from_state == "open"


def test_forwards_is_defensive_about_non_dict_payloads(tenant) -> None:
    """A legacy/hand-edited row whose JSON is not an object must not crash the
    migration — the payload is left exactly as stored."""
    with _tenant_scope(tenant.id):
        broken = GlobalWorkflowDefinition.objects.create(
            tenant=tenant,
            item_type="Issue",
            preset="issue_default",
            workflow_json=[],
        )

    migration_forwards(django_apps, None)
    broken.refresh_from_db()

    assert broken.workflow_json == []


def test_forwards_reaches_every_tenant(tenant, second_tenant) -> None:
    """Multi-tenancy: the backfill must not stop at whichever tenant happened
    to be in the thread-local TenantContext when it ran."""
    rows_a = _seed_legacy_rows(tenant, label="gh1881m-a")
    rows_b = _seed_legacy_rows(second_tenant, label="gh1881m-b")

    # Deliberately no TenantContext at all: an ``objects``-based query would
    # raise (or, worse, match nothing) here.
    assert not TenantContext.is_set()
    migration_forwards(django_apps, None)

    for rows in (rows_a, rows_b):
        _refresh_all(rows)
        assert rows["engine_def"].workflow_json["states"] == NEW_STATES
        assert rows["issue_state"].current_state == "in_progress"


# ---------------------------------------------------------------------------
# Backwards
# ---------------------------------------------------------------------------


def test_backwards_restores_the_previous_spelling(tenant) -> None:
    rows = _seed_legacy_rows(tenant)

    migration_forwards(django_apps, None)
    migration_backwards(django_apps, None)
    _refresh_all(rows)

    for key in ("global_def", "engine_def", "customized_def"):
        payload = rows[key].workflow_json
        assert payload["states"] == OLD_STATES, key
        assert payload["transitions"][0]["from_state"] == "Open", key
        assert payload["transitions"][0]["to_state"] == "In Progress", key
        assert payload["state_meta"] == {
            "Wontfix": {"is_outdated_equivalent": True},
            "Resolved": {"auto_approve_target": True},
            "Escalated": {"is_outdated_equivalent": False},
        }, key

    assert rows["issue_state"].current_state == "In Progress"
    assert rows["history"].from_state == "Open"
    assert rows["history"].to_state == "In Progress"

    # The reverse must not spill over into other item types either.
    for key in ("risk_global", "risk_def", "adr_global", "adr_def"):
        assert "closed" not in rows[key].workflow_json["states"], key
        assert "approved" not in rows[key].workflow_json["states"], key
    assert rows["risk_state"].current_state == "Closed"
    assert rows["adr_state"].current_state == "Approved"
