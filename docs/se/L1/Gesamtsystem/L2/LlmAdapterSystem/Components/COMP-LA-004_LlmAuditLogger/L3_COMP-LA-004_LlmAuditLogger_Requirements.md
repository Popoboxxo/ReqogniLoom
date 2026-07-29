decomposition_status: terminal

# L3 LlmAuditLogger Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-LA-004 — LlmAuditLogger
> **Parent-System:** LlmAdapterSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Audit-Logging fuer jeden LLM-Aufruf (erfolgreich oder fehlgeschlagen). Extrahiert Token-Verbrauch aus Provider-Responses und schreibt strukturierte Audit-Eintraege an den zentralen AuditLog (ARCH-L1-012). Sorgt fuer vollstaendige Auditierbarkeit des LLM-Nutzungsverhaltens.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-LA-006 | LLM-Audit-Logging |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-LA-INT-004 | ausgehend | COMP-LA-003 (CapabilityRouter) | `log_llm_call(provider, capability, artifact_id, token_usage, success, error)` |

## Externe Schnittstellen (falls Komponente an Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-LA-EXT-OUT-002 | ausgehend | AuditLog (ARCH-L1-012) | LLM-Aufruf-Audit-Eintrag (In-Process Python) |

---

## L3 Komponenten-Anforderungen

### REQ-L3-LA004-001: Vollstaendige Protokollierung jedes LLM-Aufrufs


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Der LlmAuditLogger SHALL jeden LLM-Aufruf — erfolgreich oder fehlgeschlagen — als Audit-Eintrag an den AuditLog schreiben. Der Eintrag SHALL folgende Felder enthalten: `source` (fest: "llm_adapter"), `provider` (str), `capability` (str), `artifact_id` (str | None), `token_usage` (int | None), `success` (bool), `error` (str | None). Der Logger SHALL den Aufruf in allen Faellen protokollieren, auch wenn kein Provider konfiguriert ist oder ein Fehler aufgetreten ist.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Successful call → AuditLog entry with `{"source": "llm_adapter", "success": true, "token_usage": <int>}`
- [ ] Failed call → AuditLog entry with `{"success": false, "error": "<message>"}`
- [ ] `LLM_NOT_CONFIGURED` case → AuditLog entry written with `{"success": false, "error": "LLM_NOT_CONFIGURED"}`
- [ ] Every call to `log_llm_call(...)` results in exactly one AuditLog write
- [ ] No exception from AuditLog write propagates back to the CapabilityRouter

---

### REQ-L3-LA004-002: Token-Verbrauch-Extraktion aus Provider-Response


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Der LlmAuditLogger SHALL den Token-Verbrauch aus der Provider-Response extrahieren. Falls die Provider-Response kein Usage-Objekt enthaelt, SHALL `token_usage: None` protokolliert werden. Die Extraktion SHALL provider-unabhaengig ueber eine normalisierte Hilfsfunktion erfolgen.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Anthropic response with `usage.input_tokens` + `usage.output_tokens` → `token_usage` = sum
- [ ] OpenAI response with `usage.total_tokens` → `token_usage` = value
- [ ] Response without usage field → `token_usage: None` logged without error
- [ ] Extraction function callable without provider SDK in scope (uses duck typing / dict access)

---

### REQ-L3-LA004-003: Fehlertolerantes Logging ohne Seiteneffekte


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Der LlmAuditLogger SHALL so implementiert sein, dass ein Fehler beim Schreiben des Audit-Eintrags den eigentlichen LLM-Aufruf und dessen Ergebnis nicht beeintraechtigt. Logging-Fehler SOLLEN intern (z.B. als Python-Warning) gemeldet werden, ohne Exception nach aussen zu propagieren.

**Priority:** desired
**Acceptance Criteria:**
- [ ] AuditLog write failure → LLM result is still returned to caller
- [ ] AuditLog write failure → Python warning or internal log message emitted
- [ ] No unhandled exception escapes from `log_llm_call(...)` under any condition

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*

---

### REQ-L3-LA004-004: L3 Context Generators Implementation

Derives from REQ-L2-LLM-015 (which derives from REQ-L1-285).
Component implements specific logic for prompt enrichment and context generation.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Context Generators are wired properly.

---

### REQ-L3-LA004-005: L3 Agent Templates & Review Endpoints

Derives from REQ-L2-LLM-016 (which derives from REQ-L1-286).
Component supports Write Modes, Agent Templates, or frontend integrations for Superpowers.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Review Endpoints / Agent Templates supported.
