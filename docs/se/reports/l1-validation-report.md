# L1 System Validation Report — ReqFlow

> **Validation ID:** VAL-001  
> **System Level:** L1 (Gesamtsystem)  
> **Datum:** 2026-06-20  
> **Validator:** se-validator-Agent  
> **Quellen:** docs/se/L0/SN_Stakeholder_Needs.md, docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Architecture.md, docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Requirements.md  
> **Verdict:** APPROVED_WITH_WARNINGS

---

## 1. Zusammenfassung

Dieser Bericht validiert die L1-Systemarchitektur von ReqFlow (12 Subsysteme, ARCH-L1-001..012) gegen die 15 Stakeholder-Needs (REQ-L0-001..015). Die Validierung erfolgt ausschließlich auf L1-Ebene (Black-Box) durch Simulation von End-to-End-User-Journeys. Keine Code-Inspektion.

**Ergebnis:** Alle Must-Have Stakeholder-Needs werden durch mindestens eine vollständige User-Journey abgedeckt. Zwei Should-Have Needs (REQ-L0-014, REQ-L0-015) sind in der L1-Architektur erfasst, aber mit niedrigerer Priorität (`desired`). Drei offene Design-Punkte (OP-01..03) existieren, blockieren jedoch nicht die L1-Validierung.

---

## 2. User-Journey-Simulationen

### Journey 1: Requirement Creation and Management

**Stakeholder Needs:** REQ-L0-002 (Skalierbare SE-Tiefe), REQ-L0-005 (Item-Lifecycle), REQ-L0-009 (i18n), REQ-L0-010 (Terminologie-Flexibilität), REQ-L0-011 (Audit-Trail), REQ-L0-012 (REST/MCP Parität)

**Actor:** Software Engineer / Systems Engineer  
**Trigger:** User opens ReqFlow in browser to document a new requirement

**Steps:**
1. **User opens browser** → ReactFrontend (ARCH-L1-001) renders login page in user's language (DE/EN) via react-i18next.
2. **User logs in** → AuthAndTenancy (ARCH-L1-011) validates Bearer Token, extracts tenant, propagates tenant context.
3. **User navigates to workspace** → ReactFrontend loads workspace settings from PresetConfigEngine (ARCH-L1-008); UI adapts labels based on active terminology profile (Dev-Modus / SE-Modus).
4. **User creates requirement** → ReactFrontend sends POST /api/requirements to RestApiAdapter (ARCH-L1-002).
5. **RestApiAdapter validates token** → AuthAndTenancy confirms role (Editor).
6. **ApplicationService (ARCH-L1-004) processes request** → Creates Requirement in PersistenceLayer (ARCH-L1-010) with tenant_id filter enforced by Custom Manager.
7. **WorkflowEngine (ARCH-L1-005) initializes state** → Sets initial WorkflowState (e.g., "Draft") based on Workspace's WorkflowDefinition.
8. **AuditLog (ARCH-L1-012) records operation** → Appends entry with user identity, operation, entity ID, timestamp.
9. **Response returns** → Requirement JSON with UUID, WorkflowState, audit fields → UI displays confirmation.

**Expected Outcome:** Requirement stored with UUID, visible in hierarchy, workflow state initialized, operation audited.

**Acceptance Signal:** Confirmation toast + requirement appears in artifact tree with correct label (e.g., "Story" in Dev-Modus, "Requirement" in SE-Modus).

**System Coverage:** Fulfilled

**Gaps:** None at L1.

---

### Journey 2: Baseline Creation and Comparison

**Stakeholder Need:** REQ-L0-004 (Unveränderliche Baselines)

**Actor:** Systems Engineer (Compliance-focused)  
**Trigger:** Team needs to freeze requirements state before design review

**Steps:**
1. **User navigates to Baselines view** → ReactFrontend checks PresetConfigEngine: is `baseline` feature enabled for this workspace's preset? (Minimal: no; Standard/Extended: yes).
2. **User clicks "Create Baseline"** → Selects scope: `project` (enabled for Standard+).
3. **UI sends POST /api/baselines** → RestApiAdapter → ApplicationService → BaselineService (ARCH-L1-006).
4. **BaselineService resolves scope** → Queries PersistenceLayer for all Requirements, ArchitectureElements, TestCases, TraceLinks in workspace.
5. **TraceabilityEngine (ARCH-L1-007) collects trace graph** → Returns complete link structure.
6. **BaselineService atomically persists snapshot** → JSON blob with item IDs + versions → PersistenceLayer. Baseline is immutable after creation.
7. **AuditLog records baseline creation** → Entry with user, scope, baseline ID.
8. **User views baseline list** → UI displays baselines with metadata.
9. **User selects two baselines and clicks "Compare"** → ApplicationService calls `BaselineService.diff(a, b)`.
10. **Diff result returned** → Added / changed / removed items with version delta.

**Expected Outcome:** Immutable baseline snapshot created on three possible scopes; diff capability available.

**Acceptance Signal:** Baseline appears in list with timestamp; diff view highlights changes.

**System Coverage:** Fulfilled

**Gaps:** None at L1. Note: Global scope only in Extended preset — this is per-design.

---

### Journey 3: Traceability Visualization

**Stakeholder Need:** REQ-L0-003 (Vollständige Traceability)

**Actor:** Systems Engineer / AI Agent  
**Trigger:** Need to understand impact of a requirement change or verify test coverage

**Steps:**
1. **User navigates to Traceability view** → ReactFrontend loads Traceability component.
2. **User selects a requirement** → UI sends GET /api/traceability?artifact_id=...&direction=downstream to RestApiAdapter.
3. **ApplicationService delegates to TraceabilityEngine (ARCH-L1-007)** → Queries TraceLinks from PersistenceLayer.
4. **TraceabilityEngine returns graph** → Links with types: `satisfies`, `verifies`, `implements`, `refines`, `derives-from`, `parent-child`.
5. **UI renders traceability graph** → Visual upstream/downstream tree.
6. **User requests Coverage Report** → UI sends GET /api/coverage?workspace_id=....
7. **TraceabilityEngine calculates coverage** → For each Requirement, checks if at least one linked TestCase exists (via `verifies` link).
8. **Coverage metrics returned** → Percentage + uncovered requirements list.

**Expected Outcome:** Bidirectional traceability graph visible; coverage report shows test completeness.

**Acceptance Signal:** Graph renders with link types annotated; coverage percentage displayed.

**System Coverage:** Fulfilled

**Gaps:** None at L1. Performance target (<200ms for 10k items) is specified but not validated at L1.

---

### Journey 4: MCP Tool Usage by AI Agent

**Stakeholder Needs:** REQ-L0-001 (Maschinenlesbarer Kontext), REQ-L0-007 (LLM-QS), REQ-L0-011 (Audit-Trail für Agenten), REQ-L0-012 (REST/MCP Parität)

**Actor:** AI Agent (Claude Code, Cursor, CI Agent)  
**Trigger:** Agent needs structured requirements context for code generation or review

**Steps:**
1. **Agent connects via MCP** → McpServer (ARCH-L1-003) accepts connection (stdio/sse/HTTP).
2. **Agent calls `workspace.get_context`** → McpServer validates API Key via AuthAndTenancy.
3. **AuthAndTenancy returns tenant + roles** → MCP context established.
4. **Agent calls `artifact.search`** → McpServer → ApplicationService → PersistenceLayer (full-text search via PostgreSQL tsvector). Results returned in <500ms.
5. **Agent calls `requirement.get`** → Retrieves structured requirement with all fields.
6. **Agent calls `requirement.decompose`** → ApplicationService checks PresetConfigEngine for LLM capability enabled.
7. **LlmAdapter (ARCH-L1-009) calls external LLM** → Provider-agnostic HTTPS call; returns structured child requirements.
8. **ApplicationService creates child requirements** → Batch INSERT via PersistenceLayer + TraceLinks (parent-child).
9. **WorkflowEngine initializes child states** → Default state per WorkflowDefinition.
10. **AuditLog records agent operation** → Entry with Agent-Client identity, API-Key, operation `decompose`, entity IDs.
11. **McpServer returns JSON response** → Structured decomposition result.

**Expected Outcome:** Agent has full structured read/write access; all operations audited with agent identity; LLM capabilities optional and gracefully degraded if not configured.

**Acceptance Signal:** JSON response contains requirements data; audit log shows agent entries; system works even if LLM is unconfigured (returns "LLM nicht konfiguriert" for validate/decompose).

**System Coverage:** Fulfilled

**Gaps:** None at L1. Note: OP-01 (LLM-Capability-Scope) is pending — which exact capabilities are v1 vs v2. Architecture supports selective activation via `LlmAdapter.CapabilityRegistry`.

---

### Journey 5: Data Import and Export

**Stakeholder Needs:** REQ-L0-013 (CSV-Import), REQ-L0-015 (PDF-Reports)

**Actor:** Migration Engineer / Compliance Officer  
**Trigger:** Team needs to import legacy requirements or export audit documentation

**Import Steps:**
1. **User navigates to Import** → ReactFrontend displays CSV upload UI.
2. **User uploads CSV** → RestApiAdapter receives file; ApplicationService (ARCH-L1-004) invokes CSV-Bulk-Import logic.
3. **Validation against Datenmodell** → Each row validated; errors reported with line numbers.
4. **Successful items inserted** → PersistenceLayer assigns regular UUIDs; TraceLinks created if specified.
5. **Import report returned** → Count of successful + failed rows with error details.

**Export Steps:**
6. **User navigates to Export** → Selects scope (workspace/artifact), format (JSON/CSV/PDF).
7. **JSON/CSV export** → ApplicationService serializes entities + metadata (including active terminology profile).
8. **PDF export (Should-Have)** → ApplicationService generates PDF report with requirements, metadata, baseline reference, workflow history, traceability matrix.
9. **File download initiated** → User receives export file.

**Expected Outcome:** Legacy data imported with validation; audit-ready reports exportable in multiple formats.

**Acceptance Signal:** Import report shows success count; PDF contains formatted requirements + traceability matrix with version and baseline info.

**System Coverage:** Partially Fulfilled — REQ-L0-013 (CSV-Import) is fully covered (mandatory REQ-L1-021). REQ-L0-015 (PDF) is covered at architecture level but marked as `desired` priority (REQ-L1-023).

**Gaps:** PDF Export is Should-Have v1; architecture supports it but implementation priority is lower.

---

### Journey 6: Multi-tenant Workspace Management

**Stakeholder Needs:** REQ-L0-006 (Self-Hosted), REQ-L0-008 (Mandantenfähigkeit), REQ-L0-009 (i18n), REQ-L0-010 (Terminologie-Flexibilität)

**Actor:** Operator / Admin  
**Trigger:** Team wants to deploy ReqFlow on-premise and configure workspace

**Steps:**
1. **Operator clones repository** → Runs `docker-compose up` (Backend, Frontend, PostgreSQL start).
2. **System initializes** → Default Tenant created automatically (v1 behavior).
3. **Admin logs in** → Creates Workspace; selects Preset (Minimal / Standard / Extended).
4. **PresetConfigEngine (ARCH-L1-008) applies rules** → Pflichtfelder, visible features, baseline scopes, workflow configurability determined.
5. **Admin selects terminology profile** → Dev-Modus or SE-Modus; UI labels adapt immediately; no data migration needed.
6. **Admin assigns users** → Roles: Admin, Editor, Viewer (Approver only in Extended).
7. **AuthAndTenancy enforces tenant isolation** → Custom Django Manager automatically filters all queries by tenant_id; no application logic can bypass.
8. **User accesses workspace** → Sees UI in preferred language (DE/EN); features match preset; all data isolated.

**Expected Outcome:** Self-hosted deployment operational; workspace configured with configurable rigor; tenant isolation enforced; terminology and language adaptable without data loss.

**Acceptance Signal:** `docker-compose up` succeeds; UI shows correct features for selected preset; language switch works; database queries include tenant filter.

**System Coverage:** Fulfilled

**Gaps:** None at L1. Note: OP-03 (Tenant-Isolation-Strenge) is pending but architecture decision (Row-Level + Custom Manager) is made and documented in ADR-03.

---

## 3. Abgleich Stakeholder-Needs ↔ L1-Architektur

| Need ID | Need Text | Journey | Status | Blocking |
|---|---|---|---|---|
| REQ-L0-001 | Maschinenlesbarer Kontext für AI-Agenten | Journey 4 | Fulfilled | No |
| REQ-L0-002 | Skalierbare SE-Tiefe ohne Produktwechsel | Journey 1, Journey 6 | Fulfilled | No |
| REQ-L0-003 | Vollständige Traceability | Journey 3 | Fulfilled | No |
| REQ-L0-004 | Unveränderliche Baselines | Journey 2 | Fulfilled | No |
| REQ-L0-005 | Konfigurierbarer Item-Lifecycle mit Rollen | Journey 1 | Fulfilled | No |
| REQ-L0-006 | Self-Hosted Deployment ohne Vendor-Lock-in | Journey 6 | Fulfilled | No |
| REQ-L0-007 | LLM-gestützte QS als optionale Capability | Journey 4 | Fulfilled | No |
| REQ-L0-008 | Mandantenfähige Isolation für SaaS-Erweiterung | Journey 6 | Fulfilled | No |
| REQ-L0-009 | Zweisprachige Benutzeroberfläche | Journey 1, Journey 6 | Fulfilled | No |
| REQ-L0-010 | Terminologie-Flexibilität ohne Datenverlust | Journey 6 | Fulfilled | No |
| REQ-L0-011 | Vollständiger Audit-Trail | Journey 1, Journey 4 | Fulfilled | No |
| REQ-L0-012 | REST API und MCP als gleichrangige Schnittstellen | Journey 1, Journey 4 | Fulfilled | No |
| REQ-L0-013 | CSV-Bulk-Import für Migration | Journey 5 | Fulfilled | No |
| REQ-L0-014 | GitHub-Integration (Issues/PRs) | — | Partially Fulfilled | No |
| REQ-L0-015 | PDF-Report-Export für Audits | Journey 5 | Partially Fulfilled | No |

**Anmerkungen:**
- REQ-L0-014 und REQ-L0-015 sind in KONZEPT.md als Should-Have klassifiziert und in L1-Requirements mit `desired` priorisiert. Die Architektur bietet Eintrittspunkte (REQ-L1-022, REQ-L1-023), aber keine Blockierung.
- REQ-L0-011 wird durch AuditLog (ARCH-L1-012) abgedeckt; die v1-Granularität ist Operation-Level (ADR-10), was die Akzeptanzkriterien erfüllt.

---

## 4. L1-Architektur-Elemente in Journeys

| Journey | Primäre Subsysteme | Querschnitts-Subsysteme |
|---|---|---|
| Journey 1 | A001 (ReactFrontend), A002 (RestApiAdapter), A004 (ApplicationService), A005 (WorkflowEngine) | A008 (PresetConfigEngine), A010 (PersistenceLayer), A011 (AuthAndTenancy), A012 (AuditLog) |
| Journey 2 | A006 (BaselineService), A007 (TraceabilityEngine) | A004 (ApplicationService), A008 (PresetConfigEngine), A010 (PersistenceLayer), A012 (AuditLog) |
| Journey 3 | A007 (TraceabilityEngine), A001 (ReactFrontend) | A002 (RestApiAdapter), A004 (ApplicationService), A010 (PersistenceLayer) |
| Journey 4 | A003 (McpServer), A004 (ApplicationService), A009 (LlmAdapter) | A005 (WorkflowEngine), A008 (PresetConfigEngine), A010 (PersistenceLayer), A011 (AuthAndTenancy), A012 (AuditLog) |
| Journey 5 | A004 (ApplicationService) | A010 (PersistenceLayer), A007 (TraceabilityEngine für PDF-Matrix) |
| Journey 6 | A001 (ReactFrontend), A010 (PersistenceLayer), A011 (AuthAndTenancy) | A008 (PresetConfigEngine) |

**Beobachtung:** Alle 12 Subsysteme sind in mindestens einer Journey involviert. KeinSubsystem ist "toter Code" aus L1-Sicht.

---

## 5. Gap-Analyse

### 5.1 Keine Blockierenden Gaps

Kein Must-Have Stakeholder-Need ist ohne L1-Abdeckung. Keine kritische Journey ohne System-Eintrittspunkt. Keine Sicherheitsanforderung unaddressed.

### 5.2 Warnungen (Non-Blocking)

| # | Issue | Betroffener Need | Empfehlung |
|---|---|---|---|
| W-01 | **Open Point OP-02 (Preset Downgrade)** — Verhalten beim Wechsel von Extended → Standard ist undefiniert. Bestehende Global-Baselines und Approved-Items könnten inkonsistent werden. | REQ-L0-002, REQ-L0-004 | Empfehlung aus Architektur: Block-Downgrade solange inkompatible Items existieren. Muss vor Implementierung entschieden werden. |
| W-02 | **REQ-L0-014 (GitHub-Integration)** — Should-Have mit `desired`-Priorität in L1. Architektur bietet Eintrittspunkt (A004 → GitHub API), aber kein dediziertes Subsystem. | REQ-L0-014 | Kein Blocker für v1-Must-Haves. Für v1-Release empfohlen, falls Kapazität vorhanden. |
| W-03 | **REQ-L0-015 (PDF-Export)** — Should-Have mit `desired`-Priorität. Architektur unterstützt via ApplicationService + TraceabilityEngine, aber kein dediziertes Reporting-Subsystem. | REQ-L0-015 | Kein Blocker. PDF-Generation kann als Service innerhalb A004 implementiert werden. |
| W-04 | **Open Point OP-01 (LLM-Capability-Scope)** — Noch nicht entschieden, welche der 4 LLM-Capabilities in v1 operativ sind. Architektur (LlmAdapter.CapabilityRegistry) ist flexibel genug. | REQ-L0-007 | Empfehlung aus KONZEPT.md: Validierung + Decomposition für v1. Entscheidung erforderlich vor L2-Verfeinerung. |
| W-05 | **Performance-Validierung** — NF-Anforderung <200ms/<500ms ist in L1 spezifiziert (REQ-L1-026, ADR-09), aber keine dedizierte Performance-Monitoring-Architektur definiert. | REQ-L0-002 | Empfohlen: Observability-Querschnittsaspekt (Logging/Metrics) in L2 oder L3 ergänzen. |

### 5.3 Over-Engineering

Kein Over-Engineering auf L1-Ebene festgestellt. Alle 12 Subsysteme sind durch mindestens einen Stakeholder-Need motiviert. Die Dual-Interface-Entscheidung (MCP + REST als gleichrangige Adapter) ist zwar komplexer als ein Wrapper-Ansatz, aber durch REQ-L0-001 und REQ-L0-012 explizit gefordert.

---

## 6. Validierungs-Verdict

**VERDICT:** `APPROVED_WITH_WARNINGS`

**Rationale:**
- Alle 13 Must-Have Stakeholder-Needs (REQ-L0-001..013) sind durch vollständige User-Journeys auf L1-Ebene abgedeckt.
- Die L1-Architektur (12 Subsysteme) bietet für jede kritische Journey einen definierten Eintrittspunkt und eine klare Schnittstellen-Kette.
- Sicherheits- und Audit-Anforderungen (REQ-L0-011) sind durch dedizierte Subsysteme (AuthAndTenancy, AuditLog) addressiert.
- Zwei Should-Have Needs (REQ-L0-014, REQ-L0-015) sind mit niedrigerer Priorität erfasst — dies ist beabsichtigt und blockiert nicht.
- Drei offene Design-Punkte (OP-01..03) existieren; sie betreffen Implementierungsdetails und keine L1-Systemstruktur.

**Empfohlene nächste Schritte:**
1. L2-Architektur-Dokumente für alle 12 Subsysteme erstellen (Parallelisierung möglich).
2. Offene Punkte OP-01, OP-02, OP-03 vor L2-Start klären (Stakeholder-Entscheidung).
3. Performance-Observability als Querschnittsanliegen in L2 ergänzen.

---

## 7. JSON Validation Report

```json
{
  "validation_id": "VAL-001",
  "system_level": "L1",
  "stakeholder_needs_reviewed": [
    {
      "need_id": "REQ-L0-001",
      "need_text": "AI-Agenten benötigen strukturierten, maschinenlesbaren Zugriff auf Anforderungen, Architektur und Tests — ohne Text-Parsing oder Webhook-Wrapper.",
      "user_journeys": [
        {
          "journey_name": "MCP Tool Usage by AI Agent",
          "actor": "AI Agent (Claude Code, Cursor, CI Agent)",
          "trigger": "Agent needs structured requirements context for code generation",
          "steps": [
            "Agent connects via MCP protocol to McpServer",
            "Agent authenticates with API Key via AuthAndTenancy",
            "Agent calls workspace.get_context for orientation",
            "Agent searches artifacts via artifact.search",
            "Agent reads/writes requirements via MCP Tools",
            "AuditLog records all agent operations with identity"
          ],
          "expected_outcome": "Full structured read/write access for AI agents with complete audit trail",
          "acceptance_signal": "Structured JSON responses; audit log shows agent entries; graceful degradation without LLM",
          "system_coverage": "Fulfilled",
          "gaps": []
        }
      ],
      "overall_status": "Fulfilled",
      "blocking": false
    },
    {
      "need_id": "REQ-L0-002",
      "need_text": "Teams unterschiedlicher Reife müssen dieselbe Plattform mit unterschiedlicher Prozessstrenge nutzen können — von einfachem CRUD bis zu vollständigem SE.",
      "user_journeys": [
        {
          "journey_name": "Requirement Creation and Management",
          "actor": "Software Engineer / Systems Engineer",
          "trigger": "User opens ReqFlow to document a requirement",
          "steps": [
            "User logs in via ReactFrontend",
            "Workspace preset is loaded from PresetConfigEngine",
            "UI adapts: visible fields, mandatory fields, workflow options depend on preset",
            "User creates requirement with workflow state transition",
            "System validates against preset rules and RBAC"
          ],
          "expected_outcome": "Requirements management adapts to team maturity level without tool switch",
          "acceptance_signal": "UI shows appropriate fields/features for Minimal/Standard/Extended preset",
          "system_coverage": "Fulfilled",
          "gaps": []
        },
        {
          "journey_name": "Workspace Configuration and Deployment",
          "actor": "Operator / Admin",
          "trigger": "Team deploys ReqFlow on-premise",
          "steps": [
            "Deploy via docker-compose up",
            "Configure workspace with preset (Minimal/Standard/Extended)",
            "Preset determines available features, baseline scopes, workflow configurability"
          ],
          "expected_outcome": "Self-hosted deployment with configurable rigor per workspace",
          "acceptance_signal": "System runs locally; preset changes adapt UI and behavior without migration",
          "system_coverage": "Fulfilled",
          "gaps": []
        }
      ],
      "overall_status": "Fulfilled",
      "blocking": false
    },
    {
      "need_id": "REQ-L0-003",
      "need_text": "Bidirektionale Verknüpfungen zwischen Anforderungen, Architektur-Elementen und Testfällen für Impact-Analysen und Coverage-Reports.",
      "user_journeys": [
        {
          "journey_name": "Traceability Visualization",
          "actor": "Systems Engineer / AI Agent",
          "trigger": "Need to understand impact of requirement change or verify test coverage",
          "steps": [
            "User navigates to Traceability view",
            "Selects artifact and queries upstream/downstream links",
            "TraceabilityEngine returns graph with link types",
            "UI renders visual traceability tree",
            "User requests Coverage Report showing requirement → test linkage"
          ],
          "expected_outcome": "Bidirectional traceability visible; coverage metrics show test completeness",
          "acceptance_signal": "Graph renders with link types; coverage percentage and uncovered items displayed",
          "system_coverage": "Fulfilled",
          "gaps": []
        }
      ],
      "overall_status": "Fulfilled",
      "blocking": false
    },
    {
      "need_id": "REQ-L0-004",
      "need_text": "Unveränderliche, benannte Anforderungs-Baselines auf Dokument-, Projekt- und Instanz-Ebene.",
      "user_journeys": [
        {
          "journey_name": "Baseline Creation and Comparison",
          "actor": "Systems Engineer (Compliance-focused)",
          "trigger": "Team needs to freeze requirements state before review",
          "steps": [
            "User navigates to Baselines view (enabled by preset)",
            "Selects scope (document/project/global) and names baseline",
            "BaselineService resolves scope and collects all items + versions",
            "TraceabilityEngine provides complete link graph",
            "Baseline atomically persisted as immutable JSON snapshot",
            "User compares two baselines: diff shows added/changed/removed items"
          ],
          "expected_outcome": "Immutable baseline snapshots on three scopes; diff capability available",
          "acceptance_signal": "Baseline in list with timestamp; diff highlights changes with version delta",
          "system_coverage": "Fulfilled",
          "gaps": []
        }
      ],
      "overall_status": "Fulfilled",
      "blocking": false
    },
    {
      "need_id": "REQ-L0-005",
      "need_text": "Konfigurierbarer Item-Lifecycle mit Rollen und Approval-Gates ohne Code-Änderungen.",
      "user_journeys": [
        {
          "journey_name": "Requirement Creation and Management",
          "actor": "Software Engineer / Systems Engineer",
          "trigger": "User creates or transitions a requirement",
          "steps": [
            "Requirement created with initial WorkflowState",
            "WorkflowEngine initializes state per WorkflowDefinition",
            "User requests state transition (e.g., Draft → Review)",
            "WorkflowEngine validates: allowed roles? change_reason provided?",
            "Transition accepted or rejected with reason",
            "WorkflowState.history updated with user, timestamp, reason"
          ],
          "expected_outcome": "Requirements follow configurable workflow with role-based approval gates",
          "acceptance_signal": "State transitions succeed only with proper role and reason; history complete",
          "system_coverage": "Fulfilled",
          "gaps": []
        }
      ],
      "overall_status": "Fulfilled",
      "blocking": false
    },
    {
      "need_id": "REQ-L0-006",
      "need_text": "Self-Hosted Deployment ohne Vendor-Lock-in, ohne Cloud-Zwang, mit voller Datenkontrolle.",
      "user_journeys": [
        {
          "journey_name": "Workspace Configuration and Deployment",
          "actor": "Operator / Admin",
          "trigger": "Team wants on-premise deployment",
          "steps": [
            "Operator runs docker-compose up",
            "Three services start: Backend (Django), Frontend (React), PostgreSQL",
            "No external cloud dependencies required",
            "LLM optional via environment variables"
          ],
          "expected_outcome": "Fully self-hosted ReqFlow instance operational",
          "acceptance_signal": "Application accessible on local host; data remains on-premise",
          "system_coverage": "Fulfilled",
          "gaps": []
        }
      ],
      "overall_status": "Fulfilled",
      "blocking": false
    },
    {
      "need_id": "REQ-L0-007",
      "need_text": "LLM-gestützte Qualitätssicherung als optionale Capability — System funktioniert ohne LLM-Zugang.",
      "user_journeys": [
        {
          "journey_name": "MCP Tool Usage by AI Agent",
          "actor": "AI Agent",
          "trigger": "Agent invokes LLM-capable tool",
          "steps": [
            "Agent calls requirement.validate or requirement.decompose",
            "ApplicationService checks PresetConfigEngine: LLM enabled?",
            "If LLM configured: LlmAdapter calls provider (Anthropic/OpenAI/Ollama/Azure)",
            "If LLM not configured: graceful error 'LLM nicht konfiguriert'",
            "Core functionality (CRUD, traceability, workflow) works regardless"
          ],
          "expected_outcome": "LLM features available when configured; system fully functional without LLM",
          "acceptance_signal": "LLM calls return structured results when configured; clean error when not",
          "system_coverage": "Fulfilled",
          "gaps": []
        }
      ],
      "overall_status": "Fulfilled",
      "blocking": false
    },
    {
      "need_id": "REQ-L0-008",
      "need_text": "Mandantenfähige Isolation für spätere SaaS-Erweiterung ohne Datenmigration.",
      "user_journeys": [
        {
          "journey_name": "Workspace Configuration and Deployment",
          "actor": "Operator / Admin",
          "trigger": "Workspace setup with tenant isolation",
          "steps": [
            "System initializes with Default Tenant (v1)",
            "All entities carry tenant_id FK",
            "Custom Django Manager automatically filters every query by tenant_id",
            "AuthAndTenancy middleware propagates tenant context",
            "v2 activation of additional tenants requires no schema migration"
          ],
          "expected_outcome": "Row-level tenant isolation enforced; v2 multi-tenant activation without migration",
          "acceptance_signal": "Database queries include tenant filter; no data leakage between contexts",
          "system_coverage": "Fulfilled",
          "gaps": []
        }
      ],
      "overall_status": "Fulfilled",
      "blocking": false
    },
    {
      "need_id": "REQ-L0-009",
      "need_text": "Zweisprachige Benutzeroberfläche (Deutsch und Englisch) ohne Funktionseinschränkungen.",
      "user_journeys": [
        {
          "journey_name": "Requirement Creation and Management",
          "actor": "End User",
          "trigger": "User accesses ReqFlow UI",
          "steps": [
            "ReactFrontend detects language preference (Accept-Language or profile)",
            "UI renders all labels, buttons, messages in DE or EN via react-i18next",
            "Backend error messages translated via central i18n module",
            "Missing translation keys are build errors (lint rule)"
          ],
          "expected_outcome": "Complete UI and error messages available in German and English",
          "acceptance_signal": "Language switch changes all UI text; no untranslated strings visible",
          "system_coverage": "Fulfilled",
          "gaps": []
        }
      ],
      "overall_status": "Fulfilled",
      "blocking": false
    },
    {
      "need_id": "REQ-L0-010",
      "need_text": "Terminologie-Flexibilität für zwei Zielgruppen ohne Datenverlust oder Migration.",
      "user_journeys": [
        {
          "journey_name": "Workspace Configuration and Deployment",
          "actor": "Admin",
          "trigger": "Team wants to switch between Dev and SE terminology",
          "steps": [
            "Admin selects terminology profile (Dev-Modus or SE-Modus) in workspace settings",
            "PresetConfigEngine stores active profile",
            "ReactFrontend reloads labels: Epic→Story→Task vs System Requirement→Function→Verification Criteria",
            "API and MCP responses unchanged (generic entity names)",
            "No database schema change; no data migration"
          ],
          "expected_outcome": "Terminology adapts instantly without data loss",
          "acceptance_signal": "Profile switch changes UI labels immediately; all data intact; API unaffected",
          "system_coverage": "Fulfilled",
          "gaps": []
        }
      ],
      "overall_status": "Fulfilled",
      "blocking": false
    },
    {
      "need_id": "REQ-L0-011",
      "need_text": "Vollständiger Audit-Trail für agentengesteuerte und manuelle Änderungen.",
      "user_journeys": [
        {
          "journey_name": "Requirement Creation and Management",
          "actor": "End User",
          "trigger": "Any write operation via UI",
          "steps": [
            "User creates/updates requirement via REST",
            "ApplicationService invokes AuditLog after successful persistence",
            "AuditLog appends entry: user, operation, entity ID, timestamp"
          ],
          "expected_outcome": "All manual changes audited",
          "acceptance_signal": "Audit log entry visible for every write operation",
          "system_coverage": "Fulfilled",
          "gaps": []
        },
        {
          "journey_name": "MCP Tool Usage by AI Agent",
          "actor": "AI Agent",
          "trigger": "Any write operation via MCP",
          "steps": [
            "Agent calls write tool (requirement.create, etc.)",
            "ApplicationService invokes AuditLog",
            "AuditLog records: Agent-Client identity, API-Key, operation, entity IDs, timestamp"
          ],
          "expected_outcome": "All agent changes audited with agent identity",
          "acceptance_signal": "Audit log distinguishes human and agent actors; API-Key traceable",
          "system_coverage": "Fulfilled",
          "gaps": []
        }
      ],
      "overall_status": "Fulfilled",
      "blocking": false
    },
    {
      "need_id": "REQ-L0-012",
      "need_text": "REST API und MCP Server als gleichrangige, vollständige Schnittstellen.",
      "user_journeys": [
        {
          "journey_name": "Requirement Creation and Management",
          "actor": "API Client / Engineer",
          "trigger": "Client accesses ReqFlow via REST",
          "steps": [
            "Client sends HTTP request with Bearer Token to RestApiAdapter",
            "RestApiAdapter directly calls ApplicationService (not via MCP)",
            "Full CRUD on all artifact types available"
          ],
          "expected_outcome": "Complete REST access to all entities",
          "acceptance_signal": "OpenAPI spec auto-generated; all CRUD operations functional",
          "system_coverage": "Fulfilled",
          "gaps": []
        },
        {
          "journey_name": "MCP Tool Usage by AI Agent",
          "actor": "AI Agent",
          "trigger": "Agent accesses ReqFlow via MCP",
          "steps": [
            "Agent connects via MCP protocol to McpServer",
            "McpServer directly calls ApplicationService (not via REST)",
            "Same use-case methods as REST; full CRUD on all artifact types",
            "20 tools available across 4 groups"
          ],
          "expected_outcome": "Complete MCP access to all entities with same semantics as REST",
          "acceptance_signal": "Every REST operation has MCP equivalent; no second-class interface",
          "system_coverage": "Fulfilled",
          "gaps": []
        }
      ],
      "overall_status": "Fulfilled",
      "blocking": false
    },
    {
      "need_id": "REQ-L0-013",
      "need_text": "Effiziente Übernahme bestehender Anforderungsdaten via CSV-Bulk-Import.",
      "user_journeys": [
        {
          "journey_name": "Data Import and Export",
          "actor": "Migration Engineer",
          "trigger": "Team migrates existing requirements to ReqFlow",
          "steps": [
            "User uploads CSV file via ReactFrontend",
            "RestApiAdapter receives file; ApplicationService processes import",
            "Each row validated against data model; errors reported with line numbers",
            "Successful items inserted with regular UUIDs; TraceLinks created if specified",
            "Import report returned with success/failure counts"
          ],
          "expected_outcome": "Legacy requirements imported with validation and error reporting",
          "acceptance_signal": "Import report shows correct counts; imported items have UUIDs and are queryable",
          "system_coverage": "Fulfilled",
          "gaps": []
        }
      ],
      "overall_status": "Fulfilled",
      "blocking": false
    },
    {
      "need_id": "REQ-L0-014",
      "need_text": "Integration mit Entwicklungstools und Issue-Trackern (GitHub Issues/PRs).",
      "user_journeys": [
        {
          "journey_name": "GitHub Integration (Should-Have v1)",
          "actor": "Developer",
          "trigger": "Team wants to link requirements to GitHub Issues/PRs",
          "steps": [
            "User configures GitHub token in workspace settings",
            "User links Requirement to GitHub Issue or PR via UI or API",
            "ApplicationService stores link; bidirectional query possible"
          ],
          "expected_outcome": "Requirements linked to GitHub artifacts",
          "acceptance_signal": "Link visible in ReqFlow; reference retrievable via REST/MCP",
          "system_coverage": "Partially Fulfilled",
          "gaps": ["REQ-L1-022 marked as desired/Should-Have; no dedicated subsystem in L1; implementation priority lower than Must-Haves"]
        }
      ],
      "overall_status": "Partially Fulfilled",
      "blocking": false
    },
    {
      "need_id": "REQ-L0-015",
      "need_text": "Audit-dokumentierbare Anforderungsberichte und Traceability-Matrizen als PDF.",
      "user_journeys": [
        {
          "journey_name": "Data Import and Export",
          "actor": "Compliance Officer",
          "trigger": "Need to produce audit documentation",
          "steps": [
            "User navigates to Export; selects PDF format",
            "Selects scope and report type (requirements document or traceability matrix)",
            "ApplicationService generates PDF including metadata, version, baseline reference, workflow history",
            "TraceabilityEngine provides matrix data",
            "File download initiated"
          ],
          "expected_outcome": "Audit-ready PDF reports generated",
          "acceptance_signal": "PDF contains formatted requirements, metadata, traceability matrix",
          "system_coverage": "Partially Fulfilled",
          "gaps": ["REQ-L1-023 marked as desired/Should-Have; architecture supports via ApplicationService + TraceabilityEngine but no dedicated reporting subsystem"]
        }
      ],
      "overall_status": "Partially Fulfilled",
      "blocking": false
    }
  ],
  "blocking_issues": [],
  "warnings": [
    {
      "need_id": "REQ-L0-002",
      "issue": "Open Point OP-02: Preset-Downgrade-Verhalten (Extended → Standard) ist undefiniert. Bestehende Global-Baselines und Approved-Items könnten inkonsistent werden.",
      "recommendation": "Block-Downgrade solange inkompatible Items existieren. Vor L2-Implementierung entscheiden."
    },
    {
      "need_id": "REQ-L0-004",
      "issue": "Open Point OP-02 betrifft Baseline-Scope-Verfügbarkeit bei Preset-Wechsel.",
      "recommendation": "Downgrade-Policy in PresetConfigEngine definieren."
    },
    {
      "need_id": "REQ-L0-014",
      "issue": "Should-Have Need für GitHub-Integration ist in L1 mit desired-Priorität erfasst (REQ-L1-022), aber kein dediziertes Subsystem existiert.",
      "recommendation": "Als Service innerhalb ApplicationService implementieren oder als eigenes Subsystem in L2 ausmodellieren, falls Kapazität vorhanden."
    },
    {
      "need_id": "REQ-L0-015",
      "issue": "Should-Have Need für PDF-Export ist in L1 mit desired-Priorität erfasst (REQ-L1-023), aber kein dediziertes Reporting-Subsystem existiert.",
      "recommendation": "PDF-Generation als Modul innerhalb ApplicationService oder eigenes L2-Subsystem; TraceabilityEngine liefert Matrix-Daten."
    },
    {
      "need_id": "REQ-L0-007",
      "issue": "Open Point OP-01: LLM-Capability-Scope (welche der 4 Capabilities in v1 operativ?) ist pending.",
      "recommendation": "Entscheidung vor L2-Verfeinerung: Empfehlung aus KONZEPT.md ist Validierung + Decomposition. LlmAdapter.CapabilityRegistry unterstützt selektive Aktivierung."
    },
    {
      "need_id": "REQ-L0-002",
      "issue": "Performance-Observability (<200ms/<500ms) ist als NF-Anforderung spezifiziert, aber kein dediziertes Monitoring-Subsystem in L1 definiert.",
      "recommendation": "Observability (Logging, Metrics, Tracing) als Querschnittsaspekt in L2 oder L3 ergänzen."
    }
  ],
  "over_engineering": [],
  "validation_verdict": "APPROVED_WITH_WARNINGS",
  "rationale": "Alle 13 Must-Have Stakeholder-Needs (REQ-L0-001..013) sind durch mindestens eine vollständige User-Journey auf L1-Ebene abgedeckt. Zwei Should-Have Needs (REQ-L0-014, REQ-L0-015) sind mit niedrigerer Priorität erfasst und blockieren nicht. Drei offene Design-Punkte (OP-01..03) betreffen Implementierungsdetails, keine L1-Systemstruktur."
}
```

---

*Erstellt durch se-validator-Agent | ReqFlow SE-Kaskade | 2026-06-20*  
*Nächster Schritt: L2-Architektur-Verfeinerung für alle 12 Subsysteme (Parallelisierung möglich).*
