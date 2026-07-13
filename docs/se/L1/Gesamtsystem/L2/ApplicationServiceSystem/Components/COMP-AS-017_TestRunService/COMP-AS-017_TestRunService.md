---
component_id: COMP-AS-017
parent_requirement: REQ-L2-AS-030
parent_system: ApplicationServiceSystem
designation: component
status: draft
timestamp: "2026-06-27T21:00:00Z"
---
# COMP-AS-017 — TestRunService

## Verantwortlichkeit

Der TestRunService verwaltet Testläufe (Test Runs) als eigenständige Entitäten. Er erstellt TestRuns mit zugehörigen TestCase-IDs, verwaltet den Ausführungsstatus pro TestCase (Passed/Failed/Blocked/Not Run), berechnet das aggregierte Lauf-Ergebnis automatisch und protokolliert Zeitstempel und ausführende Instanz.

## Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AS-EXT-IN-001 | eingehend | RestApiAdapter | `create_test_run(test_case_ids[], ctx) -> TestRun` |
| IF-AS-EXT-IN-002 | eingehend | McpServer | `test.create_run(test_case_ids[], ctx) -> TestRun` |
| IF-AS-EXT-OUT-006 | ausgehend | AuditLogSystem | `log_write(op, entity_id, ctx)` |
| IF-AS-EXT-OUT-007 | ausgehend | PersistenceLayer | Django ORM — TestRun/TestResult-CRUD |

## Teststrategie

- Aggregations-Test: Alle Passed → Passed; ein Failed → Failed; ein Blocked → Partial
- Zeitstempel-Test: Start/Ende werden korrekt gesetzt
- CI-Job-ID-Test: Ausführende Instanz wird gespeichert

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade Phase 3 | 2026-06-27*
