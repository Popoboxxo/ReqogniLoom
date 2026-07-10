# ReqFlow

> Projektbeschreibung für Claude-Agenten. Diese Datei ist die **einzige Quelle**
> für projektspezifischen Kontext — Agenten lesen sie, statt eigenen Kontext zu haben.
>
> Generiert von agent-meta v0.61.0 — `2026-06-17`
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

## Projekt

**Name:** ReqFlow
**Präfix:** rf
**Plattform:** Django + React + Docker Compose
**Beschreibung:** AI-natives Requirements-Management-Tool mit Testmanagement-Unterstützung

---

## Tech-Stack

- **Runtime:** Python 3.x (Django) + Node.js (React)
- **Sprache:** Python, TypeScript
- **Key-Dependencies:** Django, Django REST Framework, React, MCP SDK

---

## Architektur

```
backend/
  manage.py          # Django Entry-Point
  reqflow/           # Django Project
  requirements_app/  # Requirements Management App
frontend/
  src/               # React Source
  package.json
docker-compose.yml   # Orchestrierung
```

**Entry-Point:**
```
backend/manage.py — Django Management
frontend/src/index.tsx — React Entry-Point
```

**Besondere Patterns:**
- Django REST Framework für API-Endpoints
- MCP Server für AI-Tool-Integration
- Artefakt-basierte Zerlegung von Requirements

---

## Code-Konventionen

- PEP 8 für Python (Django Backend)
- TypeScript best practices für React Frontend
- Django-spezifisch: Models, Views, Serializers Trennung
- React-spezifisch: Functional Components, Hooks

---

## Build & Development

```bash
# Build
docker-compose build

# Tests
docker-compose exec backend pytest
docker-compose exec frontend npm test

# Dev-Stack starten
docker-compose up

# Nach Änderungen neu laden
docker-compose restart (oder Hot Reload je nach Service)
```

---

## Anforderungs-Kategorien

Kategorien für `docs/REQUIREMENTS.md`:

- **Functional**: Funktionale Anforderungen (Features, User Stories)
- **Non-Functional**: Nicht-funktionale Anforderungen (Performance, Sicherheit, Skalierbarkeit)
- **API**: REST API und MCP Server Schnittstellen
- **UI/UX**: Frontend und Benutzerinteraktion
- **Data**: Datenmodelle, Artefakte, Zerlegungsstrukturen
- **Integration**: Externe Systeme, Import/Export
- **Test**: Testmanagement-Anforderungen

---

## Agenten-Konfiguration

<!-- agent-meta:managed-begin -->
<!-- This block is automatically updated by sync.py on every sync. -->
<!-- Manual changes here will be overwritten. -->

Generiert von agent-meta v0.67.0 — `2026-07-10`
DoD-Preset: **spec-driven** | REQ-Traceability: true | Tests: true | Codebase-Overview: false | Security-Audit: false

> **Einstiegspunkt:** Starte mit dem `orchestrator`-Agenten für alle Entwicklungsaufgaben — Ausnahmen siehe Abschnitt »Orchestrator — Universal Router«.

| Agent | Zuständigkeit |
|-------|--------------|
| `agent-meta-manager` | agent-meta verwalten: Upgrade, Sync, Feedback, projektspezifische Agenten anlegen |
| `agent-meta-scout` | KI-Ökosystem scouten: neue Skills, Rollen, Rules und Patterns für agent-meta entdecken |
| `api-specialist` | Verwende diesen Agenten fuer API-Design, OpenAPI-Spezifikationen und Contract-First Development. |
| `bug-feature-analyzer` | Issue-Triage: Bug vs. User-Error vs. Feature vs. Out-of-Scope klassifizieren — vor developer/feature-Delegation |
| `code-reviewer` | Prüft Code-Qualität, Blast-Radius und Clean Code — nicht funktionale Korrektheit (das macht validator). |
| `concept-reviewer` | Konzept/Design-Doc reviewen: Vollständigkeit, Logik, Risiken, Approve/Iterate |
| `developer` | Feature-Implementierung und Bugfixes nach REQ-IDs |
| `devops-engineer` | Verwende diesen Agenten fuer CI/CD, IaC, Kubernetes, Monitoring und Infrastructure-Aufgaben. |
| `docker` | Dev-Stack starten/stoppen, Dockerfiles, Binary-Management |
| `documenter` | Doku pflegen: CODEBASE_OVERVIEW, ARCHITECTURE, README, Erkenntnisse |
| `effort-estimator` | Aufwandsschätzung für Tasks — delegiere hierher wenn User nach Zeit/Kosten fragt |
| `explorer` | Codebase analysieren / Dependencies / Impact — read-only, delegiert Findings |
| `export-manager` | Verwende diesen Agenten fuer Export-Routing von strukturierten Daten zu konfigurierten Targets. |
| `feature` | Feature-Lifecycle-Subagent: Branch → REQ → TDD → Dev → Validate → PR. Wird vom Orchestrator gestartet, nicht direkt vom User. |
| `feedback` | Projekt-Feedback: Bugs, Features, Verbesserungen als GitHub Issues standardisiert einreichen — immer vor git |
| `git` | Commits, Branches, Tags, Push/Pull und alle Git-Operationen |
| `ideation` | Neue Ideen explorieren, Vision schärfen, Übergabe an requirements |
| `junior-developer` | Low-Tier-Developer: triviale Fixes, Typos, kleine klar umrissene Änderungen — eskaliert bei Scope-Überschreitung |
| `log-analyzer` | Log-Analyse: Fehler clustern, Severity klassifizieren (RFC 5424), Findings als Issues oder Tasks delegieren |
| `meta-feedback` | Verbesserungsvorschläge für agent-meta als GitHub Issues einreichen |
| `orchestrator` | Einstiegspunkt für ALLE Entwicklungsaufgaben — zerlegt komplexe Tasks und dispatched parallel |
| `performance-optimizer` | Verwende diesen Agenten fuer Performance-Analyse, Big-O-Optimierung und Bottleneck-Beseitigung. |
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
| `tester` | Tests schreiben (TDD), Test-Suite ausführen, Coverage sicherstellen |
| `ui-ux-designer` | UI-Spezifikation, Mockup-Erstellung und Design-System-Definition — implementiert nicht, spezifiziert. |
| `validator` | Interner Qualitäts-Checker: DoD-Checkliste, Traceability-Audit. Wird vom Orchestrator nach der Implementierung aufgerufen. Nicht für direkte User-Fragen oder Setup-Hilfe. |
<!-- agent-meta:managed-end -->

---

## Sprachregeln

<!-- Die globale Rule .claude/rules/language.md (generiert von sync.py) deckt den Kern ab. -->
<!-- Hier nur projektspezifische Abweichungen eintragen — sonst leer lassen. -->

- `README.md` → **Englisch**
- Alle anderen Dokumente → **Deutsch**
- Code-Kommentare, Commit-Messages → **Englisch**
- Kommunikation mit dem Nutzer → **Deutsch**
