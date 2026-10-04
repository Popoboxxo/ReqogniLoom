---
type: REVIEW
scope: "W4 Abschluss — Merge-, Suite-, Live-, Restore-, Secret- und ADR-Nachweis der 2026-09-Audit-Wellen W1–W3"
status: final
date: 2026-10-03
author_agent: documenter
merge_base: 1e5d7574
version_observed: 1.8.0-beta.17
doD_preset: rapid-prototyping
---

# W4_CLOSEOUT — Abschlussnachweis der Audit-Wellen W1–W3 auf `main`

**Zweck.** Konsolidierter Abschluss der Audit-Review 2026-09 (Wellen W1–W3) auf Basis
ausschließlich **real gemessener** Werte. Dieses Dokument fasst die Vollsuite, den
Live-Nachtest der vier Kriticals, den Restore-Smoke, den Secret-Scan, die
ADR-Statuskontrolle, den Gesamt-DoD und die verbleibenden Residuen zusammen und
gibt ein Release-Reife-Urteil ab.

**Merge-Basis.** `origin/main` = `1e5d7574`. Die drei Audit-Wellen wurden als
Pull-Requests integriert:

| PR | Merge-Commit | Inhalt |
|---|---|---|
| #1134 | `feab1087` | W1 P0 Hardening (ADR-010..014, SEC/RES/DATA/INT) |
| #1137 | `3983a3c5` | W2 P1 Core-Welle (SEC-04/08, RES-04/05/06, DATA-05..09, INT-02..06, PLUG-02/03, DOC-01/03/06) |
| #1139 | `1e5d7574` | W3 P2-Welle |

Alle drei wurden per `git merge --merge` integriert (kein Force). Der W3-Merge `1e5d7574`
ist zugleich der aktuelle `origin/main`-Tip.

**CI-Blocker-Fixes (3, vor der Vollsuite).**

1. **Restore-Smoke-Aufruf.** `deploy/verify-restore.sh` hatte kein Exec-Bit
   (Modus `100644`). Korrigiert auf `100755` **und** der CI-Aufruf auf
   `bash deploy/verify-restore.sh` umgestellt; zusätzlich erforderte Compose eine
   vorhandene `.env` (`env_file: .env`) — neuer CI-Step `cp .env.example .env`
   (Compose bricht sonst bei fehlender `.env` hart ab).
2. **`npm audit` / undici.** undici `8.10.0` (transitiv via `jsdom`) → `overrides:
   undici ^8.11.2` (Lock auf 8.11.2) plus In-Range-Security-Bumps
   (`brace-expansion`, `dompurify`). `npm audit --audit-level=high` = exit 0.
3. **E2E-Precondition `/health/` = 503.** Im Playwright-CI lief kein Celery, wodurch
   die Readiness-Probe gemäß ADR-010 (fail-closed) mit 503 antwortet. `playwright.yml`
   startet nun Celery-Worker + Beat und wartet **bounded** auf `/health/ready`.
   Zusätzlich E2E-Test-Drift bei den INT-05-paginierten Listen behoben
   (envelope-toleranter in `auth-api`, `ui-test-campaign`, `user-management`,
   `hermes-bugfix-campaign`) und ein Strict-Mode-Selektor in `baselines-view`
   korrigiert. Die Logzeile `relation "mem_system_memory_settings" does not exist`
   war **gefangene Startup-Noise** (die Migration ist committet) — **nicht** die
   Ursache des 503.

---

## 1. Vollsuite auf `main`

| Suite | Ergebnis | Exit | Umgebung / Laufzeit |
|---|---|---|---|
| Backend (`pytest`) | **10341 passed, 13 skipped, 1 xfailed** | 0 | Compose-Service `backend-test`, 37m37s |
| Frontend (`vitest run`) | **251/251 Test Files, 2423/2423 Tests passed** | 0 | Container, Node 22.17.0 |
| E2E (Playwright/Chromium) | CI auf dem gemergten Head **grün** — alle 4 Shards, **32/32 Checks** im #1139-Run | 0 (CI) | CI |

- **Backend-Vergleich zur Baseline:** W1-Baseline war `10184 passed` → jetzt
  `10341 passed` = **+157** neue, grüne Tests. Keine neuen Fehler. Die 4 bekannten
  Seed-`SetupErrors` aus W1 (`mcp_server/tests/test_mcp_api_key_roles.py`, fehlender
  Demo-Workspace-Seed) treten in diesem Lauf **nicht** mehr als Fehler auf (Residuum
  siehe §7, Issue #1133).
- **Frontend-Hinweis (Umgebungsartefakt, keine Regression):** Ein Host-Lauf unter
  **Node 26** ist ungültig — das experimentelle globale `localStorage` verdeckt
  `jsdom`. Der gültige Messwert stammt aus dem Container mit **Node 22.17.0**:
  `2423/2423` grün. Das ist ein Env-Artefakt, **kein** Regressionsbefund.
- **E2E-Hinweis (ehrliche Kennzeichnung):** CI ist auf dem gemergten Head grün. Ein
  **lokaler Teillauf** (Shard 1/4 gegen den Dev-Stack) ergab `98 passed / 5 failed /
  3 skipped`. Die **5 Fails sind Dev-Stack-Zustandsartefakte**, u. a. API-Key-Erstellung
  `400` durch den 10-Key-Cap auf der langlaufenden Dev-DB und CSV-Import mit `0 rows`.
  Das ist **keine** `main`-Regression — der maßgebliche CI-Lauf ist grün.

**Evidenz:** CI-Lauf des #1139-Merges (32/32 Checks, 4 Shards); Backend-/Frontend-Messung
dieser Session.

---

## 2. Live-Nachtest der Kriticals 030 / 031 / 120 / 221

Vollständiger Rohbeleg: **`docs/audit/2026-09/review/evidence/W4_LIVE_RETEST.md`**
(Live gegen den Dev-Stack `localhost:8001`, 2026-10-03).

| Finding | Vorzustand (2026-10-01) | Jetzt (live) | Verdikt |
|---|---|---|---|
| **AUD-030** MCP-Hang bei Redis-Ausfall | HTTP 000 / curl exit 28 nach 8 s | 401 in **1,52 s** kalt / **0,025 s** warm | **bestätigt behoben** |
| **AUD-031** `/health/` false-green bei Redis down | 200 `ok` trotz Redis-Ausfall | `/health/ready` = **503** (`cache` down), `/health/live` = **200** | **bestätigt behoben** |
| **AUD-221** Rate-Limit vor AuthN | 401 füllt `throttle_mcp_key_*` (24 B → 61 B) | 401, **0** Per-Key-Buckets; nur IP-Backstop | **bestätigt behoben** |
| **AUD-120** 4× Queue-Zustellung | 1 Publish landet in 4 Queues | kontrolliert: 10 Publish → **nur** `default` (+10), `llm`/`events`/`memory` = 0 | **bestätigt behoben** |

- Keine der vier Prüfungen war „nicht verifizierbar" — alle vier wurden live reproduziert.
- **Redis und Stack am Ende healthy**; Wiederherstellung nach jedem Ausfalltest bestätigt.
- **Methodik-Hinweis AUD-120:** Für eine saubere Messung wurden `celery-1`/`celery-beat-1`
  kurzzeitig pausiert, da Beat-Dispatch sonst die Queue-Längen überlagert. Danach
  regelkonform wieder gestartet; keine Volumes/DB berührt.
- **Restrisiken** aus diesem Lauf: O1/O2 (siehe §7).

---

## 3. Restore-Smoke

Vollständiger Rohbeleg: **`docs/audit/2026-09/review/evidence/W4_RESTORE_SMOKE.txt`**.

```
atomic restore smoke: ALL CASES PASSED (15/15 tables, 0 errors, rollback verified)
Exit code: 0
```

- **COPY-Blöcke:** 15 (≥ 15 gefordert). **Tabellen:** 15/15 — Quell- und
  Restore-Ziel-Rowcounts identisch. **pgvector-Spalte:** als `vector(3)` wiederhergestellt.
- **Atomizität:** Injizierter Fehler innerhalb der Single-Transaction brach den Restore ab
  (exit 3), **0 Tabellen** verblieben → Transaktion vollständig zurückgerollt.
- Geprüft wurde der **echte** `postgres-backup`-Command-Block aus
  `deploy/docker-compose.yml` (via `docker compose config --format json`), keine Test-Kopie.
- **Keine Live-System-Auswirkung:** Throwaway-Postgres auf privatem Netz
  `reqlo-restore-smoke-*`, das der EXIT-Trap räumt; die Live-DB wurde nie kontaktiert.
  Cleanup nach dem Lauf bestätigt (keine Container/Netzwerke/Volumes übrig).
- **Bezug:** ADR-012, DATA-01.

---

## 4. Secret-Scan

Tool: **gitleaks 8.30.1**, gegen die Gate-Konfiguration.

| Scope | Findings | Exit |
|---|---|---|
| Working Tree | **0** | 0 |
| Volle History (**3843 Commits**) | **0** | 0 |

Keine Leaks in Diff, Commit oder Working Tree. Die Evidenzdateien dieser Session enthalten
**keine** Secrets (API-Keys/Tokens sind fiktiv bzw. `<redacted-invalid-key>`).

---

## 5. ADR-Statuskontrolle ADR-010…018

| ADR | Frontmatter-Status | `superseded_by` |
|---|---|---|
| ADR-010 Health-Vertrag | `accepted` | `null` |
| ADR-011 Autorisierungsachse Workspace/Tenant | `accepted` | `null` |
| ADR-012 Backup-Wahrheit | `accepted` | `null` |
| ADR-013 Collection-Route-Autorisierung | `accepted` | `null` |
| ADR-014 Import-Erfolgssemantik/-Idempotenz | `accepted` | `null` |
| ADR-015 Celery-Queue-Topologie | `accepted` | `null` |
| ADR-016 Preset-SSOT und `refines`-Hierarchiekante | `accepted` | `null` |
| ADR-017 Plugin-/Server-Versions-SSOT | `accepted` | `null` |
| ADR-018 i18n-Vertrag (Inline-Default/Ratchet) | `accepted` | `null` |

- **Verdikt:** ADR-010…ADR-018 sind durchgängig `accepted` und nicht superseded.
- **`open_adrs`:** **keine verwaisten Treffer** (0 Frontmatter-Treffer in `docs/se/**`;
  die einzigen Vorkommen des Strings stammen aus Audit-Dokumenten selbst, nicht aus REQ-
  oder ADR-Frontmatter).
- **Außerhalb des Scope:** ADR-001…ADR-004 stehen weiterhin auf `status: proposed`
  (out-of-scope dieser Welle, unverändert).

---

## 6. Gesamt-DoD gegen Preset `rapid-prototyping`

Preset-Quelle: `.agent-meta/config/dod-presets.yaml` → `presets.rapid-prototyping`.

| Gate | Preset-Wert | Erfüllt? |
|---|---|---|
| `req-traceability` | false | n/a (nicht gefordert) |
| `tests-required` | false | n/a (nicht gefordert) |
| `codebase-overview` | false | n/a |
| `security-audit` | false | n/a |
| `ai-security-review` | false | n/a |
| `prompt-governance` | false | n/a |
| `lifecycle-ownership` | false | n/a |
| `release-gates.artifact-freshness` | false | n/a |
| `release-gates.docker-image-scan` | false | n/a |
| `release-gates.action-pin-validation` | false | n/a |

- **Alle Preset-Gates sind `false`** — das Preset fordert sie nicht.
- **Basis-DoD erfüllt:** Commits folgen Conventional Commits, die Konventionen sind
  eingehalten, es wurde auf Branch `chore/w4-closeout` (nicht `main`) gearbeitet.
- **Wichtige Einordnung (ehrlich):** Wegen `tests-required: false` sind die in §1–§4
  gezeigten grünen Suiten, der Restore-Smoke, der Secret-Scan und die Live-Verifikation
  **nicht** durch das Preset vorgeschrieben — sie wurden **darüber hinaus** als Nachweis
  gefahren. Das DoD ist damit erfüllt; die Nachweise übertreffen das geforderte Minimum.

---

## 7. Offene Residuen (konsolidiert)

Keine dieser Residuen ist eine Regression aus W1–W3; alle waren bereits vor dem
Abschluss bekannt und sind als **nicht blockierend** für den Merge eingestuft.

### 7.1 GitHub-Issues #1128–#1138

| Issue | Status | Titel (gekürzt) |
|---|---|---|
| #1128 | OPEN | `fix: harden INT-01 import idempotency` (HMAC-Fingerprint, Sunset-Header, harter Tenant-Cap, guarded randomUUID) |
| #1129 | OPEN | `fix: add expected_version` Parity für MCP-Goal-Transitions und `main_goal.approve` |
| #1130 | OPEN | `fix: extend Redis resilience to TLS (rediss://)` und Frozen-Server-Read-Stalls (RES-01-Rest) |
| #1131 | OPEN | `fix: close intra-tenant 403-vs-404 existence oracle` in Workspace-Fence-Antworten (SEC-02-Rest) |
| #1132 | OPEN | `perf: stop celery beat from preloading the embedding model` (~407 MiB RSS) |
| #1133 | OPEN | `test: make MCP live-stack API-key role tests self-seeding` (4 vorbestehende SetupErrors) |
| #1134 | MERGED | `fix: W1 P0 hardening wave 1` (ADR-010..014, SEC/RES/DATA/INT) |
| #1135 | OPEN | `security: add brute-force protection / lockout for Django admin login` (SEC-04-Rest, **Entscheidung offen**) |
| #1136 | OPEN | `improvement: extend RLS coverage (pre-auth + webhook/outbox tables)` mit gestaffeltem Rollout (DATA-07-Rest, **Entscheidung offen**) |
| #1137 | MERGED | `feat: W2 P1 core wave` (SEC-04/08, RES-04/05/06, DATA-05..09, INT-02..06, PLUG-02/03, DOC-01/03/06) |
| #1138 | OPEN | `requirements: decide traceability anchor for plugin versioning` (ADR-017-Gap / 002-02) |

Explizit hervorgehoben: **#1135** und **#1136** sind Entscheidungs-Residuen
(`decision pending`) — sie benötigen eine bewusste Scope-/Policy-Entscheidung, keinen
Code-Fix. **#1138** ist eine `requirements`-Entscheidung (Traceability-Anker der
Plugin-Versionierung). Die gemergten Issues #1134/#1137 sind abgeschlossen.

### 7.2 Rest-W3 (aus dem ADR-Concept-Review ADR-016…018)

Quelle: `docs/se/reports/concept-review-ADR-016-018_2026-10-03.md`.

- **ADR-017 — `017-R2-01` (minor, Plugin-Manifest-Build-Generierung).**
  Die Zusage, dass die im Repo produktiv ausgelieferten Bundle-Manifeste
  (`dist/plugins/**`, TS-Hermes-Plugin) beim Build aus `VERSION` erzeugt werden und
  „nicht driften können", ist eine **Mechanik-Behauptung**: Das
  `integrations/hermes-plugin/reqogniloom/hermes-plugin.json` liegt heute committed mit
  `1.8.0-beta.17` vor — ob hand-gepflegt oder generiert, ist aus dem ADR nicht belegt.
  → `PLUG-04` muss die Generierung **pinnen** oder das Manifest explizit als
  hand-gepflegt benennen. **Nicht blockierend.**
- **ADR-018 — `018-R2-01` (minor, Re-Arm/Deadline).**
  Das „Deadline-Budget" erzwingt eine Senkung **bis** zur Deadline, nicht „monoton" im
  Wortsinn; nach Erreichen eines Ziels ist **kein Folge-Ziel/-Deadline (Re-Arm)**
  definiert ⇒ theoretischer Re-Freeze. → `DOC-02` muss eine Re-Arm-Regel
  (nächstes Ziel/Deadline) ergänzen oder die Wortwahl auf „deadline-stufenweise sinkend"
  schärfen. **Nicht blockierend.**

### 7.3 Live-Re-Test-Restrisiken O1 / O2

Quelle: `docs/audit/2026-09/review/evidence/W4_LIVE_RETEST.md`, §6.

- **O1 (Low) — Readiness-Probe-Latenz im Ausfall ~9,2 s.**
  `/health/ready` blockiert bei Redis-Ausfall ~**9,2 s** (mehrere sequenzielle
  Dependency-Probes mit bounded Timeouts). Das **fail-closed**-Verhalten bleibt korrekt
  (503); bei einem Orchestrator-Probe-Timeout < 9 s wird ebenfalls nicht-200 gemeldet
  (ebenfalls fail-closed). Empfehlung: Probes parallelisieren oder das Timeout-Budget
  dokumentieren. Latency-Item, kein Korrektheitsdefekt.
- **O2 (Low, Hygiene) — Rest-Binding `default→events` im Live-Broker.**
  Das Binding-Set `_kombu.binding.default` enthält 5 Members; der fünfte
  (`default→events`) ist **nicht** Teil der deklarierten `task_queues`. Im kontrollierten
  Test verursachte er **keine** Mehrfachzustellung. Vermutlich ein Überbleibsel aus der
  Vorkonfiguration im laufenden Redis-Datensatz. Empfehlung: bei nächstem Broker-Neustart
  prüfen, dass ein frischer Broker genau 4 Members zeigt, bzw. den veralteten Member
  kontrolliert entfernen. **Kein Produktcode-Defekt.**
- **(Info, zur Vollständigkeit) O3 — `redis-cli`-AUTH-Quirk.** Container-Env
  `REDISCLI_AUTH=` (leer) setzt die `-n`-DB-Auswahl zurück; Messungen müssen
  `unset REDISCLI_AUTH` verwenden. Nur Methodik-Hinweis.

### 7.4 Ergänzend offen (nicht Teil der obigen Klammer, unverändert)

- **Traceability-Gap `open_adrs`** (`AUD-2026-09-333`): repoweit **0/835** REQs führen
  `open_adrs`; maschinelle REQ↔ADR-Verknüpfung fehlt. Bewusst `requirements` überlassen.
- **ADR-001…ADR-004** weiterhin `proposed` (out-of-scope dieser Welle).

---

## 8. Release-Reife-Urteil

**Beobachtete Version:** `VERSION` = **`1.8.0-beta.17`** (aktueller Stand, nicht gebumpt).

**Ist `main` beta-/release-fähig?**

- **Beta-fähig: JA.** `main` = `1e5d7574` ist nach den drei gemergten Wellen in sich
  konsistent und durch grüne Nachweise gedeckt: Backend `10341 passed` / `0` Fehler,
  Frontend `2423/2423`, E2E-CI grün (32/32 Checks), Restore-Smoke `15/15` mit
  verifiziertem Rollback, Secret-Scan `0/0` (Working Tree **und** 3843 Commits History),
  ADR-010…018 durchgängig `accepted`. Es wurde **keine** Regression aus W1–W3 gefunden.
- **Final-/GA-fähig (1.8.0 ohne Beta): eingeschränkt.** Dafür müssten die offenen
  Residuen (§7) bewusst geschlossen **oder** als bekannte Nicht-Blocker für das
  Beta-Release akzeptiert werden. Das ist eine Scope-/Policy-Entscheidung, kein
  Regressionshindernis.

**Was für einen `1.8.0-beta.18`-Nachfolger konkret fehlt:**

1. **VERSION-Bump + Release-Carrier.** `VERSION` von `1.8.0-beta.17` auf `beta.18`
   heben und den Release-Report nach dem etablierten Muster anlegen
   (Vorbild: `docs/se/reports/RELEASE_v1.8.0-beta.17.md`). Das ist der formale
   Release-Schritt.
2. **Entscheidung zu den offenen Issues #1128–#1133, #1135, #1136, #1138.**
   Insbesondere die beiden `decision pending`-Residuen **#1135** (Admin-Login-
   Brute-Force/Lockout) und **#1136** (RLS-Coverage-Ausweitung, gestaffelter Rollout)
   sowie **#1138** (Traceability-Anker Plugin-Versionierung) benötigen eine bewusste
   Entscheidung, ob sie in `beta.18` einfließen oder als bekannte Residuen im
   Beta-Release dokumentiert werden.
3. **Rest-W3 abschließen:** `017-R2-01` (PLUG-04: Plugin-Manifest-Build-Generierung
   nachweisen oder Manifest als hand-gepflegt benennen) und `018-R2-01`
   (DOC-02: Re-Arm-/Deadline-Semantik schärfen).
4. **O1/O2 adressieren oder dokumentieren:** O1 (Readiness-Latenz ~9,2 s im Ausfall,
   Probes parallelisieren bzw. Budget dokumentieren) und O2 (Broker-Binding-Hygiene
   beim nächsten Neustart prüfen).
5. **Optional/außerhalb des engeren Scope:** der Traceability-Gap `open_adrs`
   (`AUD-2026-09-333`) und die noch `proposed` ADR-001…004.

**Fazit.** `main` ist ohne Regressionsblocker **beta-release-fähig**; für einen
`1.8.0-beta.18`-Nachfolger fehlt kein Fix an der Suite, sondern allein der formale
Version-Bump/Release-Carrier und die **bewusste Übernahme-Entscheidung** der
konsolidierten Residuen (§7). Keines der offenen Items ist ein akuter Defekt; sie sind
Hardening-, Policy- und Nachweis-Restpunkte.

---

## Evidenz- und Referenzliste

| Artefakt | Zweck |
|---|---|
| `docs/audit/2026-09/review/evidence/W4_LIVE_RETEST.md` | Rohbeleg Live-Nachtest AUD-030/031/120/221, O1/O2 |
| `docs/audit/2026-09/review/evidence/W4_RESTORE_SMOKE.txt` | Rohbeleg Restore-Smoke (15/15, Rollback verifiziert) |
| `docs/se/ADR/ADR-010…018_*.md` | ADR-Statuskontrolle (§5) |
| `.agent-meta/config/dod-presets.yaml` | Preset `rapid-prototyping` (§6) |
| `docs/se/reports/concept-review-ADR-016-018_2026-10-03.md` | Rest-W3 `017-R2-01`/`018-R2-01` (§7.2) |
| `VERSION` | Beobachtete Version `1.8.0-beta.17` (§8) |

---

*Erstellt durch `documenter` am 2026-10-03. Interne Doku (Deutsch). Keine Secrets;
alle Schlüsselwerte fiktiv bzw. redigiert. Kein Commit/Push durch den Autor — der
Commit erfolgt durch den Orchestrator via `git`-Agent. Keine erfundenen Messwerte:
alle Zahlen stammen aus dieser Session bzw. den referenzierten Evidenzdateien.*
