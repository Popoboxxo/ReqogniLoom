# Phase G — Dokumente und Milestones Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** #879 als erledigt belegen und schließen. #1374 Stufe S3 umsetzen (Projektion von Loom-Dokumenten als Markdown und Adoption von Repo-Dokumenten), mit Zustellung durch CI und Agenten statt durch den Server, und die Agentendefinition als Teil der Harness-Plugin-Skills ausliefern. Danach #1374 schließen.

**Architecture:** Der Server rendert und prüft nur: ein deterministischer Generator (`DocumentProjectionService`) erzeugt je Dokument Dateipfad und Markdown samt Hash, ein Statusabgleich vergleicht Hashes aus dem Repo mit dem Loom-Stand, `document.adopt` schaltet ein Repo-Dokument auf Loom-first. Das Schreiben ins Repo, Branch und Pull Request übernehmen ein CI-Job (`scripts/clients/project_documents.py`) oder ein Agent. Der Server hält keine Repo-Zugangsdaten. Die Agentendefinition `document-steward` mit dem Prozess-Skill `document-projection` liegt in `docs/agent-templates/` und wird über die bestehende Verteilkette in alle Harness-Plugins gerendert.

**Tech Stack:** Django 6.1/DRF, `persistence.models.Document`, `application/document_service.py`, MCP (`mcp_server/tools/`), Python-Stdlib-CLI, GitHub Actions, Agent-Templates (`docs/agent-templates/`, `package_skills.py`, `dist/plugins/claude-code/build_claude_plugin.py`, `scripts/clients/render.py`), pytest, `gh` (`export PATH=$PATH:~/.local/bin`).

**Spec:** `docs/superpowers/plans/2026-11-10-backlog-roadmap.md` Phase G, Entscheidungen 11 und 12. Konzept: `docs/concepts/2026-10-16-dokument-artefakte-workitem.md` §7 (Dual-Source, Generator, Konfliktregeln), `docs/se/ADR/ADR-026_document_artefakt.md`.

## Entscheidungen (Daniel, 2026-11-10)

| # | Entscheidung |
|---|---|
| 11 | #879: erst prüfen, was gebaut ist. Ergebnis der Prüfung: vollständig gebaut, schließen |
| 12 | #1374: Stufe 1 war "Document + Kanten + Import"; die Triage zeigt S1, S2, S4 als gebaut. Offen ist S3 |
| 12b | S3: **Generator und Adoption im Server. Zustellung durch CI und Agenten, kein Server-Push.** Die Agentendefinition soll Teil der Skills der Harness-Plugins sein |

## Befund (origin/main 3563515f, Code seit 4f8aa29f unverändert)

| Teil | Stand | Beleg |
|---|---|---|
| #879 Milestone | **gebaut** | `persistence/models.py:5109` `Milestone` (Name, Zieldatum, Status, Review-Typ SRR/PDR/CDR/TRR/ORR/OTHER, `audit_snapshot`, `baseline` PROTECT), `application/milestone_service.py`, REST `milestones` (`rest_api/urls.py:301`), MCP `milestone.create/update/bind_baseline/record_audit` (`mcp_server/tool_registry.py:334-337`), UI `frontend/src/components/BaselinesView/MilestoneList.tsx`, `queries/milestones.ts` |
| #1374 S1 Modell, Lifecycle, Freeze | **gebaut** | `Document` (`models.py:4678`, `frozen_at`, `frozen_fields`, `uid`, `kind`, `body`, `doc_date`), `WorkItem` (`:4808`, Kinds Phase/Step/Milestone/OpenPoint/Checkpoint), `document_service.py` (`release`, `reopen`, `supersede`), Link-Vokabeln `resolves/blocks/threatens` in `link_types/builtin.py` |
| S2 Vollzugriff | **gebaut** | REST `documents`, `work-items`; MCP `document.*` und `work_item.*`; Events `DOCUMENT_*`, `ITEM_*` (`application/models.py:146-160`); `inline_anchor_service.py`, `InlineAnchor` |
| S4 Agenten-Zustandsspeicher | **gebaut** | `work_item_service.py` (resume, Checkpoints, Heartbeat, `blocked_reason`) |
| S3 Projektion und Adoption | **offen** | `Document` hat bewusst keine Felder `owner_mode`, `source*`, `projection_mode` ("ENT-F5 = a", `models.py:4697`, `document_service.py:38`). Es gibt `document.project`/`document.adopt` nicht. Scopes `documents:project/adopt` (Konzept) gibt es nicht, API-Keys kennen `read/write/admin` |
| Import von Altbestand | teilweise | `application/management/commands/migrate_se_docs.py` importiert `docs/se/` als Artefakte (Needs, Requirements, Architektur, ADR), nicht als `Document` |
| Überschneidung Milestone | **geklärt** | `Milestone` (Review-Planung mit Audit-Snapshot und Baseline) und `WorkItem.Kind.MILESTONE` (Knoten im Arbeitsstand) sind verschiedene Konzepte. Es gibt keine Doppelung, nur Doku-Bedarf |

## Global Constraints

- Branch von `origin/main` (Fetch nur mit `git fetch origin +refs/heads/main:refs/remotes/origin/main`). Git-Mutationen nur über den `git`-Agenten. Commits englisch, Conventional Commits, höchstens 72 Zeichen, Trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` und `Claude-Session: https://claude.ai/code/session_01JYx6yrB2hSodcXeSkA5mAq`. Commit-Nachricht als Datei vorgeben und mit `git commit -F` verwenden.
- **Der Server schreibt nie ins Repo.** Keine Git-Bibliothek, keine Repo-Zugangsdaten, kein Token im Backend. Zustellung ausschließlich als Branch plus Pull Request durch CI oder Agent, nie Push auf `main` (Hausregel).
- Der Generator ist deterministisch: stabile Sortierung, keine Zeitstempel, festes Zeilenende (`\n`), sonst sind Diffs im Repo nicht möglich (Konzept §7.3).
- Konflikte sind fail-loud (Konzept §7.2): eine abweichende Projektionsdatei wird gemeldet, nie still übernommen.
- Neue MCP-Tools (`document.project`, `document.adopt`, `document.projection_status`) erhöhen die Tool-Zahl von 290 auf 293. `python manage.py export_tool_manifest` ausführen, die Zähler in `.meta-config/project.yaml`, `CLAUDE.md`/`AGENTS.md` und Doku über die vorhandenen Zähler-Gates (`docs/agent-templates/test_meta_tool_count_drift.py`, `test_doc_surface_consistency.py`) nachziehen. Die Gates sagen, wo. Zähler nicht von Hand raten.
- Berechtigungen: `project` und `projection_status` lesen (wie `document.read`), `adopt` ist eine schreibende Governance-Aktion (wie `document.transition`). Keine neuen Scopes, die vorhandene Operationszuordnung (`required_scope_operation`) verwenden.
- Neue Spalten sind rückwärtskompatibel: Defaults entsprechen dem heutigen Verhalten (`owner_mode=loom`, `projection_mode=none`).
- Alle Verteil-Artefakte (`dist/`) entstehen aus `docs/agent-templates/` per Generator, nie von Hand. `python scripts/clients/render.py --check` und die Tests unter `docs/agent-templates/` und `dist/` müssen grün sein.
- Backend-Tests lokal mit `DB_USER` auf dem Superuser. Volle Läufe sequentiell. Schließen von Issues erst nach Freigabe durch Daniel.

## Review Focus

- Nicht deterministische Ausgabe: gleicher Stand, zwei Läufe, verschiedene Bytes (Reihenfolge von Kanten, Zeilenenden, Datum). Test: Task 2, zweimal rendern, byteidentisch; Reihenfolge der Eingabedaten gemischt, gleiche Ausgabe.
- Stille Überschreibung: Projektion ersetzt eine von Hand geänderte Repo-Datei. Test: Task 2, `projection_status` meldet `file_changed` statt `in_sync`, der CLI-Lauf schreibt dann nichts und endet mit Fehlercode.
- Beide Seiten geändert: Test: Task 2, Status `conflict`, `adopt` verweigert.
- Adoption ohne Hash-Gleichheit: Test: Task 2, `adopt` mit abweichendem Hash liefert 409, schaltet nichts um.
- Eingefrorenes Dokument: Projektion oder Adoption ändert ein freigegebenes Dokument. Test: Task 2, `FIELD_FROZEN` bleibt gültig, Adoption mit `freeze=True` friert genau den Stand ein.
- Tote Verweise und Glossarbegriffe: Test: Task 2, toter Anker erscheint als Klartext mit Warnhinweis, nicht als kaputter Link.
- Pfad-Escape: Dokumenttitel erzeugt `../` oder einen absoluten Pfad. Test: Task 2, Pfadbildung begrenzt auf den Zielordner, keine `..`-Segmente, ASCII-Slug.
- Rechte: Lesender Key ruft `adopt` auf. Test: Task 3, 403 für `adopt` mit Read-Key, `project` mit Read-Key erlaubt.
- CI-Job schreibt auf `main`: Test: Task 4, das Skript verweigert, wenn der aktuelle Branch `main` oder `master` ist.

---

### Task 1: #879 belegen und schließen

**Files:**
- Modify: `docs/agent-templates/DOMAIN_MODEL.md` (Abgrenzung Milestone ↔ WorkItem Milestone)

**Interfaces:** Produces: Abnahmeliste, Schließ-Kommentar.

- [ ] **Step 1: Akzeptanzkriterien aus #879 prüfen**

DoD 1: Entität `Milestone` mit Name, Zieldatum, Status, Review-Typ. DoD 2: Baselines und SE-Auditor-Läufe daran bindbar.
Run: `cd backend && DB_USER=<Superuser> python -m pytest application/tests -k "milestone" persistence/tests -k "milestone" mcp_server/tests -k "milestone" -q`
Expected: grün. Fundstellen: `bind_baseline` und `record_audit` im Service. Frontend: `cd frontend && npx vitest run src/components/BaselinesView -t Milestone`.

- [ ] **Step 2: Abgrenzung dokumentieren**

In `DOMAIN_MODEL.md` zwei Sätze: `Milestone` plant formale Reviews und trägt Audit-Snapshot und Baseline, `WorkItem` mit Kind `Milestone` ist ein Knoten im Arbeitsstand eines Plans. Beide haben keine automatische Kopplung. Danach die Verteilung neu erzeugen (Task 5 Step 5 beschreibt die Befehle).

- [ ] **Step 3: Schließen (nach Freigabe)**

```bash
gh issue close 879 --reason completed --comment "Erledigt in Plan B B6 (#879, ENT-B2 = a): Entität Milestone (Name, Zieldatum, Status, Review-Typ SRR/PDR/CDR/TRR/ORR/OTHER), Baseline-Bindung (milestone.bind_baseline) und Audit-Snapshot (milestone.record_audit), REST /api/v1/milestones/, MCP milestone.*, UI BaselinesView/MilestoneList. Der Kommentar vom 2026-09 ('Nichts implementiert') ist überholt. Abgrenzung zu WorkItem.Kind.MILESTONE in docs/agent-templates/DOMAIN_MODEL.md."
```

- [ ] **Step 4: Commit** (über `git`-Agent): `docs(domain): distinguish review milestones from work item milestones`

---

### Task 2: Server — Projektion, Statusabgleich, Adoption

**Files:**
- Modify: `backend/persistence/models.py:4678` (`Document` um Felder erweitern)
- Create: `backend/persistence/migrations/<nächste>_document_projection_fields.py`
- Create: `backend/application/document_projection_service.py`, `backend/application/document_projection_render.py` (Renderer, reine Funktionen)
- Modify: `backend/application/document_service.py` (`create_document`, `update_document`: Felder `owner_mode`, `source_path`, `source_sha256`, `projection_mode` annehmen)
- Modify: `backend/application/models.py:146` (Ereignis `DOCUMENT_ADOPTED`)
- Test: `backend/application/tests/test_document_projection.py`, `backend/application/tests/test_document_adoption.py`

**Interfaces:**
- Consumes: `Document` (`uid`, `title`, `kind`, `description`, `body`, `doc_date`, `frozen_at`), `InlineAnchor` (Anker im Text), `GlossaryTerm`, `TraceLink` (Kantenliste), `DocumentService.release/get_document`.
- Produces:
  - Neue `Document`-Felder: `owner_mode` (`loom|repo_external`, Default `loom`), `source_path` (`CharField(512, blank=True)`), `source_sha256` (`CharField(64, blank=True)`), `projection_mode` (`generated|none`, Default `none`), `projected_sha256` (`CharField(64, blank=True)`), `projected_version` (`PositiveInteger`, null).
  - `@dataclass(frozen=True) class ProjectedDocument: path: str; content: str; sha256: str; version: int; state: str; warnings: tuple[str, ...]`
  - `render_document(document: Document, *, anchors: Sequence[InlineAnchor], edges: Sequence[TraceLinkRow], glossary: Mapping[str, str]) -> tuple[str, tuple[str, ...]]` (reine Funktion: Markdown und Warnungen)
  - `projection_path(document: Document) -> str`: `docs/<Ordner je kind>/<doc_date>-<slug(title)>.md`; Ordner je Kind: Spec `docs/superpowers/specs`, Plan `docs/superpowers/plans`, AuditReport `docs/audit`, Review `docs/reviews`, Concept `docs/concepts`, Conclusion `docs/conclusions`, Guide `docs/guides`; `source_path` hat Vorrang, wenn gesetzt. Slug: ASCII, Kleinbuchstaben, `-`, höchstens 80 Zeichen, keine `..`, kein führendes `/`.
  - `DocumentProjectionService.project(document_id: UUID, ctx: AuthContext) -> ProjectedDocument`
  - `DocumentProjectionService.status(workspace_id: UUID, files: Mapping[str, str], ctx: AuthContext) -> list[ProjectionStatusRow]` mit `files` = Pfad → SHA-256 der Repo-Datei (der Client hasht lokal, der Server sieht nie Repo-Inhalt). `ProjectionStatusRow.state` ∈ `in_sync | loom_changed | file_changed | conflict | missing_in_repo | untracked_in_loom`.
  - `DocumentProjectionService.confirm(document_id: UUID, sha256: str, ctx: AuthContext) -> None` (Client meldet den geschriebenen Hash, setzt `projected_sha256`/`projected_version`)
  - `DocumentProjectionService.adopt(document_id: UUID, *, file_sha256: str, source_path: str, freeze: bool, ctx: AuthContext) -> Document`: verlangt `owner_mode=repo_external` und `file_sha256 == source_sha256`, sonst `AdoptionHashMismatchError` (409). Die Fehlerklasse ist neu: `class AdoptionHashMismatchError(ValidationError)` in `application/base.py` mit `error_code = "CONFLICT"`, `http_status = 409` nach dem Muster von `AllocationConflictError` (`base.py:162`), und im 409-Mapping der REST-Schicht (`rest_api/views.py`, Abbildung `…: status.HTTP_409_CONFLICT`) und der MCP-Fehlerzuordnung (`mcp_server/tools/base.py:457` `map_tool_exception`) registriert. Setzt `owner_mode=loom`, `projection_mode=generated`, optional `DocumentService.release(...)`. Ereignis `DOCUMENT_ADOPTED`.
- Kopfzeile der erzeugten Datei (Konzept §7.3), ohne Zeitstempel:
  ```
  <!-- GENERATED by ReqogniLoom — do not edit.
       document: <uid> · version <v> · state <state> · hash <sha256-des-Inhalts-ohne-Kopfzeile>
       regenerate: reqlo project <uid>   (oder MCP: document.project) -->
  ```

- [ ] **Step 1: Failing Tests für den Renderer**

```python
def test_render_is_byte_identical_across_runs_and_input_order(doc, anchors, edges):
    a, _ = render_document(doc, anchors=anchors, edges=edges, glossary={})
    b, _ = render_document(doc, anchors=list(reversed(anchors)), edges=list(reversed(edges)), glossary={})
    assert a == b and "\r" not in a

def test_header_carries_uid_version_state_and_hash(doc): ...
def test_dead_anchor_renders_as_plain_text_with_warning(doc_with_dead_anchor):
    text, warnings = render_document(...); assert "dead reference" in warnings[0] and "](" not in dead_line(text)

def test_glossary_terms_become_links_and_term_list_is_appended(...): ...
def test_edges_without_text_anchor_are_listed_at_the_end(...): ...
def test_projection_path_is_confined(doc_title="../../etc/passwd"): assert ".." not in projection_path(doc) and not projection_path(doc).startswith("/")
def test_source_path_wins_when_set(...): ...
```
Run: `cd backend && DB_USER=<Superuser> python -m pytest application/tests/test_document_projection.py -q` — Expected: FAIL, Modul fehlt.

- [ ] **Step 2: Modell, Migration, Renderer**

Felder und Migration (additiv, Defaults wie oben, kein Backfill nötig). Renderer als reine Funktionen ohne Datenbankzugriff. Sortierung: Anker nach `ordinal` dann ID, Kanten nach Typ dann Ziel-UID, Glossar alphabetisch.

- [ ] **Step 3: Failing Tests für Service, Status und Adoption**

```python
def test_status_in_sync_when_hashes_match(...): assert row.state == "in_sync"
def test_status_file_changed_when_repo_differs_and_loom_unchanged(...): assert row.state == "file_changed"
def test_status_loom_changed_when_version_moved_after_projection(...): assert row.state == "loom_changed"
def test_status_conflict_when_both_changed(...): assert row.state == "conflict"
def test_status_missing_in_repo_does_not_delete_document(...): ...
def test_adopt_requires_matching_hash(...): with pytest.raises(AdoptionHashMismatchError): adopt(file_sha256="x"*64, ...)
def test_adopt_switches_owner_and_projection_mode(...): ...
def test_adopt_with_freeze_releases_document(...): assert doc.frozen_at is not None
def test_adopt_of_loom_owned_document_is_rejected(...): ...
def test_confirm_stores_hash_and_version(...): ...
def test_project_requires_read_permission(...): ...
```
Run: `cd backend && python -m pytest application/tests/test_document_projection.py application/tests/test_document_adoption.py -q` — Expected: FAIL.

- [ ] **Step 4: Service implementieren**

Status-Logik (Konzept §7.2), jeweils mit `projected_sha256`/`projected_version` als Referenz: Repo-Hash gleich Projektionshash und Version unverändert → `in_sync`; Version höher → `loom_changed`; Repo-Hash ungleich `projected_sha256`, Loom unverändert → `file_changed`; beides → `conflict`. Datei fehlt → `missing_in_repo` (Dokument bleibt, Herkunft wird nicht gelöscht).

- [ ] **Step 5: Tests grün, Migration, Lint**

Run: `cd backend && python -m pytest application/tests/test_document_projection.py application/tests/test_document_adoption.py application/tests -k "document" -q && python manage.py makemigrations --check --dry-run`
Expected: PASS, bestehende Dokument-Tests unverändert, keine ungewollte Migration.

- [ ] **Step 6: Commit** (über `git`-Agent, ein PR): `feat(documents): add deterministic projection and adoption service`

---

### Task 3: REST und MCP

**Files:**
- Modify: `backend/rest_api/` (Dokument-ViewSet: Aktionen `projection`, `projection-status`, `adopt`, `confirm-projection`)
- Modify: `backend/mcp_server/tools/` (Dokument-Toolgruppe: `document.project`, `document.adopt`, `document.projection_status`), `backend/mcp_server/tool_registry.py` (Operationszuordnung)
- Modify: `docs/agent-templates/tool-manifest.json` (per Export), Zähler laut Drift-Gates
- Test: `backend/rest_api/tests/test_document_projection_api.py`, `backend/mcp_server/tests/test_document_projection_tools.py`

**Interfaces:**
- Consumes: `DocumentProjectionService` (Task 2).
- Produces:
  - REST: `GET /api/v1/documents/{id}/projection/` → `{path, content, sha256, version, state, warnings}`; `POST /api/v1/documents/projection-status/` mit `{workspace_id, files: {path: sha256}}` → Liste der Zeilen; `POST /api/v1/documents/{id}/confirm-projection/` mit `{sha256}`; `POST /api/v1/documents/{id}/adopt/` mit `{file_sha256, source_path, freeze}`.
  - MCP: `document.project` (`document_id`), `document.projection_status` (`workspace_id`, `files`, optional `confirm: {document_id, sha256}` zum Zurückmelden eines geschriebenen Hashes), `document.adopt` (`document_id`, `file_sha256`, `source_path`, `freeze`). Drei Tools, kein viertes: Der Bestätigungsschritt ist ein Parameter von `projection_status`, weil ein Hash kein Dokumentinhalt ist und deshalb nicht über `document.update` läuft.

- [ ] **Step 1: Failing Tests**

```python
def test_project_endpoint_returns_deterministic_content(client, doc): assert r1.json()["content"] == r2.json()["content"]
def test_status_endpoint_classifies_rows(client, ...): ...
def test_adopt_with_read_key_is_forbidden(read_client, doc): assert r.status_code == 403
def test_project_with_read_key_is_allowed(read_client, doc): assert r.status_code == 200
def test_adopt_with_wrong_hash_is_409_with_error_envelope(client, doc): ...
def test_mcp_tools_listed_and_in_manifest(): assert {"document.project","document.adopt","document.projection_status"} <= tool_names()
def test_mcp_adopt_is_governance_gated(...): ...
```
Run: `cd backend && python -m pytest rest_api/tests/test_document_projection_api.py mcp_server/tests/test_document_projection_tools.py -q` — Expected: FAIL.

- [ ] **Step 2: Implementieren**

Aktionen über den bestehenden Dokument-ViewSet, Parameterhelfer aus `rest_api/query_params.py`, Fehlerhülle wie bei `document.release`. MCP-Handler dünn über denselben Service. Operationszuordnung wie `document.read` (lesend) bzw. `document.transition` (Adoption).

- [ ] **Step 3: Manifest, Zähler, Gates**

Run: `cd backend && python manage.py export_tool_manifest && python -m pytest mcp_server/tests/test_tool_manifest_drift.py ../docs/agent-templates/test_meta_tool_count_drift.py ../docs/agent-templates/test_doc_surface_consistency.py -q`
Expected: PASS nachdem die in den Gates genannten Zählerstellen auf 293 stehen.

- [ ] **Step 4: Tests grün**

Run: `cd backend && python -m pytest rest_api/tests/test_document_projection_api.py mcp_server/tests/test_document_projection_tools.py -q` — Expected: PASS.

- [ ] **Step 5: Commit** (über `git`-Agent): `feat(documents): expose projection and adoption via REST and MCP`

---

### Task 4: CI-Weg — `project_documents.py` und Workflow-Vorlage

**Files:**
- Create: `scripts/clients/project_documents.py`
- Create: `docs/agent-templates/ci/project-documents.yml` (Vorlage für Repos, die ReqogniLoom nutzen)
- Create: `docs/clients/document-projection.md` und `docs/clients/document-projection.de.md`
- Test: `scripts/clients/test_project_documents.py`

**Interfaces:**
- Consumes: MCP-Tools aus Task 3 (JSON-RPC über `/mcp/`). Der Plan hat **keine Abhängigkeit von Phase C**: Das Skript enthält seinen kleinen eigenen JSON-RPC-Helfer (`initialize`, `tools/call`). Falls `scripts/clients/mcp_probe.py` schon existiert, darf der Helfer dessen Aufrufmuster übernehmen, importiert es aber nicht.
- Produces: CLI `python scripts/clients/project_documents.py --url <url> --key-env REQOGNILOOM_API_KEY --workspace <uuid> --repo . [--check] [--write]`. Exit 0: alles `in_sync`. Exit 1: Abweichung (`--check`) oder Konflikt. Exit 2: Fehler (Netz, Rechte). Bei `--write` werden nur Dateien mit Status `loom_changed` oder neue geschrieben, bei `file_changed`/`conflict` nichts, Exit 1. Das Skript verweigert jede Arbeit auf `main`/`master` (liest den Branch über `git rev-parse --abbrev-ref HEAD`).

- [ ] **Step 1: Failing Tests mit Stub-MCP-Server**

```python
def test_check_mode_reports_loom_changed_with_exit_1(stub, tmp_repo): ...
def test_write_mode_writes_only_loom_changed_files(stub, tmp_repo): ...
def test_file_changed_is_never_overwritten(stub, tmp_repo): assert (tmp_repo/"docs/x.md").read_text() == "handedit" and exit == 1
def test_refuses_on_main_branch(stub, tmp_repo_on_main): assert exit == 2 and "main" in stderr
def test_written_file_hash_matches_server_hash(stub, tmp_repo): ...
def test_confirm_is_sent_after_write(stub, tmp_repo): ...
```
Run: `cd scripts/clients && python -m pytest test_project_documents.py -q` — Expected: FAIL.

- [ ] **Step 2: Implementieren**

Stdlib-only. Ablauf: lokale Dateien unter den vom Server genannten Pfaden hashen (Pfad-Liste vorab per `document.projection_status` mit leerer Map erfragen), Status abfragen, je Zeile handeln, geschriebene Hashes per `confirm` melden. Schreiben mit `\n`-Zeilenenden, Verzeichnisse bei Bedarf anlegen, nie außerhalb von `--repo` (Pfad-Auflösung prüfen).

- [ ] **Step 3: Workflow-Vorlage und Doku**

Die Vorlage führt täglich und per `workflow_dispatch` `project_documents.py --check` aus und öffnet bei Abweichung über `gh pr create` einen PR mit `--write` auf einem Branch `docs/loom-projection-<datum>` (nie `main`). Secrets: `REQOGNILOOM_API_KEY` mit Read-Key (Projektion braucht nur Lesen), `GITHUB_TOKEN` mit `contents: write` und `pull-requests: write`. Beschreibung in beiden Sprachen: Betriebsarten (`loom`, `repo_external`), Adoption, Konfliktregeln, Grenze "Server schreibt nie ins Repo".

- [ ] **Step 3b: Statische Prüfung**

Run: `python3 -c "import yaml;yaml.safe_load(open('docs/agent-templates/ci/project-documents.yml'))"` und, falls vorhanden, `actionlint docs/agent-templates/ci/project-documents.yml`
Expected: kein Fehler.

- [ ] **Step 4: Tests grün**

Run: `cd scripts/clients && python -m pytest test_project_documents.py -q` — Expected: PASS.

- [ ] **Step 5: Commit** (über `git`-Agent): `feat(clients): add document projection CLI and CI template`

---

### Task 5: Harness-Plugins — Agent `document-steward` und Skill `document-projection`

**Files:**
- Create: `docs/agent-templates/document-steward.md` (Agent, Muster `risk-analyst.md`)
- Create: `docs/agent-templates/skills/document-projection/SKILL.md` (Prozess-Skill, Muster `risk-derivation/SKILL.md`)
- Modify: `docs/agent-templates/hooks/review-policy-gate.sh`: neuer Fall `document-steward)` mit `document.adopt|document.update) decision="ask"` (Adoption und Textänderungen bleiben freigabepflichtig, Projektion und Statusabgleich laufen ohne Rückfrage); `review-policy-gate.md` entsprechend ergänzen.
- Modify: `dist/plugins/claude-code/build_claude_plugin.py` (nur falls Agenten dort aufgezählt werden, sonst liest es `docs/agent-templates/*.md`; beim Umsetzen prüfen), `docs/agent-templates/test_role_tools_exist_in_manifest.py` (Rolle und erlaubte Tools), `docs/agent-templates/README.md`, `docs/agent-templates/BOOTSTRAP.md` (Rollenliste), `docs/agent-templates/hooks/review-policy-gate.sh` und seine Beschreibung `review-policy-gate.md` (Rollen werden dort aufgezählt)
- Generated (nicht von Hand): `dist/agent-skills/`, `dist/opencode/skills/`, `dist/codex/skills/`, `dist/npm/reqogniloom-opencode/skills/`, `dist/plugins/claude-code/reqogniloom/agents/document-steward.md`, Hermes-Skill nach den Regeln von `scripts/clients/render.py`
- Test: vorhandene `docs/agent-templates/test_*.py`, `dist/test_full_regeneration.py`, `dist/test_mcp_convention_parity.py`

**Interfaces:**
- Consumes: MCP-Tools aus Task 3.
- Produces:
  - Agent-Frontmatter: `name: document-steward`, `version: 1.0.0`, `description: Projects Loom documents to Markdown and adopts repo documents, delivering through branches and pull requests, via ReqogniLoom's MCP server.`, `compatible_with: "reqogniloom>=<Version nach Release>"`, `process_skill: document-projection`, `tools:` `document.read`, `document.query`, `document.versions`, `document.diff`, `document.project`, `document.projection_status`, `document.adopt`, `document.update`, `artifact.search`, `traceability.query`, `workspace.get_context`.
  - Skill-Ablauf (Inhalt der `SKILL.md`):
    1. `workspace.get_context` (Rigor-Stufe, aktive Workspace-ID).
    2. Lokal die Repo-Dateien unter den Dokumentpfaden hashen (`sha256sum`), `document.projection_status` aufrufen.
    3. Je Zeile: `loom_changed` → `document.project`, Datei schreiben, Hash über `confirm` zurückmelden. `file_changed` oder `conflict` → anhalten und dem Menschen berichten, nie überschreiben. `missing_in_repo` → berichten, nichts löschen. `untracked_in_loom` → Adoption vorschlagen.
    4. Zustellung: Branch `docs/loom-projection-<datum>`, Commit mit der Kopfzeilen-Version in der Nachricht, `gh pr create`. Niemals auf `main`/`master` schreiben oder pushen. Gelingt der PR nicht, mit klarer Meldung stoppen (Übergabe an den Menschen, nicht an einen anderen Agenten).
    5. Adoption: Datei hashen, `document.adopt` mit `file_sha256`, `source_path`, `freeze` nur auf ausdrückliche Anweisung. Danach ist die Datei Projektion und wird nicht mehr von Hand bearbeitet.
    6. Hinweis auf `scripts/clients/project_documents.py` als CI-Weg für dieselben Schritte.

- [ ] **Step 1: Registrierungsstellen finden**

Run: `grep -rn "risk-analyst" --include=*.py --include=*.md --include=*.sh --include=*.json docs/agent-templates dist/plugins scripts/clients | grep -v "^dist/plugins/claude-code/reqogniloom/agents"`
Expected: die Stellen, die Rollen aufzählen (u. a. `build_claude_plugin.py`, `test_role_tools_exist_in_manifest.py`, README, BOOTSTRAP). Jede bekommt einen Eintrag für `document-steward`.

- [ ] **Step 2: Failing Tests**

`test_role_tools_exist_in_manifest.py` um die Rolle `document-steward` ergänzen (Tools wie oben). `test_process_skills_reference_real_tools.py` prüft, dass die in `document-projection` genannten Tools im Manifest stehen.
Run: `python -m pytest docs/agent-templates -q`
Expected: FAIL (Rolle und Skill fehlen).

- [ ] **Step 3: Agent und Skill schreiben**

Format und Ton wie `risk-analyst.md` und `risk-derivation/SKILL.md`. Skill-`description` beginnt mit "Use when …". Verweis auf `DOMAIN_MODEL.md` für die Begriffe.

- [ ] **Step 4: Verteilung erzeugen**

```bash
python docs/agent-templates/package_skills.py
python dist/plugins/claude-code/build_claude_plugin.py
python scripts/clients/render.py
```
Die genauen Aufrufe sind gegen die Kopfkommentare der Skripte zu bestätigen. Nur erzeugte Dateien committen.

- [ ] **Step 5: Gates**

Run: `python scripts/clients/render.py --check && python -m pytest docs/agent-templates dist scripts/clients -q`
Expected: PASS, kein `STALE`.

- [ ] **Step 6: Commit** (über `git`-Agent, ein PR): `feat(plugins): add document-steward agent and document-projection skill`

---

### Task 6: #1374 schließen

**Files:** keine.

**Interfaces:** Consumes: Tasks 2 bis 5 gemergt.

- [ ] **Step 1: Konzept-Akzeptanz prüfen**

S1 bis S4 gegen den Rollout-Vorschlag des Issues: S1 Modell, S2 Vollzugriff, S3 Projektion als Pull Request plus Adoptionspfad (hier: Generator und Adoption im Server, Zustellung per CI-Skript und Agent), S4 Agenten-Zustandsspeicher. Vertagt bleiben T1 (Typ `Task`) und T2 (Text-Spans als Ankertyp), wie im Issue.

- [ ] **Step 2: Schließen (nach Freigabe)**

```bash
gh issue close 1374 --reason completed --comment "<Tabelle S1-S4 mit PR-Nummern und Tests. S3: Server rendert und prüft (document.project, document.projection_status, document.adopt), Zustellung per scripts/clients/project_documents.py (CI) oder Agent document-steward als PR, nie Push auf main. Vertagt: T1, T2.>"
```

- [ ] **Step 3: Endstand**

Run: `for n in 879 1374; do gh issue view $n --json state --jq .state; done`
Expected: zweimal `CLOSED`.

---

## Self-Review

- **Abdeckung:** #879 Task 1. #1374 S3 in Tasks 2 bis 5 (Generator, Statusabgleich, Adoption, REST/MCP, CI-Skript, Agent und Skill in den Harness-Plugins), Schließen Task 6. S1, S2, S4 sind belegt, nicht neu gebaut. Entscheidung 12b (Server rendert, CI und Agent liefern aus, Agentendefinition in den Plugin-Skills) ist durchgängig umgesetzt.
- **Bewusste Abweichung vom Konzept:** Der Server erzeugt keinen Branch und keinen PR (Konzept §7.3). Das übernehmen `project_documents.py` und der Agent. Dafür muss der Server keine Repo-Zugangsdaten halten.
- **Neue Tools:** drei MCP-Tools, Tool-Zahl 290 auf 293. Das ist anders als bei Phase D (Delta 0) und folgt daraus, dass `project`, `adopt` und der Statusabgleich eigene Aktionen sind. Die Zähler-Gates nennen alle Stellen.
- **Im Review geklärt:** (a) Aufrufe der Generatoren: `python docs/agent-templates/package_skills.py` und `python dist/plugins/claude-code/build_claude_plugin.py` (beide mit Standardwerten), (b) `review-policy-gate.sh` zählt Rollen auf, `document-steward` bekommt einen Fall mit `ask` für `document.adopt` und `document.update`. **Weiter im Step zu bestätigen:** (c) Ordnerkonvention je `kind` in `projection_path` ist ein Standardvorschlag, überschreibbar über `source_path`, (d) die Statusmatrix nutzt `projected_version` als Referenz und braucht in der Spec-Kurzfassung der PRs eine Bestätigung, (e) Wiederverwendung des Stub-Servers aus Phase C (`mcp_probe.py`) hängt davon ab, ob #1755 gemergt ist (ist es: `bfbf7ace`) und die Umsetzung von Phase C schon stattfand.
- **Nicht ausgeführt:** Kein Befehl dieses Plans lief. Pfade und Signaturen stammen aus der Lektüre von beta.29.
