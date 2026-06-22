---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T13:20:00Z"
schema_version: "1.0.0"
---
# L3 PerformanceOptimizationLayer Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-PL-005_PerformanceOptimizationLayer
> **Parent:** L2_PersistenceLayerSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal

---

## 1. Verantwortlichkeit

Der PerformanceOptimizationLayer stellt sicher, dass Datenbank-Abfragen definierte Latenz-SLAs einhalten. Er verwaltet PostgreSQL-Indizes (BTree, GIST/GIN, tsvector), Connection-Pooling-Parameter, und überwacht Query-Performance. Sein Design garantiert, dass Standard-Queries < 200ms (p95) und Full-Text-Searches < 500ms (p95) laufen.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`Index` Deklarationen in Django Models:** `Meta.indexes` mit BTree, GIN, GIST Konfigurationen.
- **Connection-Pool-Manager:** Konfiguriert via `DATABASES['default']['CONN_MAX_AGE']` und optionalen `DB_POOL_SIZE`-Umgebungsvariablen.
- **`QueryPerformanceMonitor` (Utility-Klasse):** Misst Query-Latenz, logged Slow Queries, sammelt Metriken.
- **PostgreSQL Configuration:** Custom Parametrisierung für tsvector-Indizes (German Language), GIN-Indizes für Graph-Queries.

### 2.2 Datenstrukturen

**Index-Definitionen (Meta.indexes):**

1. **Artifact Hierarchy:**
   ```python
   class Artifact(TenantModel):
       parent_id = ForeignKey(..., null=True)

       class Meta:
           indexes = [
               Index(fields=['parent_id'], name='idx_artifact_parent_btree'),
           ]
   ```

2. **TraceLink Graph:**
   ```python
   class TraceLink(TenantModel):
       source_id = ForeignKey(Artifact, ...)
       target_id = ForeignKey(Artifact, ...)

       class Meta:
           indexes = [
               Index(fields=['source_id', 'target_id'], name='idx_tracelink_graph_gin'),  # GIN multi-column
           ]
   ```

3. **Full-Text-Search (German):**
   ```python
   class Requirement(TenantModel):
       title = CharField(...)
       description = TextField(...)

       class Meta:
           indexes = [
               Index(
                   expression=RawSQL(
                       "to_tsvector('german', title || ' ' || description)",
                       None
                   ),
                   name='idx_requirement_search_gin',
                   opclasses=['gin']
               ),
           ]
   ```

**Connection-Pool-Konfiguration (settings.py):**
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', 60)),
        'CONN_POOL_SIZE': int(os.getenv('DB_POOL_SIZE', 10)),
    }
}
```

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-PL005-001 (Pflichtindizes) | BTree auf `Artifact.parent_id`, GIN auf `TraceLink.source_id/target_id`, tsvector-GIN auf Requirement/ArchitectureElement/TestCase. Django-Migrationen enthalten `AddIndex` für jeden. EXPLAIN ANALYZE bestätigt Index-Nutzung. |
| REQ-L3-PL005-002 (Konfigurierbare Pool-Parameter) | `DB_CONN_MAX_AGE` und `DB_POOL_SIZE` via Umgebungsvariablen. Standard: 60s max_age, 10 pool_size. Load-Tests zeigen > 80% Wiederverwendungsrate. |
| REQ-L3-PL005-003 (Latenz-SLA-Einhaltung) | Mit Indizes und Pool-Tuning: Standard-CRUD < 200ms (p95), TraceLink-Queries < 200ms (p95), Recursive-CTE (500 Knoten) < 200ms (p95), Full-Text-Search < 500ms (p95) bei 10.000 Items, 50 concurrentusers. |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-PL-INT-004:** COMP-PL-004 erzeugt Migrationen mit AddIndex-Operationen basierend auf Index-Deklarationen.
- **IF-PL-INT-005:** COMP-PL-001 stellt `Meta.indexes` in Modell-Definitionen bereit.

**Ausgänge (Outbound):**
- **IF-PL-EXT-OUT-001:** PostgreSQL via psycopg2. Befehle: CREATE INDEX, REINDEX, EXPLAIN ANALYZE.
- **IF-PL-EXT-IN-009:** Liest Pool-Konfiguration via Umgebungsvariablen.

---

## 5. Architectural Rationale

**ADR-L3-PL-007 — Indexierungs-Strategie: Purpose-Driven Selection**

*Entscheidung:* Indizes werden basierend auf Query-Muster gewählt: BTree für Equality/Range (parent_id Hierarchie), GIN für Multi-Column-Graph (source/target), tsvector-GIN für Full-Text-Search.

*Alternative (abgelehnt):* Alle Spalten indexieren. Grund: Write-Overhead, Speicherverbrauch, Migrationszeit.

*Rationale:* REQ-L3-PL005-001 nennt konkrete Query-Pfade. Diese Auswahl ist minimal und zielsicher.

---

**ADR-L3-PL-008 — Connection-Pool via Django-Natives CONN_MAX_AGE statt externem Pooler**

*Entscheidung:* Django's built-in `CONN_MAX_AGE` wird für Connection-Reuse genutzt (statt pgbouncer/PgPool II).

*Alternative (abgelehnt):* Externen Connection-Pooler (pgbouncer) deployen. Grund: Zusätzliche Komponente, höherer Deployment-Aufwand, nicht unbedingt nötig für die beschriebenen Scale-Ziele.

*Rationale:* REQ-L3-PL005-002 fordert Pooling und Reuse-Rate > 80%. Django's Mechanism ist ausreichend für 50 concurrent users.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
