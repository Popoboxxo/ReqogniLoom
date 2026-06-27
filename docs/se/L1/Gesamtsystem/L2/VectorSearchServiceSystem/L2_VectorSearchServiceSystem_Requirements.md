# L2 VectorSearchService Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** VectorSearchServiceSystem (NEU)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-27
> **Status:** formalisiert
> **Designation:** system (L3-Zerlegung erforderlich)

---

## Traceability

- Abgeleitet von: REQ-L1-038 (primär)
- Ziel: L3-Zerlegung in COMP-VS-001 (VectorSearchEngine), COMP-VS-002 (EmbeddingPipeline), COMP-VS-003 (HybridQueryRouter)

---

## Externe Schnittstellen (Systemgrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-VS-EXT-IN-001 | input | data | Suchanfrage vom ApplicationService (natürlichsprachlicher Query oder Artefakt-ID) |
| IF-VS-EXT-IN-002 | input | data | Domain-Event (ArtifactCreated/ArtifactUpdated) vom ApplicationService |
| IF-VS-EXT-OUT-001 | output | data | Embedding-Generierung an LlmAdapterSystem |
| IF-VS-EXT-OUT-002 | output | data | Persistenz an PersistenceLayer (pgvector-Extension) |

---

## Architekturentscheidung: Self-Hosted-Kompatibilität

**Entscheidung:** Die Vektorsuche wird auf **embedded pgvector** (PostgreSQL-Extension) implementiert. Kein externer Vektordatenbank-Service (Qdrant/Milvus).

**Rationale:** REQ-L1-018 (Self-Hosted Deployment) erfordert, dass alle Komponenten innerhalb eines einzelnen Deployment-Units laufen. pgvector ist eine PostgreSQL-Extension, die keine zusätzliche Infrastruktur benötigt. Die Performance-Anforderung (≤ 2s bei 10.000 Artefakten) ist mit pgvector und HNSW-Index erfüllbar.

**Abgelehnte Alternative:** Externer Qdrant-Service — abgelehnt, da dies die Deployment-Topologie verkompliziert und Self-Hosted-Betrieb erschwert.

---

## L2 Subsystem-Anforderungen

### REQ-L2-VS-001: Semantische Vektorsuche

Der VectorSearchService SHALL eine semantische, vektorbasierte Suche über alle Artefakttypen bereitstellen. Natürlichsprachliche Queries SHALL in einen Vektor eingebettet und gegen die gespeicherten Artefakt-Vektoren verglichen werden. Ergebnisse SHALL mit Ähnlichkeits-Score gerankt zurückgegeben werden. Query per Artefakt-ID SHALL semantisch ähnliche Artefakte als Duplikat-Vorschläge liefern.

**Domain:** software
**Priority:** optional
**arch_impact:** false
**Acceptance Criteria:**
- [ ] Natürlichsprachliche Query liefert rankierte Ergebnisse mit Ähnlichkeits-Score
- [ ] Query per Artefakt-ID liefert semantisch ähnliche Artefakte als Duplikat-Vorschläge
- [ ] Suchlatenz ≤ 2s für Workspaces mit bis zu 10.000 Artefakten
- [ ] Suche ist via REST-API und MCP-Tool (artifact.semantic_search) nutzbar
- [ ] Ergebnisse enthalten Artefakt-ID, Typ, Titel und Ähnlichkeits-Score

**Interfaces:**
- Incoming: IF-VS-EXT-IN-001
- Outgoing: IF-VS-EXT-OUT-002

**Traceability:** REQ-L1-038
**Rationale:** Semantische Suche identifiziert inhaltliche Ähnlichkeiten, die Volltextsuche nicht findet.

---

### REQ-L2-VS-002: Embedding-Pipeline

Der VectorSearchService SHALL bei jeder Artefakt-Erstellung und -Bearbeitung automatisch die Embeddings aktualisieren. Die Embedding-Generierung SHALL asynchron erfolgen (maximale Verzögerung 5 Minuten). Das Embedding-Modell SHALL über den LlmAdapter abstrahiert werden (Provider-agnostisch).

**Domain:** software
**Priority:** optional
**arch_impact:** false
**Acceptance Criteria:**
- [ ] Artefakt erstellt → Embedding innerhalb von 5 Minuten generiert und gespeichert
- [ ] Artefakt bearbeitet → Embedding innerhalb von 5 Minuten aktualisiert
- [ ] Embedding-Generierung erfolgt über LlmAdapter (Provider-agnostisch)
- [ ] Ausfall des Embedding-Services → Queue persistiert, nach Wiederanlauf verarbeitet
- [ ] Embedding-Dimension ist konfigurierbar (abhängig vom Modell)

**Interfaces:**
- Incoming: IF-VS-EXT-IN-002
- Outgoing: IF-VS-EXT-OUT-001, IF-VS-EXT-OUT-002

**Traceability:** REQ-L1-038
**Rationale:** Automatische Embedding-Aktualisierung gewährleistet aktuelle Suchergebnisse.

---

### REQ-L2-VS-003: Hybrid-Suche (Vektor + Volltext)

Der VectorSearchService SHALL eine Hybrid-Suche bereitstellen, die Vektor-Ähnlichkeit und Volltext-Suche kombiniert. Das Ranking SHALL beide Signalquellen fusionieren (Reciprocal Rank Fusion oder gewichtete Summe). Volltext-Treffer SHALL bei exakten Übereinstimmungen höher gewichtet werden.

**Domain:** software
**Priority:** optional
**arch_impact:** false
**Acceptance Criteria:**
- [ ] Hybrid-Suche kombiniert Vektor- und Volltext-Ergebnisse
- [ ] Ranking fusioniert beide Signalquellen (Reciprocal Rank Fusion)
- [ ] Exakte Volltext-Treffer werden höher gewichtet als semantische Ähnlichkeit
- [ ] Suchlatenz ≤ 2s für Workspaces mit bis zu 10.000 Artefakten
- [ ] Hybrid-Suche ist via UI-Suchfeld und MCP-Tool nutzbar

**Interfaces:**
- Incoming: IF-VS-EXT-IN-001
- Outgoing: IF-VS-EXT-OUT-002

**Traceability:** REQ-L1-038
**Rationale:** Hybrid-Suche kombiniert die Stärken beider Suchansätze für bessere Trefferqualität.

---

## Traceability-Matrix: REQ-L2-VS → REQ-L1

| REQ-L2-VS | Titel | REQ-L1 | Priorität |
|-----------|-------|--------|-----------|
| REQ-L2-VS-001 | Semantische Vektorsuche | REQ-L1-038 | optional |
| REQ-L2-VS-002 | Embedding-Pipeline | REQ-L1-038 | optional |
| REQ-L2-VS-003 | Hybrid-Suche | REQ-L1-038 | optional |

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade Phase 3 | 2026-06-27*
*Designation: system — decomposition_status: L3-Zerlegung erforderlich*
