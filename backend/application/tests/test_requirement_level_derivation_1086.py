"""ADR-005 / #1086 — the level derivation through the real service write paths.

The derivation itself is pinned in
``traceability/tests/test_requirement_level_derived_1086.py``. This module
covers the three *write paths* ADR-005 names, end to end through the services,
plus the two things that must keep working: the export contract and the
``decompose()`` workflow.

Every case here fails on the pre-ADR-005 code, which is the point:

* ``decompose()`` was the only path that touched ``level``;
* a re-parent through ``Artifact.parent_id`` left the whole subtree stale;
* a ``decomposes`` / ``derives-from`` create or delete left it stale;
* ``parent_id`` did not exist on ``update_requirement`` at all.
"""
from __future__ import annotations

import uuid

import pytest

from application.artifact_service import ArtifactService
from application.base import NotFoundError, ValidationError
from application.requirement_service import RequirementService
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import Artifact, Requirement, RequirementLevel, Tenant, User, Workspace
from traceability.types import LinkType

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def env(db):
    from link_types.workspace_store import provision_workspace_link_types
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name="L1086 SVC", slug="l1086-svc", is_active=True)
    user = User.objects.create(
        username="l1086svc", email="l1086svc@t.test", tenant=tenant
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="L1086 SVC WS", preset={"name": "standard"}
        )
        # decompose() and the TraceLink service both validate the link pair
        # against the workspace catalog, so the workspace needs its own rows.
        provision_workspace_link_types(
            workspace_id=workspace.id, tenant_id=tenant.id
        )
        yield {
            "tenant": tenant,
            "workspace": workspace,
            "ctx": AuthContext(
                user_id=user.id,
                tenant_id=tenant.id,
                active_roles=("editor",),
                auth_method=AuthMethod.BEARER_TOKEN,
                api_key_id=None,
                tenant_name=tenant.name,
            ),
        }
    finally:
        TenantContext.clear_tenant()


def _svc() -> RequirementService:
    return RequirementService()


def _create(env, title="Req", parent_id=None):
    return _svc().create_requirement(
        workspace_id=env["workspace"].id, title=title, ctx=env["ctx"], parent_id=parent_id
    )


def _level(env, artifact_id):
    return Requirement.unscoped.get(artifact_id=artifact_id).level


def _level_of(env, requirement_id):
    """Level of a Requirement *entity* id (``DecompositionResultDTO`` carries
    those, not artifact ids)."""
    return Requirement.unscoped.get(id=requirement_id).level


def _chain(env, depth):
    """A root plus ``depth`` descendants, created through the service."""
    root = _create(env, "L0")
    nodes = [root]
    for index in range(1, depth + 1):
        nodes.append(
            _create(env, f"L{index}", parent_id=nodes[-1].artifact_id)
        )
    return nodes


def _assert_invariant(env, context):
    """For every hierarchy edge, child == parent + 1 unless either is NULL."""
    from traceability.audit.hierarchy import (
        HIERARCHY_LINK_TYPES,
        normalise_hierarchy_edge,
    )
    from persistence.models import TraceLink

    rows = {
        row["artifact_id"]: (row["level"], row["artifact__parent_id"])
        for row in Requirement.unscoped.filter(tenant_id=env["tenant"].id).values(
            "artifact_id", "level", "artifact__parent_id"
        )
    }
    edges = {
        (row_parent, artifact_id)
        for artifact_id, (_, row_parent) in rows.items()
        if row_parent in rows
    }
    for source_id, target_id, link_type in TraceLink.unscoped.filter(
        tenant_id=env["tenant"].id, link_type__in=HIERARCHY_LINK_TYPES
    ).values_list("source_id", "target_id", "link_type"):
        normalised = normalise_hierarchy_edge(link_type, source_id, target_id)
        if normalised and normalised[0] in rows and normalised[1] in rows:
            edges.add(normalised)
    for parent_id, child_id in edges:
        parent_level = rows[parent_id][0]
        child_level = rows[child_id][0]
        if parent_level is None or child_level is None:
            continue
        assert child_level == parent_level + 1, (
            f"{context}: {child_id} is L{child_level}, parent {parent_id} is "
            f"L{parent_level}"
        )


# ---------------------------------------------------------------------------
# create_requirement: the derivation runs, the response is truthful
# ---------------------------------------------------------------------------


class TestCreateDerivesTheLevel:
    def test_a_root_is_l1(self, env):
        req = _create(env, "Root")
        assert _level(env, req.artifact_id) == RequirementLevel.L1_SYSTEM

    def test_the_returned_object_carries_the_derived_level(self, env):
        """Response fidelity (#344's class): the derivation writes through a
        bulk UPDATE, so a stale in-memory instance would put ``level: null`` in
        a 201 body for a row whose level is 1."""
        root = _create(env, "Root")
        child = _create(env, "Child", parent_id=root.artifact_id)
        assert child.level == 2

    def test_a_child_is_one_below_its_parent(self, env):
        root = _create(env, "Root")
        child = _create(env, "Child", parent_id=root.artifact_id)
        assert _level(env, child.artifact_id) == RequirementLevel.L2_SUBSYSTEM

    def test_a_deep_chain_is_derived_end_to_end(self, env):
        nodes = _chain(env, 3)
        assert [_level(env, node.artifact_id) for node in nodes] == [1, 2, 3, 4]

    def test_the_service_no_longer_accepts_a_level(self, env):
        """The parameter is gone, not merely ignored — a caller that still
        passes one gets a loud TypeError instead of a silently wrong value."""
        with pytest.raises(TypeError):
            _svc().create_requirement(
                workspace_id=env["workspace"].id,
                title="Req",
                ctx=env["ctx"],
                level=3,
            )


# ---------------------------------------------------------------------------
# decompose() — the path that used to be the only one that worked
# ---------------------------------------------------------------------------


class TestDecompose:
    def test_children_are_derived_not_assigned(self, env):
        root = _create(env, "Root")
        result = _svc().decompose(
            requirement_id=root.id,
            ctx=env["ctx"],
            children=[{"title": "C1"}, {"title": "C2"}],
        )
        assert len(result.children) == 2
        for child in result.children:
            assert _level_of(env, child.id) == RequirementLevel.L2_SUBSYSTEM
        _assert_invariant(env, "after decompose of a root")

    def test_a_second_decomposition_generation_is_derived(self, env):
        root = _create(env, "Root")
        first = _svc().decompose(
            requirement_id=root.id, ctx=env["ctx"], children=[{"title": "C1"}]
        )
        second = _svc().decompose(
            requirement_id=first.children[0].id,
            ctx=env["ctx"],
            children=[{"title": "G1"}],
        )
        assert _level_of(env, second.children[0].id) == RequirementLevel.L3_COMPONENT
        _assert_invariant(env, "after a two-generation decomposition")

    def test_decomposing_a_pre_existing_null_level_parent_derives_the_child(
        self, env
    ):
        """A NULL parent is not a licence to invent a level *out of nothing* —
        but it is not a licence to leave the child NULL either. The parent is a
        root, so the root convention applies and the child is L2."""
        root = _create(env, "Root")
        Requirement.unscoped.filter(artifact_id=root.artifact_id).update(level=None)

        result = _svc().decompose(
            requirement_id=root.id, ctx=env["ctx"], children=[{"title": "C1"}]
        )
        assert _level_of(env, result.children[0].id) == RequirementLevel.L2_SUBSYSTEM


# ---------------------------------------------------------------------------
# The Artifact.parent_id write path
# ---------------------------------------------------------------------------


class TestArtifactParentWritePath:
    def test_a_reparent_reshifts_the_subtree(self, env):
        nodes = _chain(env, 3)
        root, a, b, c = nodes
        assert _level(env, c.artifact_id) == 4

        ArtifactService().update_artifact(
            b.artifact_id, env["ctx"], parent_id=root.artifact_id
        )
        assert _level(env, b.artifact_id) == 2
        assert _level(env, c.artifact_id) == 3
        assert _level(env, a.artifact_id) == 2
        _assert_invariant(env, "after an Artifact.parent_id re-parent")

    def test_a_reparent_of_a_deep_subtree_reaches_every_level(self, env):
        nodes = _chain(env, 3)
        root, _a, _b, leaf = nodes
        ArtifactService().update_artifact(
            leaf.artifact_id, env["ctx"], parent_id=root.artifact_id
        )
        assert _level(env, leaf.artifact_id) == 2

    def test_a_non_requirement_artifact_update_is_untouched(self, env):
        other = Artifact.objects.create(
            tenant=env["tenant"],
            workspace=env["workspace"],
            artifact_type="ArchitectureElement",
        )
        # ``parent_id=None`` is a no-op on update_artifact (unchanged
        # behaviour); the point is that a non-Requirement artifact never
        # reaches the derivation and never has a level to corrupt.
        ArtifactService().update_artifact(
            other.id, env["ctx"], artifact_type="architecture-element"
        )
        assert not Requirement.unscoped.filter(artifact_id=other.id).exists()


# ---------------------------------------------------------------------------
# The update_requirement(parent_id=...) path — the AUC fix
# ---------------------------------------------------------------------------


class TestUpdateParentId:
    def test_parent_id_is_applied(self, env):
        root = _create(env, "Root")
        other = _create(env, "Other")
        child = _create(env, "Child", parent_id=root.artifact_id)

        _svc().update_requirement(
            child.id, env["ctx"], parent_id=other.artifact_id
        )
        assert (
            Requirement.unscoped.get(artifact_id=child.artifact_id).artifact.parent_id
            == other.artifact_id
        )

    def test_the_reparent_reshifts_the_subtree(self, env):
        nodes = _chain(env, 3)
        root, a, b, c = nodes
        other = _create(env, "Other root")

        _svc().update_requirement(b.id, env["ctx"], parent_id=other.artifact_id)
        assert _level(env, b.artifact_id) == 2
        assert _level(env, c.artifact_id) == 3
        assert _level(env, root.artifact_id) == 1
        assert _level(env, a.artifact_id) == 2
        _assert_invariant(env, "after an update_requirement re-parent")

    def test_explicit_null_detaches_to_the_top(self, env):
        root = _create(env, "Root")
        child = _create(env, "Child", parent_id=root.artifact_id)
        _svc().update_requirement(child.id, env["ctx"], parent_id=None)
        assert _level(env, child.artifact_id) == 1
        assert (
            Requirement.unscoped.get(artifact_id=child.artifact_id).artifact.parent_id
            is None
        )

    def test_omitting_parent_id_changes_nothing(self, env):
        root = _create(env, "Root")
        child = _create(env, "Child", parent_id=root.artifact_id)
        _svc().update_requirement(child.id, env["ctx"], title="Renamed")
        stored = Requirement.unscoped.get(artifact_id=child.artifact_id)
        assert stored.artifact.parent_id == root.artifact_id
        assert stored.level == 2

    def test_a_self_reference_is_refused(self, env):
        req = _create(env, "Req")
        with pytest.raises(ValidationError):
            _svc().update_requirement(
                req.id, env["ctx"], parent_id=req.artifact_id
            )

    def test_a_cycle_is_refused(self, env):
        nodes = _chain(env, 2)
        root, a, b = nodes
        with pytest.raises(ValidationError):
            _svc().update_requirement(
                root.id, env["ctx"], parent_id=b.artifact_id
            )
        # The refused re-parent left the hierarchy exactly as it was.
        assert _level(env, root.artifact_id) == 1
        assert _level(env, b.artifact_id) == 3

    def test_an_unknown_parent_is_refused(self, env):
        req = _create(env, "Req")
        with pytest.raises(NotFoundError):
            _svc().update_requirement(
                req.id, env["ctx"], parent_id=uuid.uuid4()
            )

    def test_a_parent_in_another_workspace_is_refused(self, env):
        other_ws = Workspace.objects.create(
            tenant=env["tenant"], name="Other", preset={"name": "standard"}
        )
        other_artifact = Artifact.objects.create(
            tenant=env["tenant"], workspace=other_ws, artifact_type="Requirement"
        )
        Requirement.objects.create(
            tenant=env["tenant"],
            artifact=other_artifact,
            workspace=other_ws,
            title="Theirs",
        )
        req = _create(env, "Mine")
        with pytest.raises(ValidationError):
            _svc().update_requirement(
                req.id, env["ctx"], parent_id=other_artifact.id
            )
        assert _level(env, req.artifact_id) == 1

    def test_the_service_no_longer_accepts_a_level(self, env):
        req = _create(env, "Req")
        with pytest.raises(TypeError):
            _svc().update_requirement(req.id, env["ctx"], level=4)


# ---------------------------------------------------------------------------
# The TraceLink write path, through the manager
# ---------------------------------------------------------------------------


class TestTraceLinkWritePath:
    def _link(self, env, source, target, link_type):
        from traceability import services as trace_services

        return trace_services.create_trace_link(
            source_id=source, target_id=target, link_type=link_type
        )

    def test_creating_a_decomposes_link_derives_the_child(self, env):
        parent = _create(env, "Parent")
        child = _create(env, "Child")
        Requirement.unscoped.filter(artifact_id=child.artifact_id).update(level=None)

        self._link(
            env, parent.artifact_id, child.artifact_id, LinkType.DECOMPOSES.value
        )
        assert _level(env, child.artifact_id) == 2
        _assert_invariant(env, "after a decomposes link")

    def test_creating_a_derives_from_link_derives_the_child(self, env):
        """The inverse spelling is the same edge (issue #395)."""
        parent = _create(env, "Parent")
        child = _create(env, "Child")
        Requirement.unscoped.filter(artifact_id=child.artifact_id).update(level=None)

        self._link(
            env, child.artifact_id, parent.artifact_id, LinkType.DERIVES_FROM.value
        )
        assert _level(env, child.artifact_id) == 2

    def test_deleting_a_link_relevels_the_child_and_its_subtree(self, env):
        parent = _create(env, "Parent")
        child = _create(env, "Child", parent_id=None)
        grandchild = _create(env, "Grandchild", parent_id=child.artifact_id)
        link = self._link(
            env, parent.artifact_id, child.artifact_id, LinkType.DECOMPOSES.value
        )
        assert _level(env, grandchild.artifact_id) == 3

        from traceability import services as trace_services

        trace_services.delete_trace_link(link.id)
        # The child lost its hierarchy parent, so it is the top of its own
        # cascade now and everything below it follows.
        assert _level(env, child.artifact_id) == 1
        assert _level(env, grandchild.artifact_id) == 2
        _assert_invariant(env, "after deleting a decomposes link")

    def test_a_non_hierarchy_link_does_not_derive_anything(self, env):
        parent = _create(env, "Parent")
        child = _create(env, "Child")
        before = (
            _level(env, parent.artifact_id),
            _level(env, child.artifact_id),
        )
        self._link(
            env, parent.artifact_id, child.artifact_id, LinkType.REFERENCES.value
        )
        assert (
            _level(env, parent.artifact_id),
            _level(env, child.artifact_id),
        ) == before

    def test_batch_create_derives_once_for_the_whole_batch(self, env):
        from traceability import services as trace_services

        root = _create(env, "Root")
        mid = _create(env, "Mid")
        leaf = _create(env, "Leaf")
        for node in (mid, leaf):
            Requirement.unscoped.filter(artifact_id=node.artifact_id).update(level=None)

        trace_services.batch_create_trace_links(
            items=[
                {
                    "source_id": root.artifact_id,
                    "target_id": mid.artifact_id,
                    "link_type": LinkType.DECOMPOSES.value,
                },
                {
                    "source_id": mid.artifact_id,
                    "target_id": leaf.artifact_id,
                    "link_type": LinkType.DECOMPOSES.value,
                },
            ]
        )
        assert _level(env, mid.artifact_id) == 2
        assert _level(env, leaf.artifact_id) == 3
        _assert_invariant(env, "after a batch_create of a chain")

    def test_batch_delete_relevels(self, env):
        from traceability import services as trace_services

        root = _create(env, "Root")
        mid = _create(env, "Mid", parent_id=None)
        created = trace_services.batch_create_trace_links(
            items=[
                {
                    "source_id": root.artifact_id,
                    "target_id": mid.artifact_id,
                    "link_type": LinkType.DECOMPOSES.value,
                }
            ]
        )
        assert _level(env, mid.artifact_id) == 2
        trace_services.batch_delete_trace_links([created[0].id])
        assert _level(env, mid.artifact_id) == 1


# ---------------------------------------------------------------------------
# The export contract ADR-005 kept
# ---------------------------------------------------------------------------


class TestExportContractIsUnchanged:
    def test_the_csv_export_still_carries_a_derived_level(self, env):
        """ADR-005 kept the export contract: ``level`` is in
        ``export_service``'s field list and must survive losslessly even though
        it is no longer client-settable — it is still the L4 filter three audit
        rules read, and a consumer that lost it would silently stop seeing L4.
        """
        import csv
        import io

        from application.export_service import ExportService

        root = _create(env, "Root")
        child = _create(env, "Child", parent_id=root.artifact_id)
        assert _level(env, child.artifact_id) == 2

        result = ExportService().export_csv(
            "Requirement", env["workspace"].id, env["ctx"]
        )
        # The export prefixes a ``# terminology_profile:`` comment line, which
        # DictReader would otherwise take for the header.
        body = "\n".join(
            line
            for line in result.content.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
        rows = list(csv.DictReader(io.StringIO(body)))
        exported = {row["title"]: row["level"] for row in rows}
        assert exported == {"Root": "1", "Child": "2"}

    def test_the_bundle_field_list_still_includes_level(self, env):
        """``requirement_bundle_service`` publishes ``level`` as an export
        field. ADR-005 removed the *input* path, not the output one."""
        from application.requirement_bundle_service import REQUIREMENT_ALL_FIELDS

        assert "level" in REQUIREMENT_ALL_FIELDS


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# The back door: a proposed hierarchy link discarded through the agent-safety
# path (ADR-005 completeness)
# ---------------------------------------------------------------------------


class TestDiscardedProposalIsAHierarchyWrite:
    """``TraceLinkService.discard_proposed_link`` deletes the row itself.

    It already holds the instance and performs its own permission checks, so it
    does not route through ``TraceLinkManager.delete()`` -- which is where the
    recompute lives (ADR-005). That made it a *fourth* hierarchy write path that
    silently skipped the derivation, i.e. a way to reintroduce exactly the defect
    ADR-005 removes: after discarding a proposed ``decomposes`` / ``derives-from``
    link, the surviving sub-tree stayed one level too deep.

    The proposal stamping itself (``proposed_at``) is agent-safety behaviour owned
    by the create path and pinned there; these cases exercise the *discard* side
    only, so they stamp it directly rather than re-testing the agent handshake.
    """

    def _chain(self, env):
        """Flat pair. The edge is expressed ONLY by the trace link below.

        Setting ``parent_id`` as well would express the same hierarchy edge twice
        (``Artifact.parent_id`` *and* a normalised TraceLink), which the
        normaliser resolves to an undecided depth -- which is correct behaviour
        and would make this test assert the wrong thing.
        """
        root = _create(env, "Root")
        child = _create(env, "Child")
        return root, child

    def _proposed_link(self, env, source, target, link_type):
        from django.utils import timezone

        from persistence.models import TraceLink
        from traceability import services as trace_services

        link = trace_services.create_trace_link(
            source_id=source.artifact_id,
            target_id=target.artifact_id,
            link_type=link_type,
        )
        TraceLink.objects.filter(pk=link.id).update(proposed_at=timezone.now())
        return TraceLink.objects.get(pk=link.id)

    def test_discarding_a_decomposes_proposal_recomputes_the_subtree(self, env):
        from application.trace_link_service import TraceLinkService

        parent = _create(env, "Parent")
        child = _create(env, "Child")
        # Mirror the proven shape of ``TestTraceLinkWritePath``: NULL the child
        # first so the link is what establishes the depth.
        Requirement.unscoped.filter(artifact_id=child.artifact_id).update(level=None)
        link = self._proposed_link(
            env, parent, child, LinkType.DECOMPOSES.value
        )
        assert _level(env, child.artifact_id) == 2

        TraceLinkService().discard_proposed_link(link.id, ctx=env["ctx"])

        # The hierarchy edge is gone, so the child is a root itself again.
        assert _level(env, child.artifact_id) == 1, (
            "a discarded proposal must not leave a stale level behind"
        )
        _assert_invariant(env, "after discarding a proposed decomposes link")

    def test_discarding_a_non_hierarchy_proposal_leaves_levels_alone(self, env):
        from application.trace_link_service import TraceLinkService

        parent = _create(env, "Parent")
        child = _create(env, "Child", parent_id=parent.artifact_id)
        other = _create(env, "Unrelated")
        link = self._proposed_link(env, parent, other, LinkType.REFERENCES.value)
        before = _level(env, child.artifact_id)

        TraceLinkService().discard_proposed_link(link.id, ctx=env["ctx"])

        assert _level(env, child.artifact_id) == before