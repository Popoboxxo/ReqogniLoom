"""Tenant lifecycle calls the memory provider hooks (P5).

Provisioning is best-effort and must never block tenant creation; teardown is
deferred to commit and also best-effort. Both are no-ops on the default
backends and are exercised here through a fake provider.
"""
from __future__ import annotations

import pytest

from auth_tenancy import provisioning
from persistence.models import Tenant

pytestmark = pytest.mark.django_db


class _FakeProvider:
    def __init__(self) -> None:
        self.provisioned: list = []
        self.torn_down: list = []

    def provision_tenant(self, tenant_id) -> None:
        self.provisioned.append(tenant_id)

    def teardown_tenant(self, tenant_id) -> None:
        self.torn_down.append(tenant_id)


def test_ensure_tenant_provisions_the_memory_provider(monkeypatch) -> None:
    fake = _FakeProvider()
    monkeypatch.setattr("memory.backends.get_memory_backend", lambda: fake)

    tenant = provisioning._ensure_tenant()

    assert tenant.id in fake.provisioned


def test_provisioning_failure_never_blocks_tenant_creation(monkeypatch) -> None:
    def _boom():
        raise RuntimeError("memory backend unavailable")

    monkeypatch.setattr("memory.backends.get_memory_backend", _boom)

    tenant = provisioning._ensure_tenant()

    assert tenant.pk is not None


def test_teardown_runs_on_commit(monkeypatch, django_capture_on_commit_callbacks) -> None:
    from memory.apps import _teardown_memory_tenant

    fake = _FakeProvider()
    monkeypatch.setattr("memory.backends.get_memory_backend", lambda: fake)
    tenant = provisioning._ensure_tenant()

    with django_capture_on_commit_callbacks(execute=True):
        _teardown_memory_tenant(sender=Tenant, instance=tenant)

    assert tenant.id in fake.torn_down
