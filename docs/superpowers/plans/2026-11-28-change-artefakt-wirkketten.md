# Umsetzungsplan: Change-Artefakt als Wirkketten-Knoten

> **Status:** Entscheidungen D1–D18/O1/O3 sind getroffen (2026-11-28); die
> Review-Matrix (Konzept, DB, API, Security, Backend, UI) ist durchlaufen und
> die Auflagen sind eingearbeitet. **Re-Review vor G0**, keine Task begonnen.
> **Review-Protokoll:** [`../../reviews/2026-11-28-change-artefakt-wirkketten-review.md`](../../reviews/2026-11-28-change-artefakt-wirkketten-review.md).
> **Spec:** [`../specs/2026-11-28-change-artefakt-wirkketten-design.md`](../specs/2026-11-28-change-artefakt-wirkketten-design.md)
> **Basis:** `main` `c5b55108` (2026-11-28).
> **Annahmen:** D1 = Summary primär + Addendum; D2 = Gate auf `submitted`;
> D3 = Hard default, semantisch opt-in, **global + Workspace-Policy**;
> D5 = eigenes Preset-Flag; D6 = eigene Chain-Tabelle; D7 = Trigger-Policy
> (`manual` Default, `on_submit`/`on_write`/`scheduled` optional);
> D8 = `criteria-list`-Objekte; D9 = sync ≤ Cap, Celery darüber;
> O1 = Freitext nur mit Begründung; O3 = standard ohne Hinweis.
> **Schätzung:** ≈ 21 Personentage (S0–S7) nach den Review-Auflagen; kritischer Pfad S1 → S3 → S4 → S5 → S6.

## 1. Zielbild in einem Satz

Ein Change Request belegt im höchsten Rigor maschinenlesbar, **was** er ändert
(Change Set), **was davon betroffen** ist (Impact Set mit Wirkketten) und
**warum** (Change Reason); Genehmiger sehen alles in einem Kontext-Read, und die
KI-Ableitung liefert direkt testbare Akzeptanzkriterien.

## 2. Slice-Übersicht

| Slice | Inhalt | Ergebnis | Tage |
|---|---|---|---|
| S0 | Entscheidungen, ADR, Messbasis | D1–D18/O1–O5 bestätigt, `blocking`-Fixtures, ADR-033 `proposed` | 1,0 |
| S1 | P1-2 Smart Refinement | AC als `criteria-list`-Objekte + `verification_method` | 1,5 |
| S2 | P1-3 Freigabe-Kontext | `change_request.impact_context` inkl. Policy + Ketten | 1,5 |
| S3 | Impact-Datenmodell | Run/Finding/Chain + Constraints + RLS + Diff-Set | 3,0 |
| S4 | Wirkketten-Engine + Policy | Content-Fingerprint, Hierarchie-Union, Trigger, LLM | 4,5 |
| S5 | Extended-Gate + Summary | gemeinsame Precondition, Gate, Summary, Fehlercodes | 2,0 |
| S6 | CR-Detailansicht | Change Set, Analyse, Findings/Ketten, Rollen, Transitionen, A11y, Review-Queue-Einstieg | 5,5 |
| S7 | Doku, Manifest, Rollout | Tool-Manifest, MCP/REST-Surface, Rate-Limit/Retention, Evidence | 2,0 |

**Gates**

| Gate | Nach | Bedingung |
|---|---|---|
| G0 | S0 | D1–D18/O1/O3 entschieden; ADR-033 angelegt; Review-Matrix abgeschlossen; keine offenen Blocker. |
| G1 | S1 | Ableitungs- und Persistenz-Tests grün; Prompt-Fixtures aktualisiert. |
| G2 | S2+S3 | `impact_context` liefert echte Daten; RLS-/Tenant-Tests grün. |
| G3 | S4+S5 | Engine deterministisch, Caps greifen, `extended`-Gate blockiert korrekt. |
| G4 | S6+S7 | UI + E2E grün; Manifest driftfrei; Doku aktualisiert. |

## 3. Slice S0 — Entscheidungen und Architekturrahmen

**Ziel:** Die in der Spec offenen Punkte entscheiden, bevor Code entsteht.

- [x] **S0.1** D1–D18 und O1/O3 sind entschieden (2026-11-28), inklusive
  D4 (Finding-Default + Ketten-Override) und D8b (nein). Spec §6 nachziehen
  und im Review bestätigen.
- [x] **S0.2** ADR-033 `change_impact_analysis_als_artefakt` anlegen
  (`docs/se/ADR/ADR-033_change_impact_analysis_als_artefakt.md`): drei neue
  Tabellen (Run/Finding/Chain), Content-Fingerprint, Policy-Keys,
  Preset-Feature, **gemeinsame Workflow-Precondition**, Workspace-/Item-Fence,
  human-only per Bearer-Session. Status `proposed`, `affected_reqs` mit echten
  REQ-IDs (nicht AC-IDs) verlinken.
- [ ] **S0.3** Messbasis notieren: bestehende CR-Anzahl, durchschnittliche
  Affected-Item-Zahl, Workspaces im `extended`-Rigor (nur Aggregate, keine
  Personendaten) — für die Cap- und `blocking`-Kalibrierung in S4.
- [x] **S0.4** Policy-Keys und Ebenen festlegen (global = tenant-weit,
  Workspace-Override, kein User-Level) und mit dem Preference-Registry-Muster
  abgleichen. O2 (Review-Queue) und O5 (Fixtures) sind entschieden; O4 ist
  faktisch „nein".
- [ ] **S0.5** **REQ-Traceability:** über die `requirements`-Rolle neue REQs
  anlegen („strukturierte Impact-Analyse + Gate", „Smart Refinement liefert
  AC + Verifikationsmethode"); das REQ-157-Delta (`impact_assessment` wird
  Addendum) als eigenen Change Request führen. `affected_reqs` in ADR-033 und
  Spec-Kopf auf diese IDs umstellen.
- [ ] **S0.6** `blocking`-Kalibrierung **jetzt** durchführen (O5 entschieden):
  3–5 reale Workspace-Ausschnitte als Fixture, Ziel ≤ 20 % `blocking`,
  Schwellen als benannte Konstanten pinnen. O5 ist damit vor G3 geschlossen.

**Exit:** D1–D18/O1/O3 dokumentiert, D4/D8b entschieden; neue REQs + REQ-157-CR
angelegt; ADR-033 liegt als `proposed` vor; `blocking`-Fixture definiert;
keine Task aus S1 startet vor G0.

## 4. Slice S1 — P1-2: Smart Refinement

**Ziel:** Jeder abgeleitete Requirement-Draft trägt testbare
Akzeptanzkriterien und eine Verifikationsmethode; der Accept-Pfad persistiert
beides strukturiert.

### Aufgaben

- [ ] **S1.1** Prompt-Defaults erweitern:
  `backend/persistence/models.py:3012-3040`
  (`DEFAULT_NEED_TO_SYSREQ`, `DEFAULT_SYSREQ_DECOMPOSE_NEXT_LEVEL`). Response-
  Vertrag: JSON-Array mit `title`, `description`, `rationale`,
  `acceptance_criteria` (1–7 Objekte `{text}`), `verification_method` (Enum).
- [ ] **S1.2** Service-Drafts erweitern:
  `backend/application/ai_derivation_service.py:1055-1086` (need→sysreq) und
  `:1246-1340` (decompose). Neue Keys additiv; der Service normalisiert die
  AC zu `{text, fulfilled:false, evidence_ref:null}`; fehlende Methode ⇒
  `incomplete_fields: ["verification_method"]`.
- [ ] **S1.3** Validierung zentralisieren: 1–7 AC, 10–500 Zeichen, keine
  Duplikate (normalisiert), Methode im Enum. **Kein neuer Attributtyp:** der
  bestehende `criteria-list`-Typ und `normalize_criteria_list`
  (`backend/attribute_definitions/field_validation.py:269`) werden
  wiederverwendet. Kein Draft wird verworfen, nur markiert.
- [ ] **S1.4** Persistenz: Der bestehende Accept-/Write-Pfad schreibt AC über
  `RequirementService.set_acceptance_criteria`
  (`backend/application/requirement_service.py:1291`) als
  `criteria-list`-Items mit `fulfilled=false`; `verification_method` wird
  gesetzt.
- [ ] **S1.5** MCP/REST-Verträge prüfen: `ai_derivation.derive_requirements_from_need`
  und `...decompose_requirement_next_level` geben die neuen Keys zurück; keine
  Breaking Changes. `requirement.acceptance_criteria_set` bleibt unverändert.
- [ ] **S1.6** Frontend-Typen für Drafts erweitern (nur Typen/Anzeige, keine
  neue Ansicht): `frontend/src/api/` (Derivation-Typen) und die bestehende
  Draft-Vorschau, falls vorhanden.
- [ ] **S1.7** Prompt-Regression: Fälle in `promptfoo/` für den neuen
  Response-Vertrag ergänzen (Mock-Provider, deterministisch).
- [ ] **S1.8** Bestands-Overrides prüfen: `PromptTemplate`-Zeilen im
  Workspace/Tenant überschreiben die Factory-Defaults. Nicht automatisch
  überschreiben (Tenant-Hoheit); im Doku-/UI-Hinweis nennen, welche Workspaces
  noch das alte Drei-Feld-Schema verwenden. Der Service bleibt tolerant
  (`incomplete_fields`), damit alte Overrides nicht brechen.

### Tests

| Art | Datei (Vorschlag) | Prüft |
|---|---|---|
| Unit | `backend/application/tests/test_ai_derivation_acceptance_criteria.py` | Draft-Keys, Validierung, `incomplete_fields`, keine Duplikate |
| Unit | `backend/application/tests/test_requirement_service.py` (erweitern) | AC-Persistenz, `fulfilled=false`, Methode |
| Contract | `backend/mcp_server/tests/test_ai_derivation_tools.py` (erweitern) | MCP-Antwort enthält neue Keys |
| Prompt | `promptfoo/`-Fall | JSON-Schema, keine Prosa |

### Exit (G1)

- Ein Need-Draft enthält mindestens ein testbares AC und eine Methode.
- Der Accept-Pfad ist round-trip-fähig (`requirement.get` zeigt
  `acceptance_criteria_items`).
- Alte Clients, die nur drei Keys lesen, funktionieren unverändert.

## 5. Slice S2 — P1-3: Freigabe-Kontext

**Ziel:** `change_request.impact_context` liefert einem Genehmiger alles in
einem Read.

### Aufgaben

- [ ] **S2.1** Layer-2-Service `ChangeRequestImpactContextService` (neue Datei
  `backend/application/change_request_impact_context_service.py`) baut das in
  Spec §4.7 definierte DTO. Er konsumiert:
  `ChangeRequestService.list_affected_items`,
  **einen** Bulk-Lookup für `uid`/Titel/Status/`lock_version`/`revision`,
  `coverage_calculator` **nur für die betroffenen Requirements**,
  den SE-Auditor-Service hinter `audit.se_audit` **aus einem gecachten Report**
  (TTL, auf `artifact_ids ∩ affected_set` gefiltert; kein Workspace-Vollauf),
  Baseline-Drift (bestehender Pfad; sonst Feld weglassen).
- [ ] **S2.2** Caps/Pagination/Projektion: `impact_findings` nutzt die
  Projekt-Envelope (`page`/`page_size`, Default 25/Max 100, `count`);
  `impact_context` trägt `findings_count`, `findings_page`,
  `findings_page_size`, `findings_truncated`, `graph_truncated`,
  `impact_stats`; `affected_items` max. 200; Ketten max. 3 pro Finding;
  keine N+1-Abfragen. Die Ketten kommen aus `ChangeImpactChain`.
- [ ] **S2.3** Policy im DTO: effektive Werte + Quelle je Key
  (`workspace`/`global`/`default`) über `preference.get` **im Bulk** auflösen;
  Zahlwerte typisieren; das DTO nennt `policy.effective` und `policy.source`.
- [ ] **S2.4** REST: `GET .../impact-context/`, `GET .../impact-findings/`
  (Filter/Paging), `GET .../impact-runs/{run_id}/` in
  `backend/rest_api/views_governance.py`, `@extend_schema`;
  `manage.py spectacular --validate` als Gate.
- [ ] **S2.5** MCP: `change_request.impact_context`, `.impact_findings`,
  `.impact_run` in `backend/mcp_server/tools/change_request.py`; identische
  Feldnamen/Fehlercodes; `workspace_id` im `inputSchema`.
- [ ] **S2.6** Rollen/Fences: Viewer darf lesen; **Workspace-Mitgliedschaft**
  wird explizit geprüft (nicht nur Tenant), fremder Workspace ⇒ `NOT_FOUND`;
  pro Artefakt Item-Level-Read anwenden, gesperrte Einträge ausblenden und
  als `item_hidden` zählen; Audit-Sektion nur für Approver/Author, sonst leer
  + `audit_section_hidden`.
- [ ] **S2.7** Solange S3/S4 fehlen: `latest_analysis=null`,
  `findings=[]`, `warnings=[{"code":"impact_analysis_not_available"}]` — der
  Endpunkt ist abwärtskompatibel und sofort nutzbar.
- [ ] **S2.8** `contract_version` (1), `warnings` als Enum-Objekte,
  `entity_id` + `artifact_id` je Item/Finding, `lock_version` + `revision`
  getrennt (nicht `version` als Inhaltsversion verkaufen).

### Tests

| Art | Datei (Vorschlag) | Prüft |
|---|---|---|
| Unit | `test_change_request_impact_context.py` | DTO-Form, Caps, leere Analyse, `impact_stats`, Baseline/Coverage |
| REST | `test_change_request_impact_context_rest.py` | 200/404/403, Paging, `contract_version`, Feldvertrag |
| MCP | `test_change_request_impact_context_tool.py` | Parität zu REST, `workspace_id`-Pflicht |
| Tenant/Item | `test_change_request_impact_context_tenant.py` | fremder Tenant/Workspace, Item-Level-Permission, `item_hidden` |
| Audit | `test_change_request_impact_context_audit_gate.py` | Viewer leer + `audit_section_hidden`, Approver sichtbar |

### Exit (G2, mit S3)

- Ein CR mit drei Affected Items liefert in einem Aufruf Kopf, Items,
  Coverage, Audit-Findings und Baseline.
- Kein Feld erfordert einen zweiten Tool-Aufruf des Clients.

## 6. Slice S3 — Impact-Datenmodell

**Ziel:** Analyse-Läufe und Findings sind persistiert, tenant-isoliert und
auditierbar.

### Aufgaben

- [ ] **S3.1** Modelle in `backend/persistence/models.py` ergänzen:
  `ChangeImpactRun`, `ChangeImpactFinding`, `ChangeImpactChain` (Felder siehe
  Spec §4.2.3–4.2.5). `TenantScopedModel`, `db_table`
  `as_change_impact_run` / `as_change_impact_finding` /
  `as_change_impact_chain`. Run mit `workspace_id`, `baseline` (FK; API-Alias
  `baseline_id`), `root_item_ids`, `roots_source`, `gate_eligible`,
  `graph_fingerprint`, `gate_fingerprint`, `catalog_hash`, `forced`, `pinned`,
  `heartbeat_at`; Defaults `status="pending"`, `gate_eligible=false`,
  `forced=false`, `pinned=false`. Chain **ohne** eigenen `run`-FK (Lauf über
  `finding.run`), `root_artifact_id`, kanonischer `path_hash`,
  `inherited_from_run_id`; Finding mit `gate_open` **als Property, nicht als
  Spalte**, `inherited_from_run_id`, `decided_by` als User-FK.
  UNIQUE `(run, artifact_id)`, `(finding, path_hash)`, partiell
  `(change_request, graph_fingerprint) WHERE forced = false AND status IN
  ('pending','running','completed')`.
- [ ] **S3.2** `ChangeRequest`-Felder ergänzen (`impact_summary` read-only,
  `summary_run_id`, `impact_source`, `impact_generated_at`,
  `impact_override_reason`, `impact_truncation_waiver_reason`,
  `truncation_waiver_run_id`, `truncation_waiver_by`,
  `truncation_waiver_expires_at`) — additiv, nullable/blank;
  `CheckConstraint` `impact_source='hybrid' ⇒ impact_override_reason <> ''`.
- [ ] **S3.3** `ChangeRequestAffectedItem` erweitern (`change_action`,
  `rationale`, `origin`, `removed_reason`) — Defaults so, dass Bestandszeilen
  gültig bleiben. **`set_affected_items` auf diff-basiertes Upsert umstellen**
  (bestehende Zeilen behalten `state_before`/`version_before`/`origin`/
  `rationale`); separates `update_affected_item`; `remove` von der
  After-Capture ausnehmen (`state_after=null`, `removed_reason`).
- [ ] **S3.4** Migration **`backend/persistence/migrations/0158_change_impact_analysis.py`**
  (die CR-Modelle sind seit `persistence/0071` + `application/0024` im
  `persistence`-State; `application/0041` wäre ungültig). Enthält
  CreateModel (Run/Finding/Chain), AddField (CR inkl. aller Waiver-Felder,
  AffectedItem inkl. `removed_reason`), **alle CheckConstraints** (Enums, `weight 0..1`, `hop_distance 1..6`,
  `chain_count <= 3`, `jsonb_array_length(path)=hop_distance`, Notizpflicht,
  Override-Pflicht, `gate_eligible ⇒ roots_source='change_set'`,
  `status='completed' ⇒ finished_at IS NOT NULL`), Indizes
  (`(change_request,status,created_at)`, `(workspace_id)` nur wenn nicht schon
  FK-Index, `(status,created_at)`) und die RLS-Policies im Muster von
  `persistence/0003`/`0108` (`ENABLE`/`FORCE`, kanonischer Predicate,
  `RunSQL` als letzte Operation). Dependency auf die letzte
  `baseline`-Migration (`0014_baseline_waiver_scope_artifact_null`) explizit
  eintragen. **RLS-Wächter:** `persistence/tests/test_rls_coverage.py`
  (automatischer Graph-Scan) **und** `application/tests/test_rls_policies.py`
  (`_EXPECTED_RLS_TABLES`, inkl. Nachziehen des heute fehlenden
  `as_change_request_affected_item`). `test_layer_boundary` prüfen:
  Re-Export in `application/models.py` ergänzen oder Ownership-Test anpassen.
  `makemigrations --check` als Gate.
- [ ] **S3.5** Audit-Vokabular: `impact.analyze` **und**
  `impact.disposition` (je ≤ 32 Zeichen) in `backend/audit/models.py`;
  `backend/audit/tests/test_op_vocabulary.py` erweitern; Dispositions-Audit
  mit alt/neu/Begründung, `decided_by` ist kein Ersatz.
- [ ] **S3.6** Domain-Event optional: `CHANGE_IMPACT_ANALYZED` im
  `DomainEventOutbox` für spätere Automatisierung; wenn nicht benötigt,
  explizit weglassen (Entscheidung dokumentieren). Retention/GC und
  Watchdog (hängende `running`-Läufe) als Tasks in S4/S7 vorsehen.
- [ ] **S3.7** DTO/Serializer: `impact_*`/`summary_run_id` **read-only** und
  nur im **Detail**-/Kontext-Read, nicht im Listen-Serializer (Payload-Bloat,
  N+1); `ChangeRequestDTO` entsprechend splitten; Read-Serializer für
  Run/Finding/Chain (kein Schreib-Serializer außer Disposition in S5).
  `lock_version` und `revision` getrennt ausgeben, `entity_type` im Read aus
  `Artifact.artifact_type` ableiten.

### Tests

| Art | Datei (Vorschlag) | Prüft |
|---|---|---|
| Migration | `backend/persistence/tests/test_migration_0158.py` | Vorwärts/Rückwärts, Defaults, Bestandszeilen, `makemigrations --check` |
| RLS | `backend/application/tests/test_change_impact_rls.py` | Tenant-Isolation, `FORCE ROW LEVEL SECURITY`, `_EXPECTED_RLS_TABLES` |
| Modell | `backend/application/tests/test_change_impact_models.py` | UNIQUEs, CheckConstraints, Indizes, Kaskaden, `chain.run`-Invariante |
| Diff-Set | `backend/application/tests/test_change_request_affected_items_diff.py` | Re-Set erhält `state_before`/`origin`/`rationale`/`version_before` |
| Audit | `backend/audit/tests/test_op_vocabulary.py` | `impact.analyze` + `impact.disposition` |

### Exit (G2)

- Migration läuft auf leerer und bestehender DB; Reverse ist sauber.
- Zwei Tenants sehen jeweils nur ihre Runs/Findings/Chains.
- Eine Kette ist ein eigener Datensatz mit `path_hash`, Pfad und Gewicht.

## 7. Slice S4 — Wirkketten-Engine

**Ziel:** Die Analyse ist deterministisch, begrenzt, reproduzierbar und
optional LLM-annotiert.

### Aufgaben

- [ ] **S4.1** Neuer Layer-2-Service
  `backend/application/change_impact_engine.py`:
  `analyze(cr_id, ctx, root_item_ids=None, max_depth=None, include_semantic=None,
  include_llm=None, force=False) -> ChangeImpactRun`. `None` = effektive Policy
  (§4.2.6); explizite Parameter überschreiben nur diesen Lauf.
- [ ] **S4.2** Kanten-Regeln aus dem Workspace-Link-Katalog ableiten
  (`link_types/workspace_store.py`, Defaults in `link_types/builtin.py`):
  `suspect_rule` bestimmt die Richtung, `impact_weight` das Gewicht,
  `none` wird übersprungen. Kantenmenge = `TraceLink` ∪ **Hierarchie-Union**
  (`Requirement.parent`, `ArchitectureElement.parent_id`,
  `Document`/`WorkItem`-Zerlegung, über `application/tier_compute`), nicht nur
  `ArchitectureElement.parent_id`. Jeder Hop filtert `tenant_id` und
  `workspace_id` der CR.
- [ ] **S4.3** Traversierung: BFS/DFS zyklensicher und **frontier-batchted**
  (`source_id__in` je Tiefe, ein Artifact-Join für die Workspace-Fence); Werte
  aus der Policy (`max_depth` 4/Cap 6, `max_nodes` 200/Cap 500,
  `max_paths_per_finding=3`, `min_weight` 0.05); deterministische Sortierung;
  `truncated`/`truncated_reason`. Perf-Test prüft `O(max_depth)` Queries, nicht
  nur Wanduhr.
- [ ] **S4.4** Fingerprint: SHA-256 über Wurzeln
  (`artifact_id`, **`content_hash` aus `baseline.state_capture`**,
  `lifecycle_status`), die erreichbare Nachbarschaft (Knoten inkl.
  `workflow_state`/Content-Hash, Trace-Kanten, Hierarchie-Kanten,
  semantische Kanten nur mit Build-Marker), den effektiven **Link-Katalog**
  und die Policy; `affected_items_hash` separat. **Ausschlüsse aus dem
  Content-Hash:** `version`, `status`, `suspect`, `baseline` (separat
  gehasht); **nicht** `Artifact.version`; **nicht** `baseline_id` im
  Fingerprint (Baseline-Link bei Approval würde sonst entwerten).
  `gate_fingerprint` separat über **alle** `visited_node_ids` inkl.
  `content_hash`/`workflow_state`/`lifecycle_status`/`suspect` + inzidente
  Kanten. `tier_compute` um `Document`/`WorkItem` erweitern (decken die
  Hierarchie heute nicht ab). **Capture-Vollständigkeit explizit prüfen**
  (`len(states) == len(requested_ids)`, kein leerer Workflow-State), sonst
  `failed`/`stale`; `capture_states` überspringt fehlende Zeilen still.
  Hilfsfunktion isoliert testbar.
- [ ] **S4.5** Findings und Ketten schreiben: `upsert` pro
  `(run, artifact_id)`; je Finding bis zu 3 `ChangeImpactChain`-Zeilen mit
  `path_hash`, `root_artifact_id`, Pfad, Gewicht und Herkunft; `severity`
  deterministisch aus `coverage_relevant` + Hop-Distanz + `suspect` +
  Mindestgewicht, **nicht** pauschal „Zieltyp TestCase/Icd ⇒ blocking";
  Kalibrierung aus S0.6. Dispositionen des Vorlaufs nur bei unverändertem
  `(artifact_id, severity, path_hash)` übernehmen (`inherited_from_run_id`
  an Finding **und** Kette). Kantengewicht je Hop auf `[0,1]` klemmen.
- [ ] **S4.6** LLM-Annotation: neuer Prompt-Slot `change_impact_annotate` in
  `PROMPT_TEMPLATE_DEFAULTS` (`backend/application/ai_derivation_service.py`),
  nur wenn Policy/Call es erlaubt (Default aus); ein Aufruf für die Top-50-
  Findings mit minimierten Feldern (Typ, `uid`, Link-Typ; keine Volltexte),
  strikte JSON-Antwort `{artifact_id, rationale}`, unbekannte IDs verwerfen,
  **`severity` nicht ändern**, Fehler ⇒ `llm_used=false` und Lauf bleibt
  `completed`.
- [ ] **S4.7** Idempotenz: identischer `(cr, graph_fingerprint)` liefert den
  bestehenden Lauf, außer `force=true`; DB-Anker als partielle UNIQUE
  `WHERE forced=false AND status IN ('pending','running','completed')` +
  Advisory-Lock über einen `bigint`-Hash der CR-UUID
  (`hashtextextended`); Retention (letzte 20 Läufe/TTL) festlegen und testen.
  Watchdog deckt **`pending` und `running`** ab (Index `(status, created_at)`),
  sonst blockiert ein verwaister `pending`-Lauf Gate und Idempotenz.
  Retention schützt auch `summary_run_id`/`inherited_from_run_id`.
- [ ] **S4.8** Celery: ab Policy-Cap (Default 200) oder `async=true` den Lauf
  als Task ausführen; `heartbeat_at` aktualisieren, Watchdog-Sweep
  `running → failed` (`error="timeout"`), Status polling über den Run
  (`pending`/`running`).
- [ ] **S4.12** Trigger vollständig: `on_submit` (vor Transition, eigene
  Transaktion, Timeout), `on_write` (60-s-Debounce pro CR), `scheduled`
  (`CELERY_BEAT_SCHEDULE`-Eintrag, Scan auf `draft`/`submitted` mit
  fehlendem/stale Lauf), `manual` Default. Globaler Cap je Workspace/Tag.
- [ ] **S4.9** MCP/REST-Trigger `change_request.analyze_impact` (S2.3-Muster);
  Rollen Editor+ (Force nur Approver/Admin), Tenant-Fence, optional
  `expected_change_set_version` (die Eingaben sind mutabel, auch wenn der Run
  append-only ist). Policy als Obergrenze: Parameter nur restriktiver,
  Klemmen mit `policy.clamped`.
- [ ] **S4.10** Policy-Keys registrieren (`change_impact.*`, Spec §4.2.6) im
  `ready()` der `application`-App (Muster `backend/traceability/apps.py:64-89`),
  Konstanten in `application/change_impact_policy.py`: `trigger`,
  `schedule_interval_hours`, `semantic_edges`, `llm_annotation`, `max_depth`,
  `max_nodes`, `min_weight`; Ebenen `global` + `workspace`, `ui_editor` für
  die generische Settings-Section; enum-Werte beim Auflösen typisieren.
### Tests

| Art | Datei (Vorschlag) | Prüft |
|---|---|---|
| Unit | `test_change_impact_engine_graph.py` | Diamant, Zyklus, Fan-out, `parent`-Hierarchie, `none`-Kante, add/remove |
| Unit | `test_change_impact_engine_caps.py` | Caps, `truncated`, Determinismus |
| Unit | `test_change_impact_fingerprint.py` | Golden-Hash; neue Kante/Knoten, `lifecycle_status`, Katalog-/Policy-Änderung, No-op-Save ⇒ **nicht** stale |
| Unit | `test_change_impact_engine_llm.py` | keine neuen IDs, Severity unverändert, Fehler-Fallback, Default aus |
| Unit | `test_change_impact_policy.py` | Defaults, Workspace-Override, Quelle, Ceiling/Clamping |
| Unit | `test_change_impact_triggers.py` | manual/on_submit/on_write-Debounce/scheduled |
| Unit | `test_change_impact_disposition_inheritance.py` | Übernahme per `(artifact_id, path_hash)` |
| Race | `test_change_impact_race.py` | zwei parallele `analyze_impact`, `analyze ∥ submit` (`TransactionTestCase`) |
| Integration | `test_change_impact_engine_e2e.py` | CR + echte TraceLinks + Persistenz + Ketten |
| Perf | `test_change_impact_engine_perf.py` | 500 Knoten < 3 s **und** Query-Anzahl `O(max_depth)` |

### Exit (G3)

- Gleicher Graph + gleiche Parameter ⇒ identische Findings (Reihenfolge
  deterministisch).
- LLM-Ausfall ändert die Findings-Menge nicht.
- `truncated` ist bei Caps gesetzt, der Lauf endet erfolgreich.

## 8. Slice S5 — Extended-Gate und generierte Summary

**Ziel:** Im `extended`-Rigor ist die strukturierte Analyse der Nachweis; der
Freitext wird Addendum.

### Aufgaben

- [ ] **S5.1** Preset-Feature `structured_change_impact` **atomar** in
  `FEATURE_KEYS` und allen drei `features`-Dicts ergänzen
  (`backend/presets/registry.py`): `minimal=false`, `standard=false`,
  `extended=true`; `PresetConfig.features`-Export und
  `FeatureGateService` (`backend/presets/gate.py:299`) berücksichtigen;
  `test_services_facade`/Feature-Key-Pin erweitern. **Strikter Seam**
  `is_feature_enabled_strict()` einführen (Lookup-Fehler ⇒ raise), Gate nutzt
  ihn und antwortet `CHANGE_IMPACT_POLICY_UNAVAILABLE`; Test „Preset-Lookup
  down ⇒ Block, nicht Freigabe".
- [ ] **S5.2** Gate als **gemeinsame Precondition** in
  `workflow/precondition_rules.py`/`TransitionValidator` für
  `item_type="ChangeRequest"` implementieren — **nicht nur** in
  `ChangeRequestService.transition_status`. Drei explizite Metafelder
  (`change_impact_gate` genau eine, `change_impact_refresh` null oder mehr,
  `change_set_freeze` genau eine) selektieren die Kanten — keine
  Rollen-/Zustands-Heuristik. Dafür `TransitionDefinitionDTO` erweitern,
  Parser/Persistenz/Editor-API nachziehen, eine **Datenmigration** für
  bestehende `ccb_approval`-Definitionen (`draft → submitted`) schreiben und
  die Invariante bei **jedem** Definitions-Write prüfen. Standard:
  Gate/Freeze auf `draft → submitted`, Refresh auf `approved`/
  `approved → implemented`. Gilt für `/transition/`, `/transitions/`,
  `review.approve`, `change_request.submit_for_review` und
  `artifact.bulk_transition`. Prüfungen gemäß Spec §4.5 inkl. Root-Bindung,
  `gate_fingerprint`, `truncated`-Blockade im `extended`, Change-Set-Freeze
  ab `submitted` (`CHANGE_SET_FROZEN`), Re-Check bei `approved` **und**
  `approved → implemented` — **in derselben Precondition**, nicht im Service.
  **SoD und Affected-Item-Check ebenfalls in die Precondition ziehen**, damit
  `/transitions/` sie nicht umgeht. Nur bei `trigger=on_submit` vor der
  Transition auto-analysieren (eigene Transaktion, Timeout); bei `manual`
  blockiert `CHANGE_IMPACT_MISSING`.
- [ ] **S5.3** Fehlercodes: **alle Gate-Codes 409** (`MISSING`, `STALE`,
  `OPEN_FINDINGS`, `INCOMPLETE`, `RUNNING`, `TIMEOUT`), `POLICY_FORBIDDEN`
  400. Als `ValidationError`-Subtypen mit `error_code`/`http_status`/
  `details` in `application/base.py`; Registrierung in
  `_EXC_TO_HTTP`/`_EXC_TO_CODE`/`_ERROR_MESSAGES` (de+en),
  `ERROR_CODES`/`ERROR_CODE_MAP` und `map_tool_exception`; Test über beide
  Kataloge.
- [ ] **S5.4** Summary-Generator (Layer 2, z. B.
  `application/change_impact_summary.py`): **deterministisches** Markdown aus
  **Aggregaten** (Change Set, Top-Findings-Typen, Coverage, Warnungen;
  **kein LLM**, **keine Titel/UIDs** — sonst Item-Filter-Leak), Länge kappen;
  schreibt `impact_summary`, `summary_run_id` (=
  `latest_completed_run.id`), `impact_source="analysis"`,
  `impact_generated_at` am Ende jedes erfolgreichen Laufs per
  `QuerySet.update()` (kein `save()`, kein Versionsbump); read-only im
  Detail-Serializer. `impact_stats`/`findings_count`/`uncovered_ids` werden
  im Read aus der **sichtbaren** Projektion gebildet.
- [ ] **S5.5** Freitext-Regel im `extended` **in
  `ChangeRequestService.update_change_request`** (nicht nur im Serializer):
  `impact_assessment` nur mit `impact_override_reason`, Länge 10k,
  `impact_source="hybrid"`; MCP/REST-Paritätstest. In
  `minimal`/`standard` unverändert.
- [ ] **S5.6** Dispositionen (D4 = beides): `set_finding_disposition`
  (Default für alle Ketten), `set_chain_disposition` (Override je Kette),
  `adopt_finding` (idempotenter Upsert `(cr, item_id)`; Re-Adopt = 200,
  Konflikt nur bei abweichendem Zustand), `waive_truncated_impact`
  (Approver/Admin, eigenes Waiver-Feld, `run_id`/`expires_at`).
  **Disposition/Adopt/Waiver sind REST-only** (MCP-Transport ist
  API-Key-only und kann human-only nicht erfüllen); MCP bleibt lesend.
  **Human-only = interaktive Bearer-Session** (`api_key_id is None`), nicht
  nur `actor_type="user"`; der Truncation-Waiver verlangt zusätzlich
  `"otp" in ctx.amr`, `by IS NULL` gilt als nicht quittiert, `expires_at`
  max. 30 Tage. `note` Pflicht bei `mitigated`/`waived`/`rejected`; Audit
  `impact.disposition`. `adopt_finding` antwortet nach `submitted` mit
  `CHANGE_SET_FROZEN`.
- [ ] **S5.7** Bestehenden Genehmigungs-Check
  (`_enforce_affected_items_recorded`) unverändert lassen — Verteidigungslinie.
- [ ] **S5.8** Policy als **Ceiling** durchsetzen: Call-Parameter nur
  restriktiver; Klemmen mit Antwortfeld `policy.clamped` (Warncode
  `policy_clamped`); `force` **nur Approver/Admin**, rate-limitiert (1/CR/h);
  `include_semantic`/`include_llm` nur, wenn Policy es erlaubt. Eigener
  DRF-Scope `change_impact_analyze` + Tagescap ⇒ `CHANGE_IMPACT_RATE_LIMITED`
  (429).
- [ ] **S5.9** Entry-Point-Paritätstest: Blockfall für jede Transition-Route
  (`/transition/`, `/transitions/`, `review.approve`,
  `change_request.submit_for_review`, `artifact.bulk_transition`) und für
  MCP/REST gleich.

### Tests

| Art | Datei (Vorschlag) | Prüft |
|---|---|---|
| Gate | `backend/application/tests/test_change_request_impact_gate.py` | alle Codes, Root-Bindung, `truncated`, Freeze, Präzedenz, strikter Policy-Seam |
| Marker | `backend/workflow/tests/test_change_impact_markers.py` | DTO/Backfill, genau eine Gate-/Freeze-Kante, Invariante bei jedem Write |
| Entry-Points | `backend/application/tests/test_change_impact_gate_entry_points.py` | `/transition/`, `/transitions/`, `review.approve`, `bulk_transition`; SoD/Items/Re-Check |
| Fingerprint | `backend/application/tests/test_change_impact_fingerprint.py` | Content-Edit/Suspect-Flip an Nicht-Wurzel ⇒ stale; Capture fehlt ⇒ failed |
| Disposition | `.../test_change_impact_disposition.py` | Bearer+OTP-Waiver, `by NULL` ⇒ nicht quittiert, Ablauf max. 30 Tage |
| Standard | `backend/application/tests/test_change_request_impact_gate_standard.py` | `standard` blockiert nicht und liefert keinen Hinweis |
| Summary | `backend/application/tests/test_change_impact_summary.py` | deterministisch, kein LLM, `summary_run_id`, read-only |
| Disposition | `backend/application/tests/test_change_impact_disposition.py` | Bearer-only, Agent/User-Key ⇒ `PERMISSION_DENIED`, `If-Match` 412 / `expected_version` 409, Notizpflicht |
| Transport | `backend/rest_api/tests/test_change_impact_error_codes.py` + MCP-Parität | alle Codes in beiden Katalogen, 409 |
| Policy | `backend/application/tests/test_change_impact_policy_ceiling.py` | Clamping, `force`-Rolle |
| REST/MCP | Paritätstest | gleiche Codes/Felder/Rollen |

### Exit (G3)

- `extended` + fehlende Analyse ⇒ `draft → submitted` scheitert mit dem
  spezifizierten Code.
- `extended` + frische Analyse ohne offene blockierende Findings ⇒ Transition
  gelingt.
- `standard` bleibt unverändert benutzbar.

## 9. Slice S6 — CR-Detailansicht

**Ziel:** Der Mehrwert ist im UI sichtbar; heute existiert keine CR-Ansicht.

### Aufgaben

- [ ] **S6.1** API-Client + Typen: `frontend/src/api/change-requests.ts`
  (`ChangeRequestImpactContext`, `ImpactRun`, `ImpactFinding`,
  `ImpactChain`, `getImpactContext`, `getImpactRun`, `analyzeImpact`,
  `setFindingDisposition`, `setChainDisposition`, `adoptFinding`).
- [ ] **S6.2** Route und Ansicht: `ChangeRequestDetailView.tsx` plus
  `ImpactRunPanel.tsx`, `ImpactFindingsTable.tsx`, `ChangeSetTable.tsx`.
  **Route in `NavigationShell.tsx`** (`<Routes>`) registrieren, nicht in
  `App.tsx`; Navigations-/Einstiegsquelle gemäß O2.
- [ ] **S6.3** Kopfbereich: Titel, Status, Requestor, Baseline, `impact_source`,
  `summary_run_id`/`impact_generated_at` als Herkunftszeile, effektive Policy
  mit Quelle, `impact_summary` als Primärtext; `impact_assessment` als
  einklappbares Addendum („nicht Gate-relevant"), Override-Grund als
  Pflichtfeld.
- [ ] **S6.4** Aktionen mit **explizitem Rollen-Gating**: `canAnalyze`/
  `canAdopt` = Admin/Editor, `canDispose` = Admin/Approver, Viewer read-only;
  `force` nur Admin/Approver; `useHasRole` um `approver` erweitern (nicht
  inline nachbauen). Deaktivierte Controls mit Begründung statt Verstecken;
  SoD-Hinweis, wenn Requestor = aktueller Nutzer. Kettenzeile zeigt
  „Effektiv (geerbt)" und „Override", inkl. `inherited_from_run_id`
  („aus Vorlauf übernommen"); Adopt mit `ConfirmDialog`, In-flight-Guard und
  Refetch.
- [ ] **S6.4a** Policy-UI: die generischen `change_impact.*`-Keys über
  `PreferenceLevelSection` in Workspace-/System-Settings rendern
  (`ui_editor` gesetzt); keine eigene Section, solange die generische reicht.
- [ ] **S6.5** Zustände inkl. **Mapping Antwort→Zustand**: leer (kein Lauf),
  `pending`, `running` (Polling/Refresh-Affordance), `failed` (mit
  `details.reason`), `stale` (mit „neu starten"), `truncated` (welcher Cap),
  keine Findings, „keine Rechte" (nur bei Schreibaktionen, Read ist
  `NOT_FOUND`), Warnungs-Enum (`item_hidden`, `audit_section_hidden`,
  `policy_clamped`, `no_baseline`, `finding_outdated`, `truncated_scope`,
  `change_set_item_without_trace`) als sichtbare, übersetzte Liste.
- [ ] **S6.6** i18n: Namespace `changeRequests.*` in `de.json`/`en.json` und
  in `locales.test.ts` (explizite Schlüsselliste, keine Flat-Dotted-Keys);
  `data-testid`-Präfixe `change-request-*`/`cr-impact-*` inkl.
  Zustandsregionen; Tokens statt Hex-Werten.
- [ ] **S6.7** Fehlercode→Copy-Map für `CHANGE_IMPACT_*` mit nächstem Schritt
  und Sprungmarke; `role="alert"` nahe der Aktion; Statusregion nur mit
  Inhalt mounten (`role="status"`, `aria-live="polite"`).
- [ ] **S6.8** `impact_summary`/`rationale` nur über den bestehenden
  Markdown-Renderer ohne Raw-HTML (kein `dangerouslySetInnerHTML`);
  XSS-Testfall mit `<img onerror>`/`javascript:`.
- [ ] **S6.9** Wiederverwendung statt Neubau: `PageHeader`, `EmptyState`
  (inkl. `emptyState.forbidden`/`noMatch`), `ListToolbar`, `ConfirmDialog`,
  `Badge` (nicht `StatusBadge` für Severity), `useRequiredValidation`,
  `useHasRole`, `extractApiErrorMessage`, `PreferenceLevelSection`.
- [ ] **S6.10** `BaselineRollbackPanel` von Copy-Referenz auf
  `<Link to={/change-requests/${id}}>` umstellen (Copy darf bleiben); alle
  fünf „keine CR-Ansicht"-Kommentare und die Tests anpassen.
- [ ] **S6.11** CR-Workflow-Transitionen: `getTransitions`/`postTransition`
  für `change-request` im API-Client, Approve/Reject mit Pflicht-
  `change_reason` (extended), SoD-Hinweis, `409`-Behandlung; E2E-Fall.
- [ ] **S6.12** Fehlercode→Copy für **alle** neuen Ablehnungen:
  `CHANGE_IMPACT_*`, `CHANGE_SET_FROZEN`, `CONFLICT` (412/409),
  `PERMISSION_DENIED`, `NOT_FOUND`; je mit nächstem Schritt/Sprungmarke.
- [ ] **S6.13** A11y-Vertrag: Fokus nach Aktion/Zustandswechsel,
  `aria-busy` beim Analyse-Button, `aria-expanded` für Addendum/Ketten,
  echte Tabellen-Header (`th scope`), Live-Region nur mit Inhalt; Route in
  `a11y-smoke`/`CURATED_ROUTES` registrieren; A11y-AC in der Spec.
- [ ] **S6.14** Einstieg (O2 entschieden): `change-request` als
  `WorkflowArtifactType` in `workflow-transitions.ts` und als
  `REVIEW_ACTION_CONFIG` in `ReviewsView.tsx` aufnehmen, damit CRs in der
  Freigaben-Queue erscheinen. `BaselineDriftBadge` hält die erzeugte CR-ID
  und verlinkt sie (nicht nur `setCreated(true)`); Tests erweitern. Keine
  separate CR-Liste.
- [ ] **S6.15** Ketten-Hops über **einen** Bulk-Lookup über
  `affected ∪ findings ∪ path.artifact_ids` auflösen; Test „keine rohe UUID
  in der Kettenzeile". Copy-Entscheidung „Wirkkettenanalyse (CR)" vs.
  „Auswirkungsanalyse (Artefakt)" in Nav/PageHeader/Fehler-Copy.

### Tests

| Art | Datei (Vorschlag) | Prüft |
|---|---|---|
| RTL | `ChangeRequestDetailView.test.tsx` | `pending`/`running`/`stale`/`forbidden`, Rollen-Gating, `force` |
| RTL | `ImpactFindingsTable.test.tsx` | Finding-Default, Ketten-Override, `inherited_from_run_id`, `truncated` |
| RTL | `ChangeRequestTransitions.test.tsx` | Approve/Reject, `change_reason`, 409/SoD |
| RTL | `ImpactWarnings.test.tsx` | Warnungs-Enum gemappt, `audit_section_hidden`/`item_hidden` |
| RTL | `BaselineRollbackPanel.test.tsx` (erweitern) | Link statt Copy |
| RTL | `BaselineDriftBadge.test.tsx` (erweitern) | CR-ID verlinkt |
| RTL | `locales.test.ts` (erweitern) | `changeRequests.*`-Parität DE/EN |
| A11y | `e2e/tests/a11y-smoke.spec.ts` (erweitern) | Route im Axe-Sweep |
| E2E | `e2e/change-request-impact.spec.ts` | Analyse → Findings → Disposition → Freigabe; Gate-Fehlercode `MISSING` mit Copy/Sprungmarke; Adopt-Confirm |

### Exit (G4)

- Ein Approver kann ohne Tool-Wechsel sehen, was betroffen ist und warum.
- `data-testid`-Konvention eingehalten; DE/EN vollständig.

## 10. Slice S7 — Doku, Manifest, Rollout

- [ ] **S7.1** Tool-Manifest neu erzeugen
  (`python backend/manage.py export_tool_manifest`) und
  `docs/agent-templates/tool-manifest.json` aktualisieren; Drift-Test
  (`backend/mcp_server/tests/test_tool_manifest_drift.py`) grün. Neue Tools in
  `mcp_server/workspace_scope._TOOL_TARGETS` registrieren und
  `ChangeImpactFinding`/`ChangeImpactChain` in
  `application/workspace_lookup.ENTITY_SPECS` aufnehmen; Scope-Ratchet-Test.
- [ ] **S7.2** `docs/api/MCP-SURFACE.md` um die neuen Tools und Fehlercodes
  ergänzen (§1-Zähler, §2-Zeile `change_request`, §7.1-Write-Tabelle).
  `docs/api/REST-CONVENTIONS.md` um ETag-/Conditional-Action-Tabellen und den
  Fehlerkatalog erweitern.
- [ ] **S7.3** Feature-Doku `docs/features/change-impact-analysis.md`
  (intern, Deutsch): Ablauf, Rollen, Fehlercodes, Caps, Beispiel,
  Policy-Keys mit Ebenen (`global`/`workspace`) und Defaults, Trigger-Modi
  inklusive `on_write`-Entprellung und `scheduled`-Beat.
- [ ] **S7.4** Spec-Status und Indizes aktualisieren
  (`docs/superpowers/specs/index.md`, `docs/superpowers/plans/index.md`).
- [ ] **S7.5** Observability: Audit-Operationen (`impact.analyze`,
  `impact.disposition`), Run-Zähler, Fehlerrate, hängende `running`-Läufe,
  Retention-GC; optional `se_metrics`-Metrik „offene blockierende Findings".
- [ ] **S7.6** Rollout: Feature per Preset; kein Backfill. `standard` bleibt
  ohne Pflicht; `extended`-Workspaces erhalten die Analyse beim nächsten
  Submit. Rollback = Feature-Flag aus (Daten bleiben).
- [ ] **S7.7** Evidence: Testläufe, Commit-Hashes, PR-Nummern im Plan
  nachtragen (Repo-Konvention).
- [ ] **S7.8** Rate-Limit-Scope `change_impact_analyze` in
  `admin_ops/rate_limits.py` + `settings.REST_FRAMEWORK` registrieren
  (Drift-Test), **Workspace-Dimension** ergänzen (der bestehende Limiter
  kennt nur Tenant/User), Tagescap je Workspace, `force` 1/CR/h,
  `CHANGE_IMPACT_RATE_LIMITED` 429.
- [ ] **S7.9** Retention/GC: Celery-Task löscht nur `pinned=false` und nur
  Läufe, die nicht von `summary_run_id`/`inherited_from_run_id`/Disposition
  referenziert werden; Größenmetrik und Alarm auf hängende `pending`/`running`.

## 11. Teststrategie und DoD

- **Backend:** `make test-backend` (isolierter Stack); neue Tests mit
  `--reuse-db` während der Entwicklung.
- **Frontend:** `make test-frontend`; ESLint/Prettier; keine hardcodierten
  Farben, Tokens aus `styles/tokens.css`.
- **E2E:** `npx playwright test e2e/change-request-impact.spec.ts` (Chromium).
- **Tenant/RLS:** eigener Test pro neuer Tabelle; kein `unscoped`-Leck.
- **Parität:** Jede neue MCP-Operation hat einen REST-Zwilling und einen
  Paritätstest (Felder, Fehlercodes, Rollen).
- **DoD je Slice:** Code + Tests + Doku + i18n (falls UI) + Manifest (falls
  Tool) + keine Regression; Commit im Conventional-Format, Feature-Branch.

## 12. Risiken und Gegenmaßnahmen im Plan

| Risiko | Frühindikator | Gegenmaßnahme |
|---|---|---|
| Graph-Explosion | Laufzeit > 3 s bei < 500 Knoten | Caps senken, Celery, `truncated` sichtbar. |
| Falsche Severity | Zu viele „blocking"-Findings | Kalibrierung in S0.6, Schwellen als Konstante, Testdaten. |
| Stale-Rauschen | Gate blockiert ständig | Content-Hash statt `version`; Dispositions-Vererbung; `force` für bewusste Wiederholung. |
| Gate-Bypass | `/transitions/`/`review.approve` umgehen den Service | Gate als gemeinsame Workflow-Precondition + Entry-Point-Paritätstest. |
| Migrationsdrift | `makemigrations --check` rot / RLS fehlt | Migration in `persistence/0158`, `_EXPECTED_RLS_TABLES` erweitern. |
| LLM-Kosten | Viele Läufe | Ein Aufruf, optional aus, Idempotenz, Budget-Seam; `on_write` entprellt. |
| `on_write`-Last | Viele Celery-Tasks | 60-s-Debounce pro CR, Cap, Monitoring; Default bleibt `manual`. |
| `scheduled`-Kosten | Nächtliche Läufe für alle CRs | Nur `draft`/`submitted` mit fehlendem/stale Lauf, Workspace-Policy. |
| UI-Umfang | S6 zieht sich | v1 minimal; CR in der Freigaben-Queue (keine separate Liste); Wiederverwendung bestehender Komponenten. |
| API-Bruch | Clients brechen | Nur additive Felder/Endpunkte; keine Spaltenlöschung; AC-Draft bewusst objektförmig dokumentiert. |

## 13. Entscheidungsstand

**Entschieden:** D1–D18 (inkl. D4 = Finding-Default + Ketten-Override,
D8b = nein, D12 = gemeinsame Precondition, D13 = Bearer-only human-only,
D14 = `truncated` blockiert, D15 = Content-Fingerprint, D16 = deterministische
`blocking`-Regel, D17 = Workspace-/Item-Fence, D18 = `persistence/0158`),
O1, O3.

**Entschieden (O2/O5):** CR als eigener Typ in der Freigaben-Queue, keine
separate Liste. `blocking`-Kalibrierung in S0.6 mit ≤ 20 %-Ziel. Damit sind
alle fachlichen Entscheidungen geschlossen; offen bleibt nur der finale
Verification-Pass und die Kosmetik.

## 14. Nicht in diesem Plan

- Code-/AST-Tracing (P3 der Bestandsanalyse).
- Automatische Genehmigung oder Agenten-Disposition.
- Löschung der Freitextspalten.
- Eine vollständige CR-Liste/Board-Ansicht.
- Änderungen am `ccb_approval`-Zustandsgraphen.

## 15. Evidence (S0)

**Datum:** 2026-11-28 · **Branch:** `feat/change-artefakt-wirkketten` ·
**Status:** S0.1/S0.2/S0.4 abgeschlossen; S0.3 offen, S0.5 teilweise, S0.6 beim
separaten Agenten.

| Punkt | Stand |
|---|---|
| REQ-Traceability | `REQ-216` (strukturierte Impact-Analyse + Extended-Gate), `REQ-217` (Smart Refinement), `REQ-218` (Delta-CR zu `REQ-157`) in `docs/REQUIREMENTS.md` |
| ADR | `docs/se/ADR/ADR-033_change_impact_analysis_als_artefakt.md`, Status `proposed`, `affected_reqs: [REQ-216, REQ-217, REQ-157, REQ-218]` |
| Policy-Keys (S0.4) | sieben `change_impact.*`-Keys, Ebenen `global` + `workspace`, **kein** `user`-Level, typisierte Auflösung; Tabelle in ADR-033 |
| Messbasis (S0.3) | **offen (nicht gemessen)** — der Dev-Stack dieses Checkouts läuft nicht (`docker compose --env-file .env -f deploy/docker-compose.yml ps` leer); der erreichbare Backend-Container gehört zu `/home/hermes/reqogniloom-qs` und lieferte 0 CRs / 0 Affected Items / 0 Workspaces. Befehle zum Nachholen: ADR-033 §„Messbasis (S0.3)" |
| S0.5 | teilweise: REQs angelegt und in ADR-033 verlinkt; Spec-Kopf in diesem Slice bewusst unverändert, REQ-157-Delta-CR ist ein Plattform-Artefakt (nicht Gegenstand dieses Slices) |
| `blocking`-Fixtures (S0.6) | `backend/application/tests/fixtures/change_impact_calibration.py` (separater Agent, hier **nicht** geprüft) |
