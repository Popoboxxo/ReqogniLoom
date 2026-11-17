"""L1-006 — legacy audit-log reconstruction must stay inside its tenant AND type.

For a legacy (state NULL) baseline the reconstructor falls back to an
``unscoped`` ``AuditLogEntry`` query. ``unscoped`` escapes the ORM tenant
manager but not explicit predicates; without them a superuser test connection
(or any connection where RLS is not in force) would happily return another
tenant's — or another entity type's — historical payload for the same item id
and version.

Two collision shapes are covered:
  * cross-tenant: the same (object_id, object_type, version) owned by A must not
    satisfy B's reconstruction (the explicit ``tenant_id`` predicate);
  * cross-type: a decoy owned by the SAME tenant with the SAME object_id and
    version but a different ``object_type`` must not satisfy a ``Requirement``
    reconstruction (the explicit ``object_type`` predicate). The decoy is
    given the highest id so it sorts first by ``-id`` — without the
    discriminator it would be the entry actually returned.
"""
from __future__ import annotations

import uuid

import pytest

from baseline.exceptions import VersionNotFoundError
from baseline.version_reconstructor import VersionReconstructor
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db(transaction=True)

_SECRET_TITLE = "TENANT-A-SECRET-HISTORICAL-TITLE"
_DECOY_TITLE = "SAME-TENANT-OTHER-ENTITY-TYPE-DECOY"

# AuditLogEntry.id is a random UUID and the query orders by ``-id``, so pin the
# ids to guarantee the decoy sorts first without the discriminator.
_REAL_ENTRY_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_DECOY_ENTRY_ID = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")


class _LegacyStore:
    """Stand-in that forces the legacy audit-log path (no captured state)."""

    def lookup_item_version(
        self, baseline_id: uuid.UUID, item_id: str, tenant_id: uuid.UUID
    ) -> int:
        # Same item id and version for both tenants — the collision shape.
        return 1

    def load_states(
        self,
        baseline_id: uuid.UUID,
        tenant_id: uuid.UUID,
        item_ids: list[str] | None = None,
    ) -> None:
        return None


@pytest.fixture(autouse=True)
def _clear_tenant_context() -> None:
    TenantContext.clear_tenant()
    yield
    TenantContext.clear_tenant()


def _create_tenant(tenant_id: uuid.UUID, suffix: str) -> None:
    from persistence.models import Tenant

    TenantContext.set_tenant(tenant_id)
    try:
        Tenant.objects.create(
            id=tenant_id,
            name=f"Reconstructor Tenant {suffix}",
            slug=f"reconstructor-{suffix}-{tenant_id.hex[:8]}",
        )
    finally:
        TenantContext.clear_tenant()


def _seed_audit_entry(
    tenant_id: uuid.UUID,
    item_id: str,
    object_type: str,
    title: str,
    entry_id: uuid.UUID,
) -> None:
    from persistence.models import AuditLogEntry

    TenantContext.set_tenant(tenant_id)
    try:
        AuditLogEntry.objects.create(
            id=entry_id,
            object_id=item_id,
            object_type=object_type,
            action="update",
            payload={"version": 1, "title": title},
        )
    finally:
        TenantContext.clear_tenant()


def test_tenant_and_object_type_discriminate_audit_payload() -> None:
    """Only the owning tenant's, matching-type audit entry may be returned."""
    tenant_a_id, tenant_b_id = uuid.uuid4(), uuid.uuid4()
    item_id = str(uuid.uuid4())
    _create_tenant(tenant_a_id, "a")
    _create_tenant(tenant_b_id, "b")

    # Tenant A owns the real Requirement entry at this (item_id, version) pair.
    _seed_audit_entry(
        tenant_a_id, item_id, "Requirement", _SECRET_TITLE, _REAL_ENTRY_ID
    )
    # Cross-TYPE decoy: SAME tenant, SAME object_id, SAME payload version, but a
    # different entity class. Its id sorts first by -id, so it would be returned
    # if object_type were not part of the query.
    _seed_audit_entry(
        tenant_a_id, item_id, "ArchitectureElement", _DECOY_TITLE, _DECOY_ENTRY_ID
    )
    # Tenant B owns no entry at this (item_id, version) pair — the collision
    # shape for the cross-tenant guard.

    store = _LegacyStore()
    reconstructor = VersionReconstructor(store=store)
    # Distinct baseline ids: the LRU cache is keyed on (baseline_id, item,
    # version), so reusing one baseline would let the first result alias the
    # second and hide the discriminator's effect.
    baseline_undisc, baseline_a, baseline_b = (
        uuid.uuid4(),
        uuid.uuid4(),
        uuid.uuid4(),
    )

    # Proof the decoy matters: with no discriminator the newest same-id entry
    # (the cross-type decoy) wins, so the guard below cannot pass by accident.
    undiscriminated = reconstructor.get_item_at_baseline(
        baseline_undisc, item_id, tenant_a_id
    )
    assert undiscriminated.title == _DECOY_TITLE

    # With the concrete class threaded through, only the Requirement entry is
    # eligible: the same-tenant cross-type decoy is excluded.
    payload_a = reconstructor.get_item_at_baseline(
        baseline_a, item_id, tenant_a_id, object_type="Requirement"
    )
    assert payload_a.title == _SECRET_TITLE

    # Tenant B sees no row at all, so the fallback fails closed instead of
    # leaking A's secret through the unscoped audit query (with or without the
    # object_type predicate).
    with pytest.raises(VersionNotFoundError):
        reconstructor.get_item_at_baseline(
            baseline_b, item_id, tenant_b_id, object_type="Requirement"
        )
