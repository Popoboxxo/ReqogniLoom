"""Issue #989 — env-configurable default link types for new workspaces.

``DEFAULT_TRACE_LINK_TYPE`` / ``DEFAULT_DECOMPOSITION_LINK_TYPE`` decide what a
NEW workspace starts with (and the fallback for an empty column). Both stay
per-workspace overridable, and an unknown environment value must never break
workspace creation.
"""
from __future__ import annotations

import logging
import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from application.workspace_service import WorkspaceService
from link_types.defaults import (
    default_decomposition_link_type,
    default_trace_link_type,
)
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db


def _ctx(tenant_id, user_id):
    ctx = MagicMock()
    ctx.active_roles = ("admin",)
    ctx.tenant_id = tenant_id
    ctx.user_id = user_id
    ctx.has_role = lambda role: role in ("admin",)
    return ctx


def _tenant_and_user():
    tenant = Tenant.objects.create(
        name="LinkDefaults", slug=f"link-defaults-{uuid.uuid4().hex[:8]}"
    )
    user = User.objects.create(
        username=f"link-defaults-{uuid.uuid4().hex[:8]}",
        email=f"link-defaults-{uuid.uuid4().hex[:8]}@example.com",
        tenant=tenant,
    )
    return tenant, user


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


def test_resolver_uses_the_documented_fallbacks_when_unset():
    with override_settings(DEFAULT_TRACE_LINK_TYPE="", DEFAULT_DECOMPOSITION_LINK_TYPE=""):
        assert default_trace_link_type() == "references"
        assert default_decomposition_link_type() == "decomposes"


def test_resolver_honours_configured_values():
    with override_settings(
        DEFAULT_TRACE_LINK_TYPE="verifies",
        DEFAULT_DECOMPOSITION_LINK_TYPE="derives-from",
    ):
        assert default_trace_link_type() == "verifies"
        assert default_decomposition_link_type() == "derives-from"


def test_resolver_falls_back_on_an_unknown_link_type():
    with override_settings(
        DEFAULT_TRACE_LINK_TYPE="not-a-link-type",
        DEFAULT_DECOMPOSITION_LINK_TYPE="also-bogus",
    ):
        assert default_trace_link_type() == "references"
        assert default_decomposition_link_type() == "decomposes"


def test_decomposition_default_rejects_a_valid_but_non_hierarchy_link_type(caplog):
    """ADR-016 decision 4: ``refines`` is a valid built-in but must not be an
    accepted decomposition default — it degrades to ``decomposes`` with a
    warning instead of silently creating a hierarchy-ignored edge."""
    with override_settings(DEFAULT_DECOMPOSITION_LINK_TYPE="refines"):
        with caplog.at_level(logging.WARNING, logger="link_types.defaults"):
            resolved = default_decomposition_link_type()

    assert resolved == "decomposes"
    assert "refines" in caplog.text
    assert "DEFAULT_DECOMPOSITION_LINK_TYPE" in caplog.text


@pytest.mark.parametrize("value", ["decomposes", "derives-from"])
def test_decomposition_default_honours_hierarchy_link_types(value):
    """The two hierarchy types pass through unchanged (ADR-016)."""
    with override_settings(DEFAULT_DECOMPOSITION_LINK_TYPE=value):
        assert default_decomposition_link_type() == value


# ---------------------------------------------------------------------------
# Workspace creation
# ---------------------------------------------------------------------------


def test_new_workspace_uses_the_configured_defaults():
    tenant, user = _tenant_and_user()
    ctx = _ctx(tenant.id, user.id)

    with override_settings(
        DEFAULT_TRACE_LINK_TYPE="verifies",
        DEFAULT_DECOMPOSITION_LINK_TYPE="derives-from",
    ), patch("application.workspace_service.ServiceBase._audit"):
        workspace = WorkspaceService().create_workspace(
            ctx, name="Env Default WS", preset="standard"
        )

    assert workspace.default_link_type == "verifies"
    assert workspace.decomposition_link_type == "derives-from"


def test_new_workspace_uses_the_fallbacks_by_default():
    tenant, user = _tenant_and_user()
    ctx = _ctx(tenant.id, user.id)

    with patch("application.workspace_service.ServiceBase._audit"):
        workspace = WorkspaceService().create_workspace(
            ctx, name="Fallback WS", preset="standard"
        )

    assert workspace.default_link_type == "references"
    assert workspace.decomposition_link_type == "decomposes"


def test_explicit_argument_wins_over_the_environment_default():
    tenant, user = _tenant_and_user()
    ctx = _ctx(tenant.id, user.id)

    with override_settings(
        DEFAULT_TRACE_LINK_TYPE="verifies",
        DEFAULT_DECOMPOSITION_LINK_TYPE="derives-from",
    ), patch("application.workspace_service.ServiceBase._audit"):
        workspace = WorkspaceService().create_workspace(
            ctx,
            name="Explicit WS",
            preset="standard",
            default_link_type="references",
            decomposition_link_type="decomposes",
        )

    assert workspace.default_link_type == "references"
    assert workspace.decomposition_link_type == "decomposes"


def test_read_fallback_applies_to_a_blank_column():
    """A workspace row with an empty column reports the env default (#989)."""
    from rest_api.views import _workspace_to_dict

    tenant, _user = _tenant_and_user()
    workspace = Workspace.unscoped.create(
        tenant=tenant,
        name="Blank WS",
        preset={"tier": "standard"},
        default_link_type="",
        decomposition_link_type="",
    )

    with override_settings(
        DEFAULT_TRACE_LINK_TYPE="verifies",
        DEFAULT_DECOMPOSITION_LINK_TYPE="derives-from",
    ):
        payload = _workspace_to_dict(workspace)

    assert payload["default_link_type"] == "verifies"
    assert payload["decomposition_link_type"] == "derives-from"
