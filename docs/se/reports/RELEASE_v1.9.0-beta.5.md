---
type: STRATEGY
scope: release-v1-9-0-beta-5
status: draft
date: 2026-11-20
author_agent: release
---
# Release-Bericht v1.9.0-beta.5

> **Status: Beta-Cut, keine Produktions-, Staging- oder QA-Freigabe.**
> Der Cut bündelt die UI-Korrekturen (#1950, #1952), die
> Vektor-Backend-Abstraktion (#1951), die Vereinheitlichung der Fehlerpfade
> (#1953) und vier verhaltenserhaltende Refaktorierungen (#1954–#1957).
> Push, Tag, PR und GitHub-Release sind **nicht** Teil dieses Cuts.

## 1. Release-Ziel

`v1.9.0-beta.5` ist ein Beta-Cut auf dem Stand von `main` (`a849649a`).
Ziel ist es, die seit `v1.9.0-beta.4` gemergten Arbeits-Packages in einem
nachprüfbaren Versionsschnitt zu bündeln:

- **Bedienbarkeit und A11Y** der bestehenden UI (Anmeldung, Kontrast,
  Übersetzung, Fokus, Tabellen/Pagination) — #1950, #1952;
- **Pluggbare Artefakt-Vektor-Backends** mit Registry, Capabilities und
  administrativer Konfiguration — #1951;
- **Einheitliche Fehlermeldungen** im Frontend — #1953;
- **Strukturelle Refaktorierungen** ohne Verhaltensänderung — #1954–#1957.

Der Cut behauptet **nicht**: einen vollständigen Test- oder Build-Lauf in
diesem Worktree, eine Live-Device-/Screenshot-Abnahme, ein Screenreader-
Sign-off oder eine Freigabe über das Staging-Gate.

## 2. Release-Cutoff und Basis

| Feld | Wert |
|---|---|
| Schnitt-Branch | `release/v1.9.0-beta.5` (von `main` abgezweigt) |
| Basis-Commit (verifiziert) | `a849649a` — Merge PR #1957 (`refactor/requirement-editors`) |
| Direkter Vorgänger | `v1.9.0-beta.4`, Tag auf `75d4b430` (Merge PR #1946), 2026-11-19 19:22:19 +0100 |
| Cutoff (exakt) | Tag `v1.9.0-beta.4` = `75d4b430`; alle nachfolgend gemergten PRs kommen in Frage |
| Changelog-Scope | #1947–#1957 sowie Dependabot-Merges seit dem beta.4-Tag |
| Cut-Datum | 2026-11-20 |

> **Hinweis zum Scope.** Im Bereich `v1.9.0-beta.4..main` liegen zusätzlich
> die Merges #1947 (`53fd586a`), #1948 (`aeccaed7`), #1949 (`5d655b48`) sowie
> eine Reihe von Dependabot-Merges. Sie wurden nachträglich in den
> Changelog-Block `[1.9.0-beta.5]` aufgenommen, damit der Block alle Änderungen
> seit dem beta.4-Tag abdeckt.

## 3. Enthaltene Änderungen

Die Commit-Hashes und Datei-Anzahlen sind im Checkout nachprüfbar
(`git diff --stat <merge>^1 <merge>`).

| PR | Merge-Commit | Umfang (Dateien) | Inhalt |
|---|---|---|---|
| #1950 | `3756247d` | 110 | `fix(ui)`: Login-Fehlerdifferenzierung (401/429/5xx/Netzwerk), Ausstieg aus MFA-Enrollment, Danger-/Primary-Text-Kontrast, Dokument-Sprache, Tab-ARIA, Memory-Erfolgsfeedback/Retry, Entfernung wirkungsloser Honcho-Felder, `VITE_API_BASE_URL`-Default |
| #1951 | `e12dac1b` | 28 | `feat(vector)`: Registry/Capabilities für Artefakt-Vektor-Backends (analog `memory.backends`), `VectorWriteStore`/`VectorRecord` statt Qdrant-im-Indexer, Admin-UI „System Settings → Vektorspeicher" inkl. DB-Override und Diagnostic, Sichtbarkeit des DB-Secret-Status in W003/Health, Migration `0155` |
| #1952 | `0f6d4832` | 54 | `fix(ui)`: `--color-warning-text` in 5 Themes, vollständige Übersetzung von `MismatchReviewTable`, zentraler `toUserErrorMessage`, 404-Seite, Unsaved-Changes-Guard, Fokus-Restore, Login-Banner-Level, Scatter-Legende/Swatch, Tabellen-/Pagination-A11Y, Secret-Status |
| #1953 | `c3ed8773` | 48 | `refactor(ui)`: restliche Fehlerpfade über den gemeinsamen `toUserErrorMessage`-Mapper, mock-sicher, Legacy-Helper gegen Transport-Leaks gehärtet |
| #1954 | `b400ef2b` | 2 | `refactor(tree)`: Tastaturnavigation aus `WorkspaceTree` extrahiert (repowise-Backlog) |
| #1955 | `65041a41` | 1 | `refactor(tree)`: `TreeRow` in Label- und Chrome-Logik geteilt (repowise-Backlog) |
| #1956 | `22975fe9` | 3 | `refactor(reviews)`: Bulk-Confirm-Flow aus `ReviewsView` extrahiert (repowise-Backlog) |
| #1957 | `a849649a` | 2 | `refactor(requirements)`: page-level Dialoge aus `RequirementEditors` extrahiert (repowise-Backlog) |

**Keine Breaking Changes.** Die vier Refaktorierungen sind verhaltensgleich;
die UI-Korrekturen ändern keine API- oder Datenverträge. #1951 führt ein
neues Datenmodell (Migration `0155`) und eine optionale Backend-Abstraktion
ein, ohne bestehende Vektorpfade zu entfernen.

## 4. Versions-Carrier

Alle Carrier wurden über das kanonische
`python3 scripts/bump_version.py --version 1.9.0-beta.5` strukturell gesetzt
(JSON-Pointer / Compose-Default-Regex, nicht per Freitext-Ersetzung), danach
wurden die Client-Artefakte neu gerendert. Alter Stand überall
`1.9.0-beta.4`.

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

**Gesamt:** 20 Dateien durch den Bump, eine weitere durch den CHANGELOG
(21 im Diff), zuzüglich dieses Berichts. Der Bumper lief mit **exit 0**; der
Carrier-Ratchet meldet 12 Sources / 13 Version-Locations / 2 unabhängige
POC-Manifeste konsistent, `clients/render.py --check` meldet 18 Artefakte
aktuell (2 neu geschrieben, 16 unverändert).

**Keine veraltete Versionsnummer im Diff:** eine Suche nach
`1\.9\.0-beta\.4` in getrackten Dateien außerhalb des CHANGELOG und dieses
Berichts liefert keine Treffer. Bewusst nicht angefasst (wie bereits in
beta.4 dokumentiert): `.meta-config/project.yaml` nennt weiterhin
„Stand VERSION 1.9.0-beta.2"; kein Gate prüft diese Textzeile.

## 5. Changelog

`CHANGELOG.md` erhält den Block `## [1.9.0-beta.5] — 2026-11-20` direkt
unter `## [Unreleased]` (Englisch, Keep a Changelog) mit den Kategorien
`Added`, `Changed`, `Fixed`. Referenzen: #1950–#1957. Keine
`**Breaking:**`-Kennzeichnung, keine Roh-Commit-Liste.

## 6. Upgrade-Hinweise und offene Punkte

### 6.1 Migration

Migration `0155` (`0155_system_artifact_vector_settings`) gehört zu #1951
und ist im Cut enthalten. Sie wurde in diesem Worktree **nicht** ausgeführt;
ein Deployment muss den usual Migrationsschritt durchlaufen.

### 6.2 Verhaltensänderungen

Keine API-Brüche. Die Admin-Oberfläche erhält einen neuen Bereich
„Vektorspeicher"; die Vektor-Schreibpfade laufen über die neue
`VectorWriteStore`-Abstraktion. Die UI-Änderungen sind Fehler-/A11Y-
Korrekturen, keine neuen Workflows.

### 6.3 Staging-Gate

Wie in beta.4 dokumentiert, bleibt die GHCR-Publikation über das
Staging-Gate mangels `required_reviewers` fail-closed blockiert. Dieser Cut
umgeht das nicht und nimmt keine Freigabe vor.

## 7. Verifikation

> **Herkunft der Nachweise.** Der Carrier-Bump und die beiden Release-Gates
> wurden in diesem Cut lokal ausgeführt. Ein vollständiger Testlauf, ein
> Build und CI-Ergebnisse wurden **nicht** neu gemessen und werden daher
> nicht behauptet.

| Gate | Befehl / Quelle | Ergebnis |
|---|---|---|
| Voller Bump (lokal gemessen) | `python3 scripts/bump_version.py --version 1.9.0-beta.5` | **exit 0** — Carrier gesetzt, Clients gerendert, Ratchet + `render --check` grün |
| Carrier-Ratchet (lokal gemessen) | `python3 scripts/check_plugin_packages.py --expect-version 1.9.0-beta.5` | **OK** — 12 Sources, 13 Version-Locations, 2 POC-Manifeste |
| Client-Artefakte (lokal gemessen) | `python3 scripts/clients/render.py --check` | **OK** — 18 Artefakte aktuell (2 geschrieben, 16 unverändert) |
| Pre-Release-Gate-Hook | `Glob **/pre-release-check.sh` | **kein Hook vorhanden** — rein additiv, kein Gate konfiguriert |
| Backend-/Frontend-Tests | — | in diesem Cut **nicht ausgeführt** |
| Build / Image | — | in diesem Cut **nicht ausgeführt** |
| Whitespace | `git diff --check` | vorbestehender Hard-Break in `docs/CODEBASE_OVERVIEW.md:4` (siehe Abschnitt 8) |

## 8. Risiken und Residuen

- **Keine Tests im Cut.** `make test-backend` und `make test-frontend`
  wurden nicht ausgeführt; die Aussage „Tests grün" ist hier nicht
  belegt. Vor dem eigentlichen Release müssen die Tests laufen.
- **Kein Build im Cut.** Es wurde kein Artefakt gebaut; die
  Artefakt↔Commit-Kopplung ist für diesen Cut noch nicht erfüllt.
- **Staging-Gate weiterhin rot** (Abschnitt 6.3): Publishing bleibt
  blockiert; der Image-Build wurde nicht geprüft.
- **`git diff --check`**: `docs/CODEBASE_OVERVIEW.md:4` enthält einen
  vorbestehenden trailing-whitespace-Hard-Break
  (`> **Stand:** …  `), den der Bumper unverändert übernimmt. Bewusst
  **nicht** manuell korrigiert — kein Bestandteil dieses Cuts.
- **project.yaml-Inkonsistenz** siehe Abschnitt 4 — kein Gate, aber
  reviewpflichtig.

## 9. Nächste Schritte (nicht Teil dieses Cuts)

1. Review dieses Branches, dann Release-PR gegen `main` (Aufgabe des
   `git`-Agenten).
2. Nach grünen Tests und `make build`: Tag `v1.9.0-beta.5` auf den
   Release-Commit — kein Re-Tag nach dem Push.
3. GitHub-**Pre-Release** markieren, nicht `latest`; Notizen aus dem
   CHANGELOG-Block `[1.9.0-beta.5]`.
4. Migration `0155` im Deployment ausführen.

---

*Erstellt durch den `release`-Agenten am 2026-11-20. Interne Doku
(Deutsch), keine Secrets. Lokal gemessen: Bump exit 0 und die beiden
Release-Gates. Keine Tests, kein Build, kein Push/Tag/PR/Release durch
den Autor.*
