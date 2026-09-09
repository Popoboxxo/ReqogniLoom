# SDD ledger — plan: docs/superpowers/plans/2026-09-03-traceability-semantik.md

## Phase A — Catalog foundation

Task 1: `link_types` app scaffold and models — **done**

- New Layer-1 app `backend/link_types/` (`apps.py`, `models.py`, `migrations/0001_initial.py`, empty package markers), `"link_types"` added to `REQFLOW_APPS` after `"workflow"`.
- `GlobalLinkTypeDefinition` (`lt_global_definition`, `uq_lt_global_tenant_key`) and `WorkspaceLinkTypeDefinition` (`lt_workspace_definition`, `uq_lt_ws_tenant_ws_key`, `idx_lt_ws_workspace_key`, `source_global` SET_NULL) — both `TenantScopedModel`.
- **Deviation from plan text:** the plan's model code redeclares `version = IntegerField(default=1)`, which clashes with the inherited `AuditableModel.version` (Django `FieldError`). Dropped the local declaration; the field still exists via inheritance, so the Task-1 interface contract holds.
- **Deviation from plan text:** the plan's `tenant_id` fixture set a bare `uuid4()` as tenant; `TenantScopedModel.tenant` is a PROTECT FK to `persistence.Tenant`, so every insert would have hit an FK violation. Fixture now creates a real `Tenant` row.
- Tests: `backend/link_types/tests/test_models.py` — 4 passed. `makemigrations --check --dry-run` → "No changes detected".
- **Known red until Task 2:** `persistence/tests/test_rls_coverage.py` (2 failures) now flags `lt_global_definition` / `lt_workspace_definition` as tenant-scoped tables without an RLS policy. That is the ratchet working as designed; Task 2 closes it. Consider committing Task 1 + Task 2 together if the branch must stay CI-green per commit.
Task 2: RLS policies for the `lt_*` tables — **done**

- New `backend/link_types/migrations/0002_rls_policies.py` — byte-identical pattern to `workflow/0015_workflow_rls_policies.py`: ENABLE + FORCE ROW LEVEL SECURITY plus one `ALL` policy per table (`lt_global_definition_tenant_isolation`, `lt_workspace_definition_tenant_isolation`) keyed on `app.current_tenant`. Dependency is `("link_types", "0001_initial")` (0001 already depends on the current `persistence` head, so the `persistence/0003_rls_policies` dependency copied from the template is redundant but harmless — no cycle, Django resolves it transitively).
- Test: `backend/link_types/tests/test_rls_policies.py` (5 tests: RLS enabled+forced per table, policy exists per table, cross-tenant row invisibility).
- **Deviation from plan text:** the plan's `test_rows_of_another_tenant_are_invisible` draft used bare `uuid.uuid4()` values as tenant ids; `TenantScopedModel.tenant` is a PROTECT FK to `persistence.Tenant`, so the insert hit an FK violation before RLS was even relevant (same class of issue Task 1 already hit and documented). Fixed by creating two real `Tenant` rows, mirroring `link_types/tests/test_models.py`'s own fixture and `context_graph/tests/test_rls_policies.py`'s established pattern in this codebase.
- Verified: `pytest link_types/ persistence/tests/test_rls_coverage.py` → 12 passed (4 model + 5 new RLS + 3 previously-red RLS-coverage tests, now 0 failures). Migration reverse/forward roundtrip (`migrate link_types 0001` → `migrate link_types 0002`) checked clean via `backend-test` one-off container.
Task 3: `BUILTIN_LINK_TYPES` — the eight seeded definitions — **done**

- New `backend/link_types/builtin.py` — pure data module, deliberately import-free (no Django/models), so migrations can import it without app-registry side effects. Exposes `SUSPECT_RULES` (the 4-value frozenset), `BUILTIN_LINK_TYPES` (key → `definition_json` for the 8 core types: `derives-from`, `decomposes`, `allocated-to`, `verifies`, `decides`, `mitigates`, `references`, `diagram-ref`), `LEGACY_LINK_TYPE_MAPPING` (9 old keys → new key or `None` for retired), `SWAPPED_LEGACY_KEYS` (`satisfies`/`implements`), and `builtin_definition(key)` (deep-copy accessor).
- Implemented verbatim from the plan text (no deviations) — impact weights, suspect rules, `allowed_pairs`, tri-labels (de/en × downstream/upstream/neutral), `system_owned`/`manual_creatable` (only `diagram-ref` is reconciler-owned/non-manual) all match the spec tables exactly.
- Tests: `backend/link_types/tests/test_builtin.py` — 13 passed.
- Verified: full `link_types/` suite (`test_models.py` + `test_rls_policies.py` + `test_builtin.py`) — 22 passed, 0 failures. No existing test touched or broken.
Task 4: `definition_json` schema validation — **done**

- New `backend/link_types/schema.py` — `validate_definition_json(payload, *, key)`, pure function, no Django import, consumes `link_types.builtin.SUSPECT_RULES` as the only closed value range. Validates/normalizes `label` (tri-label: `{de,en} x {downstream,upstream,neutral}`, all non-empty strings), `allowed_pairs` (list of `{source_type, target_type}`, empty list legal), `suspect_rule` (must be one of `SUSPECT_RULES`), `impact_weight` (number >= 0); fills in defaults for the five optional boolean flags (`coverage_relevant`, `manual_creatable`, `system_owned`, `active`, `built_in`); rejects unknown top-level fields and missing required fields. Raises `persistence.errors.ValidationError` naming the offending field.
- Implemented verbatim from the plan text (no deviations).
- Tests: `backend/link_types/tests/test_schema.py` — 9 passed (all 8 builtin definitions validate + 8 negative/default-filling cases).
- Verified: full `link_types/` suite run via `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml run --rm backend-test python -m pytest link_types/ -v` — 31 passed, 0 failures (22 pre-existing + 9 new). No existing test touched or broken.
- Not a data migration (pure validation module, no new/changed migration files) — the plan's migration-idempotency check from the previous session does not apply here; confirmed no files under `backend/link_types/migrations/` changed.
Task 5: Catalog resolver and `validate_link_pair` — **done**

- New `backend/link_types/catalog.py` — the single seam (`resolve_catalog`, `get_definition`, `validate_link_pair`, `validate_definition`, `invalidate_workspace`, `CACHE_NAMESPACE`). Process-local cache dict keyed by workspace id, tagged with `persistence.cache_generation.cache_generation`/`bump_cache_generation` so a write on any worker invalidates every other worker's entry on next read (same pattern as `presets/gate.py`). `validate_link_pair` replaces `traceability.types.check_se_link_semantics`: no `se_mode` gate, no `SE_CORE_ARTIFACT_TYPES` allow-list — every artifact type is checked, closing audit finding U2. `normalize_artifact_type` strips `"Type:subtype"` tags before matching `allowed_pairs` (wildcard `"*"` on either side matches anything); `manual=True` additionally rejects `manual_creatable=False` (system-owned) types.
- Implemented verbatim from the plan text (no deviations in `catalog.py` itself).
- **Deviation from plan text (test fixture only):** the plan's `workspace` fixture in `test_catalog.py` set a bare `TenantContext.set_tenant(uuid.uuid4())`; `TenantScopedModel.tenant` is a PROTECT FK to `persistence.Tenant`, so every `WorkspaceLinkTypeDefinition.objects.create(...)` in the fixture hit an FK violation (`lt_workspace_definition_tenant_id_...` not present in `pl_tenant`) — identical class of issue already documented for Task 1/Task 2/Task 2's RLS test. Fixed the same way: create a real `Tenant` row via `persistence.models.Tenant.objects.create(...)` and activate its id, mirroring `link_types/tests/test_models.py`. Same fix applied to the standalone `test_a_workspace_without_any_rows_resolves_to_an_empty_catalog` (no fixture, own tenant).
- Tests: `backend/link_types/tests/test_catalog.py` — 12 passed.
- Verified: full `link_types/` suite run via `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test python -m pytest link_types/ -v` — 43 passed, 0 failures (31 pre-existing + 12 new). No existing test touched or broken.
- Not a data migration — pure resolver module, no new/changed files under `backend/link_types/migrations/`.
Task 6: `GlobalLinkTypeDefinitionStore` with propagation — **done**

- New `backend/link_types/global_store.py` — `GlobalLinkTypeDefinitionStore` with `get`/`list`/`create`/`update`/`delete`, all via `unscoped` (explicit `tenant_id` param, RLS remains the second isolation layer underneath). `update` validates through `schema.validate_definition_json`, locks `system_owned`/`manual_creatable` on system-owned types (label edits stay allowed), bumps `version`, and propagates the new `definition_json` into every derived `WorkspaceLinkTypeDefinition` row with `is_customized=False` via a bulk `QuerySet.update()` — then calls `catalog.invalidate_workspace` per affected workspace, since the bulk update bypasses `save()`/signals. `delete` rejects system-owned types and deliberately does not touch derived rows (`source_global` is SET_NULL, so they survive as standalone definitions).
- Implemented verbatim from the plan text (no deviations in `global_store.py` itself).
- **Deviation from plan text (test fixture only):** same class of issue already documented for Task 1/2/5 — the plan's `tenant_id` fixture set a bare `uuid.uuid4()`; `TenantScopedModel.tenant` is a PROTECT FK to `persistence.Tenant`. Fixed by creating a real `Tenant` row (`name=...`, `slug=f"lt-gs-{uuid4().hex}"`, mirroring `link_types/tests/test_catalog.py`'s fixture) and activating its id.
- Tests: `backend/link_types/tests/test_global_store.py` — 12 passed.
- Verified: full `link_types/` suite run via `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test python -m pytest link_types/ -v` — 55 passed, 0 failures (43 pre-existing + 12 new). No existing test touched or broken.
- Not a data migration — pure store module, no new/changed files under `backend/link_types/migrations/`.
Task 7: `WorkspaceLinkTypeDefinitionStore` and provisioning — **done**

- New `backend/link_types/workspace_store.py` — `WorkspaceLinkTypeDefinitionStore` (`get`/`list`/`update`/`reset`, all via `unscoped`) plus module-level `provision_workspace_link_types(*, workspace_id, tenant_id)`. `update` validates through `schema.validate_definition_json`, bumps `version`, sets `is_customized=True`, invalidates the workspace's resolved-catalog cache. `reset` restores from `source_global` (falls back to `builtin_definition` if the global row is gone), clears `is_customized`; raises `ValidationError` when a tenant-invented type has neither. `provision_workspace_link_types` is idempotent (`get_or_create` per built-in key, both on the global template and the workspace row), never touches an existing (customized or not) row, and reuses an existing global template instead of duplicating it.
- Modified `backend/application/workspace_provisioning.py` — added the `provision_workspace_link_types` call at the end of `provision_workspace_defaults` (after the permission-definition provisioning), with a local import to avoid a Layer-2→Layer-1(`link_types`) import at module load time. Reached transitively by every existing caller (`WorkspaceService.create_workspace`/`clone_workspace`, `self_init`, `provision_workspace_defaults_scoped`) — no separate wiring needed.
- **Deviation from plan text (import):** dropped the plan's `from .global_store import GlobalLinkTypeDefinitionStore` import in `workspace_store.py` — the store class is listed in the Task-7 "Consumes" interface but the implementation shown never actually calls it (provisioning talks to `GlobalLinkTypeDefinition.unscoped` directly); kept as written it would be an unused import (lint F401). No behavioural difference from the plan's own reference implementation.
- **Deviation from plan text (test fixture only):** same class of issue already documented for Task 1/2/5/6 — the plan's `tenant_id` fixture set a bare `uuid.uuid4()`; `TenantScopedModel.tenant` is a PROTECT FK to `persistence.Tenant`. Fixed by creating a real `Tenant` row (mirroring `link_types/tests/test_catalog.py`'s fixture) and activating its id via `TenantContext.set_tenant`.
- **Deviation from plan text (Step 4 command):** the plan's verification command names `application/tests/test_workspace_provisioning.py`, which does not exist in this codebase. Ran the actual regression coverage instead: `application/tests/test_workspace_provisioning_rls_815.py` (RLS-armed provisioning path), `application/tests/test_self_init.py` (bootstrap path that calls `provision_workspace_defaults_scoped`), and `application/tests/test_workspace_lifecycle.py` (`create_workspace`/`clone_workspace`, the request-scoped path) — all three exercise `provision_workspace_defaults` end-to-end.
- Tests: `backend/link_types/tests/test_workspace_store.py` — 11 passed.
- Verified: `link_types/ application/tests/test_workspace_lifecycle.py` — 93 passed, 0 failures (66 pre-existing `link_types` + 11 new + 27 workspace-lifecycle, incl. clone/create/close/delete/reactivate paths that all route through `provision_workspace_defaults`). Also ran `link_types/tests/test_workspace_store.py application/tests/test_workspace_provisioning_rls_815.py application/tests/test_self_init.py` standalone — 23 passed, 0 failures. No existing test touched or broken.
- Not a data migration — pure store module plus one call added to an existing function; no changes under `backend/link_types/migrations/`. Task 8 (next) is the actual backfill for pre-existing tenants/workspaces created before this call existed.
Task 8: Backfill migration for existing tenants and workspaces — **done**

- New `backend/link_types/migrations/_seed_helpers.py` — `seed_tenant(tenant_id, workspace_ids) -> (globals_created, rows_created)`. The `_` prefix keeps Django's migration loader from treating it as a migration; living outside the numbered module is what makes the behaviour testable without replaying migration state.
- New `backend/link_types/migrations/0003_seed_builtin_link_types.py` — `RunPython(seed_builtin_link_types, unseed)`, dependency `("link_types", "0002_rls_policies")`. Forward: enumerate `pl_tenant` (deliberately outside RLS per `persistence/0003_rls_policies`, so this read can never be silently blinded), arm `SET app.current_tenant` per tenant, read that tenant's workspaces inside the armed window, call `seed_tenant`, `RESET` in a `finally`. Logs the created-row totals.
- New `backend/link_types/tests/test_seed_migration.py` — 5 tests (the plan's 3 plus "an already provisioned + customized workspace is left alone" and "a tenant without workspaces still gets its 8 global templates").
- **Deviation from plan text (implementation, deliberate):** the plan's `_seed_helpers.seed_tenant` re-implements the workspace-row loop that Task 7's `workspace_store.provision_workspace_link_types` already contains verbatim. `seed_tenant` now delegates that half to Task 7's function (and keeps only the global-template loop itself, so a workspace-less tenant still gets its templates). One seeding code path means a backfilled workspace and a freshly provisioned one are byte-identical by construction, instead of by two copies staying in sync. No behavioural difference; the plan's own return contract `(globals_created, rows_created)` is preserved.
- **Deviation from plan text (dependencies):** dropped the redundant `("persistence", "0001_initial")` entry — `link_types/0001_initial` already depends on `persistence/0079_drop_glossary_term_version`, so the persistence models are reachable transitively.
- **Deviation from plan text (reverse):** `unseed` now runs the same per-tenant arming as the forward direction. The plan's version deletes through the historical (unfiltered) manager, which is only correct for a `BYPASSRLS` role — under a plain owner the RLS policy has no "all tenants" mode, so an unarmed delete removes nothing and a rollback would report success while changing nothing.
- **Deliberately NOT using the house `SET LOCAL row_security = off` guard** (`diagram/0010_backfill_current_content`, `persistence/0073_backfill_artifact_backing`): that guard exists for migrations that write cross-tenant in one statement and would otherwise no-op silently. Here every read and write happens with the correct tenant armed, so the policy is satisfied and the migration also works under a non-`BYPASSRLS` owner — where `row_security = off` would instead turn a working migration into a hard error. Reasoning recorded in the migration docstring.
- Tests: `link_types/tests/test_seed_migration.py` — 5 passed. Regression set `link_types/ persistence/tests/test_rls_coverage.py application/tests/test_workspace_lifecycle.py application/tests/test_self_init.py` — 111 passed, 0 failures, preceded by a clean `makemigrations --check --dry-run`.
- **Live-verified against the dev DB** (29 tenants / 105 workspaces, migrate run as the owner role `reqflow`): forward → 232 global rows (29x8) + 840 workspace rows (105x8), all `source_global` set, none customized, every tenant exactly 8 templates. One workspace row then hand-customized; rollback (`migrate link_types 0002`) → 0 globals / 1 workspace row (the customized one survives, its `source_global` SET_NULL as designed); reapply → back to 232/840 with the customized row untouched (`impact_weight` still 0.77, `is_customized` still true). Second forward run over the already-seeded DB (`migrate 0002 --fake` then forward) logged `LinkTypeCatalog seed: 0 global templates, 0 workspace rows created` with counts unchanged — idempotent against a fresh, a partially seeded and a fully seeded database. Dev DB left forward-applied at `0003`.
- Known wart (accepted): a row that was customized *before* a rollback keeps `source_global_id = NULL` after the reapply, because `get_or_create` finds it and leaves it alone. `WorkspaceLinkTypeDefinitionStore.reset` already falls back to `builtin_definition` when `source_global` is gone, so nothing breaks; rollback is not a routine operation.

**Phase A (Catalog foundation) is complete** — Tasks 1-8 all done.

## Phase B — Flip validation to always-on

Task 9: `inventory_link_types` command (evidence for OFFENE FRAGE 1) — **done**

- New `backend/link_types/management/__init__.py`, `backend/link_types/management/commands/__init__.py`, `backend/link_types/management/commands/inventory_link_types.py` — `collect_observed_triples() -> list[dict]` (post-3.1-rename triples with row counts, legacy keys mapped to their successor via `LEGACY_LINK_TYPE_MAPPING`, endpoints swapped for `SWAPPED_LEGACY_KEYS`), `uncovered_triples(observed) -> list[dict]` (subset no built-in `allowed_pairs` entry matches), and `Command` (`inventory_link_types [--json PATH]`) printing both lists and optionally writing them as JSON.
- Implemented verbatim from the plan text for the pure functions and the `Command` shell — no deviation there; `LEGACY_LINK_TYPE_MAPPING`, `SWAPPED_LEGACY_KEYS`, `BUILTIN_LINK_TYPES`, `normalize_artifact_type` all already existed from Tasks 3/5, so this task is a pure addition.
- **Deviation from plan text (implementation, functional, found via manual self-verification — not just green tests):** the plan's `collect_observed_triples` queries `TraceLink.objects.values(...)`, the tenant-scoped default manager. Run standalone (`python manage.py inventory_link_types`, no request/tenant context active), this raises `TenantContextNotSetError` before producing any output — the command as specified cannot do the one thing it exists for (inventory the *whole* database ahead of a production run for OFFENE FRAGE 1/Task 10). Fixed by switching to `TraceLink.unscoped` inside a `transaction.atomic()` block that first runs `SET LOCAL row_security = off` on the connection — the exact existing pattern `persistence/management/commands/check_artifact_backing.py` uses for the same "must see every tenant's rows, and fail loudly rather than silently report zero" requirement. No change to the function's signature or return contract.
- **Deviation from plan text (test fixture only):** same class of issue documented for Tasks 1/2/5/6/7 — the plan's fixture passes `title=f"{kind}-{uuid.uuid4()}"` to `Artifact.objects.create(...)`, but `Artifact` has no `title` field (confirmed against `persistence/models.py:793-892` and the `Artifact.objects.create(tenant=..., workspace=..., artifact_type=...)` pattern used throughout `context_graph/tests/test_rls_policies.py` and others). Dropped the `title` kwarg (and the now-unused `uuid` import) from the fixture; no behavioural difference from the plan's own test intent.
- Tests: `backend/link_types/tests/test_inventory_command.py` — 6 passed (as specified in the plan).
- Verified: full `link_types/` suite — 77 passed, 0 failures (71 pre-existing + 6 new). No existing test touched or broken. `makemigrations --check --dry-run` → "No changes detected" (pure command + test, no schema change). Manually ran `python manage.py inventory_link_types` standalone against the test DB with no tenant context active — after the fix it completes and prints `Observed triples: ...` / `All observed triples are covered.` instead of crashing; before the fix it raised `TenantContextNotSetError`, confirming the deviation above was load-bearing, not cosmetic.
- Not a data migration — pure command + test module, no changes under `backend/link_types/migrations/`.
- **Evidence gathering for OFFENE FRAGE 1 (production-shaped run) is explicitly Task 10's prerequisite step, not this task's** — Task 9 delivers the tool, Task 10 is the one that runs it against a production-shaped database and pastes the `uncovered` list into `GRANDFATHERED_PAIRS`. Left undone here, as scoped.
Task 10: Grandfather the observed-but-uncovered pairs — **done**

- New `backend/link_types/grandfathered.py` — `GRANDFATHERED_PAIRS` (4 entries across 2 keys) + `apply_grandfathered_pairs(definition, key)` (deep-copying, additive, duplicate-free). Function body implemented verbatim from the plan text; the **contents of the dict are the live inventory result, not the plan's placeholder**, as the plan's own comment demands ("REPLACE THE CONTENTS … The example below is the shape").
- New `backend/link_types/migrations/0004_grandfather_observed_pairs.py` — `RunPython(apply_pairs, noop)`, dependency `("link_types", "0003_seed_builtin_link_types")`. Touches every `GlobalLinkTypeDefinition` row and only the `is_customized=False` `WorkspaceLinkTypeDefinition` rows.
- New `backend/link_types/tests/test_grandfathered.py` — the plan's 7 pure-function tests plus 2 migration tests.

**OFFENE FRAGE 1 — how the plan default was applied here**

Plan default (*grandfathering by inventory*) used as documented, not re-litigated. The `uncovered` list was produced by two real runs of Task 9's `inventory_link_types`, both as the DB owner role (the least-privilege app role is RLS-blinded and the command fails loudly there — confirmed: `ProgrammingError: query would be affected by row-level security policy for table "pl_tracelink"`):

1. **Dev database** (`reqflow`, 29 tenants / 105 workspaces / 196 artifacts): **2 `TraceLink` rows total**, both legacy `realizes` → 1 observed triple (`decomposes: ArchitectureElement -> ArchitectureElement`), **0 uncovered**. Too thin to be evidence on its own — recorded so the thinness is not mistaken for "nothing to grandfather".
2. **Scratch database** `linkinv` (created from scratch, migrated to head, seeded with `seed_demo` + `seed_toothbrush` — `seed_toothbrush` is the *only* seeder in this repo that writes `TraceLink` rows; `seed_demo` writes none): **1974 rows / 8 observed triples, 4 uncovered.**

The 4 uncovered triples, pasted verbatim into `GRANDFATHERED_PAIRS`:

| triple (post section-3.1 rename) | rows | legacy origin |
|---|---|---|
| `allocated-to` StakeholderNeed → Requirement | 40 | `satisfies` |
| `references` Adr → ArchitectureElement | 12 | `documents` |
| `references` Issue → ArchitectureElement | 55 | `traces` |
| `references` Risk → Requirement | 22 | `traces` |

Exact `source_type`/`target_type` values are used, **not** the plan placeholder's `"*"` wildcards — the wildcard would legalize far more than the evidence supports.

**Finding worth carrying into Task 16:** `builtin.SWAPPED_LEGACY_KEYS` assumes every `satisfies` row ran ArchitectureElement → Requirement. The real data also uses `satisfies` as Requirement → StakeholderNeed, which the swap turns into `allocated-to` StakeholderNeed → Requirement — semantically an inverted `derives-from`, not an allocation. Grandfathered so the 40 rows stay creatable; **re-typing them is a data question Task 16 owns and this task deliberately did not decide.**

**Limitation, stated rather than papered over:** Goal / MainGoal / Interview — three of the four artifact types OFFENE FRAGE 1 names — produced *no* `TraceLink` rows in either database, so nothing was added for them (the plan says "do not guess the contents"). Issue *did* appear and is in the list. Recorded in the module docstring: an installation whose data differs must re-run `inventory_link_types` before applying `0004`.

- **Deviation from plan text (migration, deliberate — same class as Task 8):** the plan's `apply_pairs` iterates `GlobalLinkTypeDefinition.objects.filter(key=key)` with no tenant arming. Both `lt_*` tables carry FORCE RLS with a `NULLIF(current_setting('app.current_tenant', true), '')::uuid` predicate, so an unarmed `UPDATE` under a non-`BYPASSRLS` owner matches nothing **and reports success** — the migration would log "0 rows" on a fully seeded database and Task 11's always-on validation would then reject exactly the data this migration exists to legalize. `apply_pairs` therefore iterates tenants and arms `app.current_tenant` per tenant (`_arm`/`_disarm`), identical in shape to `0003`. The 6-line helper pair is duplicated rather than imported from `0003` so a future squash of `0003` cannot break `0004`.
- **Deviation from plan text (migration, minor):** added an `if merged == row.definition_json: continue` guard, so a re-apply is a true no-op and the log line reports honest counts.
- **Deviation from plan text (tests, additive):** the plan specifies 7 pure-function tests; 2 migration tests were added because the RLS deviation above is the only non-trivial logic in the file. They use a `SimpleNamespace`-based `apps` shim mapping `objects` → `unscoped`, because the *live* `lt_*` models default to the tenant-scoped manager while a real migration receives historical models with a plain one.
- **Honest limit of those 2 tests, recorded in the test file itself:** the suite's DB role (`reqflow`) is a `BYPASSRLS` superuser in this cluster, so removing the arming from the migration keeps them green — verified by actually deleting the `_arm` call and re-running (2 passed). The arming is therefore *not* proven by tests; it is justified by parity with `0003` (live-verified in Task 8) and by the non-superuser-owner deployment case, which cannot be reproduced from this environment.
- Tests: `backend/link_types/tests/test_grandfathered.py` — 9 passed. Full `link_types/` suite — **86 passed, 0 failures** (77 pre-existing + 9 new), preceded by a clean `makemigrations --check --dry-run`. No existing test touched or broken.
- **Live-verified beyond green tests:**
  - `migrate link_types` on the seeded scratch DB → `grandfathered pairs applied to 6 rows` (2 keys x (1 global + 2 workspace rows)); re-apply after `migrate link_types 0003 --fake` → `0 rows`, i.e. idempotent.
  - `migrate link_types` on the **dev DB** → `grandfathered pairs applied to 268 rows` = 29 tenants x 2 keys (58 globals) + 105 workspaces x 2 keys (210 workspace rows). Dev DB left forward-applied at `0004`.
  - **End-to-end acceptance check** via `manage.py shell` against the seeded DB: `link_types.catalog.validate_link_pair(...)` now accepts all 4 previously-uncovered triples in a real workspace catalog, while the negative control still fails: `'verifies' is not valid from Risk to Adr. Allowed: TestCase->ArchitectureElement, TestCase->Requirement.` This is the actual point of the task — green unit tests alone would not have shown it.
- Scratch DB `linkinv` dropped afterwards; dev DB data untouched apart from the `lt_*` definition rows the migration is supposed to extend.
- **Landmine handed to Task 11 (not fixed here — out of scope):** `workspace_store.provision_workspace_link_types` seeds a new workspace with `copy.deepcopy(global_row.definition_json)`, so a new workspace **inside an already-migrated tenant inherits** the grandfathered pairs, but a **brand-new tenant** gets the plain `BUILTIN_LINK_TYPES`. Once Task 11 flips validation on, `Adr → ArchitectureElement` `references` (which the app's own seeder writes) becomes uncreatable in a fresh tenant. Fixing it means deciding whether grandfathering is permanent policy or legacy-only — a design decision the plan defers, so it is flagged, not pre-empted.
Task 11: Wire `TraceLinkService` to the catalog, delete the `se_mode` gate — **done**

**Status:** Commit f1ec4d25, 2026-09-09. Phase B validation complete; all escape hatches removed; tenant asymmetry for 4 grandfathered pairs now intended.

- `application/trace_link_service.py`: `_check_se_semantics` → `_check_link_pair(...,  *, manual=True)`, delegating to `link_types.catalog.validate_link_pair`. `create_trace_link` lost its two pre-resolution gates (`link_type not in VALID_LINK_TYPES`, the hardcoded `diagram-ref` rejection) — the catalog decides both now, which is why the verdict moves *after* endpoint resolution (it depends on the endpoints' workspace).
- `traceability/types.py`: `SE_LINK_SEMANTICS`, `SE_CORE_ARTIFACT_TYPES`, `SAME_TYPE`, `check_se_link_semantics`, `normalize_artifact_type` and the `_REQ`/`_ARCH`/`_TC`/`_SN`/`_DIAG` aliases deleted (and dropped from `__all__`). `LinkType`'s docstring now says it is not the validation authority.
- New `application/tests/test_trace_link_catalog_validation.py` — the plan's 11 tests plus one for the removed permissive fallback (a missing endpoint is now `NotFoundError`, not a skipped gate). **12 passed.**

**Three escape hatches removed, not one:** the plan names the `se_mode` probe and the `SE_CORE_ARTIFACT_TYPES` allow-list. The old method also wrapped everything in `except Exception: return` — any resolution failure waved the link through. That is gone too and is called out in `_check_link_pair`'s docstring.

**Deviation from plan text (sequencing, deliberate):** the plan also says to delete `VALID_LINK_TYPES`/`MANUAL_LINK_TYPES` and shrink `LinkType` to eight members in this task. Not done: `MANUAL_LINK_TYPES` is the published `link_type` enum of two MCP tool schemas (`mcp_server/tools/architecture.py`, `.../cross_cutting.py`), `VALID_LINK_TYPES` is re-exported by `application/services.py` and pre-filters the ReqIF importer, and the retired enum members are read by `traceability/audit/hierarchy.py`, `.../rules/trace_derivation_allocation.py` and others. All of those consumers belong to Task 17 / Task 21, and deleting the symbols here is an immediate `ImportError` at module load across `mcp_server`. Both constants are kept with docstrings stating they are no longer a validation authority; the deletion moves with their consumers.

**Deviation from plan text (addition, load-bearing):** `LinkType` gained `MITIGATES` and `REFERENCES` — two of the plan's own eight target members. Without them `traceability/trace_link_manager._validate_link_type` (a second, Layer-1 allow-list the plan does not mention) rejects `mitigates`/`references` *after* the catalog has accepted them. `VALID_LINK_TYPES` must stay a superset of `link_types.builtin.BUILTIN_LINK_TYPES`; `_validate_link_type`'s docstring now says so and demotes itself to a fail-safe for direct Layer-1 callers. Consequence: the committed `docs/agent-templates/tool-manifest.json` gained the two enum values (edited in place rather than regenerated — a container-side `export_tool_manifest` run cannot read `VERSION` and would have written `generated_from: reqogniloom==unknown`; the diff was verified against a real regeneration and is exactly those two values, twice).
- `normalize_artifact_type` moved to `link_types.catalog` per the plan; its three importers repointed (`application/artifact_diff_service.py`, `mcp_server/tools/cross_cutting.py`, `rest_api/tests/test_artifact_versioning_audit.py`).

**Two bugs the flip surfaced, both previously invisible because enforcement was se_mode-only:**
1. `application/tests/test_ai_derivation_service.py` called `_write_derived_entity` without `new_entity_is_link_source=True`, i.e. it asserted the *inverted* `derives-from` (Need → Requirement) that issue #341 fixed in production. Every real caller in `mcp_server/tools/ai_derivation.py` passes the flag; only the tests encoded the pre-#341 direction. Fixed in the tests.
2. `mcp_server/tests/test_traceability_link_issue264.py` created `verifies` Requirement → TestCase. `test.link`/`test.create` have always written TestCase → Requirement, and even the old SE matrix only allowed that direction — the test passed solely because its workspace was dev_mode. Endpoints swapped; the test still pins what #264 was about (a TestCase named by its own id resolves).

**Test-suite invariant this task establishes:** a workspace with no `lt_workspace_definition` rows now rejects *every* trace link. Production always provisions (`application/workspace_provisioning.provision_workspace_defaults` → Task 7's hook), but a dozen test fixtures build `Workspace.objects.create(...)` directly. `persistence/tests/factories.make_workspace` now provisions (single seam for ~30 test modules); the fixtures that do not use it call `provision_workspace_link_types` explicitly (`application/tests/test_allocation.py`, `.../test_trace_link_service_query_count_625.py`, `mcp_server/tests/conftest.py`, `rest_api/tests/conftest.py`, and 5 mcp_server modules). Five `application/tests` fixtures were switched to `make_workspace` instead of hand-rolling the call.
- **Also fixed in `make_requirement`:** it created its backing Artifact with `artifact_type="requirement"` (lowercase). Production writes `"Requirement"` (`requirement_service.py:273`, and the dev DB has only PascalCase values). The catalog matches `allowed_pairs` on the exact string, so every fixture-built Requirement was unlinkable. Same class of divergence fixed in `test_audit_service.py` (`stakeholder-need`, `architecture-element`) and `test_trace_link_service_query_count_625.py`.
- `test_per_link_cost_does_not_grow_with_the_number_of_links` now warms the catalog cache before measuring: the first link in a process pays one extra query for `resolve_catalog`, which made the *first* link the expensive one and read the assertion backwards.

**Tests:** `application/ tests + traceability/ + link_types/` — **2003 passed, 1 failed** (see known-red below). `application/tests/test_trace_link_catalog_validation.py` 12 passed; `test_trace_link_service.py` + `test_allocation.py` + `test_trace_link_service_query_count_625.py` 78 passed (baseline before the change: 65 passed, all green). `rest_api/ mcp_server/ diagram/ icd/` re-run after the fixes: only the known-red list below plus the pre-existing `test_mcp_api_key_roles` "maximum of 10 active API keys" failures (red before this task, unrelated).

**Live-verified against the dev database** (not just green tests), via `manage.py shell` with `app.current_tenant` armed:
- legacy (migration-`0004`) workspace: all four grandfathered pairs accepted; `verifies Risk→Requirement` rejected with the allowed list; `diagram-ref` rejected as system-managed on the manual path; `satisfies` rejected as an unknown type.
- **brand-new tenant provisioned exactly the way production does it: all four grandfathered pairs REJECTED**, `verifies TestCase→Requirement` accepted. This is the Task-10 landmine, reproduced. Probe tenant rolled back.

**KNOWN-RED, handed to Task 16 / Task 17 (retired link-type literals in production code — Task 17's Step-1 test is a repo-wide grep for exactly these):**
- `application/tests/test_migrate_se_docs.py::test_migrate_sets_hierarchy_trace_links_and_is_idempotent` — `migrate_se_docs.py:205` still writes `implements`. The command degrades gracefully (logs "creation failed … skipped"); only the assertion fails. The fix is not a literal swap: `implements` → `allocated-to` also flips the §3 endpoint orientation (`SWAPPED_LEGACY_KEYS`), which is the orientation decision Task 17 owns.
- `mcp_server/tests/test_ai_derivation_tool_group.py::test_derive_risks_from_architecture_write_mode_persists_risks_and_traces` — `mcp_server/tools/ai_derivation.py` writes `LinkType.TRACES.value` for ArchitectureElement → Risk. The catalog's successor is `mitigates` with the endpoints reversed (Risk → ArchitectureElement); that is a semantic call, not a rename. **Note: `ai_derivation.py` is not in Task 17's file list — add it.**
- `mcp_server/tests/test_e2e_all_tools.py` / `test_e2e_audit.py` `[architecture.link]` — the e2e param table pins `link_type: "satisfies"`.
- `rest_api/tests/test_tracelink_outdated_endpoints.py` (3 tests) — links Requirement → Adr with `documents`. **Structural finding for Task 16/17: after the rename no built-in type puts an `Adr` on the *target* side at all** (`decides` is `Adr → *`; `references` targets are GlossaryTerm/Diagram/Icd plus the grandfathered `Adr → ArchitectureElement`). The test asserts `target_is_outdated` on the deleted ADR, so it cannot be repaired by swapping endpoints — the replacement type for Requirement↔Adr has to be decided.
- `rest_api/tests/test_tracelink_cascade_484.py::test_trace_links_survive_an_issue_soft_delete_and_reactivate` — still writes `traces` for an Issue-link; the parallel Risk case was migrated to `mitigates`, but Issue was left behind. **Genuine catalog gap:** `Issue` appears on neither side of any built-in type, making this the eighth legacy-literal case. Same class of issue as the 7 above.
- ~~`mcp_server/tests/test_traceability_link_issue264.py` (3 Goal tests) — `traces` Goal ↔ Requirement. Blocked by the open decision below, not by a literal.~~ **FIXED 2026-09-09** by the Option-(c) Hybrid resolution below (green).

---

### ~~OPEN DECISION (Task 11)~~ — RESOLVED 2026-09-09: **Option (c) Hybrid**

**Resolved by the user on 2026-09-09.** Original question: is grandfathering legacy-data amnesty or catalog policy? It was not covered by OFFENE FRAGE 1 or 2 and decided whether the flip is a silent feature regression.

**The decision, in two halves:**

1. **The 4 grandfathered triples stay LEGACY-ONLY** — `link_types/grandfathered.py` + migration `0004` only, deliberately *not* folded into `BUILTIN_LINK_TYPES`. A brand-new tenant does not get them, and that asymmetry is intended: those pairs exist because rows exist, not because the shape is wanted. Re-typing them is Task 16's job (see the sanity check below, which found a successor for 3 of the 4).
2. **Goal / MainGoal / Interview become REGULAR built-ins.** They are a shipped, tested feature (fix #237) with no legacy rows to grandfather, so `references` gained six pairs — `* → Goal`, `Goal → *`, and the same for `MainGoal` and `Interview` — plus a backfill migration for already-seeded tenants.

**Rationale for the split:** grandfathering answers "what data already exists"; the built-ins answer "what the product supports". Goal/MainGoal/Interview links are the second question, not the first — the inventory found no rows only because no seeder writes them, not because the feature is dead.

#### Sanity check on the 4 grandfathered triples (asked for explicitly, 2026-09-09)

Question: are these historical mis-mappings, or legitimate patterns that were wrongly demoted? Verdict — **all four are legacy-only-appropriate, but one carries a data-corruption risk for Task 16 and one is a real catalog gap.**

| triple | verdict | evidence |
|---|---|---|
| `allocated-to` StakeholderNeed → Requirement | **mis-mapping, and dangerous** — see below | the canonical relation is `derives-from` Requirement → StakeholderNeed (`docs/MIGRATION_SE_DOCS.md:159`, `docs/SYSTEMAUDIT_2026-09-02_GROB.md:897`), already a built-in pair. `docs/se/workspace_modes_er_model.md:124` pins `allocated-to` as "nur Req/Arch→Arch" — the target is always an ArchitectureElement. |
| `references` Adr → ArchitectureElement | mapping artifact | `decides` (`Adr → *`) is a built-in that covers it exactly. `seed_toothbrush.py:391` writes `documents`, which the key-level mapping table sends to `references` instead. |
| `references` Risk → Requirement | mapping artifact | `mitigates` (`Risk → Requirement`) is a built-in that covers it. `seed_toothbrush.py:358` writes the generic `traces`; whether "risk relates to" is a mitigation is a semantic call for Task 16, but a successor exists. |
| `references` Issue → ArchitectureElement | **genuine catalog gap** | `Issue` appears on neither side of any of the eight built-in types. This is the only one of the four with no successor at all, and a fresh tenant therefore cannot create *any* Issue link. |

**⚠ Load-bearing finding for Task 16 — `SWAPPED_LEGACY_KEYS` will corrupt 40 rows.** `satisfies` had two legitimate endpoint shapes in the old SE matrix (`(ArchitectureElement, Requirement)` **and** `(Requirement, StakeholderNeed)`), but `SWAPPED_LEGACY_KEYS` is *key*-level: the plan's migration (plan lines 4873-4922, explicitly irreversible) swaps every `satisfies` row. For the 40 `Requirement --satisfies--> StakeholderNeed` rows `seed_toothbrush.py:227` writes, that produces `StakeholderNeed --allocated-to--> Requirement`, which is:
- semantically inverted (the documented relation is `derives-from` Requirement → StakeholderNeed), and
- **coverage-poisoning**: `allocated-to` is the one `coverage_relevant: True` type besides `verifies`, so 40 phantom allocation edges would inflate Allocation-Coverage, and its `source_change_flags_target` suspect rule would flag Requirements suspect through the wrong relation.

Task 16 must branch on the *endpoint types*, not just the key: `satisfies` with a StakeholderNeed target → `derives-from`, endpoints **unswapped**. Flagged, not fixed here (Task 16 owns the data migration).

**Still open, inherited by Task 16/17:** the `Adr`-as-target gap named in the KNOWN-RED list, and the `Issue` gap in the table above. Both are "which built-in type should own this relation", the same class of question, and neither is unblocked by this decision.

#### What was implemented for the decision (2026-09-09)

- `link_types/builtin.py` — `references.allowed_pairs` gained the six Goal/MainGoal/Interview pairs, with a comment stating they are regular built-ins and pointing at `grandfathered.py` for the legacy-only four. Wildcards on **both** sides because no production code writes these links: the user picks both endpoints through the generic trace-link REST/MCP surface, in either direction (which is exactly what `test_traceability_link_issue264.py` pins — Goal as source *and* as target).
- `link_types/migrations/0005_backfill_goal_reference_pairs.py` — **needed**, and the propagation mechanism does not cover it: `BUILTIN_LINK_TYPES` is read only at *provisioning* time (`0003` / `provision_workspace_link_types`) and workspace rows are materialized copies (`catalog.resolve_catalog` does no merge-on-read), so extending a built-in in code leaves every seeded row behind. Same shape as `0004`: `is_customized=False` rows only, `app.current_tenant` armed per tenant, helper pair duplicated rather than imported so a squash of an earlier migration cannot break it.
- `link_types/tests/test_backfill_goal_reference_pairs.py` (new, 4 tests) — the merge is additive, idempotent and respects `is_customized`; one test pins that the migration's wanted-pair set really comes from the built-in.
- `link_types/tests/test_builtin.py` — `test_references_targets_are_a_list_not_a_fixed_triple` no longer pins the exact triple (it now checks the reference-entity half is append-only and order-stable); new `test_goal_main_goal_and_interview_are_reference_endpoints_in_both_directions`.
- `link_types/tests/test_inventory_command.py` — `test_a_goal_target_is_reported_as_uncovered` → `test_an_issue_source_is_reported_as_uncovered`. Goal can no longer serve as the uncovered specimen (it is covered now, which the test's second assertion pins); `Issue → ArchitectureElement` takes over, being the one triple with no built-in successor.
- `mcp_server/tests/test_traceability_link_issue264.py` — the 3 Goal tests moved from `LinkType.TRACES.value` to `LinkType.REFERENCES.value`. Same class of edit Task 11 already made in this file; cycle detection is per `link_type`, so Befund C still reproduces.

**Live-verified against the dev database** after `manage.py migrate link_types` (owner role): all 4 probed workspaces across 3 tenants have 12 `references` pairs (3 reference entities + 6 new + 3 grandfathered), `references Goal→Requirement`, `Requirement→Goal` and `Requirement→MainGoal` accepted, `Requirement→Foo` still rejected with the allowed list.

**Tests:** `mcp_server/tests/test_traceability_link_issue264.py` 12 passed (was 9 passed / 3 failed), `link_types/` 46 passed.

---

### Original text of the decision, for the record

**Blocking:** nothing in Phase B mechanically, but it decides whether the flip is a silent feature regression. Not covered by OFFENE FRAGE 1 or 2.

**Checked against the plan text first, as required:** the plan does **not** resolve this. Task 11 (lines 3191-3489), Task 10 (2979-3189), OFFENE FRAGE 1 (lines 74-84) and Decisions 6/7 were read in full. OFFENE FRAGE 1 only promises "existing data stays valid"; Decision 7 says "the migration backfills existing tenants, `provision_workspace_defaults` serves new ones" without ever asking what the new ones should be seeded *with*. `grandfathered.py`'s own framing ("the pair is allowed because it already exists") leans legacy-only, and Decision 6 shows the permanent-policy route is a `BUILTIN_LINK_TYPES` edit plus a migration — but neither is stated as a decision, and neither considers the consequence. **It is a real gap, so nothing was decided here.**

Two independent symptoms of the same question:

1. **Tenant asymmetry (the Task-10 landmine, now measured).** A legacy tenant accepts `references Adr→ArchitectureElement`, `references Issue→ArchitectureElement`, `references Risk→Requirement` and `allocated-to StakeholderNeed→Requirement`; a brand-new tenant rejects all four. `seed_toothbrush` writes links of exactly these shapes, so the app's own seeder cannot run in a fresh tenant.
2. **`Goal` / `MainGoal` / `Interview` links are now uncreatable everywhere.** OFFENE FRAGE 1 named these four types explicitly; the inventory found no `TraceLink` rows for them, so "do not guess the contents" left them out — and the flip now rejects them in *every* tenant. `Goal ↔ Requirement` is a shipped feature (fix #237 exists solely to make it work) with three regression tests in `test_traceability_link_issue264.py`.

**The three options, in ascending order of commitment:**
- **(a) Grandfathering is permanent policy.** Fold `GRANDFATHERED_PAIRS` into `BUILTIN_LINK_TYPES` (the route Decision 6 documents) so new tenants get them too. Removes the asymmetry; does not address Goal/MainGoal/Interview, which have no pairs at all.
- **(b) Grandfathering is legacy-only amnesty, and the asymmetry is intended.** Then the app's own seeder, and any customer starting fresh, must stop producing those shapes — a data-cleanup task, and `seed_toothbrush` needs fixing before the flip is safe.
- **(c) The eight built-ins get real pairs for the four uncovered artifact types** (e.g. `references *→Goal`, `references Goal→*`), making the catalog describe what the app actually supports rather than what the spec's matrix listed.

Whichever is chosen, the `Adr`-as-target gap from the known-red list above belongs in the same decision.

## Phase C — `TraceLink` extension and the suspect engine

Task 12: `TraceLink.rationale` / `suspect_flagged_at` / `suspect_source_change` and `Artifact.copied_from` — **done**

**Status:** Commit f4b6d3f2, 2026-09-09. All three `TraceLink` semantics fields + `Artifact.copied_from` self-FK implemented per plan spec. Migration 0080 generated and verified.

- `TraceLink.rationale` (TextField, default=""), `TraceLink.suspect_flagged_at` (DateTimeField, null=True, db_index=True), `TraceLink.suspect_source_change` (UUIDField, null=True — deliberately no FK, audit_entry is append-only and slated for RANGE partitioning; Decision 1 in the plan).
- `Artifact.copied_from` (Self-FK, related_name="copies", SET_NULL) — replaces the retired `copy-of` link-type as a 1:1 field, stating the "one origin" invariant.
- `Workspace.decomposition_link_type` default changed `parent-child` → `decomposes` (per the plan's 8-core-type scope).

**Code-review findings (optional, not blocking):**
1. **Serializer/View `parent-child`-Fallback (Task 17, deliberate):** `rest_api/serializers.py:1311` + `rest_api/views.py:4162` still have explicit `"parent-child"` fallback logic in their defaults. Not touched here; Task 17 (consumer sweep) will eliminate both. No new regression — both are dead code paths now that the catalog rejects `parent-child` everywhere.
2. **`copied_from` lacks tenant validation (Task 16 design question):** `Artifact.copied_from` is a self-FK with no `tenant` constraint, matching `Artifact.parent` (also unconstrained). Correct per analogy to existing patterns, but `Task 16`'s data migration will need to decide whether cross-tenant copies are audit events or a data-integrity error. Scope: this task only builds the schema; no existing `copy-of` rows exist to migrate (they are pure trace links, handled by Task 16).
3. **Non-concurrent indices in migration 0080 (noted for scale):** `suspect_flagged_at` has a simple `db_index=True`. The plan (lines 4717–4725) notes "performance gains" but does not prescribe compound indices or covering indices. At current volume they are unnecessary; if workspace-scale queries on `(workspace_id, suspect_flagged_at)` become a bottleneck, `Task 16` or Task 14's suspect-propagation loop can add them. Recorded so a scale-up does not forget this field exists.

**Tests:** `backend/persistence/tests/test_tracelink_semantics_fields.py` — 6 passed. Full regression (`persistence/ application/tests/test_trace_link_service.py`) — no new failures.

**KNOWN-RED unchanged:** the 8 pre-existing failures from Task 11's KNOWN-RED list remain; Task 12 introduced no new regressions.

Task 13: Expose the new fields through the REST serializer — **done**

**Status:** Commit 861353c0, 2026-09-09. TraceLinkSerializer fields wired; rationale and suspect markers exposed on all REST read/write paths.

- `rest_api/serializers.py:TraceLinkSerializer` added `rationale`, `suspect_flagged_at`, `suspect_source_change` fields; all three read-only on output, `rationale` writable on create/update.
- `rest_api/views.py:TraceLinkViewSet`: `_tracelink_to_dict()` includes the three new fields; `?artifact_id=` branch synchronized; `create()` accepts and passes `rationale` to service layer.
- `application/trace_link_service.py`: `create_trace_link` stores `rationale` in one call; `update_trace_link` handles rationale updates; query paths (`get_trace_link`, `get_trace_links_for_artifact`) return all three fields.
- `traceability/services.py`: trace_link_manager layer propagates rationale through; no breakage on the Layer-1 / Layer-2 seam.
- Tests: fixture-level + end-to-end REST round-trip coverage; 2 review rounds (Runde 1: fields were inert; Runde 2: approved after fix).

**OPTIONAL Findings (not blocking, for later tasks):**

1. **Defensive `getattr(tl, "rationale", "")`** at 2 places in views.py — guards against a shape that cannot occur today (all trace links are fetched via ORM or service, never hand-constructed). Relevant only if a `.only()`-projection is introduced later that excludes the field. Mark as technical debt, not a bug.

2. **Dict-Baustelle DRY-Verstoß:** `_tracelink_to_dict()` and the `?artifact_id=` branch duplicate 6 keys (`link_type`, `source_artifact_id`, `target_artifact_id`, `rationale`, `suspect_flagged_at`, `suspect_source_change`). Consciously left as-is per #512 (endpoint echo contract) and now test-covered; consolidation would require refactoring the contract first.

3. **Rationale bound at REST layer only:** `max_length=2000` gates the field at the serializer (`rest_api/`), but Layer-2 service callers (`application/`, `traceability/`) write unbounded. Relevant when Task 21 (MCP layer) exposes rationale — add a service-layer validation gate if MCP tools need the same 2000-char limit.

**Tests:** `rest_api/tests/test_tracelink_rest_semantics.py` — 8 passed. Regression (`rest_api/ application/tests/test_trace_link_service.py traceability/`) — no new failures. KNOWN-RED list unchanged (8 tests from Task 11).

Task 14: Rule-driven suspect propagation (closes #849 structurally) — **done**

**Status:** Commit ae934685, 2026-09-09. Suspect-Propagation vollständig regel-basiert (One-Hop-Dispatch statt transitiver Hülle).

- `application/trace_link_service.py`: `propagate_suspect_status` komplett neu — regel-basiertes Dispatch über den Link-Type-Katalog (`link_type.suspect_rule`), neuer optionaler Parameter `audit_entry_id`, One-Hop statt transitive Hülle. Keine globale `SUSPECT_PROPAGATION_MAX_DEPTH` mehr.
- New `application/tests/test_suspect_propagation.py` — 12 tests für die neue Logik (One-Hop-Dispatch pro Link-Type-Regel, Edge-Cases).
- Refactor in `test_trace_link_service.py` — 4 alte SN-30-Tests durch 1 ersetzt (Konsolidierung der redundanten alte-Transitiv-Tiefe-Tests).
- Tests: regression (`application/tests/test_trace_link_service.py`, `test_suspect_propagation.py`) — 13 passed. Full suite trace_link_service + suspect — green.

**OPTIONAL Findings (nicht blocking, für künftige Tasks):**

1. **Silent-Skip-Fall hinterlässt falschen Audit-Marker** — wenn ein Modelltyp nicht flaggbar ist (z.B. `Adr` in einem Workspace ohne `Adr`-Support), werden `TraceLink.suspect_flagged_at`/`suspect_source_change` trotzdem gestempelt, obwohl `flagged == 0` zurückgegeben wird. Sollte zusammen mit der geplanten `Artifact.suspect`-Verschiebung adressiert werden (siehe unten).

2. **Veraltete Doku-Referenz** — `docs/superpowers/plans/2026-08-08-reqmd-interop-and-inspiration-concept.md:773` referenziert das jetzt komplett ungenutzte `SUSPECT_PROPAGATION_MAX_DEPTH`. Bereinigung notiert für spätere Doku-Cleanup-Runde.

**Merkposten für künftige Datenmodell-Konsolidierung (Task 16 / Phase D):**

`suspect` gehört semantisch auf `Artifact` (nicht verteilt auf Requirement/ArchitectureElement/TestCase/StakeholderNeed einzeln). Das Drei-Modell-Tupel in Task 14 existiert nur, weil die Spalte noch nicht auf `Artifact` sitzt. `StakeholderNeed` hat ebenfalls ein `suspect`-Feld, fehlt aber im Propagations-Tupel — das ist bewusst deferred auf diese künftige Datenmodell-Konsolidierung, **KEINE Regression** (der alte Code hatte exakt dasselbe Drei-Modell-Tupel). Diese Verschiebung würde auch das Silent-Skip-Fall-Problem (Punkt 1 oben) beheben.

Task 15: Write `Artifact.parent` in the same transaction as the `decomposes` link — **done**

**Status:** Commit f20287a9, 2026-09-09. Atomic write of `Artifact.parent` and `decomposes` link merged.

- Try/except around `decomposes` link creation in `requirement_service.py` removed; errors now propagate, and the existing transaction rolls back both `Artifact.parent` and `TraceLink` together.
- Review approved; no REQUIRED findings.

**OPTIONAL Merkposten for Task 16/17 (not blocking, from review):**

1. **MCP `_handle_decompose` (mcp_server/tools/requirements.py) does not explicitly catch `ValidationError`** (sibling `_handle_derive` does) — but lands safely in the outer `INTERNAL_ERROR` fallback, no crash. Same pattern existed *before* this task (not a regression). Severity: low, matches exception-handling convention elsewhere in mcp_server.
2. **Git stash noted in review** — manual verification confirmed not byte-identical with current state (contains only changes to existing files, not the new test file). Deliberately not dropped; local stash is harmless, no action needed.

**Tests:** Phase C (Tasks 12-15) complete, regression suite green. KNOWN-RED unchanged (8 pre-existing from Task 11).

---

**Phase C (Catalog foundation + semantics fields + suspect engine) is complete** — Tasks 12-15 all done.

## Phase D — Hard data migration and consumer fixes

**⚠ CRITICAL — Task 16 SWAPPED_LEGACY_KEYS risk (highlighted 2026-09-09):** 
`satisfies` rows with a `StakeholderNeed` target **must** migrate to `derives-from` *unswapped* (endpoints reversed), **not** to `allocated-to` swapped. Otherwise 40 seeded rows get inverted semantics + Allocation-Coverage poisoning (coverage_relevant flag + wrong suspect-rule chain). Decision evidence and full rationale in the RESOLVED DECISION (Task 11) and Task 10 blocks above — read before starting the migration.
**✓ VERIFIED AND FIXED 2026-09-10 (Commit 9f885ed6)** — three independent probes confirmed the SWAPPED_LEGACY_KEYS mis-orientation existed (`grandfathered.py:33`, `seed_toothbrush.py:227`, git-history `a1800903`). The migration correctly branches on *endpoint types*, not just keys: `satisfies` with `StakeholderNeed` target → `derives-from` unswapped; all other `satisfies` rows → `allocated-to` swapped as documented. Post-condition verification via new function `verify_migrated_links` (atomic migration with rollback check). **Risk resolved.**

Task 16: Migrate every existing `TraceLink` row to the new type set — **done**

**Status:** Commit 9f885ed6, 2026-09-10. Hard data migration complete. Migration: `backend/persistence/migrations/0081_migrate_trace_link_types.py`. Dependencies: persistence/0080 + link_types/0005 (not the placeholder versions in plan text).

- Two review rounds: Runde 1 changes-requested (missing post-condition verification; illegal endpoint pairs could silently write), Runde 2 approved after new `verify_migrated_links(...)` function added (raises RuntimeError on violations, migration atomic=True, rollback verified).
- The SWAPPED_LEGACY_KEYS risk above proved real and was fixed in-place: endpoint-type branching for the 40 Requirement→StakeholderNeed rows, unswapped to `derives-from`, all others swapped to `allocated-to` as documented.
- Two optional findings from Runde 1 (logging precision: rewritten-vs-dropped distinction, dead code branch) addressed in Runde 2.
- Migration run only in isolated test-DB context (not applied to dev DB — that is a separate deployment step outside this SDD session scope).
- `makemigrations --check --dry-run` clean; no spurious migrations generated.

**Two follow-ups for Task 17 (noted explicitly for grep-safety):**
1. `link_types/grandfathered.py:33` — `GRANDFATHERED_PAIRS["allocated-to"]["StakeholderNeed"→"Requirement"]` is now dead code (migration handled the fork). Task 17 can clean it up (no behavioral impact).
2. `backend/vcrm_report_generator.py:205` — still filters on retired literal keys `satisfies`/`implements` and returns silent null rows post-migration. Task 17 must change to `allocated-to` (one-literal fix, also repairs the column as plan text names).

Task 17: Move every hardcoded link-type consumer with the migration — pending

**Next step:** Start Task 17 once this ledger is recorded. Grep for remaining retired literals is the safety gate (repo-wide, incl. `ai_derivation.py` which is missing from the plan's Task-17 file list — add it).
Task 18: Verify the SE-Auditor finding set before and after (OFFENE FRAGE 2) — pending

## Phase E — REST and MCP surface

Task 19: `LinkTypeFacade` — the Layer-2 seam (ADR-01) — pending
Task 20: REST endpoints for global defaults and workspace overrides — pending
Task 21: MCP `link_type.*` group and the free-string `create_link` schema — pending

## Phase F — Frontend

Task 22: `link-types` API wrapper, types and context — pending
Task 23: Catalog-driven labels, dialog filtering and workspace settings — pending
Task 24: `LinkTypeEditorPage` — pending

## OFFENE FRAGEN — blocking decisions with plan defaults

### OFFENE FRAGE 1 — Always-on validation breaks link types the seeded catalog does not mention

**Blocking for:** Task 9 / Task 10

**Plan default:** *Grandfathering by inventory* (docs/superpowers/plans/2026-09-03-traceability-semantik.md, lines 76–82)

A management command inventories the distinct `(link_type, source_artifact_type, target_artifact_type)` triples that actually exist, maps them through the 3.1 rename table, and the seed migration **extends** the built-in `allowed_pairs` with every observed triple not already covered — logging each addition loudly. Existing data stays valid; genuinely new invalid combinations are rejected.

**Decision:** Used documented plan default, not re-litigated.

**APPLIED in Task 10 (2026-09-09) — no longer blocking.** Evidence: two live `inventory_link_types` runs (dev DB: 2 rows / 0 uncovered; scratch DB seeded with `seed_demo` + `seed_toothbrush`: 1974 rows / 4 uncovered). The 4 uncovered triples — `allocated-to` StakeholderNeed→Requirement (40 rows, from legacy `satisfies`), `references` Adr→ArchitectureElement (12, from `documents`), `references` Issue→ArchitectureElement (55, from `traces`), `references` Risk→Requirement (22, from `traces`) — are in `link_types/grandfathered.py` verbatim, as exact pairs rather than wildcards. Goal / MainGoal / Interview had no `TraceLink` rows in either database and were therefore **not** added ("do not guess the contents"). See the Task 10 entry above for the full record.

---

### OFFENE FRAGE 2 — `refines` → `derives-from` changes SE-Auditor root/leaf classification

**Blocking for:** Task 16 / Task 17

**Plan default:** Migrate as the spec says (direction preserved: source stays source), but the migration **counts and reports** every `Requirement→Requirement` `refines` row it converts, and Task 17 re-runs the SE-Auditor before/after on a seeded workspace and diffs the finding set. (docs/superpowers/plans/2026-09-03-traceability-semantik.md, lines 86–92)

**Decision:** Used documented plan default, not re-litigated.

---

## Branch status: IN PROGRESS — **Phase A complete (Tasks 1-8). Phase B complete: Tasks 9-11 done. Phase C complete: Tasks 12-15 done. Phase D (hard data migration) in progress: Task 16 done, Tasks 17-18 pending.**

Validation is always-on: `link_types.catalog.validate_link_pair` is the sole authority for every trace link in every workspace and terminology profile. `TraceLink` schema extended with three semantics fields + `Artifact.copied_from` self-FK. Suspect-propagation is rule-driven via link-type catalog. Hard data migration complete (Task 16, commit 9f885ed6, 2026-09-10); SWAPPED_LEGACY_KEYS risk verified and fixed.

**Next: Task 17 (Move every hardcoded link-type consumer with the migration).**

Before starting Task 17, review the **two follow-ups noted in Task 16** (dead code cleanup in grandfathered.py, literal swap in vcrm_report_generator.py) and the **KNOWN-RED** list in the Task 11 entry — **8 tests remain red** on retired link-type literals in production code. Five file groups: `migrate_se_docs.py` (1), `mcp_server/tools/ai_derivation.py` (1), e2e param tables (2 tests), `test_tracelink_outdated_endpoints.py` (3), `test_tracelink_cascade_484.py` (1 — Issue catalog gap, added 2026-09-09). The 3 Goal tests are no longer among them.

**File-list gap for Task 17 (no fix attempted in Task 16):**
- `backend/mcp_server/tools/ai_derivation.py` is **missing from Task 17's file list** in the plan. It writes `LinkType.TRACES.value` for ArchitectureElement → Risk (line 638) and names `traces` in two docstrings/schema descriptions (lines 32, 339). Its catalog successor is `mitigates` with the endpoints reversed (Risk → ArchitectureElement) — a semantic call, not a literal swap. Add the file to the list when Task 17 starts; noted here because Task 17's Step-1 test is a repo-wide grep that would catch the literal but not the missing file entry.
