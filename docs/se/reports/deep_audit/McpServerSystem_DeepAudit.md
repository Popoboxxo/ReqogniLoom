# McpServerSystem - Deep Test Coverage Audit

> Automatisch generierter Deep-Audit-Report der Testabdeckung.

## Datei: `test_admin_tool_group.py`

### Test: `test_workspace_close_calls_service_and_audits`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_workspace_close_missing_workspace_id_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_workspace_close_invalid_uuid_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_workspace_close_not_found`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_workspace_close_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_workspace_close_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_workspace_reactivate_calls_service_and_audits`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_workspace_reactivate_not_found`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_workspace_reactivate_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_workspace_reactivate_missing_workspace_id_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_workspace_delete_calls_service_and_audits`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_workspace_delete_captcha_mismatch_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_workspace_delete_not_found`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_workspace_delete_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_workspace_delete_missing_confirmation_text_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_workspace_delete_missing_workspace_id_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_workspace_get_context_falls_through_to_cross_cutting`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_unknown_workspace_tool_falls_through_and_returns_unknown_tool`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_lifecycle_handler_does_not_call_cross_cutting`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_default_constructor_uses_real_services`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_tool_map_has_exactly_three_entries`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

## Datei: `test_audit_tool_group.py`

### Test: `test_audit_query_with_editor_role_returns_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_audit_query_with_viewer_role_returns_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_dlq_list_with_editor_role_returns_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_dlq_replay_with_editor_role_returns_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_audit_query_calls_service_and_returns_entries`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_audit_query_with_time_range_and_operation`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_audit_query_invalid_operation_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_audit_query_invalid_iso8601_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_audit_query_start_after_end_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_audit_query_invalid_limit_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_audit_query_service_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_audit_query_service_not_found`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_audit_query_workspace_id_is_validated_but_not_applied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_audit_query_does_not_write_audit`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_dlq_list_calls_service_and_returns_events`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_dlq_list_with_event_type_filter`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_dlq_list_invalid_limit_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_dlq_list_non_integer_limit_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_dlq_list_invalid_event_type_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_dlq_list_permission_denied_from_service`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_dlq_list_does_not_write_audit`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_dlq_replay_calls_service_and_audits`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_dlq_replay_missing_event_id_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_dlq_replay_invalid_event_id_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_dlq_replay_not_found`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_dlq_replay_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_dlq_replay_does_not_audit_on_failure`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_unknown_audit_tool_returns_unknown_tool`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_unknown_events_tool_returns_unknown_tool`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_default_constructor_uses_real_dlq_service`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_tool_map_has_exactly_three_entries`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_audit_prefix_is_registered`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_events_prefix_is_registered`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_events_dlq_replay_is_registered_as_write_tool`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_router_routes_audit_and_events_prefixes`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_successful_query_returns_jsonrpc_result_envelope`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_query_with_editor_role_returns_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_query_with_invalid_api_key_returns_auth_failed`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_successful_replay_returns_jsonrpc_result_envelope`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_replay_with_viewer_role_returns_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

## Datei: `test_backup_tool_group.py`

### Test: `test_backup_create_calls_service_and_audits`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_backup_create_uses_full_as_default_type`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_backup_create_invalid_type_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_backup_create_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_backup_create_value_error_from_service`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_backup_create_not_found`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_backup_list_returns_200_with_backups`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_backup_list_with_filters_applied_in_process`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_backup_list_with_invalid_status_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_backup_list_with_invalid_limit_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_backup_list_with_negative_offset_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_backup_list_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_restore_calls_service_and_audits`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_restore_captcha_mismatch_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_restore_captcha_with_trailing_space_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_restore_missing_backup_id_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_restore_invalid_backup_id_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_restore_missing_confirmation_text_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_restore_unknown_backup_id_returns_not_found`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_restore_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_restore_with_invalid_restore_type_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_unknown_admin_tool_returns_unknown_tool`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_default_constructor_uses_real_services`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_tool_map_has_exactly_three_entries`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_admin_prefix_is_registered`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_admin_tools_are_registered_as_write_tools`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_router_routes_admin_prefix`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_successful_create_returns_jsonrpc_result_envelope`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_create_with_viewer_role_returns_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_create_with_invalid_api_key_returns_auth_failed`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_successful_restore_with_correct_captcha`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_restore_captcha_mismatch_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_restore_missing_confirmation_text_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-009
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_restore_with_viewer_role_is_blocked_by_rbac`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

## Datei: `test_e2e_all_tools.py`

### Test: `test_e2e_tool_happy_path`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_viewer_denied_for_write_tool`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_invalid_api_key_returns_auth_failed`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_missing_api_key_returns_auth_failed`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_missing_jsonrpc_field`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_wrong_jsonrpc_version`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_missing_method_field`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_missing_id_field`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_invalid_json_body`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_unknown_tool_returns_unknown_tool`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_not_found_for_nonexistent_requirement`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_not_found_for_nonexistent_workspace_member_admin_call`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_validation_error_for_missing_required_param`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_validation_error_for_invalid_uuid`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_llm_not_configured_for_decompose`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_inactive_workspace_close_returns_not_found`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_workspace_delete_wrong_captcha`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_admin_restore_wrong_captcha`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_feature_not_enabled_when_preset_disables_llm_decompose`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_feature_not_enabled_via_tool_feature_map_override`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_feature_enabled_when_preset_cache_allows`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_workspace_get_context_returns_tenant_and_user`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_workspace_get_context_with_workspace_id`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_audit_query_admin_returns_entries`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_audit_query_viewer_denied`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_events_dlq_list_admin_empty`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_events_dlq_list_viewer_denied`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_user_list_admin_returns_tenant_users`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_user_list_viewer_denied`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_admin_backup_list_empty`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_admin_backup_create_with_invalid_type_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_admin_restore_with_invalid_uuid_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_permission_check_admin_read_allowed`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_permission_check_invalid_level_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_requirement_query_requires_workspace_id`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_architecture_query_requires_workspace_id`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_test_query_requires_workspace_id`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_artifact_get_tree_requires_workspace_id`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_requirement_decompose_viewer_denied`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_workspace_reactivate_admin_can_restore_closed_workspace`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_traceability_query_with_no_links_returns_empty`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_traceability_query_invalid_direction_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_user_create_viewer_denied`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_user_create_validation_error_for_short_password`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_user_create_validation_error_for_duplicate_username`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_user_assign_role_invalid_role_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_architecture_link_invalid_link_type_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_test_update_invalid_status_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_test_run_report_results_empty_array_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_test_run_report_results_invalid_status_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_audit_query_invalid_operation_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_audit_query_invalid_limit_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_events_dlq_list_invalid_limit_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_admin_backup_list_invalid_status_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_admin_backup_list_invalid_limit_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_admin_backup_list_negative_offset_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_member_role_allowed_for_requirement_create`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_admin_role_full_path_creates_and_updates_requirement`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_workspace_delete_happy_path`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_workspace_delete_missing_workspace_id_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_admin_backup_list_default_filters`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_audit_query_with_operation_filter`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_audit_query_with_time_range`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_audit_query_start_after_end_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_e2e_requirement_get_member_role_can_read`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

## Datei: `test_e2e_audit.py`

### Test: `test_write_tool_creates_audit_entry`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_audit_entry_has_correct_actor`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_audit_entry_has_sha256_api_key_hash`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_audit_entry_source_is_mcp`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_audit_entry_client_name_equals_tool_name`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_audit_entry_actor_type_is_agent`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_failed_write_does_not_create_audit_entry`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_validation_error_does_not_create_audit_entry`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_audit_query_finds_mcp_entries`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_audit_query_finds_by_entity_id`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_audit_entry_is_append_only_at_model_level`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_audit_entry_carries_tenant_id`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_multiple_write_calls_create_multiple_audit_entries`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_audit_entry_for_requirement_create_records_requirement_id`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

## Datei: `test_e2e_mcp.py`

### Test: `test_successful_close_returns_jsonrpc_result_envelope`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_close_with_viewer_role_returns_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_close_with_invalid_api_key_returns_auth_failed`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_close_not_found_propagates_as_jsonrpc_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_close_missing_workspace_id_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_successful_reactivate_returns_jsonrpc_result_envelope`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_reactivate_validation_error_propagates`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_successful_delete_with_correct_captcha`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_delete_captcha_mismatch_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_delete_missing_confirmation_text_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_delete_with_viewer_role_is_blocked_by_rbac`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_workspace_get_context_falls_through_to_cross_cutting`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_unknown_workspace_tool_returns_unknown_tool_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_lifecycle_tools_are_registered_as_write_tools`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_registry_routes_workspace_prefix_to_admin_group`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_all_three_lifecycle_tools_resolve_through_router`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

## Datei: `test_e2e_performance.py`

### Test: `test_requirement_query_with_100_requirements_under_2s`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_permissions_list_with_50_rules_under_1_5s`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_audit_query_with_50_entries_under_1_5s`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_user_list_with_50_users_under_1s`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

## Datei: `test_e2e_sse_transport.py`

### Test: `test_sse_read_tool_returns_event_stream_with_result`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_sse_write_tool_returns_event_stream_with_result`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_sse_error_case_returns_event_stream_with_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_sse_auth_failure_returns_event_stream_with_auth_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_sse_rbac_denial_returns_event_stream_with_permission_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_sse_parse_error_returns_event_stream_with_parse_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

## Datei: `test_permissions_tool_group.py`

### Test: `test_set_rule_calls_service_and_audits`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_set_rule_with_artifact_id`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_set_rule_missing_workspace_id_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_set_rule_invalid_uuid_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_set_rule_missing_level_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_set_rule_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_set_rule_invalid_level_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_list_returns_rules`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_list_with_artifact_filter_narrows_results`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_list_missing_user_id_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_list_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_revoke_calls_service_and_audits`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_revoke_unknown_id_returns_not_found`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_revoke_missing_id_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_revoke_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_revoke_service_returns_false_returns_not_found`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_check_read_at_write_returns_allowed`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_check_write_at_read_returns_denied`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_check_deny_returns_denied`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_check_missing_level_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_check_invalid_level_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_default_constructor_uses_real_service`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_tool_map_has_exactly_four_entries`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_unknown_tool_returns_unknown_tool_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_set_rule_and_revoke_are_registered_as_write_prefixes`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_set_rule_e2e_returns_jsonrpc_result`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_set_rule_e2e_viewer_is_blocked_by_rbac`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_list_e2e_returns_jsonrpc_result`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_registry_routes_permissions_prefix_to_permissions_group`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

## Datei: `test_protocol_handler.py`

### Test: `test_valid_frame_returns_none`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_missing_jsonrpc_key`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_wrong_jsonrpc_version`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_missing_method`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_empty_method`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_missing_id`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_non_dict_frame`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_format_error_known_code`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_format_error_with_details`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_format_jsonrpc_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_format_jsonrpc_result`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_read_valid_json`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_read_invalid_json_returns_parse_error_marker`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_write_response_stores_result`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_extract_api_key_from_header`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_extract_api_key_from_params`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_parse_error_on_invalid_body`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_invalid_request_on_bad_frame`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_missing_api_key_returns_auth_failed`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_successful_dispatch_returns_result`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_tool_error_propagated_to_response`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_api_key_stripped_from_params_before_dispatch`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_id_preserved_in_response`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_registry_exception_returns_internal_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-005
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Transport protocol validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

## Datei: `test_tenant_context_activation.py`

### Test: `test_valid_api_key_activates_tenant_context_during_dispatch`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_invalid_api_key_does_not_activate_tenant_context`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_tenant_context_cleared_on_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_tenant_context_cleared_on_internal_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_tenant_context_cleared_on_unknown_tool`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_stale_tenant_context_is_replaced_then_cleared`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_get_tenant_raises_when_unset`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

## Datei: `test_tool_groups.py`

### Test: `test_require_param_raises_on_missing`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_require_param_returns_value`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_require_uuid_raises_on_bad_uuid`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_require_uuid_returns_uuid`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_requirement_get_calls_service`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_requirement_create_calls_service_and_audits`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_requirement_update_calls_service_and_audits`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_requirement_get_not_found_returns_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_requirement_create_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_requirement_decompose_without_llm_returns_llm_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_requirement_validate_without_llm_returns_llm_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_requirement_query_requires_workspace_id`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_requirement_query_calls_list`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_unknown_tool_returns_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_architecture_get_calls_service`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_architecture_create_calls_service_and_audits`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_architecture_link_with_valid_type_calls_trace_service`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_architecture_link_invalid_type_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_architecture_query_requires_workspace_id`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_architecture_get_not_found`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_test_get_calls_service`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_test_create_calls_service_and_audits`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_test_create_with_linked_req_creates_trace_link`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_test_update_status_calls_update_test_status`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_test_update_invalid_status_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_test_link_creates_verifies_trace_link`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_test_query_requires_workspace_id`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_artifact_search_calls_search_service`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_artifact_search_requires_query`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_artifact_get_tree_requires_workspace_id`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_workspace_get_context_returns_tenant_id`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_traceability_query_invalid_direction`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_unknown_tool_returns_unknown_tool_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-001
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** AI-Agent -> McpServer: MCP-Protokoll (JSON-RPC)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

## Datei: `test_tool_registry.py`

### Test: `test_set_and_get`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_get_missing_returns_none`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_invalidate_removes_entry`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_routes_requirement_prefix`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_routes_architecture_prefix`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_unknown_prefix_returns_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_invalid_api_key_returns_auth_failed`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_unknown_tool_returns_unknown_tool_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_write_tool_with_viewer_role_returns_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_write_tool_with_editor_role_dispatches`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_read_tool_does_not_check_rbac`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_preset_blocked_tool_returns_feature_not_enabled`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_tool_group_exception_returns_internal_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_api_key_hash_method`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

## Datei: `test_users_tool_group.py`

### Test: `test_user_create_with_editor_role_returns_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_user_list_with_viewer_role_returns_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_user_deactivate_with_editor_role_returns_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_user_assign_role_with_viewer_role_returns_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_user_create_hashes_password_and_audits`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_user_create_missing_username_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_user_create_missing_email_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_user_create_short_password_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_user_create_unknown_role_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_user_create_duplicate_username_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_user_create_tenant_not_found_returns_not_found`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_user_create_tenant_id_as_non_superuser_returns_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_user_assign_role_calls_authorization_service_and_audits`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_user_assign_role_non_member_target_reaches_service_with_false`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_user_assign_role_missing_user_id_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_user_assign_role_missing_preset_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_user_assign_role_unknown_role_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_user_assign_role_service_raises_not_found`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_user_assign_role_service_raises_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_user_assign_role_does_not_audit_on_failure`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_user_list_returns_tenant_users`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_user_list_with_is_active_filter`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_user_list_invalid_is_active_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_user_list_invalid_limit_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_user_list_does_not_write_audit`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_user_list_tenant_id_other_than_self_returns_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_user_deactivate_sets_is_active_false_and_audits`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_user_deactivate_unknown_user_returns_not_found`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_user_deactivate_missing_user_id_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_user_deactivate_invalid_uuid_returns_validation_error`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_user_deactivate_does_not_audit_on_failure`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_unknown_user_tool_returns_unknown_tool`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_default_constructor_uses_real_authorization_service`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_tool_map_has_exactly_four_entries`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_user_prefix_is_registered`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_user_write_tools_are_registered`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_router_routes_user_prefix`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_successful_list_returns_jsonrpc_result`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_list_with_viewer_role_returns_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_list_with_invalid_api_key_returns_auth_failed`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-006
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** API-Key validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_successful_create_returns_jsonrpc_result`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_create_with_editor_role_returns_permission_denied`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **DEEP** (Ausreichend). Er testet die Logik ohne exzessives Mocking der internen State-Machine.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Aktuell kein kritischer Refactoring-Bedarf. Test kann beibehalten werden, sollte jedoch auf E2E HTTP-Level gehoben werden, falls noch nicht geschehen.

### Test: `test_successful_assign_role_returns_jsonrpc_result`
- **Verknüpfte REQ-L2 ID:** REQ-L2-MC-007
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** RBAC validation
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

### Test: `test_successful_deactivate_returns_jsonrpc_result`
- **Verknüpfte REQ-L2 ID:** N/A
- **Was der Test aktuell macht:** Der Test ist **SHALLOW** (Zu oberflächlich). Er mockt interne Services (`MagicMock`, `patch`) und validiert nur die Funktionsaufrufe anstelle der echten MCP-Integration oder Datenbank-Persistenz.
- **Akzeptanzkriterium (Anforderung):** Standard-Anforderung aus dem Header (ACs nicht explizit gelistet)
- **Refactoring-Bedarf:** Entferne die `MagicMock` / `patch` Objekte. Implementiere einen echten End-to-End Aufruf über den `ProtocolHandler` unter Verwendung einer Testdatenbank (z.B. in-memory SQLite oder Testcontainers), um die tatsächliche Persistenz und Rückgabewerte zu prüfen.

