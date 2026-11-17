# Feature-Referenzen

> **Zweck:** Einstieg in die anwender- und integratorennahen Kurzreferenzen unter
> `docs/features/`. Jede Seite beschreibt eine Funktion so, wie sie im Code
> dieses Repository-Stands existiert — inklusive Grenzen.
> **Stand:** `1.9.0-beta.2` · **Letzte Aktualisierung:** 2026-11-17
> **Abgrenzung:** Interne Architektur-Notizen stehen in
> [`../ARCHITECTURE.md`](../ARCHITECTURE.md), das Dateiinventar in
> [`../CODEBASE_OVERVIEW.md`](../CODEBASE_OVERVIEW.md); Entwürfe und
> Entscheidungsnachweise liegen unter `docs/superpowers/specs/` bzw.
> `docs/se/ADR/`. Feature-Seiten sind keine Spezifikationen.

| Seite | Ein Satz |
|---|---|
| [Bearbeitbare Dokumentansicht](document-reading-view.md) | Was `/documents/:id` aus dem Markdown-`body` eines `Document` macht: nummerierte Kapitel mit Inhaltsverzeichnis, wer welches Feld schreiben darf, sofortiges und gesammeltes Speichern, Konflikt-Antworten und der Markdown-Export. |
| [Verbindungsansicht „Bäume"](connection-view-trees.md) | Der Default-Modus von `/connections`: Requirements-Baum und Architektur-Baum nebeneinander, genau eine Allokationskante je Requirement, Kantenschalter, Selektion und Tastaturbedienung. |
| [Ordnung und Allokation](ordering-and-allocation.md) | Wie `sort_key`, Verschieben, die N:1-Allokation, die Stufen-Leiter, Workflow-Sperren und Gruppen das Modell ordnen — inklusive der Präferenzen, die Sichten und Kartenfelder speichern. |
| [Mobil und installierbare PWA](mobile-and-pwa.md) | Was die App auf 360–430 px bedienbar und auf Android installierbar macht: Manifest/Icons/Service-Worker (nur App-Hülle), Offline-/Update-Banner, Drawer und Liste → Detail — inklusive der ehrlich ausgewiesenen Reste (Touch-Pan/Zoom, Filter-Sheet, iOS nur Emulation, keine gerenderten Nachweise). |
