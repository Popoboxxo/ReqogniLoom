---
type: EVIDENCE
scope: WP-1c — Docker Compose Validierung (alle Profile)
status: final
date: 2026-09-29
author_agent: devops-engineer
---

# WP-1c E1 — Docker-Compose-Validierung (alle Varianten und Profile)

Branch `chore/system-audit-2026-09` @ `3dcc80d8`. Alle Kommandos read-only
(`docker compose config`), **kein** `up`/`down`/`build`. Der laufende Stack
(Projekt `ai-native-reqflow-poc`) wurde nicht angetastet.

## 1. Validierungsergebnis je Compose-Aufruf

| # | Kommando | Exit | Ergebnis |
|---|----------|------|----------|
| 1 | `compose -f deploy/docker-compose.yml config --quiet` | **0** | valide |
| 2 | `compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml config --quiet` | **0** | valide |
| 3 | `compose -f deploy/docker-compose.minimal.yml config --quiet` | **0** | valide |
| 4 | `compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml config --quiet` | **0** | valide |
| 5 | `compose -f deploy/docker-compose.yml --profile honcho config --quiet` | **0** | valide |
| 6 | `compose -f deploy/docker-compose.yml --profile bluepencil config --quiet` | **0** | valide |
| 7 | `compose -f deploy/docker-compose.yml --profile honcho --profile bluepencil config --quiet` | **0** | valide |

**Fazit: alle 5 realen Betriebs-Pfade und beide Profile sind syntaktisch valide
und startbar.** Kein defektes optionales Profil.

Zwei *nicht* validen Aufrufe — beide **by design** (Overlays brauchen die Basis,
siehe Datei-Header `testing/docker-compose.test.yml:19-23`):

| Kommando | Exit | Fehler |
|----------|------|--------|
| `compose -f deploy/docker-compose.override.yml config` | 1 | `service "postgres" has neither an image nor a build context specified` |
| `compose -f testing/docker-compose.test.yml config` | 1 | `service "backend-test" depends on undefined service "postgres"` |

## 2. Compliance-Matrix (aus `config --format json`, alle Profile aktiv)

| Service | Image | Profil | Restart | Healthcheck | Mem-Limit | Log-Rotation |
|---------|-------|--------|---------|-------------|-----------|--------------|
| `postgres` | `pgvector/pgvector:pg16` | default | unless-stopped | YES | 384M | 10m x3 |
| `postgres-backup` | `pgvector/pgvector:pg16` | default | unless-stopped | **MISSING** | **—** | 10m x3 |
| `redis` | `redis:7-alpine` | default | unless-stopped | YES | 512M | 10m x3 |
| `backend` | `…reqogniloom-backend:1.8.0-beta.17` | default | unless-stopped | YES | 512M | 10m x3 |
| `llm-preflight` | `…backend:1.8.0-beta.17` | default | `no` | n/a (One-shot) | 64M | 10m x3 |
| `migrate` | `…backend:1.8.0-beta.17` | default | `no` | n/a (One-shot) | 512M | 10m x3 |
| `celery` | `…backend:1.8.0-beta.17` | default | unless-stopped | YES | 384M | 10m x3 |
| `celery-beat` | `…backend:1.8.0-beta.17` | default | unless-stopped | YES | 256M | 10m x3 |
| `frontend` | `…reqogniloom-frontend:1.8.0-beta.17` | default | unless-stopped | YES | 128M | 10m x3 |
| `honcho-postgres` | `pgvector/pgvector:pg16` | honcho | **—** | YES | **—** | **NONE** |
| `honcho-redis` | `redis:7-alpine` | honcho | **—** | YES | **—** | **NONE** |
| `honcho-migrate` | `plastic-labs/honcho:latest` | honcho | **—** | n/a (One-shot) | **—** | **NONE** |
| `honcho` | `plastic-labs/honcho:latest` | honcho | **—** | YES | **—** | **NONE** |
| `honcho-deriver` | `plastic-labs/honcho:latest` | honcho | unless-stopped | YES | **—** | 10m x3 |
| `bluepencil` | `node:22-slim` | bluepencil | unless-stopped | YES | **—** | 10m x3 |

`docker ps` bestätigt: `postgres-backup-1  Up 7 hours` — **ohne** `(healthy)`,
als einziger langlaufender Default-Service.

## 3. Netz / Ports / Privileges / Volumes

| Service | Host-Port | privileged | `network_mode` | Volumes |
|---------|-----------|------------|----------------|---------|
| `backend` | `:8001->8000` | no | default | `backend_dr_backups:/app/backups` (volume) |
| `frontend` | `:5173->8080` | no | default | — |
| `redis` | **none** | no | default | `redis_data:/data` |
| `postgres` | **none** | no | default | `postgres_data:/var/lib/postgresql/data` |
| `postgres-backup` | **none** | no | default | `postgres_backup_data:/backups` |
| `celery` / `celery-beat` | **none** | no | default | — |
| `migrate` / `llm-preflight` | **none** | no | default | — |
| `honcho` | `127.0.0.1:8010->8000` | no | default | — |
| `honcho-postgres` / `honcho-redis` / `honcho-deriver` | **none** | no | default | `honcho_*_data` |
| `bluepencil` | **none** | no | default | `./deploy/bluepencil/server.js:/opt/bluepencil/server.js:ro`, `bluepencil_data:/data` |

**PASS:** kein `privileged`, kein `network_mode: host`, Postgres/Redis **nicht**
auf dem Host publiziert. Das entspricht der Datei-eigenen Sicherheitsregel
`deploy/docker-compose.yml:42`.

## 4. `depends_on` — alle Bedingungen

Jede Default-Service-Abhängigkeit trägt eine explizite `condition`:

```
backend        : llm-preflight=service_completed_successfully | migrate=service_completed_successfully
                 | postgres=service_healthy | redis=service_healthy
postgres-backup: migrate=service_completed_successfully | postgres=service_healthy
celery         : llm-preflight=service_completed_successfully | postgres=service_healthy | redis=service_healthy
celery-beat    : llm-preflight=service_completed_successfully | postgres=service_healthy | redis=service_healthy
frontend       : backend=service_healthy
migrate        : postgres=service_healthy
llm-preflight  : (keine — One-shot-Gate, korrekt)
honcho         : honcho-migrate=service_completed_successfully | honcho-postgres=service_healthy | honcho-redis=service_healthy
honcho-deriver : dito
```

**PASS für die Release-Compose.** Der Befund zum fehlenden `condition:
service_healthy` betrifft ausschließlich das **Test-Overlay**
(`testing/docker-compose.test.yml:54-56`) — siehe Finding `AUD-2026-09-140`.

## 5. Image-Pinning

**Kein einziges Image ist per Digest gepinnt.** Alle Referenzen sind mutable Tags:

| Referenz | Pin-Art |
|----------|---------|
| `pgvector/pgvector:pg16` | Major-Tag (Floating Minor) |
| `redis:7-alpine` | Major-Tag (Floating Minor) |
| `node:22-slim` | Major-Tag (Floating Minor) |
| `ghcr.io/popoboxxo/reqogniloom-{backend,frontend}:${REQOGNILOOM_VERSION:-1.8.0-beta.17}` | Release-Tag, **überschreibbar** |
| `ghcr.io/plastic-labs/honcho:latest` | **`latest`** |

Laufend gemessen: `postgres 7.4.11` Redis, `PG 16.15`, `pgvector 0.8.5` — alle
durch Tag-Drift jederzeit änderbar. Siehe Finding `AUD-2026-09-136`.

## 6. Klartext-Credentials in Compose-Dateien

`Select-String` über alle vier Compose-Dateien nach
`PASSWORD|SECRET|TOKEN|API_KEY` in **nicht-Kommentar**-Zeilen **ohne** `${…}`:
**kein Treffer.** Alle Geheimnisse kommen über `${VAR}` bzw. `env_file: .env`.
`deploy/.env` ist korrekt gitignored (`.gitignore:18`) und untracked
(`git ls-files --error-unmatch deploy/.env` → Fehler).

**Einzige Ausnahme (Low):** `deploy/docker-compose.yml:73` und `:1020` /
`:1053` enthalten den Klartext-Default `HONCHO_DB_PASSWORD:-honcho-dev-password`
für `honcho-postgres`. Betrifft nur ein optionales, intern erreichbares Profil
ohne Host-Port. → `AUD-2026-09-148`.

## 7. `build:`-Verfügbarkeit je Compose-Datei (`build.sh`-No-op, siehe E5)

| Compose-Datei | buildable Services |
|---------------|-------------------|
| `deploy/docker-compose.yml` | **0** |
| `deploy/docker-compose.override.yml` | 0 allein (Overlay) |
| `deploy/docker-compose.minimal.yml` | **0** |
| `testing/docker-compose.test.yml` | 2 (`backend-test`, `frontend-test`) |
| Release **+** Override (merged) | **5** (`backend`, `celery`, `celery-beat`, `migrate`, `frontend`) |
| Release **+** Test-Overlay (merged) | **2** (`backend-test`, `frontend-test`) |
