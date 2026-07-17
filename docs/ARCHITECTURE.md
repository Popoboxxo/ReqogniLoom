# ReqFlow — Architektur-Notizen

> Ergänzende Architektur-Dokumentation zur formalen SE-Hierarchie unter
> `docs/se/`. Diese Datei hält querschnittliche Konventionen fest, die nicht an
> eine einzelne Komponente gebunden sind.

## Transaktionsgrenzen (REQ-073, BE-17)

Der Application-Layer (`backend/application/`) ist der **einzige** Ort, an dem
Transaktionsgrenzen gesetzt werden. Views/Serializer (`rest_api/`) und der
MCP-Server (`mcp_server/`) öffnen niemals selbst eine Transaktion — sie rufen
Service-Methoden auf, die ihre Atomicity selbst kapseln (ADR-01, Single Entry
Point).

### Zwei Mechanismen

| Mechanismus | Quelle | Einsatz |
|-------------|--------|---------|
| `@atomic_transaction` (Decorator) | `persistence/transactions.py` | Einzelne Schreib-Methode (create/update/delete). Jede unbehandelte Exception rollt die gesamte Methode zurück (REQ-L3-PL003-002). |
| `TransactionContextManager` (Context-Manager) | `persistence/transactions.py` | Mehrschrittige Writes (z. B. Batch-Decomposition), optional mit `statement_timeout` (REQ-L3-PL003-003). |

Beide delegieren an Djangos natives `transaction.atomic()`.

### Reihenfolge relativ zum Commit

Innerhalb einer Service-Transaktion gilt folgende Konvention:

1. **Mutation** — ORM-Writes (`Model.objects.create/update`).
2. **Audit-Log** — `ServiceBase._audit(...)` schreibt **synchron in derselben
   Transaktion**. Ein Rollback entfernt Mutation und Audit-Eintrag gemeinsam
   (REQ-L2-AL-004, atomare Konsistenz).
3. **Domain-Events** — `ServiceBase._emit_event(...)` → `DomainEventBus.publish()`
   registriert die Outbox-Insertion via `transaction.on_commit(...)`. Der
   Outbox-Row wird **erst nach erfolgreichem Commit** geschrieben. Eine
   zurückgerollte Transaktion erzeugt daher niemals ein Event (REQ-L2-AS-029,
   REQ-L3-DEB-002). Die tatsächliche Zustellung an Subscriber erfolgt
   asynchron durch den OutboxPoller-Worker.

**Merksatz:** *Audit feuert im Commit, Domain-Events feuern nach dem Commit.*

### Abdeckung im Application-Layer

Alle öffentlichen Schreibpfade sind transaktional gekapselt:

| Service | `@atomic_transaction` | `TransactionContextManager` / `with atomic()` |
|---------|:---:|:---:|
| `adr_service` | 4 | – |
| `architecture_service` | 3 | – |
| `artifact_service` | 3 | – |
| `glossary_service` | 3 | – |
| `issue_service` | 5 | – |
| `requirement_service` | 3 | 2 (`decompose`, Batch-Writes) |
| `risk_service` | 4 | – |
| `stakeholder_need_service` | 3 | – |
| `workspace_service` | 5 | – |
| `test_service` / `test_run_service` | ✓ | – |
| `import_service` | – | 1 (Bulk-Import, ein TX pro Datei, REQ-L3-IMP-002) |
| `dlq_service` | – | 1 (atomarer DLQ-Move, REQ-021) |
| `event_bus` | – | 1 (Status-Update + Dispatch) |
| `workflow_facade` | – | 1 |

Dünne Wrapper (z. B. `requirement_service.derive_requirement`) tragen **keinen**
eigenen Wrapper — sie delegieren an eine bereits atomare Methode (`decompose`).
Das ist bewusst: eine geschachtelte `atomic()` würde nur einen Savepoint
erzeugen, ohne die Semantik zu verändern.

`trace_link_service.query_trace_links` und andere reine Read-Pfade laufen
bewusst ohne Transaktions-Wrapper (ADR-L3-AS005-02).

## Service-Layer-Grenzen (REQ-066, A-16, BE-10)

ReqFlow trennt HTTP-Concerns (`rest_api/`) strikt von Persistenz-Zugriff. Die
gewählte Ausprägung ist **Option B (Django-idiomatisch)** — kein hexagonaler
Repository-Layer über alle ORM-Call-Sites, sondern ORM-Zugriff gekapselt in
Application-/Domain-Services mit Custom Managern/QuerySets für wiederverwendete
oder komplexe Queries.

### Regeln

1. **`rest_api/` (ViewSets, APIViews):** KEIN direkter ORM-Zugriff.
   - Verboten: `Model.objects.*`, `Model.unscoped.*`, `from persistence.models
     import ...` in View-Dateien (`views.py`, `*_views.py`).
   - Ausnahme: Serializer-Validatoren und Choice-Felder in `serializers.py`
     dürfen Modelle referenzieren (Validierung ist kein Persistenz-Concern).
   - Views rufen ausschließlich Service-Methoden auf und übersetzen deren
     Domain-Exceptions (`ValidationError`, `NotFoundError`,
     `PermissionDeniedError`) via `_service_error_response` in HTTP-Codes.

2. **Application-Services (`application/`) und Domain-Services
   (`icd/services.py`, `diagram/services.py`, `auth_tenancy/services/*`):**
   dürfen ORM nutzen. Wiederverwendete/komplexe Queries (≥2 Nutzungsstellen,
   CTE, Aggregation, Bulk-Update, `unscoped`) gehören als benannte Methode in
   ein Custom-Manager/QuerySet unter `persistence/managers.py`.

3. **`unscoped` (tenant-übergreifend):** nur in Persistence-/Application-Layer
   und stets mit dokumentierter Begründung. NIE in `rest_api/`.

### Durchsetzung

Ein Ratchet-Guardrail-Test (`rest_api/tests/test_architecture.py`) zählt die
verbliebenen direkten ORM-Zeilen pro View-Datei gegen eine **schrumpfende
Allowlist** (`MAX_ORM_LINES`). Die Werte dürfen nur sinken, nie steigen — jeder
neue Verstoß bricht den Build. Ein Wert `0` (Datei nicht in der Allowlist)
bedeutet: vollständig sauber, muss so bleiben.

### Migrationsstand REQ-066

- **Phase 1 (Writes) — erledigt:** `AttributeVisibilityConfigService`,
  `CustomFieldService`, `SettingsService`, `UserProfileService` neu;
  `WorkspaceService.update_metadata`/Preset-Switch, `IcdService`/`DiagramService`
  um `get`/`delete` ergänzt. `settings_views.py` und `auth_views.py` sind damit
  ORM-frei.
- **Phase 2 (Reads) — offen:** `_resolve_artifact_titles` (views.py),
  Baseline-Titel-Helper (`unscoped`), RequirementViewSet-Allocations,
  ArtifactViewSet `unscoped`-Filter, Tenant/User-Lookup-Duplikate in
  `icd_views`/`diagram_views`/`diagram_canvas_views`.
- **Phase 3 (BE-10-Hotspots) — offen:** `RequirementQuerySet.with_artifact()`
  (6× dupliziertes `select_related("artifact").filter`), Entity-Typ-Auflösung
  in `trace_link_service`.

## Follow-up: Functional/Physical Architecture Separation (REQ-155)

**Status:** Proposed — Post-v1 / Follow-up. Zu groß für aktuellen Sprint (L-XL Aufwand).

ReqFlow speichert funktionale Architektur-Elemente (Funktionen, logische Blöcke,
Verhaltensdekomposition) und physische Architektur-Elemente (Komponenten,
Hardware-Items, physische Topologie) im gleichen `Artifact`-Typ ohne semantische
Unterscheidung. In der Systemtechnik sind das getrennte Sichten mit unterschiedlichen
Trace-Link-Typen ("allocates" von funktional → physisch).

### Technische Schulden

Das aktuelle Datenmodell (`persistence/models.py`) hat keinen
`architecture_domain`-Differenziator auf Architecture-Artefakten.
MBSE-Views (`BaselinesView`, `IcdView`) rendern funktionale und physische
Hierarchien in derselben Ansicht.

### Geplante Maßnahmen (Post-v1)

1. `architecture_domain`-Feld (Choices: `functional` / `physical`) zu
   Architecture-type Artifacts hinzufügen — additiv, backward-compatible (nullable).
2. `allocates`-TraceLink-Typ einführen — semantische Verbindung von funktionalen
   zu physischen Elementen (ergänzt die bestehenden Link-Typen in
   `persistence/models.py::VALID_LINK_TYPES`).
3. MBSE-Views aktualisieren: funktionale und physische Hierarchien separat
   rendern.

### Referenz

- Analyse: principal-developer QA Report 2026-07-17 (Rating M1 — Minor/Future)
- Anforderung: REQ-155 in `docs/REQUIREMENTS.md`
