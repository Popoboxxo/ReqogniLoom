---
type: EVIDENCE
scope: WP-1c — PostgreSQL 16 + pgvector: Parameter, Dimensionen, Indizes, EXPLAIN
status: final
date: 2026-09-29
author_agent: devops-engineer
---

# WP-1c E5 — PostgreSQL 16 + pgvector: Parameter, Embedding-Dimension, Indizes

Gemessen mit `SHOW` / `pg_settings` / `pg_hba_file_rules` /
`pg_db_role_setting` / `information_schema` / `EXPLAIN (ANALYZE, BUFFERS)`
gegen `ai-native-reqflow-poc-postgres-1`. Alle Abfragen read-only
(`SELECT`/`EXPLAIN`/`SHOW`).

## 1. Server-Identität

```
PostgreSQL 16.15 (Debian 16.15-1.pgdg12+2) on x86_64-pc-linux-gnu,
compiled by gcc (Debian 12.2.0-14+deb12u1) 12.2.0, 64-bit
pg_extension: plpgsql 1.0, vector 0.8.5
django_migrations: 294
```

`PG 16.15` + `pgvector 0.8.5` bestätigt die Vorgabe.

## 2. Parameter — Ist-Zustand und Herkunft

| Parameter | Wert | Quelle (`pg_settings.source`) | Bewertung |
|-----------|------|-------------------------------|-----------|
| `shared_buffers` | **163848 kB (160 MB)** | Konfigurationsdatei `postgresql.conf:130` | **knapp** — s.u. |
| `max_connections` | **300** | `postgresql.auto.conf:3` (via `ALTER SYSTEM`) | bewusst gesetzt |
| `superuser_reserved_connections` | 5 | `postgresql.auto.conf:4` | ok |
| `statement_timeout` | **0 (kein Timeout)** | **PostgreSQL-Default** (`-:-`) | siehe §2.1 |
| `work_mem` | 4096 kB (4 MB) | **Default** | bewusst nicht angefasst |
| `maintenance_work_mem` | 65536 kB (64 MB) | **Default** | knapp für HNSW |
| `effective_cache_size` | 5242888 kB (5,0 GB) | Default | Default, passt nicht zur cgroup |
| `effective_io_concurrency` | 1 | Default | Default |
| `random_page_cost` | 4.0 | Default | Default (SSD kostet 1.1–2.0) |
| `max_worker_processes` | 8 | Default | ok |
| `jit` | on | Default | ok |

**Kein einziger `command:`-Block auf dem `postgres`-Service**
(`deploy/docker-compose.yml:247-295`). Trotz der Aussage im Datei-Header
(`:62-64`: „`postgres`/`postgres-backup` run stock `pgvector/pgvector:pg16`
with self-contained `command:` blocks") hat **`postgres` keinen `command:`-
Block**. `max_connections=300` stammt aus `postgresql.auto.conf`, also aus dem
**Image bzw. einem einmaligen `ALTER SYSTEM` im Volume** — es ist **nicht als
versionierte Compose-Konfiguration** ausgedrückt. Ein `docker compose down -v`
oder ein Wechsel auf ein anderes Image setzt diesen Wert stillschweigend auf den
PG-Default 100 zurück, während `CONN_MAX_AGE=60` und die Gunicorn-/Prefork-
Prozesse weiter davon ausgehen. → `AUD-2026-09-147`

### 2.1 `statement_timeout` — differenzierte Bewertung

* **Am Cluster ist `statement_timeout=0`, also unbegrenzt.** Das ist der
  PostgreSQL-Default, der für **Nicht-Django**-Verbindungen greift — also für
  `psql`, `pg_isready` und den `pg_dump` des Backup-Sidecars. Für einen
  9,6-MB-Dump ist ein fehlendes Timeout **richtig**.
* **Die Django-Verbindungen haben ein Timeout**:
  `settings.py:359` setzt
  `"options": f"-c statement_timeout={config('DB_STATEMENT_TIMEOUT_MS', default=30000, cast=int)}"`
  ⇒ **30 s** pro Statement.
* **Ausnahme:** `migrate` setzt `DB_STATEMENT_TIMEOUT_MS: "0"`
  (`deploy/docker-compose.yml:774`), begründet mit unbegrenzten Index-Builds
  auf großen Produktionsdatenbanken.

⇒ **Kein Finding für den Normalbetrieb.** Der 0-Default am Cluster ist für
`pg_dump` korrekt und für die App irrelevant. Die *Absicht*
(30 s App / 0 s Migrationen) ist sauber getrennt und dokumentiert.

### 2.2 Speicher-Druck: die eigentliche PostgreSQL-Risikozeile

`postgres` hat `deploy.resources.limits.memory: 384M` und
`reservations.memory: 256M` (`deploy/docker-compose.yml:249-261`).
Gemessen: `shared_buffers` = **160 MB** ⇒ **42 % des cgroup-Limits ist allein
für den Shared Buffer reserviert.** Es bleiben ~224 MB für
`work_mem × max_connections`-Spitzen, Backends, WAL-Buffer und
Autovacuum. `effective_cache_size` sagt Postgres zusätzlich "5 GB verfügbar" —
eine **4-fache** Überzeichnung dessen, was die cgroup tatsächlich hergibt. Das
verleitet den Planner zu Index-Scans, die dann OOM-killen.

Für den **HNSW-Indexbau** ist die Rechnung schärfer: `maintenance_work_mem` 64 MB
+ `shared_buffers` 160 MB in einem 512-MB-Container (`migrate`, `:756-759`).
pgvector braucht `maintenance_work_mem` für den HNSW-Graphen. Bei
`m='16', ef_construction='64'` und 2111 Zeilen ist das heute unkritisch — bei
einer produktiven Datenmenge ist ein OOM-Kill des `migrate`-Containers
wahrscheinlicher als ein erfolgreicher Indexbau. → `AUD-2026-09-147`

## 3. `pg_hba.conf` / Authentifizierung

```
host all all 127.0.0.1 trust
host all all ::1      trust
host replication all 127.0.0.1 trust
host all all all      scram-sha-256
```

* `pg_db_role_setting` ist **leer** ⇒ keine `ALTER DATABASE … SET`-Overrides,
  insbesondere **kein** `ALTER ROLE … SET statement_timeout`.
* Der Standard-Pfad `host all all all scram-sha-256` ist korrekt (SCRAM, nicht
  `trust`/`md5`).
* Die `127.0.0.1`/`::1`-`trust`-Zeilen sind der **Image-Default** und betreffen
  nur Verbindungen **innerhalb** des Containers. Da Postgres keinen Host-Port
  publiziert, sind sie von außen unerreichbar. **PASS**.

⇒ **Kein Auth-Befund.** Positiv zu vermerken: `backend`/`celery`/`celery-beat`
laufen als least-privilege `DB_APP_USER` (`deploy/docker-compose.yml:586`,
`:818`, `:909`), nur `migrate` als Superuser (`:766`) — genau die in
`deploy/docker-compose.yml:583-585` beschriebene Rollentrennung für die
RLS-Isolation.

## 4. Embedding-Dimension — ist der `fix/deploy-embedding-dimension` really behoben?

### 4.1 Physische Spalten (gemessen)

| Tabelle | Spalte | `atttypmod` | `format_type` |
|---------|--------|-------------|---------------|
| `pl_requirement` | `embedding` | 384 | `vector(384)` |
| `pl_tracelink` | `embedding` | 384 | `vector(384)` |
| `icd_icd` | `embedding` | 384 | `vector(384)` |
| `mem_memory_entry` | `embedding` | 384 | `vector(384)` |

**Alle vier konsistent bei 384.** Keine 1536er-Reste. Das entspricht
`persistence/embedding_dimensions.py:84`
(`DEFAULT_EMBEDDING_VECTOR_DIMENSIONS = 384`, sentence-transformers /
`all-MiniLM-L6-v2`, live bestätigt im Beat-Bootlog: „Loading
SentenceTransformer model from sentence-transformers/all-MiniLM-L6-v2").

### 4.2 Kann eine dimensionsfremde Einbettung noch einen Laufzeitfehler erzeugen?

**NEIN.** Die Aufgaben-Prämisse ist damit **WIDERLEGT**. Drei unabhängige
Schichten verhindern, dass pgvector eine fremd-dimensionale Einbettung sieht:

1. **Single Source of Truth:** `persistence/models.py:149`, `:1603`, `:1947`
   und `memory/models.py:97` deklarieren **jedes** `VectorField` als
   `VectorField(dimensions=EMBEDDING_VECTOR_DIMENSIONS, …)`. Kein Feld literal.
2. **Pre-Insert-Guard an jedem Write-Site:** `requirement_service.py:894-902`,
   `trace_link_service.py:792-802`, `icd_manager.py:183-196` prüfen
   `len(embedding) == field_dimensions` **vor** dem Schreiben und lassen bei
   Abweichung den Vektor aus.
3. **Query-Guard:** `search_service.py:572-582` verwirft einen
   dimensionsfremden Query-Vektor, bevor er gegen nicht-NULL-Spalten verglichen
   wird — mit ausdrücklichem Hinweis, dass ein Mismatch dort sonst ein echter
   Postgres-Fehler und damit ein 500er wäre.

Ergänzend als **Frühwarnung**: `llm_adapter/checks.py:79-146` (Django-System-Check
`llm_adapter.W001`), registriert in `llm_adapter/apps.py:120-124`, plus der
`/health/`-Sub-Check `embedding_dimensions` (`backend/reqogniloom/health.py:187-215`).

### 4.3 Der verbleibende Rest — stille Degradation, kein Fehler

Was bleibt, ist **kein Laufzeitfehler**, sondern **stiller Datenverlust**:
Mit `EMBEDDING_PROVIDER=ollama` (768) oder `openai` (1536) passt kein Vektor in
`vector(384)`, der Guard **verwirft ihn**, und `Requirement.embedding` bleibt
NULL. Die semantische Suche liefert dann nichts — sichtbar nur als
`logger.warning` **einmal pro Prozess** (`embedding_service.py:298-328`).

**Das ist exakt Issue #1019** („Image-Deployment kann Nicht-384-Embeddings nicht
per Env aktivieren — Spalten bleiben `vector(384)`, Writes werden still
übersprungen"), am 2026-09-21 **geschlossen**. Der Self-Init-Pfad, den
#1019 beschreibt, wurde umgangen, indem der Zustand als *dokumentiertes
Restrisiko* akzeptiert und der Fehlerpfad durch Guards **beobachtbar**
gemacht wurde.

⇒ `AUD-2026-09-143` ist ein **DUPLIKAT von #1019** (kein neuer Befund), mit
einer Verschärfung: Der `/health/`-Sub-Check existiert, meldet den Zustand aber
nur als `warnings`-Eintrag bei weiterhin `status: ok` (live bestätigt, E6).
Empfehlung: entweder `status: degraded` bei Mismatch oder den Zustand als
`blocked` führen.

## 5. Indizes

### 5.1 Gesamtbestand

| Metrik | Wert |
|--------|------|
| Indizes im Schema `public` | **633** |
| davon Vektor-Indizes | **4** |
| Tabellen mit Zeilen | 14 |
| Tabellen gesamt | ca. 200+ (294 Migrationen) |

**PASS:** Für eine Django-App mit 294 Migrationen ist 633 ein **sehr**
gesundes Niveau. Es gibt **keinen** pauschalen Index-Mangel.

### 5.2 Vektor-Indizes — alle vier vorhanden und nachweislich genutzt

```
pl_requirement      -> pl_req_embedding_hnsw      : hnsw (embedding vector_cosine_ops) WITH (m='16', ef_construction='64')
pl_tracelink        -> pl_tracelink_embedding_hnsw : hnsw (embedding vector_cosine_ops) WITH (m='16', ef_construction='64')
icd_icd             -> icd_embedding_hnsw         : hnsw (embedding vector_cosine_ops) WITH (m='16', ef_construction='64')
mem_memory_entry    -> mem_entry_embedding_hnsw   : hnsw (embedding vector_cosine_ops) WITH (m='16', ef_construction='64')
```

**EXPLAIN-Beweis der Nutzung** (echte Query mit echten Daten):

```sql
EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)
SELECT id FROM pl_requirement
ORDER BY embedding <=> (SELECT embedding FROM pl_requirement
                        WHERE embedding IS NOT NULL LIMIT 1)
LIMIT 10;
```

```
 Limit (actual rows=10 loops=1)
   InitPlan 1 (returns $0)
     -> Limit (actual rows=1 loops=1)
           -> Seq Scan on pl_requirement pl_requirement_1 (actual rows=1 loops=1)
                 Filter: (embedding IS NOT NULL)
   -> Index Scan using pl_req_embedding_hnsw on pl_requirement (actual rows=10 loops=1)
         Order By: (embedding <=> $0)
 Planning Time: 1.126 ms
 Execution Time: 279.113 ms
```

⇒ Der HNSW-Index **wird** benutzt (`Index Scan using pl_req_embedding_hnsw …
Order By: (embedding <=> $0)`), kein Seq-Scan-Fallback. Der Initial-Scan für den
Query-Vektor ist ein einmaliger `Seq Scan` ohne Index (korner `IS NOT NULL` ist
nicht indexiert) — bei 2111 Zeilen irrelevant.

Die 279 ms sind **kein** Benchmark (einmaliger Lauf, `ANALYZE`-Overhead,
kalte HNSW-`ef_search`-Traversierung) und werden **nicht** als Finding
verwertet. `ef_search` ist nicht gesetzt ⇒ Default 40; bei wachsender
Datenmenge wäre das der erste Hebel. **PASS für heute.**

### 5.3 Repräsentative Listen-Endpoint-Query

```sql
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, TIMING OFF)
SELECT id, created_at FROM pl_artifact
WHERE tenant_id='7a539397-…' AND workspace_id='4eee7ca1-…'
  AND lifecycle_status='active'
ORDER BY created_at DESC LIMIT 50;
```
(Datenmenge dieser Kombination: 1169 Zeilen.)

```
 Limit (actual rows=50 loops=1)
   Buffers: shared hit=36
   ->  Sort (actual rows=50 loops=1)
         Sort Key: created_at DESC
         Sort Method: top-N heapsort  Memory: 32kB
         ->  Bitmap Heap Scan on pl_artifact (actual rows=1169 loops=1)
               Recheck Cond: (workspace_id = '4eee7ca1-…'::uuid)
               Filter: ((tenant_id = '7a539397-…'::uuid)
                        AND ((lifecycle_status)::text = 'active'::text))
               Rows Removed by Filter: 7
               Heap Blocks: exact=31
               Buffers: shared hit=33
               ->  Bitmap Index Scan on pl_artifact_workspace_id_b9c0a10b (actual rows=1176 loops=1)
                     Index Cond: (workspace_id = '4eee7ca1-…'::uuid)
```

**Zwei strukturelle Beobachtungen, beide messbar, beide kein Engpass heute:**

1. **Kein Index enthält `created_at`** ⇒ der `ORDER BY … DESC` erzwingt
   einen `Sort` (top-N heapsort über alle 1169 Treffer). Ein
   `(workspace_id, created_at DESC)`-Index würde den Sort ersetzen.
2. **Die vorhandene Composite-Index `idx_artifact_tnt_ws_type
   (tenant_id, workspace_id, artifact_type)` wird nicht gewählt.** Der Planner
   nimmt stattdessen den schmaleren `pl_artifact_workspace_id_b9c0a10b` und
   filtert `tenant_id` + `lifecycle_status` aus dem Heap
   (`Rows Removed by Filter: 7`).

**Ausdrücklich KEIN Benchmark-Roulette:** 36 Buffers, 0,055 ms Ausführungszeit
bei 3432 Zeilen gesamt. Der Befund ist **Low** und **prognostisch**: die
Struktur (Sort + ungenutzter Composite-Index) skaliert mit der Datenmenge, der
absolute Aufwand ist heute vernachlässigbar.
→ `AUD-2026-09-144`

Die 20 Indizes auf `pl_artifact` enthalten übrigens **vier exakte Duplikate**:
`pl_artifact_parent_id_71baafe4` und `idx_artifact_parent_btree` (beide auf
`parent_id`), `pl_artifact_lifecycle_status_454ebbce` und
`…_like` (btree + `varchar_pattern_ops` auf derselben Spalte), ebenso für
`priority`. Das ist **Schreib-Overhead ohne Nutzen** — bei jedem INSERT/DELETE
einer `pl_artifact`-Zeile werden 20 statt 16 Indizes gepflegt. Kein
Datenverlust, aber messbarer Overhead. → Teil von `AUD-2026-09-144`

### 5.4 Audit-Listen-Endpoint — optimal

```sql
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, TIMING OFF)
SELECT id, "timestamp" FROM audit_entry
WHERE tenant_id='7a539397-…' ORDER BY "timestamp" DESC LIMIT 50;
```

```
 Limit (actual rows=50 loops=1)
   Buffers: shared hit=5
   ->  Index Scan Backward using idx_audit_tenant_ts on audit_entry (actual rows=50 loops=1)
         Index Cond: (tenant_id = '7a539397-…'::uuid)
   Buffers: shared hit=5
 Planning Time: 0.375 ms
 Execution Time: 0.054 ms
```

⇒ `idx_audit_tenant_ts (tenant_id, "timestamp")` liefert Filter **und**
Sortierung in einem Backward-Index-Scan. **Kein Sort-Knoten, 5 Buffers.**
Exakt das gewünschte Muster — und der **Kontrast** zu §5.3 zeigt, dass der
`pl_artifact`-Fall eine echte Lücke ist und nicht der Normalfall des Schemas.
**PASS.**

## 6. `migrate` — Migrationsstand

| Metrik | Wert | Erwartet |
|--------|------|----------|
| `django_migrations` | **294** | 294 (Vorgabe) ✔ |
| jüngste Migration | `persistence.0102_…` | ✔ |
| `celery_taskmeta`-Tabelle | **existiert nicht** | ✔ korrekt — Result-Backend ist Redis, nicht die DB |

`migrate: Exited 0` im laufenden Stack bestätigt einen sauberen Durchlauf.
