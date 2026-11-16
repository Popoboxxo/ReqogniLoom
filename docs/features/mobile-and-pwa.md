# ReqogniLoom unterwegs: mobile Oberfläche und installierbare PWA

**Stand:** 2026-11-16 · Schnitt **M1** von
[`docs/superpowers/plans/2026-11-16-mobile-pwa.md`](../superpowers/plans/2026-11-16-mobile-pwa.md).
Grundlage: Spec [`2026-11-16-mobile-pwa-design.md`](../superpowers/specs/2026-11-16-mobile-pwa-design.md),
REQ-209 … REQ-215. Für M1 ist **noch kein Service Worker** enthalten — der folgt in M2.

## Was jetzt schon da ist

- Web-App-Manifest unter `/manifest.webmanifest` mit Name, Start-URL `/`,
  `display: standalone` und den Icons 192/512 (maskable 512).
- Icons in `frontend/public/icons/` („RL"-Monogramm; Master `icon.svg`, generiert mit
  `python3 frontend/scripts/generate-icons.py`).
- `theme-color` für helles und dunkles Theme, `apple-touch-icon` (180 px) und der
  Viewport `viewport-fit=cover, interactive-widget=resizes-content` in `index.html`.
- Chrome/Android bietet die Installation an, sobald die Seite über **HTTPS** (oder lokal
  `localhost`) erreicht wird.

## Installieren

**Android / Chrome (und Samsung Internet):**
1. Die Instanz in Chrome öffnen.
2. Menü ⋮ → **„App installieren"** (alternativ erscheint automatisch eine Promotion, sobald
   Chrome die Installierbarkeits-Kriterien erfüllt: HTTPS, Manifest, 192/512-Icons, `standalone`).
3. Bestätigen. Das WebAPK landet im App-Drawer und startet ohne Browser-Adressleiste.

**iPhone / iPad (iOS ≥ 16.4):**
1. Die Instanz in Safari öffnen.
2. Teilen-Symbol → **„Zum Home-Bildschirm"** → Name prüfen → **Hinzufügen**.
3. Ab iOS 16.4 geht das auch aus Chrome, Edge und Firefox. Es gibt **keine**
   Installations-API (`beforeinstallprompt`) unter iOS.

**Hinweis:** Andere Android-Browser als Chrome/Samsung Internet erzeugen in der Regel nur eine
Browser-Verknüpfung mit Browser-Rahmen, kein WebAPK.

## Offline und Updates — Stand M1

- **M1:** Ohne Service Worker ist die App nur online nutzbar. Ohne Netz zeigt der Browser
  seine eigene Fehlerseite.
- **M2 (geplant):** Service Worker cached ausschließlich die App-Hülle (HTML/JS/CSS/Fonts).
  `/api/` und `/mcp/` werden nie gecacht; offline erscheint ein Banner, Schreiben bleibt
  online-only. Ein Update wird per Banner angeboten, nie automatisch eingespielt.
- Fachdaten werden **nie** im Gerät gespeichert; eine installierte PWA hinterlässt nach dem
  Logout keine Artefakte im Cache.

## Deinstallieren

- Android: Icon_long-press → **Deinstallieren** (oder Einstellungen → Apps → ReqogniLoom).
- iOS: Icon_long-press → **App entfernen**.
- Ein WebAPK ist keine native App: Es gibt keine automatischen Hintergrund-Updates über einen
  Store; Aktualisierungen kommen mit dem nächsten Deployment der Website.

## Bekannte Grenzen

- iOS wurde in dieser Auslieferung **nur in Emulation/Simulator** geprüft (Entscheidung O5).
- Noch kein eigener „Als App installieren"-Knopf in der Oberfläche — der kommt mit M3; bis
  dahin nutzt man den browser-eigenen Installationsweg.
- Die Oberfläche ist zwar installierbar, aber die Mobil-Darstellung selbst wird erst in
  M4–M8 korrigiert (u. a. ist der Liste/Detail-Umschalter bei Telefonbreite noch fehlerhaft).

## Prüfen

```bash
# Manifest und Icons (Vitest)
cd frontend && npm test -- --run src/test/pwa-manifest.test.ts src/test/pwa-icons.test.ts

# nginx-Headers gegen eine laufende Instanz
bash frontend/scripts/check-nginx-headers.sh http://localhost:5173

# Icons neu erzeugen (nur nach Token-Änderung)
python3 frontend/scripts/generate-icons.py
```
