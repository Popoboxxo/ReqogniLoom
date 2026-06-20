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
| IF-MC-EXT-OUT-004 | output | ARCH-L1-008 | data | Preset-Abfrage |

---

## L2 Subsystem-Anforderungen

### REQ-L2-MC-001: Requirements-Tool-Gruppe (6 Tools)

Der McpServer SHALL die sechs Tools `requirement.get`, `requirement.query`, `requirement.create`, `requirement.update`, `requirement.decompose` und `requirement.validate` implementieren. Jedes Tool SHALL seine Eingabeparameter gegen ein JSON-Schema validieren und die Operation an den ApplicationService delegieren. `requirement.validate` SHALL nur bei konfiguriertem LLM-Provider ausführbar sein; ohne LLM SOLL ein strukturierter Fehler `LLM_NOT_CONFIGURED` zurückgegeben werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Alle 6 Tools via MCP-Protokoll aufrufbar mit korrekt serialisierten Ergebnissen
- [ ] `requirement.get(id)` liefert Requirement mit Traces, Workflow-History und Audit-Feldern
- [ ] `requirement.validate(id)` ohne LLM-Config → Fehler `LLM_NOT_CONFIGURED`
- [ ] `requirement.decompose(id)` ohne LLM-Config → Fehler `LLM_NOT_CONFIGURED`
- [ ] Schreibende Operationen erzeugen AuditLog-Eintrag mit Agent-Identität und API-Key

**Interfaces:**
- Incoming: IF-MC-EXT-IN-001 (MCP-Tool-Aufruf `requirement.*`)
- Outgoing: IF-MC-EXT-OUT-001 (JSON-Response)
- Internal: IF-MC-EXT-OUT-003

**Traceability:** REQ-L1-005, REQ-L1-002 (mitwirkend), REQ-L1-011 (mitwirkend), REQ-L1-013 (mitwirkend)
**Rationale:** Die sechs Requirements-Tools decken den primären AI-Workflow ab.

---

### REQ-L2-MC-002: Architecture-Tool-Gruppe (5 Tools)

Der McpServer SHALL die fünf Tools `architecture.get`, `architecture.query`, `architecture.create`, `architecture.update` und `architecture.link` implementieren. `architecture.link` SHALL das Verknüpfen eines ArchitectureElements mit einem Requirement, TestCase oder ArchitectureElement unter Angabe des Link-Typs unterstützen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Alle 5 Tools via MCP-Protokoll aufrufbar
- [ ] `architecture.create(title, description, element_type, workspace_id)` → ArchitectureElement mit UUID
- [ ] `architecture.link(arch_id, target_id, target_type, link_type)` → TraceLink mit validem Link-Typ
- [ ] Schreibende Operationen erzeugen AuditLog-Einträge

**Interfaces:**
- Incoming: IF-MC-EXT-IN-001
- Outgoing: IF-MC-EXT-OUT-001
- Internal: IF-MC-EXT-OUT-003

**Traceability:** REQ-L1-005, REQ-L1-004 (mitwirkend), REQ-L1-003 (mitwirkend), REQ-L1-011 (mitwirkend)
**Rationale:** Architektur-Tools ermöglichen AI-Agenten strukturierte Architektur-Verwaltung.

---

### REQ-L2-MC-003: Test-Tool-Gruppe (5 Tools)

Der McpServer SHALL die fünf Tools `test.get`, `test.query`, `test.create`, `test.update` und `test.link` implementieren. `test.update` SHALL das Schreiben des Test-Status (Passed/Failed/Not Run) ermöglichen. `test.link` SHALL nachträgliche TraceLink-Erzeugung vom Typ `verifies` unterstützen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Alle 5 Tools via MCP-Protokoll aufrufbar
- [ ] `test.create(title, type, linked_req_id)` → TestCase und optional TraceLink `verifies`
- [ ] `test.update(id, {status: "Passed"})` → Test-Status aktualisiert
- [ ] `test.link(test_id, req_id)` → TraceLink `verifies` erzeugt
- [ ] AuditLog-Einträge für alle schreibenden Operationen

**Interfaces:**
- Incoming: IF-MC-EXT-IN-001
- Outgoing: IF-MC-EXT-OUT-001
- Internal: IF-MC-EXT-OUT-003

**Traceability:** REQ-L1-005, REQ-L1-012 (mitwirkend), REQ-L1-003 (mitwirkend), REQ-L1-011 (mitwirkend)
**Rationale:** Test-Tools ermöglichen automatisierte Coverage-Analyse als AI-Workflow.

---

### REQ-L2-MC-004: Übergreifende Tools (4 Tools)

Der McpServer SHALL die vier Tools `traceability.query`, `artifact.search`, `artifact.get_tree` und `workspace.get_context` implementieren. `workspace.get_context` SHALL den kompletten Workspace-Status zurückgeben und als Orientierungspunkt für AI-Agenten beim Sitzungsstart dienen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `traceability.query(artifact_id, direction)` → Upstream/Downstream-Graph mit Link-Typ-Annotation
- [ ] `artifact.search(query)` → gemischte Ergebnisliste über alle Artefakttypen
- [ ] `artifact.get_tree(root_id)` → hierarchische Artefakt-Struktur
- [ ] `workspace.get_context()` → Preset, Terminologie-Profil, Coverage-Summary, offene Requirements
- [ ] Alle 4 Tools funktionieren ohne LLM-Konfiguration

**Interfaces:**
- Incoming: IF-MC-EXT-IN-001
- Outgoing: IF-MC-EXT-OUT-001
- Internal: IF-MC-EXT-OUT-003

**Traceability:** REQ-L1-005, REQ-L1-020 (mitwirkend), REQ-L1-003 (mitwirkend), REQ-L1-007 (mitwirkend)
**Rationale:** Übergreifende Tools vermeiden redundante Einzel-Calls.

---

### REQ-L2-MC-005: MCP-Transportprotokoll-Unterstützung

Der McpServer SHALL mindestens drei Transportprotokolle unterstützen: stdio, Server-Sent Events (SSE) und HTTP. Der Transport SHALL für die Tool-Handler transparent sein.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] MCP-Tool-Aufrufe über stdio korrekt dispatcht und beantwortet
- [ ] MCP-Tool-Aufrufe über SSE korrekt dispatcht und beantwortet
- [ ] MCP-Tool-Aufrufe über HTTP korrekt dispatcht und beantwortet
- [ ] Handler kennen nur den Dispatch-Contract, nicht das Transportprotokoll

**Interfaces:**
- Incoming: IF-MC-EXT-IN-001
- Outgoing: IF-MC-EXT-OUT-001

**Traceability:** REQ-L1-005
**Rationale:** Verschiedene AI-Agent-Clients verwenden unterschiedliche Transportmechanismen.

---

### REQ-L2-MC-006: API-Key-Authentifizierung

Der McpServer SHALL vor jeder Tool-Ausführung den API-Key an AuthAndTenancy (ARCH-L1-011) zur Validierung weiterleiten. Bei ungültigem oder fehlendem API-Key SHALL die Anfrage mit Fehler `AUTH_FAILED` abgelehnt werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Tool-Aufruf ohne API-Key → Fehler `AUTH_FAILED`
- [ ] Tool-Aufruf mit ungültigem API-Key → Fehler `AUTH_FAILED`
- [ ] Tool-Aufruf mit gültigem API-Key → Auth-Kontext wird verwendet
- [ ] API-Key wird nicht an ApplicationService weitergegeben

**Interfaces:**
- Incoming: IF-MC-EXT-IN-001 (API-Key)
- Outgoing: IF-MC-EXT-OUT-001 (Fehler bei Auth-Fehler)
- Internal: IF-MC-EXT-OUT-002

**Traceability:** REQ-L1-005, REQ-L1-010 (mitwirkend), REQ-L1-011 (mitwirkend)
**Rationale:** API-Key-Auth ist Voraussetzung für sicheren MCP-Schreibzugriff.

---

### REQ-L2-MC-007: RBAC für MCP-Operationen

Der McpServer SHALL vor jeder schreibenden Operation prüfen, ob die Rolle des authentifizierten Nutzers die Operation erlaubt. Bei unzureichenden Berechtigungen SHALL die Anfrage mit Fehler `PERMISSION_DENIED` abgelehnt werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `requirement.create` durch Viewer → Fehler `PERMISSION_DENIED`
- [ ] `requirement.create` durch Editor → erfolgreich
- [ ] Lese-Operationen liefern nur Daten des aktiven Tenants

**Interfaces:**
- Incoming: IF-MC-EXT-OUT-002 (Auth-Kontext mit Rollen)
- Outgoing: IF-MC-EXT-OUT-001 (Fehler bei Berechtigungsverletzung)

**Traceability:** REQ-L1-010, REQ-L1-005 (mitwirkend)
**Rationale:** RBAC-Enforcement verhindert unautorisierte Operationen durch AI-Agenten.

---

### REQ-L2-MC-008: Preset-basierte Tool-Sichtbarkeit

Der McpServer SHALL das Preset des aktiven Workspaces über PresetConfigEngine (ARCH-L1-008) abfragen. Tools, die im aktiven Preset nicht aktiviert sind, SHALL mit Fehler `FEATURE_NOT_ENABLED` abgelehnt oder nicht registriert werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Minimal-Preset: Nur freigegebene Tools sichtbar/aufrufbar
- [ ] Extended-Preset: Alle 20 Tools sichtbar/aufrufbar
- [ ] Aufruf eines deaktivierten Tools → Fehler `FEATURE_NOT_ENABLED`

**Interfaces:**
- Incoming: IF-MC-EXT-OUT-004 (Preset-Regeln)
- Outgoing: IF-MC-EXT-OUT-001 (Fehler bei deaktiviertem Feature)

**Traceability:** REQ-L1-007, REQ-L1-005 (mitwirkend)
**Rationale:** Configurable Rigor erfordert werkzeugseitige SE-Tiefe-Abbildung.

---

### REQ-L2-MC-009: Direkter ApplicationService-Zugriff (keine REST-Umleitung)

Der McpServer SHALL alle Domain-Operationen direkt über den ApplicationService (ARCH-L1-004) via In-Process-Python ausführen. KEINE HTTP-Roundtrips über die REST-API. Der McpServer SHALL denselben Domain-Kontrakt verwenden wie der RestApiAdapter.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] MCP-Tool-Aufruf ruft direkt ApplicationService-Methoden auf — kein HTTP
- [ ] MCP-Responses semantisch identisch mit REST-Responses für dieselben Operationen
- [ ] MCP-spezifische Audit-Felder ohne REST-Adapter

**Interfaces:**
- Internal: IF-MC-EXT-OUT-003

**Traceability:** REQ-L1-005, REQ-L1-006 (mitwirkend)
**Rationale:** ADR-01: Vermeidet HTTP-Roundtrip-Overhead und garantiert semantische Konsistenz.

---

### REQ-L2-MC-010: MCP-Performance-Anforderung

Der McpServer SHALL für 95% aller MCP-Standard-Requests eine Gesamtantwortzeit von unter 200ms garantieren — unter der Lastannahme von bis zu 50 gleichzeitigen Agenten und 10.000 Requirements. Exklusive externer LLM-Aufrufe.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] Lasttest: 50 gleichzeitige MCP-Clients → p95 < 200ms für Standard-Queries
- [ ] Schreiboperationen < 200ms (p95) exklusive AuditLog-Persistenz
- [ ] `workspace.get_context` < 500ms (p95) bei 10.000 Items

**Interfaces:**
- Incoming: IF-MC-EXT-IN-001 (unter Last)
- Outgoing: IF-MC-EXT-OUT-001 (innerhalb SLA)

**Traceability:** REQ-L1-026, REQ-L1-005 (mitwirkend)
**Rationale:** Hohe Latenz beeinträchtigt alle AI-gestützten Workflows.

---

### REQ-L2-MC-011: Strukturierter Fehler-Response

Der McpServer SHALL bei Fehlern eine strukturierte JSON-Fehlerantwort zurückgeben mit: `error_code` (maschinenlesbar), `message` (menschenlesbar, i18n-fähig) und `details` (optional).

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] Auth-Fehler → `{"error_code": "AUTH_FAILED", "message": "..."}`
- [ ] LLM-Fehler → `{"error_code": "LLM_NOT_CONFIGURED", "message": "..."}`
- [ ] Berechtigungsverletzung → `{"error_code": "PERMISSION_DENIED", "message": "..."}`
- [ ] Validierungsfehler → `{"error_code": "VALIDATION_ERROR", "message": "...", "details": {...}}`

**Interfaces:**
- Outgoing: IF-MC-EXT-OUT-001

**Traceability:** REQ-L1-005
**Rationale:** AI-Agenten benötigen maschinenlesbare Fehlercodes für robuste Workflows.

---

### REQ-L2-MC-012: Vollständiger MCP-Audit-Trail

Der McpServer SHALL bei jeder schreibenden Operation über den ApplicationService (ARCH-L1-004) einen AuditLog-Eintrag erzeugen mit: Agent-Client-Identität, API-Key-Hash, Tool-Name, Operation, Entitäts-ID(s) und Zeitstempel. Der Eintrag SHALL synchron vor der Response geschrieben werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Nach `requirement.create`: AuditLog enthält Agent-User-ID, API-Key-Hash, Tool-Name, UUID
- [ ] Nach `architecture.link`: AuditLog enthält TraceLink-ID
- [ ] Lese-Operationen erzeugen KEINEN AuditLog-Eintrag
- [ ] AuditLog-Eintrag vorhanden bevor Response gesendet wird

**Interfaces:**
- Internal: IF-MC-EXT-OUT-003

**Traceability:** REQ-L1-011, REQ-L1-005 (mitwirkend)
**Rationale:** Vollständige Rückverfolgbarkeit von AI-Agent-Änderungen. AuditLog wird ausschließlich durch ApplicationService geschrieben (L1-Architektur ADR-01).

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

---

## Zusammenfassung

| Metrik | Wert |
|--------|------|
| Anzahl REQ-L2-MC | 12 |
| Mandatory | 10 |
| Desired | 2 |
| Optional | 0 |
| Abgedeckte REQ-L1 (primär) | REQ-L1-005, REQ-L1-010, REQ-L1-011, REQ-L1-026, REQ-L1-007 |
| Abgedeckte REQ-L1 (mitwirkend) | REQ-L1-002, REQ-L1-003, REQ-L1-004, REQ-L1-006, REQ-L1-012, REQ-L1-013, REQ-L1-020 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L1→L2 | 2026-06-20*
*Complete Rewrite: ID-Migration REQ-L2-Mcp → REQ-L2-MC, Template-Standardisierung*
*Designation: LEAF (terminal, keine L3-Zerlegung)*
