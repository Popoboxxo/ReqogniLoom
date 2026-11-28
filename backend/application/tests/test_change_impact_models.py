"""Model invariants for the change-impact tables (spec §4.2.3–§4.2.5, REQ-216).

Covers the DB constraints (UNIQUEs, CheckConstraints), the derived
``ChangeImpactFinding.gate_open`` property, cascade behaviour and the
"chain has no own run FK" invariant.

The DB enforces these, not only Python validation, so each violating insert is
expected to raise ``IntegrityError`` — wrapped in a savepoint so the rest of
the test transaction stays usable.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from application.models import (
    ChangeImpactChain,
    ChangeImpactFinding,
    ChangeImpactRun,
    ChangeRequest,
)
from persistence.models import Tenant
from persistence.tests.factories import active_tenant, make_workspace

pytestmark = pytest.mark.django_db

_OPEN = "open"
_ACCEPTED = "accepted"
_BLOCKING = "blocking"
_DET = "deterministic"
_SEMANTIC = "semantic"


@pytest.fixture()
def env():
    """An armed tenant, one workspace and one change request."""
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        cr = ChangeRequest.objects.create(
            tenant=tenant, workspace_id=workspace.id, title="Impact CR"
        )
        yield tenant, workspace, cr


def _run(tenant, cr, workspace, **kwargs) -> ChangeImpactRun:
    defaults = {
        "tenant": tenant,
        "change_request": cr,
        "workspace_id": workspace.id,
        "graph_fingerprint": uuid.uuid4().hex,
    }
    defaults.update(kwargs)
    return ChangeImpactRun.objects.create(**defaults)


def _finding(run, tenant, **kwargs) -> ChangeImpactFinding:
    defaults = {
        "tenant": tenant,
        "run": run,
        "artifact_id": str(uuid.uuid4()),
        "entity_type": "Requirement",
        "hop_distance": 1,
        "weight": Decimal("0.5"),
        "severity": "warning",
        "origin": _DET,
    }
    defaults.update(kwargs)
    return ChangeImpactFinding.objects.create(**defaults)


def _chain(finding, tenant, **kwargs) -> ChangeImpactChain:
    defaults = {
        "tenant": tenant,
        "finding": finding,
        "root_artifact_id": str(uuid.uuid4()),
        "path_hash": uuid.uuid4().hex,
        "path": [{"artifact_id": "a", "link_id": "l"}],
        "hop_distance": 1,
        "weight": Decimal("0.5"),
        "origin": _DET,
    }
    defaults.update(kwargs)
    return ChangeImpactChain.objects.create(**defaults)


def _rejected(build) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        build()


# ---------------------------------------------------------------------------
# Defaults / Bestandszeilen
# ---------------------------------------------------------------------------


def test_new_models_have_documented_defaults(env):
    tenant, workspace, cr = env
    run = _run(tenant, cr, workspace)
    assert run.status == "pending"
    assert run.trigger == "manual"
    assert run.algorithm_version == "v1"
    assert run.roots_source == "change_set"
    assert run.gate_eligible is False
    assert run.forced is False
    assert run.pinned is False
    assert run.include_semantic is False
    assert run.node_count == run.edge_count == run.path_count == 0
    assert run.root_item_ids == []
    assert run.visited_node_ids == []

    finding = _finding(run, tenant)
    assert finding.disposition == _OPEN
    assert finding.chain_count == 0
    assert finding.via_link_types == []
    assert finding.gate_open is True

    chain = _chain(finding, tenant)
    assert chain.disposition is None
    assert chain.via_link_types == []


def test_change_request_existing_row_defaults_are_safe(env):
    _tenant, _workspace, cr = env
    cr.refresh_from_db()
    assert cr.impact_source == "none"
    assert cr.impact_summary == ""
    assert cr.impact_override_reason == ""
    assert cr.impact_truncation_waiver_reason == ""
    assert cr.summary_run_id is None
    assert cr.truncation_waiver_by_id is None


def test_affected_item_existing_row_defaults_are_safe(env):
    tenant, _workspace, cr = env
    item = cr.affected_items.create(
        tenant=tenant, item_id=str(uuid.uuid4())
    )
    item.refresh_from_db()
    assert item.change_action == "modify"
    assert item.origin == "manual"
    assert item.rationale == ""
    assert item.removed_reason == ""


# ---------------------------------------------------------------------------
# UNIQUE constraints
# ---------------------------------------------------------------------------


def test_finding_unique_run_artifact(env):
    tenant, workspace, cr = env
    run = _run(tenant, cr, workspace)
    artifact_id = str(uuid.uuid4())
    _finding(run, tenant, artifact_id=artifact_id)
    _rejected(lambda: _finding(run, tenant, artifact_id=artifact_id))


def test_chain_unique_finding_path_hash(env):
    tenant, workspace, cr = env
    run = _run(tenant, cr, workspace)
    finding = _finding(run, tenant)
    path_hash = uuid.uuid4().hex
    _chain(finding, tenant, path_hash=path_hash)
    _rejected(lambda: _chain(finding, tenant, path_hash=path_hash))


def test_run_partial_unique_blocks_duplicate_fingerprint(env):
    tenant, workspace, cr = env
    fingerprint = uuid.uuid4().hex
    _run(tenant, cr, workspace, graph_fingerprint=fingerprint)
    _rejected(
        lambda: _run(tenant, cr, workspace, graph_fingerprint=fingerprint)
    )


def test_run_partial_unique_exempts_forced_and_failed(env):
    tenant, workspace, cr = env
    fingerprint = uuid.uuid4().hex
    _run(tenant, cr, workspace, graph_fingerprint=fingerprint)
    # forced=True is outside the partial unique's predicate.
    _run(tenant, cr, workspace, graph_fingerprint=fingerprint, forced=True)
    # a failed run never blocks a retry.
    _run(tenant, cr, workspace, graph_fingerprint=fingerprint, status="failed")


# ---------------------------------------------------------------------------
# CheckConstraints — run
# ---------------------------------------------------------------------------


def test_run_status_check(env):
    tenant, workspace, cr = env
    _rejected(lambda: _run(tenant, cr, workspace, status="bogus"))


def test_run_trigger_check(env):
    tenant, workspace, cr = env
    _rejected(lambda: _run(tenant, cr, workspace, trigger="bogus"))


def test_run_gate_eligible_requires_change_set_roots(env):
    tenant, workspace, cr = env
    _rejected(
        lambda: _run(
            tenant, cr, workspace, gate_eligible=True, roots_source="explicit"
        )
    )
    allowed = _run(
        tenant, cr, workspace, gate_eligible=True, roots_source="change_set"
    )
    assert allowed.gate_eligible is True


def test_run_completed_requires_finished_at(env):
    tenant, workspace, cr = env
    _rejected(lambda: _run(tenant, cr, workspace, status="completed"))
    allowed = _run(
        tenant, cr, workspace, status="completed", finished_at="2026-11-28T10:00:00Z"
    )
    assert allowed.finished_at is not None


# ---------------------------------------------------------------------------
# CheckConstraints — finding
# ---------------------------------------------------------------------------


def test_finding_severity_and_origin_checks(env):
    tenant, workspace, cr = env
    run = _run(tenant, cr, workspace)
    _rejected(lambda: _finding(run, tenant, severity="bogus"))
    _rejected(lambda: _finding(run, tenant, origin="llm"))


def test_finding_disposition_check(env):
    tenant, workspace, cr = env
    run = _run(tenant, cr, workspace)
    _rejected(lambda: _finding(run, tenant, disposition="bogus"))


def test_finding_weight_range(env):
    tenant, workspace, cr = env
    run = _run(tenant, cr, workspace)
    _rejected(lambda: _finding(run, tenant, weight=Decimal("1.5")))
    _rejected(lambda: _finding(run, tenant, weight=Decimal("-0.1")))
    accepted = _finding(run, tenant, weight=Decimal("1.0000"))
    assert accepted.weight == Decimal("1.0000")


def test_finding_hop_distance_nonnegative(env):
    tenant, workspace, cr = env
    run = _run(tenant, cr, workspace)
    _rejected(lambda: _finding(run, tenant, hop_distance=-1))


def test_finding_chain_count_max(env):
    tenant, workspace, cr = env
    run = _run(tenant, cr, workspace)
    _rejected(lambda: _finding(run, tenant, chain_count=4))


def test_finding_note_required_for_closed_dispositions(env):
    tenant, workspace, cr = env
    run = _run(tenant, cr, workspace)
    for disposition in ("mitigated", "waived", "rejected"):
        _rejected(lambda d=disposition: _finding(run, tenant, disposition=d))
    accepted = _finding(
        run, tenant, disposition="waived", note="accepted risk"
    )
    assert accepted.disposition == "waived"


def test_semantic_finding_can_never_be_blocking(env):
    tenant, workspace, cr = env
    run = _run(tenant, cr, workspace)
    _rejected(
        lambda: _finding(
            run, tenant, origin=_SEMANTIC, severity=_BLOCKING
        )
    )
    allowed = _finding(run, tenant, origin=_SEMANTIC, severity="warning")
    assert allowed.severity == "warning"


# ---------------------------------------------------------------------------
# CheckConstraints — chain
# ---------------------------------------------------------------------------


def test_chain_origin_check(env):
    tenant, workspace, cr = env
    run = _run(tenant, cr, workspace)
    finding = _finding(run, tenant)
    _rejected(lambda: _chain(finding, tenant, origin="llm"))


def test_chain_hop_distance_range(env):
    tenant, workspace, cr = env
    run = _run(tenant, cr, workspace)
    finding = _finding(run, tenant)
    _rejected(lambda: _chain(finding, tenant, hop_distance=0, path=[]))
    _rejected(
        lambda: _chain(
            finding,
            tenant,
            hop_distance=7,
            path=[{} for _ in range(7)],
        )
    )


def test_chain_path_length_must_equal_hop_distance(env):
    tenant, workspace, cr = env
    run = _run(tenant, cr, workspace)
    finding = _finding(run, tenant)
    _rejected(
        lambda: _chain(finding, tenant, hop_distance=1, path=[{"a": 1}, {"b": 2}])
    )
    accepted = _chain(
        finding, tenant, hop_distance=2, path=[{"a": 1}, {"b": 2}]
    )
    assert len(accepted.path) == accepted.hop_distance


def test_chain_weight_range(env):
    tenant, workspace, cr = env
    run = _run(tenant, cr, workspace)
    finding = _finding(run, tenant)
    _rejected(lambda: _chain(finding, tenant, weight=Decimal("2.0")))


def test_chain_note_required_for_closed_dispositions(env):
    tenant, workspace, cr = env
    run = _run(tenant, cr, workspace)
    finding = _finding(run, tenant)
    _rejected(
        lambda: _chain(finding, tenant, disposition="waived")
    )
    accepted = _chain(
        finding, tenant, disposition="accepted", note="ok"
    )
    assert accepted.disposition == "accepted"


def test_chain_has_no_own_run_fk():
    field_names = {field.name for field in ChangeImpactChain._meta.get_fields()}
    assert "run" not in field_names
    assert "finding" in field_names


# ---------------------------------------------------------------------------
# ChangeRequest hybrid-override constraint
# ---------------------------------------------------------------------------


def test_hybrid_impact_source_requires_override_reason(env):
    _tenant, _workspace, cr = env
    cr.impact_source = "hybrid"
    cr.impact_override_reason = ""
    _rejected(cr.save)

    cr.impact_override_reason = "human addendum"
    cr.save()
    cr.refresh_from_db()
    assert cr.impact_source == "hybrid"


# ---------------------------------------------------------------------------
# gate_open property (spec §4.2.5)
# ---------------------------------------------------------------------------


def test_gate_open_without_chains_follows_finding_disposition(env):
    tenant, workspace, cr = env
    run = _run(tenant, cr, workspace)
    open_finding = _finding(run, tenant)
    assert open_finding.gate_open is True

    closed_finding = _finding(run, tenant, disposition=_ACCEPTED)
    assert closed_finding.gate_open is False


def test_gate_open_chain_override_wins(env):
    tenant, workspace, cr = env
    run = _run(tenant, cr, workspace)
    finding = _finding(run, tenant)  # finding disposition = open
    _chain(finding, tenant, disposition=_ACCEPTED)
    assert ChangeImpactFinding.objects.get(pk=finding.pk).gate_open is False


def test_gate_open_any_open_chain_keeps_finding_open(env):
    tenant, workspace, cr = env
    run = _run(tenant, cr, workspace)
    finding = _finding(run, tenant, disposition=_ACCEPTED)
    _chain(finding, tenant, disposition="open")
    _chain(finding, tenant, disposition=_ACCEPTED)
    assert ChangeImpactFinding.objects.get(pk=finding.pk).gate_open is True


def test_gate_open_null_chain_inherits_finding_disposition(env):
    tenant, workspace, cr = env
    run = _run(tenant, cr, workspace)

    finding_open = _finding(run, tenant, disposition=_OPEN)
    _chain(finding_open, tenant, disposition=None)
    assert ChangeImpactFinding.objects.get(pk=finding_open.pk).gate_open is True

    finding_closed = _finding(run, tenant, disposition=_ACCEPTED)
    _chain(finding_closed, tenant, disposition=None)
    assert ChangeImpactFinding.objects.get(pk=finding_closed.pk).gate_open is False


# ---------------------------------------------------------------------------
# Cascade behaviour
# ---------------------------------------------------------------------------


def test_deleting_run_cascades_findings_and_chains(env):
    tenant, workspace, cr = env
    run = _run(tenant, cr, workspace)
    finding = _finding(run, tenant)
    _chain(finding, tenant)

    run.delete()

    assert ChangeImpactFinding.objects.filter(run_id=run.id).count() == 0
    assert ChangeImpactChain.objects.filter(finding_id=finding.id).count() == 0


def test_deleting_change_request_cascades_runs(env):
    tenant, workspace, cr = env
    run = _run(tenant, cr, workspace)
    cr.delete()
    assert ChangeImpactRun.objects.filter(pk=run.pk).count() == 0


# ---------------------------------------------------------------------------
# Re-export / ownership
# ---------------------------------------------------------------------------


def test_models_are_owned_by_persistence_and_reexported():
    from django.apps import apps

    from application import models as application_models

    for name in ("ChangeImpactRun", "ChangeImpactFinding", "ChangeImpactChain"):
        assert apps.get_model("persistence", name)._meta.app_label == "persistence"
        assert getattr(application_models, name) is apps.get_model(
            "persistence", name
        )


def test_tenant_scoped_models_are_tenant_managed(env):
    tenant, workspace, cr = env
    run = _run(tenant, cr, workspace)
    other = Tenant.objects.create(name="other", slug="other-tenant")
    # The default manager is tenant-filtered; unscoped sees both.
    assert ChangeImpactRun.objects.filter(pk=run.pk).count() == 1
    assert ChangeImpactRun.unscoped.filter(pk=run.pk, tenant_id=tenant.id).count() == 1
    assert ChangeImpactRun.unscoped.filter(pk=run.pk, tenant_id=other.id).count() == 0
