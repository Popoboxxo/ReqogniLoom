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
