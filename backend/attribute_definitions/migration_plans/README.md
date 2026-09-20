# Erste AWMS-Migrationspläne (Spec §8)

Epic #934, Workstream WS7 (#940), Teil B. Jede Datei in diesem Verzeichnis ist
ein deklarativer Migrationsplan (Spec §3) — review-, versionier- und
wiederholbar, ausgeführt ausschließlich über
`application.attribute_migration_service.AttributeMigrationService` (CLI
`manage.py attribute_migrate`, REST `/api/v1/attribute-migration/`, MCP
`attribute_migration.*`).

**Modus-Regel:** Im Plan steht bewusst `mode: dry_run`. `apply` ist der
explizite Schreib-Einstieg (`--apply`, `POST …/apply/`, `attribute_migration.apply`);
`--dry-run` ist der Default.

## Ausführbare Pläne

| Plan | item_type | Was | Wo | Transform |
|---|---|---|---|---|
| `rationale_from_description.yaml` | Requirement | `description` → `custom_fields.rationale` (copy) | §8.1 | `extract_rationale` |
| `priority_backfill.yaml` | Requirement | leeres `Artifact.priority` füllen | §8.2 | `derive_from_link` (`derives-from` → `StakeholderNeed.moscow_priority`), Fallback `"Should"` |
| `backfill_requirement_uid.yaml` | Requirement | leere `Requirement.uid` mit `REQ-NNN` füllen | #932 | `sequence` (`application.local_uid`) |
| `stakeholder_need_moscow_priority_fold.yaml` | StakeholderNeed | Legacy-Modellspalte `moscow_priority` → `custom_fields.moscow_priority` (copy) | Matrix §2 | `trim` |
| `risk_owner_to_actor.yaml` | Risk | `owner_user`/`owner_name` → `Artifact.owner`, `created_by_name` → `Artifact.reporter` | Matrix §6 | `to_actor` |
| `issue_assignee_to_actor.yaml` | Issue | `assignee_id` → `Artifact.owner`, `created_by_name` → `Artifact.reporter` | Matrix §7 | `to_actor` |
| `change_request_requestor_to_reporter.yaml` | ChangeRequest | `requestor_id`/`created_by_name` → `Artifact.reporter` | Matrix §11 | `to_actor` |

Idempotenz: jeder Plan nutzt `only_if` (i. d. R. `target_is_empty and
source_has_text`), sodass ein zweiter Lauf nichts ändert. `copy` ist der Default;
`move`/`drop` kommen in diesem Set nicht vor (kein Datenverlust).

## `uid` — Backfill für Bestandszeilen (#932)

`uid` ist die **lokale, lesbare Kennung** (`REQ-001`, `NEED-014`, …), die jeder
Anlege-Pfad seit #932 automatisch vergibt; die ReqIF-Import-Identität liegt auf
den `Artifact.reqif_*`-Feldern (#1003).

`backfill_requirement_uid.yaml` versorgt Zeilen, die **vor** #932 entstanden
sind: `value_strategy: sequence` vergibt je Workspace die nächste freie
`REQ-NNN`-Nummer über denselben monotonen, nicht recycelnden Allokator wie der
Anlege-Pfad (`application.local_uid.generate_local_uid`). `only_if:
target_is_empty` hält den Lauf idempotent. Die Strategie ist **nur** für das
Ziel `uid` zugelassen (sonst schlägt der Schritt fehl, statt eine `REQ-NNN`-
Zeichenkette in ein fremdes Feld zu schreiben); für die übrigen uid-Typen
denselben Plan mit angepasstem `scope.item_type` verwenden. Der Bootstrap
introspiziert `uid` als `read_only`-Kernattribut (`READ_ONLY_MODEL_FIELDS`),
damit eine Formular-Rückschreibung nicht 400t.

## Vollständiger Operationskatalog (#930)

Seit #930 sind alle im Katalog sicher ausführbaren Operationen implementiert
(`OPS` in `migration_plan.py`): `define_attribute`, `rename_attribute`,
`retype_attribute`, `split_attribute`, `merge_attribute`, `migrate_value`,
`map_value`, `backfill_value`, `derive_value`, `drop_attribute`,
`deprecate_attribute`, `requeue_definition`, `verify`, `export_scope`,
`import_scope`.

* `deprecate_attribute` markiert eine Definition als abgekündigt
  (`deprecated`/`deprecated_reason`); Feld und Werte bleiben unangetastet —
  erst ein späteres `drop_attribute` entfernt sie.
* `export_scope` schreibt das Definitionsdokument eines Scope in den Run-Report
  (`steps[i].document`), `import_scope` liest es inline wieder ein
  (`on_collision: skip|overwrite|rename`). Kein Dateizugriff — MCP-sicher.

Weiterhin **nicht** im Katalog (mit Begründung in `UNSUPPORTED_OPS`):
`derive_entity` (blockiert auf #393) und `rollback` (Operation auf einem Run,
nicht auf einem Plan).

## Blockiert auf #393

`goal_measures_to_measure.draft.yaml` überführt die Goal-Interim-Attribute
(`measure_name`/`target_value`/`unit`/`threshold`, WS6 #939) in die
`Measure`-Entität. Er nutzt die Operation `derive_entity` (Spec §10 Schritt 8)
und **kann nicht laufen**, solange

* die `Measure`-Entität fehlt (Epic-#934-Non-Goal, #393), und
* `derive_entity` bewusst nicht im Operationskatalog ist (Entitäts-Erzeugung ist
  am risikoreichsten und zuletzt).

`normalize_plan` lehnt den Entwurf deshalb mit der #393-Begründung ab — der Test
`test_migration_plans.py::test_goal_measure_plan_is_blocked_on_393` hält die
Abhängigkeit fest (statt sie zu verschweigen). Bis dahin bleiben die
Interim-Attribute der Träger.

## Actor-Abhängigkeit

Die Legacy-Owner-Pläne (Risk/Issue/ChangeRequest) schreiben auf die
Artifact-Systemfelder `owner`/`reporter` (Actor-FKs). Die Engine löst den Wert
über `application.actor_service.ActorService` auf: eine User-UUID wird zum
Tenant-Actor (`get_or_create_for_user`), ein Freitext- oder hängender Wert zu
einem externen Platzhalter (`get_or_create_external`) — reviewbar statt
abbrechend. `dry_run` legt dabei **keine** Actors an (Schreibpfad erst in
`_persist`).

## Risk-Flip (WS2-Deferral aufgelöst)

Matrix §0 verlangt `owner`/`reporter`/`priority` für **alle** Typen. Bis WS7
schattierte `Risk.owner` (Freitext-CharField) den Artifact-`owner`-FK. WS7
benennt die Spalte in `Risk.owner_name` um (`db_column="owner"`, state-only →
keine Datenbewegung), nimmt Risk in `SYSTEM_FIELDS_ENABLED_ITEM_TYPES` auf und
migriert die Werte mit `risk_owner_to_actor.yaml`. Der physische Spaltenabbau
(`owner_name`) ist der Contract-Schritt danach.
