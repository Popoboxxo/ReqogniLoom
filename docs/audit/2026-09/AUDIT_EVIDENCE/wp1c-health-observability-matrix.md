---
type: EVIDENCE
scope: WP-1c — Health-/Readiness-Matrix und Observability
status: final
date: 2026-09-29
author_agent: devops-engineer
---

# WP-1c E6 — Health/Readiness-Endpunkte und Observability

## 1. Live-Probe der Endpunkte (unauthentifiziert, gegen `localhost:8001`)

| Pfad | HTTP | Bytes | Auth | Bemerkung |
|------|------|-------|------|-----------|
| `/health/` | **200** | 183 | **keine** | Container-Healthcheck des `backend` |
| `/healthz` | 404 | – | – | existiert **nur** auf `frontend` (nginx), nicht im Backend |
| `/metrics` | 404 | – | – | existiert nicht |
| `/metrics/` | 404 | – | – | existiert nicht |
| `/api/v1/metrics/` | **401** | – | JWT | das ist der eigentliche „Metrics"-Endpunkt |
| `/api/v1/admin/health/` | **401** | – | JWT | System-Health-Dashboard |
| `/api/v1/version/` | **200** | 50 | keine | |
| `/api/schema/` | **200** | 613 769 | keine | OpenAPI, ungeschützt |

**Antwortbody von `/health/` (vollständig):**

```json
{"status": "ok",
 "checks": {"database": "ok",
            "memory_backend": "ok",
            "embedding_dimensions": "ok",
            "llm_provider_env": "ok",
            "csrf_cookie_secure_matches_auth": "ok"},
 "warnings": []}
```

## 2. Health-Check-Matrix

| Abhängigkeit | Wird geprüft? | Quelle | Verhalten bei Ausfall |
|---------------|----------------|--------|----------------------|
| **PostgreSQL** | **JA** | `health.py:123-136` | `checks.database = "error"`, `status = "degraded"` (HTTP **200**) |
| Memory-Backend (Honcho/Ollama) | JA | `health.py:151-160` | `checks.memory_backend = "error"`, `status = "degraded"` |
| Embedding-Dimension | JA | `health.py:185-215` | `checks.embedding_dimensions = "mismatch"`, nur `warnings` |
| LLM-Pflicht-Env-Variablen | JA | `health.py:229-239` | `checks.llm_provider_env = "missing"`, nur `warnings` |
| CSRF-Cookie-Sicherheit | JA | `health.py:261-268` | nur `warnings` |
| Workflow-Definitionen | JA | `health.py:282-310` | nur `warnings` |
| **Redis / Django-Cache** | **NEIN** | – | **nicht erkannt** |
| **Celery-Worker** | **NEIN** | – | **nicht erkannt** |
| **Celery-Beat** | **NEIN** | – | **nicht erkannt** |
| Backup-Sidecar | NEIN | – | nicht erkannt |
| Daten-Aktualität (WAL-/Replikations-Lag) | NEIN | – | – |

**Vergleich mit der Realität zum Probezeitpunkt:** `celery-beat` hatte nachweislich
seit über 3 Tagen Laufzeit **keine einzige** Aufgabe dispatcht (E3 §3), und
`/health/` meldete `200 {"status": "ok", "warnings": []}`.
⇒ **`AUD-2026-09-031` BESTAETIGT und VERSCHÄRFT.**

Verschärfung gegenüber der Vor-Audit-Beschreibung: es fehlt nicht nur der
Cache-Check. Es fehlen **alle drei** asynchronen Komponenten (Cache, Worker,
Beat). Der Healthcheck ist damit ein reiner **Datenbank + Konfiguration**-Check
und deckt die Hälfte der Laufzeitabhängigkeiten ab.

**Statuscode-Semantik:** Der View gibt bei `degraded` weiterhin **HTTP 200**
zurück und signalisiert den Zustand nur im Body. Für einen
Load-Balancer/Orchestrator, der auf den Statuscode schaut, ist ein
Datenbankausfall damit **nicht** von einem gesunden System unterscheidbar.
`deploy/docker-compose.yml:642` nutzt `curl -f http://localhost:8000/health/`
— `curl -f` schlägt nur bei **HTTP ≥ 400** fehl, `degraded` bei 200 passiert.
⇒ Der `backend`-Container bleibt bei Datenbankverlust `healthy`, und
`frontend` (das `depends_on: backend: service_healthy`) startet ebenfalls.
→ Teil von `AUD-2026-09-129`

## 3. Gibt es getrennte Liveness und Readiness?

**Nein.** Es existiert **genau ein** Endpoint (`/health/`,
`backend/reqogniloom/urls.py:28`), und er ist **zugleich**:

* **Liveness** — der Docker-Healthcheck des `backend`-Containers
  (`deploy/docker-compose.yml:641-646`),
* **Readiness-Proxy** — weil `frontend` `depends_on: backend:
  condition: service_healthy` (`:982-984`).

**Das ist konzeptionell falsch herum:** Liveness soll bei
Abhängigkeitsausfall **nicht** fehlschlagen (sonst killt der Orchestrator
gesunde Prozesse, weil die Datenbank kurz weg ist), Readiness soll es
**schon**. Hier ist beides dasselbe Signal, und weil `degraded` HTTP 200
liefert, ist es **überhaupt keines von beiden** für den Ausfallfall.

Empfehlung (nicht implementiert — reine Audit-Arbeit):
`/livez` (Prozess lebt, keine externen Calls) und `/readyz` (DB **und** Redis
**und** Queue-Erreichbarkeit; 503 bei Fehler), `/health/` als
Detail-Diagnose für Menschen.

**Was es stattdessen gibt:** Der Celery-Healthcheck ist ein `inspect ping`
(`deploy/docker-compose.yml:847`) — das ist ein Worker-Liveness-Signal, aber
ebenfalls nur **Prozess**-Ebene, kein Task-Fluss. Der Beat-Healthcheck ist
`pgrep -f 'celery.*beat'` (`:933`) und prüft **ausschließlich
Prozessexistenz** — deshalb meldete er `healthy`, während der Beat
nichts dispatchte.

## 4. `/api/v1/metrics/` — WP-1d-Frage beantwortet

WP-1d meldete „782 KB ungepaged". Die Aufklärung:

* Der Pfad ist **nicht** `/metrics/`, sondern `/api/v1/metrics/`
  (`backend/rest_api/urls.py:237`,
  `router.register(r"metrics", MetricsViewSet, basename="metrics")`).
* **Authentifiziert:** ohne JWT ⇒ **HTTP 401**. Für eine Produktion ist das
  die richtige Entscheidung.
* **Es ist kein Prometheus-Exporter.** `MetricsViewSet` ist ein REST-Proxy auf
  `se_metrics.services.compute_metrics` — ein **SE-Coverage-/Metrik-Bericht
  pro Workspace** (`workspace_id` ist Pflichtparameter), kein
  Maschinen-Monitoring-Export.
* `grep -i "prometheus\|opentelemetry\|sentry\|structlog"` über
  `backend/requirements*.txt` und `backend/pyproject.toml`:
  **null Treffer.**

⇒ **Es existiert kein einziger Prometheus-Scraping-Endpunkt, kein
Exporter, kein Push-Gateway.** Der Auth-Reminder aus der Aufgabenstellung ist
damit beantwortet: ja, authentifiziert — aber die *Richtigkeit* der
Entscheidung ist nicht der Kern; der Kern ist, dass **kein** Exporter existiert.
**Die 782 KB sind Nutzdaten pro Workspace, kein Health-Signal.**
→ `AUD-2026-09-141`

## 5. Logging

### 5.1 Konfiguration (`backend/reqogniloom/settings.py:899-955`)

| Aspekt | Wert | Bewertung |
|--------|------|-----------|
| Format (Produktion) | `pythonjsonlogger.json.JsonFormatter` | **PASS** — strukturiert |
| Format (DEBUG) | `{levelname} {asctime} {module} {request_id} {message}` | ok |
| Format-Feld | `%(asctime)s %(name)s %(levelname)s %(request_id)s %(message)s` | **request_id in jeder Zeile** |
| Filter | `reqogniloom.middleware.RequestIdFilter` | **PASS** — Korrelation |
| Handler | `StreamHandler` → stdout | Container-Standard |
| Root-Level | `"INFO"` **hart kodiert** | **Befund** |
| `django` | INFO | |
| `django.db.backends` | WARNING (bzw. DEBUG bei `DEBUG`) | richtig — SQL nur im DEBUG |
| `reqogniloom` | INFO | |
| `celery` | INFO | |

**Befund:** Es gibt **keine `LOG_LEVEL`-Environment-Variable**. Das Root-Level
ist die literale Zeichenkette `"INFO"`. Für einen Produktionsbetrieb, in dem
man z. B. einen 5xx-Burst zeitweise auf `WARNING` drehen möchte, ohne das Image
neu zu bauen, gibt es **keinen** Hebel. Alle anderen Observability-Schalter im
Projekt sind env-konfigurierbar (`DB_STATEMENT_TIMEOUT_MS`, `SECURE_HSTS_SECONDS`,
`CELERY_CONCURRENCY`, …) — die Log-Stufe ist die Ausnahme.
→ Teil von `AUD-2026-09-141`

### 5.2 Rotation

**PASS auf Docker-Ebene:** `deploy/docker-compose.yml:67-70` begründet
ausdrücklich, warum `logging: {driver: json-file, options: {max-size, max-file}}`
**pro Service** wiederholt werden muss, weil der Default nicht rotiert. 11 von
15 Services haben `10m × 3` ⇒ **30 MB pro Service gedeckelt**.

**Lücke:** Die 4 `honcho`-Profil-Services (`honcho-postgres`, `honcho-redis`,
`honcho-migrate`, `honcho`) haben **keinen** `logging:`-Block ⇒
**unbegrenztes** `json-file`-Wachstum. `honcho` ist ein API-Server, der bei
jedem Fehler stacktraces loggt. → `AUD-2026-09-135`

**Keine** Log-Rotation auf **Anwendungsebene** (kein `logging.handlers.RotatingFileHandler`
im `LOGGING`-Dict) — bei json-Datei-Logging nach stdout ist das auch nicht nötig.

### 5.3 PII / Secrets in Logs — Stichprobe

Live im Beat-Bootlog beobachtete Zeilen (repräsentativ für das Format):

```json
{"asctime": "...", "name": "audit.writer", "levelname": "INFO", "request_id": "N/A", "message": "AuditLogWriter registered on DomainEventBus."}
{"asctime": "...", "name": "llm_adapter.apps", "levelname": "INFO", "request_id": "N/A", "message": "LlmAdapterConfig.ready(): embedding model preloaded (SentenceTransformersEmbeddingProvider)"}
{"asctime": "...", "name": "context_graph.projector", "levelname": "INFO", "request_id": "N/A", "message": "ContextGraphProjector registered on DomainEventBus for 34 event type(s)."}
```

* `request_id: "N/A"` in **Worker-/Beat-Prozessen** — korrekt, dort gibt es
  keinen Request. Der `ContextVar` ist thread-lokal; Prefork-Kinder erben
  keinen Wert.
* Tenant-UUIDs werden geloggt (`llm_adapter/tasks.py:147-152`) — **keine** PII.
* **Kein** API-Key, **kein** `SECRET_KEY`, **kein** DB-Passwort in der Stichprobe.
* `postgres-backup` loggt `POSTGRES_DB`/`POSTGRES_HOST` (nicht das Passwort);
  `export PGPASSWORD` steht im `command:`-Text, wird aber von `pg_dump` als
  Env-Variable genutzt, **nicht** in die Befehlszeile geschrieben — korrekt
  (gleiches Muster wie bei Redis/SA-51).

⇒ **Kein Secret-Logging-Befund.** Präzise Grenze der Prüfung: **Stichprobe**,
kein vollständiger Audit aller Log-Aufrufe; `BLOCKED` für die
Vollständigkeitsaussage.

## 6. Tracing

**Nicht vorhanden.**

| Merkmal | Status | Beleg |
|---------|--------|-------|
| OpenTelemetry / `opentelemetry-*` | **nein** | `grep` über `backend/requirements*.txt`, `backend/pyproject.toml` → 0 |
| `traceparent` / W3C-Trace-Context | **nein** | keine Treffer in `backend/` |
| Sentry / Error-Reporting | **nein** | 0 Treffer; obwohl `SENTRY_ENABLED` in `deploy/docker-compose.yml:78` für Honcho gesetzt wird (dort ist es ein Honcho-eigenes Flag, kein SDK dieses Projekts) |
| `request_id` als Korrelation | **ja** | `settings.py:905-916`, `RequestIdFilter` |
| Log-basierte Kette über Prozessgrenzen | **nein** | Celery-Task-ID wird nirgends in den `request_id` übernommen |

⇒ `request_id` ist **Request**-Korrelation innerhalb eines Prozesses, **keine**
distributed Traces. Eine Anfrage, die `backend` → `celery` → `DB` durchläuft,
hinterlässt **keine** durchgängige Kette; die Celery-Task-ID erscheint nirgends
in den Anwendungs-Logs. Bei genau den asynchronen Pfaden, die in E3 als
defekt auffielen, fehlt damit auch das Werkzeug, um sie zu diagnostizieren.
→ `AUD-2026-09-141`

## 7. Docker-Nutzungsmetriken (verfügbar, aber ungenutzt)

Gemessen im laufenden Stack: `connected_clients: 42` Redis-Verbindungen bei
11 Containern. `maxclients` ist 10000 ⇒ **kein** Engpass. Es gibt **keine**
Ableitung von `docker stats`, keine cgroup-Metrik, kein
`/actuator/health`-Äquivalent. `pg_stat_user_tables.n_live_tup` weicht
tatsächlich stark von den exakten Zahlen ab (`pl_artifact` 3432 exakt vs.
`n_live_tup`-Schätzung, `as_domain_event_outbox` 6861 exakt vs. Schätzung in
derselben Abfrage) ⇒ **`n_live_tup` ist als Kapazitätsindikator unbrauchbar**,
was die Frage nach einem Kapazitäts-/Sättigungs-Monitoring verschärft.
→ Teil von `AUD-2026-09-141` / `CR-35`
