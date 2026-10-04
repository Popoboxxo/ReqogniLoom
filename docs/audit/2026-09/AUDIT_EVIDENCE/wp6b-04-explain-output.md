---
type: REVIEW
scope: wp6b-concurrency-observability
status: complete
date: 2026-09-30
author_agent: code-reviewer
---

# WP-6b Evidence 04 — EXPLAIN-Output der geprüften Queries

Read-only gegen den **laufenden, geteilten** Stack
(`ai-native-reqflow-poc-postgres-1`, PostgreSQL 16 / pgvector).
Keine DDL, kein `ANALYZE`, keine schreibenden Queries.

## 0. Datenbasis (live, `count(*)` — nicht `pg_stat`)

| Tabelle | Zeilen |
|---|---|
| `pl_artifact` | **3442** |
| `pl_requirement` | **2112** |
| `pl_tracelink` | **2099** |
| `audit_entry` | **8167** |
| `as_domain_event_outbox` | **6872** |

Das ist eine realistische, nicht-leere Größenordnung.

## 0a. Methodischer Vorbehalt (wichtig für die Reconciliation)

Erste Hypothese war: *die Tabellen seien nie `ANALYZE`d worden, der Planner
arbeite ohne Statistik.* **Diese Hypothese war falsch — retracted.**

| Messung | Ergebnis | Interpretation |
|---|---|---|
| `pg_stat_user_tables`: `count(last_analyze IS NOT NULL)` | **0 / 100** | keine *gelaufene* `ANALYZE` seit Statistik-Reset |
| `pg_stat_user_tables.last_analyze` | `NULL` | dito |
| **`pg_stats`** (Spaltenstatistiken) | **38 Tabellen**, u. a. `pl_requirement` (22 cols), `pl_artifact` (22), `audit_entry` (18) | **Spaltenstatistiken SIND vorhanden** |
| `pg_class.reltuples` | `pl_artifact` 3441, `pl_requirement` 2098, `pl_tracelink` 1974, `audit_entry` 7601 | **realitätsnahe Schätzungen vorhanden** |
| `pg_postmaster_start_time()` | 2026-09-29 21:36 | Postgres läuft erst seit ~21.5 h |
| `pg_stat_database.stats_reset` | `NULL` (nie zurückgesetzt) | — |

**Erklärung:** `pg_class.reltuples` und `pg_statistic` liegen **on-disk** und
überleben einen Postmaster-Neustart; die `pg_stat_user_tables`-Zähler
(`seq_scan`, `idx_scan`, `n_live_tup`, `last_analyze`) liegen **in Shared
Memory** und werden beim Postmaster-Start genullt. Deshalb der scheinbare
Widerspruch.

**Konsequenz (zwei Teile, beide wichtig):**

1. **Für den Planner ist alles gut.** Die Pläne in diesem Dokument sind auf
   gültigen Statistiken gebaut und **vertrauenswürdig**.
2. **Für die Beweislage der Vor-Audits ist das fatal.** `pg_stat_user_tables`
   liefert in dieser Instanz **nur Zähler seit ~21.5 Stunden** und
   `n_live_tup` ist bis zum nächsten `VACUUM` bedeutungslos (belegt:
   `pl_requirement` meldet `n_live_tup = 1` bei **2112** echten Zeilen).
   Jede Performance-Aussage der Vor-Audits, die sich auf
   `seq_scan`/`idx_scan`/`n_live_tup` stützt — einschließlich der
   N+1-Hypothesen **PERF-001** und **PERF-003** und der Tracks
   **CR-33**/**CR-35** — beruht auf einer **widerlegbaren, möglicherweise
   genullten Zählerbasis**. → **288**

---

## Q1 — Requirement-Liste (hot endpoint)

Query-Shape aus `application/requirement_service.py:798-802`
(`select_related("artifact", …)`, Filter `artifact__workspace_id`,
Soft-Delete-Ausschluss), plus `ORDER BY a.priority, a.id LIMIT 50`:

```sql
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, SUMMARY ON)
SELECT r.id, r.artifact_id, r.title, a.lifecycle_status
FROM pl_requirement r
JOIN pl_artifact a ON a.id = r.artifact_id
WHERE a.tenant_id = '7a539397-6719-47bb-a6d5-5459016136fb'
  AND a.workspace_id = '4eee7ca1-eedd-4a7e-bb14-47e6493cbf88'
  AND a.lifecycle_status <> 'deleted'
ORDER BY a.priority, a.id
LIMIT 50 OFFSET 0;
```

```
 Limit (actual time=2.902..2.907 rows=50 loops=1)
   Buffers: shared hit=623
   ->  Sort (actual time=2.901..2.904 rows=50 loops=1)
         Sort Key: a.priority, r.artifact_id
         Sort Method: top-N heapsort  Memory: 42kB
         Buffers: shared hit=623
         ->  Hash Join (actual time=0.445..2.681 rows=896 loops=1)
               Hash Cond: (r.artifact_id = a.id)
               Buffers: shared hit=617
               ->  Seq Scan on pl_requirement r (actual time=0.004..2.000 rows=2112 loops=1)
                     Buffers: shared hit=578
               ->  Hash (actual time=0.425..0.426 rows=1186 loops=1)
                     Buckets: 2048  Batches: 1  Memory Usage: 81kB
                     Buffers: shared hit=39
                     ->  Bitmap Heap Scan on pl_artifact a (actual time=0.068..0.283 rows=1186 loops=1)
                           Recheck Cond: (workspace_id = '4eee7ca1-…'::uuid)
                           Filter: (((lifecycle_status)::text <> 'deleted'::text)
                                   AND (tenant_id = '7a539397-…'::uuid))
                           Heap Blocks: exact=37
                           Buffers: shared hit=39
                           ->  Bitmap Index Scan on pl_artifact_workspace_id_b9c0a10b
                                 (actual time=0.054..0.054 rows=1186 loops=1)
                                 Buffers: shared hit=2
 Planning Time: 1.681 ms
 Execution Time: 2.952 ms
```

**Bewertung: PASS (gemessen).**
- **2,95 ms**, 623 Buffer-Hits, 50 von 896 Join-Zeilen.
- Der `Seq Scan on pl_requirement` über 2112 Zeilen (578 Buffers) ist bei
  dieser Größe **richtig** — ein B-Tree-Zugriff wäre langsamer. Kein
  Fehlindizierung.
- `pl_artifact` wird per **Bitmap Index Scan** zugegriffen (2 Buffers für den
  Index, 37 Heap-Blöcke).
- **Kein Filesort auf einer großen Tabelle** — `top-N heapsort` auf 42 kB.
- **Kein N+1 im Plan**: `select_related` erzeugt einen einzigen Join; Owner/
  Reporter sind FKs auf `pl_artifact` und erscheinen nicht als weitere Queries.
- *Hartebeobachtung (kein Defekt):* der Planner wählt den **ein-spaltigen**
  `pl_artifact_workspace_id_b9c0a10b` statt des **zusammengesetzten**
  `idx_artifact_tnt_ws (tenant_id, workspace_id)` und filtert `tenant_id` +
  `lifecycle_status` als Recheck-Filter (37 Blöcke). Korrekt begründet: die
  Workspace-Prädikatselekivität (1186 von 3442) macht den schmaleren Index
  zum besseren Plan. Nur erwähnenswert, weil `idx_artifact_tnt_ws` dann
  faktisch ungenutzt ist.

---

## Q2 — Audit-Liste (drei Varianten, live 8167 Zeilen)

Query-Shape aus `audit/query.py:142-150`:
`qs.order_by("-timestamp")` + `qs.count()` + `qs[offset:offset+page_size]`.

### Q2a — Seite 1 (`LIMIT 50`)

```
 Limit (actual time=0.067..0.093 rows=50 loops=1)
   Buffers: shared hit=6
   ->  Index Scan Backward using idx_audit_tenant_ts on audit_entry
         (actual time=0.066..0.089 rows=50 loops=1)
         Index Cond: (tenant_id = '7a539397-…'::uuid)
         Buffers: shared hit=6
 Execution Time: 0.121 ms
```

**Bewertung: PASS (gemessen). 0,12 ms, 6 Buffers.** Der zusammengesetzte
Index `idx_audit_tenant_ts (tenant_id, "timestamp")` (live deployed) trägt
`WHERE tenant_id=? ORDER BY "timestamp" DESC LIMIT n` **perfekt**. Das ist der
beste geprüfte Plan des Audits.

### Q2b — tiefe Seite (`OFFSET 4000`)

```
 Limit (actual time=1.229..1.237 rows=50 loops=1)
   Buffers: shared hit=144
   ->  Index Scan Backward using idx_audit_tenant_ts on audit_entry
         (actual time=0.008..1.123 rows=4050 loops=1)
         Index Cond: (tenant_id = '7a539397-…'::uuid)
         Buffers: shared hit=144
 Execution Time: 1.245 ms
```

**Bewertung: STRUKTURDEFekt bestätigt, Auswirkung derzeit klein.**
- **4050 Zeilen gelesen, um 50 zurückzugeben — 81× Read-Amplification.**
- Der Index wird weiter benutzt (kein Seq Scan), daher ist der absolute
  Preis bei 8167 Zeilen nur **1,245 ms**.
- Das ist die **gemessene, quantifizierte** Form der bekannten Befunde
  `074`/`234` („ungebrochene Pagination"). Sie sind damit **bestätigt als
  Mechanismus** — aber **kein aktuelles Incidens**: bei dieser Größe
  sub-2-ms. Das Wachstum ist linear, die Grenze ist noch nicht erreicht.
- **Kein Keyset-Paging** (`WHERE (tenant_id, "timestamp") < (?, ?)`) — der
  vorhandene Index würde es ohne zusätzlichen Index unterstützen.

### Q2c — `COUNT(*)` für die Paginierung (läuft bei **jedem** Seitenaufruf)

```
 Aggregate (actual time=1.012..1.012 rows=1 loops=1)
   Buffers: shared hit=196
   ->  Seq Scan on audit_entry (actual time=0.008..0.717 rows=8133 loops=1)
         Filter: (tenant_id = '7a539397-…'::uuid)
         Rows Removed by Filter: 34
         Buffers: shared hit=196
 Execution Time: 1.027 ms
```

**Bewertung: latenter Kostentreiber, derzeit unkritisch.**
Voller Seq Scan über 8167 Zeilen pro Seitenaufruf, weil zum Zählen alle
passenden Zeilen gelesen werden müssen. **1,027 ms** heute.

**Der entscheidende Punkt ist die Komposition mit Finding 270:**

> Die **monatliche Retention-Job läuft nie** (#125) ⇒ `audit_entry` wächst
> unbegrenzt **und** jede Seitenanfrage der Audit-Liste macht einen vollen
> `COUNT(*)`. Zwei Defekte, die sich gegenseitig verstärken: mit 10⁵ statt
> 10³ Zeilen wird der Seq Scan ~12× langsamer (~12 ms pro Seitenaufruf) und
> `OFFSET`-Paging O(n).

→ **287 (Medium)**

---

## Q3 — Trace-Link-Liste / Graph-Traversierung

### Q3a/B — Workspace-Fan-out (`LIMIT 200`)

```
 Limit (actual time=0.627..2.007 rows=200 loops=1)
   Buffers: shared hit=845 read=3 dirtied=1
   ->  Nested Loop (actual time=0.627..1.993 rows=200 loops=1)
         ->  Index Scan using pl_tracelink_pkey on pl_tracelink t
               (actual time=0.570..1.379 rows=215 loops=1)
         ->  Memoize (actual time=0.003..0.003 rows=1 loops=215)
               Cache Key: t.source_id
               Hits: 9  Misses: 206  Evictions: 0  Overflows: 0
               ->  Index Scan using pl_artifact_pkey on pl_artifact a
                     (actual time=0.002..0.002 rows=1 loops=206)
                     Filter: ((tenant_id = …) AND (workspace_id = …))
 Execution Time: 2.096 ms
```

**Bewertung: PASS (gemessen). 2,10 ms für 200 Zeilen.** Der Planner nutzt
`Memoize` auf dem FK-Lookup — 206 Misses, aber `pl_artifact` ist nur 60 Seiten,
jeder PK-Lookup ist billig. Kein N+1 im Plan.

### Q3c — Trace-Link-Count (Coverage-Aggregation)

```
 Aggregate (actual time=1.015..1.016 rows=1 loops=1)
   Buffers: shared hit=413
   ->  Hash Join (actual time=0.405..0.942 rows=1974 loops=1)
         Hash Cond: (t.source_id = a.id)
         ->  Index Only Scan using pl_tracelink_source_id_8abb11d0 on pl_tracelink t
               (actual time=0.028..0.330 rows=2099 loops=1)
               Heap Fetches: 620
               ->  Bitmap Heap Scan on pl_artifact a … (rows=1186)
 Execution Time: 1.032 ms
```

**Bewertung: PASS (gemessen). 1,03 ms.** `Index Only Scan` über
`pl_tracelink_source_id_8abb11d0` (620 Heap-Fetches wegen `lifecycle_status`-/
Visibility-Map, unkritisch).

---

## Indizes: deployed oder nur in der Migrationsdatei?

**GEPRÜFT: alle Hot-Path-Indizes sind live deployed.** Aus `pg_indexes`
(38 Indizes über die 4 Hot-Tabellen), u. a.:

| Index | Tabelle | Trägt |
|---|---|---|
| `idx_audit_tenant_ts (tenant_id, "timestamp")` | `audit_entry` | Q2a/Q2b — **Vorzeigepfad** |
| `idx_artifact_tnt_ws (tenant_id, workspace_id)` | `pl_artifact` | Q1/Q3 (deployed, vom Planner nicht gewählt) |
| `idx_artifact_tnt_ws_type (tenant_id, workspace_id, artifact_type)` | `pl_artifact` | typgefilterte Listen |
| `pl_artifact_custom_fields_gin` (GIN) | `pl_artifact` | Custom-Field-Filter |
| `idx_requirement_fts_gin` (GIN, `to_tsvector('german', …)`) | `pl_requirement` | Volltextsuche |
| `pl_req_embedding_hnsw` / `pl_tracelink_embedding_hnsw` (HNSW) | beide | Vektorsuche |
| `idx_tracelink_graph (source_id, target_id)`, `uq_tracelink_edge (source_id, target_id, link_type)` | `pl_tracelink` | Graph-Traversierung, Duplikatschutz |
| `uq_requirement_workspace_uid`, `uq_artifact_reqif_uid`, `uq_artifact_reqif_identifier` | div. | Import-Idempotenz auf DB-Ebene |

→ **PASS: keine „nur in der Migrationsdatei" existierenden Indizes auf den
Hot-Paths.** Keine Drift zwischen Schema und Deployment festgestellt.

---

## Gesamturteil Performance (gemessen, nicht vermutet)

| Query | Ergebnis | Execution Time | Buffers |
|---|---|---|---|
| Q1 Requirement-Liste | **unkritisch** | 2,95 ms | 623 |
| Q2a Audit Seite 1 | **unkritisch (Vorzeigepfad)** | 0,12 ms | 6 |
| Q2b Audit `OFFSET 4000` | **Strukturdefekt, latenter Kostentreiber** | 1,25 ms (4050 Rows gelesen) | 144 |
| Q2c Audit `COUNT(*)` | **latenter Kostentreiber** | 1,03 ms (Seq Scan) | 196 |
| Q3b Trace-Links Fan-out | **unkritisch** | 2,10 ms | 845 |
| Q3c Trace-Link-Count | **unkritisch** | 1,03 ms | 413 |

**Kein** Seq-Scan-auf-großer-Tabelle-Problem, **kein** Filesort-auf-großer-Tabelle,
**kein** fehlender Index auf den geprüften Hot-Paths, **keine** Tiefen-Paginierung
außer der gemessenen Q2b.

**Das ist ein ehrlicher PASS-Beleg für die geprüften Queries** — nicht
„nicht geprüft". Die offenen Performance-Punkte sind ausschließlich
**strukturell/latent** (Q2b, Q2c) und **methodisch** (288).
