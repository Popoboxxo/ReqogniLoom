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
      test_attribute_definition_access.py NEW
      test_table_filter_dsl.py            NEW
      test_table_query_service.py         NEW
      test_artifact_update_adapters.py    NEW
      test_bulk_edit_service.py           NEW  <- the workflow guardrail proof
      test_bulk_edit_service_update.py    NEW  <- guardrail proven against real rows
      test_bulk_edit_service_transition.py NEW
      test_saved_view_service.py          NEW
  persistence/
    models.py                             MOD  + UserTableViewState, + SavedView
    migrations/0070_table_views.py        NEW  CreateModel x2 + RLS enable/force
    tests/test_table_view_models.py       NEW
  rest_api/
    table_views.py                        NEW  7 endpoints, zero ORM
    urls.py                               MOD  7 paths before include(router.urls)
    tests/test_table_views.py             NEW  <- bulk endpoints, incl. the 400 proof
    tests/test_table_query_view.py        NEW
    tests/test_saved_view_views.py        NEW
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
    ArtifactTable.tsx / .module.css       NEW  grid, sorting, read-only status cell
    fieldComponents.ts                    NEW  seam onto spec 2's field library
    ColumnFilterPopover.tsx / .module.css NEW  type-aware filter inputs
    ActiveFilterChips.tsx                 NEW
    ColumnPicker.tsx                      NEW  gear menu
    SavedViewBar.tsx                      NEW  dropdown + save dialog
    BulkActionBar.tsx                     NEW  selection actions + partial-success report
    InlineCellEditor.tsx                  NEW  single-item update path
    useTableViewState.ts                  NEW  auto-persisted last state
    ArtifactTableView.tsx                 NEW  composed, self-fetching section
    index.ts                              NEW  named re-exports
  components/RequirementEditors/
    RequirementEditors.tsx                MOD  list/table toggle (pilot page)
  i18n/locales/{de,en}.json               MOD  + "table" namespace
  test/
    tableViewsApi.test.ts                 NEW
    tableColumnModel.test.ts              NEW
    ArtifactTable.test.tsx                NEW
    ArtifactTableFilters.test.tsx         NEW
    ArtifactTableColumnPicker.test.tsx    NEW
    ArtifactTableSavedViews.test.tsx      NEW
    ArtifactTableBulk.test.tsx            NEW
    ArtifactTableInlineEdit.test.tsx      NEW
    ArtifactTableView.test.tsx            NEW
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

---

## Task 10: REST — bulk update and bulk transition

**Files:**
- Create: `backend/rest_api/table_views.py`
- Modify: `backend/rest_api/urls.py`
- Test: `backend/rest_api/tests/test_table_views.py`

**Interfaces:**
- Consumes: `BulkEditService.bulk_update/bulk_transition` (Tasks 6–7), `rest_api.views._service_error_response`, `rest_api.query_params.parse_workspace_id`, `rest_api.auth_enforcer.get_auth_context`
- Produces: `BulkUpdateView`, `BulkTransitionView`, routes `PATCH /api/v1/artifacts/bulk-update/`, `POST /api/v1/artifacts/bulk-transition/`

- [ ] **Step 1: Write the failing test**

Create `backend/rest_api/tests/test_table_views.py`:

```python
"""REST surface of the table view. The guardrail must answer 400 here too."""
from __future__ import annotations

import uuid

import pytest

from application import bulk_edit_service as bes
from persistence.models import Artifact, Requirement
from persistence.tenancy import TenantContext

ATTRS = [
    {"name": "title", "kind": "core", "type": "text", "editable": True, "visible": True, "order": 1},
    {"name": "category", "kind": "core", "type": "enum", "editable": True, "visible": True, "order": 2},
    {"name": "status", "kind": "core", "type": "enum", "editable": "workflow", "visible": True, "order": 3},
]


@pytest.fixture(autouse=True)
def _stub_attributes(monkeypatch):
    from application import table_query_service as tqs

    monkeypatch.setattr(bes, "resolve_attributes", lambda ctx, workspace_id, item_type: ATTRS)
    monkeypatch.setattr(tqs, "resolve_attributes", lambda ctx, workspace_id, item_type: ATTRS)


@pytest.fixture
def requirement(tenant, workspace) -> Requirement:
    TenantContext.set_tenant(tenant.id)
    try:
        art = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        return Requirement.objects.create(
            tenant=tenant, artifact=art, title="Brake force", status="draft"
        )
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_bulk_update_applies_a_plain_field(authed_client, workspace, requirement):
    response = authed_client.patch(
        "/api/v1/artifacts/bulk-update/",
        {
            "workspace_id": str(workspace.id),
            "item_type": "Requirement",
            "ids": [str(requirement.id)],
            "fields": {"category": "functional"},
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["updated"] == [str(requirement.id)]
    assert body["failed"] == []
    requirement.refresh_from_db()
    assert requirement.category == "functional"


@pytest.mark.django_db
def test_bulk_update_on_a_workflow_field_is_rejected_with_400(
    authed_client, workspace, requirement
):
    """THE guardrail (spec §2), proven at the HTTP boundary."""
    response = authed_client.patch(
        "/api/v1/artifacts/bulk-update/",
        {
            "workspace_id": str(workspace.id),
            "item_type": "Requirement",
            "ids": [str(requirement.id)],
            "fields": {"title": "Renamed", "status": "approved"},
        },
        format="json",
    )
    assert response.status_code == 400, response.content
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "status" in error["message"]
    # No partial write: neither field landed.
    requirement.refresh_from_db()
    assert requirement.title == "Brake force"
    assert requirement.status == "draft"


@pytest.mark.django_db
def test_bulk_update_reports_partial_failure(authed_client, workspace, requirement):
    missing = str(uuid.uuid4())
    response = authed_client.patch(
        "/api/v1/artifacts/bulk-update/",
        {
            "workspace_id": str(workspace.id),
            "item_type": "Requirement",
            "ids": [str(requirement.id), missing],
            "fields": {"category": "safety"},
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["updated"] == [str(requirement.id)]
    assert [f["id"] for f in body["failed"]] == [missing]


@pytest.mark.django_db
def test_bulk_update_rejects_an_unknown_field_with_400(authed_client, workspace, requirement):
    response = authed_client.patch(
        "/api/v1/artifacts/bulk-update/",
        {
            "workspace_id": str(workspace.id),
            "item_type": "Requirement",
            "ids": [str(requirement.id)],
            "fields": {"not_a_field": 1},
        },
        format="json",
    )
    assert response.status_code == 400
    assert "not_a_field" in response.json()["error"]["message"]


@pytest.mark.django_db
def test_bulk_update_requires_a_valid_workspace_id(authed_client, requirement):
    response = authed_client.patch(
        "/api/v1/artifacts/bulk-update/",
        {
            "workspace_id": "not-a-uuid",
            "item_type": "Requirement",
            "ids": [str(requirement.id)],
            "fields": {"category": "safety"},
        },
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_bulk_transition_calls_the_workflow_engine(
    authed_client, workspace, requirement, monkeypatch
):
    calls = []

    class _Facade:
        def transition(self, **kwargs):
            calls.append(kwargs)
            return object()

    monkeypatch.setattr(bes, "WorkflowFacade", lambda: _Facade())
    response = authed_client.post(
        "/api/v1/artifacts/bulk-transition/",
        {
            "workspace_id": str(workspace.id),
            "item_type": "Requirement",
            "ids": [str(requirement.id)],
            "to_state": "in_review",
            "change_reason": "batch review",
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["updated"] == [str(requirement.id)]
    assert calls[0]["target_state"] == "in_review"
    assert calls[0]["change_reason"] == "batch review"


@pytest.mark.django_db
def test_bulk_endpoints_require_authentication(client, workspace, requirement):
    response = client.patch(
        "/api/v1/artifacts/bulk-update/",
        {
            "workspace_id": str(workspace.id),
            "item_type": "Requirement",
            "ids": [str(requirement.id)],
            "fields": {"category": "safety"},
        },
        content_type="application/json",
    )
    assert response.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `BT rest_api/tests/test_table_views.py -v`
Expected: FAIL — every request answers 404 because `/api/v1/artifacts/bulk-update/` is not routed yet.

- [ ] **Step 3: Write minimal implementation**

Create `backend/rest_api/table_views.py`:

```python
"""REST surface of the table view (Tabellenansicht spec §3 and §4).

No ORM and no ``persistence.models`` import: ``rest_api/tests/test_architecture.py``
caps every ``*_views.py`` at 0 direct-ORM lines. Everything goes through the
Layer-2 services.

``_service_error_response`` is imported from ``views.py`` rather than
re-implemented: it carries the CWE-209 masking policy (fix #108) and the
exact-type exception map, and a second copy would drift.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.base import ValidationError
from application.bulk_edit_service import BulkEditService
from rest_api.auth_enforcer import get_auth_context
from rest_api.query_params import parse_workspace_id
from rest_api.serializers import build_error_response, detect_lang
from rest_api.views import _service_error_response


def _validation_error(message: str, lang: str) -> Response:
    return Response(
        build_error_response("VALIDATION_ERROR", lang, message=message),
        status=status.HTTP_400_BAD_REQUEST,
    )


def _parse_ids(raw: Any, lang: str) -> tuple[list[UUID] | None, Response | None]:
    """Parse the ``ids`` array; every entry must be a well-formed UUID."""
    if not isinstance(raw, list) or not raw:
        return None, _validation_error("'ids' must be a non-empty array", lang)
    parsed: list[UUID] = []
    for value in raw:
        try:
            parsed.append(UUID(str(value)))
        except (ValueError, AttributeError, TypeError):
            return None, _validation_error(f"'{value}' is not a valid id", lang)
    return parsed, None


class BulkUpdateView(APIView):
    """PATCH /api/v1/artifacts/bulk-update/ — spec §3.1.

    Body: ``{workspace_id, item_type, ids[], fields{}, change_reason?}``.
    200 ``{updated: [...], failed: [{id, error}]}`` on partial success;
    400 for a workflow-owned field, an unknown field, or a malformed payload —
    in that case nothing at all is written.
    """

    def patch(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        workspace_id, error = parse_workspace_id(request.data.get("workspace_id"), lang)
        if error is not None:
            return error
        ids, error = _parse_ids(request.data.get("ids"), lang)
        if error is not None:
            return error
        fields = request.data.get("fields")
        if not isinstance(fields, dict):
            return _validation_error("'fields' must be a JSON object", lang)

        try:
            result = BulkEditService().bulk_update(
                ctx=get_auth_context(request),
                workspace_id=workspace_id,
                item_type=str(request.data.get("item_type") or ""),
                ids=ids,
                fields=fields,
                change_reason=str(request.data.get("change_reason") or ""),
            )
        except Exception as exc:  # mapped by _service_error_response
            return _service_error_response(exc, lang)
        return Response(result.as_dict())


class BulkTransitionView(APIView):
    """POST /api/v1/artifacts/bulk-transition/ — spec §3.2.

    Body: ``{workspace_id, item_type, ids[], to_state, change_reason?, credential?}``.
    One full workflow transition per item; role, change_reason and signature
    gates are evaluated per item, and a blocked item lands in ``failed``.
    """

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        workspace_id, error = parse_workspace_id(request.data.get("workspace_id"), lang)
        if error is not None:
            return error
        ids, error = _parse_ids(request.data.get("ids"), lang)
        if error is not None:
            return error

        try:
            result = BulkEditService().bulk_transition(
                ctx=get_auth_context(request),
                workspace_id=workspace_id,
                item_type=str(request.data.get("item_type") or ""),
                ids=ids,
                to_state=str(request.data.get("to_state") or ""),
                change_reason=str(request.data.get("change_reason") or ""),
                credential=str(request.data.get("credential") or ""),
            )
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(result.as_dict())


__all__ = ["BulkTransitionView", "BulkUpdateView"]
```

In `backend/rest_api/urls.py`, add the import next to the other view imports:

```python
from rest_api.table_views import BulkTransitionView, BulkUpdateView
```

and the two routes into `urlpatterns` **before** `path("", include(router.urls))` — the router owns `artifacts/<pk>/`, so a later entry would be swallowed:

```python
    # Table view — bulk write endpoints (Tabellenansicht spec §3). Must precede
    # router.urls: the ArtifactViewSet detail pattern would otherwise match
    # "bulk-update" as a pk.
    path(
        "artifacts/bulk-update/",
        BulkUpdateView.as_view(),
        name="artifact-bulk-update",
    ),
    path(
        "artifacts/bulk-transition/",
        BulkTransitionView.as_view(),
        name="artifact-bulk-transition",
    ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `BT rest_api/tests/test_table_views.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/rest_api/table_views.py backend/rest_api/urls.py backend/rest_api/tests/test_table_views.py
git commit -m "feat(table): add REST bulk update and bulk transition endpoints"
```

---

## Task 11: REST — table query endpoint

**Files:**
- Modify: `backend/rest_api/table_views.py` (add `TableQueryView`), `backend/rest_api/urls.py`
- Test: `backend/rest_api/tests/test_table_query_view.py`

**Interfaces:**
- Consumes: `TableQueryService.query/serialize_rows` (Task 3), `rest_api.serializers.StandardPagination`
- Produces: `TableQueryView`, route `GET /api/v1/artifacts/table/`, helper `parse_json_param(raw, name, lang)`

- [ ] **Step 1: Write the failing test**

Create `backend/rest_api/tests/test_table_query_view.py`:

```python
"""GET /api/v1/artifacts/table/ — the single query source of the table view."""
from __future__ import annotations

import json

import pytest

from persistence.models import Artifact, Requirement
from persistence.tenancy import TenantContext

ATTRS = [
    {"name": "title", "kind": "core", "type": "text", "editable": True, "visible": True, "order": 1},
    {"name": "category", "kind": "core", "type": "enum", "editable": True, "visible": True, "order": 2},
    {"name": "status", "kind": "core", "type": "enum", "editable": "workflow", "visible": True, "order": 3},
]


@pytest.fixture(autouse=True)
def _stub_attributes(monkeypatch):
    from application import table_query_service as tqs

    monkeypatch.setattr(tqs, "resolve_attributes", lambda ctx, workspace_id, item_type: ATTRS)


@pytest.fixture
def requirements(tenant, workspace):
    TenantContext.set_tenant(tenant.id)
    try:
        made = []
        for title, category in (("Brake force", "safety"), ("Cabin light", "functional")):
            art = Artifact.objects.create(
                tenant=tenant, workspace=workspace, artifact_type="Requirement"
            )
            made.append(
                Requirement.objects.create(
                    tenant=tenant, artifact=art, title=title, category=category, status="draft"
                )
            )
        return made
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db
def test_table_query_returns_a_paginated_envelope(authed_client, workspace, requirements):
    response = authed_client.get(
        "/api/v1/artifacts/table/",
        {"workspace_id": str(workspace.id), "item_type": "Requirement"},
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["count"] == 2
    assert {"page_size", "max_page_size", "results"} <= set(body)
    assert {"id", "artifact_id", "title", "status"} <= set(body["results"][0])


@pytest.mark.django_db
def test_table_query_applies_filters_and_sort(authed_client, workspace, requirements):
    response = authed_client.get(
        "/api/v1/artifacts/table/",
        {
            "workspace_id": str(workspace.id),
            "item_type": "Requirement",
            "filters": json.dumps({"category": {"op": "in", "value": ["safety"]}}),
            "sort": json.dumps([{"field": "title", "dir": "asc"}]),
        },
    )
    assert response.status_code == 200, response.content
    assert [r["title"] for r in response.json()["results"]] == ["Brake force"]


@pytest.mark.django_db
def test_table_query_limits_the_returned_columns(authed_client, workspace, requirements):
    response = authed_client.get(
        "/api/v1/artifacts/table/",
        {"workspace_id": str(workspace.id), "item_type": "Requirement", "columns": "title"},
    )
    row = response.json()["results"][0]
    assert "title" in row
    assert "category" not in row


@pytest.mark.django_db
def test_table_query_rejects_an_unknown_filter_field(authed_client, workspace, requirements):
    response = authed_client.get(
        "/api/v1/artifacts/table/",
        {
            "workspace_id": str(workspace.id),
            "item_type": "Requirement",
            "filters": json.dumps({"nope": {"op": "contains", "value": "x"}}),
        },
    )
    assert response.status_code == 400
    assert "nope" in response.json()["error"]["message"]


@pytest.mark.django_db
def test_table_query_rejects_malformed_filter_json(authed_client, workspace, requirements):
    response = authed_client.get(
        "/api/v1/artifacts/table/",
        {"workspace_id": str(workspace.id), "item_type": "Requirement", "filters": "{oops"},
    )
    assert response.status_code == 400
    assert "filters" in response.json()["error"]["message"]


@pytest.mark.django_db
def test_table_query_rejects_an_unsupported_item_type(authed_client, workspace):
    response = authed_client.get(
        "/api/v1/artifacts/table/",
        {"workspace_id": str(workspace.id), "item_type": "Goal"},
    )
    assert response.status_code == 400
    assert "Goal" in response.json()["error"]["message"]


@pytest.mark.django_db
def test_artifacts_list_route_is_untouched(authed_client, workspace, requirements):
    """The tree-summary shape of /artifacts/ must not change (scope decision 1)."""
    response = authed_client.get("/api/v1/artifacts/", {"workspace_id": str(workspace.id)})
    assert response.status_code == 200
    assert "artifact_type" in response.json()["results"][0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `BT rest_api/tests/test_table_query_view.py -v`
Expected: FAIL — 404 on `/api/v1/artifacts/table/`

- [ ] **Step 3: Write minimal implementation**

Add to `backend/rest_api/table_views.py`:

```python
import json

from application.table_query_service import TableQueryService
from rest_api.serializers import StandardPagination


def parse_json_param(raw: Any, name: str, lang: str) -> tuple[Any, Response | None]:
    """Parse a JSON-encoded query parameter, or answer 400.

    ``filters``/``sort`` are JSON objects in a GET query string (spec §4.1).
    A malformed value is reported explicitly rather than ignored — the whole
    point of the new filter API is that a bad parameter stops being silently
    dropped the way the 86 legacy ``query_params.get()`` sites drop it (C8).
    """
    if raw in (None, ""):
        return None, None
    try:
        return json.loads(raw), None
    except (TypeError, ValueError):
        return None, _validation_error(f"'{name}' is not valid JSON", lang)


class TableQueryView(APIView):
    """GET /api/v1/artifacts/table/ — spec §4.1.

    Query: ``workspace_id`` (required), ``item_type`` (required),
    ``filters`` (JSON), ``sort`` (JSON), ``columns`` (comma-separated),
    plus ``page``/``page_size`` from ``StandardPagination``.

    Deliberately a sibling route rather than ``GET /artifacts/?item_type=``:
    ``/artifacts/`` already answers the Artifact tree-summary shape, and one
    URL cannot carry two response schemas without breaking the OpenAPI
    contract (see the plan's scope decision 1).
    """

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        workspace_id, error = parse_workspace_id(
            request.query_params.get("workspace_id"), lang
        )
        if error is not None:
            return error
        item_type = request.query_params.get("item_type") or ""
        if not item_type:
            return _validation_error("'item_type' is required", lang)

        filters, error = parse_json_param(request.query_params.get("filters"), "filters", lang)
        if error is not None:
            return error
        sort, error = parse_json_param(request.query_params.get("sort"), "sort", lang)
        if error is not None:
            return error
        raw_columns = request.query_params.get("columns")
        columns = [c for c in (raw_columns or "").split(",") if c] or None

        ctx = get_auth_context(request)
        service = TableQueryService()
        try:
            queryset = service.query(
                ctx=ctx,
                workspace_id=workspace_id,
                item_type=item_type,
                filters=filters,
                sort=sort,
            )
            paginator = StandardPagination()
            page = paginator.paginate_queryset(queryset, request, view=self)
            rows = service.serialize_rows(
                ctx=ctx,
                workspace_id=workspace_id,
                item_type=item_type,
                rows=page if page is not None else queryset,
                columns=columns,
            )
        except Exception as exc:
            return _service_error_response(exc, lang)
        if page is None:
            return Response(rows)
        return paginator.get_paginated_response(rows)
```

Extend `__all__` with `"TableQueryView"`, add `TableQueryView` to the `rest_api/urls.py` import, and register the route in the same pre-router block:

```python
    # Table view — the single query source for the grid (spec §4.1).
    path("artifacts/table/", TableQueryView.as_view(), name="artifact-table"),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `BT rest_api/tests/test_table_query_view.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/rest_api/table_views.py backend/rest_api/urls.py backend/rest_api/tests/test_table_query_view.py
git commit -m "feat(table): add filterable artifact table query endpoint"
```

---

## Task 12: REST — saved views and table view state

**Files:**
- Modify: `backend/rest_api/table_views.py`, `backend/rest_api/urls.py`
- Test: `backend/rest_api/tests/test_saved_view_views.py`

**Interfaces:**
- Consumes: `SavedViewService`, `TableViewStateService` (Task 9), `TableQueryView` helpers (Task 11)
- Produces: `SavedViewListCreateView`, `SavedViewDetailView`, `SavedViewApplyView`, `TableViewStateView`; routes `GET|POST /api/v1/saved-views/`, `GET|PATCH|DELETE /api/v1/saved-views/<uuid:pk>/`, `GET /api/v1/saved-views/<uuid:pk>/apply/`, `GET|PUT /api/v1/users/me/table-view-state/`

- [ ] **Step 1: Write the failing test**

Create `backend/rest_api/tests/test_saved_view_views.py`:

```python
"""Saved views + auto-persisted table state over REST."""
from __future__ import annotations

import pytest

from persistence.models import Artifact, Requirement
from persistence.tenancy import TenantContext

ATTRS = [
    {"name": "title", "kind": "core", "type": "text", "editable": True, "visible": True, "order": 1},
    {"name": "category", "kind": "core", "type": "enum", "editable": True, "visible": True, "order": 2},
]


@pytest.fixture(autouse=True)
def _stub_attributes(monkeypatch):
    from application import table_query_service as tqs

    monkeypatch.setattr(tqs, "resolve_attributes", lambda ctx, workspace_id, item_type: ATTRS)


@pytest.fixture
def requirement(tenant, workspace) -> Requirement:
    TenantContext.set_tenant(tenant.id)
    try:
        art = Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="Requirement"
        )
        return Requirement.objects.create(
            tenant=tenant, artifact=art, title="Brake force", category="safety", status="draft"
        )
    finally:
        TenantContext.clear_tenant()


def _create(authed_client, workspace, **overrides):
    payload = {
        "workspace_id": str(workspace.id),
        "item_type": "Requirement",
        "name": "Safety only",
        "columns": [{"field": "title", "order": 0}],
        "filters": {"category": {"op": "in", "value": ["safety"]}},
        "sort": [{"field": "title", "dir": "asc"}],
        "visibility": "private",
    }
    payload.update(overrides)
    return authed_client.post("/api/v1/saved-views/", payload, format="json")


@pytest.mark.django_db
def test_create_and_list_saved_view(authed_client, workspace):
    created = _create(authed_client, workspace)
    assert created.status_code == 201, created.content
    assert created.json()["is_owner"] is True

    listed = authed_client.get(
        "/api/v1/saved-views/", {"workspace_id": str(workspace.id), "item_type": "Requirement"}
    )
    assert listed.status_code == 200
    assert [v["name"] for v in listed.json()["results"]] == ["Safety only"]


@pytest.mark.django_db
def test_patch_and_delete_saved_view(authed_client, workspace):
    view_id = _create(authed_client, workspace).json()["id"]

    patched = authed_client.patch(
        f"/api/v1/saved-views/{view_id}/", {"name": "Renamed"}, format="json"
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Renamed"

    deleted = authed_client.delete(f"/api/v1/saved-views/{view_id}/")
    assert deleted.status_code == 204
    assert authed_client.get(f"/api/v1/saved-views/{view_id}/").status_code == 404


@pytest.mark.django_db
def test_apply_returns_the_filtered_rows(authed_client, workspace, requirement):
    view_id = _create(authed_client, workspace).json()["id"]
    response = authed_client.get(f"/api/v1/saved-views/{view_id}/apply/")
    assert response.status_code == 200, response.content
    body = response.json()
    assert [r["title"] for r in body["results"]] == ["Brake force"]
    assert "category" not in body["results"][0]  # the view stores only "title"


@pytest.mark.django_db
def test_create_rejects_an_unknown_visibility(authed_client, workspace):
    response = _create(authed_client, workspace, visibility="public")
    assert response.status_code == 400


@pytest.mark.django_db
def test_table_view_state_round_trips(authed_client, workspace):
    empty = authed_client.get(
        "/api/v1/users/me/table-view-state/",
        {"workspace_id": str(workspace.id), "item_type": "Requirement"},
    )
    assert empty.status_code == 200
    assert empty.json() == {"columns": [], "filters": {}, "sort": []}

    saved = authed_client.put(
        "/api/v1/users/me/table-view-state/",
        {
            "workspace_id": str(workspace.id),
            "item_type": "Requirement",
            "columns": [{"field": "title", "order": 0}],
            "filters": {},
            "sort": [{"field": "title", "dir": "desc"}],
        },
        format="json",
    )
    assert saved.status_code == 200, saved.content
    assert saved.json()["sort"] == [{"field": "title", "dir": "desc"}]

    again = authed_client.get(
        "/api/v1/users/me/table-view-state/",
        {"workspace_id": str(workspace.id), "item_type": "Requirement"},
    )
    assert again.json()["columns"] == [{"field": "title", "order": 0}]


@pytest.mark.django_db
def test_saved_view_detail_rejects_a_malformed_id(authed_client):
    assert authed_client.get("/api/v1/saved-views/not-a-uuid/").status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `BT rest_api/tests/test_saved_view_views.py -v`
Expected: FAIL — 404 on `/api/v1/saved-views/`

- [ ] **Step 3: Write minimal implementation**

Add to `backend/rest_api/table_views.py`:

```python
from application.saved_view_service import SavedViewService, TableViewStateService


class SavedViewListCreateView(APIView):
    """GET/POST /api/v1/saved-views/ — spec §4.2.

    GET  ``?workspace_id=&item_type=`` → own views plus workspace-shared ones.
    POST ``{workspace_id, item_type, name, columns, filters, sort, visibility}``
    → 201 with the created view.
    """

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        workspace_id, error = parse_workspace_id(
            request.query_params.get("workspace_id"), lang
        )
        if error is not None:
            return error
        try:
            views = SavedViewService().list(
                ctx=get_auth_context(request),
                workspace_id=workspace_id,
                item_type=request.query_params.get("item_type") or None,
            )
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response({"count": len(views), "results": [v.as_dict() for v in views]})

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        workspace_id, error = parse_workspace_id(request.data.get("workspace_id"), lang)
        if error is not None:
            return error
        try:
            view = SavedViewService().create(
                ctx=get_auth_context(request),
                workspace_id=workspace_id,
                item_type=str(request.data.get("item_type") or ""),
                name=str(request.data.get("name") or ""),
                columns=request.data.get("columns") or [],
                filters=request.data.get("filters") or {},
                sort=request.data.get("sort") or [],
                visibility=str(request.data.get("visibility") or "private"),
            )
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(view.as_dict(), status=status.HTTP_201_CREATED)


class SavedViewDetailView(APIView):
    """GET/PATCH/DELETE /api/v1/saved-views/<uuid:pk>/ — spec §4.2.

    PATCH and DELETE are owner-or-admin only; a foreign *private* view answers
    404 rather than 403 so its existence is not disclosed.
    """

    def get(self, request: Request, pk: UUID, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            view = SavedViewService().get(ctx=get_auth_context(request), view_id=pk)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(view.as_dict())

    def patch(self, request: Request, pk: UUID, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        allowed = ("name", "columns", "filters", "sort", "visibility")
        changes = {k: request.data[k] for k in allowed if k in request.data}
        if not changes:
            return _validation_error(
                f"Provide at least one of: {', '.join(allowed)}", lang
            )
        try:
            view = SavedViewService().update(
                ctx=get_auth_context(request), view_id=pk, **changes
            )
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(view.as_dict())

    def delete(self, request: Request, pk: UUID, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        try:
            SavedViewService().delete(ctx=get_auth_context(request), view_id=pk)
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SavedViewApplyView(APIView):
    """GET /api/v1/saved-views/<uuid:pk>/apply/ — spec §4.2.

    Runs the stored filters/sort/columns and returns the same paginated row
    envelope as ``artifacts/table/``. Fail-soft by design (spec §6): a view
    whose filter names a value that no longer exists yields an empty page, not
    an error — only a structurally invalid filter (unknown field/operator) is
    still a 400.
    """

    def get(self, request: Request, pk: UUID, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        try:
            view = SavedViewService().get(ctx=ctx, view_id=pk)
            service = TableQueryService()
            queryset = service.query(
                ctx=ctx,
                workspace_id=view.workspace_id,
                item_type=view.item_type,
                filters=view.filters,
                sort=view.sort,
            )
            paginator = StandardPagination()
            page = paginator.paginate_queryset(queryset, request, view=self)
            columns = [c["field"] for c in sorted(
                view.columns, key=lambda c: c.get("order", 0)
            )] or None
            rows = service.serialize_rows(
                ctx=ctx,
                workspace_id=view.workspace_id,
                item_type=view.item_type,
                rows=page if page is not None else queryset,
                columns=columns,
            )
        except Exception as exc:
            return _service_error_response(exc, lang)
        if page is None:
            return Response(rows)
        return paginator.get_paginated_response(rows)


class TableViewStateView(APIView):
    """GET/PUT /api/v1/users/me/table-view-state/ — spec §4.2.

    The spec defines the model but no endpoint; the frontend needs one to load
    and persist "where I last was". Shaped after ``users/me/preferences/``:
    GET answers empty defaults on first access instead of 404.
    """

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        workspace_id, error = parse_workspace_id(
            request.query_params.get("workspace_id"), lang
        )
        if error is not None:
            return error
        item_type = request.query_params.get("item_type") or ""
        if not item_type:
            return _validation_error("'item_type' is required", lang)
        try:
            state = TableViewStateService().get(
                ctx=get_auth_context(request),
                workspace_id=workspace_id,
                item_type=item_type,
            )
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(state)

    def put(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        lang = detect_lang(request)
        workspace_id, error = parse_workspace_id(request.data.get("workspace_id"), lang)
        if error is not None:
            return error
        item_type = str(request.data.get("item_type") or "")
        if not item_type:
            return _validation_error("'item_type' is required", lang)
        try:
            state = TableViewStateService().save(
                ctx=get_auth_context(request),
                workspace_id=workspace_id,
                item_type=item_type,
                columns=request.data.get("columns") or [],
                filters=request.data.get("filters") or {},
                sort=request.data.get("sort") or [],
            )
        except Exception as exc:
            return _service_error_response(exc, lang)
        return Response(state)
```

Extend `__all__` with the four new class names, import them in `backend/rest_api/urls.py`, and register in the pre-router block:

```python
    # Saved table views (spec §4.2). `<uuid:pk>` makes a malformed id a plain
    # 404 routing miss instead of a 400 — matching the aux-route convention.
    path("saved-views/", SavedViewListCreateView.as_view(), name="saved-view-list"),
    path(
        "saved-views/<uuid:pk>/apply/",
        SavedViewApplyView.as_view(),
        name="saved-view-apply",
    ),
    path(
        "saved-views/<uuid:pk>/",
        SavedViewDetailView.as_view(),
        name="saved-view-detail",
    ),
    # Auto-persisted last table state, per user+workspace+item_type.
    path(
        "users/me/table-view-state/",
        TableViewStateView.as_view(),
        name="user-table-view-state",
    ),
```

The `apply/` path must be listed before the bare `<uuid:pk>/` path.

- [ ] **Step 4: Run test to verify it passes**

Run: `BT rest_api/tests/test_saved_view_views.py rest_api/tests/test_architecture.py -v`
Expected: PASS (6 + the architecture ratchet tests; `table_views.py` must report 0 direct-ORM lines)

- [ ] **Step 5: Commit**

```bash
git add backend/rest_api/table_views.py backend/rest_api/urls.py backend/rest_api/tests/test_saved_view_views.py
git commit -m "feat(table): add saved view and table view state REST endpoints"
```

---

## Task 13: MCP — artifact.bulk_update and artifact.bulk_transition

**Files:**
- Modify: `backend/mcp_server/tools/cross_cutting.py` (owns the `artifact` prefix), `backend/mcp_server/tool_registry.py`
- Test: `backend/mcp_server/tests/test_bulk_tools.py`

**Interfaces:**
- Consumes: `BulkEditService` (Tasks 6–7), `mcp_server.tools.base.{BaseToolGroup, require_uuid, require_param}`, `ToolResult`
- Produces: tools `artifact.bulk_update`, `artifact.bulk_transition` (both WRITE-gated, both requiring `workspace_id`)

- [ ] **Step 1: Write the failing test**

Create `backend/mcp_server/tests/test_bulk_tools.py`:

```python
"""artifact.bulk_update / artifact.bulk_transition (spec §3.3)."""
from __future__ import annotations

import json
import uuid

import pytest

from application import bulk_edit_service as bes
from application.base import ValidationError
from application.bulk_edit_service import BulkItemFailure, BulkResult
from auth_tenancy.context import AuthContext
from mcp_server.tools.cross_cutting import CrossCuttingToolGroup


@pytest.fixture
def ctx() -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("editor",),
        auth_method="api_key",
    )


def _schema(name: str) -> dict:
    return next(s for s in CrossCuttingToolGroup().get_tool_schemas() if s["name"] == name)


def test_both_tools_are_advertised():
    names = {s["name"] for s in CrossCuttingToolGroup().get_tool_schemas()}
    assert {"artifact.bulk_update", "artifact.bulk_transition"} <= names


def test_workspace_id_is_a_required_input():
    """The workspace-scope ratchet only accepts an ENFORCED workspace_id."""
    for name in ("artifact.bulk_update", "artifact.bulk_transition"):
        assert "workspace_id" in _schema(name)["inputSchema"]["required"]


@pytest.mark.django_db
def test_bulk_update_returns_the_partial_success_envelope(ctx, monkeypatch):
    ok, bad = str(uuid.uuid4()), str(uuid.uuid4())

    def _fake(self, **kwargs):
        return BulkResult(updated=[ok], failed=[BulkItemFailure(id=bad, error="nope")])

    monkeypatch.setattr(bes.BulkEditService, "bulk_update", _fake)
    result = CrossCuttingToolGroup().execute_tool(
        "artifact.bulk_update",
        {
            "workspace_id": str(uuid.uuid4()),
            "item_type": "Requirement",
            "ids": [ok, bad],
            "fields": {"category": "safety"},
        },
        ctx,
    )
    assert result.success is True
    assert result.data["updated"] == [ok]
    assert result.data["failed"] == [{"id": bad, "error": "nope"}]
    json.dumps(result.data)  # stdlib json — no UUIDs may survive in the payload


@pytest.mark.django_db
def test_bulk_update_on_a_workflow_field_is_a_validation_error(ctx, monkeypatch):
    """Same guardrail as REST — the MCP path must not have its own opinion."""

    def _raise(self, **kwargs):
        raise ValidationError(
            "Fields owned by the workflow engine cannot be bulk-updated: status. "
            "Use artifacts/bulk-transition/ instead."
        )

    monkeypatch.setattr(bes.BulkEditService, "bulk_update", _raise)
    result = CrossCuttingToolGroup().execute_tool(
        "artifact.bulk_update",
        {
            "workspace_id": str(uuid.uuid4()),
            "item_type": "Requirement",
            "ids": [str(uuid.uuid4())],
            "fields": {"status": "approved"},
        },
        ctx,
    )
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "status" in result.message


@pytest.mark.django_db
def test_bulk_transition_forwards_to_state_and_change_reason(ctx, monkeypatch):
    seen = {}

    def _fake(self, **kwargs):
        seen.update(kwargs)
        return BulkResult(updated=[str(kwargs["ids"][0])], failed=[])

    monkeypatch.setattr(bes.BulkEditService, "bulk_transition", _fake)
    result = CrossCuttingToolGroup().execute_tool(
        "artifact.bulk_transition",
        {
            "workspace_id": str(uuid.uuid4()),
            "item_type": "Requirement",
            "ids": [str(uuid.uuid4())],
            "to_state": "in_review",
            "change_reason": "batch",
        },
        ctx,
    )
    assert result.success is True
    assert seen["to_state"] == "in_review"
    assert seen["change_reason"] == "batch"


def test_both_tools_stay_write_gated():
    from mcp_server.tool_registry import _READ_ONLY_TOOL_NAMES

    assert "artifact.bulk_update" not in _READ_ONLY_TOOL_NAMES
    assert "artifact.bulk_transition" not in _READ_ONLY_TOOL_NAMES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `BT mcp_server/tests/test_bulk_tools.py -v`
Expected: FAIL on `test_both_tools_are_advertised` — the schemas do not exist yet.

- [ ] **Step 3: Write minimal implementation**

In `backend/mcp_server/tools/cross_cutting.py`, add the two entries to `_TOOL_MAP`:

```python
        "artifact.bulk_update": "_handle_bulk_update",
        "artifact.bulk_transition": "_handle_bulk_transition",
```

append to `_TOOL_SCHEMAS`:

```python
        {
            "name": "artifact.bulk_update",
            "description": (
                "Update the same fields on many artifacts of one type. "
                "Fields owned by the workflow engine (status) are rejected — "
                "use artifact.bulk_transition for those."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "item_type": {"type": "string"},
                    "ids": {"type": "array", "items": {"type": "string"}},
                    "fields": {"type": "object"},
                    "change_reason": {"type": "string"},
                },
                "required": ["workspace_id", "item_type", "ids", "fields"],
            },
        },
        {
            "name": "artifact.bulk_transition",
            "description": (
                "Move many artifacts of one type to the same workflow state. "
                "Every item runs a full workflow transition, so role, "
                "change_reason and signature gates apply per item."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "item_type": {"type": "string"},
                    "ids": {"type": "array", "items": {"type": "string"}},
                    "to_state": {"type": "string"},
                    "change_reason": {"type": "string"},
                    "credential": {"type": "string"},
                },
                "required": ["workspace_id", "item_type", "ids", "to_state"],
            },
        },
```

and the two handlers (matching the module's existing error-mapping convention):

```python
    def _parse_ids(self, params: Dict[str, Any]) -> list[UUID]:
        raw = params.get("ids")
        if not isinstance(raw, list) or not raw:
            raise ParameterError("Parameter 'ids' must be a non-empty array")
        try:
            return [UUID(str(value)) for value in raw]
        except (ValueError, AttributeError, TypeError):
            raise ParameterError("Parameter 'ids' contains a value that is not a UUID")

    def _handle_bulk_update(
        self, params: Dict[str, Any], ctx: AuthContext
    ) -> ToolResult:
        """artifact.bulk_update — spec §3.3, same service as PATCH artifacts/bulk-update/."""
        try:
            result = BulkEditService().bulk_update(
                ctx=ctx,
                workspace_id=require_uuid(params, "workspace_id"),
                item_type=require_param(params, "item_type"),
                ids=self._parse_ids(params),
                fields=params.get("fields") or {},
                change_reason=str(params.get("change_reason") or ""),
            )
        except ParameterError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok(result.as_dict())

    def _handle_bulk_transition(
        self, params: Dict[str, Any], ctx: AuthContext
    ) -> ToolResult:
        """artifact.bulk_transition — spec §3.3, one real transition per item."""
        try:
            result = BulkEditService().bulk_transition(
                ctx=ctx,
                workspace_id=require_uuid(params, "workspace_id"),
                item_type=require_param(params, "item_type"),
                ids=self._parse_ids(params),
                to_state=require_param(params, "to_state"),
                change_reason=str(params.get("change_reason") or ""),
                credential=str(params.get("credential") or ""),
            )
        except ParameterError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok(result.as_dict())
```

Add whatever of `from application.bulk_edit_service import BulkEditService`,
`from mcp_server.tools.base import ParameterError, require_param, require_uuid`,
`from application.base import PermissionDeniedError, ValidationError` and `from uuid import UUID`
the module does not already import.

No change to `_READ_ONLY_TOOL_NAMES` — unknown tool names default to WRITE-gated, which is exactly right for both.

- [ ] **Step 4: Run test to verify it passes**

Run: `BT mcp_server/tests/test_bulk_tools.py mcp_server/tests/test_mcp_workspace_scope.py -v`
Expected: PASS (5 passed + the workspace-scope ratchet, which both tools satisfy through their required `workspace_id`)

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_server/tools/cross_cutting.py backend/mcp_server/tests/test_bulk_tools.py
git commit -m "feat(table): expose bulk update and bulk transition as MCP tools"
```

---

## Task 14: MCP — saved_view.list and saved_view.apply

**Files:**
- Create: `backend/mcp_server/tools/saved_view.py`
- Modify: `backend/mcp_server/tool_registry.py`
- Test: `backend/mcp_server/tests/test_saved_view_tools.py`

**Interfaces:**
- Consumes: `SavedViewService` (Task 9), `TableQueryService` (Task 3)
- Produces: `SavedViewToolGroup`, tools `saved_view.list`, `saved_view.apply`, registry prefix `"saved_view"`

- [ ] **Step 1: Write the failing test**

Create `backend/mcp_server/tests/test_saved_view_tools.py`:

```python
"""saved_view.* — an agent loads a named view instead of hand-building filters."""
from __future__ import annotations

import json
import uuid

import pytest

from application.base import NotFoundError
from application.saved_view_service import SavedViewDTO
from auth_tenancy.context import AuthContext
from mcp_server.tools.saved_view import SavedViewToolGroup


@pytest.fixture
def ctx() -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("viewer",),
        auth_method="api_key",
    )


def _dto(workspace_id: uuid.UUID) -> SavedViewDTO:
    return SavedViewDTO(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        item_type="Requirement",
        name="Safety only",
        owner_id=uuid.uuid4(),
        owner_username="owner",
        columns=[{"field": "title", "order": 0}],
        filters={"category": {"op": "in", "value": ["safety"]}},
        sort=[{"field": "title", "dir": "asc"}],
        visibility="workspace",
        is_owner=False,
    )


def test_both_tools_require_workspace_id():
    schemas = {s["name"]: s for s in SavedViewToolGroup().get_tool_schemas()}
    assert set(schemas) == {"saved_view.list", "saved_view.apply"}
    assert "workspace_id" in schemas["saved_view.list"]["inputSchema"]["required"]
    assert "workspace_id" in schemas["saved_view.apply"]["inputSchema"]["required"]


@pytest.mark.django_db
def test_list_returns_json_primitives(ctx, monkeypatch):
    workspace_id = uuid.uuid4()
    monkeypatch.setattr(
        "mcp_server.tools.saved_view.SavedViewService.list",
        lambda self, **kwargs: [_dto(workspace_id)],
    )
    result = SavedViewToolGroup().execute_tool(
        "saved_view.list", {"workspace_id": str(workspace_id)}, ctx
    )
    assert result.success is True
    assert result.data["views"][0]["name"] == "Safety only"
    json.dumps(result.data)


@pytest.mark.django_db
def test_apply_runs_the_stored_filters(ctx, monkeypatch):
    workspace_id = uuid.uuid4()
    view = _dto(workspace_id)
    seen = {}

    monkeypatch.setattr(
        "mcp_server.tools.saved_view.SavedViewService.get", lambda self, **kwargs: view
    )

    def _query(self, **kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr("mcp_server.tools.saved_view.TableQueryService.query", _query)
    monkeypatch.setattr(
        "mcp_server.tools.saved_view.TableQueryService.serialize_rows",
        lambda self, **kwargs: [{"id": "1", "title": "Brake force"}],
    )

    result = SavedViewToolGroup().execute_tool(
        "saved_view.apply",
        {"workspace_id": str(workspace_id), "view_id": str(view.id)},
        ctx,
    )
    assert result.success is True
    assert result.data["rows"] == [{"id": "1", "title": "Brake force"}]
    assert seen["filters"] == view.filters
    assert seen["sort"] == view.sort


@pytest.mark.django_db
def test_apply_refuses_a_view_from_another_workspace(ctx, monkeypatch):
    view = _dto(uuid.uuid4())
    monkeypatch.setattr(
        "mcp_server.tools.saved_view.SavedViewService.get", lambda self, **kwargs: view
    )
    result = SavedViewToolGroup().execute_tool(
        "saved_view.apply",
        {"workspace_id": str(uuid.uuid4()), "view_id": str(view.id)},
        ctx,
    )
    assert result.success is False
    assert result.error_code == "NOT_FOUND"


@pytest.mark.django_db
def test_apply_maps_not_found(ctx, monkeypatch):
    def _raise(self, **kwargs):
        raise NotFoundError("SavedView missing")

    monkeypatch.setattr("mcp_server.tools.saved_view.SavedViewService.get", _raise)
    result = SavedViewToolGroup().execute_tool(
        "saved_view.apply",
        {"workspace_id": str(uuid.uuid4()), "view_id": str(uuid.uuid4())},
        ctx,
    )
    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_both_tools_are_registered_as_read_only():
    from mcp_server.tool_registry import _READ_ONLY_TOOL_NAMES

    assert {"saved_view.list", "saved_view.apply"} <= _READ_ONLY_TOOL_NAMES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `BT mcp_server/tests/test_saved_view_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_server.tools.saved_view'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/mcp_server/tools/saved_view.py`:

```python
"""MCP tool group for the ``saved_view.*`` namespace (Tabellenansicht spec §4.2).

Read-only: an agent loads a named, human-curated view instead of hand-building
filter JSON. Both tools *require* ``workspace_id`` and enforce it — the
workspace-scope ratchet (``mcp_server/workspace_scope.py``) deliberately does
not accept a merely declared parameter, so ``apply`` re-checks that the view it
loaded really belongs to the workspace the caller was gated against.
"""
from __future__ import annotations

from typing import Any, Dict

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.saved_view_service import SavedViewService
from application.table_query_service import TableQueryService
from auth_tenancy.context import AuthContext
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup, ParameterError, require_uuid


class SavedViewToolGroup(BaseToolGroup):
    """``saved_view.list`` and ``saved_view.apply``."""

    _TOOL_MAP = {
        "saved_view.list": "_handle_list",
        "saved_view.apply": "_handle_apply",
    }
    _TOOL_SCHEMAS = [
        {
            "name": "saved_view.list",
            "description": (
                "List saved table views of a workspace: the caller's own plus "
                "every workspace-shared one."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "item_type": {"type": "string"},
                },
                "required": ["workspace_id"],
            },
        },
        {
            "name": "saved_view.apply",
            "description": (
                "Run a saved view's filters/sort/columns and return the "
                "matching artifacts."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "view_id": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["workspace_id", "view_id"],
            },
        },
    ]

    #: Hard cap so an agent cannot pull an unbounded result set in one call.
    _MAX_ROWS = 200

    def _handle_list(self, params: Dict[str, Any], ctx: AuthContext) -> ToolResult:
        try:
            views = SavedViewService().list(
                ctx=ctx,
                workspace_id=require_uuid(params, "workspace_id"),
                item_type=params.get("item_type") or None,
            )
        except ParameterError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok({"views": [v.as_dict() for v in views]})

    def _handle_apply(self, params: Dict[str, Any], ctx: AuthContext) -> ToolResult:
        try:
            workspace_id = require_uuid(params, "workspace_id")
            view = SavedViewService().get(
                ctx=ctx, view_id=require_uuid(params, "view_id")
            )
            if str(view.workspace_id) != str(workspace_id):
                # The RBAC gate was evaluated against workspace_id, so a view
                # from anywhere else must not be served through it.
                return ToolResult.error(
                    "NOT_FOUND", "SavedView not found in this workspace"
                )
            limit = min(int(params.get("limit") or self._MAX_ROWS), self._MAX_ROWS)
            service = TableQueryService()
            queryset = service.query(
                ctx=ctx,
                workspace_id=view.workspace_id,
                item_type=view.item_type,
                filters=view.filters,
                sort=view.sort,
            )
            columns = [
                c["field"] for c in sorted(view.columns, key=lambda c: c.get("order", 0))
            ] or None
            rows = service.serialize_rows(
                ctx=ctx,
                workspace_id=view.workspace_id,
                item_type=view.item_type,
                rows=list(queryset[:limit]),
                columns=columns,
            )
        except ParameterError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        return ToolResult.ok(
            {
                "view": view.as_dict(),
                "rows": rows,
                "truncated": len(rows) >= limit,
            }
        )
```

In `backend/mcp_server/tool_registry.py`:
- add `from mcp_server.tools.saved_view import SavedViewToolGroup` to the lazy import block in `_ensure_groups`,
- add `"saved_view": SavedViewToolGroup(),` to the `register_groups({...})` mapping,
- add both names to `_READ_ONLY_TOOL_NAMES` (only `.read`/`.query` suffixes are auto-exempt; `.list`/`.apply` are not):

```python
        # Tabellenansicht spec §4.2: both tools are plain reads of saved
        # filter config + the rows it selects — same class as artifact.search.
        "saved_view.list",
        "saved_view.apply",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `BT mcp_server/tests/test_saved_view_tools.py mcp_server/tests/test_mcp_workspace_scope.py mcp_server/tests/test_export_tool_manifest.py -v`
Expected: PASS (6 passed, plus the workspace-scope and tool-manifest ratchets)

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_server/tools/saved_view.py backend/mcp_server/tool_registry.py backend/mcp_server/tests/test_saved_view_tools.py
git commit -m "feat(table): add saved_view MCP tool group"
```

---

## Task 15: Frontend API wrapper

**Files:**
- Create: `frontend/src/api/table-views.ts`
- Test: `frontend/src/test/tableViewsApi.test.ts`

**Interfaces:**
- Consumes: `apiClient`, `getList` from `frontend/src/api/client.ts`; the REST routes of Tasks 10–12
- Produces: types `FilterOperator`, `FilterConstraint`, `TableFilters`, `SortTerm`, `TableSort`, `ColumnSpec`, `TableRow`, `TableViewState`, `BulkFailure`, `BulkResult`, `SavedView`; objects `tableApi`, `savedViewsApi`, `tableViewStateApi`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/tableViewsApi.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../api/client";
import { savedViewsApi, tableApi, tableViewStateApi } from "../api/table-views";

describe("table-views api", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("encodes filters and sort as JSON query parameters", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    } as never);

    await tableApi.query({
      workspaceId: "ws-1",
      itemType: "Requirement",
      filters: { title: { op: "contains", value: "brake" } },
      sort: [{ field: "title", dir: "asc" }],
      columns: ["title", "status"],
    });

    const url = get.mock.calls[0][0] as string;
    expect(url.startsWith("/artifacts/table/?")).toBe(true);
    const params = new URLSearchParams(url.split("?")[1]);
    expect(params.get("workspace_id")).toBe("ws-1");
    expect(params.get("item_type")).toBe("Requirement");
    expect(JSON.parse(params.get("filters") as string)).toEqual({
      title: { op: "contains", value: "brake" },
    });
    expect(JSON.parse(params.get("sort") as string)).toEqual([{ field: "title", dir: "asc" }]);
    expect(params.get("columns")).toBe("title,status");
  });

  it("omits empty filters and sort entirely", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    } as never);

    await tableApi.query({ workspaceId: "ws-1", itemType: "Risk", filters: {}, sort: [] });

    const params = new URLSearchParams((get.mock.calls[0][0] as string).split("?")[1]);
    expect(params.get("filters")).toBeNull();
    expect(params.get("sort")).toBeNull();
  });

  it("PATCHes bulk updates with the snake_case payload", async () => {
    const patch = vi
      .spyOn(apiClient, "patch")
      .mockResolvedValue({ updated: ["a"], failed: [] } as never);

    const result = await tableApi.bulkUpdate({
      workspaceId: "ws-1",
      itemType: "Requirement",
      ids: ["a"],
      fields: { category: "safety" },
      changeReason: "cleanup",
    });

    expect(patch).toHaveBeenCalledWith("/artifacts/bulk-update/", {
      workspace_id: "ws-1",
      item_type: "Requirement",
      ids: ["a"],
      fields: { category: "safety" },
      change_reason: "cleanup",
    });
    expect(result.updated).toEqual(["a"]);
  });

  it("POSTs bulk transitions with to_state", async () => {
    const post = vi
      .spyOn(apiClient, "post")
      .mockResolvedValue({ updated: [], failed: [] } as never);

    await tableApi.bulkTransition({
      workspaceId: "ws-1",
      itemType: "Requirement",
      ids: ["a"],
      toState: "in_review",
      changeReason: "batch",
    });

    expect(post).toHaveBeenCalledWith("/artifacts/bulk-transition/", {
      workspace_id: "ws-1",
      item_type: "Requirement",
      ids: ["a"],
      to_state: "in_review",
      change_reason: "batch",
      credential: "",
    });
  });

  it("reads and writes the table view state", async () => {
    const get = vi
      .spyOn(apiClient, "get")
      .mockResolvedValue({ columns: [], filters: {}, sort: [] } as never);
    const put = vi
      .spyOn(apiClient, "put")
      .mockResolvedValue({ columns: [], filters: {}, sort: [] } as never);

    await tableViewStateApi.get("ws-1", "Requirement");
    expect(get.mock.calls[0][0]).toContain("/users/me/table-view-state/?");

    await tableViewStateApi.save("ws-1", "Requirement", {
      columns: [{ field: "title", order: 0 }],
      filters: {},
      sort: [],
    });
    expect(put).toHaveBeenCalledWith("/users/me/table-view-state/", {
      workspace_id: "ws-1",
      item_type: "Requirement",
      columns: [{ field: "title", order: 0 }],
      filters: {},
      sort: [],
    });
  });

  it("applies a saved view through its own route", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    } as never);

    await savedViewsApi.apply("view-1");
    expect(get.mock.calls[0][0]).toBe("/saved-views/view-1/apply/");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `FT src/test/tableViewsApi.test.ts`
Expected: FAIL — `Failed to resolve import "../api/table-views"`

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/api/table-views.ts`:

```ts
/**
 * ARCH-L1-001 ReactFrontend — Table view API.
 *
 * Wraps the Tabellenansicht endpoints: /artifacts/table/,
 * /artifacts/bulk-update/, /artifacts/bulk-transition/, /saved-views/*,
 * /users/me/table-view-state/.
 *
 * The `filters` / `sort` shapes mirror the backend DSL in
 * `application/table_filter_dsl.py` one-to-one and are a frozen wire contract
 * (the Dokumentensicht feature reuses them for query-backed sections).
 */

import { apiClient } from "./client";
import type { PaginatedResponse, UUID } from "../types";

export type FilterOperator = "contains" | "in" | "gte" | "lte" | "eq";

export interface FilterConstraint {
  op: FilterOperator;
  value: string | number | boolean | string[];
}

/** One field maps to one constraint, or to several that are ANDed (ranges). */
export type TableFilters = Record<string, FilterConstraint | FilterConstraint[]>;

export interface SortTerm {
  field: string;
  dir: "asc" | "desc";
}

export type TableSort = SortTerm[];

export interface ColumnSpec {
  field: string;
  order: number;
}

export interface TableRow {
  id: UUID;
  artifact_id: UUID | null;
  version?: number | null;
  [field: string]: unknown;
}

export interface TableViewState {
  columns: ColumnSpec[];
  filters: TableFilters;
  sort: TableSort;
}

export interface BulkFailure {
  id: UUID;
  error: string;
}

export interface BulkResult {
  updated: UUID[];
  failed: BulkFailure[];
}

export interface SavedView {
  id: UUID;
  workspace_id: UUID;
  item_type: string;
  name: string;
  owner_id: UUID;
  owner_username: string;
  columns: ColumnSpec[];
  filters: TableFilters;
  sort: TableSort;
  visibility: "private" | "workspace";
  is_owner: boolean;
}

function withQuery(path: string, params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") search.set(key, value);
  });
  const qs = search.toString();
  return qs ? `${path}?${qs}` : path;
}

export interface TableQueryArgs {
  workspaceId: UUID;
  itemType: string;
  filters?: TableFilters;
  sort?: TableSort;
  columns?: string[];
  page?: number;
  pageSize?: number;
}

export const tableApi = {
  query(args: TableQueryArgs): Promise<PaginatedResponse<TableRow>> {
    const hasFilters = args.filters && Object.keys(args.filters).length > 0;
    const hasSort = args.sort && args.sort.length > 0;
    return apiClient.get<PaginatedResponse<TableRow>>(
      withQuery("/artifacts/table/", {
        workspace_id: args.workspaceId,
        item_type: args.itemType,
        filters: hasFilters ? JSON.stringify(args.filters) : undefined,
        sort: hasSort ? JSON.stringify(args.sort) : undefined,
        columns: args.columns && args.columns.length > 0 ? args.columns.join(",") : undefined,
        page: args.page ? String(args.page) : undefined,
        page_size: args.pageSize ? String(args.pageSize) : undefined,
      }),
    );
  },

  bulkUpdate(args: {
    workspaceId: UUID;
    itemType: string;
    ids: UUID[];
    fields: Record<string, unknown>;
    changeReason?: string;
  }): Promise<BulkResult> {
    return apiClient.patch<BulkResult>("/artifacts/bulk-update/", {
      workspace_id: args.workspaceId,
      item_type: args.itemType,
      ids: args.ids,
      fields: args.fields,
      change_reason: args.changeReason ?? "",
    });
  },

  bulkTransition(args: {
    workspaceId: UUID;
    itemType: string;
    ids: UUID[];
    toState: string;
    changeReason?: string;
    credential?: string;
  }): Promise<BulkResult> {
    return apiClient.post<BulkResult>("/artifacts/bulk-transition/", {
      workspace_id: args.workspaceId,
      item_type: args.itemType,
      ids: args.ids,
      to_state: args.toState,
      change_reason: args.changeReason ?? "",
      credential: args.credential ?? "",
    });
  },
};

export const savedViewsApi = {
  list(workspaceId: UUID, itemType?: string): Promise<{ count: number; results: SavedView[] }> {
    return apiClient.get(
      withQuery("/saved-views/", { workspace_id: workspaceId, item_type: itemType }),
    );
  },

  create(input: {
    workspaceId: UUID;
    itemType: string;
    name: string;
    columns: ColumnSpec[];
    filters: TableFilters;
    sort: TableSort;
    visibility: "private" | "workspace";
  }): Promise<SavedView> {
    return apiClient.post<SavedView>("/saved-views/", {
      workspace_id: input.workspaceId,
      item_type: input.itemType,
      name: input.name,
      columns: input.columns,
      filters: input.filters,
      sort: input.sort,
      visibility: input.visibility,
    });
  },

  update(id: UUID, changes: Partial<Pick<SavedView, "name" | "columns" | "filters" | "sort" | "visibility">>): Promise<SavedView> {
    return apiClient.patch<SavedView>(`/saved-views/${id}/`, changes);
  },

  remove(id: UUID): Promise<void> {
    return apiClient.delete(`/saved-views/${id}/`);
  },

  apply(id: UUID): Promise<PaginatedResponse<TableRow>> {
    return apiClient.get<PaginatedResponse<TableRow>>(`/saved-views/${id}/apply/`);
  },
};

export const tableViewStateApi = {
  get(workspaceId: UUID, itemType: string): Promise<TableViewState> {
    return apiClient.get<TableViewState>(
      withQuery("/users/me/table-view-state/", {
        workspace_id: workspaceId,
        item_type: itemType,
      }),
    );
  },

  save(workspaceId: UUID, itemType: string, state: TableViewState): Promise<TableViewState> {
    return apiClient.put<TableViewState>("/users/me/table-view-state/", {
      workspace_id: workspaceId,
      item_type: itemType,
      columns: state.columns,
      filters: state.filters,
      sort: state.sort,
    });
  },
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `FT src/test/tableViewsApi.test.ts`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/table-views.ts frontend/src/test/tableViewsApi.test.ts
git commit -m "feat(table): add table view API wrapper"
```

---

## Task 16: Column model — attribute definition to columns and operators

**Files:**
- Create: `frontend/src/components/shared/ArtifactTable/columnModel.ts`
- Test: `frontend/src/test/tableColumnModel.test.ts`

**Interfaces:**
- Consumes: the resolved attribute definition of spec 2 (`{attributes: [...]}`)
- Produces: `AttributeDefinitionEntry`, `TableColumn`, `buildColumns(attributes, state)`, `operatorsForColumn(column)`, `isWorkflowOwned(attribute)`, `columnLabel(attribute, language)`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/tableColumnModel.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import {
  buildColumns,
  columnLabel,
  isWorkflowOwned,
  operatorsForColumn,
} from "../components/shared/ArtifactTable/columnModel";
import type { AttributeDefinitionEntry } from "../components/shared/ArtifactTable/columnModel";

const attributes: AttributeDefinitionEntry[] = [
  { name: "title", kind: "core", type: "text", editable: true, visible: true, order: 1,
    label: { de: "Titel", en: "Title" } },
  { name: "category", kind: "core", type: "enum", editable: true, visible: true, order: 2,
    options: [{ value: "safety", label_de: "Sicherheit", label_en: "Safety" }] },
  { name: "status", kind: "core", type: "enum", editable: "workflow", visible: true, order: 3, locked: true },
  { name: "internal", kind: "core", type: "text", editable: true, visible: false, order: 4 },
  { name: "matrix", kind: "core", type: "widget", editable: true, visible: true, order: 5 },
  { name: "extra", kind: "extended", type: "text", editable: true, visible: true, order: 6 },
];

describe("columnModel", () => {
  it("defaults to visible core attributes in definition order", () => {
    const columns = buildColumns(attributes, []);
    expect(columns.map((c) => c.field)).toEqual(["title", "category", "status", "matrix"]);
  });

  it("honours a stored column selection and its order", () => {
    const columns = buildColumns(attributes, [
      { field: "status", order: 0 },
      { field: "title", order: 1 },
    ]);
    expect(columns.map((c) => c.field)).toEqual(["status", "title"]);
  });

  it("drops a stored column whose attribute no longer exists", () => {
    const columns = buildColumns(attributes, [
      { field: "removed_field", order: 0 },
      { field: "title", order: 1 },
    ]);
    expect(columns.map((c) => c.field)).toEqual(["title"]);
  });

  it("marks the workflow-owned column so the grid can render it read-only", () => {
    const status = buildColumns(attributes, []).find((c) => c.field === "status");
    expect(status?.workflowOwned).toBe(true);
    expect(status?.editable).toBe(false);
  });

  it("mirrors the backend operator table", () => {
    const columns = buildColumns(attributes, []);
    const byField = Object.fromEntries(columns.map((c) => [c.field, c]));
    expect(operatorsForColumn(byField.title)).toEqual(["contains"]);
    expect(operatorsForColumn(byField.category)).toEqual(["in"]);
    expect(operatorsForColumn(byField.status)).toEqual(["in"]);
  });

  it("reports a widget column as unfilterable and unsortable", () => {
    const matrix = buildColumns(attributes, []).find((c) => c.field === "matrix");
    expect(operatorsForColumn(matrix!)).toEqual([]);
    expect(matrix?.sortable).toBe(false);
  });

  it("excludes extended attributes — v1 filters core only", () => {
    expect(buildColumns(attributes, []).some((c) => c.field === "extra")).toBe(false);
  });

  it("prefers the label override for the active language", () => {
    expect(columnLabel(attributes[0], "de")).toBe("Titel");
    expect(columnLabel(attributes[0], "en")).toBe("Title");
    expect(columnLabel(attributes[1], "de")).toBe("category");
  });

  it("detects workflow ownership regardless of type", () => {
    expect(isWorkflowOwned(attributes[2])).toBe(true);
    expect(isWorkflowOwned(attributes[0])).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `FT src/test/tableColumnModel.test.ts`
Expected: FAIL — `Failed to resolve import ".../ArtifactTable/columnModel"`

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/components/shared/ArtifactTable/columnModel.ts`:

```ts
/**
 * Derives table columns and their filter operators from the resolved
 * attribute definition (Attribut-Definition spec §3.1).
 *
 * The operator table is the mirror image of
 * `backend/application/table_filter_dsl.py:FILTER_OPERATORS_BY_TYPE`. Keeping
 * both in sync is deliberate duplication: the UI must decide which control to
 * offer before it can call the server, and the server must never trust that
 * decision. Any change to one side needs the same change on the other.
 */

import type { ColumnSpec, FilterOperator } from "../../../api/table-views";

export type AttributeType =
  | "text"
  | "textarea"
  | "number"
  | "boolean"
  | "enum"
  | "multi-enum"
  | "date"
  | "reference"
  | "user"
  | "widget";

export interface AttributeOption {
  value: string;
  label_de: string;
  label_en: string;
}

/** One entry of `definition_json.attributes[]` (Attribut-Definition spec §3.1). */
export interface AttributeDefinitionEntry {
  name: string;
  kind: "core" | "extended";
  type: AttributeType;
  options?: AttributeOption[];
  required?: boolean;
  visible?: boolean;
  locked?: boolean;
  editable?: boolean | "workflow";
  section?: string;
  order?: number;
  label?: { de: string; en: string };
  help_text?: { de: string; en: string };
}

export interface TableColumn {
  field: string;
  type: AttributeType;
  options: AttributeOption[];
  /** True only for `editable: "workflow"` — the grid renders these read-only. */
  workflowOwned: boolean;
  /** Inline-editable: never true for a workflow-owned or `editable: false` field. */
  editable: boolean;
  sortable: boolean;
  attribute: AttributeDefinitionEntry;
}

const OPERATORS_BY_TYPE: Record<AttributeType, FilterOperator[]> = {
  text: ["contains"],
  textarea: ["contains"],
  enum: ["in"],
  "multi-enum": ["in"],
  number: ["gte", "lte"],
  date: ["gte", "lte"],
  boolean: ["eq"],
  reference: ["in"],
  user: ["in"],
  widget: [],
};

export function isWorkflowOwned(attribute: AttributeDefinitionEntry): boolean {
  return attribute.editable === "workflow";
}

export function columnLabel(
  attribute: AttributeDefinitionEntry,
  language: string,
): string {
  const override = attribute.label;
  if (!override) return attribute.name;
  return (language.startsWith("de") ? override.de : override.en) || attribute.name;
}

function toColumn(attribute: AttributeDefinitionEntry): TableColumn {
  const workflowOwned = isWorkflowOwned(attribute);
  return {
    field: attribute.name,
    type: attribute.type,
    options: attribute.options ?? [],
    workflowOwned,
    editable: !workflowOwned && attribute.editable !== false && attribute.type !== "widget",
    sortable: attribute.type !== "widget",
    attribute,
  };
}

/**
 * Build the column list. `selection` is the user's stored column choice
 * (`UserTableViewState.columns` or a SavedView's); an empty selection falls
 * back to every visible core attribute in definition order. A stored column
 * whose attribute has since disappeared is dropped silently — a stale saved
 * view degrades, it does not error (spec §6).
 */
export function buildColumns(
  attributes: AttributeDefinitionEntry[],
  selection: ColumnSpec[],
): TableColumn[] {
  const core = attributes.filter((a) => a.kind === "core");
  if (selection.length === 0) {
    return core
      .filter((a) => a.visible !== false)
      .slice()
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
      .map(toColumn);
  }
  const byName = new Map(core.map((a) => [a.name, a]));
  return selection
    .slice()
    .sort((a, b) => a.order - b.order)
    .map((spec) => byName.get(spec.field))
    .filter((a): a is AttributeDefinitionEntry => a !== undefined)
    .map(toColumn);
}

export function operatorsForColumn(column: TableColumn): FilterOperator[] {
  if (column.workflowOwned) return ["in"];
  return OPERATORS_BY_TYPE[column.type] ?? [];
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `FT src/test/tableColumnModel.test.ts`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shared/ArtifactTable/columnModel.ts frontend/src/test/tableColumnModel.test.ts
git commit -m "feat(table): derive table columns and operators from the attribute definition"
```

---

## Task 17: ArtifactTable grid — rendering, sorting, read-only status cell

**Files:**
- Create: `frontend/src/components/shared/ArtifactTable/ArtifactTable.tsx`, `frontend/src/components/shared/ArtifactTable/ArtifactTable.module.css`, `frontend/src/components/shared/ArtifactTable/index.ts`
- Test: `frontend/src/test/ArtifactTable.test.tsx`

**Interfaces:**
- Consumes: `TableColumn`, `columnLabel` (Task 16), `TableRow`, `TableSort` (Task 15), `components/shared/StatusBadge`
- Produces: `ArtifactTable`, `ArtifactTableProps`, `toggleSort(sort, field, additive) -> TableSort`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/ArtifactTable.test.tsx`:

```tsx
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ArtifactTable, toggleSort } from "../components/shared/ArtifactTable";
import { buildColumns } from "../components/shared/ArtifactTable/columnModel";
import type { AttributeDefinitionEntry } from "../components/shared/ArtifactTable/columnModel";
import type { TableRow } from "../api/table-views";

const attributes: AttributeDefinitionEntry[] = [
  { name: "title", kind: "core", type: "text", editable: true, visible: true, order: 1 },
  { name: "category", kind: "core", type: "enum", editable: true, visible: true, order: 2,
    options: [{ value: "safety", label_de: "Sicherheit", label_en: "Safety" }] },
  { name: "status", kind: "core", type: "enum", editable: "workflow", visible: true, order: 3 },
];

const rows: TableRow[] = [
  { id: "r1", artifact_id: "a1", title: "Brake force", category: "safety", status: "draft" },
  { id: "r2", artifact_id: "a2", title: "Cabin light", category: "functional", status: "approved" },
];

function renderTable(overrides: Partial<React.ComponentProps<typeof ArtifactTable>> = {}) {
  const props = {
    itemType: "Requirement",
    columns: buildColumns(attributes, []),
    rows,
    sort: [],
    onSortChange: vi.fn(),
    selectedIds: [] as string[],
    onSelectionChange: vi.fn(),
    onOpenTransition: vi.fn(),
    onInlineSave: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  return { props, ...render(<ArtifactTable {...props} />) };
}

describe("ArtifactTable", () => {
  it("renders one header per column and one row per record", () => {
    renderTable();
    expect(screen.getByTestId("artifact-table-header-title")).toBeInTheDocument();
    expect(screen.getByTestId("artifact-table-header-status")).toBeInTheDocument();
    expect(screen.getByTestId("artifact-table-row-r1")).toBeInTheDocument();
    expect(screen.getByTestId("artifact-table-row-r2")).toBeInTheDocument();
  });

  it("renders the status cell as a read-only badge with a separate transition action", () => {
    renderTable();
    const cell = screen.getByTestId("artifact-table-cell-r1-status");
    expect(within(cell).queryByRole("textbox")).toBeNull();
    expect(within(cell).queryByRole("combobox")).toBeNull();
    expect(screen.getByTestId("artifact-table-transition-r1")).toBeInTheDocument();
  });

  it("never enters inline edit mode on a workflow-owned cell", () => {
    renderTable();
    fireEvent.click(screen.getByTestId("artifact-table-cell-r1-status"));
    expect(screen.queryByTestId("artifact-table-editor-r1-status")).toBeNull();
  });

  it("opens the transition dialog from the status action", () => {
    const { props } = renderTable();
    fireEvent.click(screen.getByTestId("artifact-table-transition-r1"));
    expect(props.onOpenTransition).toHaveBeenCalledWith("r1");
  });

  it("sorts ascending on a header click and toggles to descending on a second", () => {
    const { props } = renderTable({ sort: [] });
    fireEvent.click(screen.getByTestId("artifact-table-header-title"));
    expect(props.onSortChange).toHaveBeenCalledWith([{ field: "title", dir: "asc" }]);
  });

  it("adds a secondary sort on shift-click", () => {
    const { props } = renderTable({ sort: [{ field: "category", dir: "asc" }] });
    fireEvent.click(screen.getByTestId("artifact-table-header-title"), { shiftKey: true });
    expect(props.onSortChange).toHaveBeenCalledWith([
      { field: "category", dir: "asc" },
      { field: "title", dir: "asc" },
    ]);
  });

  it("does not sort on a non-sortable header", () => {
    const widgetAttrs: AttributeDefinitionEntry[] = [
      { name: "matrix", kind: "core", type: "widget", editable: true, visible: true, order: 1 },
    ];
    const { props } = renderTable({ columns: buildColumns(widgetAttrs, []) });
    fireEvent.click(screen.getByTestId("artifact-table-header-matrix"));
    expect(props.onSortChange).not.toHaveBeenCalled();
  });

  it("selects rows through the checkbox column", () => {
    const { props } = renderTable();
    fireEvent.click(screen.getByTestId("artifact-table-select-r1"));
    expect(props.onSelectionChange).toHaveBeenCalledWith(["r1"]);
  });

  it("select-all picks up every visible row", () => {
    const { props } = renderTable();
    fireEvent.click(screen.getByTestId("artifact-table-select-all"));
    expect(props.onSelectionChange).toHaveBeenCalledWith(["r1", "r2"]);
  });
});

describe("toggleSort", () => {
  it("replaces the sort on a plain click", () => {
    expect(toggleSort([{ field: "a", dir: "asc" }], "b", false)).toEqual([
      { field: "b", dir: "asc" },
    ]);
  });

  it("flips the direction when the same field is clicked again", () => {
    expect(toggleSort([{ field: "a", dir: "asc" }], "a", false)).toEqual([
      { field: "a", dir: "desc" },
    ]);
  });

  it("appends on shift-click and flips an existing term in place", () => {
    expect(toggleSort([{ field: "a", dir: "asc" }], "b", true)).toEqual([
      { field: "a", dir: "asc" },
      { field: "b", dir: "asc" },
    ]);
    expect(toggleSort([{ field: "a", dir: "asc" }, { field: "b", dir: "asc" }], "a", true)).toEqual([
      { field: "a", dir: "desc" },
      { field: "b", dir: "asc" },
    ]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `FT src/test/ArtifactTable.test.tsx`
Expected: FAIL — `Failed to resolve import "../components/shared/ArtifactTable"`

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/components/shared/ArtifactTable/ArtifactTable.module.css` (every value from `styles/tokens.css` — the ratchet forbids new inline styles and hex literals):

```css
/*
 * <ArtifactTable> — Tabellenansicht spec §4.3. The status column is visually
 * separated from the editable ones on purpose: the §2 guardrail has to be
 * visible, not just enforced server-side.
 */

.wrapper {
  overflow: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
}

.table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.headerCell {
  position: sticky;
  top: 0;
  z-index: 1;
  text-align: left;
  padding: var(--space-2) var(--space-3);
  background: var(--color-surface-alt);
  color: var(--color-text);
  border-bottom: 1px solid var(--color-border);
  white-space: nowrap;
}

.sortable {
  cursor: pointer;
  user-select: none;
}

.sortIndicator {
  margin-left: var(--space-1);
  color: var(--color-text-muted);
}

.row {
  border-bottom: 1px solid var(--color-border);
}

.row:hover {
  background: var(--color-surface-hover);
}

.cell {
  padding: var(--space-2) var(--space-3);
  color: var(--color-text);
  vertical-align: middle;
}

.editableCell {
  cursor: text;
}

/* Read-only by contract — never gets the edit affordance. */
.workflowCell {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  cursor: default;
}

.selectCell {
  width: var(--space-6);
  padding: var(--space-2) var(--space-3);
}

.empty {
  padding: var(--space-4);
  text-align: center;
  color: var(--color-text-muted);
}
```

Confirm the token names used above exist in `frontend/src/styles/tokens.css`
(`grep -n "surface-alt\|surface-hover\|--space-6" frontend/src/styles/tokens.css`) and substitute the
nearest existing token if one is missing — `src/test/design-tokens.test.ts` fails on an undefined
custom property.

Create `frontend/src/components/shared/ArtifactTable/ArtifactTable.tsx`:

```tsx
/**
 * <ArtifactTable> — the grid of the Tabellenansicht (spec §4.3).
 *
 * Guardrail (spec §2): a column with `workflowOwned === true` renders a
 * read-only <StatusBadge> plus a separate "change status" action that opens
 * the transition dialog. It never becomes an editable cell, so the boundary
 * is visible in the UI and not only enforced on the server.
 *
 * Column filter popovers, the column picker, saved views and the bulk action
 * bar are separate components mounted around this one by the host page.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { StatusBadge } from "../StatusBadge";
import { columnLabel } from "./columnModel";
import type { TableColumn } from "./columnModel";
import type { TableRow, TableSort } from "../../../api/table-views";
import styles from "./ArtifactTable.module.css";

export interface ArtifactTableProps {
  itemType: string;
  columns: TableColumn[];
  rows: TableRow[];
  sort: TableSort;
  onSortChange: (sort: TableSort) => void;
  selectedIds: string[];
  onSelectionChange: (ids: string[]) => void;
  /** Opens the workflow transition dialog for one row. */
  onOpenTransition: (rowId: string) => void;
  /** Single-item update path — deliberately NOT the bulk endpoint (spec §4.3). */
  onInlineSave: (rowId: string, field: string, value: unknown) => Promise<void>;
  /** Rendered inside the header cell, next to the label (filter trigger). */
  renderHeaderFilter?: (column: TableColumn) => React.ReactNode;
  /** Rendered instead of the plain value when a cell is in edit mode. */
  renderCellEditor?: (
    column: TableColumn,
    row: TableRow,
    done: () => void,
  ) => React.ReactNode;
  loading?: boolean;
}

/**
 * Next sort state for a header click.
 * Plain click replaces the sort (or flips the direction of the same field);
 * shift-click appends a secondary term, or flips an existing one in place.
 */
export function toggleSort(
  sort: TableSort,
  field: string,
  additive: boolean,
): TableSort {
  const existing = sort.find((term) => term.field === field);
  const flipped = { field, dir: existing?.dir === "asc" ? ("desc" as const) : ("asc" as const) };
  if (!additive) return [flipped];
  if (!existing) return [...sort, { field, dir: "asc" as const }];
  return sort.map((term) => (term.field === field ? flipped : term));
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "boolean") return value ? "✓" : "";
  return String(value);
}

export function ArtifactTable({
  itemType,
  columns,
  rows,
  sort,
  onSortChange,
  selectedIds,
  onSelectionChange,
  onOpenTransition,
  onInlineSave,
  renderHeaderFilter,
  renderCellEditor,
  loading = false,
}: ArtifactTableProps): JSX.Element {
  const { t, i18n } = useTranslation();
  const [editing, setEditing] = useState<{ rowId: string; field: string } | null>(null);

  const allSelected = rows.length > 0 && selectedIds.length === rows.length;

  const toggleRow = (rowId: string): void => {
    onSelectionChange(
      selectedIds.includes(rowId)
        ? selectedIds.filter((id) => id !== rowId)
        : [...selectedIds, rowId],
    );
  };

  return (
    <div className={styles.wrapper} data-testid={`artifact-table-${itemType}`}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th className={styles.headerCell}>
              <input
                type="checkbox"
                data-testid="artifact-table-select-all"
                aria-label={t("table.selectAll", "Select all rows")}
                checked={allSelected}
                onChange={() => onSelectionChange(allSelected ? [] : rows.map((r) => r.id))}
              />
            </th>
            {columns.map((column) => {
              const term = sort.find((s) => s.field === column.field);
              return (
                <th
                  key={column.field}
                  data-testid={`artifact-table-header-${column.field}`}
                  className={`${styles.headerCell} ${column.sortable ? styles.sortable : ""}`}
                  aria-sort={term ? (term.dir === "asc" ? "ascending" : "descending") : "none"}
                  onClick={(event) => {
                    if (!column.sortable) return;
                    onSortChange(toggleSort(sort, column.field, event.shiftKey));
                  }}
                >
                  {columnLabel(column.attribute, i18n.language)}
                  {term && (
                    <span className={styles.sortIndicator} aria-hidden="true">
                      {term.dir === "asc" ? "▲" : "▼"}
                    </span>
                  )}
                  {renderHeaderFilter?.(column)}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id}
              className={styles.row}
              data-testid={`artifact-table-row-${row.id}`}
            >
              <td className={styles.selectCell}>
                <input
                  type="checkbox"
                  data-testid={`artifact-table-select-${row.id}`}
                  aria-label={t("table.selectRow", "Select row")}
                  checked={selectedIds.includes(row.id)}
                  onChange={() => toggleRow(row.id)}
                />
              </td>
              {columns.map((column) => {
                const isEditing =
                  editing?.rowId === row.id && editing.field === column.field;
                return (
                  <td
                    key={column.field}
                    data-testid={`artifact-table-cell-${row.id}-${column.field}`}
                    className={`${styles.cell} ${column.editable ? styles.editableCell : ""}`}
                    onClick={() => {
                      // Guardrail: a workflow-owned or read-only cell never
                      // enters edit mode, whatever the click.
                      if (!column.editable) return;
                      setEditing({ rowId: row.id, field: column.field });
                    }}
                  >
                    {column.workflowOwned ? (
                      <span className={styles.workflowCell}>
                        <StatusBadge status={formatValue(row[column.field])} />
                        <button
                          type="button"
                          data-testid={`artifact-table-transition-${row.id}`}
                          aria-label={t("table.changeStatus", "Change status")}
                          title={t("table.changeStatus", "Change status")}
                          onClick={(event) => {
                            event.stopPropagation();
                            onOpenTransition(row.id);
                          }}
                        >
                          ⇄
                        </button>
                      </span>
                    ) : isEditing && renderCellEditor ? (
                      renderCellEditor(column, row, () => setEditing(null))
                    ) : (
                      formatValue(row[column.field])
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {!loading && rows.length === 0 && (
        <p className={styles.empty} data-testid="artifact-table-empty">
          {t("table.noRows", "No matching artifacts")}
        </p>
      )}
    </div>
  );
}
```

Note `onInlineSave` is threaded through to the editor in Task 22; keep the prop in the
signature now so the contract does not change later.

Create `frontend/src/components/shared/ArtifactTable/index.ts`:

```ts
export { ArtifactTable, toggleSort } from "./ArtifactTable";
export type { ArtifactTableProps } from "./ArtifactTable";
export { buildColumns, columnLabel, isWorkflowOwned, operatorsForColumn } from "./columnModel";
export type { AttributeDefinitionEntry, TableColumn } from "./columnModel";
```

Confirm `StatusBadge`'s prop name before running:
`grep -n "export function StatusBadge" -A 8 frontend/src/components/shared/StatusBadge.tsx` — adapt
the call if it takes something other than `status`.

- [ ] **Step 4: Run test to verify it passes**

Run: `FT src/test/ArtifactTable.test.tsx src/test/ui-ratchet.test.ts --testTimeout=30000`
Expected: PASS (12 passed) — including the ratchet, which requires zero new `style={{` in the new files.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shared/ArtifactTable/ frontend/src/test/ArtifactTable.test.tsx
git commit -m "feat(table): add artifact table grid with read-only status cells"
```

---

## Task 18: Column filter popover and active filter chips

**Files:**
- Create: `frontend/src/components/shared/ArtifactTable/fieldComponents.ts`, `frontend/src/components/shared/ArtifactTable/ColumnFilterPopover.tsx`, `frontend/src/components/shared/ArtifactTable/ColumnFilterPopover.module.css`, `frontend/src/components/shared/ArtifactTable/ActiveFilterChips.tsx`
- Modify: `frontend/src/components/shared/ArtifactTable/index.ts`
- Test: `frontend/src/test/ArtifactTableFilters.test.tsx`

**Interfaces:**
- Consumes: `operatorsForColumn`, `TableColumn` (Task 16); the ArtifactForm field library of spec 2 through `fieldComponents.ts`
- Produces: `ColumnFilterPopover`, `ActiveFilterChips`, `constraintsFor(filters, field)`, `withConstraints(filters, field, constraints)`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/ArtifactTableFilters.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  ActiveFilterChips,
  ColumnFilterPopover,
  constraintsFor,
  withConstraints,
} from "../components/shared/ArtifactTable";
import { buildColumns } from "../components/shared/ArtifactTable/columnModel";
import type { AttributeDefinitionEntry } from "../components/shared/ArtifactTable/columnModel";
import type { TableFilters } from "../api/table-views";

const attributes: AttributeDefinitionEntry[] = [
  { name: "title", kind: "core", type: "text", editable: true, visible: true, order: 1 },
  { name: "category", kind: "core", type: "enum", editable: true, visible: true, order: 2,
    options: [
      { value: "safety", label_de: "Sicherheit", label_en: "Safety" },
      { value: "functional", label_de: "Funktional", label_en: "Functional" },
    ] },
  { name: "created_at", kind: "core", type: "date", editable: false, visible: true, order: 3 },
  { name: "matrix", kind: "core", type: "widget", editable: true, visible: true, order: 4 },
];
const columns = buildColumns(attributes, []);
const byField = Object.fromEntries(columns.map((c) => [c.field, c]));

describe("filter helpers", () => {
  it("normalises a single constraint into a list", () => {
    const filters: TableFilters = { title: { op: "contains", value: "brake" } };
    expect(constraintsFor(filters, "title")).toEqual([{ op: "contains", value: "brake" }]);
    expect(constraintsFor(filters, "missing")).toEqual([]);
  });

  it("stores one constraint plainly and several as a list", () => {
    expect(withConstraints({}, "title", [{ op: "contains", value: "x" }])).toEqual({
      title: { op: "contains", value: "x" },
    });
    expect(
      withConstraints({}, "created_at", [
        { op: "gte", value: "2026-01-01" },
        { op: "lte", value: "2026-02-01" },
      ]),
    ).toEqual({
      created_at: [
        { op: "gte", value: "2026-01-01" },
        { op: "lte", value: "2026-02-01" },
      ],
    });
  });

  it("removes the key when the constraint list is empty", () => {
    expect(withConstraints({ title: { op: "contains", value: "x" } }, "title", [])).toEqual({});
  });
});

describe("ColumnFilterPopover", () => {
  it("offers a text input for a text column", () => {
    render(
      <ColumnFilterPopover column={byField.title} filters={{}} onChange={vi.fn()} />,
    );
    fireEvent.click(screen.getByTestId("artifact-table-filter-trigger-title"));
    expect(screen.getByTestId("artifact-table-filter-text-title")).toBeInTheDocument();
  });

  it("offers one checkbox per option for an enum column and emits an in-constraint", () => {
    const onChange = vi.fn();
    render(
      <ColumnFilterPopover column={byField.category} filters={{}} onChange={onChange} />,
    );
    fireEvent.click(screen.getByTestId("artifact-table-filter-trigger-category"));
    fireEvent.click(screen.getByTestId("artifact-table-filter-option-category-safety"));
    expect(onChange).toHaveBeenCalledWith({
      category: { op: "in", value: ["safety"] },
    });
  });

  it("offers a from/to pair for a date column", () => {
    render(
      <ColumnFilterPopover column={byField.created_at} filters={{}} onChange={vi.fn()} />,
    );
    fireEvent.click(screen.getByTestId("artifact-table-filter-trigger-created_at"));
    expect(screen.getByTestId("artifact-table-filter-gte-created_at")).toBeInTheDocument();
    expect(screen.getByTestId("artifact-table-filter-lte-created_at")).toBeInTheDocument();
  });

  it("renders no trigger at all for an unfilterable column", () => {
    render(<ColumnFilterPopover column={byField.matrix} filters={{}} onChange={vi.fn()} />);
    expect(screen.queryByTestId("artifact-table-filter-trigger-matrix")).toBeNull();
  });
});

describe("ActiveFilterChips", () => {
  it("renders one removable chip per active constraint", () => {
    const onChange = vi.fn();
    render(
      <ActiveFilterChips
        columns={columns}
        filters={{
          title: { op: "contains", value: "brake" },
          category: { op: "in", value: ["safety"] },
        }}
        onChange={onChange}
      />,
    );
    expect(screen.getByTestId("artifact-table-chip-title-0")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("artifact-table-chip-remove-category-0"));
    expect(onChange).toHaveBeenCalledWith({ title: { op: "contains", value: "brake" } });
  });

  it("renders nothing when no filter is active", () => {
    const { container } = render(
      <ActiveFilterChips columns={columns} filters={{}} onChange={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `FT src/test/ArtifactTableFilters.test.tsx`
Expected: FAIL — `ColumnFilterPopover` is not exported from the ArtifactTable index.

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/components/shared/ArtifactTable/fieldComponents.ts` — the single seam onto spec 2's field library, so a naming drift there costs one file:

```ts
/**
 * Single seam onto the ArtifactForm field-component library of the
 * Attribut-Definition spec (§6). The table reuses those components for column
 * filters and inline edit rather than building a second UI system (spec §4.3).
 *
 * If that spec's plan exports different names, only this file changes.
 */
export {
  BooleanToggle,
  DateField,
  EnumSelect,
  MultiEnum,
  ReferencePicker,
  TextField,
  UserPicker,
} from "../ArtifactForm/fields";
```

Create `frontend/src/components/shared/ArtifactTable/ColumnFilterPopover.module.css`:

```css
/* Column filter popover + active-filter chips — Tabellenansicht spec §4.3. */

.trigger {
  margin-left: var(--space-1);
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
}

.triggerActive {
  color: var(--color-primary);
}

.popover {
  position: absolute;
  z-index: 2;
  min-width: 200px;
  margin-top: var(--space-1);
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  box-shadow: var(--shadow-md);
}

.option {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) 0;
  font-size: var(--font-size-sm);
}

.chipRow {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  background: var(--color-surface-alt);
  font-size: var(--font-size-xs);
}

.chipRemove {
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
}
```

Create `frontend/src/components/shared/ArtifactTable/ColumnFilterPopover.tsx`:

```tsx
/**
 * Type-aware column filter (Tabellenansicht spec §4.3): the popover offers
 * exactly the operators the column's type allows, mirroring
 * `operatorsForColumn`. A column with no operators (widget) renders no
 * trigger at all rather than an empty popover.
 *
 * Status is filterable here on purpose — filtering is a read and does not
 * touch the §2 write guardrail.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { columnLabel, operatorsForColumn } from "./columnModel";
import type { TableColumn } from "./columnModel";
import type { FilterConstraint, TableFilters } from "../../../api/table-views";
import styles from "./ColumnFilterPopover.module.css";

/** Constraints for one field, always as a list. */
export function constraintsFor(filters: TableFilters, field: string): FilterConstraint[] {
  const raw = filters[field];
  if (raw === undefined) return [];
  return Array.isArray(raw) ? raw : [raw];
}

/** Replace one field's constraints; an empty list removes the key entirely. */
export function withConstraints(
  filters: TableFilters,
  field: string,
  constraints: FilterConstraint[],
): TableFilters {
  const next: TableFilters = { ...filters };
  if (constraints.length === 0) delete next[field];
  else if (constraints.length === 1) next[field] = constraints[0];
  else next[field] = constraints;
  return next;
}

export interface ColumnFilterPopoverProps {
  column: TableColumn;
  filters: TableFilters;
  onChange: (filters: TableFilters) => void;
}

export function ColumnFilterPopover({
  column,
  filters,
  onChange,
}: ColumnFilterPopoverProps): JSX.Element | null {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const operators = operatorsForColumn(column);
  if (operators.length === 0) return null;

  const current = constraintsFor(filters, column.field);
  const valueFor = (op: string): FilterConstraint["value"] | undefined =>
    current.find((c) => c.op === op)?.value;

  const setSingle = (op: FilterConstraint["op"], value: FilterConstraint["value"]): void => {
    const rest = current.filter((c) => c.op !== op);
    const keep = value === "" || (Array.isArray(value) && value.length === 0);
    onChange(
      withConstraints(
        filters,
        column.field,
        keep ? rest : [...rest, { op, value }],
      ),
    );
  };

  const selected = (valueFor("in") as string[] | undefined) ?? [];
  const label = columnLabel(column.attribute, i18n.language);

  return (
    <>
      <button
        type="button"
        data-testid={`artifact-table-filter-trigger-${column.field}`}
        aria-label={t("table.filterColumn", "Filter {{column}}", { column: label })}
        className={`${styles.trigger} ${current.length > 0 ? styles.triggerActive : ""}`}
        aria-expanded={open}
        onClick={(event) => {
          event.stopPropagation();
          setOpen((value) => !value);
        }}
      >
        ⌄
      </button>
      {open && (
        <div
          className={styles.popover}
          data-testid={`artifact-table-filter-popover-${column.field}`}
          onClick={(event) => event.stopPropagation()}
        >
          {operators.includes("contains") && (
            <input
              type="search"
              data-testid={`artifact-table-filter-text-${column.field}`}
              aria-label={label}
              value={(valueFor("contains") as string) ?? ""}
              onChange={(event) => setSingle("contains", event.target.value)}
            />
          )}

          {operators.includes("in") &&
            (column.options.length > 0 ? (
              column.options.map((option) => (
                <label key={option.value} className={styles.option}>
                  <input
                    type="checkbox"
                    data-testid={`artifact-table-filter-option-${column.field}-${option.value}`}
                    checked={selected.includes(option.value)}
                    onChange={() =>
                      setSingle(
                        "in",
                        selected.includes(option.value)
                          ? selected.filter((v) => v !== option.value)
                          : [...selected, option.value],
                      )
                    }
                  />
                  {i18n.language.startsWith("de") ? option.label_de : option.label_en}
                </label>
              ))
            ) : (
              // reference/user columns, and any enum whose options the
              // definition does not enumerate: comma-separated ids.
              <input
                type="text"
                data-testid={`artifact-table-filter-in-${column.field}`}
                aria-label={label}
                value={selected.join(",")}
                onChange={(event) =>
                  setSingle(
                    "in",
                    event.target.value.split(",").map((v) => v.trim()).filter(Boolean),
                  )
                }
              />
            ))}

          {operators.includes("gte") && (
            <input
              type={column.type === "date" ? "date" : "number"}
              data-testid={`artifact-table-filter-gte-${column.field}`}
              aria-label={t("table.filterFrom", "From")}
              value={(valueFor("gte") as string) ?? ""}
              onChange={(event) => setSingle("gte", event.target.value)}
            />
          )}
          {operators.includes("lte") && (
            <input
              type={column.type === "date" ? "date" : "number"}
              data-testid={`artifact-table-filter-lte-${column.field}`}
              aria-label={t("table.filterTo", "To")}
              value={(valueFor("lte") as string) ?? ""}
              onChange={(event) => setSingle("lte", event.target.value)}
            />
          )}
          {operators.includes("eq") && (
            <select
              data-testid={`artifact-table-filter-eq-${column.field}`}
              aria-label={label}
              value={String(valueFor("eq") ?? "")}
              onChange={(event) =>
                setSingle("eq", event.target.value === "" ? "" : event.target.value === "true")
              }
            >
              <option value="">{t("table.filterAll", "All")}</option>
              <option value="true">{t("table.filterYes", "Yes")}</option>
              <option value="false">{t("table.filterNo", "No")}</option>
            </select>
          )}
        </div>
      )}
    </>
  );
}
```

`<input type="date">` and `<input type="number">` are the native controls for these
operators; the ArtifactForm library (`fieldComponents.ts`) is used for *inline edit*
(Task 22), where the full field semantics matter. Filters need a range pair, not a
single-value field component.

Create `frontend/src/components/shared/ArtifactTable/ActiveFilterChips.tsx`:

```tsx
/**
 * Active filters as removable chips above the table (spec §4.3) — a filter
 * that is set must always be visible and individually removable, never only
 * discoverable by reopening every column popover.
 */
import { useTranslation } from "react-i18next";
import { constraintsFor, withConstraints } from "./ColumnFilterPopover";
import { columnLabel } from "./columnModel";
import type { TableColumn } from "./columnModel";
import type { FilterConstraint, TableFilters } from "../../../api/table-views";
import styles from "./ColumnFilterPopover.module.css";

export interface ActiveFilterChipsProps {
  columns: TableColumn[];
  filters: TableFilters;
  onChange: (filters: TableFilters) => void;
}

function describe(constraint: FilterConstraint): string {
  const value = Array.isArray(constraint.value)
    ? constraint.value.join(", ")
    : String(constraint.value);
  return `${constraint.op}: ${value}`;
}

export function ActiveFilterChips({
  columns,
  filters,
  onChange,
}: ActiveFilterChipsProps): JSX.Element | null {
  const { t, i18n } = useTranslation();
  const active = columns
    .map((column) => ({ column, constraints: constraintsFor(filters, column.field) }))
    .filter((entry) => entry.constraints.length > 0);
  if (active.length === 0) return null;

  return (
    <div className={styles.chipRow} data-testid="artifact-table-chips">
      {active.map(({ column, constraints }) =>
        constraints.map((constraint, index) => (
          <span
            key={`${column.field}-${index}`}
            className={styles.chip}
            data-testid={`artifact-table-chip-${column.field}-${index}`}
          >
            {columnLabel(column.attribute, i18n.language)} · {describe(constraint)}
            <button
              type="button"
              className={styles.chipRemove}
              data-testid={`artifact-table-chip-remove-${column.field}-${index}`}
              aria-label={t("table.removeFilter", "Remove filter")}
              onClick={() =>
                onChange(
                  withConstraints(
                    filters,
                    column.field,
                    constraints.filter((_, i) => i !== index),
                  ),
                )
              }
            >
              ×
            </button>
          </span>
        )),
      )}
    </div>
  );
}
```

Append to `frontend/src/components/shared/ArtifactTable/index.ts`:

```ts
export { ActiveFilterChips } from "./ActiveFilterChips";
export { ColumnFilterPopover, constraintsFor, withConstraints } from "./ColumnFilterPopover";
export type { ColumnFilterPopoverProps } from "./ColumnFilterPopover";
export type { ActiveFilterChipsProps } from "./ActiveFilterChips";
```

- [ ] **Step 4: Run test to verify it passes**

Run: `FT src/test/ArtifactTableFilters.test.tsx src/test/ui-ratchet.test.ts --testTimeout=30000`
Expected: PASS (9 passed + ratchet)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shared/ArtifactTable/ frontend/src/test/ArtifactTableFilters.test.tsx
git commit -m "feat(table): add type-aware column filters and active filter chips"
```

---

## Task 19: Column picker and auto-persisted view state

**Files:**
- Create: `frontend/src/components/shared/ArtifactTable/ColumnPicker.tsx`, `frontend/src/components/shared/ArtifactTable/useTableViewState.ts`
- Modify: `frontend/src/components/shared/ArtifactTable/ColumnFilterPopover.module.css` (add `.pickerRow`), `frontend/src/components/shared/ArtifactTable/index.ts`
- Test: `frontend/src/test/ArtifactTableColumnPicker.test.tsx`

**Interfaces:**
- Consumes: `tableViewStateApi` (Task 15), `AttributeDefinitionEntry` (Task 16)
- Produces: `ColumnPicker`, `useTableViewState(workspaceId, itemType) -> {state, setState, ready}`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/ArtifactTableColumnPicker.test.tsx`:

```tsx
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ColumnPicker } from "../components/shared/ArtifactTable";
import { useTableViewState } from "../components/shared/ArtifactTable/useTableViewState";
import { tableViewStateApi } from "../api/table-views";
import type { AttributeDefinitionEntry } from "../components/shared/ArtifactTable/columnModel";

const attributes: AttributeDefinitionEntry[] = [
  { name: "title", kind: "core", type: "text", editable: true, visible: true, order: 1 },
  { name: "category", kind: "core", type: "enum", editable: true, visible: true, order: 2 },
  { name: "status", kind: "core", type: "enum", editable: "workflow", visible: true, order: 3 },
];

describe("ColumnPicker", () => {
  it("lists every core attribute with its current checked state", () => {
    render(
      <ColumnPicker
        attributes={attributes}
        selection={[{ field: "title", order: 0 }]}
        onChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("artifact-table-column-picker-trigger"));
    expect(screen.getByTestId("artifact-table-column-toggle-title")).toBeChecked();
    expect(screen.getByTestId("artifact-table-column-toggle-category")).not.toBeChecked();
  });

  it("appends a newly checked column at the end of the order", () => {
    const onChange = vi.fn();
    render(
      <ColumnPicker
        attributes={attributes}
        selection={[{ field: "title", order: 0 }]}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByTestId("artifact-table-column-picker-trigger"));
    fireEvent.click(screen.getByTestId("artifact-table-column-toggle-category"));
    expect(onChange).toHaveBeenCalledWith([
      { field: "title", order: 0 },
      { field: "category", order: 1 },
    ]);
  });

  it("renumbers the order after a column is removed", () => {
    const onChange = vi.fn();
    render(
      <ColumnPicker
        attributes={attributes}
        selection={[
          { field: "title", order: 0 },
          { field: "category", order: 1 },
          { field: "status", order: 2 },
        ]}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByTestId("artifact-table-column-picker-trigger"));
    fireEvent.click(screen.getByTestId("artifact-table-column-toggle-category"));
    expect(onChange).toHaveBeenCalledWith([
      { field: "title", order: 0 },
      { field: "status", order: 1 },
    ]);
  });

  it("moves a column up", () => {
    const onChange = vi.fn();
    render(
      <ColumnPicker
        attributes={attributes}
        selection={[
          { field: "title", order: 0 },
          { field: "category", order: 1 },
        ]}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByTestId("artifact-table-column-picker-trigger"));
    fireEvent.click(screen.getByTestId("artifact-table-column-up-category"));
    expect(onChange).toHaveBeenCalledWith([
      { field: "category", order: 0 },
      { field: "title", order: 1 },
    ]);
  });
});

describe("useTableViewState", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("loads the stored state once and reports ready", async () => {
    const get = vi.spyOn(tableViewStateApi, "get").mockResolvedValue({
      columns: [{ field: "title", order: 0 }],
      filters: {},
      sort: [],
    });
    const { result } = renderHook(() => useTableViewState("ws-1", "Requirement"));
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.state.columns).toEqual([{ field: "title", order: 0 }]);
    expect(get).toHaveBeenCalledTimes(1);
  });

  it("persists a change without an explicit save click", async () => {
    vi.spyOn(tableViewStateApi, "get").mockResolvedValue({
      columns: [],
      filters: {},
      sort: [],
    });
    const save = vi.spyOn(tableViewStateApi, "save").mockResolvedValue({
      columns: [],
      filters: {},
      sort: [],
    });
    const { result } = renderHook(() => useTableViewState("ws-1", "Requirement"));
    await waitFor(() => expect(result.current.ready).toBe(true));

    act(() => {
      result.current.setState({
        columns: [{ field: "status", order: 0 }],
        filters: {},
        sort: [],
      });
    });

    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save.mock.calls[0][2].columns).toEqual([{ field: "status", order: 0 }]);
  });

  it("falls back to empty state when loading fails", async () => {
    vi.spyOn(tableViewStateApi, "get").mockRejectedValue(new Error("offline"));
    const { result } = renderHook(() => useTableViewState("ws-1", "Requirement"));
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.state).toEqual({ columns: [], filters: {}, sort: [] });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `FT src/test/ArtifactTableColumnPicker.test.tsx`
Expected: FAIL — `ColumnPicker` / `useTableViewState` do not exist.

- [ ] **Step 3: Write minimal implementation**

Add to `frontend/src/components/shared/ArtifactTable/ColumnFilterPopover.module.css`:

```css
.pickerRow {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) 0;
  font-size: var(--font-size-sm);
}
```

Create `frontend/src/components/shared/ArtifactTable/ColumnPicker.tsx`:

```tsx
/**
 * Gear menu: which attributes are columns, and in which order (spec §4.3).
 * Order is changed with up/down buttons rather than drag: keyboard- and
 * screen-reader-usable out of the box, and it needs no drag library.
 * Drag-reorder is a later cosmetic addition on the same `ColumnSpec[]` model.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { columnLabel } from "./columnModel";
import type { AttributeDefinitionEntry } from "./columnModel";
import type { ColumnSpec } from "../../../api/table-views";
import styles from "./ColumnFilterPopover.module.css";

export interface ColumnPickerProps {
  attributes: AttributeDefinitionEntry[];
  selection: ColumnSpec[];
  onChange: (selection: ColumnSpec[]) => void;
}

function renumber(fields: string[]): ColumnSpec[] {
  return fields.map((field, order) => ({ field, order }));
}

export function ColumnPicker({
  attributes,
  selection,
  onChange,
}: ColumnPickerProps): JSX.Element {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const core = attributes.filter((a) => a.kind === "core");
  const chosen = selection.slice().sort((a, b) => a.order - b.order).map((s) => s.field);

  const toggle = (field: string): void => {
    onChange(
      renumber(
        chosen.includes(field) ? chosen.filter((f) => f !== field) : [...chosen, field],
      ),
    );
  };

  const move = (field: string, delta: number): void => {
    const index = chosen.indexOf(field);
    const target = index + delta;
    if (index < 0 || target < 0 || target >= chosen.length) return;
    const next = chosen.slice();
    next.splice(target, 0, next.splice(index, 1)[0]);
    onChange(renumber(next));
  };

  return (
    <>
      <button
        type="button"
        data-testid="artifact-table-column-picker-trigger"
        aria-label={t("table.columns", "Columns")}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        ⚙
      </button>
      {open && (
        <div className={styles.popover} data-testid="artifact-table-column-picker">
          {core.map((attribute) => {
            const isChosen = chosen.includes(attribute.name);
            return (
              <div key={attribute.name} className={styles.pickerRow}>
                <input
                  type="checkbox"
                  data-testid={`artifact-table-column-toggle-${attribute.name}`}
                  aria-label={columnLabel(attribute, i18n.language)}
                  checked={isChosen}
                  onChange={() => toggle(attribute.name)}
                />
                <span>{columnLabel(attribute, i18n.language)}</span>
                {isChosen && (
                  <>
                    <button
                      type="button"
                      data-testid={`artifact-table-column-up-${attribute.name}`}
                      aria-label={t("table.moveColumnUp", "Move column up")}
                      onClick={() => move(attribute.name, -1)}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      data-testid={`artifact-table-column-down-${attribute.name}`}
                      aria-label={t("table.moveColumnDown", "Move column down")}
                      onClick={() => move(attribute.name, 1)}
                    >
                      ↓
                    </button>
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}
```

Create `frontend/src/components/shared/ArtifactTable/useTableViewState.ts`:

```ts
/**
 * The unnamed, always-current table state (spec §4.2): no explicit save click,
 * "where I was last time" is simply there when the table reopens.
 *
 * Persisting is best-effort — a failed PUT must never block the interaction,
 * the state stays correct in memory for the session either way.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { tableViewStateApi } from "../../../api/table-views";
import type { TableViewState } from "../../../api/table-views";

const EMPTY: TableViewState = { columns: [], filters: {}, sort: [] };

export interface UseTableViewStateResult {
  state: TableViewState;
  setState: (next: TableViewState) => void;
  ready: boolean;
}

export function useTableViewState(
  workspaceId: string | undefined,
  itemType: string,
): UseTableViewStateResult {
  const [state, setLocalState] = useState<TableViewState>(EMPTY);
  const [ready, setReady] = useState(false);
  const loadedFor = useRef<string>("");

  useEffect(() => {
    if (!workspaceId) return;
    const key = `${workspaceId}:${itemType}`;
    if (loadedFor.current === key) return;
    loadedFor.current = key;
    let cancelled = false;
    setReady(false);
    tableViewStateApi
      .get(workspaceId, itemType)
      .then((loaded) => {
        if (!cancelled) setLocalState(loaded ?? EMPTY);
      })
      .catch(() => {
        if (!cancelled) setLocalState(EMPTY);
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, itemType]);

  const setState = useCallback(
    (next: TableViewState) => {
      setLocalState(next);
      if (!workspaceId) return;
      // ponytail: fire-and-forget PUT per change. Debouncing only matters once
      // a filter control writes on every keystroke; the popover writes on
      // change, not per character.
      void tableViewStateApi.save(workspaceId, itemType, next).catch(() => undefined);
    },
    [workspaceId, itemType],
  );

  return { state, setState, ready };
}
```

Append to `index.ts`:

```ts
export { ColumnPicker } from "./ColumnPicker";
export type { ColumnPickerProps } from "./ColumnPicker";
export { useTableViewState } from "./useTableViewState";
export type { UseTableViewStateResult } from "./useTableViewState";
```

- [ ] **Step 4: Run test to verify it passes**

Run: `FT src/test/ArtifactTableColumnPicker.test.tsx --testTimeout=30000`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shared/ArtifactTable/ frontend/src/test/ArtifactTableColumnPicker.test.tsx
git commit -m "feat(table): add column picker and auto-persisted table view state"
```

---

## Task 20: Saved view bar

**Files:**
- Create: `frontend/src/components/shared/ArtifactTable/SavedViewBar.tsx`
- Modify: `frontend/src/components/shared/ArtifactTable/index.ts`
- Test: `frontend/src/test/ArtifactTableSavedViews.test.tsx`

**Interfaces:**
- Consumes: `savedViewsApi`, `SavedView`, `TableViewState` (Task 15), `components/shared/Dialog/ModalDialogBase`
- Produces: `SavedViewBar`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/ArtifactTableSavedViews.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SavedViewBar } from "../components/shared/ArtifactTable";
import { savedViewsApi } from "../api/table-views";
import type { SavedView } from "../api/table-views";

const ownView: SavedView = {
  id: "v1", workspace_id: "ws-1", item_type: "Requirement", name: "Mine",
  owner_id: "u1", owner_username: "me",
  columns: [{ field: "title", order: 0 }], filters: {}, sort: [],
  visibility: "private", is_owner: true,
};
const sharedView: SavedView = { ...ownView, id: "v2", name: "Team", visibility: "workspace", is_owner: false };

function renderBar(overrides = {}) {
  const props = {
    workspaceId: "ws-1",
    itemType: "Requirement",
    currentState: { columns: [{ field: "title", order: 0 }], filters: {}, sort: [] },
    onApply: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<SavedViewBar {...props} />) };
}

describe("SavedViewBar", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(savedViewsApi, "list").mockResolvedValue({
      count: 2,
      results: [ownView, sharedView],
    });
  });

  it("lists own and shared views", async () => {
    renderBar();
    await waitFor(() =>
      expect(screen.getByTestId("saved-view-option-v1")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("saved-view-option-v2")).toBeInTheDocument();
  });

  it("applies the selected view's columns, filters and sort", async () => {
    const { props } = renderBar();
    await waitFor(() => screen.getByTestId("saved-view-select"));
    fireEvent.change(screen.getByTestId("saved-view-select"), { target: { value: "v2" } });
    expect(props.onApply).toHaveBeenCalledWith(sharedView);
  });

  it("saves the current state under a new name", async () => {
    const create = vi.spyOn(savedViewsApi, "create").mockResolvedValue(ownView);
    renderBar();
    await waitFor(() => screen.getByTestId("saved-view-save-button"));
    fireEvent.click(screen.getByTestId("saved-view-save-button"));
    fireEvent.change(screen.getByTestId("saved-view-name-input"), {
      target: { value: "Safety only" },
    });
    fireEvent.change(screen.getByTestId("saved-view-visibility-select"), {
      target: { value: "workspace" },
    });
    fireEvent.click(screen.getByTestId("saved-view-confirm-save"));

    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0][0]).toMatchObject({
      workspaceId: "ws-1",
      itemType: "Requirement",
      name: "Safety only",
      visibility: "workspace",
      columns: [{ field: "title", order: 0 }],
    });
  });

  it("refuses to save without a name", async () => {
    const create = vi.spyOn(savedViewsApi, "create").mockResolvedValue(ownView);
    renderBar();
    await waitFor(() => screen.getByTestId("saved-view-save-button"));
    fireEvent.click(screen.getByTestId("saved-view-save-button"));
    fireEvent.click(screen.getByTestId("saved-view-confirm-save"));
    expect(create).not.toHaveBeenCalled();
    expect(screen.getByTestId("saved-view-name-error")).toBeInTheDocument();
  });

  it("offers delete only for a view the user owns", async () => {
    renderBar();
    await waitFor(() => screen.getByTestId("saved-view-select"));
    fireEvent.change(screen.getByTestId("saved-view-select"), { target: { value: "v2" } });
    expect(screen.queryByTestId("saved-view-delete-button")).toBeNull();
    fireEvent.change(screen.getByTestId("saved-view-select"), { target: { value: "v1" } });
    expect(screen.getByTestId("saved-view-delete-button")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `FT src/test/ArtifactTableSavedViews.test.tsx`
Expected: FAIL — `SavedViewBar` is not exported.

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/components/shared/ArtifactTable/SavedViewBar.tsx`:

```tsx
/**
 * Saved-view dropdown + save dialog (spec §4.2/§4.3).
 *
 * Delete goes through the shared <ConfirmDialog> — never a hand-rolled
 * window.confirm — and is offered only for views the caller owns; a shared
 * view owned by someone else is read-only here, exactly as the server
 * enforces it.
 */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ConfirmDialog } from "../ConfirmDialog";
import { ModalDialogBase } from "../Dialog/ModalDialogBase";
import { savedViewsApi } from "../../../api/table-views";
import type { SavedView, TableViewState } from "../../../api/table-views";
import styles from "./ColumnFilterPopover.module.css";

export interface SavedViewBarProps {
  workspaceId: string;
  itemType: string;
  currentState: TableViewState;
  onApply: (view: SavedView) => void;
}

export function SavedViewBar({
  workspaceId,
  itemType,
  currentState,
  onApply,
}: SavedViewBarProps): JSX.Element {
  const { t } = useTranslation();
  const [views, setViews] = useState<SavedView[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [saveOpen, setSaveOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [name, setName] = useState("");
  const [visibility, setVisibility] = useState<"private" | "workspace">("private");
  const [nameError, setNameError] = useState(false);

  const reload = (): void => {
    void savedViewsApi
      .list(workspaceId, itemType)
      .then((response) => setViews(response.results))
      .catch(() => setViews([]));
  };

  useEffect(reload, [workspaceId, itemType]);

  const selected = views.find((view) => view.id === selectedId);

  return (
    <div className={styles.chipRow} data-testid="saved-view-bar">
      <select
        data-testid="saved-view-select"
        aria-label={t("table.savedViews", "Saved views")}
        value={selectedId}
        onChange={(event) => {
          setSelectedId(event.target.value);
          const view = views.find((v) => v.id === event.target.value);
          if (view) onApply(view);
        }}
      >
        <option value="">{t("table.savedViewsNone", "No saved view")}</option>
        {views.map((view) => (
          <option key={view.id} value={view.id} data-testid={`saved-view-option-${view.id}`}>
            {view.name}
            {view.visibility === "workspace" ? " · " + t("table.shared", "shared") : ""}
          </option>
        ))}
      </select>

      <button
        type="button"
        data-testid="saved-view-save-button"
        onClick={() => {
          setName("");
          setVisibility("private");
          setNameError(false);
          setSaveOpen(true);
        }}
      >
        {t("table.saveView", "Save view")}
      </button>

      {selected?.is_owner && (
        <button
          type="button"
          data-testid="saved-view-delete-button"
          onClick={() => setConfirmDelete(true)}
        >
          {t("table.deleteView", "Delete view")}
        </button>
      )}

      {saveOpen && (
        <ModalDialogBase
          testId="saved-view-save-dialog"
          title={t("table.saveViewTitle", "Save this view")}
          onClose={() => setSaveOpen(false)}
        >
          <input
            type="text"
            data-testid="saved-view-name-input"
            aria-label={t("table.viewName", "View name")}
            value={name}
            onChange={(event) => {
              setName(event.target.value);
              setNameError(false);
            }}
          />
          {nameError && (
            <p data-testid="saved-view-name-error">
              {t("table.viewNameRequired", "A name is required")}
            </p>
          )}
          <select
            data-testid="saved-view-visibility-select"
            aria-label={t("table.viewVisibility", "Visibility")}
            value={visibility}
            onChange={(event) =>
              setVisibility(event.target.value as "private" | "workspace")
            }
          >
            <option value="private">{t("table.visibilityPrivate", "Only me")}</option>
            <option value="workspace">
              {t("table.visibilityWorkspace", "Everyone in this workspace")}
            </option>
          </select>
          <button
            type="button"
            data-testid="saved-view-confirm-save"
            onClick={() => {
              if (!name.trim()) {
                setNameError(true);
                return;
              }
              void savedViewsApi
                .create({
                  workspaceId,
                  itemType,
                  name: name.trim(),
                  columns: currentState.columns,
                  filters: currentState.filters,
                  sort: currentState.sort,
                  visibility,
                })
                .then(() => {
                  setSaveOpen(false);
                  reload();
                });
            }}
          >
            {t("actions.save", "Save")}
          </button>
        </ModalDialogBase>
      )}

      {confirmDelete && selected && (
        <ConfirmDialog
          testId="saved-view-delete-confirm"
          confirmTestId="saved-view-delete-confirm-button"
          cancelTestId="saved-view-delete-cancel-button"
          title={t("table.deleteViewTitle", "Delete saved view")}
          message={t("table.deleteViewMessage", "Delete \"{{name}}\"?", { name: selected.name })}
          confirmLabel={t("actions.delete", "Delete")}
          onCancel={() => setConfirmDelete(false)}
          onConfirm={() => {
            void savedViewsApi.remove(selected.id).then(() => {
              setConfirmDelete(false);
              setSelectedId("");
              reload();
            });
          }}
        />
      )}
    </div>
  );
}
```

Before running, check the real prop names of the two shared dialogs and adapt the calls:
`grep -n "interface ConfirmDialogProps" -A 20 frontend/src/components/shared/ConfirmDialog.tsx` and
`grep -n "interface ModalDialogBaseProps" -A 20 frontend/src/components/RequirementsList/ModalDialogBase.tsx`.
Do not hand-roll a confirm — `ConfirmDialog` is the single delete seam in this codebase.

Append to `index.ts`:

```ts
export { SavedViewBar } from "./SavedViewBar";
export type { SavedViewBarProps } from "./SavedViewBar";
```

- [ ] **Step 4: Run test to verify it passes**

Run: `FT src/test/ArtifactTableSavedViews.test.tsx --testTimeout=30000`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shared/ArtifactTable/ frontend/src/test/ArtifactTableSavedViews.test.tsx
git commit -m "feat(table): add saved view bar with save and delete dialogs"
```

---

## Task 21: Bulk action bar with partial-success reporting

**Files:**
- Create: `frontend/src/components/shared/ArtifactTable/BulkActionBar.tsx`
- Modify: `frontend/src/components/shared/ArtifactTable/index.ts`
- Test: `frontend/src/test/ArtifactTableBulk.test.tsx`

**Interfaces:**
- Consumes: `tableApi.bulkUpdate/bulkTransition`, `BulkResult` (Task 15), `TableColumn` (Task 16), `ModalDialogBase`
- Produces: `BulkActionBar`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/ArtifactTableBulk.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BulkActionBar } from "../components/shared/ArtifactTable";
import { buildColumns } from "../components/shared/ArtifactTable/columnModel";
import type { AttributeDefinitionEntry } from "../components/shared/ArtifactTable/columnModel";
import { tableApi } from "../api/table-views";

const attributes: AttributeDefinitionEntry[] = [
  { name: "title", kind: "core", type: "text", editable: true, visible: true, order: 1 },
  { name: "category", kind: "core", type: "enum", editable: true, visible: true, order: 2,
    options: [{ value: "safety", label_de: "Sicherheit", label_en: "Safety" }] },
  { name: "status", kind: "core", type: "enum", editable: "workflow", visible: true, order: 3 },
];

function renderBar(overrides = {}) {
  const props = {
    workspaceId: "ws-1",
    itemType: "Requirement",
    columns: buildColumns(attributes, []),
    selectedIds: ["r1", "r2"],
    availableStates: ["in_review", "approved"],
    onDone: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<BulkActionBar {...props} />) };
}

describe("BulkActionBar", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("stays hidden while nothing is selected", () => {
    const { container } = renderBar({ selectedIds: [] });
    expect(container.firstChild).toBeNull();
  });

  it("shows the selection count", () => {
    renderBar();
    expect(screen.getByTestId("bulk-action-count")).toHaveTextContent("2");
  });

  it("never offers a workflow-owned field in the bulk edit dialog", () => {
    renderBar();
    fireEvent.click(screen.getByTestId("bulk-edit-button"));
    const select = screen.getByTestId("bulk-edit-field-select");
    const values = Array.from(select.querySelectorAll("option")).map((o) => o.getAttribute("value"));
    expect(values).toContain("title");
    expect(values).toContain("category");
    expect(values).not.toContain("status");
  });

  it("sends the chosen field through bulkUpdate", async () => {
    const bulkUpdate = vi
      .spyOn(tableApi, "bulkUpdate")
      .mockResolvedValue({ updated: ["r1", "r2"], failed: [] });
    renderBar();
    fireEvent.click(screen.getByTestId("bulk-edit-button"));
    fireEvent.change(screen.getByTestId("bulk-edit-field-select"), {
      target: { value: "category" },
    });
    fireEvent.change(screen.getByTestId("bulk-edit-value-input"), {
      target: { value: "safety" },
    });
    fireEvent.click(screen.getByTestId("bulk-edit-apply"));

    await waitFor(() => expect(bulkUpdate).toHaveBeenCalled());
    expect(bulkUpdate.mock.calls[0][0]).toMatchObject({
      workspaceId: "ws-1",
      itemType: "Requirement",
      ids: ["r1", "r2"],
      fields: { category: "safety" },
    });
  });

  it("reports a partial result explicitly instead of silently succeeding", async () => {
    vi.spyOn(tableApi, "bulkUpdate").mockResolvedValue({
      updated: ["r1"],
      failed: [{ id: "r2", error: "Requirement not found" }],
    });
    renderBar();
    fireEvent.click(screen.getByTestId("bulk-edit-button"));
    fireEvent.change(screen.getByTestId("bulk-edit-field-select"), {
      target: { value: "title" },
    });
    fireEvent.change(screen.getByTestId("bulk-edit-value-input"), {
      target: { value: "New title" },
    });
    fireEvent.click(screen.getByTestId("bulk-edit-apply"));

    const summary = await screen.findByTestId("bulk-result-summary");
    expect(summary).toHaveTextContent("1");
    expect(summary).toHaveTextContent("2");
    expect(screen.getByTestId("bulk-result-failure-r2")).toHaveTextContent(
      "Requirement not found",
    );
  });

  it("surfaces a rejected bulk update as an error banner", async () => {
    vi.spyOn(tableApi, "bulkUpdate").mockRejectedValue(
      new Error("Fields owned by the workflow engine cannot be bulk-updated: status."),
    );
    renderBar();
    fireEvent.click(screen.getByTestId("bulk-edit-button"));
    fireEvent.change(screen.getByTestId("bulk-edit-field-select"), {
      target: { value: "title" },
    });
    fireEvent.change(screen.getByTestId("bulk-edit-value-input"), { target: { value: "x" } });
    fireEvent.click(screen.getByTestId("bulk-edit-apply"));

    expect(await screen.findByTestId("bulk-result-error")).toHaveTextContent(
      "workflow engine",
    );
  });

  it("offers only the reachable target states for a bulk transition", async () => {
    const bulkTransition = vi
      .spyOn(tableApi, "bulkTransition")
      .mockResolvedValue({ updated: ["r1", "r2"], failed: [] });
    renderBar();
    fireEvent.click(screen.getByTestId("bulk-transition-button"));
    const options = Array.from(
      screen.getByTestId("bulk-transition-state-select").querySelectorAll("option"),
    ).map((o) => o.getAttribute("value"));
    expect(options).toEqual(["", "in_review", "approved"]);

    fireEvent.change(screen.getByTestId("bulk-transition-state-select"), {
      target: { value: "approved" },
    });
    fireEvent.change(screen.getByTestId("bulk-transition-reason-input"), {
      target: { value: "batch approval" },
    });
    fireEvent.click(screen.getByTestId("bulk-transition-apply"));

    await waitFor(() => expect(bulkTransition).toHaveBeenCalled());
    expect(bulkTransition.mock.calls[0][0]).toMatchObject({
      toState: "approved",
      changeReason: "batch approval",
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `FT src/test/ArtifactTableBulk.test.tsx`
Expected: FAIL — `BulkActionBar` is not exported.

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/components/shared/ArtifactTable/BulkActionBar.tsx`:

```tsx
/**
 * Toolbar actions for the current row selection (spec §4.3).
 *
 * Guardrail (spec §2): the field dropdown of "edit fields" is built from
 * `column.editable`, so a workflow-owned column can never even be picked. The
 * server rejects it as well — this is the visible half of the same rule.
 *
 * Partial success is reported explicitly (spec §6): "38 of 40 updated" plus a
 * per-item reason list, never a silent green.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ModalDialogBase } from "../Dialog/ModalDialogBase";
import { tableApi } from "../../../api/table-views";
import type { BulkResult } from "../../../api/table-views";
import type { TableColumn } from "./columnModel";
import { columnLabel } from "./columnModel";
import styles from "./ColumnFilterPopover.module.css";

export interface BulkActionBarProps {
  workspaceId: string;
  itemType: string;
  columns: TableColumn[];
  selectedIds: string[];
  /** Target states reachable from the current selection's states. */
  availableStates: string[];
  /** Called after a bulk operation so the host can refetch. */
  onDone: () => void;
}

type Mode = null | "edit" | "transition";

export function BulkActionBar({
  workspaceId,
  itemType,
  columns,
  selectedIds,
  availableStates,
  onDone,
}: BulkActionBarProps): JSX.Element | null {
  const { t, i18n } = useTranslation();
  const [mode, setMode] = useState<Mode>(null);
  const [field, setField] = useState("");
  const [value, setValue] = useState("");
  const [toState, setToState] = useState("");
  const [reason, setReason] = useState("");
  const [result, setResult] = useState<BulkResult | null>(null);
  const [error, setError] = useState("");

  if (selectedIds.length === 0) return null;

  const editable = columns.filter((column) => column.editable);

  const run = (promise: Promise<BulkResult>): void => {
    setError("");
    void promise
      .then((response) => {
        setResult(response);
        onDone();
      })
      .catch((exc: unknown) => {
        setResult(null);
        setError(exc instanceof Error ? exc.message : String(exc));
      });
  };

  return (
    <div className={styles.chipRow} data-testid="bulk-action-bar">
      <span data-testid="bulk-action-count">
        {t("table.selectedCount", "{{count}} selected", { count: selectedIds.length })}
      </span>
      <button type="button" data-testid="bulk-edit-button" onClick={() => setMode("edit")}>
        {t("table.bulkEdit", "Edit fields")}
      </button>
      <button
        type="button"
        data-testid="bulk-transition-button"
        onClick={() => setMode("transition")}
      >
        {t("table.bulkTransition", "Change status")}
      </button>

      {mode === "edit" && (
        <ModalDialogBase
          testId="bulk-edit-dialog"
          title={t("table.bulkEditTitle", "Edit selected artifacts")}
          onClose={() => setMode(null)}
        >
          <select
            data-testid="bulk-edit-field-select"
            aria-label={t("table.bulkEditField", "Field")}
            value={field}
            onChange={(event) => setField(event.target.value)}
          >
            <option value="">{t("table.bulkEditPickField", "Pick a field")}</option>
            {editable.map((column) => (
              <option key={column.field} value={column.field}>
                {columnLabel(column.attribute, i18n.language)}
              </option>
            ))}
          </select>
          <input
            type="text"
            data-testid="bulk-edit-value-input"
            aria-label={t("table.bulkEditValue", "New value")}
            value={value}
            onChange={(event) => setValue(event.target.value)}
          />
          <input
            type="text"
            data-testid="bulk-edit-reason-input"
            aria-label={t("table.changeReason", "Change reason")}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
          <button
            type="button"
            data-testid="bulk-edit-apply"
            disabled={!field}
            onClick={() =>
              run(
                tableApi.bulkUpdate({
                  workspaceId,
                  itemType,
                  ids: selectedIds,
                  fields: { [field]: value },
                  changeReason: reason,
                }),
              )
            }
          >
            {t("actions.apply", "Apply")}
          </button>
        </ModalDialogBase>
      )}

      {mode === "transition" && (
        <ModalDialogBase
          testId="bulk-transition-dialog"
          title={t("table.bulkTransitionTitle", "Change status of selected artifacts")}
          onClose={() => setMode(null)}
        >
          <select
            data-testid="bulk-transition-state-select"
            aria-label={t("table.targetState", "Target state")}
            value={toState}
            onChange={(event) => setToState(event.target.value)}
          >
            <option value="">{t("table.pickTargetState", "Pick a target state")}</option>
            {availableStates.map((state) => (
              <option key={state} value={state}>
                {state}
              </option>
            ))}
          </select>
          <input
            type="text"
            data-testid="bulk-transition-reason-input"
            aria-label={t("table.changeReason", "Change reason")}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
          <button
            type="button"
            data-testid="bulk-transition-apply"
            disabled={!toState}
            onClick={() =>
              run(
                tableApi.bulkTransition({
                  workspaceId,
                  itemType,
                  ids: selectedIds,
                  toState,
                  changeReason: reason,
                }),
              )
            }
          >
            {t("actions.apply", "Apply")}
          </button>
        </ModalDialogBase>
      )}

      {error && (
        <p role="alert" data-testid="bulk-result-error">
          {error}
        </p>
      )}

      {result && (
        <div data-testid="bulk-result">
          <p data-testid="bulk-result-summary">
            {t("table.bulkResult", "{{updated}} of {{total}} updated", {
              updated: result.updated.length,
              total: result.updated.length + result.failed.length,
            })}
          </p>
          {result.failed.map((failure) => (
            <p key={failure.id} data-testid={`bulk-result-failure-${failure.id}`}>
              {failure.id}: {failure.error}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
```

Append to `index.ts`:

```ts
export { BulkActionBar } from "./BulkActionBar";
export type { BulkActionBarProps } from "./BulkActionBar";
```

- [ ] **Step 4: Run test to verify it passes**

Run: `FT src/test/ArtifactTableBulk.test.tsx --testTimeout=30000`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shared/ArtifactTable/ frontend/src/test/ArtifactTableBulk.test.tsx
git commit -m "feat(table): add bulk action bar with explicit partial-success report"
```

---

## Task 22: Inline cell edit through the single-item update path

**Files:**
- Create: `frontend/src/components/shared/ArtifactTable/InlineCellEditor.tsx`
- Modify: `frontend/src/components/shared/ArtifactTable/index.ts`
- Test: `frontend/src/test/ArtifactTableInlineEdit.test.tsx`

**Interfaces:**
- Consumes: `TableColumn` (Task 16), `ArtifactTableProps.renderCellEditor` / `onInlineSave` (Task 17)
- Produces: `InlineCellEditor`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/ArtifactTableInlineEdit.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ArtifactTable, InlineCellEditor } from "../components/shared/ArtifactTable";
import { buildColumns } from "../components/shared/ArtifactTable/columnModel";
import type { AttributeDefinitionEntry } from "../components/shared/ArtifactTable/columnModel";
import type { TableRow } from "../api/table-views";

const attributes: AttributeDefinitionEntry[] = [
  { name: "title", kind: "core", type: "text", editable: true, visible: true, order: 1 },
  { name: "status", kind: "core", type: "enum", editable: "workflow", visible: true, order: 2 },
];
const rows: TableRow[] = [
  { id: "r1", artifact_id: "a1", title: "Brake force", status: "draft" },
];

function renderTable(onInlineSave = vi.fn().mockResolvedValue(undefined)) {
  const columns = buildColumns(attributes, []);
  render(
    <ArtifactTable
      itemType="Requirement"
      columns={columns}
      rows={rows}
      sort={[]}
      onSortChange={vi.fn()}
      selectedIds={[]}
      onSelectionChange={vi.fn()}
      onOpenTransition={vi.fn()}
      onInlineSave={onInlineSave}
      renderCellEditor={(column, row, done) => (
        <InlineCellEditor
          column={column}
          row={row}
          onSave={(value) => onInlineSave(row.id, column.field, value)}
          onDone={done}
        />
      )}
    />,
  );
  return onInlineSave;
}

describe("inline cell edit", () => {
  it("opens an editor on an editable cell", () => {
    renderTable();
    fireEvent.click(screen.getByTestId("artifact-table-cell-r1-title"));
    expect(screen.getByTestId("inline-editor-input")).toHaveValue("Brake force");
  });

  it("saves through the single-item path on blur", async () => {
    const onInlineSave = renderTable();
    fireEvent.click(screen.getByTestId("artifact-table-cell-r1-title"));
    fireEvent.change(screen.getByTestId("inline-editor-input"), {
      target: { value: "Braking force" },
    });
    fireEvent.blur(screen.getByTestId("inline-editor-input"));
    await waitFor(() =>
      expect(onInlineSave).toHaveBeenCalledWith("r1", "title", "Braking force"),
    );
  });

  it("saves on Enter and abandons on Escape", async () => {
    const onInlineSave = renderTable();
    fireEvent.click(screen.getByTestId("artifact-table-cell-r1-title"));
    fireEvent.change(screen.getByTestId("inline-editor-input"), { target: { value: "X" } });
    fireEvent.keyDown(screen.getByTestId("inline-editor-input"), { key: "Escape" });
    expect(onInlineSave).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("artifact-table-cell-r1-title"));
    fireEvent.change(screen.getByTestId("inline-editor-input"), { target: { value: "Y" } });
    fireEvent.keyDown(screen.getByTestId("inline-editor-input"), { key: "Enter" });
    await waitFor(() => expect(onInlineSave).toHaveBeenCalledWith("r1", "title", "Y"));
  });

  it("does not save when the value is unchanged", async () => {
    const onInlineSave = renderTable();
    fireEvent.click(screen.getByTestId("artifact-table-cell-r1-title"));
    fireEvent.blur(screen.getByTestId("inline-editor-input"));
    await waitFor(() => expect(screen.queryByTestId("inline-editor-input")).toBeNull());
    expect(onInlineSave).not.toHaveBeenCalled();
  });

  it("never opens an editor on the workflow-owned cell", () => {
    renderTable();
    fireEvent.click(screen.getByTestId("artifact-table-cell-r1-status"));
    expect(screen.queryByTestId("inline-editor-input")).toBeNull();
  });

  it("shows the error and keeps the editor open when the save is rejected", async () => {
    const onInlineSave = vi.fn().mockRejectedValue(new Error("Value not allowed"));
    renderTable(onInlineSave);
    fireEvent.click(screen.getByTestId("artifact-table-cell-r1-title"));
    fireEvent.change(screen.getByTestId("inline-editor-input"), { target: { value: "Z" } });
    fireEvent.keyDown(screen.getByTestId("inline-editor-input"), { key: "Enter" });
    expect(await screen.findByTestId("inline-editor-error")).toHaveTextContent(
      "Value not allowed",
    );
    expect(screen.getByTestId("inline-editor-input")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `FT src/test/ArtifactTableInlineEdit.test.tsx`
Expected: FAIL — `InlineCellEditor` is not exported.

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/components/shared/ArtifactTable/InlineCellEditor.tsx`:

```tsx
/**
 * One editable cell (spec §4.3).
 *
 * Saves through the caller's *single-item* update path, deliberately NOT the
 * bulk endpoint: a one-cell edit must keep the ordinary per-entity validation,
 * change_reason policy and optimistic-lock behaviour of the normal update.
 *
 * A workflow-owned cell never reaches this component — `ArtifactTable` does
 * not enter edit mode for `column.editable === false`.
 */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { TableColumn } from "./columnModel";
import type { TableRow } from "../../../api/table-views";

export interface InlineCellEditorProps {
  column: TableColumn;
  row: TableRow;
  onSave: (value: unknown) => Promise<void>;
  onDone: () => void;
}

export function InlineCellEditor({
  column,
  row,
  onSave,
  onDone,
}: InlineCellEditorProps): JSX.Element {
  const { t } = useTranslation();
  const original = row[column.field];
  const [value, setValue] = useState(original === null || original === undefined ? "" : String(original));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const commit = (): void => {
    if (busy) return;
    if (value === (original === null || original === undefined ? "" : String(original))) {
      onDone();
      return;
    }
    setBusy(true);
    setError("");
    void onSave(value)
      .then(onDone)
      .catch((exc: unknown) => {
        setError(exc instanceof Error ? exc.message : String(exc));
      })
      .finally(() => setBusy(false));
  };

  const inputType = column.type === "date" ? "date" : column.type === "number" ? "number" : "text";

  return (
    <>
      {column.options.length > 0 ? (
        <select
          data-testid="inline-editor-input"
          aria-label={t("table.editValue", "Edit value")}
          autoFocus
          disabled={busy}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === "Enter") commit();
            if (event.key === "Escape") onDone();
          }}
        >
          <option value="">—</option>
          {column.options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label_en}
            </option>
          ))}
        </select>
      ) : (
        <input
          type={inputType}
          data-testid="inline-editor-input"
          aria-label={t("table.editValue", "Edit value")}
          autoFocus
          disabled={busy}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === "Enter") commit();
            if (event.key === "Escape") onDone();
          }}
        />
      )}
      {error && (
        <span role="alert" data-testid="inline-editor-error">
          {error}
        </span>
      )}
    </>
  );
}
```

Append to `index.ts`:

```ts
export { InlineCellEditor } from "./InlineCellEditor";
export type { InlineCellEditorProps } from "./InlineCellEditor";
```

- [ ] **Step 4: Run test to verify it passes**

Run: `FT src/test/ArtifactTableInlineEdit.test.tsx --testTimeout=30000`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shared/ArtifactTable/ frontend/src/test/ArtifactTableInlineEdit.test.tsx
git commit -m "feat(table): add inline cell editing via the single-item update path"
```

---

## Task 23: Mount the table on the Requirements page + i18n

**Files:**
- Create: `frontend/src/components/shared/ArtifactTable/ArtifactTableView.tsx`
- Modify: `frontend/src/components/RequirementEditors/RequirementEditors.tsx`, `frontend/src/i18n/locales/de.json`, `frontend/src/i18n/locales/en.json`, `frontend/src/components/shared/ArtifactTable/index.ts`
- Test: `frontend/src/test/ArtifactTableView.test.tsx`

**Interfaces:**
- Consumes: everything from Tasks 15–22, `useWorkspace()` from `context/WorkspaceContext`
- Produces: `ArtifactTableView` (the composed, self-fetching table page section), the `table` i18n namespace

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/ArtifactTableView.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ArtifactTableView } from "../components/shared/ArtifactTable";
import { tableApi, tableViewStateApi, savedViewsApi } from "../api/table-views";
import type { AttributeDefinitionEntry } from "../components/shared/ArtifactTable/columnModel";

const attributes: AttributeDefinitionEntry[] = [
  { name: "title", kind: "core", type: "text", editable: true, visible: true, order: 1 },
  { name: "status", kind: "core", type: "enum", editable: "workflow", visible: true, order: 2 },
];

describe("ArtifactTableView", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(tableViewStateApi, "get").mockResolvedValue({ columns: [], filters: {}, sort: [] });
    vi.spyOn(tableViewStateApi, "save").mockResolvedValue({ columns: [], filters: {}, sort: [] });
    vi.spyOn(savedViewsApi, "list").mockResolvedValue({ count: 0, results: [] });
  });

  it("queries the table endpoint with the workspace and item type", async () => {
    const query = vi.spyOn(tableApi, "query").mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [{ id: "r1", artifact_id: "a1", title: "Brake force", status: "draft" }],
    } as never);

    render(
      <ArtifactTableView
        workspaceId="ws-1"
        itemType="Requirement"
        attributes={attributes}
        onInlineSave={vi.fn().mockResolvedValue(undefined)}
        onOpenTransition={vi.fn()}
        availableStates={["approved"]}
      />,
    );

    await waitFor(() => expect(query).toHaveBeenCalled());
    expect(query.mock.calls[0][0]).toMatchObject({
      workspaceId: "ws-1",
      itemType: "Requirement",
    });
    expect(await screen.findByTestId("artifact-table-row-r1")).toBeInTheDocument();
  });

  it("renders the toolbar pieces around the grid", async () => {
    vi.spyOn(tableApi, "query").mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    } as never);

    render(
      <ArtifactTableView
        workspaceId="ws-1"
        itemType="Requirement"
        attributes={attributes}
        onInlineSave={vi.fn()}
        onOpenTransition={vi.fn()}
        availableStates={[]}
      />,
    );

    expect(await screen.findByTestId("artifact-table-column-picker-trigger")).toBeInTheDocument();
    expect(screen.getByTestId("saved-view-bar")).toBeInTheDocument();
    expect(screen.getByTestId("artifact-table-empty")).toBeInTheDocument();
  });

  it("shows an error banner when the query fails", async () => {
    vi.spyOn(tableApi, "query").mockRejectedValue(new Error("Unknown field 'nope'"));

    render(
      <ArtifactTableView
        workspaceId="ws-1"
        itemType="Requirement"
        attributes={attributes}
        onInlineSave={vi.fn()}
        onOpenTransition={vi.fn()}
        availableStates={[]}
      />,
    );

    expect(await screen.findByTestId("artifact-table-error")).toHaveTextContent("nope");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `FT src/test/ArtifactTableView.test.tsx`
Expected: FAIL — `ArtifactTableView` is not exported.

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/components/shared/ArtifactTable/ArtifactTableView.tsx`:

```tsx
/**
 * Composed table section: saved views + column picker + filter chips + grid +
 * bulk actions, wired to `tableApi.query` and the auto-persisted view state.
 *
 * The host page supplies only what it alone knows: the workspace, the item
 * type, the resolved attribute definition, how to save a single field, how to
 * open the transition dialog, and which target states are reachable.
 */
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ActiveFilterChips } from "./ActiveFilterChips";
import { ArtifactTable } from "./ArtifactTable";
import { BulkActionBar } from "./BulkActionBar";
import { ColumnFilterPopover } from "./ColumnFilterPopover";
import { ColumnPicker } from "./ColumnPicker";
import { InlineCellEditor } from "./InlineCellEditor";
import { SavedViewBar } from "./SavedViewBar";
import { buildColumns } from "./columnModel";
import type { AttributeDefinitionEntry } from "./columnModel";
import { useTableViewState } from "./useTableViewState";
import { tableApi } from "../../../api/table-views";
import type { TableRow } from "../../../api/table-views";

export interface ArtifactTableViewProps {
  workspaceId: string;
  itemType: string;
  attributes: AttributeDefinitionEntry[];
  onInlineSave: (rowId: string, field: string, value: unknown) => Promise<void>;
  onOpenTransition: (rowId: string) => void;
  availableStates: string[];
}

export function ArtifactTableView({
  workspaceId,
  itemType,
  attributes,
  onInlineSave,
  onOpenTransition,
  availableStates,
}: ArtifactTableViewProps): JSX.Element {
  const { t } = useTranslation();
  const { state, setState, ready } = useTableViewState(workspaceId, itemType);
  const [rows, setRows] = useState<TableRow[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  const columns = buildColumns(attributes, state.columns);

  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    tableApi
      .query({
        workspaceId,
        itemType,
        filters: state.filters,
        sort: state.sort,
        columns: columns.map((column) => column.field),
      })
      .then((page) => {
        if (!cancelled) setRows(page.results);
      })
      .catch((exc: unknown) => {
        if (!cancelled) {
          setRows([]);
          setError(exc instanceof Error ? exc.message : String(exc));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // `columns` is derived from state.columns, so it needs no own dependency.
  }, [ready, workspaceId, itemType, state.filters, state.sort, state.columns, reloadToken]);

  const refresh = useCallback(() => setReloadToken((token) => token + 1), []);

  return (
    <div data-testid={`artifact-table-view-${itemType}`}>
      <SavedViewBar
        workspaceId={workspaceId}
        itemType={itemType}
        currentState={state}
        onApply={(view) =>
          setState({ columns: view.columns, filters: view.filters, sort: view.sort })
        }
      />
      <ColumnPicker
        attributes={attributes}
        selection={state.columns}
        onChange={(selection) => setState({ ...state, columns: selection })}
      />
      <ActiveFilterChips
        columns={columns}
        filters={state.filters}
        onChange={(filters) => setState({ ...state, filters })}
      />
      <BulkActionBar
        workspaceId={workspaceId}
        itemType={itemType}
        columns={columns}
        selectedIds={selectedIds}
        availableStates={availableStates}
        onDone={() => {
          setSelectedIds([]);
          refresh();
        }}
      />
      {error && (
        <p role="alert" data-testid="artifact-table-error">
          {error}
        </p>
      )}
      <ArtifactTable
        itemType={itemType}
        columns={columns}
        rows={rows}
        loading={loading}
        sort={state.sort}
        onSortChange={(sort) => setState({ ...state, sort })}
        selectedIds={selectedIds}
        onSelectionChange={setSelectedIds}
        onOpenTransition={onOpenTransition}
        onInlineSave={onInlineSave}
        renderHeaderFilter={(column) => (
          <ColumnFilterPopover
            column={column}
            filters={state.filters}
            onChange={(filters) => setState({ ...state, filters })}
          />
        )}
        renderCellEditor={(column, row, done) => (
          <InlineCellEditor
            column={column}
            row={row}
            onSave={async (value) => {
              await onInlineSave(row.id, column.field, value);
              refresh();
            }}
            onDone={done}
          />
        )}
      />
      {loading && <span data-testid="artifact-table-loading">{t("loading", "Loading…")}</span>}
    </div>
  );
}
```

Append `export { ArtifactTableView } from "./ArtifactTableView";` and its props type to `index.ts`.

Add the `table` namespace to **both** locale files (structurally identical — `src/test/i18n-parity.test.ts` compares them), as a nested object, never dotted keys.

`frontend/src/i18n/locales/en.json`:

```json
  "table": {
    "viewModeList": "List",
    "viewModeTable": "Table",
    "selectAll": "Select all rows",
    "selectRow": "Select row",
    "changeStatus": "Change status",
    "noRows": "No matching artifacts",
    "columns": "Columns",
    "moveColumnUp": "Move column up",
    "moveColumnDown": "Move column down",
    "filterColumn": "Filter {{column}}",
    "filterFrom": "From",
    "filterTo": "To",
    "filterAll": "All",
    "filterYes": "Yes",
    "filterNo": "No",
    "removeFilter": "Remove filter",
    "savedViews": "Saved views",
    "savedViewsNone": "No saved view",
    "shared": "shared",
    "saveView": "Save view",
    "saveViewTitle": "Save this view",
    "viewName": "View name",
    "viewNameRequired": "A name is required",
    "viewVisibility": "Visibility",
    "visibilityPrivate": "Only me",
    "visibilityWorkspace": "Everyone in this workspace",
    "deleteView": "Delete view",
    "deleteViewTitle": "Delete saved view",
    "deleteViewMessage": "Delete \"{{name}}\"?",
    "selectedCount": "{{count}} selected",
    "bulkEdit": "Edit fields",
    "bulkEditTitle": "Edit selected artifacts",
    "bulkEditField": "Field",
    "bulkEditPickField": "Pick a field",
    "bulkEditValue": "New value",
    "bulkTransition": "Change status",
    "bulkTransitionTitle": "Change status of selected artifacts",
    "targetState": "Target state",
    "pickTargetState": "Pick a target state",
    "changeReason": "Change reason",
    "bulkResult": "{{updated}} of {{total}} updated",
    "editValue": "Edit value"
  },
```

`frontend/src/i18n/locales/de.json` (same keys, German values):

```json
  "table": {
    "viewModeList": "Liste",
    "viewModeTable": "Tabelle",
    "selectAll": "Alle Zeilen auswählen",
    "selectRow": "Zeile auswählen",
    "changeStatus": "Status ändern",
    "noRows": "Keine passenden Artefakte",
    "columns": "Spalten",
    "moveColumnUp": "Spalte nach oben",
    "moveColumnDown": "Spalte nach unten",
    "filterColumn": "{{column}} filtern",
    "filterFrom": "Von",
    "filterTo": "Bis",
    "filterAll": "Alle",
    "filterYes": "Ja",
    "filterNo": "Nein",
    "removeFilter": "Filter entfernen",
    "savedViews": "Gespeicherte Ansichten",
    "savedViewsNone": "Keine gespeicherte Ansicht",
    "shared": "geteilt",
    "saveView": "Ansicht speichern",
    "saveViewTitle": "Diese Ansicht speichern",
    "viewName": "Name der Ansicht",
    "viewNameRequired": "Ein Name ist erforderlich",
    "viewVisibility": "Sichtbarkeit",
    "visibilityPrivate": "Nur ich",
    "visibilityWorkspace": "Alle in diesem Workspace",
    "deleteView": "Ansicht löschen",
    "deleteViewTitle": "Gespeicherte Ansicht löschen",
    "deleteViewMessage": "\"{{name}}\" löschen?",
    "selectedCount": "{{count}} ausgewählt",
    "bulkEdit": "Felder bearbeiten",
    "bulkEditTitle": "Ausgewählte Artefakte bearbeiten",
    "bulkEditField": "Feld",
    "bulkEditPickField": "Feld wählen",
    "bulkEditValue": "Neuer Wert",
    "bulkTransition": "Status ändern",
    "bulkTransitionTitle": "Status der ausgewählten Artefakte ändern",
    "targetState": "Zielzustand",
    "pickTargetState": "Zielzustand wählen",
    "changeReason": "Änderungsgrund",
    "bulkResult": "{{updated}} von {{total}} aktualisiert",
    "editValue": "Wert bearbeiten"
  },
```

In `frontend/src/components/RequirementEditors/RequirementEditors.tsx`, add the mode state near
the other `useState` calls:

```tsx
  const [viewMode, setViewMode] = useState<"list" | "table">("list");
```

add a toggle button to the `pageHeader` actions array (next to the existing entries):

```tsx
        {
          label: viewMode === "list" ? t("table.viewModeTable") : t("table.viewModeList"),
          testId: "requirements-view-mode-toggle",
          onClick: () => setViewMode((mode) => (mode === "list" ? "table" : "list")),
        },
```

and swap the body — replacing only the `<SplitView ... />` element, leaving the two surrounding
`style={{ ... }}` attributes untouched so the UI ratchet's exact `STYLE_BRACE_BASELINE` count
does not move:

```tsx
          {viewMode === "table" && activeWorkspace ? (
            <ArtifactTableView
              workspaceId={activeWorkspace.id}
              itemType="Requirement"
              attributes={attributeDefinition}
              onInlineSave={async (rowId, field, value) => {
                await updateRequirement.mutateAsync({ id: rowId, [field]: value });
              }}
              onOpenTransition={(rowId) => navigate(`/requirements/${rowId}`)}
              availableStates={availableStates}
            />
          ) : (
            <SplitView
              leftPanel={leftPanel}
              rightPanel={rightPanel}
              leftMinWidth={260}
              leftMaxWidthPercent={70}
              moduleType="requirements"
            />
          )}
```

`attributeDefinition` comes from the Attribut-Definition spec's hook
(`useAttributeDefinition(activeWorkspace.id, "Requirement")`); `availableStates` from the existing
workflow-transitions API wrapper (`frontend/src/api/workflow-transitions.ts`). Confirm both names
against the code as it stands when this task runs, and check the exact shape of the `pageHeader`
actions array (`grep -n "const pageHeader" -A 40 frontend/src/components/RequirementEditors/RequirementEditors.tsx`)
before inserting the toggle.

Deliberate scope note: the toggle ships on the Requirements page only. Rolling it out to the other
list pages is one prop-identical mount each and is a follow-up, not part of this plan.

- [ ] **Step 4: Run test to verify it passes**

Run: `FT src/test/ArtifactTableView.test.tsx src/test/i18n-parity.test.ts src/test/ui-ratchet.test.ts --testTimeout=30000`
Expected: PASS (3 passed + i18n parity + ratchet — the ratchet's `STYLE_BRACE_BASELINE` must still match exactly)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shared/ArtifactTable/ frontend/src/components/RequirementEditors/RequirementEditors.tsx frontend/src/i18n/locales/de.json frontend/src/i18n/locales/en.json frontend/src/test/ArtifactTableView.test.tsx
git commit -m "feat(table): mount the table view on the requirements page"
```

---

## Task 24: E2E — the guardrail is visible and enforced

**Files:**
- Create: `e2e/table-view-workflow-guardrail.spec.ts`
- Test: the spec itself

**Interfaces:**
- Consumes: the `data-testid`s of Tasks 17, 21, 22
- Produces: an end-to-end proof that status cannot be written from the table

- [ ] **Step 1: Write the failing test**

Create `e2e/table-view-workflow-guardrail.spec.ts`:

```ts
import { expect, test } from "@playwright/test";
import { login } from "./helpers/auth";

test.describe("Table view — workflow guardrail", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto("/requirements");
    await page.getByTestId("requirements-view-mode-toggle").click();
    await expect(page.getByTestId("artifact-table-view-Requirement")).toBeVisible();
  });

  test("a status cell is read-only and offers a separate transition action", async ({ page }) => {
    const firstRow = page.getByTestId(/^artifact-table-row-/).first();
    const rowId = (await firstRow.getAttribute("data-testid"))!.replace(
      "artifact-table-row-",
      "",
    );

    const statusCell = page.getByTestId(`artifact-table-cell-${rowId}-status`);
    await statusCell.click();
    await expect(page.getByTestId("inline-editor-input")).toHaveCount(0);
    await expect(page.getByTestId(`artifact-table-transition-${rowId}`)).toBeVisible();
  });

  test("the bulk edit dialog does not offer the status field", async ({ page }) => {
    const firstRow = page.getByTestId(/^artifact-table-row-/).first();
    const rowId = (await firstRow.getAttribute("data-testid"))!.replace(
      "artifact-table-row-",
      "",
    );

    await page.getByTestId(`artifact-table-select-${rowId}`).check();
    await page.getByTestId("bulk-edit-button").click();

    const options = page.getByTestId("bulk-edit-field-select").locator("option");
    await expect(options.filter({ hasText: /^status$/ })).toHaveCount(0);
  });

  test("a hand-crafted bulk update on status is rejected with 400", async ({ page, request }) => {
    const token = await page.evaluate(() => window.localStorage.getItem("access_token"));
    const workspaceId = await page.evaluate(() =>
      window.localStorage.getItem("active_workspace_id"),
    );
    const firstRow = page.getByTestId(/^artifact-table-row-/).first();
    const rowId = (await firstRow.getAttribute("data-testid"))!.replace(
      "artifact-table-row-",
      "",
    );

    const response = await request.patch("/api/v1/artifacts/bulk-update/", {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      data: {
        workspace_id: workspaceId,
        item_type: "Requirement",
        ids: [rowId],
        fields: { status: "approved" },
      },
    });

    expect(response.status()).toBe(400);
    expect((await response.json()).error.message).toContain("status");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd e2e && node node_modules/@playwright/test/cli.js test table-view-workflow-guardrail.spec.ts`
Expected: FAIL before Tasks 10/17/21 are merged (no toggle, no table). Use the local
`@playwright/test` cli directly — a stray root-level `node_modules/playwright` at a different
version makes every spec die at `test.describe()`.

- [ ] **Step 3: Write minimal implementation**

No production code. Adjust the spec to the repo's actual E2E conventions instead:
- `grep -rn "export async function login" e2e/` — use the existing login helper; if it lives
  elsewhere or takes arguments, adapt the import.
- `grep -rn "access_token\|active_workspace_id" frontend/src/api/client.ts frontend/src/context/` —
  auth is cookie-based on this stack, so if no bearer token is in `localStorage`, drop the
  `Authorization` header and let Playwright's shared storage state carry the auth cookie, adding
  the CSRF header the same way the other write-path specs do.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd e2e && node node_modules/@playwright/test/cli.js test table-view-workflow-guardrail.spec.ts`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add e2e/table-view-workflow-guardrail.spec.ts
git commit -m "test(table): prove the workflow guardrail end to end"
```

---

## Self-Review

**1. Spec coverage**

| Spec section | Covered by |
|---|---|
| §2 guardrail (no `editable:"workflow"` write, ever) | Tasks 4 (`WORKFLOW_OWNED_FALLBACK` subtracted from every adapter), 5 (`assert_no_workflow_owned_fields` + 8 unit tests), 6 (service-level 400 + no-partial-write proof), 10 (REST 400 proof), 13 (MCP proof), 17/21/22 (UI cannot even offer it), 24 (E2E) |
| §3.1 bulk update, adapter registry, hard 400, partial success | Tasks 4, 6, 10, 13 |
| §3.2 bulk transition through the workflow engine, per-item gates | Tasks 7, 10, 13 |
| §3.3 MCP `artifact.bulk_update` / `artifact.bulk_transition` | Task 13 |
| §4.1 type-aware filter DSL, 400 on unknown field/operator, multi-sort | Tasks 2, 3, 11 |
| §4.2 `UserTableViewState`, `SavedView`, visibility, REST, `saved_view.*` MCP | Tasks 8, 9, 12, 14 |
| §4.3 toggle, header filters, chips, sort/shift-sort, column picker, saved-view bar, inline edit, status action, bulk toolbar | Tasks 16–23 |
| §5 migration (additive, 2 tables, registry, routes, MCP tools) | Tasks 4, 8, 10–14 |
| §6 risks: new field type without operators; partial success visible; stale view fail-soft | Task 2 (`widget` → no operators, column not filterable), Task 21 (`bulk-result-summary` + per-item reasons), Tasks 9/16 (stale filters yield an empty list; a vanished column is dropped) |

Not covered, deliberately, and stated in *Scope decisions*: extended-attribute filtering/bulk-edit, Goal/MainGoal, column resize/drag-reorder/pinned column (the spec itself defers the last group), and the C8 migration of the 86 legacy `query_params.get()` sites (spec §6 excludes it explicitly).

**2. Placeholder scan** — no "TBD", no "TODO", no "similar to Task N", no "add error handling" without code. Every step names a file, a command and an expected result. Four steps deliberately end in a *verification command* rather than a guess, because the referenced symbol belongs to another spec's plan or to code that may drift: the `OptimisticLockError` import path (Task 6), the token names in `tokens.css` and `StatusBadge`'s prop (Task 17), the `ConfirmDialog`/`ModalDialogBase` prop names (Task 20), and the `pageHeader` actions shape plus the login/auth mechanics for E2E (Tasks 23, 24).

**3. Type consistency** — `BulkResult`/`BulkItemFailure` (Task 6) are consumed unchanged by Tasks 7, 10, 13 and mirrored in TS in Task 15. `TABLE_ITEM_TYPES` (Task 3) is the single item-type registry for Tasks 4, 6, 7. `ColumnSpec`/`TableFilters`/`TableSort` (Task 15) are the same shapes the backend DSL parses (Task 2) and the ones stored in both models (Task 8). `TableColumn` (Task 16) is produced once and consumed by Tasks 17, 18, 19, 21, 22, 23. `AttributeDefinitionEntry` mirrors spec 2's `definition_json.attributes[]` field-for-field.

**ID space, stated once because it is the classic trap here:** `ids[]` in both bulk endpoints, `TableRow.id`, and the row-level `data-testid`s all carry the **entity id** (`Requirement.id`, `Risk.id`, …) — the same id `update_X()` and `WorkflowFacade.transition` take. `TableRow.artifact_id` is the separate `pl_artifact` PK and is carried along only for trace-link navigation. Never mix them.

## OFFENE FRAGEN

1. **`AttributeDefinitionService.resolve()` does not exist yet.** The Attribut-Definition spec (§5) names only `validate_artifact_fields`; a read accessor for the resolved definition is implied by its REST endpoint but never named. This plan assumes `resolve(ctx, workspace_id, item_type) -> {"attributes": [...]}` and isolates the assumption in `application/attribute_definition_access.py` (Task 1) and `fieldComponents.ts` (Task 18) so a different name costs two one-line edits. **Not blocking** — but the two plans should agree on the name before Task 1 is implemented.
2. **Spec §4.1 cannot express a date/number range** (one constraint object holds one operator, yet `date` is documented as `gte, lte (Zeitraum)`). Resolved here by allowing a *list* of constraints per field, ANDed (Task 2). Since the Dokumentensicht spec consumes this format for `content_type="query"` sections, the extension should be confirmed rather than discovered later. **Not blocking**, decision documented.
3. **The spec's C8 framing does not match the code.** It says "10 `ordering_fields`/`search_fields`/`filterset_fields` against 86 manual `query_params.get(...)`" — but `django-filter` is not installed at all and `filterset_fields` appears nowhere; filtering is entirely hand-rolled (`_apply_list_query_params`, `rest_api/views.py:5270`) over in-memory service results. This changes nothing about the plan (the new DSL is a parallel, additive API either way), but any later C8 cleanup must not assume a DRF filter backend exists. **Not blocking.**
