# Verbindungsansicht „Bäume"

Kurzreferenz für Anwender und Integratoren (Spec
`docs/superpowers/specs/2026-11-08-navigationsbaum-und-verbindungsansicht-design.md`,
Schnitte V.1–V.5).

## Was der Modus zeigt

`/connections` stellt zwei Hierarchien nebeneinander dar:

- links den **Requirements-Baum** (Eltern/Kind aus `parent_id`, Geschwister in
  `sort_key`-Reihenfolge, Zeilen ohne Schlüssel zuletzt),
- rechts den **Architektur-Baum** (dieselbe Baumkonstruktion über die
  Architekturelemente).

Beide Spalten teilen sich **einen** Scroll-Container — es gibt keine
Scroll-Synchronisation. Zwischen den Spalten verlaufen die
**Allokationskanten**: genau eine Linie je Allokation (ein Requirement hat
höchstens ein Ziel, N:1). Gezeichnet werden nur die spaltenübergreifenden
Kanten; die Hierarchie selbst bleibt Linien-frei.

Jede Requirement-Zeile nennt ihr Ziel zusätzlich **als Text**: den Elementtitel,
„Nicht allokiert" oder „zugeordnet (außerhalb des Filters)" — Letzteres, wenn das
Ziel von einem aktiven Elementfilter ausgeblendet wird. Die Zuordnung hängt
damit nie allein an einer Linie.

## Kanten, Selektion, Tastatur

- **Kanten-Overlay:** misst nur gemountete Zeilen. Ein zugeklappter Zweig zeichnet
  deshalb keine Kante — das ist gewollt, der Zieltext bleibt sichtbar.
- **Hervorheben:** Klick oder Fokus auf eine Requirement-Zeile betont ihre Kante
  und die zugehörige Element-Zeile; Klick auf eine Element-Zeile betont alle
  Requirements, die darauf zeigen.
- **Auswählen:** Checkbox je Zeile (`alloc-select-<id>`); gesperrte Zeilen sind
  nicht selektierbar, gesperrte Elemente bleiben gültige Ziele. Die
  Aktionsleiste zählt nur sichtbare, nicht gesperrte Zeilen.
- **Zuweisen:** Zeile auf ein Element ziehen, oder per Tastatur: Checkbox →
  „Allokieren auf …" → Suchdialog → Enter. Beides schreibt atomar über
  `POST /api/v1/trace-links/bulk/`; ein Fehler schreibt nichts.
- **Lösen:** die Entfernen-Aktion der Zeile (`alloc-deallocate-<id>`).
- **Auf-/Zuklappen:** echter `<button aria-expanded aria-controls>` je Zweig
  (Disclosure-Muster, kein `tree`-Widget).

## Default und URL-Alias

- **Ohne `view`-Parameter** öffnet die Route `Bäume` (Entscheidung D4/O5 =
  Option a vom 2026-11-15).
- Die Umschaltleiste hat fünf Einträge: `Bäume` · `Architektur` · `Zwei Spalten`
  · `Matrix` · `Graph`.
- `setView("trees")` schreibt **keinen** `view`-Parameter; jeder andere Modus
  schreibt seinen Namen (`?view=architecture`, `?view=two-column`,
  `?view=matrix`, `?view=graph`).
- **Alias:** `?view=tree` (der Name bis V.5) öffnet `Architektur`. Der Alias
  bleibt dauerhaft gültig, damit gespeicherte Sichten und Lesezeichen
  unverändert funktionieren.
- Filter bleiben beim Moduswechsel erhalten — sie liegen ausschließlich in der
  URL.

## Präferenzen (Nutzer-Ebene)

| Schlüssel | Wirkung | Default |
|---|---|---|
| `ui.connection_view.show_edges` | Kanten-Overlay an/aus. Schaltet **nur** das Overlay ab, nie die Zieltexte. | `true` |
| `ui.connection_view.filters_expanded` | „Weitere Filter" aufgeklappt | `false` |
| `ui.connection_view.saved_views` | gespeicherte Sichten (URL-Snapshots) | `[]` |

Alle drei sind im Backend registriert (`application/preference_registry.py`).
Ein fehlgeschlagenes **Laden** fällt auf den Default zurück, ein
fehlgeschlagenes **Schreiben** meldet einen Fehler und lässt den lokalen Zustand
stehen.

## Grenzen

- Keine Virtualisierung in beiden Bäumen: die Zeilenzahl ist durch den
  Server-Deckel (`page_size=500` je Zeilenart) begrenzt — bewusste Entscheidung.
- Kanten für Zeilen außerhalb des sichtbaren Bereichs (zugeklappt oder aus dem
  Client-Fenster gescrollt) fehlen folgenlos.
- Ein Requirement hat höchstens eine Kante; Mehrfachallokation ist nicht Teil
  dieses Modus.
- Die Ansicht ist eine Lesehilfe: sie schreibt nur über die bestehenden
  Allokations-Endpunkte, nie über eigene Pfade.
