# L3 TransitionValidator Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-WE-002 — TransitionValidator
> **Parent-System:** WorkflowEngineSystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

Validierung aller State-Transitions gegen aktive WorkflowDefinition: Transition-Existenz, Rollenberechtigung, change_reason-Pflicht; prueft SignatureGate-Anforderung — bei Vorhandensein: Delegation des Credentials an COMP-WE-004. Performance-Budget: Validierung <= 10 ms.

---

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-WE-001 | Transition Validation — vier Validierungsregeln, spezifische Fehlermeldungen |
| REQ-L2-WE-008 | Transition Performance — Validierungsschritt < 10 ms |

---

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-WE-INT-001 | eingehend | COMP-WE-001 (WorkflowDefinitionStore) | `WorkflowDefinition {states, transitions, allowed_roles, requires_change_reason, signature_gate?}` |
| IF-WE-INT-002 | ausgehend | COMP-WE-003 (StateLifecycleManager) | `ValidationResult {valid, error_code?, error_message?}` |
| IF-WE-INT-004 | ausgehend | COMP-WE-004 (SignatureGateVerifier) | `CredentialVerificationRequest {transition_id, user_id, credential, timestamp}` |

## Externe Schnittstellen (Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-WE-EXT-IN-001 | eingehend | ApplicationService | `transition(item_id, target_state, change_reason, ctx)` |
| IF-WE-EXT-IN-004 | eingehend | AuthAndTenancy | Rollen-Kontext des anfragenden Nutzers |
| IF-WE-EXT-IN-005 | eingehend | ApplicationService | Credential (Passwort / TOTP-Token) fuer SignatureGate |

---

## L3 Komponenten-Anforderungen

### REQ-L3-WE002-001: Vierstufige Transition-Regelvalidierung


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Der TransitionValidator SHALL jede eingehende Transition sequenziell gegen vier Regeln pruefen: (1) Transition existiert in der aktiven WorkflowDefinition fuer den betreffenden Item-Typ und Workspace; (2) Rolle des anfragenden Nutzers ist in `allowed_roles` der Transition enthalten; (3) Falls `requires_change_reason = true`, ist ein nicht-leerer `change_reason` vorhanden; (4) Falls `signature_gate = true`, ist ein Credential uebergeben worden. Bei der ersten Regelverletzung SHALL die Validierung mit einem spezifischen `error_code` und `error_message` abgebrochen und `ValidationResult {valid: false}` zurueckgegeben werden.

**Priority:** mandatory
**Acceptance Criteria:**
- [ ] User with role `editor`, transition `draft → approved` (only `approver` allowed) → `ValidationResult {valid: false, error_code: "ROLE_NOT_ALLOWED"}`
- [ ] User with role `approver`, transition requires `change_reason`, none provided → `ValidationResult {valid: false, error_code: "CHANGE_REASON_REQUIRED"}`
- [ ] Undefined transition `draft → deprecated` → `ValidationResult {valid: false, error_code: "TRANSITION_NOT_ALLOWED"}`
- [ ] Transition with `signature_gate: true`, no credential passed → `ValidationResult {valid: false, error_code: "SIGNATURE_REQUIRED"}`
- [ ] All four rules satisfied → `ValidationResult {valid: true}`

---

### REQ-L3-WE002-002: SignatureGate-Delegierung an COMP-WE-004


**Implementation State:** Implemented
**Review Findings:** Anforderung ist durch Tests verifiziert und im Code auffindbar.
**Test Status:** Covered
**Remarks:** Regelmäßig auf Regressionen prüfen.


Erfordert eine Transition `signature_gate: true` und wurde ein Credential uebergeben, SHALL der TransitionValidator eine `CredentialVerificationRequest` an COMP-WE-004 (IF-WE-INT-004) senden. Das Ergebnis `VerificationResult {valid, seal?}` von COMP-WE-004 SHALL in das endgueltige `ValidationResult` einfliessen: bei `valid: false` wird `ValidationResult {valid: false, error_code: "SIGNATURE_INVALID"}` zurueckgegeben; bei `valid: true` wird `seal` an COMP-WE-003 weitergereicht (via IF-WE-INT-002 im Erweiterungs-Payload).

**Priority:** desired
**Acceptance Criteria:**
- [ ] Transition with `signature_gate: true`, correct password → `CredentialVerificationRequest` sent to COMP-WE-004, result `{valid: true}` propagated
- [ ] Transition with `signature_gate: true`, wrong password → COMP-WE-004 returns `{valid: false}`, TransitionValidator returns `{valid: false, error_code: "SIGNATURE_INVALID"}`
- [ ] `seal` from COMP-WE-004 is included in the payload forwarded via IF-WE-INT-002
- [ ] No call to COMP-WE-004 when `signature_gate` is absent or false

---

### REQ-L3-WE002-003: Validierungs-Performance-Budget


**Implementation State:** Implemented
**Review Findings:** Implementierung gefunden, aber keine Tests.
**Test Status:** Missing
**Remarks:** Testabdeckung fehlt.


Der TransitionValidator SHALL den gesamten Validierungsablauf (Regelprueung inkl. WorkflowDefinition-Abruf via IF-WE-INT-001, exkl. COMP-WE-004-Roundtrip) innerhalb von 10 ms abschliessen — gemessen unter Normal-Last (50 gleichzeitige Anfragen, 10.000 Items im System).

**Priority:** desired
**Acceptance Criteria:**
- [ ] 50 concurrent validation requests, 10,000 items → 95th percentile validation time < 10 ms
- [ ] WorkflowDefinition retrieval via IF-WE-INT-001 is not re-fetched per-request under stable definition (cached or pre-loaded)
- [ ] Validation time measured exclusive of COMP-WE-004 network/IPC roundtrip

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
