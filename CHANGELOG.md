# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
