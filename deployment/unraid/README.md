# ReqogniLoom Unraid Deployment

This directory contains configurations for deploying ReqogniLoom on Unraid via Docker Compose Manager Plus.

## Overview

ReqogniLoom is an AI-native Requirements and Test Management tool with MBSE support. The full stack consists of 8 services:

- **postgres** (PostgreSQL 16 with pgvector) — persistent database
- **postgres-backup** — automated daily backups
- **redis** (Redis 7) — Celery broker and cache
- **backend** (Django 4.2+) — REST API + MCP server
- **migrate** (ephemeral) — database migrations, then self-init (admin account + default workflows, REQ-188)
- **celery** — async task worker (LLM calls, webhooks)
- **celery-beat** — periodic task scheduler
- **frontend** (React 18 + Vite) — web UI (port 5554)

## Prerequisites

1. **Unraid OS 6.12+** with Docker support
2. **Docker Compose Manager Plus** plugin installed:
   - Install via Unraid's Apps store (Community Applications)
   - Required because Unraid's native CA format does NOT support docker-compose multi-container stacks
3. **Git access** to clone or reference the ReqFlow repository (for Compose Manager to fetch `docker-compose.yaml`)

## Installation

### Step 1: Add the Stack to Compose Manager Plus

1. In Unraid WebUI → **Apps** → **Compose Manager Plus**
2. **Add New Stack** → paste the repository URL:
   ```
   https://github.com/Popoboxxo/ReqogniLoom
   ```
3. Point to the stack file:
   ```
   deployment/unraid/docker-compose.yaml
   ```
4. **Validate** — Compose Manager checks syntax and dependencies

### Step 2: Configure Environment Variables

1. In Compose Manager Plus stack editor, upload or create `.env` based on `.env.example`:
   ```bash
   # Copy from deployment/unraid/.env.example
   cp deployment/unraid/.env.example deployment/unraid/.env
   ```

2. **Edit `.env`** with your Unraid paths and secrets:

   **Critical Secrets (generate fresh values):**
   ```bash
   # Django secret key
   SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(50))")
   
   # JWT signing secret
   AUTH_JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")
   
   # Field-level encryption key (REQUIRED — no default, startup fails without it;
   # encrypts persistence.LlmSettings.api_key at rest). Keep it stable once set —
   # rotating without re-encrypting existing rows makes their api_key unreadable.
   FIELD_ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
   
   # Database password (superuser — used only by the one-shot `migrate` service)
   DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
   
   # Least-privilege app DB role password (backend/celery/celery-beat runtime
   # traffic — persistence/migrations/0048_app_role.py)
   DB_APP_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
   
   # Redis broker password
   REDIS_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
   
   # Admin account password (set once, never reset unless admin clears it via UI)
   SYSTEM_ADMIN_PASSWORD="your-strong-admin-password"
   ```

   **Unraid-Specific Paths:**
   ```bash
   # If using Compose Manager's build fallback, set repo root:
   REPO_ROOT=/mnt/user/appdata/ai-native-reqogniloom-POC
   
   # Or use pre-built images (no build needed, Compose Manager just pulls)
   # — in that case, leave build: sections out of docker-compose.yaml
   ```

   **Frontend URL (critical for SPA routing):**
   ```bash
   # This URL is baked into the production frontend build
   # Must be reachable from the browser
   VITE_API_BASE_URL=https://your-domain.example.com:8443
   VITE_ALLOWED_HOSTS=your-domain.example.com
   ```

   **Network Access:**
   ```bash
   # Must include your Unraid host IP and domain
   ALLOWED_HOSTS=your-domain.example.com,172.20.4.255,localhost,127.0.0.1,backend
   ```

3. **Upload `.env`** to Compose Manager Plus or paste contents into the stack environment section

### Step 3: Create Data Volumes

Compose Manager Plus will auto-create the Docker network, but **you must pre-create the host paths** for persistent storage:

```bash
# On Unraid terminal or SSH:
mkdir -p /mnt/user/appdata/reqogniloom/{db,backup,scripts}

# Optional: Set proper permissions (docker user)
chown -R 999:999 /mnt/user/appdata/reqogniloom
chmod -R 755 /mnt/user/appdata/reqogniloom
```

The docker-compose.yaml binds these volumes:
- `/mnt/user/appdata/reqogniloom/db` → postgres data
- `/mnt/user/appdata/reqogniloom/backup` → automated backups
- `/mnt/user/appdata/reqogniloom/scripts` → backup scripts (optional)

### Step 4: Start the Stack

1. In Compose Manager Plus, click **Start Stack**
2. Services will launch in dependency order:
   - postgres (waits for health check)
   - redis (waits for health check)
   - migrate (runs once, waits for postgres healthy; on completion self-init provisions the admin account and default workflows, REQ-188)
   - backend, celery, celery-beat (wait for postgres, redis, migrate completed)
   - frontend (waits for backend healthy)

3. Check logs in Compose Manager Plus for each service
4. Once frontend shows "healthy", access at `http://[your-unraid-ip]:5554` or your configured domain

### Step 5: First Login

- Username: `admin` (or `SYSTEM_ADMIN_USERNAME` from `.env`)
- Password: `SYSTEM_ADMIN_PASSWORD` from `.env`
- The `migrate` service's self-init provisions this account on first start (REQ-188)

## Architecture: Why No Multi-Container CA Template

Unraid Community Applications (CA) use an XML template format that:
- Can define a **single** docker container per template
- Does **not** natively support docker-compose multi-container stacks
- Cannot express dependency relationships like `depends_on` or `condition: service_completed_successfully`

ReqFlow requires:
- Ordered startup: postgres → redis → migrate → backend → frontend
- An ephemeral init container (migrate) with `restart: "no"`
- Proper health checks and service-completion conditions

**Solution:** Compose Manager Plus plugin bridges this gap. It:
- Reads standard docker-compose.yaml files
- Respects all compose directives (depends_on, volumes, networks, env_file)
- Manages the full 8-container lifecycle as a single "stack"

Therefore:
- **reqflow.xml** exists only as an entry point / documentation template for the frontend UI
- **docker-compose.yaml** is the source of truth for the full stack
- **Compose Manager Plus** is the deployment orchestrator

## Configuration Reference

### Environment Variables

See `.env.example` for all options. Key categories:

| Category | Variables | Notes |
|----------|-----------|-------|
| **Secrets** | SECRET_KEY, AUTH_JWT_SECRET, FIELD_ENCRYPTION_KEY, DB_PASSWORD, DB_APP_PASSWORD, REDIS_PASSWORD, SYSTEM_ADMIN_PASSWORD | Generate fresh values, never reuse |
| **Frontend** | VITE_API_BASE_URL, VITE_ALLOWED_HOSTS | Baked into build — rebuild frontend after changes |
| **Database** | DB_NAME, DB_USER, DB_PASSWORD, DB_APP_USER, DB_APP_PASSWORD | DB_USER/DB_PASSWORD (superuser) used only by `migrate`; DB_APP_USER/DB_APP_PASSWORD (least-privilege, RLS-enforced) used by backend/celery/celery-beat |
| **Redis** | REDIS_PASSWORD | Optional (auth), defaults to no password if empty |
| **CORS/CSRF** | CORS_ALLOWED_ORIGINS, CSRF_TRUSTED_ORIGINS | Required for production HTTPS access |
| **LLM Provider** | LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL | Options: anthropic, openai, ollama, mock (default) |
| **Backup** | BACKUP_INTERVAL, BACKUP_RETENTION | Defaults: 24h interval, 7 backups retained |

### Ports

- **Frontend:** 5554 → 80 (React UI)
- **Backend:** 8010 → 8000 (REST API, for direct access; use reverse proxy in production)
- **PostgreSQL:** not exposed (internal only)
- **Redis:** not exposed (internal only)

### Data Persistence

All volumes bind to `/mnt/user/appdata/reqogniloom/`:

```yaml
postgres:
  volumes:
    - /mnt/user/appdata/reqogniloom/db:/var/lib/postgresql/data

postgres-backup:
  volumes:
    - /mnt/user/appdata/reqogniloom/backup:/backups
```

**Backup retention:** Automated daily backups (configurable). Manually restore with:
```bash
docker compose exec postgres pg_restore -U reqogniloom -d reqogniloom < /mnt/user/appdata/reqogniloom/backup/dump.sql
```

## Common Tasks

### Rebuild Frontend After Config Changes

Frontend build-time variables (VITE_*) require a rebuild:

```bash
# In Unraid terminal or via Compose Manager UI:
docker compose -f deployment/unraid/docker-compose.yaml build --no-cache frontend
docker compose -f deployment/unraid/docker-compose.yaml restart frontend
```

### View Logs

```bash
# All services:
docker compose -f deployment/unraid/docker-compose.yaml logs -f

# Specific service:
docker compose -f deployment/unraid/docker-compose.yaml logs -f backend
docker compose -f deployment/unraid/docker-compose.yaml logs -f celery
```

### Check Stack Status

```bash
docker compose -f deployment/unraid/docker-compose.yaml ps
```

### Manual Database Backup

```bash
docker compose -f deployment/unraid/docker-compose.yaml exec postgres pg_dump -U reqogniloom reqogniloom > /mnt/user/appdata/reqogniloom/backup/manual-$(date +%s).sql
```

### Reset Admin Password

If you lose the admin password, reset it via Django shell:

```bash
docker compose -f deployment/unraid/docker-compose.yaml exec backend python manage.py shell
>>> from django.contrib.auth.models import User
>>> u = User.objects.get(username='admin')
>>> u.set_password('new-password')
>>> u.save()
>>> exit()
```

## Troubleshooting

### Containers Keep Restarting

- Check logs: `docker compose logs <service>`
- Common causes:
  - Missing `.env` → services crash on startup
  - DB_PASSWORD or SECRET_KEY not set
  - Port conflicts (5554, 8010 already in use)

### Frontend Can't Connect to Backend

- Check `VITE_API_BASE_URL` is reachable from your browser
- If using HTTPS, ensure backend is behind a reverse proxy (Nginx Proxy Manager, Swag, Traefik)
- Check CORS/CSRF settings match your domain

### Database Won't Start

- Check disk space: `df /mnt/user/appdata/`
- Check volume permissions: `ls -la /mnt/user/appdata/reqogniloom/db/`
- View postgres logs: `docker compose logs postgres`

### Admin Self-Init Didn't Provision

- Check `SYSTEM_ADMIN_PASSWORD` is set in `.env` (required on first start)
- View migrate logs: `docker compose logs migrate`
- If self-init already ran successfully once, changing `SYSTEM_ADMIN_PASSWORD` has no effect (admin exists, create-only)

## Security Notes

1. **Always use HTTPS** in production (reverse proxy with TLS termination)
2. **Store `.env` securely** — never commit to version control
3. **Rotate secrets periodically** — regenerate SECRET_KEY, DB_PASSWORD, etc.
4. **Restrict Unraid access** — authenticate WebUI, disable unnecessary ports
5. **Audit logs** — check ReqogniLoom audit logs for suspicious activity (REST API: `/api/v1/audit-logs/`)

## Support and Documentation

- **Repository:** https://github.com/Popoboxxo/ReqogniLoom
- **Issues:** https://github.com/Popoboxxo/ReqogniLoom/issues
- **Architecture:** See `docs/ARCHITECTURE.md` in the repo
- **API Documentation:** http://your-domain:5554/api/schema/ (Swagger UI)

---

**Generated for ReqogniLoom** — Last updated: 2026-07-25
