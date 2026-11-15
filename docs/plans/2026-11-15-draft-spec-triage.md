# Triage: vier liegende Draft-Specs

**Datum:** 2026-11-15 · **Prüfstand:** `origin/main` `dea467b4` (2026-11-15T08:40Z)
**Art:** Befundaufnahme + Statusempfehlung. Keine Codeänderung, keine Issues.
**Auftrag:** Die als `draft`/`proposed` liegenden Konzepte gegen den aktuellen `main` prüfen und
je Spec entscheiden: umgesetzt / teilweise umgesetzt / überholt / offen.

## Prüfmethode

Belege sind Dateien, Migrationen und Tool-Namen auf `main` (Pfad-Abgleich über den
Git-Tree von `origin/main`, dazu gezielte `grep`-Läufe in den genannten Dateien).
Zeilennummern driften, deshalb sind Symbole und Dateipfade der Anker. Zusätzlich geprüft:
Status der zugehörigen Issues (#1660, #1668, #1669, #1670, #1374, #801 — alle `closed`).

> **Umsetzung:** Die Statusänderungen aus §6 sind angewendet: Ordnung-und-Allokation und das
> Release-Design stehen auf `accepted`, der Backlog-Umbrella auf `superseded`. Die beiden
> inhaltlich offenen Konzepte (Navigationsbaum, Dokumentensicht) bleiben `draft`. §6 enthält
> weiterhin die Begründung; die dort gezeigten Patch-Blöcke sind bereits eingespielt.

---

## 1. Übersicht

| # | Spec | Status heute (Datei) | Befund | Empfohlener Status | Aufwand Rest |
|---|---|---|---|---|---|
| 1 | `2026-11-04-ordnung-allokation-design.md` (P0–P6) | `draft` | **umgesetzt** (P0–P6), 2 Restlücken | **`accepted`** | klein (2 Punkte) |
| 2 | `2026-11-08-navigationsbaum-und-verbindungsansicht-design.md` | `draft` | **offen, nichts implementiert** | `draft` bleibt | 4–5,25 Tage (Plan §12) |
| 3 | `2026-11-04-dokumentensicht-neu-design.md` | `draft` | **offen, blockiert** | `draft` bleibt | nicht schätzbar (Blockade) |
| 4 | `2026-10-21-backlog-umsetzungsplaene-design.md` | `proposed` | **überholt** | **`superseded`** | 0 |

---

## 2. Spec 1 — Ordnung und Allokation (P0–P6): umgesetzt

**Status heute:** `draft` · **Befund:** P0–P6 sind gebaut, P7 war im Dokument selbst
ausgeklammert (§7, O5). Alle vier zugehörigen Issues sind geschlossen
(#1660 am 2026-11-08, #1668 am 2026-11-09, #1669 am 2026-11-12, #1670 am 2026-11-13).

### Belege je Teilprojekt

| P | Inhalt | Beleg auf `main` |
|---|---|---|
| P0 | Selbst-Parent, `ArtifactService`-Härtung, Filter #1668 | `?allocated=`/`?level=` in `rest_api/views.py` (dreistufig bzw. 1–4, ungültig → 400); `backend/application/tests/test_artifact_move.py` |
| P1 | `sort_key`, `move`, Ordnung überall | `persistence/migrations/0132_artifact_sort_key.py`, `0137_tracelink_membership_sort_key.py`, `0138_artifact_sort_key_list_index.py`, `persistence/sort_keys.py`, REST `POST /api/v1/artifacts/<id>/move/` + MCP `artifact.move`, `rest_api/tests/test_move_api.py`, `application/tests/test_artifact_move.py`, `Shared/WorkspaceTree/tree-reorder.ts` + `tree-move-dialog.tsx`, `e2e/tests/tree-reorder.spec.ts` |
| P2 | Allokation, `allocation_intent`, Stufenleiter | `0134_allocation_intent_tier_ladder.py`, `0135_workspace_tier_seed.py`, `0136_workspace_tier_rls_policy.py`, `application/tier_compute.py`, `tier_ladder_service.py`, `tier_naming.py`, `application/tests/test_tier_naming.py`, **ADR-027 `accepted`** |
| P3 | Leseobjekt + Zusammenhangs-Ansicht | `application/allocation_view_service.py` (ein Leseobjekt, `page_size` 200/500, Zähler über die gefilterte Menge), REST `allocations/` (`rest_api/urls.py:609`), `workspaces/<id>/allocation-view/`, Renderer `ConnectionView/TreeRenderer.tsx`, `MatrixRenderer.tsx`, `TwoColumnRenderer.tsx` |
| P4 | Workflow-Sperre | `application/artifact_freeze.py` (`state_meta.freeze_on_enter`), `workspaces/<id>/locks/`, Konfigurationsschalter im Workflow-Editor (`WorkflowEditor/InspectorPanel.tsx:314-323`, `workflow-inspector-freeze`), i18n `workflow.inspector.freezeState` = „Sperrt Bearbeitung (Position, Eltern, Allokation)“ |
| P5 | Karten-Graph, Ansicht/Bearbeiten, Kartenfelder | `AllocationGraph/` (`buildGraph.ts`, `cardFields.ts`, `useCardFields.ts`, `errors.ts`), Modusschalter `AllocationGraph.tsx:101-110,268-272`, Präferenz `ui.allocation_graph.card_fields` (GLOBAL/WORKSPACE/USER), `e2e/tests/allocation-graph.spec.ts` |
| P6 | Gruppen als Artefakt | `application/group_service.py`, MCP `group.create/list/members/add_member/remove_member/move_member`, `rest_api/tests/test_groups_api.py`, `Shared/WorkspaceTree/tree-groups.ts` + `workspace-tree.groups.test.tsx` |
| — | Betreiber-Referenz | `docs/features/ordering-and-allocation.md` (P1–P6, geschrieben als Auslieferungsreferenz) |

**Fachlich überholt, nicht offen:** §4.2 fordert einen **harten** Teil-Unique-Index (N:1).
Der Index kam mit `0133_tracelink_allocated_to_unique.py` und wurde mit
`0142_remove_tracelink_uniq_tracelink_allocated_to_source.py` wieder entfernt — D9
(Entscheidung 2026-11-10) macht die Kardinalität konfigurierbar
(`application/allocation_settings.py`, `test_allocation_cardinality_guard.py`,
`test_multi_allocation_config.py`, Audit-Regel `allocation_multiplicity.py`). Das ist **keine
Lücke**, sondern eine bewusste Weiterentwicklung, dokumentiert in ADR-028 (`accepted`).

### Rest (konkret, klein, ohne Entscheidungscharakter)

1. **REST `GET /api/v1/workspaces/{id}/tree/`** (§5, Tabelle „Baum lesen mit Ordnung“) ist in
   `rest_api/urls.py` **nicht registriert**; Bäume lesen weiterhin über die Listen-Endpunkte,
   sortiert nach `sort_key`. MCP `artifact.get_tree` existiert. Die Feature-Doku
   `docs/features/ordering-and-allocation.md` nennt den Endpunkt trotzdem → **Doc-Drift**.
2. **MCP `allocation.view`** (§5) fehlt; vorhanden ist nur `allocation.query`. Für Agenten
   bedeutet das: Zähler/Filter des Leseobjekts sind über MCP nicht erreichbar.

**Empfohlene Aktion:** Status auf `accepted` setzen, die zwei Restpunkte als eigene kleine
Aufgabe (Doku korrigieren **oder** Route/Tool nachziehen) — nicht als Grund, den Status zu lassen.

---

## 3. Spec 2 — Navigationsbaum + Verbindungsansicht als zwei Bäume: offen

**Status heute:** `draft` · **Befund: nichts davon ist implementiert.** Das ist kein
Versäumnis, sondern der dokumentierte Stand: `docs/plans/index.md` führt den Plan als
„plan written, nothing implemented; every task checkbox unchecked“.

| Phase | Behauptung der Spec | Beleg auf `main` |
|---|---|---|
| G — Gruppenverwaltung als Dialog | `GroupManager` nicht mehr in der Spalte, `req-list-groups-btn`, `AddToGroupDialog` | **nicht gebaut**: `RequirementEditors.tsx:657-659` reicht weiter `groupPanel={<GroupManager …/>}` an `RequirementList.tsx:279,311,474`; kein `AddToGroupDialog` im Tree |
| V2 — `kind`-Filter, Element-`sort_key` | `allocation-view/?kind=`, Element-Zeilen mit `sort_key` | **nicht gebaut**: `allocation_view_service.py:27-43` hat keinen `kind`-Parameter; `:154` liefert weiter `"sort_key": None`; das Frontend filtert clientseitig (`useAllocationView.ts:182,319,352`) |
| V — Modus `trees` | Default `trees`, Kanten-Overlay, Zeilen-Checkboxen, Präferenzen `show_edges`/`filters_expanded` | **nicht gebaut**: `ConnectionViewMode = "tree" \| "two-column" \| "matrix" \| "graph"` (`useAllocationView.ts:33`), kein `AllocationTreesRenderer.tsx`, `allocation-trees.ts`, `edge-geometry.ts`; keine Präferenzschlüssel |

**Verändert hat sich seit dem 2026-11-08 nur der Kontext:** Die Verbindungsansicht hat inzwischen
einen Gruppenfilter (`ConnectionView/groups-filter.test.tsx`), `useAllocationMutations.ts` und
gespeicherte Sichten als Präferenz (`ui.connection_view.saved_views`). Die Spec-Aussagen zu
`AllocationAssistant.tsx` (doppelte Liste), `TreeRenderer.tsx` und `useAllocationView.ts` sind
weiterhin zutreffend, die Zeilennummern driften.

**Rest:** kompletter Plan `docs/plans/2026-11-08-navigationsbaum-und-verbindungsansicht.md`
(G, V2, V; 0,5–1 / 0,5 / 3,75–4,25 Tage laut Spec §12, V1+V3 gemeinsam).

**Empfohlene Aktion:** Status **nicht** ändern (bleibt `draft`). Vor Start ein Frische-Check des
Plans (Querregel 1 der Roadmap) und die Freigabe von D4/O5 einholen: die Spec ändert §6.2 der
Ordnung-und-Allokation-Spec (Default-Darstellung), und genau dort ist inzwischen der Karten-Graph
als vierte Ansicht gebaut — die Freigabe entscheidet, ob `trees` den heutigen Default ablöst.

---

## 4. Spec 3 — Dokumentensicht (`DocumentView`): offen, blockiert

**Status heute:** `draft` · **Befund: nichts implementiert**, und die im Dokument selbst
genannte Blockade besteht weiter.

| Baustein | Erwartung (D1–D6) | Beleg auf `main` |
|---|---|---|
| Modell `DocumentView` | Tabelle, RLS, `config`-JSON, CRUD | **fehlt** (kein Modell, keine Migration 0131–0150, kein `document_view_service`) |
| REST `document-views/` | CRUD + `render/` + `export/` | **fehlt** in `rest_api/urls.py` |
| MCP `document_view.*` | 5 Tools | **fehlt** im Manifest (vorhanden: `document.*` = Artefakt `Document` aus Plan F) |
| Oberfläche | Route `/document-views/<id>` | **fehlt**; `frontend/src/components/Documents/` ist die Artefakt-UI (Plan F) |
| Abhängigkeit `bulk-update` | `PATCH /api/v1/artifacts/bulk-update/` | **fehlt** weiterhin (`rest_api/urls.py` ohne Treffer); die Tabellenansicht-Spec ist laut Spec-Index ungebaut → **D5 ist so nicht baubar** |
| Abhängigkeiten P1/P4 | `sort_key`, Sperre | **erfüllt** (0132 ff., `artifact_freeze.py`) — zwei von drei Blockern sind weg |

**Rest:** vollständiges Vorhaben; ohne die Tabellenansicht-Slice (Filter-Sprache + `bulk-update`)
lässt sich D5 (Sammel-Speichern) nicht regelkonform bauen, und ohne sie fehlt E6 (Kapitelfilter).

**Empfohlene Aktion:** Status **nicht** ändern (bleibt `draft`). Die Spec braucht zuerst eine
Entscheidung, nicht Code (siehe §6, E1): weitermachen (dann Tabellenansicht-Slice vorziehen),
auf das `Document`-Artefakt + Projektion (Phase G, S3) aufsetzen, oder einstellen.

---

## 5. Spec 4 — Backlog-Umsetzungspläne (2026-10-21): überholt

**Status heute:** `proposed` · **Befund: überholt.** Das Dokument war die Planbasis für die
Cluster A–G (67 Issues). Es ist in allen drei Funktionen abgelöst:

1. **Reihenfolge/Wellen** → `docs/superpowers/plans/2026-11-10-backlog-roadmap.md` (31 Issues,
   Phasen A–H, Entscheidungen vom 2026-11-10). Der Roadmap nennt die alten Pläne ausdrücklich als
   „auf beta.29 weitgehend umgesetzt“ und ersetzt die Wellenlogik.
2. **Querschnittsentscheidungen Q1–Q4** → alle vier sind umgesetzt bzw. entschieden:
   Präferenzdienst (Plan C), Promptfoo (#587, CI-Job existiert), Memory-Port (Plan A),
   Key-Prinzipale (Plan E).
3. **Einzelpläne** → existieren separat (`docs/plans/2026-10-21-plan-a|d|g`, Archive für B, C, E, F)
   und sind dort statusgeführt; §6 des Dokuments verweist selbst auf den Index als Wahrheit.

Die vier verbliebenen „offenen Punkte“ (§4 O1–O6) sind entweder entschieden (ADR-022/023/024
`accepted` am 2026-10-26), gegenstandslos (BluePencil am 2026-11-02 entfernt, `1ad7ef17`) oder als
`ENT-*`/`U-*` im laufenden Entscheidungsregister geführt.

**Empfohlene Aktion:** `status: superseded` mit einzeiligem Verweis auf die Roadmap.
Nicht archivieren: das Dokument bleibt der Entscheidungsnachweis der Sitzung vom 2026-10-21.

---

## 6. Statusänderungen

### Anzuwenden (Datei liegt nur auf `origin/main`, nicht im ausgecheckten Branch)

**a) `docs/superpowers/specs/2026-11-04-ordnung-allokation-design.md`**

```diff
-status: draft
+status: accepted
```
und direkt unter der H1-Zeile einfügen:

```markdown
> **Status: accepted (2026-11-15).** P0–P6 sind auf `main` umgesetzt (Belege:
> `docs/features/ordering-and-allocation.md`, Migrationen 0132–0138, ADR-027, ADR-028).
> Offen nur zwei Randpunkte: REST `GET /workspaces/{id}/tree/` ist nicht registriert,
> MCP `allocation.view` fehlt. §4.2 (harter N:1-Index) ist durch D9/ADR-028 überholt
> (Index 0133 eingeführt, 0142 entfernt, Kardinalität konfigurierbar).
```

**b) `docs/superpowers/specs/2026-10-21-backlog-umsetzungsplaene-design.md`**

```diff
-status: proposed
+status: superseded
+superseded_by: docs/superpowers/plans/2026-11-10-backlog-roadmap.md
```
und direkt unter der H1-Zeile einfügen:

```markdown
> **Status: superseded (2026-11-15)** — abgelöst durch die
> [Backlog-Roadmap A–H](../plans/2026-11-10-backlog-roadmap.md); die Einzelpläne A–G führen
> ihren Status selbst (`docs/plans/index.md`). Inhalt bleibt als Entscheidungsnachweis stehen.
```

### Nicht angewendet (bewusst)

**c) `2026-11-08-navigationsbaum-…-design.md`** — bleibt `draft`. Nichts ist gebaut; ein
Statuswechsel wäre unbelegt.

**d) `2026-11-04-dokumentensicht-neu-design.md`** — bleibt `draft`. Nichts ist gebaut, und die
Kernabhängigkeit (`bulk-update`) fehlt weiterhin.

---

## 7. Offene Entscheidungen (priorisiert)

| # | Entscheidung | Optionen | Wirkung |
|---|---|---|---|
| **E1** | Dokumentensicht: weiterverfolgen? | (a) weitermachen, Tabellenansicht-Slice (Filter-Sprache + `bulk-update`) vorziehen; (b) auf das `Document`-Artefakt + Projektion (Phase G S3) aufsetzen und `DocumentView` als zweite Oberfläche darauf definieren; (c) einstellen und Spec auf `superseded` setzen | blockiert seit 2026-11-04; ohne Entscheidung verrottet die Spec weiter |
| **E2** | Navigationsbaum-Spec freigeben? | (a) freigeben, Plan G → V2 → V ausführen; (b) erst §6.2 (Default-Darstellung) gegen den inzwischen gebauten Karten-Graph entscheiden, dann freigeben; (c) nur Phase G (Gruppen-Dialog) vorziehen, V zurückstellen | G ist unabhängig und klein (0,5–1 Tag), V ist der große Block |
| **E3** | Status Ordnung-und-Allokation | (a) `accepted` + zwei Restpunkte als Kleinkram (empfohlen); (b) Restpunkte zuerst schließen, dann `accepted` | Doku-Wahrheit vs. „nichts Halbfertiges abnehmen“ |
| **E4** | Die zwei Restpunkte aus Spec 1 | (a) MCP `allocation.view` und REST `tree/` nachziehen (Tool-Zähler +1 → Gates); (b) §5 der Spec und `docs/features/ordering-and-allocation.md` korrigieren (Delta 0 Tools) | (b) ist billiger und hält den Vertrag ehrlich |
| **E5** | Doku-Hygiene nachziehen | `docs/superpowers/specs/index.md` hat **keinen** Eintrag für die Ordnung-und-Allokation-Spec und führt die Navigationsbaum-Spec als „no plan yet“ (der Plan existiert). Nachziehen oder Index neu erzeugen | betrifft jede künftige Triage |
| **E6** | Spec `2026-11-10-allokation-objekt-release-design.md` | Sie steht auf `proposed`, ADR-028 ist `accepted` und der Code (0139–0143, `release_service.py`, `release_views.py`, `release_tier_pin.py`) liegt auf `main`. Frontmatter nachziehen oder die Abweichung begründen | außerhalb dieses Auftrags, aber derselbe Fehlertyp |
| **E7** | Freigabe D4/O5 (Default-Ansicht der Verbindungs-Route) | (a) `trees` wird Default, sobald gebaut; (b) Karten-Graph bleibt Default, `trees` wird fünfter Modus | entscheidet, ob Spec 2 §6.2 von Spec 1 ändern darf |

---

## 8. Kurzfazit

Von vier liegenden Dokumenten ist **eines umgesetzt** (Ordnung und Allokation, P0–P6), **eines
überholt** (Backlog-Umsetzungspläne → Roadmap A–H), und **zwei sind echte, unerledigte Vorhaben**
(Navigationsbaum/Bäume-Ansicht, Dokumentensicht). Die beiden unerledigten sind nicht aus Nachlässigkeit
liegen geblieben: die eine wartet auf eine Freigabe, die andere auf eine Abhängigkeit, die selbst
ungebaut ist.
