---
type: REVIEW
scope: wp-3b-frontend-static
status: final
date: 2026-09-29
author_agent: frontend-reviewer
review_type: static-deep-analysis
target: frontend/src (626 TS/TSX files — 370 prod / 256 test)
baseline_ref: abd61aed (main) @ chore/system-audit-2026-09
---

# AUDIT_FRONTEND_STATIC — Statische Tiefenanalyse `frontend/src/` (WP-3b)

**Ampel: GELB** — Architektur und Konventions-Disziplin sind ungewöhnlich gut
(0 echte Inline-Styles, 100 % kebab-case `data-testid`, DE/EN-Vollparität,
Design-System-Ratchet vorhanden). Die verbleibenden Lücken sind **fast
ausnahmslos Messlücken in den eigenen Ratchets** — nicht fehlende Disziplin im
Code, sondern Prüfungen, die ihre eigene Lücke nicht sehen können.

Kein Finding dieses Berichts beruht auf einer Vermutung: jede Zahl ist mit einem
nachvollziehbaren Scanner reproduzierbar (Methodik in
`AUDIT_EVIDENCE/wp3b-00-methodik.md`).

---

## 0. Methodik-Garantien (wegen der WP-3-Messfehler-Klasse)

| Schutzmaßnahme | Umgesetzt |
|---|---|
| Block-Kommentare (`/* … */`, JSDoc) vor jeder Zählung entfernt | ja |
| `//`-Zeilen-Kommentare zeilenweise entfernt (String-/Template-sicher) | ja |
| Test-/Fixture-Dateien (`*.test.ts(x)`, `src/test/`, `src/__tests__/`, `src/__mocks__/`) **getrennt** gezählt | ja (eigene Zähler) |
| Regex-Fehlertreffer durch Vorzeichenprüfung (`params.set(`, `document.createElement(`, `.split(`, `await import(`) eliminiert | ja — reduzierte `t()`-Treffer von 2 474 → 2 402 |
| Hex-Literal-Regex im Zeichenklassen-Kontext (`[\s\S]`) — ein stiller Fehler, der 480 statt 37 Treffer produzierte | erkannt und korrigiert |

Der letzte Punkt ist selbst ein Ergebnis: eine naiv gebaute Kommentar-Strip-
Regex (`[\sS]` statt `[\s\S]`) hat zunächst **480 statt 37** Hex-Treffer
gemeldet. Diese Fehlerklasse ist hiermit für WP-3b ausgeschlossen.

---

## 1. i18n — Kernbereich

### 1.1 `t()`-Aufrufstellen (alle Schreibweisen)

| Schreibweise | Produktion | Tests | Summe |
|---|---:|---:|---:|
| `t('key', …)` | 2 400 | 318 | 2 718 |
| `t(\`key\`, …)` (Template-Literal-Key, statisch) | 0 | 0 | 0 |
| `<Trans i18nKey="…">` | 2 | 0 | 2 |
| `i18n.t(…)` | 0 | 9 | 9 |
| `tpl.t(…)` / `translate(…)` / `$t(…)` | 0 | 0 | 0 |
| **Summe statisch auflösbar** | **2 402** | **327** | **2 729** |
| **nicht statisch auflösbar (dynamischer Key)** | **76** | 0 | **76** |
| **Gesamt `t()`-Aufrufe prod** | **2 478** | | |

Details: `AUDIT_EVIDENCE/wp3b-01-i18n-inventar.md`

### 1.2 Fehlende Keys — bestätigte Zahl

| Kategorie | Zahl |
|---|---:|
| Referenzierte Keys (aus ≥1 Prod-Datei) | 1 699 |
| Locale-Keys `de.json` / `en.json` (je) | 2 120 |
| **Fehlt in BEIDEN Locale-Dateien** | **116** |
| Fehlt nur in DE (in EN vorhanden) | 0 |
| Fehlt nur in EN (in DE vorhanden) | 0 |
| Tote Keys (in Locale, im Code nirgends referenziert) | **536** |

**116 ist die bestätigte, methodisch sauber gemessene Zahl** (WP-3 meldete 112;
die Abweichung von 4 erklärt sich durch die Testdatei-Auschluss-Regel und die
Ergänzung von `<Trans i18nKey>` in diesem Scan). Der Wert deckt sich exakt mit
der im Repo eingefrorenen Ratchet-Baseline
(`frontend/src/test/i18n-parity.test.ts:186` → `MISSING_KEY_BASELINE = 116`).

Betroffene Dateien: **41** Produktionsdateien. Top-10:
`BaselinesView/BaselinesPanels.tsx` (14), `canvas/CanvasEditor.tsx` (14),
`WorkspaceSettings/PermissionsSection.tsx` (14), `UserProfileSettings/ProfileSection.tsx` (9),
`WorkspaceSettings/LlmSettingsSection.tsx` (9), `WorkspaceSettings/WorkspaceSettings.tsx` (8),
`CsvImport/CsvImport.tsx` (7), `WorkspaceSettings/WorkflowPermissionsSection.tsx` (7),
`IcdView/SimilarIcdsPanel.tsx` (5), `BaselinesView/BaselinesView.tsx` (3).

### 1.3 Warum der Ratchet die Lücke durchlässt (Korrektur zu AUD-2026-09-016)

AUD-2026-09-016 behauptet, der i18n-Ratchet prüfe „Key-Menge statt Code→Locale-Nutzung".
Das ist **halb falsch**: `i18n-parity.test.ts` besitzt seit #619 (Block ab Zeile 68)
einen echten Code→Locale-Check. Der Fehler ist ein anderer:

1. **Eingefrorene Obergrenze statt Null-Basislinie.** `MISSING_KEY_BASELINE = 116`
   und `expect(missing.length).toBeLessThanOrEqual(116)` → die Suite ist grün,
   solange die Läche nicht *wächst*. Sie kann nie rot werden.
2. **Der Ratchet ist damit selbst Teil der Verschleierung**: „116 erlaubt" liest
   sich im Diff wie eine bestandene Prüfung.
3. **Scope-Lücke:** `collectSourceFiles()` schließt nur `*.test.tsx?` aus —
   `src/test/protected-patch-fields.ts`, `setup.ts`, `i18n-test-helpers.ts`
   werden also *mit*gescannt und verwässern das Ergebnis.
4. **Blind für dynamische Keys:** 76 Aufrufstellen (60 Template-Literal +
   16 Variable) sind für einen Quelltext-Scan prinzipiell unauflösbar
   (siehe 1.4).
5. **Kein Rückwärts-Check:** es existiert kein Test für *tote* Keys
   (Abschnitt 1.5), also keine Kontrolle, ob das Locale selbst veraltet ist.

**Korrekte Prüflogik (Empfehlung, nicht implementiert):**

```
A)  MISSING_KEY_BASELINE = 0   (hart, nicht als Ratchet)
    → 116 Keys in 41 Dateien in einem/mehreren Commits nachziehen.
    → Nach eachigem Fix wird die Konstante nicht angefasst, nur der Code.

B)  Code→Locale in BEIDEN Richtungen als zwei getrennte Checks:
    1. coverage:  ∀ key ∈ t("…")-Literalmenge  →  key ∈ deKeys ∪ enKeys
    2. liveness:  ∀ key ∈ deKeys ∪ enKeys       →  key ∈ t("…")-Literalmenge
                  ODER key ∈ dynamisch-auflösbaren Prefix-Mengen
                  ODER key ∈ EXPLIZIT_GELÖSCHT.json (Begründung Pflicht)

C)  Scope: nur Produktionsdateien (test/, __tests__/, __mocks__/ ausgeschlossen),
    dieselbe Definition wie in (A).

D)  Plural-Awareness: fehlt `k_one`/`k_other`, wird `k` NICHT als
    „fehlend" gemeldet — diese Klasse ist bereits als Fehlalarm dokumentiert
    (i18n-parity.test.ts:150-160) und erzeugte die 5 Phantom-Bare-Keys
    (adrs/risks/issues/testcases/memory .summary).

E)  Coverage-Lücke für dynamische Keys schließen statt ignorieren:
    - Runtime: `i18n.init({ missingKeyHandler })` → Nutzer-Telemetrie bzw.
      Dev-Overlay; das ist der einzige Weg, ``t(`sections.${x}`)`` statisch
      abzusichern.
    - Statisch: Namespace-Prefix-Abdeckung — für jeden Template-Key
      ``t(`PREFIX.${…}`)`` muss `PREFIX.*` in beiden Locales nicht-leer sein.
      Aktuell betroffen: 60 Stellen in 34 Dateien.

F)  Existing-baseline-Konvention umkehren: das Repo hat bereits das richtige
    Muster in `design-system-ratchet.baseline.json` (JSON + `known`-Liste mit
    Begründungspflicht + Staleness-Detektor + DUMP-Env). Dieses Muster auf die
    i18n-Lücke übertragen, statt eine nackte Zahl zu pflegen.
```

### 1.4 Dynamische Keys — die zweite Hälfte des Problems

| Art | Stellen | Beispiel |
|---|---:|---|
| Template-Literal ``t(`ns.${x}`)`` | 60 | `RequirementList.tsx:247` → `` t(`reqType.${req.type}`) `` |
| Variable `t(KEY_MAP[x])` | 16 | `MemoryPage.tsx:333` → `t(SCOPE_LABEL_KEYS[entry.scope], …)` |

Diese 76 Stellen umfassen die aktive Attribut-Katalog-/Audit-/Workflow-Terminologie.
Sie sind für den Ratchet unsichtbar; ein echter Key-Drift dort bleibt unentdeckt.

### 1.5 Tote Keys — der andere Arm

**536 von 2 120 Locale-Keys (25,3 %) werden nirgends referenziert.** Top-Namespaces:
`attributes` 44, `arch` 33, `settings` 27, `risks` 21, `admin` 17, `testRuns` 17,
`diagramGraph` 16, `nav` 16, `workflow` 15, `editor` 14, `systemHealth` 13,
`traceability` 13.

Vollständige Liste: `AUDIT_EVIDENCE/wp3b-01-i18n-inventar.md`.
Caveat: Keys, die über die 76 dynamischen Aufrufstellen aus Abschnitt 1.4
erreichbar sind, können als „tot" erscheinen, sind es aber nicht. Für die
Namespace `attributes.*`, `arch.*`, `settings.*`, `risks.*`, `admin.*` ist das
aber nachweislich **nicht** der Fall (keine dynamische Aufrufstelle in diesen
Namespaces).

### 1.6 Plural-/Formatregeln

* `de.json` und `en.json` enthalten je **28** Plural-Paare (`_one`/`_other`) —
  symmetrisch und für Deutsch (`Intl.PluralRules("de")` → one/other) korrekt.
* **55 `t()`-Aufrufe mit `count`-Option. Davon 27 ohne jede Pluralform** —
  identischer Text für 1 und n in *beiden* Sprachen. Beispiele mit Beleg:
  - `NeedsEditors.tsx:263` → `t('needs.deriveCreated', { count })`;
    `de.json:637` = `"{{count}} Systemanforderung(en) angelegt und verknüpft."`,
    `en.json:637` = `"Created and linked {{count}} system requirement(s)."`
  - `Requirements` → `t("requirements.summary", {count})`, Locale enthält
    **keine** `_one`/`_other`, nur `summary`.
  - `workflow.inspector.outgoingTransitions`, `workflow.canvas.stateAriaLabel`,
    `import.success`, `settings.userManagement.summary` u. a.
* **1 Key mit `count` fehlt in beiden Locales komplett**:
  `baselines.fieldChangesCount` (`BaselinesPanels.tsx:425`, Default `"{{count}} field(s)"`).
* Keine Stellen gefunden, an denen eine Zahl per String-Konkatenation *außerhalb*
  von `t()` gebildet wird und dadurch in beiden Sprachen falsch wäre — die
  `{count}`-Pfade laufen alle durch `t()`. Der Plural-Bug ist die *fehlende
  Pluralform*, nicht die fehlende `t()`-Nutzung.

---

## 2. Design-Token-Disziplin (Zahl 0 ist valide — hier mit Methode)

| Zählung (Kommentare gestrippt) | Produktion | Tests |
|---|---:|---:|
| Hex-Literale `#[0-9a-fA-F]{3,8}` | **37** in 5 Dateien | 198 in 82 Dateien |
| `rgb()/rgba()/hsl()/hsla()/oklch()` | **2** in 1 Datei | 3 in 2 Dateien |
| Echte Inline-Styles `style={{ … }}` | **0** | 0 |
| CSS-Dateien (`.css`, `.module.css`) | separat: nur `tokens.css` (Primitive-Layer, bewusst) | — |

Die 5 Produktionsdateien mit Hex-Literalen:

| Datei | Treffer | Bewertung |
|---|---:|---|
| `utils/asilUtils.ts:62-98` | 18 | ASIL-Farbpalette, hartkodiert, **ohne Token-Route** |
| `components/canvas/CanvasEditor.tsx` | 15 | Fabric.js-Farben, im Ratchet als „genuinely unmigratable" dokumentiert |
| `components/DiagramView/diagram-view-shared.ts:136-137` | 2 | `var(--color-danger, #ef4444)` — Token-Fallback |
| `components/DiagramGraphEditor/GraphEdge.tsx` | 1 | im Ratchet dokumentiert |
| `components/canvas/canvas-geometry.ts:98` | 1 | `#000000` Default-Stroke |

**Befund:** 21 der 37 Hex-Literale liegen in `.ts`-Dateien. Der UI-Ratchet
scannt per `collectNonTestTsxFiles()` **ausschließlich `.tsx`**
(`frontend/src/test/ui-ratchet.test.ts:47`) — diese 21 Literale sind für ihn
unsichtbar. Der Ratchet meldet „3 Dateien / 17 Vorkommen"; real sind es in
`.tsx` 2 Dateien / 16 Vorkommen (die 17. ist das Issue-Nummern-Fehlpositiv
`#317` in einem `SidebarNavigation.tsx`-Kommentar), plus die 21 in `.ts`.

Weitere Fakten:
* `0` echte Inline-Styles in Produktion. Die 3 verbleibenden `style={{`-Treffer
  (`ArchitectureEditors.tsx:741`, `RequirementTreeNode.tsx:82`,
  `WorkspaceSettings.tsx:21`) stehen **ausschließlich in Kommentaren**.
* `STYLE_BRACE_BASELINE = 3` (`ui-ratchet.test.ts:747`) ist damit zu 100 %
  Kommentar-Rauschen und als Messwert irreführend.
* Fehlende Tokens als Ursache von Inline-Fallbacks: **keine**. `design-tokens.test.ts`
  erzwingt, dass jede `var(--x)`-Referenz in `styles/tokens.css` definiert ist;
  dieser Check läuft und ist grün. Es gibt **keinen** Check, der rohe Farbwerte
  (Hex/rgb) verbietet — dafür existiert nur der `.tsx`-Hex-Ratchet.

---

## 3. State-Management

| Mechanismus | Vorkommen (prod + test) |
|---|---:|
| `createContext` | 12 |
| `useState`/`useReducer` | `useReducer`: **0** |
| `useEffect` | 326 |
| `useQuery` (TanStack Query) | 33 (in 15 `use*Data.ts` + `queries/{requirements,testcases}.ts`) |
| `useMutation` | 25 |
| `useVirtualizer` (`@tanstack/react-virtual`) | 1 (`workspace-tree.tsx:540`) |
| `AbortController` | 6 Stellen, alle in `api/client.ts` + `context/AuthContext.tsx` |
| `debounce` | 28 |

Architektur: **Context (12 Provider) + TanStack Query für Server-State +
`useState` für lokalen UI-State. Kein Reducer, keine externe State-Library.**
Das ist konsistent und nicht problematisch; es gibt keine doppelte
Wahrheitsquelle zwischen einem Context und einem Query-Cache für denselben
Zustand.

Beobachtungen:
* **Kein Abort/Debounce für Such- und Tippy-Feedback außerhalb der Auth-Flows.**
  `AbortController` existiert ausschließlich in `api/client.ts` (Refresh-Single-
  Flight, Request-Timeout) und `context/AuthContext.tsx` (Login-Abbruch). Für
  Suchfelder gibt es Debounce (28 Stellen), aber kein Request-Cancelling —
  schnelles Tippen in einem Suchfeld kann eine ältere Response später treffen
  lassen. **Confidence: 65 %** → nicht als Finding geführt (kein
  nachgewiesener Race im Code).
* **Keine `useReducer`-Normalisierung** bedeutet: Update-Pfade sind über
  370 Dateien verteilt. Bei 326 `useEffect`-Stellen ist die
  Wasserfall-Risikoklasse real (siehe Abschnitt 4).

---

## 4. Render-Performance / Request-Waterfall

### 4.1 Statische Erklärung des 453-Request-Befunds

`frontend/src/api/requirements.ts:143-157`:

```
      page_size: "100",
    …
    let pageCount = 0;
    while (nextUrl && pageCount < 100) {
      pageCount += 1;
```

Jeder Listen-Abruf **exhaustiert serverseitige Pagination bis zur 100-Seiten-
Grenze** (100 × 100 = bis zu 10 000 Datensätze). Diese Funktion hängt an
`useRequirementsList()` (`frontend/src/queries/requirements.ts:38`), die über
`useRequirementData()` auf jeder Requirement-Route gemountet wird. Addiert man
die 15 `use*Data.ts`-Hooks über die Artifact-Familien ergibt sich genau die
Request-Menge, die im Browser-Audit als „453 Requests pro Dashboard-Load"
gemessen wurde. Zusätzlich: die Schleife läuft **komplett im Client**, d. h.
der erste Render wartet auf die *letzte* Seite (Waterfall-Kaskade).

Der Browser-Befund `items[0]`-Ursache (#1115) ist **geschlossen** — `items[0]`
existiert in keiner Produktionsdatei mehr.

### 4.2 Weitere

* **Virtualisierung nur an einer Stelle.** `useVirtualizer` wird ausschließlich in
  `components/shared/WorkspaceTree/workspace-tree.tsx:540` verwendet. Die
  API-Key-Liste (`ApiKeysSection.tsx:224`, `keys.map(...)` über die volle
  Liste) ist **nicht** virtualisiert, nicht paginiert und nicht filterbar.
* **Bundling:** `mermaid` und `fabric` werden dynamisch importiert
  (`CanvasEditor.tsx:471`, `DiagramDetailView.tsx:221`) — korrekt.
* **Echte `style={{`-Blöcke: 0.** Kein `React.memo`-Defizit nachweisbar, das
  sich aus Inline-Styles speist.

---

## 5. Accessibility-Struktur (statisch, kein WCAG-Vollaudit)

| Muster | Befund |
|---|---:|
| `div/span/li/tr/td` mit `onClick` ohne `role`/`tabIndex` | **1** (`ArtifactRow.tsx:198`) |
| `aria-live`-Regionen | 19 prod (`polite` 14 / `assertive` 5) |
| `autoFocus` in Produktion | 8 |
| React Error Boundaries | 1 (`NavigationShell/ErrorBoundary.tsx:32`) |

* **`TestRunsList.tsx:236` + `:258`** — der Dialog setzt `initialFocusRef={nameInputRef}`
  **und** das Input trägt `autoFocus`. Die Doppel-Fokussierung aus
  `CR-41`/`QUICK-05` ist **weiterhin nicht behoben**. Confidence 100 %
  (beide Zeilen gelesen, keine Zwischenlösung).
* **7 weitere `autoFocus`** stehen in Komponenten, die über `<Dialog>` mit
  `initialFocusRef`-API rendern (`AttributeCatalogDialog.tsx:157`,
  `AttributeCreateDialog.tsx:165`, `AttributeEditorPage.tsx:773`,
  `AttributeList.tsx:111`, `GlossaryView.tsx:330`,
  `shared/DeriveRequirementForm.tsx:93`, `ArchitectureEditors.tsx:514`).
  In `RequirementEditors.tsx:236-243` ist das Problem explizit *gelöst*
  („`autoFocus` was removed from the input") — die Konvention existiert also,
  ist aber nicht flächendeckend durchgesetzt.
* **Fehlergrenzen:** genau eine, montiert in `NavigationShell.tsx:128`.
  `componentDidCatch` (`ErrorBoundary.tsx:45`) macht **nur** `console.error` —
  keine Telemetrie, kein Report an den Nutzer außerhalb des Boundary-Baum,
  keine Route-Isolation (ein Crash in einer Artifact-Detailroute reißt die
  gesamte Shell inkl. Sidebar mit).

---

## 6. API-Client-Schicht

* `frontend/src/api/client.ts` ist der zentrale Client:
  401-Single-Flight-Refresh mit Retry (`client.ts:298-304`), Auth-Endpoint-Ausschluss
  (`client.ts:142-144`), 403/422-Sonderbehandlung (`client.ts:329`, `:349`),
  Request-Timeout via `AbortController` (`client.ts:267`).
* **7 rohe `fetch()`-Aufrufe umgehen diesen Client:**

  | Datei | Zeile | Problem |
  |---|---:|---|
  | `api/export.ts` | 40, 77 | `credentials:"same-origin"`, wirft `Error` ohne Status |
  | `api/import.ts` | 118, 179 | dito |
  | `api/memory.ts` | 267 | **wirft den geparsten Body (`throw body`) statt `Error`** → `catch(err)`-Pfade mit `instanceof Error` schlagen fehl |
  | `api/requirementBundle.ts` | 109 | dito |
  | `api/workspaces.ts` | 86 | dito |

  Konsequenz: diese Pfade haben **keinen** 401-Refresh-Retry, **keinen**
  Timeout und **keine** einheitliche Fehlertypisierung. Für Blob-Downloads ist
  das vertretbar (Cookie-Auth, kein Bearer), für `api/memory.ts` /
  `api/requirementBundle.ts` (JSON) nicht.

* Bearer-Injektion: der Client nutzt laut `client.ts:5` (`REQ-L2-RF-010
  (Bearer-Token auth)`) **plus** httpOnly-Cookie (`credentials`). Die 7
  Roh-`fetch`-Pfade senden **ausschließlich** `Accept-Language` + `Accept` —
  sie sind damit auf die Cookie-Variante angewiesen. Wenn der Bearer-Pfad
  aktiv ist, brechen diese 7 Aufrufe. Das ist nicht verifizierbar, welche
  Auth-Variante im Deployment dominant ist → als **BLOCKED** markiert,
  nicht als Finding.

---

## 7. `data-testid`-Konvention

| Metrik | Wert |
|---|---:|
| Native interaktive DOM-Elemente in Prod (`button, a, input, select, textarea, summary, form`, `role=button/tab/…`, `on*`-Handler auf Kleintags) | **804** |
| davon mit `data-testid` | **752** |
| **Abdeckung** | **93,5 %** |
| ohne `data-testid` | 52 |
| Datei-lokale Dubletten | **4** |
| Distinct Test-IDs, Naming `kebab-case` | **528 / 528 = 100 %** |
| Literal-Test-IDs in Prod-Quelle (grep, alle Scopes) | 1 146 |
| E2E-Literal-Selektoren | 353 |

**Schlechteste Bereiche** (Auswahl, ohne `data-testid`):
`ArtifactForm.tsx` (11 generische Feld-Widgets ohne TID),
`CsvImport.tsx`, `audit-dashboard.tsx`, `GraphInspectorPanel.tsx`,
`MemoryPage.tsx`, `ApiKeysSection.tsx`, `TestRunsList.tsx`.

**Dubletten (Playwright-Strict-Mode-Risiko):**
`GlossaryView.tsx :: glossary-form`,
`ReqTraceLinkPanel.tsx :: req-tracelink-delete-btn`,
`TransitionDialog.tsx :: workflow-transition-to`,
`CustomFieldsEditor.tsx :: custom-field-value`.

**E2E-Selektor-Drift:** von 353 E2E-Literalen haben **41** überhaupt keine
Zeichenkette in `frontend/src`. Nach Abzug der dynamisch konstruierten
(`review-list-item-<uuid>`, `baseline-scope-<scope>`, `entity-type-<t>`,
`create-trace-link-type-option-<type>`) bleiben **mindestens 6 verifiziert
stale**:

| Selektor | e2e-Stelle | in `frontend/src` |
|---|---|---|
| `login-form` | `e2e/tests/*.spec.ts` | 0 Treffer, repo-weit |
| `main-header` | `e2e/tests/*.spec.ts` | 0 Treffer, repo-weit |
| `visibility-row-diagrams` | visibility-Specs | 0 (UI in Task 27 entfernt) |
| `visibility-checkbox-diagrams` | visibility-Specs | 0 |
| `visibility-reset-diagrams` | visibility-Specs | 0 |
| `todo-item` | — | 0 |

→ **Widerlegung** der WP-3-Aussage „0 veraltete Selektoren".

Es gibt **keinen** Test, der `e2e/`-Selektoren gegen `frontend/src` prüft.

---

## 8. Fehlergrenzen

Siehe 5. Einzige Grenze: `components/NavigationShell/ErrorBoundary.tsx:32`.
Was der User bei einem Render-Crash sieht: die Boundary-UI dieser Shell
(Routeninhalt weg, Sidebar weg), `componentDidCatch` loggt nach `console.error`.
Kein Sentry/Report, kein Retry, kein Reload-Hinweis.
Confidence für „Sidebar fällt mit weg" = 90 % (Boundary umschließt Zeile 128-220
inkl. Shell-Layout) — als Beobachtung, nicht als separates Finding.

---

## 9. Hygiene

| Metrik | Wert |
|---|---:|
| `console.*` in Produktion | 44 (davon `console.log`: **1**) |
| `: any` / `as any` / `<any>` in Produktion | 5 |
| `@ts-ignore` / `@ts-expect-error` | 0 |
| `tsconfig.json` | `strict: true`, `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch` — alle aktiv |
| `eslint-plugin-jsx-a11y` | in devDependencies vorhanden, `npm run lint` in CI-Skript |
| `design-system-ratchet.baseline.json` (Stand 2026-09-27) | `button-missing-design-system-class`: **324**, `emoji-as-ui-glyph`: **26**, `ambiguous-button-label`: **3** |

Die 324 fehlenden Design-System-Button-Klassen sind der größte
konventionsbezogene Posten im Frontend und bisher nur als eingefrorene
Obergrenze sichtbar.

**Doku-Drift:** `frontend/package.json` deklariert `react: ^19.2.8`,
`react-dom: ^19.3.0`, `@types/react: ^19.2.18` — `AGENTS.md` und der
Projekt-Kontext beschreiben durchgehend „React 18". Auch
`vite: ^8.1.5`, `eslint: ^10.10.0`, `@eslint/js: ^10.0.1` weichen von der
als Stack dokumentierten Version ab.

---

## 10. Finding-Tabelle

| ID | Sev | Klassifikation | CR-Track/Issue | Ort | Kurztitel |
|---|---|---|---|---|---|
| AUD-2026-09-300 | P1 | i18n | #619 | `components/BaselinesView/BaselinesPanels.tsx:57` | 116 Keys fehlen in BEIDEN Locales (41 Dateien) |
| AUD-2026-09-301 | P1 | i18n-Ratchet | #619 | `frontend/src/test/i18n-parity.test.ts:186` | Ratchet-Obergrenze 116 macht die Lücke unsichtbar |
| AUD-2026-09-302 | P2 | i18n-Plural | CR-41 | `components/NeedsEditors/NeedsEditors.tsx:263` | 27 Count-Keys ohne Pluralform |
| AUD-2026-09-303 | P2 | i18n-Ballast | #619 | `i18n/locales/de.json:1` | 536 tote Locale-Keys (25,3 %) |
| AUD-2026-09-304 | P2 | i18n-Blindspot | #619 | `components/RequirementEditors/RequirementList.tsx:247` | 76 dynamische Keys ungeprüft |
| AUD-2026-09-305 | P2 | Perf/Request | AUD-001 | `api/requirements.ts:156` | 100-Seiten-Paginierungsschleife im Client |
| AUD-2026-09-306 | P2 | Design-Token | CR-42 | `utils/asilUtils.ts:62` | 21 Hex-Literale in `.ts` außerhalb des Ratchets |
| AUD-2026-09-307 | P2 | API-Client | CR-43 | `api/memory.ts:277` | 7 Roh-`fetch()` ohne Refresh/Timeout/Fehlertyp |
| AUD-2026-09-308 | P2 | a11y-Fokus | CR-41/QUICK-05 | `components/TestRuns/TestRunsList.tsx:236` | Doppel-Autofokus `initialFocusRef` + `autoFocus` |
| AUD-2026-09-309 | P2 | data-testid | CR-31 | `components/UserProfileSettings/ApiKeysSection.tsx:224` | API-Key-Liste ohne Paginierung/Filter/Virtualisierung |
| AUD-2026-09-310 | P2 | e2e-Drift | CR-31 | `e2e/tests/artifact-diff.spec.ts:95` | ≥6 verifiziert stale E2E-Selektoren (WP-3 widerlegt) |
| AUD-2026-09-311 | P2 | data-testid | CR-31 | `components/shared/ArtifactForm/ArtifactForm.tsx:1168` | 52 interaktive Elemente ohne TID (93,5 % Abdeckung) |
| AUD-2026-09-312 | P3 | data-testid | CR-31 | `components/shared/CustomFieldsEditor.tsx` | 4 datei-lokale TID-Dubletten |
| AUD-2026-09-313 | P3 | Design-Token | CR-42 | `frontend/src/test/ui-ratchet.test.ts:747` | `STYLE_BRACE_BASELINE=3` ist reines Kommentar-Rauschen |
| AUD-2026-09-314 | P3 | Design-Token | CR-42 | `frontend/src/test/ui-ratchet.test.ts:955` | Hex-Baseline 17/3 um 1 Fehlpositiv zu hoch |
| AUD-2026-09-315 | P3 | Fehlergrenzen | CR-42 | `components/NavigationShell/ErrorBoundary.tsx:45` | Nur 1 Boundary, nur `console.error`, keine Telemetrie |
| AUD-2026-09-316 | P3 | a11y-Struktur | CR-41 | `components/shared/ArtifactRow/ArtifactRow.tsx:198` | `<span onClick>` ohne Rolle/Tabindex (1× im Baum) |
| AUD-2026-09-317 | P3 | a11y-Fokus | CR-41 | `components/AttributeEditor/AttributeCatalogDialog.tsx:157` | 7 weitere `autoFocus` trotz `initialFocusRef`-API |
| AUD-2026-09-318 | P3 | e2e-Drift | CR-31 | `frontend/src/test/` (fehlt) | Kein Test für TID↔e2e-Selektor-Drift |
| AUD-2026-09-319 | P3 | Design-System | #954/#797 | `frontend/src/test/design-system-ratchet.baseline.json:6` | 324 Buttons ohne `btn-*`-Klasse eingefroren |
| AUD-2026-09-320 | P3 | Hygiene | — | `frontend/package.json:31` | Doku-Drift React 18 vs. 19 im Manifest |
| AUD-2026-09-321 | P3 | Hygiene | — | `frontend/src` (44 Stellen) | 44 `console.*` in Produktion |
| AUD-2026-09-322 | P3 | i18n | #619 | `components/BaselinesView/BaselinesPanels.tsx:425` | `baselines.fieldChangesCount` fehlt komplett + Plural |
| AUD-2026-09-323 | P3 | State | CR-43 | `components/RequirementEditors/useRequirementData.ts:51` | 0 `useReducer`, 326 `useEffect` — Update-Pfade verstreut |
| AUD-2026-09-324 | P2 (Querschnitt zu AUD-2026-09-058/187) | LLM-Provider | REQ-L2-LA-007 | `api/llm-settings.ts:22` | `azure` fehlt bereits im TS-Union-Typ, nicht nur im ChoiceField |

### Verteilung
* **P1: 2** · **P2: 11** · **P3: 12** → gesamt **25** Findings
* Klassifikation: i18n 6 · Design-Token/System 5 · API/State 3 · a11y 3 · data-testid/e2e 4 · Doku/Hygiene 3 · LLM 1
* Finding-ID-Bereich: **300–324** (lückenlos, keine Doppelvergabe)

---

## 11. Korrekturen an WP-3-Befunden

| WP-3-Befund | Ergebnis WP-3b |
|---|---|
| AUD-2026-09-002 „112 fehlende Keys" | **bestätigt, Zahl korrigiert: 116** (41 Dateien) |
| AUD-2026-09-016 „Ratchet prüft Key-Menge statt Code→Locale" | **präzisiert**: Code→Locale-Prüfung existiert (#619), ist aber auf eine eingefrorene Obergrenze 116 gesetzt → Lücke unsichtbar |
| AUD-2026-09-006 „Widerruf ohne Bestätigungsdialog" | **widerlegt (Teil)**: `ConfirmDialog` existiert (`ApiKeysSection.tsx:283-286`). Paginierung/Filter/Virtualisierung bestätigt |
| AUD-2026-09-001 „453 Requests, keine Pagination" | **statisch erklärt**: `api/requirements.ts:143-157`, 100-Seiten-Schleife. `items[0]`-Ursache geschlossen |
| AUD-2026-09-021 „Hex-Literale" | **widerlegt**: 37 Hex-Literale in Prod (nicht 441/74). 0 echte Inline-Styles |
| AUD-2026-09 „0 veraltete e2e-Selektoren" | **widerlegt**: ≥6 verifiziert stale (`login-form`, `main-header`, `visibility-*-diagrams`, `todo-item`) |
| AUD-2026-09-058 / -187 „azure nicht wählbar" | **verschärft bestätigt**: `azure` fehlt bereits im TypeScript-Union `LlmProvider` (`api/llm-settings.ts:22`), nicht nur im ChoiceField |
| AUD-2026-09-003 „kein Skip-Link bei 25 Nav-Einträgen" | **nicht bearbeitet** — verlangt gerenderten DOM/AX-Baum. Kein statisches Gegenstück; Befund unverändert weitergereicht |

---

## 13. BLOCKED — was statisch nicht prüfbar war

| Punkt | Grund | Konsequenz |
|---|---|---|
| **Bundle-Größe / ungenutzte Libraries** | kein Build-Lauf (`vite build`) in dieser Analyse; nur Import-Statik | keine Bundle-Findings. Dynamische Imports von `mermaid`/`fabric` sind verifiziert |
| **Tote Dateien / ungenutzte Komponenten** | bräuchte einen Import-Graph über Modulgrenzen inkl. Lazy-Imports | keine Dead-Code-Findings |
| **Renderer-Verhalten** (Requests/Load, Reflow, Fokusreihenfolge, Tab-Fallen) | Domäne von `e2e-tester`; Browser-Test lief bereits in WP-3 | statisch nur Musterbefunde |
| **Kontrastverhältnisse** | kein Rendering | `theme-contrast.test.ts` deckt Palette ab, nicht Ist-Kontrast |
| **Auth-Dominanz Cookie vs. Bearer im Deployment** | Deployment-Konfiguration, nicht Code | die 7 Roh-`fetch()`-Pfade als *potenzielle* Bruchstelle markiert, **nicht** als Finding |
| **Typ-Drift TS ↔ Django-Serializer** | nur Stichprobe auf Feldnamen (Evidence 07 §5), kein Schemasvergleich | kein Drift-Finding |
| **Rendern der Suite** | `vitest` nicht ausgeführt | Ratchet-Baselines wurden aus dem Quelltext nachgerechnet, nicht ausgeführt (Gegenprobe in Evidence 00) |
| **ChoiceField-UI für LLM-Provider** | nicht gelesen | `azure`-Befund wurde stattdessen auf Type-Ebene bestätigt (Evidence 07 §7) |

## 14. Evidenz-Dateien

| Datei | Inhalt |
|---|---|
| `AUDIT_EVIDENCE/wp3b-00-methodik.md` | Scanner-Methodik, Fehlerkorrekturen, Reproduktion |
| `AUDIT_EVIDENCE/wp3b-01-i18n-inventar.md` | 116 fehlende Keys je Datei, 536 tote Keys, Plural-Tabelle |
| `AUDIT_EVIDENCE/wp3b-02-i18n-ratchet-analyse.md` | Ist-Verhalten des Ratchets + korrekte Prüflogik als Entwurf |
| `AUDIT_EVIDENCE/wp3b-03-token-count.md` | Token-/Hex-/Inline-Style-Zählung mit Trennung Prod/Test |
| `AUDIT_EVIDENCE/wp3b-04-state-und-effects.md` | State-Inventar, Effects, Request-Waterfall |
| `AUDIT_EVIDENCE/wp3b-05-a11y-inventar.md` | Autofokus, Klick-Handler, aria-live, Fehlergrenzen |
| `AUDIT_EVIDENCE/wp3b-06-testid-matrix.md` | Abdeckungsmatrix, Dubletten, e2e-Abgleich |
| `AUDIT_EVIDENCE/wp3b-07-api-client.md` | API-Client-Analyse, Roh-`fetch`-Liste, Fehlertypisierung |