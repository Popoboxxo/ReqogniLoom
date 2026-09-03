# SYSTEMAUDIT 2026-08-27 — RESTPLAN

**Erstellt:** 2026-08-28
**Basis:** `docs/SYSTEMAUDIT_2026-08-27.md` (Backend/Gesamt, 444 Zeilen) + `docs/SYSTEMAUDIT_UI_2026-08-27.md` (UI, 303 Zeilen)
**Repo-Stand:** Branch `fix/systemaudit-p2-hygiene` @ `78ba75ee` (enthält `main` + P0-PR #771 + P1-PR #772)
**Art:** Read-only-Analyse. Jedes Finding wurde gegen den **aktuellen** Code-/Repo-Zustand geprüft (git log, `gh issue list`, Datei-/Grep-Verifikation) — nicht blind aus den Audit-Dokumenten übernommen.

> **Wichtig:** Die beiden Audit-Dokumente sind **einen Tag alt, aber bereits teilweise überholt.** Seit dem Audit wurden zwei Sprints gemerged (PR #771 „P0 release-gate", PR #772 „P1 fachlichkeit"). Dieser Restplan bildet **nur den verbleibenden Rest** ab.

---

## 1. Kurzzusammenfassung

### 1.1 Zahlen

| Kennzahl | Wert |
|---|---|
| Getrackte Findings gesamt (beide Dokumente, konsolidiert) | **101** |
| davon **erledigt** (verifiziert im Code) | **19** |
| davon **teilweise erledigt** (Restarbeit benannt) | **7** |
| davon **in Arbeit** (paralleler Developer-Agent) | **1** |
| davon **obsolet / Fehlbefund** (im Audit falsch klassifiziert) | **3** |
| davon **offen** | **71** |
| Geschätzter Restaufwand | **≈ 41–58 Personentage** (ohne die 7 reinen Produktentscheidungen) |

**Verteilung der 71 offenen Findings**

| nach Schweregrad | # | nach Bereich | # | nach Aufwand | # |
|---|---|---|---|---|---|
| kritisch/Blocker | 1 | Frontend/UI | 33 | trivial (<1 h) | 14 |
| hoch | 18 | Infra/Ops | 13 | klein (<1 Tag) | 31 |
| mittel | 34 | Backend/API | 12 | mittel (1–3 Tage) | 19 |
| niedrig | 18 | Security | 6 | groß (>3 Tage) | 7 |
| | | Test/CI | 4 | | |
| | | Doku/SE | 3 | | |

### 1.2 Bilanz der bereits gelaufenen Sprints

**PR #771 „P0-release-gate" (gemerged, in `main`)** — 6 von 9 P0-Findings vollständig geschlossen, 3 teilweise:

| P0-Item | Status | Verifikation |
|---|---|---|
| 2 · RLS-Lücken ~20 Tabellen | ✅ **erledigt** | `persistence/migrations/0067_rls_remaining_pl_tables.py` + `workflow/migrations/0015_workflow_rls_policies.py` (27 Tabellen), CI-Lint |
| 4 · Kein MCP-Throttling | ✅ **erledigt** | `mcp_server/throttling.py`, in allen 3 Views verdrahtet (`views.py:181/278/373`) |
| 6 · Keine Celery-Time-Limits | ✅ **erledigt** | `settings.py:623–624` (`CELERY_TASK_SOFT_TIME_LIMIT`/`TIME_LIMIT`) |
| 7 · Redis-Eviction-Risiko | ✅ **erledigt** | commit `da698794` |
| 8 · Test-Settings durch Root-`.env` kontaminiert | ✅ **erledigt** | commit `ce914f16` |
| 9 · Dead unauth. `se_metrics/views.py` | ✅ **erledigt** | Datei existiert nicht mehr |
| 1 · Dependency-Lock EOL | ⚠️ **teilweise** | CI-Drift-Check + `backend/REGENERATING_LOCK_FILE.md` da, aber **Lock unverändert** → siehe SA-01 |
| 3 · EventBus-Pfad | ⚠️ **teilweise** | (a) Subscriber-Fehler + (c) Webhook-Registrierung erledigt; **(b) on-commit-Outbox offen** → SA-02 |
| 5 · `str(exc)`-Leak | ⚠️ **teilweise** | `protocol_handler.py` + `metrics_views.py` sauber; **`icd_views.py` 12 Stellen offen** → SA-03 |

**PR #772 „P1-fachlichkeit" (gemerged)** — 4 von 8 P1-Findings vollständig, 4 teilweise:

| P1-Item | Status | Verifikation |
|---|---|---|
| 11 · L0–L4-Mapping-Konflikt | ✅ **erledigt** | `41edb282` — Enum L1..L4 realigned, `decompose()` setzt `child.level`, neue Audit-Regel CONS-P11, Migration `persistence/0068` |
| 15 · `supersedes`-Phantom-Typ | ✅ **erledigt** | `c1a04f58` — Dead-Code-Pfade entfernt |
| 16 · Soft-Delete-Inkohärenz | ✅ **erledigt** | `137f7632` — `lifecycle_status` als echter Mirror, `is_outdated_equivalent` für adr/risk nachgezogen, Migrationen `workflow/0016+0017` |
| 10 · Traceability-Matrix stale | ⚠️ **teilweise** | `77c1a4df` — Matrix wird jetzt generiert (`scripts/generate_traceability_matrix.py`); **SN-Implementation-States nicht neu bewertet** → SA-30 |
| 12 · Layer-Verletzungen | ⚠️ **teilweise** | `32f3a2aa` — Exceptions nach `persistence/errors.py` gehoben; **4 `ServiceBase`-Importe + 5 weitere Layer-Brüche offen** → SA-20..SA-24 |
| 13 · REST-Fehlerhüllen | ⚠️ **teilweise** | `e447f101` — Envelope vereinheitlicht, Glossary-`__dict__` gefixt; **9 Serializer-umgehende Write-Handler offen** → SA-25 |
| 14 · sync-LLM-Pfad | ⚠️ **teilweise** | `7f52d2d2` — 2 von 7 `input_tokens=0`-Stellen gefixt, LLM aus `@atomic_transaction`; **5 Stellen + Flag-Semantik offen** → SA-26/SA-27 |

**Aktueller Branch `fix/systemaudit-p2-hygiene`** enthält bisher **nur die Audit-Dokumente + agent-meta-Updates**, noch keine Fixes. Die Farb-Token-Arbeit (Issues #140/#161) läuft parallel im Working Tree.

### 1.3 Top-3-Prioritäten

1. **UI-Bedienschutz (AP-3, UI-P0)** — 11 Findings, davon 1 Blocker (Interview-LLM bricht nach 30 s ab) und 3 Datenverlust-Pfade (Graph-Editor, NeedForm, TestCaseForm). Höchster Nutzer-Impact, keine Architekturänderung nötig, Fix-Muster existieren bereits im Repo. **≈ 5–7 Tage.**
2. **P0-Nachzügler (AP-1)** — `icd_views.py`-`str(exc)`-Leaks (CWE-209, Issue #697 offen), EventBus-Outbox-Crash-Fenster, Dependency-Lock. Kleine Restmenge aus einem als „abgeschlossen" gemergten Release-Gate-Sprint. **≈ 2–3 Tage.**
3. **Prod-Readiness (AP-4)** — Static-Files für /admin/+Swagger broken, keine Cookie-Hardenings, kein Connection-Pooling, keine Image-Scans/SBOM, ghcr-Concurrency-Regression. Das Audit-Verdikt „Prod bedingt ready" bleibt sonst bestehen. **≈ 5–8 Tage.**

---

## 2. Korrekturen an den Audit-Dokumenten

Drei Befunde sind bei Nachprüfung **nicht so haltbar wie klassifiziert** — sie gehören nicht in den Restplan (bzw. mit anderer Schwere):

| Audit-Stelle | Behauptung | Nachprüfung |
|---|---|---|
| §3 P0-1 / §4.6 F1 | „`requirements.lock` schient Django 4.2.30 (6 unpatched CVEs) — **HIGH**" | **Schwere zu hoch.** `backend/Dockerfile:32` und `.github/workflows/ci.yml:94` installieren beide **`requirements.txt`** (Django >=5.2.17, cryptography >=50.0.0). `requirements.lock` wird **nirgends** konsumiert — Grep findet nur Audit-Doku und `REGENERATING_LOCK_FILE.md`. Die Laufzeit ist nicht verwundbar. Realistische Schwere: **MEDIUM** (irreführendes Artefakt / Supply-Chain-Hygiene). |
| §4.4 Befund 2 / §3 P2 | „GraphToolbar.tsx:45–103 — 6 Buttons ohne `data-testid`" | **Fehlbefund**, bereits vom UI-Audit selbst korrigiert (UI-Doc §2 und §5.7): alle 6 Toolbar-Buttons haben Testids. Zusätzlich verifiziert: `DiagramGraphEditorPage.tsx` hat 14 `data-testid`, `PageHeader.tsx` 7, `ConfirmDialog.tsx` 3 — die Lückenliste in §3 P2 ist überholt. |
| §4.7 Befund 8 | „INFRA-03-Regression (concurrency nicht gepinnt in `ghcr.yml:268–269`)" | **Zeilenangabe/Datei stimmt nicht** — die Datei liegt unter `deployment/docker-compose.ghcr.yml:278`. Der **Befund selbst ist korrekt** (kein `--concurrency`). Wird als SA-42 geführt, aber `deployment/docker-compose.minimal.yml:266` fehlt es ebenfalls → Scope erweitert. |

Ebenfalls zu relativieren: das UI-Audit zählt „~15 `window.confirm()`-Stellen"; verifiziert sind **11** in 10 Dateien (`GlossaryView` ist nicht darunter). Der Befund bleibt gültig, die Menge ist kleiner.

---

## 3. Arbeitspakete

Benennung setzt das bestehende Muster fort (`fix/systemaudit-p<N>-<thema>`).

---

### AP-1 · `fix/systemaudit-p3-release-gate-rest` — P0-Nachzügler
**Priorität: 1 · Aufwand ≈ 2–3 Tage · Bereich: Security/Backend**

Der P0-Sprint wurde als abgeschlossen gemerged, hat aber drei Restposten explizit deferiert. Diese gehören **vor** die Hygiene-Arbeit, weil zwei davon Security-/Datenintegritäts-Charakter haben.

| ID | Finding | Schwere | Aufwand | Quelle |
|---|---|---|---|---|
| SA-03 | `icd_views.py`: 12× `str(exc)` an den Client (CWE-209) — widerspricht der eigenen Maskierungsrichtlinie (fix #108). Repo-weit noch 471 `str(exc)`-Vorkommen (inkl. Tests). | hoch | klein | SA §3 P0-5, §4.6 F16 |
| SA-02 | EventBus: Outbox-Insert erst in `on_commit` → Crash zwischen Commit und Callback verliert das Event dauerhaft. Kein echtes Transactional-Outbox. | hoch | mittel | SA §3 P0-3b, §4.2 #2 |
| SA-01 | `requirements.lock` schient Django 4.2.30 / cryptography 49.0.0 / anthropic 0.120.2. **Nicht laufzeitrelevant** (s. §2), aber irreführend und ein Fehlstart für jeden, der den Lock benutzt. Optionen: regenerieren **oder** löschen + `REGENERATING_LOCK_FILE.md` anpassen. | mittel | klein | SA §3 P0-1, §4.6 F1 |
| SA-04 | Sync-HTTP im Outbox-Claim-TX (`event_bus.py:264–291` + `webhook_dispatcher.py:55–57`) — Row-Lock + offene Connection über externe I/O blockiert den 5s-Poll-Zyklus. Wird durch den Webhook-Fix (jetzt aktiv!) **erst jetzt real**. | hoch | mittel | SA §4.2 #4 |
| SA-05 | DLQ-Umzug innerhalb der Claim-TX — schlägt er fehl, bleibt die Row ewig `published=False`. | niedrig | trivial | SA §4.2 #12 |

**Hinweis:** SA-04 ist eine **Folge** des P0-Fixes `ad1179f2` — der WebhookDispatcher war vorher tot, das Blockier-Risiko damit theoretisch. Jetzt ist es real. Das ist in keinem Audit-Dokument so verknüpft und sollte im PR benannt werden.

**Bestehendes Issue:** #697 („Sweep remaining str(exc) exception-leak sites — ~40+ sites incl. icd_views.py", Label `high,security`) deckt SA-03 exakt ab. SA-01/02/04/05 haben kein Issue.

---

### AP-2 · `fix/systemaudit-p2-hygiene` — Hygiene (**läuft bereits**)
**Priorität: 2 (parallel) · Bereich: Frontend/Doku/CI**

| ID | Finding | Schwere | Aufwand | Quelle |
|---|---|---|---|---|
| SA-06 | **Farb-Token-Enforcement / hardcodierte Farben** (9 Fundstellen + rgba-Verstöße) | mittel | — | **läuft bereits, siehe Branch-Commit** (Issues #140/#161) |
| SA-07 | i18n-Backlog: `MISSING_KEY_BASELINE = 145` in `frontend/src/test/i18n-parity.test.ts:137` — 145 im Code referenzierte Keys fehlen in **beiden** Locales; `t(key, "default")` leakt Englisch ins DE-UI. Historie 174→180→145. | mittel | mittel | SA §3 P2, §4.4 #1; UI §4 P2 |
| SA-08 | Dead Code entfernen: `RequirementEditors/TraceabilityPanel.tsx`, **zwei** verwaiste `TestcaseList.tsx` (`components/Testcases/` **und** `components/TestCases/` — Case-Variant-Duplikat!), `TraceabilityView/TraceLinksForm.tsx` (705 Z., nur Selbsttest), `IcdView/SimilarIcdsPanel.tsx`, toter Delete-Dialog `ArchitectureEditors.tsx:709–754` | niedrig | klein | UI §4 P2 |
| SA-09 | Coverage-Gates fehlen: `backend/pyproject.toml` hat `[tool.coverage.run]`, aber **kein `fail_under` und kein `--cov` im CI-Aufruf**; Frontend hat gar keinen Coverage-Block. | mittel | klein | SA §3 P2, §4.8 |
| SA-10 | `COMMON_ERROR_RESPONSES` (`rest_api/openapi.py:71`) ist toter Code — nur von den eigenen Tests referenziert, nie an `extend_schema` verdrahtet. `extend_schema` nur auf ~10 von ~200 Operationen. | niedrig | mittel | SA §4.3 F-08 |
| SA-11 | Doppelt gemountete TraceLink-Routen (`urls.py:162` `tracelinks` + `:169` `trace-links`) → OpenAPI-Duplikate. Bewusste Compat (fix #233) → Deprecation-Header + Sunset-Datum statt Entfernung. | niedrig | trivial | SA §4.3 F-16 |
| SA-12 | 3 parallele Tree-Implementierungen (`WorkspaceTree`, `RequirementTreeNode`, `GoalsTree`) — im Ratchet-Test dokumentiert. | niedrig | groß | SA §4.4 #6 |
| SA-13 | Globale `OrderingFilter`/`SearchFilter` (`settings.py:412–415`) sind auf der ViewSet-Architektur wirkungslos → tote Konfiguration entfernen oder nutzen. | niedrig | trivial | SA §4.3 F-17 |
| SA-14 | `_WRITE_TOOL_PREFIXES` (`tool_registry.py:133`) listet nicht existierendes `prompt_template.delete` → Katalog-Drift. | niedrig | trivial | SA §4.3 F-15 |

> **Konfliktwarnung:** SA-06 modifiziert aktuell u. a. `RequirementList.tsx` und `workspace-tree.tsx`. AP-3 (UI-05, Requirement-Delete) und SA-12 fassen dieselben Dateien an → **nicht parallel starten.**

---

### AP-3 · `fix/systemaudit-p4-ui-bedienschutz` — UI-P0: Blocker, Datenverlust, Bedienschutz
**Priorität: 3 (höchster Nutzer-Impact) · Aufwand ≈ 5–7 Tage · Bereich: Frontend**

Alle 11 UI-P0-Findings wurden gegen den Code geprüft und sind **unverändert offen**.

| ID | Finding | Schwere | Aufwand | Verifikation |
|---|---|---|---|---|
| UI-01 | **BLOCKER:** Interview-LLM-Calls mit 30 s statt 180 s Timeout. `_LONG_RUNNING_PATH_SEGMENTS` (`api/client.ts:156–163`) enthält 6 Pfade — **`/interviews/` fehlt**; `api/interviews.ts` übergibt **kein** `timeoutMs`. Reale LLM-Latenz >30 s bricht Interviews mit generischer Fehlermeldung ab. | Blocker | trivial | verifiziert |
| UI-02 | Graph-Editor verliert **alle** Edits bei Navigation: kein Autosave, kein Dirty-Indicator, kein Guard. Kontrast: `CanvasEditor` 5 s-Autosave, `MermaidEditor` 2 s-Debounce. Repo-weit **0×** `beforeunload`/`useBlocker`. | hoch | mittel | verifiziert (`DiagramGraphEditorPage.tsx`) |
| UI-03 | `CanvasEditor.tsx:1064–1078`: globaler Delete/Backspace-Keydown prüft nur `active?.isEditing`, **nicht das Event-Target** → löscht selektierte Objekte, während man in beliebigen anderen Feldern tippt. Korrektes Muster: `GraphCanvas.tsx:137–138`. | hoch | trivial | verifiziert |
| UI-04 | TestRun-Result-Erfassung existiert nicht im SPA: `addResult`/`addResultsBulk` (`api/test-runs.ts:46/68`) haben **null Aufrufer**; `TestRunDetailEditor` ist read-only. Results nur via REST/MCP/CI. | hoch | groß | verifiziert |
| UI-05 | Requirement-Delete aus der UI nicht erreichbar (Dead Code): Confirm-Overlay existiert (`RequirementList.tsx:162/306/318`), aber `setConfirmDeleteId` wird nie ≠ null gesetzt. Der Test `RequirementEditors.test.tsx:656` **dokumentiert** die Lücke bereits. | hoch | klein | verifiziert |
| UI-06 | `NeedForm.tsx`: **0** Treffer für `useFormDirty`/`isDirty` → Need-Wechsel verwirft Edits stumm. Zusätzlich `CustomFieldsEditor` (`:413`) **ohne** `key={need.id}` → #673-Contamination-Bug. Fix-Muster: `RequirementForm.tsx:917`. | hoch | klein | verifiziert |
| UI-07 | `TestCaseForm.tsx`: **0** Treffer für Dirty/Unsaved → Verlust beim Maskenwechsel. Muster: `RequirementEditors` (`req-unsaved-changes-dialog`). | hoch | klein | verifiziert |
| UI-08 | `api/architecture.ts` sendet **kein** `expected_version` → der Backend-409-Optimistic-Locking-Schutz ist aus der UI nie auslösbar. | hoch | klein | verifiziert (0 Treffer) |
| UI-09 | 6 destruktive Aktionen ohne jede Bestätigung: User-Deactivate, Tenant-Admin-Grant/Revoke, Rollen-Suspend, Custom-Field-Definition-Delete, Theme-Palette-Delete, Trace-Link-Delete. | hoch | klein | UI §4 P0-9 |
| UI-10 | 5–6 tastatur-unbedienbare Listen/Autocompletes (`li onClick`/`div onClick`): BaselinesView, TestRunsList, Glossary-Zeilen, Risk-Owner-Autocomplete, ICD-Similar-Items, ImpactView-Baum ohne `tree`-Rolle. | hoch | mittel | UI §4 P0-10 |
| UI-11 | i18n-Keys `adrs.summary` / `risks.summary` / `issues.summary` fehlen in **beiden** Locales → `PageHeader` rendert die Roh-Keys als Seiten-Summary. | hoch | trivial | verifiziert (`AdrEditors.tsx:137`, `RiskEditors.tsx:134`, `IssueEditors.tsx:134`; 0 Treffer im Locale) |

**Empfohlene Teilung:** UI-01/03/05/06/07/08/11 sind Ein-Datei-Fixes mit vorhandenem Muster → ein schneller PR („UI-P0 quick wins", ≈ 1,5 Tage). UI-02/04/09/10 sind je eigenständige Vorhaben.

**Produktklärung vor Umsetzung:** UI-05 — war der Requirement-Delete **bewusst** entfernt oder ist das eine Regression? UI-04 — soll das Result-Entry-Grid gebaut werden oder ist CI/MCP der gewollte Erfassungsweg?

---

### AP-4 · `fix/systemaudit-p5-prod-readiness` — Betrieb & Produktionsreife
**Priorität: 4 · Aufwand ≈ 5–8 Tage · Bereich: Infra/Ops/CI**

Alle Findings verifiziert offen (Grep gegen `settings.py`, `docker-compose*.yml`, `.github/workflows/`).

| ID | Finding | Schwere | Aufwand | Quelle |
|---|---|---|---|---|
| SA-40 | **Static-Files broken:** `collectstatic` im Build, aber nichts served `/static/` — kein WhiteNoise (0 Treffer in `requirements.txt`/`settings.py`), nginx proxied nur `/api/` + `/mcp/`. Django-Admin und Swagger-UI im Prod-Setup ohne Assets. | hoch | klein | SA §3 P1-16, §4.7 #6 |
| SA-41 | **Cookie-/TLS-Hardenings fehlen:** `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_SSL_REDIRECT`, `SECURE_PROXY_SSL_HEADER` — **alle 0 Treffer** in `settings.py`. | hoch | trivial | SA §4.6 F12, §4.7 #10 |
| SA-42 | **`--concurrency` nicht gepinnt** in `deployment/docker-compose.ghcr.yml:278` (INFRA-03-Regression) — und ebenso nicht in `deployment/docker-compose.minimal.yml:266`. Root-`docker-compose.yml:338` hat es korrekt. | mittel | trivial | SA §4.7 #8 (Pfad im Audit falsch, s. §2) |
| SA-43 | **Kein DB-Connection-Pooling:** `CONN_MAX_AGE` — 0 Treffer in `settings.py` → neue Connection pro Request; keine `connect_timeout`/`statement_timeout`-Defaults. | mittel | klein | SA §4.7 #5 |
| SA-44 | **Kein Image-Scan / SBOM / Signierung** in `docker-publish.yml` — 0 Treffer für trivy/grype/syft/cosign/sbom in allen Workflows. | hoch | mittel | SA §4.7 #4 |
| SA-45 | **Kein Backend-Lint/Typecheck in CI** — 0 Treffer für ruff/mypy in `ci.yml`. | mittel | klein | SA §4.7 #16 |
| SA-46 | **Keine Request-ID / Correlation-ID** — 0 Treffer in `settings.py`; Logs ohne Request-Korrelation. | mittel | klein | SA §3 P1-16, §4.7 #11 |
| SA-47 | Keine Metriken/Tracing/Alerting (kein Prometheus-Endpoint, kein OTel). | mittel | groß | SA §4.7 #12 |
| SA-48 | `frontend: user: root` (`docker-compose.yml:402`) konterkariert das Non-Root-Hardening der anderen Services. | mittel | trivial | SA §4.7 #9 |
| SA-49 | Gunicorn ohne `--timeout`/`--graceful-timeout`/`--max-requests`, kein Config-File; kein `stop_grace_period` an den Services. | mittel | klein | SA §4.7 #7 |
| SA-50 | Backups lokal, ohne Monitoring/Restore-Test; kein `pg_dump`-Erfolgs-Healthcheck am `postgres-backup`-Sidecar. | niedrig | klein | SA §4.7 #13 |
| SA-51 | Redis-Passwort in Prozess-Cmdline sichtbar (`redis-cli -a` im Healthcheck). | niedrig | trivial | SA §4.7 #14 |
| SA-52 | Postgres 384 M ohne `reservation`; knapp für pgvector/HNSW-Spikes. `MEDIA_ROOT` fehlt trotz 100 M nginx-Limit. | niedrig | trivial | SA §4.7 #15, §4.7 Settings |

---

### AP-5 · `fix/systemaudit-p6-ui-ux-a11y` — UI-P1: UX-Korrektheit & Barrierefreiheit
**Priorität: 5 · Aufwand ≈ 8–12 Tage · Bereich: Frontend/UI-Design/A11y**

Alle aus `SYSTEMAUDIT_UI_2026-08-27.md` §4 P1. Keines davon hat ein bestehendes Issue außer den drei unten genannten Überschneidungen.

| ID | Finding | Schwere | Aufwand |
|---|---|---|---|
| UI-20 | Confirm-Pattern vereinheitlichen: **11** verifizierte `window.confirm()`-Stellen in 10 Dateien → `ConfirmDialog`. (Audit sagt „~15" — überschätzt.) | mittel | mittel |
| UI-21 | GH-513-Baseline-Override ohne Rollen-Gating im UI — Panel erscheint für alle, Nicht-Berechtigte bekommen erst nach Submit einen 403-Rohstring. | mittel | klein |
| UI-22 | Preset-Downgrade (extended→minimal) feuert sofort beim Radio-Wechsel, ohne Warnung (`WorkspaceSettings.tsx:397`). | mittel | trivial |
| UI-23 | `MermaidEditor` persistiert syntaxfehlerhafte Quelle — Autosave prüft `isDirtyRef`, nicht `validationError`. | mittel | trivial |
| UI-24 | Escape/Backdrop-Guards für Draft-Dialoge: `CreateTraceLinkDialog` (Escape während `isSubmitting`), Decompose-Draft-Verlust, Workflow-Editor-Dialog-Drafts; `ConfirmDialog` ohne `isSubmitting`-Guard. | mittel | klein |
| UI-25 | **Label-Assoziations-Kluster** (9+ Stellen): DeriveRequirementForm, CreateTraceLinkDialog (source/target), MarkdownPreview-Textarea, ReqTraceLinkPanel-Selects, GraphInspectorPanel (alle Felder), Adr/Risk/IssueForm, AttributeVisibilityAdmin (28 Checkboxen ohne accessible name), **`restore-confirmation-input` (sicherheitskritisch, nur placeholder)**, prompt-variable-inputs. | mittel | mittel |
| UI-26 | Interview: Chat-Transcript ohne `role="log"`/`aria-live`; Widget-Toggle ohne `aria-expanded`/`aria-controls`; Grounding-Kandidaten ohne confirm/ignore-UX (Backend-API existiert). | mittel | mittel |
| UI-27 | A11y-Detailbatch: WorkspaceCard Enter-only (kein Space), Sidebar-Search placeholder-as-label, Mobile-Overlay nicht tastatur-schließbar, 3 Resize-Handles mouse-only (RightSidebar/SplitView/Workflow-Inspector), `TransitionEdge`/`GraphEdge` `tabIndex=-1`, RightSidebar 3 tote Icon-Buttons, TraceSpine-Warnung ohne aria-label. | mittel | mittel |
| UI-28 | `MainGoalPanel.tsx:187–194`: Generate ohne Busy-State → Doppelklicks feuern parallele LLM-Requests; kein `is_mock_fallback`-Indikator (Backend-Feld existiert seit `7f52d2d2`!). | mittel | klein |
| UI-29 | Goals: `change_reason` als generierter String statt User-Prompt — `ArchiveConfirmDialog` ohne Textarea, Audit-Gate umgangen. Kontrast: `WorkflowStatusEditor` macht es korrekt. | mittel | klein |
| UI-30 | CSV-Import: kein Partial-Success-Zustand, keine Row-Preview, kein Column-Mapping, Dropzones nicht keyboard-bedienbar, Fehlerliste auf 10 gekappt. | mittel | mittel |
| UI-31 | `useRequirementData.ts:76` verschluckt Listen-Fehler → Ladefehler sieht aus wie leere Liste. `useNeedData` macht es korrekt. | mittel | trivial |
| UI-32 | ADR-Supersede-Flow (REQ-150) im UI nicht vorhanden — kein Button, keine `superseded-by`-Anzeige. Backend-Fähigkeit existiert (`adr_service.py:495–525`). | mittel | mittel |
| UI-33 | Manueller Derive (Need): partieller Fehler ohne Rollback/Nachricht → Requirement bleibt verwaist. AI-Accept analog (kein Fortschritts-Tracking). | mittel | klein |
| UI-34 | Reviews: Ziel-State als Rohtext (`toTitleCase("Freigegeben")`); Approver sieht nicht, **warum** Approve disabled ist; Queue ohne Pagination. | mittel | klein |
| UI-35 | `MetricsDashboard`: kein „nicht berechnet"-Empty-State, Thresholds nirgends angezeigt (Status nur über Farbpunkt), Help-Toggle ohne `aria-label`/`aria-pressed`, `metric-sparkline` 5× dupliziert, `aria-label="trend"` 5× identisch. | mittel | klein |
| UI-36 | `ImpactView`: kein „0 Treffer"-State, Suchinput placeholder-as-label. | niedrig | trivial |
| UI-37 | ADR-Titel-Placeholder zeigt Need-Text („e.g. As a user, I need…", `AdrEditors.tsx:243`) + „--"-Placeholder-Müll an 3 Stellen. | niedrig | trivial |
| UI-38 | `WorkflowEditorPage`: Toast-Timer ohne Cleanup → `setState`-after-unmount möglich. | niedrig | trivial |
| UI-39 | `RiskForm`: kein `detection`-Feld (1–10) trotz Backend/MCP-Schema; keine Risk-Matrix (probability×impact); `risk_score` nirgends angezeigt. | mittel | mittel |
| UI-40 | `PermissionMatrix` ohne Unsaved-Schutz; `DecomposePanel` **ohne Unit-Tests**, `breadth`/`depth` können 0/NaN werden (Backend-Cap 10 nur serverseitig); I1–I5-Invariant-Verstöße als unstrukturierter Rohstring. | mittel | mittel |
| UI-41 | `SystemHealthDialog` doppelter Scroll-Lock (Konflikt mit Dialog-Unlock); `SplitView` `classList.add('dragging')` ohne wirksames CSS; Tabs ohne Arrow-Key-Navigation (SystemSettings, PresetSegmentedControl, WorkspaceSettings). | niedrig | klein |

**Überschneidung mit bestehenden Issues:** UI-25/UI-27 überlappen mit **#741** (Icon-only-Buttons ohne aria-label) und **#677** (fehlende aria-live-Regionen); UI-20 überlappt mit **#670** (uneinheitliche Löschbestätigungen).

---

### AP-6 · `fix/systemaudit-p7-backend-konsistenz` — Backend/API-Konsistenz
**Priorität: 6 · Aufwand ≈ 6–9 Tage · Bereich: Backend/API/Security**

| ID | Finding | Schwere | Aufwand | Quelle |
|---|---|---|---|---|
| SA-25 | 9 Write-Handler lesen `request.data` direkt und umgehen die Serializer-Validierung + `FreeTextSanitizationMixin`. (Der Glossary-`__dict__`-Teil desselben Findings ist erledigt.) | hoch | mittel | SA §4.3 F-04 |
| SA-26 | `input_tokens=0` an **5 verbliebenen Stellen**: `ai_review_service.py:411`, `architecture_decompose_service.py:826`, `interview_service.py:624/1216/1365`, `traceability_suggest_service.py:679` → Token-Budget weiterhin teilblind. Der Fix-Helper `approximate_token_count()` existiert bereits. | mittel | klein | SA §3 P1-14 (Rest), commit `7f52d2d2` |
| SA-27 | `is_mock_fallback`-Semantik divergiert: `ai_derivation_service` meldet aufgelöstes `LLM_PROVIDER=mock` als `False`, `bundle_compression_service` als `True`. Im P1-Commit **bewusst** offen gelassen. | mittel | klein | commit `7f52d2d2` |
| SA-28 | **PermissionCache-Invalidierung nur pro Thread** (`permission_cache.py`, `_ThreadLocalCacheStore`) → bis 60 s stale **Allow**-Entscheidungen nach Revoke. Sicherheitsrelevant. | hoch | mittel | SA §3 P1-15, §4.1 #7 |
| SA-29 | presets-Prozess-Cache (`gate.py:54–57/161–170`) ohne Cross-Worker-Invalidierung. | mittel | klein | SA §4.1 #8 |
| SA-15 | `presets/gate.py:91/102`: `Workspace.unscoped` + `WorkspacePresetConfig.unscoped` mit caller-gelieferter `workspace_id` **ohne Tenant-Abgleich** → Cross-Tenant-Pfad. Verifiziert unverändert. | hoch | klein | SA §4.1 #6 |
| SA-16 | `MainGoal.sequence_number`-Race (read-then-write ohne Lock/Constraint). | mittel | klein | SA §4.2 #6 |
| SA-17 | `resilience/policy_engine.py:112–134`: Timeout ohne Wallclock-Garantie — nach Timeout blockt `shutdown(wait=True)` bis zum realen Ende; Worst-Case (retries+1)×Dauer. Docstring-Claim „hard timeout" unzutreffend. | mittel | mittel | SA §4.2 #5 |
| SA-18 | `circuit_breaker.py`: `_locked_or_create`-Race (IntegrityError → 500 statt Retry); `failure_count` ohne Zeitfenster. | niedrig | klein | SA §4.2 #10/#11 |
| SA-19 | ADR-01-Buchstabenverstöße verifiziert offen: `diagram_views.py:143`, `diagram_canvas_views.py:94`, `icd_views.py:206` — direkte Model-Queries in DRF-Views. | mittel | klein | SA §4.2 #9 |
| SA-20 | Plain ViewSets (`diagram_views.py:60`, `icd_views.py:63`, `interview_views.py:97`) umgehen die `BaseEntityViewSet`-Guards (malformed-UUID-400, FreeTextSanitization, Preset-Gate). Überschneidet sich mit dem offenen Issue **#724**. | mittel | mittel | SA §4.3 F-10 |
| SA-21 | Layer-Rest: `workflow/lifecycle_manager.py:80–95/445–449` kennt `application.models`; `traceability/service.py:190/511` + `baseline/state_capture.py:247/404` lazy `application`/`icd`-Importe; `llm_adapter` importiert `resilience`/`memory`; `persistence/models.py:1168/1220` importiert `workflow`. 4× `from application.base import ServiceBase` in `auth_tenancy` (im P1-Commit **bewusst** als legitim eingestuft). | mittel | groß | SA §3 P1-12, §4.1 #1–#5 |
| SA-22 | `workflow/lifecycle_manager.py:449`: pk-keyed UPDATE ohne Tenant-Prädikat. Durch die neuen `workflow`-RLS-Policies (`0015`) **abgemildert** — Restrisiko prüfen und ggf. schließen. | mittel | klein | SA §4.6 F8 |
| SA-23 | `baseline/views.py:73` `scope_preview` mit `AllowAny` — anonyme Aufrufer erhalten 200 statt 401 (kein Cross-Tenant-Leak, Ergebnis leer). Verifiziert unverändert. | niedrig | trivial | SA §4.1 #12, §4.6 F4 |
| SA-24 | Archivierungs-Task `audit.archive_lifecycle_manager` **nicht** in `CELERY_BEAT_SCHEDULE` (nur `application.dispatch_outbox_events` ist dort) → monatliche Archivierung läuft nie automatisch. Verifiziert. | mittel | trivial | SA §4.1 #9 |
| SA-31 | **CSV-Formel-Injektion** im Workspace-Export: `export_service.py:211` `_csv_cell` gibt Strings unverändert zurück — keine `=`/`+`/`-`/`@`-Neutralisation. Der Bundle-Pfad neutralisiert. Verifiziert unverändert. | mittel | trivial | SA §3 P1-17, §4.6 F5 |
| SA-32 | Refresh-Rotation **ohne Reuse-Detection** (`auth_views.py:330–345`) — gestohlener Refresh-Token bleibt bis Ablauf nutzbar. | mittel | mittel | SA §3 P1-17, §4.6 F7 |
| SA-33 | LLM-`base_url`-SSRF: admin-gated und URLField-validiert, aber **kein Private-CIDR-Block**. | mittel | klein | SA §4.6 F9 |
| SA-34 | API-Keys als bare SHA-256 ohne Pepper. | niedrig | klein | SA §4.6 F11 |
| SA-35 | `sm_*`-Tabellen mit rohem `tenant_id` statt `TenantManager`. | niedrig | klein | SA §4.6 F14 |
| SA-36 | `csrf_exempt` auf den MCP-Views ohne Cookie-Auth-Assertion (aktuell korrekt, aber ungeschützte Invariante). | niedrig | trivial | SA §4.6 F15 |
| SA-37 | `llm_adapter/router.py:371–408`: Sync-Timeout-Thread setzt nur `TenantContext.set_tenant()`, **kein** `SET app.current_tenant` → RLS greift im Thread nicht. Muster-Fix existiert in `tasks.py:133–146` (#444). Wird durch die neuen RLS-Policies **schärfer**. | mittel | klein | SA §4.1 #10 |
| SA-38 | `rest_api/metrics_views.py:45–46`: `set_tenant` ohne `finally`/`clear` → Thread-Local-Leak über Pool-Worker. | mittel | trivial | SA §4.3 F-09 |
| SA-39 | `audit/models.py:315–327` + `writer.py:206`: redundanter EXISTS-Query je Insert; `switch_preset` (`gate.py:251–269`) lost-update ohne `select_for_update`; API-Key-Max-TOCTOU. | niedrig | klein | SA §4.1 #11/#13/#14 |

---

### AP-7 · `fix/systemaudit-p8-fachlichkeit-doku` — SE-Fachlichkeit, Doku-Drift, Tests
**Priorität: 7 · Aufwand ≈ 4–6 Tage · Bereich: Doku/SE/Test**

| ID | Finding | Schwere | Aufwand | Quelle |
|---|---|---|---|---|
| SA-30 | **SN-Implementation-States grob veraltet** (`docs/se/L0/SN_Stakeholder_Needs.md`, 50× „Not Implemented" — teilweise für implementierte Features). Der Matrix-Generator trägt die Marker **verbatim** durch, prüft sie aber nicht gegen Code. → Bulk-Neubewertung + State-Ownership festlegen. | hoch | mittel | SA §4.5 #3 |
| SA-53 | **AGENTS.md-Faktendrift verifiziert unverändert**: „5 Services" (real 8), „Django 4.2+" (real 5.2 LTS), „16 ViewSets + 2 APIViews" (real 28 + ~66), „11 Tool-Gruppen, 40+ Tools" (real 23/27/171), „Axios-Client mit auto-Bearer-Token-Injection" (real fetch + httpOnly-Cookie — **beschreibt ein falsches Sicherheitsmodell**), „17 Component-Bereiche" (real 41). → Header aus Code-Buchhaltung generieren. | mittel | mittel | SA §2, §4.3 F-13, §4.4 #3, §4.7 #17 |
| SA-54 | **README-Testzahlen veraltet** (`README.md:836`: „~1,400 pytest … + 111 Playwright" — real 5.768 / 1.363 / 274). | niedrig | trivial | SA §4.8 |
| SA-55 | `docs/REQUIREMENTS.md:1` „Successfully migrated"-Kopf täuscht; 188 Kampagnen-REQs mit Solution-Creep; zwei parallele ID-Schemata ohne Abbildungsregel. | mittel | klein | SA §4.5 #4 |
| SA-56 | `workspace_context_service.py:51–76`: `open_requirements_count` zählt `implemented`/`verified` als „offen" (`status != approved`) → Definition auf „nicht terminal-positiv laut Preset" umstellen. | mittel | klein | SA §4.5 #7 |
| SA-57 | `presets/registry.py:236/354–402`: Custom-Presets nur im In-Memory-Dict, nicht persistiert; `get_preset_config` wirft für Custom-Namen. → persistieren **oder** Custom-Pfad bis v2 sperren. | niedrig | mittel | SA §3 P2, §4.5 #10 |
| SA-58 | `registry.py:171–181`: `approval_workflows=False` im Standard-Tier trotz Approver-Gate im Standard-Schema; Flag-Konsument unauffindbar → definieren oder entfernen. | niedrig | trivial | SA §4.5 #12 |
| SA-59 | `docs/se/test_coverage_report.md` konflatiert Needs mit Testbarkeit (alle REQ-L0 „Missing" — Needs sind per Definition nicht unit-testbar) → Report auf L1+ beschränken. | niedrig | trivial | SA §4.5 #13 |
| SA-60 | Doku-Detailkorrekturen: `se-critic`-Verdict „approved_with_fixes" außerhalb des Schema-Vokabulars; „LEAF (terminal)"-Widerspruch zu 19 existierenden L3-COMP-Docs; L0-Gap-Beschreibung halb veraltet; `traceability/models.py` reine TODO-Stub-Datei. | niedrig | klein | SA §4.5 #11/#14/#15, §4.1 #15 |
| SA-61 | **MCP-SSE-Transport dauerhaft ungetestet** — `test_e2e_sse_transport.py` komplett geskippt (6 Skips): deklarierte Capability ohne aktive Regression. | mittel | mittel | SA §4.8 |
| SA-62 | `test_e2e_*`-Integrationstests ohne Klassifizierungs-Marker in den App-Testverzeichnissen; keine einheitliche Factory-Strategie (nur 1 Factory-Datei, sonst manuell). | niedrig | klein | SA §4.8 |

---

### AP-8 · Produktentscheidungen (kein Code bis Entscheid)
**Aufwand: Entscheidungs-Sessions, keine Implementierung**

Diese Punkte sind **keine Bugs**, sondern offene Fragen aus beiden Audits. Sie blockieren teilweise Findings in AP-3/AP-5/AP-6.

| ID | Entscheidung | Blockiert |
|---|---|---|
| D-01 | **MCP-Protokollversion**: eingefroren auf 2024-11-05 (`protocol_handler.py:45`) — bei Streamable-HTTP 2025-03-26+ bleiben oder Negotiation einbauen? Beeinflusst auch F-05 (PARSE_ERROR/INVALID_REQUEST → HTTP 401 statt 400) und F-11 (numerisches `code` vs. String `error_code` am selben Interface). | SA-API-Rest |
| D-02 | **stdio-Transport**: Adapter + Tests existieren, es gibt **keinen** Laufzeit-Einstieg. Aktivieren oder Modul-Docstring/`models.py:17`-TODO entschärfen? | SA §4.3 F-14 |
| D-03 | **ICD-MCP-Parität**: ICDs sind komplett ohne `icd.*`-Tools (MBSE-Kernfähigkeit nur via REST). Tool-Gruppe bauen? Überschneidet mit offenem Issue **#410**. | — |
| D-04 | **Requirement-Delete** (UI-05): bewusst entfernt oder Regression? | UI-05 |
| D-05 | **TestRun-Result-Entry-Grid** (UI-04): SPA-Feature oder CI/MCP-only? | UI-04 |
| D-06 | **Version-Restore** im `VersionPanel` (nur switch/compare vorhanden) und **Baseline-Delete-Button** (existiert, widerspricht der Immutabilitäts-Erwartung). | UI-P2 |
| D-07 | **Extended-Preset produktiv?** Level-Felder waren fast alle NULL, Rule 5/6/7 sind extended-only — ist die rechte V-Modell-Seite im echten Betrieb je verifiziert worden? Nach `41edb282` (Level-Progression) neu zu bewerten. | SE-Roadmap |

---

## 4. Abhängigkeiten und Sequenzierung

```
AP-1 (P0-Rest) ──────────────────────────────────────────► sofort, unabhängig
  │
  └─ SA-04 (Outbox-Sync-HTTP) setzt den P0-Webhook-Fix voraus  [bereits gemerged]

AP-2 (P2-Hygiene, läuft) ──┐
                           ├─ DATEIKONFLIKT ─► AP-3 erst nach Merge von SA-06 starten
AP-3 (UI-P0) ──────────────┘   (RequirementList.tsx, workspace-tree.tsx, MetricsDashboard.tsx)

AP-3 ──────► AP-5 (UI-P1)      UI-P1 baut auf den in AP-3 etablierten Mustern auf
   UI-09 (ConfirmDialog) ─────► UI-20 (window.confirm-Migration): gleiches Primitiv
   UI-02 (Dirty-Guard Graph) ─► UI-24 (Escape/Backdrop-Guards): gleicher Guard-Mechanismus
   UI-06/07 (Dirty-Guards) ───► UI-40 (PermissionMatrix-Unsaved): gleicher Hook

AP-4 (Prod) ────────────────────────────────────────────► unabhängig, parallelisierbar
   SA-41 (Cookie-Secure) ─► KOLLIDIERT mit dokumentiertem HTTP-Quickstart
                            (AUTH_COOKIE_SECURE default True) → gemeinsam lösen
   SA-44 (Image-Scan) ────► SA-01 (Lock) zuerst klären, sonst Scan-Rauschen

AP-6 (Backend) ─────────────────────────────────────────► unabhängig
   SA-15 (presets-Gate unscoped) ─► vor SA-29 (presets-Cache): gleiche Datei
   SA-37/SA-22 (RLS-Threads) ─────► profitieren von den neuen RLS-Policies aus P0
   SA-25 (Serializer-Bypass) ─────► vor SA-20 (BaseEntityViewSet-Guards): gleiche Schicht

AP-7 (Doku/SE) ─────────────────────────────────────────► unabhängig
   SA-30 (SN-States) ─► SETZT VORAUS: Matrix-Generator aus 77c1a4df [erledigt]
   SA-53 (AGENTS.md) ─► sollte NACH allen strukturellen APs laufen,
                        sonst driftet die frisch generierte Buchhaltung erneut

AP-8 (Entscheidungen) ──► D-04 blockiert UI-05, D-05 blockiert UI-04
                          → VOR AP-3-Planung klären
```

**Empfohlene Reihenfolge:**

1. **AP-8 Teilklärung** (D-04, D-05) — 1 kurze Session, entblockt AP-3
2. **AP-1** (P0-Rest) — parallel zu AP-2, andere Dateien
3. **AP-2** (läuft) fertigstellen
4. **AP-3** (UI-P0) — nach AP-2-Merge wegen Dateikonflikten
5. **AP-4** (Prod) — jederzeit parallel, eigenes Dateiuniversum
6. **AP-5** (UI-P1) und **AP-6** (Backend) parallel
7. **AP-7** (Doku) zuletzt — SA-53 als **letzter** Schritt

---

## 5. GitHub-Issue-Empfehlung

**Ist-Zustand:** Das Label **`audit-2026-08-27` existiert bereits, hat aber null Issues.** Für die Findings dieses Audits wurde bisher kein einziges Issue angelegt — die Arbeit lief direkt über PR #771/#772.

**Bereits abgedeckt durch offene Issues (kein neues Issue nötig, nur Label ergänzen):**

| Finding | Bestehendes Issue |
|---|---|
| SA-03 (`str(exc)`-Sweep, icd_views) | **#697** `[high,security]` — deckt es exakt ab |
| SA-06 (Farb-Tokens) | **#140** + **#161** `[audit-2026-07]` — in Arbeit |
| UI-20 (Confirm-Pattern) | **#670** `[ui,ux,design]` — Teilüberschneidung |
| UI-25/UI-27 (Labels, aria) | **#741** `[qa,a11y]` + **#677** `[ui,a11y]` — Teilüberschneidung |
| SA-20 (ViewSet-Guards) | **#724** `[bug,low,api,baseline]` — Teilüberschneidung (malformed UUID) |
| D-03 (ICD-MCP-Parität) | **#410** `[high,se,mcp,audit-2026-08-07]` |
| SA-30 (SE-Doku-States) | thematisch nahe **#583** `[high,qa,se]` (IEEE-29148-Pflichtfelder) |

**Empfohlen neu anzulegen** (nicht von mir angelegt — nur Empfehlung):

- **1 Epic je Arbeitspaket** (AP-1, AP-3, AP-4, AP-5, AP-6, AP-7), Label `audit-2026-08-27` + Bereichslabel, jeweils mit Checkliste der Finding-IDs. → **6 Epics**
- **Einzel-Issues** nur für die 19 Findings mit Schwere ≥ hoch, die nicht schon abgedeckt sind: UI-01…UI-11 (11), SA-02, SA-04, SA-15, SA-25, SA-28, SA-30, SA-40, SA-41, SA-44 → **20 Einzel-Issues**
- **1 Decision-Issue** für AP-8 (D-01…D-07) mit Label `question`
- Der Rest (LOW/MEDIUM-Hygiene) bleibt sinnvollerweise **nur** als Checklisten-Eintrag im jeweiligen Epic — 71 Einzel-Issues wären Verwaltungsaufwand ohne Nutzen.

**Zusätzliche Label-Empfehlung:** `audit-2026-08-27` konsequent setzen, damit `gh issue list --label audit-2026-08-27` zum Fortschrittsanzeiger wird (bei `audit-2026-07` hat das funktioniert — dort sind von 58 Issues noch 3 offen).

---

## 6. Überschneidungen mit älteren Audits

| Älterer Vorgang | Überschneidung mit 2026-08-27 |
|---|---|
| **Systemaudit 2026-07-28** (Issues #99–#186, Label `audit-2026-07`) | Von 58 Issues sind noch **3 offen**: #186 (UI-Gesamtkonzept-EPIC), #161 (Token-System-Reichweite), #140 (128 Hex-Farben). #140/#161 = SA-06, **läuft aktuell**. #186 ist der Rahmen, in den UI-Findings aus AP-5 fachlich hineingehören. |
| **SE-Methodology-Audit 2026-08-07** (Label `audit-2026-08-07`) | 8 Issues noch offen. #410 (MCP fehlen SE-Lifecycle-Tools) ↔ D-03; #414 (zwei ungebrückte ID-Räume) ↔ Trace-/Artifact-ID-Thematik; #408 (keine Pflichtfelder, kein `rationale`) ↔ SA-55; #399 (Baselines sperren keine Artefakte) ist **nicht** im 08-27-Audit enthalten und bleibt eigenständig offen. |
| **UI-Audit beta.5 / QA v1.7.0-beta.3** (#654–#719) | Header-Höhen, Create-Dialog-Inkonsistenz, Sidebar-i18n-Sprachmix. Überschneidet mit UI-P2 (Button-Stile, i18n-Backlog) und teilweise mit SA-07. Nicht dupliziert — beim Abarbeiten von AP-2/AP-5 zusammen mit #718/#719/#651/#654 lösen. |
| **QA Audit Follow-up #737** (#767, #768) | Workflow-Transitions bumpen `version` nicht; ImportService taggt TestCase-Subtyp nicht. **Nicht** im 08-27-Audit — eigenständig, aber thematisch nahe an SA-19/SA-25. |

**Wichtig:** Das 08-27-Audit referenziert #619 („i18n-145-Key-Backlog (#619) abbauen"). **#619 ist geschlossen** — es war das Issue für den *Coverage-Check* selbst, nicht für den Backlog-Abbau. Der 145-Key-Backlog (SA-07) hat damit **kein** trackendes Issue mehr.

---

## Anhang A: Vollständige Finding-Liste

Legende Status: ✅ erledigt · ⚠️ teilweise · 🔧 in Arbeit · ⭕ offen · ❌ obsolet/Fehlbefund

### A.1 Aus `SYSTEMAUDIT_2026-08-27.md`

| ID | Quelle (Abschnitt) | Finding (Kurz) | Schwere | Aufwand | Status | AP |
|---|---|---|---|---|---|---|
| SA-01 | §3 P0-1, §4.6 F1 | requirements.lock EOL-Pins (nicht laufzeitrelevant) | mittel | klein | ⚠️ | AP-1 |
| SA-02 | §3 P0-3b, §4.2 #2 | Outbox-Insert erst in `on_commit` | hoch | mittel | ⭕ | AP-1 |
| SA-03 | §3 P0-5, §4.6 F16 | `str(exc)`-Leak in icd_views (12×) | hoch | klein | ⚠️ | AP-1 |
| SA-04 | §4.2 #4 | Sync-HTTP im Outbox-Claim-TX | hoch | mittel | ⭕ | AP-1 |
| SA-05 | §4.2 #12 | DLQ-Umzug in der Claim-TX | niedrig | trivial | ⭕ | AP-1 |
| SA-06 | §3 P2, §4.4 #4 | 9 hardcodierte Farben / Token-Reichweite | mittel | — | 🔧 | AP-2 |
| SA-07 | §3 P2, §4.4 #1 | i18n 145-Key-Backlog | mittel | mittel | ⭕ | AP-2 |
| SA-08 | UI §4 P2 | Dead Code (5 Dateien, inkl. Case-Duplikat) | niedrig | klein | ⭕ | AP-2 |
| SA-09 | §3 P2, §4.8 | Coverage-Gates fehlen (BE+FE) | mittel | klein | ⭕ | AP-2 |
| SA-10 | §4.3 F-08 | `COMMON_ERROR_RESPONSES` toter Code | niedrig | mittel | ⭕ | AP-2 |
| SA-11 | §4.3 F-16 | tracelinks doppelt gemountet | niedrig | trivial | ⭕ | AP-2 |
| SA-12 | §4.4 #6 | 3 parallele Tree-Implementierungen | niedrig | groß | ⭕ | AP-2 |
| SA-13 | §4.3 F-17 | tote Ordering/SearchFilter-Konfig | niedrig | trivial | ⭕ | AP-2 |
| SA-14 | §4.3 F-15 | `_WRITE_TOOL_PREFIXES`-Katalogdrift | niedrig | trivial | ⭕ | AP-2 |
| SA-15 | §4.1 #6 | presets/gate `unscoped` ohne Tenant-Check | hoch | klein | ⭕ | AP-6 |
| SA-16 | §4.2 #6 | MainGoal `sequence_number`-Race | mittel | klein | ⭕ | AP-6 |
| SA-17 | §4.2 #5 | PolicyEngine-Timeout ohne Wallclock | mittel | mittel | ⭕ | AP-6 |
| SA-18 | §4.2 #10/#11 | CircuitBreaker-Race + Zeitfenster | niedrig | klein | ⭕ | AP-6 |
| SA-19 | §4.2 #9 | Direkte Model-Queries in 3 DRF-Views | mittel | klein | ⭕ | AP-6 |
| SA-20 | §4.3 F-10 | Plain ViewSets umgehen Base-Guards | mittel | mittel | ⭕ | AP-6 |
| SA-21 | §3 P1-12, §4.1 #1–#5 | Layer-Verletzungen (Rest) | mittel | groß | ⚠️ | AP-6 |
| SA-22 | §4.6 F8 | lifecycle_manager unscoped UPDATE | mittel | klein | ⭕ | AP-6 |
| SA-23 | §4.1 #12, §4.6 F4 | `scope_preview` AllowAny | niedrig | trivial | ⭕ | AP-6 |
| SA-24 | §4.1 #9 | Archivierungs-Task nicht im Beat-Schedule | mittel | trivial | ⭕ | AP-6 |
| SA-25 | §4.3 F-04 | 9 Write-Handler umgehen Serializer | hoch | mittel | ⚠️ | AP-6 |
| SA-26 | §3 P1-14 | `input_tokens=0` an 5 Reststellen | mittel | klein | ⚠️ | AP-6 |
| SA-27 | §4.5 #8 | `is_mock_fallback`-Semantik divergiert | mittel | klein | ⚠️ | AP-6 |
| SA-28 | §3 P1-15, §4.1 #7 | PermissionCache nur Thread-lokal invalidiert | hoch | mittel | ⭕ | AP-6 |
| SA-29 | §4.1 #8 | presets-Prozess-Cache ohne Cross-Worker-Inval. | mittel | klein | ⭕ | AP-6 |
| SA-30 | §4.5 #3 | SN-Implementation-States veraltet | hoch | mittel | ⭕ | AP-7 |
| SA-31 | §3 P1-17, §4.6 F5 | CSV-Formel-Injektion im Export | mittel | trivial | ⭕ | AP-6 |
| SA-32 | §3 P1-17, §4.6 F7 | Refresh ohne Reuse-Detection | mittel | mittel | ⭕ | AP-6 |
| SA-33 | §4.6 F9 | LLM-base_url SSRF (kein CIDR-Block) | mittel | klein | ⭕ | AP-6 |
| SA-34 | §4.6 F11 | API-Keys bare SHA-256 ohne Pepper | niedrig | klein | ⭕ | AP-6 |
| SA-35 | §4.6 F14 | `sm_*` roher tenant_id ohne TenantManager | niedrig | klein | ⭕ | AP-6 |
| SA-36 | §4.6 F15 | `csrf_exempt` ohne Cookie-Auth-Assertion | niedrig | trivial | ⭕ | AP-6 |
| SA-37 | §4.1 #10 | Sync-Timeout-Thread ohne RLS-Session-Var | mittel | klein | ⭕ | AP-6 |
| SA-38 | §4.3 F-09 | metrics_views `set_tenant` ohne `finally` | mittel | trivial | ⭕ | AP-6 |
| SA-39 | §4.1 #11/#13/#14 | Audit-EXISTS-Query, switch_preset lost-update, TOCTOU | niedrig | klein | ⭕ | AP-6 |
| SA-40 | §3 P1-16, §4.7 #6 | Static-Files /admin/ + Swagger broken | hoch | klein | ⭕ | AP-4 |
| SA-41 | §4.6 F12, §4.7 #10 | Cookie-/TLS-Hardenings fehlen | hoch | trivial | ⭕ | AP-4 |
| SA-42 | §4.7 #8 | ghcr+minimal: `--concurrency` nicht gepinnt | mittel | trivial | ⭕ | AP-4 |
| SA-43 | §4.7 #5 | Kein DB-Pooling / Timeouts | mittel | klein | ⭕ | AP-4 |
| SA-44 | §4.7 #4 | Kein Image-Scan / SBOM / Signierung | hoch | mittel | ⭕ | AP-4 |
| SA-45 | §4.7 #16 | Kein ruff/mypy in CI | mittel | klein | ⭕ | AP-4 |
| SA-46 | §4.7 #11 | Keine Request-/Correlation-ID | mittel | klein | ⭕ | AP-4 |
| SA-47 | §4.7 #12 | Keine Metriken/Tracing/Alerting | mittel | groß | ⭕ | AP-4 |
| SA-48 | §4.7 #9 | `frontend: user: root` | mittel | trivial | ⭕ | AP-4 |
| SA-49 | §4.7 #7 | Gunicorn-Flags + `stop_grace_period` | mittel | klein | ⭕ | AP-4 |
| SA-50 | §4.7 #13 | Backups ohne Monitoring/Restore-Test | niedrig | klein | ⭕ | AP-4 |
| SA-51 | §4.7 #14 | Redis-Passwort in Cmdline | niedrig | trivial | ⭕ | AP-4 |
| SA-52 | §4.7 #15 | PG-Reservation, MEDIA_ROOT | niedrig | trivial | ⭕ | AP-4 |
| SA-53 | §2, §4.3 F-13, §4.4 #3 | AGENTS.md-Faktendrift (7 falsche Claims) | mittel | mittel | ⭕ | AP-7 |
| SA-54 | §4.8 | README-Testzahlen veraltet | niedrig | trivial | ⭕ | AP-7 |
| SA-55 | §4.5 #4 | REQUIREMENTS.md-Kopf + ID-Schema-Dualität | mittel | klein | ⭕ | AP-7 |
| SA-56 | §4.5 #7 | `open_requirements_count`-Definition falsch | mittel | klein | ⭕ | AP-7 |
| SA-57 | §3 P2, §4.5 #10 | Custom-Presets nur in-memory | niedrig | mittel | ⭕ | AP-7 |
| SA-58 | §4.5 #12 | `approval_workflows=False` ohne Konsument | niedrig | trivial | ⭕ | AP-7 |
| SA-59 | §4.5 #13 | test_coverage_report konflatiert Needs | niedrig | trivial | ⭕ | AP-7 |
| SA-60 | §4.5 #11/#14/#15, §4.1 #15 | 4 SE-Doku-Detailkorrekturen | niedrig | klein | ⭕ | AP-7 |
| SA-61 | §4.8 | MCP-SSE-Transport ungetestet (6 Skips) | mittel | mittel | ⭕ | AP-7 |
| SA-62 | §4.8 | Test-Marker + Factory-Strategie | niedrig | klein | ⭕ | AP-7 |
| — | §3 P0-2 | RLS-Lücken ~20 Tabellen | hoch | — | ✅ | #771 |
| — | §3 P0-3a/c | EventBus Subscriber-Fehler + Webhook-Registrierung | hoch | — | ✅ | #771 |
| — | §3 P0-4 | MCP-Throttling | hoch | — | ✅ | #771 |
| — | §3 P0-5 | `str(exc)` protocol_handler + metrics_views | hoch | — | ✅ | #771 |
| — | §3 P0-6 | Celery-Time-Limits | hoch | — | ✅ | #771 |
| — | §3 P0-7 | Redis-Eviction | hoch | — | ✅ | #771 |
| — | §3 P0-8 | Test-Settings-Kontamination | hoch | — | ✅ | #771 |
| — | §3 P0-9 | se_metrics dead views | hoch | — | ✅ | #771 |
| — | §3 P1-10 | Traceability-Matrix-Regeneration | hoch | — | ✅ | #772 |
| — | §3 P1-11, §4.5 #1 | L0–L4-Mapping + decompose-Level + CONS-P11 | hoch | — | ✅ | #772 |
| — | §3 P1-13 | REST-Error-Envelope + Glossary-`__dict__` | mittel | — | ✅ | #772 |
| — | §3 P1-14b | LLM-Call aus `@atomic_transaction` | mittel | — | ✅ | #772 |
| — | §3 P1-15/§4.5 #5 | `supersedes`-Phantom-Typ | mittel | — | ✅ | #772 |
| — | §3 P2/§4.5 #6 | Soft-Delete-Konvention + lifecycle_status | mittel | — | ✅ | #772 |
| — | §3 P1-12 (Teil) | auth_tenancy Layer-0-Exceptions gehoben | hoch | — | ✅ | #772 |
| — | §3 P2 | data-testid-Lücken (DiagramGraphEditor u. a.) | niedrig | — | ❌ | s. §2 |
| — | §4.4 #2 | GraphToolbar ohne testid | mittel | — | ❌ | s. §2 |

### A.2 Aus `SYSTEMAUDIT_UI_2026-08-27.md`

Alle Findings **verifiziert offen** (Stichprobenprüfung an 11 von 11 P0-Findings gegen den Code, alle bestätigt).

| ID | Quelle | Finding (Kurz) | Schwere | Aufwand | Status | AP |
|---|---|---|---|---|---|---|
| UI-01 | §4 P0-1 | Interview-LLM 30 s statt 180 s Timeout | **Blocker** | trivial | ⭕ | AP-3 |
| UI-02 | §4 P0-2 | Graph-Editor Edit-Verlust bei Navigation | hoch | mittel | ⭕ | AP-3 |
| UI-03 | §4 P0-3 | CanvasEditor Delete/Backspace ohne Target-Check | hoch | trivial | ⭕ | AP-3 |
| UI-04 | §4 P0-4 | TestRun-Result-Erfassung fehlt im SPA | hoch | groß | ⭕ | AP-3 |
| UI-05 | §4 P0-5 | Requirement-Delete unerreichbar (Dead Code) | hoch | klein | ⭕ | AP-3 |
| UI-06 | §4 P0-6 | NeedForm ohne Dirty-Guard + CustomFields-Contamination | hoch | klein | ⭕ | AP-3 |
| UI-07 | §4 P0-7 | TestCaseForm Unsaved-Verlust | hoch | klein | ⭕ | AP-3 |
| UI-08 | §4 P0-8 | Architecture-Update ohne `expected_version` | hoch | klein | ⭕ | AP-3 |
| UI-09 | §4 P0-9 | 6 destruktive Aktionen ohne Bestätigung | hoch | klein | ⭕ | AP-3 |
| UI-10 | §4 P0-10 | 6 tastatur-unbedienbare Listen/Autocompletes | hoch | mittel | ⭕ | AP-3 |
| UI-11 | §4 P0-11 | `adrs/risks/issues.summary` fehlen in beiden Locales | hoch | trivial | ⭕ | AP-3 |
| UI-20 | §4 P1 | 11× `window.confirm` → ConfirmDialog | mittel | mittel | ⭕ | AP-5 |
| UI-21 | §4 P1 | GH-513-Override ohne Rollen-Gating | mittel | klein | ⭕ | AP-5 |
| UI-22 | §4 P1 | Preset-Downgrade ohne Warnung | mittel | trivial | ⭕ | AP-5 |
| UI-23 | §4 P1, §5.7 | Mermaid persistiert invalide Quelle | mittel | trivial | ⭕ | AP-5 |
| UI-24 | §4 P1 | Escape/Backdrop-Guards für Draft-Dialoge | mittel | klein | ⭕ | AP-5 |
| UI-25 | §4 P1 | Label-Assoziations-Kluster (9+) | mittel | mittel | ⭕ | AP-5 |
| UI-26 | §4 P1, §5.8 | Interview a11y + Grounding-UX | mittel | mittel | ⭕ | AP-5 |
| UI-27 | §4 P1, §6 | A11y-Detailbatch (7 Muster) | mittel | mittel | ⭕ | AP-5 |
| UI-28 | §4 P1, §5.5 | MainGoal-Generate ohne Busy-State + Mock-Indikator | mittel | klein | ⭕ | AP-5 |
| UI-29 | §4 P1, §5.5 | Goals `change_reason` generiert statt erfragt | mittel | klein | ⭕ | AP-5 |
| UI-30 | §4 P1, §5.7 | CSV-Import Partial-Success/Preview/Mapping | mittel | mittel | ⭕ | AP-5 |
| UI-31 | §4 P1 | `useRequirementData` verschluckt Listenfehler | mittel | trivial | ⭕ | AP-5 |
| UI-32 | §4 P1, §5.5 | ADR-Supersede-Flow (REQ-150) fehlt im UI | mittel | mittel | ⭕ | AP-5 |
| UI-33 | §4 P1 | Manueller Derive: partieller Fehler ohne Rollback | mittel | klein | ⭕ | AP-5 |
| UI-34 | §4 P1, §5.6 | Reviews: Rohtext-State, Disabled-Grund, keine Pagination | mittel | klein | ⭕ | AP-5 |
| UI-35 | §4 P1, §5.4 | MetricsDashboard: Empty-State, Thresholds, a11y, Testids | mittel | klein | ⭕ | AP-5 |
| UI-36 | §4 P1 | ImpactView 0-Treffer-State + placeholder-label | niedrig | trivial | ⭕ | AP-5 |
| UI-37 | §4 P1, §5.5 | ADR-Placeholder-Müll | niedrig | trivial | ⭕ | AP-5 |
| UI-38 | §4 P1, §5.8 | WorkflowEditor Toast-Timer ohne Cleanup | niedrig | trivial | ⭕ | AP-5 |
| UI-39 | §5.5 | RiskForm: detection-Feld, Matrix, risk_score fehlen | mittel | mittel | ⭕ | AP-5 |
| UI-40 | §5.3 | PermissionMatrix-Unsaved + DecomposePanel ohne Tests | mittel | mittel | ⭕ | AP-5 |
| UI-41 | §4 P2, §6 | Scroll-Lock-Konflikt, SplitView-CSS, Tab-Arrow-Keys | niedrig | klein | ⭕ | AP-5 |
| UI-50 | §4 P2, §6 | 5 Button-Stil-Systeme → 4 kanonische Klassen | mittel | mittel | ⭕ | AP-2 |
| UI-51 | §4 P2, §6 | 4 duplizierte Toast-Systeme → 1 Primitiv | mittel | mittel | ⭕ | AP-2 |
| UI-52 | §4 P2, §6 | 4 Loading-Patterns; Spinner-Primitiv ungenutzt | niedrig | klein | ⭕ | AP-2 |
| UI-53 | §4 P2 | ~55 Testid-Lücken (Logout, TracePanel ×11, 4 Saves …) | niedrig | mittel | ⭕ | AP-2 |
| UI-54 | §4 P2 | i18n-Backlog ~60 Hardcode-Zeilen + rohe Enums | mittel | mittel | ⭕ | AP-2 |
| UI-55 | §4 P2 | `statusBadge`: Varianten-Kollision, `blocked`/`skipped` fehlen | niedrig | trivial | ⭕ | AP-2 |
| UI-56 | §4 P2, §5.4 | TestRunsList: Select-All/Suche, `ci_job_id`, Close-Terminalität | niedrig | klein | ⭕ | AP-5 |
| UI-57 | §4 P2, §5.4 | Audit-„Adopt" ohne Bestätigung/Undo | mittel | trivial | ⭕ | AP-5 |
| UI-58 | §4 P2 | RequirementTreeNode ohne Retry; `traceability.cycleNode` fehlt | niedrig | trivial | ⭕ | AP-2 |
| UI-59 | §4 P2, §5.5 | GlossaryView ohne Versions-/Diff-UI (API existiert) | niedrig | mittel | ⭕ | AP-5 |

---

## Anhang B: Was dieser Plan bewusst NICHT enthält

- **INFO-Findings** beider Dokumente (dokumentierte Trade-offs, bewusste Design-Entscheidungen, Dateigrößen-Hinweise) — z. B. SA §4.2 #14, §4.4 #8–#13, §4.5 #16/#17, §4.6 F18–F21. Sie sind keine Arbeit, sondern Kontext.
- **Der Stärken-Katalog** beider Dokumente (SA §4.x „Stärken", UI §7) — er ist wichtig für Reviewer, aber nicht planbar.
- **Die 20-Claims-Konsistenzmatrix** (SA §4.5) — die 3 ❌ und 5 🟡 daraus sind als SA-30/SA-53/SA-55/SA-27 eingeflossen, die 12 ✅ nicht.
- **Der ausführliche Maskengruppen-Katalog** (UI §5.1–§5.8) — dort genannte Einzelbefunde sind über die P0/P1/P2-Konsolidierung (UI §4) abgedeckt; wo §5 zusätzliche Befunde nennt, sind sie als UI-39/UI-40/UI-41/UI-56…UI-59 aufgenommen.

---

*Erstellt am 2026-08-28 gegen `fix/systemaudit-p2-hygiene @ 78ba75ee`. Alle Status-Angaben verifiziert gegen den Arbeitsbaum, `git log`, `gh issue list` und `gh pr view`. Pfadangaben relativ zum Repo-Root, sofern nicht anders vermerkt.*
