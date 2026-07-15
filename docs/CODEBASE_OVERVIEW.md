# ReqFlow — Codebase-Übersicht (IST-Zustand)

> **Status:** Greenfield-Implementierung abgeschlossen + v1.1 Features (SE-Phasen 1–6) + Canvas/Mermaid (REQ-L1-056/057)  
> **Letzte Aktualisierung:** 2026-07-01  
> **Branch:** `feat/se-implementation`  
> **Validierung:** 1130/1130 pytest Tests grün; 111/112 E2E Tests (Playwright) grün; `manage.py check` 0 Issues

---

## Übersicht

ReqFlow ist ein Requirements-Management-Tool mit AI- und Systems-Engineering-Support. Die Implementierung folgt einer SE-Kaskade (L0 → L1 → L2 → L3 → L4) mit 16 L2-Systemen auf dem Backend (Django-Apps), einer React-SPA im Frontend, und einer PostgreSQL-Datenbank mit Tenant-Isolation.

**SE-Kaskade:** 9 L1-REQs aus dem v2-Backlog in SE-Phasen 1–6 vollständig zerlegt (15 L2-REQs, 11 Komponenten). 6 REQs als leaf terminiert (Pipeline B), 3 als continue (Pipeline C — ReqIF, Comments, RAG).

**Architektur-Schichten:**
- **Layer 0 (Foundation):** Persistierung, Auth/Tenancy, Konfiguration, Audit
- **Layer 1 (Domain Services):** LLM-Adapter, Traceability, Workflow, Baseline, Diagram, ICD
- **Layer 2 (Orchestration):** ApplicationService (16 Services, Single Entry Point)
- **Layer 3 (Interfaces):** REST API + MCP Server (20 Tools)
- **Layer 4 (Frontend):** React-SPA
- **Cross-Cutting:** SeMetrics (Read Model), ResilienceOrchestrator

**Weiterführende Architektur-Dokumente:**
- [Backend Data Model](architecture/BACKEND_DATAMODEL_DESIGN.md)
- [Design Tree View L0-L4 Hierarchy](architecture/DESIGN_TREE_VIEW_L0_L4_HIERARCHY.md)
- [UI Style Guide](architecture/UI_STYLE_GUIDE.md)

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
**Modell:** Authentifizierung (Bearer JWT + API-Key), Autorisierung (RBAC), Tenant-Context-Management.

**Exportierte API:**
```python
from auth_tenancy.rest import AuthTenancyAuthentication, HasOperationPermission
# request.auth_context -> auth_tenancy.context.AuthContext

from auth_tenancy.services import AuthenticationService, AuthorizationService, Operation
from auth_tenancy.context import AuthContext, AuthMethod
```

**Komponenten:**
- `rest.py` — `AuthTenancyAuthentication` (DRF BaseAuthentication): validiert Bearer JWT oder API-Key,
  aktiviert Tenant-Context, baut immutables `AuthContext`; `HasOperationPermission` (DRF BasePermission)
- `services/authentication.py` — `AuthenticationService`: JWT-Validierung, API-Key-Lifecycle
- `services/authorization.py` — `AuthorizationService`: RBAC-Matrix (admin/editor/viewer/approver)
- `services/password_authentication.py` — Login-Flow: Credentials → JWT-Minting
- `jwt_tokens.py` — HS256 Bearer-Token-Codec

**Rollen-Auflösung (REQ-126):**
- Bearer-Token: `claims.roles` aus JWT-Claims. Sind diese leer (neuer User / Rolle nach Login vergeben),
  folgt ein DB-Fallback via `UserRole`-Tabelle — identisch dem API-Key-Pfad.
- API-Key: Claims tragen immer `roles=()` → immer DB-Lookup aus `UserRole`.
- DB-Fallback erfolgt nach Tenant-Aktivierung (tenant-scoped Query via TenantManager).

**Passwort-Login:**
- `POST /api/v1/auth/login/` → JWT + httpOnly-Cookie `reqflow_access` (REQ-052)
- `manage.py seed_demo` erstellt Admin-Account

**Test-Coverage:** 115+ Tests (auth, RBAC, tenant-isolation, JWT, Rollen-Resolution)

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

#### `traceability/pdf_report_generator.py` (COMP-TE-004, REQ-L1-023)
**Modell:** PDF-Report-Generator für Requirement-Dokumente und Traceability-Matrizen.

**Exportierte API:**
```python
from traceability.pdf_report_generator import (
    generate_pdf_report,            # generate_pdf_report(workspace_id, layout, ctx) → bytes
)
```

**Layouts:**
- `requirement_document` — Formatiertes Anforderungsdokument mit Metadaten
- `traceability_matrix` — Traceability-Matrix mit Link-Typen und Coverage

**Test-Coverage:** 10+ Tests (Integration + PDF-Validierung)

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
**Modell:** Diagramm-Rendering (SysML, UML, Architektur-Visualisierung), Free-Hand Canvas (COMP-DS-006), Mermaid Live Preview (COMP-DS-007).

**Exportierte API:**
```python
from diagram.services import (
    render_architecture_diagram,  # render(element_id, format="svg") → SVG-String
    render_requirement_tree,      # render(requirement_id) → Tree-Visualisierung
    get_supported_formats,        # ["svg", "png", "puml"]
    # Canvas (COMP-DS-006, REQ-L1-056)
    canvas_auto_save,             # Auto-Save canvas stroke data (IF-L1-058)
    get_canvas_diagram,           # Retrieve canvas + SVG export (IF-L1-060)
    # Mermaid (COMP-DS-007, REQ-L1-057)
    update_mermaid_source,        # Update Mermaid source (IF-L1-059)
    get_mermaid_preview,          # Live preview data (IF-L1-061)
    validate_mermaid_source,      # Validate Mermaid syntax
)
```

**Komponenten:**
- `DiagramRenderer` (ABC) → SVG, PNG, PlantUML-Impls
- `ArchitectureVisualizer` — L1/L2 Element-Layouts
- `TraceGraphVisualizer` — Network-Graph-Rendering
- `CanvasEditor` (COMP-DS-006) — Free-Hand Canvas, JSON stroke data primary format, SVG derived
- `MermaidLiveRenderer` (COMP-DS-007) — Mermaid source validation, persistence, render hints for 5 types (flowchart, sequenceDiagram, classDiagram, stateDiagram, erDiagram)
- `DiagramValidator` (COMP-DS-002) — Type-specific payload validation including canvas strokes and Mermaid source

**Test-Coverage:** 73 Tests grün (42 existing + 31 canvas/mermaid)

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

**Exportierte API (19 Services — 16 Core + 3 v1.1):**
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

    # v1.1 New Features (SE-Phasen 1–6)
    ImportService,                 # CSV bulk import
    TestRunService,                # Test-Run-Protokollierung
    ArtifactDiffService,           # Strukturiertes Feld-Level-Diff
)
```

**Komponenten (16 im `services/` Subpackage — 13 Core + 3 v1.1):**
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
- `import_service.py` — `ImportService` (COMP-AS-009, v1.1 CSV-Bulk-Import)
- `test_run_service.py` — `TestRunService` (COMP-AS-017, v1.1 Test-Run-Protokollierung)
- `artifact_diff_service.py` — `ArtifactDiffService` (COMP-AS-019, v1.1 Feld-Level-Diff)

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

**Test-Coverage:** 165 Tests grün (131 Core + 34 neue v1.1 Tests für ImportService, TestRunService, ArtifactDiffService)

---

### Layer 3: Interface Adapters

#### `rest_api/` (ARCH-L1-002)
**Modell:** Django REST Framework ViewSets + Serializers gegen ApplicationService. OpenAPI über `drf-spectacular`.

**Exportierte API (16 ViewSets + 5 APIViews):**
```python
# In rest_api/views/
class ArtifactViewSet(viewsets.ModelViewSet):
    # GET/POST /api/v1/artifacts/
    # GET/PUT/DELETE /api/v1/artifacts/{id}/
    
class RequirementViewSet(viewsets.ModelViewSet):
    # GET/POST /api/v1/requirements/
    # GET/PUT/DELETE /api/v1/requirements/{id}/
    # @action: GET /api/v1/requirements/{id}/diff/?from_version=0&to_version=2
    # @action: GET /api/v1/requirements/{id}/versions/

class ArchitectureViewSet(viewsets.ModelViewSet):
    # GET/POST /api/v1/architecture/
    # GET/PUT/DELETE /api/v1/architecture/{id}/
    # @action: GET /api/v1/architecture/{id}/diff/?from_version=0&to_version=2
    # @action: GET /api/v1/architecture/{id}/versions/

class TestCaseViewSet(viewsets.ModelViewSet):
    # GET/POST /api/v1/testcases/
    # GET/PUT/DELETE /api/v1/testcases/{id}/
    # @action: GET /api/v1/testcases/{id}/diff/?from_version=0&to_version=2

class TraceLinkViewSet(viewsets.ModelViewSet):
    # GET/POST /api/v1/tracelinks/
    # GET/PUT/DELETE /api/v1/tracelinks/{id}/

class BaselineViewSet(viewsets.ViewSet):
    # GET /api/v1/baselines/?workspace={id}
    # POST /api/v1/baselines/ (create)
    # GET /api/v1/baselines/{id}/diff/?baseline2={id}

class WorkflowDefinitionViewSet(viewsets.ModelViewSet):
    # GET/POST /api/v1/workflows/

class WorkspaceViewSet(viewsets.ModelViewSet):
    # GET/POST /api/v1/workspaces/
    # PATCH /api/v1/workspaces/{id}/
    # @action: PATCH /api/v1/workspaces/{id}/preset/
    # @action: GET /api/v1/workspaces/{id}/reports/pdf/?layout=...

class AdrViewSet(viewsets.ModelViewSet):
    # GET/POST /api/v1/adrs/

class RiskViewSet(viewsets.ModelViewSet):
    # GET/POST /api/v1/risks/

class IssueViewSet(viewsets.ModelViewSet):
    # GET/POST /api/v1/issues/

class TestRunViewSet(viewsets.ModelViewSet):
    # GET/POST /api/v1/test-runs/
    # GET /api/v1/test-runs/{id}/
    # POST /api/v1/test-runs/{id}/results/bulk/

class SearchViewSet(viewsets.ViewSet):
    # GET /api/v1/search/?q=...&workspace_id=...

class ApiKeyViewSet(viewsets.ViewSet):
    # GET    /api/v1/api-keys/          — list keys (metadata only)
    # POST   /api/v1/api-keys/          — create key (plaintext returned ONCE)
    # DELETE /api/v1/api-keys/<pk>/     — revoke key

class CsvImportView(APIView):
    # POST /api/v1/workspaces/{pk}/import/csv/

class RequirementHistoryView(APIView):
    # GET /api/v1/requirements/{pk}/history/

# Canvas/Mermaid sub-resource views (IF-L1-058..061, REQ-L1-056/057)
class CanvasStrokeView(APIView):
    # GET  /api/v1/diagrams/{id}/canvas-strokes/ — retrieve stroke data + SVG
    # POST /api/v1/diagrams/{id}/canvas-strokes/ — append strokes (auto-save)
    # PUT  /api/v1/diagrams/{id}/canvas-strokes/ — replace all strokes

class MermaidSourceView(APIView):
    # GET /api/v1/diagrams/{id}/mermaid-source/ — get Mermaid source code
    # PUT /api/v1/diagrams/{id}/mermaid-source/ — update Mermaid source

class MermaidPreviewView(APIView):
    # GET /api/v1/diagrams/{id}/mermaid-preview/ — rendered preview data
```

**Auth-Endpoints:**
```python
POST /api/v1/auth/login              # (new Wave 7) email + password → JWT
GET  /api/v1/auth/me                 # Current user details (from Bearer token)
POST /api/v1/auth/logout             # Optional (stateless, JWT in localStorage)
```

**Komponenten:**
- `views.py` — 16 ViewSets + 2 APIViews (alle CRUD-Operationen)
- `api_key_views.py` — ApiKeyViewSet (Key-Lifecycle: list/create/revoke)
- `auth_views.py` — LoginView, MeView
- `diagram_views.py` — DiagramViewSet
- `diagram_canvas_views.py` — CanvasStrokeView, MermaidSourceView, MermaidPreviewView (IF-L1-058..061)
- `serializers_diagram.py` — Canvas/Mermaid DRF Serializers
- `icd_views.py` — IcdViewSet
- `metrics_views.py` — MetricsViewSet
- `serializers/` — DRF Serializers mit Validation
- `permissions/` — DRF Permission-Klassen (TenantPermission, AdminOnlyPermission)
- `pagination/` — LimitOffsetPagination (default 50, max 500)
- `filters/` — SearchFilter, OrderingFilter
- `openapi.py` — OpenAPI Schema-Generierung (drf-spectacular)

**Settings Integration:**
- `DEFAULT_AUTHENTICATION_CLASSES` → TokenAuthentication
- `DEFAULT_PERMISSION_CLASSES` → TenantPermission
- `AUTO_SCHEMA_CLASS` → drf-spectacular (OpenAPI 3.0)

**Test-Coverage:** 30+ Tests (Endpoint-Integration + PDF-Report + CSV-Import)

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
      workspaces.ts               # API-Wrapper für Workspace-CRUD
      diagrams.ts                 # API-Wrapper für Diagramme + Canvas-Strokes + Mermaid-Source/Preview
      index.ts                    # Re-exports
    components/
      DashboardViews/             # Dashboard-Container
        useDashboardData.ts        # Custom Hook für Dashboard-Daten
      RequirementEditors/         # Requirement-CRUD
        useRequirementData.ts      # Custom Hook
      ArchitectureEditors/        # Architecture-CRUD
        useArchitectureData.ts     # Custom Hook
      ArtifactDiff/               # Visueller Artefakt-Diff (side-by-side + unified)
        ArtifactDiff.tsx
      CsvImport/                  # CSV-Bulk-Import UI
        CsvImport.tsx
      TestRuns/                   # Test-Run-Ansicht mit Ergebnisliste
        TestRuns.tsx
      DiagramView/                  # Diagram-CRUD + Traceability-Sidebar
      canvas/                       # Free-Hand Canvas Editor (Fabric.js v6)
        CanvasEditor.tsx
        CanvasEditor.test.tsx
      mermaid/                      # Mermaid Code-Editor + Live-Preview
        MermaidEditor.tsx
        MermaidEditor.test.tsx
      AdrList/                    # ADR-Liste (Architecture Decision Records)
        AdrList.tsx
      RiskList/                   # Risiko-Liste
        RiskList.tsx
      IssueList/                  # Issue-Liste
        IssueList.tsx
      BaselinesView/              # Baseline-Verwaltung und Diff-Viewer
      TraceabilityView/           # Trace-Link-Visualisierung
      NavigationShell/            # Sidebar, Workspace-Switcher, globale Suche
      WorkspaceSettings/          # Workspace-Settings (Preset, Terminologie, Sprache)
    context/
      index.ts                    # React Context (Auth, Tenant, Presets, Workspace)
    types/
      index.ts                    # TypeScript Interfaces (Artifact, Requirement, etc.)
    i18n/
      index.ts                    # i18next Config (DE/EN)
      locales/de.json             # Deutsche Übersetzungen
      locales/en.json             # Englische Übersetzungen
    test/
      setup.ts                    # Vitest Setup
    styles/
      tokens.css                  # CSS Custom Properties (Design Tokens)
      global.css                  # Global Styles
      components/
        CanvasEditor.module.css   # Canvas Editor Styles
        MermaidEditor.module.css  # Mermaid Editor Styles
  package.json                    # Dependencies (React, Vite, react-i18next, Fabric.js, mermaid.js, CodeMirror 6, etc.)
  vitest.config.ts                # Vitest Config
```

**Key Components (15 hauptsächliche):**
1. `DashboardViews` — Übersichts-Dashboards (Requirements, Architecture, Tests)
2. `RequirementEditors` — Requirement-Create/Edit/Delete Forms
3. `ArchitectureEditors` — Architecture-Element-Editor
4. `TraceabilityView` — Trace-Link-Visualisierung und Create-Formular
5. `BaselinesView` — Baseline-Verwaltung und Diff-Viewer
6. `NavigationShell` — Sidebar mit Workspace-Switcher, globaler Suche
7. `WorkspaceSettings` — Workspace-Settings (Preset, Terminologie, Sprache)
8. `ArtifactDiff` — Visueller Artefakt-Diff (side-by-side + unified, Feld-Highlighting)
9. `CsvImport` — CSV-Bulk-Import UI
10. `TestRuns` — Test-Run-Ansicht mit Ergebnisliste
11. `AdrList` — ADR-Liste (Architecture Decision Records)
12. `RiskList` — Risiko-Liste
13. `IssueList` — Issue-Liste
14. `canvas/CanvasEditor` — Free-Hand Canvas Editor (Fabric.js v6, REQ-L1-056)
15. `mermaid/MermaidEditor` — Mermaid Code-Editor mit Live-Preview (CodeMirror 6 + mermaid.js, REQ-L1-057)

**Hooks:**
- `useDashboardData()` — Fetch via `api/requirements`, caching
- `useRequirementData(id)` — Load single requirement
- `useArchitectureData(id)` — Load architecture element
- `useAuthContext()` — Auth-State (Token, CurrentUser, Tenant)
- `useWorkspaceContext()` — Workspace-State, Preset, Terminologie

**i18n:** DE/EN via react-i18next (Übersetzungen in `locales/de.json`, `locales/en.json`)

**Test-Coverage:** 34+ Frontend-Dateien; Vitest für Unit-Tests; 111 E2E Tests (Playwright/Chromium)

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
# Alle Backend-Tests (1130 Tests)
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


## MCP Server Reference

### Authentication

### API Key Header (preferred)

```
X-API-Key: rfk_<40 character hex string>
```

### API Key in Body (fallback, for stdio)

Include `params.api_key` in the JSON-RPC request body alongside the tool name and arguments.

### Creating an API Key

```bash
# Obtain a JWT session token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"•••"}' | jq -r .access)

# Create a new API key
curl -X POST http://localhost:8000/api/v1/api-keys/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"claude-desktop"}'
# Response: {"id":7, "key":"rfk_Ab12Cd34Ef56Gh78Ij90Kl12Mn34Op56Qr78St90Uv12", ...}
```

**The plaintext key is returned exactly once.** Store it in a password manager or environment variable immediately.

### Revoking a Key

```bash
curl -X DELETE http://localhost:8000/api/v1/api-keys/7/ \
  -H "Authorization: Bearer $TOKEN"
```

Returns `204 No Content`. The key is immediately invalidated.

### Key Behaviour

- Keys **inherit the creator's role and workspace scope** at creation time. Creating a key as Admin gives it full Admin scope; there is no separate key-role system.
- Rotation workflow: create a new key → switch clients to use the new key → revoke the old one.
- The `rfk_` prefix is intentional so secrets-scanners (truffleHog, Gitleaks, etc.) can detect leaked keys in source code.


### Tool Reference

All 11 tool groups listed below. Tools are called as `<prefix>.<tool_name>` (e.g., `requirement.query`, `test.run_create`).

####1 `requirement.*` — Requirements Management

Read, create, update, decompose, and validate requirements.

**Tools:** `get`, `query`, `create`, `update`, `decompose`, `validate`

**Example:**
```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rfk_..." \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "requirement.get",
      "arguments": {"workspace_id": 1, "requirement_id": 42}
    }
  }'
```

**Role required:** Member

---

####2 `architecture.*` — Architecture Elements

Read, create, update, and link architecture artifacts (system components, subsystems, interfaces).

**Tools:** `get`, `query`, `create`, `update`, `link`

**Example:**
```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rfk_..." \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "architecture.query",
      "arguments": {"workspace_id": 1, "parent_id": 10}
    }
  }'
```

**Role required:** Member

---

####3 `test.*` — Test Management

Read, create, link, execute test runs, and report results.

**Tools:** `get`, `query`, `create`, `update`, `link`, `run_create`, `run_get`, `run_report_results`

**Example:**
```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rfk_..." \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "test.run_create",
      "arguments": {"workspace_id": 1, "testcase_ids": [10, 11, 12]}
    }
  }'
```

**Role required:** Member

---

####4 `traceability.*` — Cross-Cutting Traceability

Cross-cutting queries across requirements, architecture, and tests. Search artifacts and retrieve full workspace traceability trees.

**Tools:** `query`, `artifact.search`, `artifact.get_tree`, `workspace.get_context`

**Example:**
```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rfk_..." \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "traceability.artifact.search",
      "arguments": {"workspace_id": 1, "q": "safety"}
    }
  }'
```

**Role required:** Member

---

####5 `artifact.*` — Artifact Tree & Comments

Retrieve the full artifact tree and comments for a workspace.

**Tools:** `get_tree`, `get_comments`

**Example:**
```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rfk_..." \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "artifact.get_tree",
      "arguments": {"workspace_id": 1, "root_id": null}
    }
  }'
```

**Role required:** Member

---

####6 `workspace.*` — Workspace Lifecycle Management (Admin)

Close, reactivate, and delete workspaces. These are destructive or state-changing operations on the workspace itself.

**Tools:** `get_context`, `close`, `reactivate`, `delete`

**Example:**
```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rfk_..." \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "workspace.close",
      "arguments": {"workspace_id": 1}
    }
  }'
```

**Role required:** Admin

---

####7 `permissions.*` — RBAC Rule Management (Admin)

Set, list, revoke, and check RBAC permission rules.

**Tools:** `set_rule`, `list`, `revoke`, `check`

**Example:**
```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rfk_..." \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "permissions.check",
      "arguments": {"workspace_id": 1, "user_id": 5, "permission": "workspace.close"}
    }
  }'
```

**Role required:** Admin

---

####8 `admin.*` — Backup & Restore (Admin)

Create and list backups; restore a workspace from a backup.

**Tools:** `backup_create`, `backup_list`, `restore`

**Restore requires** the `X-Captcha: RESTORE` header in addition to the Admin role.

**Example:**
```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rfk_..." \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "admin.backup_create",
      "arguments": {"workspace_id": 1}
    }
  }'
```

**Role required:** Admin (+ `X-Captcha: RESTORE` for restore)

---

####9 `audit.*` — Audit Log Query

Query the system-wide audit log with filters for actor, operation, workspace, and time range.

**Tools:** `query` (supports filters: `actor`, `operation`, `workspace`, `time_from`, `time_to`, `limit`, `offset`)

**Example:**
```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rfk_..." \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "audit.query",
      "arguments": {"workspace_id": 1, "limit": 20}
    }
  }'
```

**Role required:** Member (own scope) / Admin (all scopes)

---

####10 `events.*` — Dead-Letter Queue Management

Inspect and replay failed events from the dead-letter queue (DLQ).

**Tools:** `dlq_list`, `dlq_replay`

**Example:**
```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rfk_..." \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "events.dlq_list",
      "arguments": {"workspace_id": 1, "limit": 10}
    }
  }'
```

**Role required:** Member

---

####11 `user.*` — User & Role Management (Admin)

Create, list, assign roles, and deactivate users.

**Tools:** `create`, `assign_role`, `list`, `deactivate`

**Example:**
```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rfk_..." \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "user.list",
      "arguments": {"workspace_id": 1}
    }
  }'
```

**Role required:** Admin

---

