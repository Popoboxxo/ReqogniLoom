# L2 McpServer Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** McpServerSystem (ARCH-L1-003)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-20
> **Status:** formalisiert
> **Designation:** Composite (L3-Zerlegung in Components/-Unterverzeichnis mit 6 Komponenten: COMP-MC-001 bis COMP-MC-006)

---

## Traceability

- Abgeleitet von: REQ-L1-005 (primär), REQ-L1-007 (mitwirkend), REQ-L1-010 (mitwirkend), REQ-L1-011 (mitwirkend), REQ-L1-013 (mitwirkend), REQ-L1-020 (mitwirkend), REQ-L1-026 (mitwirkend)
- Ziel: terminal (keine L3-Zerlegung)

---

## Externe Schnittstellen (Systemgrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-MC-EXT-IN-001 | input | data | AI-Agent → McpServer: MCP-Protokoll (JSON-RPC über stdio/SSE/HTTP) mit API-Key |
| IF-MC-EXT-OUT-001 | output | data | McpServer → AI-Agent: Strukturierte Tool-Response (JSON) oder Fehler |

## Externe Schnittstellen (ausgehend)

| ID | Richtung | Ziel | Typ | Beschreibung |
|----|----------|------|-----|--------------|
| IF-MC-EXT-OUT-002 | output | ARCH-L1-011 | data | API-Key-Validierung, Agent-Identität, Tenant, Rollen |
| IF-MC-EXT-OUT-003 | output | ARCH-L1-004 | data | Use-Case-Methoden (In-Process Python) |
- [ ] Fehlender/ungültiger API-Key → Fehler mit HTTP 401-Äquivalent
- [ ] Jede Einspeisung erzeugt Audit-Log-Eintrag mit Client-Identität
- [ ] Tool ist via MCP-Protokoll (stdio, SSE, HTTP) aufrufbar
- [ ] Tool akzeptiert optionale Ausgabe-Payload (z.B. Test-Log, Screenshot-Referenz)

**Interfaces:**
- Incoming: IF-MC-EXT-IN-001
- Outgoing: IF-MC-EXT-OUT-001, IF-MC-EXT-OUT-003

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch das neue Redis PubSub SSE Streaming in Tests abgedeckt und standardkonform implementiert.
**Test Status:** Covered
**Remarks:** Implementierung durch `McpMessagesView` und `McpSseTransportView` abgeschlossen.

**Traceability:** REQ-L1-036, REQ-L1-011 (mitwirkend)
**Rationale:** MCP-Tool ermöglicht AI-Agenten und CI/CD-Systemen direkte Test-Ergebnis-Einspeisung.


---

## Traceability-Matrix: REQ-L2-MC → REQ-L1

| REQ-L2-MC | Primäre REQ-L1 | Mitwirkende REQ-L1 |
|-----------|----------------|---------------------|
| REQ-L2-MC-001 | REQ-L1-005 | REQ-L1-002, REQ-L1-011, REQ-L1-013 |
| REQ-L2-MC-002 | REQ-L1-005 | REQ-L1-004, REQ-L1-003, REQ-L1-011 |
| REQ-L2-MC-003 | REQ-L1-005 | REQ-L1-012, REQ-L1-003, REQ-L1-011 |
| REQ-L2-MC-004 | REQ-L1-005 | REQ-L1-020, REQ-L1-003, REQ-L1-007 |
| REQ-L2-MC-005 | REQ-L1-005 | — |
| REQ-L2-MC-006 | REQ-L1-005 | REQ-L1-010, REQ-L1-011 |
| REQ-L2-MC-007 | REQ-L1-010 | REQ-L1-005 |
| REQ-L2-MC-008 | REQ-L1-007 | REQ-L1-005 |
| REQ-L2-MC-009 | REQ-L1-005 | REQ-L1-006 |
| REQ-L2-MC-010 | REQ-L1-026 | REQ-L1-005 |
| REQ-L2-MC-011 | REQ-L1-005 | — |
| REQ-L2-MC-012 | REQ-L1-011 | REQ-L1-005 |
| REQ-L2-MC-013 | REQ-L1-036 | REQ-L1-011 |

---

## Zusammenfassung

| Metrik | Wert |
|--------|------|
| Anzahl REQ-L2-MC | 13 |
| Mandatory | 10 |
| Desired | 3 |
| Optional | 0 |
| Abgedeckte REQ-L1 (primär) | REQ-L1-005, REQ-L1-010, REQ-L1-011, REQ-L1-026, REQ-L1-007, REQ-L1-036 |
| Abgedeckte REQ-L1 (mitwirkend) | REQ-L1-002, REQ-L1-003, REQ-L1-004, REQ-L1-006, REQ-L1-012, REQ-L1-013, REQ-L1-020 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L1→L2 | 2026-06-20*
*Complete Rewrite: ID-Migration REQ-L2-Mcp → REQ-L2-MC, Template-Standardisierung*
*Designation: LEAF (terminal, keine L3-Zerlegung)*

---

## Erweiterung v2 — REQ-L2-MC-014..015 (aus REQ-L1-036 und REQ-L1-038)

> **Datum:** 2026-06-28 | **Quelle:** REQ-L0-024 → REQ-L1-036, REQ-L0-026 → REQ-L1-038

---

### REQ-L2-MC-014: MCP-Tool `semantic_search` (Semantische Suche für AI-Agenten)

**Implementation State:** Implemented
**Review Findings:** MCP-Server exportiert das Tool `semantic_search` standardkonform.
**Test Status:** Covered
**Remarks:** Abgeleitet von REQ-L1-038 (← REQ-L0-026, SN-26). Abhängigkeit: REQ-L2-VS-001.

Der MCP-Server MUSS ein Tool `semantic_search` bereitstellen, über das AI-Agenten
semantische Suchanfragen gegen einen Workspace stellen können. Das Tool delegiert
intern an den VectorSearchService (REQ-L2-VS-001) und gibt die Top-N Ergebnisse
mit Artefakt-ID, Typ, Titel und Ähnlichkeitsscore zurück.

**MCP-Tool-Spezifikation:**
```json
{
  "name": "semantic_search",
  "description": "Search requirements semantically using vector embeddings",
  "inputSchema": {
    "workspace_id": "string (required)",
    "query": "string (required)",
    "top_n": "integer (default: 10)",
    "threshold": "float (default: 0.7)"
  }
}
```

**Akzeptanzkriterien:**
- AC1: `semantic_search(workspace_id, query)` → Liste der Top-N ähnlichsten Artefakte
- AC2: Tool ist im MCP-Tool-Katalog registriert und per `list_tools` sichtbar
- AC3: Fehlerfall (VectorSearch nicht verfügbar) → strukturierter MCP-Fehler
- AC4: Latenz innerhalb MCP-Timeout (< 30 s)

**Verifikationsmethode:** MCP-Integrationstest — Tool-Call, Response-Validierung
**Verifikiert durch:** L2-MC-Test-014
**Abgeleitet von:** REQ-L1-038
**Übergeordnete REQ-L0:** REQ-L0-026

---

### REQ-L2-MC-015: MCP-Tool `record_test_result` (Testergebnis-Einspeisung)

**Implementation State:** Implemented
**Review Findings:** Tool ist als `test.run_report_results` für Bulk-Verarbeitung und `test.run_create` implementiert. Namensgebung und Schema exportieren dynamisch über `tools/list`.
**Test Status:** Covered
**Remarks:** Abgeleitet von REQ-L1-036.

Der MCP-Server MUSS ein Tool `record_test_result` bereitstellen, über das
CI/CD-Pipelines und AI-Agenten Testergebnisse direkt in ReqFlow einspeisen können.
Ein TestRun-Record wird angelegt und mit dem zugehörigen TestCase verknüpft.
Das Tool persistiert: TestCase-ID, Status (passed/failed/skipped), Ausführungszeit,
Fehlermeldung (optional) und Zeitstempel.

**MCP-Tool-Spezifikation:**
```json
{
  "name": "record_test_result",
  "description": "Record a test execution result for a test case",
  "inputSchema": {
    "testcase_id": "string (required)",
    "status": "enum: passed | failed | skipped (required)",
    "duration_ms": "integer",
    "error_message": "string (optional)",
    "run_id": "string (optional, CI-Pipeline-Referenz)"
  }
}
```

**Akzeptanzkriterien:**
- AC1: `record_test_result(testcase_id, status="passed")` → TestRun-Record angelegt
- AC2: TestRun ist über API abrufbar und mit TestCase verknüpft
- AC3: `status="failed"` mit `error_message` → Fehlermeldung im TestRun gespeichert
- AC4: Unbekannte `testcase_id` → strukturierter MCP-Fehler (kein Crash)
- AC5: Tool ist im MCP-Tool-Katalog per `list_tools` sichtbar

**Verifikationsmethode:** MCP-Integrationstest — Tool-Call, TestRun-Persistenz prüfen
**Verifikiert durch:** L2-MC-Test-015
**Abgeleitet von:** REQ-L1-036
**Übergeordnete REQ-L0:** REQ-L0-024

---

*Erweiterung durch se-requirements-Agent | 2026-06-28 (REQ-L2-MC-014..015 aus REQ-L1-036, REQ-L1-038)*

---

## Erweiterung v1 — REQ-L2-MC-016 (System Announcement Tool)

> **Datum:** 2026-07-04 | **Quelle:** REQ-L1-082

---

### REQ-L2-MC-016: System Info Tool (Announcement)

Das McpServerSystem MUSS ein Tool (`get_system_announcement`) bereitstellen, mit dem KI-Agenten abfragen können, ob systemweite Warnungen oder Hinweise (z.B. Wartungsarbeiten) vorliegen, um ihr Verhalten entsprechend anzupassen (oder den User darauf hinzuweisen).

**Implementation State:** Implemented
**Review Findings:** `get_system_announcement` ist im MCP Server als `system.info` registriert und implementiert.
**Test Status:** Covered
**Priority:** desired
**Acceptance Criteria:**
- [ ] Tool `get_system_announcement` ist im MCP Server registriert.
- [ ] Liefert die aktuelle System-Nachricht, falls `active=true`, andernfalls eine leere oder "all good" Rückmeldung.

**Verifikationsmethode:** MCP Tool Aufruf Test.
**Verifikiert durch:** L2-MC-Test-016
**Abgeleitet von:** REQ-L1-082

---

## Erweiterung v2 — System Audit Security & Compliance (P-01 bis P-16)

> **Datum:** 2026-07-13 | **Quelle:** SYSTEM_AUDIT.md

---

### REQ-L2-MC-017: MCP Security & Secret Management

Das McpServerSystem MUSS sicherstellen, dass API-Keys niemals im Klartext geloggt werden (kein `logger.error` mit Auth-Headern). Ebenso dürfen API-Keys nicht als URL-Parameter (z.B. im SSE-Endpoint `/mcp/messages/`) übertragen werden; die Session-Verknüpfung MUSS serverseitig nach dem Handshake erfolgen.
Zudem MUSS bei der SSE-Verbindung der API-Key bereits beim initialen Connect validiert werden (nicht erst beim ersten POST).

**Implementation State:** Planned
**Review Findings:** Abgeleitet von P-01, P-02, P-16.
**Test Status:** Untested
**Priority:** mandatory
**Abgeleitet von:** REQ-L1-096

---

### REQ-L2-MC-018: MCP RBAC & Rate-Limiting

Alle mutierenden MCP-Tools (insbesondere `needs.*`, `adr.*`, `risk.*`, `issue.*`, `glossary.*`) MÜSSEN am Tool-Eingang oder durch Delegation an den ApplicationService einen RBAC-Check (Role-Based Access Control) durchführen.
Zusätzlich MUSS das MCP-System Rate-Limiting pro API-Key und eine strikte CORS-Allowlist durchsetzen (kein blindes Spiegeln des Origin-Headers).

**Implementation State:** Planned
**Review Findings:** Abgeleitet von P-03, P-13, P-15.
**Test Status:** Untested
**Priority:** mandatory
**Abgeleitet von:** REQ-L1-096, REQ-L1-099

---

### REQ-L2-MC-019: MCP Protocol Compliance & Schemas

Das MCP-System MUSS fehlerhafte Requests, die kein Auth-Problem darstellen (Parse Error), mit HTTP 400 (statt 401) beantworten. JSON-RPC-Fehler MÜSSEN als Integer-`code` formatiert sein. Alle Tools (insbesondere GenericCrud) MÜSSEN strikte JSON-Input-Schemas besitzen. Parameternamen (z.B. `id` vs. `requirement_id`) MÜSSEN zwischen Schema und Handler konsistent sein.

**Implementation State:** Planned
**Review Findings:** Abgeleitet von P-05, P-06, P-08, P-10.
**Test Status:** Untested
**Priority:** mandatory
**Abgeleitet von:** REQ-L1-005

---

### REQ-L2-MC-020: MCP Performance & Concurrency

Das MCP-System MUSS Thread-Pools in Transport-Views (z.B. `McpMessagesView`) explizit limitieren. Such-Tools wie `artifact.search` MÜSSEN ein maximales Fetch-Limit erzwingen. Listen-Filter (wie `admin.backup_list`) MÜSSEN datenbankseitig operieren, nicht in-memory. Race-Conditions via TOCTOU (z.B. bei `user.create`) MÜSSEN durch DB-Level-Constraints oder atomare Operationen verhindert werden. Preset-Caches MÜSSEN über Redis laufen (nicht prozesslokal).

**Implementation State:** Planned
**Review Findings:** Abgeleitet von P-07, P-09, P-11, P-12, P-14.
**Test Status:** Untested
**Priority:** mandatory
**Abgeleitet von:** REQ-L1-097, REQ-L1-099

---

### REQ-L2-MC-021: MCP Audit Logging für Needs

Mutierende Tools für StakeholderNeeds (`needs.create`, `needs.update`) MÜSSEN einen AuditLog-Eintrag generieren.

**Implementation State:** Planned
**Review Findings:** Abgeleitet von P-04.
**Test Status:** Untested
**Priority:** mandatory
**Abgeleitet von:** REQ-L1-005

---

*Erstellt durch se-requirements-Agent (L2) | ReqFlow SE-Kaskade | 2026-07-04*
