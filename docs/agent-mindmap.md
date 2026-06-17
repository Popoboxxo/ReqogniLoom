# Agenten-Übersicht

> Automatisch generiert von agent-meta. Nicht manuell bearbeiten.

```mermaid
mindmap
  root((orchestrator))
    🔴 developer
      tester
      git
    🔵 feature
      requirements
      validator
      developer
      tester
      git
    🔴 git
    🔵 documenter
    ⚪ ideation
    ⚪ release
      git
      documenter
    ⚪ security-auditor
    ⚪ docker
    🔴 log-analyzer
      feedback
      developer
      security-auditor
    🔴 feedback
    ⚪ agent-meta-manager
      agent-meta-scout
      developer
      git
    ⚪ agent-meta-scout
    ⚪ meta-feedback
    🔵 requirements
    🔵 validator
    🔵 tester
```

## Legende

| Symbol | Bedeutung |
|--------|-----------|
| 🔴 | required — Kern-Workflow |
| 🔵 | recommended — Standard-Qualität |
| ⚪ | optional — Bei Bedarf |

## Agenten-Details

### agent-meta-manager
- **Tier:** optional
- **Beschreibung:** agent-meta verwalten: Upgrades, Sync, Feedback-Delegation, projektspezifische Agenten, External-Skill-Lifecycle und Erweiterungen anlegen.
- **Model:** Claude: claude-sonnet-4-6, Opencode: opencode-go/qwen3.7-plus
- **Delegiert an:** agent-meta-scout, developer, git

### agent-meta-scout
- **Tier:** optional
- **Beschreibung:** Scoutet das KI-Ökosystem auf neue Skills, Agenten-Patterns, Rules und Workflows. Bewertet Kandidaten und macht konkrete Erweiterungsvorschläge für agent-meta.
- **Model:** Claude: claude-sonnet-4-6, Opencode: opencode-go/qwen3.7-plus

### api-specialist
- **Tier:** optional
- **Beschreibung:** API-Design, OpenAPI-Spezifikationen, Contract-First Development. Erstellt und pflegt API-Vertraege.
- **Model:** Claude: claude-sonnet-4-6, Opencode: opencode-go/qwen3.7-plus

### bug-feature-analyzer
- **Tier:** recommended
- **Beschreibung:** Analysiert und klassifiziert eingehende Bug-Meldungen und Feature-Requests vor Ressourcen-Allokation. Unterscheidet: Echter Bug, User-Fehler, validierbares Feature, Out-of-Scope.
- **Model:** Claude: claude-sonnet-4-6, Opencode: opencode-go/qwen3.7-plus

### code-reviewer
- **Tier:** recommended
- **Beschreibung:** Gatekeeper für Code-Gesundheit: Clean Code, SOLID, Blast-Radius-Analysen und REQ-Traceability in Code-Pfaden.
- **Model:** Claude: claude-opus-4-7, Opencode: opencode-go/kimi-k2.6

### concept-reviewer
- **Tier:** optional
- **Beschreibung:** Generischer Konzept-Critic: reviewt Design-Docs und Konzepte auf Vollständigkeit, Logik-Lücken, Annahmen, Alternativen, Risiken, Machbarkeit und Konsistenz.
- **Model:** Claude: claude-opus-4-7, Opencode: opencode-go/kimi-k2.6

### developer
- **Tier:** required
- **Beschreibung:** Implementiert Features und Bugfixes mit strikten Code-Konventionen. REQ-ID- und TDD-Pflicht konfigurativ über DoD.
- **Model:** Claude: claude-opus-4-7, Opencode: opencode-go/kimi-k2.6
- **Delegiert an:** tester, git

### devops-engineer
- **Tier:** optional
- **Beschreibung:** CI/CD-Pipelines, Infrastructure as Code, Container-Orchestrierung, Observability und Security-Best-Practices.
- **Model:** Claude: claude-haiku-4-5-20251001, Opencode: opencode-go/deepseek-v4-flash

### docker
- **Tier:** optional
- **Beschreibung:** Docker-Operationen: Compose-Stacks, Binary-Management, Test-Umgebungen und Diagnose — plattformunabhängig.
- **Model:** Claude: claude-haiku-4-5-20251001, Opencode: opencode-go/deepseek-v4-flash

### documenter
- **Tier:** recommended
- **Beschreibung:** Pflegt CODEBASE_OVERVIEW.md, ARCHITECTURE.md, README.md und Session-Erkenntnisse.
- **Model:** Claude: claude-haiku-4-5-20251001, Opencode: opencode-go/deepseek-v4-flash

### effort-estimator
- **Tier:** optional
- **Beschreibung:** Schätzt Aufwände für Entwicklungsaufgaben basierend auf Task-Typ und LLM-Fähigkeiten
- **Model:** Claude: claude-haiku-4-5-20251001, Opencode: opencode-go/deepseek-v4-flash

### explorer
- **Tier:** optional
- **Beschreibung:** Read-only Codebase-Recherche, Dependency- und Impact-Mapping, Datei- und Symbol-Suche.
- **Model:** Claude: claude-sonnet-4-6, Opencode: opencode-go/qwen3.7-plus

### export-manager
- **Tier:** optional
- **Beschreibung:** Liest .meta-config/export.yaml und routet strukturierte JSON-Payloads der Fach-Agenten zum konfigurierten Target (markdown, confluence, jira-xray, etc.).
- **Model:** Claude: claude-haiku-4-5-20251001, Opencode: opencode-go/deepseek-v4-flash

### feature
- **Tier:** recommended
- **Beschreibung:** Vollständiger Feature-Lifecycle: Branch → Requirements → TDD → Implementierung → Validierung → Commit → PR.
- **Model:** inherited
- **Delegiert an:** requirements, validator, developer, tester, git

### feedback
- **Tier:** required
- **Beschreibung:** Standardisiert Bug-Reports, Feature-Requests und Verbesserungsvorschläge für das eingesetzte Projekt — kategorisiert, aufbereitet und direkt als GitHub Issue eingereicht.
- **Model:** Claude: claude-haiku-4-5-20251001, Opencode: opencode-go/deepseek-v4-flash

### git
- **Tier:** required
- **Beschreibung:** Git-Operationen: Commits, Branches, Merges, Tags, Push/Pull und Commit-Messages — plattformunabhängig (GitHub, GitLab, Gitea).
- **Model:** Claude: claude-haiku-4-5-20251001, Opencode: opencode-go/deepseek-v4-flash

### ideation
- **Tier:** optional
- **Beschreibung:** Ideenfindung, Visions-Schärfung und Konzept-Konkretisierung — stellt Fragen, denkt Ecken, übergibt reife Ideen an Requirements.
- **Model:** inherited

### junior-developer
- **Tier:** optional
- **Beschreibung:** Schnelle, klar umrissene Code-Änderungen: 1-2 Dateien, kein Architektur-Impact. Eskaliert strukturiert sobald der Scope wächst.
- **Model:** Claude: claude-haiku-4-5-20251001, Opencode: opencode-go/deepseek-v4-flash

### log-analyzer
- **Tier:** required
- **Beschreibung:** Analysiert System- und Applikations-Logs: Frequency-Clustering, Severity-Klassifikation (RFC 5424), Root-Cause-Hypothesen und strukturierte Findings mit Delegations-Routing.
- **Model:** Claude: claude-sonnet-4-6, Opencode: opencode-go/qwen3.7-plus
- **Delegiert an:** feedback, developer, security-auditor

### meta-feedback
- **Tier:** optional
- **Beschreibung:** Verbesserungsvorschläge für agent-meta sammeln und als GitHub Issues einreichen.
- **Model:** Claude: claude-haiku-4-5-20251001, Opencode: opencode-go/deepseek-v4-flash

### openscad-developer
- **Tier:** optional
- **Beschreibung:** Spezialisierter Developer für parametrische 3D-Modelle in OpenSCAD. Render-Inspect-Refine Loop via MCP, Druckbarkeits-Wissen, Toleranz-Management.
- **Model:** Claude: claude-sonnet-4-6, Opencode: opencode-go/qwen3.7-plus

### orchestrator
- **Tier:** required
- **Beschreibung:** Provider-agnostischer Task-Orchestrator: zerlegt, parallelisiert, delegiert.
- **Model:** Claude: claude-sonnet-4-6, Opencode: opencode-go/qwen3.7-plus
- **Delegiert an:** developer, feature, git, documenter, ideation, release, security-auditor, docker, log-analyzer, feedback, agent-meta-manager, agent-meta-scout, meta-feedback, requirements, validator, tester

### performance-optimizer
- **Tier:** optional
- **Beschreibung:** Datengetriebene Identifikation und Aufloesung von Big-O Bottlenecks durch Profiling-Daten, ohne funktionale Aenderungen.
- **Model:** Claude: claude-opus-4-7, Opencode: opencode-go/kimi-k2.6

### provider-expert
- **Tier:** optional
- **Beschreibung:** Absoluter Analyse-Experte für einen AI-Provider: Funktionsweise, Konfiguration, Best Practices (Formatter, Hooks, MCPs) zur optimalen Anpassung von agent-meta.
- **Model:** inherited

### release
- **Tier:** optional
- **Beschreibung:** Versioning, Changelogs, Build-Prozesse und GitHub-Releases verwalten.
- **Model:** Claude: claude-sonnet-4-6, Opencode: opencode-go/qwen3.7-plus
- **Delegiert an:** git, documenter

### requirements
- **Tier:** recommended
- **Beschreibung:** Anforderungen aufnehmen, REQ-IDs vergeben, REQUIREMENTS.md pflegen und Traceability prüfen.
- **Model:** Claude: claude-sonnet-4-6, Opencode: opencode-go/qwen3.7-plus

### se-architect
- **Tier:** optional
- **Beschreibung:** Designs system architecture using generic laws, CQRS routing, and defines L1/L2 whiteboxes.
- **Model:** Claude: claude-opus-4-7, Opencode: opencode-go/kimi-k2.6

### se-critic
- **Tier:** optional
- **Beschreibung:** Audits requirements and architecture against generic laws (orthogonality, testability, traceability).
- **Model:** Claude: claude-opus-4-7, Opencode: opencode-go/kimi-k2.6

### se-integration-and-test-manager
- **Tier:** optional
- **Beschreibung:** V&V-Orchestrator: Koordiniert Integrationsstrategie, Test-Ebenen und Traceability-Feedback über L1-Ln.
- **Model:** Claude: claude-sonnet-4-6, Opencode: opencode-go/qwen3.7-plus

### se-interface-mgr
- **Tier:** optional
- **Beschreibung:** Manages generic signal flow and deterministic synchronization across systems.
- **Model:** Claude: claude-sonnet-4-6, Opencode: opencode-go/qwen3.7-plus

### se-orchestrator
- **Tier:** optional
- **Beschreibung:** DEPRECATED — SE functionality is now handled directly by the orchestrator via SE-Mode ({{#if SE_ENABLED}}). This agent is retained for backward compatibility only.
- **Model:** Claude: claude-sonnet-4-6, Opencode: opencode-go/qwen3.7-plus

### se-requirements
- **Tier:** optional
- **Beschreibung:** Elicits stakeholder needs and uses a multi-level template for requirements engineering.
- **Model:** Claude: claude-sonnet-4-6, Opencode: opencode-go/qwen3.7-plus

### se-termination
- **Tier:** optional
- **Beschreibung:** Deterministic per-system leaf/continue decision with dynamic depth control.
- **Model:** Claude: claude-haiku-4-5-20251001, Opencode: opencode-go/deepseek-v4-flash

### se-test-engineer
- **Tier:** optional
- **Beschreibung:** Develops MBSE test models and designs integration tests (interaction of multiple SW units). Right wing of the V-model.
- **Model:** Claude: claude-sonnet-4-6, Opencode: opencode-go/qwen3.7-plus

### se-testreviewer
- **Tier:** optional
- **Beschreibung:** Audits the test strategy. Checks for edge cases, boundary value analysis, equivalence class errors, and flakiness.
- **Model:** Claude: claude-opus-4-7, Opencode: opencode-go/kimi-k2.6

### se-validator
- **Tier:** optional
- **Beschreibung:** L1 System-Validierung: End-to-End User Journeys gegen Stakeholder-Bedürfnisse abgleichen. 'Did we build the right system?'
- **Model:** Claude: claude-opus-4-7, Opencode: opencode-go/kimi-k2.6

### se-verifier
- **Tier:** optional
- **Beschreibung:** Multi-Level Verification L1-Ln. Validates that fully integrated systems/sub-systems exactly fulfill architectural specifications and interfaces.
- **Model:** Claude: claude-sonnet-4-6, Opencode: opencode-go/qwen3.7-plus

### security-auditor
- **Tier:** optional
- **Beschreibung:** Static security analysis: OWASP Top 10, secrets detection, dependency risks, supply-chain threats, and cryptographic weaknesses — read-only, no code execution.
- **Model:** Claude: claude-opus-4-7, Opencode: opencode-go/kimi-k2.6

### senior-developer
- **Tier:** optional
- **Beschreibung:** Komplexe Features, Architektur-Entscheidungen, schwierige Bugs und Cross-Cutting-Refactorings. Analysiert vor der Implementierung und dokumentiert Entscheidungen.
- **Model:** Claude: claude-fable-5, Opencode: opencode-go/kimi-k2.7-code

### tester
- **Tier:** recommended
- **Beschreibung:** Isolierte Unit-Tests mit Mocks/Stubs nach TDD-Workflow. Für Integrationstests → se-test-engineer.
- **Model:** Claude: claude-sonnet-4-6, Opencode: opencode-go/qwen3.7-plus

### ui-ux-designer
- **Tier:** optional
- **Beschreibung:** Erstellt UI-Spezifikationen, Mockups und Design-Systeme. Ordnet UI-Elemente REQ-IDs zu.
- **Model:** Claude: claude-sonnet-4-6, Opencode: opencode-go/qwen3.7-plus

### validator
- **Tier:** recommended
- **Beschreibung:** Formaler Prozess-Wächter: DoD-Checkboxen, REQ-ID-Präsenz, Commit-Konventionen. Bewertet KEINE Code-Qualität — dafür code-reviewer.
- **Model:** Claude: claude-sonnet-4-6, Opencode: opencode-go/qwen3.7-plus
