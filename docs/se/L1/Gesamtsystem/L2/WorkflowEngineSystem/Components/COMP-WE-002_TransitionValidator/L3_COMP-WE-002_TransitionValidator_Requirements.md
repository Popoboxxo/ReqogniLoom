---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T12:00:00Z"
schema_version: "1.0.0"
---

# L3 TransitionValidator Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-WE-002_TransitionValidator
> **Parent:** L2_WorkflowEngineSystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der TransitionValidator ist das zentrale Validierungs-Gateway für alle State-Transitions. Er prüft sequenziell vier Regeln (Transition-Existenz, Rollenberechtigung, change_reason-Pflicht, signature_gate-Erfordernis), gibt spezifische Fehlercodes zurück, delegiert SignatureGate-Verifizierung an COMP-WE-004, und hält das Performance-Budget (< 10 ms exkl. COMP-WE-004) ein. Alle Validierungen sind Tenant-scoped.

---

## 2. White-Box Design (Interne Struktur)

Da dies eine terminale Komponente ist, beschreibt die White-Box hier keine weiteren SE-Subsysteme, sondern die internen Software-Klassen und Datenstrukturen.

### 2.1 Klassen und Module

- **`TransitionValidator` (Klasse):** Hauptklasse, orchestriert vierstufige Validierungslogik.
- **`ValidationResult` (Datenklasse):** Rückgabewert mit `valid: Boolean`, `error_code: String?`, `error_message: String?`, `seal: String?` (nur bei erfolgreicher SignatureGate).
- **`RuleChecker` (Klasse):** Hilfsmethoden für jede der vier Validierungsregeln.
- **`DefinitionCache` (Klasse):** In-Memory-Cache für WorkflowDefinitions (GC-basiert, nicht persistent), um Performance-Budget zu halten.

### 2.2 Datenstrukturen

- **ValidationRequest (Input):**
  - `item_id`: UUID
  - `workspace_id`: UUID
  - `item_type`: String
  - `current_state`: String
  - `target_state`: String
  - `user_id`: UUID
  - `user_roles`: List[String]
  - `change_reason`: String (optional)
  - `credential`: String (optional, Passwort oder TOTP-Token)
  - `timestamp`: ISO-8601 DateTime
  - `tenant_id`: UUID

- **ValidationResult (Output):**
  - `valid`: Boolean
  - `error_code`: String (optional, z.B. "TRANSITION_NOT_ALLOWED", "ROLE_NOT_ALLOWED", "CHANGE_REASON_REQUIRED", "SIGNATURE_REQUIRED", "SIGNATURE_INVALID")
  - `error_message`: String (optional)
  - `seal`: String (optional, nur bei `valid=true` und SignatureGate bestanden)

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-WE002-001 (Vierstufige Transition-Regelvalidierung) | Methode `validate(request: ValidationRequest) -> ValidationResult`: Führt vier Regeln sequenziell aus: (1) Ruft IF-WE-INT-001 auf, lädt WorkflowDefinition (gecacht), prüft Transition-Existenz; (2) Prüft `user_roles` gegen `allowed_roles`; (3) Falls `requires_change_reason=true`, prüft `change_reason != null && != ""`; (4) Falls `signature_gate=true`, prüft ob `credential` übergeben. Bei Regelbruch: sofort Return mit spezifischem `error_code`. |
| REQ-L3-WE002-002 (SignatureGate-Delegierung) | Falls Regel 4 bestanden, Methode `validate_signature(request)`: Ruft COMP-WE-004 via IF-WE-INT-004 auf, sendet `CredentialVerificationRequest`, erhält `VerificationResult {valid, seal?}`. Falls `valid=false`, Return `ValidationResult {valid=false, error_code="SIGNATURE_INVALID"}`. Falls `valid=true`, `seal` in `ValidationResult` speichern. |
| REQ-L3-WE002-003 (Validierungs-Performance-Budget) | DefinitionCache reduziert IF-WE-INT-001 Roundtrip auf einmalig pro Workspace/Item-Type. Sequenzielle Regelprüfung mit Early-Exit. Zielzeit: 95th percentile < 10 ms (exkl. COMP-WE-004 IPC). |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-WE-EXT-IN-001:** REST API oder ApplicationService-Methode `validate_transition(item_id, target_state, change_reason?, credential?, ctx)`.
  - **IF-WE-EXT-IN-004:** Rollen-Kontext und User-ID aus AuthAndTenancy (implizit via `ctx`).

- **Ausgänge (Outbound):**
  - **IF-WE-INT-001 (eingehend):** Query an COMP-WE-001 für WorkflowDefinition (gecacht).
  - **IF-WE-INT-004 (ausgehend):** Credential-Verifizierung an COMP-WE-004.
  - **IF-WE-INT-002 (ausgehend):** Return `ValidationResult` an StateLifecycleManager (via ApplicationService).

---

## 5. Architectural Rationale

**ADR-L3-WE002-01 — Vierstufige Regel-Sequenzialisierung mit Early-Exit**
*Entscheidung:* Validierungsregeln werden in fester Reihenfolge gepräft; bei Fehler sofort Return (kein Durchprobieren aller Regeln).
*Rationale:* Erfüllt REQ-L3-WE002-001 strikt. Early-Exit reduziert durchschnittliche Validierungszeit. Spezifische error_codes ermöglichen präzises User-Feedback.
*Alternative (abgelehnt):* Alle Regeln parallel validieren — Fehlerbehandlung wird ambig (welcher Fehler gewinnt?), keine Leistungsersparnis ohne komplexe Parallelisierung.

**ADR-L3-WE002-02 — Definition-Cache für Performance-Budget**
*Entscheidung:* WorkflowDefinitions werden im Memory gecacht; bei Definition-Update wird Cache invalidiert.
*Rationale:* Erfüllt REQ-L3-WE002-003 strikt. Reduziert IF-WE-INT-001 Roundtrips und Datenbankzugriffe. GC-basierte Eviction minimiert Memory-Overhead.
*Alternative (abgelehnt):* Jede Validierung lädt Definition neu — Performance-Budget wird gerissen bei 50 concurrent requests, nicht skalierbar.

**ADR-L3-WE002-03 — SignatureGate als delegierte Verifizierung**
*Entscheidung:* COMP-WE-004 wird erst aufgerufen nach erfolgreicher Regel 1-3; Result wird direkt in ValidationResult propagiert.
*Rationale:* Erfüllt REQ-L3-WE002-002 strikt. Trennung der Concerns: TransitionValidator prüft WorkflowDefinition-Struktur, COMP-WE-004 prüft Credentials. IPC-Latenz ist für COMP-WE-004 akzeptabel, da es optional ist.
*Alternative (abgelehnt):* Credential-Verifizierung inline — Security-Logik wird schlecht wartbar, Zuständigkeiten verschwimmen.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
