---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T10:10:00Z"
schema_version: "1.0.0"
---

# L3 AuthEnforcer Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-RA-003_AuthEnforcer
> **Parent:** L2_RestApiAdapterSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der AuthEnforcer ist die zentrale Authentifizierungs- und Autorisierungsschicht der REST-API. Er extrahiert Bearer Tokens aus HTTP-Headers, delegiert Token-Validierung an AuthAndTenancy, durchläuft rollenbasierte Zugriffskontrolle (RBAC), propagiert den Tenant-Kontext unveränderlich in den Request-Scope und blockiert nicht-autorisierte Zugriffe mit spezifischen HTTP-Fehlercodes (401, 403).

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box hier die internen Software-Klassen und Module.

### 2.1 Klassen und Module

- **`AuthEnforcer` (Klasse):** Hauptklasse mit zwei Methoden: `extract_and_validate_token(headers) -> AuthContext | AuthError` und `enforce_rbac(auth_context, resource_type, method) -> AuthError | None`.
- **`TokenExtractor` (Klasse):** Utility für Bearer-Token-Extraktion aus `Authorization`-Header. Validiert Format `Bearer <token>`.
- **`RBACEnforcer` (Klasse):** Implementiert RBAC-Regeln. Nutzt Mapping {role → allowed_operations}. Operationen sind Tuples (resource_type, HTTP_method).
- **`AuthContext` (Pydantic Model):** Immutable nach Erstellung. Felder: {user_id, roles: List[str], tenant_id, token_claims: dict}.

### 2.2 Datenstrukturen

- **`AuthError` (Exception):** {error_code: "unauthorized"|"forbidden", message, details: dict}.
- **`TokenValidationResponse` (Pydantic Model):** Vom AuthAndTenancy-System: {valid, user_id, roles, tenant_id, claims}.
- **`RBACRule` (Dataclass):** {role: str, resource_type: str, allowed_methods: List[str]}.

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-RA003-001 (Token-Extraktion & Validierung) | TokenExtractor liest `Authorization`-Header. Fehlendes/ungültiges Format → AuthError. Delegation an AuthAndTenancy für Signature/Expiry-Prüfung. OpenAPI-Schema-Endpunkt wird bypassed. |
| REQ-L3-RA003-002 (RBAC-Enforcement) | RBACEnforcer prüft (role, resource_type, method)-Triple gegen konfigurierte Regeln. Nicht erlaubte → AuthError (forbidden, HTTP 403). Prüfung VOR ApplicationService-Aufruf. |
| REQ-L3-RA003-003 (Tenant-Kontext-Propagation) | AuthContext wird nach Validierung als immutable Objekt im Request-Scope gespeichert. tenant_id aus Token, darf nicht überschrieben werden. Nachgelagerte Services empfangen unveränderlichen tenant_id. |

---

## 4. Schnittstellen-Implementierung

**Eingänge (Inbound):**
- **IF-RA-INT-001:** Von COMP-RA-001 (HttpEndpointController): `enforce_auth(headers, path, method) -> AuthContext | AuthError`.

**Ausgänge (Outbound):**
- **IF-RA-EXT-OUT-004:** Zu AuthAndTenancy (ARCH-L1-011): `validate_token(token) -> TokenValidationResponse` und `get_rbac_rules() -> List[RBACRule]`.

---

## 5. Architectural Rationale

**ADR-L3-RA3-01 — AuthContext als immutable Wert-Objekt**

*Entscheidung:* AuthContext ist nach Token-Validierung unveränderlich (Pydantic frozen=True). Kein Nachträgliches Überschreiben von tenant_id möglich.

*Rationale:* Erfüllt REQ-L3-RA003-003 ("AuthContext.tenant_id is extracted from token and attached to request context immutably"). Verhindert Tenant-Injection-Angriffe. Alternative: Mutables Request-Dictionary → würde unsicheren Zugriff ermöglichen.

---

**ADR-L3-RA3-02 — RBAC-Regeln zentral konfiguriert, nicht hardcodiert**

*Entscheidung:* RBACEnforcer lädt Regeln aus persistenter Quelle (Config-Datei oder Cache), nicht Hardcoded.

*Rationale:* Erlaubt Änderungen ohne Code-Redployment. Erfüllt Testbarkeit (REQ-L3-RA003-002 "RBAC rules are defined in a single, auditable configuration"). Alternative: Hardcoded if/else → nicht wartbar bei 3+ Rollen.

---

**ADR-L3-RA3-03 — Schema-Endpunkt umgeht Authentifizierung**

*Entscheidung:* `/api/v1/schema/` und `/api/v1/schema/swagger-ui/` erhalten spezielle Behandlung: AuthEnforcer yields für diese Pfade.

*Rationale:* Ermöglicht API-Discovery vor Authentifizierung (Acceptance Criterion "Schema endpoint is accessible without authentication"). Alternative: Alle Endpunkte geschützt → würde Client-onboarding erschweren.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
