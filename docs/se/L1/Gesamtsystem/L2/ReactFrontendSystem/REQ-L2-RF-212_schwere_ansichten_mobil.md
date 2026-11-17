---
type: REQ
scope: REQ-L2-RF-212
status: Teilweise
date: 2026-11-16
author_agent: senior-developer
legacy_id: REQ-212
sources:
  - docs/superpowers/specs/2026-11-16-mobile-pwa-design.md
  - docs/plans/mobile-baseline-2026-11.md
  - docs/features/mobile-and-pwa.md
---

# REQ-L2-RF-212: Schwere Ansichten — lesbar mobil, Bearbeiten am Desktop (M8, ex REQ-212)

**Implementation State:** Teilweise Implementiert
**Test Status:** Teilweise (M8: Tabs, horizontal scrollende Container, gestapelte Kacheln und `editor-desktop-hint` umgesetzt; Touch-Pan/Pinch-Zoom in Diagramm/Canvas offen — nur Hinweis vorhanden; Dialog-Sheet greift erst unter 640 px)
**Traceability:** REQ-L1-017, REQ-L1-027 (mitwirkend), REQ-L1-070 (mitwirkend)

## Beschreibung

Unter 768 px zeigt die Verbindungsansicht `trees` Tabs „Anforderungen"/„Architektur" statt zweier Spalten (Kanten zusätzlich als Text je Zeile); Matrizen (Berechtigungen, Traceability) scrollen horizontal in einem Container mit fixierter erster Spalte; Kennzahlen-Kacheln stapeln; Diagramm- und Canvas-Editor sind mobil read-only mit Touch-Pan/Pinch-Zoom und einem sichtbaren Hinweis `editor-desktop-hint` („Bearbeiten am Desktop"). Kein horizontales Scrollen des Dokuments auf einer Route.

Quellen/Back-links: `docs/superpowers/specs/2026-11-16-mobile-pwa-design.md`, `docs/plans/mobile-baseline-2026-11.md`, `docs/features/mobile-and-pwa.md`.

## Akzeptanzkriterien

- [ ] Unter 768 px zeigt `trees` Tabs statt zweier Spalten; Kanten zusätzlich als Text je Zeile.
- [ ] Matrizen scrollen horizontal im Container mit fixierter erster Spalte.
- [ ] Kennzahlen-Kacheln stapeln unter 768 px.
- [ ] Diagramm- und Canvas-Editor sind mobil read-only und zeigen `editor-desktop-hint`.
- [ ] Touch-Pan/Pinch-Zoom in Diagramm/Canvas ist verfügbar (nicht implementiert).
- [ ] Keine Route verursacht horizontales Scrollen des Dokuments.
