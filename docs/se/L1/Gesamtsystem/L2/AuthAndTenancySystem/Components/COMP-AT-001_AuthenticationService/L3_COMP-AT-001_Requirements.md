# L3 AuthenticationService Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-AT-001 — AuthenticationService
> **Parent-System:** AuthAndTenancySystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Bearer-Token-Validierung (JWT), API-Key-Validierung (SHA-256), Timing-Attack-resistenter Vergleich. Die Komponente ist der einzige Eintrittspunkt für Identitätsnachweise; sie liefert `IdentityClaims` an nachgelagerte Komponenten.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-AT-001 | Bearer-Token-Validierung (JWT): Signatur, Ablaufzeit, Aussteller |
| REQ-L2-AT-002 | API-Key-Validierung gegen SHA-256-Hash, Timing-Attack-Resistenz |
| REQ-L2-AT-007 | Auth-Middleware-Interception aller REST/MCP-Endpunkte |
| REQ-L2-AT-009 | API-Key-Lifecycle: Erstellung, Auflistung, Widerruf |
| REQ-L2-AT-010 | Standardisierte Fehlerantworten für Auth-Fehler |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AT-INT-001 | ausgehend | COMP-AT-002 (AuthorizationService) | `IdentityClaims {user_id, roles, auth_method}` |
| IF-AT-INT-002 | ausgehend | COMP-AT-003 (TenantContextService) | `IdentityClaims {user_id, tenant_id}` |

## Externe Schnittstellen (Komponente an Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AT-EXT-IN-001 | eingehend | RestApiAdapter / ReactFrontend | Bearer Token (JWT) im `Authorization`-Header |
| IF-AT-EXT-IN-002 | eingehend | McpServer / AI-Agent | API Key in `X-API-Key` oder `Authorization: Bearer` |
| IF-AT-EXT-OUT-003 | ausgehend | RestApiAdapter / McpServer | Berechtigungsentscheid (allow/deny) — HTTP 401 bei Fehler |
| IF-AT-EXT-OUT-004 | ausgehend | PersistenceLayer | User- und API-Key-Lookup (Django ORM) |

---

## L3 Komponenten-Anforderungen

### REQ-L3-AT001-001: JWT-Signatur- und Claims-Validierung

Der AuthenticationService SHALL eingehende JWT-Bearer-Tokens validieren — Signaturprüfung mit dem konfigurierten Secret/Public-Key, Ablaufzeit (`exp`), Aussteller (`iss`) und Zielgruppe (`aud`). Ungültige oder abgelaufene Tokens SHALL sofort mit dem entsprechenden Fehlercode zurückgewiesen werden, ohne dass nachgelagerte Komponenten erreicht werden.

**Priority:** mandatory
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-AT-001, REQ-L2-AT-007
**Acceptance Criteria:**
- [ ] Valid JWT with correct signature → `IdentityClaims` produced and forwarded to COMP-AT-002 and COMP-AT-003
- [ ] Expired JWT (`exp` in the past) → HTTP 401 `{"error": "token_expired"}`
- [ ] JWT with invalid signature → HTTP 401 `{"error": "invalid_signature"}`
- [ ] Missing `Authorization` header on protected endpoint → HTTP 401 `{"error": "authentication_required"}`
- [ ] `/health`, `/api/docs`, `/api/openapi.json` pass through without token → HTTP 200

---

### REQ-L3-AT001-002: API-Key-Validierung mit Timing-Attack-Resistenz

Der AuthenticationService SHALL API Keys ausschließlich durch Vergleich des SHA-256-Hashes des eingehenden Keys mit dem gespeicherten Hash-Wert validieren. Der Vergleich SHALL mittels `hmac.compare_digest` in konstanter Laufzeit erfolgen, um Timing-Angriffe auszuschließen. Widerrufene Keys SHALL sofort abgewiesen werden.

**Priority:** mandatory
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-AT-002, REQ-L2-AT-009
**Acceptance Criteria:**
- [ ] Valid API Key → User and tenant resolved, `IdentityClaims` produced
- [ ] Unknown key → HTTP 401 `{"error": "invalid_api_key"}`
- [ ] Revoked key → HTTP 401 `{"error": "api_key_revoked"}`
- [ ] Comparison always uses `hmac.compare_digest` (verifiable via code review)
- [ ] No plain-text key value stored or logged at any point

---

### REQ-L3-AT001-003: API-Key-Lifecycle-Verwaltung

Der AuthenticationService SHALL CRUD-Operationen für API Keys bereitstellen: Erstellung (Rückgabe des Klartexts genau einmal), Auflistung (nur Metadaten), und sofort wirksamen Widerruf. Format: `rf_<40 zufällige Zeichen>`. Pro Nutzer maximal 10 aktive Keys.

**Priority:** mandatory
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-AT-009
**Acceptance Criteria:**
- [ ] Key creation → plain-text returned in response body exactly once, SHA-256 hash stored in DB
- [ ] Key listing → returns metadata only (id, name, created_at, last_used), no plain-text
- [ ] Key revocation → subsequent request with that key → HTTP 401 within same request cycle
- [ ] Key format matches `rf_[a-zA-Z0-9]{40}`
- [ ] Creating an 11th key when 10 are active → error response

---

### REQ-L3-AT001-004: Standardisierte Auth-Fehlerantworten

Der AuthenticationService SHALL alle Authentifizierungsfehler im einheitlichen Format `{"error": "<code>", "message": "...", "doc_url": "..."}` zurückgeben. Fehlermeldungen SHALL in Deutsch und Englisch verfügbar sein. Keine sensiblen Informationen (Token-Inhalt, Hash-Werte, interne Stack-Traces) SHALL in Fehlerantworten enthalten sein.

**Priority:** desired
**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L2-AT-010
**Acceptance Criteria:**
- [ ] All 401 responses contain `error`, `message`, and `doc_url` fields
- [ ] Error messages available in DE and EN via `Accept-Language` header
- [ ] No token payload, hash values, or stack traces in error responses
- [ ] Error codes are one of: `token_expired`, `invalid_signature`, `authentication_required`, `invalid_api_key`, `api_key_revoked`

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*


## Master Traceability Matrix

| REQ-L3 | Abgeleitet von REQ-L2 |
|---------|----------------------|
| REQ-L3-AT001-001 | REQ-L2-AT-001, REQ-L2-AT-007 |
| REQ-L3-AT001-002 | REQ-L2-AT-002, REQ-L2-AT-009 |
| REQ-L3-AT001-003 | REQ-L2-AT-009 |
| REQ-L3-AT001-004 | REQ-L2-AT-010 |

