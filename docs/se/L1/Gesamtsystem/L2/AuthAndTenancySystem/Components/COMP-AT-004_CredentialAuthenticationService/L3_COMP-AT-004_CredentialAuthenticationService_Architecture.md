---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-25T00:00:00Z"
schema_version: "1.0.0"
---

# L3 CredentialAuthenticationService Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-AT-004_CredentialAuthenticationService
> **Parent:** L2_AuthAndTenancySystem_Architecture.md
> **Datum:** 2026-06-25
> **Status:** entworfen (als-gebaut — Code existiert, Tests grün)
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der CredentialAuthenticationService ist der einzige Einstiegspunkt für die **Erzeugung** eines Zugriffstokens aus Benutzername/Passwort. Er ist verantwortlich für:
- Verifikation eines Benutzername/Passwort-Paars gegen den gespeicherten Passwort-Hash (PBKDF2, Django-Hasher) in (nahezu) konstanter Laufzeit — enumeration-resistent (kein Timing-/Response-Unterschied zwischen „Nutzer unbekannt", „Passwort falsch", „Konto inaktiv").
- Auflösung der aktiven (nicht suspendierten) Rollen eines Nutzers.
- Ausstellung eines HS256-JWT, dessen Claim-Set **exakt** dem entspricht, das COMP-AT-001 (`validate_bearer_token`) konsumiert — garantiert den Token-Round-Trip durch `BearerTokenAuthentication`.

Abgrenzung zu COMP-AT-001: COMP-AT-001 **konsumiert/validiert** Tokens (eingehende Anfragen), COMP-AT-004 **produziert** Tokens (ein öffentlicher Login-Endpunkt). Siehe ADR-AT-05 (L2).

**Als-gebaut-Mapping:** `auth_tenancy/services/password_authentication.py::PasswordAuthenticationService`.

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`PasswordAuthenticationService` (Hauptklasse):** Public API:
  - `authenticate_credentials(username, password) -> User`
  - `resolve_roles(user) -> tuple[str, ...]`
  - `issue_token(user, roles=None) -> str`
- **Konstantzeit-Helfer `_dummy_password_hash()`:** liefert einen einmalig (lazy, prozessweit gecachten) via Django-Hasher erzeugten Wegwerf-Hash, damit der „Nutzer unbekannt"-Pfad denselben (bewusst teuren) `check_password`-Codepfad durchläuft wie ein echter Vergleich.
- **Token-Bausteine (geteilt mit COMP-AT-001):** `auth_tenancy.jwt_tokens.encode_hs256`, `AUTH_JWT_*`-Settings.
- **Fehler:** `auth_tenancy.errors.AuthenticationFailed("invalid_token")` — einheitlicher Code für alle Fehlerpfade.

### 2.2 Datenstrukturen

- **JWT-Claims (output) — identisch zum von COMP-AT-001 erwarteten Set:**
  ```json
  {
    "user_id": "uuid",
    "tenant_id": "uuid",
    "roles": ["editor", "approver"],
    "iat": "<Unix-Timestamp>",
    "exp": "<Unix-Timestamp>",
    "iss": "<Aussteller, falls AUTH_JWT_ISSUER gesetzt>",
    "aud": "<Zielgruppe, falls AUTH_JWT_AUDIENCE gesetzt>"
  }
  ```
- **User-Passwort-Storage (Vertrag mit PersistenceLayer, REQ-L2-AT-014):**
  - `User.password`: `CharField(max_length=128)`, gesalzener Hash im Django-Hasher-Format (`pbkdf2_sha256$...`), leer = „kein nutzbares Passwort". Zugriff ausschließlich über `set_password`/`check_password`.

### 2.3 Konfiguration (kein Secret im Code)

`AUTH_JWT_SECRET`, `AUTH_JWT_ISSUER`, `AUTH_JWT_AUDIENCE`, `AUTH_JWT_TTL_SECONDS` (Default 43200 = 12 h) aus Django-Settings. Aussteller- und Validatorseite lesen dieselben Settings — das garantiert den Round-Trip.

---

## 3. Erfüllung der Anforderungen

| REQ-L2 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L2-AT-011 (Credential-Verifikation, constant-time) | `authenticate_credentials`: User-Lookup; bei `None` Dummy-`check_password` + `AuthenticationFailed`; sonst `user.check_password`; dann `is_active`-Check. Einheitlicher Fehlercode. |
| REQ-L2-AT-012 (Token-Ausgabe, BearerToken-Kompatibilität) | `issue_token`: Claims `{user_id, tenant_id, roles, iat, exp}` (+ `iss`/`aud` falls konfiguriert), signiert mit `encode_hs256` und `AUTH_JWT_SECRET`. Guard: kein Secret / kein Tenant → `AuthenticationFailed`. |
| REQ-L2-AT-014 (Passwort-Hash-Storage-Vertrag) | Nutzt `User.set_password`/`check_password` (Django-Hasher, PBKDF2). Kein Klartext in Response (`_user_payload` ohne Passwortfeld), Logs oder Audit. |
| REQ-L2-AT-016 (keine Konto-Enumeration) | Einheitlicher Code `invalid_token`/HTTP 401 für alle drei Fehlerfälle; Timing durch Dummy-Hash angeglichen (REQ-L2-AT-011). |

> REQ-L2-AT-013 (öffentlicher Endpunkt) und REQ-L2-AT-015 (`/auth/me/`) werden RestApiAdapter-seitig durch `LoginView`/`MeView` realisiert; COMP-AT-004 liefert dafür die Verifikations-/Token-Funktion (IF-AT-EXT-IN-003 / IF-AT-EXT-OUT-005).

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-AT-EXT-IN-003:** RestApiAdapter `LoginView` (öffentlich) → `authenticate_credentials(username, password)`, `resolve_roles(user)`, `issue_token(user, roles)`.

- **Ausgänge (Outbound):**
  - **IF-AT-EXT-OUT-004:** PersistenceLayer (Django ORM) — `User`-Lookup + `check_password`; `UserRole.unscoped`-Lookup für Rollen.
  - **IF-AT-EXT-OUT-005:** RestApiAdapter `LoginView` — ausgestellter Token bzw. `AuthenticationFailed("invalid_token")`.
  - **IF-AT-INT-004 (Format-Kontrakt, nicht Aufruf):** Claim-Set deckungsgleich mit COMP-AT-001 (`validate_bearer_token`); geteilte `AUTH_JWT_*`-Settings + `encode_hs256`.

---

## 5. Architectural Rationale

**ADR-L3-AT004-01 — Constant-Time-Verifikation mit Dummy-Hash gegen Enumeration/Timing**

*Entscheidung:* Existiert der Benutzer nicht, wird dennoch ein `check_password` gegen einen prozessweit gecachten Dummy-Hash ausgeführt, bevor `AuthenticationFailed` geworfen wird.

*Rationale:*
- **Annahme:** REQ-L2-AT-011/016 fordern, dass „Nutzer unbekannt" und „Passwort falsch" zeitlich und in der Response nicht unterscheidbar sind.
- **Gewählter Ansatz:** Gleicher (teurer) Hashing-Codepfad in allen Fehlerfällen; einheitlicher Fehlercode `invalid_token`.
- **Abgelehnte Alternative:** Frühes `return`/„user not found" ohne Hash-Berechnung → messbarer Timing-Side-Channel + implizite Konto-Enumeration.

---

**ADR-L3-AT004-02 — Token-Format-Wiederverwendung statt eigener Claim-Struktur**

*Entscheidung:* `issue_token` erzeugt exakt das Claim-Set, das `AuthenticationService.validate_bearer_token` (COMP-AT-001) konsumiert, über geteilte Settings/Routine.

*Rationale:*
- **Annahme:** arch_trigger REQ-L1-033 verlangt Round-Trip-Kompatibilität mit der bestehenden Token-Schicht.
- **Gewählter Ansatz:** Eine einzige Quelle für Format + Secret (`AUTH_JWT_*`, `encode_hs256`). Der via Login erhaltene Token authentifiziert sofort alle geschützten REST-/MCP-Endpunkte; RBAC und Tenant-Kontext bleiben unverändert.
- **Abgelehnte Alternative:** Eigenes Login-Token-Format mit Übersetzungsschicht → Drift-Risiko zwischen Aussteller und Validator, doppelte Pflege.

> Siehe auch L2-ADR-AT-03 (öffentlicher Login-Endpunkt), ADR-AT-04 (Token-Format-Wiederverwendung statt Sessions), ADR-AT-05 (eigene Komponente COMP-AT-004).

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-25*
*Als-gebaut-Spiegelung von PasswordAuthenticationService*
*Designation: component (terminal) — decomposition_status: terminal*
