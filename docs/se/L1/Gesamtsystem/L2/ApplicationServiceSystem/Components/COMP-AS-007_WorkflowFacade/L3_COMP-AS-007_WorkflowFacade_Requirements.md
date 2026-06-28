---
step: requirements
agent: se-requirements
iteration: 1
status: done
timestamp: "2026-06-22T14:30:00Z"
schema_version: "1.0.0"
---
# L3 WorkflowFacade Requirements

> **Level:** L3 (Component-Anforderungen)
> **Component:** COMP-AS-007_WorkflowFacade
> **Parent:** L2_ApplicationServiceSystem_Requirements.json
> **Datum:** 2026-06-22
> **Status:** formalisiert
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## Traceability

- Abgeleitet von: REQ-L2-AppSvc-012 (primär)
- Ziel: terminal (implementierungsbereit)

---

## Systemzweck

Der WorkflowFacade orchestriert Workflow-State-Transitions für Anforderungen, ArchitectureElements und TestCases. Er delegiert Validierungen (erlaubte Rollen, change_reason-Anforderungen) an die WorkflowEngine, schreibt AuditLog-Einträge und stellt sicher, dass der ApplicationService keine Workflow-Interna direkt manipuliert.

---

## Externe Schnittstellen (Komponentengrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-AS-EXT-IN-001 | input | data | Transition-Request vom ApplicationService oder RestApiAdapter (item_id, target_state, change_reason, auth context) |
| IF-AS-INT-003 | output | data | Delegierung an WorkflowEngine (`transition(item_id, target_state, change_reason, ctx)`) |
| IF-AS-INT-007 | output | control | Konsultation PresetPolicyService für Role-Validierung (`validate_transition_roles(ctx, target_state)`) |
| IF-AS-EXT-OUT-007 | output | data | Schreib-/Lese-Aufrufe an den PersistenceLayer (Django ORM) |
| IF-AS-EXT-OUT-006 | output | event | Domain-Event-Publikation für AuditLog (via DomainEventBus) |

---

## L3 Component-Anforderungen

### REQ-L3-WF-001: Transition-Request-Validierung

Der WorkflowFacade SHALL vor der Delegierung an die WorkflowEngine folgende Validierungen durchführen:
1. Verifiziere, dass die Zielentität (Requirements, ArchitectureElement oder TestCase) existiert und dem aktuellen Tenant gehört.
2. Verifiziere, dass der Zielzustand in der aktuellen Workflow-Definition erlaubt ist.
3. Konsultiere die PresetPolicyService zur Validierung erforderlicher Rollen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Ungültige item_id wird mit strukturiertem Error zurückgewiesen
- [ ] Ungültiger target_state wird mit BenutzerNachricht zurückgewiesen
- [ ] PresetPolicyService wird vor Delegierung konsultiert
- [ ] Validierungsfehler blockieren Delegierung an WorkflowEngine

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-INT-007
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-AppSvc-012
**Rationale:** Frühe Validierung reduziert unnötige Aufrufe an die WorkflowEngine.

---

### REQ-L3-WF-002: Delegierung an WorkflowEngine

Der WorkflowFacade SHALL nach erfolgreicher Validierung die Transition an die WorkflowEngine delegieren mit vollständigem Auth-Kontext (User, Tenant, Rollen).

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Auth-Kontext wird unverändert weitergegeben
- [ ] WorkflowEngine erhält item_id, target_state und change_reason
- [ ] Fehler der WorkflowEngine werden strukturiert propagiert
- [ ] Timeout-Handling: max 5s Wartezeit auf WorkflowEngine-Antwort

**Interfaces:** IF-AS-INT-003
**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L2-AppSvc-012
**Rationale:** WorkflowEngine ist die Single Source of Truth für Transitions-Logik.

---

### REQ-L3-WF-003: AuditLog-Eintrag nach erfolgreichem Transition

Nach erfolgreicher Transition durch die WorkflowEngine SHALL der WorkflowFacade einen AuditLog-Eintrag generieren, der folgende Felder enthält:
- Entity-Typ und UUID
- Alter und neuer Workflow-State
- change_reason (falls vorhanden)
- Timestamp und Actor (User oder Agent-Client)

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] AuditLog-Event wird publikziert (via DomainEventBus)
- [ ] Eintrag reflektiert exakte alte/neue States
- [ ] change_reason wird korrekt erfasst
- [ ] AuditLog-Fehler blockieren nicht die Transition (fire-and-forget)

**Interfaces:** IF-AS-EXT-OUT-006
**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L2-AppSvc-019
**Rationale:** Vollständige Auditierbarkeit aller Transitions.

---

### REQ-L3-WF-004: Change-Reason-Validierung gegen Preset

Der WorkflowFacade SHALL vor Delegierung an WorkflowEngine verifizieren, ob change_reason gemäß aktiven Preset erforderlich ist. Falls erforderlich und nicht vorhanden, SHALL die Operation mit strukturiertem Error abgebrochen werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] PresetPolicyService wird konsultiert (`is_change_reason_required(workspace_id)`)
- [ ] Fehlende erforderliche change_reason wird sofort zurückgewiesen
- [ ] Leere oder null change_reason wird als fehlend behandelt
- [ ] Längenvalidierung: change_reason max 500 Zeichen

**Interfaces:** IF-AS-INT-007
**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L2-AppSvc-020
**Rationale:** Configurable-Rigor-Enforcement auf Transition-Ebene.

---

### REQ-L3-WF-005: Fehlerbehandlung und Rollback-Semantik

Sollte die WorkflowEngine einen Validierungsfehler zurückgeben (z.B. ungültige Transition, unzureichende Berechtigungen), SHALL der WorkflowFacade die Operation abbrechen und den Fehler strukturiert an den Aufrufer zurückgeben, ohne einen AuditLog-Eintrag zu schreiben.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] WorkflowEngine-Fehler werden unverändert propagiert
- [ ] Keine AuditLog-Einträge für fehlgeschlagene Transitions
- [ ] HTTP-Statuscode reflektiert Fehlertyp (400 für Validierung, 403 für Autorisierung)
- [ ] Fehler enthalten keine sensiblen Informationen

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-INT-003
**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L2-AppSvc-012
**Rationale:** Konsistenz zwischen persistenten Änderungen und Auditlog.

---

### REQ-L3-WF-006: Atomare Transaktionssemantik

Der WorkflowFacade SHALL garantieren, dass die Combination aus (WorkflowEngine-Aufruf + AuditLog-Eintrag) atomaren Charakter hat. Falls der AuditLog-Eintrag fehlschlägt (z.B. Datenbank-Timeout), SHALL die gesamte Transition rollback werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Verwendung von `transaction.atomic()` umhüllt beide Operationen
- [ ] Bei AuditLog-Fehler wird die Transition rückgängig gemacht
- [ ] Datenbank-State reflektiert entweder beide oder keine Änderung
- [ ] Keine orphaned Transitions ohne AuditLog

**Interfaces:** IF-AS-INT-003, IF-AS-EXT-OUT-006
**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L2-AppSvc-018
**Rationale:** Datenintegrität und Audit-Zuverlässigkeit.

---

### REQ-L3-WF-007: Caching und Performance

Der WorkflowFacade MAY Workflow-Definitionen und Preset-Regeln bis zu 5 Minuten im In-Memory-Cache halten, um Mehrfach-Konsultationen der PresetPolicyService zu reduzieren. Cache-Invalidierung erfolgt bei Preset-Änderungen.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] Präsenz von Cache reduziert PresetPolicyService-Aufrufe um ≥70%
- [ ] Cache-TTL ist auf 5 Minuten konfigurierbar
- [ ] Cache wird invalidiert bei Preset-Update-Events
- [ ] Orchestrierungs-Overhead bleibt unter 50ms

**Interfaces:** IF-AS-INT-007
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Traceability:** REQ-L2-AppSvc-023
**Rationale:** Performance-Optimierung für häufige Transitions.

---

## Traceability-Matrix: REQ-L3-WF → REQ-L2

| REQ-L3 | Primäre REQ-L2 |
|--------|----------------|
| REQ-L3-WF-001 | REQ-L2-AppSvc-012 |
| REQ-L3-WF-002 | REQ-L2-AppSvc-012 |
| REQ-L3-WF-003 | REQ-L2-AppSvc-019 |
| REQ-L3-WF-004 | REQ-L2-AppSvc-020 |
| REQ-L3-WF-005 | REQ-L2-AppSvc-012 |
| REQ-L3-WF-006 | REQ-L2-AppSvc-018 |
| REQ-L3-WF-007 | REQ-L2-AppSvc-023 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
