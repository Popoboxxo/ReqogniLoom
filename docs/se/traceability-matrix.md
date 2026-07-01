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
