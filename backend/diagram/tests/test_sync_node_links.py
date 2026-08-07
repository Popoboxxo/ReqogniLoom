"""
COMP-DS-004 TraceabilityConnector — sync_node_links reconciler tests.

Codeberg #353 Task 4: per-node artifact_ref -> DIAGRAM_REF TraceLink
reconciliation. Covers the brief's full acceptance list:

  - Dedupe: N nodes referencing the same artifact create exactly one
    DIAGRAM_REF TraceLink.
  - Idempotency: re-saving an identical graph creates/deletes nothing.
  - Clearing a node's artifact_ref removes its DIAGRAM_REF link.
  - An unresolvable artifact_ref (nonexistent / cross-tenant) aborts the
    whole save with DiagramValidationError, naming the node, and creates
    zero links.
  - THE single most important test in this task (see class docstring
    below): a pre-existing 'documents' TraceLink survives an unrelated
    node_graph save completely untouched, even when it shares the exact
    same (source, target) pair as a DIAGRAM_REF link being deleted.

Nothing here mocks create_trace_link / TraceLink.objects — every assertion
reads the real DB, through DiagramManager's public create/update_diagram.
"""
from __future__ import annotations

import json
import uuid

import pytest

from diagram.manager import DiagramManager
from diagram.tests.conftest import active_tenant, make_artifact
from diagram.validator import DiagramValidationError
from persistence.models import Requirement, TraceLink
from traceability.types import LinkType

pytestmark = pytest.mark.django_db


@pytest.fixture
def manager() -> DiagramManager:
    return DiagramManager()


# ---------------------------------------------------------------------------
# node_graph payload builders
# ---------------------------------------------------------------------------

def _node(node_id: str, artifact_ref: dict | None = None) -> dict:
    return {
        "id": node_id,
        "type": "box",
        "label": node_id,
        "position": {"x": 0, "y": 0},
        "artifact_ref": artifact_ref,
    }


def _node_graph_content(nodes: list[dict]) -> str:
    return json.dumps({"schema_version": 1, "nodes": nodes, "edges": []})


def _ref(entity_type: str, entity_id: uuid.UUID) -> dict:
    return {"entity_type": entity_type, "id": str(entity_id)}


def _make_requirement(tenant, workspace, title: str = "Req") -> Requirement:
    art = make_artifact(tenant, workspace, artifact_type="Requirement")
    return Requirement.objects.create(tenant=tenant, artifact=art, title=title)


# ---------------------------------------------------------------------------
# Dedupe + idempotency
# ---------------------------------------------------------------------------

class TestSyncNodeLinksDedupeAndIdempotency:
    """Multiple nodes -> one link; re-saving an unchanged graph is a no-op."""

    def test_two_nodes_same_artifact_create_exactly_one_link(
        self, manager, tenant_a, workspace_a
    ) -> None:
        with active_tenant(tenant_a):
            req = _make_requirement(tenant_a, workspace_a)

            content = _node_graph_content(
                [
                    _node("n-1", _ref("Requirement", req.id)),
                    _node("n-2", _ref("Requirement", req.id)),
                ]
            )
            diagram = manager.create_diagram(
                name="Dedupe Diagram",
                diagram_type="block",
                payload_format="node_graph",
                content=content,
                tenant=tenant_a,
                workspace_id=workspace_a.id,
            )

            links = TraceLink.objects.filter(
                link_type=LinkType.DIAGRAM_REF, target_id=req.artifact_id
            )
            assert links.count() == 1
            assert links.first().source_id == diagram.artifact_id

    def test_resaving_identical_graph_is_a_noop(
        self, manager, tenant_a, workspace_a
    ) -> None:
        with active_tenant(tenant_a):
            req = _make_requirement(tenant_a, workspace_a)
            content = _node_graph_content([_node("n-1", _ref("Requirement", req.id))])

            diagram = manager.create_diagram(
                name="Idempotent Diagram",
                diagram_type="block",
                payload_format="node_graph",
                content=content,
                tenant=tenant_a,
                workspace_id=workspace_a.id,
            )

            before_ids = set(
                TraceLink.objects.filter(
                    link_type=LinkType.DIAGRAM_REF
                ).values_list("id", flat=True)
            )
            assert len(before_ids) == 1

            manager.update_diagram(
                diagram_id=diagram.id,
                payload_format="node_graph",
                content=content,
            )

            after_ids = set(
                TraceLink.objects.filter(
                    link_type=LinkType.DIAGRAM_REF
                ).values_list("id", flat=True)
            )
            assert after_ids == before_ids


# ---------------------------------------------------------------------------
# Clearing a ref
# ---------------------------------------------------------------------------

class TestSyncNodeLinksClearingRef:
    def test_clearing_artifact_ref_removes_its_link(
        self, manager, tenant_a, workspace_a
    ) -> None:
        with active_tenant(tenant_a):
            req = _make_requirement(tenant_a, workspace_a)
            content_with_ref = _node_graph_content(
                [_node("n-1", _ref("Requirement", req.id))]
            )
            diagram = manager.create_diagram(
                name="Clearing Diagram",
                diagram_type="block",
                payload_format="node_graph",
                content=content_with_ref,
                tenant=tenant_a,
                workspace_id=workspace_a.id,
            )
            assert (
                TraceLink.objects.filter(link_type=LinkType.DIAGRAM_REF).count() == 1
            )

            content_without_ref = _node_graph_content([_node("n-1", None)])
            manager.update_diagram(
                diagram_id=diagram.id,
                payload_format="node_graph",
                content=content_without_ref,
            )

            assert (
                TraceLink.objects.filter(link_type=LinkType.DIAGRAM_REF).count() == 0
            )


# ---------------------------------------------------------------------------
# Unresolvable refs abort the whole save
# ---------------------------------------------------------------------------

class TestSyncNodeLinksUnresolvableRef:
    def test_nonexistent_artifact_ref_aborts_save_and_creates_zero_links(
        self, manager, tenant_a, workspace_a
    ) -> None:
        with active_tenant(tenant_a):
            ghost_id = uuid.uuid4()
            content = _node_graph_content(
                [_node("n-1", _ref("Requirement", ghost_id))]
            )

            with pytest.raises(DiagramValidationError, match="n-1"):
                manager.create_diagram(
                    name="Ghost Ref Diagram",
                    diagram_type="block",
                    payload_format="node_graph",
                    content=content,
                    tenant=tenant_a,
                    workspace_id=workspace_a.id,
                )

            assert (
                TraceLink.objects.filter(link_type=LinkType.DIAGRAM_REF).count() == 0
            )

    def test_cross_tenant_artifact_ref_aborts_save_and_creates_zero_links(
        self, manager, tenant_a, workspace_a, tenant_b, workspace_b
    ) -> None:
        with active_tenant(tenant_b):
            foreign_req = _make_requirement(tenant_b, workspace_b)

        with active_tenant(tenant_a):
            content = _node_graph_content(
                [_node("n-1", _ref("Requirement", foreign_req.id))]
            )

            with pytest.raises(DiagramValidationError, match="n-1"):
                manager.create_diagram(
                    name="Cross-Tenant Ref Diagram",
                    diagram_type="block",
                    payload_format="node_graph",
                    content=content,
                    tenant=tenant_a,
                    workspace_id=workspace_a.id,
                )

            assert (
                TraceLink.objects.filter(link_type=LinkType.DIAGRAM_REF).count() == 0
            )

        with active_tenant(tenant_b):
            # The foreign-tenant Requirement itself is of course unaffected.
            assert (
                TraceLink.unscoped.filter(
                    link_type=LinkType.DIAGRAM_REF,
                    target_id=foreign_req.artifact_id,
                ).count()
                == 0
            )

    def test_clearing_a_node_that_never_had_a_valid_ref_does_not_require_workspace(
        self, manager, tenant_a
    ) -> None:
        """Back-compat: a node_graph payload with no artifact_ref nodes must
        keep working for workspace-less Diagrams (Task 1's write-path tests
        create these), since sync_node_links must not force shadow-Artifact
        resolution when there is nothing to reconcile.
        """
        with active_tenant(tenant_a):
            content = _node_graph_content([_node("n-1", None)])
            diagram = manager.create_diagram(
                name="Workspace-less Diagram",
                diagram_type="block",
                payload_format="node_graph",
                content=content,
                tenant=tenant_a,
            )
            assert diagram.artifact_id is None
            assert (
                TraceLink.objects.filter(link_type=LinkType.DIAGRAM_REF).count() == 0
            )


# ---------------------------------------------------------------------------
# THE single most important test in Task 4
# ---------------------------------------------------------------------------

class TestSyncNodeLinksProtectsDocumentsLink:
    """Proves the DIAGRAM_REF filter actually protects hand-authored links.

    A hand-authored 'documents' TraceLink and a reconciler-owned DIAGRAM_REF
    TraceLink can legally coexist on the exact same (source, target) pair —
    they differ only by link_type (uq_tracelink_edge is on (source, target,
    link_type), so this is a valid, non-conflicting pair of rows). This test
    proves the reconciler's delete query — hard-filtered to
    link_type=LinkType.DIAGRAM_REF — never reads, creates or deletes the
    'documents' link, even while it correctly deletes the DIAGRAM_REF link on
    that identical pair in response to an unrelated node_graph save (the
    node's artifact_ref being cleared).
    """

    def test_documents_link_survives_unrelated_node_graph_save(
        self, manager, tenant_a, workspace_a
    ) -> None:
        with active_tenant(tenant_a):
            req = _make_requirement(tenant_a, workspace_a)

            # Create the diagram with BOTH a node_graph artifact_ref to `req`
            # (-> DIAGRAM_REF diagram->req) AND an explicit target_id=req
            # (-> hand-authored 'documents' diagram->req): same source, same
            # target, two different link_types on one pair.
            content_with_ref = _node_graph_content(
                [_node("n-1", _ref("Requirement", req.id))]
            )
            diagram = manager.create_diagram(
                name="Shared-Pair Diagram",
                diagram_type="block",
                payload_format="node_graph",
                content=content_with_ref,
                tenant=tenant_a,
                workspace_id=workspace_a.id,
                target_id=req.artifact_id,
            )

            documents_link = TraceLink.objects.get(
                link_type="documents",
                source_id=diagram.artifact_id,
                target_id=req.artifact_id,
            )
            diagram_ref_link = TraceLink.objects.get(
                link_type=LinkType.DIAGRAM_REF,
                source_id=diagram.artifact_id,
                target_id=req.artifact_id,
            )
            assert documents_link.id != diagram_ref_link.id

            # An "unrelated" node_graph save: the node no longer references
            # `req` at all (artifact_ref cleared) -> the DIAGRAM_REF link to
            # `req` must be deleted as no-longer-desired, but the
            # 'documents' link on that exact same pair must survive
            # completely untouched (same row, same id).
            content_cleared = _node_graph_content([_node("n-1", None)])
            manager.update_diagram(
                diagram_id=diagram.id,
                payload_format="node_graph",
                content=content_cleared,
            )

            # DIAGRAM_REF link is gone (no longer desired).
            assert not TraceLink.objects.filter(
                link_type=LinkType.DIAGRAM_REF,
                source_id=diagram.artifact_id,
                target_id=req.artifact_id,
            ).exists()

            # 'documents' link is the exact same row, completely untouched.
            documents_link.refresh_from_db()
            still_there = TraceLink.objects.get(
                link_type="documents",
                source_id=diagram.artifact_id,
                target_id=req.artifact_id,
            )
            assert still_there.id == documents_link.id
            assert (
                TraceLink.objects.filter(
                    link_type="documents",
                    source_id=diagram.artifact_id,
                    target_id=req.artifact_id,
                ).count()
                == 1
            )
