"""SYSTEMAUDIT P1-16 — ``is_outdated_equivalent`` on ``adr_default`` / ``risk_default``.

Two independent things are asserted here:

1. **The presets carry the flag.** ``adr_default``'s "Rejected"/"Superseded"
   and ``risk_default``'s "Closed" are terminal dead-ends and were the only
   ones in ``PRESET_SCHEMAS`` without the marker every sibling preset already
   had. The consumers of the flag (``review.approve``'s gate-target fallback,
   ``AiDerivationService._auto_approve``) must never pick a dead-end as an
   "approval" target.

2. **The flag does NOT leak into visibility.** ``workflow.services
   .outdated_item_ids`` matches the literal universal soft-delete state
   ``"outdated"`` and nothing else, on purpose (see its docstring). The
   regression tests below pin that contract so a future "single source of
   truth" generalisation cannot silently hide every ``deprecated`` /
   ``Rejected`` / ``Closed`` row from the lists that use it.

The first block is pure data — no database. The second and third need one.
"""
from __future__ import annotations

from contextlib import contextmanager
from importlib import import_module
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.apps import apps as django_apps

from workflow.definition_store import PRESET_SCHEMAS, get_state_meta

_mig = import_module("workflow.migrations.0016_seed_adr_risk_outdated_equivalent_flags")
seed_outdated_equivalent_flags = _mig.seed_outdated_equivalent_flags


# ---------------------------------------------------------------------------
# 1. Preset data (no DB)
# ---------------------------------------------------------------------------


def test_adr_default_flags_both_dead_end_states() -> None:
    """"Rejected" (never adopted) and "Superseded" (replaced by a successor)
    are ADR's terminal dead-ends, next to the pre-existing auto-approve
    target."""
    assert PRESET_SCHEMAS["adr_default"]["state_meta"] == {
        "Approved": {"auto_approve_target": True},
        "Rejected": {"is_outdated_equivalent": True},
        "Superseded": {"is_outdated_equivalent": True},
    }


def test_risk_default_flags_closed_but_not_mitigated() -> None:
    """"Closed" is the terminal disposition; "Mitigated" is a genuine steady
    state and must stay reachable by the auto-approve walk."""
    assert PRESET_SCHEMAS["risk_default"]["state_meta"] == {
        "Mitigated": {"auto_approve_target": True},
        "Closed": {"is_outdated_equivalent": True},
    }


@pytest.mark.parametrize(
    "preset,state",
    [
        ("adr_default", "Rejected"),
        ("adr_default", "Superseded"),
        ("risk_default", "Closed"),
    ],
)
def test_flagged_state_is_declared_and_resolves_through_get_state_meta(
    preset: str, state: str
) -> None:
    """A ``state_meta`` key that does not match a declared state name is a
    silent no-op (``get_state_meta`` looks up by name) — the exact trap
    ``test_testcase_default_state_meta_key_was_renamed_too`` guards for
    TestCase."""
    schema = PRESET_SCHEMAS[preset]
    assert state in schema["states"]
    assert get_state_meta(schema, state) == {
        "is_outdated_equivalent": True,
        "auto_approve_target": False,
    }


@pytest.mark.parametrize(
    "preset,state",
    [("adr_default", "Approved"), ("risk_default", "Mitigated")],
)
def test_auto_approve_target_is_never_also_outdated_equivalent(
    preset: str, state: str
) -> None:
    """The two flags are mutually exclusive by meaning: a state cannot be both
    "where automatic approval should land" and "never land here automatically".
    ``_auto_approve`` checks the outdated flag first, so an overlap would make
    the auto-approve target unreachable."""
    meta = get_state_meta(PRESET_SCHEMAS[preset], state)
    assert meta["auto_approve_target"] is True
    assert meta["is_outdated_equivalent"] is False


def _approval_target(preset: str, current_state: str):
    """Reproduce ``ReviewToolGroup._transition_to_gate_target``'s choice.

    Kept as pure preset data on purpose: the selection depends only on
    ``state_meta`` + ``allowed_roles``, which this module owns, and the
    ``mcp_server`` variant needs a database, a workspace and an RBAC context to
    reach the same three lines.
    """
    from workflow.services import is_approval_gate

    schema = PRESET_SCHEMAS[preset]
    available = [
        SimpleNamespace(**t)
        for t in schema["transitions"]
        if t["from_state"] == current_state
    ]
    target = next(
        (
            t.to_state
            for t in available
            if get_state_meta(schema, t.to_state).get("auto_approve_target", False)
        ),
        None,
    )
    if target is None:
        gate = next(
            (
                t
                for t in available
                if is_approval_gate(t)
                and not get_state_meta(schema, t.to_state).get(
                    "is_outdated_equivalent", False
                )
            ),
            None,
        )
        target = gate.to_state if gate is not None else None
    return target


@pytest.mark.parametrize(
    "preset,current_state,expected_target",
    [
        # Unchanged by P1-16 — the explicit auto_approve_target still wins.
        ("adr_default", "Draft", None),
        ("adr_default", "In Review", "Approved"),
        ("risk_default", "Identified", "Accepted"),
        ("risk_default", "Monitored", "Mitigated"),
        # Changed by P1-16. Before the flags, the fallback picked the only
        # approver-gated hop out of these states — so "approve an already
        # approved ADR" silently superseded it, and "approve a mitigated risk"
        # silently closed it. Now there is no approval-shaped target and
        # review.approve answers VALIDATION_ERROR, leaving the decision to an
        # explicit transition call.
        ("adr_default", "Approved", None),
        ("risk_default", "Mitigated", None),
        ("risk_default", "Accepted", None),
        # Already-terminal states never had one.
        ("adr_default", "Rejected", None),
        ("adr_default", "Superseded", None),
        ("risk_default", "Closed", None),
    ],
)
def test_approval_fallback_never_lands_on_a_dead_end(
    preset: str, current_state: str, expected_target
) -> None:
    assert _approval_target(preset, current_state) == expected_target


def test_issue_default_approval_matrix_is_untouched() -> None:
    """Control: GH-370 already tuned ``issue_default`` and P1-16 must not have
    moved it. "Closed" there is a *resolution* of a fixed issue, not a
    dead-end, and stays a legitimate approval target."""
    assert _approval_target("issue_default", "In Progress") == "Resolved"
    assert _approval_target("issue_default", "Resolved") == "Closed"
    assert _approval_target("issue_default", "Open") is None


def test_every_preset_state_meta_key_names_a_declared_state() -> None:
    """Global invariant — cheap guard against a typo in any preset."""
    for preset, schema in PRESET_SCHEMAS.items():
        declared = set(schema["states"])
        for state_name in schema.get("state_meta", {}):
            assert state_name in declared, f"{preset}: {state_name!r} not declared"


def test_adr_and_risk_declare_no_state_literally_named_outdated() -> None:
    """Why ``outdated_item_ids`` can never see these states, and why the fix
    for that is *not* to generalise it: ``"outdated"`` is written by
    ``outdate()`` outside the preset's state list, and Adr/Risk carry their
    soft-delete on the mirrored ``status`` column instead."""
    for preset in ("adr_default", "risk_default"):
        assert "outdated" not in [s.lower() for s in PRESET_SCHEMAS[preset]["states"]]


def test_adr_and_risk_are_status_mirror_types() -> None:
    """Follows from the above: their soft-delete visibility is the
    ``status == "outdated"`` column filter in AdrService/RiskService.list, not
    a WorkflowItemState join."""
    from workflow.lifecycle_manager import _STATUS_MIRROR_MODELS

    assert "Adr" in _STATUS_MIRROR_MODELS
    assert "Risk" in _STATUS_MIRROR_MODELS


# ---------------------------------------------------------------------------
# 2. outdated_item_ids narrow-contract regression (DB)
# ---------------------------------------------------------------------------

@contextmanager
def _tenant_scope(tenant_id):
    from persistence.tenancy import TenantContext

    TenantContext.set_tenant(tenant_id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def p116_tenant(db):
    from persistence.models import Tenant

    return Tenant.objects.create(name="p116-tenant", slug="p116-tenant")


def _make_item_state(tenant, *, item_type, current_state, workspace_id, definition):
    from workflow.models import WorkflowItemState

    return WorkflowItemState.unscoped.create(
        tenant=tenant,
        workspace_id=workspace_id,
        item_id=uuid4(),
        item_type=item_type,
        current_state=current_state,
        definition=definition,
    )


@pytest.fixture
def p116_definition(p116_tenant):
    from workflow.models import WorkflowEngineDefinition

    workspace_id = uuid4()
    with _tenant_scope(p116_tenant.id):
        definition = WorkflowEngineDefinition.objects.create(
            tenant=p116_tenant,
            workspace_id=workspace_id,
            item_type="Adr",
            preset="adr_default",
            workflow_json={
                "states": PRESET_SCHEMAS["adr_default"]["states"],
                "transitions": [],
                "state_meta": PRESET_SCHEMAS["adr_default"]["state_meta"],
            },
        )
    return definition, workspace_id


@pytest.mark.django_db
@pytest.mark.parametrize("dead_end_state", ["Rejected", "Superseded"])
def test_outdated_item_ids_does_not_match_flagged_adr_states(
    p116_tenant, p116_definition, dead_end_state
):
    """Contract pin: marking a state ``is_outdated_equivalent`` must NOT make
    it visible to ``outdated_item_ids``. If this ever starts failing, someone
    generalised the helper — read its docstring before "fixing" this test."""
    from workflow.services import outdated_item_ids

    definition, workspace_id = p116_definition
    with _tenant_scope(p116_tenant.id):
        row = _make_item_state(
            p116_tenant,
            item_type="Adr",
            current_state=dead_end_state,
            workspace_id=workspace_id,
            definition=definition,
        )
        assert row.item_id not in set(
            outdated_item_ids("Adr", tenant_id=p116_tenant.id)
        )


@pytest.mark.django_db
def test_outdated_item_ids_still_matches_the_universal_outdated_state(
    p116_tenant, p116_definition
):
    """The control assertion for the test above — the helper is not simply
    returning nothing."""
    from workflow.services import outdated_item_ids

    definition, workspace_id = p116_definition
    with _tenant_scope(p116_tenant.id):
        row = _make_item_state(
            p116_tenant,
            item_type="Adr",
            current_state="outdated",
            workspace_id=workspace_id,
            definition=definition,
        )
        assert row.item_id in set(outdated_item_ids("Adr", tenant_id=p116_tenant.id))


@pytest.mark.django_db
def test_outdated_item_ids_does_not_match_deprecated_architecture_elements(
    p116_tenant, p116_definition
):
    """The blast radius that makes generalisation unsafe: ArchitectureElement,
    GlossaryTerm, Icd and Diagram all flag ``"deprecated"``, and every caller
    of ``outdated_item_ids`` uses it as an ``.exclude()``. Honouring the flag
    would hide every deprecated element from lists, audit rules, validators and
    the workspace context."""
    from workflow.services import outdated_item_ids

    definition, workspace_id = p116_definition
    with _tenant_scope(p116_tenant.id):
        row = _make_item_state(
            p116_tenant,
            item_type="ArchitectureElement",
            current_state="deprecated",
            workspace_id=workspace_id,
            definition=definition,
        )
        assert row.item_id not in set(
            outdated_item_ids("ArchitectureElement", tenant_id=p116_tenant.id)
        )


# ---------------------------------------------------------------------------
# 3. Data migration 0015 (DB)
# ---------------------------------------------------------------------------


def _adr_workflow_json_without_flags() -> dict:
    return {
        "states": ["Draft", "In Review", "Approved", "Rejected", "Superseded"],
        "transitions": [],
        "state_meta": {"Approved": {"auto_approve_target": True}},
    }


def _risk_workflow_json_without_flags() -> dict:
    return {
        "states": ["Identified", "Monitored", "Mitigated", "Accepted", "Closed"],
        "transitions": [],
        "state_meta": {"Mitigated": {"auto_approve_target": True}},
    }


@pytest.mark.django_db
def test_migration_seeds_adr_dead_end_flags_and_keeps_existing_entries(p116_tenant):
    from workflow.models import GlobalWorkflowDefinition

    with _tenant_scope(p116_tenant.id):
        global_def = GlobalWorkflowDefinition.objects.create(
            tenant=p116_tenant,
            item_type="Adr",
            preset="adr_default",
            workflow_json=_adr_workflow_json_without_flags(),
        )

        seed_outdated_equivalent_flags(django_apps, None)

        global_def.refresh_from_db()
        state_meta = global_def.workflow_json["state_meta"]
        assert state_meta["Rejected"] == {"is_outdated_equivalent": True}
        assert state_meta["Superseded"] == {"is_outdated_equivalent": True}
        # The pre-existing auto_approve_target entry survives the merge.
        assert state_meta["Approved"] == {"auto_approve_target": True}


@pytest.mark.django_db
def test_migration_seeds_risk_closed_flag(p116_tenant):
    from workflow.models import GlobalWorkflowDefinition

    with _tenant_scope(p116_tenant.id):
        global_def = GlobalWorkflowDefinition.objects.create(
            tenant=p116_tenant,
            item_type="Risk",
            preset="risk_default",
            workflow_json=_risk_workflow_json_without_flags(),
        )

        seed_outdated_equivalent_flags(django_apps, None)

        global_def.refresh_from_db()
        assert global_def.workflow_json["state_meta"]["Closed"] == {
            "is_outdated_equivalent": True
        }
        assert global_def.workflow_json["state_meta"]["Mitigated"] == {
            "auto_approve_target": True
        }


@pytest.mark.django_db
def test_migration_propagates_to_non_customized_workspace_definitions(p116_tenant):
    from workflow.models import GlobalWorkflowDefinition, WorkflowEngineDefinition

    with _tenant_scope(p116_tenant.id):
        global_def = GlobalWorkflowDefinition.objects.create(
            tenant=p116_tenant,
            item_type="Adr",
            preset="adr_default",
            workflow_json=_adr_workflow_json_without_flags(),
        )
        non_customized = WorkflowEngineDefinition.objects.create(
            tenant=p116_tenant,
            workspace_id=uuid4(),
            item_type="Adr",
            preset="adr_default",
            workflow_json=_adr_workflow_json_without_flags(),
            source_global=global_def,
            is_customized=False,
        )
        customized = WorkflowEngineDefinition.objects.create(
            tenant=p116_tenant,
            workspace_id=uuid4(),
            item_type="Adr",
            preset="adr_default",
            workflow_json=_adr_workflow_json_without_flags(),
            source_global=global_def,
            is_customized=True,
        )

        seed_outdated_equivalent_flags(django_apps, None)

        non_customized.refresh_from_db()
        customized.refresh_from_db()
        assert (
            non_customized.workflow_json["state_meta"]["Superseded"][
                "is_outdated_equivalent"
            ]
            is True
        )
        # A workspace that already diverged from the global default is left alone.
        assert "Superseded" not in customized.workflow_json.get("state_meta", {})


@pytest.mark.django_db
def test_migration_backfills_orphaned_workspace_rows_with_no_global_link(p116_tenant):
    """Pre-REQ-178 rows (no ``source_global``) are backfilled directly by
    ``preset`` name, same as 0011/0013."""
    from workflow.models import WorkflowEngineDefinition

    with _tenant_scope(p116_tenant.id):
        orphaned = WorkflowEngineDefinition.objects.create(
            tenant=p116_tenant,
            workspace_id=uuid4(),
            item_type="Risk",
            preset="risk_default",
            workflow_json=_risk_workflow_json_without_flags(),
            source_global=None,
            is_customized=False,
        )

        seed_outdated_equivalent_flags(django_apps, None)

        orphaned.refresh_from_db()
        assert (
            orphaned.workflow_json["state_meta"]["Closed"]["is_outdated_equivalent"]
            is True
        )


@pytest.mark.django_db
def test_migration_is_idempotent(p116_tenant):
    from workflow.models import GlobalWorkflowDefinition

    with _tenant_scope(p116_tenant.id):
        global_def = GlobalWorkflowDefinition.objects.create(
            tenant=p116_tenant,
            item_type="Adr",
            preset="adr_default",
            workflow_json=_adr_workflow_json_without_flags(),
        )

        seed_outdated_equivalent_flags(django_apps, None)
        seed_outdated_equivalent_flags(django_apps, None)

        global_def.refresh_from_db()
        assert global_def.workflow_json["state_meta"]["Rejected"] == {
            "is_outdated_equivalent": True
        }


@pytest.mark.django_db
def test_migration_ignores_unrelated_presets(p116_tenant):
    from workflow.models import GlobalWorkflowDefinition

    with _tenant_scope(p116_tenant.id):
        unrelated = GlobalWorkflowDefinition.objects.create(
            tenant=p116_tenant,
            item_type="Issue",
            preset="issue_default",
            workflow_json={
                "states": ["Open", "Closed", "Wontfix"],
                "transitions": [],
                "state_meta": {"Wontfix": {"is_outdated_equivalent": True}},
            },
        )

        seed_outdated_equivalent_flags(django_apps, None)

        unrelated.refresh_from_db()
        # issue_default's "Closed" is a *resolution*, not a dead-end — only
        # "Wontfix" is flagged there, and this migration must not touch it.
        assert "Closed" not in unrelated.workflow_json["state_meta"]
