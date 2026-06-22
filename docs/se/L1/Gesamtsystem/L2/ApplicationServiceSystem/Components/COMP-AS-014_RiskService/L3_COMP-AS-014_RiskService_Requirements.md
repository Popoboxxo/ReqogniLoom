---
step: requirements
agent: se-requirements
iteration: 1
status: done
timestamp: "2026-06-22T14:30:00Z"
schema_version: "1.0.0"
---
# L3 RiskService Requirements

> **Level:** L3 (Component-Anforderungen)
> **Component:** COMP-AS-014_RiskService
> **Parent:** L2_ApplicationServiceSystem_Requirements.json
> **Datum:** 2026-06-22
> **Status:** formalisiert
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## Traceability

- Abgeleitet von: REQ-L1-029 (primär) — Risk-Management ist eine Cross-Cutting-Concern der L1
- Ziel: terminal (implementierungsbereit)

---

## Systemzweck

Der RiskService verwaltet den vollständigen Lifecycle von Risk-Entitäten (Risiken) im ReqFlow-System. Er orchestriert CRUD-Operationen, delegiert Workflow-Transitions an die WorkflowEngine, Traceability-Verwaltung an die TraceabilityEngine und publikziert Domain-Events via DomainEventBus. Risks sind zentrale Artefakte zur Dokumentation von identifizierten Risiken, deren Probabilität, Impact und Mitigations-Strategien.

---

## Externe Schnittstellen (Komponentengrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-AS-EXT-IN-001 | input | data | Risk CRUD-Requests vom ApplicationService (create, update, get, list, delete) |
| IF-AS-INT-002 | output | data | TraceLink-Erstellung an TraceLinkService (`create_trace_link(source_id, target_id, link_type)`) |
| IF-AS-INT-003 | output | data | Workflow-State-Transition an WorkflowFacade (`transition(item_id, target_state, change_reason, ctx)`) |
| IF-AS-INT-016 | output | event | Domain-Event-Publikation (RiskCreated/Updated/Deleted) via DomainEventBus |
| IF-AS-EXT-OUT-007 | output | data | Schreib-/Lese-Aufrufe an den PersistenceLayer (Django ORM) |

---

## L3 Component-Anforderungen

### REQ-L3-RISK-001: Risk-Erstellung mit Workflow-Initialisierung

Der RiskService SHALL ein neues Risk-Artefakt erstellen und folgende Schritte durchführen:
1. Validiere Payload (title, description, probability, impact, status obligatorisch)
2. Erstelle Risk-Entity mit eindeutiger UUID
3. Berechne Risk-Score aus probability × impact
4. Initialisiere WorkflowState gemäß aktiver WorkflowDefinition der Workspace
5. Persistiere Artefakt (Transactional)

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Risk wird mit valider UUID erstellt
- [ ] Risk-Score wird berechnet (1-25 Skala)
- [ ] WorkflowState wird automatisch initialisiert
- [ ] Transaktionale Persistierung
- [ ] Rückgabe der erstellten Risk-UUID

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-INT-003, IF-AS-EXT-OUT-007
**Traceability:** REQ-L1-029
**Rationale:** Risks sind Entscheidungs-Artefakte mit State-Management und Scoring.

---

### REQ-L3-RISK-002: Risk-Metadaten und Klassifikation

Der RiskService SHALL Risks mit strukturierten Metadaten speichern:
- `title`: kurze Risiko-Beschreibung
- `description`: detaillierte Risiko-Charakterisierung
- `category`: enum (technical, operational, organizational, business)
- `probability`: enum (low, medium, high) → numerisch 1-3
- `impact`: enum (low, medium, high) → numerisch 1-3
- `owner`: optional User/Agent, der für Mitigation verantwortlich ist
- `mitigation_strategy`: optional, Beschreibung der Maßnahmen
- `status`: enum (Identified, Monitored, Mitigated, Accepted, Closed)

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Alle Felder werden validiert
- [ ] Probability und Impact werden numerisch gespeichert
- [ ] Risk-Score ist berechenbar (prob × impact)
- [ ] Status ist änderbar per Workflow-Transition

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Traceability:** REQ-L1-029
**Rationale:** Strukturierte Risiko-Erfassung ermöglicht Analyse und Priorisierung.

---

### REQ-L3-RISK-003: Risk-Update mit Versionierung

Der RiskService SHALL Risk-Updates mit Versionshistorie verwalten. Bei Änderungen:
1. Alte Version bleibt unverändert
2. Neue Version mit version+1 wird erstellt
3. Timestamp und Actor (User/Agent) werden erfasst
4. Risk-Score wird bei Änderung von probability/impact neu berechnet

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Alte Risk-Versionen bleiben lesbar
- [ ] Neue Version wird mit version+1 gekennzeichnet
- [ ] Audit-Trail ist vollständig
- [ ] Risk-Score wird aktualisiert

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Traceability:** REQ-L1-029
**Rationale:** Nachvollziehbarkeit von Risiko-Änderungen.

---

### REQ-L3-RISK-004: Risk-Deletion mit Cascade-Cleanup

Bei Löschung eines Risks SHALL der RiskService:
1. Alle TraceLinks zum Risk löschen
2. WorkflowState-History löschen
3. Risk-Entität selbst löschen
4. Alles in einer Transaktion

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] TraceLinks werden gelöscht
- [ ] WorkflowState wird bereinigt
- [ ] Risk wird gelöscht
- [ ] Atomare Transaktion

**Interfaces:** IF-AS-INT-002, IF-AS-EXT-OUT-007
**Traceability:** REQ-L1-029
**Rationale:** Referenzielle Integrität.

---

### REQ-L3-RISK-005: Risk-Status-Transitions mit Workflow-Engine

Der RiskService SHALL Workflow-State-Transitions für Risks delegieren an WorkflowFacade. Gültige Status sind:
- Identified (initial)
- Monitored
- Mitigated
- Accepted
- Closed

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Transition wird an WorkflowFacade delegiert
- [ ] Erlaubte Übergänge gemäß WorkflowDefinition
- [ ] change_reason wird erfasst (wenn erforderlich)
- [ ] Audit-Log-Eintrag wird geschrieben

**Interfaces:** IF-AS-INT-003
**Traceability:** REQ-L1-029
**Rationale:** Kontrolled Risk-Lifecycle.

---

### REQ-L3-RISK-006: TraceLink-Verwaltung für Risk-Relationen

Der RiskService SHALL TraceLinks zwischen Risks und anderen Artefakten verwalten. Unterstützte Link-Typen:
- `threatens` (Risk gefährdet ein Requirement oder ArchitectureElement)
- `mitigated-by` (Risk wird durch ein Requirement oder ADR mitigiert)
- `related-to` (Risk ist verwandt mit anderer Risk oder Artefakt)

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] TraceLinks werden via TraceLinkService erstellt
- [ ] Link-Typ-Validierung
- [ ] Bidirektionale Querybarkeit
- [ ] Link-Erstellung ist optional

**Interfaces:** IF-AS-INT-002
**Traceability:** REQ-L1-029
**Rationale:** Impact-Analyse und Traceability.

---

### REQ-L3-RISK-007: Risk-Priorisierung nach Score

Der RiskService SHALL Risks nach Risk-Score sortieren können:
- Risk-Score = probability × impact (1-25)
- High Risk: Score ≥9
- Medium Risk: Score 4-8
- Low Risk: Score 1-3

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Risk-Score wird bei CREATE/UPDATE aktualisiert
- [ ] Sorting nach Score aufsteigend/absteigend
- [ ] Risk-Kategorien (High/Medium/Low) sind querybar
- [ ] Score wird in Result-Payload geliefert

**Interfaces:** IF-AS-EXT-OUT-007
**Traceability:** REQ-L1-029
**Rationale:** Priorisierung für Impact-Analyse.

---

### REQ-L3-RISK-008: Tenant-Isolation für Risks

Der RiskService SHALL garantieren:
1. Risks nur innerhalb gleicher Workspace
2. TraceLinks nicht Workspace-übergreifend
3. Alle Queries tenant-isoliert

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Tenant wird aus Auth-Context extrahiert
- [ ] Risk wird mit tenant_id gekennzeichnet
- [ ] Keine Cross-Tenant-Queries
- [ ] Keine Cross-Tenant-TraceLinks

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Traceability:** REQ-L2-AppSvc-022
**Rationale:** Sicherheit und Datenisolation.

---

### REQ-L3-RISK-009: Domain-Event-Publikation für Risk-Mutations

Nach erfolgreicher Mutation SHALL der RiskService Domain-Events publikzieren:
- `RiskCreated` (mit Risk-UUID und Snapshot)
- `RiskUpdated` (mit Risk-UUID, Änderungen)
- `RiskDeleted` (mit Risk-UUID)

Diese Events werden via DomainEventBus publiziert.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Events werden nach Commit publiziert
- [ ] Event-Payload ist strukturiert
- [ ] Events via IF-AS-INT-016 gestellt
- [ ] Fire-and-Forget (nicht-blockierend)

**Interfaces:** IF-AS-INT-016
**Traceability:** REQ-L2-AppSvc-026
**Rationale:** Asynchrone Publikation für Audit und externe Systeme.

---

### REQ-L3-RISK-010: Risk-Abfragen und Listing

Der RiskService SHALL folgende Query-Operationen unterstützen:
- `get_by_id(risk_id)` → einzelnes Risk
- `list_by_workspace(workspace_id)` → alle Risks (paginiert)
- `list_by_status(workspace_id, status)` → gefiltert nach Status
- `list_by_score_range(workspace_id, min, max)` → gefiltert nach Score
- `search(workspace_id, query_text)` → Volltextsuche

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Alle Queries sind tenant-isoliert
- [ ] Pagination für `list_*`
- [ ] Score-Filterung funktioniert
- [ ] Suchabfragen nutzen FTS
- [ ] Queries performant (≤500ms)

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Traceability:** REQ-L1-029
**Rationale:** Abfrageunterstützung für Analyse und Reporting.

---

## Traceability-Matrix: REQ-L3-RISK → REQ-L2/L1

| REQ-L3 | Primäre REQ-L2/L1 |
|--------|------------------|
| REQ-L3-RISK-001 | REQ-L1-029 |
| REQ-L3-RISK-002 | REQ-L1-029 |
| REQ-L3-RISK-003 | REQ-L1-029 |
| REQ-L3-RISK-004 | REQ-L1-029 |
| REQ-L3-RISK-005 | REQ-L1-029 |
| REQ-L3-RISK-006 | REQ-L1-029 |
| REQ-L3-RISK-007 | REQ-L1-029 |
| REQ-L3-RISK-008 | REQ-L2-AppSvc-022 |
| REQ-L3-RISK-009 | REQ-L2-AppSvc-026 |
| REQ-L3-RISK-010 | REQ-L1-029 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
