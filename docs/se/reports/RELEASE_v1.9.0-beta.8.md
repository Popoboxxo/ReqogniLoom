---
type: STRATEGY
scope: release-v1-9-0-beta-8
status: released
date: 2026-11-26
author_agent: release
---
# Release-Bericht v1.9.0-beta.8

> **Status: Korrektur-Release.** `v1.9.0-beta.7` wurde getaggt, aber nie
> veröffentlicht: zwei repository-weite CI-Gates waren am Tag-Commit rot, weil
> der Feature-Branch vor dem Tag nie durch CI gelaufen war. Dieser Cut trägt
> denselben Funktionsumfang plus die drei Fixes, die die Pipeline grün machen.
> Der Tag `v1.9.0-beta.7` bleibt unverändert (kein Re-Tag, kein Force-Push).

## 1. Release-Ziel

`v1.9.0-beta.8` ist ein Korrektur-Cut auf Basis des korrigierten `main`. Er
liefert:

- **unverändert** den Funktionsumfang von `1.9.0-beta.7`: Dokument-Lese-/
  Bearbeitungsmodus mit serverseitig aufgelöster Schreibfähigkeit,
  Workflow-Management für `Document` und `WorkItem`, globaler
  Workflow-Defaults-Editor mit der MCP-Gruppe `workflow_default`
  (313 Tools in 50 Gruppen-Präfixen), REST/MCP-Parität (`change_reason` /
  `include_outdated` kanonisch, `reason` / `include_deleted` als deprecatete
  Aliasse bis `1.11.0`), Produktions- und Scope-Härtung, P2.13-Hartabbruch;
- **zusätzlich** die drei Fixes, die `beta.7` erst nach dem Tag erfüllte:
  Hermes-Plugin-Klassifikation von `workflow_default.initialize`,
  Plan-Index-Link auf den REST/MCP-Review-Plan, E2E-Spezifikation der
  Leseansicht (Read-First-Default).

Nicht Teil dieses Cuts sind fachliche Änderungen, Migrationen oder
API-Brüche: der Daten- und Vertragsstand ist identisch zu `beta.7`.

## 2. Release-Cutoff und Basis

| Feld | Wert |
|---|---|
| Schnitt-Branch | `release/v1.9.0-beta.8` (von `main` abgezweigt) |
| Basis-Commit (verifiziert) | `c8e13a59` — Merge `fix/e2e-document-read-mode`; davor `9fc54712` (Merge `fix/post-release-ci-gates`) und `58466ce9` |
| Direkter Vorgänger | `v1.9.0-beta.7`, Tag auf `edcf74dc` (Merge `release/v1.9.0-beta.7`), **nicht publiziert** |
| Cut-Datum | 2026-11-26 |
| CI-Basis | Run `45848388854` auf `c8e13a59`: **completed/success** (alle Backend-Sets, Frontend, Secret Scan, Hermes Plugin, Agent Templates, E2E-Shards 1–7, Prompt Regression) |

## 3. Enthaltene Änderungen

Gegenüber `v1.9.0-beta.6` (letzter veröffentlichter Stand) enthält der Cut den
kompletten Review-Remediations-Strang aus `fix/rest-mcp-review-findings`
(1 Blocker, 16 Major, 15 Minor) plus die Dokument-/Workflow-Feature-Arbeit —
vollständig beschrieben im CHANGELOG-Block `[1.9.0-beta.7]` und im Plan
`docs/plans/2026-11-25-rest-mcp-findings-umsetzungsplan.md`.

Gegenüber dem Tag `v1.9.0-beta.7` kommen genau drei Commits hinzu:

| Commit | Inhalt |
|---|---|
| `4e5936c8` | `fix(security): exempt django check ids from the default gitleaks gate` — liegt bereits **in** `beta.7` |
| `58466ce9` | `fix(ci): close the two post-release gate failures` (Hermes-Plugin-Klassifikation, Plan-Index-Link) |
| `5994ef9a` | `test(e2e): enter edit mode before driving inline document writes` |

## 4. Versions-Carrier

Der Bump lief über `python3 scripts/bump_version.py --version 1.9.0-beta.8`
auf dem Release-Branch (nie auf `main`). Er hat **20 Carrier** geschrieben
(`VERSION`, `.env.example`, beide Compose-Dateien, `site/index.html`,
`docs/CODEBASE_OVERVIEW.md`, `docs/api/MCP-SURFACE.md`,
`systemagents/reqogniloom-operator.md`, `frontend/package*.json`, die
Hermes-Desktop-Plugin-Dateien, die beiden `dist/`-Manifeste,
`.claude-plugin/marketplace.json`, `server.json`) und
`docs/clients/hermes*.md` neu gerendert. Die Diff-Prüfung zeigt
ausschließlich die Versionszeichenkette `1.9.0-beta.7` → `1.9.0-beta.8`;
keine fremde Änderung.

## 5. Changelog

`CHANGELOG.md` erhält `## [1.9.0-beta.8] — 2026-11-26` direkt unter
`## [Unreleased]` (Englisch, Keep a Changelog) mit den Kategorien `Changed`
(unveränderter Funktionsumfang) und `Fixed` (die drei Gate-Fixes). Der Block
`[1.9.0-beta.7]` bleibt unverändert erhalten; `[Unreleased]` ist wieder leer.

## 6. Upgrade-Hinweise und offene Punkte

### 6.1 Migration

Keine neuen Migrationen in diesem Cut gegenüber `beta.7`. Die Migrationen aus
dem Review-Strang (`beta.7`) sind im Deployment wie üblich anzuwenden; sie
wurden hier nicht ausgeführt (`makemigrations --check` meldet „No changes
detected").

### 6.2 Verhaltensänderungen

Identisch zu `beta.7`: Dokumente starten in der Leseansicht (Schreibzugriff
erst über den Modus-Wechsel, serverseitig aufgelöst), Workflow-Definitionen
lassen sich global pro Preset verwalten, und die Soft-Delete-Parameter folgen
`change_reason` / `include_outdated` (Aliasse bis `1.11.0`). Neu ist nur, dass
die E2E-Spezifikation diesen Read-First-Default mitprüft.

### 6.3 Build / Image-Tags

`./scripts/build.sh` läuft **nach** dem Merge auf den finalen `main`-Commit
(Tag-Commit), damit `GIT_COMMIT_SHA` auf den Tag zeigt. Log außerhalb des
Repos (`.tmp/build-1.9.0-beta.8.log`, nicht versioniert). Verbindliche
Digests und SBOM/Provenance liefert der Publish-Job in
`.github/workflows/docker-publish.yml`; das Frontend-Image trägt bewusst keine
Version-Metadaten.

> Platzhinweis: Das Root-Dateisystem lag vor diesem Cut bei 97 % (3,2 GB frei).
> Vor dem Build wurden ausschließlich die lokalen `beta.7`-Images entfernt
> (sofern nicht von laufenden Containern verwendet) — keine fremden Images
> oder Volumes.

### 6.4 Freigabe- und Staging-Gate

Push, Tag und GHCR-Pipeline sind Teil dieses Cuts. Die eigentliche
Publikation hängt am `staging`-Environment der `docker-publish.yml`
(Required Reviewer) — diese Freigabe bleibt manuell.

## 7. Verifikation

| Gate | Befehl / Quelle | Ergebnis |
|---|---|---|
| Bump-eigene Gates | `bump_version.py` → `check_plugin_packages.py --expect-version`, `clients/render.py --check` | **PASS** (12 Sources, 13 Versionsorte, 20 Artefakte) |
| CI-Basis (vollständig) | Run `45848388854` auf `c8e13a59` | **success** — alle Backend-Sets, Frontend, E2E 1–7, Prompt Regression |
| Secret Scan | CI-Run oben + lokal `gitleaks 8.30.1` (Tree, Historie, beide Configs) | **PASS** („no leaks found", 3341 Commits) |
| Pre-Release-Gate-Dispatcher | `.claude/hooks/pre-release-check.sh` | **PASS** (action-pin validiert; artifact-freshness/docker-image-scan selbstübersprungen) |
| `git diff --check` | lokal | **PASS** |
| `makemigrations --check --dry-run` | Test-Stack (`backend-test`) | **PASS** — „No changes detected" |
| Typecheck | `npm run typecheck` (frontend) | **PASS** |
| Repo-Gate-Suite | `pytest docs/agent-templates dist scripts/…` (die Liste des CI-Jobs „Agent Templates & Distribution") | **PASS** — 255 passed, 1 skipped |
| E2E Leseansicht | `npx playwright test document-reading-view --list` + CI-Shard 1 | **PASS** |

## 8. Risiken und Residuen

- **Tag `v1.9.0-beta.7` bleibt unpubliziert.** Er zeigt auf `edcf74dc`, dessen
  CI-Gate rot ist; ein Re-Tag ist per Policy ausgeschlossen. `beta.8`
  ersetzt ihn.
- **`main` ist zwei Commits vor dem beta.8-Tag-Commit, sobald dieser Bericht
  gemergt wird** — der Tag zeigt auf den Merge-Commit des Release-Branches,
  nicht auf den letzten `main`-Push davor.
- **Staging-Approval ist manuell.** Ein grüner Tag-CI-Run bedeutet nicht
  automatisch publizierte Images.
- **Platz.** Das Root-Dateisystem bleibt nach dem Build knapp; vor dem
  nächsten Image-Build ist Platz zu schaffen.
- **Zwei Skript-Tests sind lokal rot, aber vorbestehend und nicht CI-gewired.**
  `scripts/tests/test_license_notices.py` und
  `scripts/tests/test_npm_lock_metadata.py` scheitern identisch auf dem
  CI-grünen Basis-Commit `c8e13a59` (fehlende Lizenz-Metadaten in
  `package-lock.json`); `test_dependency_audit_scope.py` scheitert lokal nur
  wegen untracked Scratch-Verzeichnissen (`.opencode/`,
  `frontend/.tmp/markdown-deps/`) und ist im sauberen Checkout grün. Kein
  Gate dieses Cuts hängt daran.

## 9. Nächste Schritte (nach diesem Cut)

1. Staging-Approval im `staging`-Environment erteilen, damit der Publish-Job
   die beiden Images nach GHCR schiebt.
2. GitHub-Pre-Release `v1.9.0-beta.8` markieren (nicht `latest`), Notizen aus
   dem CHANGELOG-Block `[1.9.0-beta.8]`.
3. `v1.9.0-beta.7` als nicht veröffentlicht kennzeichnen (Bericht/Tag-Notiz),
   damit niemand es als gültiges Artefakt zieht.

---

*Erstellt durch den `release`-Agenten am 2026-11-26. Interne Doku (Deutsch),
keine Secrets. Gemessen: Bump-Gates, CI-Basis, Secret Scan, `git diff
--check`, `makemigrations --check`, Typecheck, Repo-Gate-Suite. Build,
Tag und Publish sind Teil des Release-Laufs.*
