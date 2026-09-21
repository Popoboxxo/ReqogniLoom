# Open-Issues-Bundle 2026-09-21 — Cluster/Sequencing-Plan

> **For agentic workers:** This is a CLUSTER/SEQUENCING plan, not a low-level TDD plan.
> Root causes below were verified by reading the issue bodies and the cited `file:line`
> locations against the real ReqogniLoom source at `main` @ `e11140d6`. Where a cluster
> has multiple independent tasks, each is its own commit; where a task is a bug whose
> root cause is *not* yet code-verified, the implementer MUST run
> **superpowers:systematic-debugging** before writing a fix, then
> **superpowers:test-driven-development**. Do not guess a fix from the symptom text.

**Goal:** Process the currently open, independently-scoped findings in one coordinated
bundle — 40 open GitHub issues, of which 27 are actionable and grouped into 7 clusters.
The remaining 13 are deliberately dispositioned out (see "Deliberately out of scope").

**Cluster shape:** Each cluster is one branch, one PR, one test cycle. Clusters with
disjoint file sets *could* run in parallel, but per this host's RAM constraint
(~5.8 GiB, OOM on parallel backend+frontend+E2E) test runs are serialized.

**Spec:** No new spec — each task cites its source issue number. Cluster 5 and 6 change
the data model and therefore DO need a `concept-specifier` pass before implementation.

## Global Constraints

- Branch-Policy: `fix/*` for bug clusters, `feat/*` for model/epic clusters, `chore/*`
  for test-infra — never on `main` (`.claude/rules/branch-guard.md`).
- Commit messages MUST reference the issue they fix (`Fixes #NNN` / `Closes #NNN`) per
  `.claude/rules/issue-lifecycle.md`. Closing a GitHub issue runs via
  `gh issue close <n>` — a read/write GitHub operation, not a local git mutation.
- DoD-Preset is `rapid-prototyping` (no REQ-Traceability/Security-Audit gate required),
  but Conventional Commits + no-regressions still apply (`.opencode/skills/dod-criteria`).
- Backend tests: override `DB_USER` to the superuser locally, or every RLS test errors
  out (known project constraint).
- Frontend ratchets: every frontend-touching cluster MUST re-measure and **lower**
  (never raise) `frontend/src/test/i18n-parity.test.ts` `MISSING_KEY_BASELINE` and
  `frontend/src/test/ui-ratchet.test.ts` hex/inline-style baselines, per those tests'
  own documented convention.
- `data-testid` on every new/modified interactive element (E2E-required project rule).
- CSS Custom Properties from `styles/tokens.css` only — no new hardcoded colours/sizes.

---

## Cross-Reference: open issues → cluster → action

| Issue | Finding | Cluster | Action |
|---|---|---|---|
| #1019 | Image-Deployment kann Nicht-384-Embeddings nicht per Env aktivieren | **C1** | fix, `Closes #1019` |
| #1018 | `--profile honcho` mit 768-Embedding startet nicht | **C1** | fix, `Closes #1018` |
| #1021 | TRACE-P1 verstummt bei zyklischer Hierarchie | **C2** | fix, `Closes #1021` |
| #569 | SE-Auditor: Findings unterdrücken (Waiver) | **C2** | shares stable finding-identity with #1021; implement separately, `Closes #569` |
| #988 | bluepencil bundle predates identity fix → `author: "anonymous"` | **C3** | re-vendor, `Closes #988` |
| #318 | Create-Trace-Link-Dialog native Selects schwer bedienbar | **C3** | fix, `Closes #318` |
| #319 | Inspector-Diff zeigt `v1 → v1` nach Status-Transition | **C3** | fix, `Closes #319` |
| #876 | 1.015 Inline-Styles + 74 Hex-Farben auf `tokens.css` | **C3** | fix, `Closes #876` |
| #947 | Playwright-Suite: Bootstrap-Vorbedingung + flaky Specs | **C4** | harden, `Closes #947` |
| #433 | Regressionstest für `tenant_id`-Prädikat in Bundle-CTE | **C4** | add test, `Closes #433` |
| #424 | KI-generierte TestCases unmarkiert | **C5** | model change, `Closes #424` |
| #402 | Validation layer (Goals) default-disabled, keine Goal-Regel | **C5** | model change, `Closes #402` |
| #399 | Baselines sperren Artifacts nicht; CRs gaten keine Edits | **C5** | model change, `Closes #399` |
| #272 | SE-Interview Top-5 (AC-Gate, Link-Typ-Enum, Pass/Fail, CR↔Baseline, Fixture) | **C5** | partially covered by #424/#399 — implement remainder |
| #1003 | ReqIF-Identität von lokaler `uid` trennen | **C6** | **blocks #932**; needs decisions (§4 of issue) first |
| #393 | MOE/MOP/TPM komplett absent (CRITICAL) | **C6** | new `Measure` entity — needs ADR |
| #879 | Projekt-Meilensteine (SRR/PDR/CDR) | **C6** | new entity |
| #801 | Inspector nur bei Requirements (6 Entity-Typen ohne Verlauf) | **C7** | UI, `Closes #801` |
| #934 | Epic Attribut-System v3 | **C7** | epic — route via existing branches, not this plan |
| #929 | Konzept 3-Stufen-Attributmodell | **C7** | child of #934 |
| #941 | Attribut v3 WS0 Fundament | **C7** | child of #934 |
| #587 | Promptfoo test infrastructure | **C7** | independent, low coupling |
| #426 | SE-Methodology audit index (parent) | — | **index/parent, never closed on its own** |
| #792 | RFC Deployment/Security/Ops | — | **input to C1, not a task** |
| #946, #987, #810 | debug annotation / notification placement / view modes | — | **blocked on user design decision** |
| #649, #598, #597, #92, #89, #85, #50, #39, #35, #29, #28, #27, #19, #18, #17, #378 | backlog/features/older QA | — | no current wrong behaviour; not in this bundle |

---

## Execution order

```
C1 (deploy/embedding — silent data corruption)  ─┐
C2 (SE-audit gate — false-green)                ─┴─► both first, independent PRs
        │
        ▼
C3 (frontend integrity)  ──►  C4 (E2E hardening)   ← disjoint files, sequential per host RAM
        │
        ▼
C5 (SE completeness — data model)  ──►  C6 (ReqIF identity + Measures)  ──►  C7 (Epic UI/attribute v3)
```

Each arrow = hard sequencing: the next cluster's implementer starts only after the
previous cluster's tests are green and the PR is merged or explicitly parked.

---

## Cluster 1 — Deploy/Embedding: stop silent data corruption

**Branch:** `fix/deploy-embedding-dimension` · **Issues:** #1019, #1018 · **Priority: Sofort**

**Why one cluster:** both findings share one root cause — the pgvector column width is
fixed at MIGRATE time (hard `384` for app tables, hard `1536` for Honcho) and there is
no supported path to set it from the Env in an image-based deployment. Same failure
class (Env → schema drift) in two services.

**Root cause (verified in issue bodies):**
- `backend/persistence/migrations/0069_align_embedding_dimensions.py` freezes
  `_TARGET_DIMENSIONS = 384`; `backend/persistence/embedding_dimensions.py` binds the
  env value at import time → the documented `makemigrations` path is not persistent in
  the image deployment (migration is written to the ephemeral container filesystem).
- `deploy/docker-compose.yml`: `honcho-migrate.command: alembic upgrade head` never runs
  `scripts/configure_embeddings.py` → Honcho stays `vector(1536)`.
- Consequence: `verify_embedding_dimensions` fails loudly, but in normal operation the
  embedding guard **silently skips writes** (768 from provider vs 384 column).

**Files:**
- Add: `backend/persistence/management/commands/align_embedding_dimensions.py` (new)
- Modify: `deploy/docker-compose.yml` (honcho-migrate command)
- Modify: `backend/reqogniloom/urls.py` or health view (`/health/` mismatch status)
- Modify: `deploy/README.md`, `.env.example`

**Tasks:**
1. Management command `align_embedding_dimensions`: idempotent, `docker exec`-callable,
   adjusts the 5 app columns to `EMBEDDING_VECTOR_DIMENSIONS`, reindexes the 5 HNSW
   indexes, warns explicitly about data loss on non-NULL cast (analogous to Honcho's
   `scripts/configure_embeddings.py`).
2. `honcho-migrate` → `command: sh -c "alembic upgrade head && python scripts/configure_embeddings.py"`
   (path/entrypoint to be verified against the Honcho image before use).
3. `/health/` reflects a dimension mismatch as its own status instead of only surfacing
   via `manage.py check` (W001) or a command output.
4. `deploy/README.md` + `.env.example`: document that in image deployment the
   `makemigrations` path is not persistent; correct the "Embedding-dimension pitfall"
   note (setting the Env before the first migration is NOT sufficient for Honcho).

**Test:** Fresh `up -d` with `EMBEDDING_VECTOR_DIMENSIONS=768` + `--profile honcho` →
`verify_embedding_dimensions` OK, `/health/` ok, frontend starts (no `503` /
`unhealthy` cascade). Regression without an env override → columns stay `vector(384)`.
`ALTER`-idempotency: running the command twice is a no-op the second time.

**Dispatch:** `senior-developer` (dev/prod deploy semantics, architecture-sensitive) →
`docker` agent for the boot verification → `code-reviewer` → `git` agent for
commit + PR (`Closes #1019`, `Closes #1018`).

---

## Cluster 2 — SE-audit correctness: the gate must not silence itself

**Branch:** `fix/se-audit-trace-p1-cycle` · **Issues:** #1021, #569 · **Priority: Sofort**

**Why one cluster:** #569 requires a *stable finding identity* ("Hash aus `rule_id` +
sortierten `artifact_ids` + `scope`"), which is exactly the prerequisite for #1021's
second half (a cycle/ambiguous-parent finding that survives re-audit). Shared
foundation, then separate implementation.

**Root cause (verified in issue bodies):**
- `backend/traceability/audit/hierarchy.py:132-144` — `root_requirement_ids()` computes
  `requirement_ids - child_ids`; a combined `decomposes` (PARENT→CHILD) **and**
  `derives-from` (CHILD→PARENT) link on the same object pair in the same direction
  creates a cycle → every node is a "child" → roots = ∅.
- `backend/traceability/audit/rules/trace_derivation_allocation.py:226-258` —
  `SystemRequirementDerivesFromNeedRule.check()` exits via `if not root_ids: return []`
  with **no finding** about the cyclic/ambiguous graph.
- The TraceLink layer blocks only *same-type* chains (400 `Cycle detected in decomposes
  chain`), not the PARENT_TO_CHILD/CHILD_TO_PARENT combination.
- `backend/application/audit_service.py` — findings are never persisted;
  `AuditFindingView.index` is a positional number within a run, unstable across runs.

**Files:**
- Modify: `backend/traceability/audit/hierarchy.py` (cycle detection)
- Modify: `backend/traceability/audit/rules/trace_derivation_allocation.py` (defensive P1)
- Modify: trace-link creation/validation path (reject the combined edge)
- Add: stable finding-identity helper (hash) — shared by #1021 and #569
- Add (from #569): suppression/waiver entity + migration (`TenantScopedModel` + `AuditableModel`)
- Modify: `backend/application/audit_service.py`, `backend/rest_api/audit_views.py`,
  `backend/mcp_server/tools/audit.py`
- Frontend: third action + "show suppressed" filter in the SE-Auditor

**Tasks:**
1. Link layer: reject the contradictory combined hierarchy/derivation edge with a clear
   400 message (evaluated against the PARENT_TO_CHILD/CHILD_TO_PARENT graph, not only
   same-type chains).
2. Auditor, defensive: when `root_requirement_ids()` detects a cycle, emit a dedicated
   finding and compute P1 against all cycle nodes instead of ∅.
3. Stable finding identity (hash of `rule_id` + sorted `artifact_ids` + `scope`),
   documented and tested across a re-audit.
4. (from #569) Suppression entity with mandatory rationale, author, optional expiry,
   plus audit-log entry; REST + MCP access through the Layer-2 facade.
5. Gate semantics (#490) explicitly decided and tested: suppressed findings do NOT count
   as blockers, but ARE recorded in baseline metadata (traceability, not hiding).

**Test:** Rerun the #1021 repro (MCP `audit.se_audit` + the two REST POSTs) → with the
cycle, TRACE-P1 still fires and a cycle finding appears; control case unchanged. A
waiver survives a re-audit; a blocker cannot be removed without rationale and audit
trail. Mutation probe: removing the cycle guard makes the new test fail.

**Dispatch:** `senior-developer` (audit semantics) → `tester` → `code-reviewer` → `git`
agent, `Closes #1021`; #569 in a follow-up commit on the same branch, `Closes #569`
only once the entity + UI + gate test are all green.

---

## Cluster 3 — Frontend integrity: bug, accessibility, token drift

**Branch:** `fix/frontend-integrity-dialog-selects` · **Issues:** #988, #318, #319, #876
· **Priority: Diese Woche**

**Why one cluster:** #318 (native Selects in the trace-link dialog) and #876
(inline styles / hardcoded hex) touch the same dialog/form primitives; #319 (inspector
diff) and #876 share the inspector. One test cycle, no file collisions between them.

**Files:**
- Modify: `frontend/public/bluepencil/latest/` (re-vendor) + `latest.json` SHA256
- Modify: trace-link create dialog component (`/traceability`) → accessible dropdown
- Modify: inspector diff version-comparison source (left side = baseline)
- Modify: `NavigationShell.tsx:130`, `RequirementEditors/*`, `WorkspaceSettings/*`,
  `CanvasEditor.tsx`, `WorkflowEditor.module.css` → tokens / CSS modules
- Tests: affected component tests + `ui-ratchet` + `i18n-parity` baselines

**Tasks:**
1. **#988** — re-vendor `frontend/public/bluepencil/latest/` from a bluepencil build
   that includes the upstream identity fix (#15, released with 0.1.0-alpha.1), keep
   `latest.json` SHA256 in sync, rebuild the frontend image. Verify: a note written by a
   logged-in user is stored with their name (host bridge in `frontend/src/bluepencil/host.ts`
   already exists); an exported bundle shows the app instead of `"unknown"`.
2. **#318** — replace the native `<select>` Source/Target pickers with the accessible
   dropdown widget already used in other dialogs; make the Create button state
   deterministic once both required fields are set (React `onChange` sync — verify with
   real mouse/keyboard, not programmatic value-set).
3. **#319** — inspector diff after the first status transition must compare baseline (v0)
   against current (v1), not current against itself.
4. **#876** — replace the 74 hardcoded hex colours with `tokens.css` variables
   (`--color-bg-surface`, `--color-text-primary`, …); migrate inline styles in
   `NavigationShell` and the forms into CSS modules. **Bound this task**: the issue's
   1.015 inline styles are a ratchet target, not a big-bang; lower
   `ui-ratchet.test.ts`'s baseline to the new measured count.

**Test:** `vitest run` (frontend) green; `ui-ratchet` + `i18n-parity` green with
lowered baselines; Playwright-MCP spot-check on dialog + inspector + light-theme canvas
(CanvasEditor must stay readable in Light/Sepia).

**Dispatch:** `frontend-component-engineer` (#318) and `developer` (#319/#876) in
parallel — disjoint files, file-affinity check first — then `ui-reviewer` +
`accessibility-specialist` spot-check, `tester`, `code-reviewer`, `git` agent. One
batched PR (`Closes #318`, `Closes #319`, `Closes #876`) with #988 as its own commit
(`Closes #988`) because it is a dependency/vendoring change with a different blast radius.

---

## Cluster 4 — E2E hardening & regression protection

**Branch:** `chore/e2e-hardening-and-tenant-guard` · **Issues:** #947, #433
· **Priority: Diese Woche**

**Why one cluster:** both are test infrastructure with no application-code change; the
same test run verifies both, and #433 is explicitly future regression protection.

**Files:**
- Modify: `README.md` (E2E section), `.github/workflows/playwright.yml`
- Modify: `e2e/tests/toothbrush-syseng.spec.ts:125`,
  `e2e/tests/waterkettle-fullblown.spec.ts:548,567`,
  `e2e/tests/needs-cross-boundary.spec.ts` (+ sweep generic selectors)
- Add: `make test-e2e-reseed` path (Makefile + docs)
- Add: `backend/application/tests/test_requirement_bundle_tenant_predicate.py` (new)

**Tasks:**
1. **#947.1** — `bootstrap_attribute_definitions` as a documented + CI-automated E2E
   precondition (currently `seed_demo` alone is insufficient; all editor specs fail
   without 132 global definitions).
2. **#947.2** — decouple `toothbrush-syseng.spec.ts:125` from the start state (take the
   next allowed transition, assert the actual target state regardless of start state).
3. **#947.2** — make `waterkettle-fullblown.spec.ts` phase 4c/4d idempotent (fresh seed
   or stable state) so multi-runs stop accumulating state.
4. **#947.3** — replace remaining generic selectors (`locator('select')`,
   `locator('textarea')`, text matches) with `data-testid`/scoped locators.
5. **#947.4** — document that the suite is designed for "seed once → run once" and add a
   `make test-e2e-reseed` convenience path.
6. **#433** — regression test for the `tenant_id` defense-in-depth predicate in
   `backend/application/requirement_bundle_service.py` (`_ARCH_TREE_CTE` and its two call
   sites): two tenants, each with their own `ArchitectureElement`/`Requirement`/
   `ALLOCATED_TO` data; a query scoped to tenant A never returns tenant B's rows even
   where RLS *alone* might not isolate (mock/bypass RLS in the test, or assert the
   predicate's presence at SQL-string level). Mutation probe: neutering the predicate to
   `%s::uuid IS NOT NULL` must make the test fail (the current state gives "51 passed,
   nothing fails").

**Test:** `npx playwright test` on a fresh seed green; a second run (no reseed) no longer
deterministically red for the two named specs; the new #433 test fails when the predicate
is removed.

**Dispatch:** `e2e-tester` (#947) and `tester` (#433) in parallel (disjoint files) →
`code-reviewer` → `git` agent, `Closes #947`, `Closes #433`.

---

## Cluster 5 — SE completeness: validation as a first-class pillar

**Branch:** `feat/se-validation-completeness` · **Issues:** #424, #402, #399, #272
· **Priority: Bald**

**Why one cluster:** all four are findings from the same SE-methodology audit
(2026-08-07) / SE interview (#272) and act on the same actors
(Requirement/TestCase/Baseline/CR/Goal). #272 already consolidates four of the points.
Data-model changes → `concept-specifier` first.

**Files:** TBD after the spec pass. Expected touch points:
- `backend/persistence/models.py` (TestCase origin/reviewed; Goal defaults; Baseline↔CR)
- New migrations under `backend/persistence/migrations/`
- `backend/application/` services (test-case creation path, baseline edit path,
  change-request service `change_request_service.py:571-625`)
- `backend/traceability/audit/rules/` (new goal-coverage rule; off-nominal category)
- Frontend: TestCase AI marker, baseline drift badge, AC gate on `in_review → approved`
- `backend/management/commands/seed_demo.py` (realistic demo fixture)

**Tasks (each its own commit):**
1. **#424** — TestCase gains `origin ∈ {ai_generated, manual}` + `reviewed: bool`; UI
   shows a visible marker; the coverage calculation treats unreviewed AI test cases
   separately (never as ordinary coverage — this is a false-green path).
2. **#402** — check/enable `goals_enabled` default; add the audit rule "every L0 need
   contributes to at least one goal"; add an off-nominal category for requirements/test
   cases so validation becomes usable as a pillar next to verification.
3. **#399** — couple baseline membership to change control: a baselined artifact can only
   be changed via an approved ChangeRequest, or at minimum gets a clear drift marking.
   Decide and test the interaction with the existing `change_reason` preset policy (that
   is a justification duty, not an approval).
4. **#272** — the remainder not covered by 1–3:
   - AC-Gate at `in_review → approved` (acceptance criteria + `verification_method` mandatory),
   - **Link-type gap analysis first**: #272 asks for a link-type enum + type-compatibility
     rules; `backend/link_types/builtin.py` already has 11 built-in types — do NOT rebuild,
     instead add the compatibility rules (`verifies` only Req→TestCase, `allocated-to` only
     Req→ArchElement) and validation against deleted artifacts,
   - TestResult schema with enum (`passed/failed/blocked/not_run`) + executed_at/by +
     documented close-time aggregation rule + Requirement→Test coverage report,
   - CR gains `affected_items` (before/after versions) + CR↔Baseline reference,
     `content_available` for all versions (v0 Creation baseline currently `false`),
   - realistic demo fixture (3–5 needs → 20–30 requirements with metrics/AC → 2-level
     architecture → test cases → test runs → baseline → CR).

**Test:** One test per task where the issue names a concrete behaviour; a fresh
`seed_demo` produces a walkable full chain; an artifact with empty AC cannot reach
`approved`; an AI-generated test case is visibly distinct and does not count as full
coverage until reviewed; a baselined artifact edit is blocked or drift-marked.

**Dispatch:** `concept-specifier` (M–L: data-model changes need a spec) →
`concept-reviewer` → `database-engineer` (migrations) → `developer`/`senior-developer`
→ `validator` + `tester` → `git` agent.

---

## Cluster 6 — Data-model identity: ReqIF, Measures, Milestones

**Branch:** `feat/reqif-identity-and-measures` · **Issues:** #1003, #393, #879
· **Priority: Geplant (after #932 blocked)**

**Why one cluster:** all three extend the artifact data model (identity / measures /
milestones) and need one shared schema design. **#1003 blocks #932** — it must land
before `uid` becomes an auto-generated local identifier, otherwise the ReqIF round-trip
is silently damaged.

**Files:** TBD after the spec pass. Expected: `backend/persistence/models.py`,
new migrations, `backend/application/reqif_import_service.py`,
`backend/application/reqif_export_service.py`, new `measure` app/service,
new MCP tool group, frontend origin/import block.

**Tasks:**
1. **#1003** — separate `uid` (local) from external identity: `reqif_uid` /
   `reqif_identifier` / `reqif_alt_ids` / `reqif_source_tool` / `reqif_source_project`
   / `reqif_specification` / `reqif_imported_at` / `reqif_last_exported_at`
   (or a 1:n `ReqifIdentity` model). **The 7 open decisions in §4 of the issue must be
   decided before the migration** (join key for round-trip, import matching, ATTR-UID
   export, unique constraints, 1:n vs 1:1, local `uid` for imported artifacts, UI
   placement). Order: concept here → model fields → #932 (local generation) → AWMS
   backfill (#930). Acceptance criteria are listed in §6 of the issue and are the test
   basis.
2. **#393** — new `Measure` entity with `kind ∈ {MOE, MOP, TPM}`, `unit`, `target_value`,
   `threshold`, `current_value`, `measured_at` + time series; linkable to
   `Goal`/`StakeholderNeed` (MOE), `Requirement` (MOP), `ArchitectureElement` (TPM);
   MCP tools to create/query. **Requires an ADR** (architecture impact, `Measure` is a
   new top-level concept) per the SE-cascade ADR standard.
3. **#879** — project milestones (SRR/PDR/CDR) as system entities for phase assessment.

**Test:** ReqIF round-trip test: an identifier imported from a foreign tool survives
import → export byte-identically (see #1003 §6); `Measure` CRUD + link + series query via
REST and MCP; milestone entity usable in phase assessment.

**Dispatch:** `concept-specifier` (XL) → `concept-reviewer` → `database-engineer` →
`senior-developer` → `validator` → `git` agent. ADR obligation checked before
implementation (arch_impact = true).

---

## Cluster 7 — UI consistency & Attribute-System v3 epic

**Branch:** epic-driven (#934), not a new branch from this plan · **Issues:** #801,
#934/#929/#941/#912, #587 · **Priority: Geplant**

**Why one cluster:** #929/#934 are already structured as an epic with workstreams
(#941/#912). #801 (inspector for 6 entity types) and #587 (Promptfoo infra) couple to
the same data model / theme. **Before starting, the status of open PR #945
(`feat/attribute-v3-ws1-7`) must be clarified** — otherwise this duplicates work.

**Tasks:**
1. **#801** — bind the Inspector shell for ADR/Risk/Issue/TC/Need (component already
   exists for requirements; this is wiring, not new development) + integrate a
   trace-links widget (source/target + link type + outdated flag) from `/traceability`.
2. **#934 epic** — WS0 contract matrix + shared gateway (#941/#912), then WS1–7. Do not
   re-plan the epic here; execute against its existing workstream issues.
3. **#587** — Promptfoo test infrastructure for prompt templates (Phase 3, Prompt
   Variable Catalog).

**Test:** Inspector present and functional on all 6 entity types with diff chips as for
requirements; epic's own WS acceptance criteria; Promptfoo suite runs in CI.

**Dispatch:** `orchestrator` against the existing epic branches; `planner` only if the
WS cut is unclear. **Not** part of this plan's execution queue until C1–C6 are done.

---

## Deliberately out of scope (this bundle)

- **#426** — SE-methodology audit index/parent. Klammer, never closed on its own; its
  children (#424/#402/#399/#393) are in C5/C6.
- **#792** — RFC Deployment/Security/Ops. Meta-RFC, no fix; use as review input for C1,
  do not "work off".
- **#946, #987, #810** — decisions required from the user first (debug annotation layer,
  notification placement, view modes). Not implementable until decided.
- **#649, #598, #597, #92, #89, #85, #50, #39, #35, #29, #28, #27, #19, #18, #17, #378**
  — backlog / feature requests / older QA findings without current wrong behaviour.
  Open by intent, not part of an active bundle.
- **#934/#929/#941/#912** — routed via the existing epic (#934); adding them to a fresh
  branch from this plan would fork the work.
