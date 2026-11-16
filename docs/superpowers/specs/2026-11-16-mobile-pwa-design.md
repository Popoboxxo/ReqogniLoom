---
type: SPEC
title: "Mobil bedienbar und auf Android installierbar: responsive Oberfläche + PWA-Hülle"
status: proposed
date: 2026-11-16
author_agent: planner
language: de
related_issues: []
plan: "docs/superpowers/plans/2026-11-16-mobile-pwa.md"
evidence: "Stand origin/main fe34e583 (2026-11-16); Belege als `pfad:zeile` aus dem Worktree .tmp/wt-mobile-pwa; kein laufender Stack, gerenderte Messungen sind Teil von M0"
---

# Mobil bedienbar und auf Android installierbar

> **Status: Entwurf (2026-11-16), nicht freigegeben.** §5 enthält zehn Entscheidungen mit
> Empfehlung; sie sind **Vorschläge**, nicht beschlossen. Offene Punkte stehen ausschließlich
> in §11. Kein Produktivcode, kein Commit auf `main`.
>
> **Auftrag (Nutzer, 2026-11-16):** „Ziel ist, die Website auch auf einem Handy gut aussehen zu
> lassen und als Pseudo-App auf Android (mindestens) zu speichern."

## 1. Ziel

Zwei Ziele, die sich eine Basis teilen — die gebaute SPA:

1. **Mobil bedienbar:** Jede Route ist auf einem Telefon (360–430 px Breite, Hochformat) ohne
   horizontales Scrollen des Dokuments benutzbar: Liste → Detail als echter Wechsel mit
   Zurück-Schritt, Touch-Ziele ≥ 44 px, keine Aktion, die nur per Hover erreichbar ist, keine
   Fläche, die auf `100vh` rechnet und deshalb hinter der mobilen Browser-Leiste verschwindet.
2. **Installierbar (Android, mindestens):** Die App lässt sich in Chrome auf Android als
   WebAPK auf dem Home-Screen installieren und startet dann ohne Browser-Chrome
   (`display: standalone`). iOS bekommt denselben Stand über „Zum Home-Bildschirm" im
   Teilen-Menü, ohne eigene Install-API.

„Pseudo-App" heißt hier ausdrücklich **installierbare Web-App**, keine native App, kein
Play-Store-Paket, kein Offline-Betrieb der Fachdaten.

## 2. Nicht-Ziele

- **Kein Offline-Schreibbetrieb.** Keine Sync-Queue, kein Konfliktauflösungsmodell, keine
  IndexedDB-Kopie von Artefakten. Offline wird nur die App-Hülle ausgeliefert (§6.3).
- **Kein Play-Store-/App-Store-Paket** (TWA/Bubblewrap, PWABuilder). Möglich als späteres
  Vorhaben; es ändert an dieser Spec nur den Vertrieb, nicht die Technik.
- **Kein Redesign.** Die in `docs/UI_KONZEPT.md` Kap. 6.3 beschriebene Mobil-IA ist der
  Vertrag; es wird umgesetzt, was dort steht, nicht neu erfunden.
- **Keine Backend-, REST- oder MCP-Änderung.** Kein neues Tool, kein neues Feld, keine
  Migration, keine Änderung an Service-Verträgen. Die Tool-Zahl und damit alle Drift-Gates
  bleiben unberührt. **Genau eine Ausnahme** (M3): der Schlüssel `ui.pwa.install_dismissed`
  wird im bestehenden Nutzer-Präferenzkatalog registriert (`backend/auth_tenancy/apps.py`) —
  Nutzerzustand, kein Fachdatum, keine Migration, kein neues Tool.
- **Kein Ersatz der Desktop-Oberfläche.** Mobil ist eine zweite Darstellung derselben
  Komponenten, kein zweiter Codebaum (keine `Mobile*.tsx`-Kopien der Editoren).
- **Keine Schema-Arbeit an der SE-Kaskade.** ReqogniLoom dokumentiert sich selbst; diese Spec
  ist eine Produkt-Spec, keine SE-Zelle.

## 3. Befund (Ist-Stand auf `origin/main`, belegt)

### 3.1 Was schon steht

| Baustein | Beleg | Bewertung |
|---|---|---|
| Drei Layout-Breakpoints als Tokens (`--bp-md: 768px`, `--bp-lg: 1024px`, `--bp-xl: 1600px`) | `frontend/src/styles/tokens.css:904-912` | Modell vorhanden, Umsetzung lückenhaft |
| Navigation wird bei ≤ 1024 px zum Off-Canvas-Drawer mit Burger, Overlay und Fokus-Falle (Modal-Dialog) | `frontend/src/components/NavigationShell/SidebarNavigation.module.css:45`, `SidebarNavigation.tsx` (Mobile-Drawer-Tests in `frontend/src/test/SidebarNavigation.test.tsx`) | **gut**, trägt bis Telefonbreite |
| `<Dialog>` wird bei ≤ 640 px zum Bottom-Sheet inkl. `visualViewport`-Höhe, Grabber und `env(safe-area-inset-bottom)` | `frontend/src/components/shared/Dialog/Dialog.module.css:159,168,180`, `tokens.css:886-895` | **gut**, das Muster für alle mobilen Flächen |
| Seitenkopf reserviert Platz für den Burger (≤ 1024 px) | `frontend/src/components/shared/PageHeader.module.css:53` | gut |
| Trace-Spine wandert bei ≤ 1024 px waagerecht unter den Artefaktkopf | `frontend/src/components/shared/TraceSpine/TraceSpine.module.css:226` | gut |
| Neuer SplitView-Vertrag (`list`/`detail`/`spine`) implementiert das Drei-Zonen-Modell korrekt: Liste → Detail **ersetzt** Liste, Liste bleibt gemountet (Scroll-Position), Spine waagerecht | `frontend/src/components/SplitView/SplitView.tsx:690-880` (`ConceptSplitView`, `NARROW_RATIO`, `isMobileReplace`) | **ungenutzt** — siehe 3.2 |
| Artefakt-Tabellen scrollen selbst (`overflow: auto`) | `frontend/src/components/shared/ArtifactTable/ArtifactTable.module.css:4` | Grundlage, reicht aber nicht (3.2) |
| Zwei Haltepunkte dokumentiert, `@media`-Nutzung in 14 CSS-Dateien | `grep -rn "@media" frontend/src --include=*.css` | mehr als im Audit 2026-09 („7 Regeln"), aber punktuell |

### 3.2 Die fünf Blocker

**B1 — Die mobile Umschaltung des Splits ist defekt.** Alle 17 produktiven Aufrufer nutzen den
Legacy-Vertrag (`leftPanel`/`rightPanel`); der korrekte `ConceptSplitView` ist toter Code
(Kommentar in `SplitView.tsx:745`: „No production view mounts this contract yet").
Im Legacy-Zweig trägt **eine** Zustandsvariable zwei Bedeutungen:

```tsx
const [isResponsiveCollapsed, setIsResponsiveCollapsed] = useState(
  responsiveMode && window.innerWidth < readBreakpointToken('--bp-md', FALLBACK_BP_MD)
);
...
if (isResponsiveCollapsed) { /* Mobil: nur leftPanel + Tab-Leiste */ }
// sonst: Desktop-Zweig mit Divider und zwei Spalten
```

`responsiveMode` ist per Default `true` (`SplitView.tsx:306`). Auf einem Telefon startet die
Ansicht also mobil (nur Liste), und der Klick auf „Detail" setzt `isResponsiveCollapsed=false` —
worauf der **Desktop-Zweig** rendert: zwei Spalten mit 380 px Mindestbreite plus Divider auf
390 px Viewport. Ein Öffnen des Details ist damit entweder unsichtbar (Detail-Spalte
abgeschnitten) oder unbedienbar; der Resize-Listener (`SplitView.tsx:551-560`) setzt den
Zustand bei jeder Größenänderung zusätzlich auf „mobil" zurück. **Das ist der Kern des
Auftrags.**

**B2 — Die mobilen Tabs sind hartcodiertes Englisch.** `List`/`Detail` stehen als Literale in
`SplitView.tsx:580-591`, obwohl die Datei `useTranslation` bereits importiert. In der
DE-Oberfläche erscheint Englisch; das verstößt gegen die i18n-Regel (REQ-L2-RF-001).

**B3 — Höhen rechnen gegen `100vh`.** `AppShell` (`height: 100vh`,
`NavigationShell/AppShell.module.css:7`), `SidebarNavigation.module.css:16`,
`LoginPage.module.css:10` sowie `WorkflowEditor`/`DiagramGraphEditor`/`SystemSettings`
(`calc(100vh - …)`) ignorieren die ein-/ausfahrende Browser-Leiste auf Android/iOS. Ergebnis:
abgeschnittene Fußzeilen und ein Speichern-Knopf, der hinter der Browser-Leiste liegt. Nur der
Dialog kennt bereits `dvh`.

**B4 — Breite Layouts haben keinen Mobil-Zustand.** Belegt:
- Verbindungsansicht `trees`: `grid-template-columns: minmax(0,1fr) minmax(0,1fr)` ohne
  `@media` (`ConnectionView/AllocationTreesRenderer.module.css:35`, ebenso
  `ConnectionView.module.css:451`) — zwei Bäume à ~180 px auf einem Telefon.
- Berechtigungsmatrizen haben `min-width: 520px` (`PermissionMatrix/PermissionMatrixEditor.module.css:23`,
  `WorkspaceSettings/WorkflowPermissionsSection.module.css:51`).
- `MetricsDashboard` stapelt erst ab 768 px (`MetricsDashboard.module.css:44-61`) — darunter
  ist die KPI-Zeile eine Spalte, aber die Diagramm-Kacheln bleiben breit.
- Hover-Aktionen: drei Stellen blenden Bedienelemente mit `opacity: 0` ein
  (`WorkflowEditor.module.css:550`, `DiagramGraphEditor.module.css:480`,
  `AllocationGraph.module.css:231`) — auf Touch unerreichbar.
- `useSaveShortcut` verlangt `Strg`/`Cmd` (`frontend/src/hooks/useSaveShortcut.ts:110`); auf
  dem Telefon gibt es kein Äquivalent und keinen sichtbaren Speichern-Knopf in jeder Ansicht.
- Canvas- und Diagramm-Editoren kennen `mousedown`/Wheel, aber keine Touch-Gesten
  (`frontend/src/components/canvas/CanvasEditor.tsx:962` u. a.) — Pinch-Zoom/Pan fehlen.

**B5 — Keine PWA-Hülle.** `frontend/index.html` enthält ausschließlich `charset`, `viewport`
und `title` — **kein** `<link rel="manifest">`, kein `theme-color`, kein `apple-touch-icon`.
`frontend/public/` existiert auf `main` nicht (das Verzeichnis wurde beim BluePencil-Umbau
entfernt, `6cefc200`), es gibt also auch keine Icons. Kein Service Worker, kein Manifest, keine Install-Promotion. Damit ist
die App heute **nicht installierbar**, obwohl sie alle inhaltlichen Voraussetzungen dafür hat
(HTTPS-Deployment, same-origin-API, `httpOnly`-Session-Cookie statt LocalStorage-Token —
`frontend/src/api/client.ts:8`).

### 3.3 Was der PWA-Teil technisch braucht (extern belegt)

Chrome/Chromium verlangt für die Installations-Promotion (`beforeinstallprompt`) und ein WebAPK
auf Android: HTTPS, Manifest mit `name`/`short_name`, Icons in **192 px und 512 px**,
`start_url`, `display ∈ {fullscreen, standalone, minimal-ui, window-controls-overlay}`,
`prefer_related_applications` nicht `true` — **kein** Service Worker mehr
(web.dev „Install criteria", abgerufen 2026-11-16). Der Service Worker ist damit eine
**freiwillige** Zusatzentscheidung für die Hülle, keine Installationsvoraussetzung.

Auf Android erzeugen nur Chrome (mit Google Mobile Services) und Samsung Internet ein echtes
WebAPK; andere Browser legen eine buchsenlose Verknüpfung an. Auf iOS gibt es kein
`beforeinstallprompt`; installiert wird über „Teilen → Zum Home-Bildschirm" (ab iOS 16.4 auch
aus Chrome/Edge/Firefox), und `apple-touch-icon` (180 px) bestimmt das Icon (MDN „Making PWAs
installable", Stand 2026-10-06).

## 4. Zielbild

### 4.1 Mobil-IA (bindend, aus UI-Konzept Kap. 6.3)

| Breite | Navigation | Liste/Detail | Spine |
|---|---|---|---|
| ≥ 1024 px | feste 240-px-Leiste | nebeneinander, 40 : 60, Mindestbreiten 380/520 | senkrecht zwischen den Spalten |
| 768–1023 px | Off-Canvas-Drawer + Burger | nebeneinander, 45 : 55 | waagerecht unter dem Kopf |
| < 768 px | Drawer, Breite ≤ 85 vw, schließt bei Navigation | **einspaltig**: Detail ersetzt Liste; Zurück-Schritt im Detailkopf; Liste behält Scroll-Position | waagerecht, nur im Detail |
| < 640 px | dito | dito, zusätzlich: Touch-Dichte (44 px), Formulare einspaltig, Sheet-Dialoge | dito |

Der `< 640 px`-Zustand ist keine neue Layout-Kante, sondern die **Dichte-Stufe**: dieselbe
Struktur wie `< 768 px`, aber größere Ziele, weniger Rand (`--space-3` statt `--space-6`) und
Bottom-Sheets für Dialoge (existiert bereits). Der Wert 640 px ist schon der Sheet-Breakpoint
(`Dialog.module.css:159`) und wird als `--bp-sm` dokumentiert, damit er nicht als Literal
herumliegt.

### 4.2 Installations-Erlebnis

- Android/Chromium: eigenes „Als App installieren" im Sidebar-Fuß (und in den
  Nutzer-Einstellungen), gespeist aus `beforeinstallprompt`; nach Installation
  (`display-mode: standalone`) verschwindet der Eintrag.
- iOS: derselbe Eintrag öffnet ein Bottom-Sheet mit der Teilen-Anleitung statt eines
  Install-Buttons.
- Nach Installation: Start auf `/` (bzw. zuletzt gemerkte Route? siehe E4), ohne Browser-Chrome,
  Statusbar-Farbe passend zum Theme (`theme-color` hell/dunkel).

## 5. Entscheidungen (Vorschlag, zu bestätigen)

| # | Frage | Empfehlung | Begründung / Alternative |
|---|---|---|---|
| **E1** | Umfang der „Pseudo-App" | **Installierbar + App-Hülle**, kein Offline-Schreibbetrieb | Der Auftrag sagt „speichern", nicht „offline arbeiten". Offline-Fachdaten verlangen Konfliktmodell und Tenant-Daten im Gerätespeicher — eigener großer Vorlauf |
| **E2** | Service Worker überhaupt? | **Ja, aber nur für die Hülle** (App-Shell-Precache + Navigations-Fallback, `/api/` und `/mcp/` ausdrücklich ausgenommen) | Ohne SW startet die installierte App bei wackligem Netz auf einer weißen Seite; mit SW startet sie sofort und zeigt einen ehrlichen Offline-Hinweis. Kein Caching von Fachantworten (§8) |
| **E3** | SW-Toolchain | **`vite-plugin-pwa` (Workbox, `generateSW`)** statt handgeschriebenem SW | Precache-Manifest mit Content-Hashes entsteht im Build; ein handgeschriebener SW müsste die Asset-Liste selbst pflegen und würde bei jedem Build driften. Neue Dev-Dependency ist der Preis, `registerType: "prompt"` hält Updates unter Kontrolle |
| **E4** | `start_url` | **`"/"`** (nicht „letzte Route") | Deterministischer Einstieg, keine Zustandsmaschine im Manifest; Deep-Links funktionieren weiter über die SPA-Routen. „Letzte Route" wäre eine eigene Präferenz und ein eigener Fehlerpfad |
| **E5** | Manifest-Erzeugung | **Statische Datei** `frontend/public/manifest.webmanifest` + Vitest-Drift-Test gegen `APP_NAME` (`frontend/src/config/app-name.ts`) | `VITE_APP_NAME` ist Build-Zeit-Konfiguration; ein Manifest-Rename darf nicht stillschweigend auseinanderlaufen. Ein Build-Plugin für einen 20-Zeilen-JSON ist unverhältnismäßig |
| **E6** | Icons | **Ein SVG-Master + committete PNGs** 192/512/maskable-512/apple-touch-180, Test prüft Existenz und Pixelmaße | Kein Logo-Asset im Repo (3.2/B5); PNGs müssen committet werden, weil der Build sie unverändert ausliefert und ein SVG-zu-PNG-Schritt im Docker-Build eine neue native Abhängigkeit wäre |
| **E7** | SplitView-Strategie | **Legacy-Zweig mobil reparieren** (Zustand trennen, i18n, Detail-Zurück), `ConceptSplitView` **nicht** in diesem Zug migrieren; Migration als eigene Entscheidung O1 | 17 Aufrufer in einem Zug umzubauen ist ein eigener Umbau mit Regressionsrisiko; der Legacy-Zweig ist mit ~40 Zeilen korrigierbar. Doppelte Pflege bleibt bewusst kurzfristig |
| **E8** | Breakpoints | **Keine neuen Layout-Kanten**; `--bp-sm: 640px` nur als Dichte-/Sheet-Stufe dokumentieren | Das UI-Konzept nennt zwei Haltepunkte; eine dritte Layout-Kante würde jede bestehende `@media`-Regel mehrdeutig machen |
| **E9** | Tabellen und Matrizen | **Horizontal scrollen im Container** bleibt (kein Karten-Fallback), plus erste Spalte fixiert und Zeilenaktionen immer sichtbar (Kebab statt Hover) | Ein Karten-Fallback für 20+ Tabellen ist ein zweites Rendering pro Tabelle; Scrollen im Container ist ehrlich und barrierearm, wenn die fixierte erste Spalte den Kontext hält |
| **E10** | Schwere Editoren (Diagramm, Canvas, Verbindungsbaum) | **Lesen mobil, Bearbeiten am Desktop**: Zoom/Pan per Touch, klarer Hinweis „Bearbeiten am Desktop", keine Halb-Editing-Fläche | Ein Graph-Editor auf 390 px ist kein sinnvolles Ziel; ein kaputter Editor ist schlechter als ein ehrlicher Lesemodus |

## 6. Technische Spezifikation — PWA

### 6.1 Manifest (`frontend/public/manifest.webmanifest`)

```json
{
  "name": "ReqogniLoom",
  "short_name": "ReqogniLoom",
  "description": "Requirements- und Test-Management",
  "id": "/",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "display_override": ["standalone", "minimal-ui", "browser"],
  "orientation": "any",
  "background_color": "#11151f",
  "theme_color": "#11151f",
  "lang": "de",
  "dir": "ltr",
  "icons": [
    { "src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any" },
    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any" },
    { "src": "/icons/maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ]
}
```

Regeln: `name` folgt `APP_NAME` (E5); `lang` bleibt `de` (Oberfläche ist DE/EN, die
Erstsprache der Installation ist Deutsch — Wechsel zur Laufzeit ist über `i18next` möglich,
das Manifest wird nicht pro Sprache ausgeliefert); `background_color`/`theme_color` sind
Token-Werte des Default-Themes, keine Rohwerte mit zweiter Wahrheit (Test in M1).

### 6.2 `index.html`

```html
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover, interactive-widget=resizes-content" />
<link rel="manifest" href="/manifest.webmanifest" />
<link rel="icon" href="/icons/icon-192.png" sizes="192x192" />
<link rel="apple-touch-icon" href="/icons/apple-touch-180.png" />
<meta name="theme-color" content="#11151f" media="(prefers-color-scheme: dark)" />
<meta name="theme-color" content="#f7f8fa" media="(prefers-color-scheme: light)" />
<meta name="mobile-web-app-capable" content="yes" />
<meta name="apple-mobile-web-app-capable" content="yes" />
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
```

`interactive-widget=resizes-content` ist der Android-Gegenpol zu `100dvh`: bei offener Tastatur
verkleinert sich das Layout-Fenster, statt das Feld hinter die Tastatur zu schieben.
`viewport-fit=cover` ist Voraussetzung für `env(safe-area-inset-*)`.

### 6.3 Service Worker (E2/E3)

| Anfrage | Strategie | Cache |
|---|---|---|
| Navigationsanfragen (`mode: navigate`) | `NetworkFirst`, Fallback auf gecachtes `index.html` | `app-shell` |
| Gehashte Build-Assets (`/assets/*`, Fonts) | `CacheFirst` (Unveränderlichkeit garantiert der Hash) | `app-shell` |
| `/api/*`, `/mcp/*`, `/admin/*`, `/static/*` | **nie** abfangen, nie cachen (`navigateFallbackDenylist`, `NetworkOnly`) | — |
| Alles andere same-origin (`icons`, `manifest`) | `StaleWhileRevalidate` | `static` |

Verboten (Sicherheit, §8): Caching von JSON-Antworten der API, von HTML außerhalb des
App-Shell-Fallbacks, von `Set-Cookie`-Antworten. `registerType: "prompt"` mit einem
Aktualisieren-Hinweis (Banner), damit ein Deployment nicht mitten in der Arbeit neu lädt.

### 6.4 nginx

- `/manifest.webmanifest`: korrekter MIME (`application/manifest+json`; nginx liefert ihn über
  `mime.types` für `webmanifest` aus — im Container-Test verifizieren),
  `Cache-Control: no-cache` — sonst bleibt ein umbenanntes Produkt ewig alt.
- `/sw.js`: `Cache-Control: no-cache, no-store, must-revalidate` und **kein** langes
  Asset-Caching (der Dateiname ist nicht gehasht; ein alter SW ist ein Altsystem).
- Beide Locations brauchen `include /etc/nginx/snippets/security-headers.conf;` (nginx verwirft
  sonst alle geerbten Header, siehe Kommentar in `frontend/nginx-security-headers.conf:1-14`).
- `frontend/scripts/check-nginx-headers.sh` wird um beide Pfade erweitert (Header + Cache).
- Keine CSP-Änderung nötig: Manifest fällt unter `default-src 'self'`, der SW unter
  `script-src 'self'` (Worker-Fallback `worker-src` → `script-src`).

## 7. Technische Spezifikation — Responsive

### 7.1 Shell und Höhen (B3)

- `AppShell`, `SidebarNavigation`, `LoginPage`: `height: 100dvh` mit `100vh`-Fallback davor.
- Mobile Workflow-/Diagramm-/Settings-Höhen: `calc(100dvh - …)` statt `100vh`.
- `env(safe-area-inset-top/bottom)` an Shell-Kopf und unterem Rand der Detailspalte (heute nur
  im Dialog).
- `.main`-Padding unter 640 px: `--space-3` horizontal, `--space-4` vertikal.

### 7.2 SplitView (B1/B2, E7)

Der Legacy-Zweig bekommt zwei getrennte Zustände:

```tsx
const isMobile = useMediaQuery(`(max-width: ${bpMd}px)`);   // oder Resize wie heute
const [mobilePane, setMobilePane] = useState<"list" | "detail">("list");
```

- Auswahl eines Listeneintrags schaltet `mobilePane` auf `"detail"`.
- Detailkopf erhält einen Zurück-Schritt („Zurück zur Liste", `data-testid="splitview-back"`),
  der nur mobil erscheint.
- Die Liste bleibt gemountet und wird per `display: none` verborgen (Scroll-Position, wie im
  ConceptSplitView bereits gelöst).
- Beide Tabs/Labels kommen aus `i18n` (`splitView.list`, `splitView.detail`, `splitView.back`);
  die Tab-Leiste entfällt, wenn der Zurück-Schritt existiert (eine Navigationsmetapher, nicht
  zwei).
- Ein Breakpoint-Wechsel auf Desktop setzt `mobilePane` zurück, ohne die Auswahl zu verlieren.

### 7.3 Listen, Filter, Zeilenaktionen (B4, E9)

- `ListToolbar`: Suche volle Breite, Filter in zwei Zeilen, „Weitere Filter" als Sheet unter
  640 px; keine schrumpfenden Selects unter Lesbarkeit.
- Zeilenaktionen: sichtbares Kebab-Menü (44 px), nie `opacity: 0` als einziger Zugang; das
  Menü ist ein Bottom-Sheet unter 640 px.
- Sammelaktionen: klebende Leiste über `safe-area-inset-bottom`, solange eine Auswahl besteht.
- Tabellen: Container scrollt, erste Spalte `position: sticky`, Kopfzeile bleibt sichtbar.

### 7.4 Editoren und Detailflächen

- Formulare einspaltig unter 768 px; `--control-font-size` bleibt (16 px-Zwang gegen
  iOS-Zoom auf Inputs prüfen — M0 misst).
- Speichern: sichtbarer Knopf in der Detail-Fußzeile (nicht nur `Strg+S`), klebend über der
  Safe-Area; `useSaveShortcut` bleibt Desktop-Komfort.
- Inspector wird unter 768 px zum Bottom-Sheet (Dialog-Primitiv ist bereits sheet-fähig).

### 7.5 Schwere Ansichten (E10)

- Verbindungsansicht: unter 768 px **Tabs** `Anforderungen`/`Architektur` statt zweier
  Spalten; die Allokationskanten erscheinen als Textzeile („→ Ziel", wie heute in
  `AllocationTreesRenderer` je Zeile vorhanden).
- Matrix/Traceability: horizontaler Container-Scroll, fixierte Kopfspalte, Zellinhalte
  umbrechen nicht.
- Diagramm/Canvas: Pinch-Zoom und Pan, read-only, Hinweis „Bearbeiten am Desktop".

## 8. Sicherheit und Datenschutz

- **Keine Fachdaten im Cache.** Der SW fasst `/api/` und `/mcp/` nicht an; ein geteiltes Gerät
  darf nach dem Abmelden keine fremden Artefakte aus dem Cache zeigen.
- **Logout räumt auf:** `AuthContext`-Logout schickt dem SW eine Nachricht, die alle Caches
  löscht (Registrierung bleibt, damit die App weiter installiert bleibt).
- **Tenant-Isolation bleibt serverseitig** (RLS); der SW ist kein zweiter Autorisierungspfad.
- **Offline ist sichtbar:** ein Banner erklärt, dass Schreibvorgänge offline nicht möglich sind;
  keine stillen Fehlschläge.
- **CSP bleibt eng:** keine Erweiterung für Manifest/SW nötig; die bestehende
  `check-nginx-headers.sh`-Prüfung (kein `unsafe-inline`/`unsafe-eval`) bleibt Gate.
- **Kein `localStorage`-Token:** Auth läuft über `httpOnly`-Cookie (bereits so,
  `frontend/src/api/client.ts:8`) — eine installierte PWA erbt die Session, ohne dass ein
  Token im Gerätespeicher liegt.

## 9. Test und Abnahme

| Ebene | Werkzeug | Inhalt |
|---|---|---|
| Unit | Vitest | Manifest-Drift gegen `APP_NAME`; Icon-Maße; `useInstallPrompt`-Zustände; SplitView-Zustandsmaschine (`isMobile` × `mobilePane` × Auswahl); i18n-Schlüssel vorhanden |
| E2E | Playwright, **neue Projekte** `mobile-chrome` (Pixel 7, 412×915) und `mobile-safari` (iPhone 13, 390×844) | `mobile-smoke.spec.ts`: Login, Dashboard, je Artefakt-Route Liste → Detail → Zurück, Filter-Sheet, Burger-Drawer, kein horizontales Dokument-Scrollen (`scrollWidth <= clientWidth`) |
| Visuell | Playwright `toHaveScreenshot` | je Route ein 390-px-Snapshot (Baseline neu, eigener Ordner) |
| A11y | axe (bestehendes `a11y-smoke.spec.ts`) | zusätzlich bei 390 px; Touch-Ziele ≥ 44 px stichprobenartig |
| PWA | manuell + Skript | `check-pwa.sh` gegen die gebaute Instanz: Manifest 200 + korrekter Content-Type, Icons 200 mit richtigen Maßen, `/sw.js` 200 + `no-cache`, Installierbarkeit in Chrome (DevTools → Application) |
| Gate | bestehende CI | `npm run lint`, `npm test`, `tsc -p tsconfig.build.json`, `check-nginx-headers.sh` |

Abnahmekriterien (Definition of Done des Vorhabens):

1. Auf 360 × 800 und 390 × 844 ist auf **jeder** der 30 Navigationsrouten (`NAV_ITEMS` in
   `SidebarNavigation.tsx`) das Dokument horizontal scrollfrei; Detail öffnet als Ersatz der
   Liste mit funktionierendem Zurück.
2. Chrome/Android bietet „App installieren" an; die installierte App startet standalone, zeigt
   das richtige Icon und den Produktnamen, und ein Logout hinterlässt keine API-Daten im Cache.
3. Kein sichtbares englisches Literal in der DE-Oberfläche an den mobilen Bedienelementen.
4. Alle Touch-Ziele der mobilen Primäraktionen ≥ 44 px (WCAG 2.5.8 mit Reserve).
5. `docs/features/mobile-and-pwa.md` beschreibt Installation, Grenzen (offline = Hülle) und die
   Gerätematrix.

## 10. Risiken

| Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|
| SW liefert veraltete App nach Deployment | Nutzer arbeitet auf altem Stand, ohne es zu merken | `registerType: "prompt"` + sichtbarer Aktualisieren-Hinweis; `/sw.js` nie cachen |
| Cache leakt Tenant-Daten auf geteiltem Gerät | Datenschutzvorfall | Kein API-Caching (technisch erzwungen, getestet), Cache-Löschung beim Logout |
| 17 Legacy-SplitView-Aufrufer, je eigene Detail-Kopfzeile | Zurück-Schritt wird 17× unterschiedlich | ein `SplitDetailHeader`-Primitiv mit `data-testid`, E2E-Sweep über alle Routen |
| E2E-Laufzeit wächst (2 Geräte × Smoke) | CI-Zeit, Shard-Balance | Mobile-Suite als eigener Shard, nur Smoke (keine visuellen Snapshots aller Routen) |
| iOS-Verhalten (Installation, Session-Lifetime) weicht ab | „Funktioniert auf Android, nicht auf iPhone" | iOS nur als „unterstützt, ohne Install-API" zusagen; Teilen-Anleitung und Test auf einem echten Gerät |
| Scope-Dehnung in Editor-Umbauten | Vorhaben wird unfertig | E10: schwere Editoren bleiben read-only; alles andere ist Nicht-Ziel (§2) |

## 11. Offene Punkte

| # | Punkt | Entscheidung nötig von |
|---|---|---|
| **O1** | `ConceptSplitView` migrieren und Legacy-Zweig löschen (17 Aufrufer) — nach oder statt E7? | Auftraggeber/Architektur |
| **O2** | Icons: Monogramm aus bestehender Wortmarke ableiten oder neu zeichnen (Design-System)? | UI/Design |
| **O3** | Play-Store-Paket (TWA) als späteres Vorhaben gewünscht? | Auftraggeber |
| **O4** | Soll die installierte App eine „Was ist neu"-Notiz nach Update zeigen? | Auftraggeber |
| **O5** | iOS-Verifikation auf echtem Gerät vorhanden (oder nur Simulator)? | QS |

## 12. Quellen

- `docs/UI_KONZEPT.md` Kap. 6.3 („Schmale Fenster"), Kap. 7 (Scroll-Modell), Kap. 12.8
  (Bottom-Sheet).
- `docs/SYSTEMAUDIT_2026-09-02_GROB.md` A3 („Responsive-Modell existiert nur als Token") und
  S20 („768 px: Split-View bleibt zweispaltig").
- web.dev, „Install criteria" (abgerufen 2026-11-16): Manifest-Pflichtfelder, 192/512-Icons,
  HTTPS, kein SW-Zwang.
- MDN, „Making PWAs installable" (Stand 2026-10-06): WebAPK nur Chrome/Samsung Internet;
  iOS-Installation über Teilen-Menü, kein `beforeinstallprompt`; `display`-Fallback-Kette.
- Code-Belege siehe §3 (`pfad:zeile`, Stand `origin/main` `fe34e583`).
