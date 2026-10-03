# Release-Bericht v1.8.0-beta.18

> **Status: interner Pre-Release-Cut. Keine Produktions-, Staging- oder
> QA-Freigabe.** Der Schnitt bündelt die Security-, Resilience- und
> Data-Hardening-Wellen W1–W4 aus der Audit-Review 2026-09. Er ist bewusst als
> Beta geführt: mehrere Residuen sind `decision pending` bzw. dem
> `requirements`-Prozess überlassen (Abschnitt 8), und die in Abschnitt 6
> genannten Zahlen stammen aus dem **W4-Abschluss auf `main`** — **dieser Cut
> führt keinen eigenen Suite-Lauf durch** (Abschnitt 7).

## 1. Release-Ziel

`v1.8.0-beta.18` bündelt die Hardening-Wellen W1–W4 der Audit-Review 2026-09
sowie die dazugehörigen `accepted` ADRs `ADR-010` … `ADR-018`. Die inhaltliche
Arbeit steckt in den gemergten PRs #1134 (W1), #1137 (W2) und #1139 (W3); der
Cut selbst hebt die Versions-Carrier und zieht die W4-Abschlussnachweise heran.

Der Schnitt trennt zwei Dinge ausdrücklich:

- **Was erfixt ist:** die vier bestätigten Audit-Kriticals (AUD-030/031/120/221)
  sind live nachgestellt und behoben, der Restore-Smoke ist grün, die
  ADR-010…018 sind durchgängig `accepted`, und es wurde keine Regression aus
  W1–W3 gefunden.
- **Was er nicht behauptet:** es gibt keinen neuen Suite-Lauf dieses Cuts, die
  beiden `decision pending`-Residuen #1135/#1136 und die
  `requirements`-Entscheidung #1138 sind offen (Abschnitt 8), und die
  Hardening-Wellen sind kein Freibrief für Produktions-/QA-Reife.

## 2. Release-Cutoff (exakter Zeitstempel)

| Feld | Wert |
|---|---|
| Schnitt-Branch | `release/v1.8.0-beta.18` |
| Basis-Commit | `e2229ac869d57a75da9a634e90bec7c444734981` (`origin/main`) |
| W4-Merge-PR | #1140 (`Merge pull request #1140 from Popoboxxo/chore/w4-closeout`) |
| Merge-Eltern | `1e5d7574` (main) + `b1a8eeb0` (`chore/w4-closeout`) |
| Vorgänger | `v1.8.0-beta.17` |
| Cut-Datum | 2026-10-03 |

### 2.1 Ersetzung des überholten beta.18-Cuts

Ein **früherer `v1.8.0-beta.18`-Cut existierte bereits**, bevor dieser Schnitt
angelegt wurde. Er lag auf einem eigenen Branch `38da915f`
(`release: v1.8.0-beta.18`) mit dem Tag `v1.8.0-beta.18` = `bf918f15` und war
**nicht Vorfahre von `main`** (`git merge-base --is-ancestor 38da915f e2229ac8`
= negativ). Dieser alte Cut war wirkungslos und wurde **vor** diesem Cut
entfernt und durch den hier dokumentierten ersetzt:

- **Kein Force-Push, kein Rewrite des `main`-Verlaufs.** Der neue Schnitt zweigt
  sauber von `origin/main = e2229ac8` ab; der alte Cut wird nicht als Historie
  übernommen.
- Der alte Branch- und Tag-Ref ist nicht mehr referenziert (`git for-each-ref`
  findet für `beta.18` nur noch den aktuellen Branch `release/v1.8.0-beta.18`
  = `e2229ac8`; ein Tag `v1.8.0-beta.18` existiert derzeit nicht). Die alten
  Objekte `38da915f`/`bf918f15` sind nur noch als unreferenzierte Objekte im
  Objektspeicher vorhanden.

## 3. Enthaltene PRs seit `beta.17`

Per `git log` zwischen `1e5d7574..e2229ac8` bzw. über die Merge-Subjekte belegt:

| PR | Thema | Merge-Commit |
|---|---|---|
| #1134 | W1 P0 Hardening (ADR-010..014; SEC/RES/DATA/INT) | `feab1087` |
| #1137 | W2 P1 Core-Welle (SEC-04/08, RES-04/05/06, DATA-05..09, INT-02..06, PLUG-02/03, DOC-01/03/06; ADR-015) | `3983a3c5` |
| #1139 | W3 P2-Welle (ADR-016..018) | `1e5d7574` |
| #1140 | W4-Abschluss auf `main` (Doku + Evidenz) | `e2229ac8` |

Belegte Einzelcommits des W4-Abschlusses (nur Doku/Evidenz, kein Produktcode):

| Commit | Inhalt |
|---|---|
| `b1a8eeb0` | `docs(audit): add W4 closeout report` |
| `d1ed53b5` | `docs(audit): add W4 live retest evidence for audit criticals` |
| `8e45a87f` | `chore: add W4 atomic restore smoke evidence` |

Ergänzend relevante, belegte Fixes aus W2/W3:
`4498983c` (distinct Celery routing keys, RES-04/06), `77cb2ac7` (CI:
restore-smoke, `npm audit`, E2E readiness), `dec384b6` (`.env` für die
Restore-Smoke-Compose-Config), `1d076854` (E2E-Listen-Envelope/Status-Selektor),
`aeaf9605` (fail-closed Downgrade-Gate), `78ca816c` (Decomposition-Default auf
Hierarchie-Link-Typen), `59ab6c32`/`18a272de`/`0cdb201c` (ADR-016/017/018).

## 4. Themen-Highlights (W1–W4, ADR-010…018)

- **W1 (PR #1134; ADR-010..014):** Health-Vertrag (`/health/live` +
  `/health/ready`, fail-closed), Autorisierungsachse Workspace/Tenant,
  Backup-Wahrheit, Collection-Route-Autorisierung,
  Import-Erfolgssemantik/-Idempotenz.
- **W2 (PR #1137; ADR-015):** P1-Kernwelle inkl. Celery-Queue-Topologie mit vier
  Queues und je eigenem `routing_key` auf dem geteilten Direct-Exchange
  (`default`, `llm`, `events`, `memory`).
- **W3 (PR #1139; ADR-016..018):** Preset-SSOT und `refines`-Hierarchiekante
  (ADR-016), Plugin-/Server-Versions-SSOT (ADR-017), i18n-Vertrag mit
  Inline-Default-Ratchet (ADR-018).
- **W4 (PR #1140):** konsolidierter Abschlussnachweis — Vollsuite,
  Live-Nachtest der Kriticals, Restore-Smoke, Secret-Scan, ADR-Statuskontrolle
  und Gesamt-DoD gegen das Preset `rapid-prototyping`.

Konkrete belegte Laufzeit-Fixes (Details in Abschnitt 6):

| Finding | Vorzustand (2026-10-01) | Jetzt (live) |
|---|---|---|
| AUD-030 MCP-Hang bei Redis-Ausfall | `HTTP 000` / curl exit 28 nach 8 s | `401` in **1,52 s** kalt / **0,025 s** warm |
| AUD-031 `/health/` false-green | `200 ok` trotz Redis down | `/health/ready` **503**, `/health/live` **200** |
| AUD-221 Rate-Limit vor AuthN | `401` füllt `throttle_mcp_key_*` (24 B → 61 B) | `401`, **0** Per-Key-Buckets; nur IP-Backstop |
| AUD-120 4× Queue-Zustellung | 1 Publish landet in 4 Queues | 10 Publish → nur `default` (+10) |

## 5. Versions-Carrier-Delta

12 Carrier in 14 Dateien, 23 Ersetzungen, alle von `1.8.0-beta.17` auf
`1.8.0-beta.18`:

| Datei | Treffer |
|---|---|
| `VERSION` | 1 |
| `.env.example` | 2 |
| `deploy/docker-compose.yml` | 6 |
| `deploy/docker-compose.minimal.yml` | 3 |
| `frontend/package.json` | 1 |
| `frontend/package-lock.json` | 2 |
| `integrations/hermes-plugin/reqogniloom/package.json` | 1 |
| `integrations/hermes-plugin/reqogniloom/package-lock.json` | 2 |
| `integrations/hermes-plugin/reqogniloom/hermes-plugin.json` | 1 |
| `dist/plugins/antigravity/reqogniloom/plugin.json` | 1 |
| `dist/plugins/claude-code/reqogniloom/.claude-plugin/plugin.json` | 1 |
| `site/index.html` | 2 |

### 5.1 Doku-Stände, die mit dem Schnitt mitziehen mussten

Zwei Stellen behaupteten nach dem Bump noch den Vorgängerstand und sind
mitgezogen, weil sie den *aktuellen* Release bezeichnen:

| Datei | Stelle |
|---|---|
| `docs/api/MCP-SURFACE.md:28` | `Version`-Zeile, die `VERSION` ausdrücklich als Quelle zitiert |
| `docs/CODEBASE_OVERVIEW.md:20, 657, 1139` | „Stand `v1.8.0-beta.17`" an den drei MCP-Fundstellen |

Die Zahlen selbst (219 Tools / 35 Gruppen) sind unverändert, da W1–W4 kein
Tool, keine Gruppe und keinen `inputSchema` angefasst haben.

### 5.2 Bewusst NICHT angefasst

- **`integrations/hermes-agent-plugin` bleibt auf `0.1.0`** (`plugin.yaml:2`,
  `dashboard/manifest.json:6`). Der Versions-Drift des Python-Plugins ist als
  AUD-2026-09-106 erfasst und nicht Teil dieses Carrier-Bumps; der
  Build-Generator erfasst dieses Bundle ohnehin nicht.
- **`docs/agent-templates/tool-manifest.json`** trägt
  `"generated_from": "reqogniloom==1.8.0-beta.16"` — ein Provenienz-Stempel des
  generierten Artefakts, kein Versionscarrier. Die Datei wird nicht nur für
  einen String neu generiert.
- **`deploy/docker-compose.override.yml`** und
  **`deploy/docker-compose.test.yml`** sind Dev-/Testoverlays und gehören nicht
  zum Release.

## 6. Verifikation

> **Herkunft der Zahlen.** Alle Werte in diesem Abschnitt wurden im
> **W4-Abschluss auf `main` (`1e5d7574`)** gemessen und sind über
> `docs/audit/2026-09/review/W4_CLOSEOUT.md` sowie dessen Evidenzdateien
> `…/evidence/W4_LIVE_RETEST.md` und `…/evidence/W4_RESTORE_SMOKE.txt`
> rückverfolgbar. **Dieser Cut führt keinen eigenen Suite-Lauf durch** (siehe
> Abschnitt 7).

| Nachweis | Ergebnis | Umgebung / Laufzeit |
|---|---|---|
| Backend-Suite | **`10341 passed, 13 skipped, 1 xfailed`** (exit 0) | Compose-Service `backend-test`, 37m37s |
| Frontend-Suite | **`251/251` Test-Dateien, `2423/2423` Tests** (exit 0) | Container, Node 22.17.0 |
| E2E-CI | **grün**, alle 4 Shards, **32/32 Checks** | CI im #1139-Run |
| Restore-Smoke | **`ALL CASES PASSED (15/15 tables, 0 errors, rollback verified)`** | exit 0 |
| Secret-Scan (gitleaks 8.30.1) | **0** Working Tree, **0** über 3843 Commits | Gate-Konfiguration |
| ADR-Status | ADR-010…ADR-018 durchgängig `accepted`, nicht superseded | `docs/se/ADR/**` |

**Backend-Bezug zur Baseline.** W1-Baseline `10184 passed` → jetzt `10341` =
**+157** neue grüne Tests, keine neuen Fehler. Die vier bekannten
Seed-`SetupErrors` aus W1 (`mcp_server/tests/test_mcp_api_key_roles.py`) traten
in diesem Lauf nicht mehr als Fehler auf (Residuum: #1133).

**Live-Nachtest der vier Kriticals** (Details: `W4_LIVE_RETEST.md`):

- **AUD-030:** `401` in **1,52 s** kalt (1,5-s-DNS-Budget) / **0,025 s** warm
  (Cooldown-Pfad); vorher `HTTP 000`/exit 28 nach 8 s.
- **AUD-031:** `/health/ready` = **503** (`cache` down), `/health/live` = **200**;
  `/health/` (Alias) = 503 mit `Deprecation`/`Sunset: 01 Apr 2027`. Die
  Readiness-Probe braucht im Ausfall ~9,2 s (O1, Abschnitt 8).
- **AUD-221:** fünf distinkte ungültige Credentials → fünf `401`, **0**
  Per-Key-Buckets; nur der IP-Backstop wächst.
- **AUD-120:** im kontrollierten Test (Beat/Worker pausiert) 10 unroutete
  Publishes → `default` +10, `llm`/`events`/`memory` = 0. Redis und Stack am
  Ende healthy.

**Restore-Smoke** (`W4_RESTORE_SMOKE.txt`): 15/15 Tabellen, Rowcounts
Quelle = Ziel identisch, pgvector-Spalte als `vector(3)` wiederhergestellt,
injizierter Fehler rollte die Single-Transaction auf 0 Tabellen zurück (exit 3).
Der echte `postgres-backup`-Command-Block aus `deploy/docker-compose.yml` wurde
getestet, nicht eine Kopie.

**Secret-Scan:** gitleaks 8.30.1, 0 Findings — Working Tree **und** volle
History (3843 Commits).

**DoD:** Preset `rapid-prototyping` hat alle Gates `false`; die obigen Nachweise
wurden **über** das geforderte Minimum hinaus gefahren. Gearbeitet wurde auf
`chore/w4-closeout`, nicht auf `main`.

## 7. Was dieser Schnitt **nicht** beweist

- **Kein neuer Suite-Lauf dieses Cuts.** Die W4-Commits sind ausschließlich
  Doku/Evidenz; die Carrier- und Doku-Änderungen fassen keinen Code an. Die in
  Abschnitt 6 gezeigten Zahlen sind der W4-Abschluss auf `main`, **nicht** ein
  frischer Lauf von `release/v1.8.0-beta.18`.
- **Kein Image freigegeben/gemessen.** Ein GHCR-Publish via `docker-publish.yml`
  ist Teil von Abschnitt 9; solange nicht publiziert und gepullt, gibt es keinen
  belastbaren Image-Nachweis für diesen Cut.
- **Kein lokaler E2E-Vollnachweis.** Der maßgebliche E2E-Lauf ist die CI auf dem
  gemergten #1139-Head. Ein lokaler Shard-1-Teillauf ergab
  `98 passed / 5 failed / 3 skipped`; die Fails sind Dev-Stack-Zustandsartefakte
  (u. a. 10-Key-Cap auf der langlaufenden Dev-DB), keine `main`-Regression.
- **Kein Attributkatalog-/Migrationsnachweis für Altinstanzen** über diese
  Wellen hinaus.

## 8. Offene Punkte / Follow-ups

### 8.1 `decision pending`

- **#1135** — Brute-Force-/Lockout-Schutz für den Django-Admin-Login
  (SEC-04-Rest): braucht eine Scope-/Policy-Entscheidung, keinen Code-Fix.
- **#1136** — RLS-Coverage-Ausweitung (Pre-Auth + Webhook/Outbox-Tabellen) mit
  gestaffeltem Rollout (DATA-07-Rest): braucht eine bewusste Rollout-Entscheidung.
- **#1138** — Traceability-Anker der Plugin-Versionierung (ADR-017-Gap / 002-02):
  eine `requirements`-Entscheidung.

### 8.2 Weitere offene Audit-Issues

`#1128` (Import-Idempotenz-Härtung), `#1129` (`expected_version`-Parity für
MCP-Goal-Transitions / `main_goal.approve`), `#1130` (Redis-RESILIENZ TLS
`rediss://`, Frozen-Server-Read-Stalls), `#1131` (Intra-Tenant-403-vs-404-Oracle
in Workspace-Fence-Antworten), `#1132` (Celery-Beat lädt das Embedding-Modell,
~407 MiB RSS), `#1133` (MCP-Live-Stack-API-Key-Role-Tests self-seeding).

### 8.3 Rest-W3 (Concept-Review ADR-016…018)

- **`017-R2-01`** (minor): die Zusage, dass die Bundle-Manifeste beim Build aus
  `VERSION` erzeugt werden, ist eine Mechanik-Behauptung — `PLUG-04` muss die
  Generierung pinnen oder das Manifest explizit als hand-gepflegt benennen.
- **`018-R2-01`** (minor): das Deadline-Budget senkt bis zur Deadline, definiert
  aber kein Folge-Ziel/-Deadline (Re-Arm) ⇒ theoretischer Re-Freeze. `DOC-02`
  muss eine Re-Arm-Regel ergänzen oder die Wortwahl schärfen.

### 8.4 Live-Restrisiken O1 / O2

- **O1 (Low):** `/health/ready` blockiert bei Redis-Ausfall ~9,2 s (sequenzielle
  bounded Dependency-Probes). Fail-closed ist korrekt; Empfehlung:
  Probes parallelisieren oder das Timeout-Budget dokumentieren.
- **O2 (Low, Hygiene):** Rest-Binding `default→events` im Live-Broker
  (`_kombu.binding.default` Member 5, außerhalb der deklarierten `task_queues`);
  im kontrollierten Test keine Mehrfachzustellung. Beim nächsten Broker-Neustart
  auf genau 4 Members prüfen.

### 8.5 Unverändert offen

- **ADR-001…ADR-004** weiterhin `status: proposed` (out-of-scope dieser Wellen).
- **Traceability-Gap `open_adrs`** (AUD-2026-09-333): 0/835 REQs führen
  `open_adrs`; maschinelle REQ↔ADR-Verknüpfung fehlt. Bewusst `requirements`
  überlassen.

## 9. Tag & GitHub-Pre-Release

1. Release-PR auf `main` mergen (Basis `origin/main = e2229ac8`, PR #1140).
2. Tag `v1.8.0-beta.18` auf den Release-Commit setzen.
3. GHCR-Publish über `docker-publish.yml` (Backend-/Frontend-Image mit Tag
   `1.8.0-beta.18`).
4. GitHub-Pre-Release als **Pre-Release** markieren, **nicht** als `latest`.
5. Release-Notizen aus dem `CHANGELOG`-Block dieses Schnitts übernehmen.

---

*Erstellt durch `documenter` am 2026-10-03. Interne Doku (Deutsch). Keine
Secrets. Keine erfundenen Messwerte: alle Zahlen stammen aus
`docs/audit/2026-09/review/W4_CLOSEOUT.md` und dessen Evidenzdateien. Kein
Commit/Push durch den Autor — der Commit erfolgt durch den `git`-Agenten.*
