# WP-3b Evidence 03 — Design-Token-Zählung

Methode: siehe `wp3b-00-methodik.md`. Alle Werte nach Block- und
Zeilen-Kommentar-Stripping; Test-Dateien getrennt gezählt.

## 1. Gesamtergebnis

| Zählung | Produktion | Tests |
|---|---:|---:|
| Hex-Literale `#[0-9a-fA-F]{3,8}` | **37** (5 Dateien) | 198 (82 Dateien) |
| `rgb()/rgba()/hsl()/hsla()/oklch()` | **2** (1 Datei) | 3 (2 Dateien) |
| Echte Inline-Styles `style={{ … }}` | **0** | 0 |
| `tokens.css` definierte Custom Properties | 268 Blöcke gescannt, alle `var(--x)`-Referenzen auflösbar | — |

`design-tokens.test.ts` (Token-Existenz) und die Per-Theme-Parität
(`bauhaus`, `nordic`, `sepia`) laufen und sind grün: **es fehlt kein Token**.
Inline-Fallbacks als Ursache von Token-Verstößen treten im aktuellen Stand
nicht auf.

## 2. Hex-Literale in Produktion — vollständige Liste der 5 Dateien

| Datei | Treffer | Zeilen | Bewertung |
|---|---:|---|---|
| `utils/asilUtils.ts` | 18 | 62, 64, 66, 68, 70, 72, 88, 90, 92, 94, 96, 98 | ASIL-Farbpalette (QM/A/B/C/D), hartkodiert, **kein Token-Route, kein CI-Gate** |
| `components/canvas/CanvasEditor.tsx` | 15 | div. | Fabric.js-Farben; im Ratchet als „genuinely unmigratable" dokumentiert |
| `components/DiagramView/diagram-view-shared.ts` | 2 | 136, 137 | `var(--color-danger, #ef4444)` — Token mit Hex-Fallback |
| `components/DiagramGraphEditor/GraphEdge.tsx` | 1 | — | im Ratchet dokumentiert |
| `components/canvas/canvas-geometry.ts` | 1 | 98 | `#000000` Default-Stroke |

Belege:

```
utils/asilUtils.ts:62   return '#9CA3AF'; // gray
utils/asilUtils.ts:66   return '#F97316'; // orange
utils/asilUtils.ts:88   return { background: '#F3F4F6', text: '#4B5563' };
utils/asilUtils.ts:96   return { background: '#7F1D1D', text: '#FFFFFF' };

components/DiagramView/diagram-view-shared.ts:136
  color: "var(--color-danger, #ef4444)",
components/DiagramView/diagram-view-shared.ts:137
  border: "1px solid var(--color-danger, #ef4444)",

components/canvas/canvas-geometry.ts:98
  color: typeof o.stroke === "string" ? o.stroke : "#000000",
```

## 3. Kernbefund: Lücke zwischen `.tsx`- und `.ts`-Scope

`frontend/src/test/ui-ratchet.test.ts:44-47`

```ts
function collectNonTestTsxFiles(dir: string): string[] {
  return collectFiles(dir, /\.tsx$/).filter((f) => !f.endsWith(".test.tsx"));
}
```

Der Hex-Ratchet (`ui-ratchet.test.ts:955-956`, Baselines **17 Vorkommen /
3 Dateien**) sieht ausschließlich `.tsx`. Damit:

* **21 der 37** Prod-Hex-Literale (`utils/asilUtils.ts` 18,
  `diagram-view-shared.ts` 2, `canvas-geometry.ts` 1) sind für ihn **unsichtbar**.
* Der `design-tokens.test.ts` prüft ausschließlich `var(--x)`-**Referenzen**
  gegen `tokens.css`, nicht rohe Farbwerte. Für `.ts`-Dateien existiert damit
  **keinerlei** Farb-Disziplin-Gate.

## 4. Baselines der UI-Ratchets — Ist vs. real

| Ratchet | Konstante | Real gemessen | Delta |
|---|---|---|---|
| `STYLE_BRACE_BASELINE` (`ui-ratchet.test.ts:747`) | 3 | **0** echte Inline-Styles | 3/3 sind Kommentar-Rauschen |
| `HEX_LITERAL_OCCURRENCE_BASELINE` (`:955`) | 17 | 16 (`.tsx` prod) | +1 Fehlpositiv (`#317`) |
| `HEX_LITERAL_FILE_BASELINE` (`:956`) | 3 | 2 (`.tsx` prod) | +1 Fehlpositiv |
| `HEX_LITERAL_CSS_OCCURRENCE_BASELINE` (`:1039`) | 203 | nur `tokens.css` (Primitive-Layer, bewusst) | 0 |
| `LOCAL_TOAST_BASELINE` (`:1206`) | 2 | — | nicht geprüft |
| `PRIMARY_FILL_BASELINE` (`:1245`) | 29 | — | nicht geprüft |
| `design-system-ratchet.baseline.json` | `button-missing-design-system-class: 324` | — | Aufnahme in Bericht |

Die drei `style={{`-Treffer, die den Wert 3 ergeben:

```
components/ArchitectureEditors/ArchitectureEditors.tsx:741
  … equivalents inlined as `style={{ }}`), which is exactly the drift
components/RequirementEditors/RequirementTreeNode.tsx:82
  … The literal `style={{` text below is kept only as a …
components/WorkspaceSettings/WorkspaceSettings.tsx:21
  * `WorkspaceSettings.module.css`. No inline `style={{...}}` block remains here;
```

Der Ratchet-Header (`ui-ratchet.test.ts:740-744`) räumt das selbst ein
(„the raw-vs-AST gap of 3 … the ESLint rule's AST-visible count under
`components/` is 0"). Die Konstante wurde aber nie nachgezogen.

## 5. CSS-Dateien

`collectCssFiles()` erfasst `.css` + `.module.css`. Nach Kommentar-Stripping
enthält **ausschließlich `frontend/src/styles/tokens.css`** rohe Hex-Werte — und
zwar ausschließlich im `--palette-*`-Primitive-Layer. Das ist die dokumentierte
und gewollte Zwei-Schichten-Architektur (UI-Konzept ch. 8.6). Die semantischen
`--color-*`-Blöcke enthalten keine Rohwerte. **CSS-seitig: 0 Verstöße.**

## 6. Test-Dateien (getrennt gezählt, kein Befund)

198 Hex-Treffer in 82 Test-Dateien. Höchste:
`test/design-system-ratchet.test.ts` 11, `test/RequirementEditors.test.tsx` 10,
`components/RequirementEditors/ReqTraceLinkPanel.test.tsx` 9.
Das sind Fixture-Werte (Farb-Assertions, Kontrasttests) und Regex-Literale in
den Ratchet-Tests selbst — kein Produktionsbefund, aber ein Grund, warum
Test-Dateien in keiner Token-Zählung mitgezählt werden dürfen.