---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T14:45:00Z"
schema_version: "1.0.0"
---
# L3 SearchService Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-AS-010_SearchService
> **Parent:** L2_ApplicationServiceSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Der SearchService führt Volltextsuchen über alle Artefakt-Typen (Requirements, ArchitectureElements, TestCases) durch. Er nutzt PostgreSQL Full-Text-Search (tsvector/tsquery) für performante Recherche über title, description und tags. Ergebnisse sind relevanz-sortiert (ts_rank) und optional gefiltert nach Artefakttyp, Workspace und Tenant. Pagination unterstützt große Ergebnismengen. Suchergebnisse sind mit Artefakttyp annotiert.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`SearchService` (Klasse):** Orchestrator für Suchen (`search(query, type_filter[], workspace_id, page, limit, auth_context) → SearchResult`).
  - Parst Query in tsquery (SQL-Injection-sicher)
  - Validiert type_filter und workspace_id
  - Baut SQL-Query mit tsvector-Matching und Relevanz-Ranking
  - Implementiert Pagination (OFFSET/LIMIT)
  - Annotiert Ergebnisse mit artifact_type
  - Behandelt Fehler (ungültige tsquery, Timeout)

- **`QueryParser` (Klasse):** Parst Benutzereingabe in PostgreSQL tsquery:
  - Einfache Operatoren: AND (&), OR (|), NOT (!)
  - Präfixsuche: `prefix*` → `prefix:*` in tsquery
  - Phrasensuch mit Anführungszeichen: `"exact phrase"` → phrase-Matching

- **`SearchResult` (DTO):** results (list of {id, artifact_type, title, description, relevance_score}), total_count, page, limit.

- **`SearchException` (Exception):** Für ungültige tsquery oder DB-Timeout.

### 2.2 Datenstrukturen

- **tsvector-Spalten (in DB):** Für jede Entity-Typ: Spalte mit tsvector, die title + description + tags kombiniert. Mit GIN-Index für Performance.

- **Trigger (PostgreSQL):** Automatische Aktualisierung von tsvector-Spalten bei INSERT/UPDATE.

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-SEARCH-001 (PostgreSQL FTS Setup) | Migrations-Datei erstellt tsvector-Spalten für Requirements, ArchitectureElements, TestCases. Deutsch-Lexikon (ts_dict) konfiguriert für Stemming. GIN-Index auf tsvector-Spalten. Trigger (PostgreSQL) aktualisiert tsvector automatisch bei INSERT/UPDATE. |
| REQ-L3-SEARCH-002 (Query-Parsing) | QueryParser.parse(input_query) → tsquery. Einfache Operatoren translatert (&, |, !). Präfixsuche: "req*" → `'req':*`; Phrase: "exact phrase" → `'exact' <-> 'phrase'`. Validation: ungültige Eingabe wird mit Error + Hint abgewiesen. SQL-Injection-safe via Parameterized Queries. |
| REQ-L3-SEARCH-003 (Relevanz-Ranking) | ts_rank(tsvector, tsquery) verwendet für Sortierung. Gewichtung: title > description > tags. Exakte Matches > Präfixes (ts_rank berücksichtigt Position). Result-Payload enthält `relevance_score`. Deterministische Sortierung (Tiebreaker: creation_date DESC). |
| REQ-L3-SEARCH-004 (Artifact-Type-Filter) | type_filter Parameter: Single Type oder List von Types. Query WHERE Klausel: `artifact_type IN (type_filter)` oder `artifact_type = type_filter`. Multiple Types kombiniert mit OR. Ungültige Typen abgewiesen. |
| REQ-L3-SEARCH-005 (Workspace-Filter und Tenant-Isolation) | WHERE workspace_id = param (optional). Tenant-Isolation: alle Queries filtern nach Tenant-ID aus Auth-Context. Non-existent workspace_id → leere Ergebnisse (kein Error). Keine Cross-Tenant-Suche möglich. |
| REQ-L3-SEARCH-006 (Pagination) | OFFSET/LIMIT implementiert. page (1-basiert, default 1), limit (default 20, max 100). Response: results[], total_count (separate Query oder window function), page, limit. Page < 1 oder > max → Error. Limit-Beschränkung enforced. |
| REQ-L3-SEARCH-007 (Result-Annotation) | Jedes Suchergebnis hat `artifact_type` Feld: "Requirement", "ArchitectureElement", "TestCase". Wert reflektiert den korrekten Entity-Typ. Alle Ergebnisse annotiert (keine Auslassungen). |
| REQ-L3-SEARCH-008 (Performance und SLA) | Query mit 10.000 Items in ≤500ms p95. GIN-Index auf tsvector optimiert für read-performance. Query-Planner-Statistiken aktuell (regelmäßig ANALYZE). Keine N+1 Queries (single SELECT mit JOIN). |
| REQ-L3-SEARCH-009 (Fehlerbehandlung) | Ungültige tsquery mit Error + Hint zurückgeben. DB-Timeout gemeldet (nicht Crash). Error enthält keine internen Details. Fallback für zu breite Queries: leere Ergebnisliste (statt Error). |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-AS-EXT-IN-001:** REST API Endpoint `/search` mit Query-Parametern (query, type_filter[], workspace_id, page, limit).

- **Ausgänge (Outbound):**
  - **IF-AS-EXT-OUT-007:** SELECT Queries an PersistenceLayer (tsvector-Abfragen, Pagination mit OFFSET/LIMIT).

---

## 5. Architectural Rationale

**ADR-L3-SEARCH-01 — PostgreSQL Native FTS statt External Search Engine**

*Entscheidung:* Nutze PostgreSQL Full-Text-Search (tsvector, tsquery, GIN-Index) statt Elasticsearch oder Solr.

*Rationale:* ReqFlow verwendet bereits Django + PostgreSQL. FTS ist native, keine externe Abhängigkeit, keine zusätzliche Infrastruktur. Für Datasets mit 10.000 Items ist PostgreSQL FTS vollkommen ausreichend. Performance: ≤500ms p95. Alternative: Elasticsearch/Solr → Zusätzliche Infrastruktur, Sync-Komplexität (2 Systeme halten), Zusätzliche Kosten. **Abgelehnt**: Overkill für Größenordnung; Complexity-Overhead nicht gerechtfertigt.

*Erfüllt Trigger:* REQ-L3-SEARCH-001, REQ-L3-SEARCH-008 (Performance und SLA).

---

**ADR-L3-SEARCH-02 — tsvector-Materialisierung statt Runtime-Generierung**

*Entscheidung:* tsvector-Spalten werden materialisiert (gepflegt) in der Datenbank und bei INSERT/UPDATE via Trigger aktualisiert, nicht bei Query-Zeit generiert.

*Rationale:* Query-Zeit-Generierung wäre aufwändig (Tokenisierung + Stemming pro Query). Materialisierung ermöglicht GIN-Index und bessere Performance. Trigger stellen Konsistenz sicher. Alternative: Query-Zeit-Generierung → höhere CPU-Last, längere Latenz, kein Index-Nutzen. **Abgelehnt**: Performance-Anforderung REQ-L3-SEARCH-008 erfordert Materialisierung und Indexing.

*Erfüllt Trigger:* REQ-L3-SEARCH-001, REQ-L3-SEARCH-008.

---

**ADR-L3-SEARCH-03 — Separate Type-Filter statt Union Query**

*Entscheidung:* type_filter wird als WHERE-Klausel implementiert (`artifact_type IN (...)` oder UNION für Multiple-Type-Suche), nicht als Post-Processing-Filter.

*Rationale:* Query-basierte Filterung reduziert Datentransfer und Memory-Footprint. Alternative: Alle Typen laden, dann in Memory filtern → ineffizient. **Abgelehnt**: Performance-Anforderung REQ-L3-SEARCH-008 erfordert Query-basierte Filterung.

*Erfüllt Trigger:* REQ-L3-SEARCH-004 (Artifact-Type-Filter).

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
