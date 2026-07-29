decomposition_status: terminal

# L3 SignatureGateVerifier Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-WE-004 — SignatureGateVerifier
> **Parent-System:** WorkflowEngineSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Verifiziert Credentials (Passwort-Hash-Vergleich oder TOTP-Pruefung) gegen AuthAndTenancy; generiert kryptografisches Pruefsiegel (HMAC-SHA256 aus `transition_id + timestamp + user_id`); gibt `VerificationResult {valid, seal?}` zurueck.

---

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-WE-009 | SignatureGate — Credential-Verifizierung, HMAC-SHA256-Siegel, QES-Konformitaet |

---

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-WE-INT-004 | eingehend | COMP-WE-002 (TransitionValidator) | `CredentialVerificationRequest {transition_id, user_id, credential (password \| totp_token), timestamp}` |
| IF-WE-INT-005 | ausgehend | COMP-WE-003 (StateLifecycleManager) | `VerificationResult {valid, seal? (HMAC-SHA256 hex)}` |

## Externe Schnittstellen (Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-WE-EXT-IN-004 | eingehend | AuthAndTenancy | Credential-Pruefung (Passwort-Hash-Vergleich, TOTP-Validierung) |

---

## L3 Komponenten-Anforderungen

### REQ-L3-WE004-001: Credential-Verifizierung gegen AuthAndTenancy


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Der SignatureGateVerifier SHALL eingehende `CredentialVerificationRequest`-Nachrichten (via IF-WE-INT-004) verarbeiten, indem er das enthaltene Credential (Passwort oder TOTP-Token) gegen das AuthAndTenancy-System (IF-WE-EXT-IN-004) preuft. Passwort-Credentials MUESSEN per konstantzeit-sicherem Hash-Vergleich geprueft werden. TOTP-Tokens MUESSEN gemaess RFC 6238 validiert werden (Zeitfenster: +/- 30 Sekunden). Schlaegt die Pruefung fehl, SHALL `VerificationResult {valid: false}` ohne `seal` zurueckgegeben werden. Kein fehlgeschlagener Versuch SHALL einen Audit-Log-Eintrag ausloesen.

**Priority:** desired
**Acceptance Criteria:**
- [ ] Correct password → `VerificationResult {valid: true, seal: <non-null>}`
- [ ] Wrong password → `VerificationResult {valid: false}`, no `seal` field
- [ ] Valid TOTP token (within +/- 30s window) → `VerificationResult {valid: true, seal: <non-null>}`
- [ ] Expired or invalid TOTP token → `VerificationResult {valid: false}`, no `seal` field
- [ ] Password comparison uses constant-time algorithm (timing-safe equals, not direct string comparison)
- [ ] Failed verification attempt does not trigger any audit log write in COMP-WE-003

---

### REQ-L3-WE004-002: HMAC-SHA256-Siegel-Generierung


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Der SignatureGateVerifier SHALL bei erfolgreicher Credential-Verifizierung ein kryptografisches Pruefsiegel als HMAC-SHA256-Hex-String aus der Konkatenation `transition_id + timestamp + user_id` berechnen. Der dabei verwendete HMAC-Schluessel SHALL serverseitig konfiguriert und nicht im Code hartcodiert sein. Das Siegel SHALL im `seal`-Feld von `VerificationResult` zurueckgegeben werden.

**Priority:** desired
**Acceptance Criteria:**
- [ ] Successful verification → `seal` = HMAC-SHA256(`transition_id || timestamp || user_id`) as lowercase hex string
- [ ] Same inputs always produce the same seal (deterministic for fixed key)
- [ ] HMAC key is loaded from server configuration (environment variable or secrets store), not hardcoded
- [ ] `seal` field is absent (not null string, but missing key) when verification fails
- [ ] Seal is verifiable externally using the same HMAC-SHA256 algorithm and key

---

### REQ-L3-WE004-003: Isolation der Sicherheitslogik


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Der SignatureGateVerifier SHALL ausschliesslich auf Credential-Pruefung und Siegel-Generierung beschraenkt sein. Er SHALL keine Kenntnis von WorkflowDefinitions, States oder History-Eintraegen besitzen und keine direkten Datenbankoperationen auf Workflow-Tabellen ausfuehren.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] COMP-WE-004 has no import or dependency on WorkflowDefinition or WorkflowState models
- [ ] COMP-WE-004 executes no SQL writes to workflow-related tables
- [ ] Component interface is limited to IF-WE-INT-004 (input) and IF-WE-INT-005 (output) plus IF-WE-EXT-IN-004 (AuthAndTenancy)
- [ ] Unit test of COMP-WE-004 requires no WorkflowDefinition or WorkflowState fixtures

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*

---

### REQ-L3-WE004-004: L3 Context Generators Implementation

Derives from REQ-L2-WOR-015 (which derives from REQ-L1-285).
Component implements specific logic for prompt enrichment and context generation.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Context Generators are wired properly.

---

### REQ-L3-WE004-005: L3 Agent Templates & Review Endpoints

Derives from REQ-L2-WOR-016 (which derives from REQ-L1-286).
Component supports Write Modes, Agent Templates, or frontend integrations for Superpowers.

**Implementation State:** Planned
**Priority:** mandatory
**decomposition_status:** terminal
**Acceptance Criteria:**
- [ ] Review Endpoints / Agent Templates supported.
