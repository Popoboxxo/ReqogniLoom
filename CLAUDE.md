# ReqogniLoom

> Projektbeschreibung für Claude-Agenten. Diese Datei ist die **einzige Quelle**
> für projektspezifischen Kontext — Agenten lesen sie, statt eigenen Kontext zu haben.
>
> Generiert von agent-meta v0.101.0-beta.1 — `2026-08-27`
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
**Plattform:** Django 4.2+ (Backend) + React 18 + TypeScript 5.5+ (Frontend) + PostgreSQL 16 (Django ORM) + Redis 7 (Cache/Celery-Broker) + Celery 5.3+ (Async) + Docker Compose (5 Services: postgres, redis, backend, celery, frontend)
**Beschreibung:** AI-natives Requirements- und Test-Management-Tool mit MBSE-kompatibler Artefakt-Zerlegung, REST API + nativem MCP Server (11 Tool-Gruppen, 40+ Tools), LLM-Adapter (Anthropic/OpenAI/Ollama/mock), Multi-Tenancy mit Row-Level-Isolation, 15 Trace-Link-Typen, Baselines (3 Scopes), 3 Rigor-Presets (minimal/standard/extended) und i18n (DE/EN).

> Tech-Stack, Architektur & Build-Befehle: discoverable via Repo (Manifeste, CI-Configs).

## Code-Konventionen

- Python (PEP 8, Typings, Docstrings für public API) - TypeScript (ESLint 9, Prettier, strict mode, functional Components + Hooks) - Django-Layer: Models (persistence/) ↔ Services (application/) ↔ Views/Serializers (rest_api/) - React-Layer: api/ (Wrapper) ↔ context/ (State) ↔ components/ (UI) ↔ i18n/ (Labels) - Imports-Reihenfolge: Standard Library → Third-Party → Local (PEP 8) - Keine wildcard imports (from x import *) - Keine direkten Model-Queries in DRF-Views (immer via Serializer + Service) - data-testid auf allen interaktiven UI-Elementen (E2E-Pflicht für Playwright) - CSS Custom Properties aus styles/tokens.css (keine hardcodierten Farben/Größen) - Commits: Conventional Commits Format (feat(REQ-xxx): ..., fix: ..., chore: ...) - Branch-Policy: feat/*, fix/*, refactor/* (NIE direkt auf main) - Requirements-IDs: REQ-L0-*, REQ-L1-*, REQ-L2-*, REQ-L3-* (siehe docs/se/traceability-matrix.md) 

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



## Agenten-Konfiguration

<!-- agent-meta:managed-begin -->
<!-- Dieser Block wird von sync.py bei jedem sync automatisch aktualisiert. -->
<!-- Manuelle Änderungen hier werden überschrieben. -->

> **AI ROUTING:** Claude -> CLAUDE.md | Opencode, Gemini -> AGENTS.md

Generiert von agent-meta v0.101.0-beta.1 — `2026-08-27`
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
