# Change-Artefakt als Wirkketten-Knoten — strukturierter Impact, automatische Wirkkettenanalyse und Requirements-Smart-Refinement

> **Status:** Entscheidungen D1–D18/O1–O5 sind getroffen (2026-11-28); die
> Architekturentscheidung liegt als ADR-033 (`proposed`) vor. Umsetzung **nicht
> begonnen**.
> **Art:** Spezifikation. Der zugehörige Umsetzungsplan liegt unter
> [`../plans/2026-11-28-change-artefakt-wirkketten.md`](../plans/2026-11-28-change-artefakt-wirkketten.md).
> **Review-Protokoll:** [`../../reviews/2026-11-28-change-artefakt-wirkketten-review.md`](../../reviews/2026-11-28-change-artefakt-wirkketten-review.md).
> **Basis:** `main` `c5b55108`, Arbeitsbaum geprüft am 2026-11-28.
> **Bezug:** P1-2 (Smart Refinement) und P1-3 (Freigabe-Kontext) aus der
> Bestandsanalyse vom 2026-11-28; Change-Artefakt-Best-Practice (Abschnitt 3).
> **Leitentscheidung:** Das Change-Artefakt wird zum strukturierten Knoten.
> „Was wird geändert" (Change Set) und „was ist davon betroffen" (Impact Set)
> werden maschinenlesbar; Freitext bleibt die Begründung („warum"), nicht der
> Nachweis („was").

## 1. Ziel und Anforderung

Der Nutzer will drei Dinge gemeinsam umsetzen:

1. **P1-2 — Smart Refinement:** Die KI-Ableitung von Anforderungen liefert
   nicht mehr nur `title`, `description`, `rationale`, sondern direkt
   **testbare Akzeptanzkriterien** und eine **Verifikationsmethode**.
2. **P1-3 — Freigabe-Kontext:** Ein Change Request (CR) liefert Genehmigern
   einen aggregierten Kontext: betroffene Artefakte samt Version/Status,
   Trace-Nachbarn, Testabdeckung, offene Audit-Findings und Baseline-Bezug —
   statt nur dreier Freitextfelder.
3. **Change-Artefakt als echter Mehrwert:** Im höchsten Rigor (`extended`)
   ersetzt die strukturierte Impact-Erfassung die Freitextfelder als
   Nachweis. An das CR wird eine **automatische Wirkkettenanalyse** gekoppelt:
   ausgehend von den geänderten Artefakten werden Änderungswirkungen über
   Trace-, Allokations- und Zerlegungskanten propagiert, als Findings
   festgehalten und vor der Freigabe dispositioniert.

**Nicht** Ziel ist ein neues Workflow-System: Das CR bleibt Informations- und
Freigabe-Knoten; die Zustandsmaschine bleibt der `ccb_approval`-Graph. Das
entspricht ausdrücklich der Best Practice „Change-Artefakt steuert den Workflow
nicht aktiv" (Abschnitt 3.3, P8).

### 1.1 Scope

| Teil | Inhalt | Rigor |
|---|---|---|
| A | Smart Refinement: strukturierte AC + `verification_method` in den Ableitungs-Flows | alle |
| B | `change_request.impact_context` (P1-3): aggregierter Freigabe-Kontext | alle |
| C | Strukturierter Impact: `ChangeImpactRun` + `ChangeImpactFinding` + `ChangeImpactChain`, Wirkketten-Engine | alle (Analyse), Gate nur `extended` |
| D | `extended`-Gate: Analyse vollständig, frisch, keine offenen blockierenden Findings | `extended` |
| E | Change-Impact-Policy: global (tenant-weit) + Workspace-Override | alle |
| F | Minimale CR-Detailansicht im Frontend (heute nicht vorhanden) | alle |

### 1.2 Nicht-Ziele

- Kein Code-/AST-Tracing (P3 der Bestandsanalyse). Die Wirkkettenanalyse
  arbeitet ausschließlich auf Loom-Artefakten und TraceLinks.
- Keine automatische Genehmigung, keine Agenten-Disposition. Entscheidungen
  bleiben human-only (ADR-019, #1362b).
- Kein Entfernen der Spalten `description`, `impact_assessment`,
  `change_reason` in v1 (Additive Migration; siehe D1).
- Kein ungedrosselter Lauf pro Schreibzugriff. Der Trigger ist
  policy-konfiguriert (Default `manual`; `on_submit`/`on_write` entprellt/
  `scheduled`, D7).
- Kein neuer Workflow-Zustand und keine neue State-Machine.

## 2. Ist-Stand (belegt gegen den Code)

| Baustein | Stand | Beleg |
|---|---|---|
| `ChangeRequest` | `title`, `description` (20k), `impact_assessment` (Freitext, 10k), `change_reason` (2k), `baseline`-FK, Requestor/Reviewer; Status über WorkflowEngine | `backend/persistence/models.py:4108-4200` |
| Change Set | `ChangeRequestAffectedItem`: `item_id` = Artifact-UUID, `version_before`/`version_after`, `state_before`/`state_after`, UNIQUE `(cr, item_id)` | `backend/persistence/models.py:4203-4303` |
| Extended-Gate (heute) | Genehmigung verlangt mind. 1 Affected Item; SoD (Requestor ≠ Approver); Baseline-Link beim Abschluss | `backend/application/change_request_service.py:591-714, 718-805` |
| Impact-Analyse (heute) | `context.change_impact`: liest Nachbarn eines **einzelnen** Artefakts (Hard-Links + Zerlegung), LLM annotiert `likely_affected`/`rationale`; **read-only**, kein CR-Bezug, keine Persistenz | `backend/application/change_impact_service.py:1-120`; MCP `context.change_impact` |
| P1-3 (heute) | CR-Read liefert `affected_item_ids`, aber keine Details, Versionen, Tests, Findings oder Baseline-Diff | `backend/rest_api/serializers_governance.py:1448-1491`; `ChangeRequestDTO` ohne Impact (`change_request_service.py:92-146`) |
| Frontend | **Keine CR-Ansicht**; nur „CR anlegen"-Shortcut und Rollback-Statusanzeige | `frontend/src/api/change-requests.ts:48`; `BaselineRollbackPanel.tsx:18` |
| Presets | `extended`: `approval_workflows=true`, `change_reason=mandatory`; Gate prüft heute nur Affected Items, nicht die Analyse | `backend/presets/registry.py:251-291`; `FeatureGateService` in `backend/presets/gate.py:299` |
| Smart Refinement (heute) | `DEFAULT_NEED_TO_SYSREQ` liefert nur `title`, `description`, `rationale`; Service baut genau diese drei Keys | `backend/persistence/models.py:3012-3020`; `backend/application/ai_derivation_service.py:1055-1086` |
| Strukturierte AC (heute) | `Requirement.acceptance_criteria_items` + `RequirementService.set_acceptance_criteria`; MCP `requirement.acceptance_criteria.set` | `backend/application/requirement_service.py:1291`; `backend/mcp_server/tools/requirements.py:1447` |
| Generischer Checklisten-Typ (heute) | **`criteria-list` existiert bereits** (#1288): Objekte `{text, fulfilled, evidence_ref?}`, Backend-Validator + Frontend-Widget mit Checkbox je Zeile | `backend/attribute_definitions/field_validation.py:69-169`; `frontend/src/components/shared/ArtifactForm/fields/CriteriaList.tsx` |
| Dreistufige Konfiguration (heute) | `PreferenceKey` mit Ebenen `global`/`workspace`/`user`, `override`/`union`, Audit und generischem Settings-Editor; Traceability nutzt das Muster bereits | `backend/application/preference_registry.py:74-140`; `backend/traceability/apps.py:64-89` |
| Verifikationsmethode | `Requirement.verification_method` ist im `extended`-Gate Pflicht | `backend/presets/registry.py:251-269` |
| Kontextquellen für P1-3 | `traceability.coverage`, `traceability.vcrm`, `audit.se_audit`, `baseline.compare`, `suggestion.list` | MCP-Tools; `audit`-App |
| Vorschlags-Lifecycle | `Suggestion` + `suggestion.capture`/`accept`/`reject`; Entscheidung human-only | ADR-019, ADR-032 (proposed); `backend/application/suggestion_adapters.py` |

**Kernlücke:** Das CR beantwortet heute „warum" gut, aber „was" und „was noch"
nur als Freitext plus eine flache Liste von Affected Items. Es gibt keinen
Analyse-Lauf, keine Kette, keine Disposition und keinen Freigabe-Kontext.

## 3. Best Practices und Literatur

> **Belegart:** Etablierte Standardwerke und Normen aus dem Requirements- und
> Systems Engineering. Die Primärtexte wurden in dieser Sitzung nicht erneut
> gelesen (Websuche war nicht verfügbar); die Zitate dienen als
> Begründungsrahmen und sind vor einer Umsetzung gegen die Primärquelle zu
> prüfen. Die Wikipedia-Zusammenfassung zu Change Impact Analysis wurde
> gelesen und stützt die Begriffsabgrenzung (Bohner/Arnold, Pfleeger/Atlee).

### 3.1 Normen und Prozessmodelle

| Quelle | Kernaussage | Konsequenz für diese Spec |
|---|---|---|
| ISO/IEC/IEEE 15288:2023, §6.4.9 Configuration Management | Ein Änderungsantrag muss **was** geändert wird und **gegen welche Baseline** festhalten; Impact Assessment und Freigabe gehören zum Prozess. | `baseline`-FK bleibt; Change Set wird explizit; Impact wird als eigener Lauf auditierbar. |
| ISO/IEC/IEEE 29148:2018 | Anforderungen brauchen prüfbare Akzeptanzkriterien, Verifikationsmethode und Rückverfolgbarkeit. | P1-2 liefert AC + Methode direkt aus der Ableitung. |
| Automotive SPICE PAM 4.0, SUP.10 Change Request Management | Änderungsanträge registrieren, analysieren/bewerten, freigeben/ablehnen, umsetzen, verfolgen und verifizieren; bidirektionale Traceability. | Statusmodell bleibt; Analyse wird zum registrierten Artefakt; Findings werden dispositioniert. |
| INCOSE SE Handbook, 5. Aufl. (2023), Configuration Management | Änderungen werden über den Lebenszyklus bewertet; Impact Analysis umfasst betroffene Produkte und Pläne. | P1-3 aggregiert nicht nur Requirements, sondern Tests, Findings und Baseline. |
| IREB CPRE Foundation Level | Änderungsmanagement und Traceability sind Kernpraktiken; Auswirkungen müssen vor der Umsetzung bewertet werden. | Kein Auto-Approve; Mensch entscheidet auf Basis des Kontexts. |

### 3.2 Forschung

| Quelle | Kernaussage | Übernahme |
|---|---|---|
| Bohner & Arnold, *Software Change Impact Analysis* (1996) | Impact Analysis = „identifying the potential consequences of a change, or estimating what needs to be modified"; unterscheidet **traceability IA** und **dependency IA**; Expertenwissen als dritte Klasse. | Traceability-basierte Kanten zuerst; LLM nur als beratende Experten-Schicht. |
| Pfleeger & Atlee, *Software Engineering: Theory and Practice* (2006) | Impact Analysis bewertet auch Risiken, Aufwand und Zeit. | Findings tragen Gewicht/Severity; Kontext zeigt Coverage und offene Findings. |
| Gotel & Finkelstein (1994); Ramesh & Jarke (2001) | Traceability ist das begrenzende Gut; ihre Qualität entscheidet über Impact-Analysen. | Analyse markiert fehlende/unvollständige Kanten; `truncated` und `unlinked` werden sichtbar. |
| Clarkson, Simons & Eckert, *Predicting change propagation in complex design* (2004) | Änderungen propagieren über Abhängigkeiten; Wahrscheinlichkeit und Wirkung sind bewertbar. | Gewichtete Kanten, Pfadlänge, Abbruchschwelle. |
| Jarratt et al., *Engineering change: an overview and perspective on the literature* (2011) | Engineering Change Management umfasst Identifikation, Impact Analysis, Freigabe, Umsetzung und Verifikation. | Prozessbild und Dispositionen folgen dieser Reihenfolge. |
| Eppinger & Browning, *Design Structure Matrix Methods and Applications* (2012) | Abhängigkeitsmatrizen machen Propagationspfade sichtbar. | Pfade werden als Ketten gespeichert und im Kontext angezeigt (nicht nur Endknoten). |

### 3.3 Abgeleitete Design-Prinzipien

| ID | Prinzip |
|---|---|
| P1 | **Struktur vor Narrativ:** Change Set und Impact Set sind maschinenlesbar; Freitext ist Begründung. |
| P2 | **Baseline-relativ:** Jede Bewertung nennt die Konfiguration, gegen die sie gilt. |
| P3 | **Analyse ist ein Artefakt:** Lauf, Eingaben, Algorithmusversion, Zeitpunkt und Ergebnis werden gespeichert. |
| P4 | **Graph zuerst, LLM zweitens:** Die Kette wird deterministisch berechnet; das LLM annotiert nur, es erfindet keine Kante. |
| P5 | **Propagation ist begrenzt und gewichtet:** Tiefe, Knotenzahl, Pfade und Gewichtsschwelle sind explizit; Zyklen sind sicher. |
| P6 | **Menschliche Verantwortung:** Dispositionen und Freigabe sind human-only; SoD bleibt. |
| P7 | **Kein stiller Schreibzugriff:** Vorschläge statt Auto-Create; ADR-019/032 bleibt. |
| P8 | **Change-Artefakt führt nicht den Workflow:** Es informiert und belegt; die State-Machine bleibt `ccb_approval`. |

**Verworfene Alternativen:** (a) Freitext-Impact beibehalten und nur per Prompt
„besser" machen — nicht prüfbar, nicht auditierbar. (b) LLM entscheidet die
Impact-Menge — halluzinationsanfällig, nicht reproduzierbar. (c) Automatische
Analyse bei jedem Schreibzugriff — Kosten und Rauschen, ohne Freigabebezug.
(d) Change-Artefakt als Workflow-Treiber — widerspricht Best Practice und dem
bestehenden Engine-Design.

## 4. Zielbild

### 4.1 Begriffe

| Begriff | Bedeutung | Speicherort |
|---|---|---|
| **Change Set** | Artefakte, die das CR **tatsächlich ändern will**; versioniert und mit Vorher/Nachher-Zustand. | `ChangeRequestAffectedItem` (bestehend, erweitert) |
| **Impact Set** | Artefakte, die **potenziell betroffen** sind, ohne selbst geändert zu werden. | `ChangeImpactFinding` (neu) |
| **Wirkkette / Effect Chain** | Gerichteter Pfad vom Change-Set-Knoten zum Finding über Trace-/Allokations-/Zerlegungskanten, inkl. Link-Typen und Gewicht. | `ChangeImpactChain` (eigene Tabelle) |
| **Analyse-Lauf** | Ein konkreter, auditierbarer Berechnungslauf mit Graph-Fingerprint und Ergebnis. | `ChangeImpactRun` (neu) |
| **Freigabe-Kontext** | Aggregierte Lesesicht für den Genehmiger (P1-3). | `change_request.impact_context` (neu, read-only) |

Die Trennung ist entscheidend: Ein Finding darf **nicht** automatisch zum
Affected Item werden. Sonst wächst das Change Set unkontrolliert und die
Vorher/Nachher-Snapshots werden falsch. Ein Finding kann der Mensch bewusst
in das Change Set übernehmen (`set_affected_items`).

### 4.2 Datenmodell

#### 4.2.1 `ChangeRequest` (Erweiterung, additiv)

| Feld | Typ | Zweck |
|---|---|---|
| `impact_summary` | TextField, blank, **read-only** | Vom Lauf deterministisch generierte Markdown-Zusammenfassung (Change Set + Top-Findings + Coverage); **kein LLM**, Länge im Service gekappt. Nur der Generator schreibt. |
| `summary_run_id` | UUID, null, **read-only** | Lauf, zu dem die Summary gehört; Gate verlangt `summary_run_id == latest_completed_run.id`. |
| `impact_source` | CharField (`none`/`analysis`/`manual`/`hybrid`), default `none`, **read-only** | Woher die Zusammenfassung stammt; `analysis` nur durch den Generator. |
| `impact_generated_at` | DateTimeField, null, **read-only** | Zeitpunkt der Generierung. |
| `impact_override_reason` | TextField, blank | Pflicht, wenn im `extended`-Rigor `impact_assessment` manuell überschrieben wird (`CheckConstraint`: `impact_source='hybrid'` ⇒ nicht leer). |
| `impact_truncation_waiver_reason` | TextField, blank | Getrennte, auditierte Quittung für einen `truncated`-Lauf im `extended`; nicht mit dem Freitext-Override vermischen. |
| `truncation_waiver_run_id` | UUID, null | Lauf, auf den sich die Quittung bezieht. |
| `truncation_waiver_by` | FK `persistence.User`, `SET_NULL`, null | Approver/Admin, der quittiert hat. |
| `truncation_waiver_expires_at` | DateTime, null | Ablauf der Quittung; abgelaufen ⇒ Gate blockiert wieder. |

`description`, `impact_assessment` und `change_reason` bleiben **unverändert
bestehen** (keine Spaltenlöschung in v1). Im `extended`-Rigor gilt:
`impact_assessment` ist die **Ergänzung** des Menschen, nicht der Nachweis;
die API markiert das Feld als `override` und verlangt
`impact_override_reason`.

#### 4.2.2 `ChangeRequestAffectedItem` (Erweiterung, additiv)

| Feld | Typ | Zweck |
|---|---|---|
| `change_action` | CharField (`add`/`modify`/`remove`), default `modify` | Art der Änderung; „remove" ist für Abkündigungen nötig. |
| `rationale` | TextField, blank | Warum dieses Artefakt im Change Set ist. |
| `origin` | CharField (`manual`/`analysis`/`suggestion`), default `manual` | Herkunft (Mensch, übernommenes Finding, Vorschlag). |
| `removed_reason` | TextField, blank | Nur bei `change_action="remove"`: warum entfernt; `state_after` bleibt `null`. |

**Set-Aktualisierung ist diff-basiert**, nicht delete-all+recreate: bestehende
Zeilen behalten `rationale`, `origin`, `version_before` und ihren
`state_before`-Snapshot; nur neue IDs werden angelegt, entfernte gelöscht,
geänderte aktualisiert. Ein separater `update_affected_item`-Pfad ändert
`change_action`/`rationale`/`origin`, ohne den Replace-Pfad zu benutzen.
`set_affected_items` bumpt `ChangeRequest.version` und emittiert
`CHANGE_REQUEST_UPDATED`, damit `on_write` und der `affected_items_hash` die
Änderung sehen. `adopt_finding` nutzt denselben Pfad und darf bestehende
Einträge nicht zurücksetzen. Bei `change_action="remove"` wird der
After-Snapshot beim Abschluss bewusst nicht gezogen (`state_after=null`,
`reason="removed"`), weil das Artefakt dann nicht mehr existiert.

#### 4.2.3 `ChangeImpactRun` (neu, TenantScopedModel)

| Feld | Typ | Zweck |
|---|---|---|
| `change_request` | FK → `ChangeRequest`, CASCADE, `related_name="impact_runs"` | Zugehörigkeit. |
| `workspace_id` | UUID, `db_index` | **Explizite Workspace-Fence**; RLS deckt nur den Tenant, nicht den Workspace. Jede Query filtert zusätzlich. |
| `baseline` | FK → `baseline.BaselineSnapshot`, `SET_NULL`, null, `related_name="change_impact_runs"` (API-Alias `baseline_id`) | Konfiguration, gegen die bewertet wurde (P2); beim Lauf aus `cr.baseline`. |
| `status` | CharField (`pending`/`running`/`completed`/`failed`) | Lebenszyklus des Laufs; `stale` wird abgeleitet, nicht persistiert. |
| `trigger` | CharField (`manual`/`on_submit`/`on_write`/`scheduled`) | Auslöser; dieselbe Konstante wie die Policy-Choices. |
| `algorithm_version` | CharField (z. B. `v1`) | Reproduzierbarkeit. |
| `root_item_ids` | JSONB (Liste) | Sortierte Wurzeln des Laufs; Basis der Gate-Bindung. |
| `roots_source` | CharField (`change_set`/`explicit`) | Nur `change_set` ist gate-fähig; Vorab-Analysen im `draft` sind `explicit`. |
| `gate_eligible` | Boolean | `true` nur, wenn `roots_source="change_set"` und Wurzeln = Affected Items. |
| `graph_fingerprint` | CharField(64) | SHA-256 über Wurzeln, erreichbare Knoten/Kanten (Content-Hash), Link-Katalog und Policy — der volle Laufbeleg. Baseline ist **nur Provenienz**, nicht Teil des Hashes. |
| `gate_fingerprint` | CharField(64) | SHA-256 über Wurzeln + für **alle** `visited_node_ids` `(artifact_id, content_hash, workflow_state, lifecycle_status, suspect)` + **alle inzidenten Kanten dieser Knoten** + Katalog + Policy; die im Gate-Read **ohne Voll-Traversierung** nachgerechnete Frischezusage. |
| `affected_items_hash` | CharField(64) | SHA-256 über die Wurzeln (`artifact_id`, Content-Hash, `lifecycle_status`). |
| `visited_node_ids` | JSONB (Liste) | Audit-Trail und Gate-Frontier (nicht die volle Erreichbarkeit). |
| `catalog_hash` | CharField(64) | SHA-256 der effektiven Link-Typ-Definitionen. |
| `node_count`, `edge_count`, `path_count` | Integer | Umfang; `truncated` separat. |
| `truncated` | Boolean | Cap erreicht (Tiefe/Knoten/Pfade). |
| `truncated_reason` | CharField, blank | `depth`/`nodes`/`paths`/`scope`. |
| `include_semantic` | Boolean | Ob semantische Context-Edges einbezogen wurden. |
| `policy_hash` | CharField(64) | SHA-256 der effektiven Policy; Teil der Idempotenz. |
| `forced` | Boolean, default `false` | Ein bewusst erzwungener Lauf; von der Idempotenz-Unique ausgenommen, rate-limitiert. |
| `pinned` | Boolean, default `false` | Schutz vor Retention, sobald eine Disposition gesetzt wurde. |
| `llm_used`, `llm_provider`, `llm_model`, `prompt_version` | Bool/Char/Char/Char | Provenienz der beratenden Annotation. |
| `heartbeat_at` | DateTime, null | Watchdog für hängende `running`-Läufe. |
| `error` | TextField, blank | Fehlertext bei `failed` (`timeout`, Provider-Fehler). |
| `started_at`, `finished_at` | DateTime, null | Laufzeit. |

Constraints/Indizes: **ein** zusammengesetzter Index
`(change_request, status, created_at)` und `(status, created_at)` (der
`workspace_id`-Index kommt vom `db_index=True`-Feld); **partielle UNIQUE**
`(change_request, graph_fingerprint)` `WHERE forced = false AND status IN
('pending','running','completed')` als DB-Anker der Idempotenz (Policy steckt
bereits im Fingerprint; ein `failed`-Lauf blockiert keinen Retry). „Letzter
Lauf" wird deterministisch nach `(created_at DESC, id DESC)` gelesen. Ein
Watchdog-Sweep
(`status, created_at`) markiert hängende `pending`/`running`-Läufe als
`failed` (`error="timeout"`). Retention: pro CR bleiben die letzten N Läufe
(Default 20) bzw. eine TTL; ältere werden gelöscht, außer ein Lauf wird von
einer Disposition, `summary_run_id` oder `inherited_from_run_id`
referenziert. RLS-Policy wie bei
`as_change_request_affected_item`.

#### 4.2.4 `ChangeImpactFinding` (neu, TenantScopedModel)

| Feld | Typ | Zweck |
|---|---|---|
| `run` | FK → `ChangeImpactRun`, CASCADE, `related_name="findings"` | Zugehörigkeit. |
| `artifact_id` | CharField(64) | Artifact-UUID des betroffenen Artefakts (kein Cross-App-FK, wie Affected Items). |
| `entity_type` | CharField(32) | Diskriminator (`Requirement`, `ArchitectureElement`, `TestCase`, `Icd`, …). |
| `hop_distance` | PositiveSmallInteger | Kürzeste Distanz zum Change Set. |
| `weight` | Decimal(6,4) | Produkt der Kantengewichte, auf `[0,1]` geklemmt und auf 4 Nachkommastellen quantisiert. |
| `severity` | CharField (`info`/`warning`/`blocking`) | Gate-Relevanz; **ausschließlich deterministisch** aus Gewicht/`coverage_relevant`/Hop-Distanz/`suspect`. Das LLM darf `severity` **nicht ändern** (weder heben noch senken) — es liefert nur `rationale`. **Invariante:** `origin=semantic` ⇒ nie `blocking`. |
| `origin` | CharField (`deterministic`/`semantic`) | Herkunft der Kante; `llm` ist kein Ketten-/Finding-Origin, sondern Annotation. |
| `via_link_types` | JSONB (Liste) | Aggregierte Link-Typen aller Ketten (für die Listenansicht). |
| `chain_count` | PositiveSmallInteger | Anzahl gespeicherter Ketten (max. 3); im Engine-Transaktionsblock geschrieben. |
| `rationale` | TextField, blank | LLM-/Mensch-Begründung; im UI als „KI-generiert, ungeprüft" gelabelt. |
| `disposition` | CharField (`open`/`accepted`/`mitigated`/`rejected`/`waived`), default `open` | Menschliche Entscheidung (Default für alle Ketten). |
| `gate_open` | **Property, keine Spalte** | `true`, wenn (keine Ketten und `disposition="open"`) oder mindestens eine Kette effektiv `open` ist. Wird im Service/Serializer berechnet; kein zusätzliches gespeichertes Dispositionsfeld, keine DB-Spalte. |
| `inherited_from_run_id` | UUID, null | Herkunft einer übernommenen Disposition aus dem vorherigen Lauf (Churn-Schutz). |
| `decided_by`, `decided_at` | FK `persistence.User` (`SET_NULL`, null) / DateTime | Audit der menschlichen Entscheidung. |
| `note` | TextField, blank | Begründung; **Pflicht** bei `mitigated`/`waived`/`rejected` (`CheckConstraint`). |

UNIQUE `(run, artifact_id)`; Index `(run, disposition)` (der `tenant`-Index
kommt vom FK). Dispositionen sind **human-only** (interaktive Bearer-Session; Agenten und
User-/Relay-Keys erhalten `PERMISSION_DENIED`), analog zu
`suggestion.accept/reject`, aber strenger.

**Verwaiste Findings:** `artifact_id` ist kein FK. Beim Read wird die Existenz
per Bulk-Lookup geprüft; nicht mehr auflösbare Findings werden als
`severity=info`, `disposition=waived`, `note="artifact deleted"` behandelt und
aus der Gate-Wertung genommen (Warnung `finding_outdated`).

#### 4.2.5 `ChangeImpactChain` (neu, TenantScopedModel)

Eigene Tabelle statt JSONB im Finding (Entscheidung D6): jede Wirkkette ist ein
eigener, auditierbarer Datensatz und kann später gefiltert/aggregiert werden.

| Feld | Typ | Zweck |
|---|---|---|
| `finding` | FK → `ChangeImpactFinding`, CASCADE, `related_name="chains"` | Zielknoten; der Lauf wird über `finding.run` gelesen (kein doppelter `run`-FK, keine Inkonsistenz). |
| `root_artifact_id` | CharField(64), `db_index` | Wurzel des Change Sets, die diese Wirkung verursacht. |
| `path_hash` | CharField(64) | SHA-256 über die **kanonische** Pfadfolge (`artifact_id|link_id|link_type|direction`, lowercase UUIDs, feste Reihenfolge); verhindert Duplikate. |
| `path` | JSONB | `[{artifact_id, link_id, link_type, direction, suspect, weight}]` vom Wurzel- zum Zielknoten; Anzeige-/Evidenzfeld, nicht durchsuchbar. |
| `hop_distance` | PositiveSmallInteger | Länge der Kette; `CheckConstraint` 1…6, `jsonb_array_length(path) = hop_distance`. |
| `weight` | Decimal(6,4) | Produkt der Kantengewichte, geklemmt auf `[0,1]`; Hop-Gewichte stehen nur im `path`, nicht als eigene Spalte. |
| `origin` | CharField (`deterministic`/`semantic`) | Herkunft; `llm` ist kein Ketten-Origin. |
| `via_link_types` | JSONB (Liste) | Link-Typen dieser Kette. |
| `disposition` | CharField (gleiches Enum wie Finding), **null** | Optionaler Override; `null` = erbt die Finding-Disposition. |
| `inherited_from_run_id` | UUID, null | Herkunft einer übernommenen Ketten-Disposition (Lauf-zu-Lauf). |
| `decided_by`, `decided_at` | FK `persistence.User` (`SET_NULL`, null) / DateTime | Audit der Ketten-Entscheidung. |
| `note` | TextField, blank | Begründung; **Pflicht** bei `mitigated`/`waived`/`rejected`. |

UNIQUE `(finding, path_hash)`; Indizes `(finding, path_hash)` und
`(root_artifact_id)` (FK-/`db_index`-Indizes separat). Pro Finding werden
maximal `max_paths_per_finding` (Code-Konstante 3)
Ketten gespeichert; die Auswahl ist deterministisch (kürzester Pfad, dann
höchstes Gewicht, dann lexikografische `path_hash`).

**DB-Constraints (nicht nur Python-Validierung):** `status`/`trigger`/
`severity`/`origin`/`change_action`/`disposition` als `CheckConstraint`
(`... IN (...)`), `weight BETWEEN 0 AND 1`, `hop_distance BETWEEN 1 AND 6` bzw.
`>= 0` am Finding, `chain_count <= 3`,
`jsonb_array_length(path) = hop_distance`,
`disposition IN ('mitigated','waived','rejected') ⇒ note <> ''` (Finding und
Chain), `impact_source='hybrid' ⇒ impact_override_reason <> ''` am CR. Die
**Workspace-Fence** läuft über `run.workspace_id`; Findings/Chains filtern
über `run__workspace_id` (RLS deckt nur den Tenant).

**Effektive Disposition (D4 = „beides erlauben"):**
`chain.effective = chain.disposition ?? finding.disposition`. Setzt der CCB
die Finding-Disposition, erben alle Ketten ohne eigenen Override.
`finding.gate_open = true` genau dann, wenn (keine Ketten und
`finding.disposition == "open"`) oder mindestens eine Kette effektiv `open`
ist. `gate_open` ist **derived und read-only**; es gibt kein zweites
Dispositionsfeld am Finding. Das Gate prüft `finding.gate_open` für
blockierende Findings.

#### 4.2.6 Change-Impact-Policy (global + Workspace)

Die Analyseparameter sind **keine** Code-Konstanten, sondern eine
dreistufige Konfiguration über den bestehenden `PreferenceKey`-Mechanismus
(`global` = tenant-weit, `workspace` = Override; kein `user`-Level, weil es
eine organisatorische Policy ist). Die Keys liegen im besitzenden
`application`-Modul (`application/change_impact_policy.py`) und werden im
`ready()` der `application`-App registriert; das Muster ist
`backend/traceability/apps.py:64-89`. Die Zahlwerte werden **typisiert**
(enum → int) aufgelöst, damit `"200"` und `200` nicht im Fingerprint driften.

| Key | Typ | Default | Wirkung |
|---|---|---|---|
| `change_impact.trigger` | enum `manual`/`on_submit`/`on_write`/`scheduled` | `manual` | Wann ein Lauf entsteht. `on_write` wird entprellt (siehe unten). |
| `change_impact.schedule_interval_hours` | enum `6`/`12`/`24`/`168` | `24` | Nur bei `scheduled`; Celery-Beat-Scan. |
| `change_impact.semantic_edges` | bool | `false` | Semantische Context-Edges einbeziehen (nie blockierend). |
| `change_impact.llm_annotation` | bool | `false` | Beratende LLM-Annotation aktivieren. |
| `change_impact.max_depth` | enum `2`/`3`/`4`/`5`/`6` | `4` | Traversierungstiefe. |
| `change_impact.max_nodes` | enum `100`/`200`/`500` | `200` | Knoten-Cap; oberhalb Celery. |
| `change_impact.min_weight` | enum `0.01`/`0.05`/`0.1`/`0.2` | `0.05` | Abbruchschwelle. |

`get_preference` liefert den effektiven Wert (Workspace > global > Default);
die Antwort von `analyze_impact` und `impact_context` nennt die aufgelöste
Policy und ihre Quelle (`workspace`/`global`/`default`), damit ein Lauf
reproduzierbar bleibt. `on_write` enqueued eine **entprellte** Celery-Aufgabe
(ein Lauf pro CR und Zeitfenster, z. B. 60 s), damit nicht jeder Feldspeicher-
Vorgang einen Lauf auslöst. `scheduled` scannt periodisch CRs in `draft`/
`submitted`, deren letzter Lauf fehlt oder `stale` ist.

### 4.3 Wirkketten-Algorithmus (`v1`)

1. **Wurzeln:** alle `ChangeRequestAffectedItem.item_id`. Optional
   `root_item_ids` für eine Vorab-Analyse im `draft` (werden mit dem
   `_validate_affected_items`-Muster gegen `Artifact.unscoped.filter(
   tenant_id=…, workspace_id=cr.workspace_id)` geprüft; fremde IDs ⇒
   `VALIDATION_ERROR` ohne Existenzleck; noch nicht im Change Set). Die
   Wurzeln werden am Run persistiert
   (`root_item_ids`, `roots_source`). **Gate-fähig ist nur**
   `roots_source="change_set"` **und** Mengengleichheit
   `root_item_ids == {affected_item.item_id}`; Vorab-Läufe sind
   `gate_eligible=false` und können das Gate nicht befriedigen.
2. **Kanten:** `TraceLink` **plus die Hierarchie-Union** aus
   `Requirement.parent`, `ArchitectureElement.parent_id` und der
   `Document`/`WorkItem`-Zerlegung — über den bestehenden Helper
   (`application/tier_compute`), nicht als zweite Kantenmenge. Die
   Propagationsrichtung wird **je Change-Action** (§4.3.3) und aus dem Katalog
   abgeleitet — nicht pauschal „beide Richtungen":
   - `suspect_rule == target_change_flags_source` → Kante Ziel → Quelle,
   - `suspect_rule == source_change_flags_target` → Kante Quelle → Ziel,
   - `suspect_rule == parent_change_flags_children` → Kante Quelle → Ziel,
   - `suspect_rule == none` → überspringen (kein Impact),
   - `impact_weight` multipliziert das Pfadgewicht (auf `[0,1]` geklemmt).
   Hierarchie-Kanten laufen als `link_type="hierarchy"`, `origin=deterministic`.
   **Jeder Hop** filtert zusätzlich auf `tenant_id` und
   `Artifact.workspace_id == cr.workspace_id` (Defense-in-Depth), auch wenn
   TraceLinks die Workspace-Zugehörigkeit erben sollten.
   Semantische `ContextEdge`s werden nur mit `include_semantic=true` (Policy
   oder Call-Parameter) und als `origin=semantic` einbezogen; sie sind **nie**
   blockierend (DB-/Service-Invariante).
3. **Change-Action-Semantik:** `modify` traversiert ausgehende und eingehende
   Kanten; `remove` traversiert **eingehende** Kanten (wer verweist auf das
   entfernte Artefakt?); `add` verlangt mindestens eine Pflichtkante
   (`allocated-to`/`decomposes`) und erzeugt sonst das Warn-Finding
   `change_set_item_without_trace`.
4. **Grenzen:** Defaults aus der Policy (§4.2.6): `max_depth=4` (Hard-Cap 6),
   `max_nodes=200` (Hard-Cap 500), Gewichtsschwelle `0.05`;
   `max_paths_per_finding=3` ist eine **Code-Konstante** (kein Policy-Key).
   Zyklen werden über eine besuchte Menge abgefangen;
   `truncated=true` bei Erreichen eines Caps (`truncated_reason`).
5. **Fingerprint (Frische, Inhaltsbild statt `version`):** Zwei Ebenen:
   - **`graph_fingerprint` (voller Laufbeleg):** SHA-256 über die Wurzeln
     `(artifact_id, content_hash, lifecycle_status)`, die erreichbare
     Nachbarschaft `(artifact_id, content_hash, lifecycle_status,
     workflow_state)` + Kanten `(link_id, link_type, source_id, target_id,
     suspect_flagged_at)`, die Hierarchie-Kanten, die
     Link-Katalog-Definitionen, die effektive Policy und
     `algorithm_version`. **Nicht** `baseline_id`: der Baseline-Link passiert
     erst bei der Freigabe und würde den gerade geprüften Lauf entwerten; die
     Baseline bleibt Provenienz am Run.
   - **`gate_fingerprint` (Gate-Read):** SHA-256 über Wurzeln + für **alle**
     gespeicherten `visited_node_ids` `(artifact_id, content_hash,
     workflow_state, lifecycle_status, suspect)` + **alle inzidenten Kanten
     dieser Knoten** + Katalog + Policy. Dieses Bild wird im Gate-Read **ohne
     Voll-Traversierung** neu berechnet (Batch-Lookup über die bekannte
     ID-Menge, `O(frontier)`). Eine Inhaltsänderung, ein Suspect-Flip oder
     eine neue Kante an einem besuchten Knoten wird damit erkannt; eine
     Änderung außerhalb der Frontier kann den Impact nicht vergrößern.
     **`content_hash`** ist der Hash der kuratierten Feldwerte aus
     `baseline.state_capture.capture_states`, **ohne** die Schlüssel
     `version` (Lock-Counter), `status`/`suspect` (separat gehasht) und
     `baseline` selbst. Das ist Pflicht: `capture_states` liefert `version`
     mit, und ohne Ausschluss würde ein No-op-Save den Lauf entwerten
     (False-Stale) bzw. ein Suspect-/Bulk-Update unentdeckt bleiben.
     Capture-Fehler sind **fail-closed** (`failed`/`stale`), nicht ein leerer
     Hash. Da `capture_states` fehlende Zeilen still überspringt und ohne
     Tenant-Kontext leere Workflow-States liefert, gilt: `len(states) ==
     len(requested_ids)` **und** jeder Knoten hat einen nicht-leeren
     `content_hash`/`workflow_state`; jeder Mismatch ⇒ Lauf `failed` bzw.
     Gate `CHANGE_IMPACT_STALE`.
   - LLM-Provenienz (`llm_model`, `prompt_version`) ist **nicht** Teil des
     Fingerprints; sie ändert die deterministischen Findings nicht und würde
     nur Stale-Rauschen erzeugen.

   Zusätzlich speichert der Run `affected_items_hash` (nur die Wurzeln) und
   `visited_node_ids` (Audit **und** Gate-Frontier). Bei `truncated` gilt der
   Vergleich nur für den erreichbaren Cap-Bereich; der Kontext weist
   `stale_reason="truncated_scope"` aus. `stale` wird **nicht persistiert**,
   sondern beim Gate/Read aus `gate_fingerprint` abgeleitet.
6. **Dispositions-Vererbung (Churn-Schutz):** Ein neuer Lauf übernimmt
   Dispositionen des letzten Laufs desselben CR nur bei unverändertem
   `(artifact_id, severity, path_hash)` (Finding-Ebene: `(artifact_id,
   severity)`) und setzt `inherited_from_run_id` an Finding **und** Kette.
   Ändert sich Severity oder
   Gewichts-Bucket, startet die Kette **`open`** — sonst würde eine geerbte
   `waived`-Entscheidung nach einer Katalog-/Gewichtsänderung das Gate
   öffnen.
7. **LLM-Annotation (optional, beratend):** nur wenn die Policy
   `change_impact.llm_annotation` oder der Call-Parameter es erlaubt; genau ein
   Aufruf nach dem deterministischen Lauf, Eingabe sind die Top-Findings
   (max. 50), nur mit minimierten Feldern (Typ, `uid`, Link-Typ; keine
   Volltexte). Ausgabe `{artifact_id, rationale}`; unbekannte IDs werden
   verworfen; Fehler ⇒ Lauf bleibt `completed` mit `llm_used=false`.
   Das LLM darf keine neuen Findings oder Ketten erzeugen und **`severity`
   nicht ändern** — die Gate-Relevanz bleibt deterministisch.
8. **Kosten/Performance:** synchron bis zum Policy-Cap (Default 200); darüber
   Celery-Task mit demselben Service (Plan S4). Ein Lauf ist idempotent über
   `(change_request, graph_fingerprint)` (Policy steckt im Fingerprint); ein
   identischer Lauf wird wiederverwendet, sofern nicht `force=true`. Die
   Traversierung ist frontier-batchted (kein N+1), der Perf-Test prüft auch
   die Query-Anzahl.

### 4.4 Freitext-Strategie („Textfelder ersetzen")

| Feld | `minimal` | `standard` | `extended` |
|---|---|---|---|
| `change_reason` | optional | optional | **Pflicht** (bestehend) |
| `description` | frei | frei | frei (Narrativ) |
| `impact_assessment` | frei | frei | **Addendum**; nur mit `impact_override_reason` schreibbar; nicht Gate-relevant |
| `impact_summary` | optional | optional | **deterministisch generiert und Pflicht** (Gate; `summary_run_id == latest_completed_run.id`; kein LLM; persistiert nur Aggregate) |
| Change Set | freiwillig | freiwillig | **≥ 1** (bestehend, auf `submitted` vorgezogen) |
| Impact-Analyse | optional | optional (kein Hinweis, O3) | **completed + frisch + keine offenen blockierenden Findings** |

Damit wird das Versprechen „Textfelder ersetzen" eingehalten, ohne die
bestehende API zu brechen: Die Spalten bleiben, aber im höchsten Rigor ist der
Freitext nicht mehr der Nachweis. Die Anzeige führt `impact_summary` als
Primärtext und `impact_assessment` als einklappbares Addendum. Die Summary ist
**kein LLM-Text**: reine Template-Interpolation aus persistierten Feldern,
damit der Gate-Nachweis nicht derselben Injektionsfläche wie die Annotation
unterliegt. `impact_summary`/`impact_generated_at`/`impact_source` sind im
Serializer **read-only** und nur im Detail-/Kontext-Read enthalten, nicht in
der CR-Liste (Payload-Bloat/N+1).

### 4.5 Rigor-Gate

Neues Preset-Feature `structured_change_impact`:

| Tier | Wert | Verhalten |
|---|---|---|
| `minimal` | `false` | Keine Analysepflicht; CR wie heute. |
| `standard` | `false` | Analyse optional; **kein** automatischer Hinweis (O3). |
| `extended` | `true` | Gate auf `draft → submitted`. |

Der Lauf entsteht gemäß Policy `change_impact.trigger` (§4.2.6), Default
`manual`. Bei `on_submit` stößt der Service im `extended`-Rigor automatisch
einen Lauf an, wenn keiner frisch vorliegt; bei `manual` blockiert die
Transition mit `CHANGE_IMPACT_MISSING`, bis ein Mensch den Lauf startet. Der
automatische Lauf ist synchron bis zum Knoten-Cap; darüber bleibt die
Transition blockiert und der Client startet die Analyse asynchron. `on_write`
läuft entprellt, `scheduled` über Celery-Beat. Ein manueller Lauf bleibt
jederzeit möglich.

**Gate-Verortung (Sicherheitsgrenze):** Das Gate darf **nicht** nur in
`ChangeRequestService.transition_status` liegen. Die generische Route
`/api/v1/change-requests/{pk}/transitions/`, `review.approve`, MCP
`change_request.submit_for_review` und `artifact.bulk_transition` rufen
`WorkflowFacade.transition` direkt auf und würden ein Service-Gate umgehen.
Das Gate wird deshalb als **gemeinsame Precondition** in
`workflow/precondition_rules.py` implementiert und vom `TransitionValidator`
für `item_type="ChangeRequest"` ausgeführt; der Service bleibt die
Fachfassade, ist aber nicht die einzige Durchsetzung. Ein Entry-Point-
Paritätstest muss **jeden** dieser Pfade auf den Blockfall prüfen.

**Transaktionsgrenze:** Der automatische Lauf läuft in einer **eigenen**
Transaktion **vor** der Transition (oder als Celery-Task). Die
Transition-Transaktion enthält keinen Graph-Walk, kein `bulk_create` und
keinen LLM-Aufruf. Sie liest den persistierten Run-Stand und berechnet
**nur den `gate_fingerprint`** über die gespeicherte Frontier
(`visited_node_ids` + deren inzidente Kanten) — kein voller Graph-Walk. Die
CR-Zeile wird mit `select_for_update` gesperrt; das serialisiert Change-Set-
und CR-Writes, **nicht** beliebige TraceLink-/Artifact-Writes. Graph-Änderungen
werden ausschließlich über den `gate_fingerprint` erkannt (Abweichung ⇒
`CHANGE_IMPACT_STALE`). Rollen- und SoD-Prüfung laufen **vor** den
Content-Gates, damit ein unberechtigter Aufrufer `PERMISSION_DENIED` statt
eines Impact-Fehlercodes sieht.

**Human-only ist eine Authentisierungsaussage, kein Label:** Eine Disposition
darf nur aus einer interaktiven menschlichen Session kommen
(`ctx.auth_method == BEARER_TOKEN` **und** `ctx.api_key_id is None`), nicht
aus einem „user"-API-Key/Relay-Key. `actor_type=="user"` allein genügt nicht.
Disposition, Adopt und Truncation-Waiver sind deshalb **REST-only**; der
MCP-Transport akzeptiert nur API-Keys und kann diese Bedingung konstruktiv
nicht erfüllen. Die Prüfung liegt in Layer 2; optional Step-up/MFA für
Approver. Die Freigabe-Transition selbst bleibt beim bestehenden
Workflow-Rollenmodell (Agenten-Selbstapproval ist bereits blockiert); das ist
eine bewusste Restrisiko-Entscheidung, kein „human-only".

**Workspace-Fence:** `ChangeRequest`-Reads und alle neuen Endpunkte prüfen
nicht nur `tenant_id`, sondern die Workspace-Mitgliedschaft des Aufrufers
(`WorkspaceService`/MCP-Workspace-Scope). Ein fremder Workspace im selben
Tenant liefert `NOT_FOUND` (kein Existenzleck). Jeder Traversierungs-Hop
filtert zusätzlich auf `tenant_id` und `Artifact.workspace_id` der CR.

**Keine Vollständigkeits-Attestierung bei `truncated`:** Im `extended`-Rigor
blockiert ein `truncated=true`-Lauf das Gate (`CHANGE_IMPACT_INCOMPLETE`,
`details.reason="truncated"`). Ein Approver kann eine **eigene, auditierte
Quittung** setzen (`change_request.waive_truncated_impact`, REST-only):
`truncation_waiver_run_id`, `truncation_waiver_reason`,
`truncation_waiver_by`, `truncation_waiver_expires_at`. Das Feld
`impact_override_reason` ist dafür **nicht** verwendbar (es ist ein
Editor-schreibbares Freitext-Addendum). Der Waiver verlangt eine
OTP-gestützte Session (`"otp" in ctx.amr`), `truncation_waiver_by IS NULL`
gilt als **nicht quittiert**, und `expires_at` ist auf maximal 30 Tage
gedeckelt.

**Change-Set-Stabilität:** Ab `submitted` ist das Change Set eingefroren;
`update_change_request(affected_item_ids=…)`, `set_affected_items` und
`adopt_finding` antworten mit `CHANGE_SET_FROZEN` (409). Änderungen brauchen
eine neue CR-Revision. Zusätzlich prüft `approved` den `gate_fingerprint`
erneut (Defense-in-Depth); `approved → implemented` verlangt denselben
frischen Nachweis.

Gate-Prüfungen (nur `extended`, Feature an):

1. mindestens ein Affected Item,
2. **Root-Bindung:** der Lauf ist `gate_eligible`, `roots_source="change_set"`
   und `root_item_ids` ist **mengengleich** zu den Affected Items; ein
   Vorab-Lauf mit `root_item_ids` befriedigt das Gate nicht,
3. ein `completed`-Lauf existiert; ein danach folgender `failed`-Lauf macht
   ihn nicht ungültig, aber `failed` ohne `completed` ⇒ `MISSING`
   (`details.reason="failed"`), `pending`/`running` ⇒ `RUNNING`,
4. Fingerprint aktuell (sonst `stale`),
5. kein Finding mit `severity=blocking` und `gate_open=true` (abgeleitet aus
   Ketten-Overrides bzw. Finding-Disposition, §4.2.5),
6. `impact_summary` vorhanden **und** `summary_run_id == latest_completed_run.id`
   (nicht `latest_run`, sonst entwertet ein späterer `failed`-Lauf eine
   gültige Summary). Die Summary wird am Ende jedes erfolgreichen Laufs neu
   erzeugt.

Präzedenz: Rollen/SoD → `RUNNING` → `INCOMPLETE` → `MISSING`/`STALE` →
`OPEN_FINDINGS` → Summary.

**Gate-, Refresh- und Freeze-Kanten sind explizit markiert, nicht aus Rollen
geraten:** Der Zustandsgraph ist pro Workspace überschreibbar, und die
Rollen-Heuristik ist im Stock-Graphen falsch (`draft → submitted` ist
`editor/admin`, der erste Approver-Übergang ist `submitted → under_review`).
Deshalb tragen Transitionen drei explizite Metafelder (analog
`freeze_on_enter`):

| Metafeld | Bedeutung | Standard-Provisionierung | Validierung |
|---|---|---|---|
| `change_impact_gate: true` | Kante, an der die Analyse Pflicht wird | `draft → submitted` | genau eine |
| `change_impact_refresh: true` | Kanten, an denen die Frische erneut geprüft wird | `approved`, `approved → implemented` | null oder mehr |
| `change_set_freeze: true` | Kante, ab der das Change Set eingefroren ist | `draft → submitted` | genau eine |

Fehlt eine Pflichtmarkierung oder ist sie mehrdeutig, ist die Konfiguration
fail-closed ungültig. AC-6/AC-7 nennen `draft → submitted` nur als Default
dieser Markierungen. Kein Zustandsname wird im Code hartcodiert.

**Durchsetzung der Marker:** `TransitionDefinitionDTO` wird um
`change_impact_gate`, `change_impact_refresh` und `change_set_freeze`
erweitert (Parser, Persistenz, Editor-API). Eine Datenmigration markiert
`draft → submitted` in allen bestehenden `ccb_approval`-Definitionen; die
Invariante „genau eine Gate-/Freeze-Markierung" wird bei **jedem**
Definitions-Write geprüft (Provisioning, `update_custom_workflow`,
Granular-Mutationen) und im Gate-Read fail-closed validiert (0 oder >1 ⇒
Block). Der Frische-Re-Check bei `approved`/`approved → implemented` läuft in
**derselben Precondition** über die `change_impact_refresh`-Kanten, nicht im
Service. Auch SoD und der Affected-Item-Check werden in diese Precondition
gezogen, damit `/transitions/` sie nicht umgeht.

**Verifikation nach der Umsetzung:** Auch `approved → implemented` verlangt
einen frischen Lauf (`stale=false`, Lauf nach der letzten Graph-/Change-Set-
Änderung) oder eine begründete, auditierte Ausnahme. Ein Re-Submit nach
`rejected` erzwingt ebenfalls einen neuen Lauf.

Fehlercodes (REST/MCP einheitlich):

| Code | HTTP | Bedeutung |
|---|---|---|
| `CHANGE_IMPACT_MISSING` | 409 | Kein abgeschlossener Lauf (`details.reason` = `never`/`failed`). |
| `CHANGE_IMPACT_STALE` | 409 | Graph/Policy/Katalog hat sich seit dem Lauf geändert. |
| `CHANGE_IMPACT_OPEN_FINDINGS` | 409 | Offene blockierende Findings (Details: IDs/Count). |
| `CHANGE_IMPACT_INCOMPLETE` | 409 | Change Set leer oder Summary fehlt. |
| `CHANGE_IMPACT_RUNNING` | 409 | Ein Lauf ist `pending`/`running`; Details nennen `run_id` und Status. |
| `CHANGE_IMPACT_TIMEOUT` | 409 | Der Lauf hat den Timeout überschritten; Watchdog markiert ihn `failed`. |
| `CHANGE_IMPACT_POLICY_FORBIDDEN` | 400 | Call-Parameter verletzt die Policy-Obergrenze (falls nicht geklemmt). |
| `CHANGE_IMPACT_POLICY_UNAVAILABLE` | 409 | Preset-/Feature-Lookup nicht auflösbar; fail-closed. |
| `CHANGE_SET_FROZEN` | 409 | Change-Set-Änderung nach `submitted` (neue CR-Revision nötig). |
| `CHANGE_IMPACT_RATE_LIMITED` | 429 | Workspace-/Key-Tages- oder Minutenlimit für `analyze_impact`. |

Alle Gate-Verweigerungen sind **409** (Projektpräzedenz
`DocumentGateFailedError`/`BaselineGateBlockedError`); nur
`POLICY_FORBIDDEN` ist 400, `RATE_LIMITED` 429. Die Codes werden als eigene
`ValidationError`-Subtypen in `application/base.py` mit
`error_code`/`http_status`/`details` umgesetzt. **Transport-Nähte, die die
Implementierung treffen muss:**
- `workflow_facade._remap_workflow_exc` muss `EC_CHANGE_IMPACT_*` auf die
  dedizierten Subtypen mappen (Vorbild `EC_DOCUMENT_GATE_FAILED`), sonst
  degradiert jede Precondition-Verweigerung zu `VALIDATION_ERROR`/400.
- `map_tool_exception` muss den Subtyp **vor** `isinstance(ValidationError)`
  prüfen; sonst bleibt MCP bei `VALIDATION_ERROR`.
- `artifact.bulk_transition` behält seine Vier-Code-Envelope; die
  Impact-Codes stehen dort als `VALIDATION_ERROR` mit
  `details.change_impact_code` (bewusste, dokumentierte Abweichung). AC-13/18
  werden entsprechend formuliert.
- REST (`_EXC_TO_HTTP`, `_EXC_TO_CODE`, `_ERROR_MESSAGES`) und MCP
  (`ERROR_CODES`, `ERROR_CODE_MAP`, freie Slots `-32021…-32027`) werden
  vollständig registriert; eine Spec-Tabelle allein reicht nicht.

Die Feature-Auflösung ist **fail-closed**: Kann die Workspace-Policy nicht
geladen werden oder ist der Feature-Key unbekannt, blockiert das Gate, statt
still zu öffnen. Der Key `structured_change_impact` ist eine Modulkonstante
und wird in `FEATURE_KEYS` gepinnt. `PresetPolicyService.is_feature_enabled`
ist heute fail-open (fängt jede Exception, gibt `False`); das Gate nutzt
deshalb einen **strikten Seam** (`is_feature_enabled_strict`), der bei
Lookup-Fehler wirft. Der Gate-Read behandelt „nicht auflösbar" als Block
(`CHANGE_IMPACT_POLICY_UNAVAILABLE`, `details.reason="policy_unavailable"`).

Der bestehende Genehmigungs-Check (`approved` verlangt Affected Items) bleibt
als Verteidigungslinie erhalten. `standard` liefert bei fehlender Analyse
weder Block noch Hinweis; der `impact_context`-Read bleibt verfügbar, wenn ein
Client ihn explizit aufruft.

### 4.6 API- und MCP-Oberfläche

| Operation | REST | MCP | Schreibend | Rollen |
|---|---|---|---|---|
| Analyse starten | `POST /api/v1/change-requests/{id}/analyze-impact/` | `change_request.analyze_impact` | ja | Editor+; `force` nur Approver/Admin |
| Kontext lesen | `GET /api/v1/change-requests/{id}/impact-context/` | `change_request.impact_context` | nein | Viewer+ (Audit-Sektion gated, siehe unten) |
| Findings lesen | `GET .../impact-findings/?page=&page_size=&disposition=` | `change_request.impact_findings` | nein | Viewer+ |
| Run lesen | `GET .../impact-runs/{run_id}/` | `change_request.impact_run` | nein | Viewer+ |
| Disposition setzen (Finding) | `PATCH .../impact-findings/{finding_id}/` | — (REST-only) | ja | Approver/Admin, human-only |
| Disposition setzen (Kette) | `PATCH .../impact-chains/{chain_id}/` | — (REST-only) | ja | Approver/Admin, human-only |
| Truncation-Quittung | `POST .../waive-truncated-impact/` | — (REST-only) | ja | Approver/Admin, human-only |
| Analyse in Change Set übernehmen | `POST .../impact-findings/{finding_id}/adopt/` | — (REST-only) | ja | Editor+ (nicht nach `submitted`) |

**Run-Ressource:** Der asynchrone Pfad braucht eine lesbare Ressource; die
`latest_analysis.id` im Kontext ist sonst eine tote Referenz. `impact_run`
liefert Status, Zähler, Policy, `error` und `truncated`.

**Caps/Pagination (Projekt-Envelope):** `impact_findings` nutzt die
dokumentierte REST-Envelope `{count, next, previous, page_size,
max_page_size, results}` mit `page`/`page_size` (Default 25, Max 100). Die
Findings-Sektion des Kontexts trägt analog `findings_count`,
`findings_page`, `findings_page_size`, `findings_truncated`; getrennt davon
`graph_truncated`. `affected_items` ist auf 200 gecappt. Kein undefinierter
Cursor.

**Policy als Obergrenze:** Call-Parameter dürfen die effektive Policy nur
**restriktiver** machen (`max_depth`/`max_nodes` senken; `include_semantic`/
`include_llm` nur, wenn die Policy sie erlaubt). Überschreitungen werden
geklemmt; `policy.clamped` ist ein **Antwortfeld** (Liste der geklemmten
Keys), `policy_clamped` ein **Warncode**. `force=true` ist ausschließlich
Approver/Admin vorbehalten und rate-limitiert (max. 1 erzwungener Lauf pro CR
und Stunde). Kein Editor-Pfad.

`analyze_impact`-Parameter: `root_item_ids` (optional), `max_depth`,
`include_semantic`, `include_llm`, `force`. Fehlende Parameter werden aus der
effektiven Policy (§4.2.6) aufgelöst. Antwort enthält den Lauf, die aufgelöste
Policy mit Quelle, `policy.clamped` und eine kompakte Finding-Liste.
Dispositions-PATCH folgt `REST-CONVENTIONS.md` §1: `If-Match`-Mismatch ⇒
**412**, `expected_version`-Body-Mismatch ⇒ **409**; der Write bumpt
`version`. `note` ist bei `rejected`/`waived`/`mitigated` Pflicht.
`entity_id` ist die Entity-Zeilen-ID für entity-backed Typen und `null` für
Typen ohne eigenes Entity-Modell; `artifact_id` bleibt immer gesetzt.
`revision` ist optional (nur wenn `ArtifactVersion` existiert), `lock_version`
ist immer der Lock-Counter.

### 4.7 P1-3: Freigabe-Kontext (`impact_context`)

Antwortstruktur (gekürzt):

```json
{
  "contract_version": 1,
  "change_request": {"id": "...", "title": "...", "status": "submitted",
                      "change_reason": "...", "impact_source": "analysis",
                      "baseline_id": "..."},
  "affected_items": [
    {"artifact_id": "...", "entity_id": "...", "entity_type": "Requirement",
     "uid": "REQ-L1-007", "title": "...", "status": "approved",
     "lock_version": 4, "revision": 3, "change_action": "modify",
     "version_before": 3, "version_after": null,
     "state_before": {"title": "...", "acceptance_criteria": "..."},
     "state_after": null, "removed_reason": null}
  ],
  "policy": {"effective": {"trigger": "manual", "semantic_edges": false,
                            "max_depth": 4, "max_nodes": 200,
                            "min_weight": 0.05, "llm_annotation": false},
             "source": {"trigger": "workspace", "semantic_edges": "global",
                        "max_depth": "default"}},
  "latest_analysis": {"id": "...", "status": "completed", "finished_at": "...",
                       "algorithm_version": "v1", "truncated": false,
                       "llm_used": true, "stale": false},
  "findings": [
    {"artifact_id": "...", "entity_id": "...", "entity_type": "TestCase",
     "uid": "TC-12", "title": "...",
     "hop_distance": 1, "weight": 0.9, "severity": "blocking",
     "origin": "deterministic", "via_link_types": ["verifies"],
     "chains": [{"path_hash": "...", "weight": 0.9,
                 "path": [{"artifact_id": "...", "uid": "REQ-L1-007",
                           "title": "...", "link_type": "verifies",
                           "direction": "incoming", "suspect": false,
                           "weight": 1.0}],
                 "disposition": null, "effective_disposition": "open",
                 "inherited_from_run_id": null}],
     "disposition": "open", "gate_open": true,
     "inherited_from_run_id": null, "rationale": "..."}
  ],
  "findings_count": 12, "findings_page": 1, "findings_page_size": 25,
  "findings_truncated": false, "graph_truncated": false,
  "impact_stats": {"count_by_type": {"TestCase": 5, "ArchitectureElement": 4},
                   "blocking_count": 2, "max_weight": 0.9, "fan_out_max": 7,
                   "unlinked_change_set_items": 0},
  "coverage": {"requirements_affected": 3, "covered": 2, "uncovered": 1,
               "uncovered_ids": ["..."]},
  "test_evidence": {"linked_test_cases": 5, "last_run_status": "failed",
                    "aggregation": "latest_completed_run"},
  "audit_findings": [{"rule_id": "TRACE-P1", "severity": "blocker",
                       "message": "...", "artifact_ids": ["..."]}],
  "baseline": {"id": "...", "name": "...", "drift": true},
  "warnings": [{"code": "impact_analysis_stale", "detail": "..."},
               {"code": "graph_truncated"}]
}
```

Wichtig: Der Kontext ist **eine** Read-Operation, damit ein Genehmiger nicht
zehn Tools orchestrieren muss. Er bündelt bestehende Services
(`ChangeRequestService.list_affected_items`, `traceability.coverage`,
`audit.se_audit`, Baseline-Drift) und dupliziert keine Fachlogik.

**Scope und Kosten:** Der SE-Audit wird **nicht** pro CR-Read workspace-weit
neu gerechnet. Ein gecachter Audit-Report (TTL/Snapshot) wird auf die
CR-Artefaktmenge gefiltert; Coverage wird auf die betroffenen Requirements
eingeschränkt. Artefakt-Metadaten kommen aus **einem** Bulk-Lookup
(`Artifact.unscoped.filter(id__in=…)`) plus `state_reader`, nicht aus N+1.
`baseline.drift` nutzt den bestehenden Baseline-Drift-Pfad (Badge #399); ist
kein Service verfügbar, entfällt das Feld statt einen falschen Wert zu
liefern.

**Audit-Sektion ist gated:** `audit.se_audit` verlangt AUTHOR-Tier. Ein
Viewer-Read auf `impact-context/` liefert die Audit-Sektion deshalb **leer**
plus `warnings:[{"code":"audit_section_hidden"}]`; Approver/Author erhalten
die auf `artifact_ids ∩ affected_set` gefilterte Sektion ohne
Waiver-Details. Die Entscheidung wird in §4.6/§4.7 getestet, nicht implizit
gelassen.

**Item-Level-Permissions und Minimierung:** Der Kontext prüft pro Artefakt
die effektive Leseberechtigung (Item-Permission/Workspace-Rolle). Gesperrte
Artefakte werden ausgeblendet (`NOT_FOUND`-Semantik) und als
`warnings:[{"code":"item_hidden"}]` gezählt. `state_before` wird nur für
Rollen mit Item-Read ausgegeben; Audit-Messages werden gekappt/redigiert.
**`impact_stats`, `findings_count` und `coverage.uncovered_ids` werden aus
der sichtbaren Projektion des Requests gebildet**, nicht aus dem vollen Lauf:
sonst wäre ein gesperrtes Item über Zähler/UIDs ein Existenz-Orakel. Die
**persistierte** `impact_summary` ist ein Gate-Artefakt aus reinen
Typ-/Zahl-Aggregaten ohne Identitäten und wird nicht roh an Viewer
ausgeliefert; die UI rendert eine **request-scoped Summary** aus der
gefilterten Detailmenge. Die Regel „eine Antwort" gilt für die **sichtbare**
Menge; Caps/Paging bleiben verbindlich.

**Warnungen sind ein Enum**, keine freien Strings: `impact_analysis_stale`,
`impact_analysis_not_available`, `graph_truncated`, `findings_truncated`,
`audit_section_hidden`, `item_hidden`, `policy_clamped`, `finding_outdated`,
`change_set_item_without_trace`, `no_baseline`, `truncated_scope`. Neue Codes
sind additiv; Codes werden nie umbenannt oder entfernt.

### 4.8 Frontend (minimal, aber notwendig)

Heute existiert **keine** CR-Ansicht. Für den Mehrwert genügt v1:

- Route `/change-requests/:id` mit Kopf (Titel, Status, Requestor, Baseline),
- Change-Set-Tabelle (Artefakt, Typ, Aktion, Version vorher/nachher),
- Button „Wirkkettenanalyse starten" (Editor+), Laufstatus und `truncated`-Hinweis,
- Findings-Tabelle mit Pfad, Gewicht, Severity und Disposition (Approver+),
- generierte `impact_summary` als Primärtext, `impact_assessment` als Addendum,
- Freigabe/Ablehnung über die bestehenden Workflow-Transitionen,
- DE/EN-i18n und `data-testid` auf allen interaktiven Elementen.

**Einstieg (O2 entschieden):** Change Requests werden als eigener Typ in die
bestehende Freigaben-Queue (`/reviews`) aufgenommen (`WorkflowArtifactType`
`change-request`, `REVIEW_ACTION_CONFIG`), damit Approver sie dort sehen.
Zusätzlich verlinkt der `BaselineDriftBadge` die erzeugte CR-ID. Eine eigene
CR-Liste/Board-Ansicht gibt es in v1 **nicht**.

### 4.9 P1-2: Smart Refinement

**Ausgabeschema je Draft (additiv):**

```json
{
  "title": "string",
  "description": "string",
  "rationale": "string",
  "acceptance_criteria": [
    {"text": "string", "fulfilled": false, "evidence_ref": null}
  ],
  "verification_method": "Test|Review|Analysis|Inspection|Demonstration"
}
```

- **Kein neuer Attributtyp nötig:** `criteria-list` existiert bereits (#1288)
  und ist genau der generische Objekttyp für Checkbox-Zeilen:
  `{text, fulfilled, evidence_ref?}`. Das Frontend-Widget
  (`CriteriaList.tsx`) rendert Checkbox + Text pro Zeile. Der Draft liefert
  dieselbe Struktur; der Service normalisiert über
  `normalize_criteria_list`.
- `acceptance_criteria`: 1…7 Einträge, je 10…500 Zeichen, nicht doppelt,
  testbar formuliert (kein „soll gut sein"); `fulfilled` startet `false`.
- `verification_method`: muss dem bestehenden Enum entsprechen; fehlt sie,
  bleibt der Draft gültig, wird aber mit
  `incomplete_fields: ["verification_method"]` markiert. Die Methode bleibt
  **pro Requirement** (ISO 29148); eine Methode pro Kriterium ist D8b und
  nicht Teil von v1.
- **Prompts:** `DEFAULT_NEED_TO_SYSREQ` und
  `DEFAULT_SYSREQ_DECOMPOSE_NEXT_LEVEL` werden um die Felder erweitert; die
  Response-Anweisung wird strikt (JSON, keine Prosa).
- **Service:** `derive_requirements_from_need` und
  `decompose_requirement_next_level` übernehmen die Felder in die Drafts
  (additiv; alte Clients ignorieren sie).
- **Persistenz:** Der bestehende Accept-/Write-Pfad schreibt die AC über
  `RequirementService.set_acceptance_criteria` als `criteria-list`-Items
  (`fulfilled=false`) und setzt `verification_method`. Der Draft bleibt
  `ephemeral` (kein stilles Anlegen).
- **Validierung:** Der Service verwirft keine Drafts wegen fehlender AC; er
  markiert sie. Erst das `extended`-Genehmigungs-Gate verlangt sie (bestehend).
- **Rückwärtskompatibilität:** Antworten bleiben JSON-Arrays von Objekten;
  neue Keys sind optional. Ein alter Client, der `acceptance_criteria` als
  String-Liste erwartet, wird nicht unterstützt — die Änderung ist bewusst
  objektförmig (D8) und wird in den Draft-Typen dokumentiert.

## 5. Risiken und Gegenmaßnahmen

| Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|
| Graph-Explosion bei dichten Workspaces | Laufzeit, Speicher | Caps (Tiefe/Knoten/Pfade), Gewichtsschwelle, `truncated` sichtbar, Celery ab 200 Knoten. |
| LLM halluziniert Wirkung | falsche Freigabe | Deterministischer Graph ist die einzige Quelle für Findings; LLM liefert ausschließlich `rationale` und ändert `severity` nicht; keine neuen IDs; Provenienz wird gespeichert. |
| Veraltete Analyse | Freigabe auf altem Stand | Content-`graph_fingerprint` + `gate_fingerprint` über die Frontier; `extended`-Gate blockiert. |
| Fehlende Trace-Links | falsche Vollständigkeit | `change_set_item_without_trace`/`truncated`-Warnungen; SE-Auditor-Findings im Kontext; semantische Edges opt-in. |
| Performance der Kontext-Aggregation | langsame Freigabe | Ein Read-Service mit Caps; Findings max. 200; Audit-Cache/Scope; keine N+1-Abfragen; `select_related`/`prefetch`; p95-Ziel < 1 s. |
| RLS/Tenant-Leck | Datenleck | Neue Tabellen als `TenantScopedModel` + explizite `tenant_id`- und `workspace_id`-Filter + RLS-Policy + Tests. |
| Hängender Lauf | Gate dauerhaft blockiert | Heartbeat/Timeout, Watchdog-Sweep `running → failed`, Index `(status, started_at)`. |
| Unbegrenztes Wachstum | Betriebskosten | Retention (letzte N Läufe/TTL), Ketten-Cap, Celery-Aufräumjob. |
| Kosten | LLM-Budget | Ein Aufruf je Lauf, optional abschaltbar, bestehende Budget-/Rate-Seams. |
| Breaking Change | Clients brechen | Nur additive Felder/Endpunkte; keine Spaltenlöschung; `impact_context` separat. |
| Frontend-Umfang | Nutzen bleibt aus | S6 ist Pflicht-Slice; v1 bewusst minimal. |

### 5.1 Threat Model (4 Fragen)

1. **Was bauen wir?** Persistierte Impact-Läufe/Findings/Ketten pro Tenant mit
   RLS; Lesezugriff Viewer+, Disposition Approver/Admin human-only; Daten aus
   Workspace-Artefakten (Titel, Beschreibung, ICD-Parameter, Architektur) und
   optional ein LLM-Aufruf an Anthropic/OpenAI/Azure/Ollama.
2. **Was kann schiefgehen?** (a) Prompt-Injection über Artefakt-Titel/CR-Text
   manipuliert `rationale`/Severity; (b) Abfluss vertraulicher SE-Daten an
   Dritt-Provider; (c) Tenant-/Workspace-Überlauf im Prompt oder Read;
   (d) Markdown-/XSS-Injection über Summary/Kettenlabels; (e) Massen-
   `analyze_impact` durch einen Agenten-Key (Kosten-DoS); (f) falsche Freigabe
   auf veralteter/unvollständiger Analyse.
3. **Was tun wir dagegen?** Deterministische Gate-Severity (LLM liefert nur `rationale`, ändert `severity` nicht);
   LLM-Input als klar delimitiertes Datenfeld mit Längen-/Feld-Allowlist;
   `rationale` im UI als „KI-generiert, ungeprüft"; Summary **ohne LLM**;
   Markdown-Sanitizer; strikte Tenant-/Workspace-Filter und RLS; Provider-
   Opt-in/Redaction pro Workspace; Rate-/Budgets je Key; Root-Bindung und
   Content-Fingerprint.
4. **Konsequenzen?** Ohne diese Maßnahmen drohen Fehlfreigaben in regulierten
   Umgebungen, IP-/Kundendatenleck und Reputationsschaden. Die Analyse ist
   beratend; die Verantwortung bleibt beim menschlichen CCB.

### 5.2 Nicht-funktionale Ziele

| Ziel | Wert |
|---|---|
| `impact_context` p95 / p99 | < 1 s / < 3 s bei ≤ 200 Findings und ≤ 500 Knoten (Audit-Cache, Bulk-Lookups). |
| Engine-Lauf | < 3 s bei 500 Knoten; Query-Anzahl `O(max_depth)`, nicht `O(nodes)`. |
| Kosten | max. ein LLM-Aufruf je Lauf; LLM standardmäßig aus; Budget-Seam. |
| Rate-Limit | eigener DRF-Scope `change_impact_analyze`; Tagescap je Workspace/Key; `CHANGE_IMPACT_RATE_LIMITED` (429). |
| Retention | letzte 20 Läufe pro CR bzw. TTL; gelöscht wird nur, wenn `pinned=false` und keine Disposition/`summary_run_id`/`inherited_from_run_id` den Lauf referenziert. |
| Ausgabe-Härtung | `rationale` max. 500 Zeichen; Markdown serverseitig sanitisiert (nicht nur im Frontend). |
| Determinismus | identischer Inhaltsgraph + Policy ⇒ identischer Fingerprint und identische Findings-Reihenfolge. |

## 6. Entscheidungen (Stand 2026-11-28)

| ID | Frage | Entscheidung | Status |
|---|---|---|---|
| D1 | Freitext ersetzen oder ergänzen? | Generierte `impact_summary` ist im `extended`-Rigor der Nachweis; `impact_assessment` bleibt als Addendum (nur mit `impact_override_reason`). Keine Spaltenlöschung. | **entschieden** |
| D2 | Wo sitzt das `extended`-Gate? | `draft → submitted`; `approved` bleibt Verteidigungslinie. | **entschieden** |
| D3 | Welche Kanten? | Hard-Links (Trace/Allokation/Zerlegung) sind die Basis; semantische Edges sind opt-in und nie blockierend. Die Policy ist **global (tenant-weit) + Workspace-Override** konfigurierbar. | **entschieden** |
| D4 | Disposition pro Finding oder pro Kette? | **Beides:** Finding-Disposition ist der Default, Ketten-Disposition der optionale Override; das Gate prüft die effektive Disposition je Kette. | **entschieden** |
| D5 | Eigenes Preset-Feature? | `structured_change_impact` (minimal/standard aus, extended an). | **entschieden** |
| D6 | Pfade speichern? | Eigene `ChangeImpactChain`-Tabelle, nicht JSONB im Finding. | **entschieden** |
| D7 | Trigger? | Policy `change_impact.trigger`: Default `manual`; optional `on_submit`, `on_write` (entprellt), `scheduled` (Celery-Beat). Global + Workspace-Override. | **entschieden** |
| D8 | AC-Format? | Objekte pro Kriterium über den bestehenden `criteria-list`-Typ (`{text, fulfilled, evidence_ref?}`); `verification_method` bleibt pro Requirement. **Kein neuer Attributtyp nötig.** | **entschieden** |
| D8b | Methode pro Kriterium? | **Nein** — `verification_method` bleibt pro Requirement (ISO 29148); `criteria-list` wird nicht erweitert. | **entschieden** |
| D9 | Synchron oder async? | Synchron bis Policy-Cap (Default 200), Celery darüber. | **entschieden** |
| D10 | Was heißt „global"? | `global` = tenant-weit (`PreferenceValue.scope="global"`), nicht deployment-weit; Workspace überschreibt. Deployment-weite Defaults bleiben env/Settings. | **entschieden** |
| D11 | `on_write`-Semantik? | Entprellt (ein Lauf pro CR und 60-s-Fenster), nicht ein Lauf pro Feldspeicherung. | **entschieden** |
| D12 | Wo sitzt das Gate? | **Gemeinsame Workflow-Precondition** (`workflow/precondition_rules.py`/`TransitionValidator`), nicht nur im Service; gilt für alle Transition-Pfade. | **entschieden (Review)** |
| D13 | Was heißt „human-only"? | Interaktive Bearer-Session (`api_key_id is None`), nicht `actor_type="user"`; optional MFA-Step-up. | **entschieden (Review)** |
| D14 | Zählt `truncated` als vollständig? | **Nein** — im `extended` blockierend, außer begründete Approver-Ausnahme. | **entschieden (Review)** |
| D15 | Fingerprint-Basis? | **Content-Hash** aus `baseline.state_capture` + Re-Traversierung, nicht `Artifact.version`; Wurzeln, Hierarchie, Katalog, Policy. Baseline ist nur Provenienz am Run, **nicht** im Hash. | **entschieden (Review)** |
| D16 | `blocking`-Regel? | Deterministisch aus `coverage_relevant` + Hop-Distanz + `suspect` + Mindestgewicht; **nicht** pauschal Zieltyp `TestCase`/`Icd`; Fixture-Kalibrierung vor G3. | **entschieden (Review)** |
| D17 | Workspace-/Item-Fence? | Explizite `workspace_id` an Run, Workspace-Check in jedem Read, Item-Level-Read pro Artefakt, Hop-Fence. | **entschieden (Review)** |
| D18 | Migrationsort? | **`persistence/0158`** (CR-Modelle sind seit `persistence/0071` + `application/0024` dort im State), nicht `application/0041`. | **entschieden (Review)** |

### D4 — Erklärung (entschieden: beides erlauben)

Beispiel: Requirement `R` ändert sich. `R` wird von den Tests `T1` und `T2`
verifiziert, ist `C` zugeordnet, `C` zerlegt sich in `C1`/`C2`, und `C1` ist
durch ICD `I` beschrieben. Die Analyse findet fünf betroffene Artefakte:
`T1`, `T2`, `C`, `C1`, `I` — mit Ketten wie `R → C → C1 → I`.

- **Pro Finding:** Der CCB entscheidet **fünfmal**, je betroffenem Artefakt:
  `T1` accepted, `T2` mitigated, `C` accepted, `C1` accepted, `I` waived.
  Die Ketten bleiben als Begründung sichtbar. Weniger Entscheidungen, keine
  Doppelbefassung mit demselben Artefakt.
- **Pro Kette:** Der CCB entscheidet **pro Pfad**. Ist `I` über zwei Pfade
  erreichbar, gibt es zwei Entscheidungen für dasselbe Artefakt; bei Fan-out
  wächst die Zahl der Entscheidungen stärker als die Zahl der Artefakte. Dafür
  ist die Evidenz feiner („welcher Pfad ist akzeptabel?").

**Entscheidung:** beides. Die **Finding-Disposition** ist der Default und
deckt den Normalfall ab (eine Entscheidung je Artefakt). Die
**Ketten-Disposition** ist ein optionaler Override für den Fall, dass ein
bestimmter Pfad anders bewertet wird (z. B. „über `C1` akzeptabel, über `C2`
nicht"). Das Gate prüft die effektive Disposition je Kette; ein Finding ohne
Ketten fällt auf seine eigene Disposition zurück.

## 7. Akzeptanzkriterien

| ID | Kriterium |
|---|---|
| AC-1 | `derive_requirements_from_need` liefert je Draft `acceptance_criteria` als Objekte `{text, fulfilled:false}` (1…7) und `verification_method`; fehlende Methode wird als `incomplete_fields` markiert, der Draft bleibt nutzbar. |
| AC-2 | Der Accept-/Write-Pfad persistiert AC als `criteria-list`-Items (`fulfilled=false`) über `set_acceptance_criteria` und setzt `verification_method`; ein Read zeigt beides. |
| AC-3 | Ein CR kann eine Wirkkettenanalyse starten; der Lauf wird mit Status, Algorithmusversion, Fingerprint und Zählern gespeichert. |
| AC-4 | Die Analyse findet ausschließlich Artefakte, die über Katalog-konforme Kanten erreichbar sind; das LLM erzeugt keine neuen Findings. |
| AC-5 | Zyklen, Tiefe- und Knoten-Caps führen zu einem definierten Ende mit `truncated=true`, nicht zu einem Fehler oder einer Endlosschleife. |
| AC-6 | Ändert sich ein Knoten oder eine Kante nach dem Lauf, meldet der Kontext `stale`; im `extended`-Rigor blockiert `draft → submitted` mit `CHANGE_IMPACT_STALE`. |
| AC-7 | Im `extended`-Rigor blockiert `draft → submitted` ohne Change Set, ohne abgeschlossenen Lauf, mit offenen blockierenden Findings oder ohne Summary — jeweils mit dem spezifizierten Fehlercode. |
| AC-8 | Im `standard`-Rigor blockiert dieselbe Situation nicht und es gibt keinen automatischen Hinweis; der `impact_context`-Read bleibt auf expliziten Aufruf verfügbar. |
| AC-9 | `impact_context` liefert in einer Antwort CR-Kopf, Affected Items mit `lock_version`/`revision`/Status, effektive Policy mit Quelle, letzte Analyse, Findings mit Ketten, `impact_stats`, Coverage, Test-Evidenz, Audit-Findings, Baseline und Warnungen (paginierbar). |
| AC-10 | Eine Disposition kann nur von Approver/Admin und nur menschlich gesetzt werden; ein Agenten-Key erhält `PERMISSION_DENIED`. |
| AC-11 | Ein Finding lässt sich bewusst in das Change Set übernehmen; dabei entsteht ein `ChangeRequestAffectedItem` mit `origin=analysis` und Vorher-Snapshot. |
| AC-12 | Neue Tabellen sind tenant-isoliert (RLS + explizite Filter) und erscheinen nicht in einem fremden Workspace. |
| AC-13 | REST und MCP liefern dieselben Felder, Fehlercodes und Rollenverhalten; das Tool-Manifest ist driftfrei. |
| AC-14 | Die CR-Detailansicht zeigt Change Set, Analyse, Findings, Ketten und Summary; alle interaktiven Elemente haben `data-testid`; DE/EN sind vollständig. |
| AC-15 | `change_impact.trigger` und die Analyseparameter sind tenant-weit gesetzt und pro Workspace überschreibbar; die effektive Policy samt Quelle ist im Kontext sichtbar. |
| AC-16 | Jede gespeicherte Wirkkette ist ein eigener `ChangeImpactChain`-Datensatz mit `path_hash`, Pfad, Gewicht und Herkunft; Duplikate werden verhindert. |
| AC-17 | Eine Finding-Disposition gilt als Default für alle Ketten ohne Override; eine Ketten-Disposition überschreibt sie für genau diese Kette. Das Gate wertet die effektive Disposition je Kette aus. |
| AC-18 | Das Gate greift auf **allen** Transition-Pfaden (`/transition/`, `/transitions/`, `review.approve`, `change_request.submit_for_review`, `artifact.bulk_transition`), nicht nur im Service. |
| AC-19 | Ein Lauf ist nur gate-fähig, wenn seine Wurzeln mengengleich zum Change Set sind; ein Vorab-Lauf mit `root_item_ids` befriedigt das Gate nicht. |
| AC-20 | Ein `truncated=true`-Lauf blockiert im `extended`-Rigor, außer ein Approver quittiert begründet; `truncated` ist im Kontext sichtbar. |
| AC-21 | Human-only-Dispositionen verlangen eine interaktive Bearer-Session; ein „user"-API-Key/Relay-Key erhält `PERMISSION_DENIED`. |
| AC-22 | Reads und Analysen sind workspace- und item-level-gefenced; fremde Workspaces liefern `NOT_FOUND`, gesperrte Items werden ausgeblendet. |
| AC-23 | Der Fingerprint basiert auf Content-Hashes, Wurzeln, Hierarchie, Link-Katalog und Policy — nicht auf `Artifact.version`, `status`, `suspect` oder `baseline_id`. |
| AC-24 | Das Gate hängt an expliziten `change_impact_gate`/`change_set_freeze`/`change_impact_refresh`-Markern im `TransitionDefinitionDTO` (inkl. Backfill für Bestands-Workspaces); Provisioning **und** jeder Definitions-Write validieren die Invariante, das Gate-Read ist bei 0/>1 Markierungen fail-closed. |
| AC-25 | `force` ist ausschließlich Approver/Admin und rate-limitiert (Workspace-Dimension); `analyze_impact` hat einen eigenen DRF-Scope und antwortet bei Überschreitung mit 429. |
| AC-26 | Ab `submitted` sind `set_affected_items`/`update_change_request(affected_item_ids)`/`adopt_finding` mit `CHANGE_SET_FROZEN` blockiert; der Re-Check bei `approved`/`approved → implemented` läuft in derselben Precondition, nicht im Service. |
| AC-27 | Disposition, Adopt und Truncation-Waiver sind REST-only; MCP exponiert sie nicht. Der Waiver ist an Lauf, Approver, OTP-Session und Ablauf (max. 30 Tage) gebunden, nicht an `impact_override_reason`. |
| AC-28 | `impact_summary` enthält nur Aggregate (keine Titel/UIDs); `impact_stats`/`findings_count`/`coverage.uncovered_ids` werden aus der sichtbaren Projektion gebildet. |
| AC-29 | Der `gate_fingerprint` hasht für alle Frontier-Knoten Inhalt, Workflow-State, Lifecycle und Suspect; ein Content-Edit/Suspect-Flip an einem Nicht-Wurzel-Knoten ⇒ `stale`. |
| AC-30 | Capture-Vollständigkeit ist fail-closed: fehlende Zeile oder leerer Workflow-State ⇒ Lauf `failed`/Gate blockiert, kein leerer Hash. |

## 8. Offene Punkte (nicht blockierend)

| ID | Frage | Status/Wirkung |
|---|---|---|
| O2 | CR-Liste? | **entschieden:** CR als eigener Typ in der Freigaben-Queue; keine separate Liste in v1. |
| O4 | Sollen semantische Edges im `extended`-Gate blockieren dürfen? | **faktisch entschieden: nein** (D3/Invariante); bleibt nur als Testfall. |
| O5 | Wie wird `severity=blocking` kalibriert? | **entschieden:** Fixture-Set aus 3–5 Workspace-Ausschnitten in S0.6, Ziel ≤ 20 % `blocking`, Schwellen als Konstanten pinnen; Regel deterministisch (D16). |

## 9. Quellen

- ISO/IEC/IEEE 15288:2023, *Systems and software engineering — System life cycle processes*, §6.4.9 Configuration Management.
- ISO/IEC/IEEE 29148:2018, *Systems and software engineering — Life cycle processes — Requirements engineering*.
- Automotive SPICE Process Assessment Model 4.0, Prozess SUP.10 *Change Request Management*.
- INCOSE, *Systems Engineering Handbook*, 5. Aufl. (2023), Configuration Management.
- IREB, *CPRE Foundation Level Syllabus*, Kapitel Requirements Management/Traceability.
- Bohner, S.; Arnold, R.: *Software Change Impact Analysis*. Wiley/IEEE Computer Society, 1996.
- Pfleeger, S. L.; Atlee, J. M.: *Software Engineering: Theory and Practice*. Prentice Hall, 2006, S. 526.
- Gotel, O.; Finkelstein, A.: *An Analysis of the Requirements Traceability Problem*. RE 1994.
- Ramesh, B.; Jarke, M.: *Toward Reference Models for Requirements Traceability*. IEEE TSE 27(1), 2001.
- Clarkson, P. J.; Simons, C.; Eckert, C.: *Predicting Change Propagation in Complex Design*. Journal of Mechanical Design 126(5), 2004.
- Jarratt, T. et al.: *Engineering Change: An Overview and Perspective on the Literature*. Research in Engineering Design 22(2), 2011.
- Eppinger, S. D.; Browning, T. R.: *Design Structure Matrix Methods and Applications*. MIT Press, 2012.
- Wikipedia, *Change impact analysis* (abgerufen 2026-11-28; stützt die Begriffsabgrenzung traceability/dependency/experiential IA nach Bohner/Arnold).
