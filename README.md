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
- **Visual Artifact Diff** — Side-by-side and unified field-level change highlighting for requirements, architecture elements, and test cases
- **History Endpoint** — Full audit trail per artifact (GET /api/v1/requirements/{id}/history/)
- **PDF Report Export** — Generate Requirement Documents and Traceability Matrices as PDF with metadata
- **Test Run Tracking** — Test-Run-Protokollierung with bulk result ingestion via REST and MCP
- **CSV Bulk Import** — Atomic CSV import for Requirements, ArchitectureElements, and TestCases
- **API-Key Management** — Create, list, and revoke API keys for CI/CD integration
- **Workflow Automation** — Configurable requirement states and transitions

### AI Integration
- **MCP Server** — 11 AI-powered tool groups (40+ tools) for Claude, Cursor, and other LLM platforms
- **LLM Adapter** — Pluggable providers: Anthropic, OpenAI, Ollama, or mock mode
- **AI Derivation** — Configurable prompts to intelligently decompose Stakeholder Needs into System Requirements
- **Semantic Glossary & Linking** — Intelligent requirement matching and terminology suggestions

### Enterprise Features
- **Multi-Tenancy** — Row-level security with automatic tenant isolation
- **Configurable Rigor** — 3 presets (minimal, standard, extended) adapt complexity to your team
- **Terminology Profiles** — Switch between dev-mode and systems engineering terminology
- **Audit Logging** — Complete activity history for compliance and debugging
- **Internationalization** — German and English interfaces

### Developer Experience
- **REST API** — Full-featured /api/v1/ with JWT authentication
- **Type-Safe Frontend** — React 18 + TypeScript + Vite
- **Comprehensive Tests** — 1,416 backend tests (pytest) + 111 E2E tests (Playwright/Chromium)
- **Docker Compose** — Production-ready local development stack

## Architecture

```
Layer 4 (UI)       │  React 18 + TypeScript + Vite
                   │  (CSS Design System, i18n DE/EN, JWT Auth)
───────────────────┼─────────────────────────────────────
Layer 3 (API)      │  REST API (DRF, 16 ViewSets + 2 APIViews)
                    │  MCP Server (11 Tool Groups, 40+ AI Tools)
───────────────────┼─────────────────────────────────────
Layer 2 (App)      │  Single Entry Point
                    │  19 Domain Services (16 Core + 3 v1.1)
───────────────────┼─────────────────────────────────────
Layer 1 (Core)     │  LLM Adapter, Traceability Engine, Workflow, Baseline,
                   │  Diagram Generation, ICD (Interface Control Documents)
───────────────────┼─────────────────────────────────────
Layer 0 (Base)     │  Persistence, Auth & Tenancy, Presets, Audit Log
                   │
Cross-Cutting      │  SE Metrics, Resilience (Retry/Circuit-Breaker)
```

**V-Model Traceability:** ReqFlow follows a 3-tier V-Model decomposition (L0 stakeholder needs → L1 system requirements → L2 subsystem requirements → L3 components), with full REQ traceability from stakeholder needs down to test cases.

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

### 4. Initialize Admin User (REQUIRED for first run)

The database is empty after migrations. You must seed the demo admin user before logging in:

```bash
# Creates: Tenant "demo", Workspace "Demo Workspace", User "admin" (password: admin12345), admin role
docker-compose exec backend python manage.py seed_demo
```

**Override default password** (optional):
```bash
docker-compose exec -e DEMO_ADMIN_PASSWORD="my-secure-pw" backend python manage.py seed_demo
```

The command prints the active credentials at the end. Re-running is safe (idempotent).

### 5. Access the Application

- **Frontend:** http://localhost:5173
  - **Default credentials:** username=`admin`, password=`admin12345` (from step 4)
- **API:** http://localhost:8000/api/v1/
  - **Get JWT token:** `POST /api/v1/auth/login/` with credentials:
    ```bash
    curl -X POST http://localhost:8000/api/v1/auth/login/ \
      -H "Content-Type: application/json" \
      -d '{"username":"admin","password":"admin12345"}'
    # → {"token": "eyJhbGc...", "user": {...}, "tenant_id": "...", "roles": ["admin"]}
    ```
  - **Use token:** `Authorization: Bearer <token>` header on all subsequent requests
  - **Validate token:** `GET /api/v1/auth/me/` returns the authenticated user
  - **Full OpenAPI docs:** http://localhost:8000/api/v1/docs/
- **Admin Panel:** http://localhost:8000/admin/
  - Same credentials as frontend

### 6. (Optional) Configure LLM Provider

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

ReqFlow has **1,400+ tests** across 4 layers. Run them based on what you need to verify.

### Quick Reference (Makefile)

The root `Makefile` provides single-command targets that run against the **running dev stack**
(`docker-compose up -d` first). This is the primary entry point for the normal development loop.

```bash
make test            # Backend (pytest) + Frontend (vitest) — the standard dev check. NO E2E.
make test-backend    # Backend unit + integration tests only (pytest)
make test-frontend   # Frontend unit tests only (vitest)
make test-e2e        # Playwright E2E — SEPARATE, MANUAL ONLY (see warning below)
```

> **`make test` never runs E2E.** Playwright is intentionally excluded from `make test` (not even
> as a dependency). Unit + integration tests are fast and safe to run on every change; E2E is slow,
> resource-intensive, and must be triggered explicitly. See [End-to-End Tests](#end-to-end-tests-playwright).

The sections below document each layer manually (without Docker/Make) for fine-grained control.

### Prerequisites

```bash
# Database: ReqFlow tests require PostgreSQL.
# Option A (recommended): Use the running Docker stack's Postgres
docker-compose up -d postgres
export DB_HOST=localhost   # Linux/macOS
# Windows PowerShell: $env:DB_HOST="localhost"

# Option B: Local PostgreSQL with a 'reqflow' database
createdb reqflow
export DB_HOST=localhost   # Linux/macOS
# Windows PowerShell: $env:DB_HOST="localhost"
```

### Backend Tests (pytest)

```bash
cd backend

# ALL backend tests (Django + pytest)
pytest -q

# With coverage report
pytest --cov=. --cov-report=term-missing --cov-report=html
# → open htmlcov/index.html

# By module (fast feedback during development)
pytest auth_tenancy -q          # RBAC, API-Key, Item-Permission, Tenant-Context
pytest mcp_server -q            # MCP tools, protocol, registry
pytest admin_ops -q             # Disaster Recovery
pytest application -q           # 16 ApplicationServices
pytest persistence -q           # Models, Tenancy, Migrations
pytest workflow -q              # Workflow + State-Lifecycle
pytest baseline -q              # Baseline + Diff

# Skip slow performance tests
pytest -m "not slow"

# Only the new MCP E2E suite (added 2026-06-28, 150+ tests)
pytest mcp_server/tests/test_e2e_all_tools.py -v
pytest mcp_server/tests/test_e2e_audit.py -v
pytest mcp_server/tests/test_e2e_sse_transport.py -v

# Single test by name
pytest -k "test_login_success" -v

# Reuse existing test database to speed up subsequent test runs (Recommended)
pytest --keepdb

# With Django check
python manage.py check && pytest -q
```

> **Warning:** It is highly discouraged to run `pytest` against the actual development database, as tests will truncate tables and delete your data. `pytest` automatically creates a separate `test_reqflow` database. Use `--keepdb` to persist this test database between runs.
> For End-to-End Tests (Playwright), the tests *do* run against the actual development environment.

**Status:** ~1,400 tests passing (last verified 2026-06-28 on `feat/se-implementation`).

### Frontend Unit Tests (Vitest)

```bash
cd frontend
npm install                  # first time only
npm test                     # run tests (Vitest)
```

**Note:** If you encounter `Invalid URL` errors for API calls during tests, you may need to configure a base URL in your test environment or provide a mocked fetch setup.

### End-to-End Tests (Playwright)

> **⚠️ Separate, opt-in test layer.** E2E tests are **not** part of `make test` and never run
> automatically. They drive a real browser against the full running stack, take minutes to complete,
> and consume significant CPU/RAM. Run them **only** when you deliberately want to verify UI flows —
> e.g. before a release or after touching UI-critical code.

Wir nutzen Playwright im Frontend für robuste UI-Tests und zur Bereitstellung eines MCP-Servers (Model Context Protocol), damit LLMs die UI testen können. Die UI ist mit über 400 `data-testid`-Attributen extrem LLM-freundlich aufgebaut.

**Prerequisite:** the full stack must be running (`docker-compose up -d`).

```bash
make test-e2e                # full suite via Makefile (installs deps + runs Playwright)

# Or manually:
cd e2e
npm install                  # first time only
npx playwright test          # full suite (~3 min)
npm run test:e2e:ui          # interactive UI mode
npm run mcp:playwright       # starte Playwright MCP Server für LLM-Agenten
```

**Status:** Playwright Setup & MCP integriert.

### Manual MCP Test (curl)

Verify the MCP server responds correctly to tool calls:

```bash
# 1. Get a JWT token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin12345"}' | jq -r .token)

# 2. Create an API key for MCP
API_KEY=$(curl -s -X POST http://localhost:8000/api/v1/api-keys/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"manual-test"}' | jq -r .key)

# 3. List your workspaces (read tool, no Admin needed)
WORKSPACE_ID=$(curl -s -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"workspace.get_context","params":{}}' \
  | jq -r .result.workspaces[0].id)

# 4. Query requirements
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d "{\\"jsonrpc\\":\\"2.0\\",\\"id\\":2,\\"method\\":\\"requirement.query\\",\\"params\\":{\\"workspace_id\\":\\"$WORKSPACE_ID\\",\\"limit\\":5}}"

# 5. Server health check (no auth)
curl http://localhost:8000/mcp/
# → {"server":"ReqFlow MCP Server","protocol":"JSON-RPC 2.0","transports":["http","sse","stdio"],"version":"1.0.0"}
```

### 7. Connect an MCP Client (Claude Desktop / Cursor)

You can connect external AI assistants like Claude Desktop or Cursor to ReqFlow's MCP server.
ReqFlow exposes an SSE (Server-Sent Events) transport endpoint for remote connections.

**Important:** You need an active API key to authenticate (see Step 5 above).

#### Example: Claude Desktop Configuration

Edit your `claude_desktop_config.json` (usually located at `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS or `%APPDATA%\\Claude\\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "reqflow": {
      "command": "curl",
      "args": [
        "-N", 
        "-s",
        "-H", "X-API-Key: YOUR_API_KEY",
        "http://localhost:8000/mcp/sse/"
      ]
    }
  }
}
```
*Note: Since ReqFlow provides an HTTP/SSE endpoint, we use `curl -N` to pipe the SSE stream into Claude Desktop's standard input. Alternatively, you can write a tiny Node.js script that connects to the SSE URL and bridges it to stdio.*

#### Example: Cursor IDE

In Cursor, go to **Settings > Features > MCP**:
1. Click **+ Add new MCP server**
2. **Name**: `ReqFlow`
3. **Type**: `sse`
4. **URL**: `http://localhost:8000/mcp/sse/`
5. **Headers**: Add a header `X-API-Key` with your API Key value.

## Production Deployment

ReqFlow is designed for self-hosted deployment on Linux/Unix servers using Docker Compose. This section covers hardening the stack for production use.

### Prerequisites

- Docker >= 24.0 and Docker Compose >= 2.20
- A Linux server (amd64) or macOS
- 8+ GB available RAM
- HTTPS reverse proxy (nginx, Traefik, etc.) or cloud load balancer

### Quick Start

1. **Clone and prepare:**

   ```bash
   git clone <repository-url>
   cd ai-native-reqflow-POC
   cp .env.example .env
   ```

2. **Configure .env** — critical for production:

   ```bash
   # Generate a strong Django SECRET_KEY:
   python3 -c "import secrets; print(secrets.token_hex(50))"
   
   # Edit .env and fill ALL CHANGE-ME fields:
   vim .env
   ```

   Key variables:
   - `SECRET_KEY` — generate with Python (above)
   - `DEBUG=False` — disable debug mode (default in .env.example)
   - `ALLOWED_HOSTS` — your server hostname(s)
   - `DB_PASSWORD` — strong password (32+ chars, random)
   - `LLM_PROVIDER` — leave as `mock` for core features without AI

3. **Build and start:**

   ```bash
   docker-compose build
   docker-compose up -d
   ```

4. **Initialize database:**

   ```bash
   # Run migrations
   docker-compose exec backend python manage.py migrate
   
   # Seed demo admin user (or create manually)
   docker-compose exec backend python manage.py seed_demo
   ```

5. **Verify all services:**

   ```bash
   docker-compose ps
   # All should show: Up (healthy) or Up
   ```

### Architecture

**Services:**
- **postgres** — pgvector/pgvector:pg16-alpine (PostgreSQL with pgvector extension)
- **redis** — redis:7-alpine (Celery message broker + caching)
- **backend** — Django REST API (:8000)
- **celery** — Async task worker (depends on redis and postgres)
- **frontend** — React + Nginx (:3000)

**Data Persistence:**
- `postgres_data` named volume — automatically managed by Docker
- (Optional) Redis persistence — configure in redis service if needed

### Reverse Proxy Setup (nginx example)

```nginx
# /etc/nginx/sites-available/reqflow
upstream backend {
    server localhost:8000;
}

upstream frontend {
    server localhost:3000;
}

server {
    listen 80;
    server_name your-domain.com;
    
    # Redirect HTTP → HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    
    # Frontend (React)
    location / {
        proxy_pass http://frontend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Backend API
    location /api/ {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }
    
    # MCP Server
    location /mcp/ {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        # For SSE (Server-Sent Events):
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
    
    # Admin interface
    location /admin/ {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Environment-Specific Configuration

**For Development:**

By default, `docker-compose.yml` is production-focused. To restore development conveniences:

```bash
# docker-compose.override.yml is automatically merged by Docker Compose
# It enables hot-reload, dev server, and weak defaults
# (it's already included in the repository)

docker-compose up
# Stack runs in dev mode with hot-reload
```

**For Production:**

Delete or rename `docker-compose.override.yml` and ensure only `docker-compose.yml` is used:

```bash
rm docker-compose.override.yml
docker-compose up -d
```

### PostgreSQL with pgvector

The postgres service uses `pgvector/pgvector:pg16-alpine` image, which includes the pgvector extension for vector-based semantic search. The migration system automatically enables the extension on first run.

No manual setup is required.

### Monitoring & Logs

```bash
# Check all services
docker-compose ps

# View logs
docker-compose logs -f backend      # Django logs
docker-compose logs -f celery       # Async task logs
docker-compose logs -f postgres     # Database logs
docker-compose logs -f redis        # Cache/broker logs
docker-compose logs -f frontend     # Frontend server logs

# Follow all logs
docker-compose logs -f
```

### Backup & Restore

**Backup database:**

```bash
docker-compose exec postgres pg_dump -U reqflow reqflow > backup.sql
```

**Restore database:**

```bash
docker-compose exec -T postgres psql -U reqflow reqflow < backup.sql
```

### Scaling Considerations

- **Multiple Celery workers:** Copy the `celery` service and rename each (celery-1, celery-2, etc.)
- **External Redis:** Configure `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` to point to external Redis
- **External PostgreSQL:** Configure `DB_HOST`, `DB_USER`, `DB_PASSWORD` to point to managed RDS/Cloud SQL
- **Load balancing:** Use Traefik, Kubernetes, or cloud load balancers in front of `docker-compose up`

### Security Checklist

- [ ] `.env` file with strong `SECRET_KEY` and `DB_PASSWORD`
- [ ] `.env` added to `.gitignore` (do NOT commit secrets)
- [ ] `DEBUG=False` in production
- [ ] `ALLOWED_HOSTS` set to your actual hostnames
- [ ] HTTPS enforced via reverse proxy or load balancer
- [ ] SSH key pair for server access (no password login)
- [ ] Firewall rules restrict ports (only 80/443 from internet, 5432/6379 from internal only)
- [ ] Regular backups of `postgres_data` volume
- [ ] Log aggregation configured (optional but recommended)

### Troubleshooting Deployment

```bash
# Check if stack is healthy
docker-compose ps
# Look for: Up (healthy)

# View error logs
docker-compose logs --tail 50

# Restart a service
docker-compose restart backend

# Rebuild and restart all
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Reset database (⚠️ WARNING: Deletes all data)
docker-compose down
docker volume rm ai-native-reqflow-poc_postgres_data
docker-compose up -d
docker-compose exec backend python manage.py migrate
```

### Troubleshooting Tests

```bash
# Tests can't connect to Postgres
export DB_HOST=localhost          # or 'postgres' if running inside docker
docker-compose ps                  # verify postgres is running

# Tests fail with "DISABLE_SERVER_SIDE_CURSORS"
# → Known Django+psycopg2 issue; pinned in test setup

# Migrations needed
docker-compose exec backend python manage.py migrate

# Stale __pycache__
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
```

## MCP Server

ReqFlow ships a native MCP (Model Context Protocol) server alongside the REST API. The server exposes **11 tool groups** (40+ individual tools) for requirements engineering, test management, traceability, workspace administration, permissions, backups, audit, and user management.

### Transport Endpoints

| Endpoint | Method | Transport | Authentication |
|----------|--------|-----------|----------------|
| `/mcp/` | POST | HTTP/JSON-RPC 2.0 | `X-API-Key: rfk_<key>` header OR `params.api_key` in body |
| `/mcp/sse/` | POST | SSE (single event) | `X-API-Key: rfk_<key>` header |
| `/mcp/` | GET | — | Server info / health check (no auth required) |
| (stdio) | — | stdio (local pipe) | `params.api_key` argument |

### Authentication

MCP tools authenticate via API keys prefixed with `rfk_`. To create one:

```bash
# 1. Obtain a JWT session token via the REST API
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"•••"}' | jq -r .access)

# 2. Create a new API key
curl -X POST http://localhost:8000/api/v1/api-keys/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"claude-desktop"}'
# Response: {"id":7, "key":"rfk_Ab12Cd34Ef56Gh78Ij90Kl12Mn34Op56Qr78St90Uv12", ...}
```

The plaintext key is returned **once** at creation. Store it securely.

### Quickstart — Call a Tool

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rfk_Ab12Cd34Ef56Gh78Ij90Kl12Mn34Op56Qr78St90Uv12" \
  -d '{
    "jsonrpc":"2.0",
    "id":1,
    "method":"tools/call",
    "params":{
      "name":"requirement.query",
      "arguments":{"workspace_id":1,"limit":5}
    }
  }'
```

### Client Configuration Examples

**Cursor (`.cursor/mcp.json`)**
```json
{
  "mcpServers": {
    "reqflow": {
      "command": "curl",
      "args": [
        "-s",
        "-X", "POST",
        "http://localhost:8000/mcp/stdio/",
        "-H", "X-API-Key: rfk_Ab12Cd34Ef56Gh78Ij90Kl12Mn34Op56Qr78St90Uv12",
        "-d", "@-"
      ]
    }
  }
}
```
*(Note: Since Cursor only supports stdio currently, we use `curl` to bridge stdio to the HTTP endpoint).*

**Claude Desktop (`claude_desktop_config.json`)**
```json
{
  "mcpServers": {
    "reqflow": {
      "command": "curl",
      "args": [
        "-s",
        "-X", "POST",
        "http://localhost:8000/mcp/stdio/",
        "-H", "X-API-Key: rfk_Ab12Cd34Ef56Gh78Ij90Kl12Mn34Op56Qr78St90Uv12",
        "-d", "@-"
      ]
    }
  }
}
```

### Tool Groups (11 prefixes, 40+ tools)

| Prefix | Purpose | Example tools | Role required |
|--------|---------|---------------|---------------|
| `requirement` | Read, create, update, decompose, validate requirements | `get`, `query`, `create`, `update`, `decompose`, `validate` | Member |
| `architecture` | Read, create, update, link architecture artifacts | `get`, `query`, `create`, `update`, `link` | Member |
| `test` | Read, create, link, run tests, report results | `get`, `query`, `create`, `update`, `link`, `run_create`, `run_get`, `run_report_results` | Member |
| `traceability` | Cross-cutting traceability queries | `query`, `artifact.search`, `artifact.get_tree`, `workspace.get_context` | Member |
| `artifact` | Artifact tree and comments | `get_tree`, `get_comments` | Member |
| `workspace` | **Admin** — close, reactivate, delete workspaces | `get_context`, `close`, `reactivate`, `delete` | Admin |
| `permissions` | **Admin** — RBAC rule management | `set_rule`, `list`, `revoke`, `check` | Admin |
| `admin` | **Admin** — Backup & restore (Captcha `RESTORE` required) | `backup_create`, `backup_list`, `restore` | Admin |
| `audit` | Audit log query | `query` (filters: actor, operation, workspace, time) | Member (own scope) / Admin (all) |
| `events` | Dead-letter-queue inspection & replay | `dlq_list`, `dlq_replay` | Member |
| `user` | **Admin** — User & role management | `create`, `assign_role`, `list`, `deactivate` | Admin |

### Security Notes

- **Never commit API keys.** The `rfk_` prefix is intentional so secrets-scanners can grep for it.
- **Keys inherit the creator's roles.** Creating a key as Admin gives it Admin scope; there is no separate key-role system.
- **All calls are audit-logged** (`actor`, `operation`, `workspace`, `params` summary, `timestamp`).
- **Workspace lifecycle (close/reactivate/delete)** and **permissions mutations** require Admin role; attempts return `PERMISSION_DENIED`.
- **Backup restore** requires the literal Captcha header `X-Captcha: RESTORE` in addition to Admin role.

See [`docs/CODEBASE_OVERVIEW.md`](docs/CODEBASE_OVERVIEW.md) for the complete tool reference and architecture overview.

## REST API

ReqFlow provides a RESTful API for programmatic access to all features.

### Quick Start

```bash
# Authenticate: exchange username/password for a JWT token
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin12345"}'
# → {"token": "eyJhbGc...", "user": {...}, "tenant_id": "...", "roles": ["admin"]}

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

### v1.1 (Implemented — 2026-06-27)
- ✅ PDF-Report-Export (Requirement Documents + Traceability Matrix)
- ✅ Test-Run-Protokollierung with bulk ingestion via REST and MCP
- ✅ CSV-Bulk-Import for Requirements / ArchitectureElements / TestCases
- ✅ Visual Artifact Diff (field-level change highlighting)
- ✅ History-Endpoint for full audit trail
- ✅ API-Key Management (list / create / revoke)
- ✅ Visual Baselines (existing) & Visual Baseline Diff
- ✅ Workspace-Lifecycle-Management (REQ-L1-042)
- ✅ Item-Level-RBAC (REQ-L1-039)
- ✅ Disaster Recovery (REQ-L1-046)

### v2.0 (Next)
- ReqIF import/export for tool interoperability
- Comment threads and collaborative annotations with @Mention
- Semantic search with RAG (requires LLM)
- WebSocket-based real-time collaboration
- Embedded diagram editor (SysML, UML blocks)
- Automated compliance reporting (for safety standards like IEC 61508, DO-178B)

### Changelog Highlights

Detailed requirement and architecture specifications: [`docs/se/`](docs/se/)

| Release | Date | Highlights |
|---------|------|------------|
| **v1.1.1 — Session 2026-06-28** | 2026-06-28 | 7 new waves: Workspace-Lifecycle MCP (REQ-L1-042), Item-Level-RBAC (REQ-L1-039), Disaster Recovery (REQ-L1-046), MCP wrappers for Audit/DLQ/User-Management. ~277 new tests. |
| **v1.1 — Session 2026-06-27** | 2026-06-27 | 1,130 pytest / 111 E2E tests; 9 L1 REQs decomposed (SE-Phases 1-6); 6 leaf REQs in Pipeline B (3 implemented); 3 continue REQs for v2.0 (ReqIF, Comments, RAG) |
| **v1.0 — Greenfield** | 2026-06-25 | 1,042 pytest tests; 16 L2 subsystems; 12 L2 architectures terminal; full SE-Kaskade L0→L2 |

## AI-Readable E2E Test Output

ReqFlow utilizes Playwright for end-to-end testing and provides two scripts that produce compact, AI-readable output. Because LLM context windows are limited, standard test outputs are too noisy. These scripts generate minimal, highly readable logs that a developer can paste into an AI assistant for failure analysis.

**These scripts are always triggered manually by the developer — never run autonomously by AI agents.**

### Available scripts
1. **Single Test / Module Execution:**
   `npm run test:e2e:ai -- tests/<name>.spec.ts`
   Uses the `--reporter=line` flag and provides a compact pass/fail list.
2. **Failure Analysis:**
   Playwright appends the DOM snapshot and stacktrace to the output for failed tests. The developer can hand this output to an AI assistant to identify a broken selector or state and propose a fix.
3. **Mass-Execution (Whole Suite):**
   `npm run test:e2e:ai-mass`
   Uses the `dot` reporter for a condensed summary, surfacing only regressions without flooding the output.

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
