# L3 COMP-RO-004_DegradationManager Requirements

> **Level:** L3 (Component-Anforderungen)
> **System:** COMP-RO-004_DegradationManager
> **Parent:** L2_ResilienceOrchestratorSystem_Requirements.md
> **Datum:** 2026-06-21
> **Status:** formalisiert
> **Designation:** component (terminal — keine L4-Zerlegung)
> **decomposition_status:** terminal

---

## Traceability

- Abgeleitet von: REQ-L2-RO-005
- Ziel: terminal (keine weitere Zerlegung)

---

## Systemzweck

Der DegradationManager (COMP-RO-004) ist dafür verantwortlich, bei Ausfällen von Zielsystemen (z. B. durch Timeouts, ausgeschöpfte Retries oder offene Circuit-Breaker) dedizierte Fallback-Antworten (Graceful Degradation) zu erzeugen. Dies stellt sicher, dass die Kernverfügbarkeit des ReqFlow-Systems erhalten bleibt und Aufrufer eine sinnvolle Fehlerbehandlung anstelle eines kompletten Absturzes erfahren.

---

## Externe Schnittstellen (Component Boundary)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-RO-INT-003 | input | control | In-Process Python von PolicyEngine: `handle_failure(exception, target) -> FallbackResponse` |
| IF-RO-INT-006 | output | data | Interner Log-Aufruf an ResilienceAuditLogger: Übermittlung des Degradation-Events |

*(Hinweis: IF-RO-INT-006 referenziert die "Log" Kante im L2 Architektur-Diagramm)*

---

## L3 Component-Anforderungen

### REQ-L3-RO-004-01: Fallback-Generierung

Der DegradationManager SHALL für fehlschlagende Aufrufe, die über IF-RO-INT-003 eingehen, eine deterministische Fallback-Antwort (`FallbackResponse`) generieren, die den Fehler isoliert.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Fallback-Antwort enthält Statusinformationen, dass das System temporär degradiert ist.
- [ ] Das Frontend kann anhand der Fallback-Antwort erkennen, dass ein optionales Subsystem inaktiv ist.
**Interfaces:** IF-RO-INT-003
**Traceability:** REQ-L2-RO-005

### REQ-L3-RO-004-02: Logging von Degradation-Events

Der DegradationManager SHALL jedes ausgelöste Degradation-Event über IF-RO-INT-006 an den ResilienceAuditLogger melden.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Jedes `handle_failure` Event erzeugt ein asynchrones oder nicht-blockierendes Log-Ereignis für das Audit.
**Interfaces:** IF-RO-INT-006
**Traceability:** REQ-L2-RO-005
