"""Type-aware filter language for the artifact table (Tabellenansicht S1, Task 1.3).

A **pure Python API**: no HTTP, no request, no ``ctx``. The caller supplies the
attribute list it is allowed to expose (the resolved workspace definition, or
the built-in fallback of :mod:`application.table_query_service`), and this
module compiles the frozen wire documents into a Django ``Q`` and an
``order_by`` tuple:

    filters := {"<field>": <constraint> | [<constraint>, ...]}   (list = AND)
    constraint := {"op": "contains" | "in" | "gte" | "lte" | "eq", "value": ...}
    sort := [{"field": "<name>", "dir": "asc" | "desc"}]

Design rules (spec §3.1, plan Task 1.3):

* **Never a silent ignore.** An unknown field, an operator the field's type does
  not allow, a wrong value type, an oversized ``in`` list — every one raises
  :class:`application.base.ValidationError` and the message names the field (and
  the operator, where applicable). A dropped constraint would answer 200 with
  rows the caller did not ask for.
* **Operators follow the attribute type** (:data:`FILTER_OPERATORS_BY_TYPE`),
  with one deliberate exception: an attribute whose definition says
  ``editable == "workflow"`` (``status``) is always filterable with ``in`` —
  filtering is a read, not a write.
* **Literal text.** ``contains`` compiles to ``icontains``, so ``%``, ``_`` and
  quotes are matched literally by the ORM's own escaping; nothing here builds
  SQL strings.
* **Only declared attributes are reachable.** A name that is not in the supplied
  attribute list is refused before any ORM path is derived, which is what keeps
  ``artifact__workspace__tenant`` and every other traversal out of the queryset.
* **``status`` is not a column.** It lives in ``WorkflowItemState``
  (Datenmodell-Konsolidierung Phase 1), so its ``in`` constraint materialises
  the workspace's entity ids, projects them through
  :func:`workflow.state_reader.current_states` (with the type's initial-state
  fallback) and filters ``id__in`` the matching ones — the same shortcut
  ``RequirementService.list_requirements(status=...)`` already documents.
* **Pseudo-fields** (plan O2): ``allocated``/``level`` exist for ``Requirement``
  only and delegate to :mod:`application.requirement_filters`, the same
  implementation behind ``?allocated=``/``?level=``.
* **Sorting** accepts concrete entity columns and ``priority`` (an artifact
  column); ``status``, actor fields, the pseudo-fields, ``criteria-list``/
  ``widget`` and extended attributes are refused. ``id`` is always appended as
  the tie-breaker: pagination over a non-unique sort key would otherwise repeat
  or skip rows. The symbolic key ``{"field": "tree", "dir": "asc"}`` expands to
  ``sort_key NULLS LAST, created_at, id`` (#1670 P1 is merged, so it works;
  ``desc`` is refused — a reversed sibling order is not a tree).
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any
from uuid import UUID

from django.core.exceptions import FieldDoesNotExist
from django.db.models import F, Q
from django.utils.dateparse import parse_date, parse_datetime

from application.base import ValidationError
from application.requirement_filters import allocated_q, level_q
from application.workspace_lookup import ENTITY_SPECS, import_entity_model

__all__ = [
    "FILTER_OPERATORS_BY_TYPE",
    "MAX_CONSTRAINTS_PER_FIELD",
    "MAX_IN_VALUES",
    "MAX_SORT_TERMS",
    "PSEUDO_FIELDS",
    "TABLE_ITEM_TYPES",
    "TREE_SORT_FIELD",
    "allowed_operators",
    "compile_filters",
    "compile_sort",
    "filterable_field_names",
    "sortable_field_names",
]

#: ``item_type`` (the ``Artifact.artifact_type`` string) -> ``ENTITY_SPECS`` key.
#: Goal/MainGoal/Document are deliberately absent (plan O8: lineage versioning /
#: their own entity).
TABLE_ITEM_TYPES: dict[str, str] = {
    "Requirement": "requirement",
    "StakeholderNeed": "need",
    "ArchitectureElement": "architecture",
    "TestCase": "testcase",
    "Adr": "adr",
    "Risk": "risk",
    "Issue": "issue",
    "GlossaryTerm": "glossary",
}

#: Frozen operator table per attribute type (spec §3.1). ``criteria-list`` and
#: ``widget`` are absent on purpose: they have no ordering or containment
#: semantics, so they are neither filterable nor sortable.
FILTER_OPERATORS_BY_TYPE: dict[str, frozenset[str]] = {
    "text": frozenset({"contains"}),
    "textarea": frozenset({"contains"}),
    "enum": frozenset({"in"}),
    "multi-enum": frozenset({"in"}),
    "number": frozenset({"gte", "lte"}),
    "date": frozenset({"gte", "lte"}),
    "boolean": frozenset({"eq"}),
    "reference": frozenset({"in"}),
    "user": frozenset({"in"}),
    "actor": frozenset({"in"}),
}

#: Pseudo-fields: values the table can filter on that are not entity columns.
#: Only ``Requirement`` has any (plan O2).
PSEUDO_FIELDS: dict[str, dict[str, dict[str, Any]]] = {
    "Requirement": {
        "allocated": {"type": "boolean", "operators": frozenset({"eq"})},
        "level": {
            "type": "number",
            "operators": frozenset({"eq"}),
            "minimum": 1,
            "maximum": 4,
        },
    }
}

#: Upper bound for one ``in`` constraint. Larger lists are refused (400), not
#: truncated: a silently shortened list would drop rows the caller selected.
MAX_IN_VALUES: int = 200

#: Upper bound for a ``sort`` document.
MAX_SORT_TERMS: int = 5

#: Upper bound for the constraint list of one field (a range is 2).
MAX_CONSTRAINTS_PER_FIELD: int = 5

#: Symbolic sort key requesting the persistent sibling order.
TREE_SORT_FIELD = "tree"

#: Names that address storage, never content. Refused even when a definition
#: (or a hand-written payload) happens to carry one.
_STRUCTURAL_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "version",
        "artifact",
        "artifact_id",
        "workspace",
        "workspace_id",
        "tenant",
        "tenant_id",
        "parent",
        "parent_id",
        "sort_key",
        "lifecycle_status",
    }
)

#: System fields whose column lives on ``Artifact``, mapped to their ORM path.
_ARTIFACT_COLUMN_PATHS: dict[str, str] = {
    "owner": "artifact__owner_id",
    "reporter": "artifact__reporter_id",
    "priority": "artifact__priority",
}

_OPERATOR_LOOKUPS: dict[str, str] = {"gte": "gte", "lte": "lte", "eq": "exact"}


# ---------------------------------------------------------------------------
# Attribute lookup
# ---------------------------------------------------------------------------


def _entity_model(item_type: str):
    entity_key = TABLE_ITEM_TYPES.get(item_type)
    if entity_key is None:
        known = ", ".join(sorted(TABLE_ITEM_TYPES))
        raise ValidationError(
            f"Unknown item_type {item_type!r}; expected one of {known}"
        )
    return import_entity_model(ENTITY_SPECS[entity_key].model_path)


def _attribute_by_name(
    attributes: Sequence[Mapping[str, Any]], name: str, item_type: str
) -> Mapping[str, Any]:
    for attribute in attributes:
        if attribute.get("name") == name:
            return attribute
    known = ", ".join(sorted(str(a.get("name")) for a in attributes))
    raise ValidationError(
        f"Unknown field '{name}' for item type '{item_type}'; "
        f"filterable fields are {known or '(none)'}"
    )


def allowed_operators(attribute: Mapping[str, Any]) -> frozenset[str]:
    """Return the operators *attribute* allows.

    A workflow-owned attribute (``editable == "workflow"``, i.e. ``status``)
    always allows ``in``: reading a state is not writing one.
    """
    if attribute.get("editable") == "workflow":
        return frozenset({"in"})
    return FILTER_OPERATORS_BY_TYPE.get(str(attribute.get("type", "")), frozenset())


def filterable_field_names(
    item_type: str, attributes: Sequence[Mapping[str, Any]]
) -> tuple[str, ...]:
    """Return every filterable name (attributes with a non-empty operator set)."""
    pseudo = PSEUDO_FIELDS.get(item_type, {})
    names = {
        str(attribute.get("name"))
        for attribute in attributes
        if allowed_operators(attribute)
    }
    return tuple(sorted(names | set(pseudo)))


def sortable_field_names(
    item_type: str, attributes: Sequence[Mapping[str, Any]]
) -> tuple[str, ...]:
    """Return every sortable name (diagnostics; mirrors :func:`compile_sort`)."""
    model = _entity_model(item_type)
    pseudo = PSEUDO_FIELDS.get(item_type, {})
    names = []
    for attribute in attributes:
        name = str(attribute.get("name"))
        if name in pseudo:
            continue
        try:
            _sort_path(model, name, attribute)
        except ValidationError:
            continue
        names.append(name)
    return tuple(sorted(names))


# ---------------------------------------------------------------------------
# Value coercion
# ---------------------------------------------------------------------------


def _as_text(field: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"Field '{field}': 'contains' expects a string value")
    return value


def _as_number(field: str, value: Any) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"Field '{field}': expected a number, got {value!r}")
    return value


def _as_date(field: str, value: Any) -> date | datetime:
    parsed = None
    if isinstance(value, str):
        parsed = parse_datetime(value) or parse_date(value)
    if parsed is None:
        raise ValidationError(
            f"Field '{field}': expected an ISO-8601 date, got {value!r}"
        )
    return parsed


def _as_reference(field: str, value: Any) -> Any:
    """Accept a UUID string, a UUID, or an actor value object ``{"id": ...}``."""
    if isinstance(value, Mapping):
        value = value.get("id")
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            raise ValidationError(
                f"Field '{field}': expected a UUID reference, got a string"
            ) from None
    raise ValidationError(f"Field '{field}': expected a UUID reference")


def _coerce(field: str, value_type: str, value: Any) -> Any:
    if value_type == "number":
        return _as_number(field, value)
    if value_type == "date":
        return _as_date(field, value)
    if value_type == "boolean":
        if not isinstance(value, bool):
            raise ValidationError(
                f"Field '{field}': expected a boolean, got {value!r} "
                "(the string 'true' is not a boolean)"
            )
        return value
    if value_type in ("reference", "user", "actor"):
        return _as_reference(field, value)
    return value


def _is_array_field(model: Any, name: str) -> bool:
    try:
        field = model._meta.get_field(name)
    except FieldDoesNotExist:
        return False
    return field.get_internal_type() == "ArrayField"


# ---------------------------------------------------------------------------
# ORM path resolution
# ---------------------------------------------------------------------------


def _orm_path(
    model: Any, name: str, attribute: Mapping[str, Any]
) -> str:
    """Return the ORM path for filtering *name*, or raise ``ValidationError``."""
    if "__" in name or "." in name or name in _STRUCTURAL_FIELDS:
        raise ValidationError(f"Field '{name}' is not filterable")
    kind = str(attribute.get("kind", "core"))
    if kind == "extended":
        # Plan O6: extended attributes live in the flat custom_fields map; they
        # are not filterable in slice 1.
        raise ValidationError(f"Field '{name}' is not filterable yet")
    if name in _ARTIFACT_COLUMN_PATHS:
        return _ARTIFACT_COLUMN_PATHS[name]
    try:
        field = model._meta.get_field(name)
    except FieldDoesNotExist:
        raise ValidationError(f"Field '{name}' is not filterable yet") from None
    if not field.concrete or field.is_relation:
        raise ValidationError(f"Field '{name}' is not filterable yet")
    return name


def _sort_path(model: Any, name: str, attribute: Mapping[str, Any]) -> str:
    """Return the ORM path for sorting *name*, or raise ``ValidationError``."""
    if attribute.get("editable") == "workflow":
        raise ValidationError(
            f"Field '{name}' is not sortable: the state lives in a separate "
            "table"
        )
    value_type = str(attribute.get("type", ""))
    if value_type in ("actor", "user", "criteria-list", "widget"):
        raise ValidationError(f"Field '{name}' is not sortable")
    if str(attribute.get("kind", "core")) == "extended":
        raise ValidationError(f"Field '{name}' is not sortable yet")
    if "__" in name or "." in name or name in _STRUCTURAL_FIELDS:
        raise ValidationError(f"Field '{name}' is not sortable")
    if name in _ARTIFACT_COLUMN_PATHS:
        return _ARTIFACT_COLUMN_PATHS[name]
    try:
        field = model._meta.get_field(name)
    except FieldDoesNotExist:
        raise ValidationError(f"Field '{name}' is not sortable yet") from None
    if not field.concrete or field.is_relation:
        raise ValidationError(f"Field '{name}' is not sortable yet")
    return name


# ---------------------------------------------------------------------------
# status projection
# ---------------------------------------------------------------------------


def _status_matching_ids(
    item_type: str,
    model: Any,
    workspace_id: UUID,
    values: Sequence[str],
    *,
    tenant_id: UUID,
) -> list[Any]:
    """Return the entity ids whose projected status is one of *values*."""
    from workflow import state_reader

    rows = model.objects.filter(**_workspace_lookup(model, workspace_id)).values("id")
    ids = [row["id"] for row in rows]
    states = state_reader.current_states(item_type, ids, tenant_id=tenant_id)
    try:
        fallback = (
            state_reader.initial_state(item_type)
            if item_type in state_reader.STATUS_TRACKED_ITEM_TYPES
            else None
        )
    except KeyError:  # pragma: no cover - guarded by the membership check
        fallback = None
    wanted = set(values)
    return [item_id for item_id in ids if (states.get(str(item_id)) or fallback) in wanted]


def _workspace_lookup(model: Any, workspace_id: UUID) -> dict[str, Any]:
    """Return the keyword for the model's owning-workspace column."""
    if _has_field(model, "workspace_id"):
        return {"workspace_id": workspace_id}
    return {"artifact__workspace_id": workspace_id}


def _has_field(model: Any, name: str) -> bool:
    try:
        model._meta.get_field(name)
    except FieldDoesNotExist:
        return False
    return True


# ---------------------------------------------------------------------------
# compile_filters
# ---------------------------------------------------------------------------


def compile_filters(
    item_type: str,
    attributes: Sequence[Mapping[str, Any]],
    filters: Mapping[str, Any] | None,
    *,
    tenant_id: UUID,
    workspace_id: UUID,
) -> Q:
    """Compile the ``filters`` document into one ``Q`` (AND over all fields).

    Args:
        item_type: One of :data:`TABLE_ITEM_TYPES`.
        attributes: The attribute list the caller may expose (resolved
            definition, or the built-in fallback).
        filters: The wire document, or ``None``/``{}`` for "no filter".
        tenant_id: Tenant for the workaround lookups (``status`` link,
            ``allocated``).
        workspace_id: Workspace the rows are read from (``status`` projection).

    Raises:
        ValidationError: unknown item type/field, disallowed operator, wrong
            value type, more than :data:`MAX_IN_VALUES` values in one ``in`` or
            more than :data:`MAX_CONSTRAINTS_PER_FIELD` constraints.
    """
    model = _entity_model(item_type)
    if filters is None or filters == {}:
        return Q()
    if not isinstance(filters, Mapping):
        raise ValidationError("'filters' must be an object")

    pseudo = PSEUDO_FIELDS.get(item_type, {})
    combined = Q()
    for raw_name, constraint in filters.items():
        name = str(raw_name)
        constraints = (
            list(constraint) if isinstance(constraint, (list, tuple)) else [constraint]
        )
        if not constraints:
            raise ValidationError(
                f"Field '{name}': an empty constraint list is not allowed"
            )
        if len(constraints) > MAX_CONSTRAINTS_PER_FIELD:
            raise ValidationError(
                f"Field '{name}': at most {MAX_CONSTRAINTS_PER_FIELD} constraints "
                "per field"
            )
        for entry in constraints:
            if name in pseudo:
                combined &= _compile_pseudo_field(
                    item_type,
                    name,
                    entry,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                )
            else:
                combined &= _compile_attribute_constraint(
                    item_type,
                    model,
                    attributes,
                    name,
                    entry,
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                )
    return combined


def _constraint_parts(field: str, constraint: Any) -> tuple[str, Any]:
    if not isinstance(constraint, Mapping):
        raise ValidationError(
            f"Field '{field}': a constraint must be an object with 'op' and 'value'"
        )
    op = constraint.get("op")
    if not isinstance(op, str):
        raise ValidationError(f"Field '{field}': constraint has no 'op'")
    if "value" not in constraint:
        raise ValidationError(f"Field '{field}': constraint has no 'value'")
    return op, constraint["value"]


def _compile_pseudo_field(
    item_type: str,
    name: str,
    constraint: Any,
    *,
    tenant_id: UUID,
    workspace_id: UUID,
) -> Q:
    spec = PSEUDO_FIELDS[item_type][name]
    op, value = _constraint_parts(name, constraint)
    operators: frozenset[str] = spec["operators"]
    if op not in operators:
        allowed = ", ".join(sorted(operators))
        raise ValidationError(
            f"Field '{name}': operator '{op}' is not allowed; expected one of {allowed}"
        )
    if name == "allocated":
        allocated = _coerce(name, "boolean", value)
        return allocated_q(allocated=bool(allocated), tenant_id=tenant_id)
    number = _coerce(name, "number", value)
    minimum = spec.get("minimum")
    maximum = spec.get("maximum")
    if isinstance(number, float) or not (
        (minimum is None or number >= minimum) and (maximum is None or number <= maximum)
    ):
        raise ValidationError(
            f"Field '{name}': expected an integer between {minimum} and {maximum}"
        )
    return level_q(int(number))


def _compile_attribute_constraint(
    item_type: str,
    model: Any,
    attributes: Sequence[Mapping[str, Any]],
    name: str,
    constraint: Any,
    *,
    tenant_id: UUID,
    workspace_id: UUID,
) -> Q:
    attribute = _attribute_by_name(attributes, name, item_type)
    operators = allowed_operators(attribute)
    if not operators:
        raise ValidationError(f"Field '{name}' is not filterable")
    op, value = _constraint_parts(name, constraint)
    if op not in operators:
        allowed = ", ".join(sorted(operators))
        raise ValidationError(
            f"Field '{name}': operator '{op}' is not allowed for type "
            f"'{attribute.get('type')}'; expected one of {allowed}"
        )

    if attribute.get("editable") == "workflow":
        values = _as_state_list(name, value, op)
        matching = _status_matching_ids(
            item_type, model, workspace_id, values, tenant_id=tenant_id
        )
        return Q(id__in=matching)

    path = _orm_path(model, name, attribute)
    value_type = str(attribute.get("type", "text"))

    if op == "contains":
        if value_type not in ("text", "textarea"):
            raise ValidationError(
                f"Field '{name}': 'contains' is only allowed on text fields"
            )
        return Q(**{f"{path}__icontains": _as_text(name, value)})

    if op == "in":
        if not isinstance(value, (list, tuple)):
            raise ValidationError(f"Field '{name}': 'in' expects a list of values")
        if len(value) > MAX_IN_VALUES:
            raise ValidationError(
                f"Field '{name}': 'in' accepts at most {MAX_IN_VALUES} values"
            )
        coerced = [_coerce(name, value_type, entry) for entry in value]
        if _is_array_field(model, path):
            # A multi-valued column has no equality: "in" means "overlaps".
            return Q(**{f"{path}__overlap": coerced})
        return Q(**{f"{path}__in": coerced})

    lookup = _OPERATOR_LOOKUPS[op]
    return Q(**{f"{path}__{lookup}": _coerce(name, value_type, value)})


def _as_state_list(name: str, value: Any, op: str) -> list[str]:
    if op != "in":  # pragma: no cover - guarded by allowed_operators
        raise ValidationError(f"Field '{name}': only 'in' is allowed")
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(entry, str) for entry in value
    ):
        raise ValidationError(f"Field '{name}': 'in' expects a list of state names")
    if len(value) > MAX_IN_VALUES:
        raise ValidationError(
            f"Field '{name}': 'in' accepts at most {MAX_IN_VALUES} values"
        )
    return list(value)


# ---------------------------------------------------------------------------
# compile_sort
# ---------------------------------------------------------------------------


def compile_sort(
    item_type: str,
    attributes: Sequence[Mapping[str, Any]],
    sort: Sequence[Mapping[str, Any]] | None,
) -> tuple[Any, ...]:
    """Compile the ``sort`` document into an ``order_by`` tuple.

    Returns an empty tuple when *sort* is absent, so the caller applies its own
    default order (one place to change). ``id`` is always appended as the
    tie-breaker unless the tree order already ends with it.
    """
    model = _entity_model(item_type)
    pseudo = PSEUDO_FIELDS.get(item_type, {})
    if sort is None or sort == []:
        return ()
    if not isinstance(sort, (list, tuple)):
        raise ValidationError("'sort' must be a list")
    if len(sort) > MAX_SORT_TERMS:
        raise ValidationError(f"'sort' accepts at most {MAX_SORT_TERMS} terms")

    terms: list[Any] = []
    for index, term in enumerate(sort):
        if not isinstance(term, Mapping):
            raise ValidationError("Each sort term must be an object")
        field = term.get("field")
        if not isinstance(field, str):
            raise ValidationError("Each sort term needs a string 'field'")
        direction = term.get("dir", "asc")
        if direction not in ("asc", "desc"):
            raise ValidationError(f"Field '{field}': 'dir' must be 'asc' or 'desc'")

        if field == TREE_SORT_FIELD:
            if index != 0:
                raise ValidationError(
                    "The 'tree' order must be the first sort term"
                )
            if direction == "desc":
                raise ValidationError("The 'tree' order only supports 'asc'")
            terms.extend(_tree_order())
            continue

        if field in pseudo:
            raise ValidationError(f"Field '{field}' is not sortable")
        attribute = _attribute_by_name(attributes, field, item_type)
        path = _sort_path(model, field, attribute)
        terms.append(f"-{path}" if direction == "desc" else path)

    last = terms[-1] if terms else None
    if not (isinstance(last, str) and last.lstrip("-") == "id"):
        terms.append("id")
    return tuple(terms)


def _tree_order() -> tuple[Any, ...]:
    """Persistent sibling order: ``sort_key NULLS LAST, created_at, id``."""
    return (
        F("artifact__sort_key").asc(nulls_last=True),
        "created_at",
        "id",
    )
