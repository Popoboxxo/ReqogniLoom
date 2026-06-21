# L3 AuthEnforcer Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-RA-003 — AuthEnforcer
> **Parent-System:** RestApiAdapterSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Bearer-Token-Extraktion aus eingehenden HTTP-Requests, Delegation der Token-Validierung an AuthAndTenancy, RBAC-Enforcement (rollenbasierte Zugriffskontrolle) und Propagation des Tenant-Kontexts in den Request-Scope.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-RA-005 | Bearer-Token-Authentifizierung für alle Endpunkte |
| REQ-L2-RA-006 | RBAC-Enforcement auf API-Ebene |
| REQ-L2-RA-011 | Tenant-Kontext-Propagation |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-RA-INT-001 | eingehend / ausgehend | COMP-RA-001 (HttpEndpointController) | `AuthRequest {headers, path, method} -> AuthContext \| AuthError` |

## Externe Schnittstellen (Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Beschreibung |
|-------|----------|-------------|--------------|
| IF-RA-EXT-OUT-004 | ausgehend | AuthAndTenancy (ARCH-L1-011) | Token-Validierung, Auth-Kontext-Rückgabe |

## L3 Komponenten-Anforderungen

### REQ-L3-RA003-001: Bearer-Token-Extraktion und Validierungsdelegation

Der AuthEnforcer SHALL den Bearer Token aus dem `Authorization`-Header jedes eingehenden Requests extrahieren und dessen Validierung an AuthAndTenancy (IF-RA-EXT-OUT-004) delegieren. Fehlendes, ungültiges oder abgelaufenes Token SHALL mit `AuthError` beantwortet werden, der vom Controller in HTTP 401 übersetzt wird. Der AuthEnforcer DARF keine eigene Token-Validierungslogik implementieren.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Missing `Authorization` header produces `AuthError` → HTTP 401
- [ ] Expired token produces `AuthError` → HTTP 401
- [ ] Valid token produces `AuthContext` containing user identity, roles, and tenant_id
- [ ] AuthEnforcer contains no token signature verification logic — delegates entirely to AuthAndTenancy
- [ ] OpenAPI schema endpoints (`/api/v1/schema/`) bypass AuthEnforcer check

---

### REQ-L3-RA003-002: RBAC-Enforcement vor Delegation an ApplicationService

Der AuthEnforcer SHALL anhand des `AuthContext` (Rollen des Nutzers) und der angefragten Operation (HTTP-Methode + Ressourcentyp) prüfen, ob die Operation erlaubt ist, bevor der Controller an den ApplicationService delegiert. Nicht erlaubte Operationen SHALL mit `AuthError` (Typ: forbidden) beantwortet werden, der in HTTP 403 übersetzt wird.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Role `viewer`: GET allowed, POST/PATCH/DELETE on any resource → HTTP 403
- [ ] Role `editor`: GET/POST/PATCH/DELETE allowed on own workspace resources
- [ ] Role `admin`: all operations allowed
- [ ] Role `approver`: additionally allows workflow transitions to state `approved` (Extended preset only)
- [ ] RBAC check is performed before the Controller invokes ApplicationService
- [ ] RBAC rules are defined in a single, auditable configuration — not scattered across handlers

---

### REQ-L3-RA003-003: Tenant-Kontext-Extraktion und Propagation

Der AuthEnforcer SHALL die Tenant-ID aus dem validierten `AuthContext` extrahieren und als unveränderliche Eigenschaft des Request-Kontexts setzen. Er DARF die Tenant-ID nicht verändern, überschreiben oder umgehen. Der nachgelagerte ApplicationService-Aufruf MUSS die propagierte Tenant-ID enthalten.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `AuthContext.tenant_id` is extracted from token and attached to request context immutably
- [ ] AuthEnforcer does not allow caller to override tenant_id via query parameter or body field
- [ ] ApplicationService invocation includes tenant_id sourced exclusively from AuthContext
- [ ] Unit test: token with tenant_id=A cannot access resources of tenant_id=B

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
