# L2 BaselineServiceSystem Test-Strategie (Test-Model)

> **Level:** L2 (Subsystem white-box)
> **System:** BaselineServiceSystem (ARCH-L1-006)
> **Datum:** 2026-06-22
> **Status:** entworfen

---

## 1. Test-Ziele & Scope

Ziel der Integrationstests für das `BaselineServiceSystem` ist die Validierung der korrekten Zusammenarbeit seiner vier internen Komponenten (`DeltaIndexBuilder`, `DiffEngine`, `BaselineStore`, `VersionReconstructor`), der korrekten Interaktion mit den externen Systemen (`ApplicationService`, `PresetConfigEngine`, `TraceabilityEngine`, `AuditLog/VersionHistory`, `IcdManagement` und `PersistenceLayer`) sowie die Erfüllung aller zugeordneten `REQ-L2-BL-*` Anforderungen.

Da es sich um eine Systemkomponente mit Fokus auf Performance, Resilienz (OOM-Vermeidung durch Delta-Storage) und Datenintegrität handelt, liegen die Testschwerpunkte auf:
- Korrekter Auflösung von Scopes und Items in Abhängigkeit der externen Systeme.
- Striktem Immutability-Enforcement nach Baseline-Erstellung.
- OOM-freier Verarbeitung bei großen Datenmengen durch den schlanken Delta-Storage und Payload-Rekonstruktion.

---

## 2. Struktur- und Schnittstellentests (Structural/Interface Tests)

Diese Testsuite verifiziert die Konformität der internen und externen Schnittstellenverträge (Mocks/Stubs für ausgehende Aufrufe).

| Test-ID | Fokus | Interface(s) | Beschreibung / Erwartetes Verhalten |
|---------|-------|-------------|---------------------------------------|
| T-BL-STR-001 | Inbound API | IF-BL-EXT-IN-001 | Aufrufe von `build`, `diff`, `get` und `list` durch den `ApplicationService` werden strukturell validiert (Parameter-Typen, Context-Validierung). |
| T-BL-STR-002 | Preset Ingestion | IF-BL-EXT-IN-002 | `DeltaIndexBuilder` fragt Preset-Regeln bei `PresetConfigEngine` korrekt ab und wendet die Einschränkungen für Scopes an. |
| T-BL-STR-003 | Traceability Fetch | IF-BL-EXT-IN-003 | `DeltaIndexBuilder` liest `collect_trace_graph` aus `TraceabilityEngine` korrekt aus und transformiert das Ergebnis (Item-IDs, Versionen). |
| T-BL-STR-004 | AuditLog Fetch | IF-BL-EXT-IN-004 | `VersionReconstructor` fragt bei `AuditLog` historische Items via `get_version` korrekt an. Fehler-Handling für Timeouts, partielle Fehler spezifiziert. Testfälle für Circuit Breaker und Retries inklusive. |
| T-BL-STR-005 | Icd Management | IF-BL-EXT-IN-005 | Abruf der ICD-Versionen via `get_icd_versions` von `IcdManagement` führt zu korrekter Erweiterung der Baseline um ICDs. Fehler-Handling für Timeouts, partielle Fehler spezifiziert. Testfälle für Circuit Breaker und Retries inklusive. |
| T-BL-STR-006 | DB Persistence | IF-BL-EXT-OUT-001 | Ausgehende Aufrufe an den `PersistenceLayer` durch `BaselineStore` nutzen exakt den definierten Delta-Index ohne JSON-Payloads. |
| T-BL-STR-007 | Interne Komp. | IF-BL-INT-001..004 | Die Verträge zwischen den vier internen Komponenten werden auf Typ-Sicherheit und Exception-Handling (z. B. Baseline NotFound) verifiziert. |

---

## 3. Verhaltens- und Systemtests (Behavioral/Black-Box Tests)

Diese Testsuite prüft das Verhalten des Gesamtsystems gegen die Anforderungen.

### 3.1. Baseline-Erstellung & Immutability

| Test-ID | Testfall | Verknüpfte REQ | Beschreibung & Resilienz |
|---------|----------|----------------|--------------------------|
| T-BL-BEH-001 | Erfolgreicher Build (Alle Scopes) | REQ-L2-BL-001, REQ-L2-BL-002, REQ-L2-BL-004, REQ-L2-BL-005, REQ-L2-BL-008 | Eine neue Baseline wird aus validen Items, Traces, und ICDs zusammengebaut. Test der Äquivalenzklassen: Projekt-Scope, Document-Scope und Subsystem-Scope. Erwartung: Speicherung erfolgt ohne Payload (Resilienz, OOM-Schutz), nur IDs und Versionen im `BaselineStore`. |
| T-BL-BEH-002 | Immutability Durchsetzung | REQ-L2-BL-006 | Ein Versuch, die Delta-Index-Tabelle oder Metadaten einer bestehenden Baseline nachträglich über den `BaselineStore` zu mutieren, wird blockiert (Exception). |
| T-BL-BEH-003 | Naming & Metadata Validierung | REQ-L2-BL-005 | Erstellung einer Baseline ohne passenden Namen oder fehlgeschlagener Kontextvalidierung wird vom `DeltaIndexBuilder` abgelehnt. |

### 3.2. Baseline-Retrieval & Diffing

| Test-ID | Testfall | Verknüpfte REQ | Beschreibung & Resilienz |
|---------|----------|----------------|--------------------------|
| T-BL-BEH-004 | Diff-Berechnung | REQ-L2-BL-003, REQ-L2-BL-008 | Die `DiffEngine` vergleicht zwei Baselines (Scope-kompatibel) und liefert korrekte Diffs (added/removed/changed). |
| T-BL-BEH-005 | Inkompatible Scopes Diff | REQ-L2-BL-003 | Diff-Anfrage für zwei Baselines unterschiedlicher Scopes wird sicher abgewiesen. |
| T-BL-BEH-006 | Tenant Isolation | REQ-L2-BL-007 | Abfrage einer Baseline eines Fremd-Workspaces via `ApplicationService` / `BaselineStore` wird nicht gefunden (Tenant-Boundary Isolation). |

### 3.3. Payload-Rekonstruktion

| Test-ID | Testfall | Verknüpfte REQ | Beschreibung & Resilienz |
|---------|----------|----------------|--------------------------|
| T-BL-BEH-007 | Historische Rekonstruktion | REQ-L2-BL-009 | `VersionReconstructor` liefert für definierte Item-ID/Baseline-ID den korrekten historischen Payload (`AuditLog`). Testet deterministisches Payload-Streaming zur Vermeidung großer Memory-Spikes. |

---

## 4. Leistungs- und Resilienztests (Non-Functional)

Speziell für das Delta-Storage-Design (ADR-BL-02) und den VersionReconstructor (ADR-BL-03).

| Test-ID | Fokus | Szenario |
|---------|-------|----------|
| T-BL-PERF-001 | Massendaten (OOM-Test) | Erstellung einer Baseline mit 0 Items (Minimum), > 10.000 Items (Normalfall) und 100.000 Items (Max-Limit) mit Trace-Verlinkungen (BVA). Verifikation des Speicherverbrauchs im `DeltaIndexBuilder` (Muss konstant niedrig bleiben). |
| T-BL-PERF-002 | Diff-Performance | Diff zwischen zwei Baselines mit > 10.000 Einträgen und 1.000 Änderungen. Verifikation der Effizienz über deterministische Metriken (z.B. limitierte Query-Anzahl) zur Vermeidung von Flakiness. |
| T-BL-PERF-003 | Caching VersionReconstructor | Test der Caching-Strategie von `COMP-BL-004`. Mehrfacher sequenzieller Abruf gleicher Item-Payloads muss den `AuditLog`-Datenbankzugriff signifikant reduzieren. |

---

## 5. Traceability-Matrix

| Anforderung | Komponenten | Abgedeckte Tests |
|-------------|-------------|------------------|
| REQ-L2-BL-001 | COMP-BL-001 | T-BL-STR-001..005, T-BL-BEH-001, T-BL-PERF-001 |
| REQ-L2-BL-002 | COMP-BL-003 | T-BL-STR-006..007, T-BL-BEH-001 |
| REQ-L2-BL-003 | COMP-BL-002 | T-BL-STR-001, T-BL-BEH-004, T-BL-BEH-005, T-BL-PERF-002 |
| REQ-L2-BL-004 | COMP-BL-001 | T-BL-BEH-001 |
| REQ-L2-BL-005 | COMP-BL-001 | T-BL-BEH-001, T-BL-BEH-003 |
| REQ-L2-BL-006 | COMP-BL-003 | T-BL-BEH-002 |
| REQ-L2-BL-007 | COMP-BL-003 | T-BL-BEH-006 |
| REQ-L2-BL-008 | COMP-BL-001, COMP-BL-002, COMP-BL-003 | T-BL-BEH-001, T-BL-BEH-004 |
| REQ-L2-BL-009 | COMP-BL-004 | T-BL-STR-004, T-BL-BEH-007, T-BL-PERF-003 |

---

*Erstellt durch se-test-engineer-Agent | ReqFlow SE-Kaskade | 2026-06-22*
