"""S3-local table query core for saved views (Tabellenansicht slice 3).

Why this module exists
----------------------
Task 3.2 of ``docs/superpowers/plans/2026-11-04-tabellenansicht-neu.md``
specifies ``SavedViewService.apply`` as a consumer of Slice 1's
``TableQueryService.query/serialize_rows`` plus ``table_filter_dsl
.compile_filters/compile_sort``. **Neither module exists on the branch this
slice is built on**: slice 1 is not merged yet, so the only honest options are
(a) a hard import of a module that is not there, (b) a stub that answers
everything, or (c) this: the smallest complete implementation of the *frozen
wire format* the plan publishes, self-contained and replaceable.

This module is (c). It is deliberately named apart from slice 1's files
(``table_filter_dsl.py`` / ``table_query_service.py``) so the two never shadow
each other; the rebase of slice 3 replaces
:func:`query_rows`/:func:`compile_filters`/:func:`compile_sort` with the slice-1
imports and deletes this file. **Nothing else in slice 3 imports ORM directly**
— ``application/saved_view_service.py`` is the only caller.

Wire format (frozen by the plan, restated here so the contract survives):
    filters := {"<field>": <constraint> | [<constraint>, ...]}   (list = AND)
    constraint := {"op": "contains" | "in" | "gte" | "lte" | "eq", "value": ...}
    sort := [{"field": "<name>", "dir": "asc" | "desc"}]

Rules enforced (all raise :class:`application.base.ValidationError` naming the
field — never a silent ignore):
  * unknown field / unknown item type,
  * operator not allowed for the field's kind,
  * wrong value type, ``in`` with a non-list or with more than
    :data:`MAX_IN_VALUES` entries,
  * ``contains`` on anything but a text field,
  * sort on a non-sortable field (JSON/list columns) or more than
    :data:`MAX_SORT_TERMS` terms.

Scope (documented deviation, mirrors the plan's O6/O12):
  * only **core** fields are filterable/sortable — extended attributes live in
    ``Artifact.custom_fields`` and are explicitly out of scope for the filter
    DSL,
  * the pseudo-fields ``allocated``/``level`` are slice 1 (O2) and therefore
    unknown here; a stored view using them degrades through
    :func:`apply_saved`'s fail-soft path (empty result + warning), which is the
    contract Review Focus 4 asks for,
  * ``locked`` is always ``None``: the freeze marker comes from
    ``application/artifact_freeze.py`` (Ordnung-Allokation Task 4.1), which
    does not exist yet (plan O5).

Router-free, transport-free, view-free: REST and MCP both serialize the row
dicts this module returns.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from django.db.models import Q
from django.utils.dateparse import parse_date, parse_datetime

from application.base import ValidationError
from application.workspace_lookup import import_entity_model

#: Operators of the frozen DSL.
SUPPORTED_OPERATORS: frozenset[str] = frozenset({"contains", "in", "gte", "lte", "eq"})

#: Upper bound for one ``in`` constraint (plan Task 1.3).
MAX_IN_VALUES: int = 200

#: Upper bound for a ``sort`` document.
MAX_SORT_TERMS: int = 5


@dataclass(frozen=True)
class FieldSpec:
    """One filterable/sortable core field.

    ``kind`` is one of ``text``, ``number``, ``date``, ``bool``, ``json``.
    A ``json`` field is displayed (``values``) but never filtered or sorted:
    a JSON column has no database ordering or substring semantics, and the
    extended attributes that share this shape are out of scope (plan O6).
    """

    kind: str

    @property
    def filterable(self) -> bool:
        return self.kind != "json"

    @property
    def sortable(self) -> bool:
        return self.kind != "json"


_TEXT = FieldSpec("text")
_NUMBER = FieldSpec("number")
_DATE = FieldSpec("date")
_BOOL = FieldSpec("bool")
_JSON = FieldSpec("json")


@dataclass(frozen=True)
class ItemTypeSpec:
    """Everything this module needs to know about one table artifact type."""

    model_path: str
    #: Column that holds the owning workspace (a FK or a bare UUID column).
    workspace_field: str
    fields: Mapping[str, FieldSpec]
    #: Local human-readable id column, or ``None`` when the type has none
    #: (``GlossaryTerm`` is the one type without a ``uid``).
    uid_field: str | None = "uid"


#: The eight table types of the plan (Goal/MainGoal/Document are deliberately
#: absent — plan O8: lineage versioning / their own entity).
ITEM_TYPES: dict[str, ItemTypeSpec] = {
    "Requirement": ItemTypeSpec(
        "persistence.models.Requirement",
        workspace_field="workspace_id",
        fields={
            "title": _TEXT,
            "description": _TEXT,
            "acceptance_criteria": _TEXT,
            "rationale": _TEXT,
            "source": _TEXT,
            "category": _TEXT,
            "type": _TEXT,
            "complexity_fibonacci": _NUMBER,
            "verification_method": _TEXT,
        },
    ),
    "StakeholderNeed": ItemTypeSpec(
        "persistence.models.StakeholderNeed",
        workspace_field="workspace_id",
        fields={
            "title": _TEXT,
            "description": _TEXT,
            "category": _TEXT,
            "moscow_priority": _TEXT,
        },
    ),
    "ArchitectureElement": ItemTypeSpec(
        "persistence.models.ArchitectureElement",
        workspace_field="workspace_id",
        fields={
            "title": _TEXT,
            "description": _TEXT,
            "element_type": _TEXT,
            "asil_level": _TEXT,
            "make_or_buy": _TEXT,
        },
    ),
    "TestCase": ItemTypeSpec(
        "persistence.models.TestCase",
        workspace_field="workspace_id",
        fields={
            "title": _TEXT,
            "description": _TEXT,
            "steps": _JSON,
            "test_type": _TEXT,
            "scenario_kind": _TEXT,
        },
    ),
    "Adr": ItemTypeSpec(
        "persistence.models.Adr",
        workspace_field="workspace_id",
        fields={
            "title": _TEXT,
            "description": _TEXT,
            "context": _TEXT,
            "decision": _TEXT,
            "consequences": _TEXT,
        },
    ),
    "Risk": ItemTypeSpec(
        "persistence.models.Risk",
        workspace_field="workspace_id",
        fields={
            "title": _TEXT,
            "description": _TEXT,
            "probability": _TEXT,
            "impact": _TEXT,
            "category": _TEXT,
            "mitigation_strategy": _TEXT,
            "detection": _NUMBER,
            "risk_score": _NUMBER,
        },
    ),
    "Issue": ItemTypeSpec(
        "persistence.models.Issue",
        workspace_field="workspace_id",
        fields={
            "title": _TEXT,
            "description": _TEXT,
            "severity": _TEXT,
            "category": _TEXT,
            "due_date": _DATE,
            "tags": _JSON,
        },
    ),
    "GlossaryTerm": ItemTypeSpec(
        "persistence.models.GlossaryTerm",
        workspace_field="workspace_id",
        fields={
            "term": _TEXT,
            "definition": _TEXT,
            "synonyms": _JSON,
            "abbreviation": _TEXT,
        },
    ),
}


def _spec(item_type: str) -> ItemTypeSpec:
    spec = ITEM_TYPES.get(item_type)
    if spec is None:
        known = ", ".join(sorted(ITEM_TYPES))
        raise ValidationError(
            f"Unknown item_type {item_type!r}; expected one of {known}"
        )
    return spec


def _field_spec(item_type: str, field: str) -> FieldSpec:
    spec = _spec(item_type)
    field_spec = spec.fields.get(field)
    if field_spec is None:
        known = ", ".join(sorted(spec.fields))
        raise ValidationError(
            f"Unknown field '{field}' for item type '{item_type}'; "
            f"filterable/sortable fields are {known}"
        )
    return field_spec


# ---------------------------------------------------------------------------
# Constraint compilation
# ---------------------------------------------------------------------------


def _as_text(field: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ValidationError(
            f"Field '{field}': 'contains' expects a string value"
        )
    return value


def _as_number(field: str, value: Any) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"Field '{field}': expected a number, got {value!r}")
    return value


def _as_date(field: str, value: Any) -> date:
    parsed = None
    if isinstance(value, str):
        parsed = parse_datetime(value) or parse_date(value)
    if parsed is None:
        raise ValidationError(
            f"Field '{field}': expected an ISO-8601 date, got {value!r}"
        )
    return parsed


def _as_bool(field: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValidationError(f"Field '{field}': expected a boolean, got {value!r}")
    return value


def _coerce(field: str, field_spec: FieldSpec, value: Any) -> Any:
    if field_spec.kind == "number":
        return _as_number(field, value)
    if field_spec.kind == "date":
        return _as_date(field, value)
    if field_spec.kind == "bool":
        return _as_bool(field, value)
    return value


def _compile_constraint(item_type: str, field: str, constraint: Any) -> Q:
    """Compile one ``{"op": ..., "value": ...}`` constraint into a ``Q``."""
    field_spec = _field_spec(item_type, field)
    if not field_spec.filterable:
        raise ValidationError(f"Field '{field}' is not filterable")
    if not isinstance(constraint, Mapping):
        raise ValidationError(
            f"Field '{field}': a constraint must be an object with 'op' and 'value'"
        )
    op = constraint.get("op")
    if op not in SUPPORTED_OPERATORS:
        allowed = ", ".join(sorted(SUPPORTED_OPERATORS))
        raise ValidationError(
            f"Field '{field}': unknown operator {op!r}; expected one of {allowed}"
        )
    if "value" not in constraint:
        raise ValidationError(f"Field '{field}': constraint has no 'value'")
    value = constraint["value"]

    if op == "contains":
        if field_spec.kind != "text":
            raise ValidationError(
                f"Field '{field}': 'contains' is only allowed on text fields"
            )
        return Q(**{f"{field}__icontains": _as_text(field, value)})

    if op == "in":
        if not isinstance(value, (list, tuple)):
            raise ValidationError(
                f"Field '{field}': 'in' expects a list of values"
            )
        if len(value) > MAX_IN_VALUES:
            raise ValidationError(
                f"Field '{field}': 'in' accepts at most {MAX_IN_VALUES} values"
            )
        coerced = [_coerce(field, field_spec, entry) for entry in value]
        # An empty list matches nothing (not everything) — plan Review Focus 2.
        return Q(**{f"{field}__in": coerced})

    lookup = {"gte": "gte", "lte": "lte", "eq": "exact"}[str(op)]
    return Q(**{f"{field}__{lookup}": _coerce(field, field_spec, value)})


def compile_filters(item_type: str, filters: Any) -> Q:
    """Compile a ``filters`` document into one ``Q`` (AND over all fields).

    Raises:
        ValidationError: Unknown item type/field, disallowed operator, wrong
            value type or an oversized ``in`` list.
    """
    if filters is None or filters == {}:
        return Q()
    if not isinstance(filters, Mapping):
        raise ValidationError("'filters' must be an object")
    combined = Q()
    for field, constraint in filters.items():
        if isinstance(constraint, (list, tuple)):
            if not constraint:
                raise ValidationError(
                    f"Field '{field}': an empty constraint list is not allowed"
                )
            for entry in constraint:
                combined &= _compile_constraint(item_type, str(field), entry)
        else:
            combined &= _compile_constraint(item_type, str(field), constraint)
    return combined


def compile_sort(item_type: str, sort: Any) -> tuple[str, ...]:
    """Compile a ``sort`` document into an ``order_by`` tuple.

    Always appends ``id`` as the tiebreaker: offline pagination over a
    non-unique sort key would otherwise repeat or skip rows.
    """
    if sort is None or sort == []:
        return ("id",)
    if not isinstance(sort, (list, tuple)):
        raise ValidationError("'sort' must be a list")
    if len(sort) > MAX_SORT_TERMS:
        raise ValidationError(f"'sort' accepts at most {MAX_SORT_TERMS} terms")
    terms: list[str] = []
    for term in sort:
        if not isinstance(term, Mapping):
            raise ValidationError("Each sort term must be an object")
        field = term.get("field")
        if not isinstance(field, str):
            raise ValidationError("Each sort term needs a string 'field'")
        field_spec = _field_spec(item_type, field)
        if not field_spec.sortable:
            raise ValidationError(f"Field '{field}' is not sortable")
        direction = term.get("dir", "asc")
        if direction not in ("asc", "desc"):
            raise ValidationError(
                f"Field '{field}': 'dir' must be 'asc' or 'desc'"
            )
        terms.append(f"-{field}" if direction == "desc" else field)
    terms.append("id")
    return tuple(terms)


# ---------------------------------------------------------------------------
# Row materialisation
# ---------------------------------------------------------------------------


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def query_rows(
    workspace_id: UUID,
    item_type: str,
    filters: Any = None,
    sort: Any = None,
) -> list[dict[str, Any]]:
    """Return the table rows of *item_type* in *workspace_id*.

    Row shape (the ``artifacts/table/`` contract of the plan, minus S1's
    definition-derived ``values``)::

        {"id": "<entity id>", "artifact_id": "<pl_artifact id>",
         "item_type": "Requirement", "version": 3,
         "values": {"uid": ..., "<field>": ...}, "locked": None}

    The caller must have armed the tenant context; the workspace filter is
    applied on top, so a foreign workspace simply yields no rows.

    Raises:
        ValidationError: The filter/sort document is invalid (see module doc).
    """
    spec = _spec(item_type)
    model = import_entity_model(spec.model_path)
    where = compile_filters(item_type, filters)
    order_by = compile_sort(item_type, sort)
    field_names = tuple(spec.fields)
    extra = (spec.uid_field,) if spec.uid_field else ()
    rows = (
        model.objects.filter(**{spec.workspace_field: workspace_id})
        .filter(where)
        .order_by(*order_by)
        .values("id", "artifact_id", "version", *extra, *field_names)
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        values = {
            "uid": _json_safe(row[spec.uid_field]) if spec.uid_field else None,
            **{name: _json_safe(row[name]) for name in field_names},
        }
        result.append(
            {
                "id": str(row["id"]),
                "artifact_id": str(row["artifact_id"]),
                "item_type": item_type,
                "version": row["version"],
                "values": values,
                "locked": None,
            }
        )
    return result


def warning_for(exc: Exception) -> str:
    """Render a DSL :class:`ValidationError` as the warning an apply returns."""
    message = getattr(exc, "message", None) or str(exc)
    return f"Saved view could not be applied: {message}"


def is_known_item_type(item_type: str) -> bool:
    """Return whether *item_type* is one of the eight table types."""
    return item_type in ITEM_TYPES


def sortable_field_names(item_type: str) -> Sequence[str]:
    """Return the sortable field names of *item_type* (diagnostics/tests)."""
    spec = _spec(item_type)
    return tuple(name for name, fs in spec.fields.items() if fs.sortable)
