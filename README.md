# ReqFlow

**AI-native requirements and test management for systems engineering.**

## What is ReqFlow?

ReqFlow is an AI-integrated requirements management and test case tracking system designed for organizations ranging from simple project management to complex systems engineering workflows. Built on Django, React 18, and PostgreSQL, ReqFlow provides scalable artifact-based traceability, workflow automation, and intelligent integration points for large language models.

Whether you're managing a small backlog or orchestrating a multi-level systems architecture with MBSE-style decomposition, ReqFlow adapts to your rigor level and integrates seamlessly with your LLM tools.

## Features

### Core Capabilities
- **Requirements Management** — Create, organize, and manage requirements with workflow states and categorization
- **Architecture Elements** — Model systems engineering structures (MBSE-compatible)
- **Testcase Management** — Attach test cases to requirements and track coverage
- **Traceability** — Automatic and manual linking between requirements, architecture elements, and test cases (8 link types)
- **Baselines & Snapshots** — Capture and compare system states across time
- **Workflow Automation** — Configurable requirement states and transitions

### AI Integration
- **MCP Server** — 20 AI-powered tools for Claude, ChatGPT, and other LLM platforms
- **LLM Adapter** — Pluggable providers: Anthropic, OpenAI, Ollama, or mock mode
- **Semantic Linking** — Intelligent requirement matching and suggestions

### Enterprise Features
- **Multi-Tenancy** — Row-level security with automatic tenant isolation
- **Configurable Rigor** — 3 presets (minimal, standard, extended) adapt complexity to your team
- **Terminology Profiles** — Switch between dev-mode and systems engineering terminology
- **Audit Logging** — Complete activity history for compliance and debugging
- **Internationalization** — German and English interfaces

### Developer Experience
- **REST API** — Full-featured /api/v1/ with JWT authentication
- **Type-Safe Frontend** — React 18 + TypeScript + Vite
- **Comprehensive Tests** — 1060+ backend tests (pytest) + 31/32 E2E tests (Playwright)
- **Docker Compose** — Production-ready local development stack

## Architecture

```
Layer 4 (UI)       │  React 18 + TypeScript + Vite
                   │  (CSS Design System, i18n DE/EN, JWT Auth)
───────────────────┼─────────────────────────────────────
Layer 3 (API)      │  REST API (DRF, 6 ViewSets)
                   │  MCP Server (20 AI Tools)
───────────────────┼─────────────────────────────────────
Layer 2 (App)      │  Single Entry Point
                   │  16 Domain Services (Requirements, Tests, Architecture, etc.)
───────────────────┼─────────────────────────────────────
Layer 1 (Core)     │  LLM Adapter, Traceability Engine, Workflow, Baseline,
                   │  Diagram Generation, ICD (Interface Control Documents)
───────────────────┼─────────────────────────────────────
Layer 0 (Base)     │  Persistence, Auth & Tenancy, Presets, Audit Log
                   │
Cross-Cutting      │  SE Metrics, Resilience (Retry/Circuit-Breaker)
```

**Services:** postgres (PostgreSQL) + redis (caching/Celery) + backend (Django :8000) + frontend (Vite :5173) + celery (async tasks)

## How to Start

### Prerequisites
- Docker Desktop 4.0+ (or Docker Engine + Docker Compose)
- Node.js 18+ (for E2E tests only; Vite dev server runs in container)
- Git
- 4+ GB available RAM

### 1. Clone and Build

```bash
git clone <repository-url>
cd ai-native-reqflow-POC
docker-compose build
```

### 2. Start the Stack

```bash
docker-compose up
```

Wait for all services to be ready (backend and frontend should show "ready" or similar log messages).
Open a new terminal for the next step.

### 3. Initialize Database

```bash
# Run migrations
docker-compose exec backend python manage.py migrate

# Seed demo data (optional, recommended for first run)
docker-compose exec backend python manage.py seed_demo
```

### 4. Access the Application

- **Frontend:** http://localhost:5173
  - **Default credentials:** username=`admin`, password=`admin12345`
- **API:** http://localhost:8000/api/v1/
  - Get token: `POST /api/v1/auth/token/` with credentials
  - Full OpenAPI docs: http://localhost:8000/api/v1/docs/
- **Admin Panel:** http://localhost:8000/admin/
  - Same credentials as frontend

### 5. (Optional) Configure LLM Provider

By default, ReqFlow runs in **mock mode** (no actual LLM calls). To enable AI features:

```bash
# Stop the running stack
docker-compose down

# Set environment variables and restart
LLM_PROVIDER=anthropic LLM_API_KEY=sk-ant-... docker-compose up
```

**Supported Providers:**
- `anthropic` — Claude API (set `LLM_API_KEY`)
- `openai` — OpenAI API (set `LLM_API_KEY`)
- `ollama` — Local Ollama instance (set `LLM_OLLAMA_BASE_URL`, default: http://localhost:11434)
- `mock` — Dry-run mode, no API calls (default)

See `.env.example` for all available configuration options.

### Verify Installation

Check all services are running:

```bash
docker-compose ps
```

All containers should show `Up (healthy)` or `Up`.

## Running Tests

### Backend Tests (pytest)

```bash
# Run all backend tests
docker-compose exec backend pytest

# Run with coverage report
docker-compose exec backend pytest --cov=reqflow_backend --cov-report=html

# Run specific test file or directory
docker-compose exec backend pytest tests/test_requirements.py
```

**Status:** 1060+ tests, all passing on feat/se-implementation branch.

### End-to-End Tests (Playwright)

```bash
# Install dependencies (first time only)
cd e2e
npm install

# Run E2E tests (stack must be running)
npx playwright test

# Run with browser UI mode
npx playwright test --ui

# Run specific test file
npx playwright test tests/requirements.spec.ts
```

**Status:** 31/32 tests passing. See `e2e/README.md` for detailed documentation.

## MCP Server

ReqFlow includes a **Model Context Protocol (MCP) server** to integrate with Claude Desktop, ChatGPT, and other LLM platforms.

### Configure Claude Desktop

Add the following to `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "reqflow": {
      "command": "docker-compose",
      "args": ["exec", "-T", "backend", "python", "manage.py", "run_mcp_server"],
      "cwd": "/absolute/path/to/ai-native-reqflow-POC"
    }
  }
}
```

Restart Claude Desktop. The MCP server will automatically connect with 20 available AI tools:
- Requirement CRUD and search
- Architecture element management
- Testcase linking
- Traceability queries
- Baseline creation and comparison

See `docs/MCP_SERVER.md` for the complete tool reference.

## REST API

ReqFlow provides a RESTful API for programmatic access to all features.

### Quick Start

```bash
# Authenticate
curl -X POST http://localhost:8000/api/v1/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin12345"}'

# Use the token in subsequent requests
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/requirements/
```

### API Endpoints

| Resource | Endpoint |
|----------|----------|
| Requirements | `GET/POST /api/v1/requirements/` |
| Requirement Detail | `GET/PATCH/DELETE /api/v1/requirements/{id}/` |
| Test Cases | `GET/POST /api/v1/testcases/` |
| Architecture Elements | `GET/POST /api/v1/architecture_elements/` |
| Traceability Links | `GET/POST /api/v1/links/` |
| Baselines | `GET/POST /api/v1/baselines/` |
| Workflows | `GET/POST /api/v1/workflows/` |

Full OpenAPI specification available at http://localhost:8000/api/v1/docs/

## Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| **Backend** | Django | 4.2+ |
| | Django REST Framework | 3.14+ |
| | PostgreSQL (ORM) | 14+ |
| | Celery | 5.3+ |
| | Redis | 7.0+ (caching, message broker) |
| **Frontend** | React | 18+ |
| | TypeScript | 5+ |
| | Vite | 5+ |
| | TanStack Query | 5+ |
| | CSS Modules | Native |
| **Testing** | pytest | 7+ |
| | Playwright | 1.40+ |
| **Infrastructure** | Docker | 20.10+ |
| | Docker Compose | 2.0+ |
| **LLM Integration** | MCP SDK | Latest |
| | LLM Adapters | Anthropic, OpenAI, Ollama |

## Development Workflow

### Branch Strategy

Use feature branches for all development:

```bash
# Create a feature branch
git checkout -b feat/your-feature

# Or bugfix
git checkout -b fix/your-bugfix
```

### Code Conventions

- **Python:** PEP 8, type hints, docstrings for public functions
- **TypeScript:** ESLint config, Prettier for formatting
- **Commits:** Conventional Commits format: `feat(REQ-123): description` or `fix: description`

### Hot Reload

During development, changes to Python and TypeScript code trigger automatic reload:

```bash
# Backend auto-reloads on .py changes
docker-compose logs -f backend

# Frontend (Vite) auto-reloads on src/ changes
docker-compose logs -f frontend
```

## Configuration

### Environment Variables

Key variables (see `.env.example` for full list):

```bash
# Database
DATABASE_URL=postgresql://user:password@postgres:5432/reqflow

# Redis
REDIS_URL=redis://redis:6379/0

# LLM Provider
LLM_PROVIDER=mock  # or: anthropic, openai, ollama
LLM_API_KEY=...    # if not using mock

# Application
DEBUG=false
ALLOWED_HOSTS=localhost,127.0.0.1
SECRET_KEY=<generated-on-startup>

# Tenancy
DEFAULT_WORKSPACE_NAME=Default Workspace
```

### Presets & Rigor Levels

Configure complexity via workspace settings:

- **Minimal** — Requirements + basic workflow
- **Standard** — + Architecture elements, testcases, traceability
- **Extended** — + Baselines, advanced workflow, audit logging

### Terminology Profile

Switch requirement terminology:

- **dev_mode** — Developer-friendly labels (feature, epic, story)
- **se_mode** — Systems engineering terminology (requirement, specification, design element)

## Troubleshooting

### Services won't start

```bash
# Check logs
docker-compose logs backend
docker-compose logs frontend

# Rebuild images
docker-compose build --no-cache
docker-compose up
```

### Database migration fails

```bash
# Reset database (⚠️ deletes all data)
docker-compose down
docker volume rm ai-native-reqflow-poc_postgres_data
docker-compose up
docker-compose exec backend python manage.py migrate
```

### Frontend blank page

- Clear browser cache (Ctrl+Shift+Delete / Cmd+Shift+Delete)
- Check frontend logs: `docker-compose logs frontend`
- Verify API is accessible: `curl http://localhost:8000/api/v1/health/`

### E2E tests fail

```bash
# Ensure stack is running
docker-compose up -d

# Reinstall dependencies
cd e2e && npm install

# Run with debug output
DEBUG=pw:api npx playwright test
```

## Roadmap

### v1.1 (Next)
- ReqIF import/export for tool interoperability
- Test run tracking and execution history
- Visual requirement diffing (baseline comparison UI)
- Semantic search with RAG (requires LLM)

### v2.0 (Future)
- Comment threads and collaborative annotations
- Granular access control (role-based permissions per requirement)
- WebSocket-based real-time collaboration
- Embedded diagram editor (SysML, UML blocks)
- Automated compliance reporting (for safety standards like IEC 61508, DO-178B)

## License

[To be defined — add license file if applicable]

## Support & Contributing

For issues, feature requests, or contributions:

1. Check existing GitHub Issues
2. Open a new issue with context (error log, reproduction steps)
3. For PRs: ensure all tests pass and CODEBASE_OVERVIEW.md is updated

See `CONTRIBUTING.md` for detailed contribution guidelines.

---

**Built for teams that care about traceability.**
