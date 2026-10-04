---
type: EVIDENCE
scope: wp4-constraints-and-migrations
status: success
date: 2026-09-29
author_agent: data-engineer
---

# WP-4 Evidenz 5 — Constraint-Lücken, Migrationskette, Tenant-Isolation

Alle Messungen read-only (`SELECT` / Katalogabfragen). **Keine** Migration ausgeführt,
**keine** DDL, **keine** Datenmutation.

## 1. Fehlende Constraints an zentralen Tabellen

### 1.1 `workspace_id` ohne FK — 26 von 44 Tabellen

```sql
WITH ws AS (
  SELECT c.oid, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname='public' AND c.relkind='r'
    AND EXISTS (SELECT 1 FROM pg_attribute a
               WHERE a.attrelid=c.oid AND a.attname='workspace_id'
                 AND a.attnum>0 AND NOT a.attisdropped))
SELECT w.relname,
       EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conrelid=w.oid AND k.contype='f'
               AND pg_get_constraintdef(k.oid) LIKE '%pl_workspace(id)%') AS has_ws_fk
FROM ws w ORDER BY 2, 1;
```

**44 Tabellen haben eine `workspace_id`-Spalte. 26 haben keinen FK auf `pl_workspace`.**
Darunter die datenmodelltragenden:

| Tabelle | `workspace_id`-FK? | Rolle |
|---|---|---|
| `pl_artifact` | **NEIN** | Generic Artifact Model — **Zentrale** |
| `pl_requirement` | **NEIN** | meistgenutzter Entity-Typ |
| `we_item_state` | **NEIN** | Workflow-Zustand |
| `we_engine_definition` | **NEIN** | Workflow-Definition |
| `we_history_entry` | **NEIN** | Audit-Trail der Transitionen |
| `bl_baseline_snapshot` | **NEIN** | Baselines |
| `lt_workspace_definition` | **NEIN** | Link-Typ-Katalog |
| `ad_workspace_definition` | **NEIN** | Attribut-Katalog |
| `pl_test_run` | **NEIN** | Test-Run-Protokollierung |

Mit FK (18): `admin_ops_banner`, `at_item_permission`, `at_permission_decision_mismatch`,
`at_user_role`, `at_user_workspace_preference`, `at_workspace_permission_definition`,
`cg_workspace_context_settings`, `mem_memory_entry`, `mem_workspace_memory_settings`,
`pc_workspace_preset_config`, `pl_glossary_term`, `pl_interview_session`,
`pl_prompt_template`, `pl_prompt_variable`, `pl_review_policy`, `pl_token_usage_record`,
`pl_uid_sequence`, `sm_metric_cache`.

→ **AUD-2026-09-180** (High). Die Inkonsistenz ist real: **beide** Richtungen kommen vor.
`pc_workspace_preset_config` (der Preset-Tier-Speicher) hat einen FK, der Attribut- und
Link-Typ-Katalog derselben Produktidee nicht.

### 1.2 Live-Beweis: ein realer Orphan

```sql
-- 1: lt_workspace_definition zeigt auf einen nicht existierenden Workspace
SELECT d.workspace_id, count(*) AS keys
  FROM lt_workspace_definition d
 WHERE NOT EXISTS (SELECT 1 FROM pl_workspace w WHERE w.id=d.workspace_id)
 GROUP BY 1;
-- 3ef86cd6-ac51-4c11-b754-214716d65ebb | 8

-- 2: we_item_state zeigt auf einen nicht existierenden Workspace
SELECT count(*) FROM we_item_state s
 WHERE NOT EXISTS (SELECT 1 FROM pl_workspace w WHERE w.id=s.workspace_id);
-- 1

-- 3: sauber (keine Finding)
SELECT count(*) FROM pl_artifact a WHERE a.workspace_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM pl_workspace w WHERE w.id=a.workspace_id);        -- 0
SELECT count(*) FROM pl_requirement r WHERE r.workspace_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM pl_workspace w WHERE w.id=r.workspace_id);       -- 0
SELECT count(*) FROM we_item_state s
 WHERE NOT EXISTS (SELECT 1 FROM we_engine_definition d WHERE d.id=s.definition_id);  -- 0
```

`we_item_state` hat zusätzlich **keinen** FK auf `workspace_id` **und** keinen FK auf
`item_id` (UUID, nicht referenziert) — der Unique-Constraint
`uq_we_state_tenant_item (tenant_id, item_id, item_type)` live verifiziert deckt nur
Eindeutigkeit ab, keine Existenz.

### 1.3 `pl_tracelink.link_type` ohne CHECK

```
$ SELECT data_type FROM information_schema.columns
    WHERE table_name='pl_tracelink' AND column_name='link_type';
-- character varying
```

Kein `CHECK (link_type IN (...))`, kein Enum, kein FK auf einen Katalog. Das ist
**konsistent** mit der Tenant-Extensibility (Abschnitt 2 in
`wp4-link-type-4level-matrix.md`) — der Katalog ist Anwendungslogik. Es folgt aber:
**die DB kann einen `link_type` halten, den es im Katalog nicht (mehr) gibt**, und
niemand bemerkt es. Live ist das noch nicht eingetreten (0 unklare Keys, s. u.).

```sql
SELECT count(*) FROM pl_tracelink t
 WHERE t.link_type NOT IN ('derives-from','decomposes','refines','allocated-to',
                           'verifies','decides','mitigates','satisfies','realizes',
                           'references','diagram-ref');       -- 0
```

### 1.4 Was vorhanden ist (positiv)

| Tabelle | Constraints (live aus `pg_constraint`) |
|---|---|
| `we_item_state` | PK, `UNIQUE (tenant_id, item_id, item_type)`, 3 FKs (`definition_id`, `tenant_id`, `created_by_id`/`modified_by_id`) |
| `pl_tracelink` | PK, **`UNIQUE (source_id, target_id, link_type)`** (`uq_tracelink_edge`), 5 FKs (`source_id`/`target_id` → `pl_artifact`, `tenant_id`, `created_by_id`/`modified_by_id`, `proposed_by_id` → `at_api_key`) |
| `lt_global_definition` | PK, `UNIQUE (tenant_id, key)`, FK `tenant_id` |
| `lt_workspace_definition` | PK, `UNIQUE (tenant_id, workspace_id, key)`, FK `source_global_id`, FK `tenant_id` |
| `ad_global_definition` | PK, `UNIQUE (tenant_id, item_type, preset)`, FK `tenant_id` |
| `ad_workspace_definition` | PK, `UNIQUE (tenant_id, workspace_id, item_type)`, FK `source_global_id`, FK `tenant_id` |
| `bl_baseline_snapshot` | PK, `UNIQUE (workspace_id, name)`, FK `artifact_id`, FK `tenant_id` |

**Korrektur einer ersten Lesart:** `pl_tracelink` besitzt `uq_tracelink_edge
UNIQUE (source_id, target_id, link_type)` — doppelte Links desselben Typs zwischen
denselben Endpunkten sind auf DB-Ebene **nicht** schreibbar. Die `get_or_create`-Zeile in
`reqif_import_service.py:892` ist damit korrekt, aber redundant (sie schützt zusätzlich
gegen ein `IntegrityError` unter Raster-Sperren).

**Weiterhin fehlend an `pl_tracelink`:** eine CHECK-Bindung von `link_type` an den
Workspace-Katalog, und ein FK auf `workspace_id` (die Spalte existiert auf `pl_artifact`,
nicht auf `pl_tracelink` — der Cross-Workspace-Schutz läuft rein über
`_validate_cross_tenant_boundary`, `trace_link_manager.py:82-89`, plus den
Workspace-Übereinstimmungs-Filter im Service).

**Fehlend an `we_item_state`:** `CHECK (current_state IN (…states der definition…))` —
nicht in Django ausdrückbar, aber in `RunSQL` machbar. Der Ist-Zustand hält die
Invariante trotzdem (0 Verstöße, s. `wp4-state-bypass-inventory.md` §4), weil beide
Importpfade über `_map_status` normalisieren.

## 2. Migrationskette: Reversibilität und Re-Run

### 2.1 Struktur

```sql
SELECT count(*) FROM django_migrations;    -- 294
-- neueste: persistence.0102_adr_deciders_issue_assignee_artifact_stakeholder
--           persistence.0101_attributemigration_definition_snapshot
--           persistence.0100_workspace_goals_enabled_default
--           link_types.0009_backfill_need_satisfies_pair
```

### 2.2 `persistence.0093` — eine Datenmigration, die nicht mehr nachläuft

`backend/persistence/migrations/0093_normalize_testcase_artifact_type.py` (committed
`f280fb2b`, 2026-09-15) hat den **unbedingten** Forward-Schritt:

```python
Artifact.objects.filter(artifact_type__istartswith=_PREFIX).update(
    artifact_type=_BASE_TYPE)                       # :76-78
```

Das ist der korrekte, idempotente Shape. **Und doch tragen 99 Zeilen live noch den Tag:**

```sql
SELECT artifact_type, count(*), min(created_at)::date
  FROM pl_artifact WHERE artifact_type LIKE 'TestCase:%' GROUP BY 1;
-- TestCase:System | 30 | 2026-09-10
-- TestCase:Unit   | 69 | 2026-09-14
```

Und 30 dieser Artefakte sind **Quelle eines lebenden TraceLinks**:

```sql
SELECT count(*) FROM pl_tracelink tl
  JOIN pl_artifact a ON a.id=tl.source_id WHERE a.artifact_type LIKE 'TestCase:%';  -- 30
SELECT count(*) FROM pl_tracelink tl
  JOIN pl_artifact a ON a.id=tl.target_id WHERE a.artifact_type LIKE 'TestCase:%';  -- 0
```

**Belegte Fakten:**
1. `0093` ist in `django_migrations` verzeichnet (also ausgeführt).
2. Die 99 Zeilen stammen vom 2026-09-10/14, also **vor** dem Commit von 0093 (2026-09-15).
3. **Kein** aktueller Codepfad schreibt den Tag mehr
   (`rg "TestCase:" backend --glob "*.py" --glob "!**/tests/**"` → nur Kommentare).
4. Die globale `Requirement/extended`-Workflow-Definition trägt
   `updated_at: 2026-09-10T21:15:37Z` — dasselbe Datum.

**Hypothese (H, nicht bewiesen):** Die Instanz wurde **nach** dem Lauf der
Datenmigration neu geseedet oder aus einem Dump restauriert. Django-Datenmigrationen
sind einmalig — sie laufen nie erneut. Ein Restore überschreibt den
`django_migrations`-Eintrag nicht, sodass **nichts** die Abweichung erkennt.

**Warum das ein Befund ist, auch ohne die Hypothese:** Der Docstring der Migration
beansprucht `:27-28` *„No information is lost either way, and **no read path depends on
the tag any more**"*. Beides ist **falsch** — 4 Read-Pfade hängen real am Tag:

| Leser | Ort |
|---|---|
| Link-Typ-Paar-Validierung | `backend/link_types/catalog.py:40-48` `normalize_artifact_type` |
| Coverage-Berechnung | `backend/traceability/coverage_calculator.py` (Sammelverweis in `tests/test_coverage_calculator.py:111-120`) |
| Artefakt-Diff | `backend/application/artifact_diff_service.py` |
| Frontend Coverage-Badge | `frontend/src/utils/traceEndpoints.ts:97-99, 193-202` |

→ **AUD-2026-09-181** (High). Klassifikation **NEU** (Hypothesenanteil) — kein CR-Track;
`#1093` (normalize_testcase_artifact_type) ist **geschlossen**, betrifft aber die
Schema-Seite, nicht den Instanz-Datenbestand.

### 2.3 `link_types.0008` — gleiches Muster, kleinerer Schaden

`link_types/migrations/0008_seed_satisfaction_link_types.py:83` patcht bestehende
`WorkspaceLinkTypeDefinition`-Zeilen. Ergebnis auf der Live-Instanz:

```sql
SELECT key, count(*), count(DISTINCT workspace_id) FROM lt_workspace_definition
 GROUP BY 1 ORDER BY 1;
-- allocated-to|402  decides|402  decomposes|402  derives-from|402  diagram-ref|402
-- mitigates|402    references|402   verifies|402
-- realizes|401     refines|401      satisfies|401        <<< 1 Workspace fehlt
```

Der eine fehlende Workspace ist der Orphan aus §1.2. Die Migration hat ihn nicht
erreicht, weil er zu dem Zeitpunkt des Laufs bereits（或 ist) ohne `pl_workspace`-Zeile
existierte und der `UPDATE` über `filter()`-Kriterien lief, die ihn nicht erreichten.

→ **AUD-2026-09-156** (Low). Bestätigt die allgemeine Aussage: Datenmigrationen auf
Katalog-Tabellen sind **nicht** selbstheilend.

### 2.4 Gesamtbewertung der Migrationskette

| Frage | Antwort | Beleg |
|---|---|---|
| Ist ein `migrate` auf **frischer** DB sauber? | **BLOCKED** — nicht ausgeführt (Auftragsverbot) | Statisch plausibel: 294 Operationen, `RunSQL` nur in den ersten N; `0024_requirement_embedding` braucht Superuser für `CREATE EXTENSION vector` (belegt in `stack-db-redis.txt`) |
| Ist ein `migrate` auf **gefüllter** DB sauber? | **NEIN, nicht nachweisbar** | 0093 hat seinen Zweck auf dieser Instanz nicht erreicht (§2.2) |
| Gibt es nicht-reversible Migrationen? | **Nein, im geprüften Umfang** | `0093` hat `restore_artifact_type_tag` (`:81-92`); `_map_status` ist in beiden Kopien bewusst synchron gehalten (`reqif_import_service.py:205-209`) |
| Gibt es nicht-idempotente Migrationen? | **Ja, strukturell** | Alle `RunPython`-Datenmigrationen sind einmalig; `django_migrations` kennt keinen Zustand „schon gelaufen, aber Daten zurückgesetzt" |
| Gibt es einen Drift-Detektor? | **Nein** | Weder ein `makemigrations --check`-Gate über alle Apps (`CR-36` weiß das) noch ein Daten-Konsistenz-Gate |

→ **AUD-2026-09-183** (Medium): Die Migrationskette hat **keinen** Mechanismus, der
erkennt, dass eine einmal ausgeführte Datenmigration auf einer restaurierten oder
neu geseedeten Instanz nie nachgelaufen ist. `CR-36` ist der nächstliegende, aber
unvollständige Nachbar.

## 3. Tenant-Isolation auf Modellebene

### 3.1 PASS — kein `.raw()`, keine Fremd-Manager

```
$ rg -o "\.raw\(" backend --glob "*.py" --glob "!**/tests/**" --glob "!**/migrations/**"
  -> 0 Treffer
```

**Null** Raw-SQL-Queries im Produktions-Backend. Jede Query geht durch den
Tenant-Manager, `unscoped` oder ein explizites `raw`-Äquivalent — Letzteres kommt nicht vor.

### 3.2 PASS/BEACHTUNG — Manager-Struktur ist konsistent

`backend/persistence/tenancy.py:117` `TenantManager`,
`:161` `UnscopedManager`; `backend/persistence/models.py:446` `TenantScopedModel`,
`:464-465` `objects = TenantManager()` / `unscoped = UnscopedManager()`.

Alle 55 Model-Klassen in `persistence/models.py` erben von `TenantScopedModel` oder
`AuditableModel` (die einzige Ausnahme ist `AuditableModel` selbst, `:379`, das
Abstract-Base ist). **Kein Modell mit fehlendem Manager.**

### 3.3 `.unscoped` — 263 Verwendungen in Produktion

```
$ rg -c "\.unscoped" backend --glob "*.py" --glob "!**/tests/**" --glob "!**/migrations/**"
TOTAL: 263
```

Top-Dateien: `baseline/state_capture.py` (15), `persistence/management/commands/
cleanup_e2e_artifacts.py` (13), `application/workspace_service.py` (12),
`persistence/admin.py` (11), `baseline/store.py` (9), `icd/icd_manager.py` (9),
`workflow/global_definition_store.py` (9), `auth_tenancy/services/permission_definition.py` (7),
`auth_tenancy/services/authentication.py` (7), `traceability/audit/hierarchy.py` (6).

Das ist keine Fehlermenge per se — `unscoped` mit **explizitem** `tenant_id`-Filter
(`state_reader.py:133`, `global_definition_store.py:266`, `se_metrics/aggregator.py:243`)
ist das dokumentierte Muster (`link_types/catalog.py:15-19` beschreibt es sogar als
Vorlage). Die Beanstandung ist die **Menge** in Verbindung mit §3.4: 263
Escape-Hatches gegen 0 DB-Constraints auf 5 zentralen Tabellen ist eine
Verteilung, die ein einzelnes `Ratchet` nicht fassen kann.

→ **AUD-2026-09-186** (Medium).

### 3.4 BESTÄTIGT (CR-17) — Plain-Modelle ohne `tenant_id`, ohne RLS

Acht Produktionsmodelle erben von `models.Model` statt `TenantScopedModel`:

| Klasse | Ort | `tenant_id`-Spalte? | RLS? |
|---|---|---|---|
| `DomainEventOutbox` | `backend/application/models.py:44` | **NEIN** | nein |
| `DomainEventDLQ` | `backend/application/models.py:147` | **NEIN** | nein |
| `WebhookSubscription` | `backend/application/models.py:170` | **NEIN** | nein |
| `WebhookDeliveryLog` | `backend/application/models.py:204` | **NEIN** | nein |
| `BaselineDeltaIndexEntry` | `backend/baseline/models.py:116` | **NEIN** | nein |
| `MetricCache` | `backend/se_metrics/models.py:41` | **ja** (`:56`) | nein |
| `WorkspaceThresholdConfig` | `backend/se_metrics/models.py:92` | implizit | nein |
| `AuditableModel` | `backend/persistence/models.py:379` | (abstract) | — |

Live verifiziert (Spaltenlisten):

```
as_domain_event_dlq    | id, event_id, event_type, workspace_id, entity_id, payload,
                        | error_message, retry_count, moved_at          ← kein tenant_id
as_domain_event_outbox | id, event_id, event_type, workspace_id, entity_id, payload,
                        | created_at, published_at, published, retry_count, claimed_at
as_webhook_delivery_log| id, subscription_id, event_id, event_type, attempt, status_code,
                        | success, error_message, dispatched_at, is_dead_letter
as_webhook_subscription| id, workspace_id, event_types, url, secret, enabled, created_at
bl_delta_index_entry  | id, baseline_id, item_id, version, entity_type, state  ← kein tenant_id
sm_metric_cache        | id, workspace_id, tenant_id, timeframe_key, result_json, …
```

`backend/se_metrics/models.py:16-26` dokumentiert die bewusste Entscheidung für
`MetricCache`/`WorkspaceThresholdConfig` (rohes `tenant_id`, kein FK, kein RLS,
„a schema change to a pure read-model cache with no benefit") — das ist ein
**akzeptierter** Trade-off. Für die fünf `application`/`baseline`-Modelle gibt es
**keine** solche Begründung; ihre Isolation ist rein applikativ.

→ **AUD-2026-09-184**: Klassifikation **BESTAETIGT (CR-17)** — der Vor-Audit-Befund
`backend/baseline/models.py:116-187` + `backend/application/models.py:44-182` ist im
aktuellen Stand **unverändert** zutreffend. Neu belegt: die Liste ist **5 Modelle**
stark (nicht 2), und `as_domain_event_outbox`/`as_domain_event_dlq` tragen
`workspace_id` **ohne** FK, sind also zusätzlich von §1.1 betroffen.

### 3.5 RLS-Abdeckung

```sql
SELECT count(DISTINCT tablename) FROM pg_policies WHERE schemaname='public';   -- 71
SELECT count(*) FROM information_schema.tables
  WHERE table_schema='public' AND table_name LIKE 'pl_%';                        -- 31
-- pl_*-Tabellen OHNE RLS:
-- pl_tenant, pl_user
```

**29 von 31 `pl_*`-Tabellen haben RLS.** Ausnahmen: `pl_tenant` (Registry-Wurzel,
plausibel) und `pl_user` (Identity-Wurzel, vertretbar, aber nicht kommentiert).
Insgesamt 71 Policies über 71 Tabellen — also je eine pro Tabelle.

→ **AUD-2026-09-185** (INFO/PASS).

## 4. Reconciliation

| AUD | Klassifikation | Begründung |
|---|---|---|
| 180 | **NEU** | Kein CR-Track nennt fehlende `workspace_id`-FKs. `CR-17` nennt fehlende RLS. |
| 181 | **NEU (H-Anteil)** | `#1093` ist geschlossen und betrifft die Schema-Seite. |
| 183 | **NEU** | `CR-36` kennt nur `makemigrations --check`; nicht den Daten-Drift-Aspekt. |
| 184 | **BESTAETIGT (CR-17)** | Codepfade unverändert; Umfang von 2 auf 5 Modelle erweitert. |
| 185 | **INFO/PASS** | 29/31. |
| 186 | **NEU** | Kein CR-Track quantifiziert `.unscoped`. |
