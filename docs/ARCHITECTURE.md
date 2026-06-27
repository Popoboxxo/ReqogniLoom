# ReqFlow — Architektur

> **Status:** Greenfield-Implementierung abgeschlossen + v1.1 Features (SE-Phasen 1–6)  
> **Letzte Aktualisierung:** 2026-06-27  
> **Branch:** `feat/se-implementation`  
> **Tech-Stack:** Django + React + PostgreSQL + Docker Compose  
> **Tests:** 1.130 pytest / 111 E2E (Playwright) | L0=13/22 (59%), L1+L2=183/186 (98,4%)

---

## Architektur-Übersicht

ReqFlow folgt einer **geschichteten SE-Kaskade** von der L0-Infrastruktur bis zur L4-Präsentation. Die Gesamtarchitektur wird formal in `docs/se/STRATEGY.md` (Strategie) und `docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Architecture.md` (L1-Spezifikation) definiert. Dieses Dokument gibt die Vogelperspektive und verweist auf detaillierte Quellen.

### SE-Kaskaden-Status

Die SE-Kaskade (Phasen 1–6) ist für das v2-Backlog abgeschlossen:

- **9 L1-REQs** zerlegt (PDF-Export, ReqIF, Test-Run, Test-Einspeisung, Kommentare, RAG, Item-RBAC, Artefakt-Diff, Baseline-Diff)
- **15 L2-REQs** definiert, **11 neue Komponenten** spezifiziert
- **3 neue Subsysteme** als v2.0 geplant: ReqIFServiceSystem (RQ), CommentServiceSystem (CM), VectorSearchServiceSystem (VS)
- **8 neue L1-Interfaces** registriert (IF-L1-032..039)
- **6 leaf REQs** (Pipeline B — 3 implementiert, 3 offen) + **3 continue REQs** (Pipeline C — v2.0)

| Pipeline | REQs | Status |
|----------|------|--------|
| **B — Implementiert** | REQ-L1-023 (PDF-Export), REQ-L1-035 (Test-Run), REQ-L1-040 (Artefakt-Diff) | ✅ v1.1 |
| **B — Offen** | REQ-L1-036 (Test-Einspeisung), REQ-L1-039 (Item-RBAC), REQ-L1-041 (Baseline-Diff) | 🟡 Pipeline B |
| **C — v2.0** | REQ-L1-034 (ReqIF), REQ-L1-037 (Kommentare), REQ-L1-038 (Vektorsuche) | 🔵 Pipeline C |

### Die 5 Architektur-Layer

```
┌─────────────────────────────────────────────┐
│ Layer 4: Frontend (React-SPA)               │  frontend/
├─────────────────────────────────────────────┤
│ Layer 3: Interface Adapters                 │  rest_api/, mcp_server/
│  - REST API (DRF)                           │
│  - MCP Server (20 Tools)                    │
├─────────────────────────────────────────────┤
│ Layer 2: Orchestration (ApplicationService) │  application/
│  - 19 Domain Services (16 Core + 3 v1.1)   │  (ADR-01: Single Entry Point)
├─────────────────────────────────────────────┤
│ Layer 1: Domain Services                    │  llm_adapter/, traceability/,
│  - LLM Adapter                              │  workflow/, baseline/,
│  - Traceability Engine                      │  diagram/, icd/
│  - Workflow Engine                          │
│  - Baseline Service                         │
│  - Diagram & ICD Services                   │
├─────────────────────────────────────────────┤
│ Layer 0: Foundation                         │  persistence/, auth_tenancy/,
│  - Persistence (ORM)                        │  presets/, audit/
│  - Auth & Tenancy                           │
│  - Configuration                            │
│  - Audit Log                                │
├─────────────────────────────────────────────┤
│ Cross-Cutting                               │  se_metrics/, resilience/
│  - Analytics & Metrics                      │
│  - Resilience (Retry/Circuit-Breaker)      │
└─────────────────────────────────────────────┘
```

---

## Schichtenmodell (geschichtet)

### Layer 0: Foundation (Infrastruktur)

**Zweck:** Stellen gemeinsame Dienste für alle höheren Schichten bereit: Persistierung, Authentifizierung, Konfiguration, Audit.

| System | App | Funktion | Abhängigkeiten |
|--------|-----|----------|----------------|
| **PersistenceLayer** (010) | `persistence` | ORM-Zentrum; alle Entitäten; Tenant-Isolation via RLS + Custom Manager | — |
| **AuthAndTenancy** (011) | `auth_tenancy` | JWT + Passwort-Auth; RBAC; TenantContext | Persistence |
| **PresetConfigEngine** (008) | `presets` | Configurable Rigor; Feldvalidierung + Sichtbarkeit pro Workspace | Persistence |
| **AuditLog** (012) | `audit` | Append-Only Operation-Level Audit Trail | Persistence |

**Design-Entscheidungen (ADRs):**
- **ADR-03:** Tenant-Isolation via Row-Level Security + Custom Django Manager (kein Schema-per-Tenant)
- **ADR-04:** Configurable Rigor als Single Source of Truth
- **ADR-10:** Operation-Level AuditLog in v1 (Feld-Level in v2)

**Exports (Service-Interfaces):**
- `TenantScopedModel`, `AuditableModel` — ORM-Base-Klassen
- `TenantContext`, `TenantManager` — Tenant-Isolation
- `PresetRegistry`, `is_feature_enabled()` — Feature-Konfiguration
- `log_write()`, `query()` — Audit-API

---

### Layer 1: Domain Services (Kernlogik)

**Zweck:** Implementieren Fachlogik über allen Artefakttypen hinweg: Traceability, Workflow, Baseline, LLM-Integration, Visualisierung.

| System | App | Funktion | Abhängigkeiten |
|--------|-----|----------|----------------|
| **LlmAdapter** (009) | `llm_adapter` | Pluggable LLM-Provider (Claude, OpenAI, Ollama); 4 Capabilities | Audit |
| **TraceabilityEngine** (007) | `traceability` | Traceability-Queries; Link-Verwaltung; Coverage-Aggregation | Persistence |
| **WorkflowEngine** (005) | `workflow` | Konfigurierbare State Machines pro Workspace | Persistence, Auth, Presets |
| **BaselineService** (006) | `baseline` | Snapshot-Baselines (3 Scopes); Diff-Engine | Persistence, Presets, Traceability |
| **DiagramService** (013) | `diagram` | Diagramm-Rendering (SVG, PNG, PlantUML) | — |
| **IcdManagement** (014) | `icd` | Interface Control Document Versioning + Breaking-Change-Detection | — |

**Design-Entscheidungen (ADRs):**
- **ADR-02:** LLM-Provider über `LlmCapabilityInterface` abstrahiert (Graceful Degradation)
- **ADR-06:** Item-Lifecycle als konfigurierbare WorkflowEngine (nicht hartcodierter Enum)
- **ADR-07:** Baselines auf 3 Scopes in einer Entität

**Exports (Service-Interfaces):**
- `validate_artifact()`, `decompose_requirement()`, `check_consistency()` — LLM-Services
- `query()`, `coverage()`, `create_trace_link()` — Traceability-API
- `transition()`, `initialize_workflow_states()` — Workflow-API
- `build()`, `diff()`, `get()` — Baseline-API

---

### Layer 2: Orchestration (Fassade)

**Zweck:** Single Entry Point für alle höheren Schichten. Koordiniert alle Layer-1-Services und Lower-Layer-Komponenten.

| System | App | Funktion | Abhängigkeiten |
|--------|-----|----------|----------------|
| **ApplicationService** (004) | `application` | 19 Domain Services (16 Core + 3 v1.1); Central Facade (ADR-01) | ALL Layer-1 + Layer-0 |

**16 Core Services + 3 v1.1:**
```
ArtifactService, RequirementService, ArchitectureService, TestCaseService,
TraceabilityService, BaselineService, WorkflowService,
ValidationService, DecompositionService, ConsistencyService,
AuditService, AuthorizationService, ConfigurationService,
MetricsService, RiskService, IssueService,

# v1.1 new
ImportService,         # CSV-Bulk-Import (COMP-AS-009)
TestRunService,        # Test-Run-Protokollierung (COMP-AS-017)
ArtifactDiffService,   # Strukturiertes Feld-Level-Diff (COMP-AS-019)
```

**Architektur-Invarianten:**
- REST-Adapter (Layer 3) ruft NUR ApplicationService auf
- MCP-Server (Layer 3) ruft NUR ApplicationService auf
- Kein direkter Zugriff auf Layer-1-Services von außen

**Exports (Service-Interfaces):**
- `from application.services import *` — alle 16 Services

---

### Layer 3: Interface Adapters (Externe Schnittstellen)

**Zweck:** Fassen HTTP-Requests und MCP-Tool-Aufrufe in ApplicationService-Calls um.

| System | App | Funktion | Abhängigkeiten |
|--------|-----|----------|----------------|
| **RestApiAdapter** (002) | `rest_api` | Django REST Framework ViewSets + DRF-spectacular (OpenAPI) | ApplicationService, Auth, Presets |
| **McpServer** (003) | `mcp_server` | MCP-Tool-Registry (20 Tools in 4 Gruppen) | ApplicationService, Auth, Audit, Presets |

**REST Endpoints (+ Auth-Endpoints, + v1.1):**
```
# Auth & Identity
POST   /api/v1/auth/login                 # Email + Password → JWT
GET    /api/v1/auth/me                    # Current User (Bearer Token)

# Core CRUD (ViewSets)
GET    /api/v1/artifacts/                 # +POST
GET    /api/v1/requirements/              # +POST, PATCH, DELETE
GET    /api/v1/architecture/              # +POST, PATCH, DELETE
GET    /api/v1/testcases/                 # +POST, PATCH, DELETE
GET    /api/v1/tracelinks/                # +POST, DELETE
GET    /api/v1/baselines/                 # +POST; GET /{id}/diff/?baseline2=
GET    /api/v1/workflows/                 # +POST, PATCH, DELETE
GET    /api/v1/workspaces/                # +POST, PATCH, DELETE; PATCH /{id}/preset/

# ADR / Risk / Issue
GET    /api/v1/adrs/                      # +POST, PATCH, DELETE
GET    /api/v1/risks/                     # +POST, PATCH, DELETE
GET    /api/v1/issues/                    # +POST, PATCH, DELETE

# Search & Diagrams
GET    /api/v1/search/?q=...              # Globale Suche
GET    /api/v1/diagrams/                  # Diagramm-Rendering
GET    /api/v1/icds/                      # ICD-Management
GET    /api/v1/metrics/                   # Metriken/KPIs

# v1.1 New Features
GET    /api/v1/requirements/{id}/history/ # Audit-Trail
GET    /api/v1/requirements/{id}/diff/    # Artifact-Diff (auch architecture, testcases)
GET    /api/v1/workspaces/{id}/reports/pdf/  # PDF-Export
POST   /api/v1/workspaces/{id}/import/csv/   # CSV-Bulk-Import
GET    /api/v1/test-runs/                 # +POST; GET /{id}/; POST /{id}/results/bulk/
GET    /api/v1/api-keys/                  # +POST; DELETE /{id}/
```

**MCP Tools (20 in 4 Gruppen):**
- **Requirements (6):** create, read, update, delete, list, query
- **Architecture (6):** create, read, update, delete, list, verify-consistency
- **Tests (5):** create, read, update, execute, list
- **Traceability (3):** create-link, query, report-coverage

**Design-Entscheidungen (ADRs):**
- **ADR-01:** REST und MCP sind Geschwister-Adapter, beide greifen auf ApplicationService zu (kein REST→MCP-Chaining)

**Exports:**
- REST-API über OpenAPI (Swagger UI, ReDoc)
- MCP-Server über nativen MCP-Protokoll-Stack

---

### Layer 4: Präsentation (Frontend)

**Zweck:** React-SPA mit TypeScript, i18n, Hooks-basierter Architektur.

| System | Stack | Funktion | Abhängigkeiten |
|--------|-------|----------|----------------|
| **ReactFrontend** (001) | React 18, TypeScript, Vite | Graphische Benutzeroberfläche; Dashboard, Requirement-/Architecture-Editoren | RestApiAdapter (/api/v1/) |

**Key Komponenten:**
- `DashboardViews` — Überblicke (Requirements, Architecture, Tests)
- `RequirementEditors` — Requirement-CRUD
- `ArchitectureEditors` — Architecture-Element-Editor
- `TraceabilityViewer` — Trace-Link-Visualisierung

**i18n:** Deutsch / Englisch via react-i18next

---

### Cross-Cutting: Analytics & Resilience

| System | App | Funktion | Abhängigkeiten |
|--------|-----|----------|----------------|
| **SeMetrics** (015) | `se_metrics` | Read Model über audit/workflow/traceability/application; KPIs | Layer-0, Layer-1 |
| **ResilienceOrchestrator** (016) | `resilience` | Retry, Circuit-Breaker, Timeout Decorators | — |

### Geplante Subsysteme (v2.0 — Pipeline C)

Drei neue Subsysteme wurden in der SE-Kaskade (Phasen 1–6) identifiziert, aber als `continue` terminiert — sie erfordern eine L3-Zerlegung und sind noch nicht implementiert:

| System | Akronym | App | Funktion | REQ-L1 | L2-REQs | Komponenten |
|--------|---------|-----|----------|--------|:-------:|:-----------:|
| **ReqIFServiceSystem** (017) | RQ | *geplant* | ReqIF-Import/Export (XML-Parser/Serializer) | REQ-L1-034 | 2 | COMP-RQ-001, COMP-RQ-002 |
| **CommentServiceSystem** (018) | CM | *geplant* | Kommentar-Threads, @Mention, Benachrichtigungen | REQ-L1-037 | 3 | COMP-CM-001..003 |
| **VectorSearchServiceSystem** (019) | VS | *geplant* | Semantische Vektorsuche, Embedding-Pipeline, pgvector | REQ-L1-038 | 3 | COMP-VS-001..003 |

**Schnittstellen (8 neue IF-L1):**
| ID | Quelle → Ziel | Vertrag | Status |
|----|---------------|---------|--------|
| IF-L1-032 | ApplicationService → VectorSearchService | Domain-Event Embedding Trigger (async) | spezifiziert |
| IF-L1-033 | AuthAndTenancy → PersistenceLayer | RLS-Policy-Enforcement | spezifiziert |
| IF-L1-034 | CommentService → AuditLogSystem | Audit-Log-Pflicht | spezifiziert |
| IF-L1-035 | ApplicationService ↔ ReqIFService | Import/Export Request (sync) | spezifiziert |
| IF-L1-036 | ReqIFService → TraceabilityEngine | SpecRelations → TraceLinks | spezifiziert |
| IF-L1-037 | ApplicationService ↔ CommentService | Comment CRUD Delegation | spezifiziert |
| IF-L1-038 | ApplicationService ↔ VectorSearchService | Semantic Search Query | spezifiziert |
| IF-L1-039 | CommentService → NotificationService | Mention Notification (STUB) | spezifiziert |

Alle Interfaces sind vollständig in `docs/se/interface-registry.md` §9–10 dokumentiert (Design-by-Contract).

---

## Persistierungs-Modell

### Zentrale Entitäten (in `persistence.models`)

```python
# Multi-Tenancy
Tenant(id, name, created_at)
User(tenant, email, role, is_active, password_hash)  # password_hash neu Wave 7
Role(tenant, name, permissions)

# Core
Workspace(tenant, name, preset)
Artifact(workspace, artifact_type, state, created_at, updated_at, created_by, updated_by)
Requirement(artifact, unique_id, title, description, status, ...)
ArchitectureElement(artifact, level, type_name, ...)
TestCase(artifact, ...)

# Lifecycle & Workflow
WorkflowDefinition(workspace, name, states, transitions)
WorkflowState(artifact, workflow_def, current_state)

# Baselines
Baseline(workspace, name, scope, created_at, created_by)
BaselineItem(baseline, artifact, artifact_version)  # JSON-Stored

# Traceability
TraceLink(source_artifact, target_artifact, link_type)  # 8 Typen

# Audit
AuditLogEntry(tenant, entity_type, entity_id, operation, old_value, new_value, ...)
```

### Tenant-Isolation (ADR-03)

**Mechanismus:**
1. `persistence.TenantMiddleware` extrahiert Tenant-ID aus Request-Header (oder JWT)
2. `TenantContext` speichert aktive Tenant-ID im Thread-Local
3. `TenantScopedModel.TenantManager` filtert automatisch alle Queries auf `tenant_id`
4. PostgreSQL Row-Level Security (RLS) zusätzliche Sicherheit

**Resultat:** Datenvermischung unmöglich; isolierte Multi-Tenancy skaliert bis 4-stellige Tenant-Zahlen.

---

## Authentication & Authorization (Wave 7)

### Dual-Mode: Bearer Token + Passwort

**Komponente:** `COMP-AT-004: CredentialAuthenticationService`

**Bearer Token (REST):**
- Header: `Authorization: Bearer <JWT>`
- Token-Format: RS256 oder HS256 (konfigurierbar)
- Gültigkeitsdauer: 1 Stunde (default)
- Persistiert in Frontend `localStorage`

**Passwort-Login (neu Wave 7):**
- Endpoint: `POST /api/v1/auth/login`
- Input: `email`, `password`
- Output: `access_token` (JWT), `user` Objekt
- Passwort-Hash in `User.password_hash` (bcrypt, Argon2, o.ä.)
- Demo-Seed: `admin@example.com` / `admin12345`

**Disjunktion (ADR-05):**
- `COMP-AT-004` (Credential Auth) = Passwort-Validierung + Token-Generierung
- `COMP-AT-001` (Token Consumption) = JWT-Validierung + User-Auflösung
- Beide sind separate, nicht verzahnte Services.

---

## Configurable Rigor

### Drei Presets (ADR-04)

Alle drei Presets nutzen **dasselbe Datenmodell**. Unterschiede:

| Preset | Approval | Baseline-Scopes | Audit-Detailgrad | Zielgruppe |
|--------|----------|-----------------|------------------|-----------|
| **Minimal** | Nein | Document | Operation-Level | Startups, AI-First Teams |
| **Standard** | Optional | Document, Project | Operation-Level | Mid-Market Software |
| **Extended** | Erzwungen | Document, Project, Global | Operation-Level (v2: Field-Level) | Systems Engineering |

**Implementierung:**
- `PresetRegistry` speichert Konfiguration pro Workspace
- `ConfigurableRigorGate` validiert zur Runtime ob Feld erforderlich/sichtbar/schreibbar ist
- Keine Datenmodell-Duplizierung, nur Regeln pro Preset

---

## Integration (Bottom-Up)

### Integrations-Strategie

Siehe `docs/se/integration-strategy.md` für formale Strategie. Kurz:

**Bottom-Up mit Sandwich-Elementen:**
1. **Layer 0** implementiert und testet Foundation
2. **Layer 1** implementiert auf Layer-0-Basis, teilweise parallel
3. **Layer 2** orchestriert Layer-1 (ADR-01: Single Entry Point)
4. **Layer 3** testet gegen verifizierten Layer-2/Layer-1-Core
5. **Layer 4** ist finale Integrations-Layer

**Dependencies:**
- ApplicationService (Layer 2) hängt von ALLEN Layer-1 + Layer-0 ab
- REST/MCP (Layer 3) hängen von ApplicationService ab
- Frontend (Layer 4) hängt von REST ab

---

## Test-Strategie

### Abdeckung (1130+ Tests)

```
Layer 0: ~300 Tests
├── persistence: Tenant-Isolation, Entity-Schema, Transactions
├── auth_tenancy: Auth-Flows, JWT, RBAC
├── presets: Preset-Registry, Terminology
└── audit: Append-Only, Log-Queries

Layer 1: ~400 Tests
├── llm_adapter: 55 Tests (Provider-Mocks)
├── traceability: 13+ Tests
├── workflow: 9+ Tests
├── baseline: 9+ Tests
├── diagram: 42 Tests
└── icd: 12 Tests

Layer 2: 131 Tests
└── application: Core-Services, Integrations

Layer 3: ~90 Tests
├── rest_api: 13+ Tests (Endpoint-Integration)
└── mcp_server: 71 Tests

Cross-Cutting: ~100 Tests
├── se_metrics: 69 Tests
└── resilience: 31 Tests
```

### Test-Befehl

```bash
docker-compose exec backend pytest              # Alle Tests (1130)
docker-compose exec backend pytest backend/persistence/  # Einzelne App
docker-compose exec frontend npm test            # Frontend
```

---

## Deployment (Docker Compose)

### Services

```yaml
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DJANGO_SETTINGS_MODULE=reqflow.settings
      - DB_HOST=postgres
      - AUTH_JWT_SECRET=<your-secret>
      - LLM_PROVIDER=anthropic
      - LLM_API_KEY=<key>
    depends_on:
      - postgres
      - redis

  frontend:
    build: ./frontend
    ports:
      - "5173:5173"
    environment:
      - VITE_API_URL=http://backend:8000/api/v1
    depends_on:
      - backend

  postgres:
    image: postgres:16
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_DB=reqflow
      - POSTGRES_PASSWORD=<pw>
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7
    ports:
      - "6379:6379"
    (optional für Celery)
```

### Startup

```bash
docker-compose build
docker-compose up
docker-compose exec backend python manage.py migrate
docker-compose exec backend python manage.py seed_demo
# http://localhost:8000 (Backend)
# http://localhost:5173 (Frontend)
```

---

## Architecture Decision Records (ADRs)

Alle ADRs sind in `backend/README.md` dokumentiert. Kurzform:

| ADR | Entscheidung | Grund |
|-----|-------------|-------|
| **ADR-01** | REST + MCP greifen beide direkt auf ApplicationService zu | Gleichrangige Adapter, kein HTTP-Overhead |
| **ADR-02** | LLM-Provider über `LlmCapabilityInterface` abstrahiert | Kein Vendor-Lock-in, Graceful Degradation |
| **ADR-03** | Tenant-Isolation via Row-Level + Custom Manager | Skaliert bis 4-stellige Tenant-Zahlen |
| **ADR-04** | Configurable Rigor als Single Source of Truth | Ein Datenmodell für alle Zielgruppen |
| **ADR-05** | Generisches Artefakt-Modell + Terminologie-Profile | Keine zielgruppen-spezifischen Code-Pfade |
| **ADR-06** | Item-Lifecycle als konfigurierbare WorkflowEngine | Flexible State-Machines statt Enums |
| **ADR-07** | Baselines auf 3 Scopes in einer Entität | Flexibilität ohne Datenmodell-Explosion |
| **ADR-08** | Docker Compose, nicht Kubernetes in v1 | Self-Hosted-Footprint minimieren |
| **ADR-09** | PostgreSQL Full-Text statt Search-Engine | Performance <500ms für 10k Items |
| **ADR-10** | AuditLog Operation-Level in v1, Feld-Level in v2 | Komplexität reduzieren |

---

## Detaillierte Architektur-Referenzen

**Formale SE-Dokumentation:**
- `docs/se/STRATEGY.md` — Strategische Entscheidungen
- `docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Architecture.md` — L1-Spezifikation (formale Anforderungen, Interfaces)
- `docs/se/L1/Gesamtsystem/L2/*/L2_*_Architecture.md` — 16 L2-Subsystem-Architekturen (detaillierte Komponenten-Spezifikationen)
- `docs/se/interface-registry.md` — Zentrale Schnittstellen-Registry (alle L1-Interfaces, L2-Interfaces + v2-Backlog IF-L1-032..039)
- `docs/se/integration-strategy.md` — Bottom-Up Integrations-Ansatz
- `docs/se/test-strategy.md` — 338+ Test-Szenarien (Model-Based Testing)
- `docs/se/reports/` — Session-Berichte (SE-Phasen 1–6, Implementation Reports)
  - `se-phase1-v2-backlog-2026-06-27.md` — V2-Backlog-Klarstellung
  - `se-phase6-termination-2026-06-27.md` — Leaf/Continue-Entscheidungen
  - `implementation_status_2026-06-27.md` — Implementierungsstand
- `docs/se/traceability-matrix.md` — REQ → SYS-REQ → COMP-REQ → TEST-CASE Mapping

**Code-Dokumentation:**
- `docs/CODEBASE_OVERVIEW.md` — Code-genaue Bestandsaufnahme (Funktionssignaturen, Tests, Dependencies)
- `backend/README.md` — App-Mapping, ADRs, Development Commands

---

**Zuletzt aktualisiert:** 2026-06-27 (Branch `feat/se-implementation`)
