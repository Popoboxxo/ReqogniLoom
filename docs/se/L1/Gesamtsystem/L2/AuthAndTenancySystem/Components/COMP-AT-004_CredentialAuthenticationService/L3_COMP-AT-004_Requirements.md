# L3 CredentialAuthenticationService Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-AT-004 — CredentialAuthenticationService
> **Parent-System:** AuthAndTenancySystem (L2)
> **Status:** Entwurf (als-gebaut — Code existiert, Tests grün)

---

## Verantwortlichkeit

Credential-Verifikation (Benutzername/Passwort, constant-time, enumeration-resistent), Rollen-Auflösung und Ausstellung eines `BearerTokenAuthentication`-kompatiblen HS256-JWT. Einziger Eintrittspunkt für die **Erzeugung** eines Tokens aus Credentials (Gegenstück zu COMP-AT-001, das Tokens validiert). Als-gebaut: `PasswordAuthenticationService`.

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-AT-011 | Credential-Verifikation gegen Passwort-Hash, constant-time |
| REQ-L2-AT-012 | Token-Ausgabe mit BearerTokenAuthentication-Kompatibilität |
| REQ-L2-AT-014 | Passwort-Hash-Storage-Vertrag (PBKDF2, kein Klartext) |
| REQ-L2-AT-016 | Keine Konto-Enumeration (einheitlicher Fehlercode) |

> REQ-L2-AT-013 (öffentlicher Login-Endpunkt) und REQ-L2-AT-015 (`/auth/me/`) sind RestApiAdapter-seitige Verantwortungen (`LoginView`/`MeView`), die diese Komponente konsumieren.

## Interne / geteilte Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AT-INT-004 | Format-Kontrakt | COMP-AT-001 (AuthenticationService) | Ausgestellte JWT-Claims `{user_id, tenant_id, roles, iat, exp, iss?, aud?}` deckungsgleich mit dem von `validate_bearer_token` konsumierten Set; geteilte `AUTH_JWT_*`-Settings + `encode_hs256` |

## Externe Schnittstellen (Komponente an Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AT-EXT-IN-003 | eingehend | RestApiAdapter `LoginView` (öffentlich) | `authenticate_credentials(username, password)`, `resolve_roles(user)`, `issue_token(user, roles)` |
| IF-AT-EXT-OUT-004 | ausgehend | PersistenceLayer | `User`-Lookup + `check_password`; `UserRole.unscoped`-Rollen-Lookup |
| IF-AT-EXT-OUT-005 | ausgehend | RestApiAdapter `LoginView` | Ausgestellter Token + `{user, tenant_id, roles}` bzw. `AuthenticationFailed("invalid_token")` |

---

## L3 Komponenten-Anforderungen

### REQ-L3-AT004-001: Constant-Time-Credential-Verifikation

Der CredentialAuthenticationService SHALL ein Benutzername/Passwort-Paar gegen den gespeicherten Passwort-Hash verifizieren und den aktiven Nutzer auflösen. Existiert der Nutzer nicht, SHALL dennoch ein Dummy-Hash-Vergleich erfolgen, sodass die Timing-Kurve von „Nutzer unbekannt" und „Passwort falsch" vergleichbar bleibt.

**Priority:** mandatory
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Traceability:** REQ-L2-AT-011, REQ-L2-AT-016
**Acceptance Criteria:**
- [ ] Gültige Credentials eines aktiven Nutzers → `User` zurückgegeben
- [ ] Falsches Passwort → `AuthenticationFailed("invalid_token")`
- [ ] Unbekannter Benutzername → Dummy-`check_password` + `AuthenticationFailed("invalid_token")`
- [ ] Inaktives Konto → `AuthenticationFailed("invalid_token")`
- [ ] Verifikation über Djangos konstant-zeitige `check_password`

---

### REQ-L3-AT004-002: BearerToken-kompatible Token-Ausgabe

Der CredentialAuthenticationService SHALL nach erfolgreicher Verifikation einen HS256-JWT ausstellen, dessen Claim-Set exakt dem von COMP-AT-001 konsumierten entspricht (`user_id`, `tenant_id`, `roles`, `iat`, `exp`, optional `iss`/`aud`), gelesen aus `AUTH_JWT_*`-Settings. Der Token SHALL durch `BearerTokenAuthentication` (REQ-L2-AT-001) akzeptiert werden.

**Priority:** mandatory
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Traceability:** REQ-L2-AT-012
**Acceptance Criteria:**
- [ ] Token-Claims enthalten `{user_id, tenant_id, roles, iat, exp}` (+ `iss`/`aud` falls konfiguriert)
- [ ] Token wird von REQ-L2-AT-001 akzeptiert (Round-Trip) und liefert korrekten RBAC-/Tenant-Kontext
- [ ] Kein konfiguriertes JWT-Secret → `AuthenticationFailed("invalid_token")`
- [ ] Nutzer ohne Tenant → `AuthenticationFailed("invalid_token")`
- [ ] Rollen via `UserRole.unscoped` (nur nicht-suspendierte), dedupliziert, sortiert, lower-case

---

### REQ-L3-AT004-003: Passwort-Hash-Storage-Vertrag

Der CredentialAuthenticationService SHALL ausschließlich über `User.set_password`/`check_password` auf das Passwort zugreifen; der gespeicherte Wert SHALL ein gesalzener Hash (PBKDF2, Django-Hasher) sein. Klartext-Passwörter SHALL nie in API-Responses, Logs oder Audit-Einträgen erscheinen.

**Priority:** mandatory
**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Traceability:** REQ-L2-AT-014
**Acceptance Criteria:**
- [ ] `User.password` enthält ausschließlich Hash-Werte (`pbkdf2_sha256$...`)
- [ ] Login-/Me-Response enthält kein Passwortfeld
- [ ] Kein Klartext in Logs/Audit
- [ ] Leeres `password` → `check_password` liefert `False`

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-25*
*Als-gebaut-Spiegelung von PasswordAuthenticationService*
*Designation: component (terminal) — decomposition_status: terminal*


## Master Traceability Matrix

| REQ-L3 | Abgeleitet von REQ-L2 |
|---------|----------------------|
| REQ-L3-AT004-001 | REQ-L2-AT-011, REQ-L2-AT-016 |
| REQ-L3-AT004-002 | REQ-L2-AT-012 |
| REQ-L3-AT004-003 | REQ-L2-AT-014 |

