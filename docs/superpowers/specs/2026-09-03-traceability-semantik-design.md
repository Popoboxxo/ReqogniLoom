# Traceability-Semantik — Design

**Status:** Draft, pending user review
**Quelle:** `docs/SYSTEMAUDIT_2026-09-02_GROB.md`, Kap. B4 (Trace-Link-Typen driften),
U1–U3 (Traceability live bewertet, Zielbild 8 Kern-Typen), Q1.6 (Link-Semantik dringend),
Q2.4 (Traceability ist ein Link-Speicher, kein Modell). Dritte von mehreren unabhängigen
Folge-Specs aus demselben Audit — siehe
[2026-09-03-attribute-definition-design.md](2026-09-03-attribute-definition-design.md) und
[2026-09-03-datenmodell-konsolidierung-design.md](2026-09-03-datenmodell-konsolidierung-design.md).
**Scope:** Nicht Teil dieser Spec: Trace-Spine-UI-Vollrollout (A5, eigenes Thema), P0-Bug
"Suspect-Propagation tot" ist bereits als GitHub-Issue #849 gemeldet — diese Spec liefert
den eigentlichen Mechanismus dafür (siehe Abschnitt 5), löst #849 also strukturell mit.

## 1. Problem

`traceability/types.py` definiert `LinkType` heute als hartcodiertes Python-Enum mit 15
Werten, `SE_LINK_SEMANTICS` als statisches Dict mit erlaubten Typ-Paaren — und beides gilt
nur, wenn ein Workspace `se_mode` aktiviert hat, und nur für 5 von 10 Artefakttypen
(`SE_CORE_ARTIFACT_TYPES`). Für alles andere ist die Prüfung explizit "permissive by
design". Das erklärt den live gefundenen Bug U2 exakt: `verifies` von `Risk` nach
`Requirement` wird akzeptiert (Risk ist nicht im Kern-Set, also ungeprüft), von
`StakeholderNeed` nach `Requirement` abgelehnt (StakeholderNeed ist geprüft, aber nicht in
den erlaubten Paaren von `verifies`).

`TraceLink` (`persistence/models.py:1352`) hat nur `source`, `target`, `link_type`,
`embedding` — kein `rationale`, kein Status, kein Marker, welche Änderung eine
Suspect-Markierung ausgelöst hat (Q1.6). Frontend (`types/index.ts:265-278`) pflegt eine
eigene, unabhängige Union von 14 der 15 Typen (`diagram-ref` fehlt) — garantierte Drift
(B4).

Zusätzlich zur reinen Bereinigung: der Nutzer will das Link-Typ-Konzept selbst
**konfigurierbar** statt hartcodiert — Tenants sollen neue Trace-Typen einführen und
bestehende anpassen können, ohne Code zu ändern.

## 2. Ziel

Zwei Ebenen, sauber getrennt:

1. **Ein bereinigtes Semantik-Modell** — von 15 auf 8 Kern-Typen reduziert, jeder Typ
   trägt erlaubte Paare, Coverage-Relevanz, Suspect-Regel, Impact-Gewicht, und die
   Erlaubt-Prüfung gilt **immer**, für alle 10 Artefakttypen, nicht mehr an `se_mode`
   gekoppelt.
2. **Konfigurierbar statt hartcodiert** — der Link-Typ-Katalog wird ein Systemobjekt
   (`GlobalLinkTypeDefinition` → `WorkspaceLinkTypeDefinition`), exakt das
   Vererbungsmuster der Attribut-Definition- und Workflow-Defaults-Specs. Die 8 Typen aus
   (1) sind die mitgelieferte Startbelegung, kein Deckel — Tenants können weitere Typen
   anlegen, bestehende anpassen oder deaktivieren.

## 3. Bereinigtes Semantik-Modell (Startbelegung)

### 3.1 Typenliste

`derives-from`, `decomposes`, `allocated-to`, `verifies`, `decides`, `mitigates` (neu),
`references` (neu, ersetzt `documents`/`traces`/`uses-term`), `diagram-ref`
(Reconciler-only, unverändert). `parent-child` entfällt (siehe 3.3), `copy-of` wird zum
Artifact-Feld `copied_from` statt einem Link.

**Migrations-Mapping (harte Migration, bestehende `TraceLink`-Zeilen):**

| Alt | Neu | Besonderheit |
|---|---|---|
| `parent-child` | entfällt | siehe 3.3 |
| `satisfies` | `allocated-to` | Quelle/Ziel getauscht |
| `implements` | `allocated-to` | Quelle/Ziel getauscht |
| `refines` | `derives-from` | Paare unverändert übernommen |
| `realizes` | `decomposes` | — |
| `documents` | `references` | — |
| `traces` | `references` | — |
| `uses-term` | `references` | — |
| `copy-of` | `Artifact.copied_from` (Feld, kein Link) | siehe Risiken |
| `derives-from`, `verifies`, `allocated-to`, `decides`, `decomposes`, `diagram-ref` | unverändert | — |

### 3.2 Erlaubt-Matrix (Startwerte je Typ, danach editierbare Daten — siehe Abschnitt 4)

| Typ | Erlaubte Paare | Coverage-relevant | Suspect-Regel | Impact-Gewicht |
|---|---|---|---|---|
| `derives-from` | Req↔Req, Req↔Need, Need↔Need, **Arch↔Arch (neu, aus `refines`)** | nein | `target_change_flags_source` | 1.0 |
| `decomposes` | Req↔Req (Ebene n→n+1), Arch↔Arch | nein | `parent_change_flags_children` | 1.0 |
| `allocated-to` | Req→Arch (**nur diese Richtung** — Arch→Arch entfernt, war Dopplung mit `decomposes`) | ja (Allocation-Coverage) | `source_change_flags_target` | 1.0 |
| `verifies` | TestCase→Req, TestCase→Arch | ja (Test-Coverage) | `target_change_flags_source` | 1.0 |
| `decides` | Adr→* | nein | `none` | 0.3 |
| `mitigates` | Risk→Req, Risk→Arch | nein | `none` | 0.5 |
| `references` | *→GlossaryTerm, *→Diagram, *→Icd | nein | `none` | 0.2 |
| `diagram-ref` | Diagram→* (nur Reconciler) | nein | `none` | 0.2 |

Gilt **immer** — die heutige `se_mode`-Gate und die "Typen außerhalb des Kern-Sets sind
unbeschränkt"-Ausnahme entfallen ersatzlos. `TraceLinkService.create_trace_link`
validiert bei jeder manuellen Link-Erstellung gegen den aufgelösten Katalog des
Workspaces (Abschnitt 4).

### 3.3 Hierarchie

`parent-child` entfällt als Link-Typ. `Artifact.parent` (FK, ADR-05) bleibt als
Performance-Cache für rekursive Baum-Queries bestehen (Requirement, ArchitectureElement)
— wird aber ab jetzt **immer** in derselben Transaktion wie der zugehörige
`decomposes`-Link geschrieben, statt wie heute unabhängig von bis zu drei Mechanismen
gepflegt zu werden. Ein Unique-Constraint auf `(source, target, link_type='decomposes')`
verhindert Duplikate.

## 4. Konfigurierbarkeit: Link-Typ-Katalog als Systemobjekt

Neue Django-App `backend/link_types/` (Layer 1, wie `workflow/` und
`attribute_definitions/`):

```python
class GlobalLinkTypeDefinition(TenantScopedModel):
    key = models.CharField(max_length=64)            # "derives-from" oder tenant-eigen
    definition_json = models.JSONField(default=dict)
    version = models.IntegerField(default=1)
    # unique(tenant, key)

class WorkspaceLinkTypeDefinition(TenantScopedModel):
    workspace_id = models.UUIDField(db_index=True)
    key = models.CharField(max_length=64)
    definition_json = models.JSONField(default=dict)   # materialisierte Kopie
    source_global = models.ForeignKey(
        GlobalLinkTypeDefinition, on_delete=models.SET_NULL, null=True,
        related_name="derived_definitions",
    )
    is_customized = models.BooleanField(default=False)
    version = models.IntegerField(default=1)
    # unique(tenant, workspace_id, key)
```

Materialized-Copy-Muster wie bei Workflow/Attribut-Definition: kein Merge-on-Read, ein
Admin-Edit am Global propagiert in alle nicht-customized Workspace-Zeilen. Cache-
Invalidierung nach `presets/gate.py:_invalidate_workspace`-Muster.

**Anders als Workflow/Attribut-Definition:** kein `preset`-Feld — Link-Typen sind kein
`(item_type × preset)`-Raster, sondern ein offener, benannter Katalog. Bootstrap ist daher
keine Modell-Introspektion, sondern eine feste Seed-Migration mit den 8 Typen aus
Abschnitt 3.

`definition_json` pro Typ:
```
label             {de, en}
allowed_pairs[]    [{source_type, target_type}]
coverage_relevant  bool
suspect_rule       "none" | "target_change_flags_source" | "source_change_flags_target"
                   | "parent_change_flags_children"   (siehe Grenze unten)
impact_weight      float
manual_creatable   bool
system_owned       bool        (nur diagram-ref: key/manual_creatable gesperrt,
                                 gleiches Sperr-Konzept wie `locked` in der
                                 Attribut-Definition-Spec)
active             bool, default true   (Soft-Disable statt Hard-Delete)
built_in           bool        (informativ: gehört zur Startbelegung aus 3.1)
```

**Neue Typen einführen:** ein Tenant-Admin legt eine neue `GlobalLinkTypeDefinition`-Zeile
mit frei gewähltem `key` an (z. B. `conflicts-with`), definiert `allowed_pairs`, `label`,
`impact_weight` selbst und wählt `suspect_rule` aus dem festen Wertebereich.

**Grenze — `suspect_rule` ist kein freier Code:** die Werte sind ein kleiner, im Code
verankerter Enum, weil die Propagations-Engine (Abschnitt 5) auf diesen Wert verzweigt.
Ein neuer Typ wählt aus den vier bestehenden Verhalten oder `none` — vollständig neue
Propagationslogik per Konfiguration ist nicht möglich, das wäre ein Code-Änderung. Alles
andere (`allowed_pairs`, `label`, `coverage_relevant`, `impact_weight`, `active`) ist frei.

### 4.1 REST/MCP-API

- `GET/POST/PUT link-type-defaults/{key}/` — Tenant-Admin, global (List, neuer Typ
  anlegen, bestehenden bearbeiten).
- `GET workspaces/<id>/link-type-definitions/` — resolved (materialisierte Kopie), das
  lesen `TraceLinkService`, der Trace-Link-Dialog (FE) und der MCP-Tool-Schema-Validator.
- `PUT workspaces/<id>/link-type-definitions/{key}/` (setzt `is_customized=True`),
  `POST .../reset/`.
- MCP-Gruppe `link_type.*` (`list`, `get`, `create`, `update`, `reset`), analog zu
  `workflow.*`/`attribute_definition.*`.

**MCP-Schema-Konsequenz:** `link_type` in `traceability.create_link`s `inputSchema` wird
ein freier String statt eines festen Enums — eine feste Enum-Liste im
`tools/list`-Manifest wäre sonst pro Tenant unterschiedlich, was das "einmal gebaute
Manifest"-Modell bricht (Audit I.7, MCP-Kontextkosten). Validierung passiert serverseitig
gegen den aufgelösten Katalog; die Fehlermeldung listet die gültigen Werte (gleiche
UX-Verbesserung wie bei anderen Enum-Validierungen im Audit, R3).

**FE-Konsequenz:** `types/index.ts`s hartcodierte 14er-Union entfällt zugunsten eines
Reads gegen `GET workspaces/<id>/link-type-definitions/` — behebt B4 strukturell (keine
zwei unabhängig gepflegten Quellen mehr) statt nur die eine fehlende Zeile nachzutragen.
Der Trace-Link-Dialog (S7) filtert `link_type`-Optionen nach den `allowed_pairs` des
gewählten Quell-/Zieltyps aus derselben Quelle.

### 4.2 Editor-UI

`LinkTypeEditorPage` unter `/system-settings` (global, Tenant-Admin) und `/settings`
(Workspace-Override) — Shell vom Workflow-/Attribut-Editor übernommen
(`EntityTypeSelector`-Äquivalent wird hier eine flache Liste der Typen statt
Typ×Preset-Raster). `system_owned`-Zeilen (`diagram-ref`) werden ausgegraut mit
Schloss-Symbol dargestellt, exakt wie `locked`-Attribute in der Attribut-Definition-Spec.
"Neuer Typ"-Button öffnet ein Formular für `key`/`label`/`allowed_pairs`/`suspect_rule`/
`impact_weight`.

## 5. `TraceLink`-Modellerweiterung und Suspect-Propagation

- `rationale` (TextField, optional) — Q1.6.
- `suspect_flagged_at` (Timestamp, nullable) + `suspect_source_change` (FK auf
  `AuditEntry`, nullable) — von der Propagations-Engine gesetzt, wenn dieser Link eine
  Suspect-Markierung ausgelöst hat.
- **Propagations-Mechanismus:** bei jeder Artefakt-Änderung mit Change-Reason liest der
  Mechanismus alle `TraceLink`-Zeilen, die das geänderte Artefakt als `target`
  (`suspect_rule=target_change_flags_source`), `source`
  (`suspect_rule=source_change_flags_target`) oder Elternteil
  (`suspect_rule=parent_change_flags_children`) berühren, und markiert das jeweils andere
  Ende suspect — dabei werden `suspect_flagged_at`/`suspect_source_change` auf dem Link
  gesetzt. Das ist die fehlende Implementierung hinter dem bereits gemeldeten P0-Bug
  #849 (Suspect-Propagation tot, `suspect` fehlt im Serializer) — diese Spec liefert den
  Mechanismus, #849 wird damit strukturell mitgelöst statt separat geflickt.
- `suspect` selbst bleibt vorerst ein Feld je spezialisierter Tabelle (wie heute bei
  Requirement). Sauberer wäre `suspect` auf `Artifact` selbst, parallel zu
  `lifecycle_status` aus der Datenmodell-Konsolidierung-Spec — das ist eine kleine
  Ergänzung dort, kein Grund, diese Spec aufzublähen oder die bereits committete
  Datenmodell-Spec erneut zu öffnen. Vermerkt als Cross-Spec-Notiz für deren
  Implementierung.

## 6. Migration

Harte Migration, mehrere Schritte:

1. `link_types`-App + Seed-Migration mit den 8 Startypen aus Abschnitt 3.
2. `TraceLink`-Datenmigration nach dem Mapping aus 3.1 — `satisfies`/`implements`-Zeilen
   bekommen Quelle/Ziel getauscht, `copy-of`-Zeilen wandern in `Artifact.copied_from` und
   werden als Links gelöscht, Duplikate zwischen `parent-child` und `decomposes` für
   dasselbe Paar werden dedupliziert statt verdoppelt übernommen.
3. `TraceLink`-Schemaerweiterung um `rationale`, `suspect_flagged_at`,
   `suspect_source_change`.
4. `TraceLinkService.create_trace_link` auf die neue, immer aktive Katalog-Validierung
   umstellen (`SE_LINK_SEMANTICS`/`se_mode`-Gate entfernen).

## 7. Risiken

- **Richtungstausch bei `satisfies`/`implements`→`allocated-to`** verändert Link-Semantik
  rückwirkend. Jeder Konsument, der `link_type` direkt vergleicht statt die
  Katalog-API zu nutzen (Reports, ältere Integrationen), muss vor der Migration
  identifiziert und mit umgestellt werden — sonst bricht er still.
- **`copy-of`→`copied_from`-Migration** braucht eine Vorab-Prüfung auf Mehrfach-Kopien:
  heute als Link theoretisch N Ziele möglich, als Feld nur 1:1. Ein Artefakt mit mehr als
  einem `copy-of`-Link ist ein Datenkonflikt, der vor der Migration aufgelöst werden muss
  (z. B. neuesten Link gewinnt, Rest wird als `references`-Link erhalten).
- **MCP-Schema-Änderung (Enum → freier String für `link_type`)** verringert
  Client-seitige Autocomplete-/Typsicherheit gegenüber heute — ein bewusster Trade-off
  für Tenant-Konfigurierbarkeit, nicht kostenlos.
- **`suspect_rule`-Grenze** (Abschnitt 4) muss beim Onboarding neuer Typen klar
  kommuniziert werden, sonst erwarten Tenant-Admins fälschlich vollständig freie
  Propagationslogik.
- Cross-Spec-Abhängigkeit zur Datenmodell-Konsolidierung-Spec (`suspect` auf `Artifact`,
  Abschnitt 5) — bei deren Implementierung nachtragen.
