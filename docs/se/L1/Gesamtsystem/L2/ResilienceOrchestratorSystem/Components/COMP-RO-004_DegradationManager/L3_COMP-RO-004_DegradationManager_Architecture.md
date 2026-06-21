# L3 COMP-RO-004_DegradationManager Architecture

> **Level:** L3 (Terminal Component White-Box)
> **System:** COMP-RO-004_DegradationManager
> **Parent:** L2_ResilienceOrchestratorSystem_Architecture.md
> **Datum:** 2026-06-21
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Der DegradationManager erzeugt deterministische Fallback-Antworten (Graceful Degradation), wenn ein externes System dauerhaft nicht erreichbar ist (Retries ausgeschöpft) oder der CircuitBreaker blockiert. Er stellt sicher, dass das Frontend oder andere aufrufende Systeme kontrolliert über den Teilausfall informiert werden, ohne das gesamte ReqFlow-System zum Absturz zu bringen.

---

## 2. Internes White-Box Design (Klassen & Datenstrukturen)

### 2.1 Klassen und Module

- **`DegradationManager`**: Zentrale Klasse für Fallback-Logik.
  - **Funktion:** `handle_failure(exception: Exception, target: str) -> FallbackResponse`
  - **Ablauf:**
    1. Analysiert `exception` und `target`, um den Fallback-Strategietyp auszuwählen (z.B. "Mock-Data", "Partial-Success", "Disabled-Feature").
    2. Konstruiert eine `FallbackResponse` mit entsprechenden Metadaten.
    3. Ruft asynchron `ResilienceAuditLogger.log_degradation_event` auf (IF-RO-INT-006).
    4. Gibt die Fallback-Antwort an den Aufrufer (bzw. das Frontend-Data-Model) zurück.

- **`FallbackStrategyRegistry`**: 
  - Eine Mapping-Konfiguration (Strategy Pattern), die bestimmt, wie ein Ausfall eines spezifischen Systems beantwortet wird (z.B. LLM-Ausfall => Fallback auf Basis-Heuristiken; Webhook-Ausfall => Queue-for-later).

### 2.2 Datenstrukturen

- **`FallbackResponse`**:
  - `is_degraded: bool = True`
  - `fallback_data: dict` (z.B. leere Liste, Default-Werte, heuristische Ergebnisse)
  - `system_status_message: str` (z.B. "AI-Features temporär nicht verfügbar. Standard-Suche aktiv.")
  - `original_error_code: str`

---

## 3. Erfüllung der L3-Anforderungen

| Requirement ID | Erfüllung im Design |
|----------------|---------------------|
| **REQ-L3-RO-004-01** (Fallback-Generierung) | `handle_failure` liefert immer ein valides `FallbackResponse` Objekt zurück, welches vom Frontend oder Backend als Teilerfolg verarbeitet werden kann. |
| **REQ-L3-RO-004-02** (Logging von Degradation-Events) | Jeder Aufruf von `handle_failure` delegiert parallel ein Event an den AuditLogger via IF-RO-INT-006. |

---

## 4. Schnittstellen-Mapping

| Interface | Implementierung / Aufrufpunkt |
|-----------|-------------------------------|
| **IF-RO-INT-003** (Input) | Python-Aufruf von der `PolicyEngine` (nach finalem Fehlschlag). |
| **IF-RO-INT-006** (Output) | Python-Call an `ResilienceAuditLogger.log_degradation_event`. |

---
*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-21*
