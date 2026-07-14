"""COMP-AS-CF CustomFieldService — custom field definitions + values (REQ-066).

Single entry point for the two REST surfaces behind REQ-016:

  * ``CustomFieldDefinitionViewSet`` — workspace-wide field definitions.
  * ``ArtifactCustomFieldValuesView`` — per-artifact field values.

Moves all ORM access out of ``rest_api/views.py`` (Option B, REQ-066). Value
*validation* (type/dropdown/required checks that short-circuit with HTTP error
bodies) stays in the view; this service owns persistence only.

Error mapping (status codes unchanged vs. the former view code):
  * missing workspace / artifact / definition → :class:`NotFoundError` (404)
  * unique-constraint (duplicate definition name) → :class:`ValidationError` (400)

req_id: REQ-066, REQ-016
leaf_id: COMP-AS-CF
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import QuerySet

from auth_tenancy.context import AuthContext
from persistence.models import (
    Artifact,
    CustomFieldDefinition,
    CustomFieldValue,
    Workspace,
)

from application.base import NotFoundError, ServiceBase, ValidationError

# Fields a client may set on a definition (create + patch).
_DEFINITION_FIELDS = ("name", "field_type", "is_required", "options", "order")

_DUPLICATE_NAME_MSG = "A field with this name already exists in the workspace."


class CustomFieldService(ServiceBase):
    """Tenant-scoped CRUD for custom field definitions and values (REQ-066)."""

    # ---- Definitions: read ------------------------------------------------

    def list_definitions(self, ctx: AuthContext, workspace_id: Any) -> QuerySet:
        """Return the workspace's field definitions, ordered by (order, name)."""
        self._set_tenant_context(ctx)
        return CustomFieldDefinition.objects.filter(
            workspace_id=workspace_id
        ).order_by("order", "name")

    def get_definition(
        self, ctx: AuthContext, definition_id: Any
    ) -> CustomFieldDefinition:
        """Return one definition or raise :class:`NotFoundError`."""
        self._set_tenant_context(ctx)
        obj = CustomFieldDefinition.objects.filter(id=definition_id).first()
        if obj is None:
            raise NotFoundError(f"Definition {definition_id} not found")
        return obj

    # ---- Definitions: write ----------------------------------------------

    def create_definition(
        self,
        ctx: AuthContext,
        workspace_id: Any,
        *,
        name: str,
        field_type: str = "text",
        is_required: bool = False,
        options: list | None = None,
        order: int = 0,
    ) -> CustomFieldDefinition:
        """Create a definition. Raises NotFoundError (workspace) / ValidationError."""
        self._set_tenant_context(ctx)
        # Confirm the workspace belongs to the active tenant (scoped manager).
        if not Workspace.objects.filter(id=workspace_id).exists():
            raise NotFoundError("Workspace not found")
        try:
            # atomic so a unique-constraint violation does not poison the
            # surrounding request/test transaction.
            with transaction.atomic():
                return CustomFieldDefinition.objects.create(
                    workspace_id=workspace_id,
                    name=name,
                    field_type=field_type,
                    is_required=is_required,
                    options=options if options is not None else [],
                    order=order,
                    created_by_id=ctx.user_id,
                )
        except IntegrityError as exc:
            raise ValidationError(_DUPLICATE_NAME_MSG) from exc

    def update_definition(
        self, ctx: AuthContext, definition_id: Any, fields: dict[str, Any]
    ) -> CustomFieldDefinition:
        """Apply ``fields`` to a definition, bump version. NotFound/Validation."""
        definition = self.get_definition(ctx, definition_id)
        for attr in _DEFINITION_FIELDS:
            if attr in fields:
                setattr(definition, attr, fields[attr])
        definition.modified_by_id = ctx.user_id
        definition.version += 1
        try:
            with transaction.atomic():
                definition.save()
        except IntegrityError as exc:
            raise ValidationError(_DUPLICATE_NAME_MSG) from exc
        return definition

    def delete_definition(self, ctx: AuthContext, definition_id: Any) -> None:
        """Delete a definition (cascade its values) or raise NotFoundError."""
        definition = self.get_definition(ctx, definition_id)
        definition.delete()

    # ---- Values -----------------------------------------------------------

    def get_artifact_workspace_id(self, ctx: AuthContext, artifact_id: Any) -> str:
        """Return the workspace id owning ``artifact_id`` or raise NotFoundError."""
        self._set_tenant_context(ctx)
        artifact = Artifact.objects.filter(id=artifact_id).first()
        if artifact is None:
            raise NotFoundError("Artifact not found")
        return str(artifact.workspace_id)

    def get_definitions_map(
        self, ctx: AuthContext, workspace_id: Any
    ) -> dict[str, CustomFieldDefinition]:
        """Return a ``{definition_id: definition}`` map for a workspace."""
        self._set_tenant_context(ctx)
        return {
            str(d.id): d
            for d in CustomFieldDefinition.objects.filter(workspace_id=workspace_id)
        }

    def merged_rows(
        self, ctx: AuthContext, workspace_id: Any, artifact_id: Any
    ) -> list[dict]:
        """Return definitions merged with the artifact's current values."""
        self._set_tenant_context(ctx)
        definitions = list(
            CustomFieldDefinition.objects.filter(
                workspace_id=workspace_id
            ).order_by("order", "name")
        )
        values = {
            v.definition_id: v
            for v in CustomFieldValue.objects.filter(artifact_id=artifact_id)
        }
        rows: list[dict] = []
        for d in definitions:
            v = values.get(d.id)
            rows.append(
                {
                    "id": str(v.id) if v else None,
                    "definition_id": str(d.id),
                    "artifact_id": str(artifact_id),
                    "value": v.value if v else "",
                    "name": d.name,
                    "field_type": d.field_type,
                    "is_required": d.is_required,
                    "options": d.options,
                    "order": d.order,
                }
            )
        return rows

    def apply_values(
        self,
        ctx: AuthContext,
        artifact_id: Any,
        operations: list[tuple[str, str]],
    ) -> None:
        """Persist a batch of ``(definition_id, value)`` operations atomically.

        An empty ``value`` deletes any existing value row; a non-empty value is
        upserted. All operations run in a single transaction (all-or-nothing).
        Callers must validate the operations *before* calling this method.
        """
        self._set_tenant_context(ctx)
        with transaction.atomic():
            for definition_id, value in operations:
                if value == "":
                    CustomFieldValue.objects.filter(
                        definition_id=definition_id, artifact_id=artifact_id
                    ).delete()
                else:
                    # ``update_or_create`` bypasses TenantManager.create, so the
                    # tenant FK must be supplied explicitly here.
                    CustomFieldValue.objects.update_or_create(
                        definition_id=definition_id,
                        artifact_id=artifact_id,
                        defaults={"value": value, "tenant_id": ctx.tenant_id},
                    )


__all__ = ["CustomFieldService"]
