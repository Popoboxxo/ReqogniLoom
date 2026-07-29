decomposition_status: terminal

# L3 StateMachineEnforcer Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-RA-006 — StateMachineEnforcer
> **Parent-System:** RestApiAdapterSystem (L2)
> **Status:** formalisiert
> **Datum:** 2026-07-03

---

## Verantwortlichkeit

Die Komponente überwacht als Middleware oder DRF-ViewSet-Mixin alle `PATCH`-Requests auf die `Artifact`-Endpunkte. Sie prüft, ob das Feld `workflow_state` manipuliert wird und validiert, ob der Übergang gemäß der definierten State-Machine erlaubt ist und ob die Stage-Gating-Regeln (Guardrails) auf dem Traceability-Graphen erfüllt sind.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-RA-020 | API State Machine & Guardrails Enforcer |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-RA-INT-010 | eingehend | COMP-RA-001 (HttpEndpointController) | `ValidateTransition {artifact_id, old_state, new_state, user} -> Allowed \| Blocked(Reason)` |

---

## L3 Komponenten-Anforderungen

### REQ-L3-RA006-001: State Transition Matrix Validation

Der StateMachineEnforcer MUSS prüfen, ob der angefragte Statuswechsel im vordefinierten Graphen erlaubt ist (z.B. `Draft -> In Review` ist erlaubt, `Draft -> Verified` ist verboten).

**Implementation State:** Not Implemented
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Ungültige Wechsel werden mit HTTP `400 Bad Request` und der Meldung `"Invalid state transition"` abgelehnt.
- [ ] Neue Artefakte können nur im Status `Draft` (POST) erzeugt werden.

---

### REQ-L3-RA006-002: Stage-Gating Guardrails (Orphan & Allocation)

Der Enforcer MUSS vor der Freigabe eines Statuswechsels den Traceability-Graphen abfragen, um SE-Regeln zu garantieren.
- **Top-Down:** `SyReq` darf nicht `Approved` werden, wenn `StReq` nicht `Approved` ist.
- **No-Orphan:** `SyReq` darf nicht `In Review` gehen ohne Upstream-Trace.
- **Allocation:** `ArchE` darf nicht `Approved` werden, wenn allokierte `SyReqs` nicht `Approved` sind.

**Implementation State:** Not Implemented
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Verstoß gegen eine Regel blockiert den Request mit HTTP `409 Conflict`.
- [ ] Der Response Body enthält ein Array `guardrail_errors` mit Klartext-Erklärungen für die UI (z.B. `"Fehler: Anforderung hängt in der Luft"`).

---

### REQ-L3-RA006-003: Baseline Lock Enforcement

Bei `POST /baselines` MUSS die Komponente sicherstellen, dass alle Artefakte im Scope den Status `Approved` haben und keine `Suspect`-Links vorliegen.

**Implementation State:** Not Implemented
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Request wird mit HTTP `409 Conflict` blockiert, wenn unfertige Dokumente (`Draft`/`In Review`) im Scope liegen.

---

### REQ-L3-RA006-004: L3 Context Generators Implementation

Derives from REQ-L2-RES-015 (which derives from REQ-L1-285).
Component implements specific logic for prompt enrichment and context generation.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Context Generators are wired properly.

---

### REQ-L3-RA006-005: L3 Agent Templates & Review Endpoints

Derives from REQ-L2-RES-016 (which derives from REQ-L1-286).
Component supports Write Modes, Agent Templates, or frontend integrations for Superpowers.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Review Endpoints / Agent Templates supported.
