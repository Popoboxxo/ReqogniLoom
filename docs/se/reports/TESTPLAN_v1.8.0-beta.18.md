# Testplan v1.8.0-beta.18

> **Geltungsbereich: interner Pre-Release.** Dieser Testplan prüft den
> Schnitt, nicht die Produktionsreife. Zwei Punkte sind hier ausdrücklich als
> **nicht in diesem Cut verifiziert** geführt und dürfen nicht als bestanden
> gewertet werden: (1) es gibt **keinen neuen Suite-Lauf dieses Cuts** — die
> Zahlen stammen aus dem W4-Abschluss auf `main`; (2) #1135/#1136
> (`decision pending`) und #1138 (`requirements`) sind offen (siehe 6.5).
>
> **Checkbox-Disziplin.** Angekreuzt wird nur, was real verifiziert ist
> (W4-Evidenz bzw. CI). Alles, was in diesem Cut **nicht** gelaufen ist, ist
> explizit als „nicht in diesem Cut verifiziert — Evidenz aus W4-Abschluss auf
> `main`" markiert und **nicht** angekreuzt.

## 1. Ziel & Prüfgegenstand

Geprüft wird das Delta `1.8.0-beta.17` → `1.8.0-beta.18`, also die
Audit-Wellen W1–W4 (PR #1134, #1137, #1139, #1140) samt der `accepted` ADRs
`ADR-010` … `ADR-018`.

### 1.1 Im Scope

- **W1 (PR #1134; ADR-010..014):** Health-Vertrag, Autorisierungsachse
  Workspace/Tenant, Backup-Wahrheit, Collection-Route-Autorisierung,
  Import-Erfolgssemantik/-Idempotenz
- **W2 (PR #1137; ADR-015):** P1-Kernwelle, Celery-Queue-Topologie
- **W3 (PR #1139; ADR-016..018):** Preset-SSOT/`refines`, Plugin-/Server-
  Versions-SSOT, i18n-Vertrag
- **W4 (PR #1140):** Abschlussnachweis (Vollsuite, Live-Nachtest der Kriticals,
  Restore-Smoke, Secret-Scan, ADR-Status, DoD)

### 1.2 Nicht im Scope

- Produktions-, Staging- oder QA-Reife
- #1135 (Admin-Login-Brute-Force/Lockout) und #1136 (RLS-Coverage-Ausweitung)
  — `decision pending`
- #1138 (Traceability-Anker Plugin-Versionierung) — `requirements`-Entscheidung
- Migration von Altinstanzen
- Ein neuer Testlauf dieses Cuts (siehe 2.4)

## 2. Vorbedingungen (exakt)

### 2.1 Source-Checkout, kein Image

Es existiert (Stand dieses Berichts) **kein veröffentlichtes Image
`1.8.0-beta.18`**. Der Stack wird aus dem Source-Checkout dieses Branches
gestartet:

```
# Source-Checkout-Pfad - zwingend, da kein Image 1.8.0-beta.18 existiert
make up
```

### 2.2 Health-Check

```
# /health/live = Liveness, /health/ready = Readiness (fail-closed).
# /health/ ist ein deprecated Alias und spiegelt /health/ready.
curl http://127.0.0.1:8001/health/live
curl http://127.0.0.1:8001/health/ready
```

Erwartet: `/health/live` = HTTP 200; `/health/ready` = HTTP 200 im gesunden
Zustand. Redis/Celery werden für die Ausfalltests gemäß 3.1–3.3 gezielt gestoppt
und **zwingend wieder gestartet**.

### 2.3 Seed

```
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml \
  exec -T backend python manage.py seed_demo
```

### 2.4 Ein frischer Suite-Lauf dieses Cuts fehlt

Dieser Cut ändert — außer Version-Carriern und Doku — **keinen Code**. Es wurde
**kein** neuer Backend-/Frontend-/E2E-Suite-Lauf gegen
`release/v1.8.0-beta.18` gefahren. Alle in Abschnitt 4 genannten Zahlen sind der
**W4-Abschluss auf `main` (`1e5d7574`)** und damit Evidenz für die *inhaltlichen*
Wellen, nicht für einen erneuten Lauf dieses Cuts.

## 3. Schwerpunkttests — Hardening-Themen seit `beta.17`

Legende: **[x]** = in diesem Cut bzw. in der W4-Evidenz/CI real verifiziert ·
**[ ]** = nicht in diesem Cut verifiziert (Evidenz aus W4-Abschluss auf `main`).

### 3.1 Health-Vertrag (ADR-010)

| # | Schritt | Erwartung | Status |
|---|---|---|---|
| 1 | `/health/ready` bei gesundem Stack | HTTP 200, alle Pflicht-Checks `ok` | [x] W4 live |
| 2 | Redis stoppen, dann `/health/ready` | **HTTP 503**, `cache: down` (fail-closed) | [x] W4 live |
| 3 | Redis gestoppt, dann `/health/live` | HTTP 200 (Liveness unbeeinträchtigt) | [x] W4 live |
| 4 | `/health/` (Alias) bei Redis down | HTTP 503 + `Deprecation`/`Sunset: 01 Apr 2027` | [x] W4 live |
| 5 | Redis wieder starten, `/health/ready` erneut | HTTP 200, `cache: ok` | [x] W4 live |
| 6 | Readiness-Latenz im Ausfall messen | ~9,2 s → **O1, nicht blockierend** (8.4) | [x] gemessen (O1) |

### 3.2 Workspace-/Tenant-Fence (ADR-011/013)

| # | Schritt | Erwartung | Status |
|---|---|---|---|
| 1 | Request gegen Workspace eines anderen Tenants | **403** mit JSON-Envelope, **kein** 500, **kein** HTML | [ ] nicht in diesem Cut verifiziert — Evidenz aus W4-Abschluss auf `main` fehlt |
| 2 | Intra-Tenant 403-vs-404-Existence-Oracle | offen → **#1131** (8.2) | [ ] nicht behoben |

> Der 403-JSON-Fence ist Gegenstand von ADR-011/013 und der W1-Welle. Die
> W4-Evidenz führt hierzu **keinen** Live-/CI-Nachweis; die Zelle ist deshalb
> bewusst leer und nicht als bestanden gewertet.

### 3.3 MCP-Verhalten bei Redis-Ausfall (ADR-010)

| # | Schritt | Erwartung | Status |
|---|---|---|---|
| 1 | Redis stoppen, `POST /mcp/` ohne Key, `--max-time 8` | HTTP **401** in ~1,52 s (kein Hang/exit 28) | [x] W4 live |
| 2 | Redis gestoppt, `POST /mcp/` mit ungültigem Key | HTTP 401 in ~0,025 s (Cooldown-Pfad) | [x] W4 live |
| 3 | `POST /api/v1/mcp/` mit ungültigem Key, Redis down | HTTP 401 im Budget | [x] W4 live |
| 4 | Redis wieder starten, Redis/Stack healthy | Wiederherstellung bestätigt | [x] W4 live |

Die 1,52 s entsprechen dem 1,5-s-DNS-Budget (`bounded_dns`); Vorzustand war
`HTTP 000`/`curl exit 28` nach 8 s.

### 3.4 Rate-Limit vor AuthN (AUD-221, ADR-010)

| # | Schritt | Erwartung | Status |
|---|---|---|---|
| 1 | 5 Requests `POST /mcp/` mit 5 **verschiedenen** ungültigen Keys | fünf `401` | [x] W4 live |
| 2 | Danach Redis DB1 auf `*throttle*` scannen | **0** `mcp_key`-Buckets; nur IP-Backstop | [x] W4 live |

Vorzustand: der Per-Key-Bucket wuchs bei `401` (24 B → 61 B bei 1 → 5 Requests).

### 3.5 Celery-Queue-Topologie (AUD-120, ADR-015)

| # | Schritt | Erwartung | Status |
|---|---|---|---|
| 1 | Rote Queue-Bindings in Redis DB0 (`_kombu.binding.default`) | vier reguläre Bindings je eigenem `routing_key`; ggf. Rest-Binding (O2) | [x] W4 live |
| 2 | Beat **und** Worker pausieren, 10 unroutete Publishes | nur `default` +10; `llm`/`events`/`memory` = 0 | [x] W4 live |
| 3 | Gegenprobe: 3 explizit `llm`-geroutete Tasks | landen nur in `llm` | [x] W4 live |
| 4 | Rest-Binding `default→events` | keine Mehrfachzustellung → **O2, Hygiene** (8.4) | [x] gemessen (O2) |

### 3.6 Import-/ReqIF-Idempotenz (ADR-014)

| # | Schritt | Erwartung | Status |
|---|---|---|---|
| 1 | Import/ReqIF zweimal mit identischem Payload | idempotentes Ergebnis, Erfolgssemantik stabil | [ ] nicht in diesem Cut verifiziert — kein W4-Live-/CI-Nachweis |
| 2 | Import-Härtung (HMAC-Fingerprint, Tenant-Cap) | offen → **#1128** (8.2) | [ ] nicht in diesem Cut |

### 3.7 Backup/Restore-Wahrheit (ADR-012)

| # | Schritt | Erwartung | Status |
|---|---|---|---|
| 1 | `deploy/verify-restore.sh` ausführen | exit 0, `15/15` Tabellen, Rowcounts identisch | [x] W4-Smoke |
| 2 | pgvector-Spalte nach Restore | als `vector(3)` wiederhergestellt | [x] W4-Smoke |
| 3 | Injizierter Fehler in der Single-Transaction | Abbruch (exit 3), **0** Tabellen ⇒ Rollback | [x] W4-Smoke |
| 4 | Live-System-Auswirkung | Throwaway-Container, private Netz, Cleanup bestätigt | [x] W4-Smoke |

Getestet wurde der **echte** `postgres-backup`-Command-Block aus
`deploy/docker-compose.yml`, keine Test-Kopie.

### 3.8 Plugin-Version-SSOT (ADR-017)

| # | Schritt | Erwartung | Status |
|---|---|---|---|
| 1 | TS-Hermes-Plugin-Version vs. `VERSION` | konsistent (`1.8.0-beta.18`) | [x] Carrier (Working Tree) |
| 2 | MCP-`serverInfo.version`/HTTP-Discovery aus der Versionsquelle | nicht mehr hartkodiert | [ ] code-belegt (`18a272de`), aber nicht live in diesem Cut verifiziert |
| 3 | `integrations/hermes-agent-plugin` (`plugin.yaml`, `dashboard/manifest.json`) | bewusst auf `0.1.0` belassen → AUD-2026-09-106 | [ ] nicht angefasst |
| 4 | Plugin-Manifest-Build-Generierung (`017-R2-01`) | offen → 8.3 | [ ] nicht in diesem Cut |

### 3.9 Supply-Chain / Secret-Scan

| # | Schritt | Erwartung | Status |
|---|---|---|---|
| 1 | `npm audit --audit-level=high` | exit 0 (undici-Override `^8.11.2`) | [x] CI-Fix |
| 2 | gitleaks 8.30.1, Working Tree | **0** Findings | [x] W4 |
| 3 | gitleaks, volle History (3843 Commits) | **0** Findings | [x] W4 |

## 4. Verifikationsübersicht (echte W4-Werte)

> **Herkunft:** W4-Abschluss auf `main` (`1e5d7574`). **Kein neuer Lauf dieses
> Cuts** (siehe 2.4). Quelle: `docs/audit/2026-09/review/W4_CLOSEOUT.md` und
> dessen Evidenzdateien.

| Nachweis | Ergebnis | Status |
|---|---|---|
| Backend `pytest` | `10341 passed, 13 skipped, 1 xfailed` (exit 0; `backend-test`, 37m37s) | [x] W4 |
| Frontend `vitest run` | `251/251` Dateien, `2423/2423` Tests (exit 0; Node 22.17.0) | [x] W4 |
| E2E CI (Playwright) | grün, alle 4 Shards, **32/32 Checks** (#1139-Run) | [x] CI |
| Restore-Smoke | `ALL CASES PASSED (15/15 tables, 0 errors, rollback verified)` | [x] W4 |
| Secret-Scan | 0 (Working Tree) / 0 (3843 Commits) | [x] W4 |
| ADR-010…018 | durchgängig `accepted`, nicht superseded | [x] W4 |
| Neuer Suite-Lauf dieses Cuts | **nicht durchgeführt** | [ ] siehe 7 |

## 5. Regression-Kurzcheckliste

Nur die Punkte sind angekreuzt, die durch W4-Evidenz/CI gedeckt sind.

- [ ] `make up` startet durch, `/health/live` = 200 und `/health/ready` = 200
      — *nicht in diesem Cut verifiziert; `/health/ready` live nur im W4-Nachtest geprüft*
- [ ] `manage.py migrate` läuft ohne Ownership-Fehler durch — *nicht in diesem Cut verifiziert*
- [ ] Login, Workspace-Wechsel, Artefaktliste, Detailansicht — *nicht in diesem Cut verifiziert*
- [ ] Workflow-Transition in beide Richtungen, inkl. Revisionskonflikt — *nicht in diesem Cut verifiziert*
- [ ] Baseline erstellen, diffen, auflösen — *nicht in diesem Cut verifiziert*
- [ ] Review-Queue: Requirement nach `in_review`, approve und reject — *nicht in diesem Cut verifiziert*
- [ ] Audit-Log und Outbox werden geschrieben — *nicht in diesem Cut verifiziert*
- [ ] MCP `tools/list` und ein repräsentativer Tool-Call — *nicht in diesem Cut verifiziert (nur MCP-Fehlerpfad bei Redis down live geprüft)*
- [ ] i18n DE/EN ohne fehlende Übersetzungen — *nicht in diesem Cut verifiziert*
- [ ] Suche und Dashboard rendern — *nicht in diesem Cut verifiziert*
- [x] Backend-/Frontend-Suite + E2E-CI auf dem gemergten Head — *W4-Evidenz auf `main`, nicht dieser Cut*
- [x] Restore-Smoke 15/15 mit Rollback — *W4-Evidenz*
- [x] Secret-Scan 0/0 — *W4-Evidenz*

## 6. Bekannte Grenzen & Hinweise

### 6.1 `bluepencil`

Der Sidecar kann nach einem Stack-Start kurz unavailable sein. Kein Fehler
dieses Schnitts; der Dienst ist optional.

### 6.2 Vier bekannte Backend-Errors

`test_mcp_api_key_roles.py` braucht einen laufenden Stack. In der W4-Suite
traten die vier Seed-`SetupErrors` aus W1 nicht mehr als Fehler auf; das
Residuum ist als **#1133** erfasst. Nicht als Regression dieses Schnitts werten.

### 6.3 Frontend-Umgebungsartefakt

Ein Host-Lauf unter **Node 26** ist ungültig (experimentelles globales
`localStorage` verdeckt `jsdom`). Der gültige Messwert ist der Container-Lauf
mit **Node 22.17.0**: `2423/2423` grün. Kein Regressionsbefund.

### 6.4 Lokaler E2E-Teilauf ≠ CI

Der maßgebliche E2E-Lauf ist die CI auf dem gemergten #1139-Head (grün, 32/32).
Ein lokaler Shard-1-Lauf gegen den Dev-Stack ergab `98 passed / 5 failed /
3 skipped`; die Fails sind Dev-Stack-Zustandsartefakte (u. a. 10-Key-Cap und
CSV-Import mit 0 rows), keine `main`-Regression.

### 6.5 Nicht verifizierte Punkte — ausdrücklich nicht bestanden

- **Kein neuer Suite-Lauf dieses Cuts** (Abschnitt 2.4/4). Die Zahlen sind
  W4-Evidenz auf `main`.
- **Kein Image-Nachweis:** solange `1.8.0-beta.18` nicht via `docker-publish.yml`
  publiziert und gepullt wurde, existiert kein Image-Nachweis dieses Cuts.
- **#1135** (Admin-Login-Brute-Force/Lockout) und **#1136** (RLS-Coverage):
  `decision pending` — keine Tests, weil keine Entscheidung.
- **#1138** (Traceability-Anker Plugin-Versionierung): `requirements`-offen.
- **`017-R2-01`** (Plugin-Manifest-Build-Generierung) und **`018-R2-01`**
  (i18n-Re-Arm/Deadline): Rest-W3, nicht blockierend, aber offen.
- **O1** (Readiness-Latenz ~9,2 s im Ausfall) und **O2** (Broker-Binding-Hygiene
  `default→events`): gemessen, nicht blockierend.
- **ADR-001…ADR-004** weiterhin `proposed`; **`open_adrs`-Gap**
  (AUD-2026-09-333) unverändert.

## 7. Freigabe-Urteil dieses Testplans

Der Schnitt ist **beta-tauglich im Sinne der Audit-Wellen**: die vier
bestätigten Kriticals sind live behoben, Restore/Secret/ADR-Nachweise sind grün,
und es wurde keine Regression aus W1–W3 gefunden. **Nicht** abgedeckt sind ein
erneuter Suite-Lauf dieses Cuts, die `decision pending`-Residuen und die
`requirements`-Entscheidung. Es gibt **keine Produktions-, Staging- oder
QA-Freigabe**.

---

*Erstellt durch `documenter` am 2026-10-03. Interne Doku (Deutsch). Keine
Secrets. Keine erfundenen Häkchen: jedes **[x]** ist auf
`docs/audit/2026-09/review/W4_CLOSEOUT.md` bzw. dessen Evidenzdateien
zurückführbar. Kein Commit/Push durch den Autor.*
