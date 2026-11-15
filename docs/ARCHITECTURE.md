# ReqFlow — Architektur-Notizen

> Ergänzende Architektur-Dokumentation zur formalen SE-Hierarchie unter
> `docs/se/`. Diese Datei hält querschnittliche Konventionen fest, die nicht an
> eine einzelne Komponente gebunden sind.
>
> **Stand:** `1.9.0-beta.1` · **Letzte Aktualisierung:** 2026-11-15 ·
> **Datenquelle:** eigener Checkout von `origin/main` (`VERSION` 1.8.0-beta.29),
> Belege sind die im Text genannten Dateien — keine Aussage ohne gelesenen Code.

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
   schreibt den Outbox-Row inline, in derselben Transaktion wie die Mutation.
   Eine zurückgerollte Transaktion erzeugt daher niemals ein Event (REQ-L2-AS-029,
   REQ-L3-DEB-002). Die tatsächliche Zustellung an Subscriber erfolgt
   asynchron durch den OutboxPoller-Worker.

**Merksatz:** *Audit feuert im Commit, Outbox-Insertion erfolgt im Commit.*

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
| `bulk_update_service` | 1 (`apply`) | – (eine TX für 1–100 Einträge, alles oder nichts) |
| `dlq_service` | – | 1 (atomarer DLQ-Move, REQ-021) |
| `event_bus` | – | 1 (Status-Update + Dispatch) |
| `workflow_facade` | – | 1 |

Dünne Wrapper (z. B. `requirement_service.derive_requirement`) tragen **keinen**
eigenen Wrapper — sie delegieren an eine bereits atomare Methode (`decompose`).
Das ist bewusst: eine geschachtelte `atomic()` würde nur einen Savepoint
erzeugen, ohne die Semantik zu verändern.

`trace_link_service.query_trace_links` und andere reine Read-Pfade laufen
bewusst ohne Transaktions-Wrapper (ADR-L3-AS005-02).

### Schreibpfade der Dokumentansicht (ADR-026, Stand 1.9.0-beta.1)

Die bearbeitbare Dokumentansicht führt **keinen zweiten Schreibpfad** ein. Sie
zerlegt die Fläche in genau drei Layer-2-Bausteine:

| Baustein | Rolle | Transaktion |
|----------|-------|-------------|
| `application/document_reading_service.py` (`DocumentReadingService`, `DocumentViewResult`) | Lesedienst: Kopf, Kapitel, Markdown-Fassung, Schreiburteile je Feld. Schreibt nie. | – (reiner Read) |
| `application/document_edit_policy.py` (`resolve_field_permissions`, `EDITABLE_FIELDS_V1`) | Urteil je Feld in der Reihenfolge `PERMISSION` → `REPO_EXTERNAL` → `FIELD_FROZEN`; Rechte sind einschränkend, nie erweiternd. | – (pure Entscheidung) |
| `application/bulk_update_service.py` (`BulkUpdateService.apply`) | **Der einzige neue Schreibpfad** dieser Beta: 1–100 Einträge, eine Transaktion, alles oder nichts. | `@atomic_transaction` |

Regeln, die daraus folgen:

1. **Einzelfeld** geht unverändert über `DocumentService.update_document`
   (`PATCH /api/v1/documents/{id}/` mit `If-Match`). Der Bulk-Service ist kein
   Ersatz, sondern die Sammelvariante.
2. **Der Bulk-Service prüft nicht nach, was ein typisierter Dienst schon prüft.**
   Freeze, Change-Reason, Syntax und Optimistic Lock bleiben dort; im Batch
   geprüft werden nur die batch-eigenen Fragen (Form/Größe, Existenz +
   Workspace + bekannter Typ, Feldnamen im Update-Vertrag des Typs). Zwei
   Vorabprüfungen an zwei Orten würden irgendwann zwei Antworten liefern.
3. **Die Dispatch-Tabelle ist explizit** (`Document` → `DocumentService`,
   `Requirement` → `RequirementService`), nie der generische
   `ArtifactService`-Update — der kann Inhaltsfelder wie einen Dokument-`body`
   nicht schreiben.
4. **Ein Fehler schreibt nichts** und nennt den Eintrag über `index`; der Client
   markiert die Zeile, statt die Seite neu zu lesen.

## Dokumentansicht: „Sicht ist bearbeitbar, kein zweites Modell" (ADR-026)

ADR-026 (Nachtrag 2026-11-15) hält fest, dass die bearbeitbare Sicht **kein
zweites Modell** neben dem `Document`-Artefakt ist. Diese Aussage ist am Code
prüfbar und bleibt gültig:

- Es gibt **kein** `DocumentView`-Modell und keine Migration dafür; die Sicht
  liegt auf dem bestehenden `Document` (`persistence/models.py`).
- Kapitel sind **Textverarbeitung** des Markdown-`body`
  (`application/markdown_chapters.py`), kein Katalog von Kapitel-Entitäten und
  keine artefakt-übergreifenden Kapitel.
- Die Sicht zeigt und schreibt nur Felder, die das `Document` ohnehin besitzt;
  `kind` ist bewusst nicht Teil von `EDITABLE_FIELDS_V1` (Klassifikation, kein
  Inhalt).
- Struktur (Verschieben, Allokieren) ändert sie nie — dafür sind Bäume und
  Verbindungsansicht zuständig.

## Verbindungsansicht: Renderer, Selektion, Geometrie (Frontend)

Die Verbindungsansicht ist eine **Lesehilfe mit Schreibzugriff nur über die
bestehenden Endpunkte**. Vier Bausteine tragen den Modus `trees`:

| Datei | Verantwortung |
|-------|---------------|
| `frontend/src/components/ConnectionView/allocation-trees.ts` | Baumaufbau beider Spalten und die Allokationskanten als reine Funktionen — kein React, kein DOM. |
| `frontend/src/components/ConnectionView/AllocationTreesRenderer.tsx` | Rendert die zwei Bäume, das Kanten-Overlay und die Zeilenaktionen; ein gemeinsamer Scroll-Container, keine Scroll-Synchronisation. |
| `frontend/src/components/ConnectionView/edge-geometry.ts` | Misst gemountete Zeilen und rechnet sie in SVG-Pfade um; ein zugeklappter Zweig zeichnet deshalb bewusst keine Kante. |
| `frontend/src/components/ConnectionView/useAllocationSelection.ts` | Auswahl und Sperr-Zustand der Zeilen — eine Wahrheit für beide Bäume und die Aktionsleiste. |

Der Modus ist eine **reine Sicht-Präferenz**: `view` steht in der URL (Default
`trees` schreibt keinen Parameter, `?view=tree` bleibt als Alias auf
`architecture` gültig), die Kanten-Sichtbarkeit in der Nutzer-Präferenz
`ui.connection_view.show_edges`.

**Präferenz-Schreibpfad:** Nutzer-Präferenzen werden per `PATCH` mit
`keepalive: true` geschrieben (`frontend/src/api/client.ts`,
`preference-values.ts`), damit ein Reload mitten im Klick die Änderung nicht
verliert, und durch `frontend/src/api/preference-write-queue.ts` serialisiert
(Last-Click-Wins). Ein fehlgeschlagenes Schreiben meldet einen Fehler und lässt
den lokalen Zustand stehen; einen localStorage-Fallback gibt es nicht mehr.

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
