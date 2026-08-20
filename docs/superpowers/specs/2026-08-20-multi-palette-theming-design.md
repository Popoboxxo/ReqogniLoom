# Multi-Palette Theming System — Design

**Status:** Draft, approved by user for implementation (2026-08-20)
**Issue:** #568 (konsolidiert #140 — 128 hartcodierte Hex-Werte, #161 — 207 Inline-Styles)
**Scope:** Vier Phasen, jede Phase ein eigener Merge-Checkpoint (siehe Abschnitt 5).

## 1. Zweck

ReqogniLoom soll mehr als die zwei fest verdrahteten Themes (dark/light)
anbieten können — benannte Paletten, pro Workspace vorgebbar, pro User
überschreibbar. Das Ziel ist nicht nur "eine dritte Palette hinzufügen",
sondern die Farbverwaltung so aufzuräumen, dass eine neue Palette **überall**
korrekt greift, statt an 592 hartcodierten Hex-Stellen ins Leere zu laufen.

**Nicht-Ziel:** Kein Theme-Editor/Custom-Color-Picker für Endnutzer in dieser
Iteration — nur eine feste, im Code definierte Menge benannter Paletten.

## 2. Ist-Zustand (verifiziert, 2026-08-20)

- **Primitive-Layer bereits fertig.** `frontend/src/styles/tokens.css` hat
  bereits eine vollständige Zwei-Schichten-Architektur: `--palette-*`
  (Rohwerte, themeunabhängig) und `--color-*` (semantisch, referenziert
  ausschließlich `var(--palette-*)`). Ein `:root[data-theme="light"]`-Block
  existiert. `grep -E "^  --color-.*#[0-9a-fA-F]{3,6}"` findet 0 Treffer —
  keine rohen Hex-Werte in semantischen Deklarationen.
- **Theme-Registry minimal.** `frontend/src/context/ThemeContext.tsx`: `Theme`
  ist als `string` typisiert (bewusst offen für Erweiterung laut Kopfkommentar),
  `THEMES`-Array hat aber nur 2 Einträge (dark/light).
- **Keine Settings-UI** für Theme-Wahl. `WorkspaceSettings.tsx` hat ein
  etabliertes Muster für Sprache (Radiobutton-Gruppe + `workspacesApi.update()`),
  das für Theme gespiegelt werden kann.
- **Hex-Migration ist der eigentliche Rückstand — und größer als im Issue
  dokumentiert.** Issue-Snapshot (16.08.): 356 Hex-Treffer / 60 Dateien / 207
  Inline-Styles. Aktueller Stand (20.08.): **592 Hex-Treffer / 104 Dateien /
  1074 `style={{...}}`-Vorkommen.** Die Codebase wächst schneller als sie
  migriert wird.
- **ESLint-Regel `local/no-hex-color-in-inline-style: 'error'` existiert,
  greift aber nicht vollständig.** Verifiziert an
  `frontend/src/components/ArtifactDiff/ArtifactDiff.tsx`: `npx eslint`
  meldet 0 Verstöße, obwohl die Datei eine als `React.CSSProperties`
  typisierte Konstante mit klaren Hex-Werten enthält:
  ```tsx
  const STATUS_STYLES: Record<DiffFieldStatus, React.CSSProperties> = {
    added: { background: "#c6f6d5", color: "#22543d", ... },
    ...
  };
  ```
  Arbeitshypothese: Die Regel matched nur Hex-Literale direkt innerhalb eines
  JSX-`style={{...}}`-Attribut-Ausdrucks (AST-Knoten `JSXAttribute` mit
  `ObjectExpression`), nicht Hex-Literale in separat deklarierten,
  typisierten Objekt-Konstanten, die über `style={STATUS_STYLES[key]}`
  referenziert werden. Gleiches Muster bestätigt in
  `frontend/src/components/TestRuns/TestRunDetailEditor.tsx` (Zeilen 188,
  193, 198). Diese Lücke muss vor der Massen-Migration geschlossen werden,
  sonst wächst der Rückstand während der Migration weiter.

## 3. Reihenfolge-Entscheidung

Zwei naheliegende Reihenfolgen wurden abgewogen:

- **Migration zuerst:** saubere Basis, aber lange Strecke ohne sichtbares
  Feature (592 Treffer, 104 Dateien).
- **Registry/Settings-UI zuerst:** schnell sichtbar, aber eine neu
  freigeschaltete Palette würde an allen noch nicht migrierten Stellen
  falsch/inkonsistent aussehen — das Feature wirkt kaputt, bevor es fertig
  ist.

**Entscheidung (User-genehmigt): Hybrid, vier Phasen.** ESLint-Lücke zuerst
schließen (verhindert neue Lecks während der Migration läuft), dann
Registry-Infrastruktur (sichtbarer Fortschritt, aber neue Paletten bleiben
zunächst ungenutzt/intern), dann die eigentliche Migration verzeichnisweise,
zuletzt Freischaltung zusätzlicher Paletten + WCAG-Kontrastprüfung.

## 4. Architektur

### 4.1 ESLint-Regel-Härtung (Phase 0)

Die bestehende Custom-Regel (Implementierung vermutlich in einem lokalen
ESLint-Plugin, referenziert über `local/...` in `frontend/eslint.config.js`)
muss um einen zusätzlichen AST-Check erweitert werden: Hex-Literale in
`VariableDeclarator`-Initialisierern, deren Typ-Annotation `React.CSSProperties`
oder `Record<string, React.CSSProperties>` referenziert (bzw. pragmatischer:
jede String-Property mit einem Wert, der auf `/^#[0-9a-fA-F]{3,6}$/` matched,
innerhalb eines Objekt-Literals, das erkennbar CSS-Properties zuweist — z. B.
Property-Namen wie `background`, `color`, `borderColor` etc.), muss ebenfalls
als Verstoß gemeldet werden.

Begleitend: ein Ratchet-Test nach dem Muster von
`frontend/src/test/i18n-parity.test.ts` (`MISSING_KEY_BASELINE`) bzw.
`ui-ratchet.test.ts` — zählt rohe Hex-Treffer im gesamten `src`-Baum
(Regex-Scan, kein AST nötig, analog zu `collectReferencedKeys`), mit einer
eingefrorenen Obergrenze (`RAW_HEX_BASELINE`), die nur sinken darf. Das macht
den Fortschritt der Migration in Phase 2 messbar und verhindert Rückfall.

### 4.2 Theme-Registry (Phase 1)

- `ThemeContext.tsx`: `THEMES`-Array um weitere Einträge erweitern (Struktur
  steht schon, `Theme` ist bereits `string`). Konkrete neue Paletten-IDs und
  Farbwerte werden erst in Phase 3 final freigeschaltet — Phase 1 liefert nur
  die Mechanik.
- `tokens.css`: für jede neue Palette ein weiterer
  `:root[data-theme="<id>"]`-Block, analog zum bestehenden
  `[data-theme="light"]`-Block, referenziert ausschließlich `--palette-*`.
- **Settings-UI:** neuer Theme-Selector in `WorkspaceSettings.tsx`, exakt das
  Radiobutton-Gruppen-Muster der bestehenden Sprachauswahl gespiegelt.
- **Persistenz:** Workspace-Default (via `workspacesApi.update()`, analog
  Sprache) + User-Override (bestehender `ThemeContext`-Mechanismus, vermutlich
  `localStorage` — wird beim Implementieren am bestehenden Code verifiziert,
  nicht neu erfunden).

### 4.3 Hex-/Inline-Style-Migration (Phase 2)

Verzeichnisweise, jeweils ein Commit/Checkpoint pro Verzeichnis:

1. `shared/` (höchster Hebel — überall wiederverwendet)
2. `*Editors` (ArtifactDiff, TestRunDetailEditor, etc.)
3. Views/Dashboards
4. Settings

Migration bedeutet: rohe Hex-Werte durch passende `var(--color-*)`-Referenzen
ersetzen; existiert kein passendes semantisches Token, wird eines ergänzt
(nicht ad hoc ein neuer roher Hex-Wert). Jeder Schritt senkt den
`RAW_HEX_BASELINE`-Wert aus Phase 0 entsprechend ab.

### 4.4 Paletten-Freischaltung + WCAG (Phase 3)

- Weitere Paletten erst in der Settings-UI sichtbar machen, wenn
  Migrations-Deckung ausreichend ist (kein hartes Zahlen-Gate vorab
  festgelegt — Entscheidung beim Erreichen von Phase 3, basierend auf
  Rest-Treffern in gerade sichtbaren Bereichen).
- Automatisierter Kontrast-Test (4.5:1, WCAG AA) für alle semantischen
  Text/Hintergrund-Token-Paare jeder Palette — ein Test pro Palette, damit
  ein Fehlschlag eindeutig einer Palette zuzuordnen ist.

## 5. Phasen / Checkpoints

| Phase | Inhalt | Checkpoint |
|---|---|---|
| 0 | ESLint-Regel-Lücke schließen + Hex-Ratchet-Test | 1 Commit |
| 1 | Theme-Registry-Mechanik + Settings-UI + Persistenz | 1 Commit |
| 2 | Hex-Migration, pro Verzeichnis | 1 Commit je Verzeichnis (4) |
| 3 | Paletten-Freischaltung + WCAG-Kontrast-Tests | 1 Commit |

Jede Phase wird laut Nutzer-Vorgabe als eigener Zwischenstand gesichert
(committed), nicht erst am Ende des gesamten Projekts.

## 6. Testing

- Ratchet-Test für Hex-Treffer (Phase 0), analog `i18n-parity.test.ts`.
- Bestehende ESLint-Suite muss die erweiterte Regel grün gegen den
  *migrierten* Teil der Codebase laufen lassen (rot gegen den
  noch-nicht-migrierten Teil ist in Phase 0–1 erwartet und ok, da die Regel
  nur *neue* Verstöße hart blockt — bestehende werden über den Ratchet-Test
  separat nachverfolgt, nicht über harte ESLint-Fehler in unberührten
  Dateien).
- Kontrast-Tests (Phase 3) pro Palette.
- Bestehende `ui-ratchet.test.ts` / `design-tokens.test.ts` dürfen durch
  keine Phase brechen.

## 7. Offene Punkte für spätere Iterationen (bewusst nicht in Scope)

- Custom-Theme-Editor für Endnutzer.
- Automatische Hex-zu-Token-Migration per Codemod (Phase 2 wird zunächst
  manuell/verzeichnisweise gemacht; ein Codemod-Ansatz kann bei Bedarf
  nachgezogen werden, wenn Phase 2 sich als zu langsam erweist).
