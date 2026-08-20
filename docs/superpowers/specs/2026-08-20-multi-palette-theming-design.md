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
- **KORREKTUR (20.08., nach tieferer Prüfung): Hex-Migration ist bereits ein
  aktiv gepflegtes, mit Ratchet-Tests abgesichertes Projekt — kein
  ungetrackter Rückstand.** Die erste Messung in diesem Dokument (592
  Hex-Treffer / 104 Dateien via naivem `grep`) war falsch: dieselbe
  Zählmethode hat dieselbe Codebase bereits einmal fälschlich auf "152
  Treffer / 48 Dateien" taxiert (siehe `frontend/src/test/ui-ratchet.test.ts`
  Kommentar-Historie), weil `/#[0-9a-fA-F]{3,8}/` auch dezimale
  GitHub-Issue-Referenzen in Kommentaren matcht (`// #135`, `{/* #340 */}`).
  Die tatsächliche, um Kommentare bereinigte Zahl — bereits als Ratchet in
  `ui-ratchet.test.ts` eingefroren — ist **90 Hex-Treffer in 27 `.tsx`-Dateien**
  (`HEX_LITERAL_OCCURRENCE_BASELINE`/`HEX_LITERAL_FILE_BASELINE`) plus **55
  Treffer in 6 CSS-Dateien** (`HEX_LITERAL_CSS_OCCURRENCE_BASELINE`/
  `HEX_LITERAL_CSS_FILE_BASELINE`). Beide Ratchets dürfen nur sinken, nicht
  steigen, und ihre Historie zeigt aktive Migrationsarbeit (z. B. Task 8.1,
  die bereits die Primitive/Semantic-Trennung aus §2 oben umgesetzt hat).
  **Ein neuer Ratchet-Test ist daher NICHT nötig — er existiert schon.**
- **ESLint-Regel `local/no-hex-color-in-inline-style: 'error'` hat eine
  dokumentierte, absichtliche Scope-Grenze — kein Bug.** Verifiziert an
  `frontend/src/components/ArtifactDiff/ArtifactDiff.tsx`: `npx eslint`
  meldet 0 Verstöße für dessen `STATUS_STYLES`-Konstante
  (`Record<DiffFieldStatus, React.CSSProperties>` mit Hex-Werten wie
  `background: "#c6f6d5"`). Der Regel-Kopfkommentar
  (`frontend/eslint-rules/no-hex-color-in-inline-style.js`) sagt das
  ausdrücklich voraus: "A hoisted style constant referenced by identifier
  ... is NOT inspected — there is no literal in the attribute's own
  subtree. That is a known, accepted limitation." Außerdem existiert
  bereits ein flankierender Mechanismus dafür: `LEGACY_INLINE_STYLE_HEX_FILES`
  (`frontend/eslint-rules/legacy-inline-style-hex-files.js`) — eine
  eingefrorene Ausnahmeliste von 21 Dateien (darunter `ArtifactDiff.tsx`
  selbst), für die die Regel bewusst `'off'` ist, mit der Anweisung, jeden
  Eintrag beim Migrieren zu löschen statt neue hinzuzufügen. Die
  Lücken-Erweiterung der Regel (`VariableDeclarator`-Hex-Erkennung) wäre für
  genau diese Dateien wirkungslos, solange sie auf der Legacy-Liste stehen —
  eine Regel-Härtung bringt daher erst Wert, NACHDEM eine Datei von der
  Liste migriert wurde, nicht vorher. **Phase 0 (separate ESLint-Härtung
  vor der Migration) entfällt damit als eigener Schritt** — siehe §4.1.

## 3. Reihenfolge-Entscheidung

Zwei naheliegende Reihenfolgen wurden abgewogen:

- **Migration zuerst:** saubere Basis, aber lange Strecke ohne sichtbares
  Feature.
- **Registry/Settings-UI zuerst:** schnell sichtbar, aber eine neu
  freigeschaltete Palette würde an allen noch nicht migrierten Stellen
  falsch/inkonsistent aussehen — das Feature wirkt kaputt, bevor es fertig
  ist.

**Entscheidung (User-genehmigt): Hybrid, vier Phasen — Phase 0 entfällt
nach der Korrektur in §2.** Registry-Infrastruktur zuerst (sichtbarer
Fortschritt, aber neue Paletten bleiben zunächst ungenutzt/intern), dann
die eigentliche Migration verzeichnisweise (im bereits existierenden
Ratchet nachverfolgt), zuletzt Freischaltung zusätzlicher Paletten +
WCAG-Kontrastprüfung.

## 4. Architektur

### 4.1 ESLint/Ratchet-Infrastruktur (Phase 0 — bereits erledigt, kein Task)

Sowohl die Ratchet-Tests (`ui-ratchet.test.ts`, siehe §2) als auch die
`LEGACY_INLINE_STYLE_HEX_FILES`-Ausnahmeliste existieren bereits und werden
aktiv gepflegt. Dieser Abschnitt existiert nur noch als Dokumentation
dessen, was schon da ist — kein Implementierungs-Task in
`docs/superpowers/plans/`. Eine AST-Erweiterung der ESLint-Regel auf
`VariableDeclarator`-Hex-Fälle (wie z. B. `ArtifactDiff.tsx`s
`STATUS_STYLES`) bleibt eine sinnvolle spätere Härtung, aber erst
NACHDEM die jeweilige Datei von der Legacy-Liste migriert wurde (siehe
§2) — sie gehört inhaltlich zu Phase 2 (pro migrierter Datei: Eintrag aus
`LEGACY_INLINE_STYLE_HEX_FILES` löschen), nicht zu einer eigenen Vorstufe.

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
(nicht ad hoc ein neuer roher Hex-Wert). Jeder Schritt senkt
`HEX_LITERAL_OCCURRENCE_BASELINE`/`HEX_LITERAL_FILE_BASELINE` (aktuell
90/27, `.tsx`) bzw. `HEX_LITERAL_CSS_OCCURRENCE_BASELINE`/
`HEX_LITERAL_CSS_FILE_BASELINE` (aktuell 55/6, CSS) in
`frontend/src/test/ui-ratchet.test.ts` entsprechend ab — beide bereits
existierend, siehe §2. Wird eine Datei aus `LEGACY_INLINE_STYLE_HEX_FILES`
(`frontend/eslint-rules/legacy-inline-style-hex-files.js`) dabei
vollständig migriert, wird ihr Eintrag im selben Commit gelöscht.

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
| 0 | ~~ESLint-Lücke + Ratchet-Test~~ — bereits vorhanden, kein Task | — |
| 1 | ~~Theme-Registry-Mechanik + Settings-UI + Persistenz~~ — **erledigt** | siehe `docs/superpowers/plans/2026-08-20-multi-palette-theming-phase1.md`, 6 Tasks, alle Reviews clean (2 Fix-Runden in Task 5), 2280/2281 Backend-Tests + 1096/1098 Frontend-Tests grün (2 vorbestehende, unabhängige Fails dokumentiert im Plan-Ledger) |
| 2 | Hex-Migration, pro Verzeichnis (bestehender Ratchet sinkt) | 1 Commit je Verzeichnis (4) |
| 3 | Paletten-Freischaltung + WCAG-Kontrast-Tests | 1 Commit |

Jede Phase wird laut Nutzer-Vorgabe als eigener Zwischenstand gesichert
(committed), nicht erst am Ende des gesamten Projekts.

## 6. Testing

- Bestehender Hex-Ratchet (`ui-ratchet.test.ts`) sinkt mit jedem
  Migrations-Commit in Phase 2 — kein neuer Test nötig.
- Kontrast-Tests (Phase 3) pro Palette.
- Bestehende `ui-ratchet.test.ts` / `design-tokens.test.ts` /
  `i18n-parity.test.ts` dürfen durch keine Phase brechen.

## 7. Offene Punkte für spätere Iterationen (bewusst nicht in Scope)

- Custom-Theme-Editor für Endnutzer.
- Automatische Hex-zu-Token-Migration per Codemod (Phase 2 wird zunächst
  manuell/verzeichnisweise gemacht; ein Codemod-Ansatz kann bei Bedarf
  nachgezogen werden, wenn Phase 2 sich als zu langsam erweist).
