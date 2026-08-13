# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
