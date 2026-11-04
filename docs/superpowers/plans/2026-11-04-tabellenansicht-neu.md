# Tabellenansicht und Massenbearbeitung Implementation Plan (neu)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A type-aware filter language, a server-side table query and a workflow-safe bulk update (`PATCH artifacts/bulk-update/`, atomic or partial) as slice 1; then bulk transition, saved views with per-user table state, the `ArtifactTable` UI and an E2E guardrail, as five independently shippable slices.

**Architecture:** One new Layer-2 function, `update_artifact_fields`, composes what the single PATCH assembles in Layer 3 today (workflow guard, attribute-definition validation, `update_X(expected_version=)`, `ArtifactAttributeGateway.write`); bulk uses only that function. The filter DSL is a pure Python API (no HTTP) that compiles `filters`/`sort` JSON against the resolved attribute definition into a `Q` and an `order_by` tuple; REST, MCP and the Dokumentensicht all call it. `rest_api/table_views.py` carries zero ORM lines (architecture ratchet).

**Tech Stack:** Django 6.1 + DRF, drf-spectacular, Postgres 16 (RLS), pytest; React 19 + TypeScript strict, `@tanstack/react-virtual`, React Query, CSS Modules with tokens, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-03-tabellenansicht-design.md` (updated 2026-11-04; sections 3.1 and 4.1 hold the contract). Consumer: `docs/superpowers/specs/2026-11-04-dokumentensicht-neu-design.md` (chapter filters, `bulk-update`). Sort/freeze context: `docs/superpowers/specs/2026-11-04-ordnung-allokation-design.md` and `docs/superpowers/plans/2026-11-04-ordnung-allokation.md` (#1670).

## Global Constraints

- Branch from `origin/main` (never from local `main`), names `feat/tabellenansicht-s1` … `-s5`; **one PR per slice**, order S1 → S2 → S3 → S4 → S5. **S1 must ship alone** and is all the Dokumentensicht needs (#1670 P1/P4 are not prerequisites of S1, only of its freeze/sort tests).
- Git mutations only through the `git` agent. Commit trailers: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01JYx6yrB2hSodcXeSkA5mAq`. Conventional Commits, English, first line ≤ 72 chars. Commit steps below give only the message.
- Run test suites **sequentially** (host has ≈5.8 GiB RAM). Run only the touched modules in the fix loop, never the full backend or Playwright suite. Backend: `cd backend && pytest <path>::<test> -v`. Locally the RLS tests need the DB superuser: run in the dev container with `DJANGO_SETTINGS_MODULE=reqogniloom.settings_test` and `DB_USER`/`DB_PASSWORD` set to the Postgres superuser from `deploy/docker-compose.yml`, otherwise every RLS test errors (environmental, not a regression). Frontend: `cd frontend && npx vitest run <path>`. E2E: `cd e2e && npx playwright test tests/<file>`.
- **Migration numbers are never hard-coded:** use highest existing number in the owning app's `migrations/` + 1 at implementation time (`persistence` is at `0131_interview_session_orphan_cleanup.py` on 814cb998; #1670 and other plans collide). A new tenant table needs its RLS policy in a **separate, following migration** (pattern `persistence/migrations/0129_milestone.py` + `0130_milestone_rls_policy.py`); `persistence/tests/test_rls_coverage.py` fails the build otherwise.
- **Workflow guardrail (spec §2):** a field whose resolved definition has `editable` in `"workflow"`, `"system"`, `"automation"` or `False`, and the structural names `parent_id`, `uid`, `sort_key`, is never written by bulk update, inline edit or any path of this plan: **400 for the whole request**, nothing written, in both modes (no per-item `VALIDATION_ERROR` for these). Enforced in exactly one function, `assert_no_forbidden_fields` (Task 1.1), called once over all items before any write and again inside the seam as backstop. It raises the plain `application.base.ValidationError` (`rest_api/views.py:358` `_EXC_TO_HTTP` is keyed by exact type; a subclass degrades to 500). Defense in depth: `WORKFLOW_OWNED_FALLBACK = {"status", "lifecycle_status"}` is rejected even when the definition is missing.
- `parent_id`, `uid`, `sort_key` (and `id`, `version`, `workspace_id`, `tenant_id`, `artifact_id`) are never bulk-writable (whole-request 400, see above). Adapters use an explicit allowlist per item type, never signature introspection.
- **Write fence:** a write needs the role right **and** the per-artifact item right: `update_artifact_fields` calls `EffectivePermissionService.resolve_effective_permission(..., level="write")` per artifact (item rule `read` → `FORBIDDEN`, `none` → `NOT_FOUND`, identical to a missing id). The single PATCH is not changed (it lacks this check, see O10).
- **Workspace is derived, never sent:** the bulk body has no `workspace_id`. The workspace comes from the item artifacts (`Artifact.workspace_id`, same as `resolve_owning_workspace_id`); all items must belong to **one** workspace (else 400 naming the first foreign item); role fence and MCP scoping use the derived workspace.
- **Atomic means no side effect on rollback:** inside the atomic transaction only DB rows are written (entity, `ArtifactVersion`, audit, outbox: all roll back). Everything else is deferred with `transaction.on_commit` (embedding refresh) or is idempotent over-invalidation (cache `post_save` invalidation, not rolled back, harmless). Task 1.5 pins it.
- **bulk-update contract:** body `{"mode": "atomic"|"partial", "change_reason"?, "items": [{"artifact_id", "expected_version", "fields"}]}`; `mode` defaults to `"atomic"`; `change_reason` is optional and required only when the workspace preset demands it (O3); 1…100 items (101 → 400); `artifact_id` is the `pl_artifact` id; `expected_version` is the `version` of the domain entity as the table row returns it. Failures carry `code` ∈ `VALIDATION_ERROR | NOT_FOUND | FORBIDDEN | CONFLICT` and a `reason` (for freeze the state name).
- **Filter DSL wire format (frozen, public):** `filters := {"<field>": <constraint> | [<constraint>, ...]}` (list = AND), `constraint := {"op": "contains"|"in"|"gte"|"lte"|"eq", "value": ...}`, `sort := [{"field", "dir": "asc"|"desc"}]`. Unknown field, disallowed operator, wrong value type → `ValidationError` naming the field; never silently ignored.
- ADR-01: no ORM in `rest_api/` or `mcp_server/`; `rest_api/tests/test_architecture.py` caps a new `*_views.py` at 0 direct-ORM lines. Every DRF view calls `get_auth_context(request)` first; every service calls `self._set_tenant_context(ctx)` before its first query.
- New PATCH/POST routes declare **no** `If-Match`/412 (contract gate `rest_api/conditional_requests.py`, test `test_conditional_request_contract_1397`; ETag exists only for Requirement, Document, WorkItem, TestCase, Baseline, Workspace, Milestone). Optimistic locking is the per-item `expected_version` in the body.
- Errors use the existing envelope (`build_error_response`); version or freeze conflict is **409 `CONFLICT`**, bad input **400**.
- MCP: every new REST route and tool updates `docs/agent-templates/tool-manifest.json` (rebaseline with `TOOL_MANIFEST_REBASELINE`, see `mcp_server/tests/test_tool_manifest_drift.py`), `mcp_server/tool_registry.py`, OpenAPI tests (`test_openapi_list_params`, `test_schema_completeness_1388`). Write tools are **not** added to `_READ_ONLY_TOOL_NAMES` (`tool_registry.py:458`, fail-closed). Payloads are JSON primitives (`str()` UUIDs, `.isoformat()`). Counts in CLAUDE.md/README only via `agent-meta-manager` at the end of S1, S3.
- Frontend: React 19; **no new inline `style={{`** under `frontend/src/components/` (`ui-ratchet.test.ts:747` `STYLE_BRACE_BASELINE = 3`, asserted `<=` at `:1263`); status cells reuse `components/shared/StatusBadge.tsx` (`STATUS_BADGE_IMPLEMENTATION_BASELINE = 1`, `:1134`); `data-testid` on every interactive element; design tokens only; keyboard path for every pointer action; i18n keys are nested objects in `i18n/locales/{de,en}.json` with DE/EN parity (`src/test/i18n-parity.test.ts`).
- Do not touch files outside the repo (scratch goes to `.tmp/`).

## Review Focus

1. The same `artifact_id` twice in one request, or an `artifact_id` from another tenant/workspace, of an unsupported type (Goal, Document, Interview) or outdated: duplicates → 400; the others → a per-item `NOT_FOUND`/`VALIDATION_ERROR` identical to a missing id (no existence leak across tenants), never a silent skip, never a resurrection. Pinned in Task 1.5.
2. Filter values at the edges: `in` with `[]` matches nothing (not everything); `%`, `_`, quotes in `contains` are literal; `gte` with an unparsable date or a boolean sent as the string `"true"` is 400; more than 200 `in` values is 400. Pinned in Task 1.3.
3. An item with empty `fields` (`{}`), a `null` for a required attribute, or an unknown field name: 400 with the field named; version unchanged. Pinned in Tasks 1.2 and 1.5.
4. A saved view whose stored filter names an attribute that has since been removed: applying it answers 200 with an empty list and a `warnings` entry, never a 500. Pinned in Task 3.2.
5. Item-level rules: a `read` rule blocks a bulk write for that item, a `none` rule hides the item from the table query (count included) **and** blocks the write; an artifact-scoped rule overrides a workspace-wide one (workspace `none` + artifact `read` → visible). A viewer in workspace A who is editor in B cannot write A. Pinned in Tasks 1.2, 1.4, 1.5, 1.6.

## Open items (recorded decisions awaiting the product owner)

- **O1 (decided by the PO, 2026-11-05):** `mode` defaults to `"atomic"`.
- **O2 (decided by the PO, 2026-11-05):** the DSL accepts the pseudo-fields `allocated` and `level` for `Requirement`; they call the same implementation as `?allocated=`/`?level=` (Task 1.3 extracts it, so there is one).
- **O3 (decided by the PO, 2026-11-05):** `change_reason` is **one** optional request-level field with one reason for all items; it is required only when the workspace preset demands it, and a missing reason then rejects the **whole request with 400**. The body carries no `workspace_id` (derived from the items). The Dokumentensicht spec §4.4 needs a one-line note: its client must send `change_reason` when the preset requires it.
- **O4 (decided by the PO, 2026-11-05):** a failed atomic request answers 409 if **all** failures are `CONFLICT`, otherwise 400; the body always has `committed: false` and lists every failing item with code and reason. Partial mode answers 200 even with failures.
- **O5 (decided by the PO, 2026-11-05):** when the workflow freezes a requirement, **all** its fields including content (title, description, acceptance criteria) are not writable, not only position, parent and allocation. This extends the Ordnung-Allokation spec, which froze structure only: **align OA spec §4.5 (and E6) when #1670 P4 is implemented.** The seam calls `_assert_not_frozen` for every write and `editable_fields` returns `[]` for a frozen artifact; the end-to-end freeze tests stay xfail until #1670 P4 (`application/artifact_freeze.py` does not exist yet). Do not reuse `application/base.py:145` `FieldFrozenError` (a `ValidationError` subclass for `Document` fields, 409 `FIELD_FROZEN`; exact-type `_EXC_TO_HTTP` would give 500 unless registered): it is a different thing.
- **O6 (open, verify at implementation):** extended attributes (`kind: "extended"`, stored in `Artifact.custom_fields`) are writable in bulk only through the `custom_fields` object (same as the single PATCH); they are **not** filterable/sortable in S1.
- **O7 (decision of this plan):** new tables use `workspace` as a real FK (like `Milestone`), not a bare `UUIDField`.
- **O8 (not planned):** an MCP tool for the raw table query (agents use `saved_view.apply`); Goal, MainGoal and Document are not in the table registry (lineage versioning / own entity).
- **O9 (decided by the PO, 2026-11-05):** atomic side effects. `update_requirement` gets `refresh_embedding: bool = True` (default as today, so the single PATCH is unchanged); bulk passes `False` and enqueues the refresh with `transaction.on_commit` (Task 1.1/1.5). Same keyword on any other `update_X` that embeds (found by the Task 1.1 Step 1 grep). Cache `post_save` invalidation stays immediate (over-invalidation only). `propagate_suspect_status` swallows its own errors inside the item savepoint (accepted).
- **O10 (not part of this plan):** the finding "the single PATCH checks the role but not the per-artifact `ItemPermission` on write" is being verified first by the PO; a separate issue follows. The single PATCH is not changed here. Pointer only.
- **O11 (decided by the PO, 2026-11-05):** every successful write bumps the entity `version`. The seam always calls the type's `update_X` (empty entity part when only `owner`/`priority`/`custom_fields` are given), like the PATCH views; if an `update_X` does not bump on such a call, the seam adds an explicit `F("version") + 1` update (Task 1.2 Step 1 verifies per service). Gateway-only writes create no `ArtifactVersion` revision row (same as the PATCH).
- **O12 (decided by the PO, 2026-11-05):** no field-level read or write rights; rights are per role and per artifact only. Filter and sort are limited to the definition's `visible` attributes (`audience` is presentational, `schema.py:~208`).
- **O13 (decided by the PO, 2026-11-05):** `editable_fields` (Task 1.8) and the DSL sort key `"tree"` (`sort_key NULLS LAST, created_at, id`, xfail until #1670 P1) stay in Slice 1; REST/MCP exposure of `editable_fields` only when the Dokumentensicht plan needs it (DS B5).
- **O8 (not planned):** an MCP tool for the raw table query (agents use `saved_view.apply`); Goal, MainGoal and Document are not in the table registry (lineage versioning / own entity).

## Verified facts (state 814cb998; re-verify with grep before editing, lines drift)

| Fact | Evidence |
|---|---|
| `Requirement.id` is **not** `Artifact.id`: own `uuid4` pk, `artifact` is a OneToOne | `persistence/models.py:433` (pk), `:1610`, `:1622`; `application/requirement_service.py:413` (`Requirement.objects.create(artifact=artifact, …)` without `id=`). Same for the other seven types. Contract consequence: rows carry both `id` and `artifact_id`; bulk addresses the **artifact id** |
| Artifact → entity accessors | `related_name`: `requirement` (`:1622`), `stakeholder_need` (`:1553`), `architecture_element` (`:1861`), `test_case` (`:2323`), `glossary_term` (`:2670`), `adr` (`:3377`), `risk` (`:3520`), `issue` (`:3815`); `Artifact.artifact_type` strings: `Requirement`, `StakeholderNeed`, `ArchitectureElement`, `TestCase`, `Adr`, `Risk`, `Issue`, `GlossaryTerm` (the `ensure_artifact`/create calls in the eight services) |
| `resolve_owning_workspace_id(entity_key, entity_id)` exists | `application/workspace_lookup.py:164`; `ENTITY_SPECS` `:68` has `requirement, architecture, testcase, need, glossary, adr, risk, issue`; `import_entity_model` `:153` |
| Eight update services and their parameters | `requirement_service.py:747` (`title, description, acceptance_criteria, rationale, source, category, change_reason, type, complexity_fibonacci, verification_method, parent_id, uid, suspect, custom_fields, expected_version`), `stakeholder_need_service.py:288` (`update(ctx, need_id, title, description, category, moscow_priority, change_reason, custom_fields, expected_version)`), `architecture_service.py:222` (`update_architecture_element(arch_el_id, ctx, expected_version, title, description, element_type, parent_id, asil_level, make_or_buy, uid, custom_fields)`), `test_service.py:306` (`update_test_case(test_case_id, ctx, title, description, steps, test_type, custom_fields, change_reason, expected_version, scenario_kind)`), `adr_service.py:260`, `risk_service.py:305`, `issue_service.py:286`, `glossary_service.py:265` (`update(ctx, term_id, term, definition, synonyms, abbreviation, expected_version, custom_fields)`) |
| `expected_version` semantics | `application/optimistic_lock.py:93` `assert_expected_version` (None = skip); `OptimisticLockError` is in `application/base.py:249`, not in `optimistic_lock` |
| What the single PATCH composes (Layer 3) | `RequirementViewSet.partial_update` `rest_api/views.py:2004` → `_validate_patch_payload` (`rest_api/mixins/workflow_transitions.py:~725`, ends with `_validate_attribute_definition(ctx, workspace_id, dict(data), {"__exists__": True})`, which calls `ArtifactAttributeGateway.validate` then `validate_actor_system_fields`, `:~265-335`) → `update_requirement(...)` → `_apply_artifact_system_fields` (`views.py:1069-1103`, `ArtifactAttributeGateway().write(ctx, item_type, entity, AttributeValues(core=values))`) |
| Attribute definition resolve | `AttributeDefinitionService.resolve(ctx, item_type, workspace_id)` `application/attribute_definition_service.py:237` → `{"attributes": [...], "sections", "version", "preset", …}`; `AttributeDefinitionNotFound` when not bootstrapped |
| Attribute types and `editable` values | `attribute_definitions/schema.py:85-99` (`ATTRIBUTE_TYPES` incl. `actor`, `criteria-list`, `widget`), `:175-182` (`EDITABLE_VALUES = {True, False, "workflow", "system", "automation"}`); `audience` is presentation-only (`schema.py:~208`), i.e. the definition has no role-specific field hiding |
| `?allocated=` / `?level=` | `rest_api/views.py:1803-1853` (`@list_schema(..., strict=True, extra=("allocated","level"))`), implemented inline in `application/requirement_service.py:1253-1280` (`TraceLink.unscoped.filter(tenant_id=…, link_type="allocated-to").values_list("source_id")`); MCP `requirement.query` already declares both params (`mcp_server/tools/requirements.py:213-219`). Ordnung-Allokation V9/P0 is therefore delivered for Requirements |
| List-endpoint helpers | `reject_unknown_query_params` `rest_api/query_params.py:191`; `list_schema` `rest_api/views.py:604`; `StandardPagination` `rest_api/serializers.py:615` (25 / max 100); routes before `include(router.urls)` `rest_api/urls.py:1261-1269` |
| Freeze exists only for `Document` | `workflow/precondition_rules.py:859-881` (`is_freeze_transition`), `application/document_service.py:94`; `application/artifact_freeze.py` does **not** exist (Ordnung-Allokation Task 4.1 will create `is_frozen(artifact) -> FreezeInfo | None`) |
| Workflow transition API | `WorkflowFacade.transition(item_id, target_state, change_reason, ctx, *, credential="", item_type="Requirement", workspace_id, expected_version=None)` `application/workflow_facade.py:63-73` |
| Item-level permission | `ItemPermissionService.check_permission` `auth_tenancy/services/item_permission.py:288-318` (an artifact-scoped rule **overrides** the workspace-wide rule; no rule = no opinion; rules are per `user` only, `auth_tenancy/models.py:385`; levels `read|write|none`); `EffectivePermissionService.resolve_effective_permission(*, active_roles, user_id, workspace_id, artifact_id, level)` `application/effective_permission_service.py:129`; the item layer only restricts and only takes part when `has_explicit_rule` |
| Atomic side effects | `ServiceBase._audit` (`application/base.py:329`) and `_emit_event`/outbox (`:452`) write inside the transaction; the event-bus nudge `.delay()` is `on_commit` (`event_bus.py:~498-509`); embedding refresh `requirement_service.py:862` (update) and `:476` (create) runs inside the open transaction; cache invalidation is a `post_save` signal (`cache_invalidation.py:~274`) |
| MCP group | `cross_cutting.py:199-203` docstring claims "read-only, no audit" and is already wrong (`traceability.create_link` writes); audit helpers `write_mcp_audit`/`mcp_audit_handoff` in `mcp_server/tools/base.py:386`, used e.g. `tools/admin.py:218`; `workspace_scope.py` resolves a missing `workspace_id` through `resolve_owning_workspace_id` (`:~496`) |
| Frontend | `apiClient`/`getList` `api/client.ts:435,548`; `api/attribute-definitions.ts` (resolved definition client); field library `components/shared/ArtifactForm/fields/index.ts` (incl. `NumberField`, `CriteriaList`, `ActorPicker`, `ActorDisplay`, `DisplayField`); `ConfirmDialog` props `title, message, confirmLabel, cancelLabel?, onConfirm, onCancel, testId?, isSubmitting?, confirmDisabled?` (`components/shared/ConfirmDialog.tsx:21-43`); modal primitive is `components/shared/Dialog` (`Dialog`, no `ModalDialogBase` component); `useWorkspace()` `context/WorkspaceContext.tsx:335`; `RequirementList` mounted at `RequirementEditors.tsx:682`; `ListToolbar` (`components/shared/ListToolbar.tsx`) is client-side only; `@tanstack/react-virtual` is used in `components/shared/WorkspaceTree/tree-virtualization.tsx` (`RequirementList.tsx` only passes a `virtualize` prop, it has no `useVirtualizer`); e2e specs live in `e2e/tests/`, helpers `e2e/helpers/auth.ts` |

## File Structure

| Area | Files |
|---|---|
| S1 backend | `application/artifact_update_adapters.py` (new: allowlists + guard), `application/artifact_fields_update.py` (new: seam and `editable_fields`), `application/requirement_filters.py` (new: shared allocated/level `Q`), `application/table_filter_dsl.py` (new), `application/table_query_service.py` (new), `application/bulk_edit_service.py` (new), `rest_api/table_views.py` + `rest_api/table_serializers.py` (new), `rest_api/urls.py`, `mcp_server/tools/cross_cutting.py`, `mcp_server/tool_registry.py`, `docs/agent-templates/tool-manifest.json` |
| S2 | `application/bulk_edit_service.py` (`bulk_transition`), `rest_api/table_views.py`, `mcp_server/tools/cross_cutting.py` |
| S3 | `persistence/models.py` (+`UserTableViewState`, `SavedView`), two `persistence/migrations/<next>_*.py`, `application/saved_view_service.py` (new), `rest_api/saved_view_views.py` (new), `mcp_server/tools/saved_view.py` (new), `tool_registry.py` |
| S4 | `frontend/src/api/table-views.ts`, `frontend/src/components/shared/ArtifactTable/*`, `RequirementEditors.tsx`, `i18n/locales/{de,en}.json` |
| S5 | `e2e/tests/table-view-workflow-guardrail.spec.ts` |

Tests sit next to the code (`application/tests/`, `rest_api/tests/`, `mcp_server/tests/`, `persistence/tests/`, `frontend/src/test/`).

---

# Slice 1 — Backend core: update seam, filter DSL, table query, bulk-update

### Task 1.1: Writable-field adapters and the workflow guard

**Files:**
- Create: `backend/application/artifact_update_adapters.py`
- Modify: `backend/application/requirement_service.py:~862` (`update_requirement(..., refresh_embedding: bool = True)`, default keeps the single PATCH identical) and any other `update_X` that embeds (Step 1)
- Test: `backend/application/tests/test_artifact_update_adapters.py`, `backend/application/tests/test_requirement_service.py` (two new tests)

**Interfaces:**
- Produces:
  - `NEVER_BULK_WRITABLE: frozenset[str]` = `{"parent_id","uid","sort_key","id","version","artifact_id","workspace_id","tenant_id"}`; `WORKFLOW_OWNED_FALLBACK: frozenset[str]` = `{"status","lifecycle_status"}`.
  - `@dataclass(frozen=True) class UpdateAdapter: item_type: str; entity_key: str; accessor: str; writable_fields: frozenset[str]; update: Callable[[AuthContext, UUID, dict[str, Any], int | None, str | None], tuple[UUID, int]]` (takes `ctx, entity_id, entity_fields, expected_version, change_reason`; normalises the differing return types, ORM entity or DTO, to `(entity_id, new_version)`; passes `refresh_embedding=False` where the service has the keyword and registers `transaction.on_commit` to run the refresh once after the outermost commit).
  - `ARTIFACT_UPDATE_ADAPTERS: dict[str, UpdateAdapter]` with exactly the eight keys of the Verified-facts table. Allowlists: Requirement `title, description, acceptance_criteria, rationale, source, category, type, complexity_fibonacci, verification_method`; StakeholderNeed `title, description, category, moscow_priority`; ArchitectureElement `title, description, element_type, asil_level, make_or_buy`; TestCase `title, description, steps, test_type, scenario_kind`; Adr `title, description, context, decision, consequences`; Risk `title, description, probability, impact, category, mitigation_strategy, detection`; Issue `title, description, severity, category, due_date, tags`; GlossaryTerm `term, definition, synonyms, abbreviation`.
  - `GATEWAY_FIELDS: frozenset[str]` = `set(transport_field_names()) | {"custom_fields"}` (owner, reporter, priority, stakeholder, ADR-006 carrier fields, extended values); these go through `ArtifactAttributeGateway.write`, not through `update_X`.
  - `classify_fields(item_type: str, fields: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]` returning `(entity_fields, gateway_fields)`; any other (unknown) name raises `ValidationError("Unknown field '<name>'")` (a per-item error in bulk); `{}` raises `ValidationError("No fields given")`.
  - `assert_no_forbidden_fields(attributes: Sequence[Mapping[str, Any]], fields: Mapping[str, Any]) -> None`: raises plain `ValidationError` naming the field for any name in `NEVER_BULK_WRITABLE` or `WORKFLOW_OWNED_FALLBACK`, or whose attribute has `editable` not `True`.

- [ ] **Step 1: Verify the signatures have not drifted.** Run `cd backend && grep -n "    def update_requirement\|    def update(\|    def update_architecture_element\|    def update_test_case\|    def update_adr\|    def update_risk\|    def update_issue" application/{requirement,stakeholder_need,architecture,test,adr,risk,issue,glossary}_service.py`. If a parameter was added (for example `sort_key` by #1670), do **not** add it to an allowlist; if one was renamed, adjust the adapter and keep the test below green. Then run `grep -n "_generate_and_store_embedding\|embedding" backend/application/{requirement,stakeholder_need,architecture,test,adr,risk,issue,glossary}_service.py` and list every **update** path that calls an LLM/embedding inside its transaction (known: `requirement_service.py:862`); each gets the `refresh_embedding` keyword.
- [ ] **Step 2: Write the failing tests** in `test_artifact_update_adapters.py`: `test_registry_covers_the_eight_types` (keys equal the eight item types; each `entity_key` is in `workspace_lookup.ENTITY_SPECS`); `test_no_allowlist_contains_structural_fields` (`allowlist & NEVER_BULK_WRITABLE == set()` for every adapter); `test_allowlist_is_subset_of_update_signature` (uses `inspect.signature` **in the test only**: every allowlisted name is a parameter of the update method); `test_classify_splits_entity_and_gateway_fields` (`{"title","owner"}` → `({"title":…}, {"owner":…})`); `test_classify_rejects_unknown_and_empty_fields`; `test_guard_rejects_parent_id_uid_sort_key` (each name, message contains the field); `test_update_requirement_default_still_refreshes_embedding` and `test_update_requirement_refresh_embedding_false_skips_it` (in `test_requirement_service.py`, patch `_generate_and_store_embedding`); `test_adapter_update_returns_entity_id_and_version_for_orm_and_dto_services` (Requirement and StakeholderNeed); `test_guard_rejects_workflow_editable` (attributes with `status` `editable="workflow"`, fields `{"status":"x"}` → `ValidationError` naming `status`); `test_guard_rejects_system_automation_and_false` (three attributes, each rejected); `test_guard_fallback_without_definition` (`attributes=[]`, `{"status":"x"}` and `{"lifecycle_status":"x"}` rejected); `test_guard_raises_plain_validation_error` (`type(exc.value) is ValidationError`); `test_guard_accepts_editable_true` (`{"title":"x"}` passes).
- [ ] **Step 3: Run** `cd backend && pytest application/tests/test_artifact_update_adapters.py -v`. Expected: FAIL (`ModuleNotFoundError`).
- [ ] **Step 4: Implement** the module. `update` callables adapt the differing keyword names of the eight services (note `StakeholderNeedService.update` and `GlossaryService.update` take `ctx` first and return DTOs; `update_architecture_element` takes `expected_version` as the third positional parameter), always pass `expected_version=` through, and pass `change_reason` only where the service accepts it. The guard rejects a field when its attribute has `editable` not `True`, or when it is in `WORKFLOW_OWNED_FALLBACK`; the message names the field and says it can only change through a workflow transition (workflow) or is server-owned/read-only (others).
- [ ] **Step 5: Run** the file again. Expected: PASS.
- [ ] **Step 6: Commit** `feat: add writable-field adapters and workflow guard for bulk edit`.

### Task 1.2: Seam `update_artifact_fields`

**Files:**
- Create: `backend/application/artifact_fields_update.py`
- Test: `backend/application/tests/test_artifact_fields_update.py`, `backend/rest_api/tests/test_update_seam_parity.py`

**Interfaces:**
- Consumes: Task 1.1 (`ARTIFACT_UPDATE_ADAPTERS`, `classify_fields`, `assert_no_forbidden_fields`).
- Produces:
  - `@dataclass(frozen=True) class FieldUpdateResult: artifact_id: UUID; entity_id: UUID; item_type: str; version: int`.
  - `class ArtifactFrozenError(Exception)` with attribute `state_name: str` (if Ordnung-Allokation Task 4.2 already added a frozen-error type for artifacts, grep `class .*Frozen.*Error` in `backend/application` and reuse **that**; `application/base.py:145` `FieldFrozenError` is a different, Document-specific class and must not be reused).
  - `update_artifact_fields(ctx: AuthContext, item_type: str, artifact_id: UUID, fields: Mapping[str, Any], expected_version: int | None, *, change_reason: str | None = None) -> FieldUpdateResult`. `artifact_id` is the `pl_artifact` id; `item_type` must equal `Artifact.artifact_type`, otherwise `ValidationError`.
  - Order of work (all in one `transaction.atomic()`): `_set_tenant_context`; `ServiceBase._assert_write_permission(ctx)` (role); load the tenant-scoped `Artifact` (`NotFoundError` if absent, `ValidationError("…outdated")` if `lifecycle_status` marks it outdated); **item-level write right:** `EffectivePermissionService().resolve_effective_permission(active_roles=ctx.active_roles, user_id=ctx.user_id, workspace_id=artifact.workspace_id, artifact_id=artifact.id, level="write")`; not allowed and effective `level == "read"` → `PermissionDeniedError`, `level == "deny"` → `NotFoundError` (the role check above already passed, so a deny can only come from an item rule; the message equals the missing-id message); resolve attributes via `AttributeDefinitionService().resolve` (`AttributeDefinitionNotFound` → `[]`, the fallback guard still applies); `assert_no_forbidden_fields`; `classify_fields`; `_assert_not_frozen(artifact)` (lazy `from application.artifact_freeze import is_frozen`, `ImportError` → no-op; a `FreezeInfo` → `ArtifactFrozenError(state_name)`); `ArtifactAttributeGateway().validate(ctx, item_type, workspace_id, {**entity_fields, **gateway_fields}, {"__exists__": True})` then `validate_actor_system_fields(ctx, item_type, workspace_id, changed_fields)` (a `FieldValidationError` is re-raised as `ValidationError` with message `"<field>: <messages>; …"`, like `_validate_attribute_definition`); **always** `adapter.update(ctx, entity_id, entity_fields, expected_version, change_reason)` (also with an empty `entity_fields`, exactly like the PATCH views, so any successful write bumps the entity `version` and a replayed `expected_version` conflicts, O11); then `ArtifactAttributeGateway().write(ctx, item_type, entity, AttributeValues(core=…, extended=custom_fields))` for the gateway part; return the new version.
  - `editable_fields` lives in this module too: see Task 1.8.

- [ ] **Step 1: Verify the composition and the version behaviour.** Read `rest_api/views.py:2004-2160` (Requirement) and `:1069-1103`, and `rest_api/mixins/workflow_transitions.py:~264-335, ~725-840`. Confirm the call order above. If the PATCH now does an extra step (a `level` guard, `set_manual_level`), decide per step: structural (level, parent) stays out of the seam; content joins the seam. Then check for each of the eight `update_X` that a call with all content parameters `None` still bumps `version` (read the method). If one does not bump, the seam adds `Model.objects.filter(pk=entity_id).update(version=F("version") + 1)` for it and O11 is amended. Check the `EffectivePermission` field names with `sed -n 70,100p application/effective_permission_service.py` (`level` is one of `deny|read|write`).
- [ ] **Step 2: Write the failing tests** (`test_artifact_fields_update.py`, real DB rows via the existing fixtures): `test_updates_title_and_bumps_version_once`; `test_expected_version_mismatch_raises_optimistic_lock_error_and_writes_nothing`; `test_none_expected_version_skips_the_lock`; `test_gateway_only_change_bumps_entity_version` (only `priority`: version +1, `FieldUpdateResult.version` equals the stored version); `test_replaying_same_expected_version_after_gateway_only_change_conflicts` (second call with the old version raises `OptimisticLockError`); `test_owner_priority_written_via_gateway`; `test_custom_fields_merged_not_replaced`; `test_workflow_field_and_parent_id_rejected_before_any_write` (`ValidationError`, version unchanged); `test_unknown_field_rejected`; `test_definition_violation_rejected`; `test_null_for_required_attribute_rejected`; `test_unresolvable_actor_rejected`; `test_item_type_mismatch_rejected`; `test_other_tenant_artifact_not_found`; `test_outdated_artifact_rejected`; `test_viewer_role_permission_denied`; `test_item_rule_read_blocks_write` (`PermissionDeniedError`, nothing written); `test_item_rule_none_blocks_write_as_not_found` (same message as a missing id); `test_workspace_none_rule_with_artifact_write_rule_allows_write` (artifact-scoped wins); `test_frozen_artifact_raises_artifact_frozen_error` (stub `application.artifact_freeze` via `sys.modules` returning `state_name="Freigegeben"`; no write); the real freeze is `test_requirement_freeze_real_workflow` marked `xfail(reason="needs #1670 P4: application/artifact_freeze.py is_frozen for Requirement/ArchitectureElement; freeze covers content fields too (O5)", strict=False)`.
- [ ] **Step 3: Write the parity regression** `rest_api/tests/test_update_seam_parity.py::test_single_patch_and_seam_store_the_same_result`: two identical Requirements; PATCH one through the API client with `{"title": "T2", "description": "D2", "priority": "high"}`, call the seam on the other; assert equal `title`, `description`, `Artifact.priority`, `version == 2` on both, equal `ArtifactVersion` count. Add `test_priority_only_patch_and_seam_agree_on_version` and `test_single_patch_still_rejects_status_change`. The single PATCH is **not modified**.
- [ ] **Step 4: Run** `cd backend && pytest application/tests/test_artifact_fields_update.py rest_api/tests/test_update_seam_parity.py -v`. Expected: FAIL.
- [ ] **Step 5: Implement** the function as specified. Reuse `ArtifactAttributeGateway`/`AttributeValues`; do not re-implement actor resolution.
- [ ] **Step 6: Run** both files. Expected: PASS (the xfail test is reported as xfailed).
- [ ] **Step 7: Commit** `feat: add update_artifact_fields seam composing single-PATCH steps`.

### Task 1.3: Filter DSL (pure Python API)

**Files:**
- Create: `backend/application/requirement_filters.py`, `backend/application/table_filter_dsl.py`
- Modify: `backend/application/requirement_service.py:1253-1280` (`list_requirements` uses the extracted helper)
- Test: `backend/application/tests/test_table_filter_dsl.py`, `backend/application/tests/test_requirement_filters.py`

**Interfaces:**
- Produces in `requirement_filters.py`: `allocation_level_q(*, tenant_id: UUID, allocated: bool | None, level: int | None) -> Q` — exactly today's semantics (`level=` equality; `allocated` = `Q(artifact_id__in=<allocated-to source ids>)`, negated for `False`). `list_requirements` calls `qs.filter(allocation_level_q(...))`; behaviour unchanged.
- Produces in `table_filter_dsl.py`:
  - `FILTER_OPERATORS_BY_TYPE: dict[str, frozenset[str]]` = text/textarea `{contains}`; enum/multi-enum `{in}`; number/date `{gte,lte}`; boolean `{eq}`; reference/user/actor `{in}`. `criteria-list` and `widget` are absent (not filterable, sortable only if a plain column).
  - `PSEUDO_FIELDS: dict[str, dict[str, Any]]` for `item_type == "Requirement"` only: `allocated` (type boolean, ops `{eq}`), `level` (type number, ops `{eq}`, value int 1..4, same bounds as `parse_int_param(minimum=1, maximum=4)`).
  - `MAX_IN_VALUES = 200`, `MAX_SORT_TERMS = 5`, `MAX_CONSTRAINTS_PER_FIELD = 5`.
  - `allowed_operators(attribute: Mapping[str, Any]) -> frozenset[str]` (an attribute with `editable == "workflow"`, i.e. status, always gets `{in}`: filtering is a read).
  - `compile_filters(item_type: str, attributes: Sequence[Mapping[str, Any]], filters: Mapping[str, Any] | None, *, tenant_id: UUID, workspace_id: UUID) -> Q`
  - `compile_sort(item_type: str, attributes: Sequence[Mapping[str, Any]], sort: Sequence[Mapping[str, Any]] | None) -> tuple[str | OrderBy, ...]`. Sortable: concrete entity columns and `priority`. **Not sortable** (`ValidationError` naming the field): `status` (state lives in a separate table), actor fields (`owner`, `reporter`: UUID order is meaningless), pseudo-fields `allocated`/`level`, `criteria-list`, `widget`, extended and carrier fields. The symbolic key `{"field": "tree", "dir": "asc"}` (sole or first term; `desc` rejected) expands to `sort_key NULLS LAST, created_at, id` via `OrderBy` expressions; until #1670 P1 it raises `ValidationError("tree order needs sort_key")` (consumer: Dokumentensicht V3).
  - Both raise `application.base.ValidationError` and need no HTTP, no request, no ctx object: the caller passes the attribute list it is allowed to expose.
- Field → ORM mapping (private helper `_orm_path(model, attribute)`): a concrete column of the entity model → its name (names containing `__` or `.` are rejected: no traversal); `owner`/`reporter` (type actor) → `artifact__<name>_id` with `in`; `priority` → `artifact__priority`; `status` (`editable == "workflow"`) → `Q(id__in=<ids>)` where `<ids>` come from `workflow.state_reader.current_states` over the workspace's entity ids, with the `initial_state` fallback for rows without a `WorkflowItemState`, copied from `requirement_service.py:1225-1245` (shortcut: materialises the workspace's ids, fine for tens of thousands of rows; upgrade = subquery); any other attribute (carrier-backed multi-actor fields such as `Adr.deciders`, `kind == "extended"`) → `ValidationError("Field '<name>' is not filterable yet")`. A multi-enum column that is an `ArrayField` uses `overlap` instead of `in`.

- [ ] **Step 1: Verify** the unknowns with commands and note the result in the commit message body: `grep -n "owner = \|reporter = \|priority = " backend/persistence/models.py` inside `class Artifact` (expect FKs `owner`/`reporter` to Actor and a `priority` CharField; if `owner`/`reporter` are not plain FKs, map them as non-filterable); `grep -n "def current_states\|def initial_state\|def item_ids_in_state" backend/workflow/state_reader.py` (reuse what exists); `grep -n "level\b" backend/persistence/models.py | head` inside `Requirement` (after Ordnung-Allokation P2 the integer `level` stays as an alias, so `level` equality keeps working; if `level` was removed, make the pseudo-field filter on `tier_key` and update this plan).
- [ ] **Step 2: Write the failing tests.** `test_requirement_filters.py`: `test_allocated_true_false_and_level_match_list_requirements` (same ids as `list_requirements(allocated=…, level=…)`); `test_list_requirements_behaviour_unchanged` (run the existing `application/tests/test_requirement_service.py -k "allocated or level"` selection). `test_table_filter_dsl.py`: `test_operators_derived_from_type` (all rows of the table above, including `actor` → `{in}`, `criteria-list` → empty); `test_status_is_filterable_with_in_only`; `test_text_contains_builds_icontains`; `test_range_as_list_of_constraints_is_anded` (date `gte` + `lte`); `test_single_object_is_shorthand_for_one_element_list`; `test_unknown_field_names_the_field`; `test_disallowed_operator_names_operator_and_allowed_set`; `test_orm_traversal_name_rejected` (`artifact__workspace__tenant`); `test_extended_and_carrier_fields_rejected`; `test_in_empty_list_matches_nothing` (executed against the DB: zero rows); `test_contains_treats_percent_underscore_quote_literally` (a title `100%_"x"` is found by `contains "%_\""`, a title `abc` is not); `test_invalid_date_and_stringly_boolean_are_400`; `test_oversized_in_list_is_400` (201 values); `test_too_many_constraints_per_field_is_400`; `test_actor_in_filters_owner` (two requirements with different owners; DB result); `test_status_in_returns_matching_states_including_initial_fallback`; `test_pseudo_fields_allocated_and_level_only_for_requirement` (for `Adr` → unknown field); `test_pseudo_field_results_equal_requirement_list_filters`; `test_compile_sort_orders_multi_term` (`("-category","title")`); `test_compile_sort_rejects_bad_direction_unknown_field_and_more_than_5_terms`; `test_compile_sort_rejects_status_actor_pseudo_and_criteria_list`; `test_sort_tree_orders_by_sort_key_then_created_at_then_id` (`xfail(reason="needs #1670 P1 sort_key")`); `test_sort_tree_rejects_desc`; `test_dsl_works_without_http` (import and call with no Django request object; `ValidationError` is `application.base.ValidationError`).
- [ ] **Step 3: Run** `cd backend && pytest application/tests/test_requirement_filters.py application/tests/test_table_filter_dsl.py -v`. Expected: FAIL (`ModuleNotFoundError`).
- [ ] **Step 4: Implement** both modules and switch `list_requirements` to the helper. Wire format and limits exactly as in Global Constraints; no operator outside the table is accepted.
- [ ] **Step 5: Run** the two new files plus `pytest application/tests/test_requirement_service.py -q`. Expected: PASS.
- [ ] **Step 6: Commit** `feat: add type-aware table filter DSL and share allocation filter`.

### Task 1.4: Table query service

**Files:**
- Create: `backend/application/table_query_service.py`
- Test: `backend/application/tests/test_table_query_service.py`

**Interfaces:**
- Consumes: `compile_filters`, `compile_sort` (1.3), `ARTIFACT_UPDATE_ADAPTERS` (1.1), `workspace_lookup.ENTITY_SPECS`/`import_entity_model`.
- Produces:
  - `TABLE_ITEM_TYPES: dict[str, str]` = `{"Requirement":"requirement","StakeholderNeed":"need","ArchitectureElement":"architecture","TestCase":"testcase","Adr":"adr","Risk":"risk","Issue":"issue","GlossaryTerm":"glossary"}`.
  - `DEFAULT_ORDER: tuple[str, ...] = ("created_at", "id")` (matches `list_requirements`; after #1670 P1 the single place to change to `("sort_key" NULLS LAST, "created_at", "id")`, test `test_default_order_follows_sort_key` is xfail until then).
  - `class TableQueryService(ServiceBase)`:
    - `columns(self, ctx: AuthContext, workspace_id: UUID, item_type: str) -> list[dict[str, Any]]` — the resolved attributes with `visible` true (the same list the DSL validates against; there is no role-specific field hiding, O12).
    - `query(self, ctx: AuthContext, workspace_id: UUID, item_type: str, filters: Mapping[str, Any] | None = None, sort: Sequence[Mapping[str, Any]] | None = None, *, include_deleted: bool = False) -> QuerySet` — **the Python API the Dokumentensicht calls**; lazy queryset of entity rows, `select_related("artifact","artifact__owner","artifact__reporter")`, tenant/workspace-scoped, outdated excluded unless `include_deleted`.
    - `serialize_rows(self, ctx: AuthContext, rows: Sequence[Any], attributes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]` with row shape `{"id": str, "artifact_id": str, "item_type": str, "version": int, "values": {<attribute>: <json value>}, "locked": {"state": str} | None}`; `values` come from entity columns, `artifact_system_fields(entity)`, `Artifact.custom_fields`, and one batched `state_reader.current_states` call for `status`; `locked` is `None` until the freeze mechanism exists (lazy `is_frozen`, as in 1.2).
    - `jsonable(value) -> Any` (UUID/datetime/Decimal → str/ISO; lists and dicts recursively).
  - Rights: `PermissionDeniedError` unless `AuthorizationService().decide_access(ctx.active_roles, Operation.READ).allow`; rows hidden by an explicit item-level `none` rule are excluded **inside the queryset** (so `count` does not leak). `Goal`, `MainGoal`, `Document` are not in the registry; an unsupported `item_type` → `ValidationError`.

- [ ] **Step 1: Verify the item-level exclusion approach.** Run `grep -n "effective_permission\|ItemPermission" backend/application/search_service.py backend/application/services.py`. Outcome A: a reusable "readable artifact ids" helper exists → use it. Outcome B (expected: `search_service.py` drops unreadable hits post-query, no queryset helper) → implement `_apply_item_read_rules(qs, ctx, workspace_id) -> QuerySet` with the real precedence of `check_permission` (`item_permission.py:288-318`: an artifact-scoped rule overrides the workspace-wide rule; only an explicit rule has an opinion; rules are per `user`, there is no role-scoped rule): `rules = ItemPermission.objects.filter(user_id=ctx.user_id, workspace_id=workspace_id)`; `ws_none = rules.filter(artifact__isnull=True, permission_level="none").exists()`; `denied = rules.filter(artifact__isnull=False, permission_level="none").values("artifact_id")`; `kept = rules.filter(artifact__isnull=False).exclude(permission_level="none").values("artifact_id")`; result `qs.filter(artifact_id__in=kept)` if `ws_none` else `qs.exclude(artifact_id__in=denied)`. A `read`/`write` rule never hides. Write the chosen outcome in the module docstring. Also run `grep -rn "audience" backend --include=*.py | grep -v tests | head` to confirm it stays presentational (no role-specific field hiding); if a role-based hiding exists, `columns()` must apply it.
- [ ] **Step 2: Write the failing tests:** `test_columns_lists_visible_attributes_only`; `test_query_scopes_to_workspace_and_tenant` (second tenant's rows never appear); `test_query_applies_filters_and_sort` (title contains + `-category`); `test_query_excludes_outdated_by_default_and_includes_on_request`; `test_unsupported_item_type_rejected` (`Goal`, `Document`); `test_role_without_read_is_permission_denied`; `test_item_level_none_rule_hides_row_and_count` (queryset `.count()` excludes it); `test_workspace_none_hides_everything_without_artifact_rule`; `test_workspace_none_plus_artifact_read_rule_keeps_that_artifact_visible`; `test_artifact_none_plus_workspace_write_rule_hides_it`; `test_other_users_rules_are_ignored`; `test_read_level_rule_does_not_hide`; `test_serialize_rows_shape_and_json_primitives` (`json.dumps` succeeds; keys exactly `id, artifact_id, item_type, version, values, locked`); `test_artifact_id_differs_from_row_id_and_version_is_entity_version`; `test_status_value_batched_in_one_query` (`django_assert_max_num_queries` constant for 5 and 50 rows); `test_stale_unknown_filter_field_raises_validation_error`; `test_default_order_follows_sort_key` (`xfail(reason="needs #1670 P1 sort_key")`).
- [ ] **Step 3: Run** `cd backend && pytest application/tests/test_table_query_service.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement** the service as specified.
- [ ] **Step 5: Run** the file. Expected: PASS (one xfailed).
- [ ] **Step 6: Commit** `feat: add table query service over the filter DSL`.

### Task 1.5: `BulkEditService.bulk_update`

**Files:**
- Create: `backend/application/bulk_edit_service.py`
- Test: `backend/application/tests/test_bulk_edit_service.py`

**Interfaces:**
- Consumes: `update_artifact_fields`, `FieldUpdateResult`, `ArtifactFrozenError` (1.2); `assert_no_forbidden_fields` (1.1).
- Produces:
  - `MAX_BULK_ITEMS = 100`; `BULK_CODES = ("VALIDATION_ERROR","NOT_FOUND","FORBIDDEN","CONFLICT")`.
  - `@dataclass(frozen=True) class BulkFailure: index: int; artifact_id: UUID | None; code: str; reason: str`.
  - `@dataclass(frozen=True) class BulkUpdateResult: mode: str; committed: bool; updated: list[FieldUpdateResult]; failed: list[BulkFailure]`.
  - `class BulkEditService(ServiceBase)`:
    - `derive_workspace_id(self, ctx: AuthContext, items: Sequence[Mapping[str, Any]]) -> UUID | None` — one query `Artifact.objects.filter(id__in=…).values_list("id","workspace_id")`; returns the workspace of the first resolvable item, `None` if none resolves; raises `ValidationError` naming the first item whose workspace differs. The REST view/MCP handler calls it to obtain the role context of the **derived** workspace (Task 1.6 Step 1) before `bulk_update`.
    - `bulk_update(self, ctx: AuthContext, items: Sequence[Mapping[str, Any]], *, mode: str = "atomic", change_reason: str | None = None) -> BulkUpdateResult`.
  - Request-level errors raise `ValidationError` (→ 400, nothing written): `items` not a list, empty, more than 100, unknown `mode`, an item without `artifact_id` (UUID) / `expected_version` (int ≥ 1) / `fields` (object), a duplicate `artifact_id`, items spanning two workspaces, a missing `change_reason` when the workspace preset demands one (one reason for all items), and **any item whose fields contain a forbidden field** (workflow-owned, `parent_id`, `uid`, `sort_key`): `assert_no_forbidden_fields` runs over all items before any write (attributes of each resolvable artifact's type; the fallback set for unresolvable ones). The seam repeats the check as backstop.
  - Per-item failure mapping: `ValidationError`/`FieldValidationError` (unknown field, definition violation, empty fields, outdated, per-item content errors) → `VALIDATION_ERROR`; `NotFoundError` (missing, foreign tenant, other workspace, item rule `none`) → `NOT_FOUND` with identical text; `PermissionDeniedError` (item rule `read`) → `FORBIDDEN`; `OptimisticLockError` → `CONFLICT` (`reason="version"`); `ArtifactFrozenError` → `CONFLICT` (`reason=<state_name>`).
  - `atomic`: one outer `transaction.atomic()`, every item in its own savepoint; after the loop, if `failed` is non-empty the outer transaction is rolled back (`transaction.set_rollback(True)`), `committed=False`, `updated=[]`. `partial`: each item commits on its own; `committed=True` iff at least one item was written.

- [ ] **Step 1: Decide and verify the rollback behaviour (O9).** Verified at plan time: `_audit` (`base.py:329`) and `_emit_event`/outbox (`:452`) write inside the transaction and roll back; the event-bus `.delay()` nudge is `on_commit`; `update_X` are `@atomic_transaction` (savepoints nest). Not safe inside the transaction: the embedding refresh (`requirement_service.py:862`, LLM call; it would also hold row locks over up to 100 calls) → the adapters (Task 1.1) pass `refresh_embedding=False` and register one `transaction.on_commit` refresh per written item whose title/description changed. Cache `post_save` invalidation (`cache_invalidation.py:~274`) is immediate and not rolled back: harmless over-invalidation, documented in the class docstring. Run `grep -rn "\.delay(\|apply_async(" backend/application/*_service.py | head` and check that none of the eight update paths enqueues a Celery task outside `on_commit`; if one does, list it in the docstring and defer it the same way.
- [ ] **Step 2: Write the failing tests** (real rows; use `django_capture_on_commit_callbacks`): `test_atomic_all_valid_commits_and_returns_new_versions`; `test_atomic_one_invalid_of_five_writes_nothing_and_lists_every_failure` (items 2 and 4 invalid → entity versions and titles unchanged, `committed is False`, `failed` has exactly indices 1 and 3 with `code` and `reason`); `test_atomic_rollback_removes_audit_version_and_outbox_rows` (counts of `ArtifactVersion`, audit log rows and outbox rows before == after); `test_atomic_failure_fires_no_embedding_or_other_commit_side_effect` (patch `RequirementService._generate_and_store_embedding`: not called; captured on-commit callbacks list empty); `test_success_refreshes_embedding_once_per_changed_item_after_commit`; `test_atomic_stale_expected_version_is_conflict_and_rolls_back_the_valid_items`; `test_partial_writes_valid_items_and_reports_failures` (3 valid, 2 invalid → 3 `updated`, 2 `failed`); `test_default_mode_is_atomic`; `test_101_items_is_validation_error_and_100_is_accepted`; `test_forbidden_field_in_any_item_rejects_the_whole_request_in_both_modes` (parametrised over modes and over `status`, `parent_id`, `uid`, `sort_key`; item 5 of 5 carries it; zero writes); `test_system_automation_false_fields_rejected`; `test_duplicate_artifact_id_is_validation_error`; `test_items_from_two_workspaces_is_400_naming_the_first_foreign_item`; `test_foreign_tenant_and_other_workspace_artifact_report_not_found_like_missing` (same `reason`); `test_unsupported_type_goal_document_reports_validation_error`; `test_outdated_artifact_reports_validation_error_not_resurrected`; `test_empty_fields_item_is_validation_error`; `test_null_for_required_attribute_reports_validation_error`; `test_unknown_mode_rejected`; `test_mixed_item_types_in_one_request`; `test_change_reason_is_forwarded_to_every_item`; `test_missing_change_reason_rejects_whole_request_when_preset_requires_it` (Extended preset, zero writes, both modes); `test_item_rule_read_blocks_only_that_item` (partial: others written, failure `FORBIDDEN`; atomic: nothing written); `test_item_rule_none_reports_not_found_and_writes_nothing`; `test_per_item_uses_the_seam` (patch `application.bulk_edit_service.update_artifact_fields`: once per item with `expected_version`); `test_freeze_conflict_names_the_state` (stub `is_frozen`: `code="CONFLICT"`, `reason="Freigegeben"`); `test_requirement_freeze_blocks_content_fields_end_to_end` (title, description, acceptance criteria all `CONFLICT` with the state name) marked `xfail(reason="needs #1670 P4 (O5: freeze covers content fields)", strict=False)`.
- [ ] **Step 3: Run** `cd backend && pytest application/tests/test_bulk_edit_service.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement** `derive_workspace_id` and `bulk_update` as specified. Resolve all artifacts in one query, group by `artifact_type`, resolve each type's attributes once.
- [ ] **Step 5: Run** the file. Expected: PASS (one xfailed).
- [ ] **Step 6: Commit** `feat: add atomic and partial bulk update through the update seam`.

### Task 1.6: REST — `PATCH artifacts/bulk-update/` and `GET artifacts/table/`

**Files:**
- Create: `backend/rest_api/table_views.py`, `backend/rest_api/table_serializers.py`
- Modify: `backend/rest_api/urls.py` (two `path(...)` entries **before** `path("", include(router.urls))` at `:1269`; the comment at `:1261` explains why)
- Test: `backend/rest_api/tests/test_table_views.py`

**Interfaces:**
- Consumes: `BulkEditService.derive_workspace_id/bulk_update` (1.5), `TableQueryService` (1.4), `rest_api.views._service_error_response`, `rest_api.query_params.parse_workspace_id`/`reject_unknown_query_params`, `rest_api.serializers.StandardPagination`, `rest_api.auth_enforcer.get_auth_context`.
- Produces:
  - `BulkUpdateView(APIView)` → `PATCH /api/v1/artifacts/bulk-update/`, body `{"mode"?, "change_reason"?, "items": [...]}` (no `workspace_id`); success and partial body `{"committed": bool, "mode": str, "updated": [{"artifact_id","id","item_type","version"}], "failed": [{"index","artifact_id","code","reason"}]}` with HTTP 200; atomic with failures → HTTP 409 if all codes are `CONFLICT` else 400, body = `build_error_response(...)` with `details=failed` plus top-level `"committed": false`, `"failed"`; request-level `ValidationError` → 400.
  - `TableQueryView(APIView)` → `GET /api/v1/artifacts/table/?workspace_id=&item_type=&filters=<JSON>&sort=<JSON>&include_deleted=&page=&page_size=`; paginated with `StandardPagination` (default 25, max 100), results are `serialize_rows` output. Unknown query parameter → 400 via `reject_unknown_query_params`; invalid JSON in `filters`/`sort` → 400 naming the parameter; helper `parse_json_param(raw: str | None, name: str, lang: str) -> Any`.
  - Serializers in `table_serializers.py`: `BulkUpdateRequestSerializer`, `BulkUpdateResponseSerializer`, `TableRowSerializer`, declared in `@extend_schema` so OpenAPI shows `filters`/`sort` as string parameters with the wire format in the description.

- [ ] **Step 1: Decide how the role fence sees the derived workspace.** Read `backend/rest_api/auth_enforcer.py` (`get_auth_context`, `:185`) and find how roles are bound to a workspace for a request (query `workspace_id`, header, or token). The bulk view first calls `BulkEditService().derive_workspace_id(ctx, items)` (service call, no ORM in the view). Outcome A: `get_auth_context` accepts or derives a workspace → build the context for the derived workspace and use it for `bulk_update`. Outcome B: roles are workspace-agnostic in `ctx` → the service checks the caller's role **in the derived workspace** (find the lookup: `grep -rn "UserRole" backend/auth_tenancy/services | head`) and raises `PermissionDeniedError` before any write; add that check to `bulk_update`. Write the chosen outcome in the view docstring. A derived workspace of a foreign tenant cannot occur (the artifact lookup is tenant-scoped; such ids are `NOT_FOUND` items). Run `grep -n "classif\|SERIALIZER" backend/rest_api/tests/test_schema_completeness_1388.py backend/rest_api/tests/test_openapi_list_params.py | head` to learn which registry the new serializers must join (commit `eba34288`); do that in Step 5.
- [ ] **Step 2: Write the failing tests** (`APIClient`, two roles, two tenants, two workspaces): `test_bulk_update_atomic_success_200`; `test_bulk_update_atomic_failure_is_400_and_nothing_written_and_lists_every_failure`; `test_bulk_update_all_conflict_is_409`; `test_bulk_update_partial_returns_200_with_failed`; `test_forbidden_field_in_payload_is_400_for_whole_request_nothing_written` (`status`, `parent_id`); `test_101_items_is_400`; `test_body_without_workspace_id_is_accepted`; `test_items_from_two_workspaces_is_400`; `test_viewer_gets_403`; `test_viewer_in_a_editor_in_b_cannot_write_a` (items in workspace A → 403, nothing written; the same user writes in B → 200); `test_other_tenant_artifact_reports_not_found_item`; `test_item_rule_read_gives_forbidden_item`; `test_route_not_swallowed_by_artifact_detail`; `test_table_returns_page_with_row_shape`; `test_table_filters_and_sort_json`; `test_table_invalid_filter_is_400_with_field_name`; `test_table_unknown_param_is_400`; `test_table_page_size_capped_at_100`; `test_table_foreign_tenant_rows_absent`; `test_table_role_without_read_is_403`; `test_table_two_users_item_level_none_rule` (user A sees the row, user B with a `none` rule does not, `count` differs); `test_table_views_declare_no_if_match_header` (schema has no `If-Match` parameter on either operation).
- [ ] **Step 3: Run** `cd backend && pytest rest_api/tests/test_table_views.py -v`. Expected: FAIL (404 on the routes).
- [ ] **Step 4: Implement** views, serializers and the two routes (names `artifact-bulk-update`, `artifact-table`). No ORM in the views.
- [ ] **Step 5: Run** `pytest rest_api/tests/test_table_views.py rest_api/tests/test_architecture.py rest_api/tests/test_schema_completeness_1388.py rest_api/tests/test_openapi_list_params.py -v` and `pytest rest_api/tests -k conditional_request_contract_1397 -v`. Fix what the gates demand. Expected: PASS.
- [ ] **Step 6: Commit** `feat(api): add bulk-update and table query endpoints`.

### Task 1.7: MCP `artifact.bulk_update` and manifest

**Files:**
- Modify: `backend/mcp_server/tools/cross_cutting.py` (`_TOOL_MAP` at `:~205`, `_TOOL_SCHEMAS`, handler `_handle_artifact_bulk_update`; **rewrite the class docstring at `:199-203`**, which claims "all tools read-only, no audit entries" and is already wrong), `backend/mcp_server/tool_registry.py`, `backend/mcp_server/workspace_scope.py` (only if Step 1 requires), `docs/agent-templates/tool-manifest.json`
- Test: `backend/mcp_server/tests/test_bulk_update_tool.py`

**Interfaces:**
- Consumes: `BulkEditService.derive_workspace_id/bulk_update` (1.5), `require_param` from `mcp_server/tools/base.py`.
- Produces: tool `artifact.bulk_update` with input schema `{mode ("atomic"|"partial", default "atomic"), change_reason?, items: [{artifact_id, expected_version, fields}] (maxItems 100)}` and **no** `workspace_id`; result = the REST response body as JSON primitives; request-level errors are `VALIDATION_ERROR` tool errors; a failed atomic request returns the structured `failed` list with `isError`.

- [ ] **Step 1: Verify scoping and audit.** (a) Read `mcp_server/workspace_scope.py` (header and `:~480-520`): a write tool without a required `workspace_id` is scoped by `resolve_owning_workspace_id(entity_key, value)` of a named id parameter. Register `artifact.bulk_update` so the scope check uses the derived workspace of `items[0].artifact_id` (entity key `artifact`); if the scope module cannot express an id inside an array, the handler performs the API-key scope check itself with the derived workspace (use the helper the scope module exposes) and the test below pins it. (b) Read `BaseToolGroup.execute_tool` in `mcp_server/tools/base.py` and how `requirement.update` gets its MCP audit entry (`write_mcp_audit`, `:386`; `mcp_audit_handoff`, `tools/admin.py:218`). Decision: the service-level `_audit` rows written through the seam are the audit trail (one per written item, inside the transaction, so an atomic rollback leaves none); the MCP layer adds no second entry unless the group's execute path writes one for every write tool, in which case it is wrapped in `mcp_audit_handoff()` so each request produces exactly one request-level entry. The audit test pins whichever applies. (c) `artifact.bulk_update` is **not** added to `_READ_ONLY_TOOL_NAMES`; it stays write-gated (fail-closed).
- [ ] **Step 2: Write the failing tests:** `test_tool_listed_without_workspace_id_and_with_max_items`; `test_atomic_success_returns_updated_versions`; `test_atomic_failure_returns_failed_list_and_writes_nothing`; `test_forbidden_field_is_validation_error`; `test_read_only_key_cannot_call_it`; `test_api_key_scoped_to_other_workspace_is_refused`; `test_items_from_two_workspaces_is_validation_error`; `test_audit_rows_exist_once_per_written_item_and_none_after_atomic_failure`; `test_values_are_json_primitives`; `test_not_in_read_only_tool_names`; `test_cross_cutting_docstring_no_longer_claims_read_only`.
- [ ] **Step 3: Run** `cd backend && pytest mcp_server/tests/test_bulk_update_tool.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement** the tool, handler and docstring; rebaseline the manifest with `TOOL_MANIFEST_REBASELINE=1 pytest mcp_server/tests/test_tool_manifest_drift.py` (read the test header for the exact usage) and review the diff: only `artifact.bulk_update` added.
- [ ] **Step 5: Run** `pytest mcp_server/tests/test_bulk_update_tool.py mcp_server/tests/test_tool_manifest_drift.py rest_api/tests/test_architecture.py -v`. Expected: PASS (mind the ORM ceiling for `cross_cutting.py`: the handler calls the service only).
- [ ] **Step 6: Commit** `feat(mcp): add artifact.bulk_update tool`.

### Task 1.8: `editable_fields` read function (consumer: Dokumentensicht B5)

**Files:**
- Modify: `backend/application/artifact_fields_update.py`
- Test: `backend/application/tests/test_editable_fields.py`

**Interfaces:**
- Consumes: Tasks 1.1 and 1.2 (adapters, guard, freeze hook, item-right resolution).
- Produces: `editable_fields(ctx: AuthContext, item_type: str, artifact_id: UUID) -> list[str]` — the adapter's `writable_fields` plus the gateway fields the definition allows, minus fields rejected by `assert_no_forbidden_fields` (workflow-owned), minus everything if the artifact is frozen, and an empty list if the role has no write right or the item-level write right is not `write`. One definition resolve, one artifact query, **no writes**; it shares the helpers of the seam so display and enforcement cannot drift. Batch variant `editable_fields_many(ctx: AuthContext, item_type: str, artifact_ids: Sequence[UUID]) -> dict[UUID, list[str]]` with a constant query count (used by the Dokumentensicht `render` per page). REST/MCP exposure only if the Dokumentensicht plan needs it (O13).

- [ ] **Step 1: Write the failing tests:** `test_returns_allowlist_minus_workflow_owned` (no `status`, no `parent_id`); `test_includes_owner_priority_when_definition_editable`; `test_frozen_artifact_returns_empty` (stubbed `is_frozen`: every field, content included, is removed); `test_item_rule_read_returns_empty`; `test_viewer_role_returns_empty`; `test_never_writes` (no `ArtifactVersion`/entity change); `test_many_has_constant_query_count_for_5_and_50`; `test_agrees_with_the_seam` (every returned field is accepted by the seam with a valid value, a field not returned is refused).
- [ ] **Step 2: Run** `cd backend && pytest application/tests/test_editable_fields.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** both functions.
- [ ] **Step 4: Run** the file. Expected: PASS.
- [ ] **Step 5: Commit** `feat: add editable_fields read function for the document view`.

**Slice 1 exit check:** `pytest application/tests/test_editable_fields.py application/tests/test_artifact_update_adapters.py application/tests/test_artifact_fields_update.py application/tests/test_table_filter_dsl.py application/tests/test_requirement_filters.py application/tests/test_table_query_service.py application/tests/test_bulk_edit_service.py rest_api/tests/test_table_views.py rest_api/tests/test_update_seam_parity.py mcp_server/tests/test_bulk_update_tool.py -q` → all pass, only the documented xfails remain (freeze for Requirement, default order by `sort_key`). Then ask `agent-meta-manager` to update tool counts.

---

# Slice 2 — Bulk transition

### Task 2.1: `BulkEditService.bulk_transition`

**Files:**
- Modify: `backend/application/bulk_edit_service.py`
- Test: `backend/application/tests/test_bulk_edit_service_transition.py`

**Interfaces:**
- Consumes: `WorkflowFacade().transition(item_id, target_state, change_reason, ctx, *, item_type, workspace_id)` (`workflow_facade.py:63`), `BulkFailure` (1.5).
- Produces: `BulkEditService.bulk_transition(self, ctx: AuthContext, item_type: str, artifact_ids: Sequence[UUID], to_state: str, change_reason: str) -> BulkTransitionResult` (workspace derived from the artifacts as in `bulk_update`; ids from two workspaces → `ValidationError`; the facade call receives the derived `workspace_id`) with `BulkTransitionResult(transitioned: list[UUID], failed: list[BulkFailure])`. Spec §3.2 stays: **partial success only**, ≤ 100 ids (101 → `ValidationError`), each id runs through the normal facade call (full `allowed_roles`, `change_reason`, signature gates per item, never a direct `status` write); `artifact_id` → entity id via the adapter's `accessor`; facade errors map to `FORBIDDEN`/`VALIDATION_ERROR`/`CONFLICT`/`NOT_FOUND`; `change_reason` must be non-empty (request-level 400).

- [ ] **Step 1: Verify** how the facade reports a rejected transition: `grep -n "raise \|class .*Error" backend/application/workflow_facade.py backend/workflow/exceptions.py | head -20`. Map each exception type found to a `BULK_CODES` value in Step 4; unknown types become `VALIDATION_ERROR` with the exception message.
- [ ] **Step 2: Write the failing tests:** `test_transitions_valid_items_and_reports_failures` (3 reachable, 1 unreachable target → 3 + 1); `test_role_without_allowed_role_is_forbidden_per_item`; `test_signature_gate_item_fails_others_succeed`; `test_status_is_never_written_directly` (patch `Artifact.save`/entity update; assert only the facade ran); `test_101_ids_rejected`; `test_empty_change_reason_rejected`; `test_foreign_tenant_id_reports_not_found`; `test_ids_from_two_workspaces_rejected`; `test_mixed_current_states_each_use_own_graph`.
- [ ] **Step 3: Run** `cd backend && pytest application/tests/test_bulk_edit_service_transition.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement** the method; note in its docstring that the "Ausgewählte bestätigen" bulk accept (`proposed → draft`) of Menschen-im-System is one use of it, not a second code path.
- [ ] **Step 5: Run** the file. Expected: PASS.
- [ ] **Step 6: Commit** `feat: add bulk workflow transition with per-item gates`.

### Task 2.2: REST and MCP for bulk transition

**Files:**
- Modify: `backend/rest_api/table_views.py`, `backend/rest_api/table_serializers.py`, `backend/rest_api/urls.py`, `backend/mcp_server/tools/cross_cutting.py`, `docs/agent-templates/tool-manifest.json`
- Test: `backend/rest_api/tests/test_bulk_transition_view.py`, `backend/mcp_server/tests/test_bulk_transition_tool.py`

**Interfaces:**
- Produces: `POST /api/v1/artifacts/bulk-transition/` body `{"item_type","ids":[artifact ids],"to_state","change_reason"}` (no `workspace_id`, derived) → 200 `{"transitioned":[…],"failed":[{index,artifact_id,code,reason}]}` (partial success is the spec'd behaviour, so 200 even with failures); request-level errors 400; MCP `artifact.bulk_transition` (same schema, no `workspace_id`, scoped through the derived workspace as in Task 1.7, write-gated, not in `_READ_ONLY_TOOL_NAMES`). The transition path does not check item-level `ItemPermission` (workflow roles decide); noted with O10.

- [ ] **Step 1: Write the failing tests:** REST `test_bulk_transition_200_with_partial_failures`, `test_requires_change_reason_400`, `test_over_100_ids_400`, `test_viewer_403`, `test_viewer_in_a_editor_in_b_cannot_transition_a`, `test_route_precedes_router`, `test_declares_no_if_match`; MCP `test_tool_listed_write_gated_without_workspace_id`, `test_partial_result_primitives_only`, `test_read_only_key_refused`.
- [ ] **Step 2: Run** both files. Expected: FAIL.
- [ ] **Step 3: Implement** view, route (before `include(router.urls)`), tool, rebaseline manifest as in 1.7.
- [ ] **Step 4: Run** both files plus `mcp_server/tests/test_tool_manifest_drift.py rest_api/tests/test_architecture.py rest_api/tests/test_schema_completeness_1388.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: expose bulk transition via REST and MCP`.

---

# Slice 3 — Saved views and per-user table state

### Task 3.1: Models and migrations (table, then RLS)

**Files:**
- Modify: `backend/persistence/models.py`
- Create: `backend/persistence/migrations/<next>_table_views.py` (schema), `backend/persistence/migrations/<next+1>_table_views_rls_policy.py` (RLS, copy `0130_milestone_rls_policy.py`; both tables)
- Test: `backend/persistence/tests/test_table_view_models.py`

**Interfaces:**
- Produces (both `TenantScopedModel`, which already supplies `id`, `tenant`, `created_at`, `modified_at`, `version`, `created_by`, `modified_by`; do **not** redeclare `created_at`/`updated_at`):
  - `UserTableViewState`: `user` FK `User` (CASCADE), `workspace` FK `Workspace` (CASCADE), `item_type` Char(128), `columns` JSON list, `filters` JSON dict, `sort` JSON list; `db_table="pl_user_table_view_state"`; unique `(user, workspace, item_type)`.
  - `SavedView`: `workspace` FK, `owner` FK `User` (CASCADE), `item_type` Char(128), `name` Char(255), `columns`/`filters`/`sort` as above, `visibility` Char(16) choices `SAVED_VIEW_VISIBILITY_CHOICES = (("private","Private"),("workspace","Workspace"))` default `"private"`; `db_table="pl_saved_view"`; unique `(workspace, item_type, owner, name)`.

- [ ] **Step 1: Determine the migration numbers.** Run `ls backend/persistence/migrations | sort | tail -3`; use highest + 1 and + 2 (state in the commit message which numbers were taken and that `0131` was the highest at 814cb998). Check `grep -n "app.current_tenant" backend/persistence/migrations/0130_milestone_rls_policy.py` for the exact policy SQL to copy.
- [ ] **Step 2: Write the failing tests:** `test_saved_view_defaults_private`; `test_unique_name_per_owner_workspace_type`; `test_state_unique_per_user_workspace_type`; `test_json_defaults_are_independent_instances`; `test_tables_have_rls_policy` (via `pg_policies`: both tables, policy name ending `_tenant_isolation`, `relforcerowsecurity`); `test_rls_isolates_tenants` (SET ROLE pattern of `persistence/tests/test_rls_policies.py`: tenant B cannot select tenant A's rows); run `persistence/tests/test_rls_coverage.py` unchanged — it must pass.
- [ ] **Step 3: Run** `cd backend && pytest persistence/tests/test_table_view_models.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement** models, `python manage.py makemigrations persistence -n table_views`, then hand-write the RLS migration. Review the generated migration contains only the two `CreateModel`.
- [ ] **Step 5: Run** the new tests, `persistence/tests/test_rls_coverage.py` and `python manage.py makemigrations --check --dry-run`. Expected: PASS, no pending migrations.
- [ ] **Step 6: Commit** `feat: add SavedView and UserTableViewState models with RLS`.

### Task 3.2: Saved view and table-state services

**Files:**
- Create: `backend/application/saved_view_service.py`
- Test: `backend/application/tests/test_saved_view_service.py`

**Interfaces:**
- Consumes: models (3.1), `TableQueryService.query/columns/serialize_rows` (1.4), `compile_filters`/`compile_sort` (1.3).
- Produces:
  - `@dataclass(frozen=True) class SavedViewDTO: id: UUID; workspace_id: UUID; item_type: str; owner_id: UUID; name: str; columns: list; filters: dict; sort: list; visibility: str; version: int`.
  - `class SavedViewService(ServiceBase)`: `list(ctx, workspace_id, item_type) -> list[SavedViewDTO]` (own views + `visibility="workspace"` of others); `get(ctx, view_id) -> SavedViewDTO`; `create(ctx, workspace_id, item_type, name, columns, filters, sort, visibility="private") -> SavedViewDTO` (filters/sort validated against the current definition through the DSL, unknown field → `ValidationError`); `update(ctx, view_id, *, name=…, columns=…, filters=…, sort=…, visibility=…, expected_version=None) -> SavedViewDTO` and `delete(ctx, view_id) -> None` (owner or workspace admin only, else `PermissionDeniedError`); `apply(ctx, view_id) -> SavedViewApplyResult` with `SavedViewApplyResult(queryset: QuerySet, warnings: list[str])`.
  - `class TableViewStateService(ServiceBase)`: `get(ctx, workspace_id, item_type) -> dict | None`, `save(ctx, workspace_id, item_type, columns, filters, sort) -> dict` (upsert; JSON shape and size caps only, **no** definition validation: this is "where I was last").
  - `apply` is fail-soft: a `ValidationError` from the DSL (removed attribute, removed enum use) returns an **empty queryset** (`TableQueryService.query(...).none()`) and a warning naming the field.

- [ ] **Step 1: Verify the admin check.** Run `grep -rn "workspace_admin\|has_role(" backend/application/*_service.py | head -8` to find how services test for a workspace admin and use the same role name and call.
- [ ] **Step 2: Write the failing tests:** `test_create_and_list_private_visible_only_to_owner`; `test_workspace_view_visible_to_members_readonly_for_non_owner`; `test_non_owner_update_and_delete_denied_admin_allowed`; `test_create_with_unknown_filter_field_rejected`; `test_unique_name_conflict_is_validation_error`; `test_update_with_stale_expected_version_is_optimistic_lock_error`; `test_apply_returns_filtered_sorted_queryset`; `test_apply_with_removed_attribute_is_empty_with_warning` (Review Focus 4: delete the attribute from the definition after saving; no exception); `test_cross_tenant_view_not_found`; `test_state_upsert_one_row_per_user_workspace_type`; `test_state_is_per_user`; `test_state_rejects_oversized_json` (> 32 KiB or `columns` > 200 entries).
- [ ] **Step 3: Run** `cd backend && pytest application/tests/test_saved_view_service.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement** both services.
- [ ] **Step 5: Run** the file. Expected: PASS.
- [ ] **Step 6: Commit** `feat: add saved view and table state services`.

### Task 3.3: REST for saved views, apply and table state

**Files:**
- Create: `backend/rest_api/saved_view_views.py`
- Modify: `backend/rest_api/urls.py` (next to `users/me/preferences/` at `:553`), `backend/rest_api/table_serializers.py`
- Test: `backend/rest_api/tests/test_saved_view_views.py`

**Interfaces:**
- Consumes: `SavedViewService`, `TableViewStateService` (3.2), `parse_json_param` and the row serializers (1.6).
- Produces: `GET|POST /api/v1/saved-views/?workspace_id=&item_type=`; `GET|PATCH|DELETE /api/v1/saved-views/<uuid:pk>/` (PATCH carries `expected_version` in the body, **no** `If-Match`); `GET /api/v1/saved-views/<uuid:pk>/apply/` → same paginated row shape as `artifacts/table/` plus `warnings: []`; `GET|PUT /api/v1/users/me/table-view-state/?workspace_id=&item_type=` (GET without a record → 200 with defaults `{columns:[],filters:{},sort:[]}`).

- [ ] **Step 1: Write the failing tests:** CRUD happy paths; `test_private_view_of_other_user_is_404`; `test_workspace_view_patch_by_non_owner_is_403`; `test_apply_paginates_and_returns_warnings`; `test_apply_stale_view_is_200_empty_with_warning`; `test_state_roundtrip_and_defaults`; `test_unknown_query_param_400`; `test_routes_declare_no_if_match`; `test_foreign_tenant_404`.
- [ ] **Step 2: Run** `cd backend && pytest rest_api/tests/test_saved_view_views.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the views (zero ORM) and routes.
- [ ] **Step 4: Run** the file plus `rest_api/tests/test_architecture.py rest_api/tests/test_schema_completeness_1388.py rest_api/tests/test_openapi_list_params.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(api): add saved views and table view state endpoints`.

### Task 3.4: MCP `saved_view.list` and `saved_view.apply`

**Files:**
- Create: `backend/mcp_server/tools/saved_view.py`
- Modify: `backend/mcp_server/tool_registry.py` (new group via `register_groups` at `:~1008`; add both names to `_READ_ONLY_TOOL_NAMES`: they are reads), `docs/agent-templates/tool-manifest.json`
- Test: `backend/mcp_server/tests/test_saved_view_tools.py`

**Interfaces:**
- Consumes: `SavedViewService.list/apply` (3.2), `TableQueryService.serialize_rows` (1.4).
- Produces: `SavedViewToolGroup` with `saved_view.list` (`workspace_id` required, `item_type?`) and `saved_view.apply` (`view_id` required, `workspace_id` required, `page?`, `page_size?` ≤ 100) → rows in the `artifacts/table/` shape + `warnings`.

- [ ] **Step 1: Write the failing tests:** `test_both_tools_listed_and_read_only`; `test_list_returns_own_and_workspace_views`; `test_apply_returns_rows_and_warnings`; `test_apply_other_users_private_view_not_found`; `test_primitives_only`; `test_read_only_key_may_call`.
- [ ] **Step 2: Run** `cd backend && pytest mcp_server/tests/test_saved_view_tools.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** group, handlers (service calls only), registration, rebaseline manifest as in 1.7.
- [ ] **Step 4: Run** the file plus `mcp_server/tests/test_tool_manifest_drift.py rest_api/tests/test_architecture.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(mcp): add saved_view.list and saved_view.apply`. Then ask `agent-meta-manager` to update tool and group counts (new prefix `saved_view`).

---

# Slice 4 — Frontend

All Slice 4 tasks: React 19, tokens only, no inline `style={{`, `data-testid` on every interactive element, keyboard operable, i18n keys added to both locales in the same task they are used (nested under a `table` object; today only `tableCaption` keys exist). Run `cd frontend && npx vitest run <file>` per task and `npx vitest run src/test/ui-ratchet.test.ts src/test/i18n-parity.test.ts` in each task's last run step.

### Task 4.1: API wrapper

**Files:**
- Create: `frontend/src/api/table-views.ts`, `frontend/src/test/tableViewsApi.test.ts`

**Interfaces:**
- Produces types `FilterOperator = "contains"|"in"|"gte"|"lte"|"eq"`, `FilterConstraint {op: FilterOperator; value: unknown}`, `TableFilters = Record<string, FilterConstraint | FilterConstraint[]>`, `SortTerm {field: string; dir: "asc"|"desc"}`, `TableRow {id: string; artifact_id: string; item_type: string; version: number; values: Record<string, unknown>; locked: {state: string} | null}`, `BulkItem {artifact_id: string; expected_version: number; fields: Record<string, unknown>}`, `BulkFailure {index: number; artifact_id: string | null; code: "VALIDATION_ERROR"|"NOT_FOUND"|"FORBIDDEN"|"CONFLICT"; reason: string}`, `BulkUpdateResult {committed: boolean; mode: string; updated: {artifact_id: string; id: string; item_type: string; version: number}[]; failed: BulkFailure[]}`, `TableViewState {columns: {field: string; order: number}[]; filters: TableFilters; sort: SortTerm[]}`, `SavedView {id; workspace_id; item_type; owner_id; name; visibility: "private"|"workspace"; version; columns; filters; sort}`; objects `tableApi {query(params): Promise<Paginated<TableRow>>; bulkUpdate(body: {mode?: "atomic"|"partial"; change_reason?: string; items: BulkItem[]}): Promise<BulkUpdateResult>; bulkTransition(body)}`, `savedViewsApi {list, get, create, update, remove, apply}`, `tableViewStateApi {get, put}`.
- `tableApi.bulkUpdate` resolves with the body for HTTP 200 **and** for the 400/409 atomic-failure body (`committed:false`), so the UI can show the failure list; any other error throws via the existing client error path.

- [ ] **Step 1: Write the failing tests** (mock `apiClient`): `test_query_serialises_filters_and_sort_as_json_params`; `test_bulk_update_defaults_mode_atomic`; `test_bulk_update_returns_failure_body_on_409_and_400_with_committed_false`; `test_bulk_update_throws_on_403`; `test_saved_view_crud_paths`; `test_table_state_put_path_has_workspace_and_item_type`.
- [ ] **Step 2: Run** `npx vitest run src/test/tableViewsApi.test.ts`. Expected: FAIL.
- [ ] **Step 3: Implement** the module on top of `apiClient`/`getList` (`api/client.ts`).
- [ ] **Step 4: Run** the file. Expected: PASS.
- [ ] **Step 5: Commit** `feat(frontend): add table view API wrapper`.

### Task 4.2: Column model

**Files:**
- Create: `frontend/src/components/shared/ArtifactTable/columnModel.ts`, `frontend/src/test/tableColumnModel.test.ts`

**Interfaces:**
- Consumes: the resolved attribute definition type from `api/attribute-definitions.ts`.
- Produces: `TableColumn {name: string; type: string; kind: "core"|"extended"; label: string; editable: boolean | "workflow" | "system" | "automation"; options?: …; filterable: boolean; sortable: boolean; inlineEditable: boolean}`; `buildColumns(attributes, state: TableViewState, language: string): TableColumn[]` (state order first, then definition order; only `visible` attributes); `operatorsForColumn(column): FilterOperator[]` (mirrors `FILTER_OPERATORS_BY_TYPE` incl. `actor` → `["in"]`, status → `["in"]`; `criteria-list`, `widget`, and every `kind: "extended"` column → `[]` and `sortable=false`); `isWorkflowOwned(attr): boolean` (true for `"workflow"`, `"system"`, `"automation"`; an attribute with `editable: false` is read-only but not workflow-owned; `inlineEditable` is `editable === true` and a non-widget type only); `columnLabel(attr, language)`.

- [ ] **Step 1: Write the failing tests:** `test_operators_per_type_table` (every type row, including `actor`, `criteria-list`, `widget`); `test_status_column_filterable_with_in_but_never_inline_editable`; `test_extended_columns_not_filterable_or_sortable`; `test_inline_editable_only_when_editable_true_and_not_widget`; `test_state_order_then_definition_order`; `test_hidden_attributes_excluded`; `test_label_falls_back_to_name`.
- [ ] **Step 2: Run** `npx vitest run src/test/tableColumnModel.test.ts`. Expected: FAIL.
- [ ] **Step 3: Implement** the pure module (no React).
- [ ] **Step 4: Run** the file. Expected: PASS.
- [ ] **Step 5: Commit** `feat(frontend): derive table columns and operators from the definition`.

### Task 4.3: Grid

**Files:**
- Create: `frontend/src/components/shared/ArtifactTable/ArtifactTable.tsx`, `ArtifactTable.module.css`, `index.ts`, `frontend/src/test/ArtifactTable.test.tsx`

**Interfaces:**
- Produces: `ArtifactTableProps {columns: TableColumn[]; rows: TableRow[]; sort: SortTerm[]; onSortChange(next: SortTerm[]): void; selectedIds: ReadonlySet<string>; onSelectionChange(next: ReadonlySet<string>): void; renderCellEditor?(column, row): ReactNode; onStartInlineEdit?(rowId: string, column: string): void; loading: boolean}`; `toggleSort(sort: SortTerm[], field: string, additive: boolean): SortTerm[]` (click cycles asc → desc → off; shift adds a secondary term, max 5).
- Rows are virtualised with `@tanstack/react-virtual` (as `WorkspaceTree/tree-virtualization.tsx` does). The status cell renders `StatusBadge` read-only plus a separate "Change status" icon button (`data-testid="status-change-<rowId>"`) that is not part of the editable cell path. A locked row (`row.locked`) shows a lock marker and has no editors.

- [ ] **Step 1: Verify the primitives.** Run `grep -rn "useVirtualizer" frontend/src/components` (expect `shared/WorkspaceTree/tree-virtualization.tsx`) and read the pattern; `grep -rn "role=\"grid\"\|role=\"table\"" frontend/src/components | head -3` to see whether a grid role convention exists. Keep the choice (native `<table>` semantics with virtual rows via padding rows, or `role="grid"`) consistent with what you find and state it in the file header.
- [ ] **Step 2: Write the failing tests:** `test_renders_a_header_per_column_and_a_row_per_item`; `test_header_click_sorts_asc_then_desc_then_off`; `test_shift_click_adds_secondary_sort`; `test_toggle_sort_caps_at_five_terms`; `test_status_cell_uses_status_badge_and_has_no_editor`; `test_status_change_icon_is_a_separate_testid`; `test_checkbox_selection_and_select_all`; `test_locked_row_shows_lock_and_no_editor`; `test_keyboard_sort_via_enter_on_header`; `test_virtualises_large_row_sets` (1000 rows render far fewer DOM rows).
- [ ] **Step 3: Run** `npx vitest run src/test/ArtifactTable.test.tsx`. Expected: FAIL.
- [ ] **Step 4: Implement** the component and CSS Module (tokens only).
- [ ] **Step 5: Run** the file and `src/test/ui-ratchet.test.ts`. Expected: PASS.
- [ ] **Step 6: Commit** `feat(frontend): add ArtifactTable grid with sorting and read-only status`.

### Task 4.4: Filter popover and chips

**Files:**
- Create: `ArtifactTable/ColumnFilterPopover.tsx`, `ArtifactTable/ActiveFilterChips.tsx`, `ArtifactTable/fieldComponents.ts`, `ArtifactTable/filters.ts`, `frontend/src/test/ArtifactTableFilters.test.tsx`

**Interfaces:**
- Consumes: `operatorsForColumn` (4.2), `TableFilters` (4.1), field library `components/shared/ArtifactForm/fields` through the single seam `fieldComponents.ts`.
- Produces: `constraintsFor(filters: TableFilters, field: string): FilterConstraint[]`; `withConstraints(filters: TableFilters, field: string, constraints: FilterConstraint[]): TableFilters` (empty list removes the key); `ColumnFilterPopover {column, constraints, onChange(next: FilterConstraint[]): void, onClose()}` rendering per type: enum/multi-enum `MultiEnum`-style multiselect with `in`; text `contains` input; number and date two inputs (`gte`, `lte`) emitting a two-element list; boolean tri-state (all/true/false → `eq` or removal); reference/user/actor `in` via `ReferencePicker`/`UserPicker`/`ActorPicker`; `ActiveFilterChips {columns, filters, onChange}` with one removable chip per constraint.

- [ ] **Step 1: Verify the field components can render standalone** outside `ArtifactForm`: `sed -n 1,60p frontend/src/components/shared/ArtifactForm/fields/FieldShell.tsx` and `.../MultiEnum.tsx`; note required props (`FieldProps`). If a component needs form context, wrap the minimum in `fieldComponents.ts` instead of touching the originals.
- [ ] **Step 2: Write the failing tests:** `test_enum_popover_emits_in_with_selected_values`; `test_text_popover_emits_contains`; `test_date_range_emits_gte_and_lte_as_list`; `test_number_range_emits_gte_lte`; `test_boolean_tri_state_all_removes_constraint`; `test_actor_popover_emits_in`; `test_non_filterable_column_has_no_filter_trigger`; `test_chips_show_one_chip_per_constraint_and_remove_individually`; `test_with_constraints_empty_removes_key`; `test_popover_is_keyboard_operable_and_closes_on_escape`.
- [ ] **Step 3: Run** `npx vitest run src/test/ArtifactTableFilters.test.tsx`. Expected: FAIL.
- [ ] **Step 4: Implement** components and helpers.
- [ ] **Step 5: Run** the file, `ui-ratchet`, `i18n-parity`. Expected: PASS.
- [ ] **Step 6: Commit** `feat(frontend): add type-aware column filters and chips`.

### Task 4.5: Column picker and auto-persisted state

**Files:**
- Create: `ArtifactTable/ColumnPicker.tsx`, `ArtifactTable/useTableViewState.ts`, `frontend/src/test/ArtifactTableColumnPicker.test.tsx`

**Interfaces:**
- Consumes: `tableViewStateApi` (4.1), `TableColumn` (4.2).
- Produces: `ColumnPicker {attributes, state: TableViewState, onChange(next: TableViewState): void}` (checklist, reorder with up/down buttons plus drag; the keyboard path is the buttons); `useTableViewState(workspaceId: string, itemType: string): {state: TableViewState; setState(next: TableViewState): void; ready: boolean}` — loads once, debounces `PUT` by 800 ms, flushes on unmount, a failing `PUT` does not break the UI (state stays local, one toast).

- [ ] **Step 1: Write the failing tests:** `test_picker_toggles_and_reorders_columns`; `test_picker_buttons_reorder_without_pointer`; `test_state_loads_defaults_when_none_saved`; `test_set_state_debounces_one_put`; `test_unmount_flushes_pending_put`; `test_put_failure_keeps_local_state_and_does_not_throw`; `test_switching_item_type_loads_that_types_state`.
- [ ] **Step 2: Run** `npx vitest run src/test/ArtifactTableColumnPicker.test.tsx`. Expected: FAIL.
- [ ] **Step 3: Implement** (fake timers in tests).
- [ ] **Step 4: Run** the file and the two ratchet/parity tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(frontend): add column picker and persisted table state`.

### Task 4.6: Saved view bar

**Files:**
- Create: `ArtifactTable/SavedViewBar.tsx`, `frontend/src/test/ArtifactTableSavedViews.test.tsx`

**Interfaces:**
- Consumes: `savedViewsApi`, `SavedView`, `TableViewState` (4.1); modal primitive `components/shared/Dialog` (verify its props with `sed -n 1,60p frontend/src/components/shared/Dialog/Dialog.tsx`); `ConfirmDialog` for delete.
- Produces: `SavedViewBar {workspaceId, itemType, current: TableViewState, onApply(view: SavedView): void}`: dropdown of views, "Save view" dialog (name, private/workspace), update and delete only for owner or admin (buttons hidden otherwise), a stale-view warning banner when `apply` returns `warnings`.

- [ ] **Step 1: Write the failing tests:** `test_lists_private_and_workspace_views`; `test_save_dialog_creates_view_with_current_state`; `test_name_conflict_error_shown_in_dialog`; `test_non_owner_sees_no_edit_or_delete`; `test_delete_asks_for_confirmation`; `test_apply_calls_onApply_and_shows_warnings`; `test_dialog_focus_trap_and_escape`.
- [ ] **Step 2: Run** `npx vitest run src/test/ArtifactTableSavedViews.test.tsx`. Expected: FAIL.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run** the file and the two ratchet/parity tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(frontend): add saved view bar`.

### Task 4.7: Bulk action bar

**Files:**
- Create: `ArtifactTable/BulkActionBar.tsx`, `frontend/src/test/ArtifactTableBulk.test.tsx`

**Interfaces:**
- Consumes: `tableApi.bulkUpdate/bulkTransition`, `BulkUpdateResult`, `BulkFailure` (4.1), `TableColumn.inlineEditable` (4.2), `TableRow` (version source).
- Produces: `BulkActionBar {selectedRows: TableRow[], columns, onDone(): void}` (no workspace prop: the API derives it) with "Edit fields" (dialog offering **only** `inlineEditable` columns, a mode switch atomic/partial defaulting to atomic, a change-reason input) and "Change status" (lists target states reachable from every selected row's current state via the existing workflow API; verify with `grep -rn "transitions" frontend/src/api/workflow*.ts | head`). Sends `expected_version` from each row. Result handling: atomic failure keeps the dialog open with a per-artifact error list (code + reason), nothing is reported as saved; partial shows "N of M updated, K failed" with the failing rows listed; a 409 offers "reload rows".

- [ ] **Step 1: Write the failing tests:** `test_edit_dialog_offers_only_inline_editable_columns` (status and owner-less read-only fields absent); `test_submit_sends_items_with_each_rows_expected_version_and_mode_atomic`; `test_atomic_failure_lists_each_failing_artifact_with_code_and_reason_and_reports_no_success`; `test_partial_reports_counts_and_failures`; `test_conflict_failure_offers_reload`; `test_more_than_100_selected_disables_submit_with_hint`; `test_change_status_only_lists_common_reachable_states`; `test_change_reason_required_for_status_change`.
- [ ] **Step 2: Run** `npx vitest run src/test/ArtifactTableBulk.test.tsx`. Expected: FAIL.
- [ ] **Step 3: Implement**.
- [ ] **Step 4: Run** the file and the two ratchet/parity tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(frontend): add bulk action bar with atomic and partial reporting`.

### Task 4.8: Inline edit

**Files:**
- Create: `ArtifactTable/InlineCellEditor.tsx`, `frontend/src/test/ArtifactTableInlineEdit.test.tsx`

**Interfaces:**
- Consumes: `TableColumn` (4.2), `ArtifactTableProps.renderCellEditor/onStartInlineEdit` (4.3), the type-matching field component through `fieldComponents.ts` (4.4).
- Produces: `InlineCellEditor {column: TableColumn; row: TableRow; onSave(value: unknown): Promise<void>; onCancel(): void}`. Save uses the **single-item update path of that artifact type** (the existing `api/*` PATCH wrapper with `expected_version`), **not** `bulk-update` (spec §4.3). Only `inlineEditable` columns open an editor; Enter saves, Escape cancels, a server error keeps the editor open with the message, a 409 shows "changed by someone else, reload".

- [ ] **Step 1: Verify the per-type update wrappers.** `grep -n "export\|update" frontend/src/api/requirements.ts frontend/src/api/adrs.ts | head -20`; list the eight wrappers and their PATCH signatures in a map `UPDATE_BY_ITEM_TYPE` inside the component file.
- [ ] **Step 2: Write the failing tests:** `test_status_cell_never_opens_an_editor`; `test_text_cell_enter_saves_via_single_item_api_not_bulk`; `test_escape_cancels_without_request`; `test_server_validation_error_keeps_editor_open`; `test_conflict_shows_reload_hint`; `test_locked_row_cannot_enter_edit`; `test_enum_cell_uses_enum_select`.
- [ ] **Step 3: Run** `npx vitest run src/test/ArtifactTableInlineEdit.test.tsx`. Expected: FAIL.
- [ ] **Step 4: Implement**.
- [ ] **Step 5: Run** the file and the two ratchet/parity tests. Expected: PASS.
- [ ] **Step 6: Commit** `feat(frontend): add inline cell edit via the single-item path`.

### Task 4.9: Composition, Requirements page integration, i18n

**Files:**
- Create: `ArtifactTable/ArtifactTableView.tsx`, `frontend/src/test/ArtifactTableView.test.tsx`
- Modify: `frontend/src/components/RequirementEditors/RequirementEditors.tsx` (list/table toggle around `RequirementList` at `:682`), `frontend/src/i18n/locales/de.json`, `en.json`, `frontend/src/queries/` (a `useTableRows` React Query hook, `queries/tableViews.ts`)

**Interfaces:**
- Consumes: everything from 4.1–4.8, `useWorkspace()` (`context/WorkspaceContext.tsx:335`), `useArtifactDefinition` (`components/shared/ArtifactForm/useArtifactDefinition.ts`).
- Produces: `ArtifactTableView {itemType: AttributeItemType}` (self-fetching: definition, state, rows via `useTableRows(workspaceId, itemType, filters, sort, page)`; page size 50; pager); the toggle persists in `localStorage` (try/catch); i18n namespace `table` with every user-visible string of 4.3–4.8 in DE and EN. The pilot page is Requirements only; other pages are follow-ups.

- [ ] **Step 1: Write the failing tests:** `test_view_loads_definition_state_and_rows_and_renders_columns`; `test_filter_change_refetches_with_json_filters_and_resets_page`; `test_sort_change_refetches`; `test_applying_saved_view_replaces_filters_sort_columns`; `test_selection_enables_bulk_bar_and_done_refetches`; `test_requirement_editors_toggle_switches_between_list_and_table`; `test_toggle_survives_localstorage_failure`; `test_empty_result_shows_empty_state_with_active_filter_chips`.
- [ ] **Step 2: Run** `npx vitest run src/test/ArtifactTableView.test.tsx`. Expected: FAIL.
- [ ] **Step 3: Implement** the composition, the hook, the toggle and the locale files (nested objects, never dotted flat keys).
- [ ] **Step 4: Run** `npx vitest run src/test/ArtifactTableView.test.tsx src/test/ui-ratchet.test.ts src/test/i18n-parity.test.ts src/components/RequirementEditors` and `npx tsc --noEmit`. Expected: PASS (known-red `CanvasEditor.tools.test.tsx` and the `ArtifactDiff.smoke`/`useArchitectureData` tsc errors on main are not yours, see issue #527).
- [ ] **Step 5: Commit** `feat(frontend): mount ArtifactTable on the requirements page`.

---

# Slice 5 — E2E guardrail

### Task 5.1: The guardrail is visible and enforced

**Files:**
- Create: `e2e/tests/table-view-workflow-guardrail.spec.ts`

**Interfaces:**
- Consumes: `data-testid`s of 4.3 (`status-change-<rowId>`, header and row ids), 4.7, 4.8; helpers `e2e/helpers/auth.ts`, `global-setup.ts`; REST `PATCH /api/v1/artifacts/bulk-update/`.

- [ ] **Step 1: Write the spec** with five tests: `status cell has no inline editor, only the change-status action`; `bulk edit dialog does not offer status`; `bulk-update with status in the payload via the API answers 400 and changes nothing` (the E2E calls the API with the logged-in token, then re-reads the rows); `atomic bulk edit with one invalid value shows the failing artifact and saves none of the rows` (reload shows old values); `partial bulk edit reports N of M and keeps the valid rows`.
- [ ] **Step 2: Run** `cd e2e && npx playwright test tests/table-view-workflow-guardrail.spec.ts` against a stack built from S1–S4. Expected: PASS (run this spec alone; no full suite).
- [ ] **Step 3: Commit** `test(e2e): prove status cannot be written from the table view`.

---

## Self-Review

1. **Spec coverage.** §2 guardrail (workflow-owned and structural fields → whole-request 400) → 1.1, 1.5, 1.6, 4.2, 4.7, 4.8, 5.1. §3.1 bulk-update (mode, items, 100, `expected_version`, derived workspace, item-level write right, freeze, same service as single update, atomic without side effects) → 1.1, 1.2, 1.5, 1.6, 1.7. §3.2 bulk-transition → 2.1, 2.2. §3.3 MCP → 1.7, 2.2, 3.4. §4.1 DSL (types incl. `actor`/`criteria-list`, list of constraints, pure Python API, rights, `allocated`/`level`, `tree` sort) → 1.3, 1.4. §4.1 REST → 1.6. §4.2 state and saved views → 3.1–3.4. §4.3 frontend → 4.1–4.9. §5 migration (additive, RLS separate) → 3.1. §6 risks → 1.3/4.2, 4.7, 3.2/3.3. Dokumentensicht needs: filter language, `tree` order, `bulk-update` (items only, 101 → 400, `expected_version`, freeze 409), `editable_fields` (B5) → 1.3–1.8. All 24 old tasks are covered: old 1 dropped (replaced by 1.2), 2 → 1.3, 3 → 1.4, 4 → 1.1/1.2, 5 → 1.1, 6 → 1.5, 7 → 2.1, 8 → 3.1, 9 → 3.2, 10 → 1.6/2.2, 11 → 1.6, 12 → 3.3, 13 → 1.7/2.2, 14 → 3.4, 15–24 → 4.1–4.9/5.1.
2. **Step scan.** Every step names a command, a signature or a test with its assertion subject; bodies are given only for the order of work in 1.2 and 1.5, which the signatures and tests do not determine. "Verify" steps carry the exact grep/command and what to do per outcome.
3. **Type consistency.** `update_artifact_fields(ctx, item_type, artifact_id, fields, expected_version, *, change_reason)` (1.2) is the only writer used by 1.5 and `editable_fields` (1.8) shares its helpers; `assert_no_forbidden_fields` (renamed from the first draft, used in 1.1, 1.2, 1.5) is the single guard; `UpdateAdapter.update` returns `(entity_id, version)` (1.1) which 1.2 turns into `FieldUpdateResult`; `FieldUpdateResult`, `ArtifactFrozenError`, `BulkFailure` (1.5) are reused by 2.1; `BulkEditService.derive_workspace_id` (1.5) is used by 1.6, 1.7, 2.1/2.2; `compile_filters(item_type, attributes, filters, *, tenant_id, workspace_id)` (1.3) is called by 1.4 and 3.2; `TableRow` keys (`id, artifact_id, item_type, version, values, locked`) are identical in 1.4, 1.6, 3.3, 3.4, 4.1; wire codes `VALIDATION_ERROR|NOT_FOUND|FORBIDDEN|CONFLICT` identical in 1.5, 1.6, 2.1, 4.1; `mode` default `atomic` everywhere; no task sends or requires a bulk `workspace_id` any more.
4. **Review Focus.** Lines 1–5 are pinned in 1.5 (1, 3), 1.3 (2), 3.2 (4), 1.2/1.4/1.5/1.6 (5).
5. **Proportion.** The spec is about 250 lines; the plan has 24 tasks over five slices. Code bodies were replaced by signatures, test names and per-outcome verify steps; the review round added one task (1.8) and extended 1.2, 1.4, 1.5, 1.6, 1.7.
6. **Not verified at plan time** (each has a verify step): the role fence for the derived workspace (1.6 Step 1), MCP scope and audit mechanics (1.7 Step 1), version bump of every `update_X` on an empty call (1.2 Step 1), other embedding or Celery paths (1.1 Step 1, 1.5 Step 1), item-level read helper in `search_service` (1.4), workflow facade exception types (2.1), admin-role check (3.2), grid and field components standalone (4.3, 4.4), per-type frontend update wrappers (4.8).
