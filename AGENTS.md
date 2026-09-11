# ReqogniLoom

## Projekt

**Name:** ReqogniLoom
**Präfix:** ReqLo
**Plattform:** Django 5.2+ (Backend) + React 18 + TypeScript 5.5+ (Frontend) + PostgreSQL 16 (Django ORM) + Redis 7 (Cache/Celery-Broker) + Celery 5.3+ (Async) + Docker Compose (8 Services: postgres, postgres-backup, redis, backend, migrate, celery, celery-beat, frontend)
**Beschreibung:** AI-natives Requirements- und Test-Management-Tool mit MBSE-kompatibler Artefakt-Zerlegung, REST API + nativem MCP Server (31 Tool-Gruppen-Präfixe, 188 Tools), LLM-Adapter (Anthropic/OpenAI/Ollama/mock), Multi-Tenancy mit Row-Level-Isolation, 8 core/built-in Trace-Link-Typen (tenant-extensible catalog), Baselines (3 Scopes), 3 Rigor-Presets (minimal/standard/extended) und i18n (DE/EN).

> Struktur: siehe Verzeichnisstruktur im Repo (`ls`/`find`); deklarativ: `.meta-config/project.yaml` → `variables.PROJECT_STRUCTURE`.

**Verzeichnisstruktur:**
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

> Runtime & Abhängigkeiten: siehe Projekt-Manifest (`pyproject.toml` / `requirements.txt` / `package.json` / `manifest.json`).

**Entry-Point:** `backend/manage.py            — Django Management (migrate, seed_demo, runserver, shell, check) backend/reqogniloom/settings.py     — Settings-Entry (DRF, JWT, Celery, Apps) backend/reqogniloom/urls.py         — URL-Routing (/api/v1/, /mcp/, /api/schema/, /admin/) frontend/src/index.tsx          — React Entry-Point (ReactDOM.render) frontend/src/App.tsx            — Root-Component (Provider, Router) frontend/src/api/client.ts      — Axios-Client (auto-Bearer-Token-Injection) e2e/playwright.config.ts        — Playwright-Konfiguration (Chromium) `

**Besondere Patterns:**
- Django REST Framework (DRF) für REST-API-Endpoints (27 ViewSets + 67 APIViews) - MCP-Server (JSON-RPC 2.0) mit 31 Tool-Gruppen-Präfixen und 188 Tools für AI-Integration - drf-spectacular für OpenAPI 3.0 Schema-Generierung (Swagger-UI, ReDoc) - Single-Entry-Point Pattern (ADR-01): Layer 2 application/ ist die einzige Domain-Fassade - TenantContext als Thread-Local Singleton + Row-Level-Security (ADR-03) - Configurable Rigor (ADR-04): 3 Presets (minimal/standard/extended) mit gleichem Datenmodell - LLM-Provider-Abstraktion (ADR-02): Capability-Interface mit graceful degradation - 8 core/built-in Trace-Link-Typen (derives-from, decomposes, allocated-to, verifies, mitigates, decides, references, diagram-ref; tenant-extensible catalog, siehe backend/link_types/builtin.py) - 3 Baseline-Scopes (Document, Project, Global) in einer Entität (ADR-07) - Konfigurierbare State-Machines pro Workspace (ADR-06) - Resilience-Decorators (Retry, Circuit-Breaker, Timeout) auf Service-Ebene - V-Modell-Traceability L0-L4 (Stakeholder Needs → System Req → Subsystems → Components → Presentation) 

## Code-Konventionen

- Python (PEP 8, Typings, Docstrings für public API) - TypeScript (ESLint 9, Prettier, strict mode, functional Components + Hooks) - Django-Layer: Models (persistence/) ↔ Services (application/) ↔ Views/Serializers (rest_api/) - React-Layer: api/ (Wrapper) ↔ context/ (State) ↔ components/ (UI) ↔ i18n/ (Labels) - Imports-Reihenfolge: Standard Library → Third-Party → Local (PEP 8) - Keine wildcard imports (from x import *) - Keine direkten Model-Queries in DRF-Views (immer via Serializer + Service) - data-testid auf allen interaktiven UI-Elementen (E2E-Pflicht für Playwright) - CSS Custom Properties aus styles/tokens.css (keine hardcodierten Farben/Größen) - Commits: Conventional Commits Format (feat(REQ-xxx): ..., fix: ..., chore: ...) - Branch-Policy: feat/*, fix/*, refactor/* (NIE direkt auf main) - Requirements-IDs: REQ-L0-*, REQ-L1-*, REQ-L2-*, REQ-L3-* (siehe docs/se/traceability-matrix.md) 

## Build & Development

```bash
# Build
make build

# Tests
pytest (Backend) + npm test (Frontend)

# Dev-Stack starten
make up

# Nach Änderungen neu laden
make up (recreated Container bei geänderter Config/Env; reines `docker compose restart` liest .env NICHT neu) oder Hot-Reload automatisch je nach Service
```

## Anforderungs-Kategorien

Kategorien für `docs/REQUIREMENTS.md`:

- **Functional** — Features, User Stories, CRUD auf Requirements/Architecture/TestCases/ADRs/Risks/Issues
- **Non-Functional** — Performance, Sicherheit, Skalierbarkeit, Audit-Compliance, Multi-Tenancy
- **API** — REST API (/api/v1/, JWT-Auth, OpenAPI) und MCP Server (/mcp/, JSON-RPC 2.0, 31 Tool-Gruppen-Präfixe)
- **UI/UX** — Frontend (React 18 SPA), 41 Component-Bereiche, i18n (DE/EN), Barrierefreiheit
- **Data** — Generic Artifact Model, Multi-Tenancy via Row-Level-Security, Configurable Rigor
- **Integration** — Externe Systeme, CSV-Bulk-Import, PDF-Report-Export, LLM-Provider (Anthropic/OpenAI/Ollama/mock)
- **Test** — Test-Management, Test-Run-Protokollierung (4-Phasen-Lifecycle), Coverage-Tracking
- **Workflow** — Konfigurierbare State-Machines pro Workspace, Approval-Gates, Transition-Validierung
- **Baseline** — Snapshot, Feld-Level-Diff, 3 Scopes (Document/Project/Global)
- **Traceability** — 8 core/built-in Link-Typen (tenant-extensible), Coverage-Aggregation, V-Modell L0-L4-Traceability
- **AI** — LLM-Provider-Abstraktion, Decomposition, Validation, Consistency-Check
- **Resilience** — Retry, Circuit-Breaker, Timeout-Decorators, async via Celery



<!-- agent-meta:managed-begin -->
> **ROUTING:**

 Opencode->AGENTS.md |
 Gemini->AGENTS.md
> **ENTRY:** `orchestrator`-Agent (für alle Dev-Tasks).
`agent-meta v1.1.0` | DoD: `rapid-prototyping` | REQ-Trace: `false`



## Regeln

# Branch-Guard

Verwende Feature-Branches (`feat/`, `fix/`, `chore/`). Keine Code-Änderungen direkt auf `main` oder `master`.

## Guard-Terminologie: Convention Boundary vs. Security Boundary

Guards im System (Orchestrator-Guard, DoD-Push-Check, etc.) werden inkonsistent als
"Konventions-Tool" und als "security boundary" bezeichnet — beide Aussagen sind korrekt,
aber gegen unterschiedliche Bedrohungsmodelle:

- **Convention boundary**: fail-closed gegen AKZIDENTIELLEN Missbrauch (Tippfehler,
  vergessene Bestätigungen, naive Automatisierung). Nicht darauf ausgelegt, einen
  gezielten Bypass-Versuch zu widerstehen (siehe Lücken unten, z.B. #592).
- **Security boundary**: fail-closed gegen einen DELIBERATEN Umgehungsversuch.

Diese Definition ist die zentrale Referenz — Hook-Header und andere Doku sollen sie
verlinken (`.claude/rules/branch-guard.md#guard-terminologie-convention-boundary-vs-security-boundary`)
statt sie ad hoc zu wiederholen.

`orchestrator-guard.sh` ist primär eine **convention boundary** (siehe Lücken unten),
mit einzelnen **security-boundary**-Eigenschaften für spezifische Fälle (z.B. das
Destructive-Gate aus #516, das auch bei gültigem `git`-Sentinel blockt). `dod-push-check.sh`
ist als **security boundary** gegen fehlendes/kaputtes `python3` fail-closed (#595).

## Bekannte Grenzen

Die technische Durchsetzung (`orchestrator-guard.sh`) erkennt Git-Mutationen über eine tokenisierte Analyse des Bash-Befehls (gemeinsamer Tokenizer für Destructive- und Mutation-Gate, Issue #551), kein vollständiger Shell-Parser. Bekannte Lücken:

1. `eval "git commit ..."` wird nicht erkannt.
2. Direkte Schreibzugriffe auf `.git/` werden nicht geprüft.
3. Andere Git-Tools (`hub`, `gh repo ...`) sind nicht erfasst.
4. Command-Substitution und Indirektion (`$(...)`, Backticks, `xargs`, `eval`) können eine Git-Mutation am Tokenizer vorbeischleusen, weil der Hook den Befehl weder ausführt noch die Shell vollständig parst (Issue #592). Ein echter Shell-Interpreter wäre unverhältnismäßig für ein Konventions-Tool.

Bewusster Trade-off, kein Bug (siehe Kommentar-Header in `.claude/hooks/orchestrator-guard.sh`) — nur relevant für Nutzer, die sich vollständig auf den Schutz statt auf die Konvention verlassen.



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



# MCP Hard Prohibitions

> Kurzfassung der harten Tool-Verbote aktiver MCP-Server. Vollständige Tool-Listen und
> Hinweise: pro Provider in `.gemini/skills bzw. .opencode/skills bzw. .agents/skills bzw. .zcode/skills bzw. .kimi-code/skills` — jeweils `mcp-<server>/SKILL.md` (`use-lazy-rules.md`).

- (keine aktiven MCP-Server mit gesperrten Tools)



# SE-Kaskade: ADR-Standard

Verbindlicher MADR-Minimal-Standard für Architecture Decision Records in der
SE-Kaskade (Issue #339 B1). Normativ nur bei aktiver SE-Kaskade.

## Verzeichnis- und Namenskonvention

- Ablageort: `SE/ADR/ADR-NNN_kurztitel.md`
- `NNN` = 3-stellig, monoton steigend (ADR-001, ADR-002, …), niemals wiederverwendet.
- `kurztitel` = lowercase snake_case, ASCII, ohne Versions- oder Datumssuffix
  (Versionierung via Git, siehe Artefakt-Taxonomie).

## Frontmatter-Pflichtfelder

| Feld | Typ | Werte |
|------|-----|-------|
| `adr_id` | string | `ADR-NNN` |
| `title` | string | Kurztitel |
| `status` | enum | `proposed \| review \| accepted \| deprecated \| superseded` |
| `date` | date | ISO-8601 (`YYYY-MM-DD`) |
| `deciders` | array | Agenten-/Rollen-Namen, die entschieden haben |
| `affected_reqs` | array | REQ-IDs, die diese Entscheidung betreffen (mind. 1) |
| `superseded_by` | string | `ADR-NNN` — nur wenn `status: superseded` |

Schema: `schemas/se-adr.schema.json`.

## Body-Struktur (MADR-Minimal)

- `## Kontext` — Problem, Constraints, Treiber
- `## Alternativen` — **mindestens 2** Optionen mit Abwägung, inkl. rejected
- `## Entscheidung` — die gewählte Lösung, präzise und prüfbar
- `## Konsequenzen` — positive UND negative Folgen

## Lifecycle

```
proposed → review → accepted
                  → deprecated
                  → superseded (Referenz auf Nachfolge-ADR via superseded_by)
```

- `proposed` löst automatisch den Review-Trigger aus (`se-critic` prüft gegen
  Architekturgesetze und betroffene REQs).
- Nur `se-architect` ändert den Status; Statuswechsel werden in der ADR-Datei
  dokumentiert (Datum + Grund).
- Ein `superseded`-ADR bleibt erhalten (Audit-Trail) und verweist via
  `superseded_by` auf den Nachfolger.

## REQ ↔ ADR-Verlinkung

- Jedes ADR referenziert **mindestens eine** REQ-ID in `affected_reqs`.
- Jede REQ listet die sie betreffenden, noch nicht `accepted` ADRs im
  Frontmatter-Feld `open_adrs: []`.
- Beim Statuswechsel auf `accepted` (oder `deprecated`/`superseded`) entfernt
  `se-architect` die ADR-ID aus `open_adrs` aller `affected_reqs`; die
  Rückverfolgbarkeit bleibt über `affected_reqs` im ADR erhalten.
- Architektur-relevante REQs (`arch_impact: true`) ohne ADR-Bezug sind ein
  Kaskaden-Verstoß: `se-architect` legt für jeden `arch_trigger` einen ADR an
  oder referenziert den bestehenden.

## ADR-Template

```markdown
---
adr_id: ADR-NNN
title: "<kurztitel>"
status: proposed
date: <YYYY-MM-DD>
deciders: [se-architect, user]
affected_reqs: [REQ-L{n}-NNN]
superseded_by: null
---

# <Titel>

## Kontext
<Problem, Constraints, Treiber — Problem-Statement, keine Lösung>

## Alternativen
- <Option 1> — <Abwägung>
- <Option 2 (rejected)> — <Abwägung>

## Entscheidung
<Die gewählte Lösung, präzise und prüfbar formuliert.>

## Konsequenzen
- Positiv: <…>
- Negativ: <…>
```

## Verantwortlichkeit

- **Erstellen:** `se-architect` (bei `arch_impact: true` / `arch_trigger`, bei
  Architektur-Blockern aus V&V, bei Entscheidungen mit Wirkung über eine Zelle hinaus).
- **Review:** `se-critic` (Lifecycle `proposed → review`).
- **Impact-Prüfung:** `se-requirements` matcht neue REQs per Keyword gegen
  ADR-Titel und trägt Treffer in `open_adrs` ein (Bottom-Up, Issue #339 B6).



# SE-Kaskade: Artefakt-Taxonomie

Verbindliche Taxonomie, Trennregel und Output-Location-Regeln für alle SE-Artefakte
(Issue #339 B3/B4, Issue #334). Normativ nur bei aktiver SE-Kaskade.

## Verzeichnisstruktur

Basis-Verzeichnis: `SE` (Konzept-Default: `docs/se`; tatsächlich gilt der
per `se_output.base_dir` konfigurierte Wert).

```
SE/
├── ADR/                              ← flach: ADR-NNN_kurztitel.md
├── L0/                               ← flach: Stakeholder Needs (SN-*)
├── L1/
│   └── {Name}System/                 ← Postfix "System" Pflicht
│       ├── L1_{System}_Requirements.md
│       ├── L1_{System}_Architecture.md
│       ├── L2_architectural_decomposition_iter-N.md   ← Decomposition-Drafts
│       ├── L2_architectural_decomposition_clarifications_iter-N.md
│       ├── .se-state.yaml            ← cell-local State
│       └── L2/{SubSystem}System/     ← rekursiv verschachtelt
│           └── Components/{Id}Component/   ← Postfix "Component" Pflicht
├── VV/                               ← flach: systemweite V&V-Strategie (VV_Strategy.md)
├── reviews/                          ← flach: REVIEW_<YYYY-MM-DD>_<scope>.md
├── traceability/                     ← flach: TRACE_<scope>.md
└── reports/                          ← Status-, Audit- und Critic-Reports
    └── {System|Component}/           ← System-scoped Critic-Reports (Issue #334)
```

- System-Ordner enden IMMER auf `System`, Component-Ordner IMMER auf `Component`
  (eindeutige Zell-Identifikation ohne Tag-Ebene).
- `implementation/`-Subfolder existieren nur INNERHALB von Zellen, nie auf Root-Ebene.
- Cell-local `.se-state.yaml` pro Zelle (Resume ohne globale Locks).

## Datei-Naming

- Schema: `<TYPE>-<ID>_<kurztitel>.md` bzw. `L{N}_{FolderName}_{Artefakt}.md`
  (lowercase snake_case kurztitel, ASCII, keine Leerzeichen).
- **Versionsnummern im Dateinamen sind VERBOTEN** (`_v6`-Suffix ist die #339-Sünde).
  Versionierung ausschließlich via Git.
- Erlaubte Iterations-Marker NUR für Klärungs-/Decomposition-Dokumente: `_iter-N`.
  Review-Intermediate (`*.iter-N.md`, `*.critic.iter-N.md`, `*.critic.final.md`)
  neben Final-Artefakten sind verboten (Issue #334) — siehe unten.
- YAML-Frontmatter-Pflicht für alle SE-Dokumente, mindestens:
  `type`, `scope`, `status`, `date`, `author_agent`.
  `type` ∈ `ADR | REQ | REVIEW | TRACE | ARCH | VV-DOC | STRATEGY`.

## Output-Location-Regeln (Issue #334)

| Artefakt | Ablageort | Nie daneben |
|----------|-----------|-------------|
| Final-Artefakt (Requirements/Architecture) | Zelle: `L{N}_{FolderName}_{Requirements|Architecture}.md` (ohne Suffix) | Keine `.iter-N`/`.final`/`.critic.*`-Kopien |
| Review-Protokolle | `SE/reviews/REVIEW_<YYYY-MM-DD>_<scope>.md` | REQ-/ARCH-Dateien |
| Critic-Reports (Audit-Trail) | `SE/reports/{FolderName}/` | Zellen-Ordner |
| Traceability-Matrizen | `SE/traceability/TRACE_<scope>.md` | REQ-/ARCH-Dateien |
| Metriken/Zusammenfassungen | `SE/reports/` (zentral) | Jede REQ-/ARCH-Datei |
| V&V-Strategie-Dokumente | `SE/VV/` (flach, z. B. `VV_Strategy.md`) | REQ-/ARCH-Dateien |
| ADRs | `SE/ADR/ADR-NNN_kurztitel.md` | REQ-/ARCH-Dateien (nur `open_adrs`-Referenz) |

Ausnahme (Konzept §7-Zellen): Zell-lokale V&V-Step-Artefakte (`TestPlan`, `Validation`) dürfen im
`validation/`- bzw. `implementation/`-Subfolder **innerhalb** ihrer Zelle liegen — die flache
`VV/`-Ablage ist für systemweite Strategie-Dokumente. Beides nie in REQ-/ARCH-Dateien.

- Iterations-Zustand läuft über den A2A-Loop (Generator ⇄ Critic) und Review-Protokolle —
  nicht als Dateien neben Final-Artefakten. Optionales Iterations-History lebt im
  Critic-Endreport (Issue #334, Punkt 4), nicht in verstreuten Zwischendateien.
- Stale-Intermediate älterer Läufe (`*.iter-N.md`, `*.final.md`, `*.critic.*`) im
  Zellen-Ordner werden nach dem Final-Pass entfernt.

## L2-Trennregel (Issue #339 B4)

REQ-Dateien enthalten **NUR Anforderungen**: messbare Aussagen, Akzeptanzkriterien,
external interfaces, Verifikationsreferenzen, YAML-Frontmatter.

Erlaubte Struktur einer REQ-Datei: max. 1 H1 (Titel), 1× H2 `Beschreibung`,
N× H2 `Akzeptanzkriterien`, YAML-Frontmatter. Alles andere ist ein Taxonomie-Verstoß.

| Artefakt | Ablageort | Erlaubt in REQ-Datei? |
|----------|-----------|----------------------|
| Architecture-Decomposition | `L{N}_{System}_Architecture.md` (Zelle) | ❌ — nie inline |
| Implementation | `implementation/` innerhalb der Zelle | ❌ |
| Review-Befunde | `SE/reviews/` (nur `review_id`-Referenz) | ❌ — nie inline |
| Traceability-Matrizen | `SE/traceability/` | ❌ |
| Metrik-Tabellen/Zusammenfassungen | zentraler Report in `SE/reports/` | ❌ — redundant pro REQ-Datei verboten |
| V&V-Dokumente | `SE/VV/` | ❌ |
| ADR-Inhalte | `SE/ADR/` | ❌ — nur `open_adrs`-Referenz im Frontmatter |

## Geltungsbereich

Diese Taxonomie bindet alle Agenten, die SE-Artefakte erzeugen oder verschieben
(`se-requirements`, `se-component-requirements`, `se-architect`, `se-critic`,
`se-integration-and-test-manager`, `se-verifier`, `se-validator`, `se-developer` und Ableitungen). Beim Anlegen eines
neuen SE-Dokuments gilt: erst Taxonomie-Platz wählen, dann Datei schreiben — nie
umgekehrt.



# SE-Kaskade: Review-Lifecycle

Verbindlicher Review-Lifecycle mit Protokoll-Pflicht und RVW-Finding-IDs für die
SE-Kaskade (Issue #339 B5). Normativ nur bei aktiver SE-Kaskade.

## Lifecycle

```
Open ──► Review (Iteration N) ──► Response ──► Closed
            │                                  ▲
            └─► Iteration N+1 (Re-Review) ─────┘
```

- Jede Iteration ist ein eigener, nummerierter Review-Zyklus — keine
  statuslosen Ad-hoc-Reviews.
- `review_iteration` im REQ-Frontmatter wird mit jeder Iteration inkrementiert
  (monoton steigend, Startwert 0).

## IDs

- **Review-ID:** `RVW-YYYY-MM-DD-NNN` (NNN = 3-stellig, pro Tag monoton steigend).
- **Finding-ID:** `RVW-YYYY-MM-DD-NNN-<k>` (k = 2-stellig innerhalb des Protokolls,
  z. B. `RVW-2026-06-28-001-01`). Jeder Befund trägt eine stabile, referenzierbare ID.
- REQ-Dateien referenzieren Befunde ausschließlich über die Review-ID
  (`review_id:` im Frontmatter) — **nie inline** (siehe L2-Trennregel, B4).

## Review-Protokoll (Pflicht)

Jede Review-Iteration erzeugt ein Protokoll:

- Ablageort: `SE/reviews/REVIEW_<YYYY-MM-DD>_<scope>.md`
  (`scope` = REQ-ID oder Zell-/Systemname, lowercase).
- Frontmatter (Schema: `schemas/se-review.schema.json`):

```yaml
---
review_id: RVW-YYYY-MM-DD-NNN
target_req: REQ-L{n}-NNN
iteration: 1
status: open          # open | response | closed
date: YYYY-MM-DD
reviewer: se-critic
findings:
  - id: RVW-YYYY-MM-DD-NNN-01
    severity: major   # major | minor | info
    category: "<Kategorie, z. B. 'Akzeptanzkriterium unvollstaendig'>"
    description: "<Befund>"
    suggested_fix: "<Konkreter Fix-Vorschlag>"
---
```

- Protokoll-Status folgt dem Lifecycle: `open` (Befunde offen) → `response`
  (Generator hat reagiert) → `closed` (Befunde abgearbeitet).
- Befunde werden im Protokoll beschrieben, NICHT in REQ-Dateien kopiert.

## REQ-Frontmatter-Sync

Nach Abschluss einer Iteration aktualisiert `se-critic` die betroffene REQ:
`review_state` (`open | reviewed | approved`), `last_reviewed` (ISO-8601),
`reviewer` (`se-critic`), `review_iteration` (+1). Bei `approved` zusätzlich
`implementation_state`/`test_status` unangetastet lassen (gehört dem rechten Flügel).

## Suspect-Mark (Bottom-Up, Issue #339 B6)

Setzt `se-critic`, wenn ein Befund an einer REQ eine Re-Derivation des Parents
erfordert:

- Parent-REQ: `review_state: open` + `suspect_children: [<child-req-id>]` im
  Frontmatter + Eskalationsverweis auf die `review_id` des auslösenden Protokolls.
- Suspect-Marks fließen nach oben (Child → Parent) bis zur höchsten betroffenen
  Ebene; der ADR-Impact-Check (siehe ADR-Standard) läuft parallel.
- Max. 2 automatische Re-Derivations-Iterationen, danach User-Approval erzwingen
  (Kaskaden-Bomben-Schutz, Konzept §13).

## Akzeptanzkriterium

Jede REQ mit `review_state: reviewed` oder `approved` hat genau eine
korrespondierende Protokoll-Datei in `SE/reviews/` mit passender
`review_id`. Reviews ohne Protokoll, ohne Iterationsnummer oder ohne formalen
Abschluss-Status sind Kaskaden-Verstöße.



# Security Paved Roads

Security wird als vorgeprüfte Paved-Road-Blöcke geliefert, nicht als DIY-Aufgabe:
**invisible, consistent, embedded, non-optional** (Netflix Paved Roads / Golden Path).
Ein Block ist ausgereift, sicherheitsgeprüft und wird identisch überall verwendet —
niemand implementiert Security-Logik selbst neu.

## Block-Katalog

| Block | Abdeckt | Eigentümer-Agent |
|-------|---------|------------------|
| `auth-flow` | Authentifizierung (Login, Session, Token) | `security-auditor` |
| `dependency-check` | SBOM + CVE-Scan der Abhängigkeiten | `dependency-auditor` |
| `input-validation` | Eingabevalidierung (Schema, Sanitizing) | `security-auditor` |
| `rate-limiting` | Rate-Limiting / Throttling | `devops-engineer` |
| `cors-config` | CORS-Konfiguration | `security-auditor` |
| `secret-scanning` | Secret-Scan (Leaks in Diffs, Commits, Logs) | `security-auditor` |

## Enforcement

- **Vor jedem Commit:** Secret-Scan über den Block `secret-scanning` ausführen.
- **Vor jedem Deploy:** `dependency-check` (SBOM + CVE) ausführen.
- **Für neue Features:** den `auth-flow`-Block nutzen statt Auth selbst zu bauen.

DIY-Security ist eine Anti-Pattern: jede Variante erzeugt unbekannte Lücken.
Abweichungen vom Block-Katalog werden als Review-Befund von `security-auditor`
gemeldet, nicht als Eigenbau gerechtfertigt.



# Threat Model — die 4 Fragen

Vor jedem öffentlichen Release die 4 Fragen beantworten (Igor Andriushchenko,
CISO Lovable):

1. **Was baust du?** — Datenspeicherung, Auth, Autorisierung, woher kommen die User?
2. **Was könnte schiefgehen?** — Worst-Case-Szenarien (Leak, Bypass, Datenverlust).
3. **Was tust du dagegen?** — konkrete Gegenmaßnahme pro Risiko.
4. **Was sind die Konsequenzen?** — Business-Impact, Datenverlust, Reputation.

## Anwendung

- `concept-reviewer` prüft die 4 Fragen in Design-Docs (Threat-Model-Checkliste).
- `orchestrator` stellt die 4 Fragen vor Feature-Releases.
- **Interne Apps:** vereinfacht — 1–2 Fragen reichen.
- **Customer-facing Apps:** vollständig — alle 4 Fragen plus dokumentiertes Threat Model.



# Lazy-Loaded Rules

> Nicht immer geladen — bei Bedarf per `Read` öffnen: `.gemini/skills bzw. .opencode/skills bzw. .agents/skills bzw. .zcode/skills bzw. .kimi-code/skills/<skill>/SKILL.md` (jeweils).

| Skill | Wann |
|---|---|
| sync-interface | sync.py, Templates/Rules ändern |
| admin-ui | Admin-Server/UI betreiben (Lifecycle, Token, Ports) |
| architecture | Templates/Overrides/Placeholder ändern |
| conventions | Vor Commits in agents/, config/, scripts/lib |
| submodule-protection | .agent-meta/, external/, .gitmodules |
| a2a-delegation-gates | A2A-Delegation an Subagenten |
| issue-lifecycle | GitHub-Issue |
| lifecycle-tasks | Session-Start, pending-tasks.md vorhanden |
| session-conclusion | Feature-Abschluss |
| provider-agnostic | agents/1-generic editieren |
| mcp-reqogniloom | ReqogniLoom-MCP-Tools |
| mcp-honcho | Honcho-MCP-Memory-Tools |
| mcp-playwright | Playwright-MCP-Browser-Tools |
| mcp-viz-logger | viz-logger Event-Logging |
| tool-graphify | Architektur-/Datei-Fragen mit graphify |

Harte MCP-Tool-Verbote: siehe `mcp-guardrails.md` (always-on).



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
Commit ist für die per `auto_commit`-Tier freigeschaltete Rolle erlaubt (Details im Commit-Authority-Block der jeweiligen Rolle). Push, Tag und Branch-Management bleiben ausschließlich Aufgabe des `git` Agenten. Read-only (status, log) im Main Chat ok.

Native Extensions (Skills/Hooks) erlaubt, ignorieren nicht Branch-Guard/DoD.
Skill-getriebene Sub-Agent-Loops (z.B. generische Harness-Skills wie `subagent-driven-development`) sind KEINE dritte Ausnahme von der Orchestrator-Pflicht: ein Skill darf einen bereits vom `orchestrator` gestarteten Loop ausführen, aber niemals selbst zum Einstiegspunkt für einen neuen Dev-Task werden. Einzige Ausnahmen bleiben User-Override.

Anti-Recursion: Worker dürfen nicht an `orchestrator` zurück delegieren.



# External Tool: graphify

> graphify — lokal installiertes CLI-Tool. Baut das Repo als Wissensgraph auf (Community Detection, God Nodes, Query/Path/Explain). Wird NICHT von agent-meta bereitgestellt, muss lokal installiert sein.

---

## graphify
`graphify` ist ein lokal installiertes CLI-Tool für Architektur-/Datei-
Beziehungsfragen. Bei Bedarf `graphify-out/` prüfen bzw. `/graphify`
nutzen. Nicht auf dieser Maschine installiert? Die Hook-Wrapper unten
laufen dann folgenlos durch (exit 0), nichts wird blockiert.

## Hook-Wrapper

- `hooks/0-external/graphify-search-guard.sh`
- `hooks/0-external/graphify-read-guard.sh`

## Erlaubte Injektionen

- `.gemini/skills/graphify bzw. .opencode/skills/graphify bzw. .agents/skills/graphify bzw. .zcode/skills/graphify bzw. .kimi-code/skills/graphify` (skill) — Claude-Code-Skill (SKILL.md + references), vom graphify-Installer selbst verwaltet

---

*Generiert von agent-meta aus `config/external-tools-registry.yaml` — nicht manuell bearbeiten.*






## Übrige Regeln (Lazy-Load)

Nicht-Kern-Regeln werden NICHT in diesen Block eingebettet (Progressive Disclosure, #192):
sie liegen pro Provider als separate Dateien in .gemini/skills bzw. .opencode/skills bzw. .agents/skills bzw. .zcode/skills bzw. .kimi-code/skills — jeweils `<rule-name>/SKILL.md`.
Bei Bedarf mit `Read` laden; verfügbare Regeln via `ls` im jeweiligen Verzeichnis.


## Agent Directory
> ⚠️ **ACHTUNG:** Agenten (Prompts) liegen in `.gemini/agents bzw. .opencode/agents bzw. .codex/agents bzw. .zcode/agents bzw. .kimi-code/agents`.

| Agent | Core Capabilities |
|-------|-------------------|

| `accessibility-specialist` | WCAG 2.1/2.2 Compliance-Audit, ARIA-Checks, Keyboard-Navigation |

| `agent-meta-manager` | agent-meta verwalten: Upgrade, Sync, Feedback |

| `agent-meta-scout` | Claude-Ökosystem scouten: neue Skills, Rollen, Rules |

| `api-specialist` | OpenAPI/Contract-First API Design, Schnittstellen-Spezifikationen |

| `bug-feature-analyzer` | Issue-Triage: Eingehende Bug-Meldungen, Feature-Requests analysieren, k |

| `code-reviewer` | Clean Code Gatekeeper: Blast-Radius-Analyse, SOLID/DRY Prüfung, Code-Qualität |

| `concept-reviewer` | Konzept-Critic: reviewt Design-Docs, Konzepte auf Vollständigkeit, Logik |

| `data-engineer` | ETL/ELT-Pipelines, Schema-Migration (Datenebene), Data-Quality-Checks |

| `database-engineer` | Relationales Schema-Design, Datenbank-Migrationen, Query-Optimierung |

| `dependency-auditor` | Supply-Chain-Hygiene: SBOM-Analyse, Lizenz-Kompatibilität, Version-Drift und |

| `developer` | Feature-Implementierung, Bugfixes |

| `devops-engineer` | CI/CD, Infrastructure as Code, Kubernetes |

| `docker` | Dev-Stack verwalten, Test-Stack starten, Binary-Management |

| `documenter` | CODEBASE_OVERVIEW, ARCHITECTURE, README |

| `e2e-tester` | E2E-Tests, visuelle Regression, Accessibility-Audits via Playwright |

| `effort-estimator` | Schätzt Aufwände für Entwicklungsaufgaben basierend auf Task-Typ, LLM-Kali |

| `explorer` | Read-only Codebase-Recherche, Dependency, Impact-Mapping |

| `export-manager` | Target-agnostischer Output-Router: Markdown, Confluence, Jira-Xray |

| `feedback` | Projekt-Feedback standardisieren: Bugs, Features, Verbesserungen als GitHub I |

| `git` | Commits, Branches, Tags |

| `ideation` | Neue Ideen explorieren, Vision schärfen, Übergabe an requirements |

| `incident-responder` | Live-Incident-Koordination: korreliert Logs, Metriken, führt Runbook-Schri |

| `intern-developer` | Der übereifrige Praktikant |

| `junior-developer` | Triviale Code-Änderungen (≤2 Dateien, kein Architektur-Impact) |

| `knowledge-curator` | Strategische Knowledge-Engine-Steuerung: Schema-Evolution, Wiki-Strukturierun |

| `knowledge-gardener` | Kleinteilige Wiki-Pflege: Links reparieren, Tags harmonisieren, Frontmatter e |

| `knowledge-indexer` | Pflegt index.md (Content-Katalog, OKF §6), log.md (Chronologisches Event-L |

| `knowledge-ingestor` | Sources einlesen, Key Information extrahieren, Wiki-Seiten erstellen/ aktuali |

| `knowledge-linter` | Wiki-Gesundheitscheck: Widersprüche, Orphans, veraltete Claims |

| `knowledge-migrator` | Vorhandene Projektinhalte aufräumen, OKF-konform ins Knowledge Wiki migrieren |

| `knowledge-querier` | Fragen gegen das Knowledge Wiki beantworten |

| `log-analyzer` | System, Applikations-Logs analysieren: Frequency-Clustering, Severity-Kla |

| `meta-feedback` | Verbesserungsvorschläge für agent-meta als GitHub Issues einreichen |

| `orchestrator` | Einstiegspunkt für alle Entwicklungsaufgaben |

| `performance-optimizer` | Big-O Bottleneck-Identifikation, datengetriebene Performance-Optimierung |

| `principal-developer` | Last-Resort-Eskalationsstufe |

| `refactoring-specialist` | Systematische großflächige Code-Transformation mit Sicherheitsnetz: Strangler |

| `release` | Versioning, Changelog, Build-Artifact |

| `requirements` | Anforderungen aufnehmen, REQ-IDs vergeben, REQUIREMENTS.md pflegen |

| `se-architect` | Zerlegt Blackboxes in Whiteboxes nach strengen Architekturgesetzen (CQRS, Ort |

| `se-critic` | Prüft Architekturentscheidungen iterativ auf Vollständigkeit, Konsistenz und |

| `se-developer` | Standard SE-Leaf-Implementierung (2-4 Interfaces) mit strikter Interface-Disz |

| `se-integration-and-test-manager` | V&V-Orchestrator: Bestimmt Integrationsstrategie, koordiniert Test-Ebenen |

| `se-interface-mgr` | Verwaltet, validiert alle Schnittstellenverträge domänenübergreifend |

| `se-junior-developer` | Triviale SE-Leaf-Implementierung (0-1 Interfaces, kein cross-cutting) |

| `se-requirements` | Nimmt Stakeholder-Bedürfnisse auf, erstellt das formale L1-Blackbox-Requir |

| `se-senior-developer` | Komplexe SE-Leaf-Implementierung (5+ Interfaces, cross-cutting, boundary-leve |

| `se-termination` | Entscheidet deterministisch, ob der L3-Component-Leaf-Node erreicht wurde |

| `se-test-engineer` | Entwickelt MBSE-Testmodelle, entwirft Integrationstests für den rechten V |

| `se-testreviewer` | Auditiert Teststrategien auf Edge-Cases, Boundary Values, Äquivalenzklassen u |

| `se-validator` | L1 System-Validierung: End-to-End User Journeys gegen Stakeholder-Bedürfnisse |

| `se-verifier` | Multi-Level Verification (L1-Ln): Prüft integrierte Systeme gegen Architektur |

| `senior-developer` | Komplexe Features, Architektur-Entscheidungen, schwierige Bugs |

| `sre-engineer` | Proaktive Reliability-Disziplin: SLI/SLO-Definition, Error-Budgets, Capacity |

| `technical-writer` | Externe entwickler, nutzergerichtete Doku: API-Referenzen, Getting-Starte |

| `tester` | TDD, Test-Suite ausführen, Testabdeckung sichern |

| `ui-ux-designer` | UI-Spezifikationen, Mockups, Design-Systeme erstellen |

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
