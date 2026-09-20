# bluepencil sidecar (debug/QS only — never production)

This directory vendors the **self-hosted bluepencil sidecar** — the Option B store from the
integration plan (`docs/bluepencil-integration.md`, PR #972). It is a small Node HTTP server that
holds the bluepencil review layer's notes in **one JSON file**. ReqogniLoom's frontend talks to it
over the Compose network. The sidecar is gated behind the `bluepencil` Compose profile and the
frontend probe behind the `BLUEPENCIL_ENABLED` flag — enabling it takes both, and both are off by
default (see Enable).

## Read this before enabling it

**This is a debugging/QS tool, not a production store and not a product feature.** The sidecar:

- has **no user authentication** — anyone who can reach it can read and write notes;
- has **no tenant isolation** — one JSON file is shared by **every workspace**; there is no RLS /
  TenantContext scoping, so notes from one workspace are visible to all;
- is therefore **not** the production path. The production path is **Option A**, the DRF
  implementation (`backend/review_notes/`, `docs/bluepencil-integration.md` §0/§3): per-tenant
  `ReviewNote` rows behind JWT + RLS, writing only for reviewer roles.

Use it to *see and measure* the layer in the real app (plan stage 2), not as a "pilot" deployment.

## Enable

Two switches are required in dev — the sidecar **and** the frontend loader. Set
both in `.env` (see `.env.example`) and run `make up`:

```bash
COMPOSE_PROFILES=bluepencil   # starts the sidecar service
BLUEPENCIL_ENABLED=1          # arms the frontend probe
```

```bash
make up
```

`make bluepencil` is a one-off equivalent that starts the sidecar alone:

```bash
make bluepencil
```

That is `docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml
--project-directory . --profile bluepencil up -d`, i.e. the running dev stack plus the sidecar.
It starts the sidecar but leaves the review layer **off** until `BLUEPENCIL_ENABLED=1` is set in
`.env` and the frontend service is restarted. The sidecar is reachable inside the Compose network as
**`bluepencil:8787`**; it does **not** publish a host port.

## Production / prebuilt image (issue #980)

The dev override above arms the layer through Vite's dev server. A **prebuilt
production image** (`frontend/Dockerfile`, `target: production`) reads the flag at
*image build* time, so it must be passed as a build arg — `BLUEPENCIL_ENABLED` in
`.env` only affects the dev override:

```bash
docker build -f frontend/Dockerfile --target production frontend \
  --build-arg VITE_BLUEPENCIL_ENABLED=1 \
  --build-arg VITE_BLUEPENCIL_ENVIRONMENT=dev \
  -t reqogniloom-frontend:bluepencil
```

`frontend/nginx.conf` proxies `/bluepencil/api/` to the sidecar
(`http://bluepencil:8787`) with per-request DNS resolution, so it works both with
and without the `bluepencil` profile running. The upstream must still be reachable
on the Compose network — run the stack with `--profile bluepencil`.

## Secure context required for the integrity check (issue #981)

The vendored loader (`frontend/public/bluepencil/latest/attach.js`) verifies the
element bundle against the SHA256 in `latest.json` via WebCrypto
(`crypto.subtle`). Browsers only expose WebCrypto in a **secure context**: HTTPS,
`localhost`, `127.0.0.1` or `file:`. On a plain-HTTP origin with an IP or
hostname (e.g. `http://172.20.5.120:5173` — the usual LAN/QS deployment) the check
cannot run. ReqogniLoom then loads the layer **without** the integrity check and
logs one visible `console.warn`, instead of requesting a check that would abort
the whole attach and leave the layer silently unmounted. Serve the app over HTTPS
(or access it via `localhost`/`127.0.0.1`) to keep verification enabled.

## Why opt-in

Where no sidecar runs, the layer's `GET /bluepencil/api/health` probe is answered with 404 (or 502
through the dev proxy) and the browser logs it as a console error — and this repo's E2E suite
requires a clean console. The app must therefore not probe unless it is explicitly asked to, which
is why the layer is opt-in.

## Disable

```bash
make bluepencil-down
```

That stops just the `bluepencil` service (`... --profile bluepencil stop bluepencil`) and leaves the
rest of the stack running. Alternatively, remove `bluepencil` from `COMPOSE_PROFILES` and/or set
`BLUEPENCIL_ENABLED=0`, then run `make up`.

The sidecar itself toggles at runtime and the UI degrades gracefully when it is absent — but the
frontend loader flag (`BLUEPENCIL_ENABLED`) is read by Vite at startup, so enabling it requires the
frontend service to be (re)started after changing the value.

## Where the notes live

The Compose service mounts the named volume `bluepencil_data` at `/data`; the store file is
`/data/notes.json`. It survives container restarts and rebuilds.

**Back up the notes:**

```bash
# From the repository root, with the profile active:
docker compose -f deploy/docker-compose.yml --project-directory . --profile bluepencil \
  exec bluepencil cat /data/notes.json > notes-backup.json
```

**Reset the store:** stop the service, remove the volume, then start it again fresh.

```bash
make bluepencil-down
docker volume ls | grep bluepencil          # find the project-prefixed volume name
docker volume rm <project>_bluepencil_data  # delete the notes
make bluepencil                             # recreates the volume, empty
```

Do **not** reach for `docker compose down -v` here — the `-v` removes *every* volume in the project,
including `postgres_data`.

**Corrupt store:** if `notes.json` is not valid JSON, the sidecar **refuses to start and exits with
code 2** rather than silently serving an empty set. That is deliberate: an empty set looks like "no
notes" and would hide data loss. Fix it by restoring `notes-backup.json` into the volume or deleting
the store for a clean start.

## HTTP contract

The service is started with `--base /bluepencil/api`, so all routes are prefixed with that path:

| Method | Path | Purpose |
|---|---|---|
| GET | `/bluepencil/api/health` | Liveness: `{ ok, status, version }` (used by the container healthcheck) |
| GET | `/bluepencil/api/notes` | List notes (filters: `route, intent, type, session, source, environment, includeDone, since, status`) |
| POST | `/bluepencil/api/notes` | Create a note |
| PATCH | `/bluepencil/api/notes/{id}` | Update note fields |
| POST | `/bluepencil/api/notes/{id}/messages` | Append a message/reply to a note |
| POST | `/bluepencil/api/notes/bulk-delete` | Bulk delete (`{ ids?, filter?, confirm: true }`) |
| GET | `/bluepencil/api/sessions` | List sessions |
| GET | `/bluepencil/api/bundle` | Canonical export bundle |
| GET | `/bluepencil/api/journal` | Operation history (optional) |

The sidecar's own CLI (for running it outside Compose):

```
node server.js --store <path> [--port 8787] [--host 127.0.0.1] [--base /api/v1/bluepencil]
               [--root <static dir>] [--environment dev|staging|live] [--cors] [--read-only]
               [--allow-env-mismatch]
```

`BLUEPENCIL_STORE` is an alternative to `--store`. In this stack the Compose service passes
`--store /data/notes.json`, `--port 8787`, `--host 0.0.0.0`, `--base /bluepencil/api` and
`--environment ${BLUEPENCIL_ENVIRONMENT:-dev}`.

## Provenance

- Vendored from the `Popoboxxo/bluepencil` release **`v0.1.0-alpha.1`**.
- `deploy/bluepencil/server.js` is `dist/server.js` from `bluepencil-0.1.0-alpha.1.tgz`.
  SHA256: `931f65ffcf27da040578b4ff42f507e36debb659ac5537d856206f0185a8ef04`.
- The release's own `SHA256SUMS` authenticates the tarball (SHA256
  `0ad53281f673042ee8c90c05e2c733c021c6a105efe15743cb1d30f8255f5959`) plus the browser assets.
- The file imports **only Node builtins** — no npm dependencies, no build step. The Compose service
  therefore runs it on stock `node:22-slim`.

## Upgrade recipe

1. Download the new release tarball and its `SHA256SUMS` from the `Popoboxxo/bluepencil` releases
   page (e.g. `bluepencil-<version>.tgz`).
2. Verify the tarball against the release's `SHA256SUMS`:
   ```bash
   sha256sum -c SHA256SUMS --ignore-missing    # or: echo "<sha>  bluepencil-<version>.tgz" | sha256sum -c -
   ```
3. Extract `dist/server.js` from the tarball and replace `deploy/bluepencil/server.js`. Record the new
   file's SHA256 here (and in the PR/commit) so the next upgrade has a known-good reference.
4. Replace the browser assets under `frontend/public/bluepencil/latest/*` with the release's versions
   (this path is owned by the frontend, not by this directory).
5. Bump the version in `frontend/public/bluepencil/latest.json` so clients pick up the new asset set.
6. Restart the sidecar: `make bluepencil-down && make bluepencil`, then check
   `GET /bluepencil/api/health` reports the new `version`.

The store file format is the sidecar's contract — a version that changes it needs the store migrated
or reset, so check the release notes before upgrading an instance whose notes matter.
