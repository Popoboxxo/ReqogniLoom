# L3 AuthorizationService Requirements

> **Level:** L3 (Komponenten-Anforderungen)
> **Komponente:** COMP-AT-002 — AuthorizationService
> **Parent-System:** AuthAndTenancySystem (L2)
> **Status:** Entwurf

---

## Verantwortlichkeit

RBAC-Policy-Evaluierung pro Operation und Ressource. Preset-spezifische Rollenrestriktionen (Approver-Rolle nur im Extended-Preset). Empfängt `IdentityClaims` vom AuthenticationService und `TenantContext` vom TenantContextService; liefert einen binären Berechtigungsentscheid (allow/deny).

## Zugeordnete L2-Anforderungen

| REQ-L2 | Anforderungstext (Kurzform) |
|--------|-----------------------------|
| REQ-L2-AT-003 | RBAC-Policy-Enforcement: vier Rollen, operation- und ressourcenbezogen |
| REQ-L2-AT-004 | Approver-Rolle ausschließlich im Extended-Preset |
| REQ-L2-AT-006 | Rollenzuweisung-CRUD: nur Admin, Audit-Log, Preset-Validierung |

## Interne Schnittstellen

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AT-INT-001 | eingehend | COMP-AT-001 (AuthenticationService) | `IdentityClaims {user_id, roles, auth_method}` |
| IF-AT-INT-003 | eingehend | COMP-AT-003 (TenantContextService) | `TenantContext {tenant_id, tenant_name}` |

## Externe Schnittstellen (Komponente an Systemgrenze)

| IF-ID | Richtung | Gegenstelle | Vertrag |
|-------|----------|-------------|---------|
| IF-AT-EXT-OUT-002 | ausgehend | WorkflowEngine | Rollen-Check-Ergebnis (erlaubte Transitionen) |
| IF-AT-EXT-OUT-003 | ausgehend | RestApiAdapter / McpServer | Berechtigungsentscheid allow/deny — HTTP 403 bei Ablehnung |
| IF-AT-EXT-OUT-004 | ausgehend | PersistenceLayer | Rollenzuweisungs-CRUD (Django ORM) |

---

## L3 Komponenten-Anforderungen

### REQ-L3-AT002-001: RBAC-Policy-Evaluierung nach Vier-Rollen-Modell

Der AuthorizationService SHALL für jede eingehende Operation anhand der `IdentityClaims.roles` einen Berechtigungsentscheid nach dem Vier-Rollen-Modell (Admin, Editor, Viewer, Approver) treffen. Operationen ohne ausreichende Berechtigung SHALL mit HTTP 403 abgewiesen werden. Der Entscheid SHALL zustandslos und deterministisch sein.

| Rolle | Lesen | Schreiben | Workflow-Transitionen | Workspace-Konfiguration |
|-------|-------|-----------|------------------------|--------------------------|
| Admin | alle | alle | alle | alle |
| Editor | alle | Workspace-Artefakte | Standard | keine |
| Viewer | alle | keine | keine | keine |
| Approver | alle | Workspace-Artefakte | alle inkl. Approval | keine |

**Priority:** mandatory
**Traceability:** REQ-L2-AT-003
**Acceptance Criteria:**
- [ ] Viewer attempts POST on requirement → HTTP 403
- [ ] Editor attempts approval transition → HTTP 403
- [ ] Approver attempts approval transition → HTTP 200 (permitted)
- [ ] Admin can execute all operations → HTTP 200
- [ ] Viewer can execute all read operations → HTTP 200
- [ ] Decision is stateless: same inputs always produce same output

---

### REQ-L3-AT002-002: Preset-gebundene Approver-Rollenrestriktion

Der AuthorizationService SHALL die Approver-Rolle ausschließlich im Extended-Preset akzeptieren. Zuweisung oder Ausübung der Approver-Rolle in Minimal- oder Standard-Preset SHALL abgewiesen werden. Bei einem Preset-Wechsel von Extended zu Standard oder Minimal SHALL bestehende Approver-Zuweisungen suspendiert werden, ohne gelöscht zu werden.

**Priority:** mandatory
**Traceability:** REQ-L2-AT-004
**Acceptance Criteria:**
- [ ] Standard preset: `assign_role(user, "approver")` → error response
- [ ] Extended preset: `assign_role(user, "approver")` → success
- [ ] Approval transition in Minimal preset → HTTP 403
- [ ] Preset change Extended → Standard: existing approver assignments suspended, not deleted
- [ ] Suspended assignments reactivated on switch back to Extended preset

---

### REQ-L3-AT002-003: Rollenzuweisungs-CRUD mit Admin-Guard und Audit-Pflicht

Der AuthorizationService SHALL CRUD-Operationen für Rollenzuweisungen auf Workspace-Ebene bereitstellen. Nur Nutzer mit Admin-Rolle im betreffenden Workspace SHALL Rollen zuweisen oder entziehen dürfen. Jede Zuweisung und jeder Entzug SHALL einen Audit-Log-Eintrag erzeugen. Zielnutzer SHALL Workspace-Mitglied sein.

**Priority:** mandatory
**Traceability:** REQ-L2-AT-006
**Acceptance Criteria:**
- [ ] Admin assigns Editor role to workspace member → saved in DB + audit log entry created
- [ ] Non-admin attempts role assignment → HTTP 403
- [ ] Assignment of Approver role in Standard preset → error
- [ ] Target user not a workspace member → error response (not silent failure)
- [ ] `GET /api/v1/workspaces/{id}/members` returns members with their roles

---

*Erstellt durch se-requirements-Agent (L3-Component) | ReqFlow SE-Kaskade | 2026-06-21*
