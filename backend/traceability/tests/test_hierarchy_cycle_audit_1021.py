"""Issue #1021 — the SE-Auditor reports a cyclic hierarchy instead of silence.

``root_requirement_ids()`` is a set difference (``requirements - children``),
so a cyclic/contradictory hierarchy makes it return the empty set — and
``SystemRequirementDerivesFromNeedRule`` used to exit through
``if not root_ids: return []``. The gate's most important rule therefore
reported "conformant" for exactly the workspaces whose hierarchy is broken,
which is the failure #1021 is about.

Two things are pinned here:

  * ``hierarchy_cycle_nodes()`` names the artifacts on a cycle (the diagnostic
    the silent ∅ used to hide), and
  * TRACE-P1 emits one dedicated cycle finding **and** still evaluates every
    cycle node against the "must derive from a StakeholderNeed" requirement —
    "the graph is broken" must not be the answer that unlocks a baseline gate.

The cyclic rows are written with ``make_trace_link`` (direct ORM), because the
validated write path now rejects them (see
``test_hierarchy_contradiction_1021.py``). That is the point: imports, direct
ORM writes, data migrations and rows written before the guard all land here.
"""
from __future__ import annotations

import pytest

import traceability.audit.rules.coverage_consistency  # noqa: F401  (registration)
import traceability.audit.rules.trace_derivation_allocation  # noqa: F401  (registration)
from persistence.models import Requirement, StakeholderNeed
from traceability.audit import AuditContext, RuleEngine
from traceability.audit.hierarchy import (
    cyclic_hierarchy_nodes,
    hierarchy_cycle_nodes,
    requirement_hierarchy_edges,
    root_requirement_ids,
)
from traceability.audit.registry import TRACE_P1
from traceability.tests.conftest import active_tenant, make_artifact, make_trace_link

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _requirement(tenant, workspace, title="Req"):
    artifact = make_artifact(tenant, workspace, artifact_type="Requirement")
    Requirement.objects.create(tenant=tenant, artifact=artifact, title=title)
    return artifact


def _need(tenant, workspace, title="Need"):
    artifact = make_artifact(tenant, workspace, artifact_type="StakeholderNeed")
    StakeholderNeed.objects.create(tenant=tenant, artifact=artifact, title=title)
    return artifact


def _context(tenant, workspace) -> AuditContext:
    return AuditContext(
        tier="extended",
        workspace_id=str(workspace.id),
        tenant_id=str(tenant.id),
    )


def _run(tier, workspace, tenant):
    return RuleEngine().run(
        tier=tier, workspace_id=str(workspace.id), tenant_id=str(tenant.id)
    )


def _p1_findings(result):
    return [f for f in result.findings if f.rule_id == TRACE_P1]


def _p1_flagged_ids(result):
    return {
        artifact_id
        for finding in _p1_findings(result)
        for artifact_id in finding.artifact_ids
    }


def _per_node_p1_flagged_ids(result):
    """Ids flagged by a *per-requirement* TRACE-P1 finding.

    The dedicated cycle finding lists every node of the cycle, so it would
    make ``_p1_flagged_ids`` trivially contain all of them. These are the
    single-artifact findings the ordinary P1 check produces.
    """
    return {
        artifact_id
        for finding in _p1_findings(result)
        if len(finding.artifact_ids) == 1
        for artifact_id in finding.artifact_ids
    }


def _cycle_finding(result):
    """The dedicated cycle finding — the multi-artifact TRACE-P1 finding."""
    for finding in _p1_findings(result):
        if len(finding.artifact_ids) > 1:
            return finding
    return None


def _contradictory_pair(tenant, workspace):
    """``a --decomposes--> b`` + ``a --derives-from--> b``, written raw.

    This is the exact #1021 repro. Both edges normalise to opposite directions,
    so both Requirements are each other's ancestor.
    """
    a = _requirement(tenant, workspace, "A")
    b = _requirement(tenant, workspace, "B")
    make_trace_link(a, b, tenant, link_type="decomposes")
    make_trace_link(a, b, tenant, link_type="derives-from")
    return a, b


# ---------------------------------------------------------------------------
# The pure cycle detection
# ---------------------------------------------------------------------------


class TestCyclicHierarchyNodes:
    def test_a_dag_has_no_cyclic_nodes(self):
        assert cyclic_hierarchy_nodes({("a", "b"), ("b", "c")}) == frozenset()

    def test_a_contradictory_pair_is_a_two_cycle(self):
        assert cyclic_hierarchy_nodes({("a", "b"), ("b", "a")}) == frozenset(
            {"a", "b"}
        )

    def test_a_self_loop_counts_as_a_cycle(self):
        assert cyclic_hierarchy_nodes({("a", "a")}) == frozenset({"a"})

    def test_a_longer_cycle_is_found_and_its_tail_is_not(self):
        # a -> b -> c -> a is a cycle; d hangs off it but is not part of it.
        edges = {("a", "b"), ("b", "c"), ("c", "a"), ("c", "d")}
        assert cyclic_hierarchy_nodes(edges) == frozenset({"a", "b", "c"})

    def test_hierarchy_cycle_nodes_reads_the_normalised_graph(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            a, b = _contradictory_pair(tenant_a, workspace_a)
            context = _context(tenant_a, workspace_a)
            requirement_ids = frozenset({str(a.id), str(b.id)})

            # The degraded classification this issue is about: both nodes are
            # children, so the root set is empty ...
            assert root_requirement_ids(context, requirement_ids) == frozenset()
            # ... and the new helper says why.
            assert hierarchy_cycle_nodes(context, requirement_ids) == frozenset(
                {str(a.id), str(b.id)}
            )
            # The union graph really carries both directions.
            assert requirement_hierarchy_edges(context, requirement_ids) == {
                (str(a.id), str(b.id)),
                (str(b.id), str(a.id)),
            }


# ---------------------------------------------------------------------------
# TRACE-P1 on a cyclic hierarchy
# ---------------------------------------------------------------------------


class TestTraceP1OnACycle:
    def test_the_cycle_is_reported_and_every_cycle_node_is_still_checked(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            a, b = _contradictory_pair(tenant_a, workspace_a)
            result = _run("extended", workspace_a, tenant_a)

        cycle = _cycle_finding(result)
        assert cycle is not None, [f.to_dict() for f in _p1_findings(result)]
        assert cycle.severity.value == "blocker"
        assert set(cycle.artifact_ids) == {str(a.id), str(b.id)}
        assert "Cyclic Requirement hierarchy" in cycle.message
        assert "decomposes" in cycle.message and "derives-from" in cycle.message

        # ... and the per-node P1 check ran for both cycle nodes instead of
        # returning ∅ (neither derives from a StakeholderNeed here).
        assert _per_node_p1_flagged_ids(result) == {str(a.id), str(b.id)}
        assert _p1_flagged_ids(result) == {str(a.id), str(b.id)}

    def test_a_cycle_node_that_does_derive_from_a_need_is_not_flagged_twice(
        self, tenant_a, workspace_a
    ):
        """The cycle finding stays; the satisfied node gets no extra finding."""
        with active_tenant(tenant_a):
            need = _need(tenant_a, workspace_a)
            a, b = _contradictory_pair(tenant_a, workspace_a)
            # b is anchored at the Need — only a is missing its anchor.
            make_trace_link(b, need, tenant_a, link_type="derives-from")
            result = _run("extended", workspace_a, tenant_a)

        assert _cycle_finding(result) is not None
        assert _per_node_p1_flagged_ids(result) == {str(a.id)}

    def test_a_cycle_does_not_hide_a_healthy_part_of_the_graph(
        self, tenant_a, workspace_a
    ):
        """A separate, properly anchored root keeps being reported normally."""
        with active_tenant(tenant_a):
            need = _need(tenant_a, workspace_a)
            anchored = _requirement(tenant_a, workspace_a, "Anchored")
            make_trace_link(anchored, need, tenant_a, link_type="derives-from")
            orphan = _requirement(tenant_a, workspace_a, "Orphan Root")
            _contradictory_pair(tenant_a, workspace_a)

            result = _run("extended", workspace_a, tenant_a)

        flagged = _per_node_p1_flagged_ids(result)
        assert str(orphan.id) in flagged
        assert str(anchored.id) not in flagged
        assert _cycle_finding(result) is not None


# ---------------------------------------------------------------------------
# Control case — an acyclic hierarchy is unchanged
# ---------------------------------------------------------------------------


class TestControlCaseWithoutACycle:
    def test_a_derives_from_chain_still_produces_no_cycle_finding(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            need = _need(tenant_a, workspace_a)
            r1 = _requirement(tenant_a, workspace_a, "L1")
            r2 = _requirement(tenant_a, workspace_a, "L2")
            make_trace_link(r1, need, tenant_a, link_type="derives-from")
            make_trace_link(r2, r1, tenant_a, link_type="derives-from")
            result = _run("extended", workspace_a, tenant_a)

        assert _cycle_finding(result) is None
        assert _p1_findings(result) == []

    def test_the_guided_decompose_pair_still_produces_no_cycle_finding(
        self, tenant_a, workspace_a
    ):
        """``parent --decomposes--> child`` + ``child --derives-from--> parent``."""
        with active_tenant(tenant_a):
            need = _need(tenant_a, workspace_a)
            parent = _requirement(tenant_a, workspace_a, "Parent")
            child = _requirement(tenant_a, workspace_a, "Child")
            make_trace_link(parent, need, tenant_a, link_type="derives-from")
            make_trace_link(parent, child, tenant_a, link_type="decomposes")
            make_trace_link(child, parent, tenant_a, link_type="derives-from")
            result = _run("extended", workspace_a, tenant_a)

        assert _cycle_finding(result) is None
        assert _p1_findings(result) == []

    def test_an_unanchored_acyclic_root_is_still_flagged_once(
        self, tenant_a, workspace_a
    ):
        """The rule keeps its teeth: no cycle, one genuine root, one finding."""
        with active_tenant(tenant_a):
            parent = _requirement(tenant_a, workspace_a, "Parent")
            child = _requirement(tenant_a, workspace_a, "Child")
            make_trace_link(child, parent, tenant_a, link_type="derives-from")
            result = _run("extended", workspace_a, tenant_a)

        findings = _p1_findings(result)
        assert len(findings) == 1
        assert findings[0].artifact_ids == (str(parent.id),)
