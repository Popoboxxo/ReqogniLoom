# L2 AuthAndTenancy Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** AuthAndTenancySystem (ARCH-L1-011)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-20
> **Status:** formalisiert
> **Designation:** component (terminal — keine L3-Zerlegung)

---

## Traceability

- Abgeleitet von: REQ-L1-010 (primär), REQ-L1-015 (primär), REQ-L1-033 (primär — Credential-Login), REQ-L1-005 (mitwirkend), REQ-L1-006 (mitwirkend), REQ-L1-007 (mitwirkend), REQ-L1-009 (mitwirkend), REQ-L1-011 (mitwirkend), REQ-L1-012 (mitwirkend), REQ-L1-016 (mitwirkend)
- Ziel: terminal (keine L3-Zerlegung)

---

## Externe Schnittstellen (Systemgrenze)

| ID | Richtung | Typ | Beschreibung |
|----|----------|-----|--------------|
| IF-AT-EXT-IN-001 | input | data | Bearer Token (JWT) von Browser/REST-Client |
| IF-AT-EXT-IN-002 | input | data | API Key von AI-Agent / API-Client |
| IF-AT-EXT-OUT-001 | output | data | Auth-Kontext (User, Tenant, Rollen) an ApplicationService |
| IF-AT-EXT-OUT-002 | output | data | Rollen-Check-Ergebnis an WorkflowEngine |
| IF-AT-EXT-OUT-003 | output | data | Berechtigungsentscheid (allow/deny) an RestApiAdapter / McpServer |
| IF-AT-EXT-OUT-004 | output | data | User, Role, Tenant Lookup von PersistenceLayer |
| IF-AT-EXT-IN-003 | input | data | Login-Use-Case `{username, password}` vom RestApiAdapter (`POST /api/v1/auth/login/`, öffentlich, kein Auth-Header) |
| IF-AT-EXT-OUT-005 | output | data | Ausgestellter Bearer-Token + Identität `{token, user, tenant_id, roles}` an RestApiAdapter (Login-Erfolg) bzw. `AuthenticationFailed("invalid_token")` |

---

## L2 Subsystem-Anforderungen

### REQ-L2-AT-001: Bearer Token Authentication

Das AuthAndTenancy-System SHALL eingehende REST-API- und UI-Anfragen durch Bearer Token (JWT) Validierung authentifizieren — Signaturprüfung, Ablaufzeit, Aussteller. Ungültige/abgelaufene Tokens SHALL mit HTTP 401 zurückgewiesen werden.


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Gültiges JWT → Auth-Kontext erzeugt
- [ ] Abgelaufenes JWT → HTTP 401 `{"error": "token_expired"}`
- [ ] Ungültige Signatur → HTTP 401 `{"error": "invalid_signature"}`
- [ ] Fehlender Header → HTTP 401 `{"error": "authentication_required"}`

**Interfaces:**
- Incoming: IF-AT-EXT-IN-001
- Outgoing: IF-AT-EXT-OUT-003

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L1-006, REQ-L1-010
**Rationale:** Token-Auth ist Grundlage für REST-API-Sicherheit.

---

### REQ-L2-AT-002: API Key Authentication

Das AuthAndTenancy-System SHALL API Keys gegen gehashte Stored Values validieren. Key im Header `X-API-Key` oder `Authorization: Bearer <api_key>`. Ungültige Keys SHALL zurückgewiesen werden. Hash-Vergleich in konstanter Laufzeit.


**Implementation State:** Implemented
**Review Findings:** Anforderung ist im Code auffindbar, aber Testabdeckung fehlt.
**Test Status:** Untested
**Remarks:** Testabdeckung sicherstellen.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Gültiger API Key → User und Tenant aufgelöst
- [ ] Unbekannter Key → HTTP 401 `{"error": "invalid_api_key"}`
- [ ] Widerrufener Key → HTTP 401 `{"error": "api_key_revoked"}`
- [ ] Key ausschließlich gehasht (SHA-256) verglichen
- [ ] Timing-Attack-Resistenz: `hmac.compare_digest`

**Interfaces:**
- Incoming: IF-AT-EXT-IN-002
- Outgoing: IF-AT-EXT-OUT-003

**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L1-005, REQ-L1-010
**Rationale:** API Key Auth für AI-Agenten und API-Clients.

---

### REQ-L2-AT-003: Role-Based Permission Enforcement

Das AuthAndTenancy-System SHALL Berechtigungen pro Operation und Ressource prüfen. Vier Rollen:

| Rolle | Lesen | Schreiben | Workflow-Transitionen | Workspace-Konfiguration |
|-------|-------|-----------|------------------------|--------------------------|
| Admin | alle | alle | alle | alle |
| Editor | alle | Workspace-Artefakte | Standard | keine |
| Viewer | alle | keine | keine | keine |
| Approver | alle | Workspace-Artefakte | alle inkl. Approval | keine |

Unzureichende Berechtigung → HTTP 403.


**Implementation State:** Implemented
**Review Findings:** Anforderung ist im Code auffindbar, aber Testabdeckung fehlt.
**Test Status:** Untested
**Remarks:** Testabdeckung sicherstellen.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Viewer versucht POST → HTTP 403
- [ ] Editor versucht Approval-Transition → HTTP 403
- [ ] Approver versucht Approval-Transition → HTTP 200
- [ ] Admin kann alle Operationen ausführen
- [ ] Viewer kann alle Lese-Operationen ausführen

**Interfaces:**
- Incoming: IF-AT-EXT-OUT-001 (Auth-Kontext mit Rollen)
- Outgoing: IF-AT-EXT-OUT-003

**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L1-010
**Rationale:** Permission Enforcement ist die operative Umsetzung von RBAC.

---

### REQ-L2-AT-004: Approver Role Preset Restriction

Das AuthAndTenancy-System SHALL die Approver-Rolle ausschließlich im Extended-Preset aktivieren. In Minimal/Standard SHALL die Rolle nicht zuweisbar sein.


**Implementation State:** Implemented
**Review Findings:** Anforderung ist im Code auffindbar, aber Testabdeckung fehlt.
**Test Status:** Untested
**Remarks:** Testabdeckung sicherstellen.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Standard-Preset: `assign_role(user, "approver")` → Fehler
- [ ] Extended-Preset: `assign_role(user, "approver")` → OK
- [ ] Approval-Transition im Minimal-Preset → Fehler
- [ ] Preset-Wechsel Extended → Standard: Approver-Zuweisungen suspendiert

**Interfaces:**
- Incoming: Preset-Info von PresetConfigEngine
- Outgoing: IF-AT-EXT-OUT-003

**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L1-010, REQ-L1-007 (mitwirkend)
**Rationale:** Approver-Rolle ist Teil des Configurable-Rigor-Konzepts.

---

### REQ-L2-AT-005: Authentication Context Propagation

Das AuthAndTenancy-System SHALL nach erfolgreicher Authentifizierung einen Auth-Kontext erzeugen: `user_id`, `tenant_id`, `active_roles`, `auth_method` (bearer_token | api_key), `api_key_id` (falls API-Key). Kontext an ApplicationService, WorkflowEngine und AuditLog übergeben. Kontext ist immutable.


**Implementation State:** Implemented
**Review Findings:** Anforderung ist im Code auffindbar, aber Testabdeckung fehlt.
**Test Status:** Untested
**Remarks:** Testabdeckung sicherstellen.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Bearer-Auth: Kontext enthält `{auth_method: "bearer_token", api_key_id: null}`
- [ ] API-Key-Auth: Kontext enthält `{auth_method: "api_key", api_key_id: "<id>"}`
- [ ] ApplicationService empfängt Kontext bei jeder Use-Case-Methode
- [ ] WorkflowEngine empfängt Rollen-Info
- [ ] AuditLog empfängt Actor-Info
- [ ] Kontext immutable nach Erzeugung

**Interfaces:**
- Outgoing: IF-AT-EXT-OUT-001, IF-AT-EXT-OUT-002

**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L1-010, REQ-L1-002 (mitwirkend), REQ-L1-009 (mitwirkend), REQ-L1-011 (mitwirkend), REQ-L1-012 (mitwirkend)
**Rationale:** Auth-Kontext-Propagation ist die zentrale interne Schnittstelle.

---

### REQ-L2-AT-006: Role Assignment Management

Das AuthAndTenancy-System SHALL CRUD für Rollenzuweisungen auf Workspace-Ebene bereitstellen. Nur Admins SÜLLEN Rollen zuweisen/entziehen können. Validierung: Rolle im Preset verfügbar, Zielnutzer ist Workspace-Mitglied, Audit-Log-Eintrag.


**Implementation State:** Implemented
**Review Findings:** Anforderung ist im Code auffindbar, aber Testabdeckung fehlt.
**Test Status:** Untested
**Remarks:** Testabdeckung sicherstellen.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Admin weist Editor-Rolle zu → gespeichert + Audit-Log
- [ ] Nicht-Admin versucht Zuweisung → HTTP 403
- [ ] Approver-Rolle im Standard-Preset → Fehler
- [ ] Nutzer kein Workspace-Mitglied → Fehler
- [ ] `GET /api/v1/workspaces/{id}/members` → Mitglieder mit Rollen

**Interfaces:**
- Incoming: Admin-Anfrage
- Outgoing: IF-AT-EXT-OUT-004

**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L1-010
**Rationale:** Rollenzuweisungen sind operative Grundlage für RBAC.

---

### REQ-L2-AT-007: Auth Middleware Interception

Das AuthAndTenancy-System SHALL alle Anfragen an REST/MCP-Endpunkte durch eine Auth-Middleware leiten. Ausnahmen: `/health`, `/api/docs`, `/api/openapi.json`.


**Implementation State:** Implemented
**Review Findings:** Anforderung ist im Code auffindbar, aber Testabdeckung fehlt.
**Test Status:** Untested
**Remarks:** Testabdeckung sicherstellen.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `/api/v1/requirements/` ohne Token → HTTP 401
- [ ] `/api/v1/requirements/` mit Token → durchgelassen
- [ ] `/health` ohne Token → HTTP 200
- [ ] MCP-Tool-Aufruf ohne API Key → Fehler
- [ ] Alle registrierten Endpunkte (außer Ausnahmen) hinter Auth

**Interfaces:**
- Incoming: IF-AT-EXT-IN-001, IF-AT-EXT-IN-002
- Outgoing: IF-AT-EXT-OUT-003

**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L1-006, REQ-L1-005, REQ-L1-010
**Rationale:** Lückenlose Auth-Durchsetzung ist architektonische Pflicht.

---

### REQ-L2-AT-008: Tenant Extraction and Propagation

Das AuthAndTenancy-System SHALL den aktiven Tenant aus dem Token extrahieren und in den Request-Kontext setzen. Tenant an PersistenceLayer (Custom Manager) weitergeben. Fehlgeschlagene Tenant-Auflösung → HTTP 500 `"Tenant resolution failed"`.


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] API-Key gehört zu T1 → alle DB-Queries filtern nach T1
- [ ] Bearer Token gehört zu Nutzer in T2 → tenant_id=T2
- [ ] Key ohne Tenant-Zuordnung → HTTP 500
- [ ] Tenant T1 erstellt Requirement → Query von T2 zeigt es nicht
- [ ] Custom Manager injiziert Filter automatisch

**Interfaces:**
- Incoming: IF-AT-EXT-IN-001, IF-AT-EXT-IN-002
- Outgoing: IF-AT-EXT-OUT-001, IF-AT-EXT-OUT-004

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L1-015
**Rationale:** Tenant-Extraktion ist operative Umsetzung von Row-Level-Isolation.

---

### REQ-L2-AT-009: API Key Lifecycle Management

Das AuthAndTenancy-System SHALL API Key Verwaltung unterstützen: Erstellung, Auflistung, Widerruf. Keys ausschließlich gehasht persistieren. Klartext nur einmalig bei Erstellung. Widerruf sofort wirksam.


**Implementation State:** Implemented
**Review Findings:** Anforderung ist im Code auffindbar, aber Testabdeckung fehlt.
**Test Status:** Untested
**Remarks:** Testabdeckung sicherstellen.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Erstellung → Klartext in Response, gehasht in DB
- [ ] Auflistung → Metadaten, kein Klartext
- [ ] Widerruf → sofort wirksam, nächster Request → 401
- [ ] DB enthält nur Hash-Werte
- [ ] Format: `rf_<random_40_chars>`
- [ ] Maximal 10 aktive Keys pro Nutzer

**Interfaces:**
- Incoming: Admin/User-Anfrage
- Outgoing: IF-AT-EXT-OUT-004

**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.

**Traceability:** REQ-L1-005, REQ-L1-010
**Rationale:** Sichere API-Key-Verwaltung ist Voraussetzung für MCP-Zugriff.

---

### REQ-L2-AT-010: Authentication Failure Response Standardization

Das AuthAndTenancy-System SHALL standardisierte Fehlerantworten für Auth-Fehler zurückgeben: `{"error": "<code>", "message": "...", "doc_url": "..."}`. Fehlermeldungen übersetzbar (DE/EN).


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.
**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] 401-Antworten enthalten definierte Error-Codes
- [ ] 403-Antworten enthalten `"insufficient_permissions"` mit benötigter Rolle
- [ ] Fehlermeldungen übersetzbar (DE/EN)
- [ ] Keine sensiblen Informationen in Fehlerantworten

**Interfaces:**
- Outgoing: IF-AT-EXT-OUT-003

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L1-006, REQ-L1-016 (mitwirkend)
**Rationale:** Konsistente Fehlerbehandlung in Clients.

---

### REQ-L2-AT-011: Credential Verification (Constant-Time)

Das AuthAndTenancy-System SHALL ein Benutzername/Passwort-Paar gegen den gespeicherten Passwort-Hash (PBKDF2 oder gleichwertig) verifizieren und bei Erfolg den aktiven Nutzer auflösen. Die Verifikation SHALL in (nahezu) konstanter Laufzeit erfolgen: existiert der Nutzer nicht, SHALL dennoch ein Dummy-Hash-Vergleich durchgeführt werden, sodass die Timing-Kurve von „Nutzer unbekannt" und „Passwort falsch" vergleichbar bleibt.


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Gültige Credentials eines aktiven Nutzers → Nutzer aufgelöst
- [ ] Falsches Passwort → `AuthenticationFailed("invalid_token")`
- [ ] Unbekannter Benutzername → Dummy-Hash-Vergleich + `AuthenticationFailed("invalid_token")`
- [ ] Inaktives Konto (`is_active=False`) → `AuthenticationFailed("invalid_token")`
- [ ] Hash-Vergleich über Djangos konstant-zeitige `check_password`

**Interfaces:**
- Incoming: IF-AT-EXT-IN-003
- Outgoing: IF-AT-EXT-OUT-004 (User-Lookup), IF-AT-EXT-OUT-005

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L1-033 (AC1, AC3)
**Rationale:** Sichere, enumeration-resistente Credential-Verifikation ist der Kern des Login-Flows. Bildet `PasswordAuthenticationService.authenticate_credentials` ab.

---

### REQ-L2-AT-012: Token Issuance — BearerTokenAuthentication-Kompatibilität

Das AuthAndTenancy-System SHALL nach erfolgreicher Credential-Verifikation einen signierten HS256-JWT ausstellen, dessen Claim-Set exakt dem entspricht, was `AuthenticationService.validate_bearer_token` (REQ-L2-AT-001) konsumiert — `user_id`, `tenant_id`, `roles`, `iat`, `exp` sowie konfiguriertes `iss`/`aud`. Der Token SHALL round-trip-fähig sein: er wird von `BearerTokenAuthentication` akzeptiert und liefert den korrekten Rollen- und Tenant-Kontext für RBAC-Entscheidungen. Secret/Issuer/Audience/TTL werden aus Django-Settings (`AUTH_JWT_*`) gelesen; kein Secret im Code.


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Ausgestellter Token enthält `{user_id, tenant_id, roles, iat, exp}` (+ `iss`/`aud` falls konfiguriert)
- [ ] Token wird von REQ-L2-AT-001 (Bearer-Validierung) akzeptiert (Round-Trip)
- [ ] Aufgelöste Rollen ergeben korrekten RBAC-Kontext (REQ-L2-AT-003)
- [ ] Nutzer ohne Tenant → `AuthenticationFailed("invalid_token")` (Token wäre downstream unbrauchbar)
- [ ] Fehlendes JWT-Secret → `AuthenticationFailed("invalid_token")`

**Interfaces:**
- Incoming: IF-AT-EXT-IN-003 (nach Verifikation)
- Outgoing: IF-AT-EXT-OUT-005

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L1-033 (AC1, AC5), REQ-L1-010 (mitwirkend)
**Rationale:** Format-Kompatibilität mit der bestehenden Token-Schicht ist die zentrale Architektur-Bedingung des arch_trigger. Bildet `PasswordAuthenticationService.issue_token` + `resolve_roles` ab.

---

### REQ-L2-AT-013: Public Login Endpoint Exemption

Das AuthAndTenancy-System SHALL den Login-Endpunkt `POST /api/v1/auth/login/` von der globalen Auth-Middleware-Interception (REQ-L2-AT-007) ausnehmen: der Endpunkt ist öffentlich (kein Bearer-Token, kein Tenant-Kontext erforderlich), da er der Mechanismus ist, über den ein Client überhaupt erst einen Token erhält. Alle übrigen geschützten Endpunkte bleiben hinter der Auth-Middleware.


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `POST /api/v1/auth/login/` ohne Token → erreichbar (kein 401 durch Middleware)
- [ ] Login-View setzt `authentication_classes = []` und `AllowAny`
- [ ] Ausnahmeliste erweitert um `/api/v1/auth/login/` (zusätzlich zu `/health`, `/api/docs`, `/api/openapi.json`)
- [ ] `/api/v1/auth/me/` bleibt geschützt (erfordert Bearer-Token)
- [ ] Alle übrigen geschützten Endpunkte weiterhin hinter Auth

**Interfaces:**
- Incoming: IF-AT-EXT-IN-003
- Outgoing: IF-AT-EXT-OUT-003

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L1-033 (AC1), REQ-L1-006 (mitwirkend)
**Rationale:** Ohne unauthentifizierten Einstiegspunkt gibt es keinen Bootstrap für interaktive Nutzer/Agenten. Siehe ADR-AT-03.

---

### REQ-L2-AT-014: Password Hash Storage Contract

Das AuthAndTenancy-System SHALL voraussetzen und sicherstellen, dass Passwörter im PersistenceLayer ausschließlich als gesalzener Hash (Django-Hasher, PBKDF2 default) im `User.password`-Feld gespeichert werden — niemals im Klartext. Klartext-Passwörter SHALL nie in API-Responses, Logs oder Audit-Einträgen erscheinen. Das System SHALL `set_password`/`check_password` nutzen; ein leeres `password` bedeutet „kein nutzbares Passwort" und matcht nie.


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `User.password` enthält ausschließlich Hash-Werte (Format `pbkdf2_sha256$...`) — prüfbar per Schema-Inspektion
- [ ] Klartext erscheint nie in Login-/Me-Response (`_user_payload` enthält kein Passwortfeld)
- [ ] Kein Klartext-Passwort in Logs oder Audit-Einträgen (Log-Review)
- [ ] Leeres `password` → `check_password` liefert `False`

**Interfaces:**
- Incoming: IF-AT-EXT-IN-003
- Outgoing: IF-AT-EXT-OUT-004

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L1-033 (AC4)
**Rationale:** Passwort-Hash-Storage ist ein Vertrag zwischen AuthAndTenancy und PersistenceLayer (Entity `User`). Bildet `User.set_password`/`check_password` ab.

---

### REQ-L2-AT-015: Self-Identity Endpoint (Session Bootstrap)

Das AuthAndTenancy-System SHALL über `GET /api/v1/auth/me/` mit gültigem Bearer-Token die Identität des aktuell angemeldeten Nutzers `{username, roles, tenant_id}` für den Frontend-Session-Bootstrap zurückgeben. Die Identität SHALL aus dem aufgelösten Auth-Kontext (REQ-L2-AT-005) stammen. Ohne Token oder mit ungültigem Token SHALL HTTP 401 zurückgegeben werden.


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] `GET /api/v1/auth/me/` mit gültigem Token → `{user{username,...}, tenant_id, roles}`
- [ ] Ohne Token → HTTP 401 `authentication_required`
- [ ] Ungültiger/abgelaufener Token → HTTP 401 (via Bearer-Validierung REQ-L2-AT-001)
- [ ] Rollen/Tenant stammen aus `request.auth_context` (immutable, REQ-L2-AT-005)

**Interfaces:**
- Incoming: IF-AT-EXT-IN-001 (Bearer-Token)
- Outgoing: IF-AT-EXT-OUT-001

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L1-033 (AC6)
**Rationale:** Frontend benötigt einen Identitäts-Bootstrap nach Login. Bildet `MeView` ab.

---

### REQ-L2-AT-016: No Account Enumeration

Das AuthAndTenancy-System SHALL bei jedem Login-Fehlschlag (unbekannter Benutzername, falsches Passwort, inaktives Konto) denselben generischen Fehlercode `invalid_token` mit HTTP 401 zurückgeben — ohne Unterscheidung zwischen „Nutzer unbekannt", „Passwort falsch" und „Konto inaktiv". Die Response SHALL keine Information über die Existenz eines Kontos preisgeben.


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.
**Domain:** software
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Unbekannter Benutzername → HTTP 401 `invalid_token`
- [ ] Bekannter Nutzer, falsches Passwort → HTTP 401 `invalid_token` (identische Response)
- [ ] Inaktives Konto → HTTP 401 `invalid_token` (identische Response)
- [ ] Kein Response-/Timing-Unterschied zwischen den drei Fehlerfällen (vgl. REQ-L2-AT-011)

**Interfaces:**
- Incoming: IF-AT-EXT-IN-003
- Outgoing: IF-AT-EXT-OUT-005

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L1-033 (AC2, AC3)
**Rationale:** Enumeration-Schutz ist Sicherheitsanforderung des Login-Flows; ergänzt den Timing-Schutz aus REQ-L2-AT-011 um Response-Uniformität.

---

## Erweiterung Phase 3 (se-architect, 2026-06-27)

### REQ-L2-AT-017: Item-Level-RBAC Regelverwaltung

Das AuthAndTenancySystem SHALL Projekt-Administratoren ermöglichen, Sichtbarkeits- und Bearbeitungsrechte auf Subsystem- oder Artefakt-Ebene zu konfigurieren. Item-Level-Regeln verfeinern die Workspace-RBAC (REQ-L1-010), überschreiben sie jedoch niemals — Admin-Rechte auf Workspace-Ebene haben weiterhin Vorrang. Regeln werden via UI (Berechtigungs-Editor) und API-Endpunkt konfiguriert.


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.
**Domain:** software
**Priority:** optional
**arch_impact:** false
**Acceptance Criteria:**
- [ ] Admin konfiguriert: 'Nutzer X hat Lesezugriff auf Subsystem Y' → Regel gespeichert
- [ ] Item-Level-Regel überschreibt keine Workspace-RBAC (Admin-Rechte haben Vorrang)
- [ ] Konfiguration via UI (Berechtigungs-Editor) und API-Endpunkt (POST /permissions/item)
- [ ] Regel-Validierung: Zielnutzer muss Tenant-Mitglied sein
- [ ] Regel-Löschung → Berechtigung sofort widerrufen

**Interfaces:**
- Incoming: IF-AT-EXT-IN-001 (Admin-Request via REST-API)
- Outgoing: IF-AT-EXT-OUT-003, IF-AT-EXT-OUT-004

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.

**Traceability:** REQ-L1-039, REQ-L1-010 (mitwirkend)
**Rationale:** Feingranulare Zugriffsregeln ermöglichen externe Partner/Zulieferer ohne vollständigen Systemkontext.

---

### REQ-L2-AT-018: Item-Level Permission Enforcement

Das AuthAndTenancySystem SHALL Item-Level-Regeln bei allen API-Zugriffen auswerten (keine UI-only-Beschränkung). Die Enforcement erfolgt via PostgreSQL Row-Level Security (RLS) Policies. Der Permission-Cache (TTL: 60s) reduziert die Evaluierungs-Latenz. Performance: max. 10% Overhead auf API-Response-Zeiten für Workspaces mit ≤ 100 Item-Level-Regeln.


**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.
**Domain:** software
**Priority:** optional
**arch_impact:** false
**Acceptance Criteria:**
- [ ] Item-Level-Regel wird bei API-Zugriffen ausgewertet (keine UI-only-Beschränkung)
- [ ] Nutzer ohne Item-Level-Berechtigung → HTTP 403 bei Zugriff auf geschütztes Artefakt
- [ ] Enforcement via PostgreSQL RLS Policies (datenbankseitig)
- [ ] Permission-Cache (TTL: 60s) → max. 10% Overhead auf API-Response-Zeiten
- [ ] Cache-Invalidierung bei Regel-Änderung (sofort)

**Interfaces:**
- Incoming: IF-AT-EXT-IN-001 (Auth-Context von REST-API/MCP)
- Outgoing: IF-AT-EXT-OUT-003 (Berechtigungsentscheid allow/deny)

**Implementation State:** Not Implemented
**Review Findings:** Keine Implementierung oder Tests im Code gefunden.
**Test Status:** Missing
**Remarks:** Sollte implementiert werden.

**Traceability:** REQ-L1-039, REQ-L1-026 (mitwirkend — Performance)
**Rationale:** RLS-basierte Enforcement verhindert, dass neue API-Endpunkte versehentlich Item-Level-Regeln umgehen.

---

## Traceability-Matrix: REQ-L2-AT → REQ-L1

| REQ-L2-AT | Primäre REQ-L1 | Mitwirkende REQ-L1 |
|-----------|----------------|---------------------|
| REQ-L2-AT-001 | REQ-L1-006, REQ-L1-010 | — |
| REQ-L2-AT-002 | REQ-L1-005, REQ-L1-010 | — |
| REQ-L2-AT-003 | REQ-L1-010 | — |
| REQ-L2-AT-004 | REQ-L1-010 | REQ-L1-007 |
| REQ-L2-AT-005 | REQ-L1-010 | REQ-L1-002, -009, -011, -012 |
| REQ-L2-AT-006 | REQ-L1-010 | — |
| REQ-L2-AT-007 | REQ-L1-006, REQ-L1-005 | REQ-L1-010 |
| REQ-L2-AT-008 | REQ-L1-015 | — |
| REQ-L2-AT-009 | REQ-L1-005, REQ-L1-010 | — |
| REQ-L2-AT-010 | REQ-L1-006 | REQ-L1-016 |
| REQ-L2-AT-011 | REQ-L1-033 | — |
| REQ-L2-AT-012 | REQ-L1-033 | REQ-L1-010 |
| REQ-L2-AT-013 | REQ-L1-033 | REQ-L1-006 |
| REQ-L2-AT-014 | REQ-L1-033 | — |
| REQ-L2-AT-015 | REQ-L1-033 | — |
| REQ-L2-AT-016 | REQ-L1-033 | — |
| REQ-L2-AT-017 | REQ-L1-039 | REQ-L1-010 |
| REQ-L2-AT-018 | REQ-L1-039 | REQ-L1-026 |

---

## Zusammenfassung

| Metrik | Wert |
|--------|------|
| Anzahl REQ-L2-AT | 18 |
| Mandatory | 15 |
| Desired | 1 |
| Optional | 2 |
| Abgedeckte REQ-L1 (primär) | REQ-L1-010, REQ-L1-015, REQ-L1-033, REQ-L1-039 |
| Abgedeckte REQ-L1 (mitwirkend) | REQ-L1-002, -005, -006, -007, -009, -011, -012, -016, -026 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L1→L2 | 2026-06-20*
*Complete Rewrite: ID-Migration REQ-L2-Auth → REQ-L2-AT, Template-Standardisierung*
*Erweiterung 2026-06-25: REQ-L2-AT-011..016 (Credential-Login, REQ-L1-033) durch se-architect-Agent*
*Designation: component (terminal) — decomposition_status: terminal*

---

## Erweiterung v3 — REQ-L2-AT-017..019 vollständig ausgearbeitet (REQ-L1-039)

> **Datum:** 2026-06-28 | **Quelle:** REQ-L0-027 → REQ-L1-039

Die Anforderungen AT-017 und AT-018 existieren bereits in der Traceability-Matrix,
sind aber nur minimal beschrieben. Diese Erweiterung liefert die vollständigen
Beschreibungen inkl. Akzeptanzkriterien, Schnittstellen und Verifikationsmethode.
Zusätzlich wird AT-019 (UI-Komponente für Item-Level-Verwaltung) neu eingeführt.

---

### REQ-L2-AT-017 (vollständig): Item-Level-RBAC Regelverwaltung

**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code (ItemPermissionViewSet) auffindbar.
**Test Status:** Covered
**Remarks:** Abgeleitet von REQ-L1-039 (← REQ-L0-027, SN-27). Priority: optional (Enterprise-Feature).

Das AuthAndTenancySystem MUSS Projekt-Admins ermöglichen, Zugriffsbeschränkungen
auf Subsystem- oder Artefakt-Ebene zu definieren. Eine Item-Level-Regel verbindet
einen Nutzer oder eine Rolle mit einem Artefakt-Scope (Workspace, Subsystem-ID,
einzelne Artefakt-ID) und einem Berechtigungstyp (`read`, `write`, `none`).

**Datenmodell — ItemPermission:**
```
ItemPermission {
  id: UUID
  workspace_id: UUID          -- Pflicht (Mandanten-Scoping)
  principal_type: enum        -- "user" | "role"
  principal_id: UUID          -- User-ID oder Role-ID
  scope_type: enum            -- "workspace" | "subsystem" | "artefact"
  scope_id: UUID              -- ID des Workspace/Subsystem/Artefakts
  permission: enum            -- "read" | "write" | "none"
  created_by: UUID
  created_at: datetime
}
```

**Schnittstellen:**
- `POST /workspaces/{id}/permissions` → Regel erstellen (Admin only)
- `GET /workspaces/{id}/permissions` → Regeln auflisten (Admin only)
- `DELETE /workspaces/{id}/permissions/{perm_id}` → Regel löschen (sofort wirksam)
- Intern: `PermissionService.create_rule(...)`, `PermissionService.delete_rule(...)`

**Akzeptanzkriterien:**
- AC1: Admin kann eine `read`-Regel für User X auf Subsystem Y anlegen → persistiert
- AC2: Admin kann eine `none`-Regel anlegen (explizites Verweigern, höhere Priorität als `read`)
- AC3: Nicht-Admin versucht Regel anzulegen → HTTP 403
- AC4: Regel-Löschung → Berechtigungsentscheid sofort aktualisiert (kein Cache-Lag > 1s)
- AC5: Regeln sind workspace-scoped — keine cross-workspace Regeln möglich
- AC6: Bis zu 1.000 aktive Regeln pro Workspace ohne Performance-Degradierung

**Verifikationsmethode:** Integrationstest — Regel anlegen, Zugriff prüfen, löschen, Zugriff wieder prüfen
**Verifikiert durch:** L2-AT-Test-017
**Abgeleitet von:** REQ-L1-039
**Übergeordnete REQ-L0:** REQ-L0-027

---

### REQ-L2-AT-018 (vollständig): Item-Level Permission Enforcement (API-seitig)

**Implementation State:** Not Implemented
**Review Findings:** Kein Code-Äquivalent. API-Middleware prüft aktuell nur Workspace-Membership und Rollen, nicht Item-Level-Regeln.
**Test Status:** Missing
**Remarks:** Abgeleitet von REQ-L1-039 (← REQ-L0-027, SN-27). Voraussetzung: REQ-L2-AT-017.

Das AuthAndTenancySystem MUSS Item-Level-Regeln (REQ-L2-AT-017) bei **jedem**
API-Zugriff auf geschützte Artefakte auswerten — unabhängig vom Aufrufkanal
(REST-API, MCP-Server). Die Enforcement DARF nicht ausschließlich in der UI erfolgen.

**Enforcement-Logik (Prioritätsreihenfolge):**
1. `none`-Regel für User/Rolle auf Scope → `deny` (höchste Priorität)
2. `read`/`write`-Regel für User/Rolle auf Scope → `allow` (falls kein `none` übergeordnet)
3. Workspace-Membership ohne Item-Regel → Standard-RBAC (bestehend)
4. Kein Match → `deny` (Fail-Safe)

**Caching-Strategie:**
- Permission-Entscheide SOLLEN für max. 60 s gecacht werden (TTL-Cache pro User/Artefakt)
- Cache-Invalidierung MUSS bei Regel-Änderung (AT-017) sofort erfolgen
- Cache-Miss → Neuberechnung aus DB (max. 10 ms zusätzliche Latenz)

**Schnittstellen:**
- Intern: `PermissionEnforcer.check(user_id, artefact_id, action)` → `allow | deny`
- Integriert in API-Middleware (nach Auth-Token-Validierung, vor Request-Handler)

**Akzeptanzkriterien:**
- AC1: User ohne Item-Regel → Standard-RBAC greift (kein Breaking Change)
- AC2: User mit `read`-Regel auf Subsystem → `GET /requirements/{id}` → HTTP 200
- AC3: User mit `read`-Regel → `PATCH /requirements/{id}` → HTTP 403
- AC4: User mit `none`-Regel auf Artefakt → HTTP 403 (überschreibt `read`-Regel auf übergeordnetem Scope)
- AC5: Cache-Invalidierung bei Regel-Änderung < 1 s
- AC6: Performance-Overhead < 10 % auf API-Response-Zeit (Workspace mit ≤ 100 Regeln)
- AC7: MCP-Server-Zugriff unterliegt denselben Enforcement-Regeln wie REST-API

**Verifikationsmethode:** Integrationstest (AC1-AC5) + Lasttest (AC6)
**Verifikiert durch:** L2-AT-Test-018
**Abgeleitet von:** REQ-L1-039
**Übergeordnete REQ-L0:** REQ-L0-027

---

### REQ-L2-AT-019 (NEU): Item-Level-Berechtigungs-UI (Admin-Oberfläche)

**Implementation State:** Not Implemented
**Review Findings:** Neu identifiziert. Ohne UI ist die Item-Level-RBAC (AT-017/018) für Admins nicht nutzbar.
**Test Status:** Missing
**Remarks:** Abgeleitet von REQ-L1-039 (← REQ-L0-027, SN-27). Companion zu AT-017. Betrifft ReactFrontend.

Das System MUSS Projekt-Admins eine Oberfläche bereitstellen, über die sie
Item-Level-Berechtigungsregeln (REQ-L2-AT-017) verwalten können, ohne direkte
API-Calls zu nutzen. Die Oberfläche MUSS Regeln nach Nutzer, Rolle oder Scope
filterbar anzeigen und SOLL Konflikte (z. B. `none` überschreibt übergeordnetes `read`)
visuell kenntlich machen.

> **Hinweis:** Diese Anforderung liegt im Verantwortungsbereich des ReactFrontendSystem
> (REQ-L2-RF-xxx), wird hier aber im AuthAndTenancySystem dokumentiert, da sie
> direkt die Funktionalität von AT-017 exponiert.

**Schnittstellen:**
- Ruft `GET/POST/DELETE /workspaces/{id}/permissions` (REQ-L2-AT-017) auf
- Nutzer-Autocomplete: `GET /workspaces/{id}/users?q=prefix`

**Akzeptanzkriterien:**
- AC1: Admin sieht Tabelle aller aktiven Item-Level-Regeln für einen Workspace
- AC2: Neue Regel anlegen per Formular (Nutzer/Rolle wählen, Scope wählen, Berechtigung setzen)
- AC3: Regel löschen per Klick mit Bestätigungsdialog
- AC4: Konflikt-Highlight: `none`-Regel, die eine `read`-Regel überschreibt, wird visuell markiert
- AC5: Filter nach Nutzer, Rolle und Scope-Typ

**Verifikationsmethode:** UI-E2E-Test (Playwright) — Regel anlegen, Conflict-Highlight prüfen
**Verifikiert durch:** L2-AT-Test-019
**Abgeleitet von:** REQ-L1-039
**Übergeordnete REQ-L0:** REQ-L0-027

---

## Traceability-Matrix: REQ-L2-AT → REQ-L1 (aktualisiert)

| REQ-L2-AT | Primäre REQ-L1 | Mitwirkende REQ-L1 |
|-----------|----------------|---------------------|
| REQ-L2-AT-001 | REQ-L1-006, REQ-L1-010 | — |
| REQ-L2-AT-002 | REQ-L1-005, REQ-L1-010 | — |
| REQ-L2-AT-003 | REQ-L1-010 | — |
| REQ-L2-AT-004 | REQ-L1-010 | REQ-L1-007 |
| REQ-L2-AT-005 | REQ-L1-010 | REQ-L1-002, -009, -011, -012 |
| REQ-L2-AT-006 | REQ-L1-010 | — |
| REQ-L2-AT-007 | REQ-L1-006, REQ-L1-005 | REQ-L1-010 |
| REQ-L2-AT-008 | REQ-L1-015 | — |
| REQ-L2-AT-009 | REQ-L1-005, REQ-L1-010 | — |
| REQ-L2-AT-010 | REQ-L1-006 | REQ-L1-016 |
| REQ-L2-AT-011 | REQ-L1-033 | — |
| REQ-L2-AT-012 | REQ-L1-033 | REQ-L1-010 |
| REQ-L2-AT-013 | REQ-L1-033 | REQ-L1-006 |
| REQ-L2-AT-014 | REQ-L1-033 | — |
| REQ-L2-AT-015 | REQ-L1-033 | — |
| REQ-L2-AT-016 | REQ-L1-033 | — |
| REQ-L2-AT-017 | REQ-L1-039 | REQ-L1-010 |
| REQ-L2-AT-018 | REQ-L1-039 | REQ-L1-026 |
| REQ-L2-AT-019 | REQ-L1-039 | — |

---

## Zusammenfassung (aktualisiert)

| Metrik | Wert |
|--------|------|
| Anzahl REQ-L2-AT | 19 |
| Mandatory | 15 |
| Desired | 1 |
| Optional | 3 |
| Abgedeckte REQ-L1 (primär) | REQ-L1-010, REQ-L1-015, REQ-L1-033, REQ-L1-039 |
| Abgedeckte REQ-L1 (mitwirkend) | REQ-L1-002, -005, -006, -007, -009, -011, -012, -016, -026 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L1→L2 | 2026-06-20*
*Complete Rewrite: ID-Migration REQ-L2-Auth → REQ-L2-AT, Template-Standardisierung*
*Erweiterung 2026-06-25: REQ-L2-AT-011..016 (Credential-Login, REQ-L1-033) durch se-architect-Agent*
*Erweiterung 2026-06-28: REQ-L2-AT-017..019 vollständig ausgearbeitet (REQ-L1-039, SN-27)*
*Designation: component (terminal) — decomposition_status: terminal*

---

## Erweiterung v4 — REQ-L2-AT-020 (Personal Access Tokens)

> **Datum:** 2026-07-03 | **Quelle:** REQ-L1-081

---

### REQ-L2-AT-020: Persistierung und Validierung von PATs

Das AuthAndTenancySystem MUSS die Geschäftslogik für Personal Access Tokens kapseln. Tokens MÜSSEN in der Datenbank sicher (gehasht, z.B. HMAC/SHA256) abgelegt werden. Bei eingehenden Requests MUSS der Token aus dem `Authorization: Bearer <Token>` Header gegen den Hash in der Datenbank validiert und die Anfrage dem zugehörigen Benutzer-Kontext zugeordnet werden.

**Implementation State:** Not Implemented
**Review Findings:** Neu.
**Test Status:** Missing
**Priority:** mandatory
**Acceptance Criteria:**
- [ ] Datenbank-Modell `PersonalAccessToken` (User, Name, Hash, CreatedAt).
- [ ] Klartext-Token wird niemals in der Datenbank gespeichert.
- [ ] Token-Validierung integriert sich nahtlos in die DRF-Authentifizierung.

**Verifikationsmethode:** Unit-Tests der TokenService-Krypto-Logik.
**Verifikiert durch:** L2-AT-Test-020
**Abgeleitet von:** REQ-L1-081

---

*Erstellt durch se-requirements-Agent (L2) | ReqFlow SE-Kaskade | 2026-07-03*


## Master Traceability Matrix

| REQ-L2 | Abgeleitet von REQ-L1 |
|---------|----------------------|
| REQ-L2-AT-001 | REQ-L1-006, REQ-L1-010 |
| REQ-L2-AT-002 | REQ-L1-005, REQ-L1-010 |
| REQ-L2-AT-003 | REQ-L1-010 |
| REQ-L2-AT-004 | REQ-L1-010, REQ-L1-007 (mitwirkend) |
| REQ-L2-AT-005 | REQ-L1-010, REQ-L1-002 (mitwirkend), REQ-L1-009 (mitwirkend), REQ-L1-011 (mitwirkend), REQ-L1-012 (mitwirkend) |
| REQ-L2-AT-006 | REQ-L1-010 |
| REQ-L2-AT-007 | REQ-L1-006, REQ-L1-005, REQ-L1-010 |
| REQ-L2-AT-008 | REQ-L1-015 |
| REQ-L2-AT-009 | REQ-L1-005, REQ-L1-010 |
| REQ-L2-AT-010 | REQ-L1-006, REQ-L1-016 (mitwirkend) |
| REQ-L2-AT-011 | REQ-L1-033 (AC1 |
| REQ-L2-AT-012 | REQ-L1-033 (AC1, REQ-L1-010 (mitwirkend) |
| REQ-L2-AT-013 | REQ-L1-033 (AC1), REQ-L1-006 (mitwirkend) |
| REQ-L2-AT-014 | REQ-L1-033 (AC4) |
| REQ-L2-AT-015 | REQ-L1-033 (AC6) |
| REQ-L2-AT-016 | REQ-L1-033 (AC2 |
| REQ-L2-AT-017 | REQ-L1-039, REQ-L1-010 (mitwirkend) |
| REQ-L2-AT-018 | REQ-L1-039, REQ-L1-026 (mitwirkend — Performance) |

