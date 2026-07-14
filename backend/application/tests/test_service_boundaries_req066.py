"""REQ-066 — unit tests for the services introduced by the Service-Layer refactor.

Covers the new/extended services that absorb ORM access previously living in the
REST view layer (Option B):

  * AttributeVisibilityConfigService (new)
  * CustomFieldService (new)
  * SettingsService (new)
  * WorkspaceService.update_metadata / switch_preset_tier (extended)

Each service is checked for its core CRUD behaviour, tenant isolation and the
error mapping (NotFoundError / ValidationError) the REST layer relies on to
preserve HTTP status codes.

req_id: REQ-066
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from application.attribute_visibility_service import AttributeVisibilityConfigService
from application.base import NotFoundError, ValidationError
from application.custom_field_service import CustomFieldService
from application.settings_service import SettingsService
from application.workspace_service import WorkspaceService
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    Artifact,
    AttributeVisibilityConfig,
    CustomFieldDefinition,
    CustomFieldValue,
    Tenant,
    User,
    Workspace,
)

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
# AttributeVisibilityConfigService
# ---------------------------------------------------------------------------


class TestAttributeVisibilityConfigService:
    def test_create_and_list(self):
        tenant, user = _tenant_user("avc")
        ctx = _make_ctx(tenant_id=tenant.id, user_id=user.id)
        svc = AttributeVisibilityConfigService()

        cfg = svc.create_config(
            ctx, entity_type="Requirement", attribute_name="moscow_priority"
        )
        assert cfg.created_by_id == user.id
        assert cfg.version == 1

        rows = list(svc.list_configs(ctx))
        assert [c.id for c in rows] == [cfg.id]

    def test_update_bumps_version(self):
        tenant, user = _tenant_user("avc")
        ctx = _make_ctx(tenant_id=tenant.id, user_id=user.id)
        svc = AttributeVisibilityConfigService()
        cfg = svc.create_config(ctx, entity_type="Requirement", attribute_name="x")

        updated = svc.update_config(ctx, cfg.id, is_visible=False, is_required=True)
        assert updated.is_visible is False
        assert updated.is_required is True
        assert updated.version == 2
        assert updated.modified_by_id == user.id

    def test_delete(self):
        tenant, user = _tenant_user("avc")
        ctx = _make_ctx(tenant_id=tenant.id, user_id=user.id)
        svc = AttributeVisibilityConfigService()
        cfg = svc.create_config(ctx, entity_type="Requirement", attribute_name="x")

        svc.delete_config(ctx, cfg.id)
        assert not AttributeVisibilityConfig.unscoped.filter(id=cfg.id).exists()

    def test_get_missing_raises_not_found(self):
        tenant, user = _tenant_user("avc")
        ctx = _make_ctx(tenant_id=tenant.id, user_id=user.id)
        svc = AttributeVisibilityConfigService()
        with pytest.raises(NotFoundError):
            svc.get_config(ctx, uuid.uuid4())

    def test_tenant_isolation(self):
        t1, u1 = _tenant_user("avc1")
        t2, u2 = _tenant_user("avc2")
        svc = AttributeVisibilityConfigService()
        svc.create_config(
            _make_ctx(tenant_id=t1.id, user_id=u1.id),
            entity_type="Requirement",
            attribute_name="a",
        )

        ctx2 = _make_ctx(tenant_id=t2.id, user_id=u2.id)
        assert list(svc.list_configs(ctx2)) == []

    def test_bulk_upsert_creates_then_updates(self):
        tenant, user = _tenant_user("avc")
        ctx = _make_ctx(tenant_id=tenant.id, user_id=user.id)
        svc = AttributeVisibilityConfigService()

        first = svc.bulk_upsert(
            ctx,
            [{"entity_type": "Requirement", "attribute_name": "p", "is_visible": True}],
        )
        assert len(first) == 1 and first[0].version == 1

        second = svc.bulk_upsert(
            ctx,
            [
                {
                    "entity_type": "Requirement",
                    "attribute_name": "p",
                    "is_visible": False,
                }
            ],
        )
        assert second[0].id == first[0].id
        assert second[0].is_visible is False
        assert second[0].version == 2


# ---------------------------------------------------------------------------
# CustomFieldService
# ---------------------------------------------------------------------------


class TestCustomFieldService:
    def _env(self):
        tenant, user = _tenant_user("cf")
        set_request_tenant(tenant.id)
        ws = Workspace.objects.create(tenant=tenant, name="WS", preset={"tier": "standard"})
        artifact = Artifact.objects.create(
            tenant=tenant, workspace=ws, artifact_type="requirement"
        )
        ctx = _make_ctx(tenant_id=tenant.id, user_id=user.id)
        return tenant, user, ws, artifact, ctx

    def test_create_definition(self):
        tenant, user, ws, artifact, ctx = self._env()
        try:
            svc = CustomFieldService()
            d = svc.create_definition(ctx, ws.id, name="Priority", field_type="text")
            assert d.name == "Priority"
            assert d.created_by_id == user.id
        finally:
            clear_request_tenant()

    def test_duplicate_name_raises_validation(self):
        tenant, user, ws, artifact, ctx = self._env()
        try:
            svc = CustomFieldService()
            svc.create_definition(ctx, ws.id, name="Dup")
            with pytest.raises(ValidationError):
                svc.create_definition(ctx, ws.id, name="Dup")
        finally:
            clear_request_tenant()

    def test_missing_workspace_raises_not_found(self):
        tenant, user, ws, artifact, ctx = self._env()
        try:
            svc = CustomFieldService()
            with pytest.raises(NotFoundError):
                svc.create_definition(ctx, uuid.uuid4(), name="X")
        finally:
            clear_request_tenant()

    def test_update_and_delete_definition(self):
        tenant, user, ws, artifact, ctx = self._env()
        try:
            svc = CustomFieldService()
            d = svc.create_definition(ctx, ws.id, name="Temp")
            upd = svc.update_definition(ctx, d.id, {"name": "Renamed", "is_required": True})
            assert upd.name == "Renamed" and upd.is_required is True
            assert upd.version == d.version + 1

            svc.delete_definition(ctx, d.id)
            assert not CustomFieldDefinition.unscoped.filter(id=d.id).exists()
        finally:
            clear_request_tenant()

    def test_values_apply_and_merged_rows(self):
        tenant, user, ws, artifact, ctx = self._env()
        try:
            svc = CustomFieldService()
            d = svc.create_definition(ctx, ws.id, name="Note")

            svc.apply_values(ctx, artifact.id, [(str(d.id), "hello")])
            rows = svc.merged_rows(ctx, ws.id, artifact.id)
            assert rows[0]["value"] == "hello"

            # Empty value clears the stored row.
            svc.apply_values(ctx, artifact.id, [(str(d.id), "")])
            assert not CustomFieldValue.unscoped.filter(
                definition_id=d.id, artifact_id=artifact.id
            ).exists()
        finally:
            clear_request_tenant()

    def test_artifact_missing_raises_not_found(self):
        tenant, user, ws, artifact, ctx = self._env()
        try:
            svc = CustomFieldService()
            with pytest.raises(NotFoundError):
                svc.get_artifact_workspace_id(ctx, uuid.uuid4())
        finally:
            clear_request_tenant()


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

    def test_switch_preset_tier_invalid_raises_validation(self):
        tenant, user = _tenant_user("ws")
        ws = _workspace(tenant)
        ctx = _make_ctx(tenant_id=tenant.id, user_id=user.id)
        with pytest.raises(ValidationError):
            WorkspaceService().switch_preset_tier(ctx, ws.id, "bogus")
