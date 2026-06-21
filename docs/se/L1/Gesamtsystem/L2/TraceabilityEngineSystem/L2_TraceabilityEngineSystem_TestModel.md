# L2_TraceabilityEngineSystem_TestModel

## 1. Einleitung und Zielsetzung
Dieses Dokument definiert die modellbasierte Integrationstest-Strategie für das `TraceabilityEngineSystem` (L2) gemäß der genehmigten L2-Architektur. Das Hauptaugenmerk liegt auf der strukturellen und verhaltensbasierten Validierung der Subkomponenten, der korrekten Graph-Traversierung, der Zyklenprüfung und insbesondere der kritischen Cross-Tenant-Verifikation mit `AuthAndTenancy` sowie der Validierung der 8 dedizierten Link-Typen.

## 2. Teststrategie & Integrationsansatz

Es wird ein **Bottom-Up-Integrationsansatz** angewendet:
1. **Component-Level (Mocked Externals):** Testen der internen Geschäftslogik von `TraceLinkManager`, `QueryEngine`, `CoverageCalculator` und `VCRMReportGenerator` isoliert voneinander mittels Mocks für `AuthAndTenancy` und InMemory-SQLite (für Standard-CRUD).
2. **Subsystem-Integration:** Zusammenführen von `TraceLinkManager` mit der `QueryEngine` für Graphen-Integritätsprüfungen (IF-TE-INT-003) unter Einbindung einer echten PostgreSQL-Testinstanz (erforderlich für Recursive CTEs).
3. **External Interface Integration:** Anbindung der Schnittstellen zu `ApplicationService`, `BaselineService` und `AuthAndTenancy`. Besondere Härtetests für die Timeouts und Fail-Closed-Szenarien von `AuthAndTenancy`.

---

## 3. Strukturelle Tests (Schnittstellen)

### 3.1 Externe Schnittstellen (Integration)
| Test-ID | Schnittstelle | Testziel | Erwartetes Ergebnis |
|---------|---------------|----------|---------------------|
| ST-EXT-01 | IF-TE-EXT-IN-001/002/003 | Aufrufe aus dem `ApplicationService` validieren. | Die In-Process-API akzeptiert korrekt typisierte Argumente und leitet sie an die zuständigen Komponenten (COMP-TE-001, 002, 003) weiter. |
| ST-EXT-02 | IF-TE-EXT-IN-004 | Aufrufe aus dem `BaselineService` simulieren. | Der `collect_trace_graph` liefert einen korrekten und statischen Trace-Graph für einen angegebenen Baseline-Snapshot. |
| ST-EXT-03 | IF-TE-EXT-OUT-001 | Persistenz an PostgreSQL binden. | TraceLink-Entitäten werden persistiert (Cascade on delete geprüft). Native Recursive CTE Queries der `QueryEngine` laufen erfolgreich. |
| ST-EXT-04 | IF-TE-EXT-OUT-002 | `AuthAndTenancy` Cross-Tenant-Integration. | Die Aufrufe zu `validate_cross_tenant_boundary` greifen zuverlässig auf In-Process-Python-Ebene. |

### 3.2 Interne Schnittstellen (Subsystem)
| Test-ID | Schnittstelle | Testziel | Erwartetes Ergebnis |
|---------|---------------|----------|---------------------|
| ST-INT-01 | IF-TE-INT-001 | COMP-TE-002 -> COMP-TE-001 | Die `QueryEngine` liest Links gefiltert nach `workspace_id`. |
| ST-INT-02 | IF-TE-INT-003 | COMP-TE-001 -> COMP-TE-002 | Der `TraceLinkManager` ruft bei Bedarf (Zyklenerkennung) `validate_graph_integrity` erfolgreich auf. |
| ST-INT-03 | IF-TE-INT-004/005| COMP-TE-004 -> COMP-TE-002/003 | Der `VCRMReportGenerator` extrahiert Coverage-Daten und TraceLinks erfolgreich für die flache Matrix. |

---

## 4. Verhaltensbasierte Tests (Black-Box / Behavior)

### 4.1 Cross-Tenant-Verifikation & Security (Höchste Priorität)
- **BT-SEC-01 (Valid Intra-Tenant Link):** Erstellen eines Links zwischen Source und Target innerhalb desselben Tenants.
  - *Erwartung:* `validate_cross_tenant_boundary(source, target)` liefert True, Link wird erstellt.
- **BT-SEC-02 (Invalid Cross-Tenant Link):** Erstellen eines Links, bei dem Source in Tenant A und Target in Tenant B liegt.
  - *Erwartung:* `validate_cross_tenant_boundary` schlägt fehl (Exception/False). Der `TraceLinkManager` bricht den Schreibvorgang strikt ab (HTTP 403 / Domain-Exception). Kein Persistieren.
- **BT-SEC-03 (Timeout & Fail-Closed):** Deterministische Simulation eines Timeouts im `AuthAndTenancy` Service mittels Mock/Stub, der explizit eine `TimeoutException` wirft.
  - *Erwartung:* Die Anfrage bricht nach einem automatischen Retry ab. Der Link-Request wird deterministisch (ohne Flakiness durch reale Timings) mit `503 Service Unavailable / Auth Timeout` abgewiesen (Fail-Closed-Prinzip).

### 4.2 Link-Typ-Validierung
- **BT-LINK-01 (Supported Links):** Erstellen von Links mit allen 8 Link-Typen, explizit `documents` (z. B. Requirement -> Doc) und `realizes` (z. B. Code -> Requirement).
  - *Erwartung:* Die Link-Erstellung wird korrekt vom `TraceLinkManager` validiert und in der DB abgelegt.
- **BT-LINK-02 (Unsupported Links):** Versuch, einen Link mit Typ `unknown_type` zu erstellen.
  - *Erwartung:* Schema-Validierungsfehler in `TraceLinkManager`.

### 4.3 Zyklenerkennung (ADR-TE-03)
- **BT-CYCLE-01 (Single Link Eager Validation):** Erstellen eines Links A->B, B->C und Versuch, C->A zu erstellen (Single-API).
  - *Erwartung:* Abweisung vor dem Persistieren durch sofortige Zyklenerkennung. Link wird nicht gespeichert.
- **BT-CYCLE-02 (Bulk Import Tarjan Check):** Senden eines Bulk-Requests (Transaktion) mit zyklischen Links (D->E, E->F, F->D). Es werden Permutationen der Einfügereihenfolge getestet, um eine deterministische Verarbeitung zu gewährleisten. Zusätzlich wird die Sortierung vor dem Insert (Deadlock-Vermeidung) geprüft.
  - *Erwartung:* Die Links werden temporär eingefügt (Deadlock-frei durch lexikographische Sortierung), die Validierung via Tarjan-Algorithmus schlägt deterministisch unabhängig von der initialen Request-Reihenfolge an. Das Resultat ist ein vollständiger Rollback mit dem identifizierten Fehlerpfad.

### 4.4 Graph-Query, BVA & Performance (ADR-TE-02)
- **BT-PERF-01 (Recursive CTE BVA):** Abfrage der transitiven Hülle mittels strukturierter Boundary Value Analysis für die Traversierungstiefe (`depth`). Getestete Boundaries: `depth=0` (nur Knoten selbst), `depth=1` (direkte Nachbarn), `depth=MAX_LIMIT` (maximal erlaubte Rekursionstiefe).
  - *Erwartung:* `QueryEngine` liefert korrekte Upstream/Downstream Graphen entsprechend der exakten Tiefenvorgabe.
- **BT-PERF-02 (BVA Max-Limit Exceeded):** Abfrage mit `depth=MAX_LIMIT+1`.
  - *Erwartung:* System blockiert die Abfrage deterministisch vor oder während der Ausführung und liefert einen klaren Abbruch/Fehlermeldung (z.B. "Max Depth Exceeded").
- **BT-PERF-03 (DB Timeout Limits):** Deterministische Simulation eines "Statement Timeouts" auf Datenbankebene (z.B. via injiziertem Fehler-Status in der DB-Verbindung).
  - *Erwartung:* Die Datenbank bricht den Query ab. System liefert "Fast-Fail" als `408 Request Timeout` ohne Endlos-Retries (verhindert Thundering Herd).

### 4.5 Coverage & VCRM (ADR-TE-04)
- **BT-COV-01 (Coverage Calculation):** Berechnung der Coverage (Requirements vs. TestCases) basierend auf Link-Typ `verifies`.
  - *Erwartung:* Exakte Prozentzahl; gefiltert nach spezifischem `workspace_id` oder Artefakt-Typ.
- **BT-VCRM-01 (Report Generation):** Generieren einer VCRM-Matrix.
  - *Erwartung:* Liefert ein flaches Mapping `requirement_id -> component_id -> test_case_id -> test_result` und ermöglicht den Export in CSV/PDF.

---

## 5. Traceability Matrix (Requirements to Tests)

| Anforderung (L2) | Komponenten | Test-Fälle (Abdeckung) |
|------------------|-------------|-------------------------|
| REQ-L2-TE-001 | COMP-TE-001 | ST-EXT-01, BT-LINK-01, BT-LINK-02 |
| REQ-L2-TE-002 | COMP-TE-001 | ST-EXT-03, BT-CYCLE-01, BT-CYCLE-02 |
| REQ-L2-TE-003 | COMP-TE-001 | BT-CYCLE-02 (Tarjan Bulk Validation) |
| REQ-L2-TE-004 | COMP-TE-002 | ST-EXT-01, BT-PERF-01, BT-PERF-02 |
| REQ-L2-TE-005 | COMP-TE-002 | BT-PERF-01 (Upstream/Downstream) |
| REQ-L2-TE-006 | COMP-TE-003 | BT-COV-01 |
| REQ-L2-TE-007 | COMP-TE-003 | BT-COV-01 (Filtered Coverage) |
| REQ-L2-TE-008 | COMP-TE-002 | BT-PERF-03 (Performance/Timeout) |
| REQ-L2-TE-009 | COMP-TE-001 | BT-SEC-01, BT-SEC-02, BT-SEC-03 (Cross-Tenant) |
| REQ-L2-TE-010 | COMP-TE-001 | ST-EXT-04, BT-SEC-03 (Fail-Closed) |
| REQ-L2-TE-011 | COMP-TE-001 | ST-EXT-02 (Baseline Unterstützung) |
| REQ-L2-TE-012 | COMP-TE-001, 002, 003 | ST-EXT-01 (Isolation/Workspace Filtering) |
| REQ-L2-TE-013 | COMP-TE-004 | ST-INT-03, BT-VCRM-01 |

---
*Erstellt durch se-test-engineer-Agent | ReqFlow SE-Kaskade*
