---
step: requirements
agent: se-requirements
iteration: 1
status: done
timestamp: "2026-06-22T14:30:00Z"
schema_version: "1.0.0"
---
# L3 SearchService Requirements

> **Level:** L3 (Component-Anforderungen)
> **Component:** COMP-AS-010_SearchService
> **Parent:** L2_ApplicationServiceSystem_Requirements.json
> **Datum:** 2026-06-22
> **Status:** formalisiert
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## Traceability

- Abgeleitet von: REQ-L2-AppSvc-008, REQ-L2-AppSvc-009 (primär)
- Ziel: terminal (implementierungsbereit)

---

## Systemzweck

Der SearchService führt Volltextsuchen über Requirements, ArchitectureElements und TestCases durch. Er nutzt PostgreSQL Full-Text Search (tsvector) für performante Recherche über title, description und tags-Felder. Ergebnisse sind relevanz-sortiert und annotiert mit Artefakttyp. Optional können nach Artefakttyp und Workspace gefiltert werden.

---

## Externe Schnittstellen (Komponentengrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-AS-EXT-IN-001 | input | data | Search-Request vom ApplicationService oder MCP-Tool (query, type_filter[], workspace_id, page, limit) |
| IF-AS-EXT-OUT-007 | output | data | Schreib-/Lese-Aufrufe an den PersistenceLayer (SELECT mit tsvector) |

---

## L3 Component-Anforderungen

### REQ-L3-SEARCH-001: PostgreSQL Full-Text Search Setup

Der SearchService SHALL PostgreSQL Full-Text Search (tsvector, tsquery) einsetzen zur Indexierung und Suche. Folgende Felder werden einbezogen:
- Requirements: title, description, tags
- ArchitectureElements: title, description
- TestCases: title, description

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] tsvector-Spalten sind vorhanden für alle Entity-Typen
- [ ] GIN-Index auf tsvector-Spalten zur Performance
- [ ] Deutsch-Lexikon (ts_dict) konfiguriert für Stemming
- [ ] tsvector wird bei INSERT/UPDATE automatisch aktualisiert (Trigger)

**Interfaces:** IF-AS-EXT-OUT-007
**Traceability:** REQ-L2-AppSvc-008
**Rationale:** PostgreSQL FTS ist native, effizient und benötigt keine externen Abhängigkeiten.

---

### REQ-L3-SEARCH-002: Query-Parsing und Präfixsuche

Der SearchService SHALL SQL-Injection-resistente tsquery-Parsing durchführen:
- Einfache Operatoren: AND (&), OR (|), NOT (!)
- Präfixsuche: `prefix*` → `prefix:*`
- Phrasensuch mit Anführungszeichen: `"exact phrase"` → phrase-Ranking

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Benutzereingabe wird geparst ohne SQL-Injection-Risiko
- [ ] Präfixsuche funktioniert (z.B. "req" findet "requirement", "requirements")
- [ ] Operatoren werden korrekt übersetzt zu tsquery
- [ ] Query wird validiert und ungültige Eingaben abgewiesen

**Interfaces:** IF-AS-EXT-IN-001
**Traceability:** REQ-L2-AppSvc-008
**Rationale:** Benutzerfreundliche Suche mit erweiterten Operatoren.

---

### REQ-L3-SEARCH-003: Relevanz-Ranking und Sortierung

Der SearchService SHALL Suchergebnisse nach Relevanz-Score (ts_rank) sortieren. Höhere Scores für:
- Matches im title (gewichtet höher)
- Matches im tags (gewichtet höher)
- Exakte Wort-Matches (höher als Präfixes)

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] ts_rank wird für Sortierung herangezogen
- [ ] Title-Matches erscheinen vor Description-Matches
- [ ] Score wird in Result-Payload als `relevance_score` geliefert
- [ ] Sortierung ist deterministisch (Tiebreaker: creation_date DESC)

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Traceability:** REQ-L2-AppSvc-008
**Rationale:** Qualitätserlebnis durch intelligente Ranking.

---

### REQ-L3-SEARCH-004: Artifact-Type-Filter

Der SearchService SHALL Suchergebnisse optional nach Artefakttyp filtern:
- Single Type: `type_filter: "Requirement"`
- Multiple Types: `type_filter: ["Requirement", "ArchitectureElement"]`
- No Filter: alle Typen

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Type-Filter wird als WHERE-Klausel eingefügt
- [ ] Multiple Types werden mit OR kombiniert
- [ ] Ungültige Typen werden abgewiesen
- [ ] Filter reduziert Ergebnismenge sichtbar

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Traceability:** REQ-L2-AppSvc-009
**Rationale:** Gezielte Suche für Agenten mit spezifischen Artefakt-Anforderungen.

---

### REQ-L3-SEARCH-005: Workspace-Filter und Tenant-Isolation

Der SearchService SHALL Suchergebnisse auf eine einzelne Workspace (optional) begrenzen:
- Kein Filter: alle Workspaces des Tenants
- workspace_id: nur diese Workspace
- Tenant-Isolation ist mandatory: nur Workspaces des aktuellen Tenants

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Workspace-Filter wird als WHERE-Klausel eingefügt
- [ ] Keine Cross-Tenant-Suche möglich
- [ ] Tenant wird aus Auth-Context extrahiert
- [ ] Non-existent workspace_id wird mit Empty-Results gemeldet

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Traceability:** REQ-L2-AppSvc-009, REQ-L2-AppSvc-022
**Rationale:** Sicherheit und Datenisolation.

---

### REQ-L3-SEARCH-006: Pagination

Der SearchService SHALL Suchergebnisse paginiert zurückgeben:
- `page`: 1-basiert (default 1)
- `limit`: Ergebnisse pro Seite (default 20, max 100)
- Response enthält: results[], total_count, page, limit

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Pagination wird mit OFFSET/LIMIT implementiert
- [ ] Total-Count wird als separate Query berechnet (oder window function)
- [ ] Page < 1 oder > max wird abgewiesen
- [ ] Limit-Beschränkung (max 100) wird enforced

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Traceability:** REQ-L2-AppSvc-008
**Rationale:** Skalierbarkeit bei großen Ergebnismengen.

---

### REQ-L3-SEARCH-007: Result-Annotation mit Artefakttyp

Jedes Suchergebnis SHALL mit `artifact_type` annotiert sein:
- `"Requirement"`, `"ArchitectureElement"`, `"TestCase"`

Dies ermöglicht dem Client (UI oder MCP-Tool) die Ergebnisse korrekt zu kategorisieren.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Result-Payload enthält `artifact_type`-Feld
- [ ] Wert reflektiert den korrekten Entity-Typ
- [ ] Alle Ergebnisse annotiert (keine Auslassungen)

**Interfaces:** IF-AS-EXT-IN-001
**Traceability:** REQ-L2-AppSvc-008
**Rationale:** Usability für Multi-Type-Suche.

---

### REQ-L3-SEARCH-008: Performance und SLA

Der SearchService SHALL Suchen über bis zu 10.000 Entitäten in ≤500ms abschließen.

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Query mit 10.000 Items in ≤500ms p95
- [ ] GIN-Index auf tsvector optimiert für read-performance
- [ ] Query-Planner-Statistiken aktuell (ANALYZE regelmäßig)
- [ ] Keine N+1 Queries (single SELECT mit JOIN)

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Traceability:** REQ-L2-AppSvc-008
**Rationale:** Interaktive Suche in der UI und MCP-Tools.

---

### REQ-L3-SEARCH-009: Fehlerbehandlung

Bei Suche-Fehlern (z.B. ungültige tsquery, Datenbank-Timeout) SHALL der SearchService:
- Strukturierten Error mit Fehlermeldung zurückgeben
- Query-Fehler (z.B. unausgleichene Anführungszeichen) mit Hint beheben oder abweisen
- Keine Stack-Traces in Response

**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Ungültige tsquery wird mit Error + Hint abgewiesen
- [ ] DB-Timeout wird mit Error gemeldet (nicht Crash)
- [ ] Error enthält keine internen Details
- [ ] Fallback: leere Ergebnisliste (nicht Error) für zu breite Queries

**Interfaces:** IF-AS-EXT-IN-001, IF-AS-EXT-OUT-007
**Traceability:** REQ-L2-AppSvc-008
**Rationale:** Robustheit und Benutzerfreundlichkeit.

---

## Traceability-Matrix: REQ-L3-SEARCH → REQ-L2

| REQ-L3 | Primäre REQ-L2 |
|--------|----------------|
| REQ-L3-SEARCH-001 | REQ-L2-AppSvc-008 |
| REQ-L3-SEARCH-002 | REQ-L2-AppSvc-008 |
| REQ-L3-SEARCH-003 | REQ-L2-AppSvc-008 |
| REQ-L3-SEARCH-004 | REQ-L2-AppSvc-009 |
| REQ-L3-SEARCH-005 | REQ-L2-AppSvc-009, REQ-L2-AppSvc-022 |
| REQ-L3-SEARCH-006 | REQ-L2-AppSvc-008 |
| REQ-L3-SEARCH-007 | REQ-L2-AppSvc-008 |
| REQ-L3-SEARCH-008 | REQ-L2-AppSvc-008, REQ-L2-AppSvc-023 |
| REQ-L3-SEARCH-009 | REQ-L2-AppSvc-008 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
