---
title: Bugfix-Runde 7 — Umsetzungsplan (beta.24-QA-Batch, Autorisierungs-Wahrheit, Contract-Drift, stiller Datenverlust)
date: 2026-11-02
branch_base: origin/main @ 365fa2f4
author_agent: orchestrator
status: proposed
scope: 15 offene Bug-Issues aus dem beta.22-QA-Batch (#1592–#1615, #1639), die den Stand beta.24 überleben; #1378/#1153/#946 ausdrücklich außerhalb
---

# Bugfix-Runde 7 — Umsetzungsplan

> **Status:** `proposed` — dieser Plan implementiert nichts. Er beschreibt Auswahl, Reihenfolge,
> Wellen, PR-Schnitte und Akzeptanzkriterien.
>
> **Faktenbasis:** Backlog-Scan am **2026-11-02** gegen `origin/main @ 365fa2f4`
> (`VERSION` = `1.8.0-beta.24`, GHCR-Images veröffentlicht). **0 offene PRs**, `main`-CI und
> Playwright grün. Die QA-Issues wurden gegen **beta.22** (`dc7ee14`) gefiled; seitdem sind die
> Wellen 1–3 gemergt. Deshalb ist **Welle 0 (Re-Triage) Pflicht**, bevor Code entsteht.
>
> **Angaben aus Issues** sind als „laut Issue" markiert, eigene statische Prüfung als
> „**verifiziert**". Laufzeit-Repros gehören in Welle 0.

---

## 0. Ausgangslage

### 0.1 Basis

| Aspekt | Wert |
|---|---|
| `origin/main` | `365fa2f4` |
| Release | `v1.8.0-beta.24` (GitHub-Pre-Release + GHCR) |
| Offene PRs | 0 |
| CI | CI Pipeline + Playwright E2E grün |
| Offene Bug-Issues (Auswahl) | 15 (siehe §1) |
| Charakter | Qualitäts-/Sicherheitsrunde, **kein** neues Produktfeature, keine neuen API-Brüche |

### 0.2 Statische Vorprüfung (was noch offen ist)

| Issue | Sev | Stand gegen `365fa2f4` | Beleg |
|---|---|---|---|
| #1608 | HIGH | **offen** — `ApiKeyViewSet` gated alle Aktionen nur mit `READ`; ein `viewer` darf `scope=write` anfordern | `backend/rest_api/api_key_views.py:65-90` |
| #1593 | HIGH | **offen** — `list_tools_page`/`filter_tool_catalogue` filtern, liefern aber keine Filter-Metadaten | `backend/mcp_server/tool_registry.py:1275-1313` |
| #1639 | HIGH | **statisch behoben** — `location = /index.html` inkludiert inzwischen das Security-Snippet | `frontend/nginx.conf:113-118` |
| #1610 | MED | **statisch behoben** — `baselinesApi.list` verlangt `workspace_id` und sendet es | `frontend/src/api/baselines.ts:252-266` |
| #1614 | LOW | **statisch behoben** — ICD hat typisierte Request-/Response-Serializer + `extend_schema_view` | `backend/rest_api/icd_views.py:117-220,470-498` |
| #1596 | MED | **teilweise behoben** — Nav-Eintrag hat `requires: "admin"`; Direkt-URL-Guard prüfen | `frontend/src/components/NavigationShell/SidebarNavigation.tsx:147` |
| #1597 | MED | **offen (bewusste Regel)** — Kommentar: „GET any user, PUT/DELETE System-Admin only" | `backend/rest_api/urls.py:500-504` |
| #1592 | MED | **offen** — Rollen-Katalog wird nicht pro Preset gefiltert | `auth_tenancy/services/permission_definition.py` |
| #1594 | MED | **offen** — Katalog sagt `viewer: read=true`, Review-Queue erzwingt admin/approver/editor | `auth_tenancy/services/authorization.py` |
| #1613 | LOW | **offen** — `tier = CharField()` ohne `choices`; `timeframe` wird ungeprüft gespiegelt | `rest_api/audit_views.py:222,851`, `rest_api/metrics_views.py:210` |
| #1609 | MED | **offen** — Feld existiert in Serializer/Service, ist aber nicht an den PATCH-Pfad verdrahtet | `rest_api/serializers.py:1330`, `application/requirement_service.py:1003-1038` |
| #1611 | MED | **offen** — `artifact_type = CharField` ohne Normalisierung; Fehlertext behauptet fachlichen Ausschluss | `rest_api/interview_views.py:164,183` |
| #1615 | LOW | **offen** — `requirement.query` deklariert `workspace_id` nicht in `required` | `mcp_server/tools/requirements.py` |
| #1595 | MED | **offen** — Create-Buttons `disabled={!title.trim()}` ohne Hinweis/`aria-invalid` | `components/ArchitectureEditors/ArchitectureEditors.tsx:706` u. a. |
| #1444 | MED | **offen** — REST und MCP werten denselben Agent-Key unterschiedlich aus | `auth_tenancy` Key-Kontext vs. `mcp_server`-Gate |

**Konsequenz:** #1639, #1610 und #1614 sind Kandidaten für „verifiziert & schließen" in Welle 0,
nicht für Code. #1596 braucht einen Direkt-URL-Repro, bevor entschieden wird.

---

## 1. Scope

### 1.1 In Scope (4 Bundles)

| Bundle | Thema | Issues | Prio |
|---|---|---|---|
| **B1** | Autorisierungs-Wahrheit (Katalog = Durchsetzung; Scope-Eskalation) | #1608, #1597, #1592, #1594, #1444 | P1 |
| **B3** | Stiller Datenverlust / irreführende Fehler | #1609, #1611 | P2 |
| **B2** | API-/MCP-Contract-Drift | #1615, #1613, #1593 | P2 |
| **B4** | Frontend-Guards / UX-Wahrheit | #1595 (+ #1596 falls Repro offen) | P2 |
| **W0** | Re-Triage & Schließen | #1639, #1610, #1614, #1596 | P3 |

Reihenfolge bewusst: **B1 zuerst** (Sicherheit), dann B3 (Datenverlust), dann B2 (Contract),
dann B4 (UX). W0 läuft vor allem anderen.

### 1.2 Nicht in dieser Runde

| Issue | Grund |
|---|---|
| #1378 (Memory-Projektion synchrone Re-Embeddings) | Performance; braucht Profiling + Batch-/Cache-Design → eigene Runde 8 |
| #1153 / #1247 (Honcho-Dialektik `MissingSessionID`) | Vendor-/T1-gebunden; Live-Beleg fehlt, kein Repo-Fix |
| #946 (In-UI-Annotation-Layer) | Feature/Enhancement, kein Bugfix |
| #92, #1171, #1230 | Roadmap/Doku/One-Click, kein Bugfix |

---

## 2. Wellen und PR-Schnitte

### Welle 0 — Re-Triage (1 Tag, kein Produktivcode)

**Ziel:** keine Geister-Fixes. Jede der 15 Issue-Nummern bekommt ein Ergebnis:
`fixed → schließen mit Beleg`, `open → Bundle`, `blocked → begründen`.

- [ ] #1639: `curl -D -` gegen den Dev-/QS-Stack; CSP/X-Frame/Referrer/Permissions auf `/` und
      `/index.html` prüfen. Erwartet: Header vorhanden → Issue schließen (Beleg im Kommentar).
- [ ] #1610: `/baselines` mit aktivem Workspace öffnen; Netzwerk-Request muss `workspace_id`
      enthalten. Erwartet: 200 → schließen.
- [ ] #1614: `GET /api/schema/?format=json` → ICD-Pfad muss typisierte Felder zeigen, kein
      `additionalProperties: true` → schließen.
- [ ] #1596: als `viewer` direkt `/attributes` öffnen (nicht nur Nav prüfen). Erwartet: 403/Guard
      oder Admin-Hinweis. Sonst bleibt das Issue in B4.
- [ ] Übrige 11 Issues: Repro-Status im Issue kommentieren (`reproduced on 365fa2f4`).
- [ ] Ergebnis in `docs/bugfix-hub/README.md` bzw. Issue-Kommentaren nachführen.

**DoD W0:** Jedes Issue hat einen aktuellen Status-Kommentar; geschlossene Issues haben einen
konkreten Beleg (Header-Auszug, Request-ID, Screenshot-Text).

---

### B1 — Autorisierungs-Wahrheit (P1)

**Gemeinsame Wurzel:** Es gibt drei Aussagen über dieselbe Berechtigung — Rollen-Katalog,
REST-Gate, MCP-Gate — und sie werden getrennt gepflegt. B1 zieht sie auf **eine Quelle** zusammen.

#### PR-7-01 — `fix(auth): bound API-key scope by the creator's permissions` (Closes #1608)

- **Dateien:** `backend/rest_api/api_key_views.py` (Create-Validierung),
  `backend/auth_tenancy/services/authentication.py` (`create_api_key`),
  `backend/auth_tenancy/resource_scope.py` (Scope-Auflösung).
- **Fix:** Ein `scope=write`-Key darf nur entstehen, wenn der Ersteller in mindestens einem
  adressierten Workspace `write` effektiv besitzt. `scope=read` bleibt für jede Rolle mit
  mindestens einer Rolle im Tenant erlaubt. `principal_type=agent` erbt dieselbe Grenze.
- **Tests:** `rest_api/tests/test_api_key_views_rbac.py` erweitern: viewer→write = 403;
  viewer→read = 201; editor→write = 201; admin→write = 201; Agent-Key mit Workspace-Fence.
- **Rollback:** Revert; keine Migration.
- **Größe:** ~180 Z. · Reviewer: `security-auditor` + `code-reviewer`.

#### PR-7-02 — `fix(admin): restrict rate-limit configuration to admins` (Closes #1597)

- **Entscheidung ENT-B7-1 (vor Code):** GET auf `/admin/rate-limits/` wird **admin/approver-only**
  (konsistent zu `/admin/*`) statt „any user". Alternative „redacted view" nur, wenn ein
  Nicht-Admin sie fachlich braucht — dafür gibt es heute keinen Beleg.
- **Dateien:** `backend/rest_api/urls.py:492-504`, die zugehörige View in `admin_ops`/`rest_api`.
- **Tests:** viewer GET = 403; admin GET = 200; PUT/DELETE bleiben System-Admin; OpenAPI anpassen.
- **Rollback:** Revert; keine Migration. · **Größe:** ~80 Z. · Reviewer: `security-auditor`.

#### PR-7-03 — `fix(rbac): one truthful role catalogue per preset` (Closes #1592, #1594)

- **Dateien:** `backend/auth_tenancy/services/permission_definition.py` (Katalog),
  `backend/auth_tenancy/services/permission_matrix.py` (Preset-Matrix),
  `backend/auth_tenancy/services/authorization.py` (Durchsetzung).
- **Fix:** Der Katalog leitet die Rollen aus **derselben** Preset-Matrix ab, die die Zuweisung und
  die Review-Queue nutzen: `approver` erscheint nur, wo zuweisbar; `viewer.read` beschreibt die
  effektive Lesbarkeit inkl. `reviews/pending` (oder das Gate wird auf `read` erweitert — die
  Entscheidung fällt in der Implementierung anhand der Matrix).
- **Tests (neu):** `auth_tenancy/tests/test_permission_catalog_matches_enforcement.py` —
  für `minimal|standard|extended` × `admin|approver|editor|viewer` gilt:
  Katalogrechte == Ergebnis von `AuthorizationService.decide_access` für die repräsentativen
  Operationen (inkl. `reviews/pending` und `members`-Zuweisung).
- **Rollback:** Revert; keine Migration. · **Größe:** ~250 Z. · Reviewer: `backend-reviewer`.

#### PR-7-04 — `fix(auth): align REST and MCP agent-key authorization` (Refs #1444)

- **Vorgehen:** Erst **Spike** (read-only): beide Pfade dokumentieren
  (`rest_api`-RbacPermission vs. `mcp_server/tool_registry`-Gate), inkl. `principal_type=agent`.
  Wenn die Vereinheitlichung < ~250 Z. bleibt: gemeinsame Auflösungsfunktion in `auth_tenancy`
  und beide Türen daran anschließen. Sonst: Entscheidungsvorlage + Folge-Issue, **kein** halber Fix.
- **Tests:** derselbe Agent-Key: REST `GET /workspaces/` und MCP `requirement.query` müssen
  dieselbe Entscheidung liefern (403/200-Parität); Workspace-Fence-Fehler identisch.
- **Rollback:** Revert; keine Migration. · **Größe:** Spike + ≤250 Z. · Reviewer: `security-auditor`.

---

### B3 — Stiller Datenverlust / irreführende Fehler (P2)

#### PR-7-05 — `fix(requirements): persist or reject acceptance_criteria_items` (Closes #1609)

- **Dateien:** `backend/rest_api/serializers.py:1330`,
  `backend/application/requirement_service.py:1003-1038`,
  `backend/rest_api/views.py:6846`.
- **Fix:** `acceptance_criteria_items` im Update-Pfad entweder über
  `RequirementService.set_acceptance_criteria` persistieren (bevorzugt, Parität zum dedizierten
  Endpoint) **oder** mit `400 VALIDATION_ERROR` ablehnen. Kein `200` ohne Wirkung.
- **Tests:** PATCH mit zwei Items → GET + `/acceptance-criteria/` zeigen beide; ungültige Form →
  400; `acceptance_criteria` (Freitext) bleibt unverändert kompatibel.
- **Rollback:** Revert; keine Migration. · **Größe:** ~120 Z. · Reviewer: `code-reviewer`.

#### PR-7-06 — `fix(interviews): normalize artifact_type and correct the error` (Closes #1611)

- **Dateien:** `backend/rest_api/interview_views.py:164-210`,
  Interview-Service/Protocol-Mapping.
- **Fix:** Case-insensitive/alias-Auflösung (`requirement`, `need`, `risk`, …) auf die kanonischen
  PascalCase-Typen; unbekannter Wert → `400` mit `allowed_values`, getrennt von der echten
  „nicht unterstützt"-Meldung (MainGoal/andere).
- **Tests:** `requirement`→201, `Requirement`→201, `need`→201, `StakeholderNeed`→201,
  `unknown`→400 mit `allowed_values`; Multi-Session (`artifact_type` fehlt) unverändert.
- **Rollback:** Revert; keine Migration. · **Größe:** ~100 Z. · Reviewer: `code-reviewer`.

---

### B2 — API-/MCP-Contract-Drift (P2)

#### PR-7-07 — `fix(mcp): require workspace_id in requirement.query` (Closes #1615)

- **Dateien:** `backend/mcp_server/tools/requirements.py` (inputSchema),
  ggf. zentrale Schema-Helper.
- **Fix:** `workspace_id` in `required` aufnehmen, wie bei den Schwester-`*.query`-Tools; wenn
  möglich, die Required-Liste aus einem gemeinsamen Helper erzeugen (Drift-Guard).
- **Tests:** `mcp_server/tests/test_requirement_tool_group.py` — Schema-Required-Assertion für
  alle 6 `*.query`-Tools; Drift-Guard gegen das Manifest.
- **Rollback:** Revert inkl. Manifest. · **Größe:** ~60 Z. · Reviewer: `code-reviewer`.

#### PR-7-08 — `fix(api): validate audit tier and metrics timeframe` (Closes #1613)

- **Dateien:** `backend/rest_api/audit_views.py:222,851`,
  `backend/rest_api/metrics_views.py:210`.
- **Fix:** Enum-Validierung (`minimal|standard|extended`; `P7D|P30D|P90D|…` je nach Vertrag) →
  `400 VALIDATION_ERROR` mit `allowed_values`. Kein stiller Fallback, kein Echo ungültiger Werte.
- **Tests:** ungültig → 400 + `allowed_values`; gültig → 200 und Echo des **normalisierten** Werts;
  OpenAPI-Parameter mit `enum`.
- **Rollback:** Revert; keine Migration. · **Größe:** ~90 Z. · Reviewer: `code-reviewer`.

#### PR-7-09 — `fix(mcp): expose catalogue filtering metadata` (Closes #1593)

- **Dateien:** `backend/mcp_server/tool_registry.py:1275-1313`,
  `backend/mcp_server/server.py`/JSON-RPC-Handler (Antwortform), Manifest-Doku.
- **Fix:** `tools/list` bleibt abwärtskompatibel (`tools` unverändert), erhält aber Metadaten:
  `total`, `filtered`, `scope`/`workspace_id` (oder einen dokumentierten Hinweis samt
  `tools/filter`-Verweis). Ziel: ein Agent kann „98 von 248, gefiltert nach Key-Scope" erkennen.
- **Tests:** zwei Keys (voll/workspace-gefenct) → unterschiedliche `total`, `filtered=true` beim
  eingeschränkten Key; voller Key `filtered=false`; `nextCursor`-Semantik unverändert.
- **Rollback:** Revert inkl. Manifest. · **Größe:** ~150 Z. · Reviewer: `security-auditor`.

---

### B4 — Frontend-Guards / UX (P2)

#### PR-7-10 — `fix(ui): explain disabled create actions` (Closes #1595; ggf. #1596)

- **Dateien:** `frontend/src/components/ArchitectureEditors/ArchitectureEditors.tsx:706` und die
  Geschwister-Editoren (Adr/Issue/Need/Requirement/Risk/TestCase), gemeinsame Dialog-Komponente.
- **Fix:** Solange Pflichtfelder fehlen: sichtbarer Hinweis („Titel ist erforderlich") **und**
  `aria-invalid`/`aria-describedby` am Feld; der Button bleibt disabled, ist aber erklärbar.
  Kein stiller Klick. Für #1596 (falls Repro offen): Route-Guard + Hinweis für Nicht-Admins.
- **Tests:** `ArchitectureEditors`/`RequirementEditors`-Tests: leerer Dialog zeigt Hinweis,
  `aria-invalid` gesetzt; nach Eingabe verschwindet er; Tastaturbedienung unverändert.
- **E2E:** gezielte Spec-Erweiterung im bestehenden Editor-Spec (kein neues Spec-File nötig).
- **Rollback:** Revert; keine Migration. · **Größe:** ~120 Z. · Reviewer: `ui-reviewer`.

---

## 3. PR-Übersicht

| # | Branch | Schließt | Größe | Tests | Reviewer |
|---|---|---|---|---|---|
| 7-01 | `fix/api-key-scope-escalation` | #1608 | ~180 | set-2-api, set-4-features | security-auditor |
| 7-02 | `fix/admin-rate-limits-auth` | #1597 | ~80 | set-2-api | security-auditor |
| 7-03 | `fix/rbac-catalog-truth` | #1592, #1594 | ~250 | set-1-core, set-4-features | backend-reviewer |
| 7-04 | `fix/agent-key-auth-parity` | Refs #1444 | Spike + ≤250 | set-2-api, set-3-mcp | security-auditor |
| 7-05 | `fix/acceptance-criteria-patch` | #1609 | ~120 | set-1-core, set-2-api | code-reviewer |
| 7-06 | `fix/interview-artifact-type` | #1611 | ~100 | set-2-api | code-reviewer |
| 7-07 | `fix/mcp-requirement-query-schema` | #1615 | ~60 | set-3-mcp, drift | code-reviewer |
| 7-08 | `fix/filter-enum-validation` | #1613 | ~90 | set-2-api | code-reviewer |
| 7-09 | `fix/mcp-tools-list-filter-meta` | #1593 | ~150 | set-3-mcp, agent-templates | security-auditor |
| 7-10 | `fix/create-dialog-hints` | #1595, #1596 | ~120 | frontend-test, e2e | ui-reviewer |

**Reihenfolge:** W0 → 7-01 → 7-02 → 7-03 → 7-04 → 7-05 → 7-06 → 7-07 → 7-08 → 7-09 → 7-10.
7-01 und 7-02 dürfen parallel laufen (getrennte Dateien); 7-03 erst nach 7-01 (gleiche
Autorisierungsschicht). 7-07/7-08/7-09 sind unabhängig und können nach B3 parallel laufen.

---

## 4. Test- und Verifikationsstrategie

- **Pro PR nur die betroffenen Tests** (Test-Ökonomie); breite Matrix ist CI.
- Backend: isolierter Test-Stack
  `docker compose -p reqogniloom-test -f testing/docker-compose.test.yml --project-directory . run --rm backend-test pytest <pfade> -q --reuse-db`;
  `--create-db` nur bei Migration (in dieser Runde: keine).
- Frontend: `npx vitest run <pfade>` + `npx tsc -p tsconfig.build.json --noEmit` + ESLint;
  voller Lauf mit `--pool=forks --maxWorkers=2` (Host-Speichergrenze).
- Jeder Fix braucht **einen negativen Test**, der vor dem Fix rot ist (Repro aus dem Issue).
- **Cross-Surface-Parität** für B1/B2: REST und MCP im selben Test prüfen, wenn beide betroffen sind.
- Abschluss je Welle: `main`-CI + Playwright grün; Issue mit Beleg kommentieren und schließen.

---

## 5. Entscheidungen (vor der Umsetzung)

| ID | Frage | Empfehlung |
|---|---|---|
| ENT-B7-1 | Soll `GET /admin/rate-limits/` für Nicht-Admins 403 liefern oder eine redigierte Sicht? | **403** (konsistent zu `/admin/*`); redigierte Sicht nur mit belegtem Bedarf |
| ENT-B7-2 | Form der `tools/list`-Filter-Metadaten | Additive Felder (`total`, `filtered`, `scope`) statt neuer Response-Form; `tools` bleibt unverändert |
| ENT-B7-3 | #1444: gemeinsame Auflösung jetzt oder Folge-Issue? | Spike jetzt; Fix nur bei ≤250 Z., sonst Entscheidungsvorlage |
| ENT-B7-4 | #1596: Direkt-URL-Guard oder nur Nav-Ausblendung? | Guard + Hinweis, wenn der Repro in W0 zeigt, dass die Seite für `viewer` noch rendert |

---

## 6. Risiken

| Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|
| QA-Issues sind nach Welle 1–3 veraltet | Geister-Fixes, verschwendete PRs | Welle 0 ist Pflicht; Schließen nur mit Beleg |
| #1608-Fix bricht legitime Viewer-Read-Keys | Viewer verliert MCP/REST-Zugang | `read` bleibt erlaubt; nur `write` wird an effektive Rechte gebunden; Tests für alle Rollen |
| #1592/#1594: Katalog-Fix ändert UI-Rollenanzeige | Frontend zeigt weniger Rollen | Katalog == Matrix; UI-Tests für Presets; Doku-Update im selben PR |
| #1593: Metadaten brechen strikte Clients | Agenten-Parser | Nur additive Felder, `tools` und `nextCursor` byte-kompatibel |
| #1444 wird zu groß | Runde blockiert | Spike-Go/No-Go; sonst Folge-Issue statt halber Vereinheitlichung |
| Test-Ökonomie auf 5,8-GiB-Host | Flake/Timeouts | gezielte Pfade; voller Frontend-Lauf nur mit `--maxWorkers=2` |

---

## 7. Definition of Done (Runde 7)

- [ ] Welle 0 abgeschlossen: 15 Issues mit aktuellem Status; #1639/#1610/#1614 (und #1596, falls
      belegt) geschlossen.
- [ ] Alle B1–B4-PRs gemergt, jeder mit negativem Repro-Test und grüner CI + Playwright.
- [ ] Keine neuen `ENT-*`-IDs außer den in §5 genannten; keine absoluten Prosa-Zahlen.
- [ ] OpenAPI-Inventar, MCP-Manifest und Zähler konsistent (Drift-Gates grün).
- [ ] `main`-CI + Playwright grün; `VERSION` unverändert (kein Release in dieser Runde).
- [ ] Issues geschlossen mit Beleg-Kommentar; offene Punkte (z. B. #1444-Folge) als Issue verlinkt.

---

## 8. Aufwand (grob)

| Welle | Aufwand |
|---|---|
| W0 Re-Triage | 1 Tag |
| B1 (4 PRs) | 2–3 Tage |
| B3 (2 PRs) | 1 Tag |
| B2 (3 PRs) | 1,5 Tage |
| B4 (1 PR) | 0,5–1 Tag |
| **Gesamt** | **6–8 Tage** |
