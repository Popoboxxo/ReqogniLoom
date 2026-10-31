# ReqogniLoom — Deployment Examples

This directory holds the reference Docker Compose deployments for ReqogniLoom. Pick one file (or
combination), run it from the **repository root**, and the stack comes up.

> **After every deploy, run the verification gate in
> [`docs/DEPLOY_RUNBOOK.md`](../docs/DEPLOY_RUNBOOK.md).** A stack that reports healthy can still
> have written an empty database backup, a completely dead LLM, a proxy that 502s on login, and a
> memory worker that never runs — all four were real findings (#1074, #1050, #1051, #1052, #1054).

| File | Purpose | Use when |
|---|---|---|
| `docker-compose.yml` | Full stack: postgres, postgres-backup, redis, backend, migrate, celery, celery-beat, frontend. Optional Honcho memory backend (`honcho-postgres`/`honcho-redis`/`honcho-migrate`/`honcho`) gated behind the `honcho` Compose profile — costs nothing unless activated. | Production, or any deployment that needs async task processing and scheduled backups. **Default choice.** |
| `docker-compose.minimal.yml` | Slim stack: postgres, redis, backend, migrate, frontend only. No Celery worker/beat, no backup sidecar, no Honcho. | Quick try-out, or a small install that doesn't need async tasks (webhooks, long-running LLM calls, memory consolidation silently never run — see the file's own header comment) or automated backups. |
| `docker-compose.override.yml` | Dev overlay: hot-reload (`uvicorn --reload` / Vite dev server), source bind-mounts, weaker defaults. Auto-applied by `make up` (see repo-root `Makefile`). | Local development against the full stack only — **not** compatible with `docker-compose.minimal.yml` (it re-adds `celery`/`celery-beat`, defeating the point of minimal). |
| `docker-compose.override.example.yml` | Documentation only — a commented-out template for optional local services (e.g. Ollama). **Never read by Compose itself** (wrong filename on purpose); copy it to `docker-compose.override.yml` and uncomment what you need. | Reference when wiring up an optional local service. |

## Overlays that replace the frontend image (#1436)

The base `docker-compose.yml` pins the frontend as a **registry image**:

```yaml
frontend:
  image: ghcr.io/popoboxxo/reqogniloom-frontend:${REQOGNILOOM_VERSION:-1.8.0-beta.22}
```

Compose merges `image:` from the base unless the overlay **also sets `image:`**. An overlay that only
overrides `ports:`, `deploy:` limits or `build:` therefore still starts the GHCR image. That is the
#1436 failure mode: a locally built frontend with the re-vendored Bluepencil 0.5.0 layer was built,
the stack reported `healthy`, and `/bluepencil/latest/latest.json` still served the repo default
`0.1.0-alpha.2` because the overlay never overrode `image:`.

A correct overlay that replaces the frontend:

```yaml
services:
  frontend:
    image: reqogniloom-frontend:bluepencil-${REQOGNILOOM_VERSION}
    pull_policy: build        # or `never` for a prebuilt local image
    build:
      context: ./frontend
      dockerfile: Dockerfile
      target: production
      args:
        VITE_BLUEPENCIL_ENABLED: "1"
        VITE_BLUEPENCIL_ENVIRONMENT: dev
    ports: !override
      - "5173:8080"
```

Rules:

- `image:` is **mandatory** (and must be a different name/tag from the base registry image) whenever
  an overlay replaces the frontend.
- `pull_policy: build` (with `build:`) makes `up` rebuild instead of reusing a stale local tag;
  `pull_policy: never` is correct for a pre-built local image.
- `ports:` still needs `!override` (Compose appends port lists); see INFRA-01 in
  `docker-compose.override.yml`.
- The dev overlay already follows this pattern
  (`image: ${COMPOSE_PROJECT_NAME:-reqogniloom}-frontend:dev`).

### `docker compose pull` with a locally built frontend

A plain `docker compose pull` tries to pull every `image:` — including the local
`reqogniloom-frontend:bluepencil-…` tag, which has no registry entry — and aborts with
`pull access denied for reqogniloom-frontend`. Pull only the registry-backed services:

```bash
docker compose -f deploy/docker-compose.yml --project-directory . \
  pull postgres redis backend celery celery-beat migrate postgres-backup
```

If the overlay declares a `build:` section for the frontend, `pull --ignore-buildable` skips it
instead.

### Guard

After `up`, when `BLUEPENCIL_ENABLED=1`, verify that the running container is actually the locally
built image and serves the re-vendored layer:

```bash
bash deploy/verify-frontend-image.sh
```

It fails when the container runs a registry image, or when `BLUEPENCIL_IMAGE` names a different or
older layer. Run it as part of the runbook gate (see
[`docs/DEPLOY_RUNBOOK.md`](../docs/DEPLOY_RUNBOOK.md) §7).

## No frontend restart after a backend recreate (#1054)

The frontend's nginx resolves its upstreams **per request** through Docker's embedded DNS
(`resolver 127.0.0.11 ipv6=off valid=10s;` plus a `set $…_upstream` variable), for `/api/`, `/mcp/`
and the bluepencil sidecar alike.

**This is resolved — you do not have to restart the frontend after recreating the backend.** The old
`proxy_pass http://backend:8000;` resolved the name once, at worker start, and kept that IP, so every
`up -d` (which gives the backend container a new IP) left the proxy answering 502 on `/api/` and
`/mcp/` until the frontend was restarted too. Because the SPA is served by the same nginx, the UI kept
loading and only the login POST failed — which reads to the user as "wrong password" and is invisible
to every application health check.

The only residual is a `valid=10s` DNS cache window: a request in the first 10 seconds after a backend
recreate can still 502. Retry after 10 s. The verification command is in
[`docs/DEPLOY_RUNBOOK.md`](../docs/DEPLOY_RUNBOOK.md) §4.

## The database backup is verified, not assumed (#1074)

The `postgres-backup` sidecar dumps into the `postgres_backup_data` volume and prunes all but the
newest `BACKUP_RETENTION` dumps. A dump is only **published** if it passes two gates: a valid gzip
stream, and at least `BACKUP_MIN_COPY_BLOCKS` `COPY <table> (…) FROM stdin;` blocks. Anything else is
treated as a failed backup — the file is deleted, the failure is logged on stderr, and the exit status
is non-zero. `BACKUP_ONCE=true` runs exactly one dump and exits with *its* status, which is what the
post-deploy gate calls. Details and the exact commands:
[`docs/DEPLOY_RUNBOOK.md`](../docs/DEPLOY_RUNBOOK.md) §1. The logic is inlined in the compose file by
design (so the stack needs no repo file); `deploy/verify-backup-command.sh` extracts it back out and
regression-tests the failure semantics against a real throwaway Postgres.

A backup is only proven by restoring it (ADR-012). `deploy/verify-restore.sh` is the restore gate:
it produces a dump with the **real** inlined sidecar command block and restores it **atomically**
(`psql --single-transaction`) into an **isolated throwaway Postgres**, asserts every table's row
count matches (15/15), asserts 0 errors, and proves an injected error leaves **no half-restored
database**. The operator-facing contract and isolated-restore command are in
[`docs/DEPLOY_RUNBOOK.md`](../docs/DEPLOY_RUNBOOK.md) §6.

## LLM provider misconfiguration fails the deploy (#1050)

`LLM_PROVIDER=opencode_go` requires `LLM_OPENCODE_SESSION` — the Zen-Go endpoint answers
`400 MissingSessionID` without it, which kills every AI feature while `/health` stays 200. The
one-shot `llm-preflight` service checks that combination from the environment alone and exits
non-zero, and `backend`/`celery`/`celery-beat` declare
`depends_on: {llm-preflight, condition: service_completed_successfully}` — so a missing session value
now aborts `up -d` with an actionable message instead of producing a silently dead deployment. The
check is conditional: mock/anthropic/openai/ollama/azure deployments are unaffected.

> **Related (#1153):** this preflight only proves the session value is *present* in the environment.
> A Honcho deployment can still answer incorrectly if the `honcho` image drifts off its verified
> tag/digest — see `## Troubleshooting: Stale Honcho image (#1153)` below.

## Base images are pinned tag + digest (#1391)

Every third-party base image used by the Dockerfiles and the Compose files documented in the table
below is referenced as `IMAGE:TAG@sha256:<manifest-list-digest>`. The tag stays human-readable; the
digest makes the reference immutable, so a re-push of a moving tag (`python:3.12-slim`,
`redis:7-alpine`, `pg16`, …) can no longer change what we build or run without a commit.

| File | Reference |
|---|---|
| `backend/Dockerfile` (builder + runtime) | `python:3.12-slim@sha256:cb33f7f7…` |
| `frontend/Dockerfile` | `node:22.17.0-slim@sha256:b04ce4ae…`, `nginx:1.27-alpine@sha256:65645c7b…` |
| `deploy/docker-compose.yml` | `pgvector/pgvector:pg16@sha256:7b822b0a…` (×3), `redis:7-alpine@sha256:892022f9…` (×2), `node:22-slim@sha256:de170b39…` (bluepencil sidecar) |
| `deploy/docker-compose.yml` (optional profiles) | `ghcr.io/plastic-labs/honcho:v3.3.0@sha256:5bb8cf7a…` (×3), `qdrant/qdrant:v1.19.2@sha256:b7b0444c…` |
| `deploy/docker-compose.minimal.yml` | `pgvector/pgvector:pg16@sha256:7b822b0a…`, `redis:7-alpine@sha256:892022f9…` |
| `testing/docker-compose.test.yml` | `pgvector/pgvector:pg16@sha256:7b822b0a…`, `redis:7-alpine@sha256:892022f9…` |

Deliberately **not** digest-pinned: the `ghcr.io/popoboxxo/reqogniloom-{backend,frontend}` images,
which follow the release version-tag convention (`${REQOGNILOOM_VERSION}`) so a deployment can pick a
release by tag. The optional Honcho and Qdrant images are pinned too — see their own sections.

**Not covered yet (follow-up).** The claim above is scoped to the table. These still reference moving
tags and are **not** pinned by #1391:

- `.woodpecker.yml` — several, including an untagged `woodpeckerci/plugin-docker-buildx` and `alpine:latest`
- `.github/workflows/ci.yml:71,85`
- `.github/workflows/playwright.yml:27,40`

The two shell-based operational helpers are pinned outside the tables above:
`deploy/verify-restore.sh:50` and `deploy/verify-backup-command.sh:45` run
`pgvector/pgvector:pg16@sha256:7b822b0a…` — the same digest the Compose services use, so a restore or
backup self-check can never be validated against a different server build than production runs.
`verify-restore.sh` keeps its `RESTORE_SMOKE_PG_IMAGE` override; its digest lives in the default.

**Rule: pin the manifest list, never a platform manifest.** A multi-arch tag resolves to an *index*
(manifest list) whose digest covers every platform; the per-architecture child manifests each have a
different digest. Pinning a child digest makes the build fail on any other architecture
(`no matching manifest for linux/arm64`).

**Resolve or re-resolve a digest.** Take the top-level `Digest:` of the index. Note that the default
output starts with `Name:` — do **not** take the first line, extract the `Digest:` line:

```bash
# Preferred (version-independent): prints the index digest directly (no pull, no daemon state)
docker buildx imagetools inspect redis:7-alpine | sed -n 's/^Digest: *//p'
#   sha256:892022f9f18c26c92c30e15194d132f90044af87b94a491a75429bbc3982eab1

# Same value via --format (buildx ≥ 0.33 — exact template matching landed there):
docker buildx imagetools inspect redis:7-alpine --format '{{.Manifest.Digest}}'
#   On buildx ≤ 0.32.0 the template is prefix-matched, so this prints the whole human
#   block instead of only the digest. Use the `sed` form above on those versions.
```

If the `buildx` plugin is not installed, use the registry API directly:

```bash
# Registry API: HEAD on the tag with the index media types -> Docker-Content-Digest.
# This is exactly the value `docker buildx imagetools inspect` prints.
tok=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/redis:pull" | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')
curl -sI -H "Authorization: Bearer $tok" \
  -H "Accept: application/vnd.oci.image.index.v1+json" \
  -H "Accept: application/vnd.docker.distribution.manifest.list.v2+json" \
  https://registry-1.docker.io/v2/library/redis/manifests/7-alpine | grep -i docker-content-digest
```

> **Trap — `docker manifest inspect`.** Only the registry HEAD above (or `buildx imagetools
> inspect`) yields the index digest. `docker manifest inspect -v` lists one entry **per platform**;
> its `Ref:` / `Descriptor.digest:` values are the *child manifest* digests, not the index digest —
> do not copy them. The non-verbose `docker manifest inspect <image>:<tag>` is **not** a substitute
> either: it prints pretty-printed JSON assembled by the client, not the registry's raw manifest
> bytes, so hashing its output does **not** reproduce the registry digest.

**Verify a pin before committing** — the reference must resolve back to the same digest:

```bash
docker buildx imagetools inspect redis:7-alpine@sha256:892022f9f18c26c92c30e15194d132f90044af87b94a491a75429bbc3982eab1
```

**Automated bumps.** Dependabot's `docker` ecosystem owns this: `.github/dependabot.yml` lists one
entry per directory that holds a Docker manifest (`/backend`, `/frontend`, `/deploy`, `/testing`), and
it refreshes the digest while keeping the tag. Renovate, if used instead, needs its two `docker`
managers (`dockerfile`, `docker-compose`) configured for those same four directories, with
`pinDigests` enabled. Both only propose the change — review the diff and let the normal CI
(build + Trivy scan) gate it.

> **Digest pins and OS package patching are orthogonal.** Pinning freezes the *base layer*, but the
> `apk upgrade` / `apt-get upgrade` steps in the Dockerfiles still pull current patches from the
> rolling distro repo at build time. A digest bump is therefore a supply-chain refresh, not a
> substitute for rebuilds — the Trivy `exit-code: 1` gate in `docker-publish.yml` stays the
> authority on known CVEs.

## Optional profiles (off by default)


All three are Compose **profiles**: they cost nothing — no pull, no start — until you name them
(`--profile <name>` / `COMPOSE_PROFILES=<name>`, or the `make` wrappers). The profile choice is
per-invocation: a `down` without the same `--profile` flags leaves those containers running — see
[Teardown and upgrades](#teardown-and-upgrades-include-every-profile-you-ever-started).

| Profile | What | Status |
|---|---|---|
| `honcho` | Optional Honcho memory backend (`honcho-postgres`, `honcho-redis`, `honcho-migrate`, `honcho`). | Optional feature — fine to enable in production if you want it. |
| `qdrant` | Optional Qdrant vector backend (`qdrant`), for `MEMORY_BACKEND=qdrant` and/or `ARTIFACT_VECTOR_BACKEND=qdrant` (ADR-020; the two selectors are independent since T-A2-1). | Optional feature — **pgvector stays the default**; the vector index is regenerable from Postgres. Fine to enable in production if you want it (see below). |
| `bluepencil` | Sidecar for the in-app annotation/review layer. | **DEBUG/QS ONLY — never enable it in production.** It is a *debugging* aid for seeing and measuring the layer in the real app, not a product feature: the sidecar has **no user auth and no tenant isolation** — one JSON file is shared by every workspace. A future production path would be a DRF `review_notes` store with server-side auth, RBAC, CSRF, and tenant isolation (`docs/bluepencil-integration.md`). See `deploy/bluepencil/README.md`. |

## First Stumbling Block: CSRF Cookie Requires Matching Security Settings

**Before you deploy**, verify that `AUTH_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` are set to the **same value** in `.env`. This is a common misconfiguration in deployments without a TLS-terminating reverse proxy:

- **Without a reverse proxy** (development, HTTP-only deployments): Set both to `False` (empty string in `.env`).
- **Behind a reverse proxy with TLS termination** (HTTPS): Set both to `True`.

If they mismatch, every UI form submission fails with a raw Django 403 CSRF error, even though the session is valid.

**Verify the configuration is correct** after deployment by calling the health check:
```bash
curl http://localhost:8001/health/
```

If `"csrf_cookie_secure_matches_auth"` is `"mismatch"` in the response, you must fix `.env` and restart the backend container.

## Deprecated: bearer token in the login response body (#696)

`POST /api/v1/auth/login/` still returns the JWT as a `token` field in the response
body for API/CI tooling, and such a response is now marked `Deprecation: true`
(RFC 9745). The browser SPA does **not** use that field — it authenticates with the
httpOnly `reqogniloom_access` cookie (REQ-052). A JavaScript caller that stored the
body token would re-open exactly the XSS vector REQ-052 closed, which is why the
field is deprecated.

- **Default:** `AUTH_LOGIN_INCLUDE_BODY_TOKEN=True` — unchanged behaviour, so
  existing scripts keep working.
- **Opt out:** set `AUTH_LOGIN_INCLUDE_BODY_TOKEN=False` in `.env` to omit the field.
  Cookie login, `/auth/refresh/`, `/auth/me/` and API-key callers are unaffected.
- **Planned follow-up:** flip the default to `False` after a deprecation window,
  once tooling has moved to the cookie flow (or to a login-free API key).

## Breaking Change: v1.8.0-beta.7+ Security Hardening & Frontend Permissions (#894)

**If you upgraded from beta.6 and added a local override** (`docker-compose.override.yml` or custom `.env` / deployment script) with `user: root` or `tmpfs` entries for the frontend service: **remove those overrides now.**

- **Beta.6** required `user: root` + tmpfs on `/var/cache/nginx` / `/var/run` because the image expected root-owned paths.
- **Beta.7+** reversed this (SA-48): the frontend image now runs as non-root (uid 102), with `/var/cache/nginx` already app-owned in the image. The base compose files (`docker-compose.yml`, `docker-compose.minimal.yml`) were corrected to remove the tmpfs entry — but if you manually added a beta.6-era hotfix override, you must **delete or comment out** those lines, or the frontend will fail with `Permission denied` when nginx tries to write to the cache directory.

Symptom: frontend container in `Restarting (1)` loop with `mkdir() "/var/cache/nginx/client_temp" failed (13: Permission denied)` in logs. Fix: delete the `user:` and `tmpfs:` overrides from your `.env` or local compose files, then re-run `docker compose up -d`.

## 2FA: Gerät verloren / neues Staff-Konto

Staff-Konten können einen TOTP-Zweiten Faktor einrichten (sofern
`MFA_STAFF_ENFORCEMENT` nicht `off` ist). Ist das Authenticator-Gerät weg, wurde das
Gerät getauscht, oder sind nach einer Rotation von `FIELD_ENCRYPTION_KEY` die
gespeicherten TOTP-Secrets nicht mehr entschlüsselbar, hilft nur der Break-glass-Reset
auf der Kommandozeile. Dafür gibt es bewusst **keinen** REST- oder MCP-Weg:
`MfaService.reset` verlangt weder TOTP-Code noch Passwort — über eine API exponiert
könnte jeder Aufrufer den zweiten Faktor eines fremden Kontos entfernen.

```bash
docker compose -f deploy/docker-compose.yml --project-directory . \
  exec backend python manage.py mfa_reset <username> --reason "<Grund>"
```

Was der Befehl in **einer** Transaktion tut:

1. löscht TOTP-Gerät **und** alle Recovery-Codes des Kontos (Audit-Eintrag
   `user.mfa_reset`),
2. stellt einen **einmalig verwendbaren** Enrollment-Grant aus (Audit-Eintrag
   `user.mfa_enroll_grant`). Dessen Laufzeit ist auf höchstens 24 h begrenzt
   (`MFA_ENROLL_GRANT_TTL_SECONDS`, Default 86400 s); pro Konto existiert höchstens ein
   gültiger Grant, ein älterer unbenutzter wird dabei als verbraucht markiert.

Der Grant ist das, was das erneute Einrichten unter `MFA_STAFF_ENFORCEMENT=required`
überhaupt erlaubt (Binding Decision ENT-E7 = A). Er wird deshalb immer mit
ausgestellt — ohne ihn bliebe das Konto ausgesperrt. Scheitert einer der beiden
Schritte, wird der andere mit zurückgerollt, das Konto behält also seinen bisherigen
Zustand.

- `--reason` ist **Pflicht** und darf nicht leer sein. Grund und Actor-Label
  (`mfa_reset (CLI)`) stehen in den Audit-Einträgen sowie im Log
  `reqogniloom.security` — dort ohne Secrets oder Codes.
- Unbekannter Benutzername oder leerer Grund → `CommandError` mit Exit-Code 1; ein
  ganz fehlendes `--reason` bricht schon die Argumentprüfung ab (Exit-Code 2). In
  beiden Fällen wird nichts geschrieben.
- Für ein Konto, das nie enrolled war, ist der Aufruf unschädlich und stellt trotzdem
  einen Grant aus.
- Nach stdout/stderr gehen nur Benutzername, Zähler (Gerät/Codes entfernt) und die
  Ablaufzeit des Grants — keine Secrets, TOTP- oder Recovery-Codes (durch Tests
  abgesichert).

**Ablauf für den Nutzer:** innerhalb der Grant-Laufzeit (≤ 24 h) neu einloggen und den
zweiten Faktor einrichten; mit dem ersten bestätigten Code wird der Grant verbraucht.
Verstreicht die Frist, ist ein erneuter `mfa_reset` nötig. Ein deaktiviertes Konto
(`is_active=False`) kann nicht enrollen, solange es nicht reaktiviert ist — der Befehl
weist auf stderr darauf hin.

**Notfall: Rotation von `FIELD_ENCRYPTION_KEY`.** Nach einer Rotation lassen sich
bereits gespeicherte TOTP-Secrets in der Regel nicht mehr entschlüsseln; die
Verifikation schlägt dann fail-closed fehl. Betroffene Staff-Konten einzeln
zurücksetzen:

```bash
for u in alice bob; do
  docker compose -f deploy/docker-compose.yml --project-directory . \
    exec backend python manage.py mfa_reset "$u" --reason "FIELD_ENCRYPTION_KEY rotated"
done
```

Reihenfolge: erst den Schlüssel rotieren und den Dienst neu starten, dann die
betroffenen Konten zurücksetzen — andernfalls könnte ein Konto vor der Rotation noch
ein Gerät mit dem alten Schlüssel ausstellen. Ob ein Konto betroffen ist, zeigt der
Login (die zweite Stufe schlägt fehl) bzw. das `reqogniloom.security`-Log; eine
pauschale Aussage „alle Konten sind betroffen" ist nicht belegt, also einzeln prüfen.

## Required flag: `--project-directory .`

These compose files do **not** live in the repository root. Every direct `docker compose`
invocation against them MUST include `--project-directory .`, run from the repo root, in
addition to `-f`. Do not omit this flag — it is not optional convenience, it is required
for the stack to work correctly:

- Without it, Compose looks for `.env` relative to `deploy/` instead of the repo root, so none
  of your configured secrets/overrides are picked up.
- Without it, any relative bind-mount resolves relative to `deploy/` instead of the repo root, and
  the container either fails to start or mounts an empty/wrong directory. `docker-compose.yml` and
  `docker-compose.minimal.yml` themselves have none (every service runs a stock or published
  image, no repo files needed) — this only bites once you add `docker-compose.override.yml`
  (`./backend`, `./docs`, `./frontend`, for local hot-reload development).
- `deploy/docker-compose.override.yml` does **not** auto-merge the way a root-level
  `docker-compose.override.yml` would — Compose's automatic override discovery only triggers
  when both files sit in the same directory and no `-f` flag is passed. Once `-f` is used (which
  it must be here, since the files are not in the default location), the override has to be
  passed explicitly with its own `-f`, every time.

The canonical command shape is always:

```bash
docker compose -f deploy/docker-compose.yml [-f deploy/docker-compose.override.yml] [--profile honcho] --project-directory . <subcommand> [args...]
```

The repo-root `Makefile` wraps the common cases (`make up`, `make down`, `make minimal`,
`make minimal-down`, `make honcho`, `make build`) so day-to-day use does not require typing the
full invocation — but the flags above are what those targets expand to, and are required if you
call `docker compose` directly instead.

## Full stack — step by step

1. From the repository root:
   ```bash
   cp .env.example .env
   ```
2. Running more than one instance on the same host (e.g. QS + PROD)? Set `BACKEND_PORT`/
   `FRONTEND_PORT` in `.env` to distinct values per instance — this is the exact class of
   collision that caused the 2026-08-31 incident that started this whole compose rework
   (see `docs/UMSETZUNGSPLAN_DOCKER-COMPOSE-2026-08-31.md`). Defaults: `8001`/`5173`.
3. Fill in the required secrets in `.env` — `SECRET_KEY`, `AUTH_JWT_SECRET`,
   `FIELD_ENCRYPTION_KEY`, `DB_PASSWORD`, `DB_APP_PASSWORD` have no default and the stack refuses
   to start without them. `SYSTEM_ADMIN_PASSWORD` is different: leaving it empty does **not**
   abort the stack, it only skips auto-provisioning the admin user (logged, not fatal — see
   `backend/application/self_init.py`); set it if you want an admin account created automatically
   on first start. (See `.env.example` for the full annotated list and generation commands.)
4. Start the stack:
   ```bash
   docker compose -f deploy/docker-compose.yml --project-directory . up -d
   ```
   For local development with hot-reload instead, use `make up` (equivalent to adding
   `-f deploy/docker-compose.override.yml` to the command above).
5. Wait for all services to report healthy:
   ```bash
   docker compose -f deploy/docker-compose.yml --project-directory . ps
   ```
6. Verify the backend is serving:
   ```bash
   curl http://localhost:8001/health/
   # → {"status": "ok", "checks": {"database": "ok"}, ...}
   ```

### Persisted state (named volumes)

Everything that outlives a container is a **named Docker volume** — `docker compose down`
(without `-v`) keeps them, `down -v` wipes the stack. Bind mounts are used only by the dev
override; the minimal stack declares the first two plus `backend_dr_backups`. Stopping a stack
that used profiles needs those profiles on `down` too — see the teardown section below.

| Volume | Mount | Holds |
|---|---|---|
| `postgres_data` | `postgres:/var/lib/postgresql/data` | the database |
| `redis_data` | `redis:/data` | the Celery queue + cache (AOF is on, so it must survive a recreate) |
| `postgres_backup_data` | `postgres-backup:/backups` | nightly `pg_dump` dumps (full stack only) |
| `backend_dr_backups` | `backend:/app/backups` | admin DR dumps (`admin.backup_create`) |
| `honcho_postgres_data`, `honcho_redis_data` | Honcho services | only with `--profile honcho` |
| `bluepencil_data` | `bluepencil:/data` | review notes, only with the `bluepencil` profile |
| `qdrant_data` | `qdrant:/qdrant/storage` | Qdrant vector index, only with the `qdrant` profile — **not** in the Postgres dump; regenerable from Postgres (see the Qdrant section) |

## Teardown and upgrades: include every profile you ever started

Profiles are opt-in at **start** time, and Compose only manages the containers whose profiles are
active in the *same* invocation. A plain `docker compose down` therefore leaves profiled containers
(`honcho`, `honcho-*`, `qdrant`, `bluepencil`) running — and `--remove-orphans` does **not** remove
them: they belong to the project, they are merely profiled. The result after a version upgrade is a
mixed stack in which the default services are recreated while a profiled container keeps running for
days (#1354).

Name the full profile set on `down` (run from the repository root):

```bash
docker compose -f deploy/docker-compose.yml --project-directory . \
  --profile honcho --profile qdrant --profile bluepencil down
```

`make down` does not activate profiles either; use the command above whenever a profile was ever
started.

**Alternative: pin the profile set for the whole session.** Export the same list so `up` and `down`
cannot disagree:

```bash
export COMPOSE_PROFILES=honcho,qdrant,bluepencil   # bluepencil: DEBUG/QS only
docker compose -f deploy/docker-compose.yml --project-directory . up -d
docker compose -f deploy/docker-compose.yml --project-directory . down
```

**Warning: `-v` deletes data.** `down` alone keeps the named volumes listed above; adding `-v`
removes them — the database, the Celery queue, Honcho's memory and the Qdrant index. Use it only for
a deliberate reset:

```bash
# DESTRUCTIVE: wipes postgres/redis/honcho/bluepencil/qdrant volumes
docker compose -f deploy/docker-compose.yml --project-directory . \
  --profile honcho --profile qdrant --profile bluepencil down -v
```

**Recommended upgrade sequence:** `down` with the full profile set → `docker compose pull` → `up -d`
with the same profile set. That guarantees no container from the previous release survives the
upgrade.

The minimal stack has no profile-gated services; the same rule applies with
`-f deploy/docker-compose.minimal.yml`.

## Minimal stack

Same sequence, different `-f` path:

```bash
docker compose -f deploy/docker-compose.minimal.yml --project-directory . up -d
docker compose -f deploy/docker-compose.minimal.yml --project-directory . ps
curl http://localhost:8001/health/
```

No Celery worker/beat, no backup sidecar, no Honcho. Async-task-dependent features (LLM
long-running calls, webhooks, GitHub sync, memory consolidation) silently enqueue and never run —
see the header comment in `docker-compose.minimal.yml` for the exact list.

## Optional: Honcho memory backend

Add `--profile honcho` to the full-stack command (not available on the minimal stack):

```bash
docker compose -f deploy/docker-compose.yml --project-directory . --profile honcho up -d
```

Then set `MEMORY_BACKEND=honcho` and `HONCHO_BASE_URL=http://honcho:8000` in `.env` and restart
`backend`/`celery`.

All three Honcho **runtime** services (`honcho`, `honcho-postgres`, `honcho-redis`) carry
`restart: unless-stopped` (#1249), so a crash or host reboot no longer leaves the memory
backend silently down while the stack still reports as started. The one-shot services
(`migrate`, `llm-preflight`, `honcho-migrate`) stay at Compose's default `no` on purpose — an
auto-restart would re-run migrations/preflight in a loop. The contract is regression-guarded by
`backend/memory/tests/test_honcho_deploy_contract.py`.

**Ollama keep-alive (G2.4, #1401):** when `EMBEDDING_PROVIDER=ollama`, `EMBEDDING_KEEP_ALIVE`
is sent with every embedding request (`"30m"` by default). Ollama unloads an idle model after
5 minutes, so without it the first embedding after a quiet period pays the model-load cost
again. Unset/empty leaves the field out and Ollama's own default applies.

Honcho needs a reachable OpenAI-compatible embedding endpoint before it can write memories.
There is **one** embedding configuration per deployment, not two. `HONCHO_EMBEDDING_MODEL` and
`HONCHO_EMBEDDING_VECTOR_DIMENSIONS` are **overrides**: unset, every Honcho service falls back to
the deployment-wide `EMBEDDING_MODEL_NAME` / `EMBEDDING_VECTOR_DIMENSIONS` that `backend`/`celery`
embed with, so switching the app's provider cannot silently leave Honcho at a different width. The
compose services read these four vars from `.env` (defaults shown, `${…:-${…:-…}}` = "Honcho
override, else deployment-wide EMBEDDING_*, else the literal default"). `honcho-migrate` and
`honcho` both use them for the embedding config, and `backend`/`celery` read the raw vars for the
`/health` `memory_backend` health probe (#911):

| Variable | Default | Notes |
|----------|---------|-------|
| `HONCHO_EMBEDDING_BASE_URL` | `http://host.docker.internal:11434/v1` | Includes the `/v1` suffix. Deliberately **not** derived from the app's settings — Honcho always needs `/v1` and the app has no embedding URL. Targets a host-run Ollama; `extra_hosts` maps `host.docker.internal` so it resolves on Linux too (built-in on Docker Desktop). Use `http://ollama:11434/v1` for an in-stack `ollama` service. |
| `HONCHO_EMBEDDING_MODEL` | *inherited from* `EMBEDDING_MODEL_NAME` (else `nomic-embed-text`) | Override only when Honcho must embed with a different model than the app. |
| `HONCHO_EMBEDDING_VECTOR_DIMENSIONS` | *inherited from* `EMBEDDING_VECTOR_DIMENSIONS` (else `768`) | Must match the model's output width — see the pitfall below. |
| `HONCHO_EMBEDDING_TRANSPORT` | `openai` | OpenAI-compatible transport. |

Without a reachable endpoint, Honcho cannot embed and `/health`'s `memory_backend` row reports down.

Switching `MEMORY_BACKEND` to `honcho` neither deletes nor migrates what is already stored: the
existing memory rows stay in Postgres' `mem_memory_entry` table untouched and simply stop being
read. Switch back to `pgvector` and they are visible again. Do not drop them to "clean up" — they
are the only copy of those memories.

**Embedding-dimension pitfall:** the resolved width (`HONCHO_EMBEDDING_VECTOR_DIMENSIONS`, else
`EMBEDDING_VECTOR_DIMENSIONS`) decides the width of Honcho's own pgvector columns. `alembic
upgrade head` alone would leave them at Honcho's baked-in default (`vector(1536)`), so the
`honcho-migrate` service runs Honcho's own
`scripts/configure_embeddings.py --yes` immediately afterwards — that step ALTERs the columns to
this value, and is a no-op when they already match. Set the variable correctly *before* the first
`--profile honcho` start against a fresh `honcho_postgres_data` volume: that is the supported,
data-preserving path. A later change is re-applied by the next `honcho-migrate` run as well, but
pgvector cannot cast between widths, so already-stored memory vectors at the old width cannot
survive a resize. See the `honcho`/`honcho-migrate` service comments in `docker-compose.yml`.

### Honcho engine modules (deriver, peer card, summary, dream, dialectic)

Honcho does its reasoning **server-side**: the Python SDK exposes no provider/model/API-key/base-URL
parameter at all, so which model these modules use is entirely the `honcho` container's business.
`docker-compose.yml` pins all five active modules to this project's `opencode_go` provider
(`mimo-v2.5` on `https://opencode.ai/zen/go/v1`, reusing `LLM_API_KEY`) and turns each on explicitly —
`DERIVER_ENABLED`, `PEER_CARD_ENABLED`, `SUMMARY_ENABLED`, `DREAM_ENABLED` (all default to `true`
upstream; pinned so they are visible and flippable). None of this runs unless the profile is started:

```bash
docker compose -f deploy/docker-compose.yml --project-directory . --profile honcho up -d
```

**Two things the pins alone do not buy you.**

**(a) The `x-opencode-session` header (#1051).** The Zen-Go endpoint rejects every server-side call
without it (`400 MissingSessionID`), so a pinned base URL is not enough — Dialectic answers HTTP 500
and every engine module dies in the background. Honcho's escape hatch is
`ModelConfig.provider_params["extra_headers"]`, which reaches the SDK as the `extra_headers` kwarg.
The variable names that requires contain a **dash**. An earlier note here attributed the shim to
Docker dropping dashed names — that is **false** for Docker 29.8.1 (#1187, from the #1153 spike):
`docker run -e`, `docker run --env-file`, Compose `environment:` and Compose `env_file:` all
preserve a name with a hyphen (verified by counting what arrives in the container). The nine
per-module variables are still *not* set literally — not because Docker would drop them, but to keep
a single source of truth for the session value and to stay portable to older Docker versions and
other runtimes. The `LLM_OPENCODE_SESSION` value is passed instead, and the `honcho` /
`honcho-deriver` entrypoints materialise all nine names at container start (Python's `os.environ`
accepts them; `sh`'s `export` does not). Set it in `.env` — required for `LLM_PROVIDER=opencode_go`
too, and enforced by the `llm-preflight` service (#1050).

**(b) A deriver process (#1052).** Those pins describe what the deriver, the summary job and the dream
job *should* use, but Honcho runs them in a **separate process** (`python -m src.deriver`; upstream's
`DeriverSettings.SCHEDULER` defaults to `deriver`, not `api`). The image's own entrypoint starts only
the API server, so the API alone never drains the queue: work units stay `processed = false` forever
and no `document_sources` are written — the derived memory layers never materialise while the pins
look configured. The `honcho-deriver` service runs it, sharing the API service's entire environment
from one YAML anchor (`x-honcho-env`) so the two halves cannot drift apart. Verify with:

```bash
docker compose -f deploy/docker-compose.yml --project-directory . --profile honcho logs honcho-deriver \
  | grep -E 'Running main loop|ReconcilerScheduler started'
```

**Failure mode when a module's model is left unpinned:** Honcho's built-in default for these modules
is `transport=openai, model=gpt-5.4-mini`, but the only key in the container is the `opencode_go` one
— not a real OpenAI key. An unpinned module therefore tries to authenticate against a model/endpoint
it cannot reach and fails in the background; memory **reads** keep working, so nothing surfaces in
ReqogniLoom's UI — the summary/dream job simply never lands. Pin `SUMMARY_MODEL_CONFIG__*`,
`DREAM_DEDUCTION_MODEL_CONFIG__*` and `DREAM_INDUCTION_MODEL_CONFIG__*` alongside the
deriver/dialectic block (see the `honcho` service comments; RFC #1002 finding F6).

**Pinned image (#1153, #1315).** Everything above only holds for the *verified* image. All three
services that run the Honcho image (`honcho`, `honcho-deriver`, `honcho-migrate`) are pinned to a
**stable release tag plus digest**:
`ghcr.io/plastic-labs/honcho:v3.3.0@sha256:5bb8cf7a60845e08f83fed66f01907afa0969dd1d02e414ed576102f3b12dfe8`.
The tag names the release that is running, the digest makes the bytes immutable, so neither a moved
`:latest` nor an untagged digest can silently change the image. For the failure mode, the recreate
command and the upgrade procedure, see `## Troubleshooting: Stale Honcho image (#1153)` below.

### Derivation visibility (`derivation_status`) and the Zen-Go quota dependency (#1155)

Everything above can fail **silently**: the API stays up, memory reads keep working, and yet the
Deriver never produces anything — the beta.18 symptom, where every document stayed `level="explicit"`
(0 derived artefacts) while the UI still showed "healthy". Since AP-B5.1 the Deriver's state is
reported machine-readably, independent of the read's own `degraded` flag. Two surfaces carry the
field, and they answer different questions:

- **per scope** — `memory.digest` (MCP) and `GET /api/v1/workspaces/<id>/memory/digest/` (REST, plus
  the artifact variant): `derivation_status` + `derived_count` describe *this* scope's deriver.
- **scope-less** — the memory response envelope (`memory.list` / `memory.query` / `memory.forget`
  over MCP, the REST memory endpoints, and the admin `memory` health row): only the *capability*
  answer, because that surface has no scope to probe.

| `derivation_status` | Meaning |
|---|---|
| `ok` | *Per scope:* this scope **has produced** derived output at some point (non-empty peer representation/card, or a conclusion at level `deductive`/`inductive`/`contradiction`). `derived_count` carries the exact count when the probe could bound it, else `null`. **`ok` does not mean "the deriver is currently healthy"** — read the quota limit below. |
| `none` | *Per scope:* probed cleanly — nothing derived (yet). Writes exist, but all are `explicit`. **Not** an outage. |
| `failed` | *Per scope:* demonstrable failure — Honcho's `queue_status` accounting shows units vanished without completing (`total > completed + in_progress + pending`), the #1052 class. This **outranks `ok`**: a Deriver that dies after having produced output reads `failed`, while the digest text still carries that output. |
| `unknown` | *Per scope:* engine unreachable (or scope rejected) — the state is not determinable, never collapsed into `none`. |
| `unsupported` | The active backend has no deriver at all (pgvector) — on both surfaces. On the scope-less envelope `honcho` answers `unknown` ("can derive, not probed here"); its per-scope truth appears only on a digest. |

**Quota limit of this signal (read this before trusting `ok`).** The dominant #1155 root cause is the
Zen-Go endpoint's rate limit (HTTP 429): the Deriver dies *server-side* and Honcho counts the affected
work units as processed. The SDK surface (verified against `honcho-ai==2.5.1`) exposes **no per-unit
error flag** and no last-error/last-run detail, so such a loss leaves **no accounting gap** and is
client-undetectable: a scope that had already derived something keeps reading `ok`, a scope without
any output reads `none` — neither reads `failed`. `failed` fires only on the provable gap. Therefore:

- digests persistently reporting `none` despite growing explicit writes → check the quota and the
  `honcho-deriver` logs (section (b) above);
- digests reporting `ok` while the derived artefact stops growing → same checks; `ok` is a
  *historical* statement about the scope, not a liveness probe of the deriver.

Both cases are the documented blind spot of a client-side view, not a backend bug.

### Upstream boundary: the Honcho dialectic header is vendor-internal (#1153, #1247)

`memory.ask` on `MEMORY_BACKEND=honcho` is answered by Honcho's **server-side** dialectic engine,
and the `x-opencode-session` header that engine must attach to its Zen-Go calls is resolved
**inside the pinned `honcho` image** — code outside this repository. In-repo we can prove the
session value is present, reaches the containers, is attached by the **OpenCode Go provider on the
wire** (#1186), and that the nine Honcho module names are set in the engine process. We **cannot**
observe the Honcho engine's outbound provider request from pytest; the in-repo live spike is
`integration`/skip.

If `memory.ask` (or the dialectic endpoint) returns HTTP 500 / `400 MissingSessionID` while the
deploy gates are green, this is the documented escalation:

1. Run the pinned-image config-resolution spike (the command in
   `backend/memory/tests/test_honcho_deploy_contract.py::test_pinned_image_resolves_opencode_session_sdk_param`).
   It proves the nine names become `extra_headers`.
2. If step 1 fails, the shim/env wiring is wrong on this image — pin/rebuild it.
3. If step 1 passes but `memory.ask` still fails, the remaining gap is **inside the vendor image**
   (its HTTP client not attaching `extra_headers`). Escalate upstream — it is not fixable in-repo.
   `memory.ask` keeps returning a **loud** `degraded: true` with a non-empty `detail`, never a
   silent empty answer.

The deploy-runbook escalation and the PID 1 proof are in
[`docs/DEPLOY_RUNBOOK.md`](../docs/DEPLOY_RUNBOOK.md) §3.1.

**#1153 must be reopened:** it was closed as fixed, but #1247 shows `memory.ask` is still degraded
and the header is unobservable at the Honcho wire. Related open drift: `backend/requirements.txt`
pins `honcho-ai==2.5.1` while `backend/requirements.lock` pins `2.3.0`; confirm which the running
backend imports before diagnosing `memory.ask`.


## Memory backend capability matrix (#1251)

`MEMORY_BACKEND` picks the AI-memory store; the three implementations answer
different questions. This matrix is the single place that names what each backend
can and cannot do, so an `ask`/`digest` that "does nothing" can be read as intended
degradation rather than a bug:

| Backend (`MEMORY_BACKEND`) | Per-scope `derivation_status` | `memory.ask` | `memory.digest` | External dependency |
|---|---|---|---|---|
| `pgvector` (**default**) | `unsupported` — no deriver at all | **`ask_available = false`**: a defined degradation (`degraded: true`, empty `answer`), never an error | facts-based digest; `derivation_status: "unsupported"`, `derived_count: null` | none beyond Postgres/pgvector |
| `honcho` (optional `honcho` profile) | `ok` / `none` / `failed` / `unknown` — the Deriver probe | **`ask_available = true`**: answered by the server-side dialectic engine (`peer.chat`, scoped to the session); `degraded: false` on success, `degraded: true` on engine/transport failure | deriver-backed digest with `derivation_status` + `derived_count` | Honcho server (`HONCHO_BASE_URL`) **plus** an external LLM (Zen-Go) and an embedding endpoint |
| `qdrant` (optional `qdrant` profile) | `unsupported` — no deriver | **`ask_available = false`**: **always** `degraded: true` with `detail: "no dialectic engine"` | facts-based digest; `derivation_status: "unsupported"` | Qdrant service (`QDRANT_BASE_URL`); **no auto-fallback** to pgvector (ADR-020 §4) |

The scope-less capability that rides the memory response envelope
(`memory.list`/`memory.query`/`memory.forget`, the admin health row) has no scope
to probe, so it reports only the capability: `unsupported` for `pgvector` and
`qdrant`, `unknown` for `honcho` ("can derive, not probed here").

### LLM capability IDs are not MCP tool names (#1251)

The four names in `LLM_CAPABILITIES` (`.env.example`) are **LLM capability IDs**,
gating the AI-provider router — they are **not** MCP tool names, even where they
look like one. This distinction is the source of the "`check_consistency` tool is
missing" confusion:

| LLM capability ID (`LLM_CAPABILITIES`) | Dispatch | MCP tool(s) that drive it |
|---|---|---|
| `validate_artifact` | sync | `requirement.validate` |
| `decompose_requirement` | async (Celery) | `requirement.decompose` |
| `check_consistency` | async (Celery) | `requirement.check_consistency` (+ `requirement.check_consistency_status`) |
| `derive_requirements` | async (Celery) | *(legacy)* — no active tool: today's derivation tools (`needs.derive_requirements`, `ai_derivation.derive_requirements_from_need`) go through the `ai_derivation` service, which routes **outside** `CapabilityRouter` and is therefore **not** gated by `LLM_CAPABILITIES` |

A capability that is gated off answers the distinct error code
`LLM_CAPABILITY_DISABLED` with "Set `LLM_CAPABILITIES` to include it" — it is
**not** an unknown tool (`UNKNOWN_TOOL`). The canonical MCP tool list is
`docs/agent-templates/tool-manifest.json`; the full reference is
[`docs/api/MCP-SURFACE.md`](../docs/api/MCP-SURFACE.md) §4 and §8.

## Optional: Qdrant vector backend (ADR-020)

`pgvector` remains the **default** memory backend; Qdrant is an opt-in second operating mode, only
available on the full stack (the minimal stack stays pgvector-only). Add `--profile qdrant`:

> **Pinned.** The `qdrant` service runs `qdrant/qdrant:v1.19.2@sha256:b7b0444c…` (tag + manifest-list
> digest, [rule above](#base-images-are-pinned-tag--digest-1391)) — the index layout and the payload
> format are part of what the backend talks to, so a moving `v1.19.2` tag is not acceptable here.

```bash
docker compose -f deploy/docker-compose.yml --project-directory . --profile qdrant up -d
# or the wrapper: make qdrant
```

Then set these in `.env` (not committed) and **recreate** `backend`/`celery` (`up -d`, not
`restart` — `env_file` is read at container creation):

```bash
MEMORY_BACKEND=qdrant
QDRANT_BASE_URL=http://qdrant:6333
```

`QDRANT_BASE_URL` reaches the app the same way `HONCHO_BASE_URL` does: through `env_file: .env`.
The compose file injects nothing into `backend`/`celery` itself.

The service is **internal-only** — no host port is published; see *Operating requirement (QR-S23)*
below for the exact endpoints and the debug-bind rule.

**Multi-tenant security — set an API key.** With `QDRANT_API_KEY` empty, Qdrant is an
**unauthenticated** store. That is acceptable only when a single app/tenant talks to it on an
isolated network. As soon as **more than one tenant shares a Qdrant instance** — the normal case
here, where tenant isolation is a first-class guarantee (ADR-03) — an API key is **required**: set
`QDRANT_API_KEY` (and the matching `QDRANT__SERVICE__API_KEY` on the `qdrant` service) so the store
can tell callers apart.

| Variable | Default | Notes |
|----------|---------|-------|
| `QDRANT_BASE_URL` | *(empty)* — set `http://qdrant:6333` | Internal HTTP/REST endpoint. |
| `QDRANT_API_KEY` | *(empty)* | Only if Qdrant's API-key check is enabled; empty = no auth — acceptable **only** on a non-production deployment. Required in **any** production deployment with the artifact selector set (`memory.W003` is selector ∧ production, independent of the tenant count — see the security note above). The gate does **not** cover a memory-only Qdrant (`MEMORY_BACKEND=qdrant` with the artifact selector off), so set the key there too. Must match `QDRANT__SERVICE__API_KEY` on the `qdrant` service. |
| `QDRANT_TIMEOUT` | `5` | Seconds (matches `DEFAULT_QDRANT_TIMEOUT` in `persistence/qdrant_config.py`). |
| `QDRANT_DISTANCE` | `cosine` | Same metric as pgvector's `vector_cosine_ops`; `dot`/`euclid` are deliberate exceptions. |
| `QDRANT_COLLECTION_PREFIX` | `reqlo` | One collection per workspace/scope, in two separate families. **AI-memory** (`QdrantMemoryBackend`): `<prefix>_<tenant>_<workspace>`, `<prefix>_<tenant>_user`, and the legacy unversioned `<prefix>_<tenant>_<workspace>_artifacts`. **Artifact port** (`ARTIFACT_VECTOR_BACKEND=qdrant`): `<prefix>_<tenant>_<workspace>_artifacts_v2`, read through the stable `<prefix>_<tenant>_<workspace>_artifacts_live` alias. |
| `QDRANT_HNSW_M` / `QDRANT_HNSW_EF_CONSTRUCT` | `16` / `64` | Mirror the pgvector HNSW index already shipped (`memory/models.py`). |
| `QDRANT_PREFER_GRPC` | `false` | `true` uses the gRPC port `6334`. |

**Embedding-dimension pitfall — there is no `QDRANT_VECTOR_DIMENSIONS`.** The width is deliberately
**not** a separate setting: Qdrant collections are created at `EMBEDDING_VECTOR_DIMENSIONS` (the
single source of truth for every embedding column — see *Optional: switch the embedding provider
(and resize the schema)* below). A second, independent dimension variable could silently disagree
with the model's actual output width, so a drift must fail loud instead. Change the provider and its
width **together**, then rebuild the Qdrant collections at the new width (the index is regenerable —
see the backup note).

**No automatic fallback.** If `MEMORY_BACKEND=qdrant` is set and Qdrant is unreachable, memory is
reported **degraded** — it does **not** silently fall back to pgvector (ADR-020 §4). A silent
fallback would return stale or empty results and hide the outage. Switch back with
`MEMORY_BACKEND=pgvector` in `.env` and recreate `backend`/`celery`; the pgvector data was never
touched.

### Artifact vector search (`ARTIFACT_VECTOR_BACKEND`, ADR-020 V2)

`MEMORY_BACKEND` governs only the **AI memory** store. **Artifact** ANN search — semantic search over
Requirements/TraceLinks/ICDs and the `find_similar_*` helpers — is a **separate** port that switches
to Qdrant only through an explicit second selector:

| Variable | Default | Notes |
|----------|---------|-------|
| `ARTIFACT_VECTOR_BACKEND` | `pgvector` | Artifact vector store: `pgvector` \| `qdrant`. Independent of `MEMORY_BACKEND` — the artifact store is never switched as a side effect of another knob (ADR-020 §4). |
| `QDRANT_QUANTIZATION` | `int8` | **Artifact v2 collections only**: `int8` \| `none` (also `off`, `false`, `0`, `no`). Creation-time only — a change needs `index_artifact_vectors --recreate`. See [quantization and RAM](#quantization-and-ram). |

Leave it at `pgvector` (the default) unless the artifact index on the **target system** has
actually been built. The Qdrant artifact adapter, the backfill command and the index hooks exist,
but a deployment's per-workspace `<prefix>_<tenant>_<workspace>_artifacts_v2` collections start
empty: semantic search there returns no hits until they are populated.

**Rollout rule (QR-T16).** Enable `ARTIFACT_VECTOR_BACKEND=qdrant` on a target system only after
`python manage.py index_artifact_vectors` has run **there** and reported `failed:0`, and the
artifact index hooks are active (i.e. the deployment carrying them is already live). Until then
the default stays `pgvector`: a Qdrant store switched on before its backfill answers semantic
search from an empty collection, which looks like "no results" rather than like an error.

Selecting `qdrant` requires **all** of: the explicit `ARTIFACT_VECTOR_BACKEND=qdrant`, an
importable `qdrant_client` package, and a configured `QDRANT_BASE_URL`. If any condition is
missing the artifact port stays on pgvector — it never switches implicitly. The selection is
deliberately **independent of `MEMORY_BACKEND`**: that knob governs the AI-memory store only, so
an artifact Qdrant store can serve in front of a Honcho or pgvector memory backend.

**The key requirement applies to the artifact store too.** This port puts **tenant artifact
vectors** into Qdrant, so `QDRANT_API_KEY` (plus the matching `QDRANT__SERVICE__API_KEY` on the
`qdrant` service) is **required in any production deployment once this selector is set**. The
`memory.W003` gate is the conjunction `ARTIFACT_VECTOR_BACKEND=qdrant` ∧ production (`DJANGO_ENV`
is not a declared non-production value) ∧ no key resolves — it is **not** conditioned on the tenant
count, so a single-tenant production deployment is covered too. The gate holds even when
`MEMORY_BACKEND` is *not* `qdrant` (T-A2-1 decoupled the two selectors). Without it, a production
deployment **warns** — `memory.W003` from `manage.py check` (and therefore from `migrate`, which
runs the checks) — and `/health/?verbose=1` publishes
`advisory.qdrant_api_key=missing` plus `advisory.qdrant_api_key_missing=true`. It is a warning, not
a failure: neither `check` nor `migrate` aborts, and the service still serves. The two **advisory
keys** are `?verbose=1`-only so an anonymous caller is not handed the store's posture; the **warning
text** is unconditional, because that is what a plain `/health/` poll must carry. `/health*` is
therefore not internet-reachable — it is a probe for the compose network, and this split is
deliberate.

**Operating requirement (QR-S23).** Production therefore requires `QDRANT_API_KEY` (with the same
value as `QDRANT__SERVICE__API_KEY`, or the client gets 401) and, when Honcho is the memory backend,
`HONCHO_API_KEY`. **Do not conflate the two services' reachability** — they differ:

* **Qdrant publishes no host port.** It is reachable only on the compose network as
  `qdrant:6333` (REST) / `qdrant:6334` (gRPC). A local debugging bind must be `127.0.0.1`-only and
  must ship together with an API key.
* **Honcho *is* published, loopback-only, and ships unauthenticated.** `127.0.0.1:8010:8000` is the
  shipped default (`deploy/docker-compose.yml:1336-1337`) and `AUTH_USE_AUTH: "false"` ships with it
  (`deploy/docker-compose.yml:86`). The loopback bind keeps the port off the network, not off the
  host: anything that can reach `127.0.0.1:8010` talks to an unauthenticated memory service. Set
  `AUTH_USE_AUTH=true` plus a real key before using it beyond a single-developer local stack, and
  set `HONCHO_API_KEY` to a token that the auth-enabled Honcho server then accepts — the compose
  file wires no server-side counterpart variable, so the app's client bearer token must match
  whatever the server is configured with.

**What an unauthenticated Qdrant means.** With `QDRANT__SERVICE__API_KEY` empty the compose network
is the only boundary: every container on it can enumerate every collection
(`GET /collections`), read and delete every tenant's vectors
(`POST /collections/{collection}/points/delete`) and create, download and delete snapshots
(`/collections/{collection}/snapshots`, `/snapshots`) — i.e. read the tenant artifact corpus out of
the store and destroy it. Checked against the pinned image: with the key set, those same requests
answer **401**; keyless, they answer **200**.

**Similarity endpoints (workspace-scoped, T-A2-8).** `find_similar_trace_links` and
`find_similar_icds` address their source's workspace: with a scope they use the workspace alias,
without one they fall back to pgvector with `degraded_reason="no_workspace_scope"` instead of
failing. Neither ever scans another workspace's collection. See
[what is degraded](#what-is-degraded-while-the-artifact-backend-is-qdrant) below.

**Backup / restore of the Qdrant index.** The Postgres sidecar (ADR-012, `postgres_backup_data`)
does **not** cover `qdrant_data` — the vector index is a separate named volume and is **not** in the
`pg_dump`. That is acceptable because it is **regenerable**: Postgres (`mem_memory_entry` /
`pl_requirement` / `pl_tracelink` / `icd_icd`) stays the source of truth and Qdrant holds only
vectors plus a payload. The **point id** differs per family: it is `MemoryEntry.id` in the memory
collections, but the **entity UUID** (`Requirement.id` / `TraceLink.id` / `Icd.id`) in the artifact
`..._artifacts_v2` points, whose payload also carries `tenant_id`, `workspace_id` and `entity_type`.
After a restore or a rebuild, reconcile and reindex:

```bash
# READ-ONLY drift report: canonical Postgres rows vs. the external Qdrant points
docker compose -f deploy/docker-compose.yml --project-directory . \
  exec backend python manage.py memory_reconcile

# Re-generate the vectors from the canonical rows (reindex/backfill path)
docker compose -f deploy/docker-compose.yml --project-directory . \
  exec backend python manage.py backfill_embeddings
```

The ADR-012 gates (`deploy/verify-restore.sh`, `deploy/verify-backup-command.sh`) prove the
**Postgres** side and do **not** apply to the Qdrant volume; a genuine volume snapshot would be a
separate, deliberate operation (stop `qdrant`, then copy `qdrant_data` with the usual volume
tooling).

#### Snapshots of the artifact collections

A snapshot is the cheap way back: a rebuild re-walks every canonical row of the tenant and re-upserts
its point (a row whose stored pgvector column already matches the active embedding model costs no
embedding call — the indexer reuses it), while a restore is a single copy. Qdrant publishes no host
port and its image bundles no HTTP client, so every call goes through a container — the `backend`
image ships `curl` and already has `QDRANT_BASE_URL` / `QDRANT_API_KEY` from `env_file: .env`.

*Discover the concrete collection names.* `<prefix>` is `QDRANT_COLLECTION_PREFIX` (default `reqlo`)
and the tenant/workspace segments are the raw UUIDs, so list them instead of guessing:

```bash
docker compose -f deploy/docker-compose.yml --project-directory . exec backend sh -c \
  'curl -fsS -H "api-key: $QDRANT_API_KEY" "$QDRANT_BASE_URL/collections"'
# {"result":{"collections":[{"name":"reqlo_<tenant>_<workspace>_artifacts_v2"}]},"status":"ok"}

docker compose -f deploy/docker-compose.yml --project-directory . exec backend sh -c \
  'curl -fsS -H "api-key: $QDRANT_API_KEY" "$QDRANT_BASE_URL/aliases"'
# {"result":{"aliases":[{"alias_name":"reqlo_<tenant>_<workspace>_artifacts_live",
#                        "collection_name":"reqlo_<tenant>_<workspace>_artifacts_v2"}]},"status":"ok"}
```

A key that exists **only** in `SystemMemorySettings.qdrant_api_key` is not exported into the
container env, so `$QDRANT_API_KEY` is empty there. Never type it into the command line: an argument
is kept in shell history and stays visible in `ps` output to every local user (CWE-214). Read it
without echo and forward the *variable* instead — `exec -e QDRANT_API_KEY` copies it from this shell
into the container, so the value never becomes argv, and only the container's `sh` expands
`-H "api-key: $QDRANT_API_KEY"`:

```bash
# Prompts without echo; `-s` keeps the key out of the terminal and out of history.
read -rs QDRANT_API_KEY && export QDRANT_API_KEY
```

The same `-e QDRANT_API_KEY` applies to every `curl` call below that reads the variable.

```bash
# One snapshot per collection. Address the CONCRETE collection: an alias resolves, but the file
# then lands under the resolved name while an empty <alias> directory is left behind.
docker compose -f deploy/docker-compose.yml --project-directory . \
  exec -e QDRANT_API_KEY backend sh -c \
  'curl -fsS -X POST -H "api-key: $QDRANT_API_KEY" \
   "$QDRANT_BASE_URL/collections/<prefix>_<tenant>_<workspace>_artifacts_v2/snapshots?wait=true"'

# List / download / delete (name from the POST response, "result.name")
docker compose -f deploy/docker-compose.yml --project-directory . \
  exec -e QDRANT_API_KEY backend sh -c \
  'curl -fsS -H "api-key: $QDRANT_API_KEY" \
   "$QDRANT_BASE_URL/collections/<collection>/snapshots"'
# GET .../collections/<collection>/snapshots/<name>  -> the .snapshot file (200)
# DELETE .../collections/<collection>/snapshots/<name>
```

*Where the files land.* `/qdrant/snapshots/<collection>/<name>.snapshot` plus a
`.snapshot.checksum` sidecar inside the **qdrant container**. Only `/qdrant/storage` is the
`qdrant_data` volume, so `/qdrant/snapshots` lives in the container's writable layer and is **lost
on `docker compose up -d --force-recreate qdrant`**, a re-pull or a volume prune. Copy it out (or
stream it with the `GET .../snapshots/<name>` route) before you touch the container:

```bash
# NEVER into the checkout: a snapshot is a full copy of the tenant index (vectors
# plus the tenant_id / workspace_id / entity_id payload), i.e. tenant data.
# Treat it like a database dump: keep it outside the repository, restrict access.
# 700/600 on purpose: /var/tmp is world-writable and survives a reboot, so a
# default-mode copy (directory 1777, file 0644) would be readable by every local
# user. `install -d -m 700` also tightens a directory an earlier copy created.
install -d -m 700 /var/tmp/reqlo-snapshots
docker compose -f deploy/docker-compose.yml --project-directory . \
  cp qdrant:/qdrant/snapshots/<collection>/<name>.snapshot /var/tmp/reqlo-snapshots/
chmod 600 /var/tmp/reqlo-snapshots/<name>.snapshot
```

The host copy is a staging point only: move it encrypted to off-box storage, and delete it from
`/var/tmp` as soon as the restore (or the verification that it restores) is done.

*Retention.* Qdrant never prunes snapshots: each one is a full copy of the collection's storage
(segments plus payload), so they cost on the order of the collection itself and accumulate until
deleted — nobody deletes them for you. Delete the ones you have copied off-box, and keep at most one
on-container copy. A full-storage snapshot (`POST /snapshots`, file
`/qdrant/snapshots/full-snapshot-<timestamp>.snapshot`) also exists, but it contains **all tenants'
vectors in one file** — it is a whole-instance backup, **not** a per-tenant one, so it cannot be
handed to a single tenant's operator or restored into a shared instance without leaking one
tenant's data into another. The pinned `v1.19.2` build also exposes **no HTTP restore route for it**
(`/snapshots/recover` answers 404) — the restorable unit is the **per-collection** snapshot.

*Restore* (one collection, verified on the pinned image; `priority=snapshot` replaces the local
points with the snapshot's, so it is also the way to roll a collection back in place):

```bash
# 1. In place, from a file already inside the qdrant container (file:// URI).
#    -f makes curl exit non-zero on 401/404, so a rejected restore cannot print
#    an error body and still look successful.
docker compose -f deploy/docker-compose.yml --project-directory . exec backend sh -c \
  'curl -fsS -X PUT -H "api-key: $QDRANT_API_KEY" -H "Content-Type: application/json" \
   "$QDRANT_BASE_URL/collections/<collection>/snapshots/recover" \
   -d "{\"location\": \"file:///qdrant/snapshots/<collection>/<name>.snapshot\", \"priority\": \"snapshot\"}"'

# 2. From a file on the host: upload it (multipart, field name "snapshot").
#    -T keeps stdin attached so curl reads the `-F "snapshot=@-"` part; without
#    it Compose allocates a TTY and the upload hangs.
docker compose -f deploy/docker-compose.yml --project-directory . exec -T backend sh -c \
  'curl -fsS -X POST -H "api-key: $QDRANT_API_KEY" \
   "$QDRANT_BASE_URL/collections/<collection>/snapshots/upload?priority=snapshot" \
   -F "snapshot=@-"' < /var/tmp/reqlo-snapshots/<name>.snapshot
```

*Read window.* While a `recover` with `priority=snapshot` runs, the collection answers partially or
empty — and the `..._artifacts_live` alias still points at it, so readers see that immediately. Do
not run a restore under live search traffic: set `ARTIFACT_VECTOR_BACKEND=pgvector` and recreate
`backend`/`celery` (or stop traffic) first, restore, then switch back and re-verify with `/health/`.

*Name it right.* `snapshots/upload` **creates** a collection that does not exist yet, so a typo in
`<collection>` silently produces a new, empty, unread collection instead of an error — confirm the
target with `GET /aliases` afterwards. Keep the `_artifacts_v2` suffix on any restored collection:
the health probe matches that suffix, and a collection restored under any other name reads as
`collections=0` in `advisory.qdrant_artifact_points`.

#### Rebuilding the artifact index (`index_artifact_vectors`)

`python manage.py index_artifact_vectors` is the only supported way to build (or rebuild) the
artifact vectors: it re-embeds from the canonical Postgres rows and upserts into the **concrete**
`..._artifacts_v2` collection (`backend/application/artifact_indexer.py:222-225` builds the name,
`:294-301` upserts it) — only *readers* go through the `..._artifacts_live` alias
(`backend/application/vector_port.py:723-737`). It runs against the configured Qdrant **regardless
of `ARTIFACT_VECTOR_BACKEND`** (the selector decides the read path and the live index hooks, not
this explicit backfill command), so a backfill or rebuild never needs the selector flipped — and
therefore never exposes a half-built index to search.

```bash
# 1. Cost report. Writes nothing — not even the collection — and reports embed_calls per tenant.
docker compose -f deploy/docker-compose.yml --project-directory . exec backend \
  python manage.py index_artifact_vectors --tenant <tenant-uuid> --dry-run

# 2. Real run. --workspace scopes it to one workspace of that tenant; the rate limit keeps the
#    embedding provider inside its quota (0 disables throttling).
docker compose -f deploy/docker-compose.yml --project-directory . exec backend \
  python manage.py index_artifact_vectors --tenant <tenant-uuid> \
  --max-embeds-per-minute 120

# 3. Verify: the per-tenant report must show "failed": 0 for every type, and the command must
#    exit 0 (a run with failures still prints its report and then exits non-zero).
```

The report is JSON Lines, one object per tenant:
`{"tenant": ..., "by_type": {"Requirement": {"upserted": N, "skipped": M, "failed": 0}, ...},
"failures": {"<reason>": N}, "embed_calls": K, "duration_s": S}`. `failed: 0` in every `by_type`
entry is the gate from the rollout rule above; the per-tenant figure is the **sum of that report's
`upserted` values**. `/health/`'s `advisory.qdrant_artifact_points` is *not* per-tenant: it
aggregates **every** `*_artifacts_v2` collection of the whole Qdrant instance — all tenants and
workspaces — so read it as "is the corpus non-empty", not as this run's result.

`--recreate` is **destructive and never implicit**:

* it requires `--tenant` (a tenant is never guessed), refuses to run together with `--dry-run`,
  and refuses a `--workspace` that is not in that tenant (`CommandError`, exit non-zero) — the
  blast radius can never span tenants and an empty rebuild can never be mistaken for a success;
* it **deletes** each in-scope `..._artifacts_v2` collection and its `..._artifacts_live` alias,
  then re-provisions an empty collection, and only the same run rebuilds the vectors. An aborted
  `--recreate` therefore leaves an **empty** collection behind: re-run without `--recreate`, or
  restore a snapshot.

Use it for an index that is known-bad, a quantization change, or a payload change that cannot be
expressed through the collection version. Bumping `ARTIFACT_COLLECTION_VERSION` already changes the
collection name (`..._artifacts_v3`) and needs **no** `--recreate`; only a change that keeps the same
versioned name (new payload field, new vector config) does. Budget the dry run's `embed_calls` and
take a snapshot first.

#### Rolling back a bad v2 build

Readers never address `..._artifacts_v2` directly; the port reads the stable `..._artifacts_live`
alias. That splits the rollback into two cases:

* **Code revert is enough** when the defect is in the query/projection layer: set
  `ARTIFACT_VECTOR_BACKEND=pgvector` and recreate `backend`/`celery`. Nothing *reads* the artifact
  family while the selector says pgvector — the query port and the outbox index hooks are both
  behind it — so the collections keep their vectors and no data is lost. Writes still happen if
  someone runs `index_artifact_vectors` (that command always talks to Qdrant, by design); don't run
  one during a rollback. Artifact writes made while the selector is off are not indexed, so re-run
  the backfill before switching back on.
* **Repoint or restore the data** when the *build* is bad. Either restore a snapshot over the live
  collection (`PUT .../snapshots/recover` with `priority: snapshot`, above — selector off or traffic
  stopped, per the read window above — no alias move needed and the durable option), or restore it
  under another name and move the alias in **one** call, which deletes and creates in the same
  request (no window in which readers see no alias):

```bash
# ONE request, so readers never see an alias-less window. -f makes curl exit non-zero on 4xx,
# so a rejected update_collection_aliases cannot print an error body and still look successful.
docker compose -f deploy/docker-compose.yml --project-directory . exec backend sh -c \
  'curl -fsS -X POST -H "api-key: $QDRANT_API_KEY" -H "Content-Type: application/json" \
   "$QDRANT_BASE_URL/collections/aliases" \
   -d "{\"actions\": [{\"delete_alias\": {\"alias_name\": \"<prefix>_<tenant>_<workspace>_artifacts_live\"}}, {\"create_alias\": {\"collection_name\": \"<restored-collection>\", \"alias_name\": \"<prefix>_<tenant>_<workspace>_artifacts_live\"}}]}"'

# current target of every alias
docker compose -f deploy/docker-compose.yml --project-directory . exec backend sh -c \
  'curl -fsS -H "api-key: $QDRANT_API_KEY" "$QDRANT_BASE_URL/aliases"'
```

**The alias move is not durable across a backfill.** `ensure_artifact_collection`
(`backend/application/artifact_vector_store.py:160-190,299`) re-points `..._artifacts_live` at the
concrete `..._artifacts_v2` collection on *every* run — including a plain `index_artifact_vectors`
without `--recreate` — so any later run silently undoes an alias move made during a rollback and
readers go back to the bad build. If the rollback must survive a backfill, use the in-place
`PUT .../snapshots/recover` instead. In both cases the restored collection must keep the
`_artifacts_v2` suffix, otherwise `/health/` no longer counts it (see *Name it right* above).

#### Quantization and RAM

The v2 collections are created with **int8 scalar quantization** (`quantile=0.99`,
`always_ram=true`): the float32 vectors stay on disk and only the int8 approximation is kept in RAM,
i.e. about **a quarter** of the vector RAM the raw corpus would need, at the price of approximate
(denormalized) scores.

| `QDRANT_QUANTIZATION` | Effect |
|-----------------------|--------|
| `int8` (default) | int8 scalar quantization, `always_ram=true`. |
| `none` — also `off`, `false`, `0`, `no` | no quantization at all: **lossless** exact scores, about 4× the vector RAM for the same corpus. |
| anything else | falls back to `int8` with one warning (a typo is not fatal). |

Both modes are **creation-time only**: the setting is read when a collection is created, so changing
it on an existing collection does nothing until `index_artifact_vectors --recreate` rebuilds it.
The knob applies to the **artifact** collections only — the AI-memory collections are created
without quantization (`memory.qdrant_backend`).

#### What is degraded while the artifact backend is Qdrant

| Situation | Behaviour |
|-----------|-----------|
| Qdrant unreachable mid-request | `GET /api/v1/search/` answers **200** with `degraded: true`, `degraded_reason: "qdrant_unavailable"` and `vector_backend: "pgvector"`. The semantic leg is served from pgvector, so the entity types that have **no embedding column** contribute no semantic hits to that response (the cross-type query has no pgvector equivalent and degrades to an empty list). Documented limitation, never a 500. A cross-type-only failure reports `cross_type_query_failed` instead and keeps `vector_backend: "qdrant"`. |
| Similarity endpoints | Workspace-scoped (T-A2-8). Without a workspace scope they degrade to pgvector with `degraded_reason: "no_workspace_scope"`. |
| Hybrid BM25 | The dense leg plus a **server-side** `bm25` sparse leg, fused with RRF. The pinned `v1.19.2` computes the sparse vector itself (`qdrant/bm25`), so no `fastembed` and no extra embedding call on the client. If a collection lacks the sparse vector, the hybrid query fails (`Not existing vector name error: bm25`) and the request degrades to pgvector like any other outage — which is why `/health/` reports `advisory.qdrant_sparse_ready` (it is `false` for any `..._artifacts_v2` collection without `bm25`). |
| Empty or partially built index | Search returns "no results" with HTTP 200 (it looks healthy). Read `advisory.qdrant_artifact_points` (`collections=<n>,points=<n>`) — published only while the artifact backend actually is Qdrant — or run the `--dry-run` report above. |

**Verify a rollout on the running system.** `/health/?verbose=1` publishes
`advisory.vector_backend_active` (`qdrant` only when all three gates hold), the fallback reason when
it does not, plus `advisory.qdrant_artifact_points` and `advisory.qdrant_sparse_ready`. Enable
`ARTIFACT_VECTOR_BACKEND=qdrant` only when the backfill ran **on that system** with `failed: 0`, the
hooks are live, `vector_backend_active` says `qdrant`, `qdrant_artifact_points` is non-zero and
`qdrant_sparse_ready` is `true`.


## Troubleshooting: LLM calls fail with ConnectError (backend container DNS)

**Symptom.** Every AI feature fails while the API itself stays up. For example
`POST /api/v1/interviews/{id}/chat/` returns 400 `VALIDATION_ERROR` with:

```
LLM provider 'opencode_go' call failed (transient_exhausted): TransientError: Connection error.
```

The very same request works when you call the LLM endpoint from the host — only the backend
container cannot reach it.

**Cause.** The backend container resolves no external names at all. A container created with a
stale or empty resolver shows this in its own `/etc/resolv.conf`:

```
# NO EXTERNAL NAMESERVERS DEFINED
```

This is a hosting / container-lifecycle defect, not application code. Other containers on the same
host (for example `honcho`) resolve fine, which is what makes the fault container-specific.

**Detect.** Run these from the repository root:

```bash
docker compose -f deploy/docker-compose.yml --project-directory . exec backend cat /etc/resolv.conf
docker compose -f deploy/docker-compose.yml --project-directory . exec backend getent hosts opencode.ai
```

A healthy container lists at least one real `nameserver` (for example the Docker embedded resolver
at `127.0.0.11`) and `getent` prints one or more resolved addresses. The failure markers are the
`NO EXTERNAL NAMESERVERS DEFINED` comment above and/or an empty `getent` result.

Without Compose, the equivalent commands are:

```bash
docker exec <backend-container> cat /etc/resolv.conf
docker exec <backend-container> getent hosts opencode.ai
```

**Fix.** Recreate the backend container so it picks up the host's DNS configuration:

```bash
docker compose -f deploy/docker-compose.yml --project-directory . up -d --force-recreate backend
```

`docker compose restart backend` is **not** sufficient: a restart reuses the existing container's
resolver, and only recreation re-reads the Docker daemon's DNS configuration. Afterwards re-run the
detection commands above and confirm a real round trip (a working AI feature, or a successful
`getent hosts opencode.ai`).

**Second, independent failure on the same endpoint.** Once DNS is fixed, the Zen-Go endpoint can
still answer:

```
400 {"type":"error","error":{"type":"MissingSessionID","message":"Request is missing x-opencode-session …"}}
```

Set `LLM_OPENCODE_SESSION` (documented in `.env.example`) — it is required for
`LLM_PROVIDER=opencode_go`. Put it in `.env` and follow with `up -d`, not `restart`, because `.env`
is read at container creation.

**Start the Honcho profile alongside the standard start.** The optional memory backend is a Compose
profile and is otherwise `Exited (0)` / never started, which makes "backend down" indistinguishable
from "nothing remembered". Start the full stack *with* the profile:

```bash
docker compose -f deploy/docker-compose.yml --project-directory . --profile honcho up -d
```

`MEMORY_BACKEND=honcho` and `HONCHO_BASE_URL=http://honcho:8000` must be set, as the Honcho section
above describes.

**Verify memory health after the start.** Check the `memory_backend` row is healthy (as the Honcho
section notes, `/health` reports `memory_backend` down when the embedding endpoint is unreachable):

```bash
curl http://localhost:8001/health/
```

Optionally confirm the memory containers are actually up:

```bash
docker compose -f deploy/docker-compose.yml --project-directory . ps
```

`honcho` and `honcho-postgres` must be `running`/`healthy`.

See RFC #1002 §F12 (and issue #918).

## Troubleshooting: Stale Honcho image (#1153)

**Symptom.** The optional Honcho engine answers incorrectly while everything *looks* healthy.
Honcho's dialectic endpoint returns HTTP 500 — or the underlying provider call surfaces
`400 {"type":"error","error":{"type":"MissingSessionID", …}}` — and the background engine modules
(deriver, summary, dream) fail in the background. Memory **reads** keep working and
`GET /health/` looks green, so nothing surfaces in ReqogniLoom's UI and the summary/dream layers
simply never land.

**Cause.** A **stale/moved `:latest` image**, not a repo-code bug. When the Honcho services were
deployed by tag, `ghcr.io/plastic-labs/honcho:latest` was a *moving* tag: a host that pulled it at a
different time ran a different build than the one the stack was verified against. The compose wiring
already reaches the SDK parameters correctly — the `x-opencode-session` shim and the
`extra_headers` kwarg are all in place — but the running container came from a different build than
the verified one. The pin is now a **stable tag + digest** (#1315), so neither half can move again.

**Fix.** Recreate the two long-running engine services so they pick up the pinned image — run from
the repository root:

```bash
docker compose -f deploy/docker-compose.yml --project-directory . --profile honcho up -d --force-recreate honcho honcho-deriver
```

`docker compose restart <service>` is **not** sufficient: a restart reuses the existing container
and its already-pulled image, so a stale image is never replaced. Only a recreate
(`--force-recreate`, or a re-run `up -d` after the image reference changed) re-resolves and
re-creates the container. If the pin changed *across a release*, run `honcho-migrate` as well — a
version jump is a migration event (see **Upgrade** below).

**Tag + digest pin.** All three services that run the Honcho image — `honcho`, `honcho-deriver` and
`honcho-migrate` — are pinned to the verified immutable reference (an application of the general
rule in [Base images are pinned tag + digest](#base-images-are-pinned-tag--digest-1391): use the
manifest-list digest, not a platform digest):

```
ghcr.io/plastic-labs/honcho:v3.3.0@sha256:5bb8cf7a60845e08f83fed66f01907afa0969dd1d02e414ed576102f3b12dfe8
```

`honcho-migrate` is pinned as well on purpose: if migrations ran on a different build than the
server, the Alembic/embedding schema could drift from what the API and deriver expect.

**Which version runs?** Read the tag (and cross-check it against the image label):

```bash
docker buildx imagetools inspect ghcr.io/plastic-labs/honcho:v3.3.0 | head -n 5
docker inspect --format '{{ index .Config.Labels "org.opencontainers.image.version" }}' \
  "$(docker compose -f deploy/docker-compose.yml --project-directory . --profile honcho ps -q honcho)"
```

**Upgrade.** Pick a *released* tag (never `latest`/`staging`), re-resolve its manifest-list digest
and update both in all three places that pin them: the three `image:` lines in
`deploy/docker-compose.yml`, this README, and `_EXPECTED_TAG`/`_EXPECTED_DIGEST` in
`backend/memory/tests/test_honcho_deploy_contract.py`; then re-run the guard test above. Copy the
value from the manifest-list/index `Digest:` field — not `config.digest`. A Honcho version jump is a
**migration event**: `honcho-migrate` applies Honcho's own alembic migrations and
`configure_embeddings.py`, so smoke-test a memory read **and** write afterwards.

**Spike evidence.** The deploy contract was established with the #1153 spike, which imports
`src.config.settings` inside the *pinned* image and asserts
`sdk_params["extra_headers"]["x-opencode-session"]` is the configured value. The v3.3.0 pin was
re-checked against the real image: it still ships `scripts/configure_embeddings.py` (with `--yes`),
`alembic`, and an importable `src.config.settings` (Python 3.13). Re-run the spike command from the
guard test's docstring after every tag bump to re-prove the header resolution. The deploy contract is
regression-guarded, Docker-free and Django-free, by
`backend/memory/tests/test_honcho_deploy_contract.py`; run it on the host with:

```bash
cd backend && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest memory/tests/test_honcho_deploy_contract.py -q
```

The guard asserts the shared `x-honcho-env` session value, the nine-module entrypoint shim for both
`honcho` and `honcho-deriver`, and the stable-tag + digest pin (all three services sharing one
image).

## Optional: switch the embedding provider (and resize the schema)

The bundled default (`EMBEDDING_PROVIDER=sentence-transformers`) embeds in-process at 384
dimensions and needs no configuration. To use another provider, the pgvector column width and the
provider's output width must change **together** — setting the provider alone silently disables
embedding writes and semantic search. Set both in `.env`:

```bash
EMBEDDING_PROVIDER=ollama            # or openai
EMBEDDING_VECTOR_DIMENSIONS=768      # sentence-transformers=384, ollama=768, openai=1536
```

`EMBEDDING_VECTOR_DIMENSIONS` is the width of every embedding column. Because it changes the
database schema, switching it needs a schema resize + backfill, not just a restart. How you resize
the columns depends on how you deployed:

**Source checkout (dev overlay, `./backend` bind-mounted):**

```bash
# 1. Generate the migration (the dev overlay bind-mounts ./backend, so the
#    generated file survives the container):
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml \
  --project-directory . run --rm backend python manage.py makemigrations

# 2. Commit the migration, deploy, and let the `migrate` service apply it (or run
#    `... run --rm migrate` / `... exec backend python manage.py migrate`).
```

**Image deployment (prebuilt images, no writable source mount):** the `makemigrations` path does
**not** work here. The generated migration file is written into the container's ephemeral
filesystem and is discarded on the next `up -d`, so the physical columns silently keep their old
width while the models follow the environment. Use `align_embedding_dimensions` instead — it
resizes the live columns directly (DDL only, nothing to persist on disk) and is idempotent, so a
second run is a no-op. It must run as the Postgres superuser, so go through the one-shot `migrate`
service rather than `exec backend` (the backend runs as the least-privilege `DB_APP_USER`, which
does not own the tables):

```bash
docker compose -f deploy/docker-compose.yml --project-directory . \
  run --rm migrate python manage.py align_embedding_dimensions
```

It resizes every embedding column and recreates the HNSW index behind each one, and prints a loud
warning with the non-NULL row count before it discards any existing vectors.

**Do not run it through `backend` (#1053).** The backend runs as the least-privilege
`DB_APP_USER`, which does not own the tables or their HNSW indexes, so that path fails with a raw
`django.db.utils.ProgrammingError: must be owner of index mem_entry_embedding_hnsw` — an error that
says nothing about what to do. The `migrate` service above is the documented path because it connects
as the Postgres superuser. If you must run it in a running backend container, pass the owner
credentials explicitly:

```bash
P=$(docker compose -f deploy/docker-compose.yml --project-directory . exec -T postgres printenv POSTGRES_PASSWORD)
docker compose -f deploy/docker-compose.yml --project-directory . exec -e DB_APP_USER=reqogniloom \
  -e DB_APP_PASSWORD="$P" -e DB_USER=reqogniloom -e DB_PASSWORD="$P" \
  backend python manage.py align_embedding_dimensions
```

`verify_embedding_dimensions` is the cheap pre-deploy check (same rule: run it through `migrate`),
and `GET /health/`'s `checks.embedding_dimensions` field is the runtime signal.

**Both paths — regenerate the vectors afterwards** (the resize discards them, because pgvector
cannot cast between widths):

```bash
docker compose -f deploy/docker-compose.yml --project-directory . \
  exec backend python manage.py backfill_embeddings
```

A mismatched provider/column pair is otherwise silent: embedding writes and semantic search are
skipped, not errored. `manage.py check` flags it as `llm_adapter.W001`, and
`python manage.py verify_embedding_dimensions` compares the live DB columns against the configured
provider and exits non-zero on a mismatch — run it before deploying. `GET /health/` also reports it
while the stack runs: `checks.embedding_dimensions` becomes `"mismatch"` and a warning is added
(HTTP stays 200 — a width mismatch disables semantic search but does not make the service
unhealthy, so container probes must not restart-loop over it). pgvector cannot cast between
widths, so resizing discards existing vectors and the backfill regenerates them.

## For AI agents

If you are an AI agent deploying this system unattended, the canonical, verified command
sequence is:

```bash
# From the repository root of this checkout:
cp .env.example .env
# Fill SECRET_KEY, AUTH_JWT_SECRET, FIELD_ENCRYPTION_KEY, DB_PASSWORD, DB_APP_PASSWORD in
# .env before proceeding — the stack refuses to start without them. Also set
# SYSTEM_ADMIN_PASSWORD if you want an admin user auto-created on first start (optional:
# if left empty, admin provisioning is skipped, logged, not fatal).

docker compose -f deploy/docker-compose.yml --project-directory . up -d
docker compose -f deploy/docker-compose.yml --project-directory . ps
curl -sf http://localhost:8001/health/
```

Facts:
- Always run from the repository root. Always include `--project-directory .` on every
  `docker compose` call against files in this directory — see "Required flag" above for why.
- Health check URL: `http://localhost:8001/health/` — HTTP 200 with `{"status": "ok"}` means the
  stack is fully up (`migrate` completed, `postgres`/`redis`/`backend` are healthy).
- `/health/` is an **unauthenticated** probe, not an API: it is **not** meant to be
  internet-reachable. Keep it on the internal network (or behind the reverse proxy's own auth) —
  it publishes deployment diagnostics, and the artifact store's security posture only with
  `?verbose=1`.
- If a service does not reach `healthy` within a few minutes, inspect its logs:
  ```bash
  docker compose -f deploy/docker-compose.yml --project-directory . logs <service-name>
  ```
- Do not delete or rename `docker-compose.override.yml` to "fix" a production deploy — it is
  never applied unless explicitly passed via `-f`, so its mere presence in this directory changes
  nothing for a plain `up -d` without `-f deploy/docker-compose.override.yml`.
- Prefer `docker-compose.minimal.yml` only when explicitly asked for a minimal/slim deployment;
  default to the full stack (`docker-compose.yml`) otherwise.
- Admin provisioning is create-only: changing `SYSTEM_ADMIN_PASSWORD` in `.env` and
  re-running `up -d` does **not** reset an already-existing admin's password. It only takes
  effect the very first time, against an empty database.
- `.env` changes are read at container **creation**, not live. `docker compose restart
  <service>` does NOT pick up a changed `.env` — re-run `up -d` (recreates containers whose
  resolved config changed) instead.
- Deploying a second instance (e.g. QS alongside PROD) on the same host: set distinct
  `BACKEND_PORT`/`FRONTEND_PORT` per instance in each `.env`. Do not reuse the defaults
  (`8001`/`5173`) across instances — port collision between instances is a real incident
  this repo has already had.
