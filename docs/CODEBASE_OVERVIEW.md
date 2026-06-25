# ReqFlow — Codebase-Übersicht (IST-Zustand)

> **Status:** Greenfield-Implementierung abgeschlossen (SE-Kaskade → Code)  
> **Letzte Aktualisierung:** 2026-06-25  
> **Branch:** `feat/se-implementation`  
> **Validierung:** 1042/1042 Tests grün; `manage.py check` 0 Issues

---

## Übersicht

ReqFlow ist ein Requirements-Management-Tool mit AI- und Systems-Engineering-Support. Die Implementierung folgt einer SE-Kaskade (L0 → L1 → L2 → L3 → L4) mit 16 L2-Systemen auf dem Backend (Django-Apps), einer React-SPA im Frontend, und einer PostgreSQL-Datenbank mit Tenant-Isolation.

**Architektur-Schichten:**
- **Layer 0 (Foundation):** Persistierung, Auth/Tenancy, Konfiguration, Audit
- **Layer 1 (Domain Services):** LLM-Adapter, Traceability, Workflow, Baseline, Diagram, ICD
- **Layer 2 (Orchestration):** ApplicationService (16 Services, Single Entry Point)
- **Layer 3 (Interfaces):** REST API + MCP Server (20 Tools)
- **Layer 4 (Frontend):** React-SPA
- **Cross-Cutting:** SeMetrics (Read Model), ResilienceOrchestrator

---

## Backend-App-Struktur

### Layer 0: Foundation

#### `persistence/` (ARCH-L1-010)
**Modell:** ORM-Zentrum für alle L1-Entitäten; Tenant-Isolation via Row-Level Security + Custom Manager.

**Exportierte API:**
- `TenantScopedModel` — Base-Klasse mit automatischem `tenant_id`-Injection
- `AuditableModel` — Adds `created_at`, `updated_at`, `created_by`, `updated_by`
- `TenantContext` — Thread-Local Tenant-State
- `TenantContextNotSetError` — Error bei fehlendem Context
- `TenantManager.create()` — Injiziert `tenant_id` aus `TenantContext`
- `atomic_transaction()` — Decorator für DB-Transaktionen

**Zentrale Modelle (alle in `models.py`):**
```python
# Multi-Tenancy
Tenant(id, name, created_at)
User(tenant, email, role, is_active, password_hash)  # password_hash hinzugefügt Wave 7
Role(tenant, name, permissions)

# Core
Workspace(tenant, name, preset)
Artifact(workspace, artifact_type, state, ...)
Requirement(artifact, unique_id, title, description, status, ...)
ArchitectureElement(artifact, level, type_name, ...)
TestCase(artifact, ...)

# Lifecycle & Baseline
WorkflowDefinition(workspace, name, states, transitions)
WorkflowState(artifact, workflow_def, current_state)
Baseline(workspace, name, scope, created_at, created_by)
BaselineItem(baseline, artifact, artifact_version)

# Traceability
TraceLink(source_artifact, target_artifact, link_type)  # 8 Typen: TRACE_TO, DERIVED_FROM, etc.

# Audit
AuditLogEntry(tenant, entity_type, entity_id, operation, old_value, new_value, ...)
```

**Test-Coverage:** 1042 Tests (persistence-Anteil: ~150 Unit + Integration-Tests)

---

#### `auth_tenancy/` (ARCH-L1-011)
**Modell:** Authentifizierung (Bearer JWT + Passwort-Login), Autorisierung, Tenant-Context-Management.

**Exportierte API:**
```python
# Services
from auth_tenancy.services.tenant_context import TenantContext, TenantContextNotSetError, get_active_tenant
from auth_tenancy.services.authentication import authenticate_user, create_api_token, validate_password
from auth_tenancy.services.authorization import has_permission, get_user_roles

# REST Utilities
from auth_tenancy.rest import TenantPermission, AdminOnlyPermission  # DRF Permission-Klassen

# Exceptions
from auth_tenancy.errors import TenantContextError, UnauthorizedError

# Settings Keys
AUTH_JWT_SECRET, AUTH_JWT_ALGORITHM, AUTH_JWT_EXPIRY, DEMO_ADMIN_PASSWORD
```

**Komponenten:**
- `TenantMiddleware` — Extrahiert Tenant aus Request-Header/JWT
- `AuthenticationService` — Passwort-Validierung, Token-Generierung (neue Feature Wave 7)
- `AuthorizationService` — Role-Based Access Control (RBAC)
- `jwt_tokens.py` — Bearer-Token-Codecs (RS256 oder HS256)
- DRF Permission-Classes in `rest.py`

**Passwort-Login (REQ-L1-033, COMP-AT-004):**
- Endpoint: `POST /api/v1/auth/login` mit `email`, `password`
- Response: JWT Token + User-Details
- `manage.py seed_demo` erstellt Admin-Account (admin/admin12345)
- Passwort-Hash via `TenantScopedModel`; persistiert in `User.password_hash`

**Test-Coverage:** 10+ Integration-Tests (auth, tenant-isolation, JWT)

---

#### `presets/` (ARCH-L1-008)
**Modell:** Configurable Rigor — Konfiguriert pro Workspace Feldvalidierung, Sichtbarkeit, Workflows.

**Exportierte API:**
```python
from presets.services import (
    get_preset,                   # PresetInstance für workspace_id
    is_feature_enabled,           # Check ob Feature aktiv (z.B. "approval_workflows")
    get_terminology,              # Lokalisierte Artefakt-Bezeichnungen
    get_rigor_level,              # "minimal", "standard", "extended"
)
from presets.registry import PRESET_REGISTRY
from presets.terminology import TERMINOLOGY_PROFILES
```

**Komponenten:**
- `PresetRegistry` — 3 vordefinierte Presets (Minimal, Standard, Extended)
- `TerminologyProfile` — Lokalisierte Labels pro Zielgruppe (Agile vs. SE)
- `ConfigurableRigorGate` — Middleware/Decorator für Runtime-Validierung

**Presets:**
```python
{
    "minimal": {"approval_required": False, "baseline_scopes": ["document"], ...},
    "standard": {"approval_required": False, "baseline_scopes": ["document", "project"], ...},
    "extended": {"approval_required": True, "baseline_scopes": ["document", "project", "global"], ...}
}
```

---

#### `audit/` (ARCH-L1-012)
**Modell:** Operation-Level Audit Trail (Write-Once Log).

**Exportierte API:**
```python
from audit.services import (
    log_write,                    # log_write(entity_type, entity_id, operation, old_value, new_value, ...)
    query,                        # query(entity_type, entity_id, workspace_id)
)
from audit.writer import AuditWriter
from audit.events import AuditEvent
```

**Komponenten:**
- `AuditLogEntry` Model — Append-Only Persistence
- `AuditWriter` Service — Operation-Level Logging
- `AuditQuery` — Filtered Retrieval (entity, time-range, operation)
- DB-Trigger (Postgres) — Append-Only Enforcement

**Test-Coverage:** 9+ Tests

---

### Layer 1: Domain Services

#### `llm_adapter/` (ARCH-L1-009)
**Modell:** Pluggable LLM-Provider-Abstraktionen für Validation, Decomposition, Generation, Consistency-Checks.

**Exportierte API:**
```python
from llm_adapter.services import (
    validate_artifact,           # LlmCapabilityInterface.VALIDATE → CompletenessScore, Issues
    decompose_requirement,       # LlmCapabilityInterface.DECOMPOSE → List[ChildRequirement]
    check_consistency,           # LlmCapabilityInterface.CONSISTENCY → Bool, Issues
    generate_description,        # LlmCapabilityInterface.GENERATE → String (draft)
)
```

**Komponenten:**
- `LlmCapabilityInterface` — Enum der 4 Capabilities
- `LlmProviderAdapter` (ABC) — Basis für Claude, OpenAI, Ollama
- `GracefulDegradation` — Fallback wenn `LLM_PROVIDER` nicht konfiguriert
- Provider-Impls: `AnthropicAdapter`, `OpenAiAdapter`, `OllamaAdapter`

**Test-Coverage:** 55 Tests grün (Provider-Mocks)

---

#### `traceability/` (ARCH-L1-007)
**Modell:** Traceability-Queries und Link-Management über alle Artefakt-Typen.

**Exportierte API:**
```python
from traceability.services import (
    query,                        # query(source_id, link_type="TRACE_TO") → List[TraceLink]
    coverage,                     # coverage(requirement_id, workspace_id) → Coverage%
    create_trace_link,            # create_trace_link(source, target, link_type)
    collect_trace_graph,          # collect_trace_graph(root_artifact_id) → NetworkX Graph
)
```

**Link-Typen (8):**
- TRACE_TO, DERIVED_FROM, IMPLEMENTS, TESTS, VERIFIES, RELATED_TO, CONFLICTS_WITH, SUPERCEDES

**Komponenten:**
- `TraceLink` Model (in persistence)
- `TraceabilityQueryService` — Graph-Traversal
- `TraceLinkValidator` — Bidirektionale Konsistenz
- Coverage-Aggregator — Prozentuale Abdeckung

**Test-Coverage:** 13+ Tests

---

#### `workflow/` (ARCH-L1-005)
**Modell:** Konfigurierbare State Machines pro Workspace über WorkflowDefinition.

**Exportierte API:**
```python
from workflow.services import (
    transition,                   # transition(artifact_id, new_state, reason="...") → Result
    initialize_workflow_states,   # initialize_workflow_states(workspace_id, workflow_def_id)
    list_valid_transitions,       # list_valid_transitions(artifact_id) → List[State]
)
```

**Komponenten:**
- `WorkflowDefinition` Model — Konfigurierbar pro Workspace
- `WorkflowState` Model — Artifact-Zustands-Tracking
- `StateTransitionValidator` — Validiert erlaubte Übergänge
- Hooks für ApprovalService, NotificationService (Stubs in v1)

**Presets beeinflussen:** Ob Approval bei bestimmten Übergängen erforderlich ist

**Test-Coverage:** 9+ Tests

---

#### `baseline/` (ARCH-L1-006)
**Modell:** Snapshot-basierte Baselines auf 3 Scopes (Document, Project, Global).

**Exportierte API:**
```python
from baseline.services import (
    build,                        # build(workspace_id, scope, include_artifacts=[...]) → Baseline
    diff,                         # diff(baseline1_id, baseline2_id) → Diff
    get,                          # get(baseline_id) → Baseline + Items
    list_baselines,               # list_baselines(workspace_id, scope="project") → List[Baseline]
    get_item_at_baseline,         # get_item_at_baseline(artifact_id, baseline_id) → Version-Snapshot
)
```

**Komponenten:**
- `Baseline` Model — Name, Scope, Created-Metadata
- `BaselineItem` Model — Artifact-Version-Snapshot (JSON-Stored)
- `BaselineBuilder` — Snapshot-Sammlung
- `BaselineComparator` — Diff-Engine

**Test-Coverage:** 9+ Tests

---

#### `diagram/` (ARCH-L1-013)
**Modell:** Diagramm-Rendering (SysML, UML, Architektur-Visualisierung).

**Exportierte API:**
```python
from diagram.services import (
    render_architecture_diagram,  # render(element_id, format="svg") → SVG-String
    render_requirement_tree,      # render(requirement_id) → Tree-Visualisierung
    get_supported_formats,        # ["svg", "png", "puml"]
)
```

**Komponenten:**
- `DiagramRenderer` (ABC) → SVG, PNG, PlantUML-Impls
- `ArchitectureVisualizer` — L1/L2 Element-Layouts
- `TraceGraphVisualizer` — Network-Graph-Rendering

**Test-Coverage:** 42 Tests grün

---

#### `icd/` (ARCH-L1-014)
**Modell:** Interface Control Document Management (Versionierung + Breaking-Change-Detection).

**Exportierte API:**
```python
from icd.services import (
    get_icd_versions,            # get_icd_versions(workspace_id) → List[IcdVersion]
    create_icd_version,          # create_icd_version(workspace_id, interfaces=[...], version="1.0")
    detect_breaking_changes,     # detect_breaking_changes(old_version, new_version) → List[Change]
)
```

**Komponenten:**
- `IcdVersion` Model — Immutable Interface-Definitionen
- `InterfaceChange` — Breaking/Non-Breaking Classification
- `IcdValidator` — Konsistenzprüfung

**Test-Coverage:** 12 Tests grün

---

### Layer 2: Orchestration

#### `application/` (ARCH-L1-004)
**Modell:** Central Facade mit 16 Domain Services (ADR-01: Single Entry Point). Alle höheren Schichten rufen nur `ApplicationService` auf.

**Exportierte API (16 Services):**
```python
from application.services import (
    # Core
    ArtifactService,              # CRUD Artifacts
    RequirementService,            # Requirement-spezifisch
    ArchitectureService,           # Architecture-Elements
    TestCaseService,               # Test-Management
    
    # Traceability & Baseline
    TraceabilityService,           # Link-Management
    BaselineService,               # Snapshot-Baselines
    
    # Workflow & State
    WorkflowService,               # State Transitions
    
    # AI-gestützte Services
    ValidationService,             # LLM-Validierung
    DecompositionService,          # LLM-Decomposition
    ConsistencyService,            # LLM-Konsistenz-Checks
    
    # Audit & Security
    AuditService,                  # Audit-Trail-Queries
    AuthorizationService,          # RBAC
    
    # Configuration
    ConfigurationService,          # Preset-Abruf
    
    # Analytics & Reporting
    MetricsService,                # KPIs, Coverage
    
    # Risk & Issue Management (Wave 7)
    RiskService,                   # Risk.query_risks_by_severity()
    IssueService,                  # Issue-Tracking
)
```

**Komponenten (13 im `services/` Subpackage):**
- `artifact_service.py` — `ArtifactService`
- `requirement_service.py` — `RequirementService`
- `architecture_service.py` — `ArchitectureService`
- `testcase_service.py` — `TestCaseService`
- `traceability_service.py` — `TraceabilityService` (delegiert zu Layer-1-Service)
- `baseline_service.py` — `BaselineService` (delegiert zu Layer-1-Service)
- `workflow_service.py` — `WorkflowService` (delegiert)
- `validation_service.py` — `ValidationService` (delegiert zu LlmAdapter)
- `decomposition_service.py` — `DecompositionService`
- `consistency_service.py` — `ConsistencyService`
- `audit_service.py` — `AuditService` (delegiert zu audit Layer-0)
- `authorization_service.py` — `AuthorizationService` (delegiert zu auth_tenancy)
- `configuration_service.py` — `ConfigurationService` (delegiert zu presets)
- `metrics_service.py` — `MetricsService`
- `risk_service.py` — `RiskService` (neu Wave 7)
- `issue_service.py` — `IssueService` (neu Wave 7)

**Signature (Beispiel):**
```python
class ArtifactService:
    def create(self, workspace_id: str, artifact_type: str, data: dict) -> Artifact: ...
    def read(self, artifact_id: str) -> Artifact: ...
    def update(self, artifact_id: str, data: dict) -> Artifact: ...
    def delete(self, artifact_id: str) -> None: ...
    def list(self, workspace_id: str, filters={}) -> List[Artifact]: ...
    def search(self, workspace_id: str, query: str) -> List[Artifact]: ...

class RiskService:
    def query_risks_by_severity(self, workspace_id: str, severity: str, ctx: TenantContext) -> List[Risk]: ...
```

**Extension-Punkte (steps):**
- `services_step2.py` — Zusätzliche Services (wird beim Init leer erzeugt)
- `services_step3.py` — Weitere Erweiterungen (wird beim Init leer erzeugt)

**Test-Coverage:** 131 Tests grün

---

### Layer 3: Interface Adapters

#### `rest_api/` (ARCH-L1-002)
**Modell:** Django REST Framework ViewSets + Serializers gegen ApplicationService. OpenAPI über `drf-spectacular`.

**Exportierte API (6 ViewSets):**
```python
# In rest_api/views/
class ArtifactViewSet(viewsets.ModelViewSet):
    # GET/POST /api/v1/artifacts/
    # GET/PUT/DELETE /api/v1/artifacts/{id}/
    
class RequirementViewSet(viewsets.ModelViewSet):
    # GET/POST /api/v1/requirements/
    # GET/PUT/DELETE /api/v1/requirements/{id}/

class ArchitectureViewSet(viewsets.ModelViewSet):
    # GET/POST /api/v1/architecture/
    # GET/PUT/DELETE /api/v1/architecture/{id}/

class TestCaseViewSet(viewsets.ModelViewSet):
    # GET/POST /api/v1/testcases/
    # GET/PUT/DELETE /api/v1/testcases/{id}/

class TraceabilityViewSet(viewsets.ViewSet):
    # GET /api/v1/traceability/links/?source={id}
    # POST /api/v1/traceability/links/ (create link)

class BaselineViewSet(viewsets.ViewSet):
    # GET /api/v1/baselines/?workspace={id}
    # POST /api/v1/baselines/ (create)
    # GET /api/v1/baselines/{id}/diff/?baseline2={id}
```

**Auth-Endpoints:**
```python
POST /api/v1/auth/login              # (new Wave 7) email + password → JWT
GET  /api/v1/auth/me                 # Current user details (from Bearer token)
POST /api/v1/auth/logout             # Optional (stateless, JWT in localStorage)
```

**Komponenten:**
- `views/` — 6 ViewSets
- `serializers/` — DRF Serializers mit Validation
- `permissions/` — DRF Permission-Klassen (TenantPermission, AdminOnlyPermission)
- `pagination/` — LimitOffsetPagination (default 50, max 500)
- `filters/` — SearchFilter, OrderingFilter

**Settings Integration:**
- `DEFAULT_AUTHENTICATION_CLASSES` → TokenAuthentication
- `DEFAULT_PERMISSION_CLASSES` → TenantPermission
- `AUTO_SCHEMA_CLASS` → drf-spectacular (OpenAPI 3.0)

**Test-Coverage:** 13+ Tests (Endpoint-Integration)

---

#### `mcp_server/` (ARCH-L1-003)
**Modell:** MCP-Server mit 20 Tools in 4 Gruppen, direkt gegen ApplicationService (ADR-01).

**Exportierte API (20 MCP Tools):**

**Group 1: Requirements (6 Tools)**
```
create_requirement      # name, description, status → Requirement ID
read_requirement        # requirement_id → Requirement object
update_requirement      # requirement_id, updates → updated Requirement
delete_requirement      # requirement_id → null
list_requirements       # workspace_id, filters → List[Requirement]
query_requirements      # workspace_id, query_string → List[Requirement]
```

**Group 2: Architecture (6 Tools)**
```
create_architecture     # name, level, type_name → Element ID
read_architecture       # element_id → Element object
update_architecture     # element_id, updates → updated Element
delete_architecture     # element_id → null
list_architecture       # workspace_id → List[Element]
verify_consistency      # workspace_id → bool, issues[]
```

**Group 3: Tests (5 Tools)**
```
create_testcase         # name, requirement_id → TestCase ID
read_testcase           # testcase_id → TestCase object
update_testcase         # testcase_id, updates → updated TestCase
execute_testcase        # testcase_id, inputs → result{passed, output, duration}
list_testcases          # workspace_id → List[TestCase]
```

**Group 4: Traceability (3 Tools)**
```
create_tracelink        # source_id, target_id, link_type → TraceLink ID
query_tracelinks        # artifact_id, direction="both" → List[TraceLink]
report_coverage         # requirement_id/workspace_id → coverage%
```

**Komponenten:**
- `server.py` — MCP Server-Instanz
- `tools/` — 4 Tool-Group-Module
- `handlers/` — Request-Handler pro Tool
- `schemas/` — JSON-Schema für Tool-Inputs/-Outputs

**Test-Coverage:** 71 Tests grün

---

### Cross-Cutting: Analytics & Resilience

#### `se_metrics/` (ARCH-L1-015)
**Modell:** Read-Model über audit, traceability, workflow, application für KPI-Aggregation.

**Exportierte API:**
```python
from se_metrics.services import (
    get_requirement_coverage,     # workspace_id → Coverage%
    get_defect_trend,            # workspace_id, days=30 → Trend
    get_risk_metrics,            # workspace_id → {high: n, medium: m, low: l}
    get_approval_cycle_time,     # workspace_id → avg_days
    query_metrics,               # workspace_id, metric_keys → MetricsSnapshot
)
```

**Komponenten:**
- `aggregators/` — Coverage, Defect, Risk, ApprovalCycle Aggregators
- `cache/` — Redis-Cache (optional, Celery-async in v2)
- `models.py` — MetricsSnapshot, TrendPoint (ggf. nur temporary cache)

**Test-Coverage:** 69 Tests grün

---

#### `resilience/` (ARCH-L1-016)
**Modell:** Cross-Cutting Retry/Circuit-Breaker/Timeout-Orchestrierung.

**Exportierte API:**
```python
from resilience.services import (
    with_retry,                   # Decorator: retry(max_attempts=3, backoff_factor=2)
    with_circuit_breaker,         # Decorator: circuit_breaker(failure_threshold=5)
    with_timeout,                 # Decorator: timeout(seconds=30)
)
```

**Komponenten:**
- `decorators/` — Retry, CircuitBreaker, Timeout Decorators
- `models.py` — CircuitBreakerState, RetryPolicy (persistent state)
- `exceptions/` — CircuitBreakerOpen, TimeoutError

**Test-Coverage:** 31 Tests grün

---

### Layer 4: Frontend

#### `frontend/` (ARCH-L1-001)
**Stack:** React 18 + TypeScript + Vitest + react-i18next

**Struktur:**
```
frontend/
  src/
    index.tsx                     # React Entry-Point (ReactDOM.render)
    App.tsx                       # Root Component
    api/
      client.ts                   # Axios-Client mit auto-Bearer-Token-Injection
      requirements.ts             # API-Wrapper für Requirements
      architecture.ts             # API-Wrapper für Architecture
      artifacts.ts                # API-Wrapper für Artifacts
      tracelinks.ts               # API-Wrapper für Traceability
      index.ts                    # Re-exports
    components/
      DashboardViews/             # Dashboard-Container
        useDashboardData.ts        # Custom Hook für Dashboard-Daten
      RequirementEditors/         # Requirement-CRUD
        useRequirementData.ts      # Custom Hook
      ArchitectureEditors/        # Architecture-CRUD
        useArchitectureData.ts     # Custom Hook
    context/
      index.ts                    # React Context (Auth, Tenant, Presets)
    types/
      index.ts                    # TypeScript Interfaces (Artifact, Requirement, etc.)
    i18n/
      index.ts                    # i18next Config (DE/EN)
    test/
      setup.ts                    # Vitest Setup
  package.json                    # Dependencies (React, Vite, react-i18next, etc.)
  vitest.config.ts                # Vitest Config
```

**Key Components (6 hauptsächliche):**
1. `DashboardViews` — Übersichts-Dashboards (Requirements, Architecture, Tests)
2. `RequirementEditors` — Requirement-Create/Edit/Delete Forms
3. `ArchitectureEditors` — Architecture-Element-Editor
4. `TestEditors` — Test-Case-Management
5. `TraceabilityViewer` — Trace-Link-Visualisierung
6. `BaselineManager` — Baseline-Verwaltung und Diff-Viewer

**Hooks:**
- `useDashboardData()` — Fetch via `api/requirements`, caching
- `useRequirementData(id)` — Load single requirement
- `useArchitectureData(id)` — Load architecture element
- `useAuthContext()` — Auth-State (Token, CurrentUser, Tenant)

**i18n:** DE/EN via react-i18next (Übersetzungen in `locales/`)

**Test-Coverage:** 34 Dateien; Vitest für Unit-Tests (bei Bedarf erweiterbar)

---

## Konfigurations-Referenzen

### settings.py (Key-Variablen)

```python
# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'reqflow'),
        'USER': os.getenv('DB_USER', 'postgres'),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}

# Installed Apps (16 + Django standard)
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'drf_spectacular',
    'persistence',
    'auth_tenancy',
    'presets',
    'audit',
    'llm_adapter',
    'traceability',
    'workflow',
    'baseline',
    'application',
    'rest_api',
    'mcp_server',
    'diagram',
    'icd',
    'se_metrics',
    'resilience',
]

# Authentication
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]
AUTH_JWT_SECRET = os.getenv('AUTH_JWT_SECRET', 'dev-secret-key')
AUTH_JWT_ALGORITHM = 'HS256'
AUTH_JWT_EXPIRY = 3600  # 1 hour
DEMO_ADMIN_PASSWORD = os.getenv('DEMO_ADMIN_PASSWORD', 'admin12345')

# DRF Config
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'auth_tenancy.rest.TenantPermission',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 50,
    'MAX_PAGE_SIZE': 500,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# LLM Config
LLM_PROVIDER = os.getenv('LLM_PROVIDER', 'anthropic')  # 'anthropic', 'openai', 'ollama', 'none'
LLM_API_KEY = os.getenv('LLM_API_KEY', '')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')

# Celery (optional, async in v2)
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379')

# Middleware
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'persistence.middleware.TenantMiddleware',  # Tenant-ID aus Header injizieren
    'auth_tenancy.middleware.AuthenticationMiddleware',  # JWT validieren
]
```

---

## Build- und Test-Kommandos

### Dev-Stack starten
```bash
docker-compose up
# Backend auf http://localhost:8000
# Frontend auf http://localhost:5173
# PostgreSQL auf localhost:5432
# Redis auf localhost:6379 (optional)
```

### Migrationen
```bash
docker-compose exec backend python manage.py migrate
docker-compose exec backend python manage.py makemigrations
```

### Demo-Daten
```bash
docker-compose exec backend python manage.py seed_demo
# Erstellt Tenant + Admin-User (admin@example.com / admin12345)
```

### Tests
```bash
# Alle Backend-Tests (1042 Tests)
docker-compose exec backend pytest

# Nach Änderungen (Auto-Test im CI)
docker-compose exec backend pytest -v --cov=backend --cov-report=html

# Unit-Tests einer App
docker-compose exec backend pytest backend/persistence/tests/

# Frontend-Tests
docker-compose exec frontend npm test
```

### Django Shell
```bash
docker-compose exec backend python manage.py shell
# from persistence.models import Tenant, User
# t = Tenant.objects.first()
```

### API-Docs
```
http://localhost:8000/api/schema/swagger-ui/   # OpenAPI 3.0
http://localhost:8000/api/schema/redoc/        # ReDoc
```

### Passwort-Login (neu)
```bash
# 1. Seed Demo (admin/admin12345)
docker-compose exec backend python manage.py seed_demo

# 2. Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com", "password":"admin12345"}'

# Response: {"access_token": "eyJ...", "user": {...}}

# 3. Use token
curl http://localhost:8000/api/v1/artifacts/ \
  -H "Authorization: Bearer eyJ..."
```

---

## Architektur-Highlights

### ADR-01: Single Entry Point
Alle höheren Schichten (REST, MCP) greifen auf `ApplicationService` zu. Es gibt keine REST→MCP-Verkettung oder direkte Layer-1-Aufrufe.

### ADR-03: Tenant-Isolation
- Row-Level Security in PostgreSQL
- `TenantContext` Thread-Local Singleton
- `TenantManager.create()` Injection
- Automatische `tenant_id`-Filterung in allen Queries

### ADR-05: Credential Authentication (Wave 7)
- Komponente `COMP-AT-004: CredentialAuthenticationService`
- Passwort-Hash in `persistence.User.password_hash`
- `POST /api/v1/auth/login` generiert JWT Token
- Disjunkt von `COMP-AT-001: TokenConsumption` (JWT-Validierung)

---

## Offene Integrations-Aufgaben (v1.1+)

1. **Celery-Broker-Wiring** — AsyncDispatcher, WebhookDispatcher, SeMetrics-Cache
2. **WebhookDispatcher → ResilienceOrchestrator Umverdrahtung** — TODO-Marker gesetzt
3. **Prod-Secrets via ENV** — `AUTH_JWT_SECRET`, `DEMO_ADMIN_PASSWORD`, LLM-Keys

---

**Zuletzt aktualisiert:** 2026-06-25 (Branch `feat/se-implementation`, Commit `b01414a`)
