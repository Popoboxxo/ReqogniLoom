---
type: STRATEGY
scope: release-v1-9-0-beta-4
status: draft
date: 2026-11-19
author_agent: release
---
# Release-Bericht v1.9.0-beta.4

> **Status: dringender Follow-up-Beta-Cut zur Wiederherstellung des
> Image-Builds von `v1.9.0-beta.3`. Keine Produktions-, Staging- oder
> QA-Freigabe.** `v1.9.0-beta.3` war bereits getaggt/publiziert, sein
> Docker-Image ließ sich jedoch nicht bauen. Dieser Cut enthält ausschließlich
> die Build-Reparatur aus PR #1945; die UI-Features von beta.3 werden per
> Referenz übernommen (Abschnitt 3.3).

## 1. Release-Ziel

`v1.9.0-beta.4` ist ein **urgent follow-up beta** auf dem Stand von
`v1.9.0-beta.3`. Ziel ist allein, den **zerstörten Docker-Image-Build von
beta.3 wiederherzustellen**: In `backend/requirements-torch.txt` aktivierte
das `--hash=sha256:…`-Flag pip's globalen `--require-hashes`-Modus, wodurch der
`django-celery-beat @ git+…`-VCS-Pin mit `VcsHashUnsupported` abbricht. PR
#1945 verlegt den sha256 in ein PEP-508-URL-Fragment (`#sha256=…`); die
Hash-Prüfung bleibt erhalten, der globale Modus wird nicht aktiviert.

Der Cut behauptet **nicht**: eine neue Produktions- oder Staging-Freigabe,
einen eigenen CI-Lauf im Release-Cut, eine visuelle Abnahme auf echten Geräten
oder dass die Residuen aus beta.3 (Abschnitt 8) geschlossen sind.

## 2. Release-Cutoff und Basis

| Feld | Wert |
|---|---|
| Schnitt-Branch | `fix/torch-pip-hash-fragment` |
| Basis-Commit (verifiziert) | `2f8b05a1` („fix(deps): use URL hash fragment for torch pin") |
| Direkter Vorgänger | `v1.9.0-beta.3`, Merge `11c98c48` (PR #1944) |
| Zugehöriger PR | #1945 (vom koordinierenden Eltern-Agenten genannt) |
| Cutoff (exakt) | Fix-Commit `2f8b05a1` — zwei Dateien: `backend/requirements-torch.txt`, `scripts/tests/test_torch_index_pin.py` |
| Cut-Datum | 2026-11-19 |

> **Hinweis zur Commit-Identität.** Der koordinierende Eltern-Agent nannte
> `16aa783` als Merge-Commit von PR #1945 auf `main`. Dieser Hash ist in
> diesem Checkout in keinem Ref vorhanden (`git log --all` ohne Treffer). Der
> verifizierte HEAD dieses Worktrees ist `2f8b05a1`, der Fix-Commit auf
> `fix/torch-pip-hash-fragment`, aufgesetzt auf den beta.3-Merge `11c98c48`.
> Der Inhalt entspricht exakt der beschriebenen PR-#1945-Änderung. Alle
> Angaben oben sind die im Checkout nachprüfbaren Werte; `16aa783` wird
> deshalb nicht als Basis behauptet.

## 3. Enthaltene Änderung

### 3.1 Root Cause

`v1.9.0-beta.3` wurde getaggt und als Pre-Release publiziert, der zugehörige
Docker-Image-Build schlug jedoch fehl. Ursache war die Torch-Pin-Zeile in
`backend/requirements-torch.txt`:

```
torch @ https://…/torch-2.15.0%2Bcpu-cp315-cp315-manylinux_2_28_x86_64.whl --hash=sha256:3552…233
```

Ein `--hash=`-Flag aktiviert pip's **globalen** `--require-hashes`-Modus für
die gesamte Resolution. `requirements.txt` enthält rund 145 nicht
hash-gepinnte Pakete sowie den VCS-Pin `django-celery-beat @ git+…`; beides
ist mit diesem Modus unvereinbar (VCS-Pins liefern keine Hashes →
`VcsHashUnsupported`). Damit war der Image-Build nicht reproduzierbar.

### 3.2 Fix (PR #1945 / Commit `2f8b05a1`)

Der sha256 wandert als **PEP-508-URL-Fragment** in die Wheel-URL:

```
torch @ https://…/torch-2.15.0%2Bcpu-cp315-cp315-manylinux_2_28_x86_64.whl#sha256=3552…233
```

pip verifiziert den Hash weiterhin beim Download, aktiviert aber **nicht** den
globalen Hash-Required-Modus; der VCS-Pin bleibt auflösbar. Die
Supply-Chain-Intention aus **DEP-005** bleibt unverändert: die CPU-Wheel wird
weiterhin über eine exakte PEP-508-URL statt eines zweiten Index gepinnt (kein
Dependency-Confusion-Risiko durch einen sekundären PyTorch-Index), und ADR-08
verhindert weiterhin die mehrgigabyte-großen CUDA/`nvidia-*`-Wheels. `scripts/tests/test_torch_index_pin.py`
 wurde auf das neue Fragment-Format umgestellt (regex ` --hash=sha256:` →
`#sha256=`), sodass ein Rückfall in den Flag-Modus vom Test erkannt wird.

### 3.3 Feature-Inhalt von beta.3 — per Referenz übernommen

Dieser Cut ändert **keine** UI-Funktionalität. Die vier Schnitte von
`v1.9.0-beta.3` (Trace-Spine-Footer mit zwei User-Toggles, Baumbreite pro
Modul gemäß ADR-030, On-Demand-Impact-Drawer, Mobile-Sheet-Koordination und
A11Y-Korrekturen) sind unverändert enthalten; Details siehe
`RELEASE_v1.9.0-beta.3.md` Abschnitte 3–6 und den CHANGELOG-Block
`[1.9.0-beta.3]`. Der MCP-Katalog bleibt bei **301 Tools in 49 Präfixen**;
es gibt kein neues Datenmodell, keine Migration und kein neues Tool.

## 4. Versions-Carrier

Alle Carrier wurden über das kanonische
`python3 scripts/bump_version.py --version 1.9.0-beta.4` gesetzt
(strukturell per JSON-Pointer / Compose-Default-Regex, nicht per
String-Ersetzung), danach `scripts/clients/render.py` für die
Client-Artefakte. Alter Stand überall `1.9.0-beta.3`.

| Datei | Stellen |
|---|---|
| `VERSION` | 1 |
| `frontend/package.json` / `frontend/package-lock.json` | 1 / 2 |
| `.env.example` | 2 |
| `deploy/docker-compose.yml` / `deploy/docker-compose.minimal.yml` | 6 / 3 |
| `server.json` | 1 |
| `.claude-plugin/marketplace.json` | 2 |
| `dist/npm/reqogniloom-opencode/package.json` | 1 |
| `dist/plugins/claude-code/…/plugin.json` | 1 |
| `dist/plugins/antigravity/…/plugin.json` | 1 |
| `integrations/hermes-plugin/reqogniloom/package.json` / `package-lock.json` / `hermes-plugin.json` | 1 / 2 / 1 |
| `site/index.html` | 2 |
| `docs/CODEBASE_OVERVIEW.md` | 6 |
| `docs/api/MCP-SURFACE.md` | 5 |
| `systemagents/reqogniloom-operator.md` | 2 |
| `docs/clients/hermes.md`, `hermes.de.md` | je 1 (generiert) |

**Gesamt:** 20 Dateien, 38 Insertions / 38 Deletions — ausschließlich
Versionszeichenketten. Der Bumper lief mit **exit 0**; der Carrier-Ratchet
meldet 12 Sources / 13 Version-Locations / 2 unabhängige POC-Manifeste
konsistent, `clients/render.py --check` meldet 18 Artefakte aktuell
(2 neu geschrieben, 16 unverändert).

**Nicht vom Bumper besessen (aus beta.3 übernommen, bewusst nicht
hand-editiert):** `.meta-config/project.yaml` nennt weiterhin
`Stand VERSION 1.9.0-beta.2` und `RELEASE_v1.9.0-beta.2.md` als jüngsten
Report. Kein Gate prüft diese Textzeilen.

## 5. Changelog

`CHANGELOG.md` erhält einen Block `## [1.9.0-beta.4] — 2026-11-19` direkt
unter `## [Unreleased]` (Englisch, Keep a Changelog) mit einem einzigen
`### Fixed`-Eintrag. Kein Breaking-Change: die Reparatur stellt den
vorgesehenen Build wieder her und ändert keine API- oder
Datenverträge. Referenzen: `#1945`, `DEP-005`.

## 6. Upgrade-Hinweise und offene Punkte

### 6.1 Automatisch laufend

Keine Datenmigration. `requirements-torch.txt` wird ausschließlich vom
Backend-`Dockerfile` in derselben pip-Resolution wie `requirements.txt`
installiert; CI (Python 3.12) installiert weiterhin nur `requirements.txt`,
der cp315-Wheel-URL-Eintrag bleibt also aus den 3.12-Jobs heraus.

### 6.2 Verhaltensänderungen

Keine zur Laufzeit. Einzig die Build-Zeit-Resolution des Torch-Pins ändert
sich: kein globaler Hash-Required-Modus mehr, Hash-Prüfung pro Wheel-URL
bleibt aktiv. Die gepinnte Wheel-URL und der sha256 sind unverändert.

### 6.3 Blockierender offener Punkt

Die **GHCR-Publikation über das Staging-Gate ist weiterhin blockiert**: der
Repo-Einstellung fehlt `required_reviewers`. Das Gate ist damit bewusst
fail-closed; dieser Cut umgeht es nicht und nimmt keine Freigabe vor.

## 7. Verifikation

> **Herkunft der Nachweise.** CI-Ergebnis und Image-Builds stammen aus dem
> Kontext von PR #1945 und wurden in diesem Cut **nicht neu gemessen**. Der
> Carrier-Bump, die beiden Release-Gates und die Script-Suite wurden in
> diesem Cut lokal ausgeführt (nachfolgend als „lokal gemessen" markiert).

| Gate | Befehl / Quelle | Ergebnis |
|---|---|---|
| PR-CI | PR #1945 (koordinierender Kontext) | **34 Checks grün** |
| Docker-Images | lokal (koordinierender Kontext) | **beide Images (Backend + Frontend) erfolgreich gebaut** |
| Script-Suite (lokal gemessen) | `python3 -m pytest scripts/tests/ -q` | **102 passed, 1 skipped**, exit 0 (4.75 s) — keine Baseline angehoben |
| Voller Bump (lokal gemessen) | `python3 scripts/bump_version.py --version 1.9.0-beta.4` | **exit 0** — Carrier gesetzt, Clients gerendert, Ratchet + `render --check` grün |
| Carrier-Ratchet (lokal gemessen) | `python3 scripts/check_plugin_packages.py --expect-version 1.9.0-beta.4` | **OK** — 12 Sources, 13 Version-Locations, 2 POC-Manifeste |
| Client-Artefakte (lokal gemessen) | `python3 scripts/clients/render.py --check` | **OK** — 18 Artefakte aktuell |
| Whitespace | `git diff --check` | siehe Abschnitt 8 — vorbestehender Hard-Break in `docs/CODEBASE_OVERVIEW.md:4` |

## 8. Risiken und Residuen

- **Staging-Gate weiterhin rot.** Ohne `required_reviewers` in den
  Repository-Einstellungen bleibt die GHCR-Publikation fail-closed blockiert
  (Abschnitt 6.3). Der Image-Build selbst ist repariert, das Publishing nicht.
- **Keine erneute vollständige Suite im Cut.** Die 34 CI-Checks und die
  beiden Image-Builds stammen aus PR #1945; lokal gemessen wurden nur die
  Script-Suite (102/1) und die Release-Gates.
- **Beta.3-Residuen gelten unverändert weiter** (siehe
  `RELEASE_v1.9.0-beta.3.md` Abschnitt 8): kein frischer Suite-Lauf im
  beta.3-Cut, keine Live-Device-/PNG-Abnahme, kein manuelles
  Screenreader-Sign-off, zwei Baumbreiten-Semantiken (`ratio` Initialwert /
  `treeWidth` autoritativ), keine Cross-Device-Synchronisation.
- **`git diff --check`**: `docs/CODEBASE_OVERVIEW.md:4` enthält einen
  vorbestehenden trailing-whitespace-Hard-Break (`> **Stand:** …  `),
  der vom Bumper unverändert übernommen wird. Bewusst **nicht** manuell
  korrigiert — kein Bestandteil dieses Cuts.
- **project.yaml-Inkonsistenz** siehe Abschnitt 4 — kein Gate, aber
  reviewpflichtig.

## 9. Nächste Schritte (nicht Teil dieses Cuts)

1. Review dieses Branches, dann Release-PR gegen `main` (Aufgabe des
   `git`-Agenten).
2. Tag `v1.9.0-beta.4` auf den Release-Commit — kein Re-Tag nach dem Push.
3. Build via `scripts/build.sh` / `make build`, Publish via
   `docker-publish.yml` — **nach** Klärung des Staging-Gates
   (`required_reviewers`).
4. GitHub-**Pre-Release** markieren, nicht `latest`.
5. Release-Notizen aus dem CHANGELOG-Block `[1.9.0-beta.4]` übernehmen.

---

*Erstellt durch den `release`-Agenten am 2026-11-19. Interne Doku (Deutsch),
keine Secrets. Lokal gemessene Zahlen (Bump, Gates, 102/1 Script-Tests) sind
in diesem Worktree nachprüfbar; CI (34 Checks) und die beiden Image-Builds
stammen aus dem PR-#1945-Kontext und sind nicht hier neu gemessen. Kein
Commit/Push/Tag/PR durch den Autor.*
