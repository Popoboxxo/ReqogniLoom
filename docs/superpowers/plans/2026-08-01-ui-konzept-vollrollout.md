# UI-Konzept Vollrollout — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Alle Artefakt-Routen von ReqogniLoom auf den in `docs/UI_KONZEPT.md` festgelegten Standard heben — ein Seitenkopf, eine Toolbar, ein Baum, ein Scroll-Modell, eine Identitätsdarstellung, ein Dialog, ein Leerzustand — und die Trace-Spine (Kapitel 5) von der heutigen Ein-Seiten-Verwendung auf alle Artefakttypen ausrollen. Danach wird der Zustand durch automatische Gates (Kapitel 16) festgehalten, damit er nicht wieder auseinanderläuft.

**Architecture:** Reine Frontend-Arbeit in `frontend/src`. Der Plan ist so geschnitten, dass die geteilten Primitiven (`shared/`, `SplitView/`) **zuerst** die Zielverträge bekommen und die Seiten danach nur noch angeschlossen werden. Der teuerste Einzelposten ist `SplitView`, weil er heute den Vertrag aus Kapitel 12.6 nicht erfüllt und trotzdem von zwölf Seiten benutzt wird — er wird additiv erweitert (neue optionale Props), nicht ersetzt, damit Bestandsaufrufer unverändert weiterlaufen.

**Tech Stack:** React 18, TypeScript 5.5 (strict), Vite 5, Vitest, react-i18next, `@tanstack/react-virtual`, CSS Modules + `styles/tokens.css`, ESLint 9 (flat config), Playwright (E2E, nur auf ausdrückliche Anforderung ausführen).

## Global Constraints

- **Branch-Guard:** Feature-Branch (`feat/…`), nie direkt auf `main`. Der aktuelle Branch `feat/ui-pilot-base-goals-arch-needs` trägt den laufenden Pilot; dieser Plan beginnt erst nach dessen Merge.
- **Parallelarbeit:** Solange der Pilot läuft, sind `components/Goals/**`, `components/NeedsEditors/**`, `components/shared/ListToolbar.tsx` und `i18n/locales/*.json` von anderen Agenten belegt. Tasks, die diese Dateien anfassen, sind unten mit **[Pilot-Sperre]** markiert und starten erst nach Merge.
- **Funktionale Untergrenze (Konzept Kapitel 4):** Vor jedem Seitenumbau wird der heutige Funktionsumfang (Filter, Sortierung, Export, Felder, Aktionen) in der PR-Beschreibung aufgelistet und danach gegengeprüft. Ein Verlust ist ein offener Punkt, kein akzeptiertes Ergebnis.
- **Keine E2E-Läufe ohne ausdrückliche Anforderung des Nutzers.** E2E-Akzeptanzkriterien werden als Spec geschrieben und der Ausführung vorbehalten.
- Commits: Conventional Commits, Englisch, Imperativ, ≤ 72 Zeichen.
- Keine Default-Exports; keine Hex-Literale in neuem Code; `data-testid` auf allen neuen interaktiven Elementen.

---

## Ist-Zustand: Vermessung 2026-08-01

Erhoben durch Quelltext-Analyse über `frontend/src` (ohne Testdateien). Wo Zahlen von Anhang B des Konzepts abweichen, steht die Abweichung dabei — mehrere Werte haben sich seit der Messung vom 2026-07-28 **verbessert**, andere sind höher als dort angegeben.

### Was seit dem Audit bereits erledigt ist

| Konzept-Punkt | Stand heute |
|---|---|
| Fehlende Tokens (`--font-size-md`, `-3xl`, `--font-mono`, `--color-focus`, `--color-nav-bg`, Leadings, Trackings, Weights, `--measure`, `--nav-width`, `--list-min`, `--detail-min`, `--bp-md`, `--bp-lg`) | **alle in `styles/tokens.css` definiert** |
| Globaler Fokusring | **vorhanden** — `styles/global.css:45`, `:where(button,a,input,select,textarea,[tabindex]):focus-visible` |
| Schriften selbst hosten (9.7, Air-Gap + Datenschutz) | **erledigt** — `@fontsource/inter` + `@fontsource/outfit`, Import in `src/index.tsx`; kein Google-`@import` mehr |
| `glossary.ts` / `diagrams.ts` vollständiges Laden (#177) | **erledigt** — beide iterieren bis zur Erschöpfung |
| `role="alert"` bei Fehlern | **109 Vorkommen** gegen 46 `console.error` (Audit: 0) |
| i18n im Workflow-Editor | **14 von 15 Dateien** mit `useTranslation` (Audit: 0 von 23) |
| Dynamische Artefakt-Attribute (12.11) | `shared/ArtifactCustomFields` gebaut und in Architecture-, Goals-, Needs-, Requirement- und TestCase-Formularen verdrahtet |
| `<TraceSpine>` (Kapitel 5) | **Komponente vollständig gebaut**, inkl. dynamischer Stationszahl und Verifikations-Badge pro Station |

### Was noch offen ist

| Kennzahl | Stand 2026-08-01 | Ziel |
|---|---:|---:|
| Routen mit `<PageHeader>` | 4 / ~20 | alle Artefaktrouten |
| Routen mit `<h1>` (ohne `PageHeader`) | 3 Sonderfälle (Glossary `h2`-Größe, Reviews nackt, WorkflowEditor eigen) | 0 Sonderfälle |
| Listen mit `<ListToolbar>` | 9 | alle Listen |
| Seiten mit `<TraceSpine>` | **1** (Architecture) | alle Artefakt-Detailansichten |
| `SplitView` erfüllt Vertrag 12.6 (`spine`, `ratio`, `minWidths`, Collapse) | **nein** | ja |
| Scroll-Regeln in `SplitView` verankert (`overscroll-behavior: contain`, `scrollbar-gutter: stable`, Positionsgedächtnis) | **nein** | ja |
| Status-Badge-Implementierungen | **3** (`shared/StatusBadge`, `TestRuns/StatusBadge`, `WorkspaceSettings/DefaultStatusBadge`) | 1 |
| Baum-Implementierungen | **3** (`WorkspaceTree`, `DecompositionTree`, `RequirementTreeNode`) | 1 |
| Listen mit Virtualisierung | **2** (Needs, Requirements) | alle |
| `<ArtifactRow>` als geteilte Komponente | **fehlt** (lokal nur in `Goals/GoalsPanel.tsx`) | vorhanden |
| `<EmptyState>` | **fehlt vollständig** | vorhanden, 6 Zustände |
| `<Dialog>` (12.8) | **fehlt** — 11 handgebaute `role="dialog"`-Stellen, **kein** Fokus-Trap, **kein** Escape-Handling, **keine** Fokus-Rückgabe | 1 Primitive |
| Undefinierte, aber verwendete Tokens | **1** — `--color-background`, benutzt in **10 Dateien** inkl. `SplitView.module.scss` | 0 |
| `prefers-reduced-motion` | in 5 CSS-Modulen + `tokens.css`, **nicht** global; `global.css:6` setzt `scroll-behavior: smooth` ohne Aufhebung | einmal global |
| Inline-`style={{}}` in Komponenten | **1462** (Audit nannte 207 — die höhere Zahl ist der reale Stand) | monoton fallend |
| Hex-Literale in `.tsx` | **145 in 29 Dateien** | 0 |
| Fehlende Schlüssel in `de.json` | **3** — `actions.confirmDelete`, `actions.deleteConfirmPrompt`, `actions.deleting` | 0 |
| Theming-Ebenen (8.6) | **1** (semantisch, ohne Primitiv-Schicht); `ThemeContext` kennt zwei feste Werte | 2 Ebenen, benannte Paletten |
| Automatische Gates (Kapitel 16) | **0** | 8 |

### Seitenmatrix

Legende: ✔ vorhanden · ✖ fehlt · ~ eigene Nachbildung · n/a nicht anwendbar

| Route | PageHeader | ListToolbar | SplitView | Tree | TraceSpine | StatusBadge | ArtifactId | Custom Fields |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| `/goals` **[Pilot]** | ✔ | ✔ | ✔ | ✔ | ✖ | ✔ | ✔ | ✔ |
| `/architecture` **[Pilot]** | ✔ | ✔ | ✔ | ~ `DecompositionTree` | ✔ | ~ | ✔ | ✔ |
| `/needs` **[Pilot]** | ✔ | ✔ | ✔ | ✔ | ✖ | ✔ | ✔ | ✔ |
| `/requirements` | ✔ | ✔ | ✔ | ~ `RequirementTreeNode` | ✖ | ~ | ✖ | ✔ |
| `/adrs` | ✖ (`h3`) | ✔ | ✔ | ✔ | ✖ | ✔ | ✖ | ✖ |
| `/risks` | ✖ (`h3`) | ✔ | ✔ | ✔ | ✖ | ✔ | ✖ | ✖ |
| `/issues` | ✖ (`h3`) | ✔ | ✔ | ✔ | ✖ | ✔ | ✖ | ✖ |
| `/testcases` | ✖ (`h3`) | ✔ | ✔ | ✔ | ✖ | ✔ | ✖ | ✔ |
| `/icds` | ✖ (`h3`) | ✖ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ |
| `/diagrams` | ✖ (`h3`) | ✖ | ✔ | ✖ | ✖ | ✖ | ✖ | ✖ |
| `/baselines` | ✖ (`h3`) | ✖ | ✔ | ✖ | n/a | ✖ | ✔ | n/a |
| `/test-runs` | ✖ (`h2`) | ✖ | ✔ | ✖ | n/a | ~ eigene | ✖ | n/a |
| `/reviews` | ✖ (nackt `h1`) | ✔ | ✔ | ✖ | ✖ | ✖ | ✖ | n/a |
| `/glossary` | ✖ (`h1` in `2xl`) | ✖ (eigene Suche) | ✖ | ✖ | n/a | ✖ | ✖ | ✖ |
| `/traceability` | ✖ (`h2`) | ✖ | ✖ | ✖ | n/a | ✖ | ✖ | n/a |
| `/impact` | ✖ (`h2`) | ✖ | ✖ | ~ | n/a | ✖ | ✔ | n/a |
| `/metrics`, `/audit`, `/import`, `/settings`, `/system-settings`, `/profile`, `/workflows` | ✖ | n/a | n/a | n/a | n/a | — | — | n/a |

**Ablesbares Muster:** Vier Seiten — ADRs, Risks, Issues, TestCases — sind strukturell identisch (`SplitView` + `<Typ>List` mit `ListToolbar`+`WorkspaceTree` + `<Typ>Form` + `RightSidebar`, Anlegen als Inline-Formular in der Liste, `h3` statt `h1`, "+ New" in der Liste statt Primäraktion im Kopf). Sie werden deshalb als ein Block behandelt, nicht einzeln.

---

## Phasenüberblick

| Phase | Inhalt | Größe | Blockiert durch |
|---|---|---|---|
| 0 | Fundament-Restarbeiten (undefiniertes Token, Reduced-Motion, i18n-Lücke) | klein | — |
| 1 | Primitiven-Verträge: `SplitView` 12.6, `Dialog`, `EmptyState`, `ArtifactRow` | mittel–groß | Phase 0 |
| 2 | Quartett ADR / Risk / Issue / TestCase auf Konzeptstandard | mittel | Phase 1 |
| 3 | Requirements vervollständigen, Spine-Rollout | mittel | Phase 1 |
| 4 | Baum-Konsolidierung: 3 → 1 | groß | Phase 2 |
| 5 | Restliche Routen: ICDs, Baselines, Test Runs, Reviews, Traceability, Impact | mittel | Phase 1 |
| 6 | **Offene Entscheidung:** Glossary und Diagrams | — | Entscheidung Nutzer |
| 7 | Durchsetzung: Gates, Ratchets, E2E-Sonden | mittel | Phasen 1–5 |
| 8 | Optional: Theming-Zweiteilung, IBM Plex | mittel | unabhängig |

---

## Phase 0 — Fundament-Restarbeiten

### Task 0.1: `--color-background` auflösen

**Ziel:** Das zweite Vorkommen des `--font-size-md`-Fehlermusters beseitigen — ein Token, das benutzt, aber nie definiert wird, sodass die Deklaration *invalid at computed-value time* wird und still auf den geerbten Wert zurückfällt.

**Betroffene Dateien:**
- `frontend/src/styles/tokens.css` (Entscheidung: Alias definieren **oder** nicht)
- `frontend/src/components/SplitView/SplitView.module.scss`, `SplitView/SplitView.tsx`
- `frontend/src/components/AdminDialog/AttributeVisibilityAdmin.tsx`
- `frontend/src/components/shared/ArtifactCustomFields.tsx`
- `frontend/src/components/SystemSettings/MismatchReviewTable.tsx`, `SystemSettings/WorkspaceAdminSection.tsx`
- `frontend/src/components/WorkspaceSettings/{CustomFieldsSection,LlmSettingsSection,PromptTemplateSection,WorkspaceSettings}.tsx`

**Vorgehen:** Ersetzen durch `--color-surface` (Seitengrund) bzw. `--color-surface-raised` (erhöhte Fläche), je nach Rolle der Fläche laut Kapitel 8.4. Kein Alias-Token einführen — ein Alias verewigt den Namen, den das Konzept nicht kennt.

**Akzeptanzkriterium:** `grep -r "color-background" frontend/src` liefert 0 Treffer; die betroffenen Flächen rendern in Light **und** Dark sichtbar mit Themenfarbe (visuelle Prüfung im Browser, beide Themes).

**Abhängigkeiten:** keine. **Risiko:** niedrig — heute rendern diese Flächen ohnehin transparent/geerbt; jede Änderung ist eine sichtbare Verbesserung, aber Farbregressionen sind möglich, daher Theme-Doppelprüfung.

---

### Task 0.2: `prefers-reduced-motion` global, `scroll-behavior` aufheben

**Ziel:** Kapitel 11.3 — die Regel steht einmal in `global.css` und hebt dort auch das global gesetzte `scroll-behavior: smooth` auf.

**Betroffene Dateien:**
- `frontend/src/styles/global.css` (Regel ergänzen, `scroll-behavior` in den Reduce-Block)
- Entfernen der Duplikate in `components/shared/ArtifactInspector/{RightSidebar,TracePanel,VersionPanel}.module.css`, `components/SplitView/SplitView.module.scss`, `components/WorkflowEditor/WorkflowEditor.module.css`, `styles/tokens.css`

**Akzeptanzkriterium:** Genau ein `@media (prefers-reduced-motion: reduce)`-Block im Projekt, in `global.css`, mit `animation-duration`, `transition-duration` und `scroll-behavior`. Vitest-Snapshot nicht nötig; `grep -c` genügt als Nachweis.

**Abhängigkeiten:** keine. **Risiko:** niedrig.

---

### Task 0.3: Fehlende `de.json`-Schlüssel **[Pilot-Sperre]**

**Ziel:** Die drei seit dem Audit unveränderten Lücken schließen: `actions.confirmDelete`, `actions.deleteConfirmPrompt`, `actions.deleting`. Es sind ausgerechnet die Löschbestätigungen.

**Betroffene Dateien:** `frontend/src/i18n/locales/de.json`

**Akzeptanzkriterium:** Der Paritätstest aus Task 7.2 läuft grün (dieser Task liefert die Datenkorrektur, Task 7.2 den Test).

**Abhängigkeiten:** Merge des laufenden Piloten (Datei ist belegt). **Risiko:** niedrig.

---

## Phase 1 — Primitiven-Verträge

Diese Phase ist der Hebel. Ohne sie besteht jede Seitenumstellung aus Nachbau.

### Task 1.1: `SplitView` auf den Vertrag aus Kapitel 12.6 heben

**Ziel:** `SplitView` trägt Layout- **und** Scroll-Modell, wie das Konzept es an genau einer Stelle verankert haben will. Heute erfüllt es keinen der beiden Verträge.

**Konkrete Lücken:**
- Props sind `leftPanel` / `rightPanel` / `initialLeftWidth` / `moduleType`; das Konzept fordert `list` / `detail` / `spine` / `ratio` / `minWidths`.
- Ohne Detail läuft die Liste **nicht** über die volle Breite (Kapitel 6.2) — heute bleibt ein leeres Panel stehen.
- Kein `overscroll-behavior: contain`, kein `scrollbar-gutter: stable` (Kapitel 7.1 / 7.3).
- Kein Positionsgedächtnis, kein `scrollIntoView({ block: 'nearest' })` beim Zurückwechseln.
- Haltepunkt hart auf `768px` im SCSS statt über `--bp-md` / `--bp-lg`; der `--bp-lg`-Zustand (Off-Canvas-Navigation, 45:55) fehlt ganz.
- Kein Slot für die Spine.

**Betroffene Dateien:**
- `frontend/src/components/SplitView/SplitView.tsx`
- `frontend/src/components/SplitView/SplitView.module.scss`
- `frontend/src/components/SplitView/index.ts`
- neu: `frontend/src/components/SplitView/SplitView.test.tsx`

**Vorgehen — additiv, nicht ersetzend:** Die neuen Props `list` / `detail` / `spine` / `ratio` / `minWidths` kommen **zusätzlich** zu `leftPanel` / `rightPanel`. Sind `list`/`detail` gesetzt, gilt das neue Verhalten (Collapse, Spine-Slot, Verhältnis); sonst das alte. Scroll- und Scrollbar-Regeln gelten **sofort für beide Pfade**, weil sie keine API-Änderung sind. So bleiben die zwölf Bestandsaufrufer während der gesamten Phase 2–5 lauffähig, und jede Seite wird einzeln migriert.

**Akzeptanzkriterium:**
1. Unit-Test: mit `detail={null}` rendert die Liste ohne Detail-Container und ohne Breitenbeschränkung.
2. Unit-Test: `spine` wird zwischen Liste und Detail eingehängt und scrollt nicht mit dem Detailinhalt.
3. Berechneter Stil beider Scroll-Flächen enthält `overscroll-behavior: contain` und `scrollbar-gutter: stable`.
4. Der bestehende `src/test/SplitPaneResize.test.tsx` bleibt ohne Änderung grün (Rückwärtskompatibilität nachgewiesen).
5. Alle zwölf Bestandsseiten rendern unverändert (Smoke-Tests der betroffenen Suiten grün).

**Abhängigkeiten:** Task 0.1 (das SCSS benutzt `--color-background`). **Risiko: hoch** — größte Blast-Radius-Fläche des Plans, zwölf Aufrufer. Deshalb additive Props und ein eigener PR, der **keine** Seite migriert.

---

### Task 1.2: `shared/Dialog/` — die echte Modal-Primitive

**Ziel:** Kapitel 12.8. Heute existiert **keine** Dialog-Komponente. `RequirementsList/ModalDialogBase.tsx` trägt den Namen, ist aber ein Inline-Formular mit Stilkonstanten — kein Overlay, kein `role`, kein Fokusverhalten. Elf Stellen bauen `role="dialog"` von Hand; an keiner davon gibt es einen Fokus-Trap, ein Escape-Handling oder eine Fokus-Rückgabe.

**Betroffene Dateien:**
- neu: `frontend/src/components/shared/Dialog/Dialog.tsx`, `Dialog.module.css`, `index.ts`, `Dialog.test.tsx`
- neu (Hilfsmittel, separat testbar): `frontend/src/components/shared/Dialog/use-focus-trap.ts`

**Vertrag:**
- `role="dialog"` **und** `aria-modal="true"` **und** `aria-labelledby={titleId}` — die drei zusammen, nie einzeln
- Fokus beim Öffnen auf das erste bedienbare Element (oder auf den Dialog selbst, wenn keines existiert)
- Fokus-Falle: `Tab` / `Shift+Tab` zyklisch innerhalb des Dialogs
- `Escape` schließt
- Fokus kehrt beim Schließen auf das auslösende Element zurück (Referenz wird beim Öffnen gemerkt, nicht vom Aufrufer verlangt)
- Rendert per Portal in `document.body`; Hintergrund erhält `aria-hidden` **nicht** (Portal + `aria-modal` genügen und `aria-hidden` auf dem Root bricht den Fokus-Trap)
- Titelprop ist Pflicht; die Beschriftung ist per Konvention identisch mit dem auslösenden Knopf (Kapitel 14.1)

**Akzeptanzkriterium:** Unit-Tests decken ab: (a) alle drei ARIA-Attribute gesetzt, (b) Fokus landet beim Öffnen im Dialog, (c) `Tab` am letzten Element springt auf das erste, (d) `Escape` ruft `onClose`, (e) nach dem Schließen liegt der Fokus wieder auf dem Auslöser.

**Abhängigkeiten:** keine. **Risiko:** niedrig für die Komponente selbst; die Migration der elf Bestandsstellen ist Task 1.3.

---

### Task 1.3: Bestandsdialoge auf `shared/Dialog` umstellen

**Ziel:** Die elf handgebauten Overlays benutzen die Primitive; die neun `aria-modal`-ohne-`role`-Fälle verschwinden.

**Betroffene Dateien:**
- `components/AdminDialog/SystemHealthDialog.tsx`, `AdminDialog/TriLabelOverviewDialog.tsx`
- `components/ArchitectureEditors/ArchitectureEditors.tsx` (2 Stellen), `ArchitectureEditors/ArchitectureForm.tsx`
- `components/NavigationShell/CreateWorkspaceModal.tsx`
- `components/RequirementEditors/RequirementEditors.tsx`
- `components/Reviews/SignatureDialog.tsx`
- `components/shared/CreateTraceLinkDialog/create-trace-link-dialog.tsx`
- `components/SystemSettings/WorkspaceAdminSection.tsx`
- `components/WorkflowEditor/WorkflowModal.tsx`

**Akzeptanzkriterium:** `grep -rn 'role="dialog"' frontend/src/components` liefert nur noch `shared/Dialog/Dialog.tsx`; alle betroffenen Bestandstests bleiben grün; stichprobenhafte Tastaturbedienung (Öffnen → Tab-Zyklus → Escape → Fokus zurück) an drei Dialogen im Browser geprüft.

**Abhängigkeiten:** Task 1.2. Für `ArchitectureEditors` zusätzlich der Legenden-Dialog aus dem laufenden Piloten — Reihenfolge abstimmen, damit nicht zweimal migriert wird. **Risiko:** mittel — jeder Dialog hat eigene Öffnen/Schließen-Semantik; einzeln migrieren, nicht in einem Commit.

---

### Task 1.4: `shared/EmptyState`

**Ziel:** Kapitel 12.7 und 13. Es gibt heute keine Komponente und laut Audit vier Muster. Vor allem: **Leer** und **Kein Treffer** werden nirgends unterschieden.

**Betroffene Dateien:** neu `frontend/src/components/shared/EmptyState/EmptyState.tsx`, `EmptyState.module.css`, `index.ts`, `EmptyState.test.tsx`

**Vertrag:** Drei Rollen — Titel (was fehlt), **ein** Satz (was hier entsteht und wozu), Aktionen (der nächste Schritt). Varianten für die sechs Zustände aus 13.1: `loading` (Platzhalter in der Form des späteren Inhalts, erst ab 300 ms sichtbar), `empty`, `no-match` (Aktion = Filter zurücksetzen, **nicht** "Neu anlegen"), `error` (mit "Erneut versuchen"), `forbidden` (welche Rolle nötig ist und wer sie vergibt), `filled` (rendert nichts).

**Akzeptanzkriterium:** Unit-Test: `no-match` bietet "Filter zurücksetzen" und **keine** Anlege-Aktion; `loading` rendert vor 300 ms nichts; `error` rendert `role="alert"`.

**Abhängigkeiten:** keine. **Risiko:** niedrig.

---

### Task 1.5: `shared/ArtifactRow` aus `Goals` herausheben **[Pilot-Sperre]**

**Ziel:** Kapitel 12.3. Die zweizeilige Zeile (ID + Ebene oben, Titel unten; Status und Version rechts oben; Auswahl über Fläche + 3 px linke Kante) existiert bereits — aber nur lokal in `Goals/GoalsPanel.tsx`, gebaut im laufenden Piloten. Sie gehört nach `shared/`.

**Betroffene Dateien:**
- neu: `frontend/src/components/shared/ArtifactRow/ArtifactRow.tsx`, `.module.css`, `index.ts`, `ArtifactRow.test.tsx`
- `frontend/src/components/Goals/GoalsPanel.tsx` (Umstellung auf den Import) — **erst nach Pilot-Merge**

**Akzeptanzkriterium:** Goals rendert visuell unverändert; die Komponente ist ohne Goals-spezifische Props verwendbar (Prüfung: einmal mit einem ADR-Datensatz instanziiert im Test).

**Abhängigkeiten:** Pilot-Merge. **Risiko:** niedrig, aber die Extraktion muss die im Piloten getroffenen Detailentscheidungen erhalten — nicht neu erfinden.

---

### Task 1.6: Status-Badge-Implementierungen 3 → 1

**Ziel:** Kapitel 12.4, "die **einzige** farbkodierte Angabe". Neben `shared/StatusBadge.tsx` existieren `TestRuns/StatusBadge.tsx` und `WorkspaceSettings/DefaultStatusBadge.tsx`.

**Betroffene Dateien:**
- `frontend/src/components/shared/StatusBadge.tsx` (ggf. um die Test-Run-Zustände erweitern)
- löschen: `frontend/src/components/TestRuns/StatusBadge.tsx`
- Aufrufer: `TestRuns/{TestRuns,TestRunsList,TestRunDetailEditor}.tsx`, `WorkspaceSettings/{DefaultStatusBadge,WorkflowPermissionsSection}.tsx`

**Akzeptanzkriterium:** Genau eine Datei im Projekt erzeugt Status-Badge-Markup; Test-Run-Zustände rendern mit denselben Tokens wie Artefakt-Zustände; `TestRuns`-Bestandstests grün.

**Abhängigkeiten:** keine. **Risiko:** mittel — Test-Run-Zustände sind fachlich andere Zustände als der Workflow-Status. Vor dem Zusammenlegen prüfen, ob eine gemeinsame Semantik überhaupt trägt; wenn nicht, ist das Ergebnis eine Variante **innerhalb** derselben Komponente, keine zweite Komponente.

---

## Phase 2 — Das Quartett: ADRs, Risks, Issues, TestCases

Vier strukturgleiche Seiten, ein wiederholtes Vorgehen. Jede Seite ist ein eigener Task und ein eigener PR, aber das Rezept ist identisch — die erste Seite legt das Muster fest.

### Task 2.1: ADRs auf Konzeptstandard (Referenzumbau)

**Ziel:** `/adrs` erfüllt Kapitel 12.1, 12.2, 12.3, 12.6 und 13; das Ergebnis ist die Vorlage für 2.2–2.4.

**Betroffene Dateien:** `frontend/src/components/AdrEditors/{AdrEditors,AdrList,AdrForm}.tsx`

**Zu behebende Befunde (aus dem Quelltext belegt):**
- `AdrList.tsx` rendert `<h3>` als Seitenüberschrift → ersetzen durch `<PageHeader>` in `AdrEditors.tsx` mit `title`, immer sichtbarer `summary` und einer Primäraktion.
- Der Anlege-Knopf `+ {t('actions.new')}` steht **in der Liste** → verstößt gegen 12.2 ("Keine Primäraktion in der Leiste") und 14.2 ("+ New" benennt die Geste, nicht das Ergebnis). Wandert in den Kopf, beschriftet mit dem Ergebnis.
- Der Zähler erscheint nur bei aktivem Filter (`countLabel={hasActiveListControls ? … : null}`) → Zusammenfassung im `PageHeader` ist **immer** sichtbar (12.1).
- Listenzeile ist ein `WorkspaceTree`-Knoten mit Status-Badge, ohne ID, Ebene und Version → `<ArtifactRow>` (12.3).
- Kein Leerzustand-/Kein-Treffer-Unterschied → `<EmptyState>` mit `empty` vs. `no-match`.
- Anlegen ist ein Inline-Formular in der Liste → auf `shared/Dialog` umstellen, Dialogtitel = Knopfbeschriftung.
- `ArtifactCustomFields` fehlt im Formular → ergänzen (12.11).

**Akzeptanzkriterium:**
1. Genau ein `<h1>` auf der Route.
2. Zusammenfassung sichtbar ohne aktiven Filter.
3. Leere Liste und leeres Filterergebnis zeigen **unterschiedliche** Texte und **unterschiedliche** Aktionen.
4. Funktionale Untergrenze: Suche, Statusfilter, vier Sortierungen, Anlegen, Speichern, Löschen, Trace-Link-Panel, Versions-Sidebar — alle vorher aufgelistet und nachher nachweislich vorhanden.
5. `src/test/AdrEditors.test.tsx` angepasst und grün.

**Abhängigkeiten:** Tasks 1.1, 1.2, 1.4, 1.5. **Risiko:** mittel.

---

### Task 2.2 – 2.4: Risks, Issues, TestCases nach demselben Muster

**Ziel:** identisch zu 2.1, je Seite.

**Betroffene Dateien:**
- 2.2: `components/RiskEditors/{RiskEditors,RiskList,RiskForm}.tsx`
- 2.3: `components/IssueEditors/{IssueEditors,IssueList,IssueForm}.tsx`
- 2.4: `components/TestCaseEditors/{TestCaseEditors,TestCaseList,TestCaseForm}.tsx`

**Zusätzlich je Seite:**
- Risks und Issues tragen einen inline gestylten "Neue Verknüpfung"-Knopf mitten im Detailbereich (`RiskEditors.tsx`, `IssueEditors.tsx`) → gehört in den Artefaktkopf bzw. in das Trace-Panel, nicht als freischwebender Knopf unter das Formular.
- `IssueEditors` übergibt `currentVersion={undefined}` an die `RightSidebar` → prüfen, ob Issues wirklich keine Version führen; wenn doch, `VersionBadge` konsistent anschließen.
- TestCases: `ArtifactCustomFields` ist bereits verdrahtet — nur Kopf, Zeile, Leerzustand, Dialog.

**Akzeptanzkriterium:** wie 2.1, je Seite. Zusätzlich: eine gemeinsame Prüfung am Ende der Phase, dass alle vier Listenzeilen **pixelgleich** aufgebaut sind (gleiche Komponente, gleiche Reihenfolge — Prinzip 3.1).

**Abhängigkeiten:** Task 2.1 (Muster). **Risiko:** niedrig nach 2.1.

---

## Phase 3 — Requirements und Spine-Rollout

### Task 3.1: Requirements-Seite vervollständigen

**Ziel:** `/requirements` hat `PageHeader`, `ListToolbar` und `SplitView`, aber keine `ArtifactId` in der Liste, keinen `EmptyState`, keine Spine — und einen eigenen Baum.

**Betroffene Dateien:** `components/RequirementEditors/{RequirementEditors,RequirementList,RequirementTreeNode,RequirementForm}.tsx`

**Akzeptanzkriterium:** Listenzeile ist `<ArtifactRow>`; leere Liste und Filterleere unterschieden; Funktionsumfang inkl. `ReqTraceLinkPanel`, `SimilarRequirementsPanel`, `MarkdownPreview`, `GlossaryTooltip` unverändert.

**Abhängigkeiten:** Phase 1. **Risiko:** mittel — `RequirementEditors.tsx` ist mit ~500 Zeilen und mehreren Panels die dichteste Seite außerhalb des Piloten.

---

### Task 3.2a: Backend-`resolve`-Endpunkt für Artefakt-ID-Auflösung

> **Nutzerentscheidung 2026-08-01: Weg B.** Der Backend-Endpunkt löst das Problem einmal für alle Typen, statt es pro Seite aus bereits geladenen Listen zusammenzustückeln. Damit verlässt dieser Punkt den reinen Frontend-Scope des Plans — bewusst, auf Nutzerwunsch.

**Ziel:** `TraceSpine.tsx` dokumentiert das zugrundeliegende Problem explizit:

> "The trace graph is keyed by Artifact id while the detail routes take domain-entity ids, and no endpoint resolves one to the other for every type — so a host that cannot map an entry says so here instead of offering a dead link."

Ein neuer Endpunkt löst `artifact_id ↔ (entity_type, entity_id)` für alle Artefakttypen zentral auf, statt dass jede Frontend-Seite ihre eigene Liste danach durchsucht.

**Betroffene Dateien (Backend):**
- `backend/rest_api/views.py` (neuer `resolve`-Endpunkt oder Erweiterung des `impact`-Endpunkts um `entity_id`/`entity_type` je Knoten)
- `backend/rest_api/serializers.py`
- `backend/traceability/` (Layer 1) — Lookup-Logik, falls sie dort sauberer sitzt als in der View
- ggf. `backend/rest_api/tests/test_traceability.py` (neue Tests)

**Betroffene Dateien (Frontend):**
- `frontend/src/api/tracelinks.ts` (neuer API-Aufruf)
- `frontend/src/components/shared/TraceSpine/useDerivationChain.ts` (nutzt den Endpunkt statt lokaler Listenauflösung; `isOpenable` bleibt als Fallback für nicht auflösbare Einträge, wird aber zum Ausnahmefall statt Regelfall)

**Akzeptanzkriterium:**
1. Endpunkt liefert für eine gegebene `artifact_id` (oder Liste davon) `entity_type` + `entity_id`, für alle im System bekannten Artefakttypen — auch für nicht geladene Listen.
2. Auf einer Nicht-Architektur-Seite (Requirements) zeigt die Spine die reale Kette, alle auflösbaren Stationen sind klickbar, unabhängig davon ob deren Liste im Frontend geladen ist.
3. Nicht auflösbare Einträge (z.B. gelöschte Artefakte) bleiben über `isOpenable` sichtbar als nicht klickbar markiert, nicht als tote Links.
4. Backend-Regressionslauf (`pytest`) grün, keine neuen RBAC-Lücken (Endpunkt ist read-only, aber tenant-scoped wie alle anderen).

**Abhängigkeiten:** keine (kann parallel zu Phase 1 starten, da reiner Backend+API-Layer). **Risiko:** mittel — Backend-Änderung außerhalb des sonst reinen Frontend-Plans, eigener Review-Zyklus (Layer 1 Traceability ist Kernmodell), eigener PR.

---

### Task 3.2b: Spine-Rollout — Frontend-Anschluss

**Ziel:** Die Spine auf alle Artefakt-Detailansichten bringen, aufbauend auf dem Resolve-Endpunkt aus 3.2a.

**Betroffene Dateien:**
- `frontend/src/components/shared/TraceSpine/useDerivationChain.ts`
- Aufrufer aus Task 3.3

**Akzeptanzkriterium:** wie 3.2a Punkt 2–3, jetzt aus Sicht der aufrufenden Komponenten geprüft (Requirements, Needs, Goals, Quartett).

**Abhängigkeiten:** Task 3.2a, Task 1.1 (Spine-Slot in `SplitView`). **Risiko:** mittel — hier steckt der frontend-seitige Aufwand des Signaturelements, aber ohne das Datenproblem aus 3.2a.

---

### Task 3.3: Spine in Needs, Goals, Requirements, Quartett einhängen

**Ziel:** `<TraceSpine>` erscheint in jeder Artefakt-Detailansicht, in der eine Ableitungskette fachlich existiert.

**Betroffene Dateien:** `RequirementEditors.tsx`, `NeedsEditors.tsx` **[Pilot-Sperre]**, `Goals/GoalsPage.tsx` **[Pilot-Sperre]**, `AdrEditors.tsx`, `RiskEditors.tsx`, `IssueEditors.tsx`, `TestCaseEditors.tsx`

> **Nutzerentscheidung 2026-08-01:** Spine übernimmt die Trace-Anteile, `RightSidebar` wird auf Versionen/Baselines reduziert. Kapitel 3.4 ("Eine Fläche, eine Aufgabe") ist damit erfüllt: Spine = "wo stehe ich in der Ableitungskette", Sidebar = "welche Versionen/Baselines gibt es zu diesem Artefakt".

**Umzusetzen vor/mit dieser Task:** Trace-Link-Anteile aus `shared/ArtifactInspector/RightSidebar.tsx` (bzw. `TracePanel.tsx`) entfernen und durch die Spine ersetzen; `VersionPanel.tsx` bleibt unverändert in der Sidebar.

**Akzeptanzkriterium:** Auf jeder genannten Route ist die Spine sichtbar, solange ein Artefakt geöffnet ist, scrollt nicht mit dem Detailinhalt und wandert unter `--bp-lg` waagerecht unter den Artefaktkopf; `RightSidebar` zeigt nur noch Versionen/Baselines, keine Trace-Links mehr doppelt.

**Abhängigkeiten:** Tasks 3.2a, 3.2b, 1.1, Pilot-Merge. **Risiko:** mittel.

---

## Phase 4 — Baum-Konsolidierung

### Task 4.1: `WorkspaceTree` um Tastaturbedienung erweitern

**Ziel:** Kapitel 12.5. Der vereinigte Funktionsumfang liegt heute auf zwei Komponenten:

| Fähigkeit | `WorkspaceTree` | `DecompositionTree` | `RequirementTreeNode` |
|---|:--:|:--:|:--:|
| `role="tree"` / `treeitem` | ✔ | ✔ | ✖ |
| Virtualisierung (`@tanstack/react-virtual`) | ✔ | ✖ | ✖ |
| Suche/Filter im Baum | ✔ | ✔ | ✖ |
| Tastaturnavigation | **✖** | ✔ (`handleTreeKeyDown`) | ✖ |
| Drag & Drop zum Umhängen | **✖** | ✔ (`draggable`) | ✖ |

**Betroffene Dateien:** `components/shared/WorkspaceTree/workspace-tree.tsx`, `workspace-tree.test.tsx`

**Akzeptanzkriterium:** Die volle ARIA-Tastaturtabelle aus 12.5 (`↑ ↓ → ← Home End`, Buchstabensprung, `Enter`, `*`) ist implementiert und je Taste durch einen Unit-Test belegt — auch im virtualisierten Pfad, wo der Zielknoten erst in den DOM gescrollt werden muss.

**Abhängigkeiten:** keine. **Risiko:** mittel — Tastaturnavigation über einem Virtualizer ist der heikle Teil; nicht gerenderte Knoten müssen trotzdem erreichbar sein.

---

### Task 4.2: Drag & Drop nach `WorkspaceTree` übernehmen, `DecompositionTree` umstellen

**Betroffene Dateien:** `components/shared/WorkspaceTree/workspace-tree.tsx`, `components/ArchitectureEditors/DecompositionTree.tsx`

**Akzeptanzkriterium:** Architektur-Umhängen funktioniert unverändert (Bestandstest `ArchitectureEditors.test.tsx`, `ArchitectureDecomposePanel.test.tsx` grün); `DecompositionTree` enthält keine eigene Baumdarstellung mehr, sondern nur noch Render-Props (Badge, Kontextmenü).

**Abhängigkeiten:** Task 4.1. **Risiko: hoch** — `DecompositionTree` trägt die Architektur-Zerlegung, den fachlich empfindlichsten Baum. Eigener PR, kein Bündel.

> **Nachtrag 2026-08-15 — Aufgabenstellung war überholt, umgesetzt als Neubau.**
>
> Die oben beschriebene Migration ("D&D aus `DecompositionTree` herausheben") ließ
> sich nicht mehr ausführen: `DecompositionTree.tsx` war am 2026-08-03 mit Commit
> `254c8c2` als toter Code gelöscht worden (835 Zeilen, null Consumer). Sein Drag &
> Drop war nie im Produkt sichtbar; `architectureApi.reparent()` hatte zu keinem
> Zeitpunkt einen Aufrufer. Der Architekturbaum rendert seit 2026-07-13
> `WorkspaceTree` direkt und trug dort den Vermerk *„won't do: drag-and-drop
> reparenting (user decision 2026-07-13)"*. Das Akzeptanzkriterium „funktioniert
> unverändert" war damit gegenstandslos — es gab kein Verhalten zu erhalten, und
> die beiden genannten Bestandstests deckten Drag & Drop nie ab.
>
> **Nutzerentscheidung 2026-08-15:** Umhängen per Drag & Drop soll es geben. Die
> Notiz von 2026-07-13 ging auf TODO-004 aus
> `docs/superpowers/specs/2026-07-12-frontend-feedback-strategie-design.md` zurück,
> das *„kein Hierarchie-Tree für **Diagramme**"* festhielt — die Übertragung auf das
> Architektur-Umhängen war eine Ausweitung, die so nicht entschieden worden war.
>
> **Stattdessen umgesetzt (Neubau, nicht Migration):**
> - `WorkspaceTree` bekommt die opt-in Props `onReparent(id, newParentId)` und
>   `rootDropzoneLabel`. Ohne `onReparent` ist das DOM unverändert — die übrigen
>   Consumer (Needs, Requirements, Goals, ADR, Risk, Issue, TestCase, Diagram,
>   Impact) sind nicht betroffen.
> - Client-seitige No-ops: Drop auf sich selbst, Drop auf den aktuellen Parent,
>   Drop in den eigenen Teilbaum. Der Zyklus-Guard nutzt
>   `collectSelfAndDescendantIds` (`shared/WorkspaceTree/tree-hierarchy.ts`) —
>   dieselbe Funktion, die auch die Parent-Auswahl in `ArchitectureForm` filtert,
>   damit beide Wege identisch verbieten. Nötig, weil die serverseitige
>   Invariante I1 nur ab Standard-Rigor läuft, Workspaces aber auf Minimal
>   starten (Nutzerentscheidung 2026-08-15). Restrisiko: direkte REST-/MCP-Aufrufe
>   umgehen den Guard weiterhin.
> - Serverseitige Ablehnungen (I2 Level-Ordnung, I5 eine Wurzel) erscheinen inline
>   im Listen-Banner (#340).
> - `ArchitectureEditors` reicht `onReparent` durch und ruft
>   `architectureApi.reparent()`; der „won't do"-Vermerk ist entfernt.
> - Tests: 23 neue Fälle in `workspace-tree.test.tsx`, 5 in
>   `ArchitectureEditors.test.tsx` (vorher gab es zu Drag & Drop keinen einzigen),
>   plus `tree-hierarchy.test.ts` für den geteilten Zyklus-Helfer.
>
> Das zweite Akzeptanzkriterium („`DecompositionTree` enthält keine eigene
> Baumdarstellung mehr") ist durch die Löschung vom 2026-08-03 erfüllt. Task 4.3 war
> nie von dieser Task blockiert: die dafür nötige Render-Prop (`renderRow`) kam
> bereits mit Task 3.1.

---

### Task 4.3: `RequirementTreeNode` ablösen

**Betroffene Dateien:** `components/RequirementEditors/{RequirementTreeNode,RequirementList}.tsx`

**Akzeptanzkriterium:** `RequirementTreeNode.tsx` ist gelöscht; die Requirements-Liste benutzt `WorkspaceTree` mit Render-Props; Virtualisierung bleibt aktiv.

**Abhängigkeiten:** Task 4.2. **Risiko:** mittel.

---

### Task 4.4: Virtualisierung überall

**Ziel:** Heute setzen nur `NeedList` und `RequirementList` `virtualize`. Nach 4.1–4.3 kostet es je Liste eine Prop.

**Betroffene Dateien:** `AdrList.tsx`, `RiskList.tsx`, `IssueList.tsx`, `TestCaseList.tsx`, `ImpactView.tsx`, plus die in Phase 5 umgestellten Listen.

**Akzeptanzkriterium:** Jede Artefaktliste virtualisiert oberhalb des Schwellwerts; DOM-Knotenzahl bei 500 Einträgen bleibt konstant (Unit-Test mit gemockten Daten).

**Abhängigkeiten:** Task 4.3. **Risiko:** niedrig.

---

## Phase 5 — Restliche Routen

### Task 5.1: ICDs und Diagrams-Rahmen

**Ziel:** `/icds` und `/diagrams` benutzen `SplitView` bereits, aber weder `PageHeader` (beide `h3`) noch `ListToolbar` (eigene Suche) noch `ArtifactRow`.

**Betroffene Dateien:** `components/IcdView/{IcdView,IcdDetailPane}.tsx`, `components/DiagramView/{DiagramView,DiagramDetailView,DiagramCreateForm}.tsx`

**Hinweis:** Nur Kopf, Toolbar, Leerzustand und Zeilendarstellung. Die **Frage, ob Diagramme überhaupt ein Baum-Muster brauchen**, ist Phase 6 und wird hier bewusst nicht beantwortet.

**Akzeptanzkriterium:** je ein `<h1>`, Zusammenfassung immer sichtbar, `ListToolbar` in fester Reihenfolge (Suche → Filter → Sortierung), Smoke-Tests (`IcdView.smoke.test.tsx`, `DiagramView.smoke.test.tsx`) grün.

**Abhängigkeiten:** Phase 1. **Risiko:** niedrig.

---

### Task 5.2: Baselines und Test Runs

**Betroffene Dateien:** `components/BaselinesView/{BaselinesView,BaselinesPanels}.tsx`, `components/TestRuns/{TestRunsList,TestRuns,TestRunDetailEditor}.tsx`

**Besonderheit:** Beides sind keine Artefakttypen im Sinne der Spine — keine Ableitungskette, also **keine** Spine. `PageHeader`, `ListToolbar`, `EmptyState` und die vereinheitlichte `StatusBadge` (Task 1.6) gelten trotzdem. Baselines-Erzeugung ist eine Überlaufaktion, kein Primärknopf.

**Akzeptanzkriterium:** je ein `<h1>`; `BaselinesView.test.tsx`, `BaselinesView.container.test.tsx`, `TestRunsList.test.tsx` grün.

**Abhängigkeiten:** Tasks 1.1, 1.4, 1.6. **Risiko:** niedrig.

---

### Task 5.3: Reviews, Traceability, Impact

**Betroffene Dateien:** `components/Reviews/ReviewsView.tsx`, `components/TraceabilityView/{TraceabilityView,TraceLinksForm}.tsx`, `components/ImpactView/ImpactView.tsx`

**Zu beheben:**
- Reviews: nackter `<h1 style={{marginTop:0}}>` → `PageHeader`.
- Traceability: kein `SplitView`, `h2` als Kopf, eigene Filterleiste. Kapitel 17 Schritt 6 nennt Trace Links ausdrücklich als Split-View-Kandidat.
- Impact: `h2`, eigene Baum-Nachbildung. Nach Phase 4 auf `WorkspaceTree` umstellen.

**Akzeptanzkriterium:** je ein `<h1>`; `TraceabilityView.smoke.test.tsx`, `ReviewsView.test.tsx`, `ImpactView.test.tsx` grün; Impact-Baum nutzt die geteilte Primitive.

**Abhängigkeiten:** Phase 1, für Impact zusätzlich Phase 4. **Risiko:** mittel — `TraceabilityView.tsx` und `TraceLinksForm.tsx` sind zusammen über 50 KB.

---

### Task 5.4: Nicht-Artefakt-Routen minimal angleichen

**Ziel:** `/`, `/metrics`, `/audit`, `/import`, `/settings`, `/system-settings`, `/profile`, `/workflows` sind keine Artefaktlisten, brauchen aber je genau ein `<h1>` (Kapitel 15.1, E2E-Gate aus 16.1).

**Betroffene Dateien:** `DashboardViews/DashboardViews.tsx`, `MetricsDashboard/MetricsDashboard.tsx`, `Audit/audit-dashboard.tsx`, `CsvImport/CsvImport.tsx`, `WorkspaceSettings/WorkspaceSettings.tsx`, `SystemSettings/*`, `UserProfileSettings/*`, `WorkflowEditor/WorkflowEditorHeader.tsx`

**Hinweis:** `WorkflowEditorHeader.tsx` hat bereits ein `<h1>` mit eigenem Modul-Styling. Prüfen, ob es auf `PageHeader` gehoben werden kann oder ob der Editor-Kopf ein begründeter Sonderfall bleibt (er trägt Scope-Umschalter und Bearbeitungsmodus) — falls Sonderfall, **im Konzeptdokument vermerken** (Kapitel 16.3).

**Akzeptanzkriterium:** Jede Route hat genau ein `<h1>`; die letzte Workflow-Editor-Datei ohne `useTranslation` ist übersetzt.

**Abhängigkeiten:** Phase 1. **Risiko:** niedrig.

---

## Phase 6 — Offene Entscheidungen: Glossary und Diagrams

**Diese Phase enthält bewusst keine Aufgaben, sondern Optionen.** Der Nutzer hat erklärt, noch nicht sicher zu sein, ob das SplitView/Tree/Detail-Muster für diese beiden Typen fachlich trägt. Der Plan entscheidet das nicht.

### Entscheidung E1: Glossary

**Ausgangslage (aus dem Code belegt):** `GlossaryTerm` ist flach — `term`, `definition`, `synonyms`, `abbreviation`, `is_global`, `lifecycle_status`. **Kein `parent_id`, keine Version, kein Workflow-Status, kein Ableitungspfad.** `GlossaryView.tsx` ist heute eine einzige 26-KB-Datei mit eigenem Kopf (`<h1>` in `--font-size-2xl` statt `3xl`), eigener Suche, eigenem Filter-Segment und einem Inline-Formular. Es gibt kein `SplitView`, keinen Baum, keine Statusdarstellung. Ein Glossar wird typischerweise **überflogen und durchsucht**, nicht durchnavigiert.

| Option | Beschreibung | Spricht dafür | Spricht dagegen |
|---|---|---|---|
| **G1** | Volles SplitView + Tree wie die Artefaktseiten | maximale Einheitlichkeit (Prinzip 3.1) | Der Baum hätte genau eine Ebene — eine Hierarchie ohne Hierarchie. Kapitel 12.5 verlangt einen Baum, nicht eine Liste im Baumgewand |
| **G2** | SplitView + **flache Liste** (`ArtifactRow` ohne Ebenen-Badge), kein Baum | Detail bekommt Platz für Definition, Synonyme und Verwendungen; Kopf/Toolbar/Leerzustand werden vereinheitlicht | Ein Glossar-Detail ist oft nur zwei Felder — 60 % Bildschirmbreite dafür könnte zu viel sein |
| **G3** | Kein SplitView. Einspaltige, dichte Tabelle mit Inline-Bearbeitung; nur `PageHeader`, `ListToolbar`, `EmptyState` und `Dialog` werden vereinheitlicht | passt zum Nutzungsmuster (scannen, suchen, korrigieren); geringster Umbau; behält die heutige Stärke | weicht sichtbar vom Split-View-Grundmuster ab und braucht deshalb einen Eintrag im Konzept (Kapitel 16.3) |
| **G4** | Glossar wird gar keine eigene Route, sondern ein Panel neben dem Artefakt (`GlossaryTooltip` gibt es bereits in `RequirementEditors/`) | löst das eigentliche Problem — Begriffe werden beim Lesen gebraucht, nicht in einer eigenen Ansicht | größte Änderung, entfernt eine bestehende Route (Kapitel 4, funktionale Untergrenze) |

**Empfehlung des Analysten, nicht Entscheidung:** G3, ergänzt um G4 als späteren Zusatz. Ein Glossar ist ein Nachschlagewerk, kein Ableitungsgraph — das Signaturelement dieses Konzepts (die Spine) hat dort nichts zu zeigen. Erforderlich ist eine Nutzerentscheidung, bevor Aufwand entsteht.

### Entscheidung E2: Diagrams

**Ausgangslage:** `Diagram` hat `name`, `diagram_type`, `description`, `current_version`, `version_count`; `DiagramDetail` zusätzlich `status`. **Keine Elternbeziehung.** `SplitView` ist bereits im Einsatz (`DiagramView.tsx`), der Kopf ist ein `h3`, es gibt keine `ListToolbar`. Es existieren zwei Sondereditoren (`/diagrams/:id/canvas`, `/diagrams/:id/mermaid`), die den ganzen Bildschirm brauchen.

| Option | Beschreibung | Spricht dafür | Spricht dagegen |
|---|---|---|---|
| **D1** | SplitView beibehalten, Liste **flach**, gruppiert nach `diagram_type` als Abschnittsüberschriften | `diagram_type` ist die einzige echte Ordnung in den Daten; billig | Gruppierung ist kein Baum — die Baum-Primitive würde für Nicht-Bäume missbraucht |
| **D2** | SplitView + `WorkspaceTree` mit `diagram_type` als synthetischer Elternebene | eine Baum-Implementierung weniger im Kopf des Nutzers | erfindet eine Hierarchie, die im Datenmodell nicht existiert — Kapitel 5.1 warnt genau davor bei der Spine |
| **D3** | SplitView **nur** für die Übersicht; die Canvas-/Mermaid-Editoren bleiben Vollbild-Routen ohne Liste | Zeichenfläche braucht Platz; entspricht dem heutigen Stand | zwei unterschiedliche Layoutmodi auf derselben Route-Familie |
| **D4** | Vorschau statt Detail: rechts wird das gerenderte Diagramm gezeigt, Bearbeiten öffnet den Vollbildeditor | beantwortet die tatsächliche Frage ("wie sieht es aus?"); Prinzip 3.4 | erfordert eine Renderpfad-Entscheidung (SVG-Vorschau serverseitig vs. clientseitig) |

**Empfehlung des Analysten, nicht Entscheidung:** D1 + D3 + D4 als Ausbaustufe — flache, nach Typ gruppierte Liste, Vorschau rechts, Vollbild zum Bearbeiten. D2 ausdrücklich **nicht**, weil es eine Hierarchie erfindet.

**Was in beiden Fällen unstrittig ist und in Phase 5 mitläuft:** `PageHeader` mit `<h1>`, `ListToolbar` in fester Reihenfolge, `EmptyState` mit Leer/Kein-Treffer-Unterscheidung, `shared/Dialog` fürs Anlegen, keine Hex-Literale. Nur die **Layoutfrage** ist offen.

---

## Phase 7 — Durchsetzung

Kapitel 16. Ohne diese Phase ist der ganze Plan eine Momentaufnahme. Sie läuft **parallel** zu den Phasen 2–5, nicht danach — jedes Gate wird eingeführt, sobald der zugehörige Bereich sauber ist.

### Task 7.1: Token-Existenztest

**Ziel:** Jede `var(--token)`-Referenz in `src/` existiert in `styles/tokens.css`. Das hätte sowohl `--font-size-md` als auch `--color-background` beim Entstehen gefunden.

**Betroffene Dateien:** neu `frontend/src/test/design-tokens.test.ts`

**Akzeptanzkriterium:** Test schlägt fehl, wenn ein unbekanntes Token referenziert wird; läuft nach Task 0.1 grün.

**Abhängigkeiten:** Task 0.1. **Risiko:** niedrig.

---

### Task 7.2: i18n-Paritätstest

**Betroffene Dateien:** neu `frontend/src/test/i18n-parity.test.ts`

**Akzeptanzkriterium:** Test vergleicht die flachen Schlüsselmengen von `en.json` und `de.json` in beide Richtungen und schlägt bei Abweichung fehl. Aktueller Stand: 3 Schlüssel fehlen in `de.json`, 0 in `en.json` — nach Task 0.3 grün.

**Abhängigkeiten:** Task 0.3. **Risiko:** niedrig.

---

### Task 7.3: ESLint-Regeln

**Ziel:** Zwei Regeln aus 16.1, die heute fehlen:
- Keine Hex-Literale in `style={{}}`
- `aria-modal` nur zusammen mit `role="dialog"`

**Betroffene Dateien:** `frontend/eslint.config.js`, ggf. `frontend/eslint-rules/` (lokale Regeln)

**Hinweis:** `jsx-a11y` ist bereits eingebunden, aber alle Regeln stehen auf `warn`. Die Dialog-Regel kann als `no-restricted-syntax` formuliert werden; die Hex-Regel braucht eine eigene kleine Regel.

**Akzeptanzkriterium:** Beide Regeln als `error` aktiv; `npm run lint` grün (nach Task 1.3 gibt es keine `aria-modal`-ohne-`role`-Stelle mehr; Hex-Literale ggf. zunächst per Ratchet, siehe 7.4).

**Abhängigkeiten:** Task 1.3. **Risiko:** mittel — 145 Hex-Literale in 29 Dateien; die Regel darf nicht sofort auf `error` stehen, ohne dass diese abgebaut oder ausgenommen sind.

---

### Task 7.4: Ratchet-Tests

**Ziel:** Sperrklinken-Prinzip (16.2) für die Altlasten, die nicht in einem Zug verschwinden.

**Betroffene Dateien:** neu `frontend/src/test/ui-ratchet.test.ts`, plus eine eingecheckte Baseline-Datei

**Startwerte (Stand 2026-08-01, in der Baseline festzuhalten):**
- `style={{` in `components/` ohne Tests: **1462**
- Hex-Literale in `.tsx` ohne Tests: **145** in **29** Dateien
- Baum-Implementierungen: **3** → nach Phase 4: 1
- Status-Badge-Implementierungen: **3** → nach Task 1.6: 1

**Akzeptanzkriterium:** Test schlägt fehl, sobald ein Wert **steigt**; Baseline wird bei jedem Absenken mit dem PR aktualisiert. Vorbild ist `backend/rest_api/tests/test_architecture.py`, das dasselbe für direkte ORM-Zugriffe tut.

**Abhängigkeiten:** keine. **Risiko:** niedrig. **Wichtig:** So früh wie möglich einführen — der Wert des Ratchets liegt darin, dass er *während* der Phasen 2–5 wirkt, nicht danach.

---

### Task 7.5: E2E-Sonden (nur Spec, keine Ausführung)

**Ziel:** Zwei Gates aus 16.1, die nur dynamisch prüfbar sind:
- Genau ein `<h1>` je Route
- Höchstens 3 Scroll-Container je Route

**Betroffene Dateien:** neu `e2e/tests/ui-konzept-gates.spec.ts`

**Akzeptanzkriterium:** Spec existiert, ist über alle Routen parametrisiert und enthält **kein** `waitForTimeout` (eigenes Gate aus 16.1: heute 35 Vorkommen). **Ausführung nur auf ausdrückliche Anforderung des Nutzers** — kein DoD-Gate.

**Abhängigkeiten:** Phasen 2–5. **Risiko:** niedrig.

---

## Phase 8 — Optional und unabhängig

### Task 8.1: Theming-Zweiteilung (Kapitel 8.6)

**Ziel:** Primitiv- und Semantikebene trennen, damit ein neues Theme keinen Komponentencode anfasst.

**Ausgangslage:** `ThemeContext.tsx` setzt bereits `document.documentElement.dataset.theme` — die Mechanik ist da, sie kennt nur zwei feste Werte. `tokens.css` hat `:root` (dunkel) und `:root[data-theme="light"]`, aber **eine** Tokenebene: semantische Namen tragen direkt Rohfarbwerte.

**Betroffene Dateien:** `frontend/src/styles/tokens.css`, `frontend/src/context/ThemeContext.tsx`, Theme-Umschalter in den Einstellungen

**Vorgehen:** `--palette-*`-Primitive einziehen; `--color-*` zeigen nur noch auf Primitive; die heutigen Blöcke werden **byte-identisch** zu `default-dark` und `default-light` (Kapitel 8.6: Theming ist Erweiterung, kein Redesign). `Theme` wird von einer Union zweier Literale zu einer Theme-ID.

**Akzeptanzkriterium:** Beide Bestandsthemes rendern pixelgleich zu vorher (visuelle Prüfung, beide Themes); ein Beispiel-Drittes-Theme lässt sich **allein** durch einen neuen Primitiv-Block hinzufügen, ohne eine `.tsx` anzufassen.

**Abhängigkeiten:** Task 0.1 (kein undefiniertes Token mehr). **Risiko:** mittel — großer, mechanischer CSS-Diff; Kontrastprüfung pro Theme (8.5) nicht vergessen.

---

### Task 8.2: IBM Plex und `--font-cond`

**Ziel:** Kapitel 9. Der teuerste Teil (Selbst-Hosten) ist **bereits erledigt** — `@fontsource/inter` und `@fontsource/outfit` sind Abhängigkeiten und werden in `src/index.tsx` importiert. Offen ist nur der Familienwechsel.

**Betroffene Dateien:** `frontend/package.json`, `frontend/src/index.tsx`, `frontend/src/styles/tokens.css`

**Offen:** `--font-cond` ist weder definiert noch benutzt (0 Treffer). Es wird erst mit Plex Condensed sinnvoll.

**Akzeptanzkriterium:** `--font-sans`, `--font-mono`, `--font-cond` zeigen auf Plex-Schnitte; `tabular-nums` steht überall dort, wo Zahlen untereinander stehen (Versionen, Zähler, Metrikkacheln); Bezeichnerspalten sind bei gleicher Größe besser scanbar (visueller Vergleich mit Screenshot vorher/nachher).

**Alternative bei Ablehnung des Familienwechsels:** Nur Mono-Schnitt und `tabular-nums` — das ist laut Kapitel 9.2 die Mindestanforderung. `--font-mono` zeigt heute auf einen System-Stack (`ui-monospace, SFMono-Regular, JetBrains Mono, Cascadia Mono`), also nicht selbst gehostet und je Betriebssystem anders.

**Abhängigkeiten:** keine. **Risiko:** niedrig, aber sichtbar — eigener PR, keine Bündelung mit Strukturarbeit.

---

## Reihenfolgeempfehlung

1. **Phase 0** vollständig (klein, sofort, keine Sperren außer 0.3)
2. **Task 7.4** (Ratchet) so früh wie möglich — er wirkt nur, solange noch Arbeit kommt
3. **Task 1.1** (`SplitView`) als eigener PR ohne Seitenmigration — der Flaschenhals
4. **Tasks 1.2 / 1.4 / 1.6** parallel (unabhängig voneinander)
5. **Task 1.3** (Dialogmigration), **Task 1.5** nach Pilot-Merge
6. **Phase 2** — ADRs als Referenzumbau, dann die drei Geschwister
7. **Phase 3** — Requirements und der Spine-Rollout (Task 3.2 ist der inhaltlich schwierigste Einzelposten des Plans)
8. **Phase 5** parallel zu Phase 4, weil sie andere Dateien anfasst
9. **Phase 4** — Baum-Konsolidierung zuletzt unter den Strukturphasen, größtes Regressionsrisiko
10. **Phase 6** erst nach Nutzerentscheidung
11. **Phase 7** begleitend, **Phase 8** jederzeit einschiebbar

---

## Was dieser Plan bewusst nicht tut

- **Keine Entscheidung zu Glossary und Diagrams.** Phase 6 liefert Optionen mit Begründung, keine Festlegung (Nutzerentscheidung 2026-08-01: vertagt).
- **Keine Neugestaltung der Palette.** Kapitel 4: Indigo, Slate, Radien und die Status-Badge-Palette bleiben.
- **Keine E2E-Ausführung.** Specs werden geschrieben, nicht gefahren.

## Entscheidungen 2026-08-01 (Nutzer)

- **Glossary (E1) / Diagrams (E2):** vertagt, nicht Teil des aktuellen Rollouts.
- **Spine ↔ RightSidebar:** Spine = Trace, Sidebar = Versionen/Baselines (siehe Task 3.3).
- **Spine-Rollout (Task 3.2):** Weg B — Backend-`resolve`-Endpunkt (Task 3.2a) statt reiner Frontend-Auflösung. Damit hat der Plan jetzt doch einen Backend-Anteil, bewusst auf Nutzerwunsch.
