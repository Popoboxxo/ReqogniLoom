# L3 TransactionCoordinator Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-PL-003 — TransactionCoordinator
> **Parent-System:** PersistenceLayerSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Transaktionskontrolle (`transaction.atomic()`), Rollback-Garantie bei Fehlern, Kapslung von Multi-Entity-Transaktionen. Stellt sicher, dass schreibende Operationen ACID-konform ausgefuehrt werden und Teilzustaende in der Datenbank ausgeschlossen sind.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-PL-002 | Transaktionale Konsistenz (ACID) |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-PL-INT-002 | ausgehend | COMP-PL-001 | `transaction.atomic()` Context-Manager umschliess ORM-Write-Operationen |

## Externe Schnittstellen (falls Komponente an Systemgrenze)

Keine direkten externen Schnittstellen. Der TransactionCoordinator ist ein internes Cross-Cutting Concern; externe Dienste interagieren mit COMP-PL-001 (EntitySchemaManager).

## L3 Komponenten-Anforderungen

### REQ-L3-PL003-001: Verpflichtende Transaktionskapslung aller schreibenden Operationen

Der TransactionCoordinator MUSS sicherstellen, dass jede schreibende ORM-Operation (INSERT, UPDATE, DELETE) innerhalb eines `transaction.atomic()`-Blocks ausgefuehrt wird. Fuer Single-Entity-Operationen MUSS Django's implizites Auto-Commit deaktiviert oder ein explizites `atomic()` gesetzt sein. Fuer Multi-Entity-Operationen MUSS ein einziger uebergreifender `atomic()`-Block alle beteiligten ORM-Calls umschliessen.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] All service-layer write calls are wrapped in `transaction.atomic()`
- [ ] Single-entity write: database connection has `autocommit=False` during operation
- [ ] Multi-entity write: single `BEGIN`/`COMMIT` in database query log (no intermediate commits)
- [ ] Code review: no `save()` or `create()` call outside `atomic()` in service layer

---

### REQ-L3-PL003-002: Vollstaendiger Rollback bei Fehlern

Der TransactionCoordinator MUSS bei jeder unbehandelten Exception innerhalb eines `transaction.atomic()`-Blocks einen vollstaendigen Rollback aller innerhalb dieses Blocks vorgenommenen Schreiboperationen garantieren. Kein Teilzustand (partiell commitete Entitaeten) DARF in der Datenbank verbleiben. Savepoint-Rollbacks MUESSEN bei verschachtelten `atomic()`-Aufrufen korrekt aufgeloest werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] DB error after INSERT Requirement: no Requirement and no TraceLink persisted
- [ ] Batch decomposition: constraint violation at child 7 rolls back entire batch (children 1-6 also absent)
- [ ] Nested `atomic()`: inner rollback rolls back to savepoint, outer block unaffected
- [ ] Exception propagates to caller after rollback (not swallowed)

---

### REQ-L3-PL003-003: Transaktions-Timeout fuer langdauernde Operationen

Der TransactionCoordinator MUSS fuer alle schreibenden Transaktionen einen konfigurierbaren Timeout (Standard: 30 Sekunden) erzwingen. Ueberschreitet eine Transaktion den Timeout, MUSS die Transaktion mit einem vollstaendigen Rollback abgebrochen und eine `TransactionTimeoutError`-Exception ausgeloest werden. Der Timeout MUSS ueber eine Umgebungsvariable (`DB_TRANSACTION_TIMEOUT_SECONDS`) steuerbar sein.

**Priority:** desired
**Acceptance Criteria:**
- [ ] `DB_TRANSACTION_TIMEOUT_SECONDS` env variable controls transaction timeout
- [ ] Transaction exceeding timeout raises `TransactionTimeoutError` and rolls back
- [ ] Default timeout is 30 seconds when env variable is not set
- [ ] Long-running batch (simulated slow query): timeout triggers within ±2 seconds of configured value

---

---
*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
