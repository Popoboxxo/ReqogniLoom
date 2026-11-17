---
type: REQ
scope: REQ-L2-RF-213
status: Teilweise
date: 2026-11-16
author_agent: senior-developer
legacy_id: REQ-213
sources:
  - docs/superpowers/specs/2026-11-16-mobile-pwa-design.md
  - docs/plans/mobile-baseline-2026-11.md
  - docs/features/mobile-and-pwa.md
open_adrs: []
---

# REQ-L2-RF-213: Installierbare PWA mit Manifest, Icons und Installationsweg (M1/M3, ex REQ-213)

**Implementation State:** Teilweise Implementiert
**Test Status:** Teilweise (Manifest, Icons, MIME/Cache und SW-Richtlinie strukturell automatisiert geprüft; Chrome-Install-Prompt und Lighthouse nicht gegen eine laufende Instanz gemessen, kein Android-Installationsnachweis auf echtem Gerät)
**Traceability:** REQ-L1-018, REQ-L1-017 (mitwirkend)

## Beschreibung

Die SPA liefert ein Web-App-Manifest (`name` aus `APP_NAME`, `start_url: "/"`, `scope: "/"`, `display: standalone`, Icons 192/512 plus maskable 512), `theme-color` für hell und dunkel, `apple-touch-icon` (180 px) und `viewport-fit=cover, interactive-widget=resizes-content`; nginx liefert das Manifest mit korrektem MIME und `no-cache`. Chrome/Android bietet die Installation als WebAPK an; die installierte App startet ohne Browser-Chrome. Ein sichtbarer Einstieg (`install-app`) nutzt `beforeinstallprompt` und zeigt auf iOS die Teilen-Anleitung; eine Ablehnung wird als Präferenz `ui.pwa.install_dismissed` respektiert.

Quellen/Back-links: `docs/superpowers/specs/2026-11-16-mobile-pwa-design.md`, `docs/plans/mobile-baseline-2026-11.md`, `docs/features/mobile-and-pwa.md`.

## Akzeptanzkriterien

- [ ] Das Manifest enthält `name` aus `APP_NAME`, `start_url: "/"`, `scope: "/"`, `display: standalone`, Icons 192/512 und maskable 512.
- [ ] `theme-color` ist für hell und dunkel definiert; `apple-touch-icon` ist 180 px; Viewport nutzt `viewport-fit=cover, interactive-widget=resizes-content`.
- [ ] nginx liefert das Manifest mit korrektem MIME-Type und `no-cache`.
- [ ] Chrome/Android bietet Installation als WebAPK an; die installierte App startet ohne Browser-Chrome (Nachweis auf echtem Android-Gerät steht aus).
- [ ] `install-app` nutzt `beforeinstallprompt`, zeigt auf iOS die Teilen-Anleitung und respektiert `ui.pwa.install_dismissed`.
