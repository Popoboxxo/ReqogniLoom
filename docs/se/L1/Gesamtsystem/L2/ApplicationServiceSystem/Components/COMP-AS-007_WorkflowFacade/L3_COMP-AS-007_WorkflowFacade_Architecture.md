---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T14:45:00Z"
schema_version: "1.0.0"
---
# L3 WorkflowFacade Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-AS-007_WorkflowFacade
> **Parent:** L2_ApplicationServiceSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Der WorkflowFacade orchestriert Workflow-State-Transitions für alle Artefakt-Typen (Requirements, ArchitectureElements, TestCases, ADRs, Risks, Issues). Er ist die Single Point of Entry für Zustandsübergänge und stellt sicher, dass Validierungen (erforderliche Rollen, change_reason-Anforderungen) vor Delegierung an die WorkflowEngine erfolgen. Nach erfolgreicher Transition publiziert er AuditLog-Einträge via DomainEventBus.

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box hier keine weiteren SE-Subsysteme, sondern die internen Software-Klassen und Datenstrukturen.

### 2.1 Klassen und Module

- **`WorkflowFacade` (Klasse):** Hauptorchestrator für `transition(item_id, target_state, change_reason, auth_context)`.
  - Validiert Eingabeparameter (item existiert, target_state ist erlaubt)
  - Konsultiert PresetPolicyService zur Rolle-Validierung
  - Konsultiert PresetPolicyService zur change_reason-Validierung
  - Delegiert an WorkflowEngine für State-Transition
  - Publiziert AuditLog-Event via DomainEventBus bei Erfolg
  - Rollback bei AuditLog-Fehler (atomare Transaktion)

- **`TransitionRequest` (DTO):** Datenstruktur für Transition-Anfrage mit Feldern: item_id, target_state, change_reason (optional), auth_context.

- **`TransitionResponse` (DTO):** Erfolgreiche Transition mit altem/neuem State, Timestamp, Actor.

- **`WorkflowCache` (Cache-Manager):** In-Memory Cache für Workflow-Definitionen und Preset-Regeln (TTL 5 Minuten, Invalidierung bei Preset-Update-Events).

### 2.2 Datenstrukturen

- **WorkflowState-Entity:**
  - `id`: UUID (PK)
  - `item_id`: UUID (FK auf das betroffene Artefakt)
  - `item_type`: String (enum: Requirement, ArchitectureElement, TestCase, Adr, Risk, Issue)
  - `current_state`: String (z.B. "Draft", "In Review", "Approved")
  - `previous_state`: String (für Audit)
  - `transitioned_at`: DateTime
  - `transitioned_by`: String (User/Agent-ID)
  - `change_reason`: String (optional, für audit)

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-WF-001 (Transition-Request-Validierung) | Methode `_validate_request(request)` vor Delegierung: (1) Verifiziere item_id existiert via PersistenceLayer, (2) Verifiziere target_state ist in WorkflowDefinition erlaubt, (3) Konsultiere PresetPolicyService.validate_transition_roles() — blockiere bei ungültiger Rolle. Bei Fehlern: strukturierter Error zurückgeben, keine Delegierung. |
| REQ-L3-WF-002 (Delegierung an WorkflowEngine) | Methode `_delegate_to_engine(request)` nach erfolgreicher Validierung: Rufe `WorkflowEngine.transition(item_id, target_state, change_reason, auth_context)` auf mit Auth-Kontext unverändert weitergegeben. Timeout 5s. Fehler strukturiert propagiert. |
| REQ-L3-WF-003 (AuditLog-Eintrag) | Methode `_publish_audit_event(request, old_state, new_state)` nach erfolgreichem Engine-Aufruf: Erstelle AuditLog-Event mit entity_id, old_state, new_state, change_reason, timestamp, actor. Publiziere via DomainEventBus.publish() (fire-and-forget). |
| REQ-L3-WF-004 (Change-Reason-Validierung) | In `_validate_request()`: Rufe PresetPolicyService.is_change_reason_required(workspace_id) auf. Wenn true und change_reason fehlt/leer → Error abgebrochen. Längenbeschränkung: max 500 Zeichen. |
| REQ-L3-WF-005 (Fehlerbehandlung und Rollback) | Bei WorkflowEngine-Fehler oder AuditLog-Fehler: Operation abgebrochen, kein AuditLog-Eintrag geschrieben. Fehler strukturiert zurückgegeben mit HTTP-Status (400 für Validierung, 403 für Autorisierung). |
| REQ-L3-WF-006 (Atomare Transaktionssemantik) | Umhülle Engine-Aufruf + AuditLog-Publikation in `transaction.atomic()` (Django). Bei AuditLog-Fehler: Rollback der gesamten Transition via transaction.set_rollback(). |
| REQ-L3-WF-007 (Caching und Performance) | WorkflowCache mit 5-Minuten-TTL: Cache von Workflow-Definitionen und Preset-Regeln reduziert PresetPolicyService-Aufrufe. Listener auf Preset-Update-Events zum Invalidieren. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-AS-EXT-IN-001:** REST API oder ApplicationService-Methoden (`transition_requirement`, `transition_architecture_element`, etc.) mit TransitionRequest-Payload.

- **Ausgänge (Outbound):**
  - **IF-AS-INT-003:** Aufruf an WorkflowEngine (`WorkflowEngine.transition()`) — Python Function Call.
  - **IF-AS-INT-007:** Konsultation PresetPolicyService (`validate_transition_roles()`, `is_change_reason_required()`) — Python Function Call.
  - **IF-AS-INT-015 (Domain-Event-Publikation):** Aufruf `DomainEventBus.publish(WorkflowTransitionedEvent)` — async enqueue.
  - **IF-AS-EXT-OUT-007:** ORM-Aufrufe an PersistenceLayer zur Validierung item_id-Existenz (SELECT Queries).

---

## 5. Architectural Rationale

**ADR-L3-WF-01 — Facade Pattern für Zustandsübergänge**

*Entscheidung:* WorkflowFacade ist die alleinige Eingangsschnittstelle für State-Transitions. Alle Validierungen erfolgen vor Delegierung an die WorkflowEngine.

*Rationale:* Entkopplung von Validierungslogik (PresetPolicy, change_reason, Rolle) von der Transition-Engine selbst. Dies ermöglicht flexible Preset-Verwaltung ohne Engine-Änderungen. Alternativen: (1) WorkflowEngine enthält alle Validierungen → Monolithische Engine, schwer zu testen; (2) Jeder Service validiert selbst → Inkonsistente Regeln, keine Single Source of Truth. **Abgelehnt**: Validierungen sind Cross-Cutting und müssen zentralisiert sein.

*Erfüllt Trigger:* REQ-L3-WF-001, REQ-L3-WF-004 (Validierungen vor Delegierung).

---

**ADR-L3-WF-02 — Atomare Transaktionssemantik mit rollback on AuditLog-Fehler**

*Entscheidung:* Transition + AuditLog-Publikation erfolgen in einer einzigen Datenbank-Transaktion. AuditLog-Fehler triggert Rollback der Transition.

*Rationale:* Verhindert Zustand, in dem die Transition erfolgreich ist, aber keine Auditierung existiert (Compliance-Risiko). Alternative: Fire-and-Forget AuditLog (nicht blockiert) → Schwache Auditierbarkeit, akzeptabel für Operational Logs, aber nicht für State-Transitions, wo Governance kritisch ist. **Abgelehnt**: Schwache Konsistenz nicht akzeptabel für Workflow-State-Management.

*Erfüllt Trigger:* REQ-L3-WF-006 (atomare Transaktionssemantik).

---

**ADR-L3-WF-03 — In-Memory Cache für Preset-Regeln**

*Entscheidung:* Workflow-Definitionen und Preset-Regeln werden bis zu 5 Minuten gecacht. Invalidierung bei Preset-Update-Events.

*Rationale:* PresetPolicyService wird bei fast jedem Transition-Request konsultiert (REQ-L3-WF-001, REQ-L3-WF-004). Caching reduziert Latenz und DB-Last um 70%+. Alternative: Kein Cache, jedes Mal live query → Höhere Latenz (50-200ms pro Preset-Query). **Abgelehnt**: Performance-Anforderung REQ-L3-WF-007 erfordert Caching.

*Erfüllt Trigger:* REQ-L3-WF-007 (Performance).

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
