"""
Issue #395 — the SE-Auditor must recognise a ``derives-from`` hierarchy.

Before the fix, root/leaf classification (TRACE-P1 "root must derive from a
StakeholderNeed", VERIF-P8 "leaf must have a verifying TestCase") only looked
at ``decomposes``/``parent-child`` links. Real workspaces express the
Requirement hierarchy predominantly through ``derives-from``, so every
Requirement in such a hierarchy was classified as root *and* leaf at the same
time — two false BLOCKERs each, and permanently blocked baseline creation.

The chain used throughout: ``need <- r1 <- r2 <- r3`` written with
``derives-from`` links only (``r3 --derives-from--> r2`` etc.). The single
correct classification is r1 = root, r3 = leaf, r2 = neither.

Also covers TRACE-P3: an incoming ``allocated-to`` justifies an
ArchitectureElement just like an outgoing ``satisfies``/``implements``.
"""
from __future__ import annotations

import pytest

import traceability.audit.rules.coverage_consistency  # noqa: F401  (registration)
import traceability.audit.rules.trace_derivation_allocation  # noqa: F401  (registration)
from persistence.models import (
    ArchitectureElement,
    Requirement,
    StakeholderNeed,
)
from traceability.audit import RuleEngine
from traceability.audit.registry import TRACE_P1, TRACE_P1B, TRACE_P3, VERIF_P8
from traceability.tests.conftest import active_tenant, make_artifact, make_trace_link
from traceability.types import LinkType

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _need(tenant, workspace, title="Need"):
    artifact = make_artifact(tenant, workspace, artifact_type="StakeholderNeed")
    StakeholderNeed.objects.create(tenant=tenant, artifact=artifact, title=title)
    return artifact


def _requirement(tenant, workspace, title="Req"):
    artifact = make_artifact(tenant, workspace, artifact_type="Requirement")
    Requirement.objects.create(tenant=tenant, artifact=artifact, title=title)
    return artifact


def _arch_element(tenant, workspace, title="AE"):
    artifact = make_artifact(tenant, workspace, artifact_type="ArchitectureElement")
    ArchitectureElement.objects.create(tenant=tenant, artifact=artifact, title=title)
    return artifact


def _run(tier, workspace, tenant):
    return RuleEngine().run(
        tier=tier, workspace_id=str(workspace.id), tenant_id=str(tenant.id)
    )


def _ids(result, rule_id):
    """Return the set of artifact ids flagged by *rule_id*."""
    return {
        artifact_id
        for finding in result.findings
        if finding.rule_id == rule_id
        for artifact_id in finding.artifact_ids
    }


def _derives_chain(tenant, workspace):
    """Build ``need <- r1 <- r2 <- r3`` using ``derives-from`` links only."""
    need = _need(tenant, workspace)
    r1 = _requirement(tenant, workspace, "L1")
    r2 = _requirement(tenant, workspace, "L2")
    r3 = _requirement(tenant, workspace, "L3")
    make_trace_link(r1, need, tenant, link_type=LinkType.DERIVES_FROM.value)
    make_trace_link(r2, r1, tenant, link_type=LinkType.DERIVES_FROM.value)
    make_trace_link(r3, r2, tenant, link_type=LinkType.DERIVES_FROM.value)
    return need, r1, r2, r3


# ---------------------------------------------------------------------------
# TRACE-P1 — root classification across a derives-from hierarchy
# ---------------------------------------------------------------------------


class TestRootClassificationViaDerivesFrom:
    def test_only_the_top_of_a_derives_from_chain_is_a_root(
        self, tenant_a, workspace_a
    ):
        """r2/r3 are children, so TRACE-P1 must not demand a Need link from them.

        Pre-fix this produced a TRACE-P1 BLOCKER for r2 and r3 (both were
        classified as roots because no ``decomposes`` link existed), even
        though both correctly derive from the level above.
        """
        with active_tenant(tenant_a):
            _need_, r1, r2, r3 = _derives_chain(tenant_a, workspace_a)
            result = _run("extended", workspace_a, tenant_a)

        flagged = _ids(result, TRACE_P1)
        assert str(r2.id) not in flagged
        assert str(r3.id) not in flagged
        # r1 is the one real root and it does derive from the Need.
        assert str(r1.id) not in flagged
        assert flagged == set()

    def test_root_without_need_link_still_blocks(self, tenant_a, workspace_a):
        """The rule keeps its teeth: a genuine root without a Need is flagged."""
        with active_tenant(tenant_a):
            _need(tenant_a, workspace_a)
            r1 = _requirement(tenant_a, workspace_a, "L1")
            r2 = _requirement(tenant_a, workspace_a, "L2")
            make_trace_link(r2, r1, tenant_a, link_type=LinkType.DERIVES_FROM.value)
            result = _run("extended", workspace_a, tenant_a)

        assert _ids(result, TRACE_P1) == {str(r1.id)}

    def test_derives_from_direction_is_not_inverted(self, tenant_a, workspace_a):
        """``derives-from`` points child -> parent, the inverse of ``decomposes``.

        Naively adding ``derives-from`` to the old parent->child link-type set
        would have made the *parent* the child: r1 would be reported as the
        leaf and r2 as the root. This pins the orientation from both ends.
        """
        with active_tenant(tenant_a):
            need = _need(tenant_a, workspace_a)
            r1 = _requirement(tenant_a, workspace_a, "L1")
            r2 = _requirement(tenant_a, workspace_a, "L2")
            make_trace_link(r2, r1, tenant_a, link_type=LinkType.DERIVES_FROM.value)
            # Only r2 is linked to the Need. If the direction were inverted,
            # r2 would count as the root and TRACE-P1 would stay silent while
            # r1 (the true root) escapes the check.
            make_trace_link(r2, need, tenant_a, link_type=LinkType.DERIVES_FROM.value)
            result = _run("extended", workspace_a, tenant_a)

        assert _ids(result, TRACE_P1) == {str(r1.id)}

    def test_requirement_derived_from_a_need_stays_a_root(
        self, tenant_a, workspace_a
    ):
        """A ``Requirement --derives-from--> StakeholderNeed`` edge is not a
        decomposition edge — the Requirement remains the root (L1)."""
        with active_tenant(tenant_a):
            need = _need(tenant_a, workspace_a)
            r1 = _requirement(tenant_a, workspace_a, "L1")
            make_trace_link(r1, need, tenant_a, link_type=LinkType.DERIVES_FROM.value)
            result = _run("extended", workspace_a, tenant_a)

        # No TRACE-P1 finding: r1 is a root and satisfies the rule. And the
        # Need edge must not have made r1 a "child" that skips the check —
        # the negative twin below proves the check still runs for it.
        assert _ids(result, TRACE_P1) == set()
        assert _ids(result, TRACE_P1B) == set()


# ---------------------------------------------------------------------------
# VERIF-P8 — leaf classification across a derives-from hierarchy
# ---------------------------------------------------------------------------


class TestLeafClassificationViaDerivesFrom:
    def test_only_the_bottom_of_a_derives_from_chain_is_a_leaf(
        self, tenant_a, workspace_a
    ):
        """Pre-fix every Requirement was a leaf and VERIF-P8 flagged all three."""
        with active_tenant(tenant_a):
            _need_, r1, r2, r3 = _derives_chain(tenant_a, workspace_a)
            result = _run("extended", workspace_a, tenant_a)

        assert _ids(result, VERIF_P8) == {str(r3.id)}

    def test_decomposes_and_derives_from_agree(self, tenant_a, workspace_a):
        """Both spellings of the same edge classify identically.

        The pair ``parent --decomposes--> child`` + ``child --derives-from-->
        parent`` is what the guided derive flow now writes; it must not make
        a Requirement both parent and child of itself.
        """
        with active_tenant(tenant_a):
            need = _need(tenant_a, workspace_a)
            r1 = _requirement(tenant_a, workspace_a, "L1")
            r2 = _requirement(tenant_a, workspace_a, "L2")
            make_trace_link(r1, need, tenant_a, link_type=LinkType.DERIVES_FROM.value)
            make_trace_link(r1, r2, tenant_a, link_type=LinkType.DECOMPOSES.value)
            make_trace_link(r2, r1, tenant_a, link_type=LinkType.DERIVES_FROM.value)
            result = _run("extended", workspace_a, tenant_a)

        assert _ids(result, TRACE_P1) == set()
        assert _ids(result, VERIF_P8) == {str(r2.id)}


# ---------------------------------------------------------------------------
# TRACE-P3 — allocation justifies an ArchitectureElement
# ---------------------------------------------------------------------------


class TestArchitectureElementJustification:
    def test_incoming_allocation_satisfies_the_rule(self, tenant_a, workspace_a):
        """``Requirement --allocated-to--> element`` is the inverse spelling of
        ``element --satisfies--> Requirement`` and must count.

        The guided derive flow (and ``TraceLinkService.allocate``) only ever
        writes the allocation direction, so pre-fix every element it produced
        was reported as unjustified architecture.
        """
        with active_tenant(tenant_a):
            req = _requirement(tenant_a, workspace_a)
            ae = _arch_element(tenant_a, workspace_a)
            make_trace_link(req, ae, tenant_a, link_type=LinkType.ALLOCATED_TO.value)
            result = _run("extended", workspace_a, tenant_a)

        assert _ids(result, TRACE_P3) == set()

    def test_unlinked_element_still_blocks(self, tenant_a, workspace_a):
        """An element with neither satisfies/implements nor an allocation is
        still untraced architecture and must block."""
        with active_tenant(tenant_a):
            _requirement(tenant_a, workspace_a)
            ae = _arch_element(tenant_a, workspace_a)
            result = _run("extended", workspace_a, tenant_a)

        assert _ids(result, TRACE_P3) == {str(ae.id)}

    def test_satisfies_link_still_satisfies_the_rule(self, tenant_a, workspace_a):
        """The original, outgoing direction keeps working unchanged."""
        with active_tenant(tenant_a):
            req = _requirement(tenant_a, workspace_a)
            ae = _arch_element(tenant_a, workspace_a)
            make_trace_link(ae, req, tenant_a, link_type=LinkType.SATISFIES.value)
            result = _run("extended", workspace_a, tenant_a)

        assert _ids(result, TRACE_P3) == set()
