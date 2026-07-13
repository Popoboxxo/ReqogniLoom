# L3 ArchitectureToolGroup Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-MC-004 — ArchitectureToolGroup
> **Parent-System:** McpServerSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Implementierung der fuenf Architecture-Tools: `architecture.get`, `architecture.query`, `architecture.create`, `architecture.update` und `architecture.link`. Die Gruppe empfaengt authorisierte `execute_tool`-Aufrufe von der ToolRegistry, delegiert Domain-Operationen direkt an den ApplicationService via In-Process-Python und erzeugt TraceLinks zwischen Architekturelemente und anderen Artefakten.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-MC-002 | Fuenf Architecture-Tools; architecture.link unterstuetzt Verknuepfung mit Requirement, TestCase, ArchitectureElement |
| REQ-L2-MC-009 | Direkter ApplicationService-Zugriff via In-Process-Python; keine HTTP-Roundtrips |
| REQ-L2-MC-012 | AuditLog-Eintrag bei jeder schreibenden Operation; synchron vor Response |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-MC-INT-003 | eingehend | COMP-MC-002 ToolRegistry | `execute_tool(tool_name, params, auth_context) -> ToolResult` |
| IF-MC-INT-006 | ausgehend | COMP-MC-001 ProtocolHandler | `ToolResult -> JSON-Response` |

## Externe Schnittstellen (Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Typ | Beschreibung |
|-------|----------|-------------|-----|--------------|
| IF-MC-EXT-OUT-003 | ausgehend | ApplicationService | data | Use-Case-Methoden (In-Process Python); inkl. AuditLog-Schreiben |

---

## L3 Komponenten-Anforderungen

### REQ-L3-MC004-001: Implementierung der fuenf Architecture-Tools


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Die ArchitectureToolGroup SHALL die fuenf Tools `architecture.get`, `architecture.query`, `architecture.create`, `architecture.update` und `architecture.link` implementieren. Jedes Tool SHALL seine Eingabeparameter gegen ein dediziertes JSON-Schema validieren. `architecture.create` SHALL als Pflichtparameter `title`, `description`, `element_type` und `workspace_id` verlangen und ein ArchitectureElement mit UUID zurueckgeben.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] All 5 tools callable via `execute_tool` interface with correctly serialized results
- [ ] `architecture.create(title, description, element_type, workspace_id)` → ArchitectureElement with UUID
- [ ] `architecture.get(id)` → ArchitectureElement with all linked artifacts
- [ ] `architecture.query(filter)` → paginated list matching filter criteria
- [ ] `architecture.update(id, data)` → updated ArchitectureElement
- [ ] Missing required parameter → error `VALIDATION_ERROR` with field details

---

### REQ-L3-MC004-002: TraceLink-Erzeugung via architecture.link


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Das Tool `architecture.link` SHALL das Verknuepfen eines ArchitectureElements mit einem Requirement, einem TestCase oder einem anderen ArchitectureElement unterstuetzen. Der Parameter `link_type` SHALL validiert werden; ungueltiger Link-Typ SHALL mit `VALIDATION_ERROR` abgelehnt werden. Der erzeugte TraceLink SHALL eine eindeutige ID erhalten.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] `architecture.link(arch_id, target_id, target_type="requirement", link_type="implements")` → TraceLink with valid ID
- [ ] `architecture.link(arch_id, target_id, target_type="testcase", link_type="verified_by")` → TraceLink created
- [ ] Invalid `link_type` value → error `VALIDATION_ERROR`
- [ ] Non-existent `arch_id` or `target_id` → error from ApplicationService propagated as structured error

---

### REQ-L3-MC004-003: AuditLog-Erzeugung bei schreibenden Operationen


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Die ArchitectureToolGroup SHALL fuer jede schreibende Operation (create, update, link) einen AuditLog-Eintrag ueber den ApplicationService (IF-MC-EXT-OUT-003) erzeugen. Der Eintrag SHALL Agent-Client-Identitaet, API-Key-Hash, Tool-Name, betroffene Entitaets-ID(s) und Zeitstempel enthalten. Speziell fuer `architecture.link` SHALL die TraceLink-ID im AuditLog erfasst werden.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] After `architecture.create`: AuditLog contains agent user ID, tool name, new UUID
- [ ] After `architecture.link`: AuditLog contains agent user ID, tool name, TraceLink ID, source and target IDs
- [ ] Read operations (`get`, `query`) do NOT produce AuditLog entries
- [ ] AuditLog entry exists before ToolResult is returned to ToolRegistry

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
