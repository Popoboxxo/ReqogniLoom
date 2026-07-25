# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
