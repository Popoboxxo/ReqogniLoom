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

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Geprüft von se-verifier. System ist noch nicht implementiert.

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

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Geprüft von se-verifier. System ist noch nicht implementiert.

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

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Geprüft von se-verifier. System ist noch nicht implementiert.

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

---

## Erweiterung v2 — Vollständige Requirement-Beschreibungen (REQ-L2-VS-001..003)

> **Datum:** 2026-06-28 | **Quelle:** REQ-L0-026 → REQ-L1-038

---

### REQ-L2-VS-001: Semantische Vektorsuche (RAG-Query)

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Geprüft von se-verifier. System ist noch nicht implementiert.

Der VectorSearchService MUSS eine semantische Suche über alle Anforderungen und
Artefakte eines Workspace ermöglichen. Suchanfragen werden als Text-Embedding
(via LlmAdapter) vektorisiert und gegen die Vektordatenbank abgeglichen.
Die Antwort enthält die Top-N ähnlichsten Artefakte mit Ähnlichkeitsscore.
AI-Agenten MÜSSEN diesen Endpunkt über die REST-API und den MCP-Server nutzen können.

**Schnittstellen:**
- `POST /workspaces/{id}/search/semantic` → `{ "query": "...", "top_n": 10, "threshold": 0.7 }`
- Response: `[ { "artefact_id": "...", "type": "requirement", "score": 0.92, "title": "..." } ]`
- Intern: `VectorSearchService.query(embedding, workspace_id, top_n)` → List[SearchResult]

**Akzeptanzkriterien:**
- AC1: Semantisch ähnliche Anforderungen werden trotz unterschiedlicher Wortwahl gefunden
- AC2: `threshold`-Parameter filtert Ergebnisse unterhalb Ähnlichkeitsschwelle
- AC3: Suchanfrage-Latenz < 500 ms (p95, Workspace bis 5.000 Artefakte)
- AC4: MCP-Server stellt `semantic_search`-Tool bereit (für AI-Agenten)
- AC5: Ergebnisse enthalten Typ-Information (requirement/architecture/testcase)

**Verifikationsmethode:** Integrationstest — bekannte semantisch ähnliche REQs, Recall-Messung
**Verifikiert durch:** L2-VS-Test-001
**Abgeleitet von:** REQ-L1-038
**Übergeordnete REQ-L0:** REQ-L0-026

---

### REQ-L2-VS-002: Embedding-Pipeline (Automatisches Vektorisieren bei Artefakt-Änderungen)

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Geprüft von se-verifier. System ist noch nicht implementiert.

Der VectorSearchService MUSS Artefakt-Änderungen (create/update) automatisch erkennen
und das Embedding des geänderten Artefakts asynchron aktualisieren.
Die Embedding-Erzeugung erfolgt über den LlmAdapter (REQ-L2-LLM-xxx).
Embeddings MÜSSEN in einer dedizierten Vektordatenbank (z. B. pgvector, Weaviate)
gespeichert werden. Eine initiale Batch-Indexierung MUSS beim Workspace-Import
oder auf Admin-Anfrage auslösbar sein.

**Schnittstellen:**
- Event-Consumer: `requirement.created`, `requirement.updated` → async Embedding-Update
- `POST /workspaces/{id}/vector-index/rebuild` → Admin-Trigger für Batch-Re-Indexierung
- Intern: `LlmAdapter.embed(text) → Vector[float]`

**Akzeptanzkriterien:**
- AC1: Neue Anforderung → Embedding in < 10 s aktualisiert (async, nicht blocking)
- AC2: Geänderte Anforderung → altes Embedding überschrieben
- AC3: Batch-Rebuild indexiert alle Artefakte eines Workspace ohne Timeout
- AC4: Embedding-Dimension konsistent mit verwendetem LLM-Modell

**Verifikationsmethode:** Integrationstest — Anforderung anlegen, Embedding-Status prüfen, Suche
**Verifikiert durch:** L2-VS-Test-002
**Abgeleitet von:** REQ-L1-038
**Übergeordnete REQ-L0:** REQ-L0-026

---

### REQ-L2-VS-003: Hybrid-Suche (Semantisch + Volltext kombiniert)

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Geprüft von se-verifier. System ist noch nicht implementiert.

Der VectorSearchService SOLL eine Hybrid-Suche anbieten, die semantische
Ähnlichkeit (Vektor-Cosine) mit klassischer Volltext-Suche (BM25/TF-IDF) kombiniert.
Der Gewichtungsfaktor (semantisch vs. Volltext) SOLL konfigurierbar sein.
Hybrid-Suche verbessert die Präzision bei Anfragen mit spezifischen Schlüsselbegriffen
(REQ-IDs, Abkürzungen), die rein semantisch schlecht gefunden werden.

**Schnittstellen:**
- `POST /workspaces/{id}/search/hybrid` → `{ "query": "...", "semantic_weight": 0.7, "text_weight": 0.3 }`
- Intern: Kombination von Vektor-Score und BM25-Score via Reciprocal Rank Fusion (RRF)

**Akzeptanzkriterien:**
- AC1: REQ-ID-Suche (`REQ-L1-003`) findet exakt die Anforderung (Volltext-Anteil)
- AC2: Semantische Umschreibung findet inhaltlich ähnliche Anforderung (Vektor-Anteil)
- AC3: Gewichtungsparameter beeinflusst Ranking nachweislich
- AC4: Latenz < 800 ms (p95)

**Verifikationsmethode:** Integrationstest — REQ-ID-Suche + semantische Suche, Ranking-Vergleich
**Verifikiert durch:** L2-VS-Test-003
**Abgeleitet von:** REQ-L1-038
**Übergeordnete REQ-L0:** REQ-L0-026

---

*Erweiterung durch se-requirements-Agent | 2026-06-28 (REQ-L2-VS-001..003 vollständig ausgearbeitet)*

---

### REQ-L2-VS-004: pgvector-Extension und Embedding-Datenmodell

Das System MUSS die PostgreSQL-Extension `pgvector` aktivieren und ein dediziertes Embedding-Feld auf dem `Requirement`-Modell bereitstellen. Bei Erstellung und Änderung einer Anforderung MUSS automatisch (asynchron via Celery) ein Embedding über den konfigurierten LLM-Adapter generiert und persistiert werden. Ein REST-Endpunkt für Ähnlichkeitssuche MUSS implementiert werden. Die Suche auf dem Mock-Adapter liefert einen definierten Fallback.

**Implementation State:** Not Implemented
**Review Findings:** Keine pgvector-Extension, kein Embedding-Feld, keine Ähnlichkeitssuche vorhanden. Nur deutschsprachige Volltextsuche auf Requirements implementiert.
**Test Status:** Missing
**Remarks:** Neu aufgenommen 2026-07-10. Konkretisierung der Implementierungsebene für REQ-L2-VS-001 und REQ-L2-VS-002.

**Domain:** software
**Priority:** could
**Acceptance Criteria:**
- [ ] `pgvector`-Extension ist in der Django-Migration aktiviert (`CREATE EXTENSION IF NOT EXISTS vector`)
- [ ] `Requirement.embedding` (VectorField, dimension=konfigurierbar, nullable) ist im Django-Modell vorhanden
- [ ] Celery-Task `generate_embedding` wird nach `requirement.created` und `requirement.updated` ausgelöst und speichert das Embedding via LLM-Adapter
- [ ] Mock-Adapter gibt Null-Vektor der korrekten Dimension zurück (kein Absturz ohne echten LLM)
- [ ] REST-Endpunkt `POST /workspaces/{id}/requirements/similar` nimmt `requirement_id` oder `query`-Text und gibt Top-N ähnlichste Anforderungen mit Ähnlichkeits-Score zurück
- [ ] HNSW-Index auf `Requirement.embedding` ist aktiv (Performance: p95 < 200 ms bei 10.000 Anforderungen)
- [ ] Integrationstest: Anforderung erstellen → Embedding generiert → Ähnlichkeitssuche findet semantisch ähnliche Anforderung

**Traceability:** REQ-L1-038
**Rationale:** REQ-L2-VS-001 und VS-002 definieren das Systemverhalten; REQ-L2-VS-004 konkretisiert die Datenmodell- und Infrastrukturebene, ohne die höherstufige Spezifikation zu ersetzen.


## Master Traceability Matrix

| REQ-L2 | Abgeleitet von REQ-L1 |
|---------|----------------------|
| REQ-L2-VS-001 | REQ-L1-038 |
| REQ-L2-VS-002 | REQ-L1-038 |
| REQ-L2-VS-003 | REQ-L1-038 |
| REQ-L2-VS-004 | REQ-L1-038 |

