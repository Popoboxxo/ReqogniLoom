# Tabellenansicht und Massenbearbeitung — Design

> **Stand 2026-11-04:** Fakten gegen `main` (814cb998) korrigiert, Bulk-Update-Vertrag ersetzt
> (Abschnitt 3.1; Verbraucher: [Dokumentensicht neu](2026-11-04-dokumentensicht-neu-design.md)).
> Entscheidungen der Spec sind unverändert. Umsetzungsplan:
> [`../plans/2026-11-04-tabellenansicht-neu.md`](../plans/2026-11-04-tabellenansicht-neu.md)
> (ersetzt `../plans/2026-09-03-tabellenansicht.md`). Neu in diesem Stand: Schreibzugriff läuft
> über eine Layer-2-Funktion (`update_artifact_fields`, Abschnitt 3.1), die Filter-Sprache ist eine
> reine Python-API (Abschnitt 4.1), die Umsetzung ist in fünf Scheiben geschnitten (Plan).

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
(`SavedView`/`UserTableViewState`, siehe Abschnitt 4; ein früher skizziertes
`UserTableViewPreference` hat es im Code nie gegeben, vorhanden ist nur
`UserWorkspacePreference` mit `optional_artifact_visibility`).

## 1. Problem

Alles ist Split-View mit Liste links, Formular rechts. Keine Grid-Ansicht, kein
Bulk-Edit-Endpoint, keine Spaltenauswahl, kein Inline-Edit. Filterung ist handgestrickt:
`django_filters` ist nicht im Einsatz; die Listen lesen ihre Filter über rund 190 manuelle
`query_params.get(...)`-Aufrufe in `rest_api/*views.py` (C8). Teilweise gemildert:
`@list_schema(...)` deklariert Parameter im OpenAPI-Schema und
`reject_unknown_query_params` (`rest_api/query_params.py`) weist unbekannte Parameter ab; die
Requirement-Liste kennt `?allocated=` und `?level=`. Die Filter bleiben je Endpunkt
handgeschrieben, ohne gemeinsame, typ-bewusste Sprache. Ein Systems Engineer mit 400 Requirements und ein Agent, der
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

`PATCH artifacts/bulk-update/` — Body:

```json
{"mode": "atomic" | "partial",
 "items": [{"artifact_id": "<uuid>", "expected_version": 3, "fields": {"title": "..."}}]}
```

- `artifact_id` ist die ID des tragenden `Artifact` (`pl_artifact`), nicht die des Fachobjekts
  (Requirement, ArchitectureElement, ... haben eigene UUIDs). Die Tabellenzeile liefert beide
  (`artifact_id`, `id`) und die `version` des Fachobjekts; diese ist `expected_version`.
- Höchstens **100** Einträge je Anfrage (101 → 400).
- `expected_version` je Eintrag (optimistisches Sperren). Abweichung → Fehlereintrag der
  Klasse 409 (`CONFLICT`) für diesen Eintrag.
- **`mode: "atomic"` (Vorgabe, Vorschlag des Plans):** eine Transaktion, alles oder nichts.
  Ist ein Eintrag ungültig, wird nichts geschrieben; die Antwort listet jeden fehlerhaften
  Eintrag mit Code und Grund.
- **`mode: "partial"`:** gültige Einträge werden geschrieben, Fehler gemeldet:
  `{updated: [...], failed: [{artifact_id, code, reason}]}`.
- **Harte Ablehnung** (400 für die **ganze** Anfrage, in beiden Modi, nichts geschrieben) für
  jedes Feld, das der Workflow oder das System besitzt (`editable` ∈ `"workflow"`, `"system"`,
  `"automation"` oder `false`) — die zentrale Leitplanke aus Abschnitt 2, technisch erzwungen —
  und ebenso für `parent_id`, `uid` und `sort_key` (nie bulk-schreibbar: Struktur und Identität).
- **Workspace:** der Body enthält kein `workspace_id`; der Workspace wird aus den
  `artifact_id`s abgeleitet, alle Einträge müssen zu **einem** Workspace gehören (sonst 400 mit
  dem ersten fremden Eintrag). Rollenprüfung und MCP-Scoping nutzen den abgeleiteten Workspace.
- **`change_reason`** ist ein optionales Feld der Anfrage (nicht je Eintrag); es ist Pflicht, wenn
  das Preset es verlangt (Extended). Der Dokumentensicht-Client muss es dann senden.
- **Atomar ohne Nebenwirkung:** im atomaren Modus entsteht beim Rollback keine Nebenwirkung
  (Embedding-Auffrischung läuft erst nach dem Commit).
- **Sperre (Freeze):** ist der Zustand eines Artefakts über `freeze_on_enter` gesperrt, lautet
  der Fehler 409 `CONFLICT` mit dem Zustandsnamen als Grund. Der Mechanismus existiert für
  Requirement und ArchitectureElement erst mit #1670 P4; bis dahin gilt die Regel nur für
  `Document` (nicht Teil der Tabelle).

**Gleicher Dienst wie das Einzel-Update:** jeder Eintrag läuft durch die neue Layer-2-Funktion
`update_artifact_fields(ctx, item_type, artifact_id, fields, expected_version, *, change_reason=None)`. Sie setzt
zusammen, was der Einzel-PATCH heute in Layer 3 verteilt (Workflow-Leitplanke,
`ArtifactAttributeGateway.validate`/`validate_actor_system_fields`, `update_X(...,
expected_version=)`, `ArtifactAttributeGateway.write` für `owner`/`reporter`/`priority`/
Extended-Werte) und prüft zusätzlich das Schreibrecht je Artefakt (`ItemPermission`: Regel
`read` → verboten, `none` → wie nicht vorhanden). Jeder erfolgreiche Schreibvorgang erhöht die
`version` des Fachobjekts. Je Typ gibt es eine ausdrückliche Liste schreibbarer Felder (keine
Signatur-Introspektion); `editable_fields(ctx, item_type, artifact_id)` liefert sie als reine
Lesefunktion (Verbraucher: Dokumentensicht). Der Einzel-PATCH bleibt unverändert; ein Regressionstest belegt
gleiches Ergebnis.

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
| `reference`, `user`, `actor` | `in` (mehrere Referenzen) |
| `criteria-list`, `widget` | nicht filterbar (nur anzeigbar) |
| `editable: "workflow"` (Status) | `in` (mehrere Zielzustände) — **nur lesend**, Filtern ist kein Schreiben, verletzt die Leitplanke aus Abschnitt 2 nicht |

**Python-API:** die Sprache ist eine reine Funktionsschicht ohne HTTP
(`application/table_filter_dsl.py`), damit auch serverseitige Verbraucher (Kapitelfilter der
Dokumentensicht) sie nutzen. Je Feld gilt eine **Liste von Constraints**, UND-verknüpft (ein
einzelnes Objekt ist die Kurzform); so lässt sich ein Zeitraum (`gte` und `lte`) ausdrücken.
Rechte: filter- und sortierbar sind die sichtbaren Felder der Attribut-Definition (eine
rollenabhängige Feldausblendung gibt es im System nicht); die Zeilen unterliegen dem Leserecht
der Rolle und den Artefaktrechten (`ItemPermission`: eine artefaktbezogene Regel schlägt die
workspaceweite; `none` blendet aus). Sortierung: nur echte Spalten; der symbolische Schlüssel
`"tree"` (Baumreihenfolge `sort_key`, #1670 P1) ist für Verbraucher wie die Dokumentensicht
vorgesehen. Zwei Pseudo-Felder für Requirements,
`allocated` (boolean, `eq`) und `level` (Zahl, `eq`), rufen dieselbe Implementierung wie
`?allocated=`/`?level=` der Requirement-Liste auf (eine Implementierung, nicht zwei).

**REST:** `GET artifacts/table/?workspace_id=&item_type=Requirement&filters=<JSON>&sort=<JSON>` —
`filters` ist ein JSON-Objekt `{"field_name": {"op": "...", "value": ...}}` oder je Feld eine
Liste solcher Objekte, serverseitig gegen die Attribut-Definition validiert (unbekanntes Feld
oder unerlaubter Operator → 400 mit Klartext-Fehler). Der Pfad `artifacts/` selbst bleibt
unverändert (`ArtifactViewSet.list` liefert Baum-Zusammenfassungen). Ersetzt keine der
bestehenden Listen-Endpunkte, ist aber die einzige Quelle für die Tabellenansicht — Migration
der Altstellen ist eine eigenständige Aufräumarbeit außerhalb dieser Spec. Extended-Attribute
(`kind: "extended"`, liegen in `Artifact.custom_fields`) sind in der ersten Umsetzung weder
filter- noch sortierbar.

**Mehrfach-Sortierung:** `sort=<JSON>` — `[{"field": "priority", "dir": "desc"},
{"field": "title", "dir": "asc"}]`.

### 4.2 Gemerkter Zustand vs. gespeicherte Ansicht — zwei unterschiedliche Bedürfnisse

**`UserTableViewState`** (unbenannt, automatisch, ein Datensatz pro
User+Workspace+Typ, überschreibt sich laufend):
```python
class UserTableViewState(TenantScopedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    item_type = models.CharField(max_length=128)
    columns = models.JSONField(default=list)   # [{"field": "...", "order": int}]
    filters = models.JSONField(default=dict)
    sort = models.JSONField(default=list)
    # created_at / modified_at / version kommen von TenantScopedModel
    # unique(user, workspace, item_type)
```
Kein expliziter Speichern-Klick nötig — "wo ich zuletzt war" ist immer da, wenn die
Tabellenansicht neu geöffnet wird.

**`SavedView`** (benannt, explizites Speichern, optional geteilt):
```python
class SavedView(TenantScopedModel):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    item_type = models.CharField(max_length=128)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    columns = models.JSONField(default=list)
    filters = models.JSONField(default=dict)
    sort = models.JSONField(default=list)
    visibility = models.CharField(max_length=16, choices=[("private", "Private"), ("workspace", "Workspace")], default="private")
    # unique(workspace, item_type, owner, name); created_at / modified_at / version von TenantScopedModel
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
- Die Feldbibliothek von `ArtifactForm` umfasst auch `NumberField`, `CriteriaList`,
  `ActorPicker`/`ActorDisplay`; neue Typen (`actor`, `criteria-list`) sind in der
  Spalten- und Operator-Zuordnung bewusst entschieden (Abschnitt 4.1).
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
