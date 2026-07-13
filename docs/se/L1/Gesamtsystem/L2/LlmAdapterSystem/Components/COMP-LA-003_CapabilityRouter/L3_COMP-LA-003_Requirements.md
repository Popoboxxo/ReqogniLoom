# L3 CapabilityRouter Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-LA-003 — CapabilityRouter
> **Parent-System:** LlmAdapterSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Zentraler Einstiegspunkt fuer alle LLM-Aufrufe aus dem ApplicationService. Verantwortlich fuer: Capability-Aktivierung/Deaktivierung per Konfiguration; Graceful Degradation bei fehlender Konfiguration oder Provider-Fehlern; Routing-Entscheidung synchron vs. asynchron (`validate_artifact` → synchron; `decompose_requirement`, `check_consistency` → Celery-Task-Dispatch mit sofortiger task_id-Rueckgabe).

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-LA-002 | Graceful Degradation bei fehlender LLM-Konfiguration |
| REQ-L2-LA-003 | Selektive Capability-Aktivierung |
| REQ-L2-LA-005 | Provider-Fehlerbehandlung und Timeout |
| REQ-L2-LA-008 | Asynchrone LLM-Task-Ausführung via Celery |
| REQ-L2-LA-009 | LlmSettings — Mandanten-konfigurierbarer LLM-Provider |
| REQ-L2-LA-010 | PromptTemplate — Admin-editierbare Prompt-Slots |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-LA-INT-001 | ausgehend | COMP-LA-001 (CapabilityInterface) | `execute_capability(capability_name, **kwargs)` |
| IF-LA-INT-002 | ausgehend | COMP-LA-002 (ProviderRegistry) | `get_provider() -> LlmCapabilityInterface` |
| IF-LA-INT-004 | eingehend | COMP-LA-004 (LlmAuditLogger) | `log_llm_call(provider, capability, artifact_id, token_usage, success, error)` |
| IF-LA-INT-005 | ausgehend | COMP-LA-005 (AsyncTaskDispatcher) | `dispatch_async(capability, kwargs) -> task_id` |

## Externe Schnittstellen (falls Komponente an Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-LA-EXT-IN-001 | eingehend | ApplicationService | `execute_capability(capability_name, **kwargs) -> LlmResult` |

---

## L3 Komponenten-Anforderungen

### REQ-L3-LA003-001: Sync/Async Routing-Entscheidung


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Der CapabilityRouter SHALL `validate_artifact`-Aufrufe synchron an den Provider weiterleiten und das Ergebnis direkt zurueckgeben. `decompose_requirement`- und `check_consistency`-Aufrufe SHALL der Router an den AsyncTaskDispatcher (IF-LA-INT-005) delegieren und sofort `{task_id: "<uuid>"}` an den Aufrufer zurueckgeben, ohne den WSGI/ASGI-Worker zu blockieren.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `execute_capability("validate_artifact", artifact_id="x")` returns `LlmResult` synchronously
- [ ] `execute_capability("decompose_requirement", requirement_id="y")` returns `{"task_id": "<uuid>"}` immediately (< 200ms)
- [ ] `execute_capability("check_consistency", workspace_id="z")` returns `{"task_id": "<uuid>"}` immediately (< 200ms)
- [ ] WSGI worker thread is not blocked during async capability dispatch

---

### REQ-L3-LA003-002: Graceful Degradation und selektive Capability-Aktivierung


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Der CapabilityRouter SHALL bei fehlender LLM-Konfiguration (`LLM_NOT_CONFIGURED`) oder deaktivierter Capability den strukturierten Fehler `{error: {code: "LLM_NOT_CONFIGURED"}}` zurueckgeben, ohne eine Exception zu werfen. Der Router SHALL die Capability-Aktivierung aus `LLM_CAPABILITIES` (komma-separierte Liste) lesen. Fehlende Variable oder leere Liste SOLL fail-safe als "alle deaktiviert" gewertet werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] No `LLM_PROVIDER` set → all capabilities return `{"error": {"code": "LLM_NOT_CONFIGURED"}}`
- [ ] `LLM_CAPABILITIES=validate` → `decompose_requirement` returns `{"error": {"code": "LLM_NOT_CONFIGURED"}}`
- [ ] `LLM_CAPABILITIES` not set → all capabilities return `{"error": {"code": "LLM_NOT_CONFIGURED"}}`
- [ ] No unhandled exception escapes from the router under any configuration state
- [ ] System remains functional for non-LLM operations regardless of router state

---

### REQ-L3-LA003-003: Strukturierte Provider-Fehlerbehandlung


**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.


Der CapabilityRouter SHALL alle Exceptions aus ProviderRegistry und Provider-Aufrufen abfangen und als strukturierten Fehler `{error: {code: "LLM_PROVIDER_ERROR", message: "<detail>"}}` zurueckgeben. Abzufangende Fehlerkategorien: Timeout, HTTP-4xx/5xx, Rate-Limit (HTTP 429), unerwartete Exception.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Provider timeout → `{"error": {"code": "LLM_PROVIDER_ERROR", "message": "Request timed out"}}`
- [ ] HTTP 500 from provider → `{"error": {"code": "LLM_PROVIDER_ERROR", "message": "API error: 500"}}`
- [ ] HTTP 429 from provider → `{"error": {"code": "LLM_PROVIDER_ERROR", "message": "Rate limit exceeded"}}`
- [ ] Unexpected exception → `{"error": {"code": "LLM_PROVIDER_ERROR", "message": "<exception text>"}}`
- [ ] No raw exception propagates beyond the router boundary

---

### REQ-L3-LA003-004: Auflösung von LlmSettings und PromptTemplates

Der CapabilityRouter SHALL vor Aufruf von `get_provider` und der Ausführung der Capability prüfen, ob mandantenspezifische `LlmSettings` und/oder `PromptTemplate`-Einträge existieren. Diese MÜSSEN in den Kontext der Anfrage geladen und an ProviderRegistry (`LlmSettings`) und CapabilityInterface (`PromptTemplate`) übergeben werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Bei Ausführung wird das korrekte `PromptTemplate` für die aktuelle Capability (z.B. `sysreq_decompose_next_level`) geladen.
- [ ] Fehlt ein mandantenspezifisches Template, wird das systemweite Default-Template verwendet.

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
