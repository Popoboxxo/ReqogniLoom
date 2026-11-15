---
type: PLAN
title: "Bearbeitbare Dokumentansicht auf dem Document-Artefakt (+ Projektion) — Umsetzung R1–R7"
status: accepted
date: 2026-11-15
author_agent: planner
language: de
spec: "docs/superpowers/specs/2026-11-04-dokumentensicht-neu-design.md"
related_specs:
  - "docs/superpowers/specs/2026-11-02-f2-document-design.md"
  - "docs/superpowers/specs/2026-11-04-ordnung-allokation-design.md"
related_docs:
  - "docs/plans/2026-11-15-draft-spec-triage.md"
  - "docs/superpowers/plans/2026-11-15-navigation-trees.md"
supersedes_in_part: "docs/superpowers/specs/2026-11-04-dokumentensicht-neu-design.md §4.1 (Modell DocumentView) — ersetzt durch Richtung E1(b)"
branch_basis: "origin/main (Prüfstand dea467b4, 2026-11-15), Worktree .tmp/wt-phase-b1"
pipeline_stages:
  implement: 1
---

# Dokumentansicht auf `Document` — Umsetzungsplan

**Goal:** Die in der Triage empfohlene Richtung **E1(b)** umsetzen: die Dokumentensicht **nicht** als
neues Modell `DocumentView` bauen, sondern als **bearbeitbare Lesesicht auf dem vorhandenen
`Document`-Artefakt**, gespeist aus dem vorhandenen Projektions-Renderer. Kein neues Modell, keine
Migration, kein neues ADR — nur ein Leseobjekt, eine Route, ein Schreibweg (der bestehende) und eine
Oberfläche.

**Architecture:** Layer 2 bekommt **einen** neuen Lesedienst (`DocumentReadingService`), der
`Document` + Markdown-`body` + Inline-Anker + Trace-Kanten + Workflow-Zustand zu einem Leseobjekt
zusammenfasst. Schreiben passiert **ausschließlich** über die bestehenden Pfade
(`DocumentService.update_document` je Feld, `POST /api/v1/artifacts/bulk-update/` für den Sammelmodus).
Die Oberfläche konsumiert nur das Leseobjekt und die bestehenden Schreib-Endpunkte; sie entscheidet
nichts über Rechte oder Sperren, sie zeigt nur, was das Backend als erlaubt meldet.

**Tech Stack:** Django 6.1 + DRF + drf-spectacular, pytest 9, PostgreSQL 16 (RLS, unverändert),
React 19 + TypeScript 5.5 (strict) + Vite 8 + Vitest 5, Playwright (E2E), i18n DE/EN.

**Spec:** `docs/superpowers/specs/2026-11-04-dokumentensicht-neu-design.md` (bleibt `draft`; dieser
Plan ist die Umsetzung der Richtung E1(b) aus
`docs/plans/2026-11-15-draft-spec-triage.md` §4/§7 — **nicht** der Spec §4.1/§4.2 wörtlich).

**Auftrag:** Triage-E1 = (b). Die Spec bleibt als Ideenquelle stehen; ihre Kapitel- und
Attribut-Konfiguration (`config`-JSON, `subtree|filter|list`) ist **nicht** Teil dieses Plans, weil
sie ohne eigenes Modell keinen Ort hat.

**Nicht in diesem Plan:**

- Kein `DocumentView`-Modell, keine Tabelle, keine Migration, kein `document_view.*`-MCP-Präfix.
- Keine Kapitel-Konfiguration je Sicht (Spec V2/V3/E7 entfallen in dieser Richtung).
- Keine Filter-Sprache, keine Tabellenansicht (E6 der Spec bleibt unerledigt; dieser Plan braucht sie
  nicht mehr, weil es keine artefakt-übergreifenden Kapitelquellen gibt).
- Kein DOCX-Export, kein Teilen von Sichten (Spec O1), kein Repository-Schreiben (ADR-026 ENT-F5).

---

## 0. Globale Constraints

- **Layer-Disziplin (ADR-01):** Views und MCP rufen nur Layer-2-Services; kein ORM in
  `backend/rest_api/` oder `backend/mcp_server/` (`backend/rest_api/tests/test_architecture.py`).
- **Ein Schreibweg je Typ:** `DocumentService.update_document` bleibt der einzige Inhalts-Schreibpfad.
  Der Sammelmodus ruft **denselben** Dienst je Eintrag — keine zweite Implementierung einer Regel.
- **Sperre vor Version (ADR-026 F-3):** Reihenfolge Syntax → Freeze → Optimistic Lock ist bereits im
  Dienst implementiert und darf durch neue Aufrufer nicht umgangen werden.
- **`version` ist der ETag, nicht die Revision:** `Document.version` bleibt Optimistic-Lock-Zähler;
  die `WorkflowItemState`-Revision ist ein anderer Zähler und wird nirgends gemischt.
- **Freeze-Liste unverändert:** `FROZEN_FIELDS = ("title", "description", "body", "kind")`;
  `doc_date` und `custom_fields` bleiben laut F-2 auch im freigegebenen Zustand schreibbar.
- **Rechte sind einschränkend, nie erweiternd:** `EffectivePermissionService` +
  `ItemPermission` können eine Rolle nur beschneiden.
- **Kein neues MCP-Tool in R1/R2/R4–R7.** `document.read`, `document.projection`,
  `document.update` decken den Agenten-Bedarf bereits ab (Tool-Zahl bleibt **296**). Nur R3
  (Bulk-Update) fügt **ein** Tool hinzu (296 → 297) — dann greifen die vollen Zähler-Gates.
- **Jede neue REST-Route** zieht OpenAPI mit: `backend/rest_api/tests/test_openapi.py`,
  `test_openapi_list_params.py`, `test_schema_completeness_1388.py`.
- **Keine Migration.** Wenn ein Schnitt eine Migration braucht, ist der Schnitt falsch geschnitten.
- **UI:** i18n DE+EN im selben Commit (`frontend/src/i18n/locales.test.ts`), Design-Tokens aus
  `styles/tokens.css`, `data-testid` an jedem interaktiven Element, `ui-ratchet.test.ts` (keine
  Inline-Styles), Tastaturpfad für jede Aktion.
- **Git-Mutationen** (Branch, Commit, Push) laufen über den `git`-Agenten; Branch `feat/document-reading-view`.

## 1. Schnitt-Übersicht

| # | Schnitt | Agent | Depends on | Mergebar allein? |
|---|---|---|---|---|
| R1 | Leseobjekt + Lese-Route (`GET /documents/{id}/view/`) | senior-developer | — | **ja** (rein additiv) |
| R2 | `editable_fields` + Einzel-Speichern mit Freeze-/Rechte-Gates | senior-developer | R1 | **ja** |
| R3 | Bulk-Update `PATCH /artifacts/bulk-update/` + MCP `artifact.bulk_update` (D5-Voraussetzung) | senior-developer | — (R2 nutzt es nur) | **ja** (Tool-Zähler-Gate!) |
| R4 | UI Lesemodus auf `/documents/:id` | frontend-component-engineer | R1 | **ja** |
| R5 | UI Einzel-Speichern (Sofort-Modus) | frontend-component-engineer | R2, R4 | **ja** |
| R6 | UI Sammelmodus (alles oder nichts) | frontend-component-engineer | R3, R5 | **ja** |
| R7 | Export/Druck, Feature-Doku, ADR-026-Nachtrag, Spec-Status | technical-writer + senior-developer | R4–R6 | **ja** |

**Reihenfolge:** R1 → R2 → R3 → R4 → R5 → R6 → R7. R3 ist bewusst **vor** R4/R5 geschnitten, weil
R5 sonst gegen einen Endpunkt baut, den es noch nicht gibt; R3 ist aber auch ohne die Sicht sinnvoll
(Tabellenansicht-Vorarbeit, s. Triage §4).

**Estimated effort:** Summe der Schnitte ≈ **4,25 Tage** (R1 0,75 · R2 0,5 · R3 0,75 · R4 0,75 ·
R5 0,5 · R6 0,5 · R7 0,5). Die Zahl ist eine Planungsannahme aus dem Umfang der Spec D1–D6; eine
formale Schätzung durch `effort-estimator` steht aus und kann die Reihenfolge nicht ändern, nur die
Terminierung.

## 2. File Structure

| Bereich | Dateien |
|---|---|
| Lesen (neu) | `backend/application/document_reading_service.py`, `backend/application/document_reading_chapters.py` (pure Markdown-Kapitelung) |
| Lesen (geändert) | `backend/rest_api/views.py` (`DocumentViewSet.view`), `backend/rest_api/serializers.py` (`DocumentReadingSerializer`), `backend/rest_api/urls.py` (nur falls nicht als `@action`) |
| Berechtigung (neu) | `backend/application/document_edit_policy.py` (pure Erlaubnis-Auflösung je Feld) |
| Sammel-Schreiben (neu) | `backend/application/bulk_update_service.py` |
| Sammel-Schreiben (geändert) | `backend/rest_api/views.py` (`ArtifactBulkUpdateView`), `backend/rest_api/urls.py`, `backend/mcp_server/tools/cross_cutting.py`, `docs/agent-templates/tool-manifest.json` |
| Frontend Lesen | `frontend/src/components/Documents/DocumentReadingView.tsx` (neu), `DocumentReadingChapters.tsx` (neu), `frontend/src/queries/documents.ts`, `frontend/src/api/documents.ts`, `frontend/src/components/Documents/Documents.module.css` |
| Frontend Schreiben | `frontend/src/components/Documents/DocumentFieldEditor.tsx` (neu), `DocumentSaveBar.tsx` (neu), `useDocumentDrafts.ts` (neu), `frontend/src/api/documents.ts` |
| i18n | `frontend/src/i18n/locales/de.json`, `en.json` |
| E2E | `e2e/tests/document-reading-view.spec.ts` (neu), `e2e/tests/documents.spec.ts` (Anpassung) |
| Doku | `docs/features/document-reading-view.md` (neu), `docs/se/ADR/ADR-026_document_artefakt.md` (Nachtrag), `docs/superpowers/specs/2026-11-04-dokumentensicht-neu-design.md` (Statuszeile) |

---

# R1 — Leseobjekt und Lese-Route

### Task R1.1: Markdown-Kapitelung (pure)

**Files:**
- Create: `backend/application/document_reading_chapters.py`
- Test: `backend/application/tests/test_document_reading_chapters.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class Chapter:
      id: str            # "h-1", "h-2" … stabil über denselben Body
      level: int         # 1..MAX_CHAPTER_LEVEL (3)
      title: str
      body: str          # Markdown dieses Kapitels ohne die Überschrift selbst
      children: tuple["Chapter", ...]

  MAX_CHAPTER_LEVEL: int = 3
  def split_chapters(markdown: str, *, max_level: int = MAX_CHAPTER_LEVEL) -> tuple[Chapter, ...]
  def number_chapters(chapters: Sequence[Chapter]) -> tuple[NumberedChapter, ...]  # "1", "1.1", "1.1.1"
  ```
- Verhält sich bei: leerem Body (→ eine implizite Wurzel ohne Titel, `level=0`), Body ohne
  Überschriften (→ ein Kapitel mit `title=""`), Überschriften **in** Fenced-Code-Blöcken (→ kein
  Kapitel), Sprung von `##` auf `####` (→ `####` wird als Text behandelt, nicht als Kapitel).

- [ ] **Step 1:** Tests schreiben (fail): `test_empty_body_yields_single_root`,
  `test_no_headings_yields_one_chapter`, `test_heading_inside_fence_is_not_a_chapter`,
  `test_level_jump_is_flattened`, `test_numbering_is_nested`, `test_ids_are_stable_and_unique`.
- [ ] **Step 2:** Implementieren; nur `re` und `dataclasses`, kein Django-Import (Modul bleibt
  ohne DB lauffähig und wird auch von der Projektion genutzt).
- [ ] **Step 3:** `pytest backend/application/tests/test_document_reading_chapters.py` grün.
- [ ] **Step 4:** Commit `feat: add markdown chapter splitter for document reading view`.

### Task R1.2: `DocumentReadingService`

**Files:**
- Create: `backend/application/document_reading_service.py`
- Test: `backend/application/tests/test_document_reading_service.py`

**Interfaces:**
- Consumes: `DocumentService.get_document`, `state_reader.current_states`,
  `application.document_projection_render.render_document` (nur für Referenz-Auflösung,
  **nicht** für die Kapitel), `InlineAnchor`, `TraceLink`, `GlossaryTerm` (read-only, wie
  `DocumentProjectionService.project`).
- Produces:
  ```python
  @dataclass(frozen=True)
  class DocumentReading:
      document: Mapping[str, Any]     # Kopf des Leseobjekts
      capabilities: Mapping[str, Any] # {"can_write": bool, "can_transition": bool, "read_only_reason": str|None}
      chapters: tuple[Mapping[str, Any], ...]
      fields: tuple[Mapping[str, Any], ...]   # Feldebene, R2 füllt `editable`
      references: Mapping[str, Any]           # {"anchors": [...], "edges": [...], "glossary": {...}}
      meta: Mapping[str, Any]                 # {"chapter_total", "rendered", "truncated", "page_size", "offset"}
      def to_dict(self) -> dict[str, Any]

  class DocumentReadingService(ServiceBase):
      def read(self, document_id: UUID, ctx: AuthContext, *, page_size: int = 200, offset: int = 0) -> DocumentReading
  ```
- Wire-Vertrag (`to_dict`):
  ```json
  {"document": {"id","uid","title","kind","status","version","doc_date","modified_at",
                "frozen_at","frozen_fields","owner_mode","projection_mode","source_path"},
   "capabilities": {"can_write": true, "can_transition": true, "read_only_reason": null},
   "chapters": [{"id":"h-1","level":1,"number":"1","title":"…","body":"…"}],
   "fields": [{"name":"title","value":"…","editable":true,"locked":null}],
   "references": {"anchors":[],"edges":[],"glossary":{}},
   "meta": {"chapter_total":7,"rendered":7,"truncated":false,"page_size":200,"offset":0}}
  ```

- [ ] **Step 1:** Tests schreiben (fail):
  `test_read_returns_head_and_chapters`, `test_unknown_document_is_not_found`,
  `test_foreign_tenant_document_is_not_found`, `test_viewer_gets_can_write_false`,
  `test_frozen_document_reports_frozen_fields`, `test_query_count_is_constant`
  (`assertNumQueries(≤ 8)` für einen Body mit 40 Überschriften und 20 Ankern),
  `test_references_resolved_without_n_plus_one`, `test_page_size_is_validated` (1..500).
- [ ] **Step 2:** Service implementieren. Der Zustand kommt aus **einem** `current_states`-Aufruf;
  Anker und Kanten in je **einer** Query; Kapitel rein aus `split_chapters(document.body)`.
- [ ] **Step 3:** `pytest backend/application/tests/test_document_reading_service.py` grün.
- [ ] **Step 4:** Commit `feat: add document reading service`.

### Task R1.3: REST-Route

**Files:**
- Modify: `backend/rest_api/views.py` (`DocumentViewSet`), `backend/rest_api/serializers.py`
- Test: `backend/rest_api/tests/test_document_view_api.py`

**Interfaces:**
- Produces: `GET /api/v1/documents/{id}/view/?page_size=200&offset=0` → 200 mit dem Vertrag aus
  R1.2; `ETag: "<version>"` (dieselbe Konvention wie `retrieve`); 400 bei ungültigem `page_size`;
  404 bei unbekannter/fremder Id; **kein** Schreibverb.
- Consumes: `DocumentReadingService.read`.

- [ ] **Step 1:** Tests schreiben (fail): `test_view_returns_reading_object`,
  `test_view_emits_etag`, `test_invalid_page_size_is_400`, `test_unknown_id_is_404`,
  `test_openapi_documents_view_route_exists` (Schema-Pfad vorhanden, `page_size`/`offset` deklariert).
- [ ] **Step 2:** `@action(detail=True, methods=["get"], url_path="view")` + `@extend_schema`
  (Response `DocumentReadingSerializer`, Query-Parameter deklariert). Kein `urls.py`-Eintrag nötig.
- [ ] **Step 3:** `pytest backend/rest_api/tests/test_document_view_api.py backend/rest_api/tests/test_openapi.py backend/rest_api/tests/test_schema_completeness_1388.py` grün.
- [ ] **Step 4:** Commit `feat: expose document reading view endpoint`.

**Akzeptanz R1:** Ein Aufruf liefert Kopf, Kapitel (nummeriert), Felder (noch ohne
Bearbeitungs-Flag) und Referenzen; die Abfragezahl ist unabhängig von der Kapitelzahl konstant; die
Route steht im OpenAPI-Schema. **Gates:** OpenAPI-Tests, keine Migration, keine Änderung an
`test_tool_manifest_drift.py` (kein neues Tool). **Mergebar allein: ja.**

---

# R2 — Bearbeitbarkeit: Auflösung und Durchsetzung

### Task R2.1: Erlaubnis-Auflösung je Feld (pure)

**Files:**
- Create: `backend/application/document_edit_policy.py`
- Test: `backend/application/tests/test_document_edit_policy.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class FieldPermission:
      editable: bool
      locked: Mapping[str, Any] | None   # {"code": "FIELD_FROZEN"|"PERMISSION"|"REPO_EXTERNAL", "detail": str}

  EDITABLE_FIELDS_V1: tuple[str, ...] = ("title", "description", "body", "doc_date", "custom_fields")

  def resolve_field_permissions(
      document: Document,
      *,
      can_write: bool,
      owner_mode: str,
      frozen_fields: Sequence[str],
      allowed_custom_fields: Sequence[str] | None,
  ) -> dict[str, FieldPermission]
  ```
- Reine Funktion (kein ORM-Zugriff, kein `ctx`) — damit die Oberfläche und der Schreibpfad dieselbe
  Wahrheit teilen und die Regel ohne DB testbar ist.
- Regeln in dieser Reihenfolge: `can_write=False` → `PERMISSION`; `owner_mode=="repo_external"` →
  `REPO_EXTERNAL` (alle Felder); Feld in `frozen_fields` → `FIELD_FROZEN`; sonst editierbar.

- [ ] **Step 1:** Tests schreiben (fail): `test_reader_has_no_editable_fields`,
  `test_repo_external_is_read_only`, `test_frozen_fields_are_locked`,
  `test_doc_date_stays_editable_when_frozen`, `test_custom_fields_follow_attribute_catalog`,
  `test_kind_is_not_in_the_editable_set`, `test_locked_code_order_permission_before_freeze`.
- [ ] **Step 2:** Implementieren.
- [ ] **Step 3:** `pytest backend/application/tests/test_document_edit_policy.py` grün.
- [ ] **Step 4:** Commit `feat: add document field edit policy`.

### Task R2.2: `fields` im Leseobjekt füllen

**Files:**
- Modify: `backend/application/document_reading_service.py`
- Test: `backend/application/tests/test_document_reading_service.py`

**Interfaces:**
- Produces: `fields[].editable` / `fields[].locked` gemäß R2.1; `capabilities.read_only_reason`
  trägt denselben Grund (`"PERMISSION"`/`"REPO_EXTERNAL"`/`null`), damit die Oberfläche eine
  Erklärung hat, ohne sie zu erfinden.
- Consumes: `EffectivePermissionService.resolve_effective_permission` (Rollen-Cache),
  `resolve_field_permissions`.

- [ ] **Step 1:** Tests erweitern (fail): `test_fields_editable_for_editor_in_draft`,
  `test_fields_locked_for_frozen_document`, `test_fields_locked_for_repo_external_document`,
  `test_fields_match_actual_patch_outcome` (Tabellentest: je Feld × {Entwurf, freigegeben} ×
  {Viewer, Editor} prüfen, ob `editable` mit dem echten PATCH-Ergebnis übereinstimmt — die
  wichtigste Zusicherung dieses Schnitts).
- [ ] **Step 2:** Implementieren; keine neue Query (die Rollenauflösung ist gecacht).
- [ ] **Step 3:** `pytest backend/application/tests/test_document_reading_service.py backend/rest_api/tests/test_document_view_api.py` grün.
- [ ] **Step 4:** Commit `feat: report editable document fields`.

**Akzeptanz R2:** `editable` ist keine Behauptung, sondern deckungsgleich mit dem, was
`PATCH /documents/{id}/` tatsächlich erlaubt (Tabellentest). **Gates:** kein neuer Schreibweg
(Architekturtests grün), OpenAPI unverändert. **Mergebar allein: ja.**

---

# R3 — Bulk-Update (Voraussetzung aus D5, geteilt mit der Tabellenansicht)

### Task R3.1: `BulkUpdateService`

**Files:**
- Create: `backend/application/bulk_update_service.py`
- Test: `backend/application/tests/test_bulk_update_service.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class BulkEntry:
      artifact_id: UUID
      expected_version: int
      fields: Mapping[str, Any]

  @dataclass(frozen=True)
  class BulkUpdateResult:
      updated: tuple[Mapping[str, Any], ...]   # [{"artifact_id","version"}]
      errors: tuple[Mapping[str, Any], ...]    # [{"index","artifact_id","code","message","field"?}]

  MAX_ENTRIES: int = 100
  UPDATE_DISPATCH: Mapping[str, Callable[..., Any]]  # item_type -> update(**fields) des Typs

  class BulkUpdateService(ServiceBase):
      @atomic_transaction
      def apply(self, workspace_id: UUID, entries: Sequence[BulkEntry], ctx: AuthContext) -> BulkUpdateResult
  ```
- `UPDATE_DISPATCH` in v1: `"Document" → DocumentService.update_document`,
  `"Requirement" → RequirementService.update_requirement`. Ein weiterer Typ kommt nur mit seinem
  Dienst hinzu — **kein** generischer Fallback auf `ArtifactService.update_artifact` (der kann keine
  Inhaltsfelder).
- Alles oder nichts: der erste Fehler bricht ab und macht die Transaktion rückgängig; `errors`
  enthält **alle** geprüften Fehler, mindestens den abbrechenden.

- [ ] **Step 1:** Tests schreiben (fail): `test_happy_path_updates_all_and_bumps_versions`,
  `test_101_entries_is_rejected_with_400`, `test_empty_entries_is_rejected`,
  `test_one_invalid_entry_writes_nothing` (DB-Assertion nach dem Fehler),
  `test_frozen_field_rolls_back_the_whole_batch`,
  `test_expected_version_mismatch_rolls_back_the_whole_batch`,
  `test_entry_from_foreign_workspace_is_rejected`, `test_error_lists_index_and_code`,
  `test_unknown_artifact_type_is_rejected`.
- [ ] **Step 2:** Implementieren. Jeder Eintrag ruft den Typ-Dienst mit `expected_version` auf; die
  Rückgabewerte werden gesammelt, nicht vorab validiert (die Dienste sind die Wahrheit).
- [ ] **Step 3:** `pytest backend/application/tests/test_bulk_update_service.py` grün.
- [ ] **Step 4:** Commit `feat: add transactional bulk update service`.

### Task R3.2: REST-Route und MCP-Tool

**Files:**
- Modify: `backend/rest_api/views.py` (`ArtifactBulkUpdateView`), `backend/rest_api/urls.py`
  (**vor** den Router-URLs registrieren, gleiche Vorsichtsmaßnahme wie bei
  `artifacts/<uuid>/comments/`), `backend/mcp_server/tools/cross_cutting.py`,
  `docs/agent-templates/tool-manifest.json`
- Test: `backend/rest_api/tests/test_bulk_update_api.py`,
  `backend/mcp_server/tests/test_artifact_bulk_update_tool.py`

**Interfaces:**
- Produces: `PATCH /api/v1/artifacts/bulk-update/`
  Body `{"workspace_id": "...", "entries": [{"artifact_id","expected_version","fields"}]}`;
  200 `{"updated": [...], "errors": []}`; 400 bei Schema-/Mengenfehler (101 Einträge);
  409 bei Regel-/Versionsverstoß (nichts geschrieben, `errors` gefüllt); 403 bei fehlendem
  Schreibrecht.
- MCP: `artifact.bulk_update` (Gruppe `artifact`, **Tool 297**), Schema = derselbe Body,
  Rückgabe = `to_dict()` des Ergebnisses, Fehlercodes identisch zu REST.

- [ ] **Step 1:** Tests schreiben (fail): `test_bulk_update_endpoint_roundtrip`,
  `test_101_entries_is_400`, `test_conflict_is_409_and_writes_nothing`,
  `test_openapi_documents_bulk_update_route` (Schema vorhanden),
  `test_manifest_contains_bulk_update` + `test_tool_count_is_297`.
- [ ] **Step 2:** View (APIView, kein ViewSet — der Pfad darf nicht mit
  `artifacts/<pk>/` kollidieren; Registrierung vor `router.urls`).
- [ ] **Step 3:** MCP-Tool + Manifest aktualisieren
  (`python backend/manage.py export_tool_manifest`), `tool_count` prüfen.
- [ ] **Step 4:** `pytest backend/rest_api/tests/test_bulk_update_api.py backend/mcp_server/tests/test_tool_manifest_drift.py backend/mcp_server/tests/test_artifact_bulk_update_tool.py backend/rest_api/tests/test_openapi.py` grün.
- [ ] **Step 5:** Commit `feat: add artifact bulk update endpoint and tool`.

**Akzeptanz R3:** Ein ungültiger Eintrag schreibt **nichts** (DB-Assertion), die Antwort nennt
Index, Code und Grund; 101 Einträge → 400; das Tool-Zähler-Gate ist konsistent (Manifest,
`tool_registry`, Drift-Test, OpenAPI, Doku-Zahlen). **Gates:** Tool-Zahl 296 → 297 in
`docs/agent-templates/tool-manifest.json`, `backend/mcp_server/tool_registry.py`,
`test_tool_manifest_drift.py`, OpenAPI-Tests, ggf. `README.md`/`clients/registry.yaml` über
`agent-meta-manager`. **Mergebar allein: ja** (der Endpunkt hat ohne Sicht keinen Konsumenten, ist
aber für die Tabellenansicht bereits nutzbar).

---

# R4 — UI-Lesemodus

### Task R4.1: Query-Hook und API-Wrapper

**Files:**
- Modify: `frontend/src/api/documents.ts` (`documentsApi.readingView(id, params)`),
  `frontend/src/queries/documents.ts` (`documentReadingQuery`),
  `frontend/src/types/documents.ts` (Typen `DocumentReading`, `ReadingChapter`, `ReadingField`)
- Test: `frontend/src/test/documents-reading-hook.test.tsx`

**Interfaces:**
- Produces: `useDocumentReading(documentId)` → `{ data, isLoading, error }`;
  Query-Key `["documents","reading", workspaceId, documentId]`; `staleTime: 0` (die Sicht zeigt
  den aktuellen Stand, nie einen Cache-Schnappschuss).

- [ ] **Step 1:** Tests (fail): `test_hook_fetches_reading_object`,
  `test_hook_is_disabled_without_document_id`, `test_hook_surfaces_404_as_error`.
- [ ] **Step 2:** Implementieren (Muster: bestehende `queries/documents.ts`-Hooks).
- [ ] **Step 3:** `npm test -- documents-reading-hook` grün.
- [ ] **Step 4:** Commit `feat(ui): add document reading query hook`.

### Task R4.2: Lesekomponente

**Files:**
- Create: `frontend/src/components/Documents/DocumentReadingView.tsx`,
  `DocumentReadingChapters.tsx`
- Modify: `frontend/src/components/Documents/Documents.tsx`,
  `frontend/src/components/Documents/Documents.module.css`,
  `frontend/src/i18n/locales/de.json`, `en.json`
- Test: `frontend/src/test/DocumentReadingView.test.tsx`

**Interfaces:**
- Produces: `<DocumentReadingView document={…} reading={…} onEdit={…} />` mit
  `data-testid="document-reading-view"`, `document-reading-toc`,
  `document-reading-chapter-<id>`, `document-reading-field-<name>`,
  `document-reading-capability-notice`.
- Consumes: `useDocumentReading`, `MarkdownPreview` (bestehender Renderer) für den Kapiteltext.
- Layout: Inhaltsverzeichnis links (`<nav aria-label>`), Kapitel rechts; Kapitel als
  `<section aria-labelledby>`; Überschriften `h2`/`h3` (die Seite hat schon eine `h1`).

- [ ] **Step 1:** Tests (fail): `renders_chapters_in_order_with_numbers`,
  `renders_toc_entries_matching_chapters`, `viewer_sees_no_edit_affordance`,
  `frozen_document_shows_lock_notice`, `repo_external_document_shows_read_only_notice`,
  `empty_body_renders_single_section`, `markdown_links_render_as_text_not_html`
  (kein `dangerouslySetInnerHTML`).
- [ ] **Step 2:** Implementieren; bestehende `Documents.tsx`-Zustände (Liste, Formular) bleiben
  unverändert, der Lesemodus ersetzt nur das bisherige Read-only-Detail (`DocumentDetail`).
- [ ] **Step 3:** `npm test -- DocumentReadingView` + `npm run lint` (`ui-ratchet`) grün.
- [ ] **Step 4:** Commit `feat(ui): render document reading view`.

**Akzeptanz R4:** `/documents/:id` zeigt nummerierte Kapitel mit Inhaltsverzeichnis; ein Viewer
sieht **keine** Bearbeitungsfläche; ein freigegebenes Dokument zeigt die Sperre als Hinweis, nicht
als Fehler; bestehende `DocumentsView`-Tests bleiben grün. **Gates:** i18n-Parität,
`ui-ratchet.test.ts`, E2E `documents.spec.ts` angepasst. **Mergebar allein: ja.**

---

# R5 — UI Einzel-Speichern (Sofort-Modus)

### Task R5.1: Feld-Editor und Sofort-Speichern

**Files:**
- Create: `frontend/src/components/Documents/DocumentFieldEditor.tsx`,
  `frontend/src/components/Documents/useDocumentDrafts.ts`
- Modify: `frontend/src/components/Documents/DocumentReadingView.tsx`,
  `frontend/src/api/documents.ts` (PATCH mit `If-Match`-Header),
  `frontend/src/i18n/locales/{de,en}.json`
- Test: `frontend/src/test/DocumentFieldEditor.test.tsx`

**Interfaces:**
- Produces:
  ```ts
  interface DocumentDraft { field: string; value: unknown; status: "clean"|"dirty"|"saving"|"conflict"|"error"; error?: string }
  useDocumentDrafts(reading: DocumentReading): {
    drafts, setDraft, resetField, isDirty, saveField(name): Promise<void>, conflicts: string[],
  }
  ```
- `saveField` sendet `PATCH /documents/{id}/` mit **einem** Feld und `If-Match: "<version>"`.
- `locked.code === "FIELD_FROZEN"` → Feld `disabled`, Schloss + Grund als `title`/`aria-describedby`;
  `REPO_EXTERNAL`/`PERMISSION` → Feld `readOnly` + Hinweis am Kopf.

- [ ] **Step 1:** Tests (fail): `edit_enabled_only_for_editable_fields`,
  `patch_sends_if_match_header`, `conflict_marks_field_orange_and_offers_reload`,
  `frozen_field_is_disabled_with_reason`, `successful_save_updates_version`,
  `validation_error_is_shown_at_the_field` (400 mit `details[].field`).
- [ ] **Step 2:** Implementieren.
- [ ] **Step 3:** `npm test -- DocumentFieldEditor` grün.
- [ ] **Step 4:** Commit `feat(ui): add inline document field editing`.

**Akzeptanz R5:** Jede Änderung geht als ein `PATCH` mit `If-Match` über den bestehenden Endpunkt;
ein 412 markiert **genau das** Feld und bietet „neu laden"; ein 409 `FIELD_FROZEN` ist vorab
unmöglich, weil das Feld deaktiviert ist (und wird trotzdem korrekt angezeigt, falls der Zustand
sich zwischen Laden und Speichern geändert hat). **Gates:** keine neue Route, i18n-Parität.
**Mergebar allein: ja.**

---

# R6 — UI Sammelmodus

### Task R6.1: Entwürfe halten und als Stapel speichern

**Files:**
- Create: `frontend/src/components/Documents/DocumentSaveBar.tsx`
- Modify: `frontend/src/components/Documents/useDocumentDrafts.ts`,
  `frontend/src/api/artifacts.ts` (oder `documents.ts`, je nach Hausgebrauch: `bulkUpdate(entries)`),
  `frontend/src/i18n/locales/{de,en}.json`
- Test: `frontend/src/test/DocumentSaveBar.test.tsx`

**Interfaces:**
- Produces: `<DocumentSaveBar dirtyCount onSaveAll onDiscard conflicts />` mit
  `data-testid="document-save-bar"`, `document-save-all`, `document-discard`;
  `saveAll()` baut `entries: [{artifact_id, expected_version, fields}]` und ruft **einmal**
  `PATCH /artifacts/bulk-update/`.
- Verhalten bei 409: Entwürfe bleiben im Browser, betroffene Felder werden markiert, „Alle
  speichern" bleibt möglich (nach Neuladen des betroffenen Artefakts), „Verwerfen" ist explizit.

- [ ] **Step 1:** Tests (fail): `save_all_sends_one_request_with_all_entries`,
  `conflict_keeps_all_drafts_and_marks_the_artifact`,
  `discard_clears_drafts_without_request`, `dirty_counter_matches_changed_fields`,
  `save_all_is_disabled_without_changes`, `field_level_errors_from_response_are_mapped`.
- [ ] **Step 2:** Implementieren; Umschalter Sofort ↔ Sammeln in der Kopfzeile, Zustand **nicht**
  persistiert (bewusst: der Modus ist eine Arbeitsweise, kein Besitzstand).
- [ ] **Step 3:** `npm test -- DocumentSaveBar` grün.
- [ ] **Step 4:** Commit `feat(ui): add batch save for document view`.

**Akzeptanz R6:** Ein Stapel ist **ein** Request; bei einem Fehler bleibt der Server unverändert und
die Oberfläche behält alle Entwürfe; die Fehlerliste wird je Eintrag auf das Feld abgebildet.
**Gates:** R3 muss gemergt sein; i18n-Parität. **Mergebar allein: ja.**

---

# R7 — Export, Druck, Doku, Status

### Task R7.1: Markdown-Export aus dem Leseobjekt

**Files:**
- Modify: `backend/rest_api/views.py` (`DocumentViewSet.view_export` oder `view?format=markdown`),
  `backend/application/document_reading_service.py` (`to_markdown()`)
- Test: `backend/rest_api/tests/test_document_view_api.py`,
  `backend/application/tests/test_document_reading_service.py`

**Interfaces:**
- Produces: `GET /api/v1/documents/{id}/view/?format=markdown` → `text/markdown`, exakt der
  Lesestand der Oberfläche (Kapitelnummern, Reihenfolge, keine Bearbeitungsmarken).
- Bewusst **kein** neuer MCP-Endpunkt: `document.projection` liefert bereits Markdown; der
  Unterschied (Kapitelnummern) ist ein UI-Detail. Offene Entscheidung O6.

- [ ] **Step 1:** Tests (fail): `test_markdown_export_matches_reading_object`
  (Golden-File aus `to_dict()`-Kapiteln), `test_export_contains_no_edit_markers`,
  `test_export_of_empty_body_is_empty_document`.
- [ ] **Step 2:** Implementieren.
- [ ] **Step 3:** `pytest` grün.
- [ ] **Step 4:** Commit `feat: export document reading view as markdown`.

### Task R7.2: Druck-Stylesheet, Feature-Doku, ADR-Nachtrag, Spec-Status

**Files:**
- Modify: `frontend/src/components/Documents/Documents.module.css` (`@media print`),
  `docs/se/ADR/ADR-026_document_artefakt.md` (Nachtrag: Sicht ist bearbeitbar, kein zweites Modell),
  `docs/superpowers/specs/2026-11-04-dokumentensicht-neu-design.md` (Statuszeile: Richtung E1(b)
  umgesetzt, §4.1 als überholt markiert)
- Create: `docs/features/document-reading-view.md`
- Test: `e2e/tests/document-reading-view.spec.ts` (neu)

- [ ] **Step 1:** E2E schreiben: Kapitel sichtbar, Bearbeiten eines Feldes im Sofort-Modus,
  Sammelmodus mit zwei Änderungen → ein Request, Konfliktfall, Druckansicht ohne Bedienelemente
  (`page.emulateMedia({ media: "print" })`).
- [ ] **Step 2:** Print-CSS, Doku, ADR-Nachtrag, Spec-Statuszeile schreiben.
- [ ] **Step 3:** `npx playwright test document-reading-view` grün.
- [ ] **Step 4:** Commit `docs: document the document reading view`.

**Akzeptanz R7:** Export = Lesestand (Golden-File), Druck ohne Bedienelemente, ADR-026 und Spec
sagen die Wahrheit über den gebauten Zustand. **Zwei Restpunkte aus der Triage (REST `tree/`,
MCP `allocation.view`)** sind **nicht** Teil dieses Plans. **Mergebar allein: ja.**

---

## 3. Offene Entscheidungen

| # | Entscheidung | Optionen | Empfehlung | blockiert |
|---|---|---|---|---|
| **O1** | Woher kommen die Kapitel? | (a) Überschriften des `body` (dieser Plan); (b) Kapitel-Konfiguration wie Spec V2 — bräuchte doch ein Modell | **(a)** — ohne Modell ist (b) nicht darstellbar; die Spec §4.1 ist damit überholt | R1 |
| **O2** | Welche Felder sind in v1 bearbeitbar? | (a) `title`, `description`, `body`, `doc_date`, `custom_fields`; (b) zusätzlich `kind` | **(a)** — `kind` ist Klassifikation, nicht Inhalt, und steht in `FROZEN_FIELDS`; Änderung im Formular | R2 |
| **O3** | Bulk-Update-Semantik | (a) alles oder nichts, max. 100 (Spec B4); (b) Teilerfolg mit Fehlerliste | **(a)** — (b) widerspricht dem Anti-Ziel der Spec | R3, R6 |
| **O4** | Umgang mit `repo_external` | (a) in der Sicht schreibgeschützt, bearbeitbar erst nach `adopt`; (b) schreibbar, `adopt` entfällt | **(a)** — ein Schreibzugriff würde den Hash-Vertrag fälschen (`source_sha256`) | R2 |
| **O5** | Welche Typen kann Bulk-Update in v1? | (a) `Document` + `Requirement`; (b) alle Typen mit Update-Dienst | **(a)** — zwei Typen decken Sicht und Tabellenansicht ab; jeder weitere Typ ist eine Zeile in `UPDATE_DISPATCH` | R3 |
| **O6** | Attribut-Layout je Kapitel (Spec E2/V8) | (a) in v1 weglassen, nur globale Darstellung; (b) Nutzerpräferenz `ui.document_view.*` | **(a)** — ohne Kapitel-Konfiguration gibt es kein „je Kapitel"; (b) wäre eine Scheinlösung | R4 |
| **O7** | Eigener Markdown-Export oder `document.projection` | (a) `?format=markdown` am Leseobjekt; (b) nur die bestehende Projektion | **(a)** — die Projektion hat eine andere Kapitel-Logik; zwei Ausgaben würden auseinanderlaufen | R7 |

## 4. Risiken

| # | Risiko | Maßnahme |
|---|---|---|
| **R1** | Zwei Renderer (Projektion und Leseobjekt) driften auseinander | Kapitelung ist ein gemeinsames Modul (`document_reading_chapters.py`); Golden-File-Test für den Export; `to_markdown()` liest ausschließlich `chapters` |
| **R2** | `editable` behauptet etwas anderes als der Schreibpfad erlaubt | Tabellentest über Feld × Zustand × Rolle (R2.2 Schritt 1) ist Pflicht, nicht optional |
| **R3** | Bulk-Update umgeht Rechte/Sperren | Jeder Eintrag ruft den Typ-Dienst; Test „gesperrtes Feld → nichts geschrieben"; kein generischer Fallback auf `ArtifactService` |
| **R4** | `version`-Drift: Leseobjekt liefert `version`, Client speichert mit veralteter | ETag am `view`-Endpunkt; `If-Match` im Sofort-Modus; `expected_version` je Eintrag im Stapel |
| **R5** | Große Bodies brechen die konstante Abfragezahl | `test_query_count_is_constant`; Kapitel sind reine Textverarbeitung, keine Query je Kapitel |
| **R6** | Tool-Zähler-Gate wird vergessen (R3) | R3 ist der **einzige** Schnitt mit Tool-Änderung; Checkliste in §5 |
| **R7** | Kapitelung zerlegt Code-Blöcke oder Tabellen | Fenced-Block-Test; Überschriften nur außerhalb von Zäunen; Sprünge > `max_level` werden Text |
| **R8** | Spec und ADR behaupten weiter einen `DocumentView` | R7.2 zieht ADR-026-Nachtrag + Spec-Statuszeile nach; die Spec wird nicht gelöscht (Entscheidungsnachweis) |

## 5. Querschnitt-Gates (je Schnitt prüfen)

| Gate | gilt für |
|---|---|
| `backend/rest_api/tests/test_openapi.py`, `test_schema_completeness_1388.py` | R1, R3, R7 |
| `backend/rest_api/tests/test_architecture.py` (kein ORM in View/MCP) | R1–R3 |
| `backend/mcp_server/tests/test_tool_manifest_drift.py` + `tool_count` | **nur R3** (296 → 297) |
| RLS-/Mandanten-Tests (`test_document_views.py`-Familie) | R1, R2, R3 |
| `frontend/src/i18n/locales.test.ts` (DE/EN-Parität) | R4–R6 |
| `frontend/src/**/ui-ratchet.test.ts` (keine Inline-Styles) | R4–R6 |
| `e2e` (4 Shards) | R4, R7 |
| Migrationen: **keine** | alle |

## 6. Self-Review

- Jeder Task mappt auf genau eine Rolle: `senior-developer` (R1–R3, R7.2), `frontend-component-engineer`
  (R4–R6), `technical-writer` (R7.2 Doku). Keine Dateiüberlappung innerhalb einer Parallel-Gruppe:
  R4–R6 sind sequenziell, weil alle drei `Documents.tsx` berühren.
- Jedes Akzeptanzkriterium ist prüfbar: Query-Zahl, HTTP-Code + DB-Assertion, DOM-Testid,
  Golden-File, E2E-Schritt. Kein „funktioniert korrekt".
- `Files:`/`Interfaces:` sind je Task vollständig (Consumes/Produces getrennt).
- `pipeline_stages` gesetzt (`implement: 1`, gleiche Konvention wie
  `2026-11-15-ai-summaries-implementation.md`).
- Der Plan fügt **kein** Modell und **keine** Migration hinzu — das ist die Kernzusage der Richtung
  E1(b) und wird in jedem Schnitt geprüft.
