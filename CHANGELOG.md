# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-07-17

### Added
- Admin system health dialog showing real-time status of all backend components
  (database, cache, Celery workers) and recent audit log entries
- `GET /api/v1/version/` endpoint exposing the deployed git commit SHA
- Backend version (git commit SHA) displayed inside the System Health Dialog

### Fixed
- Auth cookie `Secure` flag decoupled from `DEBUG` setting — cookies are now
  always secure in production regardless of `DEBUG` state
- Default `WorkflowEngineDefinition` is provisioned automatically on workspace
  create/clone, preventing missing-workflow errors on fresh workspaces

### Docs
- Documented E2E testing gap for stale host/session drift (no code change)

## [0.1.0] — initial baseline

Initial public state of the repository.
