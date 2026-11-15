---
type: PLAN
title: "Navigationsbaum entlasten und Verbindungsansicht als zwei Bäume — Umsetzung G → V2 → V"
status: accepted
date: 2026-11-15
author_agent: planner
language: de
spec: "docs/superpowers/specs/2026-11-08-navigationsbaum-und-verbindungsansicht-design.md"
related_specs:
  - "docs/superpowers/specs/2026-11-04-ordnung-allokation-design.md"
related_docs:
  - "docs/plans/2026-11-15-draft-spec-triage.md"
  - "docs/plans/2026-11-08-navigationsbaum-und-verbindungsansicht.md"
  - "docs/superpowers/plans/2026-11-15-document-view-on-document.md"
branch_basis: "origin/main (Prüfstand dea467b4, 2026-11-15), Worktree .tmp/wt-phase-b1"
pipeline_stages:
  implement: 1
---

# Navigationsbaum + zwei Bäume — Umsetzungsplan

**Goal:** Die Spec vom 2026-11-08 in der dort festgelegten Reihenfolge **G → V2 → V** umsetzen, in
einzeln mergebare Schnitte zerlegt. Zuerst die **Entscheidung D4/O5** (wird `Bäume` Default oder
fünfter Modus?), weil sie Spec 1 ändert und jede UI-Arbeit daran hängt. Danach: Gruppenverwaltung aus
der Navigationsspalte in einen Dialog (G), zwei kleine Backend-Verträge (`kind`-Filter,
Element-`sort_key`) plus entdoppelte Reads (V2), zuletzt die Verbindungsansicht als zwei Bäume mit
Kanten-Overlay (V).

**Architecture:** Kein neues Modell, keine Migration, kein neues ADR. G ist reine UI-Umschichtung
(`GroupManager` in `Dialog`, Zeilenaktion, Drag-Ziel). V2 erweitert **ein** bestehendes Leseobjekt
(`AllocationViewService.list`) um `kind` und den Element-`sort_key`. V ergänzt den Frontend-Modus
`trees`: zwei pure Bausteine (`allocation-trees.ts`, `edge-geometry.ts`), ein Hook
(`useAllocationSelection`), ein Renderer mit gemeinsamem Scroll-Container und ein SVG-Overlay, das
ausschließlich gemountete Zeilen misst.

**Tech Stack:** Django 6.1 + DRF, PostgreSQL 16 (RLS unverändert), pytest 9; React 19 + TypeScript 5.5
(strict), Vite 8, Vitest 5, React Query, Playwright (4 Shards). Keine neuen Abhängigkeiten.

**Spec:** `docs/superpowers/specs/2026-11-08-navigationsbaum-und-verbindungsansicht-design.md`
(D1–D9, S1–S11, B-1…B-4, §12-Phasen). Die Spec bleibt `draft`, bis G/V2/V gemergt sind — ein
Statuswechsel vor der Umsetzung wäre unbelegt (Triage §3).

**Auftrag:** Triage-E2 = (a)/(b), mit der Maßgabe, D4/O5 **vor** dem ersten UI-Schnitt zu
entscheiden. Der alte Plan `docs/plans/2026-11-08-navigationsbaum-und-verbindungsansicht.md` bleibt
liegen; dieser Plan ersetzt seine Schnittfolge (additive Reihenfolge, siehe §1), nicht seinen Inhalt.

**Nicht in diesem Plan:**

- Keine neuen Allokations-Semantiken (N:1 bleibt, `TraceLink(allocated-to)` bleibt die Wahrheit).
- Keine Änderung an `TreeRenderer`, `TwoColumnRenderer`, `MatrixRenderer`, `buildGraph.ts`,
  `AllocationGraph/*`, `api/groups.ts`, Gruppen-Backend.
- Kein `group`-Feld im Leseobjekt (bleibt Client-Join), keine Mehrfachallokation.
- Keine Virtualisierung der Bäume (Spec §9: bewusste Entscheidung, 2 × 500 Zeilen).

---

## 0. Globale Constraints

- **Navigation bleibt Navigation:** die linke Spalte der Requirements-Route enthält nur Baum +
  Suche/Filter; die Gruppenverwaltung ist im Ruhezustand **nicht gemountet**.
- **Keine zweite Wahrheit:** Filterwerte leben in der URL, Sichtbarkeiten (Kanten, „Weitere Filter")
  in Nutzerpräferenzen `ui.connection_view.*`. Beides wird nie gegeneinander ausgespielt.
- **Spec 1 bleibt Vertrag, bis D4 wirksam ist:** die Default-Darstellung der Verbindungs-Route ändert
  sich erst mit S0-Freigabe; bis dahin bleibt `tree` Default.
- **Keine Inline-Styles:** ausschließlich CSS-Module + Design-Tokens (`ui-ratchet.test.ts` friert die
  Inline-Style-Zahl ein).
- **i18n DE+EN im selben Commit** (`frontend/src/i18n/locales.test.ts` prüft Parität).
- **Kein neues MCP-Tool, keine Migration, keine neue Tool-Zahl** (bleibt 296). Backend-Änderungen sind
  additiv (neue optionale Parameter/Felder).
- **Abwärtskompatibilität:** `view=tree` bleibt gültig und öffnet `Architektur`; gespeicherte Sichten
  sind rohe Query-Strings in `ui.connection_view.saved_views` und müssen weiter funktionieren.
- **A11y:** jede Zeige-Aktion hat einen Tastaturpfad; die Kante ist nie die einzige Information.
- **Git-Mutationen** über den `git`-Agenten; Branches `feat/nav-groups-dialog`, `feat/allocation-kind-filter`,
  `feat/connection-trees`.

## 1. Schnitt-Übersicht

| # | Schnitt | Agent | Depends on | Mergebar allein? |
|---|---|---|---|---|
| S0 | **D4/O5-Entscheidung** (Default `trees` vs. fünfter Modus) + Spec-1-Nachtrag | senior-developer | — | **ja** (nur Doku) |
| G1 | Gruppen-Dialog statt Dauerverwaltung | frontend-component-engineer | S0 nicht nötig | **ja** |
| G2 | Zeilenaktion „Zu Gruppe hinzufügen…" + `AddToGroupDialog` | frontend-component-engineer | G1 | **ja** |
| G3 | Drag einer Baumzeile auf einen Gruppen-Ordner + E2E | frontend-component-engineer | G2 | **ja** |
| V2.1 | `kind`-Filter am Leseobjekt | senior-developer | — | **ja** |
| V2.2 | Element-`sort_key` im Leseobjekt | senior-developer | — | **ja** |
| V2.3 | Frontend: zwei Reads statt zwei Vollloads | frontend-component-engineer | V2.1, V2.2 | **ja** |
| V.0 | Präferenzen `show_edges`, `filters_expanded` | developer | — | **ja** (ungenutzt) |
| V.1 | `allocation-trees.ts` (pure Baumkonstruktion) | developer | — | **ja** (toter, getesteter Code) |
| V.2 | `edge-geometry.ts` (pure Geometrie) | developer | — | **ja** |
| V.3 | `useAllocationSelection` + `AllocationTreesRenderer` + Modus `trees` (**additiv**) | frontend-component-engineer | V2.3, V.0, V.1, V.2 | **ja** |
| V.4 | Assistant präsentational, Filterleiste zweizeilig, „Nicht allokiert" als Markierung | frontend-component-engineer | V.3 | **ja** |
| V.5 | Modus-Set final, Default-Flip je S0, URL-Alias, Kopfschalter, E2E, Doku | frontend-component-engineer | V.4 | **ja** |

**Warum diese Reihenfolge von der Spec abweicht:** Spec §12 verlangt „V1 und V3 gemeinsam", weil ein
V1 ohne Zeilen-Checkboxen die Mehrfachauswahl unerreichbar macht. Dieser Plan dreht die Reihenfolge
**innerhalb** von V: erst den neuen Modus **additiv** hinzufügen (V.3 — Assistant bleibt, Auswahl
bleibt, nichts bricht), dann die Assistant-Liste entfernen (V.4), dann den Default umschalten (V.5).
Damit ist jeder einzelne Merge lauffähig, statt zwei große Schnitte künstlich zu koppeln. Der
Spec-Befund („V1 ohne V3 ist ein Rückschritt") bleibt richtig — er wird durch die Reihenfolge
vermieden, nicht durch einen Sammel-PR.

**Estimated effort:** ≈ **5,25 Tage** (S0 0,25 · G 1,0 · V2 0,75 · V 3,25). Die Spec nennt
G 0,5–1, V2 0,5, V1+V3 3,25–4,25 Tage; dieser Plan liegt in derselben Größenordnung, weil V in fünf
Schnitte zerfällt und jeder Schnitt eigene Testarbeit trägt. Eine formale Schätzung durch
`effort-estimator` steht aus.

## 2. File Structure

| Bereich | Dateien |
|---|---|
| Entscheidung | `docs/superpowers/specs/2026-11-08-navigationsbaum-und-verbindungsansicht-design.md` (§3.1 D4/D9), `docs/superpowers/specs/2026-11-04-ordnung-allokation-design.md` (§4.4 + §6.2), `docs/superpowers/specs/index.md` |
| G | `frontend/src/components/RequirementEditors/RequirementEditors.tsx`, `RequirementList.tsx`, `AddToGroupDialog.tsx` (neu) + `.module.css` (neu), `frontend/src/components/shared/WorkspaceTree/workspace-tree.tsx`, `tree-drag.ts`, `tree-groups.ts`, `frontend/src/i18n/locales/{de,en}.json` |
| V2 Backend | `backend/application/allocation_view_service.py`, `backend/rest_api/views.py` (Allocation-View-Endpunkt), `backend/application/tests/test_allocation_view.py` |
| V2 Frontend | `frontend/src/components/ConnectionView/useAllocationView.ts`, `frontend/src/api/allocation-view.ts` |
| V Präferenzen | `backend/auth_tenancy/apps.py`, `backend/auth_tenancy/tests/test_preference_keys_ordering.py`, `frontend/src/api/connection-views.ts` |
| V pure Bausteine | `frontend/src/components/ConnectionView/allocation-trees.ts` (neu), `edge-geometry.ts` (neu), `useAllocationSelection.ts` (neu) |
| V Renderer | `frontend/src/components/ConnectionView/AllocationTreesRenderer.tsx` (neu), `AllocationTreesRenderer.module.css` (neu), `ConnectionView.tsx`, `ConnectionView.module.css`, `AllocationAssistant.tsx`, `FilterBar.tsx` |
| Tests/E2E | `allocation-trees.test.ts`, `edge-geometry.test.ts`, `useAllocationSelection.test.ts`, `AllocationTreesRenderer.test.tsx`, `RequirementEditors.groups.test.tsx`, `AddToGroupDialog.test.tsx`, `e2e/tests/requirement-groups.spec.ts` (neu), `e2e/tests/connection-trees.spec.ts` (neu), `e2e/tests/connection-view.spec.ts` (anpassen) |
| Doku | `docs/features/connection-view-trees.md` (neu) |

---

# S0 — Entscheidung D4/O5: wird `Bäume` der Default?

### Task S0.1: Entscheidung festziehen und Spec 1 ändern

**Ziel:** Die einzige Frage, die eine bestehende Zusage umwirft, **vor** dem ersten UI-Schnitt
beantworten — sonst wird der Default zweimal gebaut.

**Ausgangslage (geprüft):** Der Default ist heute `tree` = **Architektur-Baum mit flachen
Requirements** (`useAllocationView.ts:171-175`, `parseConnectionView` fällt auf `"tree"` zurück).
Spec 2 D4 will `Bäume` als Standarddarstellung und ändert damit Spec 1 §6.2 (normativ, heute:
„Standarddarstellung ist B (Architektur-Baum mit Unterlisten)") sowie §4.4 (Darstellungsformen).
Seit dem 2026-11-08 ist zusätzlich der **Karten-Graph** als vierte Ansicht gebaut — die Spec 1 §6.2
kennt ihn nur als „vierte Variante", also ist die Aussage dort ohnehin schon überholt.

**Optionen:**

| | (a) `trees` wird Default (Spec 2 D4) | (b) Karten-Graph bleibt Default, `trees` als fünfter Modus |
|---|---|---|
| Nutzen | Das mentale Modell des PO („eine Verbindung aus dem Navigationsbaum von Architecture und Requirement") ist das, was man beim Öffnen sieht | Null Risiko für bestehende Nutzer; keine Änderung an Spec 1 |
| Kosten | Bestehende Aufrufe ohne `view`-Parameter wechseln die Ansicht; E2E `connection-view.spec.ts` muss angepasst werden; Spec-1-Änderung nötig | Der wichtigste Befund der Spec (die naheliegende Form fehlt) bleibt hinter einem Umschalter; `trees` wird noch eine Ansicht unter fünf |
| Risiko | Nutzer mit gespeicherten Sichten **ohne** `view` bekommen eine andere Ansicht — die Sicht bleibt gültig, nur die Darstellung ändert sich | Kein Risiko, aber dauerhaft zwei „Standard"-Kandidaten |
| Spec-Vertrag | Erfüllt D4 wörtlich | Widerspricht D4; Spec 2 müsste geändert werden |

**Empfehlung: (a) `trees` wird Default** — mit drei Auflagen:

1. **Alias, nicht Bruch:** `view=tree` → `architecture`; `trees` wird beim Setzen **nicht** als
   `view`-Parameter geschrieben (Default bleibt implizit). Gespeicherte Sichten mit
   `view=tree`/`two-column`/`matrix`/`graph` funktionieren unverändert (S4 der Spec).
2. **Einmaliger Hinweis, keine stille Umstellung:** beim ersten Öffnen ohne `view`-Parameter zeigt die
   Ansicht einen entfernbareren Hinweis („Neu: Bäume — die bisherige Ansicht findest du unter
   *Architektur*", `data-testid="trees-default-notice"`), gespeichert als
   `ui.connection_view.trees_notice_seen`. Das ist die einzige Zusatzpräferenz dieses Plans und der
   Preis für eine Default-Umstellung ohne Überraschung.
3. **Spec 1 wird nachgezogen, nicht überschrieben:** §6.2 erhält einen Verweis auf Spec 2 als
   **ÄNDERT**-Markierung (D9/O5), §4.4 einen Satz zur fünften Darstellungsform. Spec 1 bleibt
   `accepted`; die Änderung ist eine Ergänzung, keine Aufhebung.

**Konsequenzen für Spec 1 (§4.4 Darstellungsformen, §6.2 Standarddarstellung):**

- §6.2 Satz 1 („Standarddarstellung ist B") wird ersetzt durch: Standard ist **Bäume**; `Architektur`
  entspricht der bisherigen Standarddarstellung B und bleibt als Modus erhalten.
- §6.2 Satz 2 („A und C über einen Umschalter, P5 kommt als vierte Variante dazu") wird zu: fünf
  Modi (`Bäume`, `Architektur`, `Zwei Spalten`, `Matrix`, `Graph`), alle über einen Umschalter.
- §4.4 bekommt einen Absatz „Bäume (nachgetragen 2026-11-15, Spec 2)" — die Beschreibung der
  Darstellung, nicht die Begründung (die steht in Spec 2).
- **Nicht** geändert: `TraceLink(allocated-to)` als einzige Wahrheit, N:1, Sperre, `sort_key`.
- **Falls (b) gewählt wird:** Spec 2 §3.1 D4 und §5.1/§5.8.1 werden auf „fünfter Modus, Default
  bleibt `tree`" umgeschrieben; der Aufwand sinkt um den Default-Flip (V.5 letzter Schritt), die
  Spec-1-Änderung entfällt vollständig.

**Files:**
- Modify: `docs/superpowers/specs/2026-11-08-navigationsbaum-und-verbindungsansicht-design.md` (§3.1
  D4/D9: „Freigabe erteilt am …" + gewählte Option), `docs/superpowers/specs/2026-11-04-ordnung-allokation-design.md`
  (§4.4, §6.2), `docs/superpowers/specs/index.md` (Eintrag Spec 2 mit Plan-Verweis)

**Akzeptanz:**
- Spec 2 nennt die gewählte Option und das Datum; D9 ist damit erledigt („nach Freigabe").
- Spec 1 §6.2 sagt die Wahrheit über die heutige Default-Darstellung und verweist auf Spec 2.
- `docs/superpowers/specs/index.md` führt Spec 2 **mit** Plan (die Triage E5 nennt den heutigen
  Zustand „no plan yet" als Drift).

- [ ] **Step 1:** Entscheidung mit dem Product Owner festhalten (eine Zeile, Datum, Option).
- [ ] **Step 2:** Spec 2 §3.1 und Spec 1 §4.4/§6.2 patchen; Index nachziehen.
- [ ] **Step 3:** Prüfen: keine anderen Stelle behauptet weiter „Standard ist B" (`grep -rn "Standarddarstellung" docs/`).
- [ ] **Step 4:** Commit `docs: decide the default connection view`.

**Mergebar allein: ja** (nur Dokumente). **Risiko:** Die Entscheidung wird vertagt und der Default
zweimal gebaut — deshalb ist S0 der erste Schnitt.

---

# G — Requirements-Route: Navigationsspalte entlasten

### Task G1.1: `GroupManager` in einen Dialog, Button in die Filterzeile

**Files:**
- Modify: `frontend/src/components/RequirementEditors/RequirementEditors.tsx` (Zustand
  `isGroupManagerOpen`, `groupPanel`-Prop entfernen, `actions` an `ListToolbar`),
  `frontend/src/components/RequirementEditors/RequirementList.tsx` (Prop `groupPanel` +
  Docstring entfernen), `frontend/src/components/RequirementEditors/RequirementEditors.module.css`,
  `frontend/src/i18n/locales/{de,en}.json`
- Test: `frontend/src/components/RequirementEditors/RequirementEditors.groups.test.tsx` (neu),
  `frontend/src/test/DocumentsView.test.tsx` bleibt unberührt

**Interfaces:**
- Consumes: `Dialog` (`frontend/src/components/shared/Dialog/Dialog.tsx` — Fokusfalle, Escape,
  Fokus-Rückgabe), `GroupManager` **unverändert**, `ListToolbar.actions` (rendert nur in der
  Filterzeile, `hasFilterRow` ist für Requirements true).
- Produces: Button `data-testid="req-list-groups-btn"` (`aria-haspopup="dialog"`), Dialog
  `data-testid="group-manager-dialog"`; **kein** `groupPanel`-Prop mehr an `RequirementList`.

- [ ] **Step 1:** Tests schreiben (fail): `no_group_manager_in_idle_dom`,
  `groups_button_opens_dialog`, `escape_closes_and_returns_focus_to_button`,
  `viewer_sees_no_groups_button`, `left_column_children_are_toggle_and_tree_only`.
- [ ] **Step 2:** Implementieren; Dialog auf **Seitenebene** rendern (nicht in `leftPanel`), sonst
  schneidet der `overflow` der SplitView-Spalte ihn ab.
- [ ] **Step 3:** `npm test -- RequirementEditors.groups` + `npm run lint` grün.
- [ ] **Step 4:** Commit `feat(ui): move group management into a dialog`.

**Akzeptanz (Spec §4.5.1/2/5):** im Ruhezustand ist kein `data-testid="group-manager"` im DOM; der
Button öffnet den Dialog; Escape schließt und fokussiert den Auslöser; Viewer sehen keinen Button;
die Listenspalte rendert nur `IncludeDeletedToggle` + `WorkspaceTree` (+ Fehlerbanner).
**Mergebar allein: ja.** **Risiko:** `ListToolbar` rendert `actions` nur mit Filterzeile — vor dem
Umbau prüfen, sonst ist der Button unsichtbar (Spec §4.2 nennt genau diese Falle).

### Task G2.1: Zeilenaktion „Zu Gruppe hinzufügen…" + `AddToGroupDialog`

**Files:**
- Create: `frontend/src/components/RequirementEditors/AddToGroupDialog.tsx` (+ `.module.css`)
- Modify: `frontend/src/components/RequirementEditors/RequirementList.tsx` (`renderRow`: Aktion
  `req-row-group-<id>` neben dem Lösch-Trigger, nur `hasRole('editor')`),
  `frontend/src/components/RequirementEditors/RequirementEditors.tsx` (Dialog-Zustand, Reload),
  `frontend/src/components/RequirementEditors/useRequirementGroups.ts` (Mitgliedschafts-Add + Reload),
  `frontend/src/api/groups.ts` (add-member, falls noch nicht vorhanden), i18n
- Test: `frontend/src/test/AddToGroupDialog.test.tsx`

**Interfaces:**
- Produces: `AddToGroupDialogProps { requirementId: string; requirementTitle: string;
  groups: GroupManagerGroup[]; onAdd(groupId, requirementId): Promise<void>; onClose(): void }`;
  Checkbox `group-add-member-<groupId>`, bereits zugeordnete Gruppen **angehakt und deaktiviert**.
- Konsumiert die bestehende Mitgliedschafts-Sicht (`useRequirementGroups`), keine zweite Quelle.

- [ ] **Step 1:** Tests (fail): `existing_membership_is_disabled_and_checked`,
  `on_add_receives_requirement_entity_id`, `error_keeps_dialog_open_with_alert`,
  `empty_group_list_shows_empty_text_and_create_form`.
- [ ] **Step 2:** Implementieren; nach Erfolg Zähler am Ordner und „in N Gruppen"-Markierung ohne
  Routen-Reload aktualisieren (Reload des Gruppen-Hooks, kein `window.location`).
- [ ] **Step 3:** `npm test -- AddToGroupDialog RequirementList` grün.
- [ ] **Step 4:** Commit `feat(ui): assign a requirement to a group from its row`.

**Akzeptanz (Spec §4.5.3):** ein Requirement lässt sich über die Zeilenaktion genau einer Gruppe
hinzufügen; Zähler und Markierung aktualisieren sich ohne Neuladen. **Mergebar allein: ja.**

### Task G3.1: Drag einer Nicht-Mitglied-Zeile auf einen Gruppen-Ordner

**Files:**
- Modify: `frontend/src/components/shared/WorkspaceTree/workspace-tree.tsx` (Prop `onAddToGroup`),
  `frontend/src/components/shared/WorkspaceTree/tree-drag.ts` (Drop-Klassifikation
  „Nicht-Mitglied auf Ordner"), `frontend/src/components/shared/WorkspaceTree/tree-groups.ts`
  (Mitgliedschafts-Helfer), `frontend/src/components/RequirementEditors/RequirementEditors.tsx`
  (Prop setzen)
- Test: `frontend/src/components/shared/WorkspaceTree/workspace-tree.groups.test.tsx` (bestehende
  Datei erweitern), `e2e/tests/requirement-groups.spec.ts` (neu)

**Interfaces:**
- Produces: `onAddToGroup?: (groupId: string, nodeId: string) => Promise<void>`; Ordner trägt beim
  Drag `data-drop-kind="group"`.
- Abgrenzung: Drop eines **Mitglieds** bleibt `onReorderGroupMember` (bestehender Test bleibt grün);
  ohne `onAddToGroup` verhält sich der Baum exakt wie heute (Architektur/Needs/Goals).

- [ ] **Step 1:** Tests (fail): `drop_of_non_member_calls_on_add_to_group`,
  `drop_of_member_still_reorders`, `tree_without_prop_is_unchanged`,
  `drop_target_marks_group_kind`.
- [ ] **Step 2:** Implementieren (`tree-drag.ts` entscheidet, `workspace-tree.tsx` ruft nur).
- [ ] **Step 3:** Unit + `npx playwright test requirement-groups` grün.
- [ ] **Step 4:** Commit `feat(ui): drag a requirement onto a group folder`.

**Akzeptanz (Spec §4.5.4/6):** Drag eines Nicht-Mitglieds legt die Mitgliedschaft an, Drag eines
Mitglieds ordnet weiter nur innerhalb der Gruppe um; die Architektur-Route bleibt unverändert.
**Mergebar allein: ja.** **Risiko (Spec R7):** Kollision mit dem bestehenden Mitglieds-Reorder —
deshalb die Fallunterscheidung **in** `tree-drag.ts` (pur, testbar) und nicht im JSX.

---

# V2 — Backend-Verträge und entdoppelte Reads

### Task V2.1: `kind`-Filter am Leseobjekt (B-1)

**Files:**
- Modify: `backend/application/allocation_view_service.py` (`list(..., kind: str | None = None)`),
  `backend/rest_api/views.py` (Query-Parameter durchreichen), `backend/rest_api/urls.py` unverändert
- Test: `backend/application/tests/test_allocation_view.py`

**Interfaces:**
- Produces: `GET /api/v1/workspaces/{id}/allocation-view/?kind=requirement|element`; unbekannter Wert
  → **400** mit dem bestehenden Envelope (`ValidationError` im Service, vom View bereits gefangen).
- Semantik: `kind` filtert **nur** `results`, **nicht** `meta`. Filterung **nach** dem bestehenden
  Filterdurchlauf und **vor** dem Slice, damit Paginierung und Zähler stimmen:
  ```python
  filtered = [row for row in rows if matches(row)]      # unverändert
  visible  = [row for row in filtered if kind is None or row["kind"] == kind]
  return {"results": visible[offset:offset + page_size], "meta": {...aus filtered...}}
  ```
  `kind` gehört **nicht** in `matches()` — sonst hinge die Kennzahl vom Aufruf ab.

- [ ] **Step 1:** Tests (fail): `kind_requirement_returns_only_requirements`,
  `kind_element_returns_only_elements`, `meta_is_independent_of_kind`,
  `unknown_kind_is_400`, `kind_none_is_unchanged`.
- [ ] **Step 2:** Implementieren; `page_size`-Validierung (1..500) bleibt.
- [ ] **Step 3:** `pytest backend/application/tests/test_allocation_view.py backend/rest_api/tests/test_openapi_list_params.py` grün.
- [ ] **Step 4:** Commit `feat: filter the allocation view by kind`.

**Mergebar allein: ja** (der Parameter ist optional, kein Konsument ändert sich).

### Task V2.2: `sort_key` für Element-Zeilen (B-2)

**Files:**
- Modify: `backend/application/allocation_view_service.py` (`_element_row`, Artefakt-Lookup
  erweitern), Test wie V2.1

**Interfaces:**
- Produces: Element-Zeilen tragen den persistierten `sort_key` ihres Artefakts (`None`, wenn keine
  Artefakt-Zeile existiert — kein Fehler, die Zeile sortiert zuletzt).
- Der bestehende Artefakt-Lookup (`Artifact.unscoped.filter(id__in=…)`) wird um die
  Element-Artefakt-Ids erweitert; **eine** Query, keine zweite.

- [ ] **Step 1:** Tests (fail): `element_row_carries_artifact_sort_key`,
  `element_without_artifact_row_has_none`, `no_additional_query_for_elements`
  (`assertNumQueries` unverändert gegenüber V2.1).
- [ ] **Step 2:** Implementieren.
- [ ] **Step 3:** `pytest` grün.
- [ ] **Step 4:** Commit `feat: expose element sort keys in the allocation view`.

**Mergebar allein: ja.**

### Task V2.3: Frontend liest zweimal statt doppelt (B-3)

**Files:**
- Modify: `frontend/src/components/ConnectionView/useAllocationView.ts` (zwei Queries mit `kind`,
  `elements` **nur** aus `elementsQuery`), `frontend/src/api/allocation-view.ts` (`kind` im
  Query-Typ), `frontend/src/components/ConnectionView/useAllocationView.test.ts`

**Interfaces:**
- Produces: `rowsQuery = view(ws, {...filtersToQuery(filters), kind: "requirement"})`,
  `elementsQuery = view(ws, {...filtersToQuery(filters), kind: "element"})`;
  `filtersToQuery` bekommt `kind` **nicht** als Filterfeld (kein URL-Parameter); der
  `allRows`-Fallback für Elemente entfällt.
- `element_subtree` wirkt damit auch auf die Element-Spalte (der Filter steht schon in
  `filtersToQuery`).

- [ ] **Step 1:** Tests (fail): `elements_come_only_from_the_element_read`,
  `no_element_rows_when_element_read_is_empty`, `element_subtree_restricts_elements`,
  `regression_600_requirements_20_elements_yields_all_elements` (Service-Ebene, mit V2.1),
  `url_has_no_kind_parameter`.
- [ ] **Step 2:** Implementieren; Query-Keys anpassen (`allocationViewKeys.elements(ws, query)`).
- [ ] **Step 3:** `npm test -- useAllocationView` + `pytest` grün.
- [ ] **Step 4:** Commit `feat(ui): read requirements and elements separately`.

**Akzeptanz V2:** `kind` liefert je Art nur die eigene Menge, `meta` bleibt unabhängig; Element-Zeilen
tragen `sort_key`; das Frontend lädt zwei gezielte Reads statt zwei Vollloads, und der 500er-Deckel
gilt pro Art (Regressionstest mit 600 Requirements + 20 Elementen).
**Gates:** `test_openapi_list_params.py` (neuer Query-Parameter), keine Migration, kein neues Tool.
**Mergebar allein: ja** (jeder der drei Schnitte).

---

# V — Verbindungsansicht als zwei Bäume

### Task V.0: Zwei Nutzerpräferenzen registrieren (B-4)

**Files:**
- Modify: `backend/auth_tenancy/apps.py` (neben `ui.connection_view.saved_views`),
  `backend/auth_tenancy/tests/test_preference_keys_ordering.py`,
  `frontend/src/api/connection-views.ts` (Lesen/Schreiben der beiden Schlüssel)
- Test: `backend/auth_tenancy/tests/test_preference_keys_ordering.py`,
  `frontend/src/api/connection-views.test.ts`

**Interfaces:**
- Produces:
  ```python
  PreferenceKey(key="ui.connection_view.show_edges", value_type="bool", default=True,
               levels=frozenset({PREFERENCE_SCOPE_USER}), mode="override",
               ui_editor="checkbox", owner="P3")
  PreferenceKey(key="ui.connection_view.filters_expanded", value_type="bool", default=False,
               levels=frozenset({PREFERENCE_SCOPE_USER}), mode="override",
               ui_editor=None, owner="P3")
  ```
  Frontend: `loadShowEdges()`, `saveShowEdges()`, `loadFiltersExpanded()`,
  `saveFiltersExpanded()`; Lesefehler ⇒ Default, Schreibfehler ⇒ Meldung, Zustand bleibt lokal.

- [ ] **Step 1:** Tests (fail): beide Schlüssel registriert, `bool`, Defaults `true`/`false`, **nur**
  Nutzer-Ebene schreibbar (Workspace-/Global-Schreibversuch wird abgelehnt); Frontend:
  `load_falls_back_to_default_on_error`, `save_failure_keeps_local_state`.
- [ ] **Step 2:** Implementieren. **Registrierung zuerst** — ein unbekannter Schlüssel wird vom
  Backend abgelehnt, der Schalter wäre sonst wirkungslos (Spec R2).
- [ ] **Step 3:** `pytest backend/auth_tenancy/tests/test_preference_keys_ordering.py` + `npm test -- connection-views` grün.
- [ ] **Step 4:** Commit `feat: add connection view display preferences`.

**Mergebar allein: ja** (Schlüssel sind noch ungenutzt). **Gates:** keine Migration
(Präferenzschlüssel sind Code-Registrierung), Level-Gate-Test.

### Task V.1: `allocation-trees.ts` — Baumkonstruktion (pur)

**Files:**
- Create: `frontend/src/components/ConnectionView/allocation-trees.ts`
- Test: `frontend/src/components/ConnectionView/allocation-trees.test.ts`

**Interfaces:**
- Produces:
  ```ts
  export interface AllocationRequirementNode { row: AllocationRow; children: AllocationRequirementNode[]; depth: number }
  export function buildRequirementTree(rows: readonly AllocationRow[]): AllocationRequirementNode[]
  export interface AllocationEdge { requirementId: string; elementId: string }
  export function buildAllocationEdges(requirements: readonly AllocationRow[], elements: readonly AllocationRow[]): AllocationEdge[]
  ```
- Regeln: Eltern über `requirementByArtifact.get(row.parent_id)`; fehlender Elternknoten ⇒ Wurzel
  (identisch zu `useArtifactList`); Geschwister nach `sort_key` mit **`null` zuletzt**, Tiebreak
  `title` (Wiederverwendung von `compareRows` aus `useAllocationView.ts` — **nicht**
  `compareElementRows` aus `TreeRenderer.tsx`, das `null` zuerst sortiert); Zyklus-/Duplikatschutz
  über eine besuchte Menge (Muster wie `buildGraph.ts`).
- `row.allocated_to` ist die **Artefakt**-Id des Ziels → `elementByArtifact`; fehlt das Element,
  entfällt die Kante (die Zeile zeigt dann „außerhalb des Filters", nicht „nicht allokiert").

- [ ] **Step 1:** Tests (fail): `builds_roots_and_children`, `missing_parent_becomes_root`,
  `siblings_sort_by_sort_key_with_null_last`, `cycle_is_broken`,
  `no_node_appears_twice`, `edge_only_when_both_ends_present`, `edge_count_matches_allocations`.
- [ ] **Step 2:** Implementieren (kein React-Import, keine DOM-Abhängigkeit).
- [ ] **Step 3:** `npm test -- allocation-trees` grün.
- [ ] **Step 4:** Commit `feat(ui): add allocation tree builders`.

**Mergebar allein: ja** (noch nicht importiert).

### Task V.2: `edge-geometry.ts` — Zeilenrechtecke zu Pfaden (pur)

**Files:**
- Create: `frontend/src/components/ConnectionView/edge-geometry.ts`
- Test: `frontend/src/components/ConnectionView/edge-geometry.test.ts`

**Interfaces:**
- Produces:
  ```ts
  export interface RowRect { top: number; height: number }
  export interface EdgePath { id: string; d: string }
  export function buildEdgePaths(
    edges: readonly AllocationEdge[],
    from: ReadonlyMap<string, RowRect>,
    to: ReadonlyMap<string, RowRect>,
    gutter: { x1: number; x2: number },
  ): EdgePath[]
  ```
- Stabil sortiert nach `requirementId`, damit React nicht neu keyt; fehlende Enden ⇒ keine Kante;
  Bézier mit zwei Kontrollpunkten im Korridor (`x1`/`x2`).

- [ ] **Step 1:** Tests (fail): `produces_one_path_per_resolvable_edge`,
  `skips_edges_with_missing_end`, `order_is_stable_independent_of_input_order`,
  `path_starts_and_ends_at_gutter_edges`.
- [ ] **Step 2:** Implementieren.
- [ ] **Step 3:** `npm test -- edge-geometry` grün.
- [ ] **Step 4:** Commit `feat(ui): add allocation edge geometry`.

**Mergebar allein: ja.**

### Task V.3: Renderer `Bäume` **additiv** + Selektion im Baum

**Files:**
- Create: `frontend/src/components/ConnectionView/useAllocationSelection.ts` (neu),
  `frontend/src/components/ConnectionView/AllocationTreesRenderer.tsx` (neu),
  `AllocationTreesRenderer.module.css` (neu)
- Modify: `frontend/src/components/ConnectionView/useAllocationView.ts` (`ConnectionViewMode`
  um `"trees"` erweitern, `parseConnectionView` erkennt `trees`, **Default bleibt `tree`** bis V.5),
  `ConnectionView.tsx` (Render-Zweig + Modus-Eintrag), `ConnectionView.module.css`
- Test: `useAllocationSelection.test.ts`, `AllocationTreesRenderer.test.tsx`,
  `ConnectionView.test.tsx` (Erweiterung)

**Interfaces:**
- `useAllocationSelection(requirements: readonly AllocationRow[]): AllocationSelection` mit
  `selectableIds`, `selectedRows`, `isSelected`, `toggle`, `selectAll`, `clear`; gesperrte Zeilen
  sind nicht selektierbar; `selectAll` nur über sichtbare; `selectedIds` überlebt Filterwechsel,
  wirkt aber nur auf sichtbare Zeilen.
- `AllocationTreesRenderer` Props: `{ requirements, elements, selection, showEdges, onAllocate,
  onDeallocate, canEdit }`. Struktur: **ein** Scroll-Container mit zwei Spalten (kein
  Scroll-Sync), je Spalte `<section aria-label>`, Zeilen `<li>`, Teilbaum
  `<ul role="group" aria-labelledby>`, Aufklappen über `<button aria-expanded aria-controls>`.
- Kanten: `useLayoutEffect` + `getBoundingClientRect()` je sichtbarer Zeile (`[data-alloc-row]`),
  Neuberechnung bei `scroll`/`resize`/Aufklappen/Filterwechsel, gedrosselt über
  `requestAnimationFrame`; `<svg aria-hidden="true">`; Kante `data-testid="allocation-edge-<requirementId>"`.
- Zeilen kompakt (~28 px), Requirement-Zeile mit Checkbox `alloc-select-<id>`, Zieltext
  (`alloc-target-<id>` / „nicht allokiert") **immer** sichtbar, auch bei `showEdges=false`.

- [ ] **Step 1:** Tests (fail): `mode_trees_is_reachable_and_additive` (Assistant-Liste existiert
  weiterhin, bestehende Tests grün), `renders_two_columns_with_hierarchy`,
  `checkbox_selection_survives_filter_change`, `locked_rows_are_not_selectable`,
  `edge_count_equals_allocation_count`, `show_edges_false_renders_no_svg_but_keeps_target_text`,
  `keyboard_expand_uses_button_with_aria_expanded`, `drag_calls_allocate_with_entity_ids`.
- [ ] **Step 2:** Implementieren. Bewusst **keine** Entfernung der Assistant-Liste in diesem Schnitt —
  das ist die Additivitätsgarantie.
- [ ] **Step 3:** `npm test -- AllocationTreesRenderer useAllocationSelection ConnectionView` grün.
- [ ] **Step 4:** Commit `feat(ui): add the trees renderer for connections`.

**Mergebar allein: ja** (neuer Modus, alter Default, alter Assistant unverändert).
**Risiken:** Overlay-Geometrie bei zugeklappten Zweigen (nur gemountete Zeilen werden gemessen —
gewollt); `ui-ratchet.test.ts` (keine Inline-Styles).

### Task V.4: Assistant präsentational, Filterleiste zweizeilig, „Nicht allokiert" als Markierung

**Files:**
- Modify: `frontend/src/components/ConnectionView/AllocationAssistant.tsx` (Liste raus, Props
  `selection`, `requirements`, `elements`, `allocateBulk`, `suggestArchitecture`, `canEdit`),
  `ConnectionView.tsx` (Aktionsleiste, Filterzeile), `FilterBar.tsx` (Zeile 1 + „Weitere Filter"-
  Popover mit `filters_expanded`), `ConnectionView.module.css`, i18n
- Test: `AllocationAssistant.test.tsx` (umschreiben), `FilterBar.test.tsx` (neu),
  `ConnectionView.test.tsx` (Erweiterung)

**Interfaces:**
- Die Leiste zeigt immer: Auswahlzähler (`assistant-selection-count`), „Alle auswählen"
  (`assistant-select-all`), „Allokieren auf …" (`assistant-allocate`, ohne Auswahl deaktiviert),
  „Vorschläge" (`assistant-suggest`, immer aktiv). Vorschlagsliste/Bestätigung/Fehlerflächen bleiben
  (`assistant-suggestions`, `assistant-suggestion-confirm`, `assistant-error`, `assistant-notice`).
- Filterzeile 1: `Offen` · `Nicht allokiert` · `Gesperrt` · `Befunde` · Suche · `Weitere Filter ▾` ·
  Kennzahlen (`counter-total`, `counter-unallocated`, `counter-locked`, `counter-findings`).
  Popover `data-testid="filter-more"`: Stufe, Typ, Kategorie, Zustand, Element-Teilbaum, Gruppe,
  gespeicherte Sichten; Badge „Weitere Filter (n)".
- „Nicht allokiert"-Block (`unallocated-block`/`unallocated-count`) entfällt; Zeilen tragen
  `unallocated-marker-<id>` und `alloc-target-external-<id>`.

- [ ] **Step 1:** Tests (fail): `assistant_has_no_list`, `action_bar_visible_without_selection`,
  `select_all_counts_visible_unlocked_only`, `filter_more_state_follows_preference`,
  `filters_expanded_survives_reload`, `failed_preference_write_keeps_popover_open`,
  `unallocated_block_is_gone_and_marker_exists`, `url_still_carries_filter_values`.
- [ ] **Step 2:** Implementieren (Assistant bleibt präsentational — keine eigene Auswahl).
- [ ] **Step 3:** `npm test -- AllocationAssistant FilterBar ConnectionView` + `npm run lint` grün.
- [ ] **Step 4:** Commit `feat(ui): simplify the connection action and filter bars`.

**Akzeptanz (Spec §5.4/5.5/5.6, §5.8.6/7/14):** keine zweite Requirements-Liste; Aktionsleiste immer
sichtbar; „Nicht allokiert" nur noch als Zeilenmarkierung + Zähler; der Aufklapp-Zustand überlebt
einen Reload, ohne einen Filterwert aus der URL zu verlieren.
**Mergebar allein: ja** (setzt V.3 voraus — die Checkboxen sind der Ersatz für die entfernte Liste).

### Task V.5: Modus-Set final, Default je S0, URL-Alias, Kopfschalter, E2E, Doku

**Files:**
- Modify: `frontend/src/components/ConnectionView/useAllocationView.ts`
  (`ConnectionViewMode = "trees" | "architecture" | "two-column" | "matrix" | "graph"`,
  `parseConnectionView`: `"tree"|"architecture"` → `architecture`, fehlt → **je S0**),
  `ConnectionView.tsx` (fünf Einträge, `view-switch-trees`/`view-switch-architecture`,
  Kopfschalter `connection-view-show-edges`), `ConnectionView.module.css`,
  `frontend/src/i18n/locales/{de,en}.json` (`connectionView.views.tree` →
  `connectionView.views.architecture`, neu `connectionView.views.trees`),
  `e2e/tests/connection-view.spec.ts`, `docs/features/connection-view-trees.md` (neu)
- Test: `ConnectionView.test.tsx`, `useAllocationView.test.ts`,
  `e2e/tests/connection-trees.spec.ts` (neu)

**Interfaces:**
- `setView("trees")` schreibt **keinen** `view`-Parameter; alle anderen Modi schreiben ihren Namen.
- Bei S0 = (a): ohne `view` → `trees`; bei S0 = (b): ohne `view` → `tree`/`architecture`.
  Der Alias `view=tree` → `architecture` gilt in **beiden** Fällen.
- Kopfschalter liest/schreibt `ui.connection_view.show_edges`; er schaltet **nur** das Overlay ab.

- [ ] **Step 1:** Tests (fail): `default_mode_matches_decision`, `tree_alias_opens_architecture`,
  `two_column_is_unchanged`, `saved_view_with_old_params_still_works`,
  `show_edges_preference_persists_across_mode_switch`, `five_switch_entries`.
- [ ] **Step 2:** Implementieren; E2E `connection-view.spec.ts` auf die neuen Testids anpassen
  (`unallocated-count` → `counter-unallocated`, `assistant-check-<id>` → `alloc-select-<id>`),
  `connection-trees.spec.ts` neu: zwei Bäume, eine Kante, Klick betont Gegenstück, Drag allokiert,
  Tastaturpfad allokiert.
- [ ] **Step 3:** `npm test` + `npx playwright test connection-view connection-trees` (4 Shards) grün.
- [ ] **Step 4:** Feature-Doku + i18n; Commit `feat(ui): finish the trees default view`.

**Akzeptanz (Spec §5.8.1/2/8/13):** Umschaltleiste hat fünf Einträge, `Bäume` ist je Entscheidung
aktiv; `view=tree` öffnet `Architektur`; gespeicherte Sichten funktionieren; der Kantenschalter
überlebt Reload und Moduswechsel. **Mergebar allein: ja.** **Risiko (Spec R3):** gespeicherte Sichten
— deshalb Alias-Mapping + Test, und `setView` nie in den Filter-Pfad mischen.

---

## 3. Offene Entscheidungen

| # | Entscheidung | Optionen | Empfehlung | blockiert |
|---|---|---|---|---|
| **O1 (D4/O5)** | Wird `Bäume` Default? | (a) ja, mit Alias + einmaligem Hinweis; (b) nein, fünfter Modus | **(a)** — sonst bleibt der Kernbefund der Spec hinter einem Umschalter; (b) ist die billige Rückfalloption | V.5, Spec 1 |
| **O2** | Zusätzlicher Hinweis bei der Default-Umstellung? | (a) einmaliger Hinweis + Präferenz `trees_notice_seen`; (b) keine Präferenz, nur Alias | **(a)** — eine stille Umstellung des Defaults ist die einzige echte Nutzerüberraschung dieses Plans | V.5 |
| **O3** | Wird der alte Plan `docs/plans/2026-11-08-…` auf `superseded` gesetzt? | (a) ja, mit Verweis auf diesen Plan; (b) stehen lassen | **(a)** — zwei Pläne für dasselbe Vorhaben sind die nächste Triage-Lüge | S0 |
| **O4** | Wo lebt die Baum-Semantik? | (a) eigener Renderer mit `<ul role="group">` (Spec §8); (b) `WorkspaceTree` umbauen | **(a)** — ein Umbau würde fünf Routen mitziehen; Spec nennt das ausdrücklich | V.3 |
| **O5** | Wird `Zwei Spalten` beibehalten? | (a) ja (D6, entschieden); (b) streichen | **(a)** — bereits entschieden, hier nur zur Absicherung gegen „Aufräumen" | V.5 |

**Es bleiben keine inhaltlichen Fragen offen** (Spec §14): O1–O5 der Spec sind am 2026-11-08
beantwortet; die Tabelle oben enthält nur die zwei Punkte, die dieser Plan neu entscheiden muss.

## 4. Risiken

| # | Risiko | Maßnahme |
|---|---|---|
| **R1** | Overlay-Geometrie falsch bei tiefen/zugeklappten Bäumen | nur gemountete Enden messen; Zieltext zusätzlich an jeder Zeile; Test mit zugeklappten Zweigen |
| **R2** | Neuer Präferenzschlüssel nicht registriert ⇒ Schreiben 400, Schalter wirkungslos | V.0 **vor** V.3/V.4; Level-Gate-Test; fehlgeschlagenes Laden/Schreiben blockiert die Ansicht nicht |
| **R3** | Gespeicherte Sichten brechen | URL-Alias-Mapping (S4 der Spec) + Tests in `ConnectionView.test.tsx` und `useAllocationView.test.ts` |
| **R4** | `ui-ratchet.test.ts` (eingefrorene Inline-Style-Zahl) schlägt fehl | ausschließlich CSS-Module, keine `style={{}}`-Literale |
| **R5** | i18n-Paritätstest schlägt fehl | beide Locale-Dateien im selben Commit; `connectionView.views.tree` wird **umbenannt**, nicht gelöscht (Parität prüft Schlüsselmengen) |
| **R6** | 500er-Deckel bleibt an anderer Stelle (Matrix-Fenster, gespeicherte Sichten) | `SERVER_PAGE_SIZE` bleibt; V2.1 macht ihn pro Art gültig; Hinweis `trees-truncated-notice` bei Erreichen |
| **R7** | Drag-zu-Gruppe kollidiert mit Mitglieds-Reorder | Fallunterscheidung in `tree-drag.ts` + Test; ohne `onAddToGroup` unverändertes Verhalten |
| **R8** | Doppelte Semantik „Architektur" vs. „Bäume" | `Architektur` bleibt element-zentrisch, bekommt keine Checkboxen und keine Kanten; `TreeRenderer` unangetastet |
| **R9** | Default-Flip bricht E2E-Shards | V.5 ist der **einzige** Schnitt, der den Default ändert; E2E-Anpassung im selben Commit; `view-switch-*`-Testids bleiben im Muster |
| **R10** | Zwei Pläne für ein Vorhaben | O3: alten Plan auf `superseded` setzen, sobald dieser Plan läuft |

## 5. Querschnitt-Gates

| Gate | gilt für |
|---|---|
| `backend/application/tests/test_allocation_view.py` (Service-Verträge, `meta`-Semantik) | V2.1, V2.2 |
| `backend/rest_api/tests/test_openapi_list_params.py` (`kind`) | V2.1 |
| `backend/auth_tenancy/tests/test_preference_keys_ordering.py` (Registrierung + Level-Gate) | V.0 |
| `backend/rest_api/tests/test_architecture.py` (kein ORM in Views) | V2 |
| `frontend/src/i18n/locales.test.ts` (DE/EN-Parität) | G1–G3, V.3–V.5 |
| `frontend/src/**/ui-ratchet.test.ts` (Inline-Styles) | G1–G3, V.3–V.5 |
| `e2e` 4 Shards | G3, V.5 |
| Tool-Zahl / Manifest / Migrationen: **unverändert** | alle |

## 6. Self-Review

- Jeder Task mappt auf genau eine Rolle: `senior-developer` (S0, V2.1/V2.2), `developer` (V.0, V.1,
  V.2 — kleine, pur testbare Bausteine), `frontend-component-engineer` (G1–G3, V2.3, V.3–V.5).
- Keine Dateiüberlappung innerhalb einer Parallel-Gruppe: V.1 und V.2 sind unabhängig (verschiedene
  Dateien), V.3 berührt `ConnectionView.tsx` und muss nach beiden laufen. G1–G3 sind sequenziell
  (alle drei ändern `RequirementEditors.tsx`/`RequirementList.tsx`).
- Jedes Akzeptanzkriterium ist prüfbar: DOM-Testid, HTTP-Code, `assertNumQueries`, Kantenzahl,
  Reload-Verhalten, Playwright-Schritt.
- `Files:`/`Interfaces:` vollständig, Consumes/Produces getrennt.
- `pipeline_stages` gesetzt (`implement: 1`, gleiche Konvention wie die übrigen Pläne vom 2026-11-15).
- Die Reihenfolge weicht **begründet** von Spec §12 ab (V additiv statt Sammel-PR) — der Spec-Befund
  „V1 ohne V3 ist ein Rückschritt" bleibt gültig und wird durch die Reihenfolge vermieden.
