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
