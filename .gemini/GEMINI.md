# ReqogniLoom

ReqogniLoom ist ein AI-natives Requirements- und Test-Management-Tool mit MBSE-Unterstützung. Tech-Stack: Django 5.2+ (Backend) + React 18 + TypeScript (Frontend) + PostgreSQL 16 + Redis 7 + Celery 5.3+ + Docker Compose. Schnittstellen: REST API unter /api/v1/ (DRF, 27 ViewSets + 67 APIViews, JWT-Auth mit vierstufiger RBAC-Matrix + Item-Level-Permissions, OpenAPI via drf-spectacular) und nativer MCP Server unter /mcp/ (JSON-RPC 2.0, Transports: HTTP, SSE, stdio; 22 Tool-Gruppen mit 171 Tools; API-Key `reqlo_*`). Fähigkeiten: Requirements Management, Architecture Elements (MBSE-kompatibel), Test-Management, 15 Trace-Link-Typen, Baselines (3 Scopes) mit Diff-Engine, Artifact-Diff (feld-level), History-Endpoint, PDF-Report-Export, Test-Run-Protokollierung, CSV-Bulk-Import, API-Key-Management, Visual Artifact Diff, 3 Rigor-Presets (Minimal/Standard/Extended), Terminology-Profile (dev_mode/se_mode), Audit-Log, Multi-Tenancy via Row-Level-Security. LLM-Adapter: Anthropic, OpenAI, Ollama, mock (Default: mock).

<!-- agent-meta:managed-begin -->
<!-- This block is automatically updated by sync.py on every sync. -->
<!-- Manual changes here will be overwritten. -->

> **AI ROUTING:** Claude -> CLAUDE.md | Opencode -> AGENTS.md | Gemini -> .gemini/GEMINI.md

Generiert von agent-meta v0.83.0 — `2026-07-25`
DoD-Preset: **spec-driven** | REQ-Traceability: false | Tests: false | Codebase-Overview: false | Security-Audit: false

> **Einstiegspunkt:** Starte mit dem `orchestrator`-Agenten für alle Entwicklungsaufgaben — Ausnahmen siehe Abschnitt »Orchestrator — Universal Router«.

| Agent | Zuständigkeit |
|-------|--------------|
| `accessibility-specialist` | Accessibility-Audit: WCAG 2.1/2.2, ARIA, Keyboard-Nav, Screenreader-Guidelines, Kontrast, Focus-Management, A11y-Tree — Findings mit A/AA/AAA-Severity |
| `agent-meta-manager` | agent-meta verwalten: Upgrade, Sync, Feedback, projektspezifische Agenten anlegen |
| `agent-meta-scout` | KI-Ökosystem scouten: neue Skills, Rollen, Rules und Patterns für agent-meta entdecken |
| `api-specialist` | Verwende diesen Agenten fuer API-Design, OpenAPI-Spezifikationen und Contract-First Development. |
| `bug-feature-analyzer` | Issue-Triage: Bug vs. User-Error vs. Feature vs. Out-of-Scope klassifizieren — vor developer/feature-Delegation |
| `code-reviewer` | Prüft Code-Qualität, Blast-Radius und Clean Code — nicht funktionale Korrektheit (das macht validator). |
| `concept-reviewer` | Konzept/Design-Doc reviewen: Vollständigkeit, Logik, Risiken, Approve/Iterate |
| `data-engineer` | Data-Pipelines: ETL/ELT, Schema-Migration (Datenebene), Data-Quality, Lineage, Pipeline-Monitoring, Streaming/Batch — übergibt Pipeline-Spec an developer |
| `database-engineer` | Datenbank-Design: Schema, Migrationen (Alembic/Flyway-Stil), Query-Optimierung, Index-Strategie — übergibt Schema-Vertrag an developer |
| `dependency-auditor` | Dependency-Audit: SBOM, Lizenz-Kompatibilität, Version-Drift, veraltete/verwundbare Pakete — Findings über feedback als Issue |
| `developer` | Feature-Implementierung und Bugfixes nach REQ-IDs |
| `devops-engineer` | Verwende diesen Agenten fuer CI/CD, IaC, Kubernetes, Monitoring und Infrastructure-Aufgaben. |
| `docker` | Dev-Stack starten/stoppen, Dockerfiles, Binary-Management |
| `documenter` | Doku pflegen: CODEBASE_OVERVIEW, ARCHITECTURE, README, Erkenntnisse |
| `e2e-tester` | Browser-Testing-Agent: E2E-Flows, visuelle Regression, Accessibility-Audit — nicht für Unit-Tests |
| `effort-estimator` | Aufwandsschätzung für Tasks — delegiere hierher wenn User nach Zeit/Kosten fragt |
| `explorer` | Codebase analysieren / Dependencies / Impact — read-only, delegiert Findings |
| `export-manager` | Verwende diesen Agenten fuer Export-Routing von strukturierten Daten zu konfigurierten Targets. |
| `feature` | Feature-Lifecycle-Subagent: Branch → REQ → TDD → Dev → Validate → PR. Wird vom Orchestrator gestartet, nicht direkt vom User. |
| `feedback` | Projekt-Feedback: Bugs, Features, Verbesserungen als GitHub Issues standardisiert einreichen — immer vor git |
| `git` | Commits, Branches, Tags, Push/Pull und alle Git-Operationen |
| `ideation` | Neue Ideen explorieren, Vision schärfen, Übergabe an requirements |
| `incident-responder` | Incident-Koordination: Logs/Metriken triagieren, Runbook ausführen, RCA (5-Whys) erstellen, Hotfixes priorisieren — RCA an documenter, Fix an developer |
| `intern-developer` | Gag/Easter-egg agent: an over-eager, clueless intern who explains code wrong with great enthusiasm. Read-only. Do not route real work here. |
| `junior-developer` | Low-Tier-Developer: triviale Fixes, Typos, kleine klar umrissene Änderungen — eskaliert bei Scope-Überschreitung |
| `log-analyzer` | Log-Analyse: Fehler clustern, Severity klassifizieren (RFC 5424), Findings als Issues oder Tasks delegieren |
| `meta-feedback` | Verbesserungsvorschläge für agent-meta als GitHub Issues einreichen |
| `orchestrator` | Einstiegspunkt für ALLE Entwicklungsaufgaben — zerlegt komplexe Tasks und dispatched parallel |
| `performance-optimizer` | Verwende diesen Agenten fuer Performance-Analyse, Big-O-Optimierung und Bottleneck-Beseitigung. |
| `principal-developer` | Last-resort developer: only after senior-developer failed multiple times — root-cause analysis, systemic reasoning, no symptom fixes. The most expensive call in the system. |
| `refactoring-specialist` | Systematische Transformation: Strangler Fig, inkrementelles Refactoring, Legacy-Modernisierung, Feature-Flag-Rewrites — braucht exklusiven Zugriff auf betroffene Module |
| `release` | Versioning, Changelog, Build-Artifact, GitHub Release erstellen |
| `requirements` | Anforderungen aufnehmen, REQ-IDs vergeben, REQUIREMENTS.md pflegen |
| `se-architect` | Design L1 and L2 architectures from requirements. |
| `se-critic` | Validate requirements before architecture; audit decompositions. |
| `se-developer` | Standard SE leaf node implementation. Handles multiple interfaces (2-4). Escalates cross-cutting or boundary-level leafs.
 |
| `se-integration-and-test-manager` | Orchestriert den gesamten rechten Flügel der V&V-Kaskade — Bottom-Up, Top-Down, Integrationsplanung. |
| `se-interface-mgr` | Manages generic signal flow, deterministic sync across systems |
| `se-junior-developer` | Use for trivial SE leaf nodes: single component, 0-1 interfaces, no cross-cutting concerns. Escalates if interface complexity grows.
 |
| `se-requirements` | Use this agent to clarify requirements and start the SE cascade. |
| `se-senior-developer` | Complex SE leaf nodes: cross-cutting, boundary, security/performance-critical, 5+ interfaces. |
| `se-termination` | Dynamic depth termination with SE_MIN_DEPTH/SE_MAX_DEPTH control |
| `se-test-engineer` | Use this agent to create model-based test models and integration test strategies from architectural decompositions. |
| `se-testreviewer` | Use this agent to review and audit test models and integration test strategies before execution. |
| `se-validator` | Validiert das System auf L1-Ebene durch User-Journey-Simulation — ignoriert Code, prüft ob der User-Need erfüllt ist. |
| `se-verifier` | Use this agent to verify integrated systems against their specifications on all architecture levels (L1 through Ln). |
| `senior-developer` | High-Tier-Developer: Architektur-Impact, komplexe/riskante Änderungen, schwierige Bugs — analysiert erst, implementiert dann |
| `sre-engineer` | Reliability proaktiv: SLI/SLO, Error-Budgets, Capacity-Planning, Toil-Reduktion, Runbooks, Reliability-Review vor Deploy — Runbook an documenter, Fix an developer |
| `technical-writer` | Externe Doku: API-Referenz, Getting-Started, SDK-Docs, Tutorials, CLI-Help, User-Release-Notes, Microcopy — für externe Entwickler und Endnutzer |
| `tester` | Tests schreiben (TDD), Test-Suite ausführen, Coverage sicherstellen |
| `ui-ux-designer` | UI-Spezifikation, Mockup-Erstellung und Design-System-Definition — implementiert nicht, spezifiziert. |
| `validator` | Interner Qualitäts-Checker: DoD-Checkliste, Traceability-Audit. Wird vom Orchestrator nach der Implementierung aufgerufen. Nicht für direkte User-Fragen oder Setup-Hilfe. |
<!-- agent-meta:managed-end -->

## Agents

Agent files are in `.gemini/agents/`. Agents must be registered at session start via the bootstrap instructions above. `@agent` text mentions are not intercepted by Gemini.

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

## Project Setup

- **Build:** `docker-compose build`
- **Test:** `pytest (Backend) + npm test (Frontend)`
- **Platform:** Django + React + Docker Compose
- **Runtime:** Python 3.x (Django) + Node.js (React)
