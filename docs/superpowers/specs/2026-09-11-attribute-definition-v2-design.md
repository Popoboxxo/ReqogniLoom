# Attribut-Definition v2 — Anlegen, Layout, Import/Export — Design

**Status:** Draft, pending user review
**Vorgänger:** [Archive/2026-09-03-attribute-definition-design.md](Archive/2026-09-03-attribute-definition-design.md)
(im Folgenden "v1") — implementiert via PR #888, 27 Tasks, archiviert. Diese Spec ändert
nichts an v1s Datenmodell-Grundentscheidung (Global→Workspace, materialized-copy,
core/extended-Unterscheidung) — sie schließt Lücken, die v1 bewusst außerhalb seines
Scopes gelassen hat (v1 §6.1 beschreibt nur Bearbeiten bestehender, bootstrapped
Attribute — kein Anlegen).
**Quelle:** Direktes Nutzer-Feedback nach v1-Rollout (2026-09-11), verifiziert gegen den
tatsächlichen Code (siehe Abschnitt 1).

## 1. Problem (verifiziert gegen den Code)

Sieben konkrete Lücken, jede einzeln gegen den aktuellen Stand geprüft:

1. **Kein Anlegen neuer Attribute.** MCP-Gruppe `attribute_definition.*`
   (`backend/mcp_server/tools/attribute_definition.py`) kennt nur `list`/`get`/`update`/
   `reset`. REST (`backend/rest_api/attribute_definition_views.py`) kennt nur
   `GET`/`PUT` (Gesamtersatz) und `POST .../reset/`. `AttributeEditorPage` (Frontend)
   ist laut eigenem Task-26-Ledger-Eintrag bewusst auf "bearbeiten bereits
   bootstrapped Attribute" begrenzt — kein "Attribut hinzufügen"-Button existiert.
   Einziger echter Erzeugungsweg heute: das Backend-CLI-Kommando
   `bootstrap_attribute_definitions.py`.
2. **Nur Liste, keine Tabelle.** `frontend/src/components/AttributeEditor/
   AttributeList.tsx` rendert über verschachtelte `.map()` (Sektion → Zeile) — kein
   `<table>`, kein CSS-Grid, keine Spalten.
3. **Keine UI für Auswahllisten (`options[]`).** Das Backend-Schema erlaubt
   `options` bereits im Meta-Only-PUT-Whitelist (`schema.py`,
   `CORE_EDITABLE_META_PROPERTIES`), aber `AttributeInspector.tsx`s Feldliste
   (`visible, required, audience, section, label.de/en, ai_elicit, export`) zeigt
   `options` nicht an. Für `enum`/`multi-enum`-Attribute ist die Werteliste dadurch
   praktisch unerreichbar.
4. **Keine Sektions-Sichtbarkeit.** `audience`/`visible` existieren nur pro
   Einzelattribut — eine ganze Sektion ein-/ausblenden (z. B. für ein bestimmtes
   Publikum oder einen Rigor-Preset) geht nicht.
5. **Kein Sektions-Layout.** Sektionen stapeln sich ausschließlich vertikal in voller
   Breite. Kein Grid, keine Nebeneinander-Anordnung.
6. **Kein Export/Import der Definition.** Weder global noch pro Workspace lässt sich
   eine Attribut-Definition als Datei sichern oder in einen anderen Tenant/Workspace
   übertragen — jede Neueinrichtung eines Workspace mit abweichenden Anforderungen
   fängt bei null an (sobald Punkt 1 behoben ist).
7. **Visuelles Design** — allgemein als unattraktiv empfunden; siehe Abschnitt 6 für
   konkrete Maßnahmen statt vager Zustimmung.

Nicht bestätigt, sondern Missverständnis: eine dritte Scoping-Ebene ("Projekt") neben
Global/Workspace existiert im Datenmodell nicht und wird auch in dieser Spec nicht
eingeführt (User-Entscheidung 2026-09-11, s. Abschnitt 2).

## 2. Ziel

Zwei Ebenen bleiben (Global, Workspace) — keine dritte Stufe. Beide Ebenen bekommen
echtes Anlegen. Workspace-Ebene bekommt zusätzlich die Fähigkeit, komplett neue,
workspace-eigene Attribute zu definieren, die es global gar nicht gibt (nicht nur
Meta-Overrides auf geerbten Attributen) — sowohl freihändig als auch, perspektivisch,
aus einem globalen Vorlagen-Katalog (Abschnitt 5, als klar markierte Erweiterung, kein
v1-Blocker für den Rest dieser Spec).

## 3. Anlegen: Datenmodell- und API-Erweiterung

Kein neues Modell nötig — `GlobalAttributeDefinition`/`WorkspaceAttributeDefinition`
(v1 §3) bleiben, `definition_json.attributes[]` ist bereits eine offene Liste. Die
Lücke ist rein API/UI-seitig.

### 3.1 MCP/REST

Neue Operationen, gleiches Muster wie v1 §5:

- `attribute_definition.create(item_type, preset, attribute)` — Global-Scope,
  Tenant-Admin. Validiert `name` gegen Kollision mit bestehenden `core`- UND
  `extended`-Attributen desselben `(item_type, preset)`. `kind` ist bei Neuanlage
  immer `extended` — `kind=core` kann laut v1 §3.1 nur aus dem Django-Modell
  stammen, ein `create`-Aufruf mit `kind=core` wird mit 400 abgelehnt (dieselbe
  Sperre wie beim bestehenden Meta-Only-PUT, jetzt auch hier durchgesetzt).
- `attribute_definition.create_workspace(workspace_id, item_type, attribute)` —
  Workspace-Scope. Erzeugt ein Attribut, das NUR in diesem Workspace existiert
  (`kind=extended`, kein `source_global`-Gegenstück). Setzt implizit
  `is_customized=True` auf der `WorkspaceAttributeDefinition`-Zeile — ein
  workspace-eigenes Attribut divergiert per Definition vom Global-Stand, genau wie
  ein Meta-Edit es heute schon tut (v1 §3, materialized-copy-Propagation).
- `attribute_definition.delete(...)` / `.delete_workspace(...)` — nur für
  `kind=extended`, nie für `kind=core` (unverändert v1-Invariante). Attribute mit
  existierenden `CustomFieldValue`-Einträgen werden nicht hart gelöscht, sondern
  `visible=false` gesetzt plus ein Bestätigungsdialog im Frontend ("N Artefakte
  haben einen Wert für dieses Feld — wirklich löschen?" vs. "nur ausblenden");
  echtes Löschen erst nach expliziter zweiter Bestätigung.
- REST-Äquivalente unter `attribute-defaults/{item_type}/{preset}/attributes/`
  (POST/DELETE) bzw. `workspaces/<id>/attribute-definitions/{item_type}/attributes/`
  (POST/DELETE), analog zum bestehenden `GET`/`PUT` auf der Elternressource.

### 3.2 Validierung

Wiederverwendet `AttributeDefinitionService.validate_artifact_fields` (v1 §5)
unverändert — neu ist nur die Prüfung beim Anlegen selbst: `name` muss
snake_case, eindeutig innerhalb `(item_type, preset)` bzw. `(workspace, item_type)`,
und darf keinen der zehn Django-Modellfeldnamen kollidieren (sonst würde ein
`extended`-Attribut ein `core`-Feld verdecken). `type` muss aus `ATTRIBUTE_TYPES`
(v1 §3.1, 10 Werte) stammen — die UI zeigt diese als Auswahl im Create-Dialog; keine
neuen Typen nötig, nur die bestehenden zehn erstmals sichtbar gemacht (s. Abschnitt 1,
Punkt 1: das "Typen fehlen"-Gefühl ist eine Folge des fehlenden Create-Wegs, nicht
einer echten Typ-Lücke).

## 4. UI: Create-Flow, Tabelle, Auswahllisten, Sektionen

### 4.1 Anlegen

Ein "+ Attribut hinzufügen"-Button pro Sektion (und ein globaler "+ Neue Sektion"
zusätzlich zum bestehenden Sektions-Rename/Delete aus v1 §6.1) öffnet einen Dialog:
Name, Typ (Dropdown aus `ATTRIBUTE_TYPES`), bei `enum`/`multi-enum` sofort die
Options-Liste (Abschnitt 4.3), Pflichtfeld-Toggle, Sektion (vorbelegt mit der
Sektion, aus der der Button geklickt wurde). Auf Workspace-Ebene zusätzlich ein
Hinweis "Dieses Attribut existiert nur in diesem Workspace" (unterscheidet visuell
von geerbten, global definierten Zeilen — s. 4.2).

### 4.2 Tabellen-/Spaltenansicht

`AttributeList.tsx` bekommt einen zweiten Anzeigemodus (Toggle, Zustand in
`localStorage` gemerkt, kein Server-Roundtrip): Spalten `Name | Typ | Sektion |
Pflicht | Sichtbar | Audience | Herkunft (Global/Workspace-eigen)`, sortierbar pro
Spalte, mit denselben Zeilen-Aktionen (bearbeiten, löschen) wie die bestehende
Listenansicht. Beide Ansichten lesen dieselbe resolved Definition — reine
Präsentationsschicht, keine zweite Datenquelle. Umsetzung als eigene Komponente
`AttributeTable.tsx` neben der bestehenden `AttributeList.tsx`, nicht als Umbau
der bestehenden Komponente — vermeidet Regressionsrisiko auf dem bereits
review-geprüften Listen-Code.

### 4.3 Auswahllisten-Editor

Neuer Abschnitt im `AttributeInspector` (v1 §6.1), sichtbar nur bei
`type=enum`/`multi-enum`: Liste von `{value, label_de, label_en}`-Zeilen,
hinzufügen/entfernen/umsortieren (Reihenfolge = Anzeigereihenfolge im
Formular-Select). `value` muss eindeutig innerhalb des Attributs sein.
Entfernen eines Werts, der bereits in existierenden `CustomFieldValue`-Daten
referenziert wird, zeigt eine Warnung (Anzahl betroffener Artefakte) statt
stillem Datenverlust — analog zum Lösch-Fluss aus 3.1.

### 4.4 Sektions-Sichtbarkeit

Neues Sektions-Property (nicht pro Attribut, sondern auf der Sektion selbst —
Sektionen sind heute nur ein String, brauchen eine echte Struktur:
`definition_json.sections[]` als paralleles Array zu `attributes[]`,
`{name, order, visible, layout}` — s. 4.5 für `layout`). Migration: beim ersten
Zugriff auf eine Definition ohne `sections[]` werden die Sektionsnamen aus den
vorhandenen Attributen aggregiert (`sectionNames()`-Logik, v1 bereits vorhanden)
und mit `visible=true`, `layout="full"`, aufsteigender `order` materialisiert —
kein Datenverlust, rein additiv. `visible=false` auf einer Sektion blendet sie
UND alle ihre Attribute im Formular-Renderer (v1 §6) komplett aus, unabhängig von
den einzelnen `visible`-Flags der enthaltenen Attribute — Sektions-Sichtbarkeit ist
eine zusätzliche, übergeordnete Bedingung (UND-Verknüpfung), keine, die
Attribut-`visible` überschreibt oder ersetzt.

### 4.5 Sektions-Grid-Layout

`layout` pro Sektion: `"full"` (heutiges Verhalten, volle Breite) oder `"half"`
(Sektion nimmt eine von zwei Spalten auf einem 2-spaltigen CSS-Grid ein).
Zwei aufeinanderfolgende `"half"`-Sektionen (nach `order`) landen nebeneinander;
eine einzelne `"half"`-Sektion (ungerade Anzahl, oder gefolgt von einer
`"full"`-Sektion) nimmt die linke Spalte, rechte bleibt leer — kein
Auto-Reflow, der die vom Admin gewählte Reihenfolge durcheinanderbringt.
Umsetzung: CSS Grid mit `grid-template-columns: repeat(2, 1fr)` am
`ArtifactForm`-Container (v1 §6), einzelne Sektionen setzen `grid-column: span 2`
(`full`) oder `span 1` (`half`). Kein drittes/N-spaltiges Layout in v1 dieser
Erweiterung — zwei Spalten deckt den geäußerten Bedarf ("nebeneinander statt volle
Breite") ohne die Komplexität eines freien Grid-Editors; mehr Spalten sind eine
spätere, unabhängige Erweiterung, falls der Bedarf real wird.

## 5. Katalog (Erweiterung, nicht Blocker)

Nutzer-Idee: globale Attribut-*Vorlagen*, aus denen ein Workspace wählen kann,
statt jedes eigene Attribut komplett neu zu definieren. Bewusst als eigener,
nachgelagerter Abschnitt markiert — die Abschnitte 3–4 (freies Anlegen auf beiden
Ebenen) sind unabhängig funktionsfähig und liefern den Kernnutzen; der Katalog baut
darauf auf, ist aber kein Freigabe-Blocker.

Grober Umriss (nicht task-reif, für die Implementierungs-Planung noch zu schärfen):
ein `AttributeTemplate`-Objekt (Tenant-weit, unabhängig von `item_type` — z. B. eine
"Priorität (P0-P3)"-Vorlage, die für mehrere Artefakttypen sinnvoll ist), im
Workspace-Create-Dialog (4.1) als zweiter Tab neben "Neu definieren": Vorlage wählen
→ Attribut wird mit den Vorlagenwerten (Typ, Optionen, Label) als workspace-eigenes
`extended`-Attribut instanziiert — danach unabhängig vom Template editierbar (keine
laufende Bindung, keine Sync-Semantik wie bei Global→Workspace-Vererbung — das wäre
ein drittes Vererbungsmuster on top of dem bestehenden und unnötige Komplexität für
das, was der Nutzer beschrieben hat: Startpunkt sparen, nicht laufend synchronisieren).

## 6. Export / Import

Zwei unabhängige Ebenen, gleiches Dateiformat:

- **Global-Export:** `GET attribute-defaults/{item_type}/{preset}/export/` liefert
  ein JSON-Dokument (`definition_json` plus `sections[]`, versioniert mit einem
  `schema_version`-Feld für künftige Formatänderungen) zum Download.
- **Workspace-Export:** analog unter der Workspace-Ressource, exportiert die
  resolved (materialisierte) Definition inkl. aller workspace-eigenen Attribute
  aus Abschnitt 3.1.
- **Import:** `POST .../import/` mit demselben Dateiformat. Validiert gegen
  dieselbe Logik wie Anlegen (3.2) — Namenskollisionen, gültige Typen, gültige
  `options`. Import auf Global-Ebene ersetzt NICHT automatisch bereits abweichende
  (`is_customized=true`) Workspace-Kopien (folgt derselben Propagationsregel wie
  jeder andere Global-Edit, v1 §3) — Import ist "wie ein Edit", kein Sonderpfad.
  Import auf Workspace-Ebene fragt bei Namenskollision mit einem bereits
  vorhandenen (geerbten ODER workspace-eigenen) Attribut nach: überspringen,
  überschreiben, oder mit Suffix umbenennen — keine stille Kollisionsauflösung.
- **Use Case, der das treibt:** ein Tenant mit mehreren ähnlichen, aber nicht
  identischen Workspaces (z. B. mehrere Kundenprojekte mit demselben
  Grund-Attributsatz plus kundenspezifischen Zusatzfeldern) kann eine
  Referenz-Definition einmal bauen, exportieren, und in neue Workspaces
  importieren statt manuell nachzubauen.

## 7. Design (visuell)

"Deutlich attraktiver" konkretisiert statt vager Zustimmung — abgeleitet aus
`docs/UI_KONZEPT.md`s bereits etabliertem Vokabular (Prinzipien: Artefakt sieht
überall gleich aus, Farbe gehört dem Zustand, eine Fläche eine Aufgabe), nicht neu
erfunden:

- Sektionen bekommen sichtbare Karten-Grenzen (Radius-Stufe aus `tokens.css`,
  nicht hart codiert) statt reiner visueller Trennung durch Whitespace — macht das
  neue Grid-Layout (4.5) überhaupt lesbar, sonst verschwimmen zwei nebeneinander
  liegende Sektionen optisch.
- Herkunfts-Kennzeichnung (global geerbt vs. workspace-eigen vs. customized) als
  kleines Badge pro Zeile/Karte, Farbe nach Zustand (nicht Typ) — konsistent mit
  Prinzip 3 des UI-Konzepts, keine neue Farbsemantik erfinden.
- Typ-Icon pro Attribut (Text/Zahl/Datum/Auswahl/...) in Tabellen- UND Listenansicht,
  aus einem bestehenden Icon-Set (kein neues Icon-System einführen).
- Konkrete Umsetzung (genaue Maße, Farben, Zustände) gehört in die
  Implementierungs-Planung, nicht in diese Spec — hier nur die Prinzipien, damit
  die Planung nicht bei null anfängt.

## 8. Migration & Kompatibilität

- Bestehende `definition_json.attributes[]`-Einträge (v1-Bestand) bleiben
  unverändert lesbar — alle neuen Felder (`sections[]`, Katalog-Referenzen) sind
  additiv, kein Breaking Change am bestehenden Schema.
- Die Sektions-Materialisierung (4.4) läuft beim ersten Schreibzugriff nach dieser
  Spec, nicht als separate Datenmigration — vermeidet einen weiteren
  Migrations-Task für reine Lesekompatibilität.
- Bestehende Tests aus v1 (Task 8, 10, 26 laut Archiv-Ledger) bleiben grün — diese
  Spec fügt hinzu, ändert v1s bestehende Lese-/Schreibpfade für schon vorhandene
  Attribute nicht.

## 9. Bewusst nicht in dieser Spec

- **N-spaltiges/freies Grid** (mehr als zwei Sektions-Spalten) — s. 4.5.
- **Laufende Sync-Bindung** zwischen Katalog-Vorlage und instanziiertem Attribut —
  s. 5.
- **Freigabe-/Approval-Workflow für Attribut-Änderungen selbst** (z. B. ein
  Attribut-Edit müsste von einem zweiten Admin bestätigt werden) — nicht geäußert,
  nicht Teil dieser Anforderungen.
