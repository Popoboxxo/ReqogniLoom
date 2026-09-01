# ReqogniLoom

> Projektbeschreibung für Claude-Agenten. Diese Datei ist die **einzige Quelle**
> für projektspezifischen Kontext — Agenten lesen sie, statt eigenen Kontext zu haben.
>
> Generiert von agent-meta v0.100.0 — `2026-08-29`
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

Hier kannst du eigene, projektspezifische Notizen eintragen. Dieser Bereich wird von `agent-meta` nicht überschrieben!

---

## Projekt

**Name:** ReqogniLoom
**Präfix:** ReqLo
**Plattform:** Django 5.2+ (Backend) + React 18 + TypeScript 5.5+ (Frontend) + PostgreSQL 16 (Django ORM) + Redis 7 (Cache/Celery-Broker) + Celery 5.3+ (Async) + Docker Compose (8 Services: postgres, postgres-backup, redis, backend, migrate, celery, celery-beat, frontend)
**Beschreibung:** AI-natives Requirements- und Test-Management-Tool mit MBSE-kompatibler Artefakt-Zerlegung, REST API + nativem MCP Server (30 Tool-Gruppen, 171 Tools), LLM-Adapter (Anthropic/OpenAI/Ollama/mock), Multi-Tenancy mit Row-Level-Isolation, 15 Trace-Link-Typen, Baselines (3 Scopes), 3 Rigor-Presets (minimal/standard/extended) und i18n (DE/EN).

## Tech-Stack

- **Runtime:** Python 3.x (im Container: Django 5.2+, DRF 3.15+, drf-spectacular, psycopg2-binary, celery, redis, reportlab) + Node.js >= 18 (nur für E2E mit Playwright; Vite-Dev-Server läuft im Container) + Vite 5.4+ Dev-Server
- **Sprache:** Python 3.x + TypeScript 5.5+ (strict) + YAML + Bash
- **Key-Dependencies:** - Docker >= 24
- Docker Compose >= 2.x
- Node.js >= 18 (nur für E2E-Tests mit Playwright)
- Python 3.x (im Container)


## Architektur

```
backend/             # Django REST API (17 Apps) #   Layer 0: persistence, auth_tenancy, presets, audit #   Layer 1: llm_adapter, traceability, workflow, baseline #   Layer 2: application (19 Services) #   Layer 3: rest_api, mcp_server #   Ext: diagram, icd, se_metrics, resilience, admin_ops, test_runs #   reqogniloom/  # Django-Projekt (settings.py, urls.py, wsgi.py, asgi.py)
frontend/            # React 18 + TS SPA #   src/api/  src/components/  src/context/  src/i18n/ #   src/styles/  src/test/  src/types/
e2e/                 # Playwright/Chromium E2E-Tests (111 Tests)
docs/                # Anforderungen, Architektur, SE-Kaskade, Session-Reports
deploy/              # Deployment-Beispiele: docker-compose.yml (full), docker-compose.minimal.yml, docker-compose.override.yml, README.md (KI-Agenten-lesbar)
testing/             # docker-compose.test.yml (CI-/lokaler Test-Overlay, kein Deployment-File)
.meta-config/        # agent-meta Konfiguration (project.yaml)
.agent-meta/         # agent-meta Submodul (Templates, Scripts, Schemas)

```

**Entry-Point:**
```
backend/manage.py            — Django Management (migrate, seed_demo, runserver, shell, check) backend/reqogniloom/settings.py     — Settings-Entry (DRF, JWT, Celery, Apps) backend/reqogniloom/urls.py         — URL-Routing (/api/v1/, /mcp/, /api/schema/, /admin/) frontend/src/index.tsx          — React Entry-Point (ReactDOM.render) frontend/src/App.tsx            — Root-Component (Provider, Router) frontend/src/api/client.ts      — Axios-Client (auto-Bearer-Token-Injection) e2e/playwright.config.ts        — Playwright-Konfiguration (Chromium) 
```

**Besondere Patterns:**
- Django REST Framework (DRF) für REST-API-Endpoints (27 ViewSets + 67 APIViews) - MCP-Server (JSON-RPC 2.0) mit 30 Tool-Gruppen und 171 Tools für AI-Integration - drf-spectacular für OpenAPI 3.0 Schema-Generierung (Swagger-UI, ReDoc) - Single-Entry-Point Pattern (ADR-01): Layer 2 application/ ist die einzige Domain-Fassade - TenantContext als Thread-Local Singleton + Row-Level-Security (ADR-03) - Configurable Rigor (ADR-04): 3 Presets (minimal/standard/extended) mit gleichem Datenmodell - LLM-Provider-Abstraktion (ADR-02): Capability-Interface mit graceful degradation - 15 Trace-Link-Typen (parent-child, derives-from, satisfies, verifies, implements, refines, documents, realizes, traces, copy-of, allocated-to, uses-term, decides, decomposes, diagram-ref; siehe backend/traceability/types.py) - 3 Baseline-Scopes (Document, Project, Global) in einer Entität (ADR-07) - Konfigurierbare State-Machines pro Workspace (ADR-06) - Resilience-Decorators (Retry, Circuit-Breaker, Timeout) auf Service-Ebene - V-Modell-Traceability L0-L4 (Stakeholder Needs → System Req → Subsystems → Components → Presentation) 

## Code-Konventionen

- Python (PEP 8, Typings, Docstrings für public API) - TypeScript (ESLint 9, Prettier, strict mode, functional Components + Hooks) - Django-Layer: Models (persistence/) ↔ Services (application/) ↔ Views/Serializers (rest_api/) - React-Layer: api/ (Wrapper) ↔ context/ (State) ↔ components/ (UI) ↔ i18n/ (Labels) - Imports-Reihenfolge: Standard Library → Third-Party → Local (PEP 8) - Keine wildcard imports (from x import *) - Keine direkten Model-Queries in DRF-Views (immer via Serializer + Service) - data-testid auf allen interaktiven UI-Elementen (E2E-Pflicht für Playwright) - CSS Custom Properties aus styles/tokens.css (keine hardcodierten Farben/Größen) - Commits: Conventional Commits Format (feat(REQ-xxx): ..., fix: ..., chore: ...) - Branch-Policy: feat/*, fix/*, refactor/* (NIE direkt auf main) - Requirements-IDs: REQ-L0-*, REQ-L1-*, REQ-L2-*, REQ-L3-* (siehe docs/se/traceability-matrix.md) 

## Build & Development

Compose-Dateien liegen NICHT im Repo-Root, sondern unter `deploy/` (Deployment-Beispiele) und `testing/` (Test-Overlay) — siehe `deploy/README.md` (KI-Agenten-lesbarer Abschnitt "For AI agents").

```bash
# Build
make build

# Tests
make test-backend  # pytest, Container-basiert
make test-frontend # vitest, Container-basiert

# Dev-Stack starten (Full-Stack + Hot-Reload-Override)
make up

# Nach Änderungen neu laden
make up   # recreated Container bei geänderter Config/Env — `docker compose restart` liest .env NICHT neu
```

## Anforderungs-Kategorien

Kategorien für `docs/REQUIREMENTS.md`:

- **Functional** — Features, User Stories, CRUD auf Requirements/Architecture/TestCases/ADRs/Risks/Issues
- **Non-Functional** — Performance, Sicherheit, Skalierbarkeit, Audit-Compliance, Multi-Tenancy
- **API** — REST API (/api/v1/, JWT-Auth, OpenAPI) und MCP Server (/mcp/, JSON-RPC 2.0, 30 Tool-Gruppen)
- **UI/UX** — Frontend (React 18 SPA), 41 Component-Bereiche, i18n (DE/EN), Barrierefreiheit
- **Data** — Generic Artifact Model, Multi-Tenancy via Row-Level-Security, Configurable Rigor
- **Integration** — Externe Systeme, CSV-Bulk-Import, PDF-Report-Export, LLM-Provider (Anthropic/OpenAI/Ollama/mock)
- **Test** — Test-Management, Test-Run-Protokollierung (4-Phasen-Lifecycle), Coverage-Tracking
- **Workflow** — Konfigurierbare State-Machines pro Workspace, Approval-Gates, Transition-Validierung
- **Baseline** — Snapshot, Feld-Level-Diff, 3 Scopes (Document/Project/Global)
- **Traceability** — 15 Link-Typen, Coverage-Aggregation, V-Modell L0-L4-Traceability
- **AI** — LLM-Provider-Abstraktion, Decomposition, Validation, Consistency-Check
- **Resilience** — Retry, Circuit-Breaker, Timeout-Decorators, async via Celery



## Agenten-Konfiguration

<!-- agent-meta:managed-begin -->
<!-- Dieser Block wird von sync.py bei jedem sync automatisch aktualisiert. -->
<!-- Manuelle Änderungen hier werden überschrieben. -->

> **AI ROUTING:** Claude -> CLAUDE.md | Opencode, Gemini -> AGENTS.md

Generiert von agent-meta v0.100.0 — `2026-09-01`
DoD-Preset: **rapid-prototyping** | REQ-Traceability: false | Tests: false | Codebase-Overview: false | Security-Audit: false
> **Einstiegspunkt:** Du bist im `main-chat` Modus. Du agierst direkt als Router und Worker (siehe `use-orchestrator.md`).

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
