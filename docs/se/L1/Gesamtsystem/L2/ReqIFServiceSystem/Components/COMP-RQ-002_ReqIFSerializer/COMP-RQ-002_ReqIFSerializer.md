---
component_id: COMP-RQ-002
parent_requirement: REQ-L2-RQ-002
parent_system: ReqIFServiceSystem
designation: component
status: draft
timestamp: "2026-06-27T21:00:00Z"
---
# COMP-RQ-002 — ReqIFSerializer

## Verantwortlichkeit

Der ReqIFSerializer exportiert interne Artefakte (Requirements, ArchitectureElements, TraceLinks, Hierarchien) als ReqIF-Datei. Er bildet das interne Datenmodell auf SpecObjects, SpecRelations und SpecHierarchies ab und gewährleistet Roundtrip-Treue.

## Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-RQ-EXT-IN-001 | eingehend | ApplicationService | `export_reqif(workspace_id, ctx) -> file_bytes` |
| IF-RQ-EXT-OUT-001 | ausgehend | PersistenceLayer | Django ORM — Artefakt-Lesezugriff |
| IF-RQ-EXT-OUT-002 | ausgehend | TraceabilityEngine | `query_tracelinks(workspace_id, ctx) -> TraceLink[]` |

## Teststrategie

- Roundtrip-Test: Export → Re-Import → Strukturgleichheit verifizieren
- Schema-Validierung: Exportierte ReqIF-Datei valide gegen ReqIF-Schema
- Performance-Test: 100+ Artefakte → Export ≤ 10s

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade Phase 3 | 2026-06-27*
