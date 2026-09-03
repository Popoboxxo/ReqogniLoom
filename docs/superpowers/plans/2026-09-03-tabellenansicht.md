# Tabellenansicht und Massenbearbeitung Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a spreadsheet-like table view for artifacts — type-aware column filtering, multi-sort, saved views, inline edit and bulk update/transition — without ever letting a `editable: "workflow"` field be written outside a real workflow transition.

**Architecture:** All query/mutation logic lands in Layer 2 (`backend/application/`) behind three new seams — a declarative filter DSL compiler, an `ARTIFACT_UPDATE_ADAPTERS` registry modelled 1:1 on the existing `ARTIFACT_CREATION_ADAPTERS`, and a `BulkEditService` whose single `assert_no_workflow_owned_fields()` guard is the one place the workflow guardrail is enforced for REST *and* MCP. Layer 3 adds one new REST module (`rest_api/table_views.py`, no ORM — the architecture ratchet caps new `*_views.py` files at 0 direct-ORM lines) plus two MCP tool additions. The frontend adds one shared `ArtifactTable` component tree that reuses the field-component library and attribute definition from the Attribut-Definition spec instead of inventing a second UI system.

**Tech Stack:** Django 6.1 / DRF (APIView + `StandardPagination`), PostgreSQL 16 with row-level security, pytest, React 18 + TypeScript 5.5 strict, CSS Modules with `styles/tokens.css` custom properties, vitest, react-i18next.

**Spec:** docs/superpowers/specs/2026-09-03-tabellenansicht-design.md

## Global Constraints

- **Workflow guardrail (spec §2, wörtlich vom Nutzer verlangt):** No field with `editable: "workflow"` may EVER be written through a table cell, inline edit, or bulk update. Every write path of this plan enforces it; a bulk-update payload naming such a field is rejected with HTTP 400 for the WHOLE request (no partial success for that one case, spec §3.1).
- The guardrail is enforced in exactly one function — `application/bulk_edit_service.assert_no_workflow_owned_fields()` — so REST and MCP cannot diverge. Never re-implement the check in a view or tool handler.
- Defense in depth: besides the definition-driven check, `WORKFLOW_OWNED_FALLBACK = frozenset({"status", "lifecycle_status"})` is rejected unconditionally, even when the resolved attribute definition does not mark those fields. A missing/broken definition must never open the door.
- Raise **plain `application.base.ValidationError`** for the guardrail, never a subclass: `rest_api/views.py:_EXC_TO_HTTP` is keyed by *exact* exception type, so a `ValidationError` subclass silently degrades to a 500.
- Partial success everywhere else (spec §3): the response is `{"updated": [...], "failed": [{"id": ..., "error": ...}]}`; one failing item never aborts the batch.
- Bulk transitions go through `application.workflow_facade.WorkflowFacade().transition(...)` per item — full `allowed_roles` / `change_reason` / `signature_gate` gates per item, never a bulk shortcut and never a direct `status =` write.
- ADR-01: no ORM access in `rest_api/` or `mcp_server/`. `rest_api/tests/test_architecture.py` caps every new `*_views.py` at 0 direct-ORM lines and forbids importing `persistence.models`; `mcp_server/` root and `mcp_server/tools/` have their own ceilings. All ORM lives in `application/`.
- Every DRF view calls `get_auth_context(request)` first; every service calls `self._set_tenant_context(ctx)` before its first query (RLS depends on it).
- The filter DSL wire format (`filters` / `sort` JSON) is a public contract consumed later by the Dokumentensicht spec (`content_type="query"` sections). Its shape is frozen in Task 1 and must not change silently.
- Frontend: **no new inline `style={{`** anywhere under `frontend/src/components/`. `frontend/src/test/ui-ratchet.test.ts` asserts `expect(total).toBe(STYLE_BRACE_BASELINE)` — an *exact* equality, so a single new inline style block fails the build. Use CSS Modules with `var(--…)` tokens only.
- Frontend: reuse `components/shared/StatusBadge.tsx` for status cells. `STATUS_BADGE_IMPLEMENTATION_BASELINE = 1` in the same ratchet fails on a second status-badge implementation.
- `data-testid` on every interactive element (Playwright E2E requirement).
- i18n keys are **nested objects** in `frontend/src/i18n/locales/{de,en}.json`, never dotted flat keys (`keySeparator` is `"."`, so `"table.x"` as a literal key never resolves). `src/test/i18n-parity.test.ts` requires DE and EN to be structurally identical.
- MCP tool payloads are serialised with stdlib `json.dumps` — every value must already be a JSON primitive. `str()` UUIDs and `.isoformat()` datetimes before they leave the service.
- Test commands in this plan use these two shells (run from the repo root):
  ```bash
  BT() { docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml \
      --project-directory . run --rm -e DB_NAME=reqlo_tbl backend-test pytest "$@"; }
  FT() { docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml \
      --project-directory . run --rm frontend-test sh -c "npm install && npx vitest run $*"; }
  ```
  The unique `DB_NAME` avoids the `test_reqogniloom` collision when another session runs the suite in parallel.
- Never run the full backend suite or the full Playwright suite in the fix loop — only the modules touched. CI covers the matrix.
- Branch: `feat/tabellenansicht`. Conventional Commits, English messages.

---

## Dependencies on other specs

This is spec 9 of 11; specs 1–8 are implemented first. Two hard consumptions:

**From `2026-09-03-attribute-definition-design.md` (spec 2)** — the column/operator source. This plan touches that contract in exactly ONE place, `application/attribute_definition_access.py` (Task 1), so a naming drift in spec 2's plan costs a one-line edit:

```python
AttributeDefinitionService().resolve(ctx=ctx, workspace_id=workspace_id, item_type=item_type)
# -> {"attributes": [ {name, kind, type, options, required, visible, locked,
#                      editable, section, order, label, help_text, default,
#                      validation, ai_elicit, export, audience}, ... ]}
```

Frontend equivalent (Task 15): `GET /api/v1/workspaces/<id>/attribute-definitions/<item_type>/` returns the same `{"attributes": [...]}` body, and the field-component library lives at `frontend/src/components/shared/ArtifactForm/fields/` (`TextField`, `TextArea`, `EnumSelect`, `MultiEnum`, `BooleanToggle`, `DateField`, `ReferencePicker`, `UserPicker`).

**From `2026-09-03-interview-engine-fix-design.md` (spec 5)** — no code dependency, only the pattern: `application/interview_artifact_adapters.py`'s `ARTIFACT_CREATION_ADAPTERS` is copied in shape by `ARTIFACT_UPDATE_ADAPTERS` (Task 4).

## Scope decisions (deviations from the spec, each deliberate)

1. **`GET artifacts/table/`, not `GET artifacts/?item_type=…`.** The spec writes the latter, but `/api/v1/artifacts/` already exists (`ArtifactViewSet.list` → `list_child_summaries`, a tree-summary shape). Overloading one URL with two incompatible response schemas breaks drf-spectacular and every existing caller. A sibling path registered before `include(router.urls)` in `rest_api/urls.py` costs nothing and keeps both schemas honest.
2. **v1 filters/sorts/bulk-updates `kind: "core"` attributes only.** `kind: "extended"` values live in the separate `pl_custom_field_value` table; filtering/sorting across that join, and merging partial `custom_fields` dicts per item, is a second body of work. Extended fields in a `filters`/`sort`/`fields` payload are rejected with a 400 naming the field. Upgrade path: one join in `table_filter_dsl.compile_filters` plus a read-merge in the update adapters.
3. **`Goal` / `MainGoal` are excluded** from the table registry and both bulk registries. Goals are lineage-versioned (`GoalService.update` appends a NEW version); a table would list every historical version and a 40-item bulk update would fan out into 40 new versions. Documented in the registry, re-add when a `list_current`-backed spec exists.
4. **The spec's single-constraint-per-field filter shape cannot express a date range** (`date | gte, lte (Zeitraum)`, §4.1) — one object holds one `op`. Resolved by accepting **either** a single constraint object **or** a list of constraint objects per field, ANDed. The operator set is unchanged. This is the frozen wire format the Dokumentensicht spec consumes.
5. **`UserTableViewState` has no REST endpoint in the spec** although §4.2 requires the frontend to load/persist it. Added as `GET|PUT /api/v1/users/me/table-view-state/`, mirroring the existing `users/me/preferences/` shape in `rest_api/preference_views.py`.
6. **`editable: false` attributes are rejected from bulk update too**, with a different message than the workflow case. Missing `editable` counts as editable (permissive, matches the spec-2 "Bestandsschutz" tone).
7. **Column resize / reorder-by-drag / pinned first column** (spec §4.3 last bullet) are explicitly "hier nicht weiter spezifiziert" in the spec and are not planned. Column *selection* and *order* are (Task 19).

## File Structure

```
backend/
  application/
    attribute_definition_access.py        NEW  single seam onto spec 2's service
    table_filter_dsl.py                   NEW  filter/sort JSON -> Q + order_by
    table_query_service.py                NEW  item_type registry + query + row serialisation
    artifact_update_adapters.py           NEW  ARTIFACT_UPDATE_ADAPTERS registry
    bulk_edit_service.py                  NEW  guardrail + partial-success bulk update/transition
    saved_view_service.py                 NEW  SavedView CRUD + UserTableViewState upsert
    tests/
      test_table_filter_dsl.py            NEW
      test_table_query_service.py         NEW
      test_bulk_edit_service.py           NEW  <- the workflow guardrail proof
      test_saved_view_service.py          NEW
  persistence/
    models.py                             MOD  + UserTableViewState, + SavedView
    migrations/0070_table_views.py        NEW  CreateModel x2 + RLS enable/force
    tests/test_table_view_models.py       NEW
  rest_api/
    table_views.py                        NEW  7 endpoints, zero ORM
    urls.py                               MOD  7 paths before include(router.urls)
    tests/test_table_views.py             NEW
  mcp_server/
    tools/cross_cutting.py                MOD  + artifact.bulk_update / artifact.bulk_transition
    tools/saved_view.py                   NEW  saved_view.list / saved_view.apply
    tool_registry.py                      MOD  + "saved_view" group, + read-only names
    workspace_scope.py                    MOD  + read-tool classification
    tests/test_bulk_tools.py              NEW
    tests/test_saved_view_tools.py        NEW
frontend/src/
  api/table-views.ts                      NEW  types + wrappers
  components/shared/ArtifactTable/
    columnModel.ts                        NEW  pure: definition -> columns + operators
    ArtifactTable.tsx / .module.css       NEW  grid, sorting, status cell, inline edit
    ColumnFilterPopover.tsx               NEW  type-aware filter inputs
    ActiveFilterChips.tsx                 NEW
    ColumnPicker.tsx                      NEW  gear menu
    SavedViewBar.tsx                      NEW  dropdown + save dialog
    BulkActionBar.tsx                     NEW  selection actions + partial-success report
    useTableViewState.ts                  NEW  auto-persisted last state
    index.ts                              NEW  named re-exports
  components/RequirementEditors/
    RequirementEditors.tsx                MOD  list/table toggle (pilot page)
  i18n/locales/{de,en}.json               MOD  + "table" namespace
  test/
    tableColumnModel.test.ts              NEW
    ArtifactTable.test.tsx                NEW
    ArtifactTableBulk.test.tsx            NEW
    tableViewsApi.test.ts                 NEW
e2e/
  table-view-workflow-guardrail.spec.ts   NEW
```

---

## Task 1: Attribute-definition access seam

**Files:**
- Create: `backend/application/attribute_definition_access.py`
- Test: `backend/application/tests/test_table_filter_dsl.py` (the seam is exercised there in Task 2; this task only ships the module)

**Interfaces:**
- Consumes: `AttributeDefinitionService().resolve(ctx, workspace_id, item_type) -> dict` (spec 2, §5)
- Produces: `resolve_attributes(ctx, workspace_id, item_type) -> list[dict]`, `attribute_by_name(attributes, name) -> dict | None`

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_attribute_definition_access.py`:

```python
"""The single seam onto the Attribut-Definition spec's service."""
from __future__ import annotations

from uuid import uuid4

from application import attribute_definition_access as ada


def test_attribute_by_name_finds_entry():
    attributes = [{"name": "title", "type": "text"}, {"name": "status", "type": "enum"}]
    assert ada.attribute_by_name(attributes, "status")["type"] == "enum"


def test_attribute_by_name_returns_none_for_unknown():
    assert ada.attribute_by_name([{"name": "title"}], "nope") is None


def test_resolve_attributes_unwraps_the_attributes_key(monkeypatch):
    class _FakeService:
        def resolve(self, *, ctx, workspace_id, item_type):
            return {"attributes": [{"name": "title", "kind": "core", "type": "text"}]}

    monkeypatch.setattr(ada, "_service", lambda: _FakeService())
    result = ada.resolve_attributes(ctx=object(), workspace_id=uuid4(), item_type="Requirement")
    assert [a["name"] for a in result] == ["title"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `BT application/tests/test_attribute_definition_access.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.attribute_definition_access'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/application/attribute_definition_access.py`:

```python
"""Single seam onto the Attribut-Definition spec's resolved attribute list.

Every consumer in the Tabellenansicht feature (filter DSL, table query, bulk
edit, saved views) reads attributes through here, so the exact service method
name of ``2026-09-03-attribute-definition-design.md`` §5 is referenced in ONE
place. If that spec's plan names the resolver differently, only ``_service``
and the call below change.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext


def _service() -> Any:
    # Imported lazily: attribute_definitions is a Layer-1 app whose registry
    # must not be required at module import time (mirrors the lazy imports in
    # application/workspace_lookup.py).
    from attribute_definitions.services import AttributeDefinitionService

    return AttributeDefinitionService()


def resolve_attributes(
    ctx: AuthContext, workspace_id: UUID, item_type: str
) -> list[dict[str, Any]]:
    """Return the resolved ``definition_json.attributes`` for a workspace/type."""
    definition = _service().resolve(
        ctx=ctx, workspace_id=workspace_id, item_type=item_type
    )
    return list((definition or {}).get("attributes", []))


def attribute_by_name(
    attributes: list[dict[str, Any]], name: str
) -> Optional[dict[str, Any]]:
    """Return the attribute entry called *name*, or ``None``."""
    for attribute in attributes:
        if attribute.get("name") == name:
            return attribute
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `BT application/tests/test_attribute_definition_access.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/application/attribute_definition_access.py backend/application/tests/test_attribute_definition_access.py
git commit -m "feat(table): add attribute-definition access seam"
```

---

## Task 2: Filter/sort DSL compiler

**Files:**
- Create: `backend/application/table_filter_dsl.py`
- Test: `backend/application/tests/test_table_filter_dsl.py`

**Interfaces:**
- Consumes: `attribute_by_name()` from Task 1
- Produces: `FILTER_OPERATORS_BY_TYPE`, `allowed_operators(attribute) -> frozenset[str]`, `compile_filters(attributes, model, filters) -> Q`, `compile_sort(attributes, model, sort) -> tuple[str, ...]`, `MAX_IN_VALUES`, `MAX_SORT_TERMS`

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_table_filter_dsl.py`:

```python
"""Filter/sort DSL — the wire contract the Dokumentensicht spec also consumes."""
from __future__ import annotations

import pytest
from django.db.models import Q

from application.base import ValidationError
from application import table_filter_dsl as dsl
from persistence.models import Requirement

ATTRS = [
    {"name": "title", "kind": "core", "type": "text", "editable": True},
    {"name": "description", "kind": "core", "type": "textarea", "editable": True},
    {"name": "category", "kind": "core", "type": "enum", "editable": True},
    {"name": "status", "kind": "core", "type": "enum", "editable": "workflow"},
    {"name": "version", "kind": "core", "type": "number", "editable": False},
    {"name": "created_at", "kind": "core", "type": "date", "editable": False},
    {"name": "suspect", "kind": "core", "type": "boolean", "editable": True},
    {"name": "rpz_widget", "kind": "core", "type": "widget", "editable": True},
    {"name": "my_extra", "kind": "extended", "type": "text", "editable": True},
]


def test_operators_are_derived_from_type():
    assert dsl.allowed_operators(ATTRS[0]) == frozenset({"contains"})
    assert dsl.allowed_operators(ATTRS[2]) == frozenset({"in"})
    assert dsl.allowed_operators(ATTRS[4]) == frozenset({"gte", "lte"})
    assert dsl.allowed_operators(ATTRS[5]) == frozenset({"gte", "lte"})
    assert dsl.allowed_operators(ATTRS[6]) == frozenset({"eq"})


def test_workflow_owned_field_is_filterable_with_in():
    """Spec §4.1: filtering status is reading, not writing — explicitly allowed."""
    assert dsl.allowed_operators(ATTRS[3]) == frozenset({"in"})


def test_widget_type_has_no_operators():
    assert dsl.allowed_operators(ATTRS[7]) == frozenset()


def test_compile_filters_builds_expected_lookups():
    q = dsl.compile_filters(ATTRS, Requirement, {"title": {"op": "contains", "value": "brake"}})
    assert q == Q(title__icontains="brake")


def test_compile_filters_accepts_a_constraint_list_for_ranges():
    q = dsl.compile_filters(
        ATTRS,
        Requirement,
        {"created_at": [{"op": "gte", "value": "2026-01-01"}, {"op": "lte", "value": "2026-02-01"}]},
    )
    assert q == Q(created_at__gte="2026-01-01") & Q(created_at__lte="2026-02-01")


def test_compile_filters_rejects_unknown_field():
    with pytest.raises(ValidationError) as exc:
        dsl.compile_filters(ATTRS, Requirement, {"nope": {"op": "contains", "value": "x"}})
    assert "nope" in str(exc.value)


def test_compile_filters_rejects_disallowed_operator():
    with pytest.raises(ValidationError) as exc:
        dsl.compile_filters(ATTRS, Requirement, {"title": {"op": "gte", "value": "x"}})
    assert "gte" in str(exc.value)


def test_compile_filters_rejects_extended_field():
    with pytest.raises(ValidationError) as exc:
        dsl.compile_filters(ATTRS, Requirement, {"my_extra": {"op": "contains", "value": "x"}})
    assert "my_extra" in str(exc.value)


def test_compile_filters_rejects_orm_traversal_in_a_name():
    attrs = ATTRS + [{"name": "artifact__workspace__tenant", "kind": "core", "type": "text"}]
    with pytest.raises(ValidationError):
        dsl.compile_filters(attrs, Requirement, {"artifact__workspace__tenant": {"op": "contains", "value": "x"}})


def test_compile_filters_rejects_oversized_in_list():
    values = [f"v{i}" for i in range(dsl.MAX_IN_VALUES + 1)]
    with pytest.raises(ValidationError):
        dsl.compile_filters(ATTRS, Requirement, {"category": {"op": "in", "value": values}})


def test_compile_sort_builds_order_by():
    assert dsl.compile_sort(
        ATTRS, Requirement, [{"field": "category", "dir": "desc"}, {"field": "title", "dir": "asc"}]
    ) == ("-category", "title")


def test_compile_sort_rejects_bad_direction():
    with pytest.raises(ValidationError):
        dsl.compile_sort(ATTRS, Requirement, [{"field": "title", "dir": "sideways"}])


def test_compile_sort_rejects_too_many_terms():
    terms = [{"field": "title", "dir": "asc"}] * (dsl.MAX_SORT_TERMS + 1)
    with pytest.raises(ValidationError):
        dsl.compile_sort(ATTRS, Requirement, terms)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `BT application/tests/test_table_filter_dsl.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.table_filter_dsl'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/application/table_filter_dsl.py`:

```python
"""Type-aware filter/sort DSL for the table view (spec §4.1).

Wire format — FROZEN, also consumed by the Dokumentensicht spec's
``content_type="query"`` document sections::

    filters := {"<attribute>": <constraint> | [<constraint>, ...], ...}
    constraint := {"op": "contains"|"in"|"gte"|"lte"|"eq", "value": <scalar|list>}
    sort := [{"field": "<attribute>", "dir": "asc"|"desc"}, ...]

Several constraints on one field are ANDed — that is how a date/number range
is expressed, since one constraint object carries exactly one operator. The
spec's operator table (§4.1) is unchanged by this; it only says a ``date`` may
use ``gte`` *and* ``lte``, which the single-object form cannot encode.

Security: attribute names are matched against the model's own concrete fields
via ``_meta.get_field``. A definition entry naming an ORM traversal
(``artifact__workspace__tenant_id``) is rejected rather than compiled, so a
tampered definition cannot turn a filter into a cross-tenant join.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from django.contrib.postgres.fields import ArrayField
from django.db.models import Model, Q

from application.attribute_definition_access import attribute_by_name
from application.base import ValidationError

#: Hard ceiling for a single ``in`` list — an unbounded IN is a cheap DoS.
MAX_IN_VALUES = 200
#: Hard ceiling for multi-sort terms.
MAX_SORT_TERMS = 5

ALL_OPERATORS: frozenset[str] = frozenset({"contains", "in", "gte", "lte", "eq"})

#: Spec §4.1, verbatim. A type absent here is not filterable (e.g. ``widget``).
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
}

_OP_TO_LOOKUP: dict[str, str] = {
    "contains": "icontains",
    "in": "in",
    "gte": "gte",
    "lte": "lte",
    "eq": "exact",
}


def allowed_operators(attribute: Mapping[str, Any]) -> frozenset[str]:
    """Operators permitted for one attribute (spec §4.1).

    ``editable: "workflow"`` (the status field) always gets ``in`` regardless
    of its declared type — filtering is a read and does not touch the §2
    guardrail.
    """
    if attribute.get("editable") == "workflow":
        return frozenset({"in"})
    return FILTER_OPERATORS_BY_TYPE.get(str(attribute.get("type", "")), frozenset())


def _concrete_field(model: type[Model], name: str) -> Any:
    if "__" in name or "." in name:
        raise ValidationError(f"Filter field '{name}' is not a plain column name")
    try:
        return model._meta.get_field(name)
    except Exception:
        raise ValidationError(f"Filter field '{name}' does not exist on {model.__name__}")


def _resolve(attributes: Sequence[Mapping[str, Any]], model: type[Model], name: str) -> tuple[dict, Any]:
    attribute = attribute_by_name(list(attributes), name)
    if attribute is None:
        raise ValidationError(f"Unknown field '{name}' for this item type")
    if attribute.get("kind") != "core":
        raise ValidationError(
            f"Field '{name}' is an extended attribute and is not filterable or sortable yet"
        )
    return dict(attribute), _concrete_field(model, name)


def _as_constraints(raw: Any, name: str) -> list[Mapping[str, Any]]:
    items: Iterable[Any] = raw if isinstance(raw, list) else [raw]
    constraints: list[Mapping[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or "op" not in item:
            raise ValidationError(
                f"Filter for '{name}' must be an object with 'op' and 'value', or a list of them"
            )
        constraints.append(item)
    return constraints


def compile_filters(
    attributes: Sequence[Mapping[str, Any]], model: type[Model], filters: Mapping[str, Any] | None
) -> Q:
    """Compile the ``filters`` payload into a single ANDed ``Q``."""
    combined = Q()
    if not filters:
        return combined
    if not isinstance(filters, dict):
        raise ValidationError("'filters' must be a JSON object")
    for name, raw in filters.items():
        attribute, field = _resolve(attributes, model, name)
        permitted = allowed_operators(attribute)
        for constraint in _as_constraints(raw, name):
            op = str(constraint.get("op"))
            if op not in permitted:
                raise ValidationError(
                    f"Operator '{op}' is not allowed for field '{name}'. "
                    f"Allowed: {sorted(permitted) or 'none (field is not filterable)'}"
                )
            value = constraint.get("value")
            if op == "in":
                if not isinstance(value, list):
                    raise ValidationError(f"Operator 'in' on '{name}' needs a list value")
                if len(value) > MAX_IN_VALUES:
                    raise ValidationError(
                        f"Filter on '{name}' has {len(value)} values, maximum is {MAX_IN_VALUES}"
                    )
                # A multi-enum core field is an array column: "one of these
                # values is present" is __overlap, not __in (which would test
                # the whole array against the list).
                lookup = "overlap" if isinstance(field, ArrayField) else "in"
            else:
                lookup = _OP_TO_LOOKUP[op]
            combined &= Q(**{f"{name}__{lookup}": value})
    return combined


def compile_sort(
    attributes: Sequence[Mapping[str, Any]], model: type[Model], sort: Sequence[Mapping[str, Any]] | None
) -> tuple[str, ...]:
    """Compile the ``sort`` payload into ``order_by`` arguments."""
    if not sort:
        return ()
    if not isinstance(sort, list):
        raise ValidationError("'sort' must be a JSON array")
    if len(sort) > MAX_SORT_TERMS:
        raise ValidationError(f"At most {MAX_SORT_TERMS} sort terms are supported")
    terms: list[str] = []
    for entry in sort:
        if not isinstance(entry, dict):
            raise ValidationError("Each sort term must be an object with 'field' and 'dir'")
        name = str(entry.get("field", ""))
        _resolve(attributes, model, name)
        direction = str(entry.get("dir", "asc"))
        if direction not in ("asc", "desc"):
            raise ValidationError(f"Sort direction must be 'asc' or 'desc', got '{direction}'")
        terms.append(f"-{name}" if direction == "desc" else name)
    return tuple(terms)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `BT application/tests/test_table_filter_dsl.py -v`
Expected: PASS (13 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/application/table_filter_dsl.py backend/application/tests/test_table_filter_dsl.py
git commit -m "feat(table): add type-aware filter and sort DSL compiler"
```

---

## Task 3: Table query service

**Files:**
- Create: `backend/application/table_query_service.py`
- Test: `backend/application/tests/test_table_query_service.py`

**Interfaces:**
- Consumes: `compile_filters`, `compile_sort` (Task 2), `resolve_attributes` (Task 1), `application.workspace_lookup.ENTITY_SPECS` / `import_entity_model`
- Produces: `TABLE_ITEM_TYPES: dict[str, str]`, `TableQueryService.query(...) -> QuerySet`, `TableQueryService.serialize_rows(...) -> list[dict]`, `jsonable(value) -> Any`

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_table_query_service.py`:

```python
"""Generic per-item_type table query."""
from __future__ import annotations

import uuid

import pytest

from application.base import ValidationError
from application import table_query_service as tqs
from auth_tenancy.context import AuthContext
from persistence.models import Artifact, Requirement, Tenant, Workspace
from persistence.tenancy import TenantContext

ATTRS = [
    {"name": "title", "kind": "core", "type": "text", "editable": True, "visible": True, "order": 1},
    {"name": "category", "kind": "core", "type": "enum", "editable": True, "visible": True, "order": 2},
    {"name": "status", "kind": "core", "type": "enum", "editable": "workflow", "visible": True, "order": 3},
]


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="T", slug=f"t-{uuid.uuid4().hex[:8]}", is_active=True)


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="WS")
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def ctx(tenant: Tenant, workspace: Workspace) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method="test",
        workspace_id=workspace.id,
    )


def _requirement(tenant, workspace, **kwargs) -> Requirement:
    TenantContext.set_tenant(tenant.id)
    try:
        art = Artifact.objects.create(tenant=tenant, workspace=workspace, artifact_type="Requirement")
        return Requirement.objects.create(tenant=tenant, artifact=art, **kwargs)
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_query_filters_and_sorts(ctx, tenant, workspace, monkeypatch):
    monkeypatch.setattr(tqs, "resolve_attributes", lambda ctx, workspace_id, item_type: ATTRS)
    _requirement(tenant, workspace, title="Brake force", category="functional", status="draft")
    _requirement(tenant, workspace, title="Brake wear", category="safety", status="draft")
    _requirement(tenant, workspace, title="Cabin light", category="functional", status="draft")

    rows = list(
        tqs.TableQueryService().query(
            ctx=ctx,
            workspace_id=workspace.id,
            item_type="Requirement",
            filters={"title": {"op": "contains", "value": "brake"}},
            sort=[{"field": "title", "dir": "desc"}],
        )
    )
    assert [r.title for r in rows] == ["Brake wear", "Brake force"]


@pytest.mark.django_db
def test_query_excludes_soft_deleted_by_default(ctx, tenant, workspace, monkeypatch):
    monkeypatch.setattr(tqs, "resolve_attributes", lambda ctx, workspace_id, item_type: ATTRS)
    _requirement(tenant, workspace, title="Live", status="draft")
    _requirement(tenant, workspace, title="Gone", status="outdated")
    rows = list(
        tqs.TableQueryService().query(ctx=ctx, workspace_id=workspace.id, item_type="Requirement")
    )
    assert [r.title for r in rows] == ["Live"]


@pytest.mark.django_db
def test_query_rejects_unsupported_item_type(ctx, workspace):
    with pytest.raises(ValidationError) as exc:
        tqs.TableQueryService().query(ctx=ctx, workspace_id=workspace.id, item_type="Goal")
    assert "Goal" in str(exc.value)


@pytest.mark.django_db
def test_serialize_rows_returns_json_primitives(ctx, tenant, workspace, monkeypatch):
    monkeypatch.setattr(tqs, "resolve_attributes", lambda ctx, workspace_id, item_type: ATTRS)
    _requirement(tenant, workspace, title="Brake force", category="functional", status="draft")
    qs = tqs.TableQueryService().query(ctx=ctx, workspace_id=workspace.id, item_type="Requirement")
    rows = tqs.TableQueryService().serialize_rows(
        ctx=ctx, workspace_id=workspace.id, item_type="Requirement", rows=qs, columns=["title", "status"]
    )
    assert rows[0]["title"] == "Brake force"
    assert rows[0]["status"] == "draft"
    assert isinstance(rows[0]["id"], str)
    assert isinstance(rows[0]["artifact_id"], str)
    import json

    json.dumps(rows)  # must not raise — the MCP transport uses stdlib json


def test_jsonable_stringifies_uuid_and_datetime():
    from datetime import datetime

    assert tqs.jsonable(uuid.UUID(int=1)) == "00000000-0000-0000-0000-000000000001"
    assert tqs.jsonable(datetime(2026, 9, 3, 12, 0)).startswith("2026-09-03T12:00")
    assert tqs.jsonable(["a", 1, True]) == ["a", 1, True]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `BT application/tests/test_table_query_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.table_query_service'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/application/table_query_service.py`:

```python
"""Generic, item_type-parameterised query behind the table view (spec §4).

The per-type model + workspace column are NOT re-declared here: they already
exist in ``application/workspace_lookup.ENTITY_SPECS``, which the MCP RBAC gate
maintains. ``TABLE_ITEM_TYPES`` only maps the public ``item_type`` string onto
that registry's key.

Goal/MainGoal are deliberately absent: they are lineage-versioned (every edit
appends a row), so a plain model query would list every historical version.
Re-add once a ``list_current``-backed path exists.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence
from uuid import UUID

from django.db.models import Model, QuerySet

from application.attribute_definition_access import resolve_attributes
from application.base import ServiceBase, ValidationError
from application.table_filter_dsl import compile_filters, compile_sort
from application.workspace_lookup import ENTITY_SPECS, import_entity_model
from auth_tenancy.context import AuthContext

#: Public ``item_type`` -> ``workspace_lookup.ENTITY_SPECS`` key.
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

#: Universal soft-delete state written by ``workflow.services.outdate``.
_OUTDATED = "outdated"


def jsonable(value: Any) -> Any:
    """Coerce a model attribute into something ``json.dumps`` accepts.

    The MCP transport serialises tool payloads with stdlib ``json``, which has
    no encoder for UUID/datetime/Decimal — DRF hides that on the REST side, so
    the coercion has to happen here, before either boundary.
    """
    if isinstance(value, (uuid.UUID,)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def model_for(item_type: str) -> type[Model]:
    """Return the Django model backing *item_type*, or raise ValidationError."""
    key = TABLE_ITEM_TYPES.get(item_type)
    if key is None:
        raise ValidationError(
            f"Item type '{item_type}' has no table view. "
            f"Supported: {sorted(TABLE_ITEM_TYPES)}"
        )
    return import_entity_model(ENTITY_SPECS[key].model_path)


def _workspace_field(item_type: str) -> str:
    return ENTITY_SPECS[TABLE_ITEM_TYPES[item_type]].workspace_field


class TableQueryService(ServiceBase):
    """Filter/sort artifacts of one type for the table view."""

    def query(
        self,
        *,
        ctx: AuthContext,
        workspace_id: UUID,
        item_type: str,
        filters: Mapping[str, Any] | None = None,
        sort: Sequence[Mapping[str, Any]] | None = None,
    ) -> QuerySet:
        """Return a lazy QuerySet of *item_type* rows in *workspace_id*."""
        self._set_tenant_context(ctx)
        model = model_for(item_type)
        attributes = resolve_attributes(ctx, workspace_id, item_type)

        qs = model.objects.filter(**{_workspace_field(item_type): workspace_id})
        # Mirrors RequirementService.list_requirements: soft-deleted rows carry
        # status="outdated" and stay hidden unless the caller filters on status
        # explicitly.
        filters_on_status = bool(filters) and "status" in (filters or {})
        if not filters_on_status:
            try:
                model._meta.get_field("status")
            except Exception:
                pass
            else:
                qs = qs.exclude(status=_OUTDATED)

        qs = qs.filter(compile_filters(attributes, model, filters))
        order_by = compile_sort(attributes, model, sort)
        return qs.order_by(*order_by) if order_by else qs.order_by("-created_at")

    def serialize_rows(
        self,
        *,
        ctx: AuthContext,
        workspace_id: UUID,
        item_type: str,
        rows: Iterable[Any],
        columns: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Serialise *rows* to plain dicts carrying ``id``, ``artifact_id`` and
        the requested columns (default: every visible core attribute)."""
        attributes = resolve_attributes(ctx, workspace_id, item_type)
        core = [a for a in attributes if a.get("kind") == "core"]
        if columns is None:
            names = [a["name"] for a in sorted(core, key=lambda a: a.get("order", 0)) if a.get("visible", True)]
        else:
            known = {a["name"] for a in core}
            unknown = [c for c in columns if c not in known]
            if unknown:
                raise ValidationError(f"Unknown column(s): {', '.join(sorted(unknown))}")
            names = list(columns)

        out: list[dict[str, Any]] = []
        for row in rows:
            record: dict[str, Any] = {
                "id": str(row.id),
                "artifact_id": str(getattr(row, "artifact_id", None) or "") or None,
                "version": getattr(row, "version", None),
            }
            for name in names:
                record[name] = jsonable(getattr(row, name, None))
            out.append(record)
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `BT application/tests/test_table_query_service.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/application/table_query_service.py backend/application/tests/test_table_query_service.py
git commit -m "feat(table): add generic item-type table query service"
```

---

## Task 4: ARTIFACT_UPDATE_ADAPTERS registry

**Files:**
- Create: `backend/application/artifact_update_adapters.py`
- Test: `backend/application/tests/test_artifact_update_adapters.py`

**Interfaces:**
- Consumes: the eight existing `update_X()` services
- Produces: `ARTIFACT_UPDATE_ADAPTERS: dict[str, UpdateAdapter]`, `UpdateAdapter`, `updatable_fields_for(item_type) -> frozenset[str]`, `WORKFLOW_OWNED_FALLBACK`

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_artifact_update_adapters.py`:

```python
"""ARTIFACT_UPDATE_ADAPTERS — the update-side twin of ARTIFACT_CREATION_ADAPTERS."""
from __future__ import annotations

import pytest

from application.artifact_update_adapters import (
    ARTIFACT_UPDATE_ADAPTERS,
    WORKFLOW_OWNED_FALLBACK,
    updatable_fields_for,
)
from application.table_query_service import TABLE_ITEM_TYPES


def test_registry_covers_exactly_the_table_item_types():
    assert set(ARTIFACT_UPDATE_ADAPTERS) == set(TABLE_ITEM_TYPES)


def test_updatable_fields_are_derived_from_the_service_signature():
    fields = updatable_fields_for("Requirement")
    assert {"title", "description", "category", "verification_method"} <= fields


def test_workflow_owned_fields_are_never_updatable():
    """Belt to the guardrail's braces: even a bypassed check finds no kwarg."""
    for item_type in ARTIFACT_UPDATE_ADAPTERS:
        assert not (updatable_fields_for(item_type) & WORKFLOW_OWNED_FALLBACK)


def test_plumbing_kwargs_are_not_offered_as_fields():
    fields = updatable_fields_for("Requirement")
    assert "ctx" not in fields
    assert "expected_version" not in fields
    assert "requirement_id" not in fields
    assert "custom_fields" not in fields


def test_unknown_item_type_raises():
    with pytest.raises(KeyError):
        updatable_fields_for("Nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `BT application/tests/test_artifact_update_adapters.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.artifact_update_adapters'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/application/artifact_update_adapters.py`:

```python
"""Adapter registry: bulk update -> the existing, production ``update_X()`` service.

Same contract as ``application/interview_artifact_adapters.py``: every entry
MUST call the real service method, never a shortcut ``.update()`` — that is
what keeps preset change_reason policy, optimistic-lock plumbing, free-text
sanitisation, audit writes and version bumps correct for free.

``updatable_fields`` is derived from the service signature rather than
re-declared, so a new kwarg on ``update_requirement()`` becomes bulk-editable
without touching this file — minus the plumbing kwargs and minus
``WORKFLOW_OWNED_FALLBACK``, which is subtracted unconditionally so that even a
bypassed guardrail (see ``bulk_edit_service``) finds no kwarg to write status
through.

Goal/MainGoal are absent on purpose: ``GoalService.update`` appends a NEW
lineage version, so a 40-item bulk update would create 40 new versions rather
than edit 40 rows.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable
from uuid import UUID

from application.adr_service import AdrService
from application.architecture_service import ArchitectureService
from application.glossary_service import GlossaryService
from application.issue_service import IssueService
from application.requirement_service import RequirementService
from application.risk_service import RiskService
from application.stakeholder_need_service import StakeholderNeedService
from application.test_service import TestService
from auth_tenancy.context import AuthContext

#: Fields the WorkflowEngine owns. Never bulk-writable, whatever the
#: attribute definition says (spec §2).
WORKFLOW_OWNED_FALLBACK: frozenset[str] = frozenset({"status", "lifecycle_status"})

#: Kwargs that are plumbing, not user-editable attributes.
_PLUMBING = frozenset({"self", "ctx", "expected_version", "change_reason", "custom_fields"})


def _fields_of(fn: Callable[..., Any], id_param: str) -> frozenset[str]:
    names = set(inspect.signature(fn).parameters)
    return frozenset(names - _PLUMBING - {id_param} - WORKFLOW_OWNED_FALLBACK)


@dataclass(frozen=True)
class UpdateAdapter:
    """One item type's bulk-update entry point.

    Attributes:
        call: ``(entity_id, fields, ctx, change_reason) -> Any``; raises the
            service's own ValidationError/NotFoundError/PermissionDeniedError.
        updatable_fields: attribute names this adapter accepts.
    """

    call: Callable[[UUID, dict, AuthContext, str], Any]
    updatable_fields: frozenset[str]


def _requirement(entity_id: UUID, fields: dict, ctx: AuthContext, change_reason: str) -> Any:
    return RequirementService().update_requirement(
        requirement_id=entity_id, ctx=ctx, change_reason=change_reason or None, **fields
    )


def _need(entity_id: UUID, fields: dict, ctx: AuthContext, change_reason: str) -> Any:
    return StakeholderNeedService().update(
        ctx=ctx, need_id=entity_id, change_reason=change_reason, **fields
    )


def _architecture(entity_id: UUID, fields: dict, ctx: AuthContext, change_reason: str) -> Any:
    # No change_reason kwarg on this service (verified 2026-09-03).
    return ArchitectureService().update_architecture_element(
        arch_el_id=entity_id, ctx=ctx, **fields
    )


def _test_case(entity_id: UUID, fields: dict, ctx: AuthContext, change_reason: str) -> Any:
    return TestService().update_test_case(test_case_id=entity_id, ctx=ctx, **fields)


def _adr(entity_id: UUID, fields: dict, ctx: AuthContext, change_reason: str) -> Any:
    return AdrService().update_adr(
        adr_id=entity_id, ctx=ctx, change_reason=change_reason or None, **fields
    )


def _risk(entity_id: UUID, fields: dict, ctx: AuthContext, change_reason: str) -> Any:
    return RiskService().update_risk(
        risk_id=entity_id, ctx=ctx, change_reason=change_reason or None, **fields
    )


def _issue(entity_id: UUID, fields: dict, ctx: AuthContext, change_reason: str) -> Any:
    return IssueService().update_issue(
        issue_id=entity_id, ctx=ctx, change_reason=change_reason or None, **fields
    )


def _glossary(entity_id: UUID, fields: dict, ctx: AuthContext, change_reason: str) -> Any:
    return GlossaryService().update(ctx=ctx, term_id=entity_id, **fields)


ARTIFACT_UPDATE_ADAPTERS: dict[str, UpdateAdapter] = {
    "Requirement": UpdateAdapter(
        _requirement, _fields_of(RequirementService.update_requirement, "requirement_id")
    ),
    "StakeholderNeed": UpdateAdapter(
        _need, _fields_of(StakeholderNeedService.update, "need_id")
    ),
    "ArchitectureElement": UpdateAdapter(
        _architecture, _fields_of(ArchitectureService.update_architecture_element, "arch_el_id")
    ),
    "TestCase": UpdateAdapter(
        _test_case, _fields_of(TestService.update_test_case, "test_case_id")
    ),
    "Adr": UpdateAdapter(_adr, _fields_of(AdrService.update_adr, "adr_id")),
    "Risk": UpdateAdapter(_risk, _fields_of(RiskService.update_risk, "risk_id")),
    "Issue": UpdateAdapter(_issue, _fields_of(IssueService.update_issue, "issue_id")),
    "GlossaryTerm": UpdateAdapter(_glossary, _fields_of(GlossaryService.update, "term_id")),
}


def updatable_fields_for(item_type: str) -> frozenset[str]:
    """Return the bulk-updatable field names for *item_type*."""
    return ARTIFACT_UPDATE_ADAPTERS[item_type].updatable_fields
```

- [ ] **Step 4: Run test to verify it passes**

Run: `BT application/tests/test_artifact_update_adapters.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/application/artifact_update_adapters.py backend/application/tests/test_artifact_update_adapters.py
git commit -m "feat(table): add ARTIFACT_UPDATE_ADAPTERS registry"
```

---

## Task 5: Workflow guardrail — the one enforcement point

**Files:**
- Create: `backend/application/bulk_edit_service.py` (guard only; the bulk methods land in Tasks 6 and 7)
- Test: `backend/application/tests/test_bulk_edit_service.py`

**Interfaces:**
- Consumes: `attribute_by_name` (Task 1), `WORKFLOW_OWNED_FALLBACK`, `updatable_fields_for` (Task 4)
- Produces: `assert_no_workflow_owned_fields(attributes, fields) -> None`, `assert_fields_are_updatable(item_type, fields) -> None`, `MAX_BULK_IDS`

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_bulk_edit_service.py`:

```python
"""Spec §2 guardrail: editable:"workflow" fields are never bulk-writable."""
from __future__ import annotations

import pytest

from application.base import ValidationError
from application.bulk_edit_service import (
    assert_fields_are_updatable,
    assert_no_workflow_owned_fields,
)

ATTRS = [
    {"name": "title", "kind": "core", "type": "text", "editable": True},
    {"name": "category", "kind": "core", "type": "enum", "editable": True},
    {"name": "status", "kind": "core", "type": "enum", "editable": "workflow", "locked": True},
    {"name": "version", "kind": "core", "type": "number", "editable": False},
]


def test_plain_fields_pass():
    assert_no_workflow_owned_fields(ATTRS, {"title": "x", "category": "functional"})


def test_workflow_owned_field_is_rejected():
    with pytest.raises(ValidationError) as exc:
        assert_no_workflow_owned_fields(ATTRS, {"title": "x", "status": "approved"})
    message = str(exc.value)
    assert "status" in message
    assert "bulk-transition" in message


def test_rejection_is_a_plain_validation_error_not_a_subclass():
    """rest_api._EXC_TO_HTTP is keyed by EXACT type — a subclass would 500."""
    with pytest.raises(ValidationError) as exc:
        assert_no_workflow_owned_fields(ATTRS, {"status": "approved"})
    assert type(exc.value) is ValidationError


def test_status_is_rejected_even_when_the_definition_omits_it():
    """Fail-closed: a broken/incomplete definition must not open the door."""
    with pytest.raises(ValidationError) as exc:
        assert_no_workflow_owned_fields([{"name": "title", "kind": "core", "editable": True}],
                                        {"status": "approved"})
    assert "status" in str(exc.value)


def test_lifecycle_status_is_rejected_too():
    with pytest.raises(ValidationError):
        assert_no_workflow_owned_fields(ATTRS, {"lifecycle_status": "deleted"})


def test_non_editable_field_is_rejected_with_its_own_message():
    with pytest.raises(ValidationError) as exc:
        assert_no_workflow_owned_fields(ATTRS, {"version": 3})
    message = str(exc.value)
    assert "version" in message
    assert "bulk-transition" not in message


def test_assert_fields_are_updatable_rejects_unknown_kwarg():
    with pytest.raises(ValidationError) as exc:
        assert_fields_are_updatable("Requirement", {"not_a_field": 1})
    assert "not_a_field" in str(exc.value)


def test_assert_fields_are_updatable_accepts_a_real_field():
    assert_fields_are_updatable("Requirement", {"title": "x"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `BT application/tests/test_bulk_edit_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.bulk_edit_service'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/application/bulk_edit_service.py`:

```python
"""Bulk update / bulk transition (spec §3) with the §2 workflow guardrail.

THE GUARDRAIL LIVES HERE AND NOWHERE ELSE. REST (``rest_api/table_views.py``)
and MCP (``mcp_server/tools/cross_cutting.py``) both route through
``BulkEditService``, so the check cannot drift between the two boundaries.

Rejection uses a plain ``application.base.ValidationError``: the REST mapper
``rest_api/views.py:_EXC_TO_HTTP`` is keyed by *exact* exception type, so a
subclass would silently degrade to a 500 instead of the required 400.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from application.artifact_update_adapters import (
    ARTIFACT_UPDATE_ADAPTERS,
    WORKFLOW_OWNED_FALLBACK,
    updatable_fields_for,
)
from application.attribute_definition_access import attribute_by_name
from application.base import ServiceBase, ValidationError

#: Ceiling for one bulk call — each id costs a full service round-trip.
MAX_BULK_IDS = 200


def assert_no_workflow_owned_fields(
    attributes: Sequence[Mapping[str, Any]], fields: Mapping[str, Any]
) -> None:
    """Reject any field the workflow engine owns, or that is not editable.

    Spec §2: "Felder mit ``editable: "workflow"`` (allen voran Status) sind
    über Tabellen-Zellen, Inline-Edit oder Bulk-Update NIEMALS direkt
    schreibbar" — a hard 400 for the whole request, no partial success
    (spec §3.1).

    Two independent sources decide, and either one is enough to reject:

    1. the resolved attribute definition (``editable == "workflow"``), and
    2. :data:`WORKFLOW_OWNED_FALLBACK`, applied unconditionally so a missing
       or malformed definition cannot open the door.
    """
    attribute_list = list(attributes)
    workflow_owned = sorted(
        name
        for name in fields
        if name in WORKFLOW_OWNED_FALLBACK
        or (attribute_by_name(attribute_list, name) or {}).get("editable") == "workflow"
    )
    if workflow_owned:
        raise ValidationError(
            "Fields owned by the workflow engine cannot be bulk-updated: "
            f"{', '.join(workflow_owned)}. Use artifacts/bulk-transition/ "
            "(or POST <entity>/{id}/transitions/) instead."
        )

    read_only = sorted(
        name
        for name in fields
        if (attribute_by_name(attribute_list, name) or {}).get("editable") is False
    )
    if read_only:
        raise ValidationError(
            f"Fields are not editable and cannot be bulk-updated: {', '.join(read_only)}."
        )


def assert_fields_are_updatable(item_type: str, fields: Mapping[str, Any]) -> None:
    """Reject fields the item type's update service has no kwarg for."""
    adapter = ARTIFACT_UPDATE_ADAPTERS.get(item_type)
    if adapter is None:
        raise ValidationError(
            f"Item type '{item_type}' does not support bulk update. "
            f"Supported: {sorted(ARTIFACT_UPDATE_ADAPTERS)}"
        )
    unknown = sorted(set(fields) - updatable_fields_for(item_type))
    if unknown:
        raise ValidationError(
            f"Field(s) not updatable for {item_type}: {', '.join(unknown)}. "
            f"Allowed: {sorted(updatable_fields_for(item_type))}"
        )


class BulkEditService(ServiceBase):
    """Bulk update / transition across the ARTIFACT_UPDATE_ADAPTERS registry."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `BT application/tests/test_bulk_edit_service.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/application/bulk_edit_service.py backend/application/tests/test_bulk_edit_service.py
git commit -m "feat(table): enforce workflow-owned fields are never bulk-writable"
```

---

## Task 6: BulkEditService.bulk_update

**Files:**
- Modify: `backend/application/bulk_edit_service.py` (add `BulkResult`, `BulkItemFailure`, `bulk_update`)
- Test: `backend/application/tests/test_bulk_edit_service_update.py`

**Interfaces:**
- Consumes: `assert_no_workflow_owned_fields`, `assert_fields_are_updatable`, `ARTIFACT_UPDATE_ADAPTERS` (Tasks 4–5), `resolve_attributes` (Task 1), `resolve_owning_workspace_id` + `TABLE_ITEM_TYPES` (Task 3)
- Produces: `BulkItemFailure`, `BulkResult.as_dict() -> dict`, `BulkEditService.bulk_update(...) -> BulkResult`

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_bulk_edit_service_update.py`:

```python
"""bulk_update: guardrail first, then partial success."""
from __future__ import annotations

import uuid

import pytest

from application import bulk_edit_service as bes
from application.base import ValidationError
from application.bulk_edit_service import BulkEditService
from auth_tenancy.context import AuthContext
from persistence.models import Artifact, Requirement, Tenant, Workspace
from persistence.tenancy import TenantContext

ATTRS = [
    {"name": "title", "kind": "core", "type": "text", "editable": True},
    {"name": "category", "kind": "core", "type": "enum", "editable": True},
    {"name": "status", "kind": "core", "type": "enum", "editable": "workflow"},
]


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="T", slug=f"t-{uuid.uuid4().hex[:8]}", is_active=True)


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="WS", preset={"tier": "standard"})
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def ctx(tenant: Tenant, workspace: Workspace) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method="test",
        workspace_id=workspace.id,
    )


@pytest.fixture
def requirements(tenant, workspace):
    TenantContext.set_tenant(tenant.id)
    try:
        made = []
        for title in ("A", "B"):
            art = Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="Requirement"
            )
            made.append(
                Requirement.objects.create(
                    tenant=tenant, artifact=art, title=title, status="draft"
                )
            )
        return made
    finally:
        TenantContext.clear_tenant()


@pytest.fixture(autouse=True)
def _stub_attributes(monkeypatch):
    monkeypatch.setattr(bes, "resolve_attributes", lambda ctx, workspace_id, item_type: ATTRS)


@pytest.mark.django_db
def test_bulk_update_applies_plain_fields(ctx, workspace, requirements):
    result = BulkEditService().bulk_update(
        ctx=ctx,
        workspace_id=workspace.id,
        item_type="Requirement",
        ids=[r.id for r in requirements],
        fields={"category": "functional"},
    )
    assert sorted(result.updated) == sorted(str(r.id) for r in requirements)
    assert result.failed == []
    for r in requirements:
        r.refresh_from_db()
        assert r.category == "functional"


@pytest.mark.django_db
def test_bulk_update_rejects_workflow_owned_field_with_no_partial_write(
    ctx, workspace, requirements
):
    """The spec §2 leitplanke, proven end to end at the service boundary."""
    with pytest.raises(ValidationError) as exc:
        BulkEditService().bulk_update(
            ctx=ctx,
            workspace_id=workspace.id,
            item_type="Requirement",
            ids=[r.id for r in requirements],
            fields={"title": "Renamed", "status": "approved"},
        )
    assert "status" in str(exc.value)
    # Nothing was written — not even the legitimate field in the same payload.
    for r in requirements:
        r.refresh_from_db()
        assert r.title in ("A", "B")
        assert r.status == "draft"


@pytest.mark.django_db
def test_bulk_update_is_partial_on_a_per_item_error(ctx, workspace, requirements):
    missing = uuid.uuid4()
    result = BulkEditService().bulk_update(
        ctx=ctx,
        workspace_id=workspace.id,
        item_type="Requirement",
        ids=[requirements[0].id, missing],
        fields={"category": "safety"},
    )
    assert result.updated == [str(requirements[0].id)]
    assert [f.id for f in result.failed] == [str(missing)]
    assert result.failed[0].error


@pytest.mark.django_db
def test_bulk_update_refuses_an_item_from_another_workspace(ctx, tenant, workspace, requirements):
    TenantContext.set_tenant(tenant.id)
    try:
        other = Workspace.objects.create(tenant=tenant, name="Other")
        art = Artifact.objects.create(tenant=tenant, workspace=other, artifact_type="Requirement")
        foreign = Requirement.objects.create(tenant=tenant, artifact=art, title="X", status="draft")
    finally:
        TenantContext.clear_tenant()

    result = BulkEditService().bulk_update(
        ctx=ctx,
        workspace_id=workspace.id,
        item_type="Requirement",
        ids=[foreign.id],
        fields={"category": "safety"},
    )
    assert result.updated == []
    assert "workspace" in result.failed[0].error.lower()
    foreign.refresh_from_db()
    assert foreign.category != "safety"


@pytest.mark.django_db
def test_bulk_update_rejects_too_many_ids(ctx, workspace):
    with pytest.raises(ValidationError):
        BulkEditService().bulk_update(
            ctx=ctx,
            workspace_id=workspace.id,
            item_type="Requirement",
            ids=[uuid.uuid4() for _ in range(bes.MAX_BULK_IDS + 1)],
            fields={"category": "safety"},
        )


@pytest.mark.django_db
def test_bulk_update_rejects_empty_fields(ctx, workspace, requirements):
    with pytest.raises(ValidationError):
        BulkEditService().bulk_update(
            ctx=ctx,
            workspace_id=workspace.id,
            item_type="Requirement",
            ids=[requirements[0].id],
            fields={},
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `BT application/tests/test_bulk_edit_service_update.py -v`
Expected: FAIL with `AttributeError: 'BulkEditService' object has no attribute 'bulk_update'`

- [ ] **Step 3: Write minimal implementation**

Add these imports to the top of `backend/application/bulk_edit_service.py`:

```python
import logging
from dataclasses import dataclass, field
from uuid import UUID

from application.attribute_definition_access import attribute_by_name, resolve_attributes
from application.table_query_service import TABLE_ITEM_TYPES
from application.workspace_lookup import resolve_owning_workspace_id
from auth_tenancy.context import AuthContext

logger = logging.getLogger(__name__)
```

Replace the empty `BulkEditService` stub with:

```python
@dataclass(frozen=True)
class BulkItemFailure:
    """One item that could not be processed, with its own reason."""

    id: str
    error: str


@dataclass
class BulkResult:
    """Spec §3: ``{updated: [...], failed: [{id, error}]}``."""

    updated: list[str] = field(default_factory=list)
    failed: list[BulkItemFailure] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "updated": list(self.updated),
            "failed": [{"id": f.id, "error": f.error} for f in self.failed],
        }


def _safe_message(exc: Exception) -> str:
    """Forward only messages from the domain's own, safe-to-surface errors.

    Mirrors ``rest_api/views.py:_service_error_response`` (fix #108, CWE-209):
    an unmapped exception's ``str()`` can carry SQL fragments and column names,
    so anything outside the known set degrades to a static message.
    """
    from application.base import NotFoundError, PermissionDeniedError
    from application.optimistic_lock import OptimisticLockError

    if isinstance(
        exc, (ValidationError, NotFoundError, PermissionDeniedError, OptimisticLockError)
    ):
        return str(exc) or type(exc).__name__
    logger.exception("Unhandled error during bulk operation", exc_info=exc)
    return "An internal error occurred."


class BulkEditService(ServiceBase):
    """Bulk update / transition across the ARTIFACT_UPDATE_ADAPTERS registry."""

    def bulk_update(
        self,
        *,
        ctx: AuthContext,
        workspace_id: UUID,
        item_type: str,
        ids: Sequence[UUID],
        fields: Mapping[str, Any],
        change_reason: str = "",
    ) -> BulkResult:
        """Apply *fields* to every id, item by item (spec §3.1).

        Raises ``ValidationError`` (whole request, no partial success) for a
        workflow-owned field, an unknown field, an unsupported item type, an
        empty payload or an oversized id list. Everything after that point is
        partial-success: a per-item failure is collected, never re-raised.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        if not fields:
            raise ValidationError("'fields' must contain at least one field")
        if len(ids) > MAX_BULK_IDS:
            raise ValidationError(
                f"{len(ids)} ids exceed the bulk maximum of {MAX_BULK_IDS}"
            )

        assert_fields_are_updatable(item_type, fields)
        attributes = resolve_attributes(ctx, workspace_id, item_type)
        assert_no_workflow_owned_fields(attributes, fields)

        entity_key = TABLE_ITEM_TYPES[item_type]
        adapter = ARTIFACT_UPDATE_ADAPTERS[item_type]
        result = BulkResult()
        for entity_id in ids:
            try:
                owning = resolve_owning_workspace_id(entity_key, entity_id)
                if owning is not None and str(owning) != str(workspace_id):
                    raise ValidationError(
                        f"Item {entity_id} belongs to a different workspace"
                    )
                adapter.call(entity_id, dict(fields), ctx, change_reason)
            except Exception as exc:  # noqa: BLE001 — per-item isolation is the point
                result.failed.append(
                    BulkItemFailure(id=str(entity_id), error=_safe_message(exc))
                )
            else:
                result.updated.append(str(entity_id))
        return result
```

Verify the `OptimisticLockError` import path before running:
`grep -rn "class OptimisticLockError" backend/application/` — adjust the import if it does not live in `application/optimistic_lock.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `BT application/tests/test_bulk_edit_service_update.py application/tests/test_bulk_edit_service.py -v`
Expected: PASS (14 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/application/bulk_edit_service.py backend/application/tests/test_bulk_edit_service_update.py
git commit -m "feat(table): add partial-success bulk update over update adapters"
```

---

## Task 7: BulkEditService.bulk_transition

**Files:**
- Modify: `backend/application/bulk_edit_service.py` (add `bulk_transition`)
- Test: `backend/application/tests/test_bulk_edit_service_transition.py`

**Interfaces:**
- Consumes: `application.workflow_facade.WorkflowFacade().transition(item_id=, target_state=, change_reason=, ctx=, credential=, item_type=, workspace_id=)`, `BulkResult` (Task 6)
- Produces: `BulkEditService.bulk_transition(...) -> BulkResult`

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_bulk_edit_service_transition.py`:

```python
"""bulk_transition: one real WorkflowFacade call per item, partial success."""
from __future__ import annotations

import uuid

import pytest

from application import bulk_edit_service as bes
from application.base import ServiceBase, ValidationError
from application.bulk_edit_service import BulkEditService
from auth_tenancy.context import AuthContext


class _Recorder:
    """Stands in for WorkflowFacade, recording each per-item call."""

    def __init__(self, fail_on=()):
        self.calls = []
        self._fail_on = {str(i) for i in fail_on}

    def transition(
        self, *, item_id, target_state, change_reason, ctx, credential, item_type, workspace_id
    ):
        self.calls.append(
            {
                "item_id": str(item_id),
                "target_state": target_state,
                "change_reason": change_reason,
                "credential": credential,
                "item_type": item_type,
                "workspace_id": str(workspace_id),
            }
        )
        if str(item_id) in self._fail_on:
            raise ValidationError("transition not allowed from current state")
        return object()


@pytest.fixture
def ctx() -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("editor",),
        auth_method="test",
    )


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    monkeypatch.setattr(ServiceBase, "_assert_write_permission", staticmethod(lambda ctx: None))
    monkeypatch.setattr(ServiceBase, "_set_tenant_context", staticmethod(lambda ctx: None))
    monkeypatch.setattr(bes, "resolve_owning_workspace_id", lambda key, entity_id: None)


def test_bulk_transition_calls_the_facade_once_per_item(ctx, monkeypatch):
    recorder = _Recorder()
    monkeypatch.setattr(bes, "WorkflowFacade", lambda: recorder)
    ids = [uuid.uuid4(), uuid.uuid4()]

    result = BulkEditService().bulk_transition(
        ctx=ctx,
        workspace_id=uuid.uuid4(),
        item_type="Requirement",
        ids=ids,
        to_state="in_review",
        change_reason="batch review",
    )

    assert result.updated == [str(i) for i in ids]
    assert [c["target_state"] for c in recorder.calls] == ["in_review", "in_review"]
    assert {c["item_type"] for c in recorder.calls} == {"Requirement"}
    assert {c["change_reason"] for c in recorder.calls} == {"batch review"}


def test_bulk_transition_is_partial_when_one_item_is_gated(ctx, monkeypatch):
    ids = [uuid.uuid4(), uuid.uuid4()]
    recorder = _Recorder(fail_on=[ids[1]])
    monkeypatch.setattr(bes, "WorkflowFacade", lambda: recorder)

    result = BulkEditService().bulk_transition(
        ctx=ctx,
        workspace_id=uuid.uuid4(),
        item_type="Requirement",
        ids=ids,
        to_state="approved",
    )

    assert result.updated == [str(ids[0])]
    assert [f.id for f in result.failed] == [str(ids[1])]
    assert "not allowed" in result.failed[0].error


def test_bulk_transition_forwards_the_signature_credential(ctx, monkeypatch):
    recorder = _Recorder()
    monkeypatch.setattr(bes, "WorkflowFacade", lambda: recorder)
    BulkEditService().bulk_transition(
        ctx=ctx,
        workspace_id=uuid.uuid4(),
        item_type="Requirement",
        ids=[uuid.uuid4()],
        to_state="released",
        credential="totp-123456",
    )
    assert recorder.calls[0]["credential"] == "totp-123456"


def test_bulk_transition_requires_a_target_state(ctx):
    with pytest.raises(ValidationError):
        BulkEditService().bulk_transition(
            ctx=ctx,
            workspace_id=uuid.uuid4(),
            item_type="Requirement",
            ids=[uuid.uuid4()],
            to_state="",
        )


def test_bulk_transition_rejects_too_many_ids(ctx):
    with pytest.raises(ValidationError):
        BulkEditService().bulk_transition(
            ctx=ctx,
            workspace_id=uuid.uuid4(),
            item_type="Requirement",
            ids=[uuid.uuid4() for _ in range(bes.MAX_BULK_IDS + 1)],
            to_state="approved",
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `BT application/tests/test_bulk_edit_service_transition.py -v`
Expected: FAIL with `AttributeError: 'BulkEditService' object has no attribute 'bulk_transition'`

- [ ] **Step 3: Write minimal implementation**

Add `from application.workflow_facade import WorkflowFacade` to the imports of `backend/application/bulk_edit_service.py`, then add the method to `BulkEditService`:

```python
    def bulk_transition(
        self,
        *,
        ctx: AuthContext,
        workspace_id: UUID,
        item_type: str,
        ids: Sequence[UUID],
        to_state: str,
        change_reason: str = "",
        credential: str = "",
    ) -> BulkResult:
        """Transition every id to *to_state* (spec §3.2).

        One ordinary ``WorkflowFacade.transition`` per item, so the preset role
        gate, the change_reason policy and the per-transition signature gate
        fire per item exactly as for a single-item transition. There is
        deliberately no batched fast path — a bulk shortcut is precisely what
        the §2 guardrail forbids.
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        if not to_state:
            raise ValidationError("'to_state' is required")
        if len(ids) > MAX_BULK_IDS:
            raise ValidationError(
                f"{len(ids)} ids exceed the bulk maximum of {MAX_BULK_IDS}"
            )
        if item_type not in TABLE_ITEM_TYPES:
            raise ValidationError(
                f"Item type '{item_type}' does not support bulk transition. "
                f"Supported: {sorted(TABLE_ITEM_TYPES)}"
            )

        entity_key = TABLE_ITEM_TYPES[item_type]
        facade = WorkflowFacade()
        result = BulkResult()
        for entity_id in ids:
            try:
                owning = resolve_owning_workspace_id(entity_key, entity_id)
                if owning is not None and str(owning) != str(workspace_id):
                    raise ValidationError(
                        f"Item {entity_id} belongs to a different workspace"
                    )
                facade.transition(
                    item_id=entity_id,
                    target_state=to_state,
                    change_reason=change_reason,
                    ctx=ctx,
                    credential=credential,
                    item_type=item_type,
                    workspace_id=workspace_id,
                )
            except Exception as exc:  # noqa: BLE001 — per-item isolation
                result.failed.append(
                    BulkItemFailure(id=str(entity_id), error=_safe_message(exc))
                )
            else:
                result.updated.append(str(entity_id))
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `BT application/tests/test_bulk_edit_service_transition.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/application/bulk_edit_service.py backend/application/tests/test_bulk_edit_service_transition.py
git commit -m "feat(table): add bulk transition through the workflow facade"
```

---

## Task 8: UserTableViewState and SavedView models

**Files:**
- Modify: `backend/persistence/models.py` (append two models near the other `pl_*` config models)
- Create: `backend/persistence/migrations/0070_table_views.py`
- Test: `backend/persistence/tests/test_table_view_models.py`

**Interfaces:**
- Consumes: `persistence.models.TenantScopedModel`
- Produces: `UserTableViewState` (`pl_user_table_view_state`), `SavedView` (`pl_saved_view`), `SAVED_VIEW_VISIBILITY_CHOICES`

- [ ] **Step 1: Write the failing test**

Create `backend/persistence/tests/test_table_view_models.py`:

```python
"""Table-view persistence: uniqueness, defaults and RLS coverage."""
from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, connection

from persistence.models import SavedView, Tenant, User, UserTableViewState, Workspace
from persistence.tenancy import TenantContext


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="T", slug=f"t-{uuid.uuid4().hex[:8]}", is_active=True)


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="WS")
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def user(tenant: Tenant) -> User:
    return User.objects.create(username=f"u{uuid.uuid4().hex[:6]}", email="u@t.test", tenant=tenant)


@pytest.mark.django_db
def test_view_state_is_unique_per_user_workspace_and_type(tenant, workspace, user):
    TenantContext.set_tenant(tenant.id)
    try:
        UserTableViewState.objects.create(
            tenant=tenant, user=user, workspace_id=workspace.id, item_type="Requirement"
        )
        with pytest.raises(IntegrityError):
            UserTableViewState.objects.create(
                tenant=tenant, user=user, workspace_id=workspace.id, item_type="Requirement"
            )
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_view_state_defaults_are_empty_containers(tenant, workspace, user):
    TenantContext.set_tenant(tenant.id)
    try:
        state = UserTableViewState.objects.create(
            tenant=tenant, user=user, workspace_id=workspace.id, item_type="Risk"
        )
        assert state.columns == []
        assert state.filters == {}
        assert state.sort == []
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_saved_view_defaults_to_private(tenant, workspace, user):
    TenantContext.set_tenant(tenant.id)
    try:
        view = SavedView.objects.create(
            tenant=tenant,
            workspace_id=workspace.id,
            item_type="Requirement",
            owner=user,
            name="Open critical risks",
        )
        assert view.visibility == "private"
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_both_tables_have_row_level_security_enabled():
    with connection.cursor() as cur:
        cur.execute(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname IN ('pl_user_table_view_state', 'pl_saved_view')"
        )
        rows = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
    assert rows["pl_user_table_view_state"] == (True, True)
    assert rows["pl_saved_view"] == (True, True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `BT persistence/tests/test_table_view_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'SavedView' from 'persistence.models'`

- [ ] **Step 3: Write minimal implementation**

Append to `backend/persistence/models.py` (after the other `pl_*` configuration models, e.g. next to `PromptVariable`):

```python
#: Spec §4.2 — who may see a SavedView.
SAVED_VIEW_VISIBILITY_CHOICES = [
    ("private", "Private"),
    ("workspace", "Workspace"),
]


class UserTableViewState(TenantScopedModel):
    """Last table state per user+workspace+item_type (spec §4.2).

    Unnamed and automatic: overwritten on every column/filter/sort change so
    "where I last was" is always there when the table view reopens. Explicitly
    NOT a SavedView — that one is named, explicit and shareable.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="table_view_states"
    )
    workspace_id = models.UUIDField(db_index=True)
    item_type = models.CharField(max_length=128)
    #: ``[{"field": "title", "order": 0}, ...]``
    columns = models.JSONField(default=list, blank=True)
    #: Filter DSL payload, see ``application/table_filter_dsl.py``.
    filters = models.JSONField(default=dict, blank=True)
    #: ``[{"field": "title", "dir": "asc"}, ...]``
    sort = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "pl_user_table_view_state"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "user", "workspace_id", "item_type"],
                name="uq_table_view_state_scope",
            )
        ]


class SavedView(TenantScopedModel):
    """Named, explicitly saved table view (spec §4.2).

    ``visibility="workspace"`` makes it readable by every workspace member;
    editing and deleting stay with the owner (or a tenant admin) — enforced in
    ``application/saved_view_service.py``, not here.
    """

    workspace_id = models.UUIDField(db_index=True)
    item_type = models.CharField(max_length=128)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_views"
    )
    name = models.CharField(max_length=255)
    columns = models.JSONField(default=list, blank=True)
    filters = models.JSONField(default=dict, blank=True)
    sort = models.JSONField(default=list, blank=True)
    visibility = models.CharField(
        max_length=16, choices=SAVED_VIEW_VISIBILITY_CHOICES, default="private"
    )

    class Meta:
        db_table = "pl_saved_view"
        indexes = [
            models.Index(
                fields=["tenant", "workspace_id", "item_type"], name="ix_saved_view_scope"
            )
        ]
```

`created_at`/`modified_at` come from `AuditableModel` via `TenantScopedModel`; the spec's `created_at`/`updated_at` names map onto those — do not add duplicate columns.

Create `backend/persistence/migrations/0070_table_views.py` (RLS block copied from `0062_add_prompt_variable.py`, one policy per table):

```python
"""UserTableViewState + SavedView (Tabellenansicht spec §4.2).

Operation order mirrors 0062_add_prompt_variable.py:
  1. CreateModel for both tables.
  2. Enable + FORCE Row-Level Security on each.

Additive only — no existing row is touched.
"""
import django.db.models.deletion
import django.db.models.manager
import uuid
from django.conf import settings
from django.db import migrations, models


def _rls(table: str) -> tuple[str, str]:
    policy = f"{table}_tenant_isolation"
    enable = (
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;\n"
        f"CREATE POLICY {policy} ON {table}\n"
        f"    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
        f"    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
    )
    disable = (
        f"DROP POLICY IF EXISTS {policy} ON {table};\n"
        f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;\n"
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
    )
    return enable, disable


_STATE_ENABLE, _STATE_DISABLE = _rls("pl_user_table_view_state")
_VIEW_ENABLE, _VIEW_DISABLE = _rls("pl_saved_view")


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0069_align_embedding_dimensions"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserTableViewState",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("workspace_id", models.UUIDField(db_index=True)),
                ("item_type", models.CharField(max_length=128)),
                ("columns", models.JSONField(blank=True, default=list)),
                ("filters", models.JSONField(blank=True, default=dict)),
                ("sort", models.JSONField(blank=True, default=list)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("modified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(class)s_set", to="persistence.tenant")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="table_view_states", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "pl_user_table_view_state"},
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("unscoped", django.db.models.manager.Manager()),
            ],
        ),
        migrations.CreateModel(
            name="SavedView",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("workspace_id", models.UUIDField(db_index=True)),
                ("item_type", models.CharField(max_length=128)),
                ("name", models.CharField(max_length=255)),
                ("columns", models.JSONField(blank=True, default=list)),
                ("filters", models.JSONField(blank=True, default=dict)),
                ("sort", models.JSONField(blank=True, default=list)),
                ("visibility", models.CharField(choices=[("private", "Private"), ("workspace", "Workspace")], default="private", max_length=16)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("modified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="saved_views", to=settings.AUTH_USER_MODEL)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(class)s_set", to="persistence.tenant")),
            ],
            options={
                "db_table": "pl_saved_view",
                "indexes": [models.Index(fields=["tenant", "workspace_id", "item_type"], name="ix_saved_view_scope")],
            },
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("unscoped", django.db.models.manager.Manager()),
            ],
        ),
        migrations.AddConstraint(
            model_name="usertableviewstate",
            constraint=models.UniqueConstraint(
                fields=("tenant", "user", "workspace_id", "item_type"),
                name="uq_table_view_state_scope",
            ),
        ),
        migrations.RunSQL(sql=_STATE_ENABLE, reverse_sql=_STATE_DISABLE),
        migrations.RunSQL(sql=_VIEW_ENABLE, reverse_sql=_VIEW_DISABLE),
    ]
```

Before running the tests, confirm `0069_align_embedding_dimensions` is still the leaf:
`ls backend/persistence/migrations/ | tail -3`. If a newer migration exists, depend on that one instead — a renumbered/duplicated leaf blocks `migrate` entirely.

Then verify Django agrees the models and migration match:
`docker compose -f deploy/docker-compose.yml --project-directory . exec backend python manage.py makemigrations --check --dry-run`

- [ ] **Step 4: Run test to verify it passes**

Run: `BT persistence/tests/test_table_view_models.py -v --create-db`
Expected: PASS (4 passed). `--create-db` is required because the RLS `RunSQL` needs the DB owner role on a fresh test database.

- [ ] **Step 5: Commit**

```bash
git add backend/persistence/models.py backend/persistence/migrations/0070_table_views.py backend/persistence/tests/test_table_view_models.py
git commit -m "feat(table): add UserTableViewState and SavedView models with RLS"
```

---

## Task 9: SavedView and table-view-state service

**Files:**
- Create: `backend/application/saved_view_service.py`
- Test: `backend/application/tests/test_saved_view_service.py`

**Interfaces:**
- Consumes: `persistence.models.SavedView`, `persistence.models.UserTableViewState` (Task 8), `TableQueryService` (Task 3), `compile_filters`/`compile_sort` validation (Task 2)
- Produces: `SavedViewDTO`, `SavedViewService.{list,get,create,update,delete}`, `TableViewStateService.{get,save}`

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_saved_view_service.py`:

```python
"""SavedView visibility rules and the auto-persisted table view state."""
from __future__ import annotations

import uuid

import pytest

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.saved_view_service import SavedViewService, TableViewStateService
from auth_tenancy.context import AuthContext
from persistence.models import Tenant, User, Workspace
from persistence.tenancy import TenantContext


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="T", slug=f"t-{uuid.uuid4().hex[:8]}", is_active=True)


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        return Workspace.objects.create(tenant=tenant, name="WS")
    finally:
        TenantContext.clear_tenant()


def _user(tenant: Tenant, name: str) -> User:
    return User.objects.create(username=name, email=f"{name}@t.test", tenant=tenant)


def _ctx(tenant: Tenant, workspace: Workspace, user: User, role: str = "editor") -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=(role,),
        auth_method="test",
        workspace_id=workspace.id,
    )


@pytest.mark.django_db
def test_private_view_is_invisible_to_another_user(tenant, workspace):
    owner, other = _user(tenant, "owner"), _user(tenant, "other")
    svc = SavedViewService()
    svc.create(
        ctx=_ctx(tenant, workspace, owner),
        workspace_id=workspace.id,
        item_type="Requirement",
        name="Mine",
        columns=[{"field": "title", "order": 0}],
        filters={},
        sort=[],
        visibility="private",
    )
    assert svc.list(ctx=_ctx(tenant, workspace, other), workspace_id=workspace.id) == []


@pytest.mark.django_db
def test_workspace_view_is_visible_to_another_user_but_not_editable(tenant, workspace):
    owner, other = _user(tenant, "owner2"), _user(tenant, "other2")
    svc = SavedViewService()
    view = svc.create(
        ctx=_ctx(tenant, workspace, owner),
        workspace_id=workspace.id,
        item_type="Requirement",
        name="Team view",
        columns=[{"field": "title", "order": 0}],
        filters={},
        sort=[],
        visibility="workspace",
    )
    other_ctx = _ctx(tenant, workspace, other)
    listed = svc.list(ctx=other_ctx, workspace_id=workspace.id)
    assert [v.name for v in listed] == ["Team view"]
    assert listed[0].is_owner is False
    with pytest.raises(PermissionDeniedError):
        svc.update(ctx=other_ctx, view_id=view.id, name="Hijacked")
    with pytest.raises(PermissionDeniedError):
        svc.delete(ctx=other_ctx, view_id=view.id)


@pytest.mark.django_db
def test_admin_may_edit_a_foreign_workspace_view(tenant, workspace):
    owner, admin = _user(tenant, "owner3"), _user(tenant, "admin3")
    svc = SavedViewService()
    view = svc.create(
        ctx=_ctx(tenant, workspace, owner),
        workspace_id=workspace.id,
        item_type="Requirement",
        name="Team view",
        columns=[],
        filters={},
        sort=[],
        visibility="workspace",
    )
    updated = svc.update(
        ctx=_ctx(tenant, workspace, admin, role="admin"), view_id=view.id, name="Renamed"
    )
    assert updated.name == "Renamed"


@pytest.mark.django_db
def test_list_filters_by_item_type(tenant, workspace):
    owner = _user(tenant, "owner4")
    ctx = _ctx(tenant, workspace, owner)
    svc = SavedViewService()
    svc.create(ctx=ctx, workspace_id=workspace.id, item_type="Requirement", name="R", columns=[], filters={}, sort=[])
    svc.create(ctx=ctx, workspace_id=workspace.id, item_type="Risk", name="K", columns=[], filters={}, sort=[])
    assert [v.name for v in svc.list(ctx=ctx, workspace_id=workspace.id, item_type="Risk")] == ["K"]


@pytest.mark.django_db
def test_create_rejects_an_unknown_visibility(tenant, workspace):
    ctx = _ctx(tenant, workspace, _user(tenant, "owner5"))
    with pytest.raises(ValidationError):
        SavedViewService().create(
            ctx=ctx, workspace_id=workspace.id, item_type="Requirement", name="X",
            columns=[], filters={}, sort=[], visibility="public",
        )


@pytest.mark.django_db
def test_create_rejects_an_empty_name(tenant, workspace):
    ctx = _ctx(tenant, workspace, _user(tenant, "owner6"))
    with pytest.raises(ValidationError):
        SavedViewService().create(
            ctx=ctx, workspace_id=workspace.id, item_type="Requirement", name="   ",
            columns=[], filters={}, sort=[],
        )


@pytest.mark.django_db
def test_get_raises_not_found_for_a_foreign_private_view(tenant, workspace):
    owner, other = _user(tenant, "owner7"), _user(tenant, "other7")
    view = SavedViewService().create(
        ctx=_ctx(tenant, workspace, owner), workspace_id=workspace.id,
        item_type="Requirement", name="Mine", columns=[], filters={}, sort=[],
    )
    with pytest.raises(NotFoundError):
        SavedViewService().get(ctx=_ctx(tenant, workspace, other), view_id=view.id)


@pytest.mark.django_db
def test_view_state_is_upserted_not_duplicated(tenant, workspace):
    ctx = _ctx(tenant, workspace, _user(tenant, "stateuser"))
    svc = TableViewStateService()
    assert svc.get(ctx=ctx, workspace_id=workspace.id, item_type="Requirement") == {
        "columns": [],
        "filters": {},
        "sort": [],
    }
    svc.save(
        ctx=ctx, workspace_id=workspace.id, item_type="Requirement",
        columns=[{"field": "title", "order": 0}], filters={}, sort=[],
    )
    svc.save(
        ctx=ctx, workspace_id=workspace.id, item_type="Requirement",
        columns=[{"field": "status", "order": 0}], filters={}, sort=[],
    )
    stored = svc.get(ctx=ctx, workspace_id=workspace.id, item_type="Requirement")
    assert stored["columns"] == [{"field": "status", "order": 0}]

    from persistence.models import UserTableViewState

    TenantContext.set_tenant(tenant.id)
    try:
        assert UserTableViewState.objects.filter(workspace_id=workspace.id).count() == 1
    finally:
        TenantContext.clear_tenant()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `BT application/tests/test_saved_view_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.saved_view_service'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/application/saved_view_service.py`:

```python
"""SavedView CRUD + auto-persisted UserTableViewState (spec §4.2).

Visibility is enforced here, not in the model: ``visibility="workspace"`` is a
read grant only — edit and delete stay with the owner or a tenant/workspace
admin. A private view owned by someone else is reported as NOT_FOUND rather
than PERMISSION_DENIED so its mere existence is not disclosed.

A stale saved view (a filter naming a value that has since been deleted) is
fail-soft by design (spec §6): it yields an empty result list, never an error.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence
from uuid import UUID

from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ServiceBase,
    ValidationError,
)
from auth_tenancy.context import AuthContext
from persistence.models import SAVED_VIEW_VISIBILITY_CHOICES, SavedView, UserTableViewState

_VALID_VISIBILITY = {value for value, _label in SAVED_VIEW_VISIBILITY_CHOICES}
_ADMIN_ROLES = frozenset({"admin", "tenant_admin"})


@dataclass(frozen=True)
class SavedViewDTO:
    id: UUID
    workspace_id: UUID
    item_type: str
    name: str
    owner_id: UUID
    owner_username: str
    columns: list
    filters: dict
    sort: list
    visibility: str
    is_owner: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "workspace_id": str(self.workspace_id),
            "item_type": self.item_type,
            "name": self.name,
            "owner_id": str(self.owner_id),
            "owner_username": self.owner_username,
            "columns": self.columns,
            "filters": self.filters,
            "sort": self.sort,
            "visibility": self.visibility,
            "is_owner": self.is_owner,
        }


def _to_dto(row: SavedView, ctx: AuthContext) -> SavedViewDTO:
    return SavedViewDTO(
        id=row.id,
        workspace_id=row.workspace_id,
        item_type=row.item_type,
        name=row.name,
        owner_id=row.owner_id,
        owner_username=getattr(row.owner, "username", ""),
        columns=row.columns or [],
        filters=row.filters or {},
        sort=row.sort or [],
        visibility=row.visibility,
        is_owner=str(row.owner_id) == str(ctx.user_id),
    )


class SavedViewService(ServiceBase):
    """Named, optionally shared table views."""

    def list(
        self, *, ctx: AuthContext, workspace_id: UUID, item_type: Optional[str] = None
    ) -> list[SavedViewDTO]:
        """Own views plus every workspace-shared view of this workspace."""
        self._set_tenant_context(ctx)
        qs = SavedView.objects.select_related("owner").filter(workspace_id=workspace_id)
        if item_type:
            qs = qs.filter(item_type=item_type)
        rows = [
            row
            for row in qs.order_by("name")
            if row.visibility == "workspace" or str(row.owner_id) == str(ctx.user_id)
        ]
        return [_to_dto(row, ctx) for row in rows]

    def get(self, *, ctx: AuthContext, view_id: UUID) -> SavedViewDTO:
        self._set_tenant_context(ctx)
        row = SavedView.objects.select_related("owner").filter(id=view_id).first()
        if row is None or (
            row.visibility != "workspace" and str(row.owner_id) != str(ctx.user_id)
        ):
            raise NotFoundError(f"SavedView {view_id} not found")
        return _to_dto(row, ctx)

    def create(
        self,
        *,
        ctx: AuthContext,
        workspace_id: UUID,
        item_type: str,
        name: str,
        columns: Sequence[Mapping[str, Any]],
        filters: Mapping[str, Any],
        sort: Sequence[Mapping[str, Any]],
        visibility: str = "private",
    ) -> SavedViewDTO:
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        clean_name = (name or "").strip()
        if not clean_name:
            raise ValidationError("'name' is required")
        if visibility not in _VALID_VISIBILITY:
            raise ValidationError(
                f"'visibility' must be one of {sorted(_VALID_VISIBILITY)}"
            )
        row = SavedView.objects.create(
            tenant_id=ctx.tenant_id,
            workspace_id=workspace_id,
            item_type=item_type,
            owner_id=ctx.user_id,
            name=clean_name,
            columns=list(columns),
            filters=dict(filters),
            sort=list(sort),
            visibility=visibility,
        )
        return _to_dto(row, ctx)

    def update(self, *, ctx: AuthContext, view_id: UUID, **changes: Any) -> SavedViewDTO:
        """Update name/columns/filters/sort/visibility. Owner or admin only."""
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        row = self._writable_row(ctx, view_id)
        if "name" in changes:
            clean_name = (changes["name"] or "").strip()
            if not clean_name:
                raise ValidationError("'name' must not be empty")
            row.name = clean_name
        if "visibility" in changes:
            if changes["visibility"] not in _VALID_VISIBILITY:
                raise ValidationError(
                    f"'visibility' must be one of {sorted(_VALID_VISIBILITY)}"
                )
            row.visibility = changes["visibility"]
        for key in ("columns", "sort"):
            if key in changes:
                setattr(row, key, list(changes[key] or []))
        if "filters" in changes:
            row.filters = dict(changes["filters"] or {})
        row.save()
        return _to_dto(row, ctx)

    def delete(self, *, ctx: AuthContext, view_id: UUID) -> None:
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)
        self._writable_row(ctx, view_id).delete()

    def _writable_row(self, ctx: AuthContext, view_id: UUID) -> SavedView:
        row = SavedView.objects.select_related("owner").filter(id=view_id).first()
        if row is None or (
            row.visibility != "workspace" and str(row.owner_id) != str(ctx.user_id)
        ):
            raise NotFoundError(f"SavedView {view_id} not found")
        is_admin = bool(set(ctx.active_roles) & _ADMIN_ROLES)
        if str(row.owner_id) != str(ctx.user_id) and not is_admin:
            raise PermissionDeniedError(
                "Only the owner or an admin may modify this saved view"
            )
        return row


class TableViewStateService(ServiceBase):
    """The unnamed, always-current table state per user+workspace+item_type."""

    def get(self, *, ctx: AuthContext, workspace_id: UUID, item_type: str) -> dict[str, Any]:
        """Return the stored state, or empty defaults when there is none yet."""
        self._set_tenant_context(ctx)
        row = UserTableViewState.objects.filter(
            user_id=ctx.user_id, workspace_id=workspace_id, item_type=item_type
        ).first()
        if row is None:
            return {"columns": [], "filters": {}, "sort": []}
        return {"columns": row.columns or [], "filters": row.filters or {}, "sort": row.sort or []}

    def save(
        self,
        *,
        ctx: AuthContext,
        workspace_id: UUID,
        item_type: str,
        columns: Sequence[Mapping[str, Any]],
        filters: Mapping[str, Any],
        sort: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Upsert the state row — one per user+workspace+item_type, ever."""
        self._set_tenant_context(ctx)
        UserTableViewState.objects.update_or_create(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            workspace_id=workspace_id,
            item_type=item_type,
            defaults={
                "columns": list(columns),
                "filters": dict(filters),
                "sort": list(sort),
            },
        )
        return self.get(ctx=ctx, workspace_id=workspace_id, item_type=item_type)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `BT application/tests/test_saved_view_service.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/application/saved_view_service.py backend/application/tests/test_saved_view_service.py
git commit -m "feat(table): add saved view and table view state services"
```
