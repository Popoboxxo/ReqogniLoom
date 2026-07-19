# ReqFlow — Product Strategy & Project Knowledge

> **Status:** Konsolidiert (Zusammenführung aus VISION.md, STRATEGY.md und PROJECT_KNOWLEDGE.md)
> **Letzte Aktualisierung:** 2026-07-09

Dieses Dokument ist die "Single Source of Truth" für die strategische Ausrichtung, Zielgruppen, Kernarchitektur und operative Invarianten von ReqFlow.

---

## 1. Executive Summary & Vision

**ReqFlow** ist ein AI-natives Requirements-Management- und Systems-Engineering-Tool. Es verbindet die Leichtigkeit moderner Agile-Tools mit der Strenge regulierter Systems-Engineering-Prozesse (Traceability, Baselines, Audit-Trails).

Das zentrale Alleinstellungsmerkmal (USP) ist die **AI-Nativität**: ReqFlow behandelt AI-Agenten nicht als nachträgliche Chatbot-Integration, sondern als First-Class-Clients. Das System ist primär darauf ausgelegt, von Agenten gelesen und beschrieben zu werden (via Model Context Protocol - MCP).

---

## 2. Zielgruppen

ReqFlow bedient primär zwei gleichwertige Zielgruppen, die durch **Configurable Rigor** auf derselben Plattform vereint werden.

| Gruppe | Beschreibung | Bedarf |
|--------|-------------|--------|
| **AI-first Software Teams** | Teams mit AI-Agenten (Claude Code, Cursor) im Entwicklungsprozess. | Strukturierter, maschinenlesbarer Anforderungskontext; Agile-Terminologie. |
| **Systems Engineers (Mid-Market)** | Engineers in regulierten Domänen (Medizintechnik-Startups, Automotive-Zulieferer 2. Reihe). | Formale Artefakt-Hierarchien, Baselines, Approval-Workflows. |
| **SE + AI-Bridge** | Engineers, die SE-Methodik mit modernen AI-Werkzeugen kombinieren wollen. | Hybrid-Prozesse. |

### Out-of-Scope (v1)
- Teams ohne jegliche Requirements-Disziplin (Issue-Tracking-only) → Jira/Linear
- Hochregulierte Programme mit Zertifizierungspflicht (DO-178C Level A, ISO 26262 ASIL-D) → Mögliches v2-Ziel
- Primäres Dokument-Management → Confluence/SharePoint

---

## 3. Strategische Kernkonzepte

### 3.1 AI-Nativität (Zwei Dimensionen)

"AI-nativ" beschreibt zwei konkrete architektonische Dimensionen:

1. **LLM als pluggable Capability:** LLMs werden als konfigurierbare Capability für Generierung (Testfall-Ableitung), Validierung (Qualitätsprüfung), Decomposition (Zerlegungsvorschläge) und Konsistenz-Checks eingesetzt. Provider (Anthropic, OpenAI, Ollama) sind austauschbar.
2. **MCP Server als primäre Schnittstelle:** Der MCP Server bietet vollwertigen Zugriff (Lesen/Schreiben) auf alle drei Artefakttypen (Requirements, Architektur, Tests). Er ist gleichrangig neben der REST-API positioniert.

### 3.2 Configurable Rigor

Die Strenge des Prozesses (SE-Tiefe, Audit-Anforderungen, Workflows) ist pro Workspace über Presets konfigurierbar. Das Datenmodell im Backend ist immer vollständig, jedoch ändert sich die Sichtbarkeit und Erzwingung (Validation) von Feldern.

- **Minimal:** Leicht, wenig Pflichtfelder, kein Approval-Workflow.
- **Standard:** Erweiterte Pflichtfelder, Document/Project-Baselines.
- **Extended:** Vollständiger Audit, alle Baseline-Scopes, strikter Approval-Workflow mit Begründungspflicht.

---

## 4. Architektur & Tech-Stack

### 4.1 Tech-Stack

| Layer | Stack |
|-------|-------|
| **Backend** | Python 3.x, Django 4.2+, Django REST Framework, MCP SDK |
| **Frontend** | React 18+, TypeScript, Hooks, Vitest, react-i18next (DE/EN) |
| **Persistenz** | PostgreSQL via Django ORM, Row-Level Tenant-Isolation |
| **Deployment** | Docker Compose (Backend, Frontend, PostgreSQL) |
| **API** | REST (`/api/v1/`) + MCP Server (20 Tools, 4 Gruppen) |
| **Auth** | Bearer Token / API Keys, DRF-Permission-Classes |

### 4.2 Strategische Architektur-Entscheidungen (ADRs)

- **ADR-01:** MCP Server greift direkt auf den ApplicationService zu (kein HTTP-Overhead).
- **ADR-02:** LLM-Provider über schmale Adapter-Schicht abstrahiert (`LlmCapabilityInterface`).
- **ADR-03:** Tenant-Isolation via Row-Level Security und Custom Django Manager.
- **ADR-04:** Configurable Rigor als Single Source of Truth (`PresetConfigEngine`).
- **ADR-05:** Generisches Artefakt-Datenmodell und Terminologie-Profile statt redundanter Datenschemata.
- **ADR-06:** Item-Lifecycle als konfigurierbare WorkflowEngine.
- **ADR-07:** Baselines auf drei Scopes (Dokument / Projekt / Global) in einer Entität (`scope`-Enum).
- **ADR-08:** Self-Hosted via Docker Compose (Kein Kubernetes in v1).
- **ADR-09:** Volltextsuche nativ über PostgreSQL (Keine separate Vector/Search-DB in v1).
- **ADR-10:** AuditLog auf Operation-Level in v1 (Feld-Diffs folgen in v2).

---

## 5. Operative Invarianten & Konventionen

### 5.1 MCP & API
- **MCP-Methoden:** Tool-Aufrufe nutzen direkt `method: "tool.name"` (dot-notation, z.B. `requirement.query`).
- **Authentication:** Token via JWT oder API-Key.
- **Tenancy:** In jeder View muss der Tenant explizit via `set_tenant(request.user.tenant)` gesetzt werden.

### 5.2 Lokales Setup (automatischer Admin-Bootstrap)
Nach der Initialmigration (`migrate`) läuft der `bootstrap_admin` Management-Command automatisch (via dedizierter `bootstrap`-Service in docker-compose.yml) und erstellt einen Admin-User basierend auf SYSTEM_ADMIN_*-Umgebungsvariablen (oder mit Defaults: admin/admin@demo.local).

Der Command `python manage.py seed_demo` ist **optional** und erstellt nur Demo-Artefakte; für den ersten Login ist er nicht erforderlich. Die Admin-User-Initialisierung ist idempotent und verändert das Passwort nie nachträglich.

### 5.3 Commit & Branching
- Format: `<type>(REQ-ID): <beschreibung>` (z.B. `feat(REQ-L1-010): ...`)
- Branching: Feature-Branches (`feat/*`, `fix/*`). Niemals direkte Commits auf `main` ohne User-Freigabe.

---

## 6. Aktueller Status & Handoff

Die vollständige SE-Kaskade (L0 → L1 → L2) ist für alle 16 L2-Systeme sowie das React-Frontend abgeschlossen. 
Die Integrationstests (inklusive ehemals offener Aufgaben wie Celery-Verdrahtung und Audit-Index-Optimierung) sind vollständig implementiert und bestehen aus über 1100 grünen Testfällen.

**Agenten-Dispatcher für neue Features:**
- **Trivial** (1 Komp., 0 Interfaces) → `se-junior-developer`
- **Standard** (Ein Modul, 2-4 Interfaces) → `se-developer`
- **Komplex** (Cross-Cutting, Foundation, ≥5 Interfaces) → `se-senior-developer`

*(Siehe `docs/CODEBASE_OVERVIEW.md` für den detaillierten operativen IST-Stand der Codebase und aktuelle Test-Metriken).*
