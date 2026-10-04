---
type: REVIEW
scope: wp6b-concurrency-observability
status: complete
date: 2026-09-30
author_agent: code-reviewer
---

# WP-6b Evidence 03 — Race-Analyse und Auflösung Issue #125

---

# TEIL A — Pflichtaufgabe: Widerspruch #125 auflösen

## A.1 Der Widerspruch

| Quelle | Aussage |
|---|---|
| **WP-1c** | `audit.archive_lifecycle_manager` ist **NICHT** im Worker-Task-Set, weil `autodiscover_tasks()` nur `<app>/tasks.py` importiert. |
| **WP-5** | „**nicht reproduzierbar**" — `settings.py:822` registriert die Aufgabe. |

## A.2 Ergebnis — eindeutig

> ### `audit.archive_lifecycle_manager` ist **NICHT** im Worker-Task-Set registriert.
> ### WP-1c hat **recht**; WP-5 hat die **falsche Stelle** zitiert.
> **Issue #125 ist BESTÄTIGT, nicht widerlegt.**

WP-5 hat zwei Dinge verwechselt, die im Code völlig verschieden sind:

1. **`CELERY_BEAT_SCHEDULE`** (Beat-Konfiguration) — *was Beat dispatcht*.
2. **Worker-Task-Registrierung** — *was der Worker ausführen kann*.

Nur (1) ist in `settings.py` vorhanden. Damit die Retention-Job ausgeführt
werden kann, braucht es **beides**. `settings.py:822` belegt nur (1).

## A.3 Belastender Nachweis #1 — Worker-Banner (live, read-only)

```
$ docker exec ai-native-reqflow-poc-celery-1 celery -A reqogniloom inspect registered --timeout=15
->  celery@c83f04fea09b: OK
    * admin_ops.record_celery_beat_heartbeat
    * application.dispatch_outbox_events
    * context_graph.rebuild_workspace_graph
    * llm_adapter.run_capability
    * memory.consolidate_interaction
    * resilience.execute_optional_task

1 node online.
```

**6 Tasks registriert. `audit.archive_lifecycle_manager` ist nicht dabei.**
(read-only Broadcast-RPC; dasselbe Muster nutzt bereits der
Compose-Healthcheck, `deploy/docker-compose.yml:847`.)

## A.4 Belastender Nachweis #2 — Beat hat den Schedule (live, read-only)

```
$ psql -c "SELECT name, task, enabled, total_run_count FROM django_celery_beat_periodictask ORDER BY name;"
audit-monthly-archive        | audit.archive_lifecycle_manager | t | 0
celery.backend_cleanup       | celery.backend_cleanup          | t | 13
dispatch-outbox-events       | application.dispatch_outbox_events | t | 222863
record-celery-beat-heartbeat | admin_ops.record_celery_beat_heartbeat | t | 18585
```

Beat **dispatcht** die Aufgabe also Very soon — `enabled = t`. Aber
`total_run_count = 0` bei gleichzeitig **222 863** erfolgreichen
Outbox-Läufen: die Zeitplanung ist geladen, der Task hat **nie ausgeführt**.

## A.5 Root Cause (Pfad:Zeile)

| Schritt | Befund | Ort |
|---|---|---|
| 1 | Der `@shared_task` liegt in `audit/archive.py`, **nicht** in `audit/tasks.py` | `backend/audit/archive.py:448` |
| 2 | `backend/audit/tasks.py` **existiert nicht** (verifiziert: nur `admin_ops`, `application`, `context_graph`, `llm_adapter`, `memory`, `resilience` haben eine `tasks.py`) | — |
| 3 | Der Worker lädt nur `<app>/tasks.py` | `backend/reqogniloom/celery.py:45` → `app.autodiscover_tasks()` |
| 4 | `audit`-App `ready()` importiert nur `audit.writer`, **nicht** `audit.archive` | `backend/audit/apps.py:36` |
| 5 | `audit.archive` wird von **nirgends** im Repo importiert (Volltextsuche: 0 Treffer außer Selbstbezug + Docstrings) | — |
| ⇒ | Der `@shared_task`-Dekorator läuft im Worker-Prozess nie ⇒ **Task nicht registriert** | |

## A.6 Auswirkung

- Beim nächsten 1. Mai / 1. Juni 00:00 dispatcht Beat
  `audit.archive_lifecycle_manager`; der Worker antwortet
  *„Received unregistered task of type …"*. Der Job läuft **nie**.
- Der `Dropper.drop_partition`-Pfad (`backend/audit/archive.py:330`, aufgerufen
  Z. 429) wird **nie** erreicht ⇒ **`audit_entry` wächst unbegrenzt**.
  Messbar: 8167 Zeilen, monatlich wachsend (2026-09-30).
- **Verschärfend:** Der Kommentar in `settings.py:801-809` behauptet
  ausführlich, der Job *sei* jetzt verdrahtet („it exports first and only
  drops the partition when the export reported success"). Dieser Kommentar
  ist **falsch** und hat den Defekt aktiv verdeckt — er hat sehr
  wahrscheinlich WP-5 zur Fehlklassifikation „nicht reproduzierbar"
  veranlasst.
- **Latenz:** Der Fehler ist latent — er tritt erst am 1. des Monats auf.
  Deshalb ist er in 22 Stunden Laufzeit **nicht** in den Worker-Logs
  aufgetaucht (`docker logs … | Select-String "unregistered"` → 0 Treffer).
  Das ist **kein** Gegenbeleg.

## A.7 Fix-Richtung (einzeilig)

`backend/audit/tasks.py` anlegen und den `@shared_task` dorthin
**verschieben** (nicht duplizieren), oder in `celery.py` explizit
`app.autodiscover_tasks(["audit"])`-Ergänzung per `include=`. Zusätzlich
den Kommentar `settings.py:801-809` korrigieren und einen Test ergänzen, der
die **Worker-Registrierung** prüft (nicht nur den Schedule-Dict — genau
diese Verwechslung hat den Befund erzeugt; siehe
`backend/audit/tests/test_sa39_append_guard_and_schedule.py`).

→ **Finding AUD-2026-09-270 (High)**

---

# TEIL B — Concurrency-Analyse

## B.1 `select_for_update()` — wo fehlt es, wo ist es zu breit?

### Zu breit (bewusst, mit Begründung)

| Ort | Breite | Bewertung |
|---|---|---|
| `persistence/models.py:2671,2789` | sperrt den **Parent-`Tenant`**-Row für Prompt-Template-Versionierung | **OK** — kommentiert (Z. 2654): serialisiert tenant-weit. Korrekte Wahl: der Zähler ist tenant-scope-übergreifend. |
| `application/optimistic_lock.py:90` | `select_for_update(of=("self",))` | **Sehr gut** — `of=` verhindert (a) Lock-Spread über `select_related("artifact")` und (b) `FieldError` auf der nullable Seite eines Outer Joins (Z. 74-78). |
| `persistence/artifact_backing.py:108` | `type(entity).objects.select_for_update().get(pk=…)` | **OK** — genau eine Zeile, genau die mehrdeutige. |

### Fehlend — echte Lücken

| # | Ort | Analyse | Finding |
|---|---|---|---|
| R1 | **`application/goal_service.py:134-149`** | `last = Goal.objects.filter(…).order_by("-sequence_number").first()` → `sequence_number = last.sequence_number + 1`. **Kein Lock, keine DB-Constraint.** Zwei parallele `update()`-Aufrufe auf dieselbe Lineage lesen beide `N`, beide schreiben `N+1` ⇒ **Lineage-Fork**. `Goal` erbt von `TenantScopedModel` (models.py:3342), hat **kein** `version`-Feld ⇒ **kein** Optimistic-Lock-Fallback. | **281** |
| R2 | **`application/*_service.py::transition_status` (6 Aufrufe)** | `WorkflowFacade().transition(...)` ohne `expected_version` ⇒ Parameter defaultet auf `None` ⇒ **last-writer-wins innerhalb des Row-Locks**. Siehe B.3. | **282** |
| R3 | `mcp_server/tools/users.py:449` | `User.objects.filter(id=user_id).first()` **ohne** Lock — Superuser-Check. Gering: der Wert ist während der Operation nicht mutierend relevant, aber die Query ist **redundant** (die aufrufende `AuthContext` kennt bereits `user_id`). | — (Low, nur Effizienz) |

## B.2 Optimistic Locking — gibt es es?

**Ja, und es ist gut gebaut.** `application/optimistic_lock.py` (128 Zeilen)
liefert zwei Primitive; `expected_version`/`If-Match` wird über
`rest_api/serializers.py:878-901` (`ExpectedVersionSerializerMixin`) und
`rest_api/mixins/etag.py` (`resolve_expected_version`, `If-Match` hat
Vorrang vor Body-Feld) angenommen und `OptimisticLockError` → **409
CONFLICT** gemappt.

### Abdeckungslücke: `as_goal` vs. `as_main_goal` (asymmetrisch)

| Tabelle | UNIQUE-Constraint auf | Quelle |
|---|---|---|
| `as_main_goal` | **`UNIQUE (workspace_id, sequence_number)`** ✅ | `application/migrations/0019_main_goal_sequence_unique.py` |
| `as_goal` | **KEIN** — nur `CHECK (sequence_number >= 0)` | `pg_constraint`, live abgefragt |

Der Autor kannte das Race für `MainGoal` und hat die Migration geschrieben —
für `Goal` fehlt sie. **Das ist kein Zufallsfehler, sondern eine
unvollständige Anwendung eines bereits bekannten Musters.**

```
$ psql -c "SELECT conname, contype, pg_get_constraintdef(oid) FROM pg_constraint
           WHERE conrelid IN ('as_goal'::regclass,'as_main_goal'::regclass);"
as_goal_sequence_number_check  | c | CHECK ((sequence_number >= 0))
uq_main_goal_workspace_sequence | u | UNIQUE (workspace_id, sequence_number)
```

### Ehrliche Einordnung der Auswirkung

`as_goal` ist **live leer** (0 Zeilen, 0 Lineages) — das Goal-Feature ist per
`Workspace.goals_enabled` defaultmäßig **aus** (`goal_service.py:121-127`).
Der Defekt ist also **latent, nicht realisiert**. Ich habe explizit geprüft,
ob er bereits Daten beschädigt hat:

```
$ SELECT lineage_id, sequence_number, count(*) FROM as_goal
  GROUP BY 1,2 HAVING count(*)>1;   →  (0 rows)
```

**Klassifikation: codeseitig + schema-seitig bewiesen, im aktuellen
Datenbestand nicht eingetreten.** Schweregrad High (Design), Auswirkung
aktuell null — das gehört so in den Bericht.

## B.3 Transitions (CR-06 / CR-08) — selbst geprüft, Reihenfolge bestätigt

`workflow/services.py:296-380`:

| Schritt | Zeile | Aktion |
|---|---|---|
| 1 | 306 | `with transaction.atomic():` |
| 2 | **308** | `item_state = lifecycle.lock_item_state(...)` ⇒ **`SELECT … FOR UPDATE`** |
| 3 | 310 | `current_state = item_state.current_state` — Lesen **aus der gesperrten Zeile** |
| 4 | ~318-360 | Validierung (`TransitionValidator`, 4 Regeln) **gegen den gesperrten Zustand** |
| 5 | 362 | `perform_transition(…, item_state=item_state)` — übergibt die gesperrte Zeile, **kein** zweites Lock (Z. 254-255) |

`lifecycle_manager.py:278-288` setzt das Lock; Z. 267-276 dokumentiert sogar,
dass ein Aufruf außerhalb einer Transaktion unter PostgreSQL **keinen**
Fehler wirft (`supports_select_for_update_in_autocommit` ist `False`) — der
Fehler wäre also still. Sauber.

**Zusätzlich** wird die Revisions-Prüfung **vor** der Graph-Validierung
beantwortet (`workflow/services.py:312-317`) — korrekte Präzedenz: ein
verlorenes Rennen soll „409, neu lesen" ergeben, nicht „Transition nicht
erlaubt" für eine Kante, die beim Lesen gültig war.

> ### Ergebnis: **CR-06 und CR-08 sind WIDERLEGT — behoben.**
> Bestätigt die WP-4-Bewertung, unabhängig verifiziert an
> `workflow/services.py:306-318` + `workflow/lifecycle_manager.py:278-288`.

### Aber: der Schutz ist nicht überall verdrahtet (R2)

`application/workflow_facade.py:96-99` dokumentiert den Rest selbst:

> „The CR-08 rollout only threads `expected_version` through the MCP
> transition tools; the service wrappers that call this facade directly
> (**the ADR, risk, issue, change-request and main-goal services, the goal
> re-activate path**) do not pass it and remain unprotected in that
> last-writer-wins sense."

**Unabhängig verifiziert — alle 6 Aufrufe ohne `expected_version`:**

| Aufrufer | Ort |
|---|---|
| `AdrService.transition_status` | `application/adr_service.py:562-568` |
| `RiskService.transition_status` | `application/risk_service.py:686-692` |
| `IssueService.transition_status` | `application/issue_service.py:726-732` |
| `ChangeRequestService.transition_status` | `application/change_request_service.py:638-644` |
| `MainGoalService` (Freigabe) | `application/main_goal_service.py:556-562` |
| `GoalService.transition_status` | `application/goal_service.py:659-665` |

**Präzise, nicht-generische Feststellung:** dieselben Services (`adr`, `risk`,
`issue`, `change_request`) **schützen ihr `update_*` sehr wohl** über
`lock_for_version_check` (sie stehen in der Liste der 9 Nutzer). Der Schutz
ist also **asymmetrisch innerhalb derselben Klasse**: Entity-Update
geschützt, Workflow-Transition derselben Entity ungeschützt. Ein Client, der
per REST einen Statuswechsel ausführt, bekommt **nie** ein 409, auch wenn er
`If-Match` mitsendet.

Warum das nicht durch den Mixin kompensiert wird: `rest_api/mixins/workflow_transitions.py`
löst `expected_version` zwar auf (Z. ~`n = _coerce_n(self.resolve_expected_version(...))`),
aber die Entity-Services, die der ViewSet am Ende aufruft, geben den Wert
nicht weiter. → **282 (High)**

## B.4 Idempotenz der Celery-Tasks

| Task | DB-Operation | Idempotent? | Beleg |
|---|---|---|---|
| `application.dispatch_outbox_events` | Claim via `select_for_update(skip_locked=True)` + `claimed_at` + Reclaim-Cutoff; Abschluss via konditionales `UPDATE … WHERE published=False` mit Rowcount-Assert | **JA** | `application/event_bus.py:333-362, 365-378` |
| `admin_ops.record_celery_beat_heartbeat` | Cache-`set` eines Timestamps | **JA** (idempotenter Zustand) | live: 18585 Läufe, `total_run_count` wächst ⇒ läuft |
| `llm_adapter.run_capability` | nicht geprüft (Netz-I/O + LLM-Billing) | — | **BLOCKED** |
| `memory.consolidate_interaction` | nicht geprüft | — | **BLOCKED** |
| `context_graph.rebuild_workspace_graph` | nicht geprüft (reiner Rebuild ⇒ vermutlich idempotent) | — | **BLOCKED** |
| `resilience.execute_optional_task` | delegierend | — | **BLOCKED** |
| `audit.archive_lifecycle_manager` | existiert nicht | n/a | **270** |

**Outbox-Pfad (e) — kein Race gefunden: PASS mit Beleg.**
`_claim_event` (Z. 333) hält den Lock **nur** für den Claim und committet
danach; Peer-Worker werden über `claimed_at` ferngehalten (Z. 325-328); die
Reclaim-Logik zählt einen verwaisten Claim **als Retry** und committet das
**vor** dem Dispatch (Z. 355-359), damit ein Crash ihn nicht zurücksetzt;
`_finalize_success` ist ein echter CAS (Z. 374-378). Live-Zustand:

```
 total | published | pending | claimed_pending | max_retry | DLQ
  6872 |      6872 |      0 |              0 |         0 |    0
```

**Alle 6872 Events publiziert, 0 pending, 0 verwaist, 0 in DLQ.** Der
Outbox-Mechanismus funktioniert in diesem Stack nachweislich.

**Aber:** `event_bus.py:477-479` sagt explizit *„Delivery is therefore still
at-least-once and subscribers must still be idempotent (REQ-072)"* — und der
**einzige** registrierte Abonnent tut das nicht (B.5). → **283**

## B.5 Audit-Writer ist nicht idempotent (d, Folge von e)

| Aspekt | Befund | Ort |
|---|---|---|
| Insert | `AuditEntry.unscoped.model.save(entry)` — **nackter INSERT**, kein `get_or_create` | `audit/writer.py:207` |
| Idempotenzschlüssel | **keiner.** `audit_entry` hat 19 Spalten, **kein** `event_id`, **keine** Unique-Constraint über den fachlichen Inhalt | live: `information_schema.columns` |
| Versprechen des Produzenten | „subscribers must still be idempotent (REQ-072)" | `application/event_bus.py:477-479` |

Ein Worker-Crash zwischen `_claim_event` und `_finalize_success` führt nach
`CLAIM_TIMEOUT_SECONDS = 300` (Z. 314) zur **Redelivery** ⇒ zweiter, identischer
Audit-Eintrag. Bei einem append-only Compliance-Artefakt ist das relevant.

**Ehrliche Einordnung — ich behaupte NICHT, dass es live passiert ist:**

```
$ SELECT count(*) AS total,
         count(DISTINCT (op, entity_type, entity_id, entity_version)) AS distinct_tuples
    FROM audit_entry;
 total  | distinct_tuples
  8167  |           7919
```

248 kollidierende Tupel. **Das ist ein Hinweis, kein Beweis** — dieselbe
Entity kann mehrfach mit identischem `op` geloggt worden sein (Feld-Diffs,
Wiederholungen ohne Versions-Bump), und `entity_version` ist in 97.7 % der
Zeilen `NULL` (siehe **285**), sodass `count(DISTINCT …)` ohnehin schwach
diskriminiert. Ich habe die Top-Gruppen geprüft (`update Banner` ×54,
`create LlmCall 00000000-…` ×42, `create Requirement` ×24) — alle mit
`entity_version IS NULL`, also **nicht** als Redelivery-Duplikate belegbar.
**Runtime-Auftreten: UNGEKLÄRT.** Der Code-Defekt ist bewiesen. → **283 (Medium)**
