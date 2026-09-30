---
type: REVIEW
scope: wp-4-data-model
status: final
date: 2026-09-29
author_agent: data-engineer
branch: chore/system-audit-2026-09
revision: 75beb750
---

# WP-4 — Tiefenaudit des Artefakt-/Datenmodells

**Prüfgegenstand:** Generic Artifact Model, Link-Typen, Baselines, State-Machines,
Rigor-Presets, Attribute-Definitions, DB-Integrität, Tenant-Isolation.
**Änderungsgrenze:** ausschließlich die beiden in diesem Bericht genannten Audit-Pfade.
Keine Code-, Konfigurations-, Migrations- oder Datenänderung. Alle DB-Zugriffe lesend.

---

## 1. Kurzurteil

**Ampel: GELB-ORANGE.** Kein Critical, kein P0-Nachweis. Aber die beiden Kernfragen des
Auftrags liefern beide ein Ergebnis, das der beworbenen Architektur widerspricht:

1. **Der Link-Typ-Katalog ist auf allen vier Ebenen konsistent** — 11 Typen, überall
   bewusst offen, kein Enum, kein `CHECK`. Das ist ein **PASS** und Gegenteil der
   Erwartungshaltung im Auftrag. Die gefundenen Abweichungen liegen in den
   *sekundären* Konsumenten, nicht in der Primärquelle.
2. **Die Rigor-Presets sind faktisch halb hartkodiert** — und die hartkodierte Hälfte
   steuert die fachlich gewichtigere Achse (Workflow-Graphen, Attribut-Stufen,
   Invarianten-Sätze). `presets/registry.py:13` („Single Source of Truth for all preset
   rule data") ist eine **nicht haltbare** Behauptung. **ADR-Kandidat.**

Dazu **4 State-Bypass-Pfade**, davon 2 unbeabsichtigt — einer davon mit
Versionsblindstelle, einer auf einem GET-Request.

**Wichtigste Einzelkorrektur an der Vor-Audit:** **`CR-08` ist widerlegt.** Die
Transition validiert im aktuellen Code **nach** dem Lock, mit expliziten `CR-08:`-Kommentaren
und Lock-Weitergabe an `perform_transition`. Der Race ist behoben.

**Zweite Korrektur:** Die `#1112`-Prämisse ist **bestätigt**, aber dreifach gesperrt
statt einfach — das macht die Umsetzung billiger als im Issue vermutet.

---

## 2. Findings

| ID | Schwere | Klassifikation | CR-Track / Issue | Ort | Kurztitel |
|---|---|---|---|---|---|
| **AUD-2026-09-325** | High | **NEU** | — | `traceability/audit/hierarchy.py:172-186`, `baseline/services.py:430`, `baseline/delta_index_builder.py:288`, `frontend/src/utils/traceEndpoints.ts:72-75` | `refines` (Built-in, Hierarchiekante) fehlt in **allen 3** Hierarchie-Definitionen |
| **AUD-2026-09-326** | High | **NEU** | — | `application/reqif_import_service.py:886-897` | ReqIF-Import umgeht Workspace-Katalog komplett |
| **AUD-2026-09-327** | High | **NEU** | — | `icd/traceability_connector.py:82-87` → `traceability/trace_link_manager.py:334` | ICD-Connector ohne Paar-Validierung |
| **AUD-2026-09-328** | Medium | **NEU** | #1104 (verwandt) | `traceability/services.py:227`, `traceability/exceptions.py:19-24`, `trace_link_manager.py:356` | Link-Typ-Zahlen 6/8/10/11 im **Code** |
| **AUD-2026-09-154** | Medium | **NEU** | — | `traceability/types.py:76`, `trace_link_manager.py:62-73`, `traceability/services.py:65,472` | `VALID_LINK_TYPES` als Nicht-Autorität deklariert, als API re-exportiert, im ReqIF-Import **benutzt** |
| **AUD-2026-09-155** | Medium | **NEU** | CR-09 (anderer Store) | `lt_workspace_definition` (live) | Orphan-Workspace mit 8 statt 11 Keys |
| **AUD-2026-09-156** | Low | **NEU** | — | `link_types/migrations/0008_…py:83` | Datenmigration ohne Re-Run; 401 statt 402 |
| **AUD-2026-09-157** | Medium | **NEU** | CR-15 (anderer Punkt) | `traceability/trace_link_manager.py:372-392` | Zyklusprüfung **pro** Link-Typ; Self-Link nirgends abgelehnt |
| **AUD-2026-09-158** | Info | **NEU** | — | live gemessen | 4 von 11 Link-Typen haben 0 Links (PASS-Kontext) |
| **AUD-2026-09-159** | Info | **PASS** | — | 4-Ebenen-Matrix | Primärkatalog auf DB/REST/MCP/FE konsistent offen |
| **AUD-2026-09-160** | High | **NEU** | ADR-Kandidat | `presets/registry.py:13` vs. 6 Module | SSOT-Behauptung falsch; 7 datengetrieben / 5+ hartkodiert |
| **AUD-2026-09-161** | High | **NEU** | — | `attribute_definitions/stage_matrix.py:40-47` | `stage_mandatory` geseedet, **null** Produktionskonsumenten |
| **AUD-2026-09-162** | High | **NEU** | — | `presets/gate.py:536-549` | Downgrade-Blocker ist **fail-open** (`except Exception: pass`) |
| **AUD-2026-09-163** | Medium | **NEU** | — | live gemessen | 0 Workspaces auf `minimal` → alle `minimal`-Zweige ungetestet |
| **AUD-2026-09-164** | Low | **NEU** | #940 (geschlossen) | `attribute_definitions/stage_matrix.py:40-44` | Docstring zitiert **geschlossenes** Issue #940 als offenen Blocker |
| **AUD-2026-09-165** | Info | **PASS** | — | live GET | Presetwechsel auf Workflow-Achse nachweisbar wirksam (1/5/9 Transitions) |
| **AUD-2026-09-166** | — | **WIDERLEGT (CR-08)** | CR-08 | `workflow/services.py:302-341`, `lifecycle_manager.py:246-289,354` | Transition validiert **nach** dem Lock — Race behoben |
| **AUD-2026-09-167** | High | **NEU** | — | `application/import_service.py:714-722` | CSV-Import schreibt `current_state` ohne Transition, History, Version |
| **AUD-2026-09-168** | High | **NEU** | — | `application/reqif_import_service.py:791-793` | ReqIF-Import ändert `current_state` **ohne `version`-Bump** → CAS-Blindstelle |
| **AUD-2026-09-169** | High | **BESTAETIGT (CR-07) + NEU** | CR-07 | `application/interview_service.py:337-344, 354-369` | GET mutiert Zustand; `except Exception`; Status nie persistiert; `version` ohne State-Änderung |
| **AUD-2026-09-170** | Medium | **NEU** | — | `workflow/lifecycle_manager.py:416-477` | `force_transition` ohne Rolle/Signatur/Reason-Gate; 2 veraltete Docstrings |
| **AUD-2026-09-171** | Medium | **NEU** | — | `we_item_state` (live) | Kein `CHECK (current_state ∈ states(definition))`, kein FK auf `workspace_id` |
| **AUD-2026-09-172** | Medium | **NEU** | — | `workflow/definition_store.py:660-662`, `transition_validator.py:350-357` | `state_meta` modelliert nur `is_outdated_equivalent`, **keine** Terminal-Semantik |
| **AUD-2026-09-173** | Medium | **NEU** | — | `bl_baseline_snapshot` (live) | `global`-Scope: 0 Snapshots live → Codepfad unverifiziert |
| **AUD-2026-09-174** | Info | **PASS** | — | live gemessen | Scope-Trennung tenant-seitig sauber; 0 Cross-Tenant/Cross-WS TraceLinks |
| **AUD-2026-09-175** | Low | **NEU** | — | `presets/registry.py:129` | `known_scopes` = 2. hartkodierte Scope-Liste neben `PresetConfig` |
| **AUD-2026-09-176** | Medium | **BESTAETIGT #1112** | #1112 | `bootstrap_attribute_definitions.py:309, 1247-1252` | Ohne `--reset` wird `kind` **nie** geändert — **dreifach** gesperrt |
| **AUD-2026-09-177** | Medium | **NEU** | — | `attribute_definitions/schema.py:15` vs. `stage_matrix.py:48-53` | `ATTRIBUTE_KINDS` = 2 Werte, Docstring beschreibt 5 Carrier |
| **AUD-2026-09-178** | Medium | **NEU (BLOCKED-Anteil)** | — | live gemessen | 3/11 Item-Types materialisieren nie; 134/401 Workspaces ohne Attribut-Katalog |
| **AUD-2026-09-179** | Medium | **NEU** | CR-10 (anderer Store) | `bootstrap_attribute_definitions.py:994-1034` | Kein `--dry-run`, kein Undo für einen destruktiven Befehl |
| **AUD-2026-09-180** | High | **NEU** | — | 26 von 44 Tabellen | `workspace_id` **ohne FK** — inkl. `pl_artifact`, `pl_requirement` |
| **AUD-2026-09-181** | High | **NEU (H-Anteil)** | #1093 (geschlossen) | `persistence/migrations/0093_…py:76-78` + 99 Live-Zeilen | Datenmigration nicht nachgelaufen; Tag-Rückstände in 30 lebenden Links |
| **AUD-2026-09-182** | Low | **NEU** | — | `pl_tracelink` (live) | `link_type` ohne CHECK an den Katalog gebunden |
| **AUD-2026-09-183** | Medium | **NEU** | CR-36 (Nachbar) | Migrationskette | Kein Mechanismus erkennt „Datenmigration lief, Daten wurden zurückgesetzt" |
| **AUD-2026-09-184** | Medium | **BESTAETIGT (CR-17)** | CR-17 | `application/models.py:44,147,170,204`, `baseline/models.py:116` | 5 Modelle ohne `tenant_id` **und** ohne RLS (Vor-Audit nannte 2) |
| **AUD-2026-09-185** | Info | **PASS** | — | live gemessen | 29/31 `pl_*`-Tabellen mit RLS; **0** `.raw()` im Produktions-Backend |
| **AUD-2026-09-186** | Medium | **NEU** | — | 263 Verwendungen | `.unscoped` gegen 0 Constraints an 5 zentralen Tabellen |
| **AUD-2026-09-187** | Medium | **NEU** | — | `search_service.py:183-250`, `attribute_definitions/schema.py:22`, `pl_artifact` | Drei parallele, auseinanderlaufende Entity-Typ-Registries (11 / 10 / 13) |
| **AUD-2026-09-188** | Info | **NEU** | — | live gemessen | 99 `TestCase:*`-Tags = 3,2 % des Artefaktbestands |
| **AUD-2026-09-189** | Low | **NEU** | #801 (Nachbar) | `frontend/src/utils/artifactRoutes.ts:31` | Getaggte `TestCase:*` haben keinen Frontend-Router |
| **AUD-2026-09-190** | — | **BLOCKED** | CR-16 (Nachbar) | `baseline/diff_engine.py:109-177` | Diff-Engine-Korrektheit ohne Mutation nicht messbar — **kein PASS** |

**Zählung:** 41 IDs vergeben (154–190, 325–328). **11 High**, 17 Medium, 5 Low, 6 Info/PASS,
1 WIDERLEGT, 1 BLOCKED.
Reconciliation: **32 NEU**, 2 BESTÄTIGT (176 → #1112, 184 → CR-17), 1 gemischt
(169 → CR-07 bestätigt **plus** vier neue Defekte), 4 PASS, 1 WIDERLEGT, 1 BLOCKED.

---

## 3. Antworten auf die acht Auftragsfragen

### 3.1 Generic Artifact Model — generisch in den Daten, hartkodiert in den Namen

**Antwort: Das Datenmodell ist generisch. Die Typenverwaltung ist es nicht.**

13 `artifact_type`-Werte in 3062 Artefakten. Ein `pl_artifact` mit `custom_fields`-JSON
plus je Typ eine schmale typed Extension-Tabelle (`as_*`, `pl_requirement`,
`pl_stakeholder_need`, `icd_icd`, `pl_testcase`).

Aber es gibt **drei parallele Registries**, von denen keine aus der anderen abgeleitet ist:

| Registry | Ort | Umfang |
|---|---|---|
| Attribut-Definitionen | `attribute_definitions/schema.py:22` `ITEM_TYPES` | **11** |
| Suche / MCP-Enum | `application/search_service.py:183-244` `_TABLE_SPECS` | **10** |
| tatsächliche Daten | `pl_artifact.artifact_type` | **13** |

Live-Konsequenz: 124 `Icd`-, 111 `Diagram`- und 9 `Interview`-Artefakte sind
**über MCP-Suche nicht auffindbar**, obwohl `search_service.py:248-250` sich als
„single source of truth" für den MCP-`type_filter`-Enum deklariert.

Die *Daten* (Attribut-Definitionen, Workflow-Graphen, Link-Paare) sind sauber
datengetrieben und pro Tenant materialisiert. Die *zulässigen Namen* stehen an 5+
Stellen hartkodiert. Das ist der übliche Zuschnitt — aber es ist die Ursache der
messbaren Abweichung.

→ AUD-187, AUD-188, AUD-189.

### 3.2 Link-Typen — End-to-End-Konsistenz

**Verifizierte Zahl: 11.** Eigenzählung aus `backend/link_types/builtin.py:78`, bestätigt
durch Enum (`traceability/types.py:44-67`), ReqIF-Exporter (`reqif_export_service.py:71-72`),
Frontend (`traceLinkLabels.ts:42-87`) und Live-DB (11 Keys je Tenant).

**Die 4-Ebenen-Matrix — alle vier Ebenen konsistent, kein Enum:**

| Ebene | Ort | Repräsentation | Abweichung |
|---|---|---|---|
| (a) DB | `pl_tracelink.link_type` | `character varying`, kein Enum, kein CHECK | **keine** (offen = korrekt) |
| (a) DB-Katalog | `lt_*_definition.definition_json` | JSONField, `key` varchar(64) | 1 Orphan mit 8 statt 11 |
| (b) REST | `serializers.py:1394` | `CharField(max_length=64)` | **keine** |
| (b) OpenAPI | live, 4 Felder | `type: string, maxLength: 64` | **keine** |
| (c) MCP | `tools/cross_cutting.py:291-299`, `tools/architecture.py:265-274` | `type: string` + „call link_type.list" | **keine** |
| (d) FE-Typ | `types/index.ts:324` | `export type LinkType = string` | **keine** |
| (d) FE-Labels | `traceLinkLabels.ts:42-87` | Fallback-Tabelle, 11 | **keine** |

**Alle Konsistenz-Abweichungen zwischen den Ebenen — und sie liegen woanders:**

| Abweichung | Ort | Art |
|---|---|---|
| 3 Hierarchie-Listen ohne `refines` | `hierarchy.py:172-186`, `baseline/services.py:430`, `delta_index_builder.py:288`, `traceEndpoints.ts:72-75` | **semantisch** |
| Docstring sagt `derives-from`/`refines`, SQL sagt nur `derives-from` | `baseline/services.py:324` vs. `:430`; `delta_index_builder.py:262,272` vs. `:288` | **Doku vs. Code, dieselbe Datei** |
| `hierarchy.py:34-38` behauptet „`refines` no longer exists" | Stand vor #950 | **veraltet** |
| Zahlen 6/8/10/11 | `services.py:227` (8), `exceptions.py:19-24` (10, nennt 10 **retired** Keys), `trace_link_manager.py:356` (8) | **Doku** |
| `VALID_LINK_TYPES` re-exportiert + benutzt | `services.py:65,472`; `reqif_import_service.py:886` | **Autoritätswiderspruch** |

**Tenant-Extensibility: funktioniert.** Materialisierter Tenant-Katalog, `UNIQUE`-Constraints
vorhanden, `source_global` mit `SET_NULL`, REST + MCP + UI vollständig. Eine Lücke: ein
Orphan-Workspace mit 8 Keys.

**Regeln werden NICHT überall durchgesetzt.** `validate_link_pair` hat **genau eine**
Produktionsaufrufstelle (`trace_link_service.py:365,388`). Drei Bypass-Pfade:
ReqIF-Import (High), ICD-Connector (High), Diagram-Reconciler (korrekt, `manual=False`).
Zyklusprüfung ist **pro Link-Typ**; Self-Links werden nirgends abgelehnt.

→ AUD-325, AUD-326, AUD-327, AUD-328 (frühere Nummern 150–153).

### 3.3 Rigor-Presets — halb datengetrieben, halb hartkodiert

**Antwort: 12 relevante Achsen, davon 7 datengetrieben und 5+ hartkodiert in mindestens
6 voneinander unabhängigen Modulen.**

| Achse | datengetrieben? | wirksam? |
|---|---|---|
| 5 Feature-Flags, `mandatory_fields`, `baseline_scopes`, `workflow_configurability`, `change_reason` | **ja** (`PresetConfig`, `_DEFAULT_REGISTRY`) | ja |
| **Workflow-Graph** (`definition_store.py:715`) | **nein** — separate Tabelle | **ja** |
| **Attribut-Stufen** (`stage_matrix.py:64-68`) | **nein** — separate Tabelle | **nein** |
| **Architektur-Invarianten** (`validators.py:55`) | **nein** — separate Tabelle | ja |
| **SE-Audit-Regeln** (`traceability/audit/registry.py`) | **nein** — separate Tabelle | ja |
| Tier-Mitgliedschaft (`transition_validator.py:58`) | **nein** | ja |
| `proposed`-Ausnahme (`definition_store.py:628`) | **nein** | ja |
| N1-Sperre (`architecture_decompose_service.py:351`) | **nein** — Magic String | ja |
| Downgrade-Blocker (`gate.py:536`) | **nein** — Magic-Tupel | **schwach (fail-open)** |

`presets/registry.py:13` („Single Source of Truth for all preset rule data (ADR-04)")
ist damit **nicht haltbar** — die Behauptung gilt nur für `PresetConfig`.

**Zählung:** 116 Vorkommen von `minimal` in 51 Dateien (ohne Tests), davon 3
funktionale `if preset == …`-Vergleiche. **Kein** `settings.RIGOR_LEVEL` im Code (0 Treffer) —
das ist zugunsten des Projekts: die Rigor-Entscheidung fließt über genau eine Spalte.

**Wirksamkeit — live, read-only, ohne Mutation:**

| item_type/preset | states | transitions |
|---|---|---|
| `Requirement/minimal` | 2 | 1 |
| `Requirement/standard` | 5 | 5 |
| `Requirement/extended` | 8 | 9 |

Der Wechsel ist auf der **Workflow-Achse** (Graph, Rollen, Change-Reason-Pflicht)
nachweisbar wirksam. Auf der **Attribut-Achse** ist er es **nicht**:
`stage_mandatory` wird geseedet, hat aber **null** Produktionskonsumenten.

**ADR-Kandidat:** `AUD-2026-09-160` ist der formale Anker (falsche SSOT-Behauptung),
`AUD-2026-09-161` der Wirksamkeitsbeleg, `AUD-2026-09-162` der Sicherheitsbeleg.

### 3.4 State-Machines — 4 Bypass-Pfade

**Antwort: 4 vollständige Bypass-Pfade** (2 designiert, 2 unbeabsichtigt) + 1
Lese-Pfad mit Schreibnebenwirkung.

| # | Pfad | Ort | Klassifikation |
|---|---|---|---|
| S4 | `force_transition` — designierter Escape-Hatch | `lifecycle_manager.py:452-454` | **designiert** (D-1/D-3) |
| — | via `InterviewService._lazily_abandon_if_stale` | `interview_service.py:337-344` | **CR-07 + NEU** |
| S5 | CSV-Bulk-Import | `import_service.py:714-722` | **unbeabsichtigt** |
| S6/S7 | ReqIF-Import (Update- und Create-Pfad) | `reqif_import_service.py:791-793`, `:795-802` | **unbeabsichtigt** |

**Legitim:** `lifecycle_manager.py:378-384` (der einzige kanonische Write, CAS-geschützt),
`:141-147` und `:230-236` (Initialisierung — „a plain initialization is not a transition",
`:154-156`).

**Die gravierendsten Einzelbefunde:**

1. **Ein GET mutiert Zustand.** `interview_service.py:295-369` wird aus `_get_session`
   (`:293`) aufgerufen, nimmt einen `SELECT … FOR UPDATE` (`:448`) und kann
   `current_state` umschreiben.
2. **`except Exception:`** (`:354`) fängt nicht nur „kein `WorkflowItemState`" (die
   Begründung `:355-362`), sondern `ValidationError`, `DatabaseError` und jeden Bug —
   degradiert zu `logger.debug` (`:363`).
3. **Der Fallback persistiert den Status nicht** (`:367`). Die `status`-Spalte wurde
   gedroppt; `current_state` ist der einzige Store. Der Client bekommt `"abandoned"`,
   ein Folge-GET liefert `in_progress`.
4. **`version` wird erhöht, ohne dass sich der State ändert** (`:368-369`) — reproduzierbarer
   409 bei inhaltlich leerem Übergang, bei **jedem** veralteten Read.
5. **ReqIF-Import ohne `version`-Bump** (`:793`). Das ist die kritischste Einzelbeobachtung:
   `perform_transition` garantiert `version+1` in derselben Transaktion
   (`lifecycle_manager.py:378-384`) und `WorkflowFacade.transition` beantwortet einen
   veralteten `expected_version` mit 409 (`services.py:318-323`). Der Import verändert
   `current_state`, ohne `version` zu berühren — ein Client, der `expected_version=N`
   gelesen hat, bekommt seinen 409 **nicht** und überschreibt den Import statt ihn zu
   erkennen. **Lost Update mit gestrichener Versionshistorie.**

**Validierung gegen Workspace-Definition oder global?** Gegen die **Workspace-spezifische**
Definition — `transition_validator` bekommt `ValidationRequest(workspace_id=…)`
(`services.py:335-339`), und `GlobalWorkflowDefinition`-Änderungen propagieren in
abgeleitete Rows (`global_definition_store.py`). Korrekt.

**CR-08: WIDERLEGT.** `services.py:302-341` macht `transaction.atomic()` (`:306`) →
`lock_item_state` (`:308`, echtes `select_for_update`, `lifecycle_manager.py:246-289`) →
Versionsprüfung (`:318`) → Graph-Validierung gegen den **gelockten** Zustand (`:335`) →
Write (`:362`). `perform_transition` bekommt den gelockten Row übergeben (`:354`),
kein zweiter Lock. Die Reihenfolge ist korrigiert, mit `CR-08:`-Kommentaren an beiden
Stellen. *Verbleibender Rest:* `perform_transition(item_state=None)` ist ein dokumentiert
unterstützter Pfad (`:330-331`), der die korrigierte Reihenfolge umgehen würde — heute
nicht produktiv, aber ohne Linter-Wächter.

**Terminale Endzustände:** `state_meta` **ist** ein echter, konsumierter Mechanismus
(`services.py:1096-1147`, `goal_service.py:512`, `ai_derivation_service.py:1694`) — aber
er trägt ausschließlich `is_outdated_equivalent` (Sichtbarkeit), nicht Terminalität.
`terminal_validator.py:350-357` prüft nur `from → to ∈ transitions`. Der einzige
graph-theoretisch terminale Zustand ist `rejected`.

**Live-Bilanz:** 3316 Zustandszeilen, 175 History-Einträge, **0** Zustände außerhalb der
deklarierten States ihrer Definition (die `_map_status`-Normalisierung greift), **0**
Cross-Tenant-TraceLinks, 58 von 401 Workspaces ohne jede Zustandszeile.

### 3.5 Baselines — 3 Scopes, konsistent, aber `global` ungenutzt

**Die Zahl 3 stimmt** mit ADR-07 überein, über alle Ebenen. `AGENTS.md` ist hier korrekt.

Alle drei Scope-Zweige in `baseline/services.py:370-451` tragen einen `tenant_id`-Filter
(`:374, 384, 402`) — `global` **muss** das tun, weil es per Definition workspace-
übergreifend ist. Live: **0** Cross-Tenant- und **0** Cross-Workspace-TraceLinks, also
kein Scope-Leak auf Tenant-Ebene.

`global` ist aber nur in `extended` verfügbar (`registry.py:214`), `standard` hat
`("document","project")` (`:182`), `minimal` hat `()` (`:166`). Und: **0 `global`-Snapshots**
auf der Live-Instanz (17 document, 21 project). Der Codepfad ist damit **nicht ausgeführt
verifiziert**.

**Diff-Engine-Stichprobe: BLOCKED.** `diff_engine.py` wurde nicht ausgeführt (kein Testlauf,
keine Mutation). `CR-16` unbestätigt, unbestritten. Ausdrücklich **kein PASS**.

### 3.6 Attribute-Definitions — `#1112`-Prämisse **BESTÄTIGT**

**Antwort: JA, ein Lauf ohne `--reset` ändert das `kind` einer bestehenden Definition nicht.**

**Terminologie:** Der Issue-Titel sagt `field_kind`. Diese Zeichenkette existiert
**nirgends** im Repo (0 Treffer in `backend/**/*.py`, keine DB-Spalte). Gemeint ist die
**`kind`-Property** eines Attribut-Eintrags im `definition_json`. Live: `core` 1488,
`extended` 660, Schema-Werte `ATTRIBUTE_KINDS = {"core","extended"}` (`schema.py:15`).

**Der Codepfad — dreifach gesperrt, jede Sperre je für sich ausreichend:**

| # | Sperre | Ort |
|---|---|---|
| 1 | `kind` ∉ `RELABEL_KEYS = ("label","help_text")` | `:309` |
| 2 | Der Diff-Key ist `name`, nicht `kind`: `additions = [... if a["name"] not in known]` | `:1248-1249` |
| 3 | `if not additions: return False` — bei identischem Attributsatz wird **gar nichts** geschrieben (kein `save()`, kein `version`-Bump, keine Propagation) | `:1250-1251` |

Der `else`-Zweig ohne `--reset` (`:1092`) ruft **genau** diese zwei Methoden auf.

**Was der einzige schreibende Pfad kostet:** `store.reinitialize()` (`:1086`) — und
`:1144-1146` nennt den Preis selbst: *„`--reset` also fixes the data but **documentedly
DESTROYS every admin customization of the global rows**."*

**Reconciliation: BESTÄTIGT #1112**, mit zwei Präzisierungen: (a) das Feld heißt `kind`;
(b) die Sperre ist **dreifach**, nicht einfach — die Umsetzung ist billiger als im
Issue-Body vermutet.

**Die gefragten Nebenbedingungen:**

| Prüfpunkt | Ergebnis |
|---|---|
| Idempotenz | **JA**, alle drei Modi (`:1153-1156`, `:1250-1251`) |
| Transaktionsgrenze | **JA** — eine äußere `:1063` um Tenant × ItemType × Preset; `_propagate` liegt innerhalb |
| Teilfehler | **Kein Halbschreiben** — alles oder nichts |
| **Rollback-Pfad** | **NEIN** — kein `--dry-run`, kein Undo. Nach dem Commit ist die alte `definition_json` **nicht rekonstruierbar** |

### 3.7 Datenintegrität — 26 Tabellen ohne `workspace_id`-FK

**44 Tabellen haben eine `workspace_id`-Spalte. 26 haben keinen FK auf `pl_workspace`** —
darunter `pl_artifact`, `pl_requirement`, `we_item_state`, `we_history_entry`,
`bl_baseline_snapshot`, `lt_workspace_definition`, `ad_workspace_definition`.

Die Inkonsistenz ist real und bidirektional: `pc_workspace_preset_config` (der Preset-Speicher)
**hat** einen FK, der Attribut- und Link-Typ-Katalog derselben Produktidee **nicht**.

**Zwei live gemessene Orphans** — der Beweis, dass die Lücke real befüllt wird:

| Orphan | Ergebnis |
|---|---|
| `lt_workspace_definition` → nicht existierender Workspace | **1** (mit 8 statt 11 Keys) |
| `we_item_state` → nicht existierender Workspace | **1** |

Sauber dagegen: `pl_artifact` (0), `pl_requirement` (0), `we_item_state` → Definition (0).

**Migrationskette:** 294 Migrationen. `persistence.0093` (2026-09-15) hat den
**unbedingten** Forward-Schritt `filter(artifact_type__istartswith="TestCase:").update(...)`
(`:76-78`) — und trotzdem tragen **99 Zeilen** live den Tag (69 `TestCase:Unit` vom
2026-09-14, 30 `TestCase:System` vom 2026-09-10), von denen **30 Quelle eines lebenden
TraceLinks** sind.

*Belegt:* (1) `0093` ist als ausgeführt verzeichnet; (2) die Zeilen sind **älter** als der
Commit; (3) kein aktueller Pfad schreibt den Tag; (4) die globale
`Requirement/extended`-Workflow-Definition trägt `updated_at: 2026-09-10T21:15:37Z`.
*Hypothese (nicht bewiesen):* Restore oder Reseed nach dem Migrationslauf. Django-Daten-
migrationen laufen **nie** erneut, und `django_migrations` kennt den Zustand nicht.

Die Migration behauptet in `:27-28` *„no read path depends on the tag any more"* — das ist
falsch; **4** Read-Pfade hängen real daran (`link_types/catalog.py:40-48`,
`coverage_calculator.py`, `artifact_diff_service.py`, `traceEndpoints.ts:97-99`).

**Vorhandene Constraints (live aus `pg_constraint`) — nicht zu beanstanden:**
`we_item_state` PK + `UNIQUE (tenant_id, item_id, item_type)` + 3 FKs;
`pl_tracelink` PK + `UNIQUE (source_id, target_id, link_type)` + 5 FKs;
`lt_*` / `ad_*` je PK + `UNIQUE` + FKs; `bl_baseline_snapshot` PK + `UNIQUE (workspace_id, name)`.

**Fehlend:** `CHECK (current_state ∈ states(definition))` auf `we_item_state`;
CHECK-Bindung von `pl_tracelink.link_type` an den Katalog.

**Frische vs. gefüllte DB:** `migrate` auf frischer DB ist **BLOCKED** (Auftragsverbot).
Auf gefüllter DB **nicht nachweisbar** — 0093 hat seinen Zweck nicht erreicht.

### 3.8 Tenant-Isolation auf Modellebene — zwei PASS, eine Bestätigung

**PASS: 0 `.raw()`-Aufrufe** im Produktions-Backend (`rg -o "\.raw\(" … --glob "!**/tests/**"`
→ 0 Treffer). Keine Ausnahme, keine Ausrede.

**PASS: Manager-Struktur konsistent.** `TenantScopedModel` (`persistence/models.py:446`)
mit `objects = TenantManager()` / `unscoped = UnscopedManager()` (`:464-465`).
Alle 55 Model-Klassen in `persistence/models.py` erben korrekt. **Kein Modell mit
fehlendem Manager.**

**PASS: RLS-Abdeckung 29/31** `pl_*`-Tabellen; Ausnahmen `pl_tenant` und `pl_user`.

**BESTAETIGT (CR-17): 5 Modelle ohne `tenant_id` und ohne RLS** (Vor-Audit nannte 2):
`DomainEventOutbox` (`application/models.py:44`), `DomainEventDLQ` (`:147`),
`WebhookSubscription` (`:170`), `WebhookDeliveryLog` (`:204`), `BaselineDeltaIndexEntry`
(`baseline/models.py:116`). Für `se_metrics` (`:41, :92`) existiert eine dokumentierte
Begründung (`se_metrics/models.py:16-26`) — für die anderen fünf nicht.

**Die Verteilungsfrage:** 263 `.unscoped`-Verwendungen in Produktion gegen **0**
FK-Constraints an 5 zentralen Tabellen. `unscoped` mit explizitem `tenant_id`-Filter
ist das dokumentierte Muster (`link_types/catalog.py:15-19` beschreibt es als Vorlage)
— aber diese Menge ist mit einem einzelnen Ratchet nicht fassbar.

---

## 4. Top-5

| # | ID | Warum zuerst |
|---|---|---|
| **1** | **AUD-2026-09-168** | ReqIF-Import ändert `current_state` **ohne `version`-Bump**. Heißt: der Optimistic-Lock-Vertrag, den `WorkflowFacade.transition` als 409-garantie dokumentiert, hat ein Loch. Ein Client überschreibt den Import stillschweigend, und der Audit-Trail zeigt nichts. Einziger Befund mit **stillem Datenverlust bei korrektem Client**. |
| **2** | **AUD-2026-09-169** | Ein **GET** nimmt eine Schreibsperre und kann Zustand umschreiben; `except Exception` verschluckt echte Fehler; der gelieferte Status wird nie persistiert. Fünf Defekte, ein 25-Zeilen-Block, auf dem produktiver Leseverkehr liegt. |
| **3** | **AUD-2026-09-160 + -161** | `PresetRegistry` beansprucht SSOT für **alle** Preset-Daten und ist es für die fachlich gewichtigste Achse nicht (Workflow-Graphen, Attribut-Stufen, Invarianten liegen in 6 getrennten Tabellen). `stage_mandatory` hat null Konsumenten — die Stufen-Differenzierung ist auf Attributebene **nicht wirksam**. **ADR-Kandidat.** |
| **4** | **AUD-2026-09-180** | 26 von 44 Tabellen mit `workspace_id` haben keinen FK, darunter `pl_artifact` und `pl_requirement`. Zwei Orphans sind **live**. Die Tenant-Isolation hängt zu 100 % am Applikationscode; die DB schützt nichts. |
| **5** | **AUD-2026-09-325** | `refines` ist ein Built-in, der laut eigener Definition eine Hierarchiekante ist, aber in **allen** drei Hierarchie-Definitionen fehlt. Betrifft `Requirement.level` (ADR-005), TRACE-P1/VERIF-P8 und den Baseline-`document`-Scope. Dazu zwei Docstrings, die `refines` als unterstützt *behaupten* — im selben Modul wie die Queries, die es ignorieren. |

**Nah am Schneider:** AUD-162 (fail-open Downgrade-Blocker) und AUD-326/AUD-327
(Link-Typ-Validierungs-Bypässe über Import und ICD-Connector).

---

## 5. Reconciliation gegen die Vor-Audit

| Track | Disposition | Kurz |
|---|---|---|
| `CR-08` | **WIDERLEGT** | Lock-Reihenfolge korrigiert (`services.py:302-341`). Race-Anteil entfallen. |
| `CR-07` | **BESTAETIGT + verschärft** | `interview_service.py:337` (`force_transition`) und `:354` (`except Exception`). Punkt „fehlender History-Eintrag" **teilweise widerlegt** — `force_transition:460-469` schreibt ihn. |
| `CR-17` | **BESTAETIGT, erweitert** | 2 → 5 Modelle ohne `tenant_id`/RLS. Codepfade unverändert. |
| `CR-16` | **BLOCKED** | DiffEngine nicht ausgeführt. Kein PASS. |
| `CR-36` | **Nachbar, unvollständig** | `makemigrations --check` ist nicht der Drift-Mechanismus, der fehlt (AUD-183). |
| `CR-09` | **getrennt** | Mein AUD-155 betrifft `lt_workspace_definition`, nicht `workflow/global_definition_store.py`. Gleiche Fehlerklasse, anderer Store. |
| `CR-15` | **getrennt** | Mein AUD-325/AUD-157 betrifft Hierarchie-Semantik und den create-Pfad, nicht den Update-/Batch-Zyklusvertrag. |
| `CR-13` | **nicht berührt** | Workspace-Sprachspaltung liegt außerhalb des WP-4-Auftrags. |
| `AUD-2026-09-120` | **nicht bestätigt** | Die Celery-4×-Zustellung (WP-1c) hat hier keine Daten-Wirkung gezeigt; kein Duplikat, kein Widerspruch. |
| `AUD-2026-09-070/071` | **berührt, nicht dupliziert** | Der ReqIF-Import ist in AUD-070/071 als **Round-Trip** beanstandet; mein AUD-326/AUD-168 betrifft den Import als **Validierungs- und Versionspfad**. Verschiedene Defekte, gemeinsamer Codepfad, getrennte Track-Nummern. |
| `AUD-2026-09-092` | **verwandt, nicht dupliziert** | `uid`-Backfill-Lücke ≠ `TestCase:*`-Tag-Rückstände (AUD-181). Beide sind „Datenmigration nicht nachgelaufen", unterschiedliche Migrationen. |
| `#940` | **WIDERLEGT** (wie im Auftrag) | Geschlossen, Daten-Migration. Der Metadaten-Defekt ist **#1112** — **bestätigt** (AUD-176). |
| `#1093` | **geschlossen, betrifft die andere Seite** | Schema-Normalisierung; mein AUD-181 ist der Instanz-Datenbestand. |

---

## 6. Empfohlene Reihenfolge

1. **Korrektheit vor Erweiterung:** AUD-168 (Version-Bump im ReqIF-Import),
   AUD-169 (Read-Mutation + Exception-Swallow), AUD-167 (CSV-Import-Validierung).
2. **Regel-Durchsetzung schließen:** AUD-326, AUD-327 (beide Bypässe auf
   `validate_link_pair` umleiten), AUD-157 (Self-Link + Union-Zyklus für tenant-Typen).
3. **Datenmodell-Kohärenz:** AUD-160 + -161 als **ein** ADR (Preset-SSOT),
   AUD-325 (3 Hierarchie-Listen zusammenführen, `refines` entscheiden).
4. **DB-Defense-in-Depth:** AUD-180 (`workspace_id`-FKs an den 26 Tabellen, priorisiert
   `pl_artifact`/`pl_requirement`/`we_item_state`), AUD-171 (CHECK auf `we_item_state`),
   AUD-183 (Drift-Detektor für Datenmigrationen).
5. **Datenqualität nachziehen:** AUD-181 (die 99 Tags bereinigen — die 4 abhängigen
   Read-Pfade sind der Grund, warum das nicht trivial ist), AUD-155 (Orphan aufräumen),
   AUD-178 (Attribut-Provisioning-Gap klären), AUD-173 (`global`-Scope braucht echte Daten).

---

## 7. Abschlussstatus

```text
STATUS: done
RESULT: WP-4 hat 41 Findings (11 High) gegen Generic Artifact Model, Link-Typen,
Baselines, State-Machines, Rigor-Presets, Attribute-Definitions, DB-Integrität und
Tenant-Isolation geliefert. Zwei Kernkorrekturen: CR-08 (Transition validiert nach dem
Lock — Race behoben, WIDERLEGT) und die #1112-Prämisse (BESTÄTIGT, dreifach gesperrt).
Der Link-Typ-Katalog ist über alle vier Ebenen konsistent offen (PASS); die gefundenen
Abweichungen liegen in den sekundären Konsumenten. Die Rigor-Presets sind halb hartkodiert
— ADR-Kandidat. Vier State-Bypass-Pfade, zwei davon mit Datenverlust bei korrektem Client.
RECONCILIATION: 32 NEU, 2 BESTAETIGT, 1 gemischt, 4 PASS, 1 WIDERLEGT, 1 BLOCKED.
ARTIFACTS: docs/audit/2026-09/AUDIT_DATA_MODEL.md
           docs/audit/2026-09/AUDIT_EVIDENCE/wp4-evidence-index.md
           docs/audit/2026-09/AUDIT_EVIDENCE/wp4-link-type-4level-matrix.md
           docs/audit/2026-09/AUDIT_EVIDENCE/wp4-state-bypass-inventory.md
           docs/audit/2026-09/AUDIT_EVIDENCE/wp4-preset-hardcoding-inventory.md
           docs/audit/2026-09/AUDIT_EVIDENCE/wp4-bootstrap-fieldkind-proof.md
           docs/audit/2026-09/AUDIT_EVIDENCE/wp4-constraints-and-migrations.md
           docs/audit/2026-09/AUDIT_EVIDENCE/wp4-baseline-and-artifact-model.md
NEXT: Review; dann Developer-Implementierung (Reihenfolge §6), Tests an tester,
ADR-Erstellung für AUD-2026-09-160 an se-architect
```
