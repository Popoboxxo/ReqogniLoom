# L2 AuthAndTenancy Requirements

> **Level:** L2 (Subsystem-Anforderungen)
> **System:** AuthAndTenancySystem (ARCH-L1-011)
> **Parent:** L1_Gesamtsystem_Requirements.md
> **Datum:** 2026-06-20
> **Status:** formalisiert
> **Designation:** component (terminal — keine L3-Zerlegung)

---

## Traceability

- Abgeleitet von: REQ-L1-010 (primär), REQ-L1-015 (primär), REQ-L1-005 (mitwirkend), REQ-L1-006 (mitwirkend), REQ-L1-007 (mitwirkend), REQ-L1-009 (mitwirkend), REQ-L1-011 (mitwirkend), REQ-L1-012 (mitwirkend), REQ-L1-016 (mitwirkend)
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

---

## L2 Subsystem-Anforderungen

### REQ-L2-AT-001: Bearer Token Authentication

Das AuthAndTenancy-System SHALL eingehende REST-API- und UI-Anfragen durch Bearer Token (JWT) Validierung authentifizieren — Signaturprüfung, Ablaufzeit, Aussteller. Ungültige/abgelaufene Tokens SHALL mit HTTP 401 zurückgewiesen werden.

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

**Traceability:** REQ-L1-006, REQ-L1-010
**Rationale:** Token-Auth ist Grundlage für REST-API-Sicherheit.

---

### REQ-L2-AT-002: API Key Authentication

Das AuthAndTenancy-System SHALL API Keys gegen gehashte Stored Values validieren. Key im Header `X-API-Key` oder `Authorization: Bearer <api_key>`. Ungültige Keys SHALL zurückgewiesen werden. Hash-Vergleich in konstanter Laufzeit.

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

**Traceability:** REQ-L1-010
**Rationale:** Permission Enforcement ist die operative Umsetzung von RBAC.

---

### REQ-L2-AT-004: Approver Role Preset Restriction

Das AuthAndTenancy-System SHALL die Approver-Rolle ausschließlich im Extended-Preset aktivieren. In Minimal/Standard SHALL die Rolle nicht zuweisbar sein.

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

**Traceability:** REQ-L1-010, REQ-L1-007 (mitwirkend)
**Rationale:** Approver-Rolle ist Teil des Configurable-Rigor-Konzepts.

---

### REQ-L2-AT-005: Authentication Context Propagation

Das AuthAndTenancy-System SHALL nach erfolgreicher Authentifizierung einen Auth-Kontext erzeugen: `user_id`, `tenant_id`, `active_roles`, `auth_method` (bearer_token | api_key), `api_key_id` (falls API-Key). Kontext an ApplicationService, WorkflowEngine und AuditLog übergeben. Kontext ist immutable.

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

**Traceability:** REQ-L1-010, REQ-L1-002 (mitwirkend), REQ-L1-009 (mitwirkend), REQ-L1-011 (mitwirkend), REQ-L1-012 (mitwirkend)
**Rationale:** Auth-Kontext-Propagation ist die zentrale interne Schnittstelle.

---

### REQ-L2-AT-006: Role Assignment Management

Das AuthAndTenancy-System SHALL CRUD für Rollenzuweisungen auf Workspace-Ebene bereitstellen. Nur Admins SÜLLEN Rollen zuweisen/entziehen können. Validierung: Rolle im Preset verfügbar, Zielnutzer ist Workspace-Mitglied, Audit-Log-Eintrag.

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

**Traceability:** REQ-L1-010
**Rationale:** Rollenzuweisungen sind operative Grundlage für RBAC.

---

### REQ-L2-AT-007: Auth Middleware Interception

Das AuthAndTenancy-System SHALL alle Anfragen an REST/MCP-Endpunkte durch eine Auth-Middleware leiten. Ausnahmen: `/health`, `/api/docs`, `/api/openapi.json`.

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

**Traceability:** REQ-L1-006, REQ-L1-005, REQ-L1-010
**Rationale:** Lückenlose Auth-Durchsetzung ist architektonische Pflicht.

---

### REQ-L2-AT-008: Tenant Extraction and Propagation

Das AuthAndTenancy-System SHALL den aktiven Tenant aus dem Token extrahieren und in den Request-Kontext setzen. Tenant an PersistenceLayer (Custom Manager) weitergeben. Fehlgeschlagene Tenant-Auflösung → HTTP 500 `"Tenant resolution failed"`.

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

**Traceability:** REQ-L1-015
**Rationale:** Tenant-Extraktion ist operative Umsetzung von Row-Level-Isolation.

---

### REQ-L2-AT-009: API Key Lifecycle Management

Das AuthAndTenancy-System SHALL API Key Verwaltung unterstützen: Erstellung, Auflistung, Widerruf. Keys ausschließlich gehasht persistieren. Klartext nur einmalig bei Erstellung. Widerruf sofort wirksam.

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

**Traceability:** REQ-L1-005, REQ-L1-010
**Rationale:** Sichere API-Key-Verwaltung ist Voraussetzung für MCP-Zugriff.

---

### REQ-L2-AT-010: Authentication Failure Response Standardization

Das AuthAndTenancy-System SHALL standardisierte Fehlerantworten für Auth-Fehler zurückgeben: `{"error": "<code>", "message": "...", "doc_url": "..."}`. Fehlermeldungen übersetzbar (DE/EN).

**Domain:** software
**Priority:** desired
**Acceptance Criteria:**
- [ ] 401-Antworten enthalten definierte Error-Codes
- [ ] 403-Antworten enthalten `"insufficient_permissions"` mit benötigter Rolle
- [ ] Fehlermeldungen übersetzbar (DE/EN)
- [ ] Keine sensiblen Informationen in Fehlerantworten

**Interfaces:**
- Outgoing: IF-AT-EXT-OUT-003

**Traceability:** REQ-L1-006, REQ-L1-016 (mitwirkend)
**Rationale:** Konsistente Fehlerbehandlung in Clients.

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

---

## Zusammenfassung

| Metrik | Wert |
|--------|------|
| Anzahl REQ-L2-AT | 10 |
| Mandatory | 9 |
| Desired | 1 |
| Optional | 0 |
| Abgedeckte REQ-L1 (primär) | REQ-L1-010, REQ-L1-015 |
| Abgedeckte REQ-L1 (mitwirkend) | REQ-L1-002, -005, -006, -007, -009, -011, -012, -016 |

---

*Erstellt durch se-requirements-Agent | ReqFlow SE-Kaskade L1→L2 | 2026-06-20*
*Complete Rewrite: ID-Migration REQ-L2-Auth → REQ-L2-AT, Template-Standardisierung*
*Designation: component (terminal) — decomposition_status: terminal*
