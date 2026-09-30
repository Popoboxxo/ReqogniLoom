---
type: REVIEW
scope: wp6b-concurrency-observability
status: complete
date: 2026-09-30
author_agent: code-reviewer
---

# WP-6b Evidence 02 — Transaktionsgrenzen-Matrix

Frage: (a) wo fehlt `transaction.atomic()` um eine fachliche Multi-Write-Operation,
(b) wo endet eine Transaktion **früher** als die fachliche Einheit,
(c) hält ein Fehler in Schritt 3 die Schritte 1–2 zurück?

## 0. Methodik-Limit (ehrlich)

Live-Verifikation der Rollback-Semantik wäre **schreibend** gewesen
(Rollback- induzieren). Der Stack ist geteilt ⇒ **nicht ausgeführt**.
Alle Aussagen unten sind **statisch belegt** (Code-Pfade, Transaktionsgrenzen,
Dekoratorreihenfolge) — in der Spalte „Beleg" steht der konkrete Pfad.

## 1. Vorhandene Transaktionsinfrastruktur (PASS)

| Artefakt | Ort | Bewertung |
|---|---|---|
| `atomic_transaction`-Dekorator | `persistence/transactions.py:38-56` | **PASS** — delegiert an `transaction.atomic()`, `@functools.wraps` |
| `TransactionContextManager` (Multi-Step) | `persistence/transactions.py:59-95` | **PASS** — ein `atomic()` über den ganzen Block, optionales `SET LOCAL statement_timeout` (REQ-L3-PL003-003) |
| Optimistic-Lock-Primitiven | `application/optimistic_lock.py:47-128` | **PASS** — `lock_for_version_check` nimmt `select_for_update(of=("self",))` **nur** wenn `expected_version` gesetzt ist (bewusste Lock-Vermeidung auf dem dominierenden unguarded Pfad, Z. 60-62); `assert_expected_version` wirft `OptimisticLockError` → 409 |
| `atomic()`-Nutzung | 100+ Prod-Dateien, `interview_service.py` (16), `workspace_service.py` (9), `traceability/trace_link_manager.py` (7) | flächendeckend |

## 2. Transaktionsgrenzen-Matrix (fachliche Einheit vs. `atomic()`)

| # | Fachliche Operation | Ort | `atomic()`-Hülle | Fehler in Schritt 3 rollt 1–2 zurück? | Bewertung |
|---|---|---|---|---|---|
| T1 | **Workflow-Transition** (Lock → Read → Validate → Write + History) | `workflow/services.py:236-380` | **JA** — `with transaction.atomic():` Z. 306, umschließt Lock(308), Validierung, `perform_transition`(362) inkl. History-INSERT | **JA** | **PASS.** `perform_transition` ist selbst `@transaction.atomic` (Z. 290) ⇒ **verschachtelter Savepoint**; das ist korrekt und liefert genau das gewünschte Rollback-Verhalten. |
| T2 | **Global-Definition-State-Löschung** (Check + Graph-Write) | `workflow/global_definition_store.py:364-400` | **JA** — Z. 364, `locked = ...select_for_update().get(pk=obj.pk)` Z. 366 | **JA** | **PASS.** Explizit *ein* Block; der Docstring (Z. 330-337) dokumentiert, dass die frühere Zwei-Block-Form (Check in eigener Transaktion, `_persist` in zweiter) genau dieses Fenster erzeugte — **behoben**. |
| T3 | **Outbox-Claim** | `application/event_bus.py:333-362` | **JA, absichtlich eng** — Z. 333 nur um den Claim | n/a | **PASS by design.** Der enge Block ist die Voraussetzung dafür, dass kein Lock über Net-I/O gehalten wird (Z. 325-328). Die *Fachoperation* (Dispatch) liegt bewusst außerhalb — korrekt für at-least-once. |
| T4 | **Outbox-`_finalize_success`** | `application/event_bus.py:365-378` | implizit (einzelnes `UPDATE`) | n/a | **PASS.** Konditionales `UPDATE … WHERE published=False` + Rowcount-Assert `== 1` (Z. 378) ⇒ echter CAS, kein Lost Update zwischen Peer-Workern. |
| T5 | **API-Key-Cap-Zählung** (Invariant „unter Cap") | `auth_tenancy/services/authorization.py:970-1027` | **JA** | **JA** | **PASS.** Z. 986/1027 `select_for_update()` **vor** dem Excludieren/Counten in Python — genau die richtige Reihenfolge. |
| T6 | **Refresh-Token-Claim** (Rotation) | `auth_tenancy/services/authentication.py:318,382-388` | **JA** | **JA** | **PASS.** `unscoped + select_for_update` im eigenen Block; Z. 318 dokumentiert „claimed under select_for_update inside a transaction". |
| T7 | **Circuit-Breaker-State** | `resilience/circuit_breaker.py:206,211` | **JA** | **JA** | **PASS.** |
| T8 | **Interview-Session-Serialisierung** | `application/interview_service.py:960,1031` | **JA** | **JA** | **PASS.** Z. 960 benennt den Grund selbst („a check-then-act race"). |
| T9 | **UidSequence** ( monotoner Zähler) | `application/local_uid.py:83` | **JA** — `get_or_create` unter `select_for_update` | **JA** | **PASS.** Zähler-Sequenzen sind der klassische Lost-Update-Ort; hier korrekt abgesichert. |
| T10 | **TestRun-Ergebnis-Posting** | `application/test_run_service.py:415,459` | **JA** | **JA** | **PASS.** Z. 415: „every decision is made from *that* read" — Lock-vor-Entscheidung, korrekte Reihenfolge. |
| T11 | **Prompt-Template-Versionierung** | `persistence/models.py:2648-2671,2789` | **JA** | **JA** | **PASS.** Sperrt den **Parent-`Tenant`**-Row, um den Scope-übergreifend zu serialisieren (Z. 2654) — bewusste, kommentierte Überbreite mit Begründung. |
| T12 | **Audit-Write + Outbox-Event** (fachliche Einheit „Operation") | `application/event_bus.py` publish-Pfad, `audit/writer.py:207` | **JA** (Publisher öffnet) | **JA** | **PASS.** `audit/writer.py:226` („Called by DomainEventBus.publish() within the active transaction") — Audit-Eintrag und Zustandsänderung teilen sich die Transaktion ⇒ ein Rollback verwirft beides. |

## 3. Wo endet die Transaktion **früher** als die fachliche Einheit?

| # | Ort | Analyse | Bewertung |
|---|---|---|---|
| E1 | `application/tasks.py:31-38` | `dispatch_outbox_events` fängt `Exception`, loggt via `logger.exception` und gibt `0` zurück — **ohne** Re-Raise. Celery verbucht die Task damit als **erfolgreich**. | **Kein Transaktionsproblem, aber ein Observability-Problem**: `total_run_count` steigt, `task_failure` feuert nie, `dispatch-outbox-events` steht in `django_celery_beat_periodictask` mit `total_run_count=222863` und **0 Fehlschlägen**, selbst wenn jeder Zyklus scheitert. → **284** |
| E2 | `application/event_bus.py:325-328` (T3) | Transaktion endet nach dem Claim, Dispatch außerhalb. | **Bewusst korrekt** (kein Lock über Net-I/O). Der Preis ist at-least-once ⇒ die *Abonnenten* müssen idempotent sein. Der einzige registrierte Abonnent ist es nicht. → **283** |
| E3 | `admin_ops/services/admin_restore_service.py` (bekanntes `124`) | Nicht-atomarer Restore — **nicht von mir verifiziert**, außerhalb des WP-6b-Auftragsumfangs. | **BLOCKED** (kein neuer Beleg) |

## 4. Negativbefunde (gesucht und nicht gefunden)

| Gesucht | Ergebnis |
|---|---|
| Multi-Write-Service **ohne** jede `atomic()`-Hülle in `application/` | **Keiner.** Alle 30 `def update_*/create_*/transition_*` in `application/*_service.py` sind in einer Datei mit `atomic()`-Nutzung; die Versions-Hülle `@atomic_transaction` ist im `optimistic_lock.py`-Docstring (Z. 71-72) als Voraussetzung verankert. |
| Transaktion zu **groß** (Lock über Langzeit-I/O) | **Keiner im Prod-Pfad.** Der einzige Kandidat (`event_bus`) hat die Grenze bewusst gesetzt (T3/E2). `llm_adapter`-Aufrufe laufen in Celery-Tasks außerhalb von Transaktionen. |
| `atomic()` **innerhalb** eines `atomic()` ohne Savepoint-Bedürfnis | `workflow/services.py:306` → `lifecycle_manager.py:290`. Hier **korrekt** (Savepoint-Semantik gewollt, T1). |
| Fehlende `atomic()` in `traceability/`, `baseline/`, `persistence/` | `traceability/trace_link_manager.py` (7), `baseline/store.py`, `persistence/artifact_backing.py:108` (Lock), `persistence/artifact_version_service.py:140` (Lock) — alle abgesichert. |

## 5. Fazit

**Transaktionsgrenzen: keine neue Critical/High-Lücke gefunden.** 12 von 12
geprüften fachlichen Multi-Write-Operationen sind atomar, und in **allen**
Fällen, in denen ein Lock nötig ist, wird er **vor** der Entscheidung genommen,
nicht danach (T5, T8, T10, T1) — das ist genau die Reihenfolge, die CR-06/CR-08
als Defekt beschrieben hat, und sie ist hier durchgängig eingehalten.

Die verbleibenden Probleme sind **keine** Transaktionsprobleme, sondern
(1) at-least-once ohne idempotenten Abonnenten (**283**),
(2) eine Task, die Fehler als Erfolg verbucht (**284**).
