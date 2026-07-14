"""COMP-AS-AVC AttributeVisibilityConfigService — field visibility CRUD (REQ-066).

Single entry point for the admin-managed ``AttributeVisibilityConfig`` rows
behind ``/api/v1/attribute-visibility-config/``. Moves the CRUD ORM access out of
``rest_api/views.py`` (Option B, REQ-066) and replaces the former broken
``persistence.services.RequirementService`` workaround import.

All writes are tenant-scoped via ``ctx.tenant_id``; the ``created_by`` /
``modified_by`` audit columns are populated from ``ctx.user_id`` (the previous
view wrongly assigned a non-existent ``ctx.user`` attribute — see REQ-066).

req_id: REQ-066, REQ-L1-058
leaf_id: COMP-AS-AVC
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import QuerySet

from auth_tenancy.context import AuthContext
from persistence.models import AttributeVisibilityConfig

from application.base import NotFoundError, ServiceBase


class AttributeVisibilityConfigService(ServiceBase):
    """Tenant-scoped CRUD for AttributeVisibilityConfig (REQ-066)."""

    # ---- Read -------------------------------------------------------------

    def list_configs(self, ctx: AuthContext) -> QuerySet:
        """Return all visibility configs for the active tenant, ordered stably.

        Returns a lazy ``QuerySet`` so the caller may paginate without
        materialising the full result set.
        """
        self._set_tenant_context(ctx)
        return AttributeVisibilityConfig.objects.filter(
            tenant_id=ctx.tenant_id
        ).order_by("entity_type", "attribute_name")

    def get_config(
        self, ctx: AuthContext, config_id: UUID
    ) -> AttributeVisibilityConfig:
        """Return a single config or raise :class:`NotFoundError`."""
        self._set_tenant_context(ctx)
        obj = AttributeVisibilityConfig.objects.filter(
            id=config_id, tenant_id=ctx.tenant_id
        ).first()
        if obj is None:
            raise NotFoundError(f"Config {config_id} not found")
        return obj

    # ---- Write ------------------------------------------------------------

    def create_config(
        self,
        ctx: AuthContext,
        *,
        entity_type: str,
        attribute_name: str,
        is_visible: bool = True,
        is_required: bool = False,
    ) -> AttributeVisibilityConfig:
        """Create a new visibility config for the active tenant."""
        self._set_tenant_context(ctx)
        return AttributeVisibilityConfig.objects.create(
            tenant_id=ctx.tenant_id,
            entity_type=entity_type,
            attribute_name=attribute_name,
            is_visible=is_visible,
            is_required=is_required,
            created_by_id=ctx.user_id,
        )

    def update_config(
        self,
        ctx: AuthContext,
        config_id: UUID,
        *,
        is_visible: bool | None = None,
        is_required: bool | None = None,
    ) -> AttributeVisibilityConfig:
        """Patch ``is_visible`` / ``is_required`` and bump the version counter."""
        obj = self.get_config(ctx, config_id)
        if is_visible is not None:
            obj.is_visible = is_visible
        if is_required is not None:
            obj.is_required = is_required
        obj.modified_by_id = ctx.user_id
        obj.version += 1
        obj.save()
        return obj

    def delete_config(self, ctx: AuthContext, config_id: UUID) -> None:
        """Delete a config or raise :class:`NotFoundError`."""
        obj = self.get_config(ctx, config_id)
        obj.delete()

    def bulk_upsert(
        self, ctx: AuthContext, items: list[dict[str, Any]]
    ) -> list[AttributeVisibilityConfig]:
        """Upsert a batch of configs in one transaction.

        Each item is keyed by ``(entity_type, attribute_name)`` within the active
        tenant. Existing rows have their visibility flags updated and version
        bumped; new rows are created with ``created_by`` set.
        """
        self._set_tenant_context(ctx)
        results: list[AttributeVisibilityConfig] = []
        with transaction.atomic():
            for item in items:
                config, created = AttributeVisibilityConfig.objects.update_or_create(
                    tenant_id=ctx.tenant_id,
                    entity_type=item["entity_type"],
                    attribute_name=item["attribute_name"],
                    defaults={
                        "is_visible": item.get("is_visible", True),
                        "is_required": item.get("is_required", False),
                    },
                )
                if created:
                    config.created_by_id = ctx.user_id
                else:
                    config.modified_by_id = ctx.user_id
                    config.version += 1
                config.save()
                results.append(config)
        return results


__all__ = ["AttributeVisibilityConfigService"]
