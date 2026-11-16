"""Server-side table query over the filter DSL (Tabellenansicht S1, Task 1.4).

One read service for the artifact table — the REST route
(``GET /api/v1/artifacts/table/``), the saved-view ``apply`` path and the
Dokumentensicht's ``render`` all go through here, so the row shape, the
visibility rules and the query count cannot drift between them.

Layering (ADR-01): this is a Layer-2 service. ``rest_api/table_views.py`` holds
no ORM line; it paginates the queryset this module returns and hands the page to
:meth:`TableQueryService.serialize_rows`.

Row shape (frozen, spec §4.1)::

    {"id": "<entity id>", "artifact_id": "<pl_artifact id>",
     "item_type": "Requirement", "version": 3,
     "values": {"<attribute>": <json primitive>, ...},
     "locked": {"state": "<state name>"} | null}

``id`` is the typed entity id (Requirement/Adr/...), ``artifact_id`` the backing
``pl_artifact`` id a bulk write addresses, ``version`` the entity's optimistic
lock counter.

Visibility (plan Review Focus 5)
--------------------------------
* RBAC first: no ``Operation.READ`` for the caller's roles → 403.
* Item-level rules restrict, they never broaden. An explicit ``none`` rule
  hides the row **inside the queryset**, so ``count`` cannot leak its
  existence. Precedence mirrors
  :meth:`auth_tenancy.services.item_permission.ItemPermissionService.check_permission`:
  an artifact-scoped rule overrides the workspace-wide rule, a rule without an
  artifact applies to the whole workspace, and ``read``/``write`` never hide.
  Rules are per user — there is no role-scoped rule (``auth_tenancy/models.py``),
  so only the caller's own rows are consulted.

Outdated rows are hidden by default (same contract as every list endpoint) and
surfaced with ``include_deleted=True``.

Fallback attribute list
-----------------------
The filter DSL validates against the resolved attribute definition. A workspace
whose definition was never bootstrapped has none
(``AttributeDefinitionNotFound`` — the bootstrap is a rollout step, not a
request-time guarantee), and answering 400 for every table read there would be
worse than serving the model's own columns. That case falls back to
:data:`BUILTIN_ATTRIBUTES`, the type's core columns plus the shared system
fields — the same list the UI renders before a definition arrives. The
definition, when present, stays authoritative.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.core.exceptions import FieldDoesNotExist
from django.db.models import F, Q, QuerySet

from application.artifact_attribute_gateway import (
    artifact_system_fields,
    entity_carrier_fields,
)
from application.attribute_definition_service import AttributeDefinitionService
from application.base import ServiceBase, ValidationError
from application.permissions import assert_read_permission
from application.table_filter_dsl import (
    TABLE_ITEM_TYPES,
    compile_filters,
    compile_sort,
)
from application.workspace_lookup import ENTITY_SPECS, import_entity_model
from auth_tenancy.context import AuthContext

logger = logging.getLogger(__name__)

__all__ = [
    "BUILTIN_ATTRIBUTES",
    "DEFAULT_ORDER",
    "TABLE_ITEM_TYPES",
    "TableQueryService",
]

#: Default row order. Matches ``RequirementService.list_requirements``: the
#: persistent sibling key first (``sort_key`` is NULL for rows created before
#: the #1670 P1 backfill, those sort last), then creation, then the uuid so
#: offset pagination stays deterministic.
DEFAULT_ORDER: tuple[Any, ...] = (
    F("artifact__sort_key").asc(nulls_last=True),
    "created_at",
    "id",
)


def _attribute(
    name: str,
    value_type: str,
    *,
    kind: str = "core",
    editable: Any = True,
) -> dict[str, Any]:
    return {
        "name": name,
        "kind": kind,
        "type": value_type,
        "visible": True,
        "editable": editable,
    }


def _system_attributes() -> tuple[dict[str, Any], ...]:
    return (
        _attribute("owner", "actor"),
        _attribute("reporter", "actor"),
        _attribute("priority", "enum"),
        _attribute("status", "enum", editable="workflow"),
    )


#: Core attribute list per item type, used only when the workspace has no
#: resolved definition (see the module docstring).
BUILTIN_ATTRIBUTES: dict[str, tuple[dict[str, Any], ...]] = {
    "Requirement": (
        _attribute("uid", "text"),
        _attribute("title", "text"),
        _attribute("description", "textarea"),
        _attribute("acceptance_criteria", "textarea"),
        _attribute("rationale", "textarea"),
        _attribute("source", "textarea"),
        _attribute("category", "text"),
        _attribute("type", "text"),
        _attribute("complexity_fibonacci", "number"),
        _attribute("verification_method", "text"),
        _attribute("level", "number"),
        *_system_attributes(),
    ),
    "StakeholderNeed": (
        _attribute("uid", "text"),
        _attribute("title", "text"),
        _attribute("description", "textarea"),
        _attribute("category", "text"),
        _attribute("moscow_priority", "enum"),
        *_system_attributes(),
    ),
    "ArchitectureElement": (
        _attribute("uid", "text"),
        _attribute("title", "text"),
        _attribute("description", "textarea"),
        _attribute("element_type", "enum"),
        _attribute("asil_level", "enum"),
        _attribute("make_or_buy", "enum"),
        *_system_attributes(),
    ),
    "TestCase": (
        _attribute("uid", "text"),
        _attribute("title", "text"),
        _attribute("description", "textarea"),
        _attribute("steps", "widget"),
        _attribute("test_type", "enum"),
        _attribute("scenario_kind", "enum"),
        *_system_attributes(),
    ),
    "Adr": (
        _attribute("uid", "text"),
        _attribute("title", "text"),
        _attribute("description", "textarea"),
        _attribute("context", "textarea"),
        _attribute("decision", "textarea"),
        _attribute("consequences", "textarea"),
        _attribute("deciders", "actor"),
        *_system_attributes(),
    ),
    "Risk": (
        _attribute("uid", "text"),
        _attribute("title", "text"),
        _attribute("description", "textarea"),
        _attribute("probability", "enum"),
        _attribute("impact", "enum"),
        _attribute("category", "text"),
        _attribute("mitigation_strategy", "textarea"),
        _attribute("detection", "number"),
        _attribute("severity", "enum"),
        _attribute("risk_score", "number"),
        *_system_attributes(),
    ),
    "Issue": (
        _attribute("uid", "text"),
        _attribute("title", "text"),
        _attribute("description", "textarea"),
        _attribute("severity", "enum"),
        _attribute("category", "text"),
        _attribute("due_date", "date"),
        _attribute("tags", "widget"),
        *_system_attributes(),
    ),
    "GlossaryTerm": (
        _attribute("term", "text"),
        _attribute("definition", "textarea"),
        _attribute("synonyms", "widget"),
        _attribute("abbreviation", "text"),
        _attribute("uid", "text"),
        *_system_attributes(),
    ),
}

#: Attributes whose value lives on the Artifact row, not on the entity.
_ARTIFACT_VALUE_NAMES: frozenset[str] = frozenset(
    {"owner", "reporter", "priority", "status", "stakeholder"}
)


def clean_item_type(item_type: Any) -> str:
    """Validate *item_type* against the table registry."""
    if not isinstance(item_type, str) or item_type not in TABLE_ITEM_TYPES:
        known = ", ".join(sorted(TABLE_ITEM_TYPES))
        raise ValidationError(
            f"Unknown item_type {item_type!r}: the table covers {known}"
        )
    return item_type


class TableQueryService(ServiceBase):
    """Read the artifact table: columns, queryset, serialised rows."""

    # ------------------------------------------------------------------
    # Attributes
    # ------------------------------------------------------------------

    def attributes(
        self, ctx: AuthContext, workspace_id: UUID, item_type: str
    ) -> list[dict[str, Any]]:
        """Return the attribute list the DSL validates against.

        The resolved workspace definition when one exists (the DSL then honours
        ``visible``/``editable``/``kind`` exactly as the form does), else
        :data:`BUILTIN_ATTRIBUTES` for the type.

        There is no role-specific field hiding: ``audience`` is presentational
        (plan O12), so every caller sees the same attribute set.
        """
        item_type = clean_item_type(item_type)
        self._set_tenant_context(ctx)
        from attribute_definitions.global_definition_store import (
            AttributeDefinitionNotFound,
        )
        from attribute_definitions.schema import AttributeSchemaError

        try:
            definition = AttributeDefinitionService().resolve(
                ctx, item_type, workspace_id
            )
        except (AttributeDefinitionNotFound, AttributeSchemaError):
            logger.info(
                "No attribute definition for %s in workspace %s; falling back "
                "to the built-in table attributes",
                item_type,
                workspace_id,
            )
            return [dict(attribute) for attribute in BUILTIN_ATTRIBUTES[item_type]]
        attributes = definition.get("attributes") or []
        if not attributes:
            return [dict(attribute) for attribute in BUILTIN_ATTRIBUTES[item_type]]
        return list(attributes)

    def columns(
        self, ctx: AuthContext, workspace_id: UUID, item_type: str
    ) -> list[dict[str, Any]]:
        """Return the visible attributes (the table's column candidates)."""
        return [
            attribute
            for attribute in self.attributes(ctx, workspace_id, item_type)
            if attribute.get("visible", True)
        ]

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(
        self,
        ctx: AuthContext,
        workspace_id: UUID,
        item_type: str,
        filters: Mapping[str, Any] | None = None,
        sort: Sequence[Mapping[str, Any]] | None = None,
        *,
        include_deleted: bool = False,
    ) -> QuerySet:
        """Return the lazy entity queryset for one table page.

        Args:
            ctx: Caller (roles decide via ``Operation.READ``).
            workspace_id: Workspace whose rows are read.
            item_type: One of the eight table types.
            filters: Filter DSL document (see :mod:`application.table_filter_dsl`).
            sort: Sort document; empty means :data:`DEFAULT_ORDER`.
            include_deleted: Surface soft-deleted rows too.

        Raises:
            ValidationError: unsupported ``item_type``/field/operator/value.
            PermissionDeniedError: the caller holds no read role.

        The queryset is deliberately lazy: the paginator slices it, so no
        ``list()`` over the workspace happens here.
        """
        self._set_tenant_context(ctx)
        assert_read_permission(ctx, what="reading the artifact table")
        item_type = clean_item_type(item_type)
        model = self._model(item_type)
        attributes = self.attributes(ctx, workspace_id, item_type)

        qs = (
            model.objects.select_related(
                "artifact", "artifact__owner", "artifact__reporter"
            )
            .filter(**self._workspace_lookup(model, workspace_id))
            .filter(
                compile_filters(
                    item_type,
                    attributes,
                    filters,
                    tenant_id=ctx.tenant_id,
                    workspace_id=workspace_id,
                )
            )
            .filter(self._item_read_rule_q(ctx, workspace_id))
        )
        if not include_deleted:
            from workflow import state_reader

            qs = qs.exclude(
                id__in=state_reader.outdated_ids(
                    item_type, tenant_id=ctx.tenant_id
                )
            )

        prefetches = self._carrier_prefetches(model, attributes)
        if prefetches:
            qs = qs.prefetch_related(*prefetches)

        terms = compile_sort(item_type, attributes, sort)
        return qs.order_by(*(terms or DEFAULT_ORDER))

    # ------------------------------------------------------------------
    # Row serialisation
    # ------------------------------------------------------------------

    def serialize_rows(
        self,
        ctx: AuthContext,
        rows: Sequence[Any],
        attributes: Sequence[Mapping[str, Any]],
        *,
        workspace_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        """Serialise *rows* into the frozen row shape.

        One batched status projection for the whole page
        (``state_reader.current_states``): the query count does not grow with
        the number of rows. ``locked`` is derived from the same projection plus
        one workflow-definition read, so the freeze marker costs no per-row
        query either.
        """
        materials = list(rows)
        if not materials:
            return []
        from workflow import state_reader

        item_type = self._item_type_of(materials[0])
        entity_ids = [row.id for row in materials]
        states = dict(
            state_reader.current_states(item_type, entity_ids, tenant_id=ctx.tenant_id)
        )
        # ``current_states`` leaves rows without a ``WorkflowItemState`` absent
        # (it cannot know the type's default). Project the same initial-state
        # fallback the list endpoints use, so a row never shows no status.
        if item_type in state_reader.STATUS_TRACKED_ITEM_TYPES:
            fallback = state_reader.initial_state(item_type)
            for entity_id in entity_ids:
                states.setdefault(str(entity_id), fallback)
        workspace = workspace_id or self._workspace_of(materials[0])
        frozen_states = self._frozen_states(workspace, item_type)
        attribute_names = [str(attribute.get("name")) for attribute in attributes]

        serialised: list[dict[str, Any]] = []
        for entity in materials:
            artifact = entity.artifact
            values = self._values_for(
                entity, artifact, attribute_names, attributes, states
            )
            state = states.get(str(entity.id))
            serialised.append(
                {
                    "id": str(entity.id),
                    "artifact_id": str(artifact.id),
                    "item_type": item_type,
                    "version": entity.version,
                    "values": {name: self.jsonable(value) for name, value in values.items()},
                    "locked": (
                        {"state": state}
                        if state is not None and state in frozen_states
                        else None
                    ),
                }
            )
        return serialised

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _model(item_type: str):
        return import_entity_model(ENTITY_SPECS[TABLE_ITEM_TYPES[item_type]].model_path)

    @staticmethod
    def _workspace_lookup(model: Any, workspace_id: UUID) -> dict[str, Any]:
        return {"workspace_id": workspace_id}

    @staticmethod
    def _item_type_of(entity: Any) -> str:
        return entity.artifact.artifact_type

    @staticmethod
    def _workspace_of(entity: Any) -> UUID:
        return entity.artifact.workspace_id

    @staticmethod
    def _item_read_rule_q(ctx: AuthContext, workspace_id: UUID) -> Q:
        """Return the ``Q`` hiding rows an explicit ``none`` rule denies.

        Precedence of
        :meth:`ItemPermissionService.check_permission`: an artifact-scoped rule
        overrides the workspace-wide rule, only an explicit rule has an
        opinion, ``read``/``write`` never hide. Applied inside the queryset so
        ``count`` does not leak a hidden row's existence.
        """
        from auth_tenancy.models import ITEM_PERMISSION_NONE, ItemPermission

        rules = ItemPermission.objects.filter(
            user_id=ctx.user_id, workspace_id=workspace_id
        )
        workspace_none = rules.filter(
            artifact__isnull=True, permission_level=ITEM_PERMISSION_NONE
        ).exists()
        denied = rules.filter(
            artifact__isnull=False, permission_level=ITEM_PERMISSION_NONE
        ).values("artifact_id")
        if workspace_none:
            kept = (
                rules.filter(artifact__isnull=False)
                .exclude(permission_level=ITEM_PERMISSION_NONE)
                .values("artifact_id")
            )
            return Q(artifact_id__in=kept)
        return ~Q(artifact_id__in=denied)

    @staticmethod
    def _carrier_prefetches(
        model: Any, attributes: Sequence[Mapping[str, Any]]
    ) -> tuple[str, ...]:
        """Prefetch every requested carrier-backed multi-value field.

        ``artifact_system_fields`` reads ``Adr.deciders``/``Issue.assignee``
        through ``selected_actors``; without a prefetch each row would pay its
        own query, and the page's query count would grow with its size.
        """
        wanted = {str(attribute.get("name")) for attribute in attributes}
        prefetches: list[str] = []
        for name in sorted(wanted):
            try:
                field = model._meta.get_field(name)
            except FieldDoesNotExist:
                continue
            if getattr(field, "many_to_many", False):
                prefetches.append(name)
        return tuple(prefetches)

    @classmethod
    def _values_for(
        cls,
        entity: Any,
        artifact: Any,
        names: Sequence[str],
        attributes: Sequence[Mapping[str, Any]],
        states: Mapping[str, str],
    ) -> dict[str, Any]:
        """Resolve one row's ``values`` map (never raises for a missing field)."""
        by_name = {str(attribute.get("name")): attribute for attribute in attributes}
        system_names = _ARTIFACT_VALUE_NAMES | frozenset(entity_carrier_fields(
            artifact.artifact_type
        ))
        system_values: dict[str, Any] = {}
        requested_system = [name for name in names if name in system_names]
        if requested_system:
            system_values = artifact_system_fields(entity)
            if "stakeholder" in requested_system:
                stored = getattr(artifact, "stakeholder", None)
                system_values["stakeholder"] = (
                    list(stored) if isinstance(stored, (list, tuple)) else []
                )

        custom_fields = getattr(artifact, "custom_fields", None) or {}
        values: dict[str, Any] = {}
        for name in names:
            attribute = by_name.get(name, {})
            if name == "status":
                values[name] = states.get(str(entity.id))
            elif name in system_names:
                values[name] = system_values.get(name)
            elif str(attribute.get("kind", "core")) == "extended":
                values[name] = custom_fields.get(name)
            else:
                values[name] = getattr(entity, name, None)
        return values

    @staticmethod
    def _frozen_states(workspace_id: UUID, item_type: str) -> frozenset[str]:
        """Return the state names that freeze an artifact of *item_type*.

        Reads the workspace workflow definition once per page (the store caches)
        instead of calling ``artifact_freeze.is_frozen`` per row, which would
        cost two queries per row.
        """
        try:
            from workflow.definition_store import get_state_meta
            from workflow.services import get_workflow_json

            workflow_json = get_workflow_json(workspace_id, item_type)
        except Exception:  # noqa: BLE001 — fail open, like artifact_freeze
            return frozenset()
        states = (workflow_json or {}).get("states") or []
        frozen = set()
        for state in states:
            name = state.get("name") if isinstance(state, Mapping) else None
            if not name:
                continue
            meta = get_state_meta(workflow_json, name) or {}
            if meta.get("freeze_on_enter"):
                frozen.add(str(name))
        return frozenset(frozen)

    @staticmethod
    def jsonable(value: Any) -> Any:
        """Convert a stored value into a JSON primitive (recursively)."""
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, Mapping):
            return {str(key): TableQueryService.jsonable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [TableQueryService.jsonable(item) for item in value]
        if isinstance(value, (str, int, float)):
            return value
        return str(value)
