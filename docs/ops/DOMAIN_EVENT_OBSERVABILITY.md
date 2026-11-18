# SLO — Domain-Event-Observability (Transactional Outbox)

> **Status:** SLI/SLO-Definition **VORGESCHLAGEN** · Signal-Katalog **EXISTIERT** · Instrumentierung **HANDOFF (nicht erledigt)**
> **Owner:** `sre-engineer` (SLI/SLO, Error Budget, Burn-Rate-Policy) · Umsetzung: `developer` (siehe §5)
> **Stand:** 2026-11-18 · Branch `fix/s5-3-ops-maturity` · Basis `f60697d` · Scope: **Docs-only**, keine Code-Änderung
>
> Lesart der Kennzeichnungen: **EXISTIERT** = im Code vorhanden und per Test belegt ·
> **VORGESCHLAGEN** = von diesem Dokument definiert, noch nicht messbar ·
> **HANDOFF** = offene Aufgabe mit Code-Blast-Radius, ausdrücklich **nicht** in diesem Slice erledigt.

## 0. Warum dieses Dokument

Der Domain-Event-Pfad ist betrieblich **teilweise** beobachtbar: es gibt Zähler und Gauges, aber
**keinen** Latenz-SLI, **keine** SLO-Schwelle, **keinen** Owner und **keinen** Export in ein
Metrikensystem. Diese Datei legt die vorhandenen Signale fest (§1), definiert den fehlenden
SLI/SLO samt Error-Budget-Regel (§2) und übergibt die Instrumentierung an `developer` (§5).

**Wichtige Abgrenzung:** `GET /api/v1/metrics/` (und `/api/v1/metrics/catalog/`) liefert
**SE-KPIs** (Traceability-Coverage, Verification-Coverage, Volatility, Workflow-Gaps, Open Risks;
`backend/se_metrics/registry.py:22-23`, `backend/se_metrics/registry.py:148`,
`backend/rest_api/urls.py:341`). Das ist **keine** Infrastruktur-Metrik und darf nicht mit den
Outbox-Signalen verwechselt oder als SLI-Quelle verwendet werden.

## 1. Katalog EXISTIERENDER Signale

Alle Angaben sind per `Read` am Stand `f60697d` verifiziert. Die Advisory-Einträge werden von
`GET /health/ready` ausgeliefert (`backend/reqogniloom/urls.py:39-41`; veralteter Alias
`/health/` ebenda `:42-43`). Sie sind **advisory**: ein nicht-null Backlog/DLQ ändert weder HTTP-Status
noch `status: degraded` (`backend/reqogniloom/health.py:1015-1027`, Test
`backend/reqogniloom/tests/test_health_outbox_gauges_1389.py:73-85`).

| Signal (EXISTIERT) | Messpunkt (Datei:Zeile) | Exposition | Test |
|---|---|---|---|
| `outbox:unbound_publish:count` — Zähler für Publishes außerhalb einer Transaktion (Issue #1438), Decay-Fenster 24 h | `backend/application/event_bus_metrics.py:88` (Key), `:141-164` (Fenster), `:239` (`increment_unbound_publish`), `:262` (`unbound_publish_count`); Fail-open `:204-210` | `GET /health/ready` → `advisory.outbox_unbound_publishes` + `advisory.outbox_unbound_publish_window_seconds` (`backend/reqogniloom/health.py:972-987`; Warntext `:989-1013`) | `backend/application/tests/test_outbox_transaction_binding_1438.py:279` (`TestCounter`), `:427` (`TestHealthAdvisory`), `:514` (`TestCounterWindow`), `:598` (Key-Name) |
| `outbox:queue:backlog` — Gauge, TTL 120 s, **jeden** Poll-Zyklus geschrieben | `backend/application/event_bus_metrics.py:101` (Key), `:111` (TTL), `:308` (`record_queue_depths`), `:350` (`queue_depths`); Schreibaufruf `backend/application/event_bus.py:1331-1335` | `GET /health/ready` → `advisory.outbox_pending` (`backend/reqogniloom/health.py:1028-1038`), `unknown` statt `0` bei abgelaufenem Gauge (`:1036-1037`) | `backend/application/tests/test_event_bus.py:988` (`TestQueueDepthGauges`), `:996`, `:1108` (jeder Zyklus); `backend/reqogniloom/tests/test_health_outbox_gauges_1389.py:61`, `:88` |
| `outbox:queue:dlq` — Gauge, TTL 120 s, gleicher Schreibpfad | `backend/application/event_bus_metrics.py:104`, `:111`, `:308`, `:350`; `backend/application/event_bus.py:1335` | `GET /health/ready` → `advisory.outbox_dlq` (`backend/reqogniloom/health.py:1039-1041`) | `backend/application/tests/test_event_bus.py:988`, `:1002`, `:1011`; `backend/reqogniloom/tests/test_health_outbox_gauges_1389.py:61`, `:73`, `:98` |
| Change-only Poll-Log (Durchsatz/Backlog/DLQ/Orphans) — **kein** SLI, nur Log | `backend/application/event_bus.py:1287-1296`, `:1331-1343`; Orphan-WARNING `:1336-1342` | Log (`INFO` nur bei Änderung, sonst `DEBUG`) | `backend/application/tests/test_event_bus.py:864` (`TestPollObservationLogging`), `:896-974` |
| `memory_consolidations_total` — Konsolidierungszähler des AI-Memory-Loops, fail-open (nicht Outbox, hier zur Vollständigkeit) | `backend/memory/metrics.py:29-34` (Name/Endpoint), `:70` (`increment_consolidation`), `:101` (`consolidation_counts`) | `GET /api/v1/system/memory/workspaces/`-Overview (`backend/memory/metrics.py:32-34`) | — (außerhalb des Outbox-Scopes) |

**Explizite Negativbefunde (verifiziert, nicht überzubesetzen):**

- **Kein Prometheus-/OTEL-Exporter:** `0` Importe von `prometheus_client` / `opentelemetry*` im
  Backend. Die einzigen Treffer sind Kommentare über einen *zukünftigen* Exporter
  (`backend/application/event_bus_metrics.py:74`, `backend/memory/metrics.py:29-30`).
- **Kein Event-Lag-, Claim-Age- oder Retry-Count-SLI.** `retry_count`
  (`backend/application/models.py:189`) und `claimed_at` (`:196`) sind Felder der
  Dispatch-Logik (`backend/application/event_bus.py:840-862`, `:991`), aber **keine** gemessenen,
  ausgewerteten oder alarmierten SLIs.
- **Keine SLO-Schwelle, kein Schwellenwert, kein Owner** für die oben genannten Signale; keine
  Nightly-Reconciliation für den Outbox (Treffer zu „reconcile" betreffen Workflow-StatusMirror
  und Trace-Links, nicht den Event-Pfad).

## 2. VORGESCHLAGENER SLI / SLO

### SLO — Outbox-Dispatch-Latenz

**SLI (nutzerseitig formuliert):** Der Anteil der Domain-Events, die innerhalb von **15 Minuten**
nach ihrer Erzeugung beim Subscriber zugestellt wurden. Ein Nutzer merkt einen verarbeiteten
Requirement-/Testfall-/Baseline-Vorgang nicht direkt an der Outbox — sehr wohl aber daran, dass
abgeleitete Ansichten, Indizes und AI-Memory-Projektionen **nicht** aktualisiert werden. Der SLI
misst genau diese Verzögerung.

- **Messpunkt:** Tabelle `as_domain_event_outbox` (`backend/application/models.py:198-199`).
  Start `created_at` (`:186`), Erfolgszeitpunkt `published_at` (`:187`), gesetzt im Write-back
  `backend/application/event_bus.py:920`
  (`.update(published=True, published_at=timezone.now(), claimed_at=None)`).
- **Berechnung:** Zähler = Zeilen mit `created_at` im 30-Tage-Fenster und
  `published_at ≤ created_at + 15 min`; Nenner = alle Zeilen mit `created_at` im Fenster.
  Bewertung erst zum Zeitpunkt `created_at + 15 min + Puffer`, damit ein nachträglicher Dispatch
  nicht rückwirkend als „pünktlich" gilt. Segmentierung nach `event_type` und `workspace`.
- **Begründung von 15 min (Kapazität, nicht Wunschdenken):** Poll-Zyklus alle 5 s
  (`backend/reqogniloom/settings.py:1274-1278`) = 180 Zyklen pro Intervall; Claim-Timeout 300 s
  (`backend/application/event_bus.py:857`) = 5 min; `MAX_RETRIES = 5` (`:840`),
  `POLL_BATCH_SIZE = 100` (`:841`). 15 min = 3× Claim-Timeout plus Retry-Spielraum; im
  Normalfall liegt die Zustellung bei ~5–10 s.

**SLO:** **99,9 %** über **30 rollierende Tage**. Kein 100-%-Ziel — ohne Error-Budget gäbe es
keine release-steuernde Entscheidungsregel.

**Error Budget:** `0,1 % × 30 d = 0,001 × 43.200 min = 43,2 min` (≈ **43 min / 30 d**).
Nachweis der Rechnung: 30 × 24 × 60 = 43.200 Minuten; 0,1 % davon = 43,2 Minuten.

**Release-Freeze-Regel (objektiv, nicht guideline):** Feature-Releases pausieren zugunsten von
Reliability-Arbeit, sobald das Restbudget unter **20 % (< 8,6 min)** fällt **oder** der
Slow-Burn-Alarm (6×/6 h) länger als 24 h ununterbrochen aktiv ist. Trade-off: ein 99,9-%-Ziel
kauft schnelle Feature-Auslieferung bei gelegentlicher Zustell-Verzögerung; bei Budget-Erschöpfung
wird dieser Trade-off bewusst umgedreht (Reliability vor Features), bis das Budget wieder aufgefüllt
ist. Ein 99,99-%-Ziel (4,3 min) würde bei der 5-s-Poll-Architektur und fehlender externer
Exporter-Latenzmessung zu Fehlalarmen führen und ist daher nicht gewählt.

**Burn-Rate-Alarme:**

| Alarm | Schwelle | Zeitfenster | Budget-Verbrauch im Fenster | Interpretation |
|---|---|---|---|---|
| Fast burn (Page) | **14,4×** | 1 h | 1,44 % × 60 min ≈ 0,86 min | Budget bei anhaltender Rate in ~2,1 Tagen aufgebraucht → sofortige Reaktion |
| Slow burn (Ticket) | **6×** | 6 h | 0,6 % × 360 min ≈ 2,2 min | Budget in ~5 Tagen aufgebraucht → Reliability-Arbeit einplanen |

Beide Alarme setzen den vorgeschlagenen SLI voraus und sind **noch nicht implementiert** (§5).
Ein `unknown`-Gauge (Cache/Poller ausgefallen, `backend/reqogniloom/health.py:1036-1041`) darf
**nicht** als „gesund" gewertet werden.

**Capacity Headroom:**

- Poll 5 s → 17.280 Zyklen/Tag; bei `POLL_BATCH_SIZE = 100` theoretisch 1,73 Mio. Event-Slots/Tag.
- Scaling-Schwelle: `p95(published_at − created_at) > 60 s` **oder** `advisory.outbox_pending > 500`
  über 15 min → Celery-Worker hochskalieren. Sättigungsgrenzen: DB-Verbindungspool,
  Redis-Cache (Gauge-/Counter-TTLs) und bei `RLS_AS_ENFORCED` die Kandidaten-View
  (`backend/application/event_bus.py:1276-1285`).
- Die vorhandenen Gauges (`outbox_pending` / `outbox_dlq`) sind ein **Frühindikator**, ersetzen
  aber keinen Latenz-SLI: ein konstanter Backlog ist im change-only Log unsichtbar
  (`backend/application/event_bus.py:1287-1296`) und genau deshalb nur über den Gauge erkennbar.

**Toil-Kandidaten (manuell, repetitiv, automatisierbar, kein dauerhafter Wert):**

1. ``GET /health/ready``-Advisories und Poll-Log pro Incident manuell lesen und interpretable
   „backlog wächst?"-Aussage formulieren → automatisieren via SLI-Dashboard + Burn-Rate-Alarm.
2. Manuelle DB-Abfrage auf `published=FALSE AND created_at < now() - 15 min` → ersetzen durch
   den vorgeschlagenen SLI und die Nightly-Reconciliation (§5).
3. Cache-Counter bei Fehlalarm manuell zurücksetzen (`reset_unbound_publish_counters`,
   `backend/application/event_bus_metrics.py:293`) → durch das Decay-Fenster (24 h, `:113-115`)
   bereits weitgehend obsolet; nur noch als Teil des Runbooks dokumentieren.

**Reliability-Risiken vor Einführung:**

- **Fail-open der Signale:** Cache-Ausfall führt zu `unknown` bzw. Zähler `0`
  (`backend/application/event_bus_metrics.py:262-275`, `:350-374`; Tests
  `backend/application/tests/test_event_bus.py:1011`, `backend/reqogniloom/tests/test_health_outbox_gauges_1389.py:88`).
  Ein Alert auf `0` würde einen Ausfall als Erfolg melden → `unknown` separat alarmieren.
- **Kein 30-Tage-Messfundament:** ohne Export und ohne Event-Lag-Instrumentierung ist der
  vorgeschlagene SLI aktuell **nicht berechenbar**; das SLO ist daher `VORGESCHLAGEN`, nicht aktiv.
- **Orphan-Rows** ohne `tenant_id` werden bei `RLS_AS_ENFORCED` fail-closed übersprungen
  (`backend/application/event_bus.py:1304-1318`, `:1336-1342`). Sie zählen in den SLI-Nenner,
  können aber nie „pünktlich" werden → eigene Segmentierung vorsehen.
- **Transaktionsbindung:** unbound publishes (`outbox_unbound_publish_count`, §1) gefährden die
  Atomarität, nicht die Zustellung; sie sind ein eigenes Risiko und **nicht** Teil dieses SLI.

## 3. Selbstverifikation (Pflichtschritt)

1. **SLI gegen reale Messdaten geprüft — eingeschränkt:** Die *vorhandenen* Signale sind gegen
   ihre Tests verifiziert (§1, Spalte „Test"; Tests nicht erneut ausgeführt, da Docs-only und
   DB-Tests nicht im Scope). Die *vorgeschlagene* 15-min-Latenz ist **bewusst nicht validiert** —
   es existiert kein Messpunkt, der `published_at` als Verteilung über 30 Tage erhebt. Diese Lücke
   ist der Gegenstand des Handoffs (§5) und wird hier nicht als Erfolg ausgegeben.
2. **Error-Budget nachgerechnet:** 30 d × 24 h × 60 min = 43.200 min; 0,1 % = **43,2 min**;
   20 %-Freeze-Schwelle = 8,64 min. Burn-Rate 14,4×/1 h → 0,864 min; 6×/6 h → 2,16 min.
3. **Reproduzierbarkeit:** Die zitierten Tests sind deterministisch (LocMem-Cache, gemockte
   Pflicht-Probes, `pytest.mark.django_db`), vgl.
   `backend/reqogniloom/tests/test_health_outbox_gauges_1389.py:29-58`. Ein neues Runbook wird in
   diesem Slice **nicht** angelegt (kein neuer Fehlerzustand eingeführt); die Eskalation läuft über
   `incident-responder`, sobald der SLI aktiv ist.

## 4. Pre-Deployment-Review (Reliability Review)

| Frage | Antwort |
|---|---|
| Existiert ein SLI/SLO für die Journey? | **Nein** — hier erst vorgeschlagen (§2) |
| Reicht das Error-Budget für ein Release? | **Nicht bewertbar** — kein 30-Tage-Baseline-Messwert vorhanden |
| Rollback-Pfad / Runbook für den neuen Zustand? | **n/a** — dieser Slice ändert keinen Code |
| Alarmierung auf den relevanten SLIs? | **Nein** — Burn-Rate-Alarme sind Handoff (§5) |

## 5. HANDOFF — offene Developer-Aufgaben (in diesem Slice NICHT erledigt)

Owner: **`developer`** (Instrumentierung; Code-Blast-Radius: `backend/application/event_bus.py`,
`backend/application/event_bus_metrics.py`, `backend/reqogniloom/health.py`,
`backend/reqogniloom/settings.py` sowie zugehörige Tests). `sre-engineer` bleibt Owner der
SLI/SLO-Definition und validiert die Basis nach Messbeginn.

1. **Event-Lag-Instrumentierung im Poll-Pfad:** im Write-back (`backend/application/event_bus.py:920`)
   und/oder im Poll-Zyklus (`:1253-1345`) `published_at − created_at` als Histogramm/Gauge
   erfassen (Namensvorschlag `outbox_event_lag_seconds`), fail-open im Stil von
   `event_bus_metrics.py` und mit denselben Segmenten (event_type, workspace).
2. **Claim-Age- und Retry-Count-SLI:** `claimed_at` (`backend/application/models.py:196`) und
   `retry_count` (`:189`) als Gauges auslesen (`outbox_claim_age_seconds`, `outbox_retry_count`),
   inklusive `CLAIM_TIMEOUT_SECONDS`/`MAX_RETRIES`-Grenzen (`backend/application/event_bus.py:840-857`).
3. **Nightly-Reconciliation:** periodischer Celery-Task, der `published=FALSE`-Zeilen älter als
   15 min gegen den Dispatch-Output abgleicht und die Zahl als Counter/Advisory ausgibt (Orphan-
   Rows separat). Derzeit existiert **kein** solcher Task.
4. **Optionaler Exporter:** Prometheus- oder OTEL-Exporter (aktuell 0 Imports); vorhandene Namen
   `outbox_unbound_publish_count` / `memory_consolidations_total` ohne Rename übernehmen, neuen
   SLI-Namen ergänzen. Nur mit `devops-engineer` abstimmen.
5. **Burn-Rate-Alarme und 30-Tage-Baseline:** Fast 14,4×/1 h und Slow 6×/6 h als Alertregeln
   umsetzen; nach 30 Tagen Messdaten das SLO von `VORGESCHLAGEN` auf `AKTIV` heben und die
   15-min-Schwelle anhand der Verteilung nachjustieren.

**Nicht in diesem Slice:** keine Code-Änderung, keine neue Dependency, kein Exporter, keine Alert-
Regel, kein Runbook, kein Commit/Push. Diese Datei ist der einzige geänderte Pfad.
