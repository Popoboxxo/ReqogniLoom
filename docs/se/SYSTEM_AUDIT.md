# System Audit — ReqFlow

## 1. Executive Summary

- **Datum:** 2026-07-13
- **Scope:** Backend-Vollstack von ReqFlow — Datenmodell (Django Models aller Apps), Service-Layer (`backend/application/`), REST-API-Schicht (`backend/rest_api/`, DRF), MCP-Server (`backend/mcp_server/`).
- **Methodik:** Statische Code-Analyse, read-only. Vier parallele Explorer-Durchläufe je Schicht. Keine Laufzeit-/Lasttests, keine dynamische Instrumentierung. Datei- und Zeilenreferenzen beziehen sich auf den Stand des Branch `feat/frontend-feedback-cluster-a`.
- **Nicht im Scope:** Frontend (React/TypeScript), E2E-Tests, Infrastruktur/Docker, LLM-Provider-interne Logik.

### Top-5-Findings (schwerwiegendste Probleme über alle Schichten)

| Rang | ID | Schwere | Kurzbeschreibung |
|------|------|---------|------------------|
| 1 | **P-01** | KRITISCH | API-Key wird im MCP-Server im Klartext auf ERROR-Level geloggt (`mcp_server/views.py:59-62`) — Secret-Leak in Log-Aggregation. |
| 2 | **P-02** | KRITISCH | API-Key wird in die SSE-Endpoint-URL geschrieben (`mcp_server/views.py:219`) — erscheint in Access-Logs / Proxy-Logs. |
| 3 | **A-01** | KRITISCH | `ApiKeyViewSet.destroy` ohne Ownership-Check → IDOR: fremde API-Keys löschbar (`rest_api/api_key_views.py`). |
| 4 | **S-03** | KRITISCH | `StakeholderNeedService.create()` ohne Permission-Check → Tenant-/Rollen-Bypass beim Anlegen von Needs. |
| 5 | **S-01 / S-02** | KRITISCH | `DomainEventBus.poll_and_dispatch()` Race-Condition und nicht-atomarer DLQ-Move → Event-Doppelverarbeitung / -Verlust. |

Gemeinsamer Nenner der Top-5: **fehlende Autorisierungs- und Vertraulichkeits-Kontrollen** an den Systemgrenzen (MCP + REST) sowie **fehlende Transaktions-/Nebenläufigkeits-Garantien** im Event-Backbone.

### Gesamt-Bewertung (Ampel pro Schicht)

| Schicht | Ampel | Begründung |
|---------|:-----:|------------|
| Datenmodell | 🟡 GELB | Solide Abstraktions-Hierarchie und Multi-Tenancy-Basis, aber mehrere Modelle ohne Tenant-FK/Isolation, fehlende Indizes, doppelter Audit-Log, ausstehende Migration. |
| Service-Layer | 🔴 ROT | Vier kritische Befunde (Event-Bus-Nebenläufigkeit, fehlender Permission-Check, kaputter Clone-Fix). Kern-Geschäftslogik betroffen. |
| REST-API | 🟡 GELB | Ein kritisches IDOR-Finding, mehrere Queryset-/Pagination-Defekte und Stub-Endpoints im Router. Basiskonfiguration solide. |
| MCP-Server | 🔴 ROT | Zwei kritische Secret-Leaks plus fehlendes RBAC/Audit auf mehreren Write-Tools. Transport-Schicht sicherheitskritisch. |

**Gesamt: 🔴 ROT** — Die kritischen Secret-Leaks (P-01, P-02) und das IDOR (A-01) sind vor jedem produktiven Betrieb zu schließen.

---

## 2. Datenmodell-Audit (Django Models — alle Apps)

### 2.1 Übersicht Modell-Inventar

| App | Zentrale Modelle | Tenant-scoped | Auditable |
|-----|------------------|:-------------:|:---------:|
| `persistence` | `Requirement`, `StakeholderNeed`, `ArchitectureElement`, `Artifact`, `TraceLink`, `WorkflowState`, `AuditLogEntry` | überwiegend | teils |
| `auth_tenancy` | `Tenant`, `User`, `Role`, `Membership` | n/a (Root) | ja |
| `presets` | `PresetDefinition`, `TerminologyProfile`, `AttributeVisibilityConfig` | teils | nein |
| `audit` | `AuditEntry` | ja | n/a |
| `baseline` | `Baseline`, `BaselineItem` | ja | ja |
| `traceability` | `TraceLink` (Query-Sicht), Report-Modelle | ja | teils |
| `workflow` | `WorkflowDefinition`, `WorkflowState`, Legacy-State-Tabellen | teils | teils |
| `diagram` | `Diagram`, `DiagramElement` | ja | nein |
| `icd` | `InterfaceControlDocument`, `Adr`, `Risk`, `Issue` | **teils fehlend** | teils |
| `se_metrics` | `MetricCache`, `WorkspaceThresholdConfig` | **fehlend** | nein |
| `test_runs` | `TestRun`, `TestRunResult` | ja | teils |
| (events) | `DomainEvent`, `DomainEventOutbox`, `DomainEventDLQ`, `WebhookSubscription` | **teils fehlend** | nein |

### 2.2 Abstraktions-Hierarchie

```
models.Model
  └── TenantScopedModel          (persistence/) — tenant-FK + Manager mit RLS-Filter
        └── AuditableModel        (persistence/) — created/updated by/at, soft-delete
              └── Requirement, StakeholderNeed, ArchitectureElement, Artifact, ...
```

- Grundmuster ist sauber: Row-Level-Security wird über `TenantScopedModel` und einen Default-Manager erzwungen, `AuditableModel` ergänzt Audit-Felder und Soft-Delete.
- **Bruchstellen:** Mehrere jüngere Modelle (`Adr`, `Risk`, `Issue`, `DomainEvent*`, `WebhookSubscription`, `MetricCache`, `WorkspaceThresholdConfig`) erben **nicht** von `TenantScopedModel` und umgehen damit die RLS-Isolation.

### 2.3 Befunde

**M-01 (HOCH) — Fehlende Tenant-Isolation bei mehreren Modellen.**
`Adr`, `Risk`, `Issue` (`icd/`), `DomainEvent`, `DomainEventOutbox`, `DomainEventDLQ`, `WebhookSubscription` (Events), `MetricCache`, `WorkspaceThresholdConfig` (`se_metrics/`) erben nicht von `TenantScopedModel` bzw. besitzen keinen Tenant-FK. Cross-Tenant-Lecks bei Queries ohne manuellen Filter möglich.
*Maßnahme:* Tenant-FK ergänzen und auf `TenantScopedModel` migrieren; wo Datensätze bewusst global sind, explizit dokumentieren.

**M-02 (HOCH) — Ausstehende Migration 0029.**
`backend/persistence/migrations/0029_add_lifecycle_status_requirement_stakeholderneed.py` ist im Working-Tree **untracked** (nicht committet), während die Folgemigrationen 0030–0032 bereits existieren und darauf aufbauen. Ohne Commit ist die Migrationskette in frischen Checkouts inkonsistent.
*Maßnahme:* Migration committen (oder squashen), Kette 0029→0032 auf frischer DB prüfen.

**M-03 (MITTEL) — N+1-Risiko in `ArchitectureElement.get_level()`.**
Die Level-Ableitung (L0…L4) traversiert die Parent-Kette per Einzelquery pro Ebene. Bei Listenrendering vieler Elemente entsteht ein N+1-Muster.
*Maßnahme:* Level materialisieren (denormalisiertes Feld, per Signal/Service gepflegt) oder Pfad-Cache (`path`/`depth`-Spalte).

**M-04 (MITTEL) — Fehlende `uid`-Indizes.**
`Requirement.uid`, `StakeholderNeed.uid`, `ArchitectureElement.uid` werden für Lookups genutzt, tragen aber keinen DB-Index. Bei wachsenden Tabellen degradiert die Lookup-Performance.
*Maßnahme:* `db_index=True` bzw. zusammengesetzten Index `(tenant, uid)` ergänzen.

**M-05 (MITTEL) — Duale Workflow-Tabellen (Legacy-Redundanz).**
`workflow/` führt neben der aktuellen State-Machine noch Legacy-State-Tabellen. Doppelte Wahrheitsquelle für den Workflow-Zustand.
*Maßnahme:* Legacy-Tabellen deprecaten, Datenmigration in die aktuelle Struktur, Alt-Tabellen entfernen.

**M-06 (MITTEL) — Doppelter Audit-Log.**
Es existieren `persistence.AuditLogEntry` und `audit.AuditEntry` parallel. Uneinheitliche Audit-Wahrheit, doppelte Schreibpfade.
*Maßnahme:* Auf ein Audit-Modell konsolidieren (`audit.AuditEntry` als operativ führend), das andere deprecaten.

**M-07 (NIEDRIG) — `AttributeVisibilityConfig` Feldduplizierung.**
Sichtbarkeits-Attribute werden redundant gehalten (mehrfache Ablage derselben Konfigurationsdimension).
*Maßnahme:* Auf eine normalisierte Darstellung reduzieren.

**M-08 (NIEDRIG) — `unique_together` (seit Django 4.2 deprecated).**
Mehrere Modelle nutzen `unique_together` in der Meta-Klasse. Django 4.2 empfiehlt `UniqueConstraint` in `Meta.constraints`.
*Maßnahme:* Auf `constraints = [UniqueConstraint(...)]` umstellen.

**M-09 (NIEDRIG) — `WebhookSubscription.event_types` als CSV-String.**
Event-Typen werden als kommaseparierter String persistiert statt relational/als Array. Kein referenzieller Schutz, umständliche Filter.
*Maßnahme:* `ArrayField` (Postgres) oder Join-Tabelle.

**M-10 (NIEDRIG) — `DomainEventDLQ` fehlende Indizes.**
Die Dead-Letter-Queue wird nach Status/Zeit abgefragt, trägt aber keine passenden Indizes.
*Maßnahme:* Index auf `(status, created_at)` bzw. Retry-Felder.

**M-11 (NIEDRIG) — `TraceLink` fehlender Einzel-Index auf `target`.**
Rückwärtssuchen (eingehende Links) treffen keinen Index auf der Zielspalte.
*Maßnahme:* Index auf `target` (bzw. `(tenant, target)`) ergänzen; siehe auch S-13.

**M-12 (NIEDRIG) — `GlossaryTermVersion` fehlende `__str__`.**
Kein menschenlesbares Repr → schlechte Admin-/Log-Darstellung.
*Maßnahme:* `__str__` ergänzen.

### 2.4 Positive Patterns

- Konsequente Basis-Hierarchie `TenantScopedModel → AuditableModel` als Fundament für Multi-Tenancy und Auditierbarkeit.
- Soft-Delete-Standard über `AuditableModel` (dort wo genutzt).
- Klare Trennung von Persistenz (`persistence/`) und fachlichen Erweiterungs-Apps (`icd/`, `se_metrics/`, `diagram/`).
- Baselines mit dediziertem Item-Modell für reproduzierbare Snapshots.

---

## 3. Service-Layer-Audit (backend/application/)

### 3.1 Modul-Übersicht

Der Service-Layer ist der einzige legitime Einstiegspunkt zwischen API/MCP und Persistenz (19 Domain-Services). Betroffene Module dieses Audits: `domain_event_bus`, `stakeholder_need_service`, `workspace_service`, `trace_link_service`, `import_service`, `export_service`, `search_service`, `preset_policy_service`, `ai_derivation_service`, `webhook_dispatcher`, `requirement_service`, `artifact_service`, `dlq_service`.

### 3.2 Befunde

**S-01 (KRITISCH) — `DomainEventBus.poll_and_dispatch()` Race-Condition.**
Poll und Statuswechsel des Outbox-Eintrags erfolgen nicht unter Row-Lock/atomarer Claim-Semantik. Bei mehreren Worker-Prozessen (Celery) kann derselbe Event doppelt dispatcht werden.
*Maßnahme:* `select_for_update(skip_locked=True)` innerhalb `transaction.atomic()` zum atomaren Claim; oder Outbox-Pattern mit eindeutigem Claim-Token.

**S-02 (KRITISCH) — `DomainEventBus` DLQ-Move nicht atomar.**
Das Verschieben eines fehlgeschlagenen Events aus der Outbox in die DLQ ist nicht in einer Transaktion gekapselt. Absturz zwischen Schreiben (DLQ) und Löschen/Markieren (Outbox) führt zu Doppel- oder Verlustzustand.
*Maßnahme:* DLQ-Insert und Outbox-Update in eine `transaction.atomic()`-Klammer.

**S-03 (KRITISCH) — `StakeholderNeedService.create()` ohne Permission-Check.**
`create()` prüft weder Rolle noch Tenant-Berechtigung des Aufrufers. Kombiniert mit P-03/P-04 (MCP ohne RBAC/Audit) ist das Anlegen von Needs unautorisiert möglich.
*Maßnahme:* Permission-Check (Rolle + Workspace/Tenant) am Service-Eingang; konsistent mit `RequirementService`. Siehe auch S-10.

**S-04 (KRITISCH) — `WorkspaceService.clone_workspace()` Hierarchie-Fix broken.**
Beim Klonen wird die Parent-Beziehung anhand `arch.id` neu verdrahtet — zu diesem Zeitpunkt ist `arch.id` jedoch bereits die **neue** ID des geklonten Elements. Die Alt→Neu-Zuordnung greift ins Leere, Hierarchie im Klon ist falsch/flach.
*Maßnahme:* Explizite `old_id → new_instance`-Map während des Klonens aufbauen und Parent-Wiring über diese Map auflösen. Test mit ≥2 Ebenen Tiefe.

**S-05 (HOCH) — `TraceLinkService` Suspect-Propagation deaktiviert bei `direction="outgoing"`.**
Für ausgehende Links wird die Suspect-Markierung nicht propagiert → geänderte Quellartefakte markieren abhängige Ziele nicht als „suspect".
*Maßnahme:* Propagation richtungsunabhängig entlang der Link-Semantik implementieren; Regressionstest je Richtung.

**S-06 (HOCH) — `ImportService`: importierte Requirements ohne `WorkflowState`.**
CSV-importierte Requirements erhalten keinen initialen Workflow-State → sie fallen aus Workflow-getriebenen Queries/Übergängen heraus.
*Maßnahme:* Initial-State beim Import gemäß aktivem Preset setzen.

**S-07 (HOCH) — `ExportService`: soft-deleted Entities in Exporten enthalten.**
Der Export umgeht den Soft-Delete-Filter → gelöschte Datensätze erscheinen in Reports/Exports.
*Maßnahme:* Export-Querysets über den Default-Manager (Soft-Delete-gefiltert) führen; explizit begründete Ausnahmen kennzeichnen.

**S-08 (HOCH) — `SearchService`: Query-Operatoren ignoriert.**
Verwendung von `plainto_tsquery` statt `to_tsquery` → boolesche Operatoren (AND/OR/NOT) der Nutzeranfrage werden literal behandelt statt ausgewertet.
*Maßnahme:* Auf `websearch_to_tsquery` (Postgres) umstellen (unterstützt Operator-Syntax sicher) oder `to_tsquery` mit sauberer Eingabevalidierung.

**S-09 (HOCH) — `PresetPolicyService.validate_transition_roles()` nutzt `tenant_id` statt `workspace_id`.**
Rollen-Policies werden auf Tenant- statt Workspace-Ebene aufgelöst → falsche Berechtigungsentscheidung bei workspace-spezifischen Rollen.
*Maßnahme:* Scoping auf `workspace_id` korrigieren; Test mit divergierenden Tenant-/Workspace-Rollen.

**S-10 (MITTEL) — `StakeholderNeedService._set_tenant_context()` fehlt in `update()`/`delete()`.**
Der Tenant-Kontext wird nur bei `create()` gesetzt, nicht bei `update()`/`delete()` → RLS-Filter greift dort ggf. nicht.
*Maßnahme:* `_set_tenant_context()` in allen mutierenden Methoden aufrufen; siehe [[project-stakeholderneedservice-outbox-bug]] für begleitende Outbox-Problematik.

**S-11 (MITTEL) — `AiDerivationService` Silent Mock-Fallback ohne WARNING-Log.**
Fällt ohne API-Key still auf den Mock-Provider zurück, ohne Log. Nutzer erhält Mock-Daten in dem Glauben, echte LLM-Ergebnisse zu sehen.
*Maßnahme:* `logger.warning` beim Fallback; im Response-Payload Provider kennzeichnen.

**S-12 (MITTEL) — `WebhookDispatcher` synchrone HTTP-Calls (TODO-ASYNC).**
Webhook-Zustellung erfolgt synchron im Request-/Dispatch-Pfad → langsame/gestörte Empfänger blockieren den Aufrufer.
*Maßnahme:* Zustellung in Celery-Task auslagern, mit Retry/Timeout (siehe Abschnitt 6).

**S-13 (MITTEL) — `TraceLinkService` N+1 in `get_allocation_coverage()`.**
Coverage-Berechnung lädt Links/Ziele einzeln pro Element.
*Maßnahme:* `select_related`/`prefetch_related` bzw. Aggregat-Query; unterstützt durch Index aus M-11.

**S-14 (MITTEL) — `SearchService` In-Memory-Pagination.**
Vollständiges Result-Set wird geladen und erst in Python paginiert → Speicher-/Latenzproblem bei großen Treffermengen.
*Maßnahme:* DB-seitige `LIMIT/OFFSET` bzw. Keyset-Pagination.

**S-15 (MITTEL) — `PresetPolicyService` Cache nicht multi-process.**
Policy-Cache liegt im Prozess-Speicher → Inkonsistenz zwischen Gunicorn-Workern/Celery bei Policy-Änderungen (siehe Abschnitt 6).
*Maßnahme:* Redis-basierter Shared-Cache mit Invalidierung.

**S-16 (NIEDRIG) — `RequirementService` Soft-Delete ohne TraceLink-Cascade.**
Beim Soft-Delete eines Requirements bleiben verwaiste TraceLinks bestehen.
*Maßnahme:* TraceLinks mitmarkieren (soft) oder als „dangling" kennzeichnen.

**S-17 (NIEDRIG) — Hard-Delete vs. Soft-Delete inkonsistent.**
`ArtifactService` löscht hart, `RequirementService` weich → uneinheitliches Löschverhalten (siehe Abschnitt 6).
*Maßnahme:* Projektweite Löschstrategie festlegen und durchsetzen.

**S-18 (NIEDRIG) — `TraceLinkService` Exception-Remapping via String-Matching.**
Fehlerklassifizierung anhand von Exception-Message-Strings → brüchig gegenüber Formulierungsänderungen.
*Maßnahme:* Typisierte Exceptions (eigene Exception-Hierarchie) statt String-Matching.

**S-19 (NIEDRIG) — `PresetPolicyService.get_policy("scope_allowed")` gibt `None`.**
Der Schlüssel liefert `None` statt einer definierten Policy → stiller Fehlpfad bei Aufrufern.
*Maßnahme:* Definierten Default zurückgeben oder explizit `KeyError`/Validierung.

**S-20 (NIEDRIG) — `dlq_service.py` ohne Testdatei.**
Keine dedizierten Tests für die DLQ-Verarbeitung — kritischer Pfad (siehe S-02) untestet.
*Maßnahme:* Test-Modul für DLQ-Move, Retry, Idempotenz ergänzen.

### 3.3 Test-Coverage-Matrix

| Service-Modul | Tests vorhanden | Kritische Pfade abgedeckt | Lücke |
|---------------|:---------------:|:-------------------------:|-------|
| `domain_event_bus` | teils | nein | Race-Condition (S-01), atomarer DLQ-Move (S-02) untestet |
| `stakeholder_need_service` | ja | teils | Permission-Check (S-03), Tenant-Kontext update/delete (S-10) |
| `workspace_service` | ja | ja | Clone-Hierarchie ≥2 Ebenen (S-04) — abgedeckt durch `TestCloneWorkspaceHierarchy` |
| `trace_link_service` | ja | teils | Suspect-Propagation je Richtung (S-05), Coverage-N+1 (S-13) |
| `import_service` | teils | nein | Initial-WorkflowState (S-06) |
| `export_service` | teils | nein | Soft-Delete-Filter (S-07) |
| `search_service` | teils | nein | Operator-Parsing (S-08), Pagination (S-14) |
| `preset_policy_service` | ja | teils | Workspace-Scoping (S-09) |
| `ai_derivation_service` | teils | teils | Mock-Fallback-Signal (S-11) |
| `webhook_dispatcher` | teils | nein | Async/Timeout (S-12) |
| `dlq_service` | **nein** | **nein** | vollständig (S-20) |

---

## 4. API-Schicht-Audit (Django REST Framework)

### 4.1 Basis-Konfiguration

- DRF mit JWT-Auth, OpenAPI via `drf-spectacular`. 16 ViewSets + 2 APIViews unter `/api/v1/`.
- Globale FilterBackends konfiguriert; Standard-Pagination aktiv.
- Positiv: einheitlicher Router, zentrale Auth, konsistentes Error-Response-Grundgerüst (`build_error_response()`).
- Schwachpunkt-Muster: Querysets teils ohne Tenant-/Workspace-Scoping durchgereicht; Performance-Helfer definiert, aber nicht angewandt; einzelne Router-Routen zeigen auf Stub-/nicht-implementierte Actions.

### 4.2 Befunde

**A-01 (HOCH / SICHERHEIT) — `ApiKeyViewSet.destroy`: IDOR, kein Ownership-Check.**
`backend/rest_api/api_key_views.py` — `destroy` löscht anhand PK ohne Prüfung, ob der Key dem aufrufenden User/Tenant gehört → fremde API-Keys löschbar.
*Maßnahme:* Queryset auf `request.user`/Tenant filtern; bei Fremdzugriff 404 (nicht 403, um Existenz nicht zu leaken).

**A-02 (HOCH) — `DiagramViewSet.list`: `workspace_id` required, aber Queryset ignoriert sie.**
`backend/rest_api/diagram_views.py` — der Pflichtparameter `workspace_id` wird validiert, aber nicht auf das Queryset angewandt → Diagramme fremder Workspaces sichtbar.
*Maßnahme:* Queryset per `workspace_id` (und Tenant) filtern.

**A-03 (HOCH) — `IcdViewSet.destroy`: `ALTER TABLE ... DISABLE TRIGGER` im Request-Handler.**
`backend/rest_api/icd_views.py` — deaktiviert im Löschpfad DB-Trigger via DDL im laufenden Request. DDL im Request-Handler ist transaktions-/RLS-gefährdend und kann Isolation projektweit aushebeln.
*Maßnahme:* DDL entfernen; Löschreihenfolge/Constraints über ORM-Cascade oder `SET CONSTRAINTS DEFERRED` in Transaktion lösen — niemals Trigger request-seitig abschalten.

**A-04 (MITTEL) — `QUERYSET_OPTIMIZATIONS` definiert, aber nie angewandt.**
Eine zentrale Optimierungs-Map existiert, wird jedoch in keinem ViewSet auf `get_queryset()` angewandt → N+1 bei praktisch allen Listen-Endpoints.
*Maßnahme:* Map konsequent via `select_related`/`prefetch_related` in `get_queryset()` verdrahten.

**A-05 (MITTEL) — `StakeholderNeedViewSet.list`: KeyError über `/api/v1/needs/`.**
Aufruf über die Router-Route `/needs/` löst einen `KeyError` aus (fehlender erwarteter Kontext-/Lookup-Key).
*Maßnahme:* Fehlenden Key defensiv behandeln; Test für den Router-Pfad.

**A-06 (MITTEL) — `TestRunViewSet.results` unpaginiert.**
Die `results`-Action liefert alle Ergebnisse ohne Pagination → große Antworten.
*Maßnahme:* Standard-Pagination auf die Custom-Action anwenden.

**A-07 (MITTEL) — `TraceLinkViewSet.retrieve`: permanent 404 (Stub).**
`retrieve` ist als Stub implementiert und liefert immer 404, ist aber im Router sichtbar.
*Maßnahme:* Implementieren oder Action aus dem Router entfernen und OpenAPI angleichen.

**A-08 (MITTEL) — `WorkflowDefinitionViewSet` `list`/`retrieve` nicht implementiert, aber im Router sichtbar.**
Router exponiert Routen, die nicht funktionieren → irreführende API-Oberfläche/OpenAPI.
*Maßnahme:* Implementieren oder Routen entfernen.

**A-09 (MITTEL) — `AttributeVisibilityConfigViewSet.list`: Pagination umgangen.**
Liefert direkt ohne Pagination.
*Maßnahme:* Auf Standard-Pagination zurückführen.

**A-10 (NIEDRIG) — FilterBackends global, aber `search_fields`/`ordering_fields` nirgends deklariert.**
Globale Filter-/Such-/Ordering-Backends greifen mangels Feld-Deklaration nirgends → tote Konfiguration.
*Maßnahme:* Pro ViewSet `search_fields`/`ordering_fields` deklarieren oder Backends gezielt setzen.

**A-11 (NIEDRIG) — Kein `@extend_schema` auf Custom-Actions.**
Custom-Actions fehlen in der OpenAPI-Spezifikation bzw. sind untypisiert.
*Maßnahme:* `@extend_schema` mit Request/Response-Serializern ergänzen.

**A-12 (NIEDRIG) — `COMMON_ERROR_RESPONSES` definiert, nirgends verwendet.**
Zentrale Error-Response-Definition ungenutzt → OpenAPI ohne einheitliche Fehlerdoku.
*Maßnahme:* In `@extend_schema(responses=...)` einbinden.

**A-13 (NIEDRIG) — `WorkspaceViewSet` Admin-Actions ohne `permission_classes`.**
Admin-Actions erben nur globale Permissions, keine action-spezifische Härtung.
*Maßnahme:* Explizite `permission_classes` je Admin-Action.

**A-14 (NIEDRIG) — HTTP 405/403-Inkonsistenz für immutable-resource-Ablehnung.**
Ablehnung unveränderlicher Ressourcen mal 405, mal 403 → uneinheitliche Client-Semantik.
*Maßnahme:* Einheitlichen Status festlegen (empfohlen 405 für unerlaubte Methode, 403 nur für Berechtigung).

**A-15 (NIEDRIG) — `ApiKeyViewSet` Error-Format weicht von `build_error_response()` ab.**
Eigenes Fehlerformat statt Projektstandard.
*Maßnahme:* Auf `build_error_response()` vereinheitlichen.

**A-16 (NIEDRIG) — Direktes ORM in ViewSets statt über Service.**
Vereinzelt greifen ViewSets direkt auf `persistence.models` zu (verstößt gegen die Layer-Regel Service-only).
*Maßnahme:* Über `application/`-Services führen.

---

## 5. MCP-Server-Audit

### 5.1 Transport-Schicht

- JSON-RPC 2.0 unter `/mcp/`, Transporte HTTP, SSE, stdio. 11 Tool-Gruppen mit 40+ Tools. Auth via API-Key `rfk_*` (Header `X-API-Key`/`Authorization`, zusätzlich Query-Param `api_key` als Fallback).
- Sicherheitskritisch: Auth-Extraktion, SSE-Session-Handling und Tool-Autorisierung sind die zentralen Angriffsflächen. Zwei kritische Secret-Leaks und mehrere RBAC-/Audit-Lücken (siehe unten).

### 5.2 Befunde

**P-01 (KRITISCH) — API-Key-Klartext-Logging auf ERROR-Level.**
`backend/mcp_server/views.py:59-62` — drei `logger.error(f"DEBUG ...")`-Zeilen loggen die vollständigen Auth-Header inkl. API-Key und den Query-Param im Klartext. Landet in jeder Log-Aggregation. Es handelt sich zudem um vergessenen Debug-Code.
*Maßnahme:* Debug-Log-Zeilen ersatzlos entfernen. Falls Diagnose nötig: nur maskierte Präfixe (`rfk_…xxxx`) auf DEBUG-Level.

**P-02 (KRITISCH) — API-Key in SSE-Endpoint-URL.**
`backend/mcp_server/views.py:219` — der API-Key wird als Query-Param an die SSE-`endpoint`-URL (`/mcp/messages/?session_id=…&api_key=…`) angehängt und an den Client zurückgegeben. Erscheint in Server-Access-Logs, Reverse-Proxy-Logs und Browser-History.
*Maßnahme:* Key nicht in die URL schreiben. Session serverseitig an die authentifizierte Verbindung binden (Session-Token statt Key im Query-String).

**P-03 (HOCH) — RBAC fehlt für Writes von `needs.*`, `adr.*`, `risk.*`, `issue.*`, `glossary.*`.**
`backend/mcp_server/tool_registry.py` — diese Write-Tools prüfen keine Rolle/Berechtigung → jeder gültige API-Key darf schreiben (korreliert mit S-03).
*Maßnahme:* Einheitlichen RBAC-Gate für alle mutierenden Tools; Rollen aus Membership/Preset-Policy.

**P-04 (HOCH) — Kein Audit auf `needs.create`, `needs.update`.**
Diese Mutationen erzeugen keinen Audit-Eintrag → Lücke im Audit-Trail.
*Maßnahme:* Audit-Hook im Service (siehe M-06 Konsolidierung) für alle Need-Mutationen.

**P-05 (HOCH) — Param-Name-Inkonsistenz `requirement.decompose`/`validate`.**
Tool-Schema deklariert `id`, der Handler erwartet `requirement_id` (oder umgekehrt) → Aufrufe schlagen fehl bzw. Parameter wird verworfen.
*Maßnahme:* Schema und Handler auf einen Namen angleichen; Contract-Test.

**P-06 (HOCH) — JSON-RPC-Error-Format non-standard.**
Fehler liefern einen String-`error_code` statt des laut JSON-RPC 2.0 vorgeschriebenen Integer-`code` im `error`-Objekt.
*Maßnahme:* Auf `{"code": <int>, "message": <str>, "data": …}` gemäß Spezifikation umstellen.

**P-07 (MITTEL) — TOCTOU Race Condition bei `user.create`.**
Existenzprüfung und Anlage sind nicht atomar → Doppelanlage/Constraint-Fehler bei parallelen Aufrufen.
*Maßnahme:* Atomar via `get_or_create`/`UniqueConstraint` + Fehlerbehandlung.

**P-08 (MITTEL) — HTTP 401 für `PARSE_ERROR`/`INVALID_REQUEST`.**
Malformte Requests werden mit 401 beantwortet, obwohl es kein Auth-Problem ist (korrekt: 400).
*Maßnahme:* 400 für Parse-/Request-Fehler, 401 ausschließlich für Auth.

**P-09 (MITTEL) — `artifact.search` `limit` ohne Bounds-Check.**
Kein Maximum → unbegrenzt großer Fetch möglich (DoS-Vektor).
*Maßnahme:* Oberes Limit erzwingen (z.B. ≤ 200) und validieren.

**P-10 (MITTEL) — Kein Input-Schema für `StakeholderNeedsToolGroup` und `GenericCrudToolGroup`.**
Fehlende Schema-Validierung → unvalidierte Eingaben erreichen den Service.
*Maßnahme:* JSON-Schema je Tool definieren und vor Dispatch validieren.

**P-11 (NIEDRIG) — Threading ohne Pool-Limit in `McpMessagesView`.**
Unbegrenzte Thread-Erzeugung pro Nachricht → Ressourcenerschöpfung möglich.
*Maßnahme:* Begrenzter Thread-Pool/Executor.

**P-12 (NIEDRIG) — Preset-Cache nur in-process.**
Wie S-15/A-Ebene: kein Shared-Cache über Prozesse (siehe Abschnitt 6).
*Maßnahme:* Redis-Cache.

**P-13 (NIEDRIG) — CORS Allowlist fehlt (Origin spiegeln).**
Der `Origin`-Header wird reflektiert statt gegen eine Allowlist geprüft.
*Maßnahme:* Explizite Origin-Allowlist konfigurieren.

**P-14 (NIEDRIG) — `admin.backup_list` In-Memory-Filter nach DB-Fetch.**
Vollständiger Fetch, dann Filter in Python.
*Maßnahme:* DB-seitig filtern.

**P-15 (NIEDRIG) — Kein Rate-Limiting auf MCP-Endpunkten.**
Siehe Abschnitt 6.
*Maßnahme:* Rate-Limit pro API-Key.

**P-16 (NIEDRIG) — SSE-Endpoint ohne Auth-Prüfung beim Verbindungsaufbau.**
Die SSE-Verbindung wird geöffnet; Auth wird erst beim POST auf `/mcp/messages/` validiert → offene Verbindungen ohne gültigen Key möglich.
*Maßnahme:* Auth bereits beim SSE-Connect prüfen (verschärft durch P-02).

---

## 6. Schicht-übergreifende Muster

**X-01 — Inkonsistenz Hard-Delete vs. Soft-Delete.**
`ArtifactService` löscht hart, `RequirementService` weich (S-17); TraceLinks werden bei Soft-Delete nicht mitbehandelt (S-16); Exporte enthalten soft-deleted Daten (S-07). → Uneinheitliche Löschsemantik quer über Service- und API-Schicht.
*Maßnahme:* Projektweite Löschstrategie definieren (Standard: Soft-Delete mit Cascade-Regeln), Exporte/Queries konsequent filtern.

**X-02 — In-Memory-Caches nicht multi-process.**
Preset-Policy-Cache im Service (S-15), im MCP-Server (P-12) und implizit auf API-Ebene liegen prozesslokal → Inkonsistenz zwischen Gunicorn-Workern und Celery bei Konfigurations-/Policy-Änderungen.
*Maßnahme:* Zentraler Redis-Cache mit Invalidierungs-Events.

**X-03 — LLM-Aufrufe ohne Timeout.**
`AiDerivationService` und `RequirementService` rufen LLM-Provider ohne Timeout/Retry-Budget (verbunden mit Silent-Mock-Fallback S-11).
*Maßnahme:* Timeout + begrenzter Retry über die `resilience/`-App (Circuit-Breaker); Fallback sichtbar loggen.

**X-04 — Keine Rate-Limits (REST-API + MCP).**
Weder REST noch MCP begrenzen Aufrufraten (P-15, A-Ebene) → DoS-/Abuse-Vektor, verstärkt durch fehlende Bounds-Checks (P-09).
*Maßnahme:* Rate-Limiting pro API-Key/User (DRF-Throttling + MCP-Throttle-Middleware).

**X-05 — Autorisierung nicht durchgängig am Service-Eingang.**
Permission-Checks fehlen teils im Service (S-03) und werden von MCP/REST nicht kompensiert (P-03, A-01) → Defense-in-Depth nicht gegeben.
*Maßnahme:* Autorisierung als Pflicht-Gate am Service-Eingang, unabhängig vom Aufrufer (REST/MCP).

---

## 7. Maßnahmen-Backlog

Sortierung: KRITISCH → HOCH → MITTEL → NIEDRIG. Aufwand: S (≤0.5 Tag), M (0.5–2 Tage), L (>2 Tage).

| ID | Priorität | Schicht | Befund | Empfohlene Maßnahme | Aufwand |
|----|-----------|---------|--------|---------------------|:------:|
| P-01 | KRITISCH | MCP | API-Key Klartext-Logging (`views.py:59-62`) | Debug-Log-Zeilen entfernen; nur maskierte Präfixe | S |
| P-02 | KRITISCH | MCP | API-Key in SSE-URL (`views.py:219`) | Key nicht in URL; Session serverseitig binden | M |
| A-01 | KRITISCH | API | IDOR `ApiKeyViewSet.destroy` | Queryset auf Owner/Tenant filtern; 404 bei Fremdzugriff | S |
| S-03 | KRITISCH | Service | `StakeholderNeedService.create()` ohne Permission-Check | RBAC-Gate am Service-Eingang | M |
| S-01 | KRITISCH | Service | Event-Bus Race-Condition `poll_and_dispatch()` | `select_for_update(skip_locked)` in `atomic()` | M |
| S-02 | KRITISCH | Service | DLQ-Move nicht atomar | DLQ-Insert + Outbox-Update in einer Transaktion | S |
| S-04 | KRITISCH | Service | `clone_workspace()` Hierarchie-Fix broken (`arch.id` bereits neu) | Alt→Neu-ID-Map fürs Parent-Wiring | M |
| A-03 | HOCH | API | `IcdViewSet.destroy` DDL (`DISABLE TRIGGER`) im Request | DDL entfernen; ORM-Cascade/`DEFERRED` | M |
| A-02 | HOCH | API | `DiagramViewSet.list` ignoriert `workspace_id` | Queryset per workspace_id+Tenant filtern | S |
| P-03 | HOCH | MCP | RBAC fehlt für needs/adr/risk/issue/glossary Writes | Einheitliches RBAC-Gate für Write-Tools | M |
| P-04 | HOCH | MCP | Kein Audit auf `needs.create/update` | Audit-Hook im Service | S |
| P-05 | HOCH | MCP | Param-Inkonsistenz `id` vs. `requirement_id` | Schema/Handler angleichen + Contract-Test | S |
| P-06 | HOCH | MCP | JSON-RPC-Error String statt Integer `code` | Auf spezifikationskonformes Error-Objekt umstellen | S |
| S-05 | HOCH | Service | Suspect-Propagation bei `outgoing` deaktiviert | Richtungsunabhängige Propagation + Test | M |
| S-06 | HOCH | Service | Import ohne initialen `WorkflowState` | Initial-State gemäß Preset setzen | S |
| S-07 | HOCH | Service | Export enthält soft-deleted Entities | Export über Default-Manager filtern | S |
| S-08 | HOCH | Service | Search ignoriert AND/OR/NOT (`plainto_tsquery`) | `websearch_to_tsquery`/`to_tsquery` | M |
| S-09 | HOCH | Service | Policy nutzt `tenant_id` statt `workspace_id` | Scoping korrigieren + Test | S |
| M-01 | HOCH | Datenmodell | Fehlende Tenant-Isolation mehrerer Modelle | Tenant-FK + `TenantScopedModel`-Migration | L |
| M-02 | HOCH | Datenmodell | Migration 0029 untracked | Migration committen, Kette 0029→0032 prüfen | S |
| A-04 | MITTEL | API | `QUERYSET_OPTIMIZATIONS` nie angewandt (N+1) | In `get_queryset()` verdrahten | M |
| A-05 | MITTEL | API | `needs/` list → KeyError | Fehlenden Key defensiv behandeln + Test | S |
| A-06 | MITTEL | API | `TestRunViewSet.results` unpaginiert | Pagination auf Action anwenden | S |
| A-07 | MITTEL | API | `TraceLinkViewSet.retrieve` permanent 404 | Implementieren oder Route entfernen | S |
| A-08 | MITTEL | API | `WorkflowDefinitionViewSet` list/retrieve Stub | Implementieren oder Routen entfernen | S |
| A-09 | MITTEL | API | `AttributeVisibilityConfigViewSet.list` ohne Pagination | Standard-Pagination | S |
| P-07 | MITTEL | MCP | TOCTOU bei `user.create` | `get_or_create`/UniqueConstraint | S |
| P-08 | MITTEL | MCP | 401 statt 400 für Parse/Invalid-Request | Status korrigieren | S |
| P-09 | MITTEL | MCP | `artifact.search` limit ohne Bounds | Max-Limit erzwingen | S |
| P-10 | MITTEL | MCP | Kein Input-Schema (Needs/GenericCrud ToolGroup) | JSON-Schema + Validierung | M |
| S-10 | MITTEL | Service | `_set_tenant_context()` fehlt in update/delete | In allen Mutatoren aufrufen | S |
| S-11 | MITTEL | Service | Silent Mock-Fallback ohne WARNING | Warning-Log + Provider im Payload | S |
| S-12 | MITTEL | Service | Webhook synchron | In Celery-Task mit Retry/Timeout | M |
| S-13 | MITTEL | Service | N+1 in `get_allocation_coverage()` | prefetch/Aggregat-Query + Index (M-11) | M |
| S-14 | MITTEL | Service | Search In-Memory-Pagination | DB-seitige Pagination | S |
| S-15 | MITTEL | Service | Policy-Cache nicht multi-process | Redis-Shared-Cache | M |
| M-03 | MITTEL | Datenmodell | N+1 `ArchitectureElement.get_level()` | Level materialisieren/Pfad-Cache | M |
| M-04 | MITTEL | Datenmodell | Fehlende `uid`-Indizes | `(tenant, uid)`-Index | S |
| M-05 | MITTEL | Datenmodell | Duale Workflow-Tabellen | Legacy deprecaten + Datenmigration | L |
| M-06 | MITTEL | Datenmodell | Doppelter Audit-Log | Auf ein Audit-Modell konsolidieren | M |
| A-10 | NIEDRIG | API | search_fields/ordering_fields undeklariert | Pro ViewSet deklarieren | S |
| A-11 | NIEDRIG | API | Kein `@extend_schema` auf Custom-Actions | Schema ergänzen | M |
| A-12 | NIEDRIG | API | `COMMON_ERROR_RESPONSES` ungenutzt | In `responses=` einbinden | S |
| A-13 | NIEDRIG | API | Workspace-Admin-Actions ohne permission_classes | Explizite Permissions | S |
| A-14 | NIEDRIG | API | 405/403-Inkonsistenz immutable | Status vereinheitlichen | S |
| A-15 | NIEDRIG | API | ApiKey Error-Format abweichend | `build_error_response()` nutzen | S |
| A-16 | NIEDRIG | API | Direktes ORM in ViewSets | Über Service führen | M |
| P-11 | NIEDRIG | MCP | Threading ohne Pool-Limit | Begrenzter Executor | S |
| P-12 | NIEDRIG | MCP | Preset-Cache in-process | Redis-Cache (mit S-15) | M |
| P-13 | NIEDRIG | MCP | CORS spiegelt Origin | Allowlist | S |
| P-14 | NIEDRIG | MCP | `admin.backup_list` In-Memory-Filter | DB-seitig filtern | S |
| P-15 | NIEDRIG | MCP | Kein Rate-Limiting | Rate-Limit pro Key (mit X-04) | M |
| P-16 | NIEDRIG | MCP | SSE ohne Auth beim Connect | Auth beim Verbindungsaufbau | M |
| S-16 | NIEDRIG | Service | Soft-Delete ohne TraceLink-Cascade | Links mitmarkieren/kennzeichnen | S |
| S-17 | NIEDRIG | Service | Hard vs. Soft-Delete inkonsistent | Projektweite Strategie | M |
| S-18 | NIEDRIG | Service | Exception-Remapping via String | Typisierte Exceptions | S |
| S-19 | NIEDRIG | Service | `get_policy("scope_allowed")` → None | Default/Validierung | S |
| S-20 | NIEDRIG | Service | `dlq_service.py` ohne Test | Test-Modul ergänzen | S |
| M-07 | NIEDRIG | Datenmodell | `AttributeVisibilityConfig` Feldduplizierung | Normalisieren | M |
| M-08 | NIEDRIG | Datenmodell | `unique_together` deprecated | Auf `UniqueConstraint` umstellen | S |
| M-09 | NIEDRIG | Datenmodell | `WebhookSubscription.event_types` als CSV | ArrayField/Join-Tabelle | M |
| M-10 | NIEDRIG | Datenmodell | `DomainEventDLQ` fehlende Indizes | Index `(status, created_at)` | S |
| M-11 | NIEDRIG | Datenmodell | `TraceLink` kein Index auf `target` | Index ergänzen | S |
| M-12 | NIEDRIG | Datenmodell | `GlossaryTermVersion` fehlende `__str__` | `__str__` ergänzen | S |

**Empfohlene Sofort-Sequenz (Sprint 1):** P-01, A-01, S-02, M-02 (alle Aufwand S) zuerst — maximale Risikoreduktion bei minimalem Aufwand; anschließend P-02, S-01, S-03, S-04 (kritisch, Aufwand M).

---

## 8. Umsetzungsstatus (Stand 2026-07-14)

Die folgenden 7 KRITISCH-Findings wurden als REQ-IDs registriert. Der aktuelle Umsetzungsstand wurde durch Vergleich zwischen `main` und `fix/system-audit-critical` verifiziert:

| ID | REQ-ID | Status | Kommentar |
|-----|--------|--------|-----------|
| P-01 | REQ-017 | ✅ Done | Debug-Log-Zeilen in `backend/mcp_server/views.py::_extract_django_headers` entfernt. Commit `798cabde`. |
| P-02 | REQ-018 | ✅ Done | API-Key nicht mehr in SSE-URL; serverseitige Session→Key-Bindung (Redis, TTL) im SSE-Handshake, `McpMessagesView` autorisiert per `session_id`. Commit `5e37eee`. |
| A-01 | REQ-019 | ✅ Done | Ownership-Check in `ApiKeyViewSet.destroy` hinzugefügt. Commit `bda8b582`. |
| S-01 | REQ-020 | ✅ Done | Per-Record `select_for_update(skip_locked=True)` + `transaction.atomic()` in `poll_and_dispatch()`. Kein doppelter Dispatch bei konkurrierenden Workern. Commit `5d702ef`. |
| S-02 | REQ-021 | ✅ Done | DLQ-Move in `backend/application/event_bus.py::poll_and_dispatch()` jetzt in `transaction.atomic()` gekapselt. Commit `fbe8c201`. |
| S-03 | REQ-022 | ✅ Done | `_set_tenant_context` + `_assert_write_permission` am Eingang von `create()` ergänzt. Viewer-Role wird mit `PermissionDeniedError` abgewiesen. Commit `f1c5f7c`. |
| S-04 | REQ-023 | ✅ Done | `clone_workspace()` baut jetzt eine `old_id → new_instance`-Map und remappt die self-referentielle Parent-FK in zwei Durchläufen (erst ohne Parent anlegen, dann verdrahten). Regressionstest `TestCloneWorkspaceHierarchy` mit 3-Ebenen-Hierarchie (Grandparent→Parent→Child). Commit `2dc82b1`. |

### Bekanntes Problem: Commit 9e215903

Der aktuelle HEAD (`9e215903`, "Add some critical Fixes es reqs") verstößt gegen die Commit-Konventionen (kein `fix(REQ-xxx):`-Format) und enthält keine der oben aufgelisteten Backend-Fixes. Stattdessen:
- SE-Kaskade-Dokumentation (`docs/se/L1/...`)
- Drei Scratch-Skripte (`analyze_tests.py`, `fix.py`, `update_files.py`), die versehentlich wieder trackt wurden

**Nächste Schritte:**
1. Scratch-Skripte erneut aus Tracking entfernen (`.gitignore` aktualisieren)
2. Commit `9e215903` ggf. sauber aufteilen (Dokumentation separate, Backend-Fixes separate)
3. ~~Fehlende Fixes tatsächlich implementieren: **S-04**~~ — erledigt (siehe Abschnitt 8).
4. Nach Abschluss KRITISCH-Tier: HOCH/MITTEL/NIEDRIG-Tiers gemäß Abschnitt 7 fortsetzen

**Session pausiert auf 2026-07-14** — bei Fortsetzung: direkt mit Punkt 1–4 fortzfahren.

---

> **Hinweis Traceability:** Dieser Audit ist ein System-Zustandsbericht (REQ-ID n/a). Die abgeleiteten Maßnahmen sollten vor Umsetzung als eigene REQ-Einträge in `docs/REQUIREMENTS.md` bzw. dem SE-Register (`docs/se/`) verankert werden — jede Code-Änderung braucht eine REQ-ID und einen zugehörigen Test.
