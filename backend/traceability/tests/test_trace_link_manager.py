"""
COMP-TE-001 TraceLinkManager — CRUD, validation, cycle detection, batch tests.

Covers:
  REQ-L2-TE-001: TraceLink CRUD with 8 link types
  REQ-L2-TE-002: Eager cycle detection for single links
  REQ-L2-TE-003: Atomic batch operations with Tarjan cycle check
  REQ-L2-TE-009: Referential integrity (CASCADE)
  REQ-L2-TE-010: Audit metadata
  REQ-L2-TE-011: Tenant isolation
"""
from __future__ import annotations

import uuid

import pytest

from persistence.models import TraceLink
from traceability.exceptions import (
    CrossTenantLinkError,
    CycleDetectedError,
    InvalidLinkTypeError,
    SourceNotFoundError,
    TargetNotFoundError,
)
from traceability.trace_link_manager import TraceLinkManager
from traceability.tests.conftest import (
    active_tenant,
    make_artifact,
    make_requirement,
    make_trace_link,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def manager() -> TraceLinkManager:
    return TraceLinkManager()


# ---------------------------------------------------------------------------
# REQ-L2-TE-001: TraceLink CRUD with 8 link types
# ---------------------------------------------------------------------------

class TestTraceLinkCRUD:
    """REQ-L2-TE-001: Basic CRUD with validation."""

    def test_create_valid_link(self, manager, tenant_a, workspace_a):
        """Create TraceLink with valid type returns persisted link with UUID."""
        with active_tenant(tenant_a):
            src_art, _ = make_requirement(tenant_a, workspace_a, "Req-A")
            tgt_art = make_artifact(tenant_a, workspace_a, "architecture_element")

            link = manager.create(
                source_id=src_art.id,
                target_id=tgt_art.id,
                link_type="satisfies",
            )

        assert link.id is not None
        assert isinstance(link.id, uuid.UUID)
        assert link.link_type == "satisfies"
        assert link.source_id == src_art.id
        assert link.target_id == tgt_art.id

    def test_create_all_8_link_types(self, manager, tenant_a, workspace_a):
        """REQ-L2-TE-001: All 8 link types are accepted."""
        valid_types = [
            "parent-child", "derives-from", "satisfies", "verifies",
            "implements", "refines", "documents", "realizes",
        ]
        with active_tenant(tenant_a):
            for lt in valid_types:
                src = make_artifact(tenant_a, workspace_a, "requirement")
                tgt = make_artifact(tenant_a, workspace_a, "requirement")
                link = manager.create(
                    source_id=src.id,
                    target_id=tgt.id,
                    link_type=lt,
                )
                assert link.link_type == lt

    def test_create_invalid_link_type(self, manager, tenant_a, workspace_a):
        """REQ-L2-TE-001: Invalid link type raises InvalidLinkTypeError."""
        with active_tenant(tenant_a):
            src = make_artifact(tenant_a, workspace_a, "requirement")
            tgt = make_artifact(tenant_a, workspace_a, "requirement")

            with pytest.raises(InvalidLinkTypeError):
                manager.create(
                    source_id=src.id,
                    target_id=tgt.id,
                    link_type="invalid-type",
                )

    def test_create_missing_source(self, manager, tenant_a, workspace_a):
        """REQ-L2-TE-001: Missing source raises SourceNotFoundError."""
        with active_tenant(tenant_a):
            tgt = make_artifact(tenant_a, workspace_a, "requirement")

            with pytest.raises(SourceNotFoundError):
                manager.create(
                    source_id=uuid.uuid4(),
                    target_id=tgt.id,
                    link_type="satisfies",
                )

    def test_create_missing_target(self, manager, tenant_a, workspace_a):
        """REQ-L2-TE-001: Missing target raises TargetNotFoundError."""
        with active_tenant(tenant_a):
            src = make_artifact(tenant_a, workspace_a, "requirement")

            with pytest.raises(TargetNotFoundError):
                manager.create(
                    source_id=src.id,
                    target_id=uuid.uuid4(),
                    link_type="satisfies",
                )

    def test_read_link(self, manager, tenant_a, workspace_a):
        """REQ-L2-TE-001: get() returns the TraceLink by ID."""
        with active_tenant(tenant_a):
            src = make_artifact(tenant_a, workspace_a, "requirement")
            tgt = make_artifact(tenant_a, workspace_a, "requirement")
            link = manager.create(src.id, tgt.id, "satisfies")

            retrieved = manager.get(link.id)
        assert retrieved.id == link.id

    def test_update_link_type(self, manager, tenant_a, workspace_a):
        """REQ-L2-TE-001 / REQ-L2-TE-010: update changes link_type."""
        with active_tenant(tenant_a):
            src = make_artifact(tenant_a, workspace_a, "requirement")
            tgt = make_artifact(tenant_a, workspace_a, "requirement")
            link = manager.create(src.id, tgt.id, "satisfies")
            updated = manager.update(link.id, link_type="implements")
        assert updated.link_type == "implements"

    def test_delete_link(self, manager, tenant_a, workspace_a):
        """REQ-L2-TE-001: delete removes the TraceLink."""
        with active_tenant(tenant_a):
            src = make_artifact(tenant_a, workspace_a, "requirement")
            tgt = make_artifact(tenant_a, workspace_a, "requirement")
            link = manager.create(src.id, tgt.id, "satisfies")
            link_id = link.id
            manager.delete(link_id)

            with pytest.raises(TraceLink.DoesNotExist):
                manager.get(link_id)


# ---------------------------------------------------------------------------
# REQ-L2-TE-011: Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    """REQ-L2-TE-011: Cross-tenant links are rejected; queries are tenant-scoped."""

    def test_cross_tenant_link_rejected(
        self, manager, tenant_a, workspace_a, tenant_b, workspace_b_tenant_b
    ):
        """REQ-L2-TE-011: Cross-tenant link raises CrossTenantLinkError."""
        with active_tenant(tenant_a):
            src = make_artifact(tenant_a, workspace_a, "requirement")
        with active_tenant(tenant_b):
            tgt = make_artifact(tenant_b, workspace_b_tenant_b, "requirement")

        with active_tenant(tenant_a):
            with pytest.raises(CrossTenantLinkError):
                manager.create(src.id, tgt.id, "satisfies")

    def test_tenant_b_cannot_read_tenant_a_link(
        self, manager, tenant_a, workspace_a, tenant_b
    ):
        """REQ-L2-TE-011: Tenant-B cannot retrieve Tenant-A links."""
        with active_tenant(tenant_a):
            src = make_artifact(tenant_a, workspace_a, "requirement")
            tgt = make_artifact(tenant_a, workspace_a, "requirement")
            link = manager.create(src.id, tgt.id, "satisfies")
            link_id = link.id

        with active_tenant(tenant_b):
            with pytest.raises(TraceLink.DoesNotExist):
                manager.get(link_id)

    def test_get_trace_links_scoped_to_tenant(
        self, manager, tenant_a, workspace_a, tenant_b
    ):
        """REQ-L2-TE-011: get_trace_links only returns active-tenant links."""
        with active_tenant(tenant_a):
            src = make_artifact(tenant_a, workspace_a, "requirement")
            tgt = make_artifact(tenant_a, workspace_a, "requirement")
            manager.create(src.id, tgt.id, "satisfies")

        # tenant_b has no workspace / links — get_trace_links must return empty
        from persistence.models import Workspace
        with active_tenant(tenant_b):
            ws_b = Workspace.objects.create(tenant=tenant_b, name="ws-isolation")
            links = manager.get_trace_links()
        assert links == []


# ---------------------------------------------------------------------------
# REQ-L2-TE-002: Eager cycle detection
# ---------------------------------------------------------------------------

class TestCycleDetection:
    """REQ-L2-TE-002: Eager DFS cycle detection for single links."""

    def test_direct_cycle_rejected(self, manager, tenant_a, workspace_a):
        """A -> B -> A must be rejected."""
        with active_tenant(tenant_a):
            art_a = make_artifact(tenant_a, workspace_a, "requirement")
            art_b = make_artifact(tenant_a, workspace_a, "requirement")

            manager.create(art_a.id, art_b.id, "parent-child")

            with pytest.raises(CycleDetectedError):
                manager.create(art_b.id, art_a.id, "parent-child")

    def test_indirect_cycle_rejected(self, manager, tenant_a, workspace_a):
        """A -> B -> C -> A must be rejected at the last step."""
        with active_tenant(tenant_a):
            art_a = make_artifact(tenant_a, workspace_a, "requirement")
            art_b = make_artifact(tenant_a, workspace_a, "requirement")
            art_c = make_artifact(tenant_a, workspace_a, "requirement")

            manager.create(art_a.id, art_b.id, "derives-from")
            manager.create(art_b.id, art_c.id, "derives-from")

            with pytest.raises(CycleDetectedError):
                manager.create(art_c.id, art_a.id, "derives-from")

    def test_fan_out_no_cycle(self, manager, tenant_a, workspace_a):
        """A -> B, A -> C is not a cycle and must succeed."""
        with active_tenant(tenant_a):
            art_a = make_artifact(tenant_a, workspace_a, "requirement")
            art_b = make_artifact(tenant_a, workspace_a, "requirement")
            art_c = make_artifact(tenant_a, workspace_a, "requirement")

            link1 = manager.create(art_a.id, art_b.id, "satisfies")
            link2 = manager.create(art_a.id, art_c.id, "satisfies")

        assert link1 is not None
        assert link2 is not None

    def test_previous_links_survive_rejected_cycle(
        self, manager, tenant_a, workspace_a
    ):
        """REQ-L2-TE-002: Existing links are unchanged after cycle rejection."""
        with active_tenant(tenant_a):
            art_a = make_artifact(tenant_a, workspace_a, "requirement")
            art_b = make_artifact(tenant_a, workspace_a, "requirement")

            link = manager.create(art_a.id, art_b.id, "parent-child")

            with pytest.raises(CycleDetectedError):
                manager.create(art_b.id, art_a.id, "parent-child")

            # Original link must still exist
            retrieved = manager.get(link.id)
        assert retrieved.id == link.id


# ---------------------------------------------------------------------------
# REQ-L2-TE-003: Atomic batch operations
# ---------------------------------------------------------------------------

class TestBatchOperations:
    """REQ-L2-TE-003: Atomic batch with Tarjan cycle check."""

    def test_batch_create_all_valid(self, manager, tenant_a, workspace_a):
        """Batch of valid links → all persisted atomically."""
        with active_tenant(tenant_a):
            arts = [make_artifact(tenant_a, workspace_a, "requirement") for _ in range(5)]
            items = [
                {"source_id": arts[i].id, "target_id": arts[i + 1].id, "link_type": "satisfies"}
                for i in range(4)
            ]
            created = manager.batch_create(items)

        assert len(created) == 4
        with active_tenant(tenant_a):
            assert TraceLink.objects.count() == 4

    def test_batch_create_with_invalid_link_type_rolls_back(
        self, manager, tenant_a, workspace_a
    ):
        """Batch with invalid link_type → all rolled back."""
        with active_tenant(tenant_a):
            src = make_artifact(tenant_a, workspace_a, "requirement")
            tgt = make_artifact(tenant_a, workspace_a, "requirement")
            items = [
                {"source_id": src.id, "target_id": tgt.id, "link_type": "satisfies"},
                {"source_id": tgt.id, "target_id": src.id, "link_type": "NOT-VALID"},
            ]
            with pytest.raises(InvalidLinkTypeError):
                manager.batch_create(items)

            assert TraceLink.objects.count() == 0

    def test_batch_create_cycle_triggers_full_rollback(
        self, manager, tenant_a, workspace_a
    ):
        """REQ-L2-TE-003: Batch that closes a cycle → full rollback with path."""
        with active_tenant(tenant_a):
            art_a = make_artifact(tenant_a, workspace_a, "requirement")
            art_b = make_artifact(tenant_a, workspace_a, "requirement")
            art_c = make_artifact(tenant_a, workspace_a, "requirement")

            items = [
                {"source_id": art_a.id, "target_id": art_b.id, "link_type": "parent-child"},
                {"source_id": art_b.id, "target_id": art_c.id, "link_type": "parent-child"},
                {"source_id": art_c.id, "target_id": art_a.id, "link_type": "parent-child"},
            ]
            with pytest.raises(CycleDetectedError) as exc_info:
                manager.batch_create(items)

            # cycle_path must be set for batch errors (REQ-L2-TE-003)
            assert exc_info.value.cycle_path is not None
            assert TraceLink.objects.count() == 0

    def test_batch_delete_atomic(self, manager, tenant_a, workspace_a):
        """Batch delete removes all listed links atomically."""
        with active_tenant(tenant_a):
            arts = [make_artifact(tenant_a, workspace_a, "requirement") for _ in range(3)]
            links = [
                make_trace_link(arts[i], arts[i + 1], tenant_a)
                for i in range(2)
            ]
            link_ids = [l.id for l in links]

            count = manager.batch_delete(link_ids)

        assert count == 2
        with active_tenant(tenant_a):
            assert TraceLink.objects.count() == 0


# ---------------------------------------------------------------------------
# REQ-L2-TE-009: Referential integrity (CASCADE)
# ---------------------------------------------------------------------------

class TestReferentialIntegrity:
    """REQ-L2-TE-009: Deleting an artifact cascades to its TraceLinks."""

    def test_delete_source_artifact_cascades(
        self, manager, tenant_a, workspace_a
    ):
        """REQ-L2-TE-009: Deleting source artifact removes TraceLink."""
        with active_tenant(tenant_a):
            src = make_artifact(tenant_a, workspace_a, "requirement")
            tgt = make_artifact(tenant_a, workspace_a, "requirement")
            link = manager.create(src.id, tgt.id, "satisfies")

            # Delete source artifact — CASCADE must remove the link
            src.delete()

            assert TraceLink.objects.count() == 0

    def test_delete_target_artifact_cascades(
        self, manager, tenant_a, workspace_a
    ):
        """REQ-L2-TE-009: Deleting target artifact removes TraceLink."""
        with active_tenant(tenant_a):
            src = make_artifact(tenant_a, workspace_a, "requirement")
            tgt = make_artifact(tenant_a, workspace_a, "requirement")
            link = manager.create(src.id, tgt.id, "satisfies")

            tgt.delete()

            assert TraceLink.objects.count() == 0


# ---------------------------------------------------------------------------
# REQ-L2-TE-010: Audit metadata
# ---------------------------------------------------------------------------

class TestAuditMetadata:
    """REQ-L2-TE-010: created_by, modified_by captured on write."""

    def test_created_by_captured(self, manager, tenant_a, workspace_a):
        """REQ-L2-TE-010: created_by is set when provided."""
        from persistence.models import User
        with active_tenant(tenant_a):
            user = User.objects.create(
                username="actor-te", email="actor@te.test", tenant=tenant_a
            )
            src = make_artifact(tenant_a, workspace_a, "requirement")
            tgt = make_artifact(tenant_a, workspace_a, "requirement")
            link = manager.create(src.id, tgt.id, "satisfies", created_by_id=user.id)

        assert link.created_by_id == user.id
        assert link.created_at is not None

    def test_modified_by_updated_on_update(self, manager, tenant_a, workspace_a):
        """REQ-L2-TE-010: modified_by is updated; created fields are unchanged."""
        from persistence.models import User
        with active_tenant(tenant_a):
            user = User.objects.create(
                username="actor-te2", email="actor2@te.test", tenant=tenant_a
            )
            src = make_artifact(tenant_a, workspace_a, "requirement")
            tgt = make_artifact(tenant_a, workspace_a, "requirement")
            link = manager.create(src.id, tgt.id, "satisfies", created_by_id=user.id)

            updated = manager.update(link.id, link_type="implements", modified_by_id=user.id)

        assert updated.modified_by_id == user.id
        assert updated.created_by_id == user.id  # unchanged
