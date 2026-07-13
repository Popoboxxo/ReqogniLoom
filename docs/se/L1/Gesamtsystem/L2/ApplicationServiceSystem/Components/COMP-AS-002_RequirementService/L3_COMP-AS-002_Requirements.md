# L3 RequirementService Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-AS-002 — RequirementService
> **Parent-System:** ApplicationServiceSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Requirement-CRUD, Decomposition-Orchestrierung, LLM-Validation, GitHub-Integration.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-AS-003 | Requirement CRUD mit Workflow-Integration, change_reason-Validierung, Cascade-Delete |
| REQ-L2-AS-013 | LLM-Capabilities orchestrieren (validate, decompose, check_consistency) |
| REQ-L2-AS-015 | GitHub-Integration: Verknuepfung mit Issues und PRs |
| REQ-L2-AS-024 | Decomposition-Orchestrierung mit Kind-Requirements, TraceLinks und WorkflowState |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AS-INT-002 | ausgehend | COMP-AS-005 (TraceLinkService) | `create_trace_link(source_id, target_id, link_type)` |
| IF-AS-INT-003 | ausgehend | COMP-AS-007 (WorkflowFacade) | `transition(item_id, target_state, change_reason, ctx)` |
| IF-AS-INT-008 | ausgehend | COMP-AS-012 (PresetPolicyService) | `is_change_reason_required(workspace_id)` |
| IF-AS-INT-009 | ausgehend | COMP-AS-013 (DomainEventBus) | `RequirementCreated / RequirementUpdated / RequirementDeleted` — post_commit via Outbox |

## Externe Schnittstellen (falls Komponente an Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AS-EXT-OUT-005 | ausgehend | LlmAdapter | `validate`, `decompose`, `check_consistency` |
| IF-AS-EXT-OUT-007 | ausgehend | PersistenceLayer | Django ORM — Requirement-Entitaeten |

---

## L3 Komponenten-Anforderungen

### REQ-L3-AS002-001: Requirement CRUD mit change_reason-Validierung


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der RequirementService SHALL vollstaendiges CRUD fuer Requirements bereitstellen. Bei Create: initialen WorkflowState via WorkflowFacade anlegen. Bei Update: PresetPolicyService konsultieren, ob `change_reason` Pflicht ist — fehlt es im Extended-Preset, die Operation ablehnen. Bei Delete: TraceLinks via TraceLinkService kaskadiert loeschen.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] `create_requirement(data, ctx)` creates requirement with initial WorkflowState and publishes `RequirementCreated` event
- [ ] `update_requirement(id, data, change_reason=None, ctx)` in Extended preset raises `ValidationError("change_reason required")`
- [ ] `update_requirement(id, data, change_reason="justified", ctx)` in Extended preset succeeds
- [ ] `delete_requirement(id, ctx)` removes requirement and all associated TraceLinks atomically

---

### REQ-L3-AS002-002: Decomposition-Orchestrierung


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der RequirementService SHALL die Zerlegung eines Requirements orchestrieren: bei uebergebenen Kind-Definitionen diese validieren und persistieren; ohne Kind-Definitionen an den LlmAdapter delegieren. Nach Kind-Erstellung: parent-child-TraceLinks anlegen, WorkflowStates initialisieren. Die gesamte Operation muss atomar sein.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] `decompose(req_id, children=[...], ctx)` creates children, parent-child TraceLinks, and initial WorkflowStates in a single transaction
- [ ] `decompose(req_id, ctx)` without children calls LlmAdapter and persists structured result
- [ ] `decompose(req_id, ctx)` without children and without LLM configured raises `ConfigurationError("LLM not configured")`
- [ ] Failure after first child INSERT rolls back all children and TraceLinks
- [ ] LLM result failing structural validation raises error and persists nothing

---

### REQ-L3-AS002-003: LLM-Validation und Konsistenzpruefung


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der RequirementService SHALL LLM-gestuetzte Validierung und Konsistenzpruefung einzelner Requirements via LlmAdapter bereitstellen. LLM-Ergebnisse werden strukturell validiert bevor sie zurueckgegeben oder persistiert werden. Fehlende LLM-Konfiguration fuehrt zu einem erklaerenden Fehler — nicht zu einem stillen Leerfallback.

**Priority:** mandatory

**Acceptance Criteria:**
- [ ] `validate_requirement(id, ctx)` with LLM configured returns structured validation result
- [ ] `validate_requirement(id, ctx)` without LLM configured raises `ConfigurationError("LLM not configured")`
- [ ] Structurally invalid LLM response raises `LlmResponseError` and does not persist partial data
- [ ] `check_consistency(id, ctx)` delegates to LlmAdapter and returns consistency report

---

### REQ-L3-AS002-004: GitHub-Verknuepfung


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.


Der RequirementService SOLLTE die Verknuepfung von Requirements mit GitHub Issues und Pull Requests unterstuetzen. Verknuepfungen sind bidirektional abrufbar. Fehlende oder ungueltige GitHub-Konfiguration ergibt einen erklaerenden Fehler.

**Priority:** desired

**Acceptance Criteria:**
- [ ] `link_github_issue(req_id, issue_url, ctx)` with valid token stores association
- [ ] `get_github_links(req_id, ctx)` returns list of linked issues/PRs
- [ ] Call without configured token raises `ConfigurationError("GitHub token not configured")`
- [ ] Call with invalid token raises `AuthenticationError("GitHub authentication failed")`

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
