# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
