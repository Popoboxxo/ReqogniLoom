# ReqogniLoom

> Projektbeschreibung für Claude-Agenten. Diese Datei ist die **einzige Quelle**
> für projektspezifischen Kontext — Agenten lesen sie, statt eigenen Kontext zu haben.
>
> Generiert von agent-meta v2.0.0-beta.8 — `2026-11-08`
>
> **Längenempfehlung:** 200–500 Zeilen optimal. Über 500 Zeilen → Detailwissen in
> `docs/ARCHITECTURE.md`, `docs/API.md` o.ä. auslagern und manuell verlinken.
> Agent-spezifisches Wissen → `.claude/3-project/<rolle>-ext.md` (Extension).
>
> **CLAUDE.md Hierarchie (Claude Code lädt in dieser Reihenfolge):**
> 1. `~/.claude/CLAUDE.md` — global, alle Projekte (~50 Zeilen max, persönliche Präferenzen)
> 2. `<projekt>/CLAUDE.md` — diese Datei, projektspezifisch (von agent-meta verwaltet)
> 3. `<ordner>/CLAUDE.md` — optional in Unterordnern (z.B. `src/backend/CLAUDE.md`)

---

## Eigene Notizen

**Tool-Nutzung bei Agenten-Dispatches (Codebase-Exploration):** Für alle
dispatchten Agenten (developer, senior-developer, code-reviewer, etc.), die
in diesem Repo größere Recherche-/Implementierungsarbeit leisten, gilt:
Codebase-Navigation zuerst über die verfügbaren Graph-/Index-Tools statt
über rohes Grep/Read, um Tokens zu sparen:
- **graphify** (`graphify query/path/explain`) — Architektur-/Datei-Fragen, Pflicht laut Hook wenn `graphify-out/graph.json` existiert.
- **ProjectAtlas** (`mcp__projectatlas__*`, z.B. `atlas_context`, `atlas_search`, `atlas_overview`, `atlas_symbols`) — Datei-/Ordner-Overviews, Symbol-Suche, Purpose-Queue.
- **tokensave** (`mcp__tokensave__*`, z.B. `tokensave_context`, `tokensave_search`) — Code-Graph-Kontext, Aufrufer/Aufgerufene, wenn Repowise nicht verbunden ist.
- **Repowise** (`.claude/CLAUDE.md`, `get_answer`/`get_context`/`get_risk`/…) — bevorzugt, wenn MCP-Server verbunden ist (Session-Neustart nötig nach Aktivierung); fällt der Server aus, auf ProjectAtlas/tokensave/graphify ausweichen.
Erst nach der Graph-/Index-Orientierung gezielt Read/Grep auf konkrete
Dateien/Zeilen. Rohes Read/Grep bleibt richtig für erschöpfende Literal-
Suchen (z.B. "jeden Call-Site umbenennen") und zum tatsächlichen Editieren.

Hier kannst du eigene, projektspezifische Notizen eintragen. Dieser Bereich wird von `agent-meta` nicht überschrieben!

---

## Projekt

**Name:** ReqogniLoom
**Präfix:** ReqLo
**Plattform:** Django 6.1+ (Backend) + React 19 + TypeScript 5.5+ (Frontend) + PostgreSQL 16 via pgvector/pgvector:pg16 (Django ORM + pgvector) + Redis 8 (Cache/Celery-Broker) + Celery 5.6+ (Async) + Docker Compose (9 Default-Services: postgres, postgres-backup, redis, backend, llm-preflight, migrate, celery, celery-beat, frontend; optionale Profile: honcho (+5 Services), qdrant (+1 Service))
**Beschreibung:** AI-natives Requirements- und Test-Management-Tool mit MBSE-kompatibler Artefakt-Zerlegung, REST API + nativem MCP Server (46 Tool-Gruppen-Präfixe, 290 Tools), LLM-Adapter (Anthropic/OpenAI/Ollama/Azure/opencode_go/mock), Multi-Tenancy mit Row-Level-Isolation, 20 built-in Trace-Link-Typen (tenant-extensibler Katalog), Baselines (3 Scopes) mit Feld-Diff, AI-Long-Term-Memory (pgvector; optional Honcho/Qdrant), 3 Rigor-Presets (minimal/standard/extended) und i18n (DE/EN).

> Struktur: siehe Verzeichnisstruktur im Repo (`ls`/`find`); deklarativ: `.meta-config/project.yaml` → `variables.PROJECT_STRUCTURE`.

**Verzeichnisstruktur:**
```
backend/             # Django REST API (20 Apps in REQFLOW_APPS)
                     #   Layer 0: persistence, auth_tenancy, presets, audit
                     #   Layer 1: llm_adapter, traceability, workflow, link_types, attribute_definitions, baseline
                     #   Layer 2: application (68 *_service.py)
                     #   Layer 3: rest_api, mcp_server
                     #   Ext: diagram, icd, context_graph, memory, se_metrics, resilience, admin_ops
backend/reqogniloom/ # Django-Projekt (settings.py, urls.py, wsgi.py, asgi.py, version.py, health.py)
frontend/            # React 19 + TS 5.5+ SPA (Vite 8, Vitest 5, ESLint 10)
                     #   src/api/  src/components/  src/config/  src/constants/  src/context/
                     #   src/hooks/  src/i18n/  src/queries/  src/styles/  src/types/  src/utils/
e2e/                 # Playwright/Chromium E2E-Tests (67 Spec-Dateien, 4 CI-Shards)
docs/                # Anforderungen, Architektur, SE-Kaskade (docs/se/), Pläne (docs/plans/, docs/superpowers/), Konzepte, Release-Reports
deploy/              # Deployment: docker-compose.yml (Basis), .override.yml (Dev), .minimal.yml, .env, README.md
testing/             # docker-compose.test.yml (Standalone-Test-Stack, kein Overlay, kein Deployment-File)
scripts/             # build.sh, bump_version.py, setup.sh, check-version-drift.sh, check_plugin_packages.py, enable_pgvector.sh, extract_theme_tokens.py, generate_traceability_matrix.py, clients/ (Client-Installer) + pytest-Dateien
.meta-config/        # agent-meta Konfiguration (project.yaml)
.agent-meta/         # agent-meta Submodul (Templates, Scripts, Schemas)

```

> Runtime & Abhängigkeiten: siehe Projekt-Manifest (`pyproject.toml` / `requirements.txt` / `package.json` / `manifest.json`).

**Entry-Point:** `backend/manage.py                  — Django Management (migrate, seed_demo, runserver, shell, check, export_tool_manifest, …)
backend/application/self_init.py   — post_migrate-Bootstrap (Admin/Tenant/Workspace auf leerer DB)
backend/reqogniloom/settings.py    — Settings-Entry (DRF, JWT/Cookie-Auth, Celery, Apps)
backend/reqogniloom/urls.py        — URL-Routing (/health/, /api/v1/, /mcp/, /api/v1/mcp/ [deprecated Alias], /api/schema/, /admin/)
backend/reqogniloom/version.py     — Build-/Version-Metadaten (GET /api/v1/version/)
frontend/src/index.tsx             — React Entry-Point (ReactDOM)
frontend/src/App.tsx               — Root-Component (Provider, Router)
frontend/src/api/client.ts         — API-Client (Cookie-Auth, CSRF, Silent-Refresh)
e2e/playwright.config.ts           — Playwright-Konfiguration (Chromium, 4 Shards)
scripts/build.sh                   — Release-Build mit APP_VERSION/GIT_COMMIT_SHA/BUILD_TIME`

**Besondere Patterns:**
- Django REST Framework (DRF): 30 ViewSets über 35 Router-Registrierungen plus explizite APIView-Routen
- MCP-Server (JSON-RPC 2.0) mit 46 Tool-Gruppen-Präfixen und 290 Tools (kanonisches Manifest:
  docs/agent-templates/tool-manifest.json, Drift-Gate: backend/mcp_server/tests/test_tool_manifest_drift.py);
  kanonischer Pfad /mcp/, /api/v1/mcp/ nur noch deprecated Alias
- drf-spectacular für OpenAPI 3.0 (Schema, Swagger-UI, ReDoc)
- Single-Entry-Point Pattern (ADR-01): Layer 2 application/ ist die einzige Domain-Fassade (68 *_service.py)
- TenantContext als Thread-Local Singleton + Row-Level-Security (ADR-03)
- Configurable Rigor (ADR-04): 3 Presets (minimal/standard/extended) mit gleichem Datenmodell
- LLM-Provider-Abstraktion (ADR-02): Capability-Interface mit graceful degradation
  (anthropic, openai, ollama, azure, opencode_go, mock)
- 20 built-in Trace-Link-Typen mit Richtungs-/allowed_pairs-Konvention und Suspect-Propagation;
  tenant-extensibler Katalog (backend/link_types/builtin.py, Workspace-Link-Typ-Definitionen)
- Baselines mit 3 Scopes (Document, Project, Global) in einer Entität (ADR-07), Feld-Diff + Rollback
- Konfigurierbare State-Machines pro Workspace (ADR-06)
- Resilience-Decorators (Retry, Circuit-Breaker, Timeout) auf Service-Ebene
- Context-Graph als abgeleiteter Soft-Edge-Layer (Issue #377)
- AI-Long-Term-Memory: MemoryEntry pro Workspace/Tenant, Embeddings via pgvector
  (optional Honcho/Qdrant), Digest/Search/Ask-Endpoints
- Audit-Log auf Operationsebene inkl. Finding-Waivern
- V-Modell-Traceability L0-L4 (Stakeholder Needs → System Req → Subsystems → Components → Presentation)

## Code-Konventionen

- Python (PEP 8, Typings, Docstrings für public API) - TypeScript (ESLint 10, Prettier, strict mode, functional Components + Hooks) - Django-Layer: Models (persistence/) ↔ Services (application/) ↔ Views/Serializers (rest_api/) - React-Layer: api/ (Wrapper) ↔ context/ (State) ↔ components/ (UI) ↔ i18n/ (Labels) - Imports-Reihenfolge: Standard Library → Third-Party → Local (PEP 8) - Keine wildcard imports (from x import *) - Keine direkten Model-Queries in DRF-Views (immer via Serializer + Service) - data-testid auf allen interaktiven UI-Elementen (E2E-Pflicht für Playwright) - CSS Custom Properties aus styles/tokens.css (keine hardcodierten Farben/Größen) - Commits: Conventional Commits Format (feat(REQ-xxx): ..., fix: ..., chore: ...) - Branch-Policy: feat/, fix/, chore/ (NIE direkt auf main) - Requirements-IDs: REQ-L0-*, REQ-L1-*, REQ-L2-*, REQ-L3-* (siehe docs/se/traceability-matrix.md) 

## Build & Development

```bash
# Build
make build

# Tests
make test-backend (isolierter Test-Stack, schnelle Läufe zusätzlich mit --reuse-db) + make test-frontend

# Dev-Stack starten
make up

# Nach Änderungen neu laden
make up (recreated Container bei geänderter Config/Env; reines `docker compose restart` liest .env NICHT neu) oder Hot-Reload automatisch je nach Service
```

## Anforderungs-Kategorien

Kategorien für `docs/REQUIREMENTS.md`:

- **Functional** — Features, User Stories, CRUD auf Requirements/Architecture/TestCases/ADRs/Risks/Issues
- **Non-Functional** — Performance, Sicherheit, Skalierbarkeit, Audit-Compliance, Multi-Tenancy
- **API** — REST API (/api/v1/, JWT-Auth, OpenAPI) und MCP Server (/mcp/ und /api/v1/mcp/, JSON-RPC 2.0, 46 Tool-Gruppen-Präfixe)
- **UI/UX** — Frontend (React 19 SPA), 46 Component-Bereiche, i18n (DE/EN), Barrierefreiheit
- **Data** — Generic Artifact Model, Multi-Tenancy via Row-Level-Security, Configurable Rigor
- **Integration** — Externe Systeme, CSV-Bulk-Import, PDF-Report-Export, ReqIF 1.2-Import/Export, LLM-Provider (Anthropic/OpenAI/Ollama/Azure/mock)
- **Test** — Test-Management, Test-Run-Protokollierung (4-Phasen-Lifecycle), Coverage-Tracking
- **Workflow** — Konfigurierbare State-Machines pro Workspace, Approval-Gates, Transition-Validierung
- **Baseline** — Snapshot, Feld-Level-Diff, 3 Scopes (Document/Project/Global)
- **Traceability** — 20 built-in Link-Typen (tenant-extensibler Katalog), Coverage-Aggregation, V-Modell L0-L4-Traceability
- **AI** — LLM-Provider-Abstraktion (6 Provider), Ableitung/Zerlegung, Validation, Consistency-Check, Long-Term-Memory (pgvector/Honcho/Qdrant)
- **Resilience** — Retry, Circuit-Breaker, Timeout-Decorators, async via Celery



## Agenten-Konfiguration

<!-- agent-meta:managed-begin -->
<!-- Dieser Block wird von sync.py bei jedem sync automatisch aktualisiert. -->
<!-- Manuelle Änderungen hier werden überschrieben. -->

> **AI ROUTING:** Claude -> CLAUDE.md | Opencode, Gemini -> AGENTS.md

Generiert von agent-meta v2.0.0-beta.8 — `2026-11-08`
DoD-Preset: **rapid-prototyping** | REQ-Traceability: false | Tests: false | Codebase-Overview: false | Security-Audit: false
> **Einstiegspunkt:** Starte mit dem `orchestrator`-Agenten für alle Entwicklungsaufgaben — Ausnahmen siehe Abschnitt »Orchestrator — Universal Router«.

## Knowledge Engine

Die Knowledge Engine ist aktiviert. Domäne: **internal-docs**.

**Bundle-Pfad:** `knowledge/`
| Pfad | Zweck |
|------|-------|
| `knowledge/schema.md` | Steuerungsdokument — Konventionen, Concept Types, Workflows |
| `knowledge/sources/` | Immutable Raw Sources — LLM liest, modifiziert NIEMALS |
| `knowledge/wiki/` | OKF Knowledge Bundle — LLM-owned, strukturiertes Wiki |
| `knowledge/wiki/index.md` | Content-Katalog aller Wiki-Seiten (OKF §6) |
| `knowledge/wiki/log.md` | Chronologisches Event-Log (OKF §7) |

### Knowledge-Agenten
- **Schema-Owner:** `knowledge-curator` verwaltet `knowledge/schema.md` und Concept-Type-Konventionen

### Knowledge-Workflows
- **Ingest:** Source in `knowledge/sources/` ablegen → `knowledge-ingestor` verarbeitet → Wiki aktualisiert
- **Query:** Frage stellen → `knowledge-querier` durchsucht Index → synthetisiert Antwort
- **Lint:** `knowledge-linter` prüft Wiki-Gesundheit (Widersprüche, Orphans, OKF-Compliance)
- **Migration:** `knowledge-migrator` räumt vorhandene Inhalte auf und migriert ins OKF-Format
- **Gardening:** `knowledge-gardener` pflegt Links, Tags, Typos, Timestamps
<!-- agent-meta:managed-end -->

---

## Sprachregeln

Siehe `.claude/rules/language.md` für die Sprachkonventionen (von sync.py generiert, automatisch geladen).

<!-- Nur projektspezifische Abweichungen hier eintragen — sonst leer lassen. -->

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
