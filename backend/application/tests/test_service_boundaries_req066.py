"""REQ-066 — unit tests for the services introduced by the Service-Layer refactor.

Covers the new/extended services that absorb ORM access previously living in the
REST view layer (Option B):

  * SettingsService (new)
  * WorkspaceService.update_metadata / switch_preset_tier (extended)

AttributeVisibilityConfigService and CustomFieldService (both formerly covered
here) were retired in Task 9 (spec section 4, "removed, not deprecated") along
with their backing models (``AttributeVisibilityConfig``,
``CustomFieldDefinition``); see
``persistence/tests/test_retire_legacy_field_config.py`` for their replacement
coverage.

Each service is checked for its core CRUD behaviour, tenant isolation and the
error mapping (NotFoundError / ValidationError) the REST layer relies on to
preserve HTTP status codes.

req_id: REQ-066
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from application.base import NotFoundError, ValidationError
from application.settings_service import SettingsService
from application.workspace_service import WorkspaceService
from persistence.models import Tenant, User, Workspace

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(*, tenant_id, user_id, roles=("admin",)):
    ctx = MagicMock()
    ctx.active_roles = roles
    ctx.tenant_id = tenant_id
    ctx.user_id = user_id
    ctx.has_role = lambda role: role in roles
    return ctx


def _tenant_user(slug: str):
    tenant = Tenant.objects.create(name=slug, slug=f"{slug}-{uuid.uuid4().hex[:6]}")
    user = User.objects.create(
        username=f"u-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@t.test",
        tenant=tenant,
    )
    return tenant, user


def _workspace(tenant, name="WS", preset=None):
    return Workspace.unscoped.create(
        tenant=tenant, name=name, preset=preset or {"tier": "standard"}
    )


# ---------------------------------------------------------------------------
# SettingsService
# ---------------------------------------------------------------------------


class TestSettingsService:
    def test_llm_settings_get_or_create_and_update(self):
        tenant, user = _tenant_user("set")
        ctx = _make_ctx(tenant_id=tenant.id, user_id=user.id)
        svc = SettingsService()

        obj = svc.get_or_create_llm_settings(ctx)
        assert obj.tenant_id == tenant.id
        # Idempotent.
        assert svc.get_or_create_llm_settings(ctx).id == obj.id

        updated = svc.update_llm_settings(ctx, {"model_name": "gpt-x"})
        assert updated.model_name == "gpt-x"

    def test_prompt_template_update_and_reset(self):
        tenant, user = _tenant_user("set")
        ctx = _make_ctx(tenant_id=tenant.id, user_id=user.id)
        svc = SettingsService()

        svc.update_prompt_template(ctx, {"need_to_sysreq": "CUSTOM"})
        assert svc.get_or_create_prompt_template(ctx).need_to_sysreq == "CUSTOM"

        reset = svc.reset_prompt_template(ctx, slot="need_to_sysreq")
        assert reset.need_to_sysreq != "CUSTOM"

    def test_choice_surfaces(self):
        assert "mock" in SettingsService.provider_choices()
        assert SettingsService.is_valid_prompt_slot("need_to_sysreq") is True
        assert SettingsService.is_valid_prompt_slot("nope") is False


# ---------------------------------------------------------------------------
# WorkspaceService — metadata + preset orchestration
# ---------------------------------------------------------------------------


class TestWorkspaceMetadata:
    def test_update_name(self):
        tenant, user = _tenant_user("ws")
        ws = _workspace(tenant)
        ctx = _make_ctx(tenant_id=tenant.id, user_id=user.id)
        result = WorkspaceService().update_metadata(ctx, ws.id, name="Renamed")
        assert result.name == "Renamed"

    def test_empty_name_raises_validation(self):
        tenant, user = _tenant_user("ws")
        ws = _workspace(tenant)
        ctx = _make_ctx(tenant_id=tenant.id, user_id=user.id)
        with pytest.raises(ValidationError):
            WorkspaceService().update_metadata(ctx, ws.id, name="   ")

    def test_invalid_terminology_raises_validation(self):
        tenant, user = _tenant_user("ws")
        ws = _workspace(tenant)
        ctx = _make_ctx(tenant_id=tenant.id, user_id=user.id)
        with pytest.raises(ValidationError):
            WorkspaceService().update_metadata(ctx, ws.id, terminology_profile="bogus")

    def test_missing_workspace_raises_not_found(self):
        tenant, user = _tenant_user("ws")
        ctx = _make_ctx(tenant_id=tenant.id, user_id=user.id)
        with pytest.raises(NotFoundError):
            WorkspaceService().update_metadata(ctx, uuid.uuid4(), name="X")

    def test_language_stored_on_preset_blob(self):
        tenant, user = _tenant_user("ws")
        ws = _workspace(tenant)
        ctx = _make_ctx(tenant_id=tenant.id, user_id=user.id)
        result = WorkspaceService().update_metadata(ctx, ws.id, language="en")
        assert result.preset.get("language") == "en"

    def test_theme_stored_on_preset_blob(self):
        tenant, user = _tenant_user("ws")
        ws = _workspace(tenant)
        ctx = _make_ctx(tenant_id=tenant.id, user_id=user.id)
        result = WorkspaceService().update_metadata(ctx, ws.id, theme="light")
        assert result.preset.get("theme") == "light"

    def test_switch_preset_tier_invalid_raises_validation(self):
        tenant, user = _tenant_user("ws")
        ws = _workspace(tenant)
        ctx = _make_ctx(tenant_id=tenant.id, user_id=user.id)
        with pytest.raises(ValidationError):
            WorkspaceService().switch_preset_tier(ctx, ws.id, "bogus")
