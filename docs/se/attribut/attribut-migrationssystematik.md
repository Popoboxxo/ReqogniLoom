# Attribut- & Wert-Migrationssystematik (AWMS)

**Version:** 1.0 · 11.09.2026 · Basis **v1.8.0-beta.10** (`b4c3a91`)
**Zweck:** Attribute **und ihre Inhalte** reproduzierbar, überprüfbar und rückrollbar zwischen
Definitionen, Feldern, Scopes und Stufen bewegen — nicht nur einmalig für das 3-Stufen-Modell,
sondern als **dauerhaftes Werkzeug**.

---

## 1. Warum überhaupt eine Systematik? (Begründung aus dem Bestand)

| Beobachtung | Beleg | Folge ohne Systematik |
|---|---|---|
| Attribut-Definitionen ändern sich mit jeder Ausbaustufe (jetzt: 3 Stufen) | `bootstrap_attribute_definitions.py`, `export/import_definition` | **Werte** bleiben beim alten Attributnamen liegen |
| Werte liegen in `Artifact.custom_fields` (JSONB), ein flaches Map | `attribute_definition_service.count_usages:580-589` | Umbenennen/Verschieben ist Handarbeit |
| Einige Werte liegen in **Modellfeldern**, andere in **custom_fields** | `Requirement.description` vs. `custom_fields` | Silos: `rationale` steckt heute in `description` (s. §5.1) |
| Der Interview-Adapter **benennt um**, statt zu speichern | `interview_artifact_adapters.py:166` → `_PROTOCOL_FIELD_ALIASES = {"rationale": "description"}` | Begründungen sind nicht mehr als solche erkennbar |
| Definitionen sind **pro `(tenant, item_type, preset)`** und materialisieren je Workspace | `AttributeDefinitionService.resolve` + `_workspace_preset()` | eine Definition ändern ≠ Werte überall konsistent |
| In der QS liegen **0 Artefakte mit `custom_fields`** | Messung 11.09.2026 (`probe_cf.py`) | der Zeitpunkt für die Systematik ist **jetzt** günstig |

**Fazit:** Der Bestand ist heute ein **Greenfield** für Werte-Migration. Genau deshalb lohnt es sich,
die Systematik **vor** dem 3-Stufen-Rollout zu bauen — danach gibt es echte Daten zu bewegen.

---

## 2. Drei Migrations-Ebenen

| Ebene | Gegenstand | Heute vorhanden? |
|---|---|---|
| **L1 Definition** | Attribut-Definitionen in `(tenant, item_type, preset)` — anlegen, umbenennen, Typ ändern, teilen, zusammenführen, abkündigen | **teilweise**: create/update/delete, reset, export/import (`on_collision=skip\|overwrite\|rename`), Propagierung in nicht-customized Workspace-Zeilen |
| **L2 Wert** | `Artifact.custom_fields` **und** Modellfelder — kopieren, verschieben, ableiten, umschlüsseln | **fehlt vollständig** |
| **L3 Scope** | Global ↔ Workspace, Preset/Stufe A ↔ B, Tenant A ↔ B | **teilweise**: Export/Import-Dokument (Definitionsebene) |

**Die Wert-Ebene (L2) ist die eigentliche Lücke** — und genau die braucht der Nutzer („Attribute und
Inhalte von einem in ein anderes schieben").

---

## 3. Der Migrationsplan (deklarativ)

Eine Migration ist eine **Datei**, kein Skript. Damit ist sie review-, versionier- und wiederholbar.

```yaml
# migration: rationale-aus-description.yaml
id: 2026-09-rationale-recovery
description: "Interview-Begründungen aus description in das neue rationale-Modellfeld heben"
scope:
  tenant: current           # current | <uuid>
  item_type: Requirement
  preset: [standard, extended]
  workspace: "*"            # "*" = alle, oder explizite UUID-Liste
mode: dry_run               # dry_run (Default) | apply
options:
  idempotent: true          # erneuter Lauf ändert nichts
  abort_on_error: true      # ein Fehler bricht die ganze Migration ab
  audit: true               # AuditEntry je geändertem Artefakt

steps:
  # L1 — Definition anlegen
  - op: define_attribute
    name: rationale
    kind: core              # wird zum Modellfeld (s. Vorbedingung)
    target: model_field
    section: attribution
    required_on: [standard, extended]

  # L1 — Altes Attribut abkündigen (nicht löschen)
  - op: deprecate_attribute
    name: rationale_legacy
    reason: "abgelöst durch rationale (Modellfeld)"

  # L2 — Werte heben: description -> rationale, nur wenn noch leer
  - op: migrate_value
    from: {source: model_field, name: description}
    to:   {target: model_field, name: rationale}
    mode: copy              # copy = Quelle bleibt (sicher) | move = Quelle wird geleert
    only_if: 'to_is_empty and source_has_text'
    transform: extract_rationale      # siehe §4 (Transform-Registry)

  # L2 — Priorität nachziehen
  - op: backfill_value
    target: {target: model_field, name: priority}
    value_strategy: derive_from_link
    via:
      link_type: derives-from
      direction: outgoing          # Requirement --derives-from--> StakeholderNeed
      source_attr: moscow_priority
    fallback: "Should"
    only_if: 'target_is_empty'

  # L3 — Definition in alle Workspaces materialisieren
  - op: requeue_definition
    preset: [standard, extended]
    action: reset_uncustomized   # nur nicht-anpassg. Workspace-Zeilen

  # L2 — Verifikation der Migration
  - op: verify
    assertions:
      - "count(artifacts where priority is null) == 0"
      - "count(artifacts where description != '' and rationale == '') <= 5"
```

**Modus-Regel:** Ohne `mode: apply` läuft immer `dry_run`. Der Report ist identisch aufgebaut, nur ohne
Schreiboperation.

---

## 4. Operationen (Katalog)

| Op | Ebene | Wirkung | Pflichtfelder |
|---|---|---|---|
| `define_attribute` | L1 | Attribut definieren (core/extended, Typ, Section, Sichtbarkeit, `required_on`) | `name`, `kind`, `section` |
| `rename_attribute` | L1 | Definition umbenennen **und** Werte umschlüsseln (atomar!) | `from`, `to` |
| `retype_attribute` | L1 | Typwechsel + `value_map` (z. B. `text →enum`) | `name`, `new_type`, `value_map?` |
| `split_attribute` | L1/L2 | ein Attribut → mehrere (Regex/Transform je Ziel) | `from`, `targets[]` |
| `merge_attribute` | L1/L2 | mehrere → eines (Prioritätsreihenfolge) | `sources[]`, `to` |
| `deprecate_attribute` | L1 | als `deprecated` markieren, Werte bleiben | `name`, `reason` |
| `migrate_value` | L2 | Wert kopieren/verschieben: Feld↔Attribut, Attribut↔Attribut | `from`, `to`, `mode` |
| `map_value` | L2 | Werte umschlüsseln via `value_map` | `target`, `value_map` |
| `backfill_value` | L2 | leere Werte füllen (Konstante, Link-Ableitung, Ausdruck) | `target`, `value_strategy` |
| `derive_value` | L2 | Wert aus anderen Feldern berechnen (Template/Ausdruck) | `target`, `expression` |
| `drop_attribute` | L1/L2 | Attribut + Werte entfernen (nur nach `verify`) | `name`, `confirm: <name>` |
| `requeue_definition` | L3 | Definition in Workspaces/Presets neu materialisieren | `preset`, `action` |
| `export_scope` / `import_scope` | L3 | Definitions-Dokument zwischen Tenants/Workspaces | `scope`, `path` |
| `verify` | alle | Assertions über den Zielzustand | `assertions[]` |

**Nicht im Katalog (bewusst):** freie SQL-Ausführung, Python-Hooks, `delete` ohne `confirm`.
Das Werkzeug soll auch von einem Agenten (MCP) sicher bedienbar bleiben.

---

## 5. Transform-Registry (`transform:` / `value_map`)

Wiederverwendbare, benannte Umformungen — erweiterbar, aber jede registriert und getestet:

| Transform | Wirkung | Einsatzfall |
|---|---|---|
| `identity` | unverändert | Default |
| `trim` | Whitespace normalisieren | Import |
| `enum_map` | Wert aus `value_map`, sonst `fallback` | Prioritätsskalen (High/Med/Low → MoSCoW) |
| `first_paragraph` | erster Absatz | `description` → `rationale` |
| `extract_rationale` | erkennt Begründungs-Marker („Begründung:", „Rationale:", „weil …") und schneidet den Abschnitt heraus | **§5.1**, der Hauptfall |
| `join` / `split` | mit Separator | Merge/Split |
| `to_number` / `to_enum` / `to_date` | Typkonvertierung mit Fehlerquote im Report | `retype` |
| `link_derive` | Wert über eine TraceLink-Kette ziehen | `backfill_value` (§3 Beispiel) |

Jeder Transform **muss** melden: `applied`, `skipped`, `failed` (mit Beispielwerten) — nie still.

---

## 6. Sicherheit, Nachvollziehbarkeit, Rollback

| Anforderung | Umsetzung |
|---|---|
| **Kein Datenverlust** | `copy` ist der Default; `move`/`drop` nur explizit; Vorher-Snapshot in `attribute_migration_snapshot` (artifact_id, custom_fields, geänderte Modellfelder) |
| **Vorschau** | `dry_run` + Impact über `count_usages` (nutzt `custom_fields__has_key` + GIN-Index `pl_artifact_custom_fields_gin`) |
| **Wiederholbar** | `idempotent: true` — ein zweiter Lauf ändert nichts; Report zeigt `skipped_already_done` |
| **Abbrechbar** | `abort_on_error` + Transaktion je Batch; Teilerfolg wird als genau das berichtet |
| **Rollback** | `op: rollback run_id=<id>` stellt aus dem Snapshot wieder her |
| **Auditierbar** | je geändertem Artefakt ein `AuditEntry` (`actor_type` echt, siehe `application/base.py:199-207`) |
| **Run-Historie** | Tabelle `attribute_migration_run` (id, plan_id, plan_hash, mode, started/finished, counts, actor, report_json) |
| **Nebenläufigkeit** | `expected_version`-Guard je Artefakt (Optimistic Locking), sonst Konflikt statt Überschreiben |
| **Rechte** | nur Tenant-Admin; MCP-Gruppe **fail-closed write-gated** (Vorbild: `attribute_definition.update/reset`) |

**Plan-Hash:** der Plan wird gehasht und im Run gespeichert — derselbe Plan zweimal ausgeführt ist
erkennbar, ein *veränderter* Plan mit gleicher `id` wird abgelehnt (kein stilles Nachschieben).

---

## 7. Schnittstellen

| Kanal | Endpunkt | Zweck |
|---|---|---|
| CLI | `manage.py migrate_attributes <plan.yaml> [--apply] [--rollback <run_id>]` | Operator, Cron, CI |
| REST | `POST /api/v1/attribute-migrations/plan` (Vorschau) · `POST /api/v1/attribute-migrations/` (apply) · `GET /api/v1/attribute-migrations/{run_id}/` · `POST …/{run_id}/rollback/` | Admin-UI, Skripte |
| MCP | `attribute_migration.plan` · `attribute_migration.apply` (admin-gated) · `attribute_migration.status` | Agenten — **plan lesend für alle, apply nur Admin** |
| Report | JSON + Markdown, im Run gespeichert | Nachweis für Audit/QS |

---

## 8. Erstes Anwendungs-Set (die konkreten Migrationen für das 3-Stufen-Modell)

### 8.1 `description` → `rationale` (Interview-Begründungen)

**Ausgangslage:** `interview_artifact_adapters.py:166` mappt `rationale → description`. Bei
Interview-erzeugten Anforderungen steht die Begründung also **im Beschreibungsfeld**.
**Risiko:** Der Text kann mit echten Beschreibungsinhalten vermischt sein → **kein blindes Verschieben**.
**Vorgehen:**
1. `mode: copy` (Beschreibung bleibt erhalten — nichts geht verloren).
2. `transform: extract_rationale` mit Marker-Erkennung; ohne Marker `first_paragraph`.
3. `verify`-Assertion: `count(rationale gefüllt) ≤ count(interview-created)` — mehr wäre ein Fehler.
4. Erst nach Sichtprüfung optional `mode: move` in einem zweiten Plan.

### 8.2 `priority`-Backfill

**Ausgangslage:** `priority` existiert nicht; `standard`/`extended` fordern es (Presets).
**Strategie (Entscheidung Daniel, Vorschlag):**
1. `derive_from_link` über `derives-from` → `StakeholderNeed.moscow_priority`
2. Fallback `"Should"`
3. `only_if: target_is_empty` → idempotent
**Markierung:** backfilled Werte erhalten im Report den Vermerk `source: derived|fallback`, damit ein
späterer Review echte von abgeleiteten Prioritäten trennen kann.

### 8.3 `Goal`-Attribute → `Measure`-Entität (C2 aus dem Report)

Zwei-Schritt-Migration, weil eine Entität entsteht:
1. Plan A: `Measure`-Zeilen aus `Goal.measure_name`/`target_value`/`unit`/`threshold` erzeugen
   (`op: derive_entity` — Erweiterung des Katalogs, hier bewusst als **eigene Erweiterung** markiert).
2. Plan B: alte Attribute `deprecate_attribute` (nicht löschen), nach `verify` entfernen.
**Reihenfolge ist zwingend** — sonst stehen die Werte doppelt oder gar nicht.

### 8.4 3-Stufen-Definitionen ausrollen

`define_attribute` × n je `(item_type, preset)` + `requeue_definition` in die Workspaces.
Bei bestehenden Workspace-Anpassungen: `reset_uncustomized` **nicht** auf `is_customized=true`-Zeilen
anwenden (`test_reinitialize_propagates_to_non_customized_workspace_rows`) — sonst wird Kundenarbeit
überschrieben. **Das ist eine harte Regel.**

---

## 9. Erweiterbarkeit — „längerfristig und an anderen Stellen nutzbar"

Dieselbe Engine bedient ohne Umbau:

| Anwendungsfall | Wie |
|---|---|
| **Attribute umbenennen ohne Datenverlust** | `rename_attribute` (atomar, s. o.) |
| **ReqIF-/CSV-Import-Mapping** | `import_scope` + `migrate_value` aus einem Mapping-Dokument |
| **Tenant-Onboarding** | `import_scope` (Definitionsset) + `requeue_definition` |
| **Fremdsystem-Import** (z. B. Calibre, Excel) | Mapping-Plan statt Einzel-Skript |
| **Stufenwechsel eines Workspaces** (minimal→standard) | `requeue_definition` + `backfill_value` für die neuen Pflichtfelder |
| **Konsolidierung** (zwei ähnliche Attribute → eines) | `merge_attribute` |
| **Governance** (Attribut abschaffen) | `deprecate_attribute` → Wartezeit → `drop_attribute` |

**Damit ist die Systematik kein Einmal-Projekt, sondern die fehlende **zweite Hälfte** der
Attribut-Definition v2**: v2 kann Definitionen verwalten — AWMS kann **Daten** dazu bewegen.

---

## 10. Umsetzungs-Schnitt (Vorschlag)

| Schritt | Inhalt | Aufwand |
|---|---|---|
| 1 | Plan-Schema + `dry_run`-Engine + Report (nur `migrate_value`, `backfill_value`) | S |
| 2 | Transform-Registry (5 Transforms) | S |
| 3 | Snapshot + Rollback + `attribute_migration_run` | M |
| 4 | CLI + REST + MCP-Anbindung | M |
| 5 | `rename_attribute` / `merge_attribute` / `deprecate_attribute` | M |
| 6 | `split_attribute` / `derive_value` | M |
| 7 | `requeue_definition` + `import/export_scope` | M |
| 8 | `derive_entity` (Goal → Measure) | L |

**Bewusst zuletzt:** Schritt 8 ist die einzige Operation, die Entitäten erzeugt — sie ist am
risikoreichsten und braucht das Rollback aus Schritt 3.
