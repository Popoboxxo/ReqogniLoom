# L3 COMP-RO-002_PolicyEngine Requirements

> **Level:** L3 (Component-Anforderungen)
> **System:** COMP-RO-002_PolicyEngine
> **Parent:** L2_ResilienceOrchestratorSystem_Requirements.md
> **Datum:** 2026-06-21
> **Status:** formalisiert
> **Designation:** component (terminal — keine L4-Zerlegung)
> **decomposition_status:** terminal

---

## Traceability

- Abgeleitet von: REQ-L2-RO-002, REQ-L2-RO-003
- Ziel: terminal (keine weitere Zerlegung)

---

## Systemzweck

Die PolicyEngine (COMP-RO-002) ist verantwortlich für die Anwendung konfigurierbarer Timeout-Schwellen und Retry-Strategien mit Exponential Backoff auf transiente Fehler bei ausgehenden Aufrufen.

---

## Externe Schnittstellen (Component Boundary)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-RO-INT-002 | input | control | In-Process Python von AsyncDispatcher: `execute_with_policy(operation, target, payload)` |
| IF-L1-051 | output | control | Delegierter Aufruf an Externe Systeme (GitHub, Webhook) |
| IF-RO-INT-003 | output | data | In-Process Python an DegradationManager: `handle_failure(exception, target) -> FallbackResponse` |
| IF-RO-INT-004 | output | data | In-Process Python an CircuitBreaker: `report_success(target)` oder `report_failure(target)` |

---

## L3 Component-Anforderungen

### REQ-L3-RO-002-01: Timeouts durchsetzen

Die PolicyEngine SHALL bei allen über IF-RO-INT-002 eingehenden Aufrufen ein Timeout gemäß Zielsystem-Konfiguration durchsetzen (Weiterleitung via IF-L1-051).
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Überschreitet ein Request via IF-L1-051 das Timeout, wird der Aufruf abgebrochen.
- [ ] Timeout-Ausnahmen werden als Fehlschlag registriert.
**Interfaces:** IF-RO-INT-002, IF-L1-051
**Traceability:** REQ-L2-RO-002

### REQ-L3-RO-002-02: Exponential Backoff Retries

Die PolicyEngine SHALL Aufrufe, die aufgrund von transienten Fehlern (Netzwerkfehler, 5xx Status, Timeouts) fehlschlagen, mit exponentiell wachsender Wartezeit wiederholen.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Maximal konfigurierte Retry-Anzahl wird nicht überschritten.
- [ ] Bei non-retryable Errors (z. B. 400 Bad Request) findet kein Retry statt.
- [ ] Die Wartezeit vergrößert sich exponentiell zwischen den Versuchen.
**Interfaces:** IF-L1-051
**Traceability:** REQ-L2-RO-003

### REQ-L3-RO-002-03: Erfolg und Misserfolg melden

Die PolicyEngine SHALL den finalen Status (Erfolg oder Misserfolg nach Retries) an den CircuitBreaker über IF-RO-INT-004 melden.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Bei Erfolg wird `report_success(target)` aufgerufen.
- [ ] Bei finalem Misserfolg wird `report_failure(target)` aufgerufen.
**Interfaces:** IF-RO-INT-004
**Traceability:** REQ-L2-RO-002, REQ-L2-RO-003

### REQ-L3-RO-002-04: Degradation bei finalem Fehlschlag auslösen

Die PolicyEngine SHALL bei Ausschöpfung aller Retries oder bei fatalen Fehlern den DegradationManager über IF-RO-INT-003 aufrufen, um eine Graceful Degradation Response zu generieren.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `handle_failure(exception, target)` wird bei finalem Misserfolg aufgerufen.
- [ ] Rückgabe-Fallback wird verarbeitet.
**Interfaces:** IF-RO-INT-003
**Traceability:** REQ-L2-RO-002, REQ-L2-RO-003
