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

Generiert von agent-meta v0.61.1 — `2026-06-17`
DoD-Preset: **rapid-prototyping** | REQ-Traceability: false | Tests: false | Codebase-Overview: false | Security-Audit: false

> **Einstiegspunkt:** Starte mit dem `orchestrator`-Agenten für alle Entwicklungsaufgaben — Ausnahmen siehe Abschnitt »Orchestrator — Universal Router«.

| Agent | Zuständigkeit |
|-------|--------------|
| `agent-meta-manager` | agent-meta verwalten: Upgrade, Sync, Feedback, projektspezifische Agenten anlegen |
| `agent-meta-scout` | KI-Ökosystem scouten: neue Skills, Rollen, Rules und Patterns für agent-meta entdecken |
| `api-specialist` | Verwende diesen Agenten fuer API-Design, OpenAPI-Spezifikationen und Contract-First Development. |
| `code-reviewer` | Prüft Code-Qualität, Blast-Radius und Clean Code — nicht funktionale Korrektheit (das macht validator). |
| `developer` | Feature-Implementierung und Bugfixes nach REQ-IDs |
| `documenter` | Doku pflegen: CODEBASE_OVERVIEW, ARCHITECTURE, README, Erkenntnisse |
| `feature` | Feature-Lifecycle-Subagent: Branch → REQ → TDD → Dev → Validate → PR. Wird vom Orchestrator gestartet, nicht direkt vom User. |
| `git` | Commits, Branches, Tags, Push/Pull und alle Git-Operationen |
| `ideation` | Neue Ideen explorieren, Vision schärfen, Übergabe an requirements |
| `meta-feedback` | Verbesserungsvorschläge für agent-meta als GitHub Issues einreichen |
| `orchestrator` | Einstiegspunkt für ALLE Entwicklungsaufgaben — zerlegt komplexe Tasks und dispatched parallel |
| `release` | Versioning, Changelog, Build-Artifact, GitHub Release erstellen |
| `requirements` | Anforderungen aufnehmen, REQ-IDs vergeben, REQUIREMENTS.md pflegen |
| `se-architect` | Use this agent to design L1 and L2 architectures from requirements. |
| `se-critic` | Use this agent to validate requirements before architecture, and audit architectural decompositions. |
| `se-integration-and-test-manager` | Orchestriert den gesamten rechten Flügel der V&V-Kaskade — Bottom-Up, Top-Down, Integrationsplanung. |
| `se-interface-mgr` | Manages generic signal flow, deterministic sync across systems |
| `se-orchestrator` | Coordinates the 6-level recursive breakdown |
| `se-requirements` | Use this agent to clarify requirements and start the SE cascade. |
| `se-termination` | Deterministic termination at L3 (Component Requirement) |
| `se-validator` | Validiert das System auf L1-Ebene durch User-Journey-Simulation — ignoriert Code, prüft ob der User-Need erfüllt ist. |
| `se-verifier` | Use this agent to verify integrated systems against their specifications on all architecture levels (L1 through Ln). |
| `senior-developer` | High-Tier-Developer: Architektur-Impact, komplexe/riskante Änderungen, schwierige Bugs — analysiert erst, implementiert dann |
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
