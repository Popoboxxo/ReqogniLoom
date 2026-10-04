---
type: EVIDENCE
scope: WP-1c — Release-/Deploy-Kette, build.sh, Provenienz
status: final
date: 2026-09-29
author_agent: devops-engineer
---

# WP-1c E7 — Release-/Deploy-Kette

## 1. `scripts/build.sh` — No-op bestätigt und quantifiziert

`scripts/build.sh:88-92` ruft **ausschließlich**
`docker compose -f deploy/docker-compose.yml --project-directory . build "$@"`.
Gemessen:

```
$ docker compose -f deploy/docker-compose.yml --project-directory . build --dry-run
time="2026-09-30T06:30:31+02:00" level=warning msg="No services to build"
exit=0
```

**Quantifizierung der Wirkungslosigkeit:**

| Größe | Wert |
|-------|------|
| `build:`-Sektionen in `deploy/docker-compose.yml` | **0** |
| buildable Services (Release-Compose allein) | **0** |
| buildable Services (Release + `docker-compose.override.yml`) | **5** (`backend`, `celery`, `celery-beat`, `migrate`, `frontend`) |
| Exit-Code von `docker compose … build` | **0** |
| Exit-Code von `build.sh` | **0** (`set -euo pipefail` greift nicht, weil 0 herauskommt) |
| Ausgabe von `build.sh` | `[INFO] Build completed` |

**Verschärfend gegenüber der Vor-Audit-Beschreibung:** Das Skript meldet
**erfolgreichen Abschluss**. Der Aufrufer — Mensch **oder** Pipeline — bekommt
`exit 0` und die Zeile `Build completed`, obwohl **null Images** gebaut wurden.
Der Kommentar in `build.sh:80-87` begründet die Beschränkung auf die
Release-Compose **bewusst** („the override merges the frontend's *development*
target instead of the release image"), und laut Release-Doku ist das seit
beta.16 §6.3 dokumentiert gewollt. Das Problem ist nicht die Absicht, sondern
dass (a) das Skript **0 Fehler bei 0 Arbeit** signalisiert und (b) die drei
Build-Metadaten `APP_VERSION` / `GIT_COMMIT_SHA` / `BUILD_TIME`
(`build.sh:70-74`) **exportiert, aber von keinem Service konsumiert** werden —
es gibt keine `build:`-Sektion, die `build-args` entgegennehmen könnte.

**Merksatz:** Das **einzige** Werkzeug, das `APP_VERSION`/`GIT_COMMIT_SHA`/
`BUILD_TIME` als Build-Args tatsächlich durchreicht, ist
`.github/workflows/docker-publish.yml:176-179` — der CI-Weg. `build.sh` ist
ein toter Parallelweg.
→ `AUD-2026-09-138`

## 2. Release-Compose vs. Override — Drift

| Aspekt | `deploy/docker-compose.yml` (Release) | `deploy/docker-compose.override.yml` (Dev) |
|--------|--------------------------------------|--------------------------------------------|
| `build:`-Sektionen | **0** | **5** (Zeilen 48, 81, 114, 141, 174) |
| `image:` | `ghcr.io/popoboxxo/reqogniloom-{backend,frontend}:${REQOGNILOOM_VERSION:-1.8.0-beta.17}` | `${COMPOSE_PROJECT_NAME:-reqogniloom}-{backend,frontend}:dev` |
| frontend `target` | Produktion (nginx, Port 8080) | `target: development` (`:177`) |
| frontend `ports` | `"${FRONTEND_PORT:-5173}:8080"` | `ports: !override` (`:210`, braucht Compose ≥ 2.24.4) |
| Bind-Mounts | keine | `./backend:/app` u. a. |

**Belegt am laufenden Stack:** `backend`, `celery`, `celery-beat` laufen als
Image **`f45053df0afc`** (lokal gebaut), **nicht** als
`ghcr.io/popoboxxo/reqogniloom-backend:1.8.0-beta.17`. Der laufende Stack
stammt also aus Release+Override, nicht aus dem Release-Compose allein.

⇒ Der `!override`-Merge-Tag (Compose-Spezifikation ab v2.24.4) ist eine
**Härtungsstelle gegen genau dieser Drift**, und sie ist im Datei-Header
(`:30-35`) begründet. **PASS mit Einschränkung:** Legacy `docker-compose` v1
kann das Tag nicht parsen und **bricht mit einem Parse-Fehler ab** — nicht mit
einem stillen Ignorieren. Das ist das sichere Verhalten. `backup.sh` und
`build.sh` umgehen das, indem sie nur die Release-Compose laden
(`build.sh:80-87`, `backup.sh:102-106`).

## 3. `.env`-Drift: `.env.example` vs. Compose-Referenzen

Vergleich aller `${VAR[:default]}`-Referenzen aus den vier Compose-Dateien
gegen die `KEY=`-Zeilen der `.env.example`.

### 3.1 In Compose referenziert, aber **nicht** in `.env.example`

| Variable | Compose-Stelle | Wirkung |
|----------|----------------|---------|
| `BACKEND_PORT` | `docker-compose.yml:635` | Host-Port des Backends (Kollisionsvermeidung, Ref. Zeile 631-633) |
| `FRONTEND_PORT` | `docker-compose.yml:970` | dito |
| `CELERY_CONCURRENCY` | `docker-compose.yml:887` | **Pool-Größe, im Kommentar fest an das Memory-Limit gekoppelt** (`:868-881`) |
| `BACKUP_ONCE` | `docker-compose.yml:370` | One-shot-Gate für `docs/DEPLOY_RUNBOOK.md` |
| `BACKUP_DIR` | `docker-compose.yml:356` | Pfad im Sidecar |
| `AUTH_COOKIE_SECURE` | Override | Security-Hebel |
| `COMPOSE_PROJECT_NAME` | Override `:46,79,112,139,172` | Image-Namensraum der Dev-Images |
| `HONCHO_DB_PASSWORD` | `docker-compose.yml:1020,1053` | **Credential des honcho-Profils** |

⇒ `fix/deploy-compose-env-drift` hat die früheren Lücken geschlossen, aber
**8 weitere** sind hinzugekommen. `CELERY_CONCURRENCY` ist die kritischste
Lücke: der Compose-Kommentar warnt ausdrücklich, dass die Zahl *niemals allein*
geändert werden darf, weil sie das Memory-Limit bestimmt — ein Operator, der
sie nicht in `.env.example` findet, kann sie nicht sinnvoll setzen.
→ `AUD-2026-09-142`

*(Ein Teil der `.env.example`-Zeilen ohne Compose-Referenz — `API_KEY_PEPPER`,
`AUTH_JWT_SECRET`, `FIELD_ENCRYPTION_KEY`, `CORS_ALLOWED_ORIGINS`,
`EMBEDDING_*`, `MCP_RATE_LIMIT_*` u. a. — wird korrekt über `env_file: .env`
transportiert und ist deshalb **kein** Drift-Befund. Diese Trennung ist
beabsichtigt: `env_file` für App-Variablen, `${VAR:-default}` für
Compose-Parameter.)*

### 3.2 Laufende Konfiguration (`deploy/.env`, gitignored, untracked)

`git ls-files --error-unmatch deploy/.env` → Fehler (nicht getrackt);
`git check-ignore -v deploy/.env` → `.gitignore:18`. **PASS.**
`DEBUG=False`, `DB_NAME=reqflow`, `DB_USER=reqflow`,
`DB_APP_USER=reqogniloom_app` gesetzt; **keine** `BACKUP_*`- und **keine**
`REQOGNILOOM_VERSION`-Werte ⇒ die Compose-Defaults greifen
(`BACKUP_INTERVAL=21600`, `BACKUP_RETENTION=7`, Image-Tag `1.8.0-beta.17`).

## 4. CI-Release-Provenienz — `CR-32` vollständig bestätigt

`.github/workflows/` enthält 5 Workflows: `ci.yml`, `docker-publish.yml`,
`pages.yml`, `playwright.yml`, `version-drift-check.yml`.

### 4.1 Es gibt keinen Test-vor-Image-Vertrag

| Beobachtung | Beleg |
|-------------|-------|
| `ci.yml` löst auf `push: branches: [main, feat/**]` und `pull_request: [main]` aus | `ci.yml:4-7` |
| `ci.yml` löst **nicht** auf Tags aus | keine `tags:`-Zeile in `ci.yml` |
| `docker-publish.yml` löst auf `push: tags: ['v*.*.*']` und `workflow_dispatch` aus | `docker-publish.yml:15-18` |
| `docker-publish.yml` enthält **null** `needs:`, **null** `workflow_run`, **null** `concurrency:` | `Select-String` → `0` |
| `docker-publish.yml` hat genau **einen** Job: `build-and-push` | `:27` |

⇒ **Ein Tag-Push auf einem Commit, der `ci.yml` nie ausgelöst hat** (z. B. ein
Commit auf einem Branch außerhalb `main`/`feat/**`) baut und publiziert ein
Image. Die `ci.yml`-Jobs (`lint`, `backend-test`, `frontend-test`,
`requirements-drift-check`, `agent-templates-test`, `hermes-plugin-test`,
`workflow-lint`) haben **keinen** Einfluss auf `docker-publish`.

### 4.2 Scan und Push sind zwei unabhängige Build-Läufe

```
:102  docker/build-push-action@v7   (load: true, push: false)   → Image zum Scan
:145  aquasecurity/trivy-action@v0.36.0   severity CRITICAL,HIGH, exit-code 1, ignore-unfixed true
:158  github/codeql-action/upload-sarif@v4
:168  docker/build-push-action@v7   (push: true)   ← ZWEITER, unabhängiger Build
:183  docker/build-push-action@v7   (push: true)   ← dito für frontend
```

Der Push-Step ist **kein** `scan: true` im selben `build-push-action`, sondern
ein **eigener Aufruf**, der das Image erneut baut. Gescannt wird also ein
Artefakt, publiziert wird ein anderes. Weder wird der Digest aus dem Scan
weitergegeben, noch wird er in einen Output geschrieben. **Weder der
gepushte Digest noch der gescannte Digest werden irgendwo festgehalten.**

**Positiv:** Der Scan ist ein echtes Gate — `exit-code: '1'` bei
`CRITICAL,HIGH`, `ignore-unfixed: true` (nur behebbare CVEs),
SARIF-Upload in GitHub Security. Das ist die richtige Grundhaltung, nur die
Verkettung fehlt.

### 4.3 Keine SBOM, keine Signatur, keine Provenance

`Select-String -Pattern "sbom|cosign|provenance|attest|slsa"` über
**alle** `.github/workflows/*.yml` → **0 Treffer**. Konkret fehlt:

* **SBOM** — kein `anchore/sbom-action`, kein `sbom: true` an
  `build-push-action`.
* **Signatur** — kein `cosign sign`, kein keyless-Signing.
* **Provenance-Attestierung** — `provenance: true` ist an keinem
  `build-push-action` gesetzt; kein SLSA-Workflow.

### 4.4 Kein Digest-Pinning auf der Konsumentenseite

`deploy/docker-compose.yml:567, 683, 755, 802, 893, 953` referenzieren
`${REQOGNILOOM_VERSION:-1.8.0-beta.17}` — ein **Tag**, kein
`@sha256:`-Digest. Selbst wenn CI signieren würde, könnte der Deployment nicht
prüfen, ob das deployed Image das signierte ist.
→ `AUD-2026-09-136`, `AUD-2026-09-137`

**Reconciliation:** `CR-32` („Release-/Provenienz-Gate, kein Test-vor-Image-Vertrag,
Scan/Push/SBOM nicht digestgebunden") ist damit **BESTAETIGT** — alle drei
Teilaussagen einzeln belegt. `CR-38` (Lieferkette) ebenfalls.

## 5. Image-Pinning — Gesamtbild

| Image | Referenz | Art | Bewertung |
|-------|----------|-----|-----------|
| `reqogniloom-backend` | `:1.8.0-beta.17` | Release-Tag, env-überschreibbar | **kein Digest** |
| `reqogniloom-frontend` | `:1.8.0-beta.17` | dito | **kein Digest** |
| `pgvector/pgvector` | `:pg16` | Major-Tag | Minor driftet (live 16.15) |
| `redis` | `:7-alpine` | Major-Tag | Minor driftet (live 7.4.11) |
| `node` | `:22-slim` | Major-Tag | driftet |
| `plastic-labs/honcho` | `:latest` | **`latest`** | driftet unkontrolliert; Begründung in `docker-compose.yml:1003-1013` dokumentiert (SDK 2.3.0 braucht eine API, die kein vX.Y.Z-Tag trägt) |

Die `latest`-Begründung für Honcho ist **transparent und nachvollziehbar
dokumentiert** — das ist kein Versehen, sondern eine bewusste, protokollierte
Entscheidung. Sie bleibt trotzdem der einzige Ort, an dem ein Image-Update
ohne Compose-Änderung in eine laufende Umgebung einziehen kann.

⇒ `AUD-2026-09-136`

## 6. MTTG (Mean Time To Green/Feedback)

| Meilenstein | Ziel (Rolle) | Ist | Bewertung |
|-------------|--------------|-----|-----------|
| Commit → Lint | < 5 min | `ci.yml`-Job `lint` auf Push/PR, kein Tag-Trigger | **nicht messbar im aktuellen Lauf** — kein CI-Lauf dieses Branches im Fenster; **BLOCKED**, nicht als PASS gewertet |
| Commit → SAST | < 10 min | `requirements-drift-check`, `workflow-lint` (nicht klassisches SAST); **kein** Bandit/Semgrep in `ci.yml` | **Lücke**: kein SAST-Tool in `ci.yml` |
| Commit → Security-Scan | < 30 min | Trivy **nur** in `docker-publish.yml`, das **nur** auf Tags löst | ** faktisch unerreichbar für normale Commits** |
| Commit → Review | < 60 min | manuell | nicht messbar |

**Struktureller Befund:** Der einzige Vulnerability-Scan des Projekts hängt an
einem **Tag-**Trigger. Für den normalen Entwicklungszyklus (Commit → Branch →
PR) gibt es **keinen** Image-Scan. `pip-audit`/`npm audit`/`safety` kommen im
grep über `ci.yml` nicht vor ⇒ es gibt auch **keinen** Dependency-Scan im CI.
⇒ Teil von `AUD-2026-09-137`

## 7. `deploy/verify-backup-command.sh`

Vorhanden (`deploy/verify-backup-command.sh`, 9646 B) — die im Compose
(`:309-310`) referenzierte **Shell-Selbstprüfung** des Backup-`command:`-Blocks
aus #1074. Existiert und ist im Repo versioniert. **PASS** (Existenz + Verweise
konsistent); inhaltlich nicht ausgeführt (rein statische Prüfung eines
Compose-Fragments, kein Laufzeitverhalten).
