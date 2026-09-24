---
type: REVIEW
scope: system-audit-2026-09
status: final
date: 2026-09-24
author_agent: code-reviewer
revision: e3df119e52c0cbcc18df02f708567207c0374826
branch: feat/1031-bluepencil-host-bridge
---

# Systemaudit 2026-09 — Testing, CI, Build, Performance und Betrieb

## 1. Management-Summary

Dieser Bericht prüft den aktuellen Repository-Stand auf Testabdeckung, CI-/Release-Reihenfolge, TypeScript-Builds, Migrationen, Docker/Compose, Playwright/E2E, Test-Isolierung, N+1-/Concurrency-Risiken sowie die Verknüpfung mit dem Dependency-/Release-Bericht `docs/se/reports/deep_audit/system-audit-2026-09/10-dependencies-supply-chain-and-release.md`.

**Prüfmodus:** statische, read-only Analyse von Quelltext, Testdefinitionen, CI-Workflows, Dockerfiles, Compose-Dateien und Betriebsdokumentation. Es wurden keine Tests, Builds, Container, Browser, Installer oder Scanner gestartet. Die Testzahlen sind daher statische Zählungen und keine Collection-/Pass-/Coverage-Ergebnisse.

**Gesamtbefund:** **0 P0, 6 P1, 9 P2, 1 P3.** Die größten belegten Risiken sind:

1. Der GitHub-Backend-Testlauf lässt vier Testbereiche mit insgesamt 463 statisch gezählten Testdefinitionen außerhalb seiner Matrix (`.github/workflows/ci.yml:41-55`).
2. Die realen HTTP-/Redis-Integrationstests für MCP-Rollenpropagation und SSE werden in CI ausdrücklich übersprungen (`backend/mcp_server/tests/test_mcp_api_key_roles.py:71-90`, `backend/mcp_server/tests/test_e2e_sse_transport.py:317-361`).
3. Playwright startet für E2E WSGI-`runserver` und den Vite-Dev-Server, obwohl SSE ASGI und die Auslieferung nginx erwartet; der SSE-Test prüft keinen authentifizierten Stream (`.github/workflows/playwright.yml:143-185`, `e2e/tests/hermes-bugfix-campaign.spec.ts:667-687`).
4. Mehrere E2E-Fehler werden durch `test.skip(true, ...)` in grüne Läufe umgewandelt, darunter ein fehlgeschlagener TraceLink-Contract.
5. Das Tag-Release startet Image-Build/Scans unabhängig von einem im Repository sichtbaren Test-Gate; der sekundäre Woodpecker-Testschritt führt nur `manage.py check` aus.
6. Backup-/Restore-Skripte passen nicht mehr zum produktiven Compose-Sidecar und können dessen `.sql.gz`-Backups nicht wiederherstellen.

Die Anwendung besitzt dagegen gute Paved Roads: PostgreSQL/RLS bleibt in den Tests erhalten, die SeMetrics-Worker setzen RLS-Kontext explizit, der MCP-Nachrichtenpool ist begrenzt und räumt Verbindungen auf, Playwright hat globale Preconditions/Timeouts/Traces, und es existieren mehrere gezielte Contract-/Architektur-Ratchets. Diese Ratchets ersetzen jedoch keine quantitative Line-/Branch-Coverage und keine produktionsnahe E2E-Laufzeit.

## 2. Scope, Revision und Methodik

- **Repository:** `C:\Repositories\ai-native-reqflow-POC`
- **Branch:** `feat/1031-bluepencil-host-bridge`
- **Revision:** `e3df119e52c0cbcc18df02f708567207c0374826`
- **Änderungsgrenze:** ausschließlich dieser Bericht; keine Anwendungs-, CI-, Docker- oder Testdatei geändert.
- **Nicht ausgeführt:** pytest, Vitest, Playwright, TypeScript-Build, Docker-Build/Start, `pip-audit`, `npm audit`, Trivy oder externe CVE-Abfragen.
- **Historische Logs:** nicht als aktuelle Evidenz verwendet; lokale ignorierte Logs können veraltete oder vertrauliche Daten enthalten.

### 2.1 Statisches Testinventar

| Fläche | Statischer Befund | Aussagegrenze |
|---|---:|---|
| Backend | 655 Kandidaten-Testdateien; 7.647 `def test_`/`async def test_`-Treffer | Regex-/Dateimuster, nicht pytest-Collection |
| Frontend | 236 Testdateien; 2.039 `it(...)`/`test(...)`-Treffer | Regex, keine Vitest-Ausführung |
| Playwright | 54 Spec-Dateien; 304 `test(...)`-Treffer | keine Playwright-Collection |
| E2E-Skip-Stellen | 14 ausführbare `test.skip(...)`-Stellen (20 Texttreffer inklusive Kommentaren) | statische grep-Zählung |
| CI-Lücke | 463 Testdefinitionen in `context_graph`, `link_types`, `memory` und `backend/tests` | Matrixpfadvergleich gegen versionierte Dateien |

## 3. Befundübersicht

| ID | Severity | Prio | Status | Kurzfassung | Confidence |
|---|---:|---:|---|---|---:|
| CI-001 | HIGH | P1 | bestätigt | Backend-CI-Matrix lässt 463 Testdefinitionen aus | Hoch (0.99) |
| CI-002 | HIGH | P1 | bestätigt | Live-MCP-/Redis-Integrationstests werden in CI übersprungen | Hoch (0.99) |
| E2E-001 | HIGH | P1 | bestätigt | E2E testet nicht die produzierte ASGI-/nginx-Laufzeit | Hoch (0.98) |
| E2E-002 | HIGH | P1 | bestätigt | Skip-on-failure kann Kern-Contract-Regressionen als Grün melden | Hoch (0.98) |
| REL-001 | HIGH | P1 | bestätigt | Release-Pipeline hat kein sichtbares Test-vor-Image-Gate | Hoch (0.95) |
| OPS-002 | HIGH | P1 | bestätigt | Backup-/Restore-Werkzeuge passen nicht zum Sidecar-Backupformat | Hoch (0.98) |
| TEST-001 | MEDIUM | P2 | bestätigt | Fixtures hinterlassen Workspaces/API-Keys und erzeugen persistente Zustandsabhängigkeit | Hoch (0.98) |
| COV-001 | MEDIUM | P2 | bestätigt | Kein quantitativer Backend-/Frontend-Coverage-Gate | Hoch (0.99) |
| TYPE-001 | MEDIUM | P2 | bestätigt | Test-TypeScript wird nicht separat typegecheckt; E2E hat kein tsconfig | Hoch (0.96) |
| PERF-001 | MEDIUM | P2 | Hypothese | SeMetrics-Workflow-Gap-Ermittlung ist N+1 | Hoch (0.90) |
| PERF-002 | MEDIUM | P2 | bestätigt | In-Process-Cache-Lock schützt keine vier Produktionsworker | Hoch (0.99) |
| PERF-003 | MEDIUM | P2 | Hypothese | LLM-Timeout erzeugt potenziell nicht gebundene Restthreads | Mittel (0.72) |
| OPS-001 | MEDIUM | P2 | bestätigt | Kein vollständiger `makemigrations --check`-Gate über alle Apps | Hoch (0.94) |
| OPS-003 | MEDIUM | P2 | bestätigt | Compose-Befehle und Dev-Overlay-Anforderung widersprechen sich | Hoch (0.96) |
| E2E-003 | MEDIUM | P2 | bestätigt | `test:e2e:api` verweist auf ein nicht vorhandenes Verzeichnis | Hoch (0.99) |
| DOC-001 | LOW | P3 | bestätigt | README-/CI-Testzahlen sind nicht als aktuelle Collection-Baseline gepflegt | Hoch (0.98) |

**P0:** 0. **P1:** 6. **P2:** 9. **P3:** 1.

## 4. Detailbefunde

### CI-001 — Backend-CI-Matrix lässt 463 Testdefinitionen aus

**Kategorie / Status:** CI-Abdeckung / bestätigt  
**Severity:** HIGH  
**Prio:** P1  
**Tatsache/Hypothese:** Die vier GitHub-Matrix-Sätze enumerieren feste Anwendungspfade; mehrere versionierte Testbäume werden nicht genannt. Dadurch ist die tatsächliche Regression-Abdeckung des Pull-Request-Gates kleiner als das Repository-Inventar.

**Evidenz:** `.github/workflows/ci.yml:41-55`; `backend/context_graph/tests/` (20 Testdefinitionen), `backend/link_types/tests/` (135), `backend/memory/tests/` (282) und `backend/tests/` (26, darunter `backend/tests/test_wiring.py`, `backend/tests/test_required_secrets.py`, `backend/tests/test_csrf_trusted_origins.py`). Die Summe beträgt 463 statisch gezählte Definitionen. Der lokale `Makefile`-Test verwendet dagegen `pytest -q` (`Makefile:65-74`), was diese Lücke verdecken kann.

**Auswirkung:** Ein Fehler in RLS, Memory, Link-Type-Katalog, Root-Wiring, Secret-Validierung oder CSRF-Konfiguration kann den Pull Request passieren, obwohl die Tests im Repository existieren.

**Root Cause:** Manuelle Pfad-Matrix ohne Discovery-/Collection-Gate; die Matrix ist nicht aus der Teststruktur abgeleitet und wird bei neuen Apps nicht automatisch erweitert.

**Gegenmaßnahme:** Eine explizite Matrix für alle App-Bäume plus Root-Suite ergänzen und einen Guard einführen, der die versionierten Testdateien gegen die ausgeführten Pfade vergleicht. Der Guard muss absichtlich ausgeschlossene, klar benannte Integrationstests als Allowlist dokumentieren.

**Alternativen:** Ein einziger vollständiger `pytest`-Lauf ist einfacher, kann aber bei der aktuellen Installationszeit und dem 20-Minuten-Joblimit unzuverlässig werden. Ein zentraler Test-Discovery-/`pytest --collect-only`-Vergleich ist robuster als eine weitere manuelle Liste.

**Aufwand:** M (1–3 Entwicklungstage inklusive CI-Laufzeitmessung).

**Confidence:** Hoch (0.99).

**Mess-/Verifikationsplan:** In einer sauberen CI-Umgebung `pytest --collect-only -q` für die Gesamtsuite erfassen, die Ergebnisse gegen die Matrixpfade vergleichen und bei jeder nicht erfassten Testdatei fehlschlagen. Danach einen absichtlich markierten Test in `memory` und `backend/tests` ausführen und dessen CI-Artefakt/Log prüfen.

### CI-002 — Live-MCP-/Redis-Integrationstests werden in CI übersprungen

**Kategorie / Status:** Testklassifikation / bestätigt  
**Severity:** HIGH  
**Prio:** P1  
**Tatsache/Hypothese:** Die Tests, die den realen HTTP-Server für API-Key-Rollen und den echten Redis-SSE-Roundtrip benötigen, überspringen sich unter `CI`/`GITHUB_ACTIONS`; es gibt keinen separaten CI-Schritt, der sie mit diesen Infrastrukturen ausführt.

**Evidenz:** `backend/mcp_server/tests/test_mcp_api_key_roles.py:71-90` (Live-Stack-Test, in CI explizit Skip); `backend/mcp_server/tests/test_e2e_sse_transport.py:317-361` (Live-Redis-Test, in CI explizit Skip). Die GitHub-Backend-Job verwendet nur `pytest ${{ matrix.test-set.paths }}` (`.github/workflows/ci.yml:118-144`). Redis ist als Service vorhanden, aber kein ASGI-Server/pytest-Integrationsschritt ist damit verbunden.

**Auswirkung:** In-Process-ProtocolHandler-/ToolRegistry-Tests können grün sein, während API-Key-Rollen über echte HTTP-Header, Session-Bindung, Redis-Pubsub oder Connection-Lifecycle im Produktionsserver nicht funktionieren.

**Root Cause:** Integrationstests wurden als lokales Manual-Scenario klassifiziert; `integration` ist eine Markierung, aber kein verpflichtender CI-Ausführungspfad.

**Gegenmaßnahme:** Einen dedizierten Integrationsjob mit ASGI-Server, PostgreSQL und Redis bauen und nur die markierten Live-Tests mit `-m integration` ausführen. Im normalen Unit-Job dürfen diese Tests weiterhin selektiv übersprungen werden, der Integrationsjob selbst darf sie nicht als erfüllt betrachten, wenn seine Umgebung nicht bereit ist.

**Alternativen:** Docker-Compose-Testservice kann die Infrastruktur liefern, muss aber gegen einen echten Uvicorn/Gunicorn-Prozess und nicht nur gegen `manage.py check` testen. Ein bloßes Entfernen des Skip-Markers ohne Start-/Readiness-Gate ist unzureichend.

**Aufwand:** M (2–5 Tage inklusive stabiler CI-Readiness und Artefakt-Diagnose).

**Confidence:** Hoch (0.99).

**Mess-/Verifikationsplan:** Integrationsjob mit absichtlich falschem Redis-Host muss mit klarer Setup-Diagnose fehlschlagen; mit echtem Redis müssen API-Key-Rollen- und SSE-Roundtrip-Test explizit als PASS mit Testnamen und Umgebungs-Fingerprint archiviert werden.

### E2E-001 — E2E testet nicht die produzierte ASGI-/nginx-Laufzeit

**Kategorie / Status:** E2E-Laufzeitparität / bestätigt  
**Severity:** HIGH  
**Prio:** P1  
**Tatsache/Hypothese:** Der Playwright-Workflow startet den Django-Entwicklungsserver über `runserver` und den Vite-Dev-Server; der Produktions-Frontend-Container wird nur gebaut, nicht als E2E-Ziel gestartet. Der SSE-Smoke-Test behauptet asynchronen Serverbetrieb, prüft aber nur Routing-/Fehlerstatus.

**Evidenz:** `.github/workflows/playwright.yml:143-185` (`python manage.py runserver`, `npm run dev`); `.github/workflows/playwright.yml:202-205` baut nur das Frontend-Image; `deploy/docker-compose.override.yml:15-30` erklärt, dass WSGI/`runserver` den MCP-SSE-Stream nicht bedienen kann. `e2e/tests/hermes-bugfix-campaign.spec.ts:667-687` ruft `/mcp/sse/` unauthentifiziert auf und akzeptiert jeden Status `<500` außer `404`, ohne `Content-Type`, authentifizierten Handshake, `event: endpoint`, Publish/Consume oder Messages-Roundtrip zu prüfen.

**Auswirkung:** Ein Lauf kann die deklarierte SSE-Fähigkeit als bestanden melden, obwohl ein authentifizierter Stream unter dem CI-Server nicht startet oder keine Nachricht liefert. Vite-spezifische Proxy-/Modul-Verhalten kann außerdem von nginx- und Produktionsbuild-Verhalten abweichen.

**Root Cause:** Der E2E-Workflow priorisiert schnelles Setup vor Laufzeitparität; Transporttests prüfen Verfügbarkeit statt des Vertrags.

**Gegenmaßnahme:** CI gegen `uvicorn reqogniloom.asgi:application` oder das veröffentlichte Backend-Image und gegen das nginx-Frontend-Image starten. Den SSE-Test auf authentifizierten Handshake, `text/event-stream`, Endpoint-Event, Publish/Consume und Session-Timeout erweitern.

**Alternativen:** Ein separater Nightly-Produktionsimage-Smoke ist sinnvoll, ersetzt aber nicht einen schnellen PR-Test des tatsächlichen ASGI-Prozesses.

**Aufwand:** M (2–5 Tage inklusive Streaming-Timeouts und Artefakt-Diagnose).

**Confidence:** Hoch (0.98).

**Mess-/Verifikationsplan:** Einen authentifizierten SSE-Stream im CI gegen `runserver` und gegen Uvicorn ausführen; der Laufserver-Fall muss reproduzierbar einen Timeout auslösen oder einen klaren Serverfehler liefern, der Uvicorn-Fall muss Endpoint- und Message-Frames liefern. Frontend-Smoke gegen `dist`/nginx und gegen Vite getrennt protokollieren.

### E2E-002 — Skip-on-failure kann Kern-Contract-Regressionen als Grün melden

**Kategorie / Status:** E2E-Testqualität / bestätigt  
**Severity:** HIGH  
**Prio:** P1  
**Tatsache/Hypothese:** Mehrere Tests verwandeln fehlende Funktionalität oder fehlgeschlagene Vorbedingungen in `test.skip(true, ...)`, statt den Vertrag als fehlgeschlagen zu markieren. Das betrifft auch einen REST-/MCP-TraceLink-Contract.

**Evidenz:** `e2e/tests/api-completeness.spec.ts:269-287` überspringt die TraceLink-Erstellung nach jedem HTTP-Fehler; `e2e/tests/stakeholder-needs.spec.ts:308` überspringt bei fehlendem Sprachumschalter; `e2e/tests/se-workflow.spec.ts:102-221` überspringt fehlende UI-/Workspace-Bausteine; `e2e/tests/waterkettle-fullblown.spec.ts:481-818` überspringt Folgeschritte bei fehlenden IDs; `e2e/helpers/preconditions.ts:233-272` warnt nur vor dem optionalen Toothbrush-Fixture. Insgesamt 14 ausführbare Skip-Stellen.

**Auswirkung:** Ein fehlgeschlagener API-Contract, ein nicht gerenderter Workflow-Editor oder eine fehlende Folge-ID reduziert die Zahl der ausgeführten Assertions, ohne den Job rot zu machen. Ein grüner E2E-Lauf beweist dann nur die noch vorhandenen Pfade.

**Root Cause:** Optionale Fixtures und echte Produktfehler verwenden denselben Skip-Mechanismus; es fehlt eine CI-Policy für mandatory/optional/negative Pfade.

**Gegenmaßnahme:** Skip-Kategorien explizit modellieren: optionale Umgebungsfixtures dürfen mit strukturiertem Report skippen; ein fehlgeschlagener Contract darf nicht skippen. Für jede Skip-Stelle einen `required`-Marker, einen erwarteten Exitcode und einen Report im CI-Artefakt verlangen.

**Alternativen:** Optionales Feature in einen separaten nicht-blockierenden Job verschieben; im Core-Job den fehlenden Vertrag als FAIL behandeln.

**Aufwand:** S–M (1–3 Tage plus Anpassung der Specs).

**Confidence:** Hoch (0.98).

**Mess-/Verifikationsplan:** In einer Testumgebung den TraceLink-Endpunkt künstlich auf 400 stellen; der E2E-Lauf muss fehlschlagen und den konkreten Contract nennen. Ein fehlendes optionales Sidecar darf separat als Skip mit Begründung erscheinen, darf aber die Zahl der Core-Assertions nicht verändern.

### REL-001 — Release-Pipeline hat kein sichtbares Test-vor-Image-Gate

**Kategorie / Status:** Release-/Lieferkettenkontrolle / bestätigt  
**Severity:** HIGH  
**Prio:** P1  
**Tatsache/Hypothese:** Der GitHub-Tag-Workflow baut, scannt und pusht Images, führt aber selbst keine Backend-/Frontend-Tests aus und referenziert keinen separaten Teststatus. Im alternativen Woodpecker-Workflow heißt der Backend-Testschritt „test“, führt aber nur Django-Systemchecks aus; `verify-images` gibt nur Erfolgsmeldungen aus.

**Evidenz:** `.github/workflows/docker-publish.yml:15-18,26-40,165-191` (Tag-Trigger, Build/Scan/Push ohne Testjob oder `needs`); `.woodpecker.yml:1-12,39-62,163-171` (nur `python manage.py check`, danach Echo-only Verify). Der Dependency-Bericht `docs/se/reports/deep_audit/system-audit-2026-09/10-dependencies-supply-chain-and-release.md:123-134` behandelt zusätzlich den nicht digestgebundenen Scan/Push.

**Auswirkung:** Im Repository ist keine technische Reihenfolge `Commit -> grüne Tests -> Release-Image` erzwungen. Bei fehlender externer Branch-Protection-/Tag-Policy kann ein fehlerhafter oder nur unvollständig geprüfter Commit als Image veröffentlicht werden. Der Woodpecker-Verify-Schritt kann Erfolg melden, ohne das gepushte Image zu pullen oder zu starten.

**Root Cause:** Build-/Publish-Workflows sind als unabhängige Pipelines angelegt; Test-, Scan- und Deploy-Gates haben keinen gemeinsamen, referenzierbaren Workflow-Vertrag.

**Gegenmaßnahme:** Wiederverwendbaren Test-/Build-Workflow für Tag-Commits verpflichtend machen, den exakten geprüften Image-Digest an Scan/Push/Deployment binden und nach dem Push das gepushte Image in einer frischen Compose-Instanz pullen, migrieren, einen Healthcheck ausführen und rauchtesten. Woodpecker entweder als veraltete Release-Pipeline deklarieren oder mit denselben Gates versehen.

**Alternativen:**Ein manueller Release-Check ist schwächer und nicht auditierbar; GitHub-Status-/Tag-Protection kann zusätzlich außerhalb des Repositories existieren, ist hier aber nicht als Gegenmaßnahme belegt.

**Aufwand:** L (ca. 1 Woche Pipeline-/Rollout-Arbeit).

**Confidence:** Hoch (0.95).

**Mess-/Verifikationsplan:** Einen Commit mit absichtlich fehlschlagendem Test und einen nur aus dem bestehenden Workflow gebauten Commit vergleichen; Image-Push/Release darf ohne grünen, commitgebundenen Teststatus nicht erfolgen. Gepushtes Image per Digest laden und einen Health-/API-Smoke-Test ausführen.

### OPS-002 — Backup-/Restore-Werkzeuge passen nicht zum Sidecar-Backupformat

**Kategorie / Status:** Betrieb/Recovery / bestätigt  
**Severity:** HIGH  
**Prio:** P1  
**Tatsache/Hypothese:** Das Voll-Stack-Compose erzeugt automatisch gzip-komprimierte SQL-Dumps im benannten Volume, während die mitgelieferten Backup-/Restore-Skripte auf ein nicht vorhandenes Compose-Overlay und ein anderes Dateiformular zielen. Das Restore-Skript unterstützt `.dump`/`.sql`, nicht `.sql.gz`, und sucht im Repository-`backups/` statt im Sidecar-Volume.

**Evidenz:** `deploy/docker-compose.yml:127-170` erzeugt `reqogniloom_<ts>.sql.gz` in `postgres_backup_data`; `scripts/backup.sh:74-86` bricht ab, weil `docker-compose.backup.yml` fehlt, und `scripts/backup.sh:102-105` verweist auf genau diese nicht vorhandene Datei; `scripts/restore.sh:49,116,181-186` akzeptiert nur `.dump`/`.sql` und sucht unter `PROJECT_ROOT/backups`. `README.md:949-972` dokumentiert daneben manuelle `pg_dump`/`gunzip`-Kommandos.

**Auswirkung:** Ein Operator kann die dokumentierten Recovery-Werkzeuge nicht auf die tatsächlich erzeugten automatischen Backups anwenden; ein Incident-Restore hängt an ad-hoc Shell-Kommandos und ist nicht als reproduzierbarer, getesteter Runbook-Schritt verfügbar.

**Root Cause:** Nach dem Compose-Reorg blieb die Legacy-Script-Schnittstelle unverändert; Storage-Pfad, Dateiendung und Restore-Mechanismus wurden nicht als gemeinsamer Vertrag aktualisiert.

**Gegenmaßnahme:** Entweder die Skripte auf den Sidecar-Pfad/`.sql.gz` umstellen oder sie entfernen und ausschließlich ein versioniertes, getestetes Restore-Runbook veröffentlichen. Restore muss Integritätsprüfung, Quell-/Ziel-DB, aktive Verbindungen, Abbruch bei Fehlern und einen Post-Restore-Healthcheck enthalten.

**Alternativen:** Ein externes Backup-Tool mit eigenem, getestetem Repository ist robuster; ein reines README-Kommando ohne Smoke-Test ist für Recovery nicht ausreichend.

**Aufwand:** M (2–5 Tage inklusive Restore-Smoke in einer isolierten PostgreSQL-Instanz).

**Confidence:** Hoch (0.98).

**Mess-/Verifikationsplan:** Sidecar-Backup erzeugen, Datei in ein frisches Test-Volume kopieren, Restore-Skript ausführen, `pg_isready`, Tabellen-/Migrationsstand und ausgewählte Tenant-Zeilen vergleichen. Ein absichtlich beschädigtes gzip muss vor dem Überschreiben der Zieldaten abbrechen.

### TEST-001 — Fixtures hinterlassen Workspaces/API-Keys und erzeugen persistente Zustandsabhängigkeit

**Kategorie / Status:** Testisolation / bestätigt  
**Severity:** MEDIUM  
**Prio:** P2  
**Tatsache/Hypothese:** E2E-Helper und Live-Tests legen Workspaces und API-Keys an, besitzen aber keinen vollständigen `afterAll`-/Finalizer-Lifecycle. Die Tests dokumentieren selbst, dass Visual-Regression-Workspaces über lokale Läufe hinweg auf Dutzende/Hunderte anwachsen.

**Evidenz:** `e2e/helpers/auth.ts:80-99` (`createIsolatedWorkspace` ohne Delete-Helper); `e2e/tests/visual-regression.spec.ts:47-73` erstellt einen Workspace in `beforeAll`, löscht ihn aber nicht; `e2e/helpers/preconditions.ts:233-264` nennt bereits beobachtete 53+ Workspaces; `e2e/tests/api-completeness.spec.ts:180-224` erstellt ebenfalls isolierte Workspaces ohne Workspace-Cleanup. `backend/mcp_server/tests/test_mcp_api_key_roles.py:265-275` erzeugt einen modulweit gültigen API-Key ohne Tear-Down; Cleanup wird nur im Cap-Fallback `backend/mcp_server/tests/test_mcp_api_key_roles.py:215-239` versucht. `e2e/helpers/auth.ts:241-264` folgt keinem `next` und verarbeitet bei paginierten Antworten nur die erste Seite und ignoriert DELETE-Fehler.

**Auswirkung:** Wiederholte lokale Läufe verändern Listen-/Screenshotgeometrie, belasten die Datenbank, erreichen das 10-Key-Limit und machen Reihenfolge sowie Ergebnis von persistentem Vorzustand abhängig. Ein abgebrochener Lauf kann zusätzlich Fixtures zurücklassen.

**Root Cause:** Create-Helper sind auf Isolation durch einen frischen Workspace ausgelegt, Cleanup ist aber nicht Teil des Helper-Vertrags; modulare Live-Fixtures teilen den produktiven Tenanten-/Benutzerzustand.

**Gegenmaßnahme:** Für jeden Test einen eindeutigen Workspace-/Benutzerkontext mit `try/finally`/`afterAll` bereitstellen, Workspaces und Keys mit explizitem Cleanup versehen, API-Key-Listen paginieren und DELETE-Antworten prüfen. CI sollte zusätzlich eine frische Datenbank pro Lauf verwenden.

**Alternativen:** Einen ephemeren Compose-Test-Tenant pro Run ist robuster; ein globales „alle E2E-Keys revoken“ ist keine ausreichende Fixture-Isolation, weil es fremde Testläufe/User beeinflussen kann.

**Aufwand:** M (2–5 Tage inklusive wiederholten lokalen Läufen).

**Confidence:** Hoch (0.98).

**Mess-/Verifikationsplan:** Drei aufeinanderfolgende Visual-Regression-Läufe auf derselben Datenbank ausführen; Workspace-Zahl, aktive Key-Zahl und Screenshot-Diff müssen stabil bleiben. Ein absichtlich abgebrochener Lauf darf nach dem nächsten globalen Teardown keine Fixtures zurücklassen.

### COV-001 — Kein quantitativer Backend-/Frontend-Coverage-Gate

**Kategorie / Status:** Coverage / bestätigt  
**Severity:** MEDIUM  
**Prio:** P2  
**Tatsache/Hypothese:** Das Backend konfiguriert Coverage-Ausführung, aber keinen Mindestwert; das Frontend besitzt weder Coverage-Skript noch Coverage-Provider. Die vorhandenen Ratchets messen einzelne strukturelle Schulden, nicht Line-/Branch-Coverage.

**Evidenz:** `backend/pyproject.toml:28-36` enthält nur `[tool.coverage.run]` ohne `fail_under`; `frontend/package.json:7-15,40-60` enthält kein `coverage`-Script und keinen `@vitest/coverage-v8`; `.github/workflows/ci.yml:118-153,255-282` führt pytest/Vitest, aber keinen Coverage-Schritt aus. Ratchets: `frontend/src/test/ui-ratchet.test.ts`, `frontend/src/test/i18n-parity.test.ts`, `frontend/src/test/design-tokens.test.ts`, `backend/rest_api/tests/test_architecture.py` und `backend/attribute_definitions/tests/test_transport_contract_matrix.py`.

**Auswirkung:** Eine neue ungetestete Datei, ein ungetesteter Fehlerzweig oder eine Regression in einem nicht gescannten Modul kann den CI-Status nicht beeinflussen. Die Ratchet-Baselines schützen nur ihre jeweiligen Metriken und können bei gleichbleibendem Schuldstand weiterhin hohe Restlücken verdecken.

**Root Cause:** Coverage-Ratchet und Testausführung wurden getrennt geplant; ein messbarer Baseline-/Schwellenwert ist nicht Teil des CI-Vertrags.

**Gegenmaßnahme:** Backend- und Frontend-Coverage reproduzierbar erzeugen, als CI-Artefakt hochladen und zunächst eine nicht-verschärfende Baseline mit explizitem `fail_under`/Ratchet einführen. Kritische Module (Auth, MCP, Workflow, Persistence, SeMetrics) mit separaten Mindestwerten versehen.

**Alternativen:** Nur Mutationstests sind für die Gesamtqualität teurer; gezielte Mutationstests können die Coverage-Gate-Einführung ergänzen, aber nicht ersetzen.

**Aufwand:** M (2–5 Tage inklusive stabiler Coverage-Daten).

**Confidence:** Hoch (0.99).

**Mess-/Verifikationsplan:** Coverage-Report und maschinenlesbare JSON-Ausgabe im CI archivieren; absichtlich eine ungetestete Zeile einfügen und prüfen, ob der geplante Gate/Ratchet damit rot wird. Keine aktuelle Prozentzahl aus README-Zählungen ableiten.

### TYPE-001 — Test-TypeScript wird nicht separat typegecheckt; E2E hat kein tsconfig

**Kategorie / Status:** TypeScript / Build-Qualität / bestätigt  
**Severity:** MEDIUM  
**Prio:** P2  
**Tatsache/Hypothese:** Der Frontend-Produktionsbuild schließt Testdateien aus; Vitest transpiliert Tests ohne den im CI sichtbaren vollständigen TypeScript-Check. Das E2E-Verzeichnis besitzt kein `tsconfig.json` und kein `tsc --noEmit`-Skript.

**Evidenz:** `frontend/tsconfig.build.json:3-8` schließt `*.test.ts(x)`/`*.spec.ts(x)` aus; `frontend/package.json:7-15` definiert `build` mit `frontend/tsconfig.build.json`; `.github/workflows/ci.yml:273-275` führt nur `npm run test` aus. Unter `e2e/` existiert keine `tsconfig.json`; `e2e/package.json:4-10` enthält nur Playwright-Kommandos, und `.github/workflows/playwright.yml:207-212` startet Playwright direkt.

**Auswirkung:** TypeScript-Typfehler in Fixtures, Test-Doubles, Mock-Implementierungen oder E2E-Helpern können bis zur Laufzeit oder bis Playwrights Transpile-Schicht unentdeckt bleiben. Fehlerhafte Mock-Typen schwächen zudem die Testaussage.

**Root Cause:** Produktions-TypeScript, Test-TypeScript und E2E-TypeScript haben keinen gemeinsamen Typecheck-Vertrag.

**Gegenmaßnahme:** Ein separates `tsconfig.test.json` für Frontend-Tests, ein eigenes striktes E2E-`tsconfig` und CI-Schritte `tsc --noEmit` ergänzen; Testdateien nicht aus allen Checks grundsätzlich ausschließen.

**Alternativen:** ESLint mit typbewussten Regeln ist schwächer als `tsc`; Playwright-Transpilation allein ist kein Typecheck.

**Aufwand:** S–M (1–3 Tage plus Typfehlerbereinigung).

**Confidence:** Hoch (0.96).

**Mess-/Verifikationsplan:** Einen synthetischen Typfehler in einem Test-Helper einfügen; beide neuen Checks müssen fehlschlagen, während der Produktionsbuild unabhängig bleibt. Anschließend `tsc --noEmit` und Vitest-/Playwright-Ausführung getrennt archivieren.

### PERF-001 — SeMetrics-Workflow-Gap-Ermittlung ist N+1

**Kategorie / Status:** Datenbankperformance / Hypothese  
**Severity:** MEDIUM  
**Prio:** P2  
**Tatsache/Hypothese:** Für jeden geladenen `WorkflowItemState` wird eine separate `WorkflowHistoryEntry`-Query ausgeführt. Der vorhandene Index auf `item_state, transitioned_at` verbessert Einzelabfragen, eliminiert aber die vielen Roundtrips nicht.

**Evidenz:** `backend/se_metrics/aggregator.py:241-265` lädt alle Item-Zustände und führt anschließend im Loop `WorkflowHistoryEntry.unscoped.filter(item_state=item_state).values_list(...)` aus. `backend/workflow/models.py:267-271` belegt nur den passenden Index. `backend/se_metrics/tests/test_aggregator.py:7-17,161-174` mockt alle vier externen Quellen; kein Test prüft Query-Anzahl oder Laufzeit mit vielen Items.

**Auswirkung:** Bei großen Workspaces wachsen Roundtrips, Connection-Nutzung und Latenz linear mit der Anzahl der Workflowzustände; die vier parallelen Quellen verdecken dies in der Gesamtantwortzeit. Zusätzlich werden alle Item-Zustände materialisiert.

**Root Cause:** Der Adapter ist als einfache Service-Abfrage implementiert und nutzt weder `prefetch_related`/Bulk-Aggregation noch eine Workspace-/Item-Menge mit Limit.

**Gegenmaßnahme:** Historie gebündelt laden oder die besuchten States per Join/Aggregation in einer Query bestimmen; Query-Anzahl und Laufzeit mit 100/1.000/10.000 Items messen, Index-/Explain-Plan und Pagination festhalten.

**Alternativen:** Query-Zähler im Test kann N+1 früh sichtbar machen, beseitigt aber nicht das Produktionsproblem; ein Cache senkt Wiederholung, nicht die Erstberechnung.

**Aufwand:** M (2–5 Tage inklusive Last-/Explain-Profil).

**Confidence:** Hoch für das N+1-Muster (0.90), Auswirkungs-Confidence abhängig von realer Datenmenge.

**Mess-/Verifikationsplan:** `CaptureQueriesContext`/`django-debug` oder DB-Stats mit 1, 100 und 1.000 Item-Zuständen; erwartete Query-Anzahl nach Fix konstant bzw. logarithmic, kein verstecktes Vollscan-Logging. Lasttest mit dokumentierter Antwortzeit.

### PERF-002 — In-Process-Cache-Lock schützt keine vier Produktionsworker

**Kategorie / Status:** Concurrency/Cache / bestätigt  
**Severity:** MEDIUM  
**Prio:** P2  
**Tatsache/Hypothese:** Die Metrics-Cache-Sperre ist ausdrücklich pro Prozess implementiert, während das Produktionsimage vier Gunicorn-Uvicorn-Worker startet. Ein Workspace-Cache-Miss kann daher in mehreren Workern gleichzeitig berechnet werden.

**Evidenz:** `backend/se_metrics/cache.py:15-25,50-63` beschreibt `threading.Lock` und den Redis-Upgrade als Single-Process-Lösung; `backend/Dockerfile:253-260` startet Gunicorn mit `--workers 4`. `backend/se_metrics/tests/test_cache.py:154-193` prüft nur zwei Threads im selben Prozess.

**Auswirkung:** Thundering-Herd-Schutz wirkt im Mehrworker-Betrieb nicht pro Workspace über Prozessgrenzen; mehrere teure Aggregationen und DB-Lasten können parallel entstehen.

**Root Cause:** Die Lock-Schnittstelle ist stabil, aber die Implementierung erfüllt die dokumentierte Multi-Worker-Anforderung nicht.

**Gegenmaßnahme:** Redis-basierte verteilte Sperre mit Timeout/Token-Ownership einsetzen; Lock-Timeout und Fallback explizit messen. Ein lokaler Fast-Lock kann als Optimierung bleiben, ist aber nicht die alleinige Koordination.

**Alternativen:** Queue-basierte Single-Flight-Berechnung mit Celery reduziert Parallelität ebenfalls, ist aber architekturabhängig.

**Aufwand:** S–M (1–3 Tage inklusive Redis-/Worker-Test).

**Confidence:** Hoch (0.99).

**Mess-/Verifikationsplan:** Vier Prozesse gegen dieselbe Cache-Key-Koordination starten und maximal eine teure Berechnung beobachten; Redis-Ausfall, Lock-Lease und Worker-Absturz müssen getrennt getestet werden.

### PERF-003 — LLM-Timeout kann nicht gebundene Restthreads erzeugen

**Kategorie / Status:** Thread-/Connection-Concurrency / Hypothese  
**Severity:** MEDIUM  
**Prio:** P2  
**Tatsache/Hypothese:** Jeder synchrone Router-Aufruf erzeugt einen eigenen Ein-Thread-`ThreadPoolExecutor`; bei Timeout wird `shutdown(wait=False)` verwendet und der Provider-Thread nur als „endet beim Provider-Timeout“ angenommen. Ein Test misst die Freigabe des Request-Threads, nicht Thread-/Connection-Bereinigung nach gegenläufigem Provider-Verhalten.

**Evidenz:** `backend/llm_adapter/router.py:363-438`; `backend/llm_adapter/tests/test_sync_timeout.py:63-80` prüft nur `elapsed < 0.4` mit einem 0,5-s-Sleep und keine Anzahl/Beendigung von Workern.

**Auswirkung:** Unter konkurrierenden Timeouts können Provider-Threads, HTTP-Sockets oder Django-Connections länger als der Sync-Timeout leben und kumulative Ressourcen verbrauchen. Ob dies im realen Providerpfad materialisiert, ist nicht live bestätigt.

**Root Cause:** Request-Timeout und Arbeits-Thread-Lifecycle werden getrennt behandelt; es gibt kein globales Budget oder Stress-/Soak-Test für abgebrochene Calls.

**Gegenmaßnahme:** Provider-Clients mit echtem HTTP-Timeout/AsyncIO verwenden oder einen global begrenzten Pool mit nachvollziehbarem Abbruch betreiben; Thread-/Connection-Zähler und Shutdown-Verhalten testen.

**Alternativen:** Timeout nur im Request-Thread zu verlängern erhöht das Problem; ein async Provider-SDK mit backpressure ist langfristig robuster.

**Aufwand:** M (2–5 Tage inklusive Load-/Leak-Test).

**Confidence:** Mittel (0.72).

**Mess-/Verifikationsplan:** Einen Provider-Stub verwenden, der den eigenen Timeout absichtlich ignoriert; unter N parallelen Calls müssen Request-Antwortzeit, Thread-Anzahl, offene DB-Verbindungen und Prozess-Shutdown innerhalb eines festen Budgets gemessen werden.

### OPS-001 — Kein vollständiger `makemigrations --check`-Gate über alle Apps

**Kategorie / Status:** Migrationen/CI / bestätigt  
**Severity:** MEDIUM  
**Prio:** P2  
**Tatsache/Hypothese:** Es existiert ein Test für den Persistence-App-Migrationszustand, aber kein sichtbarer vollständiger Projekt-Gate über alle installierten Apps. CI und E2E führen `migrate` aus, prüfen aber nicht explizit, ob Modelle und Migrationen im aktuellen Commit auseinanderlaufen.

**Evidenz:** `backend/persistence/tests/test_migrations_and_indexes.py:26-30` ruft `makemigrations persistence --check --dry-run` nur für eine App auf; `.github/workflows/ci.yml:118-144` und `.github/workflows/playwright.yml:114-141` rufen pytest bzw. `python manage.py migrate` auf, nicht den vollständigen Check.

**Auswirkung:** Eine Modeländerung in einer anderen App kann Tests/Deployment mit einem veralteten Schema passieren, bis der Laufzeitpfad die fehlende Tabelle/Spalte verwendet. Ein späteres automatisches Deployment verschiebt die Entdeckung.

**Root Cause:** Migrationsprüfung ist als punktueller Persistence-Test statt als Release-Gate für das gesamte Projekt modelliert.

**Gegenmaßnahme:** `python manage.py makemigrations --check --dry-run` für alle Apps als separaten CI-Schritt vor pytest/Deployment ausführen und das Ergebnis als Artefakt speichern. Jede Migration sollte außerdem einen dokumentierten Rückwärts-/Vorwärtsplan besitzen.

**Alternativen:** Nur `migrate` auf einer frischen DB erkennt Syntax-/Anwendungsfehler, aber keine im Model-State fehlenden Migrationen.

**Aufwand:** S–M (1–3 Tage).

**Confidence:** Hoch (0.94).

**Mess-/Verifikationsplan:** Absichtlich eine Modeländerung ohne Migration in einer isolierten Arbeitskopie ausführen; der neue Gate-Schritt muss mit Dateiname und App fehlschlagen, während die normale Suite diesen Zustand nicht stillschweigend akzeptiert.

### OPS-003 — Compose-Befehle und Dev-Overlay-Anforderung widersprechen sich

**Kategorie / Status:** Entwickler-/Betriebsworkflow / bestätigt  
**Severity:** MEDIUM  
**Prio:** P2  
**Tatsache/Hypothese:** Das Makefile wählt standardmäßig den Legacy-Befehl `docker-compose`, während die Betriebsdokumentation Compose-v2-Kommandos und `!override`-Kompatibilität (Compose >=2.24.4) verlangt. `scripts/build.sh` unterstützt beide Befehle, das Makefile nicht.

**Evidenz:** `Makefile:26-29` setzt `COMPOSE ?= docker-compose`; `deploy/README.md:64-93` und `deploy/docker-compose.yml:26-35` dokumentieren `docker compose` und die Mindestversion für `!override`. `scripts/build.sh:48-56,88-92` prüft dagegen Legacy und Plugin.

**Auswirkung:** Auf einem System nur mit Compose-v2-Plugin scheitern `make up`, `make test` und verwandte Ziele möglicherweise am fehlenden `docker-compose`; auf Legacy-v1 kann das gemergte Dev-Overlay nicht geparst werden. Das erschwert reproduzierbare Test-/Setup-Schritte.

**Root Cause:** Zwei Compose-Kompatibilitätsstrategien wurden an verschiedenen Entry-Points beibehalten.

**Gegenmaßnahme:** Einen kanonischen `docker compose`-Befehl mit klarer Mindestversion verwenden, Legacy entweder explizit als nicht unterstützt markieren oder automatisch und sichtbar ablehnen; Makefile und Skripte teilen dieselbe Detection.

**Alternativen:** Einen versionierten Wrapper (`scripts/compose.sh`) einsetzen, der Plattform und Version prüft und einen verständlichen Fehler liefert.

**Aufwand:** S (bis 1 Tag inklusive Setup-Smoke).

**Confidence:** Hoch (0.96).

**Mess-/Verifikationsplan:** Makefile-Auflösung und `docker compose config` mit leerem Test-Compose auf einer v2-only-Umgebung prüfen; absichtlich altes v1-Parse-Verhalten mit verständlichem Fehler/keinem stillen Fallback verifizieren.

### E2E-003 — `test:e2e:api` verweist auf ein nicht vorhandenes Verzeichnis

**Kategorie / Status:** Entwicklerwerkzeug / bestätigt  
**Severity:** MEDIUM  
**Prio:** P2  
**Tatsache/Hypothese:** Das API-spezifische npm-Skript zielt auf `tests/api/`, aber im versionierten E2E-Baum existiert kein `e2e/tests/api/`-Verzeichnis. Der API-Test liegt als `e2e/tests/api-completeness.spec.ts` direkt unter `e2e/tests/`.

**Evidenz:** `e2e/package.json:4-10`, insbesondere Zeile 8; statische Dateiinventur unter `e2e/tests/api/**` ohne Treffer; vorhandene Datei `e2e/tests/api-completeness.spec.ts`.

**Auswirkung:** Ein Entwickler, der den API-Subset-Befehl nutzt, erhält entweder „no tests found“/Exit-Code 5 oder testet nicht den beabsichtigten API-Scope. Das ist ein toter/irreführender Testpfad und kein verlässlicher lokaler Release-Check.

**Root Cause:** Das Skript wurde nach einer Verzeichnisreorganisation nicht mit dem Playwright-Testlayout synchronisiert.

**Gegenmaßnahme:** Skript auf einen existierenden Glob (`e2e/tests/api-completeness.spec.ts` oder mehrere API-Specs) korrigieren oder das Skript entfernen; im CI/README nur Kommandos veröffentlichen, die per `playwright test --list` nachweislich Tests sammeln.

**Alternativen:** Einen `test:e2e:api`-Tag im Playwright-Konfigurationsmodell verwenden, damit die Auswahl nicht an einen Dateipfad gekoppelt ist.

**Aufwand:** S (bis 1 Stunde inklusive List-Smoke).

**Confidence:** Hoch (0.99).

**Mess-/Verifikationsplan:** `npm run test:e2e:api -- --list` muss eine nichtleere, benannte API-Testliste liefern; ein absichtlich leerer/ungültiger Pfad muss in der Entwicklerdokumentation als Fehler erkannt werden.

### DOC-001 — README-/CI-Testzahlen sind nicht als aktuelle Collection-Baseline gepflegt

**Kategorie / Status:** Dokumentation / bestätigt  
**Severity:** LOW  
**Prio:** P3  
**Tatsache/Hypothese:** README und Workflow-Kommentare nennen historische Gesamtzahlen, während die statische Inventur andere Werte ergibt und keine Collection-Zahlen als versionierte Baseline gespeichert sind.

**Evidenz:** `README.md:1018-1020` nennt 7.100+ pytest-, 1.363 Vitest- und 274 Playwright-Tests; statische Zählung dieses Revisionsstands: 7.647 Python-Testdefinitionen, 2.039 Frontend-Testaufrufe und 304 E2E-Testaufrufe. `.github/workflows/ci.yml:34-39` spricht von 1.286 Tests, obwohl die Matrixpfade nicht das Gesamtrepository abdecken.

**Auswirkung:** Planung, Timeout-Schätzungen und Release-Bewertungen verwenden Zahlen, die weder collection- noch laufzeitidentisch sind. Das kann zu falschen Kapazitätsannahmen und irreführenden Coverage-Aussagen führen.

**Root Cause:** Manuelle Marketing-/README-Zahlen und Workflow-Kommentare wurden nicht durch einen reproduzierbaren Testinventar- oder Collection-Schritt ersetzt.

**Gegenmaßnahme:** Testzahlen als datiertes, generiertes Artefakt aus `pytest --collect-only`, Vitest-/Playwright-List ausweisen; README nur mit revisionsgebundenen Links/Artefakten aktualisieren.

**Alternativen:** Numerische Aussagen ganz vermeiden und stattdessen auf Test-Suites/CI-Artefakte verweisen.

**Aufwand:** S (bis 1 Tag).

**Confidence:** Hoch (0.98).

**Mess-/Verifikationsplan:** Collection- und List-Befehle in einem sauberen Runner ausführen, Zähl-/Methodenstand speichern und README-Zahlen gegen das Artefakt prüfen; jede Abweichung als bewusste Korrektur mit Datum behandeln.

## 5. Positive Befunde und vorhandene Paved Roads

- `backend/reqogniloom/settings_test.py:19-24,65-76` behält PostgreSQL statt SQLite bei, damit RLS-/Tenant-Verhalten nicht durch eine falsche Test-DB verdeckt wird.
- `backend/conftest.py:20-44` bereinigt Tenant-Context vor/nach Tests; `backend/se_metrics/tests/test_rls_worker_threads_405.py` und weitere transaction-basierte Tests adressieren Worker-/RLS-Risiken.
- `backend/mcp_server/views.py:148-156,582-610` begrenzt den Message-Executor auf zehn Worker und ruft `close_old_connections()` an beiden Enden der Arbeit auf.
- `backend/application/event_bus.py:322-362,458-477` trennt kurze Claim-Transaktion, Netzwerk-Dispatch und Write-back; `backend/application/local_uid.py:78-101` nutzt eine gelockte Sequenz statt `MAX(uid)+1`.
- `e2e/playwright.config.ts:20,43-77` setzt globalen Timeout, Retry, Trace, Video und Failure-Screenshots; `e2e/helpers/preconditions.ts:62-114,191-230` bündelt Stack-/Seed-Diagnosen.
- `e2e/tests/visual-regression.spec.ts-snapshots/` enthält Linux- und Windows-Chromium-Baselines; die visuelle Suite maskiert dokumentierte volatile Bereiche, allerdings um den Preis eines wachsenden Workspace-Bestands.
- Die Contract-Matrix `backend/attribute_definitions/tests/test_transport_contract_matrix.py:1-81` und die Architektur-Ratchet `backend/rest_api/tests/test_architecture.py:1-91` prüfen reale vertikale Pfade bzw. verhindern Layering-Regressionen.
- `frontend/Dockerfile:33-41` verwendet im Produktions-Build `npm ci` und `tsc && vite build`; `backend/Dockerfile:156-260` betreibt das Image als Non-Root und mit Health-relevanten Startup-Schritten.

## 6. Abgrenzung zum Dependency-/Release-Bericht 10

- `docs/se/reports/deep_audit/system-audit-2026-09/10-dependencies-supply-chain-and-release.md` bleibt die autoritative Quelle für `DEP-001` (stale/nicht installierte Python-Lockdatei), `DEP-002` (nicht digest-gepinnte Images), `DEP-003` (nicht digestgebundener Scan/Push/SBOM), `DEP-004/005` (Action-/Tooling-Pins) und `DEP-012` (unvollständige Scanflächen).
- Die vorliegenden Befunde `COV-001`, `TYPE-001` und `REL-001` ergänzen diese Lieferkettenanalyse um Test-/Build-Reihenfolge und Release-Gating; sie zählen die Dependency-Befunde nicht doppelt.
- Die Nutzung von `backend/requirements.txt` in Docker/CI (`backend/Dockerfile:29-51`, `.github/workflows/ci.yml:98-100`) und `npm install` in Test-/E2E-Pfaden (`.github/workflows/playwright.yml:187-189`, `testing/docker-compose.test.yml:74`) ist hier nur als Test-/Build-Reproduzierbarkeits-Evidenz vermerkt. Maßnahmen zur autoritativen Lock-/SBOM-Kette gehören in Bericht 10.

## 7. Priorisierte Maßnahmen

1. **Vor dem nächsten Release (P1):** `CI-001`, `CI-002`, `E2E-001`, `E2E-002`, `REL-001` und `OPS-002` schließen oder mit datiertem, verantwortlichem Restrisiko akzeptieren.
2. **Danach (P2):** persistente Fixtures bereinigen, Coverage-Gate einführen, Test-TypeScript prüfen, SeMetrics-N+1 und Multi-Worker-Lock messen, vollständigen Migrationscheck und Compose-Wrapper vereinheitlichen.
3. **Hygiene (P3):** Testzahlen generieren und datierte Artefakte verlinken.

## 8. Verifikations- und Restrisiko-Plan

Da keine Tests, Builds oder Container ausgeführt wurden, sind vor einem Release mindestens folgende Nachweise zu erzeugen:

1. Gesamtcollection und explizite Testpfad-/Coverage-Manifeste archivieren; die 463 derzeit aus der Matrix fallenden Definitionen müssen entweder ausgeführt oder begründet ausgeschlossen sein.
2. Einen echten ASGI-/Redis-Integrationslauf und einen authentifizierten SSE-Roundtrip mit Event-/Message-Assertions durchführen.
3. Den CI-vor-Release-Workflow mit absichtlich rotem Test und absichtlich fehlerhaftem Restore in einer isolierten Umgebung prüfen.
4. `makemigrations --check --dry-run` für alle Apps, TypeScript-Checks für App-/Test-/E2E-Code und Query-Count-/Lastprofile für SeMetrics ausführen.
5. Backup erzeugen, Integrität prüfen, in eine frische DB restoren und einen Post-Restore-Healthcheck dokumentieren.

**Restrisiko:** Die statische Analyse belegt keine aktuelle Testausgabe und keine Laufzeit-CVEs. Sie belegt aber mehrere nachweisbare Lücken, durch die ein grünes CI-/E2E- oder Release-Signal nicht mit vollständiger Laufzeit-, Performance- oder Recovery-Abdeckung gleichgesetzt werden darf.

```text
STATUS: done
RESULT: Statischer Deep-Audit abgeschlossen; 0 P0, 6 P1, 9 P2 und 1 P3 belegt. Höchste Risiken sind die unvollständige Backend-CI-Matrix, übersprungene Live-Transporttests, E2E-Laufzeitabweichungen, fehlende Release-Reihenfolge und nicht zum Sidecar passende Backup-/Restore-Werkzeuge; keine aktuellen Test-, Build- oder CVE-Läufe wurden als grün behauptet.
ARTIFACTS: docs/se/reports/deep_audit/system-audit-2026-09/07-testing-ci-performance-and-dependencies.md
NEXT: [Developer: CI-/E2E-/Release-Gates, Backup-Restore und Fixture-Lifecycle; danach erneute statische Verifikation]
```
