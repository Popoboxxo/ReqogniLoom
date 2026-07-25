# ReqogniLoom Deployment Examples

Zwei Wege, den Stack zu betreiben. Beide brauchen einen `.env`.

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

## Root docker-compose.yml — Lokaler Build

Für Entwicklung oder wenn eigene Images gebaut werden sollen. Siehe Root-`.env.example`.

## unraid/ — Unraid-spezifisch

Bind-Mounts unter `/mnt/user/appdata/`, Compose Manager Plus Template.
Siehe `deployment/unraid/README.md`.
