# ReqogniLoom unterwegs: mobile Oberfläche und installierbare PWA

**Stand:** 2026-11-16 · Schnitte **M0–M9** aus
[`docs/superpowers/plans/2026-11-16-mobile-pwa.md`](../superpowers/plans/2026-11-16-mobile-pwa.md)
weitgehend umgesetzt — die unten unter „Bekannte Grenzen" genannten Reste bleiben offen.
Grundlage: Spec
[`2026-11-16-mobile-pwa-design.md`](../superpowers/specs/2026-11-16-mobile-pwa-design.md),
REQ-209 … REQ-215. Build-Basis: `origin/main` `fe34e583`.

**Belege (Stand bei Schnitt, nicht erneut verifiziert):** Commits `a9dd6a49`, `dc03bb19`,
`1dba30c4`; die M6–M9-Folge steht als *pending commit* aus. Grün sind die **strukturellen**
Gates (Manifest, Icons, MIME/Cache, SW-Richtlinie) sowie statische/gemockte Tests. Offen:
Touch-Pan/Zoom, Filter-Sheet <640 px, allgemeine klebende Sammelleiste, Inspector-Sheet erst
<640 px, iOS nur in Emulation, keine gerenderten E2E-Screenshots / kein Lighthouse, manueller
Android-Installationsnachweis.

## Was jetzt da ist

**Installierbare PWA**
- Manifest `/manifest.webmanifest` mit Name, `start_url: "/"`, `scope: "/"`,
  `display: standalone`, `display_override` und den Icons 192/512 (maskable 512).
- Icons in `frontend/public/icons/` („RL"-Monogramm aus der Wortmarke; Master `icon.svg`,
  Generator `python3 frontend/scripts/generate-icons.py`, Farben aus `tokens.css`).
- `theme-color` hell/dunkel, `apple-touch-icon` (180 px) und
  `viewport-fit=cover, interactive-widget=resizes-content`.
- Service Worker aus `vite-plugin-pwa`/Workbox (`registerType: prompt`): App-Hülle und
 statische Assets im Cache, `/api/`, `/mcp/`, `/admin/`, `/static/` **nie**. Offline-Banner und
  Update-Banner mit explizitem „Jetzt neu laden" (kein Auto-Reload). Logout löscht alle Caches.
- In-App-Einstieg `install-app` im Sidebar-Fuß und auf der Profilseite: Android nutzt
  `beforeinstallprompt`, iOS zeigt eine Teilen-Anleitung; „Nicht mehr fragen" wird als
  Nutzerpräferenz `ui.pwa.install_dismissed` gespeichert.

**Mobile Oberfläche**
- Navigation: Off-Canvas-Drawer ≤ 1024 px, Breite `min(85vw, 320px)`, Safe-Area-Padding.
- Liste → Detail ≤ 768 px: Detail ersetzt die Liste, ein Zurück-Schritt führt zurück;
  beide Panele bleiben gemountet (Scroll-Position bleibt erhalten); keine englischen
  Tab-Labels mehr.
- Shell/Editoren rechnen mit `100dvh` statt `100vh`; Login-Formular hat kein hartes
  320-px-Minimum; Touch-Kontrollen haben 16 px Schrift (kein iOS-Focus-Zoom).
- Filterzeilen brechen auf, Zeilenaktionen sind ohne Hover erreichbar, Tabellen behalten
  die erste Spalte beim horizontalen Scrollen.
- Verbindungsansicht `trees`: unter 768 px Tabs „Anforderungen"/„Architektur" statt
  zweier schmaler Spalten; Kanten-Overlay aus, Zieltexte bleiben.
- Diagramm-/Canvas-Editor zeigen unter 768 px einen klaren Read-only-Hinweis.

## Installieren

**Android / Chrome (und Samsung Internet):** Menü ⋮ → **„App installieren"** oder den
In-App-Knopf nutzen. Bestätigen → WebAPK im App-Drawer, Start ohne Browser-Adressleiste.
Voraussetzung: HTTPS (lokal `localhost` genügt), Manifest, 192/512-Icons, `standalone`.

**iPhone / iPad (iOS ≥ 16.4):** Safari → Teilen → **„Zum Home-Bildschirm"**. iOS hat keine
Installations-API; der In-App-Knopf öffnet deshalb die Anleitung. Ab iOS 16.4 geht das auch
aus Chrome/Edge/Firefox. Andere Android-Browser erzeugen meist nur eine Browser-Verknüpfung.

## Offline, Updates, Deinstallation

- Offline wird **nur die App-Hülle** ausgeliefert; Fachdaten werden nie im Gerät gespeichert.
  Ein Offline-Banner sagt, dass Änderungen nicht gespeichert werden können.
- Updates erscheinen als Banner und werden erst nach Klick eingespielt. Ein Deployment
  überschreibt also nie laufende Eingaben.
- Logout löscht alle Caches; die SW-Registrierung bleibt, damit die App installiert bleibt.
- Android: Icon lang drücken → Deinstallieren. iOS: Icon lang drücken → App entfernen.
  Es gibt kein Store-Paket und keine Store-Updates (Entscheidung O3).

## Bekannte Grenzen (ehrlich ausgewiesen)

- **iOS wurde nur in Emulation/Simulator geprüft** (Entscheidung O5); kein echtes Gerät
  in dieser Auslieferung.
- **Touch-Pan/Pinch-Zoom in Diagramm/Canvas ist nicht implementiert** (REQ-212): die
  Editoren zeigen den Read-only-Hinweis, die underlying Bibliotheken bieten kein
  dokumentiertes Touch-Gesture-API in der eingesetzten Version. Bearbeiten bleibt Desktop.
- „Weitere Filter" ist unter 640 px zweizeilig umgebrochen, aber **kein Bottom-Sheet**;
  der Inspector nutzt das vorhandene Sheet erst unter 640 px (nicht schon unter 768 px).
- Eine allgemeine klebende Sammelaktions-Leiste existiert noch nicht; die
  Dokument-Speicherleiste ist klebend und safe-area-bewusst.
- Chrome-Install-Prompt und Lighthouse wurden in der Bau-Sitzung nicht gegen eine
  laufende Instanz gemessen (kein Stack, kein Android-Gerät); die strukturellen Gates
  (Manifest, Icons, MIME/Cache, SW-Richtlinie) sind automatisiert geprüft.

## Prüfen

```bash
# PWA- und Mobil-Tests
cd frontend
npm test -- --run src/test/pwa-manifest.test.ts src/test/pwa-icons.test.ts \
  src/test/pwa-sw-policy.test.ts src/test/pwa-runtime.test.ts \
  src/test/mobile-shell.test.ts src/test/SplitView.mobile.test.tsx src/test/mobile-surfaces.test.tsx

# Produktions-Build (erzeugt dist/sw.js)
npm run build

# nginx-Headers gegen eine laufende Instanz
bash frontend/scripts/check-nginx-headers.sh http://localhost:5173

# Mobile E2E (benötigt laufenden Stack)
cd ../e2e && npm run test:e2e -- --project=mobile-chrome --project=mobile-safari --grep=@mobile

# Icons neu erzeugen (nur nach Token-Änderung)
cd .. && python3 frontend/scripts/generate-icons.py
```
