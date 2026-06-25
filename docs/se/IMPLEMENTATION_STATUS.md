# ReqFlow — Implementierungs-Status (SE-Kaskade → Code)

> **Zweck:** Zustands-Datei für die schrittweise Code-Umsetzung der SE-Kaskade.
> Hält fest, welche L2-Systeme/Komponenten implementiert sind, was offen ist
> und wie nach einem Abbruch (z.B. Session-Limit) wieder aufgesetzt wird.
>
> **Branch:** `feat/se-implementation`
> **Strategie:** Bottom-Up nach `docs/se/integration-strategy.md` (Layer 0 → 4)
> **Letzte Aktualisierung:** 2026-06-24 (nach Wave 6)

---

## Vorgehen

- Pro L2-System eine Django-App unter `backend/<app>/` (Mapping siehe `backend/README.md`).
- Delegation an SE-Developer **je Komplexität** (Pflicht — siehe »Orchestrator-Direktive« unten).
- **Model-Override-Hinweis:** SE-Agent-Frontmatter ist auf bare IDs gefixt
  (`claude-opus-4-8`, `claude-sonnet-4-6`); die laufende Harness cached alte IDs bis Reload
  → in dieser Session pro Agent-Call `model` explizit setzen (`opus`/`sonnet`/`haiku`).
- Checkpoint-Commit nach jeder Welle. `__pycache__` via `backend/.gitignore` ignoriert.

---

## Orchestrator-Direktive — se-Developer korrekt nach Komplexität einsetzen

**Verbindlich für alle restlichen Wellen.** Tier-Auswahl pro Leaf/Komponente:

| Tier | Agent | Modell | Wofür |
|------|-------|--------|-------|
| Trivial | `se-junior-developer` | Haiku | 1 Komponente, 0–1 Interfaces, kein Cross-Cutting (z.B. COTS-Wrapper, einfacher Renderer/Stub) |
| Standard | `se-developer` | Sonnet | 2–4 Interfaces, ein Modul, klar spezifiziert (Default für die meisten Komponenten) |
| Komplex | `se-senior-developer` | Opus 4.8 | Cross-Cutting, Boundary-Level, Security/Performance-kritisch, ≥5 Interfaces, Foundation |

Regeln: Foundation-/Security-/Performance-kritische Systeme → **senior**. Reine CRUD/Adapter →
**developer**. Triviale Einzel-Stubs → **junior**. Im Zweifel eine Stufe höher.

---

## Status-Übersicht

| Welle | Layer | System (ARCH-L1) | App | Status | Commit |
|-------|-------|------------------|-----|--------|--------|
| 0 | — | Scaffolding | — | ✅ | `456ea77` |
| 1 | 0 | PersistenceLayer (010) | `persistence` | ✅ | `9e77ed0` |
| 2 | 0 | AuthAndTenancy (011) | `auth_tenancy` | ✅ | `500bf06` |
| 2 | 0 | PresetConfigEngine (008) | `presets` | ✅ | `500bf06` |
| 2 | 0 | AuditLog (012) | `audit` | ✅ | `500bf06` |
| 3 | 1 | LlmAdapter (009) | `llm_adapter` | ✅ (55 Tests grün) | `424021c` |
| 3 | 1 | TraceabilityEngine (007) | `traceability` | ✅ | `424021c` |
| 4 | 1 | WorkflowEngine (005) | `workflow` | ✅ | `079687b` |
| 4 | 1 | BaselineService (006) | `baseline` | ✅ | `079687b` |
| 5a | 2 | ApplicationService (004) Foundation+Core | `application` | ✅ | `16d88c9` |
| 5b | 2 | ApplicationService Facades+IO | `application` | ✅ | `3081435` |
| 5c | 2 | ApplicationService ADR/Risk/Issue | `application` | ✅ | `7f1b445` |
| 5d | 2 | ApplicationService Core-Tests + Bugfix | `application` | ✅ (131 Tests) | `5a22777` |
| 6 | 3 | RestApiAdapter (002) | `rest_api` | ✅ | `9c77b5c` |
| 6 | 3 | McpServer (003) | `mcp_server` | ✅ (71 Tests grün) | `9c77b5c` |
| 8 | ext | DiagramService (013) | `diagram` | ✅ (42 Tests grün) | `ed731ab` |
| 8 | ext | IcdManagement (014) | `icd` | ✅ (12 Unit grün) | `ed731ab` |
| 8 | ext | SeMetrics (015) | `se_metrics` | ✅ (69 Tests grün) | `ed731ab` |
| 8 | ext | ResilienceOrchestrator (016) | `resilience` | ✅ (31 Tests grün) | `ed731ab` |
| 7 | 4 | ReactFrontend (001) | `frontend/` | ✅ (34 Dateien, Vitest) | `b01414a` |

**Fertig:** 16 von 16 Systemen + ReactFrontend vollständig committet. **Implementierung + Validierung abgeschlossen.**

### Validierung (✅ erledigt)
- `manage.py check`: 0 Issues (Index-Namen ≤30 Zeichen gefixt, E034 weg).
- Sync-Migrationen generiert; `migrate` über alle Apps grün.
- **Docker-Gesamttestlauf: 1042/1042 Tests grün** (`docker-compose run --rm --entrypoint "" backend python -m pytest`).
- Foundation-Fix: `TenantManager.create()` injiziert `tenant_id` automatisch aus aktivem `TenantContext`.

### Offene Tech-Debt (kein Blocker, v2/Folgearbeit)
1. **Celery-Broker-Wiring** in settings.py (AsyncDispatcher, WebhookDispatcher, SeMetrics-Cache, LlmAdapter-Async) — optional, Kernbetrieb läuft synchron.
2. **WebhookDispatcher/LlmAdapter → ResilienceOrchestrator** umverdrahten (TODO-Marker gesetzt).
3. **persistence.User** ohne `password`-Feld → SignatureGate/AuthN-Passwortprüfung fallen sicher auf `False`.
4. **TraceLink.link_type** DB-CHECK-Constraint (8 Typen) — derzeit nur Service-Layer-Validierung.
5. **Honcho-Memory:** `HONCHO_API_KEY` setzen + `/honcho:setup`; Wissensbasis liegt in `docs/se/PROJECT_KNOWLEDGE.md` bereit.

---

## Nächste Schritte (Resume-Reihenfolge)

1. **Wave 8 — 4 Erweiterungs-Systeme** (unabhängig, parallelisierbar, disjunkte Apps):
   - `diagram` (5 Komp) → **se-developer** (Renderer-Teil ggf. junior-Stub)
   - `icd` (4 Komp, immutable Versionierung + Breaking-Change-Detection) → **se-developer**;
     **wichtig:** `get_icd_versions(workspace_id)` bereitstellen (BaselineService-Stub wartet darauf)
   - `se_metrics` (5 Komp, Read-Model über audit/traceability/workflow/application) → **se-developer**
   - `resilience` (5 Komp, Cross-Cutting: Timeout/Retry/Circuit-Breaker) → **se-senior-developer**
   Briefing-Vorlagen lagen bereits vor (siehe Foundation-Contracts unten). Nur `backend/<app>/` +
   eigene Migration anfassen, settings/andere Apps nicht.
2. **Wave 7 — ReactFrontend** (`frontend/`, gegen REST-API `/api/v1/`): NavigationShell,
   DashboardViews, RequirementEditors, ArchitectureEditors; i18n DE/EN; → **se-developer**.
3. **Integration:** settings.py-Rest (Celery-Broker für AsyncDispatcher/Webhook), App-Registrierung
   der neuen Migrationen prüfen; dann `docker-compose up` + `pytest` Gesamtlauf
   (Phasen-Gates `docs/se/integration-strategy.md`).

---

## Foundation-Contracts (für Downstream verbindlich)

Kern-Entitäten zentral in `persistence.models` — **importieren, nicht neu definieren:**
`Tenant, User, Role, Workspace, Artifact, Requirement, ArchitectureElement, TraceLink,
TestCase, Baseline, WorkflowDefinition, WorkflowState, AuditLogEntry`.

```python
from persistence.models import TenantScopedModel, AuditableModel
from persistence.tenancy import TenantContext, TenantContextNotSetError
from persistence.transactions import atomic_transaction
```

Öffentliche Service-Fassaden (fertige Systeme):
- `from presets.services import get_preset, is_feature_enabled, get_terminology`
- `from audit.services import log_write, query`
- `from traceability.services import query, coverage, create_trace_link, collect_trace_graph`
- `from workflow.services import transition, initialize_workflow_states`
- `from baseline.services import build, diff, get, list_baselines, get_item_at_baseline`
- `from llm_adapter.services import validate_artifact, decompose_requirement, check_consistency`
- `from application.services import *` (16 Services — ADR-01 Single Entry Point; inkl.
  `RiskService.query_risks_by_severity(workspace_id, severity, ctx)` für SeMetrics)
- Auth: DRF-Auth/Permission-Classes in `auth_tenancy/rest.py` + `auth_tenancy/services/`.

---

## Offene Escalations / Tech-Debt

1. **TraceLink.link_type** `CharField` in persistence; 8-Typen-Validierung in traceability-Service.
   → DB-CHECK-Constraint-Migration in persistence nachziehen.
2. **persistence.User ohne `password`-Feld** → SignatureGate (COMP-WE-004) + AuthN-Passwortprüfung
   fallen sicher auf `False`. → Passwort-Hash-Storage in AuthAndTenancy ergänzen.
3. **ICD-Stub** in BaselineService — aktiv sobald IcdManagement (Wave 8) `get_icd_versions` liefert.
4. **settings.py:** DRF-Auth/Permission/Pagination + Auth-Middleware durch RestApiAdapter verdrahtet
   (Commit `9c77b5c`). **Offen:** Celery-Broker-Wiring (AsyncDispatcher, WebhookDispatcher),
   Registrierung neuer Wave-8-Migrationen.
5. **Tests noch nicht im Gesamtlauf:** LlmAdapter (55) + McpServer (71) laufen rein in Python;
   alle übrigen Suites brauchen PostgreSQL via Docker. Noch kein `docker-compose up` + `pytest` gesamt.
6. **WebhookDispatcher/LlmAdapter → ResilienceOrchestrator:** TODO-Marker gesetzt; tatsächliche
   Umverdrahtung erst nach Resilience-Implementierung (Wave 8) + Celery-Wiring.

---

## Resume-Anleitung (nach Limit/Neustart)

1. `git branch --show-current` → `feat/se-implementation`; `git log --oneline` mit Tabelle abgleichen.
2. `git status` — uncommittete Reste prüfen.
3. Nächster ⏳-Eintrag = nächste Aufgabe; **Orchestrator-Direktive** (Tier nach Komplexität) anwenden.
4. Pro System: Specs `docs/se/L1/Gesamtsystem/L2/<System>/` lesen, Foundation-Contracts mitgeben,
   nur eigene App anfassen, Checkpoint-Commit, diese Datei aktualisieren.
5. Zum Schluss: Integration (Punkt 3 oben) + Docker-Gesamttestlauf.
