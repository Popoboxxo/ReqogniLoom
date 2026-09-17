"""LinkTypeCatalog — global and per-workspace trace-link type definitions.

Inheritance form is **materialized copy**, identical in shape to
``workflow.GlobalWorkflowDefinition`` / ``WorkflowEngineDefinition``: each
workspace keeps its own row, links back to the global template via
``source_global``, and a workspace that has not diverged carries
``is_customized=False`` and mirrors the global ``definition_json``. An admin
edit to a global row propagates into every non-customized derived row (see
``link_types.global_store.GlobalLinkTypeDefinitionStore._propagate``).

Unlike Workflow/AttributeDefinition there is deliberately **no** ``preset``
field: link types are an open, named catalog, not an ``(item_type x preset)``
raster.

The optimistic-lock counter ``version`` is inherited from
``persistence.models.AuditableModel`` — it is deliberately NOT redeclared here
(a local field of the same name clashes with the abstract base).
"""

from __future__ import annotations

from django.db import models

from persistence.models import TenantScopedModel


class GlobalLinkTypeDefinition(TenantScopedModel):
    """Tenant-wide link-type template. Exactly one row per ``(tenant, key)``.

    ``key`` is either one of the eight built-in keys or a tenant-invented one
    (e.g. ``"conflicts-with"``). ``version`` (inherited) is the optimistic-lock
    counter.
    """

    key = models.CharField(max_length=64)
    definition_json = models.JSONField(default=dict)

    class Meta:
        db_table = "lt_global_definition"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "key"], name="uq_lt_global_tenant_key"
            )
        ]

    def __str__(self) -> str:
        return f"GlobalLinkType({self.key}@tenant:{self.tenant_id})"


class WorkspaceLinkTypeDefinition(TenantScopedModel):
    """Materialized per-workspace copy of a link-type definition.

    ``source_global`` uses SET_NULL: deleting a global template must never
    cascade-delete a live workspace override — the provenance link simply
    becomes unknown.
    """

    workspace_id = models.UUIDField(db_index=True)
    key = models.CharField(max_length=64)
    definition_json = models.JSONField(default=dict)
    source_global = models.ForeignKey(
        GlobalLinkTypeDefinition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="derived_definitions",
    )
    is_customized = models.BooleanField(default=False)

    class Meta:
        db_table = "lt_workspace_definition"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "workspace_id", "key"],
                name="uq_lt_ws_tenant_ws_key",
            )
        ]
        indexes = [
            models.Index(fields=["workspace_id", "key"], name="idx_lt_ws_workspace_key")
        ]

    def __str__(self) -> str:
        return f"WorkspaceLinkType({self.key}@{self.workspace_id})"
