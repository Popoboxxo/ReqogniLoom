# Artefakt-Inspector — Neukonzept: Umsetzungsplan (B2.1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die freigegebene Inspector-Spec (§1–§8) in fünf Vorarbeiten plus acht einzeln rückrollbare PRs umsetzen: zuerst die Vorarbeiten (D5-Id-Space, D6-Baseline-Endpunkt, Testgerüst), dann die Shell als Reiter-Panel mit Rail und Sheet (M1, Route Requirements), dann sechs Typ-Migrationen und ein Aufräum-PR. Am Ende liest **jede** Artefakt-Route den Inspector aus **einem** Bauteil, jede Information hat genau einen Ort, und die drei Messlatten M-1/M-2/M-3 aus Spec §1.1 sind erreicht.

**Architecture:** Die Shell wird **neu gebaut** (`InspectorShell` + Rail + Sheet + zwei Live-Regionen), nicht umgebaut: `RightSidebar` bleibt bis M8 importierbar, wird aber ab M1 von keiner migrierten Route mehr verwendet (Spec §8.2). Rail und Sheet sind **ein** DOM-Knoten in zwei Zuständen (Spec §2.1/§4.2). Der Typ-Unterschied ist nicht „Diff ja/nein" (alle 12 Kinds sind diff-fähig, `frontend/src/components/shared/ArtifactInspector/types.ts:128-144`), sondern **Spine ja/nein** und **Link-Zeilen ja/nein** (Spec §3) — die Shell leitet beides aus `kind` ab. Die Migration ist pro Route ein Austausch des Mount-Punkts, kein Feature-Flag (Spec §8.2).

**Tech Stack:** React 19, TypeScript 5.5 (strict), Vite 8, Vitest 5, Testing Library, Playwright (nur über den `e2e-tester` mit den erlaubten MCP-Tools), Django 6.1 + DRF + drf-spectacular (nur für B2.0-1/B2.0-4), pytest 9, CSS Custom Properties aus `frontend/src/styles/tokens.css`.

**Spec:** `docs/superpowers/specs/2026-11-10-inspector-redesign-design.md` — **freigegeben 2026-11-12**. D1–D8 sind alle mit **Option A** angenommen, inklusive der B1-Konsequenz (Sheet non-modal + `inert` auf dem verdeckten Detailbereich, Spec §11 D3, §14 B1). D5 und D6 haben Backend-Anteile und laufen darum als Vorarbeiten B2.0, nicht in M1.

**Auftrag:** Task 6 Step 3 aus [`2026-11-10-phase-b2-inspector-concept.md`](2026-11-10-phase-b2-inspector-concept.md).

**Branch-Basis:** `origin/main` @ `19d78395`, Arbeitskopie `.tmp/wt-phase-b1`, Branch `docs/inspector-implementation-plan`. Umsetzung: je Schritt ein eigener `feat(inspector)`-/`refactor(inspector)`-Branch von `origin/main`.

---

## 1. Ausgangslage

### 1.1 Was die Freigabe entscheidet

| D | Entscheidung (Option A) | Folge für diesen Plan |
|---|---|---|
| **D1** | Liste 320 px · Inhalt 508 px · Panel 320 px; Inspector ab 1440 px standardmäßig **offen**; 508 px sind 12 px unter `--detail-min` (Spec §4.4) | M1-4 (Layout-Hook, Splitter, Breiten). 508-px-Prüfung bleibt **offener visueller Punkt** (§4.4, M1-DoD 10) |
| **D2** | Reiter „Links" zeigt für Ableitungs-/Verifikationstypen **nur** eine Zusammenfassungszeile + Sprung in die Spine; Zeilen nur für die übrigen Typen (Spec §2.3) | M1-6, M1-9; Typ-Matrix als reine `kind`-Logik |
| **D3 + B1** | Ein Bauteil, drei Formen (Panel/Rail/Sheet); Sheet **non-modal**, überdeckter Detailbereich `inert`, kein Trap im Sheet (Spec §4.2, §7 SC 2.4.11) | M1-5 (`inert`), M1-3 (Rail), M1-4 (R1–R5) |
| **D4** | Vier Reiter, genau ein Bereich sichtbar (Spec §2.1) | M1-2 (Tablist, manuelle Aktivierung) |
| **D5** | Shell bekommt **zwei** IDs: `entityId` (Version/Diff/Trace) und `artifactPk` (Kommentare); Routen reichen `artifact_id` durch (Spec §11 D5) | **B2.0-2/3/4**, M1-7 (Kommentar-Reiter) |
| **D6** | Neuer Lese-Endpunkt `GET /api/v1/artifacts/<pk>/baselines/` → `[{id, name, scope, pinned_version}]`, tenant-/RLS-gesichert (Spec §11 D6, N-01) | **B2.0-1**, M1-8 (Paar-Zeile + Basiswechsel) |
| **D7** | „Anheften" wird **entfernt** (Spec §11 D7) | M8-5 |
| **D8** | Glossary bekommt die rechte Spalte wie alle Typen; „Verwendungen" entfällt als eigener Block (Spec §11 D8) | M5 |

Der Review-Fokus des Vorplans (Scheinproblem, Typ-Unterschiede, schmale Fenster, Tastatur, Doppelanzeige) ist in der Spec beantwortet; dieser Plan setzt **nur** die freigegebene Fassung um. Kein Punkt aus §11 wird hier neu verhandelt.

### 1.2 Was bereits existiert

| Bauteil | Pfad (verifiziert) | Zustand | Konsequenz |
|---|---|---|---|
| Shell | `frontend/src/components/shared/ArtifactInspector/RightSidebar.tsx` | vier **gestapelte** Panels in einer Scrollbox; `hideTraceLinks` als Routen-Schalter (`:45-57`, `:458`); Default eingeklappt unter 1600 px (`:87`); Breiten 280/360/520 (`:63-65`) | ab M1 von migrierten Routen ungenutzt, Datei fällt in M8 |
| Panels | `VersionPanel`, `DiffPanel`, `TracePanel`, `CommentPanel` (gleicher Ordner) | je eigene Live-Region, je eigener Fehlerzustand | bekommen in M1 `variant="tab"` (eigene Ansage unterdrückt, Bereichsüberschrift entfällt); alte Form bleibt für nicht migrierte Routen bis M8 |
| Barrel | `frontend/src/components/shared/ArtifactInspector/index.ts:13-35` | exportiert Shell + vier Panels + Typen | M1 ergänzt `InspectorShell`; M8 entfernt die Alt-Exporte |
| Spine | `frontend/src/components/shared/TraceSpine/TraceSpine.tsx`, `useDerivationChain.ts` | Verifikations-Badge nur bei Requirement/Architecture (Spec §2.3, U-07) | M1-9: Badge an **jeder** Station mit Daten (`useDerivationChain.ts:378-395`) |
| Spine-Slot | `frontend/src/components/SplitView/SplitView.tsx:109-111` (Prop), `:332` (Weitergabe) | Slot existiert, **kein** Konsument (Spec §0.1 I-13) | M1-4 setzt die Requirements-Spine hinein |
| SplitView-Aufruf Requirements | `frontend/src/components/RequirementEditors/RequirementEditors.tsx:818-824` | nutzt den **Legacy-Vertrag** (`leftPanel`/`rightPanel`); der Konzept-Pfad wird nur bei gesetztem `list` gewählt (`SplitView.tsx:316-338`) | der `spine`-Slot ist dort heute **unerreichbar** — M1-4 stellt auf `list`/`detail`/`spine` um, sonst bleibt I-13 offen |
| Spine heute | `RequirementEditors.tsx:642-648` | liegt **im** scrollenden Detailbereich | M1-4 verschiebt sie in den Slot |
| Kommentare | `CommentPanel.tsx:20-25` („generic Artifact id, not the business-entity id"), `frontend/src/api/comments.ts:60,68` | erwartet die Artefakt-PK | D5-Vorarbeit (B2.0-2/3/4) |
| Baselines | `frontend/src/api/baselines.ts:258-266` | nur `workspace_id` + `tag`; kein `artifact_id`-Filter (Spec §0.2 N-01) | B2.0-1 |
| Baseline-Serializer | `backend/rest_api/serializers.py:2178-2218` | `version` = **Lock-Version** (`:2210-2212`), `entries` fehlen bewusst | `pinned_version` muss aus den Einträgen kommen, nicht aus `version` |
| Ratchet | `frontend/src/test/ui-ratchet.test.ts`, `frontend/src/test/design-system-ratchet.test.ts` + `design-system-ratchet.baseline.json` | Exemptions `:89` (RightSidebar-Resize) und `:116` (`.skeletonChip`) | M1 entfernt `:116`, M8 entfernt `:89` (Details in M1/M8, „Ratchet"-Block) |

### 1.3 Messlage

Die Spec erbt die Messlage von Task 2/3 und erfindet keine Messwerte (Spec §0). Für diesen Plan heißt das:

| Aussage | Grundlage | Belastbarkeit | Folge für den Plan |
|---|---|---|---|
| Klick-/Scroll-Zahlen im Ist | Code-Pfad, Usability §3 | **Untergrenze** | Zielwerte M-1…M-3 sind Soll-Grenzen, keine gemessene Verbesserung |
| Bildschirmfotos | **keine** — am 2026-11-11 lief kein Stack (Spec §0) | nicht vorhanden | DoD 10 ist ein **Nachweis**, keine Checkbox: ohne Stack bleibt er offen |
| 768/1024/1440/320 px | CSS/JS-Arithmetik, Spec §4.4 nachgerechnet | **abgeleitet, nicht gerendert** | M1 und M8 tragen je eine visuelle Prüfaufgabe; 508 px ist der kritischste Punkt |
| Kontrast der **neuen** Paare | Token-Paare + `theme-contrast.test.ts` | Token-Ebene geprüft, Inspector-Paare erst nach Umsetzung | Messung nach M1, nicht vorher (Spec §7 „Was diese Spec nicht verspricht") |

**Regel für alle PRs:** Ein Beleg ist ein Test, ein `grep`-Ergebnis mit Zahl oder ein HTTP-Status. „Sieht gut aus" ist kein Beleg.

### 1.4 Global Constraints

- Branch von `origin/main`, nie lokales `main`. Git-Mutationen ausschließlich über den `git`-Agenten. Ein Schritt = ein PR.
- Vor jedem Commit: Secret-Scan (Paved Road `secret-scanning`); ein Fund blockiert den Commit.
- Commits: Conventional Commits, Englisch, ≤ 72 Zeichen erste Zeile.
- Jeder PR: `cd frontend && npm run typecheck`, `npx eslint <geänderte Dateien>` (Skript-Äquivalent: `npm run lint`), gezielte Vitest-Suiten, danach der volle Lauf (`npm test`), CI grün.
- Ratchet-Konstanten werden **nur gesenkt**, nie erhöht (`ui-ratchet.test.ts:16-22` laut Spec §8.3). Jede Exemption, deren Ziel im PR verschwindet, wird **im selben PR** gelöscht.
- Kein `style={{ … }}`-Objektliteral, kein Hex in `.tsx`/neuem CSS, kein Emoji als UI-Glyph, keine Literal-Geometrie, keine Schriftgröße unter `--font-size-xs` (Spec §6.1, §6.4).
- Keine neuen Design-Tokens; nur Komponenten-Aliase, **im selben CSS-Modul** deklariert (Spec §6.1, `frontend/src/test/design-tokens.test.ts:168-207`).
- Alle neuen Texte i18n DE **und** EN unter `sidebar.inspector.*`, Platzhalter `{{panel}}` (Spec §5.5). Kein neuer Schlüssel `inspector.*` (Kollision mit `diagram.inspector`, `workflow.inspector`).
- Barrierefreiheit: WCAG 2.2 AA als **Untergrenze**; jeder interaktive Treffer ≥ `--btn-h-xs` (Spec §7 SC 2.5.8, als Zusage — es gibt **kein** generelles Gate).
- Keine Verhaltensänderung an Formularen, Listen, Navigation, Rechten, Export.
- Volle Testläufe nur sequentiell (Host-RAM).

---

## 2. Vorarbeiten B2.0

Diese fünf Tasks laufen **vor M1**. B2.0-1 und B2.0-2 sind blockierend (D6/D5); B2.0-3/4 sind „prüfen → entscheiden" mit dokumentiertem Ergebnis; B2.0-5 ist das Test-Gerüst, auf dem M1–M8 aufsetzen.

### B2.0-1 — D6: Lese-Endpunkt `GET /api/v1/artifacts/<pk>/baselines/`

**Files:**
- Read/Prüfen: `backend/baseline/models.py`, `backend/baseline/state_capture.py`, `backend/baseline/services.py`
- Modify: `backend/application/baseline_facade.py` (neue Methode `list_baselines_for_artifact`)
- Modify: `backend/rest_api/serializers.py` (neuer `ArtifactBaselinePinSerializer`)
- Create: `backend/rest_api/artifact_baseline_views.py` (`ArtifactBaselinesView`, Muster: `collaboration_views.py:53-97`)
- Modify: `backend/rest_api/urls.py` (Route **vor** `path("", include(router.urls))`, Muster Kommentarroute `:1274-1281`)
- Create: `backend/rest_api/tests/test_artifact_baselines_rest.py`
- Modify: `frontend/src/api/baselines.ts` (+ Typ `ArtifactBaselinePin`, Methode `listForArtifact`)

**Interfaces:**
- Produces: `GET /api/v1/artifacts/{artifact_id}/baselines/` → `200 [{id, name, scope, pinned_version}]`, `404` bei unbekanntem Artefakt/fremdem Tenant/inaktivem `baselines`-Preset.
- Produces (Frontend): `baselinesApi.listForArtifact(artifactPk: UUID): Promise<ArtifactBaselinePin[]>`.
- Consumes: `BaselineFacade` (Tenant-Kontext, `baseline_facade.py:902-956`), `BaselineViewSet`-Preset-Gate als Vorbild (`views.py:5890-5906`, `preset_endpoint_key` `:5900`).

| # | Task | Akzeptanzkriterium |
|---|---|---|
| B2.0-1.1 | Eintrags-/Index-Tabelle prüfen: gibt es ein ORM-Filterziel auf `item_id` (nicht nur die Detail-Antwort)? | Befund im PR-Text: entweder „Filter auf `<Tabelle>.<Feld>` möglich" oder „kein Index, Begründung + Deckel N" — **kein** stiller Client-Filter (Spec §11 D6 Option C ist abgelehnt) |
| B2.0-1.2 | `BaselineFacade.list_baselines_for_artifact(artifact_id, ctx)` mit `_set_tenant_context(ctx)` | Fremder Tenant → `NotFoundError`; Test `test_foreign_tenant_is_404` grün |
| B2.0-1.3 | `pinned_version` aus dem **Eintrag** (`item_id == artifact_id`), nie aus `BaselineSummary.version` | Test: Baseline mit Lock-Version 7 und gepinnter Version 3 liefert `pinned_version == 3` |
| B2.0-1.4 | Serializer + View + Route (`<uuid:artifact_id>`, Name `api-v1-artifact-baselines`), `GET` only | `GET` 200, `POST` 405; Route löst vor der Router-Registrierung auf |
| B2.0-1.5 | Preset-Gate: unter `minimal` **404** | Test `test_minimal_preset_is_404` grün |
| B2.0-1.6 | OpenAPI: `@extend_schema(responses={200: ArtifactBaselinePinSerializer(many=True), 404: …})` | Schema-Test erweitert; die Operation erscheint mit 200-Shape (Lehre aus #1388) |
| B2.0-1.7 | Fünf Vertragsfälle | Artefakt in 2 Baselines (document+project) → 2 Zeilen · in keiner → `[]` · unbekannte UUID → 404 · fremder Tenant → 404 · Sortierung stabil (`created_at` absteigend) |
| B2.0-1.8 | Frontend-Wrapper `listForArtifact` + Typ | `frontend/src/api/baselines.ts` typecheckt; Test mockt `/artifacts/<pk>/baselines/` |

**Tests:** `pytest backend/rest_api/tests/test_artifact_baselines_rest.py -q` grün; bestehende `test_baseline_*`-Suiten unverändert grün (der neue Endpunkt ist additiv). **Ratchet:** keiner (Backend + API-Wrapper). **Rückfall:** Endpunkt entfernen; kein Consumer außer M1.

### B2.0-2 — D5: `artifact_id` an die Shell durchreichen (7 Typen)

**Files:**
- Modify: `RequirementEditors.tsx` (`:746-753`), `NeedsEditors.tsx` (`:473-478`), `RiskEditors.tsx` (`:235`), `AdrEditors.tsx` (`:308`), `IssueEditors.tsx` (`:237`), `TestCaseEditors.tsx` (`:400`), `ArchitectureEditors.tsx` (`:813-818`)
- Modify: `RightSidebar.tsx` — optionales `artifactPk?: string | null`, an `CommentPanel` durchgereicht, Fallback `artifactId` (die Datei bleibt bis M8 importierbar; der Prop verschwindet mit ihr)
- Modify (nur falls B2.0-2.1 eine Lücke zeigt): `backend/rest_api/serializers.py` + `backend/rest_api/views.py` (`_*_to_dict`)

**Interfaces:**
- Produces: `artifactPk: string | null` an jeder Route; **nie** `entityId` als Kommentar-ID.
- Consumes: bestehende `artifactId`-Props (Entity-ID) bleiben unverändert für Version/Diff/Spine.

**Befund, der die Task prägt (verifiziert am Code):** Die Spec nennt sieben Aufrufstellen, an denen `artifact_id` „vorhanden" ist. Das ist **typ-, nicht datenseitig** wahr:

- `RiskEditors.tsx:119-124` und `AdrEditors.tsx:149-154` verwenden `item?.artifact_id ?? item?.id` — der Fallback auf die Entity-ID ist im Code sichtbar.
- `types/artifact.ts:49,124,177` deklariert `artifact_id?` für Adr/Risk/Issue mit dem Kommentar „currently always undefined" (Serializer emittiert es nicht).
- Dagegen **belegt vorhanden**: Requirement (`serializers.py:1323-1330`), Goal (`:3073`), Glossary (`global_uuid`, `:3543-3548`), ICD (`icd_views.py:133,166`), Diagram (`types/diagram.ts:131-132`).

| # | Task | Akzeptanzkriterium |
|---|---|---|
| B2.0-2.1 | Ist-Erhebung mit Beleg je Typ: Feld im **Serializer** deklariert (nicht nur im TS-Typ)? | Tabelle „Typ → Serializer-Zeile → ja/nein" im PR; ADR/Risk/Issue explizit geprüft |
| B2.0-2.2 | Fehlt das Feld im Payload → Backend-Nachzug (`artifact_id` read-only im Serializer **und** im `_*_to_dict`) | Backend-Test: Antwort enthält `artifact_id` == Backing-Artefakt; Frontend-Typ-Kommentar „always undefined" entfernt |
| B2.0-2.3 | Jede der sieben Routen übergibt `artifactPk` explizit (kein `??`); die alte Shell reicht ihn an `CommentPanel` durch (Fallback `artifactId`, damit nicht migrierte Routen unverändert laufen) | Route-Test je Typ: `commentsApi.list` wird mit `<artifact_id>` aufgerufen, **nicht** mit `<entity id>`; `RightSidebar.test.tsx` bleibt grün |
| B2.0-2.4 | Fehlt `artifact_id` zur Laufzeit, ist `artifactPk = null` | Die neue Shell (M1) rendert den Kommentar-Reiter dann **nicht** (kein Fehlerbanner, Spec §4.3) — Test in M1-7 |
| B2.0-2.5 | Neuer Befund dokumentieren: die Spine-Aufrufe (`RiskEditors.tsx:120`, `AdrEditors.tsx:150`) fallen ebenfalls auf die Entity-ID zurück | Eigenes Ticket via `feedback`; **nicht** in diesem Plan mitgelöst (sonst Scope-Creep) |

**Tests:** die sieben Editor-Suiten (`RiskEditors.test.tsx`, `AdrEditors.test.tsx`, `IssueEditors.test.tsx`, `TestCaseEditors.test.tsx`, `NeedsEditors.test.tsx`, `RequirementEditors.test.tsx`, `ArchitectureEditors.test.tsx`) um je eine URL-Assertion erweitert. **Ratchet:** keiner.

### B2.0-3 — D5: `glossary`, `icd`, `diagram`, `goal` — prüfen → entscheiden

**Files:**
- Modify: `frontend/src/api/icds.ts` (`Icd`/`IcdDetail`, `:43-51`)
- Modify: ggf. `frontend/src/types/diagram.ts`, `frontend/src/types/glossary.ts` (nur wenn ein Feld fehlt)
- Create: nichts — Entscheidung + Beleg stehen im PR-Text

**Interfaces:** Produces: je Kind eine dokumentierte Quelle für `artifactPk`.

| Kind | Quelle (verifiziert) | Erwartetes Ergebnis | Restarbeit |
|---|---|---|---|
| `glossary` | `GlossaryTerm.global_uuid` (`types/glossary.ts:37-42`, „== backing Artifact id"), Backend `serializers.py:3543-3548` | **nutzbar ohne Backend-Änderung** | `artifactPk = term.global_uuid ?? null` |
| `icd` | Backend liefert `artifact_id` (`icd_views.py:133,166`), TS-Typ `Icd` hat es **nicht** (`api/icds.ts:43-51`) | Backend ✓ / Typ ✗ | `artifact_id?: UUID \| null` an `Icd` ergänzen |
| `diagram` | `types/diagram.ts:126-132` (`artifact_id`, `global_uuid`, beide nullable) | **nutzbar** | `artifactPk = d.artifact_id ?? d.global_uuid ?? null` (Legacy-Diagramm ohne Artefakt → `null`) |
| `goal` | `GoalSerializer.artifact_id` (`serializers.py:3073`), TS `types/artifact.ts:73` | **nutzbar** | nur Verdrahtung in M4; heute übergibt `GoalsPage.tsx:344` `selectedGoal.id` |

| # | Task | Akzeptanzkriterium |
|---|---|---|
| B2.0-3.1 | Jede Zeile der Tabelle am Code bestätigen (oder widerlegen) und im PR festhalten | Vier Zeilen mit `datei:zeile`; keine Zeile ohne Beleg |
| B2.0-3.2 | `icd`-Typ ergänzen | `npm run typecheck` grün; `IcdDetailPane` kann `icd.artifact_id` lesen |
| B2.0-3.3 | Für `null`-Fälle den sichtbaren Zustand festlegen | Kein Kommentar-Reiter (nicht: leerer Reiter, nicht: Fehlerbanner) |
| B2.0-3.4 | Entscheidung gegen die Alternative begründen | PR-Text nennt, warum kein neues `artifact_id`-Feld für Glossary (ein Wert, zwei Namen: `global_uuid` ist der dokumentierte) |

### B2.0-4 — D5: `mainGoal` — Typ-/Backend-Erweiterung

**Files:**
- Modify: `backend/rest_api/serializers.py` (`MainGoalSerializer`, `:3085`) — `artifact_id = serializers.UUIDField(read_only=True)`
- Modify: `backend/rest_api/views.py` (`_main_goal_to_dict`, `:8017-8038`) — `"artifact_id": str(main_goal.artifact_id)`
- Modify: `frontend/src/types/artifact.ts` (`MainGoal`, `:89-106`)
- Create/Modify: `backend/rest_api/tests/test_main_goal_artifact_id.py`

**Interfaces:** Produces: `MainGoal.artifact_id` im Wire-Format und im TS-Typ → Kommentar-Reiter für `mainGoal` möglich, **Links**-Reiter bleibt aus (Spec §3).

**Beleg:** `MainGoal.artifact` ist ein `OneToOneField` auf `Artifact` (`backend/persistence/models.py:3828-3832`); `trace_link_service.py:293` nutzt `MainGoal.artifact_id` bereits. Die Lücke ist ausschließlich der Serializer-DTO — nicht das Datenmodell. Damit ist die Spec-Aussage „kein `artifact_id`" (Spec §3, `GoalsPage.tsx:26-32`) als **Frontend-/Serializer-Lücke** präzisiert.

| # | Task | Akzeptanzkriterium |
|---|---|---|
| B2.0-4.1 | Serializer-Feld + DTO-Schlüssel ergänzen | `GET /main-goals/current/` enthält `artifact_id` == `Artifact.id` |
| B2.0-4.2 | TS-Typ ergänzen | `MainGoal.artifact_id?: UUID`; typecheck grün |
| B2.0-4.3 | Regressionstest | Alter Wert bleibt: `artifact_id` ist read-only (ein PATCH damit → 400/ignoriert, kein Schreibpfad) |
| B2.0-4.4 | Ausschluss dokumentieren, falls die Erweiterung verworfen wird | Dann Kommentar-Reiter für `mainGoal` **nicht** gerendert + Begründung im PR; M4-DoD 3 wird zur dokumentierten Ausnahme |

### B2.0-5 — Test-Gerüst und `data-testid`-Inventar

**Files:**
- Create: `frontend/src/components/shared/ArtifactInspector/InspectorShell.a11y.test.tsx` (Muster: `RightSidebar.a11y.test.tsx:1-14,69-78`)
- Create: `frontend/src/components/shared/ArtifactInspector/inspectorContract.test.ts` (IDs, Keys, Storage-Keys, keine Duplikate)
- Read: `frontend/src/test/interactive-hit-targets.test.ts` (welche vier Controls gepinnt sind — **kein** generelles 24-px-Gate)

**Interfaces:**
- Produces: `data-testid`-Inventar aus Spec §8.4 Punkt 7: `inspector-tab-<key>`, `inspector-panel-<key>`, `inspector-rail`, `inspector-rail-open`, `inspector-rail-count-<key>`, `inspector-close`, `inspector-live`, `inspector-alert`, `inspector-diff-pair`, `inspector-baseline-select`.
- Produces: a11y-Muster „jeder Button hat einen Namen" als wiederverwendbare Assertion über alle gerenderten Buttons.

| # | Task | Akzeptanzkriterium |
|---|---|---|
| B2.0-5.1 | Muster übertragen: für jeden gerenderten `button` gilt `toHaveAccessibleName()` ohne Argument | Test läuft gegen die alte Shell grün (beweist, dass das Muster trägt) und wird in M1 auf `InspectorShell` geklont |
| B2.0-5.2 | Inventar-Test: jedes der 10 Testids ist im Vertragsmodul als Konstante definiert | Test schlägt fehl, wenn eine ID doppelt oder ohne `<key>`-Template existiert |
| B2.0-5.3 | Id-Vertrag aus Spec §7 als Test-Form zuschneiden (`inspector-tab-<key>` ↔ `inspector-panel-<key>`, `aria-controls`/`aria-labelledby` lösen auf) | Test ist zunächst `skip` mit Verweis auf M1-1; in M1 aktiviert |
| B2.0-5.4 | Hit-Target-Ausgangslage notieren | PR-Text: `interactive-hit-targets.test.ts` pinnt vier Referenz-Controls + Token-Skala; neue Inspector-Controls sind **nicht** abgedeckt (Spec §6.4) |

**Tests:** `npx vitest run src/components/shared/ArtifactInspector/InspectorShell.a11y.test.tsx src/components/shared/ArtifactInspector/inspectorContract.test.ts`. **Ratchet:** keiner.

---

## 3. Migrationsschritte M1–M8

Reihenfolge und Begründung sind aus Spec §8.1 übernommen: erst der komplexeste Typ (Requirements: Spine + SplitView + Provenienz + `artifact_id`), damit ein Musterfehler früh auffällt; `mainGoal` vor `glossary`, weil `mainGoal` der einzige Typ ohne Spine **und** ohne Links ist und damit die Typ-Matrix beweist.

### Gemeinsamer Vertrag (in M1 definiert, danach nur konsumiert)

```ts
// frontend/src/components/shared/ArtifactInspector/inspectorContract.ts
export type InspectorTabKey = "version" | "diff" | "links" | "comments";

export interface InspectorShellProps {
  kind: ArtifactKind;              // 12 Werte, types.ts:21-33
  entityId: string;                // Version/Diff/Trace (Business-Entity)
  artifactPk: string | null;       // Kommentare (D5) — null ⇒ kein Kommentar-Reiter
  currentVersion?: VersionRef;
  /** Nur für Deep-Links/Tests; sonst aus Storage/URL. */
  initialTab?: InspectorTabKey;
}

/** Typ-Matrix, Spec §3. Reine kind-Logik — kein Prop, kein Schalter (Spec §8.2). */
export const HAS_SPINE: ReadonlySet<ArtifactKind>;      // alle außer mainGoal, glossary, icd, diagram
export const HAS_LINKS_TAB: ReadonlySet<ArtifactKind>;  // alle außer mainGoal
export const LINKS_ROWS_ONLY: ReadonlySet<ArtifactKind>; // glossary, icd, diagram (ohne Spine ⇒ alle Typen als Zeilen)
```

Tab-Keys: `version` · `diff` · `links` · `comments`; IDs `inspector-tab-<key>` / `inspector-panel-<key>` (Spec §7 Id-Vertrag). Storage: `reqflow_inspector_tab_<kind>_<id>` (Spec §5.4) — Ausnahme Goals-Route: **ein** Slot `reqflow_inspector_tab_goals` für `goal` und `mainGoal` (behebt I-14). URL: `?inspector=<key>`.

---

### M1 — Shell umbauen + Route Requirements

**PR:** `feat(inspector): rebuild shell as tabbed panel with rail, sheet and inert (M1)`

**Dateien:**
- Neu: `frontend/src/components/shared/ArtifactInspector/inspectorContract.ts`
- Neu: `.../InspectorShell.tsx` · `InspectorRail.tsx` · `InspectorTabs.tsx` · `InspectorSheet.tsx` · `InspectorLiveRegions.tsx` · `useInspectorLayout.ts` · `useInertBehindSheet.ts`
- Neu: `.../tabs/VersionTab.tsx` · `DiffTab.tsx` · `LinksTab.tsx` · `CommentsTab.tsx`
- Neu: `.../InspectorShell.module.css` (Komponenten-Aliase lokal, Spec §6.1)
- Geändert: `.../index.ts` (Export `InspectorShell`) · `.../VersionPanel.tsx`, `DiffPanel.tsx`, `TracePanel.tsx`, `CommentPanel.tsx` (Prop `variant?: "panel" | "tab"`)
- Geändert: `frontend/src/components/shared/TraceSpine/TraceSpine.tsx` (Badge an allen Stationen)
- Geändert: `frontend/src/components/SplitView/SplitView.tsx` (nur falls die Konzept-Breiten 320/508 einen Prop brauchen — `minWidths` existiert, `:121-122`)
- Geändert: `RequirementEditors.tsx` (Mount ersetzt, Legacy-`SplitView` → `list`/`detail`/`spine`, `hideTraceLinks` gelöscht)
- Geändert: `frontend/src/i18n/locales/de.json`, `en.json` (Spec §5.5)
- Neu (Tests): `InspectorShell.test.tsx` · `InspectorShell.a11y.test.tsx` · `InspectorTabs.keyboard.test.tsx` · `InspectorSheet.inert.test.tsx` · `InspectorLiveRegions.test.tsx` · `DiffTab.baselinePair.test.tsx`

**Interfaces:**
- Produces: `InspectorShell` (Props s. o.), `useInspectorLayout()` → `{ region: "R1"…"R5", form: "panel" | "rail" | "sheet" | "fullscreen", widthPx, setWidthPx }`, `useInertBehindSheet(ref, open)`.
- Produces: `variant="tab"` an den vier Panels (unterdrückt Panel-eigene Live-Region und Bereichs-`h3`).
- Consumes: B2.0-1 (`baselinesApi.listForArtifact`), B2.0-2 (`artifactPk`), B2.0-4 (nur für M4), B2.0-5 (Testgerüst).

| # | Task | Akzeptanzkriterium |
|---|---|---|
| M1-1 | Vertragsmodul: Tab-Keys, Testids, Storage-Keys, Typ-Matrix, `DEFAULTS` für Breiten | `inspectorContract.test.ts` grün; `HAS_LINKS_TAB` enthält `mainGoal` **nicht**; `LINKS_ROWS_ONLY` == {glossary, icd, diagram} |
| M1-2 | Tablist mit **manueller Aktivierung** (←/→/Home/End = Fokus, Enter/Space = aktivieren); `aria-selected`, `tabindex` 0/−1 | Tastatur-Test: 4× Pfeil löst **0** Fetches, 1× Enter löst **genau 1** Fetch aus; Fokus bleibt auf dem Reiter (Spec §5.1/§5.2, S2) |
| M1-3 | Rail: 40 px, jeder Zähler ein `<button>` mit lokalisiertem `aria-label` + `aria-controls`, Kürzel `aria-hidden`; Klick öffnet Panel/Sheet **auf dem Reiter** | Test: 4 Zähler-Buttons, jeder mit nicht-leerem Namen; `V/D/L/K` sind nicht im Accessible Name; `data-testid="inspector-rail-count-<key>"` |
| M1-4 | Layout-Hook R1–R5 + Splitter (`role="separator"`, `tabindex="0"`, „Stufe 5" **vor** der Kopfzeile) + Breiten-Persistenz + `?inspector=` | Test je Region: ≥1600 → Panel 360 offen · 1440–1599 → Panel 320 offen · 1280–1439 → Sheet offen · 1024–1279 → Rail · 768–1023 → Rail · <768 → Rail, Sheet = 100 %; Splitter-Pfeile ±16 px, `Home`/`End` = min/max |
| M1-5 | Sheet + `inert`: `inert` auf dem überdeckten Detailbereich (`<main>` samt Spine), kein Trap im Sheet, Entfernen **in derselben Transaktion** wie das Unmount | Test: offen ⇒ `<main>` hat `inert`, Liste **nicht**; geschlossen ⇒ Attribut weg; `Esc`/Schließen gibt Fokus an den Auslöser (Fallback: Rail-Button → Kopfzeilen-Container) |
| M1-6 | Zwei Live-Regionen (`polite` + `role="alert"`) am Ende des Inspectors; Regel „genau eine Ansage je Interaktion", `xxxLoaded` unterdrückt `tabChanged` im selben Task | Test mit Announce-Spy: Reiterwechsel ⇒ genau **eine** Ansage; Retry ⇒ `retrySucceeded` **ohne** `versionLoaded`; Fehler ⇒ genau **eine** alert-Ansage je Ereignis |
| M1-7 | Kommentar-Reiter nutzt `artifactPk`; `artifactPk === null` ⇒ Reiter **nicht gerendert** | Test: mit `artifactPk` genau 1 `GET /artifacts/<pk>/comments/` (200); ohne ⇒ kein Reiter, keine Anfrage, kein Fehlerbanner |
| M1-8 | Diff-Reiter: **eine** Paar-Zeile („Basis … → Arbeitsstand vN") + Basiswechsel aus D6; Version→Version ohne Baseline bleibt möglich | Test: 1 Klick auf „Diff" zeigt die Paar-Zeile; Basiswechsel aktualisiert Paar-Zeile **ohne** Navigation (`location.pathname` unverändert); `data-testid="inspector-diff-pair"`, `"inspector-baseline-select"` |
| M1-9 | Links-Reiter: Zusammenfassungszeile („n Ableitungs- und Verifikationslinks — in der Spine") + Sprung; Zeilen nur für die übrigen Typen. Zusätzlich: Verifikations-Badge an **jeder** Station | Test: Requirement ⇒ 0 Zeilen für `derives-from`/`verifies`, 1 Zusammenfassungszeile, Sprung fokussiert die Spine; Badge erscheint bei jeder Station mit nicht-leerer Verifikationsliste |
| M1-10 | Skip-Link als **erstes** fokussierbares Element im Detailbereich → `#inspector-heading`; ein `h2` für Detail und Inspector (Geschwister), Bereichs-`h3`; `<aside aria-labelledby>` **ohne** `role="complementary"` | Test: erster Tab im Detailbereich landet auf dem Skip-Link; `aria-labelledby` löst auf; kein `role="complementary"` im DOM; keine `h4`/`h5` im Inspector |
| M1-11 | Requirements-Route migrieren: `SplitView` auf `list`/`detail`/`spine` umstellen, Spine in den Slot, `InspectorShell` als Mount, `hideTraceLinks` an der Aufrufstelle löschen | `RequirementEditors.tsx` enthält kein `hideTraceLinks` und kein `leftPanel=`; `SplitView`-Konzeptpfad aktiv (`list` gesetzt); Spine scrollt nicht mehr mit dem Formular |
| M1-12 | i18n: alle neuen Schlüssel DE+EN unter `sidebar.inspector.*` (`tab.links`, `railCount`, `count.open`, `action.showInSpine`, `empty.linksOther`, `empty.linksAll`, `partial.noSnapshot`, `composer.submitting`, 15 `live.*` aus Spec §5.3 + `error.{{panel}}`), DE-Umlaute korrekt | `i18n-parity.test.ts` grün; beide Locale-Dateien enthalten dieselben Schlüssel; kein Schlüssel `inspector.` neu angelegt |

**Tests — bleiben unverändert grün:**
`RightSidebar.test.tsx`, `RightSidebar.a11y.test.tsx` (Shell wird noch direkt gerendert), `VersionPanel.test.tsx`, `VersionPanel.i18n.test.tsx`, `DiffPanel.test.tsx`, `TracePanel.test.tsx`, `CommentPanel.test.tsx`, `SplitView.test.tsx`, `SplitView.a11y.test.tsx`, `ui-ratchet.test.ts`, `design-system-ratchet.test.ts`, `design-tokens.test.ts`, `theme-contrast.test.ts`, `interactive-hit-targets.test.ts`, `action-labels.test.ts`, `sidebar-theme-agnostic-overlays.test.ts`, `i18n-parity.test.ts`.

**Tests — im selben PR angepasst (und im PR-Text benannt):**
`RequirementEditors.test.tsx`, `RequirementEditors.unsaved-changes.test.tsx` (Mount-Assertions: `InspectorShell` statt `RightSidebar`, Spine im Slot), `useDerivationChain.test.tsx` (Badge an allen Stationen).

**Tests — neu:** die sechs oben gelisteten Dateien; Kernzusagen: manuelle Aktivierung (M1-2), `inert`-Klammer (M1-5), Live-Region-Disziplin (M1-6), Id-Vertrag (M1-1/B2.0-5.3), Paar-Zeile (M1-8).

**Ratchet:**
| Konstante | Erwartung in M1 |
|---|---|
| `STYLE_BRACE_BASELINE` (Spec §8.3) | unverändert **3**; neue Shell hat 0 Literale — Breite über benanntes `CSSProperties` oder `element.style.setProperty` (Spec §6.1) |
| `HEX_LITERAL_*` (`.tsx` 17/3, CSS 203/1) | 0 Delta; neue CSS-Module ohne Hex (sonst Dateizahl 2 → rot) |
| `PRIMARY_FILL_BASELINE` (26) | 0 Delta; gewählter Reiter nutzt `.btn-tab` aus `global.css`; Flächen-Fills nur `--color-card-active-bg` |
| `design-system-ratchet.baseline.json:116` (`.skeletonChip`) | **entfernt**: der Chip bekommt `min-height: var(--btn-h-sm)` (Spec §8.3). Bleibt er, ist der Lauf rot |
| `design-system-ratchet.baseline.json:89` | **bleibt** bis M8 (die Datei und damit die Violation existiert weiter); M1 wählt für den neuen Griff Option (a) `btn-icon` → keine neue Exemption |

**DoD (§8.4) — M1:**
- [ ] 1. Mount-Punkt ersetzt, `hideTraceLinks` an der Aufrufstelle gelöscht.
- [ ] 2. Artefaktkopf zeigt ID **und** Status (Requirements: heute zu prüfen und ggf. im Kopf nachziehen — Kopffehler der Route, kein Inspector-Feature).
- [ ] 3. Kommentar-Pfad liefert HTTP 200 (`artifact_id` übergeben, D5).
- [ ] 4. Reiter „Links" vorhanden — außer `mainGoal`; nicht gerendert, nicht deaktiviert.
- [ ] 5. Verifikations-Badge erscheint an jeder Station mit Daten.
- [ ] 6. Kein zweiter Trace-Ort mehr im Detail.
- [ ] 7. `data-testid`-Inventar ergänzt (`inspector-tab-<key>`, `inspector-panel-<key>`, `inspector-rail`, `inspector-rail-open`, `inspector-rail-count-<key>`, `inspector-close`, `inspector-live`, `inspector-alert`, `inspector-diff-pair`, `inspector-baseline-select`).
- [ ] 8. `RightSidebar.a11y.test.tsx`-Muster (jeder Button hat einen Namen) bleibt grün — auf den neuen Reitern.
- [ ] 9. Kein `style={{`, kein Hex, kein Emoji, keine Literal-Geometrie, keine Schriftgröße unter `--font-size-xs`.
- [ ] 10. Visuelle Prüfung 1440 / 1024 / 768 / 320 px **mit laufendem Stack**; 320 px ohne horizontalen Seiten-Scroll. **M1-spezifisch:** 508 px Inhalt bei 1440 px ohne horizontales Scrollen in den Requirement-Formularen (Spec §4.4).
- [ ] 11. Die Inspector-Exemption(s), deren Ziel dieser PR entfernt, sind entfernt (§8.3): hier `:116` (`.skeletonChip`); `:89` folgt in M8, weil `RightSidebar.tsx` bis dahin existiert und die Violation sonst ohne Exemption rot wäre.

---

### M2 — `stakeholderNeed`, `risk`, `adr`, `issue`, `testCase`

**PR:** `feat(inspector): migrate need, risk, adr, issue and testCase to the new shell (M2)` (ein PR, fünf Mounts — identische Form, Spec §8.1)

**Dateien:** Geändert: `NeedsEditors.tsx` (`:473-478`), `RiskEditors.tsx` (`:235`), `AdrEditors.tsx` (`:308`), `IssueEditors.tsx` (`:237`), `TestCaseEditors.tsx` (`:400`); je Route `hideTraceLinks` gelöscht, `artifactPk` gesetzt. Tests: die fünf Editor-Suiten.

**Interfaces:** Consumes `InspectorShell`, `HAS_SPINE` (alle fünf true); Produces: fünf Mounts mit `entityId` + `artifactPk`.

| # | Task | Akzeptanzkriterium |
|---|---|---|
| M2-1 | `stakeholderNeed` migrieren (Referenz-Mount, `artifact_id` bei `NeedsEditors.tsx:405`) | Route rendert `InspectorShell`; Kommentar-Request geht auf `/artifacts/<artifact_id>/comments/`; `hideTraceLinks` fehlt |
| M2-2 | `risk` + `adr` migrieren (Backend-Feld aus B2.0-2.2 vorausgesetzt) | beide Kommentar-Requests HTTP 200 im Test; kein `?? item.id` mehr im `artifactPk`-Pfad |
| M2-3 | `issue` migrieren | dito; `IssueEditors.tsx:237` ohne `hideTraceLinks` |
| M2-4 | `testCase` migrieren (`TestCaseEditors.tsx:342,359` nutzt `artifact_id` schon für Links) | dito; Links-Tab zeigt für `verifies` **keine** Zeile, sondern die Zusammenfassung |
| M2-5 | Typ-Sweep: DoD 1–11 je Typ abhaken, Abweichungen benennen | PR-Text enthält je Typ die fünf Kernpunkte (Mount, Kopf ID+Status, HTTP 200, Links-Tab, kein zweiter Trace-Ort) |

**Tests:** unverändert grün: `RightSidebar.*`, die Panel-Suiten, alle Ratchet-/Token-/i18n-Suiten, `NeedsEditors.test.tsx` nur mit den neuen Mount-Assertions. Neu: Erweiterung von `InspectorShell.a11y.test.tsx` um die fünf Kinds (jeder Button hat einen Namen). Angepasst: `RiskEditors.test.tsx`, `AdrEditors.test.tsx`, `IssueEditors.test.tsx`, `TestCaseEditors.test.tsx`.

**Ratchet:** 0 Delta in allen Konstanten; keine neuen Buttons ohne `btn-*`, keine Geometrie-Literale.

**DoD (§8.4) — M2:**
- [ ] 1. Mount-Punkt ersetzt, `hideTraceLinks` an der Aufrufstelle gelöscht.
- [ ] 2. Artefaktkopf zeigt ID **und** Status.
- [ ] 3. Kommentar-Pfad liefert HTTP 200.
- [ ] 4. Reiter „Links" vorhanden (alle fünf Typen), nicht `mainGoal`.
- [ ] 5. Verifikations-Badge an jeder Station mit Daten.
- [ ] 6. Kein zweiter Trace-Ort im Detail.
- [ ] 7. `data-testid`-Inventar ergänzt.
- [ ] 8. `RightSidebar.a11y`-Muster auf den neuen Reitern grün.
- [ ] 9. Kein `style={{`, kein Hex, kein Emoji, keine Literal-Geometrie, keine Schriftgröße unter `--font-size-xs`.
- [ ] 10. Visuelle Prüfung 1440 / 1024 / 768 / 320 px mit Stack.
- [ ] 11. Die zwei Inspector-Exemptions im selben PR entfernt (in M2: keine offen — `:116` ist in M1 gefallen, `:89` folgt in M8).

---

### M3 — `architecture`

**PR:** `feat(inspector): migrate architecture with one spine station per level (M3)`

**Dateien:** Geändert: `ArchitectureEditors.tsx` (`:813-818`), ggf. `useDerivationChain.ts` (nur wenn die Ebenen-Zuordnung einen Typ braucht — `:19-24` beschreibt die Baumtiefe). Tests: `ArchitectureEditors.test.tsx`, `ArchitectureEditors.unsaved-changes.test.tsx`; neu `frontend/src/components/shared/TraceSpine/TraceSpine.levels.test.tsx`.

**Interfaces:** Consumes `HAS_SPINE` (true), `LevelBadge` unverändert (keine zweite Implementierung — `STATUS_BADGE_*`/`LEVEL_BADGE_*` bleiben 1/1); Produces: Stationen je Baumebene, `leftMinWidth` 250 an der Route.

| # | Task | Akzeptanzkriterium |
|---|---|---|
| M3-1 | Mount ersetzen, `hideTraceLinks` löschen, `artifactPk` aus B2.0-2 | Kommentar-Request 200; `ArchitectureEditors.tsx` ohne `hideTraceLinks` |
| M3-2 | Spine: eine Station je Baumebene, Reihenfolge L0→L4 bleibt; horizontale Variante in R4 bleibt scrollbar ab 5 Stationen | Test: 5 Ebenen ⇒ 5 Stationen in Reihenfolge; `LevelBadge` aus `utils/badgeBase.ts` (keine lokale Geometrie) |
| M3-3 | `leftMinWidth` 250 an der Route, Inhalt ≥ 448 px beim Ziehen | Prop im Code sichtbar; Test der Splitter-Klemmung (min/max) |
| M3-4 | Verifikations-Badge auch auf Architektur-Stationen (U-07) | Test: Station mit Verifikationen ⇒ Badge; Station ohne ⇒ kein Badge |

**Tests:** unverändert grün: `SplitView.*`, `useDerivationChain.test.tsx` (Zählung bleibt Untergrenze, U-16 ist **nicht** Teil dieses Plans), alle Ratchet-Suiten. Angepasst: die zwei Architecture-Suiten. Neu: `TraceSpine.levels.test.tsx`.

**Ratchet:** `TREE_IMPLEMENTATION_BASELINE` (1) unberührt — kein neuer Baum; `LEVEL_BADGE_*` unberührt.

**DoD (§8.4) — M3:**
- [ ] 1. Mount-Punkt ersetzt, `hideTraceLinks` an der Aufrufstelle gelöscht.
- [ ] 2. Artefaktkopf zeigt ID **und** Status.
- [ ] 3. Kommentar-Pfad liefert HTTP 200.
- [ ] 4. Reiter „Links" vorhanden.
- [ ] 5. Verifikations-Badge an jeder Station mit Daten.
- [ ] 6. Kein zweiter Trace-Ort im Detail.
- [ ] 7. `data-testid`-Inventar ergänzt.
- [ ] 8. a11y-Muster grün auf den neuen Reitern.
- [ ] 9. Kein `style={{`, kein Hex, kein Emoji, keine Literal-Geometrie, keine Schriftgröße unter `--font-size-xs`.
- [ ] 10. Visuelle Prüfung 1440 / 1024 / 768 / 320 px mit Stack.
- [ ] 11. Keine Inspector-Exemption betroffen (`:116` in M1 entfernt, `:89` in M8); Ratchet-Zahlen unverändert.

---

### M4 — `goal` + `mainGoal`

**PR:** `feat(inspector): migrate goal and mainGoal with a shared persistence slot (M4)`

**Dateien:** Geändert: `GoalsPage.tsx` (`:325-352`, `:378-385`), `GoalDetail.tsx` (Kommentar `:126`), `frontend/src/types/artifact.ts` (`MainGoal` `:89-106`, sofern B2.0-4). Tests: neu `frontend/src/components/Goals/GoalsPage.inspector.test.tsx`; angepasst `frontend/src/test/`-Goals-Suiten (falls vorhanden).

**Interfaces:** Consumes `HAS_LINKS_TAB` (**false** für `mainGoal` — Reiter wird nicht gerendert, nicht deaktiviert), `artifactPk` (B2.0-4 für `mainGoal`, `Goal.artifact_id` für `goal`); Produces: **ein** Storage-Slot `reqflow_inspector_tab_goals` für beide Kinds (I-14).

| # | Task | Akzeptanzkriterium |
|---|---|---|
| M4-1 | Gemeinsamer Persistenz-Slot für beide Kinds; Reiterwahl springt beim Wechsel nicht | Test: Reiter „Links" bei Goal wählen → zu MainGoal wechseln → zurück: Reiter unverändert; **kein** zweiter Storage-Key |
| M4-2 | `goal`-Mount: `entityId = selectedGoal.id`, `artifactPk = selectedGoal.artifact_id` (heute `:344` nur `.id`) | Kommentar-Request 200; `hideTraceLinks` (`:383`) gelöscht |
| M4-3 | `mainGoal`-Mount: **kein** Links-Reiter; Kommentar-Reiter nur mit `artifactPk` (B2.0-4) | Test: Reiterleiste hat 3 Reiter (version/diff/comments) und **kein** `inspector-tab-links`; kein `disabled`-Attribut |
| M4-4 | `mainGoal` ohne `artifactPk` (falls B2.0-4 verworfen) | Kommentar-Reiter fehlt; Begründung im PR; DoD 3 als dokumentierte Ausnahme |
| M4-5 | Typ-Sweep der DoD-Punkte für beide Kinds | PR-Text listet 1–11 je Kind |

**Tests:** unverändert grün: alle Shell-Suiten, `GoalDetail`-Tests, Ratchet-Suiten. Neu: `GoalsPage.inspector.test.tsx` (Slot-Sharing, 3 vs. 4 Reiter, `?inspector=` reproduzierbar).

**Ratchet:** 0 Delta.

**DoD (§8.4) — M4:**
- [ ] 1. Mount-Punkt ersetzt, `hideTraceLinks` an der Aufrufstelle gelöscht.
- [ ] 2. Artefaktkopf zeigt ID **und** Status.
- [ ] 3. Kommentar-Pfad liefert HTTP 200 — für `mainGoal` nur mit B2.0-4; sonst dokumentierte Ausnahme.
- [ ] 4. Reiter „Links" vorhanden — **außer `mainGoal`**, dort nicht gerendert.
- [ ] 5. Verifikations-Badge an jeder Station mit Daten (Goal; `mainGoal` hat keine Spine).
- [ ] 6. Kein zweiter Trace-Ort im Detail.
- [ ] 7. `data-testid`-Inventar ergänzt.
- [ ] 8. a11y-Muster grün auf den neuen Reitern.
- [ ] 9. Kein `style={{`, kein Hex, kein Emoji, keine Literal-Geometrie, keine Schriftgröße unter `--font-size-xs`.
- [ ] 10. Visuelle Prüfung 1440 / 1024 / 768 / 320 px mit Stack.
- [ ] 11. Keine Inspector-Exemption betroffen (`:116` in M1 entfernt, `:89` in M8); Ratchet-Zahlen unverändert.

---

### M5 — `glossary`

**PR:** `feat(inspector): move glossary inspector into the right column (M5)`

**Dateien:** Geändert: `GlossaryDetailPanel.tsx` (`:79-100`), `GlossaryView.module.css` (Inline-Block `:211-215,248-250` entfernen), `frontend/src/api/glossary.ts`/Typen nur falls nötig. Tests: `GlossaryView.test.tsx`, `TermSidebar.test.tsx`; neu `frontend/src/components/GlossaryView/GlossaryDetailPanel.inspector.test.tsx`.

**Interfaces:** Consumes `LINKS_ROWS_ONLY` (glossary ⇒ Links-Tab zeigt **alle** Typen als Zeilen, keine Zusammenfassungszeile), `artifactPk = global_uuid` (B2.0-3), Tab-Label „Verwendungen" über `terminologyLabel("glossary.usages")`.

| # | Task | Akzeptanzkriterium |
|---|---|---|
| M5-1 | Shell als rechte Spalte statt Inline-Block; „Verwendungen"-Überschrift entfällt | DOM: kein Block unter der Definition; `InspectorShell` ist Schwester des Detail-Inhalts; `GlossaryView.module.css` ohne die zwei Inline-Regeln |
| M5-2 | Links-Tab: alle Typen als Zeilen (auch `derives-from`/`verifies`), **keine** Zusammenfassungszeile | Test: `derives-from` erscheint als Zeile; kein Sprungziel-Button „In der Spine anzeigen" |
| M5-3 | Label „Verwendungen" aus dem Terminologie-Profil; EN „Usages" | `i18n-parity` grün; Test rendert DE/EN korrekt |
| M5-4 | Kommentar-Reiter über `global_uuid` | Request-URL == `/artifacts/<global_uuid>/comments/`, 200 |

**Tests:** unverändert grün: `GlossaryView.test.tsx` bis auf Mount-Assertions, `TermSidebar.test.tsx`, alle Ratchet-Suiten, `i18n-parity`. Neu: `GlossaryDetailPanel.inspector.test.tsx`. Angepasst: `RightSidebar.a11y.test.tsx` (der Glossary-Fall rendert den neuen Mount — der Test bleibt inhaltlich gleich, die Montagestelle ändert sich).

**Ratchet:** 0 Delta; `PRIMARY_FILL_BASELINE` unberührt (keine Flächen-Fills).

**DoD (§8.4) — M5:**
- [ ] 1. Mount-Punkt ersetzt, `hideTraceLinks` an der Aufrufstelle gelöscht (Glossary hatte keins — Nachweis per `grep`).
- [ ] 2. Artefaktkopf zeigt ID **und** Status.
- [ ] 3. Kommentar-Pfad liefert HTTP 200.
- [ ] 4. Reiter „Links" vorhanden.
- [ ] 5. Verifikations-Badge an jeder Station mit Daten — entfällt für Glossary (keine Spine); Nachweis, dass keine Station existiert.
- [ ] 6. Kein zweiter Trace-Ort mehr im Detail („Verwendungen" ist weg).
- [ ] 7. `data-testid`-Inventar ergänzt.
- [ ] 8. a11y-Muster grün auf den neuen Reitern.
- [ ] 9. Kein `style={{`, kein Hex, kein Emoji, keine Literal-Geometrie, keine Schriftgröße unter `--font-size-xs`.
- [ ] 10. Visuelle Prüfung 1440 / 1024 / 768 / 320 px mit Stack.
- [ ] 11. Keine Inspector-Exemption betroffen (`:116` in M1 entfernt, `:89` in M8); Ratchet-Zahlen unverändert.

---

### M6 — `icd`

**PR:** `feat(inspector): replace the icd grid track and drop IcdLinkedElements (M6)`

**Dateien:** Geändert: `IcdDetailPane.tsx` (`:231-235,249-253`), `IcdDetailPane.module.css` (`:112-116`, Grid `2fr 1fr`), ggf. `frontend/src/api/icds.ts` (B2.0-3). Entfällt: `IcdLinkedElements.tsx` + `IcdLinkedElements.test.tsx`. Tests: `IcdDetailPane.test.tsx`, `IcdView.smoke.test.tsx`, `IcdView.i18n.test.tsx`.

**Interfaces:** Consumes `LINKS_ROWS_ONLY` (icd ⇒ alle Typen als Zeilen), `artifactPk = icd.artifact_id` (nullable).

| # | Task | Akzeptanzkriterium |
|---|---|---|
| M6-1 | Grid-Track `2fr 1fr` durch die Panel-/Sheet-Struktur ersetzen; keine `width`/`flex-basis` innerhalb eines Grid-Tracks (I-02) | CSS-Modul enthält kein `grid-template-columns: 2fr 1fr` mehr; Resize wirkt auf die Panel-Breite (Test: Breite ändert sich) |
| M6-2 | `IcdLinkedElements` entfernen; Links-Tab ist der einzige Ort | Datei + Test gelöscht; `grep -rn "IcdLinkedElements" frontend/src` = 0 |
| M6-3 | Stale Kommentar „`/versions/` endpoint is not exposed yet" (`IcdDetailPane.tsx:78-82`) **löschen**, nicht mitwandern (I-18) | `grep -n "not exposed yet"` = 0 |
| M6-4 | `artifactPk` aus `icd.artifact_id`; `null` ⇒ kein Kommentar-Reiter | Legacy-ICD ohne Artefakt: 3 Reiter, keine Kommentar-Anfrage |

**Tests:** unverändert grün: `IcdView.smoke.test.tsx`, `IcdView.i18n.test.tsx`, `IcdDetailPane.test.tsx` (bis auf Mount-Assertions), Ratchet-Suiten. Entfällt mit der Datei: `IcdLinkedElements.test.tsx`.

**Ratchet:** 0 Delta; `PRIMARY_FILL_BASELINE` unberührt.

**DoD (§8.4) — M6:**
- [ ] 1. Mount-Punkt ersetzt, `hideTraceLinks` an der Aufrufstelle gelöscht (ICD hatte keins — `grep`-Nachweis).
- [ ] 2. Artefaktkopf zeigt ID **und** Status.
- [ ] 3. Kommentar-Pfad liefert HTTP 200.
- [ ] 4. Reiter „Links" vorhanden.
- [ ] 5. Verifikations-Badge — entfällt (keine Spine), Nachweis.
- [ ] 6. Kein zweiter Trace-Ort (`IcdLinkedElements` ist weg).
- [ ] 7. `data-testid`-Inventar ergänzt.
- [ ] 8. a11y-Muster grün auf den neuen Reitern.
- [ ] 9. Kein `style={{`, kein Hex, kein Emoji, keine Literal-Geometrie, keine Schriftgröße unter `--font-size-xs`.
- [ ] 10. Visuelle Prüfung 1440 / 1024 / 768 / 320 px mit Stack.
- [ ] 11. Keine Inspector-Exemption betroffen (`:116` in M1 entfernt, `:89` in M8); Ratchet-Zahlen unverändert.

---

### M7 — `diagram`

**PR:** `feat(inspector): migrate diagram to the shared shell (M7)`

**Dateien:** Geändert: `DiagramDetailView.tsx` (`:536-537`), `DiagramDetailView.module.css` (`:30-34`, Flex-Pane). Tests: `DiagramDetailView.test.tsx`; neu `frontend/src/components/DiagramView/DiagramDetailView.inspector.test.tsx`.

**Interfaces:** Consumes `LINKS_ROWS_ONLY` (diagram ⇒ alle Typen als Zeilen), `artifactPk = diagram.artifact_id ?? global_uuid ?? null` (B2.0-3).

| # | Task | Akzeptanzkriterium |
|---|---|---|
| M7-1 | Flex-Pane so anpassen, dass Panel/Sheet/Rail die Breite aus `useInspectorLayout` bekommen (I-02-Analogon) | Test: R2 ⇒ Panel 320, Inhalt ≥ 448; kein überlaufender Graph-Container |
| M7-2 | Mount + `artifactPk`; Legacy-Diagramm ohne Artefakt ⇒ 3 Reiter | Test: zwei Diagramme (mit/ohne `artifact_id`) ⇒ 4 bzw. 3 Reiter |
| M7-3 | Typ-Sweep DoD 1–11 | PR-Text listet alle Punkte |

**Tests:** unverändert grün: `DiagramDetailView.test.tsx` (bis auf Mount), `DiagramList.test.tsx`, `DiagramCreateForm.test.tsx`, Ratchet-Suiten.

**Ratchet:** 0 Delta.

**DoD (§8.4) — M7:**
- [ ] 1. Mount-Punkt ersetzt, `hideTraceLinks` an der Aufrufstelle gelöscht (`grep`-Nachweis).
- [ ] 2. Artefaktkopf zeigt ID **und** Status.
- [ ] 3. Kommentar-Pfad liefert HTTP 200.
- [ ] 4. Reiter „Links" vorhanden.
- [ ] 5. Verifikations-Badge — entfällt (keine Spine), Nachweis.
- [ ] 6. Kein zweiter Trace-Ort.
- [ ] 7. `data-testid`-Inventar ergänzt.
- [ ] 8. a11y-Muster grün auf den neuen Reitern.
- [ ] 9. Kein `style={{`, kein Hex, kein Emoji, keine Literal-Geometrie, keine Schriftgröße unter `--font-size-xs`.
- [ ] 10. Visuelle Prüfung 1440 / 1024 / 768 / 320 px mit Stack.
- [ ] 11. Keine Inspector-Exemption betroffen (`:116` in M1 entfernt, `:89` in M8); Ratchet-Zahlen unverändert.

---

### M8 — Aufräumen und Alt-Bauteil entfernen

**PR:** `refactor(inspector): remove RightSidebar, dead branches and leftover literals (M8)` — **ein** PR, weil die Teile sich gegenseitig bedingen (Datei-Löschung + Exemption + Exporte).

**Dateien:** Entfällt: `RightSidebar.tsx`, `RightSidebar.module.css`, `RightSidebar.test.tsx`, `RightSidebar.a11y.test.tsx`, `TracePanel.tsx`, `TracePanel.module.css`, `TracePanel.test.tsx` (sofern der Links-Tab die letzte Nutzung war — vor dem Löschen `grep`-Nachweis). Geändert: `index.ts`, `VersionPanel.module.css` (`:236,245-246,255`), `RightSidebar.module.css:67,163` (entfällt mit der Datei), `i18n/locales/de.json:2707-2708` + `en.json`, `TraceSpine.tsx` (`:225-255`, `:211-221`), `frontend/src/test/design-system-ratchet.baseline.json` (`:89`), ggf. `ui-ratchet.test.ts` (nur senken).

**Interfaces:** Consumes: alle migrierten Mounts; Produces: keine Shell-Alternative mehr — `RightSidebar` existiert nicht.

| # | Task | Akzeptanzkriterium |
|---|---|---|
| M8-1 | `hideTraceLinks` vollständig löschen (Prop + alle Aufrufstellen) | `grep -rn "hideTraceLinks" frontend/src` = **0** (heute 12 Code-Vorkommen: 8 Aufrufstellen + 4 in `RightSidebar.tsx`) |
| M8-2 | `diff-unsupported`-Zweig löschen (I-15: alle 12 Kinds sind diff-fähig) | `grep -rn "diff-unsupported" frontend/src` = 0 |
| M8-3 | Elffach literales `white` durch `--color-on-primary` ersetzen (I-16) | `grep -rn ": white" frontend/src/components` = 0 |
| M8-4 | Emoji-Glyphen `⏱`/`≅` durch Icons ersetzen, Rail-Testids belassen (I-20) | `design-system-ratchet.test.ts` grün mit `maxViolations: 0`; kein Emoji im Inspector |
| M8-5 | „Anheften" entfernen (D7): Prop, Storage-Key `reqflow_inspector_pinned_*`, UI | `grep -rn "pinned\|pin" frontend/src/components/shared/ArtifactInspector` = 0 (außer `Baseline`-Kontext) |
| M8-6 | Stale ICD-Kommentar (falls in M6 übersehen) + DE-Umlaute („Verknuepfte Testfaelle anzeigen", „{{count}} Testfaelle", I-19) | `grep -n "Testfaelle\|Verknuepfte" frontend/src/i18n/locales/de.json` = 0 |
| M8-7 | Alt-Bauteil löschen: Dateien, Barrel-Exporte, Exemption `:89` **im selben PR** | `grep -rn "RightSidebar" frontend/src` = 0 (auch Tests); `design-system-ratchet.baseline.json` enthält keinen `ArtifactInspector`-Eintrag mehr |
| M8-8 | Ratchet neu messen und **senken**, falls der Ist-Wert fällt; nie erhöhen | PR nennt alte/neue Konstante je geänderter Zeile; `ui-ratchet.test.ts` + `design-system-ratchet.test.ts` grün |
| M8-9 | Abschließende visuelle Prüfung aller 12 Typen (1440/1024/768/320) mit Stack | Screenshot-Satz je Typ; 320 px ohne horizontalen Seiten-Scroll |

**Tests:** entfallen mit den Dateien `RightSidebar.test.tsx`, `RightSidebar.a11y.test.tsx`, `TracePanel.test.tsx`. Unverändert grün bleiben: alle `InspectorShell`-Suiten (die das a11y-Muster tragen), VersionPanel/DiffPanel/CommentPanel-Suiten, alle Ratchet-/Token-/i18n-Suiten, alle zwölf Routen-Suiten.

**Ratchet:** `design-system-ratchet.baseline.json:89` **entfernt**; `:116` ist seit M1 weg. `STYLE_BRACE_BASELINE`/`HEX_LITERAL_*`/`PRIMARY_FILL_BASELINE` neu messen und nur senken.

**DoD (§8.4) — M8:**
- [ ] 1. Mount-Punkte ersetzt, `hideTraceLinks` **überall** gelöscht (nicht nur an der letzten Aufrufstelle).
- [ ] 2. Artefaktkopf zeigt bei **allen** 12 Typen ID **und** Status.
- [ ] 3. Kommentar-Pfad liefert für alle Typen mit `artifactPk` HTTP 200.
- [ ] 4. Reiter „Links" vorhanden — außer `mainGoal`.
- [ ] 5. Verifikations-Badge an jeder Station mit Daten.
- [ ] 6. Kein zweiter Trace-Ort im Detail (ICD, Glossary, Sonstiges).
- [ ] 7. `data-testid`-Inventar vollständig; Alt-Testids entfernt.
- [ ] 8. `RightSidebar.a11y.test.tsx`-Muster lebt in `InspectorShell.a11y.test.tsx` weiter; die alte Datei ist gelöscht.
- [ ] 9. Kein `style={{`, kein Hex, kein Emoji, keine Literal-Geometrie, keine Schriftgröße unter `--font-size-xs`.
- [ ] 10. Visuelle Prüfung 1440 / 1024 / 768 / 320 px für alle 12 Typen mit Stack.
- [ ] 11. Die zwei Inspector-Exemptions sind entfernt (`:116` in M1, `:89` hier).

---

## 4. Rückfallpfad

Spec §8.2, unverändert übernommen:

- **Kein Feature-Flag, kein Parallelbetrieb zweier Shells.** Ein Schritt = ein Mount-Austausch pro Route.
- **Rückfall = Revert eines PRs.** Jede Route ist einzeln umgestellt; ein Rückfall kostet genau eine Route. Es gibt keinen geteilten Reiterzustand über Routen hinweg (Schlüssel enthalten `kind` und ID, §5.4).
- **`RightSidebar` bleibt bis M8 importierbar**, wird aber ab M1 von keiner migrierten Route verwendet. Damit ist der Rückfall von M2–M7 gleichzeitig der Rückfall auf die alte Shell dieser Route — ohne dass die Shell doppelt gepflegt wird.
- **Kein Kompatibilitäts-Shim:** `hideTraceLinks` wird an den Aufrufstellen **gelöscht**, nicht ignoriert. Die Shell leitet „hat Links-Reiter" aus `kind` ab (Lehre aus I-08: kein stiller Prop, der nichts tut).
- **Daten-Rückfall:** `VERSIONS_FETCHERS`/`mapKindToDiffEntityType` bleiben unverändert; die Spec ändert keine Endpunkte außer der D6-Ergänzung. Ein Rückfall von B2.0-1 lässt M1-8 auf Version→Version zurückfallen (Ersatz-Zielwert §1.1 M-2), ohne dass die Shell angefasst werden muss.
- **Reihenfolge-Sicherheit:** M2–M7 hängen nur von M1 ab, nicht voneinander. Ein Revert von M3 blockiert M4–M7 nicht.

---

## 5. Reihenfolge und Abhängigkeiten

| # | Schritt | Blockiert durch | Blockiert | Begründung |
|---|---|---|---|---|
| B2.0-1 | D6-Endpunkt | — | **M1-8** (Basiswechsel), M2–M7 nur mittelbar (Diff-Tab existiert schon) | ohne D6 ist M-2 nicht erreichbar (Spec §1.1 Vorbehalt) |
| B2.0-2 | D5, 7 Typen | — | **M1-7** (Kommentar-Reiter), **M2** | ohne HTTP 200 ist M-1 nicht erreichbar |
| B2.0-3 | D5, Prüf-Entscheid | — | **M4**, **M5**, **M6**, **M7** | `artifactPk`-Quelle je Kind |
| B2.0-4 | `mainGoal.artifact_id` | — | **M4-3** | sonst bleibt `mainGoal` ohne Kommentare |
| B2.0-5 | Testgerüst | — | **M1-1/M1-2** | IDs und a11y-Muster müssen vor der Shell stehen |
| **M1** | Shell + Requirements | B2.0-1, B2.0-2, B2.0-5 | **M2–M7** | Muster und Vertrag entstehen hier |
| **M2** | 5 Typen | M1, B2.0-2 | M3–M7 nur mittelbar | identische Form, kein eigener Mechanismus |
| **M3** | architecture | M1 | — | Baumtiefe ist eine Spine-Variante, keine Shell-Variante |
| **M4** | goal + mainGoal | M1, B2.0-3, B2.0-4 | M5 (Spec §8.1: `mainGoal` **vor** `glossary`) | `mainGoal` beweist die Typ-Matrix (kein Spine **und** kein Links) |
| **M5** | glossary | M1, B2.0-3, M4 | M6, M7 (nur der Reihenfolge halber) | Positionswechsel beweist D8 |
| **M6** | icd | M1, B2.0-3, M5 | M7 | Grid-Track + Doppelung |
| **M7** | diagram | M1, B2.0-3, M6 | — | letzter Typ, Flex-Pane |
| **M8** | Aufräumen | **alle** M1–M7 | — | löscht die Alt-Dateien, die bis dahin importierbar bleiben |

**Kritischer Pfad:** B2.0-1/B2.0-2/B2.0-5 → M1 → M4 → M5 → M6 → M7 → M8. M1 ist der längste Einzelschritt (12 Tasks) und der einzige, der bei einem Musterfehler alle folgenden Schritte teuer macht — deshalb steht dort der komplexeste Typ (Spec §8.1).

**Was nicht blockiert:** B2.0-1 und B2.0-2 sind voneinander unabhängig und können parallel laufen; M3 ist von M2 unabhängig (nach M1 direkt möglich).

---

## 6. Risiken und Gegenmaßnahmen

| # | Risiko | Wirkung | Gegenmaßnahme | Nachweis |
|---|---|---|---|---|
| R-1 | **Visuelle Prüfung fehlt** (kein Stack am 2026-11-11, Spec §0) | 508-px-Default, R4-Reiterstreifen (422 px) und 320-px-Reflow sind **abgeleitet, nicht gerendert** — ein Fehler fällt erst im Betrieb auf | M1-DoD 10 + M8-9 als **Nachweis**; `e2e-tester` mit den erlaubten Tools (`browser_navigate`, `browser_resize`, `browser_take_screenshot`); ohne Stack bleibt der Punkt **offen** und der PR wird nicht als „fertig" gemeldet | Screenshot-Satz im PR, Prüfpunkte 508/422/320 px explizit |
| R-2 | **`inert`-Timing** | Ein Frame, in dem der Detailbereich weder fokussierbar noch sichtbar ist (oder umgekehrt ein Frame ohne `inert`) | `useLayoutEffect` + `element.toggleAttribute("inert", open)`; Entfernen **in derselben Transaktion** wie das Unmount (Spec §4.2 Punkt 4); Fokus-Rückgabe-Kette Auslöser → Rail-Button → Kopfzeile | Unit-Test auf Attribut-Präsenz; **Achtung:** jsdom implementiert `inert` **nicht verhaltensgleich** — die Fokus-Wirkung ist nur mit Playwright/manuell belegbar, das steht im Test-Kommentar |
| R-3 | **Id-Space-Verwechslung** (`entityId` vs. `artifactPk`) | Kommentare 404/400, und niemand merkt es, weil der Fehler wie ein Netzwerkfehler aussieht | zwei getrennte Props mit dokumentierter Bedeutung; Route-Test **je Typ** prüft die exakte Request-URL; B2.0-2.1 erhebt **Serializer**, nicht TS-Typ; kein `??`-Fallback im `artifactPk`-Pfad | 7 + 4 URL-Assertions; `grep` auf `artifactPk={\w+\.artifact_id}` |
| R-4 | **Ratchet-Baseline stale** | Sobald eine Exemption ihr Ziel verliert, ist der Lauf rot — der PR blockiert an einer Zeile, die niemand erwartet | `:116` fällt in M1, `:89` in M8, jeweils **im selben PR** (Spec §8.3 „Baseline-Einträge sind kein Archiv") | beide Ratchet-Suiten im PR-Lauf; PR-Text nennt die entfernte Zeile |
| R-5 | **`hideTraceLinks`-Rest** | Ein vergessener Aufrufer übergibt einen Prop, den die neue Shell nicht kennt → TS-Fehler oder (schlimmer) tote Aufrufstelle | Prop wird gelöscht, nicht ignoriert; M8-1 prüft `grep` = 0; pro Milestone wird die eigene Aufrufstelle im selben PR bereinigt | `grep -rn hideTraceLinks frontend/src` = 0 in M8 |
| R-6 | **`Adr`/`Risk`/`Issue` liefern `artifact_id` nicht** (TS-Typ deklariert es, Serializer nicht: `types/artifact.ts:49,124,177`) | Kommentar-Reiter bleibt bei drei von sieben Typen tot — M-1 wäre nur scheinbar behoben | B2.0-2.1 erhebt je Typ am Serializer; fehlt das Feld → Backend-Nachzug in B2.0-2.2 (Serializer + `_*_to_dict`), erst dann M2 | Backend-Test je Typ + URL-Assertion |
| R-7 | **Ein-Wert-zwei-Namen** (`global_uuid` ist die Artefakt-ID, `artifact_id` heißt anders) | Glossary nutzt den falschen Wert, Kommentare laufen ins Leere | B2.0-3 legt die Quelle je Kind in einer Tabelle fest; Test prüft die URL, nicht den Feldnamen | `GlossaryDetailPanel.inspector.test.tsx` |
| R-8 | **Live-Region-Dauerfeuer** | Retry-Schleifen sagen den Fehler bei jedem Versuch an (U-03/4.1.3) | Regel „genau eine Ansage je Interaktion"; `xxxLoaded` unterdrückt `tabChanged` im selben Task; alert nur einmal je Ereignis | `InspectorLiveRegions.test.tsx` mit Announce-Spy |
| R-9 | **Reiterzustand springt** (`goal`/`mainGoal`, I-14) | Nutzer wählt „Links", wechselt das Kind, landet auf „Version" | **ein** Slot `reqflow_inspector_tab_goals` für beide Kinds | `GoalsPage.inspector.test.tsx` |
| R-10 | **`style={{`-Literal für die vier Breiten** (das naheliegendste Mittel) | `STYLE_BRACE_BASELINE` ist exakt 3 — ein Literal macht den Lauf rot | benanntes `CSSProperties`-Objekt (Muster `style={asideStyle}`) oder `element.style.setProperty` per Ref (Spec §6.1) | `ui-ratchet.test.ts` |
| R-11 | **`PRIMARY_FILL_BASELINE` +1 für „gewählte Zeile"** | Ratchet rot, weil `background: var(--color-primary)` gewählt wird | Flächen-Fills ausschließlich `--color-card-active-bg` (Spec §8.3) | `ui-ratchet.test.ts` |
| R-12 | **M1 wird zu groß** (12 Tasks, alles hängt daran) | Ein Fehler im Muster multipliziert sich über sieben PRs | M1 wird gegen die Messlatten getestet, **bevor** M2 beginnt; `InspectorShell.kinds`-Test deckt die Typ-Matrix in M1 ab, nicht erst in M4 | M1-Abnahme gegen M-1/M-2/M-3 |

---

## 7. Definition of Done je PR

Gilt zusätzlich zu §8.4 (das ist die fachliche DoD pro Migrationsschritt). Reihenfolge = Ausführungsreihenfolge.

- [ ] **Typen:** `cd frontend && npm run typecheck` grün (kein `tsc`-Bypass, keine `@ts-expect-error`-Neuzugänge).
- [ ] **Lint:** `cd frontend && npx eslint <geänderte Dateien> --report-unused-disable-directives` grün (keine neuen `eslint-disable`); Voll-Skript `npm run lint`.
- [ ] **Gezielte Suiten:** `npx vitest run <geänderte Pfade>` — jede berührte Suite **einzeln** grün, inklusive der im PR-Text genannten „bleibt grün"-Suiten.
- [ ] **Voller Lauf:** `npm test` (sequentiell) grün; Abweichungen sind im PR-Text benannt und begründet.
- [ ] **Backend (nur B2.0-1/2/4):** `pytest <neue Testdatei> -q` grün plus die betroffenen `test_baseline_*`/`test_*_serializer*`-Suiten; `manage.py check` ohne neue Warnungen.
- [ ] **CI:** Pipeline grün (4 E2E-Shards unberührt; E2E-Änderungen nur im `e2e-tester`-Rahmen).
- [ ] **Ratchet:** `ui-ratchet.test.ts` **und** `design-system-ratchet.test.ts` grün; jede Konstante nur **gesenkt** oder unverändert; jede Exemption, deren Ziel verschwindet, im selben PR gelöscht.
- [ ] **Tokens/i18n:** `design-tokens.test.ts`, `theme-contrast.test.ts`, `i18n-parity.test.ts`, `action-labels.test.ts` grün; neue Schlüssel DE+EN unter `sidebar.inspector.*`.
- [ ] **§8.4:** alle 11 Punkte des Schritts abgehakt oder als **begründete** Ausnahme im PR-Text (kein stilles Überspringen; Punkt 10 ist ohne Stack eine Ausnahme, kein Häkchen).
- [ ] **Rückfall:** PR-Text nennt, was ein Revert dieses PRs zurücknimmt (Dateien, Mounts, Baseline-Zeile).
- [ ] **Secret-Scan** vor dem Commit ohne Fund.

---

## Nicht Teil dieses Plans

- **Formulare, Listen, Navigation, Rechte, Export** (PDF/ReqIF), Selektion — Spec §9. Der Inspector ändert nur die Fläche, nicht das Artefakt.
- **`ArtifactDiff`-Rendering** (Split/Unified, Diff-Algorithmus): nur Einbettung, Legende und Fehlerzustand; Split/Unified ist ein eigener Gegenstand (Spec §9, Q11).
- **U-08** („keine Abdeckung" nur für vorhandene Stationen sichtbar) und **U-16** (`V·n` als Untergrenze) — beide bewusst offen, je ein eigenes Ticket (Spec §13).
- **Link-Validität** („passen zwei verknüpfte Artefakte inhaltlich noch zusammen?"), Live-Zusammenarbeit, Kommentar-Threads, Benachrichtigungen (Spec §9).
- **Zweiter Inspector** auf einer Seite und **dritte Offenbarungsebene** außer destruktiver Bestätigung (Spec §9).
- **Neue Design-Tokens** — nur Komponenten-Aliase (Spec §9, §6.1).
- **Der Spine-Id-Fallback** `item?.artifact_id ?? item?.id` in den Editoren: als Befund in B2.0-2.5 erfasst und über `feedback` als eigenes Ticket geführt; nicht hier mitgelöst.
- **MCP-Tools** für den D6-Endpunkt: der Endpunkt ist ein Frontend-Bedarf; ein MCP-Tool würde das Manifest (`docs/agent-templates/tool-manifest.json`, Drift-Gate `backend/mcp_server/tests/test_tool_manifest_drift.py`) ändern und gehört nicht in diesen Plan.
- **Performance-Aussagen** (Ladezeiten, Request-Zahlen als Zeitmaß) — Spec §9.
- **Barrierefreiheits-Zertifizierung**: WCAG 2.2 AA ist die Untergrenze; ein AT-Lauf (Screenreader) ist ohne Stack nicht Teil dieses Plans (Spec §7 „Was diese Spec nicht verspricht").
