# DOC-03 — Test-/CI-Wahrheit (Findings 193, 194, 195, 196, 198, 199, 200)

> Status: umgesetzt · Datum: 2026-10-03 · Branch: `feat/w2-p1`
> Mess-HEAD: `fc07b930` · Workpackage: W2/P1 · ADR: keiner nötig

Ziel: Die CI führt die Backend-pytest-Suite tatsächlich aus; die genannten Tests
behaupten nichts Falsches mehr; die Testzahlen sind **gemessen**, nicht behauptet.

---

## 1. Geänderte Dateien + Begründung je Assertion-Korrektur

### 1.1 `.github/workflows/ci.yml` — Finding 193

**Vorher** (4 Pfad-Sets; `memory/tests`, `link_types/tests` und das Root-`tests/`
matchten kein Set → sie liefen in **keinem** Backend-CI-Job):

```yaml
          - id: set-4-features
            name: "Cross-Cutting & Features (llm_adapter, diagram, traceability, workflow, context_graph, se_metrics, baseline, admin_ops, icd, resilience, audit)"
            paths: "llm_adapter/tests diagram/tests traceability/tests workflow/tests context_graph/tests se_metrics/tests baseline/tests admin_ops/tests icd/tests resilience/tests audit/tests"
```

**Nachher** (die drei dunklen Pfade in das Cross-Cutting-Set aufgenommen):

```yaml
          - id: set-4-features
            # AUD-2026-09-193 (DOC-03): memory/tests (344), link_types/tests (141)
            # and the root tests/ suite (55) were previously matched by none of
            # the four path sets and therefore ran in no backend CI job. ...
            name: "Cross-Cutting & Features (llm_adapter, diagram, traceability, workflow, context_graph, se_metrics, baseline, admin_ops, icd, resilience, audit, memory, link_types, root tests)"
            paths: "llm_adapter/tests diagram/tests traceability/tests workflow/tests context_graph/tests se_metrics/tests baseline/tests admin_ops/tests icd/tests resilience/tests audit/tests memory/tests link_types/tests tests"
```

### 1.2 `.woodpecker.yml` — Finding 194

**Vorher** — `test-backend` führte **kein** `pytest` aus und hatte keine
Service-Container (DB `localhost`, kein Redis):

```yaml
      DJANGO_SETTINGS_MODULE: reqogniloom.settings
      ...
      FIELD_ENCRYPTION_KEY: test-only-encryption-key
      ...
      DB_HOST: localhost
    commands:
      - cd backend && pip install -q -r requirements.txt
      - echo "Running Django system checks..."
      - python manage.py check
```

**Nachher** — top-level `services:` (postgres + redis), `settings_test`,
Service-Hostnamen, Socket-Wait und ein echter pytest-Lauf:

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: test_reqflow
      POSTGRES_USER: test_user
      POSTGRES_PASSWORD: test_password
  redis:
    image: redis:7-alpine
...
      DJANGO_SETTINGS_MODULE: reqogniloom.settings_test
      FIELD_ENCRYPTION_KEY: ""
      DB_HOST: postgres
      DB_APP_PASSWORD: test-only-app-role-password
      CELERY_BROKER_URL: redis://redis:6379/0
      REDIS_URL: redis://redis:6379/0
    commands:
      - cd backend && pip install -q -r requirements.txt
      - echo "Running Django system checks..."
      - python manage.py check
      - echo "Waiting for postgres and redis to accept connections..."
      - |
        python - <<'PY'
        ... socket poll for postgres:5432 and redis:6379 ...
        PY
      - echo "Running backend pytest suite..."
      - pytest
```

`FIELD_ENCRYPTION_KEY` war der ungültige Literal `test-only-encryption-key`;
da `test-backend` bisher nur `manage.py check` fuhr, fiel das nie auf. Jetzt
leer → `settings_test` erzeugt prozessweise einen gültigen ephemeren Key
(issue #151). Die frühere `settings`-Modul-Wahl hätte Deployment-Config in die
Suite gelassen; `settings_test` ist das, was der GitHub-Matrix-Job nutzt.

### 1.3 `backend/mcp_server/tests/test_e2e_sse_transport.py` — Finding 198

**Vorher** — zwei `skipif`; das erste deaktivierte den Test in **jedem**
CI-Lauf:

```python
@pytest.mark.integration
@pytest.mark.skipif(
    bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS")),
    reason="SSE live-Redis round trip requires a reachable Redis (skipped in CI)",
)
@pytest.mark.skipif(not _REDIS_REACHABLE, reason=...)
def test_sse_live_redis_round_trip_delivers_published_message(...):
```

Außerdem baute `_integration_redis_url()` die URL nur aus
`REDIS_HOST`/`REDIS_PORT`/`REDIS_PASSWORD` (Default-Host `redis`) und ignorierte
`REDIS_URL` — im GitHub-Runner ist der Redis-Service aber unter `localhost`.

**Nachher** — blanker CI-`skipif` entfernt, `REDIS_URL` hat Vorrang:

```python
def _integration_redis_url() -> str:
    url = os.environ.get("REDIS_URL")
    if url:
        return url
    host = os.environ.get("REDIS_HOST", "redis")
    ...
@pytest.mark.integration
@pytest.mark.skipif(not _REDIS_REACHABLE, reason=...)
def test_sse_live_redis_round_trip_delivers_published_message(...):
```

Der verbleibende Skip ist der ehrliche: „kein erreichbares Redis". GitHub-CI
und Woodpecker stellen jetzt einen Redis-Service bereit und setzen `REDIS_URL`
→ der Live-SSE-Pfad läuft dort. Beleg: Lauf mit `CI=true`,
`GITHUB_ACTIONS=true`, `REDIS_URL=redis://redis:6379/0` → **10 passed**,
inkl. `test_sse_live_redis_round_trip_...` (siehe §3).

### 1.4 `backend/rest_api/tests/test_llm_settings.py` — Finding 200

**Vorher** — fixierte das abgeschaltete Anthropic-Modell
`claude-3-opus-20240229` als Request **und** Erwartungswert:

```python
            "model_name": "claude-3-opus-20240229",
...
    assert body["model_name"] == "claude-3-opus-20240229"
```

**Nachher** — neutraler, anbieterunabhängiger Platzhalter; der Test prüft nur
den Round-Trip eines explizit geschriebenen `model_name`, nicht ein konkretes
Produkt:

```python
            # ... no future model deprecation can invalidate it. The provider's
            # own current default is asserted in tests/test_llm_int_02_03.py.
            "model_name": "test-model-roundtrip",
...
    assert body["model_name"] == "test-model-roundtrip"
```

### 1.5 `frontend/src/hooks/useNotificationFeed.test.ts` — Finding 199

**Vorher** — Bare-Global `localStorage`:

```ts
  beforeEach(() => {
    localStorage.clear();
...
    expect(localStorage.length).toBe(0);
    expect(localStorage.getItem("reqflow-interview-widget-open")).toBeNull();
```

**Nachher** — deterministischer In-Memory-`Storage` auf `window`, gleiches
Muster wie `useReadableIdsVisible.test.ts`:

```ts
function installMemoryStorage(): Storage { ... }
describe("useNotificationFeed", () => {
  beforeEach(() => {
    installMemoryStorage();
...
    expect(window.localStorage.length).toBe(0);
    expect(window.localStorage.getItem("reqflow-interview-widget-open")).toBeNull();
```

Wichtig: `window.localStorage` allein genügt **nicht** — in dieser Runtime ist
auch `window.localStorage` `undefined` (`TypeError: Cannot read properties of
undefined (reading 'clear')`). Der Node-≥22.4-Global überschattet jsdoms
Storage. Deshalb der explizite, versionunabhängige Stub. Der Hook persistiert
nichts (ADR-009); ein frischer leerer Store pro Test drückt genau diesen
Vertrag aus.

---

## 2. Wahre Backend-Testzahlen (gemessen)

Kommando (wie gefordert):

```
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml \
  --project-directory . run --rm backend-test pytest --collect-only -q
```

| Messung | Wert |
|---|---|
| `pytest --collect-only -q` (gesamter Arbeitsbaum, HEAD `fc07b930`) | **10 320** |
| davon vom Backend-Matrix + den 3 neu aufgenommenen Pfaden abgedeckt | **10 311** |
| Rest = `docs/agent-templates` (3 Dateien, 9 Tests) | **9** |
| — separat abgedeckt durch den GH-Job `agent-templates-test` (`pytest docs/agent-templates dist`) | ✅ |

Zuvor nicht in **einem** Backend-CI-Job (nun aufgenommen):

| Pfad | collected Tests |
|---|---|
| `memory/tests` | 344 |
| `link_types/tests` | 141 |
| `tests/` (Root) | 55 |
| **Summe neu abgedeckt (committed tree)** | **540** |

Hinweis zum Shared Tree: der Arbeitsbaum wird parallel von anderen Agenten
bearbeitet. Zwei **untracked** In-Progress-Dateien
(`tests/test_int_06_openapi.py`, `tests/test_sec_04_admin_key_revocation.py`)
kamen während der Messung hinzu und erhöhten den Arbeitsbaum-Zähler um 22 auf
10 320. Die erste Messung (vor diesen Dateien) war **10 299**; der
committed-tree-relevante Wert ist ≈ **10 298**.

### Abgleich mit der Plan-Zahl „443"

Die Plan-Zeile „`pytest --collect-only` liefert 443" ist ein **Kategorienfehler**:
443 ist der im Audit statisch ausgezählte Wert an *Testfunktionen* in nicht
abgedeckten Dateien (`AUDIT_FINDINGS.md` §C10/§15.3) — **nicht** ein
pytest-Collection-Ergebnis. Die statische Zahl enthält zudem Falsch-Positive:
Produktionsmodule, die nur wegen ihres Namens wie Tests aussehen und von pytest
gar nicht gesammelt werden (`application/test_service.py`,
`application/test_run_service.py`, `mcp_server/tools/tests.py` — 0 Tests).
Die **gemessene** Lücke ist **540** collected Tests (344 + 141 + 55).
Kanone: 10 320 collected / 10 311 abgedeckt / 9 via separatem Job.

---

## 3. Lauf der drei korrigierten Tests

| Test | Ergebnis | Kommando |
|---|---|---|
| `test_e2e_sse_transport.py` (mit `CI=true`, `GITHUB_ACTIONS=true`, `REDIS_URL=redis://redis:6379/0`) | **10 passed** · 0 failed · 0 skipped — inkl. `test_sse_live_redis_round_trip_delivers_published_message` | `backend-test pytest mcp_server/tests/test_e2e_sse_transport.py -v` |
| `test_llm_settings.py` | **16 passed** · 0 failed | `backend-test pytest rest_api/tests/test_llm_settings.py -v` |
| `useNotificationFeed.test.ts` | **13 passed** · 0 failed (Host Node v26.7.0; im CI-Container `node:22` ebenfalls 13 passed) — vorher **13 failed** | `vitest run src/hooks/useNotificationFeed.test.ts` |

Der SSE-Lauf ist der Kernbeweis für Finding 198: mit gesetztem `CI`/
`GITHUB_ACTIONS` läuft der Live-Redis-Test jetzt — statt zu skippen.

---

## 4. Regressions-Check der neu abgedeckten Suiten

Da diese Suiten bisher in keiner CI liefen, musste geprüft werden, ob sie grün
sind (sonst würde die CI-Erweiterung rot).

| Suite | Ergebnis |
|---|---|
| `tests/` **tracked** (`test_celery_topology`, `test_csrf_trusted_origins`, `test_llm_int_02_03`, `test_required_secrets`, `test_version`, `test_wiring`) | **55 passed** |
| `memory/tests` + `link_types/tests` + getracktes `tests/` (gemischter Lauf) | **554 passed, 7 failed** — alle 7 failures in **untracked** In-Progress-Dateien (s. §5) |
| `memory/tests/test_backend_contract.py` (Stichprobe) | **79 passed** |

---

### 4.1 Findings 195/196 (Falsch-Abnahmen)

195 („Regression-Suite ist vollständig grün") und 196 („W1–W4 … getestet")
sind Aussagen in `RELEASE_v1.8.0-beta.17.md`. Der DOC-03-Auftrag stellt die
**Test-Wahrheit** her, nicht die Release-Notiz umzuschreiben; die Datei liegt
außerhalb des erlaubten Änderungsumfangs. Die Korrektur ist faktisch: §2 nennt
die gemessenen Zahlen, §1.1 schließt die 540-Lücke, §1.5 macht die 13 zuvor
roten ADR-009-Tests grün. Die betroffene Release-Datei bleibt als
Folge-Doku-Aufgabe (documenter) offen.

## 5. Blocker / Out-of-Scope-Befunde (nicht maskiert)

Die zwei untracked In-Progress-Dateien eines anderen Workstreams sind **rot**
und würden, sobald committet, den neu aktivierten `tests/`-CI-Pfad rot machen:

- `tests/test_int_06_openapi.py` — **6 failures**: ReqIF-Export verletzt das
  XSD (30 Violations, u. a. `REQ-IF-VERSION` != `1.0`, fehlende `LAST-CHANGE`/
  `MAX-LENGTH`), `request_id` fehlt im Error-Body, 403/500-Responses und
  ReqIF-Request-/XML-Response-Schemas sind nicht deklariert.
- `tests/test_sec_04_admin_key_revocation.py` — **1 failure**: Admin-Changelist/
  Change-View nicht tenant-scoped.

Diese gehören zu INT-06 (OpenAPI/ReqIF) bzw. SEC-04 und sind **nicht** Teil von
DOC-03. Empfehlung: vor dem Commit dieser Dateien grün stellen; sonst bricht der
neue `tests/`-Pfad die Backend-CI. Reale Produktlücken, nicht wegweisgetestet.

**Verifikationslücke:** `.woodpecker.yml` konnte lokal nicht ausgeführt werden
(kein Woodpecker-Runtime/kein Linter verfügbar). Validierung beschränkt auf
YAML-Parse (`yaml.safe_load` OK) und inhaltliche Prüfung gegen die Woodpecker-
`services`-Doku. Kein Config-Fehler sichtbar, aber der erste reale
Woodpecker-Lauf bleibt abzuwarten.

---

## 6. Beweis: CI ruft pytest jetzt (und mehr) auf

`.github/workflows/ci.yml` (seit dem SEC-08-Commit bereits vorhanden,
unverändert; die Matrix-Pfade sind die Korrektur):

```yaml
      - name: Run pytest for ${{ matrix.test-set.id }}
        working-directory: backend
        env:
          DJANGO_SETTINGS_MODULE: reqogniloom.settings_test
          ...
        run: pytest ${{ matrix.test-set.paths }}
```

Der neue `set-4-features`-Pfadschlauch enthält `memory/tests link_types/tests
tests`; die Vier-Set-Matrix deckt zusammen die 10 311 gesammelten Tests ab.
