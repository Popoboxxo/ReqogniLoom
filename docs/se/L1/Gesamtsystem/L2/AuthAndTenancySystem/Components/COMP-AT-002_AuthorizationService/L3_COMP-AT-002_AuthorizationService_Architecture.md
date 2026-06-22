---
step: architecture
agent: se-architect
iteration: 1
status: done
timestamp: "2026-06-22T00:00:00Z"
schema_version: "1.0.0"
---

# L3 AuthorizationService Architecture

> **Level:** L3 (Component white-box / Terminal)
> **Component:** COMP-AT-002_AuthorizationService
> **Parent:** L2_AuthAndTenancySystem_Architecture.md
> **Datum:** 2026-06-22
> **Status:** entworfen
> **Designation:** component (terminal)
> **decomposition_status:** terminal — component-level leaf, no further SE decomposition

---

## 1. Verantwortlichkeit

Der AuthorizationService ist die Entscheidungskomponente für Zugriffskontrolle. Er ist verantwortlich für:
- RBAC-Policy-Evaluierung nach Vier-Rollen-Modell
- Preset-gebundene Approver-Rollenrestriktion
- Rollenzuweisungs-CRUD mit Admin-Guard und Audit-Logging
- Deterministische, zustandslose Entscheidungen

---

## 2. White-Box Design (Interne Struktur)

### 2.1 Klassen und Module

- **`AuthorizationService` (Hauptklasse):** Public API für `decide_access()`, `assign_role()`, `revoke_role()`, `list_member_roles()`.
- **`RbacPolicyEvaluator` (Module):** Implementiert die Vier-Rollen-Matrix (Admin, Editor, Viewer, Approver) → operation/resource → allow/deny.
- **`PresetPolicyValidator` (Module):** Prüft Approver-Rolle nur im Extended-Preset, suspendiert bei Preset-Wechsel.
- **`RoleAssignmentManager` (Module):** CRUD für UserRole-Zuweisungen, Admin-Guard, Audit-Triggers.
- **`AuthorizationDecision` / `RoleAssignmentDTO`:** Datenstrukturen.

### 2.2 Datenstrukturen

- **RBAC-Matrix (Hard-Coded in RbacPolicyEvaluator):**

  | Rolle   | Lesen | Schreiben | Workflow-Übergänge | Workspace-Config |
  |---------|-------|-----------|-------------------|------------------|
  | Admin   | ja    | ja        | alle               | ja               |
  | Editor  | ja    | Workspace | Standard           | nein             |
  | Viewer  | ja    | nein      | nein               | nein             |
  | Approver| ja    | Workspace | alle+Approval      | nein             |

- **UserRole-Entity:**
  - `id`: UUID (Primary Key)
  - `user_id`: UUID (Foreign Key)
  - `workspace_id`: UUID (Foreign Key, Tenant)
  - `role`: String (admin|editor|viewer|approver)
  - `suspended_at`: DateTime (nullable, bei Preset-Wechsel)
  - `assigned_at`: DateTime
  - `assigned_by_user_id`: UUID (Audit-Trail)

- **AuthorizationDecision (output):**
  ```python
  {
    "allow": True | False,
    "decision_reason": "...",
    "applicable_roles": ["editor", "approver"]
  }
  ```

---

## 3. Erfüllung der Anforderungen

| REQ-L3 | Implementierungs-Ansatz |
|--------|-------------------------|
| REQ-L3-AT002-001 (RBAC-Evaluierung) | `decide_access(user_id, operation, resource_workspace_id, ctx)`: RbacPolicyEvaluator lädt user_roles, evaluiert gegen Matrix. HTTP 403 bei Denial. |
| REQ-L3-AT002-002 (Preset-Approver-Restriktion) | PresetPolicyValidator: bei assign_role("approver") in Minimal/Standard → error. Bei Preset-Wechsel Extended→Standard: suspended_at setzen (nicht löschen). |
| REQ-L3-AT002-003 (Role-CRUD mit Admin-Guard) | `assign_role(admin_user_id, target_user_id, role)`: (1) Admin-Check auf admin_user_id, (2) Target muss Workspace-Member sein, (3) PresetPolicyValidator prüfen, (4) Role persistieren, (5) Audit-Log generieren. |

---

## 4. Schnittstellen-Implementierung

- **Eingänge (Inbound):**
  - **IF-AT-INT-001:** `COMP-AT-001` (AuthenticationService) — `IdentityClaims {user_id, roles, auth_method}`
  - **IF-AT-INT-003:** `COMP-AT-003` (TenantContextService) — `TenantContext {tenant_id, tenant_name}`

- **Ausgänge (Outbound):**
  - **IF-AT-EXT-OUT-002:** WorkflowEngine — Rollen-Check-Ergebnis (erlaubte Transitionen)
  - **IF-AT-EXT-OUT-003:** REST API Adapter / MCP Server — Berechtigungsentscheid (HTTP 403 bei Denial)
  - **IF-AT-EXT-OUT-004:** Django ORM — UserRole-CRUD (mit Tenant-Isolation)

---

## 5. Architectural Rationale

**ADR-L3-AT002-01 — Explizite RBAC-Matrix im Code**

*Entscheidung:* Die Vier-Rollen-Matrix (Admin/Editor/Viewer/Approver) und ihre Permissions sind als Hard-Coded Matrix in `RbacPolicyEvaluator` definiert, nicht in DB.

*Rationale:*
- **Annahme:** RBAC-Modell ist stabil und Teil der System-Architektur, nicht konfigurierbar per Workspace.
- **Gewählter Ansatz:** Code-Spezifikation ermöglicht einfache Review und Audit.
- **Abgelehnte Alternative:** DB-Tabelle für Permissions — mehr Flexibilität, aber Komplexität, schwer zu migrieren.
- **Erfüllt REQ-L3-AT002-001:** Transparenz und Wartbarkeit.

---

**ADR-L3-AT002-02 — Preset-Binding für Approver-Rolle**

*Entscheidung:* Approver-Rolle ist nur im Extended-Preset erlaubt. Bei Preset-Wechsel zu Standard/Minimal wird die Rolle suspendiert (suspended_at), nicht gelöscht.

*Rationale:*
- **Annahme:** REQ-L3-AT002-002 fordert Preset-Binding. Suspension statt Deletion ermöglicht Rollback bei Preset-Rückwechsel.
- **Gewählter Ansatz:** suspended_at-Feld als soft-delete für Approval-Zuweisungen.
- **Abgelehnte Alternative:** Harte Löschung — keine Wiederherstellung möglich, Audit-Trail verloren.
- **Erfüllt REQ-L3-AT002-002:** Governance ist flexibel, Audit-Trail bleibt.

---

**ADR-L3-AT002-03 — Admin-Guard bei Role-Assignment**

*Entscheidung:* Nur Nutzer mit Admin-Rolle im Workspace dürfen Rollen zuweisen/entziehen. Zielnutzer muss Workspace-Member sein.

*Rationale:*
- **Annahme:** REQ-L3-AT002-003 fordert Admin-Guard. Workspace-Membership verhindert Shadow-Users.
- **Gewählter Ansatz:** Explizite Admin-Check + Membership-Validation vor Persistierung.
- **Abgelehnte Alternative:** Keine Checks → Sicherheitsrisiko.
- **Erfüllt REQ-L3-AT002-003:** Sicherheit und Governance sind gewährleistet.

---

*Erstellt durch se-architect-Agent | ReqFlow SE-Kaskade L2→L3 | 2026-06-22*
*Designation: component (terminal) — decomposition_status: terminal*
