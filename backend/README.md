# ReqFlow Backend

Django backend for ReqFlow — AI-native Requirements Management.

## App ↔ ARCH-L1 Mapping

Each Django app corresponds to one L2 subsystem from the L1 architecture
(`docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Architecture.md`).

| Django App | ARCH-L1 ID | System Name | Layer | REQ-L1 |
|---|---|---|---|---|
| `persistence` | ARCH-L1-010 | PersistenceLayer | 0 (Infrastructure) | REQ-L1-015, REQ-L1-025, REQ-L1-026 |
| `auth_tenancy` | ARCH-L1-011 | AuthAndTenancy | 0 (Infrastructure) | REQ-L1-010, REQ-L1-015 |
| `presets` | ARCH-L1-008 | PresetConfigEngine | 0 (Infrastructure) | REQ-L1-007, REQ-L1-014 |
| `audit` | ARCH-L1-012 | AuditLog | 0 (Infrastructure) | REQ-L1-011 |
| `llm_adapter` | ARCH-L1-009 | LlmAdapter | 1 (Domain Services) | REQ-L1-013 |
| `traceability` | ARCH-L1-007 | TraceabilityEngine | 1 (Domain Services) | REQ-L1-003 |
| `workflow` | ARCH-L1-005 | WorkflowEngine | 1 (Domain Services) | REQ-L1-009 |
| `baseline` | ARCH-L1-006 | BaselineService | 1 (Domain Services) | REQ-L1-008 |
| `application` | ARCH-L1-004 | ApplicationService | 2 (Orchestration) | REQ-L1-001, REQ-L1-002, REQ-L1-004, REQ-L1-012, REQ-L1-019..025 |
| `rest_api` | ARCH-L1-002 | RestApiAdapter | 3 (Interface Adapter) | REQ-L1-006 |
| `mcp_server` | ARCH-L1-003 | McpServer | 3 (Interface Adapter) | REQ-L1-005 |
| `diagram` | ARCH-L1-013 | DiagramService | 1 (Domain Services) | REQ-L1-027 |
| `icd` | ARCH-L1-014 | IcdManagement | 1 (Domain Services) | REQ-L1-028 |
| `se_metrics` | ARCH-L1-015 | SeMetrics | Read Model | REQ-L1-031 |
| `resilience` | ARCH-L1-016 | ResilienceOrchestrator | Cross-cutting | REQ-L1-032 |

**ReactFrontend (ARCH-L1-001)** lives in `../frontend/`.

## Integration Layers (Bottom-Up)

```
Layer 4: ReactFrontend (frontend/)          ← Step 12
Layer 3: rest_api, mcp_server               ← Steps 10–11
Layer 2: application                        ← Step 9
Layer 1: workflow, baseline, traceability,  ← Steps 5–8
          llm_adapter, diagram, icd
Layer 0: persistence, auth_tenancy,         ← Steps 1–4
          presets, audit
Cross:   resilience, se_metrics
```

## Architecture Decision Records (ADRs)

| ADR | Decision | App |
|-----|----------|-----|
| ADR-01 | MCP and REST both access ApplicationService directly (no REST→MCP chain) | `application`, `rest_api`, `mcp_server` |
| ADR-02 | LLM providers abstracted behind `LlmCapabilityInterface` | `llm_adapter` |
| ADR-03 | Tenant isolation via Row-Level + Custom Django Manager (no schema-per-tenant) | `persistence`, `auth_tenancy` |
| ADR-04 | Configurable Rigor as cross-cutting service (single source of truth) | `presets` |
| ADR-05 | Generic artifact data model + terminology profiles | `persistence`, `presets` |
| ADR-06 | Item lifecycle as configurable WorkflowEngine | `workflow` |
| ADR-07 | Baselines on 3 scopes (document/project/global) in one entity | `baseline` |
| ADR-08 | Self-hosted via Docker Compose (no Kubernetes in v1) | `docker-compose.yml` |
| ADR-09 | Full-text search via PostgreSQL (no separate search engine in v1) | `persistence`, `application` |
| ADR-10 | AuditLog operation-level in v1, field-level in v2 | `audit` |

## Development

```bash
# Start full stack
docker-compose up

# Run migrations
docker-compose exec backend python manage.py migrate

# Run tests
docker-compose exec backend pytest

# Django shell
docker-compose exec backend python manage.py shell
```

## Architecture References

- L1 Architecture: `docs/se/L1/Gesamtsystem/L1_Gesamtsystem_Architecture.md`
- L2 Architectures: `docs/se/L1/Gesamtsystem/L2/<SystemName>System/`
- Integration Strategy: `docs/se/integration-strategy.md`
- Interface Registry: `docs/se/interface-registry.md`
- Strategy: `docs/se/STRATEGY.md`
