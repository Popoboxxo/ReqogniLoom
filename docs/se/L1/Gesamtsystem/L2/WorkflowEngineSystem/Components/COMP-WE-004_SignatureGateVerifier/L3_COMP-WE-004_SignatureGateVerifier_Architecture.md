---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T12:00:00Z"
schema_version: "1.0.0"
---

# L3 SignatureGateVerifier Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-WE-004_SignatureGateVerifier
> **Parent:** L2_WorkflowEngineSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der SignatureGateVerifier ist die spezialisierte Sicherheitskomponente für kryptografische Credential-Verifizierung. Er prüft Passwörter mittels Constant-Time-Hash-Vergleich und TOTP-Tokens gemäß RFC 6238 gegen das AuthAndTenancy-System, generiert bei erfolgreicher Verifizierung ein kryptografisches Prüfsiegel als HMAC-SHA256 über `transition_id + timestamp + user_id`, und bleibt isoliert von WorkflowDefinitions und History-Logik. Alle Operationen sind Tenant-scoped.

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box hier keine weiteren SE-Subsysteme, sondern die internen Software-Klassen und Datenstrukturen.

### 2.1 Klassen und Module

- **`SignatureGateVerifier` (Klasse):** Hauptklasse, orchestriert Credential-Verifizierung und Siegel-Generierung.
- **`CredentialChecker` (Klasse):** Hilfsmethoden für Passwort-Vergleich (timing-safe) und TOTP-Validierung.
- **`HmacSealGenerator` (Klasse):** Generiert HMAC-SHA256-Siegel aus `transition_id + timestamp + user_id`.
- **`VerificationResult` (Datenklasse):** Rückgabewert mit `valid: Boolean`, `seal: String?` (nur bei `valid=true`).

### 2.2 Datenstrukturen

- **CredentialVerificationRequest (Input):**
  - `transition_id`: String (Transition-Identifikator)
  - `user_id`: UUID
  - `credential`: String (Passwort oder TOTP-Token)
  - `timestamp`: ISO-8601 DateTime (Request-Zeitstempel)
  - `tenant_id`: UUID (Tenant-Kontext)

- **VerificationResult (Output):**
  - `valid`: Boolean
  - `seal`: String (optional, nur bei `valid=true`, HMAC-SHA256 lowercase hex string)

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-WE004-001 (Credential-Verifizierung) | Methode `verify_credential(request: CredentialVerificationRequest) -> VerificationResult`: (1) Query AuthAndTenancy (IF-WE-EXT-IN-004) für User-Password-Hash oder TOTP-Secret. (2) Passwort: timing-safe Hash-Vergleich (z.B. `hmac.compare_digest()`). (3) TOTP: RFC 6238 Validierung mit ±30s Fenster. (4) Bei Fehler: Return `{valid: false}` ohne `seal`, kein Audit-Log. (5) Bei Erfolg: Siegel generieren (siehe REQ-L3-WE004-002). |
| REQ-L3-WE004-002 (HMAC-SHA256-Siegel) | Methode `generate_seal(transition_id, timestamp, user_id) -> String`: Compute `HMAC-SHA256(transition_id || timestamp || user_id)` mit serverseiteigem Key (via Env-Variable oder Secrets-Store, nicht hardcoded). Return lowercase hex string. Deterministic: gleiche Inputs → gleiche Siegel (für feste Key). |
| REQ-L3-WE004-003 (Isolation der Sicherheitslogik) | COMP-WE-004 hat keine Imports/Dependencies auf WorkflowDefinition, WorkflowState oder History-Models. Keine SQL-Writes auf Workflow-Tabellen. Interface ist auf IF-WE-INT-004 (Input), IF-WE-INT-005 (Output) und IF-WE-EXT-IN-004 (AuthAndTenancy) beschränkt. Unit-Tests benötigen keine Workflow-Fixtures. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-WE-INT-004 (eingehend):** `CredentialVerificationRequest {transition_id, user_id, credential, timestamp}` von TransitionValidator (COMP-WE-002).

- **Ausgänge (Outbound):**
  - **IF-WE-INT-005 (ausgehend):** `VerificationResult {valid, seal?}` zurück an StateLifecycleManager (über TransitionValidator).
  - **IF-WE-EXT-IN-004 (ausgehend):** Query an AuthAndTenancy zur Credential-Verifizierung (Passwort-Hash, TOTP-Secret).

---

## 5. Architectural Rationale

**ADR-L3-WE004-01 — Timing-Safe Credential-Vergleich**
*Entscheidung:* Passwort-Vergleich nutzt `hmac.compare_digest()` statt direktem String-Vergleich.
*Rationale:* Erfüllt REQ-L3-WE004-001 strikt. Verhindert Timing-Attacks, die aus unterschiedlich langen Vergleichszeiten Information leaken könnten. Standard-Security-Best-Practice.
*Alternative (abgelehnt):* Direkter String-Vergleich (`==`) — anfällig für Timing-Angriffe, Sicherheitslücke.

**ADR-L3-WE004-02 — HMAC-Schlüssel extern konfiguriert**
*Entscheidung:* HMAC-Schlüssel wird aus Umgebungsvariable oder Secrets-Store geladen, nie hardcoded.
*Rationale:* Erfüllt REQ-L3-WE004-002 strikt. Verhindert Schlüssel-Exposure in Quellcode. Production-ready Secrets-Management.
*Alternative (abgelehnt):* Hardcoded Key — unakzeptabel für Production, Sicherheitslücke.

**ADR-L3-WE004-03 — Isolation von Workflow-Logik**
*Entscheidung:* COMP-WE-004 kennt WorkflowDefinition, WorkflowState oder History nicht; nutzt nur IF-WE-INT-004/005 und IF-WE-EXT-IN-004.
*Rationale:* Erfüllt REQ-L3-WE004-003 strikt. Single Responsibility: nur Credential-Verifizierung + Siegel-Generierung. Testbarkeit ohne Workflow-Fixtures. Security-Komponente kann unabhängig audited und deployed werden.
*Alternative (abgelehnt):* Inline Credential-Verifizierung im TransitionValidator — Separation of Concerns verletzt, Security-Logik wird schwerer zu prüfen.

**ADR-L3-WE004-04 — No Audit-Log bei fehlgeschlagener Verifizierung**
*Entscheidung:* Failed Credential-Attempts werden NICHT in Audit-Log geschrieben.
*Rationale:* Erfüllt REQ-L3-WE004-001 strikt. Verhindert Brute-Force-Attacken die sich über Audit-Log verraten würden. Erfolgreiche Transitions werden später in StateLifecycleManager geloggt.
*Alternative (abgelehnt):* Jeder Versuch geloggt — Disk-I/O bei Brute-Force, potenzielle DoS-Anfälligkeit.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
