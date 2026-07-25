# ReqogniLoom Deployment Examples

Drei Wege, den Stack zu betreiben. Alle brauchen einen `.env`.

## docker-compose.ghcr.yml — Pull-basiert, GHCR-Images

Kein Build nötig. Zieht fertige Images von `ghcr.io/<owner>/reqogniloom-backend`
und `-frontend`.

```bash
cp deployment/.env.example deployment/.env
# .env füllen: alle CHANGE-ME-Werte, GHCR_OWNER, IMAGE_TAG
docker compose -f deployment/docker-compose.ghcr.yml --env-file deployment/.env pull
docker compose -f deployment/docker-compose.ghcr.yml --env-file deployment/.env up -d
```

- `IMAGE_TAG` in Produktion auf eine feste Version pinnen (z.B. `1.2.0`), nicht `latest`.
- Frontend-Variablen (`VITE_API_BASE_URL`, `VITE_ALLOWED_HOSTS`) sind im Image
  bereits eingebacken (Build-Zeit) — bei einem GHCR-Image nicht mehr änderbar.
- 8 Services: postgres, postgres-backup, redis, migrate (self-init, REQ-188),
  backend, celery, celery-beat, frontend. Kein separater `bootstrap`-Service.

## docker-compose.minimal.yml — Pull-basiert, 6 Services

Reduzierte Variante für kleine/Single-Instance-Deployments. Faltet `migrate`
in den Start von `backend` (REQ-188 self-init läuft dabei automatisch mit)
und `celery-beat` in `celery` (embedded beat via `-B`). `postgres-backup`
bleibt erhalten.

```bash
cp deployment/.env.example deployment/.env
# .env füllen: alle CHANGE-ME-Werte, GHCR_OWNER, IMAGE_TAG
docker compose -f deployment/docker-compose.minimal.yml --env-file deployment/.env pull
docker compose -f deployment/docker-compose.minimal.yml --env-file deployment/.env up -d
```

- 6 Services: postgres, postgres-backup, redis, backend (inkl. migrate),
  celery (inkl. beat), frontend.
- Nur für **einen** `backend`-Replica und **einen** `celery`-Replica geeignet.
  Backend führt `migrate` bei jedem Start aus (racy bei >1 Replica); Celery
  mit embedded beat darf nie mehr als einmal laufen (doppelte periodische
  Tasks). Für horizontale Skalierung → `docker-compose.ghcr.yml` (8 Services,
  dedizierte `migrate`- und `celery-beat`-Services) nutzen.
- Gleiche `.env.example` wie bei `docker-compose.ghcr.yml`.

## Root docker-compose.yml — Lokaler Build

Für Entwicklung oder wenn eigene Images gebaut werden sollen. Siehe Root-`.env.example`.

## unraid/ — Unraid-spezifisch

Bind-Mounts unter `/mnt/user/appdata/`, Compose Manager Plus Template.
Siehe `deployment/unraid/README.md`.
