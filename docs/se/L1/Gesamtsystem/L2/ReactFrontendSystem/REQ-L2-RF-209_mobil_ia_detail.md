---
type: REQ
scope: REQ-L2-RF-209
status: Teilweise
date: 2026-11-16
author_agent: senior-developer
legacy_id: REQ-209
sources:
  - docs/superpowers/specs/2026-11-16-mobile-pwa-design.md
  - docs/plans/mobile-baseline-2026-11.md
  - docs/features/mobile-and-pwa.md
---

# REQ-L2-RF-209: Mobil-IA — Detail ersetzt Liste mit Zurück-Schritt (M5, ex REQ-209)

**Implementation State:** Teilweise Implementiert
**Test Status:** Teilweise (strukturelle SplitView-Tests; Touch-Ziele ≥ 44 px nicht auf gerendertem 390px-Viewport gemessen)
**Traceability:** REQ-L1-017, REQ-L1-084, REQ-L1-016 (mitwirkend)

## Beschreibung

Unter `--bp-md` (768 px) zeigt jede Liste/Detail-Route entweder Liste oder Detail: die Auswahl einer Zeile öffnet das Detail, ein sichtbarer Zurück-Schritt (`splitview-back`) führt zur Liste zurück und fokussiert die zuletzt gewählte Zeile; die Liste bleibt gemountet und behält ihre Scroll-Position. Die Zustände „mobil" und „welche Seite" sind getrennt zu halten (das frühere `isResponsiveCollapsed` trug beide Bedeutungen, wodurch „Detail" auf einem Telefon den zweispaltigen Desktop-Zweig rendert). Die mobilen Bedienelemente sind übersetzt (`splitView.list/detail/back`, DE/EN) — kein englisches Literal in der DE-Oberfläche. Touch-Ziele mobiler Primäraktionen müssen mindestens 44 px betragen.

Quellen/Back-links: `docs/superpowers/specs/2026-11-16-mobile-pwa-design.md`, `docs/plans/mobile-baseline-2026-11.md`, `docs/features/mobile-and-pwa.md`.

## Akzeptanzkriterien

- [ ] Unter `--bp-md` wird auf einer Liste/Detail-Route ausschließlich entweder die Liste oder das Detail gerendert.
- [ ] Zeilenauswahl öffnet das Detail; `splitview-back` führt zur Liste zurück und fokussiert die zuletzt gewählte Zeile.
- [ ] Die Liste bleibt während der Detailansicht gemountet und behält ihre Scroll-Position.
- [ ] Mobile und „welche Seite" sind getrennte Zustände; ein Telefon rendert nicht den zweispaltigen Desktop-Zweig.
- [ ] Die Schlüssel `splitView.list`, `splitView.detail` und `splitView.back` sind in DE und EN übersetzt.
- [ ] Touch-Ziele mobiler Primäraktionen messen ≥ 44 px (Nachweis auf gerendertem 390px-Viewport steht aus).
