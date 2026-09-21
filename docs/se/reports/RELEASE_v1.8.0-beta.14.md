---
type: STRATEGY
scope: Release v1.8.0-beta.14
status: in-progress
date: 2026-09-21
author_agent: release
---

# Release-Bericht v1.8.0-beta.14

## 1. Release-Ziel

Vorbereitung des Beta-Release `v1.8.0-beta.14` auf dem Branch
`chore/release-v1.8.0-beta.14` (Basis: `main`). Dieser Bericht dokumentiert die
Vorbereitung in diesem Branch: Versionierung in allen Carriern, CHANGELOG und
dieser Bericht. Auslieferung (Merge, Tag, GitHub-Pre-Release, GHCR-Publish)
erfolgt durch den Release-Owner **nach** dem Merge und wird hier nachgetragen
(Abschnitte 7–9, Status `in-progress`). Dominantes Thema des Deltas ist das
Workspace-Gedächtnis v2 (RFC #1002, PRs #1020–#1025).

- **Version:** `1.8.0-beta.14`
- **Tag (geplant):** `v1.8.0-beta.14`
- **Basis-Commit:** `06978ba4` (`fix(llm): add x-opencode-session header and
  container DNS runbook (#1027)`), voll
  `06978ba4549bb170276cb9f0e78d822bffd4c0b4`
- **Letztes Release:** `v1.8.0-beta.13`, **Tag-Zeit**
  `2026-09-20T18:19:59+02:00`
- **Datumsstempel des Berichts:** 2026-09-21

## 2. Release-Cutoff (exakter Zeitstempel)

Als Cutoff wurde der **exakte Tag-Zeitstempel** von `v1.8.0-beta.13` verwendet
(`2026-09-20T18:19:59+02:00`), kein Kalender-Tagesfilter.

- `git log v1.8.0-beta.13..HEAD --no-merges` → **9 Commits**
- Darin enthaltene, seit dem Cutoff gemergte **PRs: #1017, #1020, #1022, #1023,
  #1024, #1025, #1026, #1027** (8 PRs, unten) plus der Hand-off-Commit
  `0fe67bd1` (`docs: add hand-off test plan for v1.8.0-beta.14`, kein PR).

## 3. Enthaltene PRs seit dem Cutoff

| PR | Titel (aus `git log`) | Beitrag |
|----|------------------------|---------|
| #1017 | `docs(release): finalize v1.8.0-beta.13 release report` | Finalisierung des beta.13-Berichts (Tag, Pre-Release, GHCR-Nachweis) |
| #1020 | `feat(memory): unify memory store into mem_memory_entry (#1002)` | Memory A — vereinheitlichter Store (`mem_memory_entry`, RLS, Provenienz) |
| #1022 | `feat(memory): add entry service, policy, MCP and REST surfaces (#1002)` | Memory B — Service/Policy/6 MCP-Tools/16 REST-Routen/Rate-Limit |
| #1023 | `feat(memory): artifact scope write path and prompt injection (#1002)` | Memory C — Artefakt-Scope + Prompt-Injektion |
| #1024 | `feat(memory): workspace memory UI and artifact panel (RFC #1002 PR D)` | Memory D — Workspace-Memory-UI und Artefakt-Panel |
| #1025 | `feat(memory): honcho sessions, deriver and digest (RFC #1002 F6)` | F6 — Honcho-Sessions/Deriver/`digest` hinter `MEMORY_BACKEND=honcho` |
| #1026 | `docs: correct MCP tool count to 215 and ignore .playwright-mcp` | Tool-Zahl 215 + `.playwright-mcp` ignoriert |
| #1027 | `fix(llm): add x-opencode-session header and container DNS runbook (#1027)` | `x-opencode-session`-Header + Container-DNS-Runbook |

## 4. Themen-Highlights

- **Workspace-Gedächtnis v2 (RFC #1002, PRs #1020/#1022/#1023/#1024/#1025 —
  dominantes Thema):**
  - **Store (#1020):** Das Langzeitgedächtnis liegt in der einen Tabelle
    `mem_memory_entry` unter Row-Level-Security; jeder Schreibpfad legt eine
    Provenienz (Scope, Owner, Workspace, Artefakt-Bezug, Quelle) an, sodass die
    Scopes `user` | `workspace` | `artifact` einen gemeinsamen Persistenz- und
    Retrieval-Vertrag teilen.
  - **Service/Policy/Transporte (#1022):** Die `MemoryEntryService`-Fassade
    (ADR-01) ist über REST **und** MCP erreichbar — **6 `memory.*`-Tools**
    (`memory.write`, `memory.get`, `memory.digest`, `memory.query`,
    `memory.list`, `memory.forget`) und **16 `/api/v1/`-Routen**
    (`workspaces/<id>/memory/entries/`, `…/search/`, `…/digest/`,
    `memory/entries/<entry_id>/`, `…/promote/`, `artifacts/<id>/memory/`,
    `…/memory/digest/`, `workspaces/<id>/memory-settings/`,
    `system/memory-settings/` (+`reset/`), `system/memory/workspaces/`
    (+DELETE `<id>/`), `system/memory/entries/`, `system/memory/projection/`,
    `system/memory/entries/export/`, `memory/me/`). Writes laufen über
    `MEMORY_WRITE_RATE_LIMIT_PER_HOUR` (Default 60); Backend-Wahl über
    `MEMORY_BACKEND` = `pgvector` (Default) | `honcho`.
  - **Degraded-Signal:** `backend/memory/health.py` liefert das Envelope
    `{backend, ok, detail, degraded, digest_available}`; derselbe Zustand
    erscheint als Komponente `memory_backend` in `GET /api/v1/admin/health/`
    sowie als UI-Banner.
  - **Artefakt-Scope + Prompt-Injektion (#1023):** `prompt_resolver` speist
    aufgelöste Einträge über `memory/context_builder.py` in den Prompt ein —
    Abschnitte `Artifact context:` / `Workspace context:` / `User context:`,
    artefakt-zuerst, fail-open.
  - **UI (#1024):** Workspace-Memory-Ansicht und Artefakt-Memory-Panel
    inklusive Digest und Degraded-Banner.
  - **Honcho (#1025):** Sessions/Deriver und das konsolidierte `digest` hinter
    `MEMORY_BACKEND=honcho` (Profil `honcho`).
- **Provider-Integration (#1027):** Der `opencode_go`-Provider hängt den
  `x-opencode-session`-Header **nur** an, wenn `LLM_OPENCODE_SESSION` gesetzt
  ist (nicht gesetzt ⇒ kein Header, Default); das Container-DNS-Runbook liegt in
  `deploy/README.md`, Abschnitt „Troubleshooting: LLM calls fail with ConnectError
  (backend container DNS)".
- **MCP-Surface (#1026):** Die dokumentierte Tool-Zahl ist auf die reale
  Katalog-Größe **215** korrigiert; `.playwright-mcp` wird ignoriert. Der
  MCP-Server ist unter `/mcp/` **und** `/api/v1/mcp/` gemountet (JSON-RPC 2.0:
  `ping`, `initialize`, `tools/list`, `tools/filter`, `tools/call`; SSE unter
  `.../sse/`).
- **Doku/Report (#1017):** Finalisierung des beta.13-Release-Berichts.

## 5. Versions-Carrier (Delta dieses Commits)

Alle Träger von `1.8.0-beta.13` → `1.8.0-beta.14` (bereits im Arbeitsbaum
angewendet: 12 Dateien / 22 Zeilen):

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
`CHANGELOG.md` und dieser Bericht sind neu und zählen nicht zu den 12 Carriern.

## 6. Verifikation (lokal)

| Gate | Ergebnis |
|---|---|
| `git grep "1.8.0-beta.13"` | **nur historische Treffer** unter `CHANGELOG.md` + `docs/**` (kein aktiver Carrier mehr auf `beta.13`) |
| `docker compose -f deploy/docker-compose.yml config -q` | **PASS** |
| `docker compose -f deploy/docker-compose.minimal.yml config -q` | **PASS** |
| Endpunkte/Tool-Namen des neuen Testplans gegen den Code geprüft | `backend/rest_api/urls.py`, `backend/mcp_server/tools/memory.py`, `backend/mcp_server/tools/requirements.py` — **deckungsgleich** |

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
| Vorbereitungs-PR `chore/release-v1.8.0-beta.14` | nach Merge nachzutragen |

## 8. Tag & GitHub-Pre-Release

> **Nach Merge nachzutragen.**

| Schritt | Ergebnis |
|---|---|
| Merge des Vorbereitungs-PR → `main` | nach Merge nachzutragen |
| Annotierter Tag `v1.8.0-beta.14` | nach Merge nachzutragen |
| GitHub **Pre-Release** (`prerelease=true`) | nach Merge nachzutragen |
| `Docker Publish (GHCR)` — `…-backend:1.8.0-beta.14` + `…-frontend:1.8.0-beta.14` | nach Merge nachzutragen |

## 9. Nachtrag (Auslieferung)

**In diesem Branch NICHT ausgeliefert.** Tag `v1.8.0-beta.14`, GitHub
Pre-Release (`prerelease=true`) und der GHCR-Publish der Images
`1.8.0-beta.14` (backend + frontend) werden vom Release-Owner **nach dem Merge**
dieses Vorbereitungs-PR durchgeführt und anschließend in Abschnitt 7 und 8
nachgetragen. Dieser Bericht steht daher auf `status: in-progress`.

### Bekannte Punkte / Follow-ups

- **`.env.example` (ca. Zeile 293) benennt das MCP-Tool `memory_forget`
  (Unterstrich), während der reale Tool-Name `memory.forget` (Punkt) lautet.**
  Rein dokumentarischer Defekt; **nicht** in diesem Branch behoben und als
  nicht-blockierender Follow-up geführt.
- **Externer Testplan:** Der manuelle Testplan zu diesem Release liegt als
  `docs/se/reports/TESTPLAN_v1.8.0-beta.14.md` (Hand-off-Commit `0fe67bd1`) und
  ist nicht Teil dieses Berichts.
