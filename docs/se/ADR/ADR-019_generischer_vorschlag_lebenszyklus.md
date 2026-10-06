---
adr_id: ADR-019
title: "Generischer Vorschlags-Lebenszyklus — persistierte Suggestion-Entität als Klammer über vier bestehende Mechanismen"
status: proposed
date: "2026-10-06"
deciders: [orchestrator, ideation, user]
affected_reqs: [REQ-L1-009, REQ-L1-078, REQ-L2-WE-002, REQ-L2-WE-003, REQ-L2-WE-005, REQ-L2-WE-006, REQ-L2-AS-012, REQ-L2-AI-002, REQ-L2-AI-007, REQ-L2-AI-008, REQ-L2-RV-001, REQ-L2-TE-001, REQ-L2-TE-010, REQ-L2-TE-011, REQ-L2-RA-020, REQ-L2-PC-006]
superseded_by: null
---

# ADR-019: Generischer Vorschlags-Lebenszyklus — persistierte Suggestion-Entität als Klammer über vier bestehende Mechanismen

## Entscheidungsvorlage

- **Was ist zu entscheiden:** der Modellrahmen eines generischen Vorschlags-Lebenszyklus (neue `Suggestion`-Entität vs. Wiederverwendung/Erweiterung der Mechanismen M1–M4) und sein MVP-Schnitt; das Endmodell bleibt offen (O1–O11).
- **Empfehlung (gewähltes Modell = Option A):** neue, mandanten-gescopte `Suggestion`-Entität als Kompositions-Schicht über M1–M4; **MVP mit genau einem Produzenten** (`TraceabilitySuggestService.suggest_links`, `trace_link`-Adapter).
- **Konsequenzen bei Annahme:** neue Tabelle + Migration + FORCE-RLS/CI-Gate; Manifest-/REST-/UI-Folgearbeit; additiv, ohne Verhaltensänderung an M1–M4; Umsetzung erst nach User-Freigabe.
- **Konsequenzen bei Ablehnung / Alternative:** der transiente Vorschlag bleibt ohne Warteplatz (#121 offen); die verworfenen Optionen B/C/D (erzwungene State-Machine / N Einzelmigrationen / Read-Model ohne Persistenz) sind in §Alternativen mit Risiko benannt.
- **Geschätzter Aufwand MVP:** nicht abschließend geschätzt (Aufwandszahl offen); Umfang = eine neue Tabelle + Migration/RLS, ein Produzent, ein Accept-Adapter (+ UI-/Manifest-Folgepaket).
- **Offene Produkt-Inputs:** O1–O11, s. §„Offene Punkte (require product input)".

**Status:** proposed (2026-10-06) — Entscheidungsvorlage. **User-Freigabe ausstehend**
(Statuswechsel `proposed → accepted` erst nach positivem `concept-reviewer`-Review
`RVW-2026-10-06-003` (Iteration 3, APPROVED) und User-Entscheid).
**Datum:** 2026-10-06
**Entscheider (vorgeschlagen):** `orchestrator`, `ideation`; **Freigabe:** `user` (offen).
**Betroffene REQs:** REQ-L1-009 (Konfigurierbarer Item-Level-Workflow mit Audit-Trail,
`docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Requirements.md:218`), REQ-L1-078 (State Machine &
Workflow, ebd. `:2135`), REQ-L2-WE-002 (WorkflowDefinition Management), REQ-L2-WE-003
(WorkflowState History/Audit-Trail), REQ-L2-WE-005 (Workflow State Initialization),
REQ-L2-WE-006 (Tenant-Scoped Workflow Data Isolation)
(`docs/se/L1/Gesamtsystem/L2/WorkflowEngineSystem/L2_WorkflowEngineSystem_Requirements.md`),
REQ-L2-AS-012 (Workflow Transition Orchestration, Not Implemented), REQ-L2-AI-002 (Semantic
Trace Healing Agent — Patch-Vorschlag), REQ-L2-AI-007 (AI Derivation Service — Draft/Accept-
Infrastruktur), REQ-L2-AI-008 (AI Derivation Flows)
(`docs/se/L1/Gesamtsystem/L2/AiOrchestrationSystem/L2_AiOrchestrationSystem_Requirements.md:44,116,127`),
REQ-L2-RV-001 (`backend/mcp_server/tools/review.py:2`), REQ-L2-TE-001/-010/-011
(TraceLink-Verwaltung/Audit/Tenant-Isolation), REQ-L2-RA-020 (API State Machine & Guardrails
Enforcer, `Not Implemented`), REQ-L2-PC-006 (Workflow-Konfigurierbarkeits-Regeln pro Preset).

**Bezug (Issues):** Refs #1155 (Aspekt 2 „Vorschlags-Schleife", `docs/plans/2026-10-05-bugfix-hub-integrationen.md:262`),
Refs #1156 („Zuhören & Antizipieren", Vorschlags-Hälfte), Refs #856 (nur Design), Refs #121
(`suggest_links` hat keinen Accept-Schritt, `docs/audit/2026-09/AUDIT_EVIDENCE/issue-inventory.md:239`),
#1089 (AI-Proposal-Authoring + Pending-Review-Queue), #904 („KI-Vorschlag-als-Zustand").
Arbeitseinheit **AP-B5.4** (`docs/plans/2026-10-05-bugfix-hub-integrationen.md`).

**Bezug zum Code:** `backend/workflow/definition_store.py:605` (`PROPOSED_STATE`), `:628`
(`SCHEMAS_WITHOUT_PROPOSED = {minimal, interview_default}`), `:644-711` (`inject_proposed_state`);
`backend/workflow/services.py:707-745` (`initial_state_for`), `:783` (`is_approval_gate`);
`backend/application/ai_proposal_service.py:1-55` (Authoring-Kontext, **bewusst keine**
`draft → proposed`-Kante); `backend/application/review_queue_service.py:1-101,200-264`
(transportübergreifende Pending-Review-Queue, Union aus Approval-Gate-Items und `proposed`-Items;
`:1-101` = Docstring/DTO, die Query-/Union-Logik liegt bei `:200-264`);
`backend/application/trace_link_service.py:489` (`create_trace_link`), `:601-617`
(M2-Proposal-Stempel), `:637-728` (`confirm_proposed_link`/`discard_proposed_link`);
`backend/rest_api/views.py:3359-3399` (`trace-links/{id}/confirm|discard`);
`backend/persistence/models.py:1965-1976` (`TraceLink.proposed_by`/`proposed_at`), `:1957-1959`
(TraceLinks haben **kein** `WorkflowItemState`); `backend/context_graph/models.py:56-64`
(`ContextEdge.origin="llm-suggested"`); `backend/application/interview_service.py:2088-2091,
2140-2148` (`grounding_snapshot["pending_proposal"]`), `:914,1306-1374` (`formalize(confirmed_proposal=…)`);
`backend/application/traceability_suggest_service.py:237-338`; `backend/application/ai_derivation_service.py:616-728,605-614`;
`backend/application/architecture_decompose_service.py:21-24`; `backend/application/audit_service.py:992-1014`.

**Vermerk zur Ablage:** `docs/se/ADR/` ist die *gelebte* Konvention (19 ADRs, ADR-001…018 +
ADR-DS-02). Der SE-Kaskaden-Schalter ist widersprüchlich: `.agent-meta/.meta-config/project.yaml`
setzt `overrides.se-cascade.enabled=false`, die Root-`.meta-config/project.yaml` hat keinen
entsprechenden Schlüssel. Dieses ADR folgt der gelebten Konvention `docs/se/ADR/` und
dokumentiert den Widerspruch als **Annahme** (Kontext Punkt 6).

**Überarbeitung (2026-10-06):** Iteration 2 — Review `RVW-2026-10-06-001`
(`docs/se/reports/concept-review-ADR-019_2026-10-06.md`, Verdict CHANGES_REQUESTED)
eingearbeitet: **001-01** (MVP-Pfad = Produzieren via `TraceLinkService.create_trace_link` als
M2-Proposal, Accept via `confirm_proposed_link`; Scope-Änderung ausgewiesen), **001-02**
(Threat-Model Payload-Injection/Provenienz-Trust), **001-03**
(Agent-Guard greift je Adapter), **001-04** (M4 als neuer, kleiner Adapter deklariert),
**001-05** (Idempotenz-Zusage geschärft), **001-06** (Pfad-/Zeilenpräzision). Status bleibt
`proposed`, User-Freigabe weiterhin offen. **001-07 (info):** Die Erstellung durch `ideation`
statt `se-architect` ist — wie bei ADR-016 — eine user-getragene Abweichung bei deaktivierter
SE-Kaskade (vgl. Vermerk oben). **001-08 (info):** keine Änderung nötig.

**Überarbeitung (2026-10-06, Iteration 3):** Review `RVW-2026-10-06-002`
(`docs/se/reports/concept-review-ADR-019_iter2_2026-10-06.md`) eingearbeitet:
**001-09 (major/blocking)** — der MVP-Produktionspfad wird **explizit auf Agent-/API-Key-Kontexte
begrenzt**; der Human-Bearer-REST-Trigger ist out of MVP scope und **fail-closed** (kein stiller
Human-in-the-Loop-Bypass), s. Decision 3/4 + Zusage 7(b)/(f); **001-10 (minor)** — O7 um die
Kanten-Dedup `uq_tracelink_edge` erweitert, mit benanntem MVP-Kontrollschritt im `trace_link`-
Adapter; **001-11 (info)** — Atomarität „Proposal-TraceLink + Suggestion-Quittung" als neuer
offener Punkt **O11** und als Konsequenz benannt. Status bleibt `proposed`, User-Freigabe offen.

---

## Kontext

**1. Es gibt keinen generischen Vorschlag — sondern vier inkompatible, gelebte Mechanismen.**

| # | Mechanismus | Ort | Accept-Semantik |
|---|---|---|---|
| M1 | Workflow-Zustand `proposed` | `workflow/definition_store.py:605,644-711`; in jedes Default-Graph injiziert **außer** `minimal` und `interview_default` (`:628`) | `proposed → states[0]` (`confirm`, ohne `change_reason`), `proposed → reject_state` (`discard`, `change_reason` Pflicht), Rollen `editor/approver/admin` (`:609`) |
| M2 | `TraceLink.proposed_by`/`proposed_at` | `persistence/models.py:1965-1976`; TraceLinks haben **kein** `WorkflowItemState` (`:1957-1959`) | `trace-links/{id}/confirm|discard` (`rest_api/views.py:3359-3399`; `trace_link_service.py:637-728`) — Feld-Clear, keine State-Machine |
| M3 | `InterviewSession.grounding_snapshot["pending_proposal"]` | `interview_service.py:2088-2091,2140-2148` | `formalize(confirmed_proposal=…)` (`:914,1306-1374`) |
| M4 | `ContextEdge.origin="llm-suggested"` | `context_graph/models.py:56-64` | Origin-Feld, kein eigener Accept-Endpoint |

Diese vier Mechanismen sind nicht nur unterschiedlich, sie sind **strukturell unvereinbar**:
M1 hat eine State-Machine, M2/M4 haben keine, M3 lebt in einem JSON-Snapshot eines
Prozess-Objekts. Ein „Vorschlag" ist heute also kein Domänenbegriff, sondern ein
zufälliges Nebenprodukt der Entität, auf die er zielt.

**2. Die Produzenten sind transient — sie persistieren nichts.** `TraceabilitySuggestService.suggest_links`
(`traceability_suggest_service.py:237-338`) gibt DTOs zurück und trägt dabei bereits eine reiche
Provenienz (`finding_index`, `rule_id`, echte Source-/Target-UUIDs, `score`, `rationale`);
`AiDerivationService.suggest_architecture_for_requirement` (`ai_derivation_service.py:616-728`)
und `derive_requirements_from_need` (`:605-614`) liefern Entwürfe; `ArchitectureDecomposeService.generate_draft`
ist **per explizitem Design** transient (`architecture_decompose_service.py:21-24`);
`AuditService.propose_remediation` (`audit_service.py:992-1014`) ebenso. Ergebnis: Wird der
Vorschlag nicht sofort angenommen, ist er **verloren** — es gibt keinen Ort, an dem er auf
eine spätere menschliche Entscheidung wartet. Genau dieses Loch beschreibt #121
(`suggest_links` hat keinen Accept-Schritt).

**3. Es gibt bewusst keine `draft → proposed`-Kante.** `ai_proposal_service.py:45-55` begründet
das: Ein Artefakt muss „als Vorschlag geboren" werden; es kann nicht nachträglich befördert
werden. Deshalb seedet `initial_state_for` Agent-Artefakte direkt nach `proposed`
(`workflow/services.py:743`), und der Agent-Guard verbietet dem Agenten, seinen eigenen
Vorschlag zu bestätigen (`transition_validator.py:288-306`). Ein generischer Vorschlag muss
diese Regel **respektieren**, nicht umgehen.

**4. Accept bedeutet je Vorschlagsart etwas anderes.** (a) Artefakt-erzeugende Vorschläge
bilden auf M1 (`proposed → initial_state`) ab. (b) Link-/Feld-/Annotation-Vorschläge haben
keinen `WorkflowItemState` und brauchen einen eigenen Accept-Pfad (M2/M4). Eine Vereinheitlichung,
die „alles zu einem Zustandsübergang" macht, würde (b) zwingen, eine State-Machine zu erfinden,
die es strukturell nicht gibt.

**5. Es gibt bereits eine transportübergreifende Sicht — die darf nicht dupliziert werden.**
`ReviewQueueService` (`review_queue_service.py:1-101,200-264`) vereinigt in **einer** Query
Approval-Gate-Items und `proposed`-Items, und MCP `review.list_pending` sowie die REST-Endpunkte
`/api/v1/reviews/pending/` projizieren dieselbe Liste (Issue #1089). Der Authoring-Kontext
`resolve_proposal_authoring`/`verify_proposal_state`/`require_proposal_support`
(`ai_proposal_service.py`) regelt bereits, wann ein Artefakt „als Vorschlag geboren" wird und
wann **ehrlich scheitert** (Preset ohne `proposed`). Ein neuer generischer Baustein muss auf
diesen Mechanismen **aufsetzen**, nicht daneben eine zweite Vorschlags-Wahrheit bauen.

**6. Ablageort-Annahme (SE-Kaskaden-Schalter).** Wie im Vermerk oben: `docs/se/ADR/` wird als
gelebte Konvention genutzt (19 Dateien), obwohl der SE-Kaskaden-Schalter in
`.agent-meta/.meta-config/project.yaml` `enabled=false` zeigt. Dieses ADR ändert **keine**
Kaskaden-Datei und **keine** REQ-Datei; die REQ-Zuordnung oben ist eine belegte Näherung
(Datei + Zeile), keine bereits getrackte Verknüpfung (vgl. ADR-016 §4).

**Threat-Model (4 Fragen, Vorschlags-Datenfluss):**

1. *Was gebaut?* Persistente Vorschlags-Datensätze (Tenant-Daten aus KI-Produzenten), Accept/
   Reject über REST + MCP; Auth = JWT/API-Key + RBAC + RLS; Nutzer = authentifizierte
   Tenant-User und Agenten (nur schreibend).
2. *Was schiefgeht?*
   (a) Ein Agent bestätigt über die neue Entität seinen eigenen Vorschlag (Umgehung des
   Agent-Guards aus Punkt 3).
   (b) Cross-Tenant-Leak, wenn die neue Tabelle RLS-pflichtig ist, aber ohne FORCE-Policy
   migriert wird — oder wenn Accept fremde Ziel-IDs akzeptiert.
   (c) Ein Acceptance-Adapter umgeht die bestehende State-Machine/Workflow-Policy und erzeugt
   ungültige Zustände.
   (d) Unbegrenzte Retention lässt abgelehnte Vorschläge (inkl. `payload`) zum
   Datenmüll/Informationsleck werden.
   (e) **Payload-Injection/-Tampering:** der persistierte `payload` ist LLM-erzeugt und damit
   **untrusted**; ein manipulierter Body (fremde UUIDs, unzulässiger `link_type`, injizierte
   Felder) könnte beim Accept ungeprüft materialisiert werden.
   (f) **Provenienz-Fälschung:** wer `producer`/`proposed_by`/`decided_by` caller-seitig setzen
   kann, schreibt einen Vorschlag fälschlich einem anderen Agenten/API-Key zu.
3. *Gegenmaßnahme?*
   - Agent-Accept fail-closed **je Adapter** verbieten (M1 erbt Rule 0; `trace_link` blockt
     selbst, vgl. 001-03).
   - `Suggestion` als `TenantScopedModel` (erbt `AuditableModel`) mit FORCE RLS und
     CI-Coverage-Gate `test_rls_coverage.py`; Accept läuft über `_set_tenant_context` + RLS,
     Ziel-IDs müssen im aktiven Tenant/Workspace liegen (Cross-Tenant → `ValidationError`).
   - Accept delegiert **immer** an den bestehenden Domain-Pfad und damit durch
     Policy/Workflow/RBAC/Audit — **kein** Bypass, **keine** neue State-Logik.
   - **`payload` ist untrusted:** Accept validiert ausschließlich über den delegierten Pfad
     (z. B. `trace_link_service._check_link_pair` `:537-544`, Link-Catalog,
     Cross-Tenant-/Cycle-Prüfung); der Payload liefert nur Kandidaten-IDs, nie Entscheidungen.
     Kein `eval`, kein Blind-Merge.
   - **Provenienz ist server-gesetzt:** `producer`, `proposed_by`, `proposed_at`, `decided_by`,
     `decided_at` stammen aus dem authentifizierten Principal bzw. der `ApiKey`-Zeile — **nie**
     aus dem Request-Body; ein Producer kann sich nicht selbst benennen.
   - Explizite Retention/Garbage-Collection (offene Entscheidung O9).
4. *Konsequenz?* Ohne Gegenmaßnahmen: Umgehung des Human-in-the-Loop-Prinzips, Tenant-Leak,
   Zustandsinkonsistenz, injizierte Payloads. Mit Gegenmaßnahmen: ein neuer, auditierter
   Datenbestand mehr — aber genau der Bestand, den die Vorschlags-Schleife braucht.

---

## Alternativen

### Option A: Neue generische, persistierte `Suggestion`-Entität — komponiert mit M1–M4 — GEWÄHLT (Zielrichtung, MVP geschnitten)

**Beschreibung:** Eine neue, mandanten-gescopte Entität `Suggestion` (Layer 0 `persistence/`,
`TenantScopedModel` + `AuditableModel`) mit Lebenszyklus `open | accepted | rejected |
superseded`, Produzent/Provenienz (`producer`, `proposed_by`, `proposed_at`), optionaler
Ziel-Referenz (`target_item_type`/`target_item_id`, nullable) und `payload` (JSON). Sie
**ersetzt keinen** der Mechanismen M1–M4, sondern ist die **durable Quittung + Inbox +
Provenienz** über ihnen. Accept läuft über eine Registry **per-kind Accept-Adapter**
(`kind` ∈ `artifact_create | trace_link | interview_grounding | context_edge`), die den
jeweils bestehenden Pfad aufruft — außer `context_edge`, wo der Origin explizit gesetzt wird
(kein bestehender Accept-Pfad, s. Entscheidung 3) — und danach die Suggestion quittiert.

**Abwägung:** Einzige Option, die (a) die vier Mechanismen nicht antastet, (b) dem transienten
Produzenten (#121) einen echten Warteplatz gibt, (c) eine einheitliche Provenienz-/Inbox-Fläche
für REST/MCP/UI erlaubt, ohne die bestehende `ReviewQueueService`-Sicht zu duplizieren, und
(d) ehrlich bleibt, wo die Mechanismen differieren (der Adapter benennt die Differenz, statt
sie zu verstecken). Preis: eine neue Tabelle (Migration + RLS + Audit) und eine neue Fläche
(MCP-Manifest, REST-Routen, UI). Ein sauberes Gesamtmodell ist in einem Durchgang **nicht**
entscheidbar; deshalb wird Option A als **Zielrichtung** gewählt und auf einen **MVP mit einem
Produzenten** geschnitten (s. Entscheidung).

**Risiko:** MITTEL — neue Tabelle + neue Fläche, aber additiv und ohne Verhaltensänderung an M1–M4.

### Option B: Nur den Workflow-`proposed`-Zustand wiederverwenden — VERWORFEN

**Beschreibung:** Kein neues Entity; M2/M3/M4 werden auf den M1-Zustand abgebildet, indem jede
vorschlagsfähige Entität ein `WorkflowItemState` bekommt.

**Abwägung:** Vermeidet eine neue Tabelle und nutzt die bestehende Review-Queue. Aber:
TraceLinks haben **strukturell** kein `WorkflowItemState` (`persistence/models.py:1957-1959`);
sie eines zu geben, hieße eine State-Machine für etwas zu erfinden, das keine hat, und M2
(`proposed_by`/`proposed_at` als Feld) zu verdoppeln. Zusätzlich würde M3 (Interview) in
Presets gezwungen, die `proposed` **bewusst verbieten** (`SCHEMAS_WITHOUT_PROPOSED`,
`definition_store.py:628`) — genau der Fehler, der den wichtigsten MCP-Pfad einfror (Kommentar
`:616-627`). Die transiente Produzenten-Provenienz (#121) hat hier weiterhin keinen Platz.

**Risiko:** HOCH — erzwingt Workflow-Semantik auf Entitäten ohne Workflow und kollidiert mit
einer expliziten, sicherheitsbegründeten Preset-Ausnahme.

### Option C: Bestehende per-kind Mechanismen erweitern (Feld-/Mixin-Ansatz, kein neues Entity) — VERWORFEN

**Beschreibung:** Kein generischer Datensatz; stattdessen `proposed_by`/`proposed_at` (wie M2)
auf weitere Entitäten ausrollen plus ein gemeinsamer Mixin/Serializer und ein einheitlicher
„pending"-Endpoint.

**Abwägung:** Minimaler Fußabdruck, keine neue Kerntabelle. Aber es entstehen **N**
entitätsspezifische Migrationen ohne gemeinsamen Vertrag; die semantische Klammer „das ist ein
Vorschlag" bleibt über N Tabellen verstreut, und für die **transienten** Produzenten (Punkt 2)
gibt es weiterhin kein Zuhause — die DTO ist nach dem Request weg. Der eigentliche Bedarf
(#121: Accept-Schritt für `suggest_links`) wird nicht gedeckt, weil der Vorschlag ohne
persistierte Zeile gar nicht existiert, bis er akzeptiert wird.

**Risiko:** MITTEL — breite, aber flache Änderung; löst das Kernproblem (Transienz) nicht.

### Option D: Reine Read-Model-Inbox ohne Persistenz — VERWORFEN (Außenseiter)

**Beschreibung:** `ReviewQueueService` wird um Sichten auf M2/M3/M4 und die transienten
Produzenten erweitert; nichts Neues wird gespeichert.

**Abwägung:** Keine Migration, keine neue Tabelle, keine Manifest-Änderung — beste
Risiko-/Aufwandsbilanz. Aber die transienten Produzenten werden nirgends persistiert; eine
Read-Model-Inbox kann nur zusammenfassen, was existiert. Ein `suggest_links`-Ergebnis ist
ohne Persistenz beim nächsten Request nicht mehr vorhanden — die Inbox zeigte also ins Leere.
Zudem widerspricht es dem DoD von #1155/#1156 („Vorschlag als `proposed`, Capture → Review →
Accept"), das eine **wartende** Entität verlangt.

**Risiko:** NIEDRIG im Aufwand, HOCH im Zielerreichungsgrad — löst das Problem nicht.

---

## Entscheidung

**Empfehlung: Option A als Zielrichtung, geschnitten auf einen MVP mit genau einem Produzenten
— plus explizit deferred Sub-Entscheidungen.** Eine saubere Gesamtlösung ist in einem Durchgang
nicht entscheidbar; dieses ADR entscheidet daher **nicht** das Endmodell, sondern den
risikoärmsten, testbaren ersten Schritt und benennt die offenen Punkte.

1. **Neue Entität `Suggestion` (Layer 0, mandanten-scoped).** Eigene Tabelle in
   `backend/persistence/models.py`, auf `TenantScopedModel` (`:446-474`) aufbauend — dieses
   erbt bereits von `AuditableModel` (`:379-443`), beide Basen sind damit abgedeckt;
   **verpflichtende** `FORCE ROW LEVEL SECURITY` + Policy nach dem
   Muster `persistence/migrations/0003_rls_policies.py:61-72`; das CI-Gate
   `persistence/tests/test_rls_coverage.py` muss die neue Tabelle erfassen (sonst rot). Felder
   (Vorschlag, nicht abschließend): `kind`, `status` (`open|accepted|rejected|superseded`),
   `producer` (Service/Agent-Label), `proposed_by`, `proposed_at`, `decided_by`, `decided_at`,
   `target_item_type`, `target_item_id` (nullable), `payload` (JSON), `workspace`-Scope.
   `Suggestion` ist **kein** Ersatz für die Generic-Artifact-Tabelle; ob sie langfristig
   selbst zu einem Artefakt wird, ist offene Entscheidung O8.

2. **Komposition, keine Ablösung.** Die Zustands-Hoheit bleibt bei M1–M4. `Suggestion` ist
   **durable Quittung + Inbox + Provenienz**. Der Accept-Pfad **reimplementiert keine**
   State-Machine- oder Link-Logik; er ruft den bestehenden Mechanismus auf und quittiert danach
   die Suggestion als `accepted` (bzw. `rejected`).

3. **Per-kind Accept-Adapter (Registry).** `kind` → Adapter:
   - `artifact_create` → bestehender M1-Pfad (`confirm`, `proposed → states[0]`); bei
     Workspaces **ohne** `proposed` (`minimal`/`interview_default`) trägt die Suggestion-Zeile
     selbst das Review-Gate, und Accept ruft den Create-Pfad mit **User-Kontext** auf
     (Regel aus `ai_proposal_service.py`; **kein** Injizieren von `proposed`). Damit erhält
     `minimal` eine Vorschlags-Schleife, **ohne** das Preset zu verbiegen. Ob das gewünscht
     ist, ist offene Entscheidung O3.
   - `trace_link` → **Produzieren = Create (M2-Proposal), Accept = M2-Confirm.**
     Der Adapter **legt den Vorschlag beim Produzieren als echten TraceLink an**: er ruft
     `TraceLinkService.create_trace_link(source_id, target_id, link_type, ctx, rationale)`
     (`backend/application/trace_link_service.py:489`) unter dem **Produzenten-Kontext**
     (Agent + `api_key_id`) auf. Die M2-Stempel-Logik `:601-617` setzt dabei `proposed_by`/
     `proposed_at`; damit **existiert** der Vorschlag als TraceLink, und M2 (`confirm_proposed_link`,
     `:637-676`) ist nicht mehr „confirm eines nicht existierenden Links". Dieser Create-Pfad
     trägt die vollständige Domain-Validierung (`_check_link_pair` `:537-544`,
     Allocation-Invariante, Cross-Tenant-/Cycle-Prüfung in
     `traceability.services.create_trace_link`) sowie Audit und Domain-Event. `link_type` wird
     aus `payload.rule_id` abgeleitet (TRACE-P1/P1b → `derives-from`, TRACE-P2 →
     `allocated-to`); das `suggest_links`-DTO trägt selbst **kein** `link_type`. Der
     **Top-ranked** Kandidat wird der Proposal-Link; die vollständige Rangliste bleibt im
     `Suggestion.payload` (Wahl eines Alternativkandidaten ist O10/UX). **Accept** eines Menschen
     ruft dann `TraceLinkService.confirm_proposed_link(link_id, human_ctx)` (`:637-676`) auf,
     **Reject** `discard_proposed_link` (`:678-728`); der Agent-Guard `AgentSelfConfirmError`
     (`:658-661`) liegt damit **auf dem echten Accept-Pfad**. Die `Suggestion`-Zeile bleibt die
     generische durable Quittung/Inbox (`target_item_id` → Proposal-Link-id) und trägt zusätzlich
     die Provenienz (`finding_index`, `rule_id`, `score`, `rationale`).
     **Scope-Änderung (explizit):** Der MVP-Produzent persistiert jetzt einen Proposal-TraceLink,
     statt nur eine `Suggestion`-Zeile — die frühere „confirm bzw. batch-create"-Unschärfe
     entfällt, weil der zu bestätigende Link real existiert (`create_trace_link` `:601-617` ist
     der einzige Stempel-Ursprung).
     **Produzenten-Kontext (001-09, verbindlich).** Der Stempel `:601-617` ist an die
     Vorbedingung `ctx.actor_type == "agent"` **und** `ctx.api_key_id is not None` gebunden
     (`trace_link_service.py:607`). Der MVP-Produktionspfad ist deshalb **explizit auf
     Agent-/API-Key-Kontexte begrenzt** (MCP `traceability.suggest_links`,
     `mcp_server/tools/cross_cutting.py:941-943`). Der Human-Bearer-REST-Trigger
     (`rest_api/traceability_suggest_views.py:80-82`; `actor_type="user"`, kein `api_key_id`)
     ist **out of MVP scope**. **Observables Verhalten:** Wird der Produktions-Adapter mit einem
     Nicht-Produzenten-Kontext aufgerufen, **schlägt er fail-closed fehl** — benannter
     `ProducerContextRequiredError` (→ HTTP 409 Konflikt) — statt einen ungestempelten,
     sofort bestätigten Link anzulegen; es entsteht **kein** Proposal und **kein** stiller
     Human-in-the-Loop-Bypass (weder „reject ohne Fehler" noch stiller No-op). Grundlage ist
     das belegte Fehlermuster #1089 (`ai_proposal_service.py:13-19`: human-getriggerte
     Ableitung mit `actor_type="user"`). Die Kontext-Synthese für den Human-Trigger analog
     `resolve_proposal_authoring` (Option (ii) des Reviews `RVW-2026-10-06-002`) ist **bewusst
     vertagt** und als Follow-up benannt (s. Konsequenzen).
     **Kanten-Dedup (001-10).** Vor dem Anlegen prüft der Produzent auf einen bereits
     existierenden Proposal-Link derselben Kante `(source, target, link_type)`
     (`uq_tracelink_edge`, `persistence/models.py:2037`; Kollisions-Mapping
     `trace_link_service.py:573-578`). Existiert er, wird die neue `Suggestion` an diesen
     bestehenden Proposal-Link gehängt statt ein Duplikat anzulegen — ein erneuter
     Produzenten-Lauf scheitert damit **nicht hart** an `uq_tracelink_edge`, sondern
     dedupliziert auf Kantenebene. Das erweitert O7 (bisher nur Suggestion-Dedup).
   - `interview_grounding` → M3 (`formalize(confirmed_proposal=…)`).
   - `context_edge` → M4 ist **kein** bestehender Accept-Mechanismus, sondern nur ein
     Provenienz-Träger (`ContextEdge.origin`, `context_graph/models.py:56-64`) **ohne** eigenen
     Accept-Endpoint. Der Adapter setzt den Origin explizit (`llm-suggested` → bestätigt);
     das ist **neue**, kleine Logik und wird hier als solche deklariert — er erbt **keinen**
     bestehenden Accept-Pfad.
   **Der Agent-Guard greift je Adapter:** M1 erbt Rule 0
   (`transition_validator.py:288-306`), die nur für Workflow-State-Transitions gilt. Der
   `trace_link`-Accept nutzt `confirm_proposed_link`/`discard_proposed_link`, die einen Agenten
   bereits mit `AgentSelfConfirmError` blocken (`trace_link_service.py:658-661`); der Adapter
   assertion die Sperre zusätzlich defensiv (kein „Erben" von Rule 0, da `create_trace_link`
   dem Agenten das **Erzeugen** des Proposals bewusst erlaubt). `artifact_create` muss die
   Agent-Sperre ebenfalls explizit prüfen.

4. **MVP-Schnitt: genau ein Produzent.** Zuerst `TraceabilitySuggestService.suggest_links`
   (`traceability_suggest_service.py:237-338`), weil (a) #121 exakt dieses fehlende
   Accept-Stück benennt, (b) das DTO die reichste Provenienz trägt (`finding_index`, `rule_id`,
   echte UUIDs), und (c) der normale Create-Pfad `TraceLinkService.create_trace_link` den
   Proposal-Link bildet (`:601-617`), sodass der bestehende M2-Accept (`confirm_proposed_link`)
   real greift. `AiDerivationService`,
   `ArchitectureDecomposeService` und `AuditService.propose_remediation` folgen in späteren
   Iterationen (offene Entscheidung O1).
   **Produzenten-Kontext (001-09, verbindlich):** Produziert wird im MVP ausschließlich unter
   **Agent-/API-Key-Kontext** (MCP `traceability.suggest_links`); der Human-Bearer-REST-Trigger
   ist **out of scope** und wird vom Produktions-Adapter **fail-closed** abgewiesen
   (`ProducerContextRequiredError` → 409), statt still einen ungestempelten Link zu erzeugen
   (s. Decision 3).

5. **Wiederverwendung der bestehenden Flächen.** `ReviewQueueService`
   (`review_queue_service.py`) bleibt die transportübergreifende Lese-Sicht; sie wird additiv
   um `open`-Suggestions erweitert, **nicht** kopiert. `ai_proposal_service`
   (`resolve_proposal_authoring`/`verify_proposal_state`/`require_proposal_support`) bleibt der
   Authoring-Seam. REST registriert unter `rest_api/urls.py:213-261` (Layer-Regel ADR-01:
   dünner Adapter → `application/`), RBAC über `RbacPermission`
   (`rest_api/auth_enforcer.py:60`), Audit via `audit.models.AuditEntry` bzw. `write_mcp_audit`.

6. **Kein Doppel-Surface ohne Manifest-Pflege.** Falls ein neues MCP-Tool-Gruppen-Präfix
   `suggestion` eingeführt wird, ist `docs/agent-templates/tool-manifest.json` (heute 223
   Tools/35 Präfixe) neu zu erzeugen; das Drift-Gate
   `mcp_server/tests/test_tool_manifest_drift.py` erzwingt das. Alternative: die MVP-Tools
   unter der bestehenden `review`-Gruppe (`REQ-L2-RV-001`) exponieren — offene Entscheidung O5.

7. **Testbare Kern-Zusagen (MVP).** (a) **Pro erfolgreicher** Produzenten-Ausführung
   hinterlässt diese genau eine `open`-Suggestion mit tenant-korrektem Scope und vollständiger
   Provenienz; Dedup über **mehrere** Läufe ist bewusst vertagt — O7 schließt seit **001-10**
   ausdrücklich die **Kanten-Dedup** `uq_tracelink_edge` ein (Lookup vor `create`, kein harter
   Fehler). (b) Accept ruft den bestehenden Mechanismus auf und setzt `status=accepted` +
   `decided_by`/`decided_at`; kein State-Übergang wird neu implementiert. Produktion **und**
   Accept folgen dem in Decision 3/4 festgelegten Kontextmodell: Produktion nur
   Agent-/API-Key (001-09), Accept durch den Menschen. (c) Ein Agent-Accept auf den eigenen
   Vorschlag schlägt fehl (403/Validation), nicht still. (d) `test_rls_coverage.py` und
   `test_tool_manifest_drift.py` sind grün. (e) Reject setzt `status=rejected` und zerstört
   kein Ziel-Artefakt. (f) Der Produktions-Adapter ist **fail-closed**: ein Nicht-Agent-/
   Nicht-API-Key-Kontext wird mit `ProducerContextRequiredError` (→ 409) abgewiesen — kein
   ungestempelter „Proposal"-Link, kein stiller Human-in-the-Loop-Bypass (001-09).

### Was diese Entscheidung *nicht* ist

Sie ist **keine** Aussage, dass M1–M4 abgeschafft werden. Sie ist die Aussage, dass dem
transienten, quellenlosen Vorschlag ein dauerhafter, mandanten-sicherer Platz geschaffen wird,
**ohne** die vier gewachsenen Accept-Pfade umzubauen — und dass die verbleibenden
Modellentscheidungen (O1–O11) einem bewussten Produkt-Entscheid vorbehalten bleiben.

---

## Konsequenzen

**Positiv:**

- Der transiente Vorschlag (#121, `suggest_links`) bekommt einen echten Warteplatz; „KI
  schlägt vor → Mensch bestätigt" wird über alle vier Oberflächen nachvollziehbar.
- Einheitliche Provenienz/Inbox, ohne die bestehende `ReviewQueueService`-Sicht zu duplizieren
  (#1089 bleibt die eine Queue).
- `minimal`/`interview_default` erhalten eine Vorschlags-Schleife **ohne** Injektion des
  verbotenen `proposed`-Zustands (`definition_store.py:628`) — die Preset-Ausnahme bleibt intakt.
- Der Agent-Guard bleibt fail-closed; kein Still-Accept.
- Additiv: keine Verhaltensänderung an M1–M4 im MVP.

**Negativ:**

- **Neue Tabelle + Migration.** Blast-Radius an der Multi-Tenancy-Grenze; ohne FORCE-RLS-Policy
  und CI-Coverage entsteht ein Cross-Tenant-Risiko (absichtlich als Threat-Model-Punkt 2
  benannt).
- **Manifest-Drift.** Ein neues MCP-Präfix erfordert Manifest-Regeneration; sonst schlägt
  `test_tool_manifest_drift.py` fehl. Das ist gewollt, aber ein zusätzlicher Release-Schritt.
- **UI-Folgearbeit.** Ohne Review-/Inbox-UI ist der persistierte Vorschlag für den Menschen
  unsichtbar — die Entität allein erfüllt das DoD nicht. Expliziter UI-Follow-up (s. Plan).
- **Zwei Vorschlags-Wahrheiten bleiben vorerst.** M1–M4 bleiben maßgeblich; `Suggestion` ist
  eine Klammer darüber. Eine spätere Konsolidierung (z. B. `TraceLink.proposed_by` in die
  generische Entität überführen) ist eine **neue** Entscheidung (O4), nicht still erlaubt.
- **MVP-Produzent schreibt jetzt (Scope-Änderung).** Der `trace_link`-Adapter legt beim
  Produzieren einen Proposal-TraceLink an (M2), statt nur eine `Suggestion`-Zeile — die
  TraceLink-Tabelle füllt sich mit unbestätigten Vorschlägen. Gewollt (M2-Semantik), aber
  zusätzliches Volumen und Redundanz `Suggestion` ↔ `TraceLink.proposed_by` (O4).
- **REST-Human-Trigger im MVP gesperrt (001-09).** Der Produktionspfad ist Agent-/
  API-Key-gebunden; ein human-getriggerter REST-Lauf, der einen Vorschlag erzeugen will, wird
  **fail-closed** abgewiesen (`ProducerContextRequiredError` → 409), statt still einen
  ungestempelten, sofort bestätigten Link anzulegen. Die Kontext-Synthese für den Human-Trigger
  (Option (ii) des Reviews `RVW-2026-10-06-002`, analog `resolve_proposal_authoring`) ist ein
  benannter Follow-up. Bis dahin ist die Vorschlags-Produktion auf MCP/API-Key beschränkt; die
  bestehende advisory REST-`suggest-links`-Fläche bleibt höchstens lesend und erzeugt **kein**
  Proposal.
- **Atomarität Proposal-Link ↔ Suggestion-Quittung (001-11).** `create_trace_link` ist atomar,
  das Anlegen der `Suggestion`-Zeile ist ein **separater** Write. Bei Teilfehler entstünde ein
  verwaister Proposal-TraceLink, der in der `ReviewQueueService`-Inbox unsichtbar ist (die
  Union liest nur Approval-Gate- und `proposed`-Workflow-Items, `review_queue_service.py:200-264`).
  Als offener Punkt **O11** benannt (eine Transaktion und/oder verwaiste Proposals in die Inbox
  aufnehmen).
- **`open_adrs`-Feld existiert repo-weit nicht** (vgl. ADR-016 §4, `AUD-2026-09-333`): die
  REQ↔ADR-Verknüpfung oben bleibt eine belegte Näherung.
- **Freigabe ausstehend:** Status `proposed`; Umsetzung erst nach `proposed → accepted`
  durch den User (Re-Review `RVW-2026-10-06-003`, Iteration 3, liegt mit Verdict APPROVED vor).

---

## Review-Round-Trail

Review-Lifecycle über drei Iterationen; jede Iteration ist ein eigener Zyklus
(s. `docs/se/reports/`). Status aller Findings zum Stand `RVW-2026-10-06-003`.

| Review | Iter. | Verdict | Findings | Handling |
|---|---|---|---|---|
| `RVW-2026-10-06-001` | 1 | CHANGES_REQUESTED | 001-01, 001-02 (major); 001-03…001-06 (minor); 001-07, 001-08 (info) | **001-01** (major/blocking, Accept-Pfad) → in Iteration 2 gelöst (MVP-Produzent = `create_trace_link`, Accept = `confirm_proposed_link`); **001-02** (major, Threat-Model Payload-/Provenienz-Trust) → gelöst; **001-03** (Guard je Adapter), **001-04** (M4 als neuer, kleiner Adapter), **001-05** (Idempotenz-Zusage geschärft → O7), **001-06** (Pfad-/Zeilenpräzision) → gelöst; **001-07** (Autor-Rolle, info), **001-08** (info, keine Änderung) → adressiert. |
| `RVW-2026-10-06-002` | 2 | CHANGES_REQUESTED | 001-09 (major/blocking); 001-10 (minor); 001-11 (info) | **001-09** (Human-Bypass am REST-Trigger) → in Iteration 3 gelöst (Scope auf Agent-/API-Key, fail-closed `ProducerContextRequiredError`); **001-10** (Kanten-Dedup `uq_tracelink_edge`) → gelöst (O7 erweitert); **001-11** (Atomarität Proposal-Link ↔ Suggestion-Quittung) → adressiert als O11. |
| `RVW-2026-10-06-003` | 3 | APPROVED | 003-01 (info) | **003-01** (HTTP-Status-Mapping `409` vs. `403`) → als Umsetzungshinweis offen, nicht blockierend; bei der Umsetzung in der REST-/MCP-Fehler-Taxonomie zu verankern. |

**Offen (nicht blockierend):** der einzige nicht geschlossene Befund ist `003-01` (info).
Alle Findings `001-01`…`001-11` sind geschlossen bzw. adressiert; keine critical/major offen.

---

## Offene Punkte (require product input)

1. **O1 — MVP-Produzenten-Scope:** nur `TraceabilitySuggestService` (Empfehlung) oder mehrere
   Produzenten im ersten Schnitt?
2. **O2 — Langfrist-Rolle von `Suggestion`:** dauerhaft Kompositions-/Quittungsschicht, oder
   schrittweise Zustands-Hoheit (M1–M4 ablösend)?
3. **O3 — `minimal`/`interview_default`-Semantik:** Vorschlags-Schleife über die
   Suggestion-Zeile erlauben (Empfehlung) oder Vorschläge hart verweigern
   (`require_proposal_support`-Verhalten)?
4. **O4 — `TraceLink.proposed_by`/`proposed_at`:** nach `Suggestion` migrieren und die Felder
   deprecaten, oder als M2-Feld belassen (separate Migration/Entscheidung)?
5. **O5 — MCP-Surface:** neues Präfix `suggestion` (Manifest-Regeneration, 223 → N Tools) oder
   Fold in die bestehende `review`-Gruppe?
6. **O6 — UI-Inbox:** eigene „Vorschläge"-Seite oder Eintrag in die bestehende Review-/
   Pending-Ansicht?
7. **O7 — Idempotenz/Dedup (Suggestion *und* Kante):** erneuter Produzenten-Lauf erzeugt neue
   Zeile, ersetzt sie oder markiert die alte als `superseded`? **Explizit eingeschlossen
   (001-10): Kanten-Dedup** — ein erneuter Lauf kollidiert sonst deterministisch mit
   `uq_tracelink_edge` (`persistence/models.py:2037`; Mapping `trace_link_service.py:573-578`)
   und scheitert hart. MVP-Default (Empfehlung): Lookup vor `create`; existiert ein
   Proposal-Link auf derselben Kante, wird die neue Suggestion an diesen gehängt, statt ein
   Duplikat anzulegen.
8. **O8 — Entitätstyp:** eigene Tabelle oder erstklassiges Generic-Artifact (Artefakt-Taxonomie)?
9. **O9 — Retention/GC:** Aufbewahrungsfrist und Löschregel für `rejected`/`superseded`.
10. **O10 — M2-Proposal vs. Suggestion-only:** MVP materialisiert beim Produzieren einen
    M2-Proposal-TraceLink und bestätigt ihn beim Accept (Empfehlung, s. Entscheidung 3). Die
    schlankere Alternative „Accept = Create ohne M2" (kein Proposal-Link, Provenienz nur in
    `Suggestion`) spart die Redundanz zwischen `Suggestion` und `TraceLink.proposed_by` (berührt
     O4), kostet aber den bestehenden M2-Pfad samt Guard — bewusst vertagt, **nicht** MVP.
11. **O11 — Atomarität von Proposal-Link + Suggestion-Quittung (001-11):** Laufen TraceLink-
    `create` und Suggestion-Insert in **einer** Transaktion (oder Suggestion zuerst), und/oder
    werden verwaiste Proposals in die Inbox aufgenommen? Ohne Festlegung hinterlässt ein
    Teilfehler einen Proposal-Link, der in der Suggestion-/`ReviewQueueService`-Sicht unsichtbar
    ist.

**STOP-Gate:** Bis zur Klärung von O1–O11 und der User-Freigabe wird **kein** MVP implementiert —
keine Migration, kein Modell, kein Tool. Alle drei Review-Iterationen sind abgeschlossen
(`RVW-2026-10-06-001`, `RVW-2026-10-06-002`, `RVW-2026-10-06-003`); Iteration 3 endete mit
Verdict **APPROVED**, einziger offener Befund ist `003-01` (info, nicht blockierend). Das ADR ist
damit **entscheidungsreif**; nächster Schritt ist die User-Freigabe (`proposed → accepted`).

---

*Erstellt durch `ideation` am 2026-10-06 als Entscheidungsvorlage (Status `proposed`);
Überarbeitung Iteration 2 (2026-10-06) nach Review `RVW-2026-10-06-001`,
Iteration 3 (2026-10-06) nach Review `RVW-2026-10-06-002` (001-09/001-10/001-11).
Kein Produktcode, keine Migration, keine Manifest-Änderung, kein Commit.*
