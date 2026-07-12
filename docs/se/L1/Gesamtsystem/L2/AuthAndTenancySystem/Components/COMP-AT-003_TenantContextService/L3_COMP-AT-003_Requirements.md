# L3 TenantContextService Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-AT-003 — TenantContextService
> **Parent-System:** AuthAndTenancySystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Tenant-Extraktion aus Token oder API-Key, Request-Context-Injektion für den Custom Django Manager, Tenant-Isolations-Garantie. Empfängt `IdentityClaims` vom AuthenticationService, erzeugt `TenantContext` und stellt sicher, dass alle nachgelagerten Datenbankzugriffe ausschließlich auf Daten des aktiven Tenants zugreifen.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-AT-005 | Auth-Kontext-Erzeugung und Propagation an ApplicationService, WorkflowEngine, AuditLog |
| REQ-L2-AT-008 | Tenant-Extraktion aus Token, Injektion in Request-Context für Custom Manager |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AT-INT-002 | eingehend | COMP-AT-001 (AuthenticationService) | `IdentityClaims {user_id, tenant_id}` |
| IF-AT-INT-003 | ausgehend | COMP-AT-002 (AuthorizationService) | `TenantContext {tenant_id, tenant_name}` |

## Externe Schnittstellen (Komponente an Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AT-EXT-OUT-001 | ausgehend | ApplicationService | Auth-Kontext `{user_id, tenant_id, active_roles, auth_method, api_key_id}` |
| IF-AT-EXT-OUT-004 | ausgehend | PersistenceLayer (Custom Manager) | Tenant-Filter-Injektion in Django ORM |

---

## L3 Komponenten-Anforderungen

### REQ-L3-AT003-001: Tenant-Extraktion aus IdentityClaims

Der TenantContextService SHALL aus den eingehenden `IdentityClaims` die `tenant_id` extrahieren und daraus einen validierten `TenantContext {tenant_id, tenant_name}` erzeugen. Kann die `tenant_id` nicht aufgelöst werden (unbekannter Tenant, fehlende Zuordnung), SHALL die Komponente mit HTTP 500 `{"error": "tenant_resolution_failed", "message": "Tenant resolution failed"}` abbrechen, ohne einen partiellen Kontext weiterzuleiten.

**Priority:** mandatory
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-AT-008
**Acceptance Criteria:**
- [ ] Valid `tenant_id` in `IdentityClaims` → `TenantContext` produced with correct `tenant_name` from DB
- [ ] API key belonging to tenant T1 → `TenantContext.tenant_id == T1`
- [ ] Bearer token belonging to user in tenant T2 → `TenantContext.tenant_id == T2`
- [ ] Identity claim with no tenant association → HTTP 500 `{"error": "tenant_resolution_failed"}`
- [ ] No partial `TenantContext` forwarded on resolution failure

---

### REQ-L3-AT003-002: Request-Context-Injektion für Tenant-Isolation

Der TenantContextService SHALL den erzeugten `TenantContext` in den Django Request-Context injizieren, sodass der Custom Manager ihn automatisch auf alle ORM-Queries anwendet. Die Injektion SHALL für jeden Request neu erfolgen und nach Abschluss des Requests bereinigt werden. Kein Request SHALL ohne aktiven Tenant-Context die Persistenzschicht erreichen dürfen.

**Priority:** mandatory
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Traceability:** REQ-L2-AT-008
**Acceptance Criteria:**
- [ ] Tenant T1 creates requirement → query from tenant T2 context does not return it
- [ ] Custom Manager automatically applies `filter(tenant_id=<active_tenant>)` without explicit caller action
- [ ] Context is cleared after request completion (no context leak between requests)
- [ ] Direct DB access attempt without tenant context → Custom Manager raises exception

---

### REQ-L3-AT003-003: Immutabler Auth-Kontext für nachgelagerte Systeme

Der TenantContextService SHALL nach vollständiger Tenant-Auflösung einen immutablen Auth-Kontext erzeugen: `{user_id, tenant_id, active_roles, auth_method, api_key_id}` und diesen an den ApplicationService, die WorkflowEngine und das AuditLog übergeben. Der Kontext SHALL nach Erzeugung nicht veränderbar sein.

**Priority:** mandatory
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-AT-005
**Acceptance Criteria:**
- [ ] Bearer-auth request → context contains `{auth_method: "bearer_token", api_key_id: null}`
- [ ] API-key-auth request → context contains `{auth_method: "api_key", api_key_id: "<id>"}`
- [ ] ApplicationService receives context on every use-case method call
- [ ] WorkflowEngine receives role information via context
- [ ] AuditLog receives actor information via context
- [ ] Any attempt to mutate context after creation raises `ImmutableContextError`

---

### REQ-L3-AT003-004: Tenant-Kontext-Weitergabe an AuthorizationService

Der TenantContextService SHALL den erzeugten `TenantContext` über die interne Schnittstelle IF-AT-INT-003 an den AuthorizationService weiterleiten, bevor dieser einen Berechtigungsentscheid trifft. Der `TenantContext` SHALL die vollständigen Tenant-Metadaten `{tenant_id, tenant_name}` enthalten.

**Priority:** mandatory
**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L2-AT-005, REQ-L2-AT-008
**Acceptance Criteria:**
- [ ] AuthorizationService receives `TenantContext` on every authorization evaluation
- [ ] `TenantContext` contains both `tenant_id` and `tenant_name`
- [ ] No authorization decision made before `TenantContext` is available
- [ ] On tenant resolution failure → AuthorizationService not reached

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*


## Master Traceability Matrix

| REQ-L3 | Abgeleitet von REQ-L2 |
|---------|----------------------|
| REQ-L3-AT003-001 | REQ-L2-AT-008 |
| REQ-L3-AT003-002 | REQ-L2-AT-008 |
| REQ-L3-AT003-003 | REQ-L2-AT-005 |
| REQ-L3-AT003-004 | REQ-L2-AT-005, REQ-L2-AT-008 |

