---
type: STRATEGY
scope: release-v1-9-0-beta-6
status: draft
date: 2026-11-24
author_agent: release
---
# Release-Bericht v1.9.0-beta.6

> **Status: Beta-Cut (Draft).** kein Prod-/Staging-/QA-Freigabe, kein Push/Tag/GitHub-Release in diesem Cut.
> Der Cut bündelt die Merges #2054–#2060: zwei Bugfix-Wellen (20 bzw. 44 Issues),
> die Client-/MCP-Vertragsbereinigung, den Sweep vom 21.11 (#1959, #1977,
> #1985, #2012), die RBAC-Matrix für #1731, den Null-UUID-Fix im Frontend und
> die Erweiterung der Smoke-Suite von 3 auf 47 echte Browser-Checks.
> Push, Tag, PR und GitHub-Release sind **nicht** Teil dieses Cuts.

## 1. Release-Ziel

`v1.9.0-beta.6` ist ein Beta-Cut auf dem Stand von `main` (`39f4ca89`,
Dokumentations-Commit vom 2026-11-24; letzter Funktions-Merge `5659c1ad`,
PR #2060). Ziel ist es, die seit `v1.9.0-beta.5` gemergten Arbeits-Packages in
einem nachprüfbaren Versionsschnitt zu bündeln:

- **Bugfix-Wellen** — 20 Issues in Welle 1 (#2054) und 44 Issues in Welle 2
  (#2055), über MCP-Routing, Interview-/Tool-Policy, Service-, REST- und
  Frontend-Schichten sowie CI/Test-Stabilität;
- **Vertragsbereinigung** — Client- und MCP-Kontrakte, Admin-Tier für
  tenant-weite Audit-Lesezugriffe, Interview-TestCase-Provenienz (#2056);
- **21.11-Sweep** — #1959, #1977, #1985, #2012 (#2057);
- **RBAC-Beleg für #1731** — Rechte-Matrix für API-Key-Credential-Endpunkte,
  test-only (#2058);
- **Null-UUID-Fix** —workspace-scoped First-Load-Requests werden an die echte
  Workspace-Identität statt an den Lade-Status gebunden (#2059);
- **Smoke-Suite** — Ausbau von 3 auf 47 echte Browser-Checks mit gemeinsamem
  Setup und vier neuen Spec-Dateien (#2060).

Der Cut behauptet **nicht**: einen vollständigen Testlauf, eine
Live-Device-/Screenshot-Abnahme oder eine Freigabe über ein Staging-Gate. Der
lokale Build ist in 6.3 mit Metadaten und Digests belegt.

## 2. Release-Cutoff und Basis

| Feld | Wert |
|---|---|
| Schnitt-Branch | `release/v1.9.0-beta.6` (von `main` abgezweigt) |
| Basis-Commit (verifiziert) | `39f4ca89` — docs(plan): exhaustive UI E2E testing masterplan; letzter Merge `5659c1ad` (PR #2060) |
| Direkter Vorgänger | `v1.9.0-beta.5`, Tag auf `d000094f` (Merge PR #1958), 2026-11-20 23:11:50 +0100 |
| Cutoff (exakt) | Tag `v1.9.0-beta.5` = `d000094f`; alle nachfolgend gemergten PRs kommen in Frage |
| Changelog-Scope | #2054–#2060 inklusive; 20 Issue-Fixes Welle 1, 44 Issue-Fixes Welle 2, 4 Sweep-Fixes vom 21.11, #1731, Null-UUID-Fix, Smoke-Erweiterung 3 → 47 |
| Cut-Datum | 2026-11-24 |

> **Hinweis zum Scope.** Der Vergleich `v1.9.0-beta.5..HEAD` umfasst 379
> geänderte Dateien (42.458 insertions / 5.133 deletions), darunter auch
> Vorarbeiten und Dokumentation außerhalb der oben genannten PRs. Der
> Changelog-Block beschränkt sich auf die ausdrücklich genannten PRs #2054–
> #2060 und die zugehörigen Issue-Fixes.

## 3. Enthaltene Änderungen

Die Commit-Hashes und Datei-Anzahlen sind im Checkout nachprüfbar
(`git diff --stat <merge>^1 <merge>`).

| PR | Merge-Commit | Umfang (Dateien) | Inhalt |
|---|---|---|---|
| #2054 | `2ba9f8fb` | 95 | `fix(mcp)`: erste Welle offener Issues — MCP-Routing, Group-Tools, Bulk-Freeze, Interview-Protokoll/Roundtrip, Tool-Policy-Klassifikation (`submit_for_review` als Write), CI-Test-Stack, Doku-/Testzahlen |
| #2055 | `7dd74a16` | 190 | `fix`: zweite Welle — 44 Bug-Issues über Backend-Services, REST-Serializer/Views, MCP-Registry/Schema, Frontend-Prompt-Einstellungen/Navigation, Client-Artefakte und Test-Mounts |
| #2056 | `7a3ea4b2` | 30 | `fix(clients, mcp)`: Base-URL-Normalisierung vor `/mcp/`, Admin-Tier für tenant-weite Audit-Reads (#2034), Interview-TestCase-Provenienz aus `session_kind` (#2044), Tool-Beschreibungen (#1999, #1979, #2034), OpenCode 2.3.x als unverifiziert markiert |
| #2057 | `f4b4bd33` | 29 | `fix`: Sweep vom 21.11 — strukturierte Akzeptanzkriterien autoritativ (#1959), autoritative Embedding-Drift-Meldung in Health (#1977), VCRM schließt outdated Items aus (#1985), MCP-Transport-Retry-Vertrag dokumentiert (#2012) |
| #2058 | `705d8bf2` | 1 | `test(api-keys)`: RBAC-Credential-Matrix für #1731 — Viewer verwalten nur eigene Keys (fremder PK → 404), Write-Tier-Keys bleiben durch Creator-Rechte begrenzt, `/users/` und `/permission-defaults/` bleiben Admin-only; test-only, keine Produktionsverhaltensänderung |
| #2059 | `914f74a9` | 14 | `fix(frontend)`: Null-UUID — First-Load-Requests für Preferences/Locks an die echte Workspace-ID statt an `isLoadingWorkspace` binden; Platzhalter-ID-Prädikat für das Auth-Restore-/Offline-Fenster, Vitest-Regressionen für transienten und aufgelösten Zustand |
| #2060 | `5659c1ad` | 7 | `feat(e2e)`: Smoke-Suite von 3 auf 47 echte Browser-Checks erweitert — gemeinsames Session-Setup, Core-Flows, Domain-Routes, Requirements sowie Settings-/Dialog-Checks; E2E-Spec-Zahl auf 79 korrigiert |

**Keine geplante Breaking-Change-Kennzeichnung.** Die Änderungen sind
Bugfixes, Vertragsbereinigungen, Tests und Dokumentation. #2056 zieht
Audit-Lesezugriffe auf den Admin-Tier, #2057 ändert die Autorität bei
Akzeptanzkriterien und den VCRM-Default — diese Verhaltensänderungen sind in
Abschnitt 6.2 vermerkt.

## 4. Versions-Carrier

Der Versionsstand wurde von `1.9.0-beta.5` auf `1.9.0-beta.6` gehoben. Die
Carrier sind im Arbeitsbaum bereits strukturell gesetzt; der Bump betrifft
20 Dateien:

| Datei | Stellen |
|---|---|
| `VERSION` | 1 |
| `frontend/package.json` / `frontend/package-lock.json` | 1 / 2 |
| `.env.example` | 2 |
| `deploy/docker-compose.yml` / `deploy/docker-compose.minimal.yml` | 6 / 3 |
| `server.json` | 1 |
| `.claude-plugin/marketplace.json` | 2 |
| `dist/npm/reqogniloom-opencode/package.json` | 1 |
| `dist/plugins/claude-code/…/plugin.json` / `dist/plugins/antigravity/…/plugin.json` | je 1 |
| `integrations/hermes-plugin/reqogniloom/package.json` / `package-lock.json` / `hermes-plugin.json` | 1 / 2 / 1 |
| `site/index.html` | 2 |
| `docs/CODEBASE_OVERVIEW.md` | 6 |
| `docs/api/MCP-SURFACE.md` | 5 |
| `systemagents/reqogniloom-operator.md` | 2 |
| `docs/clients/hermes.md`, `hermes.de.md` | je 1 (generiert) |

Zusätzlich wurden die reinen Zustandsangaben in `docs/plans/index.md` und
`.meta-config/project.yaml` (drei Zeilen) von `1.9.0-beta.2` auf
`1.9.0-beta.6` gezogen. Historische Beispielversionen (etwa
`1.8.0-beta.28`), Zählwerte und Test-Erwartungen bleiben unangetastet.

## 5. Changelog

`CHANGELOG.md` erhält den Block `## [1.9.0-beta.6] — 2026-11-24` direkt
unter `## [Unreleased]` (Englisch, Keep a Changelog) mit den Kategorien
`Added`, `Changed` und `Fixed`. Referenzen: #2054–#2060 sowie die
Issue-Wellen und der 21.11-Sweep. Keine Roh-Commit-Liste, keine Änderung an
historischen Blöcken.

## 6. Upgrade-Hinweise und offene Punkte

### 6.1 Migration

Im Scope liegen fünf Migrationen: `admin_ops/0008` (Export-Snapshot-Metadaten),
`attribute_definitions/0012` (Interview-Felder) und `0013`
(Architektur-Interview-Parent) aus den Wellen 1/2 sowie
`persistence/0110` (Security-Definer-Owner-Rolle) und `0156`
(Embedding-Drift-Definer-Funktion) aus dem 21.11-Sweep. Sie wurden in diesem
Worktree **nicht** ausgeführt; ein Deployment muss den üblichen
Migrationsschritt durchlaufen.

### 6.2 Verhaltensänderungen

Keine API-Brüche im Sinne einer Migrationspflicht für Clients, aber zwei
bewusste Verhaltensänderungen: tenant-weite Audit-Lesezugriffe erfordern den
Admin-Tier (#2034 in #2056), und strukturierte Akzeptanzkriterien sind
autoritativ (#1959 in #2057); der VCRM schließt outdated Items per Default
aus (#1985). Der Null-UUID-Fix verhindert workspace-scoped First-Load-Requests
während der Auth-Wiederherstellung (#2059).

### 6.3 Build / Image-Tags

**Lokal gebaut (exit 0), nicht publiziert.** `./scripts/build.sh` lief am
2026-11-24 mit exit 0; Log: `/tmp/opencode/build-beta6.log`. Build-Argumente:
`APP_VERSION=1.9.0-beta.6`,
`GIT_COMMIT_SHA=39f4ca891f03eee62c6e5480cd6bb4b71528b302` (Stand zum
Build-Zeitpunkt; die Release-Commits waren noch nicht gemacht),
`BUILD_TIME=2026-11-24T20:16:12Z`.

| Image | Digest | Größe |
|---|---|---|
| `ghcr.io/popoboxxo/reqogniloom-backend:1.9.0-beta.6` | `sha256:49a3e07298fd16dea5510bca287a02ac17ec34d733ff781c409cc9c0e776b21c` | 3,23 GB |
| `ghcr.io/popoboxxo/reqogniloom-frontend:1.9.0-beta.6` | `sha256:6e42e8d7b0b7c6553f6ecd84e76f5a23a559519b245478e9a139b89bfc48a2f9` | 140 MB |

Die Backend-Metadaten (`APP_VERSION`, `GIT_COMMIT_SHA`, `BUILD_TIME`) speist
`GET /api/v1/version/`. Die Production-Stage des Frontends war vollständig
layer-gecached, der Tag wurde frisch gesetzt; bewusst enthält das Frontend
keine Version-Metadaten.

**Kein Push, kein Publish, kein Tag, kein Merge, kein Commit.** Die GHCR-
Publikation bleibt `.github/workflows/docker-publish.yml` beim Push eines
Version-Tags vorbehalten. Da `GIT_COMMIT_SHA` noch auf den Stand vor den
Release-Commits zeigt, ist die Artefakt↔Tag-Kopplung erst nach einem erneuten
Build auf den finalen Release-Commit erfüllt.

### 6.4 Freigabe- und Staging-Gate

kein Prod-/Staging-/QA-Freigabe, kein Push/Tag/GitHub-Release in diesem Cut.
Ein Pre-Release-Gate-Hook ist im Repo vorhanden (`.agent-meta/hooks/…
/pre-release-check.sh`), wurde für diesen Dokumentations-Cut aber nicht
ausgeführt; er ist vor einem echten Release zu betreiben.

## 7. Verifikation

> **Herkunft der Nachweise.** Der Carrier-Bump und die beiden Release-Gates
> wurden vor diesem Cut lokal ausgeführt, der Build mit exit 0 in diesem Cut.
> Ein vollständiger Testlauf wurde **nicht** neu gemessen und wird daher
> nicht behauptet.

| Gate | Befehl / Quelle | Ergebnis |
|---|---|---|
| Carrier-Ratchet (lokal gemessen) | `python3 scripts/check_plugin_packages.py --expect-version 1.9.0-beta.6` | **PASS** |
| Client-Artefakte (lokal gemessen) | `python3 scripts/clients/render.py --check` | **PASS** |
| Index-Freshness (lokal gemessen) | `python3 -m pytest scripts/tests/test_doc_index_freshness.py -q` | **2 passed** — beide Indexe verlinken alle Seiten; der neue Release-Report liegt nicht im Geltungsbereich des Tests |
| Pre-Release-Gate-Hook | `.agent-meta/hooks/1-generic/pre-release-check.sh` | vorhanden, in diesem Cut **nicht ausgeführt** |
| Backend-/Frontend-Tests | — | in diesem Cut **nicht ausgeführt** |
| Build / Image (lokal gemessen) | `./scripts/build.sh`, Log `/tmp/opencode/build-beta6.log` | **exit 0** — `1.9.0-beta.6` auf `39f4ca89`, Build-Zeit `2026-11-24T20:16:12Z`; Backend-/Frontend-Digests und Größen in 6.3, nichts publiziert |

## 8. Risiken und Residuen

- **Keine vollständigen Tests im Cut.** `make test-backend` und
  `make test-frontend` wurden nicht ausgeführt; „Tests grün" ist hier nicht
  belegt. Vor dem eigentlichen Release müssen die Suiten laufen.
- **Lokaler Build ohne Publikation.** Artefakte sind gebaut (6.3), aber nicht
  gepusht oder publiziert; `GIT_COMMIT_SHA` zeigt auf den Stand vor den
  Release-Commits, die Kopplung an den finalen Tag steht noch aus.
- **Release-Gates vor dem Push wiederholen.** Die zwei hier dokumentierten
  Gates sind grün; ein echter Release-Cut muss sie erneut gegen den finalen
  Commit ausführen.
- **Zustandsangaben in Docs/Meta.** Die drei `project.yaml`-Zeilen und der
  Plans-Index wurden gezielt korrigiert; weitere historische Stand-Angaben
  (z. B. in Audit- und Archivdokumenten) sind bewusst nicht angefasst.
- **Keine Freigabe.** Prod/Staging/QA sind nicht freigegeben; es gibt keinen
  Push, kein Tag und kein GitHub-Release in diesem Cut.

## 9. Nächste Schritte (nicht Teil dieses Cuts)

1. Review dieses Branches, dann Release-PR gegen `main` (Aufgabe des
   `git`-Agenten).
2. Nach grünen Tests und Pre-Release-Gate den Build auf den finalen
   Release-Commit wiederholen (damit `GIT_COMMIT_SHA` auf den Tag-Commit
   zeigt), dann Tag `v1.9.0-beta.6` — kein Re-Tag nach dem Push.
3. GitHub-**Pre-Release** markieren, nicht `latest`; Notizen aus dem
   CHANGELOG-Block `[1.9.0-beta.6]`.
4. Migrationen aus 6.1 im Deployment ausführen und die aus 6.3 belegten
   Image-Digests bei der GHCR-Publikation verwenden.

---

*Erstellt durch den `release`-Agenten am 2026-11-24. Interne Doku
(Deutsch), keine Secrets. Lokal gemessen: die beiden Release-Gates und die
Index-Freshness sowie des lokalen Builds (exit 0). Keine vollständigen
Tests, kein Push/Tag/PR/Release, keine Publikation durch den Autor.*
