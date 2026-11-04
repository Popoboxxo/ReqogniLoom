# Dokument-Artefakt (`Document`) — Design (Plan F, WP F2)

> **Status:** freigegeben für die Umsetzung (2026-11-02, Nutzerauftrag Welle 4 / Plan F F2-T0).
> **Quellen:** Konzept [Dokument-Artefakte & Dokumenten-Workflow v4](../../../concepts/2026-10-16-dokument-artefakte-workitem.md)
> (#1374), Umsetzungsplan [Plan F](../../../plans/Archive/2026-10-21-plan-f-dokumente-baselines.md) §WP F2,
> Entscheidungsliste [§0b](../../../plans/2026-10-21-entscheidungen-offen.md#0b-entschieden-am-2026-10-26-nutzer-welle-24).
> **Entscheidungen:** ENT-F0 = a, ENT-F2 = b, ENT-F4 = a, ENT-F5 = a (alle §0b, bindend).
> **Architektur:** [ADR-026](../../../se/ADR/ADR-026_document_artefakt.md).
> **Abgrenzung:** Dieses Dokument beschreibt den gesamten F2-Umfang. Umgesetzt wird in
> diesem Auftrag nur **F2-T0 (Spec + ADR)** und **F2-T1 (Modell + RLS-Migrationen)**;
> Workflow-Seeds, Link-Typen, Service, REST, MCP, Events und Frontend folgen in F2-T2…T8.

## 1. Ziel und Nicht-Ziele

**Ziel.** Ein Dokument wird ein **Artefakt erster Klasse**: Es hat eine Identität, einen
Lebenszyklus, einen Inhalt, einen Feld-Freeze nach Freigabe und ist als Endpunkt des
Trace-Link-Graphen erreichbar. Damit wird das Leitbild aus dem Konzept („Loom ist die
Quelle, `.md` ist Projektion oder Altbestand") technisch anschlussfähig, ohne die
vorhandene Artefakt-Maschinerie zu verdoppeln.

**Nicht-Ziele dieses Auftrags:**

- kein Workflow-Seed (`workflow 0024_seed_document_workflow_definitions` → F2-T2),
- keine neuen Link-Typen und kein Subtyp-Register (`link_types 0014…` → F2-T3),
- kein `DocumentService`, keine REST-ViewSets, keine MCP-Tools (F2-T4…T6),
- keine Outbox-Event-Enum-Erweiterung und kein Indexer-Eintrag (F2-T7),
- keine Projektion/Adoption/Source-Bindung (ENT-F5 = a: eigenes WP F5),
- kein `WorkItem` (Plan F WP F3).

## 2. Entscheidungen (eingearbeitet)

| ID | Entscheidung | Konsequenz für dieses Design |
|---|---|---|
| **ENT-F0 = a** | Plan F gilt als F1-Spec | Kein separates F1-Dokument; F1-Bugfixes sind Voraussetzung, nicht Inhalt. |
| **ENT-F2 = b** | Koexistenz der Begriffe | Das #1374-Artefakt heißt **`Document`**. Die bestehende Dokumentensicht-Spec (`Document` + `DocumentSection`) wird zur schreibgeschützten Projektion **`DocumentView`**; sie ist kein Modell dieses Auftrags. `Baseline.scope="document"` akzeptiert zusätzlich ein `Document` (Vertrag, Umsetzung in F4). |
| **ENT-F4 = a** | Scopes auf Key-Stufen abbilden | `documents:read` → `read_only`, `documents:write` → `author`, `documents:project`/`documents:adopt` → `admin`. Keine `ApiKey`-Schemaänderung; Enforcement in F2-T5/T6. |
| **ENT-F5 = a** | Projektion/Adoption eigenes WP | `owner_mode`, `source*`, `projection_mode` und die MD-Projektion sind **nicht** Teil des F2-Modells; F-4/F-7/G-3 bleiben bis F5 inert spezifiziert. |

## 3. Datenmodell (F2-T1)

### 3.1 Ort und Identität

| Aspekt | Festlegung |
|---|---|
| Modell | `persistence.models.Document(ArtifactWorkspaceMirrorMixin, TenantScopedModel)` |
| Tabelle | `pl_document` |
| Rückgrat | `artifact = OneToOneField(persistence.Artifact, on_delete=CASCADE, related_name="document")` — wie `Requirement`; ein `Document` ist damit Trace-Link-Endpunkt, Baseline-Subjekt und Diff-Objekt. |
| Workspace | `workspace = ForeignKey(Workspace, on_delete=CASCADE, related_name="documents")`, **nicht null**. Der Mixin füllt sie aus `artifact.workspace_id`, wenn sie beim Anlegen fehlt. |
| Tenant | geerbt von `TenantScopedModel` (Tenant-FK, TenantManager, `unscoped`-Escape-Hatch). |
| Audit | `created_at`, `modified_at`, `created_by`, `modified_by`, `version` geerbt von `AuditableModel`. |

**Warum `persistence/models.py` und nicht `application/models.py`?** Das Konzept nennt
`application.Document`; der Ist-Stand (Plan F §WP F2, R-F2-3) hat die Artefakt-Tabellen
längst in `persistence` konsolidiert. `ARTIFACT_TYPE_MODELS` und der UID-Mechanismus
erwarten ein Modell mit `artifact`-FK in dieser App.

**Warum `workspace` nicht null?** Die Unique-Constraint `(workspace, uid)` kann nur
greifen, wenn die Spalte gefüllt ist (`NULL` ist unter einem Unique-Index distinct). Der
Mixin ist das strukturelle Sicherheitsnetz für spätere Schreibpfade; die Dienste setzen
die Spalte zusätzlich explizit.

### 3.2 Felder

| Feld | Typ | Pflicht | Bedeutung |
|---|---|---|---|
| `uid` | `CharField(64, null=True, blank=True)` | nein (wird beim Insert vergeben) | Lokale, lesbare ID `DOC-NNN` je Workspace (§7). |
| `title` | `CharField(255)` | ja | Erste H1 bzw. beim Anlegen gesetzt. |
| `kind` | `CharField(32, choices=Document.Kind)` | ja | `Spec`, `Plan`, `AuditReport`, `Review`, `Conclusion`, `Concept`, `Guide`. DB-Check `ck_document_kind` spiegelt die Choices. |
| `description` | `TextField(blank=True, default="")` | nein | Zweck/Zusammenfassung (nicht der Inhalt). |
| `body` | `TextField(blank=True, default="")` | nein | Markdown-Inhalt. Das Konzept nennt kein Feld `content`; `body` ist der stabile Name für den Text. |
| `doc_date` | `DateField(null=True, blank=True)` | nein | Dokumentdatum (z. B. aus einem Dateinamen abgeleitet). |
| `frozen_at` | `DateTimeField(null=True, blank=True)` | nein | Zeitpunkt des Eintritts in `Freigegeben` (Freeze F-1). |
| `frozen_fields` | `JSONField(default=list, blank=True)` | nein | Liste der eingefrorenen Feldnamen. |
| `version` | geerbt (`IntegerField(default=1)`) | ja | Optimistic-Lock-Zähler, **keine** Inhaltsrevision (AuditableModel-Docstring). Grundlage für `expected_version`/ETag. |

**Bewusst kein `lifecycle_state`-Feld.** Der Zustand lebt wie bei allen anderen
Artefakttypen in `WorkflowItemState` (Hausmuster, REQ-143); der Serializer liefert ihn als
`status`. Ein zusätzliches Feld wäre eine zweite Wahrheit.

**Bewusst keine Quell-/Projektionsfelder.** `owner_mode`, `source`, `source_path`,
`source_ref`, `source_hash`, `projection_mode` gehören zu ENT-F5 = a und werden mit dem
eigenen WP F5 eingeführt — dann additiv, ohne dieses Modell umzubauen.

### 3.3 Constraints und Indizes

| Name | Art | Definition |
|---|---|---|
| `uq_document_workspace_uid` | partielles Unique | `(workspace, uid)` für `uid IS NOT NULL AND uid <> ''` (G1.3-Muster, analog `uq_requirement_workspace_uid`). |
| `ck_document_kind` | Check | `kind IN ('Spec','Plan','AuditReport','Review','Conclusion','Concept','Guide')`. |
| `idx_doc_workspace_modified` | Index | `(tenant, workspace, -modified_at)` für die deterministisch sortierte Liste (später `-modified_at, id`). |

### 3.4 Registrierungen (G1.1/G1.3)

1. `persistence/artifact_backing.py::ARTIFACT_TYPE_MODELS["Document"] = ("persistence","Document")`.
2. `application/local_uid.py`: `UID_PREFIXES["Document"] = "DOC"` und
   `"persistence.Document"` in `UID_MODELS` — damit greift der `pre_save`-Receiver auf
   jedem Schreibpfad (Service, Import, Seed, künftige Direkt-ORM-Pfade).
3. `workflow` liest `outdated_item_ids("Document")` bereits registry-getrieben; das Modell
   braucht dafür kein eigenes Statusfeld.

## 4. Lebenszyklus (F2-T2, Vertrag hier festgelegt)

Zustände (deutsches Haus-Vokabular): `Entwurf → In Prüfung → Freigegeben → Abgelöst`,
zusätzlich `Archiviert`. Übergänge werden als Workflow-Schema `document_default` je Preset
konfiguriert; **kein neuer Workflow-Mechanismus**.

| Von | Nach | Wirkung |
|---|---|---|
| `Entwurf` | `In Prüfung` | Inhalt für Reviewer schreibbar; Kommentare offen. |
| `In Prüfung` | `Freigegeben` | **Freeze** (F-1), Baseline-fähig, Gate-Prüfung G-1…G-4. |
| `In Prüfung` | `Entwurf` | Zurückweisung/Rework. |
| `Freigegeben` | `In Prüfung` | **neue Version v+1** (F-5), Freeze wird aufgehoben. |
| `Freigegeben` | `Abgelöst` | Wird durch einen Nachfolger ersetzt (F-6: neues `Document` + `references` mit `rationale="supersedes"`). |
| `Freigegeben`/`Abgelöst` | `Archiviert` | aus dem Verkehr, aus Standardlisten ausgeblendet. |

**Freigabe-Erkennung** erfolgt über `state_meta.freeze_on_enter`, **nicht** über
`_APPROVAL_TARGET_STATES` (sonst greift die Goal-Freigabe in fremde Regeln).

### 4.1 Freeze-Regeln

| Regel | Inhalt |
|---|---|
| **F-1** | Beim Eintritt `Freigegeben`: `frozen_at = now()`, `frozen_fields = ["title","description","body","kind"]`. Ab F3 kommen Item-Struktur und Inline-Anker hinzu. |
| **F-2** | Frei bleiben: `status`, `owner`/`reporter`/`priority`/`stakeholder`/`custom_fields`, alle Trace-Kanten ohne Textanker, Kommentare, Item-Zustände/-Fortschritt. |
| **F-3** | Schreibversuch auf ein eingefrorenes Feld → `409 {"error":{"code":"FIELD_FROZEN","details":[{"field":"title"}]}}`. Reihenfolge: Syntax-Gate (Plan E E2.4) → F-3 → Versionsprüfung. |
| **F-4** | Re-Sync/Import schreibt bei Abweichung **nicht**, sondern erzeugt Drift-Eintrag + `suspect` + Benachrichtigung + Vorschlag „neue Version". Bis F5 inert. |
| **F-5** | `Freigegeben → In Prüfung` erzeugt Version v+1; der freigegebene Stand bleibt über `ArtifactVersion`/Baseline nachweisbar. |
| **F-6** | Identität wird nie umgeschrieben: neue Quelle-ID = neues `Document`, altes auf `Abgelöst` + Supersedes-Kante. |
| **F-7** | Die Projektion trägt Freigabestand + Hash; Dateiabweichung → Drift, keine stille Übernahme. Bis F5 inert. |

### 4.2 Gates

G-1…G-4 werden als Vorbedingungsregel 9 in `workflow/precondition_rules.py` umgesetzt
(F2-T4), Fehlercode `DOCUMENT_GATE_FAILED` mit `details` je Gate:

| Gate | Bedingung für `Freigegeben` |
|---|---|
| G-1 | kein `WorkItem` in `in_progress`/`blocked` (bis F3: keine Items ⇒ erfüllt). |
| G-2 | jedes Item hat ≥ 1 Kante oder ist `informational` (bis F3 erfüllt). |
| G-3 | kein offener Drift (bis F5 erfüllt, `owner_mode = loom`). |
| G-4 | Pflichtfelder je `kind` (Preset-Schlüssel `document_mandatory_fields_by_kind`). |

## 5. Link-Fabric (F2-T3, Vertrag hier festgelegt)

**Genau drei neue Link-Typen**, keine Matrix-Erweiterung:

| Quelle | Typ | Ziel | `suspect_rule` | `coverage_relevant` |
|---|---|---|---|---|
| `Requirement`/`StakeholderNeed`/`ArchitectureElement`/`Adr`/`Risk`/`Issue`/`Goal` | `documented-in` | `Document` | `target_change_flags_source` | `false` |
| `Document` (`kind` ∈ Conclusion/Review/AuditReport) | `evidences` | `Requirement`/`ArchitectureElement`/`StakeholderNeed` | `target_change_flags_source` | `false` (Test-Coverage bleibt exklusiv `verifies`) |
| `WorkItem` | `depends-on` | `WorkItem` | `target_change_flags_source` | `false` |

Zusätzlich wird `references` **additiv** um `("Document","*")` und `("*","Document")`
erweitert. Die Kind-Einschränkung von `evidences` läuft über das generische Subtyp-Register
(`Document:<kind>`, Wire-Format `Typ:Subtag`), **nicht** über eine zweite Validierung.

## 6. Soft-Delete und Reaktivierung (G1.5, Vertrag)

| # | Regel |
|---|---|
| V1 | Einziges Soft-Delete-Flag ist `Artifact.lifecycle_status`; „gelöscht?" beantwortet nur `workflow.services.outdated_item_ids`. `Document` hat **kein** eigenes Statusfeld. |
| V2 | `DELETE /api/v1/documents/{id}/` → `204`; `change_reason` per Body **oder** `?change_reason=` (Body gewinnt, `parse_change_reason`); fehlt er bei Preset-Pflicht → `400 VALIDATION_ERROR`. |
| V3 | `GET` eines soft-gelöschten Dokuments → `200` + `status: "outdated"`; unbekannte ID → `404`. |
| V4 | Listen enthalten soft-gelöschte Dokumente nur mit `?include_deleted=true`. |
| V5 | Reaktivierung über die bestehende `reactivate`-Aktion. |
| V6 | `Document` übernimmt V2–V5 über dieselben Mixins wie die übrigen Typen; kein eigener Mechanismus. |

In F2-T1 existiert davon nur die **Datenvoraussetzung**: kein Statusfeld, `artifact`-FK,
Registry-Eintrag. Die Endpunkt-Semantik ist F2-T5.

## 7. Lokale UID `DOC-NNN`

- Präfix `DOC`, Allokation atomar über `UidSequence` je `(workspace, "Document")`
  (`application/local_uid.py`), Format `DOC-001`, `DOC-002`, … Nicht recycelnd.
- Ein explizit gesetzter `uid` gewinnt; der `pre_save`-Receiver alloziert nur bei
  `_state.adding` und nicht bei Fixtures (`raw=True`).
- Constraint `uq_document_workspace_uid` erzwingt Eindeutigkeit je Workspace.
- **Abweichung zum Konzept:** Das Konzept nennt `doc:<repo>:<pfad>` als `uid`. Diese Form
  ist die **Herkunftsidentität** und gehört zu ENT-F5 (Source-Bindung). Der lokale,
  lesbare Identifier folgt dem Hausmuster (G1.1) und ist bewusst `DOC-NNN`.

## 8. Row-Level-Security (F2-T1)

- `pl_document` ist tenant-scoped und erhält **im selben PR** eine Policy-Migration
  (`persistence 0124_document_rls_policy`): `ENABLE` + `FORCE ROW LEVEL SECURITY` plus eine
  `ALL`-Policy, deren `USING`/`WITH CHECK` nur Zeilen mit
  `tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid` zulässt.
- Ein nicht gesetztes GUC matcht keine Zeile (fail-closed).
- `persistence/tests/test_rls_coverage.py` deckt die Tabelle statisch (Policy im
  Migrationsgraphen) und auf dem Liveschema (`pg_policies`, `relforcerowsecurity`) ab.
- `persistence/tests/test_document_model.py` prüft die Isolation zusätzlich funktional als
  App-Rolle (`SET ROLE`, Muster aus `test_quality_assessment_model.py`): fremder Tenant
  unsichtbar, Schreiben mit fremder `tenant_id` abgewiesen.

## 9. ETag / Optimistic Lock (F2-T5, Vertrag)

`Document` ist ein **ETag-fähiger** Typ: `version` + `expected_version` im Service,
`If-Match`-Auswertung über `validate_if_match`, `OptimisticLockError` →
`optimistic_lock_response(request, exc, lang)` **vor** dem generischen `except`.
Damit greift der statische Test
`test_every_etag_view_routes_optimistic_lock_through_helper` auch für die neue View.
Konflikt → `412` (ETag) bzw. `409` (Versionskonflikt), kein stiller Last-Write-Wins.

## 10. Events / Outbox (F2-T7, Vertrag)

| Event | Auslöser |
|---|---|
| `DOCUMENT_CREATED` | Anlegen |
| `DOCUMENT_UPDATED` | inhaltliche Änderung |
| `DOCUMENT_DELETED` | Soft-Delete |
| `DOCUMENT_STATE_CHANGED` | Workflow-Übergang |
| `DOCUMENT_PUBLISHED` | Eintritt `Freigegeben` |

Emission im Service in derselben Transaktion wie der Schreibvorgang (Outbox-Muster,
eigene Choices-Migration `application 0037_…` nach Plan A PR-A19). Projektoren tolerieren
Outbox-Zeilen ohne `tenant_id` (O-2). Der Indexer (`application/artifact_indexer.py`)
erhält `Document` in seiner Quellen-Registry.

## 11. Oberflächen-Vollständigkeit (F2-T5…T8)

| Oberfläche | Anforderung |
|---|---|
| Suche | Volltext über `title`/`description`/`body`, Filter auf `kind`; A3-`_TableSpec`. |
| Artefakt-Baum | `Document` als Knoten; `decomposes` zu WorkItems ab F3. |
| Baseline | `Baseline.scope="document"` akzeptiert zusätzlich ein `Document` (ENT-F2 = b); Capture-Meta-Test aus F4.1 erzwingt den Typ. |
| Attribute | `entity_type="Document"` in Definition/Catalog/Defaults; `kind`, `doc_date` katalogisierbar. |
| Kommentare | an `artifact_id` des Dokuments (vorhandener Endpunkt). |
| Memory/Digest | `/artifacts/{id}/memory/digest/` fasst Titel, Zustand und Inhalt zusammen. |
| Versionen/Diff | `/versions/`, `/diff/`, `/workflow-history/` über die vorhandenen Mixins. |
| Trace-Links | Liste mit `link_type`-Filter; Coverage-Metriken unverändert (`verifies` exklusiv). |
| REST/MCP-Parität | `document.*`-Tools (F2-T6), Read-only-Keys lesen. |

## 12. Task-Schnitt und Umsetzungsstand

| Task | Inhalt | Status |
|---|---|---|
| F2-T0 | dieses Dokument + ADR-026 + Review-Protokoll | **dieser PR** |
| F2-T1 | Modell, `persistence 0123_document` + `0124_document_rls_policy`, G1.1/G1.3-Registrierung, `ARTIFACT_TYPE_MODELS`, Tests | **dieser Auftrag** |
| F2-T2 | Workflow-Schema + fünf Registries + Seed-Migration | offen |
| F2-T3 | drei Link-Typen + `references`-Merge + Subtyp-Register | offen |
| F2-T4 | `DocumentService` (Freeze, Gates, `expected_version`) | offen |
| F2-T5 | REST + ETag + Soft-Delete-Vertrag | offen |
| F2-T6 | MCP `document.*` | offen |
| F2-T7 | Events, Indexer, Suche, Baum, Baseline-Capture, Attribute, Digest | offen |
| F2-T8 | Frontend `DocumentsView` / `DocumentView`-Projektion | offen |

## 13. Testplan (F2-T1)

| Test | Prüft |
|---|---|
| `persistence/tests/test_document_model.py::test_create_assigns_uid_and_workspace` | Anlegen über ORM: `uid` im Format `DOC-\d{3}`, `workspace` aus dem Artifact gefüllt, `version == 1`. |
| `…::test_uid_is_per_workspace_and_non_recycling` | Zwei Workspaces beginnen bei `DOC-001`; ein gelöschtes Dokument gibt seine Nummer nicht frei. |
| `…::test_uid_unique_constraint_rejects_duplicate` | `IntegrityError` bei gleichem `(workspace, uid)`; gleiche `uid` in anderem Workspace erlaubt. |
| `…::test_kind_check_constraint` | Unbekannter `kind` wird von der DB abgewiesen. |
| `…::test_artifact_cascade_deletes_document` | Artifact-Löschung kaskadiert auf das Dokument. |
| `…::test_soft_delete_lives_on_the_artifact` | `Document` hat kein `status`-Feld; `outdated_item_ids("Document")` liefert das Dokument, wenn `artifact.lifecycle_status="outdated"`. |
| `…::test_rls_hides_a_foreign_tenants_document` | App-Rolle: fremder Tenant unsichtbar (USING). |
| `…::test_rls_rejects_a_foreign_tenant_write` | App-Rolle: `INSERT` mit fremder `tenant_id` abgewiesen (WITH CHECK). |
| `persistence/tests/test_rls_coverage.py` | Policy + FORCE im Migrationsgraphen und Liveschema. |
| `persistence/tests/test_artifact_lifecycle_status.py` | Registry enthält `Document`. |
| `application/tests/test_local_uid_all_paths.py::test_uid_models_and_prefixes_in_sync` | `Document` in `UID_MODELS` **und** `UID_PREFIXES`. |
| `rest_api/tests/test_artifact_backing_linkability_matrix_1374.py` | `Document` ist als Registry-Typ über `Issue → references` erreichbar. |
| `makemigrations --check` | Migrationsstand = Modellstand. |
| `migrate persistence 0122` → `migrate persistence` | Reverse-Probe der beiden neuen Migrationen. |

## 14. Risiken und offene Punkte

| # | Risiko | Umgang |
|---|---|---|
| R1 | `Document` wird mit dem Baseline-Scope `document` und der UI-`DocumentView` verwechselt. | Namensregel in §2/ADR-026; Scope-Vertrag explizit „Dokument + `decomposes`-Kinder". |
| R2 | Die Linkability-Matrix erwartet eine Factory je Registry-Typ; ein Service existiert erst in F2-T4. | F2-T1 ergänzt eine **test-lokale** Factory, die das Dokument samt Backing-Artefakt direkt anlegt; F2-T4 ersetzt sie durch `DocumentService.create`. Im PR begründet. |
| R3 | `workspace` nicht null könnte spätere Pfade brechen, die nur ein `artifact` setzen. | `ArtifactWorkspaceMirrorMixin` füllt vor dem Insert; Tests decken den Pfad ab. |
| R4 | Freeze/Gates sind ohne `DocumentService` noch nicht durchsetzbar. | Bewusst F2-T4; dieses Modell liefert nur `frozen_at`/`frozen_fields`/`version`. |
| R5 | ENT-F5 verschiebt Quellfelder; ein späteres Nachrüsten muss additiv bleiben. | Keine Quellspalten jetzt; F5 ergänzt nullable Felder + eigene Migration. |
| R6 | `kind`-Check und Choices können auseinanderlaufen. | Check-Constraint als DB-Spiegel plus Test. |

## 15. Akzeptanzkriterien

**F2-T0**

- [x] Spec und ADR-026 sind abgelegt, `status: proposed`, Review-Protokoll vorhanden.
- [x] ENT-F0/F2/F4/F5 sind explizit eingearbeitet.
- [x] Die Abgrenzung zu F2-T2…T8 und F5 ist ohne Rückfrage lesbar.

**F2-T1**

- [ ] `Document` existiert in `persistence/models.py` mit `pl_document`, `artifact`-FK,
      `workspace`-FK, `uid`, `title`, `kind`, `description`, `body`, `doc_date`,
      `frozen_at`, `frozen_fields`, geerbtem `version`.
- [ ] `persistence 0123_document` und `0124_document_rls_policy` sind im selben PR,
      `dependencies` zeigen auf `0122_quality_assessment_rls_policy`; RLS ist
      `ENABLE`+`FORCE` und fail-closed.
- [ ] `Document` ist in `ARTIFACT_TYPE_MODELS`, `UID_MODELS` und `UID_PREFIXES` registriert;
      `uq_document_workspace_uid` und `ck_document_kind` existieren.
- [ ] `test_document_model.py` und `test_rls_coverage.py` sind grün;
      `makemigrations --check` ist leer; die Reverse-Probe läuft.
