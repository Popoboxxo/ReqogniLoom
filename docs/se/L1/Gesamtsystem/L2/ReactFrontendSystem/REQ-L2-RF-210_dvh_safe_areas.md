---
type: REQ
scope: REQ-L2-RF-210
status: Done
date: 2026-11-16
author_agent: senior-developer
legacy_id: REQ-210
sources:
  - docs/superpowers/specs/2026-11-16-mobile-pwa-design.md
  - docs/plans/mobile-baseline-2026-11.md
  - docs/features/mobile-and-pwa.md
---

# REQ-L2-RF-210: Shell und Editoren rechnen mit dvh und Safe-Areas (M4, ex REQ-210)

**Implementation State:** Implemented
**Test Status:** Covered (mobile-shell.test.ts, dvh-/Safe-Area-Tests)
**Traceability:** REQ-L1-017

## Beschreibung

Shell (`AppShell`), Navigation (`SidebarNavigation`), Login und die mobile Höhe von Workflow-/Diagramm-/Settings-Editoren verwenden `100dvh` (mit `100vh`-Fallback) statt `100vh`, sodass nichts hinter der ein-/ausfahrenden Browser-Leiste verschwindet. Drawer und Detail-Fuß respektieren `env(safe-area-inset-top/bottom)`; unter 640 px sinkt das Inhalts-Padding auf `--space-3`/`--space-4`.

Quellen/Back-links: `docs/superpowers/specs/2026-11-16-mobile-pwa-design.md`, `docs/plans/mobile-baseline-2026-11.md`, `docs/features/mobile-and-pwa.md`.

## Akzeptanzkriterien

- [ ] `AppShell`, `SidebarNavigation`, Login und die mobilen Editor-Höhen nutzen `100dvh` mit `100vh`-Fallback.
- [ ] Inhalte verschwinden bei ein-/ausfahrender Browser-Leiste nicht hinter dieser.
- [ ] Drawer und Detail-Fuß wenden `env(safe-area-inset-top)` und `env(safe-area-inset-bottom)` an.
- [ ] Unter 640 px beträgt das Inhalts-Padding `--space-3` bzw. `--space-4`.
