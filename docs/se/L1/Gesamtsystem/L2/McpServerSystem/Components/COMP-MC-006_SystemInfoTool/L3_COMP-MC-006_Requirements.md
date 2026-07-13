# L3 SystemInfoTool Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-MC-006 — SystemInfoTool
> **Parent-System:** McpServerSystem (L2)
> **Status:** formalisiert
> **Datum:** 2026-07-04

---

## Verantwortlichkeit

MCP-Tool, um Agenten über Systemwartungen oder Status-Nachrichten zu informieren, damit diese ihre Antworten oder ihr Verhalten anpassen können.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-MC-016 | System Info Tool (Announcement) |

## L3 Komponenten-Anforderungen

### REQ-L3-MC006-001: Tool Registrierung und Rückgabe

Das Tool `get_system_announcement` MUSS am MCP-Router registriert werden.

**Implementation State:** Not Implemented
**Priority:** desired
**Acceptance Criteria:**
- [ ] Wenn `active=true`, wird der `message` String an den Agenten retourniert.
- [ ] Wenn `active=false`, wird z.B. "System operates normally" retourniert.
- [ ] Tool erfordert keine Parameter.
