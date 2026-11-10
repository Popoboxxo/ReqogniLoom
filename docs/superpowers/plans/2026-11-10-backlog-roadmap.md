# Backlog-Roadmap — 31 offene Issues in 8 fachlichen Phasen abbauen

Stand: 2026-11-10, nach beta.29. Entscheidungen von Daniel am 2026-11-10 eingearbeitet. Grober Plan, kein Task-Plan. Jede Phase bekommt bei Start einen eigenen Detailplan (writing-plans).

## Ausgangslage

- 31 offene Issues (vorher 56). Backlog-Sweep (PR #1727) umgesetzt, beta.29 draußen.
- Kritische Bugs und Security-Lücken sind weg.
- Ziel: alle 31 einplanen. Am Ende bleiben zwei bewusst offen: #1230 (externe Accounts, nur Daniel) und #1247 (Honcho-Upstream-Tracker).
- Nur Issue-Texte gelesen. Jede Phase startet mit einem Triage-Gate gegen `origin/main`: reproduzieren, bei "schon gefixt" schließen.

## Label-Befund: Tags sind unzuverlässig

Nur **1 von 31** Issues trägt `bug`. Der Inhalt zählt, nicht der Tag:

| Issue | Label heute | Wirklich | Folge |
|---|---|---|---|
| #598 | keins | 11 konkrete Befunde (5 Warnings, 6 Suggestions) | Nicht schließen, Phase B |
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
| A | Hygiene und Re-Labeling | #85, #1153, #1399, #1411, #1407, #946 (6, schließen) | 25 |
| B | Frontend, Inspector-Neukonzept | #598, #801, #1094, #1287, #186 (5) | 20 |
| C | Clients und MCP | #1703, #1704 (2) | 18 |
| D | Memory und Suche | #1317, #1336, #1337, #1334, #1316, #1314, #18, #1339 (8) | 10 |
| E | Requirements ↔ Architektur | #1669, #1670 (2) | 8 |
| F | Test und Qualität | #1564, #1578, #587 (3) | 5 |
| G | Dokumente, Milestones | #1374, #879 (2) | 3 |
| H | Hermes-Plugin | #1701 (1) | 2 |
| Rest | Bewusst offen | #1230, #1247 | 2 |

Dazu kommen **Vorschläge V1–V9** (Ende des Dokuments). Noch keine Issues.

## Entscheidungen (Daniel, 2026-11-10)

| # | Frage | Entscheidung |
|---|---|---|
| 1 | #1153/#1247 | #1153 schließen, #1247 bleibt als Upstream-Tracker offen (Trigger T1 aus ADR-023) |
| 2 | Phase-A-Aktionen | Feedback-Agent bereitet Schließungen und Labels vor, Liste wird vor der Ausführung gezeigt |
| 3 | #598 Umfang | Alles inkl. S2/S3 (Gott-Komponenten zerlegen, Fetching auf react-query vereinheitlichen) |
| 4 | #801 Umfang | **Inspector komplett neu denken**: Usability und Design deutlich verbessern, tiefe Analyse mit Best Practices, neues Gesamtkonzept. Kein Anbindungs-PR |
| 5 | #1094 Rest | Profil-API bauen, Schalter am Konto speichern |
| 6 | #1703 | Bericht in `docs/clients/`, CI-Smoke prüfen, sonst manuell dokumentieren |
| 7 | #18 | Nur `ai_search.query`-MCP-Tool plus optionale KI-Zusammenfassung auf `search_service` (nach #1316). Keine neue App |
| 8 | #1669/#1670 | Drei Stufen, MVP zuerst |
| 9 | #1564 | `step_type` + `text` mit stabiler Schritt-ID |
| 10 | #1578 | Vertagung aufheben: Feature-Flag, Deckel, Rate-Parity, Item-Permission |
| 11 | #879 | Erst prüfen, was von #393/#877 gebaut wurde, dann entscheiden |
| 12 | #1374 | Stufe 1: Document + Kanten + Import (Repo-first) |
| 13 | #946 | Schließen, Bluepencil deckt es ab |

**Korrektur:** Die Memory-Richtung ist schon entschieden: ADR-022 Qdrant-Vollbetrieb (Option B), ADR-023 Honcho-Vollausbau (Option A, nur dialektik-abhängige Teile warten auf T1), ADR-024 Memory-Injektion. Alle `accepted` am 2026-10-26. Die frühere Annahme "Phase D beginnt mit A/B-Entscheidung" entfällt.

## Phasen

### Phase A — Hygiene und Re-Labeling (6 schließen, kein Code)
- Schließen mit Kommentar: #85, #1153 (Verweis auf #1247), #1399 + #1411 (Messung dokumentieren), #946 (Verweis auf `frontend/src/bluepencil/`).
- #1407: Einzelpunkte prüfen. Echte Fehler in die passende Phase, Rest schließen.
- Labels: #1247, #1287, #1578, #1230.
- Ausführung: `feedback`-Agent. Liste wird Daniel vor der Ausführung gezeigt.
- Falls #946 echte Bluepencil-Lücken hat (zentrales Löschen nach Filter/Session): kleines neues Issue.

### Phase B — Frontend, Inspector-Neukonzept (5 Issues)
Vier Stränge:
1. **Konsistenz-Bugs und Refactoring aus #598 (alles):**
   - W1/S6: Typ-Probe-Fetch `GET /artifacts/{id}/` ersetzen durch `source_type`/`target_type`/`*_title` des TraceLinks.
   - W2: MetricsDashboard auf Tokens. W3: `METRIC_HELP` nach i18n. W4: ErrorBoundary ohne rohe `error.message`. W5: Workflow-Header-Overflow (erst im Browser reproduzieren).
   - S4: Redirect-Aliase `/trace-links`, `/test-cases`. S5: einheitliche CTAs.
   - S2: Gott-Komponenten zerlegen: CanvasEditor, workspace-tree, TraceabilityView, ReqTraceLinkPanel, BaselinesView, ArchitectureEditors, SplitView. Eigene Refactoring-PRs, je Komponente, mit Test vorher.
   - S3: MetricsDashboard und AuditDashboard auf react-query.
   - Vor Start prüfen, welche Zeilenzahlen und Befunde auf main noch stimmen (Review bezog sich auf v1.6.0).
2. **Inspector-Neukonzept (#801):**
   - Schritt 1: Analyse. Best Practices (Detail-Panels, Verlauf/Diff, Beziehungen) in Requirements-Tools und vergleichbaren Werkbenches, Ist-Zustand aller 7 Entity-Typen, Nutzungsaufgaben.
   - Schritt 2: Konzept und Design mit `ui-ux-designer` (Spec, Mockups, Token/Variantenvertrag mit `design-system-architect`). Inhalte mindestens: Verlauf/Diff, Trace-Links ("Was realisiert/testet das?"), Status und Workflow, IDs (verbindet #1094).
   - Schritt 3: Daniel reviewt das Konzept, erst danach Umsetzung als eigene PRs.
   - Einstieg über brainstorming-Skill.
3. **#1094 Rest und #1287:**
   - Neue Profil-Ressource für Anzeige-Präferenzen, Frontend nutzt sie statt `localStorage`. Triage-Gate: Es gibt `DisplayPreferenceService`, prüfen ob die Ressource schon existiert.
   - #1287 Format-Zeile der Markdown-Felder ein-/ausblendbar. Preference liegt in derselben Ressource.
4. **#186 UI-Konzept-Epic:** prüfen, was die Navigationsumstrukturierung (#1733) erledigt hat, Rest in Schritte teilen. Sinnvoll erst nach dem Inspector-Konzept, weil beides das Gesamtkonzept betrifft. Danach #598/#186 schließen.

### Phase C — Clients und MCP (2 Issues)
- #1703: OpenCode 1.18.x und 2.2.x gegen echten `/mcp/`: Handshake, `notifications/initialized`, GET-SSE, `tools/list` = Soll aus `docs/agent-templates/tool-manifest.json` (beta.29: 290 Tools, key-abhängig, siehe #1730), `requirement_query` mit Read-only-Key. Bericht in `docs/clients/`. V2-Service-Restart-Quirk dokumentieren. Prüfen, ob `client-smoke` den Test tragen kann, sonst manuell.
- #1704: messen, nicht raten. Code Mode (Default V2) gegen `codemode:false` (290 statt 248 Tools seit beta.29), V1-Verhalten, Auflösung der 6 Skills, Token-Kosten, Katalog-Latenz. Ergebnis: Empfehlung, Folge-Änderung nur wenn nötig. Hängt von #1703 ab.

### Phase D — Memory und Suche (8 Issues, per ADR entschieden)
Reihenfolge nach Abhängigkeit:
1. **#1317 + #1339** nach ADR-024: Drei-Ebenen-Schalter über Q1-Schlüssel, HARD_OFF, `bundle_compression` verliert den Memory-Block, Ablagen-Inventar als Doku. Defaults = heutiges Verhalten.
2. **#1334** Artefakt-Indexer (11 von 14 Typen, Hooks, Backfill, Workspace-Scope) nach ADR-022 Option B. Mit V5 `reindex_artifacts`.
3. **#1316** Hybrid-Suche in `search_service.py`: ANN-Top-k + FTS-Top-k, RRF, `mode`-Parameter `vector|keyword|hybrid` (Default `hybrid`), Recall-Messung gegen ein manuelles Set von 20 Anfragen.
4. **#1314** Qdrant-Ausbau: Payload-Index, Sparse Vectors, Quantization. Hängt an #1334.
5. **#18-Rest** `ai_search.query` als MCP-Tool plus optionale KI-Zusammenfassung, aufgesetzt auf `search_service`. Nach #1316.
6. **#1336 Dream, #1337 Honcho-Fähigkeiten** nach ADR-023 Option A. Nur die Teile, die nicht von der Dialektik abhängen, jetzt (Peer-/Workspace-Suche, Peer-Context, Session-Summaries, Scopes prüfen). Dialektik-abhängige Teile warten auf T1 (#1247). Je Fähigkeit ein Eintrag im Plan, nicht ein Block.
- Ob die Plan-Annahmen (ADR-022 "Umsetzungsschnitt") noch auf main passen, klärt das Triage-Gate.

### Phase E — Requirements ↔ Architektur (2 Issues, drei Stufen)
Zuerst Spec/ADR-Check (ADR-005 ist betroffen, `ARCHITECTURE_DEPTH_TO_LEVEL`), dann:
- **Stufe 1 (MVP):** deklarierte Spezifikationsebene als zweite Quelle plus abgeleitete Ebene aus Allokation. Filter `?allocated=` und `?level=` in REST, MCP, UI. Begriff "V-Modell-Ebene" ersetzen. Migration der 717 Requirements mit undefinierter Ebene, mit Dry-Run-Bericht.
- **Stufe 2:** Allokation als eigenes Objekt mit Lebenszyklus.
- **Stufe 3:** Beständigkeit ab Release (Sperre, Change Request, Impact-Vorschau) und Rigor-Regler.
- Jede Stufe eigener PR. #1669 schließt mit Stufe 1, #1670 mit Stufe 3.

### Phase F — Test und Qualität (3 Issues)
- **#1564:** Schritt `{id, step_type: given|when|then|and|but, text}`. Normalisierung alter Schritte beim Lesen. Serializer und MCP-Schema deckungsgleich. Migration nur wenn nötig.
- **#1578:** `WORKFLOW_TRANSITIONED` emittieren. Auto-Assessment hinter Feature-Flag (Default aus). Celery-Beat mit Dedupe und Throttling. `QUAL-P1`-Deckel. MCP-Rate-Parity. Item-Level-Permission bei Assessment-Reads. Nur Extended-Tier, nur WARNING, nie Baseline-blockierend. Aufwand laut Issue 4–6 Tage.
- **#587:** Promptfoo. Blocker ist weg (`prompt_resolver.py` existiert). `export_promptfoo_configs`, `backend/application/prompt_testing/cases/*.yaml`, CI-Job mit Mock-Provider. Die promptfoo-Treffer im Repo gehören sonst nur zu `.agent-meta`, nicht verwechseln.

### Phase G — Dokumente und Milestones (2 Issues)
- **#879:** zuerst Triage, was von #393 (MOE/MOP/TPM) und #877 (LogicalFunction) gebaut wurde (beide geschlossen). Dann entscheiden: Milestone dort einhängen, schlanker Milestone (Name, Zieldatum, Status, Review-Typ, Baseline-Bindung) oder schließen. Achtung: #1374 führt `WorkItem:Milestone` ein. Überschneidung zuerst klären, damit es nur eine Milestone-Entität gibt.
- **#1374:** Stufe 1: `Document` mit Subtypen, Lifecycle, Kanten zu Requirements/ADR/Risk/Issue, einmaliger Import des Altbestands (Betriebsart B, Repo-first). Stufe 2: `WorkItem` mit Zustand. Stufe 3: Loom-first mit Projektion nach `.md`. Konzept: `docs/concepts/2026-10-16-dokument-artefakte-workitem.md`. Erst nach Phase E, weil Kanten und Allokation zusammenhängen.

### Phase H — Hermes-Plugin (1 Issue)
- **#1701:** Requirements-Liste, Detail, Anlegen, Bearbeiten im Plugin `integrations/hermes-plugin/reqogniloom`, auf aktuellem main. `ConnectedView` bleibt Hub, neue `View`-Zustände `requirements`, `requirement-detail`, `requirement-form`. `api.ts` behält die Härtung von main (Fehlerumschläge, Seitenfolge in `listWorkspaces`, 15-s-Timeout, Nicht-JSON-Bodies). Alter Branch `e0219a76` nur als Referenz.

### Rest (bewusst offen)
- **#1230** externe Accounts (W1–W5). Kein Code. Danach Publish-Workflows scharf schalten.
- **#1247** Honcho-Dialektik-Upstream-Tracker. Schließt, wenn Trigger T1 erfüllt ist (`memory.ask` mit `degraded:false`).

## Reihenfolge und Abhängigkeiten

- A zuerst (kostet wenig). Dann C, B-Strang 1 und 3 sowie D parallel möglich, weil getrennte Dateien.
- B-Strang 2 (Inspector) beginnt mit Analyse und Konzept sofort, Umsetzung erst nach Review durch Daniel.
- D vor F-#587 sinnvoll, nicht zwingend.
- E vor G. #879 und #1374 hängen an der Milestone-Frage.
- H zuletzt.

## Offene Entscheidungen

1. Phase A: Freigabe der vorbereiteten Schließ- und Label-Liste, bevor ausgeführt wird.
2. Phase B: Review des Inspector-Konzepts, bevor Umsetzung startet.
3. Phase G: #879 nach der Triage.
4. Vorschläge V1–V9: welche als Issues anlegen.

## Regeln pro Phase

- Branch von `origin/main`, nie lokales `main`.
- Git-Mutationen nur über den `git`-Agenten.
- Triage-Gate zuerst, dann TDD.
- Volle Testläufe nur sequentiell.
- PR-Body mit `Fixes #N` nur für wirklich erledigte Issues.
- Neue Issues während der Phasen: in die passende Phase einsortieren, Zähler nachziehen.

## Vorschläge (noch keine Issues)

- **V1:** Einheitliche Fehler- und Leer-Zustände je Entity-Liste (B).
- **V2:** Lint gegen hartcodierte Farben und Strings (B).
- **V3:** OpenCode-2-Ergebnisse in Client-Doku und `client-smoke` (C).
- **V4:** Admin-Statusseite "Memory": aktive Ablage, Indexer-Rückstand, letzter Dream (D).
- **V5:** Management-Command `reindex_artifacts`, resumable (D, zu #1334).
- **V6:** Allokations-Filter und Spezifikationsebene in Liste und Trace-Matrix (E). Wird von Stufe 1 teils abgedeckt.
- **V7:** Coverage-Ansicht "Requirements ohne Allokation je Spezifikationsebene" (E).
- **V8:** Testfall-Ableitung aus Given/When/Then, Schritt-Ergebnisse im TestRun (F, nach #1564).
- **V9:** Promptfoo als CI-Gate für geänderte Templates (F, nach #587).
