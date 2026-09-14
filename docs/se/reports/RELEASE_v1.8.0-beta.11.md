---
type: STRATEGY
scope: Release v1.8.0-beta.11
status: done
date: 2026-09-14
author_agent: release
---

# Release-Bericht v1.8.0-beta.11

## 1. Release-Ziel

Release des Beta-Release `v1.8.0-beta.11` (Vorbereitung auf dem Branch
`chore/release-v1.8.0-beta.11`, Abschluss auf `main`). Dieser Bericht
dokumentiert die **Vorbereitungsphase** (Versionierung, Changelog,
Release-Bericht, Neubau der generierten Manifeste, ein Commit) **und** den
**Abschluss** (gestempelter Build, Pre-Release-Gates inkl. Abweichung,
FF-Merge, Tag, GitHub-Pre-Release, CI-Gates auf dem Tag-Commit). Das Release
ist **abgeschlossen und verifiziert** (siehe Abschnitte 5 und 10).

- **Version:** `1.8.0-beta.11`
- **Tag (geplant):** `v1.8.0-beta.11`
- **Basis-Commit:** `f12949e2` (`Merge pull request #945`), Branch-HEAD
- **Letztes Release:** `v1.8.0-beta.10` = `b4c3a910`, Commit-Zeit
  `2026-09-11 20:44:59 +0200` (= `2026-09-11T18:44:59Z`)
- **Datumsstempel des Berichts:** 2026-09-14

## 2. Release-Cutoff (exakter Zeitstempel)

Gemäß §2 der Projekt-Extension (`.claude/3-project/ReqLo-release-ext.md`) wurde
als Cutoff der **exakte Tag-Zeitstempel** von `v1.8.0-beta.10`
(`2026-09-11T18:44:59Z`) verwendet — **kein Kalender-Tagesfilter**. Die
Änderungsmenge wurde aus `git log v1.8.0-beta.10..HEAD` (71 Commits) sowie
`gh pr list --base main --state merged --search "merged:>2026-09-11T18:44:59Z"`
ermittelt.

## 3. Enthaltene PRs seit dem Cutoff

| PR | Merged (UTC) | Titel |
|----|--------------|-------|
| #945 | 2026-09-14T14:34:02Z | feat(attributes): complete Attribut-System v3 WS1-WS7 (#934) |
| #943 | 2026-09-12T22:14:36Z | docs(attribute): attribute-system v3 specification |
| #933 | 2026-09-12T12:22:01Z | fix: close B1 API-contract & B4 embeddings bugfix bundles |
| #931 | 2026-09-11T23:04:08Z | docs(se): 3-Stufen-Attributmodell + Migrationssystematik + Verifikationsprotokoll |
| #910 | 2026-09-11T19:31:48Z | fix(e2e): stabilize visual-regression snapshots against CI drift |

**Hinweis zur Zuordnung:** Klammer-Nummern in Commit-Messages (z. B. `#935`,
`#936`, `#912`, `#864`) sind **Issue-Referenzen**, keine PR-Nummern. Die sechs
Issue-Titel wurden verifiziert (`gh issue view`) und im CHANGELOG als reine
`#NNN`-Referenzen geführt; die PR-Präfixe wurden ausschließlich gegen die
bestätigte Merge-Liste vergeben.

## 4. Themen-Highlights

- **Attribute System v3 (Hauptthema):** Rollout des Attribut-Systems v3 über
  WS1–WS7 — Transport-Parität REST/MCP und `ArtifactAttributeGateway` (#935),
  Identität & Systemfelder inkl. `Actor` (#936), Display-Engine (#937),
  12-Spalten-Layout-Engine (#938), zentraler Attribut-Katalog (#942),
  AWMS-Werte-Migration (#940) und 3-Stufen-Rollout (#939). Spezifikation,
  ADR-004 und Stufenmodell wurden dokumentiert (#931, #943).
- **Preset-Fix aus beta.10-QA:** `mandatory_fields` werden nun pro
  Item-Typ-Definition aufgelöst, statt als flache Workspace-Liste (#912).
- **B1-API-Contract- & B4-Embedding-Bundle (#933):** u. a. `test_type` im
  TestCase-Create (#864), Trace-Link-Picker-Deduplizierung (#832),
  `relevance_score`-Normalisierung (#827), env-konfigurierbare
  Embedding-Dimension (#826), Lazy-Embedding (#847), Celery-Beat-Heartbeat
  (#822), Honcho-Embedding-Config (#911).
- **E2E-Stabilität:** Stabilisierung der Visual-Regression-Snapshots gegen
  CI-Drift (#910).

## 5. Test- und Gate-Status

### 5.1 Maßgebliches Test-Gate: CI auf `f12949e2`

Gemäß User-Entscheidung **„Option A"** gilt **CI-Grün auf `f12949e2`**
(PR #945) als maßgebliches Test-Gate: **26/26 Checks grün**, u. a.
`set-1`…`set-4` (Backend-Matrix), `frontend-test`, `e2e (1..4)`, `lint`,
`agent-templates-test`, `requirements-drift-check` und `hermes-plugin-test`.

### 5.2 Lokaler Test-Gate-Lauf (ergänzend, nicht maßgeblich)

| Prüfung | Ergebnis |
|---------|----------|
| Backend-Volllauf (`backend-test`, pytest) | **7973 passed, 11 skipped, 0 failed, 4 setup-errors** — Exit 1, Gesamtdauer ~26 min |
| Frontend-Volllauf (`frontend-test`, vitest) | **1851 passed / 1 failed (1852)**, 220 Files — Exit 1; Fehler = `Test timed out in 5000ms` |
| `pytest docs/agent-templates dist` | **15 passed** |
| Hermes-Plugin `npm test` | **71 passed** (6 Files) |

Die zwei lokalen Reds (4 Backend-Fixture-Setup-Errors, 1 Frontend-Flake-Timeout)
sind belegt **nicht-produktbezogen** und blockieren den Release gemäß Option A
nicht; Details, Root-Causes und Folge-Fix-Vorschläge in Abschnitt 9
(KI-1/KI-2).

### 5.3 Nachgelagerte Gates

| Prüfung | Status |
|---------|--------|
| Gestempelter Build (`APP_VERSION=1.8.0-beta.11`, `GIT_COMMIT_SHA=884e65b6…`, `BUILD_TIME=2026-09-14T15:35:17Z`) | **erfolgreich** (verifiziert via `docker image inspect .Config.Env`; siehe §10.1) |
| `pre-release-check.sh` (Pre-Release-Gates) | **Exit 1 — Abweichung**; kein Gate real geprüft (Host-/Deployment-Defekt, siehe §5.4) |
| Docker-Image-/Trivy-Gate (Extension §1b) | **PASS** in CI `docker-publish` (Run `34866205914`) |
| Tag-Push + GitHub-Release (Extension §3 Step 2) | **erfolgt** (annotierter Tag + Pre-Release; siehe §10.2/§10.3) |

### 5.4 Gate-Abweichung (Pre-Release-Gates)

Der Pre-Release-Gate-Dispatcher wurde ausgeführt und **mit Exit 1 abgebrochen**.
Nach Einordnung durch den User (**keine** substanzielle Beanstandung, sondern
Host-/Deployment-Defekt) wurde das Release gemäß User-Entscheidung **Option C′**
fortgesetzt; die Abweichung wird hier vollständig dokumentiert.

**Symptom** — `bash .claude/hooks/pre-release-check.sh` → Exit 1:

```
.claude/hooks/pre-release-check.sh: line 45: set: pipefail: invalid option name
.claude/hooks/pre-release-check.sh: line 48: cd: $'/mnt/c/Repositories/ai-native-reqflow-POC\r': No such file or directory
```

**Root Cause:** Die sync-deployten Hook-Skripte sind **CRLF**-kodiert
(`.claude/hooks/**`, byte-identisch auch `.agents/hooks/**`). Das `\r` hängt
sich an `PROJECT_ROOT` → `cd` scheitert in Zeile 48, **bevor** die
Gate-Schleife überhaupt beginnt. Ursache der CRLF-Kodierung: `.claude/hooks/**`
ist **gitignored** (`.gitignore:26`), daher greift `.gitattributes`
(`*.sh text eol=lf`) nicht — die Regel gilt nur für **getrackte** Dateien. Das
Deployment (agent-meta `sync.py`) schreibt auf Windows CRLF.

**Wirkung:** **Kein Gate hat real geprüft.** Zusätzlich self-skippen alle drei
Gates substanziell:

- `artifact-freshness` — keine `.agent-meta/generated-artifacts.yaml` vorhanden.
- `docker-image-scan` — kein `Dockerfile` im Repo-Root, kein `trivy`.
- `action-pin-validation` — `gh` fehlt im WSL-`bash`-PATH.

Der Dispatcher scheitert dabei **fail-closed** — es gibt keinen stillen Bypass.

**Substanzielle Nachholung:** Die Gate-Logik von `action-pin-validation` wurde
im Host-Kontext mit authentifiziertem `gh 2.100.0` ausgeführt → **10/10 Pins
vorhanden (PASS)**. Zusätzlich wurde die Regex-Blindstelle geprüft:
`github/codeql-action/upload-sarif@v4` wird von der Gate-Regex nie extrahiert
(Subpath) → manuell verifiziert, Tag existiert (Exit 0). Der Defekt ist in
Issue **#949** dokumentiert.

**Integritätsprüfung:** Nach LF-Normalisierung stimmen die Gate-Hashes exakt
mit `.sha256-checksums` überein; im CRLF-Working-Tree greift der Check
konservativ falsch (`no checksum entry`).

**Einordnung/Entscheidung:** Kein substanzieller Gate-Befund, sondern
Host-/Deployment-Defekt → Release gemäß User-Entscheidung **Option C′**
fortgesetzt. Fix: Issue **#948** (upstream agent-meta: Hook-Skripte beim
Deployment LF-erzwingen + CRLF-Guard).

**Das substanzielle CVE-Gate** läuft in `docker-publish.yml` (Trivy,
`severity CRITICAL,HIGH`, `exit-code: '1'`, `ignore-unfixed: true`) **vor** dem
GHCR-Push — und hat bestanden (siehe §10.4).

## 6. Dokumentierte Konvention-Abweichungen

1. **Provider-Abweichung bei der Projekt-Extension:** Der release-Agent
   referenziert `.opencode/3-project/ReqLo-release-ext.md`; diese Datei
   **existiert im Repository nicht**. Angewendet wurde stattdessen die
   Quelldatei `.claude/3-project/ReqLo-release-ext.md` (identischer Inhalt,
   dort selbst referenziert von `.claude/agents/release.md`). Die
   `.opencode`-Ausprägung fehlt und sollte perspektivisch nachgezogen werden,
   damit die Extension provider-agnostisch greift.

2. **Frontend-Versions-Drift trotz `VERSION_DIST_BEHAVIOUR` Punkt 2:**
   `frontend/package.json` (und die entsprechenden Felder in
   `frontend/package-lock.json`) standen seit jeher auf `1.0.0`; auch der
   beta.10-Bump hat sie **nicht** angehoben, obwohl
   `.meta-config/project.yaml` → `variables.VERSION_DIST_BEHAVIOUR` Punkt 2
   fordert, dass beide Dateien exakt übereinstimmen. Für beta.11 wurde der
   **Sync durchgeführt** (`VERSION` + `package.json` + `package-lock.json`
   auf `1.8.0-beta.11`). Dies weicht bewusst von der historischen Praxis ab
   und ist im CHANGELOG unter „Changed“ vermerkt.

3. **Fehlender Report in früheren Beta-Releases:** Frühere Beta-Releases
   (`v1.8.0-beta.1` … `v1.8.0-beta.10`) haben **keinen** Bericht unter
   `docs/se/reports/` angelegt — der Verzeichnisbestand enthielt zuvor nur
   `test_quality_audit_report.md` und `deep_audit/*`. Dieser Bericht
   etabliert das Format erstmalig; eine rückwirkende Ergänzung ist nicht
   vorgesehen.

## 7. Geänderte / erzeugte Dateien

- `VERSION` → `1.8.0-beta.11`
- `frontend/package.json`, `frontend/package-lock.json` → Versionsfelder
- `CHANGELOG.md` → neuer Abschnitt `[1.8.0-beta.11] — 2026-09-14`
- `docs/se/reports/RELEASE_v1.8.0-beta.11.md` (dieser Bericht, neu)
- Regenerierte Manifeste (VERSION-Embedding, Extension §1a):
  `dist/plugins/claude-code/reqogniloom/.claude-plugin/plugin.json`,
  `dist/plugins/antigravity/reqogniloom/plugin.json`,
  `integrations/hermes-plugin/reqogniloom/package.json`,
  `integrations/hermes-plugin/reqogniloom/hermes-plugin.json`

## 8. Folge-Arbeiten (nach dem Release)

Das Release `v1.8.0-beta.11` ist **abgeschlossen und verifiziert** (siehe
Abschnitt 10). Alle zuvor beauftragten nachgelagerten Schritte sind erledigt:

1. Backend-/Frontend-Volllauf — **erfolgt** (Ergebnisse in Abschnitt 5.2).
2. Gestempelter Build — **erfolgreich** (Abschnitt 10.1).
3. Pre-Release-Gates (`pre-release-check.sh`) — **ausgeführt, Abweichung**
   (Host-/Deployment-Defekt, Abschnitt 5.4).
4. Tag-Push + GitHub-Pre-Release `v1.8.0-beta.11` — **erfolgt**
   (Abschnitte 10.2/10.3).

**Offene Folge-Arbeiten:**

- **#948** — CRLF-Hook-Deployment (upstream agent-meta: Hook-Skripte beim
  Deployment LF-erzwingen + CRLF-Guard).
- **#949** — Gate-Regex: Subpath-Pins (`github/codeql-action/upload-sarif@v4`)
  werden nicht extrahiert.
- **Optional:** Branch-Cleanup `chore/release-v1.8.0-beta.11` (vollständig
  gemergt → Löschkandidat, **nur nach expliziter Freigabe**).
- **Optional:** Test-Härtung **C1**/**C2** aus KI-1/KI-2 (Abschnitt 9).

## 9. Known Issues (lokales Test-Gate)

Beide Befunde sind **nicht-produktbezogen** (User-Entscheidung „Option A"); das
maßgebliche Gate (CI auf `f12949e2`, 26/26 grün) ist davon unberührt. Sie werden
hier inkl. Root-Cause, Evidenz und vorgeschlagenem Folge-Fix dokumentiert.

### KI-1 — Backend: 4 Fixture-Setup-Errors in `mcp_server/tests/test_mcp_api_key_roles.py`

- **Klasse:** `TestMcpApiKeyRolePropagation`
- **Symptom:** `AssertionError: Seeded 'Demo Workspace' not found — is
  bootstrap_admin/seed_demo loaded?`
- **Root Cause (verifiziert):** Der Endpoint `GET /api/v1/workspaces/` ist
  paginiert (`StandardPagination`, `page_size 25`, `max_page_size 100`) und
  serverseitig nach `-modified_at` sortiert. Im `demo`-Tenant liegen 153
  Workspaces, davon 152 frische E2E-Reste (`e2e-isolated-*`,
  `e2e-visual-regression-*`). `Demo Workspace` (`6d20f0b9-…`) hat
  `modified_at = 2026-09-10` ⇒ **Rang 152 von 153**. Die Fixture
  `seeded_workspace_id` (Zeilen ~250–264) liest nur `results` **von Seite 1**
  ⇒ Name nie gefunden. Die Assertion-Meldung ist irreführend; das Seeding ist
  intakt (Admin im Tenant `demo`, `UserRole(role='admin')` in
  `Demo Workspace` vorhanden, Workspace nicht soft-deleted).
- **Einordnung:** **kein Produktdefekt.** Der Test ist
  `pytest.mark.integration` und in CI explizit geskippt
  (`skipif(CI or GITHUB_ACTIONS)`); der Modul-Docstring nennt ihn ausdrücklich
  „must not run unattended in the normal unit suite". Er lief lokal nur, weil
  der Dev-Stack erreichbar war.
- **Vorgeschlagener Folge-Fix (C1):** Fixture auf paginierte Suche umstellen
  (alle Seiten via `next` bzw. `page_size=100` durchlaufen, bis
  `name == "Demo Workspace"` gefunden ist; DRF-404 auf Out-of-range-Seiten
  abfangen). Betrifft nur `backend/mcp_server/tests/test_mcp_api_key_roles.py`.
- **Reinigungsoption (separat, nicht Teil dieses Releases):** die
  E2E-Rest-Workspaces per `cleanup_e2e_artifacts` entfernen (DB-mutierend,
  braucht explizite Freigabe).

### KI-2 — Frontend: Flake-Timeout in `src/test/design-tokens.test.ts`

- **Symptom:** `Error: Test timed out in 5000ms` in einem der beiden
  Dateisystem-Scan-Tests („every var(--token) reference …" bzw. „every
  structural inline-style exemption …") — **kein** Assertion-/Token-Mismatch.
- **Root Cause (verifiziert, nicht-deterministisch):** Beide Scan-Tests laufen
  isoliert in ~2,7 s gegen ein 5-s-Budget; unter Volllast (220 Test-Files
  parallel) kippt jeweils einer darüber. Im Re-Run schlug ein **anderer** der
  beiden Tests fehl ⇒ load-induzierter Timeout, kein Token-Defekt. Isolierter
  Lauf: 6/6 grün, Exit 0.
- **Einordnung:** **kein Produktdefekt**; CI auf `f12949e2` war für
  `frontend-test` grün.
- **Vorgeschlagener Folge-Fix (C2):** per-File `testTimeout` erhöhen oder die
  beiden Scan-Tests in ein serialisiertes/non-parallel Projekt verschieben.

## 10. Release-Ergebnis

Das Release ist **abgeschlossen und verifiziert**. Alle Angaben wurden auf dem
Tag-Commit `884e65b6` (`884e65b6ab9e7a4a503426593b97a96a69d2f90f`) geprüft.

### 10.1 Build (gestempelt)

- **`APP_VERSION`** = `1.8.0-beta.11`
- **`GIT_COMMIT_SHA`** = `884e65b6ab9e7a4a503426593b97a96a69d2f90f`
- **`BUILD_TIME`** = `2026-09-14T15:35:17Z`
- Verifiziert via `docker image inspect .Config.Env`.

**Hinweis zum Build-Weg:** `make build` bzw. `bash scripts/build.sh` ist auf
diesem Host **nicht lauffähig** (kein `make`; WSL-`bash` ohne
Docker-Integration) → äquivalenter **gestempelter Compose-Build** über
`deploy/docker-compose.yml` + `deploy/docker-compose.override.yml` mit den drei
`--build-arg`-Werten. `deploy/docker-compose.yml` hat **keine
`build:`-Sektionen** (nur Registry-`image:`); die Build-Kontexte stammen aus
dem Overlay.

### 10.2 Merge und Tag

- **FF-Merge:** `chore/release-v1.8.0-beta.11` → `main` per **Fast-Forward**
  (`f12949e2..884e65b6`), **kein** Merge-Commit; `main` gepusht.
- **Tag:** annotiert `v1.8.0-beta.11`, Tag-Objekt
  `263140f045817eaad40c80d18224b3c10f7ceda7` → Commit
  `884e65b6ab9e7a4a503426593b97a96a69d2f90f`, gepusht (in `ls-remote`
  vorhanden, inkl. Peel `^{}`).

### 10.3 GitHub-Release

- **Pre-Release** `v1.8.0-beta.11` erstellt (Titel = bare Tag,
  `isPrerelease: true`, `isDraft: false`; Notes = CHANGELOG-Abschnitt
  `[1.8.0-beta.11]`, `--verify-tag` → Tag unverändert).
- **URL:** https://github.com/Popoboxxo/ReqogniLoom/releases/tag/v1.8.0-beta.11

### 10.4 CI-Gates auf `884e65b6`

| Workflow | Run | Ergebnis |
|----------|-----|----------|
| `docker-publish` | `34866205914` | **success** (≈8 min; beide Matrix-Jobs `backend`+`frontend` grün, **Trivy-Gate bestanden**, GHCR-Push erfolgt) |
| „CI Pipeline" | `34866189148` | **success** |
| „Playwright E2E Tests" | `34866189110` | **success** |

- GHCR-Tags `1.8.0-beta.11` für `reqogniloom-backend` und
  `reqogniloom-frontend` vorhanden; `latest` bewusst **nicht** verschoben =
  korrektes Prerelease-Verhalten.

### 10.5 Operativer Hinweis

Der Auto-Release-Hook (`auto-github-release.sh`, PostToolUse/Bash,
Claude-Code-Hook) lief in dieser Runtime **nicht** → das GitHub-Release musste
manuell per `gh release create` angelegt werden.
