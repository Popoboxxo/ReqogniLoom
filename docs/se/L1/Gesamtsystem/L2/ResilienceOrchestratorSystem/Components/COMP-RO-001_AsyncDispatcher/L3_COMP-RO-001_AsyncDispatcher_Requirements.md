# L3 COMP-RO-001_AsyncDispatcher Requirements

> **Level:** L3 (Component-Anforderungen)
> **System:** COMP-RO-001_AsyncDispatcher
> **Parent:** L2_ResilienceOrchestratorSystem_Requirements.md
> **Datum:** 2026-06-21
> **Status:** formalisiert
> **Designation:** component (terminal — keine L4-Zerlegung)
> **decomposition_status:** terminal

---

## Traceability

- Abgeleitet von: REQ-L2-RO-001
- Ziel: terminal (keine weitere Zerlegung)

---

## Systemzweck

Der AsyncDispatcher (COMP-RO-001) ist verantwortlich für die Entgegennahme externer Aufrufe aus dem ApplicationService und dem LlmAdapter. Er stellt sicher, dass diese Aufrufe asynchron über eine Message-Queue (z.B. Celery) verarbeitet werden, um die synchronen Request-Threads der Aufrufer nicht zu blockieren.

---

## Externe Schnittstellen (Component Boundary)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-L1-049 | input | control | `execute_optional(operation, target, payload, policy)` vom ApplicationService |
| IF-L1-050 | input | control | Wrapping aller HTTPS-Outbound-Calls vom LlmAdapter |
| IF-RO-INT-001 | output | control | In-Process Python Call an CircuitBreaker (COMP-RO-003): `can_execute(target_id) -> bool` |
| IF-RO-INT-002 | output | control | In-Process Python Call an PolicyEngine (COMP-RO-002): `execute_with_policy(operation, target, payload)` |

---

## L3 Component-Anforderungen

### REQ-L3-RO-001-01: Asynchrone Entgegennahme

Der AsyncDispatcher SHALL Aufrufe über IF-L1-049 und IF-L1-050 in eine asynchrone Task-Queue einreihen und dem Aufrufer sofort antworten.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Aufrufer blockiert nicht auf die Abarbeitung des externen Aufrufs.
- [ ] Rückgabe an Aufrufer erfolgt in < 50ms (Enqueue-Zeit).
**Interfaces:** IF-L1-049, IF-L1-050
**Traceability:** REQ-L2-RO-001

### REQ-L3-RO-001-02: Vorab-Prüfung der Ausführbarkeit

Der AsyncDispatcher SHALL vor dem Einreihen in die Queue den CircuitBreaker über IF-RO-INT-001 abfragen, ob das Zielsystem verfügbar ist.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Bei `can_execute == false` wird der Aufruf direkt abgelehnt (Fast Fail).
- [ ] Bei `can_execute == true` wird der Task eingereiht.
**Interfaces:** IF-RO-INT-001
**Traceability:** REQ-L2-RO-001

### REQ-L3-RO-001-03: Task-Delegation

Die asynchronen Worker des AsyncDispatchers SHALL die asynchron eingereihten Tasks über IF-RO-INT-002 an die PolicyEngine übergeben.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Worker-Prozesse rufen `execute_with_policy` mit den in der Queue persistierten Parametern auf.
**Interfaces:** IF-RO-INT-002
**Traceability:** REQ-L2-RO-001
