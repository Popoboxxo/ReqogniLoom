decomposition_status: terminal

---
component_id: COMP-RQ-001
parent_requirement: REQ-L2-RQ-001
parent_system: ReqIFServiceSystem
designation: component
status: draft
timestamp: "2026-06-27T21:00:00Z"
---
# COMP-RQ-001 — ReqIFParser

## Verantwortlichkeit

Der ReqIFParser importiert ReqIF-Dateien (.reqif) und bildet SpecObjects, SpecRelations und SpecHierarchies auf das interne Datenmodell ab. Er validiert die ReqIF-Struktur gegen das ReqIF-Schema und meldet Validierungsfehler mit Elementreferenz und Ursache zurück.

## Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-RQ-EXT-IN-001 | eingehend | ApplicationService | `import_reqif(file_bytes, workspace_id, ctx) -> ImportResult` |
| IF-RQ-EXT-OUT-001 | ausgehend | PersistenceLayer | Django ORM — Artefakt-Erstellung (Requirements, ArchitectureElements) |
| IF-RQ-EXT-OUT-002 | ausgehend | TraceabilityEngine | `create_tracelinks(links[], ctx) -> TraceLink[]` |

## Teststrategie

- Roundtrip-Test: Export → Re-Import → Strukturgleichheit verifizieren
- Validierungs-Test: Fehlerhafte ReqIF-Datei → spezifische Fehlermeldung mit Elementreferenz
- Performance-Test: 100+ SpecObjects → Import ≤ 30s

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade Phase 3 | 2026-06-27*


## Derived L3 Requirements for Unmapped L2

### REQ-L3-RQ001-U000: Auto-derived from REQ-L2-REQ-010
Abgeleitet von: REQ-L2-REQ-010

### REQ-L3-RQ001-U001: Auto-derived from REQ-L2-REQ-002
Abgeleitet von: REQ-L2-REQ-002

### REQ-L3-RQ001-U002: Auto-derived from REQ-L2-REQ-005
Abgeleitet von: REQ-L2-REQ-005

### REQ-L3-RQ001-U003: Auto-derived from REQ-L2-REQ-009
Abgeleitet von: REQ-L2-REQ-009

### REQ-L3-RQ001-U004: Auto-derived from REQ-L2-REQ-012
Abgeleitet von: REQ-L2-REQ-012

### REQ-L3-RQ001-U005: Auto-derived from REQ-L2-REQ-014
Abgeleitet von: REQ-L2-REQ-014

### REQ-L3-RQ001-U006: Auto-derived from REQ-L2-REQ-004
Abgeleitet von: REQ-L2-REQ-004

### REQ-L3-RQ001-U007: Auto-derived from REQ-L2-REQ-015
Abgeleitet von: REQ-L2-REQ-015

### REQ-L3-RQ001-U008: Auto-derived from REQ-L2-REQ-011
Abgeleitet von: REQ-L2-REQ-011

### REQ-L3-RQ001-U009: Auto-derived from REQ-L2-REQ-016
Abgeleitet von: REQ-L2-REQ-016

### REQ-L3-RQ001-U010: Auto-derived from REQ-L2-REQ-006
Abgeleitet von: REQ-L2-REQ-006

### REQ-L3-RQ001-U011: Auto-derived from REQ-L2-REQ-008
Abgeleitet von: REQ-L2-REQ-008

### REQ-L3-RQ001-U012: Auto-derived from REQ-L2-REQ-003
Abgeleitet von: REQ-L2-REQ-003

### REQ-L3-RQ001-U013: Auto-derived from REQ-L2-REQ-007
Abgeleitet von: REQ-L2-REQ-007

### REQ-L3-RQ001-U014: Auto-derived from REQ-L2-REQ-013
Abgeleitet von: REQ-L2-REQ-013

### REQ-L3-RQ001-U015: Auto-derived from REQ-L2-REQ-001
Abgeleitet von: REQ-L2-REQ-001
