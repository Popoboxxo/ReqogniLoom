decomposition_status: terminal

# L3 COMP-RO-001_AsyncDispatcher Architecture

> **Level:** L3 (Terminal Component White-Box)
> **System:** COMP-RO-001_AsyncDispatcher
> **Parent:** L2_ResilienceOrchestratorSystem_Architecture.md
> **Datum:** 2026-06-21
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Der AsyncDispatcher empfängt Aufrufe aus dem `ApplicationService` und `LlmAdapter` (IF-L1-049, IF-L1-050). Er prüft zunächst über den CircuitBreaker, ob das Zielsystem erreichbar ist. Ist dies der Fall, reiht er die Ausführung in eine asynchrone Task-Queue (Celery) ein, um eine Blockade der synchronen Aufrufer zu verhindern, und gibt dem Aufrufer sofort eine Antwort zurück.

---

## 2. Internes White-Box Design (Klassen & Datenstrukturen)

Da diese Komponente terminal ist, beschreibt das Design die direkte softwareseitige Implementierung (Klassen, Funktionen und Kontrollfluss).

### 2.1 Klassen und Module

- **`AsyncDispatcherService`**: Zentrale Einstiegsklasse.
  - **Funktion:** `dispatch(operation: str, target: str, payload: dict, policy: dict) -> DispatchResult`
  - **Ablauf:**
    1. Ruft `CircuitBreaker.can_execute(target)` auf (IF-RO-INT-001).
    2. Wenn `False`: Rückgabe eines `DispatchResult(status="fast_fail")`.
    3. Wenn `True`: Aufruf von `celery_execute_task.delay(...)`.
    4. Rückgabe von `DispatchResult(status="enqueued", job_id=...)`.

- **`celery_execute_task`**: Asynchroner Celery-Worker-Task.
  - **Funktion:** `execute_task(operation: str, target: str, payload: dict, policy: dict)`
  - **Ablauf:** Entnimmt den Task aus der Message Broker Queue und ruft `PolicyEngine.execute_with_policy(...)` synchron innerhalb des Worker-Prozesses auf (IF-RO-INT-002).

### 2.2 Datenstrukturen

- **`DispatchResult`**:
  - `status: str` ("enqueued", "fast_fail")
  - `job_id: str | None` (UUID des Celery Tasks)
  - `message: str`

---

## 3. Erfüllung der L3-Anforderungen

| Requirement ID | Erfüllung im Design |
|----------------|---------------------|
| **REQ-L3-RO-001-01** (Asynchrone Entgegennahme) | `AsyncDispatcherService.dispatch` lagert die echte Ausführung an `celery_execute_task.delay` (Celery) aus. Die Rückgabe erfolgt in < 50ms, da nur ein Message-Broker-Enqueue stattfindet. |
| **REQ-L3-RO-001-02** (Vorab-Prüfung) | Vor dem Enqueueing wird synchron `CircuitBreaker.can_execute(target)` gerufen. Bei `False` wird sofort abgebrochen. |
| **REQ-L3-RO-001-03** (Task-Delegation) | Der Celery-Worker `execute_task` ruft nach der Deserialisierung direkt `PolicyEngine.execute_with_policy` auf. |

---

## 4. Schnittstellen-Mapping

| Interface | Implementierung / Aufrufpunkt |
|-----------|-------------------------------|
| **IF-L1-049** / **IF-L1-050** (Input) | REST/GraphQL Controller rufen `AsyncDispatcherService.dispatch()` auf. |
| **IF-RO-INT-001** (Output) | Synchrone Python-Funktionsaufrufe an `CircuitBreaker.can_execute`. |
| **IF-RO-INT-002** (Output) | Synchrone Python-Aufrufe aus dem Celery-Worker an `PolicyEngine`. |

---
*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-21*


## Derived L3 Requirements for Unmapped L2

### REQ-L3-RO001-U000: Auto-derived from REQ-L2-RES-014
Abgeleitet von: REQ-L2-RES-014

### REQ-L3-RO001-U001: Auto-derived from REQ-L2-RES-011
Abgeleitet von: REQ-L2-RES-011

### REQ-L3-RO001-U002: Auto-derived from REQ-L2-RES-001
Abgeleitet von: REQ-L2-RES-001

### REQ-L3-RO001-U003: Auto-derived from REQ-L2-RES-015
Abgeleitet von: REQ-L2-RES-015

### REQ-L3-RO001-U004: Auto-derived from REQ-L2-RES-003
Abgeleitet von: REQ-L2-RES-003

### REQ-L3-RO001-U005: Auto-derived from REQ-L2-RES-010
Abgeleitet von: REQ-L2-RES-010

### REQ-L3-RO001-U006: Auto-derived from REQ-L2-RES-002
Abgeleitet von: REQ-L2-RES-002

### REQ-L3-RO001-U007: Auto-derived from REQ-L2-RES-013
Abgeleitet von: REQ-L2-RES-013

### REQ-L3-RO001-U008: Auto-derived from REQ-L2-RES-004
Abgeleitet von: REQ-L2-RES-004

### REQ-L3-RO001-U009: Auto-derived from REQ-L2-RES-009
Abgeleitet von: REQ-L2-RES-009

### REQ-L3-RO001-U010: Auto-derived from REQ-L2-RES-016
Abgeleitet von: REQ-L2-RES-016

### REQ-L3-RO001-U011: Auto-derived from REQ-L2-RES-008
Abgeleitet von: REQ-L2-RES-008

### REQ-L3-RO001-U012: Auto-derived from REQ-L2-RES-006
Abgeleitet von: REQ-L2-RES-006

### REQ-L3-RO001-U013: Auto-derived from REQ-L2-RES-012
Abgeleitet von: REQ-L2-RES-012

### REQ-L3-RO001-U014: Auto-derived from REQ-L2-RES-005
Abgeleitet von: REQ-L2-RES-005

### REQ-L3-RO001-U015: Auto-derived from REQ-L2-RES-007
Abgeleitet von: REQ-L2-RES-007
