---
type: PLAN
title: "KI-Zusammenfassungen für Artefakte (#1792) und Artefakttypen (#1793) — Umsetzung S1–S8"
status: planned
date: 2026-11-15
author_agent: planner
language: de
spec: "docs/superpowers/specs/2026-11-14-ai-artifact-summaries-design.md"
related_issues: [1792, 1793, 18]
branch_basis: "docs/1792-1793-summary-concept (PR #1831), Worktree .tmp/wt-phase-b1, Basis origin/main"
pipeline_stages:
  implement: 1
---

# KI-Zusammenfassungen — Umsetzungsplan (S1–S8)

**Goal:** Die beschlossene Spec (§9/E1–E11) in acht einzeln mergebare Schnitte umsetzen: zuerst den
on-demand-Service samt REST (S1), dann Inspector-Panel (S2) und das MCP-Tool `artifact.summary` (S3);
danach die persistente Typ-Zusammenfassung — Modell (S4), Sweep/Takt (S5), Lesepfade und die zwei
Summary-Tools (S6); zuletzt die querschnittliche Sprach-Einstellung (S7, unabhängig lieferbar) und
Sichtbarkeit/Audit/Doku/Prune-Notiz (S8). Nach S6 ist #1793 vollständig lesbar, nach S8 vollständig
sichtbar und dokumentiert.

**Architecture:** Ein Service (`ArtifactSummaryService`) mit zwei Scopes (§7.1): `summarize_artifact`
(#1792, cache-only) und `summarize_artifact_type` (#1793, ein Upsert-Stand je Scope). Beide teilen
Provider-/Budget-Gates, Kappen und die Sprachauflösung aus `application/ai_language.py` (§7.6).
Persistenz ist **Upsert** (E5), die Zeitachse liefert das `AuditLog` (§6.7). MCP: `artifact.summary`
gehört zum bestehenden `artifact`-Präfix (CrossCuttingToolGroup), die #1793-Tools bilden die neue
Gruppe `summary`.

**Tech Stack:** Django 6.1 + DRF + drf-spectacular, Celery 5.6 + django-celery-beat, DRF-Throttling,
pytest 9, PostgreSQL 16 (RLS), React 19 + TypeScript 5.5 (strict) + Vite 8 + Vitest 5 für S2/S8.

**Spec:** `docs/superpowers/specs/2026-11-14-ai-artifact-summaries-design.md` (beschlossen 2026-11-14).

**Auftrag:** #1792 (Einzel-Zusammenfassung), #1793 (zyklische Typ-Zusammenfassungen), Folgearbeit zu #18.

**Nicht in diesem Plan:** Delta-Zusammenfassung („was hat sich geändert", Spec §12/O3),
Workspace-Gesamtbericht (O4), Embedding-Index über Zusammenfassungen (Spec §2).

---

## 0. Globale Constraints

- **Layer-Disziplin (ADR-01):** Views/MCP rufen nur die Layer-2-Fassade; kein ORM in
  `backend/mcp_server/` (`backend/rest_api/tests/test_architecture.py`).
- **Kein Provider-Call ohne Gate:** Flag → Budget → Deckel → Agent-Key → Throttle, in dieser
  Reihenfolge (Spec §6.4).
- **Nichts wird gecacht, was degradiert ist** (Mock, leer, Budget, Fehler).
- **Rechte vor Payload:** ein Nachbar ohne `read` erscheint nicht im Prompt — auch nicht gekürzt
  (Spec §5.5). Das ist die härteste Anforderung des Plans.
- **Upsert, nicht Historie:** genau eine Zeile je `(workspace, artifact_type)` bzw.
  `(workspace, artifact)` (Spec §9/E5). Kein `AppendOnlyViolation` in dieser Tabelle.
- **Ein Sprach-Pfad:** kein Prompt baut eine eigene Sprach-Heuristik. Bis S7 ist
  `AiDerivationService._language_instruction` die einzige Quelle, ab S7 `application/ai_language.py`
  (Spec §7.6).
- **Degradations-Enum ist geschlossen:** `budget_exhausted | provider_unavailable | stale | disabled`
  (Spec §9/E11). Kein Freitext in der Antwort (CWE-209).
- **Jeder neue Prompt-Slot braucht eine Case-Datei** und `export_promptfoo_configs --check` muss
  grün sein (Spec §3.4/7).
- **Tool-Zahl ist ein Doku-Gate, nicht nur ein Manifest-Feld:** jede Änderung zieht sieben Dateien
  nach sich (siehe §11 „Querschnitt-Gates").

## 1. Schnitt-Übersicht

| # | Schnitt | Agent | Depends on | Mergebar allein? |
|---|---|---|---|---|
| S1 | Service + REST (#1792) | senior-developer | — | **ja** |
| S2 | Inspector-Panel | frontend-component-engineer | S1 | ja (nur UI-Konsument) |
| S3 | MCP `artifact.summary` (Tool 294) | developer | S1 | ja |
| S4 | Modell `ArtifactSummary` + RLS | database-engineer | — | ja (noch ohne Konsument) |
| S5 | Sweep + Beat + Flag + Workspace-Takt | senior-developer | S4 | ja (schreibt, noch nicht lesbar) |
| S6 | Lesepfade + MCP `summary.get`/`summary.refresh` (296) | developer | S5 | ja |
| S7 | Sprach-Einstellung für alle KI-Aktivitäten | senior-developer | — | ja (querschnittlich, eigener PR) |
| S8 | UI-Sichtbarkeit + Audit + Doku + Prune-Notiz | documenter | S6 | ja (Doku/UI-additiv) |

Empfohlene Reihenfolge: **S1 → (S2, S3 parallel) → S4 → S5 → S6 → S7 → S8**. S7 darf jederzeit
vorgezogen werden, weil es keinen Summary-Code voraussetzt; es ändert aber Prompts bestehender
Flows und braucht deshalb einen eigenen, ruhigen PR.

## 2. File Structure

- Modify: `backend/application/prompt_slots.py` — zwei Slots, Datenvariablen, `MEMORY_HARD_OFF_SLOTS`
- Modify: `backend/application/ai_derivation_service.py` — `PROMPT_TEMPLATE_DEFAULTS`,
  `_language_instruction`-Delegation
- Modify: `backend/rest_api/views.py` — Summary-Views, Workspace-Feld `ai_language`
- Modify: `backend/rest_api/urls.py` — drei neue Routen
- Modify: `backend/rest_api/serializers.py` — `ai_language` im Workspace-Payload
- Modify: `backend/rest_api/throttling.py` — DRF-Scope `artifact_summary`
- Modify: `backend/reqogniloom/settings.py` — Flag, Tick, Intervall, Budget, Agent-Key, Beat-Eintrag
- Modify: `backend/persistence/models.py` — `ArtifactSummary`, Workspace-Felder
- Modify: `backend/application/tasks.py` — Sweep-Task(s), Prune-Task
- Modify: `backend/mcp_server/tools/cross_cutting.py` — `artifact.summary`
- Modify: `backend/mcp_server/workspace_scope.py` — `_TOOL_TARGETS["artifact.summary"]`
- Modify: `backend/mcp_server/tool_registry.py` — Gruppe `summary` registrieren
- Modify: `backend/mcp_server/tools/admin.py` — `ai_language` im `workspace`-Payload
- Modify: `backend/memory/tasks.py` — Sprache aus `resolve_ai_language`
- Modify: `backend/application/ai_review_service.py`, `backend/application/architecture_decompose_service.py` — Delegation statt eigener Direktive
- Modify: `docs/agent-templates/tool-manifest.json` — 293 → 294 → 296
- Modify: `docs/api/MCP-SURFACE.md` — Präfix-Tabelle + „neueste Änderung"
- Modify: `.meta-config/project.yaml`, `AGENTS.md`, `CLAUDE.md`, `README.md`, `docs/clients/antigravity.md`, `docs/clients/antigravity.de.md` — Tool-/Präfix-Zahlen
- Modify: `backend/rest_api/tests/fixtures/openapi_operations_manifest.json` — Operations-Inventar
- Modify: `frontend/src/components/shared/ArtifactInspector/InspectorTabs.tsx`, `InspectorShell.tsx`, `index.ts` — Panel/Tab einhängen
- Modify: `frontend/src/i18n/index.ts` — DE/EN-Labels
- Modify: `frontend/src/api/index.ts` — Export des neuen API-Moduls
- Create: `backend/application/artifact_summary_service.py` — Fach-Fassade (#1792/#1793)
- Create: `backend/application/artifact_summary_sweep.py` — Gates/Sweep
- Create: `backend/application/ai_language.py` — zentrale Sprachauflösung
- Create: `backend/mcp_server/tools/summaries.py` — Gruppe `summary`
- Create: `frontend/src/components/shared/ArtifactInspector/SummaryPanel.tsx` (+ `.module.css`, `.test.tsx`)
- Create: `frontend/src/api/artifact-summary.ts` (+ `.test.ts`)
- Test: `backend/application/tests/test_artifact_summary_service.py`
- Test: `backend/application/tests/test_artifact_summary_sweep.py`
- Test: `backend/application/tests/test_ai_language.py`
- Test: `backend/rest_api/tests/test_artifact_summary_1792.py`
- Test: `backend/rest_api/tests/test_artifact_summary_1793.py`
- Test: `backend/mcp_server/tests/test_artifact_summary_tools.py`
- Test: `backend/persistence/tests/test_artifact_summary_model.py`
- Test: `backend/application/prompt_testing/cases/artifact_summary.yaml`
- Test: `backend/application/prompt_testing/cases/artifact_type_summary.yaml`

---

## 3. S1 — Service + REST (#1792)

**Ziel:** Ein authentifizierter Nutzer ruft `GET /api/v1/artifacts/{artifact_id}/summary/` und erhält
eine Zusammenfassung des Artefakts **plus** seiner sichtbaren Trace-Nachbarn (Tiefe konfigurierbar,
Default 1 Hop), oder eine degradierte Antwort mit Grund. Kein DB-Schreibpfad.

**Agent:** `senior-developer`. **Depends on:** — (E2, E3, E10, E11). **Reihenfolge:** erste Slice.

**Files (Ownership):**
- Create: `backend/application/artifact_summary_service.py`
- Create: `backend/application/tests/test_artifact_summary_service.py`
- Create: `backend/rest_api/tests/test_artifact_summary_1792.py`
- Create: `backend/application/prompt_testing/cases/artifact_summary.yaml`
- Modify: `backend/application/prompt_slots.py`, `backend/application/ai_derivation_service.py`
- Modify: `backend/rest_api/views.py`, `backend/rest_api/urls.py`, `backend/rest_api/throttling.py`
- Modify: `backend/reqogniloom/settings.py`, `backend/persistence/models.py` (nur Workspace-Feld
  `summary_trace_depth` + Migration)
- Modify: `backend/rest_api/tests/fixtures/openapi_operations_manifest.json`

**Interfaces:**
- Produces: `ArtifactSummaryService.summarize_artifact(artifact_id, ctx, *, refresh=False, depth=None) -> ArtifactSummaryResult`
  mit `text`, `degraded`, `degraded_reason`, `cache_hit`, `trace_depth`, `neighbour_count`,
  `omitted_neighbours`, `generated_at`.
- Produces: REST `GET /api/v1/artifacts/{artifact_id}/summary/`; DRF-Scope `artifact_summary`
  (Default `60/hour`); Prompt-Slot `artifact_summary`.
- Produces: `resolve_trace_depth(workspace) -> int` (1..2, Default 1) — in S1 lokal, ab S7 aus
  `application/ai_language.py`-Nachbarschaft bzw. unverändert.
- Consumes: `EffectivePermissionService.resolve_effective_permission`,
  `AiDerivationService._resolve_and_render`, `llm_adapter.providers.get_provider`,
  `llm_adapter.token_tracking.is_over_daily_limit`, `TraceLink` (Layer 2, kein View-ORM).

**Arbeitsschritte (TDD):**
- [ ] Step 1: Test schreiben (fail): Payload-Bau kappt 21 Nachbarn auf 20, 300 Zeichen je Nachbar,
      1 500 für das Artefakt; Sortierung `(hop, link_type, uid)` ist stabil.
- [ ] Step 2: Test schreiben (fail): Rechte-Leak — Nachbar ohne `read` fehlt im Prompt,
      `omitted_neighbours=1`; zwei Sichtmengen ⇒ zwei Cache-Schlüssel.
- [ ] Step 3: Test schreiben (fail): Degradation (kein Provider, `mock`, Budget, Exception) ⇒
      `degraded=True`, Enum-Grund, nichts gecacht.
- [ ] Step 4: `Workspace.summary_trace_depth` (SmallInteger, Default 1) + Migration; Klemmung
      1..2 mit Test (`0` ⇒ 1, `7` ⇒ 2).
- [ ] Step 5: Slot `artifact_summary` in `PROMPT_TEMPLATE_DEFAULTS` + `_DATA_VARIABLES_BY_SLOT`
      (`artifact_json`, `neighbours_json`, `artifact_type`, `language`) + `MEMORY_HARD_OFF_SLOTS`.
- [ ] Step 6: Prompt-Case `artifact_summary.yaml` (0 Nachbarn, 3 Nachbarn, 21 Nachbarn) und
      `export_promptfoo_configs --check` lokal grün.
- [ ] Step 7: Service implementieren (Payload-Builder, Cache-Key, `_resolve_provider`/`_complete`
      nach `backend/application/search_summary_service.py`-Muster; Sprach-Direktive aus §7.6 bzw.
      vorläufig `_language_instruction`, wenn S7 noch nicht gelandet ist).
- [ ] Step 8: REST-View + URL + Throttle + Settings (`ARTIFACT_SUMMARY_ENABLED`,
      `SUMMARY_DAILY_TOKEN_LIMIT`, `SUMMARY_MAX_NEIGHBOURS`, `SUMMARY_MAX_CHARS_PER_NEIGHBOR`,
      `SUMMARY_SYNC_TIMEOUT_SECONDS`, `SUMMARY_CACHE_TTL_SECONDS`, `ARTIFACT_SUMMARY_RATE`).
- [ ] Step 9: OpenAPI-Fixture regenerieren, Gate-Tests grün, Commit.

**Akzeptanzkriterien:**
1. 200-Antwort enthält exakt die Felder aus Spec §5.7 (`artifact_id`, `artifact_type`, `summary`,
   `degraded`, `degraded_reason`, `cache_hit`, `trace_depth`, `neighbour_count`,
   `omitted_neighbours`, `generated_at`).
2. Artefakt mit 21 sichtbaren Nachbarn ⇒ `neighbour_count=20`, `omitted_neighbours=1`.
3. `summary_trace_depth=2` ⇒ Hop-2-Nachbarn im Prompt, aber nach allen Hop-1-Nachbarn; `=7` ⇒
   Verhalten wie 2, `=0` ⇒ wie 1.
4. Zweiter identischer Aufruf ⇒ `cache_hit=true` und **null** Provider-Calls (Spy).
5. Alle vier Degradationsfälle ⇒ HTTP 200, `summary=null`, korrekter `degraded_reason`; nichts im
   Cache.
6. `ARTIFACT_SUMMARY_ENABLED=false` ⇒ 200 mit `degraded=true`, `degraded_reason="disabled"`,
   null Provider-Calls (E11-Grund statt verstecktem 404).
7. Fremder Tenant ⇒ 404; fehlende Rolle oder `ItemPermission=deny` ⇒ 403; >60 Aufrufe/h ⇒ 429 mit
   `Retry-After`.
8. `test_schema_completeness_1388.py` grün mit aktualisiertem Inventar.

**Teststrategie:** Unit (Payload/Kappen/Determinismus/Degradation), API (Feldvertrag, 404/403/429,
OpenAPI-Inventar), Kosten (Cache-Hit = 0 Calls, Budget-Gate), Flag (disabled-Pfad). Kein MCP-Delta.

**Gates:** `pytest backend/application/tests/test_artifact_summary_service.py`,
`pytest backend/rest_api/tests/test_artifact_summary_1792.py`,
`pytest backend/rest_api/tests/test_schema_completeness_1388.py`,
`python manage.py export_promptfoo_configs --check`,
`pytest backend/memory/tests/test_injection_policy.py`.

**Risiken:** (a) Rechtefilter-Latenz bei vielen Nachbarn — pro Nachbar eine
`resolve_effective_permission`-Abfrage; bei Bedarf Batch-Auflösung, aber erst messen.
(b) Prompt-Größe bei Tiefe 2 — Kappen sind fix, Test deckt es ab. (c) `summary_trace_depth` in S1
statt S4 ist bewusst: S1 darf nicht auf S4 warten.

**Mergebar ohne Folgeschnitt?** **Ja** — REST-only, kein Manifest-, kein persistenter Schreibpfad.

---

## 4. S2 — Inspector-Panel

**Ziel:** Ein Panel/Tab im Artefakt-Inspector, das die Zusammenfassung auf Klick holt, Lade-/Fehler-
und Degradations-Zustand zeigt (mit E11-Grund) und ohne Klick **keinen** Provider-Call auslöst.

**Agent:** `frontend-component-engineer`. **Depends on:** S1. **Reihenfolge:** parallel zu S3.

**Files (Ownership):**
- Create: `frontend/src/components/shared/ArtifactInspector/SummaryPanel.tsx`,
  `SummaryPanel.module.css`, `SummaryPanel.test.tsx`
- Create: `frontend/src/api/artifact-summary.ts`, `frontend/src/api/artifact-summary.test.ts`
- Modify: `frontend/src/components/shared/ArtifactInspector/InspectorTabs.tsx`,
  `InspectorShell.tsx`, `index.ts`, `frontend/src/i18n/index.ts`, `frontend/src/api/index.ts`

**Interfaces:** Consumes `GET /api/v1/artifacts/{artifact_id}/summary/`; Produces
`SummaryPanel` (`props: { artifactId: string; artifactType: string }`) und
`fetchArtifactSummary(artifactId)`.

**Arbeitsschritte (TDD):**
- [ ] Step 1: API-Wrapper-Test (fail) — Pfad, Fehler-Mapping, kein Retry.
- [ ] Step 2: Panel-Test (fail) — Klick löst genau einen Request aus; Mount löst keinen aus.
- [ ] Step 3: Zustände implementieren (idle/loading/ok/degraded/error) inkl. `degraded_reason`-Label.
- [ ] Step 4: i18n DE/EN, `data-testid`: `summary-panel`, `summary-trigger`, `summary-text`,
  `summary-degraded`, `summary-degraded-reason`.
- [ ] Step 5: A11y — `role="status"` für Ladezustand, Fokus bleibt am Button, Panel-Titel als
  Überschrift; Tastatur-Test.
- [ ] Step 6: In Inspector-Tabs einhängen (additiv, B2-Kompatibilität: eigener Tab/Slot).

**Akzeptanzkriterien:**
1. Panel rendert ohne Netzwerkaufruf und zeigt „noch nicht zusammengefasst".
2. Ein Klick = ein Request; während des Ladens ist der Button deaktiviert.
3. Degradierte Antwort zeigt Text **und** übersetzten Grund (vier Enum-Werte).
4. Alle interaktiven Elemente haben `data-testid`; Labels existieren in DE und EN.
5. Vitest-Suite grün, keine `console.error`.

**Teststrategie:** Vitest + Testing Library (Zustände, Request-Zahl via Mock), i18n-Vollständigkeit,
A11y-Assertions. Kein API-/Kosten-/Flag-Test (Backend liegt in S1).

**Gates:** `npm test -- SummaryPanel`, `npm test -- artifact-summary`, `npm run lint`,
`npm run typecheck`, `frontend/src/i18n/locales.test.ts`.

**Risiken:** Kollision mit Phase B2 (Inspector-Umbau, Spec §12/O1) — Einbau als eigener Tab, nicht
als Umbau von `InspectorShell`.

**Mergebar ohne Folgeschnitt?** **Ja** — reine additive UI auf einem bestehenden Endpunkt.

---

## 5. S3 — MCP `artifact.summary` (Tool 294)

**Ziel:** Dasselbe Ergebnis wie S1 für Agenten, als Tool im bestehenden `artifact`-Präfix
(CrossCuttingToolGroup). Tool-Zahl 293 → 294.

**Agent:** `developer`. **Depends on:** S1. **Reihenfolge:** parallel zu S2.

**Files (Ownership):**
- Modify: `backend/mcp_server/tools/cross_cutting.py` — Schema + Handler `artifact.summary`
- Modify: `backend/mcp_server/workspace_scope.py` — `_TOOL_TARGETS["artifact.summary"] = (("artifact_id", "artifact"),)`
- Modify: `backend/mcp_server/tool_registry.py` — Feature-Gate-Eintrag (falls Flag als Feature
  modelliert wird: `artifact_summary`)
- Modify: `docs/agent-templates/tool-manifest.json` (294), `docs/api/MCP-SURFACE.md`,
  `.meta-config/project.yaml`, `AGENTS.md`, `CLAUDE.md`, `README.md`,
  `docs/clients/antigravity.md`, `docs/clients/antigravity.de.md`
- Create: `backend/mcp_server/tests/test_artifact_summary_tool.py`

**Interfaces:** Consumes `ArtifactSummaryService.summarize_artifact`. Produces Tool
`artifact.summary({artifact_id: string, refresh?: boolean})` → dieselben Felder wie REST;
`RATE_LIMITED` über `admin_ops.rate_limits.resolve_rate("artifact_summary", tenant_id=…)`.

**Arbeitsschritte (TDD):**
- [ ] Step 1: Dispatch-Test (fail) — unbekanntes/fehlendes `artifact_id` ⇒ `VALIDATION_ERROR`.
- [ ] Step 2: Schema strikt (`refresh` nur echtes Boolean; String `"false"` ist ein Fehler).
- [ ] Step 3: Handler implementieren (kein ORM im MCP-Root; Service aufrufen).
- [ ] Step 4: Rate-Parität + `PERMISSION_DENIED` bei fremdem Workspace (Test).
- [ ] Step 5: `_TOOL_TARGETS`-Eintrag; `test_mcp_workspace_scope.py` grün.
- [ ] Step 6: Manifest regenerieren (294) und alle sieben Doku-Zahlen nachziehen; Gates grün.

**Akzeptanzkriterien:**
1. `tool_count` = 294, `test_tool_manifest_drift.py` grün.
2. `test_mcp_workspace_scope.py` grün (Tool klassifiziert).
3. Fremder Workspace/Artefakt ⇒ `PERMISSION_DENIED` (kein Existenz-Leak).
4. 61. Aufruf in einer Stunde ⇒ `RATE_LIMITED`.
5. Antwortfelder identisch zu S1 (ein gemeinsamer Contract-Test über beide Kanäle).
6. Alle Doku-Zahlen (manifest, project.yaml, AGENTS, CLAUDE, README, MCP-SURFACE, clients) = 294.

**Teststrategie:** MCP-Delta (Manifest, Scoping, striktes Schema, Rate), Contract-Parität REST↔MCP,
Kosten (disabled-Pfad liefert `degraded_reason="disabled"` ohne Call), Flag (Gate greift).

**Gates:** `pytest backend/mcp_server/tests/test_artifact_summary_tool.py`,
`test_tool_manifest_drift.py`, `test_mcp_workspace_scope.py`,
`backend/rest_api/tests/test_architecture.py`,
`pytest docs/agent-templates/test_meta_tool_count_drift.py`,
`pytest docs/agent-templates/test_doc_surface_consistency.py`,
`pytest scripts/clients/test_render.py` (nach Re-Render).

**Risiken:** Der Präfix `artifact` gehört `CrossCuttingToolGroup` — kein neues Gruppenobjekt, sonst
dupliziert `tools/list` die Schemas (REQ-129). Doku-Drift ist hier der wahrscheinlichste rote Test.

**Mergebar ohne Folgeschnitt?** **Ja** — reiner zusätzlicher Kanal auf S1.

---

## 6. S4 — Modell `ArtifactSummary` + RLS

**Ziel:** Die Tabelle aus Spec §6.1 steht: ein Stand je Scope, zwei partielle Unique-Constraints,
RLS-Policy, Upsert-Helfer. Noch kein Schreiber, kein Leser.

**Agent:** `database-engineer`. **Depends on:** — (E4, E5). **Reihenfolge:** nach S1/S2/S3 möglich,
spätestens vor S5.

**Files (Ownership):**
- Modify: `backend/persistence/models.py` — `ArtifactSummary` (+ `TenantScopedModel`)
- Create: `backend/persistence/migrations/XXXX_artifact_summary.py`,
  `backend/persistence/migrations/XXXX_artifact_summary_rls_policy.py`
- Create: `backend/persistence/tests/test_artifact_summary_model.py`
- Create: `backend/application/summary_support.py` (nur wenn ≥3 Helfer geteilt werden; sonst in den
  Service)

**Interfaces:** Produces Modell `ArtifactSummary` (Felder: `workspace`, `summary_kind`, `artifact`,
`artifact_type`, `text`, `content_hash`, `input_digest`, `prompt_slot/scope/version`, `provider`,
`model`, `token_usage`, `trigger`, `status`, `reason`, `generated_at`) und
`upsert_summary(...)`-Helfer mit `IntegrityError`-Retry. Consumes `TenantContext`/RLS-Konvention.

**Arbeitsschritte (TDD):**
- [ ] Step 1: Modell + Migration; `makemigrations --check` sauber.
- [ ] Step 2: Test (fail): zweiter `upsert` für denselben Scope erzeugt **keine** zweite Zeile.
- [ ] Step 3: Test (fail): Unique-Constraint greift (Type-Scope und Artifact-Scope getrennt).
- [ ] Step 4: Test (fail): `(workspace, artifact)` mit `artifact=NULL` kollidiert nicht (Postgres
  behandelt NULL als distinct) — Dokumentation des Prune-Falls.
- [ ] Step 5: RLS-Policy-Migration nach Vorbild `persistence/migrations/0122_quality_assessment_rls_policy.py`;
  Test: Tenant A sieht B nicht.
- [ ] Step 6: Paralleler Insert (simulierter `IntegrityError`) endet in genau einer Zeile.

**Akzeptanzkriterien:**
1. Zwei partielle Unique-Constraints existieren und sind per Test nachweisbar.
2. `upsert_summary` ist idempotent (zweiter Aufruf ändert `updated_at`, nicht die Zeilenzahl).
3. RLS-Test grün (Tenant-Isolation, `unscoped` ausgenommen).
4. Indizes `(workspace, summary_kind, artifact_type)` und `(tenant, content_hash)` vorhanden.
5. Kein `AppendOnlyViolation`/`QualityAssessmentQuerySet`-Wiederverwendung.

**Teststrategie:** Unit/DB (Constraints, Upsert, Retry, RLS), Migrationstest. Kein API-/MCP-/
Kosten-Test (kein Konsument).

**Gates:** `pytest backend/persistence/tests/ -k artifact_summary`,
`python manage.py makemigrations --check --dry-run`,
`pytest backend/persistence/tests/ -k rls` (bestehende RLS-Suite).

**Risiken:** Constraint-Namen müssen projektweit eindeutig sein (Präfix `uniq_artifact_summary_`).
Eine RLS-Policy ohne `FORCE ROW LEVEL SECURITY`-Muster würde still nichts schützen — Vorbild kopieren,
nicht neu erfinden.

**Mergebar ohne Folgeschnitt?** **Ja** — tote Tabelle mit Tests, keine Verhaltensänderung.

---

## 7. S5 — Sweep + Beat + Flag + Workspace-Takt

**Ziel:** Der periodische Lauf schreibt je fälligem Workspace und Typ **einen** Stand, hinter Flag,
Budget, Batch-Deckel, Agent-Key und Throttle. Takt und Typ-Scope sind je Workspace konfigurierbar.

**Agent:** `senior-developer`. **Depends on:** S4 (E6, E8). **Reihenfolge:** nach S4.

**Files (Ownership):**
- Create: `backend/application/artifact_summary_sweep.py`
- Create: `backend/application/tests/test_artifact_summary_sweep.py`
- Create: `backend/application/prompt_testing/cases/artifact_type_summary.yaml`
- Modify: `backend/persistence/models.py` — `Workspace.summary_scopes`,
  `Workspace.summary_sweep_interval_minutes` (+ Migration)
- Modify: `backend/application/tasks.py` — `artifact_summary_sweep_tick`,
  `artifact_summary_refresh_scope`
- Modify: `backend/reqogniloom/settings.py` — `ARTIFACT_SUMMARY_ENABLED`,
  `ARTIFACT_SUMMARY_TICK_MINUTES`, `ARTIFACT_SUMMARY_INTERVAL_MINUTES`,
  `ARTIFACT_SUMMARY_MIN_INTERVAL_MINUTES`, `ARTIFACT_SUMMARY_SWEEP_BATCH`,
  `ARTIFACT_SUMMARY_AGENT_KEY_ID`, `ARTIFACT_SUMMARY_MIN_INTERVAL_SECONDS`,
  `SUMMARY_DAILY_TOKEN_LIMIT`, Beat-Eintrag (nur bei Flag an)
- Modify: `backend/application/prompt_slots.py`, `backend/application/ai_derivation_service.py` —
  Slot `artifact_type_summary`

**Interfaces:** Produces `ArtifactSummarySweeper` mit
`run_for_scope(tenant_id, workspace_id, artifact_type, trigger) -> "summarized|skipped:<reason>|failed"`
und dem Tick-Task; Consumes `ArtifactSummaryService.summarize_artifact_type`, `upsert_summary`,
`_resolve_agent_context` (`backend/application/tasks.py`).

**Arbeitsschritte (TDD):**
- [ ] Step 1: Gates-Test (fail): Flag aus ⇒ `skipped:flag_off`, 0 Calls.
- [ ] Step 2: Fälligkeits-Test (fail): Intervall 1440 ⇒ Tick nach 60 min überspringt; Intervall 30
  wird auf 60 geklemmt.
- [ ] Step 3: Scope-Test (fail): `summary_scopes=["Requirement"]` ⇒ nur ein Kandidat; leer ⇒ zwölf
  Default-Typen; unbekannter Typ ⇒ Test rot (Spec §12/O10).
- [ ] Step 4: Deckel-Test (fail): 40 Kandidaten, Batch 25 ⇒ 25 Calls; Reihenfolge „nie
  zusammengefasst zuerst, dann ältester Stand".
- [ ] Step 5: Hash-Test (fail): unveränderter Eingabe-Hash ⇒ `skipped:unchanged`, **kein** Call,
  `updated_at` unverändert.
- [ ] Step 6: Budget-Test (fail): `SUMMARY_DAILY_TOKEN_LIMIT` erschöpft ⇒ Abbruch,
  `reason="budget_exhausted"`, unabhängig von `TENANT_TOKEN_LIMIT_PER_DAY`.
- [ ] Step 7: Agent-Key-Test (fail): fehlend/widerrufen ⇒ `skipped:no_agent_key`.
- [ ] Step 8: Beat-Eintrag als reine Funktion (`_artifact_summary_beat_entry`) + Test: nur bei Flag an.
- [ ] Step 9: Sweeper + Task implementieren; `TenantContext` je Tenant mit `finally`-Restore; nur IDs
  über die Queue.

**Akzeptanzkriterien:**
1. Flag aus ⇒ Sweep endet mit `disabled=True` und **null** Provider-Calls.
2. Beat enthält den Eintrag nur bei Flag an; ein nach dem Boot deaktiviertes Flag führt zu einem
   No-Op-Lauf.
3. 40 Kandidaten/Batch 25 ⇒ 25 Calls, 15 im nächsten Lauf; Zähler stimmen
   (`summarized/skipped/budget/failed`).
4. `summary_sweep_interval_minutes=30` wird auf 60 geklemmt (kein Fehler, Log-Hinweis).
5. Zweiter Lauf ohne Änderung ⇒ 0 zusätzliche Calls, `updated_at` unverändert.
6. Budget-Stopp schreibt `reason="budget_exhausted"` auf den betroffenen Scope (nur wenn ein
   Provider-Call versucht wurde; ein reiner Gate-Stopp schreibt nichts).
7. Prompt-Case `artifact_type_summary.yaml` vorhanden, `export_promptfoo_configs --check` grün.
8. `token_usage` der geschriebenen Zeile ist > 0 bei echtem Provider.

**Teststrategie:** Unit (Gates/Deckel/Fälligkeit/Hash/Budget), Task-/Beat-Test (Settings-Funktion),
Kosten (Provider-Spy zählt Calls), Flag (an/aus, nachträglich aus), RLS/Tenant-Kontext.

**Gates:** `pytest backend/application/tests/test_artifact_summary_sweep.py`,
`pytest backend/application/tests/test_tasks*.py`,
`pytest backend/memory/tests/test_injection_policy.py` (neuer Slot hard-off),
`python manage.py export_promptfoo_configs --check`,
`pytest backend/persistence/tests/test_artifact_summary_model.py`.

**Risiken:** (a) Ein `PeriodicTask`-Rest aus einem älteren Deployment feuert weiter — der Tick-Task
muss Flag und Intervall erneut lesen (Muster `backend/application/tasks.py:385-393`).
(b) Per-Workspace-Takt bei einem 60-min-Tick erzeugt viele No-Op-Läufe bei Default 1440 — gewollt,
aber die Zähler müssen das sichtbar machen. (c) Der globale Deckel kann einen kleinen Workspace
systematisch verdrängen; die Sortierung „nie zusammengefasst zuerst" verhindert das.

**Mergebar ohne Folgeschnitt?** **Ja** — Daten und Task funktionieren ohne Lesepfad; niemand sieht
etwas, aber es kostet auch nichts (Flag default aus).

---

## 8. S6 — Lesepfade #1793 + MCP `summary.get` / `summary.refresh` (Tool 296)

**Ziel:** Der geschriebene Stand wird lesbar: REST-Liste/-Einzelwert/manueller Refresh und zwei
MCP-Tools in einer neuen Gruppe `summary`. Tool-Zahl 294 → 296 (siehe Gate/Risiko).

**Agent:** `developer`. **Depends on:** S5. **Reihenfolge:** nach S5.

**Files (Ownership):**
- Modify: `backend/rest_api/views.py`, `backend/rest_api/urls.py`,
  `backend/rest_api/serializers.py`, `backend/rest_api/throttling.py`
- Modify: `backend/rest_api/tests/fixtures/openapi_operations_manifest.json`
- Create: `backend/mcp_server/tools/summaries.py` (Gruppe `summary`)
- Modify: `backend/mcp_server/tool_registry.py` (Registrierung), `docs/agent-templates/tool-manifest.json`
  (296), `docs/api/MCP-SURFACE.md`, Doku-Zahlen (sieben Dateien)
- Create: `backend/rest_api/tests/test_artifact_summary_1793.py`,
  `backend/mcp_server/tests/test_summary_tools.py`

**Interfaces:** Produces `GET /api/v1/workspaces/{id}/summaries/`,
`GET /api/v1/workspaces/{id}/summaries/{artifact_type}/`,
`POST /api/v1/workspaces/{id}/summaries/{artifact_type}/refresh/`,
`SummaryToolGroup` mit `summary.get({workspace_id, artifact_type?})` und
`summary.refresh({workspace_id, artifact_type?})`. Consumes `ArtifactSummaryService` +
`ArtifactSummarySweeper.run_for_scope` (für Refresh).

**Arbeitsschritte (TDD):**
- [ ] Step 1: API-Test (fail): Liste liefert je Typ `text`, `generated_at`, `stale`, `reason`,
  `item_count`; leerer Typ ⇒ `summary=null`, `item_count=0`, `reason=null`.
- [ ] Step 2: API-Test (fail): fremder Workspace ⇒ 404 (nicht 403 — kein Existenz-Leak).
- [ ] Step 3: Refresh-Test (fail): gleiche Gates wie Sweep (Flag/Budget/Agent-Key), `trigger="manual"`,
  Rate-Limit greift.
- [ ] Step 4: MCP-Gruppe `summary` implementieren; `workspace_id` required (kein `_TOOL_TARGETS`).
- [ ] Step 5: `summary.get` ohne `artifact_type` liefert alle Typ-Stände des Workspace.
- [ ] Step 6: Manifest regenerieren (296), Präfix-Zahl 46 → 47, alle sieben Doku-Zahlen nachziehen.

**Akzeptanzkriterien:**
1. Drei REST-Routen im OpenAPI-Inventar, Gate grün.
2. Liste/Einzelwert liefern das Spec-§6.6-Feldset; `stale=true` genau dann, wenn
   `generated_at < now - 2×Workspace-Intervall`.
3. Refresh unter Flag-aus ⇒ `degraded_reason="disabled"`, kein Call.
4. MCP: `summary.get`/`summary.refresh` funktionieren, `PERMISSION_DENIED` bei fremdem Workspace,
   `RATE_LIMITED` beim Überschreiten; `tool_count` = 296, Präfixe = 47.
5. Tool-Manifest-Drift, Workspace-Scope-Ratchet und Doku-Zahlen-Gates grün.

**Teststrategie:** API (Feldvertrag, 404/403/429), MCP-Delta (Manifest, Scoping, striktes Schema,
Rate), Kosten/Flag (Refresh respektiert alle Bremsen), Stale-Berechnung.

**Gates:** `pytest backend/rest_api/tests/test_artifact_summary_1793.py`,
`pytest backend/mcp_server/tests/test_summary_tools.py`, `test_tool_manifest_drift.py`,
`test_mcp_workspace_scope.py`, `test_schema_completeness_1388.py`,
`pytest docs/agent-templates/test_meta_tool_count_drift.py`,
`pytest docs/agent-templates/test_doc_surface_consistency.py`, `pytest backend/rest_api/tests/test_architecture.py`.

**Risiken:** **Tool-Zahl 295 vs. 296** (Spec §12/O8): Der Auftrag nennt 295, E9 beschließt zwei Tools
(294 + 2 = 296). Sollwert dieses Plans ist **296**; die einzige Alternative ist, `summary.refresh`
zu streichen (dann 295 und Refresh nur über REST). Die Entscheidung muss vor Step 6 fallen, weil
Manifest und sieben Dateien daran hängen.

**Mergebar ohne Folgeschnitt?** **Ja** — Lesepfade auf vorhandenen Daten; S8 (UI/Audit/Doku) ist
additiv.

---

## 9. S7 — Sprach-Einstellung für alle KI-Aktivitäten

**Ziel:** Eine Workspace-Einstellung (`ai_language`) steuert **jeden** LLM-Prompt; leer erbt
`Workspace.language`, danach `en`. Bestehende Flows werden verhaltensgleich umgestellt, fehlende
Flows (Search-Summary, Quality, Summaries) bekommen die Direktive erstmals.

**Agent:** `senior-developer`. **Depends on:** — (E10). **Reihenfolge:** jederzeit; bewusst eigener PR.

**Files (Ownership):**
- Create: `backend/application/ai_language.py`
- Create: `backend/application/tests/test_ai_language.py`
- Modify: `backend/persistence/models.py` — `Workspace.ai_language` (+ Migration)
- Modify: `backend/application/ai_derivation_service.py` — `_language_instruction` delegiert;
  `LANGUAGE_INSTRUCTION_NAMES` wandert nach `application/ai_language.py`
- Modify: `backend/application/ai_review_service.py`, `backend/application/architecture_decompose_service.py`,
  `backend/application/search_summary_service.py`, `backend/application/quality_service.py`
- Modify: `backend/memory/tasks.py` (Sprache für `memory.extract`)
- Modify: `backend/rest_api/serializers.py`, `backend/rest_api/views.py`,
  `backend/mcp_server/tools/admin.py` — `ai_language` im Workspace-Payload
- Modify: `backend/rest_api/tests/fixtures/openapi_operations_manifest.json`
- Modify: `backend/application/prompt_testing/cases/*.yaml` (Sprach-Variable, wo nötig)

**Interfaces:** Produces `resolve_ai_language(workspace_id) -> str`,
`language_instruction(workspace_id) -> str`, `Workspace.ai_language` (CharField(8), leer = erben).
Consumes `Workspace.language`.

**Arbeitsschritte (TDD):**
- [ ] Step 1: Test (fail): Auflösungsreihenfolge `ai_language` → `language` → `en`; unbekannter Code
  ⇒ `en`, kein Fehler.
- [ ] Step 2: Test (fail): `_language_instruction` liefert bei leerem `ai_language` exakt den
  bisherigen Text (Verhaltensgleichheit).
- [ ] Step 3: Modul + Migration implementieren; `_language_instruction` delegieren.
- [ ] Step 4: Ratchet-Test (fail): parametrisierte Liste aller Prompt-Pfade (Spec §7.6) — jeder
  gerenderte Prompt enthält die Direktive; ein neuer Pfad ohne Eintrag macht den Test rot.
- [ ] Step 5: Search-Summary + Quality auf die Direktive umstellen (eigene Tests).
- [ ] Step 6: `ai_language` in REST/MCP-Payload + OpenAPI-Fixture.
- [ ] Step 7: Doppel-Direktive verhindern: Template mit `{language}` erhält keine zweite Direktive.

**Akzeptanzkriterien:**
1. Ohne gesetztes `ai_language` sind alle bestehenden Prompt-Snapshots unverändert.
2. `ai_language="de"` ⇒ jeder Prompt der Liste enthält „Respond in German"; `="en"` ⇒ „English".
3. `memory.extract` erhält dieselbe Sprache wie die übrigen Flows (ein Test über beide Pfade).
4. REST/MCP-Workspace-Payload enthält `ai_language`; OpenAPI-Inventar grün.
5. Template mit eigenem `{language}` ⇒ genau **eine** Sprachinstruktion im Prompt.

**Teststrategie:** Unit (Auflösung, Delegation, Doppel-Direktive), Ratchet (alle Prompt-Pfade),
API (Workspace-Feld), Prompt-Cases. Kein MCP-Delta (kein neues Tool), kein Kosten-Test.

**Gates:** `pytest backend/application/tests/test_ai_language.py`,
`pytest backend/application/tests/test_ai_derivation_service.py`,
`pytest backend/application/tests/test_ai_review_service.py`,
`pytest backend/rest_api/tests/test_schema_completeness_1388.py`,
`python manage.py export_promptfoo_configs --check`.

**Risiken:** Der Ratchet-Test ist die eigentliche Arbeit — ohne ihn driftet der nächste neue Flow
sofort wieder. Ein Workspace mit `ai_language != language` erzeugt KI-Text in anderer Sprache als der
Inhalt: gewollt, in S8 zu erklären.

**Mergebar ohne Folgeschnitt?** **Ja** — verhaltensgleich bei leerem Feld, unabhängig von S1–S6.

---

## 10. S8 — UI-Sichtbarkeit + Audit + Doku + Prune-Notiz

**Ziel:** Der Typ-Stand ist im Inspector sichtbar (mit E11-Grund und „Stand vom …"), jeder echte
Provider-Call ist im AuditLog nachvollziehbar, die Betriebsdoku nennt alle neuen Env-Variablen und
Workspace-Felder, und der Prune-Fall ist dokumentiert (und optional als Task angelegt).

**Agent:** `documenter` (Slice-Owner: Doku, REQ-IDs, Prune-Notiz, Abnahme). Die zwei Code-Anteile
im selben PR liefern `senior-developer` (Audit-Aufruf) und `frontend-component-engineer`
(Inspector-Tab); ohne diese beiden ist der Schnitt nicht abnehmbar.
**Depends on:** S6. **Reihenfolge:** letzter Schnitt.

**Files (Ownership):**
- Modify: `frontend/src/components/shared/ArtifactInspector/SummaryPanel.tsx` (Tab „Überblick"),
  `frontend/src/api/artifact-summary.ts`, `frontend/src/i18n/index.ts`
- Modify: backend/application/artifact_summary_service.py (Audit-Aufruf),
  `backend/application/audit_service.py` nur falls eine Action-Konstante fehlt
- Create: `docs/AI-SUMMARIES-OPERATIONS.md` (Betrieb: Env-Variablen, Workspace-Felder, Kosten, Prune)
- Modify: `deploy/README.md` (Env-Variablen ergänzen),
  `docs/REQUIREMENTS.md` (REQ-IDs für #1792/#1793), `docs/api/MCP-SURFACE.md` (falls in S6 noch
  nicht final), `AGENTS.md`/`CLAUDE.md`/`.meta-config/project.yaml` (Endzahlen)
- Create: `frontend/src/components/shared/ArtifactInspector/SummaryOverview.test.tsx`
- Modify: `backend/application/tests/test_artifact_summary_sweep.py` (Audit-Assertions)

**Interfaces:** Consumes REST-Liste (`/summaries/`) + `summary.refresh`; Produces Audit-Action
`artifact_summary.generate` und Betriebsdoku.

**Arbeitsschritte (TDD):**
- [ ] Step 1: Test (fail): periodischer Lauf schreibt genau **einen** Audit-Eintrag pro Call; kein
  Eintrag bei Cache-Hit/unchanged/flag_off/Budget.
- [ ] Step 2: Audit-Aufruf implementieren.
- [ ] Step 3: Inspector-Tab „Überblick" (Vitest): zeigt Typ-Stand, `generated_at`, `stale`, `reason`;
  Refresh-Button ruft `POST …/refresh/`.
- [ ] Step 4: i18n DE/EN für die vier Gründe + „Stand vom".
- [ ] Step 5: Betriebsdoku (Env-Tabelle, Workspace-Felder, Kostenbeispiel aus Spec §6.4, Prune-Fall).
- [ ] Step 6: REQ-IDs vergeben und verlinken; Endzahlen der Tool-/Präfix-Doku prüfen.
- [ ] Step 7: Prune-Notiz: Waisen (`artifact=NULL`), Typen außerhalb `summary_scopes`; optional
  Task nach Muster `backend/application/tasks.py` — wenn gebaut, eigener Test.

**Akzeptanzkriterien:**
1. Ein periodischer Lauf mit 3 Calls erzeugt 3 Audit-Einträge; ein Folgelauf ohne Änderung 0.
2. Inspector zeigt für ein Artefakt mit Typ-Stand Text, Zeitstempel und ggf. `stale`/`reason`.
3. Alle neuen Env-Variablen und Workspace-Felder stehen in der Betriebsdoku.
4. REQ-IDs existieren in `docs/REQUIREMENTS.md` und referenzieren #1792/#1793.
5. Doku-Zahlen-Gates grün (`test_meta_tool_count_drift.py`,
   `test_doc_surface_consistency.py`).
6. Prune-Fall ist entschieden: entweder Task mit Test oder dokumentierte Nicht-Notwendigkeit.

**Teststrategie:** Audit (Unit), UI (Vitest), Doku-Gates, i18n-Vollständigkeit. Kein neuer
MCP-/API-Contract.

**Gates:** `pytest backend/application/tests/test_artifact_summary_sweep.py`,
`npm test -- SummaryOverview`, `pytest docs/agent-templates/test_meta_tool_count_drift.py`,
`pytest docs/agent-templates/test_doc_surface_consistency.py`, `frontend/src/i18n/locales.test.ts`.

**Risiken:** Der Inspector ist B2-Umbaugebiet (Spec §12/O1) — der Tab wird einsortiert, nicht
umgebaut. Doku-Gates sind streng: eine vergessene Zahl macht den PR rot.

**Mergebar ohne Folgeschnitt?** **Ja** — additiv; es ist der letzte Schnitt, also folgt keiner.

---

## 11. Querschnitt-Gates (gelten in jedem Schnitt, der sie berührt)

> Hinweis: Die Gate-Listen und die Datei-Listen nennen die **Soll**-Dateien des jeweiligen Schnitts.
> Bis der Schnitt gebaut ist, meldet `scripts/check_plan_refs.py` sie als `MISSING` — das ist
> erwartet und kein Planfehler; die Dateien entstehen in genau dem Schnitt, der sie nennt.

| Gate | Was es prüft | Datei/Test |
|---|---|---|
| **MCP-Manifest** | `tool_count` == `len(tools)`; Manifest ist committed | `docs/agent-templates/tool-manifest.json`, `backend/mcp_server/tests/test_tool_manifest_drift.py` |
| **Doku-Toolzahl** | `.meta-config/project.yaml`, `AGENTS.md`, `CLAUDE.md` nennen exakt `tool_count` | `docs/agent-templates/test_meta_tool_count_drift.py` |
| **Doku-Oberfläche** | `README.md`, `docs/api/MCP-SURFACE.md`, `docs/clients/antigravity.md`, `docs/clients/antigravity.de.md` nennen exakt `tool_count` | `docs/agent-templates/test_doc_surface_consistency.py` |
| **Präfix-Zahl** | 46 → 47 (`summary` neu), in denselben Dokumenten | dieselben zwei Tests |
| **Workspace-Scoping** | jedes Read-Tool ist klassifiziert oder deklariert `workspace_id` required | `backend/mcp_server/workspace_scope.py`, `backend/mcp_server/tests/test_mcp_workspace_scope.py` |
| **OpenAPI-Inventar** | jede REST-Operation ist im committed Fixture | `backend/rest_api/tests/fixtures/openapi_operations_manifest.json`, `backend/rest_api/tests/test_schema_completeness_1388.py` |
| **Prompt-Case-Files** | jeder Slot hat eine Case-Datei, Export ist vollständig | `backend/application/prompt_testing/cases/`, `python manage.py export_promptfoo_configs --check` |
| **Layer-Trennung** | kein ORM in `mcp_server/`, keine Model-Query in Views | `backend/rest_api/tests/test_architecture.py` |
| **RLS** | neue Tabelle hat Policy-Migration | `backend/persistence/migrations/`, RLS-Tests |
| **Secret-Scan** | keine Keys/Token im Diff | Paved Road `secret-scanning` vor jedem Commit |
| **Client-Render** | `docs/clients/**` == generiert | `scripts/clients/test_render.py` |

**Tool-Zahl-Fahrplan:** 293 (Ausgang) → **294** nach S3 (`artifact.summary`) → **296** nach S6
(`summary.get`, `summary.refresh`). Die im Auftrag genannte Endzahl **295** setzt E9 mit nur einem
Tool voraus; siehe Spec §12/O8 und S6-Risiko.

## 12. Reihenfolge und Abhängigkeiten

```
S1 ──┬── S2
     └── S3
S4 ── S5 ── S6 ── S8
S7 (unabhängig, jederzeit)
```

- S1 vor S2/S3 (beide konsumieren den Endpunkt/das Tool).
- S4 vor S5 (Modell + Upsert), S5 vor S6 (es gibt sonst nichts zu lesen).
- S7 ist unabhängig; wird es vorgezogen, entfällt in S1 die vorläufige `_language_instruction`-Nutzung
  (kein Merge-Konflikt, nur ein kleiner Folge-Commit).
- S8 zuletzt, weil es Endzahlen und Betriebsdoku festschreibt.

## 13. Selbstreview

- Jeder Schnitt mappt auf genau eine Rolle und ist allein mergebar (Antwort je Schnitt dokumentiert).
- Jedes Akzeptanzkriterium ist messbar (Feldwert, Call-Zahl, Zeilenzahl, Test-Grün).
- `Files:`/`Interfaces:` sind vollständig; innerhalb einer Parallel-Gruppe (S2 ∥ S3) überlappen sich
  keine Dateien.
- Keine Datei wird von zwei Schnitten gleichzeitig besessen: `backend/rest_api/views.py` ist in S1,
  S6, S7 (verschiedene Abschnitte, sequenziell), `backend/application/prompt_slots.py` in S1 und S5
  (verschiedene Slots, sequenziell).
- `pipeline_stages` deckt die Implementierungs-Stage ab (`implement: 1`).
- Widerspruchsfreiheit geprüft: E5 (Upsert) vs. „append-only" — die Spec nennt Append-only nur noch
  als **verworfene** Alternative (§6.1/§9/E4); E6 (Workspace-Takt) vs. „25 Scopes/Lauf" — der Deckel
  ist ausdrücklich **global** (§6.4/§9/E6); E10 (Sprache) vs. „Sprache des Inhalts" — die
  Inhalts-Sprache ist nur noch Default (§7.6), `Workspace.language` steuert weiter die Oberfläche.

## 14. Offene Punkte (aus der Spec übernommen)

- **O8 — Tool-Zahl 295 vs. 296** (blockiert S6-Step 6, nicht S1–S5).
- **O1 — Inspector-B2-Kollision** (betrifft S2/S8, additiv gelöst).
- **O2 — Cache-Hit-Rate** sinkt mit nutzerabhängigen Schlüsseln (akzeptiert).
- **O6 — Kontextfenster** bei Tiefe 2 (Kappen sind konservativ, Test deckt die Grenze).
- **O9 — Sprach-Umstellung** verändert Prompts; Anker ist das leere `ai_language`.
- **O10 — `summary_scopes`** muss ein Test gegen `artifact_indexer.SOURCES` absichern.
