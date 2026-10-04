# WP-3b Evidence 05 — Accessibility-Struktur (statisch, kein WCAG-Vollaudit)

Scope: strukturelle Muster, kein WCAG-2.1/2.2-Konformitätsaudit
(das bleibt `accessibility-specialist`).

## 1. Autofokus — Doppel-Fokussierung (CR-41 / QUICK-05)

`Dialog` besitzt eine eigene Fokus-API:

```
components/shared/Dialog/Dialog.tsx:47   import { useFocusTrap } from "./use-focus-trap";
components/shared/Dialog/Dialog.tsx:67   /** Focus target on open. Defaults to the first focusable element. */
components/shared/Dialog/Dialog.tsx:68   initialFocusRef?: RefObject<HTMLElement | null>;
components/shared/Dialog/Dialog.tsx:13   *   - focus moves to the first operable element when it opens,
components/shared/Dialog/Dialog.tsx:16   *   - focus returns to the triggering element when it closes,
```

**`components/TestRuns/TestRunsList.tsx`** enthält **beides** gleichzeitig:

```
TestRunsList.tsx:124   // F-08: preserve the previous `autoFocus` UX — Dialog's focus trap
TestRunsList.tsx:236             initialFocusRef={nameInputRef}
TestRunsList.tsx:258               autoFocus
```

→ Die Doppel-Fokussierung aus dem Vor-Audit ist **weiterhin offen**.
Confidence 100 %: beide Zeilen gelesen, keine Auflösung dazwischen.

Zum Vergleich — die **gelöste** Variante in
`components/RequirementEditors/RequirementEditors.tsx:233-243`:

```
233:  // the title input this form used to `autoFocus`. Pointing initialFocusRef
236:  // Issue #800: the native `autoFocus` attribute used to stay on this input
243:  // now the single source of truth; `autoFocus` was removed from the input.
```

Die Konvention existiert also und ist dokumentiert — sie ist nur nicht erzwungen.

## 2. Weitere `autoFocus` in Produktion (7)

| Datei:Zeile | Kontext |
|---|---|
| `components/AttributeEditor/AttributeCatalogDialog.tsx:157` | `<Dialog>` |
| `components/AttributeEditor/AttributeCreateDialog.tsx:165` | `<Dialog>` |
| `components/AttributeEditor/AttributeEditorPage.tsx:773` | Inline-Formular |
| `components/AttributeEditor/AttributeList.tsx:111` | Inline-Formular |
| `components/GlossaryView/GlossaryView.tsx:330` | Inline-Formular |
| `components/shared/DeriveRequirementForm.tsx:93` | Dialog-Formular |
| `components/ArchitectureEditors/ArchitectureEditors.tsx:514` | Dialog (mit F-08-Kommentar) |

Ohne erzwungenen Check bleibt die Frage „wann `autoFocus`, wann
`initialFocusRef`?" eine Stilfrage pro Datei.

## 3. Klick-Handler auf Nicht-Interaktiv-Elementen

```
grep -rE '<(div|span|li|tr|td)[^>]*onClick' frontend/src --include=*.tsx | grep -v test \
  | grep -v 'role=' | grep -v 'tabIndex'
→ components/shared/ArtifactRow/ArtifactRow.tsx:198
     <span className={styles.idGroup} onClick={(e) => e.stopPropagation()}>
```

**Genau 1 Treffer im gesamten Produktionsbaum.** Das entspricht dem Label
„CR-41 Semantik/Autofocus/Reflow (9 P2/P3-Subteile)" — diese Fehlerklasse ist
weitgehend geschlossen. `stopPropagation()` ohne Rolle/Tabindex ist formal
ein nicht-tastaturbedienbares Klickziel; Schweregrad LOW/P3.

## 4. `aria-live`-Regionen (19 in Produktion)

| Datei:Zeile | Art |
|---|---|
| `components/BaselinesView/BaselinesView.tsx:511` | `polite` |
| `components/DiagramGraphEditor/DiagramGraphEditorPage.tsx:426` | `assertive` bei Fehler, sonst `polite` |
| `components/DiagramGraphEditor/GraphInspectorPanel.tsx:83` | `polite` |
| `components/InterviewWidget/InterviewChatPane.tsx:126` | `polite` |
| `components/InterviewWidget/InterviewWidget.tsx:298` | `polite` |
| `components/shared/ArtifactForm/ArtifactForm.tsx:757,778,809` | `assertive` (3×) |
| `components/shared/ArtifactForm/fields/FieldShell.tsx:163` | `assertive` |
| `components/shared/ArtifactInspector/DiffPanel.tsx:182` | `role="status" aria-live="polite"` |
| `components/shared/EmptyState/EmptyState.tsx:159` | `polite` |
| `components/shared/IdChip/IdChip.tsx:226` | `polite` |

**Toast-Status:** In `ApiKeysSection.tsx:191-197` wird der Fehler über
`role="alert"` ausgegeben (`api-keys-error`), nicht über `aria-live` —
funktional gleichwertig, aber ein anderes Muster als der Rest des Baums.
Kein Befund, nur Konsistenzbeobachtung.

## 5. Fehlergrenzen

```
grep -rn 'getDerivedStateFromError|componentDidCatch' frontend/src | grep -v test
→ components/NavigationShell/ErrorBoundary.tsx:32  export class ErrorBoundary extends Component<
→ components/NavigationShell/ErrorBoundary.tsx:41  static getDerivedStateFromError(error: Error)
→ components/NavigationShell/ErrorBoundary.tsx:45  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
→ components/NavigationShell/ErrorBoundary.tsx:47    console.error("[ErrorBoundary] Unhandled error:", error, errorInfo);
```

Montage: **genau einmal**, in `components/NavigationShell/NavigationShell.tsx:128`
(umschließt Zeilen 128–220, also Routeninhalt **und** Shell-Layout).

Folgen für den Nutzer bei einem Render-Crash:
* Seiteninhalt und Sidebar werden durch denselben Boundary-Baum ersetzt.
* `componentDidCatch` meldet **nur** nach `console.error` — keine Telemetrie,
  kein Report, kein Retry, kein Reload-Hinweis.
* Keine Route-Isolation: ein Crash in einer Artifact-Detailroute reißt die
  gesamte Shell mit.

## 6. Nicht statisch prüfbare Punkte (bewusst offen)

| Punkt | Grund |
|---|---|
| Kontrastverhältnisse | kein Rendering; `test/theme-contrast.test.ts` deckt nur Palette ab |
| Fokus-Reihenfolge / Tab-Fallen | nur zur Laufzeit prüfbar |
| Screenreader-Namen von Icon-only-Buttons | benötigt gerenderten Accessibility-Baum; `data-testid`-Analyse zeigt aber: 752/804 interaktive Elemente tragen bereits `aria-label` oder Text (siehe Evidence 06) |
| Reflow / Zoom | Laufzeit |
| Tastatur-Reihenfolge in `SplitView` / Tabs | Laufzeit |