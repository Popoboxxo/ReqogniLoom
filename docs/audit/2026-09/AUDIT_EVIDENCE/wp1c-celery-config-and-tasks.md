---
type: EVIDENCE
scope: WP-1c — Celery 5.6 Task-Inventar, Retry/Idempotenz/Acks
status: final
date: 2026-09-29
author_agent: devops-engineer
---

# WP-1c E3 — Celery: Task-Inventar, Ack-Semantik, Idempotenz, Beat

Alle Konfigurationswerte wurden **aus dem laufenden Worker-Container
ausgelesen** (`python` → `reqogniloom.celery.app.conf`), nicht aus dem
Quelltext geraten. Zusätzlich: `celery -A reqogniloom inspect conf`,
Worker-Log und `docker logs celery-beat`.

## 1. Live-Konfiguration (`app.conf`, im Container ausgelesen)

| Schlüssel | Wert | Bewertung |
|-----------|------|-----------|
| `task_acks_late` | **`False`** | **Befund** — kein Redelivery bei Worker-Verlust |
| `task_reject_on_worker_lost` | `None` (= False) | **Befund** |
| `worker_prefetch_multiplier` | `4` | mit pre-ack: bis zu 4 Nachrichten im Speicher **bereits als zugestellt gebucht** |
| `task_acks_on_failure_or_timeout` | `True` | korrekt (Task wird auch bei Fehlschlag bestätigt) |
| `broker_transport_options` | **`{}`** | **kein `visibility_timeout`**, keine `priority_steps`, keine `queue_order_strategy` |
| `result_expires` | `timedelta(days=1)` | 24 h Ergebnis-Aufbewahrung |
| `task_track_started` | `False` | zusammen mit Worker-Banner `task events: OFF` → **keine Aufgaben-Lebenszyklus-Sichtbarkeit** |
| `task_ignore_result` | `False` | jedes Ergebnis wird 24 h gespeichert |
| `task_default_queue` | `'default'` | ok |
| `task_default_exchange` | `'default'` | siehe §2 |
| `task_default_exchange_type` | `'direct'` | siehe §2 |
| `task_default_routing_key` | `'default'` | siehe §2 |
| `broker_connection_retry_on_startup` | `None` | Celery 5.6-Default `True` ist hier nicht aktiv |

Abgeleitet aus `settings.py:850-851`:
`CELERY_TASK_SOFT_TIME_LIMIT = 160 s`, `CELERY_TASK_TIME_LIMIT = 180 s`
(bei Default `LLM_LONG_RUNNING_TIMEOUT=180`).

## 2. **KRITISCH — alle vier Queues sind identisch gebunden**

`backend/reqogniloom/celery.py:31-42` deklariert vier Queues **ohne**
expliziten `Exchange` und **ohne** expliziten `routing_key`:

```python
app.conf.task_queues = (Queue('default'), Queue('llm'),
                        Queue('events'), Queue('memory'))
```

Celery füllt für jede so deklarierte Queue den **Default**-Exchange und den
**Default**-Routing-Key ein. Live aus dem Container gemessen:

```
queue=default  exchange=default  type=direct  routing_key=default  durable=True
queue=llm      exchange=default  type=direct  routing_key=default  durable=True
queue=events   exchange=default  type=direct  routing_key=default  durable=True
queue=memory   exchange=default  type=direct  routing_key=default  durable=True
```

Dasselbe im Worker-Startbanner (`docker logs celery-1`):

```
[queues]
     .> default          exchange=default(direct) key=default
     .> events           exchange=default(direct) key=default
     .> llm              exchange=default(direct) key=default
     .> memory           exchange=default(direct) key=default
```

Und in Redis existiert **genau ein** Binding-Key: `_kombu.binding.default`.

### 2.1 Konsequenz: 4-fache Ausführung jeder Task

Ein **direct**-Exchange liefert eine Nachricht an **alle** Queues, deren
Routing-Key dem Absende-Key entspricht. Hier sind das alle vier. Beweis,
**vollständig isoliert** (kombu `memory://`-Transport im Container, **kein**
Kontakt zum Live-Broker):

```
4 queues declared, all bound to exchange=default rk=default
published exactly 1 message
queue=default  deliveries=1
queue=llm      deliveries=1
queue=events   deliveries=1
queue=memory   deliveries=1
TOTAL_EXECUTIONS_FOR_ONE_PUBLISHED_TASK=4
```

Der Worker konsumiert alle vier Queues
(`deploy/docker-compose.yml:887`, `-Q default,llm,events,memory`) — er führt
jede Nachricht also **4×** aus. Damit ist die Queue-Aufteilung, die in
`celery.py:16-30` als Skalierungs-Voraussetzung begründet wird
("mit einer gemeinsamen Queue blockiert ein langsamer LLM-Aufruf … alles
dahinter"), **technisch wirkungslos**: `llm`, `events` und `memory` sind keine
eigenständigen Queues, sondern Aliase von `default`.
→ **`AUD-2026-09-120`**

Der Fan-out wurde **nicht** gegen den laufenden Broker getestet (Publish in
den geteilten Broker hätte den Worker der Parallel-Audits beeinflusst) — die
Bindungs-Identität ist aber direkt gemessen und der Isolations-Beweis oben
zeigt die Exchange-Semantik eindeutig.

## 3. **KRITISCH — `celery-beat` hat nie eine Aufgabe dispatcht**

`docker logs ai-native-reqflow-poc-celery-beat-1`, **komplettes Log** des
Containers (Neustarts am 2026-09-27 08:27, 2026-09-28 14:39, 2026-09-29 18:12,
2026-09-29 21:37):

```
[2026-09-27 08:27:45] DatabaseScheduler: Schedule changed.
[2026-09-28 14:39:38] DatabaseScheduler: Schedule changed.
[2026-09-29 18:12:49] DatabaseScheduler: Schedule changed.
[2026-09-29 21:37:07] DatabaseScheduler: Schedule changed.
```

**Null** Vorkommen von `Sending due task` — bei Celery-Bitdefault `--loglevel`
und `-l info`. Gegenprobe im Worker-Log: dort stehen ausschließlich
`pidbox received method ping()`-Zeilen (aus den Healthchecks), **keine**
`received`/`succeeded`-Zeilen für echte Aufgaben.

`django_celery_beat_periodictask` enthält **4 Zeilen** — die Schedule-Definition
ist also in der DB vorhanden und der Scheduler liest sie.

⇒ **Die komplette periodische Ausführung ist tot.** Betroffen sind alle drei
Einträge aus `settings.py:817-830`:

| Schedule-Name | Task | Takt | Status |
|---------------|------|------|--------|
| `dispatch-outbox-events` | `application.dispatch_outbox_events` | 5 s | **läuft nie** |
| `audit-monthly-archive` | `audit.archive_lifecycle_manager` | 1. des Monats 00:00 | **läuft nie** |
| `record-celery-beat-heartbeat` | `admin_ops.record_celery_beat_heartbeat` | 60 s | **läuft nie** |

Der Healthcheck des Containers (`deploy/docker-compose.yml:933`,
`pgrep -f 'celery.*beat'`) prüft **nur, ob der Prozess lebt** — nicht, ob er
dispatcht. Deshalb meldet `docker ps` `healthy` bei kompletter Funktionslosigkeit.
→ **`AUD-2026-09-121`**

**Reconciliation:** Issue **#171** *"[AUDIT][OPS] HIGH: celery-beat in
Dauer-Restart — periodische Tasks (REQ-030) laufen nie"* wurde am 2026-07-29
**geschlossen**. Der Crash-Loop ist behoben; die **Wirkung** („periodische
Tasks laufen nie") besteht nachweislich fort. Das ist eine unvollständige
Behebung, kein neues Problem.

### 3.1 Warum füllt sich der Outbox nicht?

Gemessen: `as_domain_event_outbox` = 6861 Zeilen, davon
`published_at IS NULL` = **0**, `published = false` = **0**,
jüngste Zeile `2026-09-29 23:09:45`.

Der Outbox staut also **nicht**, weil die drei In-Process-Projektoren
(`webhook_dispatcher` 5 Event-Typen, `context_graph.projector` 34,
`memory.projector` 2 — alle im Beat-Bootlog registriert) synchron über
`transaction.on_commit` publizieren. Der 5-Sekunden-Beat-Task ist ein
**nie ausgeführter** redundanter Sicherheitsnetz-Pfad. Konsequenz: was
synchron scheitert, bleibt **für immer** unveröffentlicht — der Beat hätte es
mit unbeschränkten Versuchen (alle 5 s) nachgeholt, findet aber nicht statt.
→ Teil von `AUD-2026-09-121`

## 4. **HIGH — `audit.archive_lifecycle_manager` ist beim Worker unbekannt**

Worker-Banner `[tasks]` aus `docker logs ai-native-reqflow-poc-celery-1`:

```
[tasks]
  . admin_ops.record_celery_beat_heartbeat
  . application.dispatch_outbox_events
  . celery.accumulate
  . celery.backend_cleanup
  . celery.chain
  . celery.chord
  . celery.chord_unlock
  . celery.chunks
  . celery.group
  . celery.map
  . celery.starmap
  . context_graph.rebuild_workspace_graph
  . llm_adapter.run_capability
  . memory.consolidate_interaction
  . resilience.execute_optional_task
```

`audit.archive_lifecycle_manager` **fehlt**. Ursache:
`app.autodiscover_tasks()` (`celery.py:45`) importiert pro Django-App nur
`<app>/tasks.py`. Der Task ist aber in **`backend/audit/archive.py:448`**
definiert, nicht in `backend/audit/tasks.py` (existiert nicht). Der
`try/except ImportError`-Block in `archive.py` schluckt genau den Fehlerfall,
der hier die Registrierung verhindert hätte.

Damit ist die **monatliche Audit-Archivierung** (`settings.py:801-809`,
`REQ-L3-AL003-001`) ein **garantiertes No-op** — unabhängig vom Beat-Defekt,
also auch nach einer Beat-Reparatur weiterhin tot. `audit_entry` hat bereits
8148 Zeilen und wächst unbegrenzt (Kommentar `settings.py:804-805` beschreibt
genau dieses Symptom als motivationsgrund für den Schedule-Eintrag).
→ **`AUD-2026-09-125`**

## 5. Task-Inventar — Retry / Idempotenz / Transaktionsgrenze

`Select-String` über alle 7 Task-Definitionen nach
`max_retries|retry_backoff|autoretry|acks_late|\.retry\(|atomic|idempot|dedup|on_failure|transaction|select_for_update|skip_locked|time_limit`:

| # | Task | Datei:Zeile | `@shared_task` | `bind` | `max_retries` | `retry_backoff` | `autoretry_for` | `.retry()` | `time_limit`-Override | `atomic()` | Idempotenz |
|---|------|-------------|----------------|--------|--------------|-----------------|------------------|------------|----------------------|-----------|------------|
| 1 | `application.dispatch_outbox_events` | `application/tasks.py:20` | ja | nein | **nein** | **nein** | **nein** | **nein** | nein | **nein** | `SELECT … FOR UPDATE SKIP LOCKED` in `poll_and_dispatch` |
| 2 | `audit.archive_lifecycle_manager` | `audit/archive.py:448` | ja | nein | **nein** | **nein** | **nein** | **nein** | nein | **nein** | **fraglich** (siehe §5.1) |
| 3 | `admin_ops.record_celery_beat_heartbeat` | `admin_ops/tasks.py:18` | ja | nein | **nein** | **nein** | **nein** | **nein** | nein | **nein** | ja (Cache-Overwrite) |
| 4 | `context_graph.rebuild_workspace_graph` | `context_graph/tasks.py:19` | ja | nein | **nein** | **nein** | **nein** | **nein** | nein | **nein** | **nein** (Vollrebuild) |
| 5 | `llm_adapter.run_capability` | `llm_adapter/tasks.py:77` | ja | **ja** | **nein** | **nein** | **nein** | **nein** | nein | **nein** | **nein** (LLM-Kosten, Token-Usage) |
| 6 | `memory.consolidate_interaction` | `memory/tasks.py:305` | ja | nein | **nein** | **nein** | **nein** | **nein** | nein | **nein** | **nein** (Dubletten-Dedup dokumentiert) |
| 7 | `resilience.execute_optional_task` | `resilience/tasks.py:41` | ja (optional) | nein | **nein** | **nein** | **nein** | **nein** | nein | **nein** | nein ( delegiert an PolicyEngine) |

**Summe: 0 von 7 Tasks haben Retry/Backoff. 0 von 7 haben eine
Datenbank-Transaktionsgrenze. 0 von 7 haben einen Idempotenzschlüssel oder
Deduplizierung auf Aufrufebene.**

### 5.1 Task-spezifische Bewertung

**#1 `dispatch_outbox_events`** — verschluckt **jede** Exception und gibt `0`
zurück (`tasks.py:36-38`). Kein Retry. Der "Retry" ist der 5-s-Beat-Takt, der
nie läuft (§3). Dauerhaft fehlschlagende Zeilen werden damit **endlos**
versucht (wenn Beat repariert wird) — kein `max_retries`, kein Dead-Letter,
nur ein Log-Eintrag pro Zyklus. Die `try/except` ist als
"beat task must never crash the loop" begründet; das ist korrekt, aber es
verwandelt jeden Fehler in einen **stillschweigenden** Dauerzustand.

**#2 `archive_lifecycle_manager`** — **destruktiv** (exportiert, dann droppt
Partitionen). `ArchiveLifecycleManager.run_monthly_archive()` ist als
"fail-safe by construction" beschrieben (`settings.py:806-809`: exportiert
erst, droppt nur bei gemeldetem Erfolg). Trotzdem: **kein Retry**, **keine
Transaktion**, und **Beat-Backfill existiert nicht** — ist der Worker um
00:00 am 1. des Monats down, entfällt die Archivierung für den **gesamten
Monat** lautlos. Ein Monats-Cron ohne `expires`/Backfill ist strukturell
verlustbehaftet.

**#5 `run_capability`** — der einzige Task mit `bind=True`; `except: raise`
(`tasks.py:174-176`) ⇒ Celery verzeichnet `FAILURE`, **kein** Retry. Ein
transienter LLM-5xx/Netz-Blip ⇒ **dauerhafter Task-Verlust** ohne
Wiederholung. Zusätzlich: `record_token_usage` schreibt in die DB; bei
mehrfacher Ausführung (§2.1, 4×) werden **4 Datensätze** geschrieben — Kosten-
und Abrechnungswirkung.

**#6 `consolidate_interaction`** — wird **ohne** `transaction.on_commit`
dispatcht (`memory/projector.py:182`), im Gegensatz zu
`rebuild_workspace_graph_task.delay()` (`application/context_service.py:480`,
`:497`, das sauber in `transaction.on_commit` gewrappt ist). Eine rollbackende
Transaktion erzeugt trotzdem eine Memory-Konsolidierung → Geisterdaten.
Ebenso `run_capability.apply_async()` (`llm_adapter/dispatcher.py:149`).

## 6. Worker-Kill mitten in einem Task — was passiert

Ableitung aus `task_acks_late = False` (live gemessen) + `worker_prefetch_multiplier = 4`:

1. Worker nimmt bis zu 4 Nachrichten **vorab** aus der Queue und **bestätigt sie
   sofort** (pre-ack).
2. Task beginnt zu laufen.
3. `SIGKILL` / OOM-Kill / Container-Recreate in diesem Fenster.
4. ⇒ **Die Nachricht ist endgültig verloren.** Kein Redelivery, weil bereits
   bestätigt. `task_reject_on_worker_lost` ist `False`, würde aber nichts
   nützen, da die Bestätigung schon erfolgte.
5. Zusätzlich bis zu **3 weitere** vorab bestätigte Nachrichten aus dem
   Prefetch-Fenster gehen mit verloren.

Für die Tasks 2 (destruktive Partition-Drops), 5 (LLM-Kosten) und 6
(Datenkonsistenz) ist das ein Datenverlust-/Kostenpfad, kein Komfortproblem.
`deploy/docker-compose.yml:808` setzt `stop_grace_period: 60s`, was * orderly
Stops abdeckt — **nicht** OOM-Kill oder `docker kill`.
→ **`AUD-2026-09-126`**

## 7. Doppelte Zustellung (Broker at-least-once)

Unabhängig vom Fan-out aus §2 ist der Worker gegenüber Redis-Transport
**ohnehin** at-least-once: ein Worker, der nach `task_acks_on_failure_or_timeout
= True` eine Aufgabe nach einem Timeout abbestätigt, aber weiterläuft, erzeugt
eine Doppelzustellung. Ohne `task_reject_on_worker_lost` und ohne
Idempotenzschlüssel laufen alle 7 Tasks dann doppelt.

Da **kein** Task eine Idempotenzprüfung besitzt, ist der effektive
Verstärkungsfaktor **4 (Fan-out) × 2 (at-least-once) = bis zu 8 Ausführungen
pro logischer Task**.

## 8. Queue-/Worker-Konfiguration

| Aspekt | Wert | Bewertung |
|--------|------|-----------|
| Worker-Command | `celery -A reqogniloom worker --loglevel=info -Q default,llm,events,memory --concurrency=${CELERY_CONCURRENCY:-4}` | `deploy/docker-compose.yml:887` |
| Worker-Healthcheck | `celery -A reqogniloom inspect ping -d celery@$$HOSTNAME` | `:847` |
| Beat-Healthcheck | `pgrep -f 'celery.*beat'` | `:933` — **prüft nur Prozessexistenz** |
| Beat-Command | `celery -A reqogniloom beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler` | `:947` |
| Live-Concurrency | **2** (prefork) | Worker-Banner: `concurrency: 2 (prefork)` — Release-Compose pinnt 4 → Konfigurationsdrift → `AUD-2026-09-145` |
| `MEMORY_BACKEND=honcho`-Pfad | `memory.*` → Queue `memory` | **durch den Fan-out wirkungslos** |

### 8.1 Ist die Schedule-Definition versioniert?

**Teilweise — mit einerimportant Fallstricke.**

- `settings.py:817-830` definiert `CELERY_BEAT_SCHEDULE` als **versionierten**
  Dict im Code.
- `settings.py:834` setzt `CELERY_BEAT_SCHEDULE_SCHEDULER =
  "django_celery_beat.schedulers:DatabaseScheduler"`.
- **`DatabaseScheduler` ignoriert `CELERY_BEAT_SCHEDULE` zur Laufzeit
  vollständig.** Es liest ausschließlich `django_celery_beat_periodictask`.
- Das Dict wirkt nur als **Seed**, den `django_celery_beat` per
  `post_migrate` in die Tabelle spiegelt.

Konsequenz: **eine Änderung an `CELERY_BEAT_SCHEDULE` wirkt erst nach einem
`migrate`-Lauf**, nicht nach einem `restart`/`up -d` ohne Migration. Ein
Operator, der den Takt in `settings.py` ändert, bekommt kein Feedback und
keine Wirkung. Das ist der Grund, warum die Tabelle bei 4 Zeilen von den 3
Settings-Einträgen abweicht.

**Kollisionsfreiheit:** Die drei Tasknamen sind paarweise disjunkt
(`application.*`, `audit.*`, `admin_ops.*`). Keine Kollision. Es gibt jedoch
**keinen** Single-Point-of-Truth-Schutz: weil der Seed nur bei `migrate`
läuft, können Code und Tabelle dauerhaft auseinanderlaufen. (Der bestehende
Test `backend/tests/test_wiring.py:71-105` prüft nur, dass die Task-Namen auf
`@shared_task` **auflösbar** sind — nicht, dass die DB-Zeilen zum Dict
passen.)

## 9. `migrate` als Task-Auslöser

`migrate` (`deploy/docker-compose.yml:754-795`) führt `python manage.py migrate`
aus und setzt `DB_STATEMENT_TIMEOUT_MS: "0"` (`:774`), begründet mit
unbegrenzten Index-Builds. Gemessen: `django_migrations` = **294** Zeilen,
jüngste `persistence.0102_…`. Der Vor-Audit-Wert ist **bestätigt**.

Der `post_migrate`-Receiver `application.self_init` provisioniert Base-Tenant,
Workspace, Admin-Rolle und Workflow-/Permission-Definitionen — **einmalig**,
im One-shot-Container. Das ist korrekt und race-frei (kein Worker migriert).
