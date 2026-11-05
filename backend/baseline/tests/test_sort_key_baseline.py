"""P1 Task 1.6: ``sort_key`` in the baseline snapshot, diff and rollback map."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from baseline.diff_engine import DiffEngine, _field_diff
from baseline.restorable_fields import NON_RESTORABLE
from baseline.state_capture import capture_states
from baseline.types import DeltaIndexTuple
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Artifact, Requirement, Tenant, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db


def _requirement(slug: str) -> tuple[Tenant, Artifact]:
    tenant = Tenant.objects.create(name=slug, slug=slug)
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name=f"{slug}-ws")
    finally:
        clear_request_tenant()
    artifact = Artifact.unscoped.create(
        tenant=tenant,
        workspace=workspace,
        artifact_type="Requirement",
        sort_key="a0",
    )
    Requirement.unscoped.create(
        tenant=tenant,
        artifact=artifact,
        workspace=workspace,
        title="Req",
        uid=f"{slug}-1",
    )
    return tenant, artifact


def test_snapshot_contains_sort_key():
    tenant, artifact = _requirement("sk-snapshot")

    TenantContext.set_tenant(tenant.id)
    try:
        states = capture_states(
            [DeltaIndexTuple(item_id=str(artifact.id), version=1)], tenant.id
        )
    finally:
        TenantContext.clear_tenant()

    assert states[str(artifact.id)]["sort_key"] == "a0"


class _StubStore:
    def __init__(self, index, states):
        self._index = index
        self._states = states

    def load_delta_index(self, baseline_id, tenant_id=None):
        return self._index[baseline_id]

    def load_states(self, baseline_id, tenant_id=None, item_ids=None):
        return self._states[baseline_id]


def _diff(a, b, index, states):
    engine = DiffEngine(store=_StubStore(index, states))
    snap = MagicMock()
    snap.scope = "project"
    with patch("baseline.diff_engine.BaselineSnapshot") as mock_snap:
        mock_snap.unscoped.only.return_value.get.return_value = snap
        return engine.diff(a, b, uuid.uuid4())


def test_single_move_one_diff_entry():
    item = str(uuid.uuid4())
    a, b = uuid.uuid4(), uuid.uuid4()
    index = {a: [(item, 1, "item")], b: [(item, 1, "item")]}
    states = {
        a: {item: {"sort_key": "a0", "title": "Req", "version": 1}},
        b: {item: {"sort_key": "a1", "title": "Req", "version": 1}},
    }

    result = _diff(a, b, index, states)

    assert [change.id for change in result.changed] == [item]
    assert result.changed[0].field_changes == {
        "sort_key": {"old": "a0", "new": "a1"}
    }


def test_old_snapshot_without_sort_key_no_crash_no_noise():
    old = {"title": "Req", "version": 1}
    new = {"title": "Req", "version": 1, "sort_key": "a0"}

    assert _field_diff(old, new) == {}


def test_sort_key_classified_in_restorable_fields():
    assert "sort_key" in NON_RESTORABLE["Requirement"]
    assert "sort_key" in NON_RESTORABLE["ArchitectureElement"]
