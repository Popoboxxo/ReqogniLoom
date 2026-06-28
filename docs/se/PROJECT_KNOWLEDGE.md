# ReqFlow — Projektwissen für Honcho Memory

> Fallback-Wissensnotiz bis Honcho vollständig konfiguriert ist.
> Struktur: Destilliert aus IMPLEMENTATION_STATUS.md, STRATEGY.md, CLAUDE.md
> Letzte Aktualisierung: 2026-06-28
> Branch: `feat/se-implementation`

---

## 1. Was ist ReqFlow?

**ReqFlow** ist ein AI-natives Requirements-Management-Tool, das die Lücke zwischen leichten Agile-Tools (Jira, Linear) und schweren Enterprise-ALM-Systemen (DOORS, Polarion, Codebeamer) schließt.

**Kerncharakteristik:**
- **MCP Server als native Schnittstelle** — AI-Agenten greifen auf Requirements, Architektur und Tests strukturiert zu (kein Text-Scraping)
- **Generisches Artefakt-Modell** — ein Datenmodell für alle Zielgruppen, konfigurierbare Tiefe (Configurable Rigor)
- **AI-pluggable Capabilities** — LLM-Generierung, Validierung, Decomposition, Konsistenz-Checks über alle Artefakttypen
- **Self-Hosted First** — Docker Compose, Apache 2.0 Open Source, kein Vendor-Lock-in

---

## 2. Zielgruppen

| Gruppe | Beschreibung | Bedarf |
|--------|-------------|--------|
| **AI-first Software Teams** | Teams mit Claude Code, Cursor, Copilot im Dev-Prozess | Strukturierter, maschinenlesbarer Anforderungskontext; Agile-Terminologie |
| **Systems Engineers (Embedded/Safety)** | Medizintechnik-Startups, Automotive-Zulieferer, Industrieautomation-KMU | Formale Artefakt-Hierarchien, Baselines, Approval-Workflows |
| **SE + AI-Bridge** | SE-Profis, die SE-Methodik mit modernen AI-Tools kombinieren | Hybrid-Prozesse |

**Out-of-Scope v1:** Hochregulierte Programme (DO-178C Level A, ISO 26262 ASIL-D) → v2+

---

## 3. Kernarchitektur (SE-Kaskade L0 → L1 → L2)

### Implementierungs-Status
- **16 Systeme + ReactFrontend: vollständig implementiert** (Commit `b01414a`, Branch `feat/se-implementation`)
- **Code-Stand:** 131 Core-Tests grün, 55 LlmAdapter-Tests grün, 71 MCP-Tests grün, 12 ICD-Tests grün, 69 SeMetrics-Tests grün, 31 Resilience-Tests grün, 42 Diagram-Tests grün, 34 Frontend-Dateien
- **Offen:** nur finale Integration (Audit-Index-Patch, Celery-Wiring, Docker-Gesamttestlauf)

### Die 16 L2-Systeme

| Layer | System | App | Komponenten | REQ-L2 | Schnittstellen-Typ | Status |
|-------|--------|-----|-------------|--------|-------------------|--------|
| 0 (Foundation) | PersistenceLayer (010) | `persistence` | 6 | 10 | ORM-Models | ✅ |
| 0 | AuthAndTenancy (011) | `auth_tenancy` | 3 | 10 | Auth/Tenant-Service | ✅ |
| 0 | PresetConfigEngine (008) | `presets` | 3 | 14 | Config-Service | ✅ |
| 0 | AuditLog (012) | `audit` | 3 | 9 | Audit-Service | ✅ |
| 1 (Core Services) | LlmAdapter (009) | `llm_adapter` | 5 | 8 | AI-Capability-Interface | ✅ |
| 1 | TraceabilityEngine (007) | `traceability` | 4 | 13 | Trace-Query-Service | ✅ |
| 1 | WorkflowEngine (005) | `workflow` | 4 | 9 | State-Transition-Service | ✅ |
| 1 | BaselineService (006) | `baseline` | 4 | 9 | Baseline-CRUD-Service | ✅ |
| 2 (Application) | ApplicationService (004) | `application` | 13 | 26 | Domain-Facade (16 Services) | ✅ |
| 3 (External Adapters) | RestApiAdapter (002) | `rest_api` | 6 | 13 | REST-Endpoints DRF | ✅ |
| 3 | McpServer (003) | `mcp_server` | 6 | 12 | MCP-Tool-Registry | ✅ |
| 4 (Frontend) | ReactFrontend (001) | `frontend/` | 6 | 12 | React-SPA Hooks/Components | ✅ |
| ext (Extensions) | DiagramService (013) | `diagram` | 5 | — | Renderer-Service | ✅ |
| ext | IcdManagement (014) | `icd` | 4 | — | Version-Registry | ✅ |
| ext | SeMetrics (015) | `se_metrics` | 5 | — | Metrics-Aggregator | ✅ |
| ext | ResilienceOrchestrator (016) | `resilience` | 5 | — | Retry/Circuit-Breaker | ✅ |

### Foundation-Contracts (Import-Stempel für alle L2-Apps)

```python
# Zentrale Modelle in persistence.models
Tenant, User, Role, Workspace, Artifact, Requirement, ArchitectureElement, 
TraceLink, TestCase, Baseline, WorkflowDefinition, WorkflowState, AuditLogEntry

# Klassen & Services
TenantScopedModel, AuditableModel
TenantContext, TenantContextNotSetError
atomic_transaction

# Service-Fassaden (Single Entry Point pro System)
from presets.services import get_preset, is_feature_enabled, get_terminology
from audit.services import log_write, query
from traceability.services import query, coverage, create_trace_link, collect_trace_graph
from workflow.services import transition, initialize_workflow_states
from baseline.services import build, diff, get, list_baselines, get_item_at_baseline
from llm_adapter.services import validate_artifact, decompose_requirement, check_consistency
from application.services import * (16 Domain-Services)
```

---

## 4. Tech-Stack

| Layer | Stack |
|-------|-------|
| **Backend** | Python 3.x, Django 4.2+, Django REST Framework, MCP SDK |
| **Frontend** | React 18+, TypeScript, Hooks, Vitest, react-i18next (DE/EN) |
| **Persistenz** | PostgreSQL via Django ORM, Row-Level Tenant-Isolation |
| **Deployment** | Docker Compose (Backend, Frontend, PostgreSQL) |
| **API** | REST (`/api/v1/`) + MCP Server (20 Tools, 4 Gruppen) |
| **Auth** | Bearer Token / API Keys, DRF-Permission-Classes |

---

## 5. Strategische Architektur-Entscheidungen (ADRs)

| ADR | Entscheidung | Grund |
|-----|-------------|-------|
| ADR-01 | MCP Server greift direkt auf ApplicationService zu | Gleichrangige Adapter, kein HTTP-Overhead |
| ADR-02 | LLM-Provider über schmale Adapter-Schicht (`LlmCapabilityInterface`) | Kein Vendor-Lock-in, Graceful Degradation |
| ADR-03 | Tenant-Isolation via Row-Level + Custom Django Manager | Skaliert bis 4-stellige Tenant-Zahlen |
| ADR-04 | Configurable Rigor als Single Source of Truth (PresetConfigEngine) | Ein Datenmodell für alle Zielgruppen |
| ADR-05 | Generisches Artefakt-Modell + Terminologie-Profile | Keine zielgruppen-spezifischen Code-Pfade |
| ADR-06 | Item-Lifecycle konfigurierbar (WorkflowEngine) | Flexible State-Machines statt hartcodierter Enums |
| ADR-07 | Baselines auf 3 Scopes (Dokument/Projekt/Global) in einer Entität | Flexibilität ohne Datenmodell-Explosion |
| ADR-08 | Docker Compose, nicht Kubernetes in v1 | Self-Hosted-Footprint minimieren |
| ADR-09 | PostgreSQL Full-Text statt eigener Search-Engine | Performance-Ziel <500ms für 10k Items |
| ADR-10 | AuditLog Operation-Level (v1), Feld-Diff in v2 | Ausreichend für v1, Komplexität reduzieren |

---

## 6. Configurable Rigor — Die strategische Differenzierung

Drei Presets mit gleichem Datenmodell, unterschiedliche Prozess-Tiefe:

| Preset | Charakteristik | Zielgruppe | Feldvalidierung |
|--------|----------------|-----------|-----------------|
| **Minimal** | Leicht, wenig Pflichtfelder, kein Approval | AI-first Teams, Startups | Low |
| **Standard** | Erweiterte Felder, Document+Project-Baselines, einfacher Workflow | Mid-Market Software | Medium |
| **Extended** | Vollständiger Audit, alle Baseline-Scopes, strikter Approval, `change_reason` Pflicht | Systems Engineering, reguliert | High |

**Datenmodell:** Immer vollständig. Was sich ändert: Erzwingung, Sichtbarkeit, Schreibbarkeit per Preset-Konfiguration.

---

## 7. AI-Nativ: Zwei Dimensionen

### Dimension 1: LLM als pluggable Capability

Vier Capabilities quer über Requirements, Architektur, Tests:
- **Generierung** — Formulierungs-Vorschläge, Testfall-Ableitung
- **Validierung** — Qualitätsprüfung (Vollständigkeit, Eindeutigkeit, Testbarkeit)
- **Decomposition** — Automatische Zerlegungsvorschläge
- **Konsistenz-Checks** — Widerspruchs-Prüfung

**Provider:** Anthropic, OpenAI, Ollama austauschbar. Self-Hosted ohne LLM verliert AI-Features, nicht Kernfunktionalität.

### Dimension 2: MCP als vollwertige externe Schnittstelle

**20 MCP-Tools in 4 Gruppen:**
- Requirements: create, read, update, delete, list, query
- Architecture: create, read, update, delete, list, verify-consistency
- Tests: create, read, update, execute, query
- Traceability: create-link, query, report-coverage

Alle drei Artefakttypen vollständig les- und schreibbar.

---

## 8. Architektur-Invarianten (operativ)

### ReqFlow MCP-Server
- **Tool-Aufrufe nutzen `method: "tool.name"` direkt** (NICHT `tools/call`). Das JSON-RPC-2.0-`method`-Feld enthält den Tool-Namen in dot-notation. Beispiel: `{"method": "requirement.query", "params": {...}}`.
- **Authentifizierung:** API-Key via `X-API-Key`-Header ODER JWT via `Authorization: Bearer <token>`.
- **TenantContext muss in Views explizit via `set_tenant()` aktiviert werden** — sonst schlagen Tenancy-abhängige Queries mit leerem Tenant-Filter fehl (Production-Bug-Fix vom 2026-06-28).
- **Workspace-Kontext:** MCP-Tools arbeiten innerhalb eines Workspaces. `workspace.get_context` liefert die Liste der verfügbaren Workspaces.

### Auth-Endpoints
- **Login:** `POST /api/v1/auth/login/` mit `{"username": "...", "password": "..."}`.
  - Response: `{"token": "<jwt>", "user": {...}, "tenant_id": "...", "roles": [...]}`
  - LoginView ist PUBLIC (`authentication_classes = []`, `permission_classes = [AllowAny]`).
- **Token-Validierung:** `GET /api/v1/auth/me/` — gibt authenticated user zurück.
- **Token-Format:** JWT, `BearerTokenAuthentication`.

### seed_demo — PFLICHT
- Nach `migrate` ist die DB leer. `python manage.py seed_demo` MUSS vor dem ersten Login laufen.
- **Default-Passwort:** aus `DEMO_ADMIN_PASSWORD` env var (Default `admin12345`).
- **Idempotent:** Re-running ist sicher.
- Erstellt: Tenant "demo", Workspace "Demo Workspace", User "admin" mit admin-Rolle.

### Test-Struktur (verifiziert 2026-06-28)
- Backend: 1599 Tests (pytest, `feat/se-implementation`)
- E2E Playwright: 111 Tests
- MCP E2E Suite: 150+ Tests (40+ Tools, alle 4 Transport-Channel)
- **Collection-Error:** `traceability/tests/test_vcrm_report_generator.py` benötigt `reportlab` — pip-install behebt es, beeinflusst 1599 nicht.

---

## 9. Workflow-Konventionen

### Commit-Konventionen
- `feat(REQ-xxx): ...` für Features mit REQ-ID (req-traceability aktiv)
- `fix(REQ-xxx): ...` für Bugfixes mit REQ-ID
- `docs: ...` für Dokumentation (KEINE REQ-ID)
- `chore: ...` für Wartung (KEINE REQ-ID)

### Branch-Policy
- Feature-Branches: `feat/<thema>`, `fix/<thema>`, `refactor/<thema>`
- Direkt auf `main`: nur Version-Bump, einzelne Tippfehler (mit User-Bestätigung), Post-Merge-Pflege
- **Niemals** ohne explizite User-Freigabe pushen oder mergen

---

## 10. Bekannte Stolperfallen

| Problem | Ursache | Lösung |
|---------|---------|--------|
| Login schlägt mit 401 fehl | DB leer nach `migrate` | `python manage.py seed_demo` ausführen |
| `pytest` findet keine Tests oder DB-Fehler | `DB_HOST` nicht gesetzt | `export DB_HOST=localhost` |
| MCP-Tool schlägt mit leerem Tenant fehl | `set_tenant()` nicht in View | In jeder MCP-View am Anfang `set_tenant(request.user.tenant)` aufrufen |
| `reportlab` Collection-Error | Modul fehlt im venv | `pip install reportlab` |

---

## 11. Offene Tech-Debt

- `docs/se/traceability-matrix.md` endet bei REQ-L1-033 — REQ-L1-039/042/046 müssen nachgetragen werden
- Coverage-Commit-Subjects enthalten keine REQ-IDs (akzeptabel für `docs:`, sollte aber konsistent dokumentiert sein)
- 3 modifizierte Test-Files im Working Tree (`test_e2e_audit.py`, `test_e2e_performance.py`, `test_e2e_sse_transport.py`) — Relikte aus vorherigen Wellen, separate Aufarbeitung nötig
- Lokale Commits ahead of origin, kein Push durchgeführt

---

## 12. Offene Integrations-Aufgaben (Wave 9)

| Task | Blocker | Status |
|------|---------|--------|
| AuditEntry Index-Name kürzen (>30Z → Django-6.0 SystemCheck E034) | pytest-Start | Patch + Migration nötig |
| persistence Model/Migration sauber nachziehen | pytest | makemigrations + Sync |
| Celery-Broker in settings.py verdrahten | AsyncDispatcher, WebhookDispatcher, SeMetrics-Cache, LlmAdapter-Async | Config-Anpassung |
| WebhookDispatcher/LlmAdapter → ResilienceOrchestrator umverdrahten | Dependencies | TODO-Marker gesetzt |
| Docker-Gesamttestlauf | Alle Apps über PostgreSQL | `docker-compose up && pytest` |

---

## 13. Code-Konventionen

**Python (PEP 8):**
- Type Hints überall
- Docstrings für public API
- Imports: StdLib → Third-Party → Local

**TypeScript/React:**
- Functional Components + Hooks
- Types für Props & State
- Keine wildcard imports

**Commits:**
- Format: `<type>(REQ-ID): <beschreibung>` wenn req-traceability aktiv
- Typen: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`
- Imperativ: `add feature`, nicht `added`

**Branching:**
- Feature-Branches: `feat/<topic>`, `fix/<topic>`, `refactor/<topic>`
- Nur auf `main` nach Review/Merge, nie direkte Commits auf main

---

## 14. Wichtigste Dateipfade

```
backend/
  manage.py                              # Django Entry-Point
  reqflow/settings.py                    # Konfiguration (Celery, DRF, Auth, Apps)
  persistence/models.py                  # Foundation-Modelle
  auth_tenancy/, presets/, audit/        # Layer 0
  llm_adapter/, traceability/, workflow/ # Layer 1
  baseline/, application/                # Layer 2
  rest_api/, mcp_server/                 # Layer 3
  diagram/, icd/, se_metrics/, resilience/ # Extensions

frontend/
  src/index.tsx                          # React Entry-Point
  src/components/                        # UI-Komponenten
  src/pages/                             # Page-Container

docs/se/
  IMPLEMENTATION_STATUS.md               # Diese Datei (laufende Checkpoint-Datei)
  STRATEGY.md                            # Strategische Entscheidungen & Architektur
  L1/Gesamtsystem/L1_Gesamtsystem_Architecture.md
  L1/Gesamtsystem/L2/*/L2_*_Architecture.md # 16 Subsystem-Architekten
  traceability-matrix.md                 # SN → SYS-REQ → COMP-REQ → TEST-CASE
  interface-registry.md                  # Zentrale Schnittstellen-Registry
  reports/                               # se-critic Audit, se-termination Reports
```

---

## 15. Nächste Schritte (Resume nach Neubeginn)

1. **Open Tech-Debt abarbeiten** (§11) — Traceability-Matrix erweitern, Working-Tree-Relikte klären, reportlab installieren
2. **Push-Freigabe einholen** — lokale Commits ahead of origin, kein Push ohne Freigabe
3. **Integrations-Blockers angehen** (§12) in dieser Reihenfolge:
   - AuditEntry-Index-Patch → Migration → pytest Start-Check
   - persistence makemigrations Sync
   - Celery-Wiring settings.py
4. **Docker-Gesamttestlauf:** `docker-compose up && docker-compose exec backend pytest`
5. **Diese Datei aktualisieren** nach Checkpoint-Commit
6. **Orchestrator-Direktive anwenden** (§18 in IMPLEMENTATION_STATUS.md) für Tier-Auswahl bei neuen Features

---

## 16. Agenten-Dispatcher (SE-Kaskade)

Beim Dispatch über Orchestrator:

| Komplexität | Agent | Modell |
|-------------|-------|--------|
| Trivial (1 Komponente, 0–1 Interface, kein Cross-Cutting) | `se-junior-developer` | Haiku |
| Standard (2–4 Interface, ein Modul) | `se-developer` | Sonnet |
| Komplex (Cross-Cutting, Boundary, Security/Perf-kritisch, ≥5 Interface) | `se-senior-developer` | Opus |

**Foundation/Security/Performance-kritische Systeme → senior.**

---

## Quellen

- `docs/se/IMPLEMENTATION_STATUS.md` — laufende Implementations-Checkpoint-Datei
- `docs/se/STRATEGY.md` — konsolidierte Strategische Entscheidungen
- `CLAUDE.md` — Projekt-Metadata, Tech-Stack, Agent-Konfiguration
- `docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Architecture.md` — L1-Systemarchitektur
- `docs/VISION.md`, `docs/KONZEPT.md` — Quellen für Strategie und Architektur-Constraints

---

*Erstellt: 2026-06-25 | Fallback-Wissensnotiz für Honcho-Initialization | Nicht unter Git-Kontrolle*
