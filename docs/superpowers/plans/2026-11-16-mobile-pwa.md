---
type: PLAN
title: "Mobil bedienbar und installierbar — Umsetzung M0–M9"
status: proposed
date: 2026-11-16
author_agent: planner
language: de
spec: "docs/superpowers/specs/2026-11-16-mobile-pwa-design.md"
related_issues: []
branch_basis: "origin/main fe34e583, Worktree .tmp/wt-mobile-pwa, Branch docs/mobile-pwa-plan"
pipeline_stages:
  implement: 1
---

# Mobil bedienbar und installierbar — Umsetzungsplan (M0–M9)

**Goal:** Die SPA auf Telefonbreite (360–430 px) bedienbar machen und als installierbare PWA
auf Android ausliefern — in zehn einzeln lieferbaren Schnitten. Nach **M1** ist die App
installierbar (ohne Offline-Hülle), nach **M2** startet sie auch bei wackligem Netz, nach
**M5** ist Liste → Detail auf jedem Artefakt-Pfad benutzbar, nach **M8** ist keine Route mehr
horizontal verschoben.

**Architecture:** Kein zweiter Codebaum. Ein Manifest + ein Service Worker (Build-Zeit
generiert, `vite-plugin-pwa`) als Hülle; darunter die bestehende React-SPA. Mobil ist eine
Darstellung derselben Komponenten über die dokumentierten Breakpoints
(`--bp-lg` 1024, `--bp-md` 768, neue Dichte-Stufe `--bp-sm` 640). Der Legacy-SplitView wird
mobil repariert (zwei getrennte Zustände), nicht ersetzt; `ConceptSplitView` bleibt ungenutzt,
bis O1 entschieden ist.

**Tech Stack:** React 19 + TypeScript 5.5 (strict) + Vite 8 + Vitest 5, CSS Modules +
`styles/tokens.css`, Playwright (Chromium, neu: Pixel-7-/iPhone-13-Projekte), nginx 1.31,
`vite-plugin-pwa` (Workbox) als einzige neue Abhängigkeit.

**Spec:** `docs/superpowers/specs/2026-11-16-mobile-pwa-design.md` (Entwurf 2026-11-16).

**Nicht in diesem Plan:** Offline-Schreibbetrieb/Sync-Queue (Spec §2), Play-Store-Paket (O3),
Migration auf `ConceptSplitView` (O1), Redesign der Mobil-IA (Spec §4.1 ist bindend),
Backend/REST/MCP (keine Änderung außer der Präferenz-Registrierung in M3 — Tool-Zahl bleibt,
alle Drift-Gates unberührt).

---

## 0. Globale Constraints

- **Layer-Disziplin unverändert:** keine Änderung an `backend/`, `rest_api/`, `mcp_server/`.
  Damit sind `test_tool_manifest_drift.py` und `test_entity_surface_parity.py` per Konstruktion
  grün; wer hier etwas ändert, hat den Auftrag verlassen. Einzige Ausnahme (M3): die
  Registrierung des Präferenzschlüssels `ui.pwa.install_dismissed` im bestehenden Katalog —
  keine Migration, kein Tool, kein API-Vertrag.
- **Keine Rohwerte in Komponenten:** Farben/Größen aus `styles/tokens.css`; `@media`-Werte
  müssen den dokumentierten Tokens entsprechen (`tokens.css:904-912` sagt das ausdrücklich).
  Neue Werte nur als Token (z. B. `--bp-sm: 640px`).
- **i18n:** kein englisches Literal in einer DE-Ansicht. Jedes neue Bedienelement bekommt
  Schlüssel in **beiden** Sprachdateien (`frontend/src/i18n/`).
- **`data-testid` auf jedem neuen interaktiven Element** (E2E-Pflicht, AGENTS.md).
- **A11y bleibt Gate:** `e2e/tests/a11y-smoke.spec.ts` läuft zusätzlich bei 390 px; Touch-Ziele
  ≥ 44 px; Fokus-Falle des Drawers (`SidebarNavigation`) darf nicht regressieren.
- **Druckansicht bleibt:** `@media print`-Regeln (u. a. `Documents.module.css`) dürfen durch
  neue mobile Regeln nicht überschrieben werden — Drucktests in M9.
- **Kein `100vh` mehr** in Shell/Editoren (Spec §7.1); `dvh` mit `vh`-Fallback.
- **SW fasst `/api/` und `/mcp/` nie an** (Spec §8) — das ist die härteste Regel des Plans.
- **Jede Scheibe ist allein mergebar** und lässt die App in beiden Zuständen funktionsfähig
  (installierbar ohne SW, SW ohne Install-UI, mobil repariert ohne Tabellen-Politur).

## 1. Schnitt-Übersicht

| # | Schnitt | Agent | Depends on | Mergebar allein? | Aufwand |
|---|---|---|---|---|---|
| M0 | Messbasis: mobile Playwright-Projekte + Ist-Audit | e2e-tester | — | **ja** (nur Tests) | 0,5 d |
| M1 | PWA-Grundgerüst: Manifest, Icons, `index.html`, nginx | frontend-component-engineer | — | **ja** — danach installierbar | 1 d |
| M2 | Service Worker + Offline-Hülle + Update-Hinweis | senior-developer | M1 | ja | 1 d |
| M3 | Installations-UX (Android-Prompt, iOS-Anleitung, Einstellungen) | frontend-component-engineer | M1 | ja | 0,75 d |
| M4 | Shell/Höhen/Safe-Areas | frontend-component-engineer | — | ja | 0,5 d |
| M5 | SplitView mobil: Zustand, Zurück-Schritt, i18n | senior-developer | M4 | ja | 1,5 d |
| M6 | Listen, Filter, Zeilenaktionen, Tabellen | frontend-component-engineer | M4 | ja | 1,5 d |
| M7 | Detail-/Editorflächen und Inspector als Sheet | frontend-component-engineer | M5 | ja | 1,5 d |
| M8 | Schwere Ansichten: Verbindungsbaum, Matrix, Diagramm/Canvas | senior-developer | M6 | ja | 2 d |
| M9 | Abnahme, Doku, CI-Verdrahtung | validator + technical-writer | M1–M8 | ja | 0,5 d |

Gesamt ≈ **10,75 Tage** (ohne O1-Migration). M1–M4 sind der schnelle Weg zu „installierbar und
nicht mehr kaputt"; M5–M8 sind die eigentliche Mobil-Arbeit.

---

## 2. M0 — Messbasis

**Ziel:** Vor der ersten Zeile Produktivcode ist belegt, was kaputt ist — statt es zu glauben.

- [ ] `e2e/playwright.config.ts`: Projekte `mobile-chrome` (`devices['Pixel 7']`) und
      `mobile-safari` (`devices['iPhone 13']`) ergänzen; Desktop-Projekt unverändert lassen.
- [ ] `e2e/tests/mobile-smoke.spec.ts`: Login, Dashboard, `/requirements`, `/documents`,
      `/traceability`, `/connections`; je Route Assertion
      `document.documentElement.scrollWidth <= clientWidth + 1` und ein Screenshot
      `mobile-<route>.png` (nur `toHaveScreenshot` im mobilen Projekt).
- [ ] `e2e/helpers/mobile.ts`: `expectNoHorizontalDocumentScroll(page)` und
      `openFirstListItem(page)` (kapselt die zwei Zeilen-Konventionen
      `aria-selected`/`aria-pressed`).
- [ ] `docs/plans/mobile-baseline-2026-11.md` (neu, kurz): Ist-Audit je Route — was bricht,
      mit Screenshot-Verweis und `pfad:zeile`. Ergebnis wird zur Abhakliste für M4–M8.
- [ ] CI: die mobile Suite als eigener Shard einhängen (`.github/workflows/playwright.yml`),
      damit sie nicht am Desktop-Shard hängt.

**DoD:** Suite läuft lokal und in CI; der Baseline-Bericht nennt je Route mindestens einen
Befund oder belegt Abwesenheit. **Kein** Produktivcode in diesem Schnitt.

---

## 3. M1 — PWA-Grundgerüst (installierbar)

**Ziel:** Chrome/Android bietet „App installieren" an; die installierte App startet standalone.
Noch ohne Service Worker — das ist laut Spec §3.3 zulässig und hält den Schnitt klein.

- [ ] `frontend/public/icons/` anlegen: `icon.svg` (Master), `icon-192.png`, `icon-512.png`,
      `maskable-512.png` (Safe-Zone 80 %, Motiv innerhalb 40 % Radius), `apple-touch-180.png`
      (deckend, ohne Transparenz — iOS zeigt sonst Schwarz).
- [ ] `frontend/public/manifest.webmanifest` nach Spec §6.1.
- [ ] `frontend/index.html` nach Spec §6.2 (`viewport`, `manifest`, `theme-color` hell/dunkel,
      `apple-touch-icon`, `mobile-web-app-capable`). `viewport-fit=cover` **und**
      `interactive-widget=resizes-content` in **einem** `content`-Attribut.
- [ ] `frontend/src/config/app-name.ts` bleibt die Namensquelle; `name`/`short_name` im
      Manifest müssen dazu passen (Test: `frontend/src/test/pwa-manifest.test.ts` liest die
      Datei per `fs` und vergleicht mit dem Default `"ReqogniLoom"`; bei gesetztem
      `VITE_APP_NAME` ist der Test bewusst tolerant und prüft nur Nicht-Leere).
- [ ] `frontend/src/test/pwa-icons.test.ts`: liest PNG-Header (Bytes 16–24) und prüft
      192×192, 512×512, 180×180 — kein Bild-Decoder, keine neue Abhängigkeit.
- [ ] `frontend/nginx.conf`: `location = /manifest.webmanifest` mit
      `Cache-Control: no-cache` + `include /etc/nginx/snippets/security-headers.conf;`;
      `webmanifest` in die MIME-Auslieferung (nginx `mime.types` deckt es ab — im
      Container-Test verifizieren).
- [ ] `frontend/scripts/check-nginx-headers.sh`: Manifest-Pfad in die geprüften Routen
      aufnehmen (Header + Content-Type), damit die Regression aus RB-D02 nicht zurückkommt.
- [ ] `docs/features/mobile-and-pwa.md` (neu): Installation auf Android/iOS, was die App
      offline kann (in M1: nichts), wie man sie deinstalliert.

**Tests:** Manifest-JSON valide, Icon-Maße, `curl`-Smoke im CI (`nginx-headers-smoke`-Job
erweitert), Lighthouse-Manualcheck in Chrome DevTools (Application → Manifest: „Installable").

**DoD:** Chrome/Android zeigt Installations-Promotion, WebAPK landet auf dem Home-Screen,
Start ist standalone, Name/Icon korrekt. Keine Änderung an CSP, keine neue Dependency.

---

## 4. M2 — Service Worker und Offline-Hülle

**Ziel:** Die installierte App startet sofort und zeigt bei fehlendem Netz eine ehrliche Hülle
statt einer Browser-Fehlerseite. **Keine** Fachdaten im Cache.

- [ ] `vite-plugin-pwa` als `devDependency`; `frontend/vite.config.ts`:
      `registerType: "prompt"`, `injectRegister: "auto"`,
      `workbox.navigateFallback: "/index.html"`,
      `navigateFallbackDenylist: [/^\/api\//, /^\/mcp\//, /^\/admin\//, /^\/static\//]`,
      `globPatterns: ["**/*.{js,css,html,woff2,png,svg,webmanifest}"]`,
      `cleanupOutdatedCaches: true`.
- [ ] Explizite Laufzeitregeln (Spec §6.3): `NetworkOnly` für `/api/`, `/mcp/`;
      `CacheFirst` für `/assets/`; `StaleWhileRevalidate` für Icons/Manifest. **Kein**
      `NetworkFirst` auf API-Pfaden, auch nicht als „nur lesend".
- [ ] `frontend/src/pwa/register.ts`: Registrierung, `updatefound`-Erkennung, Export
      `applyUpdate()`/`onUpdateAvailable()`; in `index.tsx` eingehängt (nicht in `App.tsx`,
      damit Tests ohne SW laufen).
- [ ] `frontend/src/components/shared/UpdateBanner/`: „Neue Version verfügbar — jetzt neu
      laden" (`pwa-update-banner`), i18n DE/EN, `role="status"`, kein Auto-Reload.
- [ ] `frontend/src/components/shared/OfflineNotice/`: Banner bei `navigator.onLine === false`
      („Offline — Änderungen können nicht gespeichert werden"), `data-testid="offline-notice"`;
      verschwindet bei `online`.
- [ ] Logout-Pfad (`frontend/src/context/AuthContext.tsx`): `postMessage` an den SW
      (`{type: "purge-caches"}`) und im SW `caches.delete` für alle Cache-Namen.
- [ ] `frontend/src/test/pwa-sw-policy.test.ts`: liest die generierte
      `vite.config.ts`-Konfiguration (bzw. die exportierte `workbox`-Konstante) und asserted,
      dass `/api/` und `/mcp/` in `navigateFallbackDenylist` stehen **und** in keiner
      Laufzeitregel mit Cache-Strategie auftauchen. Der Test ist der Wächter gegen den
      Datenschutz-Fehler aus Spec §8.
- [ ] `frontend/nginx.conf`: `location = /sw.js` mit `no-cache, no-store, must-revalidate`,
      Security-Header-Include; `check-nginx-headers.sh` prüft zusätzlich die Cache-Direktive.
- [ ] `docs/features/mobile-and-pwa.md` fortschreiben: Cache-Inhalt, Update-Verhalten,
      Logout-Löschung.

**Tests:** E2E `pwa.spec.ts` — SW registriert (`navigator.serviceWorker.ready`), Offline via
`context.setOffline(true)`: Navigation auf `/requirements` rendert die Hülle + Offline-Hinweis;
`/api/`-Antwort ist **nicht** im Cache (`caches.keys()` + `cache.match`). Update-Banner erscheint
nach einem simulierten `waiting`-Worker.

**DoD:** Offline-Start zeigt Shell statt Netzfehler; ein Logout hinterlässt keinen API-Eintrag
im Cache; Update wird nie ungefragt eingespielt.

---

## 5. M3 — Installations-UX

**Ziel:** Ein sichtbarer Weg in die Installation, der auf Android wirklich installiert und auf
iOS ehrlich erklärt.

- [ ] `frontend/src/hooks/useInstallPrompt.ts`: fängt `beforeinstallprompt`, hält das Event,
      meldet `canInstall`; `promptInstall()` ruft `prompt()` und wertet `userChoice` aus;
      erkennt `display-mode: standalone` (`matchMedia`) und blendet danach aus.
- [ ] `frontend/src/components/NavigationShell/InstallAppButton.tsx`
      (`data-testid="install-app"`): im Sidebar-Fuß und in `UserProfileSettings`; auf
      Nicht-Chromium öffnet er das Anleitungs-Sheet (`InstallInstructionsSheet`), das die
      Teilen-Anleitung für iOS zeigt — kein toter Knopf.
- [ ] „Nicht mehr fragen": Präferenz `ui.pwa.install_dismissed` über den bestehenden
      Präferenzdienst (Muster: `frontend/src/api/preference-values.ts`,
      `ui.connection_view.*`), inkl. Backend-Registrierung — **Ausnahme von „kein Backend"**:
      die Präferenz ist Nutzerzustand, kein Fachdatum; Registrierung in
      `backend/auth_tenancy/apps.py` und Test in `test_preference_keys_ordering.py`.
- [ ] i18n: `pwa.install.*` in DE und EN.
- [ ] `frontend/src/test/useInstallPrompt.test.ts`: Event-Reihenfolge, `userChoice`-Ausgänge
      (`accepted`/`dismissed`), Standalone-Erkennung, Dismiss-Persistenz.

**DoD:** Auf Android führt der Knopf zur echten Installation; nach Installation ist der Knopf
weg; auf iOS erklärt das Sheet den Weg; ein abgelehnter Prompt wird respektiert und nicht
erneut aufgedrängt.

---

## 6. M4 — Shell, Höhen, Safe-Areas

**Ziel:** Nichts verschwindet mehr hinter der mobilen Browser-Leiste oder der Tastatur.

- [ ] `AppShell.module.css:7` → `height: 100dvh` (mit `100vh` davor als Fallback),
      `.main`-Padding unter 640 px auf `--space-3`/`--space-4`.
- [ ] `SidebarNavigation.module.css:16` (`100vh` → `dvh`), Drawer-Breite `min(85vw, 320px)`,
      `padding-top: env(safe-area-inset-top)`, Schließen bei Routenwechsel (falls nicht schon
      vorhanden: `NavigationShell`-Test ergänzen).
- [ ] `LoginPage.module.css:10` → `100dvh`; Formular `min-width` durch `width: min(100% - 2*var(--space-4), 420px)` ersetzen (320 px Mindestbreite bricht auf 360-px-Geräten mit Tastatur).
- [ ] `WorkflowEditor.module.css:17,1106`, `DiagramGraphEditor.module.css:17`,
      `SystemSettings.module.css:51`: `100vh` → `100dvh` in den `calc()`-Ausdrücken.
- [ ] Detailspalten-Fuß: `padding-bottom: env(safe-area-inset-bottom)` für die klebende
      Speicherleiste (Vorbereitung für M7).
- [ ] `frontend/src/test/mobile-shell.test.ts`: statische Assertions auf `dvh` und
      `env(safe-area-inset` in den vier Dateien (Muster: bestehender
      `Dialog.test.tsx:628-650` prüft CSS-Inhalte genauso).

**DoD:** Auf Pixel 7 und iPhone 13 (Playwright-Geräteprofile) ist die Fußzeile jeder Route
vollständig sichtbar; Tastatur-Test in M0-Screenshot nachvollzogen.

---

## 7. M5 — SplitView mobil (Kern)

**Ziel:** Detail ersetzt die Liste mit einem echten Zurück-Schritt — auf allen 17 Aufrufern,
ohne sie einzeln umzubauen.

- [ ] `SplitView.tsx`: `isResponsiveCollapsed` in zwei Zustände zerlegen:
      `isMobile` (Breakpoint, via bestehendem Resize-Effekt) und
      `mobilePane: "list" | "detail"`.
- [ ] Mobil rendert **entweder** Liste **oder** Detail (`display: none` für die versteckte
      Seite, nicht unmounten — Scroll-Position); die Tab-Leiste
      (`MOBILE_TAB_ROW_STYLE`) entfällt.
- [ ] Zurück-Schritt: `data-testid="splitview-back"`, `aria-label` aus i18n, sichtbar nur
      mobil, an derselben Kopfzeile wie der Detailtitel (Portal-Slot `detailBack`? — Umsetzung
      im Primitiv: ein `SplitView`-eigener Kopfstreifen über dem Detail, damit kein Aufrufer
      angefasst werden muss).
- [ ] Auswahl-Kopplung: Wechsel von `rightPanel`/`detail`-Inhalt (Prop-Identität) schaltet
      `mobilePane` auf `"detail"`; ein Zurück setzt `"list"` und fokussiert die zuletzt
      gewählte Zeile (`[aria-selected="true"], [aria-pressed="true"]`).
- [ ] i18n: `splitView.list`, `splitView.detail`, `splitView.back` (DE/EN); die englischen
      Literale `List`/`Detail` entfernen.
- [ ] Tests: `frontend/src/test/SplitView.mobile.test.tsx` — Zustandsmaschine
      (`isMobile` × `mobilePane` × Detail vorhanden), Breakpoint-Wechsel setzt `mobilePane`
      zurück, Scroll-Position bleibt, Labels aus i18n.
- [ ] E2E: `e2e/tests/mobile-list-detail.spec.ts` über `/requirements`, `/needs`, `/risks`,
      `/issues`, `/adrs`, `/testcases`, `/glossary`, `/baselines`: Zeile öffnen → Detail
      sichtbar, Liste nicht → Zurück → Liste sichtbar, gewählte Zeile im Blick.

**DoD:** Auf 390 px ist jeder Artefakt-Pfad Liste → Detail → Zurück bedienbar; kein
horizontaler Overflow; DE-Oberfläche ohne englische Labels.

---

## 8. M6 — Listen, Filter, Zeilenaktionen, Tabellen

**Ziel:** Finden und Auswählen funktioniert mit dem Daumen.

- [ ] `ListToolbar.module.css`: unter 640 px Suche volle Breite, Filter in zwei Zeilen,
      „Weitere Filter" als Sheet (Dialog-Primitiv, `use-sheet-gestures` existiert).
- [ ] `ArtifactRow`: Zeilenaktionen als sichtbares Kebab (`data-testid="row-actions"`),
      Sheet unter 640 px; `ArtifactRow.module.css` bekommt keinen Hover-only-Zugang.
- [ ] `ArtifactTable.module.css`: erste Spalte `position: sticky; left: 0` mit
      Hintergrund-Token, Kopfzeile sticky; `overflow: auto` bleibt der Scroll-Ort.
- [ ] Sammelleiste: klebt über `safe-area-inset-bottom`, solange Auswahl besteht
      (`data-testid="bulk-bar"`).
- [ ] Hover-only-Stellen aus Spec §3.2 (B4) auflösen: `WorkflowEditor.module.css:550`,
      `DiagramGraphEditor.module.css:480`, `AllocationGraph.module.css:231` — unter
      `@media (hover: none)` dauerhaft sichtbar.
- [ ] Tests: `ArtifactTable`-Unit (sticky-Spalte als CSS-Assertion), E2E-Filter-Sheet,
      E2E-Sammelleiste auf 390 px.

**DoD:** Jede Aktion einer Listenzeile ist ohne Hover erreichbar; Filter bleiben lesbar; keine
Tabelle schiebt das Dokument.

---

## 9. M7 — Detail- und Editorflächen

**Ziel:** Bearbeiten auf dem Telefon ist langsam, aber möglich — oder sichtbar nicht angeboten.

- [ ] Formulare einspaltig unter 768 px (gemeinsame Primitives:
      `shared/ArtifactForm`, `shared/CreateFormFields`, `FormField`).
- [ ] Klebende Speicherleiste im Detail (`data-testid="detail-save-bar"`) über der Safe-Area;
      `useSaveShortcut` bleibt zusätzlich (Desktop), kein Ersatz.
- [ ] Inspector unter 768 px als Bottom-Sheet (Dialog-Primitiv), Trigger im Detailkopf.
- [ ] `MarkdownField`-Toolbar horizontal scrollbar (kein Umbruch in drei Zeilen).
- [ ] Editoren mit vielen Feldern (`RequirementEditors`, `ArchitectureEditors`,
      `TestCaseEditors`): Abschnitts-Reihenfolge unverändert, nur Darstellung; kein
      Collapse-Verhalten neu erfinden.
- [ ] Unit: `FormField`/`ArtifactForm` CSS-Assertions; E2E: Bearbeiten + Speichern auf
      `mobile-chrome` für Requirement und Testfall.

**DoD:** Anlegen/Bearbeiten/Speichern eines Requirements und eines Testfalls ist auf 390 px
ohne Zoom möglich; die Speicherleiste ist immer erreichbar.

---

## 10. M8 — Schwere Ansichten

**Ziel:** Kein kaputter Editor, keine zwei 180-px-Bäume, keine unlesbare Matrix.

- [ ] `ConnectionView`: unter 768 px Tabs `Anforderungen`/`Architektur` (Umschalter wie
      Modus-Leiste, `data-testid="allocation-trees-tabs"`), Kanten als Textzeile je Zeile
      (bestehende Zieltexte in `AllocationTreesRenderer`), Overlay aus (keine Messung über
      verdeckte Spalten).
- [ ] `PermissionMatrix`/`WorkflowPermissionsSection`: `min-width: 520px` bleibt, aber in
      einem `overflow-x`-Container mit fixierter erster Spalte und Hinweis
      („horizontal scrollen") — kein Quetschen.
- [ ] `MetricsDashboard`: Kacheln unter 768 px einspaltig, Diagramme `min-height` statt fester
      Höhe.
- [ ] `DiagramGraphEditor`/`CanvasEditor`: Touch-Pan + Pinch-Zoom (Pointer Events), im
      mobilen Modus **read-only** mit Hinweis `data-testid="editor-desktop-hint"`
      („Bearbeiten am Desktop"); Speichern/Anlegen deaktiviert.
- [ ] `TraceabilityView`: Zellinhalte umbrechen nicht, Container scrollt, Kopfspalte sticky.
- [ ] E2E: `mobile-heavy-views.spec.ts` — Tabs, Scroll-Container, Read-only-Hinweis,
      kein Dokument-Overflow auf `/connections`, `/traceability`, `/metrics`, `/diagrams`.

**DoD:** Jede schwere Ansicht ist auf 390 px lesbar und navigierbar; wo Bearbeiten nicht
sinnvoll ist, sagt die Oberfläche das, statt es halb zu können.

---

## 11. M9 — Abnahme, Doku, CI

- [ ] `docs/features/mobile-and-pwa.md` final: Gerätematrix, Installation Android/iOS,
      Offline-Grenzen, bekannte Einschränkungen (schwere Editoren read-only, Offline nur Hülle).
- [ ] `docs/REQUIREMENTS.md`: Abschnitt „Mobile Oberfläche und installierbare PWA (M1–M9)"
      mit REQ-209 … REQ-215, Status nach Umsetzung auf `Done` setzen (Vorlage liegt bei).
- [ ] `docs/superpowers/specs/index.md` und `docs/superpowers/plans/index.md`: Status auf
      „implemented" umstellen, mit Belegen (`pfad:zeile`, PR-Nummern) — erst wenn M1–M8
      gemergt sind.
- [ ] CI: mobile Shard in `.github/workflows/playwright.yml`, `check-nginx-headers.sh`-Job um
      Manifest/SW erweitert, `pwa-manifest.test.ts` in der normalen Vitest-Suite.
- [ ] Druckansicht prüfen (`e2e/tests/document-reading-view.spec.ts` und Print-CSS): die neuen
      mobilen Regeln dürfen `@media print` nicht verändern.
- [ ] Abschluss-Notiz in `docs/plans/mobile-baseline-2026-11.md`: welche Baseline-Befunde
      geschlossen wurden, welche bewusst offen bleiben (mit Begründung).

**DoD:** Jede Zeile der Abnahmekriterien aus Spec §9 ist belegt (Test, Screenshot oder
manueller Geräte-Nachweis); Dokumentation beschreibt den ausgelieferten Stand, nicht den
geplanten.

---

## 12. Querschnitt-Gates (jede Scheibe)

| Gate | Prüfung |
|---|---|
| Tokens | keine neuen Literale in `@media`; neue Werte als Token mit Kommentar |
| i18n | `DE`- und `EN`-Schlüssel vorhanden, kein Literal im JSX |
| A11y | axe bei 390 px grün, Touch-Ziele ≥ 44 px, Fokus-Falle Drawer unverändert |
| Tests | `npm test`, `npm run lint`, `tsc -p tsconfig.build.json` |
| nginx | `bash frontend/scripts/check-nginx-headers.sh <url>` grün |
| Backend | unverändert bis auf die Präferenz-Registrierung (M3); Tool-Manifest-Drift per Konstruktion grün |
| E2E | Desktop-Suite unverändert grün, mobiler Shard grün |
| Doku | `docs/features/mobile-and-pwa.md` beschreibt den Stand der Scheibe |

## 13. Offene Entscheidungen (blockieren den Start)

| # | Entscheidung | Optionen | Wirkung |
|---|---|---|---|
| **E1/E2** | Offline-Umfang und Service Worker | (a) Hülle + SW (Empfehlung), (b) nur installierbar ohne SW, (c) Offline-Fachdaten (großer Vorlauf) | entscheidet über M2 und die Hälfte des Risikoprofils |
| **E3** | `vite-plugin-pwa` einführen | (a) ja (Empfehlung), (b) handgeschriebener SW | neue Dev-Abhängigkeit vs. eigener Precache-Generator |
| **E7/O1** | Legacy-SplitView reparieren oder auf `ConceptSplitView` migrieren | (a) reparieren (Empfehlung), (b) 17 Aufrufer migrieren, Legacy löschen | (b) ist sauberer, aber ein eigener Umbau mit eigenem Plan |
| **O2** | Icon-Motiv | (a) Monogramm „RL" aus der Wortmarke, (b) neu zeichnen | blockiert nur M1 |
| **O3/O4** | Play-Store-Paket, „Was ist neu"-Notiz | ja/nein | nicht blockierend, nur Doku/Scope |

Ohne Entscheidung zu E1/E2 wird **nicht** mit M2 begonnen; M1, M4–M8 sind unabhängig davon
startbar.
