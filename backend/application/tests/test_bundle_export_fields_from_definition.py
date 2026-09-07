"""Bundle export field list resolved from export=true (spec section 7).

Deviation from the plan brief (Task 14 self-certification, see progress.md):
the brief's literal test file imports a nonexistent ``RequirementBundleService``
and its own ``resolve_export_fields`` snippet drops 7 Requirement columns
(id/workspace_id/version/created_at/modified_at/suspect/lifecycle_status) that
``bootstrap_attribute_definitions.EXCLUDED_MODEL_FIELDS`` deliberately excludes
from ever becoming an attribute -- proven live against a real
``bootstrap_attribute_definitions`` run (see the "real bootstrap" tests below).
Fixed both: the real class is ``RequirementBundleQueryService``, and
``resolve_export_fields`` unions ``_SYSTEM_EXPORT_FIELDS`` into every mode.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.base import ValidationError
from application.requirement_bundle_service import (
    REQUIREMENT_ALL_FIELDS,
    RequirementBundleQueryService,
)

pytestmark = pytest.mark.django_db


def _attr(name, export=True, visible=True):
    return {
        "name": name, "kind": "core", "type": "text", "export": export,
        "visible": visible, "section": "general", "order": 0,
    }


@pytest.fixture
def service() -> RequirementBundleQueryService:
    return RequirementBundleQueryService()


# ---------------------------------------------------------------------------
# Mocked (fast) — mirrors the plan brief's own coverage
# ---------------------------------------------------------------------------


def test_all_mode_uses_the_export_flagged_attributes(service) -> None:
    ctx, workspace_id = MagicMock(), uuid.uuid4()
    with patch(
        "application.requirement_bundle_service.AttributeDefinitionService"
    ) as definition:
        definition.return_value.export_attributes.return_value = [
            _attr("title"), _attr("uid")
        ]
        fields = service.resolve_export_fields(ctx, workspace_id, "all", None)
    # title/uid come from the definition; the rest are the system columns no
    # definition can ever carry (see _SYSTEM_EXPORT_FIELDS).
    assert fields == {"title", "uid"} | {
        "id", "workspace_id", "version", "created_at", "modified_at",
        "suspect", "lifecycle_status",
    }


def test_visible_mode_drops_invisible_attributes(service) -> None:
    ctx, workspace_id = MagicMock(), uuid.uuid4()
    with patch(
        "application.requirement_bundle_service.AttributeDefinitionService"
    ) as definition:
        definition.return_value.export_attributes.return_value = [
            _attr("title"), _attr("secret", visible=False)
        ]
        fields = service.resolve_export_fields(ctx, workspace_id, "visible", None)
    assert "secret" not in fields
    assert "title" in fields


def test_custom_mode_rejects_a_field_outside_the_definition(service) -> None:
    ctx, workspace_id = MagicMock(), uuid.uuid4()
    with patch(
        "application.requirement_bundle_service.AttributeDefinitionService"
    ) as definition:
        definition.return_value.export_attributes.return_value = [_attr("title")]
        with pytest.raises(ValidationError) as exc:
            service.resolve_export_fields(ctx, workspace_id, "custom", ["title", "nope"])
    assert "nope" in str(exc.value)


def test_custom_mode_accepts_a_system_column_even_when_absent_from_the_definition(
    service,
) -> None:
    """id/created_at/... are never attributes (see _SYSTEM_EXPORT_FIELDS) but
    must stay selectable in filter_mode='custom' — pre-Task-14 behaviour."""
    ctx, workspace_id = MagicMock(), uuid.uuid4()
    with patch(
        "application.requirement_bundle_service.AttributeDefinitionService"
    ) as definition:
        definition.return_value.export_attributes.return_value = [_attr("title")]
        fields = service.resolve_export_fields(
            ctx, workspace_id, "custom", ["title", "created_at"]
        )
    assert fields == {"title", "created_at"}


def test_without_a_definition_the_hardcoded_list_is_the_fallback(service) -> None:
    from application.attribute_definition_service import AttributeDefinitionNotFound

    ctx, workspace_id = MagicMock(), uuid.uuid4()
    with patch(
        "application.requirement_bundle_service.AttributeDefinitionService"
    ) as definition:
        definition.return_value.export_attributes.side_effect = (
            AttributeDefinitionNotFound("x")
        )
        fields = service.resolve_export_fields(ctx, workspace_id, "all", None)
    assert fields == set(REQUIREMENT_ALL_FIELDS)


# ---------------------------------------------------------------------------
# Real bootstrap (non-mocked) — every workspace is effectively bootstrapped
# in production (SDD ledger's corrected-deployment-state finding), so this is
# the path that actually runs live. Mirrors the pattern established in
# test_interview_protocol_from_definition.py's
# test_full_interview_cycle_against_a_bootstrapped_definition_preserves_description.
# ---------------------------------------------------------------------------


def _bootstrap_tenant_workspace_ctx():
    from django.core.management import call_command

    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.middleware import clear_request_tenant, set_request_tenant
    from persistence.models import Tenant, User, Workspace

    tenant = Tenant.objects.create(name="Bundle Export Fields Test", is_active=True)
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name="ws", preset={"name": "standard"}
        )
        user = User.objects.create(
            username="bundlefieldsuser", email="bundlefields@t.test", tenant=tenant
        )
    finally:
        clear_request_tenant()

    # Same reasoning as the interview-protocol precedent: the command arms and
    # clears its own tenant context per tenant, so it must run outside the
    # block above rather than nested in it.
    call_command("bootstrap_attribute_definitions", tenant=str(tenant.id))

    set_request_tenant(tenant.id)
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )
    return ctx, workspace


def test_real_bootstrap_all_mode_matches_the_pre_task14_field_set() -> None:
    """Regression proof for the brief bug found live (see module docstring):
    a freshly bootstrapped, unmodified Requirement definition's "all" mode
    must still export every REQUIREMENT_ALL_FIELDS name — not just the 10
    admin-configurable ``export=true`` attributes bootstrap seeds, which
    silently drop id/workspace_id/version/created_at/modified_at/suspect/
    lifecycle_status (proven via a throwaway probe against this exact
    command before this fix: export_attributes returned only 10 of 17 names).
    """
    ctx, workspace = _bootstrap_tenant_workspace_ctx()
    fields = RequirementBundleQueryService().resolve_export_fields(
        ctx, workspace.id, "all", None
    )
    assert fields == set(REQUIREMENT_ALL_FIELDS)


def test_real_bootstrap_custom_mode_still_accepts_a_system_column() -> None:
    """Same regression, exercised through the "custom" 400-path: before the
    fix this raised ValidationError("Unknown field(s) ... created_at") for
    every already-bootstrapped workspace, permanently, because created_at
    can never be an attribute at all."""
    ctx, workspace = _bootstrap_tenant_workspace_ctx()
    fields = RequirementBundleQueryService().resolve_export_fields(
        ctx, workspace.id, "custom", ["created_at", "title"]
    )
    assert fields == {"created_at", "title"}


def test_real_bootstrap_visible_mode_reflects_an_admin_hidden_attribute() -> None:
    """Proves the definition-driven "visible" filtering is genuinely wired
    end to end (not just accepted by a mock): admin hides one real,
    export=true attribute via the same AttributeDefinitionService path REST/
    MCP use, and "visible" mode must drop it while "all" keeps it."""
    from application.attribute_definition_service import AttributeDefinitionService

    ctx, workspace = _bootstrap_tenant_workspace_ctx()
    admin_ctx = ctx.__class__(
        user_id=ctx.user_id,
        tenant_id=ctx.tenant_id,
        active_roles=("admin",),
        auth_method=ctx.auth_method,
        api_key_id=None,
    )
    definition_service = AttributeDefinitionService()
    resolved = definition_service.resolve(admin_ctx, "Requirement", workspace.id)
    attributes = resolved["attributes"]
    for attribute in attributes:
        if attribute["name"] == "uid":
            attribute["visible"] = False
    definition_service.update_workspace(admin_ctx, "Requirement", workspace.id, attributes)

    svc = RequirementBundleQueryService()
    visible_fields = svc.resolve_export_fields(ctx, workspace.id, "visible", None)
    all_fields = svc.resolve_export_fields(ctx, workspace.id, "all", None)

    assert "uid" not in visible_fields
    assert "uid" in all_fields
