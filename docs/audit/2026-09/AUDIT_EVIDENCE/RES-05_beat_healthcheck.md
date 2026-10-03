---
type: EVIDENCE
scope: RES-05-beat-healthcheck-memory
status: final
date: 2026-10-02
author_agent: devops-engineer
branch: fix/health-contract-live-ready
---

# RES-05 — Funktionsbasierter celery-beat-Healthcheck + Beat-Memory-Limit

## Adressierte Findings

| Finding | Bezug | Status |
|---|---|---|
| AUD-2026-09-121(a) / N4 | Compose-Healthcheck `pgrep -f 'celery.*beat'` prüfte **nur Prozessexistenz** — ein hängender, aber laufender Beat blieb `healthy` | behoben: funktionaler Probe `python manage.py check_celery_beat` ersetzt `pgrep` |
| RES-03-Blocker (Deferral `47cd4837`) | Beat lief bei 255,5/256 MiB (99,79 %), jeder zusätzliche Probe-Prozess wurde OOM-gekillt (exit 137) | behoben durch Limit-Anhebung **und** speicherschonenden Probe-Aufruf |

## 1. Gemessener Speicherbedarf (live, Stack auf Host-Port 8001)

Messbefehle (im Beat-Container bzw. via Docker):

```
docker stats --no-stream --format "{{.Name}} {{.MemUsage}} {{.MemPerc}}" ai-native-reqflow-poc-celery-beat-1
docker exec ai-native-reqflow-poc-celery-beat-1 cat /sys/fs/cgroup/memory.current
docker exec ai-native-reqflow-poc-celery-beat-1 cat /sys/fs/cgroup/memory.peak
docker exec ai-native-reqflow-poc-celery-beat-1 awk '/^anon /{print $2}' /sys/fs/cgroup/memory.stat
docker exec ai-native-reqflow-poc-celery-beat-1 ps -o pid,ppid,rss,args -e
```

| Zustand | `memory.current` | `anon` (nicht rückforderbar) | Anmerkung |
|---|---|---|---|
| Alt-Limit 256M, steady state (11 h Uptime) | 263,7 MB (251,6 MiB) | — | `memory.peak == memory.max` = 268 435 456 → Beat klebte am Limit |
| Neues Limit 768M, Beat steady state | 625–716 MiB | **407 MiB** | Modell-Preload in Beat; Rest ist rückforderbarer Page-Cache |
| Probe läuft (3–5 Läufe, Limit 768M) | max. 533,9 MB | **536 MiB** kombiniert | +94…+129 MiB transient, nach Prozessende vollständig freigegeben |

**Gesuchter Wert (Basis für das Limit): kombiniertes `anon`-Peak = 536 MiB.**
`memory.peak` erreicht das Limit (768 MiB), weil der Kernel freien Platz mit
*rückforderbarem* Page-Cache füllt — `anon` (536 MiB) bleibt deutlich darunter,
also **kein OOM-Risiko**. Verifiziert: 5 aufeinanderfolgende Probe-Läufe,
`RestartCount=0`, `OOMKilled=false`, `anon` fällt nach jedem Lauf auf den
Baseline zurück (keine Akkumulation).

**Gewähltes Limit: `768M` = ca. 1,43 × 536 MiB ⇒ > 200 MiB (≈ 43 %) Headroom.**
Deckt zusätzlich Beat-eigene Scheduler-Schwankungen ab und entspricht dem
Dev-`celery`-Limit in `docker-compose.override.yml`.

## 2. Root Cause des OOM: Embedding-Preload im Probe-Prozess

`LlmAdapterConfig.ready()` (`backend/llm_adapter/apps.py`) lädt bei **jedem**
Django-Start das SentenceTransformer-Modell vor — auch für
`manage.py check_celery_beat`, obwohl der Command nur einen Cache-Key liest und
nie embeddet. Gemessen vor dem Fix: Probe-Peak **743 MiB** und ~140 MiB
*retained* nach Prozessende. Das killte den Probe-Prozess unter dem alten
256M-Limit (exit 137).

Fix: `check_celery_beat` in die bereits vorhandene Menge
`_PRELOAD_SKIP_COMMANDS` aufgenommen (dieselbe Mechanik wie `migrate`/`check`).
Danach: Probe-Peak 536 MiB `anon` kombiniert, volle Freigabe nach Ende.
Der Command selbst braucht keine Änderung — nur der Preload-Pfad wird für diesen
einen Command übersprungen.

## 3. Compose-Verdrahtung (`deploy/docker-compose.yml`, Service `celery-beat`)

| Feld | Alt | Neu | Begründung |
|---|---|---|---|
| `deploy.resources.limits.memory` | `256M` | `768M` | s. Messung: kombiniertes `anon`-Peak 536 MiB |
| `healthcheck.test` | `pgrep -f 'celery.*beat' …` | `python manage.py check_celery_beat` | Prüft Dispatch-Frische (Heartbeat), nicht Prozessexistenz |
| `interval` | `30s` | `30s` | unverändert |
| `timeout` | `10s` | `15s` | Probe-Boot dauert gemessen ~4,3 s; Reserve |
| `retries` | `3` | `3` | 3 Fehlschläge vor `unhealthy` (Transient-Toleranz) |
| `start_period` | `40s` | `120s` | Beat-Boot + erster Heartbeat (60s-Takt) mit Reserve |

Der funktionale Probe ist exit-0 nur bei frischem Heartbeat; der Heartbeat wird
vom beat-geplanten Task `admin_ops.record_celery_beat_heartbeat` (60 s-Takt)
geschrieben und geht nach `HEARTBEAT_STALE_AFTER_SECONDS = 180` s als „stale"
über.

## 4. Live-Nachweis — Normalbetrieb (`healthy`)

Nach `docker compose up -d celery-beat` mit funktionalem Healthcheck:

- `docker ps`: `ai-native-reqflow-poc-celery-beat-1 Up (healthy)`, mehr als 11 min durchgehend.
- `docker inspect`: `RestartCount=0`, `OOMKilled=false`, `Health.Status=healthy`, `FailingStreak=0`.
- Probe manuell mehrfach: `celery beat heartbeat ok (3,9s / 8,1s old, interval 60s)`, rc = 0.
- Healthcheck-Log nach Dauerbetrieb: nur `exit=0`-Einträge.

## 5. Live-Nachweis — Störfall (`unhealthy`)

Vorgehen: Beat-Prozess einfrieren, damit er nicht mehr dispatcht, aber der
Container weiterläuft („hung beat"-Szenario):

```
docker exec ai-native-reqflow-poc-celery-beat-1 pgrep -f "reqogniloom beat"   # → PID 7 (celery)
docker exec ai-native-reqflow-poc-celery-beat-1 kill -STOP 7
```

Danach Health-Status beobachtet (Probe alle 30 s):

| Zeit nach SIGSTOP | Status | FailingStreak |
|---|---|---|
| 0–165 s | `healthy` | 0 (Heartbeat noch frisch) |
| 180 s | `healthy` | 1 (Heartbeat stale, 1. Fehlschlag) |
| 225 s | `healthy` | 2 |
| **255 s** | **`unhealthy`** | **3** |

Fehlerbeleg aus dem Healthcheck-Log (`docker inspect … .State.Health.Log`):

```
exit=1  CommandError: celery beat heartbeat is stale: last dispatched 271.1s ago (threshold 180s)
```

Recovery: `kill -CONT 7` → nächster Probe-Lauf `exit=0`
(`heartbeat ok (8.1s old)`), Health-Status innerhalb eines Intervalls wieder
`healthy`, `FailingStreak=0`, `RestartCount=0`, `OOMKilled=false`.

`kill -STOP` auf die Beat-PID simulierte den Ausfall ohne Container-Neustart,
also genau den Fall, den der alte `pgrep`-Check fälschlich als `healthy`
meldete. `kill -CONT` ist nicht destruktiv; die finale Container-Config ist
unverändert (kein manueller `docker update`-Rest).

## 6. Regressionstests (echte Zahlen, Test-Overlay)

```
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml \
  --project-directory . run --rm backend-test pytest -q <files>
```

| Testdatei | Ergebnis |
|---|---|
| `admin_ops/tests/test_check_celery_beat_command.py` (inkl. neuem Preload-Skip-Test) | **5 passed** |
| `admin_ops/tests/test_celery_beat_heartbeat.py` | **9 passed** |
| `admin_ops/tests/test_health_rest.py` | **21 passed** |
| `tests/test_wiring.py` | **11 passed** |
| **Summe** | **46 passed, 0 failed** |

Abgedeckter Vertrag: frischer Heartbeat → exit 0; fehlender (`no celery beat
heartbeat recorded yet`) und stale (`stale … threshold 180s`) Heartbeat →
`CommandError` (exit ≠ 0); unlesbarer Cache → Fehler ohne DSN-Leak; neuer Test
sichert, dass `check_celery_beat` den Embedding-Preload überspringt.

## Geänderte Dateien

- `backend/llm_adapter/apps.py` — `check_celery_beat` in `_PRELOAD_SKIP_COMMANDS`.
- `backend/admin_ops/tests/test_check_celery_beat_command.py` — Regressions-Test für den Skip.
- `deploy/docker-compose.yml` — Beat-Limit `256M → 768M`, Healthcheck `pgrep → check_celery_beat`, Timings.
- `docs/audit/2026-09/AUDIT_EVIDENCE/RES-05_beat_healthcheck.md` — dieses Dokument.

## Ergebnis

`AUD-2026-09-121(a)` / N4 geschlossen: Der `celery-beat`-Compose-Healthcheck ist
funktionsbasiert (Dispatch-Frische statt Prozessexistenz), der Probe ist
speicherschonend und das Beat-Limit ist anhand einer Live-Messung mit Headroom
gesetzt. Normalbetrieb `healthy`, hängender Beat `unhealthy`, Recovery
verifiziert.
