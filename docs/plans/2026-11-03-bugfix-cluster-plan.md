---
type: Plan
title: "Bugfix-Cluster-Plan — 20 Issues, 10 Cluster, 14 neue Befunde"
scope: "backend/application, backend/rest_api, backend/mcp_server, backend/persistence, backend/icd, backend/diagram, backend/workflow, frontend/src, scripts/, .github/workflows"
status: in_progress
date: 2026-11-03
branch_base: "origin/main @ f64b31e3 (v1.8.0-beta.25)"
author_agent: orchestrator
language: de
revision: "Stufe 1 — verifizierter Repo-Scan + Nutzerentscheidungen vom 2026-11-03"
---

# Bugfix-Cluster-Plan

> **Reiner Umsetzungsplan.** Kein Code, keine Migration, keine Config-Änderung.
> Alle `datei:zeile`-Angaben sind gegen `origin/main @ f64b31e3` (v1.8.0-beta.25) geprüft.
> Angaben aus Issues sind als „laut Issue" markiert; eigene Prüfung als „**verifiziert**".
> Der Plan ersetzt die vorläufige 20-Issue-Liste aus der Sitzung vom 2026-11-03.

---

## 0. Ausgangslage

### 0.1 Basis

| Aspekt | Wert |
|---|---|
| `origin/main` | `f64b31e3` (Merge PR #1699, `VERSION` = `1.8.0-beta.25`) |
| Offene Issues | **48** (Stand 2026-11-03) |
| Davon als Bug/Defekt greifbar | **20** |
| Davon live verifiziert | **15** |
| Davon auf `main` bereits gefixt | **4** (schließen) |
| Kleines Feature (separat) | **1** (#1564) |
| Zusätzlich beim Repo-Scan gefunden | **14** (N1–N14) |

### 0.2 Wichtigster Befund

Der Issue-Tracker ist **stark veraltet**. Viele QA-Issues aus beta.20/21 sind auf `main`
bereits behoben. Die vier als „gefixt" markierten Issues in §9 werden mit Beleg geschlossen;
elf weitere Issues aus der Bonus-Liste ebenfalls.

### 0.3 Nutzerentscheidungen (fixiert am 2026-11-03)

| Thema | Entscheidung |
|---|---|
| Soft-Delete-Vertrag | **200 + `status="outdated"` überall**, Reaktivierung überall |
| ICD-DELETE | **Soft-Delete** statt Hard-Delete |
| Workspace-Waisen | **FK + CASCADE + Cleanup-Migration** |
| Unbekannte Query-Parameter | **400 `VALIDATION_ERROR`** |
| MCP-Fehler-Mapping | **Zentral in `BaseToolGroup`** |
| #1564 Typed TestCase Steps | **Separat** (`feat/1564-typed-test-steps`) |

---

## 1. Ausgewählte Issues

### 1.1 Live verifiziert (15)

| # | Prio | Cluster | Kurz | Beleg |
|---|---|---|---|---|
| #1660 | P0 critical | C1 | Architektur-Selbstparent korrumpiert Workspace-Baum | `validators.py:55-63,368-401`; `architecture_service.py:300-319`; `serializers.py:1631-1650` |
| #1661 | P0 high | C2 | Doppeltes ICD → 500 statt 409 | `icd_manager.py:441-455`; `traceability_connector.py:114-119`; `icd_views.py:969-984` |
| #1663 | P1 medium | C2 | MCP `glossary.create` Duplikat → „internal error" | `generic.py:503-526`; `glossary_service.py:174-175` |
| #1662 | P1 medium | C8 | Versions-Träger driften | `VERSION=1.8.0-beta.25`; `frontend/package.json=1.8.0-beta.22`; `bump_version.py:55-64` |
| #1668 | P1 high | C3 | Keine `allocated`/`level`-Filter, unbekannte Params still ignoriert | `views.py:1755-1786`; `requirement_service.py:1158-1218` |
| #1381 | P1 high | C4 | Soft-Delete: architecture 404, 7 andere Typen 200 | `architecture_service.py:436-446` vs. `requirement_service.py:1132-1156` |
| #1378 | P1 medium | C6 | Memory-Projektion bettet O(n) vor Sampling ein | `memory_admin_service.py:525-607` |
| #1401 | P2 medium | C6 | Erster POST 9 s (synchrones Embedding im Create) | `requirement_service.py:470-471,1255-1310` |
| #1403 | P2 medium | C5 | `as_domain_event_outbox.workspace_id` ohne FK | `application/models.py:165`; `attribute_definitions/models.py:75`; `link_types/models.py:62` |
| #1406 | P2 low | C9 | SplitView-Hitbox 12 px; `<th>` ohne `scope` | `SplitView.tsx:610-620`; `MemoryManagementSection.tsx:100-110` |
| #1412 | P2 low | C5 | `scope_artifact_id=''` statt `NULL`; Interview-Waisen | `baseline/models.py:232`; `persistence/models.py:3242-3249` |
| #1669 | P1 high | C3 | Level ignoriert Allokation, kein Konflikt-Hinweis | `requirement_level_service.py:52-78`; `traceability/audit/hierarchy.py:218` |
| #1314 | P2 medium | C7 | Memory-Qdrant ohne Payload-Index | `memory/qdrant_backend.py:442-463`; `artifact_vector_store.py:289-297` |
| #1411/#1399 | P2 medium | C7 | HNSW/Indizes `idx_scan=0`, ANN nutzt Index nicht | `pgvector_ann.py:47-65` |
| #1410 | P3 low | C10 | 105 Waisen-Artefakte ohne Bereinigungsweg | `traceability/audit/rules/*` (nur Regel, kein Cleanup) |

### 1.2 Bereits gefixt → schließen (4)

| Issue | Beleg |
|---|---|
| #1386 | `application/local_uid.py:169-218` — `pre_save`-Signal vergibt `uid` auf jedem Schreibpfad |
| #1400 | `persistence/migrations/0120_requirement_list_index.py` — `idx_req_ws_created` |
| #1402 | `persistence/migrations/0118_uid_workspace_unique_constraints.py` — 7 uid-Constraints |
| #801 | `RightSidebar` in Adr/Risk/Issue/TestCase/Needs/Glossary |

### 1.3 Bonus — ebenfalls bereits gefixt

`#598` (W1–W5), `#1404` (mermaid 12.2.0 / katex 0.18.10), `#1407`
(`parse_change_reason`), `#1408` (Manifest 282 Tools), `#1094` (`IdChip`),
`#1287` (`MarkdownField`), `#1316` (RRF in `search_service`), `#1334`
(`artifact_indexer`), `#879` (`Milestone`), `#587`
(`export_promptfoo_configs`), `#18` (pgvector).

### 1.4 By design / extern → kommentieren und schließen

`#1409` (Workspace-Scope enthält Mitglieder-User-Memories, dokumentiert in
`memory_admin_service.py:319-361`), `#1336` / `#1337` / `#1153` / `#1247`
(Honcho-Upstream/Deployment), `#1418` (Deployment-Frage), `#1230`
(externe Accounts), `#85` / `#186` (stale Epics).

---

## 2. Neue Befunde beim Repo-Scan (N1–N14)

| # | Befund | Beleg | Cluster |
|---|---|---|---|
| N1 | `_detect_cycle` hat kein visited-set → Endlosschleife bei bereits korruptem Baum; trifft auch Requirement-Re-Parent | `application/artifact_service.py:251-274` | C1 |
| N2 | MCP `*.update` (Adr/Risk/Issue/Glossary/CR) fängt `ValidationError` aus dem Service nicht → `INTERNAL_ERROR` | `mcp_server/tools/generic.py:559-618` | C2 |
| N3 | MCP `*.delete` / `*.outdate` / `*.query` maskieren `ValidationError`/`ValueError` ebenfalls | `generic.py:620-725` | C2 |
| N4 | `architecture.outdate` maskiert `ValidationError` als `INTERNAL_ERROR` | `mcp_server/tools/architecture.py:697-710` | C2 |
| N5 | ADR/Risk/Issue/Glossary-Listen ignorieren `?status=`/`?search=`, obwohl die Services `list_*_by_status` haben | `rest_api/views.py:8498, 8985, 11130, 13597` | C3 |
| N6 | MCP `requirement.query` und generisches `query` laden unbegrenzt (kein `limit`/`offset`) | `requirements.py:584-620`; `generic.py:687-721` | C3 |
| N7 | `bump_version.py` kennt `frontend/package.json` + `package-lock.json` strukturell nicht | `scripts/bump_version.py:55-64`; `scripts/check_plugin_packages.py:64` | C8 |
| N8 | Resize-Handles sind 4/12 px breit (SplitView 12 px, RightSidebar 4 px, Workflow-Inspector 4 px) | `SplitView.tsx:610`; `RightSidebar.module.css:105-115`; `WorkflowEditor.module.css:665-675` | C9 |
| N9 | ~10 Komponenten rendern `<th>` ohne `scope`, mehrere Tabellen ohne `<caption>` | `MemoryManagementSection`, `PermissionsSection`, `PromptVariableTable`, `MismatchReviewTable`, `MemoryVisualizationSection`, `BaselinesPanels`, `AttributeTable` | C9 |
| N10 | ICD-DELETE ist Hard-Delete; alle anderen Artefakte sind Soft-Delete; keine Reaktivierung | `icd/services.py:105-143`; `icd_views.py:1105-1122` | C4 |
| N11 | Workspace-Hard-Delete lässt ICD, Diagram und Outbox als Waisen zurück | `workspace_service.py:830-887`; `icd/models.py:110`; `diagram/models.py:132` | C5 |
| N12 | `parse_include_deleted` akzeptiert nur `true/1/yes`; alles andere wird still `false` | `rest_api/query_params.py:111-131` | C3 |
| N13 | ICD-/Diagram-Detail liefert nach DELETE weiter 200 (Architecture 404) | `icd/services.py:61-79`; `diagram/services.py:157-180` | C4 |
| N14 | `Icd.workspace_id` / `Diagram.workspace_id` sind bare UUIDs ohne FK | `icd/models.py:110`; `diagram/models.py:92` | C5 |

---

## 3. Cluster-Übersicht

| Cluster | Titel | Issues | Prio | Aufwand | Branch |
|---|---|---|---|---|---|
| C1 | Hierarchie & Zyklen | #1660, N1 | P0 | 1,5 d | `fix/c1-hierarchy-cycles` |
| C2 | Fehler-Mapping REST/MCP | #1661, #1663, N2–N4 | P0/P1 | 2,5 d | `fix/c2-error-mapping` |
| C3 | Request-Contract & Filter-Parität | #1668, #1669, N5, N6, N12 | P1 | 2,5 d | `fix/c3-request-contract` |
| C4 | Lifecycle & Soft-Delete | #1381, N10, N13 | P1 | 1,5 d | `fix/c4-soft-delete-contract` |
| C5 | Datenintegrität & Workspace-Waisen | #1403, #1412, N11, N14 | P2 | 2,0 d | `fix/c5-workspace-integrity` |
| C6 | Memory/Embedding-Write-Path | #1378, #1401 | P1 | 1,5 d | `perf/c6-embedding-write-path` |
| C7 | Search/Index-Performance | #1411/#1399, #1314 | P2 | 1,0 d | `perf/c7-vector-indexes` |
| C8 | Release/Version-Carrier | #1662, N7 | P1 | 0,5 d | `fix/c8-version-carriers` |
| C9 | Accessibility | #1406, N8, N9 | P2 | 1,5 d | `fix/c9-a11y-tables-targets` |
| C10 | Datenhygiene | #1410 | P3 | 0,5 d | `chore/c10-orphan-hygiene` |
| C11 | Typed TestCase Steps (separat) | #1564 | — | 1,5 d | `feat/1564-typed-test-steps` |

**Gesamt (C1–C10):** ~15,25 d inkl. Phase 0. **Mit C11:** ~16,75 d.

---

## 4. Cluster-Details

### C1 — Hierarchie & Zyklen

**Ziel:** Ein einziger fehlerhafter PATCH darf den Architekturbaum nicht unbrauchbar machen.

**Ursache (verifiziert):** `I1`/`I2` sind nur bei `standard`/`extended` aktiv
(`validators.py:55-63`). Bei `minimal` (und im Fallback) passiert `parent_id == element_id`
die Validierung; danach setzt `architecture_service.py:300-319` `Artifact.parent_id =
artifact.id` → die rekursive CTE (`annotate_levels`/`get_tree`) terminiert nicht.

**Änderungen:**

| Datei | Änderung |
|---|---|
| `application/validators.py:368` | Selbstbezug-Guard **vor** Tier-Gating: `parent_id == element_id → ValidationError` |
| `application/architecture_service.py:300` | gleicher Guard im Service (belt & braces) |
| `rest_api/serializers.py:1631` | Guard auch im Serializer (früher 400) |
| `application/artifact_service.py:251` | `_detect_cycle`: visited-set statt Liste; bricht bei vorbestehendem Zyklus ab (N1) |
| `application/management/commands/repair_architecture_cycles.py` | neu: erkennt Selbstbezüge/Zyklen, repariert auf `NULL`, schreibt Audit |

**Tests:**
- `test_architecture_self_parent_all_tiers` (minimal/standard/extended → 400)
- `test_detect_cycle_pre_existing_cycle_terminates`
- `test_repair_command_idempotent`

**DoD:** PATCH `{"parent_id": <eigene id>}` → 400 in allen Presets; Baum bleibt lesbar.

---

### C2 — Fehler-Mapping REST/MCP

**Ziel:** Kein bekannter Client-Input endet mehr in `INTERNAL_ERROR` / HTTP 500.

**Ursache (verifiziert):**
- ICD: `create_icd` ruft den Traceability-Connector direkt; der Manager wirft rohes
  `IntegrityError` (`uq_tracelink_edge`), `IcdViewSet` fängt nur `ValueError`.
- Glossary: `GlossaryService.create` wirft `application.base.ValidationError`;
  `GenericCrudToolGroup._handle_create` fängt nur `TypeError`.

**Änderungen:**

| Datei | Änderung |
|---|---|
| `mcp_server/tools/base.py:482` | zentrale `_map_exception()`: `ValidationError→VALIDATION_ERROR`, `NotFound→NOT_FOUND`, `PermissionDenied→PERMISSION_DENIED`, `OptimisticLock→CONFLICT`, `IntegrityError→CONFLICT` |
| `mcp_server/tools/generic.py:487-725` | per-Handler-`except` durch zentrales Mapping ersetzen (N2/N3) |
| `mcp_server/tools/architecture.py:697` | `outdate` auf zentrales Mapping (N4) |
| `icd/icd_manager.py:441` + `rest_api/icd_views.py:969` | `IntegrityError` → **409 `ICD_ALREADY_EXISTS`** (#1661) |
| `application/glossary_service.py` | Duplikat bleibt `ValidationError`; MCP liefert strukturiert (#1663) |

**Tests:** tabellengetrieben pro Tool-Gruppe (adr/risk/issue/glossary/change_request/
architecture/icd); REST-ICD-Duplikat → 409; Glossary-MCP → `VALIDATION_ERROR`/`CONFLICT`;
`test_internal_error_masking_697` bleibt grün.

**DoD:** Kein bekanntes Client-Input erreicht mehr `INTERNAL_ERROR`.

---

### C3 — Request-Contract & Filter-Parität

**Ziel:** Dokumentierte Filter wirken; unbekannte Parameter werden abgelehnt.

**Ursache (verifiziert):**
- Requirements kennen nur `status`, `search`, `include_deleted`, `page`, `page_size`.
- ADR/Risk/Issue/Glossary ignorieren `?status=`/`?search=`, obwohl die Services sie haben.
- MCP-Query lädt unbegrenzt.

**Änderungen:**

| Datei | Änderung |
|---|---|
| `rest_api/query_params.py` | `reject_unknown_query_params(request, allowed)` + striktes Bool-Parsing (N12) |
| `rest_api/views.py` `BaseEntityViewSet` | Guard zentral in `list()`/Detail-Actions |
| `rest_api/views.py:8498, 8985, 11130, 13597` | `status` + `search` an ADR/Risk/Issue/Glossary durchreichen (N5) |
| `rest_api/views.py:1755` + `requirement_service.py:1158` | `allocated` + `level` (#1668) |
| `requirement_level_service.py` / `traceability/audit/hierarchy.py` | `CONS-P14`-Warnung: Level ≠ Allokationstiefe (#1669) |
| `mcp_server/tools/requirements.py:584` | `allocated`, `level`, `status`, `search`, `limit`, `offset` (N6) |
| `mcp_server/tools/generic.py:687` | `limit`/`offset` (Default 50, Max 500) |

**Tests:** Endpoint×Parameter-Matrix; `?alocated=false` → 400; `?status=`/`?search=`
liefern gefilterte Ergebnisse; MCP-Pagination; `CONS-P14`-Warnung ohne Level-Änderung.

**DoD:** Kein dokumentierter Filter wird mehr still ignoriert; unbekannte Parameter → 400.

**Breaking Change:** In `CHANGELOG.md` + Release-Notes aufnehmen.

---

### C4 — Lifecycle & Soft-Delete

**Ziel:** Ein Vertrag für alle Artefakttypen: `DELETE → 204`, `GET → 200 + status="outdated"`,
`reactivate → 200 + active`.

**Ursache (verifiziert):** Architecture filtert `outdated` im Detail-Read und antwortet 404
(`architecture_service.py:436-446`); alle anderen Typen antworten 200. ICD löscht hart
(`icd/services.py:105-143`).

**Änderungen:**

| Datei | Änderung |
|---|---|
| `application/architecture_service.py:436` | `get_architecture_element` liefert bei `include_deleted=False` künftig 200 + `status="outdated"` |
| `icd/services.py:105` | `delete_icd` → `workflow.services.outdate()`; `reactivate` ergänzen |
| `rest_api/icd_views.py:1105` | DELETE 204 + Detail 200/outdated; neuer `reactivate`-Endpoint |
| `rest_api/views.py` Architecture | Detail-/Listen-Semantik angleichen |
| Doku | Vertrag in `docs/` + OpenAPI beschreiben |

**Tests:** 9-Typen-Matrix: `DELETE → GET(200, status=outdated) → reactivate → GET(200, active)`;
Architecture nicht mehr 404; ICD reaktivierbar.

**DoD:** Kein Typ weicht vom Vertrag ab.

**Hinweis:** Bestehende hart gelöschte ICDs lassen sich nicht wiederherstellen — nur künftige
Deletes sind reaktivierbar. Release-Note.

---

### C5 — Datenintegrität & Workspace-Waisen

**Ziel:** Ein Workspace-Hard-Delete hinterlässt keine Waisen.

**Ursache (verifiziert):** `delete_workspace` löscht Artefakte und einige abhängige Tabellen,
aber nicht `as_domain_event_outbox`, `icd_icd`, `diagram` (dort `artifact` = `SET_NULL`).
`ad_workspace_definition` / `lt_workspace_definition` sind bereits FK+CASCADE.

**Änderungen:**

| Datei | Änderung |
|---|---|
| `application/models.py:165` | `DomainEventOutbox.workspace_id` → FK `ON DELETE CASCADE` |
| `icd/models.py:110` | `Icd.workspace_id` → FK `ON DELETE CASCADE` |
| `diagram/models.py:92` | `Diagram.workspace_id` → FK `ON DELETE CASCADE` (Legacy-NULL vorher backfillen) |
| `application/workspace_service.py:830` | Kaskade um ICD/Diagram/Outbox erweitern (N11) |
| `baseline/models.py:232` | `scope_artifact_id`: `''→NULL` + CheckConstraint |
| Migration | Cleanup der Bestandswaisen vor dem FK-Add (mit Report) |

**Tests:** Workspace löschen → 0 Waisen in allen drei Tabellen; `makemigrations --check`;
Migration auf Fixture-DB.

**DoD:** FK-Constraints aktiv, Cleanup gelaufen, Kaskade getestet.

**Migration:** Vor dem FK-Add ein Dry-Run-Report; danach Cleanup; FK in derselben Migration.
`SET LOCAL row_security = off` für den Scan (Hausmuster aus `0117`).

---

### C6 — Memory/Embedding-Write-Path

**Ziel:** Kein Schreibpfad blockiert auf dem Embedding-Provider.

**Ursache (verifiziert):** `get_projection` bettet alle Einträge ein, **bevor** gesampelt wird
(`memory_admin_service.py:574-607`). `create_requirement` und `update_requirement` rufen
`_generate_and_store_embedding` synchron (`requirement_service.py:470,856`).

**Änderungen:**

| Datei | Änderung |
|---|---|
| `application/memory_admin_service.py:574-607` | deterministisch sampeln **vor** `generate_embedding`; Stored-Embedding bevorzugen |
| `application/requirement_service.py:470,856` | Embedding in Celery-Task/Event auslagern; `embedding_pending`-Flag |
| `llm_adapter/embedding_service.py` | harter Timeout < 25 s; `partial`/`degraded` durchreichen |

**Tests:** 200 Projektions-Einträge < 25 s; Create mit hängendem Provider < 1 s; Embedding
wird nachgezogen.

**DoD:** Kein Schreibpfad blockiert auf dem Provider.

---

### C7 — Search/Index-Performance

**Ziel:** Vektor-Suche nutzt die vorhandenen Indizes; Qdrant filtert indexiert.

**Ursache (verifiziert):** HNSW `idx_scan=0`; Memory-Qdrant legt keinen Payload-Index an.

**Änderungen:**

| Datei | Änderung |
|---|---|
| `memory/qdrant_backend.py:442` | `create_payload_index` für `scope`, `workspace_id`, `user_id`, `artifact_id` |
| `application/pgvector_ann.py` | `ef_search`/`iterative_scan` in allen ANN-Pfaden |
| Migration/Command | `ANALYZE` nach Embedding-Backfill; ungenutzte Indizes erst messen, dann droppen |

**Tests:** `EXPLAIN ANALYZE` + `idx_scan` vor/nach; Qdrant-Fake prüft Index-Aufrufe.

**DoD:** Messwerte dokumentiert; kein Regress bei < 5 k Zeilen.

---

### C8 — Release/Version-Carrier

**Ziel:** Ein Tag kann nicht mehr mit driftenden Versionsdateien ausgeliefert werden.

**Ursache (verifiziert):** `VERSION=1.8.0-beta.25`, `frontend/package.json=1.8.0-beta.22`.
`bump_version.py` listet `frontend/package.json` und `package-lock.json` nicht.

**Änderungen:**

| Datei | Änderung |
|---|---|
| `scripts/bump_version.py:55` | `frontend/package.json` + `frontend/package-lock.json` in die Carrier-Liste |
| `.github/workflows/ci.yml` | neuer Job `version-carriers`: alle Träger == `VERSION`, sonst Fail |
| `frontend/package.json` + Lock | auf `1.8.0-beta.25` nachziehen |

**Tests:** `python scripts/bump_version.py --dry-run`; CI-Job lokal simulieren.

**DoD:** Kein Träger kann mehr unbemerkt driften.

---

### C9 — Accessibility

**Ziel:** Tabellen-Semantik und Target-Größen erfüllen WCAG 2.2 AA.

**Ursache (verifiziert):** Resize-Handles sind 4 px (RightSidebar, Workflow-Inspector) bzw.
12 px (SplitView) breit; viele `<th>` ohne `scope`, mehrere Tabellen ohne `<caption>`.

**Änderungen:**

| Datei | Änderung |
|---|---|
| `SplitView.tsx:610` | 24×24-px-Hitbox, 2 px sichtbare Linie |
| `RightSidebar.module.css:105` | 4 px → 24 px Hitbox |
| `WorkflowEditor.module.css:665` | 4 px → 24 px Hitbox |
| `MemoryManagementSection`, `PermissionsSection`, `PromptVariableTable`, `MismatchReviewTable`, `MemoryVisualizationSection`, `BaselinesPanels`, `AttributeTable` | `<th scope="col">` + `<caption>` |
| `shared/DataTable` (neu) | gemeinsames Tabellen-Primitiv |

**Tests:** axe/Playwright-A11y-Spec; Target-Size-Assertion; Snapshot der Tabellen-Semantik.

**DoD:** Kein `<th>` ohne `scope`, keine Tabelle ohne `caption`, alle Resize-Handles ≥ 24 px.

---

### C10 — Datenhygiene

**Ziel:** Waisen-Artefakte sind dauerhaft sichtbar und bereinigbar.

**Änderungen:**

| Datei | Änderung |
|---|---|
| `application/management/commands/audit_orphan_artifacts.py` | neu: Report + optionales Löschen |
| `traceability/audit/rules/` | neue WARNING-Regel für Waisen |

**Tests:** Command auf Fixture-DB; Regel liefert WARNING, blockiert keine Baseline.

**DoD:** Waisen sind dauerhaft sichtbar und bereinigbar.

---

### C11 — Typed TestCase Steps (separat)

**Branch:** `feat/1564-typed-test-steps` · **~1,5 d**

- `given/when/then` als Datenmodell, Legacy-Read, Gherkin-Export, REST/MCP-Parität.
- **Nicht Teil** dieses Bug-Batches.

---

## 5. Teststrategie

| Ebene | Wann | Kommando |
|---|---|---|
| Cluster-Tests | nach jedem Cluster | gezielte `pytest`/`vitest`-Dateien |
| Backend-Gesamt | nach C5, C7 und am Ende | `make test-backend` |
| Frontend-Gesamt | nach C9 und am Ende | `make test-frontend` |
| Migrationen | nach C5 | `python manage.py makemigrations --check --dry-run` |
| E2E/A11y | nach C9 | `make test-e2e` (A11y-Spec) |

**Regel:** Jeder Cluster bekommt eigene, benannte Tests. Kein Sammel-Branch, keine zwei
Gesamttests als Ersatz für Cluster-Tests.

---

## 6. Reihenfolge & Meilensteine

| Phase | Inhalt | Aufwand |
|---|---|---|
| 0 | Housekeeping (Issues schließen) | 0,25 d |
| 1 | C1 + C2 | 4,0 d |
| 2 | C4 + C3 | 4,0 d |
| 3 | C5 + C6 + C7 | 4,5 d |
| 4 | C8 + C9 + C10 | 2,5 d |
| **Gesamt** | | **~15,25 d** |
| separat | C11 | 1,5 d |

**Begründung der Reihenfolge:** C1/C2 beheben die kritischen Korrektheitsfehler; C4/C3
vereinheitlichen die Verträge; C5–C7 adressieren Daten und Performance; C8–C10 schließen
Release, A11y und Hygiene ab.

---

## 7. Risiken & Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
|---|---|
| C4 ändert ICD-Löschverhalten (Breaking) | Release-Note + Migrationshinweis; bestehende Hard-Deletes bleiben hart |
| C5 löscht Bestandswaisen | Backup + Dry-Run-Report vor der Migration; Cleanup in eigener Migration |
| C3 ist Breaking für Clients mit Extra-Parametern | Release-Note; ggf. ein Release mit Warnheader vorziehen |
| C2 ändert MCP-Fehlercodes | bestehende Tests bewusst anpassen; Fehlercode-Matrix im PR |
| C6 verzögert Embedding-Frische | `embedding_pending` + Backfill-Command dokumentieren |
| C9 ändert Layout/Targets | visuelle Regression via E2E-Screenshots |
| C7-Indexänderungen | erst messen, dann droppen; Messwerte im PR |

---

## 8. Traceability: Issue → Cluster

| Issue | Cluster | Issue | Cluster |
|---|---|---|---|
| #1660 | C1 | #1403 | C5 |
| #1661 | C2 | #1406 | C9 |
| #1663 | C2 | #1412 | C5 |
| #1662 | C8 | #1669 | C3 |
| #1668 | C3 | #1314 | C7 |
| #1381 | C4 | #1411/#1399 | C7 |
| #1378 | C6 | #1410 | C10 |
| #1401 | C6 | #1564 | C11 (separat) |

---

## 8b. Umsetzungsstand

| Cluster | Status | Commit / Beleg |
|---|---|---|
| C1 — Hierarchie & Zyklen | **umgesetzt** | `b5dc889` — tier-unabhängiger Selbstbezug-Guard, visited-set, Repair-Command; 15 + 46 Tests grün |
| C2 — Fehler-Mapping | **umgesetzt** | `6ea8848` — zentrales Mapping, `INVALID_STATE` registriert, ICD 409; 186 + 135 + 12 Tests grün |
| C4 — Soft-Delete-Vertrag | **umgesetzt** | `7da945c` — Architecture-Detail 200/outdated, ICD Soft-Delete + reactivate; 204 Tests grün |
| C3 — Request-Contract | **umgesetzt** | `ed4f195` — strikte Query-Params (400), Filter-Parität ADR/Risk/Issue/Glossary, `allocated`/`level`, MCP `limit`/`offset`; #1669 bereits durch `CONS-P13` abgedeckt |
| C5 — Datenintegrität | offen | — |
| C6 — Embedding-Write-Path | offen | — |
| C7 — Search/Index | offen | — |
| C8 — Version-Carrier | offen | — |
| C9 — Accessibility | offen | — |
| C10 — Datenhygiene | offen | — |
| C11 — Typed Steps | separat | — |

**Branch:** `fix/bugfix-cluster-batch` (von `main @ f64b31e3`).

---

## 9. Nicht Teil dieses Plans

- #1564 (eigener `feat/`-Branch).
- #1670 (Requirements ↔ Architektur, großes Konzept).
- #1374 (Dokument-Artefakte, großes Feature).
- #1701 (Hermes-Plugin CRUD, eigenes Paket).
- #946 (Debug-Notes-Layer, 3–4 d).
- #1578 (Auto-Assessment v2, 4–6 d).
- #1339 / #1337 / #1336 (Memory/Honcho-Features bzw. Deployment).
- #1247 / #1153 (Honcho-Upstream).
- #1230 (externe Publikations-Accounts).
