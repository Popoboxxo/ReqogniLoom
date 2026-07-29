---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T00:00:00Z"
schema_version: "1.0.0"
---

# L3 AuthenticationService Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-AT-001_AuthenticationService
> **Parent:** L2_AuthAndTenancySystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der AuthenticationService ist der einzige Einstiegspunkt für Identitätsvalidierung. Er ist verantwortlich für:
- JWT Bearer-Token-Validierung (Signatur, Ablaufzeit, Aussteller)
- API-Key-Validierung mit Timing-Attack-Resistenz
- API-Key-Lifecycle-Management (Create, List, Revoke)
- Standardisierte Fehlerantworten für Auth-Fehler
- Erzeugung von `IdentityClaims` als Output für nachgelagerte Komponenten

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`AuthenticationService` (Hauptklasse):** Public API für `validate_bearer_token()`, `validate_api_key()`, `create_api_key()`, `list_api_keys()`, `revoke_api_key()`.
- **`BearerTokenValidator` (Module):** JWT-Signaturprüfung, Claims-Validierung, Expiration-Check.
- **`ApiKeyValidator` (Module):** SHA-256-Hash-Vergleich via `hmac.compare_digest()`, Revocation-Check.
- **`ApiKeyGenerator` (Module):** Generiert `rf_<40 hex chars>` Format, berechnet SHA-256-Hash.
- **`IdentityClaimsBuilder` (Module):** Konstruiert `IdentityClaims` Datenstruktur.
- **`ErrorResponseFormatter` (Module):** Standardisierte Fehlerantworten mit optional Deutsch/Englisch.
- **`IdentityClaims` / `ApiKeyDTO`:** Datenstrukturen.

### 2.2 Datenstrukturen

- **IdentityClaims (output):**
  ```python
  {
    "user_id": "uuid",
    "tenant_id": "uuid",
    "roles": ["editor", "approver"],
    "auth_method": "bearer_token" | "api_key",
    "api_key_id": "uuid" | null  # null für Bearer-Token
  }
  ```

- **ApiKey-Entity:**
  - `id`: UUID (Primary Key)
  - `user_id`: UUID (Foreign Key)
  - `name`: String (z.B. "CI/CD Pipeline")
  - `key_hash`: String (SHA-256, `sha256:<hex>`)
  - `revoked_at`: DateTime (nullable)
  - `created_at`: DateTime
  - `last_used_at`: DateTime (nullable)

- **JWT-Payload (erwartet):**
  ```json
  {
    "user_id": "uuid",
    "tenant_id": "uuid",
    "roles": ["..."],
    "exp": "<Unix-Timestamp>",
    "iss": "<Aussteller>",
    "aud": "<Zielgruppe>"
  }
  ```

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-AT001-001 (JWT-Validierung) | `validate_bearer_token(token)`: JWT.decode() mit Secret, prüfe `exp`, `iss`, `aud`. Bei Fehler: HTTP 401 + standardisierte Fehlerantwort. Bei Erfolg: IdentityClaims. |
| REQ-L3-AT001-002 (API-Key-Validierung mit Timing-Resistenz) | `validate_api_key(key)`: (1) Key-Hash berechnen, (2) `hmac.compare_digest(computed_hash, stored_hash)`, (3) Revocation-Status prüfen. Bei Match + nicht revoked: IdentityClaims. |
| REQ-L3-AT001-003 (API-Key-Lifecycle) | `create_api_key(user_id, name, ctx)`: Generiere `rf_<40 hex>`, berechne Hash, speichere + gebe Klartext zurück (nur 1x). `list_api_keys()`: Nur Metadaten. `revoke_api_key(key_id)`: Setze revoked_at + sofortige Wirkung. |
| REQ-L3-AT001-004 (Standardisierte Fehler) | Alle 401 Responses: `{"error": "<code>", "message": "<localized>", "doc_url": "..."}`. Keine Token-Payloads oder Hashes in Fehlermeldungen. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-AT-EXT-IN-001:** REST API / React Frontend — `Authorization: Bearer <JWT>` Header
  - **IF-AT-EXT-IN-002:** MCP Server / AI-Agent — `X-API-Key: <key>` oder `Authorization: Bearer <key>` Header

- **Ausgänge (Outbound):**
  - **IF-AT-INT-001:** `COMP-AT-002` (AuthorizationService) — `IdentityClaims` (user_id, roles, auth_method)
  - **IF-AT-INT-002:** `COMP-AT-003` (TenantContextService) — `IdentityClaims` (user_id, tenant_id)
  - **IF-AT-EXT-OUT-003:** REST API Adapter — Berechtigungsentscheid (HTTP 401 bei Auth-Fehler)
  - **IF-AT-EXT-OUT-004:** Django ORM — User- und API-Key-Lookup

---

## 5. Architectural Rationale

**ADR-L3-AT001-01 — JWT als Primary Bearer Token Mechanism**

*Entscheidung:* Bearer-Token basiert auf JWT (not Opaque Session Tokens). JWT enthält Claims (user_id, tenant_id, roles) im Token selbst, keine Backend-Session.

*Rationale:*
- **Annahme:** REQ-L3-AT001-001 fordert Signaturprüfung und Claims-Validierung.
- **Gewählter Ansatz:** JWT ermöglicht stateless Authentication, besser für distributed Systeme / Microservices.
- **Abgelehnte Alternative:** Opaque Session-Tokens (store Session in Redis/DB) → statefulness, zusätzliche Lookups.
- **Erfüllt REQ-L3-AT001-001:** Stateless, skalierbar.

---

**ADR-L3-AT001-02 — hmac.compare_digest für API-Key-Vergleich**

*Entscheidung:* API-Key-Hash-Vergleich nutzt `hmac.compare_digest()`, nicht `==`. Dies verhindert Timing-Attacks.

*Rationale:*
- **Annahme:** REQ-L3-AT001-002 fordert Timing-Attack-Resistenz.
- **Gewählter Ansatz:** `hmac.compare_digest()` ist in Python stdlib, konstante Laufzeit unabhängig von String-Länge oder frühe Mismatches.
- **Abgelehnte Alternative:** Naiver `==`-Vergleich → früh exit bei Mismatch, zeitabhängig (Timing-Side-Channel).
- **Erfüllt REQ-L3-AT001-002:** Sicherheit gegen Timing-Attacks.

---

**ADR-L3-AT001-03 — API-Key-Format mit Prefix für Identifizierbarkeit**

*Entscheidung:* Generierte API-Keys folgen dem Format `rf_<40 random hexchars>`. Der `rf_`-Prefix ermöglicht sofortige Identifizierung im Code/Logs.

*Rationale:*
- **Annahme:** REQ-L3-AT001-003 fordert ein Format. Das Prefix `rf_` ist Projekt-Präfix (ReqFlow).
- **Gewählter Ansatz:** `rf_` + 40 hex chars = 42 chars total, ausreichend für Sicherheit (2^160 Kombinationen).
- **Abgelehnte Alternative:** Vollständig zufälliger String → schwer zu identifizieren ob es ein Key oder Garbage ist.
- **Erfüllt REQ-L3-AT001-003:** Klare Identifizierbarkeit, ausreichende Entropie.

---

**ADR-L3-AT001-04 — Localisierte Fehlerantworten via Accept-Language Header**

*Entscheidung:* Fehlerantworten werden in Deutsch und Englisch bereitgestellt, ausgewählt via `Accept-Language`-Header.

*Rationale:*
- **Annahme:** Internationales Team; verschiedene Nutzer sprechen verschiedene Sprachen.
- **Gewählter Ansatz:** ErrorResponseFormatter inspiziert Header, gibt entsprechende Nachricht zurück.
- **Abgelehnte Alternative:** Nur Englisch → Usability-Problem für deutschsprachige Nutzer.
- **Erfüllt REQ-L3-AT001-004:** Lokalisierung ist gewährleistet.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*


## Derived L3 Requirements for Unmapped L2

### REQ-L3-AT001-U000: Auto-derived from REQ-L2-AUT-008
Abgeleitet von: REQ-L2-AUT-008

### REQ-L3-AT001-U001: Auto-derived from REQ-L2-AUT-005
Abgeleitet von: REQ-L2-AUT-005

### REQ-L3-AT001-U002: Auto-derived from REQ-L2-AUT-001
Abgeleitet von: REQ-L2-AUT-001

### REQ-L3-AT001-U003: Auto-derived from REQ-L2-AUT-002
Abgeleitet von: REQ-L2-AUT-002

### REQ-L3-AT001-U004: Auto-derived from REQ-L2-AUT-013
Abgeleitet von: REQ-L2-AUT-013

### REQ-L3-AT001-U005: Auto-derived from REQ-L2-AUT-003
Abgeleitet von: REQ-L2-AUT-003

### REQ-L3-AT001-U006: Auto-derived from REQ-L2-AUT-007
Abgeleitet von: REQ-L2-AUT-007

### REQ-L3-AT001-U007: Auto-derived from REQ-L2-AUT-006
Abgeleitet von: REQ-L2-AUT-006

### REQ-L3-AT001-U008: Auto-derived from REQ-L2-AUT-009
Abgeleitet von: REQ-L2-AUT-009

### REQ-L3-AT001-U009: Auto-derived from REQ-L2-AUT-010
Abgeleitet von: REQ-L2-AUT-010

### REQ-L3-AT001-U010: Auto-derived from REQ-L2-AUT-004
Abgeleitet von: REQ-L2-AUT-004

### REQ-L3-AT001-U011: Auto-derived from REQ-L2-AUT-014
Abgeleitet von: REQ-L2-AUT-014

### REQ-L3-AT001-U012: Auto-derived from REQ-L2-AUT-012
Abgeleitet von: REQ-L2-AUT-012

### REQ-L3-AT001-U013: Auto-derived from REQ-L2-AUT-011
Abgeleitet von: REQ-L2-AUT-011
