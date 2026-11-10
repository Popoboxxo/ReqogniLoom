# Backlog-Roadmap — 31 offene Issues in 8 fachlichen Phasen abbauen

Stand: 2026-11-10, nach beta.29. Entscheidungen von Daniel am 2026-11-10 eingearbeitet. Grober Plan, kein Task-Plan. Jede Phase bekommt bei Start einen eigenen Detailplan (writing-plans).

## Ausgangslage

- 31 offene Issues (vorher 56). Backlog-Sweep (PR #1727) umgesetzt, beta.29 draußen.
- Kritische Bugs und Security-Lücken sind weg.
- Ziel: alle 31 einplanen. Am Ende bleiben sechs bewusst offen: #1230 (externe Accounts, nur Daniel), #1247 (Honcho-Upstream-Tracker), das neue Inspector-Konzept-Issue bis zur Umsetzung der freigegebenen Spec, die zwei neuen Feature-Issues aus #18 (B: Artefakt-Zusammenfassung, C: zyklische Zusammenfassungen) und das neue Issue zu `page_size` (Backlog, Bündel REST-Kleinkram).
- Nur Issue-Texte gelesen. Jede Phase startet mit einem Triage-Gate gegen `origin/main`: reproduzieren, bei "schon gefixt" schließen.

## Label-Befund: Tags sind unzuverlässig

Nur **1 von 31** Issues trägt `bug`. Der Inhalt zählt, nicht der Tag:

| Issue | Label heute | Wirklich | Folge |
|---|---|---|---|
| #598 | keins | 11 Befunde, davon 9 auf beta.29 schon erledigt, offen S2 und S3 | Phase B1, danach schließen |
| #1247 | keins | Regression, Ursache im Honcho-Vendor | `bug` + `upstream`, bleibt als Tracker offen |
| #1287 | keins | kleines UX-Feature | `enhancement`, `low` |
| #1578 | keins | Feature | `enhancement` |
| #1230 | keins | Infra-Roadmap | `infra` |
| #85 | keins | Review v1.0.0, veraltet | schließen |
| #1153 | `bug` | Dublette von #1247 | schließen |
| #1399, #1411 | `qa` | Planner-Verhalten, kein Fehler | schließen |
| #1407 | `qa` | Sammel-Lows | Einzelpunkte prüfen |

## Übersicht

| Phase | Thema | Issues | Offen danach |
|---|---|---|---|
| A | Hygiene und Re-Labeling | #85, #1153, #1399, #1411, #1407, #946 (6, schließen), +1 neues `page_size`-Issue | 26 |
| B | Frontend (B1 Hygiene, B2 Inspector-Konzept) | #598, #801, #1094, #1287, #186 schließen, +1 neues Inspector-Konzept-Issue | 22 |
| C | Clients und MCP | #1703, #1704 (2) | 20 |
| D | Memory und Suche (fast alles gebaut, Beweisführung) | #1317, #1336, #1337, #1334, #1316, #1314, #18, #1339 schließen, +2 neue Feature-Issues (B, C) | 14 |
| E | Requirements ↔ Architektur | #1669, #1670 (2) | 12 |
| F | Test und Qualität | #1564, #1578, #587 (3) | 9 |
| G | Dokumente, Milestones | #1374, #879 (2) | 7 |
| H | Hermes-Plugin | #1701 (1) | 6 |
| Rest | Bewusst offen | #1230, #1247, Inspector-Konzept, D-B, D-C, `page_size` | 6 |

Alle Zähler enthalten die neuen Issues der jeweiligen Phase. Ein optionales Issue zu Punkt 4 aus #1407 (Bearer mit API-Key, nur falls Doku-Lücke) ist nicht eingerechnet.

Dazu kommen **Vorschläge V1–V9** (Ende des Dokuments). Noch keine Issues.

## Entscheidungen (Daniel, 2026-11-10)

| # | Frage | Entscheidung |
|---|---|---|
| 1 | #1153/#1247 | #1153 schließen, #1247 bleibt als Upstream-Tracker offen (Trigger T1 aus ADR-023) |
| 2 | Phase-A-Aktionen | Feedback-Agent bereitet Schließungen und Labels vor, Liste wird vor der Ausführung gezeigt |
| 3 | #598 Umfang | S2/S3 umsetzen. **Präzisiert 2026-11-10:** S2 nach technischer Zuständigkeit (Hotspot-Analyse, Kohäsions-Clustering, Literatur), keine harte Zeilengrenze. W1–W5, S4, S5 sind auf beta.29 schon erledigt |
| 4 | #801 Umfang | **Inspector komplett neu denken**, am 2026-11-10 bestätigt: Der Inspector ist auf beta.29 schon in 10 Typen eingebunden, #801 wird geschlossen, neues Konzept-Issue mit Ist-Analyse, Best Practice, Spec, Freigabe-Gate |
| 5 | #1094 Rest | **Gegenstandslos:** Der Endpunkt existiert seit #1096. #1094 wird geschlossen |
| 6 | #1703 | Bericht in `docs/clients/`, CI-Smoke prüfen, sonst manuell dokumentieren |
| 7 | #18 | **Präzisiert 2026-11-10:** Scope A (Zusammenfassung je Suchanfrage) als optionaler Parameter `include_summary` an `artifact.search` (Delta 0 Tools, kein neues Tool). B (Zusammenfassung eines Artefakts) und C (zyklische Zusammenfassungen) werden neue Feature-Issues. #18 danach schließen mit Verweis |
| 8 | #1669/#1670 | Drei Stufen, MVP zuerst. **Präzisiert 2026-11-10:** Stufe 1 ist auf beta.29 schon gebaut (ADR-027). D9 Mehrfachallokation = Konflikt anzeigen, nicht auflösen, **seit 2026-11-10 per Konfiguration schaltbar** (Kardinalität `single|multiple`, Warnstufe `info|warning|blocker`, führende Kante `is_primary`). D10 Freigabeeinheit = **beides** (Element-Release und optionaler Einzel-Release, mit Vorrangregel). D12 Inhalt einfrieren = **abhängig vom Rigor** (nur Extended friert den Inhalt ein) |
| 9 | #1564 | `step_type` + `text` mit stabiler Schritt-ID |
| 10 | #1578 | Vertagung aufheben: Feature-Flag, Deckel, Rate-Parity, Item-Permission |
| 11 | #879 | Erst prüfen, was gebaut wurde. **Ergebnis 2026-11-10: vollständig gebaut, schließen** |
| 12 | #1374 | Stufe 1: Document + Kanten + Import (Repo-first). **Stand 2026-11-10:** S1, S2, S4 gebaut, offen nur S3. **12b: Generator und Adoption im Server, Zustellung durch CI und Agenten, Agentendefinition als Teil der Harness-Plugin-Skills** |
| 13 | #946 | **Geändert nach Review 2026-11-10: als nicht geplant schließen.** Ursprünglich "Bluepencil deckt es ab", das stimmt nicht mehr: Der Layer wurde am 2026-11-02 bewusst entfernt (Commit `1ad7ef17`, #1643) |

**Korrektur:** Die Memory-Richtung ist schon entschieden: ADR-022 Qdrant-Vollbetrieb (Option B), ADR-023 Honcho-Vollausbau (Option A, nur dialektik-abhängige Teile warten auf T1), ADR-024 Memory-Injektion. Alle `accepted` am 2026-10-26. Die frühere Annahme "Phase D beginnt mit A/B-Entscheidung" entfällt.

## Phasen

### Phase A — Hygiene und Re-Labeling (6 schließen, +1 neues Issue, kein Code, Plan: `2026-11-10-phase-a-hygiene.md`)
- Schließen mit Kommentar: #85, #1153 (Verweis auf #1247), #1399 + #1411 (Messung dokumentieren).
- **#946: als nicht geplant schließen** (Entscheidung nach Review). Der Bluepencil-Layer wurde am 2026-11-02 bewusst entfernt (`1ad7ef17`), die frühere Begründung "Bluepencil deckt es ab" ist hinfällig.
- **#1407** (am Code verifiziert): `offset` gewollt, DELETE-`change_reason` per Query bereits behoben (`parse_change_reason`), `/traceability/` gewollt, `page_size <= 0` fällt still auf den Standard zurück (**neues kleines Issue**), Bearer mit API-Key bleibt zu prüfen. Dann schließen.
- Labels: #1247, #1287, #1578, #1230.
- Ausführung: `feedback`-Agent. Liste wird Daniel vor der Ausführung gezeigt.

### Phase B — Frontend (5 Issues, zwei Pläne)
Das Triage-Gate (2026-11-10, origin/main 4f8aa29f) hat den Umfang stark verändert. Ausführbare Pläne: `2026-11-10-phase-b1-frontend-hygiene.md` und `2026-11-10-phase-b2-inspector-concept.md`.

**Schon erledigt auf beta.29 (nur schließen, mit Beleg):**
- #598 W1–W5, S4, S5 (Batch-Auflösung, Tokens, i18n, ErrorBoundary, `flex-wrap`, Redirects, CTA-Labels).
- #1094: Endpunkt `users/me/display-preferences/` seit #1096.
- #186: alle 19 Sub-Issues geschlossen, `ui-ratchet.test.ts` friert Kennzahlen ein.
- #1287: `shared/MarkdownField` mit Preference `ui.markdown.toolbar`. Einsatz wird per Test belegt.

**B1 Frontend-Hygiene:**
- S3: MetricsDashboard (`queries/metrics.ts`) und audit-dashboard auf react-query.
- S2: Hotspot-Analyse nach Zuständigkeit (Churn × Komplexität, Kohäsionsgraph der Deklarationen). Zerlegt wird nur, was mehrere unabhängige Zuständigkeiten hat. `audit-dashboard.tsx` (1726 Zeilen) ist der erste, verstandene Fall.
- Schließen: #1094, #186, #1287, #598.

**B2 Inspector-Neukonzept (#801):**
- #801 schließen (Anbindung erledigt), neues Konzept-Issue anlegen (+1 Issue).
- Ist-Analyse, Usability-Prüfung an fünf Aufgaben, Best-Practice-Recherche mit Quellen, Spec inklusive Trace-Spine und Token-Vertrag, Freigabe-Gate. Erst danach Umsetzungsplan.

**Zähler Phase B:** −5 Issues (#598, #801, #1094, #1287, #186) +1 (Inspector-Konzept) = −4.

### Phase C — Clients und MCP (2 Issues)
- #1703: OpenCode 1.18.x und 2.2.x gegen echten `/mcp/`: Handshake, `notifications/initialized`, GET-SSE, `tools/list` = Soll aus `docs/agent-templates/tool-manifest.json` (beta.29: 290 Tools, key-abhängig, siehe #1730), `requirement_query` mit Read-only-Key. Bericht in `docs/clients/`. V2-Service-Restart-Quirk dokumentieren. Prüfen, ob `client-smoke` den Test tragen kann, sonst manuell.
- #1704: messen, nicht raten. Code Mode (Default V2) gegen `codemode:false` (290 statt 248 Tools seit beta.29), V1-Verhalten, Auflösung der 6 Skills, Token-Kosten, Katalog-Latenz. Ergebnis: Empfehlung, Folge-Änderung nur wenn nötig. Hängt von #1703 ab.

### Phase D — Memory und Suche (8 Issues, Plan: `2026-11-10-phase-d-memory-suche.md`)
Das Triage-Gate (2026-11-10, origin/main 8d2ea4f6) hat die frühere Planung widerlegt: Plan A (`docs/plans/2026-10-21-plan-a-memory-und-suche.md`) ist auf beta.29 weitgehend umgesetzt. Die Phase besteht aus Beweisführung plus einer kleinen Neuentwicklung.

**Erledigt, mit Beleg schließen:**
- #1334 Artefakt-Indexer (`application/artifact_indexer.py`, Commands `index_artifact_vectors`, `backfill_embeddings`).
- #1314 Qdrant (Sparse `bm25`, Payload-Index, Quantisierung, `artifact_vector_store.py`).
- #1316 Hybrid-Suche (`_rrf_fuse`, `mode`-Parameter, `test_search_recall.py`).
- #1317 Ablagen und Kopplung (`memory.W001`/`W002`, Embedding-Modell je Zeile, `deploy/README.md`).
- #1336 Dream (`consolidate`, periodische Aufgabe). Live-Beleg fehlt, kein Honcho-Stack erreichbar.
- #1337 Honcho-Fähigkeiten (Peer-Suche, Peer-Context, Session-Summaries, Webhooks, native Scopes).
- #1339 Injektion je Aktivität (`MEMORY_HARD_OFF_SLOTS`, `injection_policy.py`, REST, `memory_injected`).

**Neu gebaut:** #18 als `include_summary` an `artifact.search` (MCP und REST, Default aus, kein neues Tool). Ein `SearchSummaryService` nach dem Muster von `BundleCompressionService`, Slot `search_summary` auf `MEMORY_HARD_OFF_SLOTS`.

**Neue Feature-Issues:** B (Zusammenfassung eines einzelnen Artefakts, Bezug Inspector) und C (zyklische Zusammenfassungen je Artefakttyp/Workspace, braucht ein Konzept).

### Phase E — Requirements ↔ Architektur (2 Issues, Plan: `2026-11-10-phase-e-requirements-architektur.md`)
Das Triage-Gate (2026-11-10, origin/main f20f913e) zeigt: **Stufe 1 ist gebaut** (ADR-027: leaf-relative Stufen aus der Allokation, `WorkspaceTier`-Leiter, `level_source`, `allocation_intent`, Filter `?allocated=`/`?level=`, MCP `allocation.query`, `tier_key` im Baseline-Snapshot). Ebenfalls vorhanden: Workflow-Freeze für Position (`artifact_freeze.py`) und `ArtifactVersion`.

- **Task 1:** Stufe 1 abnehmen, #1669 schließen.
- **Task 2:** ADR-028 und Spec für Stufen 2 bis 4 mit D9, D10 (beides), D12 (rigor-abhängig). Freigabe-Gate durch Daniel.
- **Task 3:** Mehrfachallokation konfigurierbar (D9: Q1-Schlüssel `allocation.cardinality`, `allocation.conflict_severity`, `allocate(mode=...)`, Audit-Regel `allocation.multiple`), Naming-Layer (D2/D7/D8, Tier `module`).
- **Task 4:** Stufe 2: Objekt `Allocation` (`draft|released|revoked`, `is_primary`), Dual-Write mit `TraceLink(allocated-to)`, Backfill der Bestandskanten, Coverage in REST, MCP (Delta 0 Tools) und UI.
- **Task 5:** Stufe 3: Element-Release-Kaskade, Einzel-Release, Sperren mit 409 und CR-Verweis, Impact-Vorschau, Rigor-Kopplung.
- **Task 6:** Stufe 4: gepinnte Ebene je Release in Baselines, Audit Live ↔ Baseline.
- **Task 7:** #1670 schließen.
Tasks 4 bis 6 starten erst nach Freigabe von ADR-028 und Spec.

### Phase F — Test und Qualität (3 Issues, Plan: `2026-11-10-phase-f-test-qualitaet.md`)
Triage-Gate (2026-11-10): **#587 ist gebaut** (`export_promptfoo_configs`, 27 Szenarien, CI-Job "Prompt Regression (promptfoo, echo)"). Die Spec-Index-Aussage "entirely missing" ist veraltet und wird korrigiert. #1564 und #1578 sind offen.

- **#587:** belegen, Abdeckung Slots ↔ Szenarien testen, Doku korrigieren, schließen.
- **#1564:** Schritt `{id, step_type, text}`, `normalize_steps` (Legacy `{step, expected_result}` → `when` + `then`), Datenmigration mit Trockenlauf, REST/MCP-Schema (Delta 0 Tools), Frontend-Widget, `steps_to_gherkin`. Gherkin-Parser und Schritt-Ergebnisse im TestRun bleiben V8.
- **#1578:** `WORKFLOW_TRANSITIONED` emittieren (heute nie), Konsument am Event-Bus, Feature-Flag (Default aus), nur Extended, nur WARNING, **ein Service-Agent-Key je Mandant** (Entscheidung 10b), Drosselung und Inhalts-Hash-Dedupe, periodischer Sweep mit Batch-Deckel, QUAL-P1-Deckel, MCP-Rate-Parität, Item-Level-Permission bei Assessment-Reads.

### Phase G — Dokumente und Milestones (2 Issues, Plan: `2026-11-10-phase-g-dokumente-milestones.md`)
Triage-Gate (2026-11-10, origin/main 3563515f): **#879 ist vollständig gebaut** (Plan B B6: Entität `Milestone` mit Review-Typ, Baseline-Bindung, Audit-Snapshot, REST, MCP `milestone.*`, UI `MilestoneList`). **#1374 S1, S2, S4 sind gebaut** (`Document`, `WorkItem`, Lifecycle, Freeze, REST/MCP, Events, resume/Checkpoints/Heartbeat). Offen ist nur **S3 (Projektion und Adoption)**. Die Überschneidung `Milestone` ↔ `WorkItem.Kind.MILESTONE` ist geklärt: verschiedene Konzepte, nur Doku-Bedarf.

- **Task 1:** #879 belegen, Abgrenzung in `DOMAIN_MODEL.md`, schließen.
- **Task 2:** Server: `Document`-Felder (`owner_mode`, `source_path`, `source_sha256`, `projection_mode`, `projected_sha256`, `projected_version`), deterministischer Renderer, `DocumentProjectionService` (project, status mit Hash-Abgleich nach Konzept §7.2, adopt).
- **Task 3:** REST und MCP: `document.project`, `document.projection_status`, `document.adopt` (Tool-Zahl 290 → 293, Zähler-Gates).
- **Task 4:** CI-Weg: `scripts/clients/project_documents.py` und Workflow-Vorlage, Branch plus PR, nie `main`.
- **Task 5:** Agent `document-steward` mit Skill `document-projection` in den Harness-Plugins (Entscheidung 12b).
- **Task 6:** #1374 schließen. Vertagt bleiben T1 (Typ `Task`) und T2 (Text-Spans).
**Entscheidung 12b (2026-11-10):** Der Server rendert und prüft nur. Zustellung durch CI und Agenten. Keine Repo-Zugangsdaten im Server.

### Phase H — Hermes-Plugin (1 Issue, Plan: `2026-11-10-phase-h-hermes-plugin.md`)
Triage-Gate (2026-11-10): Die Requirements-Ansichten fehlen auf `main` (Plugin: Connect, Connected, Interviews). **Wichtig:** Das Backend hat sich seit dem alten Branch `e0219a76` geändert. `Requirement.level` ist abgeleitet und schreibgeschützt (ADR-005/027), Updates brauchen `version` (Optimistic Lock) und je Preset einen `change_reason`. Der Plan baut deshalb neu und übernimmt vom alten Branch nur die Struktur.

- **Task 1:** REST-Vertrag prüfen und festschreiben.
- **Task 2:** `api.ts` (list, get, create, update mit erhaltener Härtung) und `state.ts` (neue `View`-Zustände, Aktionen).
- **Task 3:** Ansichten `RequirementsList`, `RequirementDetail`, `RequirementForm`, Einstieg in `ConnectedView`.
- **Task 4:** README und Clientdoku, Gates, #1701 schließen. Alten Remote-Branch löschen nur auf Anweisung.

### Rest (bewusst offen)
- **#1230** externe Accounts (W1–W5). Kein Code. Danach Publish-Workflows scharf schalten.
- **#1247** Honcho-Dialektik-Upstream-Tracker. Schließt, wenn Trigger T1 erfüllt ist (`memory.ask` mit `degraded:false`).
- **Inspector-Konzept** (neu, Phase B2). Schließt nach der Umsetzung der freigegebenen Spec.
- **D-B** und **D-C** (neu, Phase D): Zusammenfassung eines Artefakts, zyklische Zusammenfassungen. Beide brauchen ein eigenes Konzept.
- **`page_size`** (neu, Phase A): stilles Zurückfallen bei Werten ≤ 0. Backlog, Bündel REST-Kleinkram (kein Task in einem der Phasenpläne).

## Ausführungsreihenfolge

Aufwand grob relativ (S klein, M mittel, L groß), kein Zeitversprechen. Abhängigkeiten stehen im Plan der jeweiligen Phase.

| Welle | Phasen | Aufwand | Parallel möglich | Voraussetzung |
|---|---|---|---|---|
| 1 | **A** Tracker (S), **D** Beweisführung + `include_summary` (M), **C** Verifikation (M) | klein bis mittel | ja, getrennte Dateien. C startet einen Docker-Stack (Speicher beachten) | Freigabe der Schließliste (A) |
| 2 | **B1** Frontend-Hygiene (M), **B2** Inspector-Analyse und Spec (M), **F-#587** belegen (S) | mittel | B1 ∥ B2 | keine |
| 3 | **F** #1564 und #1578 (L), **E** Tasks 1–3 und ADR-028 mit Freigabe-Gate (M), **H** Hermes-Plugin (M) | groß | F ∥ H; E nach Spec-Freigabe | Freigabe ADR-028 für E Stufe 2 bis 4 |
| 4 | **E** Stufen 2–4 (L), **G** S3 Projektion und Adoption (L), **B2** Umsetzung (L) | groß | G ∥ B2; E eigene Migrationen | Spec-Freigabe (E, B2), Welle 3 für die Zähler-Gates von G |

Abhängigkeiten im Einzelnen:
- **G hängt nicht mehr an E.** Das Triage-Gate hat gezeigt, dass `Document` und `WorkItem` (#1374 S1, S2, S4) gebaut sind. S3 braucht keine Allokation.
- **F-#587 und D (`search_summary`)** hängen lose zusammen: Das Szenario für den neuen Slot kommt nach D in den Katalog.
- **C** ist unabhängig. G verwendet keinen Code aus C (eigener JSON-RPC-Helfer).
- **B2-Umsetzung** hängt an der Freigabe der Spec durch Daniel. Danach entsteht ein eigener Umsetzungsplan (Phase B3).

## Querschnittsregeln

1. **Frische-Check vor jeder Phase.** `main` bewegt sich, Pläne veralten (Beispiel: Bluepencil wurde entfernt). Vor dem Start einer Phase:
   - `git fetch origin +refs/heads/main:refs/remotes/origin/main` (über den `git`-Agenten; `remote.origin.fetch` ist auf einen Tag verengt, ein einfaches `git fetch origin` aktualisiert `origin/main` nicht).
   - `python scripts/check_plan_refs.py docs/superpowers/plans/<plan>.md` (gegen einen Checkout von `origin/main`). Gemeldete Pfade prüfen: Neuanlagen sind erwartet, entfernte Dateien nicht.
   - Das Triage-Gate des Plans erneut lesen: Ist das Issue inzwischen erledigt?
2. **Migrationen.** Jede Phase sagt "nächste freie Nummer". Phasen E, F und G legen Migrationen an. PRs mit Migrationen werden nacheinander gemergt, ein später gemergter PR rebased und renummeriert. Prüfung: `python manage.py makemigrations --check --dry-run`. Neue tenant-scoped Tabellen brauchen eine RLS-Policy-Migration (`test_rls_coverage.py`).
3. **MCP-Tool-Zähler.** Heute 290. Nur Phase G ändert ihn (+3 auf 293). Alle anderen Phasen sind Delta 0 und erweitern bestehende Tools. Jede Änderung: `python manage.py export_tool_manifest`, Drift-Gate und Zähler-Gates (`docs/agent-templates/test_meta_tool_count_drift.py`, `test_doc_surface_consistency.py`) grün.
4. **Git- und PR-Ablauf.** Branch von `origin/main`, Git nur über den `git`-Agenten. Commit-Nachricht und PR-Text als Dateien vorgeben (`git commit -F`, `--body-file`), damit der Trailer `Co-Authored-By: Claude Sonnet 5.5` nicht umgeschrieben wird. Merge als Squash nach grüner CI, kein Admin-Bypass. Ein Merge dauert wegen `set-1-core` und der E2E-Shards etwa 10 bis 15 Minuten.
5. **Ressourcen.** Host hat etwa 5,8 GiB RAM: volle Backend-, Frontend- und E2E-Läufe nur nacheinander. Phase C startet zusätzlich einen Compose-Stack.
6. **Schließen von Issues** nur nach Freigabe durch Daniel, mit Kommentar und Beleg (Datei:Zeile, Commit, Test). Kein `Fixes`-Keyword in Plan-PRs.
7. **Neue Issues** aus den Phasen: in die Tabelle oben eintragen und die Zähler nachziehen.

## Risiken

| Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|
| Pläne veralten, bevor sie laufen | falsche Arbeit (Beispiel #946) | Frische-Check (Regel 1), Triage-Gate je Phase |
| Migrationsnummern kollidieren (E, F, G) | PR bricht nach dem Merge eines anderen | Regel 2, nacheinander mergen |
| Phase E Stufen 2 bis 4 und G sind groß | lange Laufzeit, Regressionsrisiko | je Stufe ein PR, ADR/Spec-Gate vor dem Code, Ausführung in Welle 4 |
| LLM-Kosten durch Auto-Assessment (F) und `include_summary` (D) | unerwartete Kosten | Feature-Flag Default aus, Drosselung, Deckel, Service-Agent-Key |
| Dual-Source-Dokumente (G): Repo und Loom laufen auseinander | stille Überschreibung | Statusmatrix fail-loud, nie Push auf `main`, Adoption mit Hash-Prüfung |
| Zwei Freigabepfade (E, D10 "beides") | Sperre wird umgangen | Vorrangregel in der Spec, Test "Einzel-Release umgeht die Element-Sperre nicht" |

## Release-Vorschlag

Nur ein Vorschlag, Daniel entscheidet: **beta.30** nach Welle 1 (A, C, D), **beta.31** nach Welle 2 und 3 (B1, F, H, E Task 1 bis 3), **beta.32** nach Welle 4 (E Stufen 2 bis 4, G, B2). Release-Hygiene nach `docs/` und dem Release-Agenten.

## Offene Entscheidungen

1. Phase A: Freigabe der vorbereiteten Schließ- und Label-Liste, bevor ausgeführt wird (enthält jetzt #946 als "nicht geplant", Begründung Bluepencil entfernt).
2. Phase B: Review des Inspector-Konzepts, bevor Umsetzung startet.
3. Phase E: Freigabe von ADR-028 und Spec vor Stufe 2 bis 4. Phase B2: Freigabe der Inspector-Spec.
4. Vorschläge V1–V9: welche als Issues anlegen.

## Regeln pro Phase

- Branch von `origin/main`, nie lokales `main`.
- Git-Mutationen nur über den `git`-Agenten.
- Triage-Gate zuerst, dann TDD.
- Volle Testläufe nur sequentiell.
- PR-Body mit `Fixes #N` nur für wirklich erledigte Issues.
- Neue Issues während der Phasen: in die passende Phase einsortieren, Zähler nachziehen.

## Vorschläge (noch keine Issues, Stand nach Review 2026-11-10)

| # | Vorschlag | Phase | Stand |
|---|---|---|---|
| V1 | Einheitliche Fehler- und Leer-Zustände je Entity-Liste | B | offen, noch kein Task |
| V2 | Lint gegen hartcodierte Farben und Strings | B | offen, noch kein Task. Der `ui-ratchet.test.ts` deckt Hex-Farben schon teilweise ab, vor dem Anlegen prüfen |
| V3 | OpenCode-2-Ergebnisse in Client-Doku und `client-smoke` | C | **abgedeckt** durch Phase C Task 5 |
| V4 | Admin-Statusseite "Memory" | D | **vermutlich vorhanden** (`components/Memory/MemoryPage.tsx`, Memory-Admin). Vor dem Anlegen prüfen |
| V5 | Command `reindex_artifacts` | D | **vorhanden** als `index_artifact_vectors` und `backfill_embeddings`. Entfällt |
| V6 | Allokations-Filter und Ebene in Liste und Trace-Matrix (UI) | E | Filter im Backend vorhanden (`?allocated=`, `?level=`). UI-Teil prüfen, Coverage-Anzeige steht in Phase E Task 4 Step 6 |
| V7 | Coverage-Ansicht "Requirements ohne Allokation je Ebene" | E | **abgedeckt** durch Phase E Task 4 Step 6 |
| V8 | Testfall-Ableitung aus Given/When/Then, Schritt-Ergebnisse im TestRun | F | offen, baut auf #1564, bleibt Vorschlag |
| V9 | Promptfoo als CI-Gate für geänderte Templates | F | **vorhanden** (CI-Job "Prompt Regression" läuft auf PRs). Entfällt |

Offen für die Anlage als Issue bleiben V1, V2, V8 und, nach Prüfung, V4 und V6.
