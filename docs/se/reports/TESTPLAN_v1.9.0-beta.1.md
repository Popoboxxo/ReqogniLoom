# Testplan v1.9.0-beta.1

> **Geltungsbereich: interner Pre-Release.** Dieser Testplan prüft den Schnitt,
> nicht die Produktionsreife. Zwei Punkte sind ausdrücklich als **nicht in
> diesem Cut verifiziert** geführt und dürfen nicht als bestanden gewertet
> werden: (1) es gibt **keinen neuen Suite-Lauf dieses Cuts** — die Evidenz
> sind die CI-Läufe der gemergten PRs auf `main` (`bad3bf93`); (2) die
> DoD-10-Sichtprüfung der neuen Oberflächen ist offen (Abschnitt 6).
>
> **Checkbox-Disziplin.** Angekreuzt wird nur, was real verifiziert ist
> (gemergte PR mit grüner CI bzw. lokal ausgeführter Gate-Befehl). Alles, was in
> diesem Cut **nicht** gelaufen ist, bleibt leer und ist als solches begründet.

## 1. Ziel & Prüfgegenstand

Geprüft wird das Delta `1.8.0-beta.29` → `1.9.0-beta.1`: 115 gemergte PRs
strikt nach `2026-11-09T08:48:58Z` (Vorgänger-Release #1753), verteilt auf
sieben Feature-Bereiche (Details: `RELEASE_v1.9.0-beta.1.md`, Abschnitt 3).

### 1.1 Im Scope

- AI-Artifact-Summaries (#1792/#1793)
- Inspector M1–M8 und Entfernen der Legacy-Sidebar (#1762)
- Bearbeitbare Dokumentansicht R1–R7 (ADR-026-Nachtrag)
- Verbindungsansicht als zwei Bäume (S0/G1–G3/V.0–V.5)
- Allocation als Objekt, Release-Kaskade, typisierte Test-Case-Steps, Quality
- Hermes-Plugin-Requirements-Views, Search-Summary, OpenCode-Verifikation
- Audit-Abarbeitung 2026-11-15 inkl. der neuen CI-Dependency-Gates

### 1.2 Nicht im Scope

- Produktions-, Staging- oder QA-Reife
- Visuelle Abnahme über die vier DoD-10-Breiten (kein laufender Stack in diesem
  Cut)
- `ChangeRequestDTO.baseline_id`-Parität (bewusst offen, Abschnitt 6)
- Ein neuer Vollsuite-Lauf dieses Cuts (Abschnitt 2.3)
- Migration von Altinstanzen (nur die Wirkung von `0142`/`0026` auf bestehende
  Definitionen, Abschnitt 3.7)

## 2. Vorbedingungen

### 2.1 Source-Checkout, kein Image

Zum Zeitpunkt dieses Plans existiert **kein veröffentlichtes Image
`1.9.0-beta.1`**. Der Stack wird aus dem Source-Checkout des Branches
`release/v1.9.0-beta.1` gestartet:

```
make up
```

### 2.2 Health und Seed

```
curl http://127.0.0.1:8001/health/live     # 200
curl http://127.0.0.1:8001/health/ready    # 200 im gesunden Zustand
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml \
  exec -T backend python manage.py seed_demo
```

### 2.3 Kein frischer Suite-Lauf dieses Cuts

Der Cut ändert — außer Versions-Carriern, `CHANGELOG.md`, diesem Testplan, dem
Release-Bericht und den bereits vorher uncommitteten REQ-197…REQ-208 — keinen
Code. Es wurde **kein** neuer Backend-/Frontend-/E2E-Vollsuite-Lauf gegen
`release/v1.9.0-beta.1` gefahren. Die Evidenz sind die CI-Läufe der gemergten
PRs auf `main`; alle in Abschnitt 3 genannten PRs sind mit grüner CI gemergt.

## 3. Relevante Suiten für diesen Cut

### 3.1 Backend — pytest-Matrix (4 Sets, `.github/workflows/ci.yml`)

| Set | Pfade | Relevanz für diesen Cut |
|---|---|---|
| `set-1-core` | `application/tests`, `persistence/tests` | Dokument-Lese-/Edit-Policy, Bulk-Update-Service, Allocation-Kardinalität, Release-Kaskade, Summary-Service |
| `set-2-api` | `rest_api/tests`, `auth_tenancy/tests`, `presets/tests`, `reqogniloom/tests`, `test_runs/tests`, `attribute_definitions/tests` | `documents/{id}/view/`, `artifacts/bulk-update/`, `kind`/`sort_key` auf `allocation-view/`, Präferenz-Schlüssel |
| `set-3-mcp` | `mcp_server/tests` | `artifact.summary`, `artifact.bulk_update`, `summary.get`/`summary.refresh`, Manifest-Drift |
| `set-4-features` | `traceability/tests`, `workflow/tests`, `baseline/tests`, `memory/tests`, `link_types/tests`, `tests` u. a. | `released`-Zustand, Release-Kaskade, `ALLOC-P1`/`REL-P1`, typisierte Steps in Baselines, Honcho-Degradation |

Zusätzlich in CI: `pytest docs/agent-templates dist` (Doc-/Manifest-Gates) und
die separate Hermes-Plugin-Suite unter `integrations/hermes-agent-plugin/tests`.

### 3.2 Frontend — Vitest

Vollsuite `vitest run` in `frontend/`. Ratchets, die für diesen Cut besonders
zählen: `hardcoded-styles.test.ts` (Baseline nach #1863/#1866 gesenkt),
`design-system-ratchet.test.ts`, `ui-ratchet`, `theme-contrast`,
`i18n`-Vollständigkeit.

### 3.3 E2E — Playwright, 4 CI-Shards

Relevante Specs dieses Cuts: `document-reading-view.spec.ts`,
`connection-trees.spec.ts`, `requirement-groups.spec.ts`,
`connection-view.spec.ts` (umgestellt auf `counter-unallocated`/`alloc-select`).

### 3.4 Dependency-Audit

Ein CI-Job (aus #1865): `npm audit --audit-level=high --json` (critical/high
blockieren) und `pip-audit -r requirements.txt --strict` in einer
Wegwerf-venv (Version gepinnt, 2.10.1). Baseline: 145 Backend-Pakete / 676
Frontend-Pakete, 0 Findings.

### 3.5 Drift- und Konsistenz-Gates

| Gate | Befehl |
|---|---|
| Carrier-Ratchet | `python3 scripts/check_plugin_packages.py --expect-version 1.9.0-beta.1` |
| Client-Artefakte | `python3 scripts/clients/render.py --check` |
| MCP-Tool-Count-Drift | `python3 -m pytest docs/agent-templates/test_meta_tool_count_drift.py` |
| Doc-Surface-Konsistenz | `python3 -m pytest docs/agent-templates/test_doc_surface_consistency.py` |
| MCP-Manifest-Drift | `backend/mcp_server/tests/test_tool_manifest_drift.py` (in `set-3-mcp`) |

## 4. Neue Tests dieses Cuts

### 4.1 Dokumentansicht R1–R7

| Datei | Ebene |
|---|---|
| `backend/application/tests/test_document_reading_service.py` | Kapitel-/Leseobjekt-Erzeugung, Markdown-Rendering |
| `backend/rest_api/tests/test_document_view_r1.py` | Route, `ETag`, 403/404, `?format=markdown` |
| `backend/application/tests/test_document_edit_policy.py` | Urteilsreihenfolge `PERMISSION` → `REPO_EXTERNAL` → `FIELD_FROZEN` |
| `backend/application/tests/test_bulk_update_service.py` | Transaktionssemantik, `MAX_ENTRIES = 100` |
| `backend/rest_api/tests/test_bulk_update_api.py` | 400 für Stapelformfehler, 409 mit `errors[]` |
| `backend/mcp_server/tests/test_artifact_bulk_update_tool.py` | `artifact.bulk_update`, Write-Gate |
| `frontend/src/test/DocumentReadingView.test.tsx` | Lesemodus, TOC, Sperrbanner |
| `frontend/src/test/DocumentFieldEditor.test.tsx` | `If-Match`, 412/409/400 am Feld |
| `frontend/src/test/DocumentSaveBar.test.tsx` | Sammelmodus, Entwürfe bleiben bei 409 |
| `e2e/tests/document-reading-view.spec.ts` | End-to-End inkl. Druckansicht |

### 4.2 Verbindungsansicht / Bäume

| Datei | Ebene |
|---|---|
| `frontend/src/components/ConnectionView/allocation-trees.test.ts` | Baumaufbau, `sort_key`, „nicht allokiert" |
| `frontend/src/components/ConnectionView/edge-geometry.test.ts` | Kantengeometrie, eine Linie je Allokation |
| `frontend/src/components/ConnectionView/useAllocationSelection.test.ts` | Auswahl überlebt Filterwechsel, gesperrte Zeilen |
| `frontend/src/components/ConnectionView/AllocationTreesRenderer.test.tsx` | Renderer, Zieltexte, `aria-expanded` |
| `e2e/tests/connection-trees.spec.ts` | Modus `trees`, Default, Kopfschalter |
| `e2e/tests/requirement-groups.spec.ts` | Gruppendialog, Zeilenaktion, Drag auf Ordner |

Ergänzend angepasst/erweitert: `useAllocationView.reads.test.tsx` (zwei
gezielte Reads), `backend/rest_api/tests/` (`kind`/`sort_key`),
`backend/auth_tenancy/tests/test_preference_keys_ordering.py`
(`show_edges`/`filters_expanded`).

## 5. Abnahme-Checkliste für den Release

- [x] Carrier-Ratchet grün: `check_plugin_packages.py --expect-version 1.9.0-beta.1`
      (12 Sources, 13 Version-Locations, 2 unabhängige POC-Manifeste)
- [x] Client-Artefakte aktuell: `clients/render.py --check` (18 Artefakte)
- [x] Versions-Bump vollständig: `bump_version.py --version 1.9.0-beta.1` exit 0
- [x] MCP-Manifest konsistent: `tool_count` 297, 47 Präfixe, `artifact.summary`,
      `artifact.bulk_update`, `summary.get`/`summary.refresh` vorhanden
- [x] Drift-Tests der Doc-Oberfläche grün: `test_meta_tool_count_drift.py` +
      `test_doc_surface_consistency.py` → 15 passed
- [x] `CHANGELOG.md` enthält `## [1.9.0-beta.1] — 2026-11-16` mit
      Added/Changed/Fixed/Removed und PR-Nummern
- [x] Breaking-Punkt markiert: `/connections` Default `trees`, Alias
      `view=tree` → `architecture`
- [x] Release- und Testplan-Bericht liegen unter `docs/se/reports/`
- [ ] Backend-Vollsuite (4 Sets) gegen diesen Branch — *nicht in diesem Cut
      gelaufen; Evidenz sind die CI-Läufe der gemergten PRs auf `main`*
- [ ] Frontend-Vollsuite (`vitest run`) gegen diesen Branch — *dito*
- [ ] E2E-Vollsuite (4 Shards) gegen diesen Branch — *dito*
- [ ] DoD-10-Sichtprüfung 1440/1024/768/320 px für Inspector, Dokumentansicht
      und Bäume — *offen, braucht einen laufenden Stack*
- [ ] Dependency-Audit lokal reproduziert — *nur über den CI-Job #1865 belegt;
      `pip-audit` lokal nicht verfügbar*
- [ ] `#1865` als Required Check in den Repo-Settings eingetragen — *offen*

## 6. Bekannte Grenzen & Hinweise

### 6.1 `check-version-drift.sh` ist kein Carrier-Gate

Das Skript vergleicht den `commit_short` einer **deployten** Umgebung gegen
`origin/main` und verlangt `DEPLOYED_VERSION_URL`; ohne URL endet es mit
`exit 2`. Es läuft als geplanter Monitor (täglich 09:00 UTC) und blockiert
keinen Merge. Der Carrier-Gate dieses Schnitts ist
`check_plugin_packages.py` + `clients/render.py --check` (Abschnitt 3.5).

### 6.2 Kein Image-Nachweis

Solange `1.9.0-beta.1` nicht via `scripts/build.sh` gebaut und über
`docker-publish.yml` publiziert wurde, existiert kein Image- und kein
Digest-Nachweis dieses Cuts.

### 6.3 Zwei Migrationen mit Verhaltenswirkung

`0142` entfernt `uniq_tracelink_allocated_to_source` (die Kardinalitätsregel
wird jetzt workspace-spezifisch in der Service-Schicht durchgesetzt); `0026`
ergänzt den Zustand `released` in bestehenden Workflow-Definitionen. Beide sind
idempotent und verschieben keine Datenzeile. Ein Test, der die alte
DB-Constraint erwartet, ist bewusst angepasst
(`test_second_allocated_to_edge_is_rejected_by_the_service_not_the_db`).

### 6.4 `minimatch`-Override als Brücke

Der verschachtelte Override (`@typescript-eslint/typescript-estree →
minimatch ^11.0.8`) hält `npm audit` auf 0, ist aber temporär. Er muss fallen,
sobald `@typescript-eslint` ≥ 8.72.3 stabil `minimatch@^11` pinnt.

### 6.5 Live-Artefakt

Der E2E-Lauf `2026-11-14` ergab `417/418` grün; der verbleibende Fall
(`#1825` waterkettle Phase 1b: 17 statt 18 Requirements) wurde mit `#1830`
deterministisch gemacht. Nicht als offener Befund dieses Cuts werten, aber bei
einem neuen Lauf beobachten.

### 6.6 Ausdrücklich nicht bestanden

- Kein neuer Suite-Lauf dieses Cuts (2.3).
- Keine visuelle DoD-10-Abnahme (5).
- `ChangeRequestDTO.baseline_id` weiterhin nicht im REST-/MCP-Payload.
- `pip-audit` lokal nicht reproduziert.
- `#1865` nicht als Required Check registriert.

## 7. Freigabe-Urteil

Der Schnitt ist **beta-tauglich im Sinne des Feature-Umfangs**: alle 115 PRs
sind mit grüner CI gemergt, die Carrier- und Konsistenz-Gates sind lokal grün,
und die einzige Breaking-Änderung ist durch einen permanenten Alias
abgefedert. **Nicht** abgedeckt sind ein erneuter Vollsuite-Lauf dieses Cuts,
die visuelle DoD-10-Abnahme und die drei genannten offenen Paritäts-/
Prozess-Punkte. Es gibt **keine Produktions-, Staging- oder QA-Freigabe**.

---

*Erstellt durch den `release`-Agenten am 2026-11-16. Interne Doku (Deutsch),
keine Secrets. Keine erfundenen Häkchen: jedes **[x]** ist auf einen lokal
ausgeführten Gate-Befehl, eine Datei im Arbeitsbaum oder einen gemergten PR
zurückführbar. Kein Commit/Push durch den Autor.*
