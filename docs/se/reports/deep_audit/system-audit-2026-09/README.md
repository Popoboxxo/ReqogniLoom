---
type: REVIEW
scope: system-audit-2026-09
status: final
date: 2026-09-24
author_agent: documenter
revision: e3df119e52c0cbcc18df02f708567207c0374826
branch: feat/1031-bluepencil-host-bridge
---

# Systemaudit 2026-09 — konsolidierte Abschluss-Synthese

**Auditdatum:** 2026-09-24  
**Repository:** `C:\Repositories\ai-native-reqflow-POC`  
**Prüf-HEAD:** `e3df119e52c0cbcc18df02f708567207c0374826`  
**Branch:** `feat/1031-bluepencil-host-bridge`  
**Maßgebliche Reconciliation:** [`docs/se/reports/deep_audit/system-audit-2026-09/11-consistency-review.md`](11-consistency-review.md)  
**Maßgebliche P1-Korrekturen:** [`docs/se/reports/deep_audit/system-audit-2026-09/12-evidence-validation-and-corrections.md`](12-evidence-validation-and-corrections.md)  
**PR-#1055-Bezug:** Der lokale Git-Stand belegt keinen erfolgreichen Merge und keinen abschließenden PR-Status; diese Synthese behauptet keinen Merge und verwendet den aktuellen HEAD sowie die ausdrücklich markierten Berichtsbelege.  
**Änderungsgrenze dieser Synthese:** ausschließlich `docs/se/reports/deep_audit/system-audit-2026-09/README.md`, [`docs/se/reports/deep_audit/system-audit-2026-09/08-remediation-roadmap-and-alternatives.md`](08-remediation-roadmap-and-alternatives.md) und [`docs/se/reports/deep_audit/system-audit-2026-09/09-evidence-register.md`](09-evidence-register.md); keine Anwendungs-, Test-, CI- oder Infrastrukturdatei wurde geändert.

> **Kurzurteil:** Der geprüfte Stand ist nicht als konsistenter Release-Gate freigabefähig. Es gibt **keinen konsolidierten P0-Befund**, aber mehrere ungeschlossene P1-Standardpfade und eine fehlende einheitliche, revisionsgebundene Test-/Runtime-Evidenz. Die Feststellung ist eine Audit-Aussage, keine Freigabe des Produkts.

## 1. Executive Summary

ReqogniLoom besitzt tragfähige Grundlagen: REST und MCP sind als Adapter auf einen gemeinsamen Application-Service ausgerichtet, Tenant-Isolation wird auf ORM- und PostgreSQL-RLS-Ebene verteidigt, die Transactional-Outbox bindet Event-INSERT und Mutation, und mehrere Contract-/Architecture-Ratchets schützen einzelne Pfade. Die positiven Kontrollen sind in den Themenberichten und im Reconciliation-Bericht ausdrücklich dokumentiert.

Die Gesamtsicht wird jedoch von **20 P1-Tracks (Default-Exposition), 26 P2-Tracks und einem P3-Track** bestimmt. Die nachgelagerte [Kernclaim-Validierung](12-evidence-validation-and-corrections.md) bestätigt 10/12 geprüfte P1-Claims; `CR-09` und `CR-45` sind nur teilweise bestätigt und wurden in diesem Addendum in ihrer Reichweite korrigiert. Bei aktivem Bluepencil-Profil verschiebt sich `CR-25` von P2 zu P1; diese Zahlen sind **kanonisierte Tracks**, nicht eine zweite Zählung der 109 Quellbefunde.

### System Health Score: **1,4 / 5** (risikoadjustiert, nicht statistisch)

| Aussage | Ergebnis |
|---|---|
| P0 | 0 konsolidiert; kein P0 wird aus einer Hypothese eröffnet. |
| Release-Gesamturteil | **Nicht release-reif**; P1-Standardpfade und Release-Nachweise schließen oder als datiertes Restrisiko akzeptieren. |
| Score | 1,4/5, aus dem kanonischen Ledger in [`docs/se/reports/deep_audit/system-audit-2026-09/09-evidence-register.md`](09-evidence-register.md) reproduzierbar. |
| Vertrauen in den Score | Mittel: überwiegend statische Evidenz, gemischte Berichtsrevisionen, keine vollständige HEAD-Test-/Runtime-Baseline. |
| Nächster Schritt | P1-Korrektheits-/Security-Tracks und commitgebundene Release-Gates vor weiterer externer Vertragsfreigabe. |

Der Score ist ein **konservativer Steuerungsindikator**. Er sagt nicht, dass jede einzelne Funktion defekt ist, und er ist kein Wahrscheinlichkeits-, Performance- oder WCAG-Score. Die sechs Dimensionen, Gewichte, Penalty-Koeffizienten und alle Input-IDs sind in Abschnitt 2 offengelegt.

### Wesentliche P1-Gruppen

1. **Tenant-/Berechtigungsgrenzen:** neue Agent-/UI-Keys können `write`/Admin, keinen Workspace-Fence und kein Expiry erben (`CR-03`); `comment.resolve` löst den Zielworkspace nicht auf (`CR-04`).
2. **Fachliche Atomizität:** Workflow-Transition validiert vor dem Lock (`CR-08`), Global-Definitionen werden nicht atomar und ohne vollständigen Orphan-Schutz propagiert (`CR-09`), Interview-Schreibpfade umgehen den Facade-/Audit-Seam (`CR-07`).
3. **Aktive Integrationsverträge:** MCP-Multi-Interview kann ohne `confirmed_proposal` nicht ausgeführt werden (`CR-05`); Workspace-Sprache ist zwischen Blob und ORM-Spalte gespalten (`CR-13`).
4. **Security und Kosten:** Workspaceless Bearer nutzt stale Rollen (`CR-26`); LLM-Budget ist an mehreren Pfaden umgehbar (`CR-20`); ein GitHub-Actions-Input wird direkt in Shell-Quelltext interpoliert (`CR-45`).
5. **Nachweis und Lieferkette:** CI lässt 463 Testdefinitionen aus und überspringt Live-MCP-/Redis-Tests (`CR-30`); E2E testet nicht die ASGI-/nginx-Laufzeit und darf Core-Contract-Fehler skippen (`CR-31`); Release-Scan/Push/SBOM sind nicht digestgebunden (`CR-32`, `CR-38`).

## 2. Reproduzierbare Health-Score-Methodik

### 2.1 Eingangsmenge und Deduplizierung

Grundlage sind die Berichte `01`–`07`, `10` und die zweite Konsistenzprüfung `11`. `11` ist für Deduplizierung, Severity-Kalibrierung und den Umgang mit widersprüchlichen Runtime-/externen Aussagen maßgeblich. Historische `*_DeepAudit.md`- und Archivberichte dienten nur als Kontext; aus ihnen wurde kein aktueller Befund ohne aktuelle Codereferenz übernommen.

Die 109 Quellbefunde werden auf **47 kanonische Tracks `CR-01` bis `CR-47`** abgebildet. Jeder Track wird genau einer primären Score-Dimension zugeordnet; eine sekundäre Auswirkung ändert die Zuordnung nicht. Die vollständige Zuordnung und jede Primärquelle stehen in [`docs/se/reports/deep_audit/system-audit-2026-09/09-evidence-register.md`](09-evidence-register.md).

### 2.2 Dimensionen und Gewichte

| Dimension | Gewicht | Primär zugeordnete Tracks | Interpretation |
|---|---:|---|---|
| Architektur, Daten- und Servicegrenzen | 20 % | `CR-01`, `CR-02`, `CR-06`, `CR-07`, `CR-08`, `CR-09`, `CR-10`, `CR-15`, `CR-16`, `CR-17`, `CR-18`, `CR-44`, `CR-46` | Single-Entry-Point, Tenant-/RLS-Reihenfolge, Transaktionen, Event-/Baseline-Grenzen |
| Security, Auth und Trust Boundaries | 20 % | `CR-03`, `CR-04`, `CR-19`, `CR-20`, `CR-23`, `CR-24`, `CR-25`, `CR-26`, `CR-27`, `CR-28`, `CR-45` | API-Keys, Workspace-Fence, Bearer, Egress, CI-Inputs, Integrations-Grenzen |
| API-, Adapter- und Datenverträge | 15 % | `CR-05`, `CR-11`, `CR-12`, `CR-13`, `CR-14`, `CR-21`, `CR-22`, `CR-42` | REST/MCP/UI/OpenAPI, Source-of-Truth, Manifest und Vertragsdrift |
| Operations, Resilience und Deployment | 15 % | `CR-29`, `CR-31`, `CR-32`, `CR-35`, `CR-36`, `CR-37`, `CR-38`, `CR-39` | ASGI/nginx, Release, Performance, Migration, Backup, Supply Chain |
| Testing, CI, Release und SE-Evidenz | 20 % | `CR-30`, `CR-33`, `CR-34`, `CR-43`, `CR-47` | Collection, E2E, Coverage, Matrix-/Review-Nachweise |
| Frontend, UX und Accessibility | 10 % | `CR-40`, `CR-41` | Navigation, Dirty-State, Reflow, Kontrast, Semantik, AA-Nachweis |
| **Summe** | **100 %** | **47 Tracks** | |

### 2.3 Skala und Formel

Die Health-Score-Skala ist **0–5**: `5` bedeutet in der jeweiligen Dimension eine formal vollständige Kontrolle im geprüften Evidenzrahmen, `0` bedeutet Floor/keine positive Bewertung. Die Severity wird nicht als Wahrscheinlichkeit interpretiert. Für die Score-Berechnung wird jeder kanonische Track genau einmal gezählt:

```text
P(d) = 5,00 × N0(d) + 0,75 × N1(d) + 0,30 × N2(d) + 0,10 × N3(d)
S(d) = max(0, 5 − P(d))
H = Σ (Gewicht(d) × S(d))
```

- `N0` bis `N3`: Anzahl der Tracks mit P0 bis P3 in der primären Dimension.
- P0 penalty: 5,00; ein konsolidierter P0 setzt die betroffene Dimension und damit auch den Gesamtscore auf den Floor 0.
- P1 penalty: 0,75; ein wesentlicher aktiver Standardpfad.
- P2 penalty: 0,30; materielle, begrenzte oder indirekte Lücke.
- P3 penalty: 0,10; lokale Wartungs-/Nachweishygiene.
- Der Floor verhindert, dass viele P2-Befunde in einer Dimension einen formalen Negativwert erzeugen. Er verbirgt deshalb zusätzliche Risiken; die Trackzahl bleibt im Register sichtbar.
- Gewichte summieren sich zu 1,00. `H` wird erst nach der Dimensionsberechnung auf eine Nachkommastelle gerundet.

### 2.4 Reproduzierbare Berechnung

| Dimension | N0 | N1 | N2 | N3 | Penalty | Score | Gewicht | Beitrag |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Architektur/Daten/Service | 0 | 6 | 7 | 0 | 6,60 | 0,00 | 20 % | 0,00 |
| Security/Auth | 0 | 5 | 6 | 0 | 5,55 | 0,00 | 20 % | 0,00 |
| API/Adapter/Daten | 0 | 3 | 5 | 0 | 3,75 | 1,25 | 15 % | 0,19 |
| Operations/Resilience | 0 | 4 | 4 | 0 | 4,20 | 0,80 | 15 % | 0,12 |
| Testing/CI/SE-Evidenz | 0 | 1 | 3 | 1 | 1,75 | 3,25 | 20 % | 0,65 |
| Frontend/UX/Accessibility | 0 | 1 | 1 | 0 | 1,05 | 3,95 | 10 % | 0,40 |
| **Summe** | **0** | **20** | **26** | **1** |  |  | **100 %** | **1,35 → 1,4/5** |

Die Tabelle ist aus den kanonischen Tracks reproduzierbar. `CR-25` wird im Basisszenario als **P2 bei Default-off-Exposition** gezählt. Wird das Bluepencil-Profil aktiviert, ist es für den betroffenen Betriebsmodus P1-relevant; der Score ist dann als konditional zu kennzeichnen und nicht stillschweigend als gleiche Exposition zu behandeln. `CR-41`/`CR-42` enthalten P3-Subteile, werden aber als kanonische P2-Tracks einmal gezählt, um Doppeldeduplizierung zu vermeiden.

### 2.5 Unsicherheit und Gegenprüfbarkeit

Der Wert `1,4/5` ist ein **Punktwert mit Floor-Effekt**, kein Konfidenzintervall. Die Unsicherheit wird wie folgt behandelt:

- Historische Runtime-Aussagen (insbesondere `R01:641–645`) werden nicht auf den Prüf-HEAD übertragen.
- Nicht ausgeführte Checks, externe Registry-/CVE-Aussagen und Performance-Hypothesen erhalten im Evidence Register `O`/`E`/`H`; sie werden nicht als ausgeführte Tests gewertet.
- Gemischte Revisionen der Themenberichte bleiben sichtbar. Die Primärbelege sind mit dem jeweiligen Berichtsstand gekennzeichnet.
- Der Score ist deshalb **nicht geeignet**, um eine einzelne P1-Risikoaussage zu relativieren. Ein P1-Track bleibt P1, auch wenn der Dimensionsfloor erreicht ist.
- Für Reviewer gilt: `1,4/5` conservativ lesen; zur Freigabe müssen die P1-Tracks einzeln geschlossen oder mit Owner, Datum, Restrisiko und Verifikationsbeleg akzeptiert werden. Es wurde keine künstliche statistische Bandbreite erfunden.

## 3. Aktuelle Findings nach Severity

### P0 — 0

Es liegt kein konsolidierter P0-Befund vor. Das bedeutet **nicht**, dass ein P0 ausgeschlossen ist: Ein P0 darf nur bei einem am Prüf-HEAD bestätigten systemweiten Ausfall oder einem unmittelbar belegten schweren Daten-/Security-Schaden eröffnet werden. Hypothesen, historische Logs und nicht ausgeführte Runtime-Checks bleiben P1/P2/O.

### P1 — 20 Tracks im Default-Basisszenario

`CR-01, CR-02, CR-03, CR-04, CR-05, CR-06, CR-07, CR-08, CR-09, CR-12, CR-13, CR-20, CR-26, CR-30, CR-31, CR-32, CR-37, CR-38, CR-40, CR-45`.

`CR-25` ist **bedingt P1** bei aktivem Bluepencil; im Default-/QS-only-Profil wird es als P2 geführt. `CR-31` enthält zusätzlich P2-Subteile, `CR-06` zusätzlich eine P2-Atomizitätsfrage; die kanonische Einstufung bleibt P1 wegen des aktiven Race-/Korrektheitsrisikos.

### P2 — 26 Tracks im Default-Basisszenario

`CR-10, CR-11, CR-14, CR-15, CR-16, CR-17, CR-18, CR-19, CR-21, CR-22, CR-23, CR-24, CR-25, CR-27, CR-28, CR-29, CR-33, CR-34, CR-35, CR-36, CR-39, CR-41, CR-42, CR-44, CR-46, CR-47`.

`CR-41` bündelt neun P2/P3-Semantikbefunde des Frontends; `CR-42` bündelt vier Vertrags-/Produktentscheidungen. Die Quell-IDs bleiben im Evidence Register einzeln auffindbar.

### P3 — 1 kanonischer Track

`CR-43` (historische README-/CI-Testzahlen als nicht versionierte Collection-Baseline). P3-Subteile in `CR-41`/`CR-42` sowie der Quellbefund `FEA-016` werden nicht separat als zusätzliche Tracks gezählt.

### 3.1 Top-10-Risiken

| Rang | Track | Severity / Confidence | Primärbeleg | Auswirkung |
|---:|---|---|---|---|
| 1 | `CR-03` API-Key-Default | P1 / Hoch | `backend/auth_tenancy/models.py:153–162`; `backend/rest_api/api_key_views.py:285–365`; `frontend/src/api/api-keys.ts:15–45` | Neue Agent-/UI-Keys können maximalen Legacy-Scope, alle Owner-Workspaces und unbegrenzte Gültigkeit erhalten. |
| 2 | `CR-04` `comment.resolve`-Fence | P1 / Hoch | `backend/mcp_server/workspace_scope.py:173–176`; `backend/application/comment_service.py:151–173` | Tenantinterner Cross-Workspace-Write trotz fehlendem Ziel-Fence. |
| 3 | `CR-08` Workflow-Race | P1 / Hoch | `backend/workflow/services.py:273–327`; `backend/workflow/lifecycle_manager.py:295–341` | Veraltete Validierung kann nach dem Lock eine fachlich unzulässige Kante in History schreiben. |
| 4 | `CR-09` Global-Definition-Propagation | P1 / Hoch | `backend/workflow/global_definition_store.py:126–317`; `backend/rest_api/global_default_views.py:233–449` | Orphan-Items und partielle Source-of-Truth nach Fehler/Propagation. |
| 5 | `CR-26` Workspaceless Bearer | P1 / Hoch | `backend/auth_tenancy/services/authentication.py:175–220`; `backend/auth_tenancy/rest.py:172–212` | Rollen-/Accountstatus können bis zum Access-Token-TTL stale bleiben. |
| 6 | `CR-20` LLM-Budget | P1 / Hoch | `backend/mcp_server/tools/cross_cutting.py:132–179`; `backend/reqogniloom/settings.py:747–753` | Read-only-/Memory-/Health-Pfade können Kosten ohne zentrales Quota erzeugen. |
| 7 | `CR-30` CI-/Integrationslücke | P1 / Hoch | `.github/workflows/ci.yml:41–55,118–153`; `backend/mcp_server/tests/test_mcp_api_key_roles.py:71–90` | 463 Definitionen und Live-MCP-/Redis-Pfade sind nicht im PR-Gate ausgeführt. |
| 8 | `CR-31` E2E-Laufzeit/Skip | P1 / Hoch | `.github/workflows/playwright.yml:143–212`; `e2e/tests/api-completeness.spec.ts:269–287` | WSGI/Vite-Lauf und skips können eine nicht vorhandene ASGI-/nginx- oder Contract-Qualität als grün ausweisen. |
| 9 | `CR-32` Release-/Provenienz-Gate | P1 / Hoch | `.github/workflows/docker-publish.yml:98–112,142–191`; `.woodpecker.yml:123–127` | Kein sichtbarer Test-vor-Image-Vertrag; Scan, Push, SBOM und Signatur nicht digestgebunden. |
| 10 | `CR-45` GitHub-Actions-Injection | P1 / Hoch | `.github/workflows/version-drift-check.yml:53–78`; `.github/workflows/docker-publish.yml:127–132` | Dispatch-Input/Tag-Output können Shell-Code im Runner auslösen. |

## 4. Quick Wins

Quick Wins sind kleine, reversible Maßnahmen. Sie ersetzen nicht die P1-Korrektheits-, Security- oder Release-Arbeit.

| Vorschlag (keine vergebene Ticket-ID) | Track | Umsetzung | Akzeptanzkriterium |
|---|---|---|---|
| `QUICK-01` Migrationsrolle im Dev-Overlay trennen | `CR-01` | `migrate` bleibt einziger DDL-Service; Backend-Credentials bleiben App-Role. | `docker compose config` zeigt keine Backend-DDL-Ausführung; frischer Stack mit ausstehender Migration wird gesund. |
| `QUICK-02` MCP-Quickstart aus Manifest/Discovery ableiten | `CR-21` | README-Transport, Feldnamen und Toolzahlen aus dem Manifest/Server-Discovery generieren. | CI-Smoke führt `GET /mcp/`, Key-Erstellung, `tools/list` und read-only Call aus; kein `/mcp/stdio/`-Phantom. |
| `QUICK-03` SSE-/HTTP-Batch-Validierung vereinheitlichen | `CR-22` | Gemeinsame JSON-Objekt-Preflight-Prüfung vor Queueing. | Array/ungültiges JSON wird auf beiden Wegen vor `202` mit kontrolliertem `INVALID_REQUEST` abgewiesen. |
| `QUICK-04` Skip-Link im AppShell ergänzen | `CR-40` | Sichtbarer Skip-Link auf `main`; Fokusübergabe und i18n testen. | Tastaturstart: erster Tabstop ist der Skip-Link; Aktivierung setzt den Fokus in den sichtbaren Hauptinhalt. |
| `QUICK-05` Doppelten Autofocus entfernen | `CR-41`/`CR-40` | `autoFocus` im TestRun-Dialog entfernen, `initialFocusRef` als einzige Quelle. | Chromium/Firefox/Safari: sichtbarer Fokus im Namensfeld, kein Fokussprung. |
| `QUICK-06` API-E2E-Skript korrigieren | `CR-31` | `test:e2e:api` auf vorhandene Specs/Tag-Selektion umstellen. | `npm run test:e2e:api -- --list` liefert eine nichtleere API-Testliste. |
| `QUICK-07` Compose-v2-Wrapper vereinheitlichen | `CR-01`/`OPS-003` | Gemeinsame Detection für `docker compose` und Legacy-Fehler. | v2-only-Setup liefert verständlichen Fehler bzw. funktionierenden Wrapper; kein stiller v1-Fallback. |

## 5. Auditgrenzen, Test- und Runtime-Abdeckung

### 5.1 Was die Berichte tatsächlich belegen

| Quelle | Belegte Ausführung | Nicht belegte Aussage |
|---|---|---|
| `R01` | Historische Docker-/Backend-Restart-Beobachtung und statische Architekturprüfung | Kein aktueller Restart-/Health-Status am Prüf-HEAD. |
| `R02` | Statische MCP-/Manifest-/Plugin-Prüfung und positive Ratchets | Kein Server-, Container-, Hermes- oder MCP-Client-Lauf. |
| `R03` | Read-only OpenAPI-Erzeugung; laut Bericht 3 Frontend-Dateien mit 19 Tests und ein Frontend-Build | Kein vollständiger Suite-Lauf, kein PostgreSQL-Host und keine einheitliche HEAD-Baseline. |
| `R04` | Statische Workflow-/Traceability-Prüfung; pytest-Versuch scheiterte an Windows-Plugin/`fcntl` bzw. Django-Initialisierung | Kein grüner Workflow-/Traceability-Lauf. |
| `R05` | Statische Security-/Operations-Prüfung; keine Runtime- oder CVE-Läufe | Kein aktueller Auth-, SSRF-, SSE- oder CI-Injection-Lauf. |
| `R06` | 24 Vitest-Dateien, 277 Tests, 272 bestanden; 5 `localStorage`-Fehler; Lint 0 Fehler/290 Warnungen | Kein vollständiger Frontend-/Playwright-/Screenreader-/Browserlauf. |
| `R07` | Statische Testinventur, CI-/Release-/Performance-/Backup-Analyse | Keine Tests, Builds, Container oder Scanner in diesem Bericht. |
| `R10` | Manifest-/Lock-/SBOM-Sicht und externe Registry-Angaben als Daten des Berichts | Keine unabhängige CVE-Datenbankabfrage, kein Scanner-/SBOM-Lauf. |
| `R11` | Reconciliation von 109 Quellbefunden zu 47 Tracks | Keine neue Codeänderung oder neue Runtime-Messung. |
| Diese Synthese | Konsolidierung, Score und Roadmap auf Basis der obigen Berichte | Keine Test-, Docker-, Browser-, CVE- oder externe Installationsausführung. |

### 5.2 Auditgrenzen

- **Revision:** `R01`–`R04` und `R06` wurden nicht auf `e3df119e...` aktualisiert. Ihre Codeaussagen sind historische Berichtsbelege, keine Behauptung über den heutigen Arbeitsbaum.
- **Runtime:** kein frischer Uvicorn-/nginx-/Redis-/MCP-SSE-Roundtrip, kein Worker-Kill-/Lasttest und kein vollständiger Compose-Startup.
- **Security:** kein aktueller Auth-/SSRF-/MFA-/Refresh-/CI-Injection-Lauf; externe CVE-/Vendor-Aussagen bleiben unbestätigt.
- **Frontend:** keine manuelle NVDA-/JAWS-/VoiceOver-Sitzung, kein vollständiger Axe-/Reflow-Lauf und kein vollständiger Playwright-Lauf.
- **Supply Chain:** kein `pip-audit`, `npm audit`, OSV/Trivy, CycloneDX/SPDX, Cosign- oder Provenance-Lauf.
- **CVE:** In `R10` ausdrücklich **0 bestätigte verwundbare Pakete im Audit**, nicht „0 Schwachstellen“.

## 6. Offene Widersprüche und Hypothesen

1. **Kein aktiver R04-Zählwiderspruch:** Die frühere/initial Dateifassung von `R04` nannte acht P2, während Detailtabelle und Überschriften neun auswiesen. Die aktuelle Quelldatei [`R04:19`](04-workflow-state-machines-and-se.md#1-management-summary) nennt bereits **neun P2**; die frühere Formulierung bleibt nur als Audit-Trail in `R11:52–56` erhalten.
2. `R01` beschreibt einen laufenden Restart-Stack, `R06` keinen laufenden Docker-Stack. Das ist ein Zeit-/Revisionskonflikt; der aktuelle Status bleibt offen.
3. Toolzahlen `218/35` (Manifest), `215/31`, `188/31` und `20/40` sind nicht gleich. Das Manifest ist der aktuelle Anker, die anderen Dokumente sind Driftquellen.
4. Trace-Link-Typen werden in historischen Dokumenten mit 6/8, im aktuellen Code/Katalog mit 11 beschrieben. Für die Synthese zählt `R11:95–97` den Code/Katalog als Implementierungsquelle.
5. API-Key-Defaults werden in `R02`/`R03` als P1, in `R05` als P2 geführt. `R11:98` kalibriert neue fail-open Agent-/UI-Keys als P1 und Legacy-Härtung als P2.
6. „MCP pool bounded“ bedeutet nur `max_workers=10`; Queue-/SSE-/Provider-Arbeit sind nicht bounded (`R11:90`).
7. Bluepencil und Minimal-Compose sind default-off/QS-only. Ihre Sicherheits- und Capability-Lücken bleiben relevant, sind aber nicht als unbedingter Produktions-P1-Fehler zu formulieren.
8. `PERF-001`/`PERF-003` sind Hypothesen über N+1-/Thread-Lifecycle-Wirkung; Messung ist offen. Externe Registry-/CVE-Aussagen sind `E`, nicht bestätigte Findings.
9. Mit der korrigierten `R04`-Dateifassung umfassen die Quellberichte 33 P1, 69 P2 und 7 P3; die 47 kanonischen Tracks sind bewusst dedupliziert. Beide Zählungen dürfen nicht vermischt werden.

## 7. Empfohlene Reihenfolge

### Priorität 0 — nur bei neuer, konsolidierter Bestätigung

Kein P0 ist derzeit konsolidiert. Sollte eine HEAD-nahe Messung einen systemweiten Ausfall, unmittelbaren Datenabfluss oder einen belegten schweren Security-Schaden zeigen: Release einfrieren, Incident-Owner und Forensik-Sicherung benennen, Scope reproduzieren und erst danach remediate. Keine Hypothese in einen P0-Ticket umbenennen.

### Priorität 1 — vor erneuter externer Vertrags-/Produktfreigabe

1. `CR-03`, `CR-04`, `CR-26`, `CR-45`: API-Key-/Workspace-Fence, aktuelle Autorität und CI-Input-Härtung.
2. `CR-05`, `CR-06`, `CR-07`, `CR-08`, `CR-09`, `CR-13`: REST/MCP-Parität, Interview-Atomizität, Workflow-/Global-Definition-Invarianten und Workspace-Sprachquelle.
3. `CR-20`: zentrales Budget/Quota vor jedem Provideraufruf.
4. `CR-30`, `CR-31`, `CR-32`, `CR-37`, `CR-38`: vollständige Collection/Live-Integration, ASGI-/nginx-E2E, commitgebundenes Release, getesteter Restore und reproduzierbare Lock-/Digest-Kette.

### Priorität 2 — danach, vor breiter Skalierung oder AA-Sign-off

`CR-01`, `CR-02`, `CR-18`, `CR-19`, `CR-28`, `CR-29`, `CR-44` für Betrieb/Transport; anschließend `CR-11`, `CR-12`, `CR-14`, `CR-15`, `CR-16`, `CR-17`, `CR-21`, `CR-42`, `CR-46`, `CR-47` für Verträge/SE-SSOT. `CR-40`/`CR-41` benötigen Browser-, Keyboard- und Screenreader-Nachweise; die statischen Kontraste allein sind kein WCAG-2.2-AA-Sign-off.

### Priorität 3 — Hygiene

`CR-33`, `CR-34`, `CR-35`, `CR-36`, `CR-39`, `CR-43` und P3-Subteile: Coverage-Baseline, Typecheck, Query-/Worker-Messung, vollständiger Migrationscheck, SBOM-/Lizenzmatrix und generierte Testzahlen.

## 8. Berichtsindex und Konvention

Der Ordner `docs/se/reports/deep_audit/` enthält historische Einzel-/SSOT-Berichte. Für den revisionsgebundenen 2026-09-Audit wurde der Unterordner `docs/se/reports/deep_audit/system-audit-2026-09/` verwendet, damit die acht Themenberichte, die Reconciliation und die drei Abschlussdateien nicht die historischen Dateien im Parent-Verzeichnis überschreiben. Die Parent-Berichte bleiben unverändert und werden nur verlinkt.

| Datei | Rolle | Status in dieser Synthese |
|---|---|---|
| [`docs/se/reports/deep_audit/system-audit-2026-09/README.md`](README.md) | Index, Executive Summary, Health Score, Priorisierung | neu in diesem Abschlusspaket |
| [`docs/se/reports/deep_audit/system-audit-2026-09/01-architecture-and-boundaries.md`](01-architecture-and-boundaries.md) | Architektur, RLS, Outbox, Deployment | bestehender Themenbericht |
| [`docs/se/reports/deep_audit/system-audit-2026-09/02-agents-plugins-mcp.md`](02-agents-plugins-mcp.md) | Agenten, Plugins, MCP, Hermes, Bluepencil | bestehender Themenbericht |
| [`docs/se/reports/deep_audit/system-audit-2026-09/03-api-ui-data-contract-drift.md`](03-api-ui-data-contract-drift.md) | REST/MCP/UI-/ORM-Verträge | bestehender Themenbericht |
| [`docs/se/reports/deep_audit/system-audit-2026-09/04-workflow-state-machines-and-se.md`](04-workflow-state-machines-and-se.md) | Workflow, Traceability, SE-Evidenz | bestehender Themenbericht |
| [`docs/se/reports/deep_audit/system-audit-2026-09/05-security-resilience-and-operations.md`](05-security-resilience-and-operations.md) | Auth, SSRF, Costs, Operations, CI-Security | bestehender Themenbericht |
| [`docs/se/reports/deep_audit/system-audit-2026-09/06-frontend-ux-accessibility-and-design-system.md`](06-frontend-ux-accessibility-and-design-system.md) | Frontend, UX, Reflow, AA-/Kontrastnachweise | bestehender Themenbericht |
| [`docs/se/reports/deep_audit/system-audit-2026-09/07-testing-ci-performance-and-dependencies.md`](07-testing-ci-performance-and-dependencies.md) | Tests, CI, E2E, Performance, Backup | bestehender Themenbericht |
| [`docs/se/reports/deep_audit/system-audit-2026-09/08-remediation-roadmap-and-alternatives.md`](08-remediation-roadmap-and-alternatives.md) | Drei Zielmodelle, Workstreams, Reihenfolge, Reversibility | zusätzlich erstellt |
| [`docs/se/reports/deep_audit/system-audit-2026-09/09-evidence-register.md`](09-evidence-register.md) | Kanonisches Evidence-/Finding-Register | zusätzlich erstellt |
| [`docs/se/reports/deep_audit/system-audit-2026-09/10-dependencies-supply-chain-and-release.md`](10-dependencies-supply-chain-and-release.md) | Dependencies, SBOM, Lizenzen, Release-Provenienz | bestehender Themenbericht |
| [`docs/se/reports/deep_audit/system-audit-2026-09/11-consistency-review.md`](11-consistency-review.md) | Maßgebliche Reconciliation und Severity-Kalibrierung | bestehender Themenbericht |
| [`docs/se/reports/deep_audit/system-audit-2026-09/12-evidence-validation-and-corrections.md`](12-evidence-validation-and-corrections.md) | Unabhängige P1-Validierung, Korrekturen und Downgrades | neu erstellt |
| [`docs/superpowers/plans/2026-09-24-motivated-improvement-plan.md`](../../../../superpowers/plans/2026-09-24-motivated-improvement-plan.md) | Verbindlicher motivationsorientierter Plan nach Nutzerentscheidungen | neu erstellt |

Historische SSOT-/Archivverweise (unverändert, nur Kontext):

- [`docs/se/reports/deep_audit/McpServerSystem_DeepAudit.md`](../McpServerSystem_DeepAudit.md) – autogenerierter historischer MCP-Test-/Coverage-Bericht, nicht aktuelle Architekturquelle.
- [`docs/se/reports/deep_audit/ReactFrontendSystem_DeepAudit.md`](../ReactFrontendSystem_DeepAudit.md) – historischer Frontend-Audit-Trail.
- [`docs/se/SYSTEM_AUDIT.md`](../../../SYSTEM_AUDIT.md) – historisches System-Audit-Dokument mit veralteter MCP-Topologie.
- [`docs/archive/audits/SYSTEMAUDIT_2026-08-27.md`](../../../../archive/audits/SYSTEMAUDIT_2026-08-27.md) und [`docs/archive/audits/SYSTEMAUDIT_UI_2026-08-27.md`](../../../../archive/audits/SYSTEMAUDIT_UI_2026-08-27.md) – Archivstände; nicht in die aktuelle Score-Menge eingerechnet.

## 9. Transparente Commit- und Arbeitsstandnotiz

Die Git-Prüfung am 2026-09-24 ergab:

```text
HEAD: e3df119e52c0cbcc18df02f708567207c0374826
Branch: feat/1031-bluepencil-host-bridge
origin/...: 94a3737a...
HEAD ist zwei Commits voraus.
```

Im Reflog sind zwei lokale, **docs-only** Commits sichtbar:

- `66e21f56f36b10e9280e10fed75ee709e5bd7d50` – `docs: add architecture boundary audit report`, nur `docs/se/reports/deep_audit/system-audit-2026-09/01-architecture-and-boundaries.md`.
- `e3df119e52c0cbcc18df02f708567207c0374826` – `docs: add frontend accessibility audit report`, nur `docs/se/reports/deep_audit/system-audit-2026-09/06-frontend-ux-accessibility-and-design-system.md`.

Damit ist gegenüber der für diesen Audit geltenden No-Commit-Aufgabe eine **Commit-Grenzverletzung im Arbeitsstand nachweisbar**: Die beiden Commits sind vor dieser Abschlussbearbeitung bereits in der lokalen Historie vorhanden. Aus Git lässt sich jedoch weder der ausführende Worker noch die Absicht sicher ableiten; deshalb wird hier nur der verifizierte Tatbestand dokumentiert. Beide Commits enthalten **keine Anwendungscodeänderung**. Im zum Prüfzeitpunkt verifizierten Arbeitsstand sind `README.md`, `02`–`05` und `07`–`11` untracked; `01` und `06` sind modified. Staged Änderungen waren zum Prüfzeitpunkt nicht vorhanden. Dieses Abschlusspaket führt keine Git-Mutation aus.

## 10. Abschlussstatus

```text
STATUS: done
RESULT: Die drei deutschen Abschlussdateien konsolidieren die Themenberichte 01–07, 10 und die maßgebliche Reconciliation 11 zu einem reproduzierbaren Health Score, einem kanonischen P0–P3-Bild, einer priorisierten Roadmap und einem evidenzbasierten Register. Der geprüfte Stand bleibt wegen P1- und Nachweislücken nicht release-reif; kein P0 wurde ohne neue Bestätigung eröffnet.
ARTIFACTS: docs/se/reports/deep_audit/system-audit-2026-09/README.md; docs/se/reports/deep_audit/system-audit-2026-09/08-remediation-roadmap-and-alternatives.md; docs/se/reports/deep_audit/system-audit-2026-09/09-evidence-register.md
```
