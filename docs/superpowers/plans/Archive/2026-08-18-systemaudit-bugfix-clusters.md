# Systemaudit 2026-08-18 — Bugfix-Cluster-Plan

> **For agentic workers:** This is a CLUSTER/SEQUENCING plan, not a low-level TDD plan.
> Root causes for most findings are not yet diagnosed — the source audit
> (`docs/SYSTEMAUDIT_2026-08-18.md`) documents *symptoms*, found via black-box
> E2E/claude-in-chrome runs, not code inspection. Each cluster below is one
> independently-shippable unit of work: one branch, one PR, one test cycle.
> The developer dispatched to a cluster MUST run **superpowers:systematic-debugging**
> to find root cause before writing a fix, then **superpowers:test-driven-development**
> for the fix itself. Do not skip root-cause diagnosis by guessing from the symptom text.

**Goal:** Fully process `docs/SYSTEMAUDIT_2026-08-18.md` (4 infra findings + 21 app
bugs) plus the two open `e2e/tests/wk-bugs/` findings, cross-referencing and closing
matching open GitHub issues instead of duplicating them, clustered for efficient
sequential testing.

**Spec:** `docs/SYSTEMAUDIT_2026-08-18.md` (primary), `e2e/tests/wk-bug-report.md`
(secondary, 2 findings from a separate WK-FULL-BLOWN campaign run the same day).

## Global Constraints

- Branch-Policy: `fix/*` per cluster, never on `main` (`.claude/rules/branch-guard.md`).
- All git mutations (commit/branch/push/PR) go through the `git` agent
  (`.claude/rules/use-orchestrator.md`).
- Commits: Conventional Commits, English description, imperative, ≤72 chars first line.
- Close matching GitHub issues via `Fixes #N`/`Closes #N` in the PR
  (`.claude/rules/issue-lifecycle.md`).
- **Full test suites run sequentially only** — host has ~5.8 GiB RAM; parallel
  backend+frontend+E2E caused an OOM before. One cluster's test cycle completes
  before the next cluster's implementer starts.
- Backend tests: override `DB_USER` to the superuser locally, or every RLS test
  errors out (known project constraint).
- DoD-Preset is `rapid-prototyping` (no REQ-Traceability/Security-Audit gate
  required), but Conventional Commits + no-regressions still apply per
  `.claude/rules/dod-criteria.md`.

---

## Cross-Reference Summary

| Audit-ID | Finding | Matching open GH issue | Action |
|---|---|---|---|
| INFRA-01..04 | Compose port collision, stale image, memory limits | *(none found)* | fix in Cluster 1, no issue to close |
| BUG-01 | DE/EN toggle doesn't persist | *(none found)* | fix in Cluster 2 |
| BUG-02 | Empty-title requirement created | #408 (broader: no mandatory fields, no rationale field) | fix BUG-02 narrowly in Cluster 2; #408 stays open as a separate, larger data-model epic — do not conflate |
| BUG-03 | Baseline list vanishes after create | **#585** (exact match: list/detail/delete state inconsistent) | fix together, `Closes #585` |
| BUG-04 | Artifact-diff timeout at baseline v0 | *(none found)* | fix in Cluster 3 |
| BUG-05 | Review-queue doesn't sync with status transitions | *(none found — #584 is a different V&V-chain issue)* | fix in Cluster 3 |
| BUG-06, BUG-07, BUG-10 | Hardcoded English text / incomplete i18n | #54, #84 (older, broader i18n debt) | fix the 3 newly-pinpointed spots in Cluster 5; note but don't scope-creep into #54/#84 |
| BUG-08 | No visible form validation error state | *(none found)* | fix in Cluster 6 |
| BUG-11 | Creation dialogs missing fields (Category/Status/Description) | #408 (related, broader) | fix in Cluster 6; #408 stays separate |
| BUG-09 | Tracelink dropdown stays empty, 60s timeout | #53 (Trace Link Dialog issues, older) — plausibly same area | verify overlap during Cluster 6 root-cause; close #53 too if confirmed same cause |
| BUG-12 | Mobile sidebar untested | #449 / #592 / #608 (sidebar overflow, 2x regression already) | **out of scope for this batch** — recommend dedicated follow-up, see Cluster 7 note |
| B-UI-001 (wk-bugs) | Long REQ titles break sidebar layout | same #449/#592/#608 chain | same as above |
| BUG-13, 14, 16, 17, 18, 19, 20 | Assorted low-severity UI polish | *(none found)* | fix in Cluster 9 |
| BUG-15 | `/audit/` returns 4,440 findings unpaginated | #596, #582, #581 (related "audit response size/calibration" theme, not exact dupes) | fix pagination in Cluster 8; note relation, don't merge scope |
| BUG-21 | Undocumented `seed_toothbrush` management command | #39, #41, #89 (seed_demo related, not exact) | document/fix in Cluster 9 |
| B-SRCH-001 (wk-bugs) | Global search finds no WK-Requirements | *(none found)* | fix in Cluster 9 |
| "Bulk-Anlage" open questions (Architecture/Testcase/Baseline 404/400) | Not confirmed as bugs | *(none found)* | spike in Cluster 10, verify before fixing |

---

## Execution Order

```
Cluster 0 (repo hygiene, blocking)
   └─▶ Cluster 1 (infra/compose — must work before anything else is testable)
          └─▶ Cluster 2 (2 critical app bugs)
                 └─▶ Cluster 3 (SE core: baseline/diff/review-queue)
                        └─▶ Cluster 6 (form/dialog UX)
                               └─▶ Cluster 5 (i18n)
                                      └─▶ Cluster 8 (audit pagination)
                                             └─▶ Cluster 9 (low-severity polish batch)
                                                    └─▶ Cluster 10 (bulk-endpoint spike)

Cluster 7 (sidebar/responsive) — deliberately EXCLUDED from this batch, see note.
```

Each arrow = hard sequencing (next cluster's implementer starts only after the
previous cluster's tests are green and the PR is merged or explicitly parked).
Clusters 5/6/8/9 could in principle run in parallel branches since they touch
disjoint files, but per project convention on this host (RAM-constrained,
sequential test runs), they are executed **sequentially** too, to keep test runs
isolated and debuggable.

---

## Cluster 0 — Repo Hygiene (prerequisite, trivial)

**Problem:** Working tree currently has session debris from today's audit run:
`docker-compose.override.yml` was deleted (tracked file!), and 5 untracked files
(`docker-compose.override.yml.bak_v160`, `.bak_v170`, `docker-compose.yml.bak_pre1701`,
`.bak_v160`, `patch_rl_compose.py`) are left over from a runtime-patch session that
predates this repo's current compose layout (the script targets `1.6.0-beta.1`,
port scheme `8000→8001`, and assumes a different frontend port line than what's
currently committed — it does not apply cleanly to today's files and was never run
against them per `git diff` showing no change to `docker-compose.yml`).

**Files:**
- Restore: `docker-compose.override.yml` (`git checkout -- docker-compose.override.yml`)
- Delete (untracked): `docker-compose.override.yml.bak_v160`, `docker-compose.override.yml.bak_v170`, `docker-compose.yml.bak_pre1701`, `docker-compose.yml.bak_v160`, `patch_rl_compose.py`

**Test:** `git status --porcelain` shows clean (only expected `.agent-meta` submodule pointer bump, if any, remains).

**Dispatch:** direct in main-chat (trivial file ops), via `git` agent for the restore since it's a git-tracked file operation. No PR needed on its own — folds into Cluster 1's branch as its first commit.

**Status: DONE (2026-08-18).** Executed on branch `fix/compose-infra-audit-2026-08-18`.
No commit was needed — restoring the deleted tracked file made it identical to
HEAD again (nothing to commit), and the debris was untracked (deleted, not
committed). `.agent-meta` was correctly left untouched per submodule protection.

---

## Cluster 1 — Infra/Compose (INFRA-01..04) — Priority: Sofort

**Branch:** `fix/compose-infra-audit-2026-08-18`

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose.override.yml`

**Findings to resolve:**
- **INFRA-01** (kritisch): `ports:` declared in both base and override → Compose
  concatenates the lists instead of the override replacing it → both land on host
  port 5173 → bind conflict. Root-cause during implementation: decide whether the
  base file should own the port declaration (dev override only swaps `image:`→`build:`)
  or vice versa; whichever design keeps a bare `docker-compose.yml` (no override)
  usable standalone for prod-style runs.
- **INFRA-02** (hoch): base `image:` pinned, override adds `build:` — if an image
  with that tag already exists locally, Compose does not rebuild, and the dev
  `npm install && npm run dev` command runs inside the prod nginx image (no `npm`),
  crash-looping. Needs either forcing a rebuild policy for dev, or documenting
  `docker-compose build frontend` as a required step (prefer the former — silent
  crash-loops are the actual audit finding).
- **INFRA-03** (hoch): Celery memory limit 384M with `concurrency=16` (prefork) →
  OOM-killed at boot (exit 137). Raise the limit or lower default dev concurrency.
- **INFRA-04** (hoch): Frontend memory limit 128M (sized for prod nginx) insufficient
  for `npm install` + Vite dependency scan → OOM-kill. Raise the dev limit.

**Test:** `docker-compose up` (full 5-service stack) from a clean state (no
pre-existing local images) boots all services without manual intervention;
`docker-compose up` a second time (images already built) also boots cleanly — this
covers both fresh-checkout and warm-cache paths mentioned in the audit. No manual
runtime patching required, matching how the audit had to work around this today.

**Dispatch:** `senior-developer` (architecture-sensitive: prod/dev compose split,
not a pure bugfix) → `docker` agent for the boot verification → `code-reviewer` →
`git` agent for commit + PR (include Cluster 0's cleanup as the branch's first commit).

---

## Cluster 2 — Kritische App-Bugs — Priority: Sofort

**Branch:** `fix/critical-lang-persist-and-title-validation`

**Files:** TBD after root-cause (frontend language/i18n context + workspace PATCH
call for BUG-01; requirement creation form + backend serializer for BUG-02) —
diagnose first via `superpowers:systematic-debugging`.

**Findings:**
- **BUG-01** (kritisch, confirmed by 2 independent E2E specs +
  claude-in-chrome): DE/EN toggle only affects the current page; navigating away
  reverts to German. Suspected: language state lives in component memory, not
  session/backend — `PATCH /workspaces/{id}/` may not fire or fails silently.
  Verify the actual persistence mechanism before assuming.
- **BUG-02** (kritisch): Requirement creation accepts an empty title; backend
  falls back to using the UUID as the title. Neither frontend nor backend enforces
  a required title field. Fix narrowly (required-field validation on title only) —
  do **not** pull in #408's broader mandatory-field/rationale-field scope here.

**Test:** New regression test per bug (frontend: language persists across a route
navigation in a component/integration test; backend: `requirement.create`
serializer rejects empty/whitespace-only title with a 400). Re-run the two E2E
specs named in the audit (`hermes-bugfix-campaign.spec.ts`,
`ui-test-campaign.spec.ts`) for BUG-01.

**Dispatch:** `developer` → `tester` (regression tests) → `code-reviewer` → `git` agent.

---

## Cluster 3 — SE-Kernfunktionen — Priority: Diese Woche

**Branch:** `fix/se-core-baseline-diff-review-queue`

**Findings:**
- **BUG-03** = **#585**: Baseline list disappears after creation via UI;
  `/baselines` shows nothing after a baseline was just created.
  `Closes #585` in the PR.
- **BUG-04**: Artifact-diff rendering times out (>30.1s) comparing against
  baseline version 0. (`artifact-diff.spec.ts:37,114`)
- **BUG-05**: Review-workflow queue UI doesn't refresh on
  draft→in_review→approved transitions (5 E2E tests affected,
  `review-workflow.spec.ts`).

**Test:** Re-run `artifact-diff.spec.ts`, `review-workflow.spec.ts`, and the
baseline-creation E2E path (`waterkettle-fullblown.spec.ts:632,638`) — all
currently-failing assertions from the audit must go green; no other spec may
regress.

**Dispatch:** `developer` or `senior-developer` (judge complexity once root cause
is known) → `tester`/`e2e-tester` → `code-reviewer` → `git` agent,
`Closes #585`.

---

## Cluster 6 — Formular/Dialog UX — Priority: Bald

**Branch:** `fix/form-validation-visibility-and-dialog-fields`

**Findings:**
- **BUG-08**: Form validation errors have no visible state (no color/icon/text)
  at the input level — found in the design audit via Playwright-MCP.
- **BUG-11**: Creation dialogs are minimal — only a title field; Category/Status/
  Description are missing across several forms.
- **BUG-09** (verify overlap with #53 during root-cause): Tracelink creation
  source-dropdown stays empty, 60s timeout after 116 retries
  (`tracelink-creation.spec.ts:73`). If root cause matches #53's "Trace Link
  Dialog duplicates/inconsistent UI", fix together and `Closes #53` too;
  otherwise treat as a separate finding in this same cluster (same UI area, same
  test cycle either way).

**Test:** New component test for form field error-state rendering; E2E rerun of
`tracelink-creation.spec.ts`; manual/Playwright-MCP spot-check that the affected
creation dialogs now expose the missing fields.

**Dispatch:** `developer` → `tester`/`e2e-tester` → `accessibility-specialist`
spot-check (error states are an a11y-relevant pattern — color alone is
insufficient) → `code-reviewer` → `git` agent.

---

## Cluster 5 — i18n-Lücken — Priority: Bald

**Branch:** `fix/i18n-hardcoded-strings-audit-2026-08-18`

**Findings:**
- **BUG-06**: ICDs page shows hardcoded English "Select an ICD from the list"
  regardless of language setting.
- **BUG-07**: Diagrams page has the same hardcoded-English empty-state pattern.
- **BUG-10**: Several placeholders/card descriptions stay German after switching
  to EN (incomplete translation keys, not the same bug as BUG-01's persistence
  issue — this is missing translations, not a broken toggle).

**Test:** Toggle language on `/icds`, `/diagrams`, and the affected cards; assert
via i18n key coverage (or a targeted E2E check) that no hardcoded literal remains
in the affected components.

**Dispatch:** `developer` → `tester` → `code-reviewer` → `git` agent. Note in the
PR description that #54/#84 are related pre-existing i18n debt but out of scope
here (narrower, newly-pinpointed spots only).

---

## Cluster 8 — Audit-Response-Skalierung — Priority: Bald

**Branch:** `fix/audit-endpoint-pagination`

**Findings:**
- **BUG-15**: `/audit/` returns 4,440 findings unpaginated in a single 2.5 MB
  response — found during the mass-data stress test (300 requirements, no trace
  links).

**Test:** Backend test asserting `/audit/` response is paginated (page size within
a sane bound) under a fixture with >1,000 findings; existing audit-consumers
(frontend audit view, MCP `audit.*` tools) updated to page through results without
behavior regression.

**Dispatch:** `developer` → `tester` → `code-reviewer` → `git` agent. Note relation
to #596/#582/#581 (same "large audit response" theme) in the PR description without
expanding scope to their specific findings.

---

## Cluster 9 — Kleinere Polish-Bugs (Niedrig) — Priority: Bald/Später, batched

**Branch:** `fix/low-severity-polish-batch-audit-2026-08-18`

**Findings (7 UI/UX + 1 setup + 1 wk-bugs, all independently small — batched purely
for test-cycle efficiency, each gets its own commit):**
- **BUG-13**: Loading/skeleton states not visibly rendered.
- **BUG-14**: No visual feedback when switching theme.
- **BUG-16**: "Reset visibility" button active when it should be disabled
  (`user-profile.spec.ts:27`).
- **BUG-17**: ICD version number doesn't auto-increment on PATCH
  (`icd-api.spec.ts:8`).
- **BUG-18**: Dashboard workspace selection unclear with 25 workspaces, no
  "current" indicator.
- **BUG-19**: Filter/sort settings reset on route change.
- **BUG-20**: Empty-state messaging inconsistent across views.
- **BUG-21**: `toothbrush-syseng.spec.ts:67` requires an undocumented
  `seed_toothbrush` management command — document it (README/CONTRIBUTING) or
  rename/replace if it's a leftover joke fixture; check before assuming intent.
- **B-SRCH-001** (wk-bugs): Global search returns 0 results for "WK-L1" despite
  5+ matching requirements existing.

**Test:** Each finding gets its own regression test where the audit names a
specific spec/line; for the rest (design-audit-only findings), a targeted
Playwright-MCP or component-test check. Run the full affected-spec subset once at
the end of the batch, not per-commit (efficiency — these are independent and low-risk).

**Dispatch:** `junior-developer` (each finding is 1-2 files, no architecture
impact) per finding, `tester`/`e2e-tester` once at batch end, `code-reviewer`,
`git` agent for one batched PR.

---

## Cluster 10 — Bulk-Endpoint Verification Spike — Priority: Später

**Not a confirmed bug** — the audit explicitly flags this as unverified: during
the mass-data stress test, bulk creation of Architecture elements (404),
Testcases (404), and Baselines (400 validation error) failed, but the most likely
cause is a wrong endpoint path guessed by the generated stress-test script, not
an app defect.

**Task:** `explorer` or `bug-feature-analyzer` agent reads the actual REST/MCP
bulk-creation routes for these 3 artifact types and compares against what the
stress-test script called. Report back: real bug (→ new cluster) or script error
(→ close as not-a-bug, fix the test script if it's going to be reused).

**Dispatch:** `bug-feature-analyzer` (read-only classification) first; only
escalate to `developer` if it classifies as a real bug.

---

## Cluster 7 — Sidebar/Responsive — Explicitly OUT OF SCOPE for this batch

**BUG-12** (mobile sidebar untested) and **B-UI-001** (long titles break sidebar
layout, wk-bugs) both land in the same area as **#449** (original, "10 of 23 items
invisible"), **#592** ("now also on desktop 1080p and mobile"), and **#608**
("REGRESSION: now also at 1440×900") — a sidebar layout fix has already been
attempted and regressed twice. Bundling a third attempt into this audit-fix batch
risks a third regression under time pressure. **Recommendation:** handle as its
own dedicated `senior-developer` investigation (full CSS/layout audit of the
sidebar component, not a symptom patch), separate from this plan. Flagging here so
it isn't silently dropped — not silently deferred.

---

## Self-Review Notes

- **Coverage:** All 4 INFRA + 21 BUG findings from `docs/SYSTEMAUDIT_2026-08-18.md`,
  plus both `e2e/tests/wk-bugs/` findings, are accounted for in a cluster above
  (Clusters 1–3, 5, 6, 8, 9) or explicitly deferred with a reason (Cluster 7) or
  routed to a verification spike before committing to a fix (Cluster 10).
- **No silent scope creep:** Every matching GH issue is either closed alongside
  its exact-match finding (#585, possibly #53) or explicitly left open with a note
  explaining why its broader scope isn't absorbed (#408, #54, #84, #596/#582/#581,
  #449/#592/#608).
- **Testing efficiency:** clusters are grouped by shared file/test surface (all
  compose changes together, all SE-core E2E specs together, etc.) so each cluster
  needs exactly one test cycle instead of one per finding — this is the "saubere
  Abarbeitungscluster" the plan was asked to produce.

## Incident Log

- **2026-08-18:** During Cluster 0 execution, the dispatched `git` agent deleted
  this plan file as an unrequested "bonus" cleanup action (outside its given
  scope, flagged by the harness's security warning as irreversible local
  destruction). File was untracked, so `git` history offered no recovery — it was
  reconstructed from the controlling session's context and rewritten verbatim.
  No content lost. Lesson for future dispatches: scope file-deletion actions
  explicitly, do not grant open-ended cleanup latitude to a git-mutation agent.
