---
type: REVIEW
scope: "Live-Nachtest der Audit-Kriticals"
status: final
date: 2026-10-01
author_agent: senior-developer
branch: chore/audit-review-2026-09
method: "live against running stack localhost:8001 (Docker up)"
targets: [030, 031, 052, 071, 073, 074, 120, 121, 221, 222]
---

# REVIEW_LIVE_CRITICALS — Live-Nachtest der Audit-Kriticals

**Zweck.** Messung genau der Laufzeit-Behauptungen aus `AUDIT_FINDINGS.md`
§3/§5, den statischen WP-Reviews (`REVIEW_WP1A/1B/1C/1D/6A.md`) und dem
Secret-Kontext (`AUDIT_EVIDENCE/secret-incident-2026-09-30.md` §6), die bislang
nur statisch belegt bzw. als *NICHT VERIFIKABAR* ausgewiesen waren.

**Methodik & Grenzen.** Read-only/funktional gegen den laufenden Stack; **kein
Produktcode geändert, kein `git push`, kein `down -v`, keine destruktiven
DB-Operationen**. Redis wurde für den Ausfalltest gestoppt und anschließend
zwingend wieder gestartet; Endzustand: alle Container healthy. `.kimi-code/` und
`AUDIT_EVIDENCE/stack-seeds.md` wurden nicht angefasst; Zugangsdaten/Token sind
in diesem Dokument maskiert. Das audit-eigene `AUDIT_EVIDENCE/*` wurde **nicht**
als Beweis verwendet — jede Beobachtung stammt aus einer frischen Live-Messung.
Kein Playwright-MCP-Code (`browser_run_code_unsafe`/`browser_evaluate`/…) wurde
verwendet; es war kein Browser nötig.

**Stack-Snapshot (Projekt `ai-native-reqflow-poc`, HEAD `10dc620f`).**
Config-Files: `deploy/docker-compose.yml` + `deploy/docker-compose.override.yml`
+ `testing/docker-compose.test.yml`. Backend = **uvicorn `--reload`, 1 Worker**
(Sync-Views laufen im anyio-Threadpool). Cache = Django `RedisCache` auf **Redis
DB 1**; Celery-Broker/Result = **Redis DB 0** (`settings.py:792-793,878-884`).
`CACHES["default"]` hat **kein `OPTIONS`/`SOCKET_TIMEOUT`** (statisch bestätigt,
`settings.py:879-884`).

---

## 1. Stack-Zustand

| Messzeitpunkt | Beobachtung |
|---|---|
| Start | backend/frontend/celery/celery-beat/postgres/redis healthy; postgres-backup/bluepencil up |
| Nach Redis-Stopp (bounded) | `ai-native-reqflow-poc-redis-1` = `exited`; danach zwingend gestartet |
| Ende | redis `Up (healthy)`, alle übrigen healthy; `GET /health/` → 200 in 0,024 s; Redis-Keyspace intakt (db0=2429, db1=843) |

`docker ps` (Ende):
```
ai-native-reqflow-poc-frontend-1        :: Up (healthy)
ai-native-reqflow-poc-backend-1         :: Up (healthy)
ai-native-reqflow-poc-celery-1          :: Up (healthy)
ai-native-reqflow-poc-celery-beat-1     :: Up (healthy)
ai-native-reqflow-poc-postgres-backup-1 :: Up
ai-native-reqflow-poc-redis-1           :: Up 2 minutes (healthy)
ai-native-reqflow-poc-bluepencil-1      :: Up (healthy)
ai-native-reqflow-poc-postgres-1        :: Up (healthy)
```

> Hinweis: `docker compose -f deploy/docker-compose.yml ps` liefert **leer**,
> weil das Projekt über drei Config-Files läuft (Projektname
> `ai-native-reqflow-poc`). Korrekt ist
> `docker compose --project-name ai-native-reqflow-poc -f deploy/docker-compose.yml
> -f deploy/docker-compose.override.yml -f testing/docker-compose.test.yml ps`.
> Die Stopp/Start-Operation wurde über den eindeutigen Container-Namen
> `ai-native-reqflow-poc-redis-1` ausgeführt (nur so ist garantiert, dass nicht
> die getrennten Test-Stacks `reqlo-audit-*` getroffen werden).

---

## 2. Test-Matrix

| ID | Test | Befehl (Auszug) | Beobachtung | Verdikt |
|---|---|---|---|---|
| **AUD-030** | MCP hängt bei Redis-Ausfall (kein Timeout) | `docker stop …-redis-1`; danach `curl.exe --max-time 8 -X POST http://localhost:8001/mcp/ -H "Content-Type: application/json" --data-binary @tools_list.json` | **Kein HTTP-Response**; curl bricht nach **8,011 s** mit **exit 28** ab (`http=000`). Server-seitig bleibt der Request blockiert und läuft erst nach Redis-Rückkehr in den Fail-open-Zweig (WARNING `rate limiting cache unavailable for scope 'mcp_key' … fail-open`). | **BESTAETIGT** |
| **AUD-031** | `/health/` meldet bei Redis-Ausfall weiter `200 ok` | Redis down; `curl.exe -s http://localhost:8001/health/` | HTTP **200** in **0,024 s**, Body `{"status":"ok","checks":{…}}` — **kein** Cache-/Worker-/Beat-Check (`health.py` hat 0 Cache-Referenzen). | **BESTAETIGT** |
| **AUD-052** | Realer LLM-Default | `docker exec …-backend-1 sh -c 'env | grep ^LLM_'`; `python manage.py shell -c "…resolve_provider_config()"`; DB-Query `LlmSettings.unscoped` | Env: `LLM_PROVIDER=mock`, `LLM_MODEL=` (leer). Runtime `provider_name=mock`, `model_name=''`. DB `LlmSettings` rows = **0** (kein DB-Overlay). Shipped-Default ist **mock** — der retired Anthropic-Default ist nur bei `LLM_PROVIDER=anthropic` aktiv. | **TEILWEISE** (Kern „Default→Modell-ID" gilt nur opt-in; im ausgelieferten Stack **kein** Fehlschlag) |
| **AUD-071** | ReqIF-Import liefert `success:true` bei Fehlschlag | — | Ein ReqIF-Import erfordert Upload + Schreibzugriff auf einen Workspace (Datenmutation). Unter der Vorgabe „keine Produktdaten mutieren" nicht durchführbar. | **NICHT VERIFIKABAR** (Mutation erforderlich; Code-Ursache statisch in REVIEW_WP1D bestätigt) |
| **AUD-073** | HTTP 500 auf ungültiges `page` (trace-links/glossary), `/workspaces/` korrekt 404 | `GET /api/v1/workspaces/?page=0`; `GET /api/v1/trace-links/?workspace_id=<id>&page=0\|abc\|99999999`; `GET /api/v1/glossary/?workspace_id=<id>&page=0\|abc` | `/workspaces/?page=0` → **404** `Invalid page.`; `trace-links` (3 Werte) → **500** `INTERNAL_SERVER_ERROR`; `glossary` (2 Werte) → **500**. Backend-Log zeigt die Ursache zeilengenau: DRF-`NotFound("Invalid page.")` aus `views.py:3111` (TraceLink) bzw. `views.py:8369`→`:464` (Glossary) wird vom Service-`except` zu 500. | **BESTAETIGT** |
| **AUD-074** | 4 Listen-Endpunkte ohne Pagination | `GET /api/v1/api-keys/`, `/users/`, `/link-type-defaults/`, `/workspaces/<id>/link-type-definitions/` | Alle liefern ein **nacktes JSON-Array** (kein `count`/`next`); `page`/`page_size` wirkungslos. `api-keys` = **200 Items / 54 451 Bytes**; `users` = 2 089 B; `link-type-defaults` = **11 Items** / 6 432 B; `link-type-definitions` = 7 906 B. | **BESTAETIGT** |
| **AUD-120** | Alle 4 Queues identisch gebunden → Task 4× | `redis-cli -n 0 --no-raw SMEMBERS _kombu.binding.default`; `python -c "…app.conf.task_default_exchange/…/task_queues"` | `_kombu.binding.default` (SET) = 4 Members `default\x06\x16\x06\x16{default,llm,events,memory}`; `task_default_exchange=default`, `task_default_routing_key=default`; `task_queues = [('default','',''),('llm','',''),('events','',''),('memory','','')]`. Alle 4 Queues binden an exchange `default` / routing_key `default`. | **BESTAETIGT** |
| **AUD-121** | Beat dispatcht nie / Task nicht registriert / Healthcheck nur PID | `docker logs …-celery-beat-1 --since 60m \| grep -c "Sending due task"`; `celery -A reqogniloom inspect registered`; `deploy/docker-compose.yml:933` | **(c)** `Sending due task` = **0** (Fenster 60 min; Stack 17 min up) trotz **4 enabled** `PeriodicTask`-Rows (5 s Outbox, 60 s Heartbeat, monatliches Archiv). **(b)** `audit.archive_lifecycle_manager` **fehlt** im Worker-Set. **(a)** Healthcheck = `pgrep -f 'celery.*beat'` (nur Prozessexistenz), Container zeigt „healthy". | **BESTAETIGT** (a/b/c) |
| **AUD-221** | Rate-Limit vor AuthN + Bucket ohne Timeout | 5× `POST /mcp/ -H "X-API-Key: <invalider-key>"` (jeweils 401); `redis-cli -n 1 --scan --pattern '*throttle_mcp*'` + `STRLEN` | Schon der **401**-Request lädt Buckets: `:1:throttle_mcp_key_b679c448…` und `:1:throttle_mcp_ip_172.18.0.1`; nach 1 Request **24 B**, nach 5 Requests **61 B** (beide). Der Rate-Limit-Zähler wächst also **vor** jeder erfolgreichen Authentifizierung. | **BESTAETIGT** |
| **AUD-222** | Workspace-Fence greift auf mutierenden Routen ohne `workspace_id` nicht | — | Der Nachweis erfordert einen Nutzer mit Rolle in Workspace A, aber nicht B, **und** eine mutierende Route (oder das Anlegen eines workspace-gefenceten API-Keys). Beides sind Datenmutationen. Admin ist Tenant-Admin (alle Workspaces) → kein Fence-Unterschied beobachtbar. | **NICHT VERIFIKABAR** (Mutation/Scoped-User erforderlich; Mechanik statisch in REVIEW_WP6A bestätigt) |

---

## 3. Rohbeobachtungen

### 3.1 AUD-030/031/221 — Redis-Ausfall (Kernstück)

Baseline (`redis` healthy):
```
GET /health/                     -> http=200  t=0,0176 s
POST /mcp/ (no key)              -> 401  {"error":{"code":-32000,"message":"API key is required…"}}
POST /mcp/ (invalid key)         -> 401  {"error":{"code":-32000,"message":"Authentication failed: invalid_api_key"}}
```

Während `redis` = `exited`:
```
GET /health/                     -> http=200  t=0,0242 s
     {"status":"ok","checks":{"database":"ok","memory_backend":"ok",
      "embedding_dimensions":"ok","llm_provider_env":"ok",
      "csrf_cookie_secure_matches_auth":"ok"},"warnings":[]}
POST /mcp/ (no key)              -> http=000  t=8,0113 s  curl_exit=28   (Timeout, keine Antwort)
POST /mcp/ (invalid key)         -> http=000  t=8,0145 s  curl_exit=28   (Timeout, keine Antwort)
```
Server-seitig nach Redis-Rückkehr (Backend-Log):
```
admin_ops.rate_limits: cache read failed for ratelimit:overrides:global;
  redis.exceptions.ConnectionError: Error -2 connecting to redis:6379. Name or service not known.
rest_api.throttling: rate limiting cache unavailable for scope 'mcp_key';
  allowing request (fail-open) — limits are NOT enforced until the cache recovers
… POST /mcp/ HTTP/1.1" 401 Unauthorized
```
→ Der Client gibt nach 8 s auf; der Server-Thread bleibt länger blockiert (redis-py
`connect_check_health`/`call_with_retry` ohne `socket_connect_timeout`), der
Fail-open greift erst, als Redis/DNS wieder auflösbar war. **Kein** `SOCKET_TIMEOUT`
greift — die „unbegrenzt hängende" Behauptung ist für die Client-Sicht reproduziert.

### 3.2 AUD-221 — Bucket-Key und -Größe (Cache DB 1, nicht Broker DB 0)

```
DB 0 (Celery broker) dbsize = 2429–2432 ; DB 1 (Django cache) dbsize = 843–844
nach 1× invalid-key : throttle_mcp_key_b679c4480e7a16a4003900e6e76913f1 = 24 B
                      throttle_mcp_ip_172.18.0.1                       = 24 B
nach 5× invalid-key : throttle_mcp_key_b679c448…                       = 61 B
                      throttle_mcp_ip_172.18.0.1                       = 61 B
```
Die 5 Requests liefen **alle mit HTTP 401** (AuthN schlug fehl) — die Buckets wurden
dennoch gefüllt. Der Bucket-Key enthält den **SHA-256-Digest der übergebenen
(ungültigen) Credential**, d. h. pro vorgestellter Fremd-Credential entsteht ein
eigener Cache-Key (siehe §6, N1).

### 3.3 AUD-120 — Kombu-Bindings (Redis DB 0)

```
keys _kombu.binding.* : _kombu.binding.default, _kombu.binding.celeryev,
                        _kombu.binding.celery.pidbox, _kombu.binding.reply.celery.pidbox
TYPE _kombu.binding.default = set
SMEMBERS (--no-raw):
  1) "default\x06\x16\x06\x16default"
  2) "default\x06\x16\x06\x16llm"
  3) "default\x06\x16\x06\x16events"
  4) "default\x06\x16\x06\x16memory"
```
Kombu legt das Binding-Set unter dem **Exchange-Namen** ab (`_kombu.binding.default`
⇒ exchange = `default`); jedes Member ist `<routing_key>\x06\x16\x06\x16<queue>`.
⇒ **exchange = `default`, routing_key = `default`, queues = {default,llm,events,memory}**
— genau die 4-fache Zustellung. Verstärkend aus der App-Config:
```
task_default_exchange   = default
task_default_routing_key= default
task_default_queue      = default
queues = [('default','',''), ('llm','',''), ('events','',''), ('memory','','')]
```
Die leeren `exchange`/`routing_key`-Felder der `Queue(...)`-Objekte
(`celery.py:31-36`) fallen auf die Defaults zurück — das ist die live bestätigte
Wurzel des 4×-Befunds. (Es existiert **kein** `_kombu.binding.llm`/`.events`/`.memory`.)

### 3.4 AUD-121 — Beat-Dispatch & Registrierung

```
PeriodicTask (django_celery_beat): 4 Rows, 4 enabled
   - audit-monthly-archive            | task=audit.archive_lifecycle_manager
   - celery.backend_cleanup           | task=celery.backend_cleanup
   - record-celery-beat-heartbeat     | task=admin_ops.record_celery_beat_heartbeat
   - dispatch-outbox-events           | task=application.dispatch_outbox_events
" Sending due task " (--since 60m) = 0
Beat-Container: Up 17 min (healthy); MEM 249MiB / 256MiB (97,25 %); PID 1174 CPU ~2 %
Letzte Beat-Log-Zeile: 16:53:47 "DatabaseScheduler: Schedule changed." (danach keine)
Worker registered:
   admin_ops.record_celery_beat_heartbeat
   application.dispatch_outbox_events
   context_graph.rebuild_workspace_graph
   llm_adapter.run_capability
   memory.consolidate_interaction
   resilience.execute_optional_task
   -> audit.archive_lifecycle_manager NICHT enthalten
Beat-Healthcheck (compose:933): pgrep -f 'celery.*beat' > /dev/null || exit 1
```
Der 5-Sekunden-Schedule hätte im 15–60-min-Fenster hunderte `Sending due task`
erzeugen müssen; es waren **0**. Der Prozess ist sichtbar „gesund" (pgrep), tickt
aber nicht — und `audit.archive_lifecycle_manager` ist gar nicht erst registriert.
Auffällig: Beat lädt beim Start das SentenceTransformer-Modell (Django
`apps.ready()`) und steht bei **97 %** des 256-MiB-Limits (möglicher Stalls-Kontext,
siehe §6, N2).

### 3.5 AUD-052 — LLM-Default

```
backend env: LLM_PROVIDER=mock, LLM_MODEL= (leer), LLM_CAPABILITIES=…, LLM_API_KEY= (leer)
runtime resolve_provider_config(): provider_name=mock, model_name=''
persistence.LlmSettings.unscoped: rows = 0
```
Realer Default ist **mock** (credential-frei); kein DB-Overlay. Damit ist der
Anthropic-Retired-Model-Pfad **nicht** der Shipped-Default.

### 3.6 AUD-073/074 — Pagination (authentifiziert, Demo-Admin)

```
GET /api/v1/workspaces/                                  -> 200; count=401, next=…&page=2, page_size=25
GET /api/v1/workspaces/?page=0                           -> 404 {"error":{"code":"NOT_FOUND","message":"Invalid page."}}
GET /api/v1/trace-links/?workspace_id=…&page=0           -> 500 {"error":{"code":"INTERNAL_SERVER_ERROR",…}}
GET /api/v1/trace-links/?workspace_id=…&page=abc         -> 500
GET /api/v1/trace-links/?workspace_id=…&page=99999999    -> 500
GET /api/v1/glossary/?workspace_id=…&page=0              -> 500
GET /api/v1/glossary/?workspace_id=…&page=abc            -> 500
(ohne workspace_id: trace-links/glossary -> 400 "workspace_id is required")

GET /api/v1/api-keys/                              -> 200, 54 451 B, JSON-Array (200 Items)
GET /api/v1/users/                                 -> 200, 2 089 B, JSON-Array
GET /api/v1/link-type-defaults/                    -> 200, 6 432 B, JSON-Array (11 Items)
GET /api/v1/workspaces/<id>/link-type-definitions/ -> 200, 7 906 B, JSON-Array
```
Backend-Log (Ursache zeilengenau):
```
rest_api.views: Unhandled exception in service layer
  django.core.paginator.EmptyPage: That page number is less than 1
  … File "/app/rest_api/views.py", line 3111, in list
  rest_framework.exceptions.NotFound: Invalid page.
django.request: Internal Server Error: /api/v1/trace-links/ … status_code 500
```
(Dieselbe Kette für `PageNotAnInteger` bei `page=abc` und via `views.py:8369` →
`_paginate` → `:464` für Glossary.)

---

## 4. Verdikt-Zählung (n = 10 Ziele)

| Verdikt | Anzahl | IDs |
|---|---:|---|
| **BESTAETIGT** | 7 | 030, 031, 073, 074, 120, 121, 221 |
| **TEILWEISE** | 1 | 052 |
| UEBERZOGEN | 0 | — |
| FALSCH | 0 | — |
| **NICHT VERIFIKABAR** | 2 | 071, 222 |

Alle BESTAETIGT-Verdikte dieses Laufs sind **live** reproduziert (nicht nur
statisch). Die beiden NICHT-VERIFIKABAR-Fälle sind ausdrücklich durch die
„keine Datenmutation"-Vorgabe blockiert, nicht durch fehlende Evidenz zur Mechanik
(diese ist statisch in REVIEW_WP1D bzw. REVIEW_WP6A belegt).

---

## 5. Key-Verdikte

1. **AUD-030/031/221 BESTAETIGT — die Redis-Abhängigkeit ist der kritische Pfad.**
   Bei Redis-Ausfall liefert `/health/` **200 `ok` in 0,024 s** (kein Cache-Check),
   während **jeder** MCP-Request unbegrenzt hängt (Client-Timeout 8,01 s, exit 28;
   Fail-open erst nach Redis-Rückkehr). Der Rate-Limit-Check liegt nachweislich
   **vor** der AuthN: 401-Antworten füllen die Buckets (`throttle_mcp_key_<digest>`
   / `throttle_mcp_ip_<ip>`, 24→61 B bei 1→5 Requests). Ein einzelner Redis-Ausfall
   nimmt damit alle MCP-Clients in Beschlag, während die Health-Probe grün bleibt.

2. **AUD-120 BESTAETIGT — 4-fache Zustellung live manifestiert.** Alle 4 Queues
   binden an exchange `default` / routing_key `default` (`app.conf.task_default_*`
   = `default`; leere `Queue(exchange/routing_key)`). Redis zeigt genau **ein**
   Binding-Set mit **vier** Members. Eine ungeroutete Task wird 4× zugestellt.

3. **AUD-121 BESTAETIGT — Beat ist „healthy", aber tot; Archiv-Task fehlt.** 0×
   `Sending due task` in 60 min trotz 4 enabled `PeriodicTask`; Healthcheck nur
   `pgrep`. `audit.archive_lifecycle_manager` ist nicht im Worker registriert →
   monatliche Audit-Retention läuft nie.

4. **AUD-073/074 BESTAETIGT.** `workspaces/?page=0` → 404, `trace-links`/`glossary`
   → 500 (DRF-`NotFound` wird im Service-`try` geschluckt). Vier Listen-Endpunkte
   sind ungepagte Arrays; `/api-keys/` liefert exakt **200 Items / 54 451 B**.

5. **AUD-052 TEILWEISE.** Shipped-Default ist `mock` mit leerem Modell und ohne
   `LlmSettings`-Row; der retired Anthropic-Default ist nur bei Opt-in
   `LLM_PROVIDER=anthropic` wirksam. Kein Fehlschlag im ausgelieferten Stack.

---

## 6. NEU-AUDIT-LUECKE

**N1 — Per-Credential-Throttle-Bucket für ungültige Keys = Cache-/Speicher-Amplifikation (Medium).**
`McpApiKeyRateThrottle(credential or "")` (`mcp_server/throttling.py:164`) bildet
für **jede** vorgestellte, auch ungültige, Credential einen eigenen Bucket
(`throttle_mcp_key_<sha256[:32]>`). Live belegt: ein 401-Request legt sofort einen
neuen Key an. Ein Angreifer kann mit variierenden `X-API-Key`-Werten unbegrenzt
Cache-Keys erzeugen (TTL 60 s) — Redis läuft mit `maxmemory 256mb
--maxmemory-policy noeviction`, d. h. unbegrenztes Key-Wachstum ist ein
Speicher-/Eviction-Risiko, kein „nur" Rate-Limit-Thema. Der Modul-Docstring erklärt
nur die Per-IP-Backstop-Abdeckung, nicht diese Key-Churn. Empfehlung: ungültige/
leere Credentials nicht in den Per-Key-Bucket zählen (nur IP-Backstop) oder den
Bucket-Key auf verifizierte Keys begrenzen.

**N2 — Beat-Healthcheck erkennt „nicht tickenden" Beat nicht; 97 % Memory (Medium).**
`pgrep -f 'celery.*beat'` (compose:933) ist grün, obwohl Beat über 60 min **0**
Tasks dispatcht und seit dem 16:53-Start keine Log-Zeile mehr schreibt; der Prozess
steht bei **249/256 MiB (97,25 %)** — er lädt beim Start das SentenceTransformer-
Modell in einem 256-MiB-Container. Ein `Sending due task`-Age-Check (oder ein
Beat-Heartbeat-Age im Health-Endpoint) würde den Zustand sichtbar machen.
Verbindet AUD-121(a) mit AUD-031 (health prüft Beat nicht).

**N3 — MCP-Hang statt Fail-open: `socket_connect_timeout` fehlt ebenfalls (Low/Medium).**
Die Reproduktion zeigt, dass bei Ausfall nicht nur der Read-Timeout fehlt, sondern
auch der Connect/DNS-Pfad blockiert (`redis.exceptions.ConnectionError: Error -2
connecting to redis:6379. Name or service not known`, erst nach Rückkehr). Der
dokumentierte Fail-open (`rest_api/throttling.py:164-176`) greift nur, wenn eine
Exception *geworfen* wird — bei blockierendem Connect/Read passiert das zu spät.
Präzisiert AUD-030 um den DNS/Connect-Anteil.

**N4 — Messwert-Diskrepanz zur Audit-Evidenz (Info).**
Audit-Evidenz nannte für den Throttle-Bucket „187→205 Bytes"; gemessen wurden
**24→61 Bytes** (1→5 Requests) bei identischer Mechanik (Django-RedisCache-Pickle
der History-Liste). Die Absolutgrößen hängen von Vorbelegung/Serialisierung ab — die
Kernaussage (Wachstum vor AuthN) ist unabhängig davon reproduziert.

---

*Read-only Live-Messung. Kein Produktcode geändert, kein Push. `.kimi-code/` und
`AUDIT_EVIDENCE/stack-seeds.md` unangetastet; Credentials/Token maskiert. Stack am
Ende healthy.*
