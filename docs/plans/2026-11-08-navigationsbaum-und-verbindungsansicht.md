# Navigationsbaum entlasten und Verbindungsansicht als zwei Bäume — Umsetzungsplan

> **Status: geplant, nicht umgesetzt.** Alle Checkboxen sind offen. Nichts aus diesem Plan ist
> implementiert; der Branch enthält nur Spezifikation und diesen Plan.

**Ziel:** Die Requirements-Route bekommt ihre Navigationsspalte zurück (Gruppenverwaltung in einen
Dialog, Mitgliedschaft aus dem Baum heraus), und die Verbindungs-Route bekommt eine
Standarddarstellung, die Requirements-Baum und Architektur-Baum nebeneinander zeigt und die
Allokationen als Kanten dazwischen zeichnet.

**Architektur:** Keine neue Persistenz. Ein neuer Query-Parameter `kind` auf dem bestehenden
Leseobjekt `allocation-view` trennt die beiden Arten (und behebt den gemeinsamen 500er-Deckel), ein
fehlendes `sort_key` auf Element-Zeilen wird nachgezogen, zwei Nutzerpräferenzen steuern Kanten und
Filterleiste. Die Darstellung ist ein reiner Frontend-Renderer über demselben Leseobjekt (V10 der
Vorlagenspezifikation).

**Spec:** [`docs/superpowers/specs/2026-11-08-navigationsbaum-und-verbindungsansicht-design.md`](../superpowers/specs/2026-11-08-navigationsbaum-und-verbindungsansicht-design.md).
IDs (`D*`, `S*`, `B-*`, `R*`) verweisen auf deren Abschnitte. Vor dem Editieren jede `pfad:zeile`
neu prüfen — Zeilennummern wandern.

**Tech-Stack:** Django 6.1 + DRF, pytest; React 19 + TypeScript, Vitest, Playwright, React Query,
CSS Modules mit Design-Tokens.

## Globale Randbedingungen

- **Branch:** von `origin/main` (nie von lokalem `main`), Name `feat/*`. **Ein PR pro Phase**
  (G, V2, V). Phase V ist die einzige Ausnahme von „ein PR pro Task", weil V1 und V3 gemeinsam
  ausgeliefert werden müssen (Spec §12).
- **Git-Mutationen** (Branch, Commit, Push, PR) ausschließlich über den `git`-Agenten.
  Conventional Commits, Englisch, erste Zeile ≤ 72 Zeichen.
- **Testläufe sequenziell** (≈5,8 GiB RAM). Backend-RLS-Tests brauchen den DB-Superuser, siehe
  `testing/`.
- **Nicht umsetzen:** §6.2 der Vorlagenspezifikation wird **nicht** geändert (D9/O5). Diese
  Änderung erfolgt erst nach ausdrücklicher Freigabe, in einem eigenen Commit.
- **Nicht anfassen:** `TreeRenderer.tsx`, `TwoColumnRenderer.tsx`, `MatrixRenderer.tsx`,
  `buildGraph.ts`, `AllocationGraph/*`, `api/groups.ts`, Gruppen-Backend. Bestehende Tests dieser
  Module bleiben unverändert grün (Spec §5.8 Kriterium 12).
- **UI-Regeln:** i18n DE+EN in derselben Änderung (`locales.test.ts` prüft die Parität), nur
  Design-Tokens und CSS-Module (keine Inline-Styles, `ui-ratchet.test.ts`), `data-testid` an jedem
  interaktiven Element, Tastaturpfad für jede Drag-Aktion.
- **Keine neuen REST-Routen und keine neuen MCP-Tools.** Damit sind `tool-manifest.json`,
  `tool_registry.py` und die Zähler in README/CLAUDE.md **nicht** betroffen. Der neue
  Query-Parameter `kind` muss nur dort dokumentiert werden, wo `allocation-view` bereits beschrieben
  ist.

## Review-Fokus

1. **Kein Datenverlust durch Filter.** Zwei getrennte Reads (`kind=requirement` / `kind=element`)
   dürfen `meta` nicht verändern; `meta` wird weiter aus der **ungefilterten nach Art** Menge
   gerechnet (B-1). Ein Test pinnt das.
2. **Ordnungstreue.** Element-Geschwister folgen `sort_key` mit `null` **zuletzt** (B4). Ein Test
   mit gemischten `null`/gesetzten Schlüsseln pinnt die Reihenfolge in beiden Bäumen.
3. **Doppelte Semantik.** `Bäume` und `Zwei Spalten` dürfen nicht auseinanderlaufen: beide lesen
   dieselben Props, keiner bekommt eigene Filterlogik. `Architektur` bleibt unverändert.
4. **Sperre.** Ein gesperrtes Requirement ist in `Bäume` nicht ziehbar und nicht selektierbar; ein
   gesperrtes Element bleibt Ziel (E6). Ein Test prüft beides über die UI, einer über die Fehler,
   die der Schreibpfad liefert.
5. **Präferenz-Fehler sind nicht fatal.** Ein fehlgeschlagenes Laden/Schreiben der beiden
   `ui.connection_view.*`-Schlüssel darf die Ansicht weder blockieren noch den lokalen Zustand
   zurücksetzen.
6. **Kein „halb umgebauter" Zustand.** Nach Phase G ist die Gruppenverwaltung **nur** im Dialog
   erreichbar (kein toter `groupPanel`-Prop-Rest), nach Phase V gibt es **keine** zweite
   Requirements-Liste mehr im Assistant.

---

# Phase G — Gruppenverwaltung aus der Navigationsspalte

**Ziel:** Die linke Spalte enthält nur noch Toolbar + Toggles + Baum. Die Gruppenverwaltung ist ein
Dialog; Zuordnen geht aus dem Baum heraus (Zeilenaktion und Drag auf den Ordner).
**Spec:** D1, D2, D5, S1, S2, §4.1–§4.5.

### Task G.1: Akzeptanztest zuerst — die Spalte ist keine Verwaltung mehr

**Dateien:**
- Neu: `frontend/src/components/RequirementEditors/RequirementEditors.groups.test.tsx`
- Lies: `RequirementEditors.tsx:663-761` (Aufbau der linken Spalte), `RequirementList.tsx:447`

**Schnittstellen:**
- Produces (Testvertrag): Im Ruhezustand existiert **kein** `[data-testid="group-manager"]`;
  `req-list-groups-btn` öffnet `[data-testid="group-manager-dialog"]`; Escape schließt und gibt den
  Fokus auf den Auslöser zurück; ein Viewer findet weder `req-list-groups-btn` noch
  `req-row-group-<id>`.

- [ ] **Schritt 1:** Test schreiben, der `RequirementEditors` mit gemockten Hooks rendert (Muster:
  `RequirementList.roleGate.test.tsx`). Fälle: `renders_no_group_manager_by_default`,
  `opens_dialog_from_toolbar`, `escape_closes_and_restores_focus`, `viewer_sees_no_group_controls`.
- [ ] **Schritt 2:** `cd frontend && npx vitest run src/components/RequirementEditors/RequirementEditors.groups.test.tsx`.
  Erwartung: **FAIL** (heute ist `group-manager` immer gemountet).
- [ ] **Schritt 3:** Noch nicht implementieren — der Test ist der Vertrag für G.2/G.3.
- [ ] **Schritt 4:** Commit `test: pin group manager out of the requirement navigation column`.

### Task G.2: `groupPanel` entfernen

**Dateien:**
- Modify: `frontend/src/components/RequirementEditors/RequirementList.tsx` (Prop + Docstring
  `:268-273`, Render `:447`)
- Modify: `frontend/src/components/RequirementEditors/RequirementEditors.tsx:742-754`

**Schnittstellen:**
- Entfällt: `RequirementListProps.groupPanel?: React.ReactNode`. Kein Ersatz-Prop — der Dialog
  gehört auf Seitenebene, nicht in die Liste.

- [ ] **Schritt 1:** `grep -rn "groupPanel" frontend/src` — es gibt keinen Test, der den Prop
  übergibt (Stand geprüft); nach dem Entfernen muss der Treffer leer sein.
- [ ] **Schritt 2:** Prop, Docstring und Render-Block entfernen; Aufrufstelle in
  `RequirementEditors` löschen. Der Baum bleibt an derselben Stelle wie heute.
- [ ] **Schritt 3:** `npx vitest run src/components/RequirementEditors` — bestehende Tests bleiben
  grün, G.1 ist weiterhin rot (Dialog fehlt noch).
- [ ] **Schritt 4:** Commit `refactor: drop the group panel slot from RequirementList`.

### Task G.3: Toolbar-Aktion und Dialog auf Seitenebene

**Dateien:**
- Modify: `frontend/src/components/RequirementEditors/RequirementEditors.tsx`

**Schnittstellen:**
- `ListToolbar` erhält `actions` (gerendert in der Filterzeile, `ListToolbar.tsx:134-142`):
  ```tsx
  actions={hasRole('editor') ? (
    <button type="button" className="btn-ghost" data-testid="req-list-groups-btn"
            aria-haspopup="dialog" onClick={() => setGroupManagerOpen(true)}>
      <Layers aria-hidden="true" size={14} /> {t('groups.manage')}
    </button>
  ) : undefined}
  ```
- Dialog **außerhalb** von `leftPanel` (Geschwister von `splitWrapper`), damit das `overflow` der
  SplitView-Spalte ihn nicht beschneidet:
  ```tsx
  {isGroupManagerOpen && (
    <Dialog title={t('groups.title')} description={t('groups.dialogHint')}
            size="lg" testId="group-manager-dialog"
            onClose={() => setGroupManagerOpen(false)}>
      <GroupManager … />
    </Dialog>
  )}
  ```
- `GroupManager` selbst bleibt unverändert (Props wie heute aus `requirementGroups`).

- [ ] **Schritt 1:** Zustand + Button + Dialog einbauen; G.1 grün bekommen.
- [ ] **Schritt 2:** `npx vitest run src/components/RequirementEditors` — grün.
- [ ] **Schritt 3:** Sichtprüfung im Dev-Stack: Dialog öffnet/schließt, Escape, Fokus zurück,
  Baum beginnt direkt unter der Toolbar.
- [ ] **Schritt 4:** Commit `feat: open group administration from the requirement toolbar`.

### Task G.4: `AddToGroupDialog` und Zeilenaktion

**Dateien:**
- Neu: `frontend/src/components/RequirementEditors/AddToGroupDialog.tsx` (+ `.module.css`)
- Modify: `RequirementList.tsx` (`renderRow`, neben dem Lösch-Trigger `:699-720`)
- Test: `AddToGroupDialog.test.tsx`

**Schnittstellen:**
```ts
export interface AddToGroupDialogProps {
  requirementId: string;                  // Requirement-ENTITÄT (nicht Artifact)
  requirementTitle: string;
  groups: GroupManagerGroup[];            // dieselbe Sicht wie GroupManager
  onAdd: (groupId: string, requirementId: string) => Promise<void>;
  onClose: () => void;
}
```
- Zeilenaktion `data-testid="req-row-group-<id>"`, nur `hasRole('editor')`, `title`/`aria-label` aus
  `groups.addToGroup`; `stopPropagation`, damit der Klick nicht die Zeile selektiert (Muster des
  Lösch-Triggers).

- [ ] **Schritt 1:** Failing tests: `renders_one_entry_per_group`, `already_member_is_checked_and_disabled`,
  `calls_on_add_with_entity_id`, `shows_error_and_stays_open_on_rejection`.
- [ ] **Schritt 2:** `npx vitest run src/components/RequirementEditors/AddToGroupDialog.test.tsx`; FAIL.
- [ ] **Schritt 3:** Komponente implementieren (Dialog-Primitive, `Checkbox`-Liste, `role="alert"`
  bei Fehler). In `RequirementList` die Zeilenaktion + Dialogzustand ergänzen.
- [ ] **Schritt 4:** PASS; `npx vitest run src/components/RequirementEditors` für Regressionen.
- [ ] **Schritt 5:** Commit `feat: add requirements to a group from the tree row`.

### Task G.5: Mitgliedschaft per Drag auf den Gruppen-Ordner

**Dateien:**
- Modify: `frontend/src/components/shared/WorkspaceTree/workspace-tree.tsx` (Prop `onAddToGroup`),
  `tree-drag.ts` (Drop-Klassifikation), ggf. `tree-groups.ts` (Helfer „ist Mitglied")
- Modify: `RequirementEditors.tsx` (Verdrahtung auf `requirementGroups.addMember`)
- Test: `workspace-tree.groups.test.tsx` (bestehende Datei erweitern)

**Schnittstellen:**
```ts
/**
 * P6-Nachtrag: Zeile auf einen Gruppen-Ordner ziehen legt die Mitgliedschaft an.
 * Nur aufgerufen, wenn der gezogene Knoten noch NICHT Mitglied dieser Gruppe ist;
 * ein Drop eines Mitglieds bleibt onReorderGroupMember.
 */
onAddToGroup?: (groupId: string, nodeId: string) => Promise<void>;
```
- Abgrenzung muss in `tree-drag.ts` passieren, nicht im Renderer: die Drop-Klassifikation entscheidet
  „Reorder innerhalb der Gruppe" vs. „Beitritt". Ohne `onAddToGroup` unverändertes Verhalten.

- [ ] **Schritt 1:** Failing tests: `drop_non_member_on_folder_calls_on_add_to_group`,
  `drop_member_on_folder_still_calls_on_reorder_group_member`,
  `drop_on_folder_without_callback_is_ignored` (Architektur/Needs bleiben unberührt).
- [ ] **Schritt 2:** `npx vitest run src/components/shared/WorkspaceTree/workspace-tree.groups.test.tsx`; FAIL.
- [ ] **Schritt 3:** Prop + Klassifikation implementieren; Ordner zeigt während des Drags
  `data-drop-kind="group"` (CSS-Modifier analog `elementNodeDropTarget`). Optimistisches Update mit
  Rollback bei Rejection (Muster `onReorderGroupMember`).
- [ ] **Schritt 4:** PASS; `npx vitest run src/components/shared/WorkspaceTree`.
- [ ] **Schritt 5:** Commit `feat: add tree rows to a group by dropping them on the folder`.

### Task G.6: i18n

**Dateien:** `frontend/src/i18n/locales/de.json`, `en.json`

**Schnittstellen:** Schlüssel aus Spec §7: `groups.manage`, `groups.dialogHint`, `groups.addToGroup`,
`groups.addToGroupTitle`, `groups.alreadyMember`, `groups.addSelected`.

- [ ] **Schritt 1:** Beide Dateien im selben Commit ergänzen (Paritätstest).
- [ ] **Schritt 2:** `npx vitest run src/i18n/locales.test.ts`; PASS.
- [ ] **Schritt 3:** Commit `feat(i18n): add group administration labels`.

### Task G.7: E2E

**Dateien:** Neu `e2e/tests/requirement-groups.spec.ts`

- [ ] **Schritt 1:** Spec schreiben (Muster `e2e/tests/connection-view.spec.ts`: eigener Workspace
  je Test, REST-Fixtures über `request`). Fälle: Dialog öffnen/anlegen/schließen mit Fokus-Rückgabe;
  Zeilenaktion ordnet zu; „Gruppen anzeigen" zeigt den Ordner mit Zähler; Viewer sieht die Aktionen
  nicht.
- [ ] **Schritt 2:** `cd e2e && node node_modules/@playwright/test/cli.js test --list tests/requirement-groups.spec.ts`
  (Validierung ohne Stack).
- [ ] **Schritt 3:** Mit laufendem Stack: `cd e2e && npx playwright test tests/requirement-groups.spec.ts`.
- [ ] **Schritt 4:** Commit `test(e2e): cover requirement group administration`.

### Task G.8: Phasenabschluss

- [ ] **Schritt 1:** `cd frontend && npm run lint && npm run build` (tsc + vite).
- [ ] **Schritt 2:** `npx vitest run src/components/RequirementEditors src/components/shared/WorkspaceTree`.
- [ ] **Schritt 3:** `npx vitest run src/test/ui-ratchet.test.ts` (keine neuen Inline-Styles).
- [ ] **Schritt 4:** Branch `feat/group-admin-dialog` pushen, PR mit Verweis auf die Spec (§4, G).

---

# Phase V2 — Leseobjekt: Arten trennen, Ordnung nachziehen

**Ziel:** `allocation-view` liefert Requirements und Elemente getrennt (kein gemeinsamer 500er-Deckel,
`element_subtree` wirkt auf beide), Element-Zeilen tragen ihren `sort_key`.
**Spec:** B‑1, B‑2, B‑3, §5.7.

### Task V2.1: Backend-Tests zuerst

**Dateien:** Modify `backend/application/tests/test_allocation_view.py`

- [ ] **Schritt 1:** Failing tests: `test_kind_requirement_returns_only_requirements`,
  `test_kind_element_returns_only_elements`, `test_kind_does_not_change_meta`,
  `test_unknown_kind_is_400`, `test_element_rows_carry_artifact_sort_key`,
  `test_element_without_artifact_row_has_null_sort_key`,
  `test_element_catalog_survives_more_than_500_requirements` (600 Requirements + 20 Elemente),
  `test_element_subtree_limits_element_rows`.
- [ ] **Schritt 2:** `cd backend && pytest application/tests/test_allocation_view.py -v`; FAIL.
- [ ] **Schritt 3:** Commit `test: pin kind split and element order in the allocation view`.

### Task V2.2: `kind` im Service

**Dateien:** Modify `backend/application/allocation_view_service.py`

**Schnittstellen:**
- `list(..., kind: str | None = None)`; unbekannter Wert → `ValidationError` (→ 400 über
  `rest_api/views.py:8304-8310`).
- Filterung **nach** `matches()`, **vor** dem Slice; `meta` bleibt aus `filtered`:
  ```python
  filtered = [row for row in rows if matches(row)]
  visible = [row for row in filtered if kind is None or row["kind"] == kind]
  return {"results": visible[offset:offset + page_size], "meta": {...}}
  ```
- `kind` gehört **nicht** in `matches()`.

- [ ] **Schritt 1:** Parameter, Prüfung und Slice umbauen.
- [ ] **Schritt 2:** Der Controller muss den Parameter durchreichen: `rest_api/views.py`
  `params.get("kind")` in `AllocationViewService().list(...)`.
- [ ] **Schritt 3:** `pytest application/tests/test_allocation_view.py -v`; PASS.
- [ ] **Schritt 4:** Commit `feat: filter the allocation view by row kind`.

### Task V2.3: `sort_key` für Element-Zeilen

**Dateien:** Modify `backend/application/allocation_view_service.py` (`:58-62`, `:93-98`, `:148-176`)

**Schnittstellen:** `_element_row` liefert `sort_key` des zugehörigen `Artifact` (oder `None`).
Der vorhandene Artefakt-Lookup wird auf Element-Artefakte erweitert:
```python
artifact_rows = {
    row["id"]: row
    for row in Artifact.unscoped.filter(
        id__in=[req["artifact_id"] for req in requirements]
        + [el["artifact_id"] for el in elements]
    ).values("id", "parent_id", "sort_key")
}
```

- [ ] **Schritt 1:** Lookup erweitern, `_element_row` anpassen.
- [ ] **Schritt 2:** `pytest application/tests/test_allocation_view.py -v`; PASS (V2.1-Tests grün).
- [ ] **Schritt 3:** Commit `fix: expose the artifact sort key on allocation view element rows`.

### Task V2.4: Frontend-Reads entdoppeln

**Dateien:**
- Modify: `frontend/src/api/allocation-view.ts` (`kind` in `AllocationViewQuery`)
- Modify: `frontend/src/components/ConnectionView/useAllocationView.ts` (`:251-265`, `:350-357`)
- Test: `useAllocationView.test.ts`

**Schnittstellen:**
```ts
rowsQuery     = allocationViewApi.view(ws, { ...filtersToQuery(filters), kind: "requirement" });
elementsQuery = allocationViewApi.view(ws, { ...filtersToQuery(filters), kind: "element" });
```
- `elements` stammt **ausschließlich** aus `elementsQuery`; der Fallback über `allRows` entfällt.

- [ ] **Schritt 1:** Failing tests: beide Reads tragen `kind`, `elements` enthält auch bei
  `rowsQuery`-Ergebnis ohne Elemente die Elemente, `element_subtree` steht in beiden Queries.
- [ ] **Schritt 2:** `npx vitest run src/components/ConnectionView/useAllocationView.test.ts`; FAIL.
- [ ] **Schritt 3:** Implementieren; `filtersToQuery` bleibt unverändert (kein `kind`-Feld, kein
  URL-Parameter).
- [ ] **Schritt 4:** PASS.
- [ ] **Schritt 5:** Commit `feat: read allocation rows and elements separately`.

### Task V2.5: Phasenabschluss

- [ ] **Schritt 1:** `make test-backend` (sequenziell, isolierter Stack).
- [ ] **Schritt 2:** `cd frontend && npx vitest run src/components/ConnectionView`.
- [ ] **Schritt 3:** Branch `feat/allocation-view-kind`, PR (Phase V2).

---

# Phase V — Verbindungsansicht: zwei Bäume (V1 + V3 gemeinsam)

**Ziel:** `Bäume` ist die Standarddarstellung: Requirements-Baum links, Architektur-Baum rechts, ein
Scroll-Container, Allokationskanten im Korridor, Selektion in den Zeilen, schlanke Filterleiste.
**Spec:** D3, D4, D6–D8, S3–S11, §5.1–§5.8.
**Reihenfolge:** V.1 zuerst (Präferenzen), dann V.2–V.5 (Modell/Renderer), dann V.6–V.9
(Aufräumen), zuletzt V.10/V.11.

### Task V.1: Präferenzschlüssel (B‑4)

**Dateien:**
- Modify: `backend/auth_tenancy/apps.py`
- Modify: `backend/auth_tenancy/tests/test_preference_keys_ordering.py`
- Modify: `frontend/src/api/connection-views.ts`, `connection-views.test.ts`

**Schnittstellen:**
```python
PreferenceKey(key="ui.connection_view.show_edges", value_type="bool", default=True,
              levels=frozenset({PREFERENCE_SCOPE_USER}), mode="override",
              ui_editor="checkbox", owner="P3")
PreferenceKey(key="ui.connection_view.filters_expanded", value_type="bool", default=False,
              levels=frozenset({PREFERENCE_SCOPE_USER}), mode="override",
              ui_editor=None, owner="P3")
```
- Frontend: `loadConnectionPrefs(): Promise<{showEdges: boolean; filtersExpanded: boolean}>` und
  `saveConnectionPrefs(patch)`, beide über `preferenceValuesApi` (`getLevel("user")` /
  `patchLevel("user", …)`), Ladefehler ⇒ Defaults, Schreibfehler ⇒ propagiert (Aufrufer meldet).

- [ ] **Schritt 1:** Failing tests: beide Schlüssel registriert, nur Nutzer-Ebene schreibbar,
  Defaults `true`/`false`; Frontend: Laden ohne Schlüssel ⇒ Defaults, `save` schreibt genau einen
  Schlüssel.
- [ ] **Schritt 2:** `pytest auth_tenancy/tests/test_preference_keys_ordering.py -v`; FAIL.
- [ ] **Schritt 3:** Registrierung + Frontend-API implementieren (Reihenfolge der `PreferenceKey`-
  Einträge: zusammen mit den bestehenden `ui.connection_view.*`).
- [ ] **Schritt 4:** Backend- und Frontend-Tests PASS.
- [ ] **Schritt 5:** Commit `feat: add connection view display preferences`.

### Task V.2: `useAllocationSelection`

**Dateien:** Neu `frontend/src/components/ConnectionView/useAllocationSelection.ts` (+ Test)

**Schnittstellen:**
```ts
export interface AllocationSelection {
  selectableIds: ReadonlySet<string>;   // gefiltert + nicht gesperrt
  selectedRows: AllocationRow[];
  isSelected: (id: string) => boolean;
  toggle: (id: string) => void;
  selectAll: () => void;
  clear: () => void;
}
export function useAllocationSelection(requirements: readonly AllocationRow[]): AllocationSelection;
```

- [ ] **Schritt 1:** Failing tests: `selection_survives_filter_change`,
  `locked_rows_are_not_selectable`, `select_all_uses_visible_rows_only`,
  `toggle_ignores_locked_id`, `clear_empties_selection`.
- [ ] **Schritt 2:** `npx vitest run src/components/ConnectionView/useAllocationSelection.test.ts`; FAIL.
- [ ] **Schritt 3:** Hook implementieren (Logik aus `AllocationAssistant.tsx:94-154` übernehmen und
  von UI entkoppeln).
- [ ] **Schritt 4:** PASS.
- [ ] **Schritt 5:** Commit `refactor: lift allocation selection out of the assistant`.

### Task V.3: Baum- und Kantenmodell

**Dateien:** Neu `frontend/src/components/ConnectionView/allocation-trees.ts` (+ `.test.ts`)

**Schnittstellen:**
```ts
export interface AllocationRequirementNode {
  row: AllocationRow; children: AllocationRequirementNode[]; depth: number;
}
export function buildRequirementTree(requirements: readonly AllocationRow[]): AllocationRequirementNode[];
export function buildElementTree(elements: readonly AllocationRow[]): AllocationRequirementNode[];
export interface AllocationEdge { requirementId: string; elementId: string }
export function buildAllocationEdges(
  requirements: readonly AllocationRow[], elements: readonly AllocationRow[],
): AllocationEdge[];
```
- Eltern: Requirements über `requirementByArtifact.get(row.parent_id)`, Elemente über
  `parent_id` (Entitäts-Id). Fehlender Elternknoten ⇒ Wurzel.
- Sortierung: `compareRows` aus `useAllocationView.ts:189-194` wiederverwenden (`null` zuletzt) —
  **nicht** `compareElementRows` aus `TreeRenderer.tsx:40-45`.
- Zyklen/Duplikate: besuchte Menge wie `buildGraph.ts:246-277`.

- [ ] **Schritt 1:** Failing tests: `builds_requirement_hierarchy`, `missing_parent_becomes_root`,
  `null_sort_key_sorts_last`, `cycles_terminate`, `edges_resolve_artifact_to_entity_id`,
  `edge_dropped_when_element_missing`, `one_edge_per_requirement`.
- [ ] **Schritt 2:** `npx vitest run src/components/ConnectionView/allocation-trees.test.ts`; FAIL.
- [ ] **Schritt 3:** Implementieren (pur, ohne React).
- [ ] **Schritt 4:** PASS.
- [ ] **Schritt 5:** Commit `feat: build the requirement and element trees for the connection view`.

### Task V.4: Kantengeometrie

**Dateien:** Neu `frontend/src/components/ConnectionView/edge-geometry.ts` (+ `.test.ts`)

**Schnittstellen:**
```ts
export interface RowRect { top: number; height: number }
export interface EdgePath { id: string; d: string }
export function buildEdgePaths(
  edges: readonly AllocationEdge[],
  from: ReadonlyMap<string, RowRect>,
  to: ReadonlyMap<string, RowRect>,
  gutter: { x1: number; x2: number },
): EdgePath[];
```
- Stabile Reihenfolge nach `requirementId`; fehlende Enden ⇒ keine Kante; kubische Bézier von der
  rechten Kante der Requirement-Zeile zur linken Kante der Element-Zeile.

- [ ] **Schritt 1:** Failing tests: `produces_one_path_per_resolved_edge`,
  `skips_edges_with_missing_endpoint`, `order_is_stable`, `path_stays_inside_gutter`.
- [ ] **Schritt 2:** FAIL. **Schritt 3:** Implementieren. **Schritt 4:** PASS.
- [ ] **Schritt 5:** Commit `feat: compute allocation edge paths for two trees`.

### Task V.5: Renderer `AllocationTreesRenderer`

**Dateien:**
- Neu: `AllocationTreesRenderer.tsx`, `AllocationTreesRenderer.module.css` (oder Erweiterung von
  `ConnectionView.module.css`)
- Test: `AllocationTreesRenderer.test.tsx`

**Schnittstellen:**
```ts
export interface AllocationTreesRendererProps {
  requirements: AllocationRow[];
  elements: AllocationRow[];
  selection: AllocationSelection;
  canEdit: boolean;
  showEdges: boolean;
  allocate: (requirementId: string, elementId: string) => Promise<void>;
  deallocate: (allocationTraceLinkId: string) => Promise<void>;
}
```
- Ein Scroll-Container, `display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr)`;
  `position: relative` für das Overlay; SVG `aria-hidden="true"`.
- Zeilen einzeilig (~28 px), Testids: `data-alloc-row` (Messanker), `alloc-select-<id>`,
  `alloc-target-<id>` / `alloc-target-external-<id>` / `unallocated-marker-<id>`,
  `allocate-open-<id>`, `deallocate-<id>`, `element-count-<id>`, `req-locked-<id>`,
  `allocation-edge-<requirementId>`.
- Auf-/Zuklappen über `<button aria-expanded aria-controls>`; Fokus = Hervorhebung.
- Messung: `useLayoutEffect` + `getBoundingClientRect()` relativ zum Container, gedrosselt über
  `requestAnimationFrame`, Neuberechnung bei `scroll`/`resize`/Toggle/Filterwechsel; kein
  `setState` pro Scroll-Event (Ref + ein Rerender pro Frame).
- Gesperrte Requirements nicht ziehbar/selektierbar, gesperrte Elemente bleiben Ziel (E6).
- Kein `WorkspaceTree`-Umbau (Spec §5.3 Begründung).

- [ ] **Schritt 1:** Failing tests: `renders_both_columns_with_hierarchy`,
  `checkbox_uses_entity_id`, `shows_target_text`, `renders_one_edge_per_allocation`,
  `hide_edges_removes_svg_but_keeps_target_text`, `drop_calls_allocate_with_entity_ids`,
  `locked_requirement_is_not_draggable`, `keyboard_path_opens_element_picker`.
- [ ] **Schritt 2:** `npx vitest run src/components/ConnectionView/AllocationTreesRenderer.test.tsx`; FAIL.
- [ ] **Schritt 3:** Implementieren (Overlay als eigene kleine Unterkomponente im selben Modul).
- [ ] **Schritt 4:** PASS.
- [ ] **Schritt 5:** Commit `feat: add the two-tree allocation renderer`.

### Task V.6: Assistant verschlanken

**Dateien:**
- Modify: `AllocationAssistant.tsx` (`:94-154` Selektion raus, `:382-438` Liste raus)
- Modify: `AllocationAssistant.test.tsx`
- Modify: `ConnectionView.tsx` (Props, Hook-Einbindung)

**Schnittstellen:** Props `selection: AllocationSelection`, `requirements`, `elements`,
`allocateBulk`, `suggestArchitecture`, `canEdit`. Behaltene Testids: `assistant-selection-count`,
`assistant-select-all`, `assistant-allocate`, `assistant-suggest`, `assistant-notice`,
`assistant-error`, `assistant-suggestions`, `assistant-suggestion-confirm`.
Entfallen: `assistant-row-<id>`, `assistant-check-<id>`, `assistant-lock-<id>`,
`assistant-empty` (die Zeile lebt jetzt im Baum).

- [ ] **Schritt 1:** Tests umbauen: `allocate_disabled_without_selection`,
  `suggest_works_without_selection`, `suggestion_flow_unchanged`, `bulk_allocate_payload_unchanged`.
- [ ] **Schritt 2:** `npx vitest run src/components/ConnectionView/AllocationAssistant.test.tsx`; FAIL.
- [ ] **Schritt 3:** Komponente auf Aktionsleiste reduzieren.
- [ ] **Schritt 4:** PASS.
- [ ] **Schritt 5:** Commit `refactor: reduce the allocation assistant to its action bar`.

### Task V.7: Filterleiste

**Dateien:**
- Modify: `FilterBar.tsx`, `ConnectionView.tsx`, `ConnectionView.module.css`
- Neu: `FilterBar.test.tsx`

**Schnittstellen:** Props `filtersExpanded: boolean`, `onToggleExpanded: () => void`,
`activeExtraFilterCount: number`. Zeile 1: Schnellfilter + Suche + `Weitere Filter (n)` + Kennzahlen
(`counter-*` unverändert). Popover `data-testid="filter-more"` enthält die bisherigen Freifilter und
gespeicherten Sichten.

- [ ] **Schritt 1:** Failing tests: `starts_collapsed_by_default`, `starts_expanded_from_preference`,
  `badge_counts_active_extra_filters`, `toggle_keeps_filter_values`, `save_failure_keeps_local_state`.
- [ ] **Schritt 2:** FAIL. **Schritt 3:** Implementieren; Zustand aus V.1 laden/schreiben.
- [ ] **Schritt 4:** PASS. **Schritt 5:** Commit `feat: collapse the connection view filter bar`.

### Task V.8: Modus-Set, Default, URL, Kanten-Schalter

**Dateien:**
- Modify: `useAllocationView.ts` (`ConnectionViewMode`, `parseConnectionView`, `setView`),
  `ConnectionView.tsx`, `useAllocationView.test.ts`, `ConnectionView.test.tsx`

**Schnittstellen:**
```ts
export type ConnectionViewMode = "trees" | "architecture" | "two-column" | "matrix" | "graph";
// "architecture" | "tree" -> "architecture"; "trees" | fehlt -> "trees"
```
- Umschaltleiste fünf Einträge, Testids `view-switch-trees`, `view-switch-architecture`,
  `view-switch-two-column`, `view-switch-matrix`, `view-switch-graph`.
- Kopfzeilenschalter `trees-edges-toggle` mit `show_edges`-Präferenz.

- [ ] **Schritt 1:** Failing tests: Default ohne `view` ist `trees`; `tree` → `architecture`;
  `two-column` bleibt `two-column`; `setView("trees")` schreibt keinen Parameter;
  `show_edges=false` blendet das Overlay aus (Renderer-Mock).
- [ ] **Schritt 2:** FAIL. **Schritt 3:** Implementieren; `trees` rendert `AllocationTreesRenderer`,
  `architecture` weiterhin `TreeRenderer` (unverändert).
- [ ] **Schritt 4:** PASS. **Schritt 5:** Commit `feat: make the two-tree view the connection default`.

### Task V.9: „Nicht allokiert" als Markierung

**Dateien:** Modify `AllocationTreesRenderer.tsx` (Markierungen), `ConnectionView.tsx` (kein Block
mehr in `trees`)

- [ ] **Schritt 1:** Sicherstellen, dass in `trees` **kein** `unallocated-block`/`unallocated-count`
  gerendert wird, die Markierungen aber vorhanden sind (in V.5 bereits angelegt — hier der
  Nachweis-Test).
- [ ] **Schritt 2:** `npx vitest run src/components/ConnectionView`; PASS.
- [ ] **Schritt 3:** Commit `feat: mark unallocated requirements inline instead of a block`.

### Task V.10: E2E

**Dateien:**
- Modify: `e2e/tests/connection-view.spec.ts` (5 Zeilen: `unallocated-count` → `counter-unallocated`
  in 88/103; `assistant-check-` → `alloc-select-` in 90/91/139)
- Neu: `e2e/tests/connection-trees.spec.ts`

- [ ] **Schritt 1:** Bestehende Spec anpassen; neue Spec schreiben: zwei Bäume sichtbar,
  `allocation-edge-<id>` vorhanden, Klick betont Gegenstück, Drag allokiert, Tastaturpfad allokiert,
  `trees-edges-toggle` schaltet das Overlay ab, Zieltext bleibt.
- [ ] **Schritt 2:** `cd e2e && node node_modules/@playwright/test/cli.js test --list tests/connection-trees.spec.ts tests/connection-view.spec.ts`.
- [ ] **Schritt 3:** Mit Stack: `cd e2e && npx playwright test tests/connection-trees.spec.ts tests/connection-view.spec.ts`.
- [ ] **Schritt 4:** Commit `test(e2e): cover the two-tree connection view`.

### Task V.11: Phasenabschluss

- [ ] **Schritt 1:** `cd frontend && npm run lint && npm run build`.
- [ ] **Schritt 2:** `npx vitest run src/components/ConnectionView src/test/ui-ratchet.test.ts src/i18n/locales.test.ts`.
- [ ] **Schritt 3:** `make test-frontend` und `make test-backend` (sequenziell).
- [ ] **Schritt 4:** Sichtprüfung im Dev-Stack bei 1280 px und 1920 px, hell und dunkel; Kanten
  liegen im Korridor, nichts überlappt bei zugeklappten Zweigen.
- [ ] **Schritt 5:** Branch `feat/connection-two-trees`, PR mit Verweis auf Spec §5 und Phase V.
- [ ] **Schritt 6 (erst nach Freigabe, eigener Commit):** §6.2 der Vorlagenspezifikation auf den
  neuen Default umstellen und dort auf diese Spezifikation verweisen (D9/O5). **Nicht** Teil des
  PR, solange die Freigabe fehlt.

---

## Nicht in diesem Plan

- Änderungen an Allokations-Semantik, N:1-Index, Sperrregeln, `allocation_intent` (Vorlagenspez).
- Neue REST-Routen oder MCP-Tools, Manifest-Änderungen.
- Ein Umbau von `WorkspaceTree` zu einem Zwei-Spalten-Baum (bewusst: eigener Renderer).
- Virtualisierung in der `Bäume`-Ansicht (Spec §9 begründet den Verzicht; der 500er-Deckel je Art
  ist die Obergrenze).
- Ein Tab „Gruppen" im Detailbereich (durch D5 entschieden: Dialog).
