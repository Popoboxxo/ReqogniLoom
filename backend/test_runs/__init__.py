"""
backend.test_runs — Test Run domain helpers (A.6).

A thin Python module (not a Django app) that holds:
  - Pure-Python service helpers used by the REST API for the TestRun ↔
    Requirement verifies chain (REQ-L1-035).
  - Tests for those helpers and for the related REST endpoint.

The actual TestRun ORM models and the TestRunService CRUD live in
``persistence.models`` and ``application.test_run_service`` respectively.
This module is a read-only chain walker on top of those primitives and
exists to keep the chain logic out of the ViewSet layer.

REQ-L1-035 Test-Run-Protokollierung mit Ausführungsstatus.
"""
