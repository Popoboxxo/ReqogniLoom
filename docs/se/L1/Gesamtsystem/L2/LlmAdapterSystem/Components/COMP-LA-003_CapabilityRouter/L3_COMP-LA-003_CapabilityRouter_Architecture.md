---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T12:00:00Z"
schema_version: "1.0.0"
---
# L3 CapabilityRouter Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-LA-003_CapabilityRouter
> **Parent:** L2_LlmAdapterSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der CapabilityRouter ist der zentralale Einstiegspunkt für alle LLM-Capability-Anfragen vom ApplicationService. Er entscheidet synchron vs. asynchron (validate_artifact → sync; decompose_requirement, check_consistency → async via Celery), implementiert Graceful Degradation bei fehlender LLM-Konfiguration oder deaktivierten Capabilities, und fängt alle Provider-Fehler (Timeout, HTTP-Fehler, Rate-Limit) ab. Er delegiert synchrone Aufrufe an den Provider (via ProviderRegistry) und asynchrone Aufrufe an den AsyncTaskDispatcher.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`CapabilityRouter` (Klasse):** Hauptorchestrierungskörper, implementiert execute_capability(capability_name, **kwargs).
- **`CapabilityConfig` (Dataclass):** Speichert aktivierte Capabilities aus Env-Var `LLM_CAPABILITIES`.
- **`ErrorResponse` (Dataclass):** Strukturiertes Fehlerformat mit code, message, details.
- **`SyncCapabilityHandler` (Helper):** Delegiert sync-Aufrufe an Provider.
- **`AsyncCapabilityHandler` (Helper):** Delegiert async-Aufrufe an AsyncTaskDispatcher.

### 2.2 Datenstrukturen

- **CapabilityConfig:**
  - `enabled_capabilities`: set[str] — set von aktivierten Capabilities (z.B. {"validate_artifact", "decompose_requirement"})
  - `is_configured`: bool — True wenn `LLM_PROVIDER` gesetzt ist

- **ErrorResponse:**
  - `error`: dict
    - `code`: str (z.B. "LLM_NOT_CONFIGURED", "LLM_PROVIDER_ERROR")
    - `message`: str (human-readable)
    - `details`: dict | None (optional, technische Details)

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-LA003-001 (Sync/Async Routing) | `execute_capability("validate_artifact", ...)`: Aufruf an Provider (synchron), Ergebnis direkt zurück. `execute_capability("decompose_requirement", ...)`: Dispatch zu AsyncTaskDispatcher, sofort task_id zurück (< 200ms). `execute_capability("check_consistency", ...)`: Async via AsyncTaskDispatcher. |
| REQ-L3-LA003-002 (Graceful Degradation) | Wenn `LLM_PROVIDER` nicht gesetzt oder Capability nicht in `LLM_CAPABILITIES`: return `{"error": {"code": "LLM_NOT_CONFIGURED"}}` strukturiert, keine Exception. Fail-safe. |
| REQ-L3-LA003-003 (Fehlerbehandlung) | Alle Exceptions aus ProviderRegistry/Provider werden abgefangen. Kategorien: Timeout → "Request timed out", HTTP 4xx/5xx → "API error: X", HTTP 429 → "Rate limit exceeded", andere → "<exception text>". Struktur: `{"error": {"code": "LLM_PROVIDER_ERROR", "message": "..."}}`. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-LA-EXT-IN-001:** Aufruf vom ApplicationService: `execute_capability(capability_name, **kwargs) -> LlmResult | {"task_id": "..."} | {"error": {...}}`.

- **Ausgänge (Outbound):**
  - **IF-LA-INT-001:** Aufruf an CapabilityInterface (via ProviderRegistry): `validate_artifact`, `decompose_requirement`, `check_consistency`.
  - **IF-LA-INT-002:** Aufruf an ProviderRegistry: `get_provider() -> LlmCapabilityInterface`.
  - **IF-LA-INT-004:** Aufruf an LlmAuditLogger: `log_llm_call(provider, capability, artifact_id, token_usage, success, error)`.
  - **IF-LA-INT-005:** Aufruf an AsyncTaskDispatcher: `dispatch_async(capability, kwargs) -> task_id`.

---

## 5. Architectural Rationale

**ADR-L3-LA003-01 — Sync/Async Split-Decision basierend auf Capability**
*Entscheidung:* validate_artifact → sync, decompose_requirement/check_consistency → async (Celery).
*Rationale:* validate_artifact ist schnell (< 1s) und blockiert akzeptabel. decompose/consistency sind langläufig (> 10s) und sollten nicht WSGI-Worker blockieren. Erfüllt REQ-L3-LA003-001.
*Alternative abgelehnt:* Alle async — würde validate_artifact unnötig komplizieren; alle sync — würde Worker-Hang für langläufige Tasks verursachen.

**ADR-L3-LA003-02 — Strukturiertes Error-Object statt Exception-Propagation**
*Entscheidung:* Provider-Fehler werden in strukturierte Error-Response verwandelt, niemals als Raw-Exception propagiert.
*Rationale:* Graceful Degradation, kein API-Consumer muss Exception-Handling implementieren. Erfüllt REQ-L3-LA003-002 und REQ-L3-LA003-003.
*Alternative abgelehnt:* Raw-Exception-Propagation — würde zu unbehandelbaren Fehlern im Caller führen.

**ADR-L3-LA003-03 — Capability-Aktivierung via Komma-separierte Env-Var**
*Entscheidung:* `LLM_CAPABILITIES=validate_artifact,decompose_requirement` — komma-separierte Liste zur Aktivierung.
*Rationale:* Einfach, deployment-freundlich. Fail-safe default: leere Liste = alle deaktiviert. Erfüllt REQ-L3-LA003-002.
*Alternative abgelehnt:* Einzelne Env-Vars für jede Capability — zu verbose.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
