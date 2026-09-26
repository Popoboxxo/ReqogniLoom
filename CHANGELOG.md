# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **REST breaking change — `expected_version` / `If-Match` on `POST /api/v1/<entity>/{id}/transitions/` is now enforced (CR-08):** a client-supplied revision was previously read by the view and then silently dropped, so requests that carried `expected_version` or an `If-Match` header and received `200` are now answered **`409 CONFLICT`** when the item's workflow revision has moved on. Clients that relied on the old silently-ignored behaviour (or that send a stale revision without checking) must handle `409` — re-read the item and retry. Omitting the revision is unchanged and stays last-writer-wins. Note that on this route the tag denotes the **workflow revision** (`version`, now returned by both the GET and the POST response of `transitions/`), *not* the entity ETag that `If-Match` carries on `PATCH` and that answers `412`.

## [1.8.0-beta.16] — 2026-09-26

> **This beta is explicitly NOT an external production or QA release.** It is an
> internal pre-release cut prepared on `release/v1.8.0-beta.16` (base
> `origin/main` = `73892571`). The audit waves W0/W1/W2 shipped below are
> **partially** implemented — their exit criteria are **not** fully met (see
> *Known open points*), W3–W5 have **not** started, and the regression suite is
> **not green** at this cut (see *Verification*). Nothing here constitutes a
> production, staging or QA deployment approval.

### Added
- **W0 — evidence/decision baseline and the W0/W1 security slice (PR #1070, `82f13395`):** hardens the W0/W1 security boundaries. W0 is **partially** implemented — the evidence baseline and the W0/W1 slice are in place, the W0 exit criteria are **not** fully met
- **W1 close-out — RLS exit evidence, legacy API-key inventory, negative tests (PR #1071, `f85407f7`):** tenant-isolation coverage assertions, a migration arming RLS on the baseline delta-index entry, projector RLS arming checks, and a strictly read-only management command that inventories legacy API keys without exposing or mutating secret material. The actionlint gate is pinned to a digest-resolved image and the one real finding it reported is fixed, and W1 negative tests now fail when a security control regresses
- **W1 review round — workspace-fence hardening (PR #1071, `7012a7c2`):** a real bug is fixed whereby the workspace-fence rule was `if not workspace_ids`, so a fence of non-canonical entries previously passed as set; the fence is now decided by canonical UUID round-trip. The actionlint job switches to implicit workflow discovery with job-scoped `permissions: contents: read`, `context_graph/tests` joins the CI matrix, future-facing rotation classification is pinned per contract rule, and the RLS exemption justifications are made honest about Django-admin exposure and guarded by a claim marker
- **Interview formalization audit and outbox events (PR #1073, `14fc05e5`):** single formalize, multi formalize and `abandon()` now write an `AuditEntry`, and `abandon()` emits an `INTERVIEW_ABANDONED` outbox event. A swallowed transition now logs a warning and is recorded as `workflow_transition_applied`, so success and failure stay distinguishable. Adds migration `0027` (single `AlterField` on `event_type`, no data migration)
- **MCP/REST multi-interview parity (PR #1073, `14fc05e5`):** `confirmed_proposal` is added to the `interview.formalize` MCP schema and forwarded, so REST and MCP share one multi-interview contract — the published MCP multi-formalize path is no longer permanently blocked. Single-MCP without a proposal keeps working
- **Documentation — system audit and improvement plan (PR #1069, `988294b6`, `66e21f56`, `e3df119e`; status addendum `49edead8`):** the 2026-09 system audit improvement plan, the architecture-boundary and frontend accessibility audit reports, and a dated W0–W2 implementation-status section. The status section states explicitly that green tests alone never mark a track `VERIFIZIERT`
- **Release plumbing:** all 12 distribution version carriers advanced to `1.8.0-beta.16` (`VERSION`, `frontend/package.json`, `frontend/package-lock.json`, the Hermes plugin `package.json`/`hermes-plugin.json`/`package-lock.json`, both `dist` plugin manifests, `.env.example`, both compose files' image tags, and the site badge/footer)

### Fixed
- **Workflow transition business-graph validation ran outside the row lock (CR-08; PR #1073, `6f145c87`):** no caller forwarded `expected_version`, so two racing transitions could both validate their edge against a stale `current_state` and the loser wrote a never-validated history edge. Validation and write now share one lock, `expected_version` is forwarded through `WorkflowFacade.transition` and the REST/MCP callers, and a stale revision yields `409` instead of a misleading `400` — or, as before the fix, `500`
- **Interview formalization had no lock, constraint or idempotency guard (CR-05/CR-06/CR-07; PR #1073, `14fc05e5`):** the status check ran unlocked, so two concurrent callers could both formalize. `_lock_in_progress_session()` is now extracted from the already-correct multi path and used by the single path and by `abandon()`, so `abandon()` can no longer flip a just-formalized session via the declared `completed -> abandoned` edge
- **Global definition propagation was neither atomic nor orphan-safe (CR-09/CR-10; PR #1073, `d4d912bf`):** `_persist()` committed the global definition row outside any surrounding transaction and only then propagated to the derived per-workspace rows, so a failing propagation left global and derived truth diverged. Both now run in one `transaction.atomic()`, proven by fault injection before and after the derived write
- **Global `delete_state` had no live-item gate (CR-09; PR #1073, `d4d912bf`):** deleting a state propagated into every inheriting non-customized workspace, including workspaces holding live items in that state. A fail-closed `OrphanedStateError` gate now raises and maps to HTTP `409`, held with the write in one transaction with `select_for_update` on the global definition. The gate is a single condition — rolling it back is one call, not a schema step. The provisioning repair refuses to orphan a live item and names every row it did not repair; a customized row is never touched
- **Bluepencil host identity bridge (PR #1055, `3caff390`):** the review sidecar now gets a host identity bridge, so annotation anchors resolve against the right host
- **Login timeout cause was lost (PR #1055, `e3db334a`, `94a3737a`):** the timeout error cause is now preserved, including under ES2020

### Changed
- **REST breaking change — `expected_version` / `If-Match` on `POST /api/v1/<entity>/{id}/transitions/` is now enforced (CR-08; PR #1073, `6f145c87`):** a client-supplied revision was previously read by the view and then silently dropped, so requests that carried `expected_version` or an `If-Match` header and received `200` are now answered **`409 CONFLICT`** when the item's workflow revision has moved on. Clients that relied on the old silently-ignored behaviour (or that send a stale revision without checking) must handle `409` — re-read the item and retry. Omitting the revision is unchanged and stays last-writer-wins. On this route the tag denotes the **workflow revision** (`version`, now returned by both the GET and the POST response of `transitions/`), *not* the entity ETag that `If-Match` carries on `PATCH` and that answers `412`
- **Global default endpoints answer `409` on a refused orphaning delete (PR #1073, `d4d912bf`):** clients of the global default-state endpoints must handle a new `409` where a delete would orphan a live item
- **Project metadata refresh (PR #1072, `22aeae4e`):** `.meta-config/project.yaml` only — no product behaviour change
- **Two migrations added:** `backend/application/migrations/0027_alter_domaineventoutbox_event_type.py` and `backend/baseline/migrations/0010_baseline_delta_index_entry_rls.py`. `makemigrations --check --dry-run` reports no pending changes

### Known open points
W0/W1/W2 are **partially** implemented; no track is `VERIFIZIERT`. Still open:

- **D1 constraint** — the `UniqueConstraint(session, artifact)` on `InterviewSessionArtifact` is **deliberately deferred** and recorded as a named follow-up (Interview-Formalize-Constraint)
- **Correlation field** — **open**. The W2 exit criterion "Tenant, Workspace, Actor, Version **and correlation**" is not met because the correlation field is missing
- **W2 negative test 6** (chat/provider outage) — **missing entirely**
- **CR-13** — **untouched**: no test, no implementation
- **CR-17**, **CR-22**, **CR-26** — **unchanged open**. W2 closed none of them
- **`pl_user`** — **unchanged open**, recorded as a prioritized follow-up
- **Service-wrapper `expected_version` gap** — **open**
- **Orphan-gate residual window** — **open**, deliberately not closed and instead documented in the code
- **Error/status semantics** — the W2 criterion "same versioned error/status semantics" across REST, MCP **and UI** is **not** met: the UI layer was not touched
- **W3** (contract/SE-SSOT and integration contracts), **W4** (CI, release, resilience, operations) and **W5** (UX, accessibility, external maturity decision) — **not started**. No wave abort was triggered and no global release stop criterion was hit: W2 is neither stopped nor complete

### Verification
Measured on this cut, not copied from a claim:

- **Backend** (`pytest`, backend test service): `9687 passed, 12 skipped, 1 xfailed, 4 errors` in `2017.55s`, exit `1`. All 4 errors are in `mcp_server/tests/test_mcp_api_key_roles.py::TestMcpApiKeyRolePropagation` and are a **live-stack test precondition**, not an assertion failure: that module drives a real HTTP server (its own docstring says so) and its `seeded_workspace_id` fixture requires a seeded `Demo Workspace`. An earlier revision of this block attributed the failure to pre-existing tenant drift; that explanation is **disproven and withdrawn** — the login JWT used by the fixture (`_get_bearer_token()`, `test_mcp_api_key_roles.py:125-146`, `SYSTEM_ADMIN_USERNAME`/`SYSTEM_ADMIN_PASSWORD`) reaches the demo tenant `7a539397-…` as well, so there is no tenant mismatch. The verified cause is **pagination**: the fixture reads only `data.get("results", [])` (`:296`), i.e. **page 1 only**, of a list that `StandardPagination` serves with `PAGE_SIZE: 25` ordered by `-modified_at` (`backend/reqogniloom/settings.py:536-537`). `next(..., None)` at `:298-300` therefore returns `None` and `assert seeded` fails at `:301` with a misleading `is bootstrap_admin/seed_demo loaded?` message. A read-only REST probe during the full run measured `count=377` with `Demo Workspace` (`6d20f0b9-d2cf-46a0-b916-79f8b417210f`, the same workspace ID recorded in `docs/se/reports/RELEASE_v1.8.0-beta.11.md:230`) on **page 4**. Caveat, stated rather than hidden: those counts belong to the long-lived, E2E-mutated dev database of that run and are **not** reproducible on its present state — re-probed during this verification the workspace table of the live dev database holds **0 rows** (postgres restarted, `seed_demo` not re-run since), so the stable, reproducible part of this finding is the *failure class* and its code path, not the row counts. This weakness is not new: it is documented as KI-1 since `RELEASE_v1.8.0-beta.11.md:226-235`, re-confirmed as "weiterhin vorhanden" in `RELEASE_v1.8.0-beta.12.md:282-285`, and tracked in `docs/se/reports/KNOWN_TEST_GATE_REDS.md` §2 — which for a *different* run attributes the reds of the same class to the dev database's 10-active-API-key cap combined with an unchecked `DELETE` in `_revoke_all_active_keys()`. Both descriptions concern a non-reproducible dev database; neither is a product defect. `seed_demo`/`bootstrap_admin` change nothing here (the workspace, when present, already exists) and a fresh test database is ineffective, because the test runs against the live stack rather than the test database. **The module is deliberately skipped in CI:** `pytestmark` carries `pytest.mark.skipif(bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS")))` (`test_mcp_api_key_roles.py:79-90`) and the `integration` marker is "nicht Teil der Unit-Suite" (`backend/pyproject.toml:18`). Proof — a targeted run of that module with `CI=true` reports `collected 8 items` → `8 skipped`, exit `0`; the same run without `CI=true` reports `4 passed, 4 errors`, exit `1`. The test file has no commit in `v1.8.0-beta.15..HEAD`
- **Frontend** (`vitest`, frontend test service): `2201 passed, 3 failed` of 2204 in 237 files (`2 failed | 235 passed`), exit `1`. All failures are `Test timed out in 5000ms` in filesystem-scanning ratchets (`design-tokens.test.ts`, `link-type-consumers.test.ts`). **Non-determinism, measured:** the same full run was executed twice and produced **2 failures in 1 file** on one pass and **3 failures in 2 files** on the other — same cause, changing shape, i.e. load-induced and last-order-dependent rather than a fixed defect. The scanned scope is essentially unchanged across the delta: the `.tsx`/`.ts` set the ratchets walk grew from **599 to 604 files (+0.83 %)** between `v1.8.0-beta.15` and this base commit, so the timeouts are not explained by scan growth. Running the two files **in isolation at the default 5000 ms timeout** (no `--testTimeout` override) gives `19 passed`, exit `0`, with `design-tokens.test.ts` at `4763 ms` — i.e. already within ~5 % of the default budget, which is why the full run tips it over. Neither file, nor `frontend/src/styles/tokens.css`, has a commit in `v1.8.0-beta.15..HEAD`
- **Authoritative gate — CI on the release base commit `73892571`:** **green.** 2 workflow runs on that commit, 14 check-runs, **14/14 conclusion `success`**, 0 failed, 0 pending: `CI Pipeline` (run `36229673123`) and `Playwright E2E Tests` (run `36229673118`), covering `lint`, `Workflow Lint (actionlint)`, `backend-test` set-1..set-4, `frontend-test`, `e2e` (1)–(4), `Hermes IDE Plugin`, `Agent Templates & Distribution` and `Backend Requirements Drift Check`. This is the binding release condition, and the backend/frontend reds above are outside it: the failing module is CI-skipped by design, and the two frontend ratchets run under different load in CI (`docs/se/reports/KNOWN_TEST_GATE_REDS.md:37-38`)
- **Green gates (local):** `manage.py check` (0 issues), `makemigrations --check --dry-run` (no changes detected), both compose `config -q` validations, `git diff --check`, the version-carrier consistency check (12 files / 22 occurrences, all `1.8.0-beta.16`) and the pre-release gate dispatcher (exit `0`, with `action-pin-validation` really executed and all action pins verified upstream; `artifact-freshness` and `docker-image-scan` self-skipped for missing prerequisites)
- **Release build:** `make build` / `scripts/build.sh` produced **no image**, and this is **true by construction rather than by accident**: `deploy/docker-compose.yml` contains **0 `build:` sections** — it only pins prebuilt images (`pgvector/pgvector:pg16`, `redis:7-alpine`, `ghcr.io/popoboxxo/reqogniloom-backend:1.8.0-beta.16`, `ghcr.io/popoboxxo/reqogniloom-frontend:1.8.0-beta.16`, …), while the 5 `build:` sections live in the dev overlay `deploy/docker-compose.override.yml`, which `scripts/build.sh:80-92` **deliberately excludes** (documented reason: the override merges the frontend's *development* target instead of the release image, and legacy `docker-compose` v1 cannot parse its `!override` merge tag). The script therefore reports `No services to build`. The canonical release build is the tag-triggered `.github/workflows/docker-publish.yml` (`on.push.tags: ['v*.*.*']`, `:15-18`) with its fail-closed Trivy gate (`severity: CRITICAL,HIGH`, `exit-code: '1'`, `ignore-unfixed: true`, `:144-156`); images are pushed only after that scan succeeds. **No image was built for this cut, so no image digest is documented.** As the maximum reachable QS build, the frontend `tsc -p tsconfig.build.json` type-check plus a production `vite build` bundle both succeeded (exit `0`)
- **`make test` is not a release gate.** By project convention the authoritative release condition is the CI run on the release base commit, not a local `make test`: the local verification table of the previous release contains no `make test` row (`docs/se/reports/RELEASE_v1.8.0-beta.15.md:145-152`), `docs/se/reports/KNOWN_TEST_GATE_REDS.md:37-38` states that the authoritative gate (CI) is unaffected by any of the listed local reds, and `Makefile:22-24` documents `make test` as running unit + integration tests only, never Playwright E2E. The local full-run reds documented above are consequently reported as known, non-attributable Reds — not as a release blocker

## [1.8.0-beta.15] — 2026-09-23

### Added
- **Validation as a first-class pillar (PR #1035; #399, #402, #424, #272):** TestCases now carry provenance — `origin` (`manual` | `ai_generated`) and `reviewed`, written exclusively through `POST /api/v1/testcases/{id}/review/` — and one shared `counts_as_verification_evidence` predicate makes coverage, precondition rule 6 and VERIF-P8 ignore an unreviewed AI-generated TestCase, so an AI draft can no longer produce a false green. `goals_enabled` now defaults to `true` and the Extended-only VAL-P1 rule requires every active StakeholderNeed to satisfy at least one active Goal (doubly gated, advisory, never able to block a baseline build). Editing a baselined artifact records drift instead of failing: `GET /api/v1/artifacts/{id}/baseline-membership/`, an additive `baseline_drift` summary on retrieve and an `affected_item_ids` change-request prefill. The requirement→test coverage report (`GET /api/v1/requirements/coverage-report/`) gains `pending_ai_review` and `scenario_kind`, `verification_method` joins the Extended approval gate, and a manual trace link to a soft-deleted endpoint is refused (system writers unaffected)
- **SE-auditor finding waivers and suppression (PR #1037; #569):** findings get a stable `finding_key`, a `BaselineGateWaiver` entity with optional `expires_at` (migration 0009) and scope-aware matching with decision-time expiry. REST exposes `POST`/`GET /api/v1/workspaces/<id>/audit/waivers/` plus a strict `include_suppressed` filter on `GET .../audit/`; MCP adds `audit.waive_finding` (write, ADMIN tier) and `audit.waivers` (read, approval authority) with the dedicated error codes `-32008`/`-32009`/`-32010`. The SPA gains the third per-finding action *Waive* (justification required), a show-suppressed filter, a suppressed badge and a waivers panel that keeps expired waivers distinguishable from active ones
- **Empty-state create guidance (PR #1039; #27, #28, #29):** the ICD list, the custom-fields editor and the trace-link panel now explain how to create the first item instead of rendering an unexplained blank area (DE/EN parity)

### Fixed
- **TRACE-P1 no longer goes silent on a cyclic hierarchy (PR #1030; #1021):** the traceability rule reports on cyclic hierarchies again instead of producing an empty result
- **Embedding dimensions in image deployments (PR #1029; #1018, #1019):** shared embedding-column catalog introspection, an idempotent `align_embedding_dimensions` management command applied by `honcho-migrate`, and a dimension-mismatch signal surfaced on `/health/`; `deploy/README.md` documents the resize path for image deployments
- **`seed_demo` bootstraps attribute definitions (PR #1038; #29):** a database populated only through `seed_demo` no longer has zero global attribute definitions — the same shared bootstrap step as `self_init` is reused, and the idempotency regression now compares a canonical content signature (attribute and workflow definitions, versions) instead of row counts alone
- **Accessible trace-link dropdown (PR #1033; #318, #876):** the trace-link type dropdown is keyboard-accessible and migrated onto design tokens
- **bluepencil browser assets re-vendored to alpha.2 (PR #1032; #988):** vendoring only, byte-identical and SHA-256-pinned

### Changed
- **No static inline styles left in the SPA (PRs #1040–#1047; #876):** a new `local/no-static-inline-style` rule at error level closed the gap that the colour rule and the `STYLE_BRACE` ratchet left open (a new non-colour inline style passed both), and the seven follow-up stages migrated every remaining carrier onto co-located CSS modules. `STYLE_BRACE_BASELINE` dropped 705 → 3 (all three comment-only) and the frozen exemption list went 70 → 0, so the rule now guards all of `src`
- **E2E hardening and tenant predicates (PR #1034; #947, #433):** the waterkettle fixture is idempotent (the created diagram/ICD ids are returned, so the cleanup loops are no longer dead code), generic selectors and an always-true version assertion were removed, and the explicit `tenant_id` defence-in-depth predicate in the architecture-tree bundle gained a mutation-probed regression test
- **Frontend build artifacts ignored (PR #1036):** `frontend/tsconfig*.tsbuildinfo` and `frontend/vite.config.{js,d.ts}` are no longer tracked working-tree noise

## [1.8.0-beta.14] — 2026-09-21

### Added
- **Unified workspace memory store (RFC #1002):** the platform's long-term memory now lives in a single `mem_memory_entry` table under row-level-security instead of split stores; every create path writes a provenance record (scope, owner, workspace, artifact link, source) so the `user`, `workspace` and `artifact` scopes share one persistence and retrieval contract (PR #1020)
- **Memory service, policy and transport surface (RFC #1002):** the `MemoryEntryService` façade (ADR-01) is now reachable over REST and MCP — six `memory.*` tools (`memory.write`, `memory.get`, `memory.digest`, `memory.query`, `memory.list`, `memory.forget`) and sixteen `/api/v1/` routes covering workspace entries/search/digest, artifact memory/digest, global entry detail/promote, the self-service `memory/me/`, workspace and system memory settings, the system workspace overview and projection, and entry export. Writes are rate-limited through `MEMORY_WRITE_RATE_LIMIT_PER_HOUR` (default 60); the active backend is selected by `MEMORY_BACKEND` (`pgvector` default, `honcho` optional) (PR #1022)
- **Artifact-scope memory and prompt injection (RFC #1002):** artifacts now own memory, and `prompt_resolver` feeds the resolved entries into the prompt through `memory/context_builder.py`, which emits the sections `Artifact context:`, `Workspace context:` and `User context:` in artifact-first order and fails open when memory is unavailable (PR #1023)
- **Memory UI (RFC #1002):** a workspace memory view and an artifact memory panel expose the entries, the consolidated digests and a degraded-backend banner in the SPA (PR #1024)
- **Honcho backend — sessions, deriver and `digest` (RFC #1002 F6):** the optional `honcho` profile gains its session/deriver wiring and the consolidated `digest` capability behind `MEMORY_BACKEND=honcho` (PR #1025)

### Fixed
- **Degraded memory signalling (RFC #1002):** `backend/memory/health.py` returns one envelope `{backend, ok, detail, degraded, digest_available}` on every memory response, the same state surfaces as the `memory_backend` component of `GET /api/v1/admin/health/`, and the UI banner reports an unavailable backend instead of a false `ok` (PRs #1022, #1024)

### Changed
- **MCP tool catalogue corrected to 215:** the documented tool count across the distribution and the docs now reflects the real 215-tool catalogue, and `.playwright-mcp/` is ignored so local browser-tool state cannot leak into the repository (PR #1026)
- **`x-opencode-session` header and container-DNS runbook:** the `opencode_go` provider attaches the `x-opencode-session` header only when `LLM_OPENCODE_SESSION` is set (unset ⇒ no header, the default), and `deploy/README.md` documents how to fix LLM calls that fail with `ConnectError` from the backend container's DNS (PR #1027)
- **Release reporting (v1.8.0-beta.13):** the beta.13 release report is finalised with the shipped tag, pre-release and GHCR publish evidence (PR #1017)

## [1.8.0-beta.13] — 2026-09-20

### Added
- **Local readable `uid` for every artifact (#932):** Eight artifact models documented an *auto-generated* `uid` that no code ever produced. A per-`(workspace, item_type)` monotonic `UidSequence` now allocates `{PREFIX}-{NNN}` on every create path (atomic against the `(workspace, uid)` constraint and non-recycling); a client-supplied `uid` is answered with `400` instead of being silently dropped; the eight "import key" help texts are corrected; the Needs/Architecture trees render the `uid` (the UUID short hash stays a legacy fallback); and an AWMS `value_strategy: sequence` plan backfills rows created before the feature (PRs #1005, #1011, #1013)
- **ReqIF identity separated from the local `uid` (#1003):** the external ReqIF identity moved onto dedicated `Artifact.reqif_*` fields with partial unique constraints; import matches on them and export prefers the stored identifier, so a round-trip keeps both the local identifier and the source key (PR #1004)
- **INCOSE/IEEE 29148 requirement attributes (#871, #583):** `Requirement.rationale` and `Requirement.source` are real model columns now, carried end to end (serializer, REST create/patch, service, MCP) and merged into existing attribute definitions; `owner`/`priority` remain Artifact-level system fields and `acceptance_criteria`/`verification_method` stay stage-mandatory from the standard preset (PR #1014)
- **`satisfies` / `realizes` / `refines` in the trace-link catalog (#950):** the three SE validation/satisfaction semantics are built-ins again — `satisfies` is the coverage-relevant Requirement → Goal edge, `realizes` the Requirement → Goal realization claim, `refines` Requirement → Requirement; migration `0008` seeds them per tenant, and the frontend label fallback follows (PR #1010)
- **AWMS value-migration catalog completed (#930):** `deprecate_attribute`, `export_scope` and `import_scope` now run through the one engine (PR #1012)
- **Environment-configurable default link types (#989):** `DEFAULT_TRACE_LINK_TYPE` / `DEFAULT_DECOMPOSITION_LINK_TYPE` decide what a new workspace starts with and act as the empty-column fallback (PR #1009)
- **MCP surface:** coverage/VCRM/SE-auditor tools (#410) and a filtered, compact tool catalogue (#866) (PRs #1001, #1000)
- **Marketing site:** interactive GitHub Pages one-pager (#979)

### Fixed
- **Admin backups are gzip-compressed (#823):** `admin.backup_create` stores `<id>.json.gz` (Django's `loaddata` reads it transparently; existing uncompressed dumps still restore) (PR #1008)
- **Deployment robustness (#918):** the compose default image tag was four betas stale (`1.8.0-beta.8` → current), `.env.example` gained the operational variables the compose supports — including the README's *first stumbling block* `CSRF_COOKIE_SECURE` — `redis` got a named volume for its already-enabled AOF (queue/cache no longer vanish on recreate), and `bluepencil` is marked DEBUG/QS-only on every surface (PR #1015)
- **beta.12 QA bundle (#996)** across API, health, UI and bluepencil, plus the change-reason refusal surfaced at the field (`#995`)
- **Notification popover is dismissible (#985)** (PR #992)
- **UI consistency:** control standard applied to workspace settings (#986) and requirement trace links unified with derived labels and allocation (#998)

### Changed
- **E2E hardening (#947):** state-dependent and flaky Playwright specs stabilized (PR #997)

## [1.8.0-beta.12] — 2026-09-18

### Added
- **Collaboration — Comments & Notifications (Menschen im System, collaboration half):** Artifact comments and a user notification feed are now first-class citizens: new `Comment` and `Notification` models with row-level-security policies, a `CommentService` with the `comment_added` trigger, and a `NotificationService` with notifications for assignment (bound to the artifact attribute gateway), workflow `transition_pending`, `suspect_flagged` and `comment_added`. Adds a user-global notification-preference opt-out (four switches, no RLS by design), REST endpoints for artifact comments, the notification feed and self-service preferences, an MCP `comment.*` tool group, and a frontend `CommentPanel`, notification bell and profile preference section with DE/EN translations. Unimplemented comment/notification viewset routes now return 405 instead of 500 (PR #956)
- **Definition-Driven Requirement Create Dialog:** The requirement create dialog now renders the same definition-driven field structure as the edit dialog through the existing `ArtifactForm` machinery — no second renderer. Extended attributes land in the `custom_fields` carrier, the required gate only counts actually rendered/editable fields (a hidden mandatory field no longer blocks creation), required enums initialize with `default ?? options[0]` so gate and UI agree, `editable:false` fields are omitted, and an empty or failed attribute list falls back to the legacy minimal dialog. The `req-new-title-input` / `req-new-save-btn` E2E contract is preserved on both paths (PR #974; #583)
- **Optional Bluepencil Review Layer (Self-Hosted Sidecar):** An opt-in review/annotation layer can now be attached behind a global server flag plus a client-side runtime probe. The sidecar is a vendored, dependency-free `dist/server.js` served behind the `bluepencil` Compose profile (`make bluepencil` / `make bluepencil-down`), the browser bundle loads from a versioned, SHA256-verified path, and the existing `data-testid` convention doubles as the default annotation anchor. Strictly opt-in: the app probes nothing unless `VITE_BLUEPENCIL_ENABLED=1` is set alongside the `bluepencil` Compose profile — the loader flag is read at startup, so the frontend service must be restarted after a change — and logout tears the layer down. The integration plan documents the deliberate limit (no user auth, no tenant isolation → QS/demo only) and the production path (Option A, DRF `ReviewNote` with JWT + RLS) (PRs #972, #975)
- **ETag/If-Match Optimistic Locking & Runtime-Configurable Rate Limits:** Requirement, TestCase and Baseline updates support `If-Match` with `412` on stale versions (the existing `expected_version` `409` path is unchanged) and the Requirement UI is wired to it; REST and MCP rate limits are now runtime-configurable per tenant and deployment, with audit and cache handling (PR #959; #868, #923, #944, #35)

### Fixed
- **Security, API-Contract, Audit-Governance & UI/a11y Bulk:** Granular API-key scopes (`read_only < author < admin`, REST + MCP, legacy `read`/`write` aliases kept) with all governance surfaces moved to the admin tier; agent self-approval beyond the proposed state now yields `403` and agent self-confirm/discard returns `403` instead of `500`; one consistent free-text sanitization policy (markup rejected with `400`, text treated as data); read-only and unknown fields rejected with `400` instead of being silently dropped; key scope checked before the key limit; SE-auditor calibration (TRACE-P2 warning instead of blocker, ARCH-003 aggregated from 683 to 28 findings), preset `mandatory_fields` warnings scoped to real consumers, per-blocker waivers with mandatory justification, structured JSON-RPC errors for `audit.ai_review`, and failed audit runs can no longer render as consistent; `test_type` unified as single source of truth with `verifies` links counting as coverage. The accompanying UI/a11y/i18n wave aligns admin create dialogs with the design system, adds accessible names, unifies create actions, migrates pseudo-modals to the shared `Dialog` primitive, announces dynamic validation via `aria-live`, and restores missing i18n keys (PR #958; #865, #913, #914, #820, #915, #916, #917, #581, #912, #821, #951, #952, #816, #953, #886, #889, #954, #955, #797, #873, #677, #925)
- **CWE-209 Sweep, Scoping, Auth & UI Consistency Bulk:** 42 response sites no longer leak exception text to the client, backed by a guard test that fails on new leaks; `permissions.check` uses a structural discriminator instead of a debug string; the login-body token is deprecated behind `AUTH_LOGIN_INCLUDE_BODY_TOKEN`; `/health` now really probes the memory/embedding backend (`503 degraded` instead of a false `ok`); `suggest_architecture_for_requirement` fixes case-sensitive, object-blind UUID matching; and the UI wave synchronizes navigation state, clarifies list identifiers, groups requirement-form attributes into SE sections, unifies token-based badges, and balances the responsive KPI grid and smartphone bottom-sheet dialogs (PR #959; #697, #722, #696, #911, #825, #665, #666, #668, #807, #804, #803, #675, #809, #806, #874)
- **Unknown-Field Rejection Completed & Derivation Rationale Persisted:** `UnknownFieldRejectionMixin` now covers the remaining top-level write serializers and the raw write routes without a serializer, all returning the same `400 {"error": {"code": "VALIDATION_ERROR", ...}}` envelope, backed by a discovery guard test. The actor-generated `rationale` is no longer discarded on derivation: MCP tool authoring and `architecture.decompose_commit` persist it to the `custom_fields` carrier for both the architecture element and its requirement (PR #961; #851, #583)
- **Preset Change Re-Materializes Workspace Attribute Definitions:** `workspace_definition_store.resolve()` no longer returns a stale definition for the wrong preset — non-customized definitions are re-materialized on preset change, compatible customizations are fully preserved (including sections/flows), and incompatible ones raise an explicit `AttributeDefinitionConflictError` instead of silently running on the old definition. The conflict is surfaced actionably on REST (`409 CONFLICT`, including export), MCP (`VALIDATION_ERROR`) and as a fail-closed approval gate; no migration required (PR #973; #960)

### Changed
- **Dependency Updates:** Nine Dependabot bumps: `psycopg2-binary >=2.9.13,<3.0`, `django >=6.1.1,<6.2`, `whitenoise >=6.12.0,<7.0`, `anthropic >=1.5.0,<2.0`, `numpy >=2.5.3,<3.0`, `eslint 10.9.1→10.10.0`, `@tanstack/react-virtual 3.14.11→3.14.12`, `lucide-react 1.28.0→1.46.0`, and `react-dom` / `@types/react-dom` (PRs #962, #963, #964, #965, #966, #967, #969, #970, #971)

## [1.8.0-beta.11] — 2026-09-14

### Added
- **Attribute System v3 — Transport Parity & Gateway Seam (WS1):** REST and MCP `custom_fields` write/read parity for the wired artifact types, an `icd` MCP tool group behind the new `ArtifactAttributeGateway`, artifact-type discovery and section coverage, plus a REST/MCP transport contract-matrix ratchet that pins the behaviour (PRs #943, #945; #935)
- **Attribute System v3 — Identity & System Fields (WS2):** New `Actor` entity and `ActorService` with a gateway adapter; `owner`, `reporter` and `priority` wired as system fields across the remaining artifact types (Adr, Issue, CR, …); new `ActorPicker` and system-field rendering; `uid` degraded to an import key while `id` is exposed as a system field (PR #945; #936)
- **Attribute System v3 — Display Engine (WS3):** Display properties (`copyable`/`reveal`/`mask`/`format`) added to the attribute schema, a `RevealValue` wrapper and a generalized `ArtifactId`, plus id display-property backfill and mask/a11y fixes (PR #945; #937)
- **Attribute System v3 — Layout Engine (WS4):** A 12-column layout flow schema with a matching renderer/editor, and a defined empty-vs-absent contract for flows (PR #945; #938)
- **Attribute System v3 — Central Attribute Catalog (WS5):** A central attribute-catalog backend and UI entry, with capped catalog text fields and length validation (PR #945; #942)
- **Attribute System v3 — AWMS Value Migration (WS7):** A migration engine and interfaces plus the first AWMS migration plans, including pinned dry-run actor safety (PR #945; #940)
- **Attribute System v3 — Specification & ADR-004:** The attribute usability contract, the v3 specification with 3-stage matrix, the ADR-004 carrier model, and documentation of staged system-field visibility (PRs #931, #943, #945; #934)

### Fixed
- **Attribute v3 Hardening:** The workflow-status editor stays interactive under `workflow-editable`, malformed workspace preset blobs are normalized to a valid tier, the Risk `owner_name` PATCH and the AWMS actor fallback are corrected, catalog text fields are capped/validated, and N+1 status resolution on list paths is avoided (PR #945)
- **Preset `mandatory_fields` Scoped per Item Type:** Mandatory fields are now resolved per workspace/item-type definition instead of a flat workspace list, fixing the beta.10 QA finding where 22 preset mandatory fields silently matched no attribute (#912) (PR #943)
- **B1 API-Contract & B4 Embedding Bugfix Bundle:** `test_type` is accepted again in the TestCase create contract (#864), the trace-link picker is de-duplicated by artifact id (#832), `artifact.search` relevance scores are normalized to [0,1] (#827), the embedding dimension is environment-configurable (#826), missing embeddings are generated lazily for similar-search (#847), Celery-beat liveness is reported via heartbeat (#822), and the Honcho embedding config/health probe is parametrized (#911) (PR #933)
- **E2E Visual-Regression Stability:** Visual-regression snapshots are stabilized against CI drift (PR #910)

### Changed
- **Attribute System v3 — Staged Rollout (WS6):** The 3-stage attribute matrix is rolled out (priority and MoSCoW retained for the Need type only), with the staged system-field visibility documented (PR #945; #939)
- **MCP Tool Manifests Regenerated:** Regenerated for the system-field schemas, the `attribute_migration` tools and the Risk system fields (PRs #943, #945)
- **Test Infrastructure & CI:** Backend-test timeout raised for cold set-3 MCP installs, non-prod throttle rates pinned in test settings, the attribute-definitions suite added to the backend test matrix, and backend fixtures mounted into the frontend-test job (PRs #933, #943)
- **Frontend Package Version Synchronized:** `frontend/package.json` and `frontend/package-lock.json` now track the repository `VERSION`; both had stayed at `1.0.0` through earlier betas despite the distribution versioning rule requiring exact agreement

## [1.8.0-beta.10] — 2026-09-11

### Added
- **Attribute Definition v2 — Create/Delete, Sections, Export/Import:** Custom attribute definitions can now be created and deleted at both Global and Workspace scope through one shared validation path (snake_case, uniqueness, no collision with a real Django model field) that the existing edit flow already used. Adds a table/list-view toggle, an options editor for enum/multi-enum attributes with a `count_usages` safety check before removal, per-attribute origin badges + type icons, `sections[]` with visibility toggling and a half/full CSS-Grid layout (stored in `definition_json`, no migration, lazily materialized), and export/import of definitions at both scopes with skip/overwrite/rename collision handling plus a REST + MCP surface (PRs #901, #902, #905)
- **AI Proposal State (Rule 0):** Agent-authored workflow items (MainGoals, Requirements, TraceLinks, …) are created in a new `proposed` state and can never be confirmed by the same agent — enforced across direct transitions, `outdate()`, bulk-confirm, and both hard-delete paths. Trace-link proposals are now exposed over REST (list/confirm/discard), including the previously unserialized `proposed_by`/`proposed_at` fields, and the frontend review queue gained an AI-proposals mode with bulk confirm (PR #904)
- **Agent API-Key Identity & Scoping:** `ApiKey` now carries agent identity, scope and expiry fields; read-scoped keys are denied writes, workspace-restricted keys are fenced out of other workspaces, and audit entries record the caller's real `actor_type` instead of a hardcoded `user` (PR #904)

### Fixed
- **Interview Engine — Formalization, Provenance, Transcript & Surface:** `formalize()` now dispatches through the `ARTIFACT_CREATION_ADAPTERS` registry for all 8 in-scope artifact types instead of Requirement only, fixing real crashes for ArchitectureElement and Risk; interview provenance is shown on every artifact detail view for single- and multi-kind sessions; `InterviewSession.transcript_summary` plus a sliding-window compressor caps prompt growth after 10 turns (fixing transcript data loss with the default mock provider); and `/interviews?start=multi` is now a real discovery entry point while the floating widget is reduced to a launcher (PR #903)
- **API-Key Scope Bypass:** Enforced key scope on ~25 REST views that used `RbacPermission`/`HasOperationPermission` without checking it, and closed the same bypass on the MCP tool-registry's RBAC-exempt paths; `main_goal.approve` now resolves its target state by meaning instead of list position (PR #904)
- **Attribute Definition Round-Trip and Guards:** Export/import no longer drops `sections[]`, import runs the same name validation as create (including the core-field-collision guard), workspace-scoped create/delete return 403 (not 500) for a foreign workspace, `count_usages` correctly counts multi-enum option usages, a required attribute inside a hidden section no longer blocks artifact creation, and renaming/deleting a section keeps its visibility/layout state in sync (PR #905)

### Changed
- **Agent-Meta v1.1.0 Upgrade:** Upgraded the agent-meta framework to v1.1.0, tuned auto-commit roles and thresholds, and untracked generated provider directories (PRs #906, #908, #909)

### Known Issues
- Multi-mode interview sessions do not yet trigger transcript compression (the compressor call site is single-mode only); multi-mode assistant chat entries also display the raw fenced JSON proposal block alongside the parsed proposal card (cosmetic) — both documented as non-blocking follow-ups in PR #903
- Cascading delete of a non-proposed artifact can still remove attached `proposed` trace links — a deliberate non-fix in PR #904
- Two minor attribute-definition UX polish items were deferred (option removal keyed by value instead of index; raw `exc.message` instead of `extractErrorMessage` in two dialogs) — PR #905

## [1.8.0-beta.9] — 2026-09-11

### Added
- **Native Codex CLI Package:** New distribution artifact at `dist/codex/` enabling command-line access to ReqogniLoom capabilities via the Codex protocol. OpenCode integration now surfaced and documented in release checklist (PR #900)

### Fixed
- **Link-Types Migration 0081 Legacy Data Handling:** Migration now correctly grandfathers existing real-world trace links that predate the eight-type catalog system, preventing deployment failures on existing databases with legacy link data (PR #896)
- **Frontend Container Restart Loop on Non-Root Execution:** Removed tmpfs mount that shadowed the nginx cache directory in non-root deployments, fixing persistent restart loops during production deploys (PR #897)

### Changed
- **Release Automation:** Hermes IDE plugin version now automatically synchronized to repo VERSION during release process; tag-schema-consistency validation added to pre-release checklist to prevent deploy-automation breakage from malformed version tags (PR #899, PR #898)

### Dependencies
- Dependency updates: dompurify, @tanstack/react-virtual, @xyflow/react, react-router-dom, openai, gunicorn, reportlab, pypdf, sentence-transformers, github/codeql-action, and transitive pins (PRs #833–#843)

## [1.8.0-beta.8] — 2026-09-10

### Fixed
- **Backend Docker Image Size Regression:** Reduced backend image size from 9.23GB to 2.56GB (72% reduction). Root cause: duplicate CUDA torch installation from two separate `pip install --prefix=/install` invocations that did not share resolved-package state. Fixed by consolidating into a single `pip install` pass with explicit CPU-torch index URL, eliminating redundant nvidia package bloat while maintaining pytest/pytest-django and embedding smoke test functionality (PR #892)

## [1.8.0-beta.7] — 2026-09-10

### Added
- **Tenant-Configurable Trace Link Types Catalog:** Replaced hardcoded 14/15 trace-link types with an open, extensible `link_types` catalog app, allowing tenants to define custom link-type names, symbols, and semantics within project policies (PR #891). **Breaking wire-contract change:** old 14-type names (`parent-child`, `derives-from`, etc.) are no longer directly embedded; migration provided for existing deployments
- **Attribute Definition System & Definition-Driven Artifact Forms:** New `attribute_definitions` app enabling per-workspace definition of custom artifact fields with type, validation, and UI hints; artifact forms now render fields dynamically from attribute schemas instead of hardcoded layouts. Enables flexible schema extension without schema migration (PR #888)
- **Data Model Consolidation — One Artifact, One Diff World:** Unified generic artifact persistence layer across all content types (Requirements, Tests, Architecture, etc.), eliminating parallel domain-specific models. Single `Artifact` entity with configurable rigor presets, unified diff engine, and consolidated trace-link handling. Baseline and version-control semantics simplified (PR #880)
- **SystemAudit Follow-Up Specs:** 11 specification documents for post-beta features, including architecture views (Document, Role-based), table editing, MCP modernization, GitHub-Jira integration, interview engine improvements, and AI suggestion workflows (PRs #852–#863)

### Fixed
- **P0 Security & Robustness Hardening:** CSRF token enforcement across all state-changing endpoints; secure HttpOnly/SameSite cookie configuration; role-gated UI elements (Viewer/Editor permissions); traceability relationship cardinality guards; MCP tool audit declarations (stdio-only API-key parameter); AI decomposition robustness improvements; exception handling leaks in tool registration (PR #844)

### Changed
- **Release Infrastructure:** Added project-specific pre-release checklist to prevent recurring CI gate failures (VERSION-embedded artifact regeneration, Docker CVE scanning, GitHub Actions pin auditing); GitHub Release creation now mandatory (PR #819)

## [1.8.0-beta.6] — 2026-09-02

### Fixed
- **Bugfix Batch — 17 Issues Resolved:** Comprehensive batch of 17 bug fixes across REST API, MCP tooling, and E2E test infrastructure. Four self-found regressions were caught by E2E suite during QA (PR #817)

### Changed
- **Deploy Documentation & Compose Consolidation:** Optimized deployment instructions and consolidated Docker Compose files for clarity (PR #812)

## [1.8.0-beta.5] — 2026-08-31

### Fixed
- **Docker Backend Image Trivy CVE Gate:** Resolved CRITICAL and HIGH vulnerability findings in backend Docker image CI pipeline (Fixes #791). Root causes: stale duplicate setuptools metadata from two independent builder-stage pip installs without visibility; outdated pip vendoring vulnerable msgpack; unpinned msgpack transitive dependency. Fixes: removed pip from runtime image (build-time only), unified single pip install, ensured proper cache invalidation, removed pip/setuptools/msgpack SBOM poisoning (#791)

## [1.7.0] — 2026-08-23

### Added
- **System & Workspace Banners:** Admins can now publish dismissible notice banners at two scopes — a single global banner managed by System Admins in System Settings, and a single per-workspace banner managed by the Workspace Admin (or a System Admin) in Workspace Settings. Four severity levels (Neutral, Info, Warning, Critical), Markdown rendering via `react-markdown`, activate/deactivate toggle, session-scoped dismissal that is invalidated whenever an admin edits the banner, and a "dismissible" flag (Critical banners default to non-dismissible but can be configured otherwise). Banners are also shown on the public login page (#712 design, #713 implementation)

### Fixed
- **RBAC/Tenant Permission Matrix:** The Viewer role could incorrectly create API keys, and the `permissions.check` MCP tool did not accurately reflect the real RBAC matrix (Fixes #716, PR #723). The reported last-admin-guard bypass (#708) was investigated and could not be reproduced against current code; an analysis comment was left on the issue, which remains open for re-verification rather than closed as fixed
- **MCP Requirement Creation — XSS Sanitization Regression:** Fixed a regression where input sanitization was bypassed when creating requirements via MCP, reopening an XSS vector (Fixes #709, PR #721). The inconsistent UUID error-handling report (#710) was left open as a product decision requiring input rather than a code fix; an analysis comment was left on the issue
- **LLM Settings — Key Precedence & Error Classification:** A DB-stored LLM key no longer incorrectly overrides a configured environment key; authentication failures and transient/network failures are now classified distinctly, with clearer circuit-breaker diagnostics (Fixes #714, PR #717)
- **Baseline Creation — Document Scope Validation:** `baseline.create` with `scope=document` no longer raises an internal `ValueError`; it now returns a proper validation error (Fixes #715, PR #725). A related malformed-UUID 500 response leak was split out into follow-up issue #724
- **Editor Forms:** Fixed a race condition on the `changeReason` field during a concurrent background refetch (Fixes #700); custom field values no longer leak between different entities when switching the active selection (Fixes #673); forms left via the workspace tree now correctly show an "unsaved changes" warning instead of silently discarding edits (Fixes #672) (PR #728)
- **System Health UI:** The Celery Beat "unknown" status no longer reads like a dead service — it now carries an explanatory hint that this state is by design (Fixes #706, PR #726)
- **Minor UI Fixes:** Multiple "Create Need" buttons sharing the same accessible name are now distinguishable (Fixes #678); `InterviewWidget` no longer crashes in private/incognito browsing modes where `localStorage` access throws (Fixes #679) (PR #727)

### Changed
- **Dependency Updates:** `dagre` 3.0.0 → 3.1.1 (PR #640); Anthropic SDK `<1.0,>=0.120.2` → `>=0.122.0` (PR #639); `reqif` `<0.1,>=0.0.53` → `>=0.1.0` (PR #637); `pytest-django` `<5.0,>=4.13.0` → `>=4.14.0` (PR #635). Five further dependency PRs with major-version jumps (Django 5→6, ESLint 9→10 ×2, a React bump, gunicorn 21→26) were rebased but deliberately left open — each needs its own migration effort and is not part of this release

### Known Issues
- #708: Last-admin-guard-bypass report — verified not reproducible against current code; issue stays open for monitoring/re-verification, not closed as fixed
- #682: Pre-existing E2E infrastructure issue, unrelated to application code in this release
- #707: Theming inconsistency — needs a dedicated redesign, out of scope for this release
- #722 / #724: Non-blocking follow-ups from the bugfix batch (RBAC architecture findings; a related baseline malformed-UUID 500 leak) — tracked for a future release, not release blockers
- See [`docs/UMSETZUNGSPLAN_POST-1.7.0-BACKLOG.md`](docs/UMSETZUNGSPLAN_POST-1.7.0-BACKLOG.md) for the full prioritized backlog of remaining open bug/audit issues

## [1.7.0-beta.5] — 2026-08-23

### Added
- **Multi-User Workspace Management:** Tenant admins can now suspend, reactivate, and assign roles to workspace members via new `/users/` REST endpoints and MCP tool group; includes role transition guards, last-admin invariants at both workspace and tenant scope, and comprehensive audit logging (#686)
- **Workspace Members UI:** New admin settings panel for managing workspace member lifecycle (activate, suspend, reactivate, role assignment) with permission matrix tests validating REST/MCP consistency (#686)
- **TenantRole Model:** New persistent model representing tenant-level roles (e.g., tenant-admin); backfill migration for existing multi-user tenants (#686)
- **Multi-Artifact Discovery Interview Design Spec (docs only, not yet implemented):** Design for a new interview mode that helps users determine which artifact(s) they need from a described problem, and creates multiple artifacts of the same or mixed types in one confirmed, atomic batch with cross-links and provenance back to the interview (#699)

### Fixed
- **Review Findings Remediation (17-task plan):** Comprehensive accessibility, security, i18n, and consistency fixes including:
  - WCAG §4.1.2 (form label coverage): Added missing `htmlFor`/`id` linkage across 8+ input fields (#698)
  - Keyboard Navigation (WCAG §2.1.1): Trace-link entries now focusable `<button>` elements; WorkflowEditor canvas keyboard-accessible; tree-expand toggles have `aria-label` (#698)
  - Contrast Failures (WCAG §1.4.11): Fixed sitewide contrast in `.buildVersion`, `.presetBadge`, `.langNotice`, and Bauhaus/Sepia `text-muted` (#698)
  - Hardcoded English UI Text: Translated `EnforcementFlipDialog` and 10+ additional strings to German; app now respects `navigator.language` (#698)
  - Button Styling & Semantic HTML: Unified primary-button styling; migrated 5 create-forms to Dialog primitive; removed nested interactive elements (#698)
  - Trace-Link Dialog UX: Source picker now unified searchable list (not plain `<select>`); disabled state has tooltip (#698)
  - MCP Security: Restricted `params.api_key` acceptance to stdio transport only; added missing audit operation declarations (#698)
  - Exception Handling: Stopped leaking raw exception detail from MCP `/tools/list` (#698)

- **E2E Infrastructure & CI (PR #701):** Visual-regression baseline repair and test stabilization:
  - Linux baseline screenshots: Added missing baseline images for visual-regression tests in CI-matching environment (#701)
  - Dashboard/workspace-create snapshots: Stabilized and regenerated visual baselines to match CI rendering (#701)
  - Fixed 3 pre-existing, unrelated E2E test failures that had left `main`'s CI red since 2026-08-20: `artifact-diff.spec.ts` (ArtifactInspector auto-collapse below 1600px viewport hid asserted panels; a rare `RequirementForm` save-refetch race occasionally flaked one test, root cause tracked separately in #700) and `diagram-node-graph.spec.ts` (seeded demo workspace's German locale rendered the empty-state hint differently than the test expected) (#701)

- **Backend/Frontend Hygiene:** ORM import cleanup, dead code removal, timing-safe comparisons, MCP tools ratchet ceiling adjustments (#701 series)
- **Traceability View:** Fixed long traceability IDs truncation; removed dead category filter (#701 series)
- **Architecture & Glossary Empty States:** Aligned toolbar styling with sibling pages (#701 series)
- **Layout & Component Fixes:** Resolved clipping/overlap issues across 7 components; artifact inspector defaults to collapsed <1600px (#701 series)

### Changed
- **MCP Tool Restrictions:** `params.api_key` parameter now only accepted on stdio transport; other transports (HTTP, SSE) must use header-based auth (#698)
- **Preset Resolution:** Gated preset resolution to prevent spoofing; use uncached tier for Approver gate validation (#698)

### Security
- **MCP Tool Restriction:** API key parameter locked to stdio transport, closing potential surface for cross-transport token leakage (#698)
- **CORS Origin Mirroring:** Removed auto-mirroring behavior, now validates against configured allowed origins (#698)

## [1.7.0-beta.4] — 2026-08-22

### Fixed
- **E2E Test Helpers:** `createRequirementViaQuickForm` now fills a title field before clicking save (regression from prior title-required validation fix) (#687); waterkettle TestRun helpers updated to match GH-584's backend auto-completion behavior — tests no longer expect intermediate `in_progress` state or manual close-button interaction (#690)
- **E2E UI Assertions:** 10 assertions hardcoding English UI strings now accept German variants (app follows `navigator.language`); improved test robustness for bilingual deployments (#688)
- **E2E Spec Stability:** `needs-cross-boundary.spec.ts` added stable `data-testid` to form inputs to satisfy Playwright strict-mode checks (#689); `toothbrush-syseng.spec.ts` now skips gracefully with clear reason when required seed data is missing instead of failing hard (#691)
- **E2E Documentation & Defaults:** Fixed `BACKEND_URL` default from `8000` to `8001` across all E2E specs/helpers to match `docker-compose.yml` (#691); README.md updated with correct URLs
- **E2E Infrastructure:** Raised `/traceability` view loading-state timeout from 10s to 30s to reduce flakiness under full-suite sequential load (#692); removed unresolved git-merge-conflict markers from `.gitignore` (#693)

### Known Issues
- #504: Two pre-existing E2E shard failures (`artifact-diff.spec.ts` timeout on diff panel PUT response; `diagram-node-graph.spec.ts` unrelated infrastructure timeout) persist in CI but are unrelated to application or E2E framework changes in this release — not a regression from beta.3
- Baseline on 1.7.0-beta.3; no new application bugs introduced

## [1.7.0-beta.3] — 2026-08-20

### Added
- **Interview Workflow Integration:** Interview sessions are now workflow-tracked and reachable from the UI via a new `/interviews` route, sidebar entry, and CTA buttons on artifact list pages (#590 area work, PR #641)
- **Non-Atomic Requirement Hint:** Requirement titles containing "and"/"or" now surface a non-blocking `atomicity_warning` on the REST response, per IEEE 29148 §5.2.4 (#45)
- **API-Key Hygiene:** `MAX_ACTIVE_API_KEYS_PER_USER` is now environment-configurable instead of a fixed constant; new `cleanup_revoked_api_keys` management command purges old revoked keys (dry-run by default) (#606)
- **i18n Coverage Ratchet:** New source-scanning test catches translation keys referenced in code but missing from both locale files, frozen at the current baseline so the gap can only shrink (#619)
- **Audit Findings Pagination:** `GET /api/v1/workspaces/<id>/audit/` now accepts `?limit=&offset=` to page through findings past the existing 500-finding cap (backend/REST only — dashboard UI consumption is a follow-up) (#622)
- **Hermes IDE Plugin Port:** Ported to the current `@hermes/plugin-sdk` contract (ESM `dist/plugin.js`, `{id, name, register(ctx)}`) — code-complete and merged; a live load-test in a real Hermes desktop app is still outstanding (#599, PR #633)

### Fixed
- **Login over HTTP:** `AUTH_COOKIE_SECURE` now defaults to `False` for the local/dev docker-compose path, fixing every fresh quickstart login being silently rejected by the browser over plain HTTP (#589)
- **Trace-Link Query Performance:** Removed an N+1 query in `trace_link_manager`'s cycle/adjacency checks (#629)
- **MCP Audit Vocabulary:** Closed 17 call sites where an undeclared `operation` value caused `write_mcp_audit()` to silently write zero audit rows (#626)
- **Mermaid Editor:** Status bar now reflects the live client-side parse instead of a stale server-side preview (#259)
- **Workflow Seeding:** `seed_demo` and `bootstrap_admin` now provision default workflow definitions, matching `self_init`'s existing behavior (#41)
- **Workflow Editor Responsive Layout:** Header no longer overflows horizontally on narrow viewports (#596, partial — the `/audit` large-DOM concern in the same report is a deliberate cap-vs-pagination trade-off, not a regression)
- **`/prompts` Route:** Redirects into the Settings LLM tab instead of silently bouncing to the dashboard (#609)
- **i18n Locale Gaps:** Added missing `impact.*`/`nav.*` keys so English UI no longer falls back to German placeholder text (#54); 9 further confirmed leaks fixed under the new coverage ratchet (settings hints, needs/adrs/risks/issues delete-failure messages) (#619)
- **Artifact Inspector Layout:** Defaults to collapsed below 1600px viewport width (applies to all 10 artifact types sharing the component); Save-button/title-heading overlap fixed in the requirement editor header (#419)
- **Trace-Link Create Dialog:** Source picker unified with the target picker's searchable list instead of a plain unfiltered `<select>`; disabled submit button now has a tooltip explaining what's missing (#53)
- **Accessibility:** Need-form field labels linked via `htmlFor`/`id`; trace-link entries in the Traceability view are now keyboard-focusable `<button>`s that navigate to the linked artifact instead of inert text; tree-expand/collapse toggle buttons have `aria-label` (#425)
- **AI Review Timeout:** `audit.ai_review` already converted a hung/slow LLM provider into a clean error (#342) — added a regression test pinning that behavior (#312)

### Security
- **react-router-dom 6.30.4 → 7.18.2:** Resolves 2 moderate CVEs (GHSA-wrjc-x8rr-h8h6, GHSA-337j-9hxr-rhxg) (#261)

### Known Issues
- #414: Traceability/Impact views still expose both Artifact-id and entity-id inconsistently in most places; the trace-link navigation fix in this release (#425) resolves one instance of the pattern, not the underlying architectural issue
- #504: Two pre-existing E2E shard failures (`review-workflow.spec.ts`, `stakeholder-needs.spec.ts`) could not be re-verified live in the environment this release was prepared in (seeded admin credentials rejected at the API level, unrelated to application code); static review confirms the referenced #412 fix is present in source
- Baseline on 1.7.0-beta.2; no new regressions identified against it

## [1.7.0-beta.2] — 2026-08-17

### Fixed
- Interview widget TypeError: guard against missing grounding_snapshot.candidates when artifact type is clicked in interview assistant (#602)
- Diff UI dropdowns and app-wide scroll containment: fixed empty version dropdowns (Versions-Filter schloss einzige Version aus) and systemwide scroll overflow in NavigationShell (#603)

### Known Issues
- None new in this beta
- Baseline on 1.6.0 stable; all beta.1 issues resolved

## [1.7.0-beta.1] — 2026-08-16

### Added
- **Centralized Prompt Variable Catalog:** Unified configuration system for AI prompt variables across REST API and MCP, enabling dynamic prompt slot configuration without code changes (#600)
- **Prompt Variable REST/MCP CRUD:** New `/api/v1/prompt-variables/` endpoints and `prompt_variable` MCP tool group for catalog management (#600)
- **Workspace Settings UI:** New prompt variable management section in workspace configuration panel (#600)
- **Architecture Decompose Safeguards:** Migrated decompose breadth/depth constraints into configurable catalog variables with absolute blast-radius ceiling enforcement; AI decomposition now respects upper bounds from catalog (#600)
- **Prompt Variable Auto-Injection:** Config variables automatically injected into prompt slots at request time; per-slot variable display and placeholder validation in UI (#600)
- **Prompt Resolver Consolidation:** Unified prompt reading across AI derivation service, interviews, and MCP context generation via PromptVariableService (#600)

### Fixed
- Scope-lookup precedence corrections in PromptVariableService.set_variable (#600)
- Stale {n} placeholder migration in existing need_to_sysreq rows (#600)
- Config variable resolution performance: resolve max_requirements_per_need once per request (#600)

### Known Issues
- None new in this beta
- Baseline on 1.6.0 stable; all beta.3 issues resolved

## [1.6.0] — 2026-08-16

Promotion from beta.3 after comprehensive testing and stabilization. Beta.3 known issues resolved; 123 commits adding interview management, goals redesign, architecture improvements, and numerous bugfixes.

### Added
- **Interview Management Engine:** Complete lifecycle for structured requirement interviews with state machine, protocol configuration, AI-assisted grounding ranking, and formalize operation (#543, #540, #541, #542, #544)
- **Interview Management Hermes Plugin:** Web-based interview conductor for Claude Code plugin ecosystem with workspace selection, form rendering, and typed field submission (#546, #547, #548)
- **Interview Management Web Widget:** Native React UI component for hosting interview workflows within ReqogniLoom (#549)
- **Interview MCP Tool Group:** REST API and MCP facades for interview.start, interview.answer, interview.formalize, interview.list, interview.get, interview.set_target with full RBAC (#543)
- **Goals UI Redesign:** Complete overhaul with action toolbar, multi-select, search/filter, modal create, archive functionality, and ArtifactInspector version-history wiring (#564, #565, #566)
- **Architecture Drag-and-Drop Reparenting:** WorkspaceTree now supports tree node drag-drop for efficient architecture element reorganization (#550)
- **UI List Virtualization:** Adr, Risk, Issue, and TestCase list views now virtualized via WorkspaceTree for improved performance on large artifact sets (#553)
- **MCP RBAC Test Coverage:** Regression tests ensuring RBAC enforcement on MCP tool calls (#538)

### Fixed
- **LLM Provider:** Honor configured model_name in Ollama, OpenCode, Mock, and Azure adapters; prevent silent fallback to provider default (#559)
- **Cache Race Condition:** AiDerivationService cache key now threaded through service layer instead of instance state, fixing concurrent LLM request collisions (#561)
- **Baseline/Diff Service:** Register Goal and MainGoal artifact types in diff service to enable field-level diffs (#563)
- **Test Runner:** Decouple test runner from base compose service images to enable independent source mounts (#562)
- **Baseline Override:** Add justification field for SE-Auditor override on blocked baseline finalization (#554)
- **TypeScript Errors:** Resolve remaining tsc errors in CanvasEditor and related components (#557); add QueryClientProvider wrapper for CanvasEditor tests (#555)
- **MCP Admin Audit Gap:** Register missing audit operation names for MCP admin tools (#556)
- **UI Scrollbar Affordance:** Add visible scrollbar to sidebar navigation (#551)
- **LLM Derivation:** Stop silently discarding unusable LLM derivation output; prevent empty draft inflation (#552)
- **Action Label Consistency:** Standardize create-action button labels across artifact lists (#558)
- **Baseline Styles:** Extract BaselinesView override panel styles to CSS module for improved maintainability (#560)
- **Hermes Plugin Build:** Add postbuild guard against inlined React in Hermes plugin bundle (#547)
- **Tenant Context Teardown:** Guard tenant context cleanup in LLM worker to prevent stale reference crashes (#528)
- **Glossary & MCP:** Glossary soft-delete visibility and MCP get_context UUID crash fixes (#474)
- **Draft Reload & i18n:** Goal/MainGoal panel draft reloading after backend refresh and i18n label consistency (#565, #566)

### Known Issues
- #393: MOE/MOP/TPM (Measures of Effectiveness, Performance, Production) metrics not yet integrated into reporting dashboard — feature planned for next release
- Multiple SE Methodology findings from architecture review (open for prioritization in upcoming planning)
- No regressions from beta.3; both beta.2 known issues (#455, #456) remain resolved

## [1.6.0-beta.3] — 2026-08-13

### Security
- Fixed cross-tenant baseline data leak (ADR-03 Row-Level-Security isolation) (#464)
- Fixed cross-tenant ICD read/mutate leak in architecture element access control (#466)
- Enforce admin role validation on AttributeVisibilityConfigService CRUD operations (#470)
- Fixed authentication error handling: missing credentials now return 401 instead of 403 (#476)

### Breaking Changes
- TestCase status field now lowercase to match other entity naming conventions (#481)
- Deleted requirements are now readable via standard entity endpoints, reversing previous silent-remove behavior (#482)

### Added
- Requirement Bundle Export UI panel for streaming/downloading compressed artifact bundles (#463)
- Hermes IDE Plugin Connector MVP: lean connector with workspace selection, requirements list/detail, and auth flow (#507)
- Volatility metric now resolves requirement titles for improved reporting (#480)

### Fixed
- **SE Methodology & Data Integrity:** Multiple audit-driven fixes from security bughunt campaign
  - Prevent silent SE field loss on PATCH/MCP requirement operations (#486)
  - SE-metrics dashboard no longer reports false-safe zeros for uninitialized metrics (#487)
  - Make Risk/Issue trace-linkable and add acceptance_criteria field support (#488)
  - Correct trace-hierarchy classification for derives-from links (#489)
  - SE-auditor gate now fail-closed; reject baselines with unverified BLOCKER findings (#490)
  - Enforce human review gate for extended-tier workspace baselines (#491)
  - Correct trace-link type documentation to match 15-type enum (#493)
  - Display requirement level (V-model L0–L4) in UI artifact headers (#494)
  - Keep TraceLinks alive across TestCase/Issue/Risk soft-delete + reactivate; exclude outdated TestCases from coverage calculation (#484, PR #509)
- **Baseline:** Fix `TypeError` in `baseline/tests/test_diff_value_based_398.py` after `DiffEngine.diff()` gained a required `tenant_id` parameter (#464 follow-up); adds explicit cross-tenant isolation regression test (#483, PR #508)
- **MCP & API Transport:** Enable SSE transport via ASGI; REST API bundle/schema consistency aligned (#485, #477, #462)
- **Plugin Marketplace:** Write Claude Code plugin marketplace.json to correct path (#492)
- **Permission & Auth:** Workspace-scope admin checks for permissions.revoke and events.dlq_* operations (#467); enforce REQ-106 token budget and audit trail for 3 LLM copilot flows (#471)
- **UI State Management:** RequirementForm now resyncs state on requirement selection change (#472, #473); CustomFieldsEditor no longer updates parent state during render (#475); dashboard controls no longer stuck disabled on unbounded requests (#479)
- **Other Fixes:** Glossary soft-delete visibility and MCP get_context UUID crash (#474); ArchitectureElement update conflict handling (#469); TransitionValidator cache invalidation on workflow edits (#465); bundle compression no longer misreports mock output (#478); ICD/PDF-export E2E regressions fixed (#503); stale plugin distributions regenerated (#502); Hermes plugin auth error handling (#507)

### Known Issues
- None new in this release
- Resolved from beta.2: #455 (SSE transport 500, fixed via #485), #456 (plugin marketplace.json path, fixed via #492)

## [1.6.0-beta.2] — 2026-08-09

### Added
- Regenerated MCP plugin distributions (Claude Code, OpenCode, Antigravity) with the Requirement Bundle Export/Compression tools (#457)
- Renamed `requirements-architect` role to `requirements-architecture-manager` with new bundle-export tool access (#457)
- Renamed internal `reqflow` operator agent to `reqogniloom-operator` (#457)

### Known Issues
- #455: SSE transport (/mcp/sse/) returns HTTP 500 under local dev server — HTTP transport works as a workaround
- #456: Claude Code plugin build writes marketplace.json to the wrong path

## [1.6.0-beta.1] — 2026-08-09

### Security
- Fixed 3 security findings in BundleCompressionService: token budget bypass vulnerability, cross-tenant data leak in caching layer, cache poisoning on LLM provider switching (#436)

### Added
- BundleCompressionService: compressed and asynchronous artifact export via REST API and MCP (#436)
- Async requirement bundle export pipeline with token-aware compression (#436)

## [1.5.0] — 2026-08-05

> Note: a `v1.4.0` git tag exists in this repo's history (on commit `faafc354`,
> 2026-08-03) but the `VERSION` file was never bumped to match at that point -
> this release corrects the drift and is versioned relative to the actual
> last file-tracked version (1.3.0), not the stray tag.

### Breaking Changes
- **SE Governance:** Baseline creation now enforces SE-Auditor review gate for BLOCKER findings; baseline snapshots with unverified critical issues cannot be finalized (#367)
- **Workflow:** Change control board (CCB) approval flow now requires distinct approvers (same-person approval rejected); verification evidence now mandatory for transitioned-to-verified state (#367)

### Security
- Fixed stored XSS vulnerability in diagram SVG preview via attribute sanitization injection (#351)
- Backend/API/MCP: patched custom field and baseline scoping security gaps (#354)

### Added
- MCP connection info panel in workspace settings showing real-time connection status and endpoint details (#358)
- SE-conformance enforcement: mandatory field validation gates on baseline creation and requirement state transitions (#367)
- SE-Auditor blocking gate: prevents baseline finalization when BLOCKER audit findings are unresolved (#367)
- Verification evidence requirement: enforces artifact evidence submission for verified workflow state (#367)
- UI-Konzept full rollout (Phases 0–8): complete design-system implementation across all artifact types
  - Phase 0–1: shared primitives (Dialog, ListToolbar, cards, buttons)
  - Phase 2: ADR/Risk/Issue/TestCase form layouts
  - Phase 3: Requirements + Trace-Spine visual refinement
  - Phase 4a: tree keyboard navigation
  - Phase 4b: RequirementTreeNode + virtualization
  - Phase 5: remaining routes (remaining artifact pages)
  - Phase 6: Diagrams layout per E2 decision
  - Phase 7: enforcement gates UI (7.1, 7.2, 7.3, 7.5)
  - Phase 8: theming primitives and IBM Plex typography
- IBM Plex font family integration for improved visual hierarchy and multilingual support

### Fixed
- 2 CRITICAL AI/LLM bugs: fixed write-mode persistence data loss and workspace-wide LLM tool timeouts causing 500 errors (#361)
- 3 HIGH bugs: requirement save data corruption, LLM provider dropdown safety, MCP schema/search accuracy (#367)
- Goal state transitions now driven dynamically; completed goal MCP lifecycle integration (#357)
- Header font-family and summary display inconsistencies identified by live audit (#356)
- UI component count unification and non-artifact page header inconsistencies (#348)
- 25 remaining audit-2026-07 UI/backend issues resolved (#347)
- GoalsTree false-positive entry in tree-implementation ratchet (#334)
- Deployment example documentation drift corrected (#335)

### Changed
- SE governance model: baseline scope now enforces artifact-level conformance on finalization
- Workflow engine: added ChangeRequestAffectedItem model for enhanced change-control traceability (#367, migration 0014)
- Goal transitions: refactored to use dynamic state-machine evaluation for improved reliability

### Infrastructure
- Added database migration 0014 for ChangeRequestAffectedItem model supporting change-control linkage

## [1.3.0] — 2026-08-02

### Security
- Fixed rate-limiting and login-throttle DoS vulnerability; added XSS sanitizer (#269)
- Patched pytest CVE-2025-71176 (predictable temporary directories)
- Patched pypdf CVEs (36 vulnerability fixes)
- Patched brace-expansion dependency CVE

### Added
- MCP tools: `goal.query` and `goal.delete` for goal management (#216)
- Shared Dialog primitive component and architecture legend for consistent dialogs across UI
- Goals page rebuilt as SplitView with tree/detail layout for improved navigation

### Fixed
- MCP dispatch RLS test coverage: added missing `@pytest.mark.django_db` marks for integration tests (#222, #310)
- MCP tool registry database marking and migration to application services (#124, #288)
- MCP validation: return proper validation errors for missing required fields in adr/risk creation
- Critical MCP bugs: resolved traceability.create_link edge cases and race conditions
- Goal/MainGoal detail tool inconsistencies and state management (#270, #285)
- ICD (Integrated Architecture Diagram) delete operation, mermaid UUID crash, and auto-save stale closure (#286)
- Workspace deletion 500 error on confirm and silent no-op on success (#265)
- RBAC role-rejection error code comparison (#214)
- Preset policy service incorrectly using tenant_id instead of workspace_id (#215)
- Critical data-loss bug: PATCH requests losing fields due to status echo and silent field ignoring (#263)
- LLM provider configuration: prevent DB-seeded mock from overriding .env-supplied config (#276)
- Requirements endpoint search query parameter wiring (#267)
- Stale Playwright E2E selectors and fixtures causing false E2E failures (#284)
- Row-Level-Security (RLS) policies for new goal/adr/change-request synthetic views (#217, #282)

### Changed
- Backend test suite restructured: split into parallel test matrix (4 independent sets) for faster CI feedback
- Create-need button moved into ListToolbar for cleaner Goals page layout
- Version stamping: resolved drift between Docker image labels and runtime app version (#266)

### Infrastructure
- PostgreSQL pgvector extension now provisioned via init hook with proper permissions (#306)
- Nginx proxy configuration: added missing SSE buffering and upload size headers for large artifact uploads (#90, #300)
- CI self-detection false positive fixed; parallel test execution now reliable

## [1.0.1] — 2026-07-26

### Added
- GHCR image publishing CI pipeline for containerized releases
- docker-compose.ghcr.yml: Full 8-service example using GHCR registry
- docker-compose.minimal.yml: New 6-service reduced deployment example
- Unraid deployment documentation migrated from Codeberg to GHCR registry

## [1.0.0] — 2026-07-23

### Changed
- Complete product rebranding: ReqFlow → ReqogniLoom (Prefix: ReqLo)
- Django project package renamed from `reqflow` to `reqogniloom` (BREAKING)
- API key prefix changed from `rf_` to `reqlo_` (BREAKING)
- JWT issuer and audience identifiers updated to ReqogniLoom (BREAKING)
- Auth cookie name updated (BREAKING)

### Added
- Configurable app display name in frontend (allows easy whiteboarding for custom deployments)

### Fixed
- Multiple critical deployment and container runtime issues resolved
- Nginx PID redirect to /tmp for non-root container compatibility
- MCP generic CRUD response serialization for datetime/date/Decimal values
- WorkflowEngineDefinition auto-provisioning on workspace create
- TraceLink query routing fixed (missing list_incoming/list_outgoing)

### Notes
- **BREAKING CHANGE ADVISORY**: Existing ReqFlow instances must migrate:
  - Session tokens will be invalidated (users must re-login)
  - API keys must be regenerated with new `reqlo_` prefix
  - JWT tokens using old issuer/audience will be rejected
  - Custom cookies referencing old names must be updated

## [0.2.0] — 2026-07-19

### Added
- Admin system health dialog showing real-time status of all backend components
  (database, cache, Celery workers) and recent audit log entries
- `GET /api/v1/version/` endpoint exposing the deployed git commit SHA
- Backend version (git commit SHA) displayed inside the System Health Dialog
- Application version injected at build/release time and surfaced end-to-end
  across frontend and backend (including the login page)

### Fixed
- Auth cookie `Secure` flag decoupled from `DEBUG` setting — cookies are now
  always secure in production regardless of `DEBUG` state
- Default `WorkflowEngineDefinition` is provisioned automatically on workspace
  create/clone, preventing missing-workflow errors on fresh workspaces
- LoginPage version fallback text now uses an i18n key instead of a hardcoded string

### Changed
- Release lifecycle hooks configured to automate version injection during builds

### Docs
- Documented E2E testing gap for stale host/session drift (no code change)

## [0.1.0] — initial baseline

Initial public state of the repository.
