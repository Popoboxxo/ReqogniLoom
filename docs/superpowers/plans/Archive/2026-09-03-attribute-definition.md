# Attribute Definition as a System Object Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the four half-finished field-configuration mechanisms and the seven hand-written artifact forms with one `AttributeDefinition` system object per `(item_type, preset)` — global with workspace override — that drives form rendering, interview elicitation, export and serializer validation from a single source.

**Architecture:** A new Layer-1 Django app `backend/attribute_definitions/` holds `GlobalAttributeDefinition` and `WorkspaceAttributeDefinition`, using the materialized-copy inheritance pattern already proven by `workflow.GlobalWorkflowDefinition` → `workflow.WorkflowEngineDefinition` (global edit propagates into every `is_customized=False` derived row; no merge-on-read on the form hot path). `application/attribute_definition_service.py` is the single Layer-2 facade; `rest_api/attribute_definition_views.py` and `mcp_server/tools/attribute_definition.py` are thin Layer-3 adapters that hold no ORM. On the frontend a single `shared/ArtifactForm/` renderer replaces the seven hand-written forms, driven by the resolved `definition_json.attributes[]` array, with a widget registry for the three non-field-shaped special cases.

**Tech Stack:** Django 5.2+ / DRF 3.15+ / PostgreSQL 16 (JSONB + Row-Level-Security) / pytest + pytest-django (backend) · React 18 + TypeScript 5.5 strict + Vite 5 + vitest + react-i18next (frontend) · Playwright (E2E)

**Spec:** docs/superpowers/specs/2026-09-03-attribute-definition-design.md

## Global Constraints

- New Django app is `backend/attribute_definitions/`, Layer 1, analogous to `backend/workflow/` — not spread across `persistence`/`application`.
- Inheritance form is **materialized copy**, not merge-on-read: every workspace holds a full copy of the global default; a global edit propagates (application layer, not schema) into every non-customized workspace row of the same `(item_type, preset)`.
- `GlobalAttributeDefinition` is unique on `(tenant, item_type, preset)`; `WorkspaceAttributeDefinition` is unique on `(tenant, workspace_id, item_type)`.
- `WorkspaceAttributeDefinition.preset` is **frozen at creation time**.
- The attribute schema keys are exactly: `name`, `kind`, `type`, `widget_key`, `fields`, `options`, `required`, `visible`, `locked`, `editable`, `section`, `order`, `label`, `help_text`, `default`, `validation`, `ai_elicit`, `export`, `audience`.
- `kind` is one of `core` | `extended`. `core` = Django model field, `extended` = value stored outside the model.
- `type` is one of `text` | `textarea` | `number` | `boolean` | `enum` | `multi-enum` | `date` | `reference` | `user` | `widget`.
- `widget_key` and `fields[]` are only valid when `type == "widget"`.
- `options[]` entries are `{value, label_de, label_en}`; required for `enum`/`multi-enum`.
- `editable` is `true` | `false` | `"workflow"`. `"workflow"` means changeable only through a workflow transition.
- `audience` is `"basic"` | `"expert"`, default `"basic"`. It controls **only** the default expand density in `ArtifactForm`; it is **not** a security or visibility boundary — that stays `visible`.
- `locked` defaults to `false`, is only permitted on `kind == "core"`, and is curated per type in the bootstrap script — never derived from `blank=False` by heuristic.
- For `locked == true`: `visible` is fixed `true`; `required` and `editable` are not changeable. A `PUT` changing any of those three for a locked attribute is rejected with 400. `order`, `section`, `label`, `help_text` stay changeable.
- For `kind == "core"`: only the meta-properties `required`, `visible`, `editable`, `section`, `order`, `label`, `help_text`, `default`, a subset of `options`, `ai_elicit`, `export` (and `audience`) may be changed. A `PUT` changing `name`, `type`, or the existence of a core attribute is rejected with 400.
- `section` is deliberately free text, not a fixed enum. `"general"`, `"classification"`, `"change_control"` are convention from the existing codebase, not a limit.
- Migration is **hard, without a coexistence phase**: after the data migration, `AttributeVisibilityConfig`, `CustomFieldDefinition`, their REST views/serializers and `application/attribute_visibility_service.py` are removed, not deprecated.
- `CustomFieldValue` keeps its values — see Decision D3 for the one forced schema change to it.
- `field_type` mapping in the migration is exactly: `text` → `text`, `number` → `number`, `dropdown` → `enum`.
- `required` is checked **only for fields the request actually sets or clears**; a save that does not touch a required field is never blocked (grandfathering for legacy data). Create checks all `required` fields.
- `validation` (`regex` | `min` | `max` | `length`) is checked for every field present in the request.
- Unknown `extended` fields in the payload are rejected with 400.
- Preset downgrade reuses the existing `presets.services.validate_downgrade` check — not a new one.
- Cache invalidation is per workspace, following the `presets/gate.py:_invalidate_workspace` pattern (reached through the public `application.cache_invalidation.invalidate_workspace_caches`).
- Form rollout order is fixed: **Risk, Issue** → **ADR, TestCase, Need, Architecture** → **Requirement last**. Each migrated form deletes its hand-written predecessor; no parallel operation.
- Parity policy: every capability that exists today in at least one of the seven forms must be available in the new renderer for **all ten types** — dirty warning on, delete-in-form present, status as select + transition buttons wherever a workflow exists, definition-driven visibility read. The migration is a unification upward, never a cut.
- Widget registry keys are exactly `risk_matrix_rpz` (fields `probability`, `impact`, `detection`), `markdown_tab_group` (fields `description`, `context`, `consequences`), `steps_editor` (field `steps`).
- The ten bootstrapped item types are exactly: `Requirement`, `StakeholderNeed`, `ArchitectureElement`, `TestCase`, `Adr`, `Risk`, `Issue`, `Goal`, `Icd`, `GlossaryTerm`.
- The three presets are exactly `minimal`, `standard`, `extended`.

---

## Preconditions and verified deviations from the spec

These were verified against the working tree on 2026-09-03 (branch `chore/archive-implemented-specs-plans`, spec read from `main`). Each one changes what a task must do; none of them blocks the plan.

### P1 — Ordering dependency on the Datenmodell-Konsolidierung spec (soft, mitigated)

The Datenmodell-Konsolidierung spec (§7) states its Phase 1 (status consolidation) must run **before** this plan's bootstrap migration, otherwise the bootstrap picks up the soon-to-be-dropped status columns as core attributes.

Verified current state: **that plan is not yet implemented.** `Requirement.status`, `Adr.status`, `Risk.status`, `Issue.status`, `Goal.status`, `MainGoal.status`, `ChangeRequest.status` all still exist as columns, and `Adr`/`Risk`/`Goal`/`MainGoal`/`Issue`/`ChangeRequest` still live in `backend/application/models.py` as plain `models.Model` (not `TenantScopedModel`).

**Mitigation built into this plan (Task 6):** the bootstrap introspector carries an explicit `EXCLUDED_MODEL_FIELDS` skip-list containing every column the consolidation will drop (`status`, `lifecycle_status`) plus the infrastructure columns, and **injects a synthetic `status` core attribute** per type instead of reading one from the model. The synthetic attribute is `kind=core`, `type=enum`, `editable="workflow"`, `locked=true`, `options=[]` (states come from the workflow definition at render time). That makes the bootstrap produce identical output before and after the consolidation, so the ordering dependency is neutralized rather than ignored.

**Still a real precondition:** `Adr`/`Risk`/`Issue`/`Goal` are imported from `application.models` today and from `persistence.models` after the consolidation. Task 6 therefore resolves models through `django.apps.apps.get_model` with a per-type app-label fallback list, so a moved model does not break the command.

### P2 — There is no `workflow.*` MCP tool group (spec §5 is wrong)

The spec says the MCP group should be built "analogous to the existing `workflow.*` group". Verified: `backend/mcp_server/tools/` contains no workflow group, and no tool name starting with `workflow.` is registered in `ToolRegistry._ensure_groups`. **Decision:** the pattern followed is `mcp_server/tools/custom_field.py` (thin `BaseToolGroup` subclass with a `_TOOL_MAP`), which is the closest live analogue for a configuration-object tool group. Recorded as Decision D5.

### P3 — `version` is already inherited (spec §3 declares it redundantly)

The spec's model sketch declares `version = models.IntegerField(default=1)` on both models. Verified: `TenantScopedModel` → `AuditableModel` already provides `version` (optimistic-lock counter, alias `lock_version`). `GlobalWorkflowDefinition` correctly does **not** redeclare it. Redeclaring it in a subclass is a Django field clash. **Decision:** rely on the inherited field. Recorded as Decision D2.

### P4 — Ratchets that fail if this plan is implemented naively

- `backend/rest_api/tests/test_architecture.py::test_no_new_direct_orm_access` — a new file under `backend/rest_api/` gets a cap of **0** `.objects.` / `.unscoped.` lines. The new REST views must hold no ORM.
- The same file's `test_no_new_direct_orm_access_mcp_tools` applies to `backend/mcp_server/tools/`.
- `frontend/src/test/ui-ratchet.test.ts` has **two** assertions on inline styles: `toBeLessThanOrEqual(STYLE_BRACE_BASELINE)` and `toBe(STYLE_BRACE_BASELINE)` (currently `1015`). Deleting a hand-written form lowers the real count, which fails the **monotonic** assertion unless `STYLE_BRACE_BASELINE` is lowered in the same commit. Every form-rollout task therefore has an explicit "re-measure and lower the baseline" step.
- `backend/mcp_server/tests/test_mcp_workspace_scope.py::TestWorkspaceScopeCoverage::test_every_read_tool_is_classified` — every new **read** tool must either declare `workspace_id` as *required* in its `inputSchema` or be listed in one of the three classification sets.
- `backend/mcp_server/tool_registry.py::_READ_ONLY_TOOL_NAMES` is fail-closed: a new read tool not listed there is RBAC-gated as a write tool.
- `frontend/src/test/i18n-parity.test.ts` — every new key must exist in both `de.json` and `en.json`. Keys must be **nested objects**, never dotted flat keys (`keySeparator` is `"."`, so `"a.b": "x"` inside a locale object never resolves).

### P5 — `AuditEntry.op` is a closed choice list

`AuditEntry.OP_CHOICES` is validated via `full_clean()` and an undeclared `operation=` string 500s the service *after* its mutation succeeded (issue #265). This plan uses only the already-declared `AuditEntry.OP_UPDATE` (`"update"`) for definition edits and resets. **No new op choice is introduced.**

### P6 — New `TenantScopedModel` tables need their own RLS migration

`persistence/migrations/0003_rls_policies.py` does not cover other apps' tables; `workflow/migrations/0015_workflow_rls_policies.py` is the per-app pattern (ENABLE + FORCE ROW LEVEL SECURITY + one `ALL` policy keyed on `app.current_tenant`). Task 1 ships the equivalent for the two new tables. Without it the tables ship unprotected.

---

## Open questions

**OFFENE FRAGE — none blocking.** Two spec ambiguities were resolved by explicit decision (D3 and D6 below) rather than by guessing; both are called out in the final report because they change behaviour the spec describes differently.

**User confirmation (2026-09-06, ahead of execution, asked while Datenmodell-Konsolidierung was still finishing):** D3 and D6 both confirmed as written — no changes requested. This plan is clear to execute once Datenmodell-Konsolidierung reaches a clean final review, per the standing 11-plan sequencing instruction.

---

## Decisions

**D1 — `AttributeDefinitionService.validate_artifact_fields` keeps the spec's exact 5-argument signature.** Create-vs-update semantics are carried by `existing is None` (create) rather than by a sixth flag, because the spec, the Tabellenansicht spec (§3.1) and the Rollenbasierte-Sichten spec all quote the 5-argument form verbatim.

**D2 — `version` is the inherited `AuditableModel.version`,** not a redeclared field (see P3). Both stores bump it explicitly on every persist, so the REST/MCP payloads still expose a monotonically increasing `version` as the spec's §9 requires.

**D3 — `CustomFieldValue.definition` (FK) becomes `attribute_name` (CharField).** The spec says "`CustomFieldValue` stays unchanged (values, not definition)" *and* "`CustomFieldDefinition` … is removed (not just deprecated)". Those two are not simultaneously satisfiable: `CustomFieldValue.definition` is a `ForeignKey` to `CustomFieldDefinition`, so dropping the target table orphans the column. Resolution: the values are preserved, the *link* changes from a row FK to the attribute `name` that now lives in `definition_json`. Uniqueness moves from `(definition, artifact)` to `(artifact, attribute_name)`. This is the minimum change that satisfies "definition lives only in the JSON" while losing no values.

**D4 — The resolved definition is cached in `django.core.cache` under `reqogniloom:attribute-def:{workspace_id}:{item_type}`,** and `attribute_def_cache_key` is added to `application/cache_invalidation.py::_workspace_keys`. This reuses the existing cross-worker invalidation instead of adding a fourth module-level dict.

**D5 — The MCP group follows `mcp_server/tools/custom_field.py`,** because the `workflow.*` group the spec names does not exist (see P2).

**D6 — The bootstrap injects a synthetic `status` core attribute instead of introspecting a status column** (see P1). Consequence: the bootstrap output is stable across the Datenmodell-Konsolidierung migration. The attribute carries a single placeholder option `{"value": "__workflow__", ...}` rather than a real state list — `normalize_attribute` rejects an `enum` with an empty `options` list, and the concrete reachable states come from the workflow definition, which is already their single source of truth. The renderer never draws that option: an `editable: "workflow"` attribute renders as `WorkflowStatusEditor`, not as a select (Task 18, rule 3).

---

## File Structure

### Backend — new app `backend/attribute_definitions/` (Layer 1)

| File | Responsibility |
|---|---|
| `__init__.py` | empty package marker |
| `apps.py` | `AttributeDefinitionsConfig` (app label `attribute_definitions`) |
| `models.py` | `GlobalAttributeDefinition`, `WorkspaceAttributeDefinition` — nothing else |
| `schema.py` | Pure, DB-free attribute-schema vocabulary + validation: `ATTRIBUTE_TYPES`, `ATTRIBUTE_KINDS`, `EDITABLE_VALUES`, `AUDIENCE_VALUES`, `CORE_EDITABLE_META_PROPERTIES`, `LOCKED_IMMUTABLE_PROPERTIES`, `WIDGET_KEYS`, `AttributeSchemaError`, `normalize_attribute`, `validate_definition_json`, `validate_meta_only_change` |
| `global_definition_store.py` | `GlobalAttributeDefinitionStore` — CRUD on the tenant-wide default + propagation into non-customized derived rows |
| `workspace_definition_store.py` | `WorkspaceAttributeDefinitionStore` — resolve (materialize-on-first-read), update (sets `is_customized`), reset |
| `field_validation.py` | `FieldValidationError`, `validate_values(attributes, changed_fields, existing)` — the pure rule engine behind `validate_artifact_fields` |
| `management/__init__.py`, `management/commands/__init__.py` | package markers |
| `management/commands/bootstrap_attribute_definitions.py` | model introspection → initial `GlobalAttributeDefinition` rows (core attributes only), idempotent, `--sync-new-fields` mode |
| `migrations/0001_initial.py` | the two tables |
| `migrations/0002_attribute_definition_rls_policies.py` | RLS policies for both tables |
| `migrations/0003_migrate_legacy_field_config.py` | data migration from `AttributeVisibilityConfig` + `CustomFieldDefinition` |
| `tests/test_schema.py`, `tests/test_global_store.py`, `tests/test_workspace_store.py`, `tests/test_field_validation.py`, `tests/test_bootstrap_command.py`, `tests/test_legacy_migration.py`, `tests/test_rls.py` | per-module tests |

### Backend — changed files

| File | Change |
|---|---|
| `backend/reqogniloom/settings.py:205-224` | add `"attribute_definitions"` to `REQFLOW_APPS` after `"workflow"` |
| `backend/application/attribute_definition_service.py` (new) | `AttributeDefinitionService(ServiceBase)` — the single Layer-2 facade |
| `backend/application/cache_invalidation.py:66-82` | add `attribute_def_cache_key` + include it in `_workspace_keys` |
| `backend/rest_api/attribute_definition_views.py` (new) | 4 `APIView`s, no ORM |
| `backend/rest_api/urls.py` | register the 4 routes; remove the `attribute-visibility-configs` router entry and the 3 custom-field routes |
| `backend/rest_api/views.py` | wire `validate_artifact_fields` into the create/update path of the 9 workflow-backed ViewSets; delete `AttributeVisibilityConfigViewSet` + the 3 custom-field views |
| `backend/rest_api/serializers.py` | delete `AttributeVisibilityConfigSerializer`, `CustomFieldDefinitionSerializer` |
| `backend/mcp_server/tools/attribute_definition.py` (new) | `AttributeDefinitionToolGroup` — 4 tools, no ORM |
| `backend/mcp_server/tool_registry.py` | register the `attribute_definition` prefix; add the 2 read tools to `_READ_ONLY_TOOL_NAMES` |
| `backend/mcp_server/workspace_scope.py` | add `attribute_definition.list` to `TENANT_SCOPED_READ_TOOLS` |
| `backend/mcp_server/tools/custom_field.py` | delete (its service is gone) |
| `backend/application/custom_field_service.py` | delete |
| `backend/application/attribute_visibility_service.py` | delete |
| `backend/application/interview_protocol.py` | `get_protocol` derives phases/fields from `ai_elicit` when a definition exists |
| `backend/application/requirement_bundle_service.py:86-104` | `REQUIREMENT_ALL_FIELDS` becomes a fallback; field list resolved from `export=true` |
| `backend/persistence/models.py:1656-1786` | delete `AttributeVisibilityConfig` and `CustomFieldDefinition`; change `CustomFieldValue.definition` → `attribute_name` |

### Frontend — new files

| File | Responsibility |
|---|---|
| `frontend/src/api/attribute-definitions.ts` | `attributeDefinitionsApi` + the `AttributeSpec` / `AttributeDefinition` types |
| `frontend/src/components/shared/ArtifactForm/ArtifactForm.tsx` | the renderer: sections, order, audience collapse, dirty warning, delete, save |
| `frontend/src/components/shared/ArtifactForm/ArtifactForm.module.css` | all styling (no inline `style={{`) |
| `frontend/src/components/shared/ArtifactForm/fields/*.tsx` | `TextField`, `TextArea`, `EnumSelect`, `MultiEnum`, `BooleanToggle`, `DateField`, `ReferencePicker`, `UserPicker` |
| `frontend/src/components/shared/ArtifactForm/widgets/*.tsx` | `RiskMatrixRpz`, `MarkdownTabGroup`, `StepsEditor` |
| `frontend/src/components/shared/ArtifactForm/widget-registry.ts` | `WIDGET_REGISTRY` map from `widget_key` to component |
| `frontend/src/components/shared/ArtifactForm/index.ts` | named re-exports |
| `frontend/src/components/AttributeEditor/AttributeEditorPage.tsx` | `scope?: "workspace" \| "global"` editor page |
| `frontend/src/components/AttributeEditor/AttributeList.tsx` | section + attribute list with drag reorder / cross-section move |
| `frontend/src/components/AttributeEditor/AttributeInspector.tsx` | per-attribute meta-property editor incl. the `audience` toggle |
| `frontend/src/components/AttributeEditor/AttributeEditor.module.css` | styling |
| `frontend/src/components/AttributeEditor/index.ts` | named re-exports |

### Frontend — changed / deleted files

| File | Change |
|---|---|
| `frontend/src/components/NavigationShell/NavigationShell.tsx` | add `/attributes` and `/attributes/:entityType` routes |
| `frontend/src/components/SystemSettings/SystemSettings.tsx` | add the global Attribute-Defaults tab |
| `frontend/src/components/WorkspaceSettings/*` | add the workspace Attribute-Override tab |
| `frontend/src/i18n/locales/de.json`, `en.json` | new `attributes.*` and `artifactForm.*` key trees |
| `frontend/src/test/ui-ratchet.test.ts:335` | `STYLE_BRACE_BASELINE` lowered once per form-rollout task |
| `frontend/src/api/index.ts` | export `attributeDefinitionsApi`; drop `attributeVisibilityApi`, `customFieldsApi` |
| `frontend/src/api/attribute-visibility.ts`, `frontend/src/api/custom-fields.ts` | delete |
| `frontend/src/components/AdminDialog/AttributeVisibilityAdmin.tsx` | delete |
| `frontend/src/components/shared/CustomFieldsEditor.tsx`, `ArtifactCustomFields.tsx`, `CustomFieldsDisplay.tsx` | delete (subsumed by the renderer) |
| `frontend/src/components/{RiskEditors/RiskForm,IssueEditors/IssueForm,AdrEditors/AdrForm,TestCaseEditors/TestCaseForm,NeedsEditors/NeedForm,ArchitectureEditors/ArchitectureForm,RequirementEditors/RequirementForm}.tsx` | delete, one per rollout task |

---

## Phase A — Backend foundation

### Task 1: New app, models, migrations, RLS

**Files:**
- Create: `backend/attribute_definitions/__init__.py`
- Create: `backend/attribute_definitions/apps.py`
- Create: `backend/attribute_definitions/models.py`
- Create: `backend/attribute_definitions/migrations/__init__.py`
- Create: `backend/attribute_definitions/migrations/0001_initial.py` (generated)
- Create: `backend/attribute_definitions/migrations/0002_attribute_definition_rls_policies.py`
- Create: `backend/attribute_definitions/tests/__init__.py`
- Test: `backend/attribute_definitions/tests/test_models.py`
- Test: `backend/attribute_definitions/tests/test_rls.py`
- Modify: `backend/reqogniloom/settings.py:205-224` (add app to `REQFLOW_APPS`)

**Interfaces:**
- Consumes: `persistence.models.TenantScopedModel` (provides `id`, `tenant`, `version`, `created_at`, `modified_at`, `objects`, `unscoped`).
- Produces: `attribute_definitions.models.GlobalAttributeDefinition` (fields `item_type: str`, `preset: str`, `definition_json: dict`; table `ad_global_definition`); `attribute_definitions.models.WorkspaceAttributeDefinition` (fields `workspace_id: UUID`, `item_type: str`, `preset: str`, `definition_json: dict`, `source_global: FK|None`, `is_customized: bool`; table `ad_workspace_definition`, reverse name `derived_definitions`).

- [ ] **Step 1: Write the failing test**

Create `backend/attribute_definitions/tests/__init__.py` (empty) and `backend/attribute_definitions/tests/test_models.py`:

```python
"""Model-level contract for the two AttributeDefinition tables."""
from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, transaction

from attribute_definitions.models import (
    GlobalAttributeDefinition,
    WorkspaceAttributeDefinition,
)
from persistence.models import Tenant


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="t-attr", slug=f"t-{uuid.uuid4().hex[:8]}")


@pytest.mark.django_db
def test_global_is_unique_per_tenant_item_type_preset(tenant: Tenant) -> None:
    GlobalAttributeDefinition.unscoped.create(
        tenant_id=tenant.id, item_type="Requirement", preset="standard",
        definition_json={"attributes": []},
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            GlobalAttributeDefinition.unscoped.create(
                tenant_id=tenant.id, item_type="Requirement", preset="standard",
                definition_json={"attributes": []},
            )


@pytest.mark.django_db
def test_global_allows_same_item_type_in_another_preset(tenant: Tenant) -> None:
    for preset in ("minimal", "standard", "extended"):
        GlobalAttributeDefinition.unscoped.create(
            tenant_id=tenant.id, item_type="Requirement", preset=preset,
            definition_json={"attributes": []},
        )
    assert GlobalAttributeDefinition.unscoped.filter(tenant_id=tenant.id).count() == 3


@pytest.mark.django_db
def test_workspace_is_unique_per_tenant_workspace_item_type(tenant: Tenant) -> None:
    ws = uuid.uuid4()
    WorkspaceAttributeDefinition.unscoped.create(
        tenant_id=tenant.id, workspace_id=ws, item_type="Risk", preset="standard",
        definition_json={"attributes": []},
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            WorkspaceAttributeDefinition.unscoped.create(
                tenant_id=tenant.id, workspace_id=ws, item_type="Risk",
                preset="extended", definition_json={"attributes": []},
            )


@pytest.mark.django_db
def test_deleting_the_global_nulls_the_link_but_keeps_the_override(tenant: Tenant) -> None:
    """SET_NULL: a global delete must never cascade into a live workspace row."""
    g = GlobalAttributeDefinition.unscoped.create(
        tenant_id=tenant.id, item_type="Issue", preset="standard",
        definition_json={"attributes": []},
    )
    w = WorkspaceAttributeDefinition.unscoped.create(
        tenant_id=tenant.id, workspace_id=uuid.uuid4(), item_type="Issue",
        preset="standard", definition_json={"attributes": []}, source_global=g,
        is_customized=True,
    )
    g.delete()
    w.refresh_from_db()
    assert w.source_global_id is None
    assert w.is_customized is True


@pytest.mark.django_db
def test_version_is_inherited_and_starts_at_one(tenant: Tenant) -> None:
    """P3/D2: version comes from AuditableModel; it is never redeclared."""
    g = GlobalAttributeDefinition.unscoped.create(
        tenant_id=tenant.id, item_type="Goal", preset="minimal",
        definition_json={"attributes": []},
    )
    assert g.version == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest attribute_definitions/tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'attribute_definitions'`

- [ ] **Step 3: Create the app package and models**

Create `backend/attribute_definitions/__init__.py` (empty file).

Create `backend/attribute_definitions/apps.py`:

```python
"""AttributeDefinition app — Layer 1, analogous to ``backend/workflow/``."""
from __future__ import annotations

from django.apps import AppConfig


class AttributeDefinitionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "attribute_definitions"
    verbose_name = "Attribute Definitions"
```

Create `backend/attribute_definitions/models.py`:

```python
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
```

Create `backend/attribute_definitions/migrations/__init__.py` (empty file).

- [ ] **Step 4: Register the app**

In `backend/reqogniloom/settings.py`, inside `REQFLOW_APPS`, insert directly after the `"workflow",` line:

```python
    "attribute_definitions",  # AttributeDefinition system object (Layer 1)
```

- [ ] **Step 5: Generate the schema migration**

Run: `docker compose exec backend python manage.py makemigrations attribute_definitions --name initial`
Expected: creates `backend/attribute_definitions/migrations/0001_initial.py` with both `CreateModel` operations.

- [ ] **Step 6: Write the RLS policy migration**

Create `backend/attribute_definitions/migrations/0002_attribute_definition_rls_policies.py`:

```python
"""COMP-PL-006 RLSPolicyEnforcer — RLS for the ``ad_*`` AttributeDefinition tables.

Both tables are ``TenantScopedModel`` subclasses and must not ship without a
policy (Systemaudit 2026-08-27, P0 finding #2). Policy semantics are
byte-identical to ``persistence/0003_rls_policies.py`` and
``workflow/0015_workflow_rls_policies.py``: ENABLE + FORCE ROW LEVEL SECURITY
plus one ``ALL`` policy keyed on the session variable ``app.current_tenant``.
An unset/empty setting matches no rows.

``GlobalAttributeDefinition`` is "global" only in the sense of
tenant-wide-per-(item_type, preset); it still carries a per-tenant
``tenant_id``, so the standard policy applies unchanged.
"""
from __future__ import annotations

from django.db import migrations

_TENANT_TABLES = [
    "ad_global_definition",
    "ad_workspace_definition",
]


def _enable_sql() -> str:
    parts = []
    for table in _TENANT_TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;\n"
            f"CREATE POLICY {policy} ON {table}\n"
            f"    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)\n"
            f"    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);"
        )
    return "\n".join(parts)


def _disable_sql() -> str:
    parts = []
    for table in _TENANT_TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"DROP POLICY IF EXISTS {policy} ON {table};\n"
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
        )
    return "\n".join(parts)


class Migration(migrations.Migration):

    dependencies = [
        ("attribute_definitions", "0001_initial"),
        ("persistence", "0003_rls_policies"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
```

- [ ] **Step 7: Write the RLS test**

Create `backend/attribute_definitions/tests/test_rls.py`:

```python
"""RLS isolation for the two ad_* tables (REQ-L2-PL-010)."""
from __future__ import annotations

import uuid

import pytest

from attribute_definitions.models import GlobalAttributeDefinition
from auth_tenancy.context import TenantContext
from persistence.models import Tenant


@pytest.mark.django_db(transaction=True)
def test_tenant_context_scopes_global_definitions() -> None:
    t1 = Tenant.objects.create(name="t1", slug=f"t1-{uuid.uuid4().hex[:8]}")
    t2 = Tenant.objects.create(name="t2", slug=f"t2-{uuid.uuid4().hex[:8]}")
    GlobalAttributeDefinition.unscoped.create(
        tenant_id=t1.id, item_type="Requirement", preset="standard",
        definition_json={"attributes": []},
    )
    GlobalAttributeDefinition.unscoped.create(
        tenant_id=t2.id, item_type="Requirement", preset="standard",
        definition_json={"attributes": []},
    )
    try:
        TenantContext.set_tenant(t1.id)
        assert GlobalAttributeDefinition.objects.count() == 1
        TenantContext.set_tenant(t2.id)
        assert GlobalAttributeDefinition.objects.count() == 1
    finally:
        TenantContext.clear()
```

- [ ] **Step 8: Run the migrations and the tests**

Run: `docker compose exec backend python manage.py migrate attribute_definitions`
Then: `docker compose exec backend pytest attribute_definitions/tests/ -v`
Expected: PASS (6 tests)

- [ ] **Step 9: Commit**

```bash
git add backend/attribute_definitions backend/reqogniloom/settings.py
git commit -m "feat(attribute-definitions): add app, models and RLS policies"
```

---

### Task 2: Attribute schema vocabulary and validation

**Files:**
- Create: `backend/attribute_definitions/schema.py`
- Test: `backend/attribute_definitions/tests/test_schema.py`

**Interfaces:**
- Consumes: nothing (pure module, no Django imports — importable from data migrations and tests without a settings module).
- Produces:
  - `ATTRIBUTE_KINDS: frozenset[str]` = `{"core","extended"}`
  - `ATTRIBUTE_TYPES: frozenset[str]` = `{"text","textarea","number","boolean","enum","multi-enum","date","reference","user","widget"}`
  - `EDITABLE_VALUES: frozenset[Any]` = `{True, False, "workflow"}`
  - `AUDIENCE_VALUES: frozenset[str]` = `{"basic","expert"}`
  - `WIDGET_KEYS: frozenset[str]` = `{"risk_matrix_rpz","markdown_tab_group","steps_editor"}`
  - `CORE_EDITABLE_META_PROPERTIES: frozenset[str]`, `LOCKED_IMMUTABLE_PROPERTIES: frozenset[str]` = `{"visible","required","editable"}`, `ALLOWED_KEYS: frozenset[str]`
  - `class AttributeSchemaError(ValueError)` with `errors: list[str]`
  - `normalize_attribute(raw: dict) -> dict`
  - `validate_definition_json(payload: dict) -> dict`
  - `validate_meta_only_change(old_attributes: list[dict], new_attributes: list[dict]) -> None`

- [ ] **Step 1: Write the failing test**

Create `backend/attribute_definitions/tests/test_schema.py`:

```python
"""Pure schema-vocabulary tests — no DB, no Django settings needed."""
from __future__ import annotations

import pytest

from attribute_definitions.schema import (
    AttributeSchemaError,
    normalize_attribute,
    validate_definition_json,
    validate_meta_only_change,
)


def _core(name: str, **over) -> dict:
    base = {"name": name, "kind": "core", "type": "text", "section": "general", "order": 0}
    base.update(over)
    return base


def _locked_status() -> dict:
    return _core(
        "status",
        type="enum",
        options=[{"value": "draft", "label_de": "Entwurf", "label_en": "Draft"}],
        locked=True,
        editable="workflow",
    )


def test_normalize_fills_every_documented_default() -> None:
    out = normalize_attribute({"name": "title", "kind": "core", "type": "text"})
    assert out == {
        "name": "title", "kind": "core", "type": "text", "widget_key": None,
        "fields": [], "options": [], "required": False, "visible": True,
        "locked": False, "editable": True, "section": "general", "order": 0,
        "label": {"de": "", "en": ""}, "help_text": {"de": "", "en": ""},
        "default": None, "validation": {}, "ai_elicit": False, "export": False,
        "audience": "basic",
    }


def test_unknown_key_is_rejected() -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        normalize_attribute({"name": "x", "kind": "core", "type": "text", "colour": "red"})
    assert "colour" in " ".join(exc.value.errors)


def test_unknown_type_is_rejected() -> None:
    with pytest.raises(AttributeSchemaError):
        normalize_attribute({"name": "x", "kind": "core", "type": "richtext"})


def test_enum_without_options_is_rejected() -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        normalize_attribute({"name": "x", "kind": "core", "type": "enum"})
    assert "options" in " ".join(exc.value.errors)


def test_option_entries_need_value_and_both_labels() -> None:
    with pytest.raises(AttributeSchemaError):
        normalize_attribute({"name": "x", "kind": "core", "type": "enum",
                             "options": [{"value": "a", "label_de": "A"}]})


def test_widget_key_only_allowed_for_type_widget() -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        normalize_attribute({"name": "x", "kind": "core", "type": "text",
                             "widget_key": "steps_editor"})
    assert "widget_key" in " ".join(exc.value.errors)


def test_type_widget_requires_a_registered_widget_key_and_fields() -> None:
    with pytest.raises(AttributeSchemaError):
        normalize_attribute({"name": "x", "kind": "core", "type": "widget",
                             "widget_key": "not_registered", "fields": ["a"]})
    ok = normalize_attribute({"name": "x", "kind": "core", "type": "widget",
                              "widget_key": "risk_matrix_rpz",
                              "fields": ["probability", "impact", "detection"]})
    assert ok["fields"] == ["probability", "impact", "detection"]


def test_locked_is_only_allowed_on_core() -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        normalize_attribute({"name": "x", "kind": "extended", "type": "text",
                             "locked": True})
    assert "locked" in " ".join(exc.value.errors)


def test_locked_forces_visible_true() -> None:
    raw = _locked_status()
    raw["visible"] = False
    assert normalize_attribute(raw)["visible"] is True


def test_editable_accepts_workflow_literal_and_rejects_others() -> None:
    assert normalize_attribute(_core("s", editable="workflow"))["editable"] == "workflow"
    with pytest.raises(AttributeSchemaError):
        normalize_attribute(_core("s", editable="sometimes"))


def test_audience_defaults_to_basic_and_rejects_other_values() -> None:
    assert normalize_attribute(_core("a"))["audience"] == "basic"
    assert normalize_attribute(_core("a", audience="expert"))["audience"] == "expert"
    with pytest.raises(AttributeSchemaError):
        normalize_attribute(_core("a", audience="admin"))


def test_validation_rejects_unknown_rule_keys() -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        normalize_attribute(_core("a", validation={"startswith": "X"}))
    assert "startswith" in " ".join(exc.value.errors)


def test_validate_definition_json_rejects_duplicate_names() -> None:
    with pytest.raises(AttributeSchemaError) as exc:
        validate_definition_json({"attributes": [_core("title"), _core("title")]})
    assert "title" in " ".join(exc.value.errors)


def test_validate_definition_json_sorts_by_section_then_order_then_name() -> None:
    out = validate_definition_json({"attributes": [
        _core("b", section="zzz", order=1),
        _core("a", section="general", order=5),
        _core("c", section="general", order=1),
    ]})
    assert [a["name"] for a in out["attributes"]] == ["c", "a", "b"]


def test_meta_only_change_rejects_renaming_a_core_attribute() -> None:
    old = [normalize_attribute(_core("title"))]
    new = [normalize_attribute(_core("headline"))]
    with pytest.raises(AttributeSchemaError) as exc:
        validate_meta_only_change(old, new)
    assert "title" in " ".join(exc.value.errors)


def test_meta_only_change_rejects_retyping_or_dropping_a_core_attribute() -> None:
    old = [normalize_attribute(_core("title")), normalize_attribute(_core("uid"))]
    with pytest.raises(AttributeSchemaError):
        validate_meta_only_change(old, [normalize_attribute(_core("title", type="textarea")),
                                        normalize_attribute(_core("uid"))])
    with pytest.raises(AttributeSchemaError):
        validate_meta_only_change(old, [normalize_attribute(_core("title"))])


def test_meta_only_change_allows_a_new_extended_attribute() -> None:
    old = [normalize_attribute(_core("title"))]
    new = old + [normalize_attribute({"name": "sap_id", "kind": "extended", "type": "text"})]
    validate_meta_only_change(old, new)


def test_meta_only_change_rejects_a_new_core_attribute() -> None:
    old = [normalize_attribute(_core("title"))]
    new = old + [normalize_attribute(_core("smuggled"))]
    with pytest.raises(AttributeSchemaError):
        validate_meta_only_change(old, new)


def test_meta_only_change_allows_core_meta_properties() -> None:
    old = [normalize_attribute(_core("title"))]
    new = [normalize_attribute(_core("title", required=True, section="classification",
                                     order=9, audience="expert", ai_elicit=True,
                                     export=True))]
    validate_meta_only_change(old, new)


def test_meta_only_change_rejects_touching_locked_visible_required_editable() -> None:
    old = [normalize_attribute(_locked_status())]
    for prop, value in (("required", True), ("editable", True), ("visible", False)):
        changed = _locked_status()
        changed[prop] = value
        with pytest.raises(AttributeSchemaError) as exc:
            validate_meta_only_change(old, [normalize_attribute(changed)])
        assert "status" in " ".join(exc.value.errors)


def test_meta_only_change_allows_cosmetics_on_a_locked_attribute() -> None:
    old = [normalize_attribute(_locked_status())]
    moved = _locked_status()
    moved.update(section="header", order=99, label={"de": "Zustand", "en": "State"})
    validate_meta_only_change(old, [normalize_attribute(moved)])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest attribute_definitions/tests/test_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'attribute_definitions.schema'`

- [ ] **Step 3: Write the implementation**

Create `backend/attribute_definitions/schema.py`:

```python
"""Attribute-schema vocabulary and validation (spec section 3.1).

Deliberately free of Django imports so it can be used from data migrations,
from the pure field-validation engine and from tests without a settings module.

The entry contract of ``definition_json["attributes"][i]`` is the published
interface consumed by the form renderer, the interview protocol, the export
service and the table view; every key below is part of it.
"""
from __future__ import annotations

from typing import Any, Iterable

ATTRIBUTE_KINDS: frozenset[str] = frozenset({"core", "extended"})

ATTRIBUTE_TYPES: frozenset[str] = frozenset(
    {
        "text", "textarea", "number", "boolean", "enum", "multi-enum",
        "date", "reference", "user", "widget",
    }
)

#: ``"workflow"`` means: changeable only through a workflow transition.
EDITABLE_VALUES: frozenset[Any] = frozenset({True, False, "workflow"})

AUDIENCE_VALUES: frozenset[str] = frozenset({"basic", "expert"})

#: Registered widget keys (spec section 6.3). Deliberately an open extension
#: point: a new special case adds a key here and a component in the frontend
#: registry rather than weakening the renderer contract.
WIDGET_KEYS: frozenset[str] = frozenset(
    {"risk_matrix_rpz", "markdown_tab_group", "steps_editor"}
)

#: The only properties an admin may change on a ``kind="core"`` attribute.
#: ``name``/``type``/existence are fixed by the Django model.
CORE_EDITABLE_META_PROPERTIES: frozenset[str] = frozenset(
    {
        "required", "visible", "editable", "section", "order", "label",
        "help_text", "default", "options", "ai_elicit", "export", "audience",
    }
)

#: Properties that may never change on a ``locked=True`` attribute.
LOCKED_IMMUTABLE_PROPERTIES: frozenset[str] = frozenset(
    {"visible", "required", "editable"}
)

_ENUM_TYPES = frozenset({"enum", "multi-enum"})

_DEFAULTS: dict[str, Any] = {
    "widget_key": None,
    "fields": [],
    "options": [],
    "required": False,
    "visible": True,
    "locked": False,
    "editable": True,
    "section": "general",
    "order": 0,
    "label": {"de": "", "en": ""},
    "help_text": {"de": "", "en": ""},
    "default": None,
    "validation": {},
    "ai_elicit": False,
    "export": False,
    "audience": "basic",
}

_REQUIRED_KEYS = ("name", "kind", "type")

ALLOWED_KEYS: frozenset[str] = frozenset(_REQUIRED_KEYS) | frozenset(_DEFAULTS)

_VALIDATION_KEYS = frozenset({"regex", "min", "max", "length"})


class AttributeSchemaError(ValueError):
    """Raised when an attribute entry or a definition payload is malformed."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def _label_dict(value: Any, key: str, errors: list[str]) -> dict[str, str]:
    if not isinstance(value, dict):
        errors.append(f"'{key}' must be an object with 'de' and 'en' keys")
        return {"de": "", "en": ""}
    extra = sorted(set(value) - {"de", "en"})
    if extra:
        errors.append(f"'{key}' has unknown language key(s): {', '.join(extra)}")
    return {"de": str(value.get("de", "")), "en": str(value.get("en", ""))}


def _normalize_options(raw: Any, errors: list[str]) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        errors.append("'options' must be a list")
        return []
    out: list[dict[str, str]] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            errors.append(f"options[{index}] must be an object")
            continue
        missing = [k for k in ("value", "label_de", "label_en") if not entry.get(k)]
        if missing:
            errors.append(f"options[{index}] is missing {', '.join(missing)}")
            continue
        extra = sorted(set(entry) - {"value", "label_de", "label_en"})
        if extra:
            errors.append(f"options[{index}] has unknown key(s): {', '.join(extra)}")
            continue
        out.append(
            {
                "value": str(entry["value"]),
                "label_de": str(entry["label_de"]),
                "label_en": str(entry["label_en"]),
            }
        )
    return out


def normalize_attribute(raw: dict[str, Any]) -> dict[str, Any]:
    """Return *raw* with every documented key present, or raise.

    The returned dict is a new object; *raw* is never mutated.

    Raises:
        AttributeSchemaError: any structural violation; ``.errors`` lists all
            of them at once so a UI can show them together.
    """
    if not isinstance(raw, dict):
        raise AttributeSchemaError(["attribute entry must be an object"])

    errors: list[str] = []
    unknown = sorted(set(raw) - ALLOWED_KEYS)
    if unknown:
        errors.append(f"unknown key(s): {', '.join(unknown)}")
    for key in _REQUIRED_KEYS:
        if not raw.get(key):
            errors.append(f"'{key}' is required")
    if errors:
        raise AttributeSchemaError(errors)

    out: dict[str, Any] = dict(_DEFAULTS)
    out["name"] = str(raw["name"])
    out["kind"] = str(raw["kind"])
    out["type"] = str(raw["type"])

    if out["kind"] not in ATTRIBUTE_KINDS:
        errors.append(f"'kind' must be one of {sorted(ATTRIBUTE_KINDS)}")
    if out["type"] not in ATTRIBUTE_TYPES:
        errors.append(f"'type' must be one of {sorted(ATTRIBUTE_TYPES)}")

    for key in ("required", "visible", "locked", "ai_elicit", "export"):
        if key in raw:
            if not isinstance(raw[key], bool):
                errors.append(f"'{key}' must be a boolean")
            else:
                out[key] = raw[key]

    if "editable" in raw:
        if raw["editable"] not in EDITABLE_VALUES:
            errors.append("'editable' must be true, false or \"workflow\"")
        else:
            out["editable"] = raw["editable"]

    if "audience" in raw:
        if raw["audience"] not in AUDIENCE_VALUES:
            errors.append(f"'audience' must be one of {sorted(AUDIENCE_VALUES)}")
        else:
            out["audience"] = raw["audience"]

    if "section" in raw:
        if not isinstance(raw["section"], str) or not raw["section"].strip():
            errors.append("'section' must be a non-empty string")
        else:
            out["section"] = raw["section"].strip()

    if "order" in raw:
        if not isinstance(raw["order"], int) or isinstance(raw["order"], bool):
            errors.append("'order' must be an integer")
        else:
            out["order"] = raw["order"]

    if "label" in raw:
        out["label"] = _label_dict(raw["label"], "label", errors)
    if "help_text" in raw:
        out["help_text"] = _label_dict(raw["help_text"], "help_text", errors)
    if "default" in raw:
        out["default"] = raw["default"]

    if "validation" in raw:
        if not isinstance(raw["validation"], dict):
            errors.append("'validation' must be an object")
        else:
            bad = sorted(set(raw["validation"]) - _VALIDATION_KEYS)
            if bad:
                errors.append(f"'validation' has unknown rule(s): {', '.join(bad)}")
            out["validation"] = dict(raw["validation"])

    if "options" in raw:
        out["options"] = _normalize_options(raw["options"], errors)
    if out["type"] in _ENUM_TYPES and not out["options"]:
        errors.append(f"type '{out['type']}' requires a non-empty 'options' list")

    if "fields" in raw:
        if not isinstance(raw["fields"], list) or not all(
            isinstance(f, str) and f for f in raw["fields"]
        ):
            errors.append("'fields' must be a list of non-empty strings")
        else:
            out["fields"] = list(raw["fields"])

    if raw.get("widget_key") is not None:
        out["widget_key"] = str(raw["widget_key"])

    if out["type"] == "widget":
        if out["widget_key"] not in WIDGET_KEYS:
            errors.append(
                "type 'widget' requires a registered 'widget_key' "
                f"(one of {sorted(WIDGET_KEYS)})"
            )
        if not out["fields"]:
            errors.append("type 'widget' requires a non-empty 'fields' list")
    else:
        if out["widget_key"] is not None:
            errors.append("'widget_key' is only allowed when type == 'widget'")
        if out["fields"]:
            errors.append("'fields' is only allowed when type == 'widget'")

    if out["locked"]:
        if out["kind"] != "core":
            errors.append("'locked' is only allowed on kind == 'core'")
        # Spec section 3.1: for a locked attribute ``visible`` is fixed true.
        out["visible"] = True

    if errors:
        raise AttributeSchemaError(errors)
    return out


def validate_definition_json(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a whole ``{"attributes": [...]}`` payload and return it normalized.

    Attributes come back sorted by ``(section, order, name)`` so every consumer
    (form renderer, interview protocol, export) sees the same stable order
    without re-sorting.
    """
    if not isinstance(payload, dict) or "attributes" not in payload:
        raise AttributeSchemaError(
            ["payload must be an object with an 'attributes' key"]
        )
    raw_attributes = payload["attributes"]
    if not isinstance(raw_attributes, list):
        raise AttributeSchemaError(["'attributes' must be a list"])

    errors: list[str] = []
    normalized: list[dict[str, Any]] = []
    for entry in raw_attributes:
        try:
            normalized.append(normalize_attribute(entry))
        except AttributeSchemaError as exc:
            name = entry.get("name", "<unnamed>") if isinstance(entry, dict) else "<invalid>"
            errors.extend(f"{name}: {e}" for e in exc.errors)

    seen: set[str] = set()
    for attribute in normalized:
        if attribute["name"] in seen:
            errors.append(f"duplicate attribute name: {attribute['name']}")
        seen.add(attribute["name"])

    if errors:
        raise AttributeSchemaError(errors)

    normalized.sort(key=lambda a: (a["section"], a["order"], a["name"]))
    return {"attributes": normalized}


def _by_name(attributes: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {a["name"]: a for a in attributes}


def validate_meta_only_change(
    old_attributes: list[dict[str, Any]], new_attributes: list[dict[str, Any]]
) -> None:
    """Enforce the core-lock and ``locked`` rules of spec section 3.1.

    Both arguments must already be normalized (``normalize_attribute``).

    Raises:
        AttributeSchemaError: a core attribute was renamed, retyped, dropped or
            newly introduced, or a ``locked`` attribute had one of
            ``visible``/``required``/``editable`` changed.
    """
    errors: list[str] = []
    old_map = _by_name(old_attributes)
    new_map = _by_name(new_attributes)

    for name, old in old_map.items():
        if old["kind"] != "core":
            continue
        new = new_map.get(name)
        if new is None:
            errors.append(f"{name}: a core attribute may not be removed or renamed")
            continue
        if new["kind"] != "core":
            errors.append(f"{name}: a core attribute may not change its 'kind'")
        if new["type"] != old["type"]:
            errors.append(f"{name}: a core attribute may not change its 'type'")
        if old["locked"]:
            if not new["locked"]:
                errors.append(f"{name}: 'locked' may not be cleared")
            for prop in sorted(LOCKED_IMMUTABLE_PROPERTIES):
                if new[prop] != old[prop]:
                    errors.append(
                        f"{name}: '{prop}' is not changeable on a locked attribute"
                    )

    for name, new in new_map.items():
        if name in old_map:
            continue
        if new["kind"] == "core":
            errors.append(f"{name}: a core attribute may not be added through the API")
        if new["locked"]:
            errors.append(f"{name}: 'locked' may only be set by the bootstrap script")

    if errors:
        raise AttributeSchemaError(errors)


__all__ = [
    "ALLOWED_KEYS",
    "ATTRIBUTE_KINDS",
    "ATTRIBUTE_TYPES",
    "AUDIENCE_VALUES",
    "AttributeSchemaError",
    "CORE_EDITABLE_META_PROPERTIES",
    "EDITABLE_VALUES",
    "LOCKED_IMMUTABLE_PROPERTIES",
    "WIDGET_KEYS",
    "normalize_attribute",
    "validate_definition_json",
    "validate_meta_only_change",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest attribute_definitions/tests/test_schema.py -v`
Expected: PASS (21 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/attribute_definitions/schema.py backend/attribute_definitions/tests/test_schema.py
git commit -m "feat(attribute-definitions): add attribute schema vocabulary and validation"
```

---

### Task 3: Field-value validation engine

Pure rule engine behind `AttributeDefinitionService.validate_artifact_fields` (spec section 5). Kept DB-free so the rules are testable without fixtures and reusable by the bulk-update endpoint of the Tabellenansicht spec.

**Files:**
- Create: `backend/attribute_definitions/field_validation.py`
- Test: `backend/attribute_definitions/tests/test_field_validation.py`

**Interfaces:**
- Consumes: `attribute_definitions.schema.normalize_attribute` (only in tests, to build fixtures).
- Produces:
  - `class FieldValidationError(ValueError)` with `errors: dict[str, list[str]]`
  - `validate_values(attributes: list[dict], changed_fields: dict, existing: dict | None) -> None`
  - `EXTENDED_PAYLOAD_KEY: str` = `"custom_fields"`

Payload contract (used identically by REST, MCP and the bulk endpoints): `changed_fields` is flat for `kind="core"` names; `kind="extended"` values live under `changed_fields["custom_fields"]`. `existing is None` means *create* — all required attributes are checked. Otherwise only fields present in `changed_fields` are checked.

- [ ] **Step 1: Write the failing test**

Create `backend/attribute_definitions/tests/test_field_validation.py`:

```python
"""Rule engine for artifact field validation (spec section 5)."""
from __future__ import annotations

import pytest

from attribute_definitions.field_validation import (
    FieldValidationError,
    validate_values,
)
from attribute_definitions.schema import normalize_attribute


def _attrs(*raw: dict) -> list[dict]:
    return [normalize_attribute(r) for r in raw]


DEF = _attrs(
    {"name": "title", "kind": "core", "type": "text", "required": True,
     "validation": {"length": 200}},
    {"name": "description", "kind": "core", "type": "textarea"},
    {"name": "uid", "kind": "core", "type": "text",
     "validation": {"regex": r"^REQ-\d+$"}},
    {"name": "effort", "kind": "core", "type": "number",
     "validation": {"min": 1, "max": 13}},
    {"name": "hidden_note", "kind": "core", "type": "text", "required": True,
     "visible": False},
    {"name": "sap_id", "kind": "extended", "type": "text", "required": True},
    {"name": "cost_centre", "kind": "extended", "type": "text"},
)


def test_create_requires_every_visible_required_field() -> None:
    with pytest.raises(FieldValidationError) as exc:
        validate_values(DEF, {"description": "d"}, None)
    assert set(exc.value.errors) == {"title", "sap_id"}


def test_create_passes_when_all_required_fields_are_set() -> None:
    validate_values(DEF, {"title": "T", "custom_fields": {"sap_id": "S"}}, None)


def test_create_ignores_required_on_an_invisible_attribute() -> None:
    """visible=False + required=True must not block creation (spec section 5)."""
    validate_values(DEF, {"title": "T", "custom_fields": {"sap_id": "S"}}, None)


def test_update_does_not_block_a_required_field_the_request_never_touches() -> None:
    """Grandfathering for legacy data: an untouched empty required field is fine."""
    validate_values(DEF, {"description": "d"}, {"title": "", "description": ""})


def test_update_rejects_clearing_a_required_field() -> None:
    with pytest.raises(FieldValidationError) as exc:
        validate_values(DEF, {"title": "   "}, {"title": "old"})
    assert "title" in exc.value.errors


def test_update_rejects_clearing_a_required_extended_field() -> None:
    with pytest.raises(FieldValidationError) as exc:
        validate_values(DEF, {"custom_fields": {"sap_id": ""}}, {"title": "old"})
    assert "sap_id" in exc.value.errors


def test_unknown_extended_field_is_rejected() -> None:
    with pytest.raises(FieldValidationError) as exc:
        validate_values(DEF, {"custom_fields": {"nope": "x"}}, {"title": "old"})
    assert "nope" in exc.value.errors


def test_unknown_top_level_field_is_ignored() -> None:
    """Serializer control fields (change_reason, expected_version, ...) are not
    attributes; the ViewSet's own _validate_patch_payload guards those."""
    validate_values(DEF, {"change_reason": "why", "expected_version": 3}, {"title": "t"})


def test_regex_rule_is_enforced_on_a_present_field() -> None:
    validate_values(DEF, {"uid": "REQ-42"}, {"title": "t"})
    with pytest.raises(FieldValidationError) as exc:
        validate_values(DEF, {"uid": "nope"}, {"title": "t"})
    assert "uid" in exc.value.errors


def test_length_rule_is_enforced() -> None:
    with pytest.raises(FieldValidationError) as exc:
        validate_values(DEF, {"title": "x" * 201}, {"title": "t"})
    assert "title" in exc.value.errors


def test_min_max_rules_are_enforced_on_numbers() -> None:
    validate_values(DEF, {"effort": 8}, {"title": "t"})
    with pytest.raises(FieldValidationError):
        validate_values(DEF, {"effort": 0}, {"title": "t"})
    with pytest.raises(FieldValidationError):
        validate_values(DEF, {"effort": 21}, {"title": "t"})


def test_non_numeric_value_for_a_number_attribute_is_rejected() -> None:
    with pytest.raises(FieldValidationError) as exc:
        validate_values(DEF, {"effort": "big"}, {"title": "t"})
    assert "effort" in exc.value.errors


def test_none_value_skips_the_range_rules_but_still_trips_required() -> None:
    validate_values(DEF, {"effort": None}, {"title": "t"})
    with pytest.raises(FieldValidationError):
        validate_values(DEF, {"title": None}, {"title": "t"})


def test_enum_value_must_be_one_of_the_options() -> None:
    attrs = _attrs({
        "name": "category", "kind": "core", "type": "enum",
        "options": [{"value": "a", "label_de": "A", "label_en": "A"},
                    {"value": "b", "label_de": "B", "label_en": "B"}],
    })
    validate_values(attrs, {"category": "a"}, {})
    with pytest.raises(FieldValidationError) as exc:
        validate_values(attrs, {"category": "z"}, {})
    assert "category" in exc.value.errors


def test_multi_enum_value_must_be_a_list_of_known_options() -> None:
    attrs = _attrs({
        "name": "tags", "kind": "core", "type": "multi-enum",
        "options": [{"value": "a", "label_de": "A", "label_en": "A"}],
    })
    validate_values(attrs, {"tags": ["a"]}, {})
    with pytest.raises(FieldValidationError):
        validate_values(attrs, {"tags": "a"}, {})
    with pytest.raises(FieldValidationError):
        validate_values(attrs, {"tags": ["a", "z"]}, {})


def test_boolean_attribute_rejects_a_non_boolean() -> None:
    attrs = _attrs({"name": "flag", "kind": "core", "type": "boolean"})
    validate_values(attrs, {"flag": True}, {})
    with pytest.raises(FieldValidationError):
        validate_values(attrs, {"flag": "yes"}, {})


def test_widget_attribute_validates_its_bound_fields_not_its_own_name() -> None:
    attrs = _attrs(
        {"name": "risk_matrix", "kind": "core", "type": "widget",
         "widget_key": "risk_matrix_rpz",
         "fields": ["probability", "impact", "detection"]},
        {"name": "detection", "kind": "core", "type": "number",
         "validation": {"min": 1, "max": 10}},
    )
    validate_values(attrs, {"detection": 5}, {})
    with pytest.raises(FieldValidationError):
        validate_values(attrs, {"detection": 11}, {})
    # The widget's own name is not a payload field and is never demanded.
    validate_values(attrs, {"detection": 5}, None)


def test_all_errors_are_reported_together() -> None:
    with pytest.raises(FieldValidationError) as exc:
        validate_values(DEF, {"title": "", "uid": "bad", "effort": 99}, {"title": "t"})
    assert set(exc.value.errors) == {"title", "uid", "effort"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest attribute_definitions/tests/test_field_validation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'attribute_definitions.field_validation'`

- [ ] **Step 3: Write the implementation**

Create `backend/attribute_definitions/field_validation.py`:

```python
"""Artifact field-value validation against a resolved attribute definition.

Spec section 5. Deliberately DB-free and Django-free: the rules are a pure
function of ``(attributes, changed_fields, existing)``, which keeps them
testable without fixtures and reusable by the bulk-update endpoint.

Payload contract
----------------
``changed_fields`` is flat for ``kind="core"`` attribute names; ``extended``
values live in the nested ``changed_fields["custom_fields"]`` dict.

``existing is None`` means **create**: every visible, required attribute must be
present and non-empty. Otherwise (**update**) only the fields the request
actually carries are checked — a save that does not touch a required field is
never blocked, which is the grandfathering rule for legacy data.

Unknown **extended** names are rejected (issue #851: "unknown fields silently
discarded"). Unknown **top-level** names are ignored on purpose: they are the
serializer's own control fields (``change_reason``, ``expected_version``, ...),
and ``WorkflowTransitionsMixin._validate_patch_payload`` already guards those.
"""
from __future__ import annotations

import re
from typing import Any

#: Nested key under which ``kind="extended"`` values travel.
EXTENDED_PAYLOAD_KEY = "custom_fields"

_ENUM_TYPES = frozenset({"enum", "multi-enum"})


class FieldValidationError(ValueError):
    """Raised when a payload violates the resolved attribute definition.

    ``errors`` maps attribute name -> list of human-readable messages, which is
    the shape the DRF error envelope and the MCP error payload both expect.
    """

    def __init__(self, errors: dict[str, list[str]]) -> None:
        self.errors = errors
        super().__init__(
            "; ".join(f"{name}: {', '.join(msgs)}" for name, msgs in errors.items())
        )


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    return False


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _check_type(attribute: dict[str, Any], value: Any, out: list[str]) -> None:
    kind = attribute["type"]
    if kind == "number":
        if _as_number(value) is None:
            out.append("must be a number")
    elif kind == "boolean":
        if not isinstance(value, bool):
            out.append("must be a boolean")
    elif kind == "enum":
        allowed = {o["value"] for o in attribute["options"]}
        if str(value) not in allowed:
            out.append(f"must be one of {sorted(allowed)}")
    elif kind == "multi-enum":
        if not isinstance(value, list):
            out.append("must be a list")
            return
        allowed = {o["value"] for o in attribute["options"]}
        unknown = sorted({str(v) for v in value} - allowed)
        if unknown:
            out.append(f"contains unknown option(s): {', '.join(unknown)}")


def _check_rules(attribute: dict[str, Any], value: Any, out: list[str]) -> None:
    rules = attribute["validation"]
    if not rules:
        return
    if "regex" in rules:
        pattern = str(rules["regex"])
        try:
            if re.fullmatch(pattern, str(value)) is None:
                out.append(f"does not match {pattern!r}")
        except re.error:
            out.append(f"has a malformed 'regex' rule: {pattern!r}")
    if "length" in rules and len(str(value)) > int(rules["length"]):
        out.append(f"is longer than {rules['length']} characters")
    number = _as_number(value)
    if "min" in rules:
        if number is None:
            out.append("must be a number to satisfy the 'min' rule")
        elif number < float(rules["min"]):
            out.append(f"must be >= {rules['min']}")
    if "max" in rules:
        if number is None:
            out.append("must be a number to satisfy the 'max' rule")
        elif number > float(rules["max"]):
            out.append(f"must be <= {rules['max']}")


def validate_values(
    attributes: list[dict[str, Any]],
    changed_fields: dict[str, Any],
    existing: dict[str, Any] | None,
) -> None:
    """Validate *changed_fields* against *attributes*.

    Args:
        attributes: the resolved ``definition_json["attributes"]`` list
            (already normalized by ``attribute_definitions.schema``).
        changed_fields: the fields the request sets or clears; extended values
            nested under ``"custom_fields"``.
        existing: the artifact's current values, or ``None`` for a create.

    Raises:
        FieldValidationError: one entry per offending attribute; all violations
            are collected before raising.
    """
    by_name = {a["name"]: a for a in attributes}
    # A widget bundles other attributes; its own name is never a payload field.
    payload_names = {n for n, a in by_name.items() if a["type"] != "widget"}
    extended_names = {
        n for n in payload_names if by_name[n]["kind"] == "extended"
    }

    supplied_extended = changed_fields.get(EXTENDED_PAYLOAD_KEY) or {}
    if not isinstance(supplied_extended, dict):
        raise FieldValidationError(
            {EXTENDED_PAYLOAD_KEY: ["must be an object of attribute name -> value"]}
        )

    errors: dict[str, list[str]] = {}

    for name in sorted(set(supplied_extended) - extended_names):
        errors.setdefault(name, []).append("is not a defined attribute")

    # Flatten to one name -> value view of everything the request carries.
    supplied: dict[str, Any] = {
        name: value
        for name, value in changed_fields.items()
        if name != EXTENDED_PAYLOAD_KEY and name in payload_names
    }
    supplied.update(
        {name: value for name, value in supplied_extended.items() if name in extended_names}
    )

    is_create = existing is None
    for name in sorted(payload_names):
        attribute = by_name[name]
        present = name in supplied
        if not present:
            if is_create and attribute["required"] and attribute["visible"]:
                errors.setdefault(name, []).append("is required")
            continue

        value = supplied[name]
        if _is_empty(value):
            if attribute["required"] and attribute["visible"]:
                errors.setdefault(name, []).append("is required")
            continue

        messages: list[str] = []
        _check_type(attribute, value, messages)
        if not messages:
            _check_rules(attribute, value, messages)
        if messages:
            errors.setdefault(name, []).extend(messages)

    if errors:
        raise FieldValidationError(errors)


__all__ = ["EXTENDED_PAYLOAD_KEY", "FieldValidationError", "validate_values"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest attribute_definitions/tests/test_field_validation.py -v`
Expected: PASS (18 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/attribute_definitions/field_validation.py backend/attribute_definitions/tests/test_field_validation.py
git commit -m "feat(attribute-definitions): add field-value validation engine"
```

---

### Task 4: Global definition store with propagation

**Files:**
- Create: `backend/attribute_definitions/global_definition_store.py`
- Test: `backend/attribute_definitions/tests/test_global_store.py`

**Interfaces:**
- Consumes: `attribute_definitions.models.GlobalAttributeDefinition`, `attribute_definitions.models.WorkspaceAttributeDefinition`, `attribute_definitions.schema.validate_definition_json`, `attribute_definitions.schema.validate_meta_only_change`, `attribute_definitions.schema.AttributeSchemaError`.
- Produces: `class GlobalAttributeDefinitionStore` with
  - `get(tenant_id, item_type, preset) -> GlobalAttributeDefinition | None`
  - `list(tenant_id, *, item_type=None, preset=None) -> list[GlobalAttributeDefinition]`
  - `initialize(tenant_id, item_type, preset, attributes) -> GlobalAttributeDefinition`
  - `update(tenant_id, item_type, preset, attributes) -> tuple[GlobalAttributeDefinition, int]` (returns the row and the propagated workspace count)
  - `class AttributeDefinitionNotFound(LookupError)`

- [ ] **Step 1: Write the failing test**

Create `backend/attribute_definitions/tests/test_global_store.py`:

```python
"""Global store: CRUD, meta-only enforcement and propagation."""
from __future__ import annotations

import uuid

import pytest

from attribute_definitions.global_definition_store import (
    AttributeDefinitionNotFound,
    GlobalAttributeDefinitionStore,
)
from attribute_definitions.models import (
    GlobalAttributeDefinition,
    WorkspaceAttributeDefinition,
)
from attribute_definitions.schema import AttributeSchemaError
from persistence.models import Tenant

TITLE = {"name": "title", "kind": "core", "type": "text"}
STATUS = {
    "name": "status", "kind": "core", "type": "enum", "locked": True,
    "editable": "workflow",
    "options": [{"value": "draft", "label_de": "Entwurf", "label_en": "Draft"}],
}


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")


@pytest.fixture
def store() -> GlobalAttributeDefinitionStore:
    return GlobalAttributeDefinitionStore()


@pytest.mark.django_db
def test_initialize_then_get(tenant, store) -> None:
    store.initialize(tenant.id, "Risk", "standard", [TITLE])
    row = store.get(tenant.id, "Risk", "standard")
    assert [a["name"] for a in row.definition_json["attributes"]] == ["title"]


@pytest.mark.django_db
def test_initialize_twice_is_rejected(tenant, store) -> None:
    store.initialize(tenant.id, "Risk", "standard", [TITLE])
    with pytest.raises(AttributeSchemaError) as exc:
        store.initialize(tenant.id, "Risk", "standard", [TITLE])
    assert "already initialized" in " ".join(exc.value.errors)


@pytest.mark.django_db
def test_get_returns_none_for_a_missing_row(tenant, store) -> None:
    assert store.get(tenant.id, "Risk", "minimal") is None


@pytest.mark.django_db
def test_list_filters_by_item_type_and_preset(tenant, store) -> None:
    store.initialize(tenant.id, "Risk", "standard", [TITLE])
    store.initialize(tenant.id, "Risk", "minimal", [TITLE])
    store.initialize(tenant.id, "Issue", "standard", [TITLE])
    assert len(store.list(tenant.id)) == 3
    assert len(store.list(tenant.id, item_type="Risk")) == 2
    assert len(store.list(tenant.id, preset="standard")) == 2


@pytest.mark.django_db
def test_update_bumps_version_and_persists(tenant, store) -> None:
    store.initialize(tenant.id, "Risk", "standard", [TITLE])
    row, _ = store.update(tenant.id, "Risk", "standard",
                          [dict(TITLE, required=True, order=3)])
    assert row.version == 2
    assert row.definition_json["attributes"][0]["required"] is True


@pytest.mark.django_db
def test_update_of_a_missing_row_raises_not_found(tenant, store) -> None:
    with pytest.raises(AttributeDefinitionNotFound):
        store.update(tenant.id, "Risk", "standard", [TITLE])


@pytest.mark.django_db
def test_update_rejects_a_core_rename(tenant, store) -> None:
    store.initialize(tenant.id, "Risk", "standard", [TITLE])
    with pytest.raises(AttributeSchemaError):
        store.update(tenant.id, "Risk", "standard",
                     [{"name": "headline", "kind": "core", "type": "text"}])


@pytest.mark.django_db
def test_update_rejects_unlocking_a_locked_attribute(tenant, store) -> None:
    store.initialize(tenant.id, "Risk", "standard", [TITLE, STATUS])
    with pytest.raises(AttributeSchemaError) as exc:
        store.update(tenant.id, "Risk", "standard",
                     [TITLE, dict(STATUS, editable=True)])
    assert "status" in " ".join(exc.value.errors)


@pytest.mark.django_db
def test_update_propagates_into_non_customized_rows_of_the_same_preset(tenant, store) -> None:
    g = store.initialize(tenant.id, "Risk", "standard", [TITLE])
    on_default = WorkspaceAttributeDefinition.unscoped.create(
        tenant_id=tenant.id, workspace_id=uuid.uuid4(), item_type="Risk",
        preset="standard", definition_json={"attributes": []},
        source_global=g, is_customized=False,
    )
    customized = WorkspaceAttributeDefinition.unscoped.create(
        tenant_id=tenant.id, workspace_id=uuid.uuid4(), item_type="Risk",
        preset="standard", definition_json={"attributes": []},
        source_global=g, is_customized=True,
    )
    _, count = store.update(tenant.id, "Risk", "standard",
                            [dict(TITLE, required=True)])
    assert count == 1
    on_default.refresh_from_db()
    customized.refresh_from_db()
    assert on_default.definition_json["attributes"][0]["required"] is True
    assert customized.definition_json == {"attributes": []}


@pytest.mark.django_db
def test_propagation_writes_a_deep_copy(tenant, store) -> None:
    """A shared mutable reference between global and derived rows would let one
    workspace edit silently rewrite the tenant default."""
    g = store.initialize(tenant.id, "Risk", "standard", [TITLE])
    w = WorkspaceAttributeDefinition.unscoped.create(
        tenant_id=tenant.id, workspace_id=uuid.uuid4(), item_type="Risk",
        preset="standard", definition_json={"attributes": []},
        source_global=g, is_customized=False,
    )
    store.update(tenant.id, "Risk", "standard", [dict(TITLE, required=True)])
    w.refresh_from_db()
    w.definition_json["attributes"][0]["required"] = False
    w.save(update_fields=["definition_json"])
    g.refresh_from_db()
    assert g.definition_json["attributes"][0]["required"] is True


@pytest.mark.django_db
def test_propagation_ignores_another_preset(tenant, store) -> None:
    g_std = store.initialize(tenant.id, "Risk", "standard", [TITLE])
    g_min = store.initialize(tenant.id, "Risk", "minimal", [TITLE])
    WorkspaceAttributeDefinition.unscoped.create(
        tenant_id=tenant.id, workspace_id=uuid.uuid4(), item_type="Risk",
        preset="minimal", definition_json={"attributes": []},
        source_global=g_min, is_customized=False,
    )
    _, count = store.update(tenant.id, "Risk", "standard",
                            [dict(TITLE, required=True)])
    assert count == 0
    assert GlobalAttributeDefinition.unscoped.get(id=g_std.id).version == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest attribute_definitions/tests/test_global_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'attribute_definitions.global_definition_store'`

- [ ] **Step 3: Write the implementation**

Create `backend/attribute_definitions/global_definition_store.py`:

```python
"""Store for the tenant-wide ``GlobalAttributeDefinition`` rows.

Structurally symmetric to ``workflow.global_definition_store``: every mutation
persists the global row and PROPAGATES ``definition_json`` into every
``is_customized=False`` derived definition of the SAME preset, returning the
propagated workspace count so the UI can surface it.

Uses ``unscoped`` on purpose: the tenant is passed explicitly by the caller
(the service already asserted the admin role for that tenant), which mirrors
``GlobalWorkflowDefinitionStore`` and keeps the store usable from management
commands and data migrations where no thread-local tenant is armed.
"""
from __future__ import annotations

import copy
from typing import Any
from uuid import UUID

from .models import GlobalAttributeDefinition, WorkspaceAttributeDefinition
from .schema import (
    AttributeSchemaError,
    validate_definition_json,
    validate_meta_only_change,
)


class AttributeDefinitionNotFound(LookupError):
    """No definition row exists for the requested key."""


class GlobalAttributeDefinitionStore:
    """CRUD + propagation for tenant-wide global attribute defaults."""

    # ---------- Read ----------

    def get(
        self, tenant_id: UUID | str, item_type: str, preset: str
    ) -> GlobalAttributeDefinition | None:
        """Return the global row for ``(tenant, item_type, preset)`` or None."""
        return GlobalAttributeDefinition.unscoped.filter(
            tenant_id=tenant_id, item_type=item_type, preset=preset
        ).first()

    def list(
        self,
        tenant_id: UUID | str,
        *,
        item_type: str | None = None,
        preset: str | None = None,
    ) -> list[GlobalAttributeDefinition]:
        """Return all global rows for the tenant, optionally filtered."""
        qs = GlobalAttributeDefinition.unscoped.filter(tenant_id=tenant_id)
        if item_type:
            qs = qs.filter(item_type=item_type)
        if preset:
            qs = qs.filter(preset=preset)
        return list(qs.order_by("item_type", "preset"))

    # ---------- Write ----------

    def initialize(
        self,
        tenant_id: UUID | str,
        item_type: str,
        preset: str,
        attributes: list[dict[str, Any]],
    ) -> GlobalAttributeDefinition:
        """Create the global definition for ``(item_type, preset)``.

        Raises:
            AttributeSchemaError: a row already exists, or *attributes* is
                malformed. The view maps the "already initialized" case to 409.
        """
        if self.get(tenant_id, item_type, preset) is not None:
            raise AttributeSchemaError(
                [
                    f"Global attribute definition for '{item_type}/{preset}' "
                    f"is already initialized"
                ]
            )
        payload = validate_definition_json({"attributes": attributes})
        return GlobalAttributeDefinition.unscoped.create(
            tenant_id=tenant_id,
            item_type=item_type,
            preset=preset,
            definition_json=payload,
        )

    def update(
        self,
        tenant_id: UUID | str,
        item_type: str,
        preset: str,
        attributes: list[dict[str, Any]],
    ) -> tuple[GlobalAttributeDefinition, int]:
        """Replace the attribute list, bump ``version``, propagate.

        Returns:
            ``(row, propagated_workspace_count)``.

        Raises:
            AttributeDefinitionNotFound: no global row for that key.
            AttributeSchemaError: malformed payload, or a change that the
                core-lock / ``locked`` rules forbid.
        """
        obj = self.get(tenant_id, item_type, preset)
        if obj is None:
            raise AttributeDefinitionNotFound(
                f"No global attribute definition for '{item_type}/{preset}'"
            )
        payload = validate_definition_json({"attributes": attributes})
        old = (obj.definition_json or {}).get("attributes", [])
        validate_meta_only_change(old, payload["attributes"])

        obj.definition_json = payload
        obj.version = (obj.version or 1) + 1
        obj.save(update_fields=["definition_json", "version", "modified_at"])
        return obj, self._propagate(obj)

    # ---------- Propagation ----------

    def _propagate(self, obj: GlobalAttributeDefinition) -> int:
        """Copy ``definition_json`` into every non-customized derived row.

        ``preset`` is part of the derived row's identity, so the filter narrows
        on it too: a standard-preset edit must never rewrite a minimal-preset
        workspace that happens to point at a stale ``source_global``.

        ``copy.deepcopy`` is load-bearing: without it every derived row would
        share one mutable dict with the global, so an in-place edit on one row
        would silently rewrite the tenant default and all of its siblings.
        """
        return WorkspaceAttributeDefinition.unscoped.filter(
            source_global_id=obj.id,
            preset=obj.preset,
            is_customized=False,
        ).update(definition_json=copy.deepcopy(obj.definition_json))


__all__ = ["AttributeDefinitionNotFound", "GlobalAttributeDefinitionStore"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest attribute_definitions/tests/test_global_store.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/attribute_definitions/global_definition_store.py backend/attribute_definitions/tests/test_global_store.py
git commit -m "feat(attribute-definitions): add global definition store with propagation"
```

---

### Task 5: Workspace definition store (resolve / update / reset)

**Files:**
- Create: `backend/attribute_definitions/workspace_definition_store.py`
- Test: `backend/attribute_definitions/tests/test_workspace_store.py`

**Interfaces:**
- Consumes: `attribute_definitions.global_definition_store.GlobalAttributeDefinitionStore`, `attribute_definitions.models.WorkspaceAttributeDefinition`, `attribute_definitions.schema.{validate_definition_json, validate_meta_only_change, AttributeSchemaError}`, `attribute_definitions.global_definition_store.AttributeDefinitionNotFound`.
- Produces: `class WorkspaceAttributeDefinitionStore` with
  - `resolve(tenant_id, workspace_id, item_type, preset) -> WorkspaceAttributeDefinition` (materializes on first read)
  - `update(tenant_id, workspace_id, item_type, attributes) -> WorkspaceAttributeDefinition` (sets `is_customized=True`)
  - `reset(tenant_id, workspace_id, item_type) -> WorkspaceAttributeDefinition` (back to `source_global`, `is_customized=False`)
  - `missing_attributes_for_preset(tenant_id, workspace_id, item_type, target_preset) -> list[str]`

- [ ] **Step 1: Write the failing test**

Create `backend/attribute_definitions/tests/test_workspace_store.py`:

```python
"""Workspace store: materialize-on-read, override, reset, downgrade probe."""
from __future__ import annotations

import uuid

import pytest

from attribute_definitions.global_definition_store import (
    AttributeDefinitionNotFound,
    GlobalAttributeDefinitionStore,
)
from attribute_definitions.models import WorkspaceAttributeDefinition
from attribute_definitions.schema import AttributeSchemaError
from attribute_definitions.workspace_definition_store import (
    WorkspaceAttributeDefinitionStore,
)
from persistence.models import Tenant

TITLE = {"name": "title", "kind": "core", "type": "text"}
NOTE = {"name": "note", "kind": "extended", "type": "text"}


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")


@pytest.fixture
def stores() -> tuple[GlobalAttributeDefinitionStore, WorkspaceAttributeDefinitionStore]:
    return GlobalAttributeDefinitionStore(), WorkspaceAttributeDefinitionStore()


@pytest.mark.django_db
def test_resolve_materializes_a_copy_on_first_read(tenant, stores) -> None:
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", "standard", [TITLE])
    ws = uuid.uuid4()
    row = ws_store.resolve(tenant.id, ws, "Risk", "standard")
    assert row.is_customized is False
    assert row.source_global is not None
    assert [a["name"] for a in row.definition_json["attributes"]] == ["title"]
    assert WorkspaceAttributeDefinition.unscoped.filter(workspace_id=ws).count() == 1


@pytest.mark.django_db
def test_resolve_is_idempotent(tenant, stores) -> None:
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", "standard", [TITLE])
    ws = uuid.uuid4()
    first = ws_store.resolve(tenant.id, ws, "Risk", "standard")
    second = ws_store.resolve(tenant.id, ws, "Risk", "standard")
    assert first.id == second.id


@pytest.mark.django_db
def test_resolve_without_a_global_raises_not_found(tenant, stores) -> None:
    _, ws_store = stores
    with pytest.raises(AttributeDefinitionNotFound):
        ws_store.resolve(tenant.id, uuid.uuid4(), "Risk", "standard")


@pytest.mark.django_db
def test_resolve_keeps_the_frozen_preset_of_an_existing_row(tenant, stores) -> None:
    """Spec section 3: preset is frozen at creation; a later workspace preset
    switch must not silently re-point the row at another global."""
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", "standard", [TITLE])
    g_store.initialize(tenant.id, "Risk", "extended", [TITLE, NOTE])
    ws = uuid.uuid4()
    ws_store.resolve(tenant.id, ws, "Risk", "standard")
    row = ws_store.resolve(tenant.id, ws, "Risk", "extended")
    assert row.preset == "standard"
    assert [a["name"] for a in row.definition_json["attributes"]] == ["title"]


@pytest.mark.django_db
def test_update_sets_is_customized_and_bumps_version(tenant, stores) -> None:
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", "standard", [TITLE])
    ws = uuid.uuid4()
    ws_store.resolve(tenant.id, ws, "Risk", "standard")
    row = ws_store.update(tenant.id, ws, "Risk", [dict(TITLE, required=True), NOTE])
    assert row.is_customized is True
    assert row.version == 2
    assert [a["name"] for a in row.definition_json["attributes"]] == ["note", "title"]


@pytest.mark.django_db
def test_update_rejects_a_core_rename(tenant, stores) -> None:
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", "standard", [TITLE])
    ws = uuid.uuid4()
    ws_store.resolve(tenant.id, ws, "Risk", "standard")
    with pytest.raises(AttributeSchemaError):
        ws_store.update(tenant.id, ws, "Risk",
                        [{"name": "headline", "kind": "core", "type": "text"}])


@pytest.mark.django_db
def test_update_of_an_unresolved_workspace_raises_not_found(tenant, stores) -> None:
    _, ws_store = stores
    with pytest.raises(AttributeDefinitionNotFound):
        ws_store.update(tenant.id, uuid.uuid4(), "Risk", [TITLE])


@pytest.mark.django_db
def test_reset_restores_the_global_and_clears_is_customized(tenant, stores) -> None:
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", "standard", [TITLE])
    ws = uuid.uuid4()
    ws_store.resolve(tenant.id, ws, "Risk", "standard")
    ws_store.update(tenant.id, ws, "Risk", [TITLE, NOTE])
    row = ws_store.reset(tenant.id, ws, "Risk")
    assert row.is_customized is False
    assert [a["name"] for a in row.definition_json["attributes"]] == ["title"]


@pytest.mark.django_db
def test_reset_without_a_source_global_raises_not_found(tenant, stores) -> None:
    _, ws_store = stores
    ws = uuid.uuid4()
    WorkspaceAttributeDefinition.unscoped.create(
        tenant_id=tenant.id, workspace_id=ws, item_type="Risk", preset="standard",
        definition_json={"attributes": []}, source_global=None, is_customized=True,
    )
    with pytest.raises(AttributeDefinitionNotFound):
        ws_store.reset(tenant.id, ws, "Risk")


@pytest.mark.django_db
def test_missing_attributes_for_preset_lists_names_the_target_lacks(tenant, stores) -> None:
    g_store, ws_store = stores
    g_store.initialize(tenant.id, "Risk", "extended", [TITLE, NOTE])
    g_store.initialize(tenant.id, "Risk", "minimal", [TITLE])
    ws = uuid.uuid4()
    ws_store.resolve(tenant.id, ws, "Risk", "extended")
    assert ws_store.missing_attributes_for_preset(
        tenant.id, ws, "Risk", "minimal"
    ) == ["note"]
    assert ws_store.missing_attributes_for_preset(
        tenant.id, ws, "Risk", "extended"
    ) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest attribute_definitions/tests/test_workspace_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'attribute_definitions.workspace_definition_store'`

- [ ] **Step 3: Write the implementation**

Create `backend/attribute_definitions/workspace_definition_store.py`:

```python
"""Store for the per-workspace materialized attribute definitions.

Materialize-on-first-read: a workspace that has never been resolved gets a full
deep copy of its preset's global default, linked back via ``source_global`` with
``is_customized=False``. Every later global edit then reaches it through
``GlobalAttributeDefinitionStore._propagate`` — no merge-on-read on the form
load path.

``preset`` on an existing row is FROZEN (spec section 3): resolving with a
different preset returns the existing row unchanged rather than re-pointing it,
so a workspace preset switch cannot silently discard a definition. The
downgrade probe (``missing_attributes_for_preset``) is what surfaces the
consequence to the user instead.
"""
from __future__ import annotations

import copy
from typing import Any
from uuid import UUID

from .global_definition_store import (
    AttributeDefinitionNotFound,
    GlobalAttributeDefinitionStore,
)
from .models import WorkspaceAttributeDefinition
from .schema import validate_definition_json, validate_meta_only_change


class WorkspaceAttributeDefinitionStore:
    """Resolve / override / reset per-workspace attribute definitions."""

    def __init__(self, global_store: GlobalAttributeDefinitionStore | None = None) -> None:
        self._global_store = global_store or GlobalAttributeDefinitionStore()

    # ---------- Read ----------

    def get(
        self, tenant_id: UUID | str, workspace_id: UUID | str, item_type: str
    ) -> WorkspaceAttributeDefinition | None:
        """Return the workspace row or None (no materialization)."""
        return WorkspaceAttributeDefinition.unscoped.filter(
            tenant_id=tenant_id, workspace_id=workspace_id, item_type=item_type
        ).first()

    def resolve(
        self,
        tenant_id: UUID | str,
        workspace_id: UUID | str,
        item_type: str,
        preset: str,
    ) -> WorkspaceAttributeDefinition:
        """Return the workspace row, materializing it from the global if absent.

        Raises:
            AttributeDefinitionNotFound: no global default exists for
                ``(item_type, preset)`` — run the bootstrap command first.
        """
        existing = self.get(tenant_id, workspace_id, item_type)
        if existing is not None:
            return existing

        source = self._global_store.get(tenant_id, item_type, preset)
        if source is None:
            raise AttributeDefinitionNotFound(
                f"No global attribute definition for '{item_type}/{preset}' — "
                f"run 'manage.py bootstrap_attribute_definitions' first"
            )
        obj, _created = WorkspaceAttributeDefinition.unscoped.get_or_create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            item_type=item_type,
            defaults={
                "preset": preset,
                "definition_json": copy.deepcopy(source.definition_json),
                "source_global": source,
                "is_customized": False,
            },
        )
        return obj

    # ---------- Write ----------

    def update(
        self,
        tenant_id: UUID | str,
        workspace_id: UUID | str,
        item_type: str,
        attributes: list[dict[str, Any]],
    ) -> WorkspaceAttributeDefinition:
        """Persist a workspace override and flip ``is_customized`` to True.

        Raises:
            AttributeDefinitionNotFound: the workspace has never been resolved.
            AttributeSchemaError: malformed payload or a forbidden core/locked
                change.
        """
        obj = self.get(tenant_id, workspace_id, item_type)
        if obj is None:
            raise AttributeDefinitionNotFound(
                f"No attribute definition resolved for '{item_type}' in "
                f"workspace {workspace_id}"
            )
        payload = validate_definition_json({"attributes": attributes})
        old = (obj.definition_json or {}).get("attributes", [])
        validate_meta_only_change(old, payload["attributes"])

        obj.definition_json = payload
        obj.is_customized = True
        obj.version = (obj.version or 1) + 1
        obj.save(
            update_fields=["definition_json", "is_customized", "version", "modified_at"]
        )
        return obj

    def reset(
        self, tenant_id: UUID | str, workspace_id: UUID | str, item_type: str
    ) -> WorkspaceAttributeDefinition:
        """Discard the override and re-copy the global default.

        Raises:
            AttributeDefinitionNotFound: the workspace has no row, or its
                ``source_global`` link is gone (the global was deleted), in
                which case there is nothing to reset TO.
        """
        obj = self.get(tenant_id, workspace_id, item_type)
        if obj is None:
            raise AttributeDefinitionNotFound(
                f"No attribute definition resolved for '{item_type}' in "
                f"workspace {workspace_id}"
            )
        source = obj.source_global
        if source is None:
            raise AttributeDefinitionNotFound(
                f"Attribute definition for '{item_type}' in workspace "
                f"{workspace_id} has no global source to reset to"
            )
        obj.definition_json = copy.deepcopy(source.definition_json)
        obj.is_customized = False
        obj.version = (obj.version or 1) + 1
        obj.save(
            update_fields=["definition_json", "is_customized", "version", "modified_at"]
        )
        return obj

    # ---------- Preset downgrade probe ----------

    def missing_attributes_for_preset(
        self,
        tenant_id: UUID | str,
        workspace_id: UUID | str,
        item_type: str,
        target_preset: str,
    ) -> list[str]:
        """Return the attribute names the workspace uses that *target_preset* lacks.

        Feeds the warning list of ``presets.services.validate_downgrade`` — the
        spec (section 9) explicitly reuses that check rather than inventing a
        second one. An empty list means the override survives the switch.
        """
        obj = self.get(tenant_id, workspace_id, item_type)
        if obj is None:
            return []
        target = self._global_store.get(tenant_id, item_type, target_preset)
        target_names = (
            {a["name"] for a in (target.definition_json or {}).get("attributes", [])}
            if target is not None
            else set()
        )
        current_names = {
            a["name"] for a in (obj.definition_json or {}).get("attributes", [])
        }
        return sorted(current_names - target_names)


__all__ = ["WorkspaceAttributeDefinitionStore"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest attribute_definitions/tests/test_workspace_store.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/attribute_definitions/workspace_definition_store.py backend/attribute_definitions/tests/test_workspace_store.py
git commit -m "feat(attribute-definitions): add workspace definition store"
```

---

### Task 6: Bootstrap command (model introspection → core attributes)

Spec section 3.2. Runs once per tenant to seed `GlobalAttributeDefinition` for all 30 `(item_type, preset)` combinations from Django model introspection. Idempotent; `--sync-new-fields` appends later-added model fields without touching curated meta-properties.

**Files:**
- Create: `backend/attribute_definitions/management/__init__.py`
- Create: `backend/attribute_definitions/management/commands/__init__.py`
- Create: `backend/attribute_definitions/management/commands/bootstrap_attribute_definitions.py`
- Test: `backend/attribute_definitions/tests/test_bootstrap_command.py`

**Interfaces:**
- Consumes: `attribute_definitions.global_definition_store.GlobalAttributeDefinitionStore`, `attribute_definitions.schema.normalize_attribute`, `presets.registry.PresetRegistry`.
- Produces (module-level, imported by the tests and by Task 9's data migration):
  - `BOOTSTRAP_ITEM_TYPES: tuple[str, ...]` — the ten types
  - `PRESETS: tuple[str, ...]` = `("minimal", "standard", "extended")`
  - `MODEL_LOCATIONS: dict[str, tuple[tuple[str, str], ...]]` — item type → ordered `(app_label, model_name)` candidates
  - `EXCLUDED_MODEL_FIELDS: frozenset[str]`
  - `CLASSIFICATION_FIELDS: frozenset[str]`, `CHANGE_CONTROL_FIELDS: frozenset[str]`
  - `WIDGET_ATTRIBUTES: dict[str, tuple[dict, ...]]` — item type → curated widget attribute entries
  - `synthetic_status_attribute() -> dict`
  - `introspect_core_attributes(item_type: str, preset: str) -> list[dict]`

- [ ] **Step 1: Write the failing test**

Create `backend/attribute_definitions/tests/test_bootstrap_command.py`:

```python
"""Bootstrap command: introspection output and idempotency."""
from __future__ import annotations

import uuid

import pytest
from django.core.management import call_command

from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
    BOOTSTRAP_ITEM_TYPES,
    EXCLUDED_MODEL_FIELDS,
    PRESETS,
    introspect_core_attributes,
    synthetic_status_attribute,
)
from attribute_definitions.models import GlobalAttributeDefinition
from persistence.models import Tenant


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")


def test_ten_item_types_are_covered() -> None:
    assert BOOTSTRAP_ITEM_TYPES == (
        "Requirement", "StakeholderNeed", "ArchitectureElement", "TestCase",
        "Adr", "Risk", "Issue", "Goal", "Icd", "GlossaryTerm",
    )


def test_synthetic_status_is_locked_and_workflow_editable() -> None:
    status = synthetic_status_attribute()
    assert status["name"] == "status"
    assert status["kind"] == "core"
    assert status["locked"] is True
    assert status["editable"] == "workflow"
    assert status["visible"] is True


@pytest.mark.django_db
def test_every_attribute_is_core_and_names_are_unique() -> None:
    for item_type in BOOTSTRAP_ITEM_TYPES:
        attributes = introspect_core_attributes(item_type, "standard")
        assert attributes, f"{item_type} produced no attributes"
        assert all(a["kind"] == "core" for a in attributes)
        names = [a["name"] for a in attributes]
        assert len(names) == len(set(names)), item_type


@pytest.mark.django_db
def test_dropped_status_columns_are_never_introspected() -> None:
    """P1/D6: the Datenmodell-Konsolidierung drops these columns; the bootstrap
    must produce the same output before and after that migration."""
    for item_type in BOOTSTRAP_ITEM_TYPES:
        attributes = introspect_core_attributes(item_type, "standard")
        by_name = {a["name"]: a for a in attributes}
        assert "lifecycle_status" not in by_name, item_type
        assert by_name["status"]["locked"] is True, item_type
        assert by_name["status"]["editable"] == "workflow", item_type


@pytest.mark.django_db
def test_infrastructure_columns_are_excluded() -> None:
    attributes = introspect_core_attributes("Requirement", "standard")
    names = {a["name"] for a in attributes}
    assert not (names & (EXCLUDED_MODEL_FIELDS - {"status"}))


@pytest.mark.django_db
def test_choices_become_enum_options() -> None:
    attributes = {a["name"]: a for a in introspect_core_attributes("Risk", "standard")}
    probability = attributes["probability"]
    assert probability["type"] == "enum"
    assert {o["value"] for o in probability["options"]} == {"low", "medium", "high"}
    assert all(o["label_de"] and o["label_en"] for o in probability["options"])


@pytest.mark.django_db
def test_text_field_becomes_textarea_and_charfield_becomes_text() -> None:
    attributes = {a["name"]: a for a in introspect_core_attributes("Adr", "standard")}
    assert attributes["title"]["type"] == "text"
    assert attributes["description"]["type"] == "textarea"


@pytest.mark.django_db
def test_curated_widgets_are_added_with_their_bound_fields() -> None:
    risk = {a["name"]: a for a in introspect_core_attributes("Risk", "standard")}
    assert risk["risk_matrix"]["type"] == "widget"
    assert risk["risk_matrix"]["widget_key"] == "risk_matrix_rpz"
    assert risk["risk_matrix"]["fields"] == ["probability", "impact", "detection"]

    adr = {a["name"]: a for a in introspect_core_attributes("Adr", "standard")}
    assert adr["decision_record"]["widget_key"] == "markdown_tab_group"
    assert adr["decision_record"]["fields"] == ["description", "context", "consequences"]

    testcase = {a["name"]: a for a in introspect_core_attributes("TestCase", "standard")}
    assert testcase["steps"]["widget_key"] == "steps_editor"
    assert testcase["steps"]["fields"] == ["steps_data"]


@pytest.mark.django_db
def test_preset_mandatory_fields_drive_required_on_requirement() -> None:
    minimal = {a["name"]: a for a in introspect_core_attributes("Requirement", "minimal")}
    standard = {a["name"]: a for a in introspect_core_attributes("Requirement", "standard")}
    assert minimal["title"]["required"] is True
    assert minimal["description"]["required"] is False
    assert standard["description"]["required"] is True
    assert standard["acceptance_criteria"]["required"] is True


@pytest.mark.django_db
def test_command_seeds_thirty_rows_per_tenant(tenant) -> None:
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    rows = GlobalAttributeDefinition.unscoped.filter(tenant_id=tenant.id)
    assert rows.count() == len(BOOTSTRAP_ITEM_TYPES) * len(PRESETS)


@pytest.mark.django_db
def test_command_is_idempotent_and_preserves_curated_meta(tenant) -> None:
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    row = GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant.id, item_type="Risk", preset="standard"
    )
    attributes = row.definition_json["attributes"]
    for attribute in attributes:
        if attribute["name"] == "title":
            attribute["section"] = "header"
    row.definition_json = {"attributes": attributes}
    row.save(update_fields=["definition_json"])

    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    row.refresh_from_db()
    by_name = {a["name"]: a for a in row.definition_json["attributes"]}
    assert by_name["title"]["section"] == "header"
    assert GlobalAttributeDefinition.unscoped.filter(tenant_id=tenant.id).count() == 30


@pytest.mark.django_db
def test_sync_new_fields_appends_without_touching_existing_entries(tenant) -> None:
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))
    row = GlobalAttributeDefinition.unscoped.get(
        tenant_id=tenant.id, item_type="Risk", preset="standard"
    )
    kept = [a for a in row.definition_json["attributes"] if a["name"] != "detection"]
    for attribute in kept:
        attribute["audience"] = "expert"
    row.definition_json = {"attributes": kept}
    row.save(update_fields=["definition_json"])

    call_command(
        "bootstrap_attribute_definitions", "--tenant", str(tenant.id), "--sync-new-fields"
    )
    row.refresh_from_db()
    by_name = {a["name"]: a for a in row.definition_json["attributes"]}
    assert "detection" in by_name
    assert by_name["probability"]["audience"] == "expert"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest attribute_definitions/tests/test_bootstrap_command.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'attribute_definitions.management'`

- [ ] **Step 3: Write the implementation**

Create `backend/attribute_definitions/management/__init__.py` and `backend/attribute_definitions/management/commands/__init__.py` (both empty).

Create `backend/attribute_definitions/management/commands/bootstrap_attribute_definitions.py`:

```python
"""Seed the initial GlobalAttributeDefinition rows from model introspection.

Spec section 3.2 ("the cheap core list", Audit N4 step 1). Runs once per tenant
as part of the rollout, not live on every read: later new Django model fields
need an explicit ``--sync-new-fields`` run, which is deliberate — model fields
change rarely and an automatic sync would silently reintroduce columns an admin
had removed from the form.

Two design points that make this command order-independent with respect to the
Datenmodell-Konsolidierung spec:

1. ``status`` is NOT introspected from a column. It is injected synthetically
   (``locked``, ``editable="workflow"``) because the single status axis after
   that migration is ``WorkflowItemState.current_state``, not a per-model
   column. ``options`` stays empty: the concrete states come from the workflow
   definition, which is already their single source of truth.
2. Every column that migration drops is in ``EXCLUDED_MODEL_FIELDS``, so the
   output is byte-identical before and after it.

Models are resolved through ``apps.get_model`` with an ordered candidate list
because Adr / Risk / Issue / Goal currently live in ``application.models`` and
move to ``persistence.models`` in that same migration.
"""
from __future__ import annotations

import copy
from typing import Any

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import models, transaction

from attribute_definitions.global_definition_store import GlobalAttributeDefinitionStore
from attribute_definitions.models import GlobalAttributeDefinition
from attribute_definitions.schema import normalize_attribute
from persistence.models import Tenant
from presets.registry import PresetRegistry

BOOTSTRAP_ITEM_TYPES: tuple[str, ...] = (
    "Requirement",
    "StakeholderNeed",
    "ArchitectureElement",
    "TestCase",
    "Adr",
    "Risk",
    "Issue",
    "Goal",
    "Icd",
    "GlossaryTerm",
)

PRESETS: tuple[str, ...] = ("minimal", "standard", "extended")

#: Ordered ``(app_label, model_name)`` candidates per item type. The first that
#: resolves wins, so a model that moves between apps does not break the command.
MODEL_LOCATIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "Requirement": (("persistence", "Requirement"),),
    "StakeholderNeed": (("persistence", "StakeholderNeed"),),
    "ArchitectureElement": (("persistence", "ArchitectureElement"),),
    "TestCase": (("persistence", "TestCase"),),
    "GlossaryTerm": (("persistence", "GlossaryTerm"),),
    "Icd": (("icd", "Icd"),),
    "Adr": (("persistence", "Adr"), ("application", "Adr")),
    "Risk": (("persistence", "Risk"), ("application", "Risk")),
    "Issue": (("persistence", "Issue"), ("application", "Issue")),
    "Goal": (("persistence", "Goal"), ("application", "Goal")),
}

#: Columns that are never user-facing attributes. ``status`` and
#: ``lifecycle_status`` are here because they are the two status axes the
#: Datenmodell-Konsolidierung removes; ``status`` comes back synthetically.
EXCLUDED_MODEL_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "tenant",
        "tenant_id",
        "workspace",
        "workspace_id",
        "artifact",
        "artifact_id",
        "created_at",
        "modified_at",
        "updated_at",
        "created_by",
        "modified_by",
        "version",
        "lock_version",
        "status",
        "lifecycle_status",
        "risk_score",
        "severity",
        "term_fk",
    }
)

CLASSIFICATION_FIELDS: frozenset[str] = frozenset(
    {
        "category", "type", "level", "test_type", "element_type", "severity_level",
        "moscow_priority", "complexity_fibonacci", "verification_method",
        "probability", "impact", "detection",
    }
)

CHANGE_CONTROL_FIELDS: frozenset[str] = frozenset({"uid", "suspect", "baseline_id"})

#: Curated widget attributes (spec section 6.3). ``fields[]`` names the core
#: attributes the widget renders; the form renderer skips those individually so
#: they are not drawn twice.
WIDGET_ATTRIBUTES: dict[str, tuple[dict[str, Any], ...]] = {
    "Risk": (
        {
            "name": "risk_matrix",
            "kind": "core",
            "type": "widget",
            "widget_key": "risk_matrix_rpz",
            "fields": ["probability", "impact", "detection"],
            "section": "classification",
            "order": 10,
            "label": {"de": "Risikomatrix", "en": "Risk matrix"},
        },
    ),
    "Adr": (
        {
            "name": "decision_record",
            "kind": "core",
            "type": "widget",
            "widget_key": "markdown_tab_group",
            "fields": ["description", "context", "consequences"],
            "section": "general",
            "order": 10,
            "label": {"de": "Entscheidung", "en": "Decision"},
        },
    ),
    "TestCase": (
        {
            "name": "steps",
            "kind": "core",
            "type": "widget",
            "widget_key": "steps_editor",
            "fields": ["steps_data"],
            "section": "general",
            "order": 20,
            "label": {"de": "Testschritte", "en": "Test steps"},
        },
    ),
}

#: Model fields a widget consumes under a different attribute name, so the raw
#: column does not collide with the widget entry (TestCase.steps <-> the
#: ``steps`` widget). Maps ``item_type -> {model_field: attribute_name}``.
WIDGET_FIELD_ALIASES: dict[str, dict[str, str]] = {
    "TestCase": {"steps": "steps_data"},
}


def synthetic_status_attribute() -> dict[str, Any]:
    """The one systemobligatory attribute every type carries (spec section 3.1).

    ``options`` is empty on purpose: the reachable states come from the
    workflow definition for ``(workspace, item_type)``, which is their single
    source of truth. The renderer fills the select from there.
    """
    return normalize_attribute(
        {
            "name": "status",
            "kind": "core",
            "type": "enum",
            "options": [
                {"value": "__workflow__", "label_de": "Workflow", "label_en": "Workflow"}
            ],
            "required": True,
            "visible": True,
            "locked": True,
            "editable": "workflow",
            "section": "general",
            "order": -100,
            "label": {"de": "Status", "en": "Status"},
            "export": True,
        }
    )


def _resolve_model(item_type: str) -> type[models.Model]:
    for app_label, model_name in MODEL_LOCATIONS[item_type]:
        try:
            return apps.get_model(app_label, model_name)
        except LookupError:
            continue
    raise CommandError(
        f"Could not resolve a model for item type {item_type!r}; "
        f"tried {MODEL_LOCATIONS[item_type]}"
    )


def _attribute_type(field: models.Field) -> str | None:
    """Map a Django field onto an attribute ``type``, or None to skip it."""
    if getattr(field, "choices", None):
        return "enum"
    if isinstance(field, models.BooleanField):
        return "boolean"
    if isinstance(field, (models.DateField, models.DateTimeField)):
        return "date"
    if isinstance(
        field, (models.IntegerField, models.FloatField, models.DecimalField)
    ):
        return "number"
    if isinstance(field, models.TextField):
        return "textarea"
    if isinstance(field, (models.CharField, models.SlugField, models.EmailField)):
        return "text"
    if isinstance(field, (models.ForeignKey, models.OneToOneField)):
        related = field.related_model
        if related is not None and related.__name__ == "User":
            return "user"
        return "reference"
    if isinstance(field, models.UUIDField):
        return "reference"
    # JSONField and everything else has no basic renderer; a special case must
    # be registered as a widget in WIDGET_ATTRIBUTES instead.
    return None


def _options_from_choices(field: models.Field) -> list[dict[str, str]]:
    return [
        {"value": str(value), "label_de": str(label), "label_en": str(label)}
        for value, label in (field.choices or [])
    ]


def _section_for(name: str) -> str:
    if name in CLASSIFICATION_FIELDS:
        return "classification"
    if name in CHANGE_CONTROL_FIELDS:
        return "change_control"
    return "general"


def introspect_core_attributes(item_type: str, preset: str) -> list[dict[str, Any]]:
    """Return the normalized core attribute list for ``(item_type, preset)``.

    ``required`` comes from ``blank=False`` on the model, plus the preset's
    ``mandatory_fields`` for names that actually exist as columns. Names in
    ``mandatory_fields`` with no matching column (``priority``,
    ``classification``, ``traceability_target``, ``change_reason``) are ignored
    here and reported by the command as a configuration finding.
    """
    model = _resolve_model(item_type)
    aliases = WIDGET_FIELD_ALIASES.get(item_type, {})
    widget_field_names = {
        name
        for entry in WIDGET_ATTRIBUTES.get(item_type, ())
        for name in entry["fields"]
    }

    attributes: list[dict[str, Any]] = [synthetic_status_attribute()]
    order = 0
    for field in model._meta.get_fields():
        if not isinstance(field, models.Field) or field.auto_created:
            continue
        if field.name in EXCLUDED_MODEL_FIELDS:
            continue
        attribute_type = _attribute_type(field)
        name = aliases.get(field.name, field.name)
        if attribute_type is None:
            # Only keep an unrenderable column when a widget claims it.
            if name not in widget_field_names:
                continue
            attribute_type = "textarea"
        order += 1
        attributes.append(
            normalize_attribute(
                {
                    "name": name,
                    "kind": "core",
                    "type": attribute_type,
                    "options": _options_from_choices(field) if attribute_type == "enum" else [],
                    "required": not field.blank,
                    "visible": True,
                    "editable": True,
                    "section": _section_for(name),
                    "order": order,
                    "label": {"de": name, "en": name},
                    "ai_elicit": name in ("title", "description"),
                    "export": True,
                }
            )
        )

    for entry in WIDGET_ATTRIBUTES.get(item_type, ()):
        attributes.append(normalize_attribute(dict(entry, export=False)))

    mandatory = set(PresetRegistry().get_config(preset).mandatory_fields)
    for attribute in attributes:
        if attribute["name"] in mandatory:
            attribute["required"] = True

    attributes.sort(key=lambda a: (a["section"], a["order"], a["name"]))
    return attributes


def unmatched_mandatory_fields(item_type: str, preset: str) -> list[str]:
    """Preset ``mandatory_fields`` entries that have no matching attribute."""
    names = {a["name"] for a in introspect_core_attributes(item_type, preset)}
    return sorted(set(PresetRegistry().get_config(preset).mandatory_fields) - names)


class Command(BaseCommand):
    help = (
        "Seed GlobalAttributeDefinition rows from Django model introspection. "
        "Idempotent: existing rows are left alone unless --sync-new-fields."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--tenant",
            dest="tenant",
            default=None,
            help="Tenant UUID. Omit to bootstrap every tenant.",
        )
        parser.add_argument(
            "--sync-new-fields",
            action="store_true",
            dest="sync_new_fields",
            help=(
                "Append core attributes that exist on the model but not yet in "
                "the stored definition. Never modifies an existing entry."
            ),
        )

    def handle(self, *args, **options) -> None:
        store = GlobalAttributeDefinitionStore()
        tenant_ids = (
            [options["tenant"]]
            if options["tenant"]
            else list(Tenant.objects.values_list("id", flat=True))
        )
        created = updated = 0
        with transaction.atomic():
            for tenant_id in tenant_ids:
                for item_type in BOOTSTRAP_ITEM_TYPES:
                    for preset in PRESETS:
                        attributes = introspect_core_attributes(item_type, preset)
                        existing = store.get(tenant_id, item_type, preset)
                        if existing is None:
                            store.initialize(tenant_id, item_type, preset, attributes)
                            created += 1
                        elif options["sync_new_fields"]:
                            if self._append_missing(existing, attributes):
                                updated += 1

        for item_type in BOOTSTRAP_ITEM_TYPES:
            for preset in PRESETS:
                unmatched = unmatched_mandatory_fields(item_type, preset)
                if unmatched:
                    self.stdout.write(
                        self.style.WARNING(
                            f"{item_type}/{preset}: preset mandatory_fields name "
                            f"{unmatched} with no matching attribute — ignored"
                        )
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"bootstrap_attribute_definitions: {created} created, {updated} synced"
            )
        )

    @staticmethod
    def _append_missing(
        row: GlobalAttributeDefinition, introspected: list[dict[str, Any]]
    ) -> bool:
        """Append attributes the stored definition lacks. Returns True on change."""
        stored = list((row.definition_json or {}).get("attributes", []))
        known = {a["name"] for a in stored}
        additions = [copy.deepcopy(a) for a in introspected if a["name"] not in known]
        if not additions:
            return False
        stored.extend(additions)
        stored.sort(key=lambda a: (a["section"], a["order"], a["name"]))
        row.definition_json = {"attributes": stored}
        row.version = (row.version or 1) + 1
        row.save(update_fields=["definition_json", "version", "modified_at"])
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest attribute_definitions/tests/test_bootstrap_command.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Run the command against the dev database**

Run: `docker compose exec backend python manage.py bootstrap_attribute_definitions`
Expected: `bootstrap_attribute_definitions: 30 created, 0 synced` per tenant, plus warnings naming `['change_reason', 'classification', 'priority', 'traceability_target']` for the extended Requirement preset.

- [ ] **Step 6: Commit**

```bash
git add backend/attribute_definitions/management backend/attribute_definitions/tests/test_bootstrap_command.py
git commit -m "feat(attribute-definitions): add bootstrap introspection command"
```

---

### Task 7: `AttributeDefinitionService` — the Layer-2 facade

The single entry point every consumer uses (ADR-01). **These method names and signatures are quoted by the Tabellenansicht, Interview-Engine-Fix, Menschen-im-System and Rollenbasierte-Sichten plans — do not rename them.**

**Files:**
- Create: `backend/application/attribute_definition_service.py`
- Modify: `backend/application/cache_invalidation.py:66-82` (add `attribute_def_cache_key`, include it in `_workspace_keys`)
- Test: `backend/application/tests/test_attribute_definition_service.py`

**Interfaces:**
- Consumes: `attribute_definitions.global_definition_store.GlobalAttributeDefinitionStore`, `attribute_definitions.workspace_definition_store.WorkspaceAttributeDefinitionStore`, `attribute_definitions.field_validation.{validate_values, FieldValidationError}`, `attribute_definitions.schema.AttributeSchemaError`, `application.base.ServiceBase`, `presets.services.{get_preset, validate_downgrade}`, `application.cache_invalidation.invalidate_workspace_caches`, `audit.models.AuditEntry.OP_UPDATE`.
- Produces `class AttributeDefinitionService(ServiceBase)`:
  - `resolve(ctx, item_type: str, workspace_id: UUID) -> dict` → `{"item_type", "preset", "is_customized", "version", "attributes": list[dict]}`
  - `list_global(ctx, *, item_type: str | None = None, preset: str | None = None) -> list[dict]`
  - `get_global(ctx, item_type: str, preset: str) -> dict` → `{"item_type", "preset", "initialized", "version", "attributes"}`
  - `update_global(ctx, item_type: str, preset: str, attributes: list[dict]) -> dict` → `get_global` shape plus `"propagated_workspace_count": int`
  - `update_workspace(ctx, item_type: str, workspace_id: UUID, attributes: list[dict]) -> dict` → `resolve` shape
  - `reset_workspace(ctx, item_type: str, workspace_id: UUID) -> dict` → `resolve` shape
  - `validate_artifact_fields(ctx, item_type, workspace_id, changed_fields, existing) -> None`
  - `elicit_attributes(ctx, item_type: str, workspace_id: UUID) -> list[dict]`
  - `export_attributes(ctx, item_type: str, workspace_id: UUID) -> list[dict]`
  - `downgrade_warnings(ctx, workspace_id: UUID, target_preset: str) -> list[str]`
  - re-exports `AttributeSchemaError` and `FieldValidationError` for the adapters

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_attribute_definition_service.py`:

```python
"""AttributeDefinitionService — the single Layer-2 facade (ADR-01)."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from application.attribute_definition_service import (
    AttributeDefinitionService,
    AttributeSchemaError,
    FieldValidationError,
)
from application.base import PermissionDeniedError
from attribute_definitions.global_definition_store import GlobalAttributeDefinitionStore
from auth_tenancy.context import AuthContext
from persistence.models import Tenant, Workspace

TITLE = {"name": "title", "kind": "core", "type": "text", "required": True,
         "ai_elicit": True, "export": True}
NOTE = {"name": "note", "kind": "extended", "type": "text", "section": "extra"}


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")


@pytest.fixture
def workspace(tenant) -> Workspace:
    return Workspace.objects.create(
        tenant_id=tenant.id, name="ws", preset={"tier": "standard"}
    )


@pytest.fixture
def admin_ctx(tenant, workspace) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(), tenant_id=tenant.id,
        workspace_id=workspace.id, active_roles=("admin",),
    )


@pytest.fixture
def editor_ctx(tenant, workspace) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(), tenant_id=tenant.id,
        workspace_id=workspace.id, active_roles=("editor",),
    )


@pytest.fixture
def service() -> AttributeDefinitionService:
    return AttributeDefinitionService()


@pytest.fixture
def seeded(tenant) -> None:
    store = GlobalAttributeDefinitionStore()
    for preset in ("minimal", "standard", "extended"):
        store.initialize(tenant.id, "Risk", preset, [TITLE])


@pytest.mark.django_db
def test_resolve_materializes_for_the_workspace_preset(
    service, editor_ctx, workspace, seeded
) -> None:
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        out = service.resolve(editor_ctx, "Risk", workspace.id)
    assert out["item_type"] == "Risk"
    assert out["preset"] == "standard"
    assert out["is_customized"] is False
    assert [a["name"] for a in out["attributes"]] == ["title"]


@pytest.mark.django_db
def test_resolve_is_allowed_for_a_non_admin(service, editor_ctx, workspace, seeded) -> None:
    """Reading the definition is what applying it requires — never admin-only."""
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        service.resolve(editor_ctx, "Risk", workspace.id)


@pytest.mark.django_db
def test_get_global_requires_admin(service, editor_ctx, seeded) -> None:
    with pytest.raises(PermissionDeniedError):
        service.get_global(editor_ctx, "Risk", "standard")


@pytest.mark.django_db
def test_get_global_of_a_missing_row_reports_uninitialized(service, admin_ctx) -> None:
    out = service.get_global(admin_ctx, "Icd", "minimal")
    assert out == {
        "item_type": "Icd", "preset": "minimal", "initialized": False,
        "version": 0, "attributes": [],
    }


@pytest.mark.django_db
def test_update_global_requires_admin(service, editor_ctx, seeded) -> None:
    with pytest.raises(PermissionDeniedError):
        service.update_global(editor_ctx, "Risk", "standard", [TITLE])


@pytest.mark.django_db
def test_update_global_returns_the_propagated_count(
    service, admin_ctx, editor_ctx, workspace, seeded
) -> None:
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        service.resolve(editor_ctx, "Risk", workspace.id)
        out = service.update_global(
            admin_ctx, "Risk", "standard", [dict(TITLE, section="header")]
        )
    assert out["propagated_workspace_count"] == 1
    assert out["version"] == 2


@pytest.mark.django_db
def test_update_global_writes_an_audit_entry_with_the_update_op(
    service, admin_ctx, seeded
) -> None:
    """#265: an undeclared op string 500s after the mutation. Only OP_UPDATE."""
    with patch.object(AttributeDefinitionService, "_audit") as audit:
        service.update_global(admin_ctx, "Risk", "standard", [dict(TITLE, order=4)])
    assert audit.call_args.kwargs["operation"] == "update"
    assert audit.call_args.kwargs["entity_type"] == "GlobalAttributeDefinition"


@pytest.mark.django_db
def test_update_workspace_sets_is_customized_and_invalidates_the_cache(
    service, admin_ctx, workspace, seeded
) -> None:
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        service.resolve(admin_ctx, "Risk", workspace.id)
        with patch(
            "application.attribute_definition_service.invalidate_workspace_caches"
        ) as invalidate:
            out = service.update_workspace(
                admin_ctx, "Risk", workspace.id, [TITLE, NOTE]
            )
    assert out["is_customized"] is True
    invalidate.assert_called_once_with(str(workspace.id))


@pytest.mark.django_db
def test_reset_workspace_restores_the_global(
    service, admin_ctx, workspace, seeded
) -> None:
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        service.resolve(admin_ctx, "Risk", workspace.id)
        service.update_workspace(admin_ctx, "Risk", workspace.id, [TITLE, NOTE])
        out = service.reset_workspace(admin_ctx, "Risk", workspace.id)
    assert out["is_customized"] is False
    assert [a["name"] for a in out["attributes"]] == ["title"]


@pytest.mark.django_db
def test_update_workspace_rejects_a_core_rename_with_a_schema_error(
    service, admin_ctx, workspace, seeded
) -> None:
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        service.resolve(admin_ctx, "Risk", workspace.id)
        with pytest.raises(AttributeSchemaError):
            service.update_workspace(
                admin_ctx, "Risk", workspace.id,
                [{"name": "headline", "kind": "core", "type": "text"}],
            )


@pytest.mark.django_db
def test_validate_artifact_fields_on_create_demands_required_fields(
    service, editor_ctx, workspace, seeded
) -> None:
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        with pytest.raises(FieldValidationError) as exc:
            service.validate_artifact_fields(
                editor_ctx, "Risk", workspace.id, {}, None
            )
    assert "title" in exc.value.errors


@pytest.mark.django_db
def test_validate_artifact_fields_on_update_skips_untouched_fields(
    service, editor_ctx, workspace, seeded
) -> None:
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        service.validate_artifact_fields(
            editor_ctx, "Risk", workspace.id, {"description": "d"}, {"title": ""}
        )


@pytest.mark.django_db
def test_elicit_attributes_returns_only_ai_elicit_entries_in_section_order(
    service, editor_ctx, workspace, tenant
) -> None:
    GlobalAttributeDefinitionStore().initialize(
        tenant.id, "Risk", "standard",
        [TITLE, dict(NOTE, ai_elicit=True), {"name": "quiet", "kind": "extended",
                                             "type": "text", "section": "zzz"}],
    )
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        out = service.elicit_attributes(editor_ctx, "Risk", workspace.id)
    assert [a["name"] for a in out] == ["note", "title"]


@pytest.mark.django_db
def test_export_attributes_returns_only_export_entries(
    service, editor_ctx, workspace, tenant
) -> None:
    GlobalAttributeDefinitionStore().initialize(
        tenant.id, "Risk", "standard", [TITLE, NOTE],
    )
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "standard"
        out = service.export_attributes(editor_ctx, "Risk", workspace.id)
    assert [a["name"] for a in out] == ["title"]


@pytest.mark.django_db
def test_downgrade_warnings_merges_the_preset_check_with_the_attribute_probe(
    service, admin_ctx, workspace, tenant
) -> None:
    store = GlobalAttributeDefinitionStore()
    store.initialize(tenant.id, "Risk", "extended", [TITLE, NOTE])
    store.initialize(tenant.id, "Risk", "minimal", [TITLE])
    with patch("presets.services.get_preset") as get_preset:
        get_preset.return_value.preset = "extended"
        service.resolve(admin_ctx, "Risk", workspace.id)
        with patch("presets.services.validate_downgrade", return_value=["baselines"]):
            warnings = service.downgrade_warnings(admin_ctx, workspace.id, "minimal")
    assert "baselines" in warnings
    assert any("note" in w for w in warnings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest application/tests/test_attribute_definition_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.attribute_definition_service'`

- [ ] **Step 3: Add the cache key**

In `backend/application/cache_invalidation.py`, after `workflow_def_cache_key` (line 68-70) add:

```python
def attribute_def_cache_key(workspace_id: str) -> str:
    """Return the shared-cache key for a workspace's resolved attribute definitions.

    One key per workspace covers every item type: an admin edit to one type's
    definition is rare and re-resolving the others costs one indexed query each.
    """
    return f"{_KEY_PREFIX}:attribute-def:{workspace_id}"
```

and extend `_workspace_keys` to:

```python
def _workspace_keys(workspace_id: str) -> list[str]:
    """Return every shared-cache key derived from *workspace_id*."""
    return [
        preset_cache_key(workspace_id),
        terminology_cache_key(workspace_id),
        features_cache_key(workspace_id),
        workflow_def_cache_key(workspace_id),
        attribute_def_cache_key(workspace_id),
    ]
```

Add `"attribute_def_cache_key"` to the module's `__all__` list.

- [ ] **Step 4: Write the service**

Create `backend/application/attribute_definition_service.py`:

```python
"""COMP-AS-ATD AttributeDefinitionService — the single facade for attribute
definitions (spec sections 5, 7 and 9).

ADR-01: REST views, MCP tools, the interview protocol and the export service all
go through this class; none of them touches ``attribute_definitions.models``.

Permission model, deliberately asymmetric:
  * **reads of the resolved definition** (``resolve``, ``elicit_attributes``,
    ``export_attributes``, ``validate_artifact_fields``) are open to any
    authenticated tenant member — applying a configuration to your own data is
    exactly what a non-admin needs it for. Gating them on ``admin`` would make
    the configured form unusable by the users it constrains (the same reasoning
    the removed ``AttributeVisibilityConfigService.hidden_attribute_names``
    carried).
  * **management** (``list_global``, ``get_global``, ``update_global``,
    ``update_workspace``, ``reset_workspace``) requires ``admin``.

Audit: every mutation writes ``AuditEntry.OP_UPDATE``. No new ``op`` choice is
introduced on purpose — an undeclared ``operation=`` string fails ``full_clean``
and 500s the whole transaction *after* the mutation succeeded (issue #265).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from django.core.cache import cache
from django.db import transaction

from attribute_definitions.field_validation import (
    FieldValidationError,
    validate_values,
)
from attribute_definitions.global_definition_store import (
    AttributeDefinitionNotFound,
    GlobalAttributeDefinitionStore,
)
from attribute_definitions.schema import AttributeSchemaError
from attribute_definitions.workspace_definition_store import (
    WorkspaceAttributeDefinitionStore,
)
from audit.models import AuditEntry
from auth_tenancy.context import AuthContext

from application.base import ServiceBase
from application.cache_invalidation import (
    attribute_def_cache_key,
    invalidate_workspace_caches,
)

#: Resolved definitions are read on every form load; 10 minutes is long enough
#: to matter and short enough that a missed invalidation self-heals.
_CACHE_TTL_SECONDS = 600


class AttributeDefinitionService(ServiceBase):
    """Read, manage and apply attribute definitions."""

    def __init__(
        self,
        global_store: GlobalAttributeDefinitionStore | None = None,
        workspace_store: WorkspaceAttributeDefinitionStore | None = None,
    ) -> None:
        self._global = global_store or GlobalAttributeDefinitionStore()
        self._workspace = workspace_store or WorkspaceAttributeDefinitionStore()

    # ---- Helpers ----------------------------------------------------------

    @staticmethod
    def _workspace_preset(workspace_id: UUID) -> str:
        """Resolve the workspace's rigor tier through the preset gate."""
        from presets.services import get_preset

        return get_preset(str(workspace_id)).preset

    @staticmethod
    def _attributes(row: Any) -> list[dict[str, Any]]:
        return list((row.definition_json or {}).get("attributes", []))

    def _workspace_payload(self, row: Any) -> dict[str, Any]:
        return {
            "item_type": row.item_type,
            "preset": row.preset,
            "is_customized": row.is_customized,
            "version": row.version,
            "attributes": self._attributes(row),
        }

    def _global_payload(
        self, item_type: str, preset: str, row: Any, *, propagated: int | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "item_type": item_type,
            "preset": preset,
            "initialized": row is not None,
            "version": row.version if row is not None else 0,
            "attributes": self._attributes(row) if row is not None else [],
        }
        if propagated is not None:
            payload["propagated_workspace_count"] = propagated
        return payload

    # ---- Read -------------------------------------------------------------

    def resolve(
        self, ctx: AuthContext, item_type: str, workspace_id: UUID
    ) -> dict[str, Any]:
        """Return the resolved (materialized) definition for the workspace.

        Cached per workspace under ``reqogniloom:attribute-def:{workspace_id}``;
        the entry is dropped by ``invalidate_workspace_caches`` on every write.

        Raises:
            AttributeDefinitionNotFound: no global default for the workspace's
                preset — the bootstrap command has not been run.
        """
        self._set_tenant_context(ctx)
        cache_key = attribute_def_cache_key(str(workspace_id))
        cached = cache.get(cache_key) or {}
        if item_type in cached:
            return cached[item_type]

        preset = self._workspace_preset(workspace_id)
        row = self._workspace.resolve(ctx.tenant_id, workspace_id, item_type, preset)
        payload = self._workspace_payload(row)
        cached[item_type] = payload
        cache.set(cache_key, cached, _CACHE_TTL_SECONDS)
        return payload

    def list_global(
        self,
        ctx: AuthContext,
        *,
        item_type: str | None = None,
        preset: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return every tenant-wide global default, optionally filtered."""
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        rows = self._global.list(ctx.tenant_id, item_type=item_type, preset=preset)
        return [self._global_payload(r.item_type, r.preset, r) for r in rows]

    def get_global(
        self, ctx: AuthContext, item_type: str, preset: str
    ) -> dict[str, Any]:
        """Return one global default, or an ``initialized: False`` stub.

        Never 404s on a missing row so the UI can offer an "Initialize"
        affordance — same contract as ``workflow-defaults/``.
        """
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        row = self._global.get(ctx.tenant_id, item_type, preset)
        return self._global_payload(item_type, preset, row)

    def elicit_attributes(
        self, ctx: AuthContext, item_type: str, workspace_id: UUID
    ) -> list[dict[str, Any]]:
        """Attributes the interview must ask for (``ai_elicit=true``).

        Order is the resolved definition's order, i.e. section order first —
        which is what the interview protocol uses as its phase order
        (spec section 7).
        """
        return [
            a
            for a in self.resolve(ctx, item_type, workspace_id)["attributes"]
            if a["ai_elicit"] and a["visible"]
        ]

    def export_attributes(
        self, ctx: AuthContext, item_type: str, workspace_id: UUID
    ) -> list[dict[str, Any]]:
        """Attributes ReqIF / CSV / Bundle export must carry (``export=true``)."""
        return [
            a
            for a in self.resolve(ctx, item_type, workspace_id)["attributes"]
            if a["export"]
        ]

    # ---- Write ------------------------------------------------------------

    def update_global(
        self,
        ctx: AuthContext,
        item_type: str,
        preset: str,
        attributes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Replace the tenant-wide default and propagate to on-default workspaces.

        Raises:
            PermissionDeniedError: caller is not an admin.
            AttributeDefinitionNotFound: the global row does not exist yet.
            AttributeSchemaError: malformed payload or a forbidden core/locked
                change.
        """
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        with transaction.atomic():
            row, propagated = self._global.update(
                ctx.tenant_id, item_type, preset, attributes
            )
            self._audit(
                ctx,
                operation=AuditEntry.OP_UPDATE,
                entity_type="GlobalAttributeDefinition",
                entity_id=row.id,
                details={
                    "item_type": item_type,
                    "preset": preset,
                    "propagated_workspace_count": propagated,
                },
            )
        for workspace_id in self._global.list_derived_workspace_ids(row):
            invalidate_workspace_caches(str(workspace_id))
        return self._global_payload(item_type, preset, row, propagated=propagated)

    def update_workspace(
        self,
        ctx: AuthContext,
        item_type: str,
        workspace_id: UUID,
        attributes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Persist a workspace override (sets ``is_customized=True``)."""
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        with transaction.atomic():
            row = self._workspace.update(
                ctx.tenant_id, workspace_id, item_type, attributes
            )
            self._audit(
                ctx,
                operation=AuditEntry.OP_UPDATE,
                entity_type="WorkspaceAttributeDefinition",
                entity_id=row.id,
                details={"item_type": item_type, "workspace_id": str(workspace_id)},
            )
        invalidate_workspace_caches(str(workspace_id))
        return self._workspace_payload(row)

    def reset_workspace(
        self, ctx: AuthContext, item_type: str, workspace_id: UUID
    ) -> dict[str, Any]:
        """Discard the override and re-copy the global default."""
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        with transaction.atomic():
            row = self._workspace.reset(ctx.tenant_id, workspace_id, item_type)
            self._audit(
                ctx,
                operation=AuditEntry.OP_UPDATE,
                entity_type="WorkspaceAttributeDefinition",
                entity_id=row.id,
                details={
                    "item_type": item_type,
                    "workspace_id": str(workspace_id),
                    "reset": True,
                },
            )
        invalidate_workspace_caches(str(workspace_id))
        return self._workspace_payload(row)

    # ---- Apply ------------------------------------------------------------

    def validate_artifact_fields(
        self,
        ctx: AuthContext,
        item_type: str,
        workspace_id: UUID,
        changed_fields: dict[str, Any],
        existing: dict[str, Any] | None,
    ) -> None:
        """Validate a create/update payload against the resolved definition.

        Called by every artifact create/update serializer and by the bulk
        endpoints. ``existing is None`` means create (all required attributes
        are demanded); otherwise only the fields the request carries are
        checked, so a save that never touches a required field is not blocked.

        Raises:
            FieldValidationError: ``.errors`` maps attribute name -> messages.
        """
        attributes = self.resolve(ctx, item_type, workspace_id)["attributes"]
        validate_values(attributes, changed_fields, existing)

    def downgrade_warnings(
        self, ctx: AuthContext, workspace_id: UUID, target_preset: str
    ) -> list[str]:
        """Preset-downgrade warnings, reusing the existing preset check.

        Spec section 9: the same ``validate_downgrade`` as workflow, reused —
        this method only appends the attribute-specific findings for every item
        type the workspace has resolved.
        """
        ServiceBase._assert_permission(ctx, "admin")
        self._set_tenant_context(ctx)
        from presets.services import validate_downgrade

        warnings = list(validate_downgrade(str(workspace_id), target_preset))
        for item_type in self._workspace.resolved_item_types(
            ctx.tenant_id, workspace_id
        ):
            missing = self._workspace.missing_attributes_for_preset(
                ctx.tenant_id, workspace_id, item_type, target_preset
            )
            if missing:
                warnings.append(
                    f"{item_type}: attribute(s) {', '.join(missing)} do not exist "
                    f"in preset '{target_preset}'"
                )
        return warnings


__all__ = [
    "AttributeDefinitionNotFound",
    "AttributeDefinitionService",
    "AttributeSchemaError",
    "FieldValidationError",
]
```

- [ ] **Step 5: Add the two store helpers the service calls**

In `backend/attribute_definitions/global_definition_store.py`, add to `GlobalAttributeDefinitionStore`:

```python
    def list_derived_workspace_ids(
        self, obj: GlobalAttributeDefinition
    ) -> list[str]:
        """Workspace ids whose definition mirrors *obj* — the cache-drop targets.

        A bulk ``QuerySet.update()`` bypasses ``save()``/signals, so the shared
        cache is not invalidated by the propagation itself; the service walks
        this list explicitly (the same lesson as
        ``GlobalWorkflowDefinitionStore._propagate``).
        """
        return [
            str(ws_id)
            for ws_id in WorkspaceAttributeDefinition.unscoped.filter(
                source_global_id=obj.id, preset=obj.preset, is_customized=False
            ).values_list("workspace_id", flat=True)
        ]
```

In `backend/attribute_definitions/workspace_definition_store.py`, add to `WorkspaceAttributeDefinitionStore`:

```python
    def resolved_item_types(
        self, tenant_id: UUID | str, workspace_id: UUID | str
    ) -> list[str]:
        """Item types this workspace has already materialized a definition for."""
        return sorted(
            WorkspaceAttributeDefinition.unscoped.filter(
                tenant_id=tenant_id, workspace_id=workspace_id
            ).values_list("item_type", flat=True)
        )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `docker compose exec backend pytest application/tests/test_attribute_definition_service.py attribute_definitions/ -v`
Expected: PASS (all service tests plus the untouched store tests)

- [ ] **Step 7: Commit**

```bash
git add backend/application/attribute_definition_service.py backend/application/cache_invalidation.py backend/attribute_definitions backend/application/tests/test_attribute_definition_service.py
git commit -m "feat(attribute-definitions): add AttributeDefinitionService facade"
```

---

### Task 8: Data migration from `AttributeVisibilityConfig` + `CustomFieldDefinition`

Spec section 4 — hard migration, no coexistence phase. This task **only migrates**; the removal of the legacy tables is Task 9, so a dry run against a production copy can be validated before anything is dropped (spec section 10).

**Files:**
- Create: `backend/attribute_definitions/migrations/0003_migrate_legacy_field_config.py`
- Test: `backend/attribute_definitions/tests/test_legacy_migration.py`

**Interfaces:**
- Consumes: `attribute_definitions.management.commands.bootstrap_attribute_definitions.{BOOTSTRAP_ITEM_TYPES, PRESETS, introspect_core_attributes}`, `attribute_definitions.schema.normalize_attribute`.
- Produces: module-level functions in the migration, imported by the test:
  - `apply_visibility_config(global_row_attributes: list[dict], config_rows: list[dict]) -> list[dict]`
  - `custom_field_to_attribute(row: dict, order: int) -> dict`
  - `FIELD_TYPE_MAP: dict[str, str]` = `{"text": "text", "number": "number", "dropdown": "enum"}`

- [ ] **Step 1: Write the failing test**

Create `backend/attribute_definitions/tests/test_legacy_migration.py`:

```python
"""Legacy field-config migration (spec section 4)."""
from __future__ import annotations

import importlib
import uuid

import pytest

from attribute_definitions.models import (
    GlobalAttributeDefinition,
    WorkspaceAttributeDefinition,
)
from attribute_definitions.schema import normalize_attribute
from persistence.models import (
    AttributeVisibilityConfig,
    CustomFieldDefinition,
    Tenant,
    Workspace,
)

migration = importlib.import_module(
    "attribute_definitions.migrations.0003_migrate_legacy_field_config"
)


def test_field_type_map_is_exactly_the_spec_mapping() -> None:
    assert migration.FIELD_TYPE_MAP == {
        "text": "text", "number": "number", "dropdown": "enum"
    }


def test_apply_visibility_config_sets_visible_and_required() -> None:
    attributes = [normalize_attribute({"name": "uid", "kind": "core", "type": "text"})]
    out = migration.apply_visibility_config(
        attributes,
        [{"attribute_name": "uid", "is_visible": False, "is_required": True}],
    )
    assert out[0]["visible"] is False
    assert out[0]["required"] is True


def test_apply_visibility_config_never_touches_a_locked_attribute() -> None:
    locked = normalize_attribute({
        "name": "status", "kind": "core", "type": "enum", "locked": True,
        "editable": "workflow",
        "options": [{"value": "d", "label_de": "D", "label_en": "D"}],
    })
    out = migration.apply_visibility_config(
        [locked], [{"attribute_name": "status", "is_visible": False, "is_required": False}]
    )
    assert out[0]["visible"] is True


def test_apply_visibility_config_ignores_an_unknown_attribute_name() -> None:
    attributes = [normalize_attribute({"name": "uid", "kind": "core", "type": "text"})]
    out = migration.apply_visibility_config(
        attributes, [{"attribute_name": "gone", "is_visible": False, "is_required": True}]
    )
    assert [a["name"] for a in out] == ["uid"]
    assert out[0]["visible"] is True


def test_custom_field_to_attribute_maps_dropdown_to_enum_with_options() -> None:
    out = migration.custom_field_to_attribute(
        {"name": "Kostenstelle", "field_type": "dropdown", "is_required": True,
         "options": ["A", "B"], "order": 3},
        order=3,
    )
    assert out["kind"] == "extended"
    assert out["type"] == "enum"
    assert out["required"] is True
    assert out["options"] == [
        {"value": "A", "label_de": "A", "label_en": "A"},
        {"value": "B", "label_de": "B", "label_en": "B"},
    ]
    assert out["section"] == "custom"


def test_custom_field_to_attribute_maps_text_and_number() -> None:
    assert migration.custom_field_to_attribute(
        {"name": "n", "field_type": "number", "is_required": False,
         "options": [], "order": 0}, order=0
    )["type"] == "number"
    assert migration.custom_field_to_attribute(
        {"name": "t", "field_type": "text", "is_required": False,
         "options": [], "order": 0}, order=0
    )["type"] == "text"


@pytest.mark.django_db
def test_forward_migration_seeds_globals_and_folds_in_legacy_config() -> None:
    tenant = Tenant.objects.create(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")
    workspace = Workspace.objects.create(
        tenant_id=tenant.id, name="ws", preset={"tier": "standard"}
    )
    AttributeVisibilityConfig.objects.create(
        tenant_id=tenant.id, entity_type="Requirement",
        attribute_name="verification_method", is_visible=False, is_required=False,
    )
    CustomFieldDefinition.objects.create(
        tenant_id=tenant.id, workspace=workspace, name="Kostenstelle",
        field_type="dropdown", is_required=True, options=["A", "B"], order=1,
    )

    from django.apps import apps as global_apps

    migration.forwards(global_apps, None)

    assert GlobalAttributeDefinition.unscoped.filter(tenant_id=tenant.id).count() == 30
    for preset in ("minimal", "standard", "extended"):
        row = GlobalAttributeDefinition.unscoped.get(
            tenant_id=tenant.id, item_type="Requirement", preset=preset
        )
        by_name = {a["name"]: a for a in row.definition_json["attributes"]}
        assert by_name["verification_method"]["visible"] is False

    ws_rows = WorkspaceAttributeDefinition.unscoped.filter(workspace_id=workspace.id)
    assert ws_rows.count() == 10
    for ws_row in ws_rows:
        by_name = {a["name"]: a for a in ws_row.definition_json["attributes"]}
        assert by_name["Kostenstelle"]["kind"] == "extended"
        assert by_name["Kostenstelle"]["type"] == "enum"
        assert ws_row.is_customized is True


@pytest.mark.django_db
def test_forward_migration_is_idempotent() -> None:
    tenant = Tenant.objects.create(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")
    from django.apps import apps as global_apps

    migration.forwards(global_apps, None)
    migration.forwards(global_apps, None)
    assert GlobalAttributeDefinition.unscoped.filter(tenant_id=tenant.id).count() == 30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest attribute_definitions/tests/test_legacy_migration.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'attribute_definitions.migrations.0003_migrate_legacy_field_config'`

- [ ] **Step 3: Write the migration**

Create `backend/attribute_definitions/migrations/0003_migrate_legacy_field_config.py`:

```python
"""Fold AttributeVisibilityConfig + CustomFieldDefinition into the new model.

Spec section 4, hard migration:

* ``AttributeVisibilityConfig`` -> ``visible``/``required`` on the matching CORE
  attribute of all three presets of ``(tenant, entity_type)``. A ``locked``
  attribute is skipped: its ``visible``/``required`` are invariants, and a
  legacy row that hid the status field would break the workflow UI.
* ``CustomFieldDefinition`` -> ``kind="extended"`` entries in section
  ``"custom"``, appended to the WORKSPACE definition of every item type (the
  legacy model's own docstring: "a definition applies to *all* artifacts of the
  workspace"). Those workspace rows are marked ``is_customized=True`` so a
  later global edit does not silently wipe the migrated custom fields.
* ``CustomFieldValue`` keeps every value; only its link changes, in the
  persistence migration that drops the legacy tables (Decision D3).

Introspection caveat, accepted deliberately: seeding uses the *live* models via
``introspect_core_attributes`` rather than the historical models this migration
is handed. That is safe here because the seeded rows are configuration, not
user data, and it keeps the rollout reproducible from a single ``migrate`` —
the alternative (require an out-of-band management-command run first) makes a
fresh install order-dependent.
"""
from __future__ import annotations

from typing import Any

from django.db import migrations

from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
    BOOTSTRAP_ITEM_TYPES,
    PRESETS,
    introspect_core_attributes,
)
from attribute_definitions.schema import normalize_attribute

FIELD_TYPE_MAP: dict[str, str] = {
    "text": "text",
    "number": "number",
    "dropdown": "enum",
}

CUSTOM_FIELD_SECTION = "custom"


def apply_visibility_config(
    global_row_attributes: list[dict[str, Any]], config_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return *global_row_attributes* with the legacy visibility flags applied."""
    by_name = {a["name"]: a for a in global_row_attributes}
    for row in config_rows:
        attribute = by_name.get(row["attribute_name"])
        if attribute is None or attribute["locked"]:
            continue
        attribute["visible"] = bool(row["is_visible"])
        attribute["required"] = bool(row["is_required"])
    return list(by_name.values())


def custom_field_to_attribute(row: dict[str, Any], order: int) -> dict[str, Any]:
    """Convert one legacy CustomFieldDefinition row into an extended attribute."""
    field_type = FIELD_TYPE_MAP.get(row["field_type"], "text")
    options = (
        [
            {"value": str(o), "label_de": str(o), "label_en": str(o)}
            for o in (row.get("options") or [])
        ]
        if field_type == "enum"
        else []
    )
    return normalize_attribute(
        {
            "name": row["name"],
            "kind": "extended",
            "type": field_type,
            "options": options,
            "required": bool(row["is_required"]),
            "visible": True,
            "editable": True,
            "section": CUSTOM_FIELD_SECTION,
            "order": order,
            "label": {"de": row["name"], "en": row["name"]},
            "export": True,
        }
    )


def forwards(apps, schema_editor) -> None:
    Tenant = apps.get_model("persistence", "Tenant")
    Workspace = apps.get_model("persistence", "Workspace")
    AttributeVisibilityConfig = apps.get_model("persistence", "AttributeVisibilityConfig")
    CustomFieldDefinition = apps.get_model("persistence", "CustomFieldDefinition")
    GlobalAttributeDefinition = apps.get_model(
        "attribute_definitions", "GlobalAttributeDefinition"
    )
    WorkspaceAttributeDefinition = apps.get_model(
        "attribute_definitions", "WorkspaceAttributeDefinition"
    )

    for tenant_id in Tenant.objects.values_list("id", flat=True):
        visibility_by_type: dict[str, list[dict[str, Any]]] = {}
        for row in AttributeVisibilityConfig.objects.filter(tenant_id=tenant_id).values(
            "entity_type", "attribute_name", "is_visible", "is_required"
        ):
            visibility_by_type.setdefault(row["entity_type"], []).append(row)

        globals_by_key: dict[tuple[str, str], Any] = {}
        for item_type in BOOTSTRAP_ITEM_TYPES:
            for preset in PRESETS:
                attributes = apply_visibility_config(
                    introspect_core_attributes(item_type, preset),
                    visibility_by_type.get(item_type, []),
                )
                attributes.sort(key=lambda a: (a["section"], a["order"], a["name"]))
                obj, created = GlobalAttributeDefinition.objects.get_or_create(
                    tenant_id=tenant_id,
                    item_type=item_type,
                    preset=preset,
                    defaults={"definition_json": {"attributes": attributes}},
                )
                if not created:
                    obj.definition_json = {"attributes": attributes}
                    obj.save(update_fields=["definition_json"])
                globals_by_key[(item_type, preset)] = obj

        for workspace in Workspace.objects.filter(tenant_id=tenant_id):
            custom_rows = list(
                CustomFieldDefinition.objects.filter(workspace_id=workspace.id)
                .order_by("order", "name")
                .values("name", "field_type", "is_required", "options", "order")
            )
            if not custom_rows:
                continue
            preset = (workspace.preset or {}).get("tier") or "standard"
            extended = [
                custom_field_to_attribute(row, index)
                for index, row in enumerate(custom_rows)
            ]
            for item_type in BOOTSTRAP_ITEM_TYPES:
                source = globals_by_key[(item_type, preset)]
                attributes = list(source.definition_json["attributes"]) + [
                    dict(a) for a in extended
                ]
                attributes.sort(key=lambda a: (a["section"], a["order"], a["name"]))
                WorkspaceAttributeDefinition.objects.update_or_create(
                    tenant_id=tenant_id,
                    workspace_id=workspace.id,
                    item_type=item_type,
                    defaults={
                        "preset": preset,
                        "definition_json": {"attributes": attributes},
                        "source_global": source,
                        "is_customized": True,
                    },
                )


def backwards(apps, schema_editor) -> None:
    """Drop everything this migration created.

    Reversible on purpose: the legacy tables still exist at this point (they are
    dropped one migration later), so a rollback loses no configuration.
    """
    apps.get_model("attribute_definitions", "WorkspaceAttributeDefinition").objects.all().delete()
    apps.get_model("attribute_definitions", "GlobalAttributeDefinition").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("attribute_definitions", "0002_attribute_definition_rls_policies"),
        ("persistence", "0003_rls_policies"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest attribute_definitions/tests/test_legacy_migration.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Dry-run against a copy of the production data**

Spec section 10 requires this before rollout.

Run:
```bash
docker compose exec postgres pg_dump -U postgres reqogniloom > /tmp/preprod.sql
docker compose exec postgres createdb -U postgres reqogniloom_dryrun
docker compose exec -T postgres psql -U postgres reqogniloom_dryrun < /tmp/preprod.sql
docker compose exec -e DB_NAME=reqogniloom_dryrun backend python manage.py migrate attribute_definitions
docker compose exec -e DB_NAME=reqogniloom_dryrun backend python manage.py shell -c "from attribute_definitions.models import GlobalAttributeDefinition, WorkspaceAttributeDefinition; print(GlobalAttributeDefinition.unscoped.count(), WorkspaceAttributeDefinition.unscoped.count())"
```
Expected: `30 * <tenant count>` globals and one workspace row per `(workspace, item_type)` that had custom fields. Record the numbers in the PR description.

- [ ] **Step 6: Commit**

```bash
git add backend/attribute_definitions/migrations/0003_migrate_legacy_field_config.py backend/attribute_definitions/tests/test_legacy_migration.py
git commit -m "feat(attribute-definitions): migrate legacy visibility and custom-field config"
```

---

### Task 9: Remove the legacy field-configuration mechanisms

Spec section 4: removed, not deprecated. Runs after Task 8 so the data is already migrated.

**Files:**
- Create: `backend/persistence/migrations/00NN_retire_legacy_field_config.py` (next free number)
- Modify: `backend/persistence/models.py:1656-1786` (delete `AttributeVisibilityConfig`, `CustomFieldDefinition`; change `CustomFieldValue`)
- Delete: `backend/application/attribute_visibility_service.py`, `backend/application/custom_field_service.py`, `backend/mcp_server/tools/custom_field.py`
- Modify: `backend/rest_api/views.py` (delete `AttributeVisibilityConfigViewSet` and the 3 custom-field views), `backend/rest_api/serializers.py`, `backend/rest_api/urls.py:187,264-281`
- Modify: `backend/mcp_server/tool_registry.py` (drop the `custom_field` prefix registration and its import)
- Modify: `backend/application/requirement_bundle_service.py:46-48` (via `attribute_visibility_service` import — see Task 14)
- Test: `backend/persistence/tests/test_retire_legacy_field_config.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `persistence.models.CustomFieldValue` with fields `artifact: FK`, `attribute_name: CharField(max_length=128)`, `value: TextField`; unique on `(artifact, attribute_name)`.

- [ ] **Step 1: Write the failing test**

Create `backend/persistence/tests/test_retire_legacy_field_config.py`:

```python
"""The legacy field-config models are gone; values survived (Decision D3)."""
from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, transaction

import persistence.models as models_module
from persistence.models import Artifact, CustomFieldValue, Tenant, Workspace


def test_legacy_models_are_removed() -> None:
    assert not hasattr(models_module, "AttributeVisibilityConfig")
    assert not hasattr(models_module, "CustomFieldDefinition")
    assert not hasattr(models_module, "CustomFieldType")


def test_custom_field_value_is_keyed_by_attribute_name() -> None:
    field_names = {f.name for f in CustomFieldValue._meta.get_fields()}
    assert "attribute_name" in field_names
    assert "definition" not in field_names


@pytest.mark.django_db
def test_one_value_per_artifact_and_attribute_name() -> None:
    tenant = Tenant.objects.create(name="t", slug=f"t-{uuid.uuid4().hex[:8]}")
    workspace = Workspace.objects.create(tenant_id=tenant.id, name="ws", preset={})
    artifact = Artifact.objects.create(
        tenant_id=tenant.id, workspace=workspace, artifact_type="Requirement",
        title="a",
    )
    CustomFieldValue.objects.create(
        tenant_id=tenant.id, artifact=artifact, attribute_name="Kostenstelle",
        value="A",
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CustomFieldValue.objects.create(
                tenant_id=tenant.id, artifact=artifact,
                attribute_name="Kostenstelle", value="B",
            )


def test_legacy_services_are_removed() -> None:
    import importlib

    for module in (
        "application.attribute_visibility_service",
        "application.custom_field_service",
        "mcp_server.tools.custom_field",
    ):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module)


def test_legacy_rest_routes_are_removed() -> None:
    from django.urls import NoReverseMatch, reverse

    for name in (
        "attribute-visibility-config-list",
        "workspace-custom-field-definitions",
        "custom-field-definition-detail",
    ):
        with pytest.raises(NoReverseMatch):
            reverse(name)


def test_custom_field_mcp_tools_are_gone() -> None:
    from mcp_server.management.commands.export_tool_manifest import build_manifest

    names = {tool["name"] for tool in build_manifest()["tools"]}
    assert not {n for n in names if n.startswith("custom_field.")}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest persistence/tests/test_retire_legacy_field_config.py -v`
Expected: FAIL — `AttributeVisibilityConfig` still exists on the module.

- [ ] **Step 3: Write the schema migration**

Determine the next number: `ls backend/persistence/migrations/ | sort | tail -3`. Create `backend/persistence/migrations/00NN_retire_legacy_field_config.py`:

```python
"""Retire AttributeVisibilityConfig / CustomFieldDefinition (spec section 4).

Decision D3: ``CustomFieldValue`` keeps every value, but its link changes from
``definition`` (FK into the dropped table) to ``attribute_name`` (the attribute
key that now lives in ``definition_json``). The spec's "CustomFieldValue stays
unchanged" and "CustomFieldDefinition is removed" cannot both hold literally —
an FK cannot outlive its target. This is the minimum change that keeps the
values.

Three ordered steps in one migration so no state exists where a value has
neither a definition nor a name:
  1. add the nullable ``attribute_name`` column,
  2. backfill it from ``CustomFieldDefinition.name``,
  3. make it non-null, swap the unique constraint, drop the two legacy tables.
"""
from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


def backfill_attribute_names(apps, schema_editor) -> None:
    CustomFieldValue = apps.get_model("persistence", "CustomFieldValue")
    CustomFieldDefinition = apps.get_model("persistence", "CustomFieldDefinition")
    names = dict(CustomFieldDefinition.objects.values_list("id", "name"))
    for value in CustomFieldValue.objects.all().iterator():
        value.attribute_name = names.get(value.definition_id, "")
        value.save(update_fields=["attribute_name"])
    # A value whose definition vanished has no attribute to bind to and is
    # unreachable from any form; drop it rather than ship an empty key that
    # would violate the new unique constraint.
    CustomFieldValue.objects.filter(attribute_name="").delete()


def noop_reverse(apps, schema_editor) -> None:
    """Irreversible by design: the definition rows are gone after this point."""
    raise migrations.exceptions.IrreversibleError(
        "Restore from a backup: the legacy field-config tables are dropped."
    )


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0003_rls_policies"),
        ("attribute_definitions", "0003_migrate_legacy_field_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="customfieldvalue",
            name="attribute_name",
            field=models.CharField(max_length=128, null=True),
        ),
        migrations.RunPython(backfill_attribute_names, noop_reverse),
        migrations.RemoveConstraint(
            model_name="customfieldvalue",
            name="uq_customfieldvalue_definition_artifact",
        ),
        migrations.RemoveField(model_name="customfieldvalue", name="definition"),
        migrations.AlterField(
            model_name="customfieldvalue",
            name="attribute_name",
            field=models.CharField(
                max_length=128,
                help_text="Attribute name from the resolved AttributeDefinition.",
            ),
        ),
        migrations.AddConstraint(
            model_name="customfieldvalue",
            constraint=models.UniqueConstraint(
                fields=["artifact", "attribute_name"],
                name="uq_customfieldvalue_artifact_attribute",
            ),
        ),
        migrations.DeleteModel(name="CustomFieldDefinition"),
        migrations.DeleteModel(name="AttributeVisibilityConfig"),
    ]
```

- [ ] **Step 4: Change the models**

In `backend/persistence/models.py`:
- delete `class CustomFieldType` (line 332-343), `class AttributeVisibilityConfig` (line 1656) and `class CustomFieldDefinition` (line 1724) in full, including their entries in the module `__all__`;
- replace the `definition` field of `CustomFieldValue` with:

```python
    attribute_name = models.CharField(
        max_length=128,
        help_text="Attribute name from the resolved AttributeDefinition.",
    )
```

- replace `CustomFieldValue.Meta.constraints` with:

```python
        constraints = [
            models.UniqueConstraint(
                fields=["artifact", "attribute_name"],
                name="uq_customfieldvalue_artifact_attribute",
            ),
        ]
```

- change `CustomFieldValue.__str__` to `return f"{self.attribute_name}={self.value!r}"`.

- [ ] **Step 5: Delete the dependent code**

```bash
git rm backend/application/attribute_visibility_service.py \
       backend/application/custom_field_service.py \
       backend/mcp_server/tools/custom_field.py \
       backend/application/tests/test_attribute_visibility_service.py \
       backend/application/tests/test_custom_field_service.py \
       backend/mcp_server/tests/test_custom_field_tools.py
```

Then remove, by exact symbol:
- `backend/rest_api/views.py` — the `AttributeVisibilityConfigViewSet` class and the three custom-field views (`WorkspaceCustomFieldDefinitionsView`, `CustomFieldDefinitionDetailView`, `ArtifactCustomFieldValuesView`), plus their imports;
- `backend/rest_api/serializers.py` — `AttributeVisibilityConfigSerializer`, `CustomFieldDefinitionSerializer`, `CustomFieldValueSerializer` and their `__all__` entries;
- `backend/rest_api/urls.py` — line 187 (`router.register(r"attribute-visibility-configs", ...)`) and lines 264-281 (the three custom-field paths), plus the now-unused imports;
- `backend/mcp_server/tool_registry.py` — the `from mcp_server.tools.custom_field import CustomFieldToolGroup` import and the `"custom_field": CustomFieldToolGroup(),` registration;
- `backend/mcp_server/workspace_scope.py` — any `custom_field.*` entry in `_TOOL_TARGETS` / the classification sets;
- `backend/mcp_server/tool_registry.py` — the `"custom_field.get"` / `"custom_field.query"` entries in `_READ_ONLY_TOOL_NAMES`.

- [ ] **Step 6: Run the migration and the tests**

Run:
```bash
docker compose exec backend python manage.py migrate persistence
docker compose exec backend pytest persistence/tests/test_retire_legacy_field_config.py rest_api/ mcp_server/ -q
```
Expected: PASS. Any residual import of a deleted symbol surfaces here as a collection error — fix by deleting the caller, never by re-adding the symbol.

- [ ] **Step 7: Verify the ADR-01 ratchet still holds**

Run: `docker compose exec backend pytest rest_api/tests/test_architecture.py -v`
Expected: PASS. If `test_ratchet_is_monotonic` fails, the deletions lowered a real count — lower the matching `MAX_ORM_LINES` / `MCP_TOOLS_MAX_ORM_LINES` entry to the reported actual value in this same commit.

- [ ] **Step 8: Commit**

```bash
git add -A backend
git commit -m "refactor(attribute-definitions): retire AttributeVisibilityConfig and CustomFieldDefinition"
```

---

## Phase B — REST and MCP surface

### Task 10: REST endpoints (global + workspace)

Spec section 5. Pattern taken verbatim from `backend/rest_api/global_default_views.py` (`_require_admin`, `build_error_response`, `detect_lang`). **The new file must contain zero `.objects.` / `.unscoped.` lines** — the ADR-01 ratchet caps a new `rest_api/` file at 0 (P4).

**Files:**
- Create: `backend/rest_api/attribute_definition_views.py`
- Modify: `backend/rest_api/urls.py` (register 4 routes)
- Test: `backend/rest_api/tests/test_attribute_definition_views.py`

**Interfaces:**
- Consumes: `application.attribute_definition_service.{AttributeDefinitionService, AttributeDefinitionNotFound, AttributeSchemaError}`, `rest_api.auth_enforcer.get_auth_context`, `rest_api.serializers.{build_error_response, detect_lang}`, `auth_tenancy.models.ROLE_ADMIN`.
- Produces these routes under `/api/v1/`:
  - `GET  attribute-defaults/` → `{"definitions": [...]}` (admin)
  - `GET  attribute-defaults/<str:item_type>/<str:preset>/` → global payload (admin, never 404)
  - `PUT  attribute-defaults/<str:item_type>/<str:preset>/` body `{"attributes": [...]}` → global payload + `propagated_workspace_count` (admin)
  - `GET  workspaces/<uuid:workspace_id>/attribute-definitions/<str:item_type>/` → resolved payload (any member)
  - `PUT  workspaces/<uuid:workspace_id>/attribute-definitions/<str:item_type>/` → resolved payload, `is_customized: true` (admin)
  - `POST workspaces/<uuid:workspace_id>/attribute-definitions/<str:item_type>/reset/` → resolved payload, `is_customized: false` (admin)
- URL names: `attribute-defaults-list`, `attribute-defaults-detail`, `workspace-attribute-definition`, `workspace-attribute-definition-reset`.

- [ ] **Step 1: Write the failing test**

Create `backend/rest_api/tests/test_attribute_definition_views.py`:

```python
"""REST surface for attribute definitions (spec section 5)."""
from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from attribute_definitions.global_definition_store import GlobalAttributeDefinitionStore

TITLE = {"name": "title", "kind": "core", "type": "text"}


@pytest.fixture
def seeded(tenant_fixture):
    store = GlobalAttributeDefinitionStore()
    for preset in ("minimal", "standard", "extended"):
        store.initialize(tenant_fixture.id, "Risk", preset, [TITLE])
    return store


@pytest.mark.django_db
def test_get_global_returns_an_uninitialized_stub_instead_of_404(admin_client) -> None:
    response = admin_client.get("/api/v1/attribute-defaults/Icd/minimal/")
    assert response.status_code == 200
    assert response.json()["initialized"] is False
    assert response.json()["attributes"] == []


@pytest.mark.django_db
def test_get_global_requires_admin(editor_client, seeded) -> None:
    response = editor_client.get("/api/v1/attribute-defaults/Risk/standard/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_list_globals(admin_client, seeded) -> None:
    response = admin_client.get("/api/v1/attribute-defaults/?item_type=Risk")
    assert response.status_code == 200
    assert len(response.json()["definitions"]) == 3


@pytest.mark.django_db
def test_put_global_updates_and_reports_the_propagated_count(admin_client, seeded) -> None:
    response = admin_client.put(
        "/api/v1/attribute-defaults/Risk/standard/",
        {"attributes": [dict(TITLE, required=True)]},
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["attributes"][0]["required"] is True
    assert body["propagated_workspace_count"] == 0
    assert body["version"] == 2


@pytest.mark.django_db
def test_put_global_rejects_a_core_rename_with_400(admin_client, seeded) -> None:
    response = admin_client.put(
        "/api/v1/attribute-defaults/Risk/standard/",
        {"attributes": [{"name": "headline", "kind": "core", "type": "text"}]},
        format="json",
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_put_global_of_an_uninitialized_row_is_404(admin_client) -> None:
    response = admin_client.put(
        "/api/v1/attribute-defaults/Icd/minimal/",
        {"attributes": [TITLE]},
        format="json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_put_global_without_an_attributes_key_is_400(admin_client, seeded) -> None:
    response = admin_client.put(
        "/api/v1/attribute-defaults/Risk/standard/", {}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_get_workspace_definition_is_open_to_a_non_admin(
    editor_client, workspace_fixture, seeded
) -> None:
    response = editor_client.get(
        f"/api/v1/workspaces/{workspace_fixture.id}/attribute-definitions/Risk/"
    )
    assert response.status_code == 200
    assert response.json()["is_customized"] is False


@pytest.mark.django_db
def test_put_workspace_definition_requires_admin(
    editor_client, workspace_fixture, seeded
) -> None:
    response = editor_client.put(
        f"/api/v1/workspaces/{workspace_fixture.id}/attribute-definitions/Risk/",
        {"attributes": [TITLE]},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_put_then_reset_workspace_definition(
    admin_client, workspace_fixture, seeded
) -> None:
    base = f"/api/v1/workspaces/{workspace_fixture.id}/attribute-definitions/Risk/"
    admin_client.get(base)
    put = admin_client.put(
        base,
        {"attributes": [TITLE, {"name": "note", "kind": "extended", "type": "text"}]},
        format="json",
    )
    assert put.status_code == 200
    assert put.json()["is_customized"] is True

    reset = admin_client.post(f"{base}reset/", {}, format="json")
    assert reset.status_code == 200
    assert reset.json()["is_customized"] is False
    assert [a["name"] for a in reset.json()["attributes"]] == ["title"]


@pytest.mark.django_db
def test_workspace_definition_without_a_global_is_404(
    admin_client, workspace_fixture
) -> None:
    response = admin_client.get(
        f"/api/v1/workspaces/{workspace_fixture.id}/attribute-definitions/Goal/"
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_unknown_workspace_uuid_is_404(admin_client, seeded) -> None:
    response = admin_client.get(
        f"/api/v1/workspaces/{uuid.uuid4()}/attribute-definitions/Risk/"
    )
    assert response.status_code == 404
```

The fixtures `admin_client`, `editor_client`, `tenant_fixture` and `workspace_fixture` already exist in `backend/rest_api/tests/conftest.py`; reuse them unchanged. If `workspace_fixture` is missing there, add it as a `Workspace.objects.create(tenant_id=tenant_fixture.id, name="ws", preset={"tier": "standard"})` fixture in the same conftest.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest rest_api/tests/test_attribute_definition_views.py -v`
Expected: FAIL — all requests return 404 (routes not registered).

- [ ] **Step 3: Write the views**

Create `backend/rest_api/attribute_definition_views.py`:

```python
"""REST endpoints for attribute definitions (spec section 5).

Shaped after ``rest_api/global_default_views.py``: the same admin gate, the same
``build_error_response`` envelope, the same "a missing global reads as
``initialized: false`` instead of 404" contract so the UI can offer an
Initialize affordance.

No ORM in this module by design (ADR-01, enforced by
``rest_api/tests/test_architecture.py::test_no_new_direct_orm_access``): every
read and write goes through ``AttributeDefinitionService``.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.attribute_definition_service import (
    AttributeDefinitionNotFound,
    AttributeDefinitionService,
    AttributeSchemaError,
)
from auth_tenancy.models import ROLE_ADMIN
from rest_api.auth_enforcer import get_auth_context
from rest_api.serializers import build_error_response, detect_lang


def _require_admin(request: Request):
    """Return ``(ctx, lang)`` or a 403 Response when the caller is not admin."""
    lang = detect_lang(request)
    ctx = get_auth_context(request)
    if not ctx.has_role(ROLE_ADMIN):
        return Response(
            build_error_response("PERMISSION_DENIED", lang, message="Admin role required."),
            status=status.HTTP_403_FORBIDDEN,
        )
    return ctx, lang


def _validation(lang: str, message: str) -> Response:
    return Response(
        build_error_response("VALIDATION_ERROR", lang, message=message),
        status=status.HTTP_400_BAD_REQUEST,
    )


def _not_found(lang: str, message: str) -> Response:
    return Response(
        build_error_response("NOT_FOUND", lang, message=message),
        status=status.HTTP_404_NOT_FOUND,
    )


def _read_attributes(request: Request, lang: str) -> tuple[list[dict[str, Any]] | None, Response | None]:
    """Extract and shape-check the ``attributes`` list of a PUT body."""
    payload = request.data if isinstance(request.data, dict) else {}
    attributes = payload.get("attributes")
    if not isinstance(attributes, list):
        return None, _validation(lang, "Body must be an object with an 'attributes' list.")
    return attributes, None


class AttributeDefaultsListView(APIView):
    """GET /attribute-defaults/ — list the tenant's global attribute defaults."""

    def get(self, request: Request) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, _lang = gate
        definitions = AttributeDefinitionService().list_global(
            ctx,
            item_type=request.query_params.get("item_type") or None,
            preset=request.query_params.get("preset") or None,
        )
        return Response({"definitions": definitions}, status=status.HTTP_200_OK)


class AttributeDefaultsDetailView(APIView):
    """GET/PUT /attribute-defaults/{item_type}/{preset}/ — one global default."""

    def get(self, request: Request, item_type: str, preset: str) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, _lang = gate
        return Response(
            AttributeDefinitionService().get_global(ctx, item_type, preset),
            status=status.HTTP_200_OK,
        )

    def put(self, request: Request, item_type: str, preset: str) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        attributes, error = _read_attributes(request, lang)
        if error is not None:
            return error
        try:
            payload = AttributeDefinitionService().update_global(
                ctx, item_type, preset, attributes
            )
        except AttributeDefinitionNotFound as exc:
            return _not_found(lang, str(exc))
        except AttributeSchemaError as exc:
            return _validation(lang, "; ".join(exc.errors))
        return Response(payload, status=status.HTTP_200_OK)


class WorkspaceAttributeDefinitionView(APIView):
    """GET/PUT /workspaces/{id}/attribute-definitions/{item_type}/.

    GET is open to every tenant member on purpose: applying the configuration to
    your own data is exactly what a non-admin needs it for. PUT is admin-only.
    """

    def get(self, request: Request, workspace_id: UUID, item_type: str) -> Response:
        lang = detect_lang(request)
        ctx = get_auth_context(request)
        try:
            payload = AttributeDefinitionService().resolve(ctx, item_type, workspace_id)
        except AttributeDefinitionNotFound as exc:
            return _not_found(lang, str(exc))
        return Response(payload, status=status.HTTP_200_OK)

    def put(self, request: Request, workspace_id: UUID, item_type: str) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        attributes, error = _read_attributes(request, lang)
        if error is not None:
            return error
        try:
            payload = AttributeDefinitionService().update_workspace(
                ctx, item_type, workspace_id, attributes
            )
        except AttributeDefinitionNotFound as exc:
            return _not_found(lang, str(exc))
        except AttributeSchemaError as exc:
            return _validation(lang, "; ".join(exc.errors))
        return Response(payload, status=status.HTTP_200_OK)


class WorkspaceAttributeDefinitionResetView(APIView):
    """POST /workspaces/{id}/attribute-definitions/{item_type}/reset/."""

    def post(self, request: Request, workspace_id: UUID, item_type: str) -> Response:
        gate = _require_admin(request)
        if isinstance(gate, Response):
            return gate
        ctx, lang = gate
        try:
            payload = AttributeDefinitionService().reset_workspace(
                ctx, item_type, workspace_id
            )
        except AttributeDefinitionNotFound as exc:
            return _not_found(lang, str(exc))
        return Response(payload, status=status.HTTP_200_OK)


__all__ = [
    "AttributeDefaultsDetailView",
    "AttributeDefaultsListView",
    "WorkspaceAttributeDefinitionResetView",
    "WorkspaceAttributeDefinitionView",
]
```

- [ ] **Step 4: Register the routes**

In `backend/rest_api/urls.py`, add the import next to the existing `from rest_api.global_default_views import (...)` block:

```python
from rest_api.attribute_definition_views import (
    AttributeDefaultsDetailView,
    AttributeDefaultsListView,
    WorkspaceAttributeDefinitionResetView,
    WorkspaceAttributeDefinitionView,
)
```

and add these four entries to `urlpatterns`, immediately before the `workflow-defaults/` block (the reset route must precede the detail route so `reset/` is not swallowed by the `<str:item_type>` converter — it is not, because the paths differ in depth, but keeping them adjacent makes the ordering obvious):

```python
    path(
        "attribute-defaults/",
        AttributeDefaultsListView.as_view(),
        name="attribute-defaults-list",
    ),
    path(
        "attribute-defaults/<str:item_type>/<str:preset>/",
        AttributeDefaultsDetailView.as_view(),
        name="attribute-defaults-detail",
    ),
    path(
        "workspaces/<uuid:workspace_id>/attribute-definitions/<str:item_type>/reset/",
        WorkspaceAttributeDefinitionResetView.as_view(),
        name="workspace-attribute-definition-reset",
    ),
    path(
        "workspaces/<uuid:workspace_id>/attribute-definitions/<str:item_type>/",
        WorkspaceAttributeDefinitionView.as_view(),
        name="workspace-attribute-definition",
    ),
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend pytest rest_api/tests/test_attribute_definition_views.py -v`
Expected: PASS (12 tests)

- [ ] **Step 6: Verify the ORM ratchet**

Run: `docker compose exec backend pytest rest_api/tests/test_architecture.py -v`
Expected: PASS. `attribute_definition_views.py` is absent from `MAX_ORM_LINES`, so its cap is 0 — a failure here means a stray model import or `.objects.` slipped in; route it through the service instead of allowlisting the file.

- [ ] **Step 7: Commit**

```bash
git add backend/rest_api/attribute_definition_views.py backend/rest_api/urls.py backend/rest_api/tests/test_attribute_definition_views.py
git commit -m "feat(attribute-definitions): add REST endpoints for global and workspace definitions"
```

---

### Task 11: Wire `validate_artifact_fields` into the artifact ViewSets

Spec section 5: called from every create/update serializer path. The seam already exists: `WorkflowTransitionsMixin._validate_patch_payload` (`backend/rest_api/mixins/workflow_transitions.py`) is the one place all nine `partial_update` methods in `backend/rest_api/views.py` already call. Extending that seam is one change instead of nine.

**Files:**
- Modify: `backend/rest_api/mixins/workflow_transitions.py` (add `_validate_attribute_definition`)
- Modify: `backend/rest_api/views.py` (call it from the 9 `create` methods; the 9 `partial_update` methods reach it through the existing mixin call)
- Test: `backend/rest_api/tests/test_attribute_field_validation.py`

**Interfaces:**
- Consumes: `application.attribute_definition_service.{AttributeDefinitionService, FieldValidationError, AttributeDefinitionNotFound}`.
- Produces on `WorkflowTransitionsMixin`:
  - `attribute_item_type: str | None = None` — class attribute each ViewSet sets (e.g. `"Requirement"`)
  - `_validate_attribute_definition(self, ctx, workspace_id, changed_fields, existing) -> Response | None` — returns a 400 `Response` on violation, `None` when clean

- [ ] **Step 1: Write the failing test**

Create `backend/rest_api/tests/test_attribute_field_validation.py`:

```python
"""validate_artifact_fields wired into the artifact ViewSets (spec section 5)."""
from __future__ import annotations

import pytest

from attribute_definitions.global_definition_store import GlobalAttributeDefinitionStore

TITLE = {"name": "title", "kind": "core", "type": "text", "required": True}
UID = {"name": "uid", "kind": "core", "type": "text",
       "validation": {"regex": r"^RISK-\d+$"}}
SAP = {"name": "sap_id", "kind": "extended", "type": "text", "required": True}


@pytest.fixture
def risk_definition(tenant_fixture):
    GlobalAttributeDefinitionStore().initialize(
        tenant_fixture.id, "Risk", "standard", [TITLE, UID, SAP]
    )


@pytest.mark.django_db
def test_create_without_a_required_extended_field_is_400(
    admin_client, workspace_fixture, risk_definition
) -> None:
    response = admin_client.post(
        "/api/v1/risks/",
        {"workspace_id": str(workspace_fixture.id), "title": "R"},
        format="json",
    )
    assert response.status_code == 400
    assert "sap_id" in response.json()["error"]["message"]


@pytest.mark.django_db
def test_create_with_every_required_field_succeeds(
    admin_client, workspace_fixture, risk_definition
) -> None:
    response = admin_client.post(
        "/api/v1/risks/",
        {"workspace_id": str(workspace_fixture.id), "title": "R",
         "custom_fields": {"sap_id": "S-1"}},
        format="json",
    )
    assert response.status_code == 201


@pytest.mark.django_db
def test_patch_that_does_not_touch_a_required_field_is_not_blocked(
    admin_client, workspace_fixture, risk_definition
) -> None:
    created = admin_client.post(
        "/api/v1/risks/",
        {"workspace_id": str(workspace_fixture.id), "title": "R",
         "custom_fields": {"sap_id": "S-1"}},
        format="json",
    ).json()
    response = admin_client.patch(
        f"/api/v1/risks/{created['id']}/", {"description": "d"}, format="json"
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_patch_that_clears_a_required_field_is_400(
    admin_client, workspace_fixture, risk_definition
) -> None:
    created = admin_client.post(
        "/api/v1/risks/",
        {"workspace_id": str(workspace_fixture.id), "title": "R",
         "custom_fields": {"sap_id": "S-1"}},
        format="json",
    ).json()
    response = admin_client.patch(
        f"/api/v1/risks/{created['id']}/", {"title": ""}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_patch_violating_a_regex_rule_is_400(
    admin_client, workspace_fixture, risk_definition
) -> None:
    created = admin_client.post(
        "/api/v1/risks/",
        {"workspace_id": str(workspace_fixture.id), "title": "R",
         "custom_fields": {"sap_id": "S-1"}},
        format="json",
    ).json()
    response = admin_client.patch(
        f"/api/v1/risks/{created['id']}/", {"uid": "nope"}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_unknown_extended_field_is_rejected(
    admin_client, workspace_fixture, risk_definition
) -> None:
    response = admin_client.post(
        "/api/v1/risks/",
        {"workspace_id": str(workspace_fixture.id), "title": "R",
         "custom_fields": {"sap_id": "S-1", "smuggled": "x"}},
        format="json",
    )
    assert response.status_code == 400
    assert "smuggled" in response.json()["error"]["message"]


@pytest.mark.django_db
def test_a_workspace_without_a_definition_does_not_block_writes(
    admin_client, workspace_fixture
) -> None:
    """No bootstrap yet must not brick the API — validation degrades to a no-op."""
    response = admin_client.post(
        "/api/v1/risks/",
        {"workspace_id": str(workspace_fixture.id), "title": "R"},
        format="json",
    )
    assert response.status_code == 201
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest rest_api/tests/test_attribute_field_validation.py -v`
Expected: FAIL — the required/regex/unknown-field cases return 201/200 instead of 400.

- [ ] **Step 3: Extend the mixin**

In `backend/rest_api/mixins/workflow_transitions.py`, add to `WorkflowTransitionsMixin`:

```python
    #: Item type this ViewSet's rows are keyed by in the attribute definition
    #: (e.g. "Requirement"). ``None`` disables definition-driven validation for
    #: the ViewSet — used only by non-artifact ViewSets.
    attribute_item_type: str | None = None

    def _validate_attribute_definition(
        self,
        ctx,
        workspace_id,
        changed_fields: dict,
        existing: dict | None,
    ):
        """Validate a payload against the resolved AttributeDefinition.

        Returns a 400 ``Response`` on violation and ``None`` when clean, so
        callers stay a single ``if`` line.

        A workspace with no resolved definition (bootstrap not run, or a type
        outside the ten bootstrapped ones) degrades to a no-op instead of
        blocking every write — an unconfigured deployment must stay usable.
        """
        from application.attribute_definition_service import (
            AttributeDefinitionNotFound,
            AttributeDefinitionService,
            FieldValidationError,
        )
        from rest_api.serializers import build_error_response, detect_lang
        from rest_framework import status
        from rest_framework.response import Response

        if not self.attribute_item_type or workspace_id is None:
            return None
        try:
            AttributeDefinitionService().validate_artifact_fields(
                ctx, self.attribute_item_type, workspace_id, changed_fields, existing
            )
        except AttributeDefinitionNotFound:
            return None
        except FieldValidationError as exc:
            lang = detect_lang(self.request)
            message = "; ".join(
                f"{name}: {', '.join(messages)}"
                for name, messages in sorted(exc.errors.items())
            )
            return Response(
                build_error_response("VALIDATION_ERROR", lang, message=message),
                status=status.HTTP_400_BAD_REQUEST,
            )
        return None
```

Then, inside the existing `_validate_patch_payload`, after its current field-name checks pass and immediately before it returns "clean", add:

```python
        definition_error = self._validate_attribute_definition(
            ctx, self._resolve_workspace_id(pk, ctx), dict(data), {"__exists__": True}
        )
        if definition_error is not None:
            return definition_error
```

and add the small resolver the call needs:

```python
    def _resolve_workspace_id(self, pk, ctx):
        """Workspace of the row under edit, or None when it cannot be resolved.

        Reuses the ViewSet's own ``_resolve_workflow_target`` getter so there is
        no second lookup path to keep in sync.
        """
        target = self._resolve_workflow_target(pk, ctx)
        return getattr(target, "workspace_id", None) if target is not None else None
```

- [ ] **Step 4: Declare the item type and gate creates in `views.py`**

For each of the nine artifact ViewSets in `backend/rest_api/views.py` add the class attribute — `RequirementViewSet` → `attribute_item_type = "Requirement"`, `StakeholderNeedViewSet` → `"StakeholderNeed"`, `ArchitectureElementViewSet` → `"ArchitectureElement"`, `TestCaseViewSet` → `"TestCase"`, `AdrViewSet` → `"Adr"`, `RiskViewSet` → `"Risk"`, `IssueViewSet` → `"Issue"`, `GlossaryTermViewSet` → `"GlossaryTerm"`, `ChangeRequestViewSet` → `None` (ChangeRequest is not one of the ten bootstrapped types; leaving it `None` is the explicit opt-out, not an oversight).

Then, in each of those ViewSets' `create` methods, immediately after the serializer's `is_valid(raise_exception=True)` call and before the service call, insert:

```python
        definition_error = self._validate_attribute_definition(
            ctx,
            serializer.validated_data.get("workspace_id"),
            dict(request.data) if isinstance(request.data, dict) else {},
            None,
        )
        if definition_error is not None:
            return definition_error
```

`existing=None` selects create semantics (all required attributes demanded); the raw `request.data` is passed rather than `validated_data` so the nested `custom_fields` dict reaches the validator unflattened.

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend pytest rest_api/tests/test_attribute_field_validation.py rest_api/tests/ -q`
Expected: PASS, including the pre-existing PATCH tests — the status-echo and unknown-field rules of `_validate_patch_payload` are unchanged, the definition check runs after them.

- [ ] **Step 6: Commit**

```bash
git add backend/rest_api/mixins/workflow_transitions.py backend/rest_api/views.py backend/rest_api/tests/test_attribute_field_validation.py
git commit -m "feat(attribute-definitions): validate artifact fields against the definition"
```

---

### Task 12: MCP tool group `attribute_definition.*`

Spec section 5. Decision D5: the pattern is `mcp_server/tools/custom_field.py`, because the `workflow.*` group the spec names does not exist (P2).

**Files:**
- Create: `backend/mcp_server/tools/attribute_definition.py`
- Modify: `backend/mcp_server/tool_registry.py` (register prefix, extend `_READ_ONLY_TOOL_NAMES`)
- Modify: `backend/mcp_server/workspace_scope.py` (`TENANT_SCOPED_READ_TOOLS`)
- Test: `backend/mcp_server/tests/test_attribute_definition_tools.py`

**Interfaces:**
- Consumes: `application.attribute_definition_service.{AttributeDefinitionService, AttributeDefinitionNotFound, AttributeSchemaError}`, `application.base.PermissionDeniedError`, `mcp_server.tools.base.{BaseToolGroup, ParameterError, require_uuid, require_param}`, `mcp_server.protocol_handler.ToolResult`.
- Produces `class AttributeDefinitionToolGroup(BaseToolGroup)` exposing:
  - `attribute_definition.list` — read, tenant-scoped, admin; params `item_type?`, `preset?`
  - `attribute_definition.get` — read; params `item_type` (required), `workspace_id` (**required**)
  - `attribute_definition.update` — write; params `item_type`, `workspace_id`, `attributes`
  - `attribute_definition.reset` — write; params `item_type`, `workspace_id`

Ratchet obligations (P4): `attribute_definition.get` declares `workspace_id` as **required** in its `inputSchema`, which satisfies `test_every_read_tool_is_classified`. `attribute_definition.list` is tenant-wide and therefore goes into `TENANT_SCOPED_READ_TOOLS`. Both read tools must be added to `_READ_ONLY_TOOL_NAMES` or the fail-closed gate treats them as writes.

- [ ] **Step 1: Write the failing test**

Create `backend/mcp_server/tests/test_attribute_definition_tools.py`:

```python
"""attribute_definition.* MCP tools (spec section 5)."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from mcp_server.tools.attribute_definition import AttributeDefinitionToolGroup

PAYLOAD = {
    "item_type": "Risk", "preset": "standard", "is_customized": False,
    "version": 1, "attributes": [{"name": "title", "kind": "core", "type": "text"}],
}


@pytest.fixture
def group() -> AttributeDefinitionToolGroup:
    return AttributeDefinitionToolGroup()


@pytest.fixture
def ctx() -> MagicMock:
    context = MagicMock()
    context.tenant_id = uuid.uuid4()
    return context


def test_tool_map_exposes_exactly_four_tools(group) -> None:
    assert set(group._TOOL_MAP) == {
        "attribute_definition.list",
        "attribute_definition.get",
        "attribute_definition.update",
        "attribute_definition.reset",
    }


def test_get_declares_workspace_id_as_required(group) -> None:
    """P4: a *declared* workspace_id is not scoping — it must be required."""
    schema = {t["name"]: t["inputSchema"] for t in group.get_tool_schemas()}
    assert "workspace_id" in schema["attribute_definition.get"]["required"]
    assert "workspace_id" in schema["attribute_definition.update"]["required"]
    assert "workspace_id" in schema["attribute_definition.reset"]["required"]


@pytest.mark.django_db
def test_get_returns_the_resolved_definition(group, ctx) -> None:
    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.resolve.return_value = PAYLOAD
        result = group.execute_tool(
            "attribute_definition.get",
            {"item_type": "Risk", "workspace_id": str(uuid.uuid4())},
            ctx,
        )
    assert result.is_error is False
    assert result.data["definition"] == PAYLOAD


@pytest.mark.django_db
def test_get_without_workspace_id_is_a_validation_error(group, ctx) -> None:
    result = group.execute_tool("attribute_definition.get", {"item_type": "Risk"}, ctx)
    assert result.is_error is True
    assert result.code == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_list_returns_the_global_defaults(group, ctx) -> None:
    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.list_global.return_value = [PAYLOAD]
        result = group.execute_tool("attribute_definition.list", {"item_type": "Risk"}, ctx)
    assert result.data["count"] == 1
    assert result.data["definitions"] == [PAYLOAD]


@pytest.mark.django_db
def test_update_rejects_a_non_list_attributes_param(group, ctx) -> None:
    result = group.execute_tool(
        "attribute_definition.update",
        {"item_type": "Risk", "workspace_id": str(uuid.uuid4()), "attributes": {}},
        ctx,
    )
    assert result.is_error is True
    assert result.code == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_update_maps_a_schema_error_to_validation_error(group, ctx) -> None:
    from application.attribute_definition_service import AttributeSchemaError

    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.update_workspace.side_effect = AttributeSchemaError(
            ["title: a core attribute may not change its 'type'"]
        )
        result = group.execute_tool(
            "attribute_definition.update",
            {"item_type": "Risk", "workspace_id": str(uuid.uuid4()), "attributes": []},
            ctx,
        )
    assert result.is_error is True
    assert result.code == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_reset_returns_the_restored_definition(group, ctx) -> None:
    with patch(
        "mcp_server.tools.attribute_definition.AttributeDefinitionService"
    ) as service:
        service.return_value.reset_workspace.return_value = PAYLOAD
        result = group.execute_tool(
            "attribute_definition.reset",
            {"item_type": "Risk", "workspace_id": str(uuid.uuid4())},
            ctx,
        )
    assert result.data["definition"] == PAYLOAD


def test_payload_is_json_serialisable_with_the_stdlib_encoder() -> None:
    """The MCP transport uses stdlib json.dumps — a UUID in a payload 500s."""
    import json

    from mcp_server.tools.attribute_definition import _definition_payload

    json.dumps(_definition_payload(PAYLOAD))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest mcp_server/tests/test_attribute_definition_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_server.tools.attribute_definition'`

- [ ] **Step 3: Write the tool group**

Create `backend/mcp_server/tools/attribute_definition.py`:

```python
"""AttributeDefinitionToolGroup — MCP surface for attribute definitions.

Spec section 5. Modelled on ``mcp_server/tools/custom_field.py`` (Decision D5:
the ``workflow.*`` group the spec names as the analogue does not exist).

Four tools:
  attribute_definition.list   — tenant-wide global defaults (read, admin)
  attribute_definition.get    — resolved definition for a workspace (read)
  attribute_definition.update — workspace override (write, admin)
  attribute_definition.reset  — back to the global default (write, admin)

``workspace_id`` is REQUIRED on get/update/reset. That is not cosmetic: the
dispatcher's workspace gate only engages on a required parameter, and
``mcp_server/tests/test_mcp_workspace_scope.py`` fails the build for any read
tool that merely *declares* one (the artifact.search regression).

No ORM in this module (ADR-01, enforced by
``rest_api/tests/test_architecture.py::test_no_new_direct_orm_access_mcp_tools``).
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from auth_tenancy.context import AuthContext

from application.attribute_definition_service import (
    AttributeDefinitionNotFound,
    AttributeDefinitionService,
    AttributeSchemaError,
)
from application.base import PermissionDeniedError
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup, ParameterError, require_param, require_uuid

logger = logging.getLogger(__name__)


def _definition_payload(definition: Dict[str, Any]) -> Dict[str, Any]:
    """Return a transport-safe copy of a service payload.

    The MCP transport serialises with stdlib ``json.dumps``, which has no UUID
    or datetime encoder — unlike DRF, which silently handles both. Everything
    the service returns is already primitive; this coerces defensively so a
    future field addition fails loudly here rather than as a 500 in the
    transport.
    """
    return {
        "item_type": str(definition["item_type"]),
        "preset": str(definition.get("preset") or ""),
        "is_customized": bool(definition.get("is_customized", False)),
        "initialized": bool(definition.get("initialized", True)),
        "version": int(definition.get("version", 0)),
        "attributes": list(definition.get("attributes", [])),
        **(
            {"propagated_workspace_count": int(definition["propagated_workspace_count"])}
            if "propagated_workspace_count" in definition
            else {}
        ),
    }


class AttributeDefinitionToolGroup(BaseToolGroup):
    """Attribute-definition tool group (2 read + 2 write tools)."""

    _TOOL_MAP = {
        "attribute_definition.list": "_handle_list",
        "attribute_definition.get": "_handle_get",
        "attribute_definition.update": "_handle_update",
        "attribute_definition.reset": "_handle_reset",
    }

    @staticmethod
    def _get_service() -> AttributeDefinitionService:
        return AttributeDefinitionService()

    def get_tool_schemas(self) -> list[Dict[str, Any]]:
        """Advertise the four tools with their JSON schemas."""
        workspace_scoped = {
            "type": "object",
            "properties": {
                "item_type": {
                    "type": "string",
                    "description": "Artifact type, e.g. 'Requirement'.",
                },
                "workspace_id": {"type": "string", "description": "Workspace UUID."},
            },
            "required": ["item_type", "workspace_id"],
        }
        update_schema = {
            "type": "object",
            "properties": {
                **workspace_scoped["properties"],
                "attributes": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Full replacement attribute list.",
                },
            },
            "required": ["item_type", "workspace_id", "attributes"],
        }
        return [
            {
                "name": "attribute_definition.list",
                "description": "List the tenant-wide global attribute defaults.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "item_type": {"type": "string"},
                        "preset": {
                            "type": "string",
                            "enum": ["minimal", "standard", "extended"],
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "attribute_definition.get",
                "description": "Resolved attribute definition for a workspace.",
                "inputSchema": workspace_scoped,
            },
            {
                "name": "attribute_definition.update",
                "description": "Replace a workspace's attribute definition.",
                "inputSchema": update_schema,
            },
            {
                "name": "attribute_definition.reset",
                "description": "Reset a workspace definition to the global default.",
                "inputSchema": workspace_scoped,
            },
        ]

    # ---- Handlers ---------------------------------------------------------

    def _handle_list(
        self, params: Dict[str, Any], auth_context: AuthContext
    ) -> ToolResult:
        try:
            definitions = self._get_service().list_global(
                auth_context,
                item_type=params.get("item_type") or None,
                preset=params.get("preset") or None,
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        payload = [_definition_payload(d) for d in definitions]
        return ToolResult.ok({"definitions": payload, "count": len(payload)})

    def _handle_get(
        self, params: Dict[str, Any], auth_context: AuthContext
    ) -> ToolResult:
        try:
            item_type = require_param(params, "item_type")
            workspace_id = require_uuid(params, "workspace_id")
        except ParameterError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        try:
            definition = self._get_service().resolve(auth_context, item_type, workspace_id)
        except AttributeDefinitionNotFound as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        return ToolResult.ok({"definition": _definition_payload(definition)})

    def _handle_update(
        self, params: Dict[str, Any], auth_context: AuthContext
    ) -> ToolResult:
        try:
            item_type = require_param(params, "item_type")
            workspace_id = require_uuid(params, "workspace_id")
        except ParameterError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        attributes = params.get("attributes")
        if not isinstance(attributes, list):
            return ToolResult.error(
                "VALIDATION_ERROR", "Parameter 'attributes' must be a list."
            )
        try:
            definition = self._get_service().update_workspace(
                auth_context, item_type, workspace_id, attributes
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except AttributeDefinitionNotFound as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except AttributeSchemaError as exc:
            return ToolResult.error("VALIDATION_ERROR", "; ".join(exc.errors))
        return ToolResult.ok({"definition": _definition_payload(definition)})

    def _handle_reset(
        self, params: Dict[str, Any], auth_context: AuthContext
    ) -> ToolResult:
        try:
            item_type = require_param(params, "item_type")
            workspace_id = require_uuid(params, "workspace_id")
        except ParameterError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        try:
            definition = self._get_service().reset_workspace(
                auth_context, item_type, workspace_id
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except AttributeDefinitionNotFound as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        return ToolResult.ok({"definition": _definition_payload(definition)})


__all__ = ["AttributeDefinitionToolGroup"]
```

- [ ] **Step 4: Register the group and classify the read tools**

In `backend/mcp_server/tool_registry.py`:
- inside `_ensure_groups`, add the import `from mcp_server.tools.attribute_definition import AttributeDefinitionToolGroup` next to the other lazy tool-group imports, and add `"attribute_definition": AttributeDefinitionToolGroup(),` to the `register_groups({...})` dict;
- add `"attribute_definition.list"` and `"attribute_definition.get"` to `_READ_ONLY_TOOL_NAMES` (the gate is fail-closed: without this both are RBAC-checked as writes and a Viewer never sees them).

In `backend/mcp_server/workspace_scope.py`, add to `TENANT_SCOPED_READ_TOOLS` with the documented reason:

```python
        # * ``attribute_definition.list`` — the tenant-wide global defaults are
        #   per (item_type, preset), not per workspace; there is no workspace to
        #   scope to. The handler is admin-gated in the service.
        "attribute_definition.list",
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend pytest mcp_server/tests/test_attribute_definition_tools.py mcp_server/tests/test_mcp_workspace_scope.py -v`
Expected: PASS, including `test_every_read_tool_is_classified` and `test_classification_sets_are_disjoint`.

- [ ] **Step 6: Refresh the tool manifest count**

Run: `docker compose exec backend python manage.py export_tool_manifest | head -5`
Expected: the tool count rises by 4. Update any documented tool total (`CLAUDE.md`, `README.md`, `docs/`) that states "171 Tools" to the new number in this same commit.

- [ ] **Step 7: Commit**

```bash
git add backend/mcp_server/tools/attribute_definition.py backend/mcp_server/tool_registry.py backend/mcp_server/workspace_scope.py backend/mcp_server/tests/test_attribute_definition_tools.py
git commit -m "feat(attribute-definitions): add attribute_definition MCP tool group"
```

---

## Phase C — Consumers

### Task 13: Interview protocol derived from `ai_elicit`

Spec section 7: the per-type required fields come from `ai_elicit=true` attributes of the resolved definition instead of YAML in prompt-template slots; phase order = `section` order. Solves audit finding L2.2 (the default protocol only elicits title + rationale). The `formalize()` type dispatch (L2.1) is explicitly **not** part of this task — that is the separate Interview-Engine-Fix spec.

**Files:**
- Modify: `backend/application/interview_protocol.py` (add `protocol_from_definition`, use it in `get_protocol`)
- Test: `backend/application/tests/test_interview_protocol_from_definition.py`

**Interfaces:**
- Consumes: `application.attribute_definition_service.{AttributeDefinitionService, AttributeDefinitionNotFound}`, existing `ProtocolConfig`, `ProtocolPhase`, `ProtocolField`.
- Produces: `protocol_from_definition(attributes: list[dict], artifact_type: str) -> ProtocolConfig`, and the changed resolution order inside `get_protocol`.

Resolution order after this task (documented in the docstring): an explicit `interview.protocol.<ArtifactType>` **workspace or tenant** PromptTemplate still wins (an admin who wrote a protocol keeps it); otherwise the definition-derived protocol is used; the hardcoded factory default remains only as the last fallback for a workspace with no definition.

Type mapping (the protocol validator accepts exactly `text`, `textarea`, `enum`, `number`): `text`/`textarea`/`number`/`enum` pass through; `multi-enum` → `enum`; `boolean`/`date`/`reference`/`user` → `text`; `widget` attributes are skipped (their bound fields are elicited individually if those carry `ai_elicit`).

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_interview_protocol_from_definition.py`:

```python
"""Interview protocol derived from ai_elicit attributes (spec section 7)."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.interview_protocol import (
    ProtocolValidationError,
    get_protocol,
    protocol_from_definition,
)


def _attr(name, **over):
    base = {
        "name": name, "kind": "core", "type": "text", "section": "general",
        "order": 0, "ai_elicit": True, "visible": True, "options": [],
        "label": {"de": name, "en": name}, "widget_key": None, "fields": [],
    }
    base.update(over)
    return base


def test_only_ai_elicit_attributes_become_required_fields() -> None:
    protocol = protocol_from_definition(
        [_attr("title"), _attr("quiet", ai_elicit=False)], "Risk"
    )
    names = [f.name for phase in protocol.phases for f in phase.required_fields]
    assert names == ["title"]


def test_section_order_becomes_phase_order() -> None:
    protocol = protocol_from_definition(
        [
            _attr("severity", section="classification", order=0),
            _attr("title", section="general", order=0),
        ],
        "Risk",
    )
    assert [p.name for p in protocol.phases[:2]] == ["classification", "general"]


def test_approval_and_formalization_phases_are_always_appended() -> None:
    protocol = protocol_from_definition([_attr("title")], "Risk")
    assert [p.name for p in protocol.phases[-2:]] == ["approval", "formalization"]
    assert protocol.phases[-1].required_fields == []


def test_enum_attributes_carry_their_choices() -> None:
    protocol = protocol_from_definition(
        [_attr("category", type="enum",
               options=[{"value": "a", "label_de": "A", "label_en": "A"}])],
        "Risk",
    )
    field = protocol.phases[0].required_fields[0]
    assert field.type == "enum"
    assert field.choices == ["a"]


def test_multi_enum_is_narrowed_to_enum_and_other_types_to_text() -> None:
    protocol = protocol_from_definition(
        [
            _attr("tags", type="multi-enum",
                  options=[{"value": "x", "label_de": "X", "label_en": "X"}]),
            _attr("due", type="date"),
            _attr("owner", type="user"),
        ],
        "Issue",
    )
    by_name = {f.name: f for p in protocol.phases for f in p.required_fields}
    assert by_name["tags"].type == "enum"
    assert by_name["due"].type == "text"
    assert by_name["owner"].type == "text"


def test_widget_attributes_are_skipped() -> None:
    protocol = protocol_from_definition(
        [_attr("risk_matrix", type="widget", widget_key="risk_matrix_rpz",
               fields=["probability"]),
         _attr("probability", type="enum",
               options=[{"value": "low", "label_de": "N", "label_en": "L"}])],
        "Risk",
    )
    names = [f.name for p in protocol.phases for f in p.required_fields]
    assert names == ["probability"]


def test_a_definition_with_no_ai_elicit_attribute_raises() -> None:
    """A protocol with zero elicitable fields is not a usable interview."""
    with pytest.raises(ProtocolValidationError):
        protocol_from_definition([_attr("quiet", ai_elicit=False)], "Risk")


@pytest.mark.django_db
def test_get_protocol_prefers_an_explicit_template_over_the_definition() -> None:
    ctx, workspace_id = MagicMock(), uuid.uuid4()
    yaml = (
        "phases:\n  - name: custom\n    required_fields:\n"
        "      - name: handcrafted\n        type: text\n"
    )
    with patch(
        "application.prompt_resolver.try_resolve_template_content", return_value=yaml
    ):
        protocol = get_protocol(ctx, "Risk", workspace_id)
    assert protocol.phases[0].name == "custom"


@pytest.mark.django_db
def test_get_protocol_falls_back_to_the_definition() -> None:
    ctx, workspace_id = MagicMock(), uuid.uuid4()
    with patch(
        "application.prompt_resolver.try_resolve_template_content", return_value=None
    ), patch(
        "application.interview_protocol.AttributeDefinitionService"
    ) as service:
        service.return_value.elicit_attributes.return_value = [_attr("title")]
        protocol = get_protocol(ctx, "Risk", workspace_id)
    assert [f.name for p in protocol.phases for f in p.required_fields] == ["title"]


@pytest.mark.django_db
def test_get_protocol_falls_back_to_the_factory_default_without_a_definition() -> None:
    from application.attribute_definition_service import AttributeDefinitionNotFound

    ctx, workspace_id = MagicMock(), uuid.uuid4()
    with patch(
        "application.prompt_resolver.try_resolve_template_content", return_value=None
    ), patch(
        "application.interview_protocol.AttributeDefinitionService"
    ) as service:
        service.return_value.elicit_attributes.side_effect = AttributeDefinitionNotFound("x")
        protocol = get_protocol(ctx, "Risk", workspace_id)
    names = [f.name for p in protocol.phases for f in p.required_fields]
    assert names == ["title", "rationale"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest application/tests/test_interview_protocol_from_definition.py -v`
Expected: FAIL with `ImportError: cannot import name 'protocol_from_definition'`

- [ ] **Step 3: Write the implementation**

In `backend/application/interview_protocol.py`, add after `_default_protocol_yaml`:

```python
#: Attribute type -> protocol field type. The protocol validator accepts only
#: text/textarea/enum/number, so the richer attribute vocabulary is narrowed:
#: multi-enum keeps its choices as a single-select, and the reference-shaped
#: types degrade to free text rather than being dropped (the interview asks for
#: them in prose and formalize() resolves them).
_ATTRIBUTE_TO_PROTOCOL_TYPE = {
    "text": "text",
    "textarea": "textarea",
    "number": "number",
    "enum": "enum",
    "multi-enum": "enum",
    "boolean": "text",
    "date": "text",
    "reference": "text",
    "user": "text",
}


def protocol_from_definition(
    attributes: list[dict], artifact_type: str
) -> ProtocolConfig:
    """Derive an interview protocol from a resolved attribute definition.

    Spec section 7: elicitation phases ARE the definition's sections, in the
    definition's order; a phase's required fields are that section's
    ``ai_elicit=true`` attributes. ``approval`` and ``formalization`` are
    appended unchanged so the engine's phase machine is untouched.

    Resolves audit finding L2.2 as a side effect: the hardcoded default only
    ever elicited title + rationale for every type.

    Raises:
        ProtocolValidationError: the definition marks no attribute as
            ``ai_elicit`` — an interview with nothing to ask is not usable, and
            silently returning an empty protocol would strand the session.
    """
    phases: list[ProtocolPhase] = []
    by_section: dict[str, list[dict]] = {}
    for attribute in attributes:
        if attribute["type"] == "widget" or not attribute.get("ai_elicit"):
            continue
        by_section.setdefault(attribute["section"], []).append(attribute)

    if not by_section:
        raise ProtocolValidationError(
            f"No attribute of artifact_type={artifact_type!r} is marked "
            f"ai_elicit; nothing to interview for."
        )

    for section, section_attributes in by_section.items():
        fields = []
        for attribute in section_attributes:
            field_type = _ATTRIBUTE_TO_PROTOCOL_TYPE.get(attribute["type"], "text")
            choices = (
                [o["value"] for o in attribute["options"]]
                if field_type == "enum"
                else None
            )
            fields.append(
                ProtocolField(name=attribute["name"], type=field_type, choices=choices)
            )
        phases.append(
            ProtocolPhase(
                name=section,
                required_fields=fields,
                prompt_fragment=(
                    f"Elicit the {artifact_type}'s {section} attributes: "
                    f"{', '.join(f.name for f in fields)}."
                ),
            )
        )

    phases.append(
        ProtocolPhase(
            name="approval",
            required_fields=[],
            prompt_fragment=f"Present the drafted {artifact_type} for approval.",
        )
    )
    phases.append(
        ProtocolPhase(
            name="formalization", required_fields=[], prompt_fragment="Confirm and formalize."
        )
    )
    return ProtocolConfig(phases=phases)
```

Then replace the body of `get_protocol` with:

```python
def get_protocol(ctx, artifact_type: str, workspace_id) -> ProtocolConfig:
    """Resolve the effective protocol for *artifact_type* in *workspace_id*.

    Resolution order (spec section 7):
      1. an explicit ``interview.protocol.<ArtifactType>`` PromptTemplate
         (workspace, then tenant-global) — an admin who wrote a protocol by
         hand keeps it;
      2. the attribute definition's ``ai_elicit`` attributes;
      3. the hardcoded factory default, for a workspace with no definition yet.

    Imported lazily: ``prompt_resolver`` imports ``prompt_slots``, which reads
    this module's ``INTERVIEW_PROTOCOL_DEFAULTS`` — a module-level import here
    would close that cycle at import time.
    """
    from application.prompt_resolver import try_resolve_template_content

    name = f"interview.protocol.{artifact_type}"
    content = try_resolve_template_content(name, ctx, workspace_id)
    if content is not None:
        return parse_protocol_yaml(content)

    try:
        attributes = AttributeDefinitionService().elicit_attributes(
            ctx, artifact_type, workspace_id
        )
        return protocol_from_definition(attributes, artifact_type)
    except (AttributeDefinitionNotFound, ProtocolValidationError):
        return parse_protocol_yaml(_default_protocol_yaml(artifact_type))
```

and add at the top of the module, after the existing imports:

```python
from application.attribute_definition_service import (
    AttributeDefinitionNotFound,
    AttributeDefinitionService,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest application/tests/test_interview_protocol_from_definition.py application/tests/test_interview_service.py -v`
Expected: PASS. The existing interview-service tests must stay green — `try_resolve_template_content` returning a template short-circuits before the new branch.

- [ ] **Step 5: Commit**

```bash
git add backend/application/interview_protocol.py backend/application/tests/test_interview_protocol_from_definition.py
git commit -m "feat(attribute-definitions): derive interview protocol from ai_elicit attributes"
```

---

### Task 14: Export field list from `export=true`

Spec section 7: `REQUIREMENT_ALL_FIELDS` stops being the hardcoded source and becomes a fallback for callers with no resolved definition. Also removes the last consumer of the deleted `AttributeVisibilityConfigService`.

**Files:**
- Modify: `backend/application/requirement_bundle_service.py:86-104, 189-230, 390-425`
- Test: `backend/application/tests/test_bundle_export_fields_from_definition.py`

**Interfaces:**
- Consumes: `application.attribute_definition_service.{AttributeDefinitionService, AttributeDefinitionNotFound}`.
- Produces on `RequirementBundleService`: `resolve_export_fields(ctx, workspace_id, filter_mode: str, fields: list[str] | None) -> set[str]`. `REQUIREMENT_ALL_FIELDS` stays exported (other modules import it) but is documented as the fallback.

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_bundle_export_fields_from_definition.py`:

```python
"""Bundle export field list resolved from export=true (spec section 7)."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.requirement_bundle_service import (
    REQUIREMENT_ALL_FIELDS,
    RequirementBundleService,
)


def _attr(name, export=True):
    return {"name": name, "kind": "core", "type": "text", "export": export,
            "visible": True, "section": "general", "order": 0}


@pytest.fixture
def service() -> RequirementBundleService:
    return RequirementBundleService()


@pytest.mark.django_db
def test_all_mode_uses_the_export_flagged_attributes(service) -> None:
    ctx, workspace_id = MagicMock(), uuid.uuid4()
    with patch(
        "application.requirement_bundle_service.AttributeDefinitionService"
    ) as definition:
        definition.return_value.export_attributes.return_value = [
            _attr("title"), _attr("uid")
        ]
        fields = service.resolve_export_fields(ctx, workspace_id, "all", None)
    assert fields == {"title", "uid"}


@pytest.mark.django_db
def test_visible_mode_drops_invisible_attributes(service) -> None:
    ctx, workspace_id = MagicMock(), uuid.uuid4()
    with patch(
        "application.requirement_bundle_service.AttributeDefinitionService"
    ) as definition:
        definition.return_value.export_attributes.return_value = [
            _attr("title"), dict(_attr("secret"), visible=False)
        ]
        fields = service.resolve_export_fields(ctx, workspace_id, "visible", None)
    assert fields == {"title"}


@pytest.mark.django_db
def test_custom_mode_rejects_a_field_outside_the_definition(service) -> None:
    ctx, workspace_id = MagicMock(), uuid.uuid4()
    with patch(
        "application.requirement_bundle_service.AttributeDefinitionService"
    ) as definition:
        definition.return_value.export_attributes.return_value = [_attr("title")]
        with pytest.raises(ValueError) as exc:
            service.resolve_export_fields(ctx, workspace_id, "custom", ["title", "nope"])
    assert "nope" in str(exc.value)


@pytest.mark.django_db
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest application/tests/test_bundle_export_fields_from_definition.py -v`
Expected: FAIL with `AttributeError: 'RequirementBundleService' object has no attribute 'resolve_export_fields'`

- [ ] **Step 3: Write the implementation**

In `backend/application/requirement_bundle_service.py`:

Add the import at module scope:

```python
from application.attribute_definition_service import (
    AttributeDefinitionNotFound,
    AttributeDefinitionService,
)
```

Change the comment above `REQUIREMENT_ALL_FIELDS` to state its new role:

```python
# FALLBACK ONLY (spec section 7): the authoritative export field list now comes
# from the resolved AttributeDefinition's ``export=true`` attributes via
# ``RequirementBundleService.resolve_export_fields``. This tuple is what a
# workspace with no definition yet (bootstrap not run) still exports, and it is
# what the OpenAPI schema documents as the baseline set.
```

Add the method to `RequirementBundleService`:

```python
    def resolve_export_fields(
        self,
        ctx,
        workspace_id,
        filter_mode: str,
        fields: list[str] | None,
    ) -> set[str]:
        """Return the field names a bundle export must carry.

        Args:
            filter_mode: ``"all"`` (every ``export=true`` attribute),
                ``"visible"`` (additionally ``visible=true``), or ``"custom"``
                (the caller's ``fields``, each of which must be an
                ``export=true`` attribute).

        Raises:
            ValueError: ``filter_mode="custom"`` names a field the definition
                does not export. Rejecting loudly is the point — the old code
                silently dropped unknown names.
        """
        try:
            attributes = AttributeDefinitionService().export_attributes(
                ctx, "Requirement", workspace_id
            )
        except AttributeDefinitionNotFound:
            attributes = [
                {"name": name, "visible": True} for name in REQUIREMENT_ALL_FIELDS
            ]

        exportable = {a["name"] for a in attributes}
        if filter_mode == "custom":
            requested = set(fields or [])
            unknown = sorted(requested - exportable)
            if unknown:
                raise ValueError(
                    f"Unknown export field(s): {', '.join(unknown)}. "
                    f"Available: {', '.join(sorted(exportable))}"
                )
            return requested
        if filter_mode == "visible":
            return {a["name"] for a in attributes if a.get("visible", True)}
        return exportable
```

Then replace the two existing field-resolution sites: the `unknown = sorted(set(fields) - set(REQUIREMENT_ALL_FIELDS))` check around line 216 and the `filter_mode == "visible"` branch around lines 405-422 (which called `AttributeVisibilityConfigService`) both become a single call to `self.resolve_export_fields(ctx, workspace_id, filter_mode, fields)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest application/tests/test_bundle_export_fields_from_definition.py application/tests/test_requirement_bundle_service.py -v`
Expected: PASS. `test_requirement_bundle_service.py` line 477 imports `REQUIREMENT_ALL_FIELDS`, which still exists.

- [ ] **Step 5: Commit**

```bash
git add backend/application/requirement_bundle_service.py backend/application/tests/test_bundle_export_fields_from_definition.py
git commit -m "feat(attribute-definitions): resolve export field list from the definition"
```

---

## Phase D — Frontend

> **Ratchet obligation for every task in this phase (P4):** no new inline `style={{` under `frontend/src/components/`. `frontend/src/test/ui-ratchet.test.ts` asserts both `toBeLessThanOrEqual(STYLE_BRACE_BASELINE)` **and** `toBe(STYLE_BRACE_BASELINE)`, so deleting a form (which lowers the real count) fails the monotonic assertion until `STYLE_BRACE_BASELINE` is lowered to the newly measured value in the same commit. Every task below that deletes a form has an explicit re-measure step. All new styling goes into `*.module.css` using the custom properties from `frontend/src/styles/tokens.css`.

### Task 15: Frontend API wrapper and types

**Files:**
- Create: `frontend/src/api/attribute-definitions.ts`
- Modify: `frontend/src/api/index.ts` (export `attributeDefinitionsApi`)
- Test: `frontend/src/test/attributeDefinitionsApi.test.ts`

**Interfaces:**
- Consumes: `apiClient` from `./client`, `UUID` and `WorkspacePreset` from `../types`.
- Produces (named exports — no default export):
  - `type AttributeKind = "core" | "extended"`
  - `type AttributeType = "text" | "textarea" | "number" | "boolean" | "enum" | "multi-enum" | "date" | "reference" | "user" | "widget"`
  - `type AttributeEditable = boolean | "workflow"`
  - `type AttributeAudience = "basic" | "expert"`
  - `type WidgetKey = "risk_matrix_rpz" | "markdown_tab_group" | "steps_editor"`
  - `interface AttributeOption { value: string; label_de: string; label_en: string }`
  - `interface LocalizedText { de: string; en: string }`
  - `interface AttributeValidationRules { regex?: string; min?: number; max?: number; length?: number }`
  - `interface AttributeSpec` — the 19 keys of the schema
  - `interface ResolvedAttributeDefinition { item_type: string; preset: WorkspacePreset; is_customized: boolean; version: number; attributes: AttributeSpec[] }`
  - `interface GlobalAttributeDefinition { item_type: string; preset: WorkspacePreset; initialized: boolean; version: number; attributes: AttributeSpec[]; propagated_workspace_count?: number }`
  - `attributeDefinitionsApi` with `listGlobal`, `getGlobal`, `putGlobal`, `getWorkspace`, `putWorkspace`, `resetWorkspace`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/attributeDefinitionsApi.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import { attributeDefinitionsApi } from "../api/attribute-definitions";

vi.mock("../api/client", () => ({
  apiClient: {
    get: vi.fn(),
    put: vi.fn(),
    post: vi.fn(),
  },
}));

const DEFINITION = {
  item_type: "Risk",
  preset: "standard",
  is_customized: false,
  version: 1,
  attributes: [],
};

describe("attributeDefinitionsApi", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.put).mockReset();
    vi.mocked(apiClient.post).mockReset();
  });

  it("reads a global default per item type and preset", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ ...DEFINITION, initialized: true });
    await attributeDefinitionsApi.getGlobal("Risk", "standard");
    expect(apiClient.get).toHaveBeenCalledWith(
      "/attribute-defaults/Risk/standard/"
    );
  });

  it("url-encodes the item type", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ ...DEFINITION, initialized: true });
    await attributeDefinitionsApi.getGlobal("Architecture Element", "minimal");
    expect(apiClient.get).toHaveBeenCalledWith(
      "/attribute-defaults/Architecture%20Element/minimal/"
    );
  });

  it("lists global defaults with optional filters", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ definitions: [] });
    await attributeDefinitionsApi.listGlobal({ itemType: "Risk" });
    expect(apiClient.get).toHaveBeenCalledWith(
      "/attribute-defaults/?item_type=Risk"
    );
  });

  it("sends the attribute list as the PUT body", async () => {
    vi.mocked(apiClient.put).mockResolvedValue({ ...DEFINITION, initialized: true });
    await attributeDefinitionsApi.putGlobal("Risk", "standard", []);
    expect(apiClient.put).toHaveBeenCalledWith(
      "/attribute-defaults/Risk/standard/",
      { attributes: [] }
    );
  });

  it("reads a workspace definition", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(DEFINITION);
    await attributeDefinitionsApi.getWorkspace("ws-1", "Risk");
    expect(apiClient.get).toHaveBeenCalledWith(
      "/workspaces/ws-1/attribute-definitions/Risk/"
    );
  });

  it("resets a workspace definition", async () => {
    vi.mocked(apiClient.post).mockResolvedValue(DEFINITION);
    await attributeDefinitionsApi.resetWorkspace("ws-1", "Risk");
    expect(apiClient.post).toHaveBeenCalledWith(
      "/workspaces/ws-1/attribute-definitions/Risk/reset/",
      {}
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npx vitest run src/test/attributeDefinitionsApi.test.ts`
Expected: FAIL — cannot resolve `../api/attribute-definitions`.

- [ ] **Step 3: Write the wrapper**

Create `frontend/src/api/attribute-definitions.ts`:

```ts
/**
 * ARCH-L1-001 ReactFrontend — Attribute Definition API.
 *
 * Wraps /api/v1/attribute-defaults/ (tenant-wide, per item_type + preset) and
 * /api/v1/workspaces/{id}/attribute-definitions/{item_type}/ (resolved copy).
 *
 * The resolved shape is what ArtifactForm renders and what the table view
 * derives its columns and filter operators from — it is the single client-side
 * source for "what fields does this artifact type have".
 */

import { apiClient } from "./client";
import type { UUID, WorkspacePreset } from "../types";

export type AttributeKind = "core" | "extended";

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

/** `"workflow"` = changeable only through a workflow transition. */
export type AttributeEditable = boolean | "workflow";

/** Display density only — never a visibility or security boundary. */
export type AttributeAudience = "basic" | "expert";

export type WidgetKey = "risk_matrix_rpz" | "markdown_tab_group" | "steps_editor";

export interface AttributeOption {
  value: string;
  label_de: string;
  label_en: string;
}

export interface LocalizedText {
  de: string;
  en: string;
}

export interface AttributeValidationRules {
  regex?: string;
  min?: number;
  max?: number;
  length?: number;
}

/** One entry of `definition_json.attributes[]` — the published contract. */
export interface AttributeSpec {
  name: string;
  kind: AttributeKind;
  type: AttributeType;
  widget_key: WidgetKey | null;
  fields: string[];
  options: AttributeOption[];
  required: boolean;
  visible: boolean;
  locked: boolean;
  editable: AttributeEditable;
  section: string;
  order: number;
  label: LocalizedText;
  help_text: LocalizedText;
  default: unknown;
  validation: AttributeValidationRules;
  ai_elicit: boolean;
  export: boolean;
  audience: AttributeAudience;
}

export interface ResolvedAttributeDefinition {
  item_type: string;
  preset: WorkspacePreset;
  is_customized: boolean;
  version: number;
  attributes: AttributeSpec[];
}

export interface GlobalAttributeDefinition {
  item_type: string;
  preset: WorkspacePreset;
  initialized: boolean;
  version: number;
  attributes: AttributeSpec[];
  /** Present on a PUT response: how many on-default workspaces were updated. */
  propagated_workspace_count?: number;
}

function globalPath(itemType: string, preset: WorkspacePreset): string {
  return `/attribute-defaults/${encodeURIComponent(itemType)}/${encodeURIComponent(
    preset
  )}/`;
}

function workspacePath(workspaceId: UUID, itemType: string): string {
  return `/workspaces/${workspaceId}/attribute-definitions/${encodeURIComponent(
    itemType
  )}/`;
}

export const attributeDefinitionsApi = {
  async listGlobal(filters?: {
    itemType?: string;
    preset?: WorkspacePreset;
  }): Promise<GlobalAttributeDefinition[]> {
    const query = new URLSearchParams();
    if (filters?.itemType) query.set("item_type", filters.itemType);
    if (filters?.preset) query.set("preset", filters.preset);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    const raw = await apiClient.get<{ definitions: GlobalAttributeDefinition[] }>(
      `/attribute-defaults/${suffix}`
    );
    return raw.definitions;
  },

  /** Never 404s: an unseeded type returns `initialized: false` with no attributes. */
  getGlobal(
    itemType: string,
    preset: WorkspacePreset
  ): Promise<GlobalAttributeDefinition> {
    return apiClient.get<GlobalAttributeDefinition>(globalPath(itemType, preset));
  },

  putGlobal(
    itemType: string,
    preset: WorkspacePreset,
    attributes: AttributeSpec[]
  ): Promise<GlobalAttributeDefinition> {
    return apiClient.put<GlobalAttributeDefinition>(globalPath(itemType, preset), {
      attributes,
    });
  },

  getWorkspace(
    workspaceId: UUID,
    itemType: string
  ): Promise<ResolvedAttributeDefinition> {
    return apiClient.get<ResolvedAttributeDefinition>(
      workspacePath(workspaceId, itemType)
    );
  },

  putWorkspace(
    workspaceId: UUID,
    itemType: string,
    attributes: AttributeSpec[]
  ): Promise<ResolvedAttributeDefinition> {
    return apiClient.put<ResolvedAttributeDefinition>(
      workspacePath(workspaceId, itemType),
      { attributes }
    );
  },

  resetWorkspace(
    workspaceId: UUID,
    itemType: string
  ): Promise<ResolvedAttributeDefinition> {
    return apiClient.post<ResolvedAttributeDefinition>(
      `${workspacePath(workspaceId, itemType)}reset/`,
      {}
    );
  },
};
```

- [ ] **Step 4: Export it**

In `frontend/src/api/index.ts`, next to the other exports add:

```ts
export { attributeDefinitionsApi } from "./attribute-definitions";
export type {
  AttributeSpec,
  AttributeType,
  AttributeEditable,
  AttributeAudience,
  AttributeOption,
  GlobalAttributeDefinition,
  ResolvedAttributeDefinition,
  WidgetKey,
} from "./attribute-definitions";
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec frontend npx vitest run src/test/attributeDefinitionsApi.test.ts --testTimeout=30000`
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/attribute-definitions.ts frontend/src/api/index.ts frontend/src/test/attributeDefinitionsApi.test.ts
git commit -m "feat(attribute-definitions): add frontend API wrapper and types"
```

---

### Task 16: Field component library

Eight basic field components (spec section 6). Each is a controlled component with one shape, so the renderer never branches on markup.

**Files:**
- Create: `frontend/src/components/shared/ArtifactForm/fields/FieldShell.tsx`
- Create: `frontend/src/components/shared/ArtifactForm/fields/TextField.tsx`
- Create: `frontend/src/components/shared/ArtifactForm/fields/TextArea.tsx`
- Create: `frontend/src/components/shared/ArtifactForm/fields/NumberField.tsx`
- Create: `frontend/src/components/shared/ArtifactForm/fields/BooleanToggle.tsx`
- Create: `frontend/src/components/shared/ArtifactForm/fields/EnumSelect.tsx`
- Create: `frontend/src/components/shared/ArtifactForm/fields/MultiEnum.tsx`
- Create: `frontend/src/components/shared/ArtifactForm/fields/DateField.tsx`
- Create: `frontend/src/components/shared/ArtifactForm/fields/ReferencePicker.tsx`
- Create: `frontend/src/components/shared/ArtifactForm/fields/UserPicker.tsx`
- Create: `frontend/src/components/shared/ArtifactForm/fields/index.ts`
- Create: `frontend/src/components/shared/ArtifactForm/ArtifactForm.module.css`
- Test: `frontend/src/test/ArtifactFormFields.test.tsx`

**Interfaces:**
- Consumes: `AttributeSpec`, `AttributeOption` from `../../../../api/attribute-definitions`; `useTranslation` from `react-i18next`; `usersApi` from `../../../../api/users`; `artifactRefs` helpers from `../../../../api/artifactRefs`.
- Produces the shared prop contract every field implements:

```ts
export interface FieldProps<T = unknown> {
  attribute: AttributeSpec;
  value: T;
  onChange: (next: T) => void;
  disabled: boolean;
  /** Server-side validation messages for this attribute, if any. */
  errors?: string[];
  /** Stable `data-testid` prefix: `artifact-field-<name>`. */
  testId: string;
}
```

  plus `attributeLabel(attribute: AttributeSpec, language: string): string` and `optionLabel(option: AttributeOption, language: string): string` from `FieldShell.tsx`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/ArtifactFormFields.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  BooleanToggle,
  DateField,
  EnumSelect,
  MultiEnum,
  NumberField,
  TextArea,
  TextField,
  attributeLabel,
} from "../components/shared/ArtifactForm/fields";
import type { AttributeSpec } from "../api/attribute-definitions";

function spec(over: Partial<AttributeSpec> = {}): AttributeSpec {
  return {
    name: "title",
    kind: "core",
    type: "text",
    widget_key: null,
    fields: [],
    options: [],
    required: false,
    visible: true,
    locked: false,
    editable: true,
    section: "general",
    order: 0,
    label: { de: "Titel", en: "Title" },
    help_text: { de: "", en: "" },
    default: null,
    validation: {},
    ai_elicit: false,
    export: false,
    audience: "basic",
    ...over,
  };
}

describe("ArtifactForm field library", () => {
  it("prefers the definition label over the raw attribute name", () => {
    expect(attributeLabel(spec(), "de")).toBe("Titel");
    expect(attributeLabel(spec(), "en")).toBe("Title");
    expect(attributeLabel(spec({ label: { de: "", en: "" } }), "de")).toBe("title");
  });

  it("renders a text field and reports edits", () => {
    const onChange = vi.fn();
    render(
      <TextField
        attribute={spec()}
        value="a"
        onChange={onChange}
        disabled={false}
        testId="artifact-field-title"
      />
    );
    fireEvent.change(screen.getByTestId("artifact-field-title"), {
      target: { value: "b" },
    });
    expect(onChange).toHaveBeenCalledWith("b");
  });

  it("marks a required field with aria-required", () => {
    render(
      <TextField
        attribute={spec({ required: true })}
        value=""
        onChange={vi.fn()}
        disabled={false}
        testId="artifact-field-title"
      />
    );
    expect(screen.getByTestId("artifact-field-title")).toHaveAttribute(
      "aria-required",
      "true"
    );
  });

  it("associates server errors with the input via aria-describedby", () => {
    render(
      <TextField
        attribute={spec()}
        value=""
        onChange={vi.fn()}
        disabled={false}
        errors={["is required"]}
        testId="artifact-field-title"
      />
    );
    const input = screen.getByTestId("artifact-field-title");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("is required");
    expect(input.getAttribute("aria-describedby")).toContain("artifact-field-title");
  });

  it("disables the control when disabled is set", () => {
    render(
      <TextArea
        attribute={spec({ type: "textarea" })}
        value=""
        onChange={vi.fn()}
        disabled
        testId="artifact-field-description"
      />
    );
    expect(screen.getByTestId("artifact-field-description")).toBeDisabled();
  });

  it("emits a number, not a string, from the number field", () => {
    const onChange = vi.fn();
    render(
      <NumberField
        attribute={spec({ type: "number", name: "effort" })}
        value={1}
        onChange={onChange}
        disabled={false}
        testId="artifact-field-effort"
      />
    );
    fireEvent.change(screen.getByTestId("artifact-field-effort"), {
      target: { value: "8" },
    });
    expect(onChange).toHaveBeenCalledWith(8);
  });

  it("emits null when the number field is cleared", () => {
    const onChange = vi.fn();
    render(
      <NumberField
        attribute={spec({ type: "number", name: "effort" })}
        value={1}
        onChange={onChange}
        disabled={false}
        testId="artifact-field-effort"
      />
    );
    fireEvent.change(screen.getByTestId("artifact-field-effort"), {
      target: { value: "" },
    });
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("emits a boolean from the toggle", () => {
    const onChange = vi.fn();
    render(
      <BooleanToggle
        attribute={spec({ type: "boolean", name: "suspect" })}
        value={false}
        onChange={onChange}
        disabled={false}
        testId="artifact-field-suspect"
      />
    );
    fireEvent.click(screen.getByTestId("artifact-field-suspect"));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("keeps an unknown enum value instead of silently coercing to option 0", () => {
    // #274: a <select> shows option[0] for an unknown value, so Save would
    // downgrade a working configuration. The unknown value stays selectable.
    render(
      <EnumSelect
        attribute={spec({
          type: "enum",
          name: "category",
          options: [
            { value: "a", label_de: "A", label_en: "A" },
            { value: "b", label_de: "B", label_en: "B" },
          ],
        })}
        value="legacy"
        onChange={vi.fn()}
        disabled={false}
        testId="artifact-field-category"
      />
    );
    const select = screen.getByTestId("artifact-field-category") as HTMLSelectElement;
    expect(select.value).toBe("legacy");
    expect(screen.getByRole("option", { name: /legacy/ })).toBeInTheDocument();
  });

  it("toggles a value in and out of a multi-enum", () => {
    const onChange = vi.fn();
    render(
      <MultiEnum
        attribute={spec({
          type: "multi-enum",
          name: "tags",
          options: [
            { value: "a", label_de: "A", label_en: "A" },
            { value: "b", label_de: "B", label_en: "B" },
          ],
        })}
        value={["a"]}
        onChange={onChange}
        disabled={false}
        testId="artifact-field-tags"
      />
    );
    fireEvent.click(screen.getByTestId("artifact-field-tags-option-b"));
    expect(onChange).toHaveBeenCalledWith(["a", "b"]);
    fireEvent.click(screen.getByTestId("artifact-field-tags-option-a"));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("uses a native date input", () => {
    render(
      <DateField
        attribute={spec({ type: "date", name: "due_date" })}
        value="2026-09-04"
        onChange={vi.fn()}
        disabled={false}
        testId="artifact-field-due_date"
      />
    );
    expect(screen.getByTestId("artifact-field-due_date")).toHaveAttribute(
      "type",
      "date"
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npx vitest run src/test/ArtifactFormFields.test.tsx`
Expected: FAIL — cannot resolve `../components/shared/ArtifactForm/fields`.

- [ ] **Step 3: Write the shell and the CSS**

Create `frontend/src/components/shared/ArtifactForm/ArtifactForm.module.css`:

```css
/* Definition-driven artifact form. All values come from styles/tokens.css —
   no hardcoded colours or sizes (design-tokens ratchet). */

.form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.section {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
}

.sectionHeader {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  background: none;
  border: none;
  cursor: pointer;
  font: inherit;
  font-weight: var(--font-weight-semibold);
  color: var(--color-text);
  padding: 0;
}

.sectionBody {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-top: var(--space-3);
}

.field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.label {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.required::after {
  content: " *";
  color: var(--color-danger);
}

.control {
  width: 100%;
  padding: var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  font: inherit;
}

.control:disabled {
  background: var(--color-surface-muted);
  color: var(--color-text-muted);
  cursor: not-allowed;
}

.controlInvalid {
  border-color: var(--color-danger);
}

.help {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.errors {
  font-size: var(--font-size-xs);
  color: var(--color-danger);
}

.checkboxRow {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.optionList {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.optionChip {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  padding: var(--space-1) var(--space-3);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
  font: inherit;
}

.optionChipSelected {
  background: var(--color-primary);
  color: var(--color-on-primary);
  border-color: var(--color-primary);
}

.actions {
  display: flex;
  gap: var(--space-2);
  justify-content: flex-end;
}

.widget {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.matrixGrid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-2);
}

.tabList {
  display: flex;
  gap: var(--space-2);
  border-bottom: 1px solid var(--color-border);
}

.tab {
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  padding: var(--space-2);
  cursor: pointer;
  font: inherit;
  color: var(--color-text-muted);
}

.tabActive {
  border-bottom-color: var(--color-primary);
  color: var(--color-text);
}

.stepRow {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
}

.stepIndex {
  min-width: var(--space-6);
  color: var(--color-text-muted);
}
```

If a custom property referenced above is absent from `frontend/src/styles/tokens.css`, add it there in this same commit rather than hardcoding a literal — `frontend/src/test/design-tokens.test.ts` fails on hex literals.

Create `frontend/src/components/shared/ArtifactForm/fields/FieldShell.tsx`:

```tsx
/**
 * Shared chrome for every definition-driven field: label, required marker,
 * help text and the server-side error list, wired for accessibility.
 *
 * Every field component renders its control inside this shell so label/error
 * association is implemented once instead of eight times.
 */

import type { ReactNode } from "react";

import type { AttributeOption, AttributeSpec } from "../../../../api/attribute-definitions";
import styles from "../ArtifactForm.module.css";

export interface FieldProps<T = unknown> {
  attribute: AttributeSpec;
  value: T;
  onChange: (next: T) => void;
  disabled: boolean;
  /** Server-side validation messages for this attribute, if any. */
  errors?: string[];
  /** Stable `data-testid` for the control itself: `artifact-field-<name>`. */
  testId: string;
}

/** Definition label for the active language, falling back to the raw name. */
export function attributeLabel(attribute: AttributeSpec, language: string): string {
  const localized = language.startsWith("de") ? attribute.label.de : attribute.label.en;
  return localized || attribute.name;
}

export function optionLabel(option: AttributeOption, language: string): string {
  const localized = language.startsWith("de") ? option.label_de : option.label_en;
  return localized || option.value;
}

export function helpText(attribute: AttributeSpec, language: string): string {
  return language.startsWith("de") ? attribute.help_text.de : attribute.help_text.en;
}

interface FieldShellProps {
  attribute: AttributeSpec;
  language: string;
  errors?: string[];
  testId: string;
  children: ReactNode;
}

export function FieldShell({
  attribute,
  language,
  errors,
  testId,
  children,
}: FieldShellProps): JSX.Element {
  const help = helpText(attribute, language);
  return (
    <div className={styles.field}>
      <label
        className={`${styles.label} ${attribute.required ? styles.required : ""}`}
        htmlFor={testId}
      >
        {attributeLabel(attribute, language)}
      </label>
      {children}
      {help ? (
        <span className={styles.help} id={`${testId}-help`}>
          {help}
        </span>
      ) : null}
      {errors?.length ? (
        <span className={styles.errors} id={`${testId}-error`} role="alert">
          {errors.join(", ")}
        </span>
      ) : null}
    </div>
  );
}

/** ARIA wiring shared by every control inside a `FieldShell`. */
export function ariaProps(
  attribute: AttributeSpec,
  testId: string,
  errors?: string[]
): Record<string, string | boolean | undefined> {
  const described = [
    helpText(attribute, "en") || helpText(attribute, "de") ? `${testId}-help` : null,
    errors?.length ? `${testId}-error` : null,
  ].filter(Boolean);
  return {
    "aria-required": attribute.required,
    "aria-invalid": Boolean(errors?.length),
    "aria-describedby": described.length ? described.join(" ") : undefined,
  };
}
```

- [ ] **Step 4: Write the eight field components**

Create `frontend/src/components/shared/ArtifactForm/fields/TextField.tsx`:

```tsx
import { useTranslation } from "react-i18next";

import styles from "../ArtifactForm.module.css";
import { FieldShell, ariaProps, type FieldProps } from "./FieldShell";

export function TextField({
  attribute,
  value,
  onChange,
  disabled,
  errors,
  testId,
}: FieldProps<string | null>): JSX.Element {
  const { i18n } = useTranslation();
  return (
    <FieldShell
      attribute={attribute}
      language={i18n.language}
      errors={errors}
      testId={testId}
    >
      <input
        id={testId}
        data-testid={testId}
        className={`${styles.control} ${errors?.length ? styles.controlInvalid : ""}`}
        type="text"
        value={value ?? ""}
        disabled={disabled}
        maxLength={attribute.validation.length}
        onChange={(event) => onChange(event.target.value)}
        {...ariaProps(attribute, testId, errors)}
      />
    </FieldShell>
  );
}
```

Create `frontend/src/components/shared/ArtifactForm/fields/TextArea.tsx`:

```tsx
import { useTranslation } from "react-i18next";

import styles from "../ArtifactForm.module.css";
import { FieldShell, ariaProps, type FieldProps } from "./FieldShell";

export function TextArea({
  attribute,
  value,
  onChange,
  disabled,
  errors,
  testId,
}: FieldProps<string | null>): JSX.Element {
  const { i18n } = useTranslation();
  return (
    <FieldShell
      attribute={attribute}
      language={i18n.language}
      errors={errors}
      testId={testId}
    >
      <textarea
        id={testId}
        data-testid={testId}
        className={`${styles.control} ${errors?.length ? styles.controlInvalid : ""}`}
        rows={6}
        value={value ?? ""}
        disabled={disabled}
        maxLength={attribute.validation.length}
        onChange={(event) => onChange(event.target.value)}
        {...ariaProps(attribute, testId, errors)}
      />
    </FieldShell>
  );
}
```

Create `frontend/src/components/shared/ArtifactForm/fields/NumberField.tsx`:

```tsx
import { useTranslation } from "react-i18next";

import styles from "../ArtifactForm.module.css";
import { FieldShell, ariaProps, type FieldProps } from "./FieldShell";

export function NumberField({
  attribute,
  value,
  onChange,
  disabled,
  errors,
  testId,
}: FieldProps<number | null>): JSX.Element {
  const { i18n } = useTranslation();
  return (
    <FieldShell
      attribute={attribute}
      language={i18n.language}
      errors={errors}
      testId={testId}
    >
      <input
        id={testId}
        data-testid={testId}
        className={`${styles.control} ${errors?.length ? styles.controlInvalid : ""}`}
        type="number"
        value={value ?? ""}
        disabled={disabled}
        min={attribute.validation.min}
        max={attribute.validation.max}
        onChange={(event) => {
          // Emit null (not NaN, not "") when cleared: the backend treats null
          // as "not supplied" and NaN would serialise as invalid JSON.
          const raw = event.target.value;
          onChange(raw === "" ? null : Number(raw));
        }}
        {...ariaProps(attribute, testId, errors)}
      />
    </FieldShell>
  );
}
```

Create `frontend/src/components/shared/ArtifactForm/fields/BooleanToggle.tsx`:

```tsx
import { useTranslation } from "react-i18next";

import styles from "../ArtifactForm.module.css";
import { FieldShell, ariaProps, type FieldProps } from "./FieldShell";

export function BooleanToggle({
  attribute,
  value,
  onChange,
  disabled,
  errors,
  testId,
}: FieldProps<boolean | null>): JSX.Element {
  const { i18n } = useTranslation();
  return (
    <FieldShell
      attribute={attribute}
      language={i18n.language}
      errors={errors}
      testId={testId}
    >
      <span className={styles.checkboxRow}>
        <input
          id={testId}
          data-testid={testId}
          type="checkbox"
          checked={Boolean(value)}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
          {...ariaProps(attribute, testId, errors)}
        />
      </span>
    </FieldShell>
  );
}
```

Create `frontend/src/components/shared/ArtifactForm/fields/EnumSelect.tsx`:

```tsx
import { useTranslation } from "react-i18next";

import styles from "../ArtifactForm.module.css";
import { FieldShell, ariaProps, optionLabel, type FieldProps } from "./FieldShell";

export function EnumSelect({
  attribute,
  value,
  onChange,
  disabled,
  errors,
  testId,
}: FieldProps<string | null>): JSX.Element {
  const { i18n, t } = useTranslation();
  const current = value ?? "";
  // Issue #274: a <select> silently displays option[0] when its value matches
  // no option, so a Save would downgrade a legacy value the user never
  // touched. Keep the unknown value as a real option instead.
  const isUnknown = current !== "" && !attribute.options.some((o) => o.value === current);
  return (
    <FieldShell
      attribute={attribute}
      language={i18n.language}
      errors={errors}
      testId={testId}
    >
      <select
        id={testId}
        data-testid={testId}
        className={`${styles.control} ${errors?.length ? styles.controlInvalid : ""}`}
        value={current}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value || null)}
        {...ariaProps(attribute, testId, errors)}
      >
        {!attribute.required ? <option value="">{t("common.none")}</option> : null}
        {isUnknown ? (
          <option value={current}>
            {t("artifactForm.unknownValue", { value: current })}
          </option>
        ) : null}
        {attribute.options.map((option) => (
          <option key={option.value} value={option.value}>
            {optionLabel(option, i18n.language)}
          </option>
        ))}
      </select>
    </FieldShell>
  );
}
```

Create `frontend/src/components/shared/ArtifactForm/fields/MultiEnum.tsx`:

```tsx
import { useTranslation } from "react-i18next";

import styles from "../ArtifactForm.module.css";
import { FieldShell, optionLabel, type FieldProps } from "./FieldShell";

export function MultiEnum({
  attribute,
  value,
  onChange,
  disabled,
  errors,
  testId,
}: FieldProps<string[] | null>): JSX.Element {
  const { i18n } = useTranslation();
  const selected = value ?? [];
  return (
    <FieldShell
      attribute={attribute}
      language={i18n.language}
      errors={errors}
      testId={testId}
    >
      <div
        className={styles.optionList}
        id={testId}
        data-testid={testId}
        role="group"
        aria-required={attribute.required}
        aria-invalid={Boolean(errors?.length)}
      >
        {attribute.options.map((option) => {
          const isOn = selected.includes(option.value);
          return (
            <button
              key={option.value}
              type="button"
              data-testid={`${testId}-option-${option.value}`}
              className={`${styles.optionChip} ${isOn ? styles.optionChipSelected : ""}`}
              disabled={disabled}
              aria-pressed={isOn}
              onClick={() =>
                onChange(
                  isOn
                    ? selected.filter((v) => v !== option.value)
                    : [...selected, option.value]
                )
              }
            >
              {optionLabel(option, i18n.language)}
            </button>
          );
        })}
      </div>
    </FieldShell>
  );
}
```

Create `frontend/src/components/shared/ArtifactForm/fields/DateField.tsx`:

```tsx
import { useTranslation } from "react-i18next";

import styles from "../ArtifactForm.module.css";
import { FieldShell, ariaProps, type FieldProps } from "./FieldShell";

export function DateField({
  attribute,
  value,
  onChange,
  disabled,
  errors,
  testId,
}: FieldProps<string | null>): JSX.Element {
  const { i18n } = useTranslation();
  return (
    <FieldShell
      attribute={attribute}
      language={i18n.language}
      errors={errors}
      testId={testId}
    >
      {/* Native date input on purpose: no picker dependency, and the browser
          already handles locale, keyboard and screen-reader semantics. */}
      <input
        id={testId}
        data-testid={testId}
        className={`${styles.control} ${errors?.length ? styles.controlInvalid : ""}`}
        type="date"
        value={value ? String(value).slice(0, 10) : ""}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value || null)}
        {...ariaProps(attribute, testId, errors)}
      />
    </FieldShell>
  );
}
```

Create `frontend/src/components/shared/ArtifactForm/fields/ReferencePicker.tsx`:

```tsx
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { resolveArtifactRefs, type ArtifactRef } from "../../../../api/artifactRefs";
import { useWorkspace } from "../../../../context/WorkspaceContext";
import styles from "../ArtifactForm.module.css";
import { FieldShell, ariaProps, type FieldProps } from "./FieldShell";

/**
 * Picks another artifact by id. Options come from the same resolver the trace
 * panels use (`api/artifactRefs`), so ids and titles never diverge between the
 * form and the graph.
 */
export function ReferencePicker({
  attribute,
  value,
  onChange,
  disabled,
  errors,
  testId,
}: FieldProps<string | null>): JSX.Element {
  const { i18n, t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [refs, setRefs] = useState<ArtifactRef[]>([]);

  useEffect(() => {
    let cancelled = false;
    if (!activeWorkspace?.id) return undefined;
    resolveArtifactRefs(activeWorkspace.id)
      .then((resolved) => {
        if (!cancelled) setRefs(resolved);
      })
      .catch(() => {
        if (!cancelled) setRefs([]);
      });
    return () => {
      cancelled = true;
    };
  }, [activeWorkspace?.id]);

  const current = value ?? "";
  const isUnknown = current !== "" && !refs.some((r) => r.id === current);

  return (
    <FieldShell
      attribute={attribute}
      language={i18n.language}
      errors={errors}
      testId={testId}
    >
      <select
        id={testId}
        data-testid={testId}
        className={`${styles.control} ${errors?.length ? styles.controlInvalid : ""}`}
        value={current}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value || null)}
        {...ariaProps(attribute, testId, errors)}
      >
        <option value="">{t("common.none")}</option>
        {isUnknown ? (
          <option value={current}>
            {t("artifactForm.unknownValue", { value: current })}
          </option>
        ) : null}
        {refs.map((ref) => (
          <option key={ref.id} value={ref.id}>
            {ref.displayId ? `${ref.displayId} — ${ref.title}` : ref.title}
          </option>
        ))}
      </select>
    </FieldShell>
  );
}
```

Create `frontend/src/components/shared/ArtifactForm/fields/UserPicker.tsx`:

```tsx
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { usersApi, type User } from "../../../../api/users";
import styles from "../ArtifactForm.module.css";
import { FieldShell, ariaProps, type FieldProps } from "./FieldShell";

/**
 * Picks a tenant user. The `user` attribute type exists so the
 * Menschen-im-System spec's `owner`/`assignee` FKs render without a new field
 * kind — this component is that type's renderer.
 */
export function UserPicker({
  attribute,
  value,
  onChange,
  disabled,
  errors,
  testId,
}: FieldProps<string | null>): JSX.Element {
  const { i18n, t } = useTranslation();
  const [users, setUsers] = useState<User[]>([]);

  useEffect(() => {
    let cancelled = false;
    usersApi
      .list()
      .then((resolved) => {
        if (!cancelled) setUsers(resolved);
      })
      .catch(() => {
        if (!cancelled) setUsers([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const current = value ?? "";
  const isUnknown = current !== "" && !users.some((u) => u.id === current);

  return (
    <FieldShell
      attribute={attribute}
      language={i18n.language}
      errors={errors}
      testId={testId}
    >
      <select
        id={testId}
        data-testid={testId}
        className={`${styles.control} ${errors?.length ? styles.controlInvalid : ""}`}
        value={current}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value || null)}
        {...ariaProps(attribute, testId, errors)}
      >
        <option value="">{t("common.unassigned")}</option>
        {isUnknown ? (
          <option value={current}>
            {t("artifactForm.unknownValue", { value: current })}
          </option>
        ) : null}
        {users.map((user) => (
          <option key={user.id} value={user.id}>
            {user.full_name || user.email}
          </option>
        ))}
      </select>
    </FieldShell>
  );
}
```

Create `frontend/src/components/shared/ArtifactForm/fields/index.ts`:

```ts
export { BooleanToggle } from "./BooleanToggle";
export { DateField } from "./DateField";
export { EnumSelect } from "./EnumSelect";
export { FieldShell, ariaProps, attributeLabel, helpText, optionLabel } from "./FieldShell";
export type { FieldProps } from "./FieldShell";
export { MultiEnum } from "./MultiEnum";
export { NumberField } from "./NumberField";
export { ReferencePicker } from "./ReferencePicker";
export { TextArea } from "./TextArea";
export { TextField } from "./TextField";
export { UserPicker } from "./UserPicker";
```

- [ ] **Step 5: Add the i18n keys**

In `frontend/src/i18n/locales/de.json` and `en.json` add — as **nested objects**, never dotted flat keys (P4):

de.json:
```json
  "artifactForm": {
    "unknownValue": "Unbekannter Wert: {{value}}",
    "expandSection": "Abschnitt {{section}} aufklappen",
    "collapseSection": "Abschnitt {{section}} einklappen",
    "lockedHint": "systemkritisch, nicht änderbar",
    "unsavedChanges": "Ungespeicherte Änderungen gehen verloren. Fortfahren?",
    "saveFailed": "Speichern fehlgeschlagen",
    "deleteConfirm": "Dieses Artefakt wirklich löschen?"
  }
```

en.json:
```json
  "artifactForm": {
    "unknownValue": "Unknown value: {{value}}",
    "expandSection": "Expand section {{section}}",
    "collapseSection": "Collapse section {{section}}",
    "lockedHint": "system-critical, not changeable",
    "unsavedChanges": "Unsaved changes will be lost. Continue?",
    "saveFailed": "Save failed",
    "deleteConfirm": "Really delete this artifact?"
  }
```

Verify `common.none` and `common.unassigned` already exist in both files; add them the same way if not.

- [ ] **Step 6: Run test to verify it passes**

Run: `docker compose exec frontend npx vitest run src/test/ArtifactFormFields.test.tsx src/test/i18n-parity.test.ts --testTimeout=30000`
Expected: PASS (12 field tests + i18n parity)

- [ ] **Step 7: Verify the ratchets did not move**

Run: `docker compose exec frontend npx vitest run src/test/ui-ratchet.test.ts src/test/design-tokens.test.ts --testTimeout=30000`
Expected: PASS with `STYLE_BRACE_BASELINE` unchanged — this task adds no inline styles and no hex literals.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/shared/ArtifactForm frontend/src/i18n/locales frontend/src/test/ArtifactFormFields.test.tsx
git commit -m "feat(attribute-definitions): add ArtifactForm field component library"
```

---

### Task 17: Widget registry

Spec section 6.3 — the three special cases that do not fit a basic field type. The registry is an open extension point: a new special case adds a key here and in `attribute_definitions/schema.py::WIDGET_KEYS`, it never weakens the renderer contract.

**Files:**
- Create: `frontend/src/components/shared/ArtifactForm/widgets/RiskMatrixRpz.tsx`
- Create: `frontend/src/components/shared/ArtifactForm/widgets/MarkdownTabGroup.tsx`
- Create: `frontend/src/components/shared/ArtifactForm/widgets/StepsEditor.tsx`
- Create: `frontend/src/components/shared/ArtifactForm/widget-registry.ts`
- Test: `frontend/src/test/ArtifactFormWidgets.test.tsx`

**Interfaces:**
- Consumes: `AttributeSpec` from `../../../../api/attribute-definitions`; `MarkdownPreview` from `../../../RequirementEditors/MarkdownPreview`; the field components from `../fields`.
- Produces:

```ts
export interface WidgetProps {
  attribute: AttributeSpec;
  /** Values of the attributes named in `attribute.fields`, keyed by name. */
  values: Record<string, unknown>;
  onChange: (fieldName: string, next: unknown) => void;
  disabled: boolean;
  errors?: Record<string, string[]>;
  /** `artifact-widget-<attribute.name>`. */
  testId: string;
}

export const WIDGET_REGISTRY: Record<WidgetKey, (props: WidgetProps) => JSX.Element>;
```

  plus `RISK_PROBABILITY_SCORE` / `RISK_IMPACT_SCORE` and `computeRpn(probability, impact, detection): number` from `RiskMatrixRpz.tsx`.

`computeRpn` mirrors `Risk.rpn` on the backend exactly (`_PROB_NUMERIC`/`_IMPACT_NUMERIC` map `low/medium/high` to `1/2/3`, unknown values fall back to `1`, and a missing `detection` falls back to `5`), so the live preview never disagrees with the stored score.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/ArtifactFormWidgets.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  WIDGET_REGISTRY,
  computeRpn,
} from "../components/shared/ArtifactForm/widget-registry";
import type { AttributeSpec } from "../api/attribute-definitions";

function widgetSpec(over: Partial<AttributeSpec>): AttributeSpec {
  return {
    name: "w",
    kind: "core",
    type: "widget",
    widget_key: null,
    fields: [],
    options: [],
    required: false,
    visible: true,
    locked: false,
    editable: true,
    section: "general",
    order: 0,
    label: { de: "W", en: "W" },
    help_text: { de: "", en: "" },
    default: null,
    validation: {},
    ai_elicit: false,
    export: false,
    audience: "basic",
    ...over,
  };
}

describe("ArtifactForm widget registry", () => {
  it("registers exactly the three spec widget keys", () => {
    expect(Object.keys(WIDGET_REGISTRY).sort()).toEqual([
      "markdown_tab_group",
      "risk_matrix_rpz",
      "steps_editor",
    ]);
  });

  it("computes the RPN the same way the backend does", () => {
    expect(computeRpn("low", "low", 1)).toBe(1);
    expect(computeRpn("high", "high", 10)).toBe(90);
    expect(computeRpn("medium", "high", null)).toBe(30); // detection falls back to 5
    expect(computeRpn("unknown", "high", 2)).toBe(6); // unknown probability -> 1
  });

  it("renders the risk matrix and updates the RPN live", () => {
    const onChange = vi.fn();
    const Widget = WIDGET_REGISTRY.risk_matrix_rpz;
    const attribute = widgetSpec({
      name: "risk_matrix",
      widget_key: "risk_matrix_rpz",
      fields: ["probability", "impact", "detection"],
    });
    const { rerender } = render(
      <Widget
        attribute={attribute}
        values={{ probability: "low", impact: "low", detection: 1 }}
        onChange={onChange}
        disabled={false}
        testId="artifact-widget-risk_matrix"
      />
    );
    expect(screen.getByTestId("artifact-widget-risk_matrix-rpn")).toHaveTextContent("1");

    rerender(
      <Widget
        attribute={attribute}
        values={{ probability: "high", impact: "high", detection: 10 }}
        onChange={onChange}
        disabled={false}
        testId="artifact-widget-risk_matrix"
      />
    );
    expect(screen.getByTestId("artifact-widget-risk_matrix-rpn")).toHaveTextContent("90");
  });

  it("reports a risk-matrix edit under the bound field name", () => {
    const onChange = vi.fn();
    const Widget = WIDGET_REGISTRY.risk_matrix_rpz;
    render(
      <Widget
        attribute={widgetSpec({
          name: "risk_matrix",
          widget_key: "risk_matrix_rpz",
          fields: ["probability", "impact", "detection"],
        })}
        values={{ probability: "low", impact: "low", detection: 1 }}
        onChange={onChange}
        disabled={false}
        testId="artifact-widget-risk_matrix"
      />
    );
    fireEvent.change(screen.getByTestId("artifact-widget-risk_matrix-detection"), {
      target: { value: "7" },
    });
    expect(onChange).toHaveBeenCalledWith("detection", 7);
  });

  it("renders one markdown tab per bound field and switches between them", () => {
    const Widget = WIDGET_REGISTRY.markdown_tab_group;
    render(
      <Widget
        attribute={widgetSpec({
          name: "decision_record",
          widget_key: "markdown_tab_group",
          fields: ["description", "context", "consequences"],
        })}
        values={{ description: "d", context: "c", consequences: "q" }}
        onChange={vi.fn()}
        disabled={false}
        testId="artifact-widget-decision_record"
      />
    );
    expect(screen.getAllByRole("tab")).toHaveLength(3);
    fireEvent.click(screen.getByTestId("artifact-widget-decision_record-tab-context"));
    expect(
      screen.getByTestId("artifact-widget-decision_record-tab-context")
    ).toHaveAttribute("aria-selected", "true");
  });

  it("adds, edits and removes a test step", () => {
    const onChange = vi.fn();
    const Widget = WIDGET_REGISTRY.steps_editor;
    render(
      <Widget
        attribute={widgetSpec({
          name: "steps",
          widget_key: "steps_editor",
          fields: ["steps_data"],
        })}
        values={{ steps_data: ["first"] }}
        onChange={onChange}
        disabled={false}
        testId="artifact-widget-steps"
      />
    );
    fireEvent.click(screen.getByTestId("artifact-widget-steps-add"));
    expect(onChange).toHaveBeenCalledWith("steps_data", ["first", ""]);

    fireEvent.change(screen.getByTestId("artifact-widget-steps-step-0"), {
      target: { value: "edited" },
    });
    expect(onChange).toHaveBeenCalledWith("steps_data", ["edited"]);

    fireEvent.click(screen.getByTestId("artifact-widget-steps-remove-0"));
    expect(onChange).toHaveBeenCalledWith("steps_data", []);
  });

  it("tolerates a non-array steps value", () => {
    const Widget = WIDGET_REGISTRY.steps_editor;
    render(
      <Widget
        attribute={widgetSpec({
          name: "steps",
          widget_key: "steps_editor",
          fields: ["steps_data"],
        })}
        values={{ steps_data: null }}
        onChange={vi.fn()}
        disabled={false}
        testId="artifact-widget-steps"
      />
    );
    expect(screen.queryAllByTestId(/artifact-widget-steps-step-/)).toHaveLength(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npx vitest run src/test/ArtifactFormWidgets.test.tsx`
Expected: FAIL — cannot resolve `../components/shared/ArtifactForm/widget-registry`.

- [ ] **Step 3: Write the widgets**

Create `frontend/src/components/shared/ArtifactForm/widgets/RiskMatrixRpz.tsx`:

```tsx
import { useTranslation } from "react-i18next";

import styles from "../ArtifactForm.module.css";
import type { WidgetProps } from "../widget-registry";

/** Mirrors ``Risk._PROB_NUMERIC`` on the backend. */
export const RISK_PROBABILITY_SCORE: Record<string, number> = {
  low: 1,
  medium: 2,
  high: 3,
};

/** Mirrors ``Risk._IMPACT_NUMERIC`` on the backend. */
export const RISK_IMPACT_SCORE: Record<string, number> = {
  low: 1,
  medium: 2,
  high: 3,
};

/**
 * Risk Priority Number = probability x impact x detection.
 *
 * Kept byte-compatible with ``Risk.rpn`` (backend/application/models.py): an
 * unrecognised probability/impact scores 1, a missing detection falls back to
 * 5. A divergence here would show the user a number the server never stores.
 */
export function computeRpn(
  probability: unknown,
  impact: unknown,
  detection: unknown
): number {
  const p = RISK_PROBABILITY_SCORE[String(probability)] ?? 1;
  const i = RISK_IMPACT_SCORE[String(impact)] ?? 1;
  const d = typeof detection === "number" && detection > 0 ? detection : 5;
  return p * i * d;
}

const LEVEL_OPTIONS = ["low", "medium", "high"] as const;

export function RiskMatrixRpz({
  attribute,
  values,
  onChange,
  disabled,
  errors,
  testId,
}: WidgetProps): JSX.Element {
  const { t } = useTranslation();
  const rpn = computeRpn(values.probability, values.impact, values.detection);

  return (
    <div className={styles.widget} data-testid={testId}>
      <span className={styles.label}>{t("risks.matrix")}</span>
      <div className={styles.matrixGrid}>
        {(["probability", "impact"] as const).map((field) => (
          <label key={field} className={styles.field}>
            <span className={styles.label}>{t(`risks.${field}`)}</span>
            <select
              className={styles.control}
              data-testid={`${testId}-${field}`}
              value={String(values[field] ?? "")}
              disabled={disabled}
              onChange={(event) => onChange(field, event.target.value || null)}
            >
              {LEVEL_OPTIONS.map((level) => (
                <option key={level} value={level}>
                  {t(`risks.level.${level}`)}
                </option>
              ))}
            </select>
          </label>
        ))}
        <label className={styles.field}>
          <span className={styles.label}>{t("risks.detection")}</span>
          <input
            className={styles.control}
            data-testid={`${testId}-detection`}
            type="number"
            min={1}
            max={10}
            value={typeof values.detection === "number" ? values.detection : ""}
            disabled={disabled}
            onChange={(event) =>
              onChange("detection", event.target.value === "" ? null : Number(event.target.value))
            }
          />
        </label>
      </div>
      <output className={styles.help} data-testid={`${testId}-rpn`}>
        {t("risks.rpn", { value: rpn })}
      </output>
      {attribute.fields
        .flatMap((field) => errors?.[field] ?? [])
        .map((message) => (
          <span key={message} className={styles.errors} role="alert">
            {message}
          </span>
        ))}
    </div>
  );
}
```

Create `frontend/src/components/shared/ArtifactForm/widgets/MarkdownTabGroup.tsx`:

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { MarkdownPreview } from "../../../RequirementEditors/MarkdownPreview";
import { tablistKeyboardNav } from "../../tablistKeyboardNav";
import styles from "../ArtifactForm.module.css";
import type { WidgetProps } from "../widget-registry";

/**
 * Groups several markdown fields under one tab strip — replaces AdrForm's three
 * stacked editors (description / context / consequences) without changing what
 * is stored: each tab writes its own bound field.
 */
export function MarkdownTabGroup({
  attribute,
  values,
  onChange,
  disabled,
  errors,
  testId,
}: WidgetProps): JSX.Element {
  const { t } = useTranslation();
  const [active, setActive] = useState<string>(attribute.fields[0] ?? "");

  return (
    <div className={styles.widget} data-testid={testId}>
      <div
        className={styles.tabList}
        role="tablist"
        onKeyDown={(event) =>
          tablistKeyboardNav(event, attribute.fields, active, setActive)
        }
      >
        {attribute.fields.map((field) => (
          <button
            key={field}
            type="button"
            role="tab"
            id={`${testId}-tab-${field}`}
            data-testid={`${testId}-tab-${field}`}
            aria-selected={active === field}
            aria-controls={`${testId}-panel-${field}`}
            tabIndex={active === field ? 0 : -1}
            className={`${styles.tab} ${active === field ? styles.tabActive : ""}`}
            onClick={() => setActive(field)}
          >
            {t(`artifactForm.field.${field}`, { defaultValue: field })}
          </button>
        ))}
      </div>
      {attribute.fields.map((field) =>
        active === field ? (
          <div
            key={field}
            role="tabpanel"
            id={`${testId}-panel-${field}`}
            aria-labelledby={`${testId}-tab-${field}`}
          >
            <MarkdownPreview
              id={`${testId}-editor-${field}`}
              value={String(values[field] ?? "")}
              onChange={(next: string) => onChange(field, next)}
              disabled={disabled}
            />
            {(errors?.[field] ?? []).map((message) => (
              <span key={message} className={styles.errors} role="alert">
                {message}
              </span>
            ))}
          </div>
        ) : null
      )}
    </div>
  );
}
```

If `MarkdownPreview` does not currently accept a `disabled` prop, add it as an optional prop that forwards to the underlying `textarea` in that same commit — the renderer needs read-only mode for `editable: false` attributes.

Create `frontend/src/components/shared/ArtifactForm/widgets/StepsEditor.tsx`:

```tsx
import { useTranslation } from "react-i18next";
import { Plus, Trash2 } from "lucide-react";

import styles from "../ArtifactForm.module.css";
import type { WidgetProps } from "../widget-registry";

/**
 * Ordered list editor for ``TestCase.steps``. Closes audit finding V: the
 * column exists but no form ever offered an editor for it, so steps could only
 * be written through the API.
 */
export function StepsEditor({
  attribute,
  values,
  onChange,
  disabled,
  errors,
  testId,
}: WidgetProps): JSX.Element {
  const { t } = useTranslation();
  const field = attribute.fields[0] ?? "steps_data";
  const raw = values[field];
  const steps: string[] = Array.isArray(raw) ? raw.map((s) => String(s)) : [];

  const write = (next: string[]): void => onChange(field, next);

  return (
    <div className={styles.widget} data-testid={testId}>
      {steps.map((step, index) => (
        <div key={index} className={styles.stepRow}>
          <span className={styles.stepIndex}>{index + 1}</span>
          <input
            className={styles.control}
            data-testid={`${testId}-step-${index}`}
            type="text"
            value={step}
            disabled={disabled}
            aria-label={t("testcases.step", { index: index + 1 })}
            onChange={(event) =>
              write(steps.map((s, i) => (i === index ? event.target.value : s)))
            }
          />
          <button
            type="button"
            data-testid={`${testId}-remove-${index}`}
            disabled={disabled}
            aria-label={t("testcases.removeStep", { index: index + 1 })}
            onClick={() => write(steps.filter((_, i) => i !== index))}
          >
            <Trash2 aria-hidden="true" size={16} />
          </button>
        </div>
      ))}
      <button
        type="button"
        data-testid={`${testId}-add`}
        disabled={disabled}
        onClick={() => write([...steps, ""])}
      >
        <Plus aria-hidden="true" size={16} />
        {t("testcases.addStep")}
      </button>
      {(errors?.[field] ?? []).map((message) => (
        <span key={message} className={styles.errors} role="alert">
          {message}
        </span>
      ))}
    </div>
  );
}
```

Create `frontend/src/components/shared/ArtifactForm/widget-registry.ts`:

```ts
/**
 * Widget registry (spec section 6.3).
 *
 * A `type: "widget"` attribute names a `widget_key`; this map turns that key
 * into a component. Deliberately an open extension point: a new special case
 * discovered during the form rollout adds a key here and to
 * `attribute_definitions/schema.py::WIDGET_KEYS`, instead of weakening the
 * renderer's field contract.
 */

import type { AttributeSpec, WidgetKey } from "../../../api/attribute-definitions";
import { MarkdownTabGroup } from "./widgets/MarkdownTabGroup";
import { RiskMatrixRpz } from "./widgets/RiskMatrixRpz";
import { StepsEditor } from "./widgets/StepsEditor";

export interface WidgetProps {
  attribute: AttributeSpec;
  /** Values of the attributes named in `attribute.fields`, keyed by name. */
  values: Record<string, unknown>;
  onChange: (fieldName: string, next: unknown) => void;
  disabled: boolean;
  errors?: Record<string, string[]>;
  /** `artifact-widget-<attribute.name>`. */
  testId: string;
}

export const WIDGET_REGISTRY: Record<WidgetKey, (props: WidgetProps) => JSX.Element> = {
  risk_matrix_rpz: RiskMatrixRpz,
  markdown_tab_group: MarkdownTabGroup,
  steps_editor: StepsEditor,
};

export { computeRpn, RISK_IMPACT_SCORE, RISK_PROBABILITY_SCORE } from "./widgets/RiskMatrixRpz";
```

- [ ] **Step 4: Add the i18n keys**

Add to both `de.json` and `en.json` (nested objects):

de.json — under `risks`: `"matrix": "Risikomatrix"`, `"detection": "Entdeckung"`, `"rpn": "RPZ: {{value}}"`, `"level": { "low": "Niedrig", "medium": "Mittel", "high": "Hoch" }`. Under `testcases`: `"step": "Schritt {{index}}"`, `"addStep": "Schritt hinzufügen"`, `"removeStep": "Schritt {{index}} entfernen"`. Under `artifactForm`: `"field": { "description": "Beschreibung", "context": "Kontext", "consequences": "Konsequenzen" }`.

en.json — the same keys with `"matrix": "Risk matrix"`, `"detection": "Detection"`, `"rpn": "RPN: {{value}}"`, `"level": { "low": "Low", "medium": "Medium", "high": "High" }`, `"step": "Step {{index}}"`, `"addStep": "Add step"`, `"removeStep": "Remove step {{index}}"`, `"field": { "description": "Description", "context": "Context", "consequences": "Consequences" }`.

Reuse `risks.probability` / `risks.impact` if they already exist; add them the same way if not.

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec frontend npx vitest run src/test/ArtifactFormWidgets.test.tsx src/test/i18n-parity.test.ts --testTimeout=30000`
Expected: PASS (7 widget tests + i18n parity)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/shared/ArtifactForm frontend/src/i18n/locales frontend/src/test/ArtifactFormWidgets.test.tsx
git commit -m "feat(attribute-definitions): add ArtifactForm widget registry"
```

---

### Task 18: `ArtifactForm` renderer

Spec section 6. One renderer for all ten types: sections and fields in `order`, custom fields in the section the definition names, `editable: "workflow"` rendered as status badge + transition buttons, and delete / dirty warning / cancel implemented once instead of seven times (spec section 6.3 parity policy).

**Files:**
- Create: `frontend/src/components/shared/ArtifactForm/ArtifactForm.tsx`
- Create: `frontend/src/components/shared/ArtifactForm/useArtifactDefinition.ts`
- Create: `frontend/src/components/shared/ArtifactForm/field-errors.ts`
- Create: `frontend/src/components/shared/ArtifactForm/index.ts`
- Test: `frontend/src/test/ArtifactForm.test.tsx`

**Interfaces:**
- Consumes: `attributeDefinitionsApi`, `AttributeSpec`, `ResolvedAttributeDefinition` (Task 15); the field components and `attributeLabel` (Task 16); `WIDGET_REGISTRY`, `WidgetProps` (Task 17); `useWorkspace`, `useFormDirty`, `ConfirmDialog`, `WorkflowStatusEditor`, `extractErrorMessage`.
- Produces:
  - `interface ArtifactFormValues { [name: string]: unknown; custom_fields?: Record<string, unknown> }`
  - `interface ArtifactFormProps { itemType: string; artifactId: string | null; initialValues: ArtifactFormValues; onSave: (values: ArtifactFormValues) => Promise<void>; onDelete?: () => Promise<void>; onDirtyChange?: (isDirty: boolean) => void; mode?: "edit" | "read"; workflowArtifactType?: WorkflowArtifactType }`
  - `function ArtifactForm(props: ArtifactFormProps): JSX.Element`
  - `useArtifactDefinition(itemType: string): { definition: ResolvedAttributeDefinition | null; loading: boolean; error: string | null }`
  - `parseFieldErrors(message: string): Record<string, string[]>`
  - `groupIntoSections(attributes: AttributeSpec[]): { name: string; audience: AttributeAudience; attributes: AttributeSpec[] }[]`

Rendering rules, all derived from the definition:
1. `visible: false` → not rendered at all.
2. An attribute whose name appears in some `type: "widget"` attribute's `fields[]` is **not** rendered on its own — the widget draws it. This is a pure render rule; the data is unchanged, and the validator still sees the field.
3. `editable: "workflow"` → `WorkflowStatusEditor` (badge + transitions), never an editable control.
4. `editable: false` or `mode === "read"` → the control renders disabled.
5. A section is expanded by default unless **every** attribute in it has `audience: "expert"`; then it starts collapsed. A section containing a server-side error is always expanded so the message is reachable.
6. `kind: "extended"` values read from and write to `values.custom_fields`.

**Error-envelope contract:** the backend joins per-attribute messages as `"<name>: <msg>, <msg>; <name>: <msg>"` (Task 11). `parseFieldErrors` reverses exactly that format. Any message that does not match falls through to the form-level banner, so a changed envelope degrades to "shown once at the top", never to "silently swallowed".

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/ArtifactForm.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { attributeDefinitionsApi } from "../api/attribute-definitions";
import {
  ArtifactForm,
  groupIntoSections,
  parseFieldErrors,
} from "../components/shared/ArtifactForm";
import type { AttributeSpec } from "../api/attribute-definitions";

vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: { getWorkspace: vi.fn() },
}));

vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", preset: "standard" } }),
}));

vi.mock("../components/WorkflowStatusEditor", () => ({
  WorkflowStatusEditor: () => <div data-testid="workflow-status-editor" />,
}));

function spec(over: Partial<AttributeSpec>): AttributeSpec {
  return {
    name: "title",
    kind: "core",
    type: "text",
    widget_key: null,
    fields: [],
    options: [],
    required: false,
    visible: true,
    locked: false,
    editable: true,
    section: "general",
    order: 0,
    label: { de: "Titel", en: "Title" },
    help_text: { de: "", en: "" },
    default: null,
    validation: {},
    ai_elicit: false,
    export: false,
    audience: "basic",
    ...over,
  };
}

function mockDefinition(attributes: AttributeSpec[]): void {
  vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
    item_type: "Risk",
    preset: "standard",
    is_customized: false,
    version: 1,
    attributes,
  });
}

describe("parseFieldErrors", () => {
  it("reverses the backend's joined message format", () => {
    expect(parseFieldErrors("title: is required; uid: does not match")).toEqual({
      title: ["is required"],
      uid: ["does not match"],
    });
  });

  it("splits multiple messages for one attribute", () => {
    expect(parseFieldErrors("effort: must be a number, must be >= 1")).toEqual({
      effort: ["must be a number", "must be >= 1"],
    });
  });

  it("returns nothing for a message that does not match the format", () => {
    expect(parseFieldErrors("Internal server error")).toEqual({});
  });
});

describe("groupIntoSections", () => {
  it("keeps the definition's section and order", () => {
    const sections = groupIntoSections([
      spec({ name: "b", section: "classification", order: 1 }),
      spec({ name: "a", section: "general", order: 2 }),
      spec({ name: "c", section: "general", order: 1 }),
    ]);
    expect(sections.map((s) => s.name)).toEqual(["classification", "general"]);
    expect(sections[1].attributes.map((a) => a.name)).toEqual(["c", "a"]);
  });

  it("marks a section expert only when every attribute is expert", () => {
    const [mixed] = groupIntoSections([
      spec({ name: "a", audience: "expert" }),
      spec({ name: "b", audience: "basic" }),
    ]);
    expect(mixed.audience).toBe("basic");
    const [all] = groupIntoSections([
      spec({ name: "a", section: "x", audience: "expert" }),
      spec({ name: "b", section: "x", audience: "expert" }),
    ]);
    expect(all.audience).toBe("expert");
  });
});

describe("ArtifactForm", () => {
  beforeEach(() => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockReset();
  });

  it("renders every visible attribute of the definition", async () => {
    mockDefinition([spec({ name: "title" }), spec({ name: "description", type: "textarea" })]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T", description: "D" }}
        onSave={vi.fn()}
      />
    );
    expect(await screen.findByTestId("artifact-field-title")).toHaveValue("T");
    expect(screen.getByTestId("artifact-field-description")).toHaveValue("D");
  });

  it("does not render an invisible attribute", async () => {
    mockDefinition([spec({ name: "title" }), spec({ name: "hidden", visible: false })]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
      />
    );
    await screen.findByTestId("artifact-field-title");
    expect(screen.queryByTestId("artifact-field-hidden")).not.toBeInTheDocument();
  });

  it("renders the workflow status editor instead of a control for editable=workflow", async () => {
    mockDefinition([
      spec({ name: "status", type: "enum", editable: "workflow", locked: true }),
      spec({ name: "title" }),
    ]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T", status: "draft" }}
        onSave={vi.fn()}
        workflowArtifactType="Risk"
      />
    );
    expect(await screen.findByTestId("workflow-status-editor")).toBeInTheDocument();
    expect(screen.queryByTestId("artifact-field-status")).not.toBeInTheDocument();
  });

  it("does not render a field a widget already draws", async () => {
    mockDefinition([
      spec({
        name: "risk_matrix",
        type: "widget",
        widget_key: "risk_matrix_rpz",
        fields: ["probability", "impact", "detection"],
      }),
      spec({ name: "probability", type: "enum", options: [] }),
      spec({ name: "title" }),
    ]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T", probability: "low", impact: "low", detection: 3 }}
        onSave={vi.fn()}
      />
    );
    expect(await screen.findByTestId("artifact-widget-risk_matrix")).toBeInTheDocument();
    expect(screen.queryByTestId("artifact-field-probability")).not.toBeInTheDocument();
  });

  it("collapses an all-expert section by default", async () => {
    mockDefinition([
      spec({ name: "title", section: "general" }),
      spec({ name: "deep", section: "advanced", audience: "expert" }),
    ]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T", deep: "D" }}
        onSave={vi.fn()}
      />
    );
    await screen.findByTestId("artifact-field-title");
    expect(screen.queryByTestId("artifact-field-deep")).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId("artifact-section-toggle-advanced"));
    expect(screen.getByTestId("artifact-field-deep")).toBeInTheDocument();
  });

  it("routes extended values through custom_fields on save", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    mockDefinition([
      spec({ name: "title" }),
      spec({ name: "sap_id", kind: "extended", section: "custom" }),
    ]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T", custom_fields: { sap_id: "S-1" } }}
        onSave={onSave}
      />
    );
    await userEvent.clear(await screen.findByTestId("artifact-field-sap_id"));
    await userEvent.type(screen.getByTestId("artifact-field-sap_id"), "S-2");
    await userEvent.click(screen.getByTestId("artifact-form-save"));
    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith(
        expect.objectContaining({ custom_fields: { sap_id: "S-2" } })
      )
    );
  });

  it("reports dirty state to the parent and clears it after a save", async () => {
    const onDirtyChange = vi.fn();
    mockDefinition([spec({ name: "title" })]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn().mockResolvedValue(undefined)}
        onDirtyChange={onDirtyChange}
      />
    );
    await userEvent.type(await screen.findByTestId("artifact-field-title"), "X");
    await waitFor(() => expect(onDirtyChange).toHaveBeenCalledWith(true));
    await userEvent.click(screen.getByTestId("artifact-form-save"));
    await waitFor(() => expect(onDirtyChange).toHaveBeenLastCalledWith(false));
  });

  it("attaches a server field error to its own field", async () => {
    mockDefinition([spec({ name: "title" })]);
    const onSave = vi.fn().mockRejectedValue(
      Object.assign(new Error("x"), {
        response: { data: { error: { message: "title: is required" } } },
      })
    );
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={onSave}
      />
    );
    await userEvent.click(await screen.findByTestId("artifact-form-save"));
    await waitFor(() =>
      expect(screen.getByTestId("artifact-field-title")).toHaveAttribute(
        "aria-invalid",
        "true"
      )
    );
  });

  it("offers delete behind ConfirmDialog only when onDelete is supplied", async () => {
    mockDefinition([spec({ name: "title" })]);
    const onDelete = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
      />
    );
    await screen.findByTestId("artifact-field-title");
    expect(screen.queryByTestId("artifact-form-delete")).not.toBeInTheDocument();

    rerender(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
        onDelete={onDelete}
      />
    );
    await userEvent.click(screen.getByTestId("artifact-form-delete"));
    await userEvent.click(screen.getByTestId("artifact-form-delete-confirm"));
    await waitFor(() => expect(onDelete).toHaveBeenCalled());
  });

  it("disables every control in read mode", async () => {
    mockDefinition([spec({ name: "title" })]);
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
        mode="read"
      />
    );
    expect(await screen.findByTestId("artifact-field-title")).toBeDisabled();
    expect(screen.queryByTestId("artifact-form-save")).not.toBeInTheDocument();
  });

  it("shows an error banner when the definition cannot be loaded", async () => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockRejectedValue(new Error("boom"));
    render(
      <ArtifactForm
        itemType="Risk"
        artifactId="r-1"
        initialValues={{ title: "T" }}
        onSave={vi.fn()}
      />
    );
    expect(await screen.findByTestId("artifact-form-load-error")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npx vitest run src/test/ArtifactForm.test.tsx`
Expected: FAIL — cannot resolve `../components/shared/ArtifactForm`.

- [ ] **Step 3: Write the definition hook and the error parser**

Create `frontend/src/components/shared/ArtifactForm/useArtifactDefinition.ts`:

```ts
import { useEffect, useState } from "react";

import {
  attributeDefinitionsApi,
  type ResolvedAttributeDefinition,
} from "../../../api/attribute-definitions";
import { extractErrorMessage } from "../../../api/client";
import { useWorkspace } from "../../../context/WorkspaceContext";

export interface UseArtifactDefinitionResult {
  definition: ResolvedAttributeDefinition | null;
  loading: boolean;
  error: string | null;
}

/**
 * Loads the resolved attribute definition for `(activeWorkspace, itemType)`.
 *
 * The backend already caches the resolution per workspace, so this hook does no
 * client-side memoisation of its own — one indexed read per mounted form is
 * cheaper than a cache that has to be invalidated when an admin edits the
 * definition in another tab.
 */
export function useArtifactDefinition(itemType: string): UseArtifactDefinitionResult {
  const { activeWorkspace } = useWorkspace();
  const [definition, setDefinition] = useState<ResolvedAttributeDefinition | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const workspaceId = activeWorkspace?.id;
    if (!workspaceId) {
      setLoading(false);
      return undefined;
    }
    setLoading(true);
    setError(null);
    attributeDefinitionsApi
      .getWorkspace(workspaceId, itemType)
      .then((resolved) => {
        if (cancelled) return;
        setDefinition(resolved);
        setLoading(false);
      })
      .catch((exc: unknown) => {
        if (cancelled) return;
        setDefinition(null);
        setError(extractErrorMessage(exc));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeWorkspace?.id, itemType]);

  return { definition, loading, error };
}
```

Create `frontend/src/components/shared/ArtifactForm/field-errors.ts`:

```ts
/**
 * Reverses the backend's joined validation message.
 *
 * `WorkflowTransitionsMixin._validate_attribute_definition` renders
 * `FieldValidationError.errors` as
 * `"<name>: <msg>, <msg>; <name>: <msg>"`. That exact format is the contract
 * this parser depends on.
 *
 * A message that does not match falls through as `{}` on purpose: the caller
 * then shows it in the form-level banner. A changed envelope therefore degrades
 * to "shown once at the top" instead of "silently swallowed".
 */
export function parseFieldErrors(message: string): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const chunk of message.split("; ")) {
    const separator = chunk.indexOf(": ");
    if (separator <= 0) continue;
    const name = chunk.slice(0, separator).trim();
    // A name is an attribute identifier, never a sentence.
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) continue;
    const messages = chunk
      .slice(separator + 2)
      .split(", ")
      .map((m) => m.trim())
      .filter(Boolean);
    if (messages.length) out[name] = messages;
  }
  return out;
}
```

- [ ] **Step 4: Write the renderer**

Create `frontend/src/components/shared/ArtifactForm/ArtifactForm.tsx`:

```tsx
/**
 * Definition-driven artifact form (spec section 6).
 *
 * Replaces the seven hand-written forms. Everything it draws comes from the
 * resolved attribute definition: sections and their order, fields and their
 * order, labels, help text, requiredness, enum options, widgets and the
 * default expand density (`audience`).
 *
 * Parity policy (spec section 6.3): dirty warning, delete-in-form, status as
 * badge + transition buttons and definition-driven visibility are available for
 * EVERY type here — the migration unifies upward onto the best behaviour any of
 * the seven forms had, it never cuts one.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, ChevronDown, ChevronRight } from "lucide-react";

import type {
  AttributeAudience,
  AttributeSpec,
} from "../../../api/attribute-definitions";
import { extractErrorMessage } from "../../../api/client";
import type { WorkflowArtifactType } from "../../../api/workflow-transitions";
import { useFormDirty } from "../../../hooks/use-form-dirty";
import { ConfirmDialog } from "../ConfirmDialog";
import { WorkflowStatusEditor } from "../../WorkflowStatusEditor";
import styles from "./ArtifactForm.module.css";
import { parseFieldErrors } from "./field-errors";
import {
  BooleanToggle,
  DateField,
  EnumSelect,
  MultiEnum,
  NumberField,
  ReferencePicker,
  TextArea,
  TextField,
  UserPicker,
} from "./fields";
import { useArtifactDefinition } from "./useArtifactDefinition";
import { WIDGET_REGISTRY } from "./widget-registry";

export interface ArtifactFormValues {
  [name: string]: unknown;
  custom_fields?: Record<string, unknown>;
}

export interface ArtifactFormProps {
  /** Attribute-definition item type, e.g. "Risk". */
  itemType: string;
  /** `null` = create mode: no delete affordance, all required fields demanded. */
  artifactId: string | null;
  initialValues: ArtifactFormValues;
  onSave: (values: ArtifactFormValues) => Promise<void>;
  onDelete?: () => Promise<void>;
  onDirtyChange?: (isDirty: boolean) => void;
  /** `"read"` disables every control (Rollenbasierte-Sichten spec). */
  mode?: "edit" | "read";
  /** Enables the workflow status editor for `editable: "workflow"` attributes. */
  workflowArtifactType?: WorkflowArtifactType;
}

export interface FormSection {
  name: string;
  audience: AttributeAudience;
  attributes: AttributeSpec[];
}

/** Group attributes into sections, preserving the definition's order. */
export function groupIntoSections(attributes: AttributeSpec[]): FormSection[] {
  const order: string[] = [];
  const bySection = new Map<string, AttributeSpec[]>();
  for (const attribute of attributes) {
    if (!bySection.has(attribute.section)) {
      bySection.set(attribute.section, []);
      order.push(attribute.section);
    }
    bySection.get(attribute.section)!.push(attribute);
  }
  return order.map((name) => {
    const sectionAttributes = bySection.get(name)!;
    return {
      name,
      // A section is "expert" only when EVERY attribute in it is — one basic
      // attribute would otherwise be hidden behind a collapsed header.
      audience: sectionAttributes.every((a) => a.audience === "expert")
        ? "expert"
        : "basic",
      attributes: sectionAttributes,
    };
  });
}

function readValue(values: ArtifactFormValues, attribute: AttributeSpec): unknown {
  return attribute.kind === "extended"
    ? (values.custom_fields ?? {})[attribute.name]
    : values[attribute.name];
}

function writeValue(
  values: ArtifactFormValues,
  attribute: AttributeSpec,
  next: unknown
): ArtifactFormValues {
  if (attribute.kind === "extended") {
    return {
      ...values,
      custom_fields: { ...(values.custom_fields ?? {}), [attribute.name]: next },
    };
  }
  return { ...values, [attribute.name]: next };
}

export function ArtifactForm({
  itemType,
  artifactId,
  initialValues,
  onSave,
  onDelete,
  onDirtyChange,
  mode = "edit",
  workflowArtifactType,
}: ArtifactFormProps): JSX.Element {
  const { t } = useTranslation();
  const { definition, loading, error: loadError } = useArtifactDefinition(itemType);
  const [values, setValues] = useState<ArtifactFormValues>(initialValues);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const { isDirty, markClean } = useFormDirty(values, initialValues);
  const isReadOnly = mode === "read";

  useEffect(() => {
    setValues(initialValues);
    markClean(initialValues);
  }, [artifactId, initialValues, markClean]);

  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);

  const visible = useMemo(
    () => (definition?.attributes ?? []).filter((a) => a.visible),
    [definition]
  );

  // Rule 2: a field a widget draws is not rendered on its own.
  const widgetOwned = useMemo(() => {
    const owned = new Set<string>();
    for (const attribute of visible) {
      if (attribute.type === "widget") {
        attribute.fields.forEach((name) => owned.add(name));
      }
    }
    return owned;
  }, [visible]);

  const sections = useMemo(
    () => groupIntoSections(visible.filter((a) => !widgetOwned.has(a.name))),
    [visible, widgetOwned]
  );

  const isSectionOpen = useCallback(
    (section: FormSection): boolean => {
      if (section.name in expanded) return expanded[section.name];
      // Rule 5: an error anywhere in the section forces it open so the message
      // is reachable without hunting.
      if (section.attributes.some((a) => fieldErrors[a.name]?.length)) return true;
      return section.audience !== "expert";
    },
    [expanded, fieldErrors]
  );

  const update = useCallback((attribute: AttributeSpec, next: unknown): void => {
    setValues((current) => writeValue(current, attribute, next));
  }, []);

  const handleSave = useCallback(async (): Promise<void> => {
    setSaving(true);
    setFormError(null);
    setFieldErrors({});
    try {
      await onSave(values);
      markClean(values);
    } catch (exc: unknown) {
      const message = extractErrorMessage(exc);
      const parsed = parseFieldErrors(message);
      setFieldErrors(parsed);
      if (!Object.keys(parsed).length) setFormError(message);
    } finally {
      setSaving(false);
    }
  }, [markClean, onSave, values]);

  const handleDelete = useCallback(async (): Promise<void> => {
    if (!onDelete) return;
    try {
      await onDelete();
      setConfirmDelete(false);
    } catch (exc: unknown) {
      setConfirmDelete(false);
      setFormError(extractErrorMessage(exc));
    }
  }, [onDelete]);

  if (loading) {
    return <div data-testid="artifact-form-loading" aria-busy="true" />;
  }
  if (loadError || !definition) {
    return (
      <div className={styles.errors} role="alert" data-testid="artifact-form-load-error">
        <AlertCircle aria-hidden="true" size={16} />
        {loadError ?? t("artifactForm.saveFailed")}
      </div>
    );
  }

  return (
    <form
      className={styles.form}
      data-testid="artifact-form"
      onSubmit={(event) => {
        event.preventDefault();
        void handleSave();
      }}
    >
      {formError ? (
        <div className={styles.errors} role="alert" data-testid="artifact-form-error">
          {formError}
        </div>
      ) : null}

      {sections.map((section) => {
        const open = isSectionOpen(section);
        return (
          <section key={section.name} className={styles.section}>
            <button
              type="button"
              className={styles.sectionHeader}
              data-testid={`artifact-section-toggle-${section.name}`}
              aria-expanded={open}
              aria-label={t(
                open ? "artifactForm.collapseSection" : "artifactForm.expandSection",
                { section: section.name }
              )}
              onClick={() =>
                setExpanded((current) => ({ ...current, [section.name]: !open }))
              }
            >
              <span>{t(`sections.${section.name}`, { defaultValue: section.name })}</span>
              {open ? (
                <ChevronDown aria-hidden="true" size={16} />
              ) : (
                <ChevronRight aria-hidden="true" size={16} />
              )}
            </button>

            {open ? (
              <div className={styles.sectionBody}>
                {section.attributes.map((attribute) =>
                  renderAttribute({
                    attribute,
                    values,
                    fieldErrors,
                    disabled: isReadOnly || attribute.editable === false || saving,
                    artifactId,
                    workflowArtifactType,
                    update,
                  })
                )}
              </div>
            ) : null}
          </section>
        );
      })}

      {!isReadOnly ? (
        <div className={styles.actions}>
          {onDelete ? (
            <button
              type="button"
              data-testid="artifact-form-delete"
              disabled={saving}
              onClick={() => setConfirmDelete(true)}
            >
              {t("common.delete")}
            </button>
          ) : null}
          <button type="submit" data-testid="artifact-form-save" disabled={saving}>
            {t("common.save")}
          </button>
        </div>
      ) : null}

      {confirmDelete ? (
        <ConfirmDialog
          message={t("artifactForm.deleteConfirm")}
          confirmTestId="artifact-form-delete-confirm"
          cancelTestId="artifact-form-delete-cancel"
          onConfirm={() => void handleDelete()}
          onCancel={() => setConfirmDelete(false)}
        />
      ) : null}
    </form>
  );
}

interface RenderArgs {
  attribute: AttributeSpec;
  values: ArtifactFormValues;
  fieldErrors: Record<string, string[]>;
  disabled: boolean;
  artifactId: string | null;
  workflowArtifactType?: WorkflowArtifactType;
  update: (attribute: AttributeSpec, next: unknown) => void;
}

function renderAttribute({
  attribute,
  values,
  fieldErrors,
  disabled,
  artifactId,
  workflowArtifactType,
  update,
}: RenderArgs): JSX.Element | null {
  const testId = `artifact-field-${attribute.name}`;
  const errors = fieldErrors[attribute.name];

  // Rule 3: a workflow-owned attribute is never an editable control.
  if (attribute.editable === "workflow") {
    if (!workflowArtifactType || !artifactId) return null;
    return (
      <WorkflowStatusEditor
        key={attribute.name}
        artifactType={workflowArtifactType}
        artifactId={artifactId}
        disabled={disabled}
      />
    );
  }

  if (attribute.type === "widget") {
    const Widget = attribute.widget_key ? WIDGET_REGISTRY[attribute.widget_key] : undefined;
    if (!Widget) return null;
    const boundValues: Record<string, unknown> = {};
    const boundErrors: Record<string, string[]> = {};
    for (const name of attribute.fields) {
      boundValues[name] = values[name];
      if (fieldErrors[name]) boundErrors[name] = fieldErrors[name];
    }
    return (
      <Widget
        key={attribute.name}
        attribute={attribute}
        values={boundValues}
        onChange={(fieldName, next) =>
          update({ ...attribute, name: fieldName, kind: "core" }, next)
        }
        disabled={disabled}
        errors={boundErrors}
        testId={`artifact-widget-${attribute.name}`}
      />
    );
  }

  const shared = {
    key: attribute.name,
    attribute,
    disabled,
    errors,
    testId,
  } as const;
  const value = readValue(values, attribute);
  const onChange = (next: unknown): void => update(attribute, next);

  switch (attribute.type) {
    case "textarea":
      return <TextArea {...shared} value={value as string | null} onChange={onChange} />;
    case "number":
      return <NumberField {...shared} value={value as number | null} onChange={onChange} />;
    case "boolean":
      return <BooleanToggle {...shared} value={value as boolean | null} onChange={onChange} />;
    case "enum":
      return <EnumSelect {...shared} value={value as string | null} onChange={onChange} />;
    case "multi-enum":
      return <MultiEnum {...shared} value={value as string[] | null} onChange={onChange} />;
    case "date":
      return <DateField {...shared} value={value as string | null} onChange={onChange} />;
    case "reference":
      return <ReferencePicker {...shared} value={value as string | null} onChange={onChange} />;
    case "user":
      return <UserPicker {...shared} value={value as string | null} onChange={onChange} />;
    default:
      return <TextField {...shared} value={value as string | null} onChange={onChange} />;
  }
}
```

Create `frontend/src/components/shared/ArtifactForm/index.ts`:

```ts
export { ArtifactForm, groupIntoSections } from "./ArtifactForm";
export type {
  ArtifactFormProps,
  ArtifactFormValues,
  FormSection,
} from "./ArtifactForm";
export { parseFieldErrors } from "./field-errors";
export { useArtifactDefinition } from "./useArtifactDefinition";
export { WIDGET_REGISTRY } from "./widget-registry";
export type { WidgetProps } from "./widget-registry";
```

Verify `ConfirmDialog` (`frontend/src/components/shared/ConfirmDialog.tsx`) accepts `confirmTestId` / `cancelTestId`; if it does not, add both as optional props forwarded to the two buttons in this same commit — hand-rolling a second confirm dialog is explicitly forbidden by the existing single-delete-seam convention.

- [ ] **Step 5: Add the section i18n keys**

Add to both locale files a nested `sections` object with the four conventional names: `general` / `classification` / `change_control` / `custom` → de `"Allgemein"` / `"Klassifikation"` / `"Änderungskontrolle"` / `"Eigene Felder"`, en `"General"` / `"Classification"` / `"Change control"` / `"Custom fields"`. A section name with no key falls back to the raw name through `defaultValue`, which is what makes free-text section names work.

- [ ] **Step 6: Run test to verify it passes**

Run: `docker compose exec frontend npx vitest run src/test/ArtifactForm.test.tsx --testTimeout=30000`
Expected: PASS (16 tests)

- [ ] **Step 7: Verify the ratchets**

Run: `docker compose exec frontend npx vitest run src/test/ui-ratchet.test.ts src/test/design-tokens.test.ts src/test/i18n-parity.test.ts --testTimeout=30000`
Expected: PASS with `STYLE_BRACE_BASELINE` unchanged.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/shared/ArtifactForm frontend/src/components/shared/ConfirmDialog.tsx frontend/src/i18n/locales frontend/src/test/ArtifactForm.test.tsx
git commit -m "feat(attribute-definitions): add definition-driven ArtifactForm renderer"
```

---

### Task 19: Rollout wave 1a — Risk

Spec section 6.2: smallest risk first. `RiskForm.tsx` (543 lines) is deleted, not kept alongside.

**Files:**
- Create: `frontend/src/components/RiskEditors/RiskArtifactForm.tsx`
- Modify: `frontend/src/components/RiskEditors/RiskEditors.tsx:9,19,169`
- Delete: `frontend/src/components/RiskEditors/RiskForm.tsx`
- Modify: `frontend/src/test/ui-ratchet.test.ts:335` (`STYLE_BRACE_BASELINE`)
- Test: `frontend/src/test/RiskArtifactForm.test.tsx`

**Interfaces:**
- Consumes: `ArtifactForm`, `ArtifactFormValues` (Task 18); `risksApi` from `../../api/risks`; `Risk` from `../../types`.
- Produces:
  - `riskToFormValues(risk: Risk): ArtifactFormValues`
  - `formValuesToRiskPatch(values: ArtifactFormValues): Record<string, unknown>`
  - `function RiskArtifactForm(props: { risk: Risk; onSaved: () => void; onDeleted: () => void; onDirtyChange?: (isDirty: boolean) => void }): JSX.Element`

`CATEGORY_OPTIONS` currently lives in `RiskForm.tsx` and is imported by `RiskEditors.tsx:19`. It moves into `RiskArtifactForm.tsx` unchanged and keeps its named export, so the list-filter dropdown that consumes it is untouched.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/RiskArtifactForm.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { risksApi } from "../api/risks";
import {
  RiskArtifactForm,
  formValuesToRiskPatch,
  riskToFormValues,
} from "../components/RiskEditors/RiskArtifactForm";
import { attributeDefinitionsApi } from "../api/attribute-definitions";

vi.mock("../api/risks", () => ({
  risksApi: { update: vi.fn(), delete: vi.fn() },
}));
vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: { getWorkspace: vi.fn() },
}));
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", preset: "standard" } }),
}));

const RISK = {
  id: "r-1",
  workspace_id: "ws-1",
  title: "Outage",
  description: "d",
  category: "technical",
  probability: "high",
  impact: "high",
  detection: 4,
  mitigation_strategy: "m",
  custom_fields: { sap_id: "S-1" },
  version: 3,
} as never;

describe("RiskArtifactForm", () => {
  beforeEach(() => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "Risk",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [
        {
          name: "title", kind: "core", type: "text", widget_key: null, fields: [],
          options: [], required: true, visible: true, locked: false, editable: true,
          section: "general", order: 1, label: { de: "Titel", en: "Title" },
          help_text: { de: "", en: "" }, default: null, validation: {},
          ai_elicit: true, export: true, audience: "basic",
        },
      ],
    });
    vi.mocked(risksApi.update).mockReset();
    vi.mocked(risksApi.delete).mockReset();
  });

  it("maps a Risk onto form values, nesting extended values", () => {
    const values = riskToFormValues(RISK);
    expect(values.title).toBe("Outage");
    expect(values.detection).toBe(4);
    expect(values.custom_fields).toEqual({ sap_id: "S-1" });
  });

  it("does not send read-only identity fields in the patch", () => {
    const patch = formValuesToRiskPatch(riskToFormValues(RISK));
    expect(patch).not.toHaveProperty("id");
    expect(patch).not.toHaveProperty("workspace_id");
    expect(patch).not.toHaveProperty("version");
    expect(patch.title).toBe("Outage");
  });

  it("saves through risksApi.update and reports success upward", async () => {
    vi.mocked(risksApi.update).mockResolvedValue(RISK);
    const onSaved = vi.fn();
    render(
      <RiskArtifactForm risk={RISK} onSaved={onSaved} onDeleted={vi.fn()} />
    );
    await userEvent.type(await screen.findByTestId("artifact-field-title"), "!");
    await userEvent.click(screen.getByTestId("artifact-form-save"));
    await waitFor(() => expect(risksApi.update).toHaveBeenCalled());
    expect(onSaved).toHaveBeenCalled();
  });

  it("deletes through the shared confirm dialog", async () => {
    vi.mocked(risksApi.delete).mockResolvedValue(undefined as never);
    const onDeleted = vi.fn();
    render(
      <RiskArtifactForm risk={RISK} onSaved={vi.fn()} onDeleted={onDeleted} />
    );
    await userEvent.click(await screen.findByTestId("artifact-form-delete"));
    await userEvent.click(screen.getByTestId("artifact-form-delete-confirm"));
    await waitFor(() => expect(risksApi.delete).toHaveBeenCalledWith("r-1"));
    expect(onDeleted).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npx vitest run src/test/RiskArtifactForm.test.tsx`
Expected: FAIL — cannot resolve `../components/RiskEditors/RiskArtifactForm`.

- [ ] **Step 3: Write the adapter**

Create `frontend/src/components/RiskEditors/RiskArtifactForm.tsx`:

```tsx
/**
 * Risk editor — first form migrated onto the definition-driven renderer
 * (spec section 6.2, smallest risk first).
 *
 * This file holds only the Risk-specific glue: which API to call and how to map
 * between the REST shape and the form's value bag. Layout, sections, validation
 * display, dirty warning and delete all live in ArtifactForm.
 */

import { useMemo } from "react";

import { risksApi } from "../../api/risks";
import type { Risk } from "../../types";
import { ArtifactForm, type ArtifactFormValues } from "../shared/ArtifactForm";

/** Kept here (was in the deleted RiskForm) — RiskEditors imports it for its filter. */
export const CATEGORY_OPTIONS = [
  "technical",
  "operational",
  "organizational",
  "business",
] as const;

/** Server-owned fields the form must never send back. */
const READ_ONLY_KEYS = new Set([
  "id",
  "workspace_id",
  "tenant_id",
  "version",
  "created_at",
  "modified_at",
  "updated_at",
  "risk_score",
  "severity",
  "artifact",
  "artifact_id",
  "status",
]);

export function riskToFormValues(risk: Risk): ArtifactFormValues {
  const { custom_fields: customFields, ...rest } = risk as unknown as Record<string, unknown>;
  return {
    ...rest,
    custom_fields: (customFields as Record<string, unknown>) ?? {},
  };
}

export function formValuesToRiskPatch(
  values: ArtifactFormValues
): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    if (READ_ONLY_KEYS.has(key)) continue;
    patch[key] = value;
  }
  return patch;
}

export interface RiskArtifactFormProps {
  risk: Risk;
  onSaved: () => void;
  onDeleted: () => void;
  onDirtyChange?: (isDirty: boolean) => void;
}

export function RiskArtifactForm({
  risk,
  onSaved,
  onDeleted,
  onDirtyChange,
}: RiskArtifactFormProps): JSX.Element {
  const initialValues = useMemo(() => riskToFormValues(risk), [risk]);

  return (
    <ArtifactForm
      itemType="Risk"
      artifactId={risk.id}
      initialValues={initialValues}
      workflowArtifactType="Risk"
      onDirtyChange={onDirtyChange}
      onSave={async (values) => {
        await risksApi.update(risk.id, formValuesToRiskPatch(values));
        onSaved();
      }}
      onDelete={async () => {
        await risksApi.delete(risk.id);
        onDeleted();
      }}
    />
  );
}
```

- [ ] **Step 4: Swap the parent and delete the old form**

In `frontend/src/components/RiskEditors/RiskEditors.tsx`:
- line 9: `import { RiskForm } from './RiskForm';` → `import { RiskArtifactForm } from './RiskArtifactForm';`
- line 19: `import { CATEGORY_OPTIONS } from './RiskForm';` → `import { CATEGORY_OPTIONS } from './RiskArtifactForm';`
- line 169: `<RiskForm risk={item} onSaved={handleSaved} onDeleted={handleDeleted} />` → `<RiskArtifactForm risk={item} onSaved={handleSaved} onDeleted={handleDeleted} />`

Then:

```bash
git rm frontend/src/components/RiskEditors/RiskForm.tsx
```

- [ ] **Step 5: Check the E2E specs for moved test ids**

Run: `grep -rn "risk-form\|risk-save\|risk-delete" e2e/`
Expected: every hit is a selector the deleted form owned. Update each to the renderer's stable ids (`artifact-form`, `artifact-field-<name>`, `artifact-form-save`, `artifact-form-delete`, `artifact-form-delete-confirm`) in this same commit. A moved testid keeps vitest green while silently breaking Playwright, so this step is not optional.

- [ ] **Step 6: Re-measure and lower the inline-style baseline**

Run: `docker compose exec frontend npx vitest run src/test/ui-ratchet.test.ts --testTimeout=30000`
Expected: FAIL on the monotonic assertion, reporting the new lower count. Set `STYLE_BRACE_BASELINE` in `frontend/src/test/ui-ratchet.test.ts:335` to exactly that number and re-run — never raise it.

- [ ] **Step 7: Run the tests**

Run: `docker compose exec frontend npx vitest run src/test/RiskArtifactForm.test.tsx src/test/RiskEditors.test.tsx src/test/ui-ratchet.test.ts --testTimeout=30000`
Expected: PASS. `RiskEditors.test.tsx` may reference the deleted component; update its imports and selectors rather than restoring the file.

- [ ] **Step 8: Verify in the browser**

Run: `docker compose restart frontend` (Vite has no working HMR on Windows — without the restart the browser tests stale code), then open `/risks`, select a risk and confirm: fields render from the definition, the risk-matrix widget shows a live RPN, Save persists, the dirty warning appears on navigation with unsaved edits, and Delete asks for confirmation.

- [ ] **Step 9: Commit**

```bash
git add -A frontend/src/components/RiskEditors frontend/src/test e2e
git commit -m "refactor(attribute-definitions): migrate Risk form onto ArtifactForm"
```

---

### Task 20: Rollout wave 1b — Issue

**Files:**
- Create: `frontend/src/components/IssueEditors/IssueArtifactForm.tsx`
- Modify: `frontend/src/components/IssueEditors/IssueEditors.tsx` (import + render site)
- Delete: `frontend/src/components/IssueEditors/IssueForm.tsx`
- Modify: `frontend/src/test/ui-ratchet.test.ts:335`
- Test: `frontend/src/test/IssueArtifactForm.test.tsx`

**Interfaces:**
- Consumes: `ArtifactForm`, `ArtifactFormValues` (Task 18); `issuesApi` from `../../api/issues`; `Issue` from `../../types`.
- Produces:
  - `issueToFormValues(issue: Issue): ArtifactFormValues`
  - `formValuesToIssuePatch(values: ArtifactFormValues): Record<string, unknown>`
  - `function IssueArtifactForm(props: { issue: Issue; onSaved: () => void; onDeleted: () => void; onDirtyChange?: (isDirty: boolean) => void }): JSX.Element`

Parity gain (spec section 6.3): `IssueForm` had no dirty warning and no definition-driven visibility. Both arrive with the renderer, unconditionally.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/IssueArtifactForm.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { issuesApi } from "../api/issues";
import { attributeDefinitionsApi } from "../api/attribute-definitions";
import {
  IssueArtifactForm,
  formValuesToIssuePatch,
  issueToFormValues,
} from "../components/IssueEditors/IssueArtifactForm";

vi.mock("../api/issues", () => ({
  issuesApi: { update: vi.fn(), delete: vi.fn() },
}));
vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: { getWorkspace: vi.fn() },
}));
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", preset: "standard" } }),
}));

const ISSUE = {
  id: "i-1",
  workspace_id: "ws-1",
  title: "Broken",
  description: "d",
  assignee_id: "u-1",
  due_date: "2026-10-01",
  custom_fields: {},
  version: 2,
} as never;

describe("IssueArtifactForm", () => {
  beforeEach(() => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "Issue",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [
        {
          name: "title", kind: "core", type: "text", widget_key: null, fields: [],
          options: [], required: true, visible: true, locked: false, editable: true,
          section: "general", order: 1, label: { de: "Titel", en: "Title" },
          help_text: { de: "", en: "" }, default: null, validation: {},
          ai_elicit: true, export: true, audience: "basic",
        },
      ],
    });
    vi.mocked(issuesApi.update).mockReset();
    vi.mocked(issuesApi.delete).mockReset();
  });

  it("maps an Issue onto form values", () => {
    const values = issueToFormValues(ISSUE);
    expect(values.title).toBe("Broken");
    expect(values.due_date).toBe("2026-10-01");
    expect(values.custom_fields).toEqual({});
  });

  it("strips server-owned fields from the patch", () => {
    const patch = formValuesToIssuePatch(issueToFormValues(ISSUE));
    expect(patch).not.toHaveProperty("id");
    expect(patch).not.toHaveProperty("version");
    expect(patch.assignee_id).toBe("u-1");
  });

  it("reports dirty state so the parent can warn before navigating away", async () => {
    const onDirtyChange = vi.fn();
    render(
      <IssueArtifactForm
        issue={ISSUE}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
        onDirtyChange={onDirtyChange}
      />
    );
    await userEvent.type(await screen.findByTestId("artifact-field-title"), "!");
    await waitFor(() => expect(onDirtyChange).toHaveBeenCalledWith(true));
  });

  it("saves through issuesApi.update", async () => {
    vi.mocked(issuesApi.update).mockResolvedValue(ISSUE);
    const onSaved = vi.fn();
    render(
      <IssueArtifactForm issue={ISSUE} onSaved={onSaved} onDeleted={vi.fn()} />
    );
    await userEvent.click(await screen.findByTestId("artifact-form-save"));
    await waitFor(() => expect(issuesApi.update).toHaveBeenCalled());
    expect(onSaved).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npx vitest run src/test/IssueArtifactForm.test.tsx`
Expected: FAIL — cannot resolve `../components/IssueEditors/IssueArtifactForm`.

- [ ] **Step 3: Write the adapter**

Create `frontend/src/components/IssueEditors/IssueArtifactForm.tsx`:

```tsx
/**
 * Issue editor on the definition-driven renderer (spec section 6.2, wave 1).
 *
 * Parity gain over the deleted IssueForm: dirty warning and definition-driven
 * field visibility, neither of which that form had (spec section 6.3 — the
 * migration unifies upward).
 */

import { useMemo } from "react";

import { issuesApi } from "../../api/issues";
import type { Issue } from "../../types";
import { ArtifactForm, type ArtifactFormValues } from "../shared/ArtifactForm";

const READ_ONLY_KEYS = new Set([
  "id",
  "workspace_id",
  "tenant_id",
  "version",
  "created_at",
  "modified_at",
  "updated_at",
  "artifact",
  "artifact_id",
  "status",
]);

export function issueToFormValues(issue: Issue): ArtifactFormValues {
  const { custom_fields: customFields, ...rest } = issue as unknown as Record<string, unknown>;
  return {
    ...rest,
    custom_fields: (customFields as Record<string, unknown>) ?? {},
  };
}

export function formValuesToIssuePatch(
  values: ArtifactFormValues
): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    if (READ_ONLY_KEYS.has(key)) continue;
    patch[key] = value;
  }
  return patch;
}

export interface IssueArtifactFormProps {
  issue: Issue;
  onSaved: () => void;
  onDeleted: () => void;
  onDirtyChange?: (isDirty: boolean) => void;
}

export function IssueArtifactForm({
  issue,
  onSaved,
  onDeleted,
  onDirtyChange,
}: IssueArtifactFormProps): JSX.Element {
  const initialValues = useMemo(() => issueToFormValues(issue), [issue]);

  return (
    <ArtifactForm
      itemType="Issue"
      artifactId={issue.id}
      initialValues={initialValues}
      workflowArtifactType="Issue"
      onDirtyChange={onDirtyChange}
      onSave={async (values) => {
        await issuesApi.update(issue.id, formValuesToIssuePatch(values));
        onSaved();
      }}
      onDelete={async () => {
        await issuesApi.delete(issue.id);
        onDeleted();
      }}
    />
  );
}
```

- [ ] **Step 4: Swap the parent and delete the old form**

In `frontend/src/components/IssueEditors/IssueEditors.tsx` replace the `IssueForm` import and its single render site with `IssueArtifactForm`, passing the same `issue` / `onSaved` / `onDeleted` props. Then:

```bash
git rm frontend/src/components/IssueEditors/IssueForm.tsx
```

- [ ] **Step 5: Check the E2E specs for moved test ids**

Run: `grep -rn "issue-form\|issue-save\|issue-delete" e2e/`
Expected: update every hit to the renderer's stable ids in this same commit.

- [ ] **Step 6: Re-measure and lower the inline-style baseline**

Run: `docker compose exec frontend npx vitest run src/test/ui-ratchet.test.ts --testTimeout=30000`
Expected: FAIL on the monotonic assertion; set `STYLE_BRACE_BASELINE` to the reported count.

- [ ] **Step 7: Run the tests**

Run: `docker compose exec frontend npx vitest run src/test/IssueArtifactForm.test.tsx src/test/IssueEditors.test.tsx src/test/ui-ratchet.test.ts --testTimeout=30000`
Expected: PASS

- [ ] **Step 8: Verify in the browser**

Run `docker compose restart frontend`, open `/issues`, select an issue and confirm fields, save, dirty warning and delete.

- [ ] **Step 9: Commit**

```bash
git add -A frontend/src/components/IssueEditors frontend/src/test e2e
git commit -m "refactor(attribute-definitions): migrate Issue form onto ArtifactForm"
```

---

### Task 21: Rollout wave 2a — ADR

First form whose special case needs a widget: the three stacked markdown editors become one `markdown_tab_group`.

**Files:**
- Create: `frontend/src/components/AdrEditors/AdrArtifactForm.tsx`
- Modify: `frontend/src/components/AdrEditors/AdrEditors.tsx` (import + render site)
- Delete: `frontend/src/components/AdrEditors/AdrForm.tsx`
- Modify: `frontend/src/test/ui-ratchet.test.ts:335`
- Test: `frontend/src/test/AdrArtifactForm.test.tsx`

**Interfaces:**
- Consumes: `ArtifactForm`, `ArtifactFormValues` (Task 18); `MarkdownTabGroup` via `WIDGET_REGISTRY` (Task 17); `adrsApi` from `../../api/adrs`; `Adr` from `../../types`.
- Produces:
  - `adrToFormValues(adr: Adr): ArtifactFormValues`
  - `formValuesToAdrPatch(values: ArtifactFormValues): Record<string, unknown>`
  - `function AdrArtifactForm(props: { adr: Adr; onSaved: () => void; onDeleted: () => void; onDirtyChange?: (isDirty: boolean) => void }): JSX.Element`

`Adr.decision` is a fourth markdown column that the deleted form never bound to the tab group — it stays an ordinary `textarea` attribute, so no content becomes unreachable.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/AdrArtifactForm.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { adrsApi } from "../api/adrs";
import { attributeDefinitionsApi } from "../api/attribute-definitions";
import {
  AdrArtifactForm,
  adrToFormValues,
  formValuesToAdrPatch,
} from "../components/AdrEditors/AdrArtifactForm";

vi.mock("../api/adrs", () => ({ adrsApi: { update: vi.fn(), delete: vi.fn() } }));
vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: { getWorkspace: vi.fn() },
}));
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", preset: "standard" } }),
}));

const ADR = {
  id: "a-1",
  workspace_id: "ws-1",
  title: "Use Postgres",
  description: "d",
  context: "c",
  consequences: "q",
  decision: "we use it",
  custom_fields: {},
  version: 1,
} as never;

function attr(over: Record<string, unknown>) {
  return {
    name: "title", kind: "core", type: "text", widget_key: null, fields: [],
    options: [], required: false, visible: true, locked: false, editable: true,
    section: "general", order: 1, label: { de: "", en: "" },
    help_text: { de: "", en: "" }, default: null, validation: {},
    ai_elicit: false, export: true, audience: "basic", ...over,
  };
}

describe("AdrArtifactForm", () => {
  beforeEach(() => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "Adr",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [
        attr({ name: "title" }),
        attr({
          name: "decision_record", type: "widget", widget_key: "markdown_tab_group",
          fields: ["description", "context", "consequences"], order: 2,
        }),
        attr({ name: "description", type: "textarea", order: 3 }),
        attr({ name: "context", type: "textarea", order: 4 }),
        attr({ name: "consequences", type: "textarea", order: 5 }),
        attr({ name: "decision", type: "textarea", order: 6 }),
      ],
    } as never);
    vi.mocked(adrsApi.update).mockReset();
    vi.mocked(adrsApi.delete).mockReset();
  });

  it("maps an Adr onto form values", () => {
    const values = adrToFormValues(ADR);
    expect(values.context).toBe("c");
    expect(values.custom_fields).toEqual({});
  });

  it("keeps decision out of the widget and out of the read-only set", () => {
    const patch = formValuesToAdrPatch(adrToFormValues(ADR));
    expect(patch.decision).toBe("we use it");
    expect(patch).not.toHaveProperty("version");
  });

  it("renders the three bound markdown fields inside the tab group only", async () => {
    render(<AdrArtifactForm adr={ADR} onSaved={vi.fn()} onDeleted={vi.fn()} />);
    expect(
      await screen.findByTestId("artifact-widget-decision_record")
    ).toBeInTheDocument();
    expect(screen.queryByTestId("artifact-field-description")).not.toBeInTheDocument();
    expect(screen.queryByTestId("artifact-field-context")).not.toBeInTheDocument();
    // decision is NOT bound to the widget and must still be editable on its own.
    expect(screen.getByTestId("artifact-field-decision")).toBeInTheDocument();
  });

  it("saves through adrsApi.update", async () => {
    vi.mocked(adrsApi.update).mockResolvedValue(ADR);
    const onSaved = vi.fn();
    render(<AdrArtifactForm adr={ADR} onSaved={onSaved} onDeleted={vi.fn()} />);
    await userEvent.click(await screen.findByTestId("artifact-form-save"));
    await waitFor(() => expect(adrsApi.update).toHaveBeenCalled());
    expect(onSaved).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npx vitest run src/test/AdrArtifactForm.test.tsx`
Expected: FAIL — cannot resolve `../components/AdrEditors/AdrArtifactForm`.

- [ ] **Step 3: Write the adapter**

Create `frontend/src/components/AdrEditors/AdrArtifactForm.tsx`:

```tsx
/**
 * ADR editor on the definition-driven renderer (spec section 6.2, wave 2).
 *
 * The deleted AdrForm stacked three MarkdownPreview editors (description,
 * context, consequences); the definition now expresses that as one
 * `markdown_tab_group` widget bound to those exact three fields.
 * `Adr.decision` was never part of that group and stays an ordinary textarea,
 * so no content becomes unreachable.
 */

import { useMemo } from "react";

import { adrsApi } from "../../api/adrs";
import type { Adr } from "../../types";
import { ArtifactForm, type ArtifactFormValues } from "../shared/ArtifactForm";

const READ_ONLY_KEYS = new Set([
  "id",
  "workspace_id",
  "tenant_id",
  "version",
  "created_at",
  "modified_at",
  "updated_at",
  "artifact",
  "artifact_id",
  "uid",
  "status",
]);

export function adrToFormValues(adr: Adr): ArtifactFormValues {
  const { custom_fields: customFields, ...rest } = adr as unknown as Record<string, unknown>;
  return {
    ...rest,
    custom_fields: (customFields as Record<string, unknown>) ?? {},
  };
}

export function formValuesToAdrPatch(
  values: ArtifactFormValues
): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    if (READ_ONLY_KEYS.has(key)) continue;
    patch[key] = value;
  }
  return patch;
}

export interface AdrArtifactFormProps {
  adr: Adr;
  onSaved: () => void;
  onDeleted: () => void;
  onDirtyChange?: (isDirty: boolean) => void;
}

export function AdrArtifactForm({
  adr,
  onSaved,
  onDeleted,
  onDirtyChange,
}: AdrArtifactFormProps): JSX.Element {
  const initialValues = useMemo(() => adrToFormValues(adr), [adr]);

  return (
    <ArtifactForm
      itemType="Adr"
      artifactId={adr.id}
      initialValues={initialValues}
      workflowArtifactType="Adr"
      onDirtyChange={onDirtyChange}
      onSave={async (values) => {
        await adrsApi.update(adr.id, formValuesToAdrPatch(values));
        onSaved();
      }}
      onDelete={async () => {
        await adrsApi.delete(adr.id);
        onDeleted();
      }}
    />
  );
}
```

- [ ] **Step 4: Swap the parent and delete the old form**

In `frontend/src/components/AdrEditors/AdrEditors.tsx` replace the `AdrForm` import and render site with `AdrArtifactForm` (same props). Then:

```bash
git rm frontend/src/components/AdrEditors/AdrForm.tsx
```

- [ ] **Step 5: Check the E2E specs**

Run: `grep -rn "adr-form\|adr-description\|adr-context\|adr-consequences" e2e/`
Expected: rewrite each selector to the widget's ids (`artifact-widget-decision_record`, `artifact-widget-decision_record-tab-<field>`, `artifact-widget-decision_record-editor-<field>`) in this same commit.

- [ ] **Step 6: Re-measure and lower the inline-style baseline**

Run: `docker compose exec frontend npx vitest run src/test/ui-ratchet.test.ts --testTimeout=30000`, then set `STYLE_BRACE_BASELINE` to the reported count.

- [ ] **Step 7: Run the tests**

Run: `docker compose exec frontend npx vitest run src/test/AdrArtifactForm.test.tsx src/test/AdrEditors.test.tsx src/test/ui-ratchet.test.ts --testTimeout=30000`
Expected: PASS

- [ ] **Step 8: Verify in the browser**

`docker compose restart frontend`, open `/adrs`, confirm the three markdown tabs switch, preview renders, save persists all three fields.

- [ ] **Step 9: Commit**

```bash
git add -A frontend/src/components/AdrEditors frontend/src/test e2e
git commit -m "refactor(attribute-definitions): migrate ADR form onto ArtifactForm"
```

---

### Task 22: Rollout wave 2b — TestCase

Closes audit finding V as a side effect: `TestCase.steps` gets its first editor (`steps_editor` widget).

**Files:**
- Create: `frontend/src/components/TestCaseEditors/TestCaseArtifactForm.tsx`
- Modify: `frontend/src/components/TestCaseEditors/TestCaseEditors.tsx` (import + render site)
- Delete: `frontend/src/components/TestCaseEditors/TestCaseForm.tsx`
- Modify: `frontend/src/test/ui-ratchet.test.ts:335`
- Test: `frontend/src/test/TestCaseArtifactForm.test.tsx`

**Interfaces:**
- Consumes: `ArtifactForm`, `ArtifactFormValues` (Task 18); `StepsEditor` via `WIDGET_REGISTRY` (Task 17); `testcasesApi` from `../../api/testcases`; `TestCase` from `../../types`.
- Produces:
  - `testCaseToFormValues(testCase: TestCase): ArtifactFormValues`
  - `formValuesToTestCasePatch(values: ArtifactFormValues): Record<string, unknown>`
  - `function TestCaseArtifactForm(props: { testCase: TestCase; onSaved: () => void; onDeleted: () => void; onDirtyChange?: (isDirty: boolean) => void }): JSX.Element`

The bootstrap names the steps attribute `steps` (the widget) and its bound column `steps_data` (Task 6 `WIDGET_FIELD_ALIASES`), so the two never collide. The value mapping translates between `TestCase.steps` on the wire and `steps_data` in the form bag — that alias lives here and nowhere else.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/TestCaseArtifactForm.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { testcasesApi } from "../api/testcases";
import { attributeDefinitionsApi } from "../api/attribute-definitions";
import {
  TestCaseArtifactForm,
  formValuesToTestCasePatch,
  testCaseToFormValues,
} from "../components/TestCaseEditors/TestCaseArtifactForm";

vi.mock("../api/testcases", () => ({
  testcasesApi: { update: vi.fn(), delete: vi.fn() },
}));
vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: { getWorkspace: vi.fn() },
}));
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", preset: "standard" } }),
}));

const TEST_CASE = {
  id: "t-1",
  workspace_id: "ws-1",
  title: "Login works",
  description: "d",
  steps: ["open", "click"],
  test_type: "functional",
  custom_fields: {},
  version: 1,
} as never;

function attr(over: Record<string, unknown>) {
  return {
    name: "title", kind: "core", type: "text", widget_key: null, fields: [],
    options: [], required: false, visible: true, locked: false, editable: true,
    section: "general", order: 1, label: { de: "", en: "" },
    help_text: { de: "", en: "" }, default: null, validation: {},
    ai_elicit: false, export: true, audience: "basic", ...over,
  };
}

describe("TestCaseArtifactForm", () => {
  beforeEach(() => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "TestCase",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [
        attr({ name: "title" }),
        attr({
          name: "steps", type: "widget", widget_key: "steps_editor",
          fields: ["steps_data"], order: 2,
        }),
      ],
    } as never);
    vi.mocked(testcasesApi.update).mockReset();
    vi.mocked(testcasesApi.delete).mockReset();
  });

  it("aliases the wire field steps onto the form field steps_data", () => {
    const values = testCaseToFormValues(TEST_CASE);
    expect(values.steps_data).toEqual(["open", "click"]);
    expect(values).not.toHaveProperty("steps");
  });

  it("translates steps_data back to steps on the way out", () => {
    const patch = formValuesToTestCasePatch({
      title: "T",
      steps_data: ["a"],
      custom_fields: {},
    });
    expect(patch.steps).toEqual(["a"]);
    expect(patch).not.toHaveProperty("steps_data");
  });

  it("renders the steps editor and appends a step", async () => {
    render(
      <TestCaseArtifactForm
        testCase={TEST_CASE}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );
    expect(await screen.findByTestId("artifact-widget-steps")).toBeInTheDocument();
    expect(screen.getByTestId("artifact-widget-steps-step-0")).toHaveValue("open");
    await userEvent.click(screen.getByTestId("artifact-widget-steps-add"));
    expect(screen.getByTestId("artifact-widget-steps-step-2")).toBeInTheDocument();
  });

  it("saves the edited steps through testcasesApi.update", async () => {
    vi.mocked(testcasesApi.update).mockResolvedValue(TEST_CASE);
    render(
      <TestCaseArtifactForm
        testCase={TEST_CASE}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );
    await userEvent.click(await screen.findByTestId("artifact-widget-steps-add"));
    await userEvent.click(screen.getByTestId("artifact-form-save"));
    await waitFor(() =>
      expect(testcasesApi.update).toHaveBeenCalledWith(
        "t-1",
        expect.objectContaining({ steps: ["open", "click", ""] })
      )
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npx vitest run src/test/TestCaseArtifactForm.test.tsx`
Expected: FAIL — cannot resolve `../components/TestCaseEditors/TestCaseArtifactForm`.

- [ ] **Step 3: Write the adapter**

Create `frontend/src/components/TestCaseEditors/TestCaseArtifactForm.tsx`:

```tsx
/**
 * TestCase editor on the definition-driven renderer (spec section 6.2, wave 2).
 *
 * Closes audit finding V: `TestCase.steps` has existed as a column with no UI
 * at all, so steps were only writable through the API. The `steps_editor`
 * widget is that missing editor.
 *
 * Naming: the bootstrap registers the widget as `steps` and its bound column as
 * `steps_data` (WIDGET_FIELD_ALIASES) so the two do not collide inside one
 * attribute list. Translating between the wire name (`steps`) and the form name
 * (`steps_data`) happens HERE and nowhere else.
 */

import { useMemo } from "react";

import { testcasesApi } from "../../api/testcases";
import type { TestCase } from "../../types";
import { ArtifactForm, type ArtifactFormValues } from "../shared/ArtifactForm";

const STEPS_WIRE_FIELD = "steps";
const STEPS_FORM_FIELD = "steps_data";

const READ_ONLY_KEYS = new Set([
  "id",
  "workspace_id",
  "tenant_id",
  "version",
  "created_at",
  "modified_at",
  "updated_at",
  "artifact",
  "artifact_id",
  "uid",
  "suspect",
  "status",
]);

export function testCaseToFormValues(testCase: TestCase): ArtifactFormValues {
  const {
    custom_fields: customFields,
    [STEPS_WIRE_FIELD]: steps,
    ...rest
  } = testCase as unknown as Record<string, unknown>;
  return {
    ...rest,
    [STEPS_FORM_FIELD]: Array.isArray(steps) ? steps : [],
    custom_fields: (customFields as Record<string, unknown>) ?? {},
  };
}

export function formValuesToTestCasePatch(
  values: ArtifactFormValues
): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    if (READ_ONLY_KEYS.has(key)) continue;
    if (key === STEPS_FORM_FIELD) {
      patch[STEPS_WIRE_FIELD] = value;
      continue;
    }
    patch[key] = value;
  }
  return patch;
}

export interface TestCaseArtifactFormProps {
  testCase: TestCase;
  onSaved: () => void;
  onDeleted: () => void;
  onDirtyChange?: (isDirty: boolean) => void;
}

export function TestCaseArtifactForm({
  testCase,
  onSaved,
  onDeleted,
  onDirtyChange,
}: TestCaseArtifactFormProps): JSX.Element {
  const initialValues = useMemo(() => testCaseToFormValues(testCase), [testCase]);

  return (
    <ArtifactForm
      itemType="TestCase"
      artifactId={testCase.id}
      initialValues={initialValues}
      workflowArtifactType="TestCase"
      onDirtyChange={onDirtyChange}
      onSave={async (values) => {
        await testcasesApi.update(testCase.id, formValuesToTestCasePatch(values));
        onSaved();
      }}
      onDelete={async () => {
        await testcasesApi.delete(testCase.id);
        onDeleted();
      }}
    />
  );
}
```

- [ ] **Step 4: Swap the parent and delete the old form**

In `frontend/src/components/TestCaseEditors/TestCaseEditors.tsx` replace the `TestCaseForm` import and render site with `TestCaseArtifactForm`. Then:

```bash
git rm frontend/src/components/TestCaseEditors/TestCaseForm.tsx
```

- [ ] **Step 5: Check the E2E specs**

Run: `grep -rn "testcase-form\|test-case-form\|testcase-save" e2e/`
Expected: update every hit to the renderer's ids in this same commit.

- [ ] **Step 6: Re-measure and lower the inline-style baseline**

Run: `docker compose exec frontend npx vitest run src/test/ui-ratchet.test.ts --testTimeout=30000`, then set `STYLE_BRACE_BASELINE` to the reported count.

- [ ] **Step 7: Run the tests**

Run: `docker compose exec frontend npx vitest run src/test/TestCaseArtifactForm.test.tsx src/test/TestCaseEditors.test.tsx src/test/ui-ratchet.test.ts --testTimeout=30000`
Expected: PASS

- [ ] **Step 8: Verify in the browser**

`docker compose restart frontend`, open `/testcases`, add and remove steps, save, reload and confirm the steps persisted.

- [ ] **Step 9: Commit**

```bash
git add -A frontend/src/components/TestCaseEditors frontend/src/test e2e
git commit -m "refactor(attribute-definitions): migrate TestCase form onto ArtifactForm"
```

---

### Task 23: Rollout wave 2c — StakeholderNeed

`NeedForm.tsx` (631 lines) is the only form that reads the old `AttributeVisibilityConfig`, so this task also removes the last live consumer of that prop chain.

**Scope boundary that applies to this and the next two tasks:** `ArtifactForm` renders *attributes*. Non-attribute panels the current forms host — `DeriveRequirementsPanel`, `TraceLinkPanel`, `DeriveRequirementForm`, `ArtifactId`, `VersionBadge` — are **not** attributes and stay in the parent editor component, rendered next to the form. Folding them into the renderer would put trace-graph concerns behind a field-definition contract; keeping them outside is what lets the renderer stay type-agnostic.

**Files:**
- Create: `frontend/src/components/NeedsEditors/NeedArtifactForm.tsx`
- Modify: `frontend/src/components/NeedsEditors/NeedsEditors.tsx` (import, render site, drop the `attributeVisibility` prop it passes down)
- Delete: `frontend/src/components/NeedsEditors/NeedForm.tsx`
- Modify: `frontend/src/test/ui-ratchet.test.ts:335`
- Test: `frontend/src/test/NeedArtifactForm.test.tsx`

**Interfaces:**
- Consumes: `ArtifactForm`, `ArtifactFormValues` (Task 18); `stakeholderNeedApi` from `../../api/stakeholder-need`; `StakeholderNeed` from `../../types`; `DeriveRequirementsPanel` and `TraceLinkPanel` (unchanged, rendered as siblings).
- Produces:
  - `needToFormValues(need: StakeholderNeed): ArtifactFormValues`
  - `formValuesToNeedPatch(values: ArtifactFormValues): Record<string, unknown>`
  - `function NeedArtifactForm(props: { need: StakeholderNeed; onSaved: () => void; onDeleted: () => void; onDirtyChange?: (isDirty: boolean) => void }): JSX.Element`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/NeedArtifactForm.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { stakeholderNeedApi } from "../api/stakeholder-need";
import { attributeDefinitionsApi } from "../api/attribute-definitions";
import {
  NeedArtifactForm,
  formValuesToNeedPatch,
  needToFormValues,
} from "../components/NeedsEditors/NeedArtifactForm";

vi.mock("../api/stakeholder-need", () => ({
  stakeholderNeedApi: { update: vi.fn(), delete: vi.fn() },
}));
vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: { getWorkspace: vi.fn() },
}));
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", preset: "standard" } }),
}));

const NEED = {
  id: "n-1",
  workspace_id: "ws-1",
  title: "Fast login",
  description: "d",
  category: "usability",
  moscow_priority: "must",
  custom_fields: {},
  version: 1,
} as never;

function attr(over: Record<string, unknown>) {
  return {
    name: "title", kind: "core", type: "text", widget_key: null, fields: [],
    options: [], required: false, visible: true, locked: false, editable: true,
    section: "general", order: 1, label: { de: "", en: "" },
    help_text: { de: "", en: "" }, default: null, validation: {},
    ai_elicit: false, export: true, audience: "basic", ...over,
  };
}

describe("NeedArtifactForm", () => {
  beforeEach(() => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "StakeholderNeed",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [
        attr({ name: "title", required: true }),
        attr({ name: "moscow_priority", type: "enum", order: 2, visible: false }),
      ],
    } as never);
    vi.mocked(stakeholderNeedApi.update).mockReset();
    vi.mocked(stakeholderNeedApi.delete).mockReset();
  });

  it("maps a StakeholderNeed onto form values", () => {
    const values = needToFormValues(NEED);
    expect(values.title).toBe("Fast login");
    expect(values.custom_fields).toEqual({});
  });

  it("strips server-owned fields from the patch", () => {
    const patch = formValuesToNeedPatch(needToFormValues(NEED));
    expect(patch).not.toHaveProperty("id");
    expect(patch).not.toHaveProperty("version");
    expect(patch.category).toBe("usability");
  });

  it("hides an attribute the definition marks invisible", async () => {
    render(<NeedArtifactForm need={NEED} onSaved={vi.fn()} onDeleted={vi.fn()} />);
    await screen.findByTestId("artifact-field-title");
    expect(
      screen.queryByTestId("artifact-field-moscow_priority")
    ).not.toBeInTheDocument();
  });

  it("saves through stakeholderNeedApi.update", async () => {
    vi.mocked(stakeholderNeedApi.update).mockResolvedValue(NEED);
    const onSaved = vi.fn();
    render(<NeedArtifactForm need={NEED} onSaved={onSaved} onDeleted={vi.fn()} />);
    await userEvent.click(await screen.findByTestId("artifact-form-save"));
    await waitFor(() => expect(stakeholderNeedApi.update).toHaveBeenCalled());
    expect(onSaved).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npx vitest run src/test/NeedArtifactForm.test.tsx`
Expected: FAIL — cannot resolve `../components/NeedsEditors/NeedArtifactForm`.

- [ ] **Step 3: Write the adapter**

Create `frontend/src/components/NeedsEditors/NeedArtifactForm.tsx`:

```tsx
/**
 * StakeholderNeed editor on the definition-driven renderer (spec section 6.2,
 * wave 2).
 *
 * NeedForm was the ONLY consumer of the old AttributeVisibilityConfig prop
 * chain; deleting it removes the last live reader of that mechanism. Field
 * visibility now comes from the resolved definition like every other type.
 *
 * DeriveRequirementsPanel / TraceLinkPanel are not attributes and stay in
 * NeedsEditors as siblings of this form.
 */

import { useMemo } from "react";

import { stakeholderNeedApi } from "../../api/stakeholder-need";
import type { StakeholderNeed } from "../../types";
import { ArtifactForm, type ArtifactFormValues } from "../shared/ArtifactForm";

const READ_ONLY_KEYS = new Set([
  "id",
  "workspace_id",
  "tenant_id",
  "version",
  "created_at",
  "modified_at",
  "updated_at",
  "artifact",
  "artifact_id",
  "uid",
  "status",
]);

export function needToFormValues(need: StakeholderNeed): ArtifactFormValues {
  const { custom_fields: customFields, ...rest } =
    need as unknown as Record<string, unknown>;
  return {
    ...rest,
    custom_fields: (customFields as Record<string, unknown>) ?? {},
  };
}

export function formValuesToNeedPatch(
  values: ArtifactFormValues
): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    if (READ_ONLY_KEYS.has(key)) continue;
    patch[key] = value;
  }
  return patch;
}

export interface NeedArtifactFormProps {
  need: StakeholderNeed;
  onSaved: () => void;
  onDeleted: () => void;
  onDirtyChange?: (isDirty: boolean) => void;
}

export function NeedArtifactForm({
  need,
  onSaved,
  onDeleted,
  onDirtyChange,
}: NeedArtifactFormProps): JSX.Element {
  const initialValues = useMemo(() => needToFormValues(need), [need]);

  return (
    <ArtifactForm
      itemType="StakeholderNeed"
      artifactId={need.id}
      initialValues={initialValues}
      workflowArtifactType="StakeholderNeed"
      onDirtyChange={onDirtyChange}
      onSave={async (values) => {
        await stakeholderNeedApi.update(need.id, formValuesToNeedPatch(values));
        onSaved();
      }}
      onDelete={async () => {
        await stakeholderNeedApi.delete(need.id);
        onDeleted();
      }}
    />
  );
}
```

- [ ] **Step 4: Swap the parent, drop the visibility prop, delete the old form**

In `frontend/src/components/NeedsEditors/NeedsEditors.tsx`:
- replace the `NeedForm` import and render site with `NeedArtifactForm`, keeping `need` / `onSaved` / `onDeleted` / `onDirtyChange`;
- delete the `attributeVisibility` prop from the render site and every piece of state, effect and `attributeVisibilityApi` call that produced it;
- keep `DeriveRequirementsPanel` and `TraceLinkPanel` where they are, rendered next to the form.

Then:

```bash
git rm frontend/src/components/NeedsEditors/NeedForm.tsx
```

- [ ] **Step 5: Check the E2E specs**

Run: `grep -rn "need-form\|need-save\|need-delete" e2e/`
Expected: update every hit to the renderer's ids in this same commit.

- [ ] **Step 6: Re-measure and lower the inline-style baseline**

Run: `docker compose exec frontend npx vitest run src/test/ui-ratchet.test.ts --testTimeout=30000`, then set `STYLE_BRACE_BASELINE` to the reported count.

- [ ] **Step 7: Run the tests**

Run: `docker compose exec frontend npx vitest run src/test/NeedArtifactForm.test.tsx src/test/NeedsEditors.test.tsx src/test/ui-ratchet.test.ts --testTimeout=30000`
Expected: PASS

- [ ] **Step 8: Verify in the browser**

`docker compose restart frontend`, open `/needs`, confirm fields, save, dirty warning, delete, and that the derive panel and trace links still render.

- [ ] **Step 9: Commit**

```bash
git add -A frontend/src/components/NeedsEditors frontend/src/test e2e
git commit -m "refactor(attribute-definitions): migrate Need form onto ArtifactForm"
```

---

### Task 24: Rollout wave 2d — ArchitectureElement

**Files:**
- Create: `frontend/src/components/ArchitectureEditors/ArchitectureArtifactForm.tsx`
- Modify: `frontend/src/components/ArchitectureEditors/ArchitectureEditors.tsx` (import + render site)
- Delete: `frontend/src/components/ArchitectureEditors/ArchitectureForm.tsx`
- Modify: `frontend/src/test/ui-ratchet.test.ts:335`
- Test: `frontend/src/test/ArchitectureArtifactForm.test.tsx`

**Interfaces:**
- Consumes: `ArtifactForm`, `ArtifactFormValues` (Task 18); `architectureApi` from `../../api/architecture`; `ArchitectureElement` from `../../types`.
- Produces:
  - `architectureToFormValues(element: ArchitectureElement): ArtifactFormValues`
  - `formValuesToArchitecturePatch(values: ArtifactFormValues): Record<string, unknown>`
  - `function ArchitectureArtifactForm(props: { element: ArchitectureElement; onSaved: () => void; onDeleted: () => void; onDirtyChange?: (isDirty: boolean) => void }): JSX.Element`

`ArchitectureEditors.tsx` is the repo's highest-churn frontend file (20 recorded bug fixes). Touch only the import and the single render site; the decompose panel, the tree and the trace panel stay exactly as they are.

`parent` is a same-type containment FK, not a TraceLink — it renders as an ordinary `reference` attribute. Cross-type relations remain TraceLinks and stay in the trace panel.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/ArchitectureArtifactForm.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { architectureApi } from "../api/architecture";
import { attributeDefinitionsApi } from "../api/attribute-definitions";
import {
  ArchitectureArtifactForm,
  architectureToFormValues,
  formValuesToArchitecturePatch,
} from "../components/ArchitectureEditors/ArchitectureArtifactForm";

vi.mock("../api/architecture", () => ({
  architectureApi: { update: vi.fn(), delete: vi.fn() },
}));
vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: { getWorkspace: vi.fn() },
}));
vi.mock("../api/artifactRefs", () => ({ resolveArtifactRefs: vi.fn(async () => []) }));
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", preset: "standard" } }),
}));

const ELEMENT = {
  id: "e-1",
  workspace_id: "ws-1",
  title: "Gateway",
  description: "d",
  element_type: "block",
  parent: "e-0",
  custom_fields: {},
  version: 4,
} as never;

function attr(over: Record<string, unknown>) {
  return {
    name: "title", kind: "core", type: "text", widget_key: null, fields: [],
    options: [], required: false, visible: true, locked: false, editable: true,
    section: "general", order: 1, label: { de: "", en: "" },
    help_text: { de: "", en: "" }, default: null, validation: {},
    ai_elicit: false, export: true, audience: "basic", ...over,
  };
}

describe("ArchitectureArtifactForm", () => {
  beforeEach(() => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "ArchitectureElement",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [
        attr({ name: "title", required: true }),
        attr({ name: "parent", type: "reference", order: 2 }),
      ],
    } as never);
    vi.mocked(architectureApi.update).mockReset();
    vi.mocked(architectureApi.delete).mockReset();
  });

  it("maps an ArchitectureElement onto form values", () => {
    const values = architectureToFormValues(ELEMENT);
    expect(values.element_type).toBe("block");
    expect(values.parent).toBe("e-0");
  });

  it("strips server-owned fields from the patch", () => {
    const patch = formValuesToArchitecturePatch(architectureToFormValues(ELEMENT));
    expect(patch).not.toHaveProperty("version");
    expect(patch).not.toHaveProperty("workspace_id");
    expect(patch.title).toBe("Gateway");
  });

  it("renders the containment parent as a reference picker", async () => {
    render(
      <ArchitectureArtifactForm
        element={ELEMENT}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );
    expect(await screen.findByTestId("artifact-field-parent")).toBeInTheDocument();
  });

  it("saves through architectureApi.update", async () => {
    vi.mocked(architectureApi.update).mockResolvedValue(ELEMENT);
    const onSaved = vi.fn();
    render(
      <ArchitectureArtifactForm
        element={ELEMENT}
        onSaved={onSaved}
        onDeleted={vi.fn()}
      />
    );
    await userEvent.click(await screen.findByTestId("artifact-form-save"));
    await waitFor(() => expect(architectureApi.update).toHaveBeenCalled());
    expect(onSaved).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npx vitest run src/test/ArchitectureArtifactForm.test.tsx`
Expected: FAIL — cannot resolve `../components/ArchitectureEditors/ArchitectureArtifactForm`.

- [ ] **Step 3: Write the adapter**

Create `frontend/src/components/ArchitectureEditors/ArchitectureArtifactForm.tsx`:

```tsx
/**
 * ArchitectureElement editor on the definition-driven renderer
 * (spec section 6.2, wave 2).
 *
 * `parent` is the same-type containment FK and renders as an ordinary
 * `reference` attribute. Cross-type relations are TraceLinks and stay in the
 * trace panel — the element hierarchy is deliberately not a link.
 *
 * The decompose panel and the element tree are not attributes and stay in
 * ArchitectureEditors.
 */

import { useMemo } from "react";

import { architectureApi } from "../../api/architecture";
import type { ArchitectureElement } from "../../types";
import { ArtifactForm, type ArtifactFormValues } from "../shared/ArtifactForm";

const READ_ONLY_KEYS = new Set([
  "id",
  "workspace_id",
  "tenant_id",
  "version",
  "created_at",
  "modified_at",
  "updated_at",
  "artifact",
  "artifact_id",
  "uid",
  "status",
]);

export function architectureToFormValues(
  element: ArchitectureElement
): ArtifactFormValues {
  const { custom_fields: customFields, ...rest } =
    element as unknown as Record<string, unknown>;
  return {
    ...rest,
    custom_fields: (customFields as Record<string, unknown>) ?? {},
  };
}

export function formValuesToArchitecturePatch(
  values: ArtifactFormValues
): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    if (READ_ONLY_KEYS.has(key)) continue;
    patch[key] = value;
  }
  return patch;
}

export interface ArchitectureArtifactFormProps {
  element: ArchitectureElement;
  onSaved: () => void;
  onDeleted: () => void;
  onDirtyChange?: (isDirty: boolean) => void;
}

export function ArchitectureArtifactForm({
  element,
  onSaved,
  onDeleted,
  onDirtyChange,
}: ArchitectureArtifactFormProps): JSX.Element {
  const initialValues = useMemo(
    () => architectureToFormValues(element),
    [element]
  );

  return (
    <ArtifactForm
      itemType="ArchitectureElement"
      artifactId={element.id}
      initialValues={initialValues}
      workflowArtifactType="ArchitectureElement"
      onDirtyChange={onDirtyChange}
      onSave={async (values) => {
        await architectureApi.update(
          element.id,
          formValuesToArchitecturePatch(values)
        );
        onSaved();
      }}
      onDelete={async () => {
        await architectureApi.delete(element.id);
        onDeleted();
      }}
    />
  );
}
```

- [ ] **Step 4: Swap the parent and delete the old form**

In `frontend/src/components/ArchitectureEditors/ArchitectureEditors.tsx` replace only the `ArchitectureForm` import and its single render site with `ArchitectureArtifactForm`. Leave the decompose panel, tree and trace panel untouched. Then:

```bash
git rm frontend/src/components/ArchitectureEditors/ArchitectureForm.tsx
```

- [ ] **Step 5: Check the E2E specs**

Run: `grep -rn "architecture-form\|arch-form\|architecture-save" e2e/`
Expected: update every hit to the renderer's ids in this same commit.

- [ ] **Step 6: Re-measure and lower the inline-style baseline**

Run: `docker compose exec frontend npx vitest run src/test/ui-ratchet.test.ts --testTimeout=30000`, then set `STYLE_BRACE_BASELINE` to the reported count.

- [ ] **Step 7: Run the tests**

Run: `docker compose exec frontend npx vitest run src/test/ArchitectureArtifactForm.test.tsx src/test/ArchitectureEditors.test.tsx src/test/ArchitectureEditors.unsaved-changes.test.tsx src/test/ui-ratchet.test.ts --testTimeout=30000`
Expected: PASS. `ArchitectureEditors.unsaved-changes.test.tsx` asserts the dirty-warning behaviour — it must stay green through `onDirtyChange`.

- [ ] **Step 8: Verify in the browser**

`docker compose restart frontend`, open `/architecture`, select an element, confirm fields render, the parent picker lists elements, save persists, decompose panel and tree still work.

- [ ] **Step 9: Commit**

```bash
git add -A frontend/src/components/ArchitectureEditors frontend/src/test e2e
git commit -m "refactor(attribute-definitions): migrate Architecture form onto ArtifactForm"
```

---

### Task 25: Rollout wave 3 — Requirement (last)

Spec section 6.2: Requirement goes last because it has the most special cases. By now the renderer covers everything the other six raised; this task adds the one remaining shared capability — the extended-preset `change_reason` — to `ArtifactForm` itself rather than to the Requirement adapter, so all ten types gain it at once (parity policy, spec section 6.3).

**Files:**
- Modify: `frontend/src/components/shared/ArtifactForm/ArtifactForm.tsx` (change-reason control)
- Create: `frontend/src/components/RequirementEditors/RequirementArtifactForm.tsx`
- Modify: `frontend/src/components/RequirementEditors/RequirementEditors.tsx` (import + render site)
- Delete: `frontend/src/components/RequirementEditors/RequirementForm.tsx`
- Modify: `frontend/src/test/ui-ratchet.test.ts:335`
- Test: `frontend/src/test/RequirementArtifactForm.test.tsx`

**Interfaces:**
- Consumes: `ArtifactForm`, `ArtifactFormValues` (Task 18); `requirementsApi` from `../../api/requirements`; `Requirement` from `../../types`; `useWorkspace`.
- Produces:
  - added to `ArtifactFormProps`: `requiresChangeReason?: boolean` — when true and `artifactId !== null`, the form renders a required change-reason input and refuses to save while it is empty; its value travels in `values.change_reason`
  - `requirementToFormValues(requirement: Requirement): ArtifactFormValues`
  - `formValuesToRequirementPatch(values: ArtifactFormValues): Record<string, unknown>`
  - `function RequirementArtifactForm(props: { requirement: Requirement; onSaved: () => void; onDeleted: () => void; onDirtyChange?: (isDirty: boolean) => void }): JSX.Element`

The three Requirement-only actions — derive, generate test case, find similar — are not attributes and stay in `RequirementEditors` as siblings of the form, same boundary as Task 23.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/RequirementArtifactForm.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { requirementsApi } from "../api/requirements";
import { attributeDefinitionsApi } from "../api/attribute-definitions";
import {
  RequirementArtifactForm,
  formValuesToRequirementPatch,
  requirementToFormValues,
} from "../components/RequirementEditors/RequirementArtifactForm";

const workspace = { current: { id: "ws-1", preset: "standard" } };

vi.mock("../api/requirements", () => ({
  requirementsApi: { update: vi.fn(), delete: vi.fn() },
}));
vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: { getWorkspace: vi.fn() },
}));
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: workspace.current }),
}));

const REQUIREMENT = {
  id: "req-1",
  workspace_id: "ws-1",
  title: "Login",
  description: "d",
  acceptance_criteria: "ac",
  category: "functional",
  verification_method: "test",
  uid: "REQ-1",
  custom_fields: {},
  version: 7,
} as never;

function attr(over: Record<string, unknown>) {
  return {
    name: "title", kind: "core", type: "text", widget_key: null, fields: [],
    options: [], required: false, visible: true, locked: false, editable: true,
    section: "general", order: 1, label: { de: "", en: "" },
    help_text: { de: "", en: "" }, default: null, validation: {},
    ai_elicit: false, export: true, audience: "basic", ...over,
  };
}

describe("RequirementArtifactForm", () => {
  beforeEach(() => {
    workspace.current = { id: "ws-1", preset: "standard" };
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "Requirement",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [
        attr({ name: "title", required: true }),
        attr({ name: "acceptance_criteria", type: "textarea", order: 2 }),
        attr({
          name: "verification_method", type: "enum", section: "classification",
          order: 1, audience: "expert",
          options: [{ value: "test", label_de: "Test", label_en: "Test" }],
        }),
        attr({ name: "uid", section: "change_control", order: 1, editable: false }),
      ],
    } as never);
    vi.mocked(requirementsApi.update).mockReset();
    vi.mocked(requirementsApi.delete).mockReset();
  });

  it("maps a Requirement onto form values", () => {
    const values = requirementToFormValues(REQUIREMENT);
    expect(values.acceptance_criteria).toBe("ac");
    expect(values.custom_fields).toEqual({});
  });

  it("strips server-owned fields from the patch", () => {
    const patch = formValuesToRequirementPatch(requirementToFormValues(REQUIREMENT));
    expect(patch).not.toHaveProperty("version");
    expect(patch).not.toHaveProperty("id");
    expect(patch.title).toBe("Login");
  });

  it("renders the classification and change-control sections", async () => {
    render(
      <RequirementArtifactForm
        requirement={REQUIREMENT}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );
    expect(
      await screen.findByTestId("artifact-section-toggle-classification")
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("artifact-section-toggle-change_control")
    ).toBeInTheDocument();
  });

  it("renders an editable=false attribute as disabled", async () => {
    render(
      <RequirementArtifactForm
        requirement={REQUIREMENT}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );
    await userEvent.click(
      await screen.findByTestId("artifact-section-toggle-change_control")
    );
    expect(screen.getByTestId("artifact-field-uid")).toBeDisabled();
  });

  it("does not ask for a change reason outside the extended preset", async () => {
    render(
      <RequirementArtifactForm
        requirement={REQUIREMENT}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );
    await screen.findByTestId("artifact-field-title");
    expect(screen.queryByTestId("artifact-form-change-reason")).not.toBeInTheDocument();
  });

  it("requires a change reason in the extended preset before saving", async () => {
    workspace.current = { id: "ws-1", preset: "extended" };
    vi.mocked(requirementsApi.update).mockResolvedValue(REQUIREMENT);
    render(
      <RequirementArtifactForm
        requirement={REQUIREMENT}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
      />
    );
    const save = await screen.findByTestId("artifact-form-save");
    expect(screen.getByTestId("artifact-form-change-reason")).toBeInTheDocument();
    await userEvent.click(save);
    expect(requirementsApi.update).not.toHaveBeenCalled();

    await userEvent.type(
      screen.getByTestId("artifact-form-change-reason"),
      "clarified wording"
    );
    await userEvent.click(save);
    await waitFor(() =>
      expect(requirementsApi.update).toHaveBeenCalledWith(
        "req-1",
        expect.objectContaining({ change_reason: "clarified wording" })
      )
    );
  });

  it("saves and clears the dirty state", async () => {
    vi.mocked(requirementsApi.update).mockResolvedValue(REQUIREMENT);
    const onDirtyChange = vi.fn();
    render(
      <RequirementArtifactForm
        requirement={REQUIREMENT}
        onSaved={vi.fn()}
        onDeleted={vi.fn()}
        onDirtyChange={onDirtyChange}
      />
    );
    await userEvent.type(await screen.findByTestId("artifact-field-title"), "!");
    await userEvent.click(screen.getByTestId("artifact-form-save"));
    await waitFor(() => expect(onDirtyChange).toHaveBeenLastCalledWith(false));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npx vitest run src/test/RequirementArtifactForm.test.tsx`
Expected: FAIL — cannot resolve `../components/RequirementEditors/RequirementArtifactForm`.

- [ ] **Step 3: Add the change-reason control to `ArtifactForm` (all types)**

In `frontend/src/components/shared/ArtifactForm/ArtifactForm.tsx`:

Add to `ArtifactFormProps`:

```tsx
  /**
   * Extended-preset rule (REQ-162): an update must carry a change reason.
   * Lives here rather than in one adapter so every type gets it — the parity
   * policy forbids a capability that exists for one type only.
   * Ignored in create mode (`artifactId === null`): there is no change to explain.
   */
  requiresChangeReason?: boolean;
```

Add it to the destructured props with `requiresChangeReason = false`, and add the state plus the guard:

```tsx
  const [changeReason, setChangeReason] = useState<string>("");
  const changeReasonNeeded = requiresChangeReason && artifactId !== null && !isReadOnly;
  const changeReasonMissing = changeReasonNeeded && !changeReason.trim();
```

In `handleSave`, before the `await onSave(...)` call, guard and merge:

```tsx
    if (changeReasonMissing) {
      setFormError(t("artifactForm.changeReasonRequired"));
      return;
    }
    setSaving(true);
    setFormError(null);
    setFieldErrors({});
    const payload: ArtifactFormValues = changeReasonNeeded
      ? { ...values, change_reason: changeReason.trim() }
      : values;
    try {
      await onSave(payload);
      markClean(values);
      setChangeReason("");
    } catch (exc: unknown) {
```

(replace the existing `setSaving(true)` / `await onSave(values)` / `markClean(values)` lines with the block above; `markClean` keeps taking `values`, not `payload`, because `change_reason` is not part of the artifact's own state and must not count as a pending edit).

Render the control just above `styles.actions`:

```tsx
      {changeReasonNeeded ? (
        <label className={styles.field}>
          <span className={`${styles.label} ${styles.required}`}>
            {t("artifactForm.changeReason")}
          </span>
          <input
            className={styles.control}
            data-testid="artifact-form-change-reason"
            type="text"
            value={changeReason}
            required
            aria-required="true"
            onChange={(event) => setChangeReason(event.target.value)}
          />
        </label>
      ) : null}
```

Add the two i18n keys to both locale files under `artifactForm`: de `"changeReason": "Änderungsgrund"`, `"changeReasonRequired": "Bitte einen Änderungsgrund angeben."`; en `"changeReason": "Change reason"`, `"changeReasonRequired": "Please provide a change reason."`.

- [ ] **Step 4: Write the adapter**

Create `frontend/src/components/RequirementEditors/RequirementArtifactForm.tsx`:

```tsx
/**
 * Requirement editor on the definition-driven renderer — last of the seven
 * (spec section 6.2), because it carried the most special cases.
 *
 * What is NOT here on purpose: derive, generate-test-case and find-similar are
 * actions on a requirement, not attributes of one. They stay in
 * RequirementEditors as siblings of this form, the same boundary the Need and
 * Architecture migrations drew.
 */

import { useMemo } from "react";

import { requirementsApi } from "../../api/requirements";
import { useWorkspace } from "../../context/WorkspaceContext";
import type { Requirement } from "../../types";
import { ArtifactForm, type ArtifactFormValues } from "../shared/ArtifactForm";

const READ_ONLY_KEYS = new Set([
  "id",
  "workspace_id",
  "tenant_id",
  "version",
  "created_at",
  "modified_at",
  "updated_at",
  "artifact",
  "artifact_id",
  "status",
  "lifecycle_status",
  "suspect",
]);

export function requirementToFormValues(
  requirement: Requirement
): ArtifactFormValues {
  const { custom_fields: customFields, ...rest } =
    requirement as unknown as Record<string, unknown>;
  return {
    ...rest,
    custom_fields: (customFields as Record<string, unknown>) ?? {},
  };
}

export function formValuesToRequirementPatch(
  values: ArtifactFormValues
): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    if (READ_ONLY_KEYS.has(key)) continue;
    patch[key] = value;
  }
  return patch;
}

export interface RequirementArtifactFormProps {
  requirement: Requirement;
  onSaved: () => void;
  onDeleted: () => void;
  onDirtyChange?: (isDirty: boolean) => void;
}

export function RequirementArtifactForm({
  requirement,
  onSaved,
  onDeleted,
  onDirtyChange,
}: RequirementArtifactFormProps): JSX.Element {
  const { activeWorkspace } = useWorkspace();
  const initialValues = useMemo(
    () => requirementToFormValues(requirement),
    [requirement]
  );

  return (
    <ArtifactForm
      itemType="Requirement"
      artifactId={requirement.id}
      initialValues={initialValues}
      workflowArtifactType="Requirement"
      requiresChangeReason={activeWorkspace?.preset === "extended"}
      onDirtyChange={onDirtyChange}
      onSave={async (values) => {
        await requirementsApi.update(
          requirement.id,
          formValuesToRequirementPatch(values)
        );
        onSaved();
      }}
      onDelete={async () => {
        await requirementsApi.delete(requirement.id);
        onDeleted();
      }}
    />
  );
}
```

`formValuesToRequirementPatch` deliberately does **not** strip `change_reason`: the ViewSet expects it as a control field on the update payload.

- [ ] **Step 5: Swap the parent and delete the old form**

In `frontend/src/components/RequirementEditors/RequirementEditors.tsx` replace the `RequirementForm` import and its render site with `RequirementArtifactForm`, keeping `onDirtyChange`. Leave the derive / test-case / similar panels in place. Then:

```bash
git rm frontend/src/components/RequirementEditors/RequirementForm.tsx
```

- [ ] **Step 6: Check the E2E specs**

Run: `grep -rn "requirement-form\|requirement-save\|requirement-title\|change-reason" e2e/`
Expected: the largest set of hits of any rollout task. Update each to the renderer's ids (`artifact-field-title`, `artifact-form-save`, `artifact-form-change-reason`, …) in this same commit.

- [ ] **Step 7: Re-measure and lower the inline-style baseline**

Run: `docker compose exec frontend npx vitest run src/test/ui-ratchet.test.ts --testTimeout=30000`, then set `STYLE_BRACE_BASELINE` to the reported count. This is the last and largest drop.

- [ ] **Step 8: Run the tests**

Run: `docker compose exec frontend npx vitest run src/test/RequirementArtifactForm.test.tsx src/test/RequirementEditors.test.tsx src/test/RequirementEditors.unsaved-changes.test.tsx src/test/ArtifactForm.test.tsx src/test/ui-ratchet.test.ts --testTimeout=30000`
Expected: PASS

- [ ] **Step 9: Verify in the browser**

`docker compose restart frontend`, open `/requirements`, and confirm: all sections render, an expert section starts collapsed, `uid` is disabled, save works, an extended-preset workspace demands a change reason, delete asks for confirmation, and the derive / test-case / similar actions still work.

- [ ] **Step 10: Commit**

```bash
git add -A frontend/src/components/RequirementEditors frontend/src/components/shared/ArtifactForm frontend/src/i18n/locales frontend/src/test e2e
git commit -m "refactor(attribute-definitions): migrate Requirement form onto ArtifactForm"
```

---

### Task 26: `AttributeEditorPage` — the admin editor

Spec section 6.1. Shell taken 1:1 from the workflow editor (`EntityTypeSelector`, `PresetSegmentedControl`, `InspectorPanel` composition, `scope` prop); the canvas is replaced by a section/attribute list.

Drag-and-drop uses the native HTML5 drag events — no new dependency for a single reorderable list.

**Files:**
- Create: `frontend/src/components/AttributeEditor/AttributeEditorPage.tsx`
- Create: `frontend/src/components/AttributeEditor/AttributeList.tsx`
- Create: `frontend/src/components/AttributeEditor/AttributeInspector.tsx`
- Create: `frontend/src/components/AttributeEditor/attribute-edits.ts`
- Create: `frontend/src/components/AttributeEditor/AttributeEditor.module.css`
- Create: `frontend/src/components/AttributeEditor/index.ts`
- Modify: `frontend/src/components/NavigationShell/NavigationShell.tsx` (two routes)
- Modify: `frontend/src/components/SystemSettings/SystemSettings.tsx` (global tab)
- Modify: `frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx` (workspace tab)
- Test: `frontend/src/test/AttributeEditor.test.tsx`

**Interfaces:**
- Consumes: `attributeDefinitionsApi`, `AttributeSpec`, `AttributeAudience` (Task 15); `EntityTypeSelector`, `PresetSegmentedControl` from `../WorkflowEditor`; `WORKFLOW_ENTITY_TYPES`, `WORKFLOW_PRESETS` from `../WorkflowEditor/constants`; `useAuth`, `useWorkspace`; `ConfirmDialog`.
- Produces (pure helpers in `attribute-edits.ts`, all returning new arrays — the page never mutates state in place):
  - `moveAttribute(attributes: AttributeSpec[], name: string, toSection: string, toIndex: number): AttributeSpec[]`
  - `renameSection(attributes: AttributeSpec[], from: string, to: string): AttributeSpec[]`
  - `deleteSection(attributes: AttributeSpec[], name: string): AttributeSpec[]` (throws `Error` when the section is not empty)
  - `moveSection(attributes: AttributeSpec[], name: string, toIndex: number): AttributeSpec[]`
  - `patchAttribute(attributes: AttributeSpec[], name: string, patch: Partial<AttributeSpec>): AttributeSpec[]`
  - `isMetaPropertyLocked(attribute: AttributeSpec, property: keyof AttributeSpec): boolean`
  - `sectionNames(attributes: AttributeSpec[]): string[]`
- Produces (components): `AttributeEditorPage({ scope }: { scope?: "workspace" | "global" })`, `AttributeList`, `AttributeInspector`.

Routes: `/attributes` and `/attributes/:entityType` render `AttributeEditorPage` in workspace scope; System Settings mounts `<AttributeEditorPage scope="global" />`, which reads `entityType` and `preset` from the query string exactly like `WorkflowEditorPage` does.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/AttributeEditor.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { attributeDefinitionsApi } from "../api/attribute-definitions";
import { AttributeEditorPage } from "../components/AttributeEditor";
import {
  deleteSection,
  isMetaPropertyLocked,
  moveAttribute,
  patchAttribute,
  renameSection,
  sectionNames,
} from "../components/AttributeEditor/attribute-edits";
import type { AttributeSpec } from "../api/attribute-definitions";

vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: {
    getWorkspace: vi.fn(),
    putWorkspace: vi.fn(),
    resetWorkspace: vi.fn(),
    getGlobal: vi.fn(),
    putGlobal: vi.fn(),
  },
}));
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", preset: "standard" } }),
}));
vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({ roles: ["admin"] }),
}));

function attr(over: Partial<AttributeSpec>): AttributeSpec {
  return {
    name: "title", kind: "core", type: "text", widget_key: null, fields: [],
    options: [], required: false, visible: true, locked: false, editable: true,
    section: "general", order: 0, label: { de: "", en: "" },
    help_text: { de: "", en: "" }, default: null, validation: {},
    ai_elicit: false, export: false, audience: "basic", ...over,
  };
}

const STATUS = attr({
  name: "status", type: "enum", locked: true, editable: "workflow",
  options: [{ value: "draft", label_de: "E", label_en: "D" }],
});

describe("attribute-edits", () => {
  it("moves an attribute between sections and renumbers order", () => {
    const out = moveAttribute(
      [attr({ name: "a", order: 0 }), attr({ name: "b", section: "extra", order: 0 })],
      "a",
      "extra",
      0
    );
    const moved = out.find((a) => a.name === "a")!;
    expect(moved.section).toBe("extra");
    expect(moved.order).toBe(0);
    expect(out.find((a) => a.name === "b")!.order).toBe(1);
  });

  it("renames a section on every attribute in it", () => {
    const out = renameSection(
      [attr({ name: "a" }), attr({ name: "b" })],
      "general",
      "basics"
    );
    expect(out.every((a) => a.section === "basics")).toBe(true);
  });

  it("refuses to delete a non-empty section", () => {
    expect(() => deleteSection([attr({ name: "a" })], "general")).toThrow();
  });

  it("lists sections in first-appearance order", () => {
    expect(
      sectionNames([
        attr({ name: "a", section: "zzz" }),
        attr({ name: "b", section: "general" }),
      ])
    ).toEqual(["zzz", "general"]);
  });

  it("locks visible/required/editable on a locked attribute but not cosmetics", () => {
    expect(isMetaPropertyLocked(STATUS, "visible")).toBe(true);
    expect(isMetaPropertyLocked(STATUS, "required")).toBe(true);
    expect(isMetaPropertyLocked(STATUS, "editable")).toBe(true);
    expect(isMetaPropertyLocked(STATUS, "section")).toBe(false);
    expect(isMetaPropertyLocked(STATUS, "order")).toBe(false);
    expect(isMetaPropertyLocked(STATUS, "label")).toBe(false);
  });

  it("locks name and type on any core attribute", () => {
    const core = attr({ name: "title" });
    expect(isMetaPropertyLocked(core, "name")).toBe(true);
    expect(isMetaPropertyLocked(core, "type")).toBe(true);
    expect(isMetaPropertyLocked(attr({ name: "x", kind: "extended" }), "type")).toBe(false);
  });

  it("patches one attribute and leaves the rest untouched", () => {
    const out = patchAttribute(
      [attr({ name: "a" }), attr({ name: "b" })],
      "a",
      { audience: "expert" }
    );
    expect(out.find((x) => x.name === "a")!.audience).toBe("expert");
    expect(out.find((x) => x.name === "b")!.audience).toBe("basic");
  });
});

describe("AttributeEditorPage", () => {
  beforeEach(() => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "Requirement",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [STATUS, attr({ name: "title", order: 1 })],
    });
    vi.mocked(attributeDefinitionsApi.putWorkspace).mockReset();
    vi.mocked(attributeDefinitionsApi.resetWorkspace).mockReset();
  });

  function renderPage(scope: "workspace" | "global" = "workspace") {
    return render(
      <MemoryRouter initialEntries={["/attributes/Requirement"]}>
        <AttributeEditorPage scope={scope} />
      </MemoryRouter>
    );
  }

  it("lists the attributes grouped by section", async () => {
    renderPage();
    expect(await screen.findByTestId("attribute-row-title")).toBeInTheDocument();
    expect(screen.getByTestId("attribute-section-general")).toBeInTheDocument();
  });

  it("shows a lock icon and no toggles for a locked attribute", async () => {
    renderPage();
    await screen.findByTestId("attribute-row-status");
    expect(screen.getByTestId("attribute-row-status-lock")).toBeInTheDocument();
    expect(
      screen.queryByTestId("attribute-row-status-visible")
    ).not.toBeInTheDocument();
  });

  it("toggles audience through the expert switch", async () => {
    renderPage();
    await userEvent.click(await screen.findByTestId("attribute-row-title"));
    await userEvent.click(screen.getByTestId("attribute-inspector-audience"));
    await userEvent.click(screen.getByTestId("attribute-editor-save"));
    await waitFor(() =>
      expect(attributeDefinitionsApi.putWorkspace).toHaveBeenCalledWith(
        "ws-1",
        "Requirement",
        expect.arrayContaining([
          expect.objectContaining({ name: "title", audience: "expert" }),
        ])
      )
    );
  });

  it("resets a customized workspace definition after confirmation", async () => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "Requirement",
      preset: "standard",
      is_customized: true,
      version: 2,
      attributes: [STATUS, attr({ name: "title", order: 1 })],
    });
    vi.mocked(attributeDefinitionsApi.resetWorkspace).mockResolvedValue({
      item_type: "Requirement",
      preset: "standard",
      is_customized: false,
      version: 3,
      attributes: [STATUS],
    });
    renderPage();
    await userEvent.click(await screen.findByTestId("attribute-editor-reset"));
    await userEvent.click(screen.getByTestId("attribute-editor-reset-confirm"));
    await waitFor(() =>
      expect(attributeDefinitionsApi.resetWorkspace).toHaveBeenCalledWith(
        "ws-1",
        "Requirement"
      )
    );
  });

  it("reads and writes the global default in global scope", async () => {
    vi.mocked(attributeDefinitionsApi.getGlobal).mockResolvedValue({
      item_type: "Requirement",
      preset: "standard",
      initialized: true,
      version: 1,
      attributes: [attr({ name: "title" })],
    });
    vi.mocked(attributeDefinitionsApi.putGlobal).mockResolvedValue({
      item_type: "Requirement",
      preset: "standard",
      initialized: true,
      version: 2,
      attributes: [attr({ name: "title", audience: "expert" })],
      propagated_workspace_count: 3,
    });
    renderPage("global");
    await userEvent.click(await screen.findByTestId("attribute-row-title"));
    await userEvent.click(screen.getByTestId("attribute-inspector-audience"));
    await userEvent.click(screen.getByTestId("attribute-editor-save"));
    await waitFor(() => expect(attributeDefinitionsApi.putGlobal).toHaveBeenCalled());
    expect(await screen.findByTestId("attribute-editor-toast")).toHaveTextContent("3");
  });

  it("renames a section from its header", async () => {
    renderPage();
    await userEvent.click(await screen.findByTestId("attribute-section-general-rename"));
    const input = screen.getByTestId("attribute-section-general-name");
    await userEvent.clear(input);
    await userEvent.type(input, "basics{Enter}");
    expect(await screen.findByTestId("attribute-section-basics")).toBeInTheDocument();
    expect(screen.queryByTestId("attribute-section-general")).not.toBeInTheDocument();
  });

  it("adds an empty section and lets it be deleted again", async () => {
    renderPage();
    await userEvent.click(await screen.findByTestId("attribute-editor-add-section"));
    const input = screen.getByTestId("attribute-editor-new-section-name");
    await userEvent.type(input, "extra{Enter}");
    expect(await screen.findByTestId("attribute-section-extra")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("attribute-section-extra-delete"));
    expect(screen.queryByTestId("attribute-section-extra")).not.toBeInTheDocument();
  });

  it("refuses to delete a section that still holds attributes", async () => {
    renderPage();
    await userEvent.click(await screen.findByTestId("attribute-section-general-delete"));
    expect(await screen.findByTestId("attribute-editor-error")).toHaveTextContent(
      "not empty"
    );
    expect(screen.getByTestId("attribute-section-general")).toBeInTheDocument();
  });

  it("moves a whole section up in the sequence", async () => {
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue({
      item_type: "Requirement",
      preset: "standard",
      is_customized: false,
      version: 1,
      attributes: [
        attr({ name: "title", section: "general", order: 0 }),
        attr({ name: "uid", section: "change_control", order: 0 }),
      ],
    });
    renderPage();
    await userEvent.click(
      await screen.findByTestId("attribute-section-change_control-up")
    );
    const sections = screen.getAllByTestId(/^attribute-section-[a-z_]+$/);
    expect(sections[0]).toHaveAttribute(
      "data-testid",
      "attribute-section-change_control"
    );
  });

  it("surfaces a backend rejection instead of silently discarding the edit", async () => {
    vi.mocked(attributeDefinitionsApi.putWorkspace).mockRejectedValue(
      Object.assign(new Error("x"), {
        response: {
          data: { error: { message: "status: 'visible' is not changeable" } },
        },
      })
    );
    renderPage();
    await userEvent.click(await screen.findByTestId("attribute-row-title"));
    await userEvent.click(screen.getByTestId("attribute-inspector-audience"));
    await userEvent.click(screen.getByTestId("attribute-editor-save"));
    expect(await screen.findByTestId("attribute-editor-error")).toHaveTextContent(
      "not changeable"
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npx vitest run src/test/AttributeEditor.test.tsx`
Expected: FAIL — cannot resolve `../components/AttributeEditor`.

- [ ] **Step 3: Write the pure edit helpers**

Create `frontend/src/components/AttributeEditor/attribute-edits.ts`:

```ts
/**
 * Pure list edits for the attribute editor (spec section 6.1).
 *
 * Every function returns a NEW array — the page keeps the edited definition in
 * React state and must never mutate it in place, or the "unsaved changes"
 * comparison against the loaded definition would always read clean.
 */

import type { AttributeSpec } from "../../api/attribute-definitions";

const CORE_IMMUTABLE: ReadonlySet<keyof AttributeSpec> = new Set([
  "name",
  "type",
  "kind",
  "locked",
  "widget_key",
  "fields",
]);

const LOCKED_IMMUTABLE: ReadonlySet<keyof AttributeSpec> = new Set([
  "visible",
  "required",
  "editable",
]);

/** Sections in first-appearance order, which is the order the list renders. */
export function sectionNames(attributes: AttributeSpec[]): string[] {
  const seen: string[] = [];
  for (const attribute of attributes) {
    if (!seen.includes(attribute.section)) seen.push(attribute.section);
  }
  return seen;
}

function renumber(attributes: AttributeSpec[]): AttributeSpec[] {
  const counters = new Map<string, number>();
  return attributes.map((attribute) => {
    const next = counters.get(attribute.section) ?? 0;
    counters.set(attribute.section, next + 1);
    return { ...attribute, order: next };
  });
}

/**
 * Move `name` to position `toIndex` within `toSection`.
 *
 * A `locked` attribute is deliberately NOT exempt: only
 * visible/required/editable are frozen on it, order and section stay editable
 * because they are cosmetic (spec section 3.1).
 */
export function moveAttribute(
  attributes: AttributeSpec[],
  name: string,
  toSection: string,
  toIndex: number
): AttributeSpec[] {
  const moving = attributes.find((a) => a.name === name);
  if (!moving) return attributes;
  const rest = attributes.filter((a) => a.name !== name);
  const target = rest.filter((a) => a.section === toSection);
  const others = rest.filter((a) => a.section !== toSection);
  const clamped = Math.max(0, Math.min(toIndex, target.length));
  target.splice(clamped, 0, { ...moving, section: toSection });

  // Preserve section order: rebuild by walking the original section sequence.
  const order = sectionNames([...attributes, { ...moving, section: toSection }]);
  const rebuilt: AttributeSpec[] = [];
  for (const section of order) {
    rebuilt.push(
      ...(section === toSection ? target : others.filter((a) => a.section === section))
    );
  }
  return renumber(rebuilt);
}

export function renameSection(
  attributes: AttributeSpec[],
  from: string,
  to: string
): AttributeSpec[] {
  const clean = to.trim();
  if (!clean) throw new Error("A section name may not be empty.");
  return attributes.map((a) => (a.section === from ? { ...a, section: clean } : a));
}

/** Delete an EMPTY section. Throws when it still holds attributes. */
export function deleteSection(
  attributes: AttributeSpec[],
  name: string
): AttributeSpec[] {
  if (attributes.some((a) => a.section === name)) {
    throw new Error(`Section '${name}' is not empty.`);
  }
  return attributes;
}

/** Move a whole section to `toIndex` in the section sequence. */
export function moveSection(
  attributes: AttributeSpec[],
  name: string,
  toIndex: number
): AttributeSpec[] {
  const order = sectionNames(attributes).filter((s) => s !== name);
  const clamped = Math.max(0, Math.min(toIndex, order.length));
  order.splice(clamped, 0, name);
  const rebuilt: AttributeSpec[] = [];
  for (const section of order) {
    rebuilt.push(...attributes.filter((a) => a.section === section));
  }
  return renumber(rebuilt);
}

export function patchAttribute(
  attributes: AttributeSpec[],
  name: string,
  patch: Partial<AttributeSpec>
): AttributeSpec[] {
  return attributes.map((a) => (a.name === name ? { ...a, ...patch } : a));
}

/**
 * Whether the editor must render `property` as read-only for `attribute`.
 *
 * Mirrors the backend rules of `attribute_definitions/schema.py`
 * (`validate_meta_only_change`) so the UI never offers an edit the API will
 * reject with 400.
 */
export function isMetaPropertyLocked(
  attribute: AttributeSpec,
  property: keyof AttributeSpec
): boolean {
  if (attribute.kind === "core" && CORE_IMMUTABLE.has(property)) return true;
  if (attribute.locked && LOCKED_IMMUTABLE.has(property)) return true;
  return false;
}
```

- [ ] **Step 4: Write the list, inspector, page and CSS**

Create `frontend/src/components/AttributeEditor/AttributeEditor.module.css` with classes `.page`, `.toolbar`, `.body`, `.list`, `.section`, `.sectionHeader`, `.row`, `.rowSelected`, `.rowLocked`, `.badges`, `.inspector`, `.field`, `.control`, `.actions`, `.toast`, `.error` — all values from `styles/tokens.css`, same discipline as `ArtifactForm.module.css` (Task 16). No inline styles.

Create `frontend/src/components/AttributeEditor/AttributeList.tsx`:

```tsx
/**
 * Section + attribute list with native HTML5 drag reorder.
 *
 * Native drag events on purpose: one reorderable list does not justify a
 * drag-and-drop dependency, and the browser already gives keyboard users the
 * up/down buttons rendered alongside.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronUp, Lock } from "lucide-react";

import type { AttributeSpec } from "../../api/attribute-definitions";
import styles from "./AttributeEditor.module.css";
import { sectionNames } from "./attribute-edits";

export interface AttributeListProps {
  attributes: AttributeSpec[];
  selected: string | null;
  onSelect: (name: string) => void;
  onMove: (name: string, toSection: string, toIndex: number) => void;
  readOnly: boolean;
}

export function AttributeList({
  attributes,
  selected,
  onSelect,
  onMove,
  readOnly,
}: AttributeListProps): JSX.Element {
  const { t } = useTranslation();
  const [dragging, setDragging] = useState<string | null>(null);

  return (
    <div className={styles.list}>
      {sectionNames(attributes).map((section) => {
        const rows = attributes.filter((a) => a.section === section);
        return (
          <section
            key={section}
            className={styles.section}
            data-testid={`attribute-section-${section}`}
            onDragOver={(event) => event.preventDefault()}
            onDrop={() => {
              if (dragging && !readOnly) onMove(dragging, section, rows.length);
              setDragging(null);
            }}
          >
            <h3 className={styles.sectionHeader}>
              {t(`sections.${section}`, { defaultValue: section })}
            </h3>
            {rows.map((attribute, index) => (
              <div
                key={attribute.name}
                role="button"
                tabIndex={0}
                data-testid={`attribute-row-${attribute.name}`}
                className={`${styles.row} ${
                  selected === attribute.name ? styles.rowSelected : ""
                } ${attribute.locked ? styles.rowLocked : ""}`}
                draggable={!readOnly}
                onDragStart={() => setDragging(attribute.name)}
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  event.stopPropagation();
                  if (dragging && !readOnly) onMove(dragging, section, index);
                  setDragging(null);
                }}
                onClick={() => onSelect(attribute.name)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(attribute.name);
                  }
                }}
              >
                <span>{attribute.label.en || attribute.name}</span>
                <span className={styles.badges}>
                  {attribute.locked ? (
                    <Lock
                      aria-hidden="true"
                      size={14}
                      data-testid={`attribute-row-${attribute.name}-lock`}
                    />
                  ) : (
                    <>
                      <input
                        type="checkbox"
                        data-testid={`attribute-row-${attribute.name}-visible`}
                        checked={attribute.visible}
                        readOnly
                        aria-label={t("attributes.visible")}
                      />
                      <input
                        type="checkbox"
                        data-testid={`attribute-row-${attribute.name}-required`}
                        checked={attribute.required}
                        readOnly
                        aria-label={t("attributes.required")}
                      />
                    </>
                  )}
                  <button
                    type="button"
                    disabled={readOnly || index === 0}
                    aria-label={t("attributes.moveUp")}
                    data-testid={`attribute-row-${attribute.name}-up`}
                    onClick={(event) => {
                      event.stopPropagation();
                      onMove(attribute.name, section, index - 1);
                    }}
                  >
                    <ChevronUp aria-hidden="true" size={14} />
                  </button>
                  <button
                    type="button"
                    disabled={readOnly || index === rows.length - 1}
                    aria-label={t("attributes.moveDown")}
                    data-testid={`attribute-row-${attribute.name}-down`}
                    onClick={(event) => {
                      event.stopPropagation();
                      onMove(attribute.name, section, index + 1);
                    }}
                  >
                    <ChevronDown aria-hidden="true" size={14} />
                  </button>
                </span>
              </div>
            ))}
          </section>
        );
      })}
    </div>
  );
}
```

Create `frontend/src/components/AttributeEditor/AttributeInspector.tsx`:

```tsx
/**
 * Per-attribute meta-property editor. Every control it renders is one the
 * backend accepts for that attribute — `isMetaPropertyLocked` mirrors
 * `validate_meta_only_change`, so the UI never offers an edit that would 400.
 */

import { useTranslation } from "react-i18next";
import { Lock } from "lucide-react";

import type { AttributeSpec } from "../../api/attribute-definitions";
import styles from "./AttributeEditor.module.css";
import { isMetaPropertyLocked, sectionNames } from "./attribute-edits";

export interface AttributeInspectorProps {
  attribute: AttributeSpec;
  allAttributes: AttributeSpec[];
  onPatch: (patch: Partial<AttributeSpec>) => void;
  readOnly: boolean;
}

export function AttributeInspector({
  attribute,
  allAttributes,
  onPatch,
  readOnly,
}: AttributeInspectorProps): JSX.Element {
  const { t } = useTranslation();
  const frozen = (property: keyof AttributeSpec): boolean =>
    readOnly || isMetaPropertyLocked(attribute, property);

  return (
    <aside className={styles.inspector} data-testid="attribute-inspector">
      <h3>{attribute.name}</h3>
      {attribute.locked ? (
        <p title={t("attributes.lockedHint")}>
          <Lock aria-hidden="true" size={14} /> {t("attributes.lockedHint")}
        </p>
      ) : null}

      <label className={styles.field}>
        <span>{t("attributes.visible")}</span>
        <input
          type="checkbox"
          data-testid="attribute-inspector-visible"
          checked={attribute.visible}
          disabled={frozen("visible")}
          onChange={(event) => onPatch({ visible: event.target.checked })}
        />
      </label>

      <label className={styles.field}>
        <span>{t("attributes.required")}</span>
        <input
          type="checkbox"
          data-testid="attribute-inspector-required"
          checked={attribute.required}
          disabled={frozen("required")}
          onChange={(event) => onPatch({ required: event.target.checked })}
        />
      </label>

      <label className={styles.field}>
        <span>{t("attributes.expertOnly")}</span>
        <input
          type="checkbox"
          data-testid="attribute-inspector-audience"
          checked={attribute.audience === "expert"}
          disabled={readOnly}
          onChange={(event) =>
            onPatch({ audience: event.target.checked ? "expert" : "basic" })
          }
        />
      </label>

      <label className={styles.field}>
        <span>{t("attributes.section")}</span>
        <input
          className={styles.control}
          type="text"
          list="attribute-sections"
          data-testid="attribute-inspector-section"
          value={attribute.section}
          disabled={readOnly}
          onChange={(event) => onPatch({ section: event.target.value })}
        />
        <datalist id="attribute-sections">
          {sectionNames(allAttributes).map((section) => (
            <option key={section} value={section} />
          ))}
        </datalist>
      </label>

      <label className={styles.field}>
        <span>{t("attributes.labelDe")}</span>
        <input
          className={styles.control}
          type="text"
          data-testid="attribute-inspector-label-de"
          value={attribute.label.de}
          disabled={readOnly}
          onChange={(event) =>
            onPatch({ label: { ...attribute.label, de: event.target.value } })
          }
        />
      </label>

      <label className={styles.field}>
        <span>{t("attributes.labelEn")}</span>
        <input
          className={styles.control}
          type="text"
          data-testid="attribute-inspector-label-en"
          value={attribute.label.en}
          disabled={readOnly}
          onChange={(event) =>
            onPatch({ label: { ...attribute.label, en: event.target.value } })
          }
        />
      </label>

      <label className={styles.field}>
        <span>{t("attributes.aiElicit")}</span>
        <input
          type="checkbox"
          data-testid="attribute-inspector-ai-elicit"
          checked={attribute.ai_elicit}
          disabled={readOnly}
          onChange={(event) => onPatch({ ai_elicit: event.target.checked })}
        />
      </label>

      <label className={styles.field}>
        <span>{t("attributes.export")}</span>
        <input
          type="checkbox"
          data-testid="attribute-inspector-export"
          checked={attribute.export}
          disabled={readOnly}
          onChange={(event) => onPatch({ export: event.target.checked })}
        />
      </label>
    </aside>
  );
}
```

Create `frontend/src/components/AttributeEditor/AttributeEditorPage.tsx`:

```tsx
/**
 * AttributeEditorPage (spec section 6.1).
 *
 * Shell reused from the workflow editor: same `scope` prop, same
 * EntityTypeSelector + PresetSegmentedControl, same query-string contract in
 * global scope. Only the canvas differs — a section/attribute list instead of
 * a state machine.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams, useSearchParams } from "react-router-dom";

import {
  attributeDefinitionsApi,
  type AttributeSpec,
} from "../../api/attribute-definitions";
import { extractErrorMessage } from "../../api/client";
import type { WorkspacePreset } from "../../types";
import { useAuth } from "../../context/AuthContext";
import { useWorkspace } from "../../context/WorkspaceContext";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { EntityTypeSelector } from "../WorkflowEditor/EntityTypeSelector";
import { PresetSegmentedControl } from "../WorkflowEditor/PresetSegmentedControl";
import {
  DEFAULT_ENTITY_TYPE,
  WORKFLOW_PRESETS,
  entityTypeFromSlug,
} from "../WorkflowEditor/constants";
import styles from "./AttributeEditor.module.css";
import { AttributeInspector } from "./AttributeInspector";
import { AttributeList } from "./AttributeList";
import { moveAttribute, patchAttribute } from "./attribute-edits";

export interface AttributeEditorPageProps {
  /** `"workspace"` (default) edits the override; `"global"` the tenant default. */
  scope?: "workspace" | "global";
}

export function AttributeEditorPage({
  scope = "workspace",
}: AttributeEditorPageProps = {}): JSX.Element {
  const { t } = useTranslation();
  const isGlobal = scope === "global";
  const { entityType: entitySlug } = useParams<{ entityType: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const { activeWorkspace } = useWorkspace();
  const { roles } = useAuth();
  const isAdmin = roles.includes("admin");

  const itemType =
    entityTypeFromSlug(
      isGlobal ? searchParams.get("entityType") ?? undefined : entitySlug
    ) ?? DEFAULT_ENTITY_TYPE;
  const preset = (WORKFLOW_PRESETS.find((p) => p === searchParams.get("preset")) ??
    "standard") as WorkspacePreset;

  const [attributes, setAttributes] = useState<AttributeSpec[]>([]);
  const [loaded, setLoaded] = useState<AttributeSpec[]>([]);
  const [isCustomized, setIsCustomized] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);

  const load = useCallback(async (): Promise<void> => {
    setError(null);
    try {
      if (isGlobal) {
        const definition = await attributeDefinitionsApi.getGlobal(itemType, preset);
        setAttributes(definition.attributes);
        setLoaded(definition.attributes);
        setIsCustomized(false);
      } else {
        if (!activeWorkspace?.id) return;
        const definition = await attributeDefinitionsApi.getWorkspace(
          activeWorkspace.id,
          itemType
        );
        setAttributes(definition.attributes);
        setLoaded(definition.attributes);
        setIsCustomized(definition.is_customized);
      }
    } catch (exc: unknown) {
      setError(extractErrorMessage(exc));
    }
  }, [activeWorkspace?.id, isGlobal, itemType, preset]);

  useEffect(() => {
    void load();
  }, [load]);

  const isDirty = useMemo(
    () => JSON.stringify(attributes) !== JSON.stringify(loaded),
    [attributes, loaded]
  );

  const selectedAttribute = attributes.find((a) => a.name === selected) ?? null;

  const handleSave = useCallback(async (): Promise<void> => {
    setSaving(true);
    setError(null);
    setToast(null);
    try {
      if (isGlobal) {
        const result = await attributeDefinitionsApi.putGlobal(
          itemType,
          preset,
          attributes
        );
        setAttributes(result.attributes);
        setLoaded(result.attributes);
        if (typeof result.propagated_workspace_count === "number") {
          setToast(
            t("attributes.propagated", { count: result.propagated_workspace_count })
          );
        }
      } else if (activeWorkspace?.id) {
        const result = await attributeDefinitionsApi.putWorkspace(
          activeWorkspace.id,
          itemType,
          attributes
        );
        setAttributes(result.attributes);
        setLoaded(result.attributes);
        setIsCustomized(result.is_customized);
      }
    } catch (exc: unknown) {
      setError(extractErrorMessage(exc));
    } finally {
      setSaving(false);
    }
  }, [activeWorkspace?.id, attributes, isGlobal, itemType, preset, t]);

  const handleReset = useCallback(async (): Promise<void> => {
    if (!activeWorkspace?.id) return;
    setConfirmReset(false);
    try {
      const result = await attributeDefinitionsApi.resetWorkspace(
        activeWorkspace.id,
        itemType
      );
      setAttributes(result.attributes);
      setLoaded(result.attributes);
      setIsCustomized(result.is_customized);
    } catch (exc: unknown) {
      setError(extractErrorMessage(exc));
    }
  }, [activeWorkspace?.id, itemType]);

  return (
    <div className={styles.page} data-testid="attribute-editor">
      <div className={styles.toolbar}>
        <EntityTypeSelector
          value={itemType}
          onChange={(next) =>
            setSearchParams((params) => {
              params.set("entityType", next);
              return params;
            })
          }
        />
        {isGlobal ? (
          <PresetSegmentedControl
            value={preset}
            onChange={(next) =>
              setSearchParams((params) => {
                params.set("preset", next);
                return params;
              })
            }
          />
        ) : null}
        {!isGlobal && isCustomized ? (
          <button
            type="button"
            data-testid="attribute-editor-reset"
            disabled={!isAdmin}
            onClick={() => setConfirmReset(true)}
          >
            {t("attributes.reset")}
          </button>
        ) : null}
        <button
          type="button"
          data-testid="attribute-editor-save"
          disabled={!isAdmin || saving || !isDirty}
          onClick={() => void handleSave()}
        >
          {t("common.save")}
        </button>
      </div>

      {error ? (
        <div className={styles.error} role="alert" data-testid="attribute-editor-error">
          {error}
        </div>
      ) : null}
      {toast ? (
        <div className={styles.toast} role="status" data-testid="attribute-editor-toast">
          {toast}
        </div>
      ) : null}

      <div className={styles.body}>
        <AttributeList
          attributes={attributes}
          selected={selected}
          readOnly={!isAdmin}
          onSelect={setSelected}
          onMove={(name, toSection, toIndex) =>
            setAttributes((current) => moveAttribute(current, name, toSection, toIndex))
          }
        />
        {selectedAttribute ? (
          <AttributeInspector
            attribute={selectedAttribute}
            allAttributes={attributes}
            readOnly={!isAdmin}
            onPatch={(patch) =>
              setAttributes((current) =>
                patchAttribute(current, selectedAttribute.name, patch)
              )
            }
          />
        ) : null}
      </div>

      {confirmReset ? (
        <ConfirmDialog
          message={t("attributes.resetConfirm")}
          confirmTestId="attribute-editor-reset-confirm"
          cancelTestId="attribute-editor-reset-cancel"
          onConfirm={() => void handleReset()}
          onCancel={() => setConfirmReset(false)}
        />
      ) : null}
    </div>
  );
}
```

Create `frontend/src/components/AttributeEditor/index.ts`:

```ts
export { AttributeEditorPage } from "./AttributeEditorPage";
export type { AttributeEditorPageProps } from "./AttributeEditorPage";
export { AttributeInspector } from "./AttributeInspector";
export { AttributeList } from "./AttributeList";
```

- [ ] **Step 5: Wire section management (create, rename, delete-when-empty, reorder)**

Spec section 6.1 requires sections themselves to be manageable, not only attributes. `renameSection`, `deleteSection` and `moveSection` from Step 3 are the mutations; this step gives them a UI.

Extend `AttributeListProps` in `frontend/src/components/AttributeEditor/AttributeList.tsx`:

```tsx
export interface AttributeListProps {
  attributes: AttributeSpec[];
  /** Sections with no attributes — they exist only in editor state until a
   *  field is dragged into them, so the list must be told about them. */
  emptySections: string[];
  selected: string | null;
  onSelect: (name: string) => void;
  onMove: (name: string, toSection: string, toIndex: number) => void;
  onRenameSection: (from: string, to: string) => void;
  onDeleteSection: (name: string) => void;
  onMoveSection: (name: string, toIndex: number) => void;
  readOnly: boolean;
}
```

Add the rename state and render the header controls. Replace the `<h3 className={styles.sectionHeader}>` line with:

```tsx
            <div className={styles.sectionHeader}>
              {renaming === section ? (
                <input
                  className={styles.control}
                  data-testid={`attribute-section-${section}-name`}
                  defaultValue={section}
                  autoFocus
                  onBlur={(event) => {
                    onRenameSection(section, event.target.value);
                    setRenaming(null);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      onRenameSection(section, event.currentTarget.value);
                      setRenaming(null);
                    }
                    if (event.key === "Escape") setRenaming(null);
                  }}
                />
              ) : (
                <h3>{t(`sections.${section}`, { defaultValue: section })}</h3>
              )}
              <span className={styles.badges}>
                <button
                  type="button"
                  disabled={readOnly}
                  data-testid={`attribute-section-${section}-rename`}
                  aria-label={t("attributes.renameSection")}
                  onClick={() => setRenaming(section)}
                >
                  <Pencil aria-hidden="true" size={14} />
                </button>
                <button
                  type="button"
                  disabled={readOnly || sectionIndex === 0}
                  data-testid={`attribute-section-${section}-up`}
                  aria-label={t("attributes.moveSectionUp")}
                  onClick={() => onMoveSection(section, sectionIndex - 1)}
                >
                  <ChevronUp aria-hidden="true" size={14} />
                </button>
                <button
                  type="button"
                  disabled={readOnly || sectionIndex === allSections.length - 1}
                  data-testid={`attribute-section-${section}-down`}
                  aria-label={t("attributes.moveSectionDown")}
                  onClick={() => onMoveSection(section, sectionIndex + 1)}
                >
                  <ChevronDown aria-hidden="true" size={14} />
                </button>
                <button
                  type="button"
                  disabled={readOnly}
                  data-testid={`attribute-section-${section}-delete`}
                  aria-label={t("attributes.deleteSection")}
                  onClick={() => onDeleteSection(section)}
                >
                  <Trash2 aria-hidden="true" size={14} />
                </button>
              </span>
            </div>
```

and change the component body to iterate over the merged section list, tracking the index:

```tsx
  const [renaming, setRenaming] = useState<string | null>(null);
  const allSections = useMemo(
    () => [...sectionNames(attributes), ...emptySections.filter(
      (s) => !sectionNames(attributes).includes(s)
    )],
    [attributes, emptySections]
  );
  // ...
      {allSections.map((section, sectionIndex) => {
```

Add `Pencil` and `Trash2` to the `lucide-react` import and `useMemo` to the React import.

In `frontend/src/components/AttributeEditor/AttributeEditorPage.tsx` add the empty-section state and the three handlers, and a toolbar button to create one:

```tsx
  const [emptySections, setEmptySections] = useState<string[]>([]);
  const [newSection, setNewSection] = useState<string | null>(null);

  const handleRenameSection = useCallback((from: string, to: string): void => {
    setError(null);
    try {
      setAttributes((current) => renameSection(current, from, to));
      setEmptySections((current) =>
        current.map((s) => (s === from ? to.trim() : s)).filter(Boolean)
      );
    } catch (exc: unknown) {
      setError(exc instanceof Error ? exc.message : String(exc));
    }
  }, []);

  const handleDeleteSection = useCallback((name: string): void => {
    setError(null);
    try {
      // Throws when the section still holds attributes — spec section 6.1
      // allows deleting an EMPTY section only.
      setAttributes((current) => deleteSection(current, name));
      setEmptySections((current) => current.filter((s) => s !== name));
    } catch (exc: unknown) {
      setError(exc instanceof Error ? exc.message : String(exc));
    }
  }, []);

  const handleMoveSection = useCallback((name: string, toIndex: number): void => {
    setAttributes((current) => moveSection(current, name, toIndex));
  }, []);
```

Import `deleteSection`, `moveSection`, `renameSection` alongside `moveAttribute` and `patchAttribute`.

Add the create-section control to the toolbar, before the Save button:

```tsx
        {newSection === null ? (
          <button
            type="button"
            data-testid="attribute-editor-add-section"
            disabled={!isAdmin}
            onClick={() => setNewSection("")}
          >
            {t("attributes.addSection")}
          </button>
        ) : (
          <input
            className={styles.control}
            data-testid="attribute-editor-new-section-name"
            value={newSection}
            autoFocus
            onChange={(event) => setNewSection(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && newSection.trim()) {
                setEmptySections((current) => [...current, newSection.trim()]);
                setNewSection(null);
              }
              if (event.key === "Escape") setNewSection(null);
            }}
          />
        )}
```

and pass the new props to `AttributeList`:

```tsx
        <AttributeList
          attributes={attributes}
          emptySections={emptySections}
          selected={selected}
          readOnly={!isAdmin}
          onSelect={setSelected}
          onMove={(name, toSection, toIndex) =>
            setAttributes((current) => moveAttribute(current, name, toSection, toIndex))
          }
          onRenameSection={handleRenameSection}
          onDeleteSection={handleDeleteSection}
          onMoveSection={handleMoveSection}
        />
```

An empty section is intentionally editor-local state: it only reaches the backend once an attribute carries its name, because `definition_json` stores sections as a property of attributes, not as their own list. Deleting an empty section therefore never needs a save.

- [ ] **Step 6: Mount the routes and the settings tabs**

In `frontend/src/components/NavigationShell/NavigationShell.tsx`, next to the `/workflows` routes:

```tsx
              <Route path="/attributes" element={<AttributeEditorPage />} />
              <Route
                path="/attributes/:entityType"
                element={<AttributeEditorPage />}
              />
```

with `import { AttributeEditorPage } from "../AttributeEditor";`.

In `frontend/src/components/SystemSettings/SystemSettings.tsx` add an "Attribute Defaults" tab rendering `<AttributeEditorPage scope="global" />`, next to the existing workflow-defaults tab. In `frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx` add an "Attributes" tab rendering `<AttributeEditorPage />`.

- [ ] **Step 7: Add the i18n keys**

Add a nested `attributes` object to both locale files:

de: `"visible": "Sichtbar"`, `"required": "Pflicht"`, `"expertOnly": "Nur für Experten"`, `"section": "Sektion"`, `"labelDe": "Label (DE)"`, `"labelEn": "Label (EN)"`, `"aiElicit": "Im Interview abfragen"`, `"export": "Exportieren"`, `"lockedHint": "systemkritisch, nicht änderbar"`, `"moveUp": "Nach oben"`, `"moveDown": "Nach unten"`, `"addSection": "Sektion anlegen"`, `"renameSection": "Sektion umbenennen"`, `"deleteSection": "Sektion löschen"`, `"moveSectionUp": "Sektion nach oben"`, `"moveSectionDown": "Sektion nach unten"`, `"reset": "Auf Standard zurücksetzen"`, `"resetConfirm": "Workspace-Anpassungen verwerfen und den globalen Standard übernehmen?"`, `"propagated": "{{count}} Workspace(s) aktualisiert"`.

en: the same keys with `"Visible"`, `"Required"`, `"Expert only"`, `"Section"`, `"Label (DE)"`, `"Label (EN)"`, `"Elicit in interview"`, `"Export"`, `"system-critical, not changeable"`, `"Move up"`, `"Move down"`, `"Add section"`, `"Rename section"`, `"Delete section"`, `"Move section up"`, `"Move section down"`, `"Reset to default"`, `"Discard the workspace customisation and adopt the global default?"`, `"{{count}} workspace(s) updated"`.

- [ ] **Step 8: Run test to verify it passes**

Run: `docker compose exec frontend npx vitest run src/test/AttributeEditor.test.tsx src/test/i18n-parity.test.ts --testTimeout=30000`
Expected: PASS (17 tests + i18n parity)

- [ ] **Step 9: Verify the ratchets**

Run: `docker compose exec frontend npx vitest run src/test/ui-ratchet.test.ts src/test/design-tokens.test.ts --testTimeout=30000`
Expected: PASS with `STYLE_BRACE_BASELINE` unchanged — this task adds no inline styles.

- [ ] **Step 10: Verify in the browser**

`docker compose restart frontend`, then: open `/attributes`, drag an attribute to another section, rename a section, create an empty section and delete it again, reorder two sections, toggle "Expert only", save, reload and confirm it persisted; open System Settings → Attribute Defaults, edit the global for `Requirement/standard`, save and confirm the propagation toast names a workspace count; back in the workspace editor, press Reset and confirm the override disappears.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/components/AttributeEditor frontend/src/components/NavigationShell frontend/src/components/SystemSettings frontend/src/components/WorkspaceSettings frontend/src/i18n/locales frontend/src/test/AttributeEditor.test.tsx
git commit -m "feat(attribute-definitions): add attribute editor page"
```

---

### Task 27: Remove the legacy frontend configuration UI

Closes the migration: the old admin surface and the custom-field editors have no backend left after Task 9.

**Files:**
- Delete: `frontend/src/api/attribute-visibility.ts`, `frontend/src/api/custom-fields.ts`
- Delete: `frontend/src/components/AdminDialog/AttributeVisibilityAdmin.tsx`
- Delete: `frontend/src/components/shared/CustomFieldsEditor.tsx`, `CustomFieldsDisplay.tsx`, `ArtifactCustomFields.tsx`
- Delete: `frontend/src/test/ArtifactCustomFields.test.tsx`, `frontend/src/test/CustomFieldsEditor.test.tsx`
- Modify: `frontend/src/api/index.ts` (drop the two exports)
- Modify: `frontend/src/context/EntityTypeContext.tsx` (drop the `AttributeVisibilityConfig` type and any state feeding it)
- Modify: `frontend/src/components/AdminDialog/*` (drop the tab that hosted the removed admin panel)
- Modify: `frontend/src/test/ui-ratchet.test.ts:335`
- Test: `frontend/src/test/legacy-field-config-removed.test.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — this task only removes.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/legacy-field-config-removed.test.ts`:

```ts
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = resolve(__dirname, "..");

function collect(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...collect(full));
    else if (/\.tsx?$/.test(entry)) out.push(full);
  }
  return out;
}

describe("legacy field-config surface is gone", () => {
  const files = collect(SRC);

  it("has no module referencing the removed API wrappers", () => {
    const offenders = files.filter((file) => {
      const source = readFileSync(file, "utf-8");
      return (
        source.includes("attributeVisibilityApi") ||
        source.includes("customFieldsApi") ||
        source.includes("AttributeVisibilityAdmin")
      );
    });
    expect(offenders).toEqual([]);
  });

  it("has no module importing the removed custom-field components", () => {
    const offenders = files.filter((file) => {
      const source = readFileSync(file, "utf-8");
      return (
        source.includes("CustomFieldsEditor") ||
        source.includes("CustomFieldsDisplay") ||
        source.includes("ArtifactCustomFields")
      );
    });
    expect(offenders).toEqual([]);
  });

  it("has no module still importing a deleted artifact form", () => {
    const deleted = [
      "RiskForm",
      "IssueForm",
      "AdrForm",
      "TestCaseForm",
      "NeedForm",
      "ArchitectureForm",
      "RequirementForm",
    ];
    const offenders = files.filter((file) => {
      const source = readFileSync(file, "utf-8");
      return deleted.some((name) =>
        new RegExp(`from ['"][^'"]*/${name}['"]`).test(source)
      );
    });
    expect(offenders).toEqual([]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend npx vitest run src/test/legacy-field-config-removed.test.ts`
Expected: FAIL — the offender lists are non-empty.

- [ ] **Step 3: Delete the files**

```bash
git rm frontend/src/api/attribute-visibility.ts \
       frontend/src/api/custom-fields.ts \
       frontend/src/components/AdminDialog/AttributeVisibilityAdmin.tsx \
       frontend/src/components/shared/CustomFieldsEditor.tsx \
       frontend/src/components/shared/CustomFieldsDisplay.tsx \
       frontend/src/components/shared/ArtifactCustomFields.tsx \
       frontend/src/test/ArtifactCustomFields.test.tsx \
       frontend/src/test/CustomFieldsEditor.test.tsx
```

- [ ] **Step 4: Remove the references**

- `frontend/src/api/index.ts`: delete the `attributeVisibilityApi` and `customFieldsApi` export lines.
- `frontend/src/context/EntityTypeContext.tsx`: delete the `AttributeVisibilityConfig` interface and every state/effect that populated it. Custom fields now arrive through the resolved attribute definition, so no context plumbing replaces it.
- `frontend/src/components/AdminDialog/`: remove the tab entry and route that mounted `AttributeVisibilityAdmin`; if that leaves the dialog with a single tab, keep the tab strip — a later spec adds tabs back and churn there is not free.

- [ ] **Step 5: Check the E2E specs**

Run: `grep -rn "attribute-visibility\|custom-field" e2e/`
Expected: delete the specs that exercised the removed admin panel and rewrite any custom-field assertion onto `artifact-field-<name>` in the section the definition assigns (`custom` by default after the Task 8 migration).

- [ ] **Step 6: Re-measure and lower the inline-style baseline**

Run: `docker compose exec frontend npx vitest run src/test/ui-ratchet.test.ts --testTimeout=30000`, then set `STYLE_BRACE_BASELINE` to the reported count.

- [ ] **Step 7: Run the full frontend suite and the type check**

Run:
```bash
docker compose exec frontend npx vitest run --testTimeout=30000
docker compose exec frontend npx tsc --noEmit
```
Expected: the vitest run is green apart from the pre-existing local failures (roughly 14 suites that are green in CI but red locally — compare against a pre-change baseline rather than assuming they are new). `tsc --noEmit` must be clean: it is the only place a dangling import of a deleted module surfaces, because the frontend CI job does not run it.

- [ ] **Step 8: Commit**

```bash
git add -A frontend e2e
git commit -m "refactor(attribute-definitions): remove legacy field-configuration UI"
```

---

## Rollout notes

- **Order is load-bearing.** Tasks 1-7 build the model and the facade; Task 8 migrates data while the legacy tables still exist; Task 9 drops them. Running Task 9 before Task 8 loses every `CustomFieldValue`.
- **Task 8 requires the dry run** against a copy of the production database (spec section 10) before Task 9 is merged.
- **Tasks 19-25 must keep their order** (Risk, Issue → ADR, TestCase, Need, Architecture → Requirement). Each one may surface a special case that needs a new `widget_key`; registering one is a small addition to Task 17's registry plus `WIDGET_KEYS` in `attribute_definitions/schema.py`, and it delays only that form.
- **The full Playwright suite is not part of any task's definition of done.** Targeted `--grep` runs are used per task to verify moved test ids; CI runs the full matrix on every PR.

