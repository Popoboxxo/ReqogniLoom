# Attribut-Definition als Systemobjekt — Design

**Status:** Draft, pending user review
**Quelle:** `docs/SYSTEMAUDIT_2026-09-02_GROB.md`, Kap. N (Feature-Review Artefakt-Formulare),
Kap. Q1.2 (Priorität 2 von 10 im Gesamtaudit), Kap. D3.1/D3.5.
**Scope:** Spec 1 einer Reihe unabhängiger Folge-Specs aus demselben Audit. Nicht Teil
dieser Spec (bewusst ausgelagert, siehe Abschnitt 8): rollenbasierte Sichten
(Leser/Autor/Experte, Kap. T2/T3, inkl. eines möglichen `audience`-Felds), die tiefere
Neugestaltung der Interview-Elizitation über das reine Protokoll-Ableiten hinaus, und
Datenmodell-Konsolidierung (drei Status-Achsen, vier Artefakt-Orte — Kap. B1/B2/B6).

## 1. Problem

Sieben Artefakt-Formulare (Requirement, Need, Adr, Risk, Issue, TestCase, Architecture)
sind unabhängig handgeschrieben — unterschiedliche Struktur, Anlege-Flow, Lösch-Verhalten,
Status-Darstellung, Dirty-Tracking (Audit Kap. N1, Tabelle). Vier halbfertige Mechanismen
berühren je einen Aspekt, keiner deckt alle Typen ab:

- `AttributeVisibilityConfig` — nur `entity_type=Requirement` befüllt, wird aber nur von
  `NeedForm` konsumiert. Requirement ignoriert seine eigene Konfiguration.
- `CustomFieldDefinition` — kennt `text`/`number`/`dropdown`; Frontend-Renderer kennt
  `string`/`number`/`boolean`; `dropdown` wird nicht gerendert, `boolean` existiert im
  Backend nicht.
- Preset-`mandatory_fields` — nur für Requirement, nur `("title",)`.
- Terminologie-Profile — mappen nur Entitätsnamen, nie Attribute.

Ursache: Es gibt kein Attribut-*Definitions*-Objekt. Jedes Formular ist seine eigene
Definition.

## 2. Ziel

Ein Systemobjekt `AttributeDefinition` pro `(item_type, preset)`, global mit
Workspace-Override — exakt das Vererbungsmuster, das für Workflows bereits existiert
(`GlobalWorkflowDefinition` → `WorkflowEngineDefinition`). Ein generischer Formular-Renderer
ersetzt alle sieben Formulare. Vier Konsumenten lesen dieselbe Quelle: Formulare,
Interview-Protokoll, Export (ReqIF/CSV/Bundle), Serializer-Validierung.

## 3. Datenmodell

Neue Django-App `backend/attribute_definitions/` (Layer 1, analog `backend/workflow/`) —
bewusst nicht länger in `persistence`/`application` verstreut, weil dieselbe
Global→Workspace-Vererbung wie bei Workflows gebraucht wird und die App eigene
REST-Views, MCP-Tools und einen Store analog `global_definition_store.py` bekommt.

```python
class GlobalAttributeDefinition(TenantScopedModel):
    item_type = models.CharField(max_length=128)
    preset = models.CharField(max_length=32)          # minimal | standard | extended
    definition_json = models.JSONField(default=dict)   # {"attributes": [...]}
    version = models.IntegerField(default=1)

    class Meta:
        constraints = [UniqueConstraint(fields=["tenant", "item_type", "preset"], ...)]


class WorkspaceAttributeDefinition(TenantScopedModel):
    workspace_id = models.UUIDField(db_index=True)
    item_type = models.CharField(max_length=128)
    preset = models.CharField(max_length=32)           # bei Erstellung eingefroren
    definition_json = models.JSONField(default=dict)    # materialisierte Kopie
    source_global = models.ForeignKey(
        GlobalAttributeDefinition, on_delete=models.SET_NULL, null=True,
        related_name="derived_definitions",
    )
    is_customized = models.BooleanField(default=False)
    version = models.IntegerField(default=1)

    class Meta:
        constraints = [UniqueConstraint(fields=["tenant", "workspace_id", "item_type"], ...)]
```

**Materialized-Copy statt Merge-on-Read** — bewusst dasselbe Muster wie
`WorkflowEngineDefinition`: jede Workspace erhält bei erstem Zugriff eine volle Kopie des
globalen Defaults, kein Runtime-JSON-Diffing auf dem Formular-Lade-Hot-Path. Ein
Admin-Edit am Global propagiert (Application-Layer, nicht Schema) in alle
nicht-customized Workspace-Zeilen derselben `(item_type, preset)`.

### 3.1 Attribut-Schema (`definition_json.attributes[]`)

Ein Eintrag pro Feld, wie im Audit (Kap. N3) skizziert:

```
name            z.B. "verification_method"
kind            core | extended            (core = Django-Modellfeld, extended = custom_fields JSON)
type            text | textarea | number | boolean | enum | multi-enum | date | reference | user
options[]       für enum/multi-enum: {value, label_de, label_en}
required        bool
visible         bool
editable        bool | "workflow"          ("workflow" = nur über Transition änderbar, z. B. status)
section         "general" | "classification" | "change_control" | <frei>
order           int
label           {de, en} — Override, sonst i18n-Key
help_text       {de, en}
default         Wert
validation      {regex | min | max | length}
ai_elicit       bool                        (Interview fragt dieses Feld ab)
export          bool                        (ReqIF/CSV/Bundle)
```

**Sperre für `kind=core`:** Editor-UI und Backend-Write-Pfad lassen für Core-Attribute nur
die Meta-Properties zu (`required`, `visible`, `editable`, `section`, `order`, `label`,
`help_text`, `default`, Untermenge von `options`, `ai_elicit`, `export`). `name`/`type`/die
Existenz eines Core-Attributs sind durchs Django-Modell fixiert — ein `PUT`, der eine
dieser Eigenschaften für ein Core-Attribut ändert, wird mit 400 abgelehnt.

### 3.2 Bootstrap

Ein einmaliges Management-Command introspektiert die 10 Django-Modelle (Requirement,
StakeholderNeed, ArchitectureElement, TestCase, Adr, Risk, Issue, Goal, Icd,
GlossaryTerm: Felder, Choices, `blank=False`) und erzeugt daraus die initialen
`GlobalAttributeDefinition`-Zeilen (nur `kind=core`-Einträge) für jede
`(item_type, preset)`-Kombination. Das ist die "billige Kern-Liste" aus Audit N4 Schritt 1
— läuft einmal als Teil der Migration, nicht live bei jedem Read. Spätere neue
Django-Modellfelder brauchen einen manuellen Nachtrag im Bootstrap-Script (Modellfelder
ändern sich selten, das ist bewusst kein Auto-Sync).

## 4. Migration bestehender Daten

Harte Migration, keine Koexistenz-Phase: eine Daten-Migration liest
`AttributeVisibilityConfig` (→ `visible`/`required` auf den passenden Core-Attributen) und
`CustomFieldDefinition` (→ neue `kind=extended`-Einträge, `field_type` gemappt:
`text`→`text`, `number`→`number`, `dropdown`→`enum`) und schreibt sie in
`GlobalAttributeDefinition`/`WorkspaceAttributeDefinition`. `CustomFieldValue` bleibt
unverändert (Werte, nicht Definition). Nach erfolgreicher Migration werden
`AttributeVisibilityConfig`, `CustomFieldDefinition`, ihre REST-Views/-Serializer und
`application/attribute_visibility_service.py` entfernt (nicht nur deprecated).

## 5. REST- und MCP-API

Muster von `workflow-defaults/` (`backend/rest_api/global_default_views.py`) übernommen:

- `GET/PUT attribute-defaults/{item_type}/{preset}/` — Tenant-Admin, global.
- `GET workspaces/<id>/attribute-definitions/{item_type}/` — resolved (materialisierte
  Kopie), das lesen Formulare, Interview-Protokoll, Export.
- `PUT workspaces/<id>/attribute-definitions/{item_type}/` — setzt `is_customized=True`.
- `POST workspaces/<id>/attribute-definitions/{item_type}/reset/` — zurück auf Global.
- MCP-Gruppe `attribute_definition.*` (`list`, `get`, `update`, `reset`), analog zur
  bestehenden `workflow.*`-Gruppe.

**Serverseitige Validierung:** neuer Shared-Helper
`AttributeDefinitionService.validate_artifact_fields(ctx, item_type, workspace_id,
changed_fields, existing)`, aufgerufen von jedem Create/Update-Serializer:

- `required` wird **nur für Felder geprüft, die im Request tatsächlich gesetzt/geleert
  werden** — ein Save, das ein Pflichtfeld nicht anfasst, wird nicht blockiert, auch wenn
  es vorher schon leer war (Bestandsschutz für Altdaten). Neu-Anlage prüft alle
  `required`-Felder, weil dort jedes Feld "gesetzt" wird.
- `validation` (regex/min/max/length) wird für jedes im Request vorhandene Feld geprüft.
- Unbekannte `extended`-Felder im Payload werden mit 400 abgelehnt (deckt sich mit dem
  API-Hygiene-Fix aus Issue #851 — "unbekannte Felder still verworfen").

## 6. Frontend: ein Renderer statt sieben Formulare

`shared/ArtifactForm/` mit Feld-Komponentenbibliothek: `TextField`, `TextArea`,
`EnumSelect`, `MultiEnum`, `BooleanToggle`, `DateField`, `ReferencePicker`, `UserPicker`.
Der Renderer lädt die resolved Definition für `(workspace, item_type)`, rendert Sektionen
und Felder in `order`, hängt Custom Fields in die Sektion, die die Definition nennt.
`editable: "workflow"` rendert Status-Badge + Transition-Buttons (heute pro Formular
unterschiedlich gebaut, hier einmal). Delete, Dirty-Warnung, Cancel, Create-Modal-Flow
existieren einmal im Renderer statt siebenmal.

### 6.1 Editor-UI

`AttributeEditorPage` unter `/system-settings` (global, Tenant-Admin) und `/settings`
(Workspace-Override, zeigt Abweichungen vom Global) — Shell 1:1 vom Workflow-Editor
übernommen (`EntityTypeSelector`, `PresetSegmentedControl`, `InspectorPanel`), der Canvas
wird durch eine Sektions-/Attribut-Liste mit Drag-Order ersetzt.

### 6.2 Rollout-Reihenfolge der Formular-Migration

Aus Audit N4 übernommen, kleinstes Risiko zuerst: **Risk, Issue** → **ADR, TestCase, Need,
Architecture** → **Requirement zuletzt** (meiste Sonderfälle — Klassifikation,
Change-Control-Sektion, Ableiten/Testfall-generieren/Ähnliche-finden-Aktionen —, Renderer
muss bis dahin alle Fälle abdecken, die die anderen sechs Formulare aufgeworfen haben).
Jedes umgestellte Formular löscht sein handgeschriebenes Pendant, kein Parallelbetrieb.

## 7. Konsumenten

- **Interview-Protokoll:** Pflichtfelder pro Typ kommen aus `ai_elicit=true`-Attributen
  der resolved Definition statt aus YAML-pro-Typ in Prompt-Template-Slots. Phasenreihenfolge
  = `section`-Reihenfolge der Definition. Löst Audit-Befund L2.2 (Default-Protokoll erhebt
  nur Titel+Rationale) als Nebeneffekt. Der Typ-Dispatch in `formalize()` (L2.1) selbst ist
  **nicht** Teil dieser Spec — das ist die separate Interview-Engine-Spec.
- **Export (ReqIF/CSV/Bundle):** Feldliste und Label kommen aus `export=true`-Attributen
  statt aus Hardcode in `requirement_bundle_service.py` (`REQUIREMENT_ALL_FIELDS` entfällt
  zugunsten eines Reads gegen die Definition).
- **Serializer-Validierung:** siehe Abschnitt 5.

## 8. Bewusst nicht in dieser Spec

- **`audience: basic | expert`** (Kap. T3) — gehört fachlich zur rollenbasierten
  Sichten-Spec (Leser/Autor/Experte, Kap. T2), nicht hierher. Das Schema in Abschnitt 3.1
  hat dafür Platz (ein weiteres optionales Property), wird hier aber nicht spezifiziert.
- **Tiefere Interview-Neugestaltung** über das reine Protokoll-Ableiten hinaus (z. B.
  `formalize()`-Typ-Dispatch, Transkript-Deckelung, Provenienz-Anzeige — L2.1, L2.3, L2.4)
  — eigene Spec.
- **Datenmodell-Konsolidierung** (drei Status-Achsen B1, vier Artefakt-Orte B2, zwei
  Versionierungskonzepte B6) — eigene Spec; diese Attribut-Definition baut auf dem
  heutigen Datenmodell auf und ist davon unabhängig lauffähig.

## 9. Preset-Downgrade, Versionierung, Cache

- **Preset-Downgrade:** ein Workspace-Override bleibt beim Preset-Wechsel erhalten, sofern
  die referenzierten Attribute im neuen Preset noch existieren — derselbe
  `validate_downgrade`-Check wie bei Workflow, wiederverwendet, nicht neu erfunden.
- **Versionierung:** `version`-Feld + Audit-Log-Eintrag pro Änderung, wie bei Workflow.
- **Cache-Invalidierung:** pro Workspace, nach demselben Muster wie
  `presets/gate.py:_invalidate_workspace`.

## 10. Risiken

- Die Migration von `AttributeVisibilityConfig`/`CustomFieldDefinition` betrifft
  Produktivdaten (Requirement- und Need-Konfiguration ist heute in Nutzung) — Migration
  braucht einen Dry-Run gegen eine Kopie der Produktionsdaten vor dem Rollout.
- Der Formular-Renderer ersetzt sieben Formulare mit sehr unterschiedlichem
  Funktionsumfang (S6 im Audit listet Sonderfälle wie die Risikomatrix im Risk-Formular,
  drei Markdown-Editoren im ADR-Formular) — nicht jeder Sonderfall ist über
  Feld-Komponenten abbildbar; einzelne Formulare könnten Renderer-Slots für
  Custom-Widgets brauchen, die über die Basis-Feldtypen aus Abschnitt 6 hinausgehen.
