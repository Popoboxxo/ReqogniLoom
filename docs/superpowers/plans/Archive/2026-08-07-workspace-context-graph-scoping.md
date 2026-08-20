# Workspace Context Graph — Scoping & Design

> **Kein Implementierungsplan.** Dieses Dokument ist die Vorarbeit zu GitHub-Issue
> `Popoboxxo/ReqogniLoom#377`. Es enthält keine `- [ ]`-Tasks, weil vor dem Plan noch
> Produktentscheidungen offen sind (siehe §11). Ergebnis dieses Dokuments ist ein
> v1-Zuschnitt plus fünf abgetrennte Folge-Issues.
>
> **Update 2026-08-07.** Alle v1-blockierenden Fragen sind entschieden: §11.1 (abgeleitete
> Kanten gleichwertig sichtbar, ein-/ausblendbarer Marker, Kontrastfarbe aus dem Theming-Konzept,
> Coverage/VCRM bleiben strikt auf `pl_tracelink` beschränkt), §11.2 (`contradicts` nie
> materialisiert, nur Vorschlag), §11.4 (Staleness-Vertrag wie empfohlen), §11.5
> (Embedding-Generatoren verweigern bei `provider=mock`, wie empfohlen), §11.8
> (`context.*`-Präfix wie im Issue benannt), und der v1-Zuschnitt aus §9 selbst ist bestätigt.
> §11.3, §11.6, §11.7 bleiben offen, blockieren aber nur Folge-Issues, nicht v1. **Nächster
> Schritt:** dieses Dokument in einen task-by-task-Plan im Stil von
> `docs/superpowers/plans/Archive/2026-08-05-mcp-plugin-distribution.md` überführen, sobald die
> Umsetzung angestoßen werden soll.

**Goal:** Beantworten, was „Zusammenhangs- und Kontext-Speicher pro Workspace" in *dieser*
Codebasis konkret bedeutet — und ehrlich trennen, welcher Teil von #377 neue Substanz ist,
welcher Teil bereits gebaut ist und nur nicht so heißt, und welcher Teil in ein eigenes Issue
gehört.

**Kernbefund vorweg:** Der Graph existiert. `pl_artifact` ist die Knoten-, `pl_tracelink` die
Kantentabelle; `backend/traceability/service.py` implementiert bereits Impact-Analyse,
Pfadsuche und Zyklenerkennung über rekursive CTEs mit In-Path-Cycle-Guard, Depth-Clamp,
Row-Limit und einer 200-ms-SLA. Was fehlt, ist nicht „ein Graph", sondern drei konkrete Dinge:
**(a)** eine Schicht *abgeleiteter, semantischer* Kanten neben den vom Menschen gepflegten
Trace-Links, **(b)** eine automatische, inkrementelle Pflege dieser Schicht am bestehenden
Event-Bus, und **(c)** eine einzige Leseschnittstelle (`context.*`), die harte und weiche
Kanten zusammen ausliefert. Der Rest von #377 ist Komposition vorhandener Infrastruktur.

**Tech Stack (Ist-Zustand, verifiziert):** Django 4.2 / PostgreSQL 16 **mit pgvector**
(`persistence/migrations/0024_requirement_embedding.py`, HNSW-Indizes auf `Requirement.embedding`,
`TraceLink.embedding`, `IcdVersion.embedding`), Redis 7 als Cache *und* Celery-Broker,
Celery 5.3 mit `django_celery_beat.schedulers:DatabaseScheduler`, React 18 mit
**`@xyflow/react` 12 und `@dagrejs/dagre` 3 bereits als Dependencies**. Kein Neo4j, kein
zusätzlicher Datastore.

---

## 1. Bestandsaufnahme — was tatsächlich schon da ist

Alle Angaben aus dem Quellcode auf `feat/mcp-plugin-distribution`, Stand 2026-08-07.

### 1.1 Graph-Datenmodell und Traversierung

| Baustein | Ort | Zustand |
|---|---|---|
| Knoten | `persistence.Artifact` (`pl_artifact`) — FK auf `Workspace`, `artifact_type`, `custom_fields` JSONB (GIN) | vollständig |
| Kanten | `persistence.TraceLink` (`pl_tracelink`) — FK `source`/`target` → `Artifact`, `link_type` CharField, Composite-Index `idx_tracelink_graph`, Unique `(source,target,link_type)` | vollständig |
| Kantentypen | `traceability/types.py::LinkType` — 14 Werte, plus `SE_LINK_SEMANTICS` Endpunkt-Matrix (se_mode) | vollständig |
| Transitive Hülle | `traceability/query_engine.py::QueryEngine.query(transitive=True)` — `WITH RECURSIVE`, SLA 200 ms, Statement-Timeout 5 s, `MAX_GRAPH_ITEMS=100_000` | vollständig |
| Impact-Analyse | `traceability/service.py::impact_analysis()` — rekursive CTE, `direction=outgoing\|incoming\|both`, `link_types`-Whitelist, Depth-Clamp 20, Limit 1000, `_enrich()` für Titel/UID | vollständig, REST-exponiert (`rest_api/views.py:1995`, `:2176`) |
| Pfadsuche | `traceability/service.py::find_path()` — BFS-CTE, alle kürzesten Pfade | vollständig, REST-exponiert |
| Zyklen | `traceability/service.py::detect_cycles()` | vollständig, REST-exponiert |
| Ganzer Graph | `traceability/services.py::collect_trace_graph(workspace_id)` → `TraceGraphData` | vollständig (wird von Baselines genutzt) |

**Konsequenz:** Drei der vier Beispiel-Abfragen aus dem Issue („Kontext von X", „was ist von
Änderung an Y betroffen", „wie hängen Z und W zusammen") sind heute schon beantwortbar —
über `impact_analysis`, `find_path` und `traceability.query`. Sie sind nur nicht als
*ein* Kontext-Aufruf gebündelt und enthalten ausschließlich harte, handgepflegte Kanten.

### 1.2 Semantik-Infrastruktur (pgvector)

pgvector ist **installiert und produktiv**, nicht geplant. `docker/postgres/initdb/10-pgvector.sh`
legt die Extension als Superuser in `template1` an; `llm_adapter/embedding_service.py`
erzeugt 1536-dim Embeddings (OpenAI `text-embedding-3-small`).

Aber: Embeddings existieren nur auf **drei** Entitäten — `Requirement` (befüllt in
`requirement_service.py:547`), `TraceLink` (`trace_link_service.py:373`), `IcdVersion`
(`icd/icd_manager.py:61`). **`ArchitectureElement`, `TestCase`, `StakeholderNeed`, `Goal`,
`GlossaryTerm`, `Adr`, `Risk`, `Issue` haben keine Embedding-Spalte.** Eine embedding-basierte
Ähnlichkeitskante über den gesamten Artefaktbestand ist daher heute nicht möglich, ohne
Migration + Backfill für die fehlenden Typen.

Zweite Einschränkung, die im Issue nicht adressiert ist: `generate_embedding()` liefert bei
`provider="mock"` — dem **Default dieses Projekts** — einen deterministischen Pseudo-Zufallsvektor.
Der ist stabil, aber semantisch bedeutungslos. Die gesamte Semantikschicht ist ohne einen
echten Embedding-Provider (heute nur `openai`) inhaltlich wertlos. Das gehört als
Betriebsvoraussetzung ins Issue, nicht in die Fußnote.

Wichtig zur Einordnung: `artifact.search` ist **keine** Vektorsuche. `application/search_service.py`
macht PostgreSQL-Volltext (`tsvector`/`ts_rank`) plus einen lexikalischen Substring-Pass
(Issue #345). Das Issue #377 nennt „`artifact.search` / RAG-Suche mit pgvector (#18)" als
Andockpunkt — die beiden Dinge sind in dieser Codebasis getrennt. `traceability_suggest_service.py`
sagt es im Modul-Docstring ausdrücklich: „It never queries a vector index and never depends on
pgvector — a deferred, explicitly out-of-scope spike."

### 1.3 Event-System — der wunde Punkt

`backend/application/event_bus.py` ist ein sauber gebauter Transactional Outbox:
`publish()` hängt den INSERT an `transaction.on_commit`, `poll_and_dispatch()` klaut sich
Zeilen per `SELECT FOR UPDATE (skip_locked)`, retryt fünfmal, schiebt dann in die DLQ.
Der Beat-Task `application.dispatch_outbox_events` läuft **alle 5 Sekunden**
(`reqogniloom/settings.py:558`) auf der eigenen Queue `events`.

Drei Befunde, die ein Design ignorieren würde und dann teuer bezahlt:

**Befund A — der Bus hat in Produktion null Subscriber.**
Der einzige geschriebene Subscriber ist `application/webhook_dispatcher.py`. Seine
Registrierungsmethode `subscribe_to_events()` wird ausschließlich aus
`application/tests/test_webhook_dispatcher.py` aufgerufen — in keinem `apps.py::ready()`,
in keinem Modul, in keinem Startup-Pfad. Der Outbox-Poller dispatcht seit jeher ins Leere.
Der erste echte Subscriber muss also nicht nur sich selbst bauen, sondern die
Registrierungs-Infrastruktur **erstmals produktiv beweisen**. Das ist billig, aber es ist
Arbeit, und es darf nicht als „bestehende Infrastruktur, einfach andocken" veranschlagt werden.

Nicht verwechseln: `backend/audit/apps.py::ready()` registriert `AuditLogWriter` — aber auf
`audit/events.py::DomainEventBus`, einer **gleichnamigen, komplett separaten Klasse** ohne
Outbox, nur fürs Audit-Log. Zwei Klassen, ein Name, unterschiedliche Semantik. Wer
`from ... import DomainEventBus` schreibt, ohne hinzusehen, baut sich einen Heisenbug.

**Befund B — Trace-Link-Änderungen erzeugen überhaupt keine Domain-Events.**
`application/trace_link_service.py` ruft an genau einer Stelle `self._audit(...)` (Zeile 344)
und **nie** `_emit_event`. `DomainEventOutbox.EventType` (`application/models.py:40`) kennt
keinen einzigen `TraceLink*`-Wert. Akzeptanzkriterium 1 aus #377 — „Graph wird bei CRUD/**Trace**-Änderungen
automatisch aktualisiert" — ist mit dem heutigen Event-Katalog schlicht nicht erfüllbar.
Neue Event-Typen plus Emission in `create/update/delete/batch_create/batch_delete` sind
Pflichtvorarbeit.

**Befund C — der Event-Katalog ist bereits jetzt inkonsistent.**
Zwei separate Probleme:

1. *Nicht deklarierte Typen.* `stakeholder_need_service.py:129` emittiert `"StakeholderNeedCreated"`,
   `goal_service.py:177` `"GoalCreated"`, `main_goal_service.py:269` `"MainGoalCreated"` —
   keiner dieser Strings steht in `DomainEventOutbox.EventType.choices`. Django erzwingt
   `choices` nicht auf DB-Ebene, die Zeilen landen also sauber im Outbox; aber ein Subscriber,
   der sich per Iteration über `EventType.choices` registriert, sieht Needs und Goals nie.
2. *Uneinheitliche `entity_id`-Semantik.* `requirement_service.py:252` emittiert
   `RequirementCreated` mit `entity_id=requirement.id` (Domänen-ID), `artifact_service.py:281`
   emittiert **denselben Event-Typ** mit `entity_id=artifact.id` (Artefakt-ID). Der Graph ist
   über `Artifact.id` verdrahtet (`TraceLink.source/target` → `Artifact`). Ein Projektor muss
   also je nach Produzent unterschiedlich auflösen. Das ist exakt die Fehlerklasse, die in
   diesem Repo schon zweimal als 404 aufgeschlagen ist (`_resolve_artifact_id`, Issues #237/#264).

### 1.4 Per-Workspace-Konfiguration — vorhandene Präzedenzfälle

- **Felder direkt auf `Workspace`**: `goals_enabled`, `goals_ai_enabled`, `language`,
  `decomposition_link_type`, `default_link_type`. Einfach, aber `pl_workspace` ist eine sehr
  heiße Tabelle (in praktisch jeder Query).
- **JSON auf `Workspace`**: `preset` und `ai_prompts` — letzteres trägt bereits Overrides wie
  `ai_prompts["context_token_budgets"]` (siehe `cross_cutting.py::_get_context_token_budget`).
  Schemalos, kein Constraint, keine Migration nötig — und genau deshalb schwer zu validieren.
- **Eigene Settings-Tabelle**: `persistence.LlmSettings` (`pl_llm_settings`) — **tenant**-scoped,
  nicht workspace-scoped, Singleton per Unique-Constraint, eigene RLS-Policy-Migration
  (`0026_add_llm_settings.py`). Der Docstring dokumentiert eine harte, teuer gelernte Regel
  (Issue #276): *Zeilenexistenz ist bedeutungstragend.* Ein vorhandener Row überschreibt
  bedingungslos die Umgebungs-Konfiguration, deshalb darf ein Lesepfad ihn niemals anlegen.

### 1.5 Frontend

`@xyflow/react` und `@dagrejs/dagre` sind bereits installiert und produktiv im Einsatz — aber
nur im **WorkflowEditor** (`WorkflowCanvas.tsx`, `StateNode.tsx`, `TransitionEdge.tsx`).
`TraceabilityView.tsx` (27 KB) und `ImpactView.tsx` (19 KB) rendern **ohne** React Flow.
Eine Graph-Ansicht ist damit deutlich billiger als eine Greenfield-Schätzung nahelegt: die
Bibliothek, das Layout-Paket, das CSS-Import-Pattern und ein Custom-Node/Edge-Beispiel
existieren alle schon.

### 1.6 MCP-Oberfläche

`workspace.get_context` existiert bereits (`mcp_server/tools/cross_cutting.py:845`) und ist
genau das Agenten-Orientierungswerkzeug, das #377 in der Motivation beschreibt: Preset,
Terminologie, Entity-Counts, Entity-Listen, `recent_changes`, Token-Budget-Truncation über
drei `depth`-Stufen. Ein neuer `context.*`-Namensraum, der dasselbe Wort benutzt, aber etwas
anderes meint, ist eine Verwechslungsfalle für genau die Konsumenten, denen das Feature helfen
soll (§7.4).

---

## 2. Architekturempfehlung: kein neuer Graph-Store

**Empfehlung: Variante (c) — weder eine neue Adjazenz-Tabellenfamilie *als Ersatz* noch eine
Graph-DB. Stattdessen: die vorhandenen Tabellen bleiben der Graph, und es kommen genau zwei
neue Tabellen dazu — eine für *abgeleitete* Kanten, eine für Zustand/Konfiguration.**

### 2.1 Warum nicht (a) „Nodes + Edges neu modellieren"

Variante (a) aus der Fragestellung — ein Paar neuer `nodes`/`edges`-Tabellen — wäre eine
denormalisierte Kopie von `pl_artifact` + `pl_tracelink`. Damit handelt man sich das
Dual-Write-Konsistenzproblem *innerhalb derselben Datenbank* ein, ohne einen einzigen
Fähigkeitsgewinn: rekursive CTEs laufen auf der Originaltabelle genauso gut, der Index
`idx_tracelink_graph` existiert, die 200-ms-SLA wird gehalten. Eine Kopie müsste zusätzlich
gegen Baseline-Snapshots, Coverage-Berechnung und den SE-Auditor konsistent gehalten werden,
die alle direkt auf `pl_tracelink` lesen.

### 2.2 Warum nicht (b) Graph-DB (Neo4j o. ä.)

Fünf Gründe, alle aus dem Ist-Zustand dieses Stacks:

1. **Zweite Konsistenzdomäne.** Ein externer Graph-Store erzwingt Dual-Write zwischen Postgres
   und der Graph-DB — exakt das Problem, für das der Transactional Outbox in
   `application/event_bus.py` gebaut wurde, nur jetzt über eine Prozessgrenze und ohne
   gemeinsame Transaktion.
2. **Mandantentrennung müsste neu gebaut werden.** Die Isolation liegt heute in
   PostgreSQL-RLS-Policies (`persistence/migrations/0003_rls_policies.py`, `0010_…`, `0026_…`)
   mit `current_setting('app.current_tenant')`. In Cypher gibt es dafür kein Äquivalent; die
   Trennung müsste in Anwendungscode reimplementiert werden — ein Sicherheits-Rückschritt.
3. **Disaster Recovery.** `admin_ops/` (Backup/Restore) kennt genau einen Datastore. Ein zweiter
   bedeutet zweite Backup-, Restore- und Point-in-Time-Semantik plus die Frage, was ein
   Restore bei divergierenden Snapshots bedeutet.
4. **Der Datenumfang rechtfertigt es nicht.** Workspace-Graphen liegen hier bei
   Größenordnung 10²–10⁴ Knoten. `MAX_GRAPH_ITEMS` steht bei 100 000. Der Punkt, an dem eine
   rekursive CTE gegen eine native Graph-Engine verliert, liegt Größenordnungen darüber.
5. **Der Semantikteil braucht keinen Graph, sondern Vektoren** — und pgvector ist bereits da.

Ein sechster, praktischer Grund: `docker-compose.yml` hat fünf Services. Ein sechster mit
JVM-Speicherbedarf ändert die Einstiegshürde für lokale Entwicklung spürbar.

### 2.3 Was tatsächlich neu gebaut wird

Zwei Tabellen in einer neuen Layer-1-App `backend/context_graph/` (parallel zu
`traceability/`, `baseline/`, `workflow/`), exponiert über eine Layer-2-Fassade
`application/context_service.py` gemäß ADR-01. REST und MCP sprechen ausschließlich mit
der Fassade, nie mit der App.

**`ContextEdge` (`cg_context_edge`)** — abgeleitete, nicht vom Menschen gepflegte Kanten:

```
tenant           FK  (TenantScopedModel, RLS-Policy)
source           FK -> persistence.Artifact  (CASCADE)
target           FK -> persistence.Artifact  (CASCADE)
edge_kind        CharField  choices: related | influences | contradicts | refines | shares-term
origin           CharField  choices: derived-glossary | derived-embedding | derived-cochange | llm-suggested
confidence       FloatField 0..1
evidence         JSONB       # z.B. {"term_id": ..., "cosine": 0.83, "audit_entries": [...]}
generator        CharField   # Generator-Name + Version, für gezielte Invalidierung
generated_at     DateTimeField
UNIQUE (source, target, edge_kind, origin)
INDEX (tenant, source), (tenant, target), (tenant, edge_kind)
```

**`WorkspaceContextSettings` (`cg_workspace_context_settings`)** — Konfiguration *und*
Betriebszustand (§5).

**Entscheidend, und die wichtigste Designregel dieses Dokuments: abgeleitete Kanten werden
NICHT als neue `LinkType`-Werte in `pl_tracelink` abgelegt.** `LinkType` speist die
SE-Endpunkt-Matrix (`SE_LINK_SEMANTICS`), die Coverage-Berechnung
(`traceability/coverage_calculator.py`), den VCRM-Report, Baseline-Snapshots und den
SE-Auditor. Ein maschinell erratener „related"-Link in dieser Tabelle würde
Abdeckungskennzahlen, Baseline-Diffs und Konformitätsbefunde still verändern — in einem
System, das für formale Systems-Engineering-Workflows mit Extended-Rigor gedacht ist, ist
das kein Schönheitsfehler, sondern ein Integritätsbruch. Harte Kanten sind eine Aussage des
Menschen; abgeleitete Kanten sind eine Vermutung der Maschine. Sie gehören in getrennte
Tabellen und in getrennte Antwortfelder.

### 2.4 Lesepfad

`context.query` liest **nicht** aus einem eigenen materialisierten Snapshot, sondern
komponiert zur Laufzeit:

```
harte Kanten     -> traceability.service.impact_analysis() / query_engine.query()
weiche Kanten    -> ContextEdge (indizierte Punktabfrage, kein CTE)
Anreicherung     -> traceability.service._enrich() (Titel/UID) + Risks/Issues des Workspace
Cache            -> django.core.cache (Redis, settings.CACHES) — Key je (artifact_id, depth,
                    include-Set, edge-Watermark), invalidiert durch die Watermark
```

Ein materialisiertes `cg_context_snapshot` (fertiges JSONB pro Artefakt) ist bewusst **v2**:
es ist eine reine Latenz-Optimierung und bringt eine dritte Konsistenzebene mit. Erst messen,
dann materialisieren.

---

## 3. Event-sourced Pflege am bestehenden Bus

### 3.1 Ein Subscriber, kein zweites Event-System

Genau ein neuer Subscriber: `context_graph/projector.py::ContextGraphProjector`, registriert
in `ContextGraphConfig.ready()` über `get_event_bus().register_subscriber(...)`. Formal
identisch zum Muster in `audit/apps.py::ready()` — aber auf `application.event_bus`, nicht auf
`audit.events` (§1.3, Befund A).

```
handle_event(event: DomainEvent) -> None
  1. settings = WorkspaceContextSettings für event.workspace_id lesen (Redis-gecacht)
     -> fehlt oder enabled=False: sofort return (kein Fehler, Event gilt als verarbeitet)
  2. artifact_id = _resolve_artifact_id(event)      # siehe 3.3
  3. je nach event_type: betroffene ContextEdges des Artefakts als stale markieren,
     Generatoren für dieses Artefakt neu laufen lassen (Upsert), verwaiste Kanten löschen
  4. settings.last_event_id / last_projected_at fortschreiben
```

Der Projektor läuft im Celery-Worker auf der `events`-Queue, weil er im
`dispatch_outbox_events`-Callback hängt. Diese Queue ist ausdrücklich latenzsensitiv (5-s-Takt,
Kommentar in `reqogniloom/celery.py`). Der Projektor darf dort deshalb **keine LLM- oder
Embedding-Aufrufe** machen. Alles, was Netzwerk kostet, wird als eigener Task auf die
`default`-Queue delegiert (`task_routes` in `celery.py` erweitern).

### 3.2 Idempotenz

`poll_and_dispatch()` dokumentiert seine Zustellgarantie ausdrücklich als *at-least-once*:
„a worker crash after dispatch but before the row below is marked published will re-deliver
this event". Der Projektor muss das aushalten. Er tut es durch Upsert auf
`UNIQUE (source, target, edge_kind, origin)` plus vollständige Neuberechnung der Kanten
*eines* Artefakts statt inkrementellem Delta. Kein Zählerhochzählen, kein Append.

Subscriber-Fehler werden vom Bus geloggt und geschluckt (`dispatch_to_subscribers`), blockieren
also weder andere Subscriber noch den Poller. Das ist gewollt — bedeutet aber, dass ein still
scheiternder Projektor unbemerkt driftet. Deshalb gehört ein `last_error` + `last_projected_at`
in die Settings-Tabelle und eine Staleness-Anzeige in jede `context.*`-Antwort (§7.3).

### 3.3 Pflichtvorarbeit vor dem ersten Projektor-Commit

Diese drei Punkte sind keine Politur, sondern Voraussetzung dafür, dass Akzeptanzkriterium 1
überhaupt erfüllbar ist:

1. **Trace-Link-Events einführen.** `TraceLinkCreated` / `TraceLinkUpdated` / `TraceLinkDeleted`
   in `DomainEventOutbox.EventType`, emittiert aus `application/trace_link_service.py` —
   inklusive der Batch-Pfade `batch_create_trace_links` / `batch_delete_trace_links`.
2. **Undeklarierte Event-Typen deklarieren.** `StakeholderNeedCreated/Updated/Deleted`,
   `GoalCreated`, `MainGoalCreated` in `EventType` aufnehmen (§1.3 Befund C.1). Rein additiv,
   keine Datenmigration.
3. **`artifact_id` in jede Event-Payload.** Statt im Subscriber per Typ-Raten aus `entity_id`
   auf das Artefakt zu schließen (die `_resolve_artifact_id`-Falle), tragen die Produzenten
   die Artefakt-ID additiv in `payload["artifact_id"]` ein. Additiv, rückwärtskompatibel,
   und es macht den Subscriber trivial. Für Altbestand im Outbox greift ein Resolver-Fallback.

Zusätzlich, als eigener kleiner Schritt: **einen produktiven Subscriber-Registrierungspfad
erstmals belegen** (§1.3 Befund A) — mit einem Integrationstest, der eine echte Mutation macht,
den Outbox-Poller laufen lässt und beobachtet, dass der Projektor gefeuert hat. Ohne diesen
Test ist die gesamte „event-sourced"-Zusage unbewiesen.

### 3.4 Ein- und Ausschalten ohne Replay

Der Toggle greift **im Projektor**, nicht im `publish()`. Events werden immer geschrieben,
ein deaktivierter Workspace lässt sie nur ins Leere laufen. Wichtig: das Wiedereinschalten
kann **nicht** per Event-Replay aufholen — die Outbox ist keine Retention-Historie
(publizierte Zeilen bleiben zwar heute liegen, aber das ist ein unbeabsichtigter Nebeneffekt,
kein Vertrag, und die Tabelle wächst unbegrenzt). Einschalten löst deshalb einen **vollen
Rebuild aus dem aktuellen Zustand** aus, nicht aus dem Event-Strom. Das ist ohnehin die
robustere Semantik und macht `context.rebuild` zum ersten Werkzeug, das gebaut werden muss.

---

## 4. Cron / Celery Beat

### 4.1 Entwurf: ein Beat-Eintrag, Fan-out im Task

Zwei Optionen, eine Empfehlung.

**Option A (empfohlen) — ein globaler Beat-Eintrag, Fan-out im Task.**

```python
# reqogniloom/settings.py  (Ergänzung zu CELERY_BEAT_SCHEDULE)
"context-graph-refresh-due": {
    "task": "context_graph.refresh_due_workspaces",
    "schedule": timedelta(minutes=1),
},
```

`refresh_due_workspaces()` liest alle `WorkspaceContextSettings` mit
`enabled=True AND schedule_enabled=True`, prüft je Zeile `last_refresh_at` gegen das
konfigurierte Intervall und startet für fällige Workspaces `refresh_workspace_graph.delay(ws_id)`
auf der `default`-Queue. Ein Redis-Lock (`cache.add(f"cg:refresh:{ws_id}", ..., timeout)`)
verhindert Überlappung desselben Workspace mit sich selbst.

**Option B — je Workspace ein `django_celery_beat.PeriodicTask` + `CrontabSchedule`.**
Näher an der Issue-Formulierung („Cron-Expression pro Workspace") und im Django-Admin sichtbar.
Kostet dafür N Scheduler-Zeilen, die gegen den Workspace-Lebenszyklus synchron gehalten werden
müssen: `is_active=False` (Soft-Delete), harte Löschung, Sandbox-Klone über `parent_workspace`
(SN-33). Jede Änderung löst zudem einen Beat-Schedule-Reload aus.

**Empfehlung: A.** Ein Scheduler-Eintrag, keine Lebenszyklus-Kopplung, keine verwaisten Zeilen.
Option B bleibt als spätere Option offen, falls Betreiber Sichtbarkeit einzelner Tasks fordern.

### 4.2 Intervall in v1, Cron-Expression später

Eine echte Cron-Expression braucht einen Parser. `backend/requirements.txt` listet exakt zwei
einschlägige Pakete — `celery>=5.3,<6.0` und `django-celery-beat>=2.9.0,<3.0`. **`croniter`
ist nicht dabei.** `django-celery-beat` bringt zwar `CrontabSchedule` als Modell mit, aber
das ist an den DatabaseScheduler gekoppelt und liefert keinen freistehenden „ist jetzt
fällig"-Evaluator für Option A. Deshalb: v1 speichert `refresh_interval_minutes: int | null` — null Dependencies,
deckt den realistischen Bedarf („alle 15 Minuten", „nächtlich") ab. Volle Cron-Expressions
sind ein sauber abtrennbares Folge-Issue.

### 4.3 Was der periodische Lauf überhaupt tut

Wenn der Event-Pfad korrekt ist, ist der Cron-Lauf **kein** zweiter Aktualisierungsmechanismus,
sondern eine Selbstheilung. Das ist eine Designaussage, die im Issue fehlt und die den Umfang
deutlich senkt. Der periodische Lauf existiert für:

- Kanten, deren Ableitung von etwas abhängt, das *kein* Event erzeugt (Ablauf von Zeitfenstern,
  Änderungen der Glossar-Synonyme, Audit-Log-Archivierung),
- Nachziehen nach einem still fehlgeschlagenen Subscriber (§3.2),
- Neuberechnung nach einem Generator-Versionswechsel (`ContextEdge.generator`),
- Erstbefüllung nach dem Einschalten (§3.4).

---

## 5. Per-Workspace-Konfiguration

**Empfehlung: eigenes Modell `WorkspaceContextSettings` in `context_graph/models.py`,
`TenantScopedModel`, OneToOne auf `Workspace`, eigene RLS-Policy-Migration.**

```
workspace                OneToOne -> persistence.Workspace (CASCADE), UNIQUE
enabled                  Bool, default False        # Event-Pflege an/aus (AK 2)
schedule_enabled         Bool, default False        # periodischer Lauf an/aus (AK 3)
refresh_interval_minutes Int, null                  # v1 statt Cron-Expression
provider                 CharField, default "embedded"   # ausschließlich "embedded" in v1
enabled_generators       JSONB, default []          # z.B. ["glossary"]
last_projected_at        DateTime, null
last_refresh_at          DateTime, null
last_event_id            UUID, null                 # Watermark / Cache-Invalidierung
last_error               Text, blank
node_count / edge_count  Int, default 0             # für UI + Health
```

Begründung gegen die Alternativen:

- **Nicht als Felder auf `Workspace`**: die Tabelle trägt Betriebszustand (Watermarks, Fehler,
  Zähler), nicht nur Konfiguration. Betriebszustand gehört nicht in eine Tabelle, die in
  praktisch jeder Query mitgelesen wird.
- **Nicht in `Workspace.ai_prompts` / `Workspace.preset` JSONB**: schemalos, kein Constraint,
  keine Migration — und damit auch kein Ort, an dem ein Default dokumentiert oder validiert
  werden kann. Für einen reinen Prompt-Override ist das in Ordnung, für einen Schalter mit
  Nebenwirkungen auf einen Hintergrundprozess nicht.
- **Nicht wie `LlmSettings` tenant-scoped**: #377 verlangt ausdrücklich Workspace-Granularität.

Die eine Lehre, die aus `LlmSettings` übernommen wird, und die *nicht* übernommen wird:
`LlmSettings` macht Zeilenexistenz bedeutungstragend (Issue #276 — ein Row überschreibt
bedingungslos die Env-Konfiguration). Hier gilt bewusst das Gegenteil: **fehlende Zeile =
Feature aus, Defaults gelten.** Damit ist ein Lesepfad, der versehentlich anlegt, harmlos —
aber die Regel „Lesepfade legen nichts an" wird trotzdem eingehalten.

**Migrations-Warnung** (aus der Repo-Historie, `0048_app_role.py` und die
RLS-Policy-Migrationen): jede neue tenant-scoped Tabelle braucht
`ALTER TABLE … ENABLE ROW LEVEL SECURITY` + `CREATE POLICY … USING (current_setting('app.current_tenant', true))`
im selben Migrations-Schritt, nach dem Muster von `0026_add_llm_settings.py`. Ohne Policy ist
die Tabelle mandantenübergreifend lesbar. Und: die DDL läuft nur unter der DB-Owner-Rolle,
nicht unter der Least-Privilege-Runtime-Rolle.

**UI-Ort:** `frontend/src/components/WorkspaceSettings/` existiert bereits — der Schalter
gehört dorthin, nicht in `SystemSettings` (das ist global/tenant-weit).

---

## 6. Die `context.*`-MCP-Werkzeuggruppe

### 6.1 Vorgeschlagene Signaturen

Neue `ContextToolGroup` in `mcp_server/tools/context.py`, Präfix `context`, **alle drei
Werkzeuge lesend** — also ausdrücklich *nicht* in `_WRITE_TOOL_PREFIXES`
(`tool_registry.py`), damit keine Editor-Rolle erzwungen wird.

```
context.query
  artifact_id     : uuid   (Pflicht)
  workspace_id    : uuid   (optional; sonst aus dem Artefakt aufgelöst)
  depth           : int 1..3, default 2
  include         : [ "upstream" | "downstream" | "semantic" | "risks" | "issues" ]
                    default alle
  max_nodes       : int, default 50, hart gedeckelt
  ->
  { artifact: {artifact_id, uid, type, title, status, workspace_id},
    upstream:  [ {artifact_id, uid, title, type, link_type, depth} ],
    downstream:[ ... ],
    semantic:  [ {artifact_id, uid, title, edge_kind, origin, confidence, evidence} ],
    open_risks:  [...],
    open_issues: [...],
    stale: bool, generated_at: iso8601, truncated: bool }
```

```
context.graph
  workspace_id     : uuid   (Pflicht)
  root_artifact_id : uuid   (optional; ohne = ganzer Workspace)
  depth            : int 1..4, default 2
  link_types       : [str]  (optional, Whitelist harter Kanten)
  edge_kinds       : [str]  (optional, Whitelist weicher Kanten)
  max_nodes        : int, default 300, hart gedeckelt
  ->
  { nodes: [ {id, artifact_id, uid, type, title, status} ],
    edges: [ {source, target, kind, layer: "trace"|"semantic", origin, confidence} ],
    truncated: bool, stale: bool, generated_at: iso8601 }
```

```
context.related
  artifact_id    : uuid  (Pflicht)
  edge_kinds     : [str] (optional)
  min_confidence : float, default 0.5
  scope          : "workspace" | "tenant", default "workspace"
  limit          : int, default 10, max 50
  ->
  { related: [ {artifact_id, uid, title, type, workspace_id, workspace_name,
                edge_kind, confidence, why} ],
    scope: str, truncated: bool }
```

### 6.2 Komposition statt Duplikat

- `context.query` liest die **harte** Schicht über dieselbe Layer-1-API wie
  `traceability.query` (`traceability.service.impact_analysis` / `query_engine`). Es gibt keine
  zweite Traversierungsimplementierung. Wenn sich die Link-Semantik ändert, ändert sie sich an
  einer Stelle.
- `context.graph` benutzt für den Workspace-weiten Fall `traceability.services.collect_trace_graph`,
  das genau dafür schon existiert (und von Baselines genutzt wird).
- `context.related` ist die **einzige echte Neuerung** — semantische Kanten plus optional
  Workspace-übergreifende Sicht. Wenn nur ein Werkzeug in v1 gebaut wird, ist es dieses; alles
  andere ist Verpackung.
- `artifact.search` (Volltext, §1.2) bleibt unangetastet. `context.*` ruft es *nicht* auf —
  Suche und Kontext sind zwei verschiedene Fragen („wo steht der Begriff" vs. „was hängt daran").

### 6.3 Zwei konkrete Fallen aus der Repo-Historie

1. **Kein Top-Level-`content`-Schlüssel** in einer Tool-Payload — kollidiert mit der
   MCP-Envelope-Struktur. Und: Treffer und Nicht-Treffer müssen dieselbe Form haben
   (leere Liste statt fehlendes Feld).
2. **Namenskollision mit `workspace.get_context`.** Das existierende Werkzeug ist die
   *Workspace*-Orientierung, die neue Gruppe die *Artefakt*-Orientierung. Ein Agent, der beide
   im Manifest sieht, muss die Grenze aus der Beschreibung lesen können. Alternative, die ernsthaft
   erwogen werden sollte: **kein neuer `context.`-Präfix**, sondern `artifact.get_context` /
   `artifact.get_related` — dann liegt die Artefakt-Sicht dort, wo `artifact.search` und
   `artifact.get_tree` schon liegen, und der Präfix bleibt konsistent mit dem Objekt, um das es geht.
   Das ist eine offene Frage (§11).

### 6.4 RBAC und Mandantengrenze

`scope="tenant"` in `context.related` ist der einzige Ort, an dem dieses Feature eine
Sicherheitsgrenze berührt. `TraceLink` hat **keine** Workspace-Spalte — Links sind tenant-global,
der Workspace wird über den Join auf `Artifact` aufgelöst. Technisch ist die
workspace-übergreifende Abfrage damit *billiger* als erwartet. Fachlich ist sie ungeklärt:
RBAC-Rollen werden in diesem System pro Workspace aufgelöst (Issue #103), ein Nutzer kann also
in Workspace A Editor und in Workspace B ohne jede Rolle sein. Eine tenant-weite Antwort darf
dann weder Titel noch UIDs aus B enthalten. Das ist eine Filterregel, die **im Service** liegen
muss, nicht im Serializer.

---

## 7. Graphify und Honcho — ehrliche Einschätzung

### 7.1 Klarstellung, damit hier keine Verwechslung entsteht

In diesem Repository tauchen `graphify` und `Honcho` **ausschließlich als Entwickler-Werkzeug**
auf, nie als Anwendungsbestandteil:

- `graphify`: ein Verzeichnis `graphify-out/` mit einem Code-Wissensgraphen über *den
  Quellcode*, plus eine Skill-Referenz in der globalen `~/.claude/CLAUDE.md` des Entwicklers.
  Es hilft Agenten, sich in der Codebasis zurechtzufinden.
- `Honcho`: `.claude/rules/mcp-honcho.md` — eine von `agent-meta` generierte
  MCP-*Consumer*-Konfiguration für die Claude-Agenten, die an diesem Repo arbeiten.

Weder das eine noch das andere wird von `backend/` oder `frontend/` importiert. Weder das eine
noch das andere steht in `backend/requirements.txt` oder `frontend/package.json`. Die Aussage
„die Codebasis kann das schon" wäre bezogen auf das Produkt **falsch**. Beides sind Werkzeuge,
mit denen an ReqogniLoom gearbeitet wird, keine Fähigkeiten, die ReqogniLoom hat.

### 7.2 Empfehlung: explizit vertagen

Vier Gründe:

1. **Es ist primär eine Datenschutz-Entscheidung, keine technische.** Artefakttexte an einen
   externen Kontext-Dienst zu schicken ist Mandantendaten-Egress. Das ist eine Produkt- und
   ggf. Vertragsentscheidung, die vor jeder Zeile Code getroffen sein muss — insbesondere in
   einem Tool, das mit Row-Level-Mandantentrennung und Audit-Log wirbt.
2. **Es gibt noch nichts zu spiegeln.** Ein Connector exportiert einen Graphen, den es v1 erst
   entstehen zu lassen gilt. Die Reihenfolge ist zwingend.
3. **Kein stabiler, versionierter Server-Vertrag.** Für beide Ziele liegt in diesem Repo kein
   dokumentierter API-Vertrag vor, gegen den man testen könnte. Ein Adapter gegen ein
   bewegliches Ziel ist eine Wartungsfalle — dieselbe Begründung, mit der der
   OpenCode-Plugin-Hook im Plan vom 2026-08-05 verworfen wurde.
4. **Keine belegte Nachfrage.** Kein Nutzer hat danach gefragt; die Option steht im Issue als
   Möglichkeit, nicht als Bedarf.

**Konkret:** Die Provider-Abstraktion aus Akzeptanzkriterium 6 wird in v1 als schmales
Protokoll erfüllt — `ContextGraphProvider` mit `upsert_node` / `upsert_edge` / `query_context` /
`related` — und **genau einer** Implementierung (`EmbeddedProvider`). Ein
`provider`-Feld in `WorkspaceContextSettings` mit dem einzigen zulässigen Wert `"embedded"`
hält die Tür auf, ohne dass eine Provider-Registry, eine Credential-Verwaltung oder ein
Fallback-Pfad gebaut wird. Das kostet fast nichts und ist ehrlicher als eine Registry mit
einem Eintrag.

---

## 8. Aufwandsschätzung

Personentage, grob, inkl. Tests. Spalte „Art" unterscheidet **[N]** = neues Subsystem (Modelle,
Migrationen, eigene Fehlerfälle, eigene Tests) von **[K]** = Komposition vorhandener
Infrastruktur (bestehendes Muster erweitern).

| # | Fähigkeit | Art | Tage |
|---|---|---|---|
| 0a | Subscriber-Registrierungspfad erstmals produktiv beweisen (`ready()` + Integrationstest über den echten Outbox-Poller) | [K]* | 1–2 |
| 0b | `TraceLink*`-Events + undeklarierte `EventType`-Werte + `payload["artifact_id"]` in allen Produzenten | [K] | 2–3 |
| 1 | App `context_graph/`: `ContextEdge` + `WorkspaceContextSettings` + RLS-Migrationen | [N] klein | 2–3 |
| 2 | `ContextGraphProjector` (idempotent, Watermark, Toggle, Fehlerpfad) | [N] | 3–5 |
| 3a | Generator „glossary/shares-term" (deterministisch, kein LLM) | [N] | 2 |
| 3b | Generator „embedding/related" (pgvector) **inkl. fehlender Embedding-Spalten + Backfill** | [N] | 5–8 |
| 3c | Generator „cochange/influences" (Audit-Log-Mining) | [N] | 3–4 |
| 3d | „contradicts" (LLM-basiert, nur als Vorschlag) | [N] offen | 5–8 |
| 4 | Layer-2-Fassade `ContextService` + Lesepfad + Redis-Cache | [K] | 3–4 |
| 5 | `context.*`-Tool-Gruppe (3 Tools, Schemas, RBAC, Registry, Tests) | [K] | 2–3 |
| 6 | REST-Endpunkte für dieselben Abfragen | [K] | 1–2 |
| 7a | Beat-Fan-out-Task + Redis-Lock + Intervall-Konfiguration | [K] | 2–3 |
| 7b | Volle Cron-Expression (neue Dependency oder Option B aus §4.1) | [K] | 2–3 |
| 8 | UI: Graph-Ansicht + Kontext-Panel (React Flow + dagre schon vorhanden) | [K] | 5–8 |
| 9 | Workspace-übergreifende Sicht inkl. RBAC-Sichtbarkeitsregeln | [N] policy-lastig | 4–6 |
| 10 | Externe Connectoren (Graphify / Honcho) | [N] extern | 8–15+ |
| 11 | Settings-UI in `WorkspaceSettings/` | [K] | 1–2 |
| 12 | `context.rebuild` (Admin-Pfad, Voraussetzung für §3.4) | [K] | 1–2 |

\* 0a ist formal Komposition, aber der Pfad ist **unbewiesen** — deshalb nicht als „nur andocken"
einplanen.

**Summe v1 (0a, 0b, 1, 2, 3a, 4, 5, 11, 12): 17–26 Tage.**
**Summe für #377 im vollen Wortlaut: 45–70+ Tage.** Das Issue ist als eine Einheit nicht
schneidbar.

---

## 9. Empfohlene Phasierung

### v1 — dieses Issue, reduziert

Embedded-only, ereignisgesteuert, **eine** Workspace-Sicht, **ein** Kantengenerator.

- Vorarbeit 0a + 0b (ohne die ist AK 1 unerfüllbar)
- `context_graph`-App: `ContextEdge`, `WorkspaceContextSettings` inkl. RLS
- `ContextGraphProjector` am bestehenden `application/event_bus.py`
- Genau ein Generator: **glossary / `shares-term`** — deterministisch, kein LLM, keine
  Embedding-Kosten, sofort erklärbar („beide Artefakte verwenden Begriff T"), und er nutzt den
  bereits existierenden `uses-term`-Linktyp und `GlossaryTerm.synonyms`
- Layer-2-Fassade + `context.query` und `context.related` (nur `scope="workspace"`)
- Per-Workspace An/Aus in `WorkspaceSettings/` + `context.rebuild`
- `ContextGraphProvider`-Protokoll mit genau einer Implementierung

**Damit erfüllte Akzeptanzkriterien:** 1 (nach 0b), 2, 4, 6 (im Sinne von „embedded default",
ohne zweiten Provider).
**Bewusst offen:** 3 (Cron), 5 (Cross-Workspace), 7 (UI).

Begründung für diesen Schnitt: er beweist die gesamte Kette — Mutation → Outbox → Projektor →
abgeleitete Kante → MCP-Antwort — an einem Generator, dessen Ergebnisse ein Mensch sofort als
richtig oder falsch erkennen kann. Alles Weitere ist danach additiv und risikoarm.

### Folge-Issues

| ID | Inhalt | Voraussetzung |
|---|---|---|
| **A** | Embedding-basierte Kanten: fehlende `embedding`-Spalten (`ArchitectureElement`, `TestCase`, `StakeholderNeed`, …) + Backfill-Command + `derived-embedding`-Generator | v1; echter Embedding-Provider konfiguriert |
| **B** | Cron/Beat-Zeitplan pro Workspace (Intervall → Cron-Expression) | v1 |
| **C** | UI: Graph-Ansicht + Kontext-Panel je Artefakt (React Flow, `context.graph`) | v1 + `context.graph` |
| **D** | Workspace-übergreifende / tenant-weite Sicht inkl. RBAC-Sichtbarkeitsmodell | v1 + Entscheidung aus §11.3 |
| **E** | Externe Provider (Graphify / Honcho) | A–D + Datenschutz-Entscheidung §11.6 |

Die LLM-basierte „contradicts"-Kante (3d) bekommt **kein** eigenes Issue, bis §11.2 entschieden
ist. Sie ist die einzige Fähigkeit im Issue, die eine falsche Maschinenaussage über
Anforderungsqualität in ein formales SE-Artefakt tragen könnte.

---

## 10. Was dieses Feature ausdrücklich nicht ist

Zur Erwartungssteuerung, weil die Issue-Motivation an einer Stelle mehr verspricht, als sie
liefert:

- **Es ersetzt `traceability.*` nicht.** Harte Kanten bleiben die einzige Grundlage für
  Coverage, VCRM, Baselines und den SE-Auditor.
- **Es ist kein GraphRAG.** Ohne konfigurierten Embedding-Provider (§1.2) ist die Semantikschicht
  auf deterministische Generatoren (Glossar, Co-Change) beschränkt. Mit `LLM_PROVIDER=mock`
  liefert eine embedding-basierte Kante Rauschen.
- **Es ist kein zweites Audit-Log.** `audit/` beantwortet „wer hat wann was geändert",
  der Kontextgraph „was hängt womit zusammen".
- **Es macht `workspace.get_context` nicht überflüssig.** Das bleibt die Workspace-Orientierung.

---

## 11. Risiken und offene Fragen (Produkt-/Menschentscheidung nötig)

**11.1 Sichtbarkeit abgeleiteter Kanten in der Traceability-UI.**
Erscheinen `ContextEdge`-Kanten in `TraceabilityView`/`ImpactView` — und wenn ja, wie werden
sie strukturell und visuell von handgepflegten Trace-Links unterschieden? Falsch beantwortet
entsteht der Eindruck, das System habe Traceability erzeugt, die niemand verantwortet.
*Empfehlung:* eigene Ebene, eigene Farbe/Strichart, per Default ausgeblendet, nie in
Coverage-Zahlen.

**RESOLVED 2026-08-07 — gleichwertig sichtbar, aber unverwechselbar markiert.** `ContextEdge`-Kanten
erscheinen an derselben Stelle wie handgepflegte Trace-Links (nicht per Default ausgeblendet),
mit drei Auflagen: (1) ein eigener, ein-/ausblendbarer Marker/Badge (z.B. "abgeleitet") an jeder
`ContextEdge` — die Sichtbarkeits-Umschaltung selbst bleibt wie ursprünglich empfohlen, nur der
*Default* ändert sich von "aus" auf "an"; (2) die Kantenfarbe ist eine Kontrastfarbe, die über
das bestehende Theming-Konzept (`styles/tokens.css`) konfigurierbar ist, nicht hart codiert;
(3) **Coverage, VCRM und alle Konformitätskennzahlen werden weiterhin ausschließlich aus
`pl_tracelink` berechnet** — `ContextEdge` fließt in keine dieser Berechnungen ein, unabhängig
von der UI-Sichtbarkeit. Damit bleibt die im Absatz oben beschriebene Integritätsgefahr
architektonisch ausgeschlossen; nur die UI-Standardeinstellung wurde geändert.

**11.2 Wer darf „widerspricht" behaupten?**
Eine deterministische Erkennung von Widersprüchen zwischen Anforderungen gibt es nicht; sie
wäre LLM-basiert. In einem Extended-Rigor-Kontext ist eine maschinelle Behauptung „REQ-A
widerspricht REQ-B" eine Qualitätsaussage mit Konsequenzen.
*Empfehlung:* niemals als Kante materialisieren, sondern nur als **Vorschlag** mit
Adopt/Modify-Übernahme durch einen Menschen — analog zum bestehenden Remediation-Muster des
SE-Auditors. Braucht eine Produktentscheidung, keine Entwicklerentscheidung.

**RESOLVED 2026-08-07 — wie empfohlen: nie materialisieren.** `contradicts` wird nie als
`ContextEdge` gespeichert, nur als Vorschlag mit menschlicher Adopt/Modify-Übernahme. §9's
Aussage, dass 3d ("contradicts") kein eigenes Folge-Issue bekommt, bis diese Frage entschieden
ist, ist damit hinfällig — 3d kann jetzt als Folge-Issue mit dieser Einschränkung angelegt
werden, bleibt aber ohnehin außerhalb des v1-Schnitts (§9).

**11.3 Sichtbarkeitsregel für die tenant-weite Sicht.**
Rollen sind pro Workspace aufgelöst. Was sieht ein Nutzer bei `scope="tenant"` von einem
Workspace, in dem er keine Rolle hat — nichts, nur die Existenz einer Beziehung ohne Titel,
oder alles? Ohne diese Entscheidung ist Folge-Issue D nicht implementierbar.

*(Weiterhin offen — betrifft nur Folge-Issue D, nicht v1. v1 liefert ausschließlich
`scope="workspace"`.)*

**11.4 Aktualitätsvertrag.**
Was sieht ein Konsument, während eine Aktualisierung aussteht? *Empfehlung:* jede Antwort
trägt `stale: bool` + `generated_at`, es wird nie blockiert und nie synchron nachgerechnet.
Muss aber im Werkzeug-Schema stehen, sonst ignorieren Agenten es.

**RESOLVED 2026-08-07 — wie empfohlen.** `context.query`/`context.graph`/`context.related`
antworten immer sofort mit `stale: bool` + `generated_at` im Schema, nie synchrones Nachrechnen,
nie Blockieren.

**11.5 Betriebsvoraussetzung Embedding-Provider.**
Die Semantikschicht ist mit dem Projekt-Default `mock` inhaltlich leer. Soll das Feature bei
`provider=mock` die embedding-basierten Generatoren aktiv verweigern (ehrlich, aber wirkt
kaputt) oder Rauschen liefern (wirkt funktional, ist aber irreführend)?
*Empfehlung:* verweigern, mit klarer Meldung in der Settings-UI.

**RESOLVED 2026-08-07 — wie empfohlen: verweigern.** Betrifft in v1 ohnehin nur den
`glossary`/`shares-term`-Generator (deterministisch, kein Embedding) nicht — relevant erst für
Folge-Issue A (embedding-basierte Kanten), das explizit einen echten Embedding-Provider als
Voraussetzung nennt (§9).

**11.6 Datenschutz-Freigabe für externe Provider.**
Vor Folge-Issue E muss jemand entscheiden, ob Mandanten-Artefakttexte an einen externen
Kontextdienst gehen dürfen. Das ist keine Architekturfrage.

**11.7 Outbox-Wachstum.**
`DomainEventOutbox` wird nie beschnitten — publizierte Zeilen bleiben liegen. Das ist heute
folgenlos, weil niemand konsumiert; mit dem ersten produktiven Subscriber wird die Tabelle
zum Betriebsthema (Backlog-Monitoring loggt bereits `backlog` und `dlq_count`). Gehört als
eigenes Wartungs-Issue erfasst, nicht in #377 hineingezogen.

**11.8 Präfix-Entscheidung `context.*` vs. `artifact.*`.**
Siehe §6.3. `artifact.get_context` / `artifact.get_related` wäre konsistenter mit
`artifact.search` / `artifact.get_tree` und vermeidet die Verwechslung mit
`workspace.get_context`. `context.*` ist eigenständiger und im Issue so benannt. Muss vor dem
Plan entschieden sein — ein Präfix umzubenennen kostet nach Auslieferung an Agenten-Konsumenten
deutlich mehr.

**RESOLVED 2026-08-07 — `context.*`, wie im Issue benannt.** Die in §6.3 genannte
Verwechslungsgefahr mit `workspace.get_context` bleibt ein Risiko — die Tool-Beschreibung von
`context.query`/`context.graph`/`context.related` muss die Objekt-Orientierung (Artefakt statt
Workspace) explizit im ersten Satz nennen, damit ein Agent die Grenze aus dem Manifest lesen
kann, ohne beide Werkzeuge auszuprobieren.

**11.9 Die unbequeme Frage.**
`workspace.get_context(depth="full")` liefert heute schon Preset, Terminologie, Entity-Counts,
Entity-Listen und `recent_changes`; `impact_analysis`, `find_path` und `detect_cycles` sind
REST-exponiert. Ein ehrlicher Blick sagt: der *neue* Wert von #377 ist die **semantische
Kantenschicht** plus die **automatische Pflege**, nicht „ein Graph". Wenn die semantische
Schicht ohne echten Embedding-Provider (§11.5) leer bleibt und die „contradicts"-Kante
(§11.2) nicht materialisiert werden darf, schrumpft der Zugewinn auf: Glossar-Kanten,
Co-Change-Kanten und eine gebündelte Leseschnittstelle. Das ist ein guter, ehrlicher v1 —
aber es ist deutlich weniger, als der Issue-Titel verspricht, und das sollte vor dem Start
ausgesprochen sein.

---

## 12. Referenzen im Quellcode

| Thema | Datei |
|---|---|
| Outbox-Bus, Poller, DLQ | `backend/application/event_bus.py` |
| Event-Emission-Seam | `backend/application/base.py` (`_emit_event`, `_make_event`) |
| Event-Katalog | `backend/application/models.py` (`DomainEventOutbox.EventType`) |
| Separater Audit-Bus (nicht verwechseln) | `backend/audit/events.py`, `backend/audit/apps.py` |
| Einziger geschriebener Subscriber (nie registriert) | `backend/application/webhook_dispatcher.py` |
| Trace-Link-Schreibpfad (ohne Events) | `backend/application/trace_link_service.py` |
| Graph-Traversierung (rekursive CTEs) | `backend/traceability/service.py`, `backend/traceability/query_engine.py` |
| Kantentypen + SE-Endpunktmatrix | `backend/traceability/types.py` |
| Volltextsuche (kein pgvector) | `backend/application/search_service.py` |
| Embeddings | `backend/llm_adapter/embedding_service.py`, `backend/persistence/migrations/0024_…`, `0025_…` |
| Knoten-/Kantentabellen | `backend/persistence/models.py` (`Artifact`, `TraceLink`, `Workspace`, `GlossaryTerm`) |
| Settings-Präzedenz + Row-Existenz-Falle | `backend/persistence/models.py` (`LlmSettings`), `backend/persistence/migrations/0026_add_llm_settings.py` |
| Beat-Konfiguration | `backend/reqogniloom/settings.py:558`, `backend/reqogniloom/celery.py`, `docker-compose.yml:317` |
| Bestehendes Agenten-Kontextwerkzeug | `backend/mcp_server/tools/cross_cutting.py:845` (`workspace.get_context`) |
| React Flow im Einsatz | `frontend/src/components/WorkflowEditor/WorkflowCanvas.tsx` |
| Ziel-UI-Nachbarn | `frontend/src/components/TraceabilityView/`, `ImpactView/`, `WorkspaceSettings/` |
