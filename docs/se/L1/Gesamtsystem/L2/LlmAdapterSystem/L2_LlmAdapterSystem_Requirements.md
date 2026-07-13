# L2 LlmAdapter Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** LlmAdapterSystem (ARCH-L1-009)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-20
> **Status:** formalisiert
> **Designation:** component (terminal — keine L3-Zerlegung)

---

## Traceability

- Abgeleitet von: REQ-L1-013 (primär), REQ-L1-011 (mitwirkend), REQ-L1-002 (mitwirkend), REQ-L1-004 (mitwirkend), REQ-L1-026 (mitwirkend)
- Ziel: terminal (keine L3-Zerlegung)

---

## Externe Schnittstellen (Systemgrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-LA-EXT-IN-001 | input | data | `validate_artifact(artifact_id)`, `decompose_requirement(requirement_id)`, `check_consistency(workspace_id)` von ApplicationService |
| IF-LA-EXT-OUT-001 | output | data | HTTPS-Outbound zu LLM-Provider (Anthropic/OpenAI/Ollama/Azure) |
| IF-LA-EXT-OUT-002 | output | data | LLM-Aufruf-Audit-Eintrag an AuditLog (ARCH-L1-012) |
| IF-LA-EXT-OUT-003 | output | data | Task-Dispatch an Celery-Task-Queue (Redis/RabbitMQ); Rückgabe `task_id` an Aufrufer, Status-Rückmeldung via `task.status(task_id)` |

---

## L2 Subsystem-Anforderungen

### REQ-L2-LA-001: LLM-Capability-Interface mit Provider-Abstraktion
Der LlmAdapter SHALL ein stabiles internes Interface (`LlmCapabilityInterface`) mit drei Operationen bereitstellen: `validate_artifact`, `decompose_requirement`, `check_consistency`. Provider-Implementierungen SÜLLEN über ein Plugin-Interface austauschbar sein. Kein Domain-Modul DARF den konkreten Provider kennen.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Anthropic-Provider konfiguriert → `validate_artifact(req_id)` liefert `{score, suggestions}`
- [ ] OpenAI-Provider konfiguriert → identische Schnittstelle
- [ ] Ollama-Provider konfiguriert → identische Schnittstelle
- [ ] Provider-Wechsel via `.env` ohne Code-Änderung
- [ ] Kein Domain-Modul referenziert konkreten Provider-Typ

**Interfaces:**
- Incoming: IF-LA-EXT-IN-001
- Outgoing: IF-LA-EXT-OUT-001


**Traceability:** REQ-L1-013, REQ-L1-002 (mitwirkend), REQ-L1-004 (mitwirkend)
**Rationale:** Provider-Abstraktion verhindert Vendor-Lock-in (ADR-02).


---

### REQ-L2-LA-002: Graceful Degradation bei fehlender LLM-Konfiguration
Der LlmAdapter SHALL bei fehlender LLM-Konfiguration einen strukturierten Fehler `{error: {code: "LLM_NOT_CONFIGURED"}}` zurückgeben. Das restliche System SHALL vollständig funktionsfähig bleiben.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Deployment ohne LLM → `validate_artifact(id)` → Fehler `LLM_NOT_CONFIGURED`
- [ ] `requirement.create(...)` → funktioniert normal
- [ ] `decompose_requirement(id)` → Fehler `LLM_NOT_CONFIGURED`
- [ ] Alle Nicht-LLM-Operationen ohne Einschränkung funktional
- [ ] LLM-Provider nicht erreichbar → gleicher strukturierter Fehler

**Interfaces:**
- Incoming: IF-LA-EXT-IN-001
- Outgoing: IF-LA-EXT-OUT-001 (strukturierter Fehler)


**Traceability:** REQ-L1-013
**Rationale:** Self-Hosted-First bedeutet, dass Deployments ohne LLM der Normalfall sein können.


---

### REQ-L2-LA-003: Selektive Capability-Aktivierung
Der LlmAdapter SHALL per-Capability Aktivierung/Deaktivierung über Deployment-Konfiguration unterstützen. Deaktivierte Capabilities SÜLLEN `LLM_NOT_CONFIGURED` zurückgeben, auch wenn ein Provider konfiguriert ist.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `LLM_CAPABILITIES=validate,decompose` → `check_consistency` deaktiviert
- [ ] Leere Config → alle Capabilities False
- [ ] Deaktivierte Capability → Fehler `LLM_NOT_CONFIGURED`
- [ ] Fehlende Variable → alle False (fail-safe)

**Interfaces:**
- Incoming: IF-LA-EXT-IN-001


**Traceability:** REQ-L1-013
**Rationale:** Adressiert OP-01 (LLM-Capability-Scope).


---

### REQ-L2-LA-004: Standardisiertes LLM-Ergebnisformat
Der LlmAdapter SHALL standardisierte Ergebnisobjekte zurückgeben. `LlmResult`: `score` (0.0–1.0), `suggestions`, `provider`, `model`, `token_usage`. `LlmDecompositionResult` erweitert mit `children`. `LlmConsistencyResult` erweitert mit `issues`. Score außerhalb [0.0, 1.0] SHALL `ValueError` auslösen.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `LlmResult(score=0.85, ...)` → erfolgreich
- [ ] `LlmResult(score=1.5, ...)` → `ValueError`
- [ ] `LlmDecompositionResult(children=[...])` → Struktur korrekt
- [ ] Alle Provider liefern identische Datenklassen-Struktur

**Interfaces:**
- Outgoing: IF-LA-EXT-IN-001 (Rückgabewerte)


**Traceability:** REQ-L1-013
**Rationale:** Standardisierte Formate ermöglichen provider-unabhängige Verarbeitung.


---

### REQ-L2-LA-005: Provider-Fehlerbehandlung und Timeout
Der LlmAdapter SHALL Provider-Fehler (Timeout, API-Error, Rate-Limit) als strukturierten Fehler `LLM_PROVIDER_ERROR` zurückgeben. Keine unhandled Exceptions. Konfigurierbarer Timeout (Default: 30s). Bei synchron ausgeführten Operationen gilt das Timeout als HTTP-Request-Timeout; bei asynchronen Celery-Tasks (siehe REQ-L2-LA-008) wird das Timeout auf Worker-Ebene konfiguriert (`CELERY_TASK_SOFT_TIME_LIMIT`, `CELERY_TASK_TIME_LIMIT`) und greift nicht als HTTP-Request-Timeout.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Provider-Timeout bei synchronem Aufruf → `LLM_PROVIDER_ERROR` `"Request timed out"`
- [ ] HTTP 500 → `LLM_PROVIDER_ERROR` `"API error: 500"`
- [ ] HTTP 429 → `LLM_PROVIDER_ERROR` `"Rate limit exceeded"`
- [ ] Keine unhandled Exceptions
- [ ] Timeout via `LLM_TIMEOUT=60` konfigurierbar (synchron)
- [ ] Celery-Task-Timeout via `CELERY_TASK_SOFT_TIME_LIMIT` / `CELERY_TASK_TIME_LIMIT` konfigurierbar (async)

**Interfaces:**
- Outgoing: IF-LA-EXT-OUT-001, IF-LA-EXT-IN-001 (Fehler)


**Traceability:** REQ-L1-013, REQ-L1-026 (mitwirkend)
**Rationale:** LLM-Ausfälle dürfen das Gesamtsystem nicht beeinträchtigen. Async-Tasks lösen das HTTP-Timeout-Problem für Langläufer (REQ-L2-LA-008).


---

### REQ-L2-LA-006: LLM-Audit-Logging
Der LlmAdapter SHALL jeden LLM-Aufruf (erfolgreich oder fehlgeschlagen) im AuditLog protokollieren mit: `provider`, `capability`, `artifact_id`, `token_usage`, `success`, `error`.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Erfolgreicher Aufruf → AuditLog mit `{source: "llm_adapter", provider, capability, token_usage, success: true}`
- [ ] Fehlgeschlagener Aufruf → AuditLog mit `{success: false, error: "..."}`
- [ ] Token-Verbrauch aus Provider-Response extrahiert
- [ ] Response ohne Usage-Info → `token_usage: None`

**Interfaces:**
- Outgoing: IF-LA-EXT-OUT-002


**Traceability:** REQ-L1-011, REQ-L1-013 (mitwirkend)
**Rationale:** Vollständige Auditierbarkeit umfasst LLM-Aufrufe.


---

### REQ-L2-LA-007: Azure-OpenAI Provider-Unterstützung
Der LlmAdapter SOLLTE Azure-OpenAI als zusätzlichen Provider unterstützen (`LLM_PROVIDER=azure`). Azure-spezifische Konfiguration: Endpoint-URL, Deployment-Name, API-Version.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist im Code implementiert (AzureOpenAiProvider in providers.py), aber entsprechende Tests fehlen in test_llm_adapter.py.
**Test Status:** Missing
**Remarks:** Testabdeckung in test_llm_adapter.py ergänzen.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] `LLM_PROVIDER=azure` → `AzureOpenAiProvider`-Instanz
- [ ] Identische `LlmResult`-Struktur wie andere Provider
- [ ] Implementiert `LlmCapabilityInterface`

**Interfaces:**
- Outgoing: IF-LA-EXT-OUT-001


**Traceability:** REQ-L1-013
**Rationale:** Azure-OpenAI ist für Enterprise-Deployments relevant.


---

### REQ-L2-LA-008: Asynchrone LLM-Task-Ausführung via Celery
Der LlmAdapter SHALL LLM-Langläufer-Operationen (`decompose_requirement`, `check_consistency`) als Celery-Tasks asynchron ausführen. Diese Operationen DÜRFEN den WSGI/ASGI-Worker NICHT blockieren. Der Adapter SHALL bei Aufruf einer async-fähigen Capability sofort eine `task_id` zurückgeben. Der Status des Tasks ist über ein separates Interface abfragbar: `task.status(task_id)` → `{status: "pending|running|done|failed", result?, error?}`. Die Capability `validate_artifact` DARF synchron bleiben (typische Laufzeit < 5s).

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `decompose_requirement(req_id)` → sofortige Antwort `{task_id: "<uuid>"}`, kein Blocking des WSGI/ASGI-Workers
- [ ] `check_consistency(workspace_id)` → sofortige Antwort `{task_id: "<uuid>"}`
- [ ] `task.status(task_id)` → `{status: "pending"}` unmittelbar nach Dispatch
- [ ] `task.status(task_id)` → `{status: "running"}` während Celery-Worker-Ausführung
- [ ] `task.status(task_id)` → `{status: "done", result: {...}}` nach Abschluss
- [ ] `task.status(task_id)` → `{status: "failed", error: "..."}` bei Fehler
- [ ] `validate_artifact(artifact_id)` bleibt synchron und antwortet innerhalb 5s
- [ ] Celery-Broker (Redis oder RabbitMQ) via `CELERY_BROKER_URL` konfigurierbar

**Interfaces:**
- Incoming: IF-LA-EXT-IN-001
- Outgoing: IF-LA-EXT-OUT-001 (LLM-Provider-Aufruf durch Celery-Worker), IF-LA-EXT-OUT-003 (Task-Dispatch an Celery-Queue)


**Traceability:** REQ-L1-013 (primär), REQ-L1-026 (mitwirkend)
**Rationale:** Massenzerlegungen und Konsistenzprüfungen können mehrere Minuten dauern. Blockierende Synchronaufrufe erschöpfen den WSGI/ASGI-Worker-Pool und machen das System für andere Nutzer unresponsiv. Celery entkoppelt Aufruf und Ausführung.


---

### REQ-L2-LA-009: LlmSettings — Mandanten-konfigurierbarer LLM-Provider

Das System MUSS ein Singleton-Modell `LlmSettings` pro Mandant bereitstellen (Felder: provider, base_url, api_key verschlüsselt/write-only, model als Freitext) mit Fallback auf Umgebungsvariablen; REST-Zugriff nur für Admin-Rolle; api_key niemals in GET-Antworten; Admin-UI im Settings-Bereich.

**Implementation State:** Not Implemented
**Domain:** software
**Priority:** must
**Remarks:** Neu aufgenommen 2026-07-11. WP3 Aufgabe 3c.

---

### REQ-L2-LA-010: PromptTemplate — Admin-editierbare Prompt-Slots

Das System MUSS ein Modell `PromptTemplate` mit den Slots `need_to_sysreq`, `sysreq_to_arch_assign` und `sysreq_decompose_next_level` bereitstellen; jeder Slot hat einen unveränderlichen Default-Prompt (Seed-Migration), kann vom Admin überschrieben und auf Default zurückgesetzt werden; Derivation-Flows (REQ-L2-AI-002) verwenden diese Slots; REST und MCP exponiert; Admin-UI im Settings-Bereich.

**Implementation State:** Not Implemented
**Domain:** software
**Priority:** must
**Remarks:** Neu aufgenommen 2026-07-11. WP3 Aufgabe 3d.

## Traceability-Matrix: REQ-L2-LA → REQ-L1

| REQ-L2-LA | Primäre REQ-L1 | Mitwirkende REQ-L1 |
|-----------|----------------|---------------------|
| REQ-L2-LA-001 | REQ-L1-013 | REQ-L1-002, REQ-L1-004 |
| REQ-L2-LA-002 | REQ-L1-013 | — |
| REQ-L2-LA-003 | REQ-L1-013 | — |
| REQ-L2-LA-004 | REQ-L1-013 | — |
| REQ-L2-LA-005 | REQ-L1-013 | REQ-L1-026 |
| REQ-L2-LA-006 | REQ-L1-011 | REQ-L1-013 |
| REQ-L2-LA-007 | REQ-L1-013 | — |
| REQ-L2-LA-008 | REQ-L1-013 | REQ-L1-026 |
| REQ-L2-LA-009 | REQ-L1-013 | — |
| REQ-L2-LA-010 | REQ-L1-013 | — |

---

## Zusammenfassung

| Metrik | Wert |
|--------|------|
| Anzahl REQ-L2-LA | 8 |
| Mandatory | 7 |
| Desired | 1 |
| Optional | 0 |
| Abgedeckte REQ-L1 (primär) | REQ-L1-013, REQ-L1-011 |
| Abgedeckte REQ-L1 (mitwirkend) | REQ-L1-002, REQ-L1-004, REQ-L1-026 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L1→L2 | 2026-06-20*
*Complete Rewrite: ID-Migration REQ-L2-Llm → REQ-L2-LA, Template-Standardisierung*
*Designation: component (terminal) — decomposition_status: terminal*


## Master Traceability Matrix

| REQ-L2 | Abgeleitet von REQ-L1 |
|---------|----------------------|
| REQ-L2-LA-001 | REQ-L1-013, REQ-L1-002 (mitwirkend), REQ-L1-004 (mitwirkend) |
| REQ-L2-LA-002 | REQ-L1-013 |
| REQ-L2-LA-003 | REQ-L1-013 |
| REQ-L2-LA-004 | REQ-L1-013 |
| REQ-L2-LA-005 | REQ-L1-013, REQ-L1-026 (mitwirkend) |
| REQ-L2-LA-006 | REQ-L1-011, REQ-L1-013 (mitwirkend) |
| REQ-L2-LA-007 | REQ-L1-013 |
| REQ-L2-LA-008 | REQ-L1-013 (primär), REQ-L1-026 (mitwirkend) |
| REQ-L2-LA-009 | REQ-L1-013 |
| REQ-L2-LA-010 | REQ-L1-013 |

