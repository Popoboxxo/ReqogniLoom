---
type: REVIEW
scope: "W4 Live-Retest der bestätigten Audit-Kriticals (Fix-Verifikation)"
status: final
date: 2026-10-03
author_agent: sre-engineer
method: "live gegen laufenden Dev-Stack localhost:8001 (Docker Compose up)"
targets: [AUD-2026-09-030, AUD-2026-09-031, AUD-2026-09-120, AUD-2026-09-221]
---

# W4_LIVE_RETEST — Live-Nachtest der bestätigten Audit-Kriticals

**Zweck.** Verifikation der vier im Review 2026-09 als *bestätigt* ausgewiesenen
Laufzeit-Befunde **nach** Umsetzung der Fixes (RES-01/02/03/04, ADR-010/015) am
laufenden Dev-Stack auf Host-Port **:8001**. Vorgänger-Messung des Vorzustands:
`docs/audit/2026-09/review/evidence/REVIEW_LIVE_CRITICALS.md` (2026-10-01, alle
vier dort als BESTAETIGT = Bug reproduziert).

**Methodik & Grenzen.**
- Read-only gegen den laufenden Stack; **keine Produktcode-Änderung**, kein `git push`,
  kein `down -v`, keine destruktiven DB-Operationen.
- Für die Redis-Ausfalltests wurde ausschließlich der Container
  `ai-native-reqflow-poc-redis-1` gestoppt und **zwingend wieder gestartet**.
- Für den Celery-Routing-Test wurden `celery-1`/`celery-beat-1` **kurzzeitig**
  (Sekunden) pausiert, um Hintergrundverkehr (Beat-Dispatch) als Confounder
  auszuschließen — danach wieder gestartet. Keine Volumes/DB berührt.
- Keine echten Credentials verwendet; alle vorgestellten Schlüssel sind fiktive,
  vollständig redigierte `<redacted-invalid-key>`-Werte. Keine Secrets in diesem Dokument.
- **Hinweis `redis-cli`:** Der Container hat `REDISCLI_AUTH=` (leer) gesetzt; ein
  leeres AUTH setzt die DB-Auswahl (`-n`) zurück. Alle `redis-cli`-Aufrufe laufen
  daher über `sh -c "unset REDISCLI_AUTH; redis-cli -n <db> …"`.
- Cache = Redis **DB 1**, Celery-Broker/Result = Redis **DB 0**.

**Ist-Konfiguration der Fixes (statisch gelesen, ergänzend zur Live-Messung).**
- `settings.py`: `CACHES["default"]["OPTIONS"]` = `socket_connect_timeout` (Default
  **2.0 s**, env `CACHE_SOCKET_CONNECT_TIMEOUT`), `socket_timeout` (Default **5.0 s**,
  env `CACHE_SOCKET_TIMEOUT`), `pool_class=reqogniloom.bounded_dns.BoundedRedisConnectionPool`.
  Abweichung zum Task-Kontext (dort „timeout=1"): real 2 s/5 s + **1,5 s DNS-Budget**
  (`bounded_dns`, `CACHE_UNHEALTHY_COOLDOWN` 2,0 s). Die Live-Messung unten bestätigt
  das bounded Verhalten.
- `urls.py`: `/health/live` (+ Slash), `/health/ready` (+ Slash), `/health/` = Alias.
- `mcp_server/throttling.py`: `check_mcp_ip_rate_limit()` **vor** AuthN,
  `check_mcp_key_rate_limit(credential)` **nur nach** erfolgreicher AuthN und nur bei
  nicht-leerem Credential (kein Per-Key-Bucket für ungültige/leere Werte).
- `reqogniloom/celery.py`: vier Queues mit je eigenem `routing_key` auf dem geteilten
  Direct-Exchange `default`.

---

## 0. Baseline (Redis healthy)

```
TS=2026-10-03 19:58:51
GET /health/live  -> http=200 t=0.004095
GET /health/ready -> http=200 t=1.029836
GET /health/      -> http=200 t=1.037361
live  body: {"status": "ok", "checks": {}}
ready body: {"status": "ok", "checks": {"database": "ok", "memory_backend": "ok",
  "cache": "ok", "celery_worker": "ok", "celery_beat": "ok"}, "warnings": [],
  "dependencies": [], "advisory": {"embedding_dimensions": "ok",
  "llm_provider_env": "ok", "csrf_cookie_secure_matches_auth": "ok"}}
```

Stack: backend/frontend/celery/celery-beat/postgres/redis healthy; postgres-backup/bluepencil up.

---

## 1. AUD-2026-09-030 — MCP hängt bei Redis-Ausfall (kein SOCKET_TIMEOUT)

**Erwartung:** MCP-Endpoints antworten im Budget (nicht hängend), HTTP 503/500/401, kein Timeout > 5 s.

**Kommando (Redis gestoppt):**
```
docker stop ai-native-reqflow-poc-redis-1
curl.exe --max-time 8 -X POST http://localhost:8001/mcp/ \
  -H "Content-Type: application/json" --data-binary @mcp_tools_list.json
curl.exe --max-time 8 -X POST http://localhost:8001/mcp/ \
  -H "Content-Type: application/json" -H "X-API-Key: <redacted-invalid-key>" \
  --data-binary @mcp_tools_list.json
```

**Roh-Output (while Redis = Exited):**
```
POST /mcp/ (no key)      -> HTTP=401 t=1.521866s  exit=0
  body: {"jsonrpc":"2.0","id":1,"error":{"code":-32000,
         "message":"API key is required. Provide X-API-Key header or params.api_key."}}
POST /mcp/ (invalid key) -> HTTP=401 t=0.024504s  exit=0
  body: {"jsonrpc":"2.0","id":1,"error":{"code":-32000,
         "message":"Authentication failed: invalid_api_key"}}
POST /api/v1/mcp/ (invalid key) -> HTTP=401 t=0.025177s
```

**Server-seitiger Beleg (Backend-Log, während Redis down):**
```
redis.exceptions.ConnectionError: Error -3 connecting to redis:6379.
  DNS resolution for Redis host 'redis':6379 exceeded the 1.50s budget;
  taking the cache fail-open path.
rest_api.throttling: rate limiting cache unavailable for scope 'mcp_ip';
  allowing request (fail-open) — limits are NOT enforced until the cache recovers
```

**Bewertung:** Kein Hang, kein curl exit 28 (Timeout). Kaltlauf erster Request ~**1,52 s**
(= 1,5-s-DNS-Budget), Folge-Requests ~**0,025 s** (Cooldown-Pfad). Vor dem Fix:
HTTP 000 nach 8 s (curl exit 28). **Budget eingehalten (≤ ~2 s).**

**Verdikt: bestätigt behoben.**

---

## 2. AUD-2026-09-031 — `/health/` false-green bei Redis-Ausfall

**Erwartung:** `/health/ready` = **503** (cache down), `/health/live` = **200**.

**Kommando/Output (Redis = Exited):**
```
GET /health/ready -> HTTP=503 t=9.215582s
{"status": "degraded", "checks": {"database": "ok", "memory_backend": "ok",
 "cache": "error", "celery_worker": "error", "celery_beat": "error"},
 "warnings": [],
 "dependencies": [{"name": "cache", "status": "down", "detail": "dependency_down"},
                  {"name": "celery_worker", "status": "down", "detail": "dependency_down"},
                  {"name": "celery_beat", "status": "unknown", "detail": "dependency_down"}],
 "advisory": {...}}

GET /health/live -> HTTP=200 t=0.004352s
{"status": "ok", "checks": {}}

GET /health/ (Alias) -> HTTP=503 t=9.212582s
  response headers: deprecation: true
                    sunset: Thu, 01 Apr 2027 00:00:00 GMT
```

**Wiederherstellung:** `docker start ai-native-reqflow-poc-redis-1` → redis `healthy`
nach 6 s; `/health/ready` danach wieder **200** (`cache: ok`, alle Pflicht-Checks ok).

**Bewertung:** Fail-closed (503 mit `cache` down) statt vorher 200 `ok`. Liveness bleibt
200. Alias verhält sich wie `/health/ready` inkl. Deprecation/Sunset-Header.
**Beobachtung (nicht blocking):** Die Readiness-Probe selbst braucht im Ausfall **~9,2 s**
(blockierende Dependency-Checks), d. h. ein Orchestrator-Probe-Timeout < 9 s würde als
Timeout (ebenfalls fail-closed) werten. Siehe §6 O1.

**Verdikt: bestätigt behoben.**

---

## 3. AUD-2026-09-221 — Rate-Limit vor AuthN (Cache-Amplifikation)

**Erwartung:** 5 Requests mit UNGÜLTIGER Credential → HTTP 401 und **kein**
Per-Key-Throttle-Bucket (kein `throttle_mcp_key_*`-Wachstum durch ungültige Credentials).

**Kommando/Output (Redis healthy):**
```
Baseline DB1 throttle keys: total=0  mcp_key=0  mcp_ip=0

5x POST /mcp/ mit 5 VERSCHIEDENEN ungültigen X-API-Key-Werten:
  req1 http=401 t=0.020494s
  req2 http=401 t=0.018789s
  req3 http=401 t=0.018542s
  req4 http=401 t=0.019610s
  req5 http=401 t=0.019084s

Nachher DB1 --scan --pattern '*throttle*':
  total throttle keys = 1
  mcp_key buckets = 0
  mcp_ip  buckets = 1
  Key: :1:throttle_mcp_ip_172.18.0.1
```

**Bewertung:** Kein einziger `throttle_mcp_key_<sha256[:32]>`-Bucket wurde angelegt,
obwohl fünf distinkte ungültige Credentials vorgestellt wurden. Es wächst ausschließlich
der bewusst IP-gekeyte Backstop (`throttle_mcp_ip_<ip>`), der vor AuthN wirken soll und
kein Per-Credential-Key ist. Vor dem Fix wuchs der Per-Key-Bucket bereits bei 401
(24 B → 61 B bei 1 → 5 Requests).

**Verdikt: bestätigt behoben.**

---

## 4. AUD-2026-09-120 — 4 identisch gebundene Celery-Queues (Task 4×)

**Erwartung:** 1 publizierte Nachricht landet in **genau einer** Queue (nicht in allen vier).

**4.1 Live-Broker-Bindings (db0), nach Fix:**
```
docker exec …-redis-1 sh -c "unset REDISCLI_AUTH; redis-cli -n 0 --no-raw \
  SMEMBERS _kombu.binding.default"
1) "default\x06\x16\x06\x16default"
2) "llm\x06\x16\x06\x16llm"
3) "events\x06\x16\x06\x16events"
4) "memory\x06\x16\x06\x16memory"
5) "default\x06\x16\x06\x16events"      <-- Rest-Binding (siehe §6 O2)

Worker active_queues (routing_key je Queue):
  default -> routing_key 'default'   (exchange 'default', direct)
  llm     -> routing_key 'llm'
  events  -> routing_key 'events'
  memory  -> routing_key 'memory'
```
Format (aus `kombu/transport/redis.py::_queue_bind`): Member =
`routing_key\x06\x16pattern\x06\x16queue`. Die vier regulären Bindings sind je Queue
eindeutig (vorher: alle vier mit `routing_key=default`).

**4.2 Deterministischer Zustelltest.**
Confounder ausgeschlossen: `celery-1` **und** `celery-beat-1` pausiert (kein
Hintergrund-Dispatch). Linke Spalte Roh-Output:
```
baseline (quiet)                  : default=0 llm=0 events=0 memory=0
nach 10s quiet control (unverändert): default=0 llm=0 events=0 memory=0

publish 10x unrouted -> app.send_task('admin_ops.record_celery_beat_heartbeat')
  (routing_key = 'default')
after 10 unrouted publishes        : default=10 llm=0 events=0 memory=0

Worker danach wieder gestartet; queues drained -> default=0 llm=0 events=0 memory=0
```
**Ergebnis:** 10 publizierte, unroutete Nachrichten liegen **ausschließlich** in
`default` (+10); `llm`/`events`/`memory` bleiben **0**. Genau **eine** Zustellung pro
Nachricht.

**4.3 Methodik-Korrektur (Transparenz).** Eine frühere Beobachtung mit laufendem Beat
zeigte scheinbar +1 in `events`. Ursache war **Beat-Hintergrundverkehr**
(`dispatch_outbox_events` alle 5 s bzw. `record_celery_beat_heartbeat`), nicht Fanout:
Mit pausierten Produzenten (4.2) ist der Effekt reproduzierbar 0. Der 5-Member-Rest im
Binding-Set (§6 O2) löste im kontrollierten Test **keine** Mehrfachzustellung aus.
Isolations-Gegenprobe: 3 explizit `llm`-geroutete Tasks landeten nur in `llm`.

**Verdikt: bestätigt behoben** (im kontrollierten Test genau 1 Queue; die Rest-Binding
ist als Hygiene-Item vermerkt, nicht als aktive Fehlzustellung).

---

## 5. Abschluss-Zustand (Stack wiederhergestellt)

```
FINAL:
GET /health/live  -> http=200 t=0.005189
GET /health/ready -> http=200 t=1.033567   (cache/worker/beat alle ok)
GET /health/      -> http=200 t=1.031071

docker ps:
  ai-native-reqflow-poc-backend-1        :: Up (healthy)
  ai-native-reqflow-poc-frontend-1       :: Up (healthy)
  ai-native-reqflow-poc-celery-1         :: Up (healthy)
  ai-native-reqflow-poc-celery-beat-1    :: Up (healthy)
  ai-native-reqflow-poc-postgres-1       :: Up (healthy)
  ai-native-reqflow-poc-redis-1          :: Up (healthy)
  ai-native-reqflow-poc-postgres-backup-1:: Up
  ai-native-reqflow-poc-bluepencil-1     :: Up (healthy)

redis DBSIZE: db0 (broker) = 12829 ; db1 (cache) = 3818
```

**Redis und Stack am Ende healthy** — bestätigt.

---

## 6. Beobachtungen / Restrisiken (nicht Teil der 4 Verifikationen)

- **O1 (Low) — Readiness-Probe-Latenz im Ausfall ~9,2 s.** `/health/ready` blockiert
  bei Redis-Ausfall ~9,2 s (mehrere sequenzielle Dependency-Probes mit bounded
  Timeouts). Fail-closed bleibt korrekt; bei einem Probe-Timeout des Orchestrators
  < 9 s wird ebenfalls nicht-200 gemeldet (fail-closed). Empfehlung: Probes
  parallelisieren oder Timeout-Budget dokumentieren.
- **O2 (Low, Hygiene) — Rest-Binding `default→events`** im Live-Broker
  (`_kombu.binding.default` Member 5). Es ist nicht Teil der deklarierten
  `task_queues` (die vier regulären Bindings sind eindeutig) und verursachte im
  kontrollierten Test keine Mehrfachzustellung. Vermutlich ein Überbleibsel aus der
  Vorkonfiguration im laufenden Redis-Datensatz. Empfehlung: bei nächstem
  Broker-Neustart/Deploy prüfen, dass ein frischer Broker genau 4 Members zeigt, bzw.
  den veralteten Member kontrolliert entfernen. Kein Produktcode-Defekt.
- **O3 (Info) — `redis-cli`-AUTH-Quirk.** Container-Env `REDISCLI_AUTH=` (leer) setzt
  die `-n`-DB-Auswahl zurück; Messungen müssen `unset REDISCLI_AUTH` verwenden, sonst
  wird fälschlich DB 0 gelesen. Für künftige Evidenz-Läufe dokumentiert.

---

## 7. Verdikt-Zusammenfassung

| Finding | Vorzustand (2026-10-01) | Jetzt (live) | Verdikt |
|---|---|---|---|
| AUD-030 MCP-Hang bei Redis down | HTTP 000 / curl exit 28 nach 8 s | 401 in 1,52 s kalt / 0,025 s warm | **bestätigt behoben** |
| AUD-031 `/health/` false-green | 200 `ok` bei Redis down | `/health/ready` **503** (cache down), `/health/live` **200** | **bestätigt behoben** |
| AUD-221 Rate-Limit vor AuthN | 401 füllt `throttle_mcp_key_*` (24→61 B) | 401, **0** Per-Key-Buckets; nur IP-Backstop | **bestätigt behoben** |
| AUD-120 4× Queue-Zustellung | 1 Publish in 4 Queues | kontrolliert: 10 Publish → nur `default` | **bestätigt behoben** |

Keine der vier Prüfungen war „nicht verifizierbar": alle vier wurden **live**
reproduziert. Einzige Einschränkung: AUD-120 benötigt zur sauberen Messung das
kurzzeitige Pausieren der Hintergrundproduzenten (Beat/Worker), da sonst
Beat-Dispatch die Queue-Längen überlagert; danach Regeln sicher 1×.

---

*Live-Messung 2026-10-03. Keine Produktcode-Änderung. Container redis/celery/beat
kurzzeitig gestoppt und wiederhergestellt. Keine Secrets; API-Keys fiktiv/redigiert.
Stack am Ende vollständig healthy.*
