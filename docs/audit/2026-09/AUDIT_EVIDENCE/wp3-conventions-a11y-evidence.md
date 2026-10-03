---
type: REVIEW
scope: wp-3-conventions-a11y-evidence
status: complete
date: 2026-09-29
author_agent: e2e-tester
---

# WP-3 — Konventionen (data-testid, Design-Tokens) und a11y-Stichprobe

## A. data-testid

### A.1 Bestand

| Kennzahl | Wert |
|---|---|
| `data-testid`-Literale in `frontend/src` (ohne Tests) | **1 132** |
| Template-Präfixe (`` data-testid={`prefix-${id}`} ``) | **247** |
| Interaktive Elemente (`<button>`/`<input>`/`<select>`) in `frontend/src/components` | ~730 |
| Bereiche mit interaktiven Elementen | 41 |
| Bereiche mit Testid/Interaktiv-Verhältnis < 1 | **0** |

Verhältnis je Bereich (Testids pro interaktivem Element, > 100 % = Testids auch an
nicht-interaktiven Trägern, z. B. Status-Badges):

```
mermaid 1200  ·  AdminDialog 667  ·  MetricsDashboard 633  ·  ArtifactDiff 500
BaselinesView 418  ·  TraceabilityView 417  ·  Memory 324  ·  IcdView 280
UserProfileSettings 288  ·  Audit 285  ·  RequirementEditors 262  ·  Goals 262
…
AttributeEditor 134  ·  LinkTypeEditor 140  ·  GlossaryView 147  ·  canvas 157
```

⇒ **Kein Bereich ohne `data-testid`-Abdeckung.**

### A.2 Befund — Sidebar-Navigation ohne Testids (AUD-2026-09-007)

`frontend/src/components/NavigationShell/SidebarNavigation.tsx:150-160`

```tsx
<NavLink
  to={item.path}
  end={item.path === "/."}
  className={active ? styles.navLinkActive : styles.navLink}
>
  {t(item.labelKey)}
</NavLink>
```

25 Einträge, **0× `data-testid`**. Einziger Selektierpfad ist der **übersetzte**
Text (`nav.dashboard` = „Dashboard"/„Dashboard", `nav.goals` = „Ziele"/„Goals").

**Warum das auffällt, obwohl es heute nicht bricht:** die Suite navigiert mit
`page.goto()` (209 Aufrufe) und **null** Mal mit `getByRole('link', { name })`.
Damit ist die Lücke kaschiert. Sobald ein Spec die Sidebar klicken will (etwa für
den Skip-Link- oder Fokusordnungsnachweis aus AUD-2026-09-003), wird er
sprachabhängig — die App hat einen Sprachumschalter.

### A.3 Stale-Selektoren-Prüfung (positiv)

| Prüfung | Ergebnis |
|---|---|
| `getByTestId("…")`-Literale über 54 Specs | 22 distinkt |
| davon im Frontend **nicht** auffindbar | **0** |
| Erster Durchlauf meldete 3 Kandidaten (`artifact-field-moscow_priority`, `req-list-search-input`, `status-badge`) | ✅ **Falsch-positiv** — alle drei existieren (1 / 1 / 10 Treffer); mein Präfix-Matching war zu streng. Kein Befund |

Damit ist die Prämisse von **#1113** (offen) derzeit *nicht* reproduzierbar — der
Wächter selbst fehlt aber weiterhin.

### A.4 Row-scoped Testids — kein Defekt

204 Stellen nutzen `` data-testid={`prefix-${id}`} `` (z. B. `glossary-row-${term.id}`).
Das ist ein valides, per Präfix selektierbares Muster (`getByTestId(/^glossary-row-/)`)
und **kein** E2E-Bruch.

## B. Design-Tokens

### B.1 Messung

| Prüfung | Ergebnis | Bewertung |
|---|---|---|
| `frontend/src/styles/tokens.css` | 84 667 Bytes, **908** Custom Properties | ✅ Quelle der Wahrheit |
| Hex-Literale **in** `tokens.css` | 270 | ✅ korrekt (Definition) |
| Hex-Literale in Komponenten-CSS, **nach Strippen der Kommentare** | **0** (133 Dateien) | ✅ |
| davon als `var(--…)`-Fallback | 0 | ✅ |
| Hex-Literale in `style={{…}}` in `.tsx` | **0** | ✅ |
| Verbleibende `font-size: Npx` | **13** | ⚠️ P3 |

### B.2 Korrektur meiner eigenen Erstmessung

Der naive Zählaufwand ergab „441 Hex-Literale, davon 166 standalone". Das war ein
**Messfehler**: die Regex griff Issue-Nummern in CSS-Kommentaren mit
(`#876`, `#955`, `#674`, …). Nach
`[regex]::Replace($css, '/\*.*?\*/', '', Singleline)` ist das Ergebnis **0**.

Beispiel `Dialog.module.css`: roh 7 Treffer, nach Kommentar-Stripping **0**.

⇒ **AUD-2026-09-021 = WIDERLEGT.** `#876` („1.015 Inline-Styles und 74 Hardcoded
Hex-Farben migrieren") und `#674` sind wirksam geschlossen.

### B.3 Verbleibende `font-size`-Ausnahmen (P3, kosmetisch)

| Datei | Zeilen | Wert |
|---|---|---|
| `ArtifactDiff.module.css` | 64, 83, 92, 132, 240, 245, 250, 264, 270, 276, 282 | `13px` (11×) |
| `ProposalPreviewGraph.module.css` | 64 | `11px` |
| `WorkflowEditor.module.css` | 620 | `10px` |

Alle drei sollten `var(--font-size-*)` verwenden; `tokens.css` bietet die Skala an.

## C. Accessibility-Stichprobe

> **Ausdrücklich Stichprobe, kein vollständiger WCAG-Audit.** Kein Axe-Lauf, keine
> Assistive-Technology-Sitzung, keine Kontrastraten berechnet.

### C.1 Tastatur

| Prüfung | Beobachtung | Ergebnis |
|---|---|---|
| Skip-Link | ❌ **nicht vorhanden.** Erster `Tab` blendet keinen Link ein. `#main` existiert als `role="main"` in `NavigationShell.tsx:127`, ist aber nicht fokussierbar | ⚠️ **AUD-2026-09-003** |
| Reihenfolge | Sidebar (Suche → 25 Links → Artefakt-Toggle → Workspace-Umschalter) → Header (Sprache, Theme, Profil, Logout) → `main` → Interview-Widget | ✅ sinnvoll |
| Fokus-Sichtbarkeit | Beim ersten `Tab` im Screenshot **kein** Fokusring erkennbar | ⚠️ NICHT VERIFIZIERBAR (Screenshot-Timing) |
| Fokus in Dialog | Fokus wandert in den Dialog, initial auf **Abbrechen** | ✅ |
| Fokus-Rückgabe | Nach ESC `[active]` auf `req-row-delete-<uuid>` | ✅ **#991 wirksam** |
| ESC | Dialog schließt | ✅ **#985 wirksam** |
| Interaktive Treeitems | `role="treeitem"` enthält `button "Löschen"` — Potenzial für #667-Muster | ⚠️ statisch nicht neu bewertet |

### C.2 ARIA

| Element | Befund |
|---|---|
| `Dialog`-Primitiv | ✅ `role="dialog"` + `aria-modal="true"` + `aria-labelledby` gemeinsam (`Dialog.tsx:156`), unit-getestet (`Dialog.test.tsx:82`) |
| Fehlende accessible names | ❌ **2 `combobox` ohne jeden Namen** auf `/system-settings` → „Design-Paletten" → „Tenant-Standard" ⇒ ⚠️ **AUD-2026-09-005** (verwandt #425/#741) |
| Landmarken | ✅ `navigation "Hauptnavigation"`, `main role="main"`, `complementary "Inspektor"`, `toolbar "Canvas-Steuerung"`, `region "Digest"`, `tablist`/`tab`/`tabpanel` korrekt verdrahtet |
| Splitter | ✅ `separator` mit Label („Bereiche in der Größe anpassen" / „Resize panels") |
| Tabellen | ✅ `table`/`rowgroup`/`row`/`columnheader`/`cell` |
| Statusmeldungen | ✅ `role="status"`, `role="alert"` (Login-Fehler), `aria-busy` |
| Sprachumschalter | ⚠️ `button "DE"/"EN"` ohne `aria-pressed`/`aria-label` — State nur visuell |
| Theme-Umschalter | ⚠️ `button "Dunkler Modus"/"Light mode"` ohne `aria-pressed` |
| Canvas-Steuerung | ✅ alle 6 Buttons mit Namen („Vergrößern", „An Ansicht anpassen", „Raster umschalten" mit `pressed`) |
| Tabellen-Sortierung | ⚠️ „Sortieren nach" ist ein `<select>`, kein `aria-sort`-Header ⇒ kein programmatischer Sortierstatus |

### C.3 Dark Mode / Bewegung / Kontrast

| Prüfung | Ergebnis |
|---|---|
| `prefers-color-scheme: dark` via `browser_emulate_media` | ⚠️ **keine Wirkung** — die App nutzt eine eigene, serverseitig persistierte Präferenz. Bewusste Entscheidung, aber undokumentiert ⇒ AUD-2026-09-019 |
| App-Dark-Mode-Toggle | ✅ funktioniert, Kontrast ausgewogen, Screenshot `wp3-dark-mode-app-toggle.png` |
| `prefers-reduced-motion: reduce` | ⚠️ gesetzt, aber **keine Animation im Testfenster auslösbar** ⇒ NICHT VERIFIZIERBAR |
| Kontrast | ⚠️ Stichprobe: Fließtext auf Karten und der Empty-Pane-Hinweis wirken hellgrau; **keine Ratio-Messung** (kein Axe) ⇒ NICHT VERIFIZIERBAR |

## D. E2E-Abdeckungslücken (Route × Spec)

Specs liegen in `e2e/tests/` (54 Dateien), **nicht** in `e2e/`.

| Route | Specs | Spec-Dateien | Lücke |
|---|---|---|---|
| `/requirements` | 27 | u. a. `requirements`, `requirement-editor` | — |
| `/architecture` | 14 | `architecture`, `architecture-editor` | — |
| `/testcases` | 10 | `testcases`, `test-runs` | — |
| `/traceability` | 8 | `traceability`, `traceability-view`, `tracelink-creation` | — |
| `/baselines` | 8 | `baselines-view` | — |
| `/diagrams` | 8 | `canvas-diagram`, `diagram-ui`, `mermaid-diagram`, `diagram-node-graph` | — |
| `/needs` | 8 | `needs-cross-boundary`, `create-need-verification` | — |
| `/test-runs` | 7 | `test-runs` | — |
| `/login` | 7 | `auth`, `auth-api` | — |
| `/settings` | 6 | `csv-import`, `ui-konzept-gates`, `ui-test-campaign`, `user-management`, `visual-regression` | ⚠️ `workspace-settings.spec.ts` navigiert `/workspace-settings` (Legacy-Route), **nicht** `/settings` |
| `/system-settings` | 6 | `banners`, `overlay-dismissal`, `dialog-escape-robustness`, `workspace-lifecycle` | — |
| `/icds` | 6 | `icd-ui`, `icd-api` | — |
| `/profile` | 5 | `user-profile` | — |
| `/metrics` | 5 | `metrics-dashboard`, `metrics-api` | — |
| `/adrs` `/risks` `/issues` | 4 | `toothbrush-syseng`, `ui-konzept-gates`, `visual-regression`, `waterkettle-fullblown` | ❌ kein dedizierter CRUD-Spec |
| `/import` | 4 | `csv-import` | — |
| `/reviews` | 3 | `review-workflow`, `ui-konzept-gates`, `visual-regression` | ⚠️ Route ist feature-gegatet (`feature: "approver_ui"`, `SidebarNavigation.tsx:110`) ⇒ im Default-Build toten Pfad testen |
| `/goals` | 2 | `ui-konzept-gates`, `visual-regression` | ❌ **nur generisch** |
| `/workflows` | 2 | `ui-konzept-gates`, `visual-regression` | ❌ **nur generisch** |
| `/audit` | 2 | `ui-konzept-gates`, `visual-regression` | ❌ **nur generisch** |
| `/impact` | 2 | `ui-konzept-gates`, `visual-regression` | ❌ **nur generisch** |
| `/glossary` | 2 | `ui-konzept-gates`, `visual-regression` | ❌ **nur generisch** |
| `/memory` | 1 | `memory` | ⚠️ dünn |
| `/interviews` | 1 | `visual-regression` | ❌ **kein funktionaler Spec** |
| `/user-management` | 1 | `user-management` | ⚠️ dünn |
| `/attributes` | **0** | — | ❌ **Route ohne jede Abdeckung** (kein Nav-Eintrag, kein Link im Code) |

### Thematische Lücken (nicht route-bezogen)

1. **i18n**: 1 von 54 Specs nutzt `lang-switch`.
2. **Console-Hygiene**: kein Spec schlägt bei `console.error` / unhandled rejection fehl
   ⇒ die React-Flow-Warnung (AUD-2026-09-018) wäre durchgefallen.
3. **Response-Zeit**: kein First-Paint-Budget ⇒ die 10-s-Ladezeit (AUD-2026-09-014) fällt durch.
4. **Token-Ratchet**: `tokens.css` wird nicht gegen Komponenten-CSS geprüft
   (#1099 ist **offen** und friert 327 Verstöße ein).
5. **N+1-Wächter**: kein Spec begrenzt die Request-Anzahl eines Page-Loads
   ⇒ AUD-2026-09-001 (453 Requests) ist für die Suite unsichtbar.
