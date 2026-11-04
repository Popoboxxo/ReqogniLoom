# WorkItem, Agenten-Zustand und Inline-Verweise — Design (Plan F, WP F3)

> **Status:** freigegeben für die Umsetzung (2026-11-02, Nutzerauftrag Welle 4 / Plan F F3-T0).
> **Quellen:** Konzept [Dokument-Artefakte & Dokumenten-Workflow v4](../../concepts/2026-10-16-dokument-artefakte-workitem.md)
> (#1374), Umsetzungsplan [Plan F](../../plans/2026-10-21-plan-f-dokumente-baselines.md) §WP F3,
> Entscheidungsliste [§0b](../../plans/2026-10-21-entscheidungen-offen.md#0b-entschieden-am-2026-10-26-nutzer-welle-24).
> **Entscheidungen:** ENT-F3 = a (Inline-Verweise; bindend, §0b), ENT-G1 = A (Soft-Delete-Vertrag,
> vorläufig), ENT-E2 = A (ETag-Regel, vorläufig), ENT-F1 = a/b (Link-Typen, F3-T3).
> **Vorgänger:** [F2-Spec](2026-11-02-f2-document-design.md) und
> [ADR-026](../../se/ADR/ADR-026_document_artefakt.md) — F2 ist vollständig gemergt.
> **Abgrenzung:** Dieses Dokument beschreibt den gesamten F3-Umfang. Umgesetzt wird in diesem
> Auftrag nur **F3-T0 (Spec + Review-Protokoll)** und **F3-T1 (Modell + RLS-Migrationen)**;
> Workflow-Seeds, Link-Typen, Service, REST, MCP, Inline-Anker-Register, Events und Frontend
> folgen in F3-T2…T9.

## 1. Ziel und Nicht-Ziele

**Ziel.** Ein `WorkItem` wird ein **Artefakt erster Klasse**: ein zerlegbarer, adressierbarer und
zustandsbehafteter Knoten innerhalb eines `Document`. Es trägt Fortschritt, Blockadegrund,
Wiederaufnahme-Hinweis („hier weiter") und Beleg — und ist damit der explizite, abfragbare
Agenten-Zustandsspeicher, den das Konzept §9 an die Stelle von `progress-ledger`-Dateien setzt.

**Nicht-Ziele dieses Auftrags:**

- keine Workflow-Schemas und keine Provisionierung (`workflow 0025_…` → F3-T2),
- keine Link-Typen und keine Pair-Erweiterung (`link_types 0015_…` → F3-T3),
- kein `WorkItemService`, keine REST-ViewSets, keine MCP-Tools (F3-T4…T6),
- kein Inline-Anker-Register (`persistence 0126/0127_inline_anchor` → F3-T7),
- keine Outbox-Event-Enum-Erweiterung und kein Indexer-Eintrag (F3-T8),
- kein Frontend (F3-T9),
- kein Typ `Task` für dokumentfreie Agenten-Aufgaben (Konzept §12, vertagt).

## 2. Entscheidungen (eingearbeitet)

| ID | Entscheidung | Konsequenz für dieses Design |
|---|---|---|
| **ENT-F3 = a** | Anzeige `[[Begriff]]`, **Speicherung bleibt** das bestehende Token-Format `[[glossary:<uuid>@<rev>]]` | Keine Migration und keine zweite Grammatik. Der Resolver (§7) liest beide Formen; das Anker-Register speichert nur den **Fundort**, nie eine neue Token-Syntax. |
| **ENT-G1 = A** (vorläufig) | Soft-Delete ist **ein** Flag: `Artifact.lifecycle_status` | `WorkItem` bekommt **kein** `status`-/`lifecycle_state`-Feld (Plan G G1.5 V1). |
| **ENT-E2 = A** (vorläufig) | ETag über `version` + `expected_version` | `version` ist der geerbte Optimistic-Lock-Zähler; `work_item.*` nutzt `validate_if_match`/`optimistic_lock_response` (F3-T4/T5). |
| **ENT-F1** | Link-Vokabular (F3-T3) | `depends-on` (WorkItem → WorkItem) ist der einzige neue Typ; `decomposes`/`references` werden additiv um WorkItem-Paare erweitert. |

**Konsequenz aus E11/O7 (Konzept §4.2/§12):** `document` ist **Pflicht**. Ein WorkItem ohne
Dokument ist kein gültiger Zustand; freie Agenten-Aufgaben bekommen später einen eigenen Typ
`Task` (vertagt).

## 3. Datenmodell (F3-T1)

### 3.1 Ort und Identität

| Aspekt | Festlegung |
|---|---|
| Modell | `persistence.models.WorkItem(ArtifactWorkspaceMirrorMixin, TenantScopedModel)` |
| Tabelle | `pl_work_item` |
| Rückgrat | `artifact = OneToOneField(persistence.Artifact, on_delete=CASCADE, related_name="work_item")` — wie `Document`/`Requirement`; ein WorkItem ist damit Trace-Link-Endpunkt, Baseline-Subjekt und Diff-Objekt. |
| Dokumentbindung | `document = ForeignKey(persistence.Document, on_delete=PROTECT, related_name="work_items")`, **nicht null**. `PROTECT` greift nur bei einem **harten** Delete (Admin-/DB-Ebene): der reguläre Löschpfad ist Soft-Delete über `Artifact.lifecycle_status` (ENT-G1 = A) und lässt die Items unangetastet — ein Dokument mit Arbeitsstand verschwindet damit nicht versehentlich aus der Historie. |
| Workspace | `workspace = ForeignKey(Workspace, on_delete=CASCADE, related_name="workspace_work_items")`, **nicht null**. Trägt die partielle UID-Constraint (§3.3); der Mixin füllt sie aus `artifact.workspace_id`. |
| Tenant | geerbt von `TenantScopedModel` (Tenant-FK, `TenantManager`, `unscoped`-Escape-Hatch). |
| Audit | `created_at`, `modified_at`, `created_by`, `modified_by`, `version` geerbt von `AuditableModel`. |

**Warum `persistence/models.py` und nicht `application/models.py`?** Das Konzept nennt
`application.WorkItem`; der Ist-Stand hat die Artefakt-Tabellen mit F2 in `persistence`
konsolidiert (R-F2-3, ADR-026). `ARTIFACT_TYPE_MODELS`, der UID-Receiver und die
Baseline-/Diff-Pfade erwarten ein Modell mit `artifact`-FK in dieser App. `Document` und
`WorkItem` bleiben damit symmetrisch.

**Warum ein eigenes `workspace`-Feld, obwohl `document.workspace_id` existiert?** Die
G1.3-Constraint `uq_work_item_workspace_uid` braucht eine gefüllte Spalte auf **dieser** Tabelle;
`NULL` ist unter einem Unique-Index distinct, und ein Join in eine Constraint ist nicht möglich.
Der Mixin ist das strukturelle Sicherheitsnetz; die Dienste setzen die Spalte zusätzlich explizit.

### 3.2 Felder

| Feld | Typ | Pflicht | Bedeutung |
|---|---|---|---|
| `uid` | `CharField(64, null=True, blank=True)` | nein (wird beim Insert vergeben) | Lokale, lesbare ID `WI-NNN` je Workspace (§8). |
| `document` | `ForeignKey(Document, PROTECT)` | **ja** | Zugehöriges Dokument (E11/O7). |
| `kind` | `CharField(32, choices=WorkItem.Kind)` | ja | `Phase`, `Step`, `Milestone`, `OpenPoint`, `Checkpoint`. DB-Check `ck_work_item_kind` spiegelt die Choices. |
| `ordinal` | `IntegerField(default=0)` | ja (Wert) | Reihenfolge im Dokument. Ersetzt die im Konzept verworfene Kante `precedes`; Resume sortiert `(ordinal, id)`. |
| `title` | `CharField(255)` | ja | Item-Titel (Überschrift des Abschnitts). |
| `body` | `TextField(blank=True, default="")` | nein | Markdown des Abschnitts (bei `Step`/`Checkpoint`). |
| `progress` | `PositiveSmallIntegerField(null=True, blank=True)` | nein | 0–100, für `Phase`/`Milestone`. DB-Check `ck_work_item_progress_range` erzwingt den Bereich, wenn gesetzt. |
| `blocked_reason` | `TextField(blank=True, default="")` | nein (Pflicht **bei** `blocked`) | Grund der Blockade (A-4). Die Pflicht ist eine Workflow-Vorbedingung (F3-T2/T4), keine Spaltennullability — `dropped` trägt den Verwerfungsgrund ebenfalls hier. |
| `next_action` | `CharField(255, blank=True, default="")` | nein | Wiederaufnahme-Hinweis für Agenten (§6). |
| `last_activity_at` | `DateTimeField(null=True, blank=True)` | nein | Heartbeat (A-3); `DOC-P5` liest ihn. |
| `last_actor` | `CharField(128, blank=True, default="")` | nein | Agent-/Menschen-Kennung des letzten Zugriffs (A-1). |
| `evidence_ref` | `CharField(512, blank=True, default="")` | nein | Beleg (Commit, Testlauf, Artefakt-ID). |
| `approved_by` | `CharField(128, blank=True, default="")` | nein | Menschliche Freigabe, nur `extended`-Preset (§4). |
| `approved_at` | `DateTimeField(null=True, blank=True)` | nein | Zeitpunkt der Freigabe. |
| `due_date` | `DateTimeField(null=True, blank=True)` | nein | Fälligkeit. |
| `exit_criteria` | `TextField(blank=True, default="")` | nein | Fertigstellungskriterium (Gates, Konzept §5.4). |
| `version` | geerbt (`IntegerField(default=1)`) | ja | Optimistic-Lock-Zähler, **keine** Inhaltsrevision (AuditableModel-Docstring). Grundlage für `expected_version`/ETag. |

**Gemeinsame Attribut-Oberfläche.** `owner`, `reporter`, `priority` und `custom_fields` liegen wie
bei jedem Artefakt auf dem **Backing-`Artifact`** (Attribut-v3-Kommentar in
`persistence/models.py`), nicht auf `pl_work_item` — das Konzept §4.2 meint genau diese geerbte
Fläche. `WorkItem` dupliziert sie nicht.

**Warum `last_actor`/`approved_by` Freitext sind.** Ein Agent hat keinen `User`-Datensatz; die
Kennung ist eine Agent-/Session-Identität (`last_actor`) bzw. der menschliche Freigebende
(`approved_by`). Ein `Actor`-FK würde für Agenten entweder Dummy-Zeilen oder eine stille
Nicht-Erfassung erzwingen. Die Felder sind bewusst `CharField` (Konzept §4.4), die
Freigabe-Semantik (`approved_by` + `approved_at` gemeinsam) prüft der Service in F3-T4.

**Bewusst kein `item_state`-Feld.** Der Zustand (`todo|in_progress|blocked|done|dropped` bzw.
`in_review` in `extended`) lebt wie bei jedem anderen Artefakttyp in `WorkflowItemState`
(Hausmuster, REQ-143, ADR-026 R2). Ein zusätzliches Feld wäre eine zweite Wahrheit — und die
tier-abhängigen Workflows (§4) könnten sie nicht konsistent halten.

**Bewusst keine Quell-/Selektor-Felder.** `source_selector`/`source_hash` aus Konzept §4.4
gehören zur Adoption/Projektion (ENT-F5 = a, eigenes WP F5) und werden dort additiv ergänzt.

### 3.3 Constraints und Indizes

| Name | Art | Definition |
|---|---|---|
| `uq_work_item_workspace_uid` | partielles Unique | `(workspace, uid)` für `uid IS NOT NULL AND uid <> ''` (G1.3-Muster, analog `uq_document_workspace_uid`). |
| `ck_work_item_kind` | Check | `kind IN ('Phase','Step','Milestone','OpenPoint','Checkpoint')`. |
| `ck_work_item_progress_range` | Check | `progress IS NULL OR (progress >= 0 AND progress <= 100)`. |
| `idx_workitem_document_ordinal` | Index | `(tenant, document, ordinal)` — die Resume-Abfrage (§6) und jede Item-Liste je Dokument; Tiebreaker `id` kommt aus der Sortierung. |

### 3.4 Registrierungen (G1.1/G1.3)

1. `persistence/artifact_backing.py::ARTIFACT_TYPE_MODELS["WorkItem"] = ("persistence", "WorkItem")`.
   Damit ist der Typ automatisch Trace-Link-Endpunkt, Baseline-Subjekt, Diff-Objekt und
   Interview-Ziel, und der Registry-Fallback in `TraceLinkService` löst eine **Entity-ID** auf ihr
   Backing-Artefakt auf (#1075).
2. `application/local_uid.py`: `UID_PREFIXES["WorkItem"] = "WI"` und
   `"persistence.WorkItem"` in `UID_MODELS` — der `pre_save`-Receiver greift damit auf jedem
   Schreibpfad (Service, Import, Seed, künftige Direkt-ORM-Pfade).
3. `workflow` liest `outdated_item_ids("WorkItem")` registry-getrieben; das Modell braucht dafür
   kein eigenes Statusfeld.
4. Die Linkability-Matrix (`rest_api/tests/test_artifact_backing_linkability_matrix_1374.py`)
   parametrisiert über die Registry: der neue Typ wird automatisch ein Fall und erhält in F3-T1
   eine **test-lokale** Factory (bis F3-T4 den Service liefert), genau wie `Document` in F2-T1.

## 4. Workflows je Rigor-Preset (F3-T2, Vertrag hier festgelegt)

Drei Schemas, provisioniert über `workflow-defaults/{item_type=WorkItem}/{preset}` — **kein neuer
Workflow-Mechanismus**:

| Preset | Zustände | Zweck |
|---|---|---|
| `work_item_minimal` | `todo → in_progress → done`, `dropped` | nur den Abarbeitungsstand sehen (E8) |
| `work_item_standard` | + `blocked` (`blocked_reason` Pflicht) | Hindernisse sichtbar machen |
| `work_item_extended` | + `in_review`; `in_review → done` nur `approver`, setzt `approved_by`/`approved_at` | Nachweis, dass ein Mensch abgenommen hat |

- **Provisionierung** wie `Requirement`: `workspace_provisioning.py` erhält einen
  `work_item_preset`-Parameter (Default = Workspace-Preset) und legt das passende Schema an.
  `WORKFLOW_ITEM_TYPES` (`workflow/item_types.py`) listet `WorkItem` **nicht** als
  Fixed-Preset-Typ, weil es tier-abhängig ist.
- **Vorbedingungen:** `blocked` erfordert `blocked_reason`; `done` im `extended`-Preset erfordert
  die Freigabe. G-1/G-2 aus F2 (Dokument-Gates) werden mit F3-T3 aktiv.
- **Progress** ist in allen Presets möglich und unabhängig vom Zustand.

## 5. Link-Fabric (F3-T3, Vertrag)

| Quelle | Typ | Ziel | Status |
|---|---|---|---|
| `WorkItem` | `depends-on` | `WorkItem` | ➕ neu (einziger neuer Typ) |
| `Document` | `decomposes` (best.) | `WorkItem` | Pair-Erweiterung |
| `WorkItem` | `decomposes` (best.) | `WorkItem` | Pair-Erweiterung (Phase → Schritt) |
| `WorkItem` | `references` (best.) | `*` | Pair-Erweiterung (ersetzt `implements`/`traces` aus dem Konzept) |

`ordinal` ist die **Reihenfolge**, `depends-on` die **Abhängigkeit** — zwei Achsen, bewusst
getrennt. Die Kanten ohne Textanker bleiben auch im Zustand `Freigegeben` frei schreibbar (F-2).

**G-2-Ausnahme `informational` (geklärt in F3-T2):** G-2 liest in
`workflow/precondition_rules._document_item_gate_violations` ein `informational`-Flag am Item
(`getattr(item, "informational", False)`). Es steht **nicht** in der F3-T1-Feldliste und wird
bewusst als **Regel**, nicht als Spalte umgesetzt: `WorkItem.informational` ist eine abgeleitete
Property und gilt genau für `kind == "Checkpoint"` — ein Wiederaufnahme-Marker („hier weiter"),
kein Arbeitsergebnis, das verlinkt werden könnte. Eine explizite User-Markierung bräuchte eine
`persistence`-Migration und eine UI-Fläche (F3-T4/T9) und würde für alle anderen Items nur ein
unbenutztes Flag erzeugen. G-2 ist damit ab F3-T2 für Nicht-Checkpoint-Items ohne Kante
fail-closed und für Checkpoints erfüllt; beides ist in
`workflow/tests/test_work_item_workflow_presets.py` gepinnt.

## 6. Resume, Checkpoint, Heartbeat (F3-T4/T6, Vertrag)

```
GET /api/v1/work-items/resume/?workspace_id=&document_id=&actor=
MCP  work_item.resume
→ { "checkpoint": {…}|null,
    "open_items": [ { "id","uid","kind","status","progress","next_action",
                      "blocked_reason","last_actor","last_activity_at","links":[…] } ] }
```

| Regel | Inhalt |
|---|---|
| **Sortierung** | `ordinal`, Tiebreaker `id` — deterministisch (G2.1). |
| **Auswahl** | alle Items mit Zustand ≠ `done`/`dropped`; `checkpoint` = jüngstes `Checkpoint`-Item des Dokuments (bzw. `null`). |
| **Checkpoint** | `work_item.checkpoint` legt ein `WorkItem:Checkpoint` mit `next_action` an. |
| **Heartbeat** | `last_activity_at` wird bei **jeder** Item-Aktion gesetzt (A-3); `DOC-P5` meldet verwaiste `in_progress`-Items. |
| **Konflikt** | Optimistic Lock über `version` + `expected_version`/ETag (A-2, §9). |

Der Resume-Aufruf ist **ein** MCP-Tool, damit jeder Agent ohne Repo-Zugang fortsetzen kann (A-6).

## 7. Inline-Verweise und Anker (ENT-F3 = a; F3-T7)

**Entscheidung ENT-F3 = a ist bindend:** Anzeige/Autor-Eingabe `[[Begriff]]`, **Speicherung
bleibt** `[[glossary:<uuid>]]` bzw. `[[glossary:<uuid>@<rev>]]` (`glossary_reference_service.py`,
#1266). Es gibt **keine** Migration und **keine** zweite Grammatik.

| Regel | Verhalten |
|---|---|
| **I-1** | Anker gesetzt ⇒ Kante existiert — automatisch, ohne Zusatzklick. |
| **I-2** | Anker entfernt ⇒ Kante wird entfernt, **sofern** kein weiterer Anker derselben Kante im Dokument bleibt. |
| **I-3** | Kante im Graph gelöscht ⇒ zugehörige Anker werden mitentfernt; vorher `409 ANCHORS_PRESENT {"details":{"count":n}}`, erneuter Aufruf mit `?confirm_anchor_count=n`. |
| **I-4** | Kante **ohne** Anker bleibt zulässig und wird als „ohne Textstelle" gekennzeichnet. |
| **I-5** | Ziel gelöscht/archiviert ⇒ Anker bleibt als **toter Verweis** stehen; `DOC-P7` meldet ihn, die Projektion rendert Klartext + Warnung. |

**Anker-Register** (`pl_inline_anchor`, F3-T7): `source_artifact`, `field`, `target_artifact`,
`link`, `token`. Der Token ist der **bestehende** gespeicherte Text (`[[glossary:<uuid>@<rev>]]`);
`[[Begriff]]` ist ausschließlich Editor-Anzeige. Die stabile ID lebt im Register, nie im
Fließtext.

**Freeze-Wechselwirkung:** Ein Anker sitzt im Text und ist damit Inhalt — im Zustand
`Freigegeben` ist Setzen/Entfernen ein Versionsvorgang (F-5), während Kanten **ohne** Anker frei
bleiben (F-2).

## 8. Lokale UID `WI-NNN`

- Präfix `WI`, Allokation atomar über `UidSequence` je `(workspace, "WorkItem")`
  (`application/local_uid.py`), Format `WI-001`, `WI-002`, … Nicht recycelnd.
- Ein explizit gesetzter `uid` gewinnt; der `pre_save`-Receiver alloziert nur bei
  `_state.adding` und nicht bei Fixtures (`raw=True`). Kontextfreie Wartungspfade können `uid`
  `NULL` lassen — die partielle Constraint schließt sie bewusst aus, der Service-Pfad vergibt
  immer (Präzisierung aus RVW-2026-11-02-001-02).
- Constraint `uq_work_item_workspace_uid` erzwingt Eindeutigkeit je Workspace.
- **Abweichung zum Konzept:** Das Konzept nennt `item:<document-uid>:<selektor>` als `uid`. Diese
  Form ist eine **Herkunftsidentität** (Adoption/Projektion, F5) und kein lokaler Identifier. Der
  lesbare Identifier folgt dem Hausmuster (G1.1) und ist bewusst `WI-NNN` — dieselbe Abweichung,
  die F2 für `DOC-NNN` dokumentiert hat.

## 9. ETag / Optimistic Lock (F3-T5)

`WorkItem` ist ein **ETag-fähiger** Typ: `version` + `expected_version` im Service,
`If-Match`-Auswertung über `validate_if_match`, `OptimisticLockError` →
`optimistic_lock_response(request, exc, lang)` **vor** dem generischen `except`. Damit greift der
statische Test `test_every_etag_view_routes_optimistic_lock_through_helper` auch für die neue View.
Konflikt → `412` (ETag) bzw. `409` (Versionskonflikt), kein stiller Last-Write-Wins (A-2).

## 10. Events / Outbox (F3-T8, Vertrag)

| Event | Auslöser |
|---|---|
| `ITEM_STATE_CHANGED` | Workflow-Übergang eines Items |
| `ITEM_BLOCKED` | Eintritt `blocked` (mit `blocked_reason` im Payload) |

Emission im Service in derselben Transaktion wie der Schreibvorgang (Outbox-Muster, eigene
Choices-Migration `application 0038_…` nach `0037`). Projektoren tolerieren Outbox-Zeilen ohne
`tenant_id` (O-2). Der Indexer (`application/artifact_indexer.py`) erhält `WorkItem` in seiner
Quellen-Registry.

## 11. Regeln `DOC-P5` / `DOC-P7` (F3-T8)

| Regel | Prüfung | minimal | standard | extended |
|---|---|---|---|---|
| `DOC-P5` | `in_progress`-Item ohne `last_activity_at`-Aktualisierung > X Tage (verwaister Arbeitsstand) | – | WARNING | WARNING |
| `DOC-P7` | Toter Inline-Verweis (Ziel gelöscht/archiviert) | – | WARNING | BLOCKER |

Beide laufen als RuleEngine-Regeln; die Schwere kommt aus `severity_for_tier(tier)`, nicht aus
einer zweiten Tabelle.

**Schwelle für `DOC-P5`:** Default **7 Tage** ohne `last_activity_at`-Aktualisierung, konfigurierbar
über den Preset-Schlüssel `work_item_stale_after_days` (Workspace-Preset). Der Wert ist ein
Provisionierungs-Default, kein Literal im Regel-Code; die Umsetzung liegt in F3-T8.

## 12. Abgrenzung Memory / Honcho (verbindlich)

| Frage | Zuhause | Begründung |
|---|---|---|
| „Was war / was wurde gesagt / wie tickt der Nutzer" | **Honcho/Memory** (projektorbasiert) | Gesprächs-Erinnerung, unscharf, assoziativ |
| „Wo steht das Vorhaben, was ist offen, was kommt als Nächstes" | **Loom** (`Document`/`WorkItem`) | explizit, abfragbar, verlinkt, zustandsbehaftet |

Der Übergang ist der **Digest** `/artifacts/{id}/memory/digest/` (LIVE): er fasst Dokument und
Items zusammen, Honcho zieht ihn als Kontext. **Kein neuer Speicher** — Loom schreibt keinen
Gesprächsverlauf, Memory keine Item-Zustände. Die MCP-Toolbeschreibungen von `work_item.*` und
`memory.*` nennen diese Abgrenzung wörtlich (F3-T6/T8).

## 13. Row-Level-Security (F3-T1)

- `pl_work_item` ist tenant-scoped und erhält **im selben PR** eine Policy-Migration
  (`persistence 0126_work_item_rls_policy`): `ENABLE` + `FORCE ROW LEVEL SECURITY` plus eine
  `ALL`-Policy, deren `USING`/`WITH CHECK` nur Zeilen mit
  `tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid` zulässt.
- Ein nicht gesetztes GUC matcht keine Zeile (fail-closed).
- `persistence/tests/test_rls_coverage.py` deckt die Tabelle statisch (Policy im
  Migrationsgraphen) und auf dem Liveschema (`pg_policies`, `relforcerowsecurity`) ab.
- `persistence/tests/test_work_item_model.py` prüft die Isolation zusätzlich funktional als
  App-Rolle (`SET ROLE`, Muster aus `test_document_model.py`).

## 14. Oberflächen-Vollständigkeit (F3-T4…T9)

| Oberfläche | Anforderung |
|---|---|
| Suche | Volltext über `title`/`body`, Filter auf `kind` und Zustand; A3-`_TableSpec`. |
| Artefakt-Baum | `Document` → `decomposes` → `WorkItem` → `decomposes` → `WorkItem`. |
| Baseline | WorkItems sind über das Dokument-Subtree-Subjekt erfasst; Diff zeigt Item-Zustände. |
| Attribute | `entity_type="WorkItem"` in Definition/Catalog/Defaults. |
| Kommentare | an `artifact_id` des Items (vorhandener Endpunkt). |
| Memory/Digest | Digest fasst Dokument + Items zusammen (§12). |
| Versionen/Diff | `/versions/`, `/diff/`, `/workflow-history/` über die vorhandenen Mixins. |
| Trace-Links | Item↔Requirement/Issue/Adr sowie `depends-on`; Coverage-Metriken unverändert (`verifies` bleibt exklusiv). |
| REST/MCP-Parität | `work_item.*` (F3-T6): **Delta +8 Tools, +1 Präfix `work_item`** (`create, read, query, update, transition, set_progress, checkpoint, resume`). |

## 15. Task-Schnitt und Umsetzungsstand

| Task | Inhalt | Status |
|---|---|---|
| F3-T0 | dieses Dokument + Review-Protokoll | **dieser PR** |
| F3-T1 | Modell, `persistence 0125_work_item` + `0126_work_item_rls_policy`, G1.1/G1.3-Registrierung, `ARTIFACT_TYPE_MODELS`, Tests | **dieser Auftrag** |
| F3-T2 | drei Workflow-Schemas + tier-abhängige Provisionierung + Seed-Migration | offen |
| F3-T3 | `link_types 0015_merge_work_item_pairs`, G-1/G-2 aktiv | offen |
| F3-T4 | `WorkItemService` (Resume/Checkpoint/Heartbeat, `expected_version`) | offen |
| F3-T5 | REST `/api/v1/work-items/` + ETag + Soft-Delete-Vertrag | offen |
| F3-T6 | MCP `work_item.*` | offen |
| F3-T7 | Inline-Anker-Register + Resolver + I-1…I-5 + `DOC-P7` | offen |
| F3-T8 | Events `ITEM_STATE_CHANGED`/`ITEM_BLOCKED`, `DOC-P5`, Digest-Anbindung | offen |
| F3-T9 | Frontend: Items im Dokument, Zustands-Chips, Resume-Panel, `[[`-Autovervollständigung | offen |

## 16. Testplan (F3-T1)

| Test | Prüft |
|---|---|
| `persistence/tests/test_work_item_model.py::test_create_assigns_uid_and_workspace` | Anlegen über ORM: `uid` im Format `WI-\d{3}`, `workspace` aus dem Artifact gefüllt, `version == 1`. |
| `…::test_uid_is_per_workspace_and_non_recycling` | Zwei Workspaces beginnen bei `WI-001`; ein gelöschtes Item gibt seine Nummer nicht frei. |
| `…::test_uid_unique_constraint_rejects_duplicate` | `IntegrityError` bei gleichem `(workspace, uid)`; gleiche `uid` in anderem Workspace erlaubt. |
| `…::test_kind_check_constraint` | Unbekannter `kind` wird von der DB abgewiesen. |
| `…::test_progress_range_check_constraint` | `-1` und `101` werden abgewiesen, `NULL` und `0…100` akzeptiert. |
| `…::test_artifact_cascade_deletes_work_item` | Artifact-Löschung kaskadiert auf das Item. |
| `…::test_document_protect_blocks_deletion` | `ProtectedError` beim Löschen eines Dokuments mit Items. |
| `…::test_no_status_field_and_soft_delete_lives_on_the_artifact` | Kein `status`/`item_state`-Feld; `outdated_item_ids("WorkItem")` liefert das Item nach `artifact.lifecycle_status="outdated"`. |
| `…::test_rls_hides_a_foreign_tenants_work_item` | App-Rolle: fremder Tenant unsichtbar (USING). |
| `…::test_rls_rejects_a_foreign_tenant_write` | App-Rolle: `INSERT` mit fremder `tenant_id` abgewiesen (WITH CHECK). |
| `persistence/tests/test_rls_coverage.py` | Policy + FORCE im Migrationsgraphen und Liveschema. |
| `application/tests/test_local_uid_all_paths.py::test_uid_models_and_prefixes_in_sync` | `WorkItem` in `UID_MODELS` **und** `UID_PREFIXES`. |
| `rest_api/tests/test_artifact_backing_linkability_matrix_1374.py` | `WorkItem` ist als Registry-Typ über `Issue → references` erreichbar (Wildcard-Paar, keine Ausnahme nötig). |
| `makemigrations --check` | Migrationsstand = Modellstand. |
| `migrate persistence 0124` → `migrate persistence` | Reverse-Probe der beiden neuen Migrationen. |

## 17. Risiken und offene Punkte

| # | Risiko | Umgang |
|---|---|---|
| R1 | `document`-`PROTECT` blockiert den Dokument-Löschpfad härter als erwartet. | Gewollt: Dokumente werden soft-gelöscht (`Artifact.lifecycle_status`), nie hart. Test pinnt `ProtectedError`. |
| R2 | Die Linkability-Matrix erwartet eine Factory je Registry-Typ; der Service existiert erst in F3-T4. | F3-T1 ergänzt eine **test-lokale** Factory (Dokument + Backing-Artefakt direkt über ORM), die F3-T4 durch `WorkItemService.create` ersetzt — im PR begründet. |
| R3 | `progress`-Check und Feldtyp können auseinanderlaufen. | DB-Check als Spiegel plus Test. |
| R4 | Tier-abhängige Workflows sind ohne F3-T2 nicht durchsetzbar. | Bewusst F3-T2; das Modell liefert nur die Zustands-/Progress-Spalten, die der Workflow beschreibt. |
| R5 | `ordinal` als freies Integer-Feld erlaubt Duplikate. | Bewusst: Sortierung ist `(ordinal, id)`; Eindeutigkeit wäre eine künstliche Einschränkung für Umnummerierungen. |
| R6 | ENT-F3 = a: ein späterer Wunsch nach `[[slug]]`-Speicherung wäre eine Migration. | Anker-Register speichert den Token-Text, nicht die Anzeige — ein Resolver-Wechsel bleibt damit lokal. |

## 18. Akzeptanzkriterien

**F3-T0**

- [x] Spec ist abgelegt, ENT-F3 = a explizit eingearbeitet, Review-Protokoll vorhanden.
- [x] Modellfelder, `kind`, tier-abhängige Workflows, Resume/Checkpoint/Heartbeat, I-1…I-5,
      Events, `DOC-P5`/`DOC-P7`, Memory-Abgrenzung, ETag und UID sind ohne Rückfrage lesbar.
- [x] Die Abgrenzung zu F3-T2…T9 und F5 ist explizit.

**F3-T1**

- [ ] `WorkItem` existiert in `persistence/models.py` mit `pl_work_item`, `artifact`-OneToOne,
      `document`-FK (PROTECT), `workspace`-FK, `kind`, `ordinal`, `title`, `body`, `progress`,
      `blocked_reason`, `next_action`, `last_activity_at`, `last_actor`, `evidence_ref`,
      `approved_by`, `approved_at`, `due_date`, `exit_criteria`, `uid`, geerbtem `version`.
- [ ] `persistence 0125_work_item` und `0126_work_item_rls_policy` sind im selben PR,
      `dependencies` zeigen auf `0124_document_rls_policy`; RLS ist `ENABLE`+`FORCE` und
      fail-closed.
- [ ] `WorkItem` ist in `ARTIFACT_TYPE_MODELS`, `UID_MODELS` und `UID_PREFIXES` registriert;
      `uq_work_item_workspace_uid`, `ck_work_item_kind` und `ck_work_item_progress_range`
      existieren.
- [ ] `test_work_item_model.py`, `test_rls_coverage.py` und die Linkability-Matrix sind grün;
      `makemigrations --check` ist leer; die Reverse-Probe läuft.
