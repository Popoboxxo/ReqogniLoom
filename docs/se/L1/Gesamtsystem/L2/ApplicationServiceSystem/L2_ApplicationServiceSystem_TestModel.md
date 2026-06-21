# L2 ApplicationServiceSystem TestModel

> **Level:** L2 (Subsystem white-box)
> **System:** ApplicationServiceSystem (ARCH-L1-004)
> **Basierend auf:** L2_ApplicationServiceSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen

---

## 1. Teststrategie & Ziele

Das `ApplicationServiceSystem` fungiert als zentrale Fassade für Use-Cases und orchestriert diverse fachliche Services. Die Integrationstests fokussieren sich auf das korrekte Zusammenspiel dieser Services, die transaktionale Sicherheit sowie die konsistente Generierung und Verarbeitung von Events über den `DomainEventBus`.

### Primäre Testziele
- **Service-Orchestrierung:** Korrekte Zusammenarbeit zwischen schreibenden Services (z.B. RequirementService, AdrService) und Querschnitts-Services (TraceLinkService, WorkflowFacade).
- **Event-Driven Architecture (COMP-AS-016):** Sicherstellen, dass Domain-Events (z.B. `AdrCreated`, `RiskUpdated`) nach Commit korrekt im Transactional-Outbox-Store abgelegt und an Subscriber (WebhookDispatcher, AuditLog) asynchron zugestellt werden.
- **Transaktionale Konsistenz:** Fehlerhafte Operationen müssen vollständig zurückgerollt werden, ohne Events oder verwaiste TraceLinks zu hinterlassen.

---

## 2. Testumgebung & Setup

- **Test-Framework:** Pytest mit `pytest-django` für DB-Transaktionen.
- **Mocks / Stubs:**
  - `RestApiAdapter` und `McpServer` werden nicht hier getestet (L1 Fokus). Wir rufen Python-APIs direkt auf.
  - Externe Subsysteme (`WorkflowEngine`, `BaselineService`, `TraceabilityEngine`, `LlmAdapter`, `AuditLog`, `PresetConfigEngine`) werden als In-Memory-Stubs gemockt.
- **Flakiness-Prävention & Teardown-Strategie:**
  - Mock-Isolation: `unittest.mock.patch` oder `pytest-mock` verwenden, wobei jeder Test in einer eigenen Fixture (z.B. `autouse=True`) die Mocks für `TraceabilityEngine` und `WorkflowEngine` zurücksetzt (`mock.reset_mock()`).
  - In-Memory-Stubs: Singleton-State in Stubs (wie Event-Queues im asynchronen Dispatcher-Mock) wird via `yield`-Teardown-Logik in den pytest-Fixtures nach jedem Testfall zwingend geleert.
- **Event-Processing:** Der asynchrone Dispatcher für den `DomainEventBus` wird für Tests synchron ausgeführt (z.B. `CELERY_TASK_ALWAYS_EAGER = True` oder equivalentes Django-Q Setting), um Zustellung prüfen zu können.

---

## 3. Struktur- und Schnittstellentests

### 3.1 TraceLink Cascade (IF-AS-INT-001 bis IF-AS-INT-005)
- **Beschreibung:** Löschen eines Artifacts/Requirements/ADRs löscht korrespondierende TraceLinks.
- **Test-Fälle:**
  - Lösche eine Requirement (COMP-AS-002) -> TraceLinkService (COMP-AS-005) löscht verknüpfte TraceLinks.
  - Lösche ein Risk (COMP-AS-014) -> TraceLinkService löscht Links zum mitigierenden Requirement.

### 3.2 Workflow Transition Orchestrierung (IF-AS-INT-003)
- **Beschreibung:** CRUD-Operationen oder explizite Transitions von Entity-Services rufen WorkflowFacade auf.
- **Test-Fälle:**
  - Genehmigung eines Issue (COMP-AS-015) -> `WorkflowFacade.transition` wird aufgerufen.
  - Fehlschlag der Transition in der Engine bricht gesamte Transaktion ab.

### 3.3 Domain Event Bus Publikation (IF-AS-INT-009 bis IF-AS-INT-012, IF-AS-INT-015 bis IF-AS-INT-017)
- **Beschreibung:** Entity-Operationen hinterlassen Events in der Outbox.
- **Test-Fälle:**
  - Erstelle Adr (COMP-AS-013) -> `AdrCreated` Event existiert in der Outbox.
  - Update Risk (COMP-AS-014) -> `RiskUpdated` Event existiert in der Outbox.
  - Delete Issue (COMP-AS-015) -> `IssueDeleted` Event existiert in der Outbox.

### 3.4 Asynchroner Dispatch (IF-AS-INT-013, IF-AS-INT-014)
- **Beschreibung:** Outbox-Events werden an Subscriber zugestellt.
- **Test-Fälle:**
  - Event-Worker konsumiert `RiskCreated` -> WebhookDispatcher (COMP-AS-011) erhält Event.
  - Event-Worker konsumiert `AdrUpdated` -> Externe `AuditLog`-Facade empfängt Async-Call.

### 3.5 Boundary Value Analysis (BVA)
- **Beschreibung:** Validierung von Grenzwerten bei der Erstellung und Bearbeitung von Entities, insbesondere für die neuen Services (AdrService, RiskService, IssueService).
- **Test-Fälle:**
  - **String-Längen:** Anlage eines Adr (COMP-AS-013) mit exakt maximaler Titellänge (z.B. 255 Zeichen) -> Erfolg. Anlage mit 256 Zeichen -> Validierungsfehler.
  - **Paginierung:** Abfrage von 100 Issues -> Paginierung greift korrekt, Rückgabe des Limits.
  - **TraceLinks Limit:** Verknüpfung von maximal erlaubten Links an ein Risk (z.B. 50 TraceLinks) -> Erfolg. 51. Link -> `MaxLinksExceededException`.

### 3.6 Äquivalenzklassen-Validierung (Equivalence Classes)
- **Beschreibung:** Überprüfung verschiedener Eingabe-Äquivalenzklassen auf korrekte Verarbeitung oder Abweisung.
- **Test-Fälle:**
  - **Statusübergänge (Issues):** Gültige Zielstatus ("Open" -> "In Progress") delegieren an WorkflowEngine und führen zum Update. Ungültige Zielstatus ("Closed" -> "In Progress" bei finalem Status) werden direkt abgewiesen.
  - **Verlinkungen (ADR/Risk):** Risk mit verknüpftem Requirement (gültige Klasse) -> wird gespeichert. Risk mit unzulässigem Verlinkungstyp zu Issue (ungültige Klasse, gemäß TraceabilityEngine) -> `InvalidTraceLinkException`.

---

## 4. Verhaltenstests (End-to-End Szenarien im Subsystem)

### Szenario A: Komplexe Item-Anlage mit Trace und Event (AdrService Fokus)
**Vorbedingung:** Ein Requirement existiert.
**Schritte:**
1. Aufruf `AdrService.create_adr(...)` mit Verknüpfung zum Requirement (via `TraceLinkService`).
2. AdrService ruft `WorkflowFacade` auf, um Initialstatus zu setzen.
3. Transaktion committet.
**Erwartetes Resultat:**
- ADR ist in DB (PersistenceLayer).
- TraceLink zwischen ADR und Requirement existiert (COMP-AS-005).
- `AdrCreated` Event liegt in Outbox (COMP-AS-016).
- AuditLog-Mock und WebhookDispatcher registrieren erfolgreichen Dispatch des Events.

### Szenario B: Transaktionsabbruch bei Transition-Fehler (IssueService Fokus)
**Vorbedingung:** Ein Issue existiert im Status "Open".
**Schritte:**
1. Aufruf `IssueService.resolve_issue(...)` (oder ähnliche Update-Aktion).
2. `WorkflowFacade` (COMP-AS-007) delegiert an gemockte `WorkflowEngine`, welche eine ValidationException wirft (z.B. fehlende Rolle).
**Erwartetes Resultat:**
- Exception propariert zum Caller.
- Issue bleibt unverändert in DB.
- **Wichtig:** Kein `IssueUpdated` Event landet im `DomainEventBus`, da die DB-Transaktion abgebrochen wurde.

### Szenario C: Policy Check für Risk Modification (RiskService Fokus)
**Vorbedingung:** Preset erzwingt `change_reason` für Risks.
**Schritte:**
1. Aufruf `RiskService.update_risk(...)` ohne `change_reason`.
2. RiskService konsultiert `PresetPolicyService` (COMP-AS-012) via `is_change_reason_required`.
**Erwartetes Resultat:**
- PresetPolicyService wirft PolicyViolationException.
- Risk wird nicht gespeichert.
- Kein Event wird publiziert.

### Szenario D: Nebenläufigkeit und Optimistic Locking (IssueService Fokus)
**Vorbedingung:** Ein Issue (COMP-AS-015) existiert in der DB (Version = 1).
**Schritte:**
1. Prozess A lädt das Issue (Version 1).
2. Prozess B lädt das selbe Issue (Version 1).
3. Prozess A speichert Update (Status = "In Progress") -> DB-Version auf 2 hochgezählt.
4. Prozess B versucht Update zu speichern (Status = "Resolved").
**Erwartetes Resultat:**
- Prozess B erhält `OptimisticLockException` (oder `StaleObjectStateException`).
- Update von Prozess B wird zurückgerollt, keine Events für Prozess B in Outbox.

### Szenario E: Fehler bei Outbox-Generierung
**Vorbedingung:** `DomainEventBus` (COMP-AS-016) Outbox-Tabelle simuliert einen Datenbankfehler.
**Schritte:**
1. Aufruf `AdrService.create_adr(...)`.
2. Entity in DB geschrieben, post_commit-Hook versucht Outbox-Eintrag zu erstellen -> wirft `DatabaseError`.
**Erwartetes Resultat:**
- Gesamt-Transaktion muss fehlschlagen (oder es gibt eine Fallback-Strategie, die explizit getestet wird).
- Entity wird NICHT persisting gemacht, kein verwaister Zustand.

### Szenario F: Traceability Validierung durch TraceabilityEngine (Interface Coverage)
**Vorbedingung:** Gemockte `TraceabilityEngine` (IF-AS-EXT-OUT-003) ist mit spezifischen Regeln konfiguriert (z.B. "ADR muss immer mit mindestens einem Requirement verlinkt sein").
**Schritte:**
1. `AdrService.create_adr(...)` wird ohne Traces aufgerufen.
2. AdrService ruft intern die `TraceabilityEngine` zur Validierung auf.
**Erwartetes Resultat:**
- TraceabilityEngine lehnt Erstellung ab.
- `AdrService` wirft `TraceabilityValidationException`.
- Keine Entität wird gespeichert, kein Domain-Event generiert.

---

## 5. Traceability & Abdeckung

Die folgenden Architekturelemente und Anforderungen werden durch dieses TestModel abgedeckt:

| Arch-Komponente | Anforderung (REQ) | Relevante Testfälle | Status |
|-----------------|-------------------|---------------------|--------|
| COMP-AS-002 (RequirementService) | REQ-L2-AS-003, REQ-L2-AS-013, REQ-L2-AS-015, REQ-L2-AS-024 | 3.1, 3.3 | Abgedeckt |
| COMP-AS-005 (TraceLinkService) | REQ-L2-AS-010 | 3.1, Szenario A | Abgedeckt |
| COMP-AS-007 (WorkflowFacade) | REQ-L2-AS-012 | 3.2, Szenario B | Abgedeckt |
| COMP-AS-011 (WebhookDispatcher) | REQ-L2-AS-017 | 3.4, Szenario A | Abgedeckt |
| COMP-AS-012 (PresetPolicyService)| REQ-L2-AS-020 | Szenario C | Abgedeckt |
| COMP-AS-013 (AdrService) | REQ-L1-029 | 3.3, 3.5, 3.6, Szenario A, E, F | Abgedeckt |
| COMP-AS-014 (RiskService) | REQ-L1-029 | 3.1, 3.3, 3.5, 3.6, Szenario C, F | Abgedeckt |
| COMP-AS-015 (IssueService) | REQ-L1-029 | 3.2, 3.3, 3.5, 3.6, Szenario B, D, F | Abgedeckt |
| COMP-AS-016 (DomainEventBus) | REQ-L2-AS-026 | 3.3, 3.4, Szenario A, B, E | Abgedeckt |
