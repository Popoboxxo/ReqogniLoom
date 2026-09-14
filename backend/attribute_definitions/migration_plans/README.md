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
| `stakeholder_need_moscow_priority_fold.yaml` | StakeholderNeed | Legacy-Modellspalte `moscow_priority` → `custom_fields.moscow_priority` (copy) | Matrix §2 | `trim` |
| `risk_owner_to_actor.yaml` | Risk | `owner_user`/`owner_name` → `Artifact.owner`, `created_by_name` → `Artifact.reporter` | Matrix §6 | `to_actor` |
| `issue_assignee_to_actor.yaml` | Issue | `assignee_id` → `Artifact.owner`, `created_by_name` → `Artifact.reporter` | Matrix §7 | `to_actor` |
| `change_request_requestor_to_reporter.yaml` | ChangeRequest | `requestor_id`/`created_by_name` → `Artifact.reporter` | Matrix §11 | `to_actor` |

Idempotenz: jeder Plan nutzt `only_if` (i. d. R. `target_is_empty and
source_has_text`), sodass ein zweiter Lauf nichts ändert. `copy` ist der Default;
`move`/`drop` kommen in diesem Set nicht vor (kein Datenverlust).

## `uid` — kein Plan nötig

`uid` ist der externe Import-Schlüssel (ReqIF). Er wird **nie** automatisch
generiert (Matrix §0: „die **einzige** Identität ist `id`"); die Spalte bleibt
ausschließlich für Import-Zuordnungen. Es gibt also keinen Wert zu migrieren:
bewusst kein `*.yaml`, kein Transform. Der Bootstrap introspiziert `uid` als
`read_only`-Kernattribut (`READ_ONLY_MODEL_FIELDS`), damit eine Formular-
Rückschreibung nicht 400t.

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
