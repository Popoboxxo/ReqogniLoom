---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T12:00:00Z"
schema_version: "1.0.0"
---
# L3 LlmAuditLogger Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-LA-004_LlmAuditLogger
> **Parent:** L2_LlmAdapterSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der LlmAuditLogger dokumentiert jeden LLM-Aufruf — erfolgreich oder fehlgeschlagen — im zentralen AuditLog. Er extrahiert Token-Verbrauch aus Provider-Responses (provider-unabhängig via duck-typing), speichert strukturierte Audit-Einträge und sorgt für vollständige Auditierbarkeit des LLM-Nutzungsverhaltens. Er implementiert fehlertolerantes Logging: Fehler beim AuditLog-Schreiben beeinflussen nicht das eigentliche LLM-Ergebnis.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`LlmAuditLogger` (Klasse):** Zentrale Logging-API.
- **`AuditEntry` (Dataclass):** Repräsentiert einen Audit-Log-Eintrag mit standardisiertem Schema.
- **`TokenExtractor` (Helper-Klasse):** Extrahiert Token-Counts provider-unabhängig (duck-typing).
- **`AuditLogWriter` (Abstraktions-Interface):** Abstrahiert den Schreibzugriff auf den zentralen AuditLog (kann ORM, REST oder direkter DB-Zugriff sein).

### 2.2 Datenstrukturen

- **AuditEntry:**
  - `source`: str (fixed: "llm_adapter")
  - `provider`: str (z.B. "anthropic", "openai")
  - `capability`: str (z.B. "validate_artifact", "decompose_requirement")
  - `artifact_id`: str | None (ID des betroffenen Artifacts, falls vorhanden)
  - `token_usage`: int | None (Gesamttoken oder None)
  - `success`: bool (True bei Erfolg, False bei Fehler)
  - `error`: str | None (Fehlerbeschreibung, falls Fehler)
  - `timestamp`: datetime (UTC, auto-generiert)

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-LA004-001 (Vollständige Protokollierung) | Methode `log_llm_call(provider, capability, artifact_id, token_usage, success, error)`: Erstellt AuditEntry mit allen Feldern. Schreibt zu AuditLogWriter. Erfolg oder Fehler — beide protokolliert. LLM_NOT_CONFIGURED-Fall: erfolgsloser Aufruf mit error="LLM_NOT_CONFIGURED". |
| REQ-L3-LA004-002 (Token-Extraktion) | Helfer-Funktion `_extract_token_count(response)`: Duck-typing für Provider-Responses. Anthropic: `response.usage.input_tokens + response.usage.output_tokens`. OpenAI: `response.usage.total_tokens`. Wenn kein Usage-Objekt: `token_usage = None`. |
| REQ-L3-LA004-003 (Fehlertolerantes Logging) | Try-catch um AuditLogWriter-Aufruf. Bei Fehler: Python warning emittieren, aber nicht re-raise. LLM-Ergebnis wird Caller trotzdem zurückgegeben. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-LA-INT-004:** Aufruf vom CapabilityRouter: `log_llm_call(provider, capability, artifact_id, token_usage, success, error)`.

- **Ausgänge (Outbound):**
  - **IF-LA-EXT-OUT-002:** Schreib-Zugriff auf AuditLog via AuditLogWriter (In-Process Python, z.B. Django ORM).

---

## 5. Architectural Rationale

**ADR-L3-LA004-01 — Duck-Typing für Token-Extraktion**
*Entscheidung:* Token-Extraktion nutzt duck-typing (dict/attribute access), nicht provider-spezifische SDK-Imports.
*Rationale:* Entkopplung von Provider-SDKs, Provider-neutral. Erfüllt REQ-L3-LA004-002 ohne Provider-Abhängigkeit.
*Alternative abgelehnt:* Provider-spezifische if-else-Blöcke — würde neue Provider zu Code-Changes führen.

**ADR-L3-LA004-02 — Fehlertolerantes Logging mit Warning-Fallback**
*Entscheidung:* AuditLog-Schreib-Fehler werden intern gehandhabt (Python-warning), nicht re-raised.
*Rationale:* Logging-Fehler dürfen nicht das LLM-System lahmlegen. Erfüllt REQ-L3-LA004-003.
*Alternative abgelehnt:* Exception-Propagation — würde LLM-Ergebnisse blockieren.

**ADR-L3-LA004-03 — Standardisierte Token-Summe (Provider-agnostisch)**
*Entscheidung:* Unabhängig vom Provider wird ein `token_usage` als einzelne Ganzzahl gespeichert (Summe von Input+Output, wenn verfügbar).
*Rationale:* Einheitliche Audits, leichte Aggregation. Ermöglicht Kostenberechnung/Tracking.
*Alternative abgelehnt:* Separate input/output-Token-Speicherung — würde Audit-Schema komplizieren.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
