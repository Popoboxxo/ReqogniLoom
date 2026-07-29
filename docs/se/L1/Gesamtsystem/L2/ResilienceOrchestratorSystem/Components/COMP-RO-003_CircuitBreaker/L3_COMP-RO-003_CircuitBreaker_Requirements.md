decomposition_status: terminal

# L3 COMP-RO-003_CircuitBreaker Architecture

> **Level:** L3 (Terminal Component White-Box)
> **System:** COMP-RO-003_CircuitBreaker
> **Parent:** L2_ResilienceOrchestratorSystem_Architecture.md
> **Datum:** 2026-06-21
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Der CircuitBreaker ist ein in-Memory Zustandsautomat (teilweise backing via Redis zur Skalierung), der den Gesundheitszustand externer Abhängigkeiten zentral überwacht. Er sammelt Erfolgs- und Fehlermeldungen von der PolicyEngine und entscheidet auf Basis konfigurierter Schwellenwerte, ob das System Traffic weiterleitet (`Closed`), blockiert (`Open`) oder testweise durchlässt (`Half-Open`).

---

## 2. Internes White-Box Design (Klassen & Datenstrukturen)

### 2.1 Klassen und Module

- **`CircuitBreakerRegistry`**: Singleton-artiger Verwalter der Zustände für alle konfigurierten Target-Systeme.
- **`CircuitBreakerStateMachine`**:
  - Verwaltet den Lebenszyklus eines einzelnen `target`.
  - **Methoden:**
    - `can_execute() -> bool`: Prüft den aktuellen Zustand. Bei `OPEN` wird geprüft, ob `recovery_timeout` verstrichen ist. Wenn ja, Übergang nach `HALF_OPEN` und Rückgabe `True`. Ansonsten Rückgabe `False`.
    - `report_success()`: Setzt `failure_count` auf 0, State auf `CLOSED`. Meldet State-Change via IF-RO-INT-005.
    - `report_failure()`: Erhöht `failure_count`. Wenn `failure_count >= threshold`, State auf `OPEN`, Timestamp setzen. Meldet State-Change via IF-RO-INT-005.

### 2.2 Datenstrukturen

- **`CircuitState` (Enum)**: `CLOSED`, `OPEN`, `HALF_OPEN`.
- **`TargetState`**:
  - `target_id: str`
  - `state: CircuitState`
  - `failure_count: int`
  - `last_failure_timestamp: datetime | None`
- **`CircuitConfig`**:
  - `failure_threshold: int` (z.B. 5 Fehler in Folge)
  - `recovery_timeout_sec: int` (z.B. 60 Sekunden bis Half-Open)

---

## 3. Erfüllung der L3-Anforderungen

| Requirement ID | Erfüllung im Design |
|----------------|---------------------|
| **REQ-L3-RO-003-01** (Zustandsautomat) | Die Enum `CircuitState` und Klasse `CircuitBreakerStateMachine` bilden den Zustandsautomaten mit Initialzustand `CLOSED` exakt ab. |
| **REQ-L3-RO-003-02** (Open-Transition) | `report_failure()` inkrementiert den internen Counter. Bei Schwellenwert-Überschreitung erfolgt der sofortige Wechsel zu `OPEN` und Benachrichtigung des AuditLoggers. |
| **REQ-L3-RO-003-03** (Fast Fail) | `can_execute()` liefert `False` ohne Zeitverzögerung zurück, wenn der Status auf `OPEN` steht und der Timeout nicht abgelaufen ist. |
| **REQ-L3-RO-003-04** (Recovery Half-Open) | Zeitstempel-Prüfung in `can_execute()` implementiert das Recovery-Timeout und den Wechsel zu `HALF_OPEN`. |

---

## 4. Schnittstellen-Mapping

| Interface | Implementierung / Aufrufpunkt |
|-----------|-------------------------------|
| **IF-RO-INT-001** (Input) | `can_execute(target)` wird synchron vom `AsyncDispatcher` gerufen. |
| **IF-RO-INT-004** (Input) | `report_success(target)` und `report_failure(target)` werden synchron von der `PolicyEngine` gerufen. |
| **IF-RO-INT-005** (Output) | Python-Call an `ResilienceAuditLogger.log_state_change()` bei jeder Zustandsänderung. |

---
*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-21*
