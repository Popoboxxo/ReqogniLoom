# L3 StateLifecycleManager Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-WE-003 — StateLifecycleManager
> **Parent-System:** WorkflowEngineSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Atomare State-Initialisierung, State-Mutation mit Optimistic Locking, append-only History-Eintrag, Tenant-Isolation; schreibt `signature_seal` (HMAC-SHA256) in History-Eintrag wenn SignatureGate durchlaufen.

---

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-WE-003 | WorkflowState History (Audit-Trail) — append-only, atomar, signature_seal |
| REQ-L2-WE-005 | Workflow State Initialization — initialize-Operation, atomar |
| REQ-L2-WE-006 | Tenant-Scoped Workflow Data Isolation — alle Queries tenant-gefiltert |

---

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-WE-INT-002 | eingehend | COMP-WE-002 (TransitionValidator) | `ValidationResult {valid, error_code?, error_message?}` (erw. Payload mit `seal?`) |
| IF-WE-INT-003 | ausgehend | COMP-WE-001 (WorkflowDefinitionStore) | `StateQuery {workspace_id, item_type, query_type: "initial_state"}` |
| IF-WE-INT-005 | eingehend | COMP-WE-004 (SignatureGateVerifier) | `VerificationResult {valid, seal? (HMAC-SHA256 hex)}` |

## Externe Schnittstellen (Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-WE-EXT-IN-002 | eingehend | ApplicationService | `initialize(item_ids[], item_type, workspace_id, ctx)` |
| IF-WE-EXT-OUT-001 | ausgehend | PersistenceLayer | WorkflowState und History-Eintraege lesen/schreiben (Django ORM) |

---

## L3 Komponenten-Anforderungen

### REQ-L3-WE003-001: Atomare State-Initialisierung

Der StateLifecycleManager SHALL fuer eine `initialize`-Operation alle uebergebenen Items in einer einzigen atomaren Datenbanktransaktion mit dem initialen WorkflowState (Wert gemaess `initial_state`-Abfrage via IF-WE-INT-003 an COMP-WE-001) versehen. Scheitert die Transaktion fuer ein einzelnes Item, SHALL die gesamte Operation zurueckgerollt werden. Ein leeres `item_ids`-Array SHALL ohne Fehler und ohne Datenbankschreiboperation behandelt werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `initialize([id1, id2, id3], "Requirement", workspace_W, ctx)` → 3 WorkflowState records with `current_state = "draft"` created atomically
- [ ] Simulated DB failure during multi-item initialization → all records rolled back, no partial state persisted
- [ ] `initialize([], "Requirement", workspace_W, ctx)` → no records created, no error raised
- [ ] No WorkflowDefinition found for given item_type/workspace → error `"No WorkflowDefinition found"`, no records created
- [ ] All records share the same transaction commit timestamp

---

### REQ-L3-WE003-002: State-Mutation mit Optimistic Locking und Append-only History

Der StateLifecycleManager SHALL nach positivem `ValidationResult` den `current_state` eines Items aktualisieren und einen append-only History-Eintrag mit den Feldern `from_state`, `to_state`, `transitioned_by`, `transitioned_at` (UTC, Millisekunden-Praezision), `change_reason` (optional) und `signature_seal` (non-null wenn SignatureGate durchlaufen, sonst null) schreiben. Beide Operationen MUESSEN in einer atomaren Transaktion erfolgen. Schlaegt der History-Write fehl, SHALL die State-Mutation zurueckgerollt werden. Bestehende History-Eintraege DUERFEN NICHT modifiziert oder geloescht werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Successful transition `draft → approved` → `current_state` updated AND history entry written in same transaction
- [ ] History write failure (simulated) → state mutation rolled back, item remains in `from_state`
- [ ] 3 consecutive transitions → 3 history entries in ascending `transitioned_at` order
- [ ] Attempt to modify an existing history entry → raises exception `"History is append-only"`
- [ ] Transition via MCP client → `transitioned_by` contains agent-client identity
- [ ] Transition with `signature_gate` passed → `signature_seal` is non-null HMAC-SHA256 hex string in history entry
- [ ] Transition without `signature_gate` → `signature_seal` is null in history entry

---

### REQ-L3-WE003-003: Tenant-Isolation aller Datenbankoperationen

Der StateLifecycleManager SHALL bei jeder Lese- und Schreiboperation auf WorkflowState und History-Eintraegen den `tenant_id` aus dem Auth-Kontext als obligatorischen Filter anwenden. Eine Operation ohne gueltigen `tenant_id` im Kontext SHALL abgebrochen werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Query for workspace of Tenant A with Tenant-B context → returns empty result set, no Tenant-A records exposed
- [ ] Transition attempt with Tenant-B context on a Tenant-A item → rejected before any DB write
- [ ] All generated SQL contains `WHERE tenant_id = <active_tenant>` clause (verifiable via Django query log)
- [ ] Missing `tenant_id` in context → operation aborted with error `"Missing tenant context"`

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
