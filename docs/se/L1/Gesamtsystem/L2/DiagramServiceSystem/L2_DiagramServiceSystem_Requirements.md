# L2 DiagramService Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** DiagramServiceSystem (ARCH-L1-013)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-21
> **Status:** formalisiert
> **Designation:** component (terminal — keine L3-Zerlegung)

---

## Traceability

- Abgeleitet von: REQ-L1-027 (primär)
- Mitwirkende L1-Anforderungen: REQ-L1-003 (Traceability), REQ-L1-011 (Audit), REQ-L1-015 (Tenant-Isolation), REQ-L1-026 (Performance), REQ-L1-036 (AuditLog-Interface)
- Ziel: terminal (keine L3-Zerlegung)

---

## Externe Schnittstellen (Systemgrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-DS-EXT-IN-001 | input | data | `create_diagram(type, payload, artifact_link?, ctx)` von ApplicationService (IF-L1-032) |
| IF-DS-EXT-IN-002 | input | data | `update_diagram(diagram_id, payload, ctx)` von ApplicationService (IF-L1-032) |
| IF-DS-EXT-IN-003 | input | data | `get_diagram(diagram_id, version?, ctx)` von ApplicationService (IF-L1-032) |
| IF-DS-EXT-IN-004 | input | data | `list_versions(diagram_id, ctx)` von ApplicationService (IF-L1-032) |
| IF-DS-EXT-IN-005 | input | data | `delete_diagram(diagram_id, ctx)` von ApplicationService (IF-L1-032) |
| IF-DS-EXT-IN-006 | input | data | `link_artifact(diagram_id, artifact_id, target_type, ctx)` von ApplicationService (IF-L1-032) — `target_type` unterscheidet `requirement` von `architecture_element`; Unterfunktion von IF-L1-032 |
| IF-DS-EXT-IN-007 | input | data | `unlink_artifact(diagram_id, artifact_id, ctx)` von ApplicationService (IF-L1-032) — Unterfunktion von IF-L1-032 |
| IF-DS-EXT-IN-008 | input | data | `artifact.get(artifact_type='diagram', artifact_id, ctx)` von McpServer (IF-L1-033) |
| IF-DS-EXT-OUT-001 | output | data | Diagram-Entity und DiagramVersion-Entity an PersistenceLayer (IF-L1-035) |
| IF-DS-EXT-OUT-002 | output | data | TraceLink `documents` zu TraceabilityEngine (IF-L1-034) |
| IF-DS-EXT-OUT-003 | output | event | Audit-Ereignisse (create/update/delete) an AuditLog (IF-L1-036) |

---

## L2 Subsystem-Anforderungen

### REQ-L2-DS-001: Unterstützung von mindestens 3 Diagramm-Typen

Das DiagramServiceSystem SHALL mindestens drei Diagramm-Typen unterstützen: Blockdiagramm (`block`), Flussdiagramm (`flow`) und Kontextdiagramm (`context`). Jeder Typ SHALL einen typspezifischen strukturierten Payload mit definiertem Schema akzeptieren.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Erstelle Diagramm mit `type=block` → Diagramm mit UUID persistiert
- [ ] Erstelle Diagramm mit `type=flow` → Diagramm mit UUID persistiert
- [ ] Erstelle Diagramm mit `type=context` → Diagramm mit UUID persistiert
- [ ] Erstelle Diagramm mit `type=unknown` → Fehler `"Unsupported diagram type"`
- [ ] Jeder Typ akzeptiert ausschließlich seinen typkonformen Payload

**Interfaces:**
- Incoming: IF-DS-EXT-IN-001
- Outgoing: IF-DS-EXT-OUT-001

**Traceability:** REQ-L1-027
**Rationale:** REQ-L1-027 fordert explizit mindestens 3 Typen; Typ-Schema schützt vor strukturell invaliden Diagrammen.

---

### REQ-L2-DS-002: Diagramm-Erstellung (Create)

Das DiagramServiceSystem SHALL ein neues Diagramm mit einem eindeutigen UUID, Typ, strukturiertem Payload, Erstell-Zeitstempel und initialer Version `1` erzeugen. Der Payload SHALL vor der Persistierung gegen das typspezifische Schema validiert werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `create_diagram(type, payload)` → Diagramm mit UUID, `version_number=1`, `created_at` vorhanden
- [ ] Valider Payload eines falschen Typs → Fehler `"Payload schema mismatch for type"`
- [ ] Fehlender Pflicht-Payload-Schlüssel → Fehler `"Payload validation failed: <key> required"`
- [ ] Erfolgreiche Erstellung gibt Diagramm-UUID zurück

**Interfaces:**
- Incoming: IF-DS-EXT-IN-001
- Outgoing: IF-DS-EXT-OUT-001

**Traceability:** REQ-L1-027
**Rationale:** Create ist die Basis-CRUD-Operation; Payload-Validierung bei Erstellung verhindert korrupte Daten.

---

### REQ-L2-DS-003: Diagramm-Lesen (Read)

Das DiagramServiceSystem SHALL ein Diagramm anhand seiner UUID abrufen. Ohne optionale Versionsnummer SHALL die aktuelle (neueste) Version zurückgegeben werden. Mit Versionsnummer SHALL exakt die angefragte Version zurückgegeben werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `get_diagram(diagram_id)` → aktuellste Version mit Payload, Typ, Versionsnummer, Zeitstempel
- [ ] `get_diagram(diagram_id, version=2)` → exakt Version 2
- [ ] `get_diagram(diagram_id, version=99)` (nicht existent) → Fehler `"Version not found"`
- [ ] `get_diagram(unknown_id)` → Fehler `"Diagram not found"`
- [ ] Cross-Tenant-Zugriff → Fehler `"Diagram not found"` (keine Tenant-Information im Fehlertext)

**Interfaces:**
- Incoming: IF-DS-EXT-IN-003
- Outgoing: IF-DS-EXT-OUT-001

**Traceability:** REQ-L1-027
**Rationale:** Lesezugriff mit expliziter Versionsnavigation ist Kernfunktion der Verwaltung.

---

### REQ-L2-DS-004: Diagramm-Aktualisierung mit immutabler Versionierung (Update)

Das DiagramServiceSystem SHALL bei jeder Aktualisierung eines Diagramms eine neue, unveränderliche Version erzeugen. Die vorherige Version SHALL unverändert erhalten bleiben. Die neue Versionsnummer SHALL monoton inkrementierend (previous + 1) sein.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `update_diagram(diagram_id, new_payload)` → neue Version mit `version_number = previous + 1`
- [ ] `get_diagram(diagram_id, version=1)` nach Update → gibt unverändert Version 1 zurück
- [ ] Ungültiger Payload beim Update → Fehler, keine neue Version erzeugt
- [ ] Parallele Updates auf demselben Diagramm → keine Versionsnummern-Kollision (atomare Inkrementierung)

**Interfaces:**
- Incoming: IF-DS-EXT-IN-002
- Outgoing: IF-DS-EXT-OUT-001

**Traceability:** REQ-L1-027
**Rationale:** REQ-L1-027 fordert explizit, dass jede Diagramm-Änderung eine neue Version erzeugt.

---

### REQ-L2-DS-005: Diagramm-Löschung (Delete)

Das DiagramServiceSystem SHALL ein Diagramm inkl. aller seiner Versionen löschen. Alle zugehörigen TraceLinks SHALL im Rahmen derselben atomaren Transaktion entfernt werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `delete_diagram(diagram_id)` → Diagramm und alle Versionen nicht mehr abrufbar
- [ ] `get_diagram(diagram_id)` nach Löschung → Fehler `"Diagram not found"`
- [ ] TraceLinks des gelöschten Diagramms → nicht mehr in TraceabilityEngine vorhanden
- [ ] Löschung und TraceLink-Entfernung in einer Transaktion (kein Inkonsistenz-Fenster)
- [ ] `delete_diagram(unknown_id)` → Fehler `"Diagram not found"`

**Interfaces:**
- Incoming: IF-DS-EXT-IN-005
- Outgoing: IF-DS-EXT-OUT-001, IF-DS-EXT-OUT-002

**Traceability:** REQ-L1-027, REQ-L1-003 (mitwirkend)
**Rationale:** Atomare Löschung verhindert orphaned TraceLinks.

---

### REQ-L2-DS-006: Payload-Validierung pro Diagramm-Typ

Das DiagramServiceSystem SHALL bei Create und Update den Payload gegen das typspezifische Schema validieren. Ein invalider Payload SHALL die Operation abbrechen und einen beschreibenden Fehler zurückgeben. Die Schema-Definitionen der unterstützten Typen SHALL erweiterbar sein, ohne bestehende Typen zu beeinflussen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Block-Diagramm mit fehlendem Pflicht-Element `nodes` → Fehler `"Payload validation failed: nodes required"`
- [ ] Fluss-Diagramm mit fehlendem `edges` → Fehler mit Feldname
- [ ] Kontext-Diagramm mit unbekanntem Feld → abhängig von Schema-Konfiguration (strict/lenient)
- [ ] Valider Payload → kein Validierungsfehler, Operation weitergeführt
- [ ] Neuer Diagramm-Typ kann hinzugefügt werden ohne bestehende Typ-Schemas zu modifizieren

**Interfaces:**
- Incoming: IF-DS-EXT-IN-001, IF-DS-EXT-IN-002
- Outgoing: IF-DS-EXT-OUT-001

**Traceability:** REQ-L1-027
**Rationale:** Typ-spezifische Validierung sichert strukturelle Integrität der Diagramm-Daten.

---

### REQ-L2-DS-007: Versions-Navigation (Versions-Liste und Versions-Abruf)

Das DiagramServiceSystem SHALL eine geordnete Liste aller Versionen eines Diagramms bereitstellen. Die Liste SHALL für jede Version mindestens Versionsnummer, Zeitstempel der Erstellung und Autor-Identität enthalten.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `list_versions(diagram_id)` → geordnete Liste [{version_number, created_at, created_by}, ...]
- [ ] Liste nach 3 Updates: enthält genau 4 Einträge (Version 1 bis 4)
- [ ] `list_versions(unknown_id)` → Fehler `"Diagram not found"`
- [ ] Versionen in aufsteigender Reihenfolge (älteste zuerst)

**Interfaces:**
- Incoming: IF-DS-EXT-IN-004
- Outgoing: IF-DS-EXT-OUT-001

**Traceability:** REQ-L1-027
**Rationale:** Versions-Navigation ist Kernfunktion der versionierten Verwaltung.

---

### REQ-L2-DS-008: Traceability-Verknüpfung mit Requirements und ArchitectureElements

Das DiagramServiceSystem SHALL Diagramme mit Requirements oder ArchitectureElements via TraceLink vom Typ `documents` verknüpfen und diese Verknüpfung aufheben können. Source und Target MÜSSEN demselben Tenant angehören.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `link_artifact(diagram_id, requirement_id, target_type='requirement')` → TraceLink `documents` in TraceabilityEngine angelegt
- [ ] `link_artifact(diagram_id, arch_element_id, target_type='architecture_element')` → TraceLink angelegt
- [ ] Cross-Tenant-Verknüpfung → Fehler `"Cross-tenant link not allowed"`
- [ ] `unlink_artifact(diagram_id, artifact_id)` → TraceLink entfernt
- [ ] Verknüpfung zu nicht-existentem Artefakt → Fehler `"Target artifact not found"`
- [ ] Ein Diagramm kann mit mehreren Artefakten verknüpft werden

**Interfaces:**
- Incoming: IF-DS-EXT-IN-006, IF-DS-EXT-IN-007
- Outgoing: IF-DS-EXT-OUT-002

**Traceability:** REQ-L1-027, REQ-L1-003 (mitwirkend)
**Rationale:** REQ-L1-027 fordert direkte Verknüpfung zu Requirements und ArchitectureElements.

---

### REQ-L2-DS-009: MCP-Zugriff auf Diagramm-Artefakte (artifact.get)

Das DiagramServiceSystem SHALL Diagramme über das MCP-Protokoll via `artifact.get` abrufbar machen. Die zurückgegebene Darstellung SHALL den strukturierten Payload der aktuellsten Version enthalten.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `artifact.get(artifact_type='diagram', artifact_id=<uuid>)` → Diagramm mit Typ, Payload, Versionsnummer
- [ ] MCP-Zugriff auf nicht-existentes Diagramm → Fehler `"Artifact not found"`
- [ ] Cross-Tenant-Zugriff via MCP → Fehler `"Artifact not found"`
- [ ] MCP-Antwort-Format JSON-serialisierbar und schema-konform

**Interfaces:**
- Incoming: IF-DS-EXT-IN-008
- Outgoing: IF-DS-EXT-OUT-001

**Traceability:** REQ-L1-027
**Rationale:** REQ-L1-027 fordert explizit MCP-Abrufbarkeit via `artifact.get`.

---

### REQ-L2-DS-010: Renderbare Darstellung je Diagramm-Typ

Das DiagramServiceSystem SHALL zu jedem Diagramm auf Anfrage eine renderbare Darstellung erzeugen. Die renderbare Repräsentation SHALL aus dem strukturierten Payload abgeleitet werden und für die UI nutzbar sein.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `get_diagram(diagram_id, render=true)` → enthält zusätzlich `rendered_output` (z.B. SVG, HTML oder strukturiertes Render-Format)
- [ ] Render-Ausgabe für alle 3 unterstützten Typen vorhanden
- [ ] Invalider Payload → Render schlägt fehl mit Fehler `"Render failed: <reason>"`
- [ ] Render-Ergebnis ist deterministisch (gleicher Payload → gleiche Ausgabe)

**Interfaces:**
- Incoming: IF-DS-EXT-IN-003
- Outgoing: IF-DS-EXT-OUT-001

**Traceability:** REQ-L1-027
**Rationale:** REQ-L1-027 fordert „renderbare Darstellung in UI".

---

### REQ-L2-DS-011: Diagramm-Audit-Metadaten

Jedes Diagramm und jede DiagramVersion SHALL Audit-Felder (`created_by`, `created_at`, `modified_by`, `modified_at`) besitzen. Für MCP-Operationen SHALL die Agent-Client-Identität erfasst werden.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Diagramm via REST erstellt → `created_by` = User-ID, `created_at` vorhanden
- [ ] Diagramm via MCP erstellt → `created_by` = Agent-Client-ID
- [ ] Update → neue Version mit `created_by` = aktueller Aufrufer; Diagramm-Entität: `modified_by`/`modified_at` aktualisiert
- [ ] `created_by`/`created_at` der ursprünglichen Erstellung bleiben unverändert

**Interfaces:**
- Incoming: IF-DS-EXT-IN-001, IF-DS-EXT-IN-002
- Outgoing: IF-DS-EXT-OUT-001, IF-DS-EXT-OUT-003

**Traceability:** REQ-L1-027, REQ-L1-011 (mitwirkend)
**Rationale:** Vollständige Nachvollziehbarkeit aller Änderungen; konsistent mit Audit-Anforderungen auf L1.

---

### REQ-L2-DS-012: Tenant-Isolation für alle Diagramm-Operationen

Das DiagramServiceSystem SHALL für alle Operationen sicherstellen, dass ausschließlich Diagramme des aktiven Tenants sichtbar und manipulierbar sind.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Tenant-1 erstellt Diagramm → `get_diagram` von Tenant-2 → Fehler `"Diagram not found"`
- [ ] `list_versions` von Tenant-2 auf Tenant-1-Diagramm → Fehler `"Diagram not found"`
- [ ] MCP `artifact.get` von Tenant-2 → Fehler `"Artifact not found"`
- [ ] Delete von Tenant-2 auf Tenant-1-Diagramm → Fehler `"Diagram not found"`
- [ ] Fehlertext enthält keine Tenant-Identifikation (kein Information-Leakage)

**Interfaces:**
- Incoming: IF-DS-EXT-IN-001, IF-DS-EXT-IN-002, IF-DS-EXT-IN-003, IF-DS-EXT-IN-004, IF-DS-EXT-IN-005, IF-DS-EXT-IN-006, IF-DS-EXT-IN-007, IF-DS-EXT-IN-008
- Outgoing: IF-DS-EXT-OUT-001

**Traceability:** REQ-L1-027, REQ-L1-015 (mitwirkend)
**Rationale:** Isolation über Tenant-Kontext in jeder Operation; konsistent mit Tenant-Isolation auf L1.

---

### REQ-L2-DS-013: Diagramm-Abruf-Performance-SLA

Das DiagramServiceSystem SHALL Lese-Operationen in ≤ 200ms (p95) und Schreib-Operationen (Create/Update) in ≤ 500ms (p95) bei bis zu 10.000 Diagrammen und 10.000 DiagramVersions im Workspace beantworten.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] `get_diagram` bei 10.000 Diagrammen → ≤ 200ms (p95)
- [ ] `list_versions` bei 10.000 Versionen → ≤ 200ms (p95)
- [ ] `create_diagram` inkl. Payload-Validierung → ≤ 500ms (p95)
- [ ] `update_diagram` inkl. Versionierung → ≤ 500ms (p95)
- [ ] Alle Lese-Operationen (get_diagram, list_versions) erfüllen das 200ms-p95-Ziel nachweislich bei der spezifizierten Last (Lasttest-Ergebnis dokumentiert)

**Interfaces:**
- Incoming: IF-DS-EXT-IN-001, IF-DS-EXT-IN-002, IF-DS-EXT-IN-003, IF-DS-EXT-IN-004
- Outgoing: IF-DS-EXT-OUT-001

**Traceability:** REQ-L1-027, REQ-L1-026 (mitwirkend)
**Rationale:** Performance-SLA analog zu anderen L2-Systemen; `desired` da REQ-L1-027 `desired` ist.

---

## Traceability-Matrix: REQ-L2-DS → REQ-L1

| REQ-L2-DS | Primäre REQ-L1 | Mitwirkende REQ-L1 |
|-----------|----------------|---------------------|
| REQ-L2-DS-001 | REQ-L1-027 | — |
| REQ-L2-DS-002 | REQ-L1-027 | — |
| REQ-L2-DS-003 | REQ-L1-027 | — |
| REQ-L2-DS-004 | REQ-L1-027 | — |
| REQ-L2-DS-005 | REQ-L1-027 | REQ-L1-003 |
| REQ-L2-DS-006 | REQ-L1-027 | — |
| REQ-L2-DS-007 | REQ-L1-027 | — |
| REQ-L2-DS-008 | REQ-L1-027 | REQ-L1-003 |
| REQ-L2-DS-009 | REQ-L1-027 | — |
| REQ-L2-DS-010 | REQ-L1-027 | — |
| REQ-L2-DS-011 | REQ-L1-027 | REQ-L1-011 |
| REQ-L2-DS-012 | REQ-L1-027 | REQ-L1-015 |
| REQ-L2-DS-013 | REQ-L1-027 | REQ-L1-026 |

---

## Zusammenfassung

| Metrik | Wert |
|--------|------|
| Anzahl REQ-L2-DS | 13 |
| Mandatory | 12 |
| Desired | 1 |
| Optional | 0 |
| Abgedeckte REQ-L1 (primär) | 1 (REQ-L1-027) |
| Abgedeckte REQ-L1 (mitwirkend) | 4 (REQ-L1-003, REQ-L1-011, REQ-L1-015, REQ-L1-026, REQ-L1-036) |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L1→L2 | 2026-06-21*
*Designation: component (terminal) — decomposition_status: terminal*
*Korrigiert durch se-critic-Agent (Iteration 1): IF-DS-EXT-IN-006 target_type-Parameter ergänzt; Unterfunktions-Hinweis auf IF-L1-032 für 006/007 dokumentiert; REQ-L2-DS-008 Acceptance Criteria auf target_type aktualisiert*
