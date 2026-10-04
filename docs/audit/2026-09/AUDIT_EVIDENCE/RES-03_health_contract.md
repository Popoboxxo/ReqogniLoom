---
type: EVIDENCE
scope: RES-03-health-contract-adr-010
status: final
date: 2026-10-02
author_agent: senior-developer
branch: fix/health-contract-live-ready
---

# RES-03 — Health-Vertrag (ADR-010): Umsetzung und Live-Nachweis

## Adressierte Findings

| Finding | Bezug | Status |
|---|---|---|
| AUD-2026-09-031 (Critical) | `/health/` war false-green (200 trotz unbenutzbarer App) | behoben: Alias auf fail-closed `/health/ready` |
| AUD-2026-09-275 | Docstring versprach `/health/live` + `/health/ready`, beide fehlten | behoben: beide Endpunkte implementiert |
| AUD-2026-09-286 | Cache/Redis, Celery-Worker und Beat wurden nie geprüft | behoben: alle fünf Pflicht-Checks in `/health/ready` |
| AUD-2026-09-121(a) | Beat-Healthcheck prüfte nur Prozessexistenz (`pgrep`) | funktionaler Check implementiert; Compose-Verdrahtung wegen Memory-Blocker zurückgestellt (siehe unten) |

## Verhalten je Endpunkt

- `GET /health/live` — immer `200 {"status":"ok","checks":{}}`, keine Abhängigkeitsprobe (restart-sicher, ADR-010 §1).
- `GET /health/ready` — `200` nur wenn alle Pflicht-Checks (`database`, `memory_backend`, `cache`, `celery_worker`, `celery_beat`) `ok`; sonst `503` `status:"degraded"` mit `dependencies` (`{name,status,detail:"dependency_down"}`). Beratende Signale ausschließlich in `warnings`/`advisory`, nie in `checks`/`dependencies`; leerer `warnings` ⇒ `ok`, nicht-leer ⇒ `warning` (200).
- `GET /health/` — Deprecation-Alias auf `/health/ready` inkl. `Deprecation: true` und `Sunset`-Header.
- `HEALTH_STRICT_READINESS` (Default `true`; nur explizites `false` ⇒ degraded-200).
- Wiederverwendung der admin_ops-Probes; `redis`-Zeile auf Kontraktnamen `cache` gemappt. `GET /api/v1/admin/health/` unverändert.

## Tests (echte Zahlen)

Gezielte Läufe im Test-Overlay (nicht die volle Suite):

- `reqogniloom/tests/test_health.py`, `test_health_contract_adr010.py`, `admin_ops/tests/test_check_celery_beat_command.py`, `reqogniloom/tests/test_security_headers.py` → **53 passed**, 0 failed.
- `admin_ops/tests/test_health_rest.py`, `test_error_envelope_single_form_1081.py`, `rest_api/tests/test_api_consistency_460.py`, `tests/test_wiring.py` → **146 passed**, 0 failed.

## Live-Nachweis (Stack mit Host-Port 8001)

Ausgangszustand: `/health/live` = 200, `/health/ready` = 200 (alle Pflicht-Checks ok).

Redis-Container gestoppt (`docker stop ai-native-reqflow-poc-redis-1`), danach gemessen:

- `GET /health/live` → **200** `{"status":"ok","checks":{}}`
- `GET /health/ready` → **503** `status:"degraded"`, `dependencies` = `cache` (down), `celery_worker` (down), `celery_beat` (unknown) — `detail` ausschließlich `"dependency_down"`, kein DSN/Host/Secret.
- `GET /health/` → **503** mit `Deprecation: true` und `Sunset: Thu, 01 Apr 2027 00:00:00 GMT`.
- Compose-Health des Backends: `healthy` → **`unhealthy`** (gemessen).

Redis wieder gestartet (`docker start ...`), danach: `/health/ready` → **200** `status:"ok"`, Compose-Health Backend → **`healthy`**.

## Blocker: funktionaler Beat-Healthcheck in Compose

Der funktionale Check ist implementiert und getestet (`python manage.py check_celery_beat`, liest die Heartbeat-Freshness aus `admin_ops.celery_beat_heartbeat`). Live funktioniert er (im Backend-Container: exit 0, „heartbeat 18.4s old").

Die Verdrahtung als **Compose-Healthcheck des `celery-beat`-Containers** wurde bewusst zurückgestellt: Der Beat-Container läuft live bei **255.5 MiB / 256 MiB (99.79 %)**. Ein gestartetes `manage.py` wird dort OOM-gekillt (verifiziert: `exit 137`, `OOMKilled=true`; der Probe-Versuch startete den Container neu, `RestartCount` 1→2). Als Healthcheck alle 30 s verdrahtet würde er einen gesunden Beat in einen Restart-Loop zwingen — ein False-Red, genau das von RES-05 adressierte Problem.

**Vorschlag (minimale Heartbeat-Mechanik, RES-05):** Beat-Memory-Limit von 256M auf den für Worker bereits bewährten Wert (384M, mit `CELERY_CONCURRENCY`-Kopplung) anheben, dann
`test: ["CMD-SHELL", "python manage.py check_celery_beat"]` mit `start_period: 90s` verdrahten. Der Command und seine Tests liegen bereits vor.
