# L2 VectorSearchService Architecture

> **Level:** L2 (Subsystem white-box)
> **System:** VectorSearchServiceSystem
> **Parent:** L1_Gesamtsystem_Architecture.md
> **Datum:** 2026-07-12
> **Status:** entworfen

---

## 1. Verantwortlichkeit

Bereitstellung von semantischer Suche und Hybrid-Suche über alle Artefakte. Verwaltung der automatisierten Embedding-Erstellung (asynchron) bei Artefakt-Änderungen. Speicherung der Embeddings über pgvector.

---

## 2. White-Box (Komponenten-Zerlegung)

### Komponenten

| Komp-ID | Name | Verantwortlichkeit | Domain |
|---------|------|--------------------|--------|
| COMP-VS-001 | VectorSearchEngine | Führt Vektor-Queries gegen pgvector aus (HNSW-Index) und berechnet Top-N Ähnlichkeiten. Bietet REST und MCP Endpunkte (REQ-L2-VS-004). | software |
| COMP-VS-002 | EmbeddingPipeline | Empfängt Domain-Events (Celery-Tasks), ruft den LlmAdapter auf und persistiert Vektoren im `Requirement.embedding` Feld. | software |
| COMP-VS-003 | HybridQueryRouter | Kombiniert klassische BM25/Volltext-Suchen mit Vektor-Scores über Reciprocal Rank Fusion. | software |

---

## 3. Zugeordnete REQ-L2

| REQ-L2 | Komponente |
|--------|-----------|
| REQ-L2-VS-001 | COMP-VS-001 |
| REQ-L2-VS-002 | COMP-VS-002 |
| REQ-L2-VS-003 | COMP-VS-003 |
| REQ-L2-VS-004 | COMP-VS-001, COMP-VS-002 |

---

## 4. ADRs (lokal)

**ADR-VS-01 — pgvector für Vektorsuche**
*Entscheidung:* Verwendung von pgvector als PostgreSQL-Erweiterung statt einer dedizierten Vektordatenbank (REQ-L2-VS-004).
*Rationale:* Reduziert die Komplexität im Self-Hosted-Deployment.
