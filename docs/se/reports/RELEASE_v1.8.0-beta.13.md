---
type: STRATEGY
scope: Release v1.8.0-beta.13
status: done
date: 2026-09-20
author_agent: release
---

# Release-Bericht v1.8.0-beta.13

## 1. Release-Ziel

Vorbereitung des Beta-Release `v1.8.0-beta.13` auf dem Branch
`chore/release-v1.8.0-beta.13` (Basis: `main`). Dieser Bericht dokumentiert
Vorbereitung **und** Auslieferung: Versionierung in allen Carriern, CHANGELOG,
dieser Bericht, Merge, Tag, GitHub-Pre-Release und der gestempelte
Docker-Publish-Lauf (Abschnitte 7–9).

- **Version:** `1.8.0-beta.13`
- **Tag (geplant):** `v1.8.0-beta.13`
- **Basis-Commit:** `5a03160a` (`fix(deploy): … (#918) (#1015)`), voll
  `5a03160a0e224f2b1fa6d971ca734c9926458939`, Commit-Zeit
  `2026-09-20T17:42:22+02:00`
- **Letztes Release:** `v1.8.0-beta.12` = Commit `53ba83d2`
  (`chore(release): prepare v1.8.0-beta.12`), Tag-Objekt `9c85d503`,
  **Tag-Zeit** `2026-09-18T14:24:41+02:00`
- **Datumsstempel des Berichts:** 2026-09-20

## 2. Release-Cutoff (exakter Zeitstempel)

Als Cutoff wurde der **exakte Tag-Zeitstempel** von `v1.8.0-beta.12` verwendet
(`2026-09-18T14:24:41+02:00` = `2026-09-18T12:24:41Z`), kein Kalender-Tagesfilter.

- `git log v1.8.0-beta.12..5a03160a --no-merges` → **22 Commits**
- Enthaltene, seit dem Cutoff gemergte PRs: **#976 – #1015** (unten)

## 3. Enthaltene PRs seit dem Cutoff

| PR | Titel |
|----|-------|
| #976 | docs(release): finalize v1.8.0-beta.12 release report |
| #978 | docs(release): correct KI-3 wording and cross-reference in report |
| #979 | feat(site): add interactive GitHub Pages one-pager |
| #992 | fix(ui): make the notification popover dismissible (#985) |
| #993 | docs(ui): record I-10 outcome and correct an audit misjudgement |
| #995 | fix(ui): surface the change-reason refusal at the field, prove the three surfaces share one state |
| #996 | fix: resolve beta.12 QA bug bundle across api, health, ui, bluepencil |
| #997 | test(e2e): harden state-dependent and flaky Playwright specs (#947) |
| #998 | feat(ui): unify requirement trace links, derive labels, allocation |
| #999 | feat(ui): apply the control standard to workspace settings (#986) |
| #1000 | feat(mcp): filter and compact the tool catalogue (#866) |
| #1001 | feat(mcp): add coverage, VCRM and SE-auditor tools (#410) |
| #1004 | feat(reqif): separate external ReqIF identity from the local uid (#1003) |
| #1005 | feat: auto-generate local readable uid for artifacts (#932) |
| #1008 | fix: store admin backups gzip-compressed (.json.gz) (#823) |
| #1009 | feat: make the default trace link type configurable via env (#989) |
| #1010 | feat: add satisfies/realizes/refines to the built-in link catalog (#950) |
| #1011 | fix(ui): show readable uid in Needs and Architecture trees (#932) |
| #1012 | feat(awms): add deprecate_attribute, export_scope and import_scope (#930) |
| #1013 | feat(awms): backfill the local uid on pre-#932 rows via value_strategy=sequence (#932) |
| #1014 | feat: add rationale and source to Requirement (#871, #583) |
| #1015 | fix(deploy): env docs, image tag, redis persistence, bluepencil marking (#918) |

## 4. Themen-Highlights

- **Lesbare `uid` über alle Artefakte (#932, PRs #1005/#1011/#1013):** Acht
  Modelle dokumentierten eine „auto-generated" `uid`, die nie erzeugt wurde.
  Ein monotoner `UidSequence`-Zähler vergibt jetzt `{PREFIX}-{NNN}` je
  `(workspace, item_type)` — atomar gegen den bestehenden Unique-Constraint,
  nicht recycelnd. Ein mitgeschickter Wert wird mit `400` beantwortet statt
  still verworfen, die acht `help_text` sind korrigiert, der Needs-/Architecture-
  Baum zeigt die `uid` (Kurz-Hash nur noch Fallback), und ein AWMS-Plan
  (`value_strategy: sequence`) versorgt Bestandszeilen.
- **ReqIF-Identität getrennt (#1003, PR #1004):** externe ReqIF-Identität auf
  eigenen `Artifact.reqif_*`-Feldern mit partiellen Unique-Constraints; Import
  matcht darauf, Export bevorzugt den gespeicherten Identifier → Round-Trip
  erhält beide Identitäten.
- **INCOSE/IEEE-29148-Attribute (#871/#583, PR #1014):** `rationale` und
  `source` sind echte Modellspalten und durchgängig verdrahtet; `owner`/
  `priority` bleiben Artifact-Systemfelder, `acceptance_criteria`/
  `verification_method` bleiben ab `standard` stage-mandatory.
- **Trace-Katalog vervollständigt (#950, PR #1010):** `satisfies` (coverage-
  relevante Requirement→Goal-Validierungskante), `realizes` und `refines`
  als Built-ins; Migration `0008` seedet sie je Tenant.
- **AWMS-Katalog komplett (#930, PR #1012):** `deprecate_attribute`,
  `export_scope`, `import_scope` laufen über die eine Engine.
- **Deployment-Robustheit (#918, PR #1015):** Image-Default war vier Betas alt,
  `.env.example` um die fehlenden Ops-Variablen ergänzt (u. a.
  `CSRF_COOKIE_SECURE`), `redis` mit Named Volume für das aktivierte AOF,
  `bluepencil` überall als Debug/QS-only markiert.
- **MCP** (`#410`, `#866`, PRs #1001/#1000), **UI** (`#985`/#992, `#986`/#999,
  `#998`), **Admin-Backups gzip** (`#823`, PR #1008), **E2E-Härtung**
  (`#947`, PR #997).

## 5. Versions-Carrier (Delta dieses Commits)

Alle Träger von `1.8.0-beta.12` → `1.8.0-beta.13`:

| Carrier | Vorkommen |
|---|---|
| `VERSION` | 1 |
| `frontend/package.json` / `frontend/package-lock.json` | 1 / 2 |
| `integrations/hermes-plugin/reqogniloom/{package.json, hermes-plugin.json, package-lock.json}` | 1 / 1 / 2 |
| `dist/plugins/antigravity/reqogniloom/plugin.json`, `dist/plugins/claude-code/reqogniloom/.claude-plugin/plugin.json` | 1 / 1 |
| `.env.example` (`REQOGNILOOM_VERSION` + Kommentar) | 2 |
| `deploy/docker-compose.yml` / `deploy/docker-compose.minimal.yml` | 5 / 3 |
| `site/index.html` (Badge + Footer) | 2 |
| `CHANGELOG.md`, dieser Bericht | neu |

`APP_VERSION` wird beim Build aus `VERSION` gestempelt (`scripts/build.sh`).

## 6. Verifikation (lokal)

| Gate | Ergebnis |
|---|---|
| `git grep 1.8.0-beta.12` in getrackten Carriern | **leer** (nur historische `docs/`-Treffer verbleiben) |
| `docker compose -f deploy/docker-compose.yml config -q` | **PASS** |
| `docker compose -f deploy/docker-compose.minimal.yml config -q` | **PASS** |
| Carrier-Konsistenz (`VERSION` == `frontend/package.json` == compose-Default == `.env.example`) | **PASS** |

## 7. CI-Gates

| Gate | Ergebnis |
|---|---|
| Vorbereitungs-PR **#1016** (`chore/release-v1.8.0-beta.13`) | **13/13 grün** (0 fail), inkl. backend set-1..4, e2e 1–4, frontend-test, lint, Agent-Templates/`dist`, Hermes-Plugin |

## 8. Tag & GitHub-Pre-Release

| Schritt | Ergebnis |
|---|---|
| Merge PR #1016 → `main` | Commit `f73646ed` (`chore(release): prepare v1.8.0-beta.13 (#1016)`), Commit-Zeit `2026-09-20T18:18:50+02:00` |
| Annotierter Tag `v1.8.0-beta.13` (Tag-Objekt `517bda37`) | gesetzt auf `f73646ed`, **Tag-Zeit `2026-09-20T18:19:59+02:00`** |
| GitHub **Pre-Release** | https://github.com/Popoboxxo/ReqogniLoom/releases/tag/v1.8.0-beta.13 (`prerelease=true`) |
| `Docker Publish (GHCR)` Run `35522377259` | **success** (`2026-09-20T16:20:02Z` → `2026-09-20T16:25:44Z`); baut/pusht `ghcr.io/popoboxxo/reqogniloom-backend:1.8.0-beta.13` und `…-frontend:1.8.0-beta.13` |

## 9. Nachtrag (Auslieferung)

Abgeschlossen. `APP_VERSION` wird beim gestempelten Build aus `VERSION`
(`1.8.0-beta.13`) gesetzt; die GHCR-Tags `1.8.0-beta.13` sind veröffentlicht.
Ein Rollback auf `v1.8.0-beta.12` ist über den Tag + die Compose-Variable
`REQOGNILOOM_VERSION` möglich.
