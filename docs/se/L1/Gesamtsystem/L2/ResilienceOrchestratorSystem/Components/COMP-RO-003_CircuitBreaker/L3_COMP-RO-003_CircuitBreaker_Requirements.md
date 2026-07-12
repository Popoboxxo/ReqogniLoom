# L3 COMP-RO-003_CircuitBreaker Requirements

> **Level:** L3 (Component-Anforderungen)
> **System:** COMP-RO-003_CircuitBreaker
> **Parent:** L2_ResilienceOrchestratorSystem_Requirements.md
> **Datum:** 2026-06-21
> **Status:** formalisiert
> **Designation:** component (terminal — keine L4-Zerlegung)
> **decomposition_status:** terminal

---

## Traceability

- Abgeleitet von: REQ-L2-RO-004
- Ziel: terminal (keine weitere Zerlegung)

---

## Systemzweck

Der CircuitBreaker (COMP-RO-003) überwacht kontinuierlich Fehlerraten pro Zielsystem. Er implementiert einen Zustandsautomaten (Closed, Open, Half-Open), der als Schutzmechanismus agiert, um den Datenverkehr bei Überlastung oder Ausfall eines Zielsystems präventiv zu blockieren (Fast-Fail) und dem Zielsystem Zeit zur Erholung zu geben.

---

## Externe Schnittstellen (Component Boundary)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-RO-INT-001 | input | control | In-Process Python von AsyncDispatcher: `can_execute(target_id) -> bool` |
| IF-RO-INT-004 | input | control | In-Process Python von PolicyEngine: `report_success(target)` oder `report_failure(target)` |
| IF-RO-INT-005 | output | data | In-Process Python an ResilienceAuditLogger: `log_state_change(target, old_state, new_state)` |

---

## L3 Component-Anforderungen

### REQ-L3-RO-003-01: Zustandsautomat

Der CircuitBreaker SHALL den Status jedes konfigurierten Zielsystems (Target) als Zustandsautomat mit den Zuständen `Closed`, `Open` und `Half-Open` verwalten.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Initialer Zustand für neue Targets ist `Closed`.
**Interfaces:** -
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-RO-004

### REQ-L3-RO-003-02: Fehler-Akkumulation und Open-Transition

Der CircuitBreaker SHALL in den Zustand `Open` wechseln, wenn über IF-RO-INT-004 die Anzahl oder Rate der Fehler (`report_failure`) einen konfigurierbaren Schwellenwert in einem bestimmten Zeitfenster überschreitet.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Nach Erreichen der Fehlerschwelle wird der Status sofort auf `Open` gesetzt.
- [ ] Ein Statuswechsel löst einen Aufruf von IF-RO-INT-005 aus.
**Interfaces:** IF-RO-INT-004, IF-RO-INT-005
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-RO-004

### REQ-L3-RO-003-03: Fast Fail bei Open-Zustand

Der CircuitBreaker SHALL bei Anfragen über IF-RO-INT-001 (`can_execute`) `false` zurückliefern, falls der Zustand des Targets `Open` ist.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Solange `Open`, wird kein Traffic zugelassen.
**Interfaces:** IF-RO-INT-001
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-RO-004

### REQ-L3-RO-003-04: Recovery via Half-Open

Der CircuitBreaker SHALL nach Ablauf eines Recovery-Timeouts vom `Open`- in den `Half-Open`-Zustand wechseln. Im `Half-Open`-Zustand erlaubt `can_execute` einen einzelnen Probe-Request (oder eine kleine Menge), dessen Erfolg oder Misserfolg den Status auf `Closed` oder wieder auf `Open` setzt.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Nach Timeout ist `can_execute` einmalig `true`.
- [ ] Bei `report_success` geht der Status auf `Closed`.
- [ ] Bei `report_failure` geht der Status zurück auf `Open`.
- [ ] Statuswechsel lösen Aufrufe an IF-RO-INT-005 aus.
**Interfaces:** IF-RO-INT-001, IF-RO-INT-004, IF-RO-INT-005
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-RO-004


## Master Traceability Matrix

| REQ-L3 | Abgeleitet von REQ-L2 |
|---------|----------------------|
| REQ-L3-RO-003-01 | REQ-L2-RO-004 |
| REQ-L3-RO-003-02 | REQ-L2-RO-004 |
| REQ-L3-RO-003-03 | REQ-L2-RO-004 |
| REQ-L3-RO-003-04 | REQ-L2-RO-004 |

