"""GH-1199 — administrative baseline purge (Layer 1).

Pins the single sanctioned removal path for an append-only baseline and the
invariant it must not weaken:

* ``baseline.services.purge_baseline`` deletes the snapshot together with its
  delta entries — the ORM collector removes the dependents first, both under the
  transaction-local GUC ``app.baseline_admin_delete`` armed by the helper.
* The ``bl_raise_immutable`` trigger still blocks a plain DELETE/UPDATE without
  the GUC, so the application-layer guarantee is a *narrow, explicit* exception,
  not a disabled trigger.
* The GUC is transaction-local (``set_config(..., is_local=true)``): after the
  purge transaction commits, a plain delete raises again.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import InternalError, transaction

from baseline.models import BaselineDeltaIndexEntry, BaselineSnapshot
from baseline.services import purge_baseline

pytestmark = pytest.mark.django_db


def _env() -> tuple[object, object, object]:
    """Create a tenant plus one baseline with a single delta entry.

    Returns ``(tenant, snapshot, delta_entry)``.
    """
    from persistence.models import Tenant

    tenant = Tenant.objects.create(
        name=f"purge1199-{uuid.uuid4().hex[:8]}",
        slug=f"purge1199-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    snapshot = BaselineSnapshot.unscoped.create(
        tenant=tenant,
        workspace_id=uuid.uuid4(),
        scope="project",
        name=f"bl-{uuid.uuid4().hex[:8]}",
    )
    entry = BaselineDeltaIndexEntry.objects.create(
        baseline=snapshot,
        item_id=str(uuid.uuid4()),
        version=1,
        entity_type="item",
    )
    return tenant, snapshot, entry


def test_purge_removes_snapshot_and_delta_entries() -> None:
    tenant, snapshot, _ = _env()

    purge_baseline(snapshot.id, tenant.id)

    assert not BaselineSnapshot.unscoped.filter(pk=snapshot.pk).exists()
    assert not BaselineDeltaIndexEntry.objects.filter(baseline_id=snapshot.pk).exists()


def test_purge_of_unknown_baseline_raises_not_found() -> None:
    from baseline.exceptions import BaselineNotFoundError

    from persistence.models import Tenant

    tenant = Tenant.objects.create(
        name=f"purge1199-miss-{uuid.uuid4().hex[:8]}",
        slug=f"purge1199-miss-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    with pytest.raises(BaselineNotFoundError):
        purge_baseline(uuid.uuid4(), tenant.id)


def test_not_found_purge_does_not_leave_the_guc_armed() -> None:
    """A missed purge must still disarm the GUC before it raises.

    The not-found path raises *after* the (zero-row) DELETE; if the reset were
    skipped there, the GUC would stay armed for the rest of the transaction and
    a later plain DELETE would silently pass the trigger.
    """
    from baseline.exceptions import BaselineNotFoundError

    from persistence.models import Tenant

    missing_tenant = Tenant.objects.create(
        name=f"purge1199-none-{uuid.uuid4().hex[:8]}",
        slug=f"purge1199-none-{uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    _, survivor, _ = _env()

    with pytest.raises(BaselineNotFoundError):
        purge_baseline(uuid.uuid4(), missing_tenant.id)

    with transaction.atomic(), pytest.raises(InternalError, match=r"(?i)immutable"):
        BaselineSnapshot.unscoped.filter(pk=survivor.pk).delete()


def test_purge_does_not_touch_another_tenants_baseline() -> None:
    """Tenant isolation: a foreign baseline id is a not-found, not a delete."""
    from baseline.exceptions import BaselineNotFoundError

    _, victim, _ = _env()
    other_tenant, _, _ = _env()

    with pytest.raises(BaselineNotFoundError):
        purge_baseline(victim.id, other_tenant.id)

    assert BaselineSnapshot.unscoped.filter(pk=victim.pk).exists()


def test_trigger_still_blocks_a_plain_delete_without_the_guc() -> None:
    _, snapshot, _ = _env()

    with transaction.atomic(), pytest.raises(InternalError, match=r"(?i)immutable"):
        BaselineSnapshot.unscoped.filter(pk=snapshot.pk).delete()

    assert BaselineSnapshot.unscoped.filter(pk=snapshot.pk).exists()


def test_trigger_still_blocks_update_without_the_guc() -> None:
    _, snapshot, _ = _env()

    with transaction.atomic(), pytest.raises(InternalError, match=r"(?i)immutable"):
        BaselineSnapshot.unscoped.filter(pk=snapshot.pk).update(name="renamed")

    snapshot.refresh_from_db()
    assert snapshot.name != "renamed"


def test_the_guc_is_transaction_local_and_does_not_leak() -> None:
    """After the purge transaction commits, a plain delete raises again."""
    tenant, first, _ = _env()
    _, second, _ = _env()

    purge_baseline(first.id, tenant.id)
    assert not BaselineSnapshot.unscoped.filter(pk=first.pk).exists()

    with transaction.atomic(), pytest.raises(InternalError, match=r"(?i)immutable"):
        BaselineSnapshot.unscoped.filter(pk=second.pk).delete()

    assert BaselineSnapshot.unscoped.filter(pk=second.pk).exists()
