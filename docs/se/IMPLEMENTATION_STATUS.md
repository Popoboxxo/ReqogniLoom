# ReqFlow — Implementierungs-Status (SE-Kaskade → Code)

> **Zweck:** Zustands-Datei für die schrittweise Code-Umsetzung der SE-Kaskade.
> Hält fest, welche L2-Systeme/Komponenten bereits implementiert sind, was offen ist
> und wie nach einem Abbruch (z.B. Session-Limit) wieder aufgesetzt wird.
>
> **Branch:** `feat/se-implementation`
> **Strategie:** Bottom-Up nach `docs/se/integration-strategy.md` (Layer 0 → 4)
> **Letzte Aktualisierung:** 2026-06-24

---

## Vorgehen

- Pro L2-System eine Django-App unter `backend/<app>/` (Mapping siehe `backend/README.md`).
- Delegation an SE-Developer je Komplexität: `se-junior` (Haiku), `se-developer` (Sonnet), `se-senior` (Opus 4.8).
- **Model-Override-Hinweis:** Die SE-Agent-Frontmatter ist auf bare IDs gefixt
  (`claude-opus-4-8`, `claude-sonnet-4-6`), aber die laufende Harness cached die alten
  IDs bis zum Reload → in dieser Session pro Agent-Call `model` explizit setzen.
- Checkpoint-Commit nach jeder Welle. `__pycache__` via `backend/.gitignore` ignoriert.

---

## Status-Übersicht

| Welle | Layer | System (ARCH-L1) | App | Komp. | Status | Commit |
|-------|-------|------------------|-----|-------|--------|--------|
| 0 | — | Scaffolding (Django+React+Compose) | — | — | ✅ committed | `456ea77` |
| 1 | 0 | PersistenceLayer (010) | `persistence` | 5(+RLS) | ✅ committed | `9e77ed0` |
| 2 | 0 | AuthAndTenancy (011) | `auth_tenancy` | 3 | ✅ committed | `500bf06` |
| 2 | 0 | PresetConfigEngine (008) | `presets` | 3 | ✅ committed | `500bf06` |
| 2 | 0 | AuditLog (012) | `audit` | 3 | ✅ committed | `500bf06` |
| 3 | 1 | LlmAdapter (009) | `llm_adapter` | 5 | ✅ committed (55/55 Tests grün) | `424021c` |
| 3 | 1 | TraceabilityEngine (007) | `traceability` | 4 | ✅ committed | `424021c` |
| 4 | 1 | WorkflowEngine (005) | `workflow` | 4 | ✅ committed | `079687b` |
| 4 | 1 | BaselineService (006) | `baseline` | 4 | ✅ committed | `079687b` |
| 5a | 2 | ApplicationService (004) — Foundation+Core | `application` | 7/16 | ⚠️ committed (partial — **Tests fehlen, nachzuziehen**) | `WIP` |
| 5b | 2 | ApplicationService — Facades+IO | `application` | 6/16 | ⏳ offen | — |
| 5c | 2 | ApplicationService — ADR/Risk/Issue | `application` | 3/16 | ⏳ offen | — |
| 6 | 3 | RestApiAdapter (002) | `rest_api` | 5 | ⏳ offen | — |
| 6 | 3 | McpServer (003) | `mcp_server` | 5 | ⏳ offen | — |
| 7 | 4 | ReactFrontend (001) | `frontend/` | 4 | ⏳ offen | — |
| 8 | ext | DiagramService (013) | `diagram` | 5 | ⏳ offen | — |
| 8 | ext | IcdManagement (014) | `icd` | 4 | ⏳ offen | — |
| 8 | ext | SeMetrics (015) | `se_metrics` | 5 | ⏳ offen | — |
| 8 | ext | ResilienceOrchestrator (016) | `resilience` | 5 | ⏳ offen | — |

**Fertig:** 8 von 16 Systemen vollständig committet (Layer 0 + Layer 1).
**In Arbeit:** ApplicationService (5a Code da, Tests + 5b/5c offen).

---

## ApplicationService — Detailstand (Welle 5)

App `backend/application/`. Foundation-Muster steht (kompiliert, `py_compile` OK).

**5a — vorhanden auf Disk (NICHT committet, Tests fehlen):**
- `event_bus.py` (COMP-AS-016 DomainEventBus)
- `base.py` (gemeinsame ServiceBase für CRUD-Artefakt-Services)
- `artifact_service.py` (COMP-AS-001), `requirement_service.py` (002),
  `architecture_service.py` (003), `test_service.py` (004),
  `trace_link_service.py` (005), `preset_policy_service.py` (012)
- `services.py` (Fassade), `models.py`, `migrations/0001_initial.py`
- ⚠️ `tests/` enthält nur `__init__.py` — **Unit-Tests nachzuziehen** (Limit traf in Test-Phase)

**5b — offen:** COMP-AS-006 BaselineFacade, 007 WorkflowFacade, 008 ExportService,
009 ImportService, 010 SearchService, 011 WebhookDispatcher.

**5c — offen:** COMP-AS-013 AdrService, 014 RiskService, 015 IssueService
(Entitäten Adr/Risk/Issue existieren noch NICHT in `persistence.models` → in `application/models.py` anlegen, erbend von `TenantScopedModel`).

---

## Foundation-Contracts (für Downstream verbindlich)

Kern-Entitäten liegen zentral in `persistence.models` — **importieren, nicht neu definieren:**
`Tenant, User, Role, Workspace, Artifact, Requirement, ArchitectureElement, TraceLink,
TestCase, Baseline, WorkflowDefinition, WorkflowState, AuditLogEntry`.

```python
from persistence.models import TenantScopedModel, AuditableModel
from persistence.tenancy import TenantContext, TenantContextNotSetError
from persistence.transactions import atomic_transaction
```

Öffentliche Service-Fassaden (Stand fertige Systeme):
- `from presets.services import get_preset, is_feature_enabled, get_terminology`
- `from audit.services import log_write, query`
- `from traceability.services import query, coverage, create_trace_link, collect_trace_graph, ...`
- `from workflow.services import transition, initialize_workflow_states, ...`
- `from baseline.services import build, diff, get, list_baselines, get_item_at_baseline`
- `from llm_adapter.services import validate_artifact, decompose_requirement, check_consistency, get_task_status`
- Auth: DRF-Auth/Permission-Classes + AuthContext in `auth_tenancy/` (exakte Pfade in `auth_tenancy/services/`).

---

## Offene Escalations / Tech-Debt

1. **TraceLink.link_type** ist `CharField` (6 Werte) in persistence; 8-Typen-Validierung
   (`documents`, `realizes`) liegt in der traceability-Service-Schicht. → DB-CHECK-Constraint-
   Migration in persistence nachziehen (se-interface-mgr/se-architect).
2. **persistence.User hat kein `password`-Feld** (kein AbstractUser). SignatureGate (COMP-WE-004)
   und AuthN-Passwort-Prüfung fallen sicher auf `False`. → Passwort-Hash-Storage in AuthAndTenancy ergänzen.
3. **ICD-Stub** in BaselineService (`icd.services.get_icd_versions` Platzhalter) — aktiviert sich
   automatisch, sobald IcdManagement (ARCH-L1-014, Welle 8) implementiert ist.
4. **settings.py-Wiring offen:** Auth-Middleware, Celery-Broker, Connection-Pooling noch nicht in
   `backend/reqflow/settings.py` verdrahtet (Agenten durften settings.py nicht ändern). → eigener
   Integrations-Schritt vor/bei Welle 6.
5. **Tests laufen noch nicht durchgängig:** außer LlmAdapter (55 reine Python-Tests grün) benötigen
   alle Suites PostgreSQL via Docker. Noch kein `docker-compose up` + `pytest`-Gesamtlauf erfolgt.

---

## Resume-Anleitung (nach Limit/Neustart)

1. Branch prüfen: `git branch --show-current` → `feat/se-implementation`.
2. `git log --oneline` mit Tabelle oben abgleichen.
3. Uncommittet prüfen: `git status` — falls `backend/application/` dirty → Welle 5a Tests
   nachziehen, dann committen.
4. Nächster offener Eintrag der Status-Tabelle = nächste Aufgabe (Bottom-Up-Reihenfolge einhalten).
5. Jede Welle: Specs unter `docs/se/L1/Gesamtsystem/L2/<System>/` lesen, an SE-Developer
   (Komplexität → Tier) delegieren, Foundation-Contracts oben mitgeben, Checkpoint-Commit, diese
   Datei aktualisieren.
6. Nach Welle 6/7: settings.py-Wiring (Escalation 4) erledigen, dann `docker-compose up` +
   Gesamttest-Lauf (`docs/se/integration-strategy.md` Phasen-Gates).
