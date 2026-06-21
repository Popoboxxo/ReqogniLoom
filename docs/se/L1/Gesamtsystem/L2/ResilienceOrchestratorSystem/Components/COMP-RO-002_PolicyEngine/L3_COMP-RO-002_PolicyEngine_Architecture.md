# L3 COMP-RO-002_PolicyEngine Architecture

> **Level:** L3 (Terminal Component White-Box)
> **System:** COMP-RO-002_PolicyEngine
> **Parent:** L2_ResilienceOrchestratorSystem_Architecture.md
> **Datum:** 2026-06-21
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Die PolicyEngine verarbeitet asynchrone Tasks aus dem AsyncDispatcher (IF-RO-INT-002). Sie kapselt ausgehende Aufrufe an Fremdsysteme (IF-L1-051) in eine robuste Ausführungs-Logik, welche Timeouts durchsetzt und Retries mit Exponential Backoff bei transienten Fehlern anwendet. Nach Abschluss (Erfolg oder Misserfolg) informiert sie CircuitBreaker und DegradationManager.

---

## 2. Internes White-Box Design (Klassen & Datenstrukturen)

### 2.1 Klassen und Module

- **`PolicyEngineService`**: Kapselt die Resilience-Pattern-Ausführung.
  - **Funktion:** `execute_with_policy(operation: str, target: str, payload: dict, policy: TargetPolicy)`
  - **Ablauf:** Nutzt eine Retry-Bibliothek (z.B. `tenacity` in Python) für das Decorating des tatsächlichen Netzwerkkontakts.
  
- **`ExecutionWrapper`**:
  - Implementiert die Retry-Schleife.
  - Wertet HTTP-Statuscodes aus, um transiente Fehler (z.B. 500, 502, 503, 504, Timeouts) von fatalen Fehlern (400, 401, 403, 404) zu unterscheiden.
  - Löst bei Erfolg: `CircuitBreaker.report_success(target)` aus (IF-RO-INT-004).
  - Löst bei finalem Fehler (Max-Retries erreicht oder fataler Fehler): 
    1. `CircuitBreaker.report_failure(target)` aus (IF-RO-INT-004).
    2. `DegradationManager.handle_failure(exception, target)` aus (IF-RO-INT-003).

### 2.2 Datenstrukturen

- **`TargetPolicy`**: 
  - `timeout_ms: int`
  - `max_retries: int`
  - `backoff_factor: float`
  - `retryable_exceptions: list[Type[Exception]]`

---

## 3. Erfüllung der L3-Anforderungen

| Requirement ID | Erfüllung im Design |
|----------------|---------------------|
| **REQ-L3-RO-002-01** (Timeouts durchsetzen) | Die Ausführung im `ExecutionWrapper` unterliegt einem strikten `timeout`-Parameter beim HTTP-Client (z.B. `requests.post(..., timeout=X)`). |
| **REQ-L3-RO-002-02** (Exponential Backoff Retries) | `tenacity.retry(wait=wait_exponential(...), stop=stop_after_attempt(...))` dekoriert den Call. Retries nur bei passenden HTTP-Statuscodes. |
| **REQ-L3-RO-002-03** (Erfolg/Misserfolg melden) | Callback-Hooks am Ende der Retry-Kette (oder bei Erfolg des ersten Versuchs) rufen `report_success` bzw. `report_failure` am CircuitBreaker auf. |
| **REQ-L3-RO-002-04** (Degradation auslösen) | In der Exception-Behandlung des letzten Fehlschlags wird `DegradationManager.handle_failure` aufgerufen. |

---

## 4. Schnittstellen-Mapping

| Interface | Implementierung / Aufrufpunkt |
|-----------|-------------------------------|
| **IF-RO-INT-002** (Input) | Celery-Worker rufen `PolicyEngineService.execute_with_policy()` auf. |
| **IF-L1-051** (Output) | HTTP-Clients (requests/httpx) führen den echten Call zu Fremdsystemen aus. |
| **IF-RO-INT-003** (Output) | Python-Call an `DegradationManager.handle_failure`. |
| **IF-RO-INT-004** (Output) | Python-Call an `CircuitBreaker.report_success/failure`. |

---
*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-21*
