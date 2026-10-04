---
type: EVIDENCE
scope: top10-verification
status: final
date: 2026-09-30
author_agent: code-reviewer
baseline_ref: main @ abd61aed
branch: chore/system-audit-2026-09
---

# Unabhaengige Gegenpruefung der 10 kritischsten Findings (2026-09-30)

Rolle: **Faktenpruefer**, nicht Verteidiger des Audits. Jede Behauptung wurde gegen
Quelltext, gegen ein committetes Evidenzartefakt oder gegen eine eigene Messung
geprueft - nicht gegen die Zusammenfassung des Vor-Audits.

---

## 0. Vorbemerkung: die Auftragsannahme "Stack laeuft" war falsch

| Pruefung | Kommando | Ergebnis |
|---|---|---|
| Docker-Engine | `docker ps` | `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine` |
| Docker-Service | `Get-Service com.docker.service` | `Stopped`; kein `docker*`/`com.docker*`-Prozess |
| HTTP-Backend | `Invoke-WebRequest http://localhost:8001/api/v1/health/` | `Die Verbindung ... kann nicht hergestellt werden` |
| Ports 8000/8001/5432/6379/3000/5173 | `Test-NetConnection` | **alle** `TcpTestSucceeded=False` |

**Folge fuer die Belastbarkeit:** der Live-Teil des Auftrags (Redis-Bindings,
`celery inspect`, MCP-`tools/list`, `SELECT`, Round-Trip-HTTP) war **nicht** durchfuehrbar.
Ich habe deshalb konsequent statisch plus hermetisch gemessen (lokale Celery-App
mit der exakten Produktionskonfiguration, `kombu`-Transporte, Nachrechnen der
Evidenzartefakte). Nach Methodikregel 5 ist das kein Fehlbefund - aber es ist die
Grenze dieser Pruefung, und sie wird unten bei jedem betroffenen Finding benannt.

Zusaetzlich: `testing/docker-compose.test.yml` ist kein gueltiges Test-Overlay
(`service "backend-test" depends on undefined service "redis"`). Das in
`AGENTS.md` dokumentierte `pytest (Backend)`-Kommando trifft es ebenfalls nicht.

---

## 1. Urteile je Top-10-Finding

| # | ID | Behauptung (Kurzform) | Urteil | Eigener Beleg | Korrekturbedarf |
|---|---|---|---|---|---|
| 1 | `AUD-2026-09-220` | Audit committete live gueltigen `reqlo_`-Key; Arbeitsbaum redigiert, Historie offen | **bestätigt, aber Beschreibung ungenau** | Key in `3dcc80d8` (40 Zeichen nach Praefix) vorhanden; in HEAD/Arbeitsbaum nur noch blankes Praefix `reqlo_`; `git merge-base --is-ancestor 3dcc80d8 origin/chore/system-audit-2026-09` -> **exit 1 = nie gepusht** | Reichweiten-Satz korrigieren: nie auf einem Remote, kein Fork/PR konnte es ziehen. Widerruf **nicht** verifizierbar (Stack aus) |
| 2 | `AUD-2026-09-222` | Workspace-Fence greift auf 269/311 mutierenden Routen nicht | **bestätigt** | `workspace_scope.py:114` (URL->Query->JSON-Body), `rest.py:259-277` (else-Zeile 272-277 = tenant-weite UNION), `requirement_service.py:754-757` (nur tenant-skaliert). `wp1d-resolved-routes.json` nachgerechnet: 311 mutierend, 42 mit `workspace` im Pfad, **269 ohne**, 99 View-Klassen | keiner |
| 3 | `AUD-2026-09-030` + `-221` | `CACHES` ohne `SOCKET_TIMEOUT`; Rate-Limit-Check vor AuthN | **bestätigt** | `settings.py:879-884`: nur `BACKEND`+`LOCATION`, kein `OPTIONS`. `views.py:272` `check_mcp_rate_limit(request)`; AuthN erst in `handler.handle_http_request(...)` ab `:307`; Kommentar `:269` sagt es explizit | Zahl "13 MCP-Endpoints" nicht nachgezaehlt |
| 4 | `AUD-2026-09-031` | `/health/` prueft den Cache nicht, meldet bei Ausfall `200 {"status":"ok"}` | **bestätigt** | `health.py` enthaelt **null** Treffer fuer `cache`/`redis`/`CACHES`; Checks sind database/memory_backend/embedding_dimensions/llm_provider_env/csrf/workflow. Route korrekt `/health/` (`urls.py:28`, Root, **nicht** `/api/v1/health/`). Bei Redis-Ausfall + DB ok -> keine `warnings` -> `status` bleibt `"ok"`, HTTP 200 (`:312-315`) | Wortwahl "Totalausfall" praezisieren: **DB-Ausfall liefert korrekt 503**. Der Fall ist Cache-/Worker-Ausfall |
| 5 | `AUD-2026-09-070` | CSV-Roundtrip kaputt: Kommentarzeile wird als Header gelesen, `201 success:true` bei 0 Zeilen | **WIDERLEGT** | `import_service.py:341-344` strippt **jede** mit `#` beginnende Zeile vor `csv.DictReader`. Export-Kommentar und Strip stammen aus **demselben** Commit `3081435a` (2026-06-24). Eigene Messung des Original-`_parse_csv` gegen echten Export-Output: 16 Headerfelder, 1 Datenzeile, `title='CLEAN-1'` | **Finding zurueckziehen oder neu begruenden.** Ortsangabe `export_service.py:17-18` ist ein Docstring, nicht Code; Codestelle ist `:382` |
| 6 | `AUD-2026-09-071` | ReqIF-Import meldet `success: true` trotz `pl_artifact_pkey`-Fehlschlaegen | **bestätigt, aber Beschreibung ungenau** | `reqif_import_service.py:483` `success=True` **hart kodiert**; der `success: True`-Vertrag ist in `:278-279` sogar dokumentiert. `:688-703` faengt `IntegrityError` und vergibt neue UUID | "Stiller Fehlschlag" unzutreffend: die Antwort **listet** 915 Objektfehler. Ursache unvollstaendig beschrieben - s. §2 |
| 7 | `AUD-2026-09-120` | 4 Celery-Queues identisch gebunden -> 1 Nachricht, 4 Ausfuehrungen | **bestätigt** (siehe M-1) | Praemisse und Konsequenz unabhaengig gemessen; Redis-Transport teilt den Lookup-Pfad | Live-Manifestation einer echten 4x-Ausfuehrung **nicht** beobachtet; Evidenzzeile "genau ein `_kombu.binding.default`" ist ein Fehlread |
| 8 | `AUD-2026-09-123` | `restore.sh` kopiert Backup nie in den Container; `psql -f`/`pg_restore` lesen Pfade | **bestätigt** | `restore.sh:183,186` nehmen `/tmp/backup.dump` / `/tmp/backup.sql`; `:198-213` piped nur auf **stdin**. `Select-String '\bcp\b'` + `docker.*cp` ueber das ganze Skript: **null Treffer**, obwohl der Kommentar `:194` "Copy backup file to temp" verspricht | keiner |
| 9 | `AUD-2026-09-052` | Anthropic-Default `claude-3-opus-20240229` abgeschaltet; `LLM_MODEL` in allen Compose-Dateien leer | **bestätigt** | `providers.py:1080` exakt. Aufloesung `:120-121` (`LLM_MODEL_NAME or LLM_MODEL or ""`), `:340-341` (Model ueberschreibt `MODEL_NAME`), also leer -> `MODEL_NAME`. Compose: `docker-compose.yml:599,828,919` und `docker-compose.minimal.yml:141` = `${LLM_MODEL:-}`. Anthropic-Seite: eigene Recherche, Retirement **2026-01-05** | keiner |
| 10 | `AUD-2026-09-121` + `-270` | Beat dispatcht 0x; Healthcheck nur Prozessexistenz; `archive.archive_lifecycle_manager` nicht im Task-Set | **bestätigt, aber Beschreibung ungenau** | Healthcheck `docker-compose.yml:933` = `pgrep -f 'celery.*beat'` - **nur** Prozess, exakt bestaetigt. `-270`: `archive.py:448` definiert den Task, `backend/audit/tasks.py` existiert **nicht** (6 `tasks.py` im Backend, `audit` fehlt), `apps.py:36` importiert nur `audit.writer`, und **kein** Nicht-Test-Code importiert `audit.archive` | Der Beat-Teil ("0x Sending due task") ist **nicht verifizierbar** (Log nicht im Repo, Stack aus). Zudem widerspricht `AUDIT_TRACEABILITY.md:152` dem Finding - zu Unrecht, s. §4 |

**Bilanz: 6 bestaetigt · 3 bestaetigt-mit-ungenauer-Beschreibung · 1 widerlegt · 0 ganzlich unverifizierbar.**

---

## 2. M-1 - Der wichtigste Punkt: Celery-Fanout (Finding `AUD-2026-09-120`)

### 2.1 Was gemessen wurde

**(a) Praemisse - effektive Konfiguration.** Ich habe eine Celery-App mit der
**woertlichen** Konfiguration aus `backend/reqogniloom/celery.py:31-42` gebaut
(keine eigene Erfindung, keine geratenen Defaults) und `app.amqp.queues`
ausgegeben - das ist die Struktur, die der Worker beim Start deklariert:

```
conf.task_default_exchange      = 'default'
conf.task_default_exchange_type = 'direct'
conf.task_default_routing_key   = 'default'

queue=default  exchange='default' type=direct routing_key='default' durable=True
queue=llm      exchange='default' type=direct routing_key='default' durable=True
queue=events   exchange='default' type=direct routing_key='default' durable=True
queue=memory   exchange='default' type=direct routing_key='default' durable=True
UNIQUE_ROUTING_KEYS=["default"]
UNIQUE_BINDINGS=[["default","default"]]
```

Die Praemisse des Audits ist damit **korrekt gemessen** (auch von mir, unabhaengig).

Zur Warnung des Auftrags: `kombu.Queue('llm')` allein ergibt
`routing_key=''` und `exchange=Exchange('','direct')`. Der Routing-Key wird also
**nicht** vom Queue-Namen abgeleitet - er kommt aus `task_default_queue='default'`
(`celery.py:37`), das Celery auf Exchange **und** Routing-Key spiegelt. Ein nackter
`Celery('x')` liefert dagegen `exchange='celery', rk='celery'`. Die Auftragswarnung
war also berechtigt - nur trifft sie hier nicht zu, weil der Effekt identisch ist.

**(b) Bindungs-Tabelle.** Alle vier Queues in `memory://` deklariert:

```
binding table exchange='default':
  [["default", null, "default"], ["default", null, "llm"],
   ["default", null, "events"], ["default", null, "memory"]]
```

**(c) Zustellung.** Exakt **eine** Nachricht publiziert, aus allen vier Queues
konsumiert (`-Q default,llm,events,memory`, `docker-compose.yml:887`):

```
queue=default  deliveries=1
queue=llm      deliveries=1
queue=events   deliveries=1
queue=memory   deliveries=1
TOTAL_EXECUTIONS_FOR_ONE_PUBLISHED_TASK=4
```

**(d) Ist das ein `memory://`-Artefakt?** Nein. Ich habe den Quelltext des
**Redis**-Transports gelesen (installed kombu 5.6.2, `celery>=5.6.3,<6.0` in
`backend/requirements.txt:54`):

* `redis.Channel._lookup` -> bei **benanntem** Exchange
  `self.typeof(exchange).lookup(self.get_table(exchange), exchange, routing_key, default)`
* `DirectExchange.lookup` -> `{queue for rkey, _, queue in table if rkey == routing_key}`
* `redis.Channel.get_table(exchange)` liest `SMEMBERS _kombu.binding.<exchange>`
* Sonderfall: `if not exchange: return [routing_key]` - greift **nur** beim
  anonymen Exchange `''`. Hier ist der Exchange `'default'` (truthy), also der
  Bindungs-Tabellen-Pfad.

Identischer Lookup-Code fuer `memory` und `redis` - beide erben von
`kombu.transport.virtual.base.Channel`. **Der Fanout ist kein Transport-Artefakt.**

### 2.2 Ist die Behauptung "logisch korrekt"?

Die zu pruefende Gegenhypothese war: "ein Consumer liest viele Queues, die Nachricht
wird nur **einmal** konsumiert". Das ist **falsch**. Bei einem direct-Exchange ist
eine Nachricht an jede Queue **kopiert**, deren Routing-Key dem Sende-Key entspricht.
Vier Queues mit identischem `(exchange, routing_key)` sind vier Empfangsqueues,
nicht vier Sichtweisen auf eine. Ein Worker, der alle vier konsumiert, bekommt
vier unabhaengige Messages und fuehrt viermal aus. Das ist genau der klassische
Celery-Falle-Fall; die regulaere Mehr-Queue-Konfiguration gibt jeder Queue einen
**eigenen** Exchange oder Routing-Key.

### 2.3 Urteil

**`AUD-2026-09-120` haelt. Die Kritik am Vor-Audit ist selbst nicht berechtigt.**

Der Fehler ist kein Producer-Fehler im engeren Sinn ("er sendet viermal") - der
Producer sendet **einmal**. Der Fehler ist die **Deklaration**: `celery.py:31-36`
verzichtet auf `Exchange`/`routing_key`, wodurch `task_routes` und die ganze in
`celery.py:16-30` dokumentierte Skalierungsbegruendung wirkungslos werden.
Praezise, belegbare Formulierung:

> Alle vier in `task_queues` deklarierten Queues loesen auf **identisches**
> `exchange='default' (direct), routing_key='default'` auf. Da der Worker alle vier
> konsumiert (`-Q default,llm,events,memory`), erhaelt er jede publizierte Task
> viermal als vier unabhaengige Zustellungen und fuehrt sie 4x aus.
> `llm`, `events` und `memory` sind damit faktisch keine eigenstaendigen Queues,
> sondern Aliase von `default`.

### 2.4 Zwei Dinge, die das Audit zu stark formuliert

1. **Keine Live-Manifestation beobachtet.** Der Worker-Log des Vor-Audits enthaelt
   laut `wp1c-celery-config-and-tasks.md:115-117` *ausschliesslich* `pidbox ping`-Zeilen
   und keine einzige `received`/`succeeded`-Zeile fuer eine echte Aufgabe. Der
   Mechanismus ist bewiesen, eine **beobachtete** 4x-Ausfuehrung im laufenden
   Betrieb nicht. Diese Luecke schliesst sich erst mit `celery inspect active_queues`
   plus Redis-Keyspace auf einem laufenden Stack.
2. **Die Redis-Evidenzzeile ist ein Fehlread.** "`genau ein Binding-Key:
   `_kombu.binding.default`" ist **falsch gelesen**: `redis.Channel._queue_bind`
   schreibt per `SADD` **vier Members in ein SET** pro Exchange. Der Key ist die
   Exchange-Tabelle, nicht eine Binding. Die Aussage stuetzt den Befund also nicht -
   sie stuetzt ihn nicht, aber sie widerlegt ihn auch nicht.

---

## 3. M-2 - Kausalitaet fuer Finding 5/6

### 3.1 Finding 5 (`AUD-2026-09-070`) - widerlegt, statisch **und** reproduzierbar

Ich habe den `_parse_csv`-Koerper **woertlich** (Zeilen 336-356) in einem
hermetischen Lauf gegen den **woertlichen** Output des Exporters
(`export_service.py:379-395`, `quoting=csv.QUOTE_ALL`) laufen lassen:

```
line1: '# terminology_profile: default'
line2: '"title","description","category","status",...'
header_fields (16) = ['title', 'description', ... 'modified_at']
parsed rows         = 1
row[0] title        = 'CLEAN-1'

[Kontrolle OHNE den '#'-Strip]
fieldnames = ['# terminology_profile: default']
```

Ohne Strip haette der Importer **eine** Spalte namens `# terminology_profile: default`
gelesen. Die vom Audit zitierte Live-Warnung
(`Unrecognized column(s) ignored ... , 1, CLEAN-1, SyReq, demo, draft, plain desc.`)
listet jedoch **Datenwerte** als Spalten - das passt zu **keiner** der beiden
Hypothesen. Sie passt zu einem dritten Fall: einer Datei, deren **erste substantive
Zeile selbst Datenwerte** war. Der Audit-Agent hat in Fall F1 vermutlich eine
selbstgebaute Datei verwendet, deren Kopfzeile keine echte Kopfzeile war.

**Der A/B-Beweis des Auditors ist methodisch ungueltig:** "Datei mit Kommentarzeile
-> Fehler, dieselbe Datei ohne Kommentarzeile -> OK" variiert **zwei** Variablen
gleichzeitig. Wegen des Strips sind die beiden Dateien nach dem Stripping
identisch; sie haetten sich nicht unterscheiden duerfen. Der Test kann die
Behauptung also gar nicht stuetzen, selbst wenn die Behauptung richtig waere.

Wichtig fuer die Fairness: `git log -S` zeigt, dass Strip
(`3081435a`, 2026-06-24) und Export-Kommentar aus **demselben** Commit stammen.
Der Pfad war nie inkonsistent. Nahegelegene echte Restbefunde sind davon unberuehrt
(stiller Duplikat-Import ohne `id`/`uid`-Spalte, RFC-4180-Verstoss -> kollabierte
Zeile, 201 bei 0 Zeilen bei kaputter Kopfzeile) - aber das ist **nicht** die
behauptete Ursache.

Live-HTTP-Roundtrip: **nicht durchgefuehrt** (Stack aus). Das aendert nichts an
der Widerlegung, weil sie auf Quelltext plus hermetischer Wiedergabe beruht.

### 3.2 Finding 6 (`AUD-2026-09-071`) - bestaetigt, aber die Ursachenkette stimmt nicht

Bestaetigt:
* `reqif_import_service.py:483` - `success=True` ist **hart kodiert** und wird
  auch dann zurueckgegeben, wenn jedes Objekt gescheitert ist.
* `:429-443` - jedes Objekt wird soft-failed und in `report.errors` gelistet.

Ungenau / falsch:
* "Stiller Fehlschlag" - die Antwort enthaelt eine **vollstaendige Fehlerliste**
  pro Objekt. Was fehlt, ist ein herabgestuetztes `success`/Status, nicht die Diagnose.
* Die dokumentierte Ursache "`:IDENTIFIER` ist die globale `Artifact.id`" ist
  **unvollstaendig**: der Code faengt genau diesen Fall ab (`:688-703`,
  `except IntegrityError` -> neue UUID) und legt den Fall in `warnings` ab.
* **Der Grund, warum der Fallback nicht greift, fehlt in der Beschreibung:**
  `_upsert_spec_object` laeuft innerhalb des per-Objekt-Savepoints
  (`import_service`-analog `:414`, `with transaction.atomic():`). Wird die
  `IntegrityError` **innerhalb** dieses Blocks abgefangen, rollt Django den
  Savepoint **nicht** zurueck - die Postgres-Transaktion bleibt im Zustand
  "aborted". Der Retry in `:697` laeuft dann in `InFailedSqlTransaction` /
  `TransactionManagementError` und stirbt mit.
* Diese Verfeinerung erklaert das vom Audit gesehene Symptom praezise: der Fallback
  **koennte** nicht greifen, also erscheint nicht die Warnung "collided with an
  existing artifact id", sondern der generische Text "An internal error occurred
  while importing this object." - **915x**.

Live-ReqIF-Import: **nicht durchgefuehrt** (Stack aus). Ob alle 915 Objekte
tatsaechlich auf diesem Pfad scheiterten, ist damit offen; der Mechanismus ist
statisch belegt.

---

## 4. M-3 - Finding 1 (`AUD-2026-09-220`) im Detail

| Teilfrage | Ergebnis | Beleg |
|---|---|---|
| (a) Redaktion im Arbeitsbaum vollstaendig? | **ja, fuer die genannte Datei** | `wp1d-auth-pagination-filter-errors-live.json` im Arbeitsbaum: 2 Treffer auf `reqlo_`, **beide mit Laenge 0 nach dem Praefix** (blankes Praefix, kein Schluesselmaterial). Commit-Blob `3dcc80d8`: ebenfalls 1 blankes Praefix **+ 1 vollstaendiger 40-Zeichen-Schluessel** -> Historie offen, wie behauptet |
| Nur der Audit-Branch? | **ja** | `git diff --name-only abd61aed..HEAD \| where nicht docs/` -> **leer**. 115 Dateien, alle unter `docs/` |
| Rest-Vollschluessel in committeten Dateien? | **nein (neu)** | `git grep -l -E "reqlo_[A-Za-z0-9]{20,}" HEAD -- docs` -> **0 Treffer**. Die Treffer in `README.md` sind Curl-Doku-Beispiele (`-H "X-API-Key: ..."`), vorbestehend und nicht vom Audit-Branch geaendert. `.meta-config/secrets.local.yaml` und `.claude/settings.local.json` sind **gitignored** (`.gitignore:34` / `:26`) |
| (b) Key tatsaechlich widerrufen? | **NICHT VERIFIZIERBAR** | Der Test ist ein Live-MCP-`tools/list` mit dem Key -> HTTP 401. Stack aus (Abschnitt 0). **Fehlender Pruefschritt:** Stack starten, `POST /mcp/` mit `Authorization: Bearer reqlo_...` (bzw. `X-API-Key`) und `{"jsonrpc":"2.0","method":"tools/list"}`; 401 = widerrufen, 200 = widerrufen-Nachweis fehlt |
| (c) "nie gepusht"? | **ja - bestaetigt** | `git merge-base --is-ancestor 3dcc80d8 origin/chore/system-audit-2026-09` -> **exit 1**. `git branch -a --contains 3dcc80d8` -> nur der **lokale** Branch. `origin/chore/system-audit-2026-09` = `988294b6` ("docs: add system audit improvement plan"), ein **anderer, aelterer** Stand |

**Korrekturbedarf (deutlich):** `AUDIT_SUMMARY.md:188` schreibt "jeder PR-Autor und
jeder Fork hatte ein gueltiges `write`-Credential". Das ist **widerlegt**: der Commit
lag nie auf einem Remote, es gab weder PR noch Fork. Die richtige
Auswirkungsaussage lautet: *lokales Secret im Arbeitsbaum eines Entwickler-Rechners,
in der Git-Historie eines nicht gepushten Branches; nach Push, Push des Branches
oder-sharing des Repos wird es exponiert.* Der Ratchetzustand "TEILWEISE BEHOBEN"
bleibt richtig, die **Belastungsbeschreibung** ist zu stark.

---

## 5. M-4 - Die drei nachgezaehlten Zahlenpaare

### (a) MCP-Tools: 219 / 35 Praefixe vs. `tools/list` = 80

**Eigene Zaehlung aus einem committeten, vom Audit NICHT erzeugten Artefakt**
(`docs/agent-templates/tool-manifest.json`):

| Kennzahl | Wert |
|---|---|
| `tool_count` | **219** |
| `len(tools)` | **219** |
| distinkte Praefixe | **35** |
| `is_write=true` | **139** |
| `is_write=false` | **80** |
| Read-Scope-Projektion | **80 Tools / 34 Praefixe** |

**Die 80 sind ein Scope-/Rollenfilter, kein Registrierungsfehler.** Das ist
rechnerisch belegbar: 219 - 139 = 80, und die 80 sind **exakt** die
`is_write=false`-Tools. Praefixzahl 34 statt 35, weil das ganze Write-Namespace
`ai_derivation` wegfällt. Die Kette ist damit laeckenlos: 219 Registry - 139
Write-Tools = 80 sichtbar. **Bestaetigt.**

Hinweis: der Audit-Report `AGENTS.md:8/30/58` nennt "31 Praefixe / 215 Tools" - das
ist echter Doku-Drift (CR-21), kein Zaehlfehler des Audits.

### (b) `MISSING_KEY_BASELINE`

**116.** Quelle: `frontend/src/test/i18n-parity.test.ts:186`
(`const MISSING_KEY_BASELINE = 116;`), verwendet in `:216-217`.

Historische, inzwischen **abgesenkte** Ratchet-Werte im Repo: 145
(`docs/archive/audits/SYSTEMAUDIT_2026-08-27_RESTPLAN.md:120`), 123
(`docs/se/reports/KNOWN_TEST_GATE_REDS.md:102`), 117
(`.meta-viz/checkpoints/1002-f6-recon.md:252`). Ein statischer Zaehlversuch der
`t("key")`-Literale ist wegen `t(key, "default")`-Overloads und
Template-Literalen nicht verlaesslich - **die Ratchet-Quelle ist der
belastbare Pfad**, und sie sagt 116. **Bestaetigt.**

### (c) Tests, die in keinem CI-Job laufen

**Meine Zahl: 443** (in **34** Test-Dateien).

*Methode:* Alle Dateien `backend/**/test_*.py` (+ `tests.py`) unter Ausschluss von
`__pycache__`/`migrations` = **658** Dateien. Abdeckung geprueft gegen die
pytest-Matrix in `.github/workflows/ci.yml:44-55` (`working-directory: backend`,
`pytest ${{ matrix.test-set.paths }}`). Der Matrix deckt ausschliesslich
`<app>/tests`-Verzeichnisse ab - 18 davon. In keinem Matrixpfad liegen:

```
link_types/tests      14 Dateien      application/test_run_service.py     1
memory/tests          13 Dateien      application/test_service.py         1
tests/ (backend/tests) 4 Dateien      mcp_server/tools/tests.py           1
```

Test-Funktionen (`def test_*`, ohne Parametrisierung differenziert):
**443** ungedeckt / **7 684** gedeckt. `ci.yml:253` (`pytest docs/agent-templates dist`)
ist ein Root-Job und deckt nichts davon.

Das reproduziert exakt die Audit-Zahl **443** und stuetzt die Adjudikation in
`AUDIT_BACKLOG.md:393` ("443 - die einzige Zahl mit offengelegter, nachpruefbarer
Methode"). **Die Wettbewerber 463 und 511 sind mit dieser Methode nicht
reproduzierbar**; ohne ihre Methoden offengelegt sind sie nicht widerlegbar, aber
auch nicht belastbar. 443 ist korrekt.

---

## 6. Alle Findings, die ich NICHT voll bestaetigen konnte

Das ist kein Makel, das ist die Aussage der Belastbarkeit. Fuer jede Zeile steht
der **konkret fehlende Pruefschritt**.

| Finding | Was fehlt | Konkreter naechster Schritt |
|---|---|---|
| `-220` (Key-Widerruf) | Live-Nachweis der Sperrung | Stack hochfahren; `POST /mcp/` mit dem Key + `tools/list`; 401 erwartet. Ohne DB/Migration nicht moeglich |
| `-220` (Rest-Keys aus `secret-incident` §1.5/§1.6) | „zweiter live Key `ff77bbd0-…`" + „8 weitere aktive admin-Keys" nie geprueft | `SELECT` auf die Key-Tabelle; Key-Hashes gegen die genannten Praefixe; Stack aus |
| `-030` ("13 MCP-Endpoints") | Endpoint-Zahl nicht nachgezaehlt | `urls.py` + `mcp_server/urls.py` zaehlen; ausserdem ein Redis-Ausfall-Experiment (Cache-Timeout messbar machen) |
| `-030` ("haengen unbegrenzt") | Die Zeitgrenze selbst ist eine Config-Inferenz, keine Messung | `SOCKET_TIMEOUT=1` in einer Testinstanz setzen und Request-Dauer messen |
| `-031` | Live-`{"status":"ok"}` bei Redis-Ausfall | Stack hochfahren, Redis stoppen, `/health` aufrufen. Statisch ist der Code-Beweis eindeutig |
| `-070` | Live-HTTP-Roundtrip | Nicht nachholbar **als Bestätigung** - die Behauptung ist widerlegt. Ein Roundtrip *ohne* Kommentarzeile ist der Rest-Nachweis fuer die Restbefunde |
| `-071` (915 Objekte) | ReqIF-Live-Import, DB-Zustand | Export einer fremden Instanz in Wegwerf-Workspace importieren; `report.errors` + `warnings` auswerten |
| `-071` (Savepoint-Vergiftung) | Meine verfeinerte Ursache ist PostgreSQL-Semantik + Code-Lesen, **kein** Test | Reproduktion: `IntegrityError` in `transaction.atomic()` abfangen, dann erneut schreiben; `TransactionManagementError` erwarten |
| `-120` (Produktionsmanifestation) | Ein echter 4x-Lauf | `celery inspect active_queues`; `SCAN` auf `_kombu.binding.*`; `LLEN` der vier Keys; ein Task mit Worker-Log-Zeilen provozieren |
| `-120` (Redis-`_kombu.binding.*`) | Anzahl der Keys/Members | Wie oben; meine Korrektur (1 SET, 4 Members) ist quelltextbasiert, nicht live gezaehlt |
| `-121` (Beat 0x Dispatch) | Das `celery-beat`-Log | Stack hochfahren, `docker logs celery-beat`; ueber Stunden `Sending due task` zaehlen. **Zusaetzlich ungeklaert: WARUM** - der Log zeigt "0x", nicht die Ursache. Meine Quelle bleibt offen |
| `-270` (Worker-Task-Set) | Live-Banner | `celery inspect registered` im Worker; `[tasks]`-Liste. Statisch eindeutig |
| `-222` (269/311) | Live-Exploit-Probe je Route | Zahl ist aus dem Evidenzartefakt reproduziert, aber es ist eine **Pfad-Analyse**, kein 269-facher Negativtest. Ein Test je Mutationsform genuegt |

---

## 7. Korrekturen, die dieses Audit an sich selbst vornehmen sollte

1. **`AUD-2026-09-070` zurueckziehen oder neu begruenden.** Die behauptete
   Ursache ("Kommentarzeile wird als Header gelesen") ist durch
   `import_service.py:341-344` widerlegt; der Roundtrip des eigenen Exporters
   funktioniert auf Quelltextebene. Der A/B-Test, der die Behauptung stuetzen
   sollte, kann sie nicht stuetzen. Critical ist damit **ein Finding zu niedrig**
   und ein geschaetzter Findings-Zaehler **zu hoch**.
2. **`AUD-2026-09-220`: Reichweite korrigieren.** Nie gepusht. "Jeder PR-Autor und
   jeder Fork" streichen; Restrisiko auf lokale Historie +moegliches spaeteres
   Push praezisieren.
3. **`AUD-2026-09-071`: "still" streichen, Ursache korrigieren.** Die Antwort
   enumeriert die Fehler. Die eigentliche Ursache ist die **unwirksame
   Savepoint-Rettung** in `:697`, nicht primaer der globale Primaerschluessel.
4. **`AUD-2026-09-120`: Evidenzzeile korrigieren.** "Genau ein Binding-Key" ist ein
   Fehlread (1 Redis-SET mit 4 Members). Findings-Nummer und Health-Bewertung
   bleiben **unveraendert** - das ist das Ergebnis dieses Abschnitts.
5. **`AUDIT_TRACEABILITY.md:152/153` zuruecknehmen.** Dort werden `-121` (Beat) und
   der Beat-Teil von `-120` als "widerlegt" gefuehrt, gestuetzt auf (a) einen Test,
   der die Task-Existenz im *Testprozess* prueft, und (b) eine DB-Row. Beides
   adressiert die *Worker*-Frage nicht. Insbesondere kann ein Test, der
   `audit.archive` importiert, die Registrierung im Worker nicht nachweisen.
6. **`AUD-2026-09-031`: "Totalausfall" -> "Cache-/Worker-Ausfall".** Bei DB-Ausfall
   liefert `/health/` korrekt 503.

---

## 8. Selbstauskunft zu dieser Pruefung

| Aspekt | Wert |
|---|---|
| Rolle | `code-reviewer` (Fact-Check-Pass, keine Produktänderung) |
| Live-Messungen | **0** (Stack aus, siehe Abschnitt 0) |
| Statische Messungen | 11 (Celery-Konfiguration, Bindungs-Tabelle, Fanout, Redis-Transport-Quelltext, `_parse_csv`, Route-Zählung, Manifest-Zählung, Test-Inventar, Git-Objektprüfung, Secret-Scan, Web-Recherche Anthropic) |
| Produktdateien geändert | **0** (`git diff --name-only abd61aed..HEAD \| where nicht docs/` = leer) |
| Neue Datei | genau diese |
