---
type: REVIEW
scope: audit-review-method
status: final
date: 2026-10-01
author_agent: validator
branch: chore/audit-review-2026-09
source:
  - docs/audit/2026-09/review/evidence/REVIEW_WP1A.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP1B.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP1C.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP1C_SUPP.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP1D.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP2.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP3.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP4.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP5.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP6A.md
  - docs/audit/2026-09/review/evidence/REVIEW_WP6B.md
  - docs/audit/2026-09/review/evidence/REVIEW_LIVE_CRITICALS.md
---

# AUDIT_REVIEW_METHOD — Methodik und Methodenkritik der Audit-Review

> **Rolle dieses Dokuments.** Beschreibt das Vorgehen der adversarialen
> Zweitprüfung, trennt Live- von statischer Evidenz, benennt das Unverifizierbare
> und unterzieht die **Zahlen-, Zitat- und Schlussweisen des Original-Audits**
> einer Nachprüfung. Keine neue Fachanalyse, keine Produktänderung.

---

## 1. Methodik der Review

### 1.1 Aufbau — ein unabhängiger Verifier je Workpackage

Jedes Workpackage wurde von einem **eigenen, fachlich passenden Agenten**
read-only gegengeprüft:

| WP | Verifier (author_agent) | Methode |
|---|---|---|
| WP-1a (MCP) | `backend-reviewer` | statisch, Docker down |
| WP-1b (LLM-Adapter) | `backend-reviewer` | statisch, Docker down |
| WP-1c (Infra) | `code-reviewer` | statisch, Docker down |
| WP-1c-Supp | `devops-engineer` | statisch + **Live** (Stack up), isolierte Celery/kombu-Repro |
| WP-1d (REST) | `backend-reviewer` | statisch, Docker down |
| WP-2 (Plugins) | `code-reviewer` | statisch + Live-Teilproben |
| WP-3/3b (UI) | `frontend-reviewer` | statisch, Browser nicht nötig |
| WP-4 (Datenmodell) | `code-reviewer` | statisch + **Live-Postgres** (`SELECT`) |
| WP-5 (Traceability) | `validator` | statisch, Zahlen `rg`/PowerShell |
| WP-6a (Security) | `security-auditor` | statisch, Docker down |
| WP-6b (Reliability) | `code-reviewer` | statisch + **Live-Postgres** (`SELECT`/`EXPLAIN`) + `celery inspect` |

### 1.2 Verbindliche Regeln (in allen Reviews angewandt)

1. **Audit-eigene Evidenz ist kein Beweis.** `AUDIT_EVIDENCE/*` wurde nur als
   *Ortungshinweis* gelesen. Jede Aussage wurde neu aus **Produktcode/-config**
   abgeleitet. Einzige benannte Ausnahme: das von Django generierte
   `wp1d-resolved-routes.json` (WP-6a) — gegen `rest_api/urls.py` gegengeprüft und
   ausdrücklich als Gegenstand der Zahlenkritik behandelt.
2. **Zwei-Pass-Protokoll:** Recall (zitierte `file:line` lokalisieren) → Adversar
   (Aussage gegen die Mechanik falsifizieren).
3. **Gegenbeweis-Pflicht:** Jedes Verdikt trägt `file:line` + Zitat bzw. eine
   Live-Messung. Fehlzitate werden auch dann notiert, wenn die Aussage überlebt.
4. **Verdikt nur `BESTAETIGT`, wenn Ort *und* Aussage stimmen.**
5. **Kein Phantom-Gegenbeweis:** Wo das laufende System keine Entscheidung erlaubt,
   steht `NICHT VERIFIKABAR` + **konkreter fehlender Prüfschritt**.
6. **Read-only:** kein Produktcode, keine Migration, kein Push; DB nur `SELECT`.
   `.kimi-code/` und `AUDIT_EVIDENCE/stack-seeds.md` unangetastet; nur der
   `review/`-Pfad beschrieben.

### 1.3 Verdikt-Vokabular

`BESTAETIGT | TEILWEISE | FALSCH | UEBERZOGEN | UNTERSCHAETZT |
NICHT VERIFIKABAR | KEIN REQOGNILOOM-BEZUG`. Bei abweichendem Schweregrad ist
die Korrektur Pflicht. Referenzbasis: `HEAD 10dc620f` (WP-3: `636de7d4`;
WP-6b: `bf49b0f`) — zwischen Audit-Basis `abd61aed` und HEAD nur Doku-Commits,
für `backend/**`/`frontend/**` inhaltsgleich.

---

## 2. Live vs. statisch

Ab dem Docker-Neustart war der Stack (`ai-native-reqflow-poc`, Backend
`localhost:8001`) verfügbar; abhängig vom WP-Zeitpunkt ergaben sich unterschiedliche
Möglichkeiten.

### 2.1 Live nachgetestet (Stack up) und Ergebnis

`REVIEW_LIVE_CRITICALS.md` (senior-developer), `REVIEW_WP1C_SUPP.md` (Stack up),
`REVIEW_WP2.md` (Teilproben), `REVIEW_WP4.md` (Live-Postgres),
`REVIEW_WP6B.md` (Live-Postgres + `celery inspect`).

| Finding | Live-Test | Ergebnis |
|---|---|---|
| AUD-030 | Redis-Stop, `curl --max-time 8` auf `/mcp/` | **BESTAETIGT** — kein HTTP-Response, Client-Abbruch exit 28 nach 8,01 s |
| AUD-031 | `/health/` bei Redis down | **BESTAETIGT** — HTTP 200 `ok` in 0,024 s, ohne Cache-Check |
| AUD-052 | `env`, `resolve_provider_config()`, `LlmSettings` | **TEILWEISE** — Shipped-Default `mock`, kein Fehlschlag |
| AUD-071 | ReqIF-Import | **NICHT VERIFIKABAR** — Mutation erforderlich (Vorgabe) |
| AUD-073 | `page=0/abc/99999999` auf trace-links/glossary | **BESTAETIGT** — 500 (DRF-`NotFound` im Service-`try`) |
| AUD-074 | 4 Listen-Endpunkte | **BESTAETIGT** — nackte Arrays; `/api-keys/` 200 Items/54 451 B |
| AUD-120 | `_kombu.binding.default`, app.conf | **BESTAETIGT** — 4 Members, `rk=default`, 4× Zustellung |
| AUD-121 | Beat-Log, DB-Zähler, `inspect registered` | **(c) FALSCH** — Beat dispatcht; (a)/(b) bestätigt |
| AUD-221 | 5× 401-Request, `redis-cli STRLEN` | **BESTAETIGT** — Buckets 24→61 B vor AuthN |
| AUD-222 | Workspace-Fence | **NICHT VERIFIKABAR** — Scoped-User/Mutation erforderlich |
| AUD-130/132/147/148 | `redis CONFIG GET`, `SHOW`, `pg_indexes` | Zahlen korrigiert (siehe §4) |
| AUD-135/136/138/139/140/141/143/146 | Live-Compose/DB/HTTP | bestätigt bzw. präzisiert |
| AUD-109 | `pl_workspace` = 401 Zeilen, PAGE_SIZE 25 | **BESTAETIGT** — Ziel-Workspace Rang 400 |
| AUD-151 | `GET /bluepencil/api/notes` ohne Credential | **BESTAETIGT** — 200, globaler Store |
| AUD-270 | `celery inspect registered` | **BESTAETIGT** — 6 Tasks, Archive-Task fehlt |
| AUD-281/285/287/288 | Live-Postgres-Constraints/`EXPLAIN`/`pg_stat_user_tables` | bestätigt |
| AUD-220 | `git grep`, `merge-base --is-ancestor` | **TEILWEISE** — Leak belegt, Widerruf unbelegt |

### 2.2 Runtime-only geblieben — und warum

- **WP-1a/1b/1d/6a (Docker down zum Prüfzeitpunkt):** Live-Aussagen zu
  uvicorn-Access-Log-Leak (041), 65/12-Mutationsmatrizen (051), Admin-500 (223),
  RLS 29/100 (227), 9 Admin-Keys (240) blieben statisch.
- **Mutation ausgeschlossen:** 071 (ReqIF-Import), 072 (3 Duplikate), 222
  (Scoped-User/Workspace-Fence) — die Mechanik ist statisch belegt, der Live-Lauf
  nicht durchgeführt.
- **Testläufe nicht ausgeführt:** 196/199 (65 FE-Fehlschläge erfordern `vitest run`
  unter Node ≥ 22.4), 193/195 (511/443 via `pytest --collect-only`).
- **Externe Fakten ohne Netz:** 052/053 (Provider-Retirement-Daten 2026-01-05 /
  2026-10-23), 164 (#940-Issue-Status), 156 (401/402-Historie).
- **Host-Integration fehlt:** WP-2-Hermes-Hostvertrag (101/113/152) — Desktop-Client
  nicht installiert; nur die HTTP-Aufrufe sind live testbar.

---

## 3. Was unverifizierbar blieb (konkreter fehlender Prüfschritt)

| Finding | Fehlender Prüfschritt |
|---|---|
| AUD-071 (`success:true`) | Ein ReqIF-Import mit 915 Objekten gegen einen Test-Workspace (Datenmutation) |
| AUD-222 (Workspace-Fence) | Nutzer mit Rolle in WS A, aber nicht B, plus mutierende Detail-Route / workspace-gefenceter API-Key |
| AUD-052/053 (Retirement) | Externe Provider-Statusquelle (Netz) bzw. repo-interner Beleg |
| AUD-196/199 (65 FE-Fehlschläge) | `vitest run` unter Node ≥ 22.4 (read-only nicht ausgeführt) |
| AUD-009 (Datum-Clipping) | Browser-Messung der Spaltenbreite/`overflow` (kein DOM-Fehler) |
| AUD-190 (Diff-Engine) | Baselines definieren und `baseline/diff_engine.py` mutierend prüfen |
| AUD-205 (Health-Aggregation) | Messung am laufenden Stack für ok/degraded/down-Aggregat |
| AUD-065 (LLM_API_KEY-Check) | Laufzeit-Beleg des `admin_ops/health_rest.py:273`-Checks (statisch belegt) |
| AUD-022 (Historie) | Laufzeit-/E2E-Nachweis der Fokuspfade (#991/#985) |
| AUD-051 (12/12-Mutationen) | Audit-eigener Mutationslauf reproduzieren |
| AUD-075 (432/439) | `manage.py spectacular` + Zählung (Django/DRF lokal nicht installiert) |
| AUD-076 (ReqIF-XSD) | Installiertes `reqif`-Paket + XSD-Validierung |
| AUD-041 (Access-Log-Leak) | Stack up + tatsächliche uvicorn-Logzeile |
| AUD-120/121 (Live-Manifestation) | Stack + Broker-Inspektion (in WP-1c-Supp/Live nachgeholt) |

---

## 4. Methodenkritik am Original-Audit

### 4.1 Zahlen-Behauptungen — Nachprüfbarkeit

| Audit-Zahl | Nachgeprüft | Befund |
|---|---|---|
| „453 Requests" (AUD-001) | `401 + 5 = 406` | **nicht rekonstruierbar**; 47 Restrequests unbelegt |
| „112 i18n-Keys / 41 Dateien" (002/300) | 116 Keys / 34 Dateien | **unterzählt / falscher Nenner** |
| „915 Objektfehler" (071) | Code-Ursache belegt | Zahl live nicht reproduzierbar (Mutation) |
| „432/439 Operationen" (075) | nicht nachzählbar | Werkzeugkette fehlte |
| „200 Items / 54 KB" (074) | Live 200 Items / 54 451 B | **exakt** |
| „401 Workspaces / 25 erreichbar" (109) | Live 401 / PAGE_SIZE 25 | **exakt** |
| „511 Tests" (193/195) | **443** reproduziert | **Zahl ersetzt** |
| „463" (Vor-Audit) | bezieht sich auf `attribute_definitions` | kein CI-Gap |
| „116" (Ratchet) | 116 reproduziert | exakt (mit ≥ 1 Phantom-Key) |
| „218/219 Tools" (Regel-Cluster) | 219 im Manifest; 218 in `project.yaml` | dritte Doku-Drift |
| „269/311 Routen" (222) | 311 inkl. 113 `.{format}`-Aliase → 198 distinkt, 163 ohne WS | zählmethodisch aufgebläht |
| „5914 celery-task-meta" (132) | Live 2425 | Snapshot/Drift, nicht reproduzierbar |
| „648/831 ohne TTL" (130) | Live 659/843; Keys = Versionszähler | irreführend (nicht Resultate) |
| „shared_buffers 160 MB" (147) | Live 128 MB | Zahlfehler |
| „29/100 ohne RLS" (227) | Live nicht messbar (DB down) | offen |
| „27/28 Actions" (225) | 34 Vorkommen / 15 Aktionen / 1 gepinnt | nicht reproduzierbar |
| „7 geroutete Pfade fehlen" (085) | 1 davon absichtlich (404-Catch-all) → 6 | um 1 zu hoch |
| „≥6 stale Selektoren" (310) | 3 reproduzierbar | überzogen |
| „93,5 % / 52 Elemente ohne TID" (311) | 81 % (615/759) im engeren Scan | methodenabhängig |
| „3,2 % TestCase-Tags" (188) | 99/3442 = 2,9 % | snapshot-gebunden |
| „222 863 Läufe" (284) | Live 223773 | gewachsen, Aussage nicht falsch |
| „248 kollidierende Audit-Tupel" | 144/124 | Report selbst als UNGEKLÄRT markiert |
| „5064" div. DB-Zahlen (WP-4) | 42 statt 44 `workspace_id`-Tabellen | Snapshot-Drift (3442 vs. 3062 Artefakte) |

**Muster.** Die belastbaren Kernzahlen (401, 200/54 KB, 835/511/324, 116, 219)
wurden exakt reproduziert. Die Fehler konzentrieren sich auf (a) **Unter-/Falsch-
zählungen** (112, 511, 41, 453) und (b) **snapshot-/umgebungsgebundene
Absolutwerte** (5914, 3062, 160 MB), die ohne festgehaltenen Migrations-/
Datenstand nicht reproduzierbar sind.

### 4.2 Fehlzitate (falsche `file:line`-Anker)

| Finding | Audit-Anker | Korrekte Stelle |
|---|---|---|
| AUD-067 | `audit_logger.py:174-191` | `resilient_transport.py:159-196` (`_NullCircuitBreaker`) |
| AUD-180 | „inkl. `pl_artifact`, `pl_requirement`" | beide **haben** einen `workspace_id`-FK (`models.py:1212`) |
| AUD-280 | `workflow_transitions.py:281` | dort `except (AttributeDefinitionNotFound, CrossTenantWorkspaceError)`, kein `TenantContextNotSetError` |
| AUD-042 | `interview.py:181-202` | das ist `interview.formalize`, nicht `start` |
| AUD-032 | `views.py:291-304` vs. `:311-325` | beide str; der int/str-Kontrast entsteht erst in `protocol_handler.py:264-268` |
| AUD-074 | `api_key_views.py:81`, `user_management_views.py:81` | Docstring/Klassendeklaration; `list`-Body bei `:147`/`:104` |
| AUD-076 | `reqif_export_service.py:296` | Helper `_header_id`, Header-Konstruktion bei `:392-407` |
| AUD-080 | `import_service.py:196` | Docstring; Parser bei `:346-354` |
| AUD-086 | `application/pdf_report_generator` | Modul liegt unter `traceability/pdf_report_generator.py` |
| AUD-053 | `.env.example:189` „retired" | dort `gpt-4o` (nicht retired) |
| AUD-139 | `compose.yml:139,147` | zeigen heute auf `x-honcho-env` (Zeilenverschiebung) |
| AUD-282 | `goal_service.py:659` | reicht `expected_version` **weiter** |
| AUD-222 | „0 Treffer `workspace_id` in `context.py`" | `context.py:77,111,118,129,141` enthält es |

**Muster.** Fehlzitate sind meist **Zeilenverschiebungen**, **Verwechslung von
Docstring/Deklaration mit Handler-Code** und **falsche Modulpfade**. Sie
verhindern die Reproduktion, ändern aber den Sachkern nur selten (Ausnahme 180).

### 4.3 Wurde aus Code-Lesen auf Laufzeit geschlossen?

**Ja, an mehreren Stellen** — der Audit vermischte statische Ableitung mit
Laufzeitbehauptungen, ohne die Trennung zu kennzeichnen:

- **AUD-002/300 (i18n):** Aus der Deklaration `MISSING_KEY_BASELINE = 116` wurde
  eine Laufzeit-Aussage „112 maskierte Fehl-Keys" abgeleitet; die Zahl stammt aus
  einer Scan-Version, nicht aus einer Testausführung.
- **AUD-196/199 (65 FE-Fehler):** Die 65 wurde als gemessen dargestellt, ohne
  `vitest run` — die Review konnte sie nicht reproduzieren.
- **AUD-075 (432/439):** Aus der toten `COMMON_ERROR_RESPONSES`-Deklaration wurde
  auf das generierte Schema geschlossen, ohne `manage.py spectacular` zu fahren.
- **AUD-156 (401/402):** Aus einer `unseed()`-Zeile wurde eine Datenmigrations-
  Laufzeitaussage; die zitierte Stelle enthält keine Zahl.
- **AUD-205/190:** korrekt als `BLOCKED` markiert (Gegenbeispiel: der Audit
  kennzeichnet Unentscheidbares hier sauber).
- **AUD-121:** Aus „0× `Sending due task`" im Log wurde „Beat dispatcht nie" —
  eine Laufzeit-Aussage aus einem **Log-Artefakt**, live widerlegt.

**Gegenstück.** Bei 071, 073 und 083 trug die **statische Code-Ursache** das
Verdikt auch ohne Live-Lauf; hier war der Schluss von Code auf Verhalten zulässig,
weil die Mechanik vollständig im Quelltext liegt.

---

## 5. Stichprobenumfang

| WP | Critical | High | Medium | Low | Info | geprüft / Block |
|---|---:|---:|---:|---:|---:|---|
| WP-1a | 2/2 | 5/5 | 5 (gezogen) | 4 (gezogen) | 3 (gezogen) | 19 (ID 030–051) |
| WP-1b | 1/1 | 7/7 | 6 (gezogen) | 0 | 1 (gezogen) | 15 (ID 052–067) |
| WP-1c | 2/2 | 8/8 | 0 | 0 | 0 | 10 (ID 120–149 Kern) |
| WP-1c-Supp | 2/2 | 0 | 11 (gezogen) | 7 (gezogen) | 0 | 20 (ID 120–148 Ergänzung) |
| WP-1d | 1/1 (+070) | 7/7 | 6 (gezogen) | 3 (gezogen) | 1 (gezogen) | 18 (+1 Kontrolle) |
| WP-2 | 1/1 | 6/6 | 8 (gezogen) | 5 (gezogen) | 4 (gezogen) | 22 (ID 100–153) |
| WP-3/3b | 0 | 5/5 | 10 (gezogen) | 12 (gezogen) | 0 | 27 (ID 001–321 Auswahl) |
| WP-4 | 0 | 11/11 | 11 (gezogen) | 5 (gezogen) | 6 (gezogen) | 33 (ID 154–328) |
| WP-5 | 2/2 (Duplikate) | 19/19 | 10 (gezogen) | 1 (gezogen) | 0 | 32 (ID 191–350) |
| WP-6a | 2/2 | 5/5 | 7 (gezogen) | 4 (gezogen) | 0 | 18 (ID 220–241) |
| WP-6b | 0 | 3/3 | 13 (gezogen) | 3 (gezogen) | 0 | 19 (ID 270–288) |

- **Alle Critical und alle High wurden vollständig geprüft** (14/14 bzw. 76/76,
  100 %). Der Auftrag „Critical+High vollständig" ist erfüllt.
- **Medium/Low/Info wurden gezogen** (143 von 189 ≈ 75,7 %). Nicht gezogen bzw.
  nicht einzeln bewertet: die restlichen Medium/Low/Info-Findings der Register-
  Blöcke 001–025 (WP-3), 226–241 (WP-6a), 289 ff. (WP-4) — dort wurden die
  produktrelevanten Cluster (i18n, RLS, RLS-Exempt, Health, Outbox) ausgewählt.
- **Kontrollen** (WIDERLEGT/PASS/BLOCKED) wurden als solche geführt und **nicht**
  in die Finding-Zählung eingerechnet.

---

## 6. Grenzen dieser Review

1. **Kein Produktcode-Fix.** Die Reviews sind read-only; sie ändern weder
   Produktcode noch Migrationen noch die Audit-Dokumente.
2. **Kein Push.** Alle Änderungen verbleiben auf `chore/audit-review-2026-09`;
   der Secret-Fund AUD-220 wurde nicht angefasst (nur maskiert belegt).
3. **Kein vollständiger Testlauf.** `pytest`/`vitest`/E2E wurden nicht gefahren;
   die 65-FE- und 511/443-Testzahlen bleiben offene Prüfschritte.
4. **Snapshot-/Umgebungsabhängigkeit.** Live-Messungen erfolgten gegen den
   laufenden Stack; Absolutzahlen (DB-Zeilen, Cache-Keys) hängen von Datenstand
   und Neustarts ab und sind nicht dauerhaft reproduzierbar.
5. **Host-Integration nicht prüfbar.** Hermes-Desktop-/Claude-Code-Hostverträge
   bleiben BLOCKED; nur die HTTP-Ebene ist verifizierbar.
6. **Externe Fakten** (Provider-Retirement, Issue-Status) wurden ohne Netz nicht
   belegt und sind als NICHT VERIFIKABAR markiert.
7. **Keine Konsistenz-Aussage über den Abschnitt außerhalb des Ziel-Blocks.**
   Verified sind die in §5 gelisteten Blöcke; nicht gezogene Medium/Low/Info
   bleiben ungeprüft (keine Aussage „Audit-gesamt korrekt").

---

*Erstellt durch `validator` am 2026-10-01. Aggregation und Methodenkritik der
vorhandenen Review-Evidenz; kein Produktcode geändert, kein Push, keine Secrets.*
