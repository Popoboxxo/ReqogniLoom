"""Issue #1021 — the write path rejects a contradictory hierarchy pair.

``decomposes`` (parent -> child) and ``derives-from`` (child -> parent) are the
two spellings of one hierarchy fact. On the *same* object pair in the *same*
direction they assert opposite parent/child orders: ``a --decomposes--> b``
says b is below a, ``a --derives-from--> b`` says a is below b. Normalised
(see :mod:`traceability.audit.hierarchy`) that is ``(a, b)`` *and* ``(b, a)``,
a 2-cycle in which every involved Requirement is its own ancestor.

Before the fix the write succeeded, ``root_requirement_ids()`` then returned
the empty set, and the SE-Auditor's root/leaf classification silently stopped
reporting for the whole component — TRACE-P1 and VERIF-P8 raised nothing for
exactly the broken hierarchy they exist to catch.

The guard lives in ``TraceLinkManager.create`` — the single choke point behind
the REST ViewSet, the MCP tools and the Layer-2 ``TraceLinkService`` facade —
and runs on the **union** of both link types, because the pre-existing
per-link-type cycle check cannot see a cycle whose two halves carry different
link types (each half is a DAG on its own).
"""
from __future__ import annotations

import pytest

from persistence.models import TraceLink
from traceability.exceptions import (
    ContradictoryHierarchyLinkError,
    CycleDetectedError,
)
from traceability.trace_link_manager import TraceLinkManager
from traceability.tests.conftest import active_tenant, make_artifact

pytestmark = pytest.mark.django_db


@pytest.fixture
def manager() -> TraceLinkManager:
    return TraceLinkManager()


def _requirement(tenant, workspace, title="Req"):
    return make_artifact(tenant, workspace, artifact_type="Requirement")


def _need(tenant, workspace):
    return make_artifact(tenant, workspace, artifact_type="StakeholderNeed")


def _link_count(tenant) -> int:
    return TraceLink.unscoped.filter(tenant_id=tenant.id).count()


# ---------------------------------------------------------------------------
# The contradiction itself
# ---------------------------------------------------------------------------


class TestContradictoryPairIsRejected:
    def test_decomposes_then_contradicting_derives_from_is_rejected(
        self, manager, tenant_a, workspace_a
    ):
        """The exact #1021 repro: ``a --decomposes--> b`` + ``a --derives-from--> b``."""
        with active_tenant(tenant_a):
            a = _requirement(tenant_a, workspace_a, "A")
            b = _requirement(tenant_a, workspace_a, "B")
            manager.create(a.id, b.id, "decomposes")

            with pytest.raises(ContradictoryHierarchyLinkError) as excinfo:
                manager.create(a.id, b.id, "derives-from")

        message = str(excinfo.value)
        # The message has to say *what* is contradictory and *why* — a bare
        # "invalid link" would leave the user guessing which half to remove.
        assert "decomposes" in message
        assert "derives-from" in message
        assert str(a.id) in message
        assert str(b.id) in message

    def test_derives_from_then_contradicting_decomposes_is_rejected(
        self, manager, tenant_a, workspace_a
    ):
        """Creation order is irrelevant: the second half is rejected either way."""
        with active_tenant(tenant_a):
            a = _requirement(tenant_a, workspace_a, "A")
            b = _requirement(tenant_a, workspace_a, "B")
            manager.create(a.id, b.id, "derives-from")

            with pytest.raises(ContradictoryHierarchyLinkError):
                manager.create(a.id, b.id, "decomposes")

    def test_the_rejected_link_is_not_persisted(self, manager, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            a = _requirement(tenant_a, workspace_a, "A")
            b = _requirement(tenant_a, workspace_a, "B")
            manager.create(a.id, b.id, "decomposes")

            with pytest.raises(ContradictoryHierarchyLinkError):
                manager.create(a.id, b.id, "derives-from")

            assert _link_count(tenant_a) == 1

    def test_a_longer_mixed_cycle_is_rejected_too(
        self, manager, tenant_a, workspace_a
    ):
        """Not only the direct pair: the guard walks the whole normalised graph.

        ``a --decomposes--> b --decomposes--> c`` plus ``a --derives-from--> c``
        normalises to ``(a,b), (b,c), (c,a)`` — a 3-cycle. The per-link-type
        check cannot see it (the derives-from graph is still empty).
        """
        with active_tenant(tenant_a):
            a = _requirement(tenant_a, workspace_a, "A")
            b = _requirement(tenant_a, workspace_a, "B")
            c = _requirement(tenant_a, workspace_a, "C")
            manager.create(a.id, b.id, "decomposes")
            manager.create(b.id, c.id, "decomposes")

            with pytest.raises(ContradictoryHierarchyLinkError):
                manager.create(a.id, c.id, "derives-from")


# ---------------------------------------------------------------------------
# The legitimate cases the guard must NOT break
# ---------------------------------------------------------------------------


class TestLegitimateHierarchiesStillWork:
    def test_requirement_derived_from_a_need_is_still_allowed(
        self, manager, tenant_a, workspace_a
    ):
        """``Requirement --derives-from--> StakeholderNeed`` is the L1 anchor."""
        with active_tenant(tenant_a):
            req = _requirement(tenant_a, workspace_a, "L1")
            need = _need(tenant_a, workspace_a)
            link = manager.create(req.id, need.id, "derives-from")

        assert link.link_type == "derives-from"

    def test_the_guided_decompose_pair_is_still_allowed(
        self, manager, tenant_a, workspace_a
    ):
        """``parent --decomposes--> child`` + ``child --derives-from--> parent``.

        Both spellings of the *same* fact — the pair the guided "Ableiten" flow
        and ``RequirementService.decompose()`` write. They normalise to one
        edge ``(parent, child)``, so there is no cycle and the write must pass.
        """
        with active_tenant(tenant_a):
            parent = _requirement(tenant_a, workspace_a, "Parent")
            child = _requirement(tenant_a, workspace_a, "Child")
            manager.create(parent.id, child.id, "decomposes")
            twin = manager.create(child.id, parent.id, "derives-from")

            assert _link_count(tenant_a) == 2
        assert twin.link_type == "derives-from"

    def test_unrelated_hierarchy_pairs_are_unaffected(
        self, manager, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            a = _requirement(tenant_a, workspace_a, "A")
            b = _requirement(tenant_a, workspace_a, "B")
            c = _requirement(tenant_a, workspace_a, "C")
            d = _requirement(tenant_a, workspace_a, "D")
            manager.create(a.id, b.id, "decomposes")
            link = manager.create(c.id, d.id, "derives-from")

        assert link.link_type == "derives-from"

    def test_same_type_cycle_still_raises_cycle_detected(
        self, manager, tenant_a, workspace_a
    ):
        """A genuine same-type cycle keeps its established error (no regression).

        ``a --decomposes--> b`` + ``b --decomposes--> a`` is a real
        ``decomposes`` chain cycle and must stay ``CycleDetectedError`` — the
        new guard runs *after* the existing per-type check for exactly this
        reason.
        """
        with active_tenant(tenant_a):
            a = _requirement(tenant_a, workspace_a, "A")
            b = _requirement(tenant_a, workspace_a, "B")
            manager.create(a.id, b.id, "decomposes")

            with pytest.raises(CycleDetectedError):
                manager.create(b.id, a.id, "decomposes")
