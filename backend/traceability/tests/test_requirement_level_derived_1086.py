"""
ADR-005 — ``Requirement.level`` is derived from the hierarchy (issue #1086).

Two halves, deliberately in this order:

* :class:`TestDeriveRequirementLevels` — the **pure** graph function
  (:func:`traceability.audit.hierarchy.derive_requirement_levels`). It is where
  the two design decisions ADR-005 left open are actually pinned: the root
  convention (a Requirement with no hierarchy parent is ``L1_SYSTEM``) and what
  happens when the graph does not determine a level (NULL, never a guess).
* :class:`TestRecomputeRequirementLevels` — the ORM writer
  (:func:`traceability.audit.hierarchy.recompute_requirement_levels`) reached
  through the real write paths, plus the **property test** that is the point of
  the whole wave: an arbitrary sequence of hierarchy mutations across all three
  paths must leave ``level`` consistent with the graph.

The rule this wave deletes (``CONS-P11``) is asserted gone in
``TestConsP11IsGone`` — a deleted rule must not linger in any tier set, because
a tier that lists an unimplemented rule id promises a check it cannot run.

The service-level write paths (``create_requirement`` with a ``parent_id``,
``update_requirement(parent_id=...)``, ``ArtifactService.update_artifact``,
``TraceLinkManager``) are covered in
``application/tests/test_requirement_level_derivation_1086.py``; here the writer
is driven directly so a failure points at the derivation, not at a caller.
"""
from __future__ import annotations

import contextlib
import random
import uuid

import pytest

from persistence.models import Artifact, Requirement, RequirementLevel, TraceLink
from traceability.audit import RuleEngine
from traceability.audit.hierarchy import (
    CASCADE_TOP_LEVEL,
    ROOT_REQUIREMENT_LEVEL,
    derive_requirement_levels,
    recompute_requirement_levels,
)
from traceability.audit.registry import (
    ARCH_003,
    CONS_P9,
    CONS_P10,
    RULE_PRESET_MAP,
    TRACE_P5,
    VAL_P1,
    VERIF_P8,
    get_registered_rules,
)
from traceability.tests.conftest import active_tenant, make_requirement
from traceability.types import LinkType

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Pure derivation — the two decisions ADR-005 left open
# ---------------------------------------------------------------------------


class TestDeriveRequirementLevels:
    """The root convention, and "no level" instead of a guessed one."""

    def test_a_node_without_a_hierarchy_parent_is_l1(self):
        """Root convention: derived from the seed data, not invented.

        ``seed_full_chain`` gives ``L1_SYSTEM`` to exactly the Requirements
        that derive only from a StakeholderNeed and ``L2_SUBSYSTEM`` to their
        children, and ``root_requirement_ids`` already documents the root as
        the "L1 / SystemRequirement" stand-in. ``L0`` is not available at all:
        StakeholderNeed is a separate model.
        """
        assert ROOT_REQUIREMENT_LEVEL == RequirementLevel.L1_SYSTEM == 1
        assert derive_requirement_levels(set()) == {}
        assert derive_requirement_levels(set(), ["only"]) == {"only": 1}

    def test_a_child_sits_exactly_one_level_below_its_parent(self):
        edges = {("a", "b"), ("b", "c"), ("c", "d")}
        assert derive_requirement_levels(edges) == {
            "a": 1,
            "b": 2,
            "c": 3,
            "d": 4,
        }

    def test_a_child_of_l4_is_not_derivable_rather_than_clamped(self):
        """L4 is the bottom of the cascade; clamping would emit L4-under-L4.

        The pre-ADR-005 ``decompose()`` refused to guess here too ("NULL is the
        honest answer"), so this is preserved behaviour, not a new rule.
        """
        assert CASCADE_TOP_LEVEL == RequirementLevel.L4_PRESENTATION == 4
        edges = {("a", "b"), ("b", "c"), ("c", "d")}
        derived = derive_requirement_levels(edges)
        assert derived == {"a": 1, "b": 2, "c": 3, "d": 4}
        # One more level below the bottom of the cascade: not derivable.
        assert derive_requirement_levels(edges | {("d", "e")})["e"] is None

    def test_a_cycle_yields_no_level_for_any_member(self):
        """Cycle protection. TRACE-P1 checks exactly this, and ``Artifact``
        FK cycles are only rejected on the write path, so rows predating those
        guards (direct ORM writes, imports) can still be cyclic.
        """
        assert derive_requirement_levels({("a", "b"), ("b", "a")}) == {
            "a": None,
            "b": None,
        }

    def test_a_node_below_a_cycle_is_also_not_derivable(self):
        # a <-> b is cyclic, c hangs off b: c's only position depends on b's.
        assert derive_requirement_levels(
            {("a", "b"), ("b", "a"), ("b", "c")}
        ) == {"a": None, "b": None, "c": None}

    def test_a_self_loop_is_a_cycle(self):
        assert derive_requirement_levels({("a", "a")}) == {"a": None}

    def test_converging_parents_at_the_same_level_are_derived(self):
        """A DAG where both parents agree is the common, legal case.

        Two L1 requirements both deriving the same child must not be mistaken
        for a contradiction — they agree on where the child sits.
        """
        assert derive_requirement_levels(
            {("a", "c"), ("b", "c")}, ["a", "b", "c"]
        ) == {"a": 1, "b": 1, "c": 2}

    def test_parents_that_disagree_yield_no_level(self):
        """Any concrete value would be wrong for at least one parent edge.

        ``a`` is a root (L1) and ``d`` is at L2, so ``c`` cannot be both L2 and
        L3. NULL is the honest answer, and it is the conservative one for the
        audit rules: ``level IS NULL`` is never treated as L4, so a NULL row is
        audited at full strength rather than silently exempted.
        """
        edges = {("a", "b"), ("b", "d"), ("a", "c"), ("d", "c")}
        assert derive_requirement_levels(edges)["c"] is None

    def test_a_node_whose_parent_is_unknown_stays_unknown(self):
        # ``u``'s parents disagree, so ``c`` cannot be placed either.
        edges = {("a", "u"), ("b", "d"), ("d", "u"), ("a", "c"), ("u", "c")}
        derived = derive_requirement_levels(edges)
        assert derived["u"] is None
        assert derived["c"] is None

    def test_a_very_deep_chain_does_not_exhaust_the_recursion_limit(self):
        """The derivation is iterative, on purpose.

        A workspace can hold a long derivation chain, and a recursive
        implementation would turn that into a 500 — the same reason
        ``cyclic_hierarchy_nodes`` and ``TraceLinkManager._tarjan_find_cycle``
        are iterative. 1500 levels is well past Python's default limit of 1000.
        """
        depth = 1500
        edges = {(f"n{i}", f"n{i + 1}") for i in range(depth)}
        derived = derive_requirement_levels(edges)
        assert derived["n0"] == 1
        # Everything past L4 is not derivable, but every node is *decided* —
        # no crash, no unresolved entry.
        assert len(derived) == depth + 1
        assert derived[f"n{depth}"] is None


# ---------------------------------------------------------------------------
# ORM writer
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _tenant(tenant):
    """Re-entrant ``active_tenant``.

    ``traceability.tests.conftest.active_tenant`` *clears* the context on exit,
    so nesting it inside an outer ``active_tenant`` block leaves the thread with
    no tenant at all — which the helpers below, called from inside such a block,
    would trip over on their next ORM call.
    """
    from persistence.tenancy import TenantContext, TenantContextNotSetError

    try:
        previous = TenantContext.get_tenant()
    except TenantContextNotSetError:
        previous = None
    TenantContext.set_tenant(tenant.id)
    try:
        yield
    finally:
        if previous is None:
            TenantContext.clear_tenant()
        else:
            TenantContext.set_tenant(previous)


def _levels(tenant) -> dict[uuid.UUID, int | None]:
    """Return ``{artifact_id: level}`` for the tenant's Requirements."""
    with _tenant(tenant):
        return {
            row["artifact_id"]: row["level"]
            for row in Requirement.unscoped.filter(tenant_id=tenant.id).values(
                "artifact_id", "level"
            )
        }


def _union_edges(tenant) -> set[tuple[uuid.UUID, uuid.UUID]]:
    """The union hierarchy the derivation reads: FK tree + normalised links."""
    from traceability.audit.hierarchy import (
        HIERARCHY_LINK_TYPES,
        normalise_hierarchy_edge,
    )

    with _tenant(tenant):
        requirements = {
            row["artifact_id"]
            for row in Requirement.unscoped.filter(tenant_id=tenant.id).values(
                "artifact_id"
            )
        }
        edges = set()
        for row in Requirement.unscoped.filter(tenant_id=tenant.id).values(
            "artifact_id", "artifact__parent_id"
        ):
            if row["artifact__parent_id"] in requirements:
                edges.add((row["artifact__parent_id"], row["artifact_id"]))
        for source_id, target_id, link_type in TraceLink.unscoped.filter(
            tenant_id=tenant.id, link_type__in=HIERARCHY_LINK_TYPES
        ).values_list("source_id", "target_id", "link_type"):
            normalised = normalise_hierarchy_edge(link_type, source_id, target_id)
            if (
                normalised
                and normalised[0] in requirements
                and normalised[1] in requirements
            ):
                edges.add(normalised)
        return edges


def _assert_level_invariant(tenant, context: str) -> None:
    """The invariant the whole wave exists to establish.

    For every hierarchy edge whose *both* endpoints carry a level, the child
    sits exactly one level below the parent. A NULL on either side is not a
    violation: it is the derivation's honest "the graph does not determine a
    level here" answer (cycle, disagreeing parents, child of L4).

    Plus a *coverage* floor, which is what stops this from being vacuously
    green: "both non-null" is trivially true when *nothing* has a level, and
    that is exactly the pre-ADR-005 state (only ``decompose()`` ever wrote the
    field). A run that leaves the corpus essentially NULL has not derived
    anything, however well-formed its NULLs are.
    """
    levels = _levels(tenant)
    for parent_id, child_id in _union_edges(tenant):
        parent_level, child_level = levels.get(parent_id), levels.get(child_id)
        if parent_level is None or child_level is None:
            continue
        assert child_level == parent_level + 1, (
            f"{context}: child {child_id} is L{child_level} but its parent "
            f"{parent_id} is L{parent_level}"
        )
    populated = sum(1 for level in levels.values() if level is not None)
    assert populated >= max(1, len(levels) // 2), (
        f"{context}: only {populated} of {len(levels)} requirements carry a "
        f"derived level — the derivation is not running, so the edge check "
        f"above is vacuous"
    )


def _req(tenant, workspace, title, *, parent_artifact=None, level=None):
    """Create a Requirement at the ORM level and return ``(artifact, req)``.

    ORM level on purpose: these tests drive the derivation itself, so the
    creation must not already have run it.
    """
    artifact = Artifact.objects.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type="Requirement",
        parent_id=parent_artifact.id if parent_artifact is not None else None,
    )
    req = Requirement.objects.create(
        tenant=tenant, artifact=artifact, title=title, level=level
    )
    return artifact, req


def _link(tenant, source, target, link_type):
    return TraceLink.objects.create(
        tenant=tenant, source=source, target=target, link_type=link_type
    )


class TestRecomputeRequirementLevels:
    def test_ignores_artifacts_that_are_not_requirements(
        self, tenant_a, workspace_a
    ):
        """``TraceLinkManager`` passes both endpoints of every hierarchy link and
        lets the writer filter, so a link to an ArchitectureElement (or a
        StakeholderNeed) must cost nothing and change nothing."""
        with active_tenant(tenant_a):
            other = Artifact.objects.create(
                tenant=tenant_a,
                workspace=workspace_a,
                artifact_type="ArchitectureElement",
            )
            requirement, _ = _req(tenant_a, workspace_a, "Root")
            assert recompute_requirement_levels([other.id]) == {}
            recompute_requirement_levels([requirement.id])
            assert recompute_requirement_levels([other.id]) == {}
        assert _levels(tenant_a)[requirement.id] == 1

    def test_derives_a_root_as_l1(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            artifact, _ = _req(tenant_a, workspace_a, "Root")
            changed = recompute_requirement_levels([artifact.id])
        assert changed == {artifact.id: 1}
        assert _levels(tenant_a)[artifact.id] == 1

    def test_derives_from_the_artifact_parent_fk_tree(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            root, _ = _req(tenant_a, workspace_a, "Root")
            child, _ = _req(tenant_a, workspace_a, "Child", parent_artifact=root)
            grandchild, _ = _req(
                tenant_a, workspace_a, "Grandchild", parent_artifact=child
            )
            recompute_requirement_levels([root.id])
        levels = _levels(tenant_a)
        assert (levels[root.id], levels[child.id], levels[grandchild.id]) == (1, 2, 3)

    def test_derives_from_a_decomposes_link(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            parent, _ = _req(tenant_a, workspace_a, "Parent")
            child, _ = _req(tenant_a, workspace_a, "Child")
            _link(tenant_a, parent, child, LinkType.DECOMPOSES.value)
            recompute_requirement_levels([child.id])
        levels = _levels(tenant_a)
        assert (levels[parent.id], levels[child.id]) == (1, 2)

    def test_derives_from_the_inverse_derives_from_spelling(
        self, tenant_a, workspace_a
    ):
        """``child --derives-from--> parent`` is the same edge (#395)."""
        with active_tenant(tenant_a):
            parent, _ = _req(tenant_a, workspace_a, "Parent")
            child, _ = _req(tenant_a, workspace_a, "Child")
            _link(tenant_a, child, parent, LinkType.DERIVES_FROM.value)
            recompute_requirement_levels([child.id])
        levels = _levels(tenant_a)
        assert (levels[parent.id], levels[child.id]) == (1, 2)

    def test_both_spellings_of_one_edge_are_not_a_contradiction(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            parent, _ = _req(tenant_a, workspace_a, "Parent")
            child, _ = _req(tenant_a, workspace_a, "Child")
            _link(tenant_a, parent, child, LinkType.DECOMPOSES.value)
            _link(tenant_a, child, parent, LinkType.DERIVES_FROM.value)
            recompute_requirement_levels([parent.id, child.id])
        levels = _levels(tenant_a)
        assert (levels[parent.id], levels[child.id]) == (1, 2)

    def test_a_multi_level_move_reshifts_the_whole_subtree(
        self, tenant_a, workspace_a
    ):
        """The decision ADR-005 left open: recursive, not single-node.

        Re-parenting the middle of a four-deep chain shifts the moved node and
        everything below it, and the recompute has to reach the whole subtree —
        a single-node write would leave the descendants stale, which is the
        defect in its original form.
        """
        with active_tenant(tenant_a):
            root, _ = _req(tenant_a, workspace_a, "Root")
            a, _ = _req(tenant_a, workspace_a, "A", parent_artifact=root)
            b, _ = _req(tenant_a, workspace_a, "B", parent_artifact=a)
            c, _ = _req(tenant_a, workspace_a, "C", parent_artifact=b)
            recompute_requirement_levels([root.id])
            assert _levels(tenant_a)[c.id] == 4

            Artifact.objects.filter(id=b.id).update(parent_id=root.id)
            recompute_requirement_levels([b.id])

        levels = _levels(tenant_a)
        assert levels[root.id] == 1
        assert levels[a.id] == 2
        # b moved from depth 3 to depth 2, so c follows it up by one.
        assert levels[b.id] == 2
        assert levels[c.id] == 3

    def test_detaching_to_the_top_of_the_cascade(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            root, _ = _req(tenant_a, workspace_a, "Root")
            child, _ = _req(tenant_a, workspace_a, "Child", parent_artifact=root)
            grandchild, _ = _req(
                tenant_a, workspace_a, "Grandchild", parent_artifact=child
            )
            recompute_requirement_levels([root.id])

            Artifact.objects.filter(id=child.id).update(parent_id=None)
            recompute_requirement_levels([child.id])

        levels = _levels(tenant_a)
        assert levels[child.id] == 1
        assert levels[grandchild.id] == 2

    def test_siblings_of_a_moved_node_keep_their_level(self, tenant_a, workspace_a):
        """The recompute scope is ancestors + descendants, so it must not
        gratuitously rewrite a sibling whose parents did not change."""
        with active_tenant(tenant_a):
            root, _ = _req(tenant_a, workspace_a, "Root")
            one, _ = _req(tenant_a, workspace_a, "One", parent_artifact=root)
            two, _ = _req(tenant_a, workspace_a, "Two", parent_artifact=root)
            recompute_requirement_levels([root.id])

            changed = recompute_requirement_levels([two.id])
        assert one.id not in changed
        assert _levels(tenant_a)[one.id] == 2

    def test_a_second_write_is_a_no_op(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            root, _ = _req(tenant_a, workspace_a, "Root")
            child, _ = _req(tenant_a, workspace_a, "Child", parent_artifact=root)
            recompute_requirement_levels([root.id])
            assert recompute_requirement_levels([child.id]) == {}

    def test_cyclic_rows_stay_null_instead_of_getting_a_wrong_value(
        self, tenant_a, workspace_a
    ):
        """A NULL level the graph cannot place must not acquire a plausible-
        looking integer."""
        with active_tenant(tenant_a):
            a, _ = _req(tenant_a, workspace_a, "A")
            b, _ = _req(tenant_a, workspace_a, "B", parent_artifact=a)
            Artifact.objects.filter(id=a.id).update(parent_id=b.id)
            recompute_requirement_levels([a.id, b.id])
        assert set(_levels(tenant_a).values()) == {None}

    def test_going_cyclic_clears_a_level_that_is_no_longer_justified(
        self, tenant_a, workspace_a
    ):
        """The write path *does* overwrite, in both directions.

        A stored level that the (now cyclic) hierarchy no longer justifies is
        set back to NULL rather than kept — a field that keeps a stale value is
        the defect this wave removes. The calibration's ``fill_only`` contract
        is the opposite, and is pinned separately.
        """
        with active_tenant(tenant_a):
            a, _ = _req(tenant_a, workspace_a, "A")
            b, _ = _req(tenant_a, workspace_a, "B", parent_artifact=a)
            recompute_requirement_levels([root := a.id])
            assert _levels(tenant_a)[b.id] == 2

            Artifact.objects.filter(id=a.id).update(parent_id=b.id)
            changed = recompute_requirement_levels([a.id, b.id])
        assert changed == {a.id: None, b.id: None}
        assert set(_levels(tenant_a).values()) == {None}


# ---------------------------------------------------------------------------
# Existing data is protected
# ---------------------------------------------------------------------------


class TestCalibrationProtectsExistingData:
    """``fill_only=True`` — the calibration contract.

    ``Requirement.level`` was never backfilled (migration ``0040``), so the
    pre-ADR-005 corpus is largely NULL and a calibration is the only way it ever
    gets a derived value. Two rules make that safe, and both are load-bearing:

    * it **only fills NULL** — a hand-set value is a human decision the
      derivation cannot reproduce or refute, and ``level == L4`` is the *only*
      L4 filter TRACE-P5, ARCH-003 and VERIF-P8 have, so overwriting it would
      silently switch a rule off;
    * it only ever writes a value the current graph justifies, so a NULL row
      whose hierarchy is cyclic or contradictory stays NULL instead of becoming
      a wrong non-NULL value.

    The write path (``fill_only=False``) deliberately does overwrite — the user
    has just changed the hierarchy, and a field that keeps its old value across
    a re-parent is the defect this wave removes.
    """

    def test_a_preexisting_l4_row_is_not_overwritten(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            root, _ = _req(tenant_a, workspace_a, "Root")
            child, _ = _req(
                tenant_a,
                workspace_a,
                "Hand-set L4",
                parent_artifact=root,
                level=RequirementLevel.L4_PRESENTATION,
            )
            recompute_requirement_levels([root.id], fill_only=True)
        assert _levels(tenant_a)[child.id] == RequirementLevel.L4_PRESENTATION

    def test_a_null_row_is_filled_when_the_graph_justifies_it(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            root, _ = _req(tenant_a, workspace_a, "Root")
            child, _ = _req(tenant_a, workspace_a, "Child", parent_artifact=root)
            changed = recompute_requirement_levels([root.id], fill_only=True)
        assert changed == {root.id: 1, child.id: 2}

    def test_a_null_row_does_not_become_a_wrong_value(self, tenant_a, workspace_a):
        """The riskiest decision in the wave, pinned.

        A NULL level whose hierarchy cannot place it (cyclic here) must stay
        NULL. Filling it with a plausible-looking integer is precisely the
        "derived and read-only, therefore trustworthy" failure the ADR exists
        to prevent. ``changed`` is empty here precisely *because* the rows were
        already NULL and stay NULL.
        """
        with active_tenant(tenant_a):
            a, _ = _req(tenant_a, workspace_a, "A")
            b, _ = _req(tenant_a, workspace_a, "B", parent_artifact=a)
            Artifact.objects.filter(id=a.id).update(parent_id=b.id)
            changed = recompute_requirement_levels([a.id, b.id], fill_only=True)
        assert changed == {}
        assert set(_levels(tenant_a).values()) == {None}

    def test_calibration_leaves_unrelated_rows_alone(
        self, tenant_a, workspace_a, workspace_b
    ):
        """A hand-set row that no hierarchy change reaches keeps its value: the
        calibration only touches the NULLs in the graph it walks."""
        with active_tenant(tenant_a):
            root, _ = _req(tenant_a, workspace_a, "Root")
            hand_set, _ = _req(
                tenant_a,
                workspace_b,
                "Hand-set L3",
                level=RequirementLevel.L3_COMPONENT,
            )
            recompute_requirement_levels([root.id], fill_only=True)
        levels = _levels(tenant_a)
        assert levels[hand_set.id] == RequirementLevel.L3_COMPONENT
        assert levels[root.id] == 1


# ---------------------------------------------------------------------------
# The property test
# ---------------------------------------------------------------------------


class TestLevelIsInvariantUnderArbitraryMutations:
    """The test that pins the original defect.

    An arbitrary, seeded sequence of hierarchy mutations spread over all three
    write paths, with the invariant re-checked after *every* step. Before
    ADR-005, step 2 or 3 of this sequence would have left a ``level`` that
    disagreed with the graph and nothing would have noticed: ``CONS-P11`` could
    not see the ``Artifact.parent_id`` path at all, and nothing checked the
    link paths either.
    """

    _SEED = 1086
    _MUTATIONS = 24

    def test_invariant_holds_after_every_mutation(self, tenant_a, workspace_a):
        from application.artifact_service import ArtifactService
        from application.requirement_service import RequirementService
        from auth_tenancy.context import AuthContext
        from persistence.models import User

        rng = random.Random(self._SEED)
        user = User.objects.create(
            username="lvluser", email="lvl@example.com", tenant=tenant_a
        )
        ctx = AuthContext(
            user_id=user.id,
            tenant_id=tenant_a.id,
            active_roles=("editor",),
            auth_method="test",
            api_key_id=None,
            tenant_name=tenant_a.name,
        )
        requirements = RequirementService()
        artifacts = ArtifactService()
        known: list[uuid.UUID] = []
        applied = 0

        def mutate() -> bool:
            """Apply one random hierarchy mutation. Returns False if refused."""
            nonlocal applied
            choice = rng.choice(
                (
                    "create",
                    "create",
                    "decompose",
                    "reparent_fk",
                    "reparent_req",
                    "link",
                    "unlink",
                )
            )
            if choice in ("create", "decompose") or not known:
                if choice == "decompose" and known:
                    # The one path that wrote ``level`` before ADR-005: kept in
                    # the rotation so a re-parent *after* a decomposition — the
                    # sequence that reproduces the original defect — is covered.
                    from application.requirement_service import RequirementService

                    parent = Requirement.unscoped.get(
                        artifact_id=rng.choice(known)
                    )
                    result = RequirementService().decompose(
                        requirement_id=parent.id,
                        ctx=ctx,
                        children=[{"title": f"D{len(known)}"}],
                    )
                    # ``DecompositionResultDTO`` carries Requirement *entity*
                    # ids; ``known`` holds artifact ids.
                    child = Requirement.unscoped.get(id=result.children[0].id)
                    known.append(child.artifact_id)
                    applied += 1
                    return True
                parent = rng.choice(known) if (known and rng.random() < 0.7) else None
                created = requirements.create_requirement(
                    workspace_id=workspace_a.id,
                    title=f"R{len(known)}",
                    ctx=ctx,
                    parent_id=parent,
                )
                known.append(created.artifact_id)
                applied += 1
                return True
            target = rng.choice(known)
            if choice == "reparent_fk":
                new_parent = rng.choice(known + [None])
                if new_parent == target:
                    return False
                artifacts.update_artifact(target, ctx, parent_id=new_parent)
            elif choice == "reparent_req":
                new_parent = rng.choice(known + [None])
                if new_parent == target:
                    return False
                req = Requirement.unscoped.get(artifact_id=target)
                requirements.update_requirement(req.id, ctx, parent_id=new_parent)
            elif choice == "link":
                pair = (rng.choice(known), rng.choice(known))
                if pair[0] == pair[1]:
                    return False
                from traceability import services as trace_services

                # The write path rejects a cycle or a contradictory pair; skip
                # what it would refuse rather than assert on the rejection —
                # this test is about the invariant, not about the cycle guard.
                trace_services.create_trace_link(
                    source_id=pair[0],
                    target_id=pair[1],
                    link_type=rng.choice(
                        (
                            LinkType.DECOMPOSES.value,
                            LinkType.DERIVES_FROM.value,
                        )
                    ),
                )
            else:  # unlink
                from traceability import services as trace_services

                link = TraceLink.unscoped.filter(
                    tenant_id=tenant_a.id,
                    link_type__in=(
                        LinkType.DECOMPOSES.value,
                        LinkType.DERIVES_FROM.value,
                    ),
                ).first()
                if link is None:
                    return False
                trace_services.delete_trace_link(link.id)
            applied += 1
            return True

        with _tenant(tenant_a):
            for step in range(self._MUTATIONS):
                try:
                    mutate()
                except Exception:  # noqa: BLE001 — a refused mutation
                    # (cycle, self-reference) must leave the invariant intact
                    # all the same, so the failure is absorbed and the
                    # assertion below still runs.
                    pass
                _assert_level_invariant(tenant_a, f"after mutation {step}")
            assert applied >= self._MUTATIONS // 2, (
                "the mutation sequence degenerated into no-ops — the property "
                "test would be vacuously green"
            )
            assert len(known) >= 3


# ---------------------------------------------------------------------------
# What must NOT have happened
# ---------------------------------------------------------------------------


def _findings(result, rule_id):
    return [f for f in result.findings if f.rule_id == rule_id]


def _run(tenant, workspace, tier="extended"):
    return RuleEngine().run(
        tier=tier, workspace_id=str(workspace.id), tenant_id=str(tenant.id)
    )


class TestL4ExceptionsStillApply:
    """``level == L4`` is the only L4 filter TRACE-P5, ARCH-003 and VERIF-P8
    have — ``traceability.audit.hierarchy`` has no L4 concept of its own. That
    is precisely why ADR-005 rejected removing the column: only the *rule* goes.

    Each case is a pair: the same shape at L4 (skipped) and at L2 (reported).
    Without the second half, "no finding" would also pass if the rule had
    stopped looking at ``level`` altogether.
    """

    def test_trace_p5_still_skips_an_l4_decomposition(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            parent, _ = make_requirement(tenant_a, workspace_a, title="Parent Req")
            child_artifact, child = make_requirement(
                tenant_a, workspace_a, title="Child Req"
            )
            child.level = RequirementLevel.L4_PRESENTATION
            child.save(update_fields=["level"])
            _link(tenant_a, parent, child_artifact, LinkType.DECOMPOSES.value)
            # No derives-from back-link: exactly what TRACE-P5 reports — unless
            # the child is L4.
            result = _run(tenant_a, workspace_a)
        assert _findings(result, TRACE_P5) == []

    def test_trace_p5_still_reports_the_same_shape_at_l2(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            parent, _ = make_requirement(tenant_a, workspace_a, title="Parent Req")
            child_artifact, child = make_requirement(
                tenant_a, workspace_a, title="Child Req"
            )
            child.level = RequirementLevel.L2_SUBSYSTEM
            child.save(update_fields=["level"])
            _link(tenant_a, parent, child_artifact, LinkType.DECOMPOSES.value)
            result = _run(tenant_a, workspace_a)
        assert len(_findings(result, TRACE_P5)) == 1

    def test_verif_p8_still_skips_an_l4_leaf(self, tenant_a, workspace_a):
        with active_tenant(tenant_a):
            artifact = Artifact.objects.create(
                tenant=tenant_a,
                workspace=workspace_a,
                artifact_type="Requirement",
            )
            Requirement.objects.create(
                tenant=tenant_a,
                artifact=artifact,
                title="Presentation Req",
                level=RequirementLevel.L4_PRESENTATION,
            )
            result = _run(tenant_a, workspace_a)
        assert _findings(result, VERIF_P8) == []

    def test_verif_p8_still_reports_the_same_shape_at_l1(
        self, tenant_a, workspace_a
    ):
        with active_tenant(tenant_a):
            artifact = Artifact.objects.create(
                tenant=tenant_a,
                workspace=workspace_a,
                artifact_type="Requirement",
            )
            Requirement.objects.create(
                tenant=tenant_a,
                artifact=artifact,
                title="System Req",
                level=RequirementLevel.L1_SYSTEM,
            )
            result = _run(tenant_a, workspace_a)
        assert len(_findings(result, VERIF_P8)) == 1

    def test_arch_003_still_skips_an_l4_allocation(self, tenant_a, workspace_a):
        """ARCH-003 wants a requirement allocated to a child element to derive
        from one allocated to the parent element. An L4 requirement is out of
        scope, so the same shape at L2 is the only reported one."""
        from persistence.models import ArchitectureElement

        def _element(title, parent=None):
            artifact = Artifact.objects.create(
                tenant=tenant_a,
                workspace=workspace_a,
                artifact_type="architecture-element",
            )
            return ArchitectureElement.objects.create(
                tenant=tenant_a, artifact=artifact, title=title, parent=parent
            )

        with active_tenant(tenant_a):
            parent_ae = _element("System")
            child_ae = _element("Sub", parent=parent_ae)
            for title, level, element in (
                ("Parent Req", RequirementLevel.L1_SYSTEM, parent_ae),
                ("Child Req", RequirementLevel.L4_PRESENTATION, child_ae),
            ):
                artifact = Artifact.objects.create(
                    tenant=tenant_a, workspace=workspace_a, artifact_type="Requirement"
                )
                Requirement.objects.create(
                    tenant=tenant_a,
                    artifact=artifact,
                    title=title,
                    level=level,
                )
                _link(
                    tenant_a,
                    artifact,
                    element.artifact,
                    LinkType.ALLOCATED_TO.value,
                )
            # Deliberately no derives-from between the two requirements — that is
            # what ARCH-003 reports, unless the child requirement is L4.
            result = _run(tenant_a, workspace_a)
        assert _findings(result, ARCH_003) == []

    def test_arch_003_still_reports_the_same_shape_at_l2(
        self, tenant_a, workspace_a
    ):
        from persistence.models import ArchitectureElement

        def _element(title, parent=None):
            artifact = Artifact.objects.create(
                tenant=tenant_a,
                workspace=workspace_a,
                artifact_type="architecture-element",
            )
            return ArchitectureElement.objects.create(
                tenant=tenant_a, artifact=artifact, title=title, parent=parent
            )

        with active_tenant(tenant_a):
            parent_ae = _element("System")
            child_ae = _element("Sub", parent=parent_ae)
            for title, level, element in (
                ("Parent Req", RequirementLevel.L1_SYSTEM, parent_ae),
                ("Child Req", RequirementLevel.L2_SUBSYSTEM, child_ae),
            ):
                artifact = Artifact.objects.create(
                    tenant=tenant_a, workspace=workspace_a, artifact_type="Requirement"
                )
                Requirement.objects.create(
                    tenant=tenant_a,
                    artifact=artifact,
                    title=title,
                    level=level,
                )
                _link(
                    tenant_a,
                    artifact,
                    element.artifact,
                    LinkType.ALLOCATED_TO.value,
                )
            # Deliberately no derives-from between the two requirements: that is
            # what ARCH-003 reports, unless the child requirement is L4.
            result = _run(tenant_a, workspace_a)
        assert len(_findings(result, ARCH_003)) == 1


class TestConsP11IsGone:
    def test_the_rule_module_is_gone(self):
        with pytest.raises(ModuleNotFoundError):
            __import__("traceability.audit.rules.level_progression")

    def test_no_rule_registers_under_that_id(self):
        assert "CONS-P11" not in {rule.rule_id for rule in get_registered_rules()}

    def test_no_tier_still_lists_the_id(self):
        """A tier that lists an unimplemented rule id promises a check it
        cannot run — the deleted id must be gone from every set, not merely
        unregistered."""
        for tier, rule_ids in RULE_PRESET_MAP.items():
            assert "CONS-P11" not in rule_ids, tier

    def test_the_other_extended_rules_are_untouched(self):
        """The removal must not have taken a neighbour with it."""
        for rule_id in (TRACE_P5, ARCH_003, VERIF_P8, VAL_P1, CONS_P9, CONS_P10):
            assert rule_id in {
                registered.rule_id for registered in get_registered_rules()
            }, rule_id
