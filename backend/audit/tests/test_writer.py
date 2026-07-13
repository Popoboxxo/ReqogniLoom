"""
COMP-AL-001 AuditLogWriter — Tests.

Covers:
- REQ-L3-AL001-001: Event-Bus subscription and field extraction
- REQ-L3-AL001-002: MCP enrichment (client_name, api_key_hash SHA-256)
- REQ-L3-AL001-003: Append-Only constraint (no update/delete)
- REQ-L3-AL001-004: Atomic transaction consistency
- REQ-L3-AL001-005: Tenant-ID injection
"""
from __future__ import annotations

import hashlib
import uuid

import pytest

from persistence.models import Tenant
from persistence.tenancy import TenantContext, TenantContextNotSetError

from audit.events import AuditableOperationOccurred, DomainEventBus
from audit.models import AuditEntry
from audit.tests.conftest import active_tenant, make_entry
from audit.writer import (
    AuditLogWriter,
    ContextEnricher,
    MissingTenantContextError,
    TenantContextInjector,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# REQ-L3-AL001-001: Event-Bus Subscription and Field Extraction
# ---------------------------------------------------------------------------


class TestEventBusSubscription:
    def test_writer_subscribes_to_domain_event_bus(self, tenant_a: Tenant) -> None:
        """AuditLogWriter registers on DomainEventBus and handles events."""
        writer = AuditLogWriter()
        DomainEventBus.subscribe(writer.handle_event)

        entity_id = uuid.uuid4()
        with active_tenant(tenant_a):
            event = AuditableOperationOccurred(
                actor="user-42",
                actor_type="user",
                op="create",
                entity_type="Requirement",
                entity_id=entity_id,
                version=1,
            )
            DomainEventBus.publish(event)

        with active_tenant(tenant_a):
            entry = AuditEntry.objects.get(entity_id=entity_id)

        assert entry.actor == "user-42"
        assert entry.actor_type == "user"
        assert entry.op == "create"
        assert entry.entity_type == "Requirement"
        assert entry.entity_id == entity_id
        assert entry.entity_version == 1
        assert entry.tenant_id == tenant_a.id

    def test_all_mandatory_fields_mapped(self, tenant_a: Tenant) -> None:
        """All mandatory event fields are persisted without loss."""
        writer = AuditLogWriter()
        entity_id = uuid.uuid4()

        with active_tenant(tenant_a):
            event = AuditableOperationOccurred(
                actor="user-99",
                actor_type="user",
                op="update",
                entity_type="TestCase",
                entity_id=entity_id,
                version=3,
                change_reason="Status updated",
            )
            entry = writer.write(event)

        assert entry.actor == "user-99"
        assert entry.op == "update"
        assert entry.entity_type == "TestCase"
        assert entry.entity_id == entity_id
        assert entry.entity_version == 3
        assert entry.change_reason == "Status updated"

    def test_missing_optional_fields_result_in_null(self, tenant_a: Tenant) -> None:
        """Missing optional fields (change_reason) store NULL, not an error."""
        writer = AuditLogWriter()
        entity_id = uuid.uuid4()

        with active_tenant(tenant_a):
            event = AuditableOperationOccurred(
                actor="user-1",
                actor_type="user",
                op="delete",
                entity_type="Requirement",
                entity_id=entity_id,
            )
            entry = writer.write(event)

        assert entry.change_reason is None
        assert entry.entity_version is None

    def test_event_with_unknown_extra_ctx_fields_accepted(self, tenant_a: Tenant) -> None:
        """Forward-compatible: extra fields in ctx do not cause errors."""
        writer = AuditLogWriter()
        entity_id = uuid.uuid4()

        with active_tenant(tenant_a):
            event = AuditableOperationOccurred(
                actor="user-1",
                actor_type="user",
                op="create",
                entity_type="Requirement",
                entity_id=entity_id,
                ctx={"source": "rest", "unknown_future_field": "ignored"},
            )
            entry = writer.write(event)  # Must not raise

        assert entry is not None


# ---------------------------------------------------------------------------
# REQ-L3-AL001-002: MCP Enrichment
# ---------------------------------------------------------------------------


class TestMCPEnrichment:
    def test_mcp_event_stores_api_key_hash_not_raw(self, tenant_a: Tenant) -> None:
        """MCP event with API-Key stores sha256: prefixed hash, not raw key."""
        writer = AuditLogWriter()
        raw_key = "my-secret-api-key-12345"
        entity_id = uuid.uuid4()

        with active_tenant(tenant_a):
            event = AuditableOperationOccurred(
                actor="agent-claude",
                actor_type="agent",
                op="create",
                entity_type="Requirement",
                entity_id=entity_id,
                ctx={
                    "source": "mcp",
                    "client_name": "claude-code/1.0",
                    "api_key": raw_key,
                },
            )
            entry = writer.write(event)

        expected_hash = "sha256:" + hashlib.sha256(raw_key.encode()).hexdigest()
        assert entry.actor_type == "agent"
        assert entry.source == "mcp"
        assert entry.client_name == "claude-code/1.0"
        assert entry.api_key_hash == expected_hash
        assert raw_key not in (entry.api_key_hash or "")

    def test_rest_event_has_null_mcp_fields(self, tenant_a: Tenant) -> None:
        """REST event: source='rest', client_name=NULL, api_key_hash=NULL."""
        writer = AuditLogWriter()
        entity_id = uuid.uuid4()

        with active_tenant(tenant_a):
            event = AuditableOperationOccurred(
                actor="user-5",
                actor_type="user",
                op="update",
                entity_type="Requirement",
                entity_id=entity_id,
                ctx={"source": "rest"},
            )
            entry = writer.write(event)

        assert entry.actor_type == "user"
        assert entry.source == "rest"
        assert entry.client_name is None
        assert entry.api_key_hash is None

    def test_sha256_hash_is_reproducible(self) -> None:
        """Same API key always produces same SHA-256 hash."""
        raw_key = "reproducible-key"
        enrichment_1 = ContextEnricher.enrich("agent", {"api_key": raw_key, "source": "mcp"})
        enrichment_2 = ContextEnricher.enrich("agent", {"api_key": raw_key, "source": "mcp"})

        assert enrichment_1["api_key_hash"] == enrichment_2["api_key_hash"]
        assert enrichment_1["api_key_hash"].startswith("sha256:")

    def test_db_has_no_raw_api_key_column(self) -> None:
        """AuditEntry model has no 'api_key_raw' column (REQ-L3-AL001-002)."""
        field_names = [f.name for f in AuditEntry._meta.get_fields()]
        assert "api_key_raw" not in field_names
        assert "api_key" not in field_names


# ---------------------------------------------------------------------------
# REQ-L3-AL001-003: Append-Only Constraint
# ---------------------------------------------------------------------------


class TestAppendOnlyConstraint:
    def test_write_succeeds(self, tenant_a: Tenant) -> None:
        """New AuditEntry INSERT succeeds."""
        writer = AuditLogWriter()
        entity_id = uuid.uuid4()

        with active_tenant(tenant_a):
            event = AuditableOperationOccurred(
                actor="user-1",
                actor_type="user",
                op="create",
                entity_type="Requirement",
                entity_id=entity_id,
            )
            entry = writer.write(event)

        assert entry.pk is not None

    def test_bulk_update_via_manager_raises(self, tenant_a: Tenant) -> None:
        """AuditEntry.objects.update() is rejected at manager level."""
        make_entry(tenant_a)

        with active_tenant(tenant_a):
            with pytest.raises(RuntimeError, match="append-only"):
                AuditEntry.objects.update(actor="hacked")

    def test_bulk_delete_via_manager_raises(self, tenant_a: Tenant) -> None:
        """AuditEntry.objects.delete() is rejected at manager level."""
        make_entry(tenant_a)

        with active_tenant(tenant_a):
            with pytest.raises(RuntimeError, match="append-only"):
                AuditEntry.objects.delete()

    def test_instance_delete_raises(self, tenant_a: Tenant) -> None:
        """entry.delete() is rejected at instance level."""
        entry = make_entry(tenant_a)

        with pytest.raises(RuntimeError, match="append-only"):
            entry.delete()

    def test_instance_save_on_existing_raises(self, tenant_a: Tenant) -> None:
        """entry.save() on an existing entry is rejected."""
        entry = make_entry(tenant_a)

        with pytest.raises(RuntimeError, match="append-only"):
            entry.save()

    def test_no_update_entry_method_on_writer(self) -> None:
        """AuditLogWriter has no update_entry() or delete_entry() method."""
        writer = AuditLogWriter()
        assert not hasattr(writer, "update_entry")
        assert not hasattr(writer, "delete_entry")

    def test_no_update_entry_method_on_services(self) -> None:
        """audit.services has no update_entry() or delete_entry()."""
        import audit.services as svc
        assert not hasattr(svc, "update_entry")
        assert not hasattr(svc, "delete_entry")


# ---------------------------------------------------------------------------
# REQ-L3-AL001-004: Atomic Transaction Consistency
# ---------------------------------------------------------------------------


class TestAtomicConsistency:
    def test_successful_write_persists_entry(self, tenant_a: Tenant) -> None:
        """Successful write creates one AuditEntry in DB."""
        writer = AuditLogWriter()
        entity_id = uuid.uuid4()

        with active_tenant(tenant_a):
            initial_count = AuditEntry.objects.count()
            event = AuditableOperationOccurred(
                actor="user-1",
                actor_type="user",
                op="create",
                entity_type="Requirement",
                entity_id=entity_id,
            )
            writer.write(event)
            final_count = AuditEntry.objects.count()

        assert final_count == initial_count + 1

    def test_write_inside_atomic_block_rolls_back_on_error(
        self, tenant_a: Tenant
    ) -> None:
        """If the outer transaction rolls back, the audit entry is also rolled back."""
        from django.db import transaction

        writer = AuditLogWriter()
        entity_id = uuid.uuid4()

        with active_tenant(tenant_a):
            count_before = AuditEntry.objects.count()

        try:
            with transaction.atomic():
                with active_tenant(tenant_a):
                    event = AuditableOperationOccurred(
                        actor="user-1",
                        actor_type="user",
                        op="create",
                        entity_type="Requirement",
                        entity_id=entity_id,
                    )
                    writer.write(event)
                # Simulate a business error that triggers rollback
                raise ValueError("simulated business error")
        except ValueError:
            pass

        # After rollback, no entry should exist
        with active_tenant(tenant_a):
            count_after = AuditEntry.objects.count()

        assert count_after == count_before

    def test_count_equals_successful_writes(self, tenant_a: Tenant) -> None:
        """AuditEntry count equals exactly the number of successful write operations."""
        writer = AuditLogWriter()

        with active_tenant(tenant_a):
            initial = AuditEntry.objects.count()
            for i in range(5):
                event = AuditableOperationOccurred(
                    actor=f"user-{i}",
                    actor_type="user",
                    op="create",
                    entity_type="Requirement",
                    entity_id=uuid.uuid4(),
                )
                writer.write(event)
            assert AuditEntry.objects.count() == initial + 5


# ---------------------------------------------------------------------------
# REQ-L3-AL001-005: Tenant-ID Injection
# ---------------------------------------------------------------------------


class TestTenantIDInjection:
    def test_write_with_tenant_context_injects_tenant_id(
        self, tenant_a: Tenant
    ) -> None:
        """Write in tenant-A context stores tenant_id = tenant_A."""
        writer = AuditLogWriter()
        entity_id = uuid.uuid4()

        with active_tenant(tenant_a):
            event = AuditableOperationOccurred(
                actor="user-1",
                actor_type="user",
                op="create",
                entity_type="Requirement",
                entity_id=entity_id,
            )
            entry = writer.write(event)

        assert entry.tenant_id == tenant_a.id

    def test_write_without_tenant_context_raises_error(self) -> None:
        """Write without active tenant context raises MissingTenantContextError."""
        writer = AuditLogWriter()
        TenantContext.clear_tenant()

        event = AuditableOperationOccurred(
            actor="user-1",
            actor_type="user",
            op="create",
            entity_type="Requirement",
            entity_id=uuid.uuid4(),
        )
        with pytest.raises(MissingTenantContextError):
            writer.write(event)

    def test_tenant_context_injector_raises_missing_error(self) -> None:
        """TenantContextInjector raises MissingTenantContextError when context absent."""
        TenantContext.clear_tenant()
        with pytest.raises(MissingTenantContextError):
            TenantContextInjector.get_tenant_id()
