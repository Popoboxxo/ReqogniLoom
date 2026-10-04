---
type: REVIEW
scope: wp6b-concurrency-observability
status: complete
date: 2026-09-30
author_agent: code-reviewer
---

# WP-6b Evidence 05 — Observability- und Health-Matrix

## A. Logging-Konfiguration

### A.1 `LOGGING` (settings.py:899-953) — **hartkodiert, keine Env-Steuerung**

```python
"console": {  "class": "logging.StreamHandler",
              "formatter": "verbose" if DEBUG else "json",     # Z. 923
              "filters": ["request_id"] },
"root":     { "handlers": ["console"], "level": "INFO" },     # Z. 927-930
"django": INFO | "django.db.backends": DEBUG if DEBUG else WARNING
"reqogniloom": INFO | "celery": INFO
```

| Merkmal | Befund |
|---|---|
| Level je Umgebung | **NICHT konfigurierbar.** `rg "LOG_LEVEL\|DJANGO_LOG\|LOGGING_LEVEL" settings.py deploy/*.yml` → **0 Treffer**. `django.db.backends` ist die einzige stufbare Stufe, und auch sie nur über `DEBUG`. |
| Format | JSON (`pythonjsonlogger`) außer bei `DEBUG` → `verbose`. |
| Rotation | **Nicht** in `LOGGING` (nur `console`-StreamHandler). **Wird aber** auf Deploy-Ebene gelöst: `deploy/docker-compose.yml` setzt für **jeden** Service `logging: {driver: json-file, options: {max-size: 10m, max-file: 3}}` (Z. 285, 501, 547, 636, 734, 786, 841, 923, 971, 1305, 1344). **PASS.** |
| PII/Secrets | **PASS (Fehlalarm bei der Suche).** 3 Kandidaten, alle benign: `llm_adapter/token_tracking.py:163,207` loggen ein Exception-Objekt; `mcp_server/tool_registry.py:1310` loggt einen statischen String. **Kein** Logger gibt Passwort, Token, API-Key, DSN oder Personenfeld aus. Der CWE-209-Schutz ist konsequent (vgl. `reqogniloom/health.py:128-136`, `rest_api/metrics_views.py:88-96`). |

**Wichtige Korrektur an einer eigenen Hypothese:** Ich vermutete zunächst, `DEBUG`
könne das JSON-Format in Produktion unbemerkt abschalten. `settings.py:68`
gilt aber `DEBUG = _debug_requested and DJANGO_ENV in _NON_PROD_ENVS`; live ist
`DEBUG=False`. **Produktions-JSON-Format ist strukturell erzwungen. Hypothese
retracted.**

**Verbleibender, realer Befund:** die Fixierung auf `INFO` (Z. 929/934/944/949)
macht **jedes** `logger.debug(...)` in einem Fail-closed-Pfad unsichtbar. Genau
das trägt `mcp_server/tool_registry.py:1381,1411,1520` → **274**. → **276**

### A.2 Request-ID / Tracing

| Aspekt | Befund | Ort |
|---|---|---|
| Middleware | vorhanden und korrekt: `HTTP_X_REQUEST_ID` wird **UUID-validiert** übernommen (Z. 62-66), sonst neu erzeugt (Z. 69-71); ContextVar (Z. 18-19, 75) mit `reset` im `finally` (Z. 89-91) gegen Thread-Pool-Leck | `reqogniloom/middleware.py:42-91` |
| Log-Injektion | `RequestIdFilter` hängt `request_id` an **jedes** LogRecord; `%(request_id)s` im JSON-Format | `middleware.py:28-39`, `settings.py:905-908` |
| Antwort-Header | `X-Request-ID` | `middleware.py:85` |
| **Fehler-Antwortskörper** | **FEHLT.** `build_error_response` liefert `{error:{code,message,details}}` — **keine** Korrelations-ID | `rest_api/serializers.py:241-257` |
| **`trace_id` repo-weit** | **0 Treffer** (außer Tests) | — |
| **Audit-Eintrag** | `rg "request_id" audit/` → **0 Treffer**. `audit_entry` hat 19 Spalten, keine Korrelationsspalte. | — |

**Verdichtung:** Die Kette `Log → Fehlerantwort → Audit-Eintrag` ist an
**genau einer** Stelle unterbrochen: sie endet nach dem Log. Ein Support-Fall
mit einem `X-Request-ID` aus der Fehlermeldung lässt sich nicht auf den
Audit-Eintrag beziehen — und der Audit-Eintrag ist der einzige
forensisch belastbare Kanal. **Befund 077 wird damit bestätigt und
verschärft**: nicht „kein `trace_id` in Fehlerantworten", sondern
**„Korrelations-ID wird nicht persistiert"**. → **278**

## B. Health / Readiness

### B.1 Live-Probe (read-only, aus dem Backend-Container)

```
$ curl -s -w 'HTTP=%{http_code} time=%{time_total}s' http://localhost:8000/health/
HTTP=200 time=0.016850s
{"status": "ok",
 "checks": {"database": "ok", "memory_backend": "ok", "embedding_dimensions": "ok",
            "llm_provider_env": "ok", "csrf_cookie_secure_matches_auth": "ok"},
 "warnings": []}
```

### B.2 Health-Check-Abdeckungsmatrix

| Abhängigkeit | `/health/` (Orchestrator-Probe) | `/api/v1/admin/health/` (SystemHealthView) | Docker-Compose-`depends_on` |
|---|---|---|---|
| **Datenbank** | ✅ `ensure_connection()` (health.py:124-126) | ✅ `_check_database()` (Z. 86) | ✅ `pg_isready` (compose 291) |
| **Redis / Cache** | ❌ **fehlt** | ✅ `_check_redis()` (Z. 96-110) | ✅ (compose 552-556) |
| **Celery-Worker** | ❌ **fehlt** | ✅ `_check_celery_worker()` — `inspect ping` (Z. 113-132) | ✅ `inspect ping` (compose 847) |
| **Celery-Beat** | ❌ **fehlt** | ✅ `_check_celery_beat()` — Cache-Heartbeat (Z. 135-198) | ✅ `pgrep -f 'celery.*beat'` (compose 933) |
| **MCP-Server** | ❌ **fehlt** | ✅ `_check_mcp_server()` (Z. 200) | — |
| **LLM-Provider** | ⚠️ nur *env-var vorhanden* (health.py:233-254), **kein** Erreichbarkeitstest | ✅ `_check_llm_provider()` (Z. 235) | — |
| **Memory/Embedding-Backend** | ✅ (health.py:151-164) | ✅ `_check_memory_backend()` (Z. 425) | — |
| **Embedding-Dimension** | ✅ (health.py:185-215) | — | — |
| **CSRF/Cookie-Konsistenz** | ✅ (health.py:256-274) | — | — |
| **Workflow-Definitionen** | ✅ (health.py:282-310) | — | — |
| **Outbox-Backlog** | ❌ **fehlt** | ❌ **fehlt** (nur `_recent_audit_events`, Z. 487) | — |

**Befund-Kern:** Die **Abdeckung existiert** — aber nur auf dem
**admin-authentifizierten** Endpunkt (`rest_api/urls.py:383-385`, RBAC
`Operation.WORKSPACE_CONFIG`, `health_rest.py:517-523`). Die
**Orchestrator-Probe** `curl -f http://localhost:8000/health/`
(`deploy/docker-compose.yml:642`) nutzt ausgerechnet die **schwache** Variante.
→ **286**

**Konsequenz, konkret:** Fällt Redis oder der Worker aus, meldet
`/health/` weiterhin `200 {"status":"ok"}`. Docker markiert den Backend-Container
als `healthy`. Neustarts, `depends_on`-Neuverknüpfungen und externe
Liveness-Probes greifen **nicht**. Der Admin-Dashboard zeigt zur selben Zeit
`celery_worker: down`. Genau dieser Zustand ist im aktuellen Stack nicht
beobachtbar, weil beide Ebenen grün melden.

### B.3 Getrennte Liveness und Readiness?

**Nein — und der Code behauptet das Gegenteil.**

`reqogniloom/health.py:4` (Docstring):
> „Implements both `/health/ready` (readiness) and `/health/live` (liveness)
> patterns."

Routing (`reqogniloom/urls.py:28`): **nur** `path("health/", HealthView.as_view())`.
`rg "ready|live"` über `reqogniloom/urls.py` und `rest_api/urls.py` → **0 Treffer**.

**`/health/ready` und `/health/live` existieren nicht.** Der Docstring ist
falsch — und das ist mehr als ein Kosmetik-Problem: die vorgesehene
Differenzierung (Liveness darf nie von einer Abhängigkeit abhängen, Readiness
darf) ist damit **nicht implementierbar**, ohne das Verhalten zu ändern.
Aktuell hängt **alles** an einem Endpoint mit 503-Semantik. → **275**

**Zur Korrektur von `031`/`129`:** Die Teilaussage *„liefert bei `degraded`
HTTP 200"* ist **WIDERLEGT** — `health.py:135` und `:161` setzen
`http_status = 503`; die Unterscheidung `degraded` (503) vs. `warning` (200,
Z. 312-313) ist sauber implementiert und begründet (Z. 176-181: ein
Liveness-Probe soll keinen Stack neustarten, der noch Traffic bedient).
**Die Restbefunde** — kein Cache-, Worker- oder Beat-Check — **bleiben
bestehen** (→ 286).

## C. Metriken

| Frage | Befund |
|---|---|
| Welche Metriken? | **Keine Telemetrie-Metriken existieren.** `rg -i "prometheus\|opentelemetry\|django-prometheus\|statsd"` über die Dependency-Manifeste → **0 Treffer**. Kein `Counter(`/`Histogram(`/`Gauge(`-Instrumentierung im Prod-Code. |
| `/metrics/` authentifiziert? | **JA — aber die Frage läuft ins Leere.** `MetricsViewSet` (`rest_api/metrics_views.py:29-102`) ruft `get_auth_context` und gibt ohne Auth `401 AUTHENTICATION_REQUIRED` (Z. 40-46). Es ist **kein** Prometheus-Scraper-Endpunkt, sondern ein **Domänen-Metrik-Proxy** (`se_metrics.services.compute_metrics`, REQ-L2-SM-001), tenant- und workspace-gebunden. |
| **Korrektur zu WP-6a** | Die Aussage „`/metrics/` unauthentifiziert" ist **relativiert**: der Endpunkt, den WP-6a geprüft hat, ist authentifiziert. Der eigentliche Befund ist der **Wegfall**: es gibt **gar keine** Telemetrie-Metriken. |

### Fehlende kritische Metriken (priorisiert)

| # | Metrik | Warum | Wo sie fehlt |
|---|---|---|---|
| M1 | **Queue-Tiefe pro Queue** (`default`/`llm`/`events`/`memory`) | Ein gestautes `events`-Queue ist der direkte Vorlauf zu „Audit-Log wird nicht mehr geschrieben". Der Heartbeat-Task (`admin_ops.record_celery_beat_heartbeat`) beweist nur, dass Beat *dispatcht*, nicht dass Worker *drainen*. | nirgends |
| M2 | **Outbox-Backlog** (`published=false`, `retry_count ≥ MAX_RETRIES`, DLQ-Zähler) | Genau der Zustand, den `031`/`129` nicht erkennen. Live wäre trivial abfragbar (6872/6872 publiziert, 0 pending, 0 DLQ). | nirgends |
| M3 | **Request-Rate / Fehlerrate / Latenz pro Route** | Ohne das ist Finding `036` (MCP-ValidationError als 500) im Betrieb nicht messbar auffällig. | nirgends |
| M4 | **DB-Verbindungspool** (`CONN_MAX_AGE`, `max_connections`, aktive/wartende Verbindungen) | `pg_stat_activity` hätte es; nichts exponiert es. | nirgends |
| M5 | **Task-Fehlschlag-Rate** | Wird aktiv **verschluckt**: `application/tasks.py:36-38` fängt `Exception` und gibt `0` zurück ⇒ Celery verbucht Erfolg. `dispatch-outbox-events` steht in `django_celery_beat_periodictask` mit **`total_run_count = 222863` und 0 Fehlschlägen**. → **284** |
| M6 | **Transaktions-Wartezeit / Lock-Wait** | `WorkflowItemState` wird bei jedem Transition gesperrt (`lifecycle_manager.py:279`); Deadlocks/Serialisierung sind nicht beobachtbar. | nirgends |

→ **277 (Medium)**

## D. Audit-Log als Observability-Kanal

**Auffindbar:** ja — `/api/v1/admin/health/` listet `_recent_audit_events()`
(`health_rest.py:487`), und es gibt eine filterbare Query-API
(`audit/query.py:112-152`, Filter: `entity_id`, `entity_type`, `actor`,
`operation`, `source`, `timestamp`-Range; Sortierung `-timestamp`; Seite max. 200).

**Auswertbar: eingeschränkt, mit einem gemessenen Defekt.**

```
$ SELECT count(*) AS total,
         count(*) FILTER (WHERE entity_version IS NULL) AS ev_null,
         round(100.0*count(*) FILTER (WHERE entity_version IS NULL)/count(*),1) AS pct
    FROM audit_entry;

 total | ev_null | pct
 ------+---------+------
  8167 |    7979 | 97.7
```

| `op` | n | `entity_version` NULL |
|---|---|---|
| `create` | 5738 | 5627 (98.1 %) |
| `update` | 1277 | 1200 (94.0 %) |
| `delete` | 872 | **872 (100 %)** |
| `transition` | 175 | **175 (100 %)** |
| `user.*` (7 Ops) | 55 | **55 (100 %)** |
| `baseline.create` | 38 | 38 (100 %) |
| **mit `entity_version`** | **188** | — |

`AuditEntry.entity_version` (Spalte belegt, `audit_entry`-Spaltenliste live
verifiziert) wird also faktisch **nie** befüllt. Der Audit-Eintrag sagt
damit: *„irgendjemand hat Requirement X aktualisiert"* — aber **nicht**, *in
welche Revision* die Änderung resultierte. Für einen append-only
Compliance-Trail ist das die entscheidende Zuordnung.

Verschärfend: **`create LlmCall` ist 42× auf `entity_id = 00000000-0000-0000-0000-000000000000`**
gebucht — alle LLM-Aufrufe sind über `entity_id` **nicht unterscheidbar**.
Das ist derselbe Bereich wie das bekannte `169`.

→ **285 (Medium)**
