---
type: REQ
scope: REQ-L2-RF-215
status: Teilweise
date: 2026-11-16
author_agent: senior-developer
legacy_id: REQ-215
sources:
  - docs/superpowers/specs/2026-11-16-mobile-pwa-design.md
  - docs/plans/mobile-baseline-2026-11.md
  - docs/features/mobile-and-pwa.md
open_adrs: []
---

# REQ-L2-RF-215: Mobiler Abnahme-Nachweis über Geräteprofile (M0/M9, ex REQ-215)

**Implementation State:** Teilweise Implementiert
**Test Status:** Teilweise (Geräteprofil-Harness `mobile-smoke.spec.ts`/`mobile-list-detail.spec.ts` sowie statische/gemockte Manifest-, Icon-, SW-Richtlinien- und Laufzeit-Tests; keine gerenderten 390px-Screenshots, kein Chrome-Install-Prompt, kein Lighthouse, kein manueller Android-Installationsnachweis auf echtem Gerät)
**Traceability:** REQ-L1-093, REQ-L1-017 (mitwirkend)

## Beschreibung

Die E2E-Suite läuft zusätzlich mit den Playwright-Geräteprofilen `mobile-chrome` (Pixel 7) und `mobile-safari` (iPhone 13). Nachweis: Login, Dashboard, Liste → Detail → Zurück auf allen Artefakt-Routen, Filter-Sheet, Drawer, `scrollWidth <= clientWidth` je Route, axe bei 390 px, Manifest-/SW-Smoke (Content-Type, Icon-Maße, `no-cache`) und manueller Installations-Nachweis auf Android.

Quellen/Back-links: `docs/superpowers/specs/2026-11-16-mobile-pwa-design.md`, `docs/plans/mobile-baseline-2026-11.md`, `docs/features/mobile-and-pwa.md`.

## Akzeptanzkriterien

- [ ] Die Suite läuft mit `mobile-chrome` (Pixel 7) und `mobile-safari` (iPhone 13).
- [ ] Login, Dashboard und Liste → Detail → Zurück sind auf allen Artefakt-Routen nachgewiesen.
- [ ] Filter-Sheet und Drawer sind nachgewiesen; je Route gilt `scrollWidth <= clientWidth`.
- [ ] axe läuft bei 390 px; Manifest-/SW-Smoke prüft Content-Type, Icon-Maße und `no-cache`.
- [ ] Gerenderte 390px-Screenshots, Chrome-Install-Prompt, Lighthouse und der manuelle Android-Installationsnachweis liegen vor (offen).
