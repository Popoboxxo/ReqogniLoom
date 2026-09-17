# Tabellenansicht und Massenbearbeitung — Design

**Status:** Draft, pending user review
**Quelle:** `docs/SYSTEMAUDIT_2026-09-02_GROB.md`, Kap. Q1.3 ("Ein Systems Engineer mit
400 Requirements arbeitet in Tabellen"), C8 (Filterung handgestrickt), S4
(Live-UI-Vorschlag: Tabellenansicht als zweiter Modus). Neunte von mehreren unabhängigen
Folge-Specs aus demselben Audit — baut auf
[2026-09-03-attribute-definition-design.md](2026-09-03-attribute-definition-design.md)
(Spaltenquelle) und referenziert die Bulk-Accept-Aktion aus
[2026-09-03-menschen-im-system-design.md](2026-09-03-menschen-im-system-design.md).
**Scope:** "Excel-artig" heißt hier reichhaltiges Filtern/Sortieren/Spaltenverwalten plus
speicherbare Ansichten — **nicht** Formeln, Pivot-Tabellen oder Zellen-Drag-Fill. Diese
Spec erweitert und ersetzt teilweise das ursprünglich knapper skizzierte Design
(`UserTableViewPreference` wird durch die hier definierten `SavedView`/
`UserTableViewState` ersetzt, siehe Abschnitt 4).

## 1. Problem

Alles ist Split-View mit Liste links, Formular rechts. Keine Grid-Ansicht, kein
Bulk-Edit-Endpoint, keine Spaltenauswahl, kein Inline-Edit. Filterung ist handgestrickt:
10 `ordering_fields`/`search_fields`/`filterset_fields` gegen 86 manuelle
`query_params.get(...)`-Aufrufe in `views.py` (C8) — Filter-Parameter tauchen dadurch
nicht im OpenAPI-Schema auf. Ein Systems Engineer mit 400 Requirements und ein Agent, der
40 Requirements gebündelt bearbeiten soll, haben dasselbe unbediente Bedürfnis.

## 2. Ziel — unter Wahrung aller Workflow-Regeln

**Zentrale Leitplanke, wörtlich vom Nutzer verlangt:** egal wie "Excel-artig" die
Oberfläche wirkt — Felder mit `editable: "workflow"` (allen voran Status) sind über
Tabellen-Zellen, Inline-Edit oder Bulk-Update **niemals direkt schreibbar**, nur über eine
echte Workflow-Transition mit ihren `allowed_roles`/`signature_gate`-Regeln. Diese Grenze
gilt für jede Schreiboperation dieser Spec, nicht nur für eine.

1. Bulk-Update und Bulk-Transition als generische, adapter-basierte Endpoints.
2. Tabellenansicht mit typ-bewusstem Spalten-Rendering aus der Attribut-Definition.
3. Reichhaltiges, spaltenweises Filtern + Mehrfach-Sortierung — datengetrieben aus
   derselben Attribut-Definition, löst C8 (Filter nicht im Schema) strukturell mit.
4. Speicherbare Ansichten (benannt, privat oder Workspace-geteilt) plus automatisch
   gemerkter letzter Zustand.

## 3. Bulk-Update und Bulk-Transition

### 3.1 Bulk-Update

`PATCH artifacts/bulk-update/` — `{item_type, ids[], fields: {...}}`. Neue
`ARTIFACT_UPDATE_ADAPTERS`-Registry (gleiches Muster wie `ARTIFACT_CREATION_ADAPTERS` aus
der Interview-Engine-Fix-Spec), dispatcht pro Artefakt an den bestehenden
`update_X()`-Service, validiert über `AttributeDefinitionService.validate_artifact_fields`
(Attribut-Definition-Spec, Abschnitt 5). **Harte Ablehnung** (400, kein Teilerfolg für
diesen einen Fall) für jedes Feld mit `editable: "workflow"` im `fields`-Payload — das ist
die zentrale Leitplanke aus Abschnitt 2, technisch erzwungen, nicht nur dokumentiert.

**Partial-Success sonst:** Antwort `{updated: [...], failed: [{id, error}]}` — ein
fehlerhaftes Item (z. B. Validierungsfehler nur bei einem von 40) bricht nicht den ganzen
Batch ab.

### 3.2 Bulk-Transition

`POST artifacts/bulk-transition/` — `{item_type, ids[], to_state, change_reason}`. Pro
Artefakt ein normaler Transition-Aufruf über die bestehende Workflow-Engine, mit voller
`allowed_roles`/`signature_gate`-Prüfung je Item, partial-success. Der "Ausgewählte
bestätigen"-Bulk-Accept aus der Menschen-im-System-Spec (`proposed → draft`) ist ab jetzt
eine Anwendung dieses generischen Mechanismus.

### 3.3 MCP

`artifact.bulk_update`, `artifact.bulk_transition` — dieselbe Backend-Logik, deckt den im
Audit genannten Agenten-Fall ("40 Requirements einen Status setzen").

## 4. Filtern, Sortieren, Spalten — datengetrieben aus der Attribut-Definition

### 4.1 Filter-DSL, typ-bewusst

Jedes Feld aus der aufgelösten Attribut-Definition bekommt einen festen, vom `type`
abgeleiteten Operator-Satz — dieselbe Typinformation, die schon `ArtifactForm` für das
Rendering nutzt:

| Feldtyp | Operatoren |
|---|---|
| `text`, `textarea` | `contains` |
| `enum`, `multi-enum` | `in` (mehrere Werte, ODER-verknüpft) |
| `number` | `gte`, `lte` |
| `date` | `gte`, `lte` (Zeitraum) |
| `boolean` | `eq` (all/true/false) |
| `reference`, `user` | `in` (mehrere Referenzen) |
| `editable: "workflow"` (Status) | `in` (mehrere Zielzustände) — **nur lesend**, Filtern ist kein Schreiben, verletzt die Leitplanke aus Abschnitt 2 nicht |

**REST:** `GET artifacts/?item_type=Requirement&filters=<JSON>` — `filters` ist ein JSON-
Objekt `{"field_name": {"op": "...", "value": ...}}`, serverseitig gegen die
Attribut-Definition validiert (unbekanntes Feld oder unerlaubter Operator → 400 mit
Klartext-Fehler, nicht stilles Ignorieren wie die heutigen 86 `query_params.get()`-Stellen
laut C8). Ersetzt keine der 10 bestehenden `filterset_fields`-Endpoints, ist aber die
neue, einzige Quelle für die Tabellenansicht — Migration der 86 Altstellen ist eine
verwandte, aber eigenständige Aufräumarbeit außerhalb dieser Spec.

**Mehrfach-Sortierung:** `sort=<JSON>` — `[{"field": "priority", "dir": "desc"},
{"field": "title", "dir": "asc"}]`.

### 4.2 Gemerkter Zustand vs. gespeicherte Ansicht — zwei unterschiedliche Bedürfnisse

**`UserTableViewState`** (unbenannt, automatisch, ein Datensatz pro
User+Workspace+Typ, überschreibt sich laufend):
```python
class UserTableViewState(TenantScopedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    workspace_id = models.UUIDField(db_index=True)
    item_type = models.CharField(max_length=128)
    columns = models.JSONField(default=list)   # [{"field": "...", "order": int}]
    filters = models.JSONField(default=dict)
    sort = models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True)
    # unique(user, workspace_id, item_type)
```
Kein expliziter Speichern-Klick nötig — "wo ich zuletzt war" ist immer da, wenn die
Tabellenansicht neu geöffnet wird.

**`SavedView`** (benannt, explizites Speichern, optional geteilt):
```python
class SavedView(TenantScopedModel):
    workspace_id = models.UUIDField(db_index=True)
    item_type = models.CharField(max_length=128)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    columns = models.JSONField(default=list)
    filters = models.JSONField(default=dict)
    sort = models.JSONField(default=list)
    visibility = models.CharField(max_length=16, choices=[("private", "Private"), ("workspace", "Workspace")], default="private")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```
`visibility="workspace"` macht die Ansicht für alle Workspace-Mitglieder sichtbar
(read-only für Nicht-Owner — bearbeiten/löschen nur Owner oder Admin), z. B. "Offene
kritische Risiken" als Team-weit geteilte, wiederverwendbare Ansicht.

**REST:** `GET/POST/PATCH/DELETE saved-views/` (Workspace- und Typ-gefiltert),
`GET saved-views/<id>/apply/` liefert direkt die gefilterte/sortierte Artefaktliste.
**MCP:** `saved_view.list`, `saved_view.apply` — ein Agent kann eine benannte Ansicht
laden statt Filter-JSON von Hand zu bauen.

### 4.3 Frontend

- Toggle Liste/Tabelle auf jeder Listen-Seite, ergänzt `ListToolbar`.
- Spalten-Header: Klick öffnet typ-passenden Filter (Enum → Multi-Select-Dropdown, Datum
  → Range-Picker, Text → Suchfeld, ...) — dieselbe Feld-Komponentenbibliothek wie
  `ArtifactForm` (Attribut-Definition-Spec, Abschnitt 6), kein zweites UI-System.
  Aktive Filter als Chips über der Tabelle, einzeln entfernbar.
  Spalten-Header-Klick (ohne Filter-Icon) sortiert; Shift-Klick fügt Sekundär-Sortierung
  hinzu.
- Spaltenauswahl über ein Zahnrad-Menü (welche Attribute als Spalten, Reihenfolge per
  Drag) — schreibt in `UserTableViewState`.
- "Ansicht speichern"-Button neben dem Zahnrad öffnet Dialog (Name, privat/Workspace) —
  schreibt `SavedView`. Gespeicherte Ansichten als Dropdown/Tab-Leiste über der Tabelle.
- **Inline-Edit:** Klick auf eine Zelle eines nicht-`editable:"workflow"`-Feldes → dieselbe
  Feldkomponente im Edit-Modus, Speichern ruft den normalen Einzel-Update-Pfad (nicht den
  Bulk-Endpoint aus Abschnitt 3). Status-Zellen zeigen den Badge read-only mit einem
  separaten "Status ändern"-Aktions-Icon, das den Transition-Dialog öffnet — visuell klar
  getrennt von den editierbaren Zellen, damit die Leitplanke aus Abschnitt 2 auch optisch
  sichtbar ist, nicht nur serverseitig erzwungen.
- Checkbox-Zeilenauswahl → Toolbar-Aktionen "Felder bearbeiten" (Bulk-Update-Dialog,
  Abschnitt 3.1) und "Status ändern" (Bulk-Transition, Abschnitt 3.2, zeigt nur vom
  aktuellen Zustand aus erreichbare Zielzustände).
- Spalten-Resize/-Reorder per Drag, erste Spalte optional fixiert (Scroll-Verhalten) —
  reine Frontend-Interaktionsdetails, hier nicht weiter spezifiziert.

**Bewusst nicht Teil dieser Spec:** Formeln, Pivot-Tabellen, Zellen-Drag-Fill,
Gruppierung (Group-by wäre eine reine Client-seitige Sicht auf dieselben gefilterten
Daten und ist eine günstige spätere Ergänzung auf derselben Infrastruktur, aber nicht
jetzt gefordert).

## 5. Migration

Additiv, keine Bestandsdaten betroffen:

1. `UserTableViewState`, `SavedView` als neue Tabellen.
2. `ARTIFACT_UPDATE_ADAPTERS`-Registry (analog zur bestehenden
   `ARTIFACT_CREATION_ADAPTERS`).
3. `artifacts/bulk-update/`, `artifacts/bulk-transition/`, `artifacts/`-Filter-Endpoint,
   `saved-views/*` als neue REST-Routen.
4. MCP-Tools `artifact.bulk_update`, `artifact.bulk_transition`, `saved_view.list`,
   `saved_view.apply`.

## 6. Risiken

- **Filter-DSL-Komplexität wächst mit jedem neuen Feldtyp** aus der Attribut-Definition —
  ein neuer `type`-Wert dort (z. B. ein künftiger `widget`-Typ aus der
  Attribut-Definition-Spec, Abschnitt 6.3) braucht einen bewussten Entscheid, welche
  Filter-Operatoren dafür Sinn ergeben, sonst ist die Spalte in der Tabelle nur anzeigbar,
  nicht filterbar.
- **Partial-Success-Antworten** (Abschnitt 3) brauchen sorgfältige Frontend-Behandlung —
  "38 von 40 aktualisiert, 2 fehlgeschlagen" muss im UI klar sichtbar sein, nicht als
  stiller Teilerfolg durchgehen.
- **`SavedView` mit `visibility="workspace"`** kann veralten (Filter auf einen inzwischen
  gelöschten Wert, z. B. einen entfernten Benutzer als `owner`-Filter) — kein
  automatisches Aufräumen in dieser Spec vorgesehen, eine kaputte gespeicherte Ansicht
  liefert im Zweifel eine leere Liste statt eines Fehlers (fail-soft).
- **Migration der 86 bestehenden `query_params.get()`-Filterstellen (C8)** ist explizit
  nicht Teil dieser Spec — die neue Filter-API existiert parallel, bis jemand die
  Altstellen bewusst umstellt. Kein struktureller Zwang dazu, nur eine offene
  Aufräum-Gelegenheit.
