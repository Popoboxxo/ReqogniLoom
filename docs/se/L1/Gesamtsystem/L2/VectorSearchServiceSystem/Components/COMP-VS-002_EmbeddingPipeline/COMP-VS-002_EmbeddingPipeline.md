---
component_id: COMP-VS-002
parent_requirement: REQ-L2-VS-002, REQ-L2-VS-004
parent_system: VectorSearchServiceSystem
designation: component
status: draft
timestamp: "2026-06-27T21:00:00Z"
---
# COMP-VS-002 — EmbeddingPipeline

## Verantwortlichkeit

Die EmbeddingPipeline generiert automatisch Embeddings bei Artefakt-Erstellung und -Bearbeitung. Sie konsumiert Domain-Events (ArtifactCreated/ArtifactUpdated) und ruft asynchron den LlmAdapter zur Embedding-Generierung auf. Maximale Verzögerung: 5 Minuten.

## Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-VS-EXT-IN-002 | eingehend | ApplicationService (Domain-Event) | `ArtifactCreated`/`ArtifactUpdated` Event |
| IF-VS-EXT-OUT-001 | ausgehend | LlmAdapterSystem | `embed(text) -> vector` |
| IF-VS-EXT-OUT-002 | ausgehend | PersistenceLayer | pgvector — Vektor speichern |

## Teststrategie

- Event-Test: Artefakt erstellt → Embedding innerhalb 5 Minuten generiert
- Update-Test: Artefakt bearbeitet → Embedding aktualisiert
- Ausfall-Test: Embedding-Service down → Queue persistiert, nach Wiederanlauf verarbeitet

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade Phase 3 | 2026-06-27*
