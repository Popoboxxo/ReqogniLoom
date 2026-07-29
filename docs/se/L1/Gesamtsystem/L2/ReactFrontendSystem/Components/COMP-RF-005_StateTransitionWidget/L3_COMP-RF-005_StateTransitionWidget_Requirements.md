decomposition_status: terminal

# L3 StateTransitionWidget Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-RF-005 — StateTransitionWidget
> **Parent-System:** ReactFrontendSystem (L2)
> **Status:** formalisiert
> **Datum:** 2026-07-03

---

## Verantwortlichkeit

Ein isoliertes React-Widget, das auf den Editor-Views (Requirement, Architecture, TestCase) platziert wird. Es rendert den aktuellen WorkflowState, bietet ein Dropdown für State-Transitions an, feuert den `PATCH` Request und visualisiert serverseitige Stage-Gating-Fehler (HTTP 409).

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-RF-026 | UI-Feedback für Guardrail-Fehler (Stage-Gating) |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-RF-INT-010 | eingehend | COMP-RF-003, COMP-RF-004 | `RenderWidget(artifactId, currentState)` |

---

## L3 Komponenten-Anforderungen

### REQ-L3-RF005-001: Rendering und Transition-Dropdown

Das StateTransitionWidget MUSS den aktuellen Status visuell anzeigen und ein Dropdown-Menü für die laut Client-State-Machine zulässigen Übergänge rendern.

**Implementation State:** Not Implemented
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Klick auf einen neuen Status im Dropdown triggert einen PATCH Request an `/api/v1/artifacts/{id}`.
- [ ] Während des Requests zeigt das Widget einen Loading-Spinner.

---

### REQ-L3-RF005-002: Error-Handling (Stage-Gating 409)

Wenn der PATCH-Request mit HTTP `409 Conflict` fehlschlägt, MUSS das Widget den Fehler abfangen und den im Body enthaltenen String (z.B. `"transition_denied: Missing upstream trace"`) lokal auswerten.

**Implementation State:** Not Implemented
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Bei einem 409-Fehler springt der Status sofort visuell auf den Ursprungswert zurück.
- [ ] Eine rote Fehlermeldung (Alert Box oder Tooltip) wird direkt unterhalb des Widgets angezeigt.
- [ ] Die Fehlermeldung bleibt sichtbar, bis der Nutzer sie wegklickt oder einen neuen Versuch startet.
- [ ] Andere HTTP-Fehler (z.B. 500) werden an das globale Error-Handling delegiert.

---

### REQ-L3-RF005-003: L3 Context Generators Implementation

Derives from REQ-L2-REA-015 (which derives from REQ-L1-285).
Component implements specific logic for prompt enrichment and context generation.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Context Generators are wired properly.

---

### REQ-L3-RF005-004: L3 Agent Templates & Review Endpoints

Derives from REQ-L2-REA-016 (which derives from REQ-L1-286).
Component supports Write Modes, Agent Templates, or frontend integrations for Superpowers.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Review Endpoints / Agent Templates supported.
