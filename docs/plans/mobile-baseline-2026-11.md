# Mobile-Baseline 2026-11-16 (M0)

**Stand:** `origin/main` `fe34e583` · **Art:** Code-gestützte Ist-Aufnahme, **keine** gerenderten Messungen.
**Zweck:** Abhakliste für die Schnitte M4–M8 des
[Mobile/PWA-Plans](../superpowers/plans/2026-11-16-mobile-pwa.md). Grundlage ist die Spec
[§3 Befund](../superpowers/specs/2026-11-16-mobile-pwa-design.md#3-befund-ist-stand-auf-originmain-belegt).

> **Ehrlichkeitshinweis:** In dieser Sitzung war kein ReqogniLoom-Stack verfügbar (kein
> Frontend auf `:5173`, kein Backend auf `:8001`). Die unten genannten Breiten-/Overflow-Folgen
> sind aus dem Code abgeleitet, **nicht** im Browser gemessen. Das M0-Semaphore-Set
> (`e2e/tests/mobile-smoke.spec.ts`) liefert die gerenderten Nachweise, sobald der Stack läuft:
> `cd e2e && npm run test:e2e -- --project=mobile-chrome --project=mobile-safari --grep=@mobile`.
> Screenshots landen in `e2e/test-results/mobile-baseline/` (gitignored).

## 1. Messbasis (M0, umgesetzt)

| Artefakt | Inhalt |
|---|---|
| `e2e/playwright.config.ts` | Projekte `chromium` (Desktop), `mobile-chrome` (Pixel 7), `mobile-safari` (iPhone 13); `@mobile`-Tag trennt die Suiten |
| `e2e/tests/mobile-smoke.spec.ts` | Login + 5 Routen, je Route `scrollWidth <= clientWidth + 1`, Screenshot nur im iPhone-Projekt, zusätzlich Liste → Detail |
| `e2e/helpers/mobile.ts` | `expectNoHorizontalDocumentScroll`, `openFirstListItem` (beide Zeilen-Konventionen) |
| `.github/workflows/playwright.yml` | Shards 1–4 Desktop (unverändert partitioniert), Shard 5 Mobil |

## 2. Code-Befunde → Schnitt

| # | Befund (`pfad:zeile`) | Erwartete mobile Folge | Schnitt | Status |
|---|---|---|---|---|
| B1 | `SplitView.tsx:424,566` — `isResponsiveCollapsed` bedeutet „mobil" **und** „welche Spalte"; `:580-591` harte `List`/`Detail`-Labels | „Detail" rendert den Desktop-Zweig (zwei Spalten à ≥380 px + Divider) auf 390 px; DE-Oberfläche zeigt Englisch | M5 | offen |
| B2 | `AppShell.module.css:7`, `SidebarNavigation.module.css:16`, `LoginPage.module.css:10`, `WorkflowEditor.module.css:17,1106`, `DiagramGraphEditor.module.css:17`, `SystemSettings.module.css:51` — `100vh` | Fußzeilen/Speicherknöpfe verschwinden hinter der Browser-Leiste | M4 | offen |
| B3 | `AllocationTreesRenderer.module.css:35`, `ConnectionView.module.css:451` — feste 2-Spalten-Grids, kein `@media`; `PermissionMatrixEditor.module.css:23`, `WorkflowPermissionsSection.module.css:51` — `min-width: 520px` | Zwei Bäume à ~180 px auf 390 px; Matrizen quetschen oder laufen über | M8 | offen |
| B4 | `WorkflowEditor.module.css:550`, `DiagramGraphEditor.module.css:480`, `AllocationGraph.module.css:231` — `opacity: 0` ohne Hover-Alternative | Zeilenaktionen auf Touch unerreichbar | M6 | offen |
| B5 | `useSaveShortcut.ts:110` (`Strg`/`Cmd`), `canvas/CanvasEditor.tsx:962` (nur Wheel/Maus) | Kein Speichern-Weg, kein Zoom/Pan auf Touch | M7/M8 | offen |
| B6 | `frontend/index.html` — kein Manifest, kein `theme-color`, kein Icon; `frontend/public/` existiert nicht | Nicht installierbar | M1 | **in Arbeit** |

## 3. Nach M0 zu messen (noch offen)

- [ ] Für alle 30 `NAV_ITEMS`-Routen: `scrollWidth`/`clientWidth` bei 360×800 und 390×844.
- [ ] Je Route: Screenshot mit sichtbarem Burger, Detail-Kopfzeile, Filterleiste.
- [ ] Detail-Flow: Zeile öffnen → Liste ausgeblendet? Zurück vorhanden? (heute laut Code: nein/nein).
- [ ] Bottom-Sheet-Dialoge bei 390 px (erwartet gut — `Dialog.module.css:159` existiert bereits).
- [ ] Touch-Zielgrößen der Primäraktionen (Ziel ≥ 44 px).
- [ ] Tastatur-/Zoom-Verhalten bei `interactive-widget=resizes-content` auf Android (M1 liefert das Attribut).

## 4. Abschlussvermerk

Nach M9 werden hier die gemessenen Ergebnisse eingetragen und jede Zeile aus §2 auf „geschlossen"
oder „bewusst offen (Begründung)" gesetzt. Bis dahin ist dieses Dokument eine **Hypothesenliste**,
kein Abnahmebericht.
