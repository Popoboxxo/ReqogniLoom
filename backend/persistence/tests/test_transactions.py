"""
COMP-PL-003 TransactionCoordinator — ACID / rollback tests.

Covers REQ-L2-PL-002 / REQ-L3-PL003-001..002.
"""
from __future__ import annotations

import pytest

from persistence.models import Artifact, Requirement
from persistence.tests.conftest import active_tenant
from persistence.transactions import TransactionContextManager, atomic_transaction

pytestmark = pytest.mark.django_db


class _InducedError(RuntimeError):
    pass


def test_decorator_rolls_back_on_error(tenant_a, workspace_a):
    """REQ-L3-PL003-002: an exception inside the atomic block persists nothing."""

    @atomic_transaction
    def create_then_fail():
        Artifact.objects.create(
            tenant=tenant_a, workspace=workspace_a, artifact_type="x"
        )
        raise _InducedError("boom")

    with active_tenant(tenant_a):
        with pytest.raises(_InducedError):
            create_then_fail()
        assert Artifact.objects.count() == 0


def test_decorator_commits_on_success(tenant_a, workspace_a):
    """REQ-L3-PL003-001: a successful atomic method commits its writes."""

    @atomic_transaction
    def create_ok():
        return Artifact.objects.create(
            tenant=tenant_a, workspace=workspace_a, artifact_type="x"
        )

    with active_tenant(tenant_a):
        create_ok()
        assert Artifact.objects.count() == 1


def test_context_manager_batch_rollback(tenant_a, workspace_a):
    """REQ-L3-PL003-002: a failure mid-batch rolls back the whole batch."""
    with active_tenant(tenant_a):
        with pytest.raises(_InducedError):
            with TransactionContextManager():
                parent = Artifact.objects.create(
                    tenant=tenant_a, workspace=workspace_a, artifact_type="p"
                )
                Requirement.objects.create(
                    tenant=tenant_a, artifact=parent, title="r"
                )
                raise _InducedError("constraint on child 7")
        assert Artifact.objects.count() == 0
        assert Requirement.objects.count() == 0
