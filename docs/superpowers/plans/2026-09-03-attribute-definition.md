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

---

## Decisions

**D1 — `AttributeDefinitionService.validate_artifact_fields` keeps the spec's exact 5-argument signature.** Create-vs-update semantics are carried by `existing is None` (create) rather than by a sixth flag, because the spec, the Tabellenansicht spec (§3.1) and the Rollenbasierte-Sichten spec all quote the 5-argument form verbatim.

**D2 — `version` is the inherited `AuditableModel.version`,** not a redeclared field (see P3). Both stores bump it explicitly on every persist, so the REST/MCP payloads still expose a monotonically increasing `version` as the spec's §9 requires.

**D3 — `CustomFieldValue.definition` (FK) becomes `attribute_name` (CharField).** The spec says "`CustomFieldValue` stays unchanged (values, not definition)" *and* "`CustomFieldDefinition` … is removed (not just deprecated)". Those two are not simultaneously satisfiable: `CustomFieldValue.definition` is a `ForeignKey` to `CustomFieldDefinition`, so dropping the target table orphans the column. Resolution: the values are preserved, the *link* changes from a row FK to the attribute `name` that now lives in `definition_json`. Uniqueness moves from `(definition, artifact)` to `(artifact, attribute_name)`. This is the minimum change that satisfies "definition lives only in the JSON" while losing no values.

**D4 — The resolved definition is cached in `django.core.cache` under `reqogniloom:attribute-def:{workspace_id}:{item_type}`,** and `attribute_def_cache_key` is added to `application/cache_invalidation.py::_workspace_keys`. This reuses the existing cross-worker invalidation instead of adding a fourth module-level dict.

**D5 — The MCP group follows `mcp_server/tools/custom_field.py`,** because the `workflow.*` group the spec names does not exist (see P2).

**D6 — The bootstrap injects a synthetic `status` core attribute instead of introspecting a status column** (see P1). Consequence: the bootstrap output is stable across the Datenmodell-Konsolidierung migration, but the `status` attribute's `options[]` stays empty — the renderer reads the concrete states from the workflow definition, which is already the single source of truth for them.

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

<!-- PLAN-APPEND-ANCHOR -->
