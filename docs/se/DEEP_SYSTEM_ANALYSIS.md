# Tiefe Systemanalyse — ReqFlow

> Erstellt: 2026-07-14
> Scope: Frontend (React/TypeScript), Infrastruktur (Docker/CI), Backend-Vertiefung, LLM/MCP-Integration
> Vorgänger: [SYSTEM_AUDIT.md](./SYSTEM_AUDIT.md) — Findings daraus werden hier nicht wiederholt

## Executive Summary

Die Analyse vertieft das System-Audit um vier bisher nicht oder nur oberflächlich betrachtete Ebenen. Der schwerwiegendste Befund: **Das System ist in der dokumentierten Produktionskonfiguration nicht lauffähig.** Der Frontend-Prod-Build schlägt fehl (`npm ci` ohne kopiertes `package-lock.json`, `--only=production` ohne Build-Toolchain — `frontend/Dockerfile:8,24`), drei von fünf LLM-Providern (Anthropic, Ollama, Azure) sind wegen einer nicht implementierten `@abstractmethod` nicht instanziierbar, der Async-LLM-Pfad ist tot (Task-Message wird vom Worker verworfen), der SSE-Endpoint crasht bei jedem GET, und der in REQ-020/021 gefixte Transactional-Outbox-Mechanismus hat keinen Consumer — die Fixes laufen im Deployment nie. Dazu kommen ein RBAC-Bypass über sechs MCP-Tool-Gruppen (Viewer kann schreiben, inkl. persistenter Prompt-Injection via `prompt_template.*`) und O(N)-Listen-Endpoints, die vollständige Ergebnismengen vor der Paginierung materialisieren. Empfehlung: Zuerst die fünf Quick-Wins (alle P1/S, je < 1 Tag) umsetzen, dann Outbox-Consumer, Async-Pfad und SSE-Transport als P1/M-Block, bevor neue Features gebaut werden.

---

## Kapitel 1: Frontend (React 18 / TypeScript)

| # | Vorschlag | Kategorie | Aufwand | Priorität | Datei:Zeile |
|---|-----------|-----------|---------|-----------|-------------|
| FE-1 | Prod-Build reparieren: `package-lock.json` in Image kopieren, `npm ci` statt `npm ci --only=production` (devDeps `tsc`/`vite` werden für `npm run build` benötigt) | Build | S | P1 | `frontend/Dockerfile:8,24` |
| FE-2 | `eslint-plugin-react-hooks` installieren und aktivieren (`rules-of-hooks`, `exhaustive-deps`) — aktuell keinerlei Hook-Prüfung | Qualität | S | P1 | `frontend/eslint.config.js`, `frontend/package.json:30-48` |
| FE-3 | State-Management vereinheitlichen: React Query ist installiert, wird aber nur in ~4 Dateien genutzt; Rest sind handgerollte Fetch-Hooks | Architektur | L | P2 | `frontend/src/queries/*`, `frontend/src/components/*/use*Data.ts` |
| FE-4 | Fünffach dupliziertes `use*Data`-Hook-Muster durch generisches `useEntityData<T>` ersetzen | DRY | M | P2 | `useAdrData.ts`, `useRiskData.ts`, `useIssueData.ts`, `useNeedData.ts`, `useArchitectureData.ts` |
| FE-5 | Monster-Komponenten zerlegen (5 Dateien ≥ 1000 Zeilen) | Architektur | L | P2 | `CanvasEditor.tsx` (1605), `IcdView.tsx` (1483), `BaselinesView.tsx` (1461), `DiagramView.tsx` (1036), `TestRunsList.tsx` (1000) |
| FE-6 | Fetch-Hooks ohne Cleanup: `AbortController` + Unmount-Guard ergänzen (Race Conditions, setState nach Unmount) | Korrektheit | M | P2 | z.B. `frontend/src/components/AdrEditors/useAdrData.ts:13-43` |
| FE-7 | `error`-State wird nach erfolgreichem Reload nie zurückgesetzt — Fehlermeldung bleibt kleben | Korrektheit | S | P2 | `useAdrData.ts:20` (Muster in allen 5 Hooks) |
| FE-8 | 401 und 403 werden identisch behandelt: Berechtigungsfehler (403) loggt den User aus statt "keine Berechtigung" anzuzeigen | UX | S | P2 | `frontend/src/api/client.ts:64-74` |
| FE-9 | Auth-Token in `sessionStorage` ist XSS-lesbar; auf httpOnly-Cookie oder reines In-Memory + Refresh umstellen | Security | M | P2 | `frontend/src/context/AuthContext.tsx:93,149` |
| FE-10 | Testabdeckung: 35 Testdateien für ~160 Quelldateien; die größten Views (`IcdView`, `DiagramView`, `BaselinesView`, `ArtifactDiff`, `TraceabilityView`) sind ungetestet | Test | L | P2 | `frontend/src/**/*.test.tsx` |
| FE-11 | Code-Splitting via `React.lazy` für schwere Abhängigkeiten (`mermaid` ~2 MB, `fabric`) — aktuell ein monolithisches Bundle | Performance | M | P2 | `frontend/src/App.tsx`, `DiagramView.tsx`, `CanvasEditor.tsx` |
| FE-12 | i18n-Torso: `i18next`/`react-i18next` sind deklariert, `useTranslation` wird nur in 3 Komponenten genutzt — entweder konsequent ausrollen oder Dependency entfernen | DRY/DX | M | P2 | `frontend/package.json:21,26`, `ImpactView.tsx`, `TestcaseList.tsx` |
| FE-13 | Accessibility systematisieren: nur 20 `aria-`/`role`-Treffer in 10 von 117 Komponenten-Dateien; `eslint-plugin-jsx-a11y` fehlt komplett | A11y | M | P2 | `frontend/eslint.config.js` |
| FE-14 | Listen-Virtualisierung für große Artefakt-Listen (verschärft durch O(N)-Backend-Paginierung, s. BE-3) | Performance | M | P3 | `RequirementList.tsx:259`, `NeedList.tsx:270` u.a. |
| FE-15 | Memoization in Hot-Paths: `React.memo`/`useMemo` nur in 15 von 117 Komponenten-Dateien | Performance | M | P3 | `frontend/src/components/**` |
| FE-16 | Typ-Löcher schließen: `undefined as unknown as T`, `as Record<string, string>`-Header-Cast | Typsicherheit | S | P3 | `frontend/src/api/client.ts:47,93` |
| FE-17 | ESLint-Versions-Inkonsistenz: Config-Kommentar behauptet "ESLint 9 flat config", `package.json` pinnt `eslint ^8.57.0`, `globals ^17.7.0` setzt neuere Node-Umgebung voraus | DX | S | P3 | `frontend/eslint.config.js:1-2`, `frontend/package.json:42-43` |
| FE-18 | Prettier + Format-Check einführen (aktuell keine Formatter-Konfiguration) | DX | S | P3 | `frontend/` |
| FE-19 | Test-Layout vereinheitlichen: Tests liegen teils co-located (`components/**/**.test.tsx`), teils zentral (`src/test/`), teils als `api/*.test.ts` | DX | S | P3 | `frontend/src/test/`, `frontend/src/components/` |
| FE-20 | `fabric`-Mock-Alias nur in Vitest-Config — Prod-Typprüfung und Test-Realität divergieren; Contract-Test gegen echtes fabric ergänzen | Test | M | P3 | `frontend/vite.config.ts:34-38`, `frontend/src/__mocks__/fabric.ts` |

### 1.1 Komponenten-Architektur

Die Feature-Ordnerstruktur (`components/<Feature>/`) ist grundsätzlich sauber, aber die Größenverteilung ist extrem: 5 Komponenten überschreiten 1000 Zeilen (FE-5), weitere 8 liegen über 500 Zeilen (`WorkspaceSettings.tsx` 790, `TraceabilityView.tsx` 802, `SidebarNavigation.tsx` 821, `DecompositionTree.tsx` 835, `TraceLinksForm.tsx` 705, `CreateTraceLinkDialog` 656, `ArchitectureForm.tsx` 640, `MetricsDashboard.tsx` 631). Diese Dateien mischen Datenladen, lokalen UI-State, Formular-Logik und Rendering. Zielbild: Container/Presenter-Trennung, Extraktion der Fetch-Logik in Query-Hooks (siehe 1.2).

### 1.2 State Management

Zwei konkurrierende Paradigmen koexistieren:

- **React Query** (`@tanstack/react-query ^5.101.2`): genutzt in `src/queries/requirements.ts`, `src/queries/testcases.ts`, `src/queries/queryClient.ts` und `useRequirementData.ts`.
- **Handgerollte Hooks**: `useAdrData`, `useRiskData`, `useIssueData`, `useNeedData`, `useArchitectureData`, `useDashboardData`, `useTestCaseData` — strukturell nahezu identische ~50-Zeilen-Kopien (FE-4) mit `useState` + `useEffect`, ohne Caching, ohne Deduplizierung, ohne Abort-Handling (FE-6), mit klebendem Error-State (FE-7).

Die Migration auf React Query eliminiert FE-4, FE-6 und FE-7 gleichzeitig und ist deshalb der wirksamste einzelne Frontend-Refactor.

### 1.3 Typsicherheit

TypeScript strict mode ist aktiv, aber an den API-Rändern wird gecastet statt validiert: `response.json() as Promise<T>` (`client.ts:96`) vertraut dem Backend blind; `undefined as unknown as T` bei 204-Responses (`client.ts:93`) verschiebt Null-Fehler zur Laufzeit. Empfehlung: leichtgewichtige Runtime-Validierung (zod) an den API-Grenzen, mindestens für die Kern-Entitäten — idealerweise generiert aus dem vorhandenen OpenAPI-Schema (drf-spectacular).

### 1.4 Performance

Kein Code-Splitting: `mermaid` (11.x) und `fabric` (6.x) landen im Haupt-Bundle, obwohl sie nur in Diagramm-Views gebraucht werden (FE-11). Keine Listen-Virtualisierung (FE-14) — kombiniert mit der Backend-O(N)-Paginierung (BE-3) skaliert die Requirements-Ansicht doppelt schlecht. Memoization ist punktuell vorhanden (68 Treffer in 15 Dateien), aber in den größten Render-Bäumen (`BaselinesView`, `IcdView`) fehlt sie weitgehend (FE-15).

### 1.5 Testabdeckung

35 Testdateien bei ~160 Nicht-Test-Quelldateien (FE-10). Gut abgedeckt: Shared-Komponenten (`tag-input`, `trace-link-display`, `workspace-tree`, `CreateTraceLinkDialog`), WorkspaceSettings-Sektionen, Canvas-Editor. Blind: die fünf größten Views, `ArtifactDiff` (536 Zeilen, sicherheitsrelevante Diff-Darstellung), `ReqTraceLinkPanel` (589 Zeilen), sämtliche `use*Data`-Hooks. Die Vitest-Suite läuft zudem nicht in CI (siehe INF-2).

### 1.6 Accessibility

Keine A11y-Strategie erkennbar: 20 `aria-`/`role`-Attribute im gesamten Komponentenbaum, kein `eslint-plugin-jsx-a11y`, keine Fokus-Verwaltung in den Modal-Implementierungen (`ModalDialogBase.tsx` 244 Zeilen — kein Focus-Trap-Hinweis gefunden). Für ein Tool mit formalen SE-Workflows (Behörden-/Enterprise-Kontext) ist WCAG-Konformität absehbar eine Anforderung (FE-13).

### 1.7 Code-Duplizierung / DRY

Neben dem `use*Data`-Muster (FE-4) wiederholen sich List/Form/Editors-Triple pro Entität (`AdrList`/`AdrForm`/`AdrEditors`, `RiskList`/`RiskForm`/`RiskEditors`, `IssueList`/`IssueForm`/`IssueEditors`, `NeedList`/`NeedForm`/`NeedsEditors`) mit fast identischer Struktur (100–320 Zeilen je Datei). Ein generisches `EntityCrudView<T>`-Muster mit Konfigurationsobjekt würde ~2000 Zeilen eliminieren und neue Entitätstypen (Ontologie-Erweiterung) drastisch verbilligen.

### 1.8 Developer Experience

Kein Prettier (FE-18), Lint läuft nur lokal (`npm run lint` existiert, kein CI-Hook, siehe INF-2), inkonsistentes Test-Layout (FE-19), ESLint-Versionswirrwarr (FE-17). Der `fabric`-Stub nur im Test-Alias (FE-20) bedeutet: Canvas-Tests testen den Mock, nicht die Bibliothek.

---

## Kapitel 2: Infrastruktur & DevOps

| # | Vorschlag | Kategorie | Aufwand | Priorität | Datei:Zeile |
|---|-----------|-----------|---------|-----------|-------------|
| INF-1 | Frontend-Prod-Stage: Lockfile kopieren + `npm ci` fixen (Details FE-1), zusätzlich `build.args` für `VITE_*` durchreichen | Build | S | P1 | `frontend/Dockerfile:8,24`, `docker-compose.yml:150-153` |
| INF-2 | CI-Pipeline für Backend-pytest, Frontend-Vitest und Lint anlegen — einziger Workflow ist Playwright-E2E | CI/CD | M | P1 | `.github/workflows/` (nur `playwright.yml`) |
| INF-3 | Backend-Prod-Kommando: `runserver` durch gunicorn/uvicorn ersetzen (CMD und Compose-Command), `collectstatic` aktivieren | Deployment | M | P1 | `backend/Dockerfile:26,32`, `docker-compose.yml:100-102` |
| INF-4 | Source-Bind-Mounts (`./backend:/app`) aus der "Production-Ready"-Compose entfernen — gehören in `docker-compose.override.yml` | Deployment | S | P1 | `docker-compose.yml:91-92,128-129` |
| INF-5 | Postgres/Redis-Ports nicht auf den Host publishen (Widerspruch zum eigenen Security-Kommentar Zeile 24) | Security | S | P1 | `docker-compose.yml:39-40,54-55` |
| INF-6 | Celery-Beat-Service ergänzen — ohne ihn läuft der Outbox-Consumer (BE-1) nie, ebenso wenig andere periodische Tasks | Deployment | S | P1 | `docker-compose.yml` (Service fehlt) |
| INF-7 | nginx.conf für SPA-Routing (History-Fallback auf `index.html`) — Deep-Links liefern derzeit 404 | Deployment | S | P1 | `frontend/Dockerfile:35-36` (TODO im Code) |
| INF-8 | Redis absichern: `requirepass`, `maxmemory`+Policy, Persistenz (AOF) für Broker-Zuverlässigkeit | Security | S | P2 | `docker-compose.yml:51-61` |
| INF-9 | Unsichere Defaults entfernen: `DB_PASSWORD:-reqflow` fällt still auf Trivial-Passwort zurück — Fail-Fast statt Default | Security | S | P2 | `docker-compose.yml:36,78,119` |
| INF-10 | `USER`-Direktive in beiden Dockerfiles — Container laufen als root | Security | S | P2 | `backend/Dockerfile`, `frontend/Dockerfile` |
| INF-11 | Healthchecks für backend/celery definieren; `frontend.depends_on` ohne `condition` wartet nicht auf Backend-Readiness | Robustheit | S | P2 | `docker-compose.yml:66-102,142-157` |
| INF-12 | Backend-Dockerfile multi-stage: `gcc`/`libpq-dev` verbleiben im Runtime-Image (~150 MB Overhead, Angriffsfläche) | Build | M | P2 | `backend/Dockerfile:13-16` |
| INF-13 | Secrets nicht als Compose-Env (via `docker inspect` lesbar) — Docker Secrets oder env_file mit klarer Trennung | Security | M | P2 | `docker-compose.yml:73,115` |
| INF-14 | Observability-Grundausstattung: strukturierte JSON-Logs, `django-prometheus` oder OTel-Instrumentierung, Celery-Task-Metriken — aktuell nichts davon vorhanden | Observability | L | P2 | `backend/reqflow/settings.py`, `docker-compose.yml` |
| INF-15 | Migration aus dem Container-Startkommando lösen (Race bei mehreren Replicas) — dedizierter Init-/Job-Schritt | Deployment | S | P2 | `docker-compose.yml:100-102` |
| INF-16 | CI: `loaddata initial_data \|\| true` schluckt Fixture-Fehler still — Fehler sichtbar machen | CI/CD | S | P2 | `.github/workflows/playwright.yml:65` |
| INF-17 | Node-Versionsdrift: Docker baut mit node:22, CI testet mit node 20 | CI/CD | S | P3 | `frontend/Dockerfile:4`, `.github/workflows/playwright.yml:86` |
| INF-18 | Image-Versionen härten: `nginx:alpine` und `node:22-slim` ohne Digest/Minor-Pin | Build | S | P3 | `frontend/Dockerfile:4,31` |
| INF-19 | E2E-CI läuft gegen Vite-Dev-Server statt Prod-Build — Prod-Regression (wie INF-1!) bleibt unsichtbar | CI/CD | M | P3 | `.github/workflows/playwright.yml:94-98` |
| INF-20 | Dependabot/Renovate für Python- und npm-Dependencies aktivieren | Wartung | S | P3 | `.github/` |
| INF-21 | Backup-Strategie für `postgres_data`-Volume dokumentieren/automatisieren (pg_dump-Sidecar oder Cron) | Betrieb | M | P3 | `docker-compose.yml:159-160` |
| INF-22 | `restart: unless-stopped` + fehlendes Log-Rotation-Limit (`logging.options.max-size`) — Log-Volumes wachsen unbegrenzt | Betrieb | S | P3 | `docker-compose.yml:32,53,70` |

### 2.1 Docker Compose

Die Datei nennt sich "Production-Ready Configuration" (`docker-compose.yml:2`), widerspricht dem aber in vier Punkten: `runserver` als Backend-Command (:100-102), Source-Bind-Mounts (:91-92, :128-129), host-exponierte Datenbank-Ports (:39-40, :54-55) und Trivial-Passwort-Defaults (:36). Kritisch für die Domänen-Logik: **Es existiert kein `celery-beat`-Service** (INF-6) — periodische Tasks können nie feuern, was direkt den fehlenden Outbox-Consumer (BE-1) zementiert.

### 2.2 Dockerfiles

- **Frontend** (`frontend/Dockerfile`): Der Builder-Stage fehlt das `package-lock.json` (nur `package.json` wird in Zeile 8 kopiert) — `npm ci` in Zeile 24 bricht damit hart ab. Selbst mit Lockfile würde `--only=production` `tsc` und `vite` weglassen, die `npm run build` (Zeile 28) benötigt. **Das Production-Target ist seit Erstellung nicht baubar.** Zusätzlich fehlt die nginx-SPA-Konfiguration (Zeile 35 ist ein TODO), und `VITE_API_BASE_URL` wird als Runtime-Env gesetzt (`docker-compose.yml:152`), obwohl Vite-Variablen Build-Zeit-Konstanten sind — im Prod-Image wirkungslos.
- **Backend** (`backend/Dockerfile`): Single-Stage mit `gcc` im Runtime-Image, `collectstatic` auskommentiert, CMD ist der Django-Dev-Server, kein `USER`.

### 2.3 CI/CD

Einziger Workflow: `playwright.yml` (E2E). Es gibt **keine CI für die 1042 Backend-pytest-Tests, keine für Vitest, keine für ESLint/mypy** (INF-2). Der E2E-Lauf testet zudem den Vite-Dev-Server, nicht den Prod-Build (INF-19) — deshalb konnte der defekte Prod-Build unbemerkt bleiben. Kein Build-and-Push der Docker-Images, kein Release-Workflow.

### 2.4 Secrets-Handling

`.env.example` existiert und `.env` ist gitignored (gut). Aber: Alle Secrets fließen als Compose-Environment in die Container (via `docker inspect` lesbar, INF-13), `DB_PASSWORD` hat einen stillen Trivial-Default (INF-9), Redis ist unauthentifiziert (INF-8). Die LLM/MCP-spezifischen Klartext-Secret-Probleme (API-Key in Redis, Provider-Key in Postgres) sind in Kapitel 4 (F6.4) dokumentiert.

### 2.5 Observability

Keinerlei Metriken-, Tracing- oder Log-Aggregations-Infrastruktur (INF-14). Für ein System mit Async-Pfaden (Celery), Event-Bus (Outbox) und externen LLM-Calls ist das betrieblich blind: Der tote Async-LLM-Pfad (F4.1) und der fehlende Outbox-Consumer (BE-1) wären mit einer simplen Queue-Depth-Metrik sofort aufgefallen. Minimalempfehlung: strukturierte JSON-Logs, `/metrics`-Endpoint, Celery-Task-Erfolgs-/Latenz-Metriken, Outbox-Backlog-Gauge.

### 2.6 Skalierbarkeit

`runserver` ist single-threaded — bereits ein einzelner synchroner LLM-Call (bis 30 s, F5.2) blockiert die gesamte Instanz. SSE-Verbindungen über runserver/gunicorn-sync-Worker binden je einen Worker dauerhaft; für den SSE-Transport ist ein ASGI-Deployment (uvicorn/daphne) nötig. Kein Konzept für horizontale Skalierung (Sticky-Sessions für SSE, Celery-Concurrency, Postgres-Connection-Pooling via pgbouncer).

### 2.7 Developer Experience

Positiv: `docker-compose.override.yml` für Dev-Hot-Reload, Healthchecks für postgres/redis, gut kommentierte Compose-Datei. Lücken: kein `Makefile`/`justfile` für Standard-Kommandos, keine pre-commit-Hooks, Node-Versionsdrift zwischen CI und Image (INF-17), kein Dependabot (INF-20).

---

## Kapitel 3: Backend-Vertiefung (über SYSTEM_AUDIT.md hinaus)

| # | Vorschlag | Kategorie | Aufwand | Priorität | Datei:Zeile |
|---|-----------|-----------|---------|-----------|-------------|
| BE-1 | Outbox-Consumer anbinden: `poll_and_dispatch()` als Celery-Beat-Task registrieren — wird derzeit von keinem Task/Beat/Command aufgerufen | Korrektheit | M | P1 | `backend/application/event_bus.py:242` |
| BE-2 | Django `CACHES` konfigurieren (Redis-Backend) — Root-Cause der 4 In-Process-Caches | Architektur | S | P1 | `backend/reqflow/settings.py` |
| BE-3 | `BaseEntityViewSet._paginate` materialisiert vollständige Listen vor der Paginierung — auf QuerySet-Slicing/DRF-Paginator umstellen | Performance | M | P1 | `backend/rest_api/views.py:160` |
| BE-4 | SSE-PubSub: Redis-Connection-Pool statt neuer Connection pro Call | Performance | S | P1 | `backend/mcp_server/sse_pubsub.py:31-49` |
| BE-5 | Roh-API-Key als Redis-Value ablösen (Hash statt Klartext) — schwächt sonst den REQ-018-Fix | Security | S | P1 | `backend/mcp_server/sse_pubsub.py:33` |
| BE-6 | pytest auf dedizierte Test-Settings umstellen (läuft aktuell gegen Prod-Settings) | Test | S | P1 | `backend/pyproject.toml` |
| BE-7 | Cache-Invalidierungs-Strategie für alle 4 In-Process-Caches definieren (Signal-basiert oder TTL) — aktuell stale Daten über Prozessgrenzen | Korrektheit | M | P1 | Folge von BE-2 |
| BE-8 | Composite-Indexes für häufige Filterkombinationen (tenant+workspace+type, tenant+status) ergänzen | Performance | M | P1 | `backend/persistence/models.py` |
| BE-9 | Multi-Worker-Konsistenz absichern: In-Process-Caches + fehlende Invalidierung machen jedes Deployment mit >1 Worker inkonsistent — bis BE-2/BE-7 umgesetzt sind, Deployment-Constraint dokumentieren | Korrektheit | S | P1 | `backend/reqflow/settings.py` |
| BE-10 | Service-Layer-Grenzen schärfen: Application-Services delegieren Queries nicht konsequent an Repositories (direkte ORM-Zugriffe im Service-Code) | Architektur | L | P2 | `backend/application/**` |
| BE-11 | `factory-boy` ist deklariert, wird aber nirgends genutzt — entweder Fixtures darauf migrieren oder Dependency streichen | Test | S | P2 | `backend/requirements.txt`, `backend/**/tests/` |
| BE-12 | `conftest.py`-Fossil bereinigen (tote Fixtures/Konfiguration) | Test | S | P2 | `backend/conftest.py` |
| BE-13 | Outbox-Monitoring: Backlog-Größe und DLQ-Umfang als Metrik/Log exponieren (Folge von BE-1, verhindert stilles Liegenbleiben) | Observability | S | P2 | `backend/application/event_bus.py` |
| BE-14 | List-Endpoints: `select_related`/`prefetch_related`-Audit für alle 16 ViewSets (N+1 in Serializern) | Performance | M | P2 | `backend/rest_api/views.py`, `serializers.py` |
| BE-15 | API-Fehlerformat-Konsistenz zwischen DRF-Endpoints und MCP-Fehlern herstellen (gemeinsames Error-Envelope) | API-Design | M | P2 | `backend/rest_api/`, `backend/mcp_server/protocol_handler.py` |
| BE-16 | Celery-Task-Idempotenz prüfen: Outbox-Dispatch (BE-1) braucht at-least-once-taugliche, idempotente Handler | Korrektheit | M | P2 | `backend/application/event_bus.py` |
| BE-17 | Transaktionsgrenzen dokumentieren: welche Service-Methoden laufen in `atomic()`, welche Events feuern vor/nach Commit | Architektur | M | P2 | `backend/application/**` |
| BE-18 | DB-Query-Logging/`django-silk` in Dev aktivieren, um O(N)- und N+1-Regressionen sichtbar zu machen | DX | S | P2 | `backend/reqflow/settings.py` |
| BE-19 | Test-Pyramide rebalancieren: Repository-Tests gegen echte DB, Service-Tests mit Repository-Fakes — aktuell dominieren End-to-End-artige API-Tests | Test | L | P2 | `backend/**/tests/` |
| BE-20 | Paginierungs-Verträge vereinheitlichen (Cursor vs. Offset) und in OpenAPI-Schema dokumentieren | API-Design | M | P2 | `backend/rest_api/views.py:160` |
| BE-21 | Celery-Routing/Queues definieren (llm, events, default) statt Single-Queue — Voraussetzung für getrennte Skalierung | Async | M | P2 | `backend/reqflow/celery.py` |
| BE-22 | Read-Model für Traceability-Matrix erwägen (materialisierte Sicht statt Live-Graph-Traversierung) | Performance | L | P3 | `backend/application/` |

### 3.1 Service-Layer & Architektur-Grenzen

Die Schichtung Domain → Application → Persistence/REST ist angelegt, aber undicht: Application-Services greifen für Queries teils direkt aufs ORM zu, statt an Repositories zu delegieren (BE-10). Das macht die Repository-Abstraktion halbherzig — sie kann weder für Tests gemockt noch für Caching zentralisiert werden. Zusammen mit unklaren Transaktionsgrenzen (BE-17) ist nicht garantiert, dass Domain-Events (Outbox) konsistent zum Commit geschrieben werden — der atomare DLQ-Fix (REQ-021) adressierte ein Symptom dieser Unschärfe.

### 3.2 Caching-Strategie

**Root-Cause-Befund:** `CACHES` ist in `backend/reqflow/settings.py` komplett unkonfiguriert (BE-2). Django fällt damit auf `LocMemCache` zurück — pro Prozess, unsynchronisiert. Die im SYSTEM_AUDIT identifizierten 4 In-Process-Caches sind die direkte Folge: Entwickler bauten eigene Modul-Level-Caches, weil kein geteilter Cache existiert. Konsequenzen:

1. Jeder Gunicorn-/Celery-Worker hält eigene, divergierende Cache-Stände (BE-9).
2. Es gibt keine Invalidierungs-Strategie (BE-7) — Schreiboperationen eines Workers sind für andere unsichtbar, bis der Prozess stirbt.

Fix-Reihenfolge: Redis-`CACHES` konfigurieren (S) → In-Process-Caches auf `django.core.cache` migrieren → Signal-basierte Invalidierung bei Model-Save/Delete.

### 3.3 Datenbank & ORM

`BaseEntityViewSet._paginate` (`backend/rest_api/views.py:160`) materialisiert die **vollständige** Ergebnisliste (Python-Liste), bevor paginiert wird — jeder List-Endpoint aller 16 ViewSets ist damit O(N) in Speicher und Zeit (BE-3). Bei wachsenden Artefaktbeständen (Extended-Rigor-Projekte mit tausenden Requirements) degradiert das linear. Zusätzlich fehlen Composite-Indexes für die dominanten Filterkombinationen (BE-8): Row-Level-Security filtert immer auf `tenant_id`, Listen fast immer zusätzlich auf `workspace`+`type`/`status` — ohne Composite-Index läuft das auf Index-Scans mit Nachfilterung hinaus.

### 3.4 Async / Celery

**Kritischster Einzelbefund des Backends:** `poll_and_dispatch()` in `backend/application/event_bus.py:242` — der Consumer der Transactional Outbox — wird von **keinem** Celery-Task, keinem Beat-Schedule und keinem Management-Command aufgerufen (BE-1). Die Outbox füllt sich, Events werden nie dispatcht, und die REQ-020/021-Fixes (atomarer DLQ-Move) laufen im Deployment schlicht nie. Kombiniert mit dem fehlenden Beat-Service in der Compose (INF-6) ist die gesamte Event-Verarbeitung inert. Fix: Beat-Task (z.B. alle 5 s) + Beat-Service + Backlog-Metrik (BE-13) + Idempotenz-Review der Handler (BE-16). Der tote Async-LLM-Pfad (F4.1) ist das zweite Symptom derselben Lücke: Async-Infrastruktur wurde gebaut, aber nie Ende-zu-Ende verdrahtet oder getestet.

### 3.5 API-Design-Konsistenz

REST-API (DRF-Error-Envelope) und MCP-Server (`{"error_code", "message"}`, F8.1) sprechen unterschiedliche Fehlerdialekte (BE-15). Paginierungsverhalten ist durch BE-3 faktisch "alles laden, dann schneiden" — der API-Vertrag (Seitengröße, Gesamtzahl, Cursor) sollte explizit definiert und im OpenAPI-Schema verankert werden (BE-20), bevor Clients sich auf das aktuelle Verhalten verlassen.

### 3.6 Test-Architektur

Drei strukturelle Mängel:

1. **pytest läuft auf Prod-Settings** (`backend/pyproject.toml`, BE-6): keine Trennung von Test- und Produktionskonfiguration — Tests erben Prod-Cache-, Celery- und LLM-Einstellungen; ein falsch gesetztes `.env` kann Testverhalten ändern.
2. **factory-boy deklariert, nie genutzt** (BE-11): Fixtures werden manuell gebaut, was die Tests verbos und brüchig macht.
3. **conftest.py-Fossil** (BE-12): tote Konfiguration, die Suchende in die Irre führt.

Dass 1042 Tests grün sind und trotzdem der Outbox-Consumer fehlt, der Async-Pfad tot ist und SSE crasht, zeigt das eigentliche Problem: Die Suite testet Funktionen in Isolation, aber keine **Verdrahtung** (Beat-Schedules, Celery-Task-Registrierung, ASGI-Dispatch). Empfehlung: eine kleine Schicht "Wiring-Tests" — prüft, dass jeder deklarierte Task registriert ist, jeder Beat-Eintrag existiert und jeder URL-Endpoint mit der konfigurierten Server-Klasse antwortet (BE-19).

---

## Kapitel 4: LLM/MCP-Integration

| # | Vorschlag | Kategorie | Aufwand | Priorität | Datei:Zeile |
|---|-----------|-----------|---------|-----------|-------------|
| F2.1 | `derive_requirements` in Anthropic/Ollama/Azure-Providern implementieren — `@abstractmethod` macht 3 von 5 Providern nicht instanziierbar (TypeError) | Korrektheit | S | P1 | `backend/llm_adapter/interface.py:136`, `providers.py:366,640,736` |
| F4.1 | Async-LLM-Pfad reparieren: Dispatcher baut ad-hoc Celery-App im Web-Prozess; Worker kennt `llm_adapter.run_capability` nicht → Message verworfen, Status ewig PENDING | Korrektheit | M | P1 | `backend/llm_adapter/dispatcher.py:66-97`, `backend/reqflow/celery.py` |
| F6.1 | RBAC-Bypass schließen: `_WRITE_TOOL_PREFIXES` fehlen `needs.*`, `adr.*`, `risk.*`, `issue.*`, `glossary.*`, `prompt_template.*` — Viewer kann schreiben; `prompt_template`-Write = persistente Prompt-Injection | Security | S | P1 | `backend/mcp_server/tool_registry.py:52-77` |
| F6.2 | SSE-GET fixen: sync `CorsMixin.dispatch` + `async def get` → TypeError bei jedem `GET /mcp/sse/`; API-Key-Check beim Handshake ergänzen (DoS-Vektor) | Korrektheit/Security | M | P1 | `backend/mcp_server/views.py:62-78` |
| F1.2 | `requirement.validate` reparieren: Aufruf `validate_artifact(str(req_id), ctx=auth_context)`, Facade erwartet nur `artifact_id` → immer TypeError | Korrektheit | S | P1 | `backend/mcp_server/tools/requirements.py:425` |
| F3.1 | Provider-Prompts enthalten nur UUIDs, keinen Artefakt-Inhalt — LLM halluziniert bei decompose/validate/check_consistency zwangsläufig | Korrektheit | M | P1 | `backend/llm_adapter/providers.py:431,541,621,717,810` |
| F8.1 | JSON-RPC-Error-Format auf Spec bringen: `{"code": <int>, "message": <str>}` statt `{"error_code": "...", "message": "..."}` — Standard-MCP-Clients sonst inkompatibel | Protokoll | S | P1 | `backend/mcp_server/protocol_handler.py:154-165` |
| F2.2/F2.3 | Interface-Vertrag vervollständigen: `complete()` nicht im Interface; OpenAI-`derive_requirements` defekt (`self._model` AttributeError, Layer-Verletzung, `print` statt logger) | Korrektheit | M | P1 | `backend/llm_adapter/interface.py`, `providers.py` |
| F4.3 | Stillen Mock-Fallback bei LLM-Fehler entfernen oder Ergebnis explizit als Mock markieren — unmarkierter Fake-Content im Requirements-Tool ist fachlich gefährlich | Korrektheit | S | P2 | `backend/application/ai_derivation_service.py:342-345` |
| F1.1 | Echte Input-Schemas für 11 von 14 Tool-Gruppen (Fallback `{"kwargs": {"type": "object"}}` gibt Clients keine Parameter-Information) | API-Design | M | P2 | `backend/mcp_server/tools/base.py:125-146` |
| F6.3 | Prompt-Injection-Oberfläche reduzieren: User-Content ungefiltert im Prompt — Delimiter/Escaping/Instruction-Hierarchie einführen | Security | M | P2 | `backend/llm_adapter/providers.py` (alle Prompt-Builder) |
| F6.4 | Klartext-Secrets beseitigen: API-Key in Redis, Provider-`api_key` in Postgres, Key via Query-Param in Logs, CORS `*`+Credentials | Security | M | P2 | `backend/mcp_server/sse_pubsub.py:33`, `backend/persistence/models.py:1217` |
| F4.2 | Retry/Circuit-Breaker für LLM-Calls — das vorhandene `backend/resilience/`-Modul wird nicht genutzt | Robustheit | M | P2 | `backend/resilience/`, `llm_adapter/providers.py` |
| F4.4 | Tenant-LLM-Settings in Celery-Worker propagieren — per-Tenant-Konfiguration wirkt nur im Sync-Pfad | Korrektheit | M | P2 | `backend/llm_adapter/dispatcher.py` |
| F5.2 | Sync-LLM-Call blockiert Request-Thread bis 30 s (Gunicorn-Worker-Erschöpfung) — nach F4.1-Fix auf Async-Pfad umlenken | Performance | M | P2 | `backend/llm_adapter/` |
| F7.1/F7.2 | Contract-Tests für Provider; SSE-E2E-Tests testen tote API (POST statt GET) — gegen echten Transport neu schreiben | Test | M | P2 | `backend/mcp_server/tests/` |
| F8.2/F8.4 | Tool-Fehler als `isError`-Result gemäß MCP-Spec; Thread-per-Message durch Pool ersetzen + Body-Race beheben | Protokoll/Robustheit | M | P2 | `backend/mcp_server/protocol_handler.py`, `views.py` |
| F5.1 | Response-Caching für identische Derivation-Anfragen (Prompt-Hash → Ergebnis) | Performance | M | P3 | `backend/application/ai_derivation_service.py` |
| F5.3 | Token-Usage pro Tenant aggregieren und limitieren (wird nur geloggt) | Betrieb | M | P3 | `backend/llm_adapter/` |
| F8.3 | SSE at-most-once: Event-ID + `Last-Event-ID`-Replay einführen | Protokoll | M | P3 | `backend/mcp_server/sse_pubsub.py` |
| F8.5 | Kleinigkeiten: Response auf `notifications/initialized`, hartkodierte `protocolVersion`, unbounded PresetCache, `list_tools` ignoriert RBAC | Protokoll | S | P3 | `backend/mcp_server/protocol_handler.py`, `tool_registry.py` |

### 4.1 MCP Server & Tool-Definitionen

Die 40+ Tools in 14 Gruppen sind funktional breit, aber protokollseitig lückenhaft. **F1.1:** 11 der 14 Tool-Gruppen liefern kein echtes Input-Schema — `tools/base.py:125-146` fällt auf `{"kwargs": {"type": "object"}}` zurück. Ein MCP-Client (Claude, Cursor etc.) sieht damit keinerlei Parameternamen oder -typen und muss raten. **F1.2:** `requirement.validate` ist seit jeher defekt: `tools/requirements.py:425` ruft `validate_artifact(str(req_id), ctx=auth_context)` auf, die Facade akzeptiert nur `artifact_id` — jeder Aufruf endet im TypeError. Dass das nie auffiel, bestätigt die Contract-Test-Lücke (F7.1).

### 4.2 Provider-Abstraktion

Der Interface-Vertrag ist gebrochen. `derive_requirements` wurde als `@abstractmethod` in `llm_adapter/interface.py:136` deklariert, aber nur `MockLlmProvider` und `OpenAiProvider` implementieren es — **Anthropic (`providers.py:366`), Ollama (`providers.py:640`) und Azure (`providers.py:736`) werfen beim Instanziieren TypeError** (F2.1). Da der Default-Provider `mock` ist, blieb das unbemerkt: Jede Installation, die `LLM_PROVIDER=anthropic` oder `ollama` setzt, bricht sofort. Zusätzlich (F2.2/F2.3): `complete()` existiert auf Providern, ist aber nicht Teil des Interfaces (kein statischer Vertrag), und die einzige "echte" `derive_requirements`-Implementierung (OpenAI) ist selbst defekt — Zugriff auf nicht existentes `self._model`, Layer-Verletzung durch direkten Persistence-Zugriff und `print`-Debugging statt Logger.

### 4.3 AI-Derivation & Prompts

**F3.1:** Die Prompt-Builder der Provider (`providers.py:431,541,621,717,810`) interpolieren nur Artefakt-**UUIDs**, nie den Artefakt-Inhalt. Ein LLM, das "decompose requirement 3f2a…" ohne den Requirement-Text erhält, kann nur halluzinieren — decompose, validate und check_consistency liefern strukturell erfundene Ergebnisse. **F4.3:** Verschärfend fällt `ai_derivation_service.py:342-345` bei jedem LLM-Fehler **still** auf den Mock-Provider zurück: Der Nutzer erhält unmarkierten Fake-Content in einem Requirements-Werkzeug, dessen Kernversprechen Nachvollziehbarkeit ist. Mindestfix: Fallback-Ergebnisse als `"provider": "mock-fallback"` kennzeichnen und im UI ausweisen; besser: Fehler propagieren.

### 4.4 Robustheit

**F4.1 (P1):** Der Async-Pfad ist Ende-zu-Ende tot. `dispatcher.py:66-97` instanziiert eine **neue ad-hoc Celery-App im Web-Prozess** und sendet `llm_adapter.run_capability` — ein Task-Name, den der tatsächliche Worker (`reqflow/celery.py`) nie registriert hat. Der Broker nimmt die Message an, der Worker verwirft sie, der Status bleibt ewig PENDING. Weitere Lücken: kein Retry/Circuit-Breaker trotz vorhandenem, ungenutztem `backend/resilience/`-Modul (F4.2); Tenant-LLM-Settings erreichen den Worker nicht — per-Tenant-Provider-Konfiguration wirkt nur im Sync-Pfad (F4.4); der Sync-Pfad wiederum blockiert den Request-Thread bis zu 30 s (F5.2) und kann bei wenigen parallelen Derivations die Gunicorn-Worker erschöpfen.

### 4.5 Security

Vier Befunde, davon einer kritisch:

- **F6.1 (P1) — RBAC-Bypass:** `tool_registry.py:52-77` klassifiziert Schreib-Tools per Prefix-Liste; `needs.*`, `adr.*`, `risk.*`, `issue.*`, `glossary.*` und `prompt_template.*` fehlen. Ein API-Key mit Viewer-Rolle kann darüber Daten schreiben. Besonders kritisch: `prompt_template.*`-Write erlaubt **persistente Prompt-Injection** — ein Viewer kann Templates manipulieren, die später mit höheren Rechten durch das LLM laufen.
- **F6.2 (P1) — SSE-Handshake:** `views.py:62-78` kombiniert synchrones `CorsMixin.dispatch` mit `async def get` → TypeError bei jedem `GET /mcp/sse/`. Zusätzlich fehlt der API-Key-Check beim Handshake — unauthentifizierte Verbindungsversuche binden Ressourcen (DoS-Vektor).
- **F6.3:** User-Content fließt ungefiltert und ohne Delimiter in Prompts — klassische Injection-Oberfläche.
- **F6.4:** Roh-API-Key als Redis-Value (`sse_pubsub.py:33`, schwächt den REQ-018-Hash-Fix), Provider-`api_key` im Klartext in Postgres (`persistence/models.py:1217`), Key via Query-Param (landet in Access-Logs), CORS `*` in Kombination mit Credentials.

### 4.6 Testbarkeit & MCP-Transport

**F7.1/F7.2:** Es existieren keine Contract-Tests, die Provider gegen den Interface-Vertrag prüfen (hätte F2.1 sofort gefangen), und die SSE-E2E-Tests testen eine tote API-Form (POST statt GET) — sie sind grün, weil sie den crashenden Code-Pfad (F6.2) nie betreten. Transportseitig: Tool-Fehler werden als JSON-RPC-Error statt als `isError`-Tool-Result gemeldet (F8.2, Spec-Abweichung), pro Message wird ein unbegrenzter Thread gestartet inkl. Body-Read-Race (F8.4), SSE liefert at-most-once ohne Event-IDs/Replay (F8.3). Dazu Kleinteiliges (F8.5): Response auf die Notification `notifications/initialized` (Notifications erwarten keine Antwort), hartkodierte `protocolVersion`, unbounded PresetCache, `list_tools` ignoriert RBAC (Viewer sieht Schreib-Tools, die er — nach F6.1-Fix — nicht aufrufen darf).

---

## Priorisierte Gesamt-Roadmap

### Quick-Wins (P1, Aufwand S — umsetzbar in < 1 Tag)

| # | Maßnahme | Layer | Referenz |
|---|----------|-------|----------|
| 1 | **Frontend-Prod-Build fixen**: `package-lock.json` kopieren + `npm ci` (ohne `--only=production`) | Frontend/Infra | `frontend/Dockerfile:8,24` |
| 2 | **Anthropic/Ollama/Azure-Provider instanziierbar machen**: `derive_requirements` implementieren | LLM | `backend/llm_adapter/providers.py:366,640,736` |
| 3 | **RBAC-Bypass schließen**: `needs/adr/risk/issue/glossary/prompt_template.*` in `_WRITE_TOOL_PREFIXES` aufnehmen | MCP/Security | `backend/mcp_server/tool_registry.py:52-77` |
| 4 | **JSON-RPC-Error-Format auf Spec bringen**: `{"code": <int>, "message": <str>}` | MCP | `backend/mcp_server/protocol_handler.py:154-165` |
| 5 | **`eslint-plugin-react-hooks` aktivieren** | Frontend | `frontend/eslint.config.js` |
| 6 | `requirement.validate`-TypeError beheben (Signatur-Mismatch) | MCP | `backend/mcp_server/tools/requirements.py:425` |
| 7 | Django-`CACHES` auf Redis konfigurieren (Root-Cause-Fix) | Backend | `backend/reqflow/settings.py` |
| 8 | Roh-API-Key in Redis durch Hash ersetzen | Backend/Security | `backend/mcp_server/sse_pubsub.py:33` |
| 9 | Postgres/Redis-Host-Ports schließen, Celery-Beat-Service ergänzen | Infra | `docker-compose.yml:39-40,54-55` |
| 10 | pytest auf Test-Settings umstellen | Backend | `backend/pyproject.toml` |

### Mittelfristig (P1/M und P2/S-M)

| Maßnahme | Layer | Aufwand | Referenz |
|----------|-------|---------|----------|
| Outbox-Consumer als Beat-Task verdrahten + Backlog-Metrik | Backend | M | `backend/application/event_bus.py:242` |
| Async-LLM-Pfad reparieren (Task-Registrierung im Worker, Tenant-Settings-Propagation) | LLM | M | `backend/llm_adapter/dispatcher.py:66-97` |
| SSE-GET-Crash + fehlende Handshake-Auth beheben (ASGI-sauberer Dispatch) | MCP | M | `backend/mcp_server/views.py:62-78` |
| Artefakt-Inhalt in Provider-Prompts aufnehmen | LLM | M | `backend/llm_adapter/providers.py:431-810` |
| `_paginate` auf QuerySet-Slicing umstellen + Composite-Indexes | Backend | M | `backend/rest_api/views.py:160` |
| CI-Pipeline für pytest/Vitest/Lint | Infra | M | `.github/workflows/` |
| gunicorn/uvicorn statt runserver, Source-Mounts raus, nginx-SPA-Config | Infra | M | `backend/Dockerfile:32`, `docker-compose.yml:100-102` |
| Stillen Mock-Fallback markieren/entfernen | LLM | S | `backend/application/ai_derivation_service.py:342-345` |
| Echte Tool-Input-Schemas für 11 Tool-Gruppen | MCP | M | `backend/mcp_server/tools/base.py:125-146` |
| Klartext-Secrets (Postgres/Redis/Query-Param/CORS) bereinigen | Security | M | `backend/persistence/models.py:1217` u.a. |
| Contract-Tests für Provider + echte SSE-E2E-Tests | Test | M | `backend/mcp_server/tests/` |
| `use*Data`-Hooks auf React Query migrieren (behebt FE-4/6/7 gemeinsam) | Frontend | M | `frontend/src/components/*/use*Data.ts` |
| 401/403-Unterscheidung + Error-State-Reset | Frontend | S | `frontend/src/api/client.ts:64` |
| Retry/Circuit-Breaker über vorhandenes `resilience/`-Modul | LLM | M | `backend/resilience/` |

### Langfristig / Strategisch (L-Aufwand, P2-P3)

| Maßnahme | Layer | Begründung |
|----------|-------|------------|
| State-Management-Vereinheitlichung + Monster-Komponenten-Zerlegung | Frontend | Voraussetzung für Testbarkeit und Onboarding; ~2000 Zeilen Duplikat-Eliminierung über generisches CRUD-Muster |
| Service-Layer-Grenzen schärfen (Repositories konsequent, Transaktionsgrenzen explizit) | Backend | Fundament für Caching, Testbarkeit und Event-Konsistenz |
| Observability-Stack (JSON-Logs, Metriken, Outbox-/Celery-Gauges) | Infra | Hätte 3 der 5 kritischsten Befunde (toter Async-Pfad, Outbox, SSE) im Betrieb sofort sichtbar gemacht |
| Test-Pyramide rebalancieren + "Wiring-Tests" (Task-Registrierung, Beat-Schedules, Transport-Smoke) | Backend/Test | 1042 grüne Tests haben tote Verdrahtung nicht erkannt — strukturelle Lücke, kein Mengenproblem |
| Frontend-Testabdeckung der 5 größten Views | Frontend | Größte ungetestete Fläche des Systems |
| Token-Usage-Limits pro Tenant, Derivation-Response-Caching, SSE-Replay (Event-IDs) | LLM/MCP | Betriebsreife der AI-Features für Multi-Tenant-Einsatz |
| Read-Model für Traceability-Matrix | Backend | Skalierung der Kernfunktion bei Extended-Rigor-Projekten |

---

## Statistik

| Layer | P1 | P2 | P3 | Gesamt |
|-------|----|----|-----|--------|
| Frontend | 2 | ~12 | ~6 | ~20 |
| Infrastruktur | 7 | ~9 | ~6 | ~22 |
| Backend-Vertiefung | 9 | 12 | 1 | 22 |
| LLM/MCP | 8 | 9 | 5 | 22 |
| **Gesamt** | **26** | **42** | **18** | **~86** |

**Querschnitts-Muster** (über alle Layer wiederkehrend):

1. **Gebaut, aber nie verdrahtet** — Outbox-Consumer, Async-LLM-Task, `resilience/`-Modul, React Query, factory-boy, i18next: Infrastruktur existiert, wird aber nicht angeschlossen.
2. **Dev-Pfad kaschiert Prod-Defekte** — Mock-Default-Provider, Vite-Dev-Server in CI, runserver, Source-Mounts: Der einzige je getestete Pfad ist der Entwicklungspfad.
3. **Tests messen Funktionen, nicht Systemverhalten** — grüne Suiten bei totem Async-Pfad, crashendem SSE und nicht instanziierbaren Providern.

Diese drei Muster sollten als Abnahmekriterien in die Definition of Done einfließen (z.B. "neue Async-Tasks brauchen einen Wiring-Test", "CI testet den Prod-Build").

---

## Implementierungsstatus P1 (Welle 1 — 2026-07-14)

| REQ-ID | Ref | Commit | Status |
|--------|-----|--------|--------|
| REQ-024 | FE-1/INF-1 | — | ✅ done |
| REQ-025 | FE-2 | f821c25 | ✅ done |
| REQ-026 | INF-2 | — | ✅ done |
| REQ-027 | INF-3 | 4dd71ff | ✅ done |
| REQ-028 | INF-4 | 97b6d73 | ✅ done |
| REQ-029 | INF-5 | c4b65de | ✅ done |
| REQ-030 | INF-6 | 990ddef | ✅ done |
| REQ-031 | INF-7 | 536f64b | ✅ done |
| REQ-032 | BE-1 | b7e1a56 | ✅ done |
| REQ-033 | BE-2 | 446ba73 | ✅ done |
| REQ-034 | BE-3 | 7b2b3c5 | ✅ done |
| REQ-035 | BE-4 | ae37923 | ✅ done |
| REQ-036 | BE-5 | 71763d8 | ✅ done |
| REQ-037 | BE-6 | f89344c | ✅ done |
| REQ-038 | BE-7 | 752cded | ✅ done |
| REQ-039 | BE-8 | fa3702b | ✅ done |
| REQ-040 | BE-9 | 446ba73 | ✅ done |
| REQ-041 | F2.1 | 588535a | ✅ done |
| REQ-042 | F4.1 | cea3300 | ✅ done |
| REQ-043 | F6.1 | daf4323 | ✅ done |
| REQ-044 | F6.2 | 958f75e | ✅ done |
| REQ-045 | F1.2 | — | ✅ done |
| REQ-046 | F3.1 | de32284 | ✅ done |
| REQ-047 | F8.1 | c706260 | ✅ done |
| REQ-048 | F2.2/F2.3 | 71e8758 | ✅ done |

## Implementierungsstatus P2 (Welle 2 — 2026-07-14)

| REQ-ID | Ref | Commit | Status |
|--------|-----|--------|--------|
| REQ-049 | FE-3/4/6/7 | — | ⚠️ risk — L-Aufwand, 71 Dateien, React-Query-Migration auf P3 verschoben |
| REQ-050 | FE-5 | — | ⚠️ risk — L-Aufwand, Monster-Komponenten-Zerlegung auf P3 verschoben |
| REQ-051 | FE-8 | 1b4863f | ✅ done |
| REQ-052 | FE-9 | — | ⚠️ risk — erfordert Backend httpOnly-Cookie-Support + Frontend-Umbau |
| REQ-053 | FE-10 | — | ⚠️ risk — L-Aufwand, 5 große Views ungetestet, auf P3 verschoben |
| REQ-054 | FE-11 | — | ✅ done — bereits implementiert (React.lazy + Suspense in NavigationShell.tsx) |
| REQ-055 | FE-12 | — | ✅ done — Beschreibung korrigiert (i18n in 71 Dateien aktiv, Rollout als P3) |
| REQ-056 | FE-13 | 986506e | ✅ done |
| REQ-057 | INF-8 | 1596e40 | ✅ done |
| REQ-058 | INF-9 | cf6ea3a | ✅ done |
| REQ-059 | INF-10 | 5fcdae9 | ✅ done |
| REQ-060 | INF-11 | a2c4305 | ✅ done |
| REQ-061 | INF-12 | cc1f698 | ✅ done |
| REQ-062 | INF-13 | c759aed | ✅ done |
| REQ-063 | INF-14 | d3fff9c | ✅ done — JSON-Logs + /health Endpoint; Prometheus-Metriken auf P3 |
| REQ-064 | INF-15 | b9c97e0 | ✅ done |
| REQ-065 | INF-16 | b4376d4 | ✅ done |
| REQ-066 | BE-10 | — | ⚠️ risk — L-Aufwand, Service-Layer-Architektur auf P3 verschoben |
| REQ-067 | BE-11 | 87aef2b | ✅ done |
| REQ-068 | BE-12 | 16d8f9e | ✅ done |
| REQ-069 | BE-13 | 692d1a8 | ✅ done |
| REQ-070 | BE-14 | 5950055 | ✅ done |
| REQ-071 | BE-15 | 6e385e0 | ✅ done |
| REQ-072 | BE-16 | bec2a80 | ✅ done |
| REQ-073 | BE-17 | ab593dd | ✅ done |
| REQ-074 | BE-18 | 383f213 | ✅ done |
| REQ-075 | BE-19 | 032760f | ✅ done — Wiring-Tests (Beat, Celery, SSE-async); Test-Pyramide-Rebalancing auf P3 |
| REQ-076 | BE-20 | e7841dd | ✅ done |
| REQ-077 | BE-21 | 6515a2e | ✅ done |
| REQ-078 | F4.3 | c3c536c | ✅ done |
| REQ-079 | F1.1 | 484506a | ✅ done |
| REQ-080 | F6.3 | 32fcebe | ✅ done |
| REQ-081 | F6.4 | f8f3ed4 | ✅ done — CORS-Fix + api_key-Masking; Feld-Verschlüsselung auf P3 |
| REQ-082 | F4.2 | ce3a64a | ✅ done |
| REQ-083 | F4.4 | 081440b | ✅ done |
| REQ-084 | F5.2 | e726323 | ✅ done — 25s Timeout; vollständige Async-Umleitung auf P3 |
| REQ-085 | F7.1/F7.2 | 12cea5f | ✅ done |
| REQ-086 | F8.2/F8.4 | 67407cb | ✅ done |
| REQ-087 | docs | 3ea0680 | ✅ done |
| REQ-088 | Service O(N) | 11c9db2 | ✅ done |
| REQ-089 | check_consistency | 8ab74a0 | ✅ done |
| REQ-090 | E2E-Failures | d266165 | ✅ done |
| REQ-091 | FE-14 | — | ✅ done — WorkspaceTree opt-in virtualization (@tanstack/react-virtual, threshold 100) |
| REQ-102 | INF-21 | — | ✅ done — pg_dump backup sidecar + postgres_backup_data volume, 7-backup retention |
| REQ-109 | P2-Bericht | — | ✅ done — pgvector>=0.3.0 present in requirements.txt (line 15), built via Dockerfile pip install |
| REQ-110 | P2-Bericht | — | ✅ done — python-json-logger>=2.0.7 present in requirements.txt (line 39), built via Dockerfile pip install |
