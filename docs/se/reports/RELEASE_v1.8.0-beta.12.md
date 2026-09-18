---
type: STRATEGY
scope: Release v1.8.0-beta.12
status: in-progress
date: 2026-09-18
author_agent: release
---

# Release-Bericht v1.8.0-beta.12

## 1. Release-Ziel

Vorbereitung des Beta-Release `v1.8.0-beta.12` auf dem Branch
`chore/release-v1.8.0-beta.12` (Basis: `main`). Dieser Bericht dokumentiert die
**Vorbereitungsphase** (Versionierung in allen Carriern, CHANGELOG, Neubau der
generierten Manifeste, dieser Bericht, ein Commit). Tag, Merge, GitHub-Release,
gestempelter Build und CI-Gates folgen durch den Orchestrator und werden in
Abschnitt 10 nachgetragen. Der Bericht steht deshalb zunächst auf
`status: in-progress`.

- **Version:** `1.8.0-beta.12`
- **Tag (geplant):** `v1.8.0-beta.12`
- **Basis-Commit:** `e211a53a` (`Merge pull request #975`), voll
  `e211a53ab921692448597f65c216d331978c5dc5`
- **Letztes Release:** `v1.8.0-beta.11` = `884e65b6`
  (`884e65b6ab9e7a4a503426593b97a96a69d2f90f`), Commit-Zeit
  `2026-09-14T17:33:57+02:00`, **Tag-Zeit** `2026-09-14T18:03:32+02:00`
- **Datumsstempel des Berichts:** 2026-09-18

## 2. Release-Cutoff (exakter Zeitstempel)

Als Cutoff wurde — wie bereits beim beta.11-Bericht — der **exakte
Tag-Zeitstempel** von `v1.8.0-beta.11` verwendet (`2026-09-14T18:03:32+02:00`
= `2026-09-14T16:03:32Z`), **kein Kalender-Tagesfilter**. Die Änderungsmenge
wurde aus folgenden Abfragen ermittelt:

- `git log v1.8.0-beta.11..e211a53a` → **121 Commits**
- `gh pr list --base main --state merged --search "merged:>2026-09-14T14:34:02Z"`

Der `gh`-Suchfilter stimmt — wie beim beta.11-Bericht — nicht exakt mit dem
Tag-Zeitstempel überein; maßgeblich für die PR-Liste ist die Schnittmenge der
seit dem Cutoff gemergten PRs (Abschnitt 3). Klammer-Nummern in
Commit-Messages (z. B. `(#583)`, `(#960)`, `(#972)`) sind **Issue-Referenzen**,
keine PR-Nummern; PR-Nummern wurden ausschließlich gegen die bestätigte
Merge-Liste vergeben.

## 3. Enthaltene PRs seit dem Cutoff

| PR | Merged (UTC) | Titel |
|----|--------------|-------|
| #956 | 2026-09-15T19:53:57Z | feat: collaboration half of Menschen im System (comments + notifications) |
| #958 | 2026-09-16T22:45:48Z | fix: bulk bugfix session — security, API contracts, audit governance, UI/a11y |
| #959 | 2026-09-16T22:53:31Z | fix: security & UI bulk — CWE-209 sweep, scopes, rate limits, ETag, UI consistency |
| #961 | 2026-09-17T16:35:45Z | fix(api,ai): complete unknown-field rejection and persist derivation rationale |
| #962 | 2026-09-17 | chore(deps): bump psycopg2-binary to `>=2.9.13,<3.0` |
| #963 | 2026-09-17 | chore(deps): bump @tanstack/react-virtual 3.14.11 → 3.14.12 |
| #964 | 2026-09-17 | chore(deps): bump django to `>=6.1.1,<6.2` |
| #965 | 2026-09-17 | chore(deps): bump lucide-react 1.28.0 → 1.46.0 |
| #966 | 2026-09-17 | chore(deps): bump whitenoise to `>=6.12.0,<7.0` |
| #967 | 2026-09-17 | chore(deps): bump anthropic to `>=1.5.0,<2.0` |
| #969 | 2026-09-17 | chore(deps): bump numpy to `>=2.5.3,<3.0` |
| #970 | 2026-09-17 | chore(deps-dev): bump eslint 10.9.1 → 10.10.0 |
| #971 | 2026-09-17 | chore(deps): bump react-dom and @types/react-dom |
| #972 | 2026-09-18T06:03:27Z | docs(review): integration plan for bluepencil in ReqogniLoom |
| #973 | 2026-09-17T21:10:53Z | fix(attributes): re-materialize preset definitions and surface conflicts (#960) |
| #974 | 2026-09-17T22:31:08Z | feat(requirements): definition-driven create dialog (#583) |
| #975 | 2026-09-18T09:56:57Z | feat(review): optional bluepencil review layer via self-hosted sidecar (#972) |

**Hinweis:** #972 ist der Plan-PR (nur `docs/bluepencil-integration.md`); die
Umsetzung liefert #975. Die neun Dependabot-Bumps #962–#971 sind im CHANGELOG zu
einem einzigen Eintrag zusammengefasst.

## 4. Themen-Highlights

- **Collaboration — Kommentare & Notifications (#956):** Die Kollaborations­hälfte
  von „Menschen im System". Neue `Comment`/`Notification`-Modelle mit
  RLS-Policies, `CommentService` und `NotificationService` mit vier Triggern
  (Assignment über das Attribut-Gateway, `transition_pending`, `suspect_flagged`,
  `comment_added`), nutzer-globale Notification-Präferenzen (Opt-out, vier
  Schalter, bewusst ohne RLS), REST-Endpunkte (Kommentare, Feed,
  Self-Service-Präferenzen), eine MCP-Tool-Gruppe `comment.*` sowie `CommentPanel`,
  Notification-Bell und Profil-Sektion im Frontend inkl. DE/EN-i18n. Nicht
  implementierte ViewSet-Routen liefern jetzt 405 statt 500.
- **Definition-getriebener Requirement-Create-Dialog (#583 via PR #974):** Der
  Create-Dialog rendert dieselbe definitiongetriebene Feldstruktur wie der
  Edit-Dialog — über die bestehende `ArtifactForm`-Maschinerie, kein zweiter
  Renderer. Required-Gate zählt nur tatsächlich gerenderte/editierbare Felder,
  Required-Enums initialisieren mit `default ?? options[0]`, `editable:false`
  entfällt, Fallback auf den Legacy-Minimal-Dialog bei Ladefehler oder leerer
  Attributliste; der E2E-Vertrag (`req-new-title-input`/`req-new-save-btn`)
  bleibt erhalten.
- **Preset-Re-Materialisierung & Konflikt-Surfacing (#960 via PR #973):** Ein
  Preset-Wechsel re-materialisiert nicht angepasste Workspace-Attribut­definitionen,
  erhält kompatible Customizations vollständig und erzeugt bei inkompatiblen einen
  expliziten `AttributeDefinitionConflictError`. Der Konflikt wird über REST
  (`409 CONFLICT`, inkl. Export), MCP (`VALIDATION_ERROR`) und als fail-closed
  Approval-Gate handlungsorientiert gemeldet; keine Migration nötig.
- **Unknown-Field-Rejection abgeschlossen & Rationale-Persistenz (#961):**
  `UnknownFieldRejectionMixin` deckt die verbleibenden Top-Level-Write-Serializer
  und die serialiserfreien Roh-Routen ab (einheitlicher
  `VALIDATION_ERROR`-Envelope, Discovery-Guard-Test). Die vom LLM erzeugte
  `rationale` wird bei Derivation nicht mehr verworfen, sondern im
  `custom_fields`-Carrier persistiert (`ai_derivation` und
  `architecture_decompose_commit`).
- **Security-/API-/Audit-/UI-Bulk-Bundles (#958, #959):** Granulare API-Key-Scopes
  (`read_only < author < admin`) inkl. Admin-Tier für Governance-Surfaces,
  Agent-Self-Approval-/Self-Confirm-Sperren, konsistente
  Free-Text-Sanitization, 400 statt stillem Verwerfen unbekannter Felder,
  Scope-Prüfung vor Key-Limit, SE-Auditor-Kalibrierung und per-Blocker-Waiver,
  CWE-209-Sweep über 42 Sites, ETag/If-Match-Locking, runtime-konfigurierbare
  Rate-Limits, reale `/health`-Probes sowie eine UI/a11y/i18n-Welle
  (Design-System-Dialoge, Badges, KPI-Grid, Bottom-Sheets, `aria-live`, i18n-Keys).
- **Optionale bluepencil-Review-Schicht (#972 via PRs #972/#975):** Self-hosted
  Sidecar hinter dem Compose-Profil `bluepencil`, vendored ohne npm-Abhängigkeiten,
  clientseitig Build-Guard plus Runtime-Health-Probe, `data-testid` als
  Default-Anker, versionierter SHA256-geprüfter Browser-Bundle-Pfad, Teardown beim
  Logout. Bewusst streng opt-in; bewusste Grenze (keine Nutzerprüfung, keine
  Mandantentrennung) → QS/Demo, nicht Produktionspfad (Option A = DRF
  `ReviewNote` mit JWT + RLS).
- **Dependency-Updates:** Neun Dependabot-Bumps (psycopg2-binary, django,
  whitenoise, anthropic, numpy, eslint, @tanstack/react-virtual, lucide-react,
  react-dom/@types/react-dom).

## 5. Test- und Gate-Status

### 5.1 Maßgebliches Test-Gate (CI)

**Noch offen.** Gemäß dem beta.11-Muster gilt CI-Grün auf dem späteren
Tag-Commit als maßgebliches Gate. Der Tag existiert in dieser
Vorbereitungsphase noch nicht; der Orchestrator trägt das Ergebnis nach dem Tag
hier nach.

### 5.2 Auf dem Basis-Commit `e211a53a` verifizierte Läufe

| Prüfung | Ergebnis |
|---------|----------|
| Frontend-Volllauf (vitest, durch den Orchestrator auf genau diesem Tree) | **227 Dateien / 2065 Tests — alle grün** |
| Backend `set-1-core` (pytest) | **flaky Embedding-Failure**, im Re-Run **grün** (nicht branch-attribuierbar) |
| PR #975 Checks (26/26) | **grün**: `Agent Templates & Distribution`, `Backend Requirements Drift Check`, `Hermes IDE Plugin`, `lint`, `backend-test set-1…set-4`, `frontend-test`, `e2e (1..4)` |

Der Backend-Flake betrifft die Embedding-Schicht und ist kein Produktdefekt; er
wird in Abschnitt 9 nicht als offener Known Issue geführt, weil er im Re-Run
deterministisch grün war.

**Delta Tag-Commit ↔ Basis `e211a53a`:** ausschließlich Versionsstrings
(`VERSION`, `frontend/package.json`, `frontend/package-lock.json`, Hermes- und
`dist/plugins`-Manifeste), `CHANGELOG.md` und dieser Bericht — **keine
Code-Änderung**. Das auf `e211a53a` grüne 26/26-CI-Ergebnis (PR #975) ist damit
auf den Tag-Commit übertragbar.

### 5.3 Nachgelagerte Gates

| Prüfung | Status |
|---------|--------|
| `pre-release-check.sh` (Pre-Release-Gates) | **Exit 1 — Abweichung**; kein Gate real geprüft (CRLF-Hook-Defekt **#948**, identisch zu beta.11 — siehe Abschnitt 6.2) |
| Ersatzprüfung `action-pin-validation` (Host-Kontext, authentifiziertes `gh`) | **PASS — 11/11 Pins aufgelöst**, inkl. `github/codeql-action/upload-sarif@v4` (per `gh api` verifiziert; Regex-Blindstelle **#949**) |
| Gestempelter Build (`APP_VERSION=1.8.0-beta.12`) | **offen** — nach dem Tag |
| Docker-Image-/Trivy-Gate (`docker-publish`) | **offen** — nach dem Tag |
| Tag-Push + GitHub-Pre-Release | **offen** — nach dem Tag |

Der Gate-Dispatcher läuft also **fail-closed** (Exit 1), skippt aber faktisch
alle drei Teil-Gates selbst, weil er vor der Gate-Schleife an der
CRLF-Kodierung der synchronisierten Hook-Skripte scheitert. Die einzige
maschinell nachholbare Gate-Logik (`action-pin-validation`) wurde im
Host-Kontext vollständig nachgefahren und **bestanden**; das substanzielle
CVE-Gate läuft ohnehin in `docker-publish.yml` (Trivy, `severity
CRITICAL,HIGH`, `exit-code: '1'`) vor dem GHCR-Push.

## 6. Dokumentierte Konvention-Abweichungen

### 6.1 Hermes-`package-lock.json`-Versionsdrift (korrigiert)

`integrations/hermes-plugin/reqogniloom/package-lock.json` stand auf
`1.8.0-beta.8` (zwei Vorkommen: Root-`version` und `packages[""].version`),
während `package.json` und `hermes-plugin.json` bereits `1.8.0-beta.11` trugen.
Die lock-Datei wird vom Generator
(`dist/plugins/hermes/build_hermes_plugin.py`) **nicht** angefasst und war
seither nicht mitgezogen worden. Für beta.12 wurde sie bewusst auf
`1.8.0-beta.12` synchronisiert (nur die beiden Versionsfelder, Integrität
unverändert). Dies ist der erste Bump dieser Datei seit beta.8; eine
Generierung des Lockfiles ändert ausschließlich die Versionsfelder und wurde
nicht als `npm install`-Lauf ausgeführt.

### 6.2 `pre-release-check.sh` CRLF-/Deployment-Defekt (bekannt, #948)

Der Pre-Release-Gate-Dispatcher liegt unter `.claude/hooks/pre-release-check.sh`
und ist CRLF-kodiert; in der beta.11-Vorbereitung scheiterte er bereits vor der
Gate-Schleife (`set: pipefail: invalid option name`, `cd` auf einen
`\r`-behafteten Pfad). Das ist der in Issue **#948** dokumentierte
Host-/Deployment-Defekt, **kein substanzieller Gate-Befund**. In dieser
Vorbereitungsphase wurde der Hook gemäß Auftrags-Randbedingung
(„`.claude/**` nicht lesen/anfassen") **nicht ausgeführt**; die Ausführung und
Einordnung obliegt dem Orchestrator nach dem Tag. Das substanzielle CVE-Gate
läuft unabhängig davon in `docker-publish.yml` (Trivy) vor dem GHCR-Push.

### 6.3 Provider-Abweichung bei der Projekt-Extension (unverändert offen)

Der release-Agent referenziert `.opencode/3-project/ReqLo-release-ext.md`;
diese Datei **existiert im Repository nicht** (`.opencode/3-project/` ist leer).
Anders als beim beta.11-Bericht konnte die `.claude`-Quelldatei in dieser
Session nicht als Ersatz gelesen werden (Auftrags-Randbedingung). Der
Cutoff-Algorithmus (exakter Tag-Zeitstempel, kein Kalenderfilter) wurde gemäß
Auftrag angewendet. Die `.opencode`-Ausprägung der Extension sollte
perspektivisch nachgezogen werden, damit die Extension provider-agnostisch
greift.

### 6.4 `deploy/**`-Image-Tag-Fallbacks bewusst nicht angehoben (entdeckt, nicht gefixt)

Die `${REQOGNILOOM_VERSION:-…}`-Fallbacks in `deploy/docker-compose.yml` (5×)
und `deploy/docker-compose.minimal.yml` (3×) stehen auf `1.8.0-beta.8`, während
das Repo auf `1.8.0-beta.12` geht. Diese Fallbacks sind gemäß Auftrag
**bewusst nicht Teil** des Versions-Carrier-Sets (sie greifen nur, wenn
`REQOGNILOOM_VERSION` nicht gesetzt ist). Sie sind hier als **entdeckte, nicht
gefixte** Drift dokumentiert; ein Folge-Bump auf `1.8.0-beta.12` (oder auf eine
generischere Default-Logik) wäre sinnvoll, um überraschende Beta.8-Pulls bei
fehlender Env-Variable zu vermeiden.

## 7. Geänderte / erzeugte Dateien

- `VERSION` → `1.8.0-beta.12`
- `frontend/package.json`, `frontend/package-lock.json` → Versionsfelder
- `integrations/hermes-plugin/reqogniloom/package.json`
- `integrations/hermes-plugin/reqogniloom/hermes-plugin.json`
- `integrations/hermes-plugin/reqogniloom/package-lock.json` (Drift-Fix, s. 6.1)
- `dist/plugins/antigravity/reqogniloom/plugin.json`
- `dist/plugins/claude-code/reqogniloom/.claude-plugin/plugin.json`
- `CHANGELOG.md` → neuer Abschnitt `[1.8.0-beta.12] — 2026-09-18`
- `docs/se/reports/RELEASE_v1.8.0-beta.12.md` (dieser Bericht, neu)

Die Manifeste `dist/plugins/antigravity/reqogniloom/plugin.json`,
`dist/plugins/claude-code/reqogniloom/.claude-plugin/plugin.json` und
`integrations/hermes-plugin/reqogniloom/{package,hermes-plugin}.json` wurden
über die vorhandenen Generatoren
(`dist/plugins/{antigravity,claude-code,hermes}/build_*_plugin.py`) neu erzeugt
— die Generatoren lesen `VERSION`, deshalb wurde zuerst `VERSION` gebumpt. Die
Regenerierung ergab **ausschließlich** die Versionsänderungen (keine weiteren
Skill-/Agent-/Manifest-Diffs). Die beiden npm-Lockfiles wurden mangels
Generator-Abdeckung manuell synchronisiert (nur Versionsfelder).

## 8. Folge-Arbeiten (nach dem Release)

- **#948** — CRLF-Hook-Deployment (upstream agent-meta: Hook-Skripte beim
  Deployment LF-erzwingen + CRLF-Guard).
- **#949** — Gate-Regex: Subpath-Pins (`github/codeql-action/upload-sarif@v4`)
  werden nicht extrahiert.
- **KI-1-Härtung** — `seeded_workspace_id`-Fixture auf paginierte Suche
  umstellen (s. Abschnitt 9).
- **KI-2-Härtung** — per-File-`testTimeout` für die Dateisystem-Scan-Tests in
  `design-tokens.test.ts` oder Serialisierung in ein non-parallel-Projekt.
- **Bluepencil Option A** — Produktionspfad (DRF `ReviewNote` mit JWT + RLS)
  statt Sidecar (aus #975, bewusst nicht enthalten).
- **#868** — ETag/If-Match ist im Frontend nur für Requirements verdrahtet;
  TestCase/Baseline und der TanStack-Hook stehen offen (aus #959).
- **#803** — SE-Sektionsgruppierung erreicht Bestands-Tenants erst nach
  Re-Seed/Datenmigration (aus #958).
- **#944** — Rate-Limit-UI offen; Redis-down-Policy ist dokumentiert fail-open.
- **#696** — Flag-Flip `AUTH_LOGIN_INCLUDE_BODY_TOKEN` nach E2E-Helper-Migration.
- **#583** — Restpunkte: `verification_method`-Gate sowie `rationale`/`source`
  im Approval-Gate (hängt am WS7/#940-Backfill).
- **Optional:** Branch-Cleanup `chore/release-v1.8.0-beta.12` nach Merge (nur
  nach expliziter Freigabe).

## 9. Known Issues (lokales Test-Gate)

Beide Befunde sind **nicht-produktbezogen**. Der Stand wurde gegen die aktuellen
Dateien geprüft; KI-1 wurde gegenüber beta.11 korrigiert.

### KI-1 — `seeded_workspace_id`-Fixture in `backend/mcp_server/tests/test_mcp_api_key_roles.py`

- **Status Paginierungs-Schwäche:** **weiterhin vorhanden.** Die Fixture liest
  nach wie vor nur `data.get("results", [])` (Zeile ~296) und damit
  ausschließlich Seite 1 der paginierten Workspace-Liste; eine echte paginierte
  Suche fehlt weiterhin.
- **Korrektur des beobachteten Root-Cause (verifiziert):**
  `docs/se/reports/KNOWN_TEST_GATE_REDS.md` §2 hält fest, dass der im
  Collaboration-Lauf beobachtete Red **nicht** die Paginierung war, sondern das
  10-Key-Cap der Dev-DB kombiniert mit `_revoke_all_active_keys()`, das die
  `DELETE`-Statuscodes nicht prüfte. Dieser Helper wurde inzwischen gefixt
  (Status-Assertions + Re-List vorhanden); die Testklasse ist in CI per
  `skipif(CI or GITHUB_ACTIONS)` übersprungen.
- **Einordnung:** Test-Helper-/Dev-DB-Defekt, **kein Produktdefekt**.
- **Vorgeschlagener Folge-Fix:** Fixture zusätzlich auf paginierte Suche
  umstellen (alle Seiten via `next` bzw. `page_size=100` durchlaufen, bis
  `name == "Demo Workspace"` gefunden ist; DRF-404 auf Out-of-range-Seiten
  abfangen).

### KI-2 — Frontend-Timeout-Flake in `frontend/src/test/design-tokens.test.ts`

- **Status:** **weiterhin vorhanden.** Die beiden Dateisystem-Scan-Tests
  („every var(--token) reference …" und „every structural inline-style
  exemption …") existieren unverändert; weder die Datei noch
  `frontend/vite.config.ts` setzen einen expliziten `testTimeout`, es gilt der
  Vitest-Default von 5000 ms.
- **Root Cause (nicht-deterministisch):** Beide Scan-Tests laufen isoliert in
  ~2,7 s; unter Volllast (227 Test-Files parallel) kippt jeweils einer darüber.
  Kein Assertion-/Token-Mismatch.
- **Einordnung:** load-induzierter Timeout, **kein Produktdefekt**.
- **Vorgeschlagener Folge-Fix:** per-File `testTimeout` erhöhen oder die beiden
  Scan-Tests in ein serialisiertes/non-parallel Projekt verschieben.

## 10. Release-Ergebnis

**Platzhalter — durch den Orchestrator nach dem Tag zu füllen.**

- **Merge und Tag:** _offen_ (Branch-HEAD und Tag-Objekt nachtragen)
- **Gestempelter Build:** _offen_ (`APP_VERSION`, `GIT_COMMIT_SHA`, `BUILD_TIME`)
- **GitHub-Pre-Release:** _offen_ (URL nachtragen)
- **CI-Gates auf dem Tag-Commit:** _offen_ (`docker-publish`, „CI Pipeline",
  „Playwright E2E Tests")

Nach Abschluss ist `status: in-progress` auf `status: done` zu setzen.
