"""AttributeDefinition models — global default + per-workspace materialized copy.

Inheritance form is **materialized copy**, deliberately the same pattern as
``workflow.GlobalWorkflowDefinition`` -> ``workflow.WorkflowEngineDefinition``:
each workspace keeps its own full row, so the form load path never diffs JSON
at runtime. An admin edit on the global propagates into every
``is_customized=False`` derived row of the SAME preset (application layer, not
schema) — see ``attribute_definitions.global_definition_store``.

``version`` is NOT declared here: ``TenantScopedModel`` -> ``AuditableModel``
already provides it (optimistic-lock counter). Redeclaring it would be a Django
field clash. The stores bump it explicitly on every persist.
"""
from __future__ import annotations

from django.db import models

from persistence.models import TenantScopedModel

PRESET_MINIMAL = "minimal"
PRESET_STANDARD = "standard"
PRESET_EXTENDED = "extended"

PRESET_CHOICES = [
    (PRESET_MINIMAL, "Minimal"),
    (PRESET_STANDARD, "Standard"),
    (PRESET_EXTENDED, "Extended"),
]


class GlobalAttributeDefinition(TenantScopedModel):
    """Tenant-wide default attribute definition per ``(item_type, preset)``.

    Exactly one row per ``(tenant, item_type, preset)``. ``definition_json`` is
    ``{"attributes": [...]}`` — see ``attribute_definitions.schema`` for the
    entry contract.
    """

    item_type = models.CharField(max_length=128)
    preset = models.CharField(max_length=32, choices=PRESET_CHOICES)
    definition_json = models.JSONField(default=dict)

    class Meta:
        db_table = "ad_global_definition"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "item_type", "preset"],
                name="uq_ad_global_def_tenant_type_preset",
            )
        ]

    def __str__(self) -> str:
        return (
            f"GlobalAttributeDef({self.item_type}/{self.preset}"
            f"@tenant:{self.tenant_id})"
        )


class WorkspaceAttributeDefinition(TenantScopedModel):
    """Per-workspace materialized copy of a global attribute definition.

    ``preset`` is frozen at creation time (spec section 3): a later workspace
    preset switch does not silently re-point this row at another global.

    ``is_customized`` is the cheap on-default/customized signal: ``False``
    mirrors ``source_global``, ``True`` means the workspace has diverged and is
    excluded from global propagation. ``source_global`` is ``SET_NULL`` so
    deleting a global default never cascade-deletes a live override.
    """

    workspace_id = models.UUIDField(db_index=True)
    item_type = models.CharField(max_length=128)
    preset = models.CharField(max_length=32, choices=PRESET_CHOICES)
    definition_json = models.JSONField(default=dict)
    source_global = models.ForeignKey(
        "attribute_definitions.GlobalAttributeDefinition",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="derived_definitions",
    )
    is_customized = models.BooleanField(default=False)

    class Meta:
        db_table = "ad_workspace_definition"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "workspace_id", "item_type"],
                name="uq_ad_ws_def_tenant_ws_type",
            )
        ]
        indexes = [
            models.Index(
                fields=["workspace_id", "item_type"],
                name="idx_ad_ws_def_ws_type",
            )
        ]

    def __str__(self) -> str:
        return f"WorkspaceAttributeDef({self.item_type}@{self.workspace_id})"


__all__ = [
    "GlobalAttributeDefinition",
    "WorkspaceAttributeDefinition",
    "PRESET_CHOICES",
    "PRESET_MINIMAL",
    "PRESET_STANDARD",
    "PRESET_EXTENDED",
]
