---
type: Spec
title: "Ordnung und Allokation — Gesamtkonzept (P0–P6)"
status: draft
date: 2026-11-04
author_agent: claude (Sonnet 5.5), gemeinsam mit dem Product Owner erarbeitet
language: de
issues: ["#1670", "#1669", "#1668", "#1660"]
supersedes_in_part: ["#1670 (Stufen 3 und 4, Entscheidungen D9 bis D12, D16, D17)"]
evidence: ".tmp/analysis/{backend,frontend,allocation-gap}.md (Stand origin/main e7de2215); Belege stehen im Text als `pfad:zeile`"
---

# Ordnung und Allokation — Gesamtkonzept

> **Status: Entwurf zur Freigabe.** Vorschläge, die der Product Owner noch nicht bestätigt hat, sind mit **[Vorschlag]** markiert.
> Alles andere ist im Gespräch vom 2026-11-04 entschieden (inkl. O1, O2, O3, O5). Umsetzungsplan:
> `docs/superpowers/plans/2026-11-04-ordnung-allokation.md`.

## 1. Ziel

Requirements und Architekturelemente sollen **ordentlich sortierbar** sein, und die **Zuordnung Requirement → Architekturelement** (Allokation)
soll ein belastbarer Kern des Systems werden, mit mehreren Darstellungsformen darauf. Arbeitsweg des Nutzers: Er ordnet die Requirements im
Requirements-Baum, ordnet die Architektur im Architektur-Baum und **allokiert** Requirements auf Architekturelemente. Dazu kommen eine
gemeinsame Ansicht der Zusammenhänge, eine grafische Allokation und visuelle Cluster innerhalb der Requirements.

Dieses Dokument ersetzt die Stufenfolge aus #1670 durch einen engeren, im Code geprüften Umfang und löst die Findings aus #1668, #1669 und #1660 mit.

### Nicht-Ziele

- Kein neues Statuswort (`released`) und kein neuer Freigabeprozess. Der Workflow bleibt unverändert; er liefert nur die Sperre (§4.5).
- Rigor-Regler, Change-Request-Pfad mit 409 und Impact-Vorschau sind **nicht Teil von P0–P6**, aber als eigenes, voll ausgearbeitetes Vorhaben P7 geplant (§7, O5).
- Keine Mehrfachallokation. Ein Requirement hat höchstens ein Architekturelement (N:1).
- Keine Umbenennung des API-Feldes `level`.
- Kein Re-Design der ReqIF-Schnittstelle.

### Anti-Ziele (wäre ein Fehlschlag, auch wenn es technisch funktioniert)

- Die Reihenfolge ändert still die Ebene eines Requirements (Ordnung darf **nie** die Ebene setzen, wenn eine Allokation existiert).
- Ein Reorder erzeugt in Baselines Massen-Diffs oder neue Inhaltsversionen.
- Zwei Wahrheiten für die Allokation, die auseinanderlaufen können.

## 2. Ist-Stand (geprüft auf `origin/main` e7de2215)

| Thema | Befund | Beleg |
|---|---|---|
| Geschwister-Reihenfolge | existiert nicht; alle Listen und der Baum sortieren `created_at, id` | `application/requirement_service.py:1250`, `architecture_service.py:493`, `persistence/models.py:1194-1446` |
| Baum-Komponente | genau eine, `WorkspaceTree`; Umhängen per Drag-and-drop nur im Architektur-Baum, kein Reorder | `frontend/src/components/shared/WorkspaceTree/workspace-tree.tsx:306-335`, `ArchitectureEditors.tsx:782`, `RequirementList.tsx:118-130` |
| Requirement-Hierarchie | zwei Quellen: `Artifact.parent` und die Kanten `derives-from`/`decomposes`; `Requirement` hat selbst kein parent-Feld | `persistence/models.py:1225`, `traceability/audit/hierarchy.py:194-196, 529` |
| Move/Reorder | kein Endpunkt; nur PATCH `parent_id`; `artifact.get_tree` nur als MCP-Tool; `_tree_node_to_dict` ist toter Code | `rest_api/views.py:7108`, `mcp_server/tools/cross_cutting.py:1380` |
| Hierarchie-Prüfung | `ArtifactService.create_artifact` ruft eine wirkungslose Zyklusprüfung; `update_artifact` prüft keinen Workspace; `parent_id=None` heißt "nicht ändern"; kein Typ-Check am Parent | `application/artifact_service.py:~310, 352` |
| Allokation | `TraceLink(allocated-to)` ohne Status; `allocate()` erzwingt genau eine Zuordnung (ersetzt), der generische Pfad erlaubt mehrere | `application/trace_link_service.py:1432`, `link_types/builtin.py:294-312` |
| Ebene | `Requirement.level` wird ausschließlich aus Hierarchie abgeleitet (`recompute_requirement_levels`); Allokation erzeugt nur einen Vorschlag; `level_source` gibt es schon (`derived`/`manual`) | `traceability/audit/hierarchy.py:665`, `persistence/models.py:1705` |
| Tiefe 4 | `ARCHITECTURE_DEPTH_TO_LEVEL` kennt nur Tiefe 0–3; die QS hat Tiefe 4 | `traceability/audit/hierarchy.py:218-236` |
| Filter | `allocated` und `level` fehlen; unbekannte Parameter werden still akzeptiert (#1668) | `rest_api/views.py:~1773, ~3211` |
| Workflow-Sperre | `state_meta.freeze_on_enter` gibt es, aber nur für `Document` | `workflow/precondition_rules.py:859-881`, `application/document_service.py:94` |
| Diagramm-Editor | `@xyflow/react`, Nodes mit `artifact_ref` (nur Select + UUID), kein Drop von außen, erzeugt nur `diagram-ref` | `frontend/src/components/DiagramGraphEditor/*` |
| Migration/ADR-Stand | persistence endet bei `0130`, nächste `0131`; höchste ADR ist ADR-026; MCP-Manifest 282 Tools in 44 Präfixen | `docs/plans/2026-10-21-backlog-umsetzung-index.md` §e, `docs/agent-templates/tool-manifest.json` |

## 3. Entscheidungen

### 3.1 Vom Product Owner entschieden

| ID | Entscheidung |
|---|---|
| **E1** | Ein Gesamtkonzept und ein Umsetzungsplan für P0–P6, nicht je Teilprojekt eine eigene Spezifikation. |
| **E2** | Die Reihenfolge wird als **Textschlüssel `sort_key` (Fractional Indexing) direkt am `Artifact`** gespeichert, gültig unter dem Container-Eltern `Artifact.parent` für beide Bäume. |
| **E3** | Die Allokation bleibt ein **`TraceLink(allocated-to)`** (Trace-Sicht ist die Wahrheit). Es gibt **keine** zweite Quelle. |
| **E4** | Kardinalität **N:1**: ein Requirement hat höchstens ein Architekturelement, ein Element beliebig viele Requirements. |
| **E5** | Statuswörter und Workflow bleiben unverändert. Wenn ein Workflow-Zustand Read-only verlangt, gilt das (§4.5). |
| **E6** | Sperrregel: Ein **gesperrtes Requirement** ist komplett schreibgeschützt (Position, Elternknoten, Allokation) und kann nicht neu allokiert werden. Ein **gesperrtes Architekturelement** ist selbst eingefroren, darf aber weiter **Ziel** neuer Allokationen sein. Maßgeblich ist immer der Zustand des Requirements. |
| **E7** | Die Namen der Ebenen sind einstellbar: oberste Schicht (z. B. "System"), mittlere (z. B. "Subsystem"), unterste (z. B. "Module"/"Component"). |
| **E8** | Es gibt eine **neue Zusammenhangs-Ansicht** neben dem reinen Requirements- und dem reinen Architektur-Baum, gebaut aus den vorhandenen Modulen, plus eine **grafische Allokation**. |
| **E9** | Requirements sollen sich **visuell clustern** lassen. Cluster unterliegen denselben Änderungsregeln wie alle Artefakte. |

### 3.2 Meine Festlegungen **[Vorschlag]** — bitte prüfen

| ID | Vorschlag | Begründung |
|---|---|---|
| **V1** | Die Reihenfolge gilt nur unter `Artifact.parent`. Der Ableitungsbaum (`derives-from`/`decomposes`) bleibt eine Beziehung, die man sieht, aber nicht sortiert. | Eine Reihenfolge braucht genau einen Eltern-Container (Analyse-Befund 2). |
| **V2** | `allocation_intent` (`allocated`/`not_allocatable`/`unassigned`) wird ein Feld am **Requirement**, nicht an der Kante. | "Bewusst nicht allokierbar" hat keine Kante, an der es hängen könnte. |
| **V3** | **Keine Erweiterungstabelle an der Kante.** Wir hatten sie für Status, Pin und Freigabe vorgesehen; durch E5 entfallen diese. Damit entfällt auch das RLS-Risiko einer neuen Tabelle. Sie kommt nur, falls später echte Allokations-Metadaten entstehen. | YAGNI; weniger Fläche. |
| **V4** | **Die Stufen sind relativ, die Tiefe ist frei** (vom Product Owner entschieden; ersetzt feste vier Stufen und das Klammern). Pro Workspace gibt es eine kleine geordnete Liste benannter Positionen mit stabilem `tier_key`: *erste* (Wurzel), *dazwischen* (alles Mittlere, optional mehrere Namen), *vorletzte* (Eltern von Blättern), *letzte* (Element ohne Kinder), weitere "n von unten" frei ergänzbar. Die Stufe eines Architekturelements wird **vom Blatt her** bestimmt, nicht von der Tiefe; ungleich tiefe Zweige bleiben dadurch eindeutig. Es gibt kein "zu tief" und keinen Befund dafür. Der berechnete `tier_key` wird am Requirement als Zwischenspeicher geführt (einziger Schreiber bleibt `recompute_requirement_levels`); `level` bleibt nur als veralteter Integer-Alias. Hängt man einem Blatt ein Kind an, verschieben sich die Stufen seiner Vorfahren; das löst eine Neuberechnung aus und zeigt sich im Baseline-Diff (R11). Quelle: Literaturcheck `.tmp/analysis/literature-levels.md` (keine Norm fixiert eine Stufenzahl). | Heute fest vier Stufen in `RequirementLevel` (`models.py:213-258`); Konsumenten VERIF-P8, ARCH-003, TRACE-P5 müssen umgestellt werden (R11). Aufwand von P2 wächst deutlich. |
| **V5** | Naming Layer: Jede Stufe der Leiter (V4) hat einen einstellbaren Namen. Als Bedienhilfe kann ein Workspace die Leiter aus drei Namen erzeugen (oben, Mitte, unten; Mitte optional nummeriert). Gespeichert wird der stabile `tier_key`, angezeigt der Name; Umbenennen ändert keine Daten. | D2/D6/D7 aus #1670. |
| **V6** | Rangfolge der Ebenenquelle (vom Product Owner bestätigt, inkl. Rückfall): Allokation, danach **Ableitung über `derives-from`/`decomposes` (Eltern + 1) als Rückfall**, danach Typ-Default, sonst leer (`NULL`). | D5 aus #1670; der Rückfall erhält das Level der heute 717 Requirements ohne Allokation. `level_source` bekommt dafür zusätzlich den Wert `derived_hierarchy`. |
| **V7** | **Gruppen sind rein visuell** (vom Product Owner entschieden, Start): eine Gruppe ordnet nur die Darstellung und hat keine Wirkung auf Stufe oder Allokation. Die Container-Quelle der Stufe in V6 entfällt damit; eine spätere semantische Aufwertung (deklarierte Stufe pro Gruppe) bleibt möglich und wäre eine neue Entscheidung. | Ordner sind heute Requirements mit Kindern (R13). |
| **V8** | Der `sort_key` kommt in den Baseline-Snapshot **und in den Diff** (vom Product Owner als wichtig bestätigt). Eine Positionsänderung erscheint als "Position geändert". Da Textschlüssel beim Einfügen nur eine Zeile ändern, entsteht kein Massenrauschen; ein seltener Neuaufbau eines Geschwisterblocks wird als ein gebündeltes Ereignis gemeldet. | R4 aus der Analyse. |
| **V9** | Neue Filter `?allocated=true|false` und `?level=` (in P0: Integer 1–4 wie heute; ab P2 zusätzlich `tier_key`) antworten bei ungültigem Wert mit 400. Die generische Ablehnung unbekannter Parameter (#1509) bleibt ein eigenes Thema. | Kleinster Schnitt für #1668. |
| **V10** | Die Zusammenhangs-Ansicht und die grafische Allokation lesen **ein gemeinsames Leseobjekt** (ein Endpunkt mit Filtern); die Darstellungsformen sind Renderer darüber (Matrix, Baum-mit-Verknüpfung, Graph). | Du willst in Zukunft viele Darstellungsformen; so kostet jede neue nur einen Renderer. |
| **V11** | **Cluster und Ordner sind dasselbe Konzept** (Product Owner): eine Gruppe von Requirements, als **Pseudo-Ordner** im Baum sichtbar, wenn man sie einblendet (Schalter "Gruppen anzeigen"). Gruppen sind Artefakte; die Mitgliedschaft ist ein Link-Typ und erbt Versionen, Workflow, Sperre und Baselines. **Ein Requirement darf in mehreren Gruppen liegen** (Product Owner); die Reihenfolge gilt deshalb **pro Gruppe** (eigener `sort_key` auf der Mitgliedschaft). Rein visuell (V7). Träger der Gruppen-Reihenfolge: nullable Spalte `TraceLink.sort_key`, nur für Mitgliedschaften genutzt (keine Erweiterungstabelle, V3). | Erfüllt "unterliegt allen Änderungsfaktoren" ohne eigene Mechanik. Pseudo-Ordner zeigt dasselbe Requirement mehrfach. |

### 3.3 Festlegungen aus dem Builder-Check **[Vorschlag]** — Details, die ein Umsetzer sonst raten müsste

| ID | Festlegung |
|---|---|
| **B1** | **Wie wird die Sperre konfiguriert?** Heute gibt es dafür **keine Oberfläche**: `state_meta.freeze_on_enter` wird nur über Seeds und `definition_store` gesetzt (`workflow/definition_store.py:438-450, 1144`), im Frontend kommt es nicht vor. P4 enthält deshalb einen Konfigurationsweg: ein Schalter "sperrt Bearbeitung" je Zustand im Workflow-Editor (API und UI), sonst wäre die Sperre ein toter Mechanismus. |
| **B2** | **Level-Semantik.** Das Level eines Requirements ist die Stufe des Ziel-Elements: die Stufe wird vom Blatt her bestimmt (V4), nicht aus der Tiefe. Heute gilt Tiefe 0–3 → L1–L4 (`ARCHITECTURE_DEPTH_TO_LEVEL`, `hierarchy.py:218`); das entfällt. Da Gruppen rein visuell sind (V7), gibt es keinen Konflikt Ordner ↔ Allokation; `level_source = conflict` entfällt. |
| **B3** | **Reorder-Schreibweise.** `sort_key` wird per `QuerySet.update()` geschrieben (kein `save()`, keine Signale, `modified_at` und `version` bleiben unberührt, damit ETags und Baselines ruhig bleiben). Zusätzlich entsteht ein Audit-Ereignis `reordered` (wer, wohin), damit die Historie erhalten bleibt. |
| **B4** | **Geltung von `sort_key`.** Die Spalte liegt am generischen `Artifact`, P1 füllt und nutzt sie nur für Requirements und Architekturelemente. Andere Artefakttypen behalten `sort_key = NULL` und sortieren weiter nach `created_at, id` (NULL zuletzt). Der Index ist ein normaler zusammengesetzter Index `(parent, sort_key, id)`, kein Unique-Index. Wurzeln werden nach `(workspace, artifact_type)` gruppiert. |
| **B5** | **Naming Layer.** Gespeichert als Workspace-Einstellung (benannte Positionen), Default pro Tenant. Ändern dürfen Workspace-Admins. Oberfläche: Abschnitt in den Workspace-Einstellungen (neben der Baumanzeige-Konfiguration, `WorkspaceSettings/TreeDisplaySection.tsx` als Vorbild). `tier_key` wird **berechnet** (vom Blatt her, V4) und als Zwischenspeicher am Requirement geführt. |
| **B6** | **Allokation ersetzen.** `allocate()` löscht die alte Kante und legt die neue an, **in einer Transaktion**; `TraceLink` kennt keinen Soft-Delete, die alte Kante wird hart gelöscht. Der Teil-Unique-Index braucht daher keine Löschbedingung. |
| **B7** | **Soft-Delete (outdated).** Outdated-Artefakte behalten ihren `sort_key` und werden in Bäumen und Listen weiter ausgeblendet (wie heute). Beim Reaktivieren sind sie wieder an ihrer Position. Eine Allokation auf ein outdated Element bleibt bestehen und wird als Befund gemeldet, nicht still gelöscht. |
| **B8** | **`move`-Vertrag.** Body `{parent_id, after_id}`. `after_id` fehlt: ans Ende. `after_id = null`: an den Anfang. `after_id` muss ein Kind von `parent_id` sein, sonst 400. Typprüfung am Parent: Requirement unter Requirement, Architekturelement unter Architekturelement. Die Architektur-Invarianten I1–I5 stehen in `application/validators.py:11-15` (I1 keine Zyklen, I2 Ebenenordnung, I3 kein fremder Workspace, I4 `allocated-to` nicht auf einen Vorfahren, I5 höchstens eine Wurzel). |
| **B9** | **`allocation-view`.** Flache Zeilen mit Paginierung (Standard 200, Maximum 500) und denselben Filtern wie die Liste; die Baumstruktur baut der Renderer aus `parent_id` und `sort_key`. Die Matrix zeigt ein Fenster (Seite), keine Gesamttabelle. |
| **B10** | **`level` bleibt nullable** (`Requirement.level` ist `null=True`, `models.py:1694`). Nicht allokierte Requirements ohne Container und ohne Typ-Default behalten `NULL`; Exporte und Audits behandeln das heute schon. "`level_source` gesetzt" bedeutet: `unresolved` für diese Fälle. |
| **B11** | **Sperre und Folgeaktionen.** Die Sperre betrifft Position, Elternknoten und Allokation. `decompose`, `derive` und Importe, die ein gesperrtes Objekt verschieben oder umallokieren würden, überspringen es und melden einen Fehlereintrag. Löschen und Outdate folgen weiter den bestehenden Workflow-Regeln (unverändert). Rollback (ADR-025) respektiert die Sperre ebenfalls. |

## 4. Zielbild

### 4.1 Reihenfolge (`sort_key`) — P1

- Neue Spalte `Artifact.sort_key` (Text, nullable bis zum Backfill, danach nicht null), gescoped nach `(workspace, parent)`; für Wurzeln (`parent` ist `NULL`) nach `(workspace, artifact_type)`.
- Index `(parent, sort_key, id)` als Sortier- und Tiebreak-Grundlage. Alle Listen, `list_child_summaries` und der Baum (`get_tree`, CTE `ORDER BY depth, sort_key, id`) sortieren danach.
- Schlüssel: lexikografisch sortierbar, Einfügen zwischen zwei Nachbarn erzeugt einen Schlüssel dazwischen. Ein Reorder schreibt **genau eine Zeile**, erhöht weder `version` noch schreibt es eine Revision (Muster: `recompute_requirement_levels`, Bulk-UPDATE). Selten nötiges Neuaufbauen eines Geschwisterblocks läuft unter Sperre der Eltern-Zeile (`select_for_update`).
- Neue Artefakte werden ans Ende des Geschwisterblocks gehängt. Importe (ReqIF/CSV) und `decompose` setzen die Quellreihenfolge.
- Backfill: je Eltern nach `(created_at, id)`; eine Migration in `persistence` (nächste Nummer = höchste + 1), idempotent, mit Rückwärtsmigration.
- **Ein einziger Move-Dienst** `ArtifactService.move(artifact_id, new_parent_id, after_id)`: er vereint alle Prüfungen (Zyklus, Workspace, Typ-Kompatibilität am Parent, Architektur-Invarianten I1–I5, Sperre §4.5, Level-Neuberechnung) und ist der **einzige** Weg zum Umhängen und Umsortieren. REST `POST …/move/`, MCP-Tool `artifact.move`.
- `WorkspaceTree` bekommt `onReorder` (nicht eine neue Komponente, #175). Tastatur-Alternative und `data-testid` Pflicht.

### 4.2 Allokation (N:1, harte Absicherung) — P2

- Teil-Unique-Index auf `pl_tracelink (source)` mit Bedingung `link_type = 'allocated-to'` (Django `UniqueConstraint(condition=Q(...))`). Datenbankseitig kann ein Requirement nur ein Ziel haben.
- Die Migration prüft vorher auf Verstöße und **bricht laut ab** (Liste der Requirement-IDs im Fehlertext). Auf der QS gibt es laut #1669 keine Mehrfachallokation.
- Alle Schreibpfade laufen über **einen** Dienst (`TraceLinkService.allocate`, Replace-Vertrag bleibt): generischer Pfad (`traceability.create_link`, REST `/trace-links/`), `derive`, `ArchitectureDecomposeService`, MCP `suggest_architecture_for_requirement`, UI-Dialog aus #928, Seeds und `link_types/migration_ops.py`. Der generische Pfad **verweigert** ein zweites `allocated-to` mit einem klaren Fehler (409), statt zu duplizieren.
- Neues Feld `Requirement.allocation_intent` (V2), Standard `unassigned`. `not_allocatable` zählt in Coverage als "bewusst ausgenommen", nicht als Lücke.
- Neue Leseoberfläche: `GET /api/v1/allocations/` (Liste mit Filtern, Zähler) und Filter `?allocated=`/`?level=` auf der Requirement-Liste (#1668); MCP `requirement.query` bekommt `allocated`/`level`.

### 4.3 Ebene aus Allokation — P2 (Stufe 1 aus #1670)

- `recompute_requirement_levels` bekommt die Allokation als **Eingabe** nach V6. Er liest heute `Artifact.parent_id` **und** `derives-from`/`decomposes`; beide werden entkoppelt (Ableitung ist kein Ordner), und ein Allokations-Link löst künftig eine Neuberechnung aus (heute nicht, `trace_link_manager.py:430, 541, 626, 650`).
- `level_source` wird um `derived_allocation`, `derived_type`, `unresolved` erweitert (Enum plus Migration). `manual` gewinnt weiter (`hierarchy.py:716-720`).
- Die Stufe kommt vom Blatt her (V4); es gibt keine Tiefengrenze und keinen Befund "zu tief". Ein neues Kind an einem Blatt verschiebt die Stufen der Vorfahren und löst eine Neuberechnung aus.
- **Stufenleiter und Naming Layer** (V4, V5): pro Workspace (Product Owner) eine kleine Liste benannter relativer Positionen mit `tier_key`, Name und Position. Gilt in UI, Export, Fehlermeldungen. Umbenennen ändert nur den Namen; Löschen einer Position mit Verweisen wird abgelehnt oder per Zusammenführen gelöst. Stakeholder-Needs (L0) sind ein eigener Typ **ohne** Stufe. Migration von L1–L4: Seed-Positionen plus veralteter Integer-Alias (`.tmp/analysis/literature-levels.md`).
- Die Altlast (laut #1669 508 Levelwechsel) läuft in **einem** Lauf mit Trockenlauf über `report_requirement_levels` (`fill_only`). Ein neues ADR (ADR-027 oder höher) löst ADR-005 teilweise ab; `superseded_by` pflegen. CONS-P13 wird ersetzt, VERIF-P8, ARCH-003 und TRACE-P5 werden auf den neuen Schlüssel umgestellt.
- Baseline-Diffs durch den Lauf (R3) werden im ADR festgehalten; Altbaselines bleiben unverändert (Snapshots sind unveränderlich).

### 4.4 Darstellungsformen — P3, P5, P6

Siehe §6.

### 4.5 Sperre aus dem Workflow — P4

- Die vorhandene Markierung `state_meta.freeze_on_enter` (`workflow/precondition_rules.py:859-881`) gilt künftig auch für Requirements und Architekturelemente. Welche Zustände sperren, stellt der Nutzer im Workflow ein; **die Standard-Presets bleiben unverändert**, es ändert sich also zunächst nichts im Verhalten.
- Im sperrenden Zustand sind **Position (`sort_key`), Elternknoten und Allokation** schreibgeschützt (E6). Eine Änderung antwortet mit 409 (Fehler-Envelope `CONFLICT`, Grund = Zustandsname); die UI zeigt die Sperre am Knoten.
- Die Prüfung sitzt im `ArtifactService.move` und im Allokations-Dienst, nicht verteilt in Views.

## 5. API und MCP

| Zweck | REST | MCP |
|---|---|---|
| Umhängen und Umsortieren | `POST /api/v1/artifacts/{id}/move/` (Body: `parent_id`, `after_id`) | `artifact.move` |
| Baum lesen (mit Ordnung) | `GET /api/v1/workspaces/{id}/tree/?type=` (neu; ersetzt toten Code `_tree_node_to_dict`) | `artifact.get_tree` (sortiert, ohne Soft-Deleted) |
| Allokation lesen | `GET /api/v1/allocations/` (Filter `requirement`, `element`, `allocated`, `level`, `intent`) | `allocation.query` |
| Allokation schreiben | bestehende `POST /trace-links/` (mit Fehler bei zweitem Ziel) und `allocate` | `traceability.create_link`, `ai_derivation.suggest_architecture_for_requirement` |
| Filter | `?allocated=`, `?level=` auf Requirements | `requirement.query` erweitert |
| Zusammenhangs-Leseobjekt | `GET /api/v1/workspaces/{id}/allocation-view/` | `allocation.view` |

Zu aktualisieren sind bei jeder neuen Route und jedem Tool: `docs/agent-templates/tool-manifest.json` samt `test_tool_manifest_drift.py`,
`mcp_server/tool_registry.py`, die OpenAPI-Tests (`test_openapi_list_params`, `test_schema_completeness_1388`), die Zähler in CLAUDE.md,
README und `clients/registry.yaml` (nur über den `agent-meta-manager`, Plan-Index §f.1).

## 6. Oberfläche

Gemeinsame Regeln: i18n DE/EN, Design-Tokens, `data-testid` an allen interaktiven Elementen, Tastaturbedienung, Zustand der Sperre sichtbar.

### 6.1 Zwei Bäume ordnen (P1)

Beide Bäume nutzen `WorkspaceTree` mit Drag-and-drop zum Umsortieren und Umhängen, Tastatur (Alt+↑/↓) und dem "Move…"-Dialog. Der Requirements-Baum bekommt das Umhängen, das ihm heute fehlt. Optimistische Aktualisierung mit Rückfall bei Fehler. Der Kommentar in `RequirementArtifactForm.tsx:50-52` (angeblich kein `parent_id`) wird korrigiert.

### 6.2 Zusammenhangs-Ansicht (P3)

Eigene Ansicht neben den beiden Bäumen, **auf dem gemeinsamen Leseobjekt (V10)**. Vom Product Owner im Entwurf (Visual Companion, 2026-11-04) bestätigt:
- **Standarddarstellung ist B** (Architektur-Baum mit den Requirements als Unterlisten, sortiert nach `sort_key`, plus Block "Nicht allokiert"). **A (zwei Spalten mit Verbindung) und C (Matrix) sind über einen Umschalter in derselben Ansicht wählbar**; Filter und Auswahl bleiben beim Wechsel erhalten. Die grafische Darstellung (P5) kommt als vierte Variante dazu.
- **Gemeinsame Kopfleiste mit klugen Filtern:**
  - *Schnellfilter* (ein Klick): **Offen**, **Nicht allokiert**, **Gesperrt**, **Befunde** (z. B. Allokation auf ein outdated Element, B7).
  - *Freie Filter* ("zeig mir alle Requirements mit …"): Ebene, Typ, Kategorie, Workflow-Zustand, Allokationszustand (alle/allokiert/nicht allokiert/bewusst ausgenommen), Cluster, Textsuche. Filter lassen sich kombinieren (UND).
  - **Element-Teilbaum:** "nur Strukturelement A und alles darunter".
  - *Offen* **[Vorschlag]** heißt: nicht in einem Zustand, den der Workflow als abschließend oder sperrend (`freeze_on_enter`) markiert.
  - Kennzahlen "x von y unallokiert", "n gesperrt", "m Befunde"; gespeicherte Sichten pro Nutzer.
- **Allokationshilfe:** (1) Mehrfachauswahl von Requirements und "Allokieren auf …" (Elementwahl mit Suche). (2) *Vorschläge:* für jedes nicht allokierte Requirement wird das wahrscheinlichste Element mit Begründung angezeigt (vorhanden: `ai_derivation.suggest_architecture_for_requirement`, Provider-neutral über den LLM-Adapter); einzeln oder gesammelt annehmen, nach dem Muster der Suggestion-Inbox (#1289). Nichts wird ohne Bestätigung geschrieben. Der Schreibpfad ist der eine Allokationsdienst (§4.2).
- Allokieren und Lösen direkt in der Ansicht (Klick/Drag), respektiert die Sperre.

### 6.3 Grafische Allokation (P5)

**Karten-Graph (Hauptdarstellung, vom Product Owner im Entwurf bestätigt):** Beide Bäume erscheinen als **Karten**, links der Requirements-Baum, rechts der Architektur-Baum. Eltern → Kind sind graue Linien, **Allokationen sind Verbindungen zwischen den beiden Seiten** (je Requirement höchstens eine, N:1; ein Befund, z. B. outdated Ziel, ist farblich markiert). Die Reihenfolge der Geschwister folgt `sort_key`.
- *Aussehen:* nicht allokierte Karten orange mit Anfasser, gesperrte Karten grau ohne Anfasser; nicht zu den Filtern passende Karten werden **abgeblendet**, nicht ausgeblendet, damit Verbindungen sichtbar bleiben.
- *Bedienung:* Klick hebt die Verbindungen der Karte hervor; vom Anfasser einer Requirement-Karte auf eine Architektur-Karte ziehen legt die Allokation an, auf eine andere Karte ziehen allokiert um; Zweige auf-/zuklappen; Zoom, Verschieben, Minimap; Ebene und Element-Teilbaum wählbar; Tastaturalternative "Allokieren auf …" (Elementwähler, kein Zeichnen nötig).
- *Layout:* automatisch geordnet (dagre); die Bäume wachsen nach außen, die Allokationen laufen in der Mitte.
- *Technik:* Aufbau auf dem Diagramm-Editor (`@xyflow/react`, dagre). Ihm fehlen heute Drop von außen, Mehrfachauswahl, Node-Bindung per Auswahl statt UUID und Kanten vom Typ `allocated-to`; das gehört in P5. Der Graph liest das Leseobjekt aus §4.4/V10 und speichert **keine eigene Wahrheit** (kein gespeichertes Diagramm nötig).

**Ansichtsmodus und Bearbeitungsmodus.** Ein Umschalter trennt **Ansicht** (nur lesen, Anfasser und Ziehen aus) von **Bearbeiten**. Der Modus ändert **keine Regel**: Jede Schreibaktion geht über dieselben Dienste wie überall (`ArtifactService.move`, der eine Allokationsdienst), also mit allen Prüfungen (N:1-Index, Zyklus, Workspace, Architektur-Invarianten, Workflow-Sperre §4.5, Rollen/Rechte) und denselben Fehlern. Die Oberfläche blendet nur Bedienelemente ein; **durchgesetzt wird allein im Backend**. Standard ist Ansicht, Bearbeiten erfordert die Schreibrechte des Nutzers. Das gilt für alle Darstellungen der Zusammenhangs-Ansicht.

**Karteninhalt je Workspace einstellbar.** Welche Informationen auf einer Karte stehen (z. B. ID, Titel, Zustand, Ebene, Typ, Kategorie, Cluster, Allokationsanzahl, Sperre, Verantwortlicher), stellt der Workspace ein, getrennt für Requirement-Karten und Architektur-Karten, mit Reihenfolge und Anzahl der Zeilen. Umsetzung nach dem Muster der konfigurierbaren Baumanzeige (#1257): `TreeDisplayFields`/`tree-display-fields-context` und die Abschnitte `TreeDisplaySection` in System-, Workspace- und Nutzer-Einstellungen; Rang System < Workspace < Nutzer wie dort. Sicherheitsrelevante Markierungen (Sperre, Befund, nicht allokiert) sind **nicht abschaltbar**.

Drag-and-drop folgt dem Vorbild der Bäume (`tree-drag.ts`) oder dem Mechanismus von `@xyflow/react`; Tastaturalternative ist Pflicht.

### 6.4 Cluster (P6)

Requirements lassen sich in der Baum- und der Zusammenhangs-Ansicht zu Clustern zusammenfassen (Farbe/Rahmen, einklappbar). Ein Cluster ist ein Artefakt (V11) und hat damit Version, Workflow, Sperre und Baseline-Erfassung. Er ändert weder Ebene noch Allokation seiner Mitglieder.

## 7. Teilprojekte und Akzeptanz

| # | Inhalt | Akzeptanz (prüfbar) |
|---|---|---|
| **P0** | #1660 (Selbst-Parent-PATCH); `ArtifactService` härten (Workspace-Prüfung, Typ-Check, echte Zyklusprüfung bei Anlage und Update, `parent_id=None` = Abhängen); Filter #1668 | Selbst-Parent liefert 400, kein Hängen; Architektur-Baum lesbar; `?allocated=true|false`, `?level=` wirken, ungültiger Wert = 400; Tests rot vor, grün nach dem Fix |
| **P1** | `sort_key`, Backfill, `ArtifactService.move`, REST/MCP, Sortierung überall, `onReorder`, Requirements-Baum mit Umhängen | Reihenfolge überlebt Reload in beiden Bäumen; ein Reorder ändert genau eine Zeile und keine `version`; parallele Reorder im selben Eltern bleiben konsistent (Test); alle Listen deterministisch (`created_at` nicht mehr maßgeblich) |
| **P2** | Teil-Unique-Index N:1, ein Allokationsdienst, `allocation_intent`, Ebene aus Allokation, `level_source`-Werte, Naming Layer, Altlastlauf, ADR | Kein Requirement hat zwei `allocated-to` (DB-Test); generischer Pfad verweigert ein zweites Ziel; für alle Requirements ist `level_source` gesetzt; Trockenlauf-Bericht vor dem Lauf; Level wechselt nach Allokation ohne Zutun |
| **P3** | Leseobjekt `allocation-view`, Zusammenhangs-Ansicht (Baum + Matrix), Filter und Kennzahl | Unallokierte Requirements sind in der Ansicht filterbar und zählbar; Klick allokiert/löst; E2E-Test für den Hauptpfad |
| **P4** | `freeze_on_enter` für Requirement und Element, 409-Sperre in `move` und Allokation, Sperranzeige | Ein Requirement im sperrenden Zustand lässt sich weder verschieben noch (neu) allokieren; ein gesperrtes Element nimmt weiter Allokationen an; Standard-Presets verhalten sich unverändert |
| **P5** | Karten-Graph (beide Bäume als Karten, Allokation als Verbindung), Ansicht/Bearbeiten-Umschalter, konfigurierbarer Karteninhalt | Ziehen vom Anfasser auf ein Element legt die Allokation an bzw. allokiert um; im Modus "Ansicht" ist kein Schreiben möglich; ein Schreibversuch gegen Sperre, Zyklus oder N:1 liefert denselben Fehler wie über die API (Test: gleiche Fehlercodes UI ↔ REST); Kartenfelder pro Workspace einstellbar, Sperre/Befund bleiben sichtbar; Tastaturalternative vorhanden |
| **P6** | Gruppen (Cluster/Ordner) als Artefakt, Anzeige als Pseudo-Ordner | Gruppe erstellen, Mitglieder zuordnen, ein-/ausblenden und einklappen; Gruppe hat Versionen und Workflow; im Modus "rein visuell" keine Wirkung auf Ebene oder Allokation |
| **P7** | Reife und Beständigkeit voll ausgearbeitet: Rigor-Regler pro Workspace, Change-Request-Pfad mit 409 und Impact-Vorschau, Freigabe pro Element, Einfrieren in Baselines (Stufe 3 und 4 aus #1670) | Eigene Teilspezifikation nach P0–P6 (O5); Akzeptanz dort |

**Reihenfolge:** P0 → P1 und P2 (P2 kann nach P0 parallel zu P1 laufen, sie berühren verschiedene Teile) → P4 → P3 → P5 → P6 → P7. P4 vor P3, damit die Ansicht die Sperre von Anfang an zeigt. P7 ist ein eigenes, später ausgearbeitetes Vorhaben.

## 8. Migration und Risiken

| # | Risiko | Maßnahme |
|---|---|---|
| R1 | Verwechslung der ID-Räume (Requirement-, Artifact-, Element-ID) in Migrationen | Migration über `TraceLink.source/target` (Artifact-IDs), Vorher/Nachher-Zählung als Test, idempotent |
| R2 | 508 Levelwechsel erzeugen Baseline-Diffs, schreiben per Bulk-UPDATE ohne Versionssprung | Trockenlauf, ein Lauf, im ADR festhalten, Altbaselines unverändert |
| R3 | Mehrfachallokationen in Altdaten | Migration prüft und bricht laut ab |
| R4 | Sortierung ändert sich für alle Clients (`created_at,id` → `sort_key,id`) | CHANGELOG-Hinweis (Breaking), deterministischer Tiebreak |
| R5 | Parallele Reorder | Eltern-Zeile sperren bei Neuaufbau; ein Zeilen-Write sonst |
| R6 | Merge-Konflikte in `rest_api/views.py`, `urls.py`, `tool_registry.py`/Manifest, `persistence/models.py` | Queue-Regel des Plan-Index §d; generierte Dateien nach Rebase neu erzeugen |
| R7 | Audit-Regeln (TRACE-P3 ist Blocker) lesen `allocated-to` aus dem Graphen | Da die Kante die Wahrheit bleibt, ändert sich ihr Format nicht; nur die Level-Regeln werden angepasst |
| R8 | Sperre ohne Wirkung in Standard-Presets verwirrt | Doku und UI-Hinweis, welche Zustände sperren |
| R9 | Rollback (ADR-025) stellt Ordnung nicht wieder her (`restorable_fields.py`) | Klassifizierung von `sort_key` ergänzen |
| R10 | `satisfies→function` (Plan B) ist eine zweite Allokationswelt | Außerhalb dieses Umfangs; als Hinweis im ADR |
| R11 | (Literaturcheck: Klauselzitate stammen teils aus Issue #1670 oder dem Gedächtnis und sind vor Verwendung in ADRs zu prüfen, die Normvolltexte waren nicht lesbar.) Die dynamische Stufenleiter entfernt die feste Wertemenge von `Requirement.level`; Konsumenten (Serializer, MCP, Frontend `RequirementList`/`TraceSpine`, `stage_matrix.py`, Bootstrap, Audit-Regeln VERIF-P8/ARCH-003/TRACE-P5, Exporte) setzen heute 1–4 voraus | `level` bleibt als veralteter Integer-Alias (Position in der Leiter); Konsumenten werden in P2 gelistet und umgestellt; Migration L1–L4 → Leiter mit Default-Stufen; Literaturcheck vor Umsetzung (O3) |

## 9. Offene Fragen

| ID | Frage | Auswirkung |
|---|---|---|
| **O1** | ~~Gruppen semantisch oder visuell?~~ **Entschieden: rein visuell (V7).** Semantische Aufwertung später möglich. | Stufe 1 ohne Container-Quelle |
| **O2** | ~~Mehrere Gruppen je Requirement?~~ **Entschieden: ja (V11);** Reihenfolge pro Gruppe. | `sort_key` auf der Mitgliedschaft |
| **O3** | ~~Dynamische Leiter~~ **Entschieden:** relativ, vom Blatt her (V4); pro Workspace; Needs ohne Stufe. **Offen:** Wie lange lebt der Integer-Alias `level` in Exporten und API? Wie wird die Verschiebung der Stufen nach Anhängen eines Kindes im Baseline-Diff dargestellt? | Datenmodell von P2, Diff-Rauschen |
| **O4** | Wie viele Gruppen- und Stufenebenen muss die Oberfläche gleichzeitig darstellen können (Layout bei sehr tiefen Bäumen)? | Layout des Karten-Graphen, Performance |
| **O5** | ~~Zeitpunkt P7~~ **Entschieden:** P7 bekommt eine eigene Teilspezifikation nach P4; der Plan deckt P0–P6 ab. | Roadmap |

## 10. Zuordnung zu #1670 (D1–D17)

| D | Stand in diesem Konzept |
|---|---|
| D1 Leiter datengetrieben | übernommen (V4: Leiter voll dynamisch) |
| D2, D6, D7 Naming Layer | übernommen (V5) |
| D3, D17 Rigor, CCB-Pflicht | zurückgestellt (O5) |
| D4, D5 Container, Rangfolge | übernommen (V6, V7) |
| D8 `module` als Stufe | über Naming Layer abgedeckt (unterster Name) |
| D9 Mehrfachallokation | **verworfen**, durch E4 (N:1) ersetzt |
| D10–D12 Freigabe pro Element, Pin, Kaskade | **ersetzt** durch E5/E6 (Workflow-Sperre) |
| D13 `allocation_intent` | übernommen (V2, am Requirement) |
| D14, D15 Migration, CONS-P13/VERIF-P8 | übernommen (§4.3) |
| D16 Struktur in Dokumentversion | zurückgestellt (kein Träger: `DocumentSection` nie gebaut) |

## 11. Bezüge

#1670 (Feature, wird umgesetzt), #1669 (Design), #1668 (Filter), #1660 (Selbst-Parent), #1509, #175, #928, #1257, #1374; ADR-005 (wird teilweise abgelöst), ADR-025, ADR-026; Plan B, Plan C, Plan F und `docs/plans/2026-10-21-backlog-umsetzung-index.md`.
