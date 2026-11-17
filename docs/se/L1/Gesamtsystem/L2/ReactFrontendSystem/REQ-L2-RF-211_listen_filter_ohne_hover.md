---
type: REQ
scope: REQ-L2-RF-211
status: Teilweise
date: 2026-11-16
author_agent: senior-developer
legacy_id: REQ-211
sources:
  - docs/superpowers/specs/2026-11-16-mobile-pwa-design.md
  - docs/plans/mobile-baseline-2026-11.md
  - docs/features/mobile-and-pwa.md
open_adrs: []
---

# REQ-L2-RF-211: Listen, Filter und Zeilenaktionen ohne Hover (M6, ex REQ-211)

**Implementation State:** Teilweise Implementiert
**Test Status:** Teilweise (M6: „Weitere Filter" bricht unter 640 px nur zweizeilig um, kein Filter-Sheet; keine allgemeine klebende Sammelleiste über der Safe-Area — nur die Dokument-Speicherleiste ist klebend)
**Traceability:** REQ-L1-064, REQ-L1-066, REQ-L1-017 (mitwirkend)

## Beschreibung

Unter 640 px ist die Suche volle Breite, Filter brechen in zwei Zeilen bzw. wandern in ein Sheet, und jede Zeilenaktion ist ohne Hover erreichbar (sichtbares Kebab, Sheet statt Hover-Popover). Tabellen scrollen im Container, die erste Spalte und die Kopfzeile bleiben sichtbar; eine Sammelauswahl zeigt eine klebende Leiste über der Safe-Area.

Quellen/Back-links: `docs/superpowers/specs/2026-11-16-mobile-pwa-design.md`, `docs/plans/mobile-baseline-2026-11.md`, `docs/features/mobile-and-pwa.md`.

## Akzeptanzkriterien

- [ ] Unter 640 px nimmt die Suche die volle Breite ein.
- [ ] Filter brechen unter 640 px in zwei Zeilen um oder wandern in ein Sheet.
- [ ] Jede Zeilenaktion ist ohne Hover erreichbar (sichtbares Kebab, Sheet statt Hover-Popover).
- [ ] Tabellen scrollen im Container bei fixierter erster Spalte und fixierter Kopfzeile.
- [ ] Eine Sammelauswahl zeigt eine klebende Leiste über der Safe-Area (allgemeine Leiste noch nicht vorhanden).
