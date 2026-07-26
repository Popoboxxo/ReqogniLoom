# ReqFlow

ReqFlow ist ein AI-natives Requirements- und Test-Management-Tool mit MBSE-Unterstützung. Tech-Stack: Django 4.2+ (Backend) + React 18 + TypeScript (Frontend) + PostgreSQL 16 + Redis 7 + Celery 5.3+ + Docker Compose. Schnittstellen: REST API unter /api/v1/ (DRF, 16 ViewSets + 2 APIViews, JWT-Auth, OpenAPI via drf-spectacular) und nativer MCP Server unter /mcp/ (JSON-RPC 2.0, Transports: HTTP, SSE, stdio; 11 Tool-Gruppen mit 40+ Tools; API-Key `rfk_*`). Fähigkeiten: Requirements Management, Architecture Elements (MBSE-kompatibel), Test-Management, 8 Trace-Link-Typen, Baselines (3 Scopes) mit Diff-Engine, Artifact-Diff (feld-level), History-Endpoint, PDF-Report-Export, Test-Run-Protokollierung, CSV-Bulk-Import, API-Key-Management, Visual Artifact Diff, 3 Rigor-Presets (Minimal/Standard/Extended), Terminology-Profile (dev_mode/se_mode), Audit-Log, Multi-Tenancy via Row-Level-Security. LLM-Adapter: Anthropic, OpenAI, Ollama, mock (Default: mock).

<!-- agent-meta:managed-begin -->
> **ROUTING:**


 Gemini->AGENTS.md
> **ENTRY:** `orchestrator`-Agent (für alle Dev-Tasks).
`agent-meta v0.85.2` | DoD: `spec-driven` | REQ-Trace: `false`

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
> Nutze `knowledge-engine`, um komplexe Analysen und Context-Queries durchzuführen.


## Regeln

# A2A Anti-Re-Delegation Gates

1. Limit depth to 10, no self-handoff.
2. Short payload: `payload.t` max 300 Zeichen.
3. No Re-Delegation (payload starts with "Du bist...").
4. Singleton Orchestrator: NUR der `main_chat` darf den `orchestrator` spawnen.
5. Execution-Trace-Isolation: Worker-Output muss strukturiert sein (STATUS, RESULT, ARTIFACTS). Keine rohen Logs propagieren.



# Branch-Guard

Verwende Feature-Branches (`feat/`, `fix/`, `chore/`). Keine Code-Änderungen direkt auf `main` oder `master`.



# Commit-Konventionen

Verwende Conventional Commits (feat, fix, chore).
Beschreibungssprache: `Englisch`
Max 72 Zeichen in erster Zeile. Imperativ.

Format: `<type>: <beschreibung>` (Bsp: `feat: ...`)




# Definition of Done (DoD)

Pflicht: Code komplett, Konventionen & Conv. Commits eingehalten, keine Regressions.







# GitHub Issue Lifecycle

Issues referenzieren und am Ende mit passendem Keyword (`Fixes #123`, `Closes #123`) im PR oder Commit schließen. Kommentiere das Issue nach Fertigstellung.



# Sprachregeln

| Kontext | Sprache |
|---|---|
| User-Kommunikation | **Deutsch** |
| User-Input | **Deutsch** |
| Externe Doku | **Englisch** |
| Interne Doku | **Deutsch** |
| Code/Commits | **Englisch** |



# Lifecycle-Tasks

Beim Start prüfen: existiert `.gemini/pending-tasks.md`?
Falls ja und enthält `- [ ]`: User fragen ob delegiert werden soll.
Nach Erledigung: löschen. Datei nicht committen.



# Provider-Agnostic Policy

Generische Templates in `1-generic/` müssen provider-agnostisch sein. Keine spezifischen Prompts für Claude, Gemini etc., außer als Fallback/Feature-Flag.



# Python Conventions

PEP8 einhalten. Type Hints (typing) verwenden. Docstrings für Klassen/Methoden schreiben.



# Session-Abschluss

Delegate Session-Zusammenfassung an `documenter` am Ende großer Features, um CODEBASE_OVERVIEW.md aktuell zu halten.




# CRITICAL GATE
MAIN CHAT darf nicht selbst editieren. ALLES -> `orchestrator`. Keine Ausnahmen.




## Git Delegation
Git Mutationen (commit, push, add etc) -> `git` Agent. Read-only (status, log) im Main Chat ok.



Native Extensions (Skills/Hooks) erlaubt, ignorieren nicht Branch-Guard/DoD.





Anti-Recursion: Worker dürfen nicht an `orchestrator` zurück delegieren.






<!-- agent-meta:managed-end -->











> **Hinweis:** Pfade im managed Block (z.B. `.claude/`) beschreiben die agent-meta-Framework-Architektur. Dieses Projekt verwendet `.opencode/` als Laufzeit-Plattform.

## Agents

Agent files are in `.opencode/agents/`. Invoke them by name in opencode.

## Project Setup

- **Build:** `docker-compose build`
- **Test:** `pytest` (Backend) + `npm test` (Frontend)
- **Platform:** Django + React + Docker Compose
- **Runtime:** Python 3.x (Django) + Node.js (React)


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
