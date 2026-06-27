---
step: interfaces
agent: se-interface-mgr
iteration: 1
status: done
timestamp: "2026-06-27T23:00:00Z"
schema_version: "1.0.0"
source_handoff: "L2_architectural_decomposition_iter-1.md"
---

# SE Phase 5 — Interface Registration Report

> **Agent:** se-interface-mgr
> **Datum:** 2026-06-27
> **Branch:** feat/se-implementation
> **Level:** L2 (Backlog-Subsysteme REQ-L1-034..041)
> **Status:** approved

---

## 1. Summary

| Metrik | Wert |
|--------|------|
| **New interfaces registered** | **8** |
| — Priority (Top 3 flagged) | 3 (IF-L1-032, IF-L1-033, IF-L1-034) |
| — From subsystem scan | 4 (IF-L1-035, IF-L1-036, IF-L1-037, IF-L1-038) |
| — Stub (out-of-scope) | 1 (IF-L1-039) |
| **New subsystems touched** | **3** (ReqIFServiceSystem, CommentServiceSystem, VectorSearchServiceSystem) |
| **Existing subsystems touched** | **6** (AS, TE, AT, PL, AL, Notification[future]) |
| **Total interfaces per subsystem** | RQ: 3 | CM: 4 | VS: 4 |
| **Sync risks identified** | 3 (see §4) |
| **Async interfaces** | 1 (IF-L1-032) |
| **Stub interfaces** | 1 (IF-L1-039) |

---

## 2. Full Interface Contracts

### 2.1 IF-L1-032: ApplicationService → VectorSearchServiceSystem (Domain-Event Embedding Trigger)

#### Signal Flow

```
┌─────────────────┐     Domain Event (async)     ┌────────────────────────┐
│  Application    │  ──────────────────────────▶  │  VectorSearchService   │
│  Service (004)  │   ArtifactCreated/Updated     │  System (VS)           │
│                 │                               │                        │
│  COMP-AS-0xx    │  Queue: Celery/Redis          │  COMP-VS-002           │
│  ArtifactWrite  │                               │  EmbeddingPipeline     │
│  Handler        │                               │                        │
└────────┬────────┘                               └───────────┬────────────┘
         │                                                     │
         │ 1. Write-Transaktion committed                       │ 2. Embed text
         │ 3. Event published to queue                         │ 3. Store pgvector
         ▼                                                     ▼
┌─────────────────┐                               ┌────────────────────────┐
│  Persistence    │                               │  LlmAdapter (009)      │
│  Layer (010)    │                               │  IF-VS-EXT-OUT-001     │
└─────────────────┘                               └────────────────────────┘
```

#### Contract

```json
{
  "interface_id": "IF-L1-032",
  "version": "1.0.0",
  "source_id": "REQ-L2-AS",
  "target_id": "REQ-L2-VS",
  "source_system": "ApplicationServiceSystem (ARCH-L1-004)",
  "target_system": "VectorSearchServiceSystem",
  "direction": "AS → VS (uni)",
  "signal_type": "event (async fire-and-forget)",
  "protocol": "async message queue (Celery/Redis pub-sub)",
  "trigger": "Domain Event: ArtifactCreated / ArtifactUpdated",
  "subsystem_boundary_id": "IF-VS-EXT-IN-002",
  "req_l1": "REQ-L1-038",
  "payload_schema": {
    "event_type": "ArtifactCreated | ArtifactUpdated",
    "artifact_id": "uuid",
    "artifact_type": "requirement | architecture_element | test_case",
    "workspace_id": "uuid",
    "tenant_id": "uuid",
    "version": "int",
    "timestamp": "ISO8601"
  },
  "acceptance_latency": {
    "event_to_embedding_start_p95": "30s",
    "full_embedding_max": "5 min"
  },
  "failure_mode": "Queue persistiert; DLQ nach 3 Retries; Graceful Degradation",
  "idempotency": "Consumer idempotent, Key: artifact_id + version",
  "auth": "Service-Account (Queue-Zugriff)",
  "design_by_contract": {
    "preconditions": [
      "Artefakt erfolgreich in PersistenceLayer persistiert",
      "Embedding-Pipeline (VS) ist registriert und aktiv",
      "Event enthält gültige artifact_id und workspace_id"
    ],
    "postconditions": [
      "Event ist in der Queue bestätigt (ACK)",
      "Embedding wird innerhalb von 5 Min aktualisiert ODER Event landet in DLQ nach 3 Fehlversuchen",
      "Embedding-Vektor ist unter artifact_id auffindbar"
    ],
    "invariants": [
      "Embedding ist stets eine berechnete Funktion des Artefakt-Inhalts (kein manuelles Override)",
      "Embedding-Dimension ist durch Modell-Konfiguration festgelegt (konfigurierbar)",
      "Haupt-Write-Path wird durch Embedding NICHT blockiert (REQ-L1-026)"
    ]
  }
}
```

---

### 2.2 IF-L1-033: AuthAndTenancySystem → PersistenceLayer (RLS Policy Enforcement)

#### Signal Flow

```
┌─────────────────────┐      Control-Plane (DDL)       ┌─────────────────────┐
│  AuthAndTenancy     │  ───────────────────────────▶  │  PersistenceLayer   │
│  System (011)       │  CREATE/ALTER POLICY           │  (010)              │
│                     │                                │                     │
│  COMP-AT-005        │  Query-Time (Session Var)     │  COMP-PL-002        │
│  ItemPermissionStore │  ◀─────────────────────────── │  TenantIsolation    │
│                     │  SET LOCAL rls.item_permissions│  Manager            │
└─────────────────────┘                                └─────────────────────┘
```

#### Contract

```json
{
  "interface_id": "IF-L1-033",
  "version": "1.0.0",
  "source_id": "REQ-L2-AT-017",
  "target_id": "REQ-L2-PL",
  "source_system": "AuthAndTenancySystem (ARCH-L1-011)",
  "target_system": "PersistenceLayer (ARCH-L1-010)",
  "direction": "AT → PL (uni — Policy Definition; PL evaluiert automatisch)",
  "signal_type": "control (declarative policy injection)",
  "protocol": "PostgreSQL Row-Level Security (RLS): DDL ALTER POLICY + DML SET LOCAL",
  "trigger": "Admin setzt Item-Level-Regel; Query-Time Session Context",
  "req_l1": "REQ-L1-039",
  "payload_schema_policy_def": {
    "policy_id": "uuid",
    "artifact_id": "uuid | *",
    "principal_type": "user | group",
    "principal_id": "uuid",
    "permission": "read | write",
    "effect": "allow | deny",
    "priority": "int",
    "created_at": "ISO8601"
  },
  "payload_schema_query_time": "SET LOCAL rls.item_permissions = '{user_id, role_list, tenant_id}'",
  "acceptance_latency": {
    "policy_update": "< 1s",
    "query_overhead": "< 10% (TTL 60s Cache)"
  },
  "failure_mode": "Fail-Closed: Keine Ergebnisse bei fehlendem Auth-Context (kein Daten-Leak)",
  "idempotency": "CREATE POLICY IF NOT EXISTS / ALTER POLICY — deklarativ, idempotent",
  "auth": "Admin-Rolle für DDL; Query-Time via Session-Context (trusted)",
  "design_by_contract": {
    "preconditions": [
      "ItemPermissionStore hat gültige Policy-Definition",
      "PostgreSQL RLS ist auf der Ziel-Tabelle aktiviert",
      "Query-Session hat gültigen Auth-Context (user_id, tenant_id)"
    ],
    "postconditions": [
      "RLS-Policy ist auf Datenbankebene aktiv (DDL committed)",
      "Query-Ergebnisse sind gemäß Policy gefiltert",
      "Permission-Cache ist nach TTL (60s) aktualisiert"
    ],
    "invariants": [
      "Item-Level-Regeln verfeinern NIEMALS Workspace-RBAC — sie schränken nur ein, erweitern nie",
      "Fehlende Policy → Default-Deny (kein Daten-Leak)",
      "RLS-Policies persistieren über Deployment-Grenzen hinweg"
    ]
  }
}
```

---

### 2.3 IF-L1-034: CommentServiceSystem → AuditLogSystem (Audit Log Pflicht)

#### Signal Flow

```
┌─────────────────────┐       sync (Transaktion)       ┌─────────────────────┐
│  CommentService     │  ───────────────────────────▶  │  AuditLogSystem     │
│  System (CM)        │  log_write(actor, op, entity)  │  (012)              │
│                     │                                │                     │
│  COMP-CM-001/003    │  Fail-Closed: Rollback         │  COMP-AL-001        │
│  CommentManager /   │  bei Audit-Fehler              │  AuditLogWriter     │
│  NotificationDisp.  │                                │                     │
└─────────────────────┘                                └──────────┬──────────┘
                                                                  │
                                                                  ▼
                                                         ┌─────────────────┐
                                                         │  Persistence    │
                                                         │  Layer (010)    │
                                                         │  IF-L1-022      │
                                                         └─────────────────┘
```

#### Contract

```json
{
  "interface_id": "IF-L1-034",
  "version": "1.0.0",
  "source_id": "REQ-L2-CM",
  "target_id": "REQ-L2-AL",
  "source_system": "CommentServiceSystem",
  "target_system": "AuditLogSystem (ARCH-L1-012)",
  "direction": "CM → AL (uni)",
  "signal_type": "data (audit write)",
  "protocol": "sync (in-process Python) — identisch IF-L1-016",
  "subsystem_boundary_id": "IF-CM-EXT-OUT-001",
  "trigger": "comment_created | comment_updated | comment_deleted | mention_resolved | notification_dispatched",
  "req_l1": "REQ-L1-037",
  "payload_schema": {
    "actor": "uuid | system",
    "operation": "comment_created | comment_updated | comment_deleted | mention_resolved | notification_dispatched",
    "entity_id": "uuid",
    "entity_type": "comment | mention | notification",
    "artifact_id": "uuid",
    "details": {
      "comment_snippet": "string (truncated 200 chars)",
      "mentioned_users": ["uuid"],
      "thread_parent_id": "uuid | null"
    },
    "timestamp": "ISO8601",
    "source": "comment_service"
  },
  "acceptance_latency": "< 50ms Overhead (sync, in-Transaction)",
  "failure_mode": "Fail-Closed: CM-Operation rolled back bei Audit-Fehler",
  "idempotency": "Nicht erforderlich — Transaktionsgarantie",
  "auth": "Interner System-Call (trusted subsystem)",
  "design_by_contract": {
    "preconditions": [
      "CM-Operation (create/update/delete) ist im eigenen System erfolgreich abgeschlossen",
      "actor ist identifiziert (user_id oder system)",
      "entity_id referenziert existierende Kommentar/Mention-Entität"
    ],
    "postconditions": [
      "AuditLogEntry ist append-only persistiert (IF-L1-022 → PL)",
      "Audit-Eintrag enthält alle relevanten Metadaten für Nachvollziehbarkeit",
      "Bei Fehler: gesamte Transaktion rolled back (Fail-Closed)"
    ],
    "invariants": [
      "AuditLogEntry wird NIEMALS gelöscht oder modifiziert (append-only)",
      "Jede Kommentar-Operation erzeugt mindestens einen Audit-Eintrag",
      "source = comment_service ermöglicht Filterung im Audit-Log-Query"
    ]
  }
}
```

---

### 2.4 IF-L1-035: ApplicationService ↔ ReqIFServiceSystem (Import/Export)

#### Signal Flow

```
┌─────────────────────┐      sync (request-response)    ┌─────────────────────┐
│  Application        │  ◀────────────────────────────  │  ReqIFServiceSystem  │
│  Service (004)      │  Import/Export Request          │  (RQ)                │
│                     │  ───────────────────────────▶   │                      │
│  COMP-AS-0xx        │  Result: JSON                  │  COMP-RQ-001/002     │
│                     │                                │  Parser/Serializer   │
└─────────────────────┘                                └──────────┬──────────┘
                                                                  │
                                   ┌──────────────────────────────┼──────────────────────────┐
                                   │                              │                          │
                                   ▼                              ▼                          ▼
                          ┌─────────────────┐          ┌─────────────────┐      ┌──────────────────┐
                          │  Persistence    │          │  Traceability   │      │  AuditLogSystem  │
                          │  Layer (010)    │          │  Engine (007)   │      │  (012)           │
                          │  IF-RQ-EXT-     │          │  IF-RQ-EXT-     │      │  IF-L1-034       │
                          │  OUT-001        │          │  OUT-002        │      │                  │
                          └─────────────────┘          └─────────────────┘      └──────────────────┘
```

#### Contract

```json
{
  "interface_id": "IF-L1-035",
  "version": "1.0.0",
  "source_id": "REQ-L2-AS / REQ-L2-RQ",
  "target_id": "REQ-L2-RQ / REQ-L2-AS",
  "source_system": "ApplicationServiceSystem ↔ ReqIFServiceSystem",
  "target_system": "ReqIFServiceSystem ↔ ApplicationServiceSystem",
  "direction": "bidirektional (AS initiiert; RQ liefert Ergebnis)",
  "signal_type": "request-response (sync)",
  "protocol": "in-process Python (sync)",
  "subsystem_boundary_id": "IF-RQ-EXT-IN-001",
  "req_l1": "REQ-L1-034",
  "payload_schema_import_request": {
    "workspace_id": "uuid",
    "reqif_file": "base64 | S3-key",
    "options": {
      "dry_run": "bool",
      "import_tracelinks": "bool",
      "conflict_strategy": "skip | override | new_version"
    }
  },
  "payload_schema_export_request": {
    "workspace_id": "uuid",
    "scope": "workspace | project",
    "include_tracelinks": "bool",
    "format": "reqif_1_0 | reqif_1_1"
  },
  "payload_schema_import_response": {
    "artifacts_created": "int",
    "tracelinks_created": "int",
    "warnings": ["string"],
    "errors": [{"element_ref": "string", "reason": "string"}],
    "dry_run": "bool"
  },
  "payload_schema_export_response": {
    "reqif_file": "base64",
    "spec_object_count": "int",
    "spec_relation_count": "int",
    "spec_hierarchy_count": "int"
  },
  "design_by_contract": {
    "preconditions": [
      "AuthContext validiert (User hat Workspace-Rechte)",
      "ReqIF-Datei valide gegen ReqIF-Schema (Import)",
      "Workspace existiert und ist nicht im Baseline-Freeze (Export)"
    ],
    "postconditions": [
      "Import: Artefakte + TraceLinks persistiert (über PL/TE)",
      "Export: Vollständige .reqif-Datei inkl. SpecHierarchies",
      "Dry-Run: Nur Validierung, keine Persistenz"
    ],
    "invariants": [
      "Roundtrip-Treue: Export→Import erzeugt strukturgleiche Artefakte",
      "Import überschreibt NIEMALS bestehende Artefakte ohne explizite Strategie"
    ]
  }
}
```

---

### 2.5 IF-L1-036: ReqIFServiceSystem → TraceabilityEngine (SpecRelations → TraceLinks)

#### Contract

```json
{
  "interface_id": "IF-L1-036",
  "version": "1.0.0",
  "source_id": "REQ-L2-RQ",
  "target_id": "REQ-L2-TE",
  "source_system": "ReqIFServiceSystem (RQ) — COMP-RQ-001",
  "target_system": "TraceabilityEngine (ARCH-L1-007) — COMP-TE-001",
  "direction": "RQ → TE (uni)",
  "signal_type": "data (CRUD)",
  "protocol": "in-process Python (sync)",
  "subsystem_boundary_id": "IF-RQ-EXT-OUT-002",
  "trigger": "ReqIF-Import: SpecRelations → create_trace_link()",
  "req_l1": "REQ-L1-034",
  "payload_schema": {
    "source_artifact_id": "uuid",
    "target_artifact_id": "uuid",
    "link_type": "derives_from | satisfies | refines | traces",
    "workspace_id": "uuid",
    "reqif_relation_id": "string (original)"
  },
  "acceptance_latency": "Sync — in Import-Transaktion",
  "idempotency": "Erforderlich — Key: reqif_relation_id + workspace_id",
  "design_by_contract": {
    "preconditions": [
      "Quell- und Ziel-Artefakt existieren in PersistenceLayer",
      "TraceLink-Typ ist valide",
      "Workspace-Kontext ist gesetzt"
    ],
    "postconditions": [
      "TraceLink persistiert via PersistenceLayer",
      "Bei Duplikat: keine doppelte Erstellung (idempotent)",
      "Fehler → gesamter Import rolled back"
    ],
    "invariants": [
      "Jeder SpecRelation wird genau ein TraceLink (oder Warnung bei Fehler)",
      "TraceLink-Referenzen sind referentiell integer"
    ]
  }
}
```

---

### 2.6 IF-L1-037: ApplicationService ↔ CommentServiceSystem (Comment CRUD Delegation)

#### Contract

```json
{
  "interface_id": "IF-L1-037",
  "version": "1.0.0",
  "source_id": "REQ-L2-AS / REQ-L2-CM",
  "target_id": "REQ-L2-CM / REQ-L2-AS",
  "source_system": "ApplicationServiceSystem ↔ CommentServiceSystem",
  "target_system": "CommentServiceSystem ↔ ApplicationServiceSystem",
  "direction": "bidirektional (AS delegiert CRUD; CM liefert Ergebnis)",
  "signal_type": "request-response (sync)",
  "protocol": "in-process Python (sync)",
  "subsystem_boundary_id": "IF-CM-EXT-IN-001",
  "trigger": "User/Agent erstellt/listet/aktualisiert Kommentar via REST/MCP",
  "req_l1": "REQ-L1-037",
  "payload_schema_create": {
    "artifact_id": "uuid",
    "parent_comment_id": "uuid | null",
    "text": "string",
    "author_id": "uuid",
    "workspace_id": "uuid"
  },
  "payload_schema_list": {
    "artifact_id": "uuid",
    "include_deleted": "bool",
    "page": "int",
    "page_size": "int"
  },
  "acceptance_latency": "p95 < 200ms (REQ-L1-026 konform)",
  "design_by_contract": {
    "preconditions": [
      "Artefakt-ID existiert",
      "AuthContext validiert (Schreibrecht auf Artefakt)",
      "Text ist nicht leer"
    ],
    "postconditions": [
      "Kommentar (oder Antwort) persistiert",
      "Audit-Eintrag via IF-L1-034",
      "@Mentions asynchron aufgelöst",
      "In-App-Notification bei Mention"
    ],
    "invariants": [
      "Thread-Struktur immer konsistent (parent_comment_id zeigt auf existierenden Kommentar)",
      "Kommentar-Versionierung erhält Historie"
    ]
  }
}
```

---

### 2.7 IF-L1-038: ApplicationService ↔ VectorSearchServiceSystem (Semantic Search)

#### Contract

```json
{
  "interface_id": "IF-L1-038",
  "version": "1.0.0",
  "source_id": "REQ-L2-AS / REQ-L2-VS",
  "target_id": "REQ-L2-VS / REQ-L2-AS",
  "source_system": "ApplicationServiceSystem ↔ VectorSearchServiceSystem",
  "target_system": "VectorSearchServiceSystem ↔ ApplicationServiceSystem",
  "direction": "bidirektional (AS sendet Query; VS liefert RankedResults)",
  "signal_type": "request-response (sync)",
  "protocol": "in-process Python (sync)",
  "subsystem_boundary_id": "IF-VS-EXT-IN-001",
  "trigger": "User/Agent triggert semantische Suche via REST/UI/MCP",
  "req_l1": "REQ-L1-038 (primär), REQ-L1-020 (Volltext-Fallback)",
  "payload_schema_query": {
    "query": "string (natural language) | null",
    "artifact_id": "uuid (similarity search) | null",
    "workspace_id": "uuid",
    "filters": {
      "artifact_types": ["requirement", "architecture_element", "test_case"],
      "limit": "int",
      "min_score": "float"
    },
    "hybrid": "bool"
  },
  "payload_schema_result": {
    "results": [{
      "artifact_id": "uuid",
      "artifact_type": "string",
      "title": "string",
      "score": "float",
      "snippet": "string"
    }],
    "total_count": "int",
    "query_vector_used": "bool"
  },
  "acceptance_latency": "p95 < 2s (Workspace ≤ 10.000 artefacts)",
  "failure_mode": "Graceful Degradation auf Volltextsuche (REQ-L1-020)",
  "design_by_contract": {
    "preconditions": [
      "Workspace existiert",
      "Entweder query ODER artifact_id ist gesetzt (nicht beide null)",
      "Embedding-Pipeline ist initialisiert"
    ],
    "postconditions": [
      "Rankierte Ergebnisse mit Ähnlichkeits-Score zurückgegeben",
      "Hybrid-Suche wenn hybrid=true kombiniert Vektor + Volltext",
      "Bei leerem Ergebnis: leere Liste, kein Fehler"
    ],
    "invariants": [
      "Ergebnisse sind immer auf Workspace beschränkt (Tenant-Isolation via IF-L1-022)",
      "Score ist normalisiert [0,1]",
      "Keine Schreiboperationen als Seiteneffekt"
    ]
  }
}
```

---

### 2.8 IF-L1-039: CommentServiceSystem → NotificationService [STUB]

#### Contract (vorgeschlagen — noch nicht implementiert)

```json
{
  "interface_id": "IF-L1-039",
  "version": "0.1.0 (vorgeschlagen)",
  "source_id": "REQ-L2-CM",
  "target_id": "TBD — NotificationService (zukünftig)",
  "source_system": "CommentServiceSystem — COMP-CM-003 (NotificationDispatcher)",
  "target_system": "NotificationService (ZUKÜNFTIG — Out-of-Scope für v2)",
  "direction": "CM → NotificationService (uni)",
  "signal_type": "event (async — geplant)",
  "protocol": "Offen — Celery/Redis/WebSocket",
  "trigger": "@Mention eines registrierten Nutzers → Notification-Event",
  "req_l1": "REQ-L1-037 (mitwirkend)",
  "status": "STUB — nur dokumentiert für zukünftige Erweiterung",
  "payload_schema_proposed": {
    "notification_type": "mention",
    "mentioned_user_id": "uuid",
    "triggered_by_user_id": "uuid",
    "comment_id": "uuid",
    "artifact_id": "uuid",
    "workspace_id": "uuid",
    "snippet": "string (truncated 100 chars)",
    "timestamp": "ISO8601"
  },
  "design_by_contract": {
    "preconditions": [
      "Mention wurde validiert (User existiert)",
      "Notification-Typ ist definiert",
      "Empfänger hat Notification-Präferenz aktiv"
    ],
    "postconditions": [
      "Notification wurde zugestellt (Kanal-abhängig)",
      "Notification ist im Audit-Log (via IF-L1-034)"
    ],
    "invariants": [
      "Kein Spam: gleicher Mention nicht doppelt notifizieren",
      "Empfänger kann Notifications deaktivieren"
    ]
  }
}
```

---

## 3. Sync-vs-Async Decision Matrix

| IF | Name | Decision | Primary Reason |
|----|------|----------|----------------|
| IF-L1-032 | AS→VS Domain Event | **Async** | Embedding darf Write-Path nicht blockieren (REQ-L1-026). 5 Min Toleranz. |
| IF-L1-033 | AT→PL RLS | **Control + Query-Time** | Deklarative DDL + sync Query Enforcement. Fail-Closed Sicherheit. |
| IF-L1-034 | CM→AL Audit | **Sync** | Konsistent mit IF-L1-016. Audit-Pflicht = Fail-Closed. |
| IF-L1-035 | AS↔RQ Import/Export | **Sync** | User-facing Operation. Async bräuchte späteres Abrufen. |
| IF-L1-036 | RQ→TE TraceLinks | **Sync** | In Import-Transaktion. Referentielle Integrität. |
| IF-L1-037 | AS↔CM Comment CRUD | **Sync** | User-facing CRUD. < 200ms SLA. |
| IF-L1-038 | AS↔VS Search | **Sync** | ≤ 2s Latenz erlaubt Sync. Fallback: Volltext. |
| IF-L1-039 | CM→Notification | **Async (geplant)** | Stub — keine E2E-Anforderung in v2. |

## 4. Deterministic Synchronization Risk Analysis

### TOP 3 Risks

| # | Risk | Severity | Impact | Mitigation |
|---|------|----------|--------|------------|
| **1** | **Embedding Lag → Stale Search Results** | **High** | Nutzer sieht veraltete Suchergebnisse für kürzlich geänderte Artefakte. Vertrauensverlust in semantische Suche. | UI-Hinweis "Embedding in Progress" für kürzlich geänderte Artefakte; Batch-Reprocessing nach Pipeline-Neustart; Queue-Monitoring |
| **2** | **Queue Overflow bei Bulk-Import** | **Medium** | ReqIF-Import (IF-L1-035) erzeugt 100+ Artefakte → 100+ Domain Events auf IF-L1-032. DLQ-Überlauf, Embedding bleibt zurück. | Bulk-Event `ArtifactsBulkCreated` einführen (statt N Einzel-Events); Queue-Depth-Limit 10.000; DLQ-Alarm |
| **3** | **RLS Policy-Query Overhead** | **Medium** | Komplexe Item-Level-RLS-Policies könnten Query-Overhead >10% treiben. REQ-L1-026 (<200ms) gefährdet. | Permission-Cache TTL 60s; Monitoring-Alarm bei >15% Overhead; HNSW-Index unabhängig von RLS |

### Ordering Analysis

| Constraint | Violation Risk | Enforcement |
|------------|---------------|-------------|
| Write vor Embedding (IF-L1-032) | Mittel — Event könnte vor Write-Transaktion published werden | Event erst nach Transaktion-Commit publishen (OUTBOX Pattern) |
| Import vor TraceLink (IF-L1-036) | Niedrig — in einer Transaktion | `transaction.atomic()` |
| Kommentar vor Audit (IF-L1-034) | Niedrig — Fail-Closed | Transaktionsgarantie |
| Auth vor Domain | Nicht betroffen — alle neuen Interfaces nutzen AuthContext aus AS/AT | Bestehendes IF-L1-004/007 Pattern |

## 5. Outstanding Decisions für se-termination

| Entscheidung | Optionen | Interface(s) betroffen | Empfehlung |
|-------------|----------|------------------------|------------|
| **L3-Zerlegung ReqIFServiceSystem** | Tiefe 2 (Komponenten: Parser, Serializer) vs. Tiefe 1 (Gesamtsystem) | IF-L1-035, IF-L1-036 | **Tiefe 2** — RQ hat 2 klare Komponenten mit orthogonalen Verantwortlichkeiten |
| **L3-Zerlegung CommentServiceSystem** | Tiefe 3 (CM-001, CM-002, CM-003) vs. Tiefe 2 (aggregiert) | IF-L1-034, IF-L1-037, IF-L1-039 | **Tiefe 3** — Mention-Auflösung und Notification sind domänenspezifisch genug für eigene Komponenten |
| **L3-Zerlegung VectorSearchServiceSystem** | Tiefe 3 (VS-001, VS-002, VS-003) vs. Tiefe 2 (aggregiert) | IF-L1-032, IF-L1-038 | **Tiefe 3** — EmbeddingPipeline (async) und VectorSearchEngine (sync) haben unterschiedliche Sync-Charakteristiken |
| **Notification-System als L2-Subsystem?** | (a) Eigenes L2-System, (b) Erweiterung CM, (c) v3 verschieben | IF-L1-039 | **Option (c)** — In-App-Notification in CM-003 ist ausreichend für v2. Externe Notification (E-Mail/Push) out-of-scope |
| **Bulk-Event für Embedding** | (a) Einzel-Events pro Artefakt, (b) Bulk-Event `ArtifactsBulkCreated` | IF-L1-032 | **Option (b)** — Bulk-Event reduziert Queue-Load bei Massenimporten erheblich |

## 6. Interface Count by Subsystem

| Subsystem | Incoming | Outgoing | Bidirectional | Total |
|-----------|----------|----------|---------------|-------|
| ReqIFServiceSystem (RQ) | 1 (IF-L1-035 AS→RQ) | 1 (IF-L1-036 RQ→TE) | 1 (IF-L1-035 RQ→AS) | **3** |
| CommentServiceSystem (CM) | 1 (IF-L1-037 AS→CM) | 2 (IF-L1-034 CM→AL, IF-L1-039 CM→Notif) | 1 (IF-L1-037 CM→AS) | **4** |
| VectorSearchServiceSystem (VS) | 2 (IF-L1-032 AS→VS, IF-L1-038 AS→VS) | 0 | 1 (IF-L1-038 VS→AS) | **4** |
| ApplicationService (AS) | 0 | 3 (→RQ, →VS, →CM) | 3 (↔RQ, ↔VS, ↔CM) | **6** (neue) |
| TraceabilityEngine (TE) | 1 (IF-L1-036 RQ→TE) | 0 | 0 | **1** (neu) |
| AuthAndTenancy (AT) | 0 | 1 (IF-L1-033 AT→PL) | 0 | **1** (neu) |
| AuditLogSystem (AL) | 1 (IF-L1-034 CM→AL) | 0 | 0 | **1** (neu) |
| PersistenceLayer (PL) | 1 (IF-L1-033 AT→PL) | 0 | 0 | **1** (neu) |

---

## 7. Registry Update

The following file was updated:
- **`docs/se/interface-registry.md`** — Sections 9–13 appended with 8 new interfaces, propagation map, sync analysis, and change log.

Total new interfaces registered: **8** (IF-L1-032 through IF-L1-039)

---

*Erstellt durch se-interface-mgr-Agent | ReqFlow SE-Kaskade Phase 5 | 2026-06-27*
*Nächster Schritt: se-termination (Zell-Tiefe pro Subsystem bestimmen)*
