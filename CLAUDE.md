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

Generiert von agent-meta v0.75.0 — `2026-07-17`
DoD-Preset: **spec-driven** | REQ-Traceability: false | Tests: false | Codebase-Overview: false | Security-Audit: false

> **Einstiegspunkt:** Starte mit dem `orchestrator`-Agenten für alle Entwicklungsaufgaben — Ausnahmen siehe Abschnitt »Orchestrator — Universal Router«.
<!-- agent-meta:managed-end -->

---

## Sprachregeln

<!-- Die globale Rule .claude/rules/language.md (generiert von sync.py) deckt den Kern ab. -->
<!-- Hier nur projektspezifische Abweichungen eintragen — sonst leer lassen. -->

- `README.md` → **Englisch**
- Alle anderen Dokumente → **Deutsch**
- Code-Kommentare, Commit-Messages → **Englisch**
- Kommunikation mit dem Nutzer → **Deutsch**
