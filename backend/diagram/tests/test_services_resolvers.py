"""Tenant/user resolvers on the diagram service facade (ADR-01, issue #124).

``create_diagram``/``update_diagram`` take ORM ``Tenant``/``User`` objects
rather than ids, so callers need a way to turn an ``AuthContext``'s ids into
those objects. That lookup used to sit in ``mcp_server/tools/diagram.py`` and
violated ADR-01; it now lives in ``diagram.services``.

These tests pin the error/None contract the MCP tool depends on: an unknown
tenant *raises* (the tool has no meaningful fallback), an unknown or absent
user resolves to ``None`` (audit attribution is optional).
"""
from __future__ import annotations

import uuid

import pytest

from diagram.services import resolve_tenant, resolve_user

pytestmark = pytest.mark.django_db


class TestResolveTenant:
    def test_returns_the_tenant(self, tenant_a):
        assert resolve_tenant(tenant_a.id) == tenant_a

    def test_unknown_tenant_raises_does_not_exist(self):
        from persistence.models import Tenant

        with pytest.raises(Tenant.DoesNotExist):
            resolve_tenant(uuid.uuid4())


class TestResolveUser:
    def test_returns_the_user(self, tenant_a):
        from persistence.models import User

        user = User.objects.create(
            username="diagram-resolver-user",
            email="diagram-resolver@example.com",
            tenant=tenant_a,
        )

        assert resolve_user(user.id) == user

    def test_unknown_user_returns_none(self):
        assert resolve_user(uuid.uuid4()) is None

    def test_none_user_id_returns_none(self):
        """API-key/machine contexts have no user id — must not raise."""
        assert resolve_user(None) is None
