---
component_id: COMP-VS-003
parent_requirement: REQ-L2-VS-003
parent_system: VectorSearchServiceSystem
designation: component
status: draft
timestamp: "2026-06-27T21:00:00Z"
---
# COMP-VS-003 — HybridQueryRouter

## Verantwortlichkeit

Der HybridQueryRouter kombiniert Vektor-Ähnlichkeit und Volltext-Suche zu einer Hybrid-Suche. Er fusioniert beide Signalquellen mittels Reciprocal Rank Fusion und gewichtet exakte Volltext-Treffer höher als semantische Ähnlichkeit.

## Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-VS-EXT-IN-001 | eingehend | ApplicationService | `hybrid_search(query, workspace_id, ctx) -> RankedResults` |
| IF-VS-EXT-OUT-002 | ausgehend | PersistenceLayer | pgvector-Query + Volltext-Query |

## Teststrategie

- Hybrid-Test: Query → kombinierte Ergebnisse aus Vektor + Volltext
- Ranking-Test: Exakter Volltext-Treffer → höher gerankt als semantische Ähnlichkeit
- Performance-Test: 10.000 Artefakte → Suchlatenz ≤ 2s

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade Phase 3 | 2026-06-27*
