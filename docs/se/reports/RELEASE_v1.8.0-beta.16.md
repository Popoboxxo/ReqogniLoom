---
type: STRATEGY
scope: Release v1.8.0-beta.16
status: draft
date: 2026-09-26
author_agent: release
---

# Release-Bericht v1.8.0-beta.16

> **Status: `draft` — Vorbereitung, keine Auslieferung.** Bei diesem Schnitt wurde
> **kein Commit, kein Tag und kein Push** ausgeführt. Der Tag `v1.8.0-beta.16`
> existiert **nicht**; es wurde **kein Image gebaut** und deshalb **kein Image-Digest**
> dokumentiert. Dieser Bericht ist **keine** externe Production- oder QS-Freigabe.

## 1. Release-Ziel

Vorbereitung des Beta-Release `v1.8.0-beta.16` auf dem Branch
`release/v1.8.0-beta.16` (Basis: `origin/main` = `73892571`). Dieser Bericht
dokumentiert die Vorbereitung in diesem Branch: Versionierung in allen Carriern,
CHANGELOG, Testplan und dieser Bericht. Dominante Themen des Deltas sind die
Welle W0/W1 des System-Audits (Sicherheits-Slice, RLS-Exit-Evidenz, Workspace-Fence),
die Welle W2 (atomare und verwaissensichere Global-Definition-Propagation,
serialisierte und auditierte Interview-Formalisierung, erzwungene
`expected_version`-Semantik) sowie drei Dokumentationslieferungen
(System-Audit-Plan, Architektur- und Accessibility-Audit).

- **Version:** `1.8.0-beta.16`
- **Tag (geplant, nicht gesetzt):** `v1.8.0-beta.16`
- **Basis-Commit:** `73892571` (`Merge pull request #1073 from
  Popoboxxo/feat/audit-w2-atomicity-concurrency`), voll
  `73892571751ca88b8cdf4d45c5700bab322ae31f`, Commit-Zeit
  `2026-09-26T10:24:14+02:00`
- **Letztes Release:** `v1.8.0-beta.15` = Commit
  `6606b6f0f368e079b6ddb0615514c305b493afdd` (`chore(release): prepare
  v1.8.0-beta.15 (#1048)`), Tag-Objekt
  `90f9106361e7301af63037d68e3a0e772367b266`, Commit-Zeit
  `2026-09-23T22:22:41+02:00`
- **Datumsstempel des Berichts:** 2026-09-26

## 2. Release-Cutoff (exakter Zeitstempel)

Als Cutoff wurde der **exakte Tag-Zeitstempel** von `v1.8.0-beta.15` verwendet
(`2026-09-23T22:22:41+02:00`), kein Kalender-Tagesfilter.

- `git log v1.8.0-beta.15..73892571` → **21 Commits** (davon **15** `--no-merges`,
  **6** Merge-Commits)
- Enthaltene, seit dem Cutoff gemergte **PRs: #1055, #1069, #1070, #1071, #1072,
  #1073** (6 PRs, unten). Jeder der 15 Nicht-Merge-Commits ist einem dieser PRs
  zuzuordnen; es gibt keinen Commit ohne PR-Zuordnung im Delta.

## 3. Enthaltene PRs seit dem Cutoff

| PR | Merge-Commit | Titel (aus `git log`) | Beitrag |
|----|----|------------------------|---------|
| #1055 | `02f72341` | `feat: Bluepencil-Host-Identitätsbrücke` (#1031) | Host-Identitätsbrücke für die Review-Sidecar; Login-Timeout-Ursache wird jetzt durchgereicht (`e3db334a`, `94a3737a`) |
| #1069 | `37b4343c` | `chore: system-audit-2026-09` | System-Audit-Improvement-Plan (`988294b6`), Architektur-Boundary-Audit (`66e21f56`), Frontend-Accessibility-Audit (`e3df119e`) |
| #1070 | `59bcb7a9` | `feat: audit-w0-w1-security` | W0 Evidenz-/Entscheidungs-Baseline + W0/W1 Security-Slice (`82f13395`) |
| #1071 | `acde772e` | `feat: audit-w1-closeout` | W1-Close-out: RLS-Exit-Evidenz, Legacy-API-Key-Inventar, Negativtests (`f85407f7`); Review-Runde mit Workspace-Fence-Härtung (`7012a7c2`) |
| #1072 | `b4db48cc` | `chore: refresh-project-metadata` | Nur `.meta-config/project.yaml` (`22aeae4e`) — **keine** Produktverhaltensänderung |
| #1073 | `73892571` | `feat: audit-w2-atomicity-concurrency` | W2: Workflow-Transition im Row-Lock mit `expected_version` (`6f145c87`), Interview-Formalisierung serialisiert + auditiert (`14fc05e5`), atomare/orphan-sichere Global-Propagation (`d4d912bf`); Doku-Nachtrag `49edead8` |

## 4. Themen-Highlights

- **W0/W1 — Security-Slice (`#1070`, `#1071`):** W0 ist **teilweise** umgesetzt;
  die Evidenz-Baseline und der W0/W1-Slice stehen, die W0-Abschlusskriterien sind
  **nicht** vollständig erfüllt. W1 liefert RLS-Exit-Evidenz, ein strikt
  read-only Management-Command zur Inventarisierung Legacy-API-Keys, actionlint
  auf ein digest-gelistetes Image und Negativtests, die bei Regression einer
  Sicherheitskontrolle fehlschlagen.
  - **Workspace-Fence-Härtung (`7012a7c2`):** die Fence-Regel war `if not
    workspace_ids` — ein Fence aus nicht-kanonischen Einträgen passierte damit als
    leer. Die Entscheidung erfolgt jetzt über kanonischen UUID-Round-Trip.
  - **actionlint** wechselt auf implizite Workflow-Discovery mit
    job-scoped `permissions: contents: read`; `context_graph/tests` ist der
    CI-Matrix beigetreten; die RLS-Exemption-Begründungen wurden ehrlich gemacht.
- **W2 — Atomarität und Nebenläufigkeit (`#1073`):**
  - **CR-08 — `expected_version` wird erzwungen:** zuvor las die View den
    client-gelieferten Revisionsstand und **verwarf ihn stillschweigend**, sodass
    zwei konkurrierende Transitions beide gegen ein veraltetes `current_state`
    validieren konnten und der Verlierer eine nie validierte History-Kante
    schrieb. Validierung und Write teilen sich jetzt einen Lock, `expected_version`
    wird durch `WorkflowFacade.transition` und die REST-/MCP-Aufrufer
    weitergereicht, ein veralteter Revisionsstand ergibt `409` statt eines
    irreführenden `400` (vor dem Fix: `500`).
  - **CR-05/CR-06/CR-07 — Interview-Formalisierung:** der Status-Check lief ohne
    Lock, sodass zwei konkurrierende Aufrufer beide formalisieren konnten.
    `_lock_in_progress_session()` ist jetzt extrahiert und wird vom Single-Pfad
    **und** von `abandon()` genutzt. Single-/Multi-Formalize und `abandon()`
    schreiben ein `AuditEntry`; `abandon()` emittiert ein
    `INTERVIEW_ABANDONED`-Outbox-Event. Ein verschluckter Transition-Pfad loggt
    jetzt eine Warnung und wird als `workflow_transition_applied` erfasst, sodass
    Erfolg und Fehlschlag unterscheidbar bleiben. Migration `0027` (ein
    `AlterField` auf `event_type`, **keine** Datenmigration).
  - **CR-09/CR-10 — Globale Definition:** `_persist()` committete die globale
    Definitionszeile bisher außerhalb der umgebenden Transaktion und propagierte
    erst danach in die abgeleiteten Workspace-Zeilen — ein fehlschlagender
    Propagationsschritt ließ globale und abgeleitete Wahrheit auseinanderlaufen.
    Beides läuft jetzt in **einer** `transaction.atomic()`, belegt per
    Fault-Injection vor und nach dem abgeleiteten Write. Ergänzt um ein
    Fail-closed-`OrphanedStateError`-Gate auf `delete_state` (HTTP `409`,
    `select_for_update` auf der globalen Definition, Rollback ist ein Aufruf,
    kein Schema-Schritt) und eine Provisioning-Reparatur, die kein Live-Item
    verwaissen lässt und jede nicht reparierte Zeile benennt.
- **Dokumentation (`#1069`):** System-Audit-Improvement-Plan,
  Architektur-Boundary-Audit, Frontend-Accessibility-Audit sowie ein datierter
  W0–W2-Implementierungsstatus. Der Statusabschnitt hält ausdrücklich fest, dass
  grüne Tests allein niemals ein Track auf `VERIFIZIERT` setzen.
- **Bluepencil/Auth (`#1055`):** Host-Identitätsbrücke für die Review-Sidecar;
  der Login-Timeout-Fehler behält seine Ursache, auch unter ES2020.

## 5. Versions-Carrier (Delta dieses Commits)

Alle Träger von `1.8.0-beta.15` → `1.8.0-beta.16` (im Arbeitsbaum angewendet:
12 Dateien / 22 Zeilen):

| Carrier | Zeilen |
|---|---|
| `VERSION` | 1 |
| `frontend/package.json` | 1 |
| `frontend/package-lock.json` | 2 |
| `integrations/hermes-plugin/reqogniloom/package.json` | 1 |
| `integrations/hermes-plugin/reqogniloom/hermes-plugin.json` | 1 |
| `integrations/hermes-plugin/reqogniloom/package-lock.json` | 2 |
| `dist/plugins/antigravity/reqogniloom/plugin.json` | 1 |
| `dist/plugins/claude-code/reqogniloom/.claude-plugin/plugin.json` | 1 |
| `.env.example` (Kommentar + `REQOGNILOOM_VERSION`) | 2 |
| `deploy/docker-compose.yml` (5 Image-Tags) | 5 |
| `deploy/docker-compose.minimal.yml` (3 Image-Tags) | 3 |
| `site/index.html` (Badge + Footer) | 2 |
| **Summe** | **22** |

`APP_VERSION` wird beim Build aus `VERSION` gestempelt (`scripts/build.sh`).
`CHANGELOG.md`, dieser Bericht und der neue Testplan sind neu und zählen nicht zu
den 12 Carriern. **Verifiziert:** `git grep "1.8.0-beta.16"` findet 13 Dateien /
27 Vorkommen — die 12 Carrier mit 22 Vorkommen plus 5 Vorkommen in `CHANGELOG.md`.
In den aktiven Carrier-Pfaden (`VERSION`, `frontend/package.json`, `.env.example`,
`deploy/`, `site/`, `dist/`, `integrations/`) existiert **kein** verbliebener
`1.8.0-beta.15`-Treffer.

## 6. Verifikation (lokal)

| Gate | Ergebnis |
|---|---|
| `git grep "1\.8\.0-beta\.16"` | **12 Carrier-Dateien** (22 Vorkommen) + `CHANGELOG.md` (5) — deckungsgleich mit der Carrier-Tabelle |
| Carrier-Konsistenz (`VERSION` == `frontend/package.json` == Hermes-`package.json`/`hermes-plugin.json` == `dist`-Plugins == `.env.example` == Site-Badge == beide Compose-Dateien) | **PASS** (alle `1.8.0-beta.16`) |
| Rest-Treffer `1.8.0-beta.15` in aktiven Carrier-Pfaden | **keine** (PASS) |
| `git diff --check` | **PASS** (Exit 0, keine Whitespace-Fehler) |
| Backend pytest (Volllauf, Test-Service) | **rot** — `9687 passed, 12 skipped, 1 xfailed, 4 errors`, `2017.55s`, Exit `1`. Siehe 6.1 |
| Frontend vitest (Volllauf, Test-Service) | **rot** — `2201 passed, 3 failed` von 2204 in 237 Dateien, Exit `1`. Siehe 6.2 |
| `manage.py check` | **PASS** (0 Issues) |
| `makemigrations --check --dry-run` | **PASS** (keine ausstehenden Änderungen) |
| `docker compose -f deploy/docker-compose.yml config -q` | **PASS** (Exit 0) |
| `docker compose -f deploy/docker-compose.minimal.yml config -q` | **PASS** (Exit 0) |
| Pre-Release-Gate-Dispatcher `.claude/hooks/pre-release-check.sh` | **Exit 0** — `action-pin-validation` real ausgeführt, alle Action-Pins upstream verifiziert; `artifact-freshness` und `docker-image-scan` **Self-Skip** (fehlende Voraussetzungen), nicht als bestanden gezählt |
| `make build` / `scripts/build.sh` | **kein Image** — per Konstruktion ein No-op. Siehe 6.3 |
| Frontend `tsc -p tsconfig.build.json` + Produktions-`vite build` | **PASS** (Exit 0) — maximal erreichbarer QS-Build |

### 6.1 Backend-Red: 4 Errors in `test_mcp_api_key_roles.py`

`9687 passed, 12 skipped, 1 xfailed, 4 errors`, Exit `1`. Alle 4 Errors liegen in
`backend/mcp_server/tests/test_mcp_api_key_roles.py::TestMcpApiKeyRolePropagation`
und sind eine **Live-Stack-Testvoraussetzung**, kein Assertion-Fehler und **kein
Produktdefekt**.

- Das Modul fährt gegen einen echten HTTP-Server (eigenes Docstring), nicht
  gegen Django-Test-Fixtures. `seeded_workspace_id`
  (`test_mcp_api_key_roles.py:277-305`) verlangt einen geseedeten
  `Demo Workspace`.
- **Ursache (verifiziert, korrigiert):** Die Fixture liest ausschließlich
  `data.get("results", [])` (`:296`), also **nur Seite 1** einer Liste, die
  `StandardPagination` mit `PAGE_SIZE: 25` und Sortierung `-modified_at` ausliefert
  (`backend/reqogniloom/settings.py:536-537`). `next(..., None)` (`:298-300`)
  liefert daher `None`, und `assert seeded` (`:301`) schlägt mit der irreführenden
  Meldung `is bootstrap_admin/seed_demo loaded?` fehl.
- **Ausgeschlossen wurde:** eine zuvor behauptete Tenant-Drift. Der Login-JWT der
  Fixture (`_get_bearer_token()`, `:125-146`) erreicht auch den Demo-Tenant
  `7a539397-…`; ein Tenant-Mismatch existiert nicht. Die Behauptung wurde aus dem
  CHANGELOG entfernt.
- **Historie:** als KI-1 dokumentiert in
  `docs/se/reports/RELEASE_v1.8.0-beta.11.md:226-235`, in
  `RELEASE_v1.8.0-beta.12.md:282-285` als „weiterhin vorhanden" bestätigt, geführt
  in `docs/se/reports/KNOWN_TEST_GATE_REDS.md` §2. §2 beschreibt für einen
  *anderen* Lauf die Reds derselben Klasse über das 10-Key-Cap der Dev-DB
  kombiniert mit einem ungeprüften `DELETE` in `_revoke_all_active_keys()`. Beide
  Beschreibungen betreffen eine nicht reproduzierbare, langjährig E2E-mutierte
  Dev-DB; keine davon ist ein Produktdefekt.
- **`seed_demo` / `bootstrap_admin` ändern nichts** (der Workspace existiert
  bereits, wenn vorhanden), und eine **frische Test-DB ist wirkungslos**, weil der
  Test gegen den laufenden Live-Stack geht, nicht gegen die Test-DB.
- **In CI bewusst übersprungen:** `pytestmark` mit
  `pytest.mark.skipif(bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS")))`
  (`:79-90`); der `integration`-Marker ist laut `backend/pyproject.toml:18`
  „nicht Teil der Unit-Suite".
- **Nachweis (selbst gemessen):** gezielter Lauf des Moduls mit `CI=true` →
  `collected 8 items` → `8 skipped`, Exit `0`. Derselbe Lauf ohne `CI=true` →
  `4 passed, 4 errors`, Exit `1`.
- Die Testdatei hat **keinen** Commit in `v1.8.0-beta.15..HEAD`.

### 6.2 Frontend-Red: nicht-deterministische Timeouts in zwei Ratchets

`2201 passed, 3 failed` von 2204 in 237 Dateien (`2 failed | 235 passed`),
Exit `1`. Alle Failures sind `Test timed out in 5000ms` in den
Dateisystem-scanenden Ratchets `design-tokens.test.ts` und
`link-type-consumers.test.ts`.

- **Nichtdeterminismus, gemessen:** derselbe Volllauf lief zweimal und ergab
  einmal **2 Failures in 1 File**, einmal **3 Failures in 2 Files** — gleiche
  Ursache, wechselnde Ausprägung, lastinduziert.
- **Scan-Scope:** die von den Ratchets walkte `.tsx`/`.ts`-Menge wuchs zwischen
  `v1.8.0-beta.15` und dem Basis-Commit von **599 auf 604 Dateien (+0,83 %)**.
  Die Timeouts sind damit **nicht** durch Scan-Wachstum erklärt.
- **Isolierter Lauf mit Default-5000 ms** (ohne `--testTimeout`-Override):
  `19 passed`, Exit `0`, mit `design-tokens.test.ts` bei `4763 ms` — also bereits
  rund 5 % unter dem Default-Budget, weshalb der Volllauf kippt.
- Keine der beiden Dateien und `frontend/src/styles/tokens.css` haben einen
  Commit in `v1.8.0-beta.15..HEAD`.

### 6.3 Release-Build: per Konstruktion ein No-op

`make build` / `scripts/build.sh` erzeugte **kein Image**. Das ist **per
Konstruktion** so und nicht zufällig:

- `deploy/docker-compose.yml` enthält **0 `build:`-Sektionen** und pinnt
  ausschließlich fertige Images (`pgvector/pgvector:pg16`, `redis:7-alpine`,
  `ghcr.io/popoboxxo/reqogniloom-backend:1.8.0-beta.16`,
  `ghcr.io/popoboxxo/reqogniloom-frontend:1.8.0-beta.16`, …).
- Die **5** `build:`-Sektionen liegen im Dev-Overlay
  `deploy/docker-compose.override.yml`, das `scripts/build.sh:80-92`
  **absichtlich ausschließt** (dokumentierter Grund: das Override mergt das
  *Entwicklungs*-Target des Frontends statt des Release-Images, und legacy
  `docker-compose` v1 kann das `!override`-Merge-Tag nicht parsen).
- Das Skript meldet folglich `No services to build`.
- **Kanonischer Release-Build** ist der tag-getriggerte
  `.github/workflows/docker-publish.yml` (`on: push: tags: ['v*.*.*']`,
  `:15-18`) mit fail-closed Trivy-Gate (`severity: CRITICAL,HIGH`,
  `exit-code: '1'`, `ignore-unfixed: true`, `:144-156`); gepusht wird erst nach
  erfolgreichem Scan.
- **Kein Image gebaut ⇒ kein Image-Digest dokumentiert** (analog beta.15).

### 6.4 `make test` ist kein Release-Gate

Nach Projektkonvention ist das **maßgebliche Release-Gate der CI-Lauf auf dem
Release-Basis-Commit**, nicht ein lokales `make test`. Belege: die
lokale Verifikationstabelle des Vor-Releases enthält keine `make test`-Zeile
(`docs/se/reports/RELEASE_v1.8.0-beta.15.md:145-152`);
`docs/se/reports/KNOWN_TEST_GATE_REDS.md:37-38` hält fest, dass das maßgebliche
Gate (CI) von keinem der gelisteten Reds betroffen ist; `Makefile:22-24`
dokumentiert `make test` als Unit- + Integrationstests **ohne** Playwright E2E.
Die lokalen Volllauf-Reds aus 6.1/6.2 werden folglich als bekannte,
nicht-attributierbare Reds geführt — **nicht** als Release-Blocker.

## 7. CI-Gates (maßgebliche Release-Bedingung)

**Gemessen auf dem Release-Basis-Commit `73892571` — GRÜN.**
2 Workflow-Runs auf diesem Commit, 14 Check-Runs, **14/14 Conclusion `success`**,
0 failed, 0 pending.

| Workflow | Run-ID | Status | Conclusion | URL |
|---|---|---|---|---|
| `CI Pipeline` | `36229673123` | `completed` | **`success`** | https://github.com/Popoboxxo/ReqogniLoom/actions/runs/36229673123 |
| `Playwright E2E Tests` | `36229673118` | `completed` | **`success`** | https://github.com/Popoboxxo/ReqogniLoom/actions/runs/36229673118 |

Enthaltene Jobs (alle `success`, Run `36229673123`): `Workflow Lint (actionlint)`,
`Agent Templates & Distribution`, `Hermes IDE Plugin (integrations/hermes-plugin)`,
`Backend Requirements Drift Check`, `lint`, `frontend-test`, `backend-test`
(set-1-core, set-2-api, set-3-mcp, set-4-features), sowie in Run `36229673118`
`e2e (1)`–`e2e (4)`. Legacy-Commit-Statuses: **0** (nur Check-Runs verwendet).

**`ci_green_on_base_commit: true`.**

Die lokalen Reds aus 6.1/6.2 liegen **außerhalb** dieses Gates: das betroffene
Backend-Modul ist in CI per `skipif` übersprungen, und die beiden Frontend-Ratchets
laufen in CI unter anderer Last. Damit ist die bindende Release-Bedingung erfüllt.

## 8. Tag & GitHub-Pre-Release

**NICHT ausgeführt.** Bei diesem Schnitt wurde bewusst **kein Commit, kein Tag und
kein Push** vorgenommen.

| Schritt | Ergebnis |
|---|---|
| Commit des Release-Branches | **nicht ausgeführt** (Auftrag: kein Commit) |
| Annotierter Tag `v1.8.0-beta.16` | **nicht gesetzt** |
| GitHub Pre-Release | **nicht erstellt** |
| `Docker Publish (GHCR)` | **nicht ausgelöst** — der Workflow ist tag-getriggert (`tags: ['v*.*.*']`); ohne Tag kein Publish |
| Image-Digest `1.8.0-beta.16` | **nicht vorhanden** — es wurde kein Image gebaut, deshalb wird hier bewusst **kein** Digest geführt |

## 9. Offene Punkte / Follow-ups

- **W0/W1/W2 sind teilweise umgesetzt; kein Track ist `VERIFIZIERT`.** Die
  vollständige Liste der offenen Punkte steht im CHANGELOG-Abschnitt
  *Known open points* des Schnitts `1.8.0-beta.16` und wird hier nicht dupliziert.
  Kurz: D1-Constraint (bewusst zurückgestellt), Correlation-Feld (**offen**),
  W2-Negativtest 6 (**fehlt vollständig**), CR-13 (**unberührt**), CR-17/CR-22/CR-26
  (**offen**), `pl_user` (**offen**), Service-Wrapper-`expected_version`-Lücke
  (**offen**), Orphan-Gate-Restfenster (**offen**, im Code dokumentiert),
  Error-/Status-Semantik über REST + MCP + **UI** (**nicht** erfüllt — die
  UI-Schicht wurde nicht angefasst), W3/W4/W5 (**nicht begonnen**).
- **REST-Breaking-Change `expected_version` / `If-Match` auf
  `POST /api/v1/<entity>/{id}/transitions/` (CR-08):** Clients, die sich auf das
  frühere stille Ignorieren verlassen, müssen jetzt `409` behandeln. Auf dieser
  Route bezeichnet der Tag den **Workflow-Revisionsstand** (`version`), nicht den
  Entity-ETag, den `If-Match` auf `PATCH` trägt und der mit `412` beantwortet wird.
- **Global-Default-Endpunkte** antworten nun `409`, wenn ein Delete ein Live-Item
  verwaissen würde — Clients dieser Endpunkte müssen das behandeln.
- **`seeded_workspace_id`-Fixture (`test_mcp_api_key_roles.py:277-305`):** liest
  weiterhin nur Seite 1 einer paginierten Liste. Ein echter paginierter Lookup
  fehlt bis heute. Kein Produktdefekt, aber eine Testschwäche.
- **`_revoke_all_active_keys()` (`:154-171`)** prüft die Statuscodes der
  `DELETE`-Aufrufe inzwischen; die Fixture liest Seite 1 weiterhin ohne
  Paginierung.
- **Externer Testplan:** `docs/se/reports/TESTPLAN_v1.8.0-beta.16.md` — **nicht**
  Teil dieses Berichts und **keine** externe Production-/QS-Freigabe.
