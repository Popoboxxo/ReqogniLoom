---
type: REQ
scope: REQ-L2-RF-214
status: Done
date: 2026-11-16
author_agent: senior-developer
legacy_id: REQ-214
sources:
  - docs/superpowers/specs/2026-11-16-mobile-pwa-design.md
  - docs/plans/mobile-baseline-2026-11.md
  - docs/features/mobile-and-pwa.md
---

# REQ-L2-RF-214: Service Worker cached keine Fachdaten und wird beim Logout geleert (M2, ex REQ-214)

**Implementation State:** Implemented
**Test Status:** Covered (pwa-sw-policy.test.ts, Logout-Cache-Clear-Tests)
**Traceability:** REQ-L1-018, REQ-L1-017 (mitwirkend)

## Beschreibung

Ein Service Worker liefert die App-Hülle (App-Shell-Precache, Navigations-Fallback) und aktualisiert sich nur nach ausdrücklicher Bestätigung. `/api/`, `/mcp/`, `/admin/` und `/static/` werden nie abgefangen oder gecacht; ein Logout löscht alle Caches. Damit hinterlässt eine installierte PWA auf einem geteilten Gerät keine fremden Artefakte, und die Autorisierung bleibt ausschließlich serverseitig.

Quellen/Back-links: `docs/superpowers/specs/2026-11-16-mobile-pwa-design.md`, `docs/plans/mobile-baseline-2026-11.md`, `docs/features/mobile-and-pwa.md`.

## Akzeptanzkriterien

- [ ] Der Service Worker precacht die App-Hülle und liefert einen Navigations-Fallback.
- [ ] Eine neue Version wird erst nach ausdrücklicher Bestätigung eingespielt.
- [ ] `/api/`, `/mcp/`, `/admin/` und `/static/` werden weder abgefangen noch gecacht.
- [ ] Ein Logout löscht alle Caches; die SW-Registrierung bleibt erhalten.
