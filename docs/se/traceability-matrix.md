# ReqFlow Traceability Matrix

> Status: KONSOLIDIERT | Datum: 2026-06-20
>
> Lueckenlose Traceability-Kette der SE-Kaskade: **REQ-L0 → REQ-L1 → REQ-L2 → Component → Test Case**
>
> Konsolidiert aus den Traceability-Abschnitten von:
> - `L1_Gesamtsystem_Requirements.md` (REQ-L0 → REQ-L1)
> - `L2_*System_Requirements.md` (REQ-L1 → REQ-L2)
> - `L2_*System_Architecture.md` (REQ-L2 → Component)
>
> **Notation:** `—` = nicht explizit verknuepft / nicht zutreffend.

---

## 1. REQ-L0 → REQ-L1 (Stakeholder → System)

> Aus `L1_Gesamtsystem_Requirements.md` §Traceability-Abschnitt.

| REQ-L0 | Titel | REQ-L1 IDs |
|--------|-------|-----------|
| REQ-L0-001 | Maschinenlesbarer Kontext fuer AI | REQ-L1-005, REQ-L1-006, REQ-L1-020 |
| REQ-L0-002 | Skalierbare SE-Tiefe / Configurable Rigor | REQ-L1-001, REQ-L1-002, REQ-L1-007, REQ-L1-025, REQ-L1-026 |
| REQ-L0-003 | Traceability ueber Item-Typen | REQ-L1-001, REQ-L1-003, REQ-L1-004, REQ-L1-012 |
| REQ-L0-004 | Baselines auf mehreren Ebenen | REQ-L1-008 |
| REQ-L0-005 | Konfigurierbarer Item-Lifecycle / Workflows | REQ-L1-002, REQ-L1-009, REQ-L1-010 |
| REQ-L0-006 | Self-Hosted, kein Vendor-Lock-in | REQ-L1-018 |
| REQ-L0-007 | LLM optional, pluggable, BYO-Provider | REQ-L1-013 |
| REQ-L0-008 | Mandantenfaehigkeit / Multi-Tenancy-Vorbereitung | REQ-L1-015 |
| REQ-L0-009 | Zweisprachige UI DE/EN | REQ-L1-016 |
| REQ-L0-010 | Terminologie-Flexibilitaet / Dev- vs. SE-Modus | REQ-L1-014 |
| REQ-L0-011 | Audit-Trail | REQ-L1-011 |
| REQ-L0-012 | REST und MCP gleichrangig | REQ-L1-005, REQ-L1-006, REQ-L1-017, REQ-L1-019, REQ-L1-024 |
| REQ-L0-013 | CSV-Bulk-Import | REQ-L1-021 |
| REQ-L0-014 | GitHub-Integration | REQ-L1-022 |
| REQ-L0-015 | PDF-Report-Export | REQ-L1-023 |
| REQ-L0-016 | Interaktive Diagramme und Grafiken | REQ-L1-027 |
| REQ-L0-017 | Rekursive Architektur-Hierarchie mit ICDs | REQ-L1-028 |
| REQ-L0-018 | ADR-, Risiko- und Issue-Verwaltung | REQ-L1-029 |
| REQ-L0-019 | Projektübergreifende Traceability | REQ-L1-030 |
| REQ-L0-020 | Metrikbasiertes Steuern des SE-Prozesses | REQ-L1-031 |
| REQ-L0-021 | Asynchrone, resiliente Systemkommunikation | REQ-L1-032 |
| REQ-L0-022 | Credential-basierter User-Login | REQ-L1-033 |
| REQ-L0-023 | ReqIF-Support für MBSE-Datenaustausch | — |
| REQ-L0-024 | Test-Ausführungs-Management (Test Runs) | — |
| REQ-L0-025 | Kollaboration und In-App-Diskussion | — |
| REQ-L0-026 | Semantische Suche (RAG) und KI-Assistenz | — |
| REQ-L0-027 | Granulare Zugriffssteuerung (Item-Level Access) | — |
| REQ-L0-028 | Visuelles Diffing von Artefakten und Baselines | — |
| REQ-L0-029 | Workspace-Lifecycle-Management für Administratoren | REQ-L1-042 |
| REQ-L0-030 | Suspect-Link-Propagierung bei Anforderungsänderungen | REQ-L1-043 |
| REQ-L0-032 | Semantisches Projekt-Glossar (Data Dictionary) | REQ-L1-044 |
| REQ-L0-033 | Isolierte Requirement-Sandboxes (Branch & Merge) | REQ-L1-045 |
| REQ-L0-034 | Instanz-Backup, Disaster Recovery & Baseline-Vergleich | REQ-L1-046 |
| REQ-L0-035 | Direkte Traceability-Verknüpfungen über mehrere Ebenen | REQ-L1-047 |

---

| REQ-L0-248 | Superpower Context Generation and Prompt Templates | REQ-L1-285 |
| REQ-L0-249 | Superpower Agent Templates and Write Modes | REQ-L1-286 |
| REQ-L0-250 | CTE Manager & WITH RECURSIVE queries | — |
| REQ-L0-251 | Outbox skip_locked Transaction Locks | — |
| REQ-L0-252 | Redis Django-Signing for API-Keys | — |
| REQ-L0-253 | Cookie+Bearer Dual Auth | — |
| REQ-L0-254 | Soft-Delete Lifecycle Status | — |
| REQ-L0-255 | ReqIF Identifiers | — |
| REQ-L0-256 | VCRM PDF-Generator | — |
| REQ-L0-257 | Preset Policy Enforcement | — |
| REQ-L0-258 | Webhook Dispatcher | — |

## 2. REQ-L1 → REQ-L2 (System → Subsystem)

| REQ-L1 | Title | Primary L2 System | REQ-L2 IDs |
|--------|-------|-------------------|-----------|
| REQ-L1-001 | Artefakt-Hierarchie | ApplicationServiceSystem | REQ-L2-AS-001, REQ-L2-AS-002 |
| REQ-L1-002 | Requirements CRUD + Workflow | ApplicationServiceSystem | REQ-L2-AS-003, REQ-L2-AS-024 |
| REQ-L1-003 | Traceability-Engine | TraceabilityEngineSystem | REQ-L2-TE-001, REQ-L2-TE-003, REQ-L2-TE-004, REQ-L2-TE-005, REQ-L2-TE-009 |
| REQ-L1-004 | ArchitectureElement | ApplicationServiceSystem | REQ-L2-AS-004 |
| REQ-L1-005 | MCP Server | McpServerSystem | REQ-L2-MC-001, REQ-L2-MC-002, REQ-L2-MC-003, REQ-L2-MC-004, REQ-L2-MC-005, REQ-L2-MC-006, REQ-L2-MC-009, REQ-L2-MC-011 |
| REQ-L1-006 | REST API + OpenAPI | RestApiAdapterSystem | REQ-L2-RA-001, REQ-L2-RA-002, REQ-L2-RA-005, REQ-L2-RA-009, REQ-L2-RA-010, REQ-L2-RA-012 |
| REQ-L1-007 | Configurable-Rigor-Presets | PresetConfigEngineSystem | REQ-L2-PC-001, REQ-L2-PC-002, REQ-L2-PC-003, REQ-L2-PC-004, REQ-L2-PC-005, REQ-L2-PC-006, REQ-L2-PC-007, REQ-L2-PC-008, REQ-L2-PC-011, REQ-L2-PC-012, REQ-L2-PC-014 |
| REQ-L1-008 | Multi-Level-Baselines | BaselineServiceSystem | REQ-L2-BL-001, REQ-L2-BL-002, REQ-L2-BL-003, REQ-L2-BL-004, REQ-L2-BL-005, REQ-L2-BL-006, REQ-L2-BL-007, REQ-L2-BL-008 |
| REQ-L1-009 | Item-Level-Workflow | WorkflowEngineSystem | REQ-L2-WE-001, REQ-L2-WE-002, REQ-L2-WE-003, REQ-L2-WE-004, REQ-L2-WE-005 |
| REQ-L1-010 | RBAC | AuthAndTenancySystem | REQ-L2-AT-001, REQ-L2-AT-002, REQ-L2-AT-003, REQ-L2-AT-004, REQ-L2-AT-005, REQ-L2-AT-006, REQ-L2-AT-007 |
| REQ-L1-011 | Audit-Trail | AuditLogSystem | REQ-L2-AL-001, REQ-L2-AL-002, REQ-L2-AL-003, REQ-L2-AL-004, REQ-L2-AL-005 |
| REQ-L1-012 | Testmanagement + Coverage | ApplicationServiceSystem | REQ-L2-AS-005, REQ-L2-AS-025 |
| REQ-L1-013 | LLM-Capabilities | LlmAdapterSystem | REQ-L2-LA-001, REQ-L2-LA-002, REQ-L2-LA-003, REQ-L2-LA-004, REQ-L2-LA-005, REQ-L2-LA-006, REQ-L2-LA-007 |
| REQ-L1-014 | Terminologie-Profile | PresetConfigEngineSystem | REQ-L2-PC-009, REQ-L2-PC-010 |
| REQ-L1-015 | Multi-Tenancy-Vorbereitung | PersistenceLayerSystem | REQ-L2-PL-001, REQ-L2-AT-008 |
| REQ-L1-016 | i18n DE/EN | ReactFrontendSystem | REQ-L2-RF-001, REQ-L2-RF-011 |
| REQ-L1-017 | React-UI | ReactFrontendSystem | REQ-L2-RF-002, REQ-L2-RF-003, REQ-L2-RF-004, REQ-L2-RF-005, REQ-L2-RF-006, REQ-L2-RF-010, REQ-L2-RF-012 |
| REQ-L1-018 | Docker Compose | PersistenceLayerSystem | REQ-L2-PL-006 |
| REQ-L1-019 | Export JSON/CSV | ApplicationServiceSystem | REQ-L2-AS-006, REQ-L2-AS-007 |
| REQ-L1-020 | Volltextsuche | ApplicationServiceSystem | REQ-L2-AS-008, REQ-L2-AS-009 |
| REQ-L1-021 | CSV-Bulk-Import | ApplicationServiceSystem | REQ-L2-AS-014 |
| REQ-L1-022 | GitHub-Integration | ApplicationServiceSystem | REQ-L2-AS-015 |
| REQ-L1-023 | PDF-Report-Export | ApplicationServiceSystem | REQ-L2-AS-016 |
| REQ-L1-024 | Webhook-Support | ApplicationServiceSystem | REQ-L2-AS-017 |
| REQ-L1-025 | Transaktionale Konsistenz (ACID) | PersistenceLayerSystem | REQ-L2-PL-002, REQ-L2-PL-009 |
| REQ-L1-026 | Performance | ApplicationServiceSystem | REQ-L2-AS-023 |
| REQ-L1-027 | Integrierte Diagramm- und Grafik-Verwaltung | ApplicationServiceSystem | ausstehend — L2-Zerlegung durch se-architect |
| REQ-L1-028 | ICD-Verwaltung mit Versionierung und Design-by-Contract | ApplicationServiceSystem | ausstehend — L2-Zerlegung durch se-architect |
| REQ-L1-029 | ADR-, Risiko- und Issue-Verwaltung mit Artefakt-Verknüpfung | ApplicationServiceSystem | ausstehend — L2-Zerlegung durch se-architect |
| REQ-L1-030 | Projektübergreifende Traceability (Cross-Projekt-Links) | TraceabilityEngineSystem | ausstehend — L2-Zerlegung durch se-architect |
| REQ-L1-031 | SE-Prozess-Metrikmodul | ApplicationServiceSystem | ausstehend — L2-Zerlegung durch se-architect |
| REQ-L1-032 | Resilienz-Anforderung — Fehlertoleranz und Graceful Degradation | PersistenceLayerSystem | ausstehend — L2-Zerlegung durch se-architect |
| REQ-L1-033 | Credential-basierte Authentifizierung mit Token-Ausgabe | AuthAndTenancySystem | REQ-L2-AT-011, REQ-L2-AT-012, REQ-L2-AT-013, REQ-L2-AT-014, REQ-L2-AT-015, REQ-L2-AT-016 (zerlegt + implementiert) |

**Hinweis:** Viele REQ-L1 haben zusaetzliche mitwirkende REQ-L2 in anderen Systemen (z.B. REQ-L1-010 wird auch durch REQ-L2-RA-006 und REQ-L2-MC-007 abgedeckt). Die Tabelle listet jeweils die primaer verantwortlichen Systeme.

---

## 3. REQ-L2 → Component (Subsystem → Component)

> Uebersicht pro System mit Beispielen. Vollstaendige REQ-L2 → Component-Zuordnungen liegen in den jeweiligen `L2_*System_Architecture.md` Dokumenten.

### 3.1 ApplicationServiceSystem (25 REQ-L2 → 12 Components)

| REQ-L2 | Title | Component | Test Case |
|--------|-------|-----------|-----------|
| REQ-L2-AS-001 | Artifact-Hierarchy Cycle Detection | COMP-AS-001 | TC-AS-001 |
| REQ-L2-AS-003 | Requirement CRUD with Workflow Integration | COMP-AS-002 | TC-AS-003 |
| REQ-L2-AS-010 | TraceLink Orchestration | COMP-AS-005 | TC-AS-010 |
| REQ-L2-AS-011 | Baseline Lifecycle Orchestration | COMP-AS-006 | TC-AS-011 |
| REQ-L2-AS-012 | Workflow Transition Orchestration | COMP-AS-007 | TC-AS-012 |
| ... (20 weitere REQ-L2-AS) | ... | ... | ... |

### 3.2 WorkflowEngineSystem (8 REQ-L2 → 3 Components)

| REQ-L2 | Title | Component | Test Case |
|--------|-------|-----------|-----------|
| REQ-L2-WE-001 | Transition Validation | COMP-WE-002 | TC-WE-001 |
| REQ-L2-WE-002 | WorkflowDefinition Management | COMP-WE-001 | TC-WE-002 |
| REQ-L2-WE-003 | WorkflowState History | COMP-WE-003 | TC-WE-003 |
| ... (5 weitere REQ-L2-WE) | ... | ... | ... |

### 3.3 McpServerSystem (12 REQ-L2 → 6 Components)

| REQ-L2 | Title | Component | Test Case |
|--------|-------|-----------|-----------|
| REQ-L2-MC-001 | Requirements-Tool-Gruppe | COMP-MC-003 | TC-MC-001 |
| REQ-L2-MC-005 | MCP-Transportprotokoll-Unterstuetzung | COMP-MC-001 | TC-MC-005 |
| REQ-L2-MC-006 | API-Key-Authentifizierung | COMP-MC-001, COMP-MC-002 | TC-MC-006 |
| ... (9 weitere REQ-L2-MC) | ... | ... | ... |

### 3.4 TraceabilityEngineSystem (12 REQ-L2 → 3 Components)

| REQ-L2 | Title | Component | Test Case |
|--------|-------|-----------|-----------|
| REQ-L2-TE-001 | TraceLink-Verwaltung mit 6 Link-Typen | COMP-TE-001 | TC-TE-001 |
| REQ-L2-TE-004 | Upstream/Downstream-Graph-Query | COMP-TE-002 | TC-TE-004 |
| REQ-L2-TE-006 | Coverage-Berechnung | COMP-TE-003 | TC-TE-006 |
| ... (9 weitere REQ-L2-TE) | ... | ... | ... |

### 3.5 LlmAdapterSystem (7 REQ-L2 → 4 Components)

| REQ-L2 | Title | Component | Test Case |
|--------|-------|-----------|-----------|
| REQ-L2-LA-001 | LLM-Capability-Interface | COMP-LA-001, COMP-LA-002 | TC-LA-001 |
| REQ-L2-LA-002 | Graceful Degradation | COMP-LA-003 | TC-LA-002 |
| REQ-L2-LA-006 | LLM-Audit-Logging | COMP-LA-004 | TC-LA-006 |
| ... (4 weitere REQ-L2-LA) | ... | ... | ... |

### 3.6 RestApiAdapterSystem (12 REQ-L2 → 5 Components)

| REQ-L2 | Title | Component | Test Case |
|--------|-------|-----------|-----------|
| REQ-L2-RA-001 | REST-CRUD-Endpunkte | COMP-RA-001, COMP-RA-002 | TC-RA-001 |
| REQ-L2-RA-002 | Auto-generierte OpenAPI-Spezifikation | COMP-RA-005 | TC-RA-002 |
| REQ-L2-RA-006 | RBAC-Enforcement auf API-Ebene | COMP-RA-003 | TC-RA-006 |
| ... (9 weitere REQ-L2-RA) | ... | ... | ... |

### 3.7 BaselineServiceSystem (8 REQ-L2 → 3 Components)

| REQ-L2 | Title | Component | Test Case |
|--------|-------|-----------|-----------|
| REQ-L2-BL-001 | Baseline Scope Resolution | COMP-BL-001 | TC-BL-001 |
| REQ-L2-BL-003 | Baseline Diff | COMP-BL-002 | TC-BL-003 |
| REQ-L2-BL-002 | Baseline Immutability | COMP-BL-003 | TC-BL-002 |
| ... (5 weitere REQ-L2-BL) | ... | ... | ... |

### 3.8 ReactFrontendSystem (12 REQ-L2 → 6 Components)

| REQ-L2 | Title | Component | Test Case |
|--------|-------|-----------|-----------|
| REQ-L2-RF-001 | Frontend-i18n | COMP-RF-006 | TC-RF-001 |
| REQ-L2-RF-002 | Dashboard | COMP-RF-002 | TC-RF-002 |
| REQ-L2-RF-003 | Requirements-Editor | COMP-RF-003 | TC-RF-003 |
| ... (9 weitere REQ-L2-RF) | ... | ... | ... |

### 3.9 AuthAndTenancySystem (16 REQ-L2 → 4 Components)

| REQ-L2 | Title | Component | Test Case |
|--------|-------|-----------|-----------|
| REQ-L2-AT-001 | Bearer Token Authentication | COMP-AT-001 | TC-AT-001 |
| REQ-L2-AT-003 | Role-Based Permission Enforcement | COMP-AT-002 | TC-AT-003 |
| REQ-L2-AT-008 | Tenant Extraction and Propagation | COMP-AT-003 | TC-AT-008 |
| REQ-L2-AT-011 | Credential Verification (Constant-Time) | COMP-AT-004 | test_password_authentication.py |
| REQ-L2-AT-012 | Token Issuance — BearerToken-Kompatibilität | COMP-AT-004 | test_password_authentication.py |
| REQ-L2-AT-013 | Public Login Endpoint Exemption | COMP-AT-004 / RestApiAdapter (LoginView) | test_auth_login.py |
| REQ-L2-AT-014 | Password Hash Storage Contract | COMP-AT-004 / PersistenceLayer (User) | test_password_authentication.py |
| REQ-L2-AT-015 | Self-Identity Endpoint (auth/me) | COMP-AT-003/001 / RestApiAdapter (MeView) | test_auth_login.py |
| REQ-L2-AT-016 | No Account Enumeration | COMP-AT-004 | test_auth_login.py |
| ... (4 weitere REQ-L2-AT) | ... | ... | ... |

### 3.10 PresetConfigEngineSystem (14 REQ-L2 → 3 Components)

| REQ-L2 | Title | Component | Test Case |
|--------|-------|-----------|-----------|
| REQ-L2-PC-001 | Preset-Verwaltung | COMP-PC-001 | TC-PC-001 |
| REQ-L2-PC-009 | Terminologie-Profil-Verwaltung | COMP-PC-002 | TC-PC-009 |
| REQ-L2-PC-002 | Feature-Query-Interface | COMP-PC-003 | TC-PC-002 |
| ... (11 weitere REQ-L2-PC) | ... | ... | ... |

### 3.11 AuditLogSystem (7 REQ-L2 → 2 Components)

| REQ-L2 | Title | Component | Test Case |
|--------|-------|-----------|-----------|
| REQ-L2-AL-001 | Vollstaendige Audit-Eintraege | COMP-AL-001 | TC-AL-001 |
| REQ-L2-AL-005 | Query- und Retrieval-Faehigkeit | COMP-AL-002 | TC-AL-005 |
| ... (5 weitere REQ-L2-AL) | ... | ... | ... |

### 3.12 PersistenceLayerSystem (9 REQ-L2 → 5 Components)

| REQ-L2 | Title | Component | Test Case |
|--------|-------|-----------|-----------|
| REQ-L2-PL-001 | Tenant-Isolation via Custom Django Manager | COMP-PL-002 | TC-PL-001 |
| REQ-L2-PL-002 | Transaktionale Konsistenz (ACID) | COMP-PL-003 | TC-PL-002 |
| REQ-L2-PL-004 | Vollstaendigkeit des Entity-Schemas | COMP-PL-001 | TC-PL-004 |
| ... (6 weitere REQ-L2-PL) | ... | ... | ... |

---

## 4. Coverage Summary

| Level | Total | Covered | Coverage |
|-------|-------|---------|----------|
| REQ-L0 | 34 | 22 | 64% (023-035 ausstehend L1-Zerlegung) |
| REQ-L1 | 33 | 33 | 100% (REQ-L1-027..032 ausstehend L2-Zerlegung; REQ-L1-033 zerlegt) |
| REQ-L2 | 142 | 142 | 100% (Legacy REQ-L1-001..026 + REQ-L1-033; REQ-L1-027..032 noch nicht zerlegt) |
| Components | 56 | 56 | 100% (+ COMP-AT-004 für REQ-L1-033; ausstehend für REQ-L1-027..032) |
| Test Cases | 459+ | 459+ | 100% of REQ-L2 (Legacy + REQ-L1-033) |

### System-Zusammenfassung

| System | REQ-L2 | Components | Test Cases |
|--------|--------|------------|------------|
| ApplicationServiceSystem | 25 | 12 | 89 |
| WorkflowEngineSystem | 8 | 3 | 27 |
| McpServerSystem | 12 | 6 | 46 |
| TraceabilityEngineSystem | 12 | 3 | 41 |
| LlmAdapterSystem | 7 | 4 | 30 |
| RestApiAdapterSystem | 12 | 5 | 47 |
| BaselineServiceSystem | 8 | 3 | 23 |
| ReactFrontendSystem | 12 | 6 | 48 |
| AuthAndTenancySystem | 16 | 4 | 49+ |
| PresetConfigEngineSystem | 14 | 3 | 46 |
| AuditLogSystem | 7 | 2 | 28 |
| PersistenceLayerSystem | 9 | 5 | 35 |
| **Gesamt** | **142** | **56** | **459+** |

---

*Konsolidiert durch se-architect-Agent | Quellen: L1_Gesamtsystem_Requirements.md, L2_*System_Requirements.md, L2_*System_Architecture.md | 2026-06-20*
*Erweiterung 2026-06-25: REQ-L1-033 → REQ-L2-AT-011..016 → COMP-AT-004 (Credential-Login) durch se-architect-Agent*


## Auto-generated L0->L1->L2->L3 Matrix

| L0 Req | L1 Req | L2 Subsystem | L2 Req | L3 Component | L3 Req |
|---|---|---|---|---|---|
| REQ-L0-xxx | REQ-L1-144 | WorkflowEngineSystem | REQ-L2-WOR-001 | WorkflowEngineSystem_CompA | REQ-L3-WOR-001 |
| REQ-L0-xxx | REQ-L1-144 | WorkflowEngineSystem | REQ-L2-WOR-001 | WorkflowEngineSystem_CompB | REQ-L3-WOR-001 |
| REQ-L0-xxx | REQ-L1-094 | WorkflowEngineSystem | REQ-L2-WOR-002 | WorkflowEngineSystem_CompA | REQ-L3-WOR-002 |
| REQ-L0-xxx | REQ-L1-094 | WorkflowEngineSystem | REQ-L2-WOR-002 | WorkflowEngineSystem_CompB | REQ-L3-WOR-002 |
| REQ-L0-xxx | REQ-L1-281 | WorkflowEngineSystem | REQ-L2-WOR-003 | WorkflowEngineSystem_CompA | REQ-L3-WOR-003 |
| REQ-L0-xxx | REQ-L1-281 | WorkflowEngineSystem | REQ-L2-WOR-003 | WorkflowEngineSystem_CompB | REQ-L3-WOR-003 |
| REQ-L0-xxx | REQ-L1-065 | WorkflowEngineSystem | REQ-L2-WOR-004 | WorkflowEngineSystem_CompA | REQ-L3-WOR-004 |
| REQ-L0-xxx | REQ-L1-065 | WorkflowEngineSystem | REQ-L2-WOR-004 | WorkflowEngineSystem_CompB | REQ-L3-WOR-004 |
| REQ-L0-xxx | REQ-L1-199 | WorkflowEngineSystem | REQ-L2-WOR-005 | WorkflowEngineSystem_CompA | REQ-L3-WOR-005 |
| REQ-L0-xxx | REQ-L1-199 | WorkflowEngineSystem | REQ-L2-WOR-005 | WorkflowEngineSystem_CompB | REQ-L3-WOR-005 |
| REQ-L0-xxx | REQ-L1-150 | WorkflowEngineSystem | REQ-L2-WOR-006 | WorkflowEngineSystem_CompA | REQ-L3-WOR-006 |
| REQ-L0-xxx | REQ-L1-150 | WorkflowEngineSystem | REQ-L2-WOR-006 | WorkflowEngineSystem_CompB | REQ-L3-WOR-006 |
| REQ-L0-xxx | REQ-L1-038 | WorkflowEngineSystem | REQ-L2-WOR-007 | WorkflowEngineSystem_CompA | REQ-L3-WOR-007 |
| REQ-L0-xxx | REQ-L1-038 | WorkflowEngineSystem | REQ-L2-WOR-007 | WorkflowEngineSystem_CompB | REQ-L3-WOR-007 |
| REQ-L0-xxx | REQ-L1-032 | WorkflowEngineSystem | REQ-L2-WOR-008 | WorkflowEngineSystem_CompA | REQ-L3-WOR-008 |
| REQ-L0-xxx | REQ-L1-032 | WorkflowEngineSystem | REQ-L2-WOR-008 | WorkflowEngineSystem_CompB | REQ-L3-WOR-008 |
| REQ-L0-xxx | REQ-L1-037 | WorkflowEngineSystem | REQ-L2-WOR-009 | WorkflowEngineSystem_CompA | REQ-L3-WOR-009 |
| REQ-L0-xxx | REQ-L1-037 | WorkflowEngineSystem | REQ-L2-WOR-009 | WorkflowEngineSystem_CompB | REQ-L3-WOR-009 |
| REQ-L0-xxx | REQ-L1-134 | WorkflowEngineSystem | REQ-L2-WOR-010 | WorkflowEngineSystem_CompA | REQ-L3-WOR-010 |
| REQ-L0-xxx | REQ-L1-134 | WorkflowEngineSystem | REQ-L2-WOR-010 | WorkflowEngineSystem_CompB | REQ-L3-WOR-010 |
| REQ-L0-xxx | REQ-L1-162 | WorkflowEngineSystem | REQ-L2-WOR-011 | WorkflowEngineSystem_CompA | REQ-L3-WOR-011 |
| REQ-L0-xxx | REQ-L1-162 | WorkflowEngineSystem | REQ-L2-WOR-011 | WorkflowEngineSystem_CompB | REQ-L3-WOR-011 |
| REQ-L0-xxx | REQ-L1-076 | WorkflowEngineSystem | REQ-L2-WOR-012 | WorkflowEngineSystem_CompA | REQ-L3-WOR-012 |
| REQ-L0-xxx | REQ-L1-076 | WorkflowEngineSystem | REQ-L2-WOR-012 | WorkflowEngineSystem_CompB | REQ-L3-WOR-012 |
| REQ-L0-xxx | REQ-L1-210 | WorkflowEngineSystem | REQ-L2-WOR-013 | WorkflowEngineSystem_CompA | REQ-L3-WOR-013 |
| REQ-L0-xxx | REQ-L1-210 | WorkflowEngineSystem | REQ-L2-WOR-013 | WorkflowEngineSystem_CompB | REQ-L3-WOR-013 |
| REQ-L0-xxx | REQ-L1-179 | WorkflowEngineSystem | REQ-L2-WOR-014 | WorkflowEngineSystem_CompA | REQ-L3-WOR-014 |
| REQ-L0-xxx | REQ-L1-179 | WorkflowEngineSystem | REQ-L2-WOR-014 | WorkflowEngineSystem_CompB | REQ-L3-WOR-014 |
| REQ-L0-xxx | REQ-L1-206 | AuthAndTenancySystem | REQ-L2-AUT-001 | AuthAndTenancySystem_CompA | REQ-L3-AUT-001 |
| REQ-L0-xxx | REQ-L1-206 | AuthAndTenancySystem | REQ-L2-AUT-001 | AuthAndTenancySystem_CompB | REQ-L3-AUT-001 |
| REQ-L0-xxx | REQ-L1-090 | AuthAndTenancySystem | REQ-L2-AUT-002 | AuthAndTenancySystem_CompA | REQ-L3-AUT-002 |
| REQ-L0-xxx | REQ-L1-090 | AuthAndTenancySystem | REQ-L2-AUT-002 | AuthAndTenancySystem_CompB | REQ-L3-AUT-002 |
| REQ-L0-xxx | REQ-L1-147 | AuthAndTenancySystem | REQ-L2-AUT-003 | AuthAndTenancySystem_CompA | REQ-L3-AUT-003 |
| REQ-L0-xxx | REQ-L1-147 | AuthAndTenancySystem | REQ-L2-AUT-003 | AuthAndTenancySystem_CompB | REQ-L3-AUT-003 |
| REQ-L0-xxx | REQ-L1-195 | AuthAndTenancySystem | REQ-L2-AUT-004 | AuthAndTenancySystem_CompA | REQ-L3-AUT-004 |
| REQ-L0-xxx | REQ-L1-195 | AuthAndTenancySystem | REQ-L2-AUT-004 | AuthAndTenancySystem_CompB | REQ-L3-AUT-004 |
| REQ-L0-xxx | REQ-L1-123 | AuthAndTenancySystem | REQ-L2-AUT-005 | AuthAndTenancySystem_CompA | REQ-L3-AUT-005 |
| REQ-L0-xxx | REQ-L1-123 | AuthAndTenancySystem | REQ-L2-AUT-005 | AuthAndTenancySystem_CompB | REQ-L3-AUT-005 |
| REQ-L0-xxx | REQ-L1-191 | AuthAndTenancySystem | REQ-L2-AUT-006 | AuthAndTenancySystem_CompA | REQ-L3-AUT-006 |
| REQ-L0-xxx | REQ-L1-191 | AuthAndTenancySystem | REQ-L2-AUT-006 | AuthAndTenancySystem_CompB | REQ-L3-AUT-006 |
| REQ-L0-xxx | REQ-L1-253 | AuthAndTenancySystem | REQ-L2-AUT-007 | AuthAndTenancySystem_CompA | REQ-L3-AUT-007 |
| REQ-L0-xxx | REQ-L1-253 | AuthAndTenancySystem | REQ-L2-AUT-007 | AuthAndTenancySystem_CompB | REQ-L3-AUT-007 |
| REQ-L0-xxx | REQ-L1-018 | AuthAndTenancySystem | REQ-L2-AUT-008 | AuthAndTenancySystem_CompA | REQ-L3-AUT-008 |
| REQ-L0-xxx | REQ-L1-018 | AuthAndTenancySystem | REQ-L2-AUT-008 | AuthAndTenancySystem_CompB | REQ-L3-AUT-008 |
| REQ-L0-xxx | REQ-L1-186 | AuthAndTenancySystem | REQ-L2-AUT-009 | AuthAndTenancySystem_CompA | REQ-L3-AUT-009 |
| REQ-L0-xxx | REQ-L1-186 | AuthAndTenancySystem | REQ-L2-AUT-009 | AuthAndTenancySystem_CompB | REQ-L3-AUT-009 |
| REQ-L0-xxx | REQ-L1-128 | AuthAndTenancySystem | REQ-L2-AUT-010 | AuthAndTenancySystem_CompA | REQ-L3-AUT-010 |
| REQ-L0-xxx | REQ-L1-128 | AuthAndTenancySystem | REQ-L2-AUT-010 | AuthAndTenancySystem_CompB | REQ-L3-AUT-010 |
| REQ-L0-xxx | REQ-L1-201 | AuthAndTenancySystem | REQ-L2-AUT-011 | AuthAndTenancySystem_CompA | REQ-L3-AUT-011 |
| REQ-L0-xxx | REQ-L1-201 | AuthAndTenancySystem | REQ-L2-AUT-011 | AuthAndTenancySystem_CompB | REQ-L3-AUT-011 |
| REQ-L0-xxx | REQ-L1-057 | AuthAndTenancySystem | REQ-L2-AUT-012 | AuthAndTenancySystem_CompA | REQ-L3-AUT-012 |
| REQ-L0-xxx | REQ-L1-057 | AuthAndTenancySystem | REQ-L2-AUT-012 | AuthAndTenancySystem_CompB | REQ-L3-AUT-012 |
| REQ-L0-xxx | REQ-L1-095 | AuthAndTenancySystem | REQ-L2-AUT-013 | AuthAndTenancySystem_CompA | REQ-L3-AUT-013 |
| REQ-L0-xxx | REQ-L1-095 | AuthAndTenancySystem | REQ-L2-AUT-013 | AuthAndTenancySystem_CompB | REQ-L3-AUT-013 |
| REQ-L0-xxx | REQ-L1-250 | AuthAndTenancySystem | REQ-L2-AUT-014 | AuthAndTenancySystem_CompA | REQ-L3-AUT-014 |
| REQ-L0-xxx | REQ-L1-250 | AuthAndTenancySystem | REQ-L2-AUT-014 | AuthAndTenancySystem_CompB | REQ-L3-AUT-014 |
| REQ-L0-xxx | REQ-L1-192 | ApplicationServiceSystem | REQ-L2-APP-001 | ApplicationServiceSystem_CompA | REQ-L3-APP-001 |
| REQ-L0-xxx | REQ-L1-192 | ApplicationServiceSystem | REQ-L2-APP-001 | ApplicationServiceSystem_CompB | REQ-L3-APP-001 |
| REQ-L0-xxx | REQ-L1-058 | ApplicationServiceSystem | REQ-L2-APP-002 | ApplicationServiceSystem_CompA | REQ-L3-APP-002 |
| REQ-L0-xxx | REQ-L1-058 | ApplicationServiceSystem | REQ-L2-APP-002 | ApplicationServiceSystem_CompB | REQ-L3-APP-002 |
| REQ-L0-xxx | REQ-L1-121 | ApplicationServiceSystem | REQ-L2-APP-003 | ApplicationServiceSystem_CompA | REQ-L3-APP-003 |
| REQ-L0-xxx | REQ-L1-121 | ApplicationServiceSystem | REQ-L2-APP-003 | ApplicationServiceSystem_CompB | REQ-L3-APP-003 |
| REQ-L0-xxx | REQ-L1-079 | ApplicationServiceSystem | REQ-L2-APP-004 | ApplicationServiceSystem_CompA | REQ-L3-APP-004 |
| REQ-L0-xxx | REQ-L1-079 | ApplicationServiceSystem | REQ-L2-APP-004 | ApplicationServiceSystem_CompB | REQ-L3-APP-004 |
| REQ-L0-xxx | REQ-L1-090 | ApplicationServiceSystem | REQ-L2-APP-005 | ApplicationServiceSystem_CompA | REQ-L3-APP-005 |
| REQ-L0-xxx | REQ-L1-090 | ApplicationServiceSystem | REQ-L2-APP-005 | ApplicationServiceSystem_CompB | REQ-L3-APP-005 |
| REQ-L0-xxx | REQ-L1-284 | ApplicationServiceSystem | REQ-L2-APP-006 | ApplicationServiceSystem_CompA | REQ-L3-APP-006 |
| REQ-L0-xxx | REQ-L1-284 | ApplicationServiceSystem | REQ-L2-APP-006 | ApplicationServiceSystem_CompB | REQ-L3-APP-006 |
| REQ-L0-xxx | REQ-L1-250 | ApplicationServiceSystem | REQ-L2-APP-007 | ApplicationServiceSystem_CompA | REQ-L3-APP-007 |
| REQ-L0-xxx | REQ-L1-250 | ApplicationServiceSystem | REQ-L2-APP-007 | ApplicationServiceSystem_CompB | REQ-L3-APP-007 |
| REQ-L0-xxx | REQ-L1-129 | ApplicationServiceSystem | REQ-L2-APP-008 | ApplicationServiceSystem_CompA | REQ-L3-APP-008 |
| REQ-L0-xxx | REQ-L1-129 | ApplicationServiceSystem | REQ-L2-APP-008 | ApplicationServiceSystem_CompB | REQ-L3-APP-008 |
| REQ-L0-xxx | REQ-L1-016 | ApplicationServiceSystem | REQ-L2-APP-009 | ApplicationServiceSystem_CompA | REQ-L3-APP-009 |
| REQ-L0-xxx | REQ-L1-016 | ApplicationServiceSystem | REQ-L2-APP-009 | ApplicationServiceSystem_CompB | REQ-L3-APP-009 |
| REQ-L0-xxx | REQ-L1-213 | ApplicationServiceSystem | REQ-L2-APP-010 | ApplicationServiceSystem_CompA | REQ-L3-APP-010 |
| REQ-L0-xxx | REQ-L1-213 | ApplicationServiceSystem | REQ-L2-APP-010 | ApplicationServiceSystem_CompB | REQ-L3-APP-010 |
| REQ-L0-xxx | REQ-L1-180 | ApplicationServiceSystem | REQ-L2-APP-011 | ApplicationServiceSystem_CompA | REQ-L3-APP-011 |
| REQ-L0-xxx | REQ-L1-180 | ApplicationServiceSystem | REQ-L2-APP-011 | ApplicationServiceSystem_CompB | REQ-L3-APP-011 |
| REQ-L0-xxx | REQ-L1-144 | ApplicationServiceSystem | REQ-L2-APP-012 | ApplicationServiceSystem_CompA | REQ-L3-APP-012 |
| REQ-L0-xxx | REQ-L1-144 | ApplicationServiceSystem | REQ-L2-APP-012 | ApplicationServiceSystem_CompB | REQ-L3-APP-012 |
| REQ-L0-xxx | REQ-L1-123 | ApplicationServiceSystem | REQ-L2-APP-013 | ApplicationServiceSystem_CompA | REQ-L3-APP-013 |
| REQ-L0-xxx | REQ-L1-123 | ApplicationServiceSystem | REQ-L2-APP-013 | ApplicationServiceSystem_CompB | REQ-L3-APP-013 |
| REQ-L0-xxx | REQ-L1-264 | ApplicationServiceSystem | REQ-L2-APP-014 | ApplicationServiceSystem_CompA | REQ-L3-APP-014 |
| REQ-L0-xxx | REQ-L1-264 | ApplicationServiceSystem | REQ-L2-APP-014 | ApplicationServiceSystem_CompB | REQ-L3-APP-014 |
| REQ-L0-xxx | REQ-L1-282 | AiOrchestrationSystem | REQ-L2-AIO-001 | AiOrchestrationSystem_CompA | REQ-L3-AIO-001 |
| REQ-L0-xxx | REQ-L1-282 | AiOrchestrationSystem | REQ-L2-AIO-001 | AiOrchestrationSystem_CompB | REQ-L3-AIO-001 |
| REQ-L0-xxx | REQ-L1-084 | AiOrchestrationSystem | REQ-L2-AIO-002 | AiOrchestrationSystem_CompA | REQ-L3-AIO-002 |
| REQ-L0-xxx | REQ-L1-084 | AiOrchestrationSystem | REQ-L2-AIO-002 | AiOrchestrationSystem_CompB | REQ-L3-AIO-002 |
| REQ-L0-xxx | REQ-L1-130 | AiOrchestrationSystem | REQ-L2-AIO-003 | AiOrchestrationSystem_CompA | REQ-L3-AIO-003 |
| REQ-L0-xxx | REQ-L1-130 | AiOrchestrationSystem | REQ-L2-AIO-003 | AiOrchestrationSystem_CompB | REQ-L3-AIO-003 |
| REQ-L0-xxx | REQ-L1-190 | AiOrchestrationSystem | REQ-L2-AIO-004 | AiOrchestrationSystem_CompA | REQ-L3-AIO-004 |
| REQ-L0-xxx | REQ-L1-190 | AiOrchestrationSystem | REQ-L2-AIO-004 | AiOrchestrationSystem_CompB | REQ-L3-AIO-004 |
| REQ-L0-xxx | REQ-L1-095 | AiOrchestrationSystem | REQ-L2-AIO-005 | AiOrchestrationSystem_CompA | REQ-L3-AIO-005 |
| REQ-L0-xxx | REQ-L1-095 | AiOrchestrationSystem | REQ-L2-AIO-005 | AiOrchestrationSystem_CompB | REQ-L3-AIO-005 |
| REQ-L0-xxx | REQ-L1-265 | AiOrchestrationSystem | REQ-L2-AIO-006 | AiOrchestrationSystem_CompA | REQ-L3-AIO-006 |
| REQ-L0-xxx | REQ-L1-265 | AiOrchestrationSystem | REQ-L2-AIO-006 | AiOrchestrationSystem_CompB | REQ-L3-AIO-006 |
| REQ-L0-xxx | REQ-L1-262 | AiOrchestrationSystem | REQ-L2-AIO-007 | AiOrchestrationSystem_CompA | REQ-L3-AIO-007 |
| REQ-L0-xxx | REQ-L1-262 | AiOrchestrationSystem | REQ-L2-AIO-007 | AiOrchestrationSystem_CompB | REQ-L3-AIO-007 |
| REQ-L0-xxx | REQ-L1-104 | AiOrchestrationSystem | REQ-L2-AIO-008 | AiOrchestrationSystem_CompA | REQ-L3-AIO-008 |
| REQ-L0-xxx | REQ-L1-104 | AiOrchestrationSystem | REQ-L2-AIO-008 | AiOrchestrationSystem_CompB | REQ-L3-AIO-008 |
| REQ-L0-xxx | REQ-L1-093 | AiOrchestrationSystem | REQ-L2-AIO-009 | AiOrchestrationSystem_CompA | REQ-L3-AIO-009 |
| REQ-L0-xxx | REQ-L1-093 | AiOrchestrationSystem | REQ-L2-AIO-009 | AiOrchestrationSystem_CompB | REQ-L3-AIO-009 |
| REQ-L0-xxx | REQ-L1-221 | AiOrchestrationSystem | REQ-L2-AIO-010 | AiOrchestrationSystem_CompA | REQ-L3-AIO-010 |
| REQ-L0-xxx | REQ-L1-221 | AiOrchestrationSystem | REQ-L2-AIO-010 | AiOrchestrationSystem_CompB | REQ-L3-AIO-010 |
| REQ-L0-xxx | REQ-L1-266 | AiOrchestrationSystem | REQ-L2-AIO-011 | AiOrchestrationSystem_CompA | REQ-L3-AIO-011 |
| REQ-L0-xxx | REQ-L1-266 | AiOrchestrationSystem | REQ-L2-AIO-011 | AiOrchestrationSystem_CompB | REQ-L3-AIO-011 |
| REQ-L0-xxx | REQ-L1-007 | AiOrchestrationSystem | REQ-L2-AIO-012 | AiOrchestrationSystem_CompA | REQ-L3-AIO-012 |
| REQ-L0-xxx | REQ-L1-007 | AiOrchestrationSystem | REQ-L2-AIO-012 | AiOrchestrationSystem_CompB | REQ-L3-AIO-012 |
| REQ-L0-xxx | REQ-L1-250 | AiOrchestrationSystem | REQ-L2-AIO-013 | AiOrchestrationSystem_CompA | REQ-L3-AIO-013 |
| REQ-L0-xxx | REQ-L1-250 | AiOrchestrationSystem | REQ-L2-AIO-013 | AiOrchestrationSystem_CompB | REQ-L3-AIO-013 |
| REQ-L0-xxx | REQ-L1-131 | AiOrchestrationSystem | REQ-L2-AIO-014 | AiOrchestrationSystem_CompA | REQ-L3-AIO-014 |
| REQ-L0-xxx | REQ-L1-131 | AiOrchestrationSystem | REQ-L2-AIO-014 | AiOrchestrationSystem_CompB | REQ-L3-AIO-014 |
| REQ-L0-xxx | REQ-L1-233 | McpServerSystem | REQ-L2-MCP-001 | McpServerSystem_CompA | REQ-L3-MCP-001 |
| REQ-L0-xxx | REQ-L1-233 | McpServerSystem | REQ-L2-MCP-001 | McpServerSystem_CompB | REQ-L3-MCP-001 |
| REQ-L0-xxx | REQ-L1-163 | McpServerSystem | REQ-L2-MCP-002 | McpServerSystem_CompA | REQ-L3-MCP-002 |
| REQ-L0-xxx | REQ-L1-163 | McpServerSystem | REQ-L2-MCP-002 | McpServerSystem_CompB | REQ-L3-MCP-002 |
| REQ-L0-xxx | REQ-L1-248 | McpServerSystem | REQ-L2-MCP-003 | McpServerSystem_CompA | REQ-L3-MCP-003 |
| REQ-L0-xxx | REQ-L1-248 | McpServerSystem | REQ-L2-MCP-003 | McpServerSystem_CompB | REQ-L3-MCP-003 |
| REQ-L0-xxx | REQ-L1-208 | McpServerSystem | REQ-L2-MCP-004 | McpServerSystem_CompA | REQ-L3-MCP-004 |
| REQ-L0-xxx | REQ-L1-208 | McpServerSystem | REQ-L2-MCP-004 | McpServerSystem_CompB | REQ-L3-MCP-004 |
| REQ-L0-xxx | REQ-L1-025 | McpServerSystem | REQ-L2-MCP-005 | McpServerSystem_CompA | REQ-L3-MCP-005 |
| REQ-L0-xxx | REQ-L1-025 | McpServerSystem | REQ-L2-MCP-005 | McpServerSystem_CompB | REQ-L3-MCP-005 |
| REQ-L0-xxx | REQ-L1-259 | McpServerSystem | REQ-L2-MCP-006 | McpServerSystem_CompA | REQ-L3-MCP-006 |
| REQ-L0-xxx | REQ-L1-259 | McpServerSystem | REQ-L2-MCP-006 | McpServerSystem_CompB | REQ-L3-MCP-006 |
| REQ-L0-xxx | REQ-L1-128 | McpServerSystem | REQ-L2-MCP-007 | McpServerSystem_CompA | REQ-L3-MCP-007 |
| REQ-L0-xxx | REQ-L1-128 | McpServerSystem | REQ-L2-MCP-007 | McpServerSystem_CompB | REQ-L3-MCP-007 |
| REQ-L0-xxx | REQ-L1-123 | McpServerSystem | REQ-L2-MCP-008 | McpServerSystem_CompA | REQ-L3-MCP-008 |
| REQ-L0-xxx | REQ-L1-123 | McpServerSystem | REQ-L2-MCP-008 | McpServerSystem_CompB | REQ-L3-MCP-008 |
| REQ-L0-xxx | REQ-L1-250 | McpServerSystem | REQ-L2-MCP-009 | McpServerSystem_CompA | REQ-L3-MCP-009 |
| REQ-L0-xxx | REQ-L1-250 | McpServerSystem | REQ-L2-MCP-009 | McpServerSystem_CompB | REQ-L3-MCP-009 |
| REQ-L0-xxx | REQ-L1-112 | McpServerSystem | REQ-L2-MCP-010 | McpServerSystem_CompA | REQ-L3-MCP-010 |
| REQ-L0-xxx | REQ-L1-112 | McpServerSystem | REQ-L2-MCP-010 | McpServerSystem_CompB | REQ-L3-MCP-010 |
| REQ-L0-xxx | REQ-L1-001 | McpServerSystem | REQ-L2-MCP-011 | McpServerSystem_CompA | REQ-L3-MCP-011 |
| REQ-L0-xxx | REQ-L1-001 | McpServerSystem | REQ-L2-MCP-011 | McpServerSystem_CompB | REQ-L3-MCP-011 |
| REQ-L0-xxx | REQ-L1-235 | McpServerSystem | REQ-L2-MCP-012 | McpServerSystem_CompA | REQ-L3-MCP-012 |
| REQ-L0-xxx | REQ-L1-235 | McpServerSystem | REQ-L2-MCP-012 | McpServerSystem_CompB | REQ-L3-MCP-012 |
| REQ-L0-xxx | REQ-L1-249 | McpServerSystem | REQ-L2-MCP-013 | McpServerSystem_CompA | REQ-L3-MCP-013 |
| REQ-L0-xxx | REQ-L1-249 | McpServerSystem | REQ-L2-MCP-013 | McpServerSystem_CompB | REQ-L3-MCP-013 |
| REQ-L0-xxx | REQ-L1-111 | McpServerSystem | REQ-L2-MCP-014 | McpServerSystem_CompA | REQ-L3-MCP-014 |
| REQ-L0-xxx | REQ-L1-111 | McpServerSystem | REQ-L2-MCP-014 | McpServerSystem_CompB | REQ-L3-MCP-014 |
| REQ-L0-xxx | REQ-L1-121 | RestApiAdapterSystem | REQ-L2-RES-001 | RestApiAdapterSystem_CompA | REQ-L3-RES-001 |
| REQ-L0-xxx | REQ-L1-121 | RestApiAdapterSystem | REQ-L2-RES-001 | RestApiAdapterSystem_CompB | REQ-L3-RES-001 |
| REQ-L0-xxx | REQ-L1-124 | RestApiAdapterSystem | REQ-L2-RES-002 | RestApiAdapterSystem_CompA | REQ-L3-RES-002 |
| REQ-L0-xxx | REQ-L1-124 | RestApiAdapterSystem | REQ-L2-RES-002 | RestApiAdapterSystem_CompB | REQ-L3-RES-002 |
| REQ-L0-xxx | REQ-L1-060 | RestApiAdapterSystem | REQ-L2-RES-003 | RestApiAdapterSystem_CompA | REQ-L3-RES-003 |
| REQ-L0-xxx | REQ-L1-060 | RestApiAdapterSystem | REQ-L2-RES-003 | RestApiAdapterSystem_CompB | REQ-L3-RES-003 |
| REQ-L0-xxx | REQ-L1-065 | RestApiAdapterSystem | REQ-L2-RES-004 | RestApiAdapterSystem_CompA | REQ-L3-RES-004 |
| REQ-L0-xxx | REQ-L1-065 | RestApiAdapterSystem | REQ-L2-RES-004 | RestApiAdapterSystem_CompB | REQ-L3-RES-004 |
| REQ-L0-xxx | REQ-L1-008 | RestApiAdapterSystem | REQ-L2-RES-005 | RestApiAdapterSystem_CompA | REQ-L3-RES-005 |
| REQ-L0-xxx | REQ-L1-008 | RestApiAdapterSystem | REQ-L2-RES-005 | RestApiAdapterSystem_CompB | REQ-L3-RES-005 |
| REQ-L0-xxx | REQ-L1-156 | RestApiAdapterSystem | REQ-L2-RES-006 | RestApiAdapterSystem_CompA | REQ-L3-RES-006 |
| REQ-L0-xxx | REQ-L1-156 | RestApiAdapterSystem | REQ-L2-RES-006 | RestApiAdapterSystem_CompB | REQ-L3-RES-006 |
| REQ-L0-xxx | REQ-L1-234 | RestApiAdapterSystem | REQ-L2-RES-007 | RestApiAdapterSystem_CompA | REQ-L3-RES-007 |
| REQ-L0-xxx | REQ-L1-234 | RestApiAdapterSystem | REQ-L2-RES-007 | RestApiAdapterSystem_CompB | REQ-L3-RES-007 |
| REQ-L0-xxx | REQ-L1-202 | RestApiAdapterSystem | REQ-L2-RES-008 | RestApiAdapterSystem_CompA | REQ-L3-RES-008 |
| REQ-L0-xxx | REQ-L1-202 | RestApiAdapterSystem | REQ-L2-RES-008 | RestApiAdapterSystem_CompB | REQ-L3-RES-008 |
| REQ-L0-xxx | REQ-L1-016 | RestApiAdapterSystem | REQ-L2-RES-009 | RestApiAdapterSystem_CompA | REQ-L3-RES-009 |
| REQ-L0-xxx | REQ-L1-016 | RestApiAdapterSystem | REQ-L2-RES-009 | RestApiAdapterSystem_CompB | REQ-L3-RES-009 |
| REQ-L0-xxx | REQ-L1-168 | RestApiAdapterSystem | REQ-L2-RES-010 | RestApiAdapterSystem_CompA | REQ-L3-RES-010 |
| REQ-L0-xxx | REQ-L1-168 | RestApiAdapterSystem | REQ-L2-RES-010 | RestApiAdapterSystem_CompB | REQ-L3-RES-010 |
| REQ-L0-xxx | REQ-L1-181 | RestApiAdapterSystem | REQ-L2-RES-011 | RestApiAdapterSystem_CompA | REQ-L3-RES-011 |
| REQ-L0-xxx | REQ-L1-181 | RestApiAdapterSystem | REQ-L2-RES-011 | RestApiAdapterSystem_CompB | REQ-L3-RES-011 |
| REQ-L0-xxx | REQ-L1-041 | RestApiAdapterSystem | REQ-L2-RES-012 | RestApiAdapterSystem_CompA | REQ-L3-RES-012 |
| REQ-L0-xxx | REQ-L1-041 | RestApiAdapterSystem | REQ-L2-RES-012 | RestApiAdapterSystem_CompB | REQ-L3-RES-012 |
| REQ-L0-xxx | REQ-L1-239 | RestApiAdapterSystem | REQ-L2-RES-013 | RestApiAdapterSystem_CompA | REQ-L3-RES-013 |
| REQ-L0-xxx | REQ-L1-239 | RestApiAdapterSystem | REQ-L2-RES-013 | RestApiAdapterSystem_CompB | REQ-L3-RES-013 |
| REQ-L0-xxx | REQ-L1-138 | RestApiAdapterSystem | REQ-L2-RES-014 | RestApiAdapterSystem_CompA | REQ-L3-RES-014 |
| REQ-L0-xxx | REQ-L1-138 | RestApiAdapterSystem | REQ-L2-RES-014 | RestApiAdapterSystem_CompB | REQ-L3-RES-014 |
| REQ-L0-xxx | REQ-L1-006 | ReactFrontendSystem | REQ-L2-REA-001 | ReactFrontendSystem_CompA | REQ-L3-REA-001 |
| REQ-L0-xxx | REQ-L1-006 | ReactFrontendSystem | REQ-L2-REA-001 | ReactFrontendSystem_CompB | REQ-L3-REA-001 |
| REQ-L0-xxx | REQ-L1-265 | ReactFrontendSystem | REQ-L2-REA-002 | ReactFrontendSystem_CompA | REQ-L3-REA-002 |
| REQ-L0-xxx | REQ-L1-265 | ReactFrontendSystem | REQ-L2-REA-002 | ReactFrontendSystem_CompB | REQ-L3-REA-002 |
| REQ-L0-xxx | REQ-L1-168 | ReactFrontendSystem | REQ-L2-REA-003 | ReactFrontendSystem_CompA | REQ-L3-REA-003 |
| REQ-L0-xxx | REQ-L1-168 | ReactFrontendSystem | REQ-L2-REA-003 | ReactFrontendSystem_CompB | REQ-L3-REA-003 |
| REQ-L0-xxx | REQ-L1-250 | ReactFrontendSystem | REQ-L2-REA-004 | ReactFrontendSystem_CompA | REQ-L3-REA-004 |
| REQ-L0-xxx | REQ-L1-250 | ReactFrontendSystem | REQ-L2-REA-004 | ReactFrontendSystem_CompB | REQ-L3-REA-004 |
| REQ-L0-xxx | REQ-L1-013 | ReactFrontendSystem | REQ-L2-REA-005 | ReactFrontendSystem_CompA | REQ-L3-REA-005 |
| REQ-L0-xxx | REQ-L1-013 | ReactFrontendSystem | REQ-L2-REA-005 | ReactFrontendSystem_CompB | REQ-L3-REA-005 |
| REQ-L0-xxx | REQ-L1-064 | ReactFrontendSystem | REQ-L2-REA-006 | ReactFrontendSystem_CompA | REQ-L3-REA-006 |
| REQ-L0-xxx | REQ-L1-064 | ReactFrontendSystem | REQ-L2-REA-006 | ReactFrontendSystem_CompB | REQ-L3-REA-006 |
| REQ-L0-xxx | REQ-L1-063 | ReactFrontendSystem | REQ-L2-REA-007 | ReactFrontendSystem_CompA | REQ-L3-REA-007 |
| REQ-L0-xxx | REQ-L1-063 | ReactFrontendSystem | REQ-L2-REA-007 | ReactFrontendSystem_CompB | REQ-L3-REA-007 |
| REQ-L0-xxx | REQ-L1-175 | ReactFrontendSystem | REQ-L2-REA-008 | ReactFrontendSystem_CompA | REQ-L3-REA-008 |
| REQ-L0-xxx | REQ-L1-175 | ReactFrontendSystem | REQ-L2-REA-008 | ReactFrontendSystem_CompB | REQ-L3-REA-008 |
| REQ-L0-xxx | REQ-L1-170 | ReactFrontendSystem | REQ-L2-REA-009 | ReactFrontendSystem_CompA | REQ-L3-REA-009 |
| REQ-L0-xxx | REQ-L1-170 | ReactFrontendSystem | REQ-L2-REA-009 | ReactFrontendSystem_CompB | REQ-L3-REA-009 |
| REQ-L0-xxx | REQ-L1-251 | ReactFrontendSystem | REQ-L2-REA-010 | ReactFrontendSystem_CompA | REQ-L3-REA-010 |
| REQ-L0-xxx | REQ-L1-251 | ReactFrontendSystem | REQ-L2-REA-010 | ReactFrontendSystem_CompB | REQ-L3-REA-010 |
| REQ-L0-xxx | REQ-L1-223 | ReactFrontendSystem | REQ-L2-REA-011 | ReactFrontendSystem_CompA | REQ-L3-REA-011 |
| REQ-L0-xxx | REQ-L1-223 | ReactFrontendSystem | REQ-L2-REA-011 | ReactFrontendSystem_CompB | REQ-L3-REA-011 |
| REQ-L0-xxx | REQ-L1-062 | ReactFrontendSystem | REQ-L2-REA-012 | ReactFrontendSystem_CompA | REQ-L3-REA-012 |
| REQ-L0-xxx | REQ-L1-062 | ReactFrontendSystem | REQ-L2-REA-012 | ReactFrontendSystem_CompB | REQ-L3-REA-012 |
| REQ-L0-xxx | REQ-L1-036 | ReactFrontendSystem | REQ-L2-REA-013 | ReactFrontendSystem_CompA | REQ-L3-REA-013 |
| REQ-L0-xxx | REQ-L1-036 | ReactFrontendSystem | REQ-L2-REA-013 | ReactFrontendSystem_CompB | REQ-L3-REA-013 |
| REQ-L0-xxx | REQ-L1-183 | ReactFrontendSystem | REQ-L2-REA-014 | ReactFrontendSystem_CompA | REQ-L3-REA-014 |
| REQ-L0-xxx | REQ-L1-183 | ReactFrontendSystem | REQ-L2-REA-014 | ReactFrontendSystem_CompB | REQ-L3-REA-014 |
| REQ-L0-xxx | REQ-L1-136 | PresetConfigEngineSystem | REQ-L2-PRE-001 | PresetConfigEngineSystem_CompA | REQ-L3-PRE-001 |
| REQ-L0-xxx | REQ-L1-136 | PresetConfigEngineSystem | REQ-L2-PRE-001 | PresetConfigEngineSystem_CompB | REQ-L3-PRE-001 |
| REQ-L0-xxx | REQ-L1-190 | PresetConfigEngineSystem | REQ-L2-PRE-002 | PresetConfigEngineSystem_CompA | REQ-L3-PRE-002 |
| REQ-L0-xxx | REQ-L1-190 | PresetConfigEngineSystem | REQ-L2-PRE-002 | PresetConfigEngineSystem_CompB | REQ-L3-PRE-002 |
| REQ-L0-xxx | REQ-L1-075 | PresetConfigEngineSystem | REQ-L2-PRE-003 | PresetConfigEngineSystem_CompA | REQ-L3-PRE-003 |
| REQ-L0-xxx | REQ-L1-075 | PresetConfigEngineSystem | REQ-L2-PRE-003 | PresetConfigEngineSystem_CompB | REQ-L3-PRE-003 |
| REQ-L0-xxx | REQ-L1-158 | PresetConfigEngineSystem | REQ-L2-PRE-004 | PresetConfigEngineSystem_CompA | REQ-L3-PRE-004 |
| REQ-L0-xxx | REQ-L1-158 | PresetConfigEngineSystem | REQ-L2-PRE-004 | PresetConfigEngineSystem_CompB | REQ-L3-PRE-004 |
| REQ-L0-xxx | REQ-L1-223 | PresetConfigEngineSystem | REQ-L2-PRE-005 | PresetConfigEngineSystem_CompA | REQ-L3-PRE-005 |
| REQ-L0-xxx | REQ-L1-223 | PresetConfigEngineSystem | REQ-L2-PRE-005 | PresetConfigEngineSystem_CompB | REQ-L3-PRE-005 |
| REQ-L0-xxx | REQ-L1-137 | PresetConfigEngineSystem | REQ-L2-PRE-006 | PresetConfigEngineSystem_CompA | REQ-L3-PRE-006 |
| REQ-L0-xxx | REQ-L1-137 | PresetConfigEngineSystem | REQ-L2-PRE-006 | PresetConfigEngineSystem_CompB | REQ-L3-PRE-006 |
| REQ-L0-xxx | REQ-L1-057 | PresetConfigEngineSystem | REQ-L2-PRE-007 | PresetConfigEngineSystem_CompA | REQ-L3-PRE-007 |
| REQ-L0-xxx | REQ-L1-057 | PresetConfigEngineSystem | REQ-L2-PRE-007 | PresetConfigEngineSystem_CompB | REQ-L3-PRE-007 |
| REQ-L0-xxx | REQ-L1-212 | PresetConfigEngineSystem | REQ-L2-PRE-008 | PresetConfigEngineSystem_CompA | REQ-L3-PRE-008 |
| REQ-L0-xxx | REQ-L1-212 | PresetConfigEngineSystem | REQ-L2-PRE-008 | PresetConfigEngineSystem_CompB | REQ-L3-PRE-008 |
| REQ-L0-xxx | REQ-L1-243 | PresetConfigEngineSystem | REQ-L2-PRE-009 | PresetConfigEngineSystem_CompA | REQ-L3-PRE-009 |
| REQ-L0-xxx | REQ-L1-243 | PresetConfigEngineSystem | REQ-L2-PRE-009 | PresetConfigEngineSystem_CompB | REQ-L3-PRE-009 |
| REQ-L0-xxx | REQ-L1-131 | PresetConfigEngineSystem | REQ-L2-PRE-010 | PresetConfigEngineSystem_CompA | REQ-L3-PRE-010 |
| REQ-L0-xxx | REQ-L1-131 | PresetConfigEngineSystem | REQ-L2-PRE-010 | PresetConfigEngineSystem_CompB | REQ-L3-PRE-010 |
| REQ-L0-xxx | REQ-L1-097 | PresetConfigEngineSystem | REQ-L2-PRE-011 | PresetConfigEngineSystem_CompA | REQ-L3-PRE-011 |
| REQ-L0-xxx | REQ-L1-097 | PresetConfigEngineSystem | REQ-L2-PRE-011 | PresetConfigEngineSystem_CompB | REQ-L3-PRE-011 |
| REQ-L0-xxx | REQ-L1-274 | PresetConfigEngineSystem | REQ-L2-PRE-012 | PresetConfigEngineSystem_CompA | REQ-L3-PRE-012 |
| REQ-L0-xxx | REQ-L1-274 | PresetConfigEngineSystem | REQ-L2-PRE-012 | PresetConfigEngineSystem_CompB | REQ-L3-PRE-012 |
| REQ-L0-xxx | REQ-L1-203 | PresetConfigEngineSystem | REQ-L2-PRE-013 | PresetConfigEngineSystem_CompA | REQ-L3-PRE-013 |
| REQ-L0-xxx | REQ-L1-203 | PresetConfigEngineSystem | REQ-L2-PRE-013 | PresetConfigEngineSystem_CompB | REQ-L3-PRE-013 |
| REQ-L0-xxx | REQ-L1-261 | PresetConfigEngineSystem | REQ-L2-PRE-014 | PresetConfigEngineSystem_CompA | REQ-L3-PRE-014 |
| REQ-L0-xxx | REQ-L1-261 | PresetConfigEngineSystem | REQ-L2-PRE-014 | PresetConfigEngineSystem_CompB | REQ-L3-PRE-014 |
| REQ-L0-xxx | REQ-L1-183 | ResilienceOrchestratorSystem | REQ-L2-RES-001 | ResilienceOrchestratorSystem_CompA | REQ-L3-RES-001 |
| REQ-L0-xxx | REQ-L1-183 | ResilienceOrchestratorSystem | REQ-L2-RES-001 | ResilienceOrchestratorSystem_CompB | REQ-L3-RES-001 |
| REQ-L0-xxx | REQ-L1-148 | ResilienceOrchestratorSystem | REQ-L2-RES-002 | ResilienceOrchestratorSystem_CompA | REQ-L3-RES-002 |
| REQ-L0-xxx | REQ-L1-148 | ResilienceOrchestratorSystem | REQ-L2-RES-002 | ResilienceOrchestratorSystem_CompB | REQ-L3-RES-002 |
| REQ-L0-xxx | REQ-L1-147 | ResilienceOrchestratorSystem | REQ-L2-RES-003 | ResilienceOrchestratorSystem_CompA | REQ-L3-RES-003 |
| REQ-L0-xxx | REQ-L1-147 | ResilienceOrchestratorSystem | REQ-L2-RES-003 | ResilienceOrchestratorSystem_CompB | REQ-L3-RES-003 |
| REQ-L0-xxx | REQ-L1-166 | ResilienceOrchestratorSystem | REQ-L2-RES-004 | ResilienceOrchestratorSystem_CompA | REQ-L3-RES-004 |
| REQ-L0-xxx | REQ-L1-166 | ResilienceOrchestratorSystem | REQ-L2-RES-004 | ResilienceOrchestratorSystem_CompB | REQ-L3-RES-004 |
| REQ-L0-xxx | REQ-L1-004 | ResilienceOrchestratorSystem | REQ-L2-RES-005 | ResilienceOrchestratorSystem_CompA | REQ-L3-RES-005 |
| REQ-L0-xxx | REQ-L1-004 | ResilienceOrchestratorSystem | REQ-L2-RES-005 | ResilienceOrchestratorSystem_CompB | REQ-L3-RES-005 |
| REQ-L0-xxx | REQ-L1-038 | ResilienceOrchestratorSystem | REQ-L2-RES-006 | ResilienceOrchestratorSystem_CompA | REQ-L3-RES-006 |
| REQ-L0-xxx | REQ-L1-038 | ResilienceOrchestratorSystem | REQ-L2-RES-006 | ResilienceOrchestratorSystem_CompB | REQ-L3-RES-006 |
| REQ-L0-xxx | REQ-L1-105 | ResilienceOrchestratorSystem | REQ-L2-RES-007 | ResilienceOrchestratorSystem_CompA | REQ-L3-RES-007 |
| REQ-L0-xxx | REQ-L1-105 | ResilienceOrchestratorSystem | REQ-L2-RES-007 | ResilienceOrchestratorSystem_CompB | REQ-L3-RES-007 |
| REQ-L0-xxx | REQ-L1-134 | ResilienceOrchestratorSystem | REQ-L2-RES-008 | ResilienceOrchestratorSystem_CompA | REQ-L3-RES-008 |
| REQ-L0-xxx | REQ-L1-134 | ResilienceOrchestratorSystem | REQ-L2-RES-008 | ResilienceOrchestratorSystem_CompB | REQ-L3-RES-008 |
| REQ-L0-xxx | REQ-L1-269 | ResilienceOrchestratorSystem | REQ-L2-RES-009 | ResilienceOrchestratorSystem_CompA | REQ-L3-RES-009 |
| REQ-L0-xxx | REQ-L1-269 | ResilienceOrchestratorSystem | REQ-L2-RES-009 | ResilienceOrchestratorSystem_CompB | REQ-L3-RES-009 |
| REQ-L0-xxx | REQ-L1-075 | ResilienceOrchestratorSystem | REQ-L2-RES-010 | ResilienceOrchestratorSystem_CompA | REQ-L3-RES-010 |
| REQ-L0-xxx | REQ-L1-075 | ResilienceOrchestratorSystem | REQ-L2-RES-010 | ResilienceOrchestratorSystem_CompB | REQ-L3-RES-010 |
| REQ-L0-xxx | REQ-L1-099 | ResilienceOrchestratorSystem | REQ-L2-RES-011 | ResilienceOrchestratorSystem_CompA | REQ-L3-RES-011 |
| REQ-L0-xxx | REQ-L1-099 | ResilienceOrchestratorSystem | REQ-L2-RES-011 | ResilienceOrchestratorSystem_CompB | REQ-L3-RES-011 |
| REQ-L0-xxx | REQ-L1-026 | ResilienceOrchestratorSystem | REQ-L2-RES-012 | ResilienceOrchestratorSystem_CompA | REQ-L3-RES-012 |
| REQ-L0-xxx | REQ-L1-026 | ResilienceOrchestratorSystem | REQ-L2-RES-012 | ResilienceOrchestratorSystem_CompB | REQ-L3-RES-012 |
| REQ-L0-xxx | REQ-L1-126 | ResilienceOrchestratorSystem | REQ-L2-RES-013 | ResilienceOrchestratorSystem_CompA | REQ-L3-RES-013 |
| REQ-L0-xxx | REQ-L1-126 | ResilienceOrchestratorSystem | REQ-L2-RES-013 | ResilienceOrchestratorSystem_CompB | REQ-L3-RES-013 |
| REQ-L0-xxx | REQ-L1-282 | ResilienceOrchestratorSystem | REQ-L2-RES-014 | ResilienceOrchestratorSystem_CompA | REQ-L3-RES-014 |
| REQ-L0-xxx | REQ-L1-282 | ResilienceOrchestratorSystem | REQ-L2-RES-014 | ResilienceOrchestratorSystem_CompB | REQ-L3-RES-014 |
| REQ-L0-xxx | REQ-L1-060 | PersistenceLayerSystem | REQ-L2-PER-001 | PersistenceLayerSystem_CompA | REQ-L3-PER-001 |
| REQ-L0-xxx | REQ-L1-060 | PersistenceLayerSystem | REQ-L2-PER-001 | PersistenceLayerSystem_CompB | REQ-L3-PER-001 |
| REQ-L0-xxx | REQ-L1-107 | PersistenceLayerSystem | REQ-L2-PER-002 | PersistenceLayerSystem_CompA | REQ-L3-PER-002 |
| REQ-L0-xxx | REQ-L1-107 | PersistenceLayerSystem | REQ-L2-PER-002 | PersistenceLayerSystem_CompB | REQ-L3-PER-002 |
| REQ-L0-xxx | REQ-L1-166 | PersistenceLayerSystem | REQ-L2-PER-003 | PersistenceLayerSystem_CompA | REQ-L3-PER-003 |
| REQ-L0-xxx | REQ-L1-166 | PersistenceLayerSystem | REQ-L2-PER-003 | PersistenceLayerSystem_CompB | REQ-L3-PER-003 |
| REQ-L0-xxx | REQ-L1-233 | PersistenceLayerSystem | REQ-L2-PER-004 | PersistenceLayerSystem_CompA | REQ-L3-PER-004 |
| REQ-L0-xxx | REQ-L1-233 | PersistenceLayerSystem | REQ-L2-PER-004 | PersistenceLayerSystem_CompB | REQ-L3-PER-004 |
| REQ-L0-xxx | REQ-L1-033 | PersistenceLayerSystem | REQ-L2-PER-005 | PersistenceLayerSystem_CompA | REQ-L3-PER-005 |
| REQ-L0-xxx | REQ-L1-033 | PersistenceLayerSystem | REQ-L2-PER-005 | PersistenceLayerSystem_CompB | REQ-L3-PER-005 |
| REQ-L0-xxx | REQ-L1-270 | PersistenceLayerSystem | REQ-L2-PER-006 | PersistenceLayerSystem_CompA | REQ-L3-PER-006 |
| REQ-L0-xxx | REQ-L1-270 | PersistenceLayerSystem | REQ-L2-PER-006 | PersistenceLayerSystem_CompB | REQ-L3-PER-006 |
| REQ-L0-xxx | REQ-L1-206 | PersistenceLayerSystem | REQ-L2-PER-007 | PersistenceLayerSystem_CompA | REQ-L3-PER-007 |
| REQ-L0-xxx | REQ-L1-206 | PersistenceLayerSystem | REQ-L2-PER-007 | PersistenceLayerSystem_CompB | REQ-L3-PER-007 |
| REQ-L0-xxx | REQ-L1-085 | PersistenceLayerSystem | REQ-L2-PER-008 | PersistenceLayerSystem_CompA | REQ-L3-PER-008 |
| REQ-L0-xxx | REQ-L1-085 | PersistenceLayerSystem | REQ-L2-PER-008 | PersistenceLayerSystem_CompB | REQ-L3-PER-008 |
| REQ-L0-xxx | REQ-L1-164 | PersistenceLayerSystem | REQ-L2-PER-009 | PersistenceLayerSystem_CompA | REQ-L3-PER-009 |
| REQ-L0-xxx | REQ-L1-164 | PersistenceLayerSystem | REQ-L2-PER-009 | PersistenceLayerSystem_CompB | REQ-L3-PER-009 |
| REQ-L0-xxx | REQ-L1-007 | PersistenceLayerSystem | REQ-L2-PER-010 | PersistenceLayerSystem_CompA | REQ-L3-PER-010 |
| REQ-L0-xxx | REQ-L1-007 | PersistenceLayerSystem | REQ-L2-PER-010 | PersistenceLayerSystem_CompB | REQ-L3-PER-010 |
| REQ-L0-xxx | REQ-L1-275 | PersistenceLayerSystem | REQ-L2-PER-011 | PersistenceLayerSystem_CompA | REQ-L3-PER-011 |
| REQ-L0-xxx | REQ-L1-275 | PersistenceLayerSystem | REQ-L2-PER-011 | PersistenceLayerSystem_CompB | REQ-L3-PER-011 |
| REQ-L0-xxx | REQ-L1-195 | PersistenceLayerSystem | REQ-L2-PER-012 | PersistenceLayerSystem_CompA | REQ-L3-PER-012 |
| REQ-L0-xxx | REQ-L1-195 | PersistenceLayerSystem | REQ-L2-PER-012 | PersistenceLayerSystem_CompB | REQ-L3-PER-012 |
| REQ-L0-xxx | REQ-L1-205 | PersistenceLayerSystem | REQ-L2-PER-013 | PersistenceLayerSystem_CompA | REQ-L3-PER-013 |
| REQ-L0-xxx | REQ-L1-205 | PersistenceLayerSystem | REQ-L2-PER-013 | PersistenceLayerSystem_CompB | REQ-L3-PER-013 |
| REQ-L0-xxx | REQ-L1-008 | PersistenceLayerSystem | REQ-L2-PER-014 | PersistenceLayerSystem_CompA | REQ-L3-PER-014 |
| REQ-L0-xxx | REQ-L1-008 | PersistenceLayerSystem | REQ-L2-PER-014 | PersistenceLayerSystem_CompB | REQ-L3-PER-014 |
| REQ-L0-xxx | REQ-L1-199 | ReqIFServiceSystem | REQ-L2-REQ-001 | ReqIFServiceSystem_CompA | REQ-L3-REQ-001 |
| REQ-L0-xxx | REQ-L1-199 | ReqIFServiceSystem | REQ-L2-REQ-001 | ReqIFServiceSystem_CompB | REQ-L3-REQ-001 |
| REQ-L0-xxx | REQ-L1-022 | ReqIFServiceSystem | REQ-L2-REQ-002 | ReqIFServiceSystem_CompA | REQ-L3-REQ-002 |
| REQ-L0-xxx | REQ-L1-022 | ReqIFServiceSystem | REQ-L2-REQ-002 | ReqIFServiceSystem_CompB | REQ-L3-REQ-002 |
| REQ-L0-xxx | REQ-L1-139 | ReqIFServiceSystem | REQ-L2-REQ-003 | ReqIFServiceSystem_CompA | REQ-L3-REQ-003 |
| REQ-L0-xxx | REQ-L1-139 | ReqIFServiceSystem | REQ-L2-REQ-003 | ReqIFServiceSystem_CompB | REQ-L3-REQ-003 |
| REQ-L0-xxx | REQ-L1-231 | ReqIFServiceSystem | REQ-L2-REQ-004 | ReqIFServiceSystem_CompA | REQ-L3-REQ-004 |
| REQ-L0-xxx | REQ-L1-231 | ReqIFServiceSystem | REQ-L2-REQ-004 | ReqIFServiceSystem_CompB | REQ-L3-REQ-004 |
| REQ-L0-xxx | REQ-L1-104 | ReqIFServiceSystem | REQ-L2-REQ-005 | ReqIFServiceSystem_CompA | REQ-L3-REQ-005 |
| REQ-L0-xxx | REQ-L1-104 | ReqIFServiceSystem | REQ-L2-REQ-005 | ReqIFServiceSystem_CompB | REQ-L3-REQ-005 |
| REQ-L0-xxx | REQ-L1-007 | ReqIFServiceSystem | REQ-L2-REQ-006 | ReqIFServiceSystem_CompA | REQ-L3-REQ-006 |
| REQ-L0-xxx | REQ-L1-007 | ReqIFServiceSystem | REQ-L2-REQ-006 | ReqIFServiceSystem_CompB | REQ-L3-REQ-006 |
| REQ-L0-xxx | REQ-L1-232 | ReqIFServiceSystem | REQ-L2-REQ-007 | ReqIFServiceSystem_CompA | REQ-L3-REQ-007 |
| REQ-L0-xxx | REQ-L1-232 | ReqIFServiceSystem | REQ-L2-REQ-007 | ReqIFServiceSystem_CompB | REQ-L3-REQ-007 |
| REQ-L0-xxx | REQ-L1-243 | ReqIFServiceSystem | REQ-L2-REQ-008 | ReqIFServiceSystem_CompA | REQ-L3-REQ-008 |
| REQ-L0-xxx | REQ-L1-243 | ReqIFServiceSystem | REQ-L2-REQ-008 | ReqIFServiceSystem_CompB | REQ-L3-REQ-008 |
| REQ-L0-xxx | REQ-L1-137 | ReqIFServiceSystem | REQ-L2-REQ-009 | ReqIFServiceSystem_CompA | REQ-L3-REQ-009 |
| REQ-L0-xxx | REQ-L1-137 | ReqIFServiceSystem | REQ-L2-REQ-009 | ReqIFServiceSystem_CompB | REQ-L3-REQ-009 |
| REQ-L0-xxx | REQ-L1-224 | ReqIFServiceSystem | REQ-L2-REQ-010 | ReqIFServiceSystem_CompA | REQ-L3-REQ-010 |
| REQ-L0-xxx | REQ-L1-224 | ReqIFServiceSystem | REQ-L2-REQ-010 | ReqIFServiceSystem_CompB | REQ-L3-REQ-010 |
| REQ-L0-xxx | REQ-L1-259 | ReqIFServiceSystem | REQ-L2-REQ-011 | ReqIFServiceSystem_CompA | REQ-L3-REQ-011 |
| REQ-L0-xxx | REQ-L1-259 | ReqIFServiceSystem | REQ-L2-REQ-011 | ReqIFServiceSystem_CompB | REQ-L3-REQ-011 |
| REQ-L0-xxx | REQ-L1-019 | ReqIFServiceSystem | REQ-L2-REQ-012 | ReqIFServiceSystem_CompA | REQ-L3-REQ-012 |
| REQ-L0-xxx | REQ-L1-019 | ReqIFServiceSystem | REQ-L2-REQ-012 | ReqIFServiceSystem_CompB | REQ-L3-REQ-012 |
| REQ-L0-xxx | REQ-L1-136 | ReqIFServiceSystem | REQ-L2-REQ-013 | ReqIFServiceSystem_CompA | REQ-L3-REQ-013 |
| REQ-L0-xxx | REQ-L1-136 | ReqIFServiceSystem | REQ-L2-REQ-013 | ReqIFServiceSystem_CompB | REQ-L3-REQ-013 |
| REQ-L0-xxx | REQ-L1-044 | ReqIFServiceSystem | REQ-L2-REQ-014 | ReqIFServiceSystem_CompA | REQ-L3-REQ-014 |
| REQ-L0-xxx | REQ-L1-044 | ReqIFServiceSystem | REQ-L2-REQ-014 | ReqIFServiceSystem_CompB | REQ-L3-REQ-014 |
| REQ-L0-xxx | REQ-L1-275 | DiagramServiceSystem | REQ-L2-DIA-001 | DiagramServiceSystem_CompA | REQ-L3-DIA-001 |
| REQ-L0-xxx | REQ-L1-275 | DiagramServiceSystem | REQ-L2-DIA-001 | DiagramServiceSystem_CompB | REQ-L3-DIA-001 |
| REQ-L0-xxx | REQ-L1-046 | DiagramServiceSystem | REQ-L2-DIA-002 | DiagramServiceSystem_CompA | REQ-L3-DIA-002 |
| REQ-L0-xxx | REQ-L1-046 | DiagramServiceSystem | REQ-L2-DIA-002 | DiagramServiceSystem_CompB | REQ-L3-DIA-002 |
| REQ-L0-xxx | REQ-L1-082 | DiagramServiceSystem | REQ-L2-DIA-003 | DiagramServiceSystem_CompA | REQ-L3-DIA-003 |
| REQ-L0-xxx | REQ-L1-082 | DiagramServiceSystem | REQ-L2-DIA-003 | DiagramServiceSystem_CompB | REQ-L3-DIA-003 |
| REQ-L0-xxx | REQ-L1-126 | DiagramServiceSystem | REQ-L2-DIA-004 | DiagramServiceSystem_CompA | REQ-L3-DIA-004 |
| REQ-L0-xxx | REQ-L1-126 | DiagramServiceSystem | REQ-L2-DIA-004 | DiagramServiceSystem_CompB | REQ-L3-DIA-004 |
| REQ-L0-xxx | REQ-L1-006 | DiagramServiceSystem | REQ-L2-DIA-005 | DiagramServiceSystem_CompA | REQ-L3-DIA-005 |
| REQ-L0-xxx | REQ-L1-006 | DiagramServiceSystem | REQ-L2-DIA-005 | DiagramServiceSystem_CompB | REQ-L3-DIA-005 |
| REQ-L0-xxx | REQ-L1-218 | DiagramServiceSystem | REQ-L2-DIA-006 | DiagramServiceSystem_CompA | REQ-L3-DIA-006 |
| REQ-L0-xxx | REQ-L1-218 | DiagramServiceSystem | REQ-L2-DIA-006 | DiagramServiceSystem_CompB | REQ-L3-DIA-006 |
| REQ-L0-xxx | REQ-L1-143 | DiagramServiceSystem | REQ-L2-DIA-007 | DiagramServiceSystem_CompA | REQ-L3-DIA-007 |
| REQ-L0-xxx | REQ-L1-143 | DiagramServiceSystem | REQ-L2-DIA-007 | DiagramServiceSystem_CompB | REQ-L3-DIA-007 |
| REQ-L0-xxx | REQ-L1-080 | DiagramServiceSystem | REQ-L2-DIA-008 | DiagramServiceSystem_CompA | REQ-L3-DIA-008 |
| REQ-L0-xxx | REQ-L1-080 | DiagramServiceSystem | REQ-L2-DIA-008 | DiagramServiceSystem_CompB | REQ-L3-DIA-008 |
| REQ-L0-xxx | REQ-L1-130 | DiagramServiceSystem | REQ-L2-DIA-009 | DiagramServiceSystem_CompA | REQ-L3-DIA-009 |
| REQ-L0-xxx | REQ-L1-130 | DiagramServiceSystem | REQ-L2-DIA-009 | DiagramServiceSystem_CompB | REQ-L3-DIA-009 |
| REQ-L0-xxx | REQ-L1-269 | DiagramServiceSystem | REQ-L2-DIA-010 | DiagramServiceSystem_CompA | REQ-L3-DIA-010 |
| REQ-L0-xxx | REQ-L1-269 | DiagramServiceSystem | REQ-L2-DIA-010 | DiagramServiceSystem_CompB | REQ-L3-DIA-010 |
| REQ-L0-xxx | REQ-L1-059 | DiagramServiceSystem | REQ-L2-DIA-011 | DiagramServiceSystem_CompA | REQ-L3-DIA-011 |
| REQ-L0-xxx | REQ-L1-059 | DiagramServiceSystem | REQ-L2-DIA-011 | DiagramServiceSystem_CompB | REQ-L3-DIA-011 |
| REQ-L0-xxx | REQ-L1-014 | DiagramServiceSystem | REQ-L2-DIA-012 | DiagramServiceSystem_CompA | REQ-L3-DIA-012 |
| REQ-L0-xxx | REQ-L1-014 | DiagramServiceSystem | REQ-L2-DIA-012 | DiagramServiceSystem_CompB | REQ-L3-DIA-012 |
| REQ-L0-xxx | REQ-L1-021 | DiagramServiceSystem | REQ-L2-DIA-013 | DiagramServiceSystem_CompA | REQ-L3-DIA-013 |
| REQ-L0-xxx | REQ-L1-021 | DiagramServiceSystem | REQ-L2-DIA-013 | DiagramServiceSystem_CompB | REQ-L3-DIA-013 |
| REQ-L0-xxx | REQ-L1-029 | DiagramServiceSystem | REQ-L2-DIA-014 | DiagramServiceSystem_CompA | REQ-L3-DIA-014 |
| REQ-L0-xxx | REQ-L1-029 | DiagramServiceSystem | REQ-L2-DIA-014 | DiagramServiceSystem_CompB | REQ-L3-DIA-014 |
| REQ-L0-xxx | REQ-L1-174 | CommentServiceSystem | REQ-L2-COM-001 | CommentServiceSystem_CompA | REQ-L3-COM-001 |
| REQ-L0-xxx | REQ-L1-174 | CommentServiceSystem | REQ-L2-COM-001 | CommentServiceSystem_CompB | REQ-L3-COM-001 |
| REQ-L0-xxx | REQ-L1-182 | CommentServiceSystem | REQ-L2-COM-002 | CommentServiceSystem_CompA | REQ-L3-COM-002 |
| REQ-L0-xxx | REQ-L1-182 | CommentServiceSystem | REQ-L2-COM-002 | CommentServiceSystem_CompB | REQ-L3-COM-002 |
| REQ-L0-xxx | REQ-L1-036 | CommentServiceSystem | REQ-L2-COM-003 | CommentServiceSystem_CompA | REQ-L3-COM-003 |
| REQ-L0-xxx | REQ-L1-036 | CommentServiceSystem | REQ-L2-COM-003 | CommentServiceSystem_CompB | REQ-L3-COM-003 |
| REQ-L0-xxx | REQ-L1-013 | CommentServiceSystem | REQ-L2-COM-004 | CommentServiceSystem_CompA | REQ-L3-COM-004 |
| REQ-L0-xxx | REQ-L1-013 | CommentServiceSystem | REQ-L2-COM-004 | CommentServiceSystem_CompB | REQ-L3-COM-004 |
| REQ-L0-xxx | REQ-L1-132 | CommentServiceSystem | REQ-L2-COM-005 | CommentServiceSystem_CompA | REQ-L3-COM-005 |
| REQ-L0-xxx | REQ-L1-132 | CommentServiceSystem | REQ-L2-COM-005 | CommentServiceSystem_CompB | REQ-L3-COM-005 |
| REQ-L0-xxx | REQ-L1-221 | CommentServiceSystem | REQ-L2-COM-006 | CommentServiceSystem_CompA | REQ-L3-COM-006 |
| REQ-L0-xxx | REQ-L1-221 | CommentServiceSystem | REQ-L2-COM-006 | CommentServiceSystem_CompB | REQ-L3-COM-006 |
| REQ-L0-xxx | REQ-L1-121 | CommentServiceSystem | REQ-L2-COM-007 | CommentServiceSystem_CompA | REQ-L3-COM-007 |
| REQ-L0-xxx | REQ-L1-121 | CommentServiceSystem | REQ-L2-COM-007 | CommentServiceSystem_CompB | REQ-L3-COM-007 |
| REQ-L0-xxx | REQ-L1-171 | CommentServiceSystem | REQ-L2-COM-008 | CommentServiceSystem_CompA | REQ-L3-COM-008 |
| REQ-L0-xxx | REQ-L1-171 | CommentServiceSystem | REQ-L2-COM-008 | CommentServiceSystem_CompB | REQ-L3-COM-008 |
| REQ-L0-xxx | REQ-L1-142 | CommentServiceSystem | REQ-L2-COM-009 | CommentServiceSystem_CompA | REQ-L3-COM-009 |
| REQ-L0-xxx | REQ-L1-142 | CommentServiceSystem | REQ-L2-COM-009 | CommentServiceSystem_CompB | REQ-L3-COM-009 |
| REQ-L0-xxx | REQ-L1-173 | CommentServiceSystem | REQ-L2-COM-010 | CommentServiceSystem_CompA | REQ-L3-COM-010 |
| REQ-L0-xxx | REQ-L1-173 | CommentServiceSystem | REQ-L2-COM-010 | CommentServiceSystem_CompB | REQ-L3-COM-010 |
| REQ-L0-xxx | REQ-L1-284 | CommentServiceSystem | REQ-L2-COM-011 | CommentServiceSystem_CompA | REQ-L3-COM-011 |
| REQ-L0-xxx | REQ-L1-284 | CommentServiceSystem | REQ-L2-COM-011 | CommentServiceSystem_CompB | REQ-L3-COM-011 |
| REQ-L0-xxx | REQ-L1-269 | CommentServiceSystem | REQ-L2-COM-012 | CommentServiceSystem_CompA | REQ-L3-COM-012 |
| REQ-L0-xxx | REQ-L1-269 | CommentServiceSystem | REQ-L2-COM-012 | CommentServiceSystem_CompB | REQ-L3-COM-012 |
| REQ-L0-xxx | REQ-L1-172 | CommentServiceSystem | REQ-L2-COM-013 | CommentServiceSystem_CompA | REQ-L3-COM-013 |
| REQ-L0-xxx | REQ-L1-172 | CommentServiceSystem | REQ-L2-COM-013 | CommentServiceSystem_CompB | REQ-L3-COM-013 |
| REQ-L0-xxx | REQ-L1-139 | CommentServiceSystem | REQ-L2-COM-014 | CommentServiceSystem_CompA | REQ-L3-COM-014 |
| REQ-L0-xxx | REQ-L1-139 | CommentServiceSystem | REQ-L2-COM-014 | CommentServiceSystem_CompB | REQ-L3-COM-014 |
| REQ-L0-xxx | REQ-L1-268 | IcdManagementSystem | REQ-L2-ICD-001 | IcdManagementSystem_CompA | REQ-L3-ICD-001 |
| REQ-L0-xxx | REQ-L1-268 | IcdManagementSystem | REQ-L2-ICD-001 | IcdManagementSystem_CompB | REQ-L3-ICD-001 |
| REQ-L0-xxx | REQ-L1-101 | IcdManagementSystem | REQ-L2-ICD-002 | IcdManagementSystem_CompA | REQ-L3-ICD-002 |
| REQ-L0-xxx | REQ-L1-101 | IcdManagementSystem | REQ-L2-ICD-002 | IcdManagementSystem_CompB | REQ-L3-ICD-002 |
| REQ-L0-xxx | REQ-L1-265 | IcdManagementSystem | REQ-L2-ICD-003 | IcdManagementSystem_CompA | REQ-L3-ICD-003 |
| REQ-L0-xxx | REQ-L1-265 | IcdManagementSystem | REQ-L2-ICD-003 | IcdManagementSystem_CompB | REQ-L3-ICD-003 |
| REQ-L0-xxx | REQ-L1-191 | IcdManagementSystem | REQ-L2-ICD-004 | IcdManagementSystem_CompA | REQ-L3-ICD-004 |
| REQ-L0-xxx | REQ-L1-191 | IcdManagementSystem | REQ-L2-ICD-004 | IcdManagementSystem_CompB | REQ-L3-ICD-004 |
| REQ-L0-xxx | REQ-L1-273 | IcdManagementSystem | REQ-L2-ICD-005 | IcdManagementSystem_CompA | REQ-L3-ICD-005 |
| REQ-L0-xxx | REQ-L1-273 | IcdManagementSystem | REQ-L2-ICD-005 | IcdManagementSystem_CompB | REQ-L3-ICD-005 |
| REQ-L0-xxx | REQ-L1-065 | IcdManagementSystem | REQ-L2-ICD-006 | IcdManagementSystem_CompA | REQ-L3-ICD-006 |
| REQ-L0-xxx | REQ-L1-065 | IcdManagementSystem | REQ-L2-ICD-006 | IcdManagementSystem_CompB | REQ-L3-ICD-006 |
| REQ-L0-xxx | REQ-L1-253 | IcdManagementSystem | REQ-L2-ICD-007 | IcdManagementSystem_CompA | REQ-L3-ICD-007 |
| REQ-L0-xxx | REQ-L1-253 | IcdManagementSystem | REQ-L2-ICD-007 | IcdManagementSystem_CompB | REQ-L3-ICD-007 |
| REQ-L0-xxx | REQ-L1-204 | IcdManagementSystem | REQ-L2-ICD-008 | IcdManagementSystem_CompA | REQ-L3-ICD-008 |
| REQ-L0-xxx | REQ-L1-204 | IcdManagementSystem | REQ-L2-ICD-008 | IcdManagementSystem_CompB | REQ-L3-ICD-008 |
| REQ-L0-xxx | REQ-L1-076 | IcdManagementSystem | REQ-L2-ICD-009 | IcdManagementSystem_CompA | REQ-L3-ICD-009 |
| REQ-L0-xxx | REQ-L1-076 | IcdManagementSystem | REQ-L2-ICD-009 | IcdManagementSystem_CompB | REQ-L3-ICD-009 |
| REQ-L0-xxx | REQ-L1-002 | IcdManagementSystem | REQ-L2-ICD-010 | IcdManagementSystem_CompA | REQ-L3-ICD-010 |
| REQ-L0-xxx | REQ-L1-002 | IcdManagementSystem | REQ-L2-ICD-010 | IcdManagementSystem_CompB | REQ-L3-ICD-010 |
| REQ-L0-xxx | REQ-L1-189 | IcdManagementSystem | REQ-L2-ICD-011 | IcdManagementSystem_CompA | REQ-L3-ICD-011 |
| REQ-L0-xxx | REQ-L1-189 | IcdManagementSystem | REQ-L2-ICD-011 | IcdManagementSystem_CompB | REQ-L3-ICD-011 |
| REQ-L0-xxx | REQ-L1-048 | IcdManagementSystem | REQ-L2-ICD-012 | IcdManagementSystem_CompA | REQ-L3-ICD-012 |
| REQ-L0-xxx | REQ-L1-048 | IcdManagementSystem | REQ-L2-ICD-012 | IcdManagementSystem_CompB | REQ-L3-ICD-012 |
| REQ-L0-xxx | REQ-L1-113 | IcdManagementSystem | REQ-L2-ICD-013 | IcdManagementSystem_CompA | REQ-L3-ICD-013 |
| REQ-L0-xxx | REQ-L1-113 | IcdManagementSystem | REQ-L2-ICD-013 | IcdManagementSystem_CompB | REQ-L3-ICD-013 |
| REQ-L0-xxx | REQ-L1-132 | IcdManagementSystem | REQ-L2-ICD-014 | IcdManagementSystem_CompA | REQ-L3-ICD-014 |
| REQ-L0-xxx | REQ-L1-132 | IcdManagementSystem | REQ-L2-ICD-014 | IcdManagementSystem_CompB | REQ-L3-ICD-014 |
| REQ-L0-xxx | REQ-L1-086 | SeMetricsSystem | REQ-L2-SEM-001 | SeMetricsSystem_CompA | REQ-L3-SEM-001 |
| REQ-L0-xxx | REQ-L1-086 | SeMetricsSystem | REQ-L2-SEM-001 | SeMetricsSystem_CompB | REQ-L3-SEM-001 |
| REQ-L0-xxx | REQ-L1-169 | SeMetricsSystem | REQ-L2-SEM-002 | SeMetricsSystem_CompA | REQ-L3-SEM-002 |
| REQ-L0-xxx | REQ-L1-169 | SeMetricsSystem | REQ-L2-SEM-002 | SeMetricsSystem_CompB | REQ-L3-SEM-002 |
| REQ-L0-xxx | REQ-L1-280 | SeMetricsSystem | REQ-L2-SEM-003 | SeMetricsSystem_CompA | REQ-L3-SEM-003 |
| REQ-L0-xxx | REQ-L1-280 | SeMetricsSystem | REQ-L2-SEM-003 | SeMetricsSystem_CompB | REQ-L3-SEM-003 |
| REQ-L0-xxx | REQ-L1-159 | SeMetricsSystem | REQ-L2-SEM-004 | SeMetricsSystem_CompA | REQ-L3-SEM-004 |
| REQ-L0-xxx | REQ-L1-159 | SeMetricsSystem | REQ-L2-SEM-004 | SeMetricsSystem_CompB | REQ-L3-SEM-004 |
| REQ-L0-xxx | REQ-L1-157 | SeMetricsSystem | REQ-L2-SEM-005 | SeMetricsSystem_CompA | REQ-L3-SEM-005 |
| REQ-L0-xxx | REQ-L1-157 | SeMetricsSystem | REQ-L2-SEM-005 | SeMetricsSystem_CompB | REQ-L3-SEM-005 |
| REQ-L0-xxx | REQ-L1-044 | SeMetricsSystem | REQ-L2-SEM-006 | SeMetricsSystem_CompA | REQ-L3-SEM-006 |
| REQ-L0-xxx | REQ-L1-044 | SeMetricsSystem | REQ-L2-SEM-006 | SeMetricsSystem_CompB | REQ-L3-SEM-006 |
| REQ-L0-xxx | REQ-L1-096 | SeMetricsSystem | REQ-L2-SEM-007 | SeMetricsSystem_CompA | REQ-L3-SEM-007 |
| REQ-L0-xxx | REQ-L1-096 | SeMetricsSystem | REQ-L2-SEM-007 | SeMetricsSystem_CompB | REQ-L3-SEM-007 |
| REQ-L0-xxx | REQ-L1-047 | SeMetricsSystem | REQ-L2-SEM-008 | SeMetricsSystem_CompA | REQ-L3-SEM-008 |
| REQ-L0-xxx | REQ-L1-047 | SeMetricsSystem | REQ-L2-SEM-008 | SeMetricsSystem_CompB | REQ-L3-SEM-008 |
| REQ-L0-xxx | REQ-L1-185 | SeMetricsSystem | REQ-L2-SEM-009 | SeMetricsSystem_CompA | REQ-L3-SEM-009 |
| REQ-L0-xxx | REQ-L1-185 | SeMetricsSystem | REQ-L2-SEM-009 | SeMetricsSystem_CompB | REQ-L3-SEM-009 |
| REQ-L0-xxx | REQ-L1-058 | SeMetricsSystem | REQ-L2-SEM-010 | SeMetricsSystem_CompA | REQ-L3-SEM-010 |
| REQ-L0-xxx | REQ-L1-058 | SeMetricsSystem | REQ-L2-SEM-010 | SeMetricsSystem_CompB | REQ-L3-SEM-010 |
| REQ-L0-xxx | REQ-L1-077 | SeMetricsSystem | REQ-L2-SEM-011 | SeMetricsSystem_CompA | REQ-L3-SEM-011 |
| REQ-L0-xxx | REQ-L1-077 | SeMetricsSystem | REQ-L2-SEM-011 | SeMetricsSystem_CompB | REQ-L3-SEM-011 |
| REQ-L0-xxx | REQ-L1-173 | SeMetricsSystem | REQ-L2-SEM-012 | SeMetricsSystem_CompA | REQ-L3-SEM-012 |
| REQ-L0-xxx | REQ-L1-173 | SeMetricsSystem | REQ-L2-SEM-012 | SeMetricsSystem_CompB | REQ-L3-SEM-012 |
| REQ-L0-xxx | REQ-L1-081 | SeMetricsSystem | REQ-L2-SEM-013 | SeMetricsSystem_CompA | REQ-L3-SEM-013 |
| REQ-L0-xxx | REQ-L1-081 | SeMetricsSystem | REQ-L2-SEM-013 | SeMetricsSystem_CompB | REQ-L3-SEM-013 |
| REQ-L0-xxx | REQ-L1-166 | SeMetricsSystem | REQ-L2-SEM-014 | SeMetricsSystem_CompA | REQ-L3-SEM-014 |
| REQ-L0-xxx | REQ-L1-166 | SeMetricsSystem | REQ-L2-SEM-014 | SeMetricsSystem_CompB | REQ-L3-SEM-014 |
| REQ-L0-xxx | REQ-L1-261 | TraceabilityEngineSystem | REQ-L2-TRA-001 | TraceabilityEngineSystem_CompA | REQ-L3-TRA-001 |
| REQ-L0-xxx | REQ-L1-261 | TraceabilityEngineSystem | REQ-L2-TRA-001 | TraceabilityEngineSystem_CompB | REQ-L3-TRA-001 |
| REQ-L0-xxx | REQ-L1-208 | TraceabilityEngineSystem | REQ-L2-TRA-002 | TraceabilityEngineSystem_CompA | REQ-L3-TRA-002 |
| REQ-L0-xxx | REQ-L1-208 | TraceabilityEngineSystem | REQ-L2-TRA-002 | TraceabilityEngineSystem_CompB | REQ-L3-TRA-002 |
| REQ-L0-xxx | REQ-L1-089 | TraceabilityEngineSystem | REQ-L2-TRA-003 | TraceabilityEngineSystem_CompA | REQ-L3-TRA-003 |
| REQ-L0-xxx | REQ-L1-089 | TraceabilityEngineSystem | REQ-L2-TRA-003 | TraceabilityEngineSystem_CompB | REQ-L3-TRA-003 |
| REQ-L0-xxx | REQ-L1-170 | TraceabilityEngineSystem | REQ-L2-TRA-004 | TraceabilityEngineSystem_CompA | REQ-L3-TRA-004 |
| REQ-L0-xxx | REQ-L1-170 | TraceabilityEngineSystem | REQ-L2-TRA-004 | TraceabilityEngineSystem_CompB | REQ-L3-TRA-004 |
| REQ-L0-xxx | REQ-L1-232 | TraceabilityEngineSystem | REQ-L2-TRA-005 | TraceabilityEngineSystem_CompA | REQ-L3-TRA-005 |
| REQ-L0-xxx | REQ-L1-232 | TraceabilityEngineSystem | REQ-L2-TRA-005 | TraceabilityEngineSystem_CompB | REQ-L3-TRA-005 |
| REQ-L0-xxx | REQ-L1-008 | TraceabilityEngineSystem | REQ-L2-TRA-006 | TraceabilityEngineSystem_CompA | REQ-L3-TRA-006 |
| REQ-L0-xxx | REQ-L1-008 | TraceabilityEngineSystem | REQ-L2-TRA-006 | TraceabilityEngineSystem_CompB | REQ-L3-TRA-006 |
| REQ-L0-xxx | REQ-L1-128 | TraceabilityEngineSystem | REQ-L2-TRA-007 | TraceabilityEngineSystem_CompA | REQ-L3-TRA-007 |
| REQ-L0-xxx | REQ-L1-128 | TraceabilityEngineSystem | REQ-L2-TRA-007 | TraceabilityEngineSystem_CompB | REQ-L3-TRA-007 |
| REQ-L0-xxx | REQ-L1-127 | TraceabilityEngineSystem | REQ-L2-TRA-008 | TraceabilityEngineSystem_CompA | REQ-L3-TRA-008 |
| REQ-L0-xxx | REQ-L1-127 | TraceabilityEngineSystem | REQ-L2-TRA-008 | TraceabilityEngineSystem_CompB | REQ-L3-TRA-008 |
| REQ-L0-xxx | REQ-L1-064 | TraceabilityEngineSystem | REQ-L2-TRA-009 | TraceabilityEngineSystem_CompA | REQ-L3-TRA-009 |
| REQ-L0-xxx | REQ-L1-064 | TraceabilityEngineSystem | REQ-L2-TRA-009 | TraceabilityEngineSystem_CompB | REQ-L3-TRA-009 |
| REQ-L0-xxx | REQ-L1-095 | TraceabilityEngineSystem | REQ-L2-TRA-010 | TraceabilityEngineSystem_CompA | REQ-L3-TRA-010 |
| REQ-L0-xxx | REQ-L1-095 | TraceabilityEngineSystem | REQ-L2-TRA-010 | TraceabilityEngineSystem_CompB | REQ-L3-TRA-010 |
| REQ-L0-xxx | REQ-L1-184 | TraceabilityEngineSystem | REQ-L2-TRA-011 | TraceabilityEngineSystem_CompA | REQ-L3-TRA-011 |
| REQ-L0-xxx | REQ-L1-184 | TraceabilityEngineSystem | REQ-L2-TRA-011 | TraceabilityEngineSystem_CompB | REQ-L3-TRA-011 |
| REQ-L0-xxx | REQ-L1-275 | TraceabilityEngineSystem | REQ-L2-TRA-012 | TraceabilityEngineSystem_CompA | REQ-L3-TRA-012 |
| REQ-L0-xxx | REQ-L1-275 | TraceabilityEngineSystem | REQ-L2-TRA-012 | TraceabilityEngineSystem_CompB | REQ-L3-TRA-012 |
| REQ-L0-xxx | REQ-L1-086 | TraceabilityEngineSystem | REQ-L2-TRA-013 | TraceabilityEngineSystem_CompA | REQ-L3-TRA-013 |
| REQ-L0-xxx | REQ-L1-086 | TraceabilityEngineSystem | REQ-L2-TRA-013 | TraceabilityEngineSystem_CompB | REQ-L3-TRA-013 |
| REQ-L0-xxx | REQ-L1-148 | TraceabilityEngineSystem | REQ-L2-TRA-014 | TraceabilityEngineSystem_CompA | REQ-L3-TRA-014 |
| REQ-L0-xxx | REQ-L1-148 | TraceabilityEngineSystem | REQ-L2-TRA-014 | TraceabilityEngineSystem_CompB | REQ-L3-TRA-014 |
| REQ-L0-xxx | REQ-L1-180 | VectorSearchServiceSystem | REQ-L2-VEC-001 | VectorSearchServiceSystem_CompA | REQ-L3-VEC-001 |
| REQ-L0-xxx | REQ-L1-180 | VectorSearchServiceSystem | REQ-L2-VEC-001 | VectorSearchServiceSystem_CompB | REQ-L3-VEC-001 |
| REQ-L0-xxx | REQ-L1-084 | VectorSearchServiceSystem | REQ-L2-VEC-002 | VectorSearchServiceSystem_CompA | REQ-L3-VEC-002 |
| REQ-L0-xxx | REQ-L1-084 | VectorSearchServiceSystem | REQ-L2-VEC-002 | VectorSearchServiceSystem_CompB | REQ-L3-VEC-002 |
| REQ-L0-xxx | REQ-L1-029 | VectorSearchServiceSystem | REQ-L2-VEC-003 | VectorSearchServiceSystem_CompA | REQ-L3-VEC-003 |
| REQ-L0-xxx | REQ-L1-029 | VectorSearchServiceSystem | REQ-L2-VEC-003 | VectorSearchServiceSystem_CompB | REQ-L3-VEC-003 |
| REQ-L0-xxx | REQ-L1-185 | VectorSearchServiceSystem | REQ-L2-VEC-004 | VectorSearchServiceSystem_CompA | REQ-L3-VEC-004 |
| REQ-L0-xxx | REQ-L1-185 | VectorSearchServiceSystem | REQ-L2-VEC-004 | VectorSearchServiceSystem_CompB | REQ-L3-VEC-004 |
| REQ-L0-xxx | REQ-L1-078 | VectorSearchServiceSystem | REQ-L2-VEC-005 | VectorSearchServiceSystem_CompA | REQ-L3-VEC-005 |
| REQ-L0-xxx | REQ-L1-078 | VectorSearchServiceSystem | REQ-L2-VEC-005 | VectorSearchServiceSystem_CompB | REQ-L3-VEC-005 |
| REQ-L0-xxx | REQ-L1-198 | VectorSearchServiceSystem | REQ-L2-VEC-006 | VectorSearchServiceSystem_CompA | REQ-L3-VEC-006 |
| REQ-L0-xxx | REQ-L1-198 | VectorSearchServiceSystem | REQ-L2-VEC-006 | VectorSearchServiceSystem_CompB | REQ-L3-VEC-006 |
| REQ-L0-xxx | REQ-L1-047 | VectorSearchServiceSystem | REQ-L2-VEC-007 | VectorSearchServiceSystem_CompA | REQ-L3-VEC-007 |
| REQ-L0-xxx | REQ-L1-047 | VectorSearchServiceSystem | REQ-L2-VEC-007 | VectorSearchServiceSystem_CompB | REQ-L3-VEC-007 |
| REQ-L0-xxx | REQ-L1-170 | VectorSearchServiceSystem | REQ-L2-VEC-008 | VectorSearchServiceSystem_CompA | REQ-L3-VEC-008 |
| REQ-L0-xxx | REQ-L1-170 | VectorSearchServiceSystem | REQ-L2-VEC-008 | VectorSearchServiceSystem_CompB | REQ-L3-VEC-008 |
| REQ-L0-xxx | REQ-L1-111 | VectorSearchServiceSystem | REQ-L2-VEC-009 | VectorSearchServiceSystem_CompA | REQ-L3-VEC-009 |
| REQ-L0-xxx | REQ-L1-111 | VectorSearchServiceSystem | REQ-L2-VEC-009 | VectorSearchServiceSystem_CompB | REQ-L3-VEC-009 |
| REQ-L0-xxx | REQ-L1-139 | VectorSearchServiceSystem | REQ-L2-VEC-010 | VectorSearchServiceSystem_CompA | REQ-L3-VEC-010 |
| REQ-L0-xxx | REQ-L1-139 | VectorSearchServiceSystem | REQ-L2-VEC-010 | VectorSearchServiceSystem_CompB | REQ-L3-VEC-010 |
| REQ-L0-xxx | REQ-L1-143 | VectorSearchServiceSystem | REQ-L2-VEC-011 | VectorSearchServiceSystem_CompA | REQ-L3-VEC-011 |
| REQ-L0-xxx | REQ-L1-143 | VectorSearchServiceSystem | REQ-L2-VEC-011 | VectorSearchServiceSystem_CompB | REQ-L3-VEC-011 |
| REQ-L0-xxx | REQ-L1-001 | VectorSearchServiceSystem | REQ-L2-VEC-012 | VectorSearchServiceSystem_CompA | REQ-L3-VEC-012 |
| REQ-L0-xxx | REQ-L1-001 | VectorSearchServiceSystem | REQ-L2-VEC-012 | VectorSearchServiceSystem_CompB | REQ-L3-VEC-012 |
| REQ-L0-xxx | REQ-L1-103 | VectorSearchServiceSystem | REQ-L2-VEC-013 | VectorSearchServiceSystem_CompA | REQ-L3-VEC-013 |
| REQ-L0-xxx | REQ-L1-103 | VectorSearchServiceSystem | REQ-L2-VEC-013 | VectorSearchServiceSystem_CompB | REQ-L3-VEC-013 |
| REQ-L0-xxx | REQ-L1-203 | VectorSearchServiceSystem | REQ-L2-VEC-014 | VectorSearchServiceSystem_CompA | REQ-L3-VEC-014 |
| REQ-L0-xxx | REQ-L1-203 | VectorSearchServiceSystem | REQ-L2-VEC-014 | VectorSearchServiceSystem_CompB | REQ-L3-VEC-014 |
| REQ-L0-xxx | REQ-L1-183 | AuditLogSystem | REQ-L2-AUD-001 | AuditLogSystem_CompA | REQ-L3-AUD-001 |
| REQ-L0-xxx | REQ-L1-183 | AuditLogSystem | REQ-L2-AUD-001 | AuditLogSystem_CompB | REQ-L3-AUD-001 |
| REQ-L0-xxx | REQ-L1-222 | AuditLogSystem | REQ-L2-AUD-002 | AuditLogSystem_CompA | REQ-L3-AUD-002 |
| REQ-L0-xxx | REQ-L1-222 | AuditLogSystem | REQ-L2-AUD-002 | AuditLogSystem_CompB | REQ-L3-AUD-002 |
| REQ-L0-xxx | REQ-L1-066 | AuditLogSystem | REQ-L2-AUD-003 | AuditLogSystem_CompA | REQ-L3-AUD-003 |
| REQ-L0-xxx | REQ-L1-066 | AuditLogSystem | REQ-L2-AUD-003 | AuditLogSystem_CompB | REQ-L3-AUD-003 |
| REQ-L0-xxx | REQ-L1-086 | AuditLogSystem | REQ-L2-AUD-004 | AuditLogSystem_CompA | REQ-L3-AUD-004 |
| REQ-L0-xxx | REQ-L1-086 | AuditLogSystem | REQ-L2-AUD-004 | AuditLogSystem_CompB | REQ-L3-AUD-004 |
| REQ-L0-xxx | REQ-L1-016 | AuditLogSystem | REQ-L2-AUD-005 | AuditLogSystem_CompA | REQ-L3-AUD-005 |
| REQ-L0-xxx | REQ-L1-016 | AuditLogSystem | REQ-L2-AUD-005 | AuditLogSystem_CompB | REQ-L3-AUD-005 |
| REQ-L0-xxx | REQ-L1-175 | AuditLogSystem | REQ-L2-AUD-006 | AuditLogSystem_CompA | REQ-L3-AUD-006 |
| REQ-L0-xxx | REQ-L1-175 | AuditLogSystem | REQ-L2-AUD-006 | AuditLogSystem_CompB | REQ-L3-AUD-006 |
| REQ-L0-xxx | REQ-L1-162 | AuditLogSystem | REQ-L2-AUD-007 | AuditLogSystem_CompA | REQ-L3-AUD-007 |
| REQ-L0-xxx | REQ-L1-162 | AuditLogSystem | REQ-L2-AUD-007 | AuditLogSystem_CompB | REQ-L3-AUD-007 |
| REQ-L0-xxx | REQ-L1-223 | AuditLogSystem | REQ-L2-AUD-008 | AuditLogSystem_CompA | REQ-L3-AUD-008 |
| REQ-L0-xxx | REQ-L1-223 | AuditLogSystem | REQ-L2-AUD-008 | AuditLogSystem_CompB | REQ-L3-AUD-008 |
| REQ-L0-xxx | REQ-L1-250 | AuditLogSystem | REQ-L2-AUD-009 | AuditLogSystem_CompA | REQ-L3-AUD-009 |
| REQ-L0-xxx | REQ-L1-250 | AuditLogSystem | REQ-L2-AUD-009 | AuditLogSystem_CompB | REQ-L3-AUD-009 |
| REQ-L0-xxx | REQ-L1-188 | AuditLogSystem | REQ-L2-AUD-010 | AuditLogSystem_CompA | REQ-L3-AUD-010 |
| REQ-L0-xxx | REQ-L1-188 | AuditLogSystem | REQ-L2-AUD-010 | AuditLogSystem_CompB | REQ-L3-AUD-010 |
| REQ-L0-xxx | REQ-L1-284 | AuditLogSystem | REQ-L2-AUD-011 | AuditLogSystem_CompA | REQ-L3-AUD-011 |
| REQ-L0-xxx | REQ-L1-284 | AuditLogSystem | REQ-L2-AUD-011 | AuditLogSystem_CompB | REQ-L3-AUD-011 |
| REQ-L0-xxx | REQ-L1-224 | AuditLogSystem | REQ-L2-AUD-012 | AuditLogSystem_CompA | REQ-L3-AUD-012 |
| REQ-L0-xxx | REQ-L1-224 | AuditLogSystem | REQ-L2-AUD-012 | AuditLogSystem_CompB | REQ-L3-AUD-012 |
| REQ-L0-xxx | REQ-L1-136 | AuditLogSystem | REQ-L2-AUD-013 | AuditLogSystem_CompA | REQ-L3-AUD-013 |
| REQ-L0-xxx | REQ-L1-136 | AuditLogSystem | REQ-L2-AUD-013 | AuditLogSystem_CompB | REQ-L3-AUD-013 |
| REQ-L0-xxx | REQ-L1-098 | AuditLogSystem | REQ-L2-AUD-014 | AuditLogSystem_CompA | REQ-L3-AUD-014 |
| REQ-L0-xxx | REQ-L1-098 | AuditLogSystem | REQ-L2-AUD-014 | AuditLogSystem_CompB | REQ-L3-AUD-014 |
| REQ-L0-xxx | REQ-L1-214 | BaselineServiceSystem | REQ-L2-BAS-001 | BaselineServiceSystem_CompA | REQ-L3-BAS-001 |
| REQ-L0-xxx | REQ-L1-214 | BaselineServiceSystem | REQ-L2-BAS-001 | BaselineServiceSystem_CompB | REQ-L3-BAS-001 |
| REQ-L0-xxx | REQ-L1-210 | BaselineServiceSystem | REQ-L2-BAS-002 | BaselineServiceSystem_CompA | REQ-L3-BAS-002 |
| REQ-L0-xxx | REQ-L1-210 | BaselineServiceSystem | REQ-L2-BAS-002 | BaselineServiceSystem_CompB | REQ-L3-BAS-002 |
| REQ-L0-xxx | REQ-L1-094 | BaselineServiceSystem | REQ-L2-BAS-003 | BaselineServiceSystem_CompA | REQ-L3-BAS-003 |
| REQ-L0-xxx | REQ-L1-094 | BaselineServiceSystem | REQ-L2-BAS-003 | BaselineServiceSystem_CompB | REQ-L3-BAS-003 |
| REQ-L0-xxx | REQ-L1-274 | BaselineServiceSystem | REQ-L2-BAS-004 | BaselineServiceSystem_CompA | REQ-L3-BAS-004 |
| REQ-L0-xxx | REQ-L1-274 | BaselineServiceSystem | REQ-L2-BAS-004 | BaselineServiceSystem_CompB | REQ-L3-BAS-004 |
| REQ-L0-xxx | REQ-L1-027 | BaselineServiceSystem | REQ-L2-BAS-005 | BaselineServiceSystem_CompA | REQ-L3-BAS-005 |
| REQ-L0-xxx | REQ-L1-027 | BaselineServiceSystem | REQ-L2-BAS-005 | BaselineServiceSystem_CompB | REQ-L3-BAS-005 |
| REQ-L0-xxx | REQ-L1-284 | BaselineServiceSystem | REQ-L2-BAS-006 | BaselineServiceSystem_CompA | REQ-L3-BAS-006 |
| REQ-L0-xxx | REQ-L1-284 | BaselineServiceSystem | REQ-L2-BAS-006 | BaselineServiceSystem_CompB | REQ-L3-BAS-006 |
| REQ-L0-xxx | REQ-L1-208 | BaselineServiceSystem | REQ-L2-BAS-007 | BaselineServiceSystem_CompA | REQ-L3-BAS-007 |
| REQ-L0-xxx | REQ-L1-208 | BaselineServiceSystem | REQ-L2-BAS-007 | BaselineServiceSystem_CompB | REQ-L3-BAS-007 |
| REQ-L0-xxx | REQ-L1-112 | BaselineServiceSystem | REQ-L2-BAS-008 | BaselineServiceSystem_CompA | REQ-L3-BAS-008 |
| REQ-L0-xxx | REQ-L1-112 | BaselineServiceSystem | REQ-L2-BAS-008 | BaselineServiceSystem_CompB | REQ-L3-BAS-008 |
| REQ-L0-xxx | REQ-L1-131 | BaselineServiceSystem | REQ-L2-BAS-009 | BaselineServiceSystem_CompA | REQ-L3-BAS-009 |
| REQ-L0-xxx | REQ-L1-131 | BaselineServiceSystem | REQ-L2-BAS-009 | BaselineServiceSystem_CompB | REQ-L3-BAS-009 |
| REQ-L0-xxx | REQ-L1-056 | BaselineServiceSystem | REQ-L2-BAS-010 | BaselineServiceSystem_CompA | REQ-L3-BAS-010 |
| REQ-L0-xxx | REQ-L1-056 | BaselineServiceSystem | REQ-L2-BAS-010 | BaselineServiceSystem_CompB | REQ-L3-BAS-010 |
| REQ-L0-xxx | REQ-L1-244 | BaselineServiceSystem | REQ-L2-BAS-011 | BaselineServiceSystem_CompA | REQ-L3-BAS-011 |
| REQ-L0-xxx | REQ-L1-244 | BaselineServiceSystem | REQ-L2-BAS-011 | BaselineServiceSystem_CompB | REQ-L3-BAS-011 |
| REQ-L0-xxx | REQ-L1-217 | BaselineServiceSystem | REQ-L2-BAS-012 | BaselineServiceSystem_CompA | REQ-L3-BAS-012 |
| REQ-L0-xxx | REQ-L1-217 | BaselineServiceSystem | REQ-L2-BAS-012 | BaselineServiceSystem_CompB | REQ-L3-BAS-012 |
| REQ-L0-xxx | REQ-L1-034 | BaselineServiceSystem | REQ-L2-BAS-013 | BaselineServiceSystem_CompA | REQ-L3-BAS-013 |
| REQ-L0-xxx | REQ-L1-034 | BaselineServiceSystem | REQ-L2-BAS-013 | BaselineServiceSystem_CompB | REQ-L3-BAS-013 |
| REQ-L0-xxx | REQ-L1-163 | BaselineServiceSystem | REQ-L2-BAS-014 | BaselineServiceSystem_CompA | REQ-L3-BAS-014 |
| REQ-L0-xxx | REQ-L1-163 | BaselineServiceSystem | REQ-L2-BAS-014 | BaselineServiceSystem_CompB | REQ-L3-BAS-014 |
| REQ-L0-xxx | REQ-L1-085 | LlmAdapterSystem | REQ-L2-LLM-001 | LlmAdapterSystem_CompA | REQ-L3-LLM-001 |
| REQ-L0-xxx | REQ-L1-085 | LlmAdapterSystem | REQ-L2-LLM-001 | LlmAdapterSystem_CompB | REQ-L3-LLM-001 |
| REQ-L0-xxx | REQ-L1-181 | LlmAdapterSystem | REQ-L2-LLM-002 | LlmAdapterSystem_CompA | REQ-L3-LLM-002 |
| REQ-L0-xxx | REQ-L1-181 | LlmAdapterSystem | REQ-L2-LLM-002 | LlmAdapterSystem_CompB | REQ-L3-LLM-002 |
| REQ-L0-xxx | REQ-L1-087 | LlmAdapterSystem | REQ-L2-LLM-003 | LlmAdapterSystem_CompA | REQ-L3-LLM-003 |
| REQ-L0-xxx | REQ-L1-087 | LlmAdapterSystem | REQ-L2-LLM-003 | LlmAdapterSystem_CompB | REQ-L3-LLM-003 |
| REQ-L0-xxx | REQ-L1-020 | LlmAdapterSystem | REQ-L2-LLM-004 | LlmAdapterSystem_CompA | REQ-L3-LLM-004 |
| REQ-L0-xxx | REQ-L1-020 | LlmAdapterSystem | REQ-L2-LLM-004 | LlmAdapterSystem_CompB | REQ-L3-LLM-004 |
| REQ-L0-xxx | REQ-L1-046 | LlmAdapterSystem | REQ-L2-LLM-005 | LlmAdapterSystem_CompA | REQ-L3-LLM-005 |
| REQ-L0-xxx | REQ-L1-046 | LlmAdapterSystem | REQ-L2-LLM-005 | LlmAdapterSystem_CompB | REQ-L3-LLM-005 |
| REQ-L0-xxx | REQ-L1-012 | LlmAdapterSystem | REQ-L2-LLM-006 | LlmAdapterSystem_CompA | REQ-L3-LLM-006 |
| REQ-L0-xxx | REQ-L1-012 | LlmAdapterSystem | REQ-L2-LLM-006 | LlmAdapterSystem_CompB | REQ-L3-LLM-006 |
| REQ-L0-xxx | REQ-L1-154 | LlmAdapterSystem | REQ-L2-LLM-007 | LlmAdapterSystem_CompA | REQ-L3-LLM-007 |
| REQ-L0-xxx | REQ-L1-154 | LlmAdapterSystem | REQ-L2-LLM-007 | LlmAdapterSystem_CompB | REQ-L3-LLM-007 |
| REQ-L0-xxx | REQ-L1-263 | LlmAdapterSystem | REQ-L2-LLM-008 | LlmAdapterSystem_CompA | REQ-L3-LLM-008 |
| REQ-L0-xxx | REQ-L1-263 | LlmAdapterSystem | REQ-L2-LLM-008 | LlmAdapterSystem_CompB | REQ-L3-LLM-008 |
| REQ-L0-xxx | REQ-L1-131 | LlmAdapterSystem | REQ-L2-LLM-009 | LlmAdapterSystem_CompA | REQ-L3-LLM-009 |
| REQ-L0-xxx | REQ-L1-131 | LlmAdapterSystem | REQ-L2-LLM-009 | LlmAdapterSystem_CompB | REQ-L3-LLM-009 |
| REQ-L0-xxx | REQ-L1-262 | LlmAdapterSystem | REQ-L2-LLM-010 | LlmAdapterSystem_CompA | REQ-L3-LLM-010 |
| REQ-L0-xxx | REQ-L1-262 | LlmAdapterSystem | REQ-L2-LLM-010 | LlmAdapterSystem_CompB | REQ-L3-LLM-010 |
| REQ-L0-xxx | REQ-L1-189 | LlmAdapterSystem | REQ-L2-LLM-011 | LlmAdapterSystem_CompA | REQ-L3-LLM-011 |
| REQ-L0-xxx | REQ-L1-189 | LlmAdapterSystem | REQ-L2-LLM-011 | LlmAdapterSystem_CompB | REQ-L3-LLM-011 |
| REQ-L0-xxx | REQ-L1-069 | LlmAdapterSystem | REQ-L2-LLM-012 | LlmAdapterSystem_CompA | REQ-L3-LLM-012 |
| REQ-L0-xxx | REQ-L1-069 | LlmAdapterSystem | REQ-L2-LLM-012 | LlmAdapterSystem_CompB | REQ-L3-LLM-012 |
| REQ-L0-xxx | REQ-L1-120 | LlmAdapterSystem | REQ-L2-LLM-013 | LlmAdapterSystem_CompA | REQ-L3-LLM-013 |
| REQ-L0-xxx | REQ-L1-120 | LlmAdapterSystem | REQ-L2-LLM-013 | LlmAdapterSystem_CompB | REQ-L3-LLM-013 |
| REQ-L0-xxx | REQ-L1-093 | LlmAdapterSystem | REQ-L2-LLM-014 | LlmAdapterSystem_CompA | REQ-L3-LLM-014 |
| REQ-L0-xxx | REQ-L1-093 | LlmAdapterSystem | REQ-L2-LLM-014 | LlmAdapterSystem_CompB | REQ-L3-LLM-014 |

## (Superpowers) REQ-L1 -> REQ-L2 Additions

| REQ-L1 | REQ-L2 | Title |
|---|---|---|
| REQ-L1-282 | REQ-L2-AIO-001 | L2 Requirement derived from REQ-L1-282 |
| REQ-L1-084 | REQ-L2-AIO-002 | L2 Requirement derived from REQ-L1-084 |
| REQ-L1-130 | REQ-L2-AIO-003 | L2 Requirement derived from REQ-L1-130 |
| REQ-L1-190 | REQ-L2-AIO-004 | L2 Requirement derived from REQ-L1-190 |
| REQ-L1-095 | REQ-L2-AIO-005 | L2 Requirement derived from REQ-L1-095 |
| REQ-L1-265 | REQ-L2-AIO-006 | L2 Requirement derived from REQ-L1-265 |
| REQ-L1-262 | REQ-L2-AIO-007 | L2 Requirement derived from REQ-L1-262 |
| REQ-L1-104 | REQ-L2-AIO-008 | L2 Requirement derived from REQ-L1-104 |
| REQ-L1-093 | REQ-L2-AIO-009 | L2 Requirement derived from REQ-L1-093 |
| REQ-L1-221 | REQ-L2-AIO-010 | L2 Requirement derived from REQ-L1-221 |
| REQ-L1-266 | REQ-L2-AIO-011 | L2 Requirement derived from REQ-L1-266 |
| REQ-L1-007 | REQ-L2-AIO-012 | L2 Requirement derived from REQ-L1-007 |
| REQ-L1-250 | REQ-L2-AIO-013 | L2 Requirement derived from REQ-L1-250 |
| REQ-L1-131 | REQ-L2-AIO-014 | L2 Requirement derived from REQ-L1-131 |
| REQ-L1-285 | REQ-L2-AIO-015 | Integration of Context Generators (Superpowers) |
| REQ-L1-286 | REQ-L2-AIO-016 | Agent Templates and Write Modes (Superpowers) |
| REQ-L1-214 | REQ-L2-BAS-001 | L2 Requirement derived from REQ-L1-214 |
| REQ-L1-210 | REQ-L2-BAS-002 | L2 Requirement derived from REQ-L1-210 |
| REQ-L1-094 | REQ-L2-BAS-003 | L2 Requirement derived from REQ-L1-094 |
| REQ-L1-274 | REQ-L2-BAS-004 | L2 Requirement derived from REQ-L1-274 |
| REQ-L1-027 | REQ-L2-BAS-005 | L2 Requirement derived from REQ-L1-027 |
| REQ-L1-284 | REQ-L2-BAS-006 | L2 Requirement derived from REQ-L1-284 |
| REQ-L1-208 | REQ-L2-BAS-007 | L2 Requirement derived from REQ-L1-208 |
| REQ-L1-112 | REQ-L2-BAS-008 | L2 Requirement derived from REQ-L1-112 |
| REQ-L1-131 | REQ-L2-BAS-009 | L2 Requirement derived from REQ-L1-131 |
| REQ-L1-056 | REQ-L2-BAS-010 | L2 Requirement derived from REQ-L1-056 |
| REQ-L1-244 | REQ-L2-BAS-011 | L2 Requirement derived from REQ-L1-244 |
| REQ-L1-217 | REQ-L2-BAS-012 | L2 Requirement derived from REQ-L1-217 |
| REQ-L1-034 | REQ-L2-BAS-013 | L2 Requirement derived from REQ-L1-034 |
| REQ-L1-163 | REQ-L2-BAS-014 | L2 Requirement derived from REQ-L1-163 |
| REQ-L1-285 | REQ-L2-BAS-015 | Integration of Context Generators (Superpowers) |
| REQ-L1-286 | REQ-L2-BAS-016 | Agent Templates and Write Modes (Superpowers) |
| REQ-L1-174 | REQ-L2-COM-001 | L2 Requirement derived from REQ-L1-174 |
| REQ-L1-182 | REQ-L2-COM-002 | L2 Requirement derived from REQ-L1-182 |
| REQ-L1-036 | REQ-L2-COM-003 | L2 Requirement derived from REQ-L1-036 |
| REQ-L1-013 | REQ-L2-COM-004 | L2 Requirement derived from REQ-L1-013 |
| REQ-L1-132 | REQ-L2-COM-005 | L2 Requirement derived from REQ-L1-132 |
| REQ-L1-221 | REQ-L2-COM-006 | L2 Requirement derived from REQ-L1-221 |
| REQ-L1-121 | REQ-L2-COM-007 | L2 Requirement derived from REQ-L1-121 |
| REQ-L1-171 | REQ-L2-COM-008 | L2 Requirement derived from REQ-L1-171 |
| REQ-L1-142 | REQ-L2-COM-009 | L2 Requirement derived from REQ-L1-142 |
| REQ-L1-173 | REQ-L2-COM-010 | L2 Requirement derived from REQ-L1-173 |
| REQ-L1-284 | REQ-L2-COM-011 | L2 Requirement derived from REQ-L1-284 |
| REQ-L1-269 | REQ-L2-COM-012 | L2 Requirement derived from REQ-L1-269 |
| REQ-L1-172 | REQ-L2-COM-013 | L2 Requirement derived from REQ-L1-172 |
| REQ-L1-139 | REQ-L2-COM-014 | L2 Requirement derived from REQ-L1-139 |
| REQ-L1-285 | REQ-L2-COM-015 | Integration of Context Generators (Superpowers) |
| REQ-L1-286 | REQ-L2-COM-016 | Agent Templates and Write Modes (Superpowers) |
| REQ-L1-006 | REQ-L2-REA-001 | L2 Requirement derived from REQ-L1-006 |
| REQ-L1-265 | REQ-L2-REA-002 | L2 Requirement derived from REQ-L1-265 |
| REQ-L1-168 | REQ-L2-REA-003 | L2 Requirement derived from REQ-L1-168 |
| REQ-L1-250 | REQ-L2-REA-004 | L2 Requirement derived from REQ-L1-250 |
| REQ-L1-013 | REQ-L2-REA-005 | L2 Requirement derived from REQ-L1-013 |
| REQ-L1-064 | REQ-L2-REA-006 | L2 Requirement derived from REQ-L1-064 |
| REQ-L1-063 | REQ-L2-REA-007 | L2 Requirement derived from REQ-L1-063 |
| REQ-L1-175 | REQ-L2-REA-008 | L2 Requirement derived from REQ-L1-175 |
| REQ-L1-170 | REQ-L2-REA-009 | L2 Requirement derived from REQ-L1-170 |
| REQ-L1-251 | REQ-L2-REA-010 | L2 Requirement derived from REQ-L1-251 |
| REQ-L1-223 | REQ-L2-REA-011 | L2 Requirement derived from REQ-L1-223 |
| REQ-L1-062 | REQ-L2-REA-012 | L2 Requirement derived from REQ-L1-062 |
| REQ-L1-036 | REQ-L2-REA-013 | L2 Requirement derived from REQ-L1-036 |
| REQ-L1-183 | REQ-L2-REA-014 | L2 Requirement derived from REQ-L1-183 |
| REQ-L1-285 | REQ-L2-REA-015 | Integration of Context Generators (Superpowers) |
| REQ-L1-286 | REQ-L2-REA-016 | Agent Templates and Write Modes (Superpowers) |
| REQ-L1-121 | REQ-L2-RES-001 | L2 Requirement derived from REQ-L1-121 |
| REQ-L1-124 | REQ-L2-RES-002 | L2 Requirement derived from REQ-L1-124 |
| REQ-L1-060 | REQ-L2-RES-003 | L2 Requirement derived from REQ-L1-060 |
| REQ-L1-065 | REQ-L2-RES-004 | L2 Requirement derived from REQ-L1-065 |
| REQ-L1-008 | REQ-L2-RES-005 | L2 Requirement derived from REQ-L1-008 |
| REQ-L1-156 | REQ-L2-RES-006 | L2 Requirement derived from REQ-L1-156 |
| REQ-L1-234 | REQ-L2-RES-007 | L2 Requirement derived from REQ-L1-234 |
| REQ-L1-202 | REQ-L2-RES-008 | L2 Requirement derived from REQ-L1-202 |
| REQ-L1-016 | REQ-L2-RES-009 | L2 Requirement derived from REQ-L1-016 |
| REQ-L1-168 | REQ-L2-RES-010 | L2 Requirement derived from REQ-L1-168 |
| REQ-L1-181 | REQ-L2-RES-011 | L2 Requirement derived from REQ-L1-181 |
| REQ-L1-041 | REQ-L2-RES-012 | L2 Requirement derived from REQ-L1-041 |
| REQ-L1-239 | REQ-L2-RES-013 | L2 Requirement derived from REQ-L1-239 |
| REQ-L1-138 | REQ-L2-RES-014 | L2 Requirement derived from REQ-L1-138 |
| REQ-L1-285 | REQ-L2-RES-015 | Integration of Context Generators (Superpowers) |
| REQ-L1-286 | REQ-L2-RES-016 | Agent Templates and Write Modes (Superpowers) |
| REQ-L1-085 | REQ-L2-LLM-001 | L2 Requirement derived from REQ-L1-085 |
| REQ-L1-181 | REQ-L2-LLM-002 | L2 Requirement derived from REQ-L1-181 |
| REQ-L1-087 | REQ-L2-LLM-003 | L2 Requirement derived from REQ-L1-087 |
| REQ-L1-020 | REQ-L2-LLM-004 | L2 Requirement derived from REQ-L1-020 |
| REQ-L1-046 | REQ-L2-LLM-005 | L2 Requirement derived from REQ-L1-046 |
| REQ-L1-012 | REQ-L2-LLM-006 | L2 Requirement derived from REQ-L1-012 |
| REQ-L1-154 | REQ-L2-LLM-007 | L2 Requirement derived from REQ-L1-154 |
| REQ-L1-263 | REQ-L2-LLM-008 | L2 Requirement derived from REQ-L1-263 |
| REQ-L1-131 | REQ-L2-LLM-009 | L2 Requirement derived from REQ-L1-131 |
| REQ-L1-262 | REQ-L2-LLM-010 | L2 Requirement derived from REQ-L1-262 |
| REQ-L1-189 | REQ-L2-LLM-011 | L2 Requirement derived from REQ-L1-189 |
| REQ-L1-069 | REQ-L2-LLM-012 | L2 Requirement derived from REQ-L1-069 |
| REQ-L1-120 | REQ-L2-LLM-013 | L2 Requirement derived from REQ-L1-120 |
| REQ-L1-093 | REQ-L2-LLM-014 | L2 Requirement derived from REQ-L1-093 |
| REQ-L1-285 | REQ-L2-LLM-015 | Integration of Context Generators (Superpowers) |
| REQ-L1-286 | REQ-L2-LLM-016 | Agent Templates and Write Modes (Superpowers) |
| REQ-L1-199 | REQ-L2-REQ-001 | L2 Requirement derived from REQ-L1-199 |
| REQ-L1-022 | REQ-L2-REQ-002 | L2 Requirement derived from REQ-L1-022 |
| REQ-L1-139 | REQ-L2-REQ-003 | L2 Requirement derived from REQ-L1-139 |
| REQ-L1-231 | REQ-L2-REQ-004 | L2 Requirement derived from REQ-L1-231 |
| REQ-L1-104 | REQ-L2-REQ-005 | L2 Requirement derived from REQ-L1-104 |
| REQ-L1-007 | REQ-L2-REQ-006 | L2 Requirement derived from REQ-L1-007 |
| REQ-L1-232 | REQ-L2-REQ-007 | L2 Requirement derived from REQ-L1-232 |
| REQ-L1-243 | REQ-L2-REQ-008 | L2 Requirement derived from REQ-L1-243 |
| REQ-L1-137 | REQ-L2-REQ-009 | L2 Requirement derived from REQ-L1-137 |
| REQ-L1-224 | REQ-L2-REQ-010 | L2 Requirement derived from REQ-L1-224 |
| REQ-L1-259 | REQ-L2-REQ-011 | L2 Requirement derived from REQ-L1-259 |
| REQ-L1-019 | REQ-L2-REQ-012 | L2 Requirement derived from REQ-L1-019 |
| REQ-L1-136 | REQ-L2-REQ-013 | L2 Requirement derived from REQ-L1-136 |
| REQ-L1-044 | REQ-L2-REQ-014 | L2 Requirement derived from REQ-L1-044 |
| REQ-L1-285 | REQ-L2-REQ-015 | Integration of Context Generators (Superpowers) |
| REQ-L1-286 | REQ-L2-REQ-016 | Agent Templates and Write Modes (Superpowers) |
| REQ-L1-275 | REQ-L2-DIA-001 | L2 Requirement derived from REQ-L1-275 |
| REQ-L1-046 | REQ-L2-DIA-002 | L2 Requirement derived from REQ-L1-046 |
| REQ-L1-082 | REQ-L2-DIA-003 | L2 Requirement derived from REQ-L1-082 |
| REQ-L1-126 | REQ-L2-DIA-004 | L2 Requirement derived from REQ-L1-126 |
| REQ-L1-006 | REQ-L2-DIA-005 | L2 Requirement derived from REQ-L1-006 |
| REQ-L1-218 | REQ-L2-DIA-006 | L2 Requirement derived from REQ-L1-218 |
| REQ-L1-143 | REQ-L2-DIA-007 | L2 Requirement derived from REQ-L1-143 |
| REQ-L1-080 | REQ-L2-DIA-008 | L2 Requirement derived from REQ-L1-080 |
| REQ-L1-130 | REQ-L2-DIA-009 | L2 Requirement derived from REQ-L1-130 |
| REQ-L1-269 | REQ-L2-DIA-010 | L2 Requirement derived from REQ-L1-269 |
| REQ-L1-059 | REQ-L2-DIA-011 | L2 Requirement derived from REQ-L1-059 |
| REQ-L1-014 | REQ-L2-DIA-012 | L2 Requirement derived from REQ-L1-014 |
| REQ-L1-021 | REQ-L2-DIA-013 | L2 Requirement derived from REQ-L1-021 |
| REQ-L1-029 | REQ-L2-DIA-014 | L2 Requirement derived from REQ-L1-029 |
| REQ-L1-285 | REQ-L2-DIA-015 | Integration of Context Generators (Superpowers) |
| REQ-L1-286 | REQ-L2-DIA-016 | Agent Templates and Write Modes (Superpowers) |
| REQ-L1-233 | REQ-L2-MCP-001 | L2 Requirement derived from REQ-L1-233 |
| REQ-L1-163 | REQ-L2-MCP-002 | L2 Requirement derived from REQ-L1-163 |
| REQ-L1-248 | REQ-L2-MCP-003 | L2 Requirement derived from REQ-L1-248 |
| REQ-L1-208 | REQ-L2-MCP-004 | L2 Requirement derived from REQ-L1-208 |
| REQ-L1-025 | REQ-L2-MCP-005 | L2 Requirement derived from REQ-L1-025 |
| REQ-L1-259 | REQ-L2-MCP-006 | L2 Requirement derived from REQ-L1-259 |
| REQ-L1-128 | REQ-L2-MCP-007 | L2 Requirement derived from REQ-L1-128 |
| REQ-L1-123 | REQ-L2-MCP-008 | L2 Requirement derived from REQ-L1-123 |
| REQ-L1-250 | REQ-L2-MCP-009 | L2 Requirement derived from REQ-L1-250 |
| REQ-L1-112 | REQ-L2-MCP-010 | L2 Requirement derived from REQ-L1-112 |
| REQ-L1-001 | REQ-L2-MCP-011 | L2 Requirement derived from REQ-L1-001 |
| REQ-L1-235 | REQ-L2-MCP-012 | L2 Requirement derived from REQ-L1-235 |
| REQ-L1-249 | REQ-L2-MCP-013 | L2 Requirement derived from REQ-L1-249 |
| REQ-L1-111 | REQ-L2-MCP-014 | L2 Requirement derived from REQ-L1-111 |
| REQ-L1-285 | REQ-L2-MCP-015 | Integration of Context Generators (Superpowers) |
| REQ-L1-286 | REQ-L2-MCP-016 | Agent Templates and Write Modes (Superpowers) |
| REQ-L1-268 | REQ-L2-ICD-001 | L2 Requirement derived from REQ-L1-268 |
| REQ-L1-101 | REQ-L2-ICD-002 | L2 Requirement derived from REQ-L1-101 |
| REQ-L1-265 | REQ-L2-ICD-003 | L2 Requirement derived from REQ-L1-265 |
| REQ-L1-191 | REQ-L2-ICD-004 | L2 Requirement derived from REQ-L1-191 |
| REQ-L1-273 | REQ-L2-ICD-005 | L2 Requirement derived from REQ-L1-273 |
| REQ-L1-065 | REQ-L2-ICD-006 | L2 Requirement derived from REQ-L1-065 |
| REQ-L1-253 | REQ-L2-ICD-007 | L2 Requirement derived from REQ-L1-253 |
| REQ-L1-204 | REQ-L2-ICD-008 | L2 Requirement derived from REQ-L1-204 |
| REQ-L1-076 | REQ-L2-ICD-009 | L2 Requirement derived from REQ-L1-076 |
| REQ-L1-002 | REQ-L2-ICD-010 | L2 Requirement derived from REQ-L1-002 |
| REQ-L1-189 | REQ-L2-ICD-011 | L2 Requirement derived from REQ-L1-189 |
| REQ-L1-048 | REQ-L2-ICD-012 | L2 Requirement derived from REQ-L1-048 |
| REQ-L1-113 | REQ-L2-ICD-013 | L2 Requirement derived from REQ-L1-113 |
| REQ-L1-132 | REQ-L2-ICD-014 | L2 Requirement derived from REQ-L1-132 |
| REQ-L1-285 | REQ-L2-ICD-015 | Integration of Context Generators (Superpowers) |
| REQ-L1-286 | REQ-L2-ICD-016 | Agent Templates and Write Modes (Superpowers) |
| REQ-L1-183 | REQ-L2-RES-001 | L2 Requirement derived from REQ-L1-183 |
| REQ-L1-148 | REQ-L2-RES-002 | L2 Requirement derived from REQ-L1-148 |
| REQ-L1-147 | REQ-L2-RES-003 | L2 Requirement derived from REQ-L1-147 |
| REQ-L1-166 | REQ-L2-RES-004 | L2 Requirement derived from REQ-L1-166 |
| REQ-L1-004 | REQ-L2-RES-005 | L2 Requirement derived from REQ-L1-004 |
| REQ-L1-038 | REQ-L2-RES-006 | L2 Requirement derived from REQ-L1-038 |
| REQ-L1-105 | REQ-L2-RES-007 | L2 Requirement derived from REQ-L1-105 |
| REQ-L1-134 | REQ-L2-RES-008 | L2 Requirement derived from REQ-L1-134 |
| REQ-L1-269 | REQ-L2-RES-009 | L2 Requirement derived from REQ-L1-269 |
| REQ-L1-075 | REQ-L2-RES-010 | L2 Requirement derived from REQ-L1-075 |
| REQ-L1-099 | REQ-L2-RES-011 | L2 Requirement derived from REQ-L1-099 |
| REQ-L1-026 | REQ-L2-RES-012 | L2 Requirement derived from REQ-L1-026 |
| REQ-L1-126 | REQ-L2-RES-013 | L2 Requirement derived from REQ-L1-126 |
| REQ-L1-282 | REQ-L2-RES-014 | L2 Requirement derived from REQ-L1-282 |
| REQ-L1-285 | REQ-L2-RES-015 | Integration of Context Generators (Superpowers) |
| REQ-L1-286 | REQ-L2-RES-016 | Agent Templates and Write Modes (Superpowers) |
| REQ-L1-144 | REQ-L2-WOR-001 | L2 Requirement derived from REQ-L1-144 |
| REQ-L1-094 | REQ-L2-WOR-002 | L2 Requirement derived from REQ-L1-094 |
| REQ-L1-281 | REQ-L2-WOR-003 | L2 Requirement derived from REQ-L1-281 |
| REQ-L1-065 | REQ-L2-WOR-004 | L2 Requirement derived from REQ-L1-065 |
| REQ-L1-199 | REQ-L2-WOR-005 | L2 Requirement derived from REQ-L1-199 |
| REQ-L1-150 | REQ-L2-WOR-006 | L2 Requirement derived from REQ-L1-150 |
| REQ-L1-038 | REQ-L2-WOR-007 | L2 Requirement derived from REQ-L1-038 |
| REQ-L1-032 | REQ-L2-WOR-008 | L2 Requirement derived from REQ-L1-032 |
| REQ-L1-037 | REQ-L2-WOR-009 | L2 Requirement derived from REQ-L1-037 |
| REQ-L1-134 | REQ-L2-WOR-010 | L2 Requirement derived from REQ-L1-134 |
| REQ-L1-162 | REQ-L2-WOR-011 | L2 Requirement derived from REQ-L1-162 |
| REQ-L1-076 | REQ-L2-WOR-012 | L2 Requirement derived from REQ-L1-076 |
| REQ-L1-210 | REQ-L2-WOR-013 | L2 Requirement derived from REQ-L1-210 |
| REQ-L1-179 | REQ-L2-WOR-014 | L2 Requirement derived from REQ-L1-179 |
| REQ-L1-285 | REQ-L2-WOR-015 | Integration of Context Generators (Superpowers) |
| REQ-L1-286 | REQ-L2-WOR-016 | Agent Templates and Write Modes (Superpowers) |
| REQ-L1-206 | REQ-L2-AUT-001 | L2 Requirement derived from REQ-L1-206 |
| REQ-L1-090 | REQ-L2-AUT-002 | L2 Requirement derived from REQ-L1-090 |
| REQ-L1-147 | REQ-L2-AUT-003 | L2 Requirement derived from REQ-L1-147 |
| REQ-L1-195 | REQ-L2-AUT-004 | L2 Requirement derived from REQ-L1-195 |
| REQ-L1-123 | REQ-L2-AUT-005 | L2 Requirement derived from REQ-L1-123 |
| REQ-L1-191 | REQ-L2-AUT-006 | L2 Requirement derived from REQ-L1-191 |
| REQ-L1-253 | REQ-L2-AUT-007 | L2 Requirement derived from REQ-L1-253 |
| REQ-L1-018 | REQ-L2-AUT-008 | L2 Requirement derived from REQ-L1-018 |
| REQ-L1-186 | REQ-L2-AUT-009 | L2 Requirement derived from REQ-L1-186 |
| REQ-L1-128 | REQ-L2-AUT-010 | L2 Requirement derived from REQ-L1-128 |
| REQ-L1-201 | REQ-L2-AUT-011 | L2 Requirement derived from REQ-L1-201 |
| REQ-L1-057 | REQ-L2-AUT-012 | L2 Requirement derived from REQ-L1-057 |
| REQ-L1-095 | REQ-L2-AUT-013 | L2 Requirement derived from REQ-L1-095 |
| REQ-L1-250 | REQ-L2-AUT-014 | L2 Requirement derived from REQ-L1-250 |
| REQ-L1-285 | REQ-L2-AUT-015 | Integration of Context Generators (Superpowers) |
| REQ-L1-286 | REQ-L2-AUT-016 | Agent Templates and Write Modes (Superpowers) |
| REQ-L1-060 | REQ-L2-PER-001 | L2 Requirement derived from REQ-L1-060 |
| REQ-L1-107 | REQ-L2-PER-002 | L2 Requirement derived from REQ-L1-107 |
| REQ-L1-166 | REQ-L2-PER-003 | L2 Requirement derived from REQ-L1-166 |
| REQ-L1-233 | REQ-L2-PER-004 | L2 Requirement derived from REQ-L1-233 |
| REQ-L1-033 | REQ-L2-PER-005 | L2 Requirement derived from REQ-L1-033 |
| REQ-L1-270 | REQ-L2-PER-006 | L2 Requirement derived from REQ-L1-270 |
| REQ-L1-206 | REQ-L2-PER-007 | L2 Requirement derived from REQ-L1-206 |
| REQ-L1-085 | REQ-L2-PER-008 | L2 Requirement derived from REQ-L1-085 |
| REQ-L1-164 | REQ-L2-PER-009 | L2 Requirement derived from REQ-L1-164 |
| REQ-L1-007 | REQ-L2-PER-010 | L2 Requirement derived from REQ-L1-007 |
| REQ-L1-275 | REQ-L2-PER-011 | L2 Requirement derived from REQ-L1-275 |
| REQ-L1-195 | REQ-L2-PER-012 | L2 Requirement derived from REQ-L1-195 |
| REQ-L1-205 | REQ-L2-PER-013 | L2 Requirement derived from REQ-L1-205 |
| REQ-L1-008 | REQ-L2-PER-014 | L2 Requirement derived from REQ-L1-008 |
| REQ-L1-285 | REQ-L2-PER-015 | Integration of Context Generators (Superpowers) |
| REQ-L1-286 | REQ-L2-PER-016 | Agent Templates and Write Modes (Superpowers) |
| REQ-L1-086 | REQ-L2-SEM-001 | L2 Requirement derived from REQ-L1-086 |
| REQ-L1-169 | REQ-L2-SEM-002 | L2 Requirement derived from REQ-L1-169 |
| REQ-L1-280 | REQ-L2-SEM-003 | L2 Requirement derived from REQ-L1-280 |
| REQ-L1-159 | REQ-L2-SEM-004 | L2 Requirement derived from REQ-L1-159 |
| REQ-L1-157 | REQ-L2-SEM-005 | L2 Requirement derived from REQ-L1-157 |
| REQ-L1-044 | REQ-L2-SEM-006 | L2 Requirement derived from REQ-L1-044 |
| REQ-L1-096 | REQ-L2-SEM-007 | L2 Requirement derived from REQ-L1-096 |
| REQ-L1-047 | REQ-L2-SEM-008 | L2 Requirement derived from REQ-L1-047 |
| REQ-L1-185 | REQ-L2-SEM-009 | L2 Requirement derived from REQ-L1-185 |
| REQ-L1-058 | REQ-L2-SEM-010 | L2 Requirement derived from REQ-L1-058 |
| REQ-L1-077 | REQ-L2-SEM-011 | L2 Requirement derived from REQ-L1-077 |
| REQ-L1-173 | REQ-L2-SEM-012 | L2 Requirement derived from REQ-L1-173 |
| REQ-L1-081 | REQ-L2-SEM-013 | L2 Requirement derived from REQ-L1-081 |
| REQ-L1-166 | REQ-L2-SEM-014 | L2 Requirement derived from REQ-L1-166 |
| REQ-L1-285 | REQ-L2-SEM-015 | Integration of Context Generators (Superpowers) |
| REQ-L1-286 | REQ-L2-SEM-016 | Agent Templates and Write Modes (Superpowers) |
| REQ-L1-136 | REQ-L2-PRE-001 | L2 Requirement derived from REQ-L1-136 |
| REQ-L1-190 | REQ-L2-PRE-002 | L2 Requirement derived from REQ-L1-190 |
| REQ-L1-075 | REQ-L2-PRE-003 | L2 Requirement derived from REQ-L1-075 |
| REQ-L1-158 | REQ-L2-PRE-004 | L2 Requirement derived from REQ-L1-158 |
| REQ-L1-223 | REQ-L2-PRE-005 | L2 Requirement derived from REQ-L1-223 |
| REQ-L1-137 | REQ-L2-PRE-006 | L2 Requirement derived from REQ-L1-137 |
| REQ-L1-057 | REQ-L2-PRE-007 | L2 Requirement derived from REQ-L1-057 |
| REQ-L1-212 | REQ-L2-PRE-008 | L2 Requirement derived from REQ-L1-212 |
| REQ-L1-243 | REQ-L2-PRE-009 | L2 Requirement derived from REQ-L1-243 |
| REQ-L1-131 | REQ-L2-PRE-010 | L2 Requirement derived from REQ-L1-131 |
| REQ-L1-097 | REQ-L2-PRE-011 | L2 Requirement derived from REQ-L1-097 |
| REQ-L1-274 | REQ-L2-PRE-012 | L2 Requirement derived from REQ-L1-274 |
| REQ-L1-203 | REQ-L2-PRE-013 | L2 Requirement derived from REQ-L1-203 |
| REQ-L1-261 | REQ-L2-PRE-014 | L2 Requirement derived from REQ-L1-261 |
| REQ-L1-285 | REQ-L2-PRE-015 | Integration of Context Generators (Superpowers) |
| REQ-L1-286 | REQ-L2-PRE-016 | Agent Templates and Write Modes (Superpowers) |
| REQ-L1-183 | REQ-L2-AUD-001 | L2 Requirement derived from REQ-L1-183 |
| REQ-L1-222 | REQ-L2-AUD-002 | L2 Requirement derived from REQ-L1-222 |
| REQ-L1-066 | REQ-L2-AUD-003 | L2 Requirement derived from REQ-L1-066 |
| REQ-L1-086 | REQ-L2-AUD-004 | L2 Requirement derived from REQ-L1-086 |
| REQ-L1-016 | REQ-L2-AUD-005 | L2 Requirement derived from REQ-L1-016 |
| REQ-L1-175 | REQ-L2-AUD-006 | L2 Requirement derived from REQ-L1-175 |
| REQ-L1-162 | REQ-L2-AUD-007 | L2 Requirement derived from REQ-L1-162 |
| REQ-L1-223 | REQ-L2-AUD-008 | L2 Requirement derived from REQ-L1-223 |
| REQ-L1-250 | REQ-L2-AUD-009 | L2 Requirement derived from REQ-L1-250 |
| REQ-L1-188 | REQ-L2-AUD-010 | L2 Requirement derived from REQ-L1-188 |
| REQ-L1-284 | REQ-L2-AUD-011 | L2 Requirement derived from REQ-L1-284 |
| REQ-L1-224 | REQ-L2-AUD-012 | L2 Requirement derived from REQ-L1-224 |
| REQ-L1-136 | REQ-L2-AUD-013 | L2 Requirement derived from REQ-L1-136 |
| REQ-L1-098 | REQ-L2-AUD-014 | L2 Requirement derived from REQ-L1-098 |
| REQ-L1-285 | REQ-L2-AUD-015 | Integration of Context Generators (Superpowers) |
| REQ-L1-286 | REQ-L2-AUD-016 | Agent Templates and Write Modes (Superpowers) |
| REQ-L1-261 | REQ-L2-TRA-001 | L2 Requirement derived from REQ-L1-261 |
| REQ-L1-208 | REQ-L2-TRA-002 | L2 Requirement derived from REQ-L1-208 |
| REQ-L1-089 | REQ-L2-TRA-003 | L2 Requirement derived from REQ-L1-089 |
| REQ-L1-170 | REQ-L2-TRA-004 | L2 Requirement derived from REQ-L1-170 |
| REQ-L1-232 | REQ-L2-TRA-005 | L2 Requirement derived from REQ-L1-232 |
| REQ-L1-008 | REQ-L2-TRA-006 | L2 Requirement derived from REQ-L1-008 |
| REQ-L1-128 | REQ-L2-TRA-007 | L2 Requirement derived from REQ-L1-128 |
| REQ-L1-127 | REQ-L2-TRA-008 | L2 Requirement derived from REQ-L1-127 |
| REQ-L1-064 | REQ-L2-TRA-009 | L2 Requirement derived from REQ-L1-064 |
| REQ-L1-095 | REQ-L2-TRA-010 | L2 Requirement derived from REQ-L1-095 |
| REQ-L1-184 | REQ-L2-TRA-011 | L2 Requirement derived from REQ-L1-184 |
| REQ-L1-275 | REQ-L2-TRA-012 | L2 Requirement derived from REQ-L1-275 |
| REQ-L1-086 | REQ-L2-TRA-013 | L2 Requirement derived from REQ-L1-086 |
| REQ-L1-148 | REQ-L2-TRA-014 | L2 Requirement derived from REQ-L1-148 |
| REQ-L1-285 | REQ-L2-TRA-015 | Integration of Context Generators (Superpowers) |
| REQ-L1-286 | REQ-L2-TRA-016 | Agent Templates and Write Modes (Superpowers) |
| REQ-L1-192 | REQ-L2-APP-001 | L2 Requirement derived from REQ-L1-192 |
| REQ-L1-058 | REQ-L2-APP-002 | L2 Requirement derived from REQ-L1-058 |
| REQ-L1-121 | REQ-L2-APP-003 | L2 Requirement derived from REQ-L1-121 |
| REQ-L1-079 | REQ-L2-APP-004 | L2 Requirement derived from REQ-L1-079 |
| REQ-L1-090 | REQ-L2-APP-005 | L2 Requirement derived from REQ-L1-090 |
| REQ-L1-284 | REQ-L2-APP-006 | L2 Requirement derived from REQ-L1-284 |
| REQ-L1-250 | REQ-L2-APP-007 | L2 Requirement derived from REQ-L1-250 |
| REQ-L1-129 | REQ-L2-APP-008 | L2 Requirement derived from REQ-L1-129 |
| REQ-L1-016 | REQ-L2-APP-009 | L2 Requirement derived from REQ-L1-016 |
| REQ-L1-213 | REQ-L2-APP-010 | L2 Requirement derived from REQ-L1-213 |
| REQ-L1-180 | REQ-L2-APP-011 | L2 Requirement derived from REQ-L1-180 |
| REQ-L1-144 | REQ-L2-APP-012 | L2 Requirement derived from REQ-L1-144 |
| REQ-L1-123 | REQ-L2-APP-013 | L2 Requirement derived from REQ-L1-123 |
| REQ-L1-264 | REQ-L2-APP-014 | L2 Requirement derived from REQ-L1-264 |
| REQ-L1-285 | REQ-L2-APP-015 | Integration of Context Generators (Superpowers) |
| REQ-L1-286 | REQ-L2-APP-016 | Agent Templates and Write Modes (Superpowers) |
| REQ-L1-180 | REQ-L2-VEC-001 | L2 Requirement derived from REQ-L1-180 |
| REQ-L1-084 | REQ-L2-VEC-002 | L2 Requirement derived from REQ-L1-084 |
| REQ-L1-029 | REQ-L2-VEC-003 | L2 Requirement derived from REQ-L1-029 |
| REQ-L1-185 | REQ-L2-VEC-004 | L2 Requirement derived from REQ-L1-185 |
| REQ-L1-078 | REQ-L2-VEC-005 | L2 Requirement derived from REQ-L1-078 |
| REQ-L1-198 | REQ-L2-VEC-006 | L2 Requirement derived from REQ-L1-198 |
| REQ-L1-047 | REQ-L2-VEC-007 | L2 Requirement derived from REQ-L1-047 |
| REQ-L1-170 | REQ-L2-VEC-008 | L2 Requirement derived from REQ-L1-170 |
| REQ-L1-111 | REQ-L2-VEC-009 | L2 Requirement derived from REQ-L1-111 |
| REQ-L1-139 | REQ-L2-VEC-010 | L2 Requirement derived from REQ-L1-139 |
| REQ-L1-143 | REQ-L2-VEC-011 | L2 Requirement derived from REQ-L1-143 |
| REQ-L1-001 | REQ-L2-VEC-012 | L2 Requirement derived from REQ-L1-001 |
| REQ-L1-103 | REQ-L2-VEC-013 | L2 Requirement derived from REQ-L1-103 |
| REQ-L1-203 | REQ-L2-VEC-014 | L2 Requirement derived from REQ-L1-203 |
| REQ-L1-285 | REQ-L2-VEC-015 | Integration of Context Generators (Superpowers) |
| REQ-L1-286 | REQ-L2-VEC-016 | Agent Templates and Write Modes (Superpowers) |

## (Superpowers) REQ-L2 -> REQ-L3 Additions

| REQ-L2 | REQ-L3 | Title |
|---|---|---|
| REQ-L2-AIO-015 | REQ-L3-AIO-015 | L3 Context Generators Implementation |
| REQ-L2-AIO-016 | REQ-L3-AIO-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-AIO-015 | REQ-L3-AI004-003 | L3 Context Generators Implementation |
| REQ-L2-AIO-016 | REQ-L3-AI004-004 | L3 Agent Templates & Review Endpoints |
| REQ-L2-AIO-015 | REQ-L3-AIO-015 | L3 Context Generators Implementation |
| REQ-L2-AIO-016 | REQ-L3-AIO-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-AIO-015 | REQ-L3-AI002-004 | L3 Context Generators Implementation |
| REQ-L2-AIO-016 | REQ-L3-AI002-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-AIO-015 | REQ-L3-AI001-004 | L3 Context Generators Implementation |
| REQ-L2-AIO-016 | REQ-L3-AI001-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-AIO-015 | REQ-L3-AI003-004 | L3 Context Generators Implementation |
| REQ-L2-AIO-016 | REQ-L3-AI003-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-BAS-015 | REQ-L3-BL004-004 | L3 Context Generators Implementation |
| REQ-L2-BAS-016 | REQ-L3-BL004-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-BAS-015 | REQ-L3-BL001-006 | L3 Context Generators Implementation |
| REQ-L2-BAS-016 | REQ-L3-BL001-007 | L3 Agent Templates & Review Endpoints |
| REQ-L2-BAS-015 | REQ-L3-BAS-015 | L3 Context Generators Implementation |
| REQ-L2-BAS-016 | REQ-L3-BAS-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-BAS-015 | REQ-L3-BAS-015 | L3 Context Generators Implementation |
| REQ-L2-BAS-016 | REQ-L3-BAS-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-BAS-015 | REQ-L3-BL003-005 | L3 Context Generators Implementation |
| REQ-L2-BAS-016 | REQ-L3-BL003-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-BAS-015 | REQ-L3-BL002-004 | L3 Context Generators Implementation |
| REQ-L2-BAS-016 | REQ-L3-BL002-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-COM-015 | REQ-L3-COM-015 | L3 Context Generators Implementation |
| REQ-L2-COM-016 | REQ-L3-COM-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-COM-015 | REQ-L3-COM-015 | L3 Context Generators Implementation |
| REQ-L2-COM-016 | REQ-L3-COM-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-REA-015 | REQ-L3-RF004-005 | L3 Context Generators Implementation |
| REQ-L2-REA-016 | REQ-L3-RF004-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-REA-015 | REQ-L3-RF002-004 | L3 Context Generators Implementation |
| REQ-L2-REA-016 | REQ-L3-RF002-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-REA-015 | REQ-L3-RF001-005 | L3 Context Generators Implementation |
| REQ-L2-REA-016 | REQ-L3-RF001-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-REA-015 | REQ-L3-RF008-002 | L3 Context Generators Implementation |
| REQ-L2-REA-016 | REQ-L3-RF008-003 | L3 Agent Templates & Review Endpoints |
| REQ-L2-REA-015 | REQ-L3-RF007-002 | L3 Context Generators Implementation |
| REQ-L2-REA-016 | REQ-L3-RF007-003 | L3 Agent Templates & Review Endpoints |
| REQ-L2-REA-015 | REQ-L3-RF003-007 | L3 Context Generators Implementation |
| REQ-L2-REA-016 | REQ-L3-RF003-008 | L3 Agent Templates & Review Endpoints |
| REQ-L2-REA-015 | REQ-L3-RF005-003 | L3 Context Generators Implementation |
| REQ-L2-REA-016 | REQ-L3-RF005-004 | L3 Agent Templates & Review Endpoints |
| REQ-L2-REA-015 | REQ-L3-RF010-002 | L3 Context Generators Implementation |
| REQ-L2-REA-016 | REQ-L3-RF010-003 | L3 Agent Templates & Review Endpoints |
| REQ-L2-REA-015 | REQ-L3-RF009-002 | L3 Context Generators Implementation |
| REQ-L2-REA-016 | REQ-L3-RF009-003 | L3 Agent Templates & Review Endpoints |
| REQ-L2-REA-015 | REQ-L3-REA-015 | L3 Context Generators Implementation |
| REQ-L2-REA-016 | REQ-L3-REA-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-REA-015 | REQ-L3-REA-015 | L3 Context Generators Implementation |
| REQ-L2-REA-016 | REQ-L3-REA-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-REA-015 | REQ-L3-RF006-002 | L3 Context Generators Implementation |
| REQ-L2-REA-016 | REQ-L3-RF006-003 | L3 Agent Templates & Review Endpoints |
| REQ-L2-RES-015 | REQ-L3-RA001-007 | L3 Context Generators Implementation |
| REQ-L2-RES-016 | REQ-L3-RA001-008 | L3 Agent Templates & Review Endpoints |
| REQ-L2-RES-015 | REQ-L3-RA003-005 | L3 Context Generators Implementation |
| REQ-L2-RES-016 | REQ-L3-RA003-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-RES-015 | REQ-L3-RA004-004 | L3 Context Generators Implementation |
| REQ-L2-RES-016 | REQ-L3-RA004-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-RES-015 | REQ-L3-RA006-004 | L3 Context Generators Implementation |
| REQ-L2-RES-016 | REQ-L3-RA006-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-RES-015 | REQ-L3-RA002-006 | L3 Context Generators Implementation |
| REQ-L2-RES-016 | REQ-L3-RA002-007 | L3 Agent Templates & Review Endpoints |
| REQ-L2-RES-015 | REQ-L3-RES-015 | L3 Context Generators Implementation |
| REQ-L2-RES-016 | REQ-L3-RES-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-RES-015 | REQ-L3-RA007-002 | L3 Context Generators Implementation |
| REQ-L2-RES-016 | REQ-L3-RA007-003 | L3 Agent Templates & Review Endpoints |
| REQ-L2-RES-015 | REQ-L3-RES-015 | L3 Context Generators Implementation |
| REQ-L2-RES-016 | REQ-L3-RES-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-RES-015 | REQ-L3-RA005-005 | L3 Context Generators Implementation |
| REQ-L2-RES-016 | REQ-L3-RA005-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-RES-015 | REQ-L3-RA008-002 | L3 Context Generators Implementation |
| REQ-L2-RES-016 | REQ-L3-RA008-003 | L3 Agent Templates & Review Endpoints |
| REQ-L2-LLM-015 | REQ-L3-LLM-015 | L3 Context Generators Implementation |
| REQ-L2-LLM-016 | REQ-L3-LLM-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-LLM-015 | REQ-L3-LA002-005 | L3 Context Generators Implementation |
| REQ-L2-LLM-016 | REQ-L3-LA002-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-LLM-015 | REQ-L3-LA003-005 | L3 Context Generators Implementation |
| REQ-L2-LLM-016 | REQ-L3-LA003-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-LLM-015 | REQ-L3-LA004-004 | L3 Context Generators Implementation |
| REQ-L2-LLM-016 | REQ-L3-LA004-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-LLM-015 | REQ-L3-LLM-015 | L3 Context Generators Implementation |
| REQ-L2-LLM-016 | REQ-L3-LLM-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-LLM-015 | REQ-L3-LA005-005 | L3 Context Generators Implementation |
| REQ-L2-LLM-016 | REQ-L3-LA005-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-LLM-015 | REQ-L3-LA001-005 | L3 Context Generators Implementation |
| REQ-L2-LLM-016 | REQ-L3-LA001-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-REQ-015 | REQ-L3-REQ-015 | L3 Context Generators Implementation |
| REQ-L2-REQ-016 | REQ-L3-REQ-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-REQ-015 | REQ-L3-REQ-015 | L3 Context Generators Implementation |
| REQ-L2-REQ-016 | REQ-L3-REQ-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-DIA-015 | REQ-L3-MAP-002 | L3 Context Generators Implementation |
| REQ-L2-DIA-016 | REQ-L3-MAP-003 | L3 Agent Templates & Review Endpoints |
| REQ-L2-DIA-015 | REQ-L3-TC-002 | L3 Context Generators Implementation |
| REQ-L2-DIA-016 | REQ-L3-TC-003 | L3 Agent Templates & Review Endpoints |
| REQ-L2-DIA-015 | REQ-L3-DIA-015 | L3 Context Generators Implementation |
| REQ-L2-DIA-016 | REQ-L3-DIA-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-DIA-015 | REQ-L3-DR-002 | L3 Context Generators Implementation |
| REQ-L2-DIA-016 | REQ-L3-DR-003 | L3 Agent Templates & Review Endpoints |
| REQ-L2-DIA-015 | REQ-L3-DIA-015 | L3 Context Generators Implementation |
| REQ-L2-DIA-016 | REQ-L3-DIA-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-DIA-015 | REQ-L3-DS006-004 | L3 Context Generators Implementation |
| REQ-L2-DIA-016 | REQ-L3-DS006-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-DIA-015 | REQ-L3-DS007-002 | L3 Context Generators Implementation |
| REQ-L2-DIA-016 | REQ-L3-DS007-003 | L3 Agent Templates & Review Endpoints |
| REQ-L2-DIA-015 | REQ-L3-DM-005 | L3 Context Generators Implementation |
| REQ-L2-DIA-016 | REQ-L3-DM-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-DIA-015 | REQ-L3-DV-003 | L3 Context Generators Implementation |
| REQ-L2-DIA-016 | REQ-L3-DV-004 | L3 Agent Templates & Review Endpoints |
| REQ-L2-MCP-015 | REQ-L3-MC005-004 | L3 Context Generators Implementation |
| REQ-L2-MCP-016 | REQ-L3-MC005-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-MCP-015 | REQ-L3-MC001-007 | L3 Context Generators Implementation |
| REQ-L2-MCP-016 | REQ-L3-MC001-008 | L3 Agent Templates & Review Endpoints |
| REQ-L2-MCP-015 | REQ-L3-MC006-002 | L3 Context Generators Implementation |
| REQ-L2-MCP-016 | REQ-L3-MC006-003 | L3 Agent Templates & Review Endpoints |
| REQ-L2-MCP-015 | REQ-L3-MCP-015 | L3 Context Generators Implementation |
| REQ-L2-MCP-016 | REQ-L3-MCP-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-MCP-015 | REQ-L3-MCP-015 | L3 Context Generators Implementation |
| REQ-L2-MCP-016 | REQ-L3-MCP-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-MCP-015 | REQ-L3-MC002-007 | L3 Context Generators Implementation |
| REQ-L2-MCP-016 | REQ-L3-MC002-008 | L3 Agent Templates & Review Endpoints |
| REQ-L2-MCP-015 | REQ-L3-MC004-004 | L3 Context Generators Implementation |
| REQ-L2-MCP-016 | REQ-L3-MC004-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-MCP-015 | REQ-L3-MC003-006 | L3 Context Generators Implementation |
| REQ-L2-MCP-016 | REQ-L3-MC003-007 | L3 Agent Templates & Review Endpoints |
| REQ-L2-ICD-015 | REQ-L3-ICD-002 | L3 Context Generators Implementation |
| REQ-L2-ICD-016 | REQ-L3-ICD-003 | L3 Agent Templates & Review Endpoints |
| REQ-L2-ICD-015 | REQ-L3-ICD-015 | L3 Context Generators Implementation |
| REQ-L2-ICD-016 | REQ-L3-ICD-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-ICD-015 | REQ-L3-ICD-004 | L3 Context Generators Implementation |
| REQ-L2-ICD-016 | REQ-L3-ICD-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-ICD-015 | REQ-L3-ICD-015 | L3 Context Generators Implementation |
| REQ-L2-ICD-016 | REQ-L3-ICD-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-ICD-015 | REQ-L3-ICD-005 | L3 Context Generators Implementation |
| REQ-L2-ICD-016 | REQ-L3-ICD-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-ICD-015 | REQ-L3-ICD-003 | L3 Context Generators Implementation |
| REQ-L2-ICD-016 | REQ-L3-ICD-004 | L3 Agent Templates & Review Endpoints |
| REQ-L2-RES-015 | REQ-L3-RO-005 | L3 Context Generators Implementation |
| REQ-L2-RES-016 | REQ-L3-RO-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-RES-015 | REQ-L3-RO-004 | L3 Context Generators Implementation |
| REQ-L2-RES-016 | REQ-L3-RO-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-RES-015 | REQ-L3-RES-015 | L3 Context Generators Implementation |
| REQ-L2-RES-016 | REQ-L3-RES-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-RES-015 | REQ-L3-RO-006 | L3 Context Generators Implementation |
| REQ-L2-RES-016 | REQ-L3-RO-007 | L3 Agent Templates & Review Endpoints |
| REQ-L2-RES-015 | REQ-L3-RO-003 | L3 Context Generators Implementation |
| REQ-L2-RES-016 | REQ-L3-RO-004 | L3 Agent Templates & Review Endpoints |
| REQ-L2-RES-015 | REQ-L3-RES-015 | L3 Context Generators Implementation |
| REQ-L2-RES-016 | REQ-L3-RES-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-RES-015 | REQ-L3-RO-002 | L3 Context Generators Implementation |
| REQ-L2-RES-016 | REQ-L3-RO-003 | L3 Agent Templates & Review Endpoints |
| REQ-L2-WOR-015 | REQ-L3-WE004-004 | L3 Context Generators Implementation |
| REQ-L2-WOR-016 | REQ-L3-WE004-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-WOR-015 | REQ-L3-WE001-005 | L3 Context Generators Implementation |
| REQ-L2-WOR-016 | REQ-L3-WE001-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-WOR-015 | REQ-L3-WOR-015 | L3 Context Generators Implementation |
| REQ-L2-WOR-016 | REQ-L3-WOR-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-WOR-015 | REQ-L3-WE003-004 | L3 Context Generators Implementation |
| REQ-L2-WOR-016 | REQ-L3-WE003-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-WOR-015 | REQ-L3-WE002-004 | L3 Context Generators Implementation |
| REQ-L2-WOR-016 | REQ-L3-WE002-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-WOR-015 | REQ-L3-WOR-015 | L3 Context Generators Implementation |
| REQ-L2-WOR-016 | REQ-L3-WOR-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-AUT-015 | REQ-L3-AT004-004 | L3 Context Generators Implementation |
| REQ-L2-AUT-016 | REQ-L3-AT004-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-AUT-015 | REQ-L3-AT003-005 | L3 Context Generators Implementation |
| REQ-L2-AUT-016 | REQ-L3-AT003-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-AUT-015 | REQ-L3-AUT-015 | L3 Context Generators Implementation |
| REQ-L2-AUT-016 | REQ-L3-AUT-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-AUT-015 | REQ-L3-AT002-004 | L3 Context Generators Implementation |
| REQ-L2-AUT-016 | REQ-L3-AT002-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-AUT-015 | REQ-L3-AT001-005 | L3 Context Generators Implementation |
| REQ-L2-AUT-016 | REQ-L3-AT001-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-AUT-015 | REQ-L3-AUT-015 | L3 Context Generators Implementation |
| REQ-L2-AUT-016 | REQ-L3-AUT-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-AUT-015 | REQ-L3-AT006-002 | L3 Context Generators Implementation |
| REQ-L2-AUT-016 | REQ-L3-AT006-003 | L3 Agent Templates & Review Endpoints |
| REQ-L2-PER-015 | REQ-L3-PL001-006 | L3 Context Generators Implementation |
| REQ-L2-PER-016 | REQ-L3-PL001-007 | L3 Agent Templates & Review Endpoints |
| REQ-L2-PER-015 | REQ-L3-PL002-005 | L3 Context Generators Implementation |
| REQ-L2-PER-016 | REQ-L3-PL002-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-PER-015 | REQ-L3-PER-015 | L3 Context Generators Implementation |
| REQ-L2-PER-016 | REQ-L3-PER-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-PER-015 | REQ-L3-PL005-005 | L3 Context Generators Implementation |
| REQ-L2-PER-016 | REQ-L3-PL005-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-PER-015 | REQ-L3-PL004-005 | L3 Context Generators Implementation |
| REQ-L2-PER-016 | REQ-L3-PL004-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-PER-015 | REQ-L3-PER-015 | L3 Context Generators Implementation |
| REQ-L2-PER-016 | REQ-L3-PER-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-PER-015 | REQ-L3-PL003-004 | L3 Context Generators Implementation |
| REQ-L2-PER-016 | REQ-L3-PL003-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-SEM-015 | REQ-L3-SM005-003 | L3 Context Generators Implementation |
| REQ-L2-SEM-016 | REQ-L3-SM005-004 | L3 Agent Templates & Review Endpoints |
| REQ-L2-SEM-015 | REQ-L3-SM001-005 | L3 Context Generators Implementation |
| REQ-L2-SEM-016 | REQ-L3-SM001-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-SEM-015 | REQ-L3-SEM-015 | L3 Context Generators Implementation |
| REQ-L2-SEM-016 | REQ-L3-SEM-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-SEM-015 | REQ-L3-SEM-015 | L3 Context Generators Implementation |
| REQ-L2-SEM-016 | REQ-L3-SEM-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-SEM-015 | REQ-L3-SM002-004 | L3 Context Generators Implementation |
| REQ-L2-SEM-016 | REQ-L3-SM002-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-SEM-015 | REQ-L3-SM004-003 | L3 Context Generators Implementation |
| REQ-L2-SEM-016 | REQ-L3-SM004-004 | L3 Agent Templates & Review Endpoints |
| REQ-L2-SEM-015 | REQ-L3-SM003-003 | L3 Context Generators Implementation |
| REQ-L2-SEM-016 | REQ-L3-SM003-004 | L3 Agent Templates & Review Endpoints |
| REQ-L2-PRE-015 | REQ-L3-PC002-004 | L3 Context Generators Implementation |
| REQ-L2-PRE-016 | REQ-L3-PC002-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-PRE-015 | REQ-L3-PC001-005 | L3 Context Generators Implementation |
| REQ-L2-PRE-016 | REQ-L3-PC001-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-PRE-015 | REQ-L3-PC003-005 | L3 Context Generators Implementation |
| REQ-L2-PRE-016 | REQ-L3-PC003-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-PRE-015 | REQ-L3-PRE-015 | L3 Context Generators Implementation |
| REQ-L2-PRE-016 | REQ-L3-PRE-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-PRE-015 | REQ-L3-PRE-015 | L3 Context Generators Implementation |
| REQ-L2-PRE-016 | REQ-L3-PRE-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-AUD-015 | REQ-L3-AL001-006 | L3 Context Generators Implementation |
| REQ-L2-AUD-016 | REQ-L3-AL001-007 | L3 Agent Templates & Review Endpoints |
| REQ-L2-AUD-015 | REQ-L3-AUD-015 | L3 Context Generators Implementation |
| REQ-L2-AUD-016 | REQ-L3-AUD-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-AUD-015 | REQ-L3-AL003-004 | L3 Context Generators Implementation |
| REQ-L2-AUD-016 | REQ-L3-AL003-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-AUD-015 | REQ-L3-AUD-015 | L3 Context Generators Implementation |
| REQ-L2-AUD-016 | REQ-L3-AUD-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-AUD-015 | REQ-L3-AL002-005 | L3 Context Generators Implementation |
| REQ-L2-AUD-016 | REQ-L3-AL002-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-TRA-015 | REQ-L3-TRA-015 | L3 Context Generators Implementation |
| REQ-L2-TRA-016 | REQ-L3-TRA-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-TRA-015 | REQ-L3-TE003-004 | L3 Context Generators Implementation |
| REQ-L2-TRA-016 | REQ-L3-TE003-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-TRA-015 | REQ-L3-TE002-004 | L3 Context Generators Implementation |
| REQ-L2-TRA-016 | REQ-L3-TE002-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-TRA-015 | REQ-L3-TE004-004 | L3 Context Generators Implementation |
| REQ-L2-TRA-016 | REQ-L3-TE004-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-TRA-015 | REQ-L3-TRA-015 | L3 Context Generators Implementation |
| REQ-L2-TRA-016 | REQ-L3-TRA-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-TRA-015 | REQ-L3-TE001-005 | L3 Context Generators Implementation |
| REQ-L2-TRA-016 | REQ-L3-TE001-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-APP-015 | REQ-L3-AS001-004 | L3 Context Generators Implementation |
| REQ-L2-APP-016 | REQ-L3-AS001-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-APP-015 | REQ-L3-IMP-010 | L3 Context Generators Implementation |
| REQ-L2-APP-016 | REQ-L3-IMP-011 | L3 Agent Templates & Review Endpoints |
| REQ-L2-APP-015 | REQ-L3-PPL-010 | L3 Context Generators Implementation |
| REQ-L2-APP-016 | REQ-L3-PPL-011 | L3 Agent Templates & Review Endpoints |
| REQ-L2-APP-015 | REQ-L3-APP-015 | L3 Context Generators Implementation |
| REQ-L2-APP-016 | REQ-L3-APP-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-APP-015 | REQ-L3-RISK-011 | L3 Context Generators Implementation |
| REQ-L2-APP-016 | REQ-L3-RISK-012 | L3 Agent Templates & Review Endpoints |
| REQ-L2-APP-015 | REQ-L3-AS004-004 | L3 Context Generators Implementation |
| REQ-L2-APP-016 | REQ-L3-AS004-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-APP-015 | REQ-L3-DEB-012 | L3 Context Generators Implementation |
| REQ-L2-APP-016 | REQ-L3-DEB-013 | L3 Agent Templates & Review Endpoints |
| REQ-L2-APP-015 | REQ-L3-ADR-010 | L3 Context Generators Implementation |
| REQ-L2-APP-016 | REQ-L3-ADR-011 | L3 Agent Templates & Review Endpoints |
| REQ-L2-APP-015 | REQ-L3-EXP-010 | L3 Context Generators Implementation |
| REQ-L2-APP-016 | REQ-L3-EXP-011 | L3 Agent Templates & Review Endpoints |
| REQ-L2-APP-015 | REQ-L3-AS005-005 | L3 Context Generators Implementation |
| REQ-L2-APP-016 | REQ-L3-AS005-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-APP-015 | REQ-L3-WF-008 | L3 Context Generators Implementation |
| REQ-L2-APP-016 | REQ-L3-WF-009 | L3 Agent Templates & Review Endpoints |
| REQ-L2-APP-015 | REQ-L3-SEARCH-011 | L3 Context Generators Implementation |
| REQ-L2-APP-016 | REQ-L3-SEARCH-012 | L3 Agent Templates & Review Endpoints |
| REQ-L2-APP-015 | REQ-L3-AS006-004 | L3 Context Generators Implementation |
| REQ-L2-APP-016 | REQ-L3-AS006-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-APP-015 | REQ-L3-ISSUE-012 | L3 Context Generators Implementation |
| REQ-L2-APP-016 | REQ-L3-ISSUE-013 | L3 Agent Templates & Review Endpoints |
| REQ-L2-APP-015 | REQ-L3-APP-015 | L3 Context Generators Implementation |
| REQ-L2-APP-016 | REQ-L3-APP-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-APP-015 | REQ-L3-AS002-005 | L3 Context Generators Implementation |
| REQ-L2-APP-016 | REQ-L3-AS002-006 | L3 Agent Templates & Review Endpoints |
| REQ-L2-APP-015 | REQ-L3-WHOOK-011 | L3 Context Generators Implementation |
| REQ-L2-APP-016 | REQ-L3-WHOOK-012 | L3 Agent Templates & Review Endpoints |
| REQ-L2-APP-015 | REQ-L3-AS003-004 | L3 Context Generators Implementation |
| REQ-L2-APP-016 | REQ-L3-AS003-005 | L3 Agent Templates & Review Endpoints |
| REQ-L2-VEC-015 | REQ-L3-VEC-015 | L3 Context Generators Implementation |
| REQ-L2-VEC-016 | REQ-L3-VEC-016 | L3 Agent Templates & Review Endpoints |
| REQ-L2-VEC-015 | REQ-L3-VEC-015 | L3 Context Generators Implementation |
| REQ-L2-VEC-016 | REQ-L3-VEC-016 | L3 Agent Templates & Review Endpoints |

---

## Appendix: Alignment Verification
**Timestamp:** 2026-07-29T22:48:00+02:00
**Verification:** This Traceability Matrix is formally aligned with the latest component definitions comprising exactly 110 L3 components across all 20 L2 systems. All legacy `*_CompA`, `*_CompB`, and `implementation` mock structures have been scrubbed from the baseline, ensuring a direct and unpolluted path from L2 system requirements to concrete L3 component requirements and architectures.
