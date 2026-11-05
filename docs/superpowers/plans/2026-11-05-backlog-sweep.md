# Backlog-Sweep (5 Bündel, 28 Tasks, ~31 Issues) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Offene Bugs, Design-Fehler und Mini-Features aus dem Backlog (56 offene Issues, Stand 2026-11-05) in 5 thematisch geschlossenen PRs abarbeiten; mindestens 20 Issues müssen nach dem Triage-Gate real geschlossen werden.

**Architecture:** Kein neues Subsystem. Jeder Task startet mit einem **Triage-Gate** (Repro gegen `origin/main`): ist das Issue dort schon behoben, wird es mit Kommentar geschlossen und der Task entfällt. Sonst: failing test → minimaler Fix → Commit. Grund für das Gate: ein Teil der „offenen" Issues ist auf `main` bereits ganz oder teilweise erledigt (siehe Abschnitt „Befunde zum Ist-Stand").

**Tech Stack:** Django 6.1 + DRF, pytest, PostgreSQL 16/pgvector, React 19 + TS strict, Vitest.

**Spec:** Je Task der GitHub-Issue-Text (`gh issue view N`). Entscheidungen D1–D8 unten gelten als Spec für die betroffenen Tasks; Defaults sind die jeweils **fett** markierte Empfehlung.

## Global Constraints

- **Alle Arbeit von `origin/main` aus** (aktuell `8cda953f`, `VERSION` 1.8.0-beta.25). Der lokale Checkout (`docs/opencode-v2-support-plan`) liegt **655 Commits zurück** und enthält ungecommittete BluePencil-/Sandbox-Änderungen — weder darauf bauen noch sie einsammeln. Branch-Anlage, `git fetch` und Commits laufen über den `git`-Agenten (Orchestrator-Guard blockt Git im Main-Chat).
- Nie lokales `main` auschecken/resetten.
- Branches: `fix/sweep-api-contracts`, `fix/sweep-data-memory`, `fix/sweep-frontend`, `chore/sweep-release-clients`, `fix/sweep-item-permissions`.
- Commits: Conventional Commits, Englisch, Imperativ, ≤72 Zeichen, `Fixes #N` bzw. `Refs #N` im Body. Trailer: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Keine Model-Queries in DRF-Views (Serializer + Service in `application/`).
- Frontend: `data-testid` auf interaktiven Elementen, nur Tokens aus `styles/tokens.css`, i18n DE **und** EN.
- Backend-Tests lokal mit `DB_USER` = Superuser (RLS-Tests); bekannte rote Tests auf `main` nicht anfassen. Volle Läufe nur **sequentiell** (OOM-Gefahr, ~5,8 GiB RAM).
- `.agent-meta/` nie editieren. Nach Codeänderung `graphify update .`. Scratch nur unter `.tmp/`.
- Code-Anker unten sind Startpunkte, kein Beleg: vor dem Edit `graphify query`/`git grep` auf dem Arbeits-Branch.

## Befunde zum Ist-Stand (gegen `origin/main` geprüft)

- **Schon erledigt/fast erledigt, Issue aber offen:** #1407 DELETE-`change_reason` per Query (`46935e62`), #1386 ReqIF-Embedding (`95b479a7`), #598 W2–W4 (Tokens, i18n, ErrorBoundary), #1287 Markdown-Toolbar-Toggle (`showToolbar` in `MarkdownPreview.tsx`), #1402 teilweise (`bcd348b3`), #1403 teilweise (`link_types` hat FK), #1406 teilweise (Backups-Tabelle `19662f8f`), #1412 teilweise (`0116_index_hygiene_1411`).
- **Reproduziert auf `main`:** #1662 (`VERSION` = beta.25, `frontend/package.json` = beta.22), #1378 (`generate_embedding` pro Eintrag in `memory_admin_service.py:575`), #1668 (keine Filter in OpenAPI).
- **Neu eingeordnet:** #1660 — `check_i1` fängt Selbstbezug an sich ab, läuft aber nur `if is_enabled(INVARIANT_I1)`; Verdacht: Bug nur bei Preset ohne I1 oder in einem anderen Pfad → reproduzieren, bevor gefixt wird.

## Entscheidungen — getroffen am 2026-11-05

D1 Vertrag behalten (GET nach DELETE → 200/`outdated`) · D2 `severity` read-only + klare 400; konfigurierbare Ableitung über den Attribut-Mechanismus kommt als **eigenes Design-Issue** (nicht im Sweep) · D3 gespeichertes Feld / `allocated-to`-Link · D4 400 + Klemmen · D5 Schreiben + `retrieve` · D6 Projektion nur für den aktiven Speicher · D7 nur Hard-off-Slots · **D8 abweichend:** bestehenden OpenCode-Plan **erst gegen #1702–#1706 abgleichen und überarbeiten**, dann ausführen (Task 26 beginnt mit dem Plan-Review). Ausführungsart: offen, **Plan wird noch nicht ausgeführt**.

Die Tabelle unten bleibt als Begründung stehen; die Spalte „Empfehlung" gilt, außer bei D8.

| # | Frage | Empfehlung (Default im Plan) | Betrifft |
|---|---|---|---|
| D1 | Soft-Delete-Vertrag: `main` hat bewusst **GET nach DELETE → 200, `status=outdated`** festgeschrieben (OpenAPI-Text, e2e `4641245d`, „G1.5/#1381 removed the 404 outlier"). Issue #1381 fordert 404. | **Vertrag behalten**, Issue als „by design" schließen, `docs/API.md` präzisieren. Alternative 404 bricht e2e und Restore-Flows. | T7 |
| D2 | Risk-`severity`: Code definiert sie als **abgeleitete** Spalte (RPN, `stage_matrix.py:662-668`, `editable="automation"`), Serializer erlaubt aber Enum-Schreiben, Attribut-Guard verlangt Zahl. Issue will „schreibbar". | **Read-only + eine klare 400-Meldung** („severity is derived from probability × impact"); Eingabe über `probability`/`impact`. Alternative: Enum schreibbar → Ableitung/RPN widersprüchlich. | T4 |
| D3 | `?allocated=` / `?level=`: #1669/#1670 (Design) stellen offen, woraus `level` folgt. | **`level` = gespeichertes Feld filtern, `allocated` = existiert `allocated-to`-Link**; keine Semantikänderung, Design-Epic bleibt separat. | T5, T17 |
| D4 | Paginierung ungültig: `page_size=0/-1/abc`, `offset=…` werden still ignoriert. | **400 `VALIDATION_ERROR`** für ≤0/nicht-numerisch/`offset`; zu großes `page_size` auf Max klemmen und effektiven Wert zurückgeben. | T6 |
| D5 | #1716-Umfang: Write-Check allein ist inkonsistent, wenn Lesen (`retrieve`) dieselbe Regel `none` ignoriert. | **Writes + `retrieve`**; Listen-Filterung als Folge-Issue. | T28 |
| D6 | Memory-Projektion (#1378/#1409): `mem_memory_entry` (pgvector) ist laut #1317 bei `MEMORY_BACKEND=honcho` eine **Waise**. Fix der Projektion wäre sonst am toten Speicher. | **Projektion nur für den aktiven Backend-Speicher**; unter Honcho klarer Hinweis statt Pseudo-Daten. Bitte bestätigen, was die UI heute unter Honcho zeigen soll. | T13, T15 |
| D7 | #1339: nur die „Hard-off"-Slots jetzt, oder das ganze Drei-Ebenen-Feature? | **Nur Hard-off** (`bundle_compression`, `memory.extract`, `interview.transcript_summary`) — Bugfix-Teil. Schalter-Feature bleibt eigenes Issue. | T14 |
| D8 | OpenCode: #1702/#1705/#1706 sind durch den **bereits auf `main` gemergten Plan** `docs/superpowers/plans/2026-11-01-opencode-v2-support.md` (PR #1708, „one shared Streamable HTTP config") abgedeckt. | **Diesen Plan ausführen, nicht neu planen.** Lokale Plan-Version auf `docs/opencode-v2-support-plan` ist veraltet → verwerfen. | T26 |

Nicht entschieden, außerhalb des Sweeps: #1418 (bluepencil im Repo? — im Arbeitsverzeichnis liegt eine halbfertige Umstellung auf flache `/bluepencil/`-Pfade, Besitzer klären), #1669/#1670 (Design-Epic Allokation), #1230 (Roadmap).

## Review Focus

- Selbst-/Zyklus-Parent per PATCH in **jedem** Preset (minimal/standard/extended) und danach lesbarer Baum (T1).
- Unbekannte/ungültige Query-Werte (`allocated=maybe`, `level=9`, `page_size=0`, `offset=3`) → 400, nie stilles 200 (T5, T6).
- Unique-Index-Migration auf Bestand mit Duplikaten bricht kontrolliert ab statt halb zu migrieren (T8).
- `none`-Regel: Schreib- und `retrieve`-Zugriff liefern 404, kein Existenz-Leak über 403 (T28).
- Memory-Projektion mit 0 Einträgen und mit Einträgen ohne Embedding: kein Timeout, kein 500 (T13).

---

## Bündel 1 — API-Verträge (Backend) · Branch `fix/sweep-api-contracts`

Gemeinsames Muster: Fehler- und Filterverträge von REST/MCP. Ein PR, Task = ein Commit.

### Task 1: Architektur-Selbst-/Zyklus-Parent im PATCH (#1660, critical)
**Files:** `backend/application/validators.py` (`check_i1`, `validate_parent_assignment`), `backend/application/architecture_service.py` (Update-Pfad), Test `backend/application/tests/test_architecture_parent_cycle.py`.
- [ ] Gate: PATCH `parent_id == id` je Preset gegen `main` reproduzieren; Ergebnis in den Issue-Kommentar.
- [ ] Failing tests: `test_patch_parent_to_self_rejected_in_all_presets` (parametrisiert minimal/standard/extended → `ValidationError`/REST 400), `test_patch_parent_to_descendant_rejected`, `test_tree_readable_after_rejected_patch` (GET Liste+Detail 200, `parent_id` unverändert), `test_reading_tree_with_preexisting_self_parent_terminates` (korrupte Daten per ORM: Lesen endet, kein 500).
- [ ] Fix: Selbstbezug/Zyklus **unabhängig vom I1-Preset-Flag** ablehnen (Strukturschutz ≠ Rigor-Regel); Lesepfade (Tiefe/Pfad) mit Besuchsmenge begrenzen.
- [ ] Commit `fix(architecture): reject self and cyclic parent in every preset` — `Fixes #1660`.

### Task 2: Doppeltes ICD → 409 (#1661)
**Files:** `backend/rest_api/icd_views.py` (`create`), `backend/icd/icd_manager.py`/`services.py`, Test `backend/rest_api/tests/test_icd_duplicate.py`.
- [ ] Gate: zweimal identischer POST gegen `main`.
- [ ] Test `test_duplicate_icd_returns_409` (Status 409, `error.code` gesetzt, Meldung nennt Source/Target).
- [ ] Fix: Duplikat im Service erkennen bzw. `IntegrityError` in Domain-Exception übersetzen, View mappt auf 409.
- [ ] Commit `fix(icd): answer duplicate ICD with 409` — `Fixes #1661`.

### Task 3: MCP `glossary.create` Dublette strukturiert (#1663)
**Files:** Handler zu `glossary.create` (`backend/mcp_server/tool_registry.py`), `backend/application/glossary_service.py:175` (wirft `ValidationError("…already exists…")`), Test `backend/mcp_server/tests/test_glossary_duplicate_error.py`.
- [ ] Test: zweiter Aufruf → `isError` und Text enthält `DUPLICATE_TERM`; nicht „An internal error occurred".
- [ ] Fix: Service-Duplikat auf stabilen Code mappen (kleiner dedizierter Subtyp statt String-Match); `test_tool_manifest_drift.py` bleibt grün.
- [ ] Commit `fix(mcp): return DUPLICATE_TERM for duplicate glossary.create` — `Fixes #1663`.

### Task 4: Risk-`severity` konsistent ablehnen (#1707, nach D2)
**Files:** `backend/rest_api/serializers.py` (RiskSerializer.severity), `backend/attribute_definitions/stage_matrix.py:666`, `backend/application/risk_service.py`, Test `backend/rest_api/tests/test_risk_severity_contract.py`.
- [ ] Tests: `severity` in POST/PATCH → 400 mit **identischer** Meldung für `"high"` und `7`; Lesen liefert weiter abgeleiteten Wert; Änderung von `probability`/`impact` ändert `severity`.
- [ ] Fix: Serializer-Feld `read_only`, Schreibversuch erzeugt die eine Meldung (kein „must be a number" / „not a valid choice" mehr).
- [ ] Commit `fix(risk): make derived severity read-only with a clear error` — `Refs #1707`. Issue bleibt offen, bis das Folge-Issue „Abgeleitete Attribute konfigurierbar über den Attribut-Mechanismus" (Regeln, Einstellung, Bereitstellung) angelegt und verlinkt ist; Anlage über den `feedback`-Agenten.

### Task 5: Filter `allocated`/`level` + 400 bei Müllwerten (#1668, nach D3)
**Files:** Requirements-`list` (`backend/rest_api/views.py`), `backend/rest_api/query_params.py` (`parse_enum_param`), `backend/application/requirement_service.py` (Exists-Subquery auf `allocated-to`), MCP `requirement.query`, Tests `backend/rest_api/tests/test_requirement_filters.py`, `backend/mcp_server/tests/test_requirement_query_filters.py`.
- [ ] Tests: `allocated=true|false`, `level=2`; `allocated=maybe`/`level=9` → 400 mit Parametername; MCP-Spiegel. Kein N+1.
- [ ] Manifest/OpenAPI aktualisieren (`export_tool_manifest`).
- [ ] Commit `feat(requirements): add allocated and level filters` — `Refs #1668` (Issue schließt mit Task 17).

### Task 6: Pagination strikt + Traceability-Index (#1407-Rest, nach D4)
**Files:** zentrale Paginator-Klasse + `backend/rest_api/query_params.py` (`parse_pagination`), `backend/rest_api/urls.py` (`traceability`-Registrierung), Tests `backend/rest_api/tests/test_pagination_params.py`, `test_traceability_index.py`.
- [ ] Gate: DELETE-Query-Parameter ist bereits gemergt (`46935e62`) — nur Rest prüfen.
- [ ] Tests: `page_size=0|-1|abc` → 400; `offset=3` → 400; `page_size=1000000` → geklemmt, Antwort nennt effektiven Wert; `GET /api/v1/traceability/` → 200 (Index der Unterressourcen), `OPTIONS` mit `Allow`.
- [ ] Commit `fix(api): validate pagination params and serve traceability index` — `Fixes #1407`.

### Task 7: Soft-Delete-Vertrag festschreiben (#1381, nach D1)
**Files:** `docs/API.md`, OpenAPI-Beschreibung der DELETE-Operationen, Test `backend/rest_api/tests/test_soft_delete_contract.py` (parametrisiert über die 8 Typen: DELETE→204, GET→200 mit `status=outdated`, Liste ohne Eintrag, `include_deleted=true` mit Eintrag).
- [ ] Test beweist den einheitlichen Vertrag über **alle** Typen (heute nur Architektur gepinnt).
- [ ] Commit `test(api): pin uniform soft-delete contract for all artifact types` — `Fixes #1381` + Kommentar „by design".

---

## Bündel 2 — Daten & Memory · Branch `fix/sweep-data-memory`

Gemeinsames Muster: Migrationen (fortlaufend nummerieren, nur ein Autor je Migrationskette im PR) und Memory-Backend-Korrektheit.

### Task 8: `uid`-Unique-Constraints für die restlichen Tabellen (#1402)
**Files:** neue Migration(en); Muster `0055_requirement_workspace_uid_constraint.py`; Test `backend/persistence/tests/test_uid_unique_constraints.py`.
- [ ] Gate: per `pg_indexes` auf frischer Test-DB prüfen, welche der 7 Tabellen (`pl_testcase`, `pl_architecture_element`, `pl_stakeholder_need`, `as_adr`, `as_risk`, `as_issue`, `pl_test_run`) nach `bcd348b3` noch keinen Constraint haben.
- [ ] Tests je verbleibender Tabelle: gleiche `(workspace, uid)` → `IntegrityError`; anderer Workspace ok; leere/NULL-`uid` mehrfach ok.
- [ ] Migration mit Duplikat-Preflight (`RunPython`, klare Abbruchmeldung), `AddIndexConcurrently`/`atomic=False`, Reverse vorhanden.
- [ ] Commit `fix(db): enforce per-workspace uid uniqueness` — `Fixes #1402`.

### Task 9: Workspace-Waisen (#1403)
**Files:** `ad_workspace_definition`, `as_domain_event_outbox` (Gate: `lt_workspace_definition` hat laut `link_types/models.py:61` bereits FK), Workspace-Löschpfad, Test `backend/persistence/tests/test_workspace_delete_cleanup.py`.
- [ ] Test: Workspace löschen → keine Zeilen der betroffenen Tabellen mit dessen ID. Data-Migration räumt Bestand (Count ins Log).
- [ ] Definitionen per FK `CASCADE`; Outbox bleibt FK-frei, Cleanup im Löschpfad (Events müssen nach Löschung zustellbar bleiben).
- [ ] Commit `fix(db): clean workspace-scoped rows on workspace delete` — `Fixes #1403`.

### Task 10: Leerer Scope als NULL, Interview-Waisen (#1412)
**Files:** Baseline-Waiver-/Snapshot-Modelle, `pl_interview_session`, Test `backend/baseline/tests/test_scope_artifact_null.py`.
- [ ] Gate: Round-6-Merge `2be05595` hat Indizes geliefert — Rest gegen Issue-Liste abgleichen.
- [ ] Test: Waiver ohne Scope speichert `NULL`; Roundtrip liefert `null`; Migration normalisiert Bestand und entfernt Waisen.
- [ ] Commit `fix(baseline): store empty scope as NULL` — `Fixes #1412`.

### Task 11: Listen-Index `(workspace_id, created_at DESC)` (#1400)
**Files:** Migration (Gate: `0116_index_hygiene_1411` deckt nur `(created_at, id)`), Test `backend/persistence/tests/test_artifact_list_index.py`.
- [ ] Test: Index per `pg_indexes` vorhanden (kein Plan-Assert, Planner-abhängig); EXPLAIN vorher/nachher in den PR-Text.
- [ ] Commit `perf(db): index artifact list by workspace and created_at` — `Fixes #1400`.

### Task 12: ReqIF-Import vergibt `uid` + Backfill (#1386-Rest)
**Files:** `backend/application/reqif_import_service.py`, Management-Command `backfill_requirement_uid`, Test `backend/application/tests/test_reqif_import_uid.py`.
- [ ] Gate: Embedding-Teil ist gemergt (`95b479a7`); nur `uid` prüfen.
- [ ] Tests: Import → jede Requirement hat `uid` (workspace-lokal fortlaufend, keine Kollision); Re-Import erzeugt keine Duplikate; Command idempotent mit `--dry-run`.
- [ ] Commit `fix(reqif): assign uid on import and backfill existing rows` — `Fixes #1386`.

### Task 13: Memory-Projektion ohne Remote-Call pro Eintrag (#1378, nach D6)
**Files:** `backend/application/memory_admin_service.py:525-605`, Test `backend/application/tests/test_memory_projection_stored_embedding.py`.
- [ ] Test: `generate_embedding` gemockt mit `assert_not_called()`; Einträge mit gespeichertem Vektor werden projiziert, ohne Vektor zählen in `excluded_no_embedding`; Sampling vor jeder teuren Arbeit.
- [ ] Commit `perf(memory): read stored embeddings for projection` — `Fixes #1378`.

### Task 14: Hard-off-Slots für Memory-Injektion (#1339-Teil, nach D7)
**Files:** `prompt_slots.py` (`HARD_OFF`), `context_builder`/`build_memory_context(..., slot_name=None)`, `_DATA_VARIABLES_BY_SLOT`, Test `backend/application/tests/test_memory_hard_off_slots.py`.
- [ ] Test: für `bundle_compression`, `memory.extract`, `interview.transcript_summary` bleibt `memory_context` leer, auch bei aktivem Workspace-Memory; Konsistenz-Slots (`need_to_sysreq` …) unverändert.
- [ ] Commit `fix(memory): never inject memory into compression and extraction` — `Refs #1339`.

### Task 15: Backend-Wechsel-Doku + Projektion-Scope (#1317, #1409)
**Files:** `docs/` Betriebs-Runbook (Backend-Wechsel, Verhalten der pgvector-Altdaten, Kopplung `EMBEDDING_*` ↔ `HONCHO_EMBEDDING_*` mit Dimensionscheck), Projektions-Filter in `memory_admin_service.py`, Test `test_memory_projection_scope.py`.
- [ ] Test: `scope=workspace` enthält keine `owner_type='user'`-Punkte.
- [ ] Commit `fix(memory): keep user entries out of workspace projection` — `Fixes #1409`, `Refs #1317` (Doku-Teil schließt #1317).

---

## Bündel 3 — Frontend · Branch `fix/sweep-frontend`

### Task 16: ICD-Detailseite stürzt ab (#1709)
**Files:** `frontend/src/components/IcdView/IcdDetailPane.tsx` (+ `IcdLinkedElements.tsx`), Test `IcdDetailPane.parameters.test.tsx`.
- [ ] Test: Parameter-Objekt `{name,unit,data_type,direction}` → Felder sichtbar, kein Throw; leere Liste ok. Fix: Felder einzeln rendern, `data-testid="icd-parameter-row"`.
- [ ] Commit `fix(icd-ui): render parameter fields instead of object` — `Fixes #1709`.

### Task 17: Filter „Allokiert / Nicht allokiert" in der Requirement-Liste (#1668-UI)
**Consumes:** Task 5 (`allocated`). **Files:** Requirement-Liste + `frontend/src/api/`, i18n DE/EN, Test `allocationFilter.test.tsx`.
- [ ] Test: Auswahl „Nicht allokiert" ruft API mit `allocated=false`; Zähler `data-testid="requirements-unallocated-count"`.
- [ ] Commit `feat(requirements-ui): filter by allocation` — `Fixes #1668`.

### Task 18: A11y-Reste (#1406)
**Files:** `frontend/src/components/SplitView/` (Divider-Trefferfläche ≥ 24 px, `aria-valuenow`), System-Settings-Tabelle (`caption`/`scope`), Tests im jeweiligen Ordner.
- [ ] Gate: Backups-Tabelle ist schon gefixt (`19662f8f`) — nur Divider und System-Settings-Tabelle.
- [ ] Commit `fix(a11y): enlarge split divider hit area and label settings table` — `Fixes #1406` (BluePencil-Dialoge im Befund gehören nicht zur App).

### Task 19: ID-Chip kopiert die System-ID (#1094, #1287-Abgleich)
**Files:** Gate zuerst: was existiert in `display-preferences.ts`/`PreferencesHydrator.tsx` und `MarkdownPreview.tsx` (`showToolbar`)? Neu nur, was fehlt: `IdChip({ uid: string; id?: string })` — Copy kopiert `id` (UUID), Fallback `uid` mit Hinweis; Sichtbarkeit der lesbaren ID als **serverseitige** Display-Preference (nicht localStorage). Test `IdChip.test.tsx`.
- [ ] Ergebnis: #1287 schließen, wenn der Toolbar-Toggle reicht; sonst Persistenz als Display-Preference ergänzen.
- [ ] Commit `feat(ui): add IdChip copying the system ID` — `Fixes #1094`, ggf. `Fixes #1287`.

### Task 20: Redirect-Aliase für alte Routen (#598-S4)
**Files:** `frontend/src/components/NavigationShell/NavigationShell.tsx` (Catch-all `path="*"`), Test `legacyRedirects.test.tsx`.
- [ ] Test: `/trace-links` → `/traceability`, `/test-cases` → Nachfolgeseite statt Dashboard. Commit `fix(routing): redirect legacy trace-links and test-cases routes` — `Refs #598`.

### Task 21: Trace-Ziel ohne Typ-Probe-Request (#598-W1/S6)
**Files:** `frontend/src/api/artifactRefs.ts` (`resolveArtifactRef`).
- [ ] Test: Auflösung nutzt `source_type/target_type`/`*_title` des TraceLink; `artifactsApi.get` wird nicht aufgerufen (Mock `not.toHaveBeenCalled`). Commit `perf(trace-ui): resolve refs from link metadata, not a probe GET` — `Refs #598`.

### Task 22: WorkflowEditor-Header-Overflow + CTA-Varianz (#598-W5/S5)
**Files:** `WorkflowEditor.module.css` (`.header`: `flex-wrap`, `min-width:0`), CTA-Labels `Create Run`/`Add term` auf `New …`-Muster (i18n DE/EN).
- [ ] Gate: Overflow bei schmaler Breite messen (Vitest/Playwright-Snapshot). Commit `fix(ui): wrap workflow header and unify create CTAs` — `Fixes #598` (wenn alle Punkte W1–W5/S4–S6 erledigt, sonst `Refs`).

### Task 23: Inspector (Version/History/Diff) für ADR und Risk (#801, stretch)
**Files:** bestehende Inspector-Komponente der Requirements-Ansicht wiederverwenden (Gate: Version-API der ADR/Risk-Endpunkte vorhanden?), Test je Typ. Nur ADR + Risk in diesem Sweep; übrige 4 Typen als Folge-Issue.
- [ ] Commit `feat(ui): show version history inspector for ADRs and risks` — `Refs #801`.

### Task 24: npm-Audit katex/mermaid (#1404-Frontend)
**Files:** `frontend/package.json`/`package-lock.json`.
- [ ] `npm audit --omit=dev` Baseline; Bump; `npx vitest run src/components/mermaid` + `npm run build` grün. Lässt sich nur per Major-Sprung beheben: Kommentar „blockiert", Task entfällt. Commit `chore(deps): bump mermaid and katex` — `Refs #1404`.

---

## Bündel 4 — Release & Clients · Branch `chore/sweep-release-clients`

### Task 25: Versionsträger konsistent + CI-Gate (#1662)
**Files:** `scripts/bump_version.py`, `scripts/test_bump_version.py`, neu `scripts/check_version_carriers.py`, CI-Step im Release-Workflow.
- [ ] Gate bestätigt: `main` hat `VERSION` 1.8.0-beta.25, `frontend/package.json` beta.22.
- [ ] Tests: `bump` setzt alle Träger (VERSION, `frontend/package.json` + Lockfile, Backend-Metadaten); `check_version_carriers` Exit 1 bei Abweichung. Träger jetzt auf die aktuelle Version heben.
- [ ] Commit `fix(release): gate tags on consistent version carriers` — `Fixes #1662`.

### Task 26: OpenCode 2 — bestehenden Plan ausführen (#1702, #1703, #1704, #1705, #1706, nach D8)
- [ ] **Plan-Review zuerst (D8):** `docs/superpowers/plans/2026-11-01-opencode-v2-support.md` von `origin/main` gegen #1702 (Config auf `/mcp/`), #1703 (Test gegen echten Endpunkt), #1704 (Code-Mode vs. 248 Tools), #1705 (CI/Docs) und #1706 (`subagent_depth`) abgleichen; Lücken im Plan ergänzen, Ergebnis als Commit auf dem Plan. Erst danach Tasks 0–6 ausführen. Keine Parallelarbeit an `clients/registry.yaml`.
- [ ] #1706 (`subagent_depth` aus `.agent-meta/opencode.json`): nur Upstream-Issue + Doku, Submodul bleibt unberührt.
- [ ] Abschluss: `Fixes #1702 #1703 #1705`, #1704/#1706 mit Befund-Kommentar.

---

## Bündel 5 — Security · Branch `fix/sweep-item-permissions`

Eigener PR: Autorisierungslogik, soll separat reviewt und gemerged werden.

### Task 28: ItemPermission auf Schreib- und `retrieve`-Pfaden erzwingen (#1716, nach D5)
**Files:** `ServiceBase._assert_write_permission` (`backend/application/services.py`), `backend/auth_tenancy/services/item_permission.py` (`check_permission`), `backend/application/effective_permission_service.py`, Test `backend/application/tests/test_item_permission_write.py`.
- [ ] Gate: Befund aus Issue (nur RBAC auf Update) auf `main` bestätigen.
- [ ] Tests (parametrisiert: Requirement, Architektur, Risiko, TestCase, ADR, Glossar, Need, Issue + MCP `requirement.update`): Regel `read` → Schreiben abgelehnt; `none` → Schreiben **und** `retrieve` 404; Artefakt-Regel schlägt Workspace-Regel; ohne Regel unverändert; Regel erweitert nie RBAC.
- [ ] Fix zentral in `_assert_write_permission` plus ein gemeinsamer Check im Retrieve-Mixin; Bulk-Updates ohne N+1 (Query-Zähler-Test).
- [ ] Commit `fix(authz): enforce ItemPermission on write and retrieve paths` — `Fixes #1716`.

---

## Abschluss je Bündel

- [ ] Backend-Suite, dann Frontend-Suite, dann betroffene E2E-Shards — nacheinander.
- [ ] `graphify update .`; PR über `git`-Agent; jedes Issue mit Kurzkommentar (Ergebnis + Test) schließen.
- [ ] Nach Bündel 3: `documenter` für `CODEBASE_OVERVIEW.md`.

## Self-Review

- **Abdeckung:** Issues (Auswahl, 33 Nummern): #1660 #1661 #1663 #1707 #1668 #1407 #1381 | #1402 #1403 #1412 #1400 #1386 #1378 #1339 #1317 #1409 | #1709 #1406 #1094 #1287 #598 #801 #1404 | #1662 #1702 #1703 #1704 #1705 #1706 | #1716. Davon Gate-Kandidaten, die evtl. nur geschlossen werden: #1407, #1386, #1287, #598, #1381 → Untergrenze ≥ 20 echte Schließungen bleibt realistisch.
- **Typ-/Interface-Konsistenz:** Task 17 konsumiert `allocated` aus Task 5; Task 26 hängt nur am externen Plan. Sonst unabhängig.
- **Nummerierung:** Task 27 entfällt bewusst (Hermes-Plugin #1701 ist ein eigenes Feature, siehe „nicht im Sweep"); die Lücke ist gewollt.
- **Nicht im Sweep:** #18, #186, #587, #879, #946, #1230, #1314–#1316, #1334, #1336–#1337, #1374, #1399, #1401, #1418, #1564, #1578, #1669/#1670, #1701, #85, #1247/#1153 (Honcho-Infra), #1404-Celery-DNS, #1408/#1410/#1411.
