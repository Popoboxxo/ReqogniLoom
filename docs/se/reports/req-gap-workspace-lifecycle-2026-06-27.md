# Gap Analysis: Workspace-Lifecycle-Management

> **Datum:** 2026-06-27
> **Autor:** se-requirements-Agent
> **Analyse im Kontext:** `feat/se-implementation` — Workspace close/delete/archive

---

## Zusammenfassung

**Es gibt eine vollständige Lücke.** Workspace-Lifecycle-Management (Schließen, Reaktivieren, Löschen von Workspaces) ist weder auf L0/L1/L2-Requirements-Ebene spezifiziert noch im Backend (WorkspaceService, WorkspaceViewSet) implementiert.

---

## 1. Suchstrategie & Ergebnisse

### 1.1 Requirements-Durchsuchung

| Datei | Suchbegriffe | Ergebnis |
|-------|-------------|----------|
| `docs/se/L0/SN_Stakeholder_Needs.md` | close, delete, archive, lifecycle, deactivate, terminate | **Kein Treffer** — 22 SNs (REQ-L0-001..022) |
| `docs/se/L0/SN_Stakeholder_Needs_Backlog.md` | close, delete, archive, lifecycle, deactivate, terminate | **Kein Treffer** — 6 Backlog-SNs (REQ-L0-023..028) |
| `docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Requirements.md` | close, delete, archive, lifecycle, deactivate, terminate | **Kein Treffer** — 41 REQs (REQ-L1-001..041) |
| `docs/se/L1/Gesamtsystem/L2/*/L2_*_Requirements.md` | close, delete, archive, lifecycle, deactivate, terminate (in 19 L2-Dateien) | **Kein Treffer** — 0 L2-REQs adressieren Workspace-Lifecycle |
| Gesamter `docs/`-Baum via `grep` | `workspace.*(close\|delete\|archive\|lifecycle\|terminate)` | **1 Treffer** — nur JSON-Datei (nicht relevant) |

**Befund:** Kein einziges Requirement erwähnt die Operationen Close, Delete, Archive, Reactivate oder Terminate im Kontext von Workspaces.

### 1.2 Code-Durchsuchung

| Datei | Befund |
|-------|--------|
| `backend/application/workspace_service.py` | Nur `list_workspaces`, `get_workspace`, `create_workspace` implementiert. **Keine Lifecycle-Methoden.** |
| `backend/rest_api/views.py` (WorkspaceViewSet, Zeile 1262) | Explizit als **"read-only — list + retrieve"** deklariert. Keine Mutation außer `create` (via create-Methode nicht im ViewSet). |
| `backend/persistence/models.py` (Workspace, Zeile 168) | `is_active = models.BooleanField(default=True)` existiert, wird aber **nie auf False gesetzt**. Kein `closed_at`, `closed_by`, `deleted_at`. |

### 1.3 Relevante existierende REQs (für Traceability)

| REQ-ID | Relevanz |
|--------|----------|
| REQ-L1-010 | RBAC (Admin-Rolle für Lifecycle-Operationen erforderlich) |
| REQ-L1-011 | Audit-Trail (Lifecycle-Ereignisse müssen protokolliert werden) |
| REQ-L1-015 | Mandantenfähigkeit (Workspace-Isolation bei Delete erhalten) |
| REQ-L1-033 | Credential-Login (Auth-Basis für Lifecycle-Endpunkte) |
| REQ-L2-AT-003 | Role-Based Permission Enforcement (Admin-Check) |

---

## 2. Lücken-Details

### 2.1 Funktionslücke

Folgende Operationen existieren weder als REQ noch als Implementierung:

| Operation | Beschreibung | Fehlt in |
|-----------|-------------|----------|
| **Close** | Workspace auf `is_active=false` setzen, Daten bleiben lesbar | L0, L1, L2, Backend |
| **Reactivate** | Geschlossenen Workspace wieder aktivieren | L0, L1, L2, Backend |
| **Delete** | Workspace + alle abhängigen Daten kaskadierend löschen | L0, L1, L2, Backend |
| **Captcha-Bestätigung** | Bestätigung per Workspace-Name vor Hard-Delete | L0, L1, L2, Backend |
| **Lifecycle-Audit** | AuditLog-Eintrag bei Close/Reactivate/Delete | L0, L1, L2, Backend |
| **Lifecycle-UI** | Admin-Buttons + Confirmation-Modal im Frontend | L0, L1, L2, Frontend |

### 2.2 Konsequenzen der Lücke

1. **Kein Cleanup möglich:** Workspaces können nur per direktem Datenbankzugriff entfernt werden — fehleranfällig und nicht auditierbar.
2. **Keine Compliance-Archivierung:** Geschlossene Projekte können nicht als Read-Only-Archiv markiert werden.
3. **RBAC-Inkonsistenz:** Die Admin-Rolle (REQ-L1-010) hat keine Lifecycle-Operationen, obwohl dies implizit erwartet wird.
4. **Multi-Tenancy-Problem:** Ohne Delete können Workspaces nicht sauber aus einem Tenant entfernt werden.
5. **Datenmüll:** Nicht mehr benötigte Workspaces sammeln sich an, ohne entfernt werden zu können.

---

## 3. REQ-Design

### L0 — REQ-L0-029 (SN-29)

**Titel:** Workspace-Lifecycle-Management für Administratoren

**Beschreibung:** (siehe SN_Stakeholder_Needs.md — neu angefügt)

**Rationale:** Ohne expliziten Lifecycle können Workspaces nur über direkten Datenbankzugriff entfernt werden — fehleranfällig, inkompatibel mit Multi-Tenancy-Isolation und blockiert jede Form von Compliance-Archivierung. RBAC (REQ-L0-008) und Configurable-Rigor (REQ-L0-002) benötigen einen definierten Workspace-Lebenszyklus.

### L1 — REQ-L1-042

**Titel:** Workspace-Lifecycle-Operationen mit RBAC

**Beschreibung:** (siehe L1_Gesamtsystem_Requirements.md — neu angefügt)

**Architektur-Impact:** `false` — keine neue Architektur nötig; nur neuer Endpoint + Service-Methode innerhalb bestehender Struktur.

### L2-Skizze (für se-architect)

| L2-REQ | Subsystem | Beschreibung |
|--------|-----------|-------------|
| REQ-L2-AS-033 | ApplicationService | `close()`, `reactivate()`, `delete()` + `cascade_delete_workspace()` |
| REQ-L2-AT-019 | AuthAndTenancy | Admin-Rollen-Prüfung auf Lifecycle-Endpunkten (kein neues Component — bereits in COMP-AT-002) |
| REQ-L2-AL-004 | AuditLog | Neue Audit-Operationstypen: `workspace.close`, `workspace.reactivate`, `workspace.delete` (kein neues Component — bereits in COMP-AL-001) |
| REQ-L2-RF-017 | ReactFrontend | `WorkspaceAdminPanel`-Komponente in WorkspaceSettings |
| REQ-L2-RA-008 | RestApi | 3 neue Actions auf `WorkspaceViewSet`: `close`, `reactivate`, `delete` |

---

## 4. Empfehlung

1. **Sofort** REQ-L0-029 und REQ-L1-042 in die Requirement-Dokumente aufnehmen
2. **Nächster Schritt:** se-architect mit L2-Zerlegung beauftragen
3. **Implementierung** als separaten Task an se-developer/senior-developer delegieren

---

*Erstellt durch se-requirements-Agent | Gap-Analyse im Kontext feat/se-implementation | 2026-06-27*
