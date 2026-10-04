---
type: PLAN
scope: audit-review-2026-09-resilience-health
status: final
date: 2026-10-01
author_agent: planner
epic: RES — Resilience & Health
branch: chore/audit-review-2026-09
parent: IMPLEMENTATION_PLAN.md
---

# Epic RES — Resilience & Health

> Detailplan. Redis-Abhängigkeit ist der kritische Pfad (live bestätigt: 030/031/221).
>
> **Health-Vertrag (`plan/INTERFACE_CONTRACTS.md` §3/§7.1, api-specialist).** Sollmodell
> `/health/live` (immer 200) + `/health/ready` (fail-closed, 503) + `/health/`-Alias,
> Empfehlung **Option C (ADR i) kombiniert mit fail-closed Readiness**. **ADR i blockiert**
> diese Endpunkt-Topologie und fail-closed vs. degraded-200 → hier nur
> **Vertragsvorschlag**, kein Sofort-Fix; RES-05/RES-07 hängen daran. Das widerlegte
> Finding `129` („`degraded` → 200") ist **nicht** Fixgegenstand.
>
> **Aufwand.** Verbindliche PT-Spannen: `plan/EFFORT_ESTIMATES.md` §1; die Angaben
> `Aufwand: S/M/L` in dieser Datei sind nur Groborientierung.

## RES-01 — Redis-/Cache-Timeouts fail-safe (P0, W1)

- **Findings:** 030
- **Abgrenzung `N3`:** Die Connect/DNS-Präzisierung aus `REVIEW_LIVE_CRITICALS.md` §6
  (dort als „N3“ indexiert) ist **Teil von `030`** — kein eigenes Finding. Das Kürzel
  `N3` ist in dieser Planung eindeutig der **Outbox-Idempotenz-Lücke** vorbehalten und
  gehört ausschließlich zu `DATA-09` (`plan/DATA_RECOVERY.md`), **nicht** zu RES-01.
- **Ort:** `reqogniloom/settings.py:879-884` (`CACHES` ohne `OPTIONS`/`SOCKET_TIMEOUT`);
  `rest_api/throttling.py:164-176` (fail-open fängt nur `Exception`, nicht blockierenden Socket)
- **Zielverhalten:** `socket_connect_timeout` + `socket_timeout` sind explizit gesetzt;
  der Rate-Limit-Pfad fällt bei Connect-/Read-Blockade **innerhalb** des Timeouts in den
  dokumentierten fail-open-Zweig statt zu hängen.
- **Akzeptanz:** Bei gestopptem Redis antwortet ein MCP-Request innerhalb des konfigurierten
  Timeouts (kein 8-s-Hang, kein `exit 28`); Test prüft, dass `OPTIONS` beide Timeouts setzt.
- **Test:** pytest (Settings-Vertrag) + Live-Nachtest (Redis-Stop, bounded `curl --max-time`).
- **Aufwand:** S · **Risiko/Rollback:** zu kurze Timeouts ⇒ falsche fail-open-Auslösung →
  konservativer Default, per Env überschreibbar. · **Deps:** — · **ADR:** —

## RES-02 — Rate-Limit nach AuthN + Bucket-Amplifikation (P0, W1)

- **Findings:** 221, N6
- **Ort:** `mcp_server/views.py:272` (vor `:307` AuthN); `mcp_server/throttling.py:164`
  (`McpApiKeyRateThrottle(credential or "")`); `:132-136` (`McpIpRateThrottle` keyt jeden Request)
- **Zielverhalten:** AuthN **vor** dem Rate-Limit; ungültige/leere Credentials erzeugen
  keinen Per-Key-Bucket (nur IP-Backstop); kein unbegrenztes Cache-Key-Wachstum gegen
  `maxmemory 256mb`/`noeviction`.
- **Akzeptanz:** 401-Requests füllen **keinen** neuen `throttle_mcp_key_*`-Bucket; Live-Verifikation
  via `redis-cli --scan` vor/nach 5 ungültigen Requests.
- **Test:** pytest (Reihenfolge AuthN→Throttle) + Live-Nachtest (Bucket-Zählung).
- **Aufwand:** M · **Risiko/Rollback:** Reihenfolgeänderung kann legitime Limitierung
  verschieben → IP-Backstop bleibt aktiv. · **Deps:** RES-01 · **ADR:** —

## RES-03 — ADR + Health-Vertrag (P0, W1)

- **Findings:** 031, 129 (nur Rest-Kern), 139, 275, 286, 205; (auch 121(a))
- **Nicht eingeplant:** Die widerlegte Formulierung „`degraded` liefert HTTP 200" aus
  `129` ist **nicht** Fixgegenstand — der Code setzt bei `degraded` bereits 503
  (`health.py:134-135,160-161`). Genutzt wird ausschließlich der verbleibende Kern
  (fehlende Cache-/Worker-/Beat-Probe).
- **Ort:** `reqogniloom/health.py:118-315` (0 Cache-Treffer; `:134-135,160-161` degraded⇒503;
  `:312-315` warning⇒200; Docstring `:4` verspricht `/health/ready`+`/health/live`, die nicht existieren);
  `admin_ops/health_rest.py:96-198` (vollständige Probe, aber RBAC-geschützt);
  `deploy/docker-compose.yml:642` (`curl -f /health/`)
- **Zielverhalten (ADR-blockiert = Vertragsvorschlag `INTERFACE_CONTRACTS.md` §3/§7.1; nicht
  umsetzbar bis ADR i):** **ADR (i) entscheidet** fail-closed vs. degraded. Danach:
  `/health/live` (Prozess) und `/health/ready` (DB, Cache/Redis, Celery-Worker, Beat,
  Outbox) getrennt; Compose/CI-Gates werten Readiness aus; keine falsch-grüne Probe.
- **Akzeptanz:** Bei Redis-Stop liefert `/health/ready` **503** mit gelisteter ausgefallener
  Abhängigkeit; `/health/live` bleibt 200; Compose-Health des Backends wird rot.
- **Test:** pytest (Health-View je Abhängigkeit) + Live-Nachtest Redis-Stop.
- **Aufwand:** M–L · **Risiko/Rollback:** zu strikte Readiness nimmt Oberfläche aus dem LB →
  ADR-Entscheidung + Feature-Flag. · **Deps:** ADR i · **ADR:** schreibt (i)

## RES-04 — Celery-Queue-Topologie + acks_late (P1, W2)

- **Findings:** 120, 126, 132, 133, 056
- **Ort:** `reqogniloom/celery.py:31-37` (4 Queues, leere exchange/routing_key);
  Live `_kombu.binding.default` = 4 Members; `settings.py:777-951` (0 acks_late-Einstellungen)
- **Zielverhalten:** **ADR (iv) entscheidet** Routing (echt / eine Queue / Prioritätsklassen);
  ungeroutete Task wird **genau einmal** zugestellt; `task_acks_late` gemäß Entscheidung.
- **Akzeptanz:** `_kombu.binding.*` zeigt je Queue eigenen Routing-Key (bei Option A/C) bzw.
  genau eine Queue (Option B); Task-Zustellung live = 1× pro Dispatch.
- **Test:** pytest (app.conf-Vertrag) + Live-Isolation (`_kombu.binding`, Test-Task zählen).
- **Aufwand:** M · **Risiko/Rollback:** still falsch geroutete Tasks → Routing-Wächter-Test,
  revert per Branch. · **Deps:** ADR iv · **ADR:** iv

## RES-05 — Beat-Healthcheck funktionsbasiert + Memory (P1, W2)

- **Findings:** 121(a), N4
- **Ort:** `deploy/docker-compose.yml:933` (`pgrep -f 'celery.*beat'`); Live 249/256 MiB (97 %)
- **Zielverhalten:** Healthcheck prüft Dispatch-Age (letzter `Sending due task`/Heartbeat),
  nicht nur Prozessexistenz; Beat-Memory-Limit und Modell-Last werden angepasst/beobachtet.
- **Akzeptanz:** Ein „hängender" Beat (kein Dispatch) macht den Container unhealthy;
  Beat läuft nicht mehr bei 97 % Memory.
- **Test:** Compose-Health-Szenario + Live-Age-Messung.
- **Aufwand:** S–M · **Risiko/Rollback:** Fehlalarm bei ruhigem Schedule → Schwellwert
  großzügig; revert. · **Deps:** RES-03 (ADR i, Heartbeat-Auswertung) · **ADR:** i

## RES-06 — `audit.archive_lifecycle_manager` registrieren (P1, W2)

- **Findings:** 125, 270
- **Ort:** `backend/audit/archive.py:448` (`@shared_task`), `backend/audit/apps.py:36`,
  `reqogniloom/celery.py:45` (`autodiscover_tasks()`), kein `audit/tasks.py`;
  Live `celery inspect registered` = 6 Tasks
- **Zielverhalten:** Task wird im Worker registriert (z. B. `audit/tasks.py` mit Import
  oder `CELERY_IMPORTS`), monatliche Audit-Retention läuft tatsächlich.
- **Akzeptanz:** `celery inspect registered` enthält den Task; ein Testdispatch führt die
  Retention aus (oder ein Task-Registrierungstest).
- **Test:** pytest + Live `celery inspect registered`.
- **Aufwand:** S · **Risiko/Rollback:** Retention könnte Daten löschen → Trockenlauf/Test-Workspace,
  reversibel. · **Deps:** RES-04 (ADR iv für Topologie) · **ADR:** iv (teil)

## RES-07 — Observability: Log-Level, request_id, Metrics (P2, W3)

- **Findings:** 274, 276, 278, 077, 277, 141
- **Ort:** `mcp_server/tool_registry.py:1382,1412,1520` (`logger.debug`); `settings.py:899-953`
  (hart INFO, kein `LOG_LEVEL`); `rest_api/serializers.py:241-257` (kein `request_id` im Body,
  Header existiert `middleware.py:85`); 0 Prometheus/OTel
- **Zielverhalten:** fail-closed-Sites loggen ≥ WARNING; `LOG_LEVEL`-Env; `request_id` in
  Fehlerbody; Telemetrie-Exporter.
- **Akzeptanz:** DB-Ausfall erzeugt Logzeile; `LOG_LEVEL=DEBUG` wirkt; Fehlerbody enthält
  `request_id`. · **Test:** pytest/Log-Capture + HTTP-Smoke. · **Aufwand:** M ·
  **Risiko/Rollback:** Log-Rauschen → Level-Default; revert. · **Deps:** RES-03 · **ADR:** —

## RES-08 — Audit-Query-Offset + `n_live_tup`-Evidenz (P2, W3)

- **Findings:** 287, 288
- **Ort:** `audit/query.py:146-148` (`count()`+Offset); `pg_stat_user_tables` (`n_live_tup=0`)
- **Zielverhalten:** Deep-Offset vermeiden (Keyset-Pagination); Evidenz nicht auf
  `n_live_tup` vor `ANALYZE` stützen.
- **Akzeptanz:** `EXPLAIN` ohne wachsenden Offset-Scan; Doku nennt `count(*)` als Evidenz.
- **Test:** pytest/DB-`EXPLAIN`. · **Aufwand:** S · **Risiko/Rollback:** API-Pagination-Änderung
  → additiv. · **Deps:** — · **ADR:** —
