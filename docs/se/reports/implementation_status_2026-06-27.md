# ReqFlow — Implementierungsstand

> **Branch:** `feat/se-implementation`
> **Datum:** 2026-06-27
> **E2E-Tests:** 89 passed / 0 failed / 3 skipped (92 gesamt, Playwright/Chromium)
> **Commits auf Branch:** 63

---

## 1. Test-Ergebnis (aktuell)

```
89 passed | 0 failed | 3 skipped
Laufzeit: ~1,3 Minuten (Playwright, Chromium)
```

### Skipped — bewusste Gaps (Backend-Feature fehlt)

| Test | Datei | Grund |
|------|-------|-------|
| Language-Switch-UI | `stakeholder-needs.spec.ts` | i18n-Keys unvollständig gemappt |
| Requirement-History | `stakeholder-needs.spec.ts` | `GET /api/v1/requirements/:id/history/` nicht implementiert |
| Cross-Projekt-TraceLinks | `stakeholder-needs.spec.ts` | REQ-L0-019 noch nicht implementiert |

---

## 2. E2E-Testdateien (vollständige Liste)

| Datei | Abdeckung | Tests |
|-------|-----------|-------|
| `auth.spec.ts` | REQ-L0-022 — Login UI | 3 |
| `auth-api.spec.ts` | REQ-L0-022 — Login API | 3 |
| `dashboard.spec.ts` | REQ-L2-RF-002 — Workspace-Karten + Metriken | 3 |
| `workspace.spec.ts` | REQ-L2-RF-012 — Bootstrap + Switcher | 3 |
| `workspace-settings.spec.ts` | REQ-L2-RF-012 — Settings-Seite, Preset, Workspace anlegen | 3 |
| `requirements.spec.ts` | REQ-L2-RF-003 — Liste + Create | 4 |
| `requirement-editor.spec.ts` | REQ-L2-RF-004 — Inline-Edit, Markdown, change_reason | 3 |
| `architecture.spec.ts` | REQ-L2-RF-005 — Architecture CRUD via API | 2 |
| `architecture-editor.spec.ts` | REQ-L2-RF-005 — element_type, Markdown, TraceLink-Panel | 3 |
| `traceability.spec.ts` | REQ-L1-003 — TraceLinks via API | 2 |
| `traceability-view.spec.ts` | REQ-L2-RF-006 — TraceabilityView UI | 2 |
| `tracelink-creation.spec.ts` | REQ-L0-003, REQ-L2-RF-006 — TraceLink anlegen | 7 |
| `baselines-view.spec.ts` | REQ-L1-018 — Baselines UI | 3 |
| `search.spec.ts` | REQ-L1-009 — Globale Suche | 2 |
| `testcases.spec.ts` | REQ-L1-012 — TestCase API | 2 |
| `api-completeness.spec.ts` | REQ-L0-012 — CRUD alle Entitäten | 12 |
| `stakeholder-needs.spec.ts` | REQ-L0-001 bis REQ-L0-022 | 16 |
| `se-workflow.spec.ts` | REQ-L0-002/011, REQ-L2-RF-004/005/007/008 | 12 |

---

## 3. Implementierte Features

### Auth & Workspace-Bootstrap
- Credential-Login (Benutzername/Passwort → Bearer-Token)
- `AuthContext` Race Condition behoben: Token synchron im `useState`-Initializer und im `login()`-Callback gesetzt — vor dem ersten Re-Render von `WorkspaceContext`
- `WorkspaceContext` normalisiert alle Preset-Formate aus der API:
  - `"extended"` (String)
  - `{name: "extended"}` (Objekt Format 1)
  - `{tier: "minimal", language: "de", terminology_profile: "se_mode"}` (Objekt Format 2)

### Dashboard (`/`)
- Workspace-Karten mit Metriken (`requirement_count`, `open_item_count`)
- Terminologie-Profil-Label: dev_mode vs. se_mode
- Preset-Badge: minimal / standard / extended
- Klick → navigiert zu `/requirements`

### Sidebar (NavigationShell)
- Workspace-Switcher (`data-testid="workspace-switcher"`)
- Globale Suche mit 300ms Debounce + Live-Dropdown (`data-testid="global-search"`)
- `+ Workspace`-Formular mit Name, Preset, Sprache (`data-testid="create-workspace-btn"`)
- Navigation nach Workspace-Anlage ohne Seiten-Reload (`reloadWorkspaces` + `useNavigate`)

### Workspace Settings (`/settings`, `/workspace-settings`)
- Preset wechseln: minimal / standard / extended mit Feature-Beschreibung pro Option
- Terminologie-Profil: dev_mode / se_mode
- Sprache: DE / EN
- Name editieren
- Echte API-Calls: `PATCH /workspaces/:id/` + `PATCH /workspaces/:id/preset/`
- `data-testid="workspace-settings"`, `data-testid="preset-selector"`

### Requirement-Editor (`/requirements`)
- Inline-Edit: Titel, Beschreibung (Markdown-Preview)
- Kategorie-Dropdown (7 Kategorien: functional, non-functional, api, ui-ux, data, integration, test)
- Workflow-Status-Selector
- `change_reason`-Pflichtfeld bei Extended-Preset (`data-testid="change-reason-input"`)

### Architecture-Editor (`/architecture`)
- CRUD für Architektur-Elemente
- `element_type`-Selector: Component / Interface / Subsystem / Layer / Module (`data-testid="arch-element-type-select"`)
- `parent_id`-Selektor für Hierarchie (Subsystem → Komponente)
- Markdown-Preview für Beschreibung
- **TraceLink-Panel**: bestehende Links anzeigen, neue `satisfies`/`implements`/`verifies`/`derives-from`-Links zu Requirements anlegen (`data-testid="arch-tracelink-panel"`)
- `change_reason` bei Extended-Preset (`data-testid="arch-change-reason-input"`)

### Traceability-View (`/traceability`)
- Liste bestehender TraceLinks
- Create-Formular mit Source/Target-Dropdowns + Link-Type-Selector
- Default-Link-Typ: `satisfies`
- Backend-Fehlermeldungen korrekt extrahiert und angezeigt

### Baselines-View (`/baselines`)
- Liste + Create-Formular (Artifact-Selector + Scope)
- Nur sichtbar bei Standard/Extended-Preset
- `data-testid="baselines-view"` auf allen States (loading, error, success)
- `data-testid="create-baseline-btn"`

### Globale Suche
- `GET /api/v1/search/?q=...&workspace_id=...`
- `SearchViewSet` registriert in `urls.py`

---

## 4. Backend-Endpunkte (REST API)

| Endpunkt | Methoden | Status |
|----------|----------|--------|
| `/api/v1/auth/login/` | POST | ✅ |
| `/api/v1/workspaces/` | GET, POST | ✅ |
| `/api/v1/workspaces/:id/` | GET, PATCH | ✅ |
| `/api/v1/workspaces/:id/preset/` | PATCH | ✅ |
| `/api/v1/requirements/` | GET, POST | ✅ |
| `/api/v1/requirements/:id/` | GET, PATCH, DELETE | ✅ |
| `/api/v1/architecture/` | GET, POST | ✅ |
| `/api/v1/architecture/:id/` | GET, PATCH, DELETE | ✅ |
| `/api/v1/tracelinks/` | GET, POST | ✅ |
| `/api/v1/tracelinks/:id/` | DELETE | ✅ |
| `/api/v1/baselines/` | GET, POST | ✅ |
| `/api/v1/artifacts/` | GET | ✅ |
| `/api/v1/testcases/` | GET, POST | ✅ |
| `/api/v1/search/` | GET | ✅ |
| `/api/v1/requirements/:id/history/` | GET | ❌ nicht implementiert |

---

## 5. Preset-System (Backend)

- `PresetConfigEngine` (`presets/gate.py`): `switch_preset()`, `is_feature_enabled()`, `is_change_reason_required()`
- Cache: `_tier_cache` per workspace_id
- `BaselineViewSet.preset_endpoint_key = "baselines"` (korrigiert von `"baseline_endpoints"`)
- `change_reason` Pflicht in Extended enforced in `RequirementService.update_requirement()`

---

## 6. Stakeholder-Need-Abdeckung (L0)

| REQ-ID | Need | Testabdeckung |
|--------|------|---------------|
| REQ-L0-001 | MCP für AI-Agenten | Smoke-Test (HTTP-Ping) |
| REQ-L0-002 | Skalierbare SE-Tiefe | Preset-Wechsel UI + 3 Optionen |
| REQ-L0-003 | Vollständige Traceability | TraceLink Create + Liste |
| REQ-L0-004 | Baselines | Baseline Create + Liste |
| REQ-L0-005 | Konfigurierbarer Lifecycle | Workflow-Status sichtbar |
| REQ-L0-006 | Self-Hosted | App startet + Auth funktioniert |
| REQ-L0-007 | LLM optional | System funktioniert ohne LLM |
| REQ-L0-008 | Mandantenfähigkeit | workspace_id-Isolation API-Test |
| REQ-L0-009 | Zweisprachige UI | *(Skipped — i18n-Keys unvollständig)* |
| REQ-L0-010 | Terminologie-Flexibilität | dev_mode vs. se_mode im Dashboard |
| REQ-L0-011 | Audit-Trail | change_reason Feld sichtbar |
| REQ-L0-012 | REST API vollständig | CRUD alle Entitäten |
| REQ-L0-013 | Bulk-Import | ❌ nicht implementiert |
| REQ-L0-014 | GitHub-Integration | ❌ nicht implementiert |
| REQ-L0-015 | PDF-Export | ❌ nicht implementiert |
| REQ-L0-016 | Diagramme | ❌ nicht implementiert |
| REQ-L0-017 | ICD-Versionierung | ❌ nicht implementiert |
| REQ-L0-018 | ADR/Risiko/Issue | ❌ nicht implementiert |
| REQ-L0-019 | Cross-Projekt-Traceability | ❌ nicht implementiert |
| REQ-L0-020 | SE-Prozess-Metriken | ❌ nicht implementiert |
| REQ-L0-021 | Async Resilienz | ❌ nicht implementiert |
| REQ-L0-022 | Credential-Login | Login UI + API-Test |

---

## 7. Offene Punkte (priorisiert)

| Thema | Priorität | REQ-ID |
|-------|-----------|--------|
| Requirement-History-Endpoint | Hoch | REQ-L0-011 |
| Language-Switch vollständig (i18n-Keys) | Mittel | REQ-L0-009 |
| Cross-Projekt-TraceLinks | Mittel | REQ-L0-019 |
| ADR / Risiko / Issue Artefakte | Mittel | REQ-L0-018 |
| SE-Prozess-Metriken Dashboard | Mittel | REQ-L0-020 |
| PDF-Export | Niedrig | REQ-L0-015 |
| GitHub-Integration | Niedrig | REQ-L0-014 |
| Bulk-Import (CSV) | Niedrig | REQ-L0-013 |
| Diagramm-Editor (integriert) | Niedrig | REQ-L0-016 |
| ICD-Versionierung | Niedrig | REQ-L0-017 |
| Async Resilienz / Graceful Degradation | Niedrig | REQ-L0-021 |

---

## 8. Docker-Stack

| Service | Port | Status |
|---------|------|--------|
| Backend (Django) | 8000 | ✅ |
| Frontend (Vite) | 5173 | ✅ |
| PostgreSQL | 5432 | ✅ |
| Redis | 6379 | ✅ |
| Celery Worker | — | ✅ |

Login: `admin` / `admin12345`
Demo Workspace: `6d20f0b9-d2cf-46a0-b916-79f8b417210f` (preset: extended)

---

*Erstellt: 2026-06-27 | Branch: feat/se-implementation | 63 Commits auf Branch*
