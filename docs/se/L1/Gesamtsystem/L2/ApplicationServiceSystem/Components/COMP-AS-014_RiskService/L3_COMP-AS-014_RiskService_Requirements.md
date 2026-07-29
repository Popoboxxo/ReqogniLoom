---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T14:45:00Z"
schema_version: "1.0.0"
---
# L3 RiskService Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-AS-014_RiskService
> **Parent:** L2_ApplicationServiceSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Der RiskService verwaltet den vollständigen Lifecycle von Risk-Entitäten im ReqFlow-System. Er orchestriert CRUD-Operationen, delegiert Workflow-Transitions an die WorkflowFacade, verwaltet TraceLinks via TraceLinkService und publikziert Domain-Events via DomainEventBus. Risks sind zentrale Artefakte zur Dokumentation von identifizierten Risiken, deren Probabilität, Impact und Mitigations-Strategien. Der Service implementiert automatische Risk-Score-Berechnung und Priorisierung nach Score.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`RiskService` (Klasse):** Orchestrator für Risk-Operationen:
  - `create_risk(title, description, probability, impact, category, owner, mitigation_strategy, status, workspace_id, auth_context) → Risk`
  - `update_risk(risk_id, updates) → Risk`
  - `get_risk(risk_id) → Risk`
  - `list_risk(workspace_id, page, limit) → [Risk]`
  - `list_by_score_range(workspace_id, min, max) → [Risk]`
  - `delete_risk(risk_id)`
  - `transition_status(risk_id, target_status, change_reason, auth_context) → Risk`
  - `create_tracelink(risk_id, target_id, link_type) → TraceLink`

- **`RiskScoreCalculator` (Klasse):** Berechnet Risk-Score = probability_numeric × impact_numeric (1-3 × 1-3 = 1-25).

- **`RiskValidator` (Klasse):** Validiert Risk-Payloads gegen Schema.

- **`RiskDTO` (DTO):** Data Transfer Object für Risk-Responses.

### 2.2 Datenstrukturen

- **Risk-Entity:**
  - `id`: UUID (PK)
  - `workspace_id`: UUID (FK)
  - `tenant_id`: UUID (FK)
  - `title`: String
  - `description`: String
  - `category`: enum (technical, operational, organizational, business)
  - `probability`: enum (low=1, medium=2, high=3)
  - `impact`: enum (low=1, medium=2, high=3)
  - `risk_score`: Integer (calculated = probability × impact, 1-25)
  - `owner`: String (optional, User-ID)
  - `mitigation_strategy`: String (optional)
  - `status`: enum (Identified, Monitored, Mitigated, Accepted, Closed)
  - `version`: Integer (Append-Only)
  - `created_at`, `updated_at`: DateTime
  - `created_by`: String

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-RISK-001 (Risk-Erstellung) | Methode `create_risk(payload)`: (1) Validiere Payload (title, description, probability, impact, status erforderlich), (2) Erstelle Risk-Entity mit UUID, (3) Berechne Risk-Score (probability × impact), (4) Initialisiere WorkflowState (delegiere an WorkflowFacade), (5) Persistiere atomare Transaktion. Rückgabe: Risk-UUID. |
| REQ-L3-RISK-002 (Risk-Metadaten) | Risk-Entity speichert: title, description, category (technical/operational/organizational/business), probability (1-3 numerisch), impact (1-3 numerisch), owner (optional), mitigation_strategy (optional), status (enum). Alle Felder validiert. Risk-Score berechenbar. Status änderbar per Workflow-Transition. |
| REQ-L3-RISK-003 (Update mit Versionierung) | Methode `update_risk(risk_id, updates)`: Alte Version beibehalten, neue Version mit version+1 erstellen. Risk-Score wird neu berechnet wenn probability/impact geändert. Timestamp und Actor erfasst. Audit-Trail vollständig. |
| REQ-L3-RISK-004 (Deletion mit Cascade-Cleanup) | Methode `delete_risk(risk_id)` in `transaction.atomic()`: (1) Lösche TraceLinks, (2) Lösche WorkflowState-History, (3) Lösche Risk. Bei Fehler: Rollback. |
| REQ-L3-RISK-005 (Status-Transitions) | Methode `transition_status(risk_id, target_status, change_reason)`: Delegiere an WorkflowFacade. Gültige Status: Identified (initial) → Monitored → Mitigated (oder Accepted) → Closed. change_reason erfasst (wenn erforderlich). Audit-Log-Eintrag geschrieben. |
| REQ-L3-RISK-006 (TraceLink-Verwaltung) | Methode `create_tracelink(risk_id, target_id, link_type)`: Unterstützte Link-Typen: threatens (Risk gefährdet Requirement/ArchitectureElement), mitigated-by (Risk wird mitigiert), related-to. Rufe TraceLinkService auf. Bidirektionale Querybarkeit. |
| REQ-L3-RISK-007 (Priorisierung nach Score) | RiskScoreCalculator: Score = prob × impact (1-25). High Risk: Score ≥9, Medium: 4-8, Low: 1-3. Sorting nach Score aufsteigend/absteigend möglich. Score wird bei CREATE/UPDATE aktualisiert. Risk-Kategorien (High/Medium/Low) sind querybar. Score in Result-Payload. |
| REQ-L3-RISK-008 (Tenant-Isolation) | Tenant wird aus Auth-Context extrahiert. Risk wird mit tenant_id gekennzeichnet. Keine Cross-Tenant-Queries. Keine Cross-Tenant-TraceLinks. |
| REQ-L3-RISK-009 (Domain-Event-Publikation) | Nach erfolgreicher Mutation: Publiziere Event via DomainEventBus (post_commit Hook). Events: RiskCreated, RiskUpdated, RiskDeleted. Event-Payload strukturiert. Fire-and-Forget. |
| REQ-L3-RISK-010 (Abfragen und Listing) | Methoden: get_by_id(), list_by_workspace(), list_by_status(), list_by_score_range(min, max), search(query_text). Alle Queries tenant-isoliert. Pagination. FTS. Queries performant (≤500ms). |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-AS-EXT-IN-001:** REST API Endpoints für Risk CRUD.

- **Ausgänge (Outbound):**
  - **IF-AS-INT-002:** Aufruf TraceLinkService.
  - **IF-AS-INT-003:** Aufruf WorkflowFacade.
  - **IF-AS-INT-016 (Domain-Event):** Publikation RiskCreated/Updated/Deleted Events via DomainEventBus.
  - **IF-AS-EXT-OUT-007:** ORM-Aufrufe an PersistenceLayer.

---

## 5. Architectural Rationale

**ADR-L3-RISK-01 — Automatische Risk-Score-Berechnung statt Manueller Eingabe**

*Entscheidung:* Risk-Score wird automatisch berechnet (probability × impact), nicht manuell vom Nutzer eingegeben.

*Rationale:* Verhindert Inkonsistenzen und Fehleingaben. Score ist deterministische Funktion von probability/impact. Alternative: Benutzer gibt Score ein → Risiko von Fehlern (Score entspricht nicht probability×impact). **Abgelehnt**: Automatische Berechnung ist weniger fehleranfällig.

*Erfüllt Trigger:* REQ-L3-RISK-007 (Priorisierung nach Score).

---

**ADR-L3-RISK-02 — Enum-Probability/Impact statt Freier Numerischer Eingabe**

*Entscheidung:* Probability und Impact sind enums (low=1, medium=2, high=3), nicht freie numerische Eingabe.

*Rationale:* Vereinfacht Klassifikation und Konsistenz. Benutzer wählt aus 3 Optionen, Score ist dann deterministisch. Alternative: Freie numerische Eingabe (1-5, 1-10) → Inkonsistenzen zwischen Nutzern, schwerer zu vergleichen. **Abgelehnt**: Enum ist praktikabler für Risk-Management.

*Erfüllt Trigger:* REQ-L3-RISK-002 (Risk-Metadaten).

---

**ADR-L3-RISK-03 — Score-Range-Query statt Nur Status-Filter**

*Entscheidung:* Zusätzlich zu Status-Filterung wird Score-Range-Filterung unterstützt (`list_by_score_range(min, max)`).

*Rationale:* Ermöglicht Impact-Analyse: "Alle High-Risk-Items (Score≥9)" ist wichtiger Use-Case als nur Status-Filter. Alternative: Nur Status-Filter → Nutzer müsste manuell Ergebnisse sortieren. **Abgelehnt**: Risk-Management erfordert Score-basierte Priorisierung.

*Erfüllt Trigger:* REQ-L3-RISK-007 (Priorisierung nach Score).

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
