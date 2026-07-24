# Phase 4: Prompt-Template-System

Implementierungsplan für die Prompt-Template-Funktionalität in ReqogniLoom.

## Ziele

- Standardisierte, wiederverwendbare Prompt-Vorlagen für LLM-Integration
- Template-Management über Admin-Interface
- Kontextuelle Template-Auswahl basierend auf Artifact-Typ
- Versionierung und Rollback-Fähigkeit

## Scope

### In Scope
- Backend: Template-Model, CRUD-Endpoints, Serializer
- Frontend: Template-Management-UI
- REST API: `/api/v1/prompt-templates/`
- MCP-Tools: Template-Verwaltung

### Out of Scope
- LLM-Provider-spezifische Optimierungen
- Advanced Prompt-Engineering
- Multi-Language Template-Varianten (Phase 5)

## Architektur

### Datenmodell
```
PromptTemplate
├── id (UUID)
├── name (str, unique)
├── description (str)
├── category (enum: decomposition|validation|synthesis|analysis)
├── artifact_type (FK → ArtifactType)
├── template_text (str, mit {{ placeholders }})
├── variables (JSON: required/optional params)
├── created_at / updated_at
├── is_active (bool)
└── version (int)
```

### REST-Endpoints
- `GET /api/v1/prompt-templates/` — Liste
- `POST /api/v1/prompt-templates/` — Erstellen
- `GET /api/v1/prompt-templates/{id}/` — Detail
- `PATCH /api/v1/prompt-templates/{id}/` — Update
- `DELETE /api/v1/prompt-templates/{id}/` — Löschen
- `POST /api/v1/prompt-templates/{id}/validate/` — Syntax-Check

### MCP-Tools
- `template:list` — Verfügbare Templates
- `template:get` — Detail eines Templates
- `template:render` — Template mit Variablen rendern

## Implementation Steps

1. **Datenmodell** — Django Model + Migrationen
2. **Serializer** — DRF Serializer mit Validierung
3. **ViewSet** — CRUD-Endpoints
4. **MCP-Integration** — Tool-Implementierung
5. **Frontend** — Template-Management-UI
6. **Tests** — Unit + E2E

## Timeline

| Phase | Dauer | Owner |
|-------|-------|-------|
| Design Review | 1d | Architect |
| Backend (Steps 1-4) | 4d | Developer |
| Frontend (Step 5) | 3d | Frontend |
| Testing (Step 6) | 2d | QA |
| **Total** | **10d** | — |

## Dependencies

- Phase 1: Artifact-Modell (✓)
- Phase 2: LLM-Adapter (✓)
- Phase 3: MCP-Server (✓)

## Offene Fragen

- [ ] Template-Vererbung (global/workspace/project)?
- [ ] Versionshistorie pro Template?
- [ ] Rate-Limiting für Template-Rendering?

---

*Erstellt: 2026-07-24*
