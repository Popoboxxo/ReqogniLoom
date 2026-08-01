# ReqogniLoom

## Projekt

**Name:** ReqogniLoom
**Präfix:** ReqLo
**Plattform:** Django 4.2+ (Backend) + React 18 + TypeScript 5.5+ (Frontend) + PostgreSQL 16 (Django ORM) + Redis 7 (Cache/Celery-Broker) + Celery 5.3+ (Async) + Docker Compose (5 Services: postgres, redis, backend, celery, frontend)
**Beschreibung:** AI-natives Requirements- und Test-Management-Tool mit MBSE-kompatibler Artefakt-Zerlegung, REST API + nativem MCP Server (11 Tool-Gruppen, 40+ Tools), LLM-Adapter (Anthropic/OpenAI/Ollama/mock), Multi-Tenancy mit Row-Level-Isolation, 8 Trace-Link-Typen, Baselines (3 Scopes), 3 Rigor-Presets (minimal/standard/extended) und i18n (DE/EN).

## Tech-Stack

- **Runtime:** Python 3.x (im Container: Django 4.2+, DRF 3.15+, drf-spectacular, psycopg2-binary, celery, redis, reportlab) + Node.js >= 18 (nur für E2E mit Playwright; Vite-Dev-Server läuft im Container) + Vite 5.4+ Dev-Server
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
docker-compose.yml   # 5 Services: postgres, redis, backend, celery, frontend
.meta-config/        # agent-meta Konfiguration (project.yaml)
.agent-meta/         # agent-meta Submodul (Templates, Scripts, Schemas)

```

**Entry-Point:**
```
backend/manage.py            — Django Management (migrate, seed_demo, runserver, shell, check) backend/reqogniloom/settings.py     — Settings-Entry (DRF, JWT, Celery, Apps) backend/reqogniloom/urls.py         — URL-Routing (/api/v1/, /mcp/, /api/schema/, /admin/) frontend/src/index.tsx          — React Entry-Point (ReactDOM.render) frontend/src/App.tsx            — Root-Component (Provider, Router) frontend/src/api/client.ts      — Axios-Client (auto-Bearer-Token-Injection) e2e/playwright.config.ts        — Playwright-Konfiguration (Chromium) 
```

**Besondere Patterns:**
- Django REST Framework (DRF) für REST-API-Endpoints (16 ViewSets + 2 APIViews) - MCP-Server (JSON-RPC 2.0) mit 11 Tool-Gruppen und 40+ Tools für AI-Integration - drf-spectacular für OpenAPI 3.0 Schema-Generierung (Swagger-UI, ReDoc) - Single-Entry-Point Pattern (ADR-01): Layer 2 application/ ist die einzige Domain-Fassade - TenantContext als Thread-Local Singleton + Row-Level-Security (ADR-03) - Configurable Rigor (ADR-04): 3 Presets (minimal/standard/extended) mit gleichem Datenmodell - LLM-Provider-Abstraktion (ADR-02): Capability-Interface mit graceful degradation - 8 Trace-Link-Typen (TRACE_TO, DERIVED_FROM, IMPLEMENTS, TESTS, VERIFIES, RELATED_TO, CONFLICTS_WITH, SUPERCEDES) - 3 Baseline-Scopes (Document, Project, Global) in einer Entität (ADR-07) - Konfigurierbare State-Machines pro Workspace (ADR-06) - Resilience-Decorators (Retry, Circuit-Breaker, Timeout) auf Service-Ebene - V-Modell-Traceability L0-L4 (Stakeholder Needs → System Req → Subsystems → Components → Presentation) 

## Code-Konventionen

- Python (PEP 8, Typings, Docstrings für public API) - TypeScript (ESLint 9, Prettier, strict mode, functional Components + Hooks) - Django-Layer: Models (persistence/) ↔ Services (application/) ↔ Views/Serializers (rest_api/) - React-Layer: api/ (Wrapper) ↔ context/ (State) ↔ components/ (UI) ↔ i18n/ (Labels) - Imports-Reihenfolge: Standard Library → Third-Party → Local (PEP 8) - Keine wildcard imports (from x import *) - Keine direkten Model-Queries in DRF-Views (immer via Serializer + Service) - data-testid auf allen interaktiven UI-Elementen (E2E-Pflicht für Playwright) - CSS Custom Properties aus styles/tokens.css (keine hardcodierten Farben/Größen) - Commits: Conventional Commits Format (feat(REQ-xxx): ..., fix: ..., chore: ...) - Branch-Policy: feat/*, fix/*, refactor/* (NIE direkt auf main) - Requirements-IDs: REQ-L0-*, REQ-L1-*, REQ-L2-*, REQ-L3-* (siehe docs/se/traceability-matrix.md) 

## Build & Development

```bash
# Build
docker-compose build

# Tests
pytest (Backend) + npm test (Frontend)

# Dev-Stack starten
docker-compose up

# Nach Änderungen neu laden
docker-compose restart (oder Hot Reload je nach Service)
```

## Anforderungs-Kategorien

Kategorien für `docs/REQUIREMENTS.md`:

- **Functional** — Features, User Stories, CRUD auf Requirements/Architecture/TestCases/ADRs/Risks/Issues
- **Non-Functional** — Performance, Sicherheit, Skalierbarkeit, Audit-Compliance, Multi-Tenancy
- **API** — REST API (/api/v1/, JWT-Auth, OpenAPI) und MCP Server (/mcp/, JSON-RPC 2.0, 11 Tool-Gruppen)
- **UI/UX** — Frontend (React 18 SPA), 17 Component-Bereiche, i18n (DE/EN), Barrierefreiheit
- **Data** — Generic Artifact Model, Multi-Tenancy via Row-Level-Security, Configurable Rigor
- **Integration** — Externe Systeme, CSV-Bulk-Import, PDF-Report-Export, LLM-Provider (Anthropic/OpenAI/Ollama/mock)
- **Test** — Test-Management, Test-Run-Protokollierung (4-Phasen-Lifecycle), Coverage-Tracking
- **Workflow** — Konfigurierbare State-Machines pro Workspace, Approval-Gates, Transition-Validierung
- **Baseline** — Snapshot, Feld-Level-Diff, 3 Scopes (Document/Project/Global)
- **Traceability** — 8 Link-Typen, Coverage-Aggregation, V-Modell L0-L4-Traceability
- **AI** — LLM-Provider-Abstraktion, Decomposition, Validation, Consistency-Check
- **Resilience** — Retry, Circuit-Breaker, Timeout-Decorators, async via Celery



<!-- agent-meta:managed-begin -->
> **ROUTING:**


 Gemini->AGENTS.md
> **ENTRY:** `orchestrator`-Agent (für alle Dev-Tasks).
`agent-meta v0.91.2` | DoD: `rapid-prototyping` | REQ-Trace: `false`


## Regeln

# Branch-Guard

Verwende Feature-Branches (`feat/`, `fix/`, `chore/`). Keine Code-Änderungen direkt auf `main` oder `master`.



# Commit-Konventionen

Verwende Conventional Commits (feat, fix, chore).
Beschreibungssprache: `Englisch`
Max 72 Zeichen in erster Zeile. Imperativ.
Format: `<type>: <beschreibung>` (Bsp: `feat: ...`)



# Sprachregeln

| Kontext | Sprache |
|---|---|
| User-Kommunikation | **Deutsch** |
| User-Input | **Deutsch** |
| Externe Doku | **Englisch** |
| Interne Doku | **Deutsch** |
| Code/Commits | **Englisch** |



# Orchestrator
Jeder Dev-Task -> `orchestrator`. Ausnahme: User Override oder 1-Step (falls erlaubt).
## Direkter Dispatch (nur nach Regel 2)

| Operation | Direkt an | Bedingung |
|-----------|-----------|-----------|
| Commit, Push, Branch, Tag, PR | `git` | Einzelner Git-Befehl |
| Sync, Upgrade, Meta-Konfiguration | `agent-meta-manager` | Reine agent-meta-Operation |
| Bug/Feature/Verbesserung melden | `feedback` | Issue-Erstellung |
| Session-Erkenntnisse speichern | `documenter` | Nur bei Session-Ende |

> **Faustregel:** >1 Tool-Call → Orchestrator. Unsicher → Orchestrator.

## Git Delegation
Git Mutationen (commit, push, add etc) -> `git` Agent. Read-only (status, log) im Main Chat ok.

Native Extensions (Skills/Hooks) erlaubt, ignorieren nicht Branch-Guard/DoD.

Anti-Recursion: Worker dürfen nicht an `orchestrator` zurück delegieren.





## Agent Directory
> ⚠️ **ACHTUNG:** Agenten (Prompts) liegen in `.gemini/agents bzw. .opencode/agents`.

| Agent | Core Capabilities |
|-------|-------------------|

| `accessibility-specialist` | WCAG 2.1/2.2 Compliance-Audit, ARIA-Checks, Keyboard-Navigation, Screenreader... |

| `agent-meta-manager` | agent-meta verwalten: Upgrade, Sync, Feedback, projektspezifische Agenten anl... |

| `agent-meta-scout` | Claude-Ökosystem scouten: neue Skills, Rollen, Rules und Patterns entdecken |

| `api-specialist` | OpenAPI/Contract-First API Design, Schnittstellen-Spezifikationen. |

| `bug-feature-analyzer` | Issue-Triage: Eingehende Bug-Meldungen und Feature-Requests analysieren und k... |

| `code-reviewer` | Clean Code Gatekeeper: Blast-Radius-Analyse, SOLID/DRY Prüfung, Code-Qualität... |

| `concept-reviewer` | Konzept-Critic: reviewt Design-Docs und Konzepte auf Vollständigkeit, Logik, ... |

| `data-engineer` | ETL/ELT-Pipelines, Schema-Migration (Datenebene), Data-Quality-Checks, Lineag... |

| `database-engineer` | Relationales Schema-Design, Datenbank-Migrationen, Query-Optimierung und Inde... |

| `dependency-auditor` | Supply-Chain-Hygiene: SBOM-Analyse, Lizenz-Kompatibilität, Version-Drift und ... |

| `developer` | Feature-Implementierung und Bugfixes |

| `devops-engineer` | CI/CD, Infrastructure as Code, Kubernetes, Observability. |

| `docker` | Dev-Stack verwalten, Test-Stack starten, Binary-Management, Dockerfiles erste... |

| `documenter` | CODEBASE_OVERVIEW, ARCHITECTURE, README, Erkenntnisse pflegen |

| `e2e-tester` | E2E-Tests, visuelle Regression und Accessibility-Audits via Playwright |

| `effort-estimator` | Schätzt Aufwände für Entwicklungsaufgaben basierend auf Task-Typ und LLM-Kali... |

| `explorer` | Read-only Codebase-Recherche, Dependency- und Impact-Mapping, Datei- und Symb... |

| `export-manager` | Target-agnostischer Output-Router: Markdown, Confluence, Jira-Xray, Notion. |

| `feature` | Feature-Lifecycle-Subagent: Branch → REQ → TDD → Dev → Validate → PR |

| `feedback` | Projekt-Feedback standardisieren: Bugs, Features, Verbesserungen als GitHub I... |

| `git` | Commits, Branches, Tags, Push/Pull und alle Git-Operationen |

| `ideation` | Neue Ideen explorieren, Vision schärfen, Übergabe an requirements |

| `incident-responder` | Live-Incident-Koordination: korreliert Logs und Metriken, führt Runbook-Schri... |

| `intern-developer` | [EASTER EGG / GAG] Der übereifrige Praktikant |

| `junior-developer` | Triviale Code-Änderungen (≤2 Dateien, kein Architektur-Impact) |

| `knowledge-curator` | Strategische Knowledge-Engine-Steuerung: Schema-Evolution, Wiki-Strukturierun... |

| `knowledge-gardener` | Kleinteilige Wiki-Pflege: Links reparieren, Tags harmonisieren, Frontmatter e... |

| `knowledge-indexer` | Pflegt index.md (Content-Katalog, OKF §6) und log.md (Chronologisches Event-L... |

| `knowledge-ingestor` | Sources einlesen, Key Information extrahieren, Wiki-Seiten erstellen/ aktuali... |

| `knowledge-linter` | Wiki-Gesundheitscheck: Widersprüche, Orphans, veraltete Claims, kaputte Links... |

| `knowledge-migrator` | Vorhandene Projektinhalte aufräumen und OKF-konform ins Knowledge Wiki migrieren |

| `knowledge-querier` | Fragen gegen das Knowledge Wiki beantworten |

| `log-analyzer` | System- und Applikations-Logs analysieren: Frequency-Clustering, Severity-Kla... |

| `meta-feedback` | Verbesserungsvorschläge für agent-meta als GitHub Issues einreichen |

| `orchestrator` | Einstiegspunkt für alle Entwicklungsaufgaben |

| `performance-optimizer` | Big-O Bottleneck-Identifikation und datengetriebene Performance-Optimierung. |

| `principal-developer` | Last-Resort-Eskalationsstufe |

| `refactoring-specialist` | Systematische großflächige Code-Transformation mit Sicherheitsnetz: Strangler... |

| `release` | Versioning, Changelog, Build-Artifact, GitHub Release erstellen |

| `requirements` | Anforderungen aufnehmen, REQ-IDs vergeben, REQUIREMENTS.md pflegen |

| `se-architect` | Zerlegt Blackboxes in Whiteboxes nach strengen Architekturgesetzen (CQRS, Ort... |

| `se-critic` | Prüft Architekturentscheidungen iterativ auf Vollständigkeit, Konsistenz und ... |

| `se-developer` | Standard SE-Leaf-Implementierung (2-4 Interfaces) mit strikter Interface-Disz... |

| `se-integration-and-test-manager` | V&V-Orchestrator: Bestimmt Integrationsstrategie und koordiniert Test-Ebenen. |

| `se-interface-mgr` | Verwaltet und validiert alle Schnittstellenverträge domänenübergreifend. |

| `se-junior-developer` | Triviale SE-Leaf-Implementierung (0-1 Interfaces, kein cross-cutting) |

| `se-requirements` | Nimmt Stakeholder-Bedürfnisse auf und erstellt das formale L1-Blackbox-Requir... |

| `se-senior-developer` | Komplexe SE-Leaf-Implementierung (5+ Interfaces, cross-cutting, boundary-leve... |

| `se-termination` | Entscheidet deterministisch, ob der L3-Component-Leaf-Node erreicht wurde. |

| `se-test-engineer` | Entwickelt MBSE-Testmodelle und entwirft Integrationstests für den rechten V-... |

| `se-testreviewer` | Auditiert Teststrategien auf Edge-Cases, Boundary Values, Äquivalenzklassen u... |

| `se-validator` | L1 System-Validierung: End-to-End User Journeys gegen Stakeholder-Bedürfnisse. |

| `se-verifier` | Multi-Level Verification (L1-Ln): Prüft integrierte Systeme gegen Architektur... |

| `senior-developer` | Komplexe Features, Architektur-Entscheidungen, schwierige Bugs, Cross-Cutting... |

| `sre-engineer` | Proaktive Reliability-Disziplin: SLI/SLO-Definition, Error-Budgets, Capacity-... |

| `technical-writer` | Externe entwickler- und nutzergerichtete Doku: API-Referenzen, Getting-Starte... |

| `tester` | TDD, Test-Suite ausführen, Testabdeckung sichern |

| `ui-ux-designer` | UI-Spezifikationen, Mockups und Design-Systeme erstellen. |

| `validator` | Code gegen REQs prüfen, DoD-Checkliste, Traceability-Audit |


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











## Eigene Notizen

Hier kannst du eigene, projektspezifische Notizen eintragen. Dieser Bereich wird von `agent-meta` nicht überschrieben!

<!-- headroom:rtk-instructions -->
# RTK (Rust Token Killer) - Token-Optimized Commands

When running shell commands, **always prefix with `rtk`**. This reduces context
usage by 60-90% with zero behavior change. If rtk has no filter for a command,
it passes through unchanged — so it is always safe to use.

## Key Commands
```bash
# Git (59-80% savings)
rtk git status          rtk git diff            rtk git log

# Files & Search (60-75% savings)
rtk ls <path>           rtk read <file>         rtk grep <pattern>
rtk find <pattern>      rtk diff <file>

# Test (90-99% savings) — shows failures only
rtk pytest tests/       rtk cargo test          rtk test <cmd>

# Build & Lint (80-90% savings) — shows errors only
rtk tsc                 rtk lint                rtk cargo build
rtk prettier --check    rtk mypy                rtk ruff check

# Analysis (70-90% savings)
rtk err <cmd>           rtk log <file>          rtk json <file>
rtk summary <cmd>       rtk deps                rtk env

# GitHub (26-87% savings)
rtk gh pr view <n>      rtk gh run list         rtk gh issue list

# Infrastructure (85% savings)
rtk docker ps           rtk kubectl get         rtk docker logs <c>

# Package managers (70-90% savings)
rtk pip list            rtk pnpm install        rtk npm run <script>
```

## Rules
- In command chains, prefix each segment: `rtk git add . && rtk git commit -m "msg"`
- For debugging, use raw command without rtk prefix
- `rtk proxy <cmd>` runs command without filtering but tracks usage
<!-- /headroom:rtk-instructions -->

<!-- agent-meta:bootstrap-begin -->

## Agent Bootstrap — Session-Start Pflicht

Gemini/Antigravity benötigt eine einmalige Agent-Registrierung pro Session.
**Führe folgende Schritte zu Beginn JEDER Session aus:**

1. Lies alle Agenten-Dateien aus `.gemini/agents/`:
   - `accessibility-specialist.md` → registriere als `accessibility-specialist`
   - `agent-meta-manager.md` → registriere als `agent-meta-manager`
   - `agent-meta-scout.md` → registriere als `agent-meta-scout`
   - `api-specialist.md` → registriere als `api-specialist`
   - `bug-feature-analyzer.md` → registriere als `bug-feature-analyzer`
   - `code-reviewer.md` → registriere als `code-reviewer`
   - `concept-reviewer.md` → registriere als `concept-reviewer`
   - `data-engineer.md` → registriere als `data-engineer`
   - `database-engineer.md` → registriere als `database-engineer`
   - `dependency-auditor.md` → registriere als `dependency-auditor`
   - `developer.md` → registriere als `developer`
   - `devops-engineer.md` → registriere als `devops-engineer`
   - `docker.md` → registriere als `docker`
   - `documenter.md` → registriere als `documenter`
   - `e2e-tester.md` → registriere als `e2e-tester`
   - `effort-estimator.md` → registriere als `effort-estimator`
   - `explorer.md` → registriere als `explorer`
   - `export-manager.md` → registriere als `export-manager`
   - `feature.md` → registriere als `feature`
   - `feedback.md` → registriere als `feedback`
   - `git.md` → registriere als `git`
   - `ideation.md` → registriere als `ideation`
   - `incident-responder.md` → registriere als `incident-responder`
   - `intern-developer.md` → registriere als `intern-developer`
   - `junior-developer.md` → registriere als `junior-developer`
   - `knowledge-curator.md` → registriere als `knowledge-curator`
   - `knowledge-gardener.md` → registriere als `knowledge-gardener`
   - `knowledge-indexer.md` → registriere als `knowledge-indexer`
   - `knowledge-ingestor.md` → registriere als `knowledge-ingestor`
   - `knowledge-linter.md` → registriere als `knowledge-linter`
   - `knowledge-migrator.md` → registriere als `knowledge-migrator`
   - `knowledge-querier.md` → registriere als `knowledge-querier`
   - `log-analyzer.md` → registriere als `log-analyzer`
   - `meta-feedback.md` → registriere als `meta-feedback`
   - `orchestrator.md` → registriere als `orchestrator`
   - `performance-optimizer.md` → registriere als `performance-optimizer`
   - `principal-developer.md` → registriere als `principal-developer`
   - `refactoring-specialist.md` → registriere als `refactoring-specialist`
   - `release.md` → registriere als `release`
   - `requirements.md` → registriere als `requirements`
   - `se-architect.md` → registriere als `se-architect`
   - `se-critic.md` → registriere als `se-critic`
   - `se-developer.md` → registriere als `se-developer`
   - `se-integration-and-test-manager.md` → registriere als `se-integration-and-test-manager`
   - `se-interface-mgr.md` → registriere als `se-interface-mgr`
   - `se-junior-developer.md` → registriere als `se-junior-developer`
   - `se-requirements.md` → registriere als `se-requirements`
   - `se-senior-developer.md` → registriere als `se-senior-developer`
   - `se-termination.md` → registriere als `se-termination`
   - `se-test-engineer.md` → registriere als `se-test-engineer`
   - `se-testreviewer.md` → registriere als `se-testreviewer`
   - `se-validator.md` → registriere als `se-validator`
   - `se-verifier.md` → registriere als `se-verifier`
   - `senior-developer.md` → registriere als `senior-developer`
   - `sre-engineer.md` → registriere als `sre-engineer`
   - `technical-writer.md` → registriere als `technical-writer`
   - `tester.md` → registriere als `tester`
   - `ui-ux-designer.md` → registriere als `ui-ux-designer`
   - `validator.md` → registriere als `validator`

2. Registriere jeden Agenten via define_subagent API-Call:
   ```
   define_subagent(name="accessibility-specialist", ...)
   define_subagent(name="agent-meta-manager", ...)
   define_subagent(name="agent-meta-scout", ...)
   define_subagent(name="api-specialist", ...)
   define_subagent(name="bug-feature-analyzer", ...)
   define_subagent(name="code-reviewer", ...)
   define_subagent(name="concept-reviewer", ...)
   define_subagent(name="data-engineer", ...)
   define_subagent(name="database-engineer", ...)
   define_subagent(name="dependency-auditor", ...)
   define_subagent(name="developer", ...)
   define_subagent(name="devops-engineer", ...)
   define_subagent(name="docker", ...)
   define_subagent(name="documenter", ...)
   define_subagent(name="e2e-tester", ...)
   define_subagent(name="effort-estimator", ...)
   define_subagent(name="explorer", ...)
   define_subagent(name="export-manager", ...)
   define_subagent(name="feature", ...)
   define_subagent(name="feedback", ...)
   define_subagent(name="git", ...)
   define_subagent(name="ideation", ...)
   define_subagent(name="incident-responder", ...)
   define_subagent(name="intern-developer", ...)
   define_subagent(name="junior-developer", ...)
   define_subagent(name="knowledge-curator", ...)
   define_subagent(name="knowledge-gardener", ...)
   define_subagent(name="knowledge-indexer", ...)
   define_subagent(name="knowledge-ingestor", ...)
   define_subagent(name="knowledge-linter", ...)
   define_subagent(name="knowledge-migrator", ...)
   define_subagent(name="knowledge-querier", ...)
   define_subagent(name="log-analyzer", ...)
   define_subagent(name="meta-feedback", ...)
   define_subagent(name="orchestrator", ...)
   define_subagent(name="performance-optimizer", ...)
   define_subagent(name="principal-developer", ...)
   define_subagent(name="refactoring-specialist", ...)
   define_subagent(name="release", ...)
   define_subagent(name="requirements", ...)
   define_subagent(name="se-architect", ...)
   define_subagent(name="se-critic", ...)
   define_subagent(name="se-developer", ...)
   define_subagent(name="se-integration-and-test-manager", ...)
   define_subagent(name="se-interface-mgr", ...)
   define_subagent(name="se-junior-developer", ...)
   define_subagent(name="se-requirements", ...)
   define_subagent(name="se-senior-developer", ...)
   define_subagent(name="se-termination", ...)
   define_subagent(name="se-test-engineer", ...)
   define_subagent(name="se-testreviewer", ...)
   define_subagent(name="se-validator", ...)
   define_subagent(name="se-verifier", ...)
   define_subagent(name="senior-developer", ...)
   define_subagent(name="sre-engineer", ...)
   define_subagent(name="technical-writer", ...)
   define_subagent(name="tester", ...)
   define_subagent(name="ui-ux-designer", ...)
   define_subagent(name="validator", ...)
   ```

3. Erst danach: Bearbeite User-Anfragen (Delegation an Orchestrator etc.)

> **Ohne diese Registrierung existieren die Agenten NICHT in der Runtime**
> und der Orchestrator kann nicht delegieren.
<!-- agent-meta:bootstrap-end -->

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
