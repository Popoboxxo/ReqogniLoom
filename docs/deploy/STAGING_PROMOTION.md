# Staging Deployment & Same-Digest Production Promotion

**Status: BESTÄTIGT** (S5.2 WP-3, OPS-010 + OPS-007 production half)  
**Workflow:** `.github/workflows/deploy-staging.yml`  
**Deployment model:** Docker Compose on isolated hosts (this repo's model — not Kubernetes)

## 1. Problem this closes

`docker-publish.yml` ends at keyless cosign sign/verify (lines ~409-470). It has a
`staging` *approval* environment between CI and publish, but:

- no `docker compose up` against a staging host,
- no migration rehearsal,
- no restore rehearsal,
- no HTTP smoke,
- no `production` environment / promotion job.

Consequently a destructive migration can reach a customer database on the first
`up -d` with no prior rehearsal. This workflow adds the missing bridge **without
changing the existing release path**: `docker-publish.yml`, `client-smoke.yml`,
`docker-compose.yml`, `ci.yml` and the README are untouched (WP-1/WP-2 boundaries).

> The compose-internal migration ordering was verified as already correct and is
> deliberately relied upon, not changed: `deploy/docker-compose.yml:925` has
> `migrate.depends_on.postgres.condition: service_healthy`, and
> `backend` / `celery` / `celery-beat` wait on
> `migrate: service_completed_successfully`.

## 2. Flow

```
docker-publish.yml (unchanged; tag vX.Y.Z)
  └─ cosign sign + verify                    [existing]
       └─ workflow_run: completed/success     ──┐
          OR repository_dispatch deploy-staging ├─► guard ─► resolve ─► deploy-staging
                                                │              │             │
                                                │              │    compose up (pinned digests)
                                                │              │    migrate one-shot (depends_on)
                                                │              │    verify-restore.sh (throwaway DBs)
                                                │              │    HTTP smoke /health/live + /ready
                                                │              │             │
                                                │              └─────────────┴─► deploy-production
                                                │                                 [environment: production]
                                                │                                 required reviewers (out-of-band)
                                                │                                 IDENTICAL digests, no rebuild
                                                │                                 migrate one-shot + up + smoke
```

### Jobs

| Job | Purpose | Key property |
|-----|---------|--------------|
| `guard` | Static self-audit of the workflow source | Fails closed on missing `environment: production`, missing deploy job, any build construct, or a deploy job not consuming the resolve outputs |
| `resolve` | Resolve tag → immutable `sha256:` digest for **both** images; re-verify cosign signature | Digest resolved exactly once |
| `deploy-staging` | Apply pinned digests on the isolated staging host; rehearse migration + restore + HTTP smoke | Fail-closed migration wait via `docker wait` |
| `deploy-production` | Promote the **identical** digests after approval | `environment: production`; no tag re-resolution |

## 3. Same-digest invariant

1. `resolve` produces `backend_digest` and `frontend_digest` from the publish
   output (or accepts an explicitly signed digest pair via `repository_dispatch`),
   validates `^sha256:[0-9a-f]{64}$`, and re-verifies the keyless cosign signature
   against the `docker-publish.yml` workflow identity.
2. Both deploy jobs receive **the same two job outputs** and generate an override
   file that replaces `image:` for `backend`, `llm-preflight`, `migrate`, `celery`,
   `celery-beat` (all backend digest) and `frontend` (frontend digest):

   ```yaml
   services:
     migrate:
       image: ghcr.io/<owner>/reqogniloom-backend@sha256:<backend-digest>
     frontend:
       image: ghcr.io/<owner>/reqogniloom-frontend@sha256:<frontend-digest>
   ```

   Compose merges this over `deploy/docker-compose.yml`; all other settings
   (`command`, `env_file`, `depends_on`, healthchecks) stay intact.
3. The production job is invoked with `needs: [deploy-staging, resolve]` and
   reads `needs.resolve.outputs.*` — it never inspects a moving tag and never
   builds. `compose pull` fetches by digest, not by tag.
4. The `guard` job enforces INV-1..INV-4 (see the workflow header). Tokens are
   assembled at runtime inside the guard so it cannot match its own source.

### Local guard verification

Run this from the repo root on a branch containing the workflow:

```bash
python3 - <<'PY'
import pathlib, re, sys
text = pathlib.Path(".github/workflows/deploy-staging.yml").read_text()
lines = text.splitlines(); errors = []
if not re.search(r"^\s{4}environment:\s*production\s*$", text, re.M):
    errors.append("INV-1: missing `environment: production`")
starts = [(i, m.group(1)) for i, l in enumerate(lines)
          if (m := re.match(r"^  ([A-Za-z0-9_-]+):\s*$", l))]
spans = {n: (i, starts[k+1][0] if k+1 < len(starts) else len(lines))
         for k, (i, n) in enumerate(starts)}
for n in ("deploy-staging", "deploy-production"):
    if n not in spans: errors.append(f"INV-2: missing job `{n}`")
for n in ("deploy-staging", "deploy-production"):
    if n not in spans: continue
    lo, hi = spans[n]
    body = "\n".join(lines[lo:hi])
    code = "\n".join(p.split("#", 1)[0] for p in body.splitlines())
    for t in ["docker"+" build", "buildx"+" build", "compose"+" build", " "+"--build", "build"+":"]:
        if t in code: errors.append(f"INV-3: `{n}` contains {t!r}")
    for o in ("needs.resolve.outputs.backend_digest", "needs.resolve.outputs.frontend_digest"):
        if o not in body: errors.append(f"INV-4: `{n}` missing {o}")
print("GUARD OK" if not errors else "GUARD FAILED\n" + "\n".join(errors))
sys.exit(bool(errors))
PY
```

## 4. Environment protection (out-of-band setup — GitHub UI)

The workflow declares `environment: production` but **does not create or
configure it**. An administrator must, in **Settings → Environments**:

1. Create the `production` environment.
2. Add **Required reviewers** (at least one person/team who is not the release
   engineer). This is what makes the `deploy-production` job pause for approval.
3. Optionally restrict deployment branches/tags and add a wait timer.
4. Keep the existing `staging` environment used by `docker-publish.yml` as-is —
   it is a separate approval gate and is not modified here.

> Reviewers are intentionally configured out-of-band so the approval authority
> cannot be changed by a code-review-only PR. Never commit reviewer identities
> into the workflow file.

## 5. Hosts, secrets and variables

All values are GitHub Actions secrets/variables — **no credentials in code or
config**. The runner uses `GITHUB_TOKEN` with `packages: read` for GHCR.

| Kind | Name | Purpose |
|------|------|---------|
| Variable | `STAGING_HOST`, `STAGING_USER` | Isolated staging host and SSH user |
| Variable | `STAGING_BASE_URL` | Base URL for `/health/live` + `/health/ready` smoke |
| Variable | `PRODUCTION_HOST`, `PRODUCTION_USER` | Production host and SSH user |
| Variable | `PRODUCTION_BASE_URL` | Base URL for production smoke |
| Variable | `REMOTE_DEPLOY_DIR` | Directory on each host containing `docker-compose.yml` + `.env` |
| Secret | `STAGING_SSH_KEY`, `STAGING_KNOWN_HOSTS` | Deploy key + pinned host key (strict host-key checking) |
| Secret | `PRODUCTION_SSH_KEY`, `PRODUCTION_KNOWN_HOSTS` | Same for production |

Host prerequisites (per environment):

- Docker Engine with the Compose v2 plugin, `curl`, `bash` and `ps`.
- A working `.env` (DB credentials, `SECRET_KEY`, LLM provider config that
  satisfies the `llm-preflight` one-shot — e.g. `opencode_go` requires its
  session variable). The workflow never writes or reads these secrets itself.
- The remote deploy directory must already exist and be writable by the SSH user.
- Network egress from the runner to GHCR (pull) and to both hosts (SSH/HTTP).
- The workflow file must be present on the default branch so `workflow_run` can
  execute it (GitHub runs `workflow_run` workflows from the default branch).

## 6. Staging rehearsal

Before production approval, `deploy-staging` performs:

1. **Resolve + verify** immutable digests and cosign signatures.
2. **Compose apply (no rebuild):** `compose pull`, then `compose up -d postgres redis`.
3. **Migrate one-shot:** `compose up -d migrate`, locate the container with
   `compose ps -aq migrate`, block on `docker wait <id>`, and fail the job on any
   non-zero migration exit code. This relies on the existing
   `postgres: service_healthy` gate at `deploy/docker-compose.yml:925`.
4. **Restore rehearsal:** `deploy/verify-restore.sh` runs on the runner against
   throwaway Postgres containers (it extracts the real `postgres-backup` block,
   restores atomically and checks table/vector parity). The live database is
   never contacted. If the script were absent, the documented fallback is the
   HTTP smoke in step 5 plus a manual restore check — but it **is** present, so
   it always runs.
5. **HTTP smoke:** `curl -fsS` against `/health/live` and `/health/ready`
   (fail-closed readiness). Retries are bounded; no failure is masked.

Only after all five steps succeed does the `production` job become eligible for
review. Production repeats the digest-pinned apply, migration one-shot and HTTP
smoke — but not the restore rehearsal, which is a staging-only gate.

## 7. Rollback

Rollback is a redeploy of a previously signed digest — never a rebuild:

```yaml
# repository_dispatch payload (type: deploy-staging)
client_payload:
  backend_digest: "sha256:<previous-backend>"
  frontend_digest: "sha256:<previous-frontend>"
  version: "<previous-version>"
```

The dispatch path validates and cosign-verifies the supplied digests before
deployment, so an unsigned or malformed rollback is refused. Run the rollback
against staging first; only promote after the production approval gate.

## 8. Planned (S5.3) — Migration-Safety-Runbook

> **Pointer only — the runbook is intentionally NOT written here.**
> S5.3 will add the Migration-Safety-Runbook covering destructive-migration
> classification, expand/contract sequencing, backup-before-migrate, and
> migration rollback/forward-fix criteria. Until it lands, the restore rehearsal
> in §6 is the interim safety gate. Do not duplicate that runbook into this
> document or the workflow.

## 9. Delivery-effect note (DORA)

- **Lead time:** unchanged for image production; adds an automated staging +
  approval hop before production (a deliberate, reviewer-controlled gate).
- **Deployment frequency:** unchanged for publish; production promotion is now
  decoupled into its own gated job.
- **Change-fail rate:** expected to decrease — destructive migrations fail in
  staging (migrate wait + restore rehearsal) before touching customer data.
- **Recovery time:** improved — digest-pinned rollback is a one-command
  repository_dispatch, not a rebuild/re-tag.
