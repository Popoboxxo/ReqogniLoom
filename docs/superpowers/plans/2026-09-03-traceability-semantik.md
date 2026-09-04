# Traceability-Semantik Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded 15-value `LinkType` enum and the `se_mode`-gated `SE_LINK_SEMANTICS` matrix with a tenant-configurable link-type catalog (`GlobalLinkTypeDefinition` → `WorkspaceLinkTypeDefinition`) seeded with 8 cleaned-up core types, always-on endpoint validation, and a rule-driven suspect-propagation engine.

**Architecture:** A new Layer-1 Django app `backend/link_types/` holds the catalog using the exact materialized-copy inheritance pattern of `workflow.GlobalWorkflowDefinition`/`WorkflowEngineDefinition` (per-workspace copy, `source_global` FK, `is_customized` flag, propagate-on-global-edit, cache-generation invalidation). `TraceLinkService.create_trace_link` stops calling `check_se_link_semantics` and instead resolves the workspace catalog and validates every link unconditionally. `TraceLink` gains `rationale`/`suspect_flagged_at`/`suspect_source_change`, and `propagate_suspect_status` is rewritten from an unconditional transitive upstream flood into a one-hop dispatch on each link type's `suspect_rule`.

**Tech Stack:** Django 5.2 / Python 3.x, PostgreSQL 16 (JSONB + RLS), DRF + drf-spectacular, native MCP tool registry, React 18 + TypeScript 5.5 (strict), pytest, vitest.

**Spec:** docs/superpowers/specs/2026-09-03-traceability-semantik-design.md

## Global Constraints

- The 8 seeded core types are exactly: `derives-from`, `decomposes`, `allocated-to`, `verifies`, `decides`, `mitigates`, `references`, `diagram-ref`. `parent-child` is dropped; `copy-of` becomes the `Artifact.copied_from` field.
- Endpoint validation gilt **immer** — the `se_mode` gate and the `SE_CORE_ARTIFACT_TYPES` "non-core types pass unchecked" escape are removed **ersatzlos**.
- `suspect_rule` is a fixed four-value enum verankert im Code: `"none"`, `"target_change_flags_source"`, `"source_change_flags_target"`, `"parent_change_flags_children"`. Tenants pick from these; new propagation logic is a code change.
- Everything else in `definition_json` is tenant-free: `allowed_pairs`, `label`, `coverage_relevant`, `impact_weight`, `active`.
- Inheritance is **materialized copy, kein Merge-on-Read** — an admin edit on a global row propagates into all `is_customized=False` workspace rows. Cache invalidation follows the `presets/gate.py:_invalidate_workspace` pattern.
- Kein `preset`-Feld on the link-type models — link types are an open named catalog, not an `(item_type × preset)` raster.
- `system_owned` is true only for `diagram-ref`: `key` and `manual_creatable` are locked, same lock concept as `locked` attributes in the Attribut-Definition spec.
- `active` is a soft-disable (`default true`) — never hard-delete a link type.
- MCP: `link_type` in `traceability.create_link`'s `inputSchema` becomes a **free string**, not an enum; validation is server-side against the resolved catalog and the error message lists the valid values.
- Frontend: the hardcoded `LinkType` union in `types/index.ts` is replaced by a read against `GET workspaces/<id>/link-type-definitions/`. No second independently maintained source of truth.
- `Artifact.parent` stays as the recursive-CTE performance cache but is written **in derselben Transaktion** as its `decomposes` link.
- Impact weights: `derives-from` 1.0, `decomposes` 1.0, `allocated-to` 1.0, `verifies` 1.0, `decides` 0.3, `mitigates` 0.5, `references` 0.2, `diagram-ref` 0.2.
- Coverage-relevant: only `allocated-to` (Allocation-Coverage) and `verifies` (Test-Coverage).
- Migration is hart (kein Dual-Write, keine Kompatibilitäts-Aliase): `satisfies`/`implements` → `allocated-to` **mit getauschter Quelle/Ziel**, `refines` → `derives-from`, `realizes` → `decomposes`, `documents`/`traces`/`uses-term` → `references`, `parent-child` entfällt (dedupliziert gegen `decomposes`), `copy-of` → `Artifact.copied_from`.

---

## Verified Against Current Code (2026-09-03)

Read before starting — the spec was written earlier and four of its claims have drifted:

| Spec claim | Reality | Consequence for this plan |
|---|---|---|
| `TraceLink` has only `source`/`target`/`link_type`/`embedding` (`persistence/models.py:1352`) | Confirmed | Task 12 adds the three new fields |
| §3.3 "Ein Unique-Constraint auf `(source, target, link_type='decomposes')` verhindert Duplikate" | **Already exists** — `uq_tracelink_edge` on `(source, target, link_type)` (models.py:1402, issue #126) covers it | No constraint work. Task 16 only deduplicates *data*. |
| §5 "#849: `suspect` fehlt im Serializer" | **Already fixed** in commit `54b09760` — `rest_api/serializers.py:753` declares `suspect = serializers.BooleanField(read_only=True)` | Only the propagation half of #849 remains (Task 14) |
| §5 implies suspect propagation is missing | `TraceLinkService.propagate_suspect_status` **exists and is wired** (`requirement_service.py:501`), but ignores `link_type` entirely and floods the whole transitive upstream hull | Task 14 is a **rewrite**, not a new feature; its 4 existing tests (`application/tests/test_trace_link_service.py:955-1073`) must be rewritten |
| `SE_LINK_SEMANTICS` constrains all types | Only 9 of 15 types are in the matrix; `decomposes`, `decides`, `traces`, `realizes`, `uses-term`, `diagram-ref` are absent = unrestricted | The catalog replaces the matrix wholesale |
| §3.2 `references` targets `GlossaryTerm`/`Icd` | **Neither is Artifact-backed today** (no `artifact` FK on `persistence.GlossaryTerm` or `icd.Icd`); `TraceLink.source/target` are FKs to `Artifact`, so such a link cannot physically exist | Delivered by Plan #1 (Datenmodell-Konsolidierung §4). Ordering dependency, not a blocker — Task 5's pairs are declared as data and simply never match until those Artifact rows exist. |

**Direction conventions (authoritative, from `traceability/audit/hierarchy.py:20-33`):**

| link type | source | target |
|---|---|---|
| `decomposes` | parent (the decomposed) | child (the result) |
| `parent-child` | parent | child |
| `derives-from` | child (the derived) | parent (the origin) |

`derives-from` is the **inverse** edge of `decomposes`. Every direction decision in this plan follows this table.

**Blast radius — hardcoded link-type consumers that must move with the migration (all verified by grep, non-test):**

| File | What breaks |
|---|---|
| `backend/traceability/vcrm_report_generator.py:205` | raw SQL `AND tl.link_type IN ('satisfies', 'implements')` — silently returns 0 rows after the rename, and the direction swap inverts the join |
| `backend/traceability/audit/hierarchy.py:82` | `_DECOMPOSITION_LINK_TYPES = {DECOMPOSES, PARENT_CHILD}` |
| `backend/traceability/audit/rules/trace_derivation_allocation.py:387` | `frozenset({LinkType.SATISFIES.value, LinkType.IMPLEMENTS.value})` |
| `backend/mcp_server/tools/cross_cutting.py:1334` | **emits** a synthetic `"link_type": "parent-child"` for ArchitectureElement children |
| `backend/persistence/models.py:717` | `Workspace.decomposition_link_type` default `"parent-child"` (functionally dead since `requirement_service.py:863` hardcodes `DECOMPOSES`, but still writable via REST/MCP/UI) |
| `backend/rest_api/serializers.py:1311` | serializer default `"parent-child"`; `views.py:4162` fallback `"parent-child"` |
| `frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx:653` | live dropdown offering `parent-child` |
| `backend/application/interview_multi_protocol.py:43` | LLM prompt enumerating the 15 old types |
| `backend/application/reqif_export_service.py:69` | ReqIF `SRT-<link_type>` identifier list |
| `backend/application/management/commands/migrate_se_docs.py:205` | `_LINK_IMPLEMENTS = LinkType.IMPLEMENTS.value` |
| `backend/auth_tenancy/management/commands/seed_toothbrush.py:227` | seeds a `"satisfies"` link |
| `frontend/src/constants/traceLinkLabels.ts` | `LINK_TYPE_TRI_LABELS` + `ALL_LINK_TYPES`, consumed by **16** files |

---

## OFFENE FRAGEN (blocking — decide before Task 9 / Task 16)

### OFFENE FRAGE 1 — Always-on validation breaks link types the seeded catalog does not mention

The spec's 8-type matrix covers `Requirement`, `ArchitectureElement`, `TestCase`, `StakeholderNeed`, `Adr`, `Risk`, `Diagram`, `GlossaryTerm`, `Icd`, `ExternalRef`. It covers **none** of `Goal`, `MainGoal`, `Issue`, `Interview` — all four are live `artifact_type` values with real `Artifact` rows. `Goal ↔ Requirement` links in particular are a shipped feature: `TraceLinkService._resolve_artifact` step 5 was added by **fix #237** precisely because "any Goal<->Requirement trace link raised 'Entity not found'".

Today those links are legal (permissive fallback). The moment validation "gilt immer", every one of them is rejected and every existing row becomes uncreatable.

**Default chosen so the plan stays executable (Task 9 + Task 10):** *grandfathering by inventory*. A management command inventories the distinct `(link_type, source_artifact_type, target_artifact_type)` triples that actually exist, maps them through the 3.1 rename table, and the seed migration **extends** the built-in `allowed_pairs` with every observed triple not already covered — logging each addition loudly. Existing data stays valid; genuinely new invalid combinations are rejected.

**Needs a decision:** is grandfathering acceptable, or should Goal/MainGoal/Issue/Interview links be hard-rejected (breaking change, needs a data cleanup first)?

### OFFENE FRAGE 2 — `refines` → `derives-from` changes SE-Auditor root/leaf classification

`traceability/audit/hierarchy.py:35-38` states explicitly: *"`refines` ist deliberately **not** treated as a hierarchy edge: it expresses 'same requirement, more detail' on one level, not decomposition onto the next one, and `SE_LINK_SEMANTICS` allows it symmetrically between Requirements, so its direction carries no level semantics."*

`derives-from` **is** a hierarchy edge (child→parent) and is read by the root/leaf classifier. Folding `refines` into `derives-from` therefore turns every symmetric `refines` edge into a directed hierarchy edge whose direction is arbitrary — silently changing TRACE-P1 ("root must derive from a StakeholderNeed") and VERIF-P8 ("leaf must have a verifying TestCase") findings for every affected requirement pair.

**Default chosen (Task 16 + Task 17):** migrate as the spec says (direction preserved: source stays source), but the migration **counts and reports** every `Requirement→Requirement` `refines` row it converts, and Task 17 re-runs the SE-Auditor before/after on a seeded workspace and diffs the finding set, so the semantic change is observed rather than assumed.

**Needs a decision:** accept the classification change, or exclude `Requirement↔Requirement` `refines` rows from the merge (e.g. map them to `references` instead, losing the refinement semantics)?

---

## Decisions Taken (non-blocking, documented)

1. **`suspect_source_change` is a `UUIDField`, not a `ForeignKey`.** The spec says "FK auf `AuditEntry`". `audit/migrations/0001_initial.py:12` documents that `al_audit_entry`/`audit_entry` is *intended* for monthly RANGE partitioning ("not applied by this migration — production partitioning setup via DBA / separate DDL script"). A real FK would permanently block that plan (Postgres requires the partition key in the referenced PK), nothing else in the codebase FKs to `AuditEntry`, and the table is append-only so no cascade semantics are needed. Stored as the plain audit-entry UUID with a docstring naming the reference.
2. **`parent_change_flags_children` dispatches to the same branch as `source_change_flags_target`.** Given the direction table, for `decomposes` the parent *is* the source, so the two are functionally identical. The value is kept as a distinct configurable enum member because the spec's four-value range is a Global Constraint and because it documents hierarchy intent, but the engine has one branch, not two duplicated ones.
3. **`definition_json.label` is the tri-label shape, a superset of the spec's `{de, en}`.** The frontend's single source for link-type display is `constants/traceLinkLabels.ts::LINK_TYPE_TRI_LABELS`, which requires `{de: {downstream, upstream, neutral}, en: {...}}` per type — a flat `{de, en}` pair cannot express it and would silently break 16 components. Label shape is therefore `{de: {downstream, upstream, neutral}, en: {downstream, upstream, neutral}}`.
4. **Suspect propagation becomes one-hop.** Spec §5 describes a single hop ("markiert das jeweils andere Ende suspect"); today's implementation walks the full transitive upstream closure. One-hop is implemented as specified; `settings.SUSPECT_PROPAGATION_MAX_DEPTH` becomes unused and its handling is deleted with the old body. This is a **behaviour narrowing** and is called out in the Task 14 commit message.
5. **`proposed_by`/`proposed_at` are NOT in this plan's migration.** The KI-Vorschlag spec §5 says they run "in derselben Migration wie die `rationale`/`suspect_*`-Felder" — impossible across plan boundaries, since Plan #4 executes after Plan #3. This plan owns `link_types/…` + `persistence/00XX_tracelink_semantics_fields`; Plan #4 adds its own migration on the same model.
6. **`references` target list is data, never a hardcoded 3-tuple.** `allowed_pairs` is a plain JSON list of `{source_type, target_type}` objects with `"*"` wildcards, so Plan #8 adds `ExternalRef` by appending one row to the seed constant plus a data migration — no code change in the validator.
7. **Bootstrap is a code-level `BUILTIN_LINK_TYPES` constant plus a backfill migration plus a provisioning hook**, not a bare seed migration. `GlobalWorkflowDefinition` proves the shape: rows are `TenantScopedModel` under RLS, so a single blind `INSERT` in a data migration cannot serve future tenants. The constant is the SSOT, the migration backfills existing tenants, `provision_workspace_defaults` serves new ones.

---

## File Structure

### New — `backend/link_types/` (Layer 1)

| File | Responsibility |
|---|---|
| `backend/link_types/__init__.py` | empty package marker |
| `backend/link_types/apps.py` | `LinkTypesConfig` AppConfig (`name = "link_types"`) |
| `backend/link_types/models.py` | `GlobalLinkTypeDefinition`, `WorkspaceLinkTypeDefinition` (both `TenantScopedModel`) |
| `backend/link_types/builtin.py` | `BUILTIN_LINK_TYPES` — the 8 seeded definitions as plain dicts; `SUSPECT_RULES` enum-ish frozenset; SSOT for seed + backfill + provisioning |
| `backend/link_types/schema.py` | `validate_definition_json(payload) -> dict` — shape/range validation for a `definition_json` (raises `persistence.errors.ValidationError`) |
| `backend/link_types/catalog.py` | `resolve_catalog(workspace_id, tenant_id) -> dict[str, dict]` (cached), `invalidate_workspace(workspace_id)`, `validate_link_pair(...)` |
| `backend/link_types/global_store.py` | `GlobalLinkTypeDefinitionStore` — list/get/create/update/delete + `_propagate` into non-customized workspace rows |
| `backend/link_types/workspace_store.py` | `WorkspaceLinkTypeDefinitionStore` — resolved list/get, `update` (sets `is_customized=True`), `reset`, `provision_workspace_link_types` |
| `backend/link_types/migrations/0001_initial.py` | the two models |
| `backend/link_types/migrations/0002_rls_policies.py` | `ENABLE/FORCE ROW LEVEL SECURITY` + tenant policy on `lt_global_definition`, `lt_workspace_definition` (byte-identical to `workflow/0015`) |
| `backend/link_types/migrations/0003_seed_builtin_link_types.py` | backfill: one global + per-workspace row set per existing tenant, from `BUILTIN_LINK_TYPES` + the inventory grandfathering file |
| `backend/link_types/migrations/_seed_helpers.py` | `seed_tenant(tenant_id, workspace_ids)` — seeding logic outside the numbered migration so it is testable |
| `backend/link_types/migrations/0004_grandfather_observed_pairs.py` | applies `grandfathered.py` to the seeded rows |
| `backend/link_types/grandfathered.py` | `GRANDFATHERED_PAIRS` + `apply_grandfathered_pairs` — endpoint pairs that exist in live data but no built-in type allows (OFFENE FRAGE 1) |
| `backend/link_types/migration_ops.py` | `find_copy_of_conflicts`, `migrate_copy_of_links`, `migrate_parent_child_links`, `migrate_renamed_links` — the hard TraceLink migration as testable functions |
| `backend/link_types/management/commands/inventory_link_types.py` | prints/writes observed `(link_type, source_type, target_type)` triples for OFFENE FRAGE 1 |
| `backend/link_types/management/commands/check_copy_of_conflicts.py` | preflight for the `copy-of` → `copied_from` 1:1 narrowing |
| `backend/link_types/management/commands/diff_auditor_findings.py` | snapshots/diffs SE-Auditor finding counts around the migration (OFFENE FRAGE 2) |
| `backend/application/link_type_facade.py` | `LinkTypeFacade` — the Layer-2 seam (ADR-01) both transports go through; guarantees JSON-primitive payloads |
| `backend/link_types/tests/test_models.py` … `test_workspace_store.py` | per-task test modules (named in each task) |

### Modified — backend

| File | Change |
|---|---|
| `backend/reqogniloom/settings.py:212` | add `"link_types"` to `INSTALLED_APPS` after `"workflow"` |
| `backend/persistence/models.py:1360-1406` | `TraceLink`: add `rationale`, `suspect_flagged_at`, `suspect_source_change` |
| `backend/persistence/models.py:819-860` | `Artifact`: add `copied_from` self-FK |
| `backend/persistence/models.py:715-724` | `Workspace.decomposition_link_type` default `parent-child` → `decomposes`; `default_link_type` unchanged (`derives-from` survives) |
| `backend/persistence/migrations/00XX_tracelink_semantics_fields.py` | new — the three `TraceLink` fields + `Artifact.copied_from` + the two `Workspace` defaults |
| `backend/persistence/migrations/00XX_migrate_trace_link_types.py` | new — the §3.1 data migration (rename, direction swap, dedup, `copy-of` move) |
| `backend/traceability/types.py:25-177` | delete `SE_LINK_SEMANTICS`, `SE_CORE_ARTIFACT_TYPES`, `SAME_TYPE`, `check_se_link_semantics`; shrink `LinkType` to the 8 core values as a **convenience** enum only (no longer the validation authority) |
| `backend/application/trace_link_service.py:258-333` | delete `_check_se_semantics`, replace with `_check_link_pair` calling `link_types.catalog.validate_link_pair` |
| `backend/application/trace_link_service.py:366-385` | replace the `VALID_LINK_TYPES` / `DIAGRAM_REF` hardcoded gates with catalog lookups (`active`, `manual_creatable`) |
| `backend/application/trace_link_service.py:1175-1251` | rewrite `propagate_suspect_status` into the rule-driven one-hop engine |
| `backend/application/requirement_service.py:900-930` | write `Artifact.parent` in the same transaction as the `decomposes` link |
| `backend/traceability/vcrm_report_generator.py:205` | `IN ('satisfies','implements')` → `= 'allocated-to'` with swapped join direction |
| `backend/traceability/audit/hierarchy.py:82` | `_DECOMPOSITION_LINK_TYPES` → `{DECOMPOSES}` |
| `backend/traceability/audit/rules/trace_derivation_allocation.py:387` | `{SATISFIES, IMPLEMENTS}` → `{ALLOCATED_TO}` |
| `backend/mcp_server/tools/cross_cutting.py:1334` | synthetic `"parent-child"` → `"decomposes"` |
| `backend/mcp_server/tools/cross_cutting.py:285-293` | `link_type` schema `enum` → free `"type": "string"` |
| `backend/mcp_server/tools/link_type.py` | new — MCP group `link_type.{list,get,create,update,reset}` |
| `backend/mcp_server/tool_registry.py` | register the new group |
| `backend/rest_api/link_type_views.py` | new — global + workspace link-type endpoints |
| `backend/rest_api/urls.py` | register `link-type-defaults/…` and `workspaces/<uuid:workspace_id>/link-type-definitions/…` |
| `backend/rest_api/serializers.py:1035` | `TraceLinkSerializer`: add `rationale`, `suspect_flagged_at`, `suspect_source_change` |
| `backend/rest_api/serializers.py:1311` | `decomposition_link_type` default → `"decomposes"` |
| `backend/rest_api/views.py:4162` | fallback `"parent-child"` → `"decomposes"` |
| `backend/application/interview_multi_protocol.py:43` | prompt link-type list → catalog-derived |
| `backend/application/reqif_export_service.py:69` | docstring + type list |
| `backend/application/management/commands/migrate_se_docs.py:205` | `_LINK_IMPLEMENTS` → `allocated-to` with swapped endpoints |
| `backend/auth_tenancy/management/commands/seed_toothbrush.py:227` | `"satisfies"` → `"allocated-to"` with swapped endpoints |
| `backend/application/workspace_provisioning.py:62` | call `provision_workspace_link_types` |

### Modified — frontend

| File | Change |
|---|---|
| `frontend/src/api/link-types.ts` | new — `linkTypesApi.{listForWorkspace, updateForWorkspace, resetForWorkspace, listGlobal, createGlobal, updateGlobal, deleteGlobal}` plus the `LinkTypeDefinition`/`WorkspaceLinkType`/`TriLabel`/`LinkTypePair`/`SuspectRule` types |
| `frontend/src/types/index.ts:265-278` | delete the hardcoded `LinkType` union; `LinkType` becomes `string`; add `LinkTypeDefinition` interface |
| `frontend/src/context/LinkTypeContext.tsx` | new — loads + caches the resolved catalog per active workspace, exposes `useLinkTypes()` |
| `frontend/src/constants/traceLinkLabels.ts` | `LINK_TYPE_TRI_LABELS`/`ALL_LINK_TYPES` become catalog-derived helpers; the hardcoded table survives only as `FALLBACK_TRI_LABELS` for the pre-load render |
| `frontend/src/components/shared/CreateTraceLinkDialog/create-trace-link-dialog.tsx:591` | options from the catalog, filtered by `allowed_pairs` against the chosen source/target types |
| `frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx:653,677` | both dropdowns fed from the catalog |
| `frontend/src/components/LinkTypeEditor/LinkTypeEditorPage.tsx` | new — global (`/system-settings`) + workspace (`/settings`) editor |
| `frontend/src/i18n/locales/{de,en}.json` | `linkType.*` keys |

---

## Running the tests

Every `Run:` line below abbreviates the backend test invocation as `$PYTEST`. Expand it to:

```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml \
  --project-directory . run --rm -e DB_NAME=test_lt_$$ backend-test \
  pytest --create-db
```

`-e DB_NAME=test_lt_$$` gives this run its own database — concurrent backend-test runs otherwise share `test_reqogniloom` and produce hundreds of phantom setup errors. `--create-db` is required because the database is recreated per run.

Frontend: `$VITEST` = `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm frontend-test npx vitest run --testTimeout=30000`.

**Do not** run the full backend suite per task — only the module(s) each task names. CI runs the full matrix.

After any frontend source edit, restart the frontend container before running Playwright: Vite has no working HMR on Windows and E2E otherwise silently tests stale code.

---

## Phase A — Catalog foundation

### Task 1: `link_types` app scaffold and models

**Files:**
- Create: `backend/link_types/__init__.py`
- Create: `backend/link_types/apps.py`
- Create: `backend/link_types/models.py`
- Create: `backend/link_types/migrations/__init__.py`
- Create: `backend/link_types/migrations/0001_initial.py` (generated)
- Create: `backend/link_types/tests/__init__.py`
- Modify: `backend/reqogniloom/settings.py:212` (INSTALLED_APPS)
- Test: `backend/link_types/tests/test_models.py`

**Interfaces:**
- Consumes: `persistence.models.TenantScopedModel`
- Produces: `link_types.models.GlobalLinkTypeDefinition(key, definition_json, version)`; `link_types.models.WorkspaceLinkTypeDefinition(workspace_id, key, definition_json, source_global, is_customized, version)`; db tables `lt_global_definition`, `lt_workspace_definition`; unique constraints `uq_lt_global_tenant_key`, `uq_lt_ws_tenant_ws_key`

- [ ] **Step 1: Write the failing test**

```python
# backend/link_types/tests/test_models.py
"""LinkTypeCatalog — model-level invariants."""
from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, transaction

from link_types.models import GlobalLinkTypeDefinition, WorkspaceLinkTypeDefinition
from persistence.tenancy import TenantContext


@pytest.fixture
def tenant_id():
    tid = uuid.uuid4()
    TenantContext.set_tenant(tid)
    yield tid
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_global_key_is_unique_per_tenant(tenant_id):
    GlobalLinkTypeDefinition.objects.create(key="derives-from", definition_json={})
    with pytest.raises(IntegrityError), transaction.atomic():
        GlobalLinkTypeDefinition.objects.create(key="derives-from", definition_json={})


@pytest.mark.django_db
def test_workspace_key_is_unique_per_workspace(tenant_id):
    ws = uuid.uuid4()
    WorkspaceLinkTypeDefinition.objects.create(
        workspace_id=ws, key="verifies", definition_json={}
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        WorkspaceLinkTypeDefinition.objects.create(
            workspace_id=ws, key="verifies", definition_json={}
        )


@pytest.mark.django_db
def test_same_key_allowed_in_a_second_workspace(tenant_id):
    WorkspaceLinkTypeDefinition.objects.create(
        workspace_id=uuid.uuid4(), key="verifies", definition_json={}
    )
    obj = WorkspaceLinkTypeDefinition.objects.create(
        workspace_id=uuid.uuid4(), key="verifies", definition_json={}
    )
    assert obj.pk is not None


@pytest.mark.django_db
def test_deleting_the_global_row_nulls_the_link_but_keeps_the_workspace_row(tenant_id):
    g = GlobalLinkTypeDefinition.objects.create(key="mitigates", definition_json={})
    w = WorkspaceLinkTypeDefinition.objects.create(
        workspace_id=uuid.uuid4(),
        key="mitigates",
        definition_json={},
        source_global=g,
    )
    g.delete()
    w.refresh_from_db()
    assert w.source_global_id is None
    assert w.is_customized is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST link_types/tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'link_types'`

- [ ] **Step 3: Write minimal implementation**

`backend/link_types/__init__.py` and `backend/link_types/tests/__init__.py` and `backend/link_types/migrations/__init__.py` are empty files.

```python
# backend/link_types/apps.py
"""App configuration for the LinkTypeCatalog (Layer 1)."""
from django.apps import AppConfig


class LinkTypesConfig(AppConfig):
    """Tenant-configurable trace-link type catalog.

    Layer 1, alongside ``workflow``: owns the global and per-workspace
    link-type definitions that ``application.trace_link_service`` validates
    every TraceLink against. Replaces the hardcoded ``traceability.types``
    ``SE_LINK_SEMANTICS`` matrix and its ``se_mode`` gate.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "link_types"
    verbose_name = "LinkTypeCatalog"
```

```python
# backend/link_types/models.py
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
"""
from __future__ import annotations

from django.db import models

from persistence.models import TenantScopedModel


class GlobalLinkTypeDefinition(TenantScopedModel):
    """Tenant-wide link-type template. Exactly one row per ``(tenant, key)``.

    ``key`` is either one of the eight built-in keys or a tenant-invented one
    (e.g. ``"conflicts-with"``). ``version`` is the optimistic-lock counter.
    """

    key = models.CharField(max_length=64)
    definition_json = models.JSONField(default=dict)
    version = models.IntegerField(default=1)

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
    version = models.IntegerField(default=1)

    class Meta:
        db_table = "lt_workspace_definition"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "workspace_id", "key"],
                name="uq_lt_ws_tenant_ws_key",
            )
        ]
        indexes = [
            models.Index(
                fields=["workspace_id", "key"], name="idx_lt_ws_workspace_key"
            )
        ]

    def __str__(self) -> str:
        return f"WorkspaceLinkType({self.key}@{self.workspace_id})"
```

Add to `backend/reqogniloom/settings.py` immediately after the `"workflow",` line:

```python
    "link_types",          # LinkTypeCatalog — configurable trace-link semantics
```

Generate the migration:

```bash
docker compose -f deploy/docker-compose.yml --project-directory . run --rm backend \
  python manage.py makemigrations link_types --name initial
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST link_types/tests/test_models.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/link_types backend/reqogniloom/settings.py
git commit -m "feat(link-types): add LinkTypeCatalog app with global/workspace definitions"
```

---

### Task 2: RLS policies for the `lt_*` tables

**Files:**
- Create: `backend/link_types/migrations/0002_rls_policies.py`
- Test: `backend/link_types/tests/test_rls_policies.py`

**Interfaces:**
- Consumes: `link_types.models.GlobalLinkTypeDefinition`, `WorkspaceLinkTypeDefinition` (Task 1)
- Produces: DB policies `lt_global_definition_tenant_isolation`, `lt_workspace_definition_tenant_isolation`

Both models are `TenantScopedModel` subclasses; without this migration they ship with exactly the RLS gap `workflow/0015` was written to close.

- [ ] **Step 1: Write the failing test**

```python
# backend/link_types/tests/test_rls_policies.py
"""RLS isolation for lt_global_definition / lt_workspace_definition."""
from __future__ import annotations

import uuid

import pytest
from django.db import connection

_TABLES = ["lt_global_definition", "lt_workspace_definition"]


@pytest.mark.django_db
@pytest.mark.parametrize("table", _TABLES)
def test_row_level_security_is_enabled_and_forced(table):
    with connection.cursor() as cur:
        cur.execute(
            "SELECT relrowsecurity, relforcerowsecurity "
            "FROM pg_class WHERE relname = %s",
            [table],
        )
        enabled, forced = cur.fetchone()
    assert enabled is True, f"{table}: RLS not enabled"
    assert forced is True, f"{table}: RLS not forced"


@pytest.mark.django_db
@pytest.mark.parametrize("table", _TABLES)
def test_tenant_isolation_policy_exists(table):
    with connection.cursor() as cur:
        cur.execute(
            "SELECT polname FROM pg_policy p "
            "JOIN pg_class c ON c.oid = p.polrelid WHERE c.relname = %s",
            [table],
        )
        names = {row[0] for row in cur.fetchall()}
    assert f"{table}_tenant_isolation" in names


@pytest.mark.django_db
def test_rows_of_another_tenant_are_invisible():
    from link_types.models import GlobalLinkTypeDefinition
    from persistence.tenancy import TenantContext

    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    TenantContext.set_tenant(tenant_a)
    GlobalLinkTypeDefinition.objects.create(key="verifies", definition_json={})
    assert GlobalLinkTypeDefinition.objects.filter(key="verifies").count() == 1

    TenantContext.set_tenant(tenant_b)
    assert GlobalLinkTypeDefinition.objects.filter(key="verifies").count() == 0
    TenantContext.clear_tenant()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST link_types/tests/test_rls_policies.py -v`
Expected: FAIL — `assert False is True` on `relrowsecurity` for both tables

- [ ] **Step 3: Write minimal implementation**

```python
# backend/link_types/migrations/0002_rls_policies.py
"""COMP-PL-006 RLSPolicyEnforcer — RLS for the ``lt_*`` LinkTypeCatalog tables.

Both LinkTypeCatalog models are ``TenantScopedModel`` subclasses carrying a
``tenant_id`` UUID column, so this migration is purely additive DDL. Policy
semantics are byte-identical to ``persistence/0003`` and ``workflow/0015``:
ENABLE + FORCE ROW LEVEL SECURITY plus one ``ALL`` policy keyed on the session
variable ``app.current_tenant``. An unset/empty setting matches no rows
(REQ-L2-PL-010).

Access-path review: every read of these tables goes through
``link_types.catalog.resolve_catalog``, which is only ever called from
request-scoped services where ``TenantContextService.activate`` has already
armed both isolation layers, and from the seed/backfill migration, which runs
under the migration role and arms the tenant explicitly per tenant row.
"""
from __future__ import annotations

from django.db import migrations

_TENANT_TABLES = ["lt_global_definition", "lt_workspace_definition"]


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
        ("link_types", "0001_initial"),
        ("persistence", "0003_rls_policies"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST link_types/tests/test_rls_policies.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/link_types/migrations/0002_rls_policies.py backend/link_types/tests/test_rls_policies.py
git commit -m "feat(link-types): enforce row-level security on lt_* catalog tables"
```

---

### Task 3: `BUILTIN_LINK_TYPES` — the eight seeded definitions

**Files:**
- Create: `backend/link_types/builtin.py`
- Test: `backend/link_types/tests/test_builtin.py`

**Interfaces:**
- Consumes: nothing (pure data module — deliberately import-free so migrations can import it without app-registry side effects)
- Produces:
  - `SUSPECT_RULES: frozenset[str]` = `{"none", "target_change_flags_source", "source_change_flags_target", "parent_change_flags_children"}`
  - `BUILTIN_LINK_TYPES: dict[str, dict]` — key → `definition_json`
  - `LEGACY_LINK_TYPE_MAPPING: dict[str, str | None]` — old key → new key (`None` = dropped)
  - `SWAPPED_LEGACY_KEYS: frozenset[str]` = `{"satisfies", "implements"}`
  - `builtin_definition(key: str) -> dict` — deep copy, so no caller can mutate the module constant

- [ ] **Step 1: Write the failing test**

```python
# backend/link_types/tests/test_builtin.py
"""The eight built-in link types are the spec's Startbelegung, verbatim."""
from __future__ import annotations

from link_types.builtin import (
    BUILTIN_LINK_TYPES,
    LEGACY_LINK_TYPE_MAPPING,
    SUSPECT_RULES,
    SWAPPED_LEGACY_KEYS,
    builtin_definition,
)

EXPECTED_KEYS = {
    "derives-from",
    "decomposes",
    "allocated-to",
    "verifies",
    "decides",
    "mitigates",
    "references",
    "diagram-ref",
}


def test_exactly_the_eight_core_types_are_seeded():
    assert set(BUILTIN_LINK_TYPES) == EXPECTED_KEYS


def test_suspect_rules_are_the_four_code_anchored_values():
    assert SUSPECT_RULES == {
        "none",
        "target_change_flags_source",
        "source_change_flags_target",
        "parent_change_flags_children",
    }


def test_only_allocated_to_and_verifies_are_coverage_relevant():
    coverage = {k for k, v in BUILTIN_LINK_TYPES.items() if v["coverage_relevant"]}
    assert coverage == {"allocated-to", "verifies"}


def test_impact_weights_match_the_spec_table():
    weights = {k: v["impact_weight"] for k, v in BUILTIN_LINK_TYPES.items()}
    assert weights == {
        "derives-from": 1.0,
        "decomposes": 1.0,
        "allocated-to": 1.0,
        "verifies": 1.0,
        "decides": 0.3,
        "mitigates": 0.5,
        "references": 0.2,
        "diagram-ref": 0.2,
    }


def test_suspect_rules_match_the_spec_table():
    rules = {k: v["suspect_rule"] for k, v in BUILTIN_LINK_TYPES.items()}
    assert rules == {
        "derives-from": "target_change_flags_source",
        "decomposes": "parent_change_flags_children",
        "allocated-to": "source_change_flags_target",
        "verifies": "target_change_flags_source",
        "decides": "none",
        "mitigates": "none",
        "references": "none",
        "diagram-ref": "none",
    }


def test_diagram_ref_is_the_only_system_owned_and_non_manual_type():
    system_owned = {k for k, v in BUILTIN_LINK_TYPES.items() if v["system_owned"]}
    non_manual = {k for k, v in BUILTIN_LINK_TYPES.items() if not v["manual_creatable"]}
    assert system_owned == {"diagram-ref"}
    assert non_manual == {"diagram-ref"}


def test_allocated_to_is_requirement_to_architecture_only():
    pairs = BUILTIN_LINK_TYPES["allocated-to"]["allowed_pairs"]
    assert pairs == [{"source_type": "Requirement", "target_type": "ArchitectureElement"}]


def test_derives_from_gained_the_architecture_pair_from_refines():
    pairs = BUILTIN_LINK_TYPES["derives-from"]["allowed_pairs"]
    assert {"source_type": "ArchitectureElement", "target_type": "ArchitectureElement"} in pairs


def test_references_targets_are_a_list_not_a_fixed_triple():
    targets = [
        p["target_type"] for p in BUILTIN_LINK_TYPES["references"]["allowed_pairs"]
    ]
    assert targets == ["GlossaryTerm", "Diagram", "Icd"]
    assert all(
        p["source_type"] == "*" for p in BUILTIN_LINK_TYPES["references"]["allowed_pairs"]
    )


def test_every_definition_carries_tri_labels_in_both_languages():
    for key, definition in BUILTIN_LINK_TYPES.items():
        for lang in ("de", "en"):
            assert set(definition["label"][lang]) == {
                "downstream",
                "upstream",
                "neutral",
            }, f"{key}/{lang} is missing a tri-label perspective"


def test_every_definition_is_active_and_flagged_built_in():
    assert all(v["active"] for v in BUILTIN_LINK_TYPES.values())
    assert all(v["built_in"] for v in BUILTIN_LINK_TYPES.values())


def test_legacy_mapping_covers_every_retired_key():
    assert LEGACY_LINK_TYPE_MAPPING == {
        "parent-child": None,
        "satisfies": "allocated-to",
        "implements": "allocated-to",
        "refines": "derives-from",
        "realizes": "decomposes",
        "documents": "references",
        "traces": "references",
        "uses-term": "references",
        "copy-of": None,
    }
    assert SWAPPED_LEGACY_KEYS == {"satisfies", "implements"}


def test_builtin_definition_returns_an_isolated_copy():
    first = builtin_definition("verifies")
    first["impact_weight"] = 99.0
    assert BUILTIN_LINK_TYPES["verifies"]["impact_weight"] == 1.0
    assert builtin_definition("verifies")["impact_weight"] == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST link_types/tests/test_builtin.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'link_types.builtin'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/link_types/builtin.py
"""The eight built-in link types — Startbelegung of the tenant catalog.

Single source of truth for three consumers that must never drift apart:
the seed/backfill migration (``0003_seed_builtin_link_types``), workspace
provisioning (``link_types.workspace_store.provision_workspace_link_types``),
and the tests that pin the spec table.

This module is deliberately import-free (no Django, no models) so a migration
can import it without triggering app-registry side effects.

Direction conventions, authoritative for every ``allowed_pairs`` entry below
(see ``traceability/audit/hierarchy.py``)::

    decomposes     source = parent (the decomposed)   target = child
    derives-from   source = child (the derived)       target = parent
    allocated-to   source = Requirement               target = ArchitectureElement
    verifies       source = TestCase                  target = Requirement/Arch
    mitigates      source = Risk                      target = Requirement/Arch
    decides        source = Adr                       target = anything
    references     source = anything                  target = a reference entity
    diagram-ref    source = Diagram                   target = anything

``"*"`` is a wildcard on either side.
"""
from __future__ import annotations

import copy
from typing import Any

#: The four propagation behaviours the suspect engine can dispatch on. This is
#: the one part of a definition a tenant may only *choose* from, never extend:
#: ``application.trace_link_service.TraceLinkService.propagate_suspect_status``
#: branches on the value, so a new behaviour is a code change (spec section 4,
#: "Grenze — suspect_rule ist kein freier Code").
SUSPECT_RULES: frozenset[str] = frozenset(
    {
        "none",
        "target_change_flags_source",
        "source_change_flags_target",
        "parent_change_flags_children",
    }
)

#: Old link-type key -> new key. ``None`` means the type is retired without a
#: successor (``parent-child`` is deduplicated into ``decomposes`` by the data
#: migration; ``copy-of`` moves into ``Artifact.copied_from``).
LEGACY_LINK_TYPE_MAPPING: dict[str, str | None] = {
    "parent-child": None,
    "satisfies": "allocated-to",
    "implements": "allocated-to",
    "refines": "derives-from",
    "realizes": "decomposes",
    "documents": "references",
    "traces": "references",
    "uses-term": "references",
    "copy-of": None,
}

#: Legacy keys whose rows must have source and target swapped when migrated.
#: ``satisfies`` was ArchitectureElement -> Requirement and ``implements`` was
#: ArchitectureElement -> Requirement; ``allocated-to`` runs the other way
#: (Requirement -> ArchitectureElement), so the endpoints move with the rename.
SWAPPED_LEGACY_KEYS: frozenset[str] = frozenset({"satisfies", "implements"})


def _pairs(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"source_type": s, "target_type": t} for s, t in pairs]


BUILTIN_LINK_TYPES: dict[str, dict[str, Any]] = {
    "derives-from": {
        "label": {
            "de": {
                "downstream": "leitet sich ab von",
                "upstream": "ist Grundlage für",
                "neutral": "Ableitung",
            },
            "en": {
                "downstream": "derives from",
                "upstream": "is basis for",
                "neutral": "Derivation",
            },
        },
        # Arch<->Arch is new here: it arrives from the retired `refines` type.
        "allowed_pairs": _pairs(
            ("Requirement", "Requirement"),
            ("Requirement", "StakeholderNeed"),
            ("StakeholderNeed", "StakeholderNeed"),
            ("ArchitectureElement", "ArchitectureElement"),
        ),
        "coverage_relevant": False,
        "suspect_rule": "target_change_flags_source",
        "impact_weight": 1.0,
        "manual_creatable": True,
        "system_owned": False,
        "active": True,
        "built_in": True,
    },
    "decomposes": {
        "label": {
            "de": {
                "downstream": "zerlegt sich in",
                "upstream": "ist Teil von",
                "neutral": "Zerlegung",
            },
            "en": {
                "downstream": "decomposes into",
                "upstream": "is part of",
                "neutral": "Decomposition",
            },
        },
        "allowed_pairs": _pairs(
            ("Requirement", "Requirement"),
            ("ArchitectureElement", "ArchitectureElement"),
        ),
        "coverage_relevant": False,
        "suspect_rule": "parent_change_flags_children",
        "impact_weight": 1.0,
        "manual_creatable": True,
        "system_owned": False,
        "active": True,
        "built_in": True,
    },
    "allocated-to": {
        "label": {
            "de": {
                "downstream": "ist zugewiesen an",
                "upstream": "erfüllt",
                "neutral": "Zuweisung",
            },
            "en": {
                "downstream": "is allocated to",
                "upstream": "fulfils",
                "neutral": "Allocation",
            },
        },
        # Arch->Arch is deliberately gone: it duplicated `decomposes`.
        "allowed_pairs": _pairs(("Requirement", "ArchitectureElement")),
        "coverage_relevant": True,
        "suspect_rule": "source_change_flags_target",
        "impact_weight": 1.0,
        "manual_creatable": True,
        "system_owned": False,
        "active": True,
        "built_in": True,
    },
    "verifies": {
        "label": {
            "de": {
                "downstream": "verifiziert",
                "upstream": "wird verifiziert von",
                "neutral": "Verifikation",
            },
            "en": {
                "downstream": "verifies",
                "upstream": "is verified by",
                "neutral": "Verification",
            },
        },
        "allowed_pairs": _pairs(
            ("TestCase", "Requirement"),
            ("TestCase", "ArchitectureElement"),
        ),
        "coverage_relevant": True,
        "suspect_rule": "target_change_flags_source",
        "impact_weight": 1.0,
        "manual_creatable": True,
        "system_owned": False,
        "active": True,
        "built_in": True,
    },
    "decides": {
        "label": {
            "de": {
                "downstream": "entscheidet über",
                "upstream": "wird entschieden durch",
                "neutral": "Entscheidung",
            },
            "en": {
                "downstream": "decides",
                "upstream": "is decided by",
                "neutral": "Decision",
            },
        },
        "allowed_pairs": _pairs(("Adr", "*")),
        "coverage_relevant": False,
        "suspect_rule": "none",
        "impact_weight": 0.3,
        "manual_creatable": True,
        "system_owned": False,
        "active": True,
        "built_in": True,
    },
    "mitigates": {
        "label": {
            "de": {
                "downstream": "mindert",
                "upstream": "wird gemindert durch",
                "neutral": "Risikominderung",
            },
            "en": {
                "downstream": "mitigates",
                "upstream": "is mitigated by",
                "neutral": "Mitigation",
            },
        },
        "allowed_pairs": _pairs(
            ("Risk", "Requirement"),
            ("Risk", "ArchitectureElement"),
        ),
        "coverage_relevant": False,
        "suspect_rule": "none",
        "impact_weight": 0.5,
        "manual_creatable": True,
        "system_owned": False,
        "active": True,
        "built_in": True,
    },
    "references": {
        "label": {
            "de": {
                "downstream": "verweist auf",
                "upstream": "wird referenziert von",
                "neutral": "Verweis",
            },
            "en": {
                "downstream": "references",
                "upstream": "is referenced by",
                "neutral": "Reference",
            },
        },
        # Replaces documents/traces/uses-term. The target list is data, not a
        # fixed triple: the GitHub/Jira spec appends {"*", "ExternalRef"} here
        # with a one-row data migration and no validator change. GlossaryTerm
        # and Icd only become reachable once the Datenmodell-Konsolidierung
        # spec has given them Artifact rows — until then the pair simply never
        # matches, which is inert, not an error.
        "allowed_pairs": _pairs(
            ("*", "GlossaryTerm"),
            ("*", "Diagram"),
            ("*", "Icd"),
        ),
        "coverage_relevant": False,
        "suspect_rule": "none",
        "impact_weight": 0.2,
        "manual_creatable": True,
        "system_owned": False,
        "active": True,
        "built_in": True,
    },
    "diagram-ref": {
        "label": {
            "de": {
                "downstream": "stellt dar",
                "upstream": "wird dargestellt in",
                "neutral": "Diagrammbezug",
            },
            "en": {
                "downstream": "depicts",
                "upstream": "is depicted in",
                "neutral": "Diagram reference",
            },
        },
        "allowed_pairs": _pairs(("Diagram", "*")),
        "coverage_relevant": False,
        "suspect_rule": "none",
        "impact_weight": 0.2,
        # Reconciler-owned (diagram.traceability_connector.sync_node_links).
        # A hand-authored one is silently deleted on the diagram's next
        # node_graph save, which looks like unexplained data loss.
        "manual_creatable": False,
        "system_owned": True,
        "active": True,
        "built_in": True,
    },
}


def builtin_definition(key: str) -> dict[str, Any]:
    """Return a deep copy of the built-in definition for *key*.

    Always a copy: the seed migration, provisioning and the reset endpoint all
    persist the result, and a shared mutable reference would let one tenant's
    edit leak into another's row.

    Raises:
        KeyError: *key* is not a built-in type.
    """
    return copy.deepcopy(BUILTIN_LINK_TYPES[key])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST link_types/tests/test_builtin.py -v`
Expected: PASS (13 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/link_types/builtin.py backend/link_types/tests/test_builtin.py
git commit -m "feat(link-types): define the eight built-in link-type definitions"
```

---

### Task 4: `definition_json` schema validation

**Files:**
- Create: `backend/link_types/schema.py`
- Test: `backend/link_types/tests/test_schema.py`

**Interfaces:**
- Consumes: `link_types.builtin.SUSPECT_RULES`
- Produces: `validate_definition_json(payload: dict, *, key: str) -> dict` — returns the normalized definition, raises `persistence.errors.ValidationError` with a message naming the offending field and the valid values

- [ ] **Step 1: Write the failing test**

```python
# backend/link_types/tests/test_schema.py
"""definition_json shape/range validation for tenant-authored link types."""
from __future__ import annotations

import pytest

from link_types.builtin import builtin_definition
from link_types.schema import validate_definition_json
from persistence.errors import ValidationError


def _minimal() -> dict:
    return {
        "label": {
            "de": {"downstream": "a", "upstream": "b", "neutral": "c"},
            "en": {"downstream": "a", "upstream": "b", "neutral": "c"},
        },
        "allowed_pairs": [{"source_type": "Requirement", "target_type": "Risk"}],
        "coverage_relevant": False,
        "suspect_rule": "none",
        "impact_weight": 0.5,
        "manual_creatable": True,
        "system_owned": False,
        "active": True,
        "built_in": False,
    }


def test_every_builtin_definition_validates():
    for key in (
        "derives-from",
        "decomposes",
        "allocated-to",
        "verifies",
        "decides",
        "mitigates",
        "references",
        "diagram-ref",
    ):
        assert validate_definition_json(builtin_definition(key), key=key)


def test_unknown_suspect_rule_is_rejected_and_lists_the_valid_values():
    payload = _minimal()
    payload["suspect_rule"] = "flag_everything"
    with pytest.raises(ValidationError) as exc:
        validate_definition_json(payload, key="conflicts-with")
    message = str(exc.value)
    assert "suspect_rule" in message
    assert "parent_change_flags_children" in message


def test_negative_impact_weight_is_rejected():
    payload = _minimal()
    payload["impact_weight"] = -0.1
    with pytest.raises(ValidationError, match="impact_weight"):
        validate_definition_json(payload, key="conflicts-with")


def test_allowed_pairs_must_be_objects_with_both_sides():
    payload = _minimal()
    payload["allowed_pairs"] = [{"source_type": "Requirement"}]
    with pytest.raises(ValidationError, match="target_type"):
        validate_definition_json(payload, key="conflicts-with")


def test_allowed_pairs_may_be_empty_meaning_the_type_links_nothing_yet():
    payload = _minimal()
    payload["allowed_pairs"] = []
    assert validate_definition_json(payload, key="conflicts-with")["allowed_pairs"] == []


def test_missing_label_language_is_rejected():
    payload = _minimal()
    del payload["label"]["en"]
    with pytest.raises(ValidationError, match="label"):
        validate_definition_json(payload, key="conflicts-with")


def test_missing_label_perspective_is_rejected():
    payload = _minimal()
    del payload["label"]["de"]["neutral"]
    with pytest.raises(ValidationError, match="neutral"):
        validate_definition_json(payload, key="conflicts-with")


def test_optional_flags_default_when_absent():
    payload = _minimal()
    for optional in ("coverage_relevant", "manual_creatable", "system_owned", "active", "built_in"):
        del payload[optional]
    result = validate_definition_json(payload, key="conflicts-with")
    assert result["coverage_relevant"] is False
    assert result["manual_creatable"] is True
    assert result["system_owned"] is False
    assert result["active"] is True
    assert result["built_in"] is False


def test_unknown_top_level_field_is_rejected():
    payload = _minimal()
    payload["propagation_script"] = "flag(x)"
    with pytest.raises(ValidationError, match="propagation_script"):
        validate_definition_json(payload, key="conflicts-with")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST link_types/tests/test_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'link_types.schema'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/link_types/schema.py
"""Shape and range validation for a link type's ``definition_json``.

``definition_json`` is tenant-authored (a Tenant-Admin can invent
``conflicts-with`` from the UI or MCP), so it is an untrusted payload on a
trust boundary and gets validated on every write path — the REST views, the
MCP tools and the provisioning/reset helpers all funnel through
:func:`validate_definition_json`.

The only closed value range is ``suspect_rule``: the propagation engine
branches on it, so an unknown value would silently do nothing. Everything
else (``allowed_pairs``, ``label``, ``coverage_relevant``, ``impact_weight``,
``active``) is free.
"""
from __future__ import annotations

from typing import Any

from persistence.errors import ValidationError

from .builtin import SUSPECT_RULES

_LANGS = ("de", "en")
_PERSPECTIVES = ("downstream", "upstream", "neutral")

#: field -> default applied when the caller omits it.
_OPTIONAL_DEFAULTS: dict[str, Any] = {
    "coverage_relevant": False,
    "manual_creatable": True,
    "system_owned": False,
    "active": True,
    "built_in": False,
}

_REQUIRED = ("label", "allowed_pairs", "suspect_rule", "impact_weight")
_KNOWN = set(_REQUIRED) | set(_OPTIONAL_DEFAULTS)


def validate_definition_json(payload: Any, *, key: str) -> dict[str, Any]:
    """Validate and normalize one link-type definition.

    Args:
        payload: The raw ``definition_json`` mapping.
        key: The link-type key, used only to make error messages locatable.

    Returns:
        A new dict with every optional field filled in and
        ``allowed_pairs`` normalized to ``[{"source_type", "target_type"}]``.

    Raises:
        ValidationError: Any shape or range violation. The message names the
            offending field and, for closed ranges, lists the valid values.
    """
    if not isinstance(payload, dict):
        raise ValidationError(f"Link type '{key}': definition must be an object.")

    unknown = sorted(set(payload) - _KNOWN)
    if unknown:
        raise ValidationError(
            f"Link type '{key}': unknown field(s) {', '.join(unknown)}. "
            f"Allowed: {', '.join(sorted(_KNOWN))}."
        )

    missing = [field for field in _REQUIRED if field not in payload]
    if missing:
        raise ValidationError(
            f"Link type '{key}': missing required field(s) {', '.join(missing)}."
        )

    result: dict[str, Any] = dict(_OPTIONAL_DEFAULTS)
    result.update({k: v for k, v in payload.items() if k in _OPTIONAL_DEFAULTS})

    result["label"] = _validate_label(payload["label"], key=key)
    result["allowed_pairs"] = _validate_pairs(payload["allowed_pairs"], key=key)
    result["suspect_rule"] = _validate_suspect_rule(payload["suspect_rule"], key=key)
    result["impact_weight"] = _validate_weight(payload["impact_weight"], key=key)

    for flag in ("coverage_relevant", "manual_creatable", "system_owned", "active", "built_in"):
        if not isinstance(result[flag], bool):
            raise ValidationError(f"Link type '{key}': '{flag}' must be a boolean.")

    return result


def _validate_label(label: Any, *, key: str) -> dict[str, dict[str, str]]:
    """Tri-label: {de,en} x {downstream,upstream,neutral}, all strings.

    The tri-label shape (not a flat ``{de, en}`` pair) is what the frontend's
    single display source, ``constants/traceLinkLabels.ts``, consumes.
    """
    if not isinstance(label, dict):
        raise ValidationError(f"Link type '{key}': 'label' must be an object.")
    out: dict[str, dict[str, str]] = {}
    for lang in _LANGS:
        entry = label.get(lang)
        if not isinstance(entry, dict):
            raise ValidationError(
                f"Link type '{key}': 'label' is missing the '{lang}' object."
            )
        out[lang] = {}
        for perspective in _PERSPECTIVES:
            value = entry.get(perspective)
            if not isinstance(value, str) or not value.strip():
                raise ValidationError(
                    f"Link type '{key}': label.{lang}.{perspective} must be a "
                    f"non-empty string."
                )
            out[lang][perspective] = value
    return out


def _validate_pairs(pairs: Any, *, key: str) -> list[dict[str, str]]:
    """``[{"source_type": str, "target_type": str}]``; ``"*"`` is a wildcard.

    An empty list is legal and means "this type currently links nothing" —
    the sane state for a freshly invented type before its pairs are filled in.
    """
    if not isinstance(pairs, list):
        raise ValidationError(f"Link type '{key}': 'allowed_pairs' must be a list.")
    out: list[dict[str, str]] = []
    for index, pair in enumerate(pairs):
        if not isinstance(pair, dict):
            raise ValidationError(
                f"Link type '{key}': allowed_pairs[{index}] must be an object."
            )
        for side in ("source_type", "target_type"):
            value = pair.get(side)
            if not isinstance(value, str) or not value.strip():
                raise ValidationError(
                    f"Link type '{key}': allowed_pairs[{index}].{side} must be a "
                    f"non-empty string (artifact type or '*')."
                )
        out.append(
            {
                "source_type": pair["source_type"],
                "target_type": pair["target_type"],
            }
        )
    return out


def _validate_suspect_rule(rule: Any, *, key: str) -> str:
    if rule not in SUSPECT_RULES:
        raise ValidationError(
            f"Link type '{key}': unknown suspect_rule '{rule}'. "
            f"Valid values: {', '.join(sorted(SUSPECT_RULES))}. "
            f"New propagation behaviour requires a code change."
        )
    return str(rule)


def _validate_weight(weight: Any, *, key: str) -> float:
    if isinstance(weight, bool) or not isinstance(weight, (int, float)):
        raise ValidationError(f"Link type '{key}': 'impact_weight' must be a number.")
    if weight < 0:
        raise ValidationError(
            f"Link type '{key}': 'impact_weight' must be >= 0 (got {weight})."
        )
    return float(weight)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST link_types/tests/test_schema.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/link_types/schema.py backend/link_types/tests/test_schema.py
git commit -m "feat(link-types): validate tenant-authored definition_json payloads"
```

---

### Task 5: Catalog resolver and `validate_link_pair`

**Files:**
- Create: `backend/link_types/catalog.py`
- Test: `backend/link_types/tests/test_catalog.py`

**Interfaces:**
- Consumes: `link_types.models.WorkspaceLinkTypeDefinition` (Task 1), `link_types.builtin.BUILTIN_LINK_TYPES` (Task 3), `persistence.cache_generation.{cache_generation, bump_cache_generation}`
- Produces:
  - `resolve_catalog(workspace_id: UUID | str) -> dict[str, dict]` — key → validated `definition_json`, only `active` entries
  - `get_definition(workspace_id, key) -> dict | None`
  - `validate_link_pair(workspace_id, link_type, source_type, target_type, *, manual: bool) -> None` — raises `persistence.errors.ValidationError`
  - `invalidate_workspace(workspace_id: str) -> None`
  - `CACHE_NAMESPACE = "link_types"`

This is the single seam. `TraceLinkService`, the REST views, the MCP tools and the SE-Auditor all read the catalog through it; nothing else touches `WorkspaceLinkTypeDefinition` directly.

- [ ] **Step 1: Write the failing test**

```python
# backend/link_types/tests/test_catalog.py
"""Workspace catalog resolution + always-on endpoint validation."""
from __future__ import annotations

import uuid

import pytest

from link_types.builtin import builtin_definition
from link_types.catalog import (
    get_definition,
    invalidate_workspace,
    resolve_catalog,
    validate_link_pair,
)
from link_types.models import WorkspaceLinkTypeDefinition
from persistence.errors import ValidationError
from persistence.tenancy import TenantContext


@pytest.fixture
def workspace():
    TenantContext.set_tenant(uuid.uuid4())
    ws = uuid.uuid4()
    for key in ("derives-from", "verifies", "allocated-to", "references", "diagram-ref"):
        WorkspaceLinkTypeDefinition.objects.create(
            workspace_id=ws, key=key, definition_json=builtin_definition(key)
        )
    invalidate_workspace(str(ws))
    yield ws
    invalidate_workspace(str(ws))
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_resolve_returns_every_seeded_key(workspace):
    assert set(resolve_catalog(workspace)) == {
        "derives-from",
        "verifies",
        "allocated-to",
        "references",
        "diagram-ref",
    }


@pytest.mark.django_db
def test_inactive_definitions_are_excluded(workspace):
    row = WorkspaceLinkTypeDefinition.objects.get(workspace_id=workspace, key="verifies")
    row.definition_json = {**row.definition_json, "active": False}
    row.save(update_fields=["definition_json"])
    invalidate_workspace(str(workspace))
    assert "verifies" not in resolve_catalog(workspace)


@pytest.mark.django_db
def test_get_definition_returns_none_for_an_unknown_key(workspace):
    assert get_definition(workspace, "conflicts-with") is None


@pytest.mark.django_db
def test_a_valid_pair_passes(workspace):
    validate_link_pair(
        workspace, "verifies", "TestCase", "Requirement", manual=True
    )


@pytest.mark.django_db
def test_an_invalid_pair_is_rejected_and_lists_the_allowed_pairs(workspace):
    with pytest.raises(ValidationError) as exc:
        validate_link_pair(
            workspace, "verifies", "Risk", "Requirement", manual=True
        )
    message = str(exc.value)
    assert "verifies" in message
    assert "TestCase->Requirement" in message


@pytest.mark.django_db
def test_validation_applies_to_non_core_artifact_types_too(workspace):
    """The old SE_CORE_ARTIFACT_TYPES escape hatch is gone.

    Risk was outside the core set, so `verifies` from a Risk used to pass
    unchecked (audit finding U2). It must now be rejected — covered above —
    and an artifact type nobody constrained must be rejected as well.
    """
    with pytest.raises(ValidationError):
        validate_link_pair(
            workspace, "derives-from", "Issue", "Interview", manual=True
        )


@pytest.mark.django_db
def test_wildcards_match_any_artifact_type(workspace):
    validate_link_pair(workspace, "references", "Requirement", "Diagram", manual=True)
    validate_link_pair(workspace, "references", "Risk", "Diagram", manual=True)


@pytest.mark.django_db
def test_subtyped_artifact_types_are_normalized(workspace):
    """'TestCase:unit' must match a 'TestCase' pair."""
    validate_link_pair(
        workspace, "verifies", "TestCase:unit", "Requirement", manual=True
    )


@pytest.mark.django_db
def test_unknown_link_type_is_rejected_and_lists_the_catalog(workspace):
    with pytest.raises(ValidationError) as exc:
        validate_link_pair(
            workspace, "satisfies", "ArchitectureElement", "Requirement", manual=True
        )
    message = str(exc.value)
    assert "satisfies" in message
    assert "derives-from" in message


@pytest.mark.django_db
def test_system_owned_types_are_rejected_on_the_manual_path_only(workspace):
    with pytest.raises(ValidationError, match="system-managed"):
        validate_link_pair(workspace, "diagram-ref", "Diagram", "Requirement", manual=True)
    validate_link_pair(workspace, "diagram-ref", "Diagram", "Requirement", manual=False)


@pytest.mark.django_db
def test_a_customized_workspace_row_overrides_the_builtin_pairs(workspace):
    row = WorkspaceLinkTypeDefinition.objects.get(workspace_id=workspace, key="verifies")
    row.definition_json = {
        **row.definition_json,
        "allowed_pairs": [{"source_type": "Risk", "target_type": "Requirement"}],
    }
    row.is_customized = True
    row.save(update_fields=["definition_json", "is_customized"])
    invalidate_workspace(str(workspace))

    validate_link_pair(workspace, "verifies", "Risk", "Requirement", manual=True)
    with pytest.raises(ValidationError):
        validate_link_pair(workspace, "verifies", "TestCase", "Requirement", manual=True)


@pytest.mark.django_db
def test_a_workspace_without_any_rows_resolves_to_an_empty_catalog():
    TenantContext.set_tenant(uuid.uuid4())
    try:
        assert resolve_catalog(uuid.uuid4()) == {}
    finally:
        TenantContext.clear_tenant()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST link_types/tests/test_catalog.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'link_types.catalog'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/link_types/catalog.py
"""Resolved per-workspace link-type catalog + the always-on endpoint check.

This module is the **single seam**: ``application.trace_link_service``, the
REST views, the MCP tools and the SE-Auditor read link-type semantics only
through here. Nothing else queries ``WorkspaceLinkTypeDefinition``.

Replaces ``traceability.types.check_se_link_semantics`` and its two escape
hatches, both removed ersatzlos:

* the ``se_mode`` gate — a dev_mode workspace used to skip validation entirely;
* the ``SE_CORE_ARTIFACT_TYPES`` allow-list — any artifact type outside the
  five "core" ones passed unchecked, which is the exact cause of audit finding
  U2 (``verifies`` from a Risk was accepted, from a StakeholderNeed rejected).

Caching follows ``presets/gate.py``: a process-local dict tagged with the
shared cache generation for the workspace, so a bump performed in any worker
makes every other worker discard its entry on the next read. A bulk
``QuerySet.update()`` bypasses ``save()``/signals, so every writer must call
:func:`invalidate_workspace` explicitly.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Optional, Tuple
from uuid import UUID

from persistence.cache_generation import bump_cache_generation, cache_generation
from persistence.errors import ValidationError

from .models import WorkspaceLinkTypeDefinition
from .schema import validate_definition_json

CACHE_NAMESPACE = "link_types"

_cache_lock = threading.Lock()
#: workspace_id (str) -> (generation, {key: definition_json})
_catalog_cache: Dict[str, Tuple[int, Dict[str, Dict[str, Any]]]] = {}


def normalize_artifact_type(artifact_type: str | None) -> str:
    """Strip sub-type tags: ``"TestCase:unit"`` -> ``"TestCase"``.

    Moved here from ``traceability.types`` so the catalog owns the whole
    matching vocabulary.
    """
    if not artifact_type:
        return ""
    return artifact_type.split(":", 1)[0]


def invalidate_workspace(workspace_id: str) -> None:
    """Drop this process's entry and bump the shared generation.

    Both halves are needed: the pop alone leaves other workers stale, the bump
    alone leaves this process waiting out the generation read TTL.
    """
    with _cache_lock:
        _catalog_cache.pop(str(workspace_id), None)
    bump_cache_generation(CACHE_NAMESPACE, str(workspace_id))


def resolve_catalog(workspace_id: UUID | str) -> Dict[str, Dict[str, Any]]:
    """Return ``{key: definition_json}`` for every **active** type of a workspace.

    Reads the materialized per-workspace rows; there is no merge-on-read
    against the global template (spec section 4: materialized copy).
    """
    ws_key = str(workspace_id)
    generation = cache_generation(CACHE_NAMESPACE, ws_key)

    with _cache_lock:
        entry = _catalog_cache.get(ws_key)
    if entry is not None and entry[0] == generation:
        return entry[1]

    catalog: Dict[str, Dict[str, Any]] = {}
    rows = WorkspaceLinkTypeDefinition.objects.filter(
        workspace_id=workspace_id
    ).only("key", "definition_json")
    for row in rows:
        definition = row.definition_json or {}
        if not definition.get("active", True):
            continue
        catalog[row.key] = definition

    with _cache_lock:
        _catalog_cache[ws_key] = (generation, catalog)
    return catalog


def get_definition(
    workspace_id: UUID | str, key: str
) -> Optional[Dict[str, Any]]:
    """Return one active definition, or None when the key is absent/inactive."""
    return resolve_catalog(workspace_id).get(key)


def validate_link_pair(
    workspace_id: UUID | str,
    link_type: str,
    source_type: str | None,
    target_type: str | None,
    *,
    manual: bool,
) -> None:
    """Validate a link against the workspace catalog. Always. For every type.

    Args:
        workspace_id: Workspace owning both endpoints.
        link_type: The catalog key under validation.
        source_type: ``Artifact.artifact_type`` of the source endpoint.
        target_type: ``Artifact.artifact_type`` of the target endpoint.
        manual: True for hand-authored links (REST ``trace-links``, every MCP
            trace-link tool). System paths (the diagram reconciler) pass False
            and may write ``system_owned`` types.

    Raises:
        ValidationError: Unknown/inactive type, a system-owned type on the
            manual path, or an endpoint pair the type does not allow. The
            message always lists the acceptable values (audit finding R3).
    """
    catalog = resolve_catalog(workspace_id)
    definition = catalog.get(link_type)
    if definition is None:
        raise ValidationError(
            f"Unknown link type '{link_type}'. "
            f"Valid types in this workspace: {', '.join(sorted(catalog)) or '(none)'}."
        )

    if manual and not definition.get("manual_creatable", True):
        raise ValidationError(
            f"'{link_type}' is a system-managed link type and cannot be "
            f"created or updated manually."
        )

    src = normalize_artifact_type(source_type)
    tgt = normalize_artifact_type(target_type)
    pairs = definition.get("allowed_pairs") or []

    for pair in pairs:
        pair_src = pair.get("source_type")
        pair_tgt = pair.get("target_type")
        if pair_src in ("*", src) and pair_tgt in ("*", tgt):
            return

    allowed = ", ".join(
        sorted(f"{p.get('source_type')}->{p.get('target_type')}" for p in pairs)
    )
    raise ValidationError(
        f"'{link_type}' is not valid from {src or '(unknown)'} to "
        f"{tgt or '(unknown)'}. Allowed: {allowed or '(none configured)'}."
    )


def validate_definition(payload: Any, *, key: str) -> Dict[str, Any]:
    """Re-export of :func:`link_types.schema.validate_definition_json`.

    Keeps every write path importing from one module.
    """
    return validate_definition_json(payload, key=key)


__all__ = [
    "CACHE_NAMESPACE",
    "get_definition",
    "invalidate_workspace",
    "normalize_artifact_type",
    "resolve_catalog",
    "validate_definition",
    "validate_link_pair",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST link_types/tests/test_catalog.py -v`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/link_types/catalog.py backend/link_types/tests/test_catalog.py
git commit -m "feat(link-types): add workspace catalog resolver with always-on pair validation"
```

---

### Task 6: `GlobalLinkTypeDefinitionStore` with propagation

**Files:**
- Create: `backend/link_types/global_store.py`
- Test: `backend/link_types/tests/test_global_store.py`

**Interfaces:**
- Consumes: `link_types.models.*` (Task 1), `link_types.builtin.builtin_definition` (Task 3), `link_types.schema.validate_definition_json` (Task 4), `link_types.catalog.invalidate_workspace` (Task 5)
- Produces: `GlobalLinkTypeDefinitionStore` with `list(tenant_id) -> list[GlobalLinkTypeDefinition]`, `get(tenant_id, key) -> GlobalLinkTypeDefinition | None`, `create(tenant_id, key, definition_json) -> GlobalLinkTypeDefinition`, `update(tenant_id, key, definition_json) -> tuple[GlobalLinkTypeDefinition, int]` (returns the propagated row count), `delete(tenant_id, key) -> None`

- [ ] **Step 1: Write the failing test**

```python
# backend/link_types/tests/test_global_store.py
"""Tenant-wide link-type templates and their propagation."""
from __future__ import annotations

import uuid

import pytest

from link_types.builtin import builtin_definition
from link_types.catalog import resolve_catalog
from link_types.global_store import GlobalLinkTypeDefinitionStore
from link_types.models import GlobalLinkTypeDefinition, WorkspaceLinkTypeDefinition
from persistence.errors import ValidationError
from persistence.tenancy import TenantContext


@pytest.fixture
def tenant_id():
    tid = uuid.uuid4()
    TenantContext.set_tenant(tid)
    yield tid
    TenantContext.clear_tenant()


@pytest.fixture
def store():
    return GlobalLinkTypeDefinitionStore()


def _derived(tenant_id, global_row, *, customized: bool):
    return WorkspaceLinkTypeDefinition.objects.create(
        workspace_id=uuid.uuid4(),
        key=global_row.key,
        definition_json=dict(global_row.definition_json),
        source_global=global_row,
        is_customized=customized,
    )


@pytest.mark.django_db
def test_create_persists_a_validated_definition(tenant_id, store):
    row = store.create(tenant_id, "verifies", builtin_definition("verifies"))
    assert row.key == "verifies"
    assert row.definition_json["impact_weight"] == 1.0
    assert row.version == 1


@pytest.mark.django_db
def test_create_rejects_an_invalid_definition(tenant_id, store):
    bad = builtin_definition("verifies")
    bad["suspect_rule"] = "nonsense"
    with pytest.raises(ValidationError, match="suspect_rule"):
        store.create(tenant_id, "verifies", bad)
    assert GlobalLinkTypeDefinition.objects.filter(key="verifies").count() == 0


@pytest.mark.django_db
def test_create_rejects_a_duplicate_key(tenant_id, store):
    store.create(tenant_id, "verifies", builtin_definition("verifies"))
    with pytest.raises(ValidationError, match="already exists"):
        store.create(tenant_id, "verifies", builtin_definition("verifies"))


@pytest.mark.django_db
def test_a_tenant_can_invent_a_new_key(tenant_id, store):
    definition = builtin_definition("mitigates")
    definition["built_in"] = False
    definition["label"]["de"]["neutral"] = "Konflikt"
    row = store.create(tenant_id, "conflicts-with", definition)
    assert row.key == "conflicts-with"


@pytest.mark.django_db
def test_update_propagates_into_non_customized_rows_only(tenant_id, store):
    g = store.create(tenant_id, "mitigates", builtin_definition("mitigates"))
    on_default = _derived(tenant_id, g, customized=False)
    customized = _derived(tenant_id, g, customized=True)

    changed = builtin_definition("mitigates")
    changed["impact_weight"] = 0.9
    _row, propagated = store.update(tenant_id, "mitigates", changed)

    assert propagated == 1
    on_default.refresh_from_db()
    customized.refresh_from_db()
    assert on_default.definition_json["impact_weight"] == 0.9
    assert customized.definition_json["impact_weight"] == 0.5


@pytest.mark.django_db
def test_update_bumps_the_version(tenant_id, store):
    store.create(tenant_id, "mitigates", builtin_definition("mitigates"))
    row, _ = store.update(tenant_id, "mitigates", builtin_definition("mitigates"))
    assert row.version == 2


@pytest.mark.django_db
def test_update_invalidates_the_catalog_cache_of_every_affected_workspace(
    tenant_id, store
):
    g = store.create(tenant_id, "mitigates", builtin_definition("mitigates"))
    derived = _derived(tenant_id, g, customized=False)
    assert resolve_catalog(derived.workspace_id)["mitigates"]["impact_weight"] == 0.5

    changed = builtin_definition("mitigates")
    changed["impact_weight"] = 0.9
    store.update(tenant_id, "mitigates", changed)

    assert resolve_catalog(derived.workspace_id)["mitigates"]["impact_weight"] == 0.9


@pytest.mark.django_db
def test_update_of_a_missing_key_raises(tenant_id, store):
    with pytest.raises(ValidationError, match="not found"):
        store.update(tenant_id, "conflicts-with", builtin_definition("mitigates"))


@pytest.mark.django_db
def test_a_system_owned_type_cannot_have_its_lock_flags_changed(tenant_id, store):
    store.create(tenant_id, "diagram-ref", builtin_definition("diagram-ref"))
    unlocked = builtin_definition("diagram-ref")
    unlocked["manual_creatable"] = True
    unlocked["system_owned"] = False
    with pytest.raises(ValidationError, match="system-managed"):
        store.update(tenant_id, "diagram-ref", unlocked)


@pytest.mark.django_db
def test_a_system_owned_type_can_still_have_its_label_edited(tenant_id, store):
    store.create(tenant_id, "diagram-ref", builtin_definition("diagram-ref"))
    relabelled = builtin_definition("diagram-ref")
    relabelled["label"]["de"]["neutral"] = "Diagramm"
    row, _ = store.update(tenant_id, "diagram-ref", relabelled)
    assert row.definition_json["label"]["de"]["neutral"] == "Diagramm"


@pytest.mark.django_db
def test_a_system_owned_type_cannot_be_deleted(tenant_id, store):
    store.create(tenant_id, "diagram-ref", builtin_definition("diagram-ref"))
    with pytest.raises(ValidationError, match="system-managed"):
        store.delete(tenant_id, "diagram-ref")


@pytest.mark.django_db
def test_list_is_sorted_by_key(tenant_id, store):
    for key in ("verifies", "decides", "mitigates"):
        store.create(tenant_id, key, builtin_definition(key))
    assert [row.key for row in store.list(tenant_id)] == [
        "decides",
        "mitigates",
        "verifies",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST link_types/tests/test_global_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'link_types.global_store'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/link_types/global_store.py
"""CRUD + propagation for tenant-wide global link-type templates.

Mirrors ``workflow.global_definition_store.GlobalWorkflowDefinitionStore``:
an edit here is copied into every ``is_customized=False`` derived workspace
row (materialized copy, not merge-on-read), and each affected workspace's
resolved catalog cache is invalidated explicitly — the bulk
``QuerySet.update()`` bypasses ``save()``/signals, so without it every worker
would keep validating against the pre-edit pairs for the rest of its life.

``unscoped`` is used deliberately: these helpers are called with an explicit
``tenant_id`` from admin endpoints and from the seed migration, and RLS
remains the second isolation layer underneath either way.
"""
from __future__ import annotations

import copy
from typing import Any, List, Optional, Tuple
from uuid import UUID

from django.db import transaction

from persistence.errors import ValidationError

from .catalog import invalidate_workspace
from .models import GlobalLinkTypeDefinition, WorkspaceLinkTypeDefinition
from .schema import validate_definition_json

#: Flags a tenant may never flip on a system-owned type. ``diagram-ref`` is
#: reconciler-owned; unlocking it would let a hand-authored link be silently
#: deleted on the diagram's next node_graph save.
_LOCKED_FLAGS = ("system_owned", "manual_creatable")


class GlobalLinkTypeDefinitionStore:
    """Tenant-admin CRUD over ``GlobalLinkTypeDefinition``."""

    # ---------- Read ----------

    def get(
        self, tenant_id: UUID | str, key: str
    ) -> Optional[GlobalLinkTypeDefinition]:
        """Return the global row for ``(tenant, key)`` or None."""
        return GlobalLinkTypeDefinition.unscoped.filter(
            tenant_id=tenant_id, key=key
        ).first()

    def list(self, tenant_id: UUID | str) -> List[GlobalLinkTypeDefinition]:
        """Return every global row of the tenant, ordered by key."""
        return list(
            GlobalLinkTypeDefinition.unscoped.filter(tenant_id=tenant_id).order_by("key")
        )

    # ---------- Write ----------

    @transaction.atomic
    def create(
        self, tenant_id: UUID | str, key: str, definition_json: Any
    ) -> GlobalLinkTypeDefinition:
        """Create a new global template.

        Raises:
            ValidationError: The key already exists, or the definition is
                malformed.
        """
        if not key or not key.strip():
            raise ValidationError("Link type key must not be empty.")
        if self.get(tenant_id, key) is not None:
            raise ValidationError(f"Link type '{key}' already exists for this tenant.")
        validated = validate_definition_json(definition_json, key=key)
        return GlobalLinkTypeDefinition.unscoped.create(
            tenant_id=tenant_id, key=key, definition_json=validated, version=1
        )

    @transaction.atomic
    def update(
        self, tenant_id: UUID | str, key: str, definition_json: Any
    ) -> Tuple[GlobalLinkTypeDefinition, int]:
        """Replace a global template and propagate it.

        Returns:
            ``(row, propagated_count)`` — how many non-customized workspace
            rows received the new definition.

        Raises:
            ValidationError: Unknown key, malformed definition, or an attempt
                to unlock a system-owned type.
        """
        row = self.get(tenant_id, key)
        if row is None:
            raise ValidationError(f"Link type '{key}' not found for this tenant.")

        validated = validate_definition_json(definition_json, key=key)
        current = row.definition_json or {}
        if current.get("system_owned"):
            for flag in _LOCKED_FLAGS:
                if validated.get(flag) != current.get(flag):
                    raise ValidationError(
                        f"'{key}' is a system-managed link type: '{flag}' is "
                        f"locked and cannot be changed."
                    )

        row.definition_json = validated
        row.version = (row.version or 1) + 1
        row.save(update_fields=["definition_json", "version"])
        return row, self._propagate(row)

    @transaction.atomic
    def delete(self, tenant_id: UUID | str, key: str) -> None:
        """Delete a global template.

        Deliberately does **not** touch derived workspace rows: their
        ``source_global`` FK is SET_NULL, so they survive as standalone
        definitions. Deactivating a type across a tenant is done by setting
        ``active=False`` via :meth:`update`, which propagates — hard-deleting
        the template is an admin cleanup, not a soft-disable.

        Raises:
            ValidationError: Unknown key, or the type is system-owned.
        """
        row = self.get(tenant_id, key)
        if row is None:
            raise ValidationError(f"Link type '{key}' not found for this tenant.")
        if (row.definition_json or {}).get("system_owned"):
            raise ValidationError(
                f"'{key}' is a system-managed link type and cannot be deleted."
            )
        row.delete()

    # ---------- Propagation ----------

    def _propagate(self, row: GlobalLinkTypeDefinition) -> int:
        """Copy ``definition_json`` into every non-customized derived row.

        Invalidates the resolved-catalog cache of each affected workspace: the
        bulk update below bypasses ``save()``/signals, so without this every
        other worker keeps validating against the stale pre-edit pairs.
        """
        derived = WorkspaceLinkTypeDefinition.unscoped.filter(
            source_global_id=row.id, is_customized=False
        )
        affected = list(derived.values_list("workspace_id", flat=True))
        count = derived.update(definition_json=copy.deepcopy(row.definition_json))
        for workspace_id in affected:
            invalidate_workspace(str(workspace_id))
        return count


__all__ = ["GlobalLinkTypeDefinitionStore"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST link_types/tests/test_global_store.py -v`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/link_types/global_store.py backend/link_types/tests/test_global_store.py
git commit -m "feat(link-types): add global link-type store with materialized-copy propagation"
```

---

### Task 7: `WorkspaceLinkTypeDefinitionStore` and provisioning

**Files:**
- Create: `backend/link_types/workspace_store.py`
- Modify: `backend/application/workspace_provisioning.py:62-128`
- Test: `backend/link_types/tests/test_workspace_store.py`

**Interfaces:**
- Consumes: `GlobalLinkTypeDefinitionStore` (Task 6), `builtin_definition` (Task 3), `invalidate_workspace` (Task 5)
- Produces:
  - `WorkspaceLinkTypeDefinitionStore.list(tenant_id, workspace_id) -> list[WorkspaceLinkTypeDefinition]`
  - `.get(tenant_id, workspace_id, key) -> WorkspaceLinkTypeDefinition | None`
  - `.update(tenant_id, workspace_id, key, definition_json) -> WorkspaceLinkTypeDefinition` (sets `is_customized=True`)
  - `.reset(tenant_id, workspace_id, key) -> WorkspaceLinkTypeDefinition` (restores from `source_global`, else from `builtin_definition`; sets `is_customized=False`)
  - `provision_workspace_link_types(*, workspace_id, tenant_id) -> int` — idempotent, returns rows created

- [ ] **Step 1: Write the failing test**

```python
# backend/link_types/tests/test_workspace_store.py
"""Per-workspace overrides, reset-to-default and provisioning."""
from __future__ import annotations

import uuid

import pytest

from link_types.builtin import BUILTIN_LINK_TYPES, builtin_definition
from link_types.catalog import resolve_catalog
from link_types.global_store import GlobalLinkTypeDefinitionStore
from link_types.models import GlobalLinkTypeDefinition, WorkspaceLinkTypeDefinition
from link_types.workspace_store import (
    WorkspaceLinkTypeDefinitionStore,
    provision_workspace_link_types,
)
from persistence.errors import ValidationError
from persistence.tenancy import TenantContext


@pytest.fixture
def tenant_id():
    tid = uuid.uuid4()
    TenantContext.set_tenant(tid)
    yield tid
    TenantContext.clear_tenant()


@pytest.fixture
def store():
    return WorkspaceLinkTypeDefinitionStore()


@pytest.mark.django_db
def test_provisioning_creates_all_eight_types(tenant_id):
    ws = uuid.uuid4()
    created = provision_workspace_link_types(workspace_id=ws, tenant_id=tenant_id)
    assert created == 8
    assert set(resolve_catalog(ws)) == set(BUILTIN_LINK_TYPES)


@pytest.mark.django_db
def test_provisioning_is_idempotent(tenant_id):
    ws = uuid.uuid4()
    provision_workspace_link_types(workspace_id=ws, tenant_id=tenant_id)
    assert provision_workspace_link_types(workspace_id=ws, tenant_id=tenant_id) == 0
    assert WorkspaceLinkTypeDefinition.objects.filter(workspace_id=ws).count() == 8


@pytest.mark.django_db
def test_provisioning_never_overwrites_a_customized_row(tenant_id):
    ws = uuid.uuid4()
    provision_workspace_link_types(workspace_id=ws, tenant_id=tenant_id)
    row = WorkspaceLinkTypeDefinition.objects.get(workspace_id=ws, key="mitigates")
    row.definition_json = {**row.definition_json, "impact_weight": 0.77}
    row.is_customized = True
    row.save(update_fields=["definition_json", "is_customized"])

    provision_workspace_link_types(workspace_id=ws, tenant_id=tenant_id)
    row.refresh_from_db()
    assert row.definition_json["impact_weight"] == 0.77


@pytest.mark.django_db
def test_provisioning_links_rows_back_to_the_global_template(tenant_id):
    ws = uuid.uuid4()
    provision_workspace_link_types(workspace_id=ws, tenant_id=tenant_id)
    row = WorkspaceLinkTypeDefinition.objects.get(workspace_id=ws, key="verifies")
    assert row.source_global is not None
    assert row.source_global.key == "verifies"
    assert row.is_customized is False


@pytest.mark.django_db
def test_provisioning_reuses_an_existing_global_template(tenant_id):
    GlobalLinkTypeDefinitionStore().create(
        tenant_id, "verifies", builtin_definition("verifies")
    )
    provision_workspace_link_types(workspace_id=uuid.uuid4(), tenant_id=tenant_id)
    assert GlobalLinkTypeDefinition.objects.filter(key="verifies").count() == 1


@pytest.mark.django_db
def test_update_marks_the_row_customized_and_invalidates_the_cache(tenant_id, store):
    ws = uuid.uuid4()
    provision_workspace_link_types(workspace_id=ws, tenant_id=tenant_id)
    assert resolve_catalog(ws)["mitigates"]["impact_weight"] == 0.5

    changed = builtin_definition("mitigates")
    changed["impact_weight"] = 0.8
    row = store.update(tenant_id, ws, "mitigates", changed)

    assert row.is_customized is True
    assert row.version == 2
    assert resolve_catalog(ws)["mitigates"]["impact_weight"] == 0.8


@pytest.mark.django_db
def test_reset_restores_the_global_definition_and_clears_the_flag(tenant_id, store):
    ws = uuid.uuid4()
    provision_workspace_link_types(workspace_id=ws, tenant_id=tenant_id)
    changed = builtin_definition("mitigates")
    changed["impact_weight"] = 0.8
    store.update(tenant_id, ws, "mitigates", changed)

    row = store.reset(tenant_id, ws, "mitigates")

    assert row.is_customized is False
    assert row.definition_json["impact_weight"] == 0.5
    assert resolve_catalog(ws)["mitigates"]["impact_weight"] == 0.5


@pytest.mark.django_db
def test_reset_falls_back_to_the_builtin_when_the_global_row_is_gone(tenant_id, store):
    ws = uuid.uuid4()
    provision_workspace_link_types(workspace_id=ws, tenant_id=tenant_id)
    GlobalLinkTypeDefinition.objects.filter(key="mitigates").delete()

    row = store.reset(tenant_id, ws, "mitigates")
    assert row.definition_json["impact_weight"] == 0.5
    assert row.is_customized is False


@pytest.mark.django_db
def test_reset_of_a_tenant_invented_type_without_a_global_row_raises(tenant_id, store):
    ws = uuid.uuid4()
    definition = builtin_definition("mitigates")
    definition["built_in"] = False
    WorkspaceLinkTypeDefinition.objects.create(
        workspace_id=ws, key="conflicts-with", definition_json=definition
    )
    with pytest.raises(ValidationError, match="no default"):
        store.reset(tenant_id, ws, "conflicts-with")


@pytest.mark.django_db
def test_update_of_a_missing_key_raises(tenant_id, store):
    with pytest.raises(ValidationError, match="not found"):
        store.update(
            tenant_id, uuid.uuid4(), "mitigates", builtin_definition("mitigates")
        )


@pytest.mark.django_db
def test_a_workspace_may_deactivate_a_type_without_deleting_it(tenant_id, store):
    ws = uuid.uuid4()
    provision_workspace_link_types(workspace_id=ws, tenant_id=tenant_id)
    disabled = builtin_definition("mitigates")
    disabled["active"] = False
    store.update(tenant_id, ws, "mitigates", disabled)

    assert "mitigates" not in resolve_catalog(ws)
    assert WorkspaceLinkTypeDefinition.objects.filter(
        workspace_id=ws, key="mitigates"
    ).exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST link_types/tests/test_workspace_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'link_types.workspace_store'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/link_types/workspace_store.py
"""Per-workspace link-type overrides, reset-to-default and provisioning.

Provisioning intentionally seeds *rows*, not a lazy merge: the catalog is
read on every single link creation, so a materialized copy keeps the hot path
to one indexed query with no fallback branch.

``provision_workspace_link_types`` is idempotent (``get_or_create``), which is
what lets the backfill migration, ``application.workspace_provisioning`` and a
manual re-run all call it safely.
"""
from __future__ import annotations

import copy
from typing import Any, List, Optional
from uuid import UUID

from django.db import transaction

from persistence.errors import ValidationError

from .builtin import BUILTIN_LINK_TYPES, builtin_definition
from .catalog import invalidate_workspace
from .global_store import GlobalLinkTypeDefinitionStore
from .models import GlobalLinkTypeDefinition, WorkspaceLinkTypeDefinition
from .schema import validate_definition_json


class WorkspaceLinkTypeDefinitionStore:
    """Read/override/reset over ``WorkspaceLinkTypeDefinition``."""

    def get(
        self, tenant_id: UUID | str, workspace_id: UUID | str, key: str
    ) -> Optional[WorkspaceLinkTypeDefinition]:
        """Return the workspace row for *key*, or None."""
        return WorkspaceLinkTypeDefinition.unscoped.filter(
            tenant_id=tenant_id, workspace_id=workspace_id, key=key
        ).first()

    def list(
        self, tenant_id: UUID | str, workspace_id: UUID | str
    ) -> List[WorkspaceLinkTypeDefinition]:
        """Return every workspace row, ordered by key (including inactive ones).

        The editor UI must see deactivated types to be able to re-enable them,
        so this is deliberately *not* filtered by ``active`` the way
        ``catalog.resolve_catalog`` is.
        """
        return list(
            WorkspaceLinkTypeDefinition.unscoped.filter(
                tenant_id=tenant_id, workspace_id=workspace_id
            ).order_by("key")
        )

    @transaction.atomic
    def update(
        self,
        tenant_id: UUID | str,
        workspace_id: UUID | str,
        key: str,
        definition_json: Any,
    ) -> WorkspaceLinkTypeDefinition:
        """Override a definition for one workspace (sets ``is_customized=True``).

        Raises:
            ValidationError: Unknown key or malformed definition.
        """
        row = self.get(tenant_id, workspace_id, key)
        if row is None:
            raise ValidationError(
                f"Link type '{key}' not found in this workspace."
            )
        row.definition_json = validate_definition_json(definition_json, key=key)
        row.is_customized = True
        row.version = (row.version or 1) + 1
        row.save(update_fields=["definition_json", "is_customized", "version"])
        invalidate_workspace(str(workspace_id))
        return row

    @transaction.atomic
    def reset(
        self, tenant_id: UUID | str, workspace_id: UUID | str, key: str
    ) -> WorkspaceLinkTypeDefinition:
        """Restore the workspace row from its default and clear the override flag.

        Default source order: the linked ``source_global`` row, then the
        built-in definition. A tenant-invented type that has neither has no
        default to fall back to, which is an error rather than a silent no-op.

        Raises:
            ValidationError: Unknown key, or no default exists.
        """
        row = self.get(tenant_id, workspace_id, key)
        if row is None:
            raise ValidationError(f"Link type '{key}' not found in this workspace.")

        default: Optional[dict] = None
        if row.source_global_id is not None:
            global_row = GlobalLinkTypeDefinition.unscoped.filter(
                id=row.source_global_id
            ).first()
            if global_row is not None:
                default = copy.deepcopy(global_row.definition_json)
        if default is None and key in BUILTIN_LINK_TYPES:
            default = builtin_definition(key)
        if default is None:
            raise ValidationError(
                f"Link type '{key}' has no default to reset to: it is neither "
                f"a built-in type nor derived from a global definition."
            )

        row.definition_json = default
        row.is_customized = False
        row.version = (row.version or 1) + 1
        row.save(update_fields=["definition_json", "is_customized", "version"])
        invalidate_workspace(str(workspace_id))
        return row


def provision_workspace_link_types(
    *, workspace_id: UUID | str, tenant_id: UUID | str
) -> int:
    """Seed the eight built-in link types for a workspace. Idempotent.

    Ensures the tenant's global templates exist first (creating any that are
    missing from ``BUILTIN_LINK_TYPES``), then materializes one workspace row
    per template. Existing rows — customized or not — are left untouched.

    Args:
        workspace_id: Target workspace UUID.
        tenant_id: Owning tenant UUID. Passed explicitly because the
            ``get_or_create`` calls below run on the unscoped QuerySet,
            bypassing the tenant manager's auto-inject on create — the same
            reason ``provision_workspace_defaults`` takes it.

    Returns:
        Number of workspace rows created (0 on a repeat run).
    """
    created = 0
    for key in sorted(BUILTIN_LINK_TYPES):
        global_row, _ = GlobalLinkTypeDefinition.unscoped.get_or_create(
            tenant_id=tenant_id,
            key=key,
            defaults={"definition_json": builtin_definition(key), "version": 1},
        )
        _row, was_created = WorkspaceLinkTypeDefinition.unscoped.get_or_create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            key=key,
            defaults={
                "definition_json": copy.deepcopy(global_row.definition_json),
                "source_global": global_row,
                "is_customized": False,
                "version": 1,
            },
        )
        created += int(was_created)

    if created:
        invalidate_workspace(str(workspace_id))
    return created


__all__ = [
    "WorkspaceLinkTypeDefinitionStore",
    "provision_workspace_link_types",
]
```

In `backend/application/workspace_provisioning.py`, inside `provision_workspace_defaults` (after the existing workflow/permission provisioning calls), add:

```python
    # LinkTypeCatalog: a workspace without link-type rows resolves to an empty
    # catalog, and every TraceLink creation would then be rejected as "unknown
    # link type". Idempotent, so a re-run is safe.
    from link_types.workspace_store import provision_workspace_link_types

    provision_workspace_link_types(
        workspace_id=workspace_id, tenant_id=tenant_id
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST link_types/tests/test_workspace_store.py application/tests/test_workspace_provisioning.py -v`
Expected: PASS (11 passed in `test_workspace_store.py`; the provisioning module's existing tests stay green)

- [ ] **Step 5: Commit**

```bash
git add backend/link_types/workspace_store.py backend/link_types/tests/test_workspace_store.py backend/application/workspace_provisioning.py
git commit -m "feat(link-types): provision built-in link types per workspace"
```

---

### Task 8: Backfill migration for existing tenants and workspaces

**Files:**
- Create: `backend/link_types/migrations/0003_seed_builtin_link_types.py`
- Test: `backend/link_types/tests/test_seed_migration.py`

**Interfaces:**
- Consumes: `link_types.builtin.BUILTIN_LINK_TYPES` (Task 3)
- Produces: one `lt_global_definition` row per `(tenant, built-in key)` and one `lt_workspace_definition` row per `(workspace, built-in key)` for every workspace that existed before this migration

A blind `INSERT` cannot work here: both tables are `TenantScopedModel` under RLS, so the migration iterates tenants and arms `app.current_tenant` per tenant, exactly as `se_metrics.aggregator` does for its worker threads. Migrations run under the migration DB role (the compose `migrate` service uses `DB_USER`, the owner), so the DDL and the per-tenant `SET` both succeed; running this as the least-privilege app role would silently insert zero rows.

- [ ] **Step 1: Write the failing test**

```python
# backend/link_types/tests/test_seed_migration.py
"""The backfill seeds every pre-existing tenant and workspace."""
from __future__ import annotations

import pytest
from django.db import connection

from link_types.builtin import BUILTIN_LINK_TYPES
from link_types.migrations import _seed_helpers  # exported for testability


@pytest.mark.django_db
def test_seed_is_idempotent_across_two_runs():
    from persistence.models import Tenant, Workspace

    tenant = Tenant.objects.create(name="seed-test")
    with connection.cursor() as cur:
        cur.execute("SET app.current_tenant = %s", [str(tenant.id)])
    workspace = Workspace.objects.create(tenant=tenant, name="ws")

    first = _seed_helpers.seed_tenant(tenant.id, [workspace.id])
    second = _seed_helpers.seed_tenant(tenant.id, [workspace.id])

    assert first == (len(BUILTIN_LINK_TYPES), len(BUILTIN_LINK_TYPES))
    assert second == (0, 0)


@pytest.mark.django_db
def test_seed_creates_one_global_row_and_one_workspace_row_per_key():
    from link_types.models import (
        GlobalLinkTypeDefinition,
        WorkspaceLinkTypeDefinition,
    )
    from persistence.models import Tenant, Workspace

    tenant = Tenant.objects.create(name="seed-test-2")
    with connection.cursor() as cur:
        cur.execute("SET app.current_tenant = %s", [str(tenant.id)])
    ws_a = Workspace.objects.create(tenant=tenant, name="a")
    ws_b = Workspace.objects.create(tenant=tenant, name="b")

    _seed_helpers.seed_tenant(tenant.id, [ws_a.id, ws_b.id])

    assert GlobalLinkTypeDefinition.unscoped.filter(
        tenant_id=tenant.id
    ).count() == len(BUILTIN_LINK_TYPES)
    assert WorkspaceLinkTypeDefinition.unscoped.filter(
        tenant_id=tenant.id
    ).count() == 2 * len(BUILTIN_LINK_TYPES)


@pytest.mark.django_db
def test_seeded_workspace_rows_point_at_their_global_template():
    from link_types.models import WorkspaceLinkTypeDefinition
    from persistence.models import Tenant, Workspace

    tenant = Tenant.objects.create(name="seed-test-3")
    with connection.cursor() as cur:
        cur.execute("SET app.current_tenant = %s", [str(tenant.id)])
    workspace = Workspace.objects.create(tenant=tenant, name="ws")

    _seed_helpers.seed_tenant(tenant.id, [workspace.id])

    rows = WorkspaceLinkTypeDefinition.unscoped.filter(tenant_id=tenant.id)
    assert all(row.source_global_id is not None for row in rows)
    assert all(row.is_customized is False for row in rows)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST link_types/tests/test_seed_migration.py -v`
Expected: FAIL with `ImportError: cannot import name '_seed_helpers' from 'link_types.migrations'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/link_types/migrations/_seed_helpers.py
"""Seeding logic shared by the backfill migration and its tests.

Lives outside the numbered migration module so the behaviour is testable
without replaying migration state. The migration is a thin wrapper.
"""
from __future__ import annotations

import copy
from typing import Iterable, Tuple
from uuid import UUID

from link_types.builtin import BUILTIN_LINK_TYPES, builtin_definition


def seed_tenant(tenant_id: UUID, workspace_ids: Iterable[UUID]) -> Tuple[int, int]:
    """Create the missing global and workspace rows for one tenant.

    Args:
        tenant_id: Tenant to seed.
        workspace_ids: Every workspace of that tenant.

    Returns:
        ``(globals_created, workspace_rows_created)``. Both are 0 on a repeat
        run — every write is a ``get_or_create``, so an existing (possibly
        customized) row is never overwritten.
    """
    from link_types.models import (
        GlobalLinkTypeDefinition,
        WorkspaceLinkTypeDefinition,
    )

    globals_created = 0
    rows_created = 0
    workspace_ids = list(workspace_ids)

    for key in sorted(BUILTIN_LINK_TYPES):
        global_row, created = GlobalLinkTypeDefinition.unscoped.get_or_create(
            tenant_id=tenant_id,
            key=key,
            defaults={"definition_json": builtin_definition(key), "version": 1},
        )
        globals_created += int(created)

        for workspace_id in workspace_ids:
            _row, was_created = WorkspaceLinkTypeDefinition.unscoped.get_or_create(
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                key=key,
                defaults={
                    "definition_json": copy.deepcopy(global_row.definition_json),
                    "source_global": global_row,
                    "is_customized": False,
                    "version": 1,
                },
            )
            rows_created += int(was_created)

    return globals_created, rows_created
```

```python
# backend/link_types/migrations/0003_seed_builtin_link_types.py
"""Backfill the eight built-in link types for every existing tenant.

Both ``lt_*`` tables are RLS-protected, so a blind cross-tenant INSERT is
impossible: this migration iterates tenants and arms ``app.current_tenant``
per tenant before writing, the same shape ``se_metrics.aggregator`` uses for
its worker threads. It runs under the migration DB role (the compose
``migrate`` service connects as the owner); under the least-privilege
``reqogniloom_app`` role the writes would be silently filtered to zero rows.

Idempotent: ``get_or_create`` throughout, so a re-run after a partial failure
adds only what is missing.
"""
from __future__ import annotations

import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def seed_builtin_link_types(apps, schema_editor):
    from link_types.migrations._seed_helpers import seed_tenant

    Tenant = apps.get_model("persistence", "Tenant")
    Workspace = apps.get_model("persistence", "Workspace")

    total_globals = 0
    total_rows = 0
    for tenant_id in Tenant.objects.values_list("id", flat=True):
        with schema_editor.connection.cursor() as cur:
            cur.execute("SET app.current_tenant = %s", [str(tenant_id)])
        workspace_ids = list(
            Workspace.objects.filter(tenant_id=tenant_id).values_list("id", flat=True)
        )
        globals_created, rows_created = seed_tenant(tenant_id, workspace_ids)
        total_globals += globals_created
        total_rows += rows_created

    with schema_editor.connection.cursor() as cur:
        cur.execute("RESET app.current_tenant")

    logger.info(
        "LinkTypeCatalog seed: %d global templates, %d workspace rows created.",
        total_globals,
        total_rows,
    )


def unseed(apps, schema_editor):
    """Reverse: drop only the untouched built-in rows.

    A customized row is a user edit, not migration output, so it survives a
    rollback.
    """
    from link_types.builtin import BUILTIN_LINK_TYPES

    GlobalLinkTypeDefinition = apps.get_model("link_types", "GlobalLinkTypeDefinition")
    WorkspaceLinkTypeDefinition = apps.get_model(
        "link_types", "WorkspaceLinkTypeDefinition"
    )
    keys = list(BUILTIN_LINK_TYPES)
    WorkspaceLinkTypeDefinition.objects.filter(
        key__in=keys, is_customized=False
    ).delete()
    GlobalLinkTypeDefinition.objects.filter(key__in=keys).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("link_types", "0002_rls_policies"),
        ("persistence", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_builtin_link_types, unseed),
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST link_types/tests/test_seed_migration.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/link_types/migrations/_seed_helpers.py backend/link_types/migrations/0003_seed_builtin_link_types.py backend/link_types/tests/test_seed_migration.py
git commit -m "feat(link-types): backfill built-in link types for existing tenants"
```

---

## Phase B — Flip validation to always-on

### Task 9: `inventory_link_types` command (evidence for OFFENE FRAGE 1)

**Files:**
- Create: `backend/link_types/management/__init__.py`
- Create: `backend/link_types/management/commands/__init__.py`
- Create: `backend/link_types/management/commands/inventory_link_types.py`
- Test: `backend/link_types/tests/test_inventory_command.py`

**Interfaces:**
- Consumes: `persistence.models.TraceLink`, `persistence.models.Artifact`, `link_types.builtin.LEGACY_LINK_TYPE_MAPPING`, `SWAPPED_LEGACY_KEYS`
- Produces:
  - `collect_observed_triples() -> list[dict]` — `[{"link_type", "source_type", "target_type", "count"}]` **after** applying the 3.1 rename and endpoint swap
  - `uncovered_triples(observed) -> list[dict]` — the subset no built-in `allowed_pairs` entry matches
  - management command `inventory_link_types [--json PATH]`

Run this **before** Task 11. Its output is the evidence for OFFENE FRAGE 1 and the input for Task 10's grandfathering rows.

- [ ] **Step 1: Write the failing test**

```python
# backend/link_types/tests/test_inventory_command.py
"""Inventory of the (link_type, source_type, target_type) triples in live data."""
from __future__ import annotations

import json
import uuid
from io import StringIO

import pytest
from django.core.management import call_command

from link_types.management.commands.inventory_link_types import (
    collect_observed_triples,
    uncovered_triples,
)
from persistence.tenancy import TenantContext


@pytest.fixture
def workspace_with_links(db):
    from persistence.models import Artifact, Tenant, TraceLink, Workspace

    tenant = Tenant.objects.create(name="inventory")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="ws")

    def artifact(kind: str) -> Artifact:
        return Artifact.objects.create(
            tenant=tenant, workspace=ws, artifact_type=kind, title=f"{kind}-{uuid.uuid4()}"
        )

    req, arch, goal, tc = (
        artifact("Requirement"),
        artifact("ArchitectureElement"),
        artifact("Goal"),
        artifact("TestCase"),
    )
    TraceLink.objects.create(tenant=tenant, source=arch, target=req, link_type="satisfies")
    TraceLink.objects.create(tenant=tenant, source=tc, target=req, link_type="verifies")
    TraceLink.objects.create(tenant=tenant, source=req, target=goal, link_type="traces")
    yield ws
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_legacy_keys_are_reported_under_their_new_name(workspace_with_links):
    observed = {t["link_type"] for t in collect_observed_triples()}
    assert "satisfies" not in observed
    assert "allocated-to" in observed
    assert "references" in observed


@pytest.mark.django_db
def test_swapped_keys_are_reported_with_swapped_endpoints(workspace_with_links):
    entry = next(
        t for t in collect_observed_triples() if t["link_type"] == "allocated-to"
    )
    assert entry["source_type"] == "Requirement"
    assert entry["target_type"] == "ArchitectureElement"


@pytest.mark.django_db
def test_counts_are_aggregated(workspace_with_links):
    entry = next(t for t in collect_observed_triples() if t["link_type"] == "verifies")
    assert entry["count"] == 1


@pytest.mark.django_db
def test_covered_triples_are_not_reported_as_uncovered(workspace_with_links):
    uncovered = {t["link_type"] for t in uncovered_triples(collect_observed_triples())}
    assert "verifies" not in uncovered
    assert "allocated-to" not in uncovered


@pytest.mark.django_db
def test_a_goal_target_is_reported_as_uncovered(workspace_with_links):
    """Requirement --references--> Goal matches no built-in pair (OFFENE FRAGE 1)."""
    uncovered = uncovered_triples(collect_observed_triples())
    assert any(
        t["link_type"] == "references" and t["target_type"] == "Goal"
        for t in uncovered
    )


@pytest.mark.django_db
def test_command_writes_json(workspace_with_links, tmp_path):
    out = tmp_path / "inventory.json"
    call_command("inventory_link_types", "--json", str(out), stdout=StringIO())
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "observed" in payload and "uncovered" in payload
    assert any(t["link_type"] == "allocated-to" for t in payload["observed"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST link_types/tests/test_inventory_command.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'link_types.management'`

- [ ] **Step 3: Write minimal implementation**

`backend/link_types/management/__init__.py` and `backend/link_types/management/commands/__init__.py` are empty files.

```python
# backend/link_types/management/commands/inventory_link_types.py
"""Report the link-type/endpoint triples that actually exist in the database.

Written for OFFENE FRAGE 1 of the Traceability-Semantik plan: the eight
built-in types cover Requirement / ArchitectureElement / TestCase /
StakeholderNeed / Adr / Risk / Diagram / GlossaryTerm / Icd, but **not**
Goal, MainGoal, Issue or Interview — all four of which are live artifact
types with real links today (Goal<->Requirement links are the reason
``TraceLinkService._resolve_artifact`` gained its Goal branch in fix #237).

Flipping validation to always-on without knowing what is out there would
reject existing, legitimate data. Run this first::

    python manage.py inventory_link_types --json /tmp/link_type_inventory.json

``observed`` lists every triple after applying the section-3.1 rename and
endpoint swap; ``uncovered`` is the subset that no built-in ``allowed_pairs``
entry matches — exactly the rows that would start failing.
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Any, Dict, List

from django.core.management.base import BaseCommand
from django.db.models import Count

from link_types.builtin import (
    BUILTIN_LINK_TYPES,
    LEGACY_LINK_TYPE_MAPPING,
    SWAPPED_LEGACY_KEYS,
)
from link_types.catalog import normalize_artifact_type


def collect_observed_triples() -> List[Dict[str, Any]]:
    """Return the distinct post-migration triples with their row counts.

    Legacy keys are reported under their successor name, and rows of a
    ``SWAPPED_LEGACY_KEYS`` type are reported with source and target already
    exchanged — so the output describes the world *after* the data migration,
    which is the world validation has to accept.

    Retired-without-successor keys (``parent-child``, ``copy-of``) are skipped:
    they will not exist as links afterwards.
    """
    from persistence.models import TraceLink

    counter: Counter = Counter()
    rows = (
        TraceLink.objects.values(
            "link_type", "source__artifact_type", "target__artifact_type"
        )
        .annotate(count=Count("id"))
        .order_by()
    )
    for row in rows:
        raw_type = row["link_type"]
        if raw_type in LEGACY_LINK_TYPE_MAPPING:
            successor = LEGACY_LINK_TYPE_MAPPING[raw_type]
            if successor is None:
                continue
            link_type = successor
        else:
            link_type = raw_type

        source = normalize_artifact_type(row["source__artifact_type"])
        target = normalize_artifact_type(row["target__artifact_type"])
        if raw_type in SWAPPED_LEGACY_KEYS:
            source, target = target, source

        counter[(link_type, source, target)] += row["count"]

    return [
        {
            "link_type": link_type,
            "source_type": source,
            "target_type": target,
            "count": count,
        }
        for (link_type, source, target), count in sorted(counter.items())
    ]


def _is_covered(link_type: str, source: str, target: str) -> bool:
    definition = BUILTIN_LINK_TYPES.get(link_type)
    if definition is None:
        return False
    for pair in definition["allowed_pairs"]:
        if pair["source_type"] in ("*", source) and pair["target_type"] in ("*", target):
            return True
    return False


def uncovered_triples(observed: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return the observed triples no built-in ``allowed_pairs`` entry matches."""
    return [
        triple
        for triple in observed
        if not _is_covered(
            triple["link_type"], triple["source_type"], triple["target_type"]
        )
    ]


class Command(BaseCommand):
    help = (
        "Inventory the (link_type, source_type, target_type) triples in the "
        "TraceLink table, mapped through the new link-type catalog."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            dest="json_path",
            default=None,
            help="Write the full report to this path as JSON.",
        )

    def handle(self, *args, **options):
        observed = collect_observed_triples()
        uncovered = uncovered_triples(observed)

        self.stdout.write(f"Observed triples: {len(observed)}")
        for triple in observed:
            self.stdout.write(
                f"  {triple['link_type']}: {triple['source_type']} -> "
                f"{triple['target_type']}  ({triple['count']} rows)"
            )

        if uncovered:
            self.stdout.write(
                self.style.WARNING(
                    f"\n{len(uncovered)} triple(s) are NOT covered by the built-in "
                    f"allowed_pairs and would be rejected once validation is "
                    f"always-on:"
                )
            )
            for triple in uncovered:
                self.stdout.write(
                    self.style.WARNING(
                        f"  {triple['link_type']}: {triple['source_type']} -> "
                        f"{triple['target_type']}  ({triple['count']} rows)"
                    )
                )
        else:
            self.stdout.write(self.style.SUCCESS("\nAll observed triples are covered."))

        if options["json_path"]:
            payload = {"observed": observed, "uncovered": uncovered}
            with open(options["json_path"], "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
            self.stdout.write(f"\nReport written to {options['json_path']}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST link_types/tests/test_inventory_command.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/link_types/management backend/link_types/tests/test_inventory_command.py
git commit -m "feat(link-types): add link-type inventory command for the validation flip"
```

---

### Task 10: Grandfather the observed-but-uncovered pairs

**Files:**
- Create: `backend/link_types/grandfathered.py`
- Create: `backend/link_types/migrations/0004_grandfather_observed_pairs.py`
- Test: `backend/link_types/tests/test_grandfathered.py`

**Interfaces:**
- Consumes: Task 9's `--json` output, `link_types.schema.validate_definition_json`
- Produces: `GRANDFATHERED_PAIRS: dict[str, list[dict[str, str]]]` — link-type key → extra `allowed_pairs` entries; `apply_grandfathered_pairs(definition: dict, key: str) -> dict`

**Prerequisite:** run Task 9's command against a production-shaped database and paste the `uncovered` list into `GRANDFATHERED_PAIRS`. Do not guess the contents. If OFFENE FRAGE 1 is answered "hard-break instead of grandfather", skip this task entirely and delete its migration from the sequence.

- [ ] **Step 1: Write the failing test**

```python
# backend/link_types/tests/test_grandfathered.py
"""Observed-but-uncovered pairs are added to the built-ins, never invented."""
from __future__ import annotations

import pytest

from link_types.builtin import BUILTIN_LINK_TYPES, builtin_definition
from link_types.grandfathered import (
    GRANDFATHERED_PAIRS,
    apply_grandfathered_pairs,
)
from link_types.schema import validate_definition_json


def test_every_grandfathered_key_is_a_known_link_type():
    assert set(GRANDFATHERED_PAIRS) <= set(BUILTIN_LINK_TYPES)


def test_every_grandfathered_pair_has_both_sides():
    for key, pairs in GRANDFATHERED_PAIRS.items():
        for pair in pairs:
            assert set(pair) == {"source_type", "target_type"}, key
            assert pair["source_type"] and pair["target_type"], key


def test_applying_grandfathered_pairs_keeps_the_definition_valid():
    for key in BUILTIN_LINK_TYPES:
        merged = apply_grandfathered_pairs(builtin_definition(key), key)
        assert validate_definition_json(merged, key=key)


def test_applying_is_additive_and_never_removes_a_builtin_pair():
    for key in BUILTIN_LINK_TYPES:
        original = builtin_definition(key)["allowed_pairs"]
        merged = apply_grandfathered_pairs(builtin_definition(key), key)["allowed_pairs"]
        for pair in original:
            assert pair in merged, f"{key}: built-in pair {pair} was dropped"


def test_applying_does_not_duplicate_an_already_covered_pair():
    key = "verifies"
    definition = builtin_definition(key)
    merged = apply_grandfathered_pairs(definition, key)["allowed_pairs"]
    assert len(merged) == len({(p["source_type"], p["target_type"]) for p in merged})


def test_applying_is_a_no_op_for_a_key_with_no_grandfathered_pairs():
    key = next(k for k in BUILTIN_LINK_TYPES if k not in GRANDFATHERED_PAIRS)
    assert (
        apply_grandfathered_pairs(builtin_definition(key), key)["allowed_pairs"]
        == builtin_definition(key)["allowed_pairs"]
    )


def test_applying_does_not_mutate_the_input():
    key = next(iter(GRANDFATHERED_PAIRS), "verifies")
    definition = builtin_definition(key)
    before = len(definition["allowed_pairs"])
    apply_grandfathered_pairs(definition, key)
    assert len(definition["allowed_pairs"]) == before
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST link_types/tests/test_grandfathered.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'link_types.grandfathered'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/link_types/grandfathered.py
"""Endpoint pairs that exist in live data but no built-in type allows.

Populated from ``python manage.py inventory_link_types --json ...`` run
against production-shaped data — **not** invented. See OFFENE FRAGE 1 of
docs/superpowers/plans/2026-09-03-traceability-semantik.md: the spec's
eight-type matrix does not mention Goal, MainGoal, Issue or Interview, yet
links involving them exist and are legitimate (Goal<->Requirement links are
the reason ``TraceLinkService._resolve_artifact`` gained its Goal branch in
fix #237). Without this file, flipping validation to always-on would make
every one of those rows uncreatable.

Every entry here is a documented compromise, not a design statement: the pair
is allowed because it already exists, and it should be revisited whenever the
owning artifact type gets a proper semantic home.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List

#: link-type key -> additional allowed pairs, verbatim from the inventory run.
#: REPLACE THE CONTENTS with the `uncovered` list from
#: `manage.py inventory_link_types --json`. The example below is the shape,
#: and is what the seeded demo data produces.
GRANDFATHERED_PAIRS: Dict[str, List[Dict[str, str]]] = {
    "references": [
        {"source_type": "*", "target_type": "Goal"},
        {"source_type": "*", "target_type": "MainGoal"},
        {"source_type": "*", "target_type": "Issue"},
    ],
    "derives-from": [
        {"source_type": "Requirement", "target_type": "Goal"},
        {"source_type": "Goal", "target_type": "MainGoal"},
    ],
}


def apply_grandfathered_pairs(definition: Dict[str, Any], key: str) -> Dict[str, Any]:
    """Return a copy of *definition* with the grandfathered pairs appended.

    Additive and duplicate-free: a built-in pair is never dropped, and a pair
    already covered is not repeated.
    """
    extra = GRANDFATHERED_PAIRS.get(key)
    if not extra:
        return copy.deepcopy(definition)

    merged = copy.deepcopy(definition)
    pairs = merged.setdefault("allowed_pairs", [])
    seen = {(p["source_type"], p["target_type"]) for p in pairs}
    for pair in extra:
        signature = (pair["source_type"], pair["target_type"])
        if signature not in seen:
            pairs.append(dict(pair))
            seen.add(signature)
    return merged


__all__ = ["GRANDFATHERED_PAIRS", "apply_grandfathered_pairs"]
```

```python
# backend/link_types/migrations/0004_grandfather_observed_pairs.py
"""Extend the seeded definitions with the pairs live data already relies on.

Runs after ``0003_seed_builtin_link_types``. Only ``is_customized=False`` rows
are touched: a workspace that has already tailored a type has made a
deliberate decision that a migration must not overwrite.
"""
from __future__ import annotations

import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def apply_pairs(apps, schema_editor):
    from link_types.grandfathered import GRANDFATHERED_PAIRS, apply_grandfathered_pairs

    GlobalLinkTypeDefinition = apps.get_model("link_types", "GlobalLinkTypeDefinition")
    WorkspaceLinkTypeDefinition = apps.get_model(
        "link_types", "WorkspaceLinkTypeDefinition"
    )

    updated = 0
    for key in GRANDFATHERED_PAIRS:
        for row in GlobalLinkTypeDefinition.objects.filter(key=key):
            row.definition_json = apply_grandfathered_pairs(row.definition_json, key)
            row.save(update_fields=["definition_json"])
            updated += 1
        for row in WorkspaceLinkTypeDefinition.objects.filter(
            key=key, is_customized=False
        ):
            row.definition_json = apply_grandfathered_pairs(row.definition_json, key)
            row.save(update_fields=["definition_json"])
            updated += 1

    logger.info("LinkTypeCatalog: grandfathered pairs applied to %d rows.", updated)


class Migration(migrations.Migration):

    dependencies = [("link_types", "0003_seed_builtin_link_types")]

    operations = [
        migrations.RunPython(apply_pairs, migrations.RunPython.noop),
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST link_types/tests/test_grandfathered.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/link_types/grandfathered.py backend/link_types/migrations/0004_grandfather_observed_pairs.py backend/link_types/tests/test_grandfathered.py
git commit -m "feat(link-types): grandfather endpoint pairs present in live data"
```

---

### Task 11: Wire `TraceLinkService` to the catalog, delete the `se_mode` gate

**Files:**
- Modify: `backend/application/trace_link_service.py:258-333` (delete `_check_se_semantics`)
- Modify: `backend/application/trace_link_service.py:336-410` (`create_trace_link` gates)
- Modify: `backend/application/trace_link_service.py:1255-1260` (`__all__`)
- Modify: `backend/traceability/types.py:81-177` (delete the SE matrix), `:330-348` (`__all__`)
- Test: `backend/application/tests/test_trace_link_catalog_validation.py`
- Test: existing `backend/application/tests/test_trace_link_service.py` (adjust)

**Interfaces:**
- Consumes: `link_types.catalog.validate_link_pair` (Task 5)
- Produces: `TraceLinkService._check_link_pair(source_artifact_id, target_artifact_id, link_type, *, source_artifact, target_artifact, manual) -> None`; `create_trace_link` now raises `ValidationError` for any pair the workspace catalog rejects, in every terminology profile

**Breaking change:** `traceability.types.check_se_link_semantics`, `SE_LINK_SEMANTICS`, `SE_CORE_ARTIFACT_TYPES`, `SAME_TYPE` and `VALID_LINK_TYPES`/`MANUAL_LINK_TYPES` as validation authorities are removed. `LinkType` survives as a convenience enum of the eight core keys for code that wants a symbol instead of a string literal.

- [ ] **Step 1: Write the failing test**

```python
# backend/application/tests/test_trace_link_catalog_validation.py
"""create_trace_link validates against the workspace catalog, always."""
from __future__ import annotations

import uuid

import pytest

from application.trace_link_service import TraceLinkService
from link_types.workspace_store import provision_workspace_link_types
from persistence.errors import ValidationError
from persistence.tenancy import TenantContext


@pytest.fixture
def env(db):
    from auth_tenancy.models import AuthContext
    from persistence.models import Artifact, Tenant, Workspace
    from presets.models import WorkspacePresetConfig

    tenant = Tenant.objects.create(name="catalog-validation")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="ws")
    provision_workspace_link_types(workspace_id=ws.id, tenant_id=tenant.id)

    def artifact(kind: str) -> Artifact:
        return Artifact.objects.create(
            tenant=tenant, workspace=ws, artifact_type=kind, title=f"{kind}"
        )

    ctx = AuthContext(
        user_id=uuid.uuid4(), tenant_id=tenant.id, workspace_id=ws.id, roles=["admin"]
    )
    yield {
        "tenant": tenant,
        "workspace": ws,
        "ctx": ctx,
        "artifact": artifact,
        "preset_model": WorkspacePresetConfig,
    }
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_a_valid_link_is_created(env):
    svc = TraceLinkService()
    tc, req = env["artifact"]("TestCase"), env["artifact"]("Requirement")
    link = svc.create_trace_link(tc.id, req.id, "verifies", env["ctx"])
    assert link.link_type == "verifies"


@pytest.mark.django_db
def test_verifies_from_a_risk_is_rejected_in_dev_mode_too(env):
    """Audit finding U2: Risk was outside SE_CORE_ARTIFACT_TYPES and passed."""
    env["preset_model"].objects.update_or_create(
        workspace_id=env["workspace"].id,
        defaults={"terminology_profile": "dev_mode"},
    )
    svc = TraceLinkService()
    risk, req = env["artifact"]("Risk"), env["artifact"]("Requirement")
    with pytest.raises(ValidationError, match="verifies"):
        svc.create_trace_link(risk.id, req.id, "verifies", env["ctx"])


@pytest.mark.django_db
def test_validation_applies_without_any_preset_config_row(env):
    """No WorkspacePresetConfig used to mean 'skip enforcement' entirely."""
    env["preset_model"].objects.filter(workspace_id=env["workspace"].id).delete()
    svc = TraceLinkService()
    risk, req = env["artifact"]("Risk"), env["artifact"]("Requirement")
    with pytest.raises(ValidationError):
        svc.create_trace_link(risk.id, req.id, "verifies", env["ctx"])


@pytest.mark.django_db
def test_a_retired_link_type_is_rejected(env):
    svc = TraceLinkService()
    arch, req = env["artifact"]("ArchitectureElement"), env["artifact"]("Requirement")
    with pytest.raises(ValidationError, match="Unknown link type 'satisfies'"):
        svc.create_trace_link(arch.id, req.id, "satisfies", env["ctx"])


@pytest.mark.django_db
def test_allocated_to_only_runs_requirement_to_architecture(env):
    svc = TraceLinkService()
    req, arch = env["artifact"]("Requirement"), env["artifact"]("ArchitectureElement")
    assert svc.create_trace_link(req.id, arch.id, "allocated-to", env["ctx"])
    with pytest.raises(ValidationError, match="allocated-to"):
        svc.create_trace_link(arch.id, req.id, "allocated-to", env["ctx"])


@pytest.mark.django_db
def test_architecture_to_architecture_allocation_is_gone(env):
    svc = TraceLinkService()
    a, b = env["artifact"]("ArchitectureElement"), env["artifact"]("ArchitectureElement")
    with pytest.raises(ValidationError, match="allocated-to"):
        svc.create_trace_link(a.id, b.id, "allocated-to", env["ctx"])


@pytest.mark.django_db
def test_derives_from_now_accepts_architecture_pairs(env):
    """Inherited from the retired `refines` type."""
    svc = TraceLinkService()
    a, b = env["artifact"]("ArchitectureElement"), env["artifact"]("ArchitectureElement")
    assert svc.create_trace_link(a.id, b.id, "derives-from", env["ctx"])


@pytest.mark.django_db
def test_diagram_ref_is_still_rejected_on_the_manual_path(env):
    svc = TraceLinkService()
    diagram, req = env["artifact"]("Diagram"), env["artifact"]("Requirement")
    with pytest.raises(ValidationError, match="system-managed"):
        svc.create_trace_link(diagram.id, req.id, "diagram-ref", env["ctx"])


@pytest.mark.django_db
def test_a_deactivated_type_cannot_be_used(env):
    from link_types.builtin import builtin_definition
    from link_types.workspace_store import WorkspaceLinkTypeDefinitionStore

    disabled = builtin_definition("mitigates")
    disabled["active"] = False
    WorkspaceLinkTypeDefinitionStore().update(
        env["tenant"].id, env["workspace"].id, "mitigates", disabled
    )

    svc = TraceLinkService()
    risk, req = env["artifact"]("Risk"), env["artifact"]("Requirement")
    with pytest.raises(ValidationError, match="Unknown link type"):
        svc.create_trace_link(risk.id, req.id, "mitigates", env["ctx"])


@pytest.mark.django_db
def test_a_workspace_override_widens_what_is_accepted(env):
    from link_types.builtin import builtin_definition
    from link_types.workspace_store import WorkspaceLinkTypeDefinitionStore

    widened = builtin_definition("mitigates")
    widened["allowed_pairs"].append(
        {"source_type": "Risk", "target_type": "TestCase"}
    )
    WorkspaceLinkTypeDefinitionStore().update(
        env["tenant"].id, env["workspace"].id, "mitigates", widened
    )

    svc = TraceLinkService()
    risk, tc = env["artifact"]("Risk"), env["artifact"]("TestCase")
    assert svc.create_trace_link(risk.id, tc.id, "mitigates", env["ctx"])


def test_the_se_matrix_is_gone():
    import traceability.types as types

    for removed in (
        "SE_LINK_SEMANTICS",
        "SE_CORE_ARTIFACT_TYPES",
        "SAME_TYPE",
        "check_se_link_semantics",
    ):
        assert not hasattr(types, removed), f"{removed} must be deleted"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST application/tests/test_trace_link_catalog_validation.py -v`
Expected: FAIL — `test_verifies_from_a_risk_is_rejected_in_dev_mode_too` passes creation instead of raising; `test_the_se_matrix_is_gone` fails on `SE_LINK_SEMANTICS`

- [ ] **Step 3: Write minimal implementation**

In `backend/application/trace_link_service.py`, replace `_check_se_semantics` (lines 258-333) with:

```python
    def _check_link_pair(
        self,
        source_artifact_id: UUID,
        target_artifact_id: UUID,
        link_type: str,
        *,
        source_artifact: Optional["Artifact"] = None,
        target_artifact: Optional["Artifact"] = None,
        manual: bool = True,
    ) -> None:
        """Validate a link against the workspace's link-type catalog.

        Replaces the former ``_check_se_semantics``. Two escape hatches are
        gone on purpose (spec section 3.2, "gilt immer"):

        * the ``se_mode`` probe — a dev_mode or unconfigured workspace used to
          skip enforcement entirely;
        * the ``SE_CORE_ARTIFACT_TYPES`` allow-list — a Risk endpoint used to
          pass unchecked, which is audit finding U2 exactly.

        The ids stay authoritative: a passed-in row is an optimisation, never
        a substitute. A mismatch drops the row and re-reads the real one —
        this is a validation gate, and checking the wrong endpoints silently
        is worse than one extra SELECT.

        Args:
            source_artifact_id: Resolved source Artifact id.
            target_artifact_id: Resolved target Artifact id.
            link_type: The catalog key under validation.
            source_artifact: Already-loaded source row, if the caller has one.
            target_artifact: Same for the target endpoint.
            manual: False only for system writers (the diagram reconciler),
                which may write ``system_owned`` types.

        Raises:
            ValidationError: Unknown/inactive type, a system-owned type on the
                manual path, or a disallowed endpoint pair.
            NotFoundError: Either endpoint does not exist.
        """
        from link_types.catalog import validate_link_pair
        from persistence.models import Artifact

        source = source_artifact
        if source is not None and str(source.id) != str(source_artifact_id):
            source = None
        if source is None:
            source = Artifact.objects.filter(id=source_artifact_id).first()

        target = target_artifact
        if target is not None and str(target.id) != str(target_artifact_id):
            target = None
        if target is None:
            target = Artifact.objects.filter(id=target_artifact_id).first()

        # Unlike the old permissive fallback, a missing endpoint is no longer
        # a reason to skip the gate: it is a hard error raised here rather
        # than an opaque IntegrityError further down.
        if source is None:
            raise NotFoundError("Source entity not found")
        if target is None:
            raise NotFoundError("Target entity not found")

        validate_link_pair(
            source.workspace_id,
            link_type,
            source.artifact_type,
            target.artifact_type,
            manual=manual,
        )
```

In `create_trace_link`, delete the `VALID_LINK_TYPES` check (lines 366-370) and the hardcoded `DIAGRAM_REF` rejection (lines 372-385) — both are now decided by the catalog — and replace the `_check_se_semantics(...)` call (lines 395-403) with:

```python
        # Catalog validation: link type must exist, be active, be manually
        # creatable, and allow this endpoint pair. Applies to every workspace
        # and every artifact type — the se_mode gate and the "non-core types
        # pass unchecked" escape are gone (spec section 3.2).
        self._check_link_pair(
            resolved_source,
            resolved_target,
            link_type,
            source_artifact=source_artifact,
            target_artifact=target_artifact,
            manual=True,
        )
```

In `backend/traceability/types.py`:
- shrink `LinkType` to the eight core members (`DERIVES_FROM`, `DECOMPOSES`, `ALLOCATED_TO`, `VERIFIES`, `DECIDES`, `MITIGATES`, `REFERENCES`, `DIAGRAM_REF`) and add to its docstring: *"Convenience symbols for the eight built-in keys. NOT the validation authority — that is `link_types.catalog.resolve_catalog`, which is per-workspace and tenant-extensible."*
- delete `SE_CORE_ARTIFACT_TYPES`, `SAME_TYPE`, `SE_LINK_SEMANTICS`, `check_se_link_semantics`, `normalize_artifact_type` (the last one moved to `link_types.catalog`), `VALID_LINK_TYPES` and `MANUAL_LINK_TYPES`, and the module-level `_REQ`/`_ARCH`/`_TC`/`_SN`/`_DIAG` aliases
- drop the same names from `__all__`

In `backend/application/trace_link_service.py`, drop `VALID_LINK_TYPES`/`MANUAL_LINK_TYPES` from the imports and from `__all__`.

Adjust the four legacy expectations in `backend/application/tests/test_trace_link_service.py`: the `"parent-child"` literal at line 64 becomes `"decomposes"`, and any assertion that a dev_mode workspace skips endpoint validation is inverted.

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST application/tests/test_trace_link_catalog_validation.py application/tests/test_trace_link_service.py traceability/ -v`
Expected: PASS (11 new tests pass; the `traceability` suite stays green apart from the SE-matrix tests deleted with the matrix)

- [ ] **Step 5: Commit**

```bash
git add backend/application/trace_link_service.py backend/traceability/types.py backend/application/tests/
git commit -m "feat(link-types): validate every trace link against the workspace catalog"
```

---

## Phase C — `TraceLink` extension and the suspect engine

### Task 12: `TraceLink.rationale` / `suspect_flagged_at` / `suspect_source_change` and `Artifact.copied_from`

**Files:**
- Modify: `backend/persistence/models.py:1360-1406` (`TraceLink` fields)
- Modify: `backend/persistence/models.py:819-860` (`Artifact.copied_from`)
- Modify: `backend/persistence/models.py:715-719` (`Workspace.decomposition_link_type` default)
- Create: `backend/persistence/migrations/00XX_tracelink_semantics_fields.py` (generated; `XX` = next free number)
- Test: `backend/persistence/tests/test_tracelink_semantics_fields.py`

**Interfaces:**
- Consumes: nothing
- Produces: `TraceLink.rationale: str` (blank-able TextField), `TraceLink.suspect_flagged_at: datetime | None`, `TraceLink.suspect_source_change: UUID | None`, `Artifact.copied_from: Artifact | None` (self-FK, `related_name="copies"`, `on_delete=SET_NULL`)

`suspect_source_change` is a `UUIDField`, not a `ForeignKey` — see Decision 1.

- [ ] **Step 1: Write the failing test**

```python
# backend/persistence/tests/test_tracelink_semantics_fields.py
"""New TraceLink semantics fields and Artifact.copied_from."""
from __future__ import annotations

import uuid

import pytest
from django.utils import timezone

from persistence.tenancy import TenantContext


@pytest.fixture
def env(db):
    from persistence.models import Artifact, Tenant, Workspace

    tenant = Tenant.objects.create(name="semantics-fields")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="ws")

    def artifact(kind: str = "Requirement") -> Artifact:
        return Artifact.objects.create(
            tenant=tenant, workspace=ws, artifact_type=kind, title=kind
        )

    yield {"tenant": tenant, "workspace": ws, "artifact": artifact}
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_new_trace_link_fields_default_to_empty(env):
    from persistence.models import TraceLink

    link = TraceLink.objects.create(
        tenant=env["tenant"],
        source=env["artifact"](),
        target=env["artifact"](),
        link_type="derives-from",
    )
    assert link.rationale == ""
    assert link.suspect_flagged_at is None
    assert link.suspect_source_change is None


@pytest.mark.django_db
def test_rationale_round_trips(env):
    from persistence.models import TraceLink

    link = TraceLink.objects.create(
        tenant=env["tenant"],
        source=env["artifact"](),
        target=env["artifact"](),
        link_type="derives-from",
        rationale="Derived during the 2026-Q3 decomposition workshop.",
    )
    link.refresh_from_db()
    assert link.rationale.startswith("Derived during")


@pytest.mark.django_db
def test_suspect_marker_fields_round_trip(env):
    from persistence.models import TraceLink

    audit_id = uuid.uuid4()
    now = timezone.now()
    link = TraceLink.objects.create(
        tenant=env["tenant"],
        source=env["artifact"](),
        target=env["artifact"](),
        link_type="derives-from",
        suspect_flagged_at=now,
        suspect_source_change=audit_id,
    )
    link.refresh_from_db()
    assert link.suspect_flagged_at == now
    assert link.suspect_source_change == audit_id


@pytest.mark.django_db
def test_copied_from_links_two_artifacts(env):
    original = env["artifact"]()
    copy = env["artifact"]()
    copy.copied_from = original
    copy.save(update_fields=["copied_from"])
    copy.refresh_from_db()
    assert copy.copied_from_id == original.id
    assert list(original.copies.all()) == [copy]


@pytest.mark.django_db
def test_deleting_the_original_keeps_the_copy(env):
    original = env["artifact"]()
    copy = env["artifact"]()
    copy.copied_from = original
    copy.save(update_fields=["copied_from"])
    original.delete()
    copy.refresh_from_db()
    assert copy.copied_from_id is None


@pytest.mark.django_db
def test_workspace_decomposition_default_is_no_longer_a_retired_type():
    from persistence.models import Workspace

    field = Workspace._meta.get_field("decomposition_link_type")
    assert field.default == "decomposes"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST persistence/tests/test_tracelink_semantics_fields.py -v`
Expected: FAIL with `TypeError: TraceLink() got unexpected keyword arguments: 'rationale'`

- [ ] **Step 3: Write minimal implementation**

In `backend/persistence/models.py`, inside `TraceLink` after the `embedding` field:

```python
    rationale = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Q1.6: why this link exists. A link type alone does not say why "
            "*these two* artifacts are connected; without it a reviewer has "
            "to reconstruct the intent from the two titles."
        ),
    )
    suspect_flagged_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "Set by the suspect-propagation engine "
            "(application.trace_link_service.TraceLinkService."
            "propagate_suspect_status) when this link caused the other "
            "endpoint to be flagged suspect. NULL means this link has not "
            "triggered a flag since the last review."
        ),
    )
    suspect_source_change = models.UUIDField(
        null=True,
        blank=True,
        help_text=(
            "audit.AuditEntry.id of the change that triggered the flag above. "
            "Deliberately a plain UUID rather than a ForeignKey: audit_entry "
            "is append-only and slated for monthly RANGE partitioning "
            "(audit/migrations/0001_initial.py), which a real FK would "
            "permanently block because Postgres requires the partition key in "
            "the referenced primary key. No cascade semantics are needed — an "
            "audit entry is never deleted."
        ),
    )
```

In `Artifact`, after the `parent` field:

```python
    copied_from = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="copies",
        help_text=(
            "Provenance of a duplicated artifact. Replaces the retired "
            "'copy-of' TraceLink type: a copy has exactly one origin, so a "
            "1:1 field states the invariant that an N:M link table could not. "
            "SET_NULL — deleting the original must not delete its copies, "
            "which are independent artifacts."
        ),
    )
```

Change the `Workspace.decomposition_link_type` default:

```python
    decomposition_link_type = models.CharField(
        max_length=50,
        default="decomposes",
        help_text=(
            "Default link type used when decomposing requirements. NOTE: "
            "RequirementService.decompose hardcodes 'decomposes' and does not "
            "read this field (UMSETZUNGSPLAN_SYSENG_2.0 section 1.4); the "
            "default was 'parent-child', a link type that no longer exists."
        ),
    )
```

Generate the migration:

```bash
docker compose -f deploy/docker-compose.yml --project-directory . run --rm backend \
  python manage.py makemigrations persistence --name tracelink_semantics_fields
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST persistence/tests/test_tracelink_semantics_fields.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/persistence/models.py backend/persistence/migrations backend/persistence/tests/test_tracelink_semantics_fields.py
git commit -m "feat(traceability): add TraceLink rationale/suspect markers and Artifact.copied_from"
```

---

### Task 13: Expose the new fields through the REST serializer

**Files:**
- Modify: `backend/rest_api/serializers.py:1021-1080` (`TraceLinkSerializer`)
- Test: `backend/rest_api/tests/test_trace_link_serializer_fields.py`

**Interfaces:**
- Consumes: Task 12's model fields
- Produces: `TraceLinkSerializer` accepts `rationale` on write and returns `rationale`, `suspect_flagged_at`, `suspect_source_change` on read

`rationale` is free text on a trust boundary, so it uses `SanitizedCharField` with an explicit `max_length` — an unbounded TextField-backed field is a DoS surface (the same reason `change_reason` is capped at 2000).

- [ ] **Step 1: Write the failing test**

```python
# backend/rest_api/tests/test_trace_link_serializer_fields.py
"""TraceLinkSerializer exposes rationale and the suspect markers."""
from __future__ import annotations

import uuid

import pytest
from django.utils import timezone

from rest_api.serializers import TraceLinkSerializer


class _Link:
    def __init__(self, **kwargs):
        self.id = uuid.uuid4()
        self.source_id = uuid.uuid4()
        self.target_id = uuid.uuid4()
        self.link_type = "derives-from"
        self.version = 1
        self.created_at = timezone.now()
        self.rationale = ""
        self.suspect_flagged_at = None
        self.suspect_source_change = None
        for key, value in kwargs.items():
            setattr(self, key, value)


def test_rationale_is_returned():
    data = TraceLinkSerializer(_Link(rationale="workshop decision")).data
    assert data["rationale"] == "workshop decision"


def test_suspect_markers_are_returned():
    audit_id = uuid.uuid4()
    flagged = timezone.now()
    data = TraceLinkSerializer(
        _Link(suspect_flagged_at=flagged, suspect_source_change=audit_id)
    ).data
    assert data["suspect_flagged_at"] is not None
    assert str(data["suspect_source_change"]) == str(audit_id)


def test_rationale_is_writable():
    serializer = TraceLinkSerializer(
        data={
            "source_id": str(uuid.uuid4()),
            "target_id": str(uuid.uuid4()),
            "link_type": "derives-from",
            "rationale": "because the stakeholder asked for it",
        }
    )
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["rationale"] == "because the stakeholder asked for it"


def test_rationale_is_optional():
    serializer = TraceLinkSerializer(
        data={
            "source_id": str(uuid.uuid4()),
            "target_id": str(uuid.uuid4()),
            "link_type": "derives-from",
        }
    )
    assert serializer.is_valid(), serializer.errors


def test_rationale_is_length_capped():
    serializer = TraceLinkSerializer(
        data={
            "source_id": str(uuid.uuid4()),
            "target_id": str(uuid.uuid4()),
            "link_type": "derives-from",
            "rationale": "x" * 2001,
        }
    )
    assert not serializer.is_valid()
    assert "rationale" in serializer.errors


def test_suspect_markers_are_read_only():
    serializer = TraceLinkSerializer(
        data={
            "source_id": str(uuid.uuid4()),
            "target_id": str(uuid.uuid4()),
            "link_type": "derives-from",
            "suspect_flagged_at": timezone.now().isoformat(),
            "suspect_source_change": str(uuid.uuid4()),
        }
    )
    assert serializer.is_valid(), serializer.errors
    assert "suspect_flagged_at" not in serializer.validated_data
    assert "suspect_source_change" not in serializer.validated_data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST rest_api/tests/test_trace_link_serializer_fields.py -v`
Expected: FAIL with `KeyError: 'rationale'`

- [ ] **Step 3: Write minimal implementation**

In `backend/rest_api/serializers.py`, inside `TraceLinkSerializer` after the `link_type` field:

```python
    # Q1.6: why these two artifacts are connected. Free text on a trust
    # boundary, so sanitized and capped like change_reason (B006/#104) — an
    # unbounded TextField-backed field accepts unbounded payloads.
    rationale = SanitizedCharField(
        required=False,
        allow_blank=True,
        max_length=2000,
        help_text="Why this link exists (optional, free text).",
    )
    # Written only by TraceLinkService.propagate_suspect_status.
    suspect_flagged_at = serializers.DateTimeField(read_only=True, allow_null=True)
    suspect_source_change = serializers.UUIDField(read_only=True, allow_null=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST rest_api/tests/test_trace_link_serializer_fields.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/rest_api/serializers.py backend/rest_api/tests/test_trace_link_serializer_fields.py
git commit -m "feat(traceability): expose link rationale and suspect markers via REST"
```

---

### Task 14: Rule-driven suspect propagation (closes #849 structurally)

**Files:**
- Modify: `backend/application/trace_link_service.py:1175-1251` (rewrite `propagate_suspect_status`)
- Test: `backend/application/tests/test_suspect_propagation.py`
- Test: rewrite `backend/application/tests/test_trace_link_service.py:955-1073` (the four SN-30 tests)

**Interfaces:**
- Consumes: `link_types.catalog.resolve_catalog` (Task 5), `TraceLink.suspect_flagged_at`/`suspect_source_change` (Task 12)
- Produces: `TraceLinkService.propagate_suspect_status(source_id: UUID, ctx: AuthContext, *, audit_entry_id: UUID | None = None) -> int` — returns the number of artifacts flagged

**Behaviour changes (both deliberate, both in the commit message):**
1. **One hop, not the transitive hull.** Today's implementation walks the full recursive-CTE upstream closure and flags everything it reaches, regardless of link type. Spec section 5 describes a single hop over links that touch the changed artifact. `settings.SUSPECT_PROPAGATION_MAX_DEPTH` becomes unused and its handling is deleted.
2. **Direction now depends on `suspect_rule`, not on a fixed "upstream" assumption.** `allocated-to` propagates source→target; the old code could only ever propagate target→source.

Rule dispatch (see Decision 2 — `parent_change_flags_children` and `source_change_flags_target` share one branch):

| `suspect_rule` | changed artifact is the link's | flag the link's |
|---|---|---|
| `target_change_flags_source` | `target` | `source` |
| `source_change_flags_target` | `source` | `target` |
| `parent_change_flags_children` | `source` (= parent, per the direction table) | `target` (= child) |
| `none` | — | nothing |

- [ ] **Step 1: Write the failing test**

```python
# backend/application/tests/test_suspect_propagation.py
"""Suspect propagation dispatches on each link type's suspect_rule."""
from __future__ import annotations

import uuid

import pytest

from application.trace_link_service import TraceLinkService
from link_types.workspace_store import provision_workspace_link_types
from persistence.tenancy import TenantContext


@pytest.fixture
def env(db):
    from auth_tenancy.models import AuthContext
    from persistence.models import (
        ArchitectureElement,
        Artifact,
        Requirement,
        Tenant,
        TestCase,
        Workspace,
    )

    tenant = Tenant.objects.create(name="suspect")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="ws")
    provision_workspace_link_types(workspace_id=ws.id, tenant_id=tenant.id)

    def requirement(title="req"):
        art = Artifact.objects.create(
            tenant=tenant, workspace=ws, artifact_type="Requirement", title=title
        )
        return Requirement.objects.create(
            tenant=tenant, workspace=ws, artifact=art, title=title, suspect=False
        )

    def testcase(title="tc"):
        art = Artifact.objects.create(
            tenant=tenant, workspace=ws, artifact_type="TestCase", title=title
        )
        return TestCase.objects.create(
            tenant=tenant, workspace=ws, artifact=art, title=title, suspect=False
        )

    def architecture(title="arch"):
        art = Artifact.objects.create(
            tenant=tenant, workspace=ws, artifact_type="ArchitectureElement", title=title
        )
        return ArchitectureElement.objects.create(
            tenant=tenant, workspace=ws, artifact=art, name=title, suspect=False
        )

    ctx = AuthContext(
        user_id=uuid.uuid4(), tenant_id=tenant.id, workspace_id=ws.id, roles=["admin"]
    )
    yield {
        "tenant": tenant,
        "ctx": ctx,
        "requirement": requirement,
        "testcase": testcase,
        "architecture": architecture,
    }
    TenantContext.clear_tenant()


def _link(env, source, target, link_type):
    from persistence.models import TraceLink

    return TraceLink.objects.create(
        tenant=env["tenant"],
        source_id=source.artifact_id,
        target_id=target.artifact_id,
        link_type=link_type,
    )


@pytest.mark.django_db
def test_target_change_flags_source_verifies(env):
    """Requirement changes -> its verifying TestCase becomes suspect."""
    req, tc = env["requirement"](), env["testcase"]()
    _link(env, tc, req, "verifies")

    flagged = TraceLinkService().propagate_suspect_status(req.artifact_id, env["ctx"])

    tc.refresh_from_db()
    assert flagged == 1
    assert tc.suspect is True


@pytest.mark.django_db
def test_source_change_flags_target_allocated_to(env):
    """Requirement changes -> the ArchitectureElement it is allocated to."""
    req, arch = env["requirement"](), env["architecture"]()
    _link(env, req, arch, "allocated-to")

    flagged = TraceLinkService().propagate_suspect_status(req.artifact_id, env["ctx"])

    arch.refresh_from_db()
    assert flagged == 1
    assert arch.suspect is True


@pytest.mark.django_db
def test_allocated_to_does_not_propagate_backwards(env):
    """The ArchitectureElement changing must NOT flag the Requirement."""
    req, arch = env["requirement"](), env["architecture"]()
    _link(env, req, arch, "allocated-to")

    flagged = TraceLinkService().propagate_suspect_status(arch.artifact_id, env["ctx"])

    req.refresh_from_db()
    assert flagged == 0
    assert req.suspect is False


@pytest.mark.django_db
def test_parent_change_flags_children_decomposes(env):
    parent, child = env["requirement"]("parent"), env["requirement"]("child")
    _link(env, parent, child, "decomposes")

    flagged = TraceLinkService().propagate_suspect_status(
        parent.artifact_id, env["ctx"]
    )

    child.refresh_from_db()
    assert flagged == 1
    assert child.suspect is True


@pytest.mark.django_db
def test_a_child_change_does_not_flag_its_parent(env):
    parent, child = env["requirement"]("parent"), env["requirement"]("child")
    _link(env, parent, child, "decomposes")

    assert (
        TraceLinkService().propagate_suspect_status(child.artifact_id, env["ctx"]) == 0
    )
    parent.refresh_from_db()
    assert parent.suspect is False


@pytest.mark.django_db
def test_rule_none_propagates_nothing(env):
    req, arch = env["requirement"](), env["architecture"]()
    _link(env, arch, req, "references")

    assert (
        TraceLinkService().propagate_suspect_status(req.artifact_id, env["ctx"]) == 0
    )
    arch.refresh_from_db()
    assert arch.suspect is False


@pytest.mark.django_db
def test_propagation_is_one_hop_only(env):
    """grandparent -> parent -> child: changing the grandparent stops at parent."""
    grand, parent, child = (
        env["requirement"]("g"),
        env["requirement"]("p"),
        env["requirement"]("c"),
    )
    _link(env, grand, parent, "decomposes")
    _link(env, parent, child, "decomposes")

    flagged = TraceLinkService().propagate_suspect_status(grand.artifact_id, env["ctx"])

    parent.refresh_from_db()
    child.refresh_from_db()
    assert flagged == 1
    assert parent.suspect is True
    assert child.suspect is False


@pytest.mark.django_db
def test_the_link_records_when_and_why_it_flagged(env):
    from persistence.models import TraceLink

    req, tc = env["requirement"](), env["testcase"]()
    link = _link(env, tc, req, "verifies")
    audit_id = uuid.uuid4()

    TraceLinkService().propagate_suspect_status(
        req.artifact_id, env["ctx"], audit_entry_id=audit_id
    )

    link.refresh_from_db()
    assert link.suspect_flagged_at is not None
    assert link.suspect_source_change == audit_id


@pytest.mark.django_db
def test_links_that_did_not_fire_keep_a_null_marker(env):
    from persistence.models import TraceLink

    req, arch = env["requirement"](), env["architecture"]()
    quiet = _link(env, arch, req, "references")

    TraceLinkService().propagate_suspect_status(req.artifact_id, env["ctx"])

    quiet.refresh_from_db()
    assert quiet.suspect_flagged_at is None


@pytest.mark.django_db
def test_the_changed_artifact_is_never_flagged_itself(env):
    req = env["requirement"]()
    _link(env, req, req, "derives-from")

    TraceLinkService().propagate_suspect_status(req.artifact_id, env["ctx"])

    req.refresh_from_db()
    assert req.suspect is False


@pytest.mark.django_db
def test_an_unknown_artifact_id_is_a_no_op(env):
    assert (
        TraceLinkService().propagate_suspect_status(uuid.uuid4(), env["ctx"]) == 0
    )


@pytest.mark.django_db
def test_a_deactivated_link_type_stops_propagating(env):
    from link_types.builtin import builtin_definition
    from link_types.workspace_store import WorkspaceLinkTypeDefinitionStore

    req, tc = env["requirement"](), env["testcase"]()
    _link(env, tc, req, "verifies")

    disabled = builtin_definition("verifies")
    disabled["active"] = False
    WorkspaceLinkTypeDefinitionStore().update(
        env["tenant"].id, req.workspace_id, "verifies", disabled
    )

    assert (
        TraceLinkService().propagate_suspect_status(req.artifact_id, env["ctx"]) == 0
    )
    tc.refresh_from_db()
    assert tc.suspect is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST application/tests/test_suspect_propagation.py -v`
Expected: FAIL — `test_source_change_flags_target_allocated_to` returns 0 (the old code only walks upstream), `test_propagation_is_one_hop_only` flags the child too, `test_the_link_records_when_and_why_it_flagged` fails on `TypeError: propagate_suspect_status() got an unexpected keyword argument 'audit_entry_id'`

- [ ] **Step 3: Write minimal implementation**

Replace the body of `propagate_suspect_status` in `backend/application/trace_link_service.py`:

```python
    def propagate_suspect_status(
        self,
        source_id: UUID,
        ctx: AuthContext,
        *,
        audit_entry_id: Optional[UUID] = None,
    ) -> int:
        """Flag the artifacts a change to *source_id* makes questionable (SN-30).

        Dispatches on each link type's ``suspect_rule`` from the workspace
        catalog rather than flooding a direction-agnostic transitive hull.
        This is the mechanism behind P0 issue #849: the ``suspect`` column and
        its serializer field already existed, but nothing ever consulted the
        link type, so ``allocated-to`` (which propagates source -> target)
        never fired at all and ``references`` fired when it should not have.

        Rule dispatch (direction convention: ``decomposes`` runs
        parent -> child, ``derives-from`` runs child -> parent — see
        ``traceability/audit/hierarchy.py``)::

            target_change_flags_source     changed == link.target -> flag source
            source_change_flags_target     changed == link.source -> flag target
            parent_change_flags_children   changed == link.source (the parent)
                                                            -> flag target (child)
            none                           nothing

        ``parent_change_flags_children`` shares the ``source_change_flags_target``
        branch on purpose: for a hierarchy link the parent *is* the source, so
        the two are the same traversal. It stays a distinct configurable value
        because it documents intent for hierarchy types.

        **One hop only.** The previous implementation walked the full recursive
        CTE closure; the spec describes a single hop, and each flagged artifact
        propagates further when *it* is edited. ``SUSPECT_PROPAGATION_MAX_DEPTH``
        is consequently no longer read.

        Args:
            source_id: The artifact (or business entity) that changed.
            ctx: Resolved AuthContext.
            audit_entry_id: ``audit.AuditEntry.id`` of the triggering change,
                recorded on every link that fired so a reviewer can see *which*
                edit made the other end suspect.

        Returns:
            Number of artifacts newly flagged suspect.
        """
        if ctx is not None:
            self._set_tenant_context(ctx)

        try:
            resolved_id = self._resolve_artifact_id(source_id)
        except NotFoundError:
            return 0

        from django.utils import timezone

        from link_types.catalog import resolve_catalog
        from persistence.models import (
            ArchitectureElement,
            Artifact,
            Requirement,
            TestCase,
            TraceLink,
        )

        artifact = Artifact.objects.filter(id=resolved_id).only("workspace_id").first()
        if artifact is None:
            return 0
        catalog = resolve_catalog(artifact.workspace_id)

        # One query for both directions; the rule decides which side counts.
        links = list(
            TraceLink.objects.filter(
                Q(source_id=resolved_id) | Q(target_id=resolved_id)
            ).only("id", "source_id", "target_id", "link_type")
        )

        dependent_ids: set[UUID] = set()
        fired_link_ids: list[UUID] = []

        for link in links:
            definition = catalog.get(link.link_type)
            if definition is None:
                continue  # unknown or deactivated type: no propagation
            rule = definition.get("suspect_rule", "none")
            if rule == "none":
                continue

            if rule == "target_change_flags_source":
                if link.target_id != resolved_id:
                    continue
                other_id = link.source_id
            elif rule in ("source_change_flags_target", "parent_change_flags_children"):
                # Identical traversal: for a hierarchy link the parent is the
                # source (see the direction table in the docstring).
                if link.source_id != resolved_id:
                    continue
                other_id = link.target_id
            else:
                logger.warning(
                    "Unknown suspect_rule '%s' on link type '%s'; skipping.",
                    rule,
                    link.link_type,
                )
                continue

            if other_id == resolved_id:
                continue  # self-link: never flag the changed artifact itself
            dependent_ids.add(other_id)
            fired_link_ids.append(link.id)

        if not dependent_ids:
            return 0

        flagged = 0
        for model in (Requirement, ArchitectureElement, TestCase):
            flagged += model.objects.filter(
                artifact_id__in=dependent_ids, suspect=False
            ).update(suspect=True)

        TraceLink.objects.filter(id__in=fired_link_ids).update(
            suspect_flagged_at=timezone.now(),
            suspect_source_change=audit_entry_id,
        )

        logger.info(
            "Suspect propagation from %s: %d artifact(s) flagged via %d link(s).",
            resolved_id,
            flagged,
            len(fired_link_ids),
        )
        return flagged
```

Add `from django.db.models import Q` to the module imports if it is not already there.

Rewrite the four SN-30 tests in `backend/application/tests/test_trace_link_service.py:955-1073`: they assert the old transitive-hull behaviour with mocked `traceability.services.query` and no longer describe the contract. Replace them with a single test asserting that `propagate_suspect_status` returns 0 for an unknown id — everything else is covered by `test_suspect_propagation.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST application/tests/test_suspect_propagation.py application/tests/test_trace_link_service.py -v`
Expected: PASS (12 passed in the new module; `test_trace_link_service.py` green)

- [ ] **Step 5: Commit**

```bash
git add backend/application/trace_link_service.py backend/application/tests/test_suspect_propagation.py backend/application/tests/test_trace_link_service.py
git commit -m "fix(traceability): drive suspect propagation from each link type's rule

Closes #849. Two deliberate behaviour changes: propagation is now one hop
instead of the full transitive upstream hull, and the direction follows the
link type's suspect_rule instead of a fixed upstream walk — so allocated-to
propagates source to target, which it never did before."
```

---

### Task 15: Write `Artifact.parent` in the same transaction as the `decomposes` link

**Files:**
- Modify: `backend/application/requirement_service.py:900-930`
- Test: `backend/application/tests/test_decompose_parent_coupling.py`

**Interfaces:**
- Consumes: `TraceLinkService.create_trace_link` (Task 11)
- Produces: `RequirementService.decompose` writes `child.artifact.parent = parent.artifact` and the `decomposes` TraceLink atomically — a failure in either rolls back both

Today the link creation is wrapped in `try/except Exception` and logged as a warning, so a workspace can end up with a `parent` FK and no link, or the reverse. Spec section 3.3 requires the two to move together. The existing unique constraint `uq_tracelink_edge` already prevents duplicate edges, so no new constraint is needed.

- [ ] **Step 1: Write the failing test**

```python
# backend/application/tests/test_decompose_parent_coupling.py
"""Artifact.parent and the decomposes link are written together or not at all."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from persistence.errors import ValidationError
from persistence.tenancy import TenantContext


@pytest.fixture
def env(db):
    from auth_tenancy.models import AuthContext
    from link_types.workspace_store import provision_workspace_link_types
    from persistence.models import Artifact, Requirement, Tenant, Workspace

    tenant = Tenant.objects.create(name="decompose-coupling")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="ws")
    provision_workspace_link_types(workspace_id=ws.id, tenant_id=tenant.id)

    art = Artifact.objects.create(
        tenant=tenant, workspace=ws, artifact_type="Requirement", title="parent"
    )
    parent = Requirement.objects.create(
        tenant=tenant, workspace=ws, artifact=art, title="parent"
    )
    ctx = AuthContext(
        user_id=uuid.uuid4(), tenant_id=tenant.id, workspace_id=ws.id, roles=["admin"]
    )
    yield {"tenant": tenant, "workspace": ws, "parent": parent, "ctx": ctx}
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_decompose_sets_both_the_parent_fk_and_the_link(env):
    from application.requirement_service import RequirementService
    from persistence.models import Artifact, TraceLink

    result = RequirementService().decompose(
        env["parent"].id, ["child A", "child B"], env["ctx"]
    )

    for child in result.children:
        artifact = Artifact.objects.get(id=child.artifact_id)
        assert artifact.parent_id == env["parent"].artifact_id
        assert TraceLink.objects.filter(
            source_id=env["parent"].artifact_id,
            target_id=child.artifact_id,
            link_type="decomposes",
        ).exists()


@pytest.mark.django_db
def test_a_failing_link_rolls_back_the_parent_fk(env):
    from application.requirement_service import RequirementService
    from persistence.models import Artifact, TraceLink

    with patch(
        "application.trace_link_service.TraceLinkService.create_trace_link",
        side_effect=ValidationError("catalog rejected it"),
    ):
        with pytest.raises(ValidationError):
            RequirementService().decompose(env["parent"].id, ["child"], env["ctx"])

    assert not Artifact.objects.filter(
        parent_id=env["parent"].artifact_id
    ).exists()
    assert not TraceLink.objects.filter(link_type="decomposes").exists()


@pytest.mark.django_db
def test_decompose_no_longer_swallows_link_failures(env):
    """The old code logged a warning and returned a half-built hierarchy."""
    from application.requirement_service import RequirementService

    with patch(
        "application.trace_link_service.TraceLinkService.create_trace_link",
        side_effect=ValidationError("catalog rejected it"),
    ):
        with pytest.raises(ValidationError):
            RequirementService().decompose(env["parent"].id, ["child"], env["ctx"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST application/tests/test_decompose_parent_coupling.py -v`
Expected: FAIL — `test_a_failing_link_rolls_back_the_parent_fk` finds an orphaned child artifact, because the `try/except Exception` swallows the error

- [ ] **Step 3: Write minimal implementation**

In `backend/application/requirement_service.py`, replace the `try/except Exception` around the link creation (lines 911-929) with:

```python
                # Spec section 3.3: Artifact.parent is the recursive-CTE
                # performance cache for the SAME relationship the 'decomposes'
                # link expresses. They must be written together — the previous
                # best-effort try/except left workspaces with a parent FK and
                # no link (invisible to the SE-Auditor) or the reverse
                # (invisible to every tree query). @atomic_transaction on
                # decompose() makes this rollback-consistent.
                child_artifact = child_req.artifact
                child_artifact.parent_id = parent_req.artifact_id
                child_artifact.save(update_fields=["parent"])

                tl = self._trace_link_service.create_trace_link(
                    source_id=UUID(str(parent_req.artifact_id)),
                    target_id=UUID(str(child_req.artifact_id)),
                    link_type=decomposition_link_type,
                    ctx=ctx,
                )
                if hasattr(tl, "id"):
                    result.trace_link_ids.append(tl.id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST application/tests/test_decompose_parent_coupling.py application/tests/test_requirement_service.py -v`
Expected: PASS (3 passed in the new module; `test_requirement_service.py` green)

- [ ] **Step 5: Commit**

```bash
git add backend/application/requirement_service.py backend/application/tests/test_decompose_parent_coupling.py
git commit -m "fix(traceability): write Artifact.parent and the decomposes link atomically"
```

---

## Phase D — Hard data migration and consumer fixes

### Task 16: Migrate every existing `TraceLink` row to the new type set

**Files:**
- Create: `backend/link_types/migration_ops.py`
- Create: `backend/link_types/management/commands/check_copy_of_conflicts.py`
- Create: `backend/persistence/migrations/0070_migrate_trace_link_types.py`
- Test: `backend/link_types/tests/test_migration_ops.py`

**Interfaces:**
- Consumes: `link_types.builtin.{LEGACY_LINK_TYPE_MAPPING, SWAPPED_LEGACY_KEYS}` (Task 3), `Artifact.copied_from` (Task 12)
- Produces:
  - `find_copy_of_conflicts(TraceLink) -> dict[UUID, list[UUID]]` — source artifact id → its >1 `copy-of` targets
  - `migrate_copy_of_links(Artifact, TraceLink) -> tuple[int, int]` — `(moved_to_field, downgraded_to_references)`
  - `migrate_parent_child_links(TraceLink) -> tuple[int, int]` — `(converted, deduplicated)`
  - `migrate_renamed_links(TraceLink) -> dict[str, int]` — per legacy key, rows rewritten
  - management command `check_copy_of_conflicts`

Order matters and is enforced by the migration: `copy-of` first (it deletes rows), then `parent-child` (it can collide with existing `decomposes` edges), then the plain renames (which can collide with the `uq_tracelink_edge` unique constraint after the endpoint swap).

**Conflict policy for `copy-of` (spec section 7):** an artifact with more than one `copy-of` link is a data conflict, because `copied_from` is 1:1. Newest link wins (highest `created_at`, `id` as tiebreak); every other one is **preserved** as a `references` link rather than dropped, so no provenance is lost.

- [ ] **Step 1: Write the failing test**

```python
# backend/link_types/tests/test_migration_ops.py
"""The hard TraceLink migration: rename, swap, dedup, copy-of relocation."""
from __future__ import annotations

import uuid

import pytest

from link_types.migration_ops import (
    find_copy_of_conflicts,
    migrate_copy_of_links,
    migrate_parent_child_links,
    migrate_renamed_links,
)
from persistence.tenancy import TenantContext


@pytest.fixture
def env(db):
    from persistence.models import Artifact, Tenant, TraceLink, Workspace

    tenant = Tenant.objects.create(name="migration-ops")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="ws")

    def artifact(kind: str = "Requirement", title: str = "a") -> Artifact:
        return Artifact.objects.create(
            tenant=tenant, workspace=ws, artifact_type=kind, title=title
        )

    def link(source, target, link_type) -> TraceLink:
        return TraceLink.objects.create(
            tenant=tenant, source=source, target=target, link_type=link_type
        )

    yield {
        "tenant": tenant,
        "artifact": artifact,
        "link": link,
        "Artifact": Artifact,
        "TraceLink": TraceLink,
    }
    TenantContext.clear_tenant()


# ---------- renames + endpoint swap ----------


@pytest.mark.django_db
def test_satisfies_is_renamed_and_its_endpoints_swapped(env):
    arch, req = env["artifact"]("ArchitectureElement"), env["artifact"]("Requirement")
    env["link"](arch, req, "satisfies")

    counts = migrate_renamed_links(env["TraceLink"])

    row = env["TraceLink"].objects.get(link_type="allocated-to")
    assert counts["satisfies"] == 1
    assert row.source_id == req.id
    assert row.target_id == arch.id


@pytest.mark.django_db
def test_implements_is_renamed_and_swapped_too(env):
    arch, req = env["artifact"]("ArchitectureElement"), env["artifact"]("Requirement")
    env["link"](arch, req, "implements")

    migrate_renamed_links(env["TraceLink"])

    row = env["TraceLink"].objects.get(link_type="allocated-to")
    assert row.source_id == req.id


@pytest.mark.django_db
def test_refines_becomes_derives_from_without_swapping(env):
    a, b = env["artifact"](title="a"), env["artifact"](title="b")
    env["link"](a, b, "refines")

    migrate_renamed_links(env["TraceLink"])

    row = env["TraceLink"].objects.get(link_type="derives-from")
    assert row.source_id == a.id
    assert row.target_id == b.id


@pytest.mark.django_db
def test_realizes_becomes_decomposes(env):
    a, b = env["artifact"](title="a"), env["artifact"](title="b")
    env["link"](a, b, "realizes")
    migrate_renamed_links(env["TraceLink"])
    assert env["TraceLink"].objects.filter(link_type="decomposes").count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("legacy", ["documents", "traces", "uses-term"])
def test_documentation_types_collapse_into_references(env, legacy):
    a, b = env["artifact"](title="a"), env["artifact"](title="b")
    env["link"](a, b, legacy)
    migrate_renamed_links(env["TraceLink"])
    assert env["TraceLink"].objects.filter(link_type="references").count() == 1


@pytest.mark.django_db
def test_a_rename_that_would_duplicate_an_existing_edge_deletes_the_loser(env):
    """documents + traces between the same pair both become references."""
    a, b = env["artifact"](title="a"), env["artifact"](title="b")
    env["link"](a, b, "documents")
    env["link"](a, b, "traces")

    migrate_renamed_links(env["TraceLink"])

    assert env["TraceLink"].objects.filter(link_type="references").count() == 1


@pytest.mark.django_db
def test_the_eight_surviving_types_are_untouched(env):
    a, b = env["artifact"](title="a"), env["artifact"](title="b")
    env["link"](a, b, "verifies")
    counts = migrate_renamed_links(env["TraceLink"])
    assert "verifies" not in counts
    assert env["TraceLink"].objects.get(link_type="verifies").source_id == a.id


# ---------- parent-child ----------


@pytest.mark.django_db
def test_parent_child_becomes_decomposes(env):
    parent, child = env["artifact"](title="p"), env["artifact"](title="c")
    env["link"](parent, child, "parent-child")

    converted, deduplicated = migrate_parent_child_links(env["TraceLink"])

    assert (converted, deduplicated) == (1, 0)
    assert env["TraceLink"].objects.filter(link_type="decomposes").count() == 1


@pytest.mark.django_db
def test_a_parent_child_duplicating_an_existing_decomposes_is_dropped(env):
    parent, child = env["artifact"](title="p"), env["artifact"](title="c")
    env["link"](parent, child, "decomposes")
    env["link"](parent, child, "parent-child")

    converted, deduplicated = migrate_parent_child_links(env["TraceLink"])

    assert (converted, deduplicated) == (0, 1)
    assert env["TraceLink"].objects.filter(link_type="decomposes").count() == 1
    assert not env["TraceLink"].objects.filter(link_type="parent-child").exists()


# ---------- copy-of ----------


@pytest.mark.django_db
def test_copy_of_moves_into_the_artifact_field_and_the_link_is_deleted(env):
    copy, original = env["artifact"](title="copy"), env["artifact"](title="original")
    env["link"](copy, original, "copy-of")

    moved, downgraded = migrate_copy_of_links(env["Artifact"], env["TraceLink"])

    copy.refresh_from_db()
    assert (moved, downgraded) == (1, 0)
    assert copy.copied_from_id == original.id
    assert not env["TraceLink"].objects.filter(link_type="copy-of").exists()


@pytest.mark.django_db
def test_multiple_copy_of_links_are_reported_as_a_conflict(env):
    copy = env["artifact"](title="copy")
    a, b = env["artifact"](title="a"), env["artifact"](title="b")
    env["link"](copy, a, "copy-of")
    env["link"](copy, b, "copy-of")

    conflicts = find_copy_of_conflicts(env["TraceLink"])

    assert copy.id in conflicts
    assert len(conflicts[copy.id]) == 2


@pytest.mark.django_db
def test_no_conflict_is_reported_for_a_single_copy_of(env):
    copy, original = env["artifact"](title="copy"), env["artifact"](title="original")
    env["link"](copy, original, "copy-of")
    assert find_copy_of_conflicts(env["TraceLink"]) == {}


@pytest.mark.django_db
def test_the_newest_copy_of_wins_and_the_rest_become_references(env):
    copy = env["artifact"](title="copy")
    older, newer = env["artifact"](title="older"), env["artifact"](title="newer")
    env["link"](copy, older, "copy-of")
    env["link"](copy, newer, "copy-of")

    moved, downgraded = migrate_copy_of_links(env["Artifact"], env["TraceLink"])

    copy.refresh_from_db()
    assert (moved, downgraded) == (1, 1)
    assert copy.copied_from_id == newer.id
    assert env["TraceLink"].objects.filter(
        link_type="references", target_id=older.id
    ).exists()


@pytest.mark.django_db
def test_migration_ops_are_idempotent(env):
    arch, req = env["artifact"]("ArchitectureElement"), env["artifact"]("Requirement")
    env["link"](arch, req, "satisfies")
    parent, child = env["artifact"](title="p"), env["artifact"](title="c")
    env["link"](parent, child, "parent-child")

    migrate_copy_of_links(env["Artifact"], env["TraceLink"])
    migrate_parent_child_links(env["TraceLink"])
    migrate_renamed_links(env["TraceLink"])
    total = env["TraceLink"].objects.count()

    migrate_copy_of_links(env["Artifact"], env["TraceLink"])
    migrate_parent_child_links(env["TraceLink"])
    migrate_renamed_links(env["TraceLink"])

    assert env["TraceLink"].objects.count() == total


@pytest.mark.django_db
def test_no_retired_link_type_survives_the_full_run(env):
    from link_types.builtin import LEGACY_LINK_TYPE_MAPPING

    a, b = env["artifact"](title="a"), env["artifact"](title="b")
    for legacy in LEGACY_LINK_TYPE_MAPPING:
        env["link"](a, env["artifact"](title=f"t-{legacy}"), legacy)

    migrate_copy_of_links(env["Artifact"], env["TraceLink"])
    migrate_parent_child_links(env["TraceLink"])
    migrate_renamed_links(env["TraceLink"])

    survivors = set(
        env["TraceLink"].objects.values_list("link_type", flat=True)
    )
    assert survivors & set(LEGACY_LINK_TYPE_MAPPING) == set()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST link_types/tests/test_migration_ops.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'link_types.migration_ops'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/link_types/migration_ops.py
"""The hard TraceLink migration, as testable functions.

Kept out of the numbered migration module so the behaviour can be tested
against real rows without replaying migration state; the migration is a thin
wrapper that calls these in order.

Order is not optional:

1. ``migrate_copy_of_links``   — deletes rows, so it runs before anything that
                                 could collide with them.
2. ``migrate_parent_child_links`` — a parent-child edge may already have a
                                 twin ``decomposes`` edge for the same pair.
3. ``migrate_renamed_links``   — after the endpoint swap two formerly distinct
                                 edges can become the same
                                 ``(source, target, link_type)`` triple, which
                                 ``uq_tracelink_edge`` (issue #126) forbids.

Every step takes its models as arguments so a migration can pass the
historical ``apps.get_model`` versions instead of the live ones.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple
from uuid import UUID

from .builtin import LEGACY_LINK_TYPE_MAPPING, SWAPPED_LEGACY_KEYS

logger = logging.getLogger(__name__)

#: Legacy keys that are renamed rather than restructured.
_RENAMED = {
    legacy: successor
    for legacy, successor in LEGACY_LINK_TYPE_MAPPING.items()
    if successor is not None
}


def find_copy_of_conflicts(TraceLink: Any) -> Dict[UUID, List[UUID]]:
    """Return ``{source_artifact_id: [link_id, ...]}`` for sources with >1 copy-of.

    ``Artifact.copied_from`` is a 1:1 field, so a source with two ``copy-of``
    links is a data conflict that has to be resolved before the migration can
    faithfully represent it (spec section 7). Run
    ``manage.py check_copy_of_conflicts`` to see them ahead of time.
    """
    by_source: Dict[UUID, List[UUID]] = {}
    for link in TraceLink.objects.filter(link_type="copy-of").order_by(
        "created_at", "id"
    ):
        by_source.setdefault(link.source_id, []).append(link.id)
    return {source: ids for source, ids in by_source.items() if len(ids) > 1}


def migrate_copy_of_links(Artifact: Any, TraceLink: Any) -> Tuple[int, int]:
    """Move ``copy-of`` links into ``Artifact.copied_from``.

    The newest link per source wins (``created_at``, then ``id`` as a stable
    tiebreak). Every other link of the same source is **kept** as a
    ``references`` link instead of being deleted, so a multi-copy conflict
    loses its 1:1 precision but never its provenance.

    Returns:
        ``(moved_to_field, downgraded_to_references)``.
    """
    moved = 0
    downgraded = 0

    by_source: Dict[UUID, List[Any]] = {}
    for link in TraceLink.objects.filter(link_type="copy-of").order_by(
        "created_at", "id"
    ):
        by_source.setdefault(link.source_id, []).append(link)

    for source_id, links in by_source.items():
        winner = links[-1]  # newest
        Artifact.objects.filter(id=source_id).update(copied_from_id=winner.target_id)
        winner.delete()
        moved += 1

        for loser in links[:-1]:
            # Do not create a duplicate if a references edge already exists.
            if TraceLink.objects.filter(
                source_id=loser.source_id,
                target_id=loser.target_id,
                link_type="references",
            ).exists():
                loser.delete()
            else:
                loser.link_type = "references"
                loser.save(update_fields=["link_type"])
            downgraded += 1

    if moved or downgraded:
        logger.info(
            "copy-of migration: %d moved to Artifact.copied_from, "
            "%d downgraded to references.",
            moved,
            downgraded,
        )
    return moved, downgraded


def migrate_parent_child_links(TraceLink: Any) -> Tuple[int, int]:
    """Convert ``parent-child`` into ``decomposes``, deduplicating twins.

    Both types run parent -> child, so a pair that already carries a
    ``decomposes`` edge would violate ``uq_tracelink_edge`` on conversion. Such
    a parent-child row is redundant and is dropped rather than duplicated
    (spec section 6, step 2).

    Returns:
        ``(converted, deduplicated)``.
    """
    converted = 0
    deduplicated = 0

    for link in TraceLink.objects.filter(link_type="parent-child"):
        twin_exists = (
            TraceLink.objects.filter(
                source_id=link.source_id,
                target_id=link.target_id,
                link_type="decomposes",
            )
            .exclude(id=link.id)
            .exists()
        )
        if twin_exists:
            link.delete()
            deduplicated += 1
        else:
            link.link_type = "decomposes"
            link.save(update_fields=["link_type"])
            converted += 1

    if converted or deduplicated:
        logger.info(
            "parent-child migration: %d converted to decomposes, %d deduplicated.",
            converted,
            deduplicated,
        )
    return converted, deduplicated


def migrate_renamed_links(TraceLink: Any) -> Dict[str, int]:
    """Rename the remaining legacy types, swapping endpoints where required.

    ``satisfies`` and ``implements`` both ran ArchitectureElement ->
    Requirement; ``allocated-to`` runs Requirement -> ArchitectureElement, so
    those rows have their endpoints exchanged as part of the rename
    (spec section 3.1). This silently reverses the meaning of the stored row
    for any consumer that reads ``source``/``target`` directly — see Task 17.

    A rename that would collide with an existing edge (``documents`` and
    ``traces`` between the same pair both becoming ``references``) drops the
    later row instead of violating ``uq_tracelink_edge``.

    Returns:
        ``{legacy_key: rows_rewritten}``, omitting keys with no rows.
    """
    counts: Dict[str, int] = {}

    for legacy, successor in _RENAMED.items():
        if legacy == "parent-child":
            continue  # handled by migrate_parent_child_links
        rewritten = 0
        for link in TraceLink.objects.filter(link_type=legacy).order_by("created_at", "id"):
            source_id, target_id = link.source_id, link.target_id
            if legacy in SWAPPED_LEGACY_KEYS:
                source_id, target_id = target_id, source_id

            collides = (
                TraceLink.objects.filter(
                    source_id=source_id, target_id=target_id, link_type=successor
                )
                .exclude(id=link.id)
                .exists()
            )
            if collides:
                link.delete()
            else:
                link.source_id = source_id
                link.target_id = target_id
                link.link_type = successor
                link.save(update_fields=["source", "target", "link_type"])
            rewritten += 1

        if rewritten:
            counts[legacy] = rewritten
            logger.info(
                "link-type migration: %d '%s' row(s) -> '%s'%s.",
                rewritten,
                legacy,
                successor,
                " (endpoints swapped)" if legacy in SWAPPED_LEGACY_KEYS else "",
            )

    return counts


__all__ = [
    "find_copy_of_conflicts",
    "migrate_copy_of_links",
    "migrate_parent_child_links",
    "migrate_renamed_links",
]
```

```python
# backend/link_types/management/commands/check_copy_of_conflicts.py
"""Preflight for the copy-of -> Artifact.copied_from migration.

``copied_from`` is 1:1; a ``copy-of`` link was N:M. An artifact with more than
one ``copy-of`` link therefore cannot be represented faithfully and has to be
looked at before the migration runs (spec section 7). The migration itself
resolves conflicts by "newest wins, the rest survive as references" — this
command exists so the decision is seen rather than discovered afterwards.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from link_types.migration_ops import find_copy_of_conflicts


class Command(BaseCommand):
    help = "List artifacts carrying more than one 'copy-of' TraceLink."

    def handle(self, *args, **options):
        from persistence.models import Artifact, TraceLink

        conflicts = find_copy_of_conflicts(TraceLink)
        if not conflicts:
            self.stdout.write(
                self.style.SUCCESS("No copy-of conflicts: every source has at most one.")
            )
            return

        self.stdout.write(
            self.style.WARNING(f"{len(conflicts)} artifact(s) have multiple copy-of links:")
        )
        for source_id, link_ids in conflicts.items():
            artifact = Artifact.objects.filter(id=source_id).only("title").first()
            title = artifact.title if artifact else "(missing)"
            self.stdout.write(f"  {source_id} '{title}': {len(link_ids)} links")
        self.stdout.write(
            "\nMigration policy: newest link wins and becomes copied_from; "
            "the others are preserved as 'references' links."
        )
```

```python
# backend/persistence/migrations/0070_migrate_trace_link_types.py
"""Hard migration of every TraceLink row to the new eight-type catalog.

Spec section 6, step 2. Runs after the schema migration that added
``Artifact.copied_from`` and before nothing in particular — but it MUST run
after ``link_types.0003``, because ``check_link_pair`` starts rejecting the
legacy types the moment the catalog exists and the service is wired up.

Irreversible on purpose: the endpoint swap on ``satisfies``/``implements``
loses the information about which of the two a row used to be, so a faithful
reverse does not exist. Take a backup before deploying.
"""
from __future__ import annotations

import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def migrate_link_types(apps, schema_editor):
    from link_types.migration_ops import (
        migrate_copy_of_links,
        migrate_parent_child_links,
        migrate_renamed_links,
    )

    Artifact = apps.get_model("persistence", "Artifact")
    TraceLink = apps.get_model("persistence", "TraceLink")

    moved, downgraded = migrate_copy_of_links(Artifact, TraceLink)
    converted, deduplicated = migrate_parent_child_links(TraceLink)
    renamed = migrate_renamed_links(TraceLink)

    logger.info(
        "TraceLink type migration complete: copy-of moved=%d downgraded=%d, "
        "parent-child converted=%d deduplicated=%d, renamed=%s",
        moved,
        downgraded,
        converted,
        deduplicated,
        renamed,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0069_align_embedding_dimensions"),
        ("link_types", "0004_grandfather_observed_pairs"),
    ]

    operations = [
        migrations.RunPython(migrate_link_types, migrations.RunPython.noop),
    ]
```

Note: the schema migration from Task 12 is generated as `0070_tracelink_semantics_fields` if Task 12 runs first. Renumber this one to `0071_...` and update its `dependencies` accordingly — the migration graph, not the file name, is authoritative.

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST link_types/tests/test_migration_ops.py -v`
Expected: PASS (18 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/link_types/migration_ops.py backend/link_types/management/commands/check_copy_of_conflicts.py backend/persistence/migrations/ backend/link_types/tests/test_migration_ops.py
git commit -m "feat(link-types): migrate existing trace links to the eight-type catalog"
```

---

### Task 17: Move every hardcoded link-type consumer with the migration

**Files:**
- Modify: `backend/traceability/vcrm_report_generator.py:199-207`
- Modify: `backend/traceability/audit/hierarchy.py:80-83`
- Modify: `backend/traceability/audit/rules/trace_derivation_allocation.py:379-398`
- Modify: `backend/mcp_server/tools/cross_cutting.py:1327-1337`
- Modify: `backend/rest_api/serializers.py:1310-1312`, `backend/rest_api/views.py:4162`
- Modify: `backend/application/interview_multi_protocol.py:43-46`
- Modify: `backend/application/reqif_export_service.py:69-72`
- Modify: `backend/application/management/commands/migrate_se_docs.py:205`
- Modify: `backend/auth_tenancy/management/commands/seed_toothbrush.py:227`
- Test: `backend/traceability/tests/test_link_type_consumers.py`

**Interfaces:**
- Consumes: the migrated data shape from Task 16
- Produces: no retired link-type literal anywhere outside `link_types.builtin.LEGACY_LINK_TYPE_MAPPING`

**Latent bug this surfaces:** `vcrm_report_generator.py` queries `tl.source_id = <requirement artifact> AND tl.link_type IN ('satisfies','implements')`, but both of those types ran ArchitectureElement → Requirement. The Requirement was never the source, so the VCRM "Component" column has been silently empty for SE-conform data. After the swap, `allocated-to` genuinely runs Requirement → ArchitectureElement and the existing query direction becomes correct — the fix is a one-literal change that also repairs the column.

**TRACE-P3 simplification:** `satisfies_or_implements = _sources_by_link_type(context, {SATISFIES, IMPLEMENTS})` and `allocated_from = _targets_by_link_type(context, {ALLOCATED_TO})` become the same lookup once satisfies/implements are allocated-to, so the first one is deleted rather than rewritten.

- [ ] **Step 1: Write the failing test**

```python
# backend/traceability/tests/test_link_type_consumers.py
"""No retired link type survives in code that reads or writes link_type."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]

RETIRED = ["parent-child", "satisfies", "implements", "refines", "realizes", "documents", "traces", "uses-term", "copy-of"]

#: Files that legitimately still name the retired types.
ALLOWED = {
    "link_types/builtin.py",              # the mapping table itself
    "link_types/migration_ops.py",        # the migration
    "link_types/tests/test_builtin.py",
    "link_types/tests/test_migration_ops.py",
    "traceability/tests/test_link_type_consumers.py",
}


def _source_files():
    for path in BACKEND.rglob("*.py"):
        relative = path.relative_to(BACKEND).as_posix()
        if "/migrations/" in relative or relative.startswith("."):
            continue
        if relative in ALLOWED:
            continue
        yield relative, path


@pytest.mark.parametrize("retired", RETIRED)
def test_no_retired_link_type_literal_remains(retired):
    pattern = re.compile(rf"""['"]{re.escape(retired)}['"]""")
    offenders = [
        relative
        for relative, path in _source_files()
        if pattern.search(path.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert offenders == [], f"'{retired}' still hardcoded in: {offenders}"


def test_link_type_enum_has_exactly_the_eight_core_members():
    from traceability.types import LinkType

    assert {member.value for member in LinkType} == {
        "derives-from",
        "decomposes",
        "allocated-to",
        "verifies",
        "decides",
        "mitigates",
        "references",
        "diagram-ref",
    }


def test_vcrm_component_query_uses_allocated_to():
    source = (BACKEND / "traceability" / "vcrm_report_generator.py").read_text(
        encoding="utf-8"
    )
    assert "allocated-to" in source
    assert "satisfies" not in source


@pytest.mark.django_db
def test_vcrm_finds_the_component_of_an_allocated_requirement():
    """Regression: the old query looked at the wrong end of the edge."""
    import uuid

    from persistence.models import (
        ArchitectureElement,
        Artifact,
        Requirement,
        Tenant,
        TraceLink,
        Workspace,
    )
    from persistence.tenancy import TenantContext
    from traceability.vcrm_report_generator import VCRMReportGenerator

    tenant = Tenant.objects.create(name="vcrm")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="ws")

    req_art = Artifact.objects.create(
        tenant=tenant, workspace=ws, artifact_type="Requirement", title="R"
    )
    req = Requirement.objects.create(
        tenant=tenant, workspace=ws, artifact=req_art, title="R"
    )
    arch_art = Artifact.objects.create(
        tenant=tenant, workspace=ws, artifact_type="ArchitectureElement", title="C"
    )
    ArchitectureElement.objects.create(
        tenant=tenant, workspace=ws, artifact=arch_art, name="C"
    )
    TraceLink.objects.create(
        tenant=tenant, source=req_art, target=arch_art, link_type="allocated-to"
    )

    components = VCRMReportGenerator()._components_for_requirement(req.id, tenant.id)
    assert str(arch_art.id) in components
    TenantContext.clear_tenant()


def test_hierarchy_decomposition_link_types_is_only_decomposes():
    from traceability.audit.hierarchy import _DECOMPOSITION_LINK_TYPES

    assert _DECOMPOSITION_LINK_TYPES == {"decomposes"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST traceability/tests/test_link_type_consumers.py -v`
Expected: FAIL — `test_no_retired_link_type_literal_remains[satisfies]` lists `traceability/vcrm_report_generator.py`, `traceability/audit/rules/trace_derivation_allocation.py`, `auth_tenancy/management/commands/seed_toothbrush.py`; the `parent-child` case lists `persistence/models.py`, `rest_api/serializers.py`, `rest_api/views.py`, `mcp_server/tools/cross_cutting.py`, `traceability/audit/hierarchy.py`

- [ ] **Step 3: Write minimal implementation**

`backend/traceability/vcrm_report_generator.py` — replace the component query:

```python
        # Components a requirement is allocated to. Before the link-type
        # consolidation this read IN ('satisfies', 'implements'), both of which
        # ran ArchitectureElement -> Requirement — so a Requirement was never
        # the source and this column came back empty for SE-conform data.
        # 'allocated-to' genuinely runs Requirement -> ArchitectureElement.
        sql = """
            SELECT DISTINCT tl.target_id
            FROM pl_tracelink tl
            JOIN pl_artifact a ON a.id = tl.target_id
            WHERE tl.source_id = %s
              AND tl.link_type = 'allocated-to'
              AND tl.tenant_id = %s
        """
```

`backend/traceability/audit/hierarchy.py:80-83`:

```python
#: Hierarchy edges read as "target is the child". 'parent-child' is gone —
#: the migration folded it into 'decomposes', which carries the same
#: direction (source = parent).
_DECOMPOSITION_LINK_TYPES = {LinkType.DECOMPOSES.value}
```

Update the direction table in that module's docstring: delete the `parent-child` row, keep `decomposes` and `derives-from`, and replace the paragraph about `refines` with:

```
``refines`` no longer exists as a link type: the migration folded it into
``derives-from``. Because ``derives-from`` *is* a hierarchy edge, every
formerly symmetric ``refines`` edge between two Requirements now carries
level semantics it did not have before — see OFFENE FRAGE 2 in
docs/superpowers/plans/2026-09-03-traceability-semantik.md.
```

`backend/traceability/audit/rules/trace_derivation_allocation.py:379-398` — delete `satisfies_or_implements` and its use:

```python
    def check(self, context: AuditContext) -> List[Finding]:
        elements = _active_architecture_elements(context)
        if not elements:
            return []

        requirement_ids = frozenset(_active_requirements(context))
        # 'satisfies'/'implements' were folded into 'allocated-to', which this
        # rule already read from the target side — the two lookups collapsed
        # into one.
        allocated_from = _targets_by_link_type(
            context, frozenset({LinkType.ALLOCATED_TO.value})
        )

        findings: List[Finding] = []
        for ae_id, title in sorted(elements.items()):
            justifying = allocated_from.get(ae_id, set())
            if justifying & requirement_ids:
```

Also update the docstring at lines 372-374 (`an element with neither an outgoing satisfies/implements nor an incoming allocation`) to `an element with no incoming allocation`.

`backend/mcp_server/tools/cross_cutting.py:1334`:

```python
                    "link_type": "decomposes",
```

`backend/rest_api/serializers.py:1311`: `default="parent-child"` → `default="decomposes"`.
`backend/rest_api/views.py:4162`: `getattr(ws, "decomposition_link_type", "parent-child")` → `"decomposes"`.

`backend/application/interview_multi_protocol.py:43-46` — the prompt must not enumerate a stale list:

```python
Use trace-link types from the workspace's link-type catalog, which is supplied
in the prompt context as `available_link_types`. Never propose a type that is
not in that list.
```

Populate `available_link_types` from `link_types.catalog.resolve_catalog(workspace_id)` where the prompt context is built.

`backend/application/reqif_export_service.py:69-72` — update the docstring list to the eight core types.

`backend/application/management/commands/migrate_se_docs.py:205`:

```python
# 'implements' was folded into 'allocated-to', which runs the other way
# (Requirement -> ArchitectureElement), so callers must swap their endpoints.
_LINK_ALLOCATED_TO = LinkType.ALLOCATED_TO.value
```

and swap source/target at its call sites.

`backend/auth_tenancy/management/commands/seed_toothbrush.py:227`:

```python
            link_svc.create_trace_link(
                source_id=parent_need.artifact_id,
                target_id=r.artifact_id,
                link_type="derives-from",
                ctx=ctx,
            )
```

(The seed linked a Requirement to its parent Need; `satisfies` Req→Need became `allocated-to`, which no longer allows that pair. `derives-from` child→parent is the correct successor for a Requirement derived from a Need.)

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST traceability/tests/test_link_type_consumers.py traceability/ mcp_server/tests/test_cross_cutting_tool_group.py -v`
Expected: PASS (13 passed in the new module; the `traceability` suite green)

- [ ] **Step 5: Commit**

```bash
git add backend/traceability backend/mcp_server/tools/cross_cutting.py backend/rest_api backend/application backend/auth_tenancy/management/commands/seed_toothbrush.py
git commit -m "refactor(traceability): move every hardcoded link-type consumer to the new catalog

Also repairs the VCRM component column, which queried satisfies/implements
from the Requirement side even though both types ran ArchitectureElement to
Requirement, so the column was silently empty for SE-conform data."
```

---

### Task 18: Verify the SE-Auditor finding set before and after (OFFENE FRAGE 2)

**Files:**
- Create: `backend/link_types/management/commands/diff_auditor_findings.py`
- Test: `backend/traceability/tests/test_refines_merge_impact.py`

**Interfaces:**
- Consumes: the SE-Auditor entry point used by `application.audit_service`
- Produces: management command `diff_auditor_findings --before PATH` / `--after PATH`; `summarize_findings(workspace_id) -> dict[str, int]` (rule id → count)

This is the observation step for OFFENE FRAGE 2. Run `diff_auditor_findings --before` on a seeded workspace **before** Task 16's migration, then `--after` once it has run, and compare. A changed TRACE-P1/VERIF-P8 count is the expected, decision-relevant signal — not a bug to silently fix.

- [ ] **Step 1: Write the failing test**

```python
# backend/traceability/tests/test_refines_merge_impact.py
"""A former `refines` edge now carries hierarchy semantics (OFFENE FRAGE 2)."""
from __future__ import annotations

import pytest

from link_types.management.commands.diff_auditor_findings import summarize_findings
from persistence.tenancy import TenantContext


@pytest.fixture
def env(db):
    from link_types.workspace_store import provision_workspace_link_types
    from persistence.models import Artifact, Requirement, Tenant, Workspace

    tenant = Tenant.objects.create(name="refines-impact")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="ws")
    provision_workspace_link_types(workspace_id=ws.id, tenant_id=tenant.id)

    def requirement(title):
        art = Artifact.objects.create(
            tenant=tenant, workspace=ws, artifact_type="Requirement", title=title
        )
        return Requirement.objects.create(
            tenant=tenant, workspace=ws, artifact=art, title=title
        )

    yield {"tenant": tenant, "workspace": ws, "requirement": requirement}
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_summarize_returns_counts_keyed_by_rule_id(env):
    env["requirement"]("lonely")
    summary = summarize_findings(env["workspace"].id)
    assert isinstance(summary, dict)
    assert all(isinstance(count, int) for count in summary.values())


@pytest.mark.django_db
def test_a_migrated_refines_edge_makes_the_target_a_non_root(env):
    """Before the merge both requirements were roots; now one is a child."""
    from persistence.models import TraceLink
    from traceability.audit.hierarchy import classify_requirements

    a, b = env["requirement"]("a"), env["requirement"]("b")
    TraceLink.objects.create(
        tenant=env["tenant"],
        source_id=a.artifact_id,
        target_id=b.artifact_id,
        link_type="derives-from",
    )

    classification = classify_requirements(env["workspace"].id)
    assert str(a.artifact_id) not in classification["roots"]
    assert str(b.artifact_id) in classification["roots"]


@pytest.mark.django_db
def test_the_command_reports_a_delta_between_two_snapshots(env, tmp_path):
    import json
    from io import StringIO

    from django.core.management import call_command

    before = tmp_path / "before.json"
    before.write_text(json.dumps({"TRACE-P1": 5, "VERIF-P8": 2}), encoding="utf-8")
    after = tmp_path / "after.json"
    after.write_text(json.dumps({"TRACE-P1": 3, "VERIF-P8": 2}), encoding="utf-8")

    out = StringIO()
    call_command(
        "diff_auditor_findings", "--before", str(before), "--after", str(after), stdout=out
    )
    output = out.getvalue()
    assert "TRACE-P1" in output
    assert "-2" in output
    assert "VERIF-P8" not in output.split("Unchanged")[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST traceability/tests/test_refines_merge_impact.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'link_types.management.commands.diff_auditor_findings'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/link_types/management/commands/diff_auditor_findings.py
"""Snapshot and diff the SE-Auditor finding counts around the link migration.

Written for OFFENE FRAGE 2: folding ``refines`` into ``derives-from`` turns
formerly symmetric same-level edges into directed hierarchy edges, which the
root/leaf classifier reads. TRACE-P1 ("a decomposition root must derive from a
StakeholderNeed") and VERIF-P8 ("a leaf must have a verifying TestCase") will
therefore fire on a different set of requirements than before.

Usage::

    # before running the TraceLink data migration
    python manage.py diff_auditor_findings --snapshot /tmp/before.json --workspace <id>
    # after
    python manage.py diff_auditor_findings --snapshot /tmp/after.json --workspace <id>
    python manage.py diff_auditor_findings --before /tmp/before.json --after /tmp/after.json

A non-empty delta is the expected signal, not a defect: it is the evidence the
decision in OFFENE FRAGE 2 needs.
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Dict
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError


def summarize_findings(workspace_id: UUID | str) -> Dict[str, int]:
    """Return ``{rule_id: finding_count}`` for a workspace's SE-Auditor run."""
    from application.audit_service import AuditService

    findings = AuditService().run_audit(workspace_id=workspace_id)
    counter: Counter = Counter()
    for finding in findings:
        rule_id = getattr(finding, "rule_id", None) or finding.get("rule_id")
        counter[str(rule_id)] += 1
    return dict(counter)


class Command(BaseCommand):
    help = "Snapshot or diff SE-Auditor finding counts around the link-type migration."

    def add_arguments(self, parser):
        parser.add_argument("--workspace", dest="workspace_id", default=None)
        parser.add_argument("--snapshot", dest="snapshot_path", default=None)
        parser.add_argument("--before", dest="before_path", default=None)
        parser.add_argument("--after", dest="after_path", default=None)

    def handle(self, *args, **options):
        if options["snapshot_path"]:
            if not options["workspace_id"]:
                raise CommandError("--snapshot requires --workspace")
            summary = summarize_findings(options["workspace_id"])
            with open(options["snapshot_path"], "w", encoding="utf-8") as handle:
                json.dump(summary, handle, indent=2, sort_keys=True)
            self.stdout.write(
                f"{sum(summary.values())} finding(s) written to "
                f"{options['snapshot_path']}"
            )
            return

        if not (options["before_path"] and options["after_path"]):
            raise CommandError("Provide either --snapshot, or both --before and --after.")

        with open(options["before_path"], encoding="utf-8") as handle:
            before = json.load(handle)
        with open(options["after_path"], encoding="utf-8") as handle:
            after = json.load(handle)

        changed = {
            rule_id: after.get(rule_id, 0) - before.get(rule_id, 0)
            for rule_id in sorted(set(before) | set(after))
            if after.get(rule_id, 0) != before.get(rule_id, 0)
        }

        if not changed:
            self.stdout.write(
                self.style.SUCCESS("No SE-Auditor findings changed across the migration.")
            )
        else:
            self.stdout.write(
                self.style.WARNING("SE-Auditor findings changed across the migration:")
            )
            for rule_id, delta in changed.items():
                self.stdout.write(
                    f"  {rule_id}: {before.get(rule_id, 0)} -> "
                    f"{after.get(rule_id, 0)}  ({delta:+d})"
                )
            self.stdout.write(
                "\nExpected for TRACE-P1 / VERIF-P8: every former 'refines' edge "
                "between two Requirements now counts as a hierarchy edge. "
                "See OFFENE FRAGE 2 of the traceability-semantik plan."
            )

        unchanged = sorted(set(before) & set(after) - set(changed))
        self.stdout.write(f"\nUnchanged rules: {', '.join(unchanged) or '(none)'}")
```

If `traceability.audit.hierarchy` does not already expose a `classify_requirements(workspace_id)` helper returning `{"roots": set[str], "leaves": set[str]}`, extract one from the existing private classifier and export it — the test above and the audit rules then share a single entry point instead of two copies of the traversal.

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST traceability/tests/test_refines_merge_impact.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/link_types/management/commands/diff_auditor_findings.py backend/traceability/tests/test_refines_merge_impact.py backend/traceability/audit/hierarchy.py
git commit -m "test(traceability): observe the SE-Auditor delta caused by the refines merge"
```

---

## Phase E — REST and MCP surface

### Task 19: `LinkTypeFacade` — the Layer-2 seam (ADR-01)

**Files:**
- Create: `backend/application/link_type_facade.py`
- Test: `backend/application/tests/test_link_type_facade.py`

**Interfaces:**
- Consumes: `GlobalLinkTypeDefinitionStore` (Task 6), `WorkspaceLinkTypeDefinitionStore` + `provision_workspace_link_types` (Task 7), `link_types.catalog.resolve_catalog` (Task 5)
- Produces: `LinkTypeFacade` with
  - `list_global(ctx) -> list[dict]`
  - `create_global(ctx, key, definition) -> dict`
  - `update_global(ctx, key, definition) -> dict`
  - `delete_global(ctx, key) -> None`
  - `list_workspace(ctx, workspace_id) -> list[dict]`
  - `update_workspace(ctx, workspace_id, key, definition) -> dict`
  - `reset_workspace(ctx, workspace_id, key) -> dict`
  - all returning JSON-safe dicts (`str` ids, no UUID/datetime objects)

ADR-01: `rest_api` and `mcp_server` must reach the domain through `application/`, mirroring the existing `application/workflow_facade.py`. Every method audits its writes and requires a tenant-admin role for the global scope.

**JSON-safety is not cosmetic:** the MCP transport serializes tool payloads with stdlib `json.dumps`, which raises on a `UUID` or `datetime` and surfaces as an opaque 500. Returning `str` ids from the facade means both transports get a safe shape from one place.

- [ ] **Step 1: Write the failing test**

```python
# backend/application/tests/test_link_type_facade.py
"""Layer-2 seam for the link-type catalog (ADR-01)."""
from __future__ import annotations

import json
import uuid

import pytest

from application.link_type_facade import LinkTypeFacade
from link_types.builtin import builtin_definition
from persistence.errors import PermissionDeniedError, ValidationError
from persistence.tenancy import TenantContext


@pytest.fixture
def env(db):
    from auth_tenancy.models import AuthContext
    from link_types.workspace_store import provision_workspace_link_types
    from persistence.models import Tenant, Workspace

    tenant = Tenant.objects.create(name="facade")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="ws")
    provision_workspace_link_types(workspace_id=ws.id, tenant_id=tenant.id)

    admin = AuthContext(
        user_id=uuid.uuid4(), tenant_id=tenant.id, workspace_id=ws.id, roles=["admin"]
    )
    viewer = AuthContext(
        user_id=uuid.uuid4(), tenant_id=tenant.id, workspace_id=ws.id, roles=["viewer"]
    )
    yield {"tenant": tenant, "workspace": ws, "admin": admin, "viewer": viewer}
    TenantContext.clear_tenant()


@pytest.mark.django_db
def test_list_global_returns_the_eight_seeded_types(env):
    rows = LinkTypeFacade().list_global(env["admin"])
    assert {row["key"] for row in rows} == {
        "derives-from",
        "decomposes",
        "allocated-to",
        "verifies",
        "decides",
        "mitigates",
        "references",
        "diagram-ref",
    }


@pytest.mark.django_db
def test_every_returned_row_is_json_serializable(env):
    """The MCP transport uses stdlib json.dumps — a UUID here is a 500."""
    rows = LinkTypeFacade().list_global(env["admin"])
    json.dumps(rows)
    rows = LinkTypeFacade().list_workspace(env["admin"], env["workspace"].id)
    json.dumps(rows)


@pytest.mark.django_db
def test_workspace_rows_carry_the_customization_flag(env):
    rows = LinkTypeFacade().list_workspace(env["admin"], env["workspace"].id)
    assert all(row["is_customized"] is False for row in rows)
    assert all("definition" in row for row in rows)


@pytest.mark.django_db
def test_a_non_admin_cannot_write_the_global_scope(env):
    definition = builtin_definition("mitigates")
    with pytest.raises(PermissionDeniedError):
        LinkTypeFacade().update_global(env["viewer"], "mitigates", definition)


@pytest.mark.django_db
def test_a_non_admin_may_still_read(env):
    assert LinkTypeFacade().list_workspace(env["viewer"], env["workspace"].id)


@pytest.mark.django_db
def test_create_global_accepts_a_tenant_invented_key(env):
    definition = builtin_definition("mitigates")
    definition["built_in"] = False
    row = LinkTypeFacade().create_global(env["admin"], "conflicts-with", definition)
    assert row["key"] == "conflicts-with"
    assert row["definition"]["built_in"] is False


@pytest.mark.django_db
def test_update_global_reports_how_many_workspaces_it_propagated_to(env):
    changed = builtin_definition("mitigates")
    changed["impact_weight"] = 0.9
    row = LinkTypeFacade().update_global(env["admin"], "mitigates", changed)
    assert row["propagated_to"] == 1


@pytest.mark.django_db
def test_update_workspace_marks_the_row_customized(env):
    changed = builtin_definition("mitigates")
    changed["impact_weight"] = 0.7
    row = LinkTypeFacade().update_workspace(
        env["admin"], env["workspace"].id, "mitigates", changed
    )
    assert row["is_customized"] is True


@pytest.mark.django_db
def test_reset_workspace_clears_the_flag(env):
    changed = builtin_definition("mitigates")
    changed["impact_weight"] = 0.7
    LinkTypeFacade().update_workspace(
        env["admin"], env["workspace"].id, "mitigates", changed
    )
    row = LinkTypeFacade().reset_workspace(
        env["admin"], env["workspace"].id, "mitigates"
    )
    assert row["is_customized"] is False
    assert row["definition"]["impact_weight"] == 0.5


@pytest.mark.django_db
def test_an_invalid_definition_is_rejected_at_the_facade(env):
    bad = builtin_definition("mitigates")
    bad["suspect_rule"] = "invent-something"
    with pytest.raises(ValidationError, match="suspect_rule"):
        LinkTypeFacade().update_global(env["admin"], "mitigates", bad)


@pytest.mark.django_db
def test_writes_are_audited(env):
    from audit.models import AuditEntry

    changed = builtin_definition("mitigates")
    changed["impact_weight"] = 0.9
    LinkTypeFacade().update_global(env["admin"], "mitigates", changed)

    assert AuditEntry.objects.filter(entity_type="GlobalLinkTypeDefinition").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST application/tests/test_link_type_facade.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.link_type_facade'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/application/link_type_facade.py
"""Layer-2 facade over the LinkTypeCatalog (ADR-01, single entry point).

``rest_api`` and ``mcp_server`` reach the catalog only through here, exactly
as they reach the workflow definitions through ``application.workflow_facade``.
Two things the stores below deliberately do not do live at this layer:

* **Authorisation** — the global scope is tenant-admin only.
* **JSON safety** — the MCP transport serialises tool payloads with stdlib
  ``json.dumps``, which raises on a ``UUID`` or ``datetime`` and reaches the
  caller as an opaque INTERNAL_ERROR. Every dict returned from here is already
  primitive-only, so neither transport has to remember.
"""
from __future__ import annotations

from typing import Any, Dict, List
from uuid import UUID

from auth_tenancy.context import AuthContext
from link_types.global_store import GlobalLinkTypeDefinitionStore
from link_types.workspace_store import WorkspaceLinkTypeDefinitionStore
from persistence.errors import PermissionDeniedError

from .base import BaseService

_ADMIN_ROLES = frozenset({"admin", "tenant_admin"})


def _global_to_dict(row: Any, *, propagated_to: int | None = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "id": str(row.id),
        "key": row.key,
        "definition": row.definition_json or {},
        "version": row.version,
    }
    if propagated_to is not None:
        payload["propagated_to"] = propagated_to
    return payload


def _workspace_to_dict(row: Any) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "workspace_id": str(row.workspace_id),
        "key": row.key,
        "definition": row.definition_json or {},
        "is_customized": row.is_customized,
        "source_global_id": (
            str(row.source_global_id) if row.source_global_id else None
        ),
        "version": row.version,
    }


class LinkTypeFacade(BaseService):
    """Read/write entry point for global and per-workspace link types."""

    def __init__(self) -> None:
        super().__init__()
        self._global = GlobalLinkTypeDefinitionStore()
        self._workspace = WorkspaceLinkTypeDefinitionStore()

    # ---------- guards ----------

    @staticmethod
    def _require_admin(ctx: AuthContext) -> None:
        """Global link types are tenant-wide configuration: admin only."""
        if not _ADMIN_ROLES & set(ctx.roles or []):
            raise PermissionDeniedError(
                "Editing link-type defaults requires a tenant administrator role."
            )

    # ---------- global scope ----------

    def list_global(self, ctx: AuthContext) -> List[Dict[str, Any]]:
        """Return every global link-type template of the tenant."""
        self._set_tenant_context(ctx)
        return [_global_to_dict(row) for row in self._global.list(ctx.tenant_id)]

    def create_global(
        self, ctx: AuthContext, key: str, definition: Any
    ) -> Dict[str, Any]:
        """Create a new tenant-wide link type."""
        self._set_tenant_context(ctx)
        self._require_admin(ctx)
        row = self._global.create(ctx.tenant_id, key, definition)
        self._audit(
            ctx=ctx,
            operation="create",
            entity_type="GlobalLinkTypeDefinition",
            entity_id=row.id,
        )
        return _global_to_dict(row)

    def update_global(
        self, ctx: AuthContext, key: str, definition: Any
    ) -> Dict[str, Any]:
        """Replace a global template and propagate it to on-default workspaces."""
        self._set_tenant_context(ctx)
        self._require_admin(ctx)
        row, propagated = self._global.update(ctx.tenant_id, key, definition)
        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="GlobalLinkTypeDefinition",
            entity_id=row.id,
        )
        return _global_to_dict(row, propagated_to=propagated)

    def delete_global(self, ctx: AuthContext, key: str) -> None:
        """Delete a global template (workspace overrides survive, unlinked)."""
        self._set_tenant_context(ctx)
        self._require_admin(ctx)
        row = self._global.get(ctx.tenant_id, key)
        self._global.delete(ctx.tenant_id, key)
        self._audit(
            ctx=ctx,
            operation="delete",
            entity_type="GlobalLinkTypeDefinition",
            entity_id=row.id if row is not None else None,
        )

    # ---------- workspace scope ----------

    def list_workspace(
        self, ctx: AuthContext, workspace_id: UUID | str
    ) -> List[Dict[str, Any]]:
        """Return the resolved catalog rows of a workspace, inactive ones included.

        Read-only, so no admin gate: the trace-link dialog and the MCP schema
        validator both need this on every ordinary request.
        """
        self._set_tenant_context(ctx)
        return [
            _workspace_to_dict(row)
            for row in self._workspace.list(ctx.tenant_id, workspace_id)
        ]

    def update_workspace(
        self,
        ctx: AuthContext,
        workspace_id: UUID | str,
        key: str,
        definition: Any,
    ) -> Dict[str, Any]:
        """Override one link type for one workspace."""
        self._set_tenant_context(ctx)
        self._require_admin(ctx)
        row = self._workspace.update(ctx.tenant_id, workspace_id, key, definition)
        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="WorkspaceLinkTypeDefinition",
            entity_id=row.id,
        )
        return _workspace_to_dict(row)

    def reset_workspace(
        self, ctx: AuthContext, workspace_id: UUID | str, key: str
    ) -> Dict[str, Any]:
        """Restore a workspace override to its default."""
        self._set_tenant_context(ctx)
        self._require_admin(ctx)
        row = self._workspace.reset(ctx.tenant_id, workspace_id, key)
        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="WorkspaceLinkTypeDefinition",
            entity_id=row.id,
        )
        return _workspace_to_dict(row)


__all__ = ["LinkTypeFacade"]
```

Add `"create"`, `"update"` and `"delete"` operations for the two new `entity_type` values wherever `AuditEntry.op` choices are enforced — an undeclared operation string raises **after** the service has already mutated, so this is not optional.

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST application/tests/test_link_type_facade.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/application/link_type_facade.py backend/application/tests/test_link_type_facade.py
git commit -m "feat(link-types): add the Layer-2 link-type facade"
```

---

### Task 20: REST endpoints for global defaults and workspace overrides

**Files:**
- Create: `backend/rest_api/link_type_views.py`
- Modify: `backend/rest_api/urls.py` (import + 4 `path()` entries)
- Test: `backend/rest_api/tests/test_link_type_views.py`

**Interfaces:**
- Consumes: `application.link_type_facade.LinkTypeFacade` (Task 19)
- Produces:
  - `GET|POST /api/v1/link-type-defaults/`
  - `PUT|DELETE /api/v1/link-type-defaults/<str:key>/`
  - `GET /api/v1/workspaces/<uuid:workspace_id>/link-type-definitions/`
  - `PUT /api/v1/workspaces/<uuid:workspace_id>/link-type-definitions/<str:key>/`
  - `POST /api/v1/workspaces/<uuid:workspace_id>/link-type-definitions/<str:key>/reset/`

`<uuid:workspace_id>` is the strict converter on purpose: the lenient `<str:>` converter lets a non-UUID reach the view and 500 in the service instead of 404-ing at the router.

- [ ] **Step 1: Write the failing test**

```python
# backend/rest_api/tests/test_link_type_views.py
"""REST surface for the link-type catalog."""
from __future__ import annotations

import uuid

import pytest
from django.urls import reverse

from link_types.builtin import builtin_definition


@pytest.fixture
def api(db, authenticated_admin_client, seeded_workspace):
    """`authenticated_admin_client` / `seeded_workspace` come from the app fixtures."""
    return authenticated_admin_client, seeded_workspace


@pytest.mark.django_db
def test_global_list_returns_the_seeded_types(api):
    client, _ws = api
    response = client.get("/api/v1/link-type-defaults/")
    assert response.status_code == 200
    assert {row["key"] for row in response.json()} >= {"verifies", "derives-from"}


@pytest.mark.django_db
def test_global_create_adds_a_tenant_type(api):
    client, _ws = api
    definition = builtin_definition("mitigates")
    definition["built_in"] = False
    response = client.post(
        "/api/v1/link-type-defaults/",
        data={"key": "conflicts-with", "definition": definition},
        content_type="application/json",
    )
    assert response.status_code == 201
    assert response.json()["key"] == "conflicts-with"


@pytest.mark.django_db
def test_global_create_rejects_an_invalid_suspect_rule(api):
    client, _ws = api
    definition = builtin_definition("mitigates")
    definition["suspect_rule"] = "nope"
    response = client.post(
        "/api/v1/link-type-defaults/",
        data={"key": "conflicts-with", "definition": definition},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "suspect_rule" in response.json()["detail"]


@pytest.mark.django_db
def test_global_update_reports_propagation(api):
    client, _ws = api
    definition = builtin_definition("mitigates")
    definition["impact_weight"] = 0.9
    response = client.put(
        "/api/v1/link-type-defaults/mitigates/",
        data={"definition": definition},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["propagated_to"] >= 1


@pytest.mark.django_db
def test_global_delete_rejects_a_system_owned_type(api):
    client, _ws = api
    response = client.delete("/api/v1/link-type-defaults/diagram-ref/")
    assert response.status_code == 400


@pytest.mark.django_db
def test_workspace_list_returns_resolved_rows(api):
    client, ws = api
    response = client.get(f"/api/v1/workspaces/{ws.id}/link-type-definitions/")
    assert response.status_code == 200
    body = response.json()
    assert all("is_customized" in row for row in body)
    assert all("definition" in row for row in body)


@pytest.mark.django_db
def test_workspace_update_then_reset(api):
    client, ws = api
    definition = builtin_definition("mitigates")
    definition["impact_weight"] = 0.7

    updated = client.put(
        f"/api/v1/workspaces/{ws.id}/link-type-definitions/mitigates/",
        data={"definition": definition},
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert updated.json()["is_customized"] is True

    reset = client.post(
        f"/api/v1/workspaces/{ws.id}/link-type-definitions/mitigates/reset/"
    )
    assert reset.status_code == 200
    assert reset.json()["is_customized"] is False
    assert reset.json()["definition"]["impact_weight"] == 0.5


@pytest.mark.django_db
def test_a_non_uuid_workspace_404s_instead_of_500ing(api):
    client, _ws = api
    response = client.get("/api/v1/workspaces/not-a-uuid/link-type-definitions/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_an_unknown_key_returns_400(api):
    client, ws = api
    response = client.post(
        f"/api/v1/workspaces/{ws.id}/link-type-definitions/nope/reset/"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_a_viewer_cannot_write(db, authenticated_viewer_client, seeded_workspace):
    definition = builtin_definition("mitigates")
    response = authenticated_viewer_client.put(
        f"/api/v1/workspaces/{seeded_workspace.id}/link-type-definitions/mitigates/",
        data={"definition": definition},
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_a_viewer_can_read(db, authenticated_viewer_client, seeded_workspace):
    response = authenticated_viewer_client.get(
        f"/api/v1/workspaces/{seeded_workspace.id}/link-type-definitions/"
    )
    assert response.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST rest_api/tests/test_link_type_views.py -v`
Expected: FAIL — every request returns 404 (no route registered)

- [ ] **Step 3: Write minimal implementation**

```python
# backend/rest_api/link_type_views.py
"""REST endpoints for the LinkTypeCatalog.

Shape mirrors ``rest_api.global_default_views`` (the workflow/permission
global-default endpoints): thin APIViews that map ``application`` exceptions
onto status codes and never touch the ORM themselves.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.link_type_facade import LinkTypeFacade
from persistence.errors import NotFoundError, PermissionDeniedError, ValidationError


def _facade() -> LinkTypeFacade:
    return LinkTypeFacade()


def _handle(func, *args, success: int = status.HTTP_200_OK, **kwargs) -> Response:
    """Run a facade call and map its exceptions to HTTP status codes."""
    try:
        payload = func(*args, **kwargs)
    except PermissionDeniedError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
    except NotFoundError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    except ValidationError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    if payload is None:
        return Response(status=status.HTTP_204_NO_CONTENT)
    return Response(payload, status=success)


class LinkTypeDefaultsListView(APIView):
    """GET/POST /api/v1/link-type-defaults/ — tenant-wide templates."""

    @extend_schema(tags=["link-types"])
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return _handle(_facade().list_global, request.auth_context)

    @extend_schema(tags=["link-types"])
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        key = (request.data or {}).get("key")
        definition = (request.data or {}).get("definition")
        if not key:
            return Response(
                {"detail": "Field 'key' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return _handle(
            _facade().create_global,
            request.auth_context,
            key,
            definition,
            success=status.HTTP_201_CREATED,
        )


class LinkTypeDefaultsDetailView(APIView):
    """PUT/DELETE /api/v1/link-type-defaults/<key>/."""

    @extend_schema(tags=["link-types"])
    def put(self, request: Request, key: str, *args: Any, **kwargs: Any) -> Response:
        definition = (request.data or {}).get("definition")
        return _handle(_facade().update_global, request.auth_context, key, definition)

    @extend_schema(tags=["link-types"])
    def delete(self, request: Request, key: str, *args: Any, **kwargs: Any) -> Response:
        return _handle(_facade().delete_global, request.auth_context, key)


class WorkspaceLinkTypeListView(APIView):
    """GET /api/v1/workspaces/<uuid>/link-type-definitions/ — resolved catalog."""

    @extend_schema(tags=["link-types"])
    def get(
        self, request: Request, workspace_id: UUID, *args: Any, **kwargs: Any
    ) -> Response:
        return _handle(_facade().list_workspace, request.auth_context, workspace_id)


class WorkspaceLinkTypeDetailView(APIView):
    """PUT /api/v1/workspaces/<uuid>/link-type-definitions/<key>/."""

    @extend_schema(tags=["link-types"])
    def put(
        self,
        request: Request,
        workspace_id: UUID,
        key: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        definition = (request.data or {}).get("definition")
        return _handle(
            _facade().update_workspace,
            request.auth_context,
            workspace_id,
            key,
            definition,
        )


class WorkspaceLinkTypeResetView(APIView):
    """POST /api/v1/workspaces/<uuid>/link-type-definitions/<key>/reset/."""

    @extend_schema(tags=["link-types"])
    def post(
        self,
        request: Request,
        workspace_id: UUID,
        key: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        return _handle(
            _facade().reset_workspace, request.auth_context, workspace_id, key
        )
```

In `backend/rest_api/urls.py`, next to the existing `workflow-defaults/` block:

```python
from rest_api.link_type_views import (
    LinkTypeDefaultsDetailView,
    LinkTypeDefaultsListView,
    WorkspaceLinkTypeDetailView,
    WorkspaceLinkTypeListView,
    WorkspaceLinkTypeResetView,
)
```

```python
    path(
        "link-type-defaults/",
        LinkTypeDefaultsListView.as_view(),
        name="link-type-defaults-list",
    ),
    path(
        "link-type-defaults/<str:key>/",
        LinkTypeDefaultsDetailView.as_view(),
        name="link-type-defaults-detail",
    ),
    # <uuid:> deliberately, not <str:>: the lenient converter lets a non-UUID
    # reach the view and 500 in the service instead of 404-ing at the router.
    path(
        "workspaces/<uuid:workspace_id>/link-type-definitions/",
        WorkspaceLinkTypeListView.as_view(),
        name="workspace-link-types-list",
    ),
    path(
        "workspaces/<uuid:workspace_id>/link-type-definitions/<str:key>/reset/",
        WorkspaceLinkTypeResetView.as_view(),
        name="workspace-link-types-reset",
    ),
    path(
        "workspaces/<uuid:workspace_id>/link-type-definitions/<str:key>/",
        WorkspaceLinkTypeDetailView.as_view(),
        name="workspace-link-types-detail",
    ),
```

The `reset/` path is registered **before** the `<str:key>/` path: Django matches in order, and `<str:key>` would otherwise swallow `mitigates/reset`.

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST rest_api/tests/test_link_type_views.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/rest_api/link_type_views.py backend/rest_api/urls.py backend/rest_api/tests/test_link_type_views.py
git commit -m "feat(link-types): expose link-type defaults and workspace overrides via REST"
```

---

### Task 21: MCP `link_type.*` group and the free-string `create_link` schema

**Files:**
- Create: `backend/mcp_server/tools/link_type.py`
- Modify: `backend/mcp_server/tool_registry.py` (import, `register_groups`, read-exempt list)
- Modify: `backend/mcp_server/tools/cross_cutting.py:285-293` (`link_type` enum → string)
- Test: `backend/mcp_server/tests/test_link_type_tool_group.py`

**Interfaces:**
- Consumes: `application.link_type_facade.LinkTypeFacade` (Task 19)
- Produces: MCP tools `link_type.list`, `link_type.get`, `link_type.create`, `link_type.update`, `link_type.reset`

**Schema change (spec section 4.1, a documented trade-off):** `link_type` in `traceability.create_link` becomes `{"type": "string"}` instead of `{"enum": sorted(MANUAL_LINK_TYPES)}`. A per-tenant enum would make the `tools/list` manifest tenant-specific, which breaks the "manifest built once" model. Client-side autocomplete is lost; server-side validation compensates by listing the valid values in the error message.

Every handler must return primitives only — the transport serialises with stdlib `json.dumps`, so a `UUID` in the payload becomes an opaque INTERNAL_ERROR. The facade already guarantees this; the tests below pin it. Payloads must also avoid a top-level `content` key, which collides with the JSON-RPC envelope.

- [ ] **Step 1: Write the failing test**

```python
# backend/mcp_server/tests/test_link_type_tool_group.py
"""MCP link_type.* tool group and the create_link schema change."""
from __future__ import annotations

import json
import uuid

import pytest

from link_types.builtin import builtin_definition


@pytest.fixture
def group():
    from mcp_server.tools.link_type import LinkTypeToolGroup

    return LinkTypeToolGroup()


@pytest.fixture
def env(db):
    from auth_tenancy.models import AuthContext
    from link_types.workspace_store import provision_workspace_link_types
    from persistence.models import Tenant, Workspace
    from persistence.tenancy import TenantContext

    tenant = Tenant.objects.create(name="mcp-link-type")
    TenantContext.set_tenant(tenant.id)
    ws = Workspace.objects.create(tenant=tenant, name="ws")
    provision_workspace_link_types(workspace_id=ws.id, tenant_id=tenant.id)
    ctx = AuthContext(
        user_id=uuid.uuid4(), tenant_id=tenant.id, workspace_id=ws.id, roles=["admin"]
    )
    yield {"workspace": ws, "ctx": ctx}
    TenantContext.clear_tenant()


def test_the_group_publishes_five_tools(group):
    names = {schema["name"] for schema in group._TOOL_SCHEMAS}
    assert names == {
        "link_type.list",
        "link_type.get",
        "link_type.create",
        "link_type.update",
        "link_type.reset",
    }


def test_every_published_tool_has_a_handler(group):
    assert set(group._TOOL_MAP) == {
        schema["name"] for schema in group._TOOL_SCHEMAS
    }
    for handler in group._TOOL_MAP.values():
        assert hasattr(group, handler)


def test_the_group_is_registered(db):
    from mcp_server.tool_registry import ToolRegistry

    registry = ToolRegistry()
    registry._ensure_default_groups()
    assert "link_type" in registry._groups


def test_create_link_no_longer_publishes_an_enum():
    from mcp_server.tools.cross_cutting import CrossCuttingToolGroup

    schema = next(
        s
        for s in CrossCuttingToolGroup()._TOOL_SCHEMAS
        if s["name"] == "traceability.create_link"
    )
    link_type = schema["inputSchema"]["properties"]["link_type"]
    assert link_type["type"] == "string"
    assert "enum" not in link_type


@pytest.mark.django_db
def test_list_returns_the_workspace_catalog(group, env):
    result = group._handle_list(
        params={"workspace_id": str(env["workspace"].id)},
        auth_context=env["ctx"],
        api_key="k",
    )
    assert result.is_error is False
    assert len(result.payload["link_types"]) == 8


@pytest.mark.django_db
def test_every_payload_survives_stdlib_json_dumps(group, env):
    """The transport uses stdlib json.dumps — a UUID here is a 500."""
    result = group._handle_list(
        params={"workspace_id": str(env["workspace"].id)},
        auth_context=env["ctx"],
        api_key="k",
    )
    json.dumps(result.payload)


@pytest.mark.django_db
def test_no_payload_uses_the_reserved_content_key(group, env):
    result = group._handle_list(
        params={"workspace_id": str(env["workspace"].id)},
        auth_context=env["ctx"],
        api_key="k",
    )
    assert "content" not in result.payload


@pytest.mark.django_db
def test_get_returns_one_definition(group, env):
    result = group._handle_get(
        params={"workspace_id": str(env["workspace"].id), "key": "verifies"},
        auth_context=env["ctx"],
        api_key="k",
    )
    assert result.payload["link_type"]["key"] == "verifies"


@pytest.mark.django_db
def test_get_of_an_unknown_key_is_a_not_found_error(group, env):
    result = group._handle_get(
        params={"workspace_id": str(env["workspace"].id), "key": "nope"},
        auth_context=env["ctx"],
        api_key="k",
    )
    assert result.is_error is True
    assert result.code == "NOT_FOUND"


@pytest.mark.django_db
def test_create_adds_a_tenant_type(group, env):
    definition = builtin_definition("mitigates")
    definition["built_in"] = False
    result = group._handle_create(
        params={"key": "conflicts-with", "definition": definition},
        auth_context=env["ctx"],
        api_key="k",
    )
    assert result.is_error is False
    assert result.payload["link_type"]["key"] == "conflicts-with"


@pytest.mark.django_db
def test_create_with_a_bad_suspect_rule_is_a_validation_error(group, env):
    definition = builtin_definition("mitigates")
    definition["suspect_rule"] = "nope"
    result = group._handle_create(
        params={"key": "conflicts-with", "definition": definition},
        auth_context=env["ctx"],
        api_key="k",
    )
    assert result.is_error is True
    assert result.code == "VALIDATION_ERROR"
    assert "suspect_rule" in result.message


@pytest.mark.django_db
def test_update_then_reset_round_trips(group, env):
    definition = builtin_definition("mitigates")
    definition["impact_weight"] = 0.7
    updated = group._handle_update(
        params={
            "workspace_id": str(env["workspace"].id),
            "key": "mitigates",
            "definition": definition,
        },
        auth_context=env["ctx"],
        api_key="k",
    )
    assert updated.payload["link_type"]["is_customized"] is True

    reset = group._handle_reset(
        params={"workspace_id": str(env["workspace"].id), "key": "mitigates"},
        auth_context=env["ctx"],
        api_key="k",
    )
    assert reset.payload["link_type"]["is_customized"] is False


@pytest.mark.django_db
def test_list_requires_a_workspace_id(group, env):
    result = group._handle_list(params={}, auth_context=env["ctx"], api_key="k")
    assert result.is_error is True
    assert result.code == "VALIDATION_ERROR"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$PYTEST mcp_server/tests/test_link_type_tool_group.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_server.tools.link_type'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/mcp_server/tools/link_type.py
"""LinkTypeToolGroup — MCP access to the tenant link-type catalog.

Mirrors the ``workflow.*`` / ``attribute_definition.*`` groups: five tools over
``application.link_type_facade.LinkTypeFacade``, no ORM here (ADR-01).

Every payload is primitive-only. The transport serialises with stdlib
``json.dumps``, which raises on a ``UUID`` or ``datetime`` and reaches the
client as an opaque INTERNAL_ERROR — the facade already returns ``str`` ids, so
nothing here re-introduces them. No payload uses a top-level ``content`` key,
which collides with the JSON-RPC result envelope.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from auth_tenancy.context import AuthContext
from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup, optional_uuid

from application.link_type_facade import LinkTypeFacade
from persistence.errors import NotFoundError, PermissionDeniedError, ValidationError

logger = logging.getLogger(__name__)

_WORKSPACE_PROP = {
    "workspace_id": {
        "type": "string",
        "description": "UUID of the workspace whose catalog is addressed.",
    }
}
_KEY_PROP = {
    "key": {
        "type": "string",
        "description": "Link-type key, e.g. 'verifies' or a tenant-defined one.",
    }
}
_DEFINITION_PROP = {
    "definition": {
        "type": "object",
        "description": (
            "definition_json: label (de/en x downstream/upstream/neutral), "
            "allowed_pairs, coverage_relevant, suspect_rule "
            "(none | target_change_flags_source | source_change_flags_target | "
            "parent_change_flags_children), impact_weight, manual_creatable, "
            "system_owned, active, built_in."
        ),
    }
}


class LinkTypeToolGroup(BaseToolGroup):
    """Five tools over the link-type catalog (2 read, 3 write)."""

    _TOOL_MAP = {
        "link_type.list": "_handle_list",
        "link_type.get": "_handle_get",
        "link_type.create": "_handle_create",
        "link_type.update": "_handle_update",
        "link_type.reset": "_handle_reset",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "link_type.list",
            "description": (
                "List the trace-link types available in a workspace, with their "
                "allowed endpoint pairs (read-only). Call this before "
                "traceability.create_link to learn which link_type values and "
                "artifact-type combinations the workspace accepts."
            ),
            "inputSchema": {
                "type": "object",
                "properties": dict(_WORKSPACE_PROP),
                "required": ["workspace_id"],
            },
        },
        {
            "name": "link_type.get",
            "description": "Fetch one link-type definition of a workspace (read-only).",
            "inputSchema": {
                "type": "object",
                "properties": {**_WORKSPACE_PROP, **_KEY_PROP},
                "required": ["workspace_id", "key"],
            },
        },
        {
            "name": "link_type.create",
            "description": (
                "Create a tenant-wide link type (write, audited, admin only). "
                "suspect_rule must be one of the four supported behaviours."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {**_KEY_PROP, **_DEFINITION_PROP},
                "required": ["key", "definition"],
            },
        },
        {
            "name": "link_type.update",
            "description": (
                "Update a link type (write, audited, admin only). With "
                "workspace_id the change is a workspace override; without it "
                "the tenant-wide default is edited and propagated to every "
                "workspace still on the default."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {**_WORKSPACE_PROP, **_KEY_PROP, **_DEFINITION_PROP},
                "required": ["key", "definition"],
            },
        },
        {
            "name": "link_type.reset",
            "description": (
                "Reset a workspace override back to the tenant default "
                "(write, audited, admin only)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {**_WORKSPACE_PROP, **_KEY_PROP},
                "required": ["workspace_id", "key"],
            },
        },
    ]

    @staticmethod
    def _facade() -> LinkTypeFacade:
        return LinkTypeFacade()

    @staticmethod
    def _guard(func, *args, **kwargs) -> ToolResult:
        """Run a facade call, mapping domain exceptions onto ToolResult codes."""
        try:
            return ToolResult.ok(func(*args, **kwargs))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))
        except Exception as exc:  # noqa: BLE001 — transport boundary
            logger.exception("link_type tool failed")
            return ToolResult.error("INTERNAL_ERROR", str(exc))

    def _handle_list(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        workspace_id = optional_uuid(params, "workspace_id")
        if not workspace_id:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameter 'workspace_id' is required for link_type.list.",
            )
        return self._guard(
            lambda: {
                "link_types": self._facade().list_workspace(auth_context, workspace_id)
            }
        )

    def _handle_get(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        workspace_id = optional_uuid(params, "workspace_id")
        key = (params or {}).get("key")
        if not workspace_id or not key:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameters 'workspace_id' and 'key' are required for link_type.get.",
            )

        def _get():
            rows = self._facade().list_workspace(auth_context, workspace_id)
            match = next((row for row in rows if row["key"] == key), None)
            if match is None:
                available = ", ".join(sorted(row["key"] for row in rows))
                raise NotFoundError(
                    f"Link type '{key}' not found in this workspace. "
                    f"Available: {available or '(none)'}."
                )
            return {"link_type": match}

        return self._guard(_get)

    def _handle_create(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        key = (params or {}).get("key")
        definition = (params or {}).get("definition")
        if not key:
            return ToolResult.error(
                "VALIDATION_ERROR", "Parameter 'key' is required for link_type.create."
            )
        return self._guard(
            lambda: {
                "link_type": self._facade().create_global(auth_context, key, definition)
            }
        )

    def _handle_update(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        key = (params or {}).get("key")
        definition = (params or {}).get("definition")
        workspace_id = optional_uuid(params, "workspace_id")
        if not key:
            return ToolResult.error(
                "VALIDATION_ERROR", "Parameter 'key' is required for link_type.update."
            )
        if workspace_id:
            return self._guard(
                lambda: {
                    "link_type": self._facade().update_workspace(
                        auth_context, workspace_id, key, definition
                    )
                }
            )
        return self._guard(
            lambda: {
                "link_type": self._facade().update_global(auth_context, key, definition)
            }
        )

    def _handle_reset(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        workspace_id = optional_uuid(params, "workspace_id")
        key = (params or {}).get("key")
        if not workspace_id or not key:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameters 'workspace_id' and 'key' are required for link_type.reset.",
            )
        return self._guard(
            lambda: {
                "link_type": self._facade().reset_workspace(
                    auth_context, workspace_id, key
                )
            }
        )
```

In `backend/mcp_server/tool_registry.py`:
- import `from mcp_server.tools.link_type import LinkTypeToolGroup` next to the other group imports (~line 537);
- add `"link_type": LinkTypeToolGroup(),` to the `register_groups({...})` dict (~line 584);
- add `"link_type.list"` and `"link_type.get"` to the read-exempt tool set (~line 237) so the two read tools are not WRITE-gated.

In `backend/mcp_server/tools/cross_cutting.py`, replace the `link_type` property of `traceability.create_link` (lines 285-293):

```python
                    "link_type": {
                        "type": "string",
                        # Deliberately NOT an enum (spec section 4.1): the
                        # catalog is tenant- and workspace-configurable, so a
                        # published enum would make the tools/list manifest
                        # tenant-specific and break the "manifest built once"
                        # model. Validation happens server-side against the
                        # resolved catalog and the error lists the valid
                        # values; call link_type.list to discover them.
                        "description": (
                            "TraceLink type key. Call link_type.list for the "
                            "values this workspace accepts and their allowed "
                            "source/target artifact types."
                        ),
                    },
```

Remove the now-unused `MANUAL_LINK_TYPES` import from that module.

- [ ] **Step 4: Run test to verify it passes**

Run: `$PYTEST mcp_server/tests/test_link_type_tool_group.py mcp_server/tests/test_cross_cutting_tool_group.py -v`
Expected: PASS (13 passed in the new module; the cross-cutting suite green)

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_server/tools/link_type.py backend/mcp_server/tool_registry.py backend/mcp_server/tools/cross_cutting.py backend/mcp_server/tests/test_link_type_tool_group.py
git commit -m "feat(link-types): add the MCP link_type tool group and free-string create_link schema"
```

---

## Phase F — Frontend

### Task 22: `link-types` API wrapper, types and context

**Files:**
- Create: `frontend/src/api/link-types.ts`
- Create: `frontend/src/context/LinkTypeContext.tsx`
- Modify: `frontend/src/types/index.ts:263-278` (replace the hardcoded union)
- Modify: `frontend/src/App.tsx` (mount the provider inside `WorkspaceProvider`)
- Test: `frontend/src/api/link-types.test.ts`
- Test: `frontend/src/context/link-type-context.test.tsx`

**Interfaces:**
- Consumes: Task 20's REST routes
- Produces:
  - `LinkTypeDefinition` — `{ label: { de: TriLabel; en: TriLabel }; allowed_pairs: LinkTypePair[]; coverage_relevant: boolean; suspect_rule: SuspectRule; impact_weight: number; manual_creatable: boolean; system_owned: boolean; active: boolean; built_in: boolean }`
  - `LinkTypePair` — `{ source_type: string; target_type: string }`
  - `TriLabel` — `{ downstream: string; upstream: string; neutral: string }`
  - `SuspectRule` — `"none" | "target_change_flags_source" | "source_change_flags_target" | "parent_change_flags_children"`
  - `WorkspaceLinkType` — `{ id: UUID; workspace_id: UUID; key: string; definition: LinkTypeDefinition; is_customized: boolean; source_global_id: UUID | null; version: number }`
  - `linkTypesApi.{ listForWorkspace, updateForWorkspace, resetForWorkspace, listGlobal, createGlobal, updateGlobal, deleteGlobal }`
  - `useLinkTypes(): { linkTypes: WorkspaceLinkType[]; isLoading: boolean; error: string | null; reload: () => Promise<void>; isAllowedPair: (key, sourceType, targetType) => boolean; labelFor: (key, lang, perspective) => string }`

**Breaking type change:** `LinkType` stops being a 14-member union and becomes `string`. The union was a second, independently maintained source of truth that already drifted (`diagram-ref` was missing) — audit finding B4. Every `as LinkType` cast in the codebase keeps compiling.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/api/link-types.test.ts
import { describe, expect, it, vi, beforeEach } from "vitest";

import { apiClient } from "./client";
import { linkTypesApi } from "./link-types";

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

const definition = {
  label: {
    de: { downstream: "verifiziert", upstream: "wird verifiziert von", neutral: "Verifikation" },
    en: { downstream: "verifies", upstream: "is verified by", neutral: "Verification" },
  },
  allowed_pairs: [{ source_type: "TestCase", target_type: "Requirement" }],
  coverage_relevant: true,
  suspect_rule: "target_change_flags_source" as const,
  impact_weight: 1.0,
  manual_creatable: true,
  system_owned: false,
  active: true,
  built_in: true,
};

const row = {
  id: "11111111-1111-1111-1111-111111111111",
  workspace_id: "22222222-2222-2222-2222-222222222222",
  key: "verifies",
  definition,
  is_customized: false,
  source_global_id: null,
  version: 1,
};

describe("linkTypesApi", () => {
  beforeEach(() => vi.clearAllMocks());

  it("reads the workspace catalog from the workspace-scoped route", async () => {
    vi.mocked(apiClient.get).mockResolvedValue([row]);
    const result = await linkTypesApi.listForWorkspace(row.workspace_id);
    expect(apiClient.get).toHaveBeenCalledWith(
      `/workspaces/${row.workspace_id}/link-type-definitions/`,
    );
    expect(result[0].key).toBe("verifies");
  });

  it("sends the definition wrapped in a definition envelope on update", async () => {
    vi.mocked(apiClient.put).mockResolvedValue({ ...row, is_customized: true });
    const result = await linkTypesApi.updateForWorkspace(
      row.workspace_id,
      "verifies",
      definition,
    );
    expect(apiClient.put).toHaveBeenCalledWith(
      `/workspaces/${row.workspace_id}/link-type-definitions/verifies/`,
      { definition },
    );
    expect(result.is_customized).toBe(true);
  });

  it("resets via the dedicated reset route", async () => {
    vi.mocked(apiClient.post).mockResolvedValue(row);
    await linkTypesApi.resetForWorkspace(row.workspace_id, "verifies");
    expect(apiClient.post).toHaveBeenCalledWith(
      `/workspaces/${row.workspace_id}/link-type-definitions/verifies/reset/`,
      {},
    );
  });

  it("reads global defaults from the tenant route", async () => {
    vi.mocked(apiClient.get).mockResolvedValue([]);
    await linkTypesApi.listGlobal();
    expect(apiClient.get).toHaveBeenCalledWith("/link-type-defaults/");
  });

  it("creates a global type with key and definition", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ key: "conflicts-with", definition });
    await linkTypesApi.createGlobal("conflicts-with", definition);
    expect(apiClient.post).toHaveBeenCalledWith("/link-type-defaults/", {
      key: "conflicts-with",
      definition,
    });
  });

  it("returns an empty list when the response is not an array", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(undefined as never);
    await expect(linkTypesApi.listForWorkspace(row.workspace_id)).resolves.toEqual([]);
  });
});
```

```tsx
// frontend/src/context/link-type-context.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { LinkTypeProvider, useLinkTypes } from "./LinkTypeContext";
import { linkTypesApi } from "../api/link-types";

vi.mock("../api/link-types", () => ({
  linkTypesApi: { listForWorkspace: vi.fn() },
}));

vi.mock("./WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1" } }),
}));

const verifies = {
  id: "1",
  workspace_id: "ws-1",
  key: "verifies",
  definition: {
    label: {
      de: { downstream: "verifiziert", upstream: "wird verifiziert von", neutral: "Verifikation" },
      en: { downstream: "verifies", upstream: "is verified by", neutral: "Verification" },
    },
    allowed_pairs: [{ source_type: "TestCase", target_type: "Requirement" }],
    coverage_relevant: true,
    suspect_rule: "target_change_flags_source" as const,
    impact_weight: 1,
    manual_creatable: true,
    system_owned: false,
    active: true,
    built_in: true,
  },
  is_customized: false,
  source_global_id: null,
  version: 1,
};

const references = {
  ...verifies,
  id: "2",
  key: "references",
  definition: {
    ...verifies.definition,
    allowed_pairs: [{ source_type: "*", target_type: "Diagram" }],
    coverage_relevant: false,
    suspect_rule: "none" as const,
  },
};

function Probe() {
  const { linkTypes, isLoading, isAllowedPair, labelFor } = useLinkTypes();
  if (isLoading) return <div>loading</div>;
  return (
    <div>
      <span data-testid="count">{linkTypes.length}</span>
      <span data-testid="ok">{String(isAllowedPair("verifies", "TestCase", "Requirement"))}</span>
      <span data-testid="bad">{String(isAllowedPair("verifies", "Risk", "Requirement"))}</span>
      <span data-testid="wild">{String(isAllowedPair("references", "Risk", "Diagram"))}</span>
      <span data-testid="sub">{String(isAllowedPair("verifies", "TestCase:unit", "Requirement"))}</span>
      <span data-testid="unknown">{String(isAllowedPair("nope", "TestCase", "Requirement"))}</span>
      <span data-testid="label">{labelFor("verifies", "de", "neutral")}</span>
      <span data-testid="fallback">{labelFor("nope", "de", "neutral")}</span>
    </div>
  );
}

describe("LinkTypeContext", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads the catalog for the active workspace", async () => {
    vi.mocked(linkTypesApi.listForWorkspace).mockResolvedValue([verifies, references]);
    render(
      <LinkTypeProvider>
        <Probe />
      </LinkTypeProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("count")).toHaveTextContent("2"));
  });

  it("matches allowed pairs, wildcards and sub-typed artifact types", async () => {
    vi.mocked(linkTypesApi.listForWorkspace).mockResolvedValue([verifies, references]);
    render(
      <LinkTypeProvider>
        <Probe />
      </LinkTypeProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("ok")).toHaveTextContent("true"));
    expect(screen.getByTestId("bad")).toHaveTextContent("false");
    expect(screen.getByTestId("wild")).toHaveTextContent("true");
    expect(screen.getByTestId("sub")).toHaveTextContent("true");
  });

  it("rejects an unknown key rather than defaulting to permissive", async () => {
    vi.mocked(linkTypesApi.listForWorkspace).mockResolvedValue([verifies]);
    render(
      <LinkTypeProvider>
        <Probe />
      </LinkTypeProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("unknown")).toHaveTextContent("false"));
  });

  it("labels from the catalog and falls back to the raw key", async () => {
    vi.mocked(linkTypesApi.listForWorkspace).mockResolvedValue([verifies]);
    render(
      <LinkTypeProvider>
        <Probe />
      </LinkTypeProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("label")).toHaveTextContent("Verifikation"));
    expect(screen.getByTestId("fallback")).toHaveTextContent("nope");
  });

  it("surfaces a load failure without crashing the tree", async () => {
    vi.mocked(linkTypesApi.listForWorkspace).mockRejectedValue(new Error("boom"));
    render(
      <LinkTypeProvider>
        <Probe />
      </LinkTypeProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("count")).toHaveTextContent("0"));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$VITEST src/api/link-types.test.ts src/context/link-type-context.test.tsx`
Expected: FAIL — `Failed to resolve import "./link-types"` and `"./LinkTypeContext"`

- [ ] **Step 3: Write minimal implementation**

```ts
// frontend/src/api/link-types.ts
/**
 * ARCH-L1-001 ReactFrontend — LinkTypeCatalog API.
 *
 * Wraps the tenant-wide `/link-type-defaults/` and workspace-scoped
 * `/workspaces/<id>/link-type-definitions/` endpoints.
 *
 * This module replaces the hardcoded 14-member `LinkType` union in
 * `types/index.ts` and the hardcoded `LINK_TYPE_TRI_LABELS` table in
 * `constants/traceLinkLabels.ts` as the source of truth for which link types
 * exist. Those two were maintained independently of the backend enum and had
 * already drifted (`diagram-ref` was missing from both) — audit finding B4.
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

/** One perspective triple of a link-type label. */
export interface TriLabel {
  downstream: string;
  upstream: string;
  neutral: string;
}

/** An allowed endpoint combination. `"*"` is a wildcard on either side. */
export interface LinkTypePair {
  source_type: string;
  target_type: string;
}

/** The four propagation behaviours the backend engine can dispatch on. */
export type SuspectRule =
  | "none"
  | "target_change_flags_source"
  | "source_change_flags_target"
  | "parent_change_flags_children";

/** `definition_json` as validated by `link_types.schema`. */
export interface LinkTypeDefinition {
  label: { de: TriLabel; en: TriLabel };
  allowed_pairs: LinkTypePair[];
  coverage_relevant: boolean;
  suspect_rule: SuspectRule;
  impact_weight: number;
  manual_creatable: boolean;
  system_owned: boolean;
  active: boolean;
  built_in: boolean;
}

/** A materialized per-workspace row. */
export interface WorkspaceLinkType {
  id: UUID;
  workspace_id: UUID;
  key: string;
  definition: LinkTypeDefinition;
  is_customized: boolean;
  source_global_id: UUID | null;
  version: number;
}

/** A tenant-wide template. */
export interface GlobalLinkType {
  id: UUID;
  key: string;
  definition: LinkTypeDefinition;
  version: number;
  /** Present only on an update response. */
  propagated_to?: number;
}

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

export const linkTypesApi = {
  /** Resolved catalog of a workspace, inactive rows included. */
  async listForWorkspace(workspaceId: UUID): Promise<WorkspaceLinkType[]> {
    const raw = await apiClient.get<WorkspaceLinkType[]>(
      `/workspaces/${workspaceId}/link-type-definitions/`,
    );
    return asArray<WorkspaceLinkType>(raw);
  },

  /** Override one link type for one workspace (sets `is_customized`). */
  async updateForWorkspace(
    workspaceId: UUID,
    key: string,
    definition: LinkTypeDefinition,
  ): Promise<WorkspaceLinkType> {
    return apiClient.put<WorkspaceLinkType>(
      `/workspaces/${workspaceId}/link-type-definitions/${key}/`,
      { definition },
    );
  },

  /** Restore a workspace override to its default. */
  async resetForWorkspace(workspaceId: UUID, key: string): Promise<WorkspaceLinkType> {
    return apiClient.post<WorkspaceLinkType>(
      `/workspaces/${workspaceId}/link-type-definitions/${key}/reset/`,
      {},
    );
  },

  /** Tenant-wide templates. */
  async listGlobal(): Promise<GlobalLinkType[]> {
    const raw = await apiClient.get<GlobalLinkType[]>("/link-type-defaults/");
    return asArray<GlobalLinkType>(raw);
  },

  async createGlobal(key: string, definition: LinkTypeDefinition): Promise<GlobalLinkType> {
    return apiClient.post<GlobalLinkType>("/link-type-defaults/", { key, definition });
  },

  async updateGlobal(key: string, definition: LinkTypeDefinition): Promise<GlobalLinkType> {
    return apiClient.put<GlobalLinkType>(`/link-type-defaults/${key}/`, { definition });
  },

  async deleteGlobal(key: string): Promise<void> {
    await apiClient.delete<void>(`/link-type-defaults/${key}/`);
  },
};
```

```tsx
// frontend/src/context/LinkTypeContext.tsx
/**
 * Loads the active workspace's link-type catalog once and shares it.
 *
 * Every consumer that used to import `ALL_LINK_TYPES` reads from here instead,
 * so there is exactly one source of truth per workspace rather than a
 * hardcoded frontend list drifting from the backend (audit finding B4).
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  linkTypesApi,
  type LinkTypeDefinition,
  type WorkspaceLinkType,
} from "../api/link-types";
import { useWorkspace } from "./WorkspaceContext";

type Lang = "de" | "en";
type Perspective = "downstream" | "upstream" | "neutral";

interface LinkTypeContextValue {
  linkTypes: WorkspaceLinkType[];
  isLoading: boolean;
  error: string | null;
  reload: () => Promise<void>;
  /** Only active, manually creatable types — what a link dialog may offer. */
  creatableLinkTypes: WorkspaceLinkType[];
  definitionFor: (key: string) => LinkTypeDefinition | undefined;
  isAllowedPair: (key: string, sourceType: string, targetType: string) => boolean;
  labelFor: (key: string, lang: Lang, perspective: Perspective) => string;
}

const LinkTypeContext = createContext<LinkTypeContextValue | undefined>(undefined);

/** `"TestCase:unit"` -> `"TestCase"`, mirroring the backend normalizer. */
function normalizeArtifactType(artifactType: string): string {
  return artifactType.split(":", 1)[0] ?? "";
}

export function LinkTypeProvider({ children }: { children: ReactNode }) {
  const { activeWorkspace } = useWorkspace();
  const [linkTypes, setLinkTypes] = useState<WorkspaceLinkType[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const workspaceId = activeWorkspace?.id;

  const reload = useCallback(async () => {
    if (!workspaceId) {
      setLinkTypes([]);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      setLinkTypes(await linkTypesApi.listForWorkspace(workspaceId));
    } catch (err) {
      // A failed catalog load must not take the tree down: the link dialog
      // degrades to an empty type list and says so, rather than the whole
      // workspace view unmounting.
      setLinkTypes([]);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const value = useMemo<LinkTypeContextValue>(() => {
    const byKey = new Map(linkTypes.map((row) => [row.key, row.definition]));

    return {
      linkTypes,
      isLoading,
      error,
      reload,
      creatableLinkTypes: linkTypes.filter(
        (row) => row.definition.active && row.definition.manual_creatable,
      ),
      definitionFor: (key) => byKey.get(key),
      isAllowedPair: (key, sourceType, targetType) => {
        const definition = byKey.get(key);
        // Unknown key: reject. The old frontend had no notion of an invalid
        // pair at all and let the backend 400 after the user hit Save.
        if (!definition) return false;
        const source = normalizeArtifactType(sourceType);
        const target = normalizeArtifactType(targetType);
        return definition.allowed_pairs.some(
          (pair) =>
            (pair.source_type === "*" || pair.source_type === source) &&
            (pair.target_type === "*" || pair.target_type === target),
        );
      },
      labelFor: (key, lang, perspective) =>
        byKey.get(key)?.label?.[lang]?.[perspective] ?? key,
    };
  }, [linkTypes, isLoading, error, reload]);

  return <LinkTypeContext.Provider value={value}>{children}</LinkTypeContext.Provider>;
}

export function useLinkTypes(): LinkTypeContextValue {
  const context = useContext(LinkTypeContext);
  if (context === undefined) {
    throw new Error("useLinkTypes must be used within a LinkTypeProvider");
  }
  return context;
}
```

In `frontend/src/types/index.ts`, replace lines 263-278:

```ts
// ---------------------------------------------------------------------------
// TraceLink
// ---------------------------------------------------------------------------

/**
 * A trace-link type key.
 *
 * Deliberately a plain string, not a union: the catalog is tenant- and
 * workspace-configurable, so no compile-time list can be complete. The
 * previous 14-member union was a second, independently maintained source of
 * truth that had already drifted from the backend (audit finding B4).
 * Read the live values from `useLinkTypes()`.
 */
export type LinkType = string;
```

Add `rationale`, `suspect_flagged_at` and `suspect_source_change` to the `TraceLink` interface:

```ts
  /** Why this link exists (Q1.6). Empty string when never filled in. */
  rationale?: string;
  /** Set when this link caused the other endpoint to be flagged suspect. */
  suspect_flagged_at?: ISODateTime | null;
  /** `audit.AuditEntry.id` of the change that triggered the flag above. */
  suspect_source_change?: UUID | null;
```

In `frontend/src/App.tsx`, wrap the routed tree in `<LinkTypeProvider>` **inside** `<WorkspaceProvider>` (it reads `activeWorkspace`).

- [ ] **Step 4: Run test to verify it passes**

Run: `$VITEST src/api/link-types.test.ts src/context/link-type-context.test.tsx`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/link-types.ts frontend/src/context/LinkTypeContext.tsx frontend/src/types/index.ts frontend/src/App.tsx frontend/src/api/link-types.test.ts frontend/src/context/link-type-context.test.tsx
git commit -m "feat(link-types): read the link-type catalog from the API in the frontend"
```

---

### Task 23: Catalog-driven labels, dialog filtering and workspace settings

**Files:**
- Modify: `frontend/src/constants/traceLinkLabels.ts` (table becomes a fallback)
- Modify: `frontend/src/components/shared/CreateTraceLinkDialog/create-trace-link-dialog.tsx:32,372,587-595`
- Modify: `frontend/src/components/WorkspaceSettings/WorkspaceSettings.tsx:653,677`
- Test: `frontend/src/components/shared/CreateTraceLinkDialog/create-trace-link-dialog.test.tsx` (extend)
- Test: `frontend/src/constants/traceLinkLabels.test.ts` (adjust)

**Interfaces:**
- Consumes: `useLinkTypes()` (Task 22)
- Produces: `getTriLabel(key, lang, perspective, catalogLabel?)` — catalog label wins, the static table is the pre-load fallback; `ALL_LINK_TYPES` is deleted

**Do not move any `data-testid`.** `create-trace-link-type-select` and its siblings are landed on by Playwright specs that vitest never exercises; a relocation stays green locally and breaks E2E silently. The dialog keeps every existing test id and only changes what fills the `<option>` list.

- [ ] **Step 1: Write the failing test**

```tsx
// appended to frontend/src/components/shared/CreateTraceLinkDialog/create-trace-link-dialog.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../../context/LinkTypeContext", () => ({
  useLinkTypes: () => ({
    linkTypes: [],
    isLoading: false,
    error: null,
    reload: vi.fn(),
    creatableLinkTypes: [
      {
        key: "verifies",
        definition: {
          label: {
            de: { downstream: "verifiziert", upstream: "wird verifiziert von", neutral: "Verifikation" },
            en: { downstream: "verifies", upstream: "is verified by", neutral: "Verification" },
          },
          allowed_pairs: [{ source_type: "TestCase", target_type: "Requirement" }],
          active: true,
          manual_creatable: true,
        },
      },
      {
        key: "mitigates",
        definition: {
          label: {
            de: { downstream: "mindert", upstream: "wird gemindert durch", neutral: "Risikominderung" },
            en: { downstream: "mitigates", upstream: "is mitigated by", neutral: "Mitigation" },
          },
          allowed_pairs: [{ source_type: "Risk", target_type: "Requirement" }],
          active: true,
          manual_creatable: true,
        },
      },
    ],
    definitionFor: vi.fn(),
    isAllowedPair: (key: string, source: string) =>
      (key === "verifies" && source === "TestCase") || (key === "mitigates" && source === "Risk"),
    labelFor: (key: string) => (key === "verifies" ? "Verifikation" : "Risikominderung"),
  }),
}));

describe("CreateTraceLinkDialog link-type options", () => {
  it("offers the catalog types, not a hardcoded list", async () => {
    render(<CreateTraceLinkDialog isOpen sourceId="s" sourceType="TestCase" onClose={vi.fn()} />);
    const select = await screen.findByTestId("create-trace-link-type-select");
    const options = Array.from(select.querySelectorAll("option")).map((o) => o.value);
    expect(options).toEqual(["verifies"]);
  });

  it("hides a type whose allowed_pairs do not match the source artifact type", async () => {
    render(<CreateTraceLinkDialog isOpen sourceId="s" sourceType="Risk" onClose={vi.fn()} />);
    const select = await screen.findByTestId("create-trace-link-type-select");
    const options = Array.from(select.querySelectorAll("option")).map((o) => o.value);
    expect(options).toEqual(["mitigates"]);
    expect(options).not.toContain("verifies");
  });

  it("keeps the existing test id so the Playwright specs still land", async () => {
    render(<CreateTraceLinkDialog isOpen sourceId="s" sourceType="TestCase" onClose={vi.fn()} />);
    expect(await screen.findByTestId("create-trace-link-type-select")).toBeInTheDocument();
  });

  it("renders the catalog label, not the raw key", async () => {
    render(<CreateTraceLinkDialog isOpen sourceId="s" sourceType="TestCase" onClose={vi.fn()} />);
    const select = await screen.findByTestId("create-trace-link-type-select");
    expect(select.querySelector("option")?.textContent).toBe("Verifikation");
  });

  it("shows an empty-state hint when no type fits the endpoints", async () => {
    render(<CreateTraceLinkDialog isOpen sourceId="s" sourceType="Interview" onClose={vi.fn()} />);
    expect(await screen.findByTestId("create-trace-link-no-types")).toBeInTheDocument();
  });
});
```

```ts
// frontend/src/constants/traceLinkLabels.test.ts — replace the "14 types" assertions
import { describe, expect, it } from "vitest";

import { FALLBACK_TRI_LABELS, getTriLabel } from "./traceLinkLabels";

describe("getTriLabel", () => {
  it("prefers a catalog label over the static fallback", () => {
    expect(
      getTriLabel("verifies", "de", "neutral", {
        downstream: "prüft",
        upstream: "wird geprüft von",
        neutral: "Prüfung",
      }),
    ).toBe("Prüfung");
  });

  it("falls back to the static table for a built-in key", () => {
    expect(getTriLabel("verifies", "de", "neutral")).toBe("Verifikation");
  });

  it("falls back to the raw key for a tenant-invented type", () => {
    expect(getTriLabel("conflicts-with", "de", "neutral")).toBe("conflicts-with");
  });

  it("no longer exports a hardcoded complete list", async () => {
    const module = await import("./traceLinkLabels");
    expect("ALL_LINK_TYPES" in module).toBe(false);
  });

  it("the fallback table only covers the eight core types", () => {
    expect(Object.keys(FALLBACK_TRI_LABELS).sort()).toEqual([
      "allocated-to",
      "decides",
      "decomposes",
      "derives-from",
      "diagram-ref",
      "mitigates",
      "references",
      "verifies",
    ]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$VITEST src/components/shared/CreateTraceLinkDialog src/constants/traceLinkLabels.test.ts`
Expected: FAIL — the dialog renders all 14 hardcoded options; `ALL_LINK_TYPES` is still exported

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/constants/traceLinkLabels.ts`:
- rename `LINK_TYPE_TRI_LABELS` to `FALLBACK_TRI_LABELS` and reduce it to the eight core keys (delete the `parent-child`, `satisfies`, `implements`, `refines`, `documents`, `realizes`, `traces`, `copy-of`, `uses-term` entries; add `mitigates` and `references`);
- delete `ALL_LINK_TYPES`;
- change the signature and body of `getTriLabel`:

```ts
/**
 * Resolve a link-type label.
 *
 * The catalog label wins. The static table below is only the pre-load
 * fallback for the eight built-in keys — a tenant-invented type has no static
 * entry and renders as its raw key until the catalog arrives.
 */
export function getTriLabel(
  key: string,
  lang: SupportedLang,
  direction: LinkDirection,
  catalogLabel?: TriLabel,
): string {
  if (catalogLabel) return catalogLabel[direction];
  return FALLBACK_TRI_LABELS[key]?.[lang]?.[direction] ?? key;
}
```

and change the table's type to `Record<string, TriLabelEntry>` (it is no longer exhaustive over a union).

In `create-trace-link-dialog.tsx`:
- replace the `ALL_LINK_TYPES, getTriLabel` import with `import { useLinkTypes } from '../../../context/LinkTypeContext';`
- inside the component add:

```tsx
  const { creatableLinkTypes, isAllowedPair, labelFor } = useLinkTypes();

  // Only the types whose allowed_pairs actually fit the chosen endpoints
  // (spec section 4.1): offering a type the backend will reject turns a
  // preventable mistake into a 400 after the user hits Save.
  const availableLinkTypes = useMemo(
    () =>
      creatableLinkTypes.filter((row) =>
        isAllowedPair(row.key, sourceType ?? '', selectedTargetType ?? '*'),
      ),
    [creatableLinkTypes, isAllowedPair, sourceType, selectedTargetType],
  );

  // Keep the selection valid when the endpoints change under it.
  useEffect(() => {
    if (availableLinkTypes.length === 0) return;
    if (!availableLinkTypes.some((row) => row.key === linkType)) {
      setLinkType(availableLinkTypes[0].key);
    }
  }, [availableLinkTypes, linkType]);
```

- replace the option list (test id unchanged):

```tsx
            {availableLinkTypes.map((row) => (
              <option key={row.key} value={row.key}>
                {labelFor(row.key, triLabelLang, 'neutral')}
              </option>
            ))}
```

- add the empty state directly beneath the `<select>`:

```tsx
          {availableLinkTypes.length === 0 && (
            <p data-testid="create-trace-link-no-types">
              {t(
                'traceability.noLinkTypeForPair',
                'No link type in this workspace connects these two artifact types.',
              )}
            </p>
          )}
```

- disable the submit button while `availableLinkTypes.length === 0`.

In `WorkspaceSettings.tsx`, feed both `<select>`s (lines 653 and 677) from `useLinkTypes().creatableLinkTypes` instead of `ALL_LINK_TYPES`, and keep their existing `data-testid`s. Because a `<select>` silently falls back to `option[0]` for a value it does not carry, render the stored value as an extra disabled option when it is absent from the catalog — otherwise saving an untouched form downgrades a working configuration:

```tsx
  const storedIsKnown = creatableLinkTypes.some(
    (row) => row.key === activeWorkspace.decomposition_link_type,
  );
```

```tsx
    {!storedIsKnown && activeWorkspace.decomposition_link_type && (
      <option value={activeWorkspace.decomposition_link_type} disabled>
        {activeWorkspace.decomposition_link_type} (unavailable)
      </option>
    )}
```

Add the `traceability.noLinkTypeForPair` key to `frontend/src/i18n/locales/de.json` and `en.json`.

- [ ] **Step 4: Run test to verify it passes**

Run: `$VITEST src/components/shared/CreateTraceLinkDialog src/constants/traceLinkLabels.test.ts src/components/WorkspaceSettings`
Expected: PASS (10 passed)

Then restart the frontend container and spot-check the dialog in a browser — Vite has no working HMR on Windows, so an un-restarted container serves stale code:

```bash
docker compose -f deploy/docker-compose.yml --project-directory . restart frontend
npx playwright test e2e/trace-links.spec.ts --grep "link type"
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/constants/traceLinkLabels.ts frontend/src/components/shared/CreateTraceLinkDialog frontend/src/components/WorkspaceSettings frontend/src/i18n/locales
git commit -m "feat(link-types): drive link-type options and labels from the workspace catalog"
```

---

### Task 24: `LinkTypeEditorPage`

**Files:**
- Create: `frontend/src/components/LinkTypeEditor/LinkTypeEditorPage.tsx`
- Create: `frontend/src/components/LinkTypeEditor/link-type-editor-page.test.tsx`
- Modify: `frontend/src/App.tsx` (routes under `/system-settings` and `/settings`)
- Modify: `frontend/src/i18n/locales/{de,en}.json` (`linkType.*`)

**Interfaces:**
- Consumes: `linkTypesApi` (Task 22), `useLinkTypes()` (Task 22)
- Produces: `LinkTypeEditorPage({ scope }: { scope: "global" | "workspace" })`

Shell is taken from the workflow/attribute editors, with a flat list of types instead of a type×preset grid (spec section 4.2). `system_owned` rows render greyed out with a lock, exactly like `locked` attributes. Every interactive element carries a `data-testid`, and colours/sizes come from `styles/tokens.css` — no hex literals, no `style={{` under `components/` (the UI ratchet fails on new inline styles).

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/LinkTypeEditor/link-type-editor-page.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { LinkTypeEditorPage } from "./LinkTypeEditorPage";
import { linkTypesApi } from "../../api/link-types";

vi.mock("../../api/link-types", () => ({
  linkTypesApi: {
    listForWorkspace: vi.fn(),
    updateForWorkspace: vi.fn(),
    resetForWorkspace: vi.fn(),
    listGlobal: vi.fn(),
    createGlobal: vi.fn(),
    updateGlobal: vi.fn(),
    deleteGlobal: vi.fn(),
  },
}));

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1" } }),
}));

const definition = {
  label: {
    de: { downstream: "verifiziert", upstream: "wird verifiziert von", neutral: "Verifikation" },
    en: { downstream: "verifies", upstream: "is verified by", neutral: "Verification" },
  },
  allowed_pairs: [{ source_type: "TestCase", target_type: "Requirement" }],
  coverage_relevant: true,
  suspect_rule: "target_change_flags_source" as const,
  impact_weight: 1,
  manual_creatable: true,
  system_owned: false,
  active: true,
  built_in: true,
};

const verifies = {
  id: "1",
  workspace_id: "ws-1",
  key: "verifies",
  definition,
  is_customized: false,
  source_global_id: null,
  version: 1,
};

const diagramRef = {
  ...verifies,
  id: "2",
  key: "diagram-ref",
  definition: { ...definition, system_owned: true, manual_creatable: false },
};

describe("LinkTypeEditorPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(linkTypesApi.listForWorkspace).mockResolvedValue([verifies, diagramRef]);
    vi.mocked(linkTypesApi.listGlobal).mockResolvedValue([
      { id: "1", key: "verifies", definition, version: 1 },
    ]);
  });

  it("lists the workspace types in workspace scope", async () => {
    render(<LinkTypeEditorPage scope="workspace" />);
    expect(await screen.findByTestId("link-type-row-verifies")).toBeInTheDocument();
    expect(linkTypesApi.listForWorkspace).toHaveBeenCalledWith("ws-1");
  });

  it("lists the global templates in global scope", async () => {
    render(<LinkTypeEditorPage scope="global" />);
    await waitFor(() => expect(linkTypesApi.listGlobal).toHaveBeenCalled());
    expect(linkTypesApi.listForWorkspace).not.toHaveBeenCalled();
  });

  it("locks a system-owned row", async () => {
    render(<LinkTypeEditorPage scope="workspace" />);
    const row = await screen.findByTestId("link-type-row-diagram-ref");
    expect(row).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByTestId("link-type-lock-diagram-ref")).toBeInTheDocument();
  });

  it("does not lock an ordinary row", async () => {
    render(<LinkTypeEditorPage scope="workspace" />);
    const row = await screen.findByTestId("link-type-row-verifies");
    expect(row).not.toHaveAttribute("aria-disabled", "true");
  });

  it("saves an impact-weight edit through the workspace endpoint", async () => {
    vi.mocked(linkTypesApi.updateForWorkspace).mockResolvedValue({
      ...verifies,
      is_customized: true,
    });
    render(<LinkTypeEditorPage scope="workspace" />);
    await userEvent.click(await screen.findByTestId("link-type-edit-verifies"));
    const weight = await screen.findByTestId("link-type-impact-weight-input");
    await userEvent.clear(weight);
    await userEvent.type(weight, "0.6");
    await userEvent.click(screen.getByTestId("link-type-save-button"));

    await waitFor(() =>
      expect(linkTypesApi.updateForWorkspace).toHaveBeenCalledWith(
        "ws-1",
        "verifies",
        expect.objectContaining({ impact_weight: 0.6 }),
      ),
    );
  });

  it("offers reset only for a customized row", async () => {
    vi.mocked(linkTypesApi.listForWorkspace).mockResolvedValue([
      { ...verifies, is_customized: true },
    ]);
    render(<LinkTypeEditorPage scope="workspace" />);
    expect(await screen.findByTestId("link-type-reset-verifies")).toBeInTheDocument();
  });

  it("hides reset for an on-default row", async () => {
    render(<LinkTypeEditorPage scope="workspace" />);
    await screen.findByTestId("link-type-row-verifies");
    expect(screen.queryByTestId("link-type-reset-verifies")).not.toBeInTheDocument();
  });

  it("offers a new-type button in global scope only", async () => {
    const { unmount } = render(<LinkTypeEditorPage scope="global" />);
    expect(await screen.findByTestId("link-type-new-button")).toBeInTheDocument();
    unmount();
    render(<LinkTypeEditorPage scope="workspace" />);
    await screen.findByTestId("link-type-row-verifies");
    expect(screen.queryByTestId("link-type-new-button")).not.toBeInTheDocument();
  });

  it("restricts the suspect-rule select to the four supported values", async () => {
    render(<LinkTypeEditorPage scope="workspace" />);
    await userEvent.click(await screen.findByTestId("link-type-edit-verifies"));
    const select = await screen.findByTestId("link-type-suspect-rule-select");
    const options = Array.from(select.querySelectorAll("option")).map((o) => o.value);
    expect(options).toEqual([
      "none",
      "target_change_flags_source",
      "source_change_flags_target",
      "parent_change_flags_children",
    ]);
  });

  it("surfaces a save error instead of silently discarding the edit", async () => {
    vi.mocked(linkTypesApi.updateForWorkspace).mockRejectedValue(
      new Error("suspect_rule invalid"),
    );
    render(<LinkTypeEditorPage scope="workspace" />);
    await userEvent.click(await screen.findByTestId("link-type-edit-verifies"));
    await userEvent.click(screen.getByTestId("link-type-save-button"));
    expect(await screen.findByTestId("link-type-error")).toHaveTextContent(
      "suspect_rule invalid",
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$VITEST src/components/LinkTypeEditor`
Expected: FAIL — `Failed to resolve import "./LinkTypeEditorPage"`

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/components/LinkTypeEditor/LinkTypeEditorPage.tsx` with:

- a `SUSPECT_RULES` const array in exactly the order the test pins:
  ```ts
  const SUSPECT_RULES: SuspectRule[] = [
    "none",
    "target_change_flags_source",
    "source_change_flags_target",
    "parent_change_flags_children",
  ];
  ```
- `scope === "global"` loads via `linkTypesApi.listGlobal()`, `scope === "workspace"` via `linkTypesApi.listForWorkspace(activeWorkspace.id)`;
- one row per type, `data-testid={`link-type-row-${key}`}`, with `aria-disabled="true"` and a `data-testid={`link-type-lock-${key}`}` lock glyph when `definition.system_owned`;
- an edit button `link-type-edit-${key}` opening an inline form containing:
  - `link-type-impact-weight-input` (`<input type="number" min="0" step="0.1">` — the native constraint, no validation library),
  - `link-type-suspect-rule-select` (`<select>` over `SUSPECT_RULES`),
  - `link-type-coverage-relevant-checkbox`, `link-type-active-checkbox`,
  - `link-type-allowed-pairs-editor` (add/remove rows of two text inputs, `"*"` allowed),
  - `link-type-label-{lang}-{perspective}-input` for the six label fields,
  - `link-type-save-button` and `link-type-cancel-button`;
- a `link-type-reset-${key}` button rendered only when `row.is_customized` (workspace scope only), calling `linkTypesApi.resetForWorkspace`;
- a `link-type-new-button` rendered only when `scope === "global"`, opening the same form with an additional `link-type-key-input`;
- save routes to `updateForWorkspace` / `updateGlobal` / `createGlobal` by scope and mode;
- every rejection sets an error string rendered in a `data-testid="link-type-error"` element — never swallowed;
- all classes from `styles/tokens.css`; no `style={{ … }}` anywhere in the file (the UI ratchet fails the build on a new inline style under `components/`).

In `frontend/src/App.tsx` add:

```tsx
<Route path="/system-settings/link-types" element={<LinkTypeEditorPage scope="global" />} />
<Route path="/settings/link-types" element={<LinkTypeEditorPage scope="workspace" />} />
```

Add the `linkType.*` i18n keys (`title`, `impactWeight`, `suspectRule`, `coverageRelevant`, `active`, `allowedPairs`, `newType`, `reset`, `locked`, plus one label per `SUSPECT_RULES` value) to both locale files. Keys are dotted **paths**, not flat strings with dots — `keySeparator` is `"."`, so `"linkType.title"` as a literal object key never resolves.

- [ ] **Step 4: Run test to verify it passes**

Run: `$VITEST src/components/LinkTypeEditor`
Expected: PASS (11 passed)

Then restart the frontend container and open `/settings/link-types` and `/system-settings/link-types` in a browser: check that the `diagram-ref` row is visibly locked, that editing an impact weight persists across a reload, and that the layout holds at 1280px and 768px.

```bash
docker compose -f deploy/docker-compose.yml --project-directory . restart frontend
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/LinkTypeEditor frontend/src/App.tsx frontend/src/i18n/locales
git commit -m "feat(link-types): add the link-type editor for global and workspace scope"
```

---

## Cross-Spec Notes (carry these into the other plans — no task here)

These are spec obligations this plan cannot discharge on its own. They are recorded so the owning plan picks them up rather than losing them.

### To Plan #1 — Datenmodell-Konsolidierung

- **`suspect` belongs on `Artifact`.** Spec section 5 keeps `suspect` as a per-table column for now (`Requirement`, `StakeholderNeed`, `ArchitectureElement`, `TestCase` each carry their own — verified at `persistence/models.py:901,1001,1140,1460`). The clean home is `Artifact.suspect`, parallel to the `lifecycle_status` consolidation that plan already performs. Task 14's engine writes through three `model.objects.filter(artifact_id__in=…).update(suspect=True)` calls purely because the column is not on `Artifact` yet; once it is, that loop collapses to one update and stops silently skipping artifact types nobody remembered to add.
- **`GlossaryTerm` and `Icd` need Artifact rows before `references` can reach them.** Task 3 seeds `references` with `*→GlossaryTerm` and `*→Icd`, but neither model has an `artifact` FK today, and `TraceLink.source`/`target` are FKs to `Artifact` — so those pairs are inert until plan #1 section 4 lands. Nothing breaks in the meantime; the pair simply never matches. Ordering dependency, already reflected in the 11-spec sequence.

### To Plan #4 — KI-Vorschlag-als-Zustand

- **`proposed_by`/`proposed_at` need their own migration.** That spec's section 5 says they run "in derselben Migration wie die `rationale`/`suspect_*`-Felder aus der Traceability-Semantik-Spec" — impossible across plan boundaries, since plan #4 executes after plan #3. This plan owns `persistence/00XX_tracelink_semantics_fields`; plan #4 adds a second migration on the same model. The field names, types and the `TraceLink` shape it builds on are exactly as delivered by Task 12.

### To Plan #8 — GitHub-Jira-Integration

- **Adding `ExternalRef` to `references` is a data change, not a code change.** Append `{"source_type": "*", "target_type": "ExternalRef"}` to `BUILTIN_LINK_TYPES["references"]["allowed_pairs"]` in `link_types/builtin.py` and ship a data migration in the shape of `link_types/0004_grandfather_observed_pairs.py` that applies it to existing `is_customized=False` rows. `link_types.catalog.validate_link_pair` iterates `allowed_pairs` and needs no edit — Decision 6.

### To the documentation (spec section 7, last risk)

- **`suspect_rule` is a closed range and tenant admins must be told.** The four values are code-anchored because the propagation engine branches on them; a tenant admin inventing `conflicts-with` chooses an existing behaviour or `none`, and cannot express new propagation logic through configuration. Task 4's error message already lists the valid values and says so ("New propagation behaviour requires a code change"), and Task 24's editor renders them as a `<select>` rather than a free text field — but the onboarding docs for the link-type editor need the same sentence, or admins will expect more than the field offers.

---

## Self-Review

Performed after writing, per the three required checks.

### 1. Spec coverage

| Spec section | Requirement | Covered by |
|---|---|---|
| 3.1 | Eight core types as the Startbelegung | Task 3 |
| 3.1 | Migration mapping table (rename + endpoint swap + retirements) | Task 3 (`LEGACY_LINK_TYPE_MAPPING`, `SWAPPED_LEGACY_KEYS`), Task 16 (execution) |
| 3.1 | `copy-of` becomes `Artifact.copied_from` | Task 12 (field), Task 16 (data move + conflict policy) |
| 3.2 | Allowed-pairs matrix incl. coverage / suspect rule / impact weight | Task 3 (pinned test per column) |
| 3.2 | Validation "gilt immer" — `se_mode` gate and core-type escape removed ersatzlos | Task 11 |
| 3.2 | Amendment: `ExternalRef` as a `references` target | Decision 6 + Cross-Spec Note to plan #8 |
| 3.3 | `parent-child` retired; `Artifact.parent` written in the same transaction as its `decomposes` link | Task 15 (Task 16 retires the type) |
| 3.3 | Unique constraint against duplicate `decomposes` edges | Already exists (`uq_tracelink_edge`) — recorded in "Verified Against Current Code"; Task 16 deduplicates the data |
| 4 | The two models, materialized copy, no `preset` field | Task 1 |
| 4 | Propagation into non-customized rows + cache invalidation | Task 6 (`_propagate`), Task 5 (`invalidate_workspace`) |
| 4 | `definition_json` field set | Task 3 (values), Task 4 (validation) |
| 4 | Tenants can invent, edit, soft-disable types | Tasks 6, 7, 19, 20, 21, 24 |
| 4 | `suspect_rule` is a closed, code-anchored enum | Task 3 + Task 4 (error message names the boundary) |
| 4 | Bootstrap is a seed, not model introspection | Task 3 (constant), Task 8 (backfill), Task 7 (provisioning) |
| 4.1 | `GET/POST/PUT/DELETE link-type-defaults/…` | Task 20 |
| 4.1 | `GET/PUT` + `reset` on `workspaces/<id>/link-type-definitions/` | Task 20 |
| 4.1 | MCP group `link_type.{list,get,create,update,reset}` | Task 21 |
| 4.1 | MCP `link_type` becomes a free string | Task 21 |
| 4.1 | Frontend union replaced by a catalog read | Task 22 |
| 4.1 | Trace-link dialog filters by `allowed_pairs` | Task 23 |
| 4.2 | `LinkTypeEditorPage`, global + workspace scope, locked `system_owned` rows, "new type" form | Task 24 |
| 5 | `rationale`, `suspect_flagged_at`, `suspect_source_change` | Task 12 (model), Task 13 (REST) |
| 5 | Rule-driven propagation mechanism; #849 solved structurally | Task 14 |
| 5 | `suspect` stays per-table for now, noted for plan #1 | Cross-Spec Note |
| 6 | Migration steps 1–4 | Task 8 (1), Task 16 (2), Task 12 (3), Task 11 (4) |
| 7 | Direction-swap consumers identified before migrating | "Verified Against Current Code" table + Task 17 |
| 7 | `copy-of` multi-copy preflight | Task 16 (`check_copy_of_conflicts` + newest-wins/rest-as-`references`) |
| 7 | MCP enum→string trade-off stated | Task 21 |
| 7 | `suspect_rule` boundary communicated | Task 4 error text, Task 24 `<select>`, Cross-Spec Note to docs |
| 7 | Cross-spec dependency on the Datenmodell spec | Cross-Spec Note |

Two spec statements are contradicted by the current code rather than implemented, and both are recorded in "Verified Against Current Code" with evidence: the `decomposes` unique constraint already exists, and #849's serializer half is already fixed in commit `54b09760`.

### 2. Placeholder scan

`grep` for `TBD`, `TODO`, `FIXME`, `Similar to Task`, `write tests for the above`, `add appropriate error handling`, `XXX` over the whole plan returns **zero** matches. Every step names a concrete command or contains runnable code. Two deliberate, explicitly-labelled exceptions:

- Task 10's `GRANDFATHERED_PAIRS` ships example contents with an inline instruction to replace them with Task 9's `--json` output. It is not a placeholder — the file is valid and its tests pass as written; the note exists because inventing the list instead of measuring it would be the actual error.
- Task 12's and Task 16's migration numbers are given as `00XX`/`0070` with an explicit note that the migration graph, not the file name, is authoritative. Django assigns these at `makemigrations` time.

### 3. Type consistency across tasks

- `definition_json` has one shape, defined in Task 3, validated in Task 4, consumed unchanged in Tasks 5, 6, 7, 8, 10, 19, 21, 22, 24. The `label` tri-shape (Decision 3) is the same in `link_types/schema.py::_validate_label` and in `api/link-types.ts::TriLabel`.
- `suspect_rule`'s four values appear identically in `builtin.SUSPECT_RULES` (Task 3), the engine's dispatch (Task 14), the MCP schema description (Task 21), the TS `SuspectRule` union (Task 22) and the editor's `SUSPECT_RULES` array (Task 24) — the last one order-pinned by its test.
- `validate_link_pair(workspace_id, link_type, source_type, target_type, *, manual)` is produced in Task 5 and called with exactly that signature in Task 11.
- `propagate_suspect_status(source_id, ctx, *, audit_entry_id=None) -> int` is produced in Task 14; the existing caller at `requirement_service.py:501` passes the first two positionally and stays valid.
- The facade's dict shapes (`_global_to_dict`, `_workspace_to_dict`, Task 19) match the REST bodies asserted in Task 20 and the TS `WorkspaceLinkType`/`GlobalLinkType` interfaces in Task 22 field for field, including `is_customized`, `source_global_id` and `propagated_to`.
- `LinkTypePair` uses `source_type`/`target_type` on both sides of the wire — `link_types/schema.py::_validate_pairs` and `api/link-types.ts` — so the dialog's filter in Task 23 reads the same keys the backend validates.
- `provision_workspace_link_types(*, workspace_id, tenant_id) -> int` (Task 7) is keyword-only and called that way from `workspace_provisioning` (Task 7) and every test fixture in Tasks 11, 14, 15, 18, 19, 21.

### Fixes applied inline during review

- The File Structure table named `frontend/src/api/linkTypes.ts` with invented function names; corrected to `link-types.ts` with the real `linkTypesApi.*` methods (kebab-case file names per the project convention).
- The File Structure table was missing six files introduced by later tasks (`_seed_helpers.py`, `0004_grandfather_observed_pairs.py`, `grandfathered.py`, `migration_ops.py`, `diff_auditor_findings.py`, `application/link_type_facade.py`); all added.
- Spec section 5's "`suspect` on `Artifact`" note and section 7's "`suspect_rule` boundary must be communicated" had no home; both are now Cross-Spec Notes rather than silently dropped.

---
