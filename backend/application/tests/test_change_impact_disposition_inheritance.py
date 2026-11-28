"""Disposition inheritance across runs (S4.5, spec §4.3.6).

A disposition is carried over only when the identifying key is unchanged:
``(artifact_id, severity)`` for a finding and
``(artifact_id, severity, path_hash)`` for a chain. A severity change re-opens
it — otherwise a carried-over waiver would open the gate after a catalog or
weight change.
"""
from __future__ import annotations

import copy

import pytest
from django.utils import timezone

from application.models import ChangeImpactChain, ChangeImpactFinding
from link_types.workspace_store import WorkspaceLinkTypeDefinitionStore

from ._change_impact_engine_helpers import (
    add_affected_item,
    engine_env,
    make_artifact,
    make_link,
)

pytestmark = pytest.mark.django_db


def _blocking_graph(env):
    """root -> verifying test case (coverage-relevant, weight 1.0, hop 1)."""
    root = make_artifact(env, "root")
    test_case = make_artifact(env, "test", artifact_type="TestCase")
    make_link(env, test_case, root, "verifies")
    add_affected_item(env, root)
    return root, test_case


def test_same_severity_and_path_hash_inherit_on_finding_and_chain() -> None:
    with engine_env() as env:
        _blocking_graph(env)
        first = env.engine.analyze(env.cr.id, env.ctx)
        finding = ChangeImpactFinding.objects.get(run=first)
        assert finding.severity == "blocking"
        chain_row = ChangeImpactChain.objects.get(finding=finding)

        decided_at = timezone.now()
        finding.disposition = ChangeImpactFinding.Disposition.ACCEPTED
        finding.decided_by_id = env.ctx.user_id
        finding.decided_at = decided_at
        finding.note = "accepted by CCB"
        finding.save()
        chain_row.disposition = ChangeImpactChain.Disposition.MITIGATED
        chain_row.decided_by_id = env.ctx.user_id
        chain_row.decided_at = decided_at
        chain_row.note = "mitigated"
        chain_row.save()

        second = env.engine.analyze(env.cr.id, env.ctx, force=True)
        assert second.id != first.id

        inherited = ChangeImpactFinding.objects.get(run=second)
        assert inherited.severity == "blocking"
        assert inherited.disposition == "accepted"
        assert inherited.inherited_from_run_id == first.id
        assert inherited.decided_by_id == env.ctx.user_id
        assert inherited.note == "accepted by CCB"

        inherited_chain = ChangeImpactChain.objects.get(finding=inherited)
        assert inherited_chain.path_hash == chain_row.path_hash
        assert inherited_chain.disposition == "mitigated"
        assert inherited_chain.inherited_from_run_id == first.id
        assert inherited_chain.note == "mitigated"


def test_severity_change_re_opens_the_finding() -> None:
    with engine_env() as env:
        _blocking_graph(env)
        first = env.engine.analyze(env.cr.id, env.ctx)
        finding = ChangeImpactFinding.objects.get(run=first)
        assert finding.severity == "blocking"

        finding.disposition = ChangeImpactFinding.Disposition.WAIVED
        finding.note = "waived earlier"
        finding.decided_by_id = env.ctx.user_id
        finding.decided_at = timezone.now()
        finding.save()

        # Drop coverage relevance in the catalog: the same edge is no longer
        # blocking, so the identifying key changes.
        store = WorkspaceLinkTypeDefinitionStore()
        row = store.get(env.tenant.id, env.workspace.id, "verifies")
        definition = copy.deepcopy(row.definition_json)
        definition["coverage_relevant"] = False
        store.update(env.tenant.id, env.workspace.id, "verifies", definition)

        second = env.engine.analyze(env.cr.id, env.ctx, force=True)
        renewed = ChangeImpactFinding.objects.get(run=second)

        assert renewed.severity != "blocking"
        assert renewed.disposition == ChangeImpactFinding.Disposition.OPEN
        assert renewed.inherited_from_run_id is None
        assert renewed.note == ""
        # The chain key includes the severity, so it is open too.
        assert ChangeImpactChain.objects.get(finding=renewed).disposition is None


def test_open_disposition_is_not_marked_as_inherited() -> None:
    with engine_env() as env:
        _blocking_graph(env)
        first = env.engine.analyze(env.cr.id, env.ctx)

        second = env.engine.analyze(env.cr.id, env.ctx, force=True)
        renewed = ChangeImpactFinding.objects.get(run=second)

        assert renewed.disposition == ChangeImpactFinding.Disposition.OPEN
        assert renewed.inherited_from_run_id is None
        assert first.id != second.id


def test_inheritance_uses_the_last_completed_run_only() -> None:
    with engine_env() as env:
        _blocking_graph(env)
        first = env.engine.analyze(env.cr.id, env.ctx)
        finding = ChangeImpactFinding.objects.get(run=first)
        finding.disposition = ChangeImpactFinding.Disposition.REJECTED
        finding.note = "not relevant"
        finding.save()

        second = env.engine.analyze(env.cr.id, env.ctx, force=True)
        third = env.engine.analyze(env.cr.id, env.ctx, force=True)

        newest = ChangeImpactFinding.objects.get(run=third)
        assert newest.disposition == "rejected"
        assert newest.inherited_from_run_id == second.id
