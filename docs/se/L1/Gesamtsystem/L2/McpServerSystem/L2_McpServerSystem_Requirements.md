# L2 McpServer Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** McpServerSystem (ARCH-L1-003)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-20
> **Status:** formalisiert
> **Designation:** LEAF (terminal, keine L3-Zerlegung)

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

**Implementation State:** Not Implemented
**Review Findings:** Anforderung ist in Tests abgedeckt, aber Implementierung fehlt.
**Test Status:** Covered
**Remarks:** Implementierung abschließen.

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
# L2 McpServer Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** McpServerSystem (ARCH-L1-003)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-20
> **Status:** formalisiert
> **Designation:** LEAF (terminal, keine L3-Zerlegung)

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

**Implementation State:** Not Implemented
**Review Findings:** Anforderung ist in Tests abgedeckt, aber Implementierung fehlt.
**Test Status:** Covered
**Remarks:** Implementierung abschließen.

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

**Implementation State:** Not Implemented
**Review Findings:** MCP-Server hat kein `semantic_search`-Tool. VectorSearchService (REQ-L2-VS-001) muss zuerst implementiert werden.
**Test Status:** Missing
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

**Implementation State:** Not Implemented
**Review Findings:** Das Tool `test.record_result` existiert in der Spezifikation, ist aber nicht implementiert.
**Test Status:** Missing
**Remarks:** Abgeleitet von REQ-L1-036 (← REQ-L0-024, SN-24). Kritisch für CI/CD-Integration.

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
