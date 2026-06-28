# MCP E2E Test Coverage Report — 2026-06-28

## Zusammenfassung

| Metrik | Wert |
|--------|------|
| Datum | 2026-06-28 |
| Branch | `feat/se-implementation` |
| MCP-Tools gesamt | 40 |
| Tools mit Happy-Path-Test | 40 / 40 (100%) |
| Tools mit Auth-Check | 5 (representative) |
| Write-Tools mit RBAC-Denial-Test | 23 / 23 (100%) |
| Write-Tools mit Audit-Log-Test | 23 / 23 (100%) |
| Tools mit SSE-Transport-Test | 3 (representative: requirement.query, workspace.close, requirement.get) |
| Tools mit Performance-Test | 4 (requirement.query, permissions.list, audit.query, user.list) |
| **Neue Tests total** | **183** |
| Bestehende Tests (Baseline) | ~405 |
| **Test-Suite Total (nach Wellen 1-3)** | **~588** |

### Neue Tests — Aufschlüsselung

| Welle | Datei | Tests | Details |
|-------|-------|-------|---------|
| Welle 1 | `test_tenant_context_activation.py` | 7 | 6x TenantContext-Lifecycle + 1x regression (get_tenant raises) |
| Welle 2 | `test_e2e_all_tools.py` | 130 | 40 Happy-Path + 23 RBAC + 6 Auth + 6 JSON-RPC + 6 Error-Code + 2 Captcha + 3 Preset-Feature + 9 Smoke + 35 standalone |
| Welle 3a | `test_e2e_sse_transport.py` | 6 | Read/Write/Error/Auth/RBAC/Parse über SSE |
| Welle 3b | `test_e2e_audit.py` | 36 | 23 parametrisierte Write-Tool-Audit + 7 Feld-Validierung + 2 Query + 4 zusätzliche Contract-Checks |
| Welle 3c | `test_e2e_performance.py` | 4 | 4 @slow-Budget-Tests |
| **Total** | | **183** | |

## Test-Architektur

### Geänderte Production-Files
- `backend/mcp_server/tool_registry.py` — TenantContext-Aktivierung im `dispatch_request()` (try/finally). Fix verhindert `TenantContextNotSetError` bei tenant-scoped Queries innerhalb des Dispatch-Zyklus.

### Neue Test-Files
- `backend/mcp_server/tests/conftest_e2e.py` — 14 Fixtures: `admin_client`, `member_client`, `viewer_client`, `invalid_client`, `e2e_workspace`, `e2e_tenant`, `e2e_user_admin`, `e2e_user_member`, `e2e_user_viewer`, `e2e_userrole_admin`, `e2e_userrole_member`, `e2e_userrole_viewer`, `e2e_api_key_admin`, `e2e_api_key_member`, `e2e_api_key_viewer`, `e2e_api_key_invalid`, `mock_llm_configured`, `mock_backup_filesystem`, plus 2 autouse Singleton-Reset-Fixtures (`_e2e_reset_handler`, `_e2e_clear_preset_cache`)
- `backend/mcp_server/tests/helpers.py` — `make_jsonrpc_frame()`, `make_jsonrpc_request()`, `post_mcp()`, `extract_result()`, `extract_error_code()`, `extract_error_message()`, Rollen-Konstanten, Seed-Templates
- `backend/mcp_server/tests/test_e2e_all_tools.py` — 130 Tests über alle 40 Tools (2324 Zeilen)
- `backend/mcp_server/tests/test_e2e_sse_transport.py` — 6 SSE-Tests (332 Zeilen)
- `backend/mcp_server/tests/test_e2e_audit.py` — 36 Audit-Tests (1095 Zeilen)
- `backend/mcp_server/tests/test_e2e_performance.py` — 4 @slow-Tests (272 Zeilen)
- `backend/mcp_server/tests/test_tenant_context_activation.py` — 7 Unit-Tests (327 Zeilen)

### Test-Pattern

Alle E2E-Tests durchlaufen den echten Django-Request/Response-Zyklus via `django.test.Client.post('/mcp/', ...)`. Die Auth/RBAC/Tenant-Isolation/Preset-Gates sind produktions-echt (keine Mocks auf View-Ebene). Einzige Mock-Punkte:
- LLM-Adapter (Deep-Mock für decompose/validate) via `mock_llm_deep`-Fixture
- Backup-Service (BackupService/AdminRestoreService) via `mock_backup_service`-Fixture
- LLM-Configured-Check via `mock_llm_configured`-Fixture

## Tool-by-Tool-Coverage-Matrix

Legende:
- ✓ = getestet
- – = nicht getestet (im aktuellen Scope)
- n/a = nicht anwendbar (read-only tool)

### requirement.* (6 Tools)

| Tool | Happy | Auth | RBAC | Audit | SSE | Perf | Notes |
|------|-------|------|------|-------|-----|------|-------|
| requirement.get | ✓ | ✓ | n/a | n/a | ✓ (error + auth over SSE) | – | NOT_FOUND getestet |
| requirement.query | ✓ | – | n/a | n/a | ✓ (read happy over SSE) | ✓ (100 req, <2.0s) | Pagination-Test pending |
| requirement.create | ✓ | – | ✓ | ✓ | – | – | RBAC + Audit vollständig |
| requirement.update | ✓ | – | ✓ | ✓ | – | – | |
| requirement.decompose | ✓ | – | ✓ | ✓ | – | – | LLM-not-configured testbar |
| requirement.validate | ✓ | – | ✓ | ✓ | – | – | LLM-not-configured testbar |

### architecture.* (5 Tools)

| Tool | Happy | Auth | RBAC | Audit | SSE | Perf | Notes |
|------|-------|------|------|-------|-----|------|-------|
| architecture.get | ✓ | – | n/a | n/a | – | – | |
| architecture.query | ✓ | – | n/a | n/a | – | – | |
| architecture.create | ✓ | – | ✓ | ✓ | – | – | |
| architecture.update | ✓ | – | ✓ | ✓ | – | – | |
| architecture.link | ✓ | – | ✓ | ✓ | – | – | Invalid link_type geprüft |

### test.* (8 Tools)

| Tool | Happy | Auth | RBAC | Audit | SSE | Perf | Notes |
|------|-------|------|------|-------|-----|------|-------|
| test.get | ✓ | – | n/a | n/a | – | – | |
| test.query | ✓ | – | n/a | n/a | – | – | |
| test.create | ✓ | – | ✓ | ✓ | – | – | |
| test.update | ✓ | – | ✓ | ✓ | – | – | Invalid status geprüft |
| test.link | ✓ | – | ✓ | ✓ | – | – | |
| test.run_create | ✓ | – | ✓ | ✓ | – | – | |
| test.run_get | ✓ | – | n/a | n/a | – | – | |
| test.run_report_results | ✓ | – | ✓ | ✓ | – | – | Empty results + invalid status geprüft |

### traceability.* (1 Tool)

| Tool | Happy | Auth | RBAC | Audit | SSE | Perf | Notes |
|------|-------|------|------|-------|-----|------|-------|
| traceability.query | ✓ | – | n/a | n/a | – | – | Invalid direction geprüft |

### artifact.* (2 Tools)

| Tool | Happy | Auth | RBAC | Audit | SSE | Perf | Notes |
|------|-------|------|------|-------|-----|------|-------|
| artifact.search | ✓ | – | n/a | n/a | – | – | |
| artifact.get_tree | ✓ | – | n/a | n/a | – | – | Ohne workspace_id → VALIDATION_ERROR |

### workspace.* (4 Tools)

| Tool | Happy | Auth | RBAC | Audit | SSE | Perf | Notes |
|------|-------|------|------|-------|-----|------|-------|
| workspace.get_context | ✓ | – | n/a | n/a | – | – | 2 Varianten (ohne/mit workspace_id) |
| workspace.close | ✓ | ✓ | ✓ | ✓ | ✓ (write happy over SSE) | – | Double-close getestet (200) |
| workspace.reactivate | ✓ | – | ✓ | ✓ | – | – | Close+Reactivate Roundtrip |
| workspace.delete | ✓ | – | ✓ | ✓ | – | – | Inkl. Captcha-Fehlertest |

### permissions.* (4 Tools)

| Tool | Happy | Auth | RBAC | Audit | SSE | Perf | Notes |
|------|-------|------|------|-------|-----|------|-------|
| permissions.set_rule | ✓ | – | ✓ | ✓ | – | – | |
| permissions.list | ✓ | ✓ | n/a | n/a | – | ✓ (50 rules, <1.5s) | |
| permissions.revoke | ✓ | – | ✓ | ✓ | – | – | |
| permissions.check | ✓ | – | n/a | n/a | – | – | Invalid level geprüft |

### admin.* (3 Tools)

| Tool | Happy | Auth | RBAC | Audit | SSE | Perf | Notes |
|------|-------|------|------|-------|-----|------|-------|
| admin.backup_create | ✓ | ✓ | ✓ | ✓ | – | – | Invalid backup_type geprüft |
| admin.backup_list | ✓ | – | n/a | n/a | – | – | Invalid status/limit/offset geprüft |
| admin.restore | ✓ | – | ✓ | ✓ | – | – | Inkl. Captcha-Fehlertest |

### audit.* (1 Tool)

| Tool | Happy | Auth | RBAC | Audit | SSE | Perf | Notes |
|------|-------|------|------|-------|-----|------|-------|
| audit.query | ✓ | – | n/a (admin-only, getestet) | n/a | – | ✓ (50 entries, <1.5s) | Viewer denied getestet, operation/limit/time-range Filter |

### events.* (2 Tools)

| Tool | Happy | Auth | RBAC | Audit | SSE | Perf | Notes |
|------|-------|------|------|-------|-----|------|-------|
| events.dlq_list | ✓ | – | n/a (read) | n/a | – | – | Viewer denied getestet, invalid limit |
| events.dlq_replay | ✓ | – | ✓ | ✓ | – | – | |

### user.* (4 Tools)

| Tool | Happy | Auth | RBAC | Audit | SSE | Perf | Notes |
|------|-------|------|------|-------|-----|------|-------|
| user.create | ✓ | – | ✓ | ✓ | – | – | Short password + duplicate username geprüft |
| user.assign_role | ✓ | – | ✓ | ✓ | – | – | Invalid role geprüft |
| user.list | ✓ | ✓ | n/a | n/a | – | ✓ (50 users, <1.0s) | Viewer denied getestet |
| user.deactivate | ✓ | – | ✓ | ✓ | – | – | |

## Getestete Fehler-Codes

| Error Code | HTTP Status | Tests | Abgedeckt in |
|------------|-------------|-------|-------------|
| `AUTH_FAILED` | 401 | 6 | 5 parametrisierte Auth-Tests + 1 Missing-Key (all_tools), 1 SSE (sse_transport) |
| `PERMISSION_DENIED` | 403 | 25+ | 23 parametrisierte RBAC-Denial (all_tools) + audit.query viewer + events.dlq_list viewer + user.list viewer + audit failed-write (audit.py) |
| `FEATURE_NOT_ENABLED` | 400 | 3 | 2 Preset-Disabled (decompose + validate) + 1 enabled-as-success (all_tools section 7) |
| `VALIDATION_ERROR` | 400 | 25+ | Missing params, invalid UUID, Captcha wrong, invalid backup_type, invalid role, invalid link_type, invalid status, invalid direction, empty results, invalid limit/offset, duplicate username, short password, start_time > end_time (all_tools + audit.py) |
| `NOT_FOUND` | 404 | 3 | requirement.get nonexistent UUID (all_tools), workspace.close unknown WS (403 — documented), SSE NOT_FOUND (sse_transport) |
| `UNKNOWN_TOOL` | 400 | 1 | Nicht-registrierter Tool-Name (all_tools section 4) |
| `PARSE_ERROR` | 401 | 2 | Invalid JSON body (all_tools section 4 + sse_transport) |
| `INVALID_REQUEST` | 401 | 4 | Fehlendes jsonrpc, falsche Version, fehlendes method, fehlendes id (all_tools section 4) |
| `INTERNAL_ERROR` | 500 | 1 | implizit via TenantContext-Unit-Test (test_tenant_context_activation.py: execute_tool raise → INTERNAL_ERROR) |
| `LLM_NOT_CONFIGURED` | 400 | 1 | requirement.decompose ohne LLM-env (all_tools section 5) |

## Performance-Budgets

| Test | Datenmenge | Budget | Gemessen (CI) | Status |
|------|------------|--------|---------------|--------|
| requirement.query | 100 Requirements | < 2.0s | – | Noch nicht in CI gelaufen |
| permissions.list | 50 Regeln | < 1.5s | – | Noch nicht in CI gelaufen |
| audit.query | 50 AuditEntries | < 1.5s | – | Noch nicht in CI gelaufen |
| user.list | 50 Users | < 1.0s | – | Noch nicht in CI gelaufen |

> **Hinweis:** Performance-Tests sind mit `@pytest.mark.slow` markiert und laufen nicht im Standard-CI-Test-Suite (müssen explizit via `pytest -m "slow"` aktiviert werden). Die Budgets sind grosszügig bemessen (Sekunden, nicht Millisekunden), da die Django-Test-Client pro Test eine frische DB-Transaktion bootet. Ziel ist das Abfangen schwerer Regressionen (z.B. N+1 Queries), nicht die Durchsetzung absoluter Production-SLAs.

## Lücken / Out-of-Scope

### Nicht getestet (bewusst out-of-scope)
- **Stdio-Transport** — wird separat in `test_protocol_handler.py` getestet
- **Long-lived SSE-Streaming** — Django ist synchron, SSE-View antwortet mit genau einem Event pro Request
- **LLM-Output-Quality** — LLM-Adapter in allen Tests gemockt (nur Routing/Fehlerpfade werden getestet)
- **Backup-FileSystem-Edge-Cases** — BackupService.create_backup + AdminRestoreService.restore sind gemockt
- **Concurrency / Race Conditions** — erfordert separate Test-Klasse mit Threading/Async-Setup
- **Websocket-Transport** — derzeit nicht implementiert

### Teilabdeckung / bekannte Lücken
- **Pagination** — für requirement.query KEIN expliziter Pagination-Test (nur default-limit)
- **SSE pro Tool** — SSE-Transport wird repräsentativ getestet (nicht für jedes Tool einzeln)
- **Auth pro Tool** — Auth-Failure wird repräsentativ getestet (5 Tools), nicht alle 40
- **views.py HTTP-Response-Status-Mapping** — alle 5 HTTP-Status-Codes (401/403/400/404/500) sind mindestens einmal abgedeckt, aber nicht exhaustiv
- **Item-Permission** — nur per Happy-Path getestet (permissions.check, permissions.list). Kein Cross-User-Szenario
- **Backup-Restore mit realem FileSystem** — Backup-Edge-Cases (korrupte Datei, falscher Checksumme) nicht getestet

### Nicht getestet (sollte in Zukunft abgedeckt werden)
- **Fuzzy-Input** — JSON-RPC-Frame-Validierung deckt nur 6 Standard-Fehler ab
- **Rate-Limiting** — nicht implementiert
- **Multi-Tenant-Isolation (negativ)** — dass Tenant A nicht auf Tenant B Daten zugreifen kann, ist nur indirekt (via TenantContext-Fix) getestet
- **CORS-Header** — Frontend-Komponente nicht im Scope

## Empfehlungen

1. **Performance-Tests in CI mit `pytest -m "slow"` aktivieren** (z.B. nightly)
2. **Audit-Tests als Compliance-Check** — sie verifizieren REQ-L2-MC-012 (MCP-Audit-Trail) und REQ-L2-AL-001/002 (vollständige Audit-Felder, SHA-256-Hash)
3. **Neue Tools sollten jeweils Happy-Path + RBAC + Audit-Tests bekommen** — Vorlage: siehe `test_e2e_all_tools.py` happy-path + RBAC + `test_e2e_audit.py`
4. **TenantContext-Fix in Code-Reviews explizit beachten** — der Fix in `tool_registry.py` ist kritisch für korrekte Multi-Tenant-Isolation
5. **Pagination-Tests ergänzen** — für requirement.query, audit.query, user.list, permissions.list
6. **Concurrency-Test-Klasse anlegen** — separate `test_e2e_concurrency.py` für Race-Condition-Szenarien (empfohlen für Phase 5)
7. **Test-Suite nach Integration sichern** — nach Merge in `main` sollten alle 588 Tests als Baseline durchlaufen

## Referenzen

### Code
- `backend/mcp_server/tool_registry.py` — `dispatch_request()` + TenantContext-Lifecycle (COMP-MC-002)
- `backend/mcp_server/views.py` — HTTP + SSE Views (COMP-MC-001)
- `backend/mcp_server/protocol_handler.py` — JSON-RPC-Frame-Validation
- `backend/mcp_server/tools/base.py` — `write_mcp_audit()` (REQ-L2-MC-012)
- `backend/audit/services.py` — `log_write()`, `query()`
- `backend/audit/models.py` — `AuditEntry` Append-Only-Contract

### Test-Files
- `backend/mcp_server/tests/conftest_e2e.py` — 14+ Fixtures (428 Zeilen)
- `backend/mcp_server/tests/helpers.py` — JSON-RPC-Builder + Django-Client-Helpers (92 Zeilen)
- `backend/mcp_server/tests/test_e2e_all_tools.py` — 130 Tests (2324 Zeilen)
- `backend/mcp_server/tests/test_e2e_sse_transport.py` — 6 Tests (332 Zeilen)
- `backend/mcp_server/tests/test_e2e_audit.py` — 36 Tests (1095 Zeilen)
- `backend/mcp_server/tests/test_e2e_performance.py` — 4 Tests (272 Zeilen)
- `backend/mcp_server/tests/test_tenant_context_activation.py` — 7 Tests (327 Zeilen)

### Architektur- & Requirements-Dokumente
- `docs/se/L1/Gesamtsystem/L2/McpServerSystem/` — Architecture-Reference
- `docs/REQUIREMENTS.md` — REQ-L1-039 (Permissions), REQ-L1-042 (Workspace-Lifecycle), REQ-L1-046 (Admin-Umbrella), REQ-L2-MC-001..013, REQ-L2-AL-001..003
- `docs/se/reports/` — Vorherige Reports und SE-Phase-Dokumentation
