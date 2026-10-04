---
adr_id: ADR-015
title: "Celery-Queue-Topologie: vier Queues mit echter Routing-Wirkung, task_acks_late als Teilentscheidung"
status: accepted
date: "2026-10-03"
deciders: [user, senior-developer]
affected_reqs: [REQ-077]
superseded_by: null
---

# ADR-015: Celery-Queue-Topologie — vier Queues mit echter Routing-Wirkung

**Status:** accepted
**Datum:** 2026-10-03
**Entscheider:** user (Freigabe-Instanz), senior-developer (Autor)
**Betroffene REQs:** REQ-077 (Celery-Routing/Queues definieren — separate Queues für `llm`,
`events` und `default` als Voraussetzung getrennter Skalierung, `docs/REQUIREMENTS.md:108`)

**Bezug:** Implementierungsplan **Kandidat iv** — „Warum vier Celery-Queues — Wirkung
herstellen, zurückbauen oder Prioritätsklassen?" (`docs/audit/2026-09/review/IMPLEMENTATION_PLAN.md:223`);
Workstream **B `RES`** „Resilience & Health: …, Celery-Topologie, Beat, Observability"
(`IMPLEMENTATION_PLAN.md:106`); Arbeitseinheiten `RES-04` (Celery-Queue-Topologie +
acks_late) und `RES-06` (teil) (`IMPLEMENTATION_PLAN.md:162,164`); expliziter Blockierer
**(B4) ADR iv blockiert RES-04/06** (`IMPLEMENTATION_PLAN.md:371-372`); Plan-Zeile
`W2 | fix/celery-topology | RES-04/05/06` (`IMPLEMENTATION_PLAN.md:492`).
Findings: `AUD-2026-09-120` (Critical), `-126` (High), `-132`/`-133`/`-056` (Medium),
`-125` (High), `-270` (High) (`docs/audit/2026-09/AUDIT_ADR_CANDIDATES.md:176`;
`docs/audit/2026-09/AUDIT_FINDINGS.md:195,224,225,277,289,306,307`).
Ist-Zustand: `backend/reqogniloom/celery.py:31-42` (vor Änderung);
`docs/audit/2026-09/review/plan/RESILIENCE_HEALTH.md:79-90,105-116`;
`docs/audit/2026-09/AUDIT_EVIDENCE/verification-2026-09-30.md:60-138`.

---

## Kontext

**Vier Queues sind deklariert, aber ohne Routing-Wirkung — der Kern ist eine
unentschiedene Architekturfrage, kein Einzelticket.**

**1. Die Deklaration widerspricht dem Verhalten.** `celery.py` deklariert vier Queues
(`default`, `llm`, `events`, `memory`) mit dokumentierter Skalierbarkeitsabsicht
(„Voraussetzung, jede Workload unabhängig zu skalieren", REQ-077). Tatsächlich fielen
die nackten `Queue(name)`-Deklarationen alle auf die kombu-Defaults
`exchange='default'` (direct) / `routing_key='default'` zurück, sodass die vier Queues
**identisch gebunden** waren. Eine Veröffentlichung über diesen benannten Exchange
matchte damit **alle vier** Queues gleichzeitig — eine Task lief **4×**
(`AUD-2026-09-120`; hermetisch über den kombu-`memory://`-Nachweis belegt und in der
Gegenprüfung bestätigt, `verification-2026-09-30.md:60-138`). Vier Queues ohne
Routing-Wirkung sind zugleich eine **falsche Abdeckungszusage**: `AUD-2026-09-350`
stuft Asynchronität als „Covered" ein, weil jede Task 4× läuft.

**2. Die Ack-Semantik war pre-ack.** `app.conf.task_acks_late` stand live auf `False`
(keine `acks_late`-Einstellung in `settings.py:777-951`) und
`task_reject_on_worker_lost` war nicht gesetzt: Die Nachricht wurde **vor** der
Ausführung bestätigt, ein OOM-/SIGKILL-Kill des Worker-Kindes verlor die laufende Task
**endgültig** (`AUD-2026-09-126`).

**3. Der Wartungs-Task war nie registriert.** `audit.archive_lifecycle_manager` ist in
`CELERY_BEAT_SCHEDULE['audit-monthly-archive']` eingetragen (`settings.py:865-867`),
aber der `@shared_task` lebt in `backend/audit/archive.py:448` — einer Datei, die
`app.autodiscover_tasks()` nicht importiert (es importiert nur `<app>.tasks`). Es gab
kein `audit/tasks.py`; `audit/apps.py` importiert `archive.py` nicht. Der Worker kannte
den Task nicht (live 6 Tasks) und hätte ihn als unregistriert abgelehnt — die monatliche
Audit-Retention lief nie (`AUD-2026-09-125`, `-270`).

**4. Kein bestehender ADR regelt die Task-Topologie.** `ADR-002_Event-Bus.md` betrifft
die Zustellung **innerhalb** der Anwendung (Producer/Consumer, Transaktions-Outbox),
**nicht** das Celery-Routing. Es gibt keinen inhaltlichen Konflikt, aber auch keine
Deckung. `AUD-2026-09-283`/`-284` (Outbox at-least-once, nicht-idempotenter Abonnent)
sind ein **eigenes** Thema (Zustellgarantie) und **nicht** Gegenstand dieser ADR.

**5. Keine REQ formuliert die Ack-Semantik.** REQ-077 deckt die Queue-Trennung
(„separate Queues für Task-Klassen"), aber **keine** REQ schreibt `task_acks_late` oder
die Zustellgarantie fest. Die Ack-Einstellung ist daher eine **Teilentscheidung dieses
ADR** (Kandidat iv, `IMPLEMENTATION_PLAN.md:223`: „`task_acks_late` als
Teilentscheidung"), keine bloße Umsetzung einer bestehenden Anforderung. Es wird
**keine** REQ neu erfunden und **keine** REQ-Datei geändert; `open_adrs` existiert
repo-weit nicht (`AUD-2026-09-333`), die REQ↔ADR-Verknüpfung bleibt Folgeaufgabe.

---

## Alternativen

### Option A: Echte Routing-Wirkung — jede Queue erhält eigenen Routing-Key — GEWÄHLT

**Beschreibung:** Die vier Queues bleiben (je eine hat einen distinkten Zweck und einen
passenden `task_routes`-Eintrag); jede Queue deklariert einen **eigenen** `routing_key`
auf dem geteilten `direct`-Exchange `default`. `task_routes` pinnen den Routing-Key
mit; der Default-Publish-Pfad wird explizit auf `default`/`default` festgelegt.
Zusätzlich `task_acks_late=True` und `task_reject_on_worker_lost=True` als
Teilentscheidung.

**Abwägung:** Stellt die **dokumentierte Absicht** (REQ-077) tatsächlich her, statt sie
zurückzubauen; eine Veröffentlichung über den benannten Exchange matcht danach **genau
eine** Queue. Der Fix ist zugleich die Voraussetzung dafür, dass `AUD-2026-09-350`
(„Asynchronität Covered") nicht auf einer Fanout-Illusion beruht. Die Ack-Erweiterung
schließt den endgültigen Task-Verlust bei Worker-Kill.

**Risiko:** MITTEL — Routing ist eine **stille** Änderung: ein falsch gerouteter Task
läuft nie und fällt erst beim Dispatch auf. Deshalb ist ein Routing-Wächter-Test Teil
der Entscheidung (siehe `## Entscheidung`, Punkt 5). Reversibel per Branch.

### Option B: Auf eine Queue zurückbauen — VERWORFEN

**Beschreibung:** Die drei zusätzlichen Queue-Namen entfernen, die Skalierbarkeitsabsicht
aus dem Kommentar streichen; `task_acks_late` und die Beat-Registrierung bleiben die
einzigen echten Reparaturen.

**Abwägung:** Kleinster Zustand, keine falsche Zusage. Er gibt aber die
Skalierbarkeit über Task-Klassen auf — bei Provider-Hot-Paths (LLM-Aufrufe,
latency-sensitiver Outbox-Dispatch) genau der falsche Ort. Zudem widerspricht er dem
Wortlaut von REQ-077 (separate Queues für `llm`/`events`/`default`) und macht die
dokumentierte Routing-Absicht still rückgängig.

**Risiko:** MITTEL — REQ-077 müsste dann angepasst werden (außerhalb dieser ADR); der
Skalierungshebel geht verloren.

### Option C: Neu modellieren als Prioritätsklassen — VERWORFEN

**Beschreibung:** Drei bis vier Queues nach **Dringlichkeit** (`critical` / `default` /
`bulk`) statt nach Worker-Klasse, mit expliziter Priorität im Task.

**Abwägung:** Macht Wartung (Retention, Archivierung) und KI-Kosten kontrollierbar.
Erzwingt aber eine Task-Umbenennung, der **alle** Aufrufer, Beat-Zeitpläne
(`application.dispatch_outbox_events`, `audit.archive_lifecycle_manager`) und
Monitoring-Regeln folgen müssten. Das ist eine größere Umstellung als der vorliegende
Defekt verlangt und wäre eine eigene Arbeitseinheit; die Kosten stehen in keinem
Verhältnis zum konkreten Befund (identische Bindungen).

**Risiko:** HOCH — breite Umbenennung, viele versteckte Aufrufer, kein Mehrwert
gegenüber A für die hier zu schließende Lücke.

---

## Entscheidung

**Option A wird gewählt: die vier Queues bleiben und erhalten echte Routing-Wirkung;
`task_acks_late`/`task_reject_on_worker_lost` werden als Teilentscheidung aktiviert;
der fehlende Wartungs-Task wird über `audit/tasks.py` registriert.** Verbindlich und
prüfbar:

1. **Per-Queue distinkter Routing-Key auf einem geteilten `direct`-Exchange.** Jede
   Queue deklariert `Queue(name, exchange=Exchange('default', type='direct'),
   routing_key=name)` für `name ∈ {default, llm, events, memory}`. Damit existiert je
   Queue genau ein `(exchange, routing_key)`-Paar.

2. **Expliziter Default-Publish-Pfad.** `task_default_queue='default'`,
   `task_default_exchange='default'`, `task_default_exchange_type='direct'`,
   `task_default_routing_key='default'`. Der Routing-Key `default` ist nur von der
   Queue `default` gebunden, sodass eine ungeroutete Task nicht auf
   `llm`/`events`/`memory` streuen kann.

3. **`task_routes` pinnen Queue und Routing-Key.** `llm_adapter.* → llm`, 
   `application.dispatch_outbox_events → events`, `memory.* → memory`, jeweils mit
   passendem `routing_key`; alles Ungematchte fällt auf `default`.

4. **Ack-Semantik: at-least-once statt pre-ack.** `task_acks_late=True` und
   `task_reject_on_worker_lost=True`. Eine bestätigte Task wird erst **nach** der
   Ausführung quittiert, und stirbt das Worker-Kind mid-task, wird die Nachricht
   requeued. **Konsequenz für Task-Bodies:** Sie müssen idempotent sein. Der
   Outbox-Konsument (`SELECT … FOR UPDATE SKIP LOCKED`) und die Audit-Archivierung
   (export-before-drop) sind es; wiederholte LLM-/Memory-Läufe bei Worker-Verlust
   werden als Preis dafür akzeptiert, keine Arbeit zu verlieren. Der Happy Path bleibt
   genau-einmal.

5. **Routing-Wächter-Test als Pflicht (Testbarkeit = Teil der Entscheidung).** Der
   Vertrag wird durch `backend/tests/test_celery_topology.py` bewacht: (a) distinkte
   `(exchange, routing_key)`-Paare, (b) `(default, default)` matcht genau die Queue
   `default`, (c) eine Veröffentlichung über den benannten Exchange trifft **genau
   eine** Queue (In-Memory-Transport), (d) `task_acks_late`/`task_reject_on_worker_lost`
   sind aktiv, (e) der Audit-Task ist registriert. Ein Verstoß macht den Test rot,
   **bevor** ein falsch gerouteter Task in Produktion still ausfällt.

6. **Registrierung des Wartungs-Tasks über den Autodiscovery-Hook.** `audit/tasks.py`
   importiert `run_monthly_archive_task` aus `audit/archive.py`; damit importiert
   `app.autodiscover_tasks()` das Modul und der `@shared_task`
   `audit.archive_lifecycle_manager` wird im Worker registriert. Das ist eine reine
   Registrierungs-Brücke ohne neue Verhaltenslogik.

7. **Bewusste Scope-Abgrenzung (nicht Teil dieser ADR):** `AUD-2026-09-132` (unbegrenzt
   wachsende `celery-task-meta-*`-Keys), `AUD-2026-09-133` (`mcp:session:*` und Broker
   teilen db0) und `AUD-2026-09-056` (kein `time_limit` auf `run_capability`) werden
   hier **nicht** entschieden. Sie betreffen Result-Backend-Retention,
   Redis-Namespace-Trennung bzw. Task-Timeouts — eigene Entscheidungen und Fixes,
   geführt in den jeweiligen Arbeitseinheiten (`RES-05`/`RES-07` bzw. INT/LLM).

---

## Konsequenzen

**Positiv:**

- **Die Routing-Absicht wird real:** Eine Veröffentlichung über den benannten Exchange
  trifft genau **eine** Queue statt aller vier; REQ-077 ist erfüllt statt nur
  deklariert. Der 4×-Fanout (`AUD-2026-09-120`, Critical) ist strukturell unmöglich.
- **Kein endgültiger Task-Verlust:** `task_acks_late` + `task_reject_on_worker_lost`
  liefern at-least-once; ein OOM-/SIGKILL-Kill requeued die laufende Task
  (`AUD-2026-09-126`).
- **Die monatliche Audit-Retention läuft tatsächlich:** `audit.archive_lifecycle_manager`
  ist im Worker registriert (`AUD-2026-09-125`/`-270`), der auf `audit_entry` sonst nie
  ausgeführt worden wäre.
- **Wächter statt stiller Fehlrouting:** Der Test aus Entscheidung Punkt 5 ist rot,
  sobald die Topologie verwässert wird — die stille Änderung wird beobachtbar.

**Negativ:**

- **Task-Bodies müssen idempotent bleiben/sind es zu halten.** at-least-once bedeutet,
  dass ein wiederholter Lauf möglich ist; ein nicht-idempotenter Handler erzeugt
  Doppelwirkung. Für LLM-/Memory-Läufe wird eine Wiederholung nach Worker-Verlust
  bewusst in Kauf genommen.
- **Stale Broker-Bindings müssen gepurged werden.** Kombu entfernt Bindings, die aus
  einer früheren Topologie stammen, **nicht** automatisch. Ein auf einem alten Stack
  erzeugtes Alt-Binding (`default` → `default` + `events`) überlebt den Neustart und
  würde den Fanout latent halten, bis es aus dem Broker-Set entfernt ist
  (Nachweis/Behebung: siehe Umsetzungsvermerk unten).
- **Kein Ersatz für die Nachbar-Findings:** Result-Backend-Retention (`-132`),
  Namespace-Trennung (`-133`) und Task-Timeouts (`-056`) bleiben offen; das ADR
  behauptet keine Deckung, die es nicht liefert.
- **Keine REQ trägt die Ack-Semantik:** `task_acks_late` ist durch keine REQ
  festgeschrieben; die Zuordnung zu REQ-077 deckt nur die Queue-Trennung. Eine
  getrackte REQ↔ADR-Verknüpfung (`open_adrs`) fehlt repo-weit (`AUD-2026-09-333`) und
  bleibt Folgeaufgabe.

---

## Folgeaufgaben (nicht Teil dieser Entscheidung)

1. **`open_adrs`-Feld einführen** (`AUD-2026-09-333`), damit REQ-077 dieses ADR
   referenzieren kann. Bis dahin wird **keine** REQ-Datei geändert.
2. **Result-Backend-Retention** (`AUD-2026-09-132`): `result_expires` bzw.
   Cleanup-Policy für `celery-task-meta-*` festlegen (`RES-05`/`RES-07`).
3. **Redis-Namespace-Trennung** (`AUD-2026-09-133`): MCP-Sessions und Celery-Broker
   in getrennte Redis-DBs führen, damit ein `FLUSHDB` keine laufenden Sessions zerstört.
4. **Task-Timeouts** (`AUD-2026-09-056`): `time_limit`/`soft_time_limit` für
   `llm_adapter.run_capability` setzen und gegen die LLM-Retry-Strategie abstimmen.
5. **Lifecycle-Nachweis:** DoD-/Traceability-Prüfung durch `validator`; Statuswechsel
   erfolgt ausschließlich durch `se-architect`/User.

---

## Umsetzungsvermerk (2026-10-03, Port von `994ed0b3`)

Die Entscheidung ist umgesetzt und live belegt:

- **Topologie:** `app.conf.task_queues` deklariert die vier Queues je mit eigenem
  `routing_key` auf dem geteilten `direct`-Exchange `default`; der Default-Publish-Pfad
  ist explizit gesetzt (`task_default_exchange='default'`,
  `task_default_routing_key='default'`). Live-`_lookup('default', <key>)` liefert je
  Routing-Key **genau eine** Queue (`default→default`, `llm→llm`, `events→events`,
  `memory→memory`).
- **Ack-Semantik:** `task_acks_late=True`, `task_reject_on_worker_lost=True` (live im
  Worker bestätigt).
- **Registrierung:** `backend/audit/tasks.py` neu; `celery inspect registered` zeigt
  **8** Tasks inkl. `audit.archive_lifecycle_manager` (war 6).
- **Wächter:** `backend/tests/test_celery_topology.py` (8 Tests) deckt den Vertrag
  (RED 6 failed / 2 passed vor dem Port → GREEN 8 passed danach).
- **Stale-Binding-Hinweis:** Ein auf dem laufenden Stack aus der Alt-Topologie
  stammendes Binding `default\x06\x16\x06\x16events` in `_kombu.binding.default` wurde
  entfernt (`SREM`), damit der Lookup `default` nicht latent auf `events` streut
  (Kombu purged entfernte Bindings nicht selbst — siehe Konsequenzen).

---

*Erstellt durch `senior-developer` am 2026-10-03 als Doku-Artefakt zum Port von
`994ed0b3` ("give each celery queue a distinct routing key") auf den Zweig
`feat/w2-p1`. Status `accepted` seit 2026-10-03; die Entscheidung ist zugleich die
ADR-Freigabe für `RES-04`/`RES-06` (Blockierer B4). Kein Produktcode in diesem
Doku-Artefakt, keine Migration, keine REQ-ID erfunden; Belege gegen
`docs/audit/2026-09/AUDIT_ADR_CANDIDATES.md`, `AUDIT_FINDINGS.md`,
`review/IMPLEMENTATION_PLAN.md` und `review/plan/RESILIENCE_HEALTH.md` geprüft.*
