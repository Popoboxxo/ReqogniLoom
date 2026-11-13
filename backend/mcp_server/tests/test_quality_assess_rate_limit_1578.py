"""Issue #1578: ``quality.assess`` is capped with the same scope on MCP."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from django.core.cache import cache

from auth_tenancy.context import AuthContext
from mcp_server.tools.quality import _assess_rate_limited

pytestmark = pytest.mark.django_db


def _ctx() -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("editor",),
        auth_method="test",
        api_key_id=uuid.uuid4(),
    )


def test_the_mcp_assessment_uses_the_shared_scope() -> None:
    cache.clear()
    ctx = _ctx()

    with patch(
        "admin_ops.rate_limits.resolve_rate", return_value="1/hour"
    ) as resolve:
        assert _assess_rate_limited(ctx, "key") is False
        assert _assess_rate_limited(ctx, "key") is True

    resolve.assert_called_with("quality_assess", tenant_id=ctx.tenant_id)
    cache.clear()


def test_an_empty_rate_falls_back_to_the_rest_default() -> None:
    cache.clear()
    ctx = _ctx()

    with patch("admin_ops.rate_limits.resolve_rate", return_value=""):
        assert _assess_rate_limited(ctx, "key") is False
    cache.clear()
