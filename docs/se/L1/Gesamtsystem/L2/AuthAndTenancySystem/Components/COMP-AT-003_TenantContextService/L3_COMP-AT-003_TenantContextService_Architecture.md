---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T00:00:00Z"
schema_version: "1.0.0"
---

# L3 TenantContextService Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-AT-003_TenantContextService
> **Parent:** L2_AuthAndTenancySystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der TenantContextService ist die Tenant-Auflösungs- und Kontext-Injektions-Komponente. Er ist verantwortlich für:
- Tenant-Extraktion aus IdentityClaims
- Validierung und Auflösung des Tenants (DB-Lookup)
- Injektion des TenantContext in den Django Request-Context
- Erzeugung eines immutablen Auth-Kontexts für nachgelagerte Systeme
- Weitergabe an AuthorizationService

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`TenantContextService` (Hauptklasse):** Public API für `resolve_tenant_context()`.
- **`TenantResolver` (Module):** Lädt Tenant-Metadaten aus DB, validiert Existenz.
- **`RequestContextInjector` (Module):** Speichert TenantContext in Django Request-Context (thread-safe via contextvars oder request.user).
- **`AuthContextBuilder` (Module):** Erzeugt immutablen Auth-Kontext `{user_id, tenant_id, active_roles, auth_method, api_key_id}`.
- **`TenantContext` / `AuthContext`:** Datenstrukturen (frozen/immutable).

### 2.2 Datenstrukturen

- **TenantContext (output):**
  ```python
  @dataclass(frozen=True)  # immutable
  class TenantContext:
    tenant_id: UUID
    tenant_name: str
    features: Dict[str, bool]  # optional
  ```

- **AuthContext (fully immutable):**
  ```python
  @dataclass(frozen=True)  # immutable
  class AuthContext:
    user_id: UUID
    tenant_id: UUID
    active_roles: List[str]
    auth_method: str  # "bearer_token" | "api_key"
    api_key_id: UUID | None
  ```

- **Tenant-Entity (DB):**
  - `id`: UUID (Primary Key)
  - `name`: String
  - `plan`: String (minimal|standard|extended)
  - `created_at`: DateTime

- **User-TenantMembership-Entity:**
  - `user_id`: UUID
  - `tenant_id`: UUID
  - `joined_at`: DateTime

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-AT003-001 (Tenant-Extraktion und Validierung) | `resolve_tenant_context(identity_claims, ctx)`: TenantResolver lädt Tenant via tenant_id. Falls nicht existent → HTTP 500 `{"error": "tenant_resolution_failed"}`. Bei Erfolg: TenantContext zurück. |
| REQ-L3-AT003-002 (Request-Context-Injektion) | RequestContextInjector speichert TenantContext in Django request.user.tenant (oder contextvars). Nach Request: cleanup (kein Leak). Custom Manager nutzt automatisch filter(tenant_id=<active>). |
| REQ-L3-AT003-003 (Immutabler Auth-Kontext) | AuthContextBuilder: frozen dataclass mit user_id, tenant_id, active_roles, auth_method, api_key_id. Attempt to mutate → FrozenInstanceError. Übergabe an ApplicationService, WorkflowEngine, AuditLog. |
| REQ-L3-AT003-004 (Kontext-Weitergabe an AuthorizationService) | Nach Tenant-Auflösung: TenantContext an AuthorizationService übergeben. Nur mit aktiven TenantContext erfolgen Authorization-Checks. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-AT-INT-002:** `COMP-AT-001` (AuthenticationService) — `IdentityClaims {user_id, tenant_id}`

- **Ausgänge (Outbound):**
  - **IF-AT-INT-003:** `COMP-AT-002` (AuthorizationService) — `TenantContext {tenant_id, tenant_name}`
  - **IF-AT-EXT-OUT-001:** ApplicationService — Auth-Kontext `{user_id, tenant_id, active_roles, auth_method, api_key_id}`
  - **IF-AT-EXT-OUT-004:** Django ORM (Custom Manager) — Tenant-Filter-Injektion

---

## 5. Architectural Rationale

**ADR-L3-AT003-01 — DB-Lookup für Tenant-Auflösung statt Token-Trust**

*Entscheidung:* Tenant-ID wird nicht direkt aus dem Token/API-Key vertraut, sondern gegen DB validiert. DB-Lookup liefert authoritative Tenant-Metadaten.

*Rationale:*
- **Annahme:** REQ-L3-AT003-001 fordert Validierung. Token/Keys können gestohlen sein; DB ist authoritative Quelle.
- **Gewählter Ansatz:** TenantResolver führt SELECT durch, nicht nur Token-Extraktion.
- **Abgelehnte Alternative:** Blind-Trust in Token → Sicherheitsrisiko bei Key-Leakage.
- **Erfüllt REQ-L3-AT003-001:** Validierung ist rigoros.

---

**ADR-L3-AT003-02 — Frozen Dataclasses für Immutabilität**

*Entscheidung:* AuthContext und TenantContext sind Python frozen dataclasses (`@dataclass(frozen=True)`). Versuch, Felder zu mutieren, wirft `FrozenInstanceError`.

*Rationale:*
- **Annahme:** REQ-L3-AT003-003 fordert Immutabilität nach Erzeugung. Mutation würde Sicherheitszustände invalidieren.
- **Gewählter Ansatz:** Python frozen dataclasses sind Standard, Low-Overhead.
- **Abgelehnte Alternative:** Manuelles Property-Locking → fehleranfällig.
- **Erfüllt REQ-L3-AT003-003:** Immutabilität ist erzwungen.

---

**ADR-L3-AT003-03 — Custom Manager mit automatischem Tenant-Filter**

*Entscheidung:* Django ORM Model für alle Entities nutzen einen Custom Manager, der automatisch `filter(tenant_id=<active>)` auf ALLE Queries anwendet.

*Rationale:*
- **Annahme:** REQ-L3-AT003-002 fordert automatische Tenant-Isolation. Manuelles Filtern in jedem Query ist fehleranfällig.
- **Gewählter Ansatz:** Override von `get_queryset()` im Custom Manager → Tenant-Filter ist transparent.
- **Abgelehnte Alternative:** Manuelle Tenant-Filter in jedem Service-Call → Vergesslichkeit, Data-Leak-Risiko.
- **Erfüllt REQ-L3-AT003-002:** Isolation ist systematisch erzwungen.

---

**ADR-L3-AT003-04 — Request-Context Cleanup nach Request**

*Entscheidung:* TenantContext wird am Anfang eines Requests injiziert, am Ende (success oder exception) aus dem Context gelöscht.

*Rationale:*
- **Annahme:** REQ-L3-AT003-002 fordert: "Context ist nach Request bereinigt werden. Kein Context-Leak zwischen Requests."
- **Gewählter Ansatz:** Django Middleware mit `process_request()` (inject) und `process_response()` / `process_exception()` (cleanup).
- **Abgelehnte Alternative:** Manuelle cleanup in jedem View — Boilerplate, fehlerträchtig.
- **Erfüllt REQ-L3-AT003-002:** Keine Context-Leaks.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
