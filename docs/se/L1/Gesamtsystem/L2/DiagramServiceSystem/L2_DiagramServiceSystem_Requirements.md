# L2 DiagramService Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** DiagramServiceSystem (ARCH-L1-013)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-21
> **Status:** formalisiert
> **Designation:** component (terminal — keine L3-Zerlegung)
> **decomposition_status:** terminal

---

## Traceability

- Abgeleitet von: REQ-L1-027 (primär)
- Ziel: terminal (keine L3-Zerlegung)

---

## Systemzweck

Das DiagramServiceSystem ist für die Verwaltung von Diagrammen als eigenständige, versionierte Artefakte zuständig. Es ermöglicht die Speicherung, Validierung (z.B. Mermaid, PlantUML) und das Rendern grafischer Modelle. Es stellt eine nahtlose Integration mit der TraceabilityEngine her, um Diagramme mit Requirements und ArchitectureElements über den Link-Typ `documents` zu verknüpfen.

---

## Externe Schnittstellen (Systemgrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-L1-032 | input | control | `create_diagram`, `update_diagram`, `get_diagram`, `list_versions` vom ApplicationService (ARCH-L1-004) |
| IF-L1-033 | input | control | `artifact.get` für Diagramm-Artefakttyp vom McpServer (ARCH-L1-003) |
| IF-L1-034 | output | data | TraceLink `documents` zwischen Diagramm und Requirement/ArchitectureElement an TraceabilityEngine (ARCH-L1-007) |
| IF-L1-035 | output | data | Diagram-Entity, DiagramVersion-Entity an PersistenceLayer (ARCH-L1-010) |
| IF-L1-036 | output | data | Schreib-Operationen an AuditLog (ARCH-L1-012, via ApplicationService delegiert) |

---

## L2 Subsystem-Anforderungen

### REQ-L2-DS-001: Diagramm CRUD und Versionierung
Das DiagramServiceSystem SHALL vollständiges CRUD für Diagramm-Artefakte bereitstellen, wobei jede inhaltliche Änderung zwingend eine neue, unveränderliche Version (DiagramVersion) erzeugt.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] Erstellen eines Diagramms liefert UUID und Version 1.
- [ ] Update eines Diagramms erzeugt Version N+1, vorherige Version bleibt unverändert abrufbar.
- [ ] Abruf der Historie listet alle Versionen mit Zeitstempel.

**Interfaces:**
- Incoming: IF-L1-032, IF-L1-033
- Outgoing: IF-L1-035, IF-L1-036


**Traceability:** REQ-L1-027
**Rationale:** Unveränderliche Versionen sind notwendig für Auditierbarkeit und Nachverfolgbarkeit von Architekturänderungen.

---

### REQ-L2-DS-002: Strukturierte Payload-Validierung
Das DiagramServiceSystem SHALL den Payload der Diagramme gegen typspezifische Regeln (z.B. Syntax von Mermaid oder PlantUML) validieren. Unterstützt werden MÜSSEN mindestens 3 Typen: Blockdiagramm, Flussdiagramm, Kontextdiagramm.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] Invalider Mermaid-Syntax wird mit aussagekräftiger Fehlermeldung abgelehnt.
- [ ] Mindestens Blockdiagramm, Flussdiagramm und Kontextdiagramm werden als Typen unterstützt.

**Interfaces:**
- Incoming: IF-L1-032


**Traceability:** REQ-L1-027
**Rationale:** Nur validierter Payload stellt sicher, dass Diagramme fehlerfrei im Frontend gerendert werden können.

---

### REQ-L2-DS-003: Renderbare Repräsentation
Das DiagramServiceSystem SHALL renderbare Repräsentationen (oder den rohen, validierten String) bereitstellen, die das Frontend zur grafischen Darstellung nutzen kann.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] API-Antwort enthält alle notwendigen Informationen, um das Diagramm in der UI zu rendern.

**Interfaces:**
- Incoming: IF-L1-032


**Traceability:** REQ-L1-027
**Rationale:** Die primäre Nutzung der Diagramme erfolgt visuell in der UI.

---

### REQ-L2-DS-004: Traceability-Verknüpfung (Typ: documents)
Das DiagramServiceSystem SHALL bei der Erstellung oder Aktualisierung von Diagrammen die Möglichkeit bieten, diese mit Requirements oder ArchitectureElements über den Link-Typ `documents` zu verknüpfen.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] Diagramm kann an Requirement-ID gebunden werden.
- [ ] Es wird ein TraceLink vom Typ `documents` in der TraceabilityEngine angelegt.

**Interfaces:**
- Incoming: IF-L1-032
- Outgoing: IF-L1-034


**Traceability:** REQ-L1-027
**Rationale:** Traceability schließt die Lücke zwischen grafischem Modell und textueller Anforderung.

---

### REQ-L2-DS-005: MCP-Tool Integration
Das DiagramServiceSystem SHALL den Diagramm-Abruf über das MCP-Tool `artifact.get` unterstützen, um KI-Agenten direkten Zugriff auf Diagramminhalte zu ermöglichen.

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] MCP-Call `artifact.get` mit Diagramm-ID liefert den strukturierten Diagramm-Payload.

**Interfaces:**
- Incoming: IF-L1-033


**Traceability:** REQ-L1-027
**Rationale:** KI-Agenten müssen architektonischen Kontext aus Diagrammen extrahieren können.

---

## Traceability-Matrix: REQ-L2-DS → REQ-L1

| REQ-L2-DS | Primäre REQ-L1 | Mitwirkende REQ-L1 |
|-----------|----------------|---------------------|
| REQ-L2-DS-001 | REQ-L1-027 | — |
| REQ-L2-DS-002 | REQ-L1-027 | — |
| REQ-L2-DS-003 | REQ-L1-027 | — |
| REQ-L2-DS-004 | REQ-L1-027 | — |
| REQ-L2-DS-005 | REQ-L1-027 | — |

---

## Zusammenfassung

| Metrik | Wert |
|--------|------|
| Anzahl REQ-L2-DS | 5 |
| Mandatory | 0 |
| Desired | 5 |
| Optional | 0 |
| Abgedeckte REQ-L1 (primär) | 1 (REQ-L1-027) |
| Abgedeckte REQ-L1 (mitwirkend) | 0 |
| Referenzierte Interfaces | IF-L1-032..IF-L1-036 (alle 5) |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L1→L2 | 2026-06-21*
*Handoff: HOFF-20260621-002 | Parent: REQ-L1-027 | Architektur-Referenz: ARCH-L1-013*
*Designation: component (terminal) — decomposition_status: terminal*
