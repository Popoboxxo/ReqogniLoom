---
title: Bugfix-Runde 6 — Umsetzungsplan (beta.22-QA-Batch, Performance, API-Contract, Datenintegrität, UX/A11y, Ops)
date: 2026-10-20
branch_base: origin/main @ dc7ee148
author_agent: orchestrator
status: proposed
scope: Offener Bug-/QA-Backlog nach Runde 5 (R1–R10: #1379–#1412, #1378, #1386, #1439, #1443/#1444) + Persistenz-/Memory-/Honcho-Residuen (#1153/#1247, #1314–#1337, #1334) in Wellen W18–W25; Feature-/Roadmap-Issues ausdrücklich außerhalb
---

# Bugfix-Runde 6 — Umsetzungsplan

> **Status:** `proposed` — dieser Plan implementiert nichts. Er beschreibt Paket, Reihenfolge,
> Wellen und Akzeptanzkriterien.
>
> **Faktenbasis:** Eigener Backlog-Scan am **2026-10-20** gegen `origin/main @ dc7ee148`
> (v1.8.0-beta.22). **73 offene Issues**, davon ca. 40 Bug-/QA-/Performance-/Ops-relevant.
> Angaben aus Issues sind als „laut Issue" markiert, eigene Prüfung als „**verifiziert**".
> Korrekturen an Ursachenangaben stehen in §0.2.
>
> **Abgrenzung zu Runde 5** (`bugfix-round-5-plan.md`): Runde 5 (W12–W17) ist **vollständig
> gemergt** (PRs #1413–#1425). Der Frontend-Audit-Plan ist mit Phasen 0–8 ebenfalls gemergt
> (#1426–#1442). Die drei MEDIUM-Fixes aus dem beta.21-Nachlauf — **#1438, #1437, #1436** — sind
> bereits in beta.22 enthalten (PRs #1446–#1448) und **nicht** Teil dieser Runde.

---

## 0. Ausgangslage

### 0.1 Basen & bereits Erledigtes

| Aspekt | Wert |
|---|---|
| `origin/main` | `dc7ee148` (Merge PR #1449, `VERSION` = `1.8.0-beta.22`) |
| Letzter Release | `v1.8.0-beta.22` (Tag `dc7ee148`, GitHub-Release, GHCR-Images backend/frontend) |
| Runde 5 | vollständig gemergt (W12–W17, PRs #1413–#1425) |
| Frontend-Audit | Phasen 0–8 vollständig gemergt (#1426–#1442; Ratchet-Ceilings 18/0/0) |
| Beta.21-Nachlauf | **erledigt:** #1438 (Outbox), #1437 (/health Vector-Backend), #1436 (Overlay-`image:`) — PRs #1446–#1448 |
| Offener Backlog | **73 Issues**: 4 `bug`, 39 `qa`, 11 `high`, 20 `medium`, 10 `low`; Rest Feature/Enhancement/Roadmap |
| Charakter dieser Runde | **Qualitäts-/Stabilitätsrunde** — kein neues Produktfeature, keine API-/Contract-Brüche |

### 0.2 Verifizierte Befunde und Ursachenkorrekturen

1. **#1381 (Soft-Delete) — verifiziert, Ursache präzisiert:** `rest_api/views.py` dokumentiert das
   Verhalten explizit als **gewollt** (GH-443): `DELETE` → 204, ein anschließendes Detail-`GET`
   antwortet weiter 200 mit `status="outdated"`, damit „404 = Ressource existiert nicht" eindeutig
   bleibt. Das ist **kein blinder Bugfix**, sondern eine Contract-Entscheidung: pro Ressourcenfamilie
   prüfen, ob die Semantik konsistent dokumentiert ist, dann entweder Doku/Schema nachziehen oder die
   Semantik bewusst vereinheitlichen.
2. **#1380 (Baselines 404) — verifiziert, Ursache präzisiert:** Die Route **existiert**
   (`rest_api/urls.py:258,314`; `BaselineViewSet`, `views.py:4707`), ist aber **preset-gated**:
   Im `minimal`-Preset wird bewusst `Http404` geworfen (`_check_preset`, `views.py:4747`).
   Der reale Defekt ist die **Schema-/Doku-Lücke** (OpenAPI verspricht GET/POST ohne den
   Preset-Vorbehalt), nicht ein fehlender Endpoint.
3. **#1390 (Pagination ohne ORDER BY) — teilweise verifiziert:** `StandardPagination`
   (`rest_api/serializers.py:409-447`) setzt **kein** `ordering` und keine `ordering`-Query-Quelle.
   Die `UnorderedObjectListWarning` ist damit plausibel; pro ViewSet ist `Meta.ordering` bzw. ein
   explizites `order_by` nachzuziehen.
4. **#1379 (Kontrast 1.18:1 auf /reviews) — laut Issue, Theme-/Token-Hypothese:** Die
   Reviews-Komponenten nutzen ausschließlich Tokens (`--color-text`, `--color-text-muted`,
   `--color-badge-info-text`), keinen Hardcode. Der Bruch ist damit **theme-/token-spezifisch**
   (z. B. dunkle Karte + `--color-text`), nicht ein einzelner `color:`-Literal. Fix erst nach
   axe-/Screenshot-Repro im betroffenen Theme.
5. **#1378 (Memory-Projektion) — laut Issue, Profiling nötig:** Endpoint und Service existieren
   (`memory/memory_rest.py:816`, `application/memory_admin_service.py:525`). Die Hypothese
   „synchrone Re-Embeddings pro Eintrag" ist plausibel, aber nicht belegt; erst messen, dann
   Batch-/Cache-Strategie festlegen.
6. **#1444 (REST vs. MCP Agent-Key) — laut Issue, Repro nötig:** Beide Pfade teilen
   `auth_tenancy` (API-Key-Kontext, Scopes, `api_key_workspace_ids`), werten die Rollen aber
   offenbar unterschiedlich aus (REST 403 RBAC vs. MCP 200 für die eigene Workspace). Der Fix
   gehört in eine **gemeinsame Autorisierungsauflösung**, nicht in zwei Sonderpfade.
7. **#1386 (ReqIF-Import) — laut Issue, hoher Datenimpact:** Import erzeugt Requirements ohne
   native `uid` und ohne Embedding. Vor dem Fix Backfill-/Idempotenz-Strategie festlegen
   (bestehende 903 Zeilen!), sonst entstehen Duplikate.

---

## 1. Inventar der offenen Bug-/QA-/Ops-Issues

| # | Sev | Track | Kurz | Welle |
|---|---|---|---|---|
| 1444 | MED | API/Auth | REST 403 RBAC vs. MCP 200 für denselben Agent-Key | W18 |
| 1380 | HIGH | API/Schema | Baselines-404 vs. OpenAPI (Preset-Gate nicht dokumentiert) | W18 |
| 1397 | MED | API/ETag | OpenAPI verspricht 412 für 5 Pfade, ETag/If-Match nur für 3 Familien | W18 |
| 1396 | MED | API/ETag | If-Match nur bei exakt zitierten Ganzzahlen; Weak-Validator unlesbar | W18 |
| 1388 | MED | API/Schema | OpenAPI beim Start still um 124 View-Klassen beschnitten | W18 |
| 1439 | LOW | API | api-keys-POST meldet nur das nächste fehlende Pflichtfeld | W18 |
| 1385 | HIGH | Perf | SE-Audit: 78 Queries, p95 2,794 s, 397 kB Antwort | W19 |
| 1384 | HIGH | Perf | allocation-coverage: 1.798 Queries (N+1) | W19 |
| 1398 | MED | Perf | issues/risks/adrs-Liste: 121 Queries für 55 Objekte | W19 |
| 1400 | MED | Perf/DB | Grosslisten ohne `(workspace_id, created_at)`-Index | W19 |
| 1401 | MED | Perf | Schreibpfad-Kaltstart: erster POST 9,2 s | W19 |
| 1399 | MED | Perf/DB | Vektor-Suche nutzt HNSW-Indizes nicht (Seq Scan) | W19 |
| 1390 | MED | Perf/DB | Paginierung ohne ORDER BY (25 Warnings) | W19 |
| 1378 | MED | Perf/Memory | Memory-Projektion bettet synchron neu ein → UI-Timeout | W19 |
| 1383 | HIGH | SE-Audit | Paginierung ignoriert (`page_size`/`offset` wirkungslos) | W20 |
| 1382 | HIGH | SE-Audit | `counts`-Block auf 500 gedeckelt, widerspricht `total_*_available` | W20 |
| 1403 | MED | Data | 323 hängende `workspace_id`-Referenzen ohne FK | W21 |
| 1402 | MED | Data | `uid`-Eindeutigkeit nur für `pl_requirement` erzwungen | W21 |
| 1386 | HIGH | Import/Data | ReqIF-Import: keine native `uid`, kein Embedding (903 Zeilen) | W21 |
| 1381 | HIGH | Lifecycle | Soft-Delete-Semantik inkonsistent (dokumentiert, Contract-Entscheidung) | W21 |
| 1379 | HIGH | UX/A11y | WCAG-Kontrast 1.18:1 auf /reviews | W22 |
| 1395 | MED | UX/A11y | Icon-Buttons/Sektionsköpfe unter 24 px | W22 |
| 1394 | MED | UX/A11y | Treffergröße 13×13 px bei Radio/Checkbox (4 Routen) | W22 |
| 1393 | MED | UX/Form | Pflichtfelder in 9/11 Create-Dialogen nicht markiert | W22 |
| 1392 | MED | UX/Form | Kein `maxlength` in 43 Feldern / 12 Dialogen | W22 |
| 1443 | MED | Plugin/UX | Dashboard-Tab „none visible" statt 403-Grund | W22 |
| 1287 | LOW | UX | Markdown-Formatierungszeile nicht ein-/ausblendbar | W22 |
| 1258 | LOW | UI | SystemSettings-Buttons ohne einheitliches Format | W22 (optional) |
| 1391 | MED | Ops | Basis-Images ohne Digest-Pin | W23 |
| 1389 | MED | Ops | Celery: 3 Logzeilen pro Poll-Zyklus (51.861/24 h) | W23 |
| 1387 | MED | Ops | `postgres-1` trägt als einziger Service das Testing-Override | W23 |
| 1418 | — | Ops/Frage | Bluepencil-Layer im Repo statt nur im Deployment | W23 (Entscheidung) |
| 1334 | HIGH | Vector | Artefakt-Indexer fehlt komplett (`_artifacts` bleibt leer) | W24 |
| 1336 | HIGH | Honcho | Dream konfiguriert, aber nie ausgeführt | W24 |
| 1247/#1153 | HIGH | Honcho | Dialektik endet in HTTP 500 (400 MissingSessionID, upstream) | W24 (Doku/Eskalation) |
| 1314 | MED | Qdrant | Konfiguration schöpft das Backend nicht aus | W24 |
| 1337 | MED | Honcho | 6 Fähigkeiten ohne Aufrufer | W24 |
| 1317 | LOW | Docs | Drei Memory-Ablagen, doppelte Embedding-Config | W24 (Doku/ADR) |
| 1316 | MED | Feature | Keine Hybrid-Suche (HNSW + FTS nie kombiniert) | außerhalb (Feature) |
| 1339 | — | Feature | Memory-Injektion je KI-Aktivität/Workspace/User schaltbar | außerhalb (Feature) |
| 1404–1412 | LOW | QA-Sammel | 9 Sammel-Issues der Rollen R1–R10 | W25 |

### Ausdrücklich außerhalb dieser Runde (Feature/Roadmap/EPIC)

#18, #50, #85, #89, #92, #186, #272, #378, #587, #598, #792, #801, #877, #878, #879,
#934, #941, #946, #1094, #1171, #1230, #1308, #1374, #1339, #1316.
Diese Issues sind Features/Enhancements/Roadmap oder eigenständige EPICs; sie werden **nicht**
in eine Bugfix-Runde gezogen. #1258 bleibt optional (separater Frontend-/Design-System-Strang).

---

## 2. Wellen

Jede Welle ist unabhängig shippbar: eigener `fix/*`-Branch off `origin/main`, kein Commit auf
`main`, Conventional Commits, gitleaks vor jedem Commit. Bündelung nach **geteilter Komponente**.

### W18 — API-Contract, OpenAPI & Auth-Konsistenz

| Teil | Inhalt | Ziel |
|---|---|---|
| **W18a — #1444** | Gemeinsame Autorisierungsauflösung für REST und MCP: derselbe Agent-Key muss dieselbe Entscheidung (Workspace-Scope + Rolle) erhalten. Repro als Test (REST 403 vs. MCP 200), dann eine Quelle (`AuthorizationService`) statt zweier Pfade. | Ein Key, eine Entscheidung; kein RBAC-Bypass über MCP |
| **W18b — #1380** | Preset-Gate im OpenAPI abbilden (404 im `minimal`-Preset als dokumentierte Bedingung) **oder** das Gate im Schema ausweisen. Keine Verhaltensänderung am Gate. | Schema und Laufzeit widersprechen sich nicht mehr |
| **W18c — #1397/#1396** | Conditional Requests vereinheitlichen: ETag/If-Match für die Familien, die 412 versprechen; Weak-Validator und unlesbare Werte korrekt behandeln (400 vs. 412). | OpenAPI-Versprechen = Laufzeit; keine stillen Weak-Validator-Fehler |
| **W18d — #1388** | Ursache der 124 „unable to guess serializer"-View-Klassen beheben (Serializer/`get_serializer_class`/Schema-Hooks), damit das Schema nicht still beschnitten wird. | Vollständiges, verlässliches OpenAPI |
| **W18e — #1439** | `POST /api/v1/api-keys/` sammelt **alle** fehlenden Pflichtfelder statt nur des nächsten. | Agent-Onboarding in einer Runde statt drei |

**Regressionsnetz:** `rest_api/tests/` (Contract-/Auth-Tests), `mcp_server/tests/` (Workspace-Fence,
API-Key-Scopes), OpenAPI-Schema-Drift-Test.

### W19 — Performance: SE-Audit, Listen & DB

| Teil | Inhalt | Ziel |
|---|---|---|
| **W19a — #1385** | SE-Audit-Request profilieren (Query-Log + `django-debug-toolbar`/`connection.queries`): 78 Queries und 397 kB Antwort aufteilen; N+1 und Serializer-Payload reduzieren. | p95 deutlich unter 2,8 s; Query-Zahl skalierbar |
| **W19b — #1384** | allocation-coverage: 1.798 Queries durch `select_related`/`prefetch_related` + Aggregation ersetzen (kein N+1 pro Requirement/Trace-Link). | Query-Zahl unabhängig von der Requirement-Zahl |
| **W19c — #1398** | issues/risks/adrs-Listen: Serializer-N+1 (121 Queries/55 Objekte) beheben. | lineare statt quadratische Query-Zahl |
| **W19d — #1400** | Fehlende `(workspace_id, created_at)`-Indizes ergänzen (Migration + `EXPLAIN`-Beweis). | 100-Zeilen-Request liest nicht 4.370 Zeilen |
| **W19e — #1399** | Vektor-Suche: HNSW-Index tatsächlich nutzen (`EXPLAIN`, `enable_seqscan=off`-Gegenprobe, Query-Form/Operator prüfen). | `idx_scan > 0`, kein Seq Scan + Sort |
| **W19f — #1401** | Kaltstart des Schreibpfads messen (Import-/Connection-Setup vs. echte Arbeit), dann gezielt vorwärmen/entkoppeln. | erster POST nicht 9,2 s |
| **W19g — #1390** | Pro ViewSet ein deterministisches `order_by` (bzw. `Meta.ordering`) setzen; `UnorderedObjectListWarning` = 0. | stabile Pagination, keine Warnings |
| **W19h — #1378** | Memory-Projektion: Embeddings batch-/cache-basiert statt synchron pro Eintrag; UI-Timeout ab ~150 Einträgen beseitigen. | Projektion bleibt bei 150+ Einträgen bedienbar |

**Regressionsnetz:** `application/tests/` (Audit/Coverage), `rest_api/tests/` (Listen/Pagination),
`memory/tests/`, `EXPLAIN`-Belege im PR.

### W20 — SE-Audit-Response-Contract

| Teil | Inhalt | Ziel |
|---|---|---|
| **W20a — #1383** | `page_size`/`offset` tatsächlich anwenden; Findings 501–1515 müssen erreichbar sein (oder das API gibt klar zu erkennen, dass es keinen vollständigen Walk gibt). | Paginierung wirkt; kein stiller Datenverlust |
| **W20b — #1382** | `counts`-Block und `total_*_available` aus derselben Quelle ableiten; 500er-Deckel entfernen oder als `counts_truncated` explizit machen. | Zahlen widersprechen sich nicht |

**Regressionsnetz:** SE-Audit-Tests (`audit_se_audit`/`audit.query`), Contract-Snapshot.

### W21 — Datenintegrität, Import & Lifecycle

| Teil | Inhalt | Ziel |
|---|---|---|
| **W21a — #1403** | 323 hängende `workspace_id`-Referenzen: Backfill + FK-Constraint (oder bewusst dokumentierte Ausnahme). Migration idempotent, mit Pre-Check. | Keine verwaisten Workspace-Referenzen |
| **W21b — #1402** | `uid`-Eindeutigkeit für die 7 weiteren uid-tragenden Typen per DB-Constraint erzwingen (nach Duplikat-Backfill). | Eindeutigkeit auf DB-Ebene, nicht nur im Service |
| **W21c — #1386** | ReqIF-Import: native `uid` vergeben + Embedding-Pfad anbinden; **bestehende 903 Zeilen backfillen**, ohne Duplikate. | Import erzeugt vollständige, auffindbare Requirements |
| **W21d — #1381** | Soft-Delete-Contract pro Ressourcenfamilie dokumentieren und vereinheitlichen (204 → GET 200 `outdated` ist gewollt, GH-443). Entscheidung: Doku/Schema nachziehen **oder** Semantik ändern — nicht beides halb. | Ein dokumentierter Lifecycle-Vertrag |

**Regressionsnetz:** `persistence/tests/` (Constraints/Migrationen), `rest_api/tests/` (Lifecycle),
ReqIF-Import-Tests; `manage.py makemigrations --check`.

### W22 — Frontend UX, A11y & Form-Contracts

| Teil | Inhalt | Ziel |
|---|---|---|
| **W22a — #1379** | Kontrast auf /reviews im betroffenen Theme per axe/Screenshot reproduzieren, Token/Farbrolle korrigieren (kein Hardcode). | WCAG-AA-Kontrast ≥ 4.5:1 (Text) |
| **W22b — #1395/#1394** | Interaktive Ziele auf ≥ 24×24 px (SC 2.5.8): Icon-Buttons, Sektionsköpfe, Radio/Checkbox auf 4 Routen. | Trefferflächen AA-konform |
| **W22c — #1393** | Pflichtfelder in den 9 Create-Dialogen als `required`/`aria-required` markieren und sichtbar kennzeichnen (gemeinsame Form-Infrastruktur). | Pflichtfeld-Contract im UI und DOM |
| **W22d — #1392** | `maxlength` (bzw. Zod/HTML-Validierung) für die 43 Felder aus dem Server-Contract ableiten; kein 255-Zeichen-Abbruch erst am Server. | Client und Server validieren gleich |
| **W22e — #1443** | Plugin-Dashboard: 403-Grund anzeigen statt „none visible"; Workspace-Picker mit der Fehlerursache koppeln. | Kein funktionsloser Tab ohne Erklärung |
| **W22f — #1287/#1258** | Optional: Markdown-Formatierungszeile ein-/ausblendbar; SystemSettings-Buttons auf `btn-*`-Chrome (Ratchet nur senken). | Kleinere UX-/Konsistenz-Reste |

**Regressionsnetz:** `vitest` (Reviews/Form/Dialog), `ui-ratchet`/`design-system-ratchet`
(nur senken), axe-Smoke (`e2e/tests/a11y-smoke.spec.ts`).

### W23 — Ops, Deploy & Observability

| Teil | Inhalt | Ziel |
|---|---|---|
| **W23a — #1391** | Basis-Images (`python:3.12-slim`, `redis:7-alpine`, `pgvector/pgvector:pg16`, `nginx`) auf Digest pinnen; Renovate/Dependabot-Hinweis dokumentieren. | Reproduzierbare Builds |
| **W23b — #1389** | Celery-Poll-Logging auf Zustandsänderungen reduzieren (3 Zeilen/Zyklus → eine bei Änderung), Zähler/Health statt Flood. | 51.861 Zeilen/24 h → wenige |
| **W23c — #1387** | Prüfen, warum `postgres-1` als einziger Service das Testing-Override trägt; Override sauber trennen. | Kein Test-Overlay im Produktionspfad |
| **W23d — #1418** | Bluepencil-Layer-Ablage beantworten/entscheiden (Repo vs. Deployment) und im README/Runbook dokumentieren. | Klare Betriebsgrenze, keine stille Annahme |

**Regressionsnetz:** Compose-`config`-Validierung, CI-Deploy-Gates, Runbook.

### W24 — Memory/Vector/Honcho (Entscheidungsspur)

Diese Welle ist **architekturgetrieben** und beginnt mit einer Entscheidung (ADR/Issue-Kommentar),
nicht mit Code:

| Teil | Inhalt | Ziel |
|---|---|---|
| **W24a — #1334** | Artefakt-Indexer für die `_artifacts`-Collections bauen (oder Qdrant-Opt-in ehrlich als „nicht produktionsreif" dokumentieren). | Qdrant liefert echte Treffer oder wird klar als unvollständig markiert |
| **W24b — #1336/#1337** | Honcho-Dream/6 Fähigkeiten: Aufrufer/Scheduler ergänzen **oder** als „Engine-only, nicht Produkt" dokumentieren. | Keine Fähigkeit, die niemand auslöst |
| **W24c — #1247/#1153** | Honcho-Dialektik: Header-Seam ist vendor-intern; Upstream-Eskalation + ehrliche `degraded`-Semantik beibehalten. | Kein stiller 500; dokumentierte Grenze |
| **W24d — #1314/#1317** | Qdrant-Konfiguration (Payload-Index, Sparse) und die drei Memory-Ablagen als ADR/Doku schließen. | Konfiguration und Doku decken das Backend |
| **W24e — #1316/#1339** | Hybrid-Suche / Memory-Injektion nur nach positiver Entscheidung; sonst Feature-Backlog. | Kein Feature-Schmuggel in eine Bugfix-Runde |

### W25 — Low-QA-Triage (#1404–#1412)

Die 9 Sammel-Issues der Rollen R1–R10 werden **triagiert, nicht blind gefixt**: je Befund
„fixen / Duplikat / nicht reproduzierbar / akzeptiert" entscheiden, dann gebündelt abarbeiten.
Ziel: Backlog-Hygiene, keine offenen Sammel-Issues ohne Disposition.

---

## 3. Priorisierter Vorschlag („schneller Nutzen zuerst")

1. **W18a (#1444)** — Sicherheits-/Konsistenzlücke mit klarer Repro; verhindert einen RBAC-Bypass.
2. **W19g (#1390) + W20 (#1383/#1382)** — kleine, klar prüfbare Contract-/Stabilitätsfixes.
3. **W19b (#1384) + W19c (#1398)** — N+1 mit direkt messbarem Query-Delta.
4. **W22a (#1379) + W22b (#1395/#1394)** — WCAG-AA, hohe Sichtbarkeit, isolierte Stellen.
5. **W18b–W18e** — Schema-/Contract-Hygiene; einzeln revertierbar.
6. **W19a/#1385, W19d–W19f, W19h** — größere Performance-Arbeit nach Profiling.
7. **W21a–W21d** — Datenintegrität mit Migrationen (höchste Sorgfalt).
8. **W22c–W22f, W23** — Form-/Ops-Hygiene.
9. **W24** — Entscheidungsspur, erst nach ADR/Kommentar.
10. **W25** — Triage parallel.

---

## 4. Reihenfolge & Parallelisierung

- **Parallelisierbar:** W18 (API) ∥ W19 (Perf) ∥ W22 (Frontend) — getrennte Dateien/Komponenten.
- **Nicht parallel:** W21-Migrationen (DB-Schema) untereinander; W20 nach W19a (gleicher Endpoint).
- **Reihenfolge:** W18a → W19g/W20 → W19b/c → W22a/b → W18b–e → W19a/d–f/h → W21 → W22c–f/W23 → W24 → W25.
- Jede Welle: eigener `fix/*`-Branch off aktuellem `origin/main`; ein Commit pro Issue/Batch;
  nach jedem Commit die betroffene Suite; bei Rot sofort revertieren (kein Nachbessern im roten Zustand).
- Keine Welle erhöht ein Ratchet-Ceiling; Frontend-Ratchets nur senken.

---

## 5. Definition of Done (je Welle)

- Repro/Test **vor** dem Fix (rot), danach grün; für Contract-Fixes ein Schema-/Snapshot-Test.
- `pytest` (betroffene Suiten) + `npx vitest run` + `npm run lint` + `npx tsc --noEmit` grün.
- Keine API-/Contract-Brüche ohne explizite Entscheidung; OpenAPI/Serializer konsistent.
- Migrationen: `makemigrations --check`, idempotent, mit Rollback-/Backfill-Notiz.
- Performance-Fixes: Vorher/Nachher-Messung (`EXPLAIN`, Query-Zahl, p95) im PR.
- Issue mit `Fixes #NNNN`, danach kommentiert (Ursache, Fix, Verifikation, Rest-Risiken).
- Secret-Scan (gitleaks) vor jedem Commit; keine fremden dirty Dateien im Commit.
- Runde-Abschluss: Backlog-Delta dokumentiert (geschlossen / verschoben / außerhalb).

---

## 6. Risiken & offene Entscheidungen

| Risiko / Entscheidung | Auswirkung | Vorschlag |
|---|---|---|
| #1381 Soft-Delete-Semantik | Contract-Änderung vs. Doku | **Doku/Schema nachziehen** (GH-443 ist bewusst); nur bei belegtem Bedarf ändern |
| #1380 Preset-Gate im Schema | Schema-Generierung vs. Laufzeit | Gate im Schema abbilden; Endpoint nicht „öffnen" |
| #1386 ReqIF-Backfill | 903 Bestandszeilen, Duplikatrisiko | Erst Trockenlauf + Mapping, dann idempotenter Backfill |
| #1403/#1402 Migrationen | Datenverlust bei falschem Backfill | Pre-Check, Transaktion, Rollback-Plan, Staging-Lauf |
| #1391 Digest-Pins | Renovate/Dependabot-Aufwand | Pins + dokumentierter Update-Pfad |
| #1444 Auth-Divergenz | Sicherheitsrelevanz | Gemeinsame Quelle, kein Quick-Patch in einem der beiden Pfade |
| #1334/#1336 Honcho/Qdrant | Architektur, ggf. Feature-Umfang | Erst ADR/Entscheidung; sonst ehrlich als unvollständig dokumentieren |
| #1379 Theme-Kontrast | Nur ein Theme betroffen? | axe-Repro im Dark-/Sepia-Theme, dann Token-Fix |

---

## 7. Self-Review

- **Vollständigkeit:** Alle 4 `bug`-Issues (#1378, #1443, #1444, #1153) sind zugeordnet; alle
  HIGH/MEDIUM-QA-Befunde (#1379–#1403, #1386) sind in W18–W24 verortet; die Low-Sammel-Issues in W25.
- **Abgrenzung:** Feature-/Roadmap-Issues sind explizit ausgeschlossen; keine Vermischung mit
  Produktfeatures.
- **Risiko-Reihenfolge:** risikoarme Contract-/UI-Fixes zuerst, DB-Migrationen und Architektur
  (W21/W24) zuletzt.
- **Verifikationslücken:** #1379, #1378, #1444, #1384–#1386 sind „laut Issue" und benötigen vor dem
  Fix eine Repro/Messung; das ist als erster Schritt je Welle verankert.
- **Kein Implementierungsanspruch:** Dieser Plan ändert keinen Code.

---

*Erstellt am 2026-10-20 gegen `origin/main @ dc7ee148` (v1.8.0-beta.22). Runde 5 und der
Frontend-Audit-Plan sind abgeschlossen; Runde 6 ist die nächste Qualitäts-/Stabilitätsrunde.*
