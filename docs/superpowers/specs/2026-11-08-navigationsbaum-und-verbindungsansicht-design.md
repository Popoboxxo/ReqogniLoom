---
type: Spec
title: "Navigationsbaum entlasten und Verbindungsansicht als zwei Bäume"
status: draft
date: 2026-11-08
author_agent: opencode (DeepSeek V4.1 Flash), aus der Analyse mit dem Product Owner
language: de
related_specs: ["2026-11-04-ordnung-allokation-design.md"]
supersedes_in_part: ["2026-11-04-ordnung-allokation-design.md §6.2 — nur die Default-Darstellung der Verbindungs-Ansicht (D4)"]
evidence: "Ist-Stand am 2026-11-08 gegen den Arbeitsstand im Repo geprüft; Belege als `pfad:zeile`"
---

# Navigationsbaum entlasten und Verbindungsansicht als zwei Bäume

> **Status: Entwurf zur Freigabe.** Die fünf offenen Fragen (O1–O5) wurden am 2026-11-08 entschieden
> (Protokoll in §3.3); die Festlegungen in §3.2 sind damit gesetzt und nicht mehr Vorschlag.
> Abschnitte, die eine bestehende Zusage ändern, sind mit **ÄNDERT** markiert.
>
> **Umsetzungsplan:** [`docs/plans/2026-11-08-navigationsbaum-und-verbindungsansicht.md`](../../plans/2026-11-08-navigationsbaum-und-verbindungsansicht.md)
> (Phasen G, V2, V — geschrieben, nicht umgesetzt).

## 1. Ziel

Zwei zusammenhängende Navigationsprobleme, ein gemeinsames Prinzip: **Navigation bleibt Navigation.**

1. **Requirements-Route.** Die linke Spalte ist heute kein Navigationsbaum mehr, sondern ein
   Stapel aus Baum + dauerhaft gemounteter Gruppenverwaltung. Sie soll wieder nur Baum sein; die
   Gruppenverwaltung bleibt erreichbar, kostet aber im Ruhezustand keine Höhe.
2. **Verbindungs-Route.** Die Ansicht zeigt heute wahlweise einen reinen Architektur-Baum mit
   flachen Requirements darunter, zwei flache Spalten, eine Matrix oder einen Karten-Graph — aber
   nicht die naheliegende Form: **Requirements-Baum und Architektur-Baum nebeneinander, mit den
   Allokationen als Verbindungen dazwischen.** Diese Form wird die Standarddarstellung.

Das mentale Modell des Product Owners: *„eine Verbindung aus dem Navigationsbaum von Architecture
und Requirement"*. Es existiert im Code bereits als Karten-Graph (`buildGraph.ts:497-548`), aber
als vierte Ansicht hinter einem Umschalter und in Kartenform statt in Baumform.

### Nicht-Ziele

- Keine neuen Allokations-Semantiken: N:1, `TraceLink(allocated-to)` als einzige Wahrheit, Sperre
  aus `freeze_on_enter` — alles unverändert (E3, E4, E6 der Vorlagenspezifikation).
- Keine neue Persistenz, keine Migration, kein neues ADR.
- Keine Änderung an Requirements-Detailformular, Trace-Panel, AI-Aktionen oder RightSidebar.
- Keine Änderung an Architektur-Route, Needs, Tests, ADRs.
- Gruppen bleiben rein visuell (V7). Diese Spezifikation fügt ihnen **keine** Semantik hinzu.

### Anti-Ziele (wäre ein Fehlschlag, auch wenn es technisch funktioniert)

- Die Gruppenverwaltung wird nur „nach unten geschoben" und ist weiterhin dauerhaft sichtbar.
- Die neue Verbindungsansicht zeigt zwei Listen, die man auch einzeln aufklappen kann, aber die
  Zuordnung ist nur durch Scrollen und Merken erkennbar.
- Die neue Ansicht wird ein zweiter Karten-Graph mit anderem Namen.
- Der Requirements-Baum in der Verbindungsansicht verliert seine Hierarchie und wird wieder flach.

## 2. Ist-Stand (geprüft 2026-11-08)

### 2.1 Requirements-Route

| Befund | Beleg |
|---|---|
| Die linke Spalte stapelt: Fehlerbanner → „Gelöschte anzeigen" → **Gruppenverwaltung** → Toolbar → Baum | `RequirementEditors.tsx:663-761` |
| `GroupManager` wird als `groupPanel` **vor** die Toolbar in die Liste gehängt | `RequirementList.tsx:447`, `RequirementEditors.tsx:742-754` |
| `GroupManager` ist volles CRUD: Anlegeformular + je Gruppe Titel, Beschreibung, Mitgliederliste, **eigenes Suchfeld**, Trefferliste | `GroupManager.tsx:108-287` |
| Die Verwaltung ist ein Kasten mit Rahmen, Innenabstand und `margin-bottom` — kein einklappbarer Bereich | `GroupManager.module.css:8-17` |
| Die linke Spalte ist per Default 40 % der Fensterbreite (min. 260 px, max. 70 %) | `SplitView.tsx:400`, `RequirementEditors.tsx:948-949` |
| Das *Ergebnis* der Gruppen („Gruppen anzeigen") ist dagegen ein leises Checkbox im Baum | `workspace-tree.tsx:1295-1308` |
| Die Architektur-Route hat an derselben Stelle nur Toggle + Toolbar + Baum — Requirements ist der Ausreißer | `ArchitectureEditors.tsx:776-814` |
| Mitgliedschaft gibt es nur über das Suchfeld *pro Gruppe*; kein Weg vom ausgewählten Requirement zur Gruppe | `GroupManager.tsx:230-281`, `api/groups.ts` (nur create/list/members) |
| Kein E2E-Test, keine eigene Testdatei für `GroupManager` | `grep group-manager e2e/` → leer |

**Höhenüberschlag** (aus den CSS-Werten, nicht am laufenden System gemessen): Toggle ≈ 28 px,
`GroupManager` ≈ 110 px Grundfläche + ≈ 110 px je Gruppe + ≈ 20 px je Mitglied, Toolbar ≈ 80 px.
Bei drei Gruppen mit je vier Mitgliedern sind das ≈ 800 px vor der ersten Baumzeile — auf einem
1080p-Schirm praktisch der gesamte erste Bildschirm der Spalte.

### 2.2 Verbindungs-Route

| Befund | Beleg |
|---|---|
| Seitenaufbau: Header → `AllocationAssistant` → `FilterBar` → Renderer | `ConnectionView.tsx:160-279` |
| Der Assistant rendert eine **zweite vollständige Liste aller Requirements** (Checkboxen, `max-height: 14rem`, Scroll) — die Selektionsfläche für den Baum darunter | `AllocationAssistant.tsx:382-438` |
| Selektion ist damit an das Panel gebunden, nicht an den Baum: Baumzeilen sind nicht selektierbar | `TreeRenderer.tsx:193-251` |
| Die Filterleiste ist dauerhaft dreizeilig (Schnellfilter, Freifilter, gespeicherte Sichten) | `FilterBar.tsx:68-330`, `ConnectionView.module.css:64-72` |
| Der Baum-Renderer baut **nur** die Architektur-Hierarchie; Requirements sind flache Zeilen unter dem Element | `TreeRenderer.tsx:47-85`, `:303-307` |
| Die `parent_id`-Hierarchie der Requirements liegt im Leseobjekt bereits vor, wird aber nicht genutzt | `allocation_view_service.py:124-126` |
| „Nicht allokiert" ist ein Block **unter** dem gesamten Baum | `TreeRenderer.tsx:345-378` |
| Element-Zeilen haben **kein** `sort_key` → Geschwister sind alphabetisch statt in Baum-Reihenfolge | `allocation_view_service.py:154` |
| Der Vergleich `sort_key ?? ""` sortiert Zeilen ohne Schlüssel **zuerst** — die Vorlagenspezifikation fordert „NULL zuletzt" (B4) | `TreeRenderer.tsx:40-45`, `TwoColumnRenderer.tsx:22-27` |
| „Element-Teilbaum" filtert Requirements, aber nie den Baum: Elemente kommen aus einem zweiten, ungefilterten Read | `useAllocationView.ts:257-265` |
| Der Element-Katalog ist auf 500 Zeilen gedeckelt; bei > 500 Requirements enthält die Seite **null** Elemente (die Vorlagenspezifikation nennt 717 Requirements) | `useAllocationView.ts:51, 350-357`, `allocation_view_service.py:215-216` |
| Zwei vollständige Reads pro Laden (Zeilen + Elemente), beide ungefiltert/gefiltert gemischt | `useAllocationView.ts:251-265` |
| Der Karten-Graph macht das Gewünschte bereits: zwei Bänder, Hierarchie-Kanten innen, Allokations-Kanten dazwischen | `buildGraph.ts:497-548` |

## 3. Entscheidungen

### 3.1 Vom Product Owner entschieden

| ID | Entscheidung |
|---|---|
| **D1** | Die linke Spalte der Requirements-Route enthält **nur** Navigationsbaum + Suche/Filter. Die Gruppenverwaltung wird aus der Spalte entfernt. |
| **D2** | Die Gruppenverwaltung bleibt vorhanden, wird aber **bei Bedarf eingeblendet** statt dauerhaft gerendert. |
| **D3** | Die Verbindungsansicht bekommt eine Darstellung, die Requirements-Baum und Architektur-Baum **verbindet**. |
| **D4** | Diese Darstellung wird die **Standarddarstellung** der Route. **ÄNDERT** §6.2 der Vorlagenspezifikation (dort ist „Architektur-Baum mit Unterlisten" Default), Inkraftsetzung erst nach Freigabe (O5). |
| **D5** | Gruppenverwaltung als **modaler Dialog**, nicht als Tab und nicht als einklappbarer Bereich (Antwort zu O1, 2026-11-08). |
| **D6** | `Zwei Spalten` **bleibt** als eigener Modus erhalten (Antwort zu O2). Die Modus-Menge hat damit fünf Einträge. |
| **D7** | Die Kantendarstellung ist **abschaltbar als Nutzerpräferenz** (Antwort zu O3). |
| **D8** | Der Aufklapp-Zustand von „Weitere Filter" wird **als Nutzerpräferenz** gemerkt (Antwort zu O4). |
| **D9** | §6.2 der Vorlagenspezifikation wird **erst nach Freigabe** dieser Spezifikation geändert (Antwort zu O5). |

### 3.2 Festlegungen dieser Spezifikation

| ID | Festlegung | Begründung |
|---|---|---|
| **S1** | Gruppenverwaltung als **modaler Dialog**, Auslöser ist ein Button „Gruppen…" in der Filterzeile der Listen-Toolbar. | Der Dialog ist die vorhandene Primitive mit Fokusfalle, Escape und Fokus-Rückgabe (`Dialog.tsx:2-36`); im Ruhezustand kostet er 0 px. Ein Drawer bräuchte neue Zustands- und Fokuslogik. |
| **S2** | Zusätzlich zur Suche im Dialog: **Zeilenaktion „Zu Gruppe hinzufügen…"** am Requirements-Knoten (Tastaturpfad) und **Drag einer Baumzeile auf einen Gruppen-Ordner** (Zeigerpfad), beides nur bei aktivierter Gruppenansicht bzw. für Editoren. | Der Nutzer steht im Baum, wenn er gruppieren will. Der heutige Weg (Dialog öffnen, Gruppe suchen, Mitglied suchen) ist die Umkehrung der Arbeitsrichtung. |
| **S3** | Die Modus-Menge wird `Bäume` (neu, Default) · `Architektur` (bisher `tree`, unverändert) · `Zwei Spalten` (unverändert) · `Matrix` · `Graph`. | D6: die flache Variante bleibt, weil sie getestet und billig ist; `Bäume` ersetzt sie nicht, sondern ergänzt sie um Hierarchie. |
| **S4** | Alt-URLs bleiben gültig: `view=tree` → `architecture`, alle anderen Werte unverändert, ohne `view` → `trees`. Gespeicherte Sichten funktionieren weiter. | Gespeicherte Sichten liegen als rohe Query-Parameter in den Nutzerpräferenzen (`ConnectionView.tsx:141-154`). |
| **S5** | Der Assistant verliert seine Liste, behält aber seine Identität (Bulk-Allokation + Vorschläge) und wird zu einer **einseitigen Aktionsleiste** (~40 px) über der Ansicht. | Die Aktion bleibt dort, wo sie war; nur die redundante Liste verschwindet. `assistant-*`-Testids der Aktionen bleiben. |
| **S6** | Die Filterleiste wird **einfach**: Schnellfilter + Suche in Zeile 1, alles Übrige hinter „Weitere Filter" (Popover). Der Aufklapp-Zustand ist eine Nutzerpräferenz (D8), die Filterwerte bleiben in der URL. | Filter bleiben vollständig; die URL bleibt die Wahrheit für den *Wert*, die Präferenz für die *Sichtbarkeit*. |
| **S7** | „Nicht allokiert" verschwindet als Block am Seitenende. Nicht allokierte Requirements tragen eine **Markierung an der Zeile**; der Schnellfilter `allocated=false` und die Kennzahl bleiben. | Der Block ist ein zweiter Ort für dieselbe Information und war der Hauptgrund für die lange Scrollstrecke. |
| **S8** | Der Requirements-Baum der neuen Ansicht nutzt die vorhandene `parent_id`-Hierarchie und sortiert Geschwister nach `sort_key` (NULL zuletzt). | Das Leseobjekt liefert beides bereits; die Vorlagenspezifikation fordert die Ordnung (B4). |
| **S9** | Allokations-Verbindungen werden als **SVG-Overlay** zwischen den beiden Spalten gezeichnet, ausschließlich für aktuell gemountete Zeilen. Ein Schalter „Verbindungen anzeigen" in der Kopfzeile schaltet sie ab (D7). | Die Hierarchie steckt schon in der Einrückung; nur die spaltenübergreifende Kante braucht eine Linie. |
| **S10** | Die beiden Bäume teilen sich **einen** Scroll-Container (Grid mit zwei Spalten). | Damit entfällt Scroll-Synchronisation, und die Kantengeometrie bleibt ohne Nachrechnen stabil. |
| **S11** | Beide Schalter liegen im Präferenzspeicher auf **Nutzer-Ebene** (`ui.connection_view.*`), nicht in der URL und nicht in den Workspace-Einstellungen. | Sie sind Lesehilfen einer Person; das Muster existiert bereits für die gespeicherten Sichten und die Seitenleisten-Gruppen (`auth_tenancy/apps.py:88-113`). |

### 3.3 Entscheidungsprotokoll (2026-11-08)

| Frage | Antwort | Wirkt in |
|---|---|---|
| **O1** Gruppenverwaltung: Dialog, Tab oder einklappbar? | Modaler Dialog | D5, §4, S1 |
| **O2** Darf `Zwei Spalten` entfallen? | Nein, bleibt als fünfter Modus | D6, S3, §5.2 |
| **O3** Kanten abschaltbar? | Ja, als Nutzerpräferenz | D7, S9, S11, §5.1, §5.7 (B-4) |
| **O4** „Weitere Filter"-Zustand merken? | Ja, als Nutzerpräferenz | D8, S6, S11, §5.5, §5.7 (B-4) |
| **O5** §6.2 sofort ändern? | Erst nach Freigabe | D9, §11 |

Damit sind alle früheren Annahmen A1–A3 entschieden; es bleiben keine offenen Annahmen in dieser
Spezifikation.

## 4. Teil A — Requirements-Route: Navigationsspalte entlasten

### 4.1 Zielbild

```
PageHeader  (Titel, Anzahl, „+ Neue Anforderung", Overflow)
┌ Navigationsspalte (~40 %) ────────┬ Detail (~60 %) ───────────────────┬ Versionen ┐
│ [Suche ……………………] [Gruppen…]      │ TraceSpine                        │          │
│ [Kategorie ▾] [Status ▾] [Sort ▾] │ Formular                          │          │
│ □ Gelöschte anzeigen               │ Custom Fields                     │          │
│ □ Gruppen anzeigen                │ Trace-Links                       │          │
│ ▾ Requirements-Baum               │ AI-Aktionen, Similar, Gedächtnis  │          │
│   ▸ …                             │                                   │          │
└───────────────────────────────────┴───────────────────────────────────┴──────────┘
```

Der Requirements-Baum beginnt direkt unter der Toolbar. Die Gruppenverwaltung ist **nicht
gemountet**, solange der Dialog zu ist.

### 4.2 Komponentenverträge

**`RequirementEditors.tsx`**

- `RequirementList` erhält **kein** `groupPanel` mehr; der Prop wird entfernt
  (`RequirementList.tsx:268-273`, `:447`) — inklusive der Docstrings, die ihn erklären.
- Neuer Zustand `isGroupManagerOpen: boolean` (Default `false`).
- `ListToolbar` bekommt `actions`:
  ```tsx
  actions={hasRole('editor') ? (
    <button type="button" className="btn-ghost" data-testid="req-list-groups-btn"
            aria-haspopup="dialog" onClick={() => setGroupManagerOpen(true)}>
      <Layers aria-hidden="true" size={14} /> {t('groups.manage')}
    </button>
  ) : undefined}
  ```
  Hinweis: `ListToolbar` rendert `actions` heute **nur innerhalb der Filterzeile** und nur, wenn
  `hasFilterRow` true ist (`ListToolbar.tsx:134-142`). Requirements erfüllt beides; der Vertrag
  wird nicht geändert.
- Der Dialog wird auf **Seitenebene** gerendert (nicht in `leftPanel`), damit er nicht am
  `overflow` der SplitView-Spalte hängt:
  ```tsx
  {isGroupManagerOpen && (
    <Dialog
      title={t('groups.title')}
      description={t('groups.dialogHint')}
      size="lg"
      testId="group-manager-dialog"
      onClose={() => setGroupManagerOpen(false)}
    >
      <GroupManager … />
    </Dialog>
  )}
  ```
  `GroupManager` selbst bleibt **unverändert** (API, Testids, Suche je Gruppe). Der Dialog liefert
  Fokusfalle, Escape und Fokus-Rückgabe (`Dialog.tsx:2-36`).

**`AddToGroupDialog`** (neu, `RequirementEditors/AddToGroupDialog.tsx`)

```ts
export interface AddToGroupDialogProps {
  requirementId: string;
  requirementTitle: string;
  groups: GroupManagerGroup[];          // dieselbe Sicht, die der GroupManager nutzt
  onAdd: (groupId: string, requirementId: string) => Promise<void>;
  onClose: () => void;
}
```

- Listet die Gruppen mit Checkbox (`group-add-member-<groupId>`); bereits zugeordnete Gruppen sind
  angehakt und deaktiviert (kein Doppel-Add).
- Eine Aktion pro Zeile, kein Freitext. Schließen über Escape/Dialog-Chrome.
- Wird über die Zeilenaktion geöffnet (siehe 4.3).

**`WorkspaceTree` — Mitgliedschaft per Drag** (additiv)

```ts
/**
 * P6-Nachtrag: eine Baumzeile auf einen Gruppen-Ordner ziehen legt die
 * Mitgliedschaft an (statt sie umzusortieren). Nur aufgerufen, wenn das
 * gezogene Element noch nicht Mitglied dieser Gruppe ist; der Aufrufer
 * besitzt den Reload.
 */
onAddToGroup?: (groupId: string, nodeId: string) => Promise<void>;
```

- Wirksam nur, wenn `groups` gesetzt und die Gruppenansicht eingeschaltet ist.
- Abgrenzung zum bestehenden Verhalten: ein Drop eines **Mitglieds** auf einen Ordner bleibt
  `onReorderGroupMember` (`workspace-tree.tsx:845-900`); nur ein Drop eines **Nicht-Mitglieds**
  ruft `onAddToGroup`.
- Ohne `onAddToGroup` verhält sich der Baum exakt wie heute (keine Regression für Architektur,
  Needs, Goals).
- Der Ordner zeigt während des Drags einen Aufnahme-Zustand (`data-drop-kind="group"`), analog zu
  `elementNodeDropTarget` in der Verbindungsansicht.

### 4.3 Interaktion und Tastatur

| Aktion | Zeiger | Tastatur |
|---|---|---|
| Gruppenverwaltung öffnen | Klick auf „Gruppen…" | Tab → Enter |
| Requirement einer Gruppe zuordnen | Baumzeile auf Gruppen-Ordner ziehen | Zeilenaktion „Zu Gruppe hinzufügen…" (`req-row-group-<id>`) → Enter → Checkbox → Enter |
| Gruppe anzeigen/ausblenden | Checkbox „Gruppen anzeigen" (unverändert) | Space |
| Gruppe anlegen | im Dialog (Formular, unverändert) | Enter im Namensfeld |

Die Zeilenaktion sitzt neben dem vorhandenen Lösch-Trigger in `renderRow`
(`RequirementList.tsx:699-720`) und wird — wie dieser — nur für `hasRole('editor')` gerendert.

### 4.4 Zustände

- **Kein Workspace / Viewer:** kein „Gruppen…"-Button (statt deaktiviert). Die Gruppenansicht
  bleibt für Viewer lesbar, wenn `groups` geliefert wird (heute schon so).
- **Keine Gruppen:** Dialog zeigt den vorhandenen Leertext (`groups.empty`) und das Anlegeformular.
- **Fehler beim Zuordnen:** Meldung im Dialog (`role="alert"`), Dialog bleibt offen.
- **Ladezustand:** `groups.loading` im Dialog; der Baum bleibt bedienbar.

### 4.5 Akzeptanzkriterien

1. Auf `/requirements` ist im Ruhezustand **kein** Element mit `data-testid="group-manager"`
   gemountet; `req-list-groups-btn` öffnet `group-manager-dialog`, Escape schließt ihn und gibt den
   Fokus auf den Button zurück.
2. Die Höhe zwischen Toolbar und erster Baumzeile enthält nur noch „Gelöschte anzeigen",
   „Gruppen anzeigen" und optional ein Fehlerbanner. Nachweis: der Test findet kein
   `group-manager` im DOM und die Listenspalte rendert genau `IncludeDeletedToggle` +
   `WorkspaceTree` (children des Seitencontainers), nicht die Verwaltung.
3. Ein Requirement lässt sich über `req-row-group-<id>` genau einer Gruppe hinzufügen; der Zähler
   am Ordner und die Markierung „in N Gruppen" aktualisieren sich ohne Neuladen der Route.
4. Ein Drag einer Nicht-Mitglied-Zeile auf einen Ordner legt die Mitgliedschaft an; ein Drag einer
   Mitglied-Zeile ordnet weiterhin **nur innerhalb** der Gruppe um (bestehender Test bleibt grün).
5. Viewer sehen weder `req-list-groups-btn` noch `req-row-group-<id>` im DOM.
6. Die Architektur-Route ist unverändert (kein `onAddToGroup` gesetzt, kein zusätzlicher Button).

## 5. Teil B — Verbindungs-Route: zwei Bäume

### 5.1 Zielbild

```
PageHeader  „Verbindungen"   [Bäume | Architektur | Zwei Spalten | Matrix | Graph]   [Verbindungen anzeigen ☑]
[Offen] [Nicht allokiert] [Gesperrt] [Befunde]   [Suche …………]   [Weitere Filter ▾]   x von y · n gesperrt · m Befunde
─────────────────────────────────────────────────────────────────────────────────────
 2 ausgewählt     [Allokieren auf …]  [Vorschläge]  [Auswahl aufheben]     ← immer sichtbar, Aktionen je Auswahl aktiv
┌ Requirements-Baum ──────────────────┬ Architektur-Baum ────────────────────────────┐
│ ▾ Systemanforderungen               │ ▾ System                                     │
│   ▸ [ ] R-001 …  → Bremse           │   ▾ Subsystem Bremse                         │
│   ▸ [ ] R-002 …  (nicht allokiert)  │     • Steuergerät                           │
│   …                                 │   …                                          │
└─────────────────────────────────────┴──────────────────────────────────────────────┘
        Allokationskanten verlaufen im Korridor zwischen den Spalten
```

- Beide Spalten scrollen **gemeinsam** (ein Container, S10).
- Die Hierarchie wird durch die Baumstruktur gezeigt; gezeichnet werden nur die
  **spaltenübergreifenden Allokationskanten** (S9).
- Jede Requirement-Zeile nennt ihr Ziel zusätzlich **als Text** („→ Bremse" bzw. „nicht
  allokiert"), damit die Zuordnung nicht allein von einer Linie abhängt (A11y, Abschnitt 8).
- „Verbindungen anzeigen" ist ein Nutzerschalter in der Kopfzeile (D7, S9): ausgeschaltet
  verschwindet das Overlay, **nicht** die Textmarke. Der Zustand liegt in der Präferenz
  `ui.connection_view.show_edges` (Default `true`, B-4).

### 5.2 Ansichtsmodi und URL

```ts
export type ConnectionViewMode =
  | "trees"        // neu, Default
  | "architecture" // bisher "tree"
  | "two-column"   // unverändert
  | "matrix"
  | "graph";

// parseConnectionView:
//   "architecture" | "tree"           -> "architecture"
//   "two-column" | "matrix" | "graph" -> wie bisher
//   "trees" | fehlt                   -> "trees"       (Default)
```

- `setView` schreibt bei `trees` (Default) **keinen** `view`-Parameter und bei allen anderen Modi den
  Modusnamen.
- Die Umschaltleiste zeigt fünf Einträge: `Bäume`, `Architektur`, `Zwei Spalten`, `Matrix`, `Graph`.
- Alle Filter bleiben beim Moduswechsel erhalten (URL ist die Wahrheit — unverändert).

### 5.3 Renderer „Bäume"

Neue Datei `frontend/src/components/ConnectionView/AllocationTreesRenderer.tsx`, reine
Baumkonstruktion in `allocation-trees.ts` (testbar ohne React).

**Baumaufbau Requirements**

```ts
export interface AllocationRequirementNode {
  row: AllocationRow;                 // id = Requirement-Entität
  children: AllocationRequirementNode[];
  depth: number;
}

export function buildRequirementTree(
  requirements: readonly AllocationRow[],
): AllocationRequirementNode[];
```

- Elternbestimmung: `requirementByArtifact.get(row.parent_id)`; fehlt der Elternknoten (gefiltert
  oder kein Requirement-Artefakt), wird die Zeile **Wurzel** — identisch zum Verhalten von
  `RequirementList` (`useArtifactList` baut aus der gefilterten Liste).
- Geschwister-Reihenfolge: `sort_key` lexikografisch, `null` **zuletzt**, Tiebreak `title`
  (B4). Der vorhandene `compareRows` (`useAllocationView.ts:189-194`) erfüllt das bereits und wird
  wiederverwendet — **nicht** `compareElementRows` aus `TreeRenderer.tsx:40-45` (das sortiert
  `null` zuerst).
- Zyklen und Duplikate: wie in `buildGraph.ts:246-277` (besuchte Menge, kein Knoten zweimal).

**Baumaufbau Elemente**: derselbe Algorithmus über `elements` (`parent_id` = Element-Entität),
Geschwister nach `sort_key`/`title`.

**Kanten**

```ts
export interface AllocationEdge {
  requirementId: string;   // Requirement-Entität (Knoten-id)
  elementId: string;       // Element-Entität (Knoten-id)
}

/** Allokationen, deren beide Enden im aktuell gerenderten Satz liegen. */
export function buildAllocationEdges(
  requirements: readonly AllocationRow[],
  elements: readonly AllocationRow[],
): AllocationEdge[];
```

Auflösung: `row.allocated_to` ist die **Artefakt**-Id des Ziels → `elementByArtifact`.
Fehlt das Element (Teilbaum-Filter, veraltete Kante), entfällt die Kante; die Zeile zeigt dann
„zugeordnet (außerhalb des Filters)" statt „nicht allokiert" (siehe 5.6) — sie lügt nicht über einen
Zustand, den sie nicht kennt.

**Geometrie** (`edge-geometry.ts`, pur)

```ts
export interface RowRect { top: number; height: number }
export interface EdgePath { id: string; d: string }

/**
 * Rechnet Zeilenrechtecke (relativ zum gemeinsamen Scroll-Inhalt) in
 * Bézier-Pfade im Korridor um. Reihenfolge der Kanten ist stabil (nach
 * requirementId), damit React nicht neu keyt.
 */
export function buildEdgePaths(
  edges: readonly AllocationEdge[],
  from: ReadonlyMap<string, RowRect>,   // requirementId -> Zeile
  to: ReadonlyMap<string, RowRect>,     // elementId -> Zeile
  gutter: { x1: number; x2: number },
): EdgePath[];
```

Messung im Renderer: `useLayoutEffect` + `getBoundingClientRect()` je sichtbarer Zeile
(`[data-alloc-row]`), relativ zum Scroll-Container; Neuberechnung bei `scroll`, `resize`,
Auf-/Zuklappen und Filterwechsel, gedrosselt über `requestAnimationFrame`. Nicht gemountete Zeilen
fehlen in der Map und werden übersprungen (S9). `aria-hidden="true"` auf dem `<svg>`.

**Zeilenaufbau**

- Beide Spalten verwenden **kompakte** Zeilen (einzeilig, ~28 px), nicht `<ArtifactRow>`
  (88 px) — die Ansicht ist eine Arbeitsfläche, keine Leseansicht.
- Requirement-Zeile: Einrückung + Aufklapp-Pfeil + `<input type="checkbox" data-testid="alloc-select-<id>">`
  + Titel + Typ-Badge + Ziel („→ Bremse" | „nicht allokiert") + Sperr-Icon (`Lock`, wie
  `TreeRenderer.tsx:222-236`).
- Element-Zeile: Einrückung + Pfeil + Titel + Typ-Badge + Zähler (`element-count-<id>`,
  bestehende Testid) + Sperr-Icon.
- Rollen: je Spalte `<section aria-label>`; jede Zeile ist ein `<li>`; ein aufgeklappter Teilbaum ist
  eine verschachtelte `<ul role="group" aria-labelledby="…">`. Aufklappen über einen echten
  `<button aria-expanded aria-controls>`, nicht über ein `<div onClick>`. (Der bestehende
  `WorkspaceTree` ist hier nicht wiederverwendbar: er kennt weder Checkboxen noch eine zweite,
  gekoppelte Spalte, und seine Zeilen sind als Navigationszeilen mit `renderRow` gebaut. Ein Umbau
  dort würde die fünf anderen Routen mitziehen.)

**Interaktion**

| Aktion | Zeiger | Tastatur |
|---|---|---|
| Auswählen | Checkbox | Space auf der Checkbox |
| Alle auswählen/abwählen | Aktionsleiste | Enter auf `assistant-select-all` |
| Zuweisen | Zeile auf Element ziehen | `allocate-open-<id>` in der Zeile → Suchdialog (`element-picker`) |
| Umallokieren | auf anderes Element ziehen (ersetzt die Kante, B6) | derselbe Dialog |
| Lösen | `Entfernen`-Aktion der Zeile (`deallocate-<id>`) | Enter |
| Hervorheben | Hover/Klick auf Zeile → Kante und Gegenstück betont | Fokus auf Zeile = dasselbe |
| Auf-/Zuklappen | Pfeil | Enter/Space auf dem Pfeil |

Beim Ziehen: gültige Ziele werden betont, gesperrte Requirements sind nicht ziehbar (E6), gesperrte
Elemente bleiben gültige Ziele (E6) — beides wie in `TreeRenderer.tsx:125-170`.

### 5.4 Selektion und Aktionsleiste

Die Selektion wandert aus dem Assistant in einen Hook auf Seitenebene
(`ConnectionView/useAllocationSelection.ts`):

```ts
export interface AllocationSelection {
  selectableIds: ReadonlySet<string>;   // gefilterte, nicht gesperrte Requirements
  selectedRows: AllocationRow[];
  isSelected: (id: string) => boolean;
  toggle: (id: string) => void;
  selectAll: () => void;
  clear: () => void;
}

export function useAllocationSelection(
  requirements: readonly AllocationRow[],
): AllocationSelection;
```

- `selectedIds` bleibt bei Filterwechsel erhalten, wirkt aber nur auf sichtbare Zeilen (wie
  heute: `selectedRows` wird aus `requirements` gefiltert, `AllocationAssistant.tsx:102-108`).
- `AllocationAssistant` wird **präsentational**: Props `selection`, `requirements`, `elements`,
  `allocateBulk`, `suggestArchitecture`, `canEdit`; keine eigene Liste mehr.
- Die Leiste zeigt immer: Auswahlzähler (`assistant-selection-count`), „Alle auswählen",
  „Allokieren auf …", „Vorschläge". Ohne Auswahl ist nur „Allokieren auf …" deaktiviert;
  „Vorschläge" arbeitet dann über alle nicht allokierten Requirements (heutiges Verhalten,
  `AllocationAssistant.tsx:197-206`).
- Vorschlagsliste, Bestätigungsdialog, Fehler- und Hinweisfläche bleiben unverändert
  (`assistant-suggestions`, `assistant-suggestion-confirm`, `assistant-error`, `assistant-notice`).

### 5.5 Filterleiste

Zeile 1 (immer sichtbar): `Offen` · `Nicht allokiert` · `Gesperrt` · `Befunde` · Freitextsuche ·
`Weitere Filter ▾` · Kennzahlen (`counter-total`, `counter-unallocated`, `counter-locked`,
`counter-findings`, alle bestehend).

Zeile 2 (Popover, `data-testid="filter-more"`): Stufe, Typ, Kategorie, Zustand, Element-Teilbaum,
Gruppe, gespeicherte Sichten (Name, Speichern, Liste). Anzahl aktiver Zusatzfilter steht als Badge
am Auslöser („Weitere Filter (2)").

Der Aufklapp-Zustand ist eine **Nutzerpräferenz** (D8): `ui.connection_view.filters_expanded`,
Default `false` (B-4), über `preferenceValuesApi` auf Nutzer-Ebene gelesen und geschrieben. Er ist
**nicht** Teil der URL — die URL bleibt die Wahrheit über den Filter**wert**, die Präferenz über die
Sichtbarkeit. Ein fehlgeschlagener Schreibvorgang darf das Aufklappen nicht blockieren (der Zustand
gilt lokal weiter, der Fehler wird wie bei den gespeicherten Sichten gemeldet).

### 5.6 Markierungen (statt „Nicht allokiert"-Block)

| Zustand | Darstellung | Testid |
|---|---|---|
| nicht allokiert | Zieltext „nicht allokiert" in `--color-warning`, Punktmarke links am Titel | `unallocated-marker-<id>` |
| zugeordnet | Zieltext „→ {{element}}" | `alloc-target-<id>` |
| gesperrt | `Lock`-Icon + Zustandsname im `title`/`aria-label` | `req-locked-<id>` (bestehend) |
| Kante ins Nichts (`allocated_to` gesetzt, Element nicht im Satz) | Zieltext „zugeordnet (außerhalb des Filters)" | `alloc-target-external-<id>` |
| Befund an der Zeile | Warnpunkt; Details im `title` | `req-findings-<id>` |

Der Block `unallocated-block`/`unallocated-count` entfällt. Die Aussage „2 nicht allokiert" liefert
weiterhin `counter-unallocated` in der Kopfzeile.

### 5.7 Backend-Verträge

**B-1 — `kind`-Filter auf dem Leseobjekt**

```
GET /api/v1/workspaces/{id}/allocation-view/?kind=requirement|element&page_size=500
```

- `kind` ist optional; unbekannter Wert → **400** mit dem bestehenden Fehler-Envelope
  (`ValidationError` im Service, `views.py:8304-8310` fängt sie bereits).
- `kind` beschränkt **nur** `results`; `meta` bleibt über die gesamte gefilterte Menge gerechnet
  (`allocation_view_service.py:215-228`), damit die Kennzahlen unabhängig vom `kind` des Aufrufs
  stimmen.
- Implementierung im Service: `kind: str | None = None` als Parameter, Prüfung am Anfang von
  `list()` zusammen mit `page_size`/`offset` (`:45-48`). Die Filterung erfolgt **nach** dem
  bestehenden Filterdurchlauf und **vor** dem Slice, damit Paginierung und `meta` stimmen:

  ```python
  filtered = [row for row in rows if matches(row)]                  # unverändert
  visible = [
      row for row in filtered if kind is None or row["kind"] == kind
  ]
  return {
      "results": visible[offset : offset + page_size],
      "meta": {...},                                               # aus `filtered`, nicht `visible`
  }
  ```

  `kind` gehört **nicht** in `matches()` — sonst würden die Kennzahlen vom Aufruf abhängen.

**B-2 — `sort_key` für Element-Zeilen**

`_element_row` liefert heute `"sort_key": None` (`:154`). Künftig der persistierte Schlüssel des
zugehörigen Artefakts. Die Element-Abfrage (`:58-62`) selektiert `artifact_id` bereits; der
vorhandene Artefakt-Lookup (`:93-98`) wird auf Element-Artefakte erweitert:

```python
artifact_rows = {
    row["id"]: row
    for row in Artifact.unscoped.filter(
        id__in=[req["artifact_id"] for req in requirements]
        + [el["artifact_id"] for el in elements]
    ).values("id", "parent_id", "sort_key")
}
```

- `_requirement_row` nutzt weiterhin `artifact.get("sort_key")`; `_element_row` nutzt
  `artifact_rows.get(row["artifact_id"], {}).get("sort_key")`.
- Ein Element ohne Artefakt-Zeile (defekte Daten) liefert `None` — kein Fehler, die Zeile sortiert
  zuletzt.

**B-3 — Frontend-Reads entdoppeln**

`useAllocationView` lädt künftig:

```ts
rowsQuery     = allocationViewApi.view(ws, {
  ...filtersToQuery(filters),
  kind: "requirement",
});
elementsQuery = allocationViewApi.view(ws, {
  ...filtersToQuery(filters),
  kind: "element",
});
```

- `elements` stammt **ausschließlich** aus `elementsQuery` (kein Fallback über `allRows`) — damit
  ist der 500er-Deckel pro Art kein gemeinsamer Deckel mehr und der leere Katalog bei > 500
  Requirements behoben.
- `element_subtree` wirkt jetzt auch auf die Element-Spalte (der Filter steht in
  `filtersToQuery`, `useAllocationView.ts:149-168`) — der Baum zeigt dann den Teilbaum.
- `filtersToQuery` bekommt `kind` **nicht** als Filterfeld, sondern als Parameter der beiden
  Aufrufe; `buildConnectionSearch`/`parseConnectionSearch` bleiben unverändert (kein URL-Parameter).

**B-4 — zwei Nutzerpräferenzen (D7, D8)**

Registrierung in `backend/auth_tenancy/apps.py` neben den vorhandenen
`ui.connection_view.*`-Schlüsseln (`:104-114`):

```python
# Kanten-Overlay der "Bäume"-Ansicht (D7): reine Lesehilfe einer Person.
PreferenceKey(
    key="ui.connection_view.show_edges",
    value_type="bool",
    default=True,
    levels=frozenset({PREFERENCE_SCOPE_USER}),
    mode="override",
    ui_editor="checkbox",
    owner="P3",
),
# Aufklapp-Zustand der Zusatzfilter (D8): Komfort, keine Datenaussage.
PreferenceKey(
    key="ui.connection_view.filters_expanded",
    value_type="bool",
    default=False,
    levels=frozenset({PREFERENCE_SCOPE_USER}),
    mode="override",
    ui_editor=None,
    owner="P3",
),
```

- Nur Nutzer-Ebene: ein Workspace-Admin darf die Lesehilfe anderer Personen nicht umstellen.
- `ui_editor` ist auf `None`/`"checkbox"`/`"select"` beschränkt
  (`application/preference_registry.py:155-158`) — beide Schlüssel bleiben hier gültig.
- Frontend: Erweiterung von `api/connection-views.ts` (besitzt bereits den Namensraum und nutzt
  `preferenceValuesApi`); Laden über `getLevel("user")`, Schreiben über `patchLevel("user", …)`.
  Fehlgeschlagenes Laden ⇒ Default, fehlgeschlagenes Schreiben ⇒ Meldung, Zustand bleibt lokal.
- Ein unbekannter Schlüssel wird vom Backend abgelehnt; die Registrierung ist deshalb
  Voraussetzung für den Schalter, nicht Nacharbeit.

**Nicht Teil dieser Spezifikation:** `group`-Feld im Leseobjekt füllen (bleibt Client-Join),
Mehrfachallokation, Änderungen an `meta`-Semantik.

### 5.8 Akzeptanzkriterien

1. `/connections` öffnet ohne `view`-Parameter in `Bäume`; die Umschaltleiste markiert `Bäume` als
   aktiv (`aria-pressed="true"`, `view-switch-trees`).
2. Beide Spalten zeigen die **Hierarchie** (Eltern/Kind eingerückt, auf-/zuklappbar), nicht flache
   Listen; Geschwister stehen in `sort_key`-Reihenfolge, Zeilen ohne Schlüssel zuletzt.
3. Jede Allokation erzeugt genau **eine** Kante; ein Requirement hat höchstens eine Kante (N:1).
   Kanten für Zeilen außerhalb des sichtbaren Bereichs fehlen folgenlos (kein Fehler, keine
   Konsolenwarnung).
4. Klick/Fokus auf eine Requirement-Zeile betont ihre Kante **und** die Ziel-Elementzeile; Klick auf
   eine Elementzeile betont alle ihre Requirements.
5. Ziehen einer Requirement-Zeile auf ein Element allokiert (ersetzt bestehende Kante); Ziehen auf
   ein gesperrtes Requirement ist nicht möglich; ein gesperrtes Element nimmt weiter an.
6. Die Aktionsleiste erscheint mit der Auswahl; `assistant-selection-count` zählt nur sichtbare,
   nicht gesperrte Zeilen. Ohne Auswahl ist „Allokieren auf …" deaktiviert, „Vorschläge" aktiv.
7. „Nicht allokiert" ist als Zeilenmarkierung sichtbar (`unallocated-marker-<id>`) und über den
   Schnellfilter filterbar; ein Block am Seitenende existiert nicht mehr.
8. `view=tree` öffnet `Architektur`; `view=two-column` öffnet unverändert `Zwei Spalten`; eine
   gespeicherte Sicht mit diesen Parametern funktioniert unverändert.
9. Der Element-Teilbaum-Filter beschränkt **beide** Spalten auf den Teilbaum.
10. Bei einem Workspace mit > 500 Requirements enthält die Element-Spalte weiterhin alle Elemente
    (Regressionstest mit 600 Requirements + 20 Elementen auf Service-Ebene).
11. Tastatur: die vollständige Allokation ist ohne Zeigegerät möglich (Checkbox → „Allokieren auf …"
    → Suchdialog → Enter).
12. Der Modus `Architektur` und der Modus `Zwei Spalten` verhalten sich unverändert (bestehende
    `TreeRenderer`- und `TwoColumnRenderer`-Tests bleiben grün).
13. „Verbindungen anzeigen" schaltet **nur** das Overlay ab; die Zieltexte an den Zeilen bleiben
    sichtbar. Die Einstellung überlebt einen Reload und einen Moduswechsel (Nutzerpräferenz,
    `ui.connection_view.show_edges`).
14. „Weitere Filter" behält seinen Aufklapp-Zustand über einen Reload (Nutzerpräferenz,
    `ui.connection_view.filters_expanded`), ohne dass ein Filterwert aus der URL verloren geht.
15. Ein unbekannter Präferenzschlüssel führt **nicht** zu einem stillen Fehlschlag: nach der
    Registrierung (B-4) liefert ein Lesen den Default, ein Schreiben wird vom Backend akzeptiert.

## 6. Datenverträge (Auszug)

```jsonc
// GET /workspaces/{id}/allocation-view/?kind=element
{
  "results": [
    {
      "kind": "element",
      "id": "…",              // ArchitectureElement.id
      "artifact_id": "…",
      "parent_id": "…",       // Element-Entität des Elternknotens
      "sort_key": "a3",       // NEU: persistierter Schlüssel des Artefakts (oder null)
      "title": "Bremse",
      "type": "Subsystem",
      "locked": null,
      "findings": []
    }
  ],
  "meta": { "total": 812, "unallocated": 96, "locked": 4, "findings": 0 }
}
```

- `meta` ist **nicht** auf `kind` bezogen (B-1). `meta.total` zählt Requirements **und** Elemente,
  wie heute; es ist eine Kennzahl der Seite, nicht der Spalte. `meta.unallocated` zählt weiterhin nur
  Requirements ohne `allocated_to`.
- Requirement-Zeilen unverändert, insbesondere `parent_id` = Eltern-**Artefakt**-Id und
  `allocated_to` = Ziel-**Artefakt**-Id (bestehender Vertrag, `api/allocation-view.ts:36-74`).

## 7. i18n (DE/EN, beide Dateien)

| Key | DE | EN |
|---|---|---|
| `groups.manage` | „Gruppen…" | "Groups…" |
| `groups.dialogHint` | „Gruppen sind rein visuell: Sie ordnen die Anzeige, nicht die Ebene oder die Allokation." | "Groups are visual only: they order the view, never the tier or the allocation." |
| `groups.addToGroup` | „Zu Gruppe hinzufügen…" | "Add to group…" |
| `groups.addToGroupTitle` | „{{name}} einer Gruppe zuordnen" | "Assign {{name}} to a group" |
| `groups.alreadyMember` | „Bereits zugeordnet" | "Already assigned" |
| `groups.addSelected` | „Hinzufügen" | "Add" |
| `connectionView.views.trees` | „Bäume" | "Trees" |
| `connectionView.views.architecture` | „Architektur" | "Architecture" |
| `connectionView.filters.more` | „Weitere Filter" | "More filters" |
| `connectionView.filters.moreActive` | „Weitere Filter ({{count}})" | "More filters ({{count}})" |
| `connectionView.allocTarget` | „→ {{element}}" | "→ {{element}}" |
| `connectionView.allocTargetMissing` | „zugeordnet (außerhalb des Filters)" | "assigned (outside the filter)" |
| `connectionView.notAllocated` | „nicht allokiert" | "not allocated" |
| `connectionView.deallocate` | „Zuordnung lösen" | "Remove allocation" |
| `connectionView.trees.requirements` | „Anforderungen" | "Requirements" |
| `connectionView.trees.elements` | „Architektur" | "Architecture" |
| `connectionView.trees.selectionHint` | „Zeilen auswählen, um mehrere Anforderungen gemeinsam zuzuordnen." | "Select rows to allocate several requirements at once." |
| `connectionView.trees.showEdges` | „Verbindungen anzeigen" | "Show connections" |
| `connectionView.trees.edgesOff` | „Verbindungen ausgeblendet — die Zuordnung steht an jeder Zeile." | "Connections hidden — each row still names its target." |

`connectionView.views.twoColumn` **bleibt** (D6).
`frontend/src/i18n/locales.test.ts` prüft die Schlüsselparität DE/EN — beide Dateien müssen den
gleichen Satz enthalten.

## 8. Barrierefreiheit

- **Kante ist nie die einzige Information.** Jede Requirement-Zeile nennt ihr Ziel als Text
  (`alloc-target-<id>` / „nicht allokiert"). Das SVG-Overlay ist `aria-hidden="true"` und trägt
  keine Bedeutung.
- **Fokus = Hervorhebung.** Tastaturfokus auf einer Zeile löst dieselbe Betonung aus wie Hover,
  damit die Zuordnung ohne Zeigegerät erkennbar ist.
- **Baum-Semantik:** Auf-/Zuklappen über `<button aria-expanded aria-controls>`; die Spalte hat
  `aria-label`; die Zeilen sind `<li>`, ein Teilbaum ist eine `role="group"`-Liste. Kein
  `role="tree"`-Eigenbau, solange die Pfeiltasten-Navigation nicht vollständig implementiert ist
  (ein halbes `tree`-Rollenmodell ist schlechter als eine ehrliche Liste).
- **Checkboxen** haben ein Label, das den Titel enthält (kein `aria-label` ohne Bezug).
- **Kontrast:** Zieltext und Marke nutzen `--color-warning`/`--color-text-muted` nur als
  Zusatzsignal; der Text selbst bleibt `--color-text`. Keine Farbe als alleiniger Träger.
- **Drag:** jede Zeige-Aktion hat einen Tastaturpfad (Tabelle 5.3). Das ist Pflicht, nicht optional
  (Vorlagenspezifikation §6).
- **Reduzierte Bewegung:** das Auf-/Zuklappen animiert nicht (`prefers-reduced-motion` bleibt
  unberührt, weil keine Transition eingeführt wird).

## 9. Performance

- Ein gemeinsamer Scroll-Container (S10) → keine Scroll-Synchronisation, keine doppelte
  Layoutberechnung.
- Kantenberechnung ist O(sichtbare Kanten), gedrosselt auf einen Frame; kein `setState` pro
  Scroll-Event (Ref + `requestAnimationFrame`).
- Keine Virtualisierung in beiden Bäumen (bewusste Entscheidung): die Zeilen sind einzeilig
  (~28 px); 2 × 500 Zeilen sind ~1 000 DOM-Knoten. Der Deckel des Leseobjekts (500 je Art, B-1)
  ist damit die Obergrenze. Wird sie erreicht, erscheint oberhalb der Bäume ein Hinweis
  („{{n}} Zeilen nicht dargestellt", `data-testid="trees-truncated-notice"`, gespeist aus
  `meta.total` minus gerenderte Zeilen), statt still abzuschneiden.
- Kein zusätzlicher Netzwerkaufruf: `kind`-Filter ersetzt den zweiten Vollload (B-3), statt ihn zu
  ergänzen.

## 10. Tests

**Backend** (`backend/application/tests/test_allocation_view.py`)

- `kind=requirement`/`kind=element` liefern nur die jeweilige Art; `meta` unverändert.
- `kind=unbekannt` → 400 mit `VALIDATION_ERROR`-Envelope.
- Element-Zeilen tragen den `sort_key` ihres Artefakts; Elemente ohne Artefakt-Zeile → `None`.
- 600 Requirements + 20 Elemente: `kind=element&page_size=500` liefert alle 20 Elemente
  (Regression zum 500er-Deckel).
- `element_subtree` beschränkt Element-Zeilen auf den Teilbaum.

**Backend — Präferenzen** (`backend/auth_tenancy/tests/test_preference_keys_ordering.py`,
bestehende Datei erweitern)

- `ui.connection_view.show_edges` und `ui.connection_view.filters_expanded` sind registriert, nur auf
  Nutzer-Ebene schreibbar, `bool`, mit den Defaults `true`/`false`.
- Ein Schreibversuch auf Workspace- oder Global-Ebene wird abgelehnt (Level-Gate der bestehenden
  Tests).

**Frontend Unit**

- `allocation-trees.test.ts` — Wurzeln, fehlender Elternknoten ⇒ Wurzel, `sort_key`-Ordnung mit
  `null` zuletzt, Zyklus-Schutz, Duplikat-Schutz.
- `edge-geometry.test.ts` — Rechtecke → Pfade, stabile Reihenfolge, fehlende Enden ⇒ keine Kante.
- `useAllocationSelection.test.ts` — Auswahl überlebt Filterwechsel, gesperrte Zeilen nicht
  selektierbar, `selectAll` nur über sichtbare.
- `AllocationTreesRenderer.test.tsx` — Rendert beide Spalten, Checkbox-Testid, Zieltext, Kantenanzahl
  = Allokationsanzahl, Ziehen ruft `allocate` mit den **Entitäts**-Ids; `showEdges=false` rendert
  **kein** `<svg>`, aber weiterhin `alloc-target-<id>`.
- `ConnectionView.test.tsx` — Default-Modus `Bäume`, `tree`-Alias → `Architektur`,
  `two-column` bleibt `Zwei Spalten`; Präferenz `show_edges=false` blendet das Overlay aus.
- `FilterBar.test.tsx` — „Weitere Filter" startet gemäß Präferenz auf-/zugeklappt; ein
  fehlgeschlagenes Speichern kippt den lokalen Zustand nicht.
- `RequirementEditors.groups.test.tsx` (neu) — kein `group-manager` im Ruhezustand, Button öffnet
  den Dialog, Viewer sieht weder Button noch Zeilenaktion.
- `AddToGroupDialog.test.tsx` — bereits zugeordnete Gruppe deaktiviert, `onAdd` mit
  Requirement-**Entitäts**-Id.
- `workspace-tree.groups.test.tsx` — Drop eines Nicht-Mitglieds ruft `onAddToGroup`, Drop eines
  Mitglieds weiterhin `onReorderGroupMember`.

**E2E**

- `e2e/tests/connection-view.spec.ts` anpassen (5 Zeilen): `unallocated-count` →
  `counter-unallocated` (Zeilen 88, 103); `assistant-check-<id>` → `alloc-select-<id>`
  (Zeilen 90, 91, 139).
- `e2e/tests/connection-trees.spec.ts` (neu): zwei Bäume sichtbar, Kante vorhanden
  (`data-testid="allocation-edge-<requirementId>"`), Klick betont Gegenstück, Drag allokiert,
  Tastaturpfad allokiert.
- `e2e/tests/requirement-groups.spec.ts` (neu): „Gruppen…" öffnet den Dialog, Gruppe anlegen,
  Requirement über die Zeilenaktion zuordnen, „Gruppen anzeigen" zeigt den Ordner mit Zähler,
  Escape schließt und fokussiert den Auslöser.

## 11. Dateiliste

**Neu**

- `frontend/src/components/ConnectionView/AllocationTreesRenderer.tsx`
- `frontend/src/components/ConnectionView/allocation-trees.ts`
- `frontend/src/components/ConnectionView/edge-geometry.ts`
- `frontend/src/components/ConnectionView/useAllocationSelection.ts`
- `frontend/src/components/ConnectionView/AllocationTreesRenderer.module.css` (oder Erweiterung von
  `ConnectionView.module.css`; Design-Tokens, keine Inline-Styles — `ui-ratchet.test.ts`)
- `frontend/src/components/RequirementEditors/AddToGroupDialog.tsx` (+ `.module.css`)
- Tests: `allocation-trees.test.ts`, `edge-geometry.test.ts`, `useAllocationSelection.test.ts`,
  `AllocationTreesRenderer.test.tsx`, `AddToGroupDialog.test.tsx`, `FilterBar.test.tsx`,
  `RequirementEditors.groups.test.tsx`, `e2e/tests/connection-trees.spec.ts`,
  `e2e/tests/requirement-groups.spec.ts`

**Geändert**

- `frontend/src/components/RequirementEditors/RequirementEditors.tsx` — `groupPanel` raus,
  Dialog + Toolbar-Aktion rein.
- `frontend/src/components/RequirementEditors/RequirementList.tsx` — Prop `groupPanel` entfernen,
  Zeilenaktion „Zu Gruppe hinzufügen…" in `renderRow`.
- `frontend/src/components/shared/WorkspaceTree/workspace-tree.tsx` + `tree-drag.ts` +
  `tree-groups.ts` — `onAddToGroup`, Drop-Klassifikation „Nicht-Mitglied auf Ordner".
- `frontend/src/components/ConnectionView/ConnectionView.tsx` — Modus-Set, Default, Aktionsleiste,
  Filterzeile, Kopfzeilenschalter „Verbindungen anzeigen" (Präferenz `show_edges`).
- `frontend/src/components/ConnectionView/useAllocationView.ts` — `kind`-Reads, `ConnectionViewMode`,
  `parseConnectionView`.
- `frontend/src/components/ConnectionView/FilterBar.tsx` — Zeile 1 + „Weitere Filter"-Popover
  (Präferenz `filters_expanded`).
- `frontend/src/components/ConnectionView/AllocationAssistant.tsx` — Liste raus, präsentational.
- `frontend/src/components/ConnectionView/ConnectionView.module.css` — Spalten/Korridor/Kanten.
- `frontend/src/api/allocation-view.ts` — `kind` im Query-Typ.
- `frontend/src/api/connection-views.ts` — die beiden neuen Präferenzschlüssel lesen/schreiben.
- `backend/application/allocation_view_service.py` — `kind`, Element-`sort_key`.
- `backend/auth_tenancy/apps.py` — zwei `PreferenceKey`-Einträge (B-4).
- `backend/auth_tenancy/tests/test_preference_keys_ordering.py` — Registrierung + Level-Gate.
- `frontend/src/i18n/locales/de.json`, `en.json` — Abschnitt 7.
- `e2e/tests/connection-view.spec.ts` — 5 Zeilen.
- `docs/superpowers/specs/index.md` — neuer Eintrag.
- `docs/superpowers/specs/2026-11-04-ordnung-allokation-design.md` §6.2 — Verweis auf diese
  Spezifikation als Änderung der Default-Ansicht (D4), **erst nach Freigabe (D9/O5)**.

**Bewusst nicht angefasst:** `TreeRenderer.tsx`, `TwoColumnRenderer.tsx`, `MatrixRenderer.tsx`,
`buildGraph.ts`, `AllocationGraph/*`, `api/groups.ts`, Gruppen-Backend.

## 12. Phasen und Aufwand (Schätzung)

| Phase | Inhalt | Reihenfolge | Aufwand |
|---|---|---|---|
| **G** | Gruppen-Dialog, Zeilenaktion, Drag-zu-Gruppe, Tests | unabhängig, zuerst (kleinster Nutzen je Risiko) | 0,5–1 Tag |
| **V1** | Selektion in den Baum, Aktionsleiste, Filterzeile inkl. `filters_expanded`-Präferenz, „Nicht allokiert" als Markierung, E2E-Anpassung | **zusammen mit V3** | 1–1,25 Tage |
| **V2** | `kind`-Filter, Element-`sort_key`, entdoppelte Reads, Backend-Tests | unabhängig, vor V3 | 0,5 Tag |
| **V3** | `Bäume`-Renderer, Kanten-Overlay inkl. `show_edges`-Präferenz, Default-Modus, URL-Alias, Tests | nach V2, **zusammen mit V1** | 2–3 Tage |

V1 und V3 werden **gemeinsam** ausgeliefert: V1 entfernt die Selektionsliste, V3 liefert die
Zeilen-Checkboxen. Ein V1 ohne V3 würde die Mehrfachauswahl vorübergehend unerreichbar machen
(der Modus `Architektur` bekäme bewusst keine Checkboxen, siehe „Bewusst nicht angefasst").
V2 ist davon unabhängig und kann vorher gemergt werden. G ist von allem unabhängig.

## 13. Risiken

| # | Risiko | Maßnahme |
|---|---|---|
| R1 | Overlay-Geometrie wird bei tiefen Bäumen falsch, weil nur gemountete Zeilen messbar sind | Kanten nur für gemountete Enden; Ziel zusätzlich als Text; Test mit zugeklappten Zweigen |
| R2 | Neuer Präferenzschlüssel nicht registriert ⇒ Schreiben scheitert mit 400, Schalter wirkt nicht | B-4 zuerst umsetzen; Test in `test_preference_keys_ordering.py`; fehlgeschlagenes Laden/Schreiben blockiert die Ansicht nicht |
| R3 | Gespeicherte Sichten brechen | URL-Alias-Mapping (S4) + Test in `ConnectionView.test.tsx` und `useAllocationView.test.ts` |
| R4 | `ui-ratchet.test.ts` (eingefrorene Inline-Style-Zahl) schlägt fehl | ausschließlich CSS-Module, keine `style={{}}`-Literale |
| R5 | i18n-Paritätstest schlägt fehl | beide Locale-Dateien im selben Commit (Abschnitt 7) |
| R6 | Der 500er-Deckel bleibt an anderer Stelle (gespeicherte Sichten, Matrix-Fenster) | `SERVER_PAGE_SIZE` bleibt; B-1 macht ihn pro Art gültig; Hinweis bei Erreichen (§9) |
| R7 | Drag-zu-Gruppe kollidiert mit dem bestehenden Mitglieds-Reorder | klare Fallunterscheidung in `tree-drag.ts` + Test in `workspace-tree.groups.test.tsx` |
| R8 | Doppelte Semantik „Architektur"-Modus vs. „Bäume" | `Architektur` bleibt ausschließlich element-zentrisch; kein zweiter Ort für Kanten, keine Änderung am Renderer |

## 14. Offene Entscheidungen

**Keine.** Alle fünf Fragen (O1–O5) sind am 2026-11-08 beantwortet; das Protokoll steht in §3.3, die
Antworten sind in D5–D9 sowie S3, S6, S9 und S11 eingearbeitet:

- Gruppenverwaltung als modaler Dialog (O1).
- `Zwei Spalten` bleibt als eigener Modus (O2).
- Kanten und Zusatzfilter-Leiste sind abschaltbar bzw. merken ihren Zustand als Nutzerpräferenz
  (O3, O4).
- §6.2 der Vorlagenspezifikation wird erst nach Freigabe geändert (O5).

Offen ist damit nur noch die **Freigabe dieser Spezifikation**; danach kann die Umsetzung mit
Phase G beginnen (§12).

## 15. Bezüge

- `docs/superpowers/specs/2026-11-04-ordnung-allokation-design.md` — V10 (ein Leseobjekt, mehrere
  Renderer), B4 (`sort_key`, NULL zuletzt), B9 (`allocation-view`), E4 (N:1), E6 (Sperre), V11
  (Gruppen rein visuell), §6.2 (Default-Ansicht, wird durch D4 geändert), §6.3 (Karten-Graph), §6.4
  (Cluster).
- `docs/superpowers/plans/2026-11-04-ordnung-allokation.md` — P3 (Zusammenhangs-Ansicht), P5
  (Karten-Graph), P6 (Gruppen).
- `docs/plans/2026-11-08-navigationsbaum-und-verbindungsansicht.md` — Umsetzungsplan zu dieser
  Spezifikation (Phasen G, V2, V).
- `docs/UI_KONZEPT.md` ch. 12.1 (eine primäre Aktion pro Route), ch. 12.3 (Zeilenlayout), ch. 12.8
  (Dialog-Vertrag), ch. 13.3 (Empty States).
- Code-Einstiegspunkte: `RequirementEditors.tsx`, `RequirementList.tsx`, `GroupManager.tsx`,
  `ConnectionView.tsx`, `useAllocationView.ts`, `AllocationAssistant.tsx`, `TreeRenderer.tsx`,
  `buildGraph.ts`, `allocation_view_service.py`.
