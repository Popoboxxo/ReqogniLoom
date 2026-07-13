# Deep Audit Report: AuditLogSystem

## Ziel und Umfang
Dieser Bericht analysiert die bestehenden Tests im Modul `backend/audit/tests/` (spezifisch `test_writer.py`) auf "Shallow-Testing"-Symptome im Abgleich mit den L2-Anforderungen aus `L2_AuditLogSystem_Requirements.md`.

---

## Detaillierte Test-Analyse (`test_writer.py`)

### 1. `test_writer_subscribes_to_domain_event_bus`
- **REQ-L2 ID**: REQ-L2-AL-001
- **Aktuelles Verhalten (Shallow)**: Prüft in Isolation, dass der `AuditLogWriter` auf simulierte `AuditableOperationOccurred`-Events reagiert.
- **Gefordertes Akzeptanzkriterium**: "Erstelle Requirement via REST → AuditLog: {actor: user_id, ...}"
- **Exakter Refactoring-Bedarf**: Der Test muss einen echten REST-Request (z.B. `POST /requirements`) an den ApplicationService senden und verifizieren, dass das gesamte System (API -> Service -> Event-Bus -> DB) den Log-Eintrag korrekt erzeugt.

### 2. `test_all_mandatory_fields_mapped`
- **REQ-L2 ID**: REQ-L2-AL-001
- **Aktuelles Verhalten (Shallow)**: Erzeugt manuell ein isoliertes Event und prüft das Mapping in das Modell.
- **Gefordertes Akzeptanzkriterium**: "Update Requirement → Eintrag: {operation: 'update', version: 2}", "Workflow-Transition mit change_reason → Eintrag enthält change_reason"
- **Exakter Refactoring-Bedarf**: Der Test muss durch einen API/Integrationstest ersetzt werden, der ein tatsächliches Update und eine Workflow-Transition mit `change_reason` über die Endpunkte durchführt.

### 3. `test_missing_optional_fields_result_in_null`
- **REQ-L2 ID**: REQ-L2-AL-001
- **Aktuelles Verhalten (Shallow)**: Direkter Aufruf des Writers mit einem Event, bei dem `change_reason` fehlt.
- **Gefordertes Akzeptanzkriterium**: "Delete via MCP → Eintrag: {operation: 'delete'}"
- **Exakter Refactoring-Bedarf**: Muss durch einen Delete-Workflow auf Service- oder API-Ebene abgelöst werden, um zu garantieren, dass die weggelassenen Felder auch auf diesen Ebenen nicht zu Fehlern führen.

### 4. `test_event_with_unknown_extra_ctx_fields_accepted`
- **REQ-L2 ID**: REQ-L2-AL-001
- **Aktuelles Verhalten (Shallow)**: Übergibt ein Dummy-Event mit zusätzlichen Dictionary-Keys an den Writer.
- **Gefordertes Akzeptanzkriterium**: Implizite Robustheit.
- **Exakter Refactoring-Bedarf**: Weiterhin als Unit-Test akzeptabel, aber sollte auf API-Ebene geprüft werden (was passiert bei unerwartetem JSON im Body?).

### 5. `test_mcp_event_stores_api_key_hash_not_raw`
- **REQ-L2 ID**: REQ-L2-AL-002
- **Aktuelles Verhalten (Shallow)**: Ruft den Writer manuell mit `source="mcp"` und API-Key im Kontext auf.
- **Gefordertes Akzeptanzkriterium**: "MCP requirement.create mit API-Key → {actor_type: 'agent', client_name: 'claude-code/1.0', api_key_hash: 'sha256:...', source: 'mcp'}"
- **Exakter Refactoring-Bedarf**: Echter Aufruf über das MCP-Interface. Muss testen, dass das MCP-Framework die Header/Auth-Tokens korrekt liest und der Middleware übergibt, sodass der Key tatsächlich nicht im Klartext in die DB wandert.

### 6. `test_rest_event_has_null_mcp_fields`
- **REQ-L2 ID**: REQ-L2-AL-002
- **Aktuelles Verhalten (Shallow)**: Manuelles Event mit `source="rest"`.
- **Gefordertes Akzeptanzkriterium**: "REST-Operation → {actor_type: 'user', source: 'rest', client_name: null}"
- **Exakter Refactoring-Bedarf**: Ausführung eines Standard-REST-Requests. Prüfung, ob die REST-Middleware die MCP-Felder explizit auf `null` setzt.

### 7. `test_sha256_hash_is_reproducible`
- **REQ-L2 ID**: REQ-L2-AL-002
- **Aktuelles Verhalten (Shallow)**: Reiner Unit-Test des `ContextEnricher`.
- **Gefordertes Akzeptanzkriterium**: "API-Key NIEMALS im Klartext."
- **Exakter Refactoring-Bedarf**: Test behalten, aber er deckt das Systemverhalten nicht ab (muss in Kombination mit echtem MCP-Request getestet werden).

### 8. `test_db_has_no_raw_api_key_column`
- **REQ-L2 ID**: REQ-L2-AL-002
- **Aktuelles Verhalten (Shallow)**: Prüft über die Django ORM Meta-Klasse, ob ein Python-Feld namens `api_key_raw` existiert.
- **Gefordertes Akzeptanzkriterium**: "DB-Check: kein Eintrag enthält Roh-API-Key"
- **Exakter Refactoring-Bedarf**: Der Test ist unzureichend, da er nicht prüft, ob der Klartext-Key z.B. unbeabsichtigt in einem JSONB-Kontextfeld landet. Der Test muss echte Datensätze per MCP anlegen und mittels raw SQL (`SELECT * FROM audit_entry WHERE context::text LIKE '%raw-key%';`) prüfen, ob der Key auf DB-Ebene wirklich inexistent ist.

### 9. `test_write_succeeds`
- **REQ-L2 ID**: REQ-L2-AL-003
- **Aktuelles Verhalten (Shallow)**: Direkter Aufruf des Writers.
- **Gefordertes Akzeptanzkriterium**: "Write → erfolgreich"
- **Exakter Refactoring-Bedarf**: Als echter API-Write umzusetzen.

### 10. `test_bulk_update_via_manager_raises`, `test_bulk_delete_via_manager_raises`, `test_instance_delete_raises`, `test_instance_save_on_existing_raises`
- **REQ-L2 ID**: REQ-L2-AL-003
- **Aktuelles Verhalten (Shallow)**: Prüft nur die Python-Sicherung (Django ORM `RuntimeError`).
- **Gefordertes Akzeptanzkriterium**: "Versuch UPDATE/DELETE → DB-Constraint-Fehler", "Erzwingung auf Datenbankebene."
- **Exakter Refactoring-Bedarf**: Dieser Test prüft NICHT die geforderte Datenbankebene. Er muss refactored werden, um ein nacktes SQL `UPDATE` und `DELETE` (über `django.db.connection.cursor()`) abzusetzen und zu verifizieren, dass die DB einen `IntegrityError` (z.B. durch Table Triggers) wirft.

### 11. `test_no_update_entry_method_on_writer`, `test_no_update_entry_method_on_services`
- **REQ-L2 ID**: REQ-L2-AL-003
- **Aktuelles Verhalten (Shallow)**: Python `hasattr()` Check.
- **Gefordertes Akzeptanzkriterium**: "API bietet keine update_entry() oder delete_entry() Methode"
- **Exakter Refactoring-Bedarf**: Sollte statt interner Methoden primär die öffentlichen API-Router (REST/MCP) prüfen, dass keine `PUT`/`PATCH`/`DELETE` Routen für AuditLogs registriert sind.

### 12. `test_successful_write_persists_entry`
- **REQ-L2 ID**: REQ-L2-AL-004
- **Aktuelles Verhalten (Shallow)**: Isoliertes Schreiben über den Writer.
- **Gefordertes Akzeptanzkriterium**: "Erstelle Requirement → Requirement UND Audit-Eintrag in DB"
- **Exakter Refactoring-Bedarf**: Muss durch den echten `RequirementService.create()` getestet werden, um das Zusammenspiel der Transaktion zu belegen.

### 13. `test_write_inside_atomic_block_rolls_back_on_error`
- **REQ-L2 ID**: REQ-L2-AL-004
- **Aktuelles Verhalten (Shallow)**: Testet Djangos `transaction.atomic()` mittels explizitem `raise ValueError` in einem künstlichen Setup.
- **Gefordertes Akzeptanzkriterium**: "DB-Fehler nach INSERT → Rollback: weder Requirement noch Audit-Eintrag" und "Audit-INSERT-Fehler → Requirement nicht persistiert"
- **Exakter Refactoring-Bedarf**: Der Test muss die echten Business-Logik-Services nutzen. Es muss ein echter DB-Fehler in der Requirement-Persistierung provoziert werden, und unabhängig davon ein Fehler beim Schreiben des AuditLogs (z.B. durch DB-Mock), um das gegenseitige Rollback im E2E-Szenario sicherzustellen.

### 14. `test_count_equals_successful_writes`
- **REQ-L2 ID**: REQ-L2-AL-004
- **Aktuelles Verhalten (Shallow)**: Führt nacheinander 5 direkte Writer-Aufrufe aus.
- **Gefordertes Akzeptanzkriterium**: "AuditLogEntry.objects.count() entspricht exakt der Anzahl erfolgreicher Schreiboperationen"
- **Exakter Refactoring-Bedarf**: Test muss über API/Services laufen. Mix aus erfolgreichen und fehlgeschlagenen Requests simulieren und danach prüfen, ob nur die erfolgreichen geloggt wurden.

### 15. `test_write_with_tenant_context_injects_tenant_id`
- **REQ-L2 ID**: REQ-L2-AL-006
- **Aktuelles Verhalten (Shallow)**: Schreibt mit explizitem `TenantContext` und prüft das Feld auf der Instanz.
- **Gefordertes Akzeptanzkriterium**: "5 Einträge in T1, 3 in T2. Query T1 → exakt 5", "Custom Manager injiziert Filter automatisch"
- **Exakter Refactoring-Bedarf**: Der Test prüft nur den Schreib-Aspekt. Es fehlt die Verifikation des Managers für Lesezugriffe. Muss erweitert werden: Anlegen von Einträgen in verschiedenen Tenants -> Query über `AuditEntry.objects.all()` -> Assert, dass nur die Einträge des aktiven Tenants zurückkommen (ohne expliziten `.filter()` Aufruf).

### 16. `test_write_without_tenant_context_raises_error` & `test_tenant_context_injector_raises_missing_error`
- **REQ-L2 ID**: REQ-L2-AL-006
- **Aktuelles Verhalten (Shallow)**: Isoliertes Prüfen, dass ohne Context ein Fehler fliegt.
- **Gefordertes Akzeptanzkriterium**: Tenant-Isolation (implizit Sicherheit gegen ungewollte Leaks).
- **Exakter Refactoring-Bedarf**: Sollte durch einen echten API-Aufruf ohne (oder mit ungültigem) Tenant-Header/Auth getestet werden, der dann kontrolliert in einem 400er/401er Fehler mündet, statt nur eine interne Python-Exception zu prüfen.

---
**Fazit:** 
Fast alle Tests im aktuellen Stand sind "Shallow". Sie testen die Implementierungsdetails (z.B. Methodenaufrufe, Django ORM) anstatt die Anforderungen über die tatsächlichen Systemgrenzen (REST/MCP-Schnittstellen, echte DB-Constraints, Tenant-Manager) hinweg zu validieren. Es besteht drastischer Refactoring-Bedarf in Richtung Integration Testing.
