---
type: STRATEGY
scope: Release v1.8.0-beta.15
status: in-progress
date: 2026-09-23
author_agent: release
---

# Release-Bericht v1.8.0-beta.15

## 1. Release-Ziel

Vorbereitung des Beta-Release `v1.8.0-beta.15` auf dem Branch
`chore/release-v1.8.0-beta.15` (Basis: `main`). Dieser Bericht dokumentiert die
Vorbereitung in diesem Branch: Versionierung in allen Carriern, CHANGELOG,
Testplan und dieser Bericht. Auslieferung (Merge, Tag, GitHub-Pre-Release,
GHCR-Publish) erfolgt durch den Release-Owner **nach** dem Merge und wird hier
nachgetragen (Abschnitte 7–9, Status `in-progress`). Dominante Themen des Deltas
sind SE-Vollständigkeit/Validation als gleichwertige Säule (#1035), Audit-Waivers
(#1037) und die vollständige Inline-Style→CSS-Module-Migration (#876, PRs
#1040–#1047).

- **Version:** `1.8.0-beta.15`
- **Tag (geplant):** `v1.8.0-beta.15`
- **Basis-Commit:** `851955ec` (`refactor(frontend): migrate last 37 inline-style
  carriers (#876) (#1047)`), voll
  `851955ec3ce2c7dd4c40de05a05e1ca2102b2756`, Commit-Zeit
  `2026-09-23T21:17:32+02:00`
- **Letztes Release:** `v1.8.0-beta.14` = Commit `e11140d6`
  (`release: v1.8.0-beta.14 test plan for external testers + release prep
  (#1028)`), Tag-Objekt `1e7fef63`, **Tag-Zeit** `2026-09-21T10:56:35+02:00`
- **Datumsstempel des Berichts:** 2026-09-23

## 2. Release-Cutoff (exakter Zeitstempel)

Als Cutoff wurde der **exakte Tag-Zeitstempel** von `v1.8.0-beta.14` verwendet
(`2026-09-21T10:56:35+02:00` = `2026-09-21T08:56:35Z`), kein Kalender-Tagesfilter.

- `git log v1.8.0-beta.14..851955ec --no-merges` → **18 Commits**
- Enthaltene, seit dem Cutoff gemergte **PRs: #1029, #1030, #1032, #1033, #1034,
  #1035, #1036, #1037, #1038, #1039, #1040, #1041, #1042, #1043, #1044, #1045,
  #1046, #1047** (18 PRs, unten). Alle 18 Commits sind Squash-Merges ihrer PRs
  (kein commit ohne PR, kein Merge-Commit im Delta).

## 3. Enthaltene PRs seit dem Cutoff

| PR | Titel (aus `git log`) | Beitrag |
|----|------------------------|---------|
| #1029 | `fix(deploy): align embedding dimensions in image deployments (#1019, #1018)` | Embedding-Dimensionen im Image-Deployment + `/health/`-Signal |
| #1030 | `fix(traceability): stop TRACE-P1 going silent on a cyclic hierarchy (#1021)` | TRACE-P1 bei zyklischer Hierarchie |
| #1032 | `fix(bluepencil): re-vendor browser assets to alpha.2 (vendoring only)` | Bluepencil-Re-Vendoring (`#988`) |
| #1033 | `fix(frontend): accessible trace-link dropdown, token migration (#318, #876)` | Barrierefreies Trace-Link-Dropdown |
| #1034 | `chore(e2e): hardening, reseed path, tenant predicate guards (#947, #433)` | E2E-Härtung + tenant_id-Regressionstest |
| #1035 | `feat(se): validation as a first-class pillar — testcase provenance, goal rules, baseline drift` | Validation-Säule (`#399/#402/#424/#272`) |
| #1036 | `chore: ignore frontend build artifacts in git` | Build-Artefakte ignoriert |
| #1037 | `feat(se): audit finding suppression/waivers (#569)` | SE-Auditor Waivers/Suppression |
| #1038 | `fix(seed): bootstrap attrs in seed_demo + harden idempotency` | `seed_demo`-Attribute + Idempotenz (`#39`) |
| #1039 | `feat(frontend): add empty-state create guidance (#27, #28, #29)` | Empty-State-Anleitung |
| #1040 | `feat(frontend): enforce no static inline style objects in JSX` | ESLint-Gate `no-static-inline-style` (`#876` Option C) |
| #1041 | `refactor(frontend): migrate TestRuns inline styles to CSS modules` | Inline-Style-Migration Etappe 1 |
| #1042 | `refactor(frontend): migrate BaselinesView/ArtifactDiff inline styles` | Inline-Style-Migration Etappe 2 |
| #1043 | `refactor(frontend): migrate 4 components' inline styles to CSS modules` | Inline-Style-Migration Etappe 3 |
| #1044 | `refactor(frontend): migrate 5 components to CSS modules` | Inline-Style-Migration Etappe 4 |
| #1045 | `refactor(frontend): migrate 8 components to CSS modules (#876)` | Inline-Style-Migration Etappe 5 |
| #1046 | `refactor(frontend): migrate 12 components to CSS modules (#876)` | Inline-Style-Migration Etappe 6 |
| #1047 | `refactor(frontend): migrate last 37 inline-style carriers (#876)` | Inline-Style-Migration Etappe 7 (Abschluss) |

## 4. Themen-Highlights

- **Validation als gleichwertige Säule (PR #1035; #399/#402/#424/#272):**
  - **TestCase-Provenienz:** `origin` (`manual` | `ai_generated`) und `reviewed`
    sind echte Felder; `reviewed` ist ausschließlich über
    `POST /api/v1/testcases/{id}/review/` schreibbar (nicht über den
    Serializer-PATCH). Ein gemeinsames Prädikat
    `counts_as_verification_evidence` lässt Coverage, Precondition-Regel 6 und
    VERIF-P8 einen ungeprüften AI-TestCase **ignorieren** — ein AI-Entwurf kann
    damit kein falsches Grün mehr erzeugen. Die Produzenten P3 (MCP-Derive) und
    P4 (Interview-Formalisierung) markieren ihre Zeilen als
    `ai_generated`/`unreviewed`.
  - **Goal-Regeln:** `Workspace.goals_enabled` defaultet jetzt auf `True`; die
    Extended-only-Regel VAL-P1 verlangt, dass jedes aktive StakeholderNeed
    mindestens ein aktives Goal erfüllt. Doppelt gegated (`goals_enabled` +
    mindestens ein aktives Goal) und **advisory** — sie kann einen
    Baseline-Build nie blockieren.
  - **Baseline-Drift:** Ein Edit an einem baselined Artefakt wird nicht mehr
    blockiert, sondern als Drift im Audit-Eintrag festgehalten. Sichtbar über
    `GET /api/v1/artifacts/{id}/baseline-membership/`, ein additives
    `baseline_drift`-Summary und eine `affected_item_ids`-Vorbelegung im
    Change-Request.
  - **Abschluss-Rest (#272):** `verification_method` im Extended-Approval-Gate,
    Ablehnung manueller Trace-Links auf soft-gelöschte Endpunkte, Coverage-Report
    (`GET /api/v1/requirements/coverage-report/`) mit `pending_ai_review` und
    `scenario_kind`.
- **SE-Auditor Waivers/Suppression (PR #1037; #569):** stabile
  Finding-Identität (`finding_key`), `BaselineGateWaiver`-Entität mit optionalem
  `expires_at` (Migration `0009`), scope-aware Matching mit Decision-Time-Expiry.
  REST: `POST`/`GET /api/v1/workspaces/<id>/audit/waivers/` plus strikter
  `include_suppressed`-Parameter auf `GET .../audit/`. MCP: `audit.waive_finding`
  (write, ADMIN-Tier) und `audit.waivers` (read, Approval-Authority) mit den
  dedizierten Fehlercodes `-32008`/`-32009`/`-32010`. UI: dritte Aktion *Waive*
  (Begründung Pflicht), Show-Suppressed-Filter, Suppressed-Badge und ein
  Waivers-Panel, das abgelaufene von aktiven Waivers unterscheidet.
- **Frontend-Integrität (#876, PRs #1040–#1047):** Neue ESLint-Regel
  `local/no-static-inline-style` (error) schloss die Lücke, die Farbregel und
  `STYLE_BRACE`-Ratchet offen ließen. Sieben Etappen migrierten danach **alle**
  verbleibenden Inline-Style-Träger auf CSS-Module; `STYLE_BRACE_BASELINE`
  705 → 3 (rein kommentarhaft) und die Exemption-Liste 70 → 0 — die Regel
  bewacht jetzt ganz `src`.
- **Deploy/Robustheit:** Embedding-Dimensionen im Image-Deployment (#1029;
  `#1018/#1019`) inkl. `/health/`-Spiegelung; E2E-Härtung + tenant_id-Guard
  (#1034; `#947/#433`); `seed_demo` bootstrappt Attribute-Definitions
  idempotent (#1038; `#39`); Build-Artefakte ignoriert (#1036).
- **UI/UX:** barrierefreies Trace-Link-Dropdown mit Token-Migration (#1033;
  `#318/#876`) und Empty-State-Anleitung (#1039; `#27/#28/#29`).
- **Bluepencil:** Browser-Assets auf `alpha.2` re-vendored, ausschließlich
  Vendoring und SHA-256-gepinnt (#1032; `#988`).

## 5. Versions-Carrier (Delta dieses Commits)

Alle Träger von `1.8.0-beta.14` → `1.8.0-beta.15` (im Arbeitsbaum angewendet:
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
den 12 Carriern.

## 6. Verifikation (lokal)

| Gate | Ergebnis |
|---|---|
| `git grep "1.8.0-beta.15"` | **12 Carrier-Dateien** (22 Vorkommen) + `CHANGELOG.md` — deckungsgleich mit der Carrier-Tabelle |
| `git grep "1.8.0-beta.14"` | **nur historische Treffer**: `CHANGELOG.md` (beta.14-Abschnitt), `docs/se/reports/RELEASE_v1.8.0-beta.14.md`, `docs/se/reports/TESTPLAN_v1.8.0-beta.14.md`, `docs/superpowers/plans/index.md` — kein aktiver Carrier mehr auf `beta.14` |
| Carrier-Konsistenz (`VERSION` == `frontend/package.json` == Hermes-`package.json`/`hermes-plugin.json` == `dist`-Plugins == `.env.example` == Site-Badge) | **PASS** (alle `1.8.0-beta.15`) |
| `docker compose -f deploy/docker-compose.yml config -q` | **PASS** (Exit 0) |
| `docker compose -f deploy/docker-compose.minimal.yml config -q` | **PASS** (Exit 0) |
| Pre-Release-Gate-Hook `.claude/hooks/pre-release-check.sh` (Dispatcher v3.1.0) | **Exit 0** — Details siehe unten |

### 6.1 Pre-Release-Gate-Ergebnis (Exit 0)

Der Gate-Dispatcher wurde vor dem Versionsbump ausgeführt. **Wichtig:** Die
deployte Kopie unter `.claude/hooks/` hat **CRLF**-Zeilenenden und scheitert
unter Linux-Bash sofort (`$'\r': command not found`, `set: pipefail: invalid
option name`, danach `cd: '…\r': No such file or directory` → **Exit 1**). Das
ist ein Umgebungsartefakt (Windows-Checkout einer von `sync.py` deployten,
gitignorierten Datei), kein Gate-Fehler. Die SHA-256-Integritätsprüfung belegt
das: die im Manifest registrierten Hashes sind die **LF**-normalisierten Hashes
(z. B. `action-pin-validation.sh` → `2b7500046fdf6bb4…`, identisch mit
`.meta-config/generated-file-hashes.json`), während die CRLF-Version auf der
Platte `1588bf734ecb0750…` ergibt.

Ausgeführt wurde daher eine LF-normalisierte Kopie der Gate-Kette (Checksums
über die normalisierten Gates neu berechnet — die Integritätsprüfung lief damit
**echt** und bestand):

| Gate | Ergebnis |
|---|---|
| `action-pin-validation` | **PASS** — 13 distinkte Action-Pins in `.github/workflows/*.yml` gegen Upstream verifiziert (`gh` via Windows-Shim, da `gh` nicht im WSL-PATH lag) |
| `artifact-freshness` | **[SKIP]** — kein `.agent-meta/generated-artifacts.yaml` (opt-in nicht konfiguriert) |
| `docker-image-scan` | **[SKIP]** — kein `Dockerfile` im Repo-Root (Default `PRE_RELEASE_DOCKERFILE_PATH=Dockerfile`; real liegen `backend/Dockerfile` und `frontend/Dockerfile`); `trivy` ist zudem nicht installiert |
| **Dispatcher** | **`RESULT: all release gates passed` — Exit 0** |

Die beiden Skips sind **Self-Skips des Gate-Vertrags** (fehlende Voraussetzung),
keine Fehlschläge. Sie werden hier ehrlich als „nicht gelaufen" ausgewiesen und
**nicht** als bestandene Prüfung gezählt.

## 7. CI-Gates

> **Nach Merge nachzutragen.** Dieser Abschnitt wird vom Release-Owner mit den
> realen Ergebnissen des Vorbereitungs-PR gefüllt; die Werte unten sind die zu
> erwartenden Gates, nicht die gemessenen.

| Gate | Ergebnis |
|---|---|
| Conventional-Commits-Check | nach Merge nachzutragen |
| Backend pytest (`backend-test` set-1..4) | nach Merge nachzutragen |
| Frontend vitest (`frontend-test`) | nach Merge nachzutragen |
| E2E (`e2e` 1..4, Playwright/Chromium) | nach Merge nachzutragen |
| Lint | nach Merge nachzutragen |
| Agent-Templates / `dist` / Hermes-Plugin | nach Merge nachzutragen |
| Docker-Build (`docker-publish`) | nach Merge nachzutragen |
| Vorbereitungs-PR `chore/release-v1.8.0-beta.15` | nach Merge nachzutragen |

## 8. Tag & GitHub-Pre-Release

> **Nach Merge nachzutragen.** In diesem Branch **nicht** ausgeführt (siehe
> Abschnitt 9).

| Schritt | Ergebnis |
|---|---|
| Merge des Vorbereitungs-PR → `main` | nach Merge nachzutragen |
| Annotierter Tag `v1.8.0-beta.15` | nach Merge nachzutragen |
| GitHub **Pre-Release** (`prerelease=true`) | nach Merge nachzutragen |
| `Docker Publish (GHCR)` — `…-backend:1.8.0-beta.15` + `…-frontend:1.8.0-beta.15` | nach Merge nachzutragen |

## 9. Nachtrag (Auslieferung)

**In diesem Branch NICHT ausgeliefert.** Tag `v1.8.0-beta.15`, GitHub
Pre-Release (`prerelease=true`) und der GHCR-Publish der Images
`1.8.0-beta.15` (backend + frontend) werden vom Release-Owner **nach dem Merge**
dieses Vorbereitungs-PR durchgeführt und anschließend in Abschnitt 7 und 8
nachgetragen. Dieser Bericht steht daher auf `status: in-progress`.

Vorbereitet und verifiziert ist alles, was ohne Merge möglich ist: Carrier-Bump
(12 Dateien / 22 Zeilen), CHANGELOG, Testplan, dieser Bericht, beide
Compose-Validierungen und der Pre-Release-Gate-Lauf (Exit 0).

### Bekannte Punkte / Follow-ups

- **`.env.example` (Zeile 314) benennt das MCP-Tool `memory_forget`
  (Unterstrich), während der reale Tool-Name `memory.forget` (Punkt) lautet.**
  Rein dokumentarischer Defekt; bereits im beta.14-Bericht als nicht-blockierender
  Follow-up geführt und **in diesem Branch nicht behoben** — weiterhin offen.
- **Vorbestehende, out-of-scope `tsc`-Fehler** in `DiagramCreateForm.tsx:88` und
  `MermaidEditor.test.tsx:117` (im PR #1047 als pre-existing/out-of-scope
  ausgewiesen). Kein Release-Blocker, da Lint und vitest grün sind.
- **Externer Testplan:** Der manuelle Testplan zu diesem Release liegt als
  `docs/se/reports/TESTPLAN_v1.8.0-beta.15.md` und ist nicht Teil dieses
  Berichts.
- **Gate-Ausführung unter Windows:** Der CRLF-Zustand der deployten Hook-Dateien
  ist ein Umgebungsartefakt; für reproduzierbare Gate-Läufe unter Linux ist die
  LF-Normalisierung nötig (siehe §6.1).
