decomposition_status: terminal

# L3 RequirementsToolGroup Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-MC-003 — RequirementsToolGroup
> **Parent-System:** McpServerSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Implementierung der sechs Requirements-Tools: `requirement.get`, `requirement.query`, `requirement.create`, `requirement.update`, `requirement.decompose` und `requirement.validate`. Die Gruppe empfaengt authorisierte `execute_tool`-Aufrufe von der ToolRegistry, delegiert Domain-Operationen direkt an den ApplicationService via In-Process-Python und gibt strukturierte `ToolResult`-Objekte zurueck.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-MC-001 | Sechs Requirements-Tools; JSON-Schema-Validierung; LLM-abhaengige Tools mit LLM_NOT_CONFIGURED-Fehler |
| REQ-L2-MC-009 | Direkter ApplicationService-Zugriff via In-Process-Python; keine HTTP-Roundtrips |
| REQ-L2-MC-012 | AuditLog-Eintrag bei jeder schreibenden Operation; synchron vor Response |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-MC-INT-002 | eingehend | COMP-MC-002 ToolRegistry | `execute_tool(tool_name, params, auth_context) -> ToolResult` |
| IF-MC-INT-006 | ausgehend | COMP-MC-001 ProtocolHandler | `ToolResult -> JSON-Response` |

## Externe Schnittstellen (Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Typ | Beschreibung |
|-------|----------|-------------|-----|--------------|
| IF-MC-EXT-OUT-003 | ausgehend | ApplicationService | data | Use-Case-Methoden (In-Process Python); inkl. AuditLog-Schreiben |

---

## L3 Komponenten-Anforderungen

### REQ-L3-MC003-001: Implementierung der sechs Requirements-Tools


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Die RequirementsToolGroup SHALL die sechs Tools `requirement.get`, `requirement.query`, `requirement.create`, `requirement.update`, `requirement.decompose` und `requirement.validate` implementieren. Jedes Tool SHALL seine Eingabeparameter gegen ein dediziertes JSON-Schema validieren, bevor der ApplicationService aufgerufen wird. Bei Parameterverstoss SHALL ein `VALIDATION_ERROR` zurueckgegeben werden.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] All 6 tools callable via `execute_tool` interface with correctly serialized results
- [ ] `requirement.get(id)` returns requirement with traces, workflow history, and audit fields
- [ ] `requirement.query(filter)` returns paginated list matching filter criteria
- [ ] `requirement.create(data)` returns new requirement with UUID
- [ ] `requirement.update(id, data)` returns updated requirement
- [ ] Missing required parameter → error `VALIDATION_ERROR` with field details

---

### REQ-L3-MC003-002: LLM-abhaengige Tool-Absicherung


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Die Tools `requirement.decompose` und `requirement.validate` SHALL vor dem ApplicationService-Aufruf pruefen, ob ein LLM-Provider konfiguriert ist. Ist kein LLM-Provider konfiguriert, SHALL das Tool unmittelbar mit dem Fehler `LLM_NOT_CONFIGURED` zurueckgeben, ohne den ApplicationService aufzurufen.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] `requirement.decompose` without LLM config → error `LLM_NOT_CONFIGURED`, no ApplicationService call
- [ ] `requirement.validate` without LLM config → error `LLM_NOT_CONFIGURED`, no ApplicationService call
- [ ] `requirement.decompose` with LLM config → ApplicationService called and result returned
- [ ] `requirement.validate` with LLM config → ApplicationService called and result returned

---

### REQ-L3-MC003-003: AuditLog-Erzeugung bei schreibenden Operationen


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Die RequirementsToolGroup SHALL fuer jede schreibende Operation (create, update, decompose) einen AuditLog-Eintrag ueber den ApplicationService (IF-MC-EXT-OUT-003) erzeugen. Der Eintrag SHALL Agent-Client-Identitaet, API-Key-Hash, Tool-Name, betroffene Entitaets-ID und Zeitstempel enthalten. Der AuditLog-Eintrag SHALL synchron persistiert sein, bevor das `ToolResult` zurueckgegeben wird.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] After `requirement.create`: AuditLog contains agent user ID, API-Key hash, tool name, new UUID
- [ ] After `requirement.update`: AuditLog contains agent user ID, tool name, updated entity UUID
- [ ] Read operations (`get`, `query`) do NOT produce AuditLog entries
- [ ] AuditLog entry exists before ToolResult is returned to ToolRegistry

---

### REQ-L3-MC003-004: MCP RBAC Enforcement (P-03)

Die RequirementsToolGroup MUSS am Tool-Eingang einen strikten RBAC-Check (Role-Based Access Control) durchführen, bevor mutierende Operationen ausgeführt werden.

**Implementation State:** Planned
**Review Findings:** Abgeleitet von P-03.
**Test Status:** Untested
**Priority:** mandatory
**Abgeleitet von:** REQ-L2-MC-018

---

### REQ-L3-MC003-005: MCP Audit Logging für StakeholderNeeds (P-04)

Mutierende Tools für StakeholderNeeds (`needs.create`, `needs.update`) MÜSSEN einen AuditLog-Eintrag generieren. (Falls StakeholderNeeds hier verwaltet werden).

**Implementation State:** Planned
**Review Findings:** Abgeleitet von P-04.
**Test Status:** Untested
**Priority:** mandatory
**Abgeleitet von:** REQ-L2-MC-021

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*

---

### REQ-L3-MC003-006: L3 Context Generators Implementation

Derives from REQ-L2-MCP-015 (which derives from REQ-L1-285).
Component implements specific logic for prompt enrichment and context generation.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Context Generators are wired properly.

---

### REQ-L3-MC003-007: L3 Agent Templates & Review Endpoints

Derives from REQ-L2-MCP-016 (which derives from REQ-L1-286).
Component supports Write Modes, Agent Templates, or frontend integrations for Superpowers.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Review Endpoints / Agent Templates supported.
