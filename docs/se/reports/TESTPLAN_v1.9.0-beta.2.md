# Testplan v1.9.0-beta.2

> **Geltungsbereich: interner Bugfix-Beta.** Kein Produktions-, Staging- oder
> QA-Nachweis. **Dieser Cut führt keinen eigenen Suite-Lauf durch** — die
> Evidenz sind die CI-Läufe der 11 gemergten PRs auf `main` (`2c287d50`).
> Angekreuzt wird nur, was lokal ausgeführt oder durch einen grünen CI-Lauf
> belegt ist; alles andere bleibt leer und ist begründet (Abschnitt 6).

## 1. Prüfgegenstand

Delta `v1.9.0-beta.1` (`f1e9c8f3`) → `2c287d50`: 11 PRs in drei Bereichen.

| Bereich | PRs |
|---|---|
| Tabellenansicht komplett | #1872, #1874, #1876, #1877 |
| MCP-Modernisierung A–E | #1871, #1873, #1875, #1878 |
| Bugfixes aus der Beta-Rückmeldung | #1884, #1885, #1886 |

Details: `RELEASE_v1.9.0-beta.2.md`, Abschnitt 3.

### 1.1 Nicht im Scope

- Ein neuer Vollsuite-Lauf dieses Cuts (Abschnitt 6.1)
- Visuelle DoD-10-Abnahme der Tabellenansicht
- Die in `RELEASE_v1.9.0-beta.2.md` §6.3 genannten Residuen (#1247, #1230,
  CORS-Header, `transitions/`-Filter, `baseline_id`-Parität)

## 2. Relevante Suiten

| Suite | Wo | Was sie in diesem Cut abdeckt |
|---|---|---|
| Backend-Matrix (pytest, Django) | `make test-backend` bzw. CI `ci.yml` | Table-Query-Service + Filter-DSL, Saved Views, MCP-Protokoll/Session/Resources/Prompts, API-Key-Gruppen, Memory-/Workflow-/Coverage-Fixes |
| Frontend (Vitest) | `make test-frontend` | `ArtifactTable`, Spalten-/Filter-Zustand, Bulk-Leiste, i18n der neuen Strings |
| E2E (Playwright, 4 Shards) | `npm run test:e2e` in `e2e/` | `artifact-table.spec.ts` (Tabellen-Flows inkl. Bulk-Transition-Ausgang) |
| Dependency Audit | CI-Job (`npm audit --audit-level=high` + `pip-audit --strict`) | unverändert; keine neuen Abhängigkeiten in diesem Cut |
| Drift-Gates | `test_tool_manifest_drift.py`, `test_doc_surface_consistency.py`, `test_meta_tool_count_drift.py`, `clients/render.py --check` | Katalog 301/49 und Doku-Oberfläche nach dem Bump |

## 3. Neue Tests dieses Cuts

### 3.1 Tabellenansicht

- `backend/application/tests/test_table_query_service.py` — Zeilenform,
  Batch-Lookups, Seitengröße, `id`-Tiebreak
- `backend/application/tests/test_table_filter_dsl.py` — typisierte Operatoren
  je Feldart, `?allocated=`/`?level=` auf derselben DSL
- `backend/rest_api/tests/test_table_views.py` — `GET /api/v1/artifacts/table/`
- `backend/application/tests/test_saved_view_service.py`,
  `backend/rest_api/tests/test_saved_view_views.py`,
  `backend/mcp_server/tests/test_saved_view_tools.py` — gespeicherte Sichten,
  Workspace-Fence, `saved_view.list`/`saved_view.apply` read-only
- `backend/persistence/tests/test_table_views.py` — `0151`/`0152` + RLS
- `e2e/tests/artifact-table.spec.ts` — Tabellen-Flows (überspringt sich mit
  Begründung, wenn der Endpoint nicht deployt ist)

### 3.2 MCP-Modernisierung

- `test_protocol_version_negotiation.py` — Echo unterstützter Revisionen,
  Default `2025-06-18`
- `test_streamable_http_session.py` — `Mcp-Session-Id` aus `initialize`,
  `DELETE /mcp/`, `400 INVALID_REQUEST` bei ungültigem Versions-Header
- `test_resources_capability.py`, `test_prompts_capability.py` —
  `resources/*` und `prompts/*` außerhalb von `tools/list`
- `test_api_key_tool_groups_filter.py`, `test_api_key_scope_gate.py`,
  `backend/rest_api/tests/test_api_key_tool_groups_rest.py` — Curation vs.
  Durchsetzung, Migration `0035`
- `test_introspection_tool_group.py` — `tool.list_groups` immer sichtbar

### 3.3 Bugfixes

- `backend/memory/tests/test_memory_rest.py` — Purge mit `entry_id` → `400`
  statt Datenverlust
- `backend/rest_api/tests/test_document_projection_api.py` — leerer Body →
  `400` statt `500`
- `backend/rest_api/tests/test_issue_workflow_vocabulary_1881.py`,
  `backend/workflow/tests/test_issue_state_vocabulary_lowercase_migration_1881.py`,
  `backend/workflow/tests/test_workflow_vocabulary_consistency_1881.py` —
  Lowercase-Vokabular + Datenmigration `workflow/0027`
- `backend/rest_api/tests/test_audit_finding_standard_ref_1882.py` —
  `standard_ref`/Titel auf Findings
- `TestAllocationCoverageContract` (`backend/rest_api/tests/test_openapi.py`) —
  echtes Coverage-Schema, `coverage_percent`

## 4. Vorbedingungen für einen Nachlauf

```
make up
curl -s http://127.0.0.1:8001/health/live      # 200
curl -s http://127.0.0.1:8001/health/ready     # 200
docker compose -f deploy/docker-compose.yml exec -T backend python manage.py migrate
```

## 5. Abnahme-Checkliste

- [x] Carrier gesetzt: `VERSION` = `1.9.0-beta.2`, 21 Dateien, 40 Zeilen
- [x] Carrier-Ratchet: `scripts/check_plugin_packages.py --expect-version
      1.9.0-beta.2` → OK
- [x] Client-Artefakte: `scripts/clients/render.py --check` → 18 Artefakte OK
- [x] Doc-Surface + Manifest-Drift: `pytest
      docs/agent-templates/test_doc_surface_consistency.py
      docs/agent-templates/test_meta_tool_count_drift.py -q` → 15 passed
- [x] MCP-Manifest: `tool_count` 301, 49 Präfixe; neu `artifact.bulk_transition`,
      `tool.list_groups`, `saved_view.list`, `saved_view.apply`
- [x] `CHANGELOG.md` enthält `## [1.9.0-beta.2] — 2026-11-16` mit
      Added/Changed/Fixed und PR-Nummern
- [x] Drei Breaking-Punkte markiert (`coverage_percent`, Issue-Lowercase,
      MCP `2025-06-18`)
- [x] Release- und Testplan-Bericht liegen unter `docs/se/reports/`
- [x] **Upgrade-Probe geplant** (Abschnitt 6.2)
- [ ] Upgrade-Probe **ausgeführt** — *nicht in diesem Cut gelaufen*
- [ ] Backend-/Frontend-/E2E-Vollsuite gegen diesen Branch — *nicht gelaufen;
      Evidenz sind die CI-Läufe der 11 PRs*
- [ ] DoD-10-Sichtprüfung der Tabellenansicht — *offen, braucht einen Stack*

## 6. Bekannte Grenzen

### 6.1 Kein eigener Suite-Lauf

Der Cut ändert keinen Code. Die Verifikation ist die grüne CI der 11 PRs. Ein
Nachlauf von `make test-backend`, `make test-frontend` und `npm run test:e2e`
bleibt empfohlen, ist aber nicht Teil dieses Berichts.

### 6.2 Upgrade-Probe (Migrationsrisiko `workflow/0027`)

Vor einem Rollout auf eine **Kopie** einer bestehenden Datenbank:

1. Snapshot der Kopie ziehen und die Issue-Zeilen mit
   `state IN ('Open','In Progress','Resolved','Closed','Won't Fix')` zählen.
2. `manage.py migrate workflow` ausführen.
3. Dieselbe Zählung wiederholen — erwartet: 0 Titel-Schreibweisen, dieselbe
   Anzahl Zeilen, andere Item-Typen unverändert.
4. Migration ein zweites Mal laufen lassen (idempotent, keine Änderung).
5. Reverse (`migrate workflow 0026`) auf der Kopie prüfen, bevor irgendetwas
   Produktives angefasst wird.

### 6.3 `check-version-drift.sh` ist kein Carrier-Gate

Das Skript vergleicht den `commit_short` einer **deployten** Umgebung gegen
`origin/main` und verlangt `DEPLOYED_VERSION_URL` (ohne URL `exit 2`). Es läuft
als täglicher Monitor und blockiert keinen Merge.

### 6.4 E2E-Guardrail kann „nichts beweisen"

`artifact-table.spec.ts` überspringt sich mit Begründung, solange
`GET /api/v1/artifacts/table/` in der Zielumgebung nicht antwortet. Das ist
Absicht (kein hohles Grün), heißt aber: in einer Umgebung ohne den Endpoint
belegt der Spec keinen Tabellen-Flow.

### 6.5 Kein Image-Nachweis

Ohne `scripts/build.sh` + `docker-publish.yml` existiert kein Image-/Digest-Beleg
für `1.9.0-beta.2`.

## 7. Freigabe-Urteil

Beta-tauglich im Sinne des Bugfix-Umfangs: alle 11 PRs sind mit grüner CI
gemergt, die Carrier- und Konsistenz-Gates sind lokal grün, und die drei
Breaking-Punkte sind benannt und migriert. **Nicht** abgedeckt: ein erneuter
Vollsuite-Lauf, die visuelle Abnahme der Tabellenansicht und die in
`RELEASE_v1.9.0-beta.2.md` §6.3 gelisteten Residuen. Keine Produktions-,
Staging- oder QA-Freigabe.

---

*Erstellt durch den `release`-Agenten am 2026-11-16. Interne Doku (Deutsch),
keine Secrets. Keine erfundenen Häkchen: jedes **[x]** ist auf einen lokal
ausgeführten Gate-Befehl, eine Datei im Arbeitsbaum oder einen gemergten PR
zurückführbar. Kein Commit/Push/Tag durch den Autor.*
