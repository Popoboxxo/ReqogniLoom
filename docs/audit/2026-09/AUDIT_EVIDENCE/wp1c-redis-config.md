---
type: EVIDENCE
scope: WP-1c — Redis 7 Cache/Broker-Konfiguration
status: final
date: 2026-09-29
author_agent: devops-engineer
---

# WP-1c E2 — Redis 7: Cache, Broker, Key-Namespace, Ausfallverhalten

Gemessen am **laufenden** Container `ai-native-reqflow-poc-redis-1` (nur
`INFO` / `CONFIG GET` / `KEYS` — reine Leseoperationen, kein Write, kein
`FLUSHDB`).

## 1. Server-Identität und -Konfiguration

| Parameter | Wert | Quelle |
|-----------|------|--------|
| `redis_version` | **7.4.11** | `INFO` |
| `maxmemory` | **268435456** (256 MB) | `CONFIG GET` |
| `maxmemory-policy` | **noeviction** | `CONFIG GET` |
| `appendonly` / `aof_enabled` | yes / 1 | `CONFIG GET` / `INFO` |
| `save` | `3600 1 300 100 60 10000` | `CONFIG GET` |
| `requirepass` | **(leer)** | `CONFIG GET` |
| `bind` | `* -::*` | `CONFIG GET` |
| `protected-mode` | **no** | `CONFIG GET` |
| `maxclients` | 10000 | `CONFIG GET` |
| `connected_clients` | **42** | `INFO` |
| `used_memory_human` | 3.94M | `INFO` |
| `evicted_keys` | 0 | `INFO` |
| `expired_keys` | 248 | `INFO` |
| `keyspace_hits` / `keyspace_misses` | 5866 / **10714** | `INFO` |
| `total_error_replies` | **5965** | `INFO` |

**Kontext der `noeviction`-Wahl** ist im Compose explizit begründet
(`deploy/docker-compose.yml:510-514`): `volatile-lru` hätte Broker-Nachrichten
ohne TTL stillschweigend eviziert. Die Entscheidung ist für den **Broker**
richtig. Sie hat aber eine **Nebenwirkung, die nirgends dokumentiert ist**:
`maxmemory-policy` gilt **serverseitig für alle logischen Datenbanken**, also
auch für den Django-Cache in db1. Bei 256 MB Volldruck liefert `noeviction`
`OOM command not allowed` — **Cache-Writes beginnen dann zu fehlschlagen**,
statt zu evicten. → `AUD-2026-09-131`.

`protected-mode no` + `bind *` ist vertretbar, weil Redis **keinen Host-Port**
publiziert (E1 §3) und nur im Compose-Netz erreichbar ist.

## 2. Logische Datenbanken und Trennung

| DB | Zweck | Keys | davon mit TTL | Konfiguration |
|----|-------|------|---------------|---------------|
| db0 | Celery **Broker** + **Result-Backend** + **MCP-Sessions** | **5918** | 5909 | `settings.py:792-793` |
| db1 | Django **Cache** | **831** | **183** | `settings.py:878` |

Die Broker/Cache-Trennung **über logische DBs funktioniert** und ist explizit
dokumentiert (`settings.py:862-864`). **Aber:** db0 enthält drei verschiedene
Nutzlasten. Siehe §4.

## 3. db0 — was liegt wirklich drin

Präfix-Histogramm über alle 5918 Keys:

| Präfix | Anzahl | Zweck | TTL |
|--------|--------|-------|-----|
| `celery-task-meta-<uuid>` | **5914** | Result-Backend (`result_expires = 1 day`) | 24 h |
| `_kombu.binding.default` | 1 | Queue-Binding | persistent |
| `_kombu.binding.celeryev` | 1 | Event-Exchange-Binding | persistent |
| `_kombu.binding.celery.pidbox` | 1 | `inspect ping`-Reply-Queue | persistent |
| `mcp:session:<uuid>:auth` | **4** | **MCP-Session-Authentifizierung** | — |

Zwei Befunde:

**(a) 5914 Result-Keys mit 24-h-TTL.** Gemessen live; `task_ignore_result =
False`, `result_expires = timedelta(days=1)` (live aus der laufenden App
ausgelesen). Das Backend-Worker-Banner zeigt `task events: OFF`. → `AUD-2026-09-132`.

**(b) `mcp:session:*` liegt in derselben DB wie der Broker.** Das ist genau
der Effekt, den `settings.py:862-864` für Cache-vs-Broker vermeiden will — für
Broker-vs-MCP-Session gilt er **nicht**. Die naheliegendste Notfallmaßnahme bei
einem Broker-Problem ist `redis-cli -n 0 FLUSHDB` (genau das, was der
`Dockerfile`-Kommentar bei `celery.backend_cleanup` nahelegt); das zerstört
**alle laufenden MCP-Sessions** und den DLQ-Zustand mit. → `AUD-2026-09-133`.

## 4. db1 — Django-Cache: Namespace und TTL

`CACHES` (`backend/reqogniloom/settings.py:879-884`) ist **vollständig**:

```python
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}
```

**Kein `SOCKET_TIMEOUT`, kein `TIMEOUT`, kein `OPTIONS`, kein `KEY_PREFIX`,
kein `KEY_FUNCTION`.**

### 4.1 Was wird gecacht (live gemessene Präfixe, db1, 831 Keys)

| Präfix | Keys | permanent (TTL = -1) | mit TTL | Quelle |
|--------|-------|----------------------|---------|--------|
| `llm_derivation_ver` | **648** | **648** | 0 | `application/ai_derivation_service.py:396` und `:500` — `cache.set(version_key, version, None)` |
| `reqogniloom:cachegen:preset` | 181 | 0 | 181 | Preset-Cache-Generierung |
| `throttle_mcp_key_*` | 1 | 0 | 1 | MCP-Rate-Limit (gut) |
| `throttle_mcp_ip_*` | 1 | 0 | 1 | MCP-Rate-Limit (gut) |
| **Summe** | **831** | **649** | **182** | |

`timeout=None` bedeutet in Django *unbegrenzt*. Es existiert **kein
`cache.delete()`** für `llm_derivation_ver` im Repo. Der Bestand wächst um
**einen Key pro Artefakt** (Key-Schema: `llm_derivation_ver:{artifact_id}`)
und wird **nie** wieder freigegeben. → `AUD-2026-09-130`.

Bei aktuell 3,94 MB `used_memory` ist das unkritisch. Die Fehlerklasse ist
trotzdem real: bei `noeviction` werden Cache-Writes bei 256 MB **hart mit
`OOM command not allowed` fehlschlagen** — und `CACHES` hat keinen Timeout,
der das abfangen würde.

### 4.2 Tenant-Sicherheit des Key-Namespace

**Befund: Der Namespace enthält keine Tenant-Komponente.** Es gibt weder
`KEY_PREFIX` noch `KEY_FUNCTION`. Die Trennung hängt vollständig davon ab, dass
die im Key eingebetteten UUIDs global eindeutig sind:

- `llm_derivation_ver:{artifact_id}` — UUID, PK → **keine Kollision möglich.**
- `reqogniloom:cachegen:preset:{preset_id}` — UUID, PK → **keine Kollision möglich.**

Bewertung: **in der aktuellen Implementierung tenant-sicher, aber nur
*zufällig* — die Invariante ist nicht kodiert.** Ein nicht-UUID-schlüssel
(Workspace-Lesezeichen, Slug, zusammengesetzter Schreibschlüssel) würde
sofort kollidieren. Zusätzlich: `KEY_PREFIX` fehlt, d. h. jede andere
Anwendung, die Redis **db1 derselben Instanz** nutzt, teilt sich den Namespace
ohne Vorwarnung. → `AUD-2026-09-134`.

### 4.3 Cache-Hit-Rate

`keyspace_hits 5866` / `keyspace_misses 10714` → **35,4 % Hit-Rate** über die
gesamte Lebenszeit des Containers. Kein Finding per se (der Container läuft erst
6 h und der Bestand ist noch jung), aber als Messwert festgehalten.

## 5. Ausfallverhalten bei Redis-Down

### 5.1 Bestätigter Pfad: unbegrenztes Hängen

`CACHES` (settings.py:879-884) enthält **kein** `SOCKET_TIMEOUT`. Der von
`RedisCache` an redis-py weitergereichte Socket hat damit **kein Zeitlimit**.
`redis-py` verbindet mit `socket_connect_timeout=None` /
`socket_timeout=None`; ein TCP-Connect auf eine Paket-Filter-Firewall
(hang-up statt RST) oder eine Partition mit Antwortverlust blockiert den
Aufrufer-Thread **unbegrenzt**.

Belegt durch den Vor-Audit-Befund: bei laufendem Redis-Totalausfall hängen
**13/13 MCP-Endpunkte** unbegrenzt. → `AUD-2026-09-030` **BESTAETIGT**,
unverändert in `settings.py:879`.

**Verschärfung gegenüber dem Vor-Audit:** Der Ausfall ist nicht der einzige
Pfad, und der Fehler braucht keinen Ausfall. Siehe §1/§4 — `noeviction` @ 256 MB
lässt `cache.set()` auch im **Normalbetrieb** mit `OOM command not allowed`
scheitern, und `CACHES` hat keinen `TIMEOUT`, der das als Fehler behandelt
(sonst stiller Fehlschlag). → `AUD-2026-09-131`.

### 5.2 Gibt es einen Fallback-Pfad?

**Nein.** Es gibt:

- **kein** `KEY_PREFIX`/`KEY_FUNCTION`-basiertes Failover,
- **kein** `django-redis` mit Sentinel/Cluster-Fallback,
- **keine** `DummyCache`-Degradation in `settings.py`,
- **keinen** `Circuit-Breaker` um Cache-Zugriffe herum.

Der einzige `Circuit-Breaker` im Projekt liegt in `llm_adapter/`, nicht am
Cache. Beim Totalausfall ist das beobachtete Verhalten damit **Hängen, nicht
Fehlschlag** — der für einen Load-Balancer schlimmere der beiden Fälle, weil
ein `/health/`-Probe weiter 200 liefert (siehe E5).

## 6. Abgleich mit `deploy/docker-compose.yml:531-546`

Der `entrypoint`-Wrapper macht `REDIS_PASSWORD` optional (dev: kein
`requirepass`, prod: gesetzt) — **korrekt** und mit
`REDISCLI_AUTH` für den Healthcheck umgesetzt, ohne das Passwort in `ps`
offenzulegen. Das ist ein **PASS**.

Gemessen: `requirepass` ist im laufenden Stack leer, `REDIS_PASSWORD` ist in
`deploy/.env` nicht gesetzt. Konsistent.

**PASS:** AOF ist an **und** `/data` liegt auf dem benannten Volume
`redis_data` (`deploy/docker-compose.yml:526-527`) — ohne dieses Volume würde
jedes `up --force-recreate` Queue und Cache stillschweigend verlieren. Die
Sorge ist im Compose-Header (`:522-525`) explizit adressiert.
